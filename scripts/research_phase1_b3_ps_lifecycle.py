"""Deterministic B3 P/S lifecycle reconciliation.

Research-only and performance-blind. Combines the frozen original P/S history,
transaction-bearing amendments, supporting predecessors, zero-transaction
amendment evidence, and the frozen amendment-scope inventory.

Ambiguous evidence is quarantined. No fuzzy economic matching is permitted.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import (
    CanonicalTransaction,
    Lifecycle,
    LifecycleStatus,
)
from insider_turning_engine.normalization.amendments import resolve_amendments

LINKABLE_SCOPE = {"ROOT_IN_PS_UNIVERSE", "SUPPORTING_PREDECESSOR_REQUIRED"}
SCOPE_QUARANTINE_PREFIX = "QUARANTINE_"

_CANCEL_RE = re.compile(
    "|".join(
        (
            r"\bdid not (?:in fact )?(?:occur|take place)\b",
            r"\bwas not consummated\b",
            r"\bnot consummated\b",
            r"\bnever (?:in fact )?(?:purchased|sold|bought|acquired|disposed)\b",
            r"\bdid not (?:sell|purchase|buy|acquire|dispose of)\b",
            r"\b(?:trade|transaction|purchase|sale) (?:was |were )?"
            r"(?:subsequently )?(?:cancelled|canceled)\b",
            r"\bunwound\b.{0,180}\bdid not occur\b",
            r"\bvoid ab initio\b",
        )
    ),
    re.IGNORECASE,
)
_NO_CHANGE_RE = re.compile(
    "|".join(
        (
            r"\bdoes not disclose any transactions\b",
            r"\bsolely to (?:correct|update)\b.{0,180}\b(?:address|amount of securities "
            r"beneficially owned|shares beneficially owned|holdings|officer title|signature|ownership)\b",
            r"\b(?:correct|update)\b.{0,100}\b(?:amount of securities beneficially owned|"
            r"shares beneficially owned|shares owned following|mailing address|reporting person.?s "
            r"address|officer title|signature)\b",
            r"\bcorrect(?:ed|ing)? the number of securities beneficially owned\b",
        )
    ),
    re.IGNORECASE,
)
_ECON_CORRECTION_RE = re.compile(
    r"\b(?:incorrect|incorrectly|erroneous|erroneously|mistaken|mistakenly|inadvertent|"
    r"inadvertently|reported in error|filed in error|over[- ]reported|under[- ]reported|omitted)\b"
    r".{0,180}\b(?:purchase|sale|sold|buy|acquisition|disposition|transaction|trade|price|"
    r"transaction code|shares (?:sold|purchased|acquired|disposed))\b|"
    r"\b(?:purchase|sale|sold|buy|acquisition|disposition|transaction|trade|price|transaction code)\b"
    r".{0,180}\b(?:incorrect|incorrectly|erroneous|erroneously|mistaken|mistakenly|inadvertent|"
    r"inadvertently|reported in error|filed in error|over[- ]reported|under[- ]reported|omitted)\b",
    re.IGNORECASE,
)
_SALE_RE = re.compile(r"\b(?:sale|sold|sell|disposition|disposed)\b", re.IGNORECASE)
_BUY_RE = re.compile(r"\b(?:purchase|purchased|buy|bought|acquisition|acquired)\b", re.IGNORECASE)
_SHARES_RE = re.compile(
    r"\b(?:sale|purchase|sold|purchased|sell|buy|acquisition|disposition)"
    r".{0,80}?([0-9][0-9,]*(?:\.[0-9]+)?)\s+(?:shares?|common units?)\b",
    re.IGNORECASE,
)
_OWNER_CIK_RE = re.compile(r"<rptOwnerCik>\s*(\d{1,10})\s*</rptOwnerCik>", re.IGNORECASE)


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


def _bucket(issuer_cik: str, shard_count: int) -> int:
    digest = hashlib.sha256(str(issuer_cik).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def _selected(issuer_cik: str, shard_index: int, shard_count: int) -> bool:
    return _bucket(issuer_cik, shard_count) == shard_index


def _canonical_issuer(row: dict[str, Any]) -> str:
    issuer = row.get("issuer")
    if not isinstance(issuer, dict) or not issuer.get("cik"):
        raise ValueError("canonical row is missing issuer.cik")
    return str(issuer["cik"])


def _core_record(row: dict[str, Any], *, amendment: bool) -> CanonicalTransaction:
    value = copy.deepcopy(row)
    value.pop("researchBackfill", None)
    value.pop("researchReconciliation", None)
    knowledge = value["timestamps"]["knowledgeAt"]
    value["lifecycle"]["validFrom"] = knowledge
    value["lifecycle"]["validTo"] = None
    value["lifecycle"]["status"] = LifecycleStatus.ACTIVE.value
    value["lifecycle"]["isAmendment"] = amendment
    value["lifecycle"]["supersedesRevisionId"] = None
    return CanonicalTransaction.model_validate(value)


def _row_key(
    record: CanonicalTransaction, accession: str
) -> tuple[str, str, str, int]:
    return (
        accession,
        record.reporting_owner.cik,
        record.security.table_type.value,
        record.source.row_sequence,
    )


def _positive(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number > 0


def _qualified_side_record(record: CanonicalTransaction) -> str | None:
    tx = record.transaction
    if record.security.table_type.value != "NON_DERIVATIVE":
        return None
    if not _positive(tx.shares) or not _positive(tx.price_per_share):
        return None
    if (
        tx.code == "P"
        and tx.acquired_disposed == "A"
        and tx.economic_classification.value == "OPEN_MARKET_PURCHASE"
    ):
        return "BUY"
    if (
        tx.code == "S"
        and tx.acquired_disposed == "D"
        and tx.economic_classification.value == "OPEN_MARKET_SALE"
    ):
        return "SALE"
    return None


def _economic_signature(record: CanonicalTransaction) -> tuple[Any, ...]:
    tx = record.transaction
    return (
        _qualified_side_record(record),
        str(tx.shares) if tx.shares is not None else None,
        str(tx.price_per_share) if tx.price_per_share is not None else None,
        tx.transaction_date.isoformat(),
        tx.code,
        tx.acquired_disposed,
        tx.economic_classification.value,
    )


def _predicted_revision_id(
    predecessor_transaction_id: str,
    predecessor_revision_id: str,
    amendment: CanonicalTransaction,
) -> str:
    material = "|".join(
        (
            predecessor_transaction_id,
            predecessor_revision_id,
            amendment.source.accession_number,
            amendment.source.content_hash,
        )
    )
    return "txr_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _xml_text(payload: str) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("zero-transaction XML is not parseable") from exc
    pieces: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag in {"remarks", "footnote"}:
            pieces.extend(part.strip() for part in node.itertext() if part.strip())
    return html.unescape(re.sub(r"\s+", " ", " ".join(pieces))).strip()


def _owner_ciks(payload: str) -> set[str]:
    return {match.zfill(10) for match in _OWNER_CIK_RE.findall(payload)}


def _cancel_descriptor(text: str) -> tuple[str | None, Decimal | None]:
    sale = bool(_SALE_RE.search(text))
    buy = bool(_BUY_RE.search(text))
    side = "SALE" if sale and not buy else "BUY" if buy and not sale else None
    shares_match = _SHARES_RE.search(text)
    shares = None
    if shares_match is not None:
        try:
            shares = Decimal(shares_match.group(1).replace(",", ""))
        except InvalidOperation:
            shares = None
    return side, shares


def _classify_zero_text(text: str) -> tuple[str, str]:
    if _CANCEL_RE.search(text):
        return "PS_LIFECYCLE_CHANGE_SUPPORTED", "EXPLICIT_REPORTED_TRANSACTION_DID_NOT_OCCUR"
    if _NO_CHANGE_RE.search(text) and not _ECON_CORRECTION_RE.search(text):
        return "NON_TRANSACTIONAL_NO_CHANGE_TO_PS_ECONOMICS", "EXPLICIT_NON_TRANSACTIONAL_CORRECTION"
    return (
        "QUARANTINE_AMBIGUOUS_ZERO_TRANSACTION_AMENDMENT",
        "ZERO_TRANSACTION_TEXT_NOT_SAFE_FOR_AUTOMATIC_ECONOMIC_TRANSFORM",
    )


def _zero_evidence(
    evidence_root: Path,
    *,
    shard_index: int,
    shard_count: int,
) -> list[tuple[Path, dict[str, Any], str]]:
    values: list[tuple[Path, dict[str, Any], str]] = []
    for manifest_path in sorted(evidence_root.rglob("zero-transaction-manifest.jsonl")):
        for row in _read_jsonl(manifest_path):
            issuer = str(row.get("issuerCik") or "")
            if not issuer or not _selected(issuer, shard_index, shard_count):
                continue
            xml_rel = str(row.get("xmlEvidencePath") or "")
            xml_path = manifest_path.parent / xml_rel
            if not xml_path.exists():
                raise ValueError(f"missing zero-transaction XML evidence: {xml_path}")
            values.append((xml_path, row, xml_path.read_text(encoding="utf-8")))
    return values


def reconcile_shard(
    *,
    original_root: Path,
    amendment_root: Path,
    evidence_root: Path,
    scope_root: Path,
    output: Path,
    shard_index: int,
    shard_count: int,
) -> dict[str, Any]:
    if shard_count <= 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid issuer shard")

    original_rows = [
        row
        for row in _read_all(original_root, "canonical-research.jsonl")
        if _selected(_canonical_issuer(row), shard_index, shard_count)
    ]
    support_rows = [
        row
        for row in _read_all(evidence_root, "supporting-predecessor-canonical.jsonl")
        if _selected(_canonical_issuer(row), shard_index, shard_count)
    ]
    amendment_rows = [
        row
        for row in _read_all(amendment_root, "canonical-research.jsonl")
        if _selected(_canonical_issuer(row), shard_index, shard_count)
    ]
    scope_rows = [
        row
        for row in _read_all(scope_root, "amendment-ps-scope.jsonl")
        if _selected(str(row["issuerCik"]), shard_index, shard_count)
    ]
    scope_by_accession = {
        str(row["amendmentAccession"]): row for row in scope_rows
    }
    if len(scope_by_accession) != len(scope_rows):
        raise ValueError("duplicate amendment scope accession in shard")

    originals = [_core_record(row, amendment=False) for row in original_rows]
    supports = [_core_record(row, amendment=False) for row in support_rows]
    amendments = [_core_record(row, amendment=True) for row in amendment_rows]
    roots = [*originals, *supports]
    if not roots:
        output.mkdir(parents=True, exist_ok=True)

    all_input = [*roots, *amendments]
    if any(row.timestamps.knowledge_at.year >= 2023 for row in all_input):
        raise ValueError("sealed OOS boundary violated by 2023+ canonical evidence")
    if any(
        row.timestamps.accepted_at is None
        or row.timestamps.knowledge_at != row.timestamps.accepted_at
        for row in all_input
    ):
        raise ValueError("historical knowledgeAt != acceptedAt")

    support_accessions = {
        row.source.accession_number for row in supports
    }
    exact_root: dict[tuple[str, str, str, int], CanonicalTransaction] = {}
    latest_revision: dict[tuple[str, str, str, int], str] = {}
    latest_record: dict[tuple[str, str, str, int], CanonicalTransaction] = {}
    event_at: dict[tuple[str, str, str, int], datetime | None] = {}
    meta_by_revision: dict[str, dict[str, Any]] = {}
    root_txid_by_key: dict[tuple[str, str, str, int], str] = {}

    for record in roots:
        accession = record.source.accession_number
        key = _row_key(record, accession)
        prior = exact_root.get(key)
        if prior is not None and prior.revision_id != record.revision_id:
            raise ValueError(f"duplicate root exact row identity: {key}")
        exact_root[key] = record
        latest_revision[key] = record.revision_id
        latest_record[key] = record
        root_txid_by_key[key] = record.transaction_id
        initial_event = (
            record.timestamps.knowledge_at
            if _qualified_side_record(record) is not None
            and accession not in support_accessions
            else None
        )
        event_at[key] = initial_event
        meta_by_revision[record.revision_id] = {
            "rootAccession": accession,
            "rootRowSequence": record.source.row_sequence,
            "rootTableType": record.security.table_type.value,
            "rootSupportingPredecessor": accession in support_accessions,
            "economicEventAt": initial_event.isoformat() if initial_event else None,
        }

    amendment_by_accession: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for record in amendments:
        amendment_by_accession[record.source.accession_number].append(record)

    missing_scope = sorted(set(amendment_by_accession) - set(scope_by_accession))
    if missing_scope:
        raise ValueError(f"hydrated amendments missing frozen scope: {missing_scope[:5]}")

    linked_amendments: list[CanonicalTransaction] = []
    linkage_rows: list[dict[str, Any]] = []
    quarantines: list[dict[str, Any]] = []
    transition_counts: dict[str, int] = defaultdict(int)

    ordered_accessions = sorted(
        amendment_by_accession,
        key=lambda accession: (
            min(r.timestamps.knowledge_at for r in amendment_by_accession[accession]),
            accession,
        ),
    )
    for accession in ordered_accessions:
        rows = amendment_by_accession[accession]
        scope = scope_by_accession[accession]
        frozen_status = str(scope["status"])
        root_accession = scope.get("resolvedRootPredecessorAccession")
        linked_rows = 0
        status = frozen_status
        reason = scope.get("reason")

        if frozen_status in LINKABLE_SCOPE and root_accession:
            for amendment in rows:
                key = _row_key(amendment, str(root_accession))
                root = exact_root.get(key)
                predecessor_revision = latest_revision.get(key)
                prior_record = latest_record.get(key)
                if root is None or predecessor_revision is None or prior_record is None:
                    quarantines.append(
                        {
                            "accession": accession,
                            "reasonCode": "AMENDMENT_ROW_NO_EXACT_PREDECESSOR",
                            "rootAccession": root_accession,
                            "ownerCik": amendment.reporting_owner.cik,
                            "tableType": amendment.security.table_type.value,
                            "rowSequence": amendment.source.row_sequence,
                        }
                    )
                    continue
                source = amendment.source.model_copy(
                    update={"amends_accession_number": None}
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
                prepared = amendment.model_copy(
                    update={"source": source, "lifecycle": lifecycle}
                )
                predicted = _predicted_revision_id(
                    root.transaction_id, predecessor_revision, prepared
                )
                prior_side = _qualified_side_record(prior_record)
                new_side = _qualified_side_record(prepared)
                current_event = event_at.get(key)
                if prior_side is None and new_side is not None:
                    current_event = prepared.timestamps.knowledge_at
                    transition_counts[f"{new_side}_ADDED"] += 1
                elif prior_side is not None and new_side is None:
                    transition_counts[f"{prior_side}_REMOVED"] += 1
                    current_event = None
                elif prior_side is not None and new_side is not None:
                    if prior_side != new_side:
                        transition_counts[f"{prior_side}_REMOVED"] += 1
                        transition_counts[f"{new_side}_ADDED"] += 1
                        current_event = prepared.timestamps.knowledge_at
                    elif _economic_signature(prior_record) != _economic_signature(prepared):
                        transition_counts[f"{new_side}_CORRECTED"] += 1
                latest_revision[key] = predicted
                latest_record[key] = prepared
                event_at[key] = current_event
                meta_by_revision[predicted] = {
                    "rootAccession": str(root_accession),
                    "rootRowSequence": root.source.row_sequence,
                    "rootTableType": root.security.table_type.value,
                    "rootSupportingPredecessor": str(root_accession) in support_accessions,
                    "economicEventAt": (
                        current_event.isoformat() if current_event else None
                    ),
                }
                linked_amendments.append(prepared)
                linked_rows += 1
            if linked_rows != len(rows):
                status = "PARTIALLY_LINKED_EXACT_ROWS"
                reason = "ONE_OR_MORE_ROWS_QUARANTINED"
            else:
                status = "LINKED_EXACT_ROWS"
        elif frozen_status.startswith(SCOPE_QUARANTINE_PREFIX):
            for amendment in rows:
                quarantines.append(
                    {
                        "accession": accession,
                        "reasonCode": frozen_status,
                        "scopeReason": reason,
                        "ownerCik": amendment.reporting_owner.cik,
                        "tableType": amendment.security.table_type.value,
                        "rowSequence": amendment.source.row_sequence,
                    }
                )
        elif frozen_status != "OUTSIDE_PS_ECONOMIC_SCOPE":
            raise ValueError(f"unexpected frozen scope status: {frozen_status}")

        linkage_rows.append(
            {
                "amendmentAccession": accession,
                "issuerCik": scope["issuerCik"],
                "frozenScopeStatus": frozen_status,
                "resolvedRootPredecessorAccession": root_accession,
                "status": status,
                "reason": reason,
                "canonicalRows": len(rows),
                "linkedRows": linked_rows,
                "acceptedAt": min(r.timestamps.knowledge_at for r in rows).isoformat(),
            }
        )

    resolution_input = [*roots, *linked_amendments]
    if resolution_input:
        point_in_time = max(r.timestamps.knowledge_at for r in resolution_input) + timedelta(seconds=1)
        resolved = resolve_amendments(resolution_input, as_of=point_in_time)
        revisions = list(resolved.all_revisions)
        resolver_quarantines = [
            q.model_dump(by_alias=True, mode="json") for q in resolved.quarantines
        ]
    else:
        revisions = []
        resolver_quarantines = []

    revision_positions = {row.revision_id: i for i, row in enumerate(revisions)}
    if len(revision_positions) != len(revisions):
        raise ValueError("duplicate revision IDs after reconciliation")

    zero_classifications: list[dict[str, Any]] = []
    zero_actions: list[dict[str, Any]] = []
    for xml_path, manifest, payload in _zero_evidence(
        evidence_root,
        shard_index=shard_index,
        shard_count=shard_count,
    ):
        accession = str(manifest["accession"])
        scope = scope_by_accession.get(accession)
        if scope is None or scope.get("status") != "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT":
            raise ValueError(f"zero-transaction evidence lacks frozen P/S-root scope: {accession}")
        root_accession = str(manifest["rootPredecessorAccession"])
        accepted = datetime.fromisoformat(str(manifest["acceptedAt"])).astimezone(UTC)
        if accepted.year >= 2023:
            raise ValueError("sealed OOS boundary violated by zero amendment")
        text = _xml_text(payload)
        category, reason_code = _classify_zero_text(text)
        item: dict[str, Any] = {
            "amendmentAccession": accession,
            "issuerCik": manifest["issuerCik"],
            "rootPredecessorAccession": root_accession,
            "acceptedAt": accepted.isoformat(),
            "classification": category,
            "reasonCode": reason_code,
            "actionApplied": False,
            "targetTransactionIds": [],
        }

        if category == "PS_LIFECYCLE_CHANGE_SUPPORTED":
            side, shares = _cancel_descriptor(text)
            owners = _owner_ciks(payload)
            candidates: list[tuple[tuple[str, str, str, int], CanonicalTransaction]] = []
            for key, root in exact_root.items():
                if key[0] != root_accession:
                    continue
                if owners and root.reporting_owner.cik not in owners:
                    continue
                root_side = _qualified_side_record(root)
                if root_side is None:
                    continue
                if side is not None and root_side != side:
                    continue
                if shares is not None and root.transaction.shares != shares:
                    continue
                candidates.append((key, root))
            groups: dict[tuple[str, int, str, str], list[tuple[Any, CanonicalTransaction]]] = defaultdict(list)
            for key, root in candidates:
                groups[
                    (
                        root.security.table_type.value,
                        root.source.row_sequence,
                        _qualified_side_record(root) or "",
                        str(root.transaction.shares),
                    )
                ].append((key, root))
            if len(groups) != 1:
                item["classification"] = "QUARANTINE_AMBIGUOUS_ZERO_TRANSACTION_AMENDMENT"
                item["reasonCode"] = "EXPLICIT_CANCELLATION_DID_NOT_MATCH_ONE_PS_ECONOMIC_ROW"
            else:
                group = next(iter(groups.values()))
                txids = sorted({root_txid_by_key[key] for key, _ in group})
                item["targetTransactionIds"] = txids
                item["cancelledSide"] = _qualified_side_record(group[0][1])
                item["cancelledShares"] = str(group[0][1].transaction.shares)
                zero_actions.append(
                    {
                        "accession": accession,
                        "acceptedAt": accepted,
                        "transactionIds": txids,
                        "classificationItem": item,
                    }
                )
        zero_classifications.append(item)

    for action in sorted(
        zero_actions, key=lambda row: (row["acceptedAt"], row["accession"])
    ):
        applied = 0
        for transaction_id in action["transactionIds"]:
            active = [
                row
                for row in revisions
                if row.transaction_id == transaction_id
                and row.lifecycle.valid_from <= action["acceptedAt"]
                and (
                    row.lifecycle.valid_to is None
                    or action["acceptedAt"] < row.lifecycle.valid_to
                )
            ]
            if len(active) != 1:
                continue
            current = active[0]
            lifecycle = Lifecycle(
                revision=current.lifecycle.revision,
                status=LifecycleStatus.VOID,
                is_amendment=current.lifecycle.is_amendment,
                supersedes_revision_id=current.lifecycle.supersedes_revision_id,
                valid_from=current.lifecycle.valid_from,
                valid_to=action["acceptedAt"],
            )
            revised = current.model_copy(update={"lifecycle": lifecycle})
            revisions[revision_positions[current.revision_id]] = revised
            side = _qualified_side_record(current)
            if side:
                transition_counts[f"{side}_REMOVED"] += 1
            applied += 1
        item = action["classificationItem"]
        if applied == len(action["transactionIds"]) and applied > 0:
            item["actionApplied"] = True
        else:
            item["classification"] = "QUARANTINE_AMBIGUOUS_ZERO_TRANSACTION_AMENDMENT"
            item["reasonCode"] = "CANCELLATION_TARGET_NOT_UNIQUELY_ACTIVE_AT_ACCEPTANCE"
            item["actionApplied"] = False

    for item in zero_classifications:
        if item["classification"] == "QUARANTINE_AMBIGUOUS_ZERO_TRANSACTION_AMENDMENT":
            quarantines.append(
                {
                    "accession": item["amendmentAccession"],
                    "reasonCode": item["reasonCode"],
                    "rootAccession": item["rootPredecessorAccession"],
                    "stage": "ZERO_TRANSACTION_SEMANTIC_CLASSIFICATION",
                }
            )

    dumps: list[dict[str, Any]] = []
    for row in revisions:
        value = row.canonical_dump()
        meta = meta_by_revision.get(row.revision_id)
        if meta is None:
            raise ValueError(f"missing reconciliation metadata for revision {row.revision_id}")
        side = _qualified_side_record(row)
        company_key = "|".join(
            (
                row.issuer.cik,
                str(meta["rootAccession"]),
                str(meta["rootTableType"]),
                str(meta["rootRowSequence"]),
            )
        )
        value["researchReconciliation"] = {
            **meta,
            "companyEconomicKey": company_key,
            "b3QualifiedSide": side,
        }
        dumps.append(value)

    end = datetime(2023, 1, 1, tzinfo=UTC)
    effective = [
        row
        for row in dumps
        if row["researchReconciliation"]["b3QualifiedSide"] is not None
        and datetime.fromisoformat(row["lifecycle"]["validFrom"]).astimezone(UTC) < end
        and (
            row["lifecycle"].get("validTo") is None
            or end <= datetime.fromisoformat(row["lifecycle"]["validTo"]).astimezone(UTC)
        )
        and row["lifecycle"]["status"] == LifecycleStatus.ACTIVE.value
    ]

    output.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output / "reconciled-ps-revisions.jsonl",
        sorted(
            dumps,
            key=lambda row: (
                row["issuer"]["cik"],
                row["transactionId"],
                row["lifecycle"]["validFrom"],
                row["revisionId"],
            ),
        ),
    )
    _write_jsonl(output / "effective-ps-end-2022.jsonl", effective)
    _write_jsonl(output / "amendment-linkage.jsonl", linkage_rows)
    _write_jsonl(output / "zero-transaction-classification.jsonl", zero_classifications)
    _write_jsonl(
        output / "quarantines.jsonl",
        sorted(
            [*quarantines, *resolver_quarantines],
            key=lambda row: (
                str(row.get("accession") or ""),
                str(row.get("reasonCode") or ""),
                str(row.get("ownerCik") or ""),
            ),
        ),
    )

    zero_counts: dict[str, int] = defaultdict(int)
    for row in zero_classifications:
        zero_counts[str(row["classification"])] += 1
    linkage_counts: dict[str, int] = defaultdict(int)
    for row in linkage_rows:
        linkage_counts[str(row["status"])] += 1

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 P/S deterministic amendment lifecycle reconciliation",
        "period": "2013-2022",
        "issuerShard": {
            "index": shard_index,
            "count": shard_count,
            "method": "sha256(issuer_cik)[0:8] mod shard_count",
        },
        "originalPsCanonicalRows": len(originals),
        "supportingPredecessorCanonicalRows": len(supports),
        "transactionBearingAmendmentCanonicalRows": len(amendments),
        "transactionBearingAmendmentFilingsHydrated": len(amendment_by_accession),
        "linkedAmendmentRows": len(linked_amendments),
        "linkageStatusCounts": dict(sorted(linkage_counts.items())),
        "zeroTransactionAmendmentsOnPsRoots": len(zero_classifications),
        "zeroTransactionClassificationCounts": dict(sorted(zero_counts.items())),
        "zeroLifecycleActionsApplied": sum(
            row["classification"] == "PS_LIFECYCLE_CHANGE_SUPPORTED"
            and row["actionApplied"] is True
            for row in zero_classifications
        ),
        "qualifiedBuyRowsAddedByAmendment": transition_counts["BUY_ADDED"],
        "qualifiedBuyRowsRemovedByAmendment": transition_counts["BUY_REMOVED"],
        "qualifiedBuyRowsCorrectedByAmendment": transition_counts["BUY_CORRECTED"],
        "qualifiedSaleRowsAddedByAmendment": transition_counts["SALE_ADDED"],
        "qualifiedSaleRowsRemovedByAmendment": transition_counts["SALE_REMOVED"],
        "qualifiedSaleRowsCorrectedByAmendment": transition_counts["SALE_CORRECTED"],
        "researchQuarantineRows": len(quarantines),
        "resolverQuarantineRows": len(resolver_quarantines),
        "reconciledRevisionRows": len(dumps),
        "effectiveQualifiedPsRowsAtEndOf2022": len(effective),
        "zeroTransactionSemanticReviewComplete": True,
        "supportingPredecessorHydrationComplete": True,
        "fullPsHistoryComplete": True,
        "amendmentsReconciledForPsUniverse": True,
        "b3Eligible": False,
        "b3DefinitionFrozen": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "marketDataJoined": False,
        "signalReady": False,
        "linkagePolicy": {
            "rootEvidence": "frozen B3 P/S amendment scope inventory",
            "rowEvidence": "exact root accession + owner CIK + table type + row sequence",
            "multiAmendmentChain": "immediate supersedesRevisionId",
            "fuzzyMatching": False,
            "ambiguousLinks": "quarantine and preserve prior effective state",
        },
        "zeroTransactionPolicy": {
            "explicitCancellation": "apply only when text and one exact P/S economic row agree",
            "explicitNonTransactionalCorrection": "no economic lifecycle change",
            "otherwise": "quarantine; never infer cancellation from empty transaction table",
        },
        "nextGate": "freeze B3 company-net-buying definition before any development performance",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--amendment-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--scope-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile_shard(
                original_root=args.original_root,
                amendment_root=args.amendment_root,
                evidence_root=args.evidence_root,
                scope_root=args.scope_root,
                output=args.output,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
