from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from insider_turning_engine.backtest import (
    BacktestEngine,
    BacktestError,
    BacktestSignal,
    BacktestWindows,
    LookaheadError,
    ScoringProvenanceError,
    SealedOOSAccessError,
    validate_evaluation_inputs,
)
from insider_turning_engine.ingestion.market import DailyBar
from insider_turning_engine.scoring import ScoreEngine

_LOCKED_SCORING = ScoreEngine()
_FROZEN_AT = _LOCKED_SCORING.score_frozen_at


def _sessions(start: date, count: int) -> list[date]:
    values: list[date] = []
    cursor = start
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor += timedelta(days=1)
    return values


def _bars(symbol: str, sessions: list[date], *, base: int = 100) -> list[DailyBar]:
    return [
        DailyBar(
            date=session,
            symbol=symbol,
            open=Decimal(base + position),
            high=Decimal(base + position + 3),
            low=Decimal(base + position - 5),
            close=Decimal(base + position + 2),
            volume=1_000,
        )
        for position, session in enumerate(sessions)
    ]


def _signal(
    signal_id: str,
    available_at: datetime,
    *,
    ticker: str = "ACME",
    signal_type: str = "TURNING",
    score: float = 75.0,
    transaction_date: date | None = None,
    **kwargs: object,
) -> BacktestSignal:
    payload: dict[str, object] = {
        "score_config_hash": _LOCKED_SCORING.score_config_hash,
        "score_lineage": _LOCKED_SCORING.score_lineage,
        "frozen_at": _FROZEN_AT,
    }
    payload.update(kwargs)
    return BacktestSignal(
        signal_id=signal_id,
        ticker=ticker,
        signal_type=signal_type,
        score=score,
        accepted_at=available_at,
        transaction_date=transaction_date,
        **payload,
    )


def test_filing_knowledge_time_not_transaction_date_and_entry_is_next_open() -> None:
    sessions = _sessions(date(2020, 1, 2), 40)
    transaction_day = sessions[0]
    accepted = datetime(2020, 1, 8, 14, tzinfo=UTC)
    knowledge = datetime(2020, 1, 9, 14, tzinfo=UTC)
    signal = BacktestSignal(
        signal_id="knowledge",
        ticker="ACME",
        signal_type="TURNING",
        score=80,
        accepted_at=accepted,
        knowledge_at=knowledge,
        transaction_date=transaction_day,
        score_config_hash=_LOCKED_SCORING.score_config_hash,
        score_lineage=_LOCKED_SCORING.score_lineage,
        frozen_at=_FROZEN_AT,
    )

    result = BacktestEngine(horizons=(21,)).run(
        [signal], bars=_bars("ACME", sessions), spy_bars=_bars("SPY", sessions, base=200)
    )
    event = result.development.simple_benchmark.events[0]

    assert event.event_session == date(2020, 1, 9)
    assert event.event_session != transaction_day
    assert event.entry_session == date(2020, 1, 10)
    assert event.entry_open == 106.0


def test_forward_horizons_spy_excess_and_mae_use_exact_market_sessions() -> None:
    sessions = _sessions(date(2020, 1, 2), 280)
    signal = _signal("returns", datetime(2020, 1, 3, 14, tzinfo=UTC))
    result = BacktestEngine().run(
        [signal], bars=_bars("ACME", sessions), spy_bars=_bars("SPY", sessions, base=200)
    )
    event = result.development.simple_benchmark.events[0]
    entry_index = sessions.index(event.entry_session)  # type: ignore[arg-type]

    for horizon in (21, 63, 126, 252):
        outcome = event.forward_returns[horizon]
        assert outcome.exit_session == sessions[entry_index + horizon]
        expected_stock = (102 + entry_index + horizon) / (100 + entry_index) - 1.0
        expected_spy = (202 + entry_index + horizon) / (200 + entry_index) - 1.0
        assert outcome.stock_return == pytest.approx(expected_stock)
        assert outcome.spy_return == pytest.approx(expected_spy)
        assert outcome.spy_excess_return == pytest.approx(expected_stock - expected_spy)
        assert outcome.max_adverse_excursion == pytest.approx(
            (95 + entry_index) / (100 + entry_index) - 1.0
        )


