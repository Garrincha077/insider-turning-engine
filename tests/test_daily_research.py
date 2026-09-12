import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

from test_identity_observations import _observation
from test_live_experimental import POINT, _record, _rows

from insider_turning_engine.domain.research import DayEvidence
from insider_turning_engine.pipeline import daily_research
from insider_turning_engine.pipeline.research_history import ResearchHistory


def test_ninety_day_inventory_is_bounded_disjoint_and_newest_first():
    calls = []

    def discover(start, end):
        assert (end - start).days <= 31
        calls.append((start, end))
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]

    result = daily_research.discover_research_days(SimpleNamespace(discover_days=discover),
                                                   end=POINT.date())
    assert len(result) == 90
    assert result[0] == POINT.date() - timedelta(days=89) and result[-1] == POINT.date()
    assert calls[0][1] == POINT.date()
    assert len(calls) == 3
    assert calls[1][1] == calls[0][0] - timedelta(days=1)


def _inputs():
    record = _record()
    identity = _observation()
    identity.update(cik=record.issuer.cik, knowledge_at=POINT.isoformat(),
                    valid_from=POINT.date().isoformat())
    day = (POINT - timedelta(days=3)).date()
    history = ResearchHistory((record,), (day,), (DayEvidence(
        day=day, discovered_filings=1, stored_filings=1, parse_rows=1,
        quarantined_rows=0, failures=0, complete=True),), {record.source.accession_number: day})
    return record, identity, history


def test_no_market_does_not_hide_source_linked_sec_facts(tmp_path):
    record, identity, history = _inputs()
    output = tmp_path / "public"
    daily_research.materialize_research(history, identity_rows=[identity], market={},
        as_of=POINT, run_id="run_daily_research_001", output=output)
    data = json.loads((output / "research-v2.json").read_text())
    assert len(data["economicTransactions"]) == 1
    assert data["economicTransactions"][0]["issuerCik"] == record.issuer.cik
    assert data["companies"][0]["currentPrice"] is None
    assert data["researchScores"][0]["total"] is None
    assert data["readiness"]["predictive"]["status"] == "BLOCKED"
    assert json.loads((output / "dashboard.json").read_text())["marketPulse"] is None


def test_full_materialization_replay_and_future_bars(tmp_path):
    _record_value, identity, history = _inputs()
    output = tmp_path / "public"
    market = {symbol: _rows(symbol) for symbol in ["ACME", "SPY", "XLK"]}
    kwargs = dict(identity_rows=[identity], as_of=POINT,
                  run_id="run_daily_research_001", output=output)
    first = daily_research.materialize_research(history, market=market, **kwargs)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    assert first == daily_research.materialize_research(history, market=market, **kwargs)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    market["ACME"] = (*market["ACME"], replace(market["ACME"][-1],
        date=POINT.date() + timedelta(days=1), available_at=POINT + timedelta(days=1)))
    daily_research.materialize_research(history, market=market, **kwargs)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    data = json.loads((output / "research-v2.json").read_text())
    assert data["companies"][0]["currentPrice"] is not None
    assert data["companySeries"]
    assert all(row["volume"] is not None for row in data["companySeries"])
    assert not data["readiness"]["predictive"]["status"] == "READY"


def test_market_outage_holds_recorded_state(tmp_path):
    record, identity, history = _inputs()
    prior = {record.issuer.cik: {"state": "BASE_FORMING", "established": True,
                               "failed_evaluations": 1, "changed_at": None}}
    result = daily_research.materialize_research(history, identity_rows=[identity], market={},
        as_of=POINT, run_id="run_daily_research_001", output=tmp_path, prior_state=prior)
    data = json.loads((tmp_path / "research-v2.json").read_text())
    assert data["researchScores"][0]["state"] == "BASE_FORMING"
    assert "STALE_DATA_HOLD" in data["researchScores"][0]["reasons"]
    assert result["states"][record.issuer.cik]["failed_evaluations"] == 1
    assert result["states"][record.issuer.cik]["state"] == "BASE_FORMING"


def test_same_session_reuses_hysteresis_and_rejects_corrupt_prior(tmp_path):
    import pytest

    record, identity, history = _inputs()
    prior = {record.issuer.cik: {"state": "BASE_FORMING", "established": True,
                               "failed_evaluations": 1, "changed_at": None,
                               "last_evaluated_session": POINT.date().isoformat()}}
    daily_research.materialize_research(history, identity_rows=[identity], market={},
        as_of=POINT, run_id="run_daily_research_002", output=tmp_path, prior_state=prior)
    data = json.loads((tmp_path / "research-v2.json").read_text())
    assert "SAME_SESSION_STATE_REUSED" in data["researchScores"][0]["reasons"]
    prior[record.issuer.cik]["state"] = "MADE_UP"
    with pytest.raises(ValueError, match="prior research state"):
        daily_research.materialize_research(history, identity_rows=[identity], market={},
            as_of=POINT, run_id="run_daily_research_002", output=tmp_path, prior_state=prior)


def test_shards_are_disjoint_bounded_and_keep_per_symbol_failures(tmp_path, monkeypatch):
    calls = []

    def fetch(symbols, **kwargs):
        calls.append(tuple(symbols))
        return ({symbol: () for symbol in symbols if symbol != "BAD"},
                {symbol: "private provider error" for symbol in symbols if symbol == "BAD"},
                {}, set())

    monkeypatch.setattr(daily_research, "_fetch_market", fetch)
    bars, failures = daily_research.market_shards(["BAD", "SPY", "AAA", "BBB", "AAA"],
                                                 cache_dir=tmp_path)
    assert len(calls) <= 3
    assert sorted(symbol for shard in calls for symbol in shard) == ["AAA", "BAD", "BBB", "SPY"]
    assert set(bars) == {"AAA", "BBB", "SPY"}
    assert failures == {"BAD": "MARKET_PROVIDER_UNAVAILABLE"}
