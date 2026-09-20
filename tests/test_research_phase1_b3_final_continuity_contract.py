from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_final_continuity_contract")


def _key_row(
    event: int,
    *,
    decision: str = "SAME_SECURITY_CONTINUITY",
) -> dict[str, object]:
    row: dict[str, object] = {
        "eventNumber": event,
        "issuerCik": f"{event:010d}",
        "ticker": f"T{event}",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-06",
        "resolutionDecision": decision,
        "resultState": (
            "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION"
            if decision == "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION"
            else "PRICE_CONTINUOUS_ADJUSTED"
        ),
    }
    if decision == "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION":
        row["basket"] = [
            {
                "symbol": "MIMO",
                "securityClass": "COMMON_STOCK",
                "quantityPerEntryUnit": 1.0,
            },
            {
                "symbol": "MIMO WS",
                "securityClass": "PUBLIC_WARRANT",
                "quantityPerEntryUnit": 1.0,
            },
        ]
    return row


def test_later_source_counts_sum_to_frozen_residual91() -> None:
    assert sum(int(spec["count"]) for spec in mod.SOURCE_SPECS) == 91
    assert len(mod.SOURCE_SPECS) == 8


def test_all_pinned_asset_digests_are_sha256() -> None:
    values = [
        mod.MULTISOURCE_ASSET_SHA256,
        *(str(spec["assetSha256"]) for spec in mod.SOURCE_SPECS),
    ]
    assert all(value.startswith("sha256:") for value in values)
    assert all(len(value) == 71 for value in values)


def test_multi_component_basket_is_preserved() -> None:
    rows = [_key_row(i) for i in range(1, 264)]
    rows.append(
        _key_row(
            264,
            decision="TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
        )
    )
    counts = mod._validate_final_rows(rows)
    assert counts["TRANSFORMED_MULTI_COMPONENT_CONSIDERATION"] == 1


def test_multi_component_basket_cannot_drop_warrant() -> None:
    rows = [_key_row(i) for i in range(1, 264)]
    basket_row = _key_row(
        264,
        decision="TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
    )
    basket_row["basket"] = basket_row["basket"][:1]
    rows.append(basket_row)
    with pytest.raises(ValueError, match="lost its basket"):
        mod._validate_final_rows(rows)


def test_boundary_rejects_performance_read() -> None:
    payload = {
        "researchOnly": True,
        "performanceRead": True,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "correctedPerformanceOpened": False,
    }
    with pytest.raises(ValueError, match="read performance"):
        mod._assert_research_boundary(payload, "fixture")
