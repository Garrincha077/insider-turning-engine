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
