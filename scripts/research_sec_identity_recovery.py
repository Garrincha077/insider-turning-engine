"""Research-only PIT recovery diagnostic for missing SEC issuer tickers.

The diagnostic never reads 2023+ data and never mutates the canonical SEC data.
For qualified issuer-session purchase events whose filing ticker is missing or an
explicit audit placeholder, it asks whether a real ticker for the same issuer CIK
was already observable in SEC data at or before the event knowledge time.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd
from research_market_event_audit import (
    END_YEAR,
    IDENTITY_PLACEHOLDERS,
    SEALED_YEAR,
    START_YEAR,
    _evaluation_session,
    _qualified_purchase,
)

STRICT_LOOKBACK_DAYS = 90
EXTENDED_LOOKBACK_DAYS = 365


def _real_ticker(value: object) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    if not ticker or ticker in IDENTITY_PLACEHOLDERS:
        return None
    return ticker


def _age_days(older: str, newer: str) -> float:
    return float((pd.Timestamp(newer) - pd.Timestamp(older)).total_seconds() / 86_400)


def run(*, sec_path: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    calendar = xcals.get_calendar("XNYS")
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    observations: dict[str, list[tuple[str, str]]] = defaultdict(list)
    rows_read = 0

    with sec_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            knowledge = str(row["timestamps"]["knowledgeAt"])
            year = int(knowledge[:4])
            if year >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if not START_YEAR <= year <= END_YEAR:
                continue
            rows_read += 1

            cik = str(row.get("issuer", {}).get("cik") or "")
            ticker = _real_ticker(row.get("issuer", {}).get("ticker"))
            if cik and ticker:
                observations[cik].append((knowledge, ticker))

            if not _qualified_purchase(row):
                continue
            evaluation_session = _evaluation_session(knowledge, calendar)
            key = (cik, evaluation_session)
            event = grouped.setdefault(
                key,
                {
                    "issuerCik": cik,
                    "evaluationSession": evaluation_session,
                    "knowledgeAtFirst": knowledge,
                    "knowledgeAtLast": knowledge,
                    "tickers": set(),
                    "rawQualifiedRows": 0,
                },
            )
            event["knowledgeAtFirst"] = min(str(event["knowledgeAtFirst"]), knowledge)
            event["knowledgeAtLast"] = max(str(event["knowledgeAtLast"]), knowledge)
            event["rawQualifiedRows"] += 1
            raw_ticker = row.get("issuer", {}).get("ticker")
            if raw_ticker:
                event["tickers"].add(str(raw_ticker).strip().upper())

    for cik in observations:
        observations[cik].sort()

    targets: list[dict[str, Any]] = []
    for event in grouped.values():
        tickers = sorted(event.pop("tickers"))
        real = [ticker for ticker in tickers if ticker not in IDENTITY_PLACEHOLDERS]
        if real:
            continue
        event["identityProblem"] = "placeholderOnly" if tickers else "missingTicker"
        targets.append(event)

    results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    recovered_tickers: Counter[str] = Counter()
    problem_counts: Counter[str] = Counter()

    for event in targets:
        cik = str(event["issuerCik"])
        cutoff = str(event["knowledgeAtFirst"])
        prior = [(ts, ticker) for ts, ticker in observations.get(cik, []) if ts <= cutoff]
        problem = str(event["identityProblem"])
        problem_counts[problem] += 1

        status = "NO_PRIOR_REAL_TICKER"
        recovered: str | None = None
        latest_at: str | None = None
        age_days: float | None = None
        trailing_90: list[str] = []
        trailing_365: list[str] = []

        if prior:
            latest_at, latest_ticker = prior[-1]
            age_days = _age_days(latest_at, cutoff)
            trailing_90 = sorted(
                {
                    ticker
                    for ts, ticker in prior
                    if _age_days(ts, cutoff) <= STRICT_LOOKBACK_DAYS
                }
            )
            trailing_365 = sorted(
                {
                    ticker
                    for ts, ticker in prior
                    if _age_days(ts, cutoff) <= EXTENDED_LOOKBACK_DAYS
                }
            )

            if age_days <= STRICT_LOOKBACK_DAYS and trailing_90 == [latest_ticker]:
                status = "RECOVERABLE_STRICT_90D"
                recovered = latest_ticker
            elif age_days <= EXTENDED_LOOKBACK_DAYS and trailing_365 == [latest_ticker]:
                status = "RECOVERABLE_UNIQUE_365D"
                recovered = latest_ticker
            elif age_days > EXTENDED_LOOKBACK_DAYS:
                status = "PRIOR_TICKER_STALE_GT365D"
            else:
                status = "PRIOR_TICKER_AMBIGUOUS"

        status_counts[status] += 1
        if recovered:
            recovered_tickers[recovered] += 1

        results.append(
            {
                "issuerCik": cik,
                "evaluationSession": str(event["evaluationSession"]),
                "knowledgeAtFirst": cutoff,
                "knowledgeAtLast": str(event["knowledgeAtLast"]),
                "rawQualifiedRows": int(event["rawQualifiedRows"]),
                "identityProblem": problem,
                "recoveryStatus": status,
                "recoveredTicker": recovered,
                "latestPriorRealTickerAt": latest_at,
                "latestPriorRealTickerAgeDays": age_days,
                "uniqueRealTickersTrailing90d": trailing_90,
                "uniqueRealTickersTrailing365d": trailing_365,
            }
        )

    results.sort(
        key=lambda row: (
            str(row["recoveryStatus"]),
            str(row["issuerCik"]),
            str(row["evaluationSession"]),
        )
    )
    (output / "identity-recovery-events.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    target_count = len(targets)
    strict = status_counts["RECOVERABLE_STRICT_90D"]
    extended = status_counts["RECOVERABLE_UNIQUE_365D"]
    max_allowed_missing = int(0.01 * len(grouped))
    strict_remaining = target_count - strict
    strict_plus_extended_remaining = target_count - strict - extended

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "PIT CIK-to-ticker recovery diagnostic",
        "period": f"{START_YEAR}-{END_YEAR}",
        "effectiveSecRowsRead": rows_read,
        "qualifiedIssuerSessionEvents": len(grouped),
        "identityProblemEvents": target_count,
        "identityProblemCounts": dict(sorted(problem_counts.items())),
        "recoveryStatusCounts": dict(sorted(status_counts.items())),
        "strict90dRecoverable": strict,
        "strict90dRecoveryRate": strict / target_count if target_count else 0.0,
        "strictPlusUnique365dRecoverable": strict + extended,
        "strictPlusUnique365dRecoveryRate": (
            (strict + extended) / target_count if target_count else 0.0
        ),
        "remainingAfterStrict90d": strict_remaining,
        "remainingAfterStrictPlusUnique365d": strict_plus_extended_remaining,
        "onePctGateMaxMissingEventsApprox": max_allowed_missing,
        "wouldStrict90dMeetOnePctIdentityGate": strict_remaining <= max_allowed_missing,
        "wouldStrictPlusUnique365dMeetOnePctIdentityGate": (
            strict_plus_extended_remaining <= max_allowed_missing
        ),
        "topRecoveredTickers": [
            {"ticker": ticker, "issuerSessionEvents": count}
            for ticker, count in recovered_tickers.most_common(30)
        ],
        "policy": (
            "Only ticker observations for the same issuer CIK with knowledgeAt at or before "
            "the event are eligible. Strict recovery requires a unique real ticker within 90 "
            "days; the 365-day tier is diagnostic and remains separate. No future ticker is used."
        ),
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalSecChanged": False,
        "status": "SEC_PIT_IDENTITY_RECOVERY_DIAGNOSTIC_COMPLETE",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(sec_path=args.sec, output=args.output)


if __name__ == "__main__":
    main()
