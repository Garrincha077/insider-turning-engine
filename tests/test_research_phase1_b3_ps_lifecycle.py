from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_ps_lifecycle")


def test_zero_classifier_requires_explicit_evidence() -> None:
    assert mod._classify_zero_text(
        "The reporting person filed a Form 4 reporting a sale of 2,500 shares "
        "that did not in fact occur."
    )[0] == "PS_LIFECYCLE_CHANGE_SUPPORTED"
    assert mod._classify_zero_text(
        "This Form 4/A does not disclose any transactions. It only discloses derivative holdings."
    )[0] == "NON_TRANSACTIONAL_NO_CHANGE_TO_PS_ECONOMICS"
    assert mod._classify_zero_text(
        "This amendment corrects information in the prior filing."
    )[0] == "QUARANTINE_AMBIGUOUS_ZERO_TRANSACTION_AMENDMENT"


def test_cancel_descriptor_extracts_side_and_shares() -> None:
    side, shares = mod._cancel_descriptor(
        "The Form 4 reported a purchase of 3,000 shares that did not in fact occur."
    )
    assert side == "BUY"
    assert str(shares) == "3000"


def test_cancel_descriptor_does_not_guess_when_both_sides_appear() -> None:
    side, _shares = mod._cancel_descriptor(
        "The exercise and sale did not occur; the purchase reference was unrelated."
    )
    assert side is None
