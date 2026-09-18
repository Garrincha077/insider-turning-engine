from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_ps_amendment_scope")


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _candidate(accession: str, *, buy: int = 0, sale: int = 0) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": "0000000001",
        "filingDate": "2016-01-15",
        "documentType": "4",
        "buyCount": buy,
        "saleCount": sale,
        "transactionCount": buy + sale,
        "sourceYear": 2016,
        "sourceQuarter": 1,
    }


def _pred(
    accession: str,
    *,
    issuer: str = "0000000001",
    date: str = "2016-01-15",
    owners: list[str] | None = None,
) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": issuer,
        "filingDate": date,
        "documentType": "4",
        "reportingOwnerCiks": owners or ["0000000100"],
        "transactionCount": 1,
        "buyCount": 0,
        "saleCount": 0,
        "sourceYear": 2016,
        "sourceQuarter": 1,
    }


def _amendment(
    accession: str,
    *,
    original_date: str | None = "2016-01-15",
    owners: list[str] | None = None,
) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": "0000000001",
        "filingDate": "2016-02-01",
        "documentType": "4/A",
        "reportingOwnerCiks": owners or ["0000000100"],
        "transactionCount": 1,
        "buyCount": 0,
        "saleCount": 1,
        "sourceYear": 2016,
        "sourceQuarter": 1,
        "originalSubmissionDate": original_date,
    }


def _canonical(
    accession: str,
    *,
    code: str = "S",
    ad: str = "D",
    economic: str = "OPEN_MARKET_SALE",
    table: str = "NON_DERIVATIVE",
    shares: str = "10",
    price: str = "12",
    year: int = 2016,
) -> dict[str, object]:
    return {
        "source": {"accessionNumber": accession},
        "timestamps": {
            "knowledgeAt": f"{year}-02-01T12:00:00+00:00",
            "acceptedAt": f"{year}-02-01T12:00:00+00:00",
        },
        "security": {"tableType": table},
        "transaction": {
            "code": code,
            "acquiredDisposed": ad,
            "economicClassification": economic,
            "shares": shares,
            "pricePerShare": price,
        },
    }