def test_dedup_and_top_decile_are_deterministic_with_simple_benchmark() -> None:
    sessions = _sessions(date(2020, 1, 2), 70)
    first = _signal("first", datetime.combine(sessions[1], datetime.min.time(), tzinfo=UTC))
    duplicate = _signal(
        "duplicate", datetime.combine(sessions[21], datetime.min.time(), tzinfo=UTC)
    )
    later = _signal("later", datetime.combine(sessions[22], datetime.min.time(), tzinfo=UTC))
    cross_section = [
        _signal(
            f"score-{number}",
            datetime(2020, 4, 1, 14, tzinfo=UTC),
            ticker=f"T{number}",
            score=float(number),
        )
        for number in range(10)
    ]

    result = BacktestEngine(horizons=(21,)).run(
        [first, duplicate, later, *cross_section],
        bars=[
            *_bars("ACME", sessions),
            *[bar for number in range(10) for bar in _bars(f"T{number}", sessions)],
        ],
        spy_bars=_bars("SPY", sessions, base=200),
    )

    benchmark = result.development.simple_benchmark.events
    april = [event for event in benchmark if event.event_session == date(2020, 4, 1)]
    top = [
        event
        for event in result.development.top_decile.events
        if event.event_session == date(2020, 4, 1)
    ]
    assert result.duplicate_signal_ids == ("duplicate",)
    assert {event.signal.signal_id for event in benchmark} >= {"first", "later"}
    assert len(april) == 10
    assert [event.signal.signal_id for event in top] == ["score-9"]


def test_missing_delisted_return_is_retained_as_attrition_with_reason_count() -> None:
    sessions = _sessions(date(2020, 1, 2), 35)
    signal = _signal("gone", datetime(2020, 1, 3, 14, tzinfo=UTC), ticker="GONE")
    gone = _bars("GONE", sessions[:10])

    result = BacktestEngine(horizons=(21,), delisted_tickers={"GONE"}).run(
        [signal], bars=gone, spy_bars=_bars("SPY", sessions, base=200)
    )
    event = result.development.simple_benchmark.events[0]

    assert event.forward_returns[21].attrition_reason == "DELISTED_RETURN_21"
    assert result.attrition.reason_counts["DELISTED_RETURN_21"] == 1
    assert event.forward_returns[21].stock_return is None


def test_sealed_oos_rejects_evaluator_and_tuner_access() -> None:
    sessions = _sessions(date(2023, 1, 3), 45)
    signal = _signal("oos", datetime(2023, 1, 4, 14, tzinfo=UTC))
    result = BacktestEngine(horizons=(21,)).run(
        [signal],
        bars=_bars("ACME", sessions),
        spy_bars=_bars("SPY", sessions, base=200),
        as_of=sessions[-1],
    )

    with pytest.raises(SealedOOSAccessError):
        result.sealed_oos.for_evaluator()
    with pytest.raises(SealedOOSAccessError):
        result.sealed_oos.for_tuner()
    assert len(result.sealed_oos.final_report().results.simple_benchmark.events) == 1


def test_anti_lookahead_rejects_future_features_and_evaluation_bars() -> None:
    sessions = _sessions(date(2020, 1, 2), 30)
    available = datetime(2020, 1, 3, 14, tzinfo=UTC)
    future_feature = _signal("future-feature", available, feature_as_of=date(2020, 1, 6))

    with pytest.raises(LookaheadError, match="feature as_of"):
        BacktestEngine(horizons=(21,)).run(
            [future_feature],
            bars=_bars("ACME", sessions),
            spy_bars=_bars("SPY", sessions, base=200),
        )
    with pytest.raises(LookaheadError, match="market bar dated"):
        validate_evaluation_inputs(
            signals=[_signal("known", available)],
            bars=_bars("ACME", sessions[:2]),
            spy_bars=_bars("SPY", sessions[:3], base=200),
            as_of=sessions[1],
        )


