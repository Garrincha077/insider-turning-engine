"""Development-only attribution of the canonical B1 126-session return tail."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PRIMARY_HORIZON = 126
DEVELOPMENT_START_YEAR = 2016
DEVELOPMENT_END_YEAR = 2020
SEALED_YEAR = 2023
TOP_FRACTION = 0.01
STATUS = "PHASE1_B1_TAIL_ATTRIBUTION_COMPLETE"

DATE_FIELDS = (
    "knowledgeAtFirst",
    "evaluationSession",
    "entrySession",
    "exit_21",
    "exit_63",
    "exit_126",
    "exit_252",
)


def _parse_float(value: object, *, field: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {field}")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}")
    return number


def _date_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if len(text) < 10:
        raise ValueError(f"invalid {field}")
    try:
        int(text[:4])
        int(text[5:7])
        int(text[8:10])
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    return text[:10]


def _date_year(value: object, *, field: str) -> int:
    return int(_date_text(value, field=field)[:4])


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _win_rate(values: list[float]) -> float | None:
    return sum(value > 0.0 for value in values) / len(values) if values else None


def _top_removed_mean(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = math.floor(len(ordered) * fraction)
    kept = ordered[: len(ordered) - cut] if cut else ordered
    return _mean(kept)


def _trimmed_mean(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = math.floor(len(ordered) * fraction)
    kept = ordered[cut : len(ordered) - cut if cut else len(ordered)]
    return _mean(kept)


def _summary_stats(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": _mean(values),
        "median": _median(values),
        "winRate": _win_rate(values),
    }


def _validate_source_summary(summary: dict[str, Any]) -> None:
    if summary.get("status") != "PHASE1_B1_DEVELOPMENT_DESCRIPTIVE_COMPLETE":
        raise ValueError("unexpected B1 source summary status")
    if summary.get("primaryHorizonSessions") != PRIMARY_HORIZON:
        raise ValueError("unexpected B1 primary horizon")
    if summary.get("researchOnly") is not True:
        raise ValueError("source summary is not research-only")
    if summary.get("oosOpened") is not False:
        raise ValueError("source summary indicates OOS was opened")
    if summary.get("productionScoringChanged") is not False:
        raise ValueError("source summary indicates production scoring changed")
    if summary.get("period") != "2016-2020 XNYS evaluation-session cohort":
        raise ValueError("unexpected B1 development period")
    if summary.get("outcomeMarketBoundary") != "2016-2022 only":
        raise ValueError("unexpected B1 outcome boundary")


def _load_rows(path: Path) -> list[dict[str, str]]:
    required = {
        "issuerCik",
        "ticker",
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        "opportunisticOwnerCount",
        "rawOpportunisticPurchaseRows",
        "exit_126",
        "raw_126",
        "excess_126",
    }
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        if not required.issubset(fields):
            raise ValueError(f"B1 events missing required fields: {sorted(required - fields)}")
        rows = list(reader)
    if not rows:
        raise ValueError("B1 events file is empty")
    return rows


def _validate_global_boundaries(rows: list[dict[str, str]]) -> None:
    for row in rows:
        evaluation_year = _date_year(row["evaluationSession"], field="evaluationSession")
        if not DEVELOPMENT_START_YEAR <= evaluation_year <= DEVELOPMENT_END_YEAR:
            raise ValueError("evaluationSession outside frozen development cohort")
        for field in DATE_FIELDS:
            text = str(row.get(field) or "").strip()
            if not text:
                continue
            if _date_year(text, field=field) >= SEALED_YEAR:
                raise ValueError(f"sealed OOS boundary violated by {field}")


def _mature_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if str(row.get("excess_126") or "").strip()]


def _excess(row: dict[str, str]) -> float:
    return _parse_float(row["excess_126"], field="excess_126")


def _tail_sort_key(row: dict[str, str]) -> tuple[float, str, str, str]:
    return (
        -_excess(row),
        _date_text(row["evaluationSession"], field="evaluationSession"),
        str(row["issuerCik"]).strip(),
        str(row["ticker"]).strip(),
    )


def _canonical_reproduction(
    mature: list[dict[str, str]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    values = [_excess(row) for row in mature]
    expected = summary["horizons"][str(PRIMARY_HORIZON)]
    actual = {
        "maturedOutcomeCount": len(values),
        "spyExcessMean": _mean(values),
        "spyExcessMedian": _median(values),
        "spyExcessWinRate": _win_rate(values),
    }
    if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
        raise ValueError("canonical mature count mismatch")
    for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
        if not math.isclose(actual[key], expected[key], rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"canonical {key} mismatch")
    return actual


def _most_common(counter: Counter[str]) -> dict[str, Any]:
    if not counter:
        return {"value": None, "count": 0, "share": None}
    value, count = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
    total = sum(counter.values())
    return {"value": value, "count": count, "share": count / total}


def _audit_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "issuerCik": str(row["issuerCik"]).strip(),
        "ticker": str(row["ticker"]).strip(),
        "evaluationSession": _date_text(
            row["evaluationSession"],
            field="evaluationSession",
        ),
        "entrySession": _date_text(row["entrySession"], field="entrySession"),
        "exitSession": _date_text(row["exit_126"], field="exit_126"),
        "entryOpen": _parse_float(row["entryOpen"], field="entryOpen"),
        "raw126": _parse_float(row["raw_126"], field="raw_126"),
        "excess126": _excess(row),
        "opportunisticOwnerCount": int(row["opportunisticOwnerCount"]),
        "rawOpportunisticPurchaseRows": int(row["rawOpportunisticPurchaseRows"]),
    }


def _sanity_failures(row: dict[str, str]) -> list[str]:
    failures: list[str] = []
    issuer = str(row.get("issuerCik") or "").strip()
    ticker = str(row.get("ticker") or "").strip()
    if not issuer:
        failures.append("MISSING_ISSUER_CIK")
    if not ticker:
        failures.append("MISSING_TICKER")
    try:
        knowledge = _date_text(row["knowledgeAtFirst"], field="knowledgeAtFirst")
        evaluation = _date_text(row["evaluationSession"], field="evaluationSession")
        entry = _date_text(row["entrySession"], field="entrySession")
        exit_126 = _date_text(row["exit_126"], field="exit_126")
        for field, value in (
            ("knowledgeAtFirst", knowledge),
            ("evaluationSession", evaluation),
            ("entrySession", entry),
            ("exit_126", exit_126),
        ):
            if int(value[:4]) >= SEALED_YEAR:
                failures.append(f"SEALED_DATE_{field}")
        if not evaluation <= entry <= exit_126:
            failures.append("INVALID_SESSION_ORDER")
    except (KeyError, ValueError):
        failures.append("INVALID_REQUIRED_DATE")
    try:
        entry_open = _parse_float(row["entryOpen"], field="entryOpen")
        if entry_open <= 0.0:
            failures.append("NONPOSITIVE_ENTRY_OPEN")
    except (KeyError, ValueError):
        failures.append("INVALID_ENTRY_OPEN")
    for field in ("raw_126", "excess_126"):
        try:
            _parse_float(row[field], field=field)
        except (KeyError, ValueError):
            failures.append(f"INVALID_{field.upper()}")
    return sorted(set(failures))


def _global_tail(mature: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    ordered = sorted(mature, key=_tail_sort_key)
    top_count = math.floor(len(ordered) * TOP_FRACTION)
    if top_count <= 0:
        raise ValueError("top-1% audit set is empty")
    top = ordered[:top_count]
    full_sum = sum(_excess(row) for row in mature)
    top_sum = sum(_excess(row) for row in top)
    issuer_counts = Counter(str(row["issuerCik"]).strip() for row in top)
    ticker_counts = Counter(str(row["ticker"]).strip() for row in top)
    year_counts = Counter(
        _date_year(row["evaluationSession"], field="evaluationSession") for row in top
    )
    top_ten = [_audit_row(row) for row in top[:10]]
    result = {
        "count": top_count,
        "signedExcessSum": top_sum,
        "fullCohortSignedExcessSum": full_sum,
        "signedExcessShare": top_sum / full_sum if full_sum != 0.0 else None,
        "uniqueIssuers": len(issuer_counts),
        "uniqueTickers": len(ticker_counts),
        "maxIssuerRepeats": max(issuer_counts.values()),
        "maxTickerRepeats": max(ticker_counts.values()),
        "yearCounts": {str(year): year_counts[year] for year in sorted(year_counts)},
        "shareFrom2020": year_counts.get(2020, 0) / top_count,
        "topIssuer": _most_common(issuer_counts),
        "topTicker": _most_common(ticker_counts),
        "topTen": top_ten,
    }
    return result, top


def _year_rows(
    mature: list[dict[str, str]],
) -> dict[int, list[dict[str, str]]]:
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in mature:
        year = _date_year(row["evaluationSession"], field="evaluationSession")
        grouped[year].append(row)
    expected = set(range(DEVELOPMENT_START_YEAR, DEVELOPMENT_END_YEAR + 1))
    if set(grouped) != expected:
        raise ValueError("mature primary outcomes do not cover every development year")
    return grouped


def _within_year(grouped: dict[int, list[dict[str, str]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for year in sorted(grouped):
        values = [_excess(row) for row in grouped[year]]
        ordered = sorted(values, reverse=True)
        cut = math.floor(len(values) * TOP_FRACTION)
        signed_sum = sum(values)
        top_five = sum(ordered[:5])
        result[str(year)] = {
            **_summary_stats(values),
            "top1PctRemovedCount": cut,
            "top1PctRemovedMean": _top_removed_mean(values, TOP_FRACTION),
            "trimmedMean1PctEachTail": _trimmed_mean(values, TOP_FRACTION),
            "largestExcess126": ordered[0],
            "topFiveSignedExcessShare": (
                top_five / signed_sum if signed_sum != 0.0 else None
            ),
        }
    return result


def _attribution_2020(
    mature: list[dict[str, str]],
    grouped: dict[int, list[dict[str, str]]],
    top: list[dict[str, str]],
) -> dict[str, Any]:
    rows_2020 = grouped[2020]
    values_2020 = [_excess(row) for row in rows_2020]
    signed_2020 = sum(values_2020)
    top_2020_sum = sum(
        _excess(row)
        for row in top
        if _date_year(row["evaluationSession"], field="evaluationSession") == 2020
    )
    non_2020 = [
        _excess(row)
        for row in mature
        if _date_year(row["evaluationSession"], field="evaluationSession") != 2020
    ]
    return {
        **_summary_stats(values_2020),
        "signedExcessSum": signed_2020,
        "top1PctRemovedCount": math.floor(len(values_2020) * TOP_FRACTION),
        "top1PctRemovedMean": _top_removed_mean(values_2020, TOP_FRACTION),
        "trimmedMean1PctEachTail": _trimmed_mean(values_2020, TOP_FRACTION),
        "globalTopSetSignedExcessSum": top_2020_sum,
        "globalTopSetShareOf2020SignedExcess": (
            top_2020_sum / signed_2020 if signed_2020 != 0.0 else None
        ),
        "fullCohortExcluding2020": _summary_stats(non_2020),
    }


def _sanity(top: list[dict[str, str]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, row in enumerate(top, start=1):
        reasons = _sanity_failures(row)
        if reasons:
            failures.append(
                {
                    "rank": index,
                    "issuerCik": str(row.get("issuerCik") or "").strip(),
                    "ticker": str(row.get("ticker") or "").strip(),
                    "reasons": reasons,
                }
            )
    return {
        "checked": len(top),
        "failureCount": len(failures),
        "anyFailure": bool(failures),
        "failures": failures,
    }


def run(
    *,
    events_path: Path,
    source_summary_path: Path,
    output_path: Path,
    source_run_id: str,
) -> dict[str, Any]:
    summary_bytes = source_summary_path.read_bytes()
    summary = json.loads(summary_bytes)
    _validate_source_summary(summary)
    rows = _load_rows(events_path)
    _validate_global_boundaries(rows)
    mature = _mature_rows(rows)
    reproduction = _canonical_reproduction(mature, summary)
    global_tail, top = _global_tail(mature)
    if len(mature) == 5944 and global_tail["count"] != 59:
        raise ValueError("frozen canonical top-1% count must be 59")
    grouped = _year_rows(mature)
    result = {
        "schemaVersion": 1,
        "status": STATUS,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "source": {
            "runId": str(source_run_id),
            "eventsFile": events_path.name,
            "summaryFile": source_summary_path.name,
            "summarySha256": hashlib.sha256(summary_bytes).hexdigest(),
        },
        "canonicalReproduction": reproduction,
        "globalTop1Pct": global_tail,
        "attribution2020": _attribution_2020(mature, grouped, top),
        "withinYearTailSensitivity": _within_year(grouped),
        "topSetSanity": _sanity(top),
        "interpretation": (
            "Development-only attribution audit. The output cannot create an ex-post "
            "filter, open OOS, change production scoring, or support a formal alpha claim."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-run-id", required=True)
    args = parser.parse_args()
    run(
        events_path=args.events,
        source_summary_path=args.source_summary,
        output_path=args.output,
        source_run_id=args.source_run_id,
    )


if __name__ == "__main__":
    main()
