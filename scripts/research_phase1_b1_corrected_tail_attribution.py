"""Development-only attribution of the continuity-corrected B1 126-session tail."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import research_phase1_b1_corrected_robustness as corrected_robustness
import research_phase1_b1_tail_attribution as base

PRIMARY_HORIZON = 126
STATUS = "PHASE1_B1_CONTINUITY_CORRECTED_TAIL_ATTRIBUTION_COMPLETE"


def _corrected_expected(summary: dict[str, Any]) -> dict[str, Any]:
    try:
        return summary["horizons"][str(PRIMARY_HORIZON)]["B1ContinuityCorrected"]
    except (KeyError, TypeError) as exc:
        raise ValueError("corrected source summary missing primary horizon") from exc


def _join_corrected_to_canonical(
    corrected_rows: list[dict[str, str]],
    canonical_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    primary = [row for row in corrected_rows if int(row["horizon"]) == PRIMARY_HORIZON]
    if len(primary) != len(canonical_rows):
        raise ValueError("corrected primary rows do not match frozen canonical B1 event count")

    joined: list[dict[str, str]] = []
    seen_events: set[int] = set()
    for corrected in primary:
        event_number = int(corrected["eventNumber"])
        if event_number in seen_events:
            raise ValueError("duplicate corrected primary eventNumber")
        seen_events.add(event_number)
        if event_number < 1 or event_number > len(canonical_rows):
            raise ValueError("corrected eventNumber outside frozen canonical B1 order")
        canonical = canonical_rows[event_number - 1]

        comparisons = {
            "issuerCik": (corrected["issuerCik"], canonical["issuerCik"]),
            "ticker": (corrected["ticker"], canonical["ticker"]),
            "evaluationSession": (
                corrected["evaluationSession"],
                canonical["evaluationSession"],
            ),
            "entrySession": (corrected["entrySession"], canonical["entrySession"]),
            "targetExitSession": (corrected["targetExitSession"], canonical["exit_126"]),
        }
        mismatches = [
            field
            for field, (left, right) in comparisons.items()
            if str(left).strip() != str(right).strip()
        ]
        if mismatches:
            raise ValueError(
                f"corrected/canonical identity-date mismatch at event {event_number}: {mismatches}"
            )

        corrected_excess = str(corrected.get("correctedExcess") or "").strip()
        corrected_raw = str(corrected.get("correctedRaw") or "").strip()
        status = str(corrected.get("valuationStatus") or "").strip()
        if corrected_excess:
            if status != "VALUED":
                raise ValueError("corrected mature row is not VALUED")
            if not corrected_raw:
                raise ValueError("corrected mature row missing correctedRaw")

        joined.append(
            {
                "eventNumber": str(event_number),
                "issuerCik": str(canonical["issuerCik"]).strip(),
                "ticker": str(canonical["ticker"]).strip(),
                "knowledgeAtFirst": str(canonical["knowledgeAtFirst"]).strip(),
                "evaluationSession": str(canonical["evaluationSession"]).strip(),
                "entrySession": str(canonical["entrySession"]).strip(),
                "entryOpen": str(corrected["entryOpen"]).strip(),
                "opportunisticOwnerCount": str(canonical["opportunisticOwnerCount"]).strip(),
                "rawOpportunisticPurchaseRows": str(
                    canonical["rawOpportunisticPurchaseRows"]
                ).strip(),
                "exit_126": str(corrected["targetExitSession"]).strip(),
                "raw_126": corrected_raw,
                "excess_126": corrected_excess,
                "valuationStatus": status,
                "continuityState": str(corrected.get("continuityState") or "").strip(),
                "valuationKind": str(corrected.get("valuationKind") or "").strip(),
            }
        )
    if seen_events != set(range(1, len(canonical_rows) + 1)):
        raise ValueError(
            "corrected primary eventNumber set diverges from frozen canonical B1 order"
        )
    return joined


def _corrected_reproduction(
    mature: list[dict[str, str]], summary: dict[str, Any]
) -> dict[str, Any]:
    values = [base._excess(row) for row in mature]
    expected = _corrected_expected(summary)
    actual = {
        "maturedOutcomeCount": len(values),
        "spyExcessMean": base._mean(values),
        "spyExcessMedian": base._median(values),
        "spyExcessWinRate": base._win_rate(values),
    }
    if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
        raise ValueError("corrected primary mature count mismatch")
    for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
        if not math.isclose(
            float(actual[key]), float(expected[key]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(f"corrected primary {key} mismatch")
    return actual


def _top_set_metadata(top: list[dict[str, str]]) -> dict[str, Any]:
    continuity: dict[str, int] = {}
    valuation_kinds: dict[str, int] = {}
    for row in top:
        state = str(row.get("continuityState") or "")
        kind = str(row.get("valuationKind") or "")
        continuity[state] = continuity.get(state, 0) + 1
        valuation_kinds[kind] = valuation_kinds.get(kind, 0) + 1
    return {
        "continuityStates": dict(sorted(continuity.items())),
        "valuationKinds": dict(sorted(valuation_kinds.items())),
    }


def run(
    *,
    corrected_event_horizons_path: Path,
    corrected_summary_path: Path,
    canonical_events_path: Path,
    canonical_summary_path: Path,
    output_path: Path,
    corrected_run_id: str,
    corrected_artifact: str,
    corrected_artifact_digest: str,
    canonical_run_id: str,
    canonical_artifact: str,
    canonical_artifact_digest: str,
) -> dict[str, Any]:
    corrected_summary_bytes = corrected_summary_path.read_bytes()
    corrected_summary = json.loads(corrected_summary_bytes)
    corrected_robustness._validate_source_summary(corrected_summary)
    corrected_rows = corrected_robustness._load_rows(corrected_event_horizons_path)

    canonical_summary_bytes = canonical_summary_path.read_bytes()
    canonical_summary = json.loads(canonical_summary_bytes)
    base._validate_source_summary(canonical_summary)
    canonical_rows = base._load_rows(canonical_events_path)
    base._validate_global_boundaries(canonical_rows)

    joined = _join_corrected_to_canonical(corrected_rows, canonical_rows)
    base._validate_global_boundaries(joined)
    mature = base._mature_rows(joined)
    reproduction = _corrected_reproduction(mature, corrected_summary)

    global_tail, top = base._global_tail(mature)
    grouped = base._year_rows(mature)
    within_year = base._within_year(grouped)
    attribution_2020 = base._attribution_2020(mature, grouped, top)
    sanity = base._sanity(top)

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
        "correctedSource": {
            "runId": str(corrected_run_id),
            "artifact": corrected_artifact,
            "artifactDigest": corrected_artifact_digest,
            "summarySha256": hashlib.sha256(corrected_summary_bytes).hexdigest(),
            "eventHorizonsSha256": hashlib.sha256(
                corrected_event_horizons_path.read_bytes()
            ).hexdigest(),
        },
        "canonicalMetadataSource": {
            "runId": str(canonical_run_id),
            "artifact": canonical_artifact,
            "artifactDigest": canonical_artifact_digest,
            "summarySha256": hashlib.sha256(canonical_summary_bytes).hexdigest(),
            "eventsSha256": hashlib.sha256(canonical_events_path.read_bytes()).hexdigest(),
        },
        "correctedPrimaryReproduction": reproduction,
        "scope": {
            "canonicalB1Events": len(canonical_rows),
            "correctedPrimaryRows": len(joined),
            "correctedMaturePrimaryRows": len(mature),
            "globalTop1PctCount": global_tail["count"],
        },
        "globalTop1Pct": global_tail,
        "globalTop1PctCorrectedValuationMetadata": _top_set_metadata(top),
        "attribution2020": attribution_2020,
        "withinYear": within_year,
        "sanity": sanity,
        "anyDeterministicSanityFailure": sanity["anyFailure"],
        "topTenValueBasis": "continuity-corrected holder raw return and SPY excess",
        "interpretation": (
            "Development-only residual tail/year attribution using the same audit semantics frozen "
            "before the canonical top-tail identities were inspected. No discovered identity, year "
            "or return magnitude is an exclusion rule. HAC/calendar-time and 2023+ OOS remain "
            "closed."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corrected-event-horizons", type=Path, required=True)
    parser.add_argument("--corrected-summary", type=Path, required=True)
    parser.add_argument("--canonical-events", type=Path, required=True)
    parser.add_argument("--canonical-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corrected-run-id", required=True)
    parser.add_argument("--corrected-artifact", required=True)
    parser.add_argument("--corrected-artifact-digest", required=True)
    parser.add_argument("--canonical-run-id", required=True)
    parser.add_argument("--canonical-artifact", required=True)
    parser.add_argument("--canonical-artifact-digest", required=True)
    args = parser.parse_args()
    result = run(
        corrected_event_horizons_path=args.corrected_event_horizons,
        corrected_summary_path=args.corrected_summary,
        canonical_events_path=args.canonical_events,
        canonical_summary_path=args.canonical_summary,
        output_path=args.output,
        corrected_run_id=args.corrected_run_id,
        corrected_artifact=args.corrected_artifact,
        corrected_artifact_digest=args.corrected_artifact_digest,
        canonical_run_id=args.canonical_run_id,
        canonical_artifact=args.canonical_artifact,
        canonical_artifact_digest=args.canonical_artifact_digest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
