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
    assert "AMBIGUOUS_LISTING" in _observation(
        _profile(tickers=["ACME", "ACME.B"]),
        tickers=("ACME", "ACME.B"))["quality_flags"]
    assert "NO_CURRENT_LISTING" in _observation(tickers=())["quality_flags"]
    row = _observation(_profile(sic="9999"))
    assert row["sector_etf"] == "UNKNOWN"
    assert "SECTOR_UNMAPPED" in row["quality_flags"]


def _common_filing(ticker="ACME", title="Common Stock"):
    from test_live_experimental import _record

    record = _record().model_copy(deep=True)
    record.issuer.cik = CIK
    record.issuer.ticker = ticker
    record.security.title = title
    return record


def _multi_listing_observation(records, *, tickers=("ACME", "ACME-WT"), metadata=None):
    return identity_observation(
        CIK, parse_company_tickers_exchange(_map(tickers), retrieved_at=NOW),
        metadata=metadata or _profile(tickers=list(tickers)), observed_at=NOW,
        map_observed_at=NOW, map_hash="sha256:" + "a" * 64, run_id=RUN,
        filing_records=records)


def test_multi_listing_resolution_requires_point_in_time_common_stock_filing_proof():
    record = _common_filing()
    row = _multi_listing_observation([record, record])
    assert row["identity_status"] == "RESOLVED" and row["ticker"] == "ACME"
    proof = row["provenance"]["common_stock_listing_evidence"]
    assert proof["accession"] == record.source.accession_number
    assert proof["source_hash"] == record.source.content_hash
    assert proof["source_url"] == record.source.source_url
    assert proof["security_title"] == "Common Stock"
    assert row["knowledge_at"] == NOW.isoformat()  # no historical backdating
    assert "COMMON_STOCK_LISTING_CONFIRMED" in row["quality_flags"]
    assert _multi_listing_observation([])["identity_status"] == "UNRESOLVED"


@pytest.mark.parametrize("change", ["future", "undurable", "old", "derivative", "preferred",
                                   "warrant", "wrong_cik", "missing_ticker", "future_transaction"])
def test_unusable_filings_cannot_resolve_a_multi_listing(change):
    from insider_turning_engine.domain.models import TableType

    record = _common_filing()
    if change == "future":
        record.timestamps.knowledge_at = NOW + timedelta(seconds=1)
    elif change == "undurable":
        record.timestamps.recorded_at = NOW + timedelta(seconds=1)
    elif change == "old":
        record.timestamps.accepted_at = NOW - timedelta(days=366)
    elif change == "derivative":
        record.security.table_type = TableType.DERIVATIVE
    elif change == "preferred":
        record.security.title = "Preferred Stock convertible to Common Stock"
    elif change == "warrant":
        record.security.title = "Warrant to acquire Common Stock"
    elif change == "wrong_cik":
        record.issuer.cik = "0000000008"
    elif change == "missing_ticker":
        record.issuer.ticker = None
    else:
        record.transaction.transaction_date = (NOW + timedelta(days=1)).date()
    assert _multi_listing_observation([record])["ticker"] is None


def test_two_evidenced_common_classes_and_source_disagreement_remain_unresolved():
    records = [_common_filing("ACME"), _common_filing("ACME.B", "Class B Common Stock")]
    row = _multi_listing_observation(records, tickers=("ACME", "ACME.B"))
    assert row["ticker"] is None and "AMBIGUOUS_LISTING" in row["quality_flags"]
    row = _multi_listing_observation([records[0]], metadata=_profile(tickers=["ACME", "OTHER"]))
    assert "SOURCE_LISTING_DISAGREEMENT" in row["quality_flags"]


def test_acquisition_passes_canonical_listing_proof_into_fresh_observation(tmp_path):
    def handler(request):
        payload = (_map(("ACME", "ACME-WT")) if str(request.url) == COMPANY_TICKERS_EXCHANGE_URL
                   else _profile(tickers=["ACME", "ACME-WT"]))
        return httpx.Response(200, content=payload, headers={"Content-Type": "application/json"},
                              request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = acquire_identity_observations(
            [CIK], user_agent="ITE test@example.com", run_id=RUN, output=tmp_path / "out",
            client=client, clock=lambda: NOW, filing_records=[_common_filing()])
    assert report["resolvedIssuerCount"] == 1 and not report["unresolved"]
    rows = json.loads((tmp_path / "out/identities.json").read_bytes())
    assert rows[0]["ticker"] == "ACME"
    assert rows[0]["provenance"]["common_stock_listing_evidence"]["source_hash"]


def test_resolved_listing_enables_factual_digest_without_market_or_score():
    from decimal import Decimal

    from insider_turning_engine.domain.research import DayEvidence
    from insider_turning_engine.notifications.digest import load_digest_policy, preview_digest
    from insider_turning_engine.pipeline.research_snapshot import build_research_snapshot

    record = _common_filing()
    record.transaction.shares = Decimal("100000")
    record.transaction.price_per_share = Decimal("1")
    record.transaction.value = Decimal("100000")
    identity = _multi_listing_observation([record])
    day = record.timestamps.accepted_at.date()
    snapshot = build_research_snapshot(
        [record], as_of=NOW, run_id=RUN, identities={CIK: identity}, expected_sec_days=[day],
        sec_day_by_accession={record.source.accession_number: day},
        day_evidence=[DayEvidence(day=day, discovered_filings=1, stored_filings=1,
                                 parse_rows=1, quarantined_rows=0, failures=0, complete=True)])
    draft = preview_digest(snapshot, load_digest_policy())
    assert len(draft.event_ids) == 1 and not draft.reasons
    assert "$100,000" in draft.text and "ACME" in draft.text
    assert snapshot.companies[0].current_price is None
    assert snapshot.research_scores[0].total is None


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
