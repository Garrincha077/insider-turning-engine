"""Offline read-only SEC replay verification with mocked public SEC responses."""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from test_sec_amount_repair import (
    DAY, INDEX, XML, legacy_checkpoint, provider,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_existing_sec_quarantines_readonly import (  # noqa: E402
    audit, replay_filing, safe_cause,
)
from triage_existing_sec_quarantines import SourceDriftError  # noqa: E402


class FakeStore:
    def __init__(self, content):
        self.content = content
        self.lookups = []

    def latest(self, day):
        self.lookups.append(day)
        return copy.deepcopy(self.content) if day == DAY else None


def pinned(original):
    filings = original["filings"]
    return {
        "schemaVersion": "sec-quarantine-triage-input-v1",
        "sourceRunId": "run_research_fixture_20260831",
        "sourceAsOf": "2026-09-03T00:00:00Z",
        "sourceResearchSha256": "a" * 64,
        "incompleteDays": [{
            "day": DAY.isoformat(),
            "discoveredFilings": len(original["discoveredAccessions"]),
            "storedFilings": len(filings),
            "quarantinedRows": sum(len(f["quarantines"]) for f in filings),
            "failures": len(original["failures"]),
        }],
    }


def test_derivative_new_parser_replay_is_preflight_only():
    old = legacy_checkpoint()
    before = copy.deepcopy(old)
    calls = []
    sec = provider(calls)
    try:
        report = audit(FakeStore(old), sec, pinned(old))
    finally:
        sec.close()
    assert old == before
    assert report["status"] == "COMPLETE_DIAGNOSTIC_NOT_A_REPAIR"
    assert report["quarantinedRows"] == 1
    assert report["sourceVerifiedRowsParsed"] == 1
    assert report["derivativePrecheckFilings"] == 1
    assert report["outcomeTotals"] == {"PARSES_WITH_CURRENT_PARSER": 1}
    assert report["sourceStatusTotals"] == {"CANONICAL_UNCHANGED": 1}
    assert (report["checkpointUpdated"], report["scoreChanged"], report["alertsSent"]) == (
        False, False, False,
    )
    assert sum(path.endswith(".txt") for path in calls) == 1
    rendered = json.dumps(report)
    assert "0001999103" not in rendered
    assert "0001234567-26" not in rendered
    assert "rawXml" not in rendered and "XML" not in rendered


def test_current_parser_still_rejects_invalid_derivative_source():
    bad = XML.replace(b"<value>35000</value>", b"<value>invalid</value>")
    old = legacy_checkpoint(bad)
    sec = provider([], xml=bad)
    try:
        report = audit(FakeStore(old), sec, pinned(old))
    finally:
        sec.close()
    assert report["sourceVerifiedRowsParsed"] == 1
    assert report["derivativePrecheckFilings"] == 0
    assert report["outcomeTotals"] == {
        "STILL_REJECTED_DERIVATIVE_TOTAL_VALUE_UNAVAILABLE": 1,
    }


def test_official_daily_index_drift_refuses_to_fetch_submission():
    old = legacy_checkpoint()
    calls = []
    sec = provider(calls, index=INDEX + b"\n")
    try:
        report = audit(FakeStore(old), sec, pinned(old))
    finally:
        sec.close()
    assert report["status"] == "PARTIAL_UNVERIFIED"
    assert report["outcomeTotals"] == {"INDEX_SOURCE_DRIFT": 1}
    assert not any(path.endswith(".txt") for path in calls)


def test_official_submission_hash_drift_never_relabels_old_row():
    old = legacy_checkpoint()
    wrong = XML.replace(b"<value>35000</value>", b"<value>36000</value>")
    sec = provider([], xml=wrong)
    try:
        report = audit(FakeStore(old), sec, pinned(old))
    finally:
        sec.close()
    assert report["outcomeTotals"] == {"SOURCE_SUBMISSION_HASH_OR_PROVENANCE_DRIFT": 1}
    assert report["status"] == "PARTIAL_UNVERIFIED"
    assert report["sourceVerifiedRowsParsed"] == 0


def test_no_original_canonical_lineage_is_never_preapproved():
    old = legacy_checkpoint()
    old["filings"][0]["records"] = []
    sec = provider([])
    try:
        report = audit(FakeStore(old), sec, pinned(old))
    finally:
        sec.close()
    assert report["status"] == "COMPLETE_DIAGNOSTIC_NOT_A_REPAIR"
    assert report["derivativePrecheckFilings"] == 0
    assert report["sourceStatusTotals"] == {"CANONICAL_UNVERIFIED_OR_CHANGED": 1}


def test_checkpoint_count_drift_fails_before_any_source_gets():
    old = legacy_checkpoint()
    evidence = pinned(old)
    evidence["incompleteDays"][0]["quarantinedRows"] += 1
    calls = []
    sec = provider(calls)
    try:
        with pytest.raises(SourceDriftError, match="aggregate drift"):
            audit(FakeStore(old), sec, evidence)
    finally:
        sec.close()
    assert calls == []


@pytest.mark.parametrize(("message", "reason"), [
    ("transaction shares are required and must be non-negative", "MISSING_OR_INVALID_SHARES"),
    ("transaction price is invalid", "INVALID_PRICE"),
    ("derivative without transaction shares requires a valid total value",
     "DERIVATIVE_TOTAL_VALUE_UNAVAILABLE"),
    ("Secret SEC owner name 123-45-6789", "OTHER_MODEL_OR_PARSER_VALIDATION"),
])
def test_safe_cause_never_returns_source_text(message, reason):
    assert safe_cause(message) == reason
    assert "123-45" not in safe_cause(message)


def test_stale_row_or_missing_source_status_stays_unverified():
    old = legacy_checkpoint()
    # No request for an unrelated date or a larger-than-allowed evidence set.
    evidence = pinned(old)
    evidence["incompleteDays"] = [
        {**evidence["incompleteDays"][0], "day": date(2026, 8, day).isoformat()}
        for day in range(1, 22)
    ]
    sec = provider([])
    try:
        with pytest.raises(SourceDriftError, match="too many days"):
            audit(FakeStore(old), sec, evidence)
    finally:
        sec.close()
