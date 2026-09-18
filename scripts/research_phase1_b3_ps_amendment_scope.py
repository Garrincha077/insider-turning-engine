"""Build the frozen B3 P/S amendment scope without computing any returns.

The inventory combines:
- the frozen original P/S accession universe;
- already hydrated transaction-bearing 4/A and 5/A canonical rows;
- frozen SEC amendment/predecessor catalogs, including zero-transaction amendments.

It classifies amendment chains for the later P/S lifecycle gate. It does not
hydrate supporting predecessors, does not resolve lifecycle changes, does not
open 2023+ evidence, and does not define or evaluate B3.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_all(root: Path, filename: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob(filename)):
        rows.extend(_read_jsonl(path))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


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
    if not _positive(transaction.get("shares")):
        return None
    if not _positive(transaction.get("pricePerShare")):
        return None
    code = str(transaction.get("code") or "").upper()
    ad = str(transaction.get("acquiredDisposed") or "").upper()
    economic = str(transaction.get("economicClassification") or "")
    if code == "P" and ad == "A" and economic == "OPEN_MARKET_PURCHASE":
        return "BUY"
    if code == "S" and ad == "D" and economic == "OPEN_MARKET_SALE":
        return "SALE"
    return None


def _ps_root_accessions(rows: list[dict[str, Any]]) -> set[str]:
    roots: set[str] = set()
    for row in rows:
        year = int(row["sourceYear"])
        if not 2013 <= year <= 2022:
            raise ValueError("P/S candidate source is outside frozen 2013-2022 scope")
        form = str(row.get("documentType") or "").upper()
        if form not in {"4", "5"}:
            continue
        buy = int(row.get("buyCount", 0))
        sale = int(row.get("saleCount", 0))
        if buy > 0 or sale > 0:
            roots.add(str(row["accession"]))
    if not roots:
        raise ValueError("empty original P/S accession universe")
    return roots


def _catalog_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        form = str(row.get("documentType") or "").upper()
        if form not in {"4", "5"}:
            continue
        filing_date = str(row.get("filingDate") or "")
        if not filing_date:
            continue
        index[(str(row["issuerCik"]), filing_date, form)].append(row)
    return index


def _resolve_root(
    amendment: dict[str, Any],
    catalog: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> tuple[str | None, str | None, int]:
    original_date = amendment.get("originalSubmissionDate")
    if not original_date:
        return None, "MISSING_DATE_OF_ORIG_SUB", 0
    form = str(amendment.get("documentType") or "").upper()
    base_form = form[:-2] if form.endswith("/A") else form
    owners = {str(value) for value in amendment.get("reportingOwnerCiks", [])}
    candidates = []
    for row in catalog.get(
        (str(amendment["issuerCik"]), str(original_date), base_form),
        [],
    ):
        predecessor_owners = {str(value) for value in row.get("reportingOwnerCiks", [])}
        if owners.issubset(predecessor_owners):
            candidates.append(row)
    accessions = sorted({str(row["accession"]) for row in candidates})
    if not accessions:
        return None, "NO_PREDECESSOR_CATALOG_MATCH", 0
    if len(accessions) > 1:
        return None, "AMBIGUOUS_PREDECESSOR_CATALOG_MATCH", len(accessions)
    return accessions[0], None, 1


def _canonical_by_accession(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        knowledge = str((row.get("timestamps") or {}).get("knowledgeAt") or "")
        accepted = str((row.get("timestamps") or {}).get("acceptedAt") or "")
        if not knowledge or knowledge[:4].isdigit() is False:
            raise ValueError("canonical amendment row is missing knowledgeAt")
        if int(knowledge[:4]) >= 2023:
            raise ValueError("sealed OOS boundary violated by 2023+ amendment evidence")
        if knowledge != accepted:
            raise ValueError("historical amendment knowledgeAt != acceptedAt")
        accession = str((row.get("source") or {}).get("accessionNumber") or "")
        if not accession:
            raise ValueError("canonical amendment row is missing accession")
        grouped[accession].append(row)
    return grouped


def build(
    *,
    ps_candidate_root: Path,
    amendment_root: Path,
    catalog_root: Path,
    output: Path,
) -> dict[str, Any]:
    ps_candidates = _read_all(ps_candidate_root, "candidates.jsonl")
    amendment_candidates = _read_all(catalog_root, "amendment-candidates.jsonl")
    predecessor_rows = _read_all(catalog_root, "predecessor-catalog.jsonl")
    zero_rows = _read_all(catalog_root, "zero-transaction-amendments.jsonl")
    canonical_rows = _read_all(amendment_root, "canonical-research.jsonl")

    roots = _ps_root_accessions(ps_candidates)
    catalog = _catalog_index(predecessor_rows)
    canonical = _canonical_by_accession(canonical_rows)

    candidate_by_accession = {
        str(row["accession"]): row for row in amendment_candidates
    }
    if len(candidate_by_accession) != len(amendment_candidates):
        raise ValueError("duplicate transaction-bearing amendment accession")
    if set(canonical) != set(candidate_by_accession):
        missing = sorted(set(candidate_by_accession) - set(canonical))
        extra = sorted(set(canonical) - set(candidate_by_accession))
        raise ValueError(
            f"amendment canonical/candidate accession mismatch; missing={missing[:5]} extra={extra[:5]}"
        )

    scope_rows: list[dict[str, Any]] = []
    supporting: dict[str, dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []

    for accession in sorted(candidate_by_accession):
        evidence = candidate_by_accession[accession]
        rows = canonical[accession]
        sides = [_qualified_side(row) for row in rows]
        qualified_buy = sum(side == "BUY" for side in sides)
        qualified_sale = sum(side == "SALE" for side in sides)
        root, reason, candidate_count = _resolve_root(evidence, catalog)
        root_in_ps = root in roots if root is not None else None

        if root is None:
            status = (
                "QUARANTINE_UNRESOLVED_QUALIFIED_PS_AMENDMENT"
                if qualified_buy or qualified_sale
                else "QUARANTINE_SCOPE_UNRESOLVED"
            )
        elif root_in_ps:
            status = "ROOT_IN_PS_UNIVERSE"
        elif qualified_buy or qualified_sale:
            status = "SUPPORTING_PREDECESSOR_REQUIRED"
            supporting[root] = {
                "rootPredecessorAccession": root,
                "issuerCik": evidence["issuerCik"],
                "rootFilingDate": evidence["originalSubmissionDate"],
                "rootForm": str(evidence["documentType"]).upper()[:-2],
                "supportingPredecessorOnly": True,
                "requiredByAmendmentAccessions": sorted(
                    {
                        *supporting.get(root, {}).get(
                            "requiredByAmendmentAccessions", []
                        ),
                        accession,
                    }
                ),
                "oosOpened": False,
            }
        else:
            status = "OUTSIDE_PS_ECONOMIC_SCOPE"

        accepted_values = sorted(
            {
                str(row["timestamps"]["acceptedAt"])
                for row in rows
            }
        )
        item = {
            "amendmentAccession": accession,
            "documentType": evidence["documentType"],
            "issuerCik": evidence["issuerCik"],
            "originalSubmissionDate": evidence.get("originalSubmissionDate"),
            "acceptedAt": accepted_values[0] if accepted_values else None,
            "canonicalRows": len(rows),
            "qualifiedBuyRows": qualified_buy,
            "qualifiedSaleRows": qualified_sale,
            "resolvedRootPredecessorAccession": root,
            "rootInOriginalPsUniverse": root_in_ps,
            "predecessorCandidateCount": candidate_count,
            "status": status,
            "reason": reason,
        }
        scope_rows.append(item)
        if status.startswith("QUARANTINE_"):
            quarantine_rows.append(item)

    for evidence in sorted(zero_rows, key=lambda row: str(row["accession"])):
        root, reason, candidate_count = _resolve_root(evidence, catalog)
        root_in_ps = root in roots if root is not None else None
        if root is None:
            status = "QUARANTINE_ZERO_TRANSACTION_SCOPE_UNRESOLVED"
        elif root_in_ps:
            status = "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT"
        else:
            status = "OUTSIDE_PS_ECONOMIC_SCOPE"

        item = {
            "amendmentAccession": evidence["accession"],
            "documentType": evidence["documentType"],
            "issuerCik": evidence["issuerCik"],
            "originalSubmissionDate": evidence.get("originalSubmissionDate"),
            "acceptedAt": None,
            "canonicalRows": 0,
            "qualifiedBuyRows": 0,
            "qualifiedSaleRows": 0,
            "resolvedRootPredecessorAccession": root,
            "rootInOriginalPsUniverse": root_in_ps,
            "predecessorCandidateCount": candidate_count,
            "status": status,
            "reason": reason,
            "zeroTransactionAmendment": True,
            "acceptanceHydrationRequired": (
                status == "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT"
                or status.startswith("QUARANTINE_")
            ),
        }
        scope_rows.append(item)
        if status.startswith("QUARANTINE_"):
            quarantine_rows.append(item)

    scope_rows.sort(
        key=lambda row: (
            str(row.get("acceptedAt") or ""),
            str(row["amendmentAccession"]),
        )
    )
    supporting_rows = sorted(
        supporting.values(),
        key=lambda row: str(row["rootPredecessorAccession"]),
    )

    status_counts: dict[str, int] = defaultdict(int)
    for row in scope_rows:
        status_counts[str(row["status"])] += 1

    output.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output / "amendment-ps-scope.jsonl", scope_rows)
    _write_jsonl(output / "supporting-predecessors.jsonl", supporting_rows)
    _write_jsonl(output / "scope-quarantines.jsonl", quarantine_rows)

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 P/S amendment scope inventory",
        "period": "2013-2022",
        "researchOnly": True,
        "originalPsRootAccessions": len(roots),
        "transactionBearingAmendmentFilings": len(amendment_candidates),
        "zeroTransactionAmendmentFilings": len(zero_rows),
        "scopeRows": len(scope_rows),
        "statusCounts": dict(sorted(status_counts.items())),
        "supportingPredecessorFilingsRequired": len(supporting_rows),
        "quarantineRows": len(quarantine_rows),
        "scopeInventoryComplete": True,
        "supportingPredecessorHydrationComplete": False,
        "zeroTransactionSemanticReviewComplete": False,
        "amendmentsReconciledForPsUniverse": False,
        "b3Eligible": False,
        "b3DefinitionFrozen": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "signalReady": False,
        "nextGate": (
            "hydrate required supporting predecessors and zero-transaction amendments, "
            "then run deterministic P/S lifecycle reconciliation"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ps-candidate-root", type=Path, required=True)
    parser.add_argument("--amendment-root", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                ps_candidate_root=args.ps_candidate_root,
                amendment_root=args.amendment_root,
                catalog_root=args.catalog_root,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
