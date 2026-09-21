from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_residual33_scope"
)


def _row(event: int, ticker: str = "TEST") -> dict[str, object]:
    return {
        "eventNumber": event,
        "issuerCik": f"{event:010d}",
        "ticker": ticker,
        "evaluationSession": "2021-01-04",
        "entrySession": "2021-01-05",
        "horizon": 126,
        "targetExitSession": "2021-07-07",
    }


def test_key_digest_is_order_invariant() -> None:
    a = _row(1)
    b = _row(2)
    assert mod._key_digest([a, b]) == mod._key_digest([b, a])


def test_key_tuple_includes_event_number() -> None:
    a = _row(1)
    b = _row(2)
    b["issuerCik"] = a["issuerCik"]
    assert mod._key_tuple(a) != mod._key_tuple(b)


def test_frozen_counts_are_consistent() -> None:
    assert mod.EXPECTED_AUDIT_ROWS == 41
    assert mod.EXPECTED_RESOLVED_ROWS == 8
    assert mod.EXPECTED_RESIDUAL_ROWS == 33
    assert (
        mod.EXPECTED_RESOLVED_ROWS + mod.EXPECTED_RESIDUAL_ROWS
        == mod.EXPECTED_AUDIT_ROWS
    )
