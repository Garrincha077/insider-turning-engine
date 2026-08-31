from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from insider_turning_engine.backtest import (
    BacktestEvent,
    BacktestPeriod,
    BacktestSignal,
    EvaluationStage,
    EventGroup,
    ForwardReturn,
    PeriodResults,
    ReportingError,
    ValidationEvidence,
    bootstrap_median_ci,
    build_backtest_report,
    summarize_events,
)
from insider_turning_engine.backtest import evaluate_formal_gate as _evaluate_formal_gate
from insider_turning_engine.backtest.reporting import BenchmarkComparison
from insider_turning_engine.scoring import ScoreEngine

_LOCKED_SCORING = ScoreEngine()
_FROZEN_AT = _LOCKED_SCORING.score_frozen_at


def evaluate_formal_gate(*args, **kwargs):
    kwargs.setdefault("evaluation_stage", EvaluationStage.DEV_VALIDATION)
    return _evaluate_formal_gate(*args, **kwargs)

_EVIDENCE = ValidationEvidence(
    parse_success_rate=0.995,
    market_coverage=0.90,
    core_branch_coverage=0.85,
    canonical_valid=True,
    schema_valid=True,
    hash_valid=True,
    temporal_valid=True,
    benchmark_fresh=True,
    scoring_methodology_complete=True,
)


def _events(values: list[float], *, name: str = "group") -> tuple[BacktestEvent, ...]:
    rows: list[BacktestEvent] = []
    for index, value in enumerate(values):
        signal = BacktestSignal(
            signal_id=f"{name}-{index}",
            ticker=f"T{index}",
            signal_type="TURNING",
            score=float(index % 101),
            accepted_at=datetime(2020, 1, 2, 14, tzinfo=UTC),
            sector="Technology",
            score_config_hash=_LOCKED_SCORING.score_config_hash,
            score_lineage=_LOCKED_SCORING.score_lineage,
            methodology_hash=_LOCKED_SCORING.methodology_hash,
            methodology_status=_LOCKED_SCORING.methodology_status,
            frozen_at=_FROZEN_AT,
        )
        rows.append(
            BacktestEvent(
                signal=signal,
                period=BacktestPeriod.OOS,
                event_session=date(2020, 1, 2),
                entry_session=date(2020, 1, 3),
                entry_open=100.0,
                forward_returns={
                    63: ForwardReturn(63, date(2020, 4, 1), value, 0.0, value, -0.1),
                    126: ForwardReturn(126, date(2020, 7, 1), value, 0.0, value, -0.1),
                    252: ForwardReturn(252, date(2021, 1, 1), value, 0.0, value, -0.1),
                },
            )
        )
    return tuple(rows)


def _comparison(name: str, values: list[float]) -> BenchmarkComparison:
    events = _events(values, name=name)
    return _comparison_from_events(name, events)


def _comparison_from_events(name: str, events: tuple[BacktestEvent, ...]) -> BenchmarkComparison:
    group = EventGroup(name, BacktestPeriod.OOS, events)
    from insider_turning_engine.backtest.reporting import summarize_group

    return summarize_group(group)


def test_bootstrap_median_is_seeded_and_omits_missing() -> None:
    first = bootstrap_median_ci([1.0, None, 3.0, 5.0], iterations=500, seed=41)
    second = bootstrap_median_ci([1.0, None, 3.0, 5.0], iterations=500, seed=41)
    assert first == second
    assert first.estimate == 3.0
    assert first.lower is not None and first.upper is not None


def test_formal_gate_passes_only_with_positive_ci_and_two_hundred_events() -> None:
    full = _comparison("full_engine", [0.20] * 220)
    simple = _comparison("simple_ps", [0.01] * 220)
    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=_EVIDENCE,
        iterations=300,
        seed=7,
    )
    assert assessment.status == "PASS"
    assert assessment.interval.lower is not None and assessment.interval.lower > 0


