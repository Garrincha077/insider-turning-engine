"""Apply the frozen B1 dependence/tail gate to continuity-corrected outcomes.

This runner intentionally reuses the already frozen diagnostic arithmetic and warning
thresholds from ``research_phase1_b1_robustness.py``. It consumes only the persisted
continuity-corrected B1 event-horizon artifact, keeps 2023+ sealed, and does not open
the deferred daily-path calendar-time/HAC stage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_b1_robustness as base

HORIZONS = base.HORIZONS
PRIMARY_HORIZON = base.PRIMARY_HORIZON
DEVELOPMENT_START_YEAR = base.DEVELOPMENT_START_YEAR
DEVELOPMENT_END_YEAR = base.DEVELOPMENT_END_YEAR
SEALED_YEAR = base.SEALED_YEAR
STATUS = "PHASE1_B1_CONTINUITY_CORRECTED_ROBUSTNESS_COMPLETE"
SOURCE_STATUS = "PHASE1_B1_CONTINUITY_CORRECTED_PERFORMANCE_COMPLETE"


def _date_year(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text[:4])
    except ValueError as exc:
        raise ValueError(f"invalid date-like value: {text}") from exc


def _validate_source_summary(summary: dict[str, Any]) -> None:
    if summary.get("status") != SOURCE_STATUS:
        raise ValueError("unexpected corrected B1 source status")
    if summary.get("resultClass") != "research/descriptive":
        raise ValueError("corrected source is not research/descriptive")
    if summary.get("primaryHorizonSessions") != PRIMARY_HORIZON:
        raise ValueError("unexpected corrected B1 primary horizon")
    if summary.get("horizonsSessions") != list(HORIZONS):
        raise ValueError("unexpected corrected B1 horizons")
    if summary.get("period") != "2016-2020 XNYS evaluation-session cohort":
        raise ValueError("unexpected corrected B1 development period")
    if summary.get("outcomeMarketBoundary") != "2016-2022 only":
        raise ValueError("unexpected corrected B1 outcome boundary")
    if summary.get("researchOnly") is not True:
        raise ValueError("corrected source is not research-only")
    if summary.get("oosOpened") is not False:
        raise ValueError("corrected source indicates OOS was opened")
    if summary.get("productionScoringChanged") is not False:
        raise ValueError("corrected source indicates production scoring changed")
    if summary.get("formalAlphaClaimed") is not False:
        raise ValueError("corrected source unexpectedly claims formal alpha")
    continuity = summary.get("continuityGate") or {}
    if continuity.get("unresolvedEventHorizonRows") != 0:
        raise ValueError("corrected source is not downstream of zero-unresolved gate")


def _validate_row(row: dict[str, str]) -> int:
    evaluation_year = _date_year(row.get("evaluationSession"))
    if evaluation_year is None or not (
        DEVELOPMENT_START_YEAR <= evaluation_year <= DEVELOPMENT_END_YEAR
    ):
        raise ValueError("evaluationSession outside frozen development cohort")
    for field in ("evaluationSession", "entrySession", "targetExitSession"):
        year = _date_year(row.get(field))
        if year is not None and year >= SEALED_YEAR:
            raise ValueError(f"sealed OOS boundary violated by {field}")
    horizon = int(str(row.get("horizon") or "0"))
    if horizon not in HORIZONS:
        raise ValueError(f"unexpected horizon: {horizon}")
    return horizon


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
            "correctedExcess",
            "valuationStatus",
        }
        if not required.issubset(reader.fieldnames or []):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"corrected event-horizon file missing fields: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("corrected event-horizon file is empty")

    seen: set[tuple[str, int]] = set()
    event_horizons: dict[str, set[int]] = {}
    for row in rows:
        horizon = _validate_row(row)
        event = str(row["eventNumber"]).strip()
        if not event:
            raise ValueError("missing eventNumber")
        key = (event, horizon)
        if key in seen:
            raise ValueError(f"duplicate corrected event-horizon row: {key}")
        seen.add(key)
        event_horizons.setdefault(event, set()).add(horizon)
        value = base._parse_float(row.get("correctedExcess"))
        if value is not None and row.get("valuationStatus") != "VALUED":
            raise ValueError("non-valued corrected row contains corrected excess")
    expected = set(HORIZONS)
    incomplete = [event for event, horizons in event_horizons.items() if horizons != expected]
    if incomplete:
        raise ValueError("corrected source does not contain the frozen four horizons per event")
    return rows


def _rows_for_horizon(rows: list[dict[str, str]], horizon: int) -> list[dict[str, str]]:
    return [row for row in rows if int(row["horizon"]) == horizon]


def _values(rows: list[dict[str, str]], horizon: int) -> list[float]:
    values: list[float] = []
    for row in _rows_for_horizon(rows, horizon):
        value = base._parse_float(row.get("correctedExcess"))
        if value is not None:
            values.append(value)
    return values


def _corrected_expected(summary: dict[str, Any], horizon: int) -> dict[str, Any]:
    try:
        return summary["horizons"][str(horizon)]["B1ContinuityCorrected"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"corrected source summary missing horizon {horizon}") from exc


def _reproduction(rows: list[dict[str, str]], summary: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for horizon in HORIZONS:
        values = _values(rows, horizon)
        expected = _corrected_expected(summary, horizon)
        actual = {
            "maturedOutcomeCount": len(values),
            "spyExcessMean": base._mean(values),
            "spyExcessMedian": base._median(values),
            "spyExcessWinRate": base._win_rate(values),
        }
        if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
            raise ValueError(f"corrected count mismatch at horizon {horizon}")
        for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
            left = actual[key]
            right = expected[key]
            if left is None or right is None or not math.isclose(
                float(left), float(right), rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError(f"corrected {key} mismatch at horizon {horizon}")
        checks[str(horizon)] = actual
    return checks


def _primary_wide_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
    for row in _rows_for_horizon(rows, PRIMARY_HORIZON):
        converted.append(
            {
                "issuerCik": str(row.get("issuerCik") or ""),
                "entrySession": str(row.get("entrySession") or ""),
                "evaluationSession": str(row.get("evaluationSession") or ""),
                f"excess_{PRIMARY_HORIZON}": str(row.get("correctedExcess") or ""),
            }
        )
    return converted


def _valuation_coverage(rows: list[dict[str, str]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("valuationStatus") or "") for row in rows)
    return {
        "eventHorizonRows": len(rows),
        "events": len({str(row["eventNumber"]) for row in rows}),
        "valuationStatuses": dict(sorted(statuses.items())),
        "valuedRows": statuses.get("VALUED", 0),
    }


def run(
    *,
    event_horizons_path: Path,
    source_summary_path: Path,
    output_path: Path,
    source_run_id: str,
    source_artifact: str,
    source_artifact_digest: str,
) -> dict[str, Any]:
    summary_bytes = source_summary_path.read_bytes()
    source_summary = json.loads(summary_bytes)
    _validate_source_summary(source_summary)
    rows = _load_rows(event_horizons_path)
    reproduction = _reproduction(rows, source_summary)

    tails = {str(h): base._tail_diagnostics(_values(rows, h)) for h in HORIZONS}
    primary_rows = _primary_wide_rows(rows)
    issuer = base._group_diagnostics(primary_rows, "issuerCik")
    session = base._group_diagnostics(primary_rows, "entrySession")
    yearly = base._year_diagnostics(primary_rows)
    warnings = base._warnings(tails[str(PRIMARY_HORIZON)], issuer, session, yearly)
    blocked = any(warnings.values())

    result: dict[str, Any] = {
        "schemaVersion": 1,
        "status": STATUS,
        "resultClass": "research/descriptive",
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "calendarTimeHacStageOpened": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "horizonsSessions": list(HORIZONS),
        "source": {
            "runId": str(source_run_id),
            "artifact": source_artifact,
            "artifactDigest": source_artifact_digest,
            "summarySha256": hashlib.sha256(summary_bytes).hexdigest(),
            "eventHorizonsSha256": hashlib.sha256(event_horizons_path.read_bytes()).hexdigest(),
            "status": source_summary["status"],
            "period": source_summary["period"],
            "outcomeMarketBoundary": source_summary["outcomeMarketBoundary"],
            "continuityUnresolvedRows": source_summary["continuityGate"][
                "unresolvedEventHorizonRows"
            ],
        },
        "scope": _valuation_coverage(rows),
        "correctedReproduction": reproduction,
        "tailDiagnostics": tails,
        "issuerDependence": issuer,
        "entrySessionDependence": session,
        "yearStability": yearly,
        "warningConditions": warnings,
        "blockingWarningPresent": blocked,
        "progression": (
            "BLOCK_HAC_AND_OOS" if blocked else "MAY_FREEZE_SEPARATE_DAILY_PATH_HAC_DESIGN"
        ),
        "interpretation": (
            "Continuity-corrected development-only dependence/tail diagnostics using the "
            "unchanged warning semantics frozen before the canonical robustness run. No formal "
            "alpha claim and no OOS opening. The daily-path calendar-time/HAC stage remains closed "
            "unless this warning gate is clean and a separate design is frozen before execution."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-horizons", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--source-artifact", required=True)
    parser.add_argument("--source-artifact-digest", required=True)
    args = parser.parse_args()
    result = run(
        event_horizons_path=args.event_horizons,
        source_summary_path=args.source_summary,
        output_path=args.output,
        source_run_id=args.source_run_id,
        source_artifact=args.source_artifact,
        source_artifact_digest=args.source_artifact_digest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
