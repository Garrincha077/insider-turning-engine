from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_sec_hydrate_with_fallback")


def _candidate(
    *,
    issuer: str = "0000105319",
    owners: list[str] | None = None,
) -> dict[str, object]:
    return {
        "accession": "0001209191-14-050967",
        "issuerCik": issuer,
        "documentType": "4",
        "_filed": date(2014, 8, 6),
        "reportingOwnerCiks": owners if owners is not None else ["0001053905"],
    }


def test_archive_fallback_uses_verified_issuer_cik_first() -> None:
    entries = mod._direct_entries(_candidate())
    assert entries[0].filer_cik == "0000105319"
    assert entries[0].submission_path == (
        "edgar/data/105319/000120919114050967/0001209191-14-050967.txt"
    )
    assert mod._archive_cik_basis(entries[0], _candidate()) == "ISSUER_CIK"


def test_reporting_owner_paths_remain_secondary() -> None:
    candidate = _candidate(owners=["0001053905", "0001053906"])
    entries = mod._direct_entries(candidate)
    assert [entry.filer_cik for entry in entries] == [
        "0000105319",
        "0001053905",
        "0001053906",
    ]
    assert [mod._archive_cik_basis(entry, candidate) for entry in entries] == [
        "ISSUER_CIK",
        "REPORTING_OWNER_CIK",
        "REPORTING_OWNER_CIK",
    ]


def test_duplicate_owner_equal_to_issuer_is_not_repeated() -> None:
    candidate = _candidate(owners=["0000105319", "1053905"])
    entries = mod._direct_entries(candidate)
    assert [entry.filer_cik for entry in entries] == [
        "0000105319",
        "0001053905",
    ]


def test_issuer_cik_is_sufficient_even_without_reporting_owners() -> None:
    candidate = _candidate(owners=[])
    entries = mod._direct_entries(candidate)
    assert len(entries) == 1
    assert entries[0].filer_cik == "0000105319"


@pytest.mark.parametrize("issuer", ["", "ABC", "12345678901"])
def test_invalid_issuer_cik_is_rejected(issuer: str) -> None:
    with pytest.raises(ValueError, match="issuer CIK"):
        mod._direct_entries(_candidate(issuer=issuer))


def test_invalid_reporting_owner_cik_is_rejected() -> None:
    with pytest.raises(ValueError, match="reporting-owner CIK"):
        mod._direct_entries(_candidate(owners=["OWNER"]))


class _Source:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def fetch_entry(self, entry: object, *, index_hash: str) -> object:
        filer_cik = entry.filer_cik
        self.calls.append(filer_cik)
        outcome = self.outcomes[filer_cik]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_fetch_verified_archive_stops_on_issuer_success() -> None:
    raw = object()
    source = _Source({"0000105319": raw, "0001053905": object()})
    result, entry = mod._fetch_verified_archive(
        candidate=_candidate(),
        source=source,
    )
    assert result is raw
    assert entry.filer_cik == "0000105319"
    assert source.calls == ["0000105319"]


def test_fetch_verified_archive_uses_owner_only_after_issuer_404() -> None:
    raw = object()
    source = _Source(
        {
            "0000105319": RuntimeError("404 Not Found"),
            "0001053905": raw,
        }
    )
    result, entry = mod._fetch_verified_archive(
        candidate=_candidate(),
        source=source,
    )
    assert result is raw
    assert entry.filer_cik == "0001053905"
    assert source.calls == ["0000105319", "0001053905"]


def test_fallback_reason_accepts_only_frozen_recovery_cases() -> None:
    assert (
        mod._fallback_reason_for_failure(
            {
                "stage": "DISCOVERY",
                "reason": "ACCESSION_NOT_FOUND_WITHIN_10_DAYS",
            }
        )
        == "not_found_in_daily_index_within_10_days"
    )
    assert (
        mod._fallback_reason_for_failure(
            {
                "stage": "HYDRATE_PARSE_VALIDATE",
                "reason": "RuntimeError",
                "message": mod.OVERSIZED_SEC_RESPONSE_MESSAGE,
            }
        )
        == "daily_index_fetch_response_exceeds_configured_size_limit"
    )
    assert (
        mod._fallback_reason_for_failure(
            {
                "stage": "HYDRATE_PARSE_VALIDATE",
                "reason": "RuntimeError",
                "message": "SEC daily-index request failed: unrelated error",
            }
        )
        is None
    )
    assert (
        mod._fallback_reason_for_failure(
            {
                "stage": "HYDRATE_PARSE_VALIDATE",
                "reason": "ValueError",
                "message": mod.OVERSIZED_SEC_RESPONSE_MESSAGE,
            }
        )
        is None
    )

def test_verified_archive_cap_is_bounded_by_daily_index_source_contract() -> None:
    assert mod.MAX_CONFIGURABLE_SUBMISSION_BYTES == 100 * 1024 * 1024

