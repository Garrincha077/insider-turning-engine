"""Research-only P/S PIT hydration for the B3 sale-history prerequisite.

This module broadens the historical original-filing selector from buy-bearing
filings to every verified original Form 4/5 filing containing at least one
qualified P/A purchase or S/D sale candidate. It reuses the existing audited
SEC acceptance-time hydration and parser unchanged.

It does not define B3, does not compute performance, and never opens 2023+ OOS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import research_sec_hydrate as base
import research_sec_hydrate_quarter as quarter
import research_sec_hydrate_with_fallback as fallback

PILOT_CONCORDANCE_THRESHOLD = 0.995
MIN_YEAR = 2013
MAX_YEAR = 2022


def _load_ps_candidates(path: Path, year: int, quarter_number: int) -> list[dict[str, Any]]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("P/S PIT history is bounded to 2013-2022")
    if quarter_number not in {1, 2, 3, 4}:
        raise ValueError("quarter must be 1..4")

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        form = str(row.get("documentType") or "").upper()
        buy_count = int(row.get("buyCount", 0))
        sale_count = int(row.get("saleCount", 0))
        if (
            int(row["sourceYear"]) == year
            and int(row["sourceQuarter"]) == quarter_number
            and form in {"4", "5"}
            and int(row.get("transactionCount", 0)) > 0
            and (buy_count > 0 or sale_count > 0)
        ):
            row["_filed"] = base._bulk_date(row["filingDate"])
            rows.append(row)
    rows.sort(key=lambda item: (item["_filed"], str(item["accession"])))
    return rows


def _validate_shard(summary: dict[str, Any], expected_total: int) -> None:
    selected = int(summary["selectedOriginalBuyFilings"])
    discovered = int(summary.get("discoveredFilings", summary["matchedInDailyIndex"]))
    if selected <= 0:
        raise ValueError("empty P/S hydration shard")
    if int(summary["eligibleOriginalBuyFilingsInQuarter"]) != expected_total:
        raise ValueError("P/S shard candidate count disagrees with frozen universe")
    if discovered != selected:
        raise ValueError("P/S accession discovery is incomplete")
    if int(summary["hydratedAndParsedFilings"]) != selected:
        raise ValueError("P/S hydration/parser coverage is incomplete")
    if int(summary["failureCount"]) != 0:
        raise ValueError("P/S shard contains failures")
    if summary.get("allCanonicalKnowledgeEqualAccepted") is not True:
        raise ValueError("historical PIT clock gate failed")
    if summary.get("oosOpened") is not False:
        raise ValueError("sealed OOS boundary was opened")
    if summary.get("signalReady") is not False:
        raise ValueError("P/S research hydration must never mark signalReady")


def _positive(value: object) -> bool:
    if value in (None, ""):
        return False
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number > 0


def _qualified_side(row: dict[str, Any]) -> str | None:
    security = row.get("security") or {}
    transaction = row.get("transaction") or {}
    if security.get("tableType") != "NON_DERIVATIVE":
        return None
    if not _positive(transaction.get("shares")) or not _positive(
        transaction.get("pricePerShare")
    ):
        return None

    code = str(transaction.get("code") or "").upper()
    acquired = str(transaction.get("acquiredDisposed") or "").upper()
    economic = str(transaction.get("economicClassification") or "")
    if code == "P" and acquired == "A" and economic == "OPEN_MARKET_PURCHASE":
        return "BUY"
    if code == "S" and acquired == "D" and economic == "OPEN_MARKET_SALE":
        return "SALE"
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _concordance(
    candidates: list[dict[str, Any]], canonical_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    sides_by_accession: dict[str, set[str]] = {}
    for row in canonical_rows:
        year = int(str((row.get("timestamps") or {}).get("knowledgeAt") or "0000")[:4])
        if year >= 2023:
            raise ValueError("sealed OOS boundary violated by canonical P/S row")
        accession = str((row.get("source") or {}).get("accessionNumber") or "")
        if not accession:
            raise ValueError("canonical P/S row missing accession")
        side = _qualified_side(row)
        if side is not None:
            sides_by_accession.setdefault(accession, set()).add(side)

    expected_accessions = {str(row["accession"]) for row in candidates}
    observed_accessions = {
        str((row.get("source") or {}).get("accessionNumber") or "")
        for row in canonical_rows
    }
    outside = sorted(observed_accessions - expected_accessions)
    if outside:
        raise ValueError(f"canonical rows outside frozen P/S candidate universe: {outside[:5]}")

    buy_candidates = {
        str(row["accession"]) for row in candidates if int(row.get("buyCount", 0)) > 0
    }
    sale_candidates = {
        str(row["accession"]) for row in candidates if int(row.get("saleCount", 0)) > 0
    }
    buy_matches = {acc for acc in buy_candidates if "BUY" in sides_by_accession.get(acc, set())}
    sale_matches = {
        acc for acc in sale_candidates if "SALE" in sides_by_accession.get(acc, set())
    }
    missing_buy = sorted(buy_candidates - buy_matches)
    missing_sale = sorted(sale_candidates - sale_matches)

    buy_rate = len(buy_matches) / len(buy_candidates) if buy_candidates else None
    sale_rate = len(sale_matches) / len(sale_candidates) if sale_candidates else None
    return {
        "candidateAccessions": len(expected_accessions),
        "buyCandidateAccessions": len(buy_candidates),
        "saleCandidateAccessions": len(sale_candidates),
        "buyConcordantAccessions": len(buy_matches),
        "saleConcordantAccessions": len(sale_matches),
        "buyConcordanceRate": buy_rate,
        "saleConcordanceRate": sale_rate,
        "missingBuyCandidateAccessions": missing_buy,
        "missingSaleCandidateAccessions": missing_sale,
        "qualifiedCanonicalBuyRows": sum(
            _qualified_side(row) == "BUY" for row in canonical_rows
        ),
        "qualifiedCanonicalSaleRows": sum(
            _qualified_side(row) == "SALE" for row in canonical_rows
        ),
    }


def _candidate_mix(candidates: list[dict[str, Any]]) -> dict[str, int]:
    buy_only = sale_only = mixed = 0
    for row in candidates:
        buy = int(row.get("buyCount", 0)) > 0
        sale = int(row.get("saleCount", 0)) > 0
        if buy and sale:
            mixed += 1
        elif buy:
            buy_only += 1
        elif sale:
            sale_only += 1
    return {
        "buyOnlyFilings": buy_only,
        "saleOnlyFilings": sale_only,
        "mixedBuySaleFilings": mixed,
    }


def _pilot_passed(mix: dict[str, int], concordance: dict[str, Any]) -> bool:
    buy_rate = concordance["buyConcordanceRate"]
    sale_rate = concordance["saleConcordanceRate"]
    return (
        mix["saleOnlyFilings"] > 0
        and buy_rate is not None
        and sale_rate is not None
        and math.isfinite(float(buy_rate))
        and math.isfinite(float(sale_rate))
        and float(buy_rate) >= PILOT_CONCORDANCE_THRESHOLD
        and float(sale_rate) >= PILOT_CONCORDANCE_THRESHOLD
    )


def run(
    *,
    candidate_path: Path,
    output: Path,
    year: int,
    quarter_number: int,
    candidate_run_id: str,
    shard_size: int = 500,
    workers: int = 4,
) -> dict[str, Any]:
    if not 1 <= shard_size <= 1000:
        raise ValueError("shard_size must be 1..1000")
    if not 1 <= workers <= 6:
        raise ValueError("workers must be 1..6")

    candidates = _load_ps_candidates(candidate_path, year, quarter_number)
    if not candidates:
        raise ValueError("no frozen P/S candidates for requested quarter")

    original_base_loader = base._load_candidates
    original_fallback_loader = fallback._load_candidates
    original_quarter_loader = quarter._load_candidates
    original_validate = quarter._validate_shard
    original_hydrate = quarter.hydrate

    try:
        base._load_candidates = _load_ps_candidates
        fallback._load_candidates = _load_ps_candidates
        quarter._load_candidates = _load_ps_candidates
        quarter._validate_shard = _validate_shard
        quarter.hydrate = fallback.hydrate

        shard_root = output.parent / f".{output.name}-shards"
        shard_root.mkdir(parents=True, exist_ok=True)
        shard_dirs: list[Path] = []
        user_agent = os.environ.get("SEC_USER_AGENT", "")
        if not user_agent.strip():
            raise ValueError("SEC_USER_AGENT is required")

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
            _validate_shard(summary, len(candidates))
            shard_dirs.append(shard_output)

        summary = quarter._finalize(
            shard_dirs=shard_dirs,
            output=output,
            candidate_path=candidate_path,
            year=year,
            quarter=quarter_number,
            candidate_run_id=candidate_run_id,
        )
    finally:
        base._load_candidates = original_base_loader
        fallback._load_candidates = original_fallback_loader
        quarter._load_candidates = original_quarter_loader
        quarter._validate_shard = original_validate
        quarter.hydrate = original_hydrate

    canonical_rows = _read_jsonl(output / "canonical-research.jsonl")
    mix = _candidate_mix(candidates)
    concordance = _concordance(candidates, canonical_rows)

    summary.update(
        {
            "schemaVersion": "1.0.0-b3-ps",
            "source": "sec-historical-pit-original-ps-research",
            "researchOnly": True,
            "eligibleOriginalPsFilings": len(candidates),
            "hydratedOriginalPsFilings": int(summary["hydratedOriginalBuyFilings"]),
            "candidateMix": mix,
            "bulkCanonicalConcordance": concordance,
            "pilotConcordanceThreshold": PILOT_CONCORDANCE_THRESHOLD,
            "psHistoryScalePilotPassed": _pilot_passed(mix, concordance),
            "fullPsHistoryComplete": False,
            "amendmentsReconciledForPsUniverse": False,
            "b3Eligible": False,
            "oosOpened": False,
            "productionScoringChanged": False,
            "canonicalReady": False,
            "signalReady": False,
            "b3DefinitionFrozen": False,
            "interpretation": (
                "P/S PIT acquisition prerequisite only. Passing this pilot authorizes "
                "scaling the identical acquisition contract; it does not define or test B3."
            ),
        }
    )
    summary["qualityGates"].update(
        {
            "saleOnlyFilingsPresent": mix["saleOnlyFilings"] > 0,
            "buyConcordanceAtLeast995": (
                concordance["buyConcordanceRate"] is not None
                and concordance["buyConcordanceRate"] >= PILOT_CONCORDANCE_THRESHOLD
            ),
            "saleConcordanceAtLeast995": (
                concordance["saleConcordanceRate"] is not None
                and concordance["saleConcordanceRate"] >= PILOT_CONCORDANCE_THRESHOLD
            ),
            "fullPsHistoryComplete": False,
            "amendmentsReconciledForPsUniverse": False,
            "b3Eligible": False,
            "productionScoringChanged": False,
        }
    )

    summary_path = output / "quarter-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = json.loads((output / "checksums.json").read_text(encoding="utf-8"))
    checksums["quarter-summary.json"] = quarter._sha256(summary_path)
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