def test_same_date_feature_timestamp_after_daily_close_is_rejected_with_timezone_precision() -> (
    None
):
    sessions = _sessions(date(2020, 1, 2), 30)
    signal = _signal(
        "future-same-day-feature",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        # US regular-session close is 21:00 UTC in January.
        feature_as_of=datetime(2020, 1, 3, 21, 0, 1, tzinfo=UTC),
    )

    with pytest.raises(LookaheadError, match="feature as_of"):
        BacktestEngine(horizons=(21,)).run(
            [signal], bars=_bars("ACME", sessions), spy_bars=_bars("SPY", sessions, base=200)
        )

    late_available = _signal(
        "future-same-day-availability",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        feature_available_at=datetime(2020, 1, 3, 21, 0, 1, tzinfo=UTC),
    )
    with pytest.raises(LookaheadError, match="feature available_at"):
        BacktestEngine(horizons=(21,)).run(
            [late_available],
            bars=_bars("ACME", sessions),
            spy_bars=_bars("SPY", sessions, base=200),
        )

    # The standalone validator enforces the same close precision when a
    # caller supplies a daily (date-only) cutoff.
    with pytest.raises(LookaheadError, match="feature as_of"):
        validate_evaluation_inputs(
            signals=[
                _signal(
                    "validator-future-feature",
                    datetime(2020, 1, 3, 14, tzinfo=UTC),
                    feature_as_of=datetime(2020, 1, 3, 21, 0, 1, tzinfo=UTC),
                )
            ],
            bars=[],
            spy_bars=[],
            as_of=date(2020, 1, 3),
        )


def test_date_only_as_of_rejects_same_day_information_after_market_close() -> None:
    session = date(2020, 1, 3)
    after_close = datetime(2020, 1, 3, 21, 0, 1, tzinfo=UTC)

    with pytest.raises(LookaheadError, match="signal knowledge/acceptance time"):
        validate_evaluation_inputs(
            signals=[_signal("late-filing", after_close)],
            bars=[],
            spy_bars=[],
            as_of=session,
        )

    late_bar = replace(_bars("ACME", [session])[0], available_at=after_close)
    with pytest.raises(LookaheadError, match="market bar available_at"):
        validate_evaluation_inputs(
            signals=[],
            bars=[late_bar],
            spy_bars=[],
            as_of=session,
        )


def test_date_only_as_of_rejects_late_feature_even_when_signal_is_outside_windows() -> None:
    session = date(2020, 1, 3)
    windows = BacktestWindows(
        development_start=date(2016, 1, 1),
        development_end=date(2016, 12, 31),
        validation_start=date(2017, 1, 1),
        validation_end=date(2017, 12, 31),
        oos_start=date(2018, 1, 1),
        oos_end=date(2018, 12, 31),
    )
    signal = _signal(
        "late-unscheduled-feature",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        feature_as_of=datetime(2020, 1, 3, 21, 0, 1, tzinfo=UTC),
    )

    with pytest.raises(LookaheadError, match="feature as_of"):
        BacktestEngine(horizons=(1,), windows=windows).run(
            [signal],
            bars=_bars("ACME", [session]),
            spy_bars=_bars("SPY", [session], base=200),
            as_of=session,
        )


def test_evaluated_runs_require_frozen_scoring_provenance_and_bounded_scores() -> None:
    sessions = _sessions(date(2020, 1, 2), 30)
    with pytest.raises(BacktestError, match=r"\[0, 100\]"):
        _signal("bad-score", datetime(2020, 1, 3, 14, tzinfo=UTC), score=100.01)

    unprovenanced = BacktestSignal(
        signal_id="unprovenanced",
        ticker="ACME",
        signal_type="TURNING",
        score=75,
        accepted_at=datetime(2020, 1, 3, 14, tzinfo=UTC),
    )
    with pytest.raises(ScoringProvenanceError, match="score_config_hash"):
        BacktestEngine(horizons=(21,)).run(
            [unprovenanced],
            bars=_bars("ACME", sessions),
            spy_bars=_bars("SPY", sessions, base=200),
        )

    forged = _signal(
        "forged-provenance",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        score_config_hash="sha256:" + "0" * 64,
        score_lineage="config/scoring.v1.yaml@sha256:" + "0" * 64,
    )
    with pytest.raises(ScoringProvenanceError, match="locked config/scoring.v1.yaml"):
        BacktestEngine(horizons=(21,)).run(
            [forged],
            bars=_bars("ACME", sessions),
            spy_bars=_bars("SPY", sessions, base=200),
        )

    forged_freeze = _signal(
        "forged-freeze",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        frozen_at=datetime(2015, 12, 31, 20, tzinfo=UTC),
    )
    with pytest.raises(ScoringProvenanceError, match="exact scoring.v1 lock frozenAt"):
        BacktestEngine(horizons=(21,)).run(
            [forged_freeze],
            bars=_bars("ACME", sessions),
            spy_bars=_bars("SPY", sessions, base=200),
        )


