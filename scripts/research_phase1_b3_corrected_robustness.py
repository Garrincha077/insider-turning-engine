"""Frozen robustness diagnostics for continuity-corrected B3 development."""

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
STATUS = "PHASE1_B3_CONTINUITY_CORRECTED_ROBUSTNESS_COMPLETE"
SOURCE_STATUS = "PHASE1_B3_CONTINUITY_CORRECTED_DEVELOPMENT_COMPLETE"


def _validate_source_summary(summary: dict[str, Any]) -> None:
    required = {
        "status": SOURCE_STATUS,
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "horizonsSessions": list(HORIZONS),
        "continuityCorrectionComplete": True,
        "maeRecomputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
        "definitionId": "B3_CONTINUITY_CORRECTED_DEVELOPMENT_V1",
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"corrected B3 source mismatch: {key}")
    if summary.get("coverageTier") not in {
        "A_HIGH_CONFIDENCE",
        "B_RESEARCH_GRADE",
        "C_EXPLORATORY",
    }:
        raise ValueError("corrected B3 source lacks frozen coverage tier")


def _reproduction(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
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
            raise ValueError(f"corrected B3 count mismatch at horizon {horizon}")
        for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
            if not math.isclose(
                float(actual[key]),
                float(expected[key]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"corrected B3 {key} mismatch at horizon {horizon}"
                )
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
        "sourceStatus": SOURCE_STATUS,
        "resultClass": "research/descriptive",
        "researchOnly": True,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "calendarTimeHacStageOpened": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "continuityCorrectionComplete": True,
        "robustnessSemanticsChanged": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "horizonsSessions": list(HORIZONS),
        "source": {
            "runId": str(source_run_id),
            "release": source_release,
            "asset": source_asset,
            "assetDigest": source_asset_digest,
            "summarySha256": hashlib.sha256(summary_bytes).hexdigest(),
            "eventsSha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
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
            "Continuity-corrected B3 development-only robustness using the "
            "already-frozen B1/B3 warning semantics unchanged. No formal "
            "alpha claim, validation opening, HAC opening or OOS opening."
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
    result = run(
        events_path=args.events,
        source_summary_path=args.source_summary,
        output_path=args.output,
        source_run_id=args.source_run_id,
        source_release=args.source_release,
        source_asset=args.source_asset,
        source_asset_digest=args.source_asset_digest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