def test_formal_gate_is_inconclusive_when_interval_crosses_zero_or_sample_is_small() -> None:
    full = _comparison("full_engine", [-0.30, 0.50] * 20)
    simple = _comparison("simple_ps", [0.0] * 40)
    crossing = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=_EVIDENCE,
        iterations=300,
        seed=7,
    )
    assert crossing.status == "INCONCLUSIVE"

    positive = _comparison("full_engine", [0.20] * 20)
    small = _comparison("simple_ps", [0.01] * 20)
    insufficient = evaluate_formal_gate(
        [positive, small],
        sealed_oos_events=20,
        validation_evidence=_EVIDENCE,
        iterations=300,
        seed=7,
    )
    assert insufficient.status == "INCONCLUSIVE"


def test_formal_gate_fails_on_non_positive_point_estimate() -> None:
    full = _comparison("full_engine", [0.01] * 25)
    simple = _comparison("simple_ps", [0.02] * 25)
    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=_EVIDENCE,
        iterations=300,
        seed=7,
    )
    assert assessment.status == "FAIL"
    assert assessment.point_estimate is not None and assessment.point_estimate < 0


def test_metric_summary_has_requested_horizons_and_tail_metrics() -> None:
    summary = summarize_events(_events([-0.2, 0.1, 0.4]), 126)
    assert summary.observed_count == 3
    assert summary.win_rate == pytest.approx(2 / 3)
    assert summary.downside_tail is not None
    assert summary.median_mae == pytest.approx(-0.1)


def test_formal_gate_never_passes_without_required_validation_evidence() -> None:
    full = _comparison("full_engine", [0.20] * 220)
    simple = _comparison("simple_ps", [0.01] * 220)

    assessment = evaluate_formal_gate([full, simple], sealed_oos_events=220, iterations=300, seed=7)

    assert assessment.status == "INCONCLUSIVE"
    assert "evidence is missing" in assessment.reason


def test_formal_gate_counts_observed_eligible_not_retained_oos_events() -> None:
    full_events = list(_events([0.20] * 220, name="full_engine"))
    simple_events = list(_events([0.01] * 220, name="simple_ps"))
    for index in range(25, 220):
        original = full_events[index]
        full_events[index] = BacktestEvent(
            signal=original.signal,
            period=original.period,
            event_session=original.event_session,
            entry_session=original.entry_session,
            entry_open=original.entry_open,
            forward_returns={
                **original.forward_returns,
                126: ForwardReturn(
                    126, date(2020, 7, 1), None, None, None, None, "MISSING_RETURN_126"
                ),
            },
        )
    full = _comparison_from_events("full_engine", tuple(full_events))
    simple = _comparison_from_events("simple_ps", tuple(simple_events))

    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=_EVIDENCE,
        iterations=300,
        seed=7,
    )

    assert assessment.status == "INCONCLUSIVE"
    assert assessment.observed_eligible_oos_outcomes == 25
    assert "observed eligible" in assessment.reason


def test_failed_validation_evidence_is_fail_closed() -> None:
    full = _comparison("full_engine", [0.20] * 220)
    simple = _comparison("simple_ps", [0.01] * 220)
    failed = ValidationEvidence(
        parse_success_rate=0.995,
        market_coverage=0.90,
        core_branch_coverage=0.85,
        canonical_valid=True,
        schema_valid=True,
        hash_valid=True,
        temporal_valid=True,
        benchmark_fresh=False,
        scoring_methodology_complete=True,
    )

    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=failed,
        iterations=300,
        seed=7,
    )

    assert assessment.status == "FAIL"
    assert "benchmark freshness" in assessment.reason


def test_caller_methodology_boolean_cannot_override_lock_derived_state() -> None:
    full = _comparison("full_engine", [0.20] * 220)
    simple = _comparison("simple_ps", [0.01] * 220)

    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=replace(_EVIDENCE, scoring_methodology_complete=False),
        iterations=300,
        seed=7,
    )

    assert assessment.status == "PASS"


