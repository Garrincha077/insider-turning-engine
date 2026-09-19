from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_ps_evidence_hydration")


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _predecessor(accession: str) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": "1",
        "filingDate": "2016-01-15",
        "documentType": "4",
        "reportingOwnerCiks": ["100"],
        "transactionCount": 1,
    }


def _zero(accession: str) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": "1",
        "filingDate": "2016-02-01",
        "documentType": "4/A",
        "reportingOwnerCiks": ["100"],
        "transactionCount": 0,
    }


def test_build_targets_joins_only_frozen_scope_rows(tmp_path: Path) -> None:
    support_acc = "0000000001-16-000001"
    zero_acc = "0000000001-16-000002"
    scope = tmp_path / "scope"
    catalog = tmp_path / "catalog"
    _write(
        scope / "supporting-predecessors.jsonl",
        [
            {
                "rootPredecessorAccession": support_acc,
                "issuerCik": "0000000001",
                "rootFilingDate": "2016-01-15",
                "rootForm": "4",
            }
        ],
    )
    _write(
        scope / "amendment-ps-scope.jsonl",
        [
            {
                "amendmentAccession": zero_acc,
                "issuerCik": "0000000001",
                "status": "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT",
                "resolvedRootPredecessorAccession": support_acc,
            },
            {
                "amendmentAccession": "0000000001-16-000099",
                "issuerCik": "0000000001",
                "status": "QUARANTINE_ZERO_TRANSACTION_SCOPE_UNRESOLVED",
                "resolvedRootPredecessorAccession": None,
            },
        ],
    )
    _write(catalog / "predecessor-catalog.jsonl", [_predecessor(support_acc)])
    _write(catalog / "zero-transaction-amendments.jsonl", [_zero(zero_acc)])

    supporting, zero = mod._build_targets(
        scope_root=scope,
        catalog_root=catalog,
        year=2016,
    )
    assert [row["accession"] for row in supporting] == [support_acc]
    assert [row["accession"] for row in zero] == [zero_acc]
    assert supporting[0]["_supportingPredecessorOnly"] is True
    assert zero[0]["_rootPredecessorAccession"] == support_acc


def test_missing_supporting_predecessor_catalog_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "scope"
    catalog = tmp_path / "catalog"
    _write(
        scope / "supporting-predecessors.jsonl",
        [
            {
                "rootPredecessorAccession": "0000000001-16-000001",
                "issuerCik": "0000000001",
                "rootFilingDate": "2016-01-15",
                "rootForm": "4",
            }
        ],
    )
    _write(scope / "amendment-ps-scope.jsonl", [])
    _write(catalog / "predecessor-catalog.jsonl", [])
    _write(catalog / "zero-transaction-amendments.jsonl", [])
    with pytest.raises(ValueError, match="missing predecessor catalog evidence"):
        mod._build_targets(
            scope_root=scope,
            catalog_root=catalog,
            year=2016,
        )


def test_zero_transaction_catalog_mismatch_fails_closed(tmp_path: Path) -> None:
    zero_acc = "0000000001-16-000002"
    scope = tmp_path / "scope"
    catalog = tmp_path / "catalog"
    _write(scope / "supporting-predecessors.jsonl", [])
    _write(
        scope / "amendment-ps-scope.jsonl",
        [
            {
                "amendmentAccession": zero_acc,
                "issuerCik": "0000000001",
                "status": "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT",
                "resolvedRootPredecessorAccession": "0000000001-16-000001",
            }
        ],
    )
    bad = _zero(zero_acc)
    bad["transactionCount"] = 1
    _write(catalog / "predecessor-catalog.jsonl", [])
    _write(catalog / "zero-transaction-amendments.jsonl", [bad])
    with pytest.raises(ValueError, match="zero-transaction catalog disagrees"):
        mod._build_targets(
            scope_root=scope,
            catalog_root=catalog,
            year=2016,
        )


def test_clean_provenance_never_claims_daily_index_discovery() -> None:
    raw = SimpleNamespace(
        provenance={
            "discovery": "edgar_daily_index",
            "daily_index_url": "https://example.invalid/master.idx",
            "daily_index_hash": "sha256:old",
            "complete_submission_hash": "sha256:kept",
        }
    )
    entry = SimpleNamespace(filer_cik="0000000001")
    candidate = {
        "issuerCik": "0000000001",
        "_filed": mod.base._bulk_date("2016-01-15"),
    }
    value = mod._clean_provenance(raw, entry=entry, candidate=candidate)
    assert value["discovery"] == "verified_accession_archive_evidence"
    assert "daily_index_url" not in value
    assert "daily_index_hash" not in value
    assert value["complete_submission_hash"] == "sha256:kept"
