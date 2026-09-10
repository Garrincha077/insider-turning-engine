import copy
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_sec_checkpoints import DAY, checkpoint

from insider_turning_engine.pipeline.sec_history import assemble_history

AS_OF = datetime(2026, 9, 2, 20, tzinfo=UTC)


def test_history_replay_is_byte_identical_and_deduplicates_inputs(tmp_path: Path) -> None:
    value = checkpoint(tmp_path / "source")
    output = tmp_path / "history"
    report = assemble_history([value, value], expected_days=(DAY,), as_of=AS_OF, output=output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    assert report["status"] == "HISTORY_READY" and report["effectiveTransactions"] > 0
    assert not report["signalReady"] and not report["publishable"]
    assert assemble_history([value], expected_days=(DAY,), as_of=AS_OF, output=output) == report
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}


def test_future_observation_does_not_enter_earlier_history(tmp_path: Path) -> None:
    value = checkpoint(tmp_path / "source")
    report = assemble_history([value], expected_days=(DAY,),
                              as_of=datetime(2026, 9, 1, 20, tzinfo=UTC),
                              output=tmp_path / "history")
    assert report["effectiveTransactions"] == 0 and report["excludedAfterAsOf"] > 0
    assert (tmp_path / "history/canonical.json").read_text() == "[]\n"


def test_repeated_observation_across_days_does_not_double_count(tmp_path: Path) -> None:
    original = checkpoint(tmp_path / "source")
    later = copy.deepcopy(original)
    later["day"] = "2026-09-01"
    for filing in later["filings"]:
        filing["provenance"]["daily_index_url"] = (
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/master.20260901.idx"
        )
    single = assemble_history([original], expected_days=(DAY,), as_of=AS_OF,
                              output=tmp_path / "single")
    joined = assemble_history([later, original], expected_days=(DAY, date(2026, 9, 1)),
                              as_of=AS_OF, output=tmp_path / "joined")
    assert joined["eligibleObservations"] == single["eligibleObservations"] * 2
    assert joined["effectiveTransactions"] == single["effectiveTransactions"]
    assert (tmp_path / "single/canonical.json").read_bytes() == (
        tmp_path / "joined/canonical.json"
    ).read_bytes()


@pytest.mark.parametrize("problem", ["quarantine", "missing", "amendment"])
def test_incomplete_history_never_exports_a_signal_input(tmp_path: Path, problem: str) -> None:
    value = checkpoint(tmp_path / "source", invalid_rows=problem == "quarantine")
    days = (DAY, date(2026, 9, 1)) if problem == "missing" else (DAY,)
    if problem == "amendment":
        value = copy.deepcopy(value)
        for filing in value["filings"]:
            for row in filing["records"]:
                row["source"]["formType"] = "4/A"
                row["lifecycle"]["isAmendment"] = True
    output = tmp_path / "history"
    report = assemble_history([value], expected_days=days, as_of=AS_OF, output=output)
    assert report["status"] == "BLOCKED" and report["blockingReasons"]
    assert [path.name for path in output.iterdir()] == ["history-manifest.json"]


def test_history_cannot_overwrite_previous_cutoff(tmp_path: Path) -> None:
    value = checkpoint(tmp_path / "source")
    output = tmp_path / "history"
    assemble_history([value], expected_days=(DAY,), as_of=AS_OF, output=output)
    with pytest.raises(ValueError, match="immutable"):
        assemble_history([value], expected_days=(DAY,),
                         as_of=datetime(2026, 9, 3, 20, tzinfo=UTC), output=output)
