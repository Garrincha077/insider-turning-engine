from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from insider_turning_engine.cli import app
from insider_turning_engine.ingestion.sec.identity import (
    COMPANY_TICKERS_EXCHANGE_URL,
    parse_company_tickers_exchange,
)
from insider_turning_engine.normalization.identity import map_sic_to_sector_etf
from insider_turning_engine.pipeline.daily import _ticker_by_cik
from insider_turning_engine.pipeline.identity_observations import (
    LIVE_SIC_MAPPING_PATH,
    acquire_identity_observations,
    identity_observation,
    merge_observations,
)
from insider_turning_engine.pipeline.live_inputs import _identity_candidates

NOW = datetime(2026, 9, 10, 20, 1, tzinfo=UTC)
CIK = "0000000007"
RUN = "run_identity_test_001"


def _map(tickers: tuple[str, ...] = ("ACME",)) -> bytes:
    return json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                       "data": [[7, "Acme Inc", ticker, "Nasdaq"] for ticker in tickers]}).encode()


def _profile(**overrides: object) -> bytes:
    return json.dumps({"cik": CIK, "name": "Acme Inc", "entityType": "operating",
                       "sic": "3571", "stateOfIncorporation": "DE", "tickers": ["ACME"],
                       "exchanges": ["Nasdaq"], **overrides}).encode()


def _observation(metadata: bytes | None = None, *, tickers: tuple[str, ...] = ("ACME",)):
    return identity_observation(
        CIK, parse_company_tickers_exchange(_map(tickers), retrieved_at=NOW),
        metadata=metadata if metadata is not None else _profile(), observed_at=NOW,
        map_observed_at=NOW - timedelta(seconds=1), map_hash="sha256:" + "a" * 64, run_id=RUN,
    )


def test_current_identity_requires_filing_evidence_and_is_not_backdated():
    row = _observation()
    assert row["sector_etf"] == "XLK"
    assert row["country"] == "US"
    assert row["knowledge_at"] == NOW.isoformat()
    assert "security_type" not in row
    assert _identity_candidates([row], as_of=NOW) == {}
    kwargs = {"common_stock_titles": {CIK: "Common Stock"}}
    assert _identity_candidates([row], as_of=NOW - timedelta(minutes=1), **kwargs) == {}
    selected = _identity_candidates([row], as_of=NOW, **kwargs)[CIK]
    assert selected["provenance"] == row["provenance"]
    assert selected["security_type"] == "COMMON_STOCK"
    assert _ticker_by_cik([selected], as_of=NOW) == {CIK: "ACME"}


@pytest.mark.parametrize("changes,reason", [
    ({"cik": "8"}, "INVALID_COMPANY_METADATA"),
    ({"entityType": "investment"}, "NOT_OPERATING_ENTITY"),
    ({"stateOfIncorporation": "E9"}, "US_INCORPORATION_UNCONFIRMED"),
    ({"sic": None}, "MISSING_SIC"),
    ({"sic": "6770"}, "EXCLUDED_UNIVERSE"),
    ({"tickers": ["WRONG"]}, "SOURCE_LISTING_DISAGREEMENT"),
    ({"tickers": ["ACME", "ACME.B"]}, "SOURCE_LISTING_DISAGREEMENT"),
    ({"exchanges": ["NYSE"]}, "SOURCE_LISTING_DISAGREEMENT"),
])
def test_unconfirmed_profile_is_not_a_usable_listing(changes, reason):
    row = _observation(_profile(**changes))
    assert row["identity_status"] == "UNRESOLVED"
    assert row["ticker"] is None
    assert reason in row["quality_flags"]


def test_multiple_classes_missing_listing_and_missing_sector_are_explicit():
    assert "AMBIGUOUS_LISTING" in _observation(tickers=("ACME", "ACME.B"))["quality_flags"]
    assert "NO_CURRENT_LISTING" in _observation(tickers=())["quality_flags"]
    row = _observation(_profile(sic="9999"))
    assert row["sector_etf"] == "UNKNOWN"
    assert "SECTOR_UNMAPPED" in row["quality_flags"]


def test_merge_is_replayable_and_never_mutates_old_observations():
    old = _observation()
    new = {**old, "knowledge_at": (NOW + timedelta(days=1)).isoformat(), "ticker": "NEW"}
    before = json.dumps(old, sort_keys=True)
    assert merge_observations([old], [new, old]) == [old, new]
    assert json.dumps(old, sort_keys=True) == before
    with pytest.raises(ValueError, match="conflicting"):
        merge_observations([old], [{**old, "ticker": "CONFLICT"}])
    with pytest.raises(ValueError, match="timezone"):
        merge_observations([], [{**old, "knowledge_at": "2026-09-10T20:01:00"}])


