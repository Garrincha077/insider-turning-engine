"""Deterministic, point-in-time resolution of SEC Form 4 amendment chains.

The SEC parser emits immutable observations.  This module is the only place
where a Form 4/A may replace a prior economic revision: it requires an exact
row identity and leaves an unlinked correction in quarantine rather than
silently counting both rows.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from insider_turning_engine.domain.models import (
    CanonicalTransaction,
    Lifecycle,
    LifecycleStatus,
    QuarantineRecord,
)

_RowIdentity = tuple[str, str, str, int]


@dataclass(frozen=True, slots=True)
class AmendmentResolution:
    """All eligible revisions, their effective rows, and safe rejections."""

    all_revisions: tuple[CanonicalTransaction, ...]
    effective_records: tuple[CanonicalTransaction, ...]
    quarantines: tuple[QuarantineRecord, ...]

    @property
    def records(self) -> tuple[CanonicalTransaction, ...]:
        """Compatibility alias for callers interested in active rows only."""

        return self.effective_records


def _as_utc(as_of: datetime) -> datetime:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return as_of.astimezone(UTC)


def _row_identity(record: CanonicalTransaction, accession: str | None = None) -> _RowIdentity:
    """The exact SEC row key used for amendment matching, never fuzzy facts."""

    return (
        accession or record.source.accession_number,
        record.reporting_owner.cik,
        record.security.table_type.value,
        record.source.row_sequence,
    )


def _content_identity(record: CanonicalTransaction) -> tuple[str, str, str, int, str]:
    """Identity for idempotent duplicate delivery of an immutable SEC row."""

    accession, owner_cik, table_type, row_sequence = _row_identity(record)
    return accession, owner_cik, table_type, row_sequence, record.source.content_hash


def _order(record: CanonicalTransaction) -> tuple[datetime, datetime, str, str]:
    """Stable ordering independent of fetch order when timestamps tie."""

    return (
        record.timestamps.knowledge_at,
        record.timestamps.recorded_at,
        record.source.accession_number,
        record.revision_id,
    )


def _is_amendment(record: CanonicalTransaction) -> bool:
    return record.lifecycle.is_amendment or record.source.form_type.endswith("/A")


def _quarantine(
    record: CanonicalTransaction,
    reason_code: str,
    message: str,
) -> QuarantineRecord:
    return QuarantineRecord(
        reason_code=reason_code,
        message=message,
        source_row_key=record.source.source_row_key,
        locator=(
            f"{record.source.accession_number}|{record.reporting_owner.cik}|"
            f"{record.security.table_type.value}|{record.source.row_sequence}"
        ),
        run_id=record.run_id,
    )


def _revision_id(predecessor: CanonicalTransaction, amendment: CanonicalTransaction) -> str:
    """Create a deterministic revision identifier for a resolved correction."""

    material = "|".join(
        (
            predecessor.transaction_id,
            predecessor.revision_id,
            amendment.source.accession_number,
            amendment.source.content_hash,
        )
    )
    return "txr_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _same_row(
    predecessor: CanonicalTransaction,
    amendment: CanonicalTransaction,
) -> bool:
    return (
        predecessor.issuer.cik == amendment.issuer.cik
        and _row_identity(predecessor)[1:] == _row_identity(amendment)[1:]
    )


def _is_effective(record: CanonicalTransaction, as_of: datetime) -> bool:
    valid_to = record.lifecycle.valid_to
    return (
        record.lifecycle.status is LifecycleStatus.ACTIVE
        and record.timestamps.knowledge_at <= as_of
        and record.lifecycle.valid_from <= as_of
        and (valid_to is None or as_of < valid_to)
    )


def resolve_amendments(
    records: Iterable[CanonicalTransaction],
    *,
    as_of: datetime,
) -> AmendmentResolution:
    """Resolve eligible Form 4 revisions and select the effective view.

    A Form 4/A may target a predecessor explicitly by revision ID, by a
    supplied predecessor accession, or (only for the same accession) by the
    exact ``accession|owner CIK|table type|row sequence`` row key.  Differing
    accessions without an explicit link are deliberately quarantined: matching
    them on price, date, or share count would be a non-auditable fuzzy merge.
    """

    point_in_time = _as_utc(as_of)
    unique: dict[tuple[str, str, str, int, str], CanonicalTransaction] = {}
    for record in sorted(records, key=_order):
        if record.timestamps.knowledge_at > point_in_time:
            continue
        unique.setdefault(_content_identity(record), record)

    revisions: list[CanonicalTransaction] = []
    by_revision_id: dict[str, CanonicalTransaction] = {}
    source_rows: dict[_RowIdentity, list[CanonicalTransaction]] = {}
    positions: dict[str, int] = {}
    successor_by_revision: dict[str, str] = {}
    quarantines: list[QuarantineRecord] = []

    for record in sorted(unique.values(), key=_order):
        if not _is_amendment(record):
            positions[record.revision_id] = len(revisions)
            revisions.append(record)
            by_revision_id[record.revision_id] = record
            source_rows.setdefault(_row_identity(record), []).append(record)
            continue

        predecessor: CanonicalTransaction | None = None
        explicit_revision = record.lifecycle.supersedes_revision_id
        explicit_accession = record.source.amends_accession_number
        if explicit_revision is not None:
            predecessor = by_revision_id.get(explicit_revision)
            if predecessor is None:
                quarantines.append(
                    _quarantine(
                        record,
                        "UNRESOLVED_AMENDMENT",
                        "the declared predecessor revision is not known as of the requested time",
                    )
                )
                continue
            if not _same_row(predecessor, record):
                quarantines.append(
                    _quarantine(
                        record,
                        "AMENDMENT_IDENTITY_MISMATCH",
                        "the declared predecessor does not match issuer, owner, table, "
                        "and row sequence",
                    )
                )
                continue
            if (
                explicit_accession is not None
                and predecessor.source.accession_number != explicit_accession
            ):
                quarantines.append(
                    _quarantine(
                        record,
                        "AMENDMENT_LINK_CONFLICT",
                        "declared predecessor revision and accession identify different "
                        "source rows",
                    )
                )
                continue
        else:
            predecessor_accession = explicit_accession or record.source.accession_number
            candidates = source_rows.get(_row_identity(record, predecessor_accession), [])
            candidates = [candidate for candidate in candidates if _same_row(candidate, record)]
            if len(candidates) == 1:
                predecessor = candidates[0]
            elif not candidates:
                quarantines.append(
                    _quarantine(
                        record,
                        "UNRESOLVED_AMENDMENT",
                        "no exact predecessor row is known; correction was excluded from "
                        "aggregates",
                    )
                )
                continue
            else:
                quarantines.append(
                    _quarantine(
                        record,
                        "AMBIGUOUS_AMENDMENT",
                        "multiple exact predecessor revisions require an explicit supersedes link",
                    )
                )
                continue

        assert predecessor is not None
        if predecessor.revision_id in successor_by_revision:
            quarantines.append(
                _quarantine(
                    record,
                    "AMENDMENT_CHAIN_FORK",
                    "the predecessor already has a resolved successor; correction was excluded",
                )
            )
            continue

        valid_from = max(record.lifecycle.valid_from, record.timestamps.knowledge_at)
        if valid_from < predecessor.lifecycle.valid_from:
            quarantines.append(
                _quarantine(
                    record,
                    "AMENDMENT_TIME_CONFLICT",
                    "correction becomes known before its predecessor is valid",
                )
            )
            continue

        superseded_lifecycle = Lifecycle(
            revision=predecessor.lifecycle.revision,
            status=LifecycleStatus.SUPERSEDED,
            is_amendment=predecessor.lifecycle.is_amendment,
            supersedes_revision_id=predecessor.lifecycle.supersedes_revision_id,
            valid_from=predecessor.lifecycle.valid_from,
            valid_to=valid_from,
        )
        superseded = predecessor.model_copy(update={"lifecycle": superseded_lifecycle})
        predecessor_position = positions[predecessor.revision_id]
        revisions[predecessor_position] = superseded
        by_revision_id[predecessor.revision_id] = superseded

        corrected_lifecycle = Lifecycle(
            revision=predecessor.lifecycle.revision + 1,
            status=LifecycleStatus.ACTIVE,
            is_amendment=True,
            supersedes_revision_id=predecessor.revision_id,
            valid_from=valid_from,
        )
        corrected = record.model_copy(
            update={
                "transaction_id": predecessor.transaction_id,
                "revision_id": _revision_id(predecessor, record),
                "lifecycle": corrected_lifecycle,
            }
        )
        positions[corrected.revision_id] = len(revisions)
        revisions.append(corrected)
        by_revision_id[corrected.revision_id] = corrected
        source_rows.setdefault(_row_identity(corrected), []).append(corrected)
        successor_by_revision[predecessor.revision_id] = corrected.revision_id

    effective_by_transaction: dict[str, CanonicalTransaction] = {}
    for record in revisions:
        if not _is_effective(record, point_in_time):
            continue
        current = effective_by_transaction.get(record.transaction_id)
        if current is None or _order(record) > _order(current):
            effective_by_transaction[record.transaction_id] = record

    return AmendmentResolution(
        all_revisions=tuple(revisions),
        effective_records=tuple(
            effective_by_transaction[transaction_id]
            for transaction_id in sorted(effective_by_transaction)
        ),
        quarantines=tuple(quarantines),
    )


def effective_view(
    records: Iterable[CanonicalTransaction],
    *,
    as_of: datetime,
) -> AmendmentResolution:
    """Alias for :func:`resolve_amendments` used by read-model callers."""

    return resolve_amendments(records, as_of=as_of)


__all__ = ["AmendmentResolution", "effective_view", "resolve_amendments"]
