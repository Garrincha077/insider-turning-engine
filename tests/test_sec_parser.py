"""Contract tests for the deterministic SEC ownership XML parser."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from insider_turning_engine.domain.models import (
    InsiderRole,
    ParseResult,
    TransactionClassification,
    TriState,
    ValueDerivation,
)
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml

FIXTURES = Path(__file__).parent / "fixtures"
METADATA = {
    "accession_number": "0001234567-26-000001",
    "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
    "accepted_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
    "observed_at": datetime(2026, 8, 30, 10, tzinfo=UTC),
    "run_id": "run_test_parser_20260830",
}


def parse(name: str) -> ParseResult:
    return parse_sec_xml((FIXTURES / name).read_bytes(), METADATA)


def test_non_derivative_rows_are_normalized_and_stable() -> None:
    first = parse("form4_non_derivative.xml")
    second = parse("form4_non_derivative.xml")
    assert len(first.records) == 2
    assert not first.quarantines
    assert [row.transaction.code for row in first.records] == ["P", "S"]
    assert (
        first.records[0].transaction_classification
        is TransactionClassification.OPEN_MARKET_PURCHASE
    )
    assert first.records[1].transaction_classification is TransactionClassification.OPEN_MARKET_SALE
    assert first.records[0].transaction.value == 1000
    assert first.records[0].transaction_id == second.records[0].transaction_id
    assert first.records[0].source.content_hash.startswith("sha256:")
    expected = hashlib.sha256(b"0001234567-26-000001|0001999101|NON_DERIVATIVE|1").hexdigest()
    assert first.records[0].transaction_id == f"txn_{expected}"


def test_canonical_serialization_has_only_canonical_schema_fields() -> None:
    row = parse("form4_non_derivative.xml").records[0]
    serialized = row.model_dump(by_alias=True, mode="json")
    assert set(serialized) == {
        "schemaVersion",
        "runId",
        "ingestedAt",
        "transactionId",
        "revisionId",
        "issuer",
        "reportingOwner",
        "relationship",
        "security",
        "transaction",
        "source",
        "timestamps",
        "lifecycle",
        "quality",
    }
    assert serialized["ingestedAt"] == serialized["timestamps"]["recordedAt"]
    assert set(serialized["source"]) == {
        "provider",
        "providerRecordId",
        "accessionNumber",
        "formType",
        "rowSequence",
        "sourceRowKey",
        "contentHash",
        "sourceUrl",
    }
    assert "normalizedRoles" not in serialized["relationship"]


def test_special_and_derivative_codes() -> None:
    special = parse("form4_special_codes.xml")
    assert [row.transaction_classification for row in special.records] == [
        TransactionClassification.AWARD,
        TransactionClassification.GIFT,
        TransactionClassification.TAX_WITHHOLDING,
        TransactionClassification.TRANSFER,
    ]
    derivative = parse("form4_derivative.xml")
    row = derivative.records[0]
    assert row.security.table_type.value == "DERIVATIVE"
    assert row.security.underlying_title == "Common Stock"
    assert row.transaction_classification is TransactionClassification.OPTION_EXERCISE


def test_missing_price_is_warning_and_not_zero() -> None:
    result = parse("form4_missing_price.xml")
    row = result.records[0]
    assert row.transaction.price_per_share is None
    assert row.transaction.value is None
    assert row.transaction.value_derivation is ValueDerivation.UNAVAILABLE
    assert row.quality.status.value == "WARN"
    assert row.quality.flags[0].code == "MISSING_PRICE"


def test_owners_and_10b5_1_tri_state() -> None:
    result = parse("form4_direct_indirect_multi_owner.xml")
    assert len(result.records) == 4
    assert {row.reporting_owner.cik for row in result.records} == {"0001999105", "0001999106"}
    assert {row.transaction.ownership_nature for row in result.records} == {"D", "I"}
    assert InsiderRole.DIRECTOR in result.records[0].relationship.normalized_roles
    assert InsiderRole.TEN_PERCENT_OWNER in result.records[-1].relationship.normalized_roles
    assert parse("form4_10b5_1_explicit.xml").records[0].ten_b5_1 is TriState.TRUE
    assert parse("form4_10b5_1_footnote.xml").records[0].ten_b5_1 is TriState.TRUE
    assert parse("form4_original.xml").records[0].ten_b5_1 is TriState.FALSE


def test_officer_titles_normalize_material_roles() -> None:
    payload = (
        (FIXTURES / "form4_derivative.xml")
        .read_bytes()
        .replace(
            b"Example Treasurer",
            b"Chairman, Chief Executive Officer (CEO), and CFO",
        )
    )
    row = parse_sec_xml(payload, METADATA).records[0]
    assert {
        InsiderRole.CEO,
        InsiderRole.CFO,
        InsiderRole.CHAIRMAN,
        InsiderRole.OFFICER,
    }.issubset(row.relationship.normalized_roles)


def test_amendment_is_recorded_without_deduplication() -> None:
    row = parse("form4_amendment.xml").records[0]
    assert row.lifecycle.is_amendment is True
    assert row.transaction.price_per_share == 10.50


def test_parser_retains_explicit_amendment_link_for_row_level_resolution() -> None:
    predecessor = "txr_" + "a" * 64
    result = parse_sec_xml(
        (FIXTURES / "form4_amendment.xml").read_bytes(),
        {
            **METADATA,
            "amends_accession_number": "0001234567-26-000099",
            "supersedes_revision_id": predecessor,
        },
    )
    row = result.records[0]
    assert row.source.amends_accession_number == "0001234567-26-000099"
    assert row.lifecycle.supersedes_revision_id == predecessor


def test_missing_owner_cik_is_quarantined() -> None:
    payload = (
        (FIXTURES / "form4_non_derivative.xml")
        .read_bytes()
        .replace(
            b"<rptOwnerCik>0001999101</rptOwnerCik>",
            b"<rptOwnerCik></rptOwnerCik>",
        )
    )
    result = parse_sec_xml(payload, METADATA)
    assert not result.records
    assert result.quarantines[0].reason_code == "MISSING_OWNER_CIK"


def test_malformed_xml_is_quarantined() -> None:
    result = parse_sec_xml(b"<ownershipDocument>", METADATA)
    assert not result.records
    assert result.quarantines[0].reason_code == "INVALID_XML"


def test_excessive_xml_nesting_is_quarantined() -> None:
    payload = b"<ownershipDocument>" + (b"<x>" * 100) + (b"</x>" * 100) + b"</ownershipDocument>"
    result = parse_sec_xml(payload, METADATA)
    assert not result.records
    assert result.quarantines[0].reason_code == "XML_NESTING_LIMIT"
