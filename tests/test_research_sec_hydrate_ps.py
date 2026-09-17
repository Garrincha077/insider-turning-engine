from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_sec_hydrate_ps")


def _candidate(
    accession: str,
    *,
    year: int = 2016,
    quarter: int = 1,
    form: str = "4",
    buys: int = 0,
    sales: int = 0,
) -> dict[str, object]:
    return {
        "accession": accession,
        "issuerCik": "0000000001",
        "filingDate": "2016-02-01",
        "documentType": form,
        "transactionCount": buys + sales,
        "buyCount": buys,
        "saleCount": sales,
        "firstTransactionDate": "2016-01-29",
        "lastTransactionDate": "2016-01-29",
        "sourceYear": year,
        "sourceQuarter": quarter,
    }


def _write_candidates(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _canonical(
    accession: str,
    *,
    code: str,
    acquired: str,
    economic: str,
    year: int = 2016,
) -> dict[str, object]:
    return {
        "source": {"accessionNumber": accession},
        "timestamps": {
            "knowledgeAt": f"{year}-02-01T14:00:00+00:00",
            "acceptedAt": f"{year}-02-01T14:00:00+00:00",
        },
        "security": {"tableType": "NON_DERIVATIVE"},
        "transaction": {
            "code": code,
            "acquiredDisposed": acquired,
            "shares": "100",
            "pricePerShare": "10",
            "economicClassification": economic,
        },
    }


def test_loader_includes_buy_sale_and_sale_only_original_forms(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    rows = [
        _candidate("0000000001-16-000001", buys=1),
        _candidate("0000000001-16-000002", sales=1),
        _candidate("0000000001-16-000003", buys=1, sales=1),
        _candidate("0000000001-16-000004", form="4/A", sales=1),
        _candidate("0000000001-16-000005", buys=0, sales=0),
    ]
    _write_candidates(path, rows)
    selected = mod._load_ps_candidates(path, 2016, 1)
    assert [row["accession"] for row in selected] == [
        "0000000001-16-000001",
        "0000000001-16-000002",
        "0000000001-16-000003",
    ]


def test_loader_excludes_forms_other_than_original_4_or_5(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    rows = [
        _candidate("0000000001-16-000001", form="3", sales=1),
        _candidate("0000000001-16-000002", form="5", sales=1),
    ]
    _write_candidates(path, rows)
    selected = mod._load_ps_candidates(path, 2016, 1)
    assert [row["accession"] for row in selected] == ["0000000001-16-000002"]


def test_loader_hard_bounds_2023_plus(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    _write_candidates(
        path,
        [
            {
                **_candidate(
                    "0000000001-23-000001",
                    year=2023,
                    quarter=1,
                    sales=1,
                ),
                "filingDate": "2023-02-01",
            }
        ],
    )
    with pytest.raises(ValueError, match="2013-2022"):
        mod._load_ps_candidates(path, 2023, 1)


@pytest.mark.parametrize(
    ("code", "acquired", "economic", "expected"),
    [
        ("P", "A", "OPEN_MARKET_PURCHASE", "BUY"),
        ("S", "D", "OPEN_MARKET_SALE", "SALE"),
        ("S", "A", "OPEN_MARKET_SALE", None),
        ("F", "D", "TAX_WITHHOLDING", None),
    ],
)
def test_qualified_side_is_strict(
    code: str, acquired: str, economic: str, expected: str | None
) -> None:
    row = _canonical(
        "0000000001-16-000001",
        code=code,
        acquired=acquired,
        economic=economic,
    )
    assert mod._qualified_side(row) == expected


def test_concordance_separately_checks_bulk_buy_and_sale_candidates() -> None:
    candidates = [
        _candidate("0000000001-16-000001", buys=1),
        _candidate("0000000001-16-000002", sales=1),
        _candidate("0000000001-16-000003", buys=1, sales=1),
    ]
    canonical = [
        _canonical(
            "0000000001-16-000001",
            code="P",
            acquired="A",
            economic="OPEN_MARKET_PURCHASE",
        ),
        _canonical(
            "0000000001-16-000002",
            code="S",
            acquired="D",
            economic="OPEN_MARKET_SALE",
        ),
        _canonical(
            "0000000001-16-000003",
            code="P",
            acquired="A",
            economic="OPEN_MARKET_PURCHASE",
        ),
        _canonical(
            "0000000001-16-000003",
            code="S",
            acquired="D",
            economic="OPEN_MARKET_SALE",
        ),
    ]
    result = mod._concordance(candidates, canonical)
    assert result["buyCandidateAccessions"] == 2
    assert result["saleCandidateAccessions"] == 2
    assert result["buyConcordanceRate"] == 1.0
    assert result["saleConcordanceRate"] == 1.0
    assert result["missingBuyCandidateAccessions"] == []
    assert result["missingSaleCandidateAccessions"] == []


def test_concordance_rejects_sealed_2023_canonical_evidence() -> None:
    candidates = [_candidate("0000000001-16-000001", sales=1)]
    canonical = [
        _canonical(
            "0000000001-16-000001",
            code="S",
            acquired="D",
            economic="OPEN_MARKET_SALE",
            year=2023,
        )
    ]
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._concordance(candidates, canonical)


def test_pilot_pass_requires_sale_only_and_both_concordance_rates() -> None:
    mix = {"buyOnlyFilings": 1, "saleOnlyFilings": 1, "mixedBuySaleFilings": 1}
    concordance = {"buyConcordanceRate": 1.0, "saleConcordanceRate": 0.995}
    assert mod._pilot_passed(mix, concordance) is True

    no_sale_only = {**mix, "saleOnlyFilings": 0}
    assert mod._pilot_passed(no_sale_only, concordance) is False

    weak_sale = {**concordance, "saleConcordanceRate": 0.994}
    assert mod._pilot_passed(mix, weak_sale) is False