def _roots(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    root = tmp_path / "ps"
    _write(root / "2016" / "candidates.jsonl", rows)
    return root


def _catalogs(
    tmp_path: Path,
    *,
    amendments: list[dict[str, object]],
    predecessors: list[dict[str, object]],
    zero: list[dict[str, object]] | None = None,
) -> Path:
    root = tmp_path / "catalog"
    _write(root / "2016" / "amendment-candidates.jsonl", amendments)
    _write(root / "2016" / "predecessor-catalog.jsonl", predecessors)
    _write(root / "2016" / "zero-transaction-amendments.jsonl", zero or [])
    return root


def _canon_root(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    root = tmp_path / "amend"
    _write(root / "2016q1" / "canonical-research.jsonl", rows)
    return root


def test_root_in_ps_universe_is_in_scope(tmp_path: Path) -> None:
    root_acc = "0000000001-16-000001"
    amend_acc = "0000000001-16-000002"
    ps = _roots(tmp_path, [_candidate(root_acc, buy=1)])
    catalogs = _catalogs(
        tmp_path,
        amendments=[_amendment(amend_acc)],
        predecessors=[_pred(root_acc)],
    )
    amendments = _canon_root(tmp_path, [_canonical(amend_acc, code="F", ad="D", economic="TAX_WITHHOLDING")])
    out = tmp_path / "out"
    summary = mod.build(
        ps_candidate_root=ps,
        amendment_root=amendments,
        catalog_root=catalogs,
        output=out,
    )
    rows = mod._read_jsonl(out / "amendment-ps-scope.jsonl")
    assert rows[0]["status"] == "ROOT_IN_PS_UNIVERSE"
    assert summary["statusCounts"]["ROOT_IN_PS_UNIVERSE"] == 1


def test_qualified_sale_amendment_outside_ps_requires_supporting_predecessor(
    tmp_path: Path,
) -> None:
    ps_root = "0000000001-16-000001"
    outside_root = "0000000001-16-000010"
    amend_acc = "0000000001-16-000020"
    ps = _roots(tmp_path, [_candidate(ps_root, buy=1)])
    catalogs = _catalogs(
        tmp_path,
        amendments=[_amendment(amend_acc)],
        predecessors=[_pred(outside_root)],
    )
    amendments = _canon_root(tmp_path, [_canonical(amend_acc)])
    out = tmp_path / "out"
    summary = mod.build(
        ps_candidate_root=ps,
        amendment_root=amendments,
        catalog_root=catalogs,
        output=out,
    )
    scope = mod._read_jsonl(out / "amendment-ps-scope.jsonl")
    supporting = mod._read_jsonl(out / "supporting-predecessors.jsonl")
    assert scope[0]["status"] == "SUPPORTING_PREDECESSOR_REQUIRED"
    assert supporting[0]["rootPredecessorAccession"] == outside_root
    assert summary["supportingPredecessorFilingsRequired"] == 1


def test_outside_root_and_non_ps_amendment_is_outside_scope(tmp_path: Path) -> None:
    ps_root = "0000000001-16-000001"
    outside_root = "0000000001-16-000010"
    amend_acc = "0000000001-16-000020"
    ps = _roots(tmp_path, [_candidate(ps_root, buy=1)])
    catalogs = _catalogs(
        tmp_path,
        amendments=[_amendment(amend_acc)],
        predecessors=[_pred(outside_root)],
    )
    amendments = _canon_root(
        tmp_path,
        [_canonical(amend_acc, code="F", ad="D", economic="TAX_WITHHOLDING")],
    )
    out = tmp_path / "out"
    mod.build(
        ps_candidate_root=ps,
        amendment_root=amendments,
        catalog_root=catalogs,
        output=out,
    )
    scope = mod._read_jsonl(out / "amendment-ps-scope.jsonl")
    assert scope[0]["status"] == "OUTSIDE_PS_ECONOMIC_SCOPE"


def test_zero_transaction_amendment_on_ps_root_is_explicit(tmp_path: Path) -> None:
    root_acc = "0000000001-16-000001"
    zero_acc = "0000000001-16-000030"
    ps = _roots(tmp_path, [_candidate(root_acc, sale=1)])
    zero = {
        **_amendment(zero_acc),
        "transactionCount": 0,
        "buyCount": 0,
        "saleCount": 0,
    }
    catalogs = _catalogs(
        tmp_path,
        amendments=[],
        predecessors=[_pred(root_acc)],
        zero=[zero],
    )
    amendments = _canon_root(tmp_path, [])
    out = tmp_path / "out"
    summary = mod.build(
        ps_candidate_root=ps,
        amendment_root=amendments,
        catalog_root=catalogs,
        output=out,
    )
    scope = mod._read_jsonl(out / "amendment-ps-scope.jsonl")
    assert scope[0]["status"] == "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT"
    assert scope[0]["acceptanceHydrationRequired"] is True
    assert summary["statusCounts"]["ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT"] == 1


def test_ambiguous_predecessor_is_quarantined(tmp_path: Path) -> None:
    ps_root = "0000000001-16-000001"
    amend_acc = "0000000001-16-000020"
    ps = _roots(tmp_path, [_candidate(ps_root, buy=1)])
    catalogs = _catalogs(
        tmp_path,
        amendments=[_amendment(amend_acc)],
        predecessors=[
            _pred("0000000001-16-000010"),
            _pred("0000000001-16-000011"),
        ],
    )
    amendments = _canon_root(tmp_path, [_canonical(amend_acc)])
    out = tmp_path / "out"
    summary = mod.build(
        ps_candidate_root=ps,
        amendment_root=amendments,
        catalog_root=catalogs,
        output=out,
    )
    scope = mod._read_jsonl(out / "amendment-ps-scope.jsonl")
    assert scope[0]["status"] == "QUARANTINE_UNRESOLVED_QUALIFIED_PS_AMENDMENT"
    assert scope[0]["reason"] == "AMBIGUOUS_PREDECESSOR_CATALOG_MATCH"
    assert summary["quarantineRows"] == 1


def test_derivative_sale_is_not_qualified_ps(tmp_path: Path) -> None:
    row = _canonical(
        "0000000001-16-000020",
        table="DERIVATIVE",
        code="S",
        ad="D",
        economic="OPEN_MARKET_SALE",
    )
    assert mod._qualified_side(row) is None


def test_2023_plus_amendment_evidence_is_rejected(tmp_path: Path) -> None:
    root_acc = "0000000001-16-000001"
    amend_acc = "0000000001-16-000020"
    ps = _roots(tmp_path, [_candidate(root_acc, buy=1)])
    catalogs = _catalogs(
        tmp_path,
        amendments=[_amendment(amend_acc)],
        predecessors=[_pred(root_acc)],
    )
    amendments = _canon_root(tmp_path, [_canonical(amend_acc, year=2023)])
    with pytest.raises(ValueError, match="sealed OOS"):
        mod.build(
            ps_candidate_root=ps,
            amendment_root=amendments,
            catalog_root=catalogs,
            output=tmp_path / "out",
        )


def test_owner_subset_is_required_for_root_resolution(tmp_path: Path) -> None:
    evidence = _amendment("0000000001-16-000020", owners=["0000000100", "0000000200"])
    catalog = mod._catalog_index([
        _pred("0000000001-16-000001", owners=["0000000100"]),
    ])
    root, reason, count = mod._resolve_root(evidence, catalog)
    assert root is None
    assert reason == "NO_PREDECESSOR_CATALOG_MATCH"
    assert count == 0
