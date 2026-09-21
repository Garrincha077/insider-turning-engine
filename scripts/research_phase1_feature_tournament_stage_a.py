"""Phase-1 insider feature tournament Stage A: outcome-blind feature freeze."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

import research_market_event_audit as market_audit
import research_market_event_audit_v2 as p0

DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
DISCOVERY_END = "2018-12-31"
CONFIRMATION_START = "2019-01-01"
EXPECTED_B0_EXACT_ENTRY = 24192
EXPECTED_B0_DISTINCT_ISSUERS = 4729
DEDUP_SESSIONS = 20
SEALED_YEAR = 2023
F4_BASIS_DAYS = 90

FORBIDDEN_OUTPUT_TOKENS = (
    "raw_21",
    "raw_63",
    "raw_126",
    "raw_252",
    "excess_",
    "mae_",
    "forward_return",
    "future_return",
)

CONTINUOUS_FEATURES = (
    "F1_ABS_DOLLARS",
    "F1_FRACTION_POST",
    "F1_FRACTION_PRE",
    "F1_OWNER_HISTORY_PERCENTILE",
    "F3_RETURN_21",
    "F3_RETURN_63",
    "F3_RETURN_126",
    "F3_RETURN_252",
    "F3_DRAWDOWN_252",
    "F4_DISTANCE_TO_BASIS",
    "DOLLAR_ADV_20",
    "DOLLAR_ADV_60",
    "STOCK_PRICE",
)

FEATURE_VARIANTS = (
    "F1_ABS_DOLLARS",
    "F1_FRACTION_POST",
    "F1_FRACTION_PRE",
    "F1_OWNER_HISTORY_PERCENTILE",
    "F1_ABS_PLUS_FRACTION_POST",
    "F2_DIRECT_VS_INDIRECT",
    "F3_RETURN_21",
    "F3_RETURN_63",
    "F3_RETURN_126",
    "F3_RETURN_252",
    "F3_DRAWDOWN_252",
    "F3_NEW_52W_LOW",
    "F4_ABOVE_BASIS",
    "F4_DISTANCE_TO_BASIS",
    "F4_TRUE_RECLAIM",
    "F4_RECLAIM_PERSIST_2",
    "F4_RECLAIM_PERSIST_5",
)


def _parse_stamp(value: object) -> datetime:
    text = str(value or "").replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _qualified_purchase(row: dict[str, Any]) -> bool:
    security = row.get("security") or {}
    tx = row.get("transaction") or {}
    shares = _float(tx.get("shares"))
    price = _float(tx.get("pricePerShare"))
    return (
        security.get("tableType") == "NON_DERIVATIVE"
        and str(tx.get("code") or "").upper() == "P"
        and str(tx.get("acquiredDisposed") or "").upper() == "A"
        and str(tx.get("economicClassification") or "") == "OPEN_MARKET_PURCHASE"
        and shares is not None
        and shares > 0
        and price is not None
        and price > 0
    )


def _regular(row: tuple[Any, ...] | None) -> bool:
    return row is not None and not bool(row[7]) and int(row[5]) > 0 and int(row[6]) > 0


def _build_market_db(paths: list[Path], db_path: Path) -> None:
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE market (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                trade_count INTEGER NOT NULL,
                terminal INTEGER NOT NULL
            );
            """
        )
        sql = (
            "INSERT INTO market "
            "(ticker,date,open,high,low,close,volume,trade_count,terminal) "
            "VALUES (?,?,?,?,?,?,?,?,?)"
        )
        batch: list[tuple[object, ...]] = []
        seen: set[tuple[str, str]] = set()
        for path in paths:
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                required = {
                    "date",
                    "ticker",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "trade_count",
                    "terminal_candidate",
                }
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError(f"market context missing columns: {path}")
                for row in reader:
                    ticker = str(row["ticker"]).strip().upper()
                    day = str(row["date"])[:10]
                    if int(day[:4]) >= SEALED_YEAR:
                        raise ValueError("sealed OOS market row")
                    key = (ticker, day)
                    if key in seen:
                        continue
                    seen.add(key)
                    batch.append(
                        (
                            ticker,
                            day,
                            float(row["open"]),
                            float(row["high"]),
                            float(row["low"]),
                            float(row["close"]),
                            int(float(row.get("volume") or 0)),
                            int(float(row.get("trade_count") or 0)),
                            int(str(row.get("terminal_candidate") or "").lower() == "true"),
                        )
                    )
                    if len(batch) >= 50000:
                        conn.executemany(sql, batch)
                        batch.clear()
        if batch:
            conn.executemany(sql, batch)
        conn.execute("CREATE INDEX market_ticker_date_idx ON market(ticker,date)")
        conn.commit()
    finally:
        conn.close()


