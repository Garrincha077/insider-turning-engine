import copy
from datetime import date
from types import SimpleNamespace

import pytest
from test_sec_checkpoints import DAY, MemoryStore, checkpoint

from insider_turning_engine.pipeline.research_history import research_history
from insider_turning_engine.pipeline.sec_acquisition import acquire_range


def _republished(value, day):
    duplicate = copy.deepcopy(value)
    duplicate["day"] = day.isoformat()
    duplicate["indexHash"] = "sha256:" + "9" * 64
    for filing in duplicate["filings"]:
        filing["indexHash"] = duplicate["indexHash"]
        filing["provenance"]["daily_index_hash"] = duplicate["indexHash"]
        filing["provenance"]["daily_index_url"] = (
            f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/"
            f"QTR{(day.month - 1) // 3 + 1}/master.{day:%Y%m%d}.idx"
        )
    return duplicate


def test_partial_research_keeps_facts_and_explicit_day_evidence(tmp_path):
    value = checkpoint(tmp_path)
    missing_day = date(2026, 9, 1)
    first = research_history([value], expected_days=[DAY, missing_day])
    second = research_history([value], expected_days=[missing_day, DAY])
    assert first == second
    assert first.records
    assert first.expected_days == (DAY, missing_day)
    assert first.evidence[0].complete
    assert set(first.sec_day_by_accession.values()) == {DAY}


def test_quarantined_checkpoint_is_not_complete_and_schema_damage_is_fatal(tmp_path):
    value = checkpoint(tmp_path, invalid_rows=True)
    history = research_history([value], expected_days=[DAY])
    assert history.evidence[0].quarantined_rows > 0
    assert not history.evidence[0].complete
    value["indexHash"] = "fake"
    with pytest.raises(ValueError):
        research_history([value], expected_days=[DAY])


def test_checkpoint_must_belong_to_exact_unique_day_inventory(tmp_path):
    value = checkpoint(tmp_path)
    with pytest.raises(ValueError, match="duplicate"):
        research_history([value, value], expected_days=[DAY])
    with pytest.raises(ValueError, match="unexpected"):
        research_history([value], expected_days=[])


def test_unchanged_accession_republished_in_later_index_is_counted_once(tmp_path):
    value = checkpoint(tmp_path)
    later_day = date(2026, 9, 1)
    duplicate = _republished(value, later_day)
    history = research_history([duplicate, value], expected_days=[DAY, later_day])
    assert len(history.records) == sum(len(filing["records"]) for filing in value["filings"])
    assert set(history.sec_day_by_accession.values()) == {DAY}
    assert len(history.evidence) == 2


def test_republished_accession_with_different_source_hash_is_fatal(tmp_path):
    value = checkpoint(tmp_path)
    later_day = date(2026, 9, 1)
    duplicate = _republished(value, later_day)
    duplicate["filings"][0]["provenance"]["complete_submission_hash"] = (
        "sha256:" + "8" * 64
    )
    with pytest.raises(ValueError, match="conflicting SEC day"):
        research_history([value, duplicate], expected_days=[DAY, later_day])


def test_newest_first_prioritizes_current_day_without_silencing_failure(tmp_path, monkeypatch):
    days = [date(2026, 8, 31), date(2026, 9, 2)]
    calls = []

    def failed_ingest(_source, *, day, **kwargs):
        calls.append(day)
        raise RuntimeError("fixture partial fetch")

    monkeypatch.setattr("insider_turning_engine.pipeline.sec_acquisition.ingest_day",
                        failed_ingest)
    report = acquire_range(SimpleNamespace(discover_days=lambda start, end: days),
                           MemoryStore(), start=days[0], end=days[-1], root=tmp_path,
                           max_days=1, newest_first=True)
    assert calls == [days[-1]]
    assert report["deferredDays"] == [days[0].isoformat()]
    assert report["acquisitionStatus"] == "INCOMPLETE"
    assert not report["publishable"]
    assert not (tmp_path / "sec.cursor").exists()
