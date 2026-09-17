"""Frozen development-only temporal clustering diagnostic for corrected Phase-1 B1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import research_phase1_b1_corrected_robustness as corrected_robustness
import research_phase1_b1_corrected_tail_attribution as corrected_tail
import research_phase1_b1_robustness as robustness
import research_phase1_b1_tail_attribution as tail_base

PRIMARY_HORIZON = 126
STATUS = "PHASE1_B1_CONTINUITY_CORRECTED_TEMPORAL_CLUSTERING_COMPLETE"
YEARS = tuple(range(2016, 2021))


def _bucket_key(value: str, granularity: str) -> str:
    parsed = date.fromisoformat(str(value).strip())
    if parsed.year >= 2023:
        raise ValueError("sealed OOS boundary violated by bucket date")
    if granularity == "month":
        return f"{parsed.year:04d}-{parsed.month:02d}"
    if granularity == "quarter":
        quarter = ((parsed.month - 1) // 3) + 1
        return f"{parsed.year:04d}-Q{quarter}"
    raise ValueError(f"unsupported granularity: {granularity}")


def _summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": robustness._mean(values),
        "median": robustness._median(values),
        "winRate": robustness._win_rate(values),
        "signedExcessSum": sum(values),
    }


def _bucket_rows(rows: list[dict[str, str]], granularity: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_bucket_key(row["evaluationSession"], granularity)].append(row)

    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        values = [tail_base._excess(row) for row in bucket]
        issuers = Counter(str(row["issuerCik"]).strip() for row in bucket)
        if "" in issuers:
            raise ValueError("missing issuer in temporal bucket")
        item = {
            "bucket": key,
            **_summary(values),
            "positiveExcessSum": sum(value for value in values if value > 0.0),
            "uniqueIssuers": len(issuers),
            "largestIssuerEventCount": max(issuers.values()),
        }
        output.append(item)
    return output


def _top_share(items: list[float], denominator: float, count: int = 5) -> float | None:
    if denominator == 0.0:
        return None
    return sum(sorted(items, reverse=True)[:count]) / denominator


def _longest_run(flags: list[bool]) -> int:
    best = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _bucket_diagnostics(rows: list[dict[str, str]], granularity: str) -> dict[str, Any]:
    buckets = _bucket_rows(rows, granularity)
    if not buckets:
        raise ValueError("temporal bucket set is empty")

    total_events = sum(int(item["count"]) for item in buckets)
    full_signed = sum(float(item["signedExcessSum"]) for item in buckets)
    full_positive = sum(float(item["positiveExcessSum"]) for item in buckets)
    counts = [int(item["count"]) for item in buckets]
    count_shares = [count / total_events for count in counts]
    means = [float(item["mean"]) for item in buckets]
    medians = [float(item["median"]) for item in buckets]
    wins = [float(item["winRate"]) for item in buckets]

    busiest = sorted(buckets, key=lambda item: (-int(item["count"]), str(item["bucket"])))[:5]
    signed_best = sorted(
        buckets,
        key=lambda item: (-float(item["signedExcessSum"]), str(item["bucket"])),
    )[:5]
    positive_best = sorted(
        buckets,
        key=lambda item: (-float(item["positiveExcessSum"]), str(item["bucket"])),
    )[:5]

    positive_mean_flags = [value > 0.0 for value in means]
    non_positive_mean_flags = [value <= 0.0 for value in means]
    return {
        "granularity": granularity,
        "buckets": buckets,
        "concentration": {
            "nonEmptyBuckets": len(buckets),
            "fiveBusiestBuckets": [item["bucket"] for item in busiest],
            "fiveBusiestEventShare": sum(int(item["count"]) for item in busiest) / total_events,
            "fiveHighestSignedExcessBuckets": [item["bucket"] for item in signed_best],
            "fiveHighestSignedExcessShareOfFullSigned": _top_share(
                [float(item["signedExcessSum"]) for item in buckets], full_signed
            ),
            "fiveHighestPositiveExcessBuckets": [item["bucket"] for item in positive_best],
            "fiveHighestPositiveExcessShareOfFullPositive": _top_share(
                [float(item["positiveExcessSum"]) for item in buckets], full_positive
            ),
            "maxBucketEventCount": max(counts),
            "maxBucketEventShare": max(counts) / total_events,
            "eventCountHhi": sum(share * share for share in count_shares),
        },
        "stability": {
            "positiveMeanBuckets": sum(positive_mean_flags),
            "positiveMeanBucketShare": sum(positive_mean_flags) / len(buckets),
            "positiveMedianBuckets": sum(value > 0.0 for value in medians),
            "positiveMedianBucketShare": sum(value > 0.0 for value in medians) / len(buckets),
            "winRateAboveHalfBuckets": sum(value > 0.5 for value in wins),
            "winRateAboveHalfBucketShare": sum(value > 0.5 for value in wins) / len(buckets),
            "longestPositiveMeanRun": _longest_run(positive_mean_flags),
            "longestNonPositiveMeanRun": _longest_run(non_positive_mean_flags),
        },
    }


def _leave_one_year_out(rows: list[dict[str, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for year in YEARS:
        kept = [row for row in rows if int(row["evaluationSession"][:4]) != year]
        values = [tail_base._excess(row) for row in kept]
        result[str(year)] = _summary(values)
    return result


def _entry_session_reproduction(rows: list[dict[str, str]]) -> dict[str, Any]:
    wide = [
        {
            "entrySession": row["entrySession"],
            f"excess_{PRIMARY_HORIZON}": row["excess_126"],
        }
        for row in rows
    ]
    diagnostics = robustness._group_diagnostics(wide, "entrySession")
    return {
        "uniqueEntrySessions": diagnostics["groupCount"],
        **diagnostics["eventCountConcentration"],
    }


def _corrected_reproduction(
    rows: list[dict[str, str]], source_summary: dict[str, Any]
) -> dict[str, Any]:
    values = [tail_base._excess(row) for row in rows]
    expected = source_summary["horizons"][str(PRIMARY_HORIZON)]["B1ContinuityCorrected"]
    actual = {
        "maturedOutcomeCount": len(values),
        "spyExcessMean": robustness._mean(values),
        "spyExcessMedian": robustness._median(values),
        "spyExcessWinRate": robustness._win_rate(values),
    }
    if actual["maturedOutcomeCount"] != expected["maturedOutcomeCount"]:
        raise ValueError("corrected primary mature count mismatch")
    for key in ("spyExcessMean", "spyExcessMedian", "spyExcessWinRate"):
        if not math.isclose(
            float(actual[key]), float(expected[key]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(f"corrected primary {key} mismatch")
    return actual


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
    tail_base._validate_source_summary(canonical_summary)
    canonical_rows = tail_base._load_rows(canonical_events_path)
    tail_base._validate_global_boundaries(canonical_rows)

    joined = corrected_tail._join_corrected_to_canonical(corrected_rows, canonical_rows)
    tail_base._validate_global_boundaries(joined)
    mature = tail_base._mature_rows(joined)
    reproduction = _corrected_reproduction(mature, corrected_summary)

    result: dict[str, Any] = {
        "schemaVersion": 1,
        "status": STATUS,
        "resultClass": "research/descriptive",
        "diagnosticOnly": True,
        "newFilterCreated": False,
        "researchOnly": True,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "oosOpened": False,
        "calendarTimeHacStageOpened": False,
        "productionScoringChanged": False,
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
        "scope": {
            "canonicalB1Events": len(canonical_rows),
            "correctedPrimaryRows": len(joined),
            "correctedMaturePrimaryRows": len(mature),
        },
        "correctedPrimaryReproduction": reproduction,
        "monthly": _bucket_diagnostics(mature, "month"),
        "quarterly": _bucket_diagnostics(mature, "quarter"),
        "leaveOneYearOut": _leave_one_year_out(mature),
        "entrySessionClusteringReproduction": _entry_session_reproduction(mature),
        "interpretation": (
            "Development-only temporal clustering and regime attribution. This is not a daily "
            "calendar-time portfolio and does not perform HAC inference. It cannot clear the "
            "existing robustness warning gate, create an exclusion rule, or open 2023+ OOS."
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
    print(
        json.dumps(
            run(
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
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
