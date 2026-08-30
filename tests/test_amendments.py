"""Point-in-time Form 4 amendment-chain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction, LifecycleStatus
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml
from insider_turning_engine.normalization.amendments import resolve_amendments

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/test.xml"
RUN_ID = "run_test_amendments_20260830"


def parse_row(
    fixture: str,
    accession: str,
    timestamp: datetime,
    **extra_metadata: Any,
) -> CanonicalTransaction:
    metadata: dict[str, Any] = {
        "accession_number": accession,
        "source_url": SOURCE_URL,
        "accepted_at": timestamp,
        "observed_at": timestamp,
        "recorded_at": timestamp,
        "run_id": RUN_ID,
        **extra_metadata,
    }
    result = parse_sec_xml((FIXTURES / fixture).read_bytes(), metadata)
    assert not result.quarantines
    assert len(result.records) == 1
    return result.records[0]


def test_linked_amendment_replaces_original_at_the_effective_time() -> None:
    original = parse_row(
        "form4_original.xml",
        "0001234567-26-000010",
        datetime(2026, 8, 20, tzinfo=UTC),
    )
    amendment = parse_row(
        "form4_amendment.xml",
        "0001234567-26-000011",
        datetime(2026, 8, 22, tzinfo=UTC),
        amends_accession_number=original.source.accession_number,
    )

    before_correction = resolve_amendments(
        [original, amendment], as_of=datetime(2026, 8, 21, tzinfo=UTC)
    )
    assert [row.transaction.price_per_share for row in before_correction.records] == [
        Decimal("10.00")
    ]

    resolved = resolve_amendments([original, amendment], as_of=datetime(2026, 8, 30, tzinfo=UTC))
    assert not resolved.quarantines
    assert len(resolved.all_revisions) == 2
    superseded, corrected = resolved.all_revisions
    assert superseded.lifecycle.status is LifecycleStatus.SUPERSEDED
    assert superseded.lifecycle.valid_to == datetime(2026, 8, 22, tzinfo=UTC)
    assert corrected.lifecycle.status is LifecycleStatus.ACTIVE
    assert corrected.lifecycle.revision == 2
    assert corrected.lifecycle.supersedes_revision_id == superseded.revision_id
    assert corrected.transaction_id == original.transaction_id
    assert corrected.source.accession_number == amendment.source.accession_number
    assert [row.transaction.price_per_share for row in resolved.records] == [Decimal("10.50")]


def test_exact_duplicate_content_is_idempotent() -> None:
    original = parse_row(
        "form4_original.xml",
        "0001234567-26-000010",
        datetime(2026, 8, 20, tzinfo=UTC),
    )
    amendment = parse_row(
        "form4_amendment.xml",
        "0001234567-26-000011",
        datetime(2026, 8, 22, tzinfo=UTC),
        amends_accession_number=original.source.accession_number,
    )
    resolved = resolve_amendments(
        [original, original.model_copy(deep=True), amendment, amendment.model_copy(deep=True)],
        as_of=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert len(resolved.all_revisions) == 2
    assert len(resolved.records) == 1
    assert not resolved.quarantines


def test_unlinked_correction_is_quarantined_instead_of_double_counted() -> None:
    original = parse_row(
        "form4_original.xml",
        "0001234567-26-000010",
        datetime(2026, 8, 20, tzinfo=UTC),
    )
    amendment = parse_row(
        "form4_amendment.xml",
        "0001234567-26-000011",
        datetime(2026, 8, 22, tzinfo=UTC),
    )
    resolved = resolve_amendments([original, amendment], as_of=datetime(2026, 8, 30, tzinfo=UTC))
    assert [row.transaction.price_per_share for row in resolved.records] == [Decimal("10.00")]
    assert [quarantine.reason_code for quarantine in resolved.quarantines] == [
        "UNRESOLVED_AMENDMENT"
    ]


def test_explicit_revision_link_requires_the_same_owner_table_and_sequence() -> None:
    original = parse_row(
        "form4_original.xml",
        "0001234567-26-000010",
        datetime(2026, 8, 20, tzinfo=UTC),
    )
    amendment = parse_row(
        "form4_amendment.xml",
        "0001234567-26-000011",
        datetime(2026, 8, 22, tzinfo=UTC),
        supersedes_revision_id=original.revision_id,
    )
    resolved = resolve_amendments([original, amendment], as_of=datetime(2026, 8, 30, tzinfo=UTC))
    assert not resolved.quarantines
    assert resolved.records[0].lifecycle.supersedes_revision_id == original.revision_id


def test_multi_owner_rows_are_resolved_independently_by_owner_and_sequence() -> None:
    original_payload = (FIXTURES / "form4_direct_indirect_multi_owner.xml").read_bytes()
    amendment_payload = original_payload.replace(
        b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"
    ).replace(b"<value>12.00</value>", b"<value>12.50</value>")
    original_metadata: dict[str, Any] = {
        "accession_number": "0001234567-26-000020",
        "source_url": SOURCE_URL,
        "accepted_at": datetime(2026, 8, 20, tzinfo=UTC),
        "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
        "recorded_at": datetime(2026, 8, 20, tzinfo=UTC),
        "run_id": RUN_ID,
    }
    amended_metadata = {
        **original_metadata,
        "accession_number": "0001234567-26-000021",
        "accepted_at": datetime(2026, 8, 22, tzinfo=UTC),
        "observed_at": datetime(2026, 8, 22, tzinfo=UTC),
        "recorded_at": datetime(2026, 8, 22, tzinfo=UTC),
        "amends_accession_number": "0001234567-26-000020",
    }
    original_result = parse_sec_xml(original_payload, original_metadata)
    amendment_result = parse_sec_xml(amendment_payload, amended_metadata)
    assert len(original_result.records) == len(amendment_result.records) == 4

    resolved = resolve_amendments(
        [*original_result.records, *amendment_result.records],
        as_of=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert not resolved.quarantines
    assert len(resolved.records) == 4
    assert {row.reporting_owner.cik for row in resolved.records} == {"0001999105", "0001999106"}
    assert {row.transaction.ownership_nature for row in resolved.records} == {"D", "I"}
    assert {row.transaction.price_per_share for row in resolved.records} == {Decimal("12.50")}
