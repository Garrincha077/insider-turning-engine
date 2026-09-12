"""Nullable derivative quantities preserve reported amounts and legacy bytes."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from insider_turning_engine.domain.models import CanonicalTransaction, ValueDerivation
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml

FIXTURES = Path(__file__).parent / "fixtures"
METADATA = {
    "accession_number": "0001234567-26-000001",
    "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
    "accepted_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
    "observed_at": datetime(2026, 8, 30, 10, tzinfo=UTC),
    "run_id": "run_test_parser_20260830",
}
SCHEMA = json.loads(
    (Path(__file__).parents[1] / "schemas/canonical-transaction.schema.json").read_text()
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
# Recorded before the quantity extension, with fixed metadata and LF XML input.
LEGACY_GOLDENS = {
    "form4_10b5_1_explicit.xml": "d317df83763efbc1e1ddb076867802b5e5741e098250aa748a2f7042f3d1ce7b",
    "form4_10b5_1_footnote.xml": "a025de0759bd8dcb783148bde8f1a303cc2175cc1ebb0009d8adf9f728abe2d9",
    "form4_amendment.xml": "155626e6f1b2175168b4b73afa5ab8a0b0497483f2ba9a7ec73fe807d29b8bec",
    "form4_derivative.xml": "ee3aaa8ea633e6bd442e5bd3c9c109e296608de991b60e590b9202e30afc31d4",
    "form4_direct_indirect_multi_owner.xml": (
        "9849c95431ea9deb64187087251ef3189e25e0e598c0a85aea2c11e539a6b911"
    ),
    "form4_missing_price.xml": "6f3fc7e752990ddf9abc7e55638f042e6f45ebd7f995a17e6d410aec45d6866e",
    "form4_non_derivative.xml": "f61797615964d30c22e0f89e5dec8c32242d6e17046a51af85b90f4b41b45582",
    "form4_original.xml": "93897dc8ff6fe20e7f788b980ab2ff306de3b38a2a26b53a5ef09ffd010136b1",
    "form4_special_codes.xml": "28c313f68b391a3cfb3cb221424e590901ebc2b8be7eb970e3ea2ab33b12234e",
}


def xml(name: str = "form4_derivative_amount.xml") -> str:
    # Normalize checkout line endings before hashing source-dependent identities.
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name,expected", LEGACY_GOLDENS.items())
def test_existing_canonical_records_remain_byte_identical(name: str, expected: str) -> None:
    result = parse_sec_xml(xml(name).encode(), METADATA)
    assert result.records and not result.quarantines
    dumps = [row.canonical_dump() for row in result.records]
    content = json.dumps(dumps, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(content).hexdigest() == expected
    for value in dumps:
        assert value["schemaVersion"] == "1.0.0"
        VALIDATOR.validate(value)
        assert CanonicalTransaction.model_validate(value).canonical_dump() == value


def test_amount_disposal_has_no_fabricated_quantity_and_stable_provenance() -> None:
    payload = xml().encode()
    result = parse_sec_xml(payload, METADATA)
    assert not result.quarantines and len(result.records) == 2
    note, preferred = result.records
    assert note.schema_version == "1.1.0"
    assert note.transaction.shares is None
    assert note.transaction.value == Decimal("35000")
    assert note.transaction.value_derivation is ValueDerivation.SOURCE
    assert note.transaction.price_per_share == 0
    assert note.transaction.post_transaction_shares is None
    assert (note.transaction.code, note.transaction.acquired_disposed) == ("M", "D")
    assert preferred.schema_version == "1.0.0"
    assert preferred.transaction.shares == 13216
    assert preferred.transaction.value == 0
    assert preferred.transaction.value_derivation is ValueDerivation.SHARES_TIMES_PRICE
    for sequence, row in enumerate(result.records, 1):
        material = f"0001234567-26-000001|0001999103|DERIVATIVE|{sequence}"
        assert row.transaction_id == "txn_" + hashlib.sha256(material.encode()).hexdigest()
        assert row.source.source_row_key == f"DERIVATIVE:{sequence}:0001999103"
        assert row.source.content_hash == "sha256:" + hashlib.sha256(payload).hexdigest()
        assert row.timestamps.accepted_at == METADATA["accepted_at"]
        assert row.timestamps.observed_at == METADATA["observed_at"]
        assert row.timestamps.recorded_at == METADATA["observed_at"]
        assert row.timestamps.knowledge_at == METADATA["observed_at"]
        assert row.run_id == METADATA["run_id"]
        value = row.canonical_dump()
        VALIDATOR.validate(value)
        assert CanonicalTransaction.model_validate(value).canonical_dump() == value
    assert [r.canonical_dump() for r in parse_sec_xml(payload, METADATA).records] == [
        row.canonical_dump() for row in result.records
    ]


@pytest.mark.parametrize("quantity", ["", " ", "bad", "-1", "NaN", "Infinity", "-Infinity"])
def test_present_invalid_shares_cannot_fall_back_to_total_value(quantity: str) -> None:
    payload = xml().replace(
        "<transactionTotalValue>",
        f"<transactionShares><value>{quantity}</value></transactionShares><transactionTotalValue>",
        1,
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert len(result.quarantines) == len(result.records) == 1
    assert result.quarantines[0].reason_code == "INVALID_TRANSACTION"
    assert result.quarantines[0].source_row_key == "DERIVATIVE:1:0001999103"
    assert result.records[0].source.row_sequence == 2


def test_empty_shares_element_is_not_absent() -> None:
    payload = xml().replace(
        "<transactionTotalValue>", "<transactionShares/><transactionTotalValue>", 1
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert len(result.quarantines) == 1


@pytest.mark.parametrize("amount", ["", " ", "bad", "-1", "NaN", "Infinity", "-Infinity"])
def test_missing_quantity_requires_valid_reported_amount(amount: str) -> None:
    payload = xml().replace("<value>35000</value>", f"<value>{amount}</value>")
    result = parse_sec_xml(payload.encode(), METADATA)
    assert len(result.quarantines) == len(result.records) == 1
    assert result.quarantines[0].reason_code == "INVALID_TRANSACTION"


def test_absent_quantity_and_amount_remains_quarantined() -> None:
    payload = xml().replace(
        "<transactionTotalValue><value>35000</value></transactionTotalValue>", ""
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert len(result.quarantines) == 1


def test_source_zero_and_missing_price_are_preserved_truthfully() -> None:
    payload = xml().replace("<value>35000</value>", "<value>0</value>").replace(
        "<transactionPricePerShare><value>0</value></transactionPricePerShare>", "", 1
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert not result.quarantines
    row = result.records[0]
    assert row.transaction.shares is None and row.transaction.price_per_share is None
    assert row.transaction.value == 0 and row.transaction.value_derivation is ValueDerivation.SOURCE
    assert row.quality.flags[0].code == "MISSING_PRICE"
    assert "value is unavailable" not in row.quality.flags[0].message
    VALIDATOR.validate(row.canonical_dump())


def test_non_derivative_requires_shares_even_with_reported_amount() -> None:
    payload = xml().replace("derivativeTable", "nonDerivativeTable").replace(
        "derivativeTransaction", "nonDerivativeTransaction"
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert len(result.quarantines) == 1
    assert result.quarantines[0].source_row_key == "NON_DERIVATIVE:1:0001999103"


@pytest.mark.parametrize("name", ["form4_non_derivative.xml", "form4_derivative.xml"])
def test_reported_amount_does_not_change_existing_share_valuation(name: str) -> None:
    original = parse_sec_xml(xml(name).encode(), METADATA)
    payload = xml(name).replace(
        "<transactionAmounts>",
        "<transactionAmounts><transactionTotalValue><value>999999</value></transactionTotalValue>",
    )
    result = parse_sec_xml(payload.encode(), METADATA)
    assert not result.quarantines
    assert [row.transaction.model_dump() for row in result.records] == [
        row.transaction.model_dump() for row in original.records
    ]
    assert all(row.schema_version == "1.0.0" for row in result.records)


@pytest.mark.parametrize("section,field,value", [
    (None, "schemaVersion", "1.0.0"),
    (None, "schemaVersion", "1.2.0"),
    ("security", "tableType", "NON_DERIVATIVE"),
    ("transaction", "shares", "0"),
    ("transaction", "value", None),
    ("transaction", "value", "-1"),
    ("transaction", "valueDerivation", "SHARES_TIMES_PRICE"),
    ("transaction", "valueDerivation", "UNAVAILABLE"),
])
def test_model_and_schema_reject_invalid_quantity_contracts(
    section: str | None, field: str, value: Any,
) -> None:
    payload = deepcopy(parse_sec_xml(xml().encode(), METADATA).records[0].canonical_dump())
    target = payload if section is None else payload[section]
    assert isinstance(target, dict)
    target[field] = value
    with pytest.raises(ValidationError):
        CanonicalTransaction.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        VALIDATOR.validate(payload)


def test_nullable_shares_field_is_still_required() -> None:
    payload = parse_sec_xml(xml().encode(), METADATA).records[0].canonical_dump()
    transaction = payload["transaction"]
    assert isinstance(transaction, dict)
    del transaction["shares"]
    with pytest.raises(ValidationError):
        CanonicalTransaction.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        VALIDATOR.validate(payload)