def _market_paths(root: Path, prefix: str, years: range) -> list[Path]:
    paths = []
    for year in years:
        matches = list(root.rglob(f"{prefix}-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one {prefix}-{year}.csv under {root}, got {len(matches)}"
            )
        paths.append(matches[0])
    return paths


def _load_b0_scope(
    *,
    sec_effective: Path,
    adjusted_db: Path,
) -> list[dict[str, Any]]:
    events_by_ticker, _ = market_audit._load_events(sec_effective)
    sessions = p0._expected_sessions()
    session_index = {day: idx for idx, day in enumerate(sessions)}

    candidates: list[dict[str, Any]] = []
    for ticker, events in events_by_ticker.items():
        for event in events:
            if event["identityAmbiguous"]:
                continue
            evaluation = str(event["evaluationSession"])
            if not DEVELOPMENT_START <= evaluation <= DEVELOPMENT_END:
                continue
            index = session_index.get(evaluation)
            if index is None:
                continue
            candidates.append({**event, "ticker": ticker, "evaluationIndex": index})

    candidates.sort(
        key=lambda row: (
            int(row["evaluationIndex"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
            str(row["ticker"]),
        )
    )

    retained: list[dict[str, Any]] = []
    last_by_issuer: dict[str, int] = {}
    for event in candidates:
        cik = str(event["issuerCik"])
        index = int(event["evaluationIndex"])
        previous = last_by_issuer.get(cik)
        if previous is not None and index - previous <= DEDUP_SESSIONS:
            continue
        last_by_issuer[cik] = index
        retained.append(event)

    conn = sqlite3.connect(adjusted_db)
    output: list[dict[str, Any]] = []
    try:
        spy = {
            str(row[0]): row
            for row in conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker='SPY' ORDER BY date"
            ).fetchall()
        }
        for event in retained:
            idx = int(event["evaluationIndex"]) + 1
            if idx >= len(sessions):
                continue
            entry = sessions[idx]
            stock = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? AND date=?",
                (str(event["ticker"]).upper(), entry),
            ).fetchone()
            if not _regular(stock) or not _regular(spy.get(entry)):
                continue
            output.append(
                {
                    "eventNumber": len(output) + 1,
                    "issuerCik": str(event["issuerCik"]),
                    "ticker": str(event["ticker"]).upper(),
                    "knowledgeAtFirst": str(event["knowledgeAtFirst"]),
                    "knowledgeAtLast": str(event["knowledgeAtLast"]),
                    "evaluationSession": str(event["evaluationSession"]),
                    "entrySession": entry,
                }
            )
    finally:
        conn.close()

    if len(output) != EXPECTED_B0_EXACT_ENTRY:
        raise ValueError(
            f"frozen B0 exact-entry scope changed: {len(output)} "
            f"!= {EXPECTED_B0_EXACT_ENTRY}"
        )
    if len({row["issuerCik"] for row in output}) != EXPECTED_B0_DISTINCT_ISSUERS:
        raise ValueError("frozen B0 distinct-issuer scope changed")
    return output


def _load_revisions(
    path: Path,
    issuers: set[str],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            issuer = str((row.get("issuer") or {}).get("cik") or "")
            if issuer not in issuers:
                continue
            knowledge = _parse_stamp((row.get("timestamps") or {}).get("knowledgeAt"))
            if knowledge.year >= SEALED_YEAR:
                raise ValueError("sealed OOS SEC revision")
            lifecycle = row.get("lifecycle") or {}
            valid_from = _parse_stamp(lifecycle.get("validFrom"))
            valid_to_raw = lifecycle.get("validTo")
            valid_to = _parse_stamp(valid_to_raw) if valid_to_raw else None
            row["_knowledge"] = knowledge
            row["_valid_from"] = valid_from
            row["_valid_to"] = valid_to
            result[issuer].append(row)
    for rows in result.values():
        rows.sort(
            key=lambda row: (
                row["_valid_from"],
                str((row.get("source") or {}).get("accessionNumber") or ""),
                str(row.get("revisionId") or ""),
            )
        )
    return result


def _active_purchases(
    rows: list[dict[str, Any]],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    active = []
    for row in rows:
        if row["_valid_from"] > cutoff:
            continue
        valid_to = row["_valid_to"]
        if valid_to is not None and cutoff >= valid_to:
            continue
        lifecycle = row.get("lifecycle") or {}
        if str(lifecycle.get("status") or "").upper() == "VOID":
            continue
        if row["_knowledge"] > cutoff:
            continue
        if _qualified_purchase(row):
            active.append(row)
    return active


def _purchase_value(row: dict[str, Any]) -> float | None:
    tx = row.get("transaction") or {}
    value = _float(tx.get("value"))
    if value is not None and value >= 0:
        return value
    shares = _float(tx.get("shares"))
    price = _float(tx.get("pricePerShare"))
    if shares is None or price is None:
        return None
    return shares * price


def _percentile(value: float, prior: list[float]) -> float | None:
    valid = sorted(item for item in prior if math.isfinite(item) and item >= 0)
    if not valid:
        return None
    transformed = [math.log10(1.0 + item) for item in valid]
    current = math.log10(1.0 + value)
    less = sum(item < current for item in transformed)
    equal = sum(item == current for item in transformed)
    return (less + (equal + 1) / 2) / len(transformed) * 100.0


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot freeze quantile from empty discovery values")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _quintiles(values: list[float]) -> dict[str, float]:
    return {
        "q20": _quantile(values, 0.20),
        "q40": _quantile(values, 0.40),
        "q60": _quantile(values, 0.60),
        "q80": _quantile(values, 0.80),
    }


def _regular_market_rows(
    conn: sqlite3.Connection,
    ticker: str,
) -> list[tuple[Any, ...]]:
    return [
        row
        for row in conn.execute(
            "SELECT date,open,high,low,close,volume,trade_count,terminal "
            "FROM market WHERE ticker=? ORDER BY date",
            (ticker,),
        ).fetchall()
        if _regular(row)
    ]


def _at_or_before(
    rows: list[tuple[Any, ...]],
    day: str,
) -> int | None:
    dates = [str(row[0]) for row in rows]
    idx = bisect.bisect_right(dates, day) - 1
    if idx < 0 or dates[idx] != day:
        return None
    return idx


def _trailing_return(
    rows: list[tuple[Any, ...]],
    idx: int | None,
    sessions: int,
) -> float | None:
    if idx is None or idx - sessions < 0:
        return None
    current = float(rows[idx][4])
    prior = float(rows[idx - sessions][4])
    return current / prior - 1.0 if prior > 0 else None


def _drawdown_252(
    rows: list[tuple[Any, ...]],
    idx: int | None,
) -> float | None:
    if idx is None or idx - 251 < 0:
        return None
    window = rows[idx - 251 : idx + 1]
    high = max(float(row[2]) for row in window)
    close = float(rows[idx][4])
    return 1.0 - close / high if high > 0 else None


def _new_52w_low(
    rows: list[tuple[Any, ...]],
    idx: int | None,
) -> bool | None:
    if idx is None or idx - 251 < 0:
        return None
    window = rows[idx - 251 : idx + 1]
    close = float(rows[idx][4])
    low = min(float(row[4]) for row in window)
    return close <= low + 1e-12


def _adv(
    rows: list[tuple[Any, ...]],
    idx: int | None,
    sessions: int,
) -> float | None:
    if idx is None or idx - sessions + 1 < 0:
        return None
    window = rows[idx - sessions + 1 : idx + 1]
    dollars = [float(row[4]) * int(row[5]) for row in window]
    return statistics.fmean(dollars) if dollars else None


def _event_features(
    *,
    event: dict[str, Any],
    issuer_rows: list[dict[str, Any]],
    adjusted_rows: list[tuple[Any, ...]],
    raw_rows: list[tuple[Any, ...]],
    calendar: Any,
) -> dict[str, Any]:
    evaluation = str(event["evaluationSession"])
    cutoff = calendar.session_close(pd.Timestamp(evaluation)).to_pydatetime()
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    cutoff = cutoff.astimezone(UTC)

    active = _active_purchases(issuer_rows, cutoff)
    current_rows = []
    for row in active:
        row_session = market_audit._evaluation_session(
            row["_knowledge"].isoformat(),
            calendar,
        )
        if row_session == evaluation:
            current_rows.append(row)

    values = [value for row in current_rows if (value := _purchase_value(row)) is not None]
    f1_abs = sum(values) if values else None

    fractions_post: list[float] = []
    fractions_pre: list[float] = []
    owner_history: list[float] = []
    ownerships: set[str] = set()

    for row in current_rows:
        tx = row.get("transaction") or {}
        shares = _float(tx.get("shares"))
        post = _float(tx.get("postTransactionShares"))
        value = _purchase_value(row)
        if shares is not None and post is not None and 0 < shares <= post:
            fractions_post.append(shares / post)
            pre = post - shares
            if pre > 0:
                fractions_pre.append(shares / pre)

        ownership = str(tx.get("ownershipNature") or "").upper()
        if ownership in {"D", "I"}:
            ownerships.add(ownership)

        owner = str((row.get("reportingOwner") or {}).get("cik") or "")
        tx_date = str(tx.get("transactionDate") or "")[:10]
        if value is not None and owner and tx_date:
            prior = []
            for old in active:
                if str((old.get("reportingOwner") or {}).get("cik") or "") != owner:
                    continue
                old_tx = old.get("transaction") or {}
                old_date = str(old_tx.get("transactionDate") or "")[:10]
                if not old_date or old_date >= tx_date:
                    continue
                old_value = _purchase_value(old)
                if old_value is not None:
                    prior.append(old_value)
            pct = _percentile(value, prior)
            if pct is not None:
                owner_history.append(pct)

    if ownerships == {"D"}:
        ownership_category = "DIRECT_ONLY"
    elif ownerships == {"I"}:
        ownership_category = "INDIRECT_ONLY"
    elif ownerships == {"D", "I"}:
        ownership_category = "MIXED"
    else:
        ownership_category = "UNKNOWN"

    adjusted_idx = _at_or_before(adjusted_rows, evaluation)
    raw_idx = _at_or_before(raw_rows, evaluation)

    f3 = {
        "F3_RETURN_21": _trailing_return(adjusted_rows, adjusted_idx, 21),
        "F3_RETURN_63": _trailing_return(adjusted_rows, adjusted_idx, 63),
        "F3_RETURN_126": _trailing_return(adjusted_rows, adjusted_idx, 126),
        "F3_RETURN_252": _trailing_return(adjusted_rows, adjusted_idx, 252),
        "F3_DRAWDOWN_252": _drawdown_252(adjusted_rows, adjusted_idx),
        "F3_NEW_52W_LOW": _new_52w_low(adjusted_rows, adjusted_idx),
    }

    stock_price = float(raw_rows[raw_idx][4]) if raw_idx is not None else None
    adv20 = _adv(raw_rows, raw_idx, 20)
    adv60 = _adv(raw_rows, raw_idx, 60)

    lower = datetime.fromisoformat(evaluation).date() - timedelta(days=F4_BASIS_DAYS)
    basis_rows = []
    for row in active:
        tx = row.get("transaction") or {}
        tx_date_text = str(tx.get("transactionDate") or "")[:10]
        if not tx_date_text:
            continue
        tx_date = datetime.fromisoformat(tx_date_text).date()
        if lower <= tx_date <= datetime.fromisoformat(evaluation).date():
            shares = _float(tx.get("shares"))
            price = _float(tx.get("pricePerShare"))
            if shares is not None and price is not None and shares > 0 and price > 0:
                basis_rows.append((shares, price))

    basis_shares = sum(item[0] for item in basis_rows)
    basis_dollars = sum(item[0] * item[1] for item in basis_rows)
    basis = basis_dollars / basis_shares if basis_shares > 0 else None

    above_basis: bool | None = None
    distance: float | None = None
    true_reclaim: bool | None = None
    persist2: bool | None = None
    persist5: bool | None = None

    if basis is not None and stock_price is not None and raw_idx is not None:
        above_basis = stock_price >= basis
        distance = stock_price / basis - 1.0
        if raw_idx >= 1:
            true_reclaim = (
                float(raw_rows[raw_idx - 1][4]) < basis
                and float(raw_rows[raw_idx][4]) >= basis
            )
        if raw_idx >= 2:
            persist2 = (
                float(raw_rows[raw_idx - 2][4]) < basis
                and all(
                    float(raw_rows[index][4]) >= basis
                    for index in range(raw_idx - 1, raw_idx + 1)
                )
            )
        if raw_idx >= 5:
            persist5 = (
                float(raw_rows[raw_idx - 5][4]) < basis
                and all(
                    float(raw_rows[index][4]) >= basis
                    for index in range(raw_idx - 4, raw_idx + 1)
                )
            )

    return {
        **event,
        "F1_ABS_DOLLARS": f1_abs,
        "F1_FRACTION_POST": max(fractions_post) if fractions_post else None,
        "F1_FRACTION_PRE": max(fractions_pre) if fractions_pre else None,
        "F1_OWNER_HISTORY_PERCENTILE": (
            max(owner_history) if owner_history else None
        ),
        "F1_ABS_PLUS_FRACTION_POST": None,
        "F2_OWNERSHIP_CATEGORY": ownership_category,
        "F2_DIRECT_VS_INDIRECT": (
            ownership_category
            if ownership_category in {"DIRECT_ONLY", "INDIRECT_ONLY"}
            else None
        ),
        **f3,
        "F4_BASIS_90D": basis,
        "F4_ABOVE_BASIS": above_basis,
        "F4_DISTANCE_TO_BASIS": distance,
        "F4_TRUE_RECLAIM": true_reclaim,
        "F4_RECLAIM_PERSIST_2": persist2,
        "F4_RECLAIM_PERSIST_5": persist5,
        "DOLLAR_ADV_20": adv20,
        "DOLLAR_ADV_60": adv60,
        "STOCK_PRICE": stock_price,
        "PIT_MARKET_CAP": None,
        "PIT_MARKET_CAP_STATUS": "PIT_BLOCKED_PENDING_RAW_PRICE_AND_PIT_SHARES",
        "CURRENT_EVENT_QUALIFIED_ROWS": len(current_rows),
    }


def _coverage_class(
    observed: int,
    total: int,
    annual: dict[int, tuple[int, int]],
) -> str:
    overall = observed / total if total else 0.0
    rates = [
        seen / count if count else 0.0
        for _year, (seen, count) in sorted(annual.items())
    ]
    if overall >= 0.50 and rates and min(rates) >= 0.35:
        return "GENERAL_ELIGIBLE"
    if overall >= 0.15 and rates and min(rates) >= 0.10:
        return "SPECIALTY_ELIGIBLE"
    return "BELOW_SPECIALTY"


def _is_observed(value: object) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _scope_digest(rows: list[dict[str, Any]]) -> str:
    keys = [
        {
            "eventNumber": row["eventNumber"],
            "issuerCik": row["issuerCik"],
            "ticker": row["ticker"],
            "evaluationSession": row["evaluationSession"],
            "entrySession": row["entrySession"],
        }
        for row in rows
    ]
    payload = json.dumps(
        keys,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def run(
    *,
    sec_effective: Path,
    sec_revisions: Path,
    adjusted_root: Path,
    raw_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    adjusted_paths = _market_paths(
        adjusted_root,
        "canonical-market",
        range(2016, 2022),
    )
    raw_paths = _market_paths(
        raw_root,
        "raw-feature-market",
        range(2015, 2021),
    )
    adjusted_db = output / "stage-a-adjusted.sqlite"
    raw_db = output / "stage-a-raw.sqlite"
    _build_market_db(adjusted_paths, adjusted_db)
    _build_market_db(raw_paths, raw_db)

    try:
        scope = _load_b0_scope(
            sec_effective=sec_effective,
            adjusted_db=adjusted_db,
        )
        issuers = {row["issuerCik"] for row in scope}
        revisions = _load_revisions(sec_revisions, issuers)
        calendar = xcals.get_calendar("XNYS")

        adjusted_conn = sqlite3.connect(adjusted_db)
        raw_conn = sqlite3.connect(raw_db)
        matrix: list[dict[str, Any]] = []
        try:
            adjusted_cache: dict[str, list[tuple[Any, ...]]] = {}
            raw_cache: dict[str, list[tuple[Any, ...]]] = {}
            for event in scope:
                ticker = str(event["ticker"])
                if ticker not in adjusted_cache:
                    adjusted_cache[ticker] = _regular_market_rows(
                        adjusted_conn,
                        ticker,
                    )
                if ticker not in raw_cache:
                    raw_cache[ticker] = _regular_market_rows(raw_conn, ticker)
                matrix.append(
                    _event_features(
                        event=event,
                        issuer_rows=revisions.get(event["issuerCik"], []),
                        adjusted_rows=adjusted_cache[ticker],
                        raw_rows=raw_cache[ticker],
                        calendar=calendar,
                    )
                )
        finally:
            adjusted_conn.close()
            raw_conn.close()

        discovery = [
            row
            for row in matrix
            if row["evaluationSession"] <= DISCOVERY_END
        ]
        confirmation = [
            row
            for row in matrix
            if row["evaluationSession"] >= CONFIRMATION_START
        ]

        cutpoints: dict[str, Any] = {}
        for feature in CONTINUOUS_FEATURES:
            values = [
                float(row[feature])
                for row in discovery
                if _is_observed(row.get(feature))
            ]
            cutpoints[feature] = {
                "method": "linear empirical quintiles on 2016-2018 only",
                "n": len(values),
                **(_quintiles(values) if values else {}),
            }

        abs_q60 = cutpoints["F1_ABS_DOLLARS"].get("q60")
        fraction_q60 = cutpoints["F1_FRACTION_POST"].get("q60")
        if abs_q60 is not None and fraction_q60 is not None:
            for row in matrix:
                dollars = row["F1_ABS_DOLLARS"]
                fraction = row["F1_FRACTION_POST"]
                if dollars is not None and fraction is not None:
                    row["F1_ABS_PLUS_FRACTION_POST"] = (
                        float(dollars) >= float(abs_q60)
                        and float(fraction) >= float(fraction_q60)
                    )

        coverage: dict[str, Any] = {}
        for feature in FEATURE_VARIANTS:
            observed = sum(_is_observed(row.get(feature)) for row in matrix)
            annual: dict[int, tuple[int, int]] = {}
            for year in range(2016, 2021):
                yearly = [
                    row
                    for row in matrix
                    if int(str(row["evaluationSession"])[:4]) == year
                ]
                annual[year] = (
                    sum(_is_observed(row.get(feature)) for row in yearly),
                    len(yearly),
                )
            coverage[feature] = {
                "observed": observed,
                "total": len(matrix),
                "overallRate": observed / len(matrix),
                "annual": {
                    str(year): {
                        "observed": seen,
                        "total": total,
                        "rate": seen / total if total else None,
                    }
                    for year, (seen, total) in annual.items()
                },
                "coverageClass": _coverage_class(observed, len(matrix), annual),
            }

        context_coverage = {}
        for feature in ("DOLLAR_ADV_20", "DOLLAR_ADV_60", "STOCK_PRICE"):
            observed = sum(_is_observed(row.get(feature)) for row in matrix)
            context_coverage[feature] = {
                "observed": observed,
                "total": len(matrix),
                "overallRate": observed / len(matrix),
            }
        context_coverage["PIT_MARKET_CAP"] = {
            "status": "PIT_BLOCKED_PENDING_RAW_PRICE_AND_PIT_SHARES",
            "substitutionAllowed": False,
        }

        fieldnames = list(matrix[0].keys())
        lowered = " ".join(fieldnames).lower()
        if any(token in lowered for token in FORBIDDEN_OUTPUT_TOKENS):
            raise ValueError("Stage A output contains forbidden outcome field")

        with (output / "stage-a-feature-matrix.csv").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(matrix)

        (output / "stage-a-cutpoints.json").write_text(
            json.dumps(cutpoints, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        summary = {
            "schemaVersion": "1.0.0",
            "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_STAGE_A_FROZEN",
            "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
            "researchOnly": True,
            "forwardReturnsRead": False,
            "outcomeFieldsRead": [],
            "maeRead": False,
            "robustnessRead": False,
            "validationOpened": False,
            "oosOpened": False,
            "productionScoringChanged": False,
            "marketCapStatus": "PIT_BLOCKED_PENDING_RAW_PRICE_AND_PIT_SHARES",
            "scope": {
                "events": len(matrix),
                "distinctIssuers": len({row["issuerCik"] for row in matrix}),
                "scopeKeySha256": _scope_digest(matrix),
                "discoveryEvents2016To2018": len(discovery),
                "confirmationEvents2019To2020": len(confirmation),
                "eventUnit": "frozen B0 exact-entry issuer event",
                "dedupSessions": DEDUP_SESSIONS,
            },
            "coverage": coverage,
            "contextCoverage": context_coverage,
            "cutpoints": cutpoints,
            "nextGate": (
                "freeze exact Stage-B event-horizon scope and complete "
                "performance-blind security continuity to zero unresolved"
            ),
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        adjusted_db.unlink(missing_ok=True)
        raw_db.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-effective", type=Path, required=True)
    parser.add_argument("--sec-revisions", type=Path, required=True)
    parser.add_argument("--adjusted-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        sec_effective=args.sec_effective,
        sec_revisions=args.sec_revisions,
        adjusted_root=args.adjusted_root,
        raw_root=args.raw_root,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