def test_dedup_uses_issuer_identity_and_exposure_family_across_alert_types() -> None:
    sessions = _sessions(date(2020, 1, 2), 50)
    first = _signal(
        "old-ticker",
        datetime(2020, 1, 3, 14, tzinfo=UTC),
        ticker="OLDC",
        signal_type="TURNING_ALERT",
        issuer_cik="320193",
    )
    overlap = _signal(
        "new-ticker",
        datetime(2020, 1, 6, 14, tzinfo=UTC),
        ticker="NEWC",
        signal_type="TURNING_SIGNAL",
        issuer_cik="0000320193",
    )

    result = BacktestEngine(horizons=(21,)).run(
        [first, overlap],
        bars=[*_bars("OLDC", sessions), *_bars("NEWC", sessions)],
        spy_bars=_bars("SPY", sessions, base=200),
    )

    assert result.duplicate_signal_ids == ("new-ticker",)
    assert [event.signal.signal_id for event in result.development.simple_benchmark.events] == [
        "old-ticker"
    ]


def test_missing_intermediate_stock_bar_is_named_quality_attrition() -> None:
    sessions = _sessions(date(2020, 1, 2), 35)
    signal = _signal("missing-path", datetime(2020, 1, 3, 14, tzinfo=UTC))
    stock = _bars("ACME", sessions)
    # Keep the exact 21-session exit but remove a bar inside the MAE path.
    missing_session = sessions[5]
    stock = [bar for bar in stock if bar.date != missing_session]

    result = BacktestEngine(horizons=(21,)).run(
        [signal], bars=stock, spy_bars=_bars("SPY", sessions, base=200)
    )
    event = result.development.simple_benchmark.events[0]

    assert event.forward_returns[21].max_adverse_excursion is None
    assert event.forward_returns[21].quality_reasons == ("MISSING_INTERMEDIATE_BAR_21",)
    assert result.attrition.reason_counts["MISSING_INTERMEDIATE_BAR_21"] == 1


def test_unsealed_metadata_excludes_oos_attrition_and_duplicate_ids() -> None:
    sessions = _sessions(date(2020, 1, 2), 50) + _sessions(date(2023, 1, 3), 50)
    windows = BacktestWindows(oos_end=date(2023, 3, 31))
    development = _signal("development", datetime(2020, 1, 3, 14, tzinfo=UTC))
    oos_first = _signal("oos-first", datetime(2023, 1, 3, 14, tzinfo=UTC))
    oos_duplicate = _signal("oos-duplicate", datetime(2023, 1, 4, 14, tzinfo=UTC))
    stock = _bars("ACME", sessions)
    # OOS has a missing 21-session return; development remains fully observed.
    stock = [bar for bar in stock if bar.date != date(2023, 2, 2)]

    result = BacktestEngine(horizons=(21,), windows=windows).run(
        [development, oos_first, oos_duplicate],
        bars=stock,
        spy_bars=_bars("SPY", sessions, base=200),
        as_of=date(2023, 3, 31),
    )

    assert result.duplicate_signal_ids == ()
    assert all("MISSING_RETURN_21" not in caveat.message for caveat in result.caveats)
    sealed = result.sealed_oos.final_report()
    assert sealed.duplicate_signal_ids == ("oos-duplicate",)
    assert sealed.attrition.reason_counts["MISSING_RETURN_21"] == 1
