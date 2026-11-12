import json
from datetime import datetime, timedelta

import httpx
import pytest
from test_company_facts import AS_OF, CIK, FIRST, LATER, payload

from insider_turning_engine.ingestion.sec.financial_source import (
    SECFinancialSource,
    acceptance_index,
)
from insider_turning_engine.ingestion.sec.historical import RequestPacer

UA = "InsiderTurningEngine tests test@example.org"
CONCEPTS = {"us-gaap": ["NetIncomeLoss"]}


def submissions(accession=FIRST):
    return {"cik": CIK, "filings": {"recent": {"accessionNumber": [accession],
        "form": ["10-K"], "acceptanceDateTime": ["2026-02-10T22:00:00Z"]}, "files": []}}


def source(tmp_path, handler, now=None):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return SECFinancialSource(UA, cache_dir=tmp_path, client=client,
        pacer=RequestPacer(sleeper=lambda delay: None), clock=now or (lambda: AS_OF))


def test_warm_cache_replays_exact_documents_without_network_and_keeps_provenance(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["User-Agent"] == UA
        return httpx.Response(200, json=payload() if "companyfacts" in request.url.path
                              else submissions(), request=request)

    adapter = source(tmp_path, handler)
    first = adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS, max_archives=0)
    second = adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS, max_archives=0)
    assert first.result == second.result and first.acceptance_count == 1
    assert len(calls) == 2 and all(row.cache_hit for row in second.sources)
    assert first.sources[1].sha256 == second.sources[1].sha256
    assert second.sources[1].fetched_at == AS_OF
    adapter.close()
    assert not adapter.client.is_closed  # Injected client belongs to the caller.
    adapter.client.close()


def test_corrupt_checksum_is_not_replayed_and_wrong_issuer_is_not_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=payload() if "companyfacts" in request.url.path
                              else submissions(), request=request)

    adapter = source(tmp_path, handler)
    adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS, max_archives=0)
    cache = tmp_path / CIK / "companyfacts.json"
    value = json.loads(cache.read_bytes())
    value["sha256"] = "0" * 64
    cache.write_text(json.dumps(value))
    result = adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS, max_archives=0)
    assert len(calls) == 3 and result.sources[1].cache_hit is False
    adapter.client.close()
    wrong = source(tmp_path / "wrong", lambda request: httpx.Response(200,
        json={**submissions(), "cik": "999"}, request=request))
    with pytest.raises(ValueError, match="issuer"):
        wrong.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS)
    assert not list((tmp_path / "wrong").rglob("*.json"))
    wrong.client.close()


def test_new_financial_accession_refreshes_facts_before_seven_day_ttl(tmp_path):
    now, calls = [AS_OF], []

    def handler(request):
        calls.append(str(request.url))
        current = FIRST if now[0] == AS_OF else LATER
        data = payload() if "companyfacts" in request.url.path else submissions(current)
        if "companyfacts" in request.url.path and current == LATER:
            row = data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]
            row.update(accn=LATER, val=999)
        return httpx.Response(200, json=data, request=request)

    adapter = source(tmp_path, handler, now=lambda: now[0])
    adapter.fetch(CIK, as_of=now[0], concepts=CONCEPTS, max_archives=0)
    now[0] += timedelta(hours=7)
    result = adapter.fetch(CIK, as_of=now[0], concepts=CONCEPTS, max_archives=0)
    assert len(calls) == 4 and not result.sources[1].cache_hit
    assert result.result.facts[0].value == 999
    adapter.client.close()


def test_archives_are_bounded_by_metadata_date_and_fill_explicit_acceptance_gaps(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        data = submissions()
        if "companyfacts" in request.url.path:
            data = payload()
            row = data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]
            row["accn"] = LATER
        elif request.url.path.endswith("-009.json"):
            data = submissions(LATER)["filings"]["recent"]
        else:
            data["filings"]["files"] = [
                {"name": f"CIK{CIK}-submissions-001.json", "filingTo": "2020-01-01"},
                {"name": f"CIK{CIK}-submissions-009.json", "filingTo": "2026-02-10"}]
        return httpx.Response(200, json=data, request=request)

    adapter = source(tmp_path, handler)
    result = adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS, max_archives=1)
    assert len(calls) == 3 and calls[-1].endswith("-009.json")
    assert result.archives_requested == result.remaining_archives == 1
    assert result.acceptance_count == 2 and result.result.facts[0].accession == LATER
    adapter.client.close()


@pytest.mark.parametrize("change", [
    {"accessionNumber": [FIRST, LATER]}, {"acceptanceDateTime": ["2026-02-10T22:00:00"]},
    {"acceptanceDateTime": [None]}, {"form": [{}]},
])
def test_bad_acceptance_arrays_do_not_invent_timestamps(change):
    document = submissions()
    document["filings"]["recent"].update(change)
    with pytest.raises(ValueError):
        acceptance_index([document])


def test_conflicting_archive_clocks_fail_and_naive_asof_fails_before_http(tmp_path):
    archive = submissions()["filings"]["recent"]
    archive["acceptanceDateTime"] = ["2026-02-11T01:00:00Z"]
    with pytest.raises(ValueError, match="conflicting"):
        acceptance_index([submissions(), archive])
    adapter = source(tmp_path, lambda request: pytest.fail("unexpected network"))
    with pytest.raises(ValueError, match="timezone"):
        adapter.fetch(CIK, as_of=datetime(2026, 3, 1), concepts=CONCEPTS)
    adapter.client.close()


@pytest.mark.parametrize("response", ["redirect", "oversize", "unsafe_archive"])
def test_host_size_and_archive_path_guards_preserve_cache_boundary(tmp_path, response):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if response == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.example/x"},
                                  request=request)
        if response == "oversize":
            return httpx.Response(200, content=b"{}", headers={"Content-Type": "application/json",
                "Content-Length": str(33 * 1024 * 1024)}, request=request)
        data = payload() if "companyfacts" in request.url.path else submissions()
        if "filings" in data:
            data["filings"]["files"] = [{"name": "../../evil.json", "filingTo": "2026-01-01"}]
        return httpx.Response(200, json=data, request=request)

    adapter = source(tmp_path, handler)
    with pytest.raises((ValueError, RuntimeError)):
        adapter.fetch(CIK, as_of=AS_OF, concepts=CONCEPTS)
    assert all(value.startswith("https://data.sec.gov/") for value in calls)
    assert not list(tmp_path.rglob("evil.json"))
    adapter.client.close()