def test_string_validation_flags_cannot_be_truthy_coerced() -> None:
    full = _comparison("full_engine", [0.20] * 220)
    simple = _comparison("simple_ps", [0.01] * 220)
    malformed = {
        "parse_success_rate": 0.995,
        "market_coverage": 0.90,
        "core_branch_coverage": 0.85,
        "canonical_valid": "false",
        "schema_valid": True,
        "hash_valid": True,
        "temporal_valid": True,
        "benchmark_fresh": True,
        "scoring_methodology_complete": True,
    }

    assessment = evaluate_formal_gate(
        [full, simple],
        sealed_oos_events=220,
        validation_evidence=malformed,
        iterations=300,
        seed=7,
    )

    assert assessment.status == "FAIL"
    assert "malformed" in assessment.reason


def test_report_discloses_adjustment_and_data_quality_counts() -> None:
    events = _events([0.10, 0.20])
    results = PeriodResults(
        BacktestPeriod.VALIDATION,
        EventGroup("top_decile", BacktestPeriod.VALIDATION, events),
        EventGroup("simple_benchmark", BacktestPeriod.VALIDATION, events),
    )

    report = build_backtest_report(
        results,
        period=BacktestPeriod.VALIDATION,
        validation_evidence=_EVIDENCE,
        bootstrap_iterations=300,
        bootstrap_seed=7,
    )

    assert report.data_quality.adjustment_basis_counts == {"UNKNOWN": 2}
    assert report.data_quality.ticker_identity_missing_count == 2
    assert report.data_quality.sector_missing_count == 0
    assert report.data_quality.missing_return_count == 0
    assert "ADJUSTMENT_BASIS_COUNTS" in {caveat.code for caveat in report.caveats}
    assert report.scoring_provenance.score_config_hash == _LOCKED_SCORING.score_config_hash
    assert report.scoring_provenance.score_lineage == _LOCKED_SCORING.score_lineage
    assert report.scoring_provenance.methodology_hash == _LOCKED_SCORING.methodology_hash
    assert report.scoring_provenance.methodology_status == "CANDIDATE"
    assert report.scoring_provenance.frozen_at is None
    assert report.gate is None
    assert {row.name for row in report.benchmark_table} == {
        "full_engine",
        "simple_benchmark",
    }


def test_oos_report_rejects_candidate_methodology_before_sensitivity() -> None:
    events = _events([0.10])
    results = PeriodResults(
        BacktestPeriod.OOS,
        EventGroup("top_decile", BacktestPeriod.OOS, events),
        EventGroup("simple_benchmark", BacktestPeriod.OOS, events),
    )

    with pytest.raises(ReportingError, match="FROZEN, complete methodology lock"):
        build_backtest_report(
            results,
            sensitivity_scenarios={"threshold-search": {"scores": [60, 70], "threshold": 65}},
        )


def test_report_rejects_mixed_scoring_provenance() -> None:
    events = list(_events([0.10, 0.20]))
    events[1] = replace(
        events[1],
        signal=replace(events[1].signal, methodology_hash="sha256:" + "0" * 64),
    )
    rows = tuple(events)
    results = PeriodResults(
        BacktestPeriod.VALIDATION,
        EventGroup("top_decile", BacktestPeriod.VALIDATION, rows),
        EventGroup("simple_benchmark", BacktestPeriod.VALIDATION, rows),
    )

    with pytest.raises(ReportingError, match="share one scoring.v1 methodology"):
        build_backtest_report(results, period=BacktestPeriod.VALIDATION)


def test_report_rejects_missing_scoring_provenance() -> None:
    event = _events([0.10])[0]
    event = replace(
        event,
        signal=replace(
            event.signal,
            score_config_hash=None,
            score_lineage=None,
            methodology_hash=None,
            methodology_status=None,
            frozen_at=None,
        ),
    )
    rows = (event,)
    results = PeriodResults(
        BacktestPeriod.VALIDATION,
        EventGroup("top_decile", BacktestPeriod.VALIDATION, rows),
        EventGroup("simple_benchmark", BacktestPeriod.VALIDATION, rows),
    )

    with pytest.raises(ReportingError, match="score_config_hash"):
        build_backtest_report(results, period=BacktestPeriod.VALIDATION)
