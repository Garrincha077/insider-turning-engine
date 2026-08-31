"""Focused fail-closed tests for publication-quality rate evidence."""

from __future__ import annotations

import pytest

from insider_turning_engine.notifications import assess_quality_gates


def _passing_quality() -> dict[str, object]:
    return {
        "benchmark_fresh": True,
        "canonical_valid": True,
        "scoring_methodology_complete": True,
        "parse_success_rate": 1.0,
        "market_data_coverage_rate": 0.95,
        "core_branch_coverage_rate": 0.90,
        "quality_gate_passed": True,
    }


@pytest.mark.parametrize("rate", [float("inf"), float("-inf"), float("nan"), -0.1, 1.1])
def test_quality_rates_must_be_finite_unit_interval(rate: float) -> None:
    quality = _passing_quality()
    quality["parse_success_rate"] = rate

    result = assess_quality_gates(quality)

    assert not result.allowed
    assert "INSUFFICIENT_PARSE_SUCCESS_RATE" in result.reasons


def test_mapping_rate_must_match_positive_counts() -> None:
    quality = _passing_quality()
    quality["parse_success_rate"] = {
        "numerator": 1,
        "denominator": 100,
        "rate": 1.0,
    }

    result = assess_quality_gates(quality)

    assert not result.allowed
    assert "INSUFFICIENT_PARSE_SUCCESS_RATE" in result.reasons


def test_string_quality_booleans_do_not_pass() -> None:
    quality = _passing_quality()
    quality["benchmark_fresh"] = "false"
    quality["canonical_valid"] = "true"

    result = assess_quality_gates(quality)

    assert not result.allowed
    assert "MISSING_BENCHMARK" in result.reasons
    assert "CANONICAL_INVALID" in result.reasons
