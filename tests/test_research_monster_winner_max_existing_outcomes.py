from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod=importlib.import_module("research_monster_winner_max_existing_outcomes")


def test_semantic_key_ignores_event_number() -> None:
    row={
        "eventNumber":999,
        "issuerCik":"0001",
        "ticker":"abc",
        "evaluationSession":"2021-01-04",
        "entrySession":"2021-01-05",
        "horizon":"126",
        "targetExitSession":"2021-07-06",
    }
    assert mod._semantic_key(row)==(
        "0001","ABC","2021-01-04","2021-01-05","126","2021-07-06"
    )


def test_unresolved_without_crossing_is_unknown() -> None:
    assert mod._label(
        values=[10.0,11.0,None,12.0],
        entry_open=10.0,
        multiple=2.0,
        forced_unknown=True,
    )=="UNKNOWN"


def test_unresolved_observed_crossing_is_positive() -> None:
    assert mod._label(
        values=[10.0,None,21.0,None],
        entry_open=10.0,
        multiple=2.0,
        forced_unknown=True,
    )=="POSITIVE"


def test_complete_no_crossing_can_be_negative() -> None:
    assert mod._label(
        values=[10.0]*20,
        entry_open=10.0,
        multiple=2.0,
        forced_unknown=False,
    )=="NEGATIVE"


def test_provider_unresolved_action_cuts_path_at_action_date() -> None:
    terms={
        "mode":"UNRESOLVED_ACTION",
        "effectiveDate":"2021-06-15",
        "successor":"",
        "quantity":0.0,
        "cash":0.0,
        "forcedUnknown":True,
    }
    maps={"OLD":{
        "2021-06-14":(10.0,11.0,100,10,False),
        "2021-06-15":(10.0,12.0,100,10,False),
    }}
    assert mod._path_value(
        day="2021-06-14",ticker="OLD",terms=terms,maps=maps
    )==11.0
    assert mod._path_value(
        day="2021-06-15",ticker="OLD",terms=terms,maps=maps
    ) is None


def test_stock_dividend_contract_uses_adjusted_same_series() -> None:
    terms=mod._contract_terms("OLD",{
        "resolutionDecision":"TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind":"STOCK_DIVIDEND_QUANTITY",
        "effectiveDate":"2021-06-15",
        "successorSymbol":"OLD",
        "successorSharesPerEntryShare":"1.1",
        "cashPerEntryShare":"0",
    })
    assert terms["mode"]=="ORDINARY"
    assert terms["successor"]=="OLD"
    assert terms["quantity"]==1.0
