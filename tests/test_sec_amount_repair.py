"""Explicit derivative replay preserves legacy evidence and repair availability."""

import copy
import gzip
import hashlib
import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_sec_checkpoints import FakeReleases

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.ingestion.sec.checkpoint import (
    decode_checkpoint,
    encode_checkpoint,
    restore_checkpoint,
    validate_checkpoint,
)
from insider_turning_engine.ingestion.sec.daily_history import (
    LEGACY_PARSER_VERSION,
    PARSER_VERSION,
    _load_filing,
)
from insider_turning_engine.ingestion.sec.daily_index import (
    SECDailyIndexSource,
    daily_index_url,
    parse_complete_submission,
    parse_daily_master_index,
)
from insider_turning_engine.ingestion.sec.historical import RequestPacer
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing
from insider_turning_engine.ingestion.sec.repair_amounts import repair_checkpoint

DAY = date(2026, 8, 31)
ACCESSION = "0001234567-26-000001"
ROW_KEY = "DERIVATIVE:1:0001999103"
OBSERVED = datetime(2026, 9, 2, 10, tzinfo=UTC)
REPAIRED = datetime(2026, 9, 3, 11, tzinfo=UTC)
INDEX = (
    "CIK|Company Name|Form Type|Date Filed|Filename\n----\n"
    f"1234567|Owner|4|2026-08-31|edgar/data/1234567/{ACCESSION}.txt\n"
).encode()
XML = (Path(__file__).parent / "fixtures/form4_derivative_amount.xml").read_text().encode()


def submission(xml: bytes = XML, *, stamp: str = "20260831160100") -> bytes:
    header = (
        f"<ACCEPTANCE-DATETIME>{stamp}\n<ACCESSION-NUMBER>{ACCESSION}\n"
        "<DOCUMENT>\n<TYPE>4\n<FILENAME>ownership.xml\n<TEXT>\n"
    ).encode()
    return header + xml + b"\n</TEXT>\n</DOCUMENT>"


def legacy_checkpoint(xml: bytes = XML) -> dict[str, Any]:
    index_hash = "sha256:" + hashlib.sha256(INDEX).hexdigest()
    raw = parse_complete_submission(
        submission(xml), parse_daily_master_index(INDEX)[0], retrieved_at=OBSERVED,
        index_url=daily_index_url(DAY), index_hash=index_hash,
    )
    parsed = parse_sec_filing(raw.payload, {
        "accession_number": ACCESSION, "source_url": raw.source_url,
        "accepted_at": raw.accepted_at, "observed_at": OBSERVED, "recorded_at": OBSERVED,
        "run_id": "run_original_amount_fixture_001",
    })
    # Reconstruct the old parser's valid second row and first-row quarantine.
    rows = [row.canonical_dump() for row in parsed.records if row.source.row_sequence == 2]
    assert len(rows) == 1 and rows[0]["schemaVersion"] == "1.0.0"
    filing = {
        "schemaVersion": "1.0.0", "source": "sec-daily-index",
        "parserVersion": LEGACY_PARSER_VERSION, "accession": ACCESSION,
        "indexHash": index_hash, "provenance": dict(raw.provenance), "records": rows,
        "quarantines": [{"reason_code": "INVALID_TRANSACTION",
                         "message": "Inspect original SEC filing", "source_row_key": ROW_KEY}],
    }
    return validate_checkpoint({
        "schemaVersion": "1.0.0", "day": DAY.isoformat(),
        "parserVersion": LEGACY_PARSER_VERSION, "indexHash": index_hash,
        "discoveredAccessions": [ACCESSION], "filings": [filing], "failures": [],
        "signalReady": False,
    }, day=DAY)


