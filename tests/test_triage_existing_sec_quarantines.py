"""Offline contract tests for read-only SEC quarantine reason diagnosis."""
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_sec_checkpoints import DAY, checkpoint

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from triage_existing_sec_quarantines import (  # noqa: E402
    SourceDriftError,
    aggregate_verified_checkpoint,
    audit,
    verify_expectation,
)


class FakeReleaseStore:
    def __init__(self, payload):
        self.payload = payload
        self.requested = []

    def latest(self, day):
        self.requested.append(day)
        return copy.deepcopy(self.payload) if day == DAY else None


def fixture_reference(value):
    count = sum(len(item["quarantines"]) for item in value["filings"])
    return {
        "schemaVersion": "sec-quarantine-triage-input-v1",
        "sourceRunId": "run_research_fixture_001",
        "sourceAsOf": datetime(2026, 9, 3, tzinfo=UTC).isoformat(),
        "sourceResearchSha256": "a" * 64,
        "incompleteDays": [{
            "day": DAY.isoformat(),
            "discoveredFilings": len(value["discoveredAccessions"]),
            "storedFilings": len(value["filings"]),
            "quarantinedRows": count,
            "failures": len(value["failures"]),
        }],
    }


def test_real_parser_fixture_reconciles_and_never_exports_raw(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    expected = fixture_reference(value)
    store = FakeReleaseStore(value)
    result = audit(store, expected)
    assert result["status"] == "VERIFIED_CURRENT_CHECKPOINT_COUNTS_MATCH_PINNED_SOURCE"
    assert result["incompleteDays"] == 1
    assert result["totalQuarantinedRows"] > 0
    assert sum(result["reasonCounts"].values()) == result["totalQuarantinedRows"]
    assert sum(result["days"][0]["quarantineReasonCodes"].values()) == (
        result["totalQuarantinedRows"]
    )
    assert store.requested == [DAY]
    assert (result["scoringModified"], result["stateModified"], result["alertsSent"]) == (
        False, False, False,
    )
    report = json.dumps(result)
    assert "owner_cik" not in report and "reportingOwner" not in report
    assert "sourceRowKey" not in report and "0001234567-26-" not in report
    assert "0001999101" not in report


def test_corrupted_source_counts_fail_closed(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    expected = fixture_reference(value)
    expected["incompleteDays"][0]["quarantinedRows"] += 1
    with pytest.raises(SourceDriftError, match="aggregate drift"):
        audit(FakeReleaseStore(value), expected)
    expected = fixture_reference(value)
    expected["incompleteDays"][0]["storedFilings"] -= 1
    with pytest.raises(SourceDriftError, match="aggregate drift"):
        audit(FakeReleaseStore(value), expected)


def test_remote_missing_fails_closed(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    with pytest.raises(SourceDriftError, match="release missing"):
        audit(FakeReleaseStore(None), fixture_reference(value))


def test_tampered_checkpoint_is_never_misreported(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    wrong = copy.deepcopy(value)
    wrong["indexHash"] = "incorrect"
    with pytest.raises(ValueError):
        aggregate_verified_checkpoint(
            wrong, day=DAY, expected=fixture_reference(value)["incompleteDays"][0],
        )


def test_rejects_wrong_schema_duplicate_dates_and_no_quarantine(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    base = fixture_reference(value)
    assert len(verify_expectation(base)) == 1
    changed = copy.deepcopy(base)
    changed["schemaVersion"] = "unsupported"
    with pytest.raises(SourceDriftError):
        verify_expectation(changed)
    changed = copy.deepcopy(base)
    changed["incompleteDays"] *= 2
    with pytest.raises(SourceDriftError, match="duplicate"):
        verify_expectation(changed)
    changed = copy.deepcopy(base)
    changed["incompleteDays"][0]["quarantinedRows"] = 0
    with pytest.raises(SourceDriftError, match="not incomplete"):
        verify_expectation(changed)


def test_same_checkpoint_never_requires_network_during_fake_replay(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    original = copy.deepcopy(value)
    store = FakeReleaseStore(value)
    first = audit(store, fixture_reference(value))
    second = audit(store, fixture_reference(value))
    assert first == second
    assert original == value