@pytest.mark.parametrize("update", [
    {"ticker": None, "identity_status": "UNRESOLVED"},
    {"exchange": "OTC"},
    {"security_type": "Preferred Stock"},
    {"valid_to": "2026-09-11"},
])
def test_new_invalid_or_expired_identity_never_resurrects_old_mapping(update):
    old = {**_observation(), "security_type": "Common Stock"}
    tomorrow = NOW + timedelta(days=1)
    new = {**old, "knowledge_at": tomorrow.isoformat(), **update}
    assert _identity_candidates([old, new], as_of=NOW)[CIK]["ticker"] == "ACME"
    assert _identity_candidates([old, new], as_of=tomorrow) == {}


def test_simultaneous_ambiguous_tickers_fail_closed_but_exact_replay_deduplicates():
    old = {**_observation(), "security_type": "Common Stock"}
    assert len(_identity_candidates([old, old], as_of=NOW)) == 1
    assert _identity_candidates([old, {**old, "ticker": "OTHER"}], as_of=NOW) == {}
    # One price series must not be silently assigned to two legal issuers.
    assert _identity_candidates([old, {**old, "cik": "0000000008"}], as_of=NOW) == {}


def test_acquisition_atomic_append_and_partial_failure(tmp_path: Path):
    requested = []

    def handler(request: httpx.Request):
        requested.append(str(request.url))
        assert "test@example.com" in request.headers["User-Agent"]
        if str(request.url) == COMPANY_TICKERS_EXCHANGE_URL:
            body = _map()
        elif "CIK0000000008" in str(request.url):
            return httpx.Response(404, request=request)
        else:
            body = _profile()
        return httpx.Response(200, content=body, headers={"Content-Type": "application/json"},
                              request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = acquire_identity_observations(
            ["7", "8", "7"], user_agent="ITE test@example.com", run_id=RUN,
            output=tmp_path / "first", client=client, clock=lambda: NOW,
        )
        assert len(requested) == 3
        assert report["status"] == "PARTIAL"
        assert report["resolvedIssuerCount"] == 1
        assert report["unresolved"][0]["reasons"] == ["METADATA_FETCH_FAILED"]
        assert report["signalReady"] is report["alertsAllowed"] is False
        previous = tmp_path / "first" / "identities.json"
        previous_bytes = previous.read_bytes()
        assert report["artifacts"]["identities.json"] == (
            "sha256:" + hashlib.sha256(previous_bytes).hexdigest())
        second = acquire_identity_observations(
            ["7"], user_agent="ITE test@example.com", run_id=RUN,
            output=tmp_path / "second", previous=previous,
            client=client, clock=lambda: NOW + timedelta(days=1),
        )
        assert second["status"] == "OBSERVED"
        assert previous.read_bytes() == previous_bytes
        assert len(json.loads((tmp_path / "second" / "identities.json").read_bytes())) == 3
        with pytest.raises(ValueError, match="fresh immutable"):
            acquire_identity_observations(["7"], user_agent="ITE test@example.com", run_id=RUN,
                                          output=tmp_path / "first", client=client)


def test_global_map_failure_leaves_no_partial_bundle(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"bad": "map"}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            acquire_identity_observations(["7"], user_agent="ITE test@example.com", run_id=RUN,
                                          output=tmp_path / "failed", client=client)
    assert not (tmp_path / "failed").exists()


def test_cli_preview_needs_no_network_or_sec_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    ciks = tmp_path / "ciks.txt"
    ciks.write_text("7\n0000000007\n8\n")
    result = CliRunner().invoke(app, ["observe-sec-identities", "--ciks-file", str(ciks),
                                    "--output", str(tmp_path / "out"), "--run-id", RUN])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["issuerCount"] == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("sic,expected", [
    ("1040", "XLB"), ("1099", "XLB"), ("1100", "UNKNOWN"), ("1221", "XLE"),
    ("1311", "XLE"), ("1623", "XLI"), ("1699", "XLI"), ("1700", "UNKNOWN"),
    ("2320", "XLY"), ("2510", "XLY"), ("2519", "XLY"), ("2520", "UNKNOWN"),
    ("2834", "XLV"), ("3840", "XLV"), ("3852", "XLI"), ("9999", "UNKNOWN"),
])
def test_live_sector_v11_golden_boundaries_preserve_old_replay(sic, expected):
    result = map_sic_to_sector_etf(sic, mapping_path=LIVE_SIC_MAPPING_PATH)
    assert result.sector_etf == expected
    assert result.mapping_version == "1.1.0"
    assert map_sic_to_sector_etf("1040").sector_etf == "XLE"  # unchanged archived v1.0