def provider(
    calls: list[str], *, xml: bytes = XML, index: bytes = INDEX,
    stamp: str = "20260831160100",
) -> SECDailyIndexSource:
    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        body = index if request.url.path.endswith(".idx") else submission(xml, stamp=stamp)
        return httpx.Response(200, content=body)

    return SECDailyIndexSource(
        "ITE test@example.com", client=httpx.Client(transport=httpx.MockTransport(respond)),
        clock=lambda: REPAIRED + timedelta(days=1), max_attempts=1, sleeper=lambda _: None,
        pacer=RequestPacer(sleeper=lambda _: None),
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def test_legacy_checkpoint_bytes_and_hash_are_readable_without_relabeling(tmp_path: Path) -> None:
    original = legacy_checkpoint()
    # Encode using the legacy wire recipe independently of the current encoder.
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressor:
        compressor.write(canonical_bytes(original))
    compressed = stream.getvalue()
    name = "checkpoint-" + hashlib.sha256(compressed).hexdigest() + ".json.gz"
    assert encode_checkpoint(original) == (name, compressed)
    restored = decode_checkpoint(name, compressed, day=DAY)
    assert restored == original and encode_checkpoint(restored) == (name, compressed)
    root = tmp_path / "legacy"
    restore_checkpoint(restored, day=DAY, root=root)
    filing = _load_filing(root / "filings" / f"{ACCESSION}.json", ACCESSION,
                          original["indexHash"], retry_quarantined=False)
    assert filing == original["filings"][0]
    assert filing["parserVersion"] == LEGACY_PARSER_VERSION
    assert not list(root.rglob("*.sha256")) and not list(root.rglob("*.cursor"))


def test_repair_is_deterministic_immutable_and_known_only_at_repair() -> None:
    original = legacy_checkpoint()
    before = copy.deepcopy(original)
    old_encoding = encode_checkpoint(original)
    unchanged = canonical_bytes(original["filings"][0]["records"][0])
    calls: list[str] = []
    source = provider(calls)
    try:
        repaired = repair_checkpoint(original, source, repaired_at=REPAIRED)
        repeated = repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()
    assert repeated == repaired and encode_checkpoint(repeated) == encode_checkpoint(repaired)
    assert original == before and encode_checkpoint(original) == old_encoding
    assert sum(path.endswith(".txt") for path in calls) == 2
    assert repaired["parserVersion"] == PARSER_VERSION
    assert repaired["signalReady"] is False and repaired["failures"] == []
    filing = repaired["filings"][0]
    assert filing["quarantines"] == [] and filing["parserVersion"] == PARSER_VERSION
    rows = {row["source"]["sourceRowKey"]: row for row in filing["records"]}
    assert canonical_bytes(rows["DERIVATIVE:2:0001999103"]) == unchanged
    row = CanonicalTransaction.model_validate(rows[ROW_KEY])
    prior = CanonicalTransaction.model_validate(original["filings"][0]["records"][0])
    assert row.schema_version == "1.1.0" and row.transaction.shares is None
    assert row.transaction.value == 35000 and row.transaction.price_per_share == 0
    assert row.transaction.value_derivation.value == "SOURCE"
    assert row.timestamps.accepted_at == prior.timestamps.accepted_at
    assert row.source.content_hash == prior.source.content_hash
    assert row.timestamps.observed_at == row.timestamps.recorded_at == REPAIRED
    assert row.timestamps.knowledge_at == row.ingested_at == row.lifecycle.valid_from == REPAIRED
    assert row.timestamps.knowledge_at > prior.timestamps.knowledge_at
    assert row.run_id.startswith("run_repair_") and row.run_id != prior.run_id
    assert filing["provenance"] == original["filings"][0]["provenance"]
    assert filing["repair"] == {
        "previousFilingHash": hashlib.sha256(canonical_bytes(original["filings"][0])).hexdigest(),
        "previousCheckpointHash": hashlib.sha256(old_encoding[1]).hexdigest(),
        "previousParserVersion": LEGACY_PARSER_VERSION, "replayedAt": REPAIRED.isoformat(),
        "previousRecordCount": 1, "resolvedRowKeys": [ROW_KEY],
    }
    assert decode_checkpoint(*encode_checkpoint(repaired), day=DAY) == repaired


def test_already_repaired_checkpoint_is_idempotent_without_source_requests() -> None:
    calls: list[str] = []
    source = provider(calls)
    try:
        repaired = repair_checkpoint(legacy_checkpoint(), source, repaired_at=REPAIRED)
        calls.clear()
        repeated = repair_checkpoint(repaired, source, repaired_at=REPAIRED + timedelta(days=2))
    finally:
        source.close()
    assert repeated == repaired and repeated is not repaired
    assert encode_checkpoint(repeated) == encode_checkpoint(repaired) and not calls


@pytest.mark.parametrize("kind", ["index", "submission", "acceptance"])
def test_changed_source_evidence_rejects_repair_without_mutation(kind: str) -> None:
    original = legacy_checkpoint()
    before = encode_checkpoint(original)
    calls: list[str] = []
    source = provider(
        calls, index=INDEX + b"\n" if kind == "index" else INDEX,
        xml=XML.replace(b"35000", b"36000") if kind == "submission" else XML,
        stamp="20260831160200" if kind == "acceptance" else "20260831160100",
    )
    try:
        with pytest.raises(ValueError, match="index changed|evidence changed"):
            repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()
    assert encode_checkpoint(original) == before
    if kind == "index":
        assert not any(path.endswith(".txt") for path in calls)


def test_remaining_parser_error_rejects_repair() -> None:
    malformed = XML.replace(b"<value>35000</value>", b"<value>invalid</value>")
    original = legacy_checkpoint(malformed)
    before = encode_checkpoint(original)
    source = provider([], xml=malformed)
    try:
        with pytest.raises(ValueError, match="still has quarantines"):
            repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()
    assert encode_checkpoint(original) == before


@pytest.mark.parametrize("mutation", ["changed_revision", "extra_quarantine", "no_lineage"])
def test_repair_cannot_overwrite_existing_facts_or_partially_resolve_rows(mutation: str) -> None:
    original = legacy_checkpoint()
    filing = original["filings"][0]
    if mutation == "changed_revision":
        filing["records"][0]["transaction"]["pricePerShare"] = "123"
    elif mutation == "extra_quarantine":
        filing["quarantines"].append({**filing["quarantines"][0],
                                      "source_row_key": "DERIVATIVE:3:0001999103"})
    else:
        filing["records"] = []
    before = encode_checkpoint(original)
    source = provider([])
    try:
        with pytest.raises(ValueError, match="existing canonical|exactly resolve|lineage evidence"):
            repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()
    assert encode_checkpoint(original) == before


def test_repair_does_not_accept_other_kinds_of_recovered_transaction() -> None:
    ordinary = XML.replace(
        b"<transactionTotalValue><value>35000</value></transactionTotalValue>",
        b"<transactionShares><value>14</value></transactionShares>",
    )
    original = legacy_checkpoint(ordinary)
    source = provider([], xml=ordinary)
    try:
        with pytest.raises(ValueError, match="exactly resolve"):
            repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()


@pytest.mark.parametrize("point", [REPAIRED.replace(tzinfo=None), OBSERVED - timedelta(seconds=1)])
def test_repair_clock_cannot_be_naive_or_precede_original_observation(point: datetime) -> None:
    source = provider([])
    try:
        with pytest.raises(ValueError, match="clock|precede original"):
            repair_checkpoint(legacy_checkpoint(), source, repaired_at=point)
    finally:
        source.close()


def test_release_store_preserves_v1_prefers_v2_and_never_hides_corruption() -> None:
    original = legacy_checkpoint()
    source = provider([])
    try:
        repaired = repair_checkpoint(original, source, repaired_at=REPAIRED)
    finally:
        source.close()
    store = FakeReleases()
    old = store.persist(original)
    old_bytes = store.files[old["tag"]]
    assert old["tag"].startswith("sec-day-v1-") and store.latest(DAY) == original
    new = store.persist(repaired)
    assert new["tag"].startswith("sec-day-v2-") and store.latest(DAY) == repaired
    assert store.files[old["tag"]] == old_bytes
    assert store.persist(repaired) == new
    assert sum(args[:2] == ("release", "create") for args in store.commands) == 2
    # A later release from an old runner must not displace an explicit repair.
    next(item for item in store.releases if item["tag_name"] == old["tag"])["id"] = 100
    assert store.latest(DAY) == repaired
    damaged = bytearray(store.files[new["tag"]])
    damaged[len(damaged) // 2] ^= 1
    store.files[new["tag"]] = bytes(damaged)
    with pytest.raises(ValueError, match="checksum"):
        store.latest(DAY)
    assert store.files[old["tag"]] == old_bytes
    assert decode_checkpoint(*encode_checkpoint(original), day=DAY) == original
