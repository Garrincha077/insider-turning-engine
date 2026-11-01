"""Only in-memory derivative repair; immutable SEC receipts and PIT fail closed."""
from __future__ import annotations

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_sec_amount_repair import (
    DAY,
    INDEX,
    OBSERVED,
    REPAIRED,
    XML,
    legacy_checkpoint,
    provider,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dry_run_sec_derivative_repair import (  # noqa: E402
    SourceDriftError,
    audit,
    verify_dry_run,
)


class FakeStore:
    def __init__(self, checkpoint):
        self.value = copy.deepcopy(checkpoint)
        self.downloads = 0
        self.writes = 0

    def latest(self, day):
        assert day == DAY
        self.downloads += 1
        return copy.deepcopy(self.value)

    def persist(self, value):
        self.writes += 1
        raise AssertionError("read-only audit attempted to publish Release")


def pinned(original):
    filing_rows = original["filings"]
    return {
        "schemaVersion": "sec-quarantine-triage-input-v1",
        "sourceRunId": "run_research_fixture_001",
        "sourceAsOf": "2026-09-03T00:00:00Z",
        "sourceResearchSha256": "a" * 64,
        "incompleteDays": [{
            "day": DAY.isoformat(),
            "discoveredFilings": len(original["discoveredAccessions"]),
            "storedFilings": len(filing_rows),
            "quarantinedRows": sum(len(f["quarantines"]) for f in filing_rows),
            "failures": len(original["failures"]),
        }],
    }


def test_legacy_derivative_dry_run_calls_real_repair_without_writing():
    original = legacy_checkpoint()
    frozen = copy.deepcopy(original)
    store = FakeStore(original)
    calls = []
    sec = provider(calls)
    try:
        result = audit(store, sec, pinned(original), repair_at=REPAIRED)
    finally:
        sec.close()
    assert original == frozen == store.value
    assert result["status"] == "COMPLETE_DIAGNOSTIC_NOT_AN_ARCHIVE_REPAIR"
    assert result["summary"]["candidateDerivativeFilings"] == 1
    assert result["summary"]["candidateDerivativeRows"] == 1
    assert result["summary"]["verifiedDryRunFilings"] == 1
    assert result["summary"]["verifiedDryRunRows"] == 1
    assert result["days"][0]["result"] == "FULL_DAY_REPAIR_DRY_RUN_VERIFIED"
    assert result["remoteWrites"] is False and result["archivePublished"] is False
    assert result["scoringChanged"] is False and result["telegramSent"] is False
    assert store.downloads == 1 and store.writes == 0
    assert sum(x.endswith(".txt") for x in calls) == 1
    text = json.dumps(result)
    assert "0001999103" not in text and "0001234567-26" not in text
    assert "<ownershipDocument" not in text


def test_other_derivative_without_accepted_lineage_blocks_atomic_day():
    original = legacy_checkpoint()
    second = copy.deepcopy(original["filings"][0])
    second["accession"] = "0001234567-26-000002"
    second["records"] = []
    original["filings"].append(second)
    original["discoveredAccessions"].append(second["accession"])
    store = FakeStore(original)
    calls = []
    sec = provider(calls)
    try:
        result = audit(store, sec, pinned(original), repair_at=REPAIRED)
    finally:
        sec.close()
    assert result["summary"]["candidateDerivativeFilings"] == 2
    assert result["summary"]["candidateFilingsWithLineage"] == 1
    assert result["summary"]["candidateFilingsWithoutLineage"] == 1
    assert result["summary"]["candidateFilingsBlockedByDayAtomicity"] == 1
    assert result["summary"].get("verifiedDryRunRows", 0) == 0
    assert result["days"][0]["result"] == "BLOCKED_WHOLE_DAY_DUE_TO_UNVERIFIABLE_CANDIDATE"
    assert calls == [] and store.writes == 0


def test_index_or_submission_hash_drift_does_not_persist():
    original = legacy_checkpoint()
    for index, xml, reason in [
        (INDEX + b"\n", XML, "BLOCKED_OFFICIAL_INDEX_CHANGED"),
        (INDEX, XML.replace(b"35000", b"36000"), "BLOCKED_SOURCE_HASH_OR_ACCEPTANCE_DRIFT"),
    ]:
        store = FakeStore(original)
        sec = provider([], index=index, xml=xml)
        try:
            result = audit(store, sec, pinned(original), repair_at=REPAIRED)
        finally:
            sec.close()
        assert result["days"][0]["result"] == reason
        assert result["summary"].get("verifiedDryRunRows", 0) == 0
        assert original == store.value and store.writes == 0


def test_original_observation_clock_never_moves_backward():
    original = legacy_checkpoint()
    sec = provider([])
    try:
        result = audit(
            FakeStore(original), sec, pinned(original),
            repair_at=OBSERVED - timedelta(seconds=1),
        )
    finally:
        sec.close()
    assert result["days"][0]["result"] == "BLOCKED_REPAIR_CLOCK_BEFORE_ORIGINAL"
    assert result["summary"].get("verifiedDryRunRows", 0) == 0


def test_non_derivative_invalid_row_remains_untouched():
    original = legacy_checkpoint()
    original["filings"][0]["quarantines"][0]["source_row_key"] = (
        "NON_DERIVATIVE:1:0001999103"
    )
    calls = []
    sec = provider(calls)
    try:
        result = audit(FakeStore(original), sec, pinned(original), repair_at=REPAIRED)
    finally:
        sec.close()
    assert result["summary"]["candidateDerivativeFilings"] == 0
    assert result["days"][0]["result"] == "NO_DERIVATIVE_CANDIDATES"
    assert calls == [] and result["remoteWrites"] is False


def test_verified_repair_fails_if_recovered_knowledge_is_backdated():
    original = legacy_checkpoint()
    sec = provider([])
    try:
        from insider_turning_engine.ingestion.sec.repair_amounts import repair_checkpoint

        fixed = repair_checkpoint(original, sec, repaired_at=REPAIRED)
    finally:
        sec.close()
    with pytest.raises(SourceDriftError, match="backdated"):
        verify_dry_run(original, fixed, repair_at=REPAIRED + timedelta(days=1))


def test_untrusted_counts_fail_before_SEC_request():
    original = legacy_checkpoint()
    wrong = pinned(original)
    wrong["incompleteDays"][0]["quarantinedRows"] += 1
    store = FakeStore(original)
    calls = []
    sec = provider(calls)
    try:
        with pytest.raises(SourceDriftError, match="aggregate drift"):
            audit(store, sec, wrong, repair_at=REPAIRED)
    finally:
        sec.close()
    assert calls == [] and store.writes == 0


def test_unaware_clock_fails_closed():
    original = legacy_checkpoint()
    sec = provider([])
    try:
        with pytest.raises(SourceDriftError, match="timezone"):
            audit(FakeStore(original), sec, pinned(original),
                  repair_at=REPAIRED.replace(tzinfo=None))
    finally:
        sec.close()
