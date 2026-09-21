from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_provider_completeness_amendment"
)


def _row(
    *,
    action_id: str,
    ticker: str,
    cik: str,
    entry: str,
    target: str,
) -> dict[str, str]:
    return {
        "eventNumber": "1",
        "issuerCik": cik,
        "ticker": ticker,
        "evaluationSession": "2020-01-02",
        "entrySession": entry,
        "horizon": "252",
        "targetExitSession": target,
        "state": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "",
        "resolutionSource": "provider",
        "candidateActionTypes": "stock_mergers",
        "candidateActionIds": action_id,
    }


def _fact(
    *,
    action_id: str,
    ticker: str,
    cik: str,
    effective: str,
    successor: str,
    quantity: float,
    cash: float,
    kind: str,
) -> dict[str, object]:
    return {
        "actionId": action_id,
        "issuerCik": cik,
        "ticker": ticker,
        "effectiveDate": effective,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": kind,
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": successor,
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": cash,
        "primaryEvidence": [{"accession": "test"}],
    }


def test_qes_post_split_ratio_is_primary_evidence_term() -> None:
    action_id = "3f1999bc-0671-4ac9-832d-34a273de33b0"
    row = _row(
        action_id=action_id,
        ticker="QES",
        cik="0001704235",
        entry="2020-03-12",
        target="2021-03-12",
    )
    fact = _fact(
        action_id=action_id,
        ticker="QES",
        cik="0001704235",
        effective="2020-07-28",
        successor="KLXE",
        quantity=0.0969,
        cash=0,
        kind="PRIMARY_SEC_POST_SPLIT_STOCK_MERGER",
    )

    result = mod._resolution(row, fact)

    assert result["successorSymbol"] == "KLXE"
    assert result["successorSharesPerEntryShare"] == 0.0969
    assert result["cashPerEntryShare"] == 0


def test_wstl_one_entry_share_cashout_is_supported() -> None:
    action_id = "025514e5-df61-4736-abbd-958aef5d7747"
    row = _row(
        action_id=action_id,
        ticker="WSTL",
        cik="0001002135",
        entry="2020-09-02",
        target="2021-09-02",
    )
    fact = _fact(
        action_id=action_id,
        ticker="WSTL",
        cik="0001002135",
        effective="2020-10-01",
        successor="",
        quantity=0,
        cash=1.48,
        kind="PRIMARY_SEC_REVERSE_FORWARD_CASHOUT_ONE_ENTRY_SHARE",
    )
    fact["holderPolicy"] = "ONE_ENTRY_SHARE"

    result = mod._resolution(row, fact)

    assert result["successorSymbol"] == ""
    assert result["successorSharesPerEntryShare"] == 0
    assert result["cashPerEntryShare"] == 1.48
    assert result["holderPolicy"] == "ONE_ENTRY_SHARE"


def test_amendment_rejects_discovery_overlap() -> None:
    action_id = "5952fed5-9d9e-4228-b719-dab4e78cb1cc"
    row = _row(
        action_id=action_id,
        ticker="PAAC",
        cik="0001764711",
        entry="2018-05-01",
        target="2020-06-30",
    )
    row["evaluationSession"] = "2018-04-30"
    fact = _fact(
        action_id=action_id,
        ticker="PAAC",
        cik="0001764711",
        effective="2020-06-16",
        successor="LGHL",
        quantity=1,
        cash=0,
        kind="PRIMARY_SEC_SPAC_STOCK_EXCHANGE",
    )

    with pytest.raises(ValueError, match="overlaps frozen discovery"):
        mod._resolution(row, fact)
