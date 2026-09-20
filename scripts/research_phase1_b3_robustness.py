"""B3 development-only dependence and tail robustness diagnostics.

This runner applies the already-frozen Phase-1 B1 diagnostic arithmetic and
warning thresholds unchanged to the persisted B3 development outcome series.
It does not modify B3 selection, open validation/OOS, or claim formal alpha.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import research_phase1_b1_robustness as base

HORIZONS = base.HORIZONS
PRIMARY_HORIZON = base.PRIMARY_HORIZON
STATUS = "PHASE1_B3_ROBUSTNESS_DIAGNOSTICS_COMPLETE"
SOURCE_STATUS = "PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE"


def _validate_source_summary(summary: dict[str, Any]) -> None:
    if summary.get("status") != SOURCE_STATUS:
        raise ValueError("unexpected B3 source status")
    if summary.get("benchmark") != "B3_COMPANY_NET_BUYING_V1":
        raise ValueError("unexpected B3 benchmark")
    if summary.get("resultClass") != "research/descriptive":
        raise ValueError("B3 source is not research/descriptive")
    if summary.get("formalAlphaClaimed") is not False:
        raise ValueError("B3 source unexpectedly claims formal alpha")
    if summary.get("period") != "2016-2020 XNYS evaluation-session cohort":
        raise ValueError("unexpected B3 development period")
    if summary.get("outcomeMarketBoundary") != "2016-2022 only":
        raise ValueError("unexpected B3 outcome boundary")
    if summary.get("primaryHorizonSessions") != PRIMARY_HORIZON:
        raise ValueError("unexpected B3 primary horizon")
    if summary.get("horizonsSessions") != list(HORIZONS):
        raise ValueError("unexpected B3 horizon family")
    if summary.get("coverageTier") not in {
        "A_HIGH_CONFIDENCE",
        "B_RESEARCH_GRADE",
        "C_EXPLORATORY",
    }:
        raise ValueError("B3 source did not pass frozen minimum coverage tier")
    if summary.get("validationPerformanceComputed") is not False:
        raise ValueError("B3 validation performance was opened")
    if summary.get("oosOpened") is not False:
        raise ValueError("B3 source indicates OOS was opened")
    if summary.get("productionScoringChanged") is not False:
        raise ValueError("B3 source indicates production scoring changed")
    if summary.get("b3DefinitionChanged") is not False:
        raise ValueError("B3 definition changed in source")
    if summary.get("eventConstructionChanged") is not False:
        raise ValueError("B3 event construction changed in source")
    if summary.get("identityDefinitionChanged") is not False:
        raise ValueError("B3 identity definition changed in source")


def _reproduction(
    rows: list[dict[str, str]], summary: dict[str, Any]
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for horizon in HORIZONS:
        values = base._horizon_values(rows, horizon)
        expected = summary["horizons"][str(horizon)]
        actual = {
            "maturedOutcomeCount": len(values),
            "spyExcessMean": base._mean(values),
            "spyExcessMedian": base._median(values),
            "spyExcessWinRate": base._win_rate(values),
        }
        if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
            raise ValueError(f"B3 matured count mismatch at horizon {horizon}")
        for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
            if not math.isclose(
                float(actual[key]),
                float(expected[key]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(f"B3 {key} mismatch at horizon {horizon}")
        checks[str(horizon)] = actual
    return checks


def run(
    *,
    events_path: Path,
    source_summary_path: Path,
    output_path: Path,
    source_run_id: str,
    source_release: str,
    source_asset: str,
    source_asset_digest: str,
) -> dict[str, Any]:
    summary_bytes = source_summary_path.read_bytes()
    summary = json.loads(summary_bytes)
    _validate_source_summary(summary)

    rows = base._load_events(events_path)
    reproduction = _reproduction(rows, summary)

    tails = {
        str(horizon): base._tail_diagnostics(
            base._horizon_values(rows, horizon)
        )
        for horizon in HORIZONS
    }
    issuer = base._group_diagnostics(rows, "issuerCik")
    session = base._group_diagnostics(rows, "entrySession")
    yearly = base._year_diagnostics(rows)
    warnings = base._warnings(
        tails[str(PRIMARY_HORIZON)],
        issuer,
        session,
        yearly,
    )
    blocked = any(warnings.values())

    result: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": STATUS,
        "resultClass": "research/descriptive",
        "researchOnly": True,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "calendarTimeHacStageOpened": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "horizonsSessions": list(HORIZONS),
        "source": {
            "runId": str(source_run_id),
            "release": source_release,
            "asset": source_asset,
            "assetDigest": source_asset_digest,
            "summarySha256": hashlib.sha256(summary_bytes).hexdigest(),
            "eventsSha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
            "status": summary["status"],
            "coverageTier": summary["coverageTier"],
            "period": summary["period"],
            "outcomeMarketBoundary": summary["outcomeMarketBoundary"],
        },
        "canonicalReproduction": reproduction,
        "tailDiagnostics": tails,
        "issuerDependence": issuer,
        "entrySessionDependence": session,
        "yearStability": yearly,
        "warningConditions": warnings,
        "blockingWarningPresent": blocked,
        "progression": (
            "BLOCK_HAC_AND_OOS"
            if blocked
            else "MAY_FREEZE_SEPARATE_DAILY_PATH_HAC_DESIGN"
        ),
        "interpretation": (
            "Development-only B3 dependence and tail diagnostics using the exact "
            "warning semantics already frozen for Phase-1 B1. No feature tuning, "
            "formal alpha claim, validation opening or OOS opening. A clean "
            "warning set would only permit a separately frozen daily-path "
            "calendar-time/HAC design."
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
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--source-asset", required=True)
    parser.add_argument("--source-asset-digest", required=True)
    args = parser.parse_args()

    print(
        json.dumps(
            run(
                events_path=args.events,
                source_summary_path=args.source_summary,
                output_path=args.output,
                source_run_id=args.source_run_id,
                source_release=args.source_release,
                source_asset=args.source_asset,
                source_asset_digest=args.source_asset_digest,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
