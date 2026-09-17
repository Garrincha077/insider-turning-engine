"""Development-only dependence and tail diagnostics for canonical Phase-1 B1.

This runner consumes only the persisted canonical B1 event file and summary. It
never changes signal selection, never opens 2023+ OOS, and does not make a formal
alpha claim. The diagnostic contract is frozen in
``docs/research-phase1-b1-robustness-gate.md``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
DEVELOPMENT_START_YEAR = 2016
DEVELOPMENT_END_YEAR = 2020
SEALED_YEAR = 2023
STATUS = "PHASE1_B1_ROBUSTNESS_DIAGNOSTICS_COMPLETE"


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _win_rate(values: list[float]) -> float | None:
    return sum(value > 0.0 for value in values) / len(values) if values else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _trimmed_mean(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = math.floor(len(ordered) * fraction)
    kept = ordered[cut : len(ordered) - cut if cut else len(ordered)]
    return _mean(kept)


def _top_removed_mean(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = math.floor(len(ordered) * fraction)
    kept = ordered[: len(ordered) - cut] if cut else ordered
    return _mean(kept)


def _top_share(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values, reverse=True)
    count = max(1, math.ceil(len(ordered) * fraction))
    denominator = sum(ordered)
    if denominator == 0.0:
        return None
    return sum(ordered[:count]) / denominator


def _tail_diagnostics(values: list[float]) -> dict[str, Any]:
    positive = [value for value in values if value > 0.0]
    signed_sum = sum(values)
    top_ten = sorted(values, reverse=True)[:10]
    return {
        "count": len(values),
        "mean": _mean(values),
        "median": _median(values),
        "winRate": _win_rate(values),
        "trimmedMean1PctEachTail": _trimmed_mean(values, 0.01),
        "trimmedMean5PctEachTail": _trimmed_mean(values, 0.05),
        "top1PctRemovedMean": _top_removed_mean(values, 0.01),
        "top5PctRemovedMean": _top_removed_mean(values, 0.05),
        "quantiles": {
            "p01": _quantile(values, 0.01),
            "p05": _quantile(values, 0.05),
            "p95": _quantile(values, 0.95),
            "p99": _quantile(values, 0.99),
        },
        "positiveTailContribution": {
            "top1Pct": _top_share(positive, 0.01),
            "top5Pct": _top_share(positive, 0.05),
            "top10Pct": _top_share(positive, 0.10),
        },
        "topTenSignedExcessShare": (sum(top_ten) / signed_sum if signed_sum != 0.0 else None),
    }


def _parse_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("non-finite excess return")
    return number


def _date_year(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text[:4])
    except ValueError as exc:
        raise ValueError(f"invalid date-like value: {text}") from exc


def _validate_row_dates(row: dict[str, str]) -> None:
    date_fields = (
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "exit_21",
        "exit_63",
        "exit_126",
        "exit_252",
    )
    for field in date_fields:
        year = _date_year(row.get(field))
        if year is not None and year >= SEALED_YEAR:
            raise ValueError(f"sealed OOS boundary violated by {field}")
    evaluation_year = _date_year(row.get("evaluationSession"))
    in_development = (
        evaluation_year is not None
        and DEVELOPMENT_START_YEAR <= evaluation_year <= DEVELOPMENT_END_YEAR
    )
    if not in_development:
        raise ValueError("evaluationSession outside frozen development cohort")


def _load_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"issuerCik", "entrySession", *(f"excess_{h}" for h in HORIZONS)}
        if not required.issubset(reader.fieldnames or []):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"B1 events missing required fields: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("B1 events file is empty")
    for row in rows:
        _validate_row_dates(row)
    return rows


def _horizon_values(rows: Iterable[dict[str, str]], horizon: int) -> list[float]:
    values: list[float] = []
    field = f"excess_{horizon}"
    for row in rows:
        value = _parse_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def _canonical_reproduction(rows: list[dict[str, str]], summary: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for horizon in HORIZONS:
        values = _horizon_values(rows, horizon)
        expected = summary["horizons"][str(horizon)]
        actual = {
            "maturedOutcomeCount": len(values),
            "spyExcessMean": _mean(values),
            "spyExcessMedian": _median(values),
            "spyExcessWinRate": _win_rate(values),
        }
        if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
            raise ValueError(f"canonical count mismatch at horizon {horizon}")
        for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
            if not math.isclose(actual[key], expected[key], rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"canonical {key} mismatch at horizon {horizon}")
        checks[str(horizon)] = actual
    return checks


def _count_concentration(counts: list[int]) -> dict[str, Any]:
    total = sum(counts)
    ordered = sorted(counts, reverse=True)
    top_count = max(1, math.ceil(len(ordered) * 0.01))
    return {
        "groups": len(counts),
        "events": total,
        "maxEventsPerGroup": max(counts) if counts else 0,
        "p95EventsPerGroup": _quantile([float(v) for v in counts], 0.95),
        "p99EventsPerGroup": _quantile([float(v) for v in counts], 0.99),
        "top1PctGroupsEventShare": (sum(ordered[:top_count]) / total if total else None),
    }


def _group_diagnostics(rows: list[dict[str, str]], key_field: str) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = _parse_float(row.get(f"excess_{PRIMARY_HORIZON}"))
        if value is None:
            continue
        key = str(row.get(key_field) or "").strip()
        if not key:
            raise ValueError(f"missing {key_field} in mature B1 event")
        grouped[key].append(value)
    group_means = [statistics.fmean(group) for group in grouped.values()]
    counts = [len(group) for group in grouped.values()]
    return {
        "groupField": key_field,
        "groupCount": len(grouped),
        "equalWeightMean": _mean(group_means),
        "equalWeightMedian": _median(group_means),
        "equalWeightWinRate": _win_rate(group_means),
        "eventWeightedMean": _mean([value for group in grouped.values() for value in group]),
        "eventCountConcentration": _count_concentration(counts),
    }


def _year_diagnostics(rows: list[dict[str, str]]) -> dict[str, Any]:
    yearly: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        value = _parse_float(row.get(f"excess_{PRIMARY_HORIZON}"))
        if value is None:
            continue
        year = _date_year(row.get("evaluationSession"))
        if year is None:
            raise ValueError("missing evaluationSession in mature B1 event")
        yearly[year].append(value)
    expected_years = set(range(DEVELOPMENT_START_YEAR, DEVELOPMENT_END_YEAR + 1))
    if set(yearly) != expected_years:
        raise ValueError("mature B1 primary outcomes do not cover all frozen development years")
    detail = {
        str(year): {
            "count": len(yearly[year]),
            "mean": _mean(yearly[year]),
            "median": _median(yearly[year]),
            "winRate": _win_rate(yearly[year]),
        }
        for year in sorted(yearly)
    }
    means = [detail[str(year)]["mean"] for year in sorted(yearly)]
    return {
        "years": detail,
        "positiveMeanYears": sum(value > 0.0 for value in means),
        "positiveMedianYears": sum(detail[str(year)]["median"] > 0.0 for year in sorted(yearly)),
        "meanMaxMinusMin": max(means) - min(means),
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


def _warnings(
    tail_primary: dict[str, Any],
    issuer: dict[str, Any],
    session: dict[str, Any],
    yearly: dict[str, Any],
) -> dict[str, bool]:
    top1 = tail_primary["positiveTailContribution"]["top1Pct"]
    return {
        "issuerEqualWeightMeanNonPositive": issuer["equalWeightMean"] <= 0.0,
        "entrySessionEqualWeightMeanNonPositive": session["equalWeightMean"] <= 0.0,
        "top1PctRemovedMeanNonPositive": tail_primary["top1PctRemovedMean"] <= 0.0,
        "fewerThanThreePositiveMeanYears": yearly["positiveMeanYears"] < 3,
        "top1PctPositiveTailAtLeastHalf": top1 is not None and top1 >= 0.50,
    }


def run(
    *,
    events_path: Path,
    source_summary_path: Path,
    output_path: Path,
    source_run_id: str,
) -> dict[str, Any]:
    summary_text = source_summary_path.read_bytes()
    source_summary = json.loads(summary_text)
    _validate_source_summary(source_summary)
    rows = _load_events(events_path)
    reproduction = _canonical_reproduction(rows, source_summary)

    tails = {str(h): _tail_diagnostics(_horizon_values(rows, h)) for h in HORIZONS}
    issuer = _group_diagnostics(rows, "issuerCik")
    session = _group_diagnostics(rows, "entrySession")
    yearly = _year_diagnostics(rows)
    warnings = _warnings(tails[str(PRIMARY_HORIZON)], issuer, session, yearly)

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
            "summarySha256": hashlib.sha256(summary_text).hexdigest(),
            "canonicalStatus": source_summary["status"],
            "period": source_summary["period"],
            "outcomeMarketBoundary": source_summary["outcomeMarketBoundary"],
            "p0DataQualityTier": source_summary.get("p0DataQualityTier"),
        },
        "canonicalReproduction": reproduction,
        "tailDiagnostics": tails,
        "issuerDependence": issuer,
        "entrySessionDependence": session,
        "yearStability": yearly,
        "warningConditions": warnings,
        "blockingWarningPresent": any(warnings.values()),
        "interpretation": (
            "Development-only dependence/tail diagnostics. No formal alpha claim "
            "and no OOS opening. A clean warning set is necessary but not sufficient "
            "for progression to a separately frozen daily-path calendar-time/HAC "
            "inference design."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
