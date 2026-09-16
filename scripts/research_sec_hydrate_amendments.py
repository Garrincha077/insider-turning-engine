"""Research-only PIT hydration runner for transaction-bearing Forms 4/A and 5/A.

This reuses the audited daily-index + reporting-owner archive-fallback acquisition
path, but swaps in an amendment-only candidate loader.  It never enables scoring,
alerts, Pages, or OOS evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import research_sec_hydrate as base
import research_sec_hydrate_quarter as quarter
import research_sec_hydrate_with_fallback as fallback


def _load_amendment_candidates(path: Path, year: int, quarter_number: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            int(row["sourceYear"]) == year
            and int(row["sourceQuarter"]) == quarter_number
            and str(row["documentType"]).upper() in {"4/A", "5/A"}
            and int(row.get("transactionCount", 0)) > 0
        ):
            row["_filed"] = base._bulk_date(row["filingDate"])
            rows.append(row)
    rows.sort(key=lambda item: (item["_filed"], item["accession"]))
    return rows


def _validate(summary: dict[str, Any], expected_total: int) -> None:
    selected = int(summary["selectedOriginalBuyFilings"])
    discovered = int(summary.get("discoveredFilings", summary["matchedInDailyIndex"]))
    if selected <= 0:
        raise ValueError("empty amendment hydration shard")
    if int(summary["eligibleOriginalBuyFilingsInQuarter"]) != expected_total:
        raise ValueError("amendment shard eligible-quarter count disagrees with candidate universe")
    if discovered != selected:
        raise ValueError("amendment discovery is incomplete")
    if int(summary["hydratedAndParsedFilings"]) != selected:
        raise ValueError("amendment hydration/parser coverage is incomplete")
    if int(summary["failureCount"]) != 0:
        raise ValueError("amendment shard contains failures")
    if summary.get("allCanonicalKnowledgeEqualAccepted") is not True:
        raise ValueError("historical PIT clock gate failed")
    if summary.get("oosOpened") is not False:
        raise ValueError("OOS boundary was opened unexpectedly")
    if summary.get("signalReady") is not False:
        raise ValueError("research amendment hydration must never mark signalReady")


def _write_zero_quarter(output: Path, year: int, quarter_number: int, candidate_run_id: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("raw-manifest.jsonl", "canonical-research.jsonl", "failures.jsonl"):
        (output / filename).write_text("", encoding="utf-8")
    summary = {
        "schemaVersion": "1.0.0",
        "source": "sec-historical-pit-amendment-research",
        "year": year,
        "quarter": quarter_number,
        "candidateRunId": candidate_run_id,
        "eligibleAmendmentFilings": 0,
        "hydratedAmendmentFilings": 0,
        "canonicalRecordCount": 0,
        "qualityGates": {
            "completeAccessionCoverage": True,
            "zeroFailures": True,
            "uniqueTransactionIds": True,
            "uniqueRevisionIds": True,
            "uniqueExactSecRows": True,
            "knowledgeEqualsAccepted": True,
            "oosOpened": False,
            "amendmentAcquisitionComplete": True,
            "amendmentsReconciled": False,
            "canonicalReady": False,
            "signalReady": False,
        },
        "researchScope": "transaction-bearing Forms 4/A and 5/A only",
    }
    summary_path = output / "quarter-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {
        filename: quarter._sha256(output / filename)
        for filename in (
            "raw-manifest.jsonl",
            "canonical-research.jsonl",
            "failures.jsonl",
            "quarter-summary.json",
        )
    }
    (output / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def run(*, candidate_path: Path, output: Path, year: int, quarter_number: int, candidate_run_id: str, shard_size: int, workers: int) -> dict[str, Any]:
    if not 2006 <= year <= 2022:
        raise ValueError("research amendment hydration is bounded to pre-OOS years <= 2022")
    if quarter_number not in {1, 2, 3, 4}:
        raise ValueError("quarter must be 1..4")
    if not 1 <= shard_size <= 1000 or not 1 <= workers <= 6:
        raise ValueError("shard-size/workers outside research safety bounds")

    base._load_candidates = _load_amendment_candidates
    fallback._load_candidates = _load_amendment_candidates
    quarter._load_candidates = _load_amendment_candidates
    quarter.hydrate = fallback.hydrate
    quarter._validate_shard = _validate

    candidates = _load_amendment_candidates(candidate_path, year, quarter_number)
    if not candidates:
        return _write_zero_quarter(output, year, quarter_number, candidate_run_id)

    shard_dirs: list[Path] = []
    shard_root = output.parent / f".{output.name}-shards"
    shard_root.mkdir(parents=True, exist_ok=True)
    import os

    user_agent = os.environ.get("SEC_USER_AGENT", "")
    for shard_index, offset in enumerate(range(0, len(candidates), shard_size)):
        limit = min(shard_size, len(candidates) - offset)
        shard_output = shard_root / f"shard-{shard_index:03d}"
        summary = fallback.hydrate(
            candidate_path=candidate_path,
            output=shard_output,
            year=year,
            quarter=quarter_number,
            offset=offset,
            limit=limit,
            workers=workers,
            user_agent=user_agent,
            candidate_run_id=candidate_run_id,
        )
        _validate(summary, len(candidates))
        shard_dirs.append(shard_output)

    summary = quarter._finalize(
        shard_dirs=shard_dirs,
        output=output,
        candidate_path=candidate_path,
        year=year,
        quarter=quarter_number,
        candidate_run_id=candidate_run_id,
    )
    summary["eligibleAmendmentFilings"] = summary["eligibleOriginalBuyFilings"]
    summary["hydratedAmendmentFilings"] = summary["hydratedOriginalBuyFilings"]
    summary["researchScope"] = "transaction-bearing Forms 4/A and 5/A only"
    summary["amendmentPolicy"] = "acquisition complete for transaction-bearing amendments; deterministic PIT reconciliation remains separate"
    summary["qualityGates"]["amendmentAcquisitionComplete"] = True
    summary["qualityGates"]["amendmentsReconciled"] = False
    summary_path = output / "quarter-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {
        filename: quarter._sha256(output / filename)
        for filename in (
            "raw-manifest.jsonl",
            "canonical-research.jsonl",
            "failures.jsonl",
            "quarter-summary.json",
        )
    }
    (output / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--shard-size", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                candidate_path=args.candidate_path,
                output=args.output,
                year=args.year,
                quarter_number=args.quarter,
                candidate_run_id=args.candidate_run_id,
                shard_size=args.shard_size,
                workers=args.workers,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
