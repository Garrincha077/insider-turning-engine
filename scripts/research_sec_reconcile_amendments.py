"""Deterministic research-only PIT reconciliation of historical Forms 4/A and 5/A.

Linkage is deliberately conservative.  It uses SEC DATE_OF_ORIG_SUB, issuer CIK,
reporting-owner CIK, form family, and exact canonical owner/table/row-sequence
evidence.  It never matches on approximate price, shares, or transaction date.

The acquired historical canonical rows retain actual 2026 retrieval in
``recordedAt``.  Their parser lifecycle ``validFrom`` therefore reflects storage
time, not historical information availability.  This research layer explicitly
normalizes lifecycle ``validFrom`` to ``knowledgeAt`` (which was already audited
to equal SEC ``acceptedAt``) before applying amendment chains.  Production parser
or scoring configuration is not changed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction, LifecycleStatus
from insider_turning_engine.normalization.amendments import resolve_amendments


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_all(root: Path, filename: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob(filename)):
        rows.extend(_read_jsonl(path))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _core_record(row: dict[str, Any], *, amendment: bool) -> CanonicalTransaction:
    value = copy.deepcopy(row)
    value.pop("researchBackfill", None)
    knowledge = value["timestamps"]["knowledgeAt"]
    value["lifecycle"]["validFrom"] = knowledge
    value["lifecycle"]["validTo"] = None
    value["lifecycle"]["status"] = LifecycleStatus.ACTIVE.value
    value["lifecycle"]["isAmendment"] = amendment
    value["lifecycle"]["supersedesRevisionId"] = None
    return CanonicalTransaction.model_validate(value)


def _row_key(record: CanonicalTransaction, accession: str) -> tuple[str, str, str, int]:
    return (
        accession,
        record.reporting_owner.cik,
        record.security.table_type.value,
        record.source.row_sequence,
    )


def _predicted_revision_id(predecessor_transaction_id: str, predecessor_revision_id: str, amendment: CanonicalTransaction) -> str:
    material = "|".join(
        (
            predecessor_transaction_id,
            predecessor_revision_id,
            amendment.source.accession_number,
            amendment.source.content_hash,
        )
    )
    return "txr_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def reconcile(*, original_root: Path, amendment_root: Path, catalog_root: Path, output: Path) -> dict[str, Any]:
    original_rows = _read_all(original_root, "canonical-research.jsonl")
    amendment_rows = _read_all(amendment_root, "canonical-research.jsonl")
    candidate_rows = _read_all(catalog_root, "amendment-candidates.jsonl")
    predecessor_rows = _read_all(catalog_root, "predecessor-catalog.jsonl")
    zero_transaction_rows = _read_all(catalog_root, "zero-transaction-amendments.jsonl")
    if not original_rows:
        raise ValueError("no original-buy canonical history was supplied")
    if not candidate_rows and amendment_rows:
        raise ValueError("amendment canonical rows exist without candidate evidence")

    originals = [_core_record(row, amendment=False) for row in original_rows]
    amendments = [_core_record(row, amendment=True) for row in amendment_rows]
    if any(record.timestamps.knowledge_at.year >= 2023 for record in [*originals, *amendments]):
        raise ValueError("sealed OOS boundary violated by 2023+ canonical evidence")
    if any(record.timestamps.knowledge_at != record.timestamps.accepted_at for record in [*originals, *amendments]):
        raise ValueError("knowledgeAt != acceptedAt in historical PIT input")

    original_by_accession: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    exact_original: dict[tuple[str, str, str, int], CanonicalTransaction] = {}
    for record in originals:
        accession = record.source.accession_number
        original_by_accession[accession].append(record)
        key = _row_key(record, accession)
        prior = exact_original.get(key)
        if prior is not None and prior.revision_id != record.revision_id:
            raise ValueError(f"duplicate exact original row identity: {key}")
        exact_original[key] = record

    candidate_by_accession = {str(row["accession"]): row for row in candidate_rows}
    if len(candidate_by_accession) != len(candidate_rows):
        raise ValueError("duplicate amendment candidate accession")

    catalog_index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in predecessor_rows:
        key = (
            str(row["issuerCik"]),
            str(row["filingDate"]),
            str(row["documentType"]).upper(),
        )
        catalog_index[key].append(row)

    amendment_by_accession: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for record in amendments:
        amendment_by_accession[record.source.accession_number].append(record)

    accession_order = sorted(
        amendment_by_accession,
        key=lambda accession: (
            min(row.timestamps.knowledge_at for row in amendment_by_accession[accession]),
            accession,
        ),
    )
    latest_revision: dict[tuple[str, str, str, int], str] = {
        _row_key(record, record.source.accession_number): record.revision_id for record in originals
    }
    linked_amendments: list[CanonicalTransaction] = []
    linkage_rows: list[dict[str, Any]] = []
    research_quarantines: list[dict[str, Any]] = []

    for accession in accession_order:
        rows = amendment_by_accession[accession]
        evidence = candidate_by_accession.get(accession)
        if evidence is None:
            raise ValueError(f"missing candidate evidence for hydrated amendment {accession}")
        original_date = evidence.get("originalSubmissionDate")
        form = str(evidence["documentType"]).upper()
        base_form = form[:-2] if form.endswith("/A") else form
        amendment_owners = {row.reporting_owner.cik for row in rows}
        status = "UNRESOLVED"
        root_accession: str | None = None
        reason: str | None = None

        if not original_date:
            reason = "MISSING_DATE_OF_ORIG_SUB"
        else:
            candidates = [
                item
                for item in catalog_index.get(
                    (str(evidence["issuerCik"]), str(original_date), base_form), []
                )
                if amendment_owners.issubset(set(item.get("reportingOwnerCiks", [])))
            ]
            if not candidates:
                reason = "NO_PREDECESSOR_CATALOG_MATCH"
            else:
                supported: list[str] = []
                for item in candidates:
                    candidate_accession = str(item["accession"])
                    exact_matches = sum(
                        _row_key(row, candidate_accession) in exact_original for row in rows
                    )
                    if exact_matches > 0:
                        supported.append(candidate_accession)
                supported = sorted(set(supported))
                if len(supported) == 1:
                    root_accession = supported[0]
                    status = "LINKED_TO_ORIGINAL_BUY_UNIVERSE"
                elif len(supported) > 1:
                    reason = "AMBIGUOUS_EXACT_PREDECESSOR"
                elif len(candidates) == 1:
                    root_accession = str(candidates[0]["accession"])
                    if root_accession not in original_by_accession:
                        status = "PREDECESSOR_OUTSIDE_ORIGINAL_BUY_UNIVERSE"
                    else:
                        reason = "NO_EXACT_ROW_MATCH"
                else:
                    reason = "AMBIGUOUS_PREDECESSOR_WITHOUT_EXACT_ROW"

        linked_rows = 0
        if status == "LINKED_TO_ORIGINAL_BUY_UNIVERSE" and root_accession is not None:
            prepared: list[CanonicalTransaction] = []
            for amendment in rows:
                root_key = _row_key(amendment, root_accession)
                root = exact_original.get(root_key)
                predecessor_revision = latest_revision.get(root_key)
                if root is None or predecessor_revision is None:
                    research_quarantines.append(
                        {
                            "accession": accession,
                            "reasonCode": "AMENDMENT_ROW_NO_EXACT_PREDECESSOR",
                            "ownerCik": amendment.reporting_owner.cik,
                            "tableType": amendment.security.table_type.value,
                            "rowSequence": amendment.source.row_sequence,
                        }
                    )
                    continue
                source = amendment.source.model_copy(
                    update={"amends_accession_number": root_accession}
                )
                lifecycle = amendment.lifecycle.model_copy(
                    update={
                        "valid_from": amendment.timestamps.knowledge_at,
                        "valid_to": None,
                        "status": LifecycleStatus.ACTIVE,
                        "is_amendment": True,
                        "supersedes_revision_id": predecessor_revision,
                    }
                )
                prepared_row = amendment.model_copy(
                    update={"source": source, "lifecycle": lifecycle}
                )
                prepared.append(prepared_row)
                latest_revision[root_key] = _predicted_revision_id(
                    root.transaction_id, predecessor_revision, prepared_row
                )
            linked_amendments.extend(prepared)
            linked_rows = len(prepared)
            if linked_rows != len(rows):
                status = "PARTIALLY_LINKED_EXACT_ROWS"
                reason = "ONE_OR_MORE_AMENDMENT_ROWS_LACK_EXACT_PREDECESSOR"
        elif status not in {"PREDECESSOR_OUTSIDE_ORIGINAL_BUY_UNIVERSE"}:
            for amendment in rows:
                research_quarantines.append(
                    {
                        "accession": accession,
                        "reasonCode": reason or "UNRESOLVED_AMENDMENT",
                        "ownerCik": amendment.reporting_owner.cik,
                        "tableType": amendment.security.table_type.value,
                        "rowSequence": amendment.source.row_sequence,
                    }
                )

        linkage_rows.append(
            {
                "amendmentAccession": accession,
                "documentType": form,
                "issuerCik": evidence["issuerCik"],
                "originalSubmissionDate": original_date,
                "resolvedPredecessorAccession": root_accession,
                "status": status,
                "reason": reason,
                "canonicalRows": len(rows),
                "linkedRows": linked_rows,
                "acceptedAt": min(row.timestamps.knowledge_at for row in rows).isoformat(),
            }
        )

    point_in_time = max(record.timestamps.knowledge_at for record in [*originals, *linked_amendments]) + timedelta(seconds=1)
    resolved = resolve_amendments([*originals, *linked_amendments], as_of=point_in_time)
    resolver_quarantines = [q.model_dump(by_alias=True, mode="json") for q in resolved.quarantines]

    output.mkdir(parents=True, exist_ok=True)
    revisions = [row.canonical_dump() for row in resolved.all_revisions]
    effective = [row.canonical_dump() for row in resolved.effective_records]
    _write_jsonl(output / "reconciled-all-revisions.jsonl", revisions)
    _write_jsonl(output / "effective-end-2022.jsonl", effective)
    _write_jsonl(output / "amendment-linkage.jsonl", linkage_rows)
    _write_jsonl(
        output / "quarantines.jsonl",
        [*research_quarantines, *resolver_quarantines],
    )

    counts: dict[str, int] = defaultdict(int)
    for row in linkage_rows:
        counts[str(row["status"])] += 1
    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "SEC PIT amendment reconciliation research",
        "period": "2013-2022",
        "originalCanonicalRows": len(originals),
        "transactionBearingAmendmentFilingsHydrated": len(amendment_by_accession),
        "zeroTransactionAmendmentFilingsObserved": len(zero_transaction_rows),
        "amendmentCanonicalRows": len(amendments),
        "linkedAmendmentRows": len(linked_amendments),
        "linkageStatusCounts": dict(sorted(counts.items())),
        "researchQuarantineRows": len(research_quarantines),
        "resolverQuarantineRows": len(resolver_quarantines),
        "reconciledRevisionRows": len(revisions),
        "effectiveRowsAtEndOfPeriod": len(effective),
        "lifecycleHistoricalClockNormalization": {
            "applied": True,
            "from": "parser recordedAt/retrieval-time validFrom",
            "to": "knowledgeAt == SEC acceptedAt",
            "productionParserChanged": False,
        },
        "linkagePolicy": {
            "dateEvidence": "SEC SUBMISSION.DATE_OF_ORIG_SUB",
            "identityEvidence": [
                "issuer CIK",
                "reporting-owner CIK",
                "form family",
                "exact owner/table/row sequence",
            ],
            "fuzzyPriceShareDateMatching": False,
            "ambiguousLinks": "quarantine",
        },
        "amendmentReconciliationComplete": True,
        "canonicalReady": False,
        "marketDataJoined": False,
        "signalReady": False,
        "oosOpened": False,
        "nextGate": "historical adjusted/delisted market-data join",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--amendment-root", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile(
                original_root=args.original_root,
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
