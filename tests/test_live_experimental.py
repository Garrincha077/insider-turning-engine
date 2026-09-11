import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_identity_observations import _observation

from insider_turning_engine.domain.time import us_equity_session_close
from insider_turning_engine.export import (
    dashboard_experimental_publication_policy,
    validate_dashboard_directory,
)
from insider_turning_engine.ingestion.market import DailyBar
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml
from insider_turning_engine.pipeline import live_experimental as live

POINT = datetime(2026, 8, 31, 20, 1, tzinfo=UTC)


def _record():
    return parse_sec_xml(
        (Path(__file__).parent / "fixtures/form4_non_derivative.xml").read_bytes(),
        {"accession_number": "0001234567-26-000001",
         "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
         "accepted_at": POINT - timedelta(days=3), "observed_at": POINT - timedelta(days=3),
         "run_id": "run_live_fixture_001"},
    ).records[0]


def _rows(symbol):
    days = [POINT.date() - timedelta(days=n) for n in range(1250, -1, -1)
            if (POINT.date() - timedelta(days=n)).weekday() < 5]
    return tuple(DailyBar(
        date=day, symbol=symbol,
        open=Decimal(50 + i % 10) + Decimal(i) / 10,
        high=Decimal(52 + i % 10) + Decimal(i) / 10,
        low=Decimal(49 + i % 10) + Decimal(i) / 10,
        close=Decimal(51 + i % 10) + Decimal(i) / 10,
        volume=100000 + i * 7, available_at=us_equity_session_close(day),
        provider="fixture", is_adjusted=True,
    ) for i, day in enumerate(days))


def _wire(monkeypatch, *, missing=None, stale=False, storage_failure=False):
    record = _record()
    calls = []
    monkeypatch.setattr(live.SECDailyIndexSource, "discover_days",
                        lambda _self, first, last: (date(2026, 8, 28),))
    monkeypatch.setattr(live, "_fetch_sec_records",
                        lambda **_: ([record], 1, 0, 0, 0, POINT - timedelta(minutes=1)))

    def acquire(ciks, *, output, **kwargs):
        assert ciks == [record.issuer.cik]
        row = _observation()
        row.update(cik=record.issuer.cik, ticker="ACME", knowledge_at=POINT.isoformat(),
                   valid_from=POINT.date().isoformat(), ingested_at=POINT.isoformat())
        row["provenance"].update(
            metadata_url=f"https://data.sec.gov/submissions/CIK{record.issuer.cik}.json",
            metadata_observed_at=POINT.isoformat(), exchange_observed_at=POINT.isoformat(),
        )
        output.mkdir(parents=True)
        (output / "identities.json").write_text(json.dumps([row]))
        return {"observedThrough": POINT.isoformat(), "unresolvedIssuerCount": 0}

    class Store:
        def __init__(self, *args, **kwargs):
            pass

        def latest(self):
            return None

        def persist(self, rows):
            calls.append("durable_identity")
            if storage_failure:
                raise RuntimeError("readback failed")
            return {"storageStatus": "VERIFIED", "url": "https://github.com/owner/repo/releases"}

    def market(symbols, **kwargs):
        assert set(symbols) == {"ACME", "SPY", "XLK"}
        assert calls == ["durable_identity"]
        calls.append("market")
        result = {symbol: _rows(symbol) for symbol in symbols if symbol != missing}
        if stale:
            result["XLK"] = result["XLK"][:-4]
        return result, {}, dict.fromkeys(symbols, "fixture"), set(symbols)

    monkeypatch.setattr(live, "acquire_identity_observations", acquire)
    monkeypatch.setattr(live, "ReleaseIdentityStore", Store)
    monkeypatch.setattr(live, "_fetch_market", market)
    return calls


def test_adapter_to_public_snapshot_uses_real_sector_contract_and_keeps_alerts_off(
    tmp_path, monkeypatch,
):
    calls = _wire(monkeypatch)
    result = live.generate_live_experimental_dashboard(
        output_dir=tmp_path / "public", cache_dir=tmp_path / "cache",
        user_agent="ITE test@example.com", now=POINT, max_symbols=0,
        identity_repository="owner/repo", identity_target="a" * 40,
    )
    assert calls == ["durable_identity", "market"]
    assert result.candidates == 1
    manifest = validate_dashboard_directory(tmp_path / "public", require_settings=True)
    assert dashboard_experimental_publication_policy(manifest) == (True, False)
    assert manifest["quality"]["marketCoverage"]["denominator"] == 1
    dashboard = json.loads((tmp_path / "public/dashboard.json").read_text())
    candidate = dashboard["candidates"][0]
    assert candidate["sector"] == "Technology / XLK (SIC)"
    assert "SECTOR_RS_PROXY_SPY" not in result.issues
    assert candidate["sourceReferences"]["sectorMappingVersion"] == "1.1.0"
    assert candidate["sourceReferences"]["identityKnownAt"] == (
        POINT.isoformat().replace("+00:00", "Z"))


@pytest.mark.parametrize("missing,stale,storage_failure,message", [
    ("XLK", False, False, "benchmark unavailable"),
    ("ACME", False, False, "coverage below"),
    (None, True, False, "stale"),
    (None, False, True, "readback failed"),
])
def test_failed_source_or_durability_preserves_previous_snapshot(
    tmp_path, monkeypatch, missing, stale, storage_failure, message,
):
    _wire(monkeypatch, missing=missing, stale=stale, storage_failure=storage_failure)
    public = tmp_path / "public"
    public.mkdir()
    marker = public / "manifest.json"
    marker.write_text("previous valid manifest")
    with pytest.raises(RuntimeError, match=message):
        live.generate_live_experimental_dashboard(
            output_dir=public, cache_dir=tmp_path / "cache", user_agent="ITE test@example.com",
            now=POINT, identity_repository="owner/repo", identity_target="a" * 40,
        )
    assert marker.read_text() == "previous valid manifest"


def test_selection_does_not_require_current_filing_ticker_or_choose_ambiguous_identity():
    record = _record()
    row = _observation()
    row.update(cik=record.issuer.cik, knowledge_at=POINT.isoformat(),
               valid_from=POINT.date().isoformat(), ticker="NEW")
    selected, rows = live._select_issuers([record], [row], as_of=POINT, max_symbols=0)
    assert selected == {record.issuer.cik: "NEW"}
    assert rows[0]["sector_etf"] == "XLK"
    selected, _ = live._select_issuers([record], [row, {**row, "ticker": "OTHER"}],
                                      as_of=POINT, max_symbols=0)
    assert selected == {}
