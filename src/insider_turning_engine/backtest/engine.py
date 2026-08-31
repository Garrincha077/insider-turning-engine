"""Deterministic, daily-close, point-in-time event backtesting.

This module makes the information boundary intentionally visible:

* a filing is scheduled from ``knowledge_at``/``accepted_at``, never its
  transaction date;
* a signal is evaluated at the first market daily close at or after that
  timestamp, then enters at the following market-session open;
* only event-time inputs are checked for look-ahead.  Subsequent bars are
  outcome observations and cannot influence selection.
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from insider_turning_engine.domain.time import us_equity_session_close
from insider_turning_engine.ingestion.market.base import DailyBar
from insider_turning_engine.scoring import ScoreEngine

from .models import (
    HORIZONS,
    AttritionReport,
    BacktestCaveat,
    BacktestError,
    BacktestEvent,
    BacktestPeriod,
    BacktestResult,
    BacktestSignal,
    EventGroup,
    ForwardReturn,
    LookaheadError,
    OOSReport,
    PeriodResults,
    ScoringProvenanceError,
    SealedOOSResults,
)


@dataclass(frozen=True, slots=True)
class BacktestWindows:
    """The fixed model-development policy and the bounded sealed OOS window."""

    development_start: date = date(2016, 1, 1)
    development_end: date = date(2020, 12, 31)
    validation_start: date = date(2021, 1, 1)
    validation_end: date = date(2022, 12, 31)
    oos_start: date = date(2023, 1, 1)
    oos_end: date = date(2023, 1, 31)

    def period_for(self, session: date) -> BacktestPeriod | None:
        if self.development_start <= session <= self.development_end:
            return BacktestPeriod.DEVELOPMENT
        if self.validation_start <= session <= self.validation_end:
            return BacktestPeriod.VALIDATION
        if self.oos_start <= session <= self.oos_end:
            return BacktestPeriod.OOS
        return None


def last_complete_month_end(reference: date | datetime) -> date:
    """Return the last calendar day of the complete month before ``reference``."""

    current = reference.date() if isinstance(reference, datetime) else reference
    return current.replace(day=1) - timedelta(days=1)


def default_windows(reference: date | datetime) -> BacktestWindows:
    """Construct fixed development/validation windows plus bounded sealed OOS."""

    return BacktestWindows(oos_end=last_complete_month_end(reference))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise BacktestError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _as_cutoff(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    return datetime.combine(value, time.max, tzinfo=UTC)


def _bar_value(value: Decimal) -> float:
    number = float(value)
    if number <= 0:
        raise BacktestError("market prices must be positive")
    return number


def _bar_index(bars: Iterable[DailyBar], *, label: str) -> dict[str, dict[date, DailyBar]]:
    by_symbol: dict[str, dict[date, DailyBar]] = defaultdict(dict)
    for bar in bars:
        if not isinstance(bar, DailyBar):
            raise BacktestError(f"{label} contains a non-DailyBar value")
        symbol = bar.symbol.upper()
        if bar.date in by_symbol[symbol]:
            raise BacktestError(f"duplicate {label} bar for {symbol} on {bar.date.isoformat()}")
        by_symbol[symbol][bar.date] = bar
    return dict(by_symbol)


def _flatten_bars(
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
) -> tuple[DailyBar, ...]:
    if isinstance(bars, Mapping):
        return tuple(bar for values in bars.values() for bar in values)
    return tuple(bars)


def validate_evaluation_inputs(
    *,
    signals: Iterable[BacktestSignal],
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
    spy_bars: Iterable[DailyBar],
    as_of: date | datetime,
    require_scoring_provenance: bool = False,
    windows: BacktestWindows | None = None,
) -> None:
    """Fail closed if a purported evaluation dataset crosses ``as_of``.

    This helper is for the inputs used to create a signal snapshot.  Outcome
    bars used later by :meth:`BacktestEngine.run` are intentionally separate:
    they measure a selected event and do not participate in event selection.
    """

    cutoff = _as_cutoff(as_of)
    # A date cutoff denotes the US regular-session close, not the end of the
    # UTC calendar day.  Keep market-bar date checks date-based, but apply the
    # exact close to every information-availability timestamp so a filing,
    # feature, or provider publication received later that day cannot slip
    # through a date-only snapshot.
    information_cutoff = (
        us_equity_session_close(cutoff.date()) if not isinstance(as_of, datetime) else cutoff
    )
    signal_rows = tuple(signals)
    for signal in signal_rows:
        if _as_utc(signal.availability_at) > information_cutoff:
            raise LookaheadError("signal knowledge/acceptance time later than evaluation as_of")
        if signal.feature_as_of is not None:
            if isinstance(signal.feature_as_of, datetime):
                if _as_utc(signal.feature_as_of) > information_cutoff:
                    raise LookaheadError("feature as_of later than evaluation as_of")
            elif signal.feature_as_of > cutoff.date():
                raise LookaheadError("feature as_of later than evaluation as_of")
        if (
            signal.feature_available_at is not None
            and _as_utc(signal.feature_available_at) > information_cutoff
        ):
            raise LookaheadError("feature available_at later than evaluation as_of")
    for bar in (*_flatten_bars(bars), *tuple(spy_bars)):
        if bar.date > cutoff.date():
            raise LookaheadError("market bar dated later than evaluation as_of")
        if bar.available_at is not None and _as_utc(bar.available_at) > information_cutoff:
            raise LookaheadError("market bar available_at later than evaluation as_of")
    if require_scoring_provenance:
        validate_scoring_provenance(signal_rows, windows=windows)


def validate_scoring_provenance(
    signals: Iterable[BacktestSignal], *, windows: BacktestWindows | None = None
) -> None:
    """Require one exact ``scoring.v1`` methodology lineage for an evaluated run.

    A signal object remains usable as an audit fixture without this evidence,
    but ``BacktestEngine.run`` always calls this validator before it schedules
    an event. Candidate lineage is allowed for development/validation, while
    the reporting gate separately requires FROZEN before sealed OOS. All
    evaluated signals have to identify the same exact methodology. ``windows`` is retained for
    API compatibility, but historical event dates are not evidence of when an
    analyst first opened the OOS result.  That independent control is carried
    by ``ValidationEvidence.temporal_valid`` at the formal gate.
    """

    rows = tuple(signals)
    if not rows:
        return
    locked_engine = ScoreEngine()
    locked_identity = (
        locked_engine.score_version,
        locked_engine.score_config_hash,
        locked_engine.score_lineage,
    )
    locked_provenance = (
        *locked_identity,
        locked_engine.methodology_hash,
        locked_engine.methodology_status,
        locked_engine.score_frozen_at,
    )
    expected: tuple[str, str, str, str, str, datetime | None] | None = None
    for signal in rows:
        if (
            signal.score_version != "scoring.v1"
            or signal.score_config_hash is None
            or signal.score_lineage is None
            or signal.methodology_hash is None
            or signal.methodology_status is None
        ):
            raise ScoringProvenanceError(
                "evaluated signals require scoring.v1 score_config_hash, "
                "score_lineage, methodology_hash, and methodology_status evidence"
            )
        provenance = (
            signal.score_version,
            signal.score_config_hash,
            signal.score_lineage,
            signal.methodology_hash,
            signal.methodology_status,
            _as_utc(signal.frozen_at) if signal.frozen_at is not None else None,
        )
        if expected is None:
            expected = provenance
        elif provenance != expected:
            raise ScoringProvenanceError(
                "evaluated signals must share one scoring.v1 methodology provenance"
            )
    if expected != locked_provenance:
        if expected is not None and expected[:3] != locked_identity:
            raise ScoringProvenanceError(
                "evaluated signals must reference the locked config/scoring.v1.yaml "
                "version, sha256, and lineage"
            )
        raise ScoringProvenanceError("evaluated signals must reference the exact scoring.v1 lock")


class BacktestEngine:
    """Run a fixed-score event study without opening or tuning OOS data."""

    def __init__(
        self,
        *,
        horizons: Sequence[int] = HORIZONS,
        dedup_sessions: int = 20,
        windows: BacktestWindows | None = None,
        delisted_tickers: Mapping[str, str] | Iterable[str] = (),
    ) -> None:
        normal_horizons = tuple(int(value) for value in horizons)
        if not normal_horizons or any(value <= 0 for value in normal_horizons):
            raise BacktestError("horizons must be non-empty positive session counts")
        if len(set(normal_horizons)) != len(normal_horizons):
            raise BacktestError("horizons must be unique")
        if dedup_sessions < 0:
            raise BacktestError("dedup_sessions must be non-negative")
        self._horizons = tuple(sorted(normal_horizons))
        self._dedup_sessions = dedup_sessions
        self._configured_windows = windows
        if isinstance(delisted_tickers, Mapping):
            self._delisted = {
                str(ticker).upper(): str(reason) or "DELISTED"
                for ticker, reason in delisted_tickers.items()
            }
        else:
            self._delisted = {str(ticker).upper(): "DELISTED" for ticker in delisted_tickers}

    @property
    def horizons(self) -> tuple[int, ...]:
        return self._horizons

    @property
    def dedup_sessions(self) -> int:
        return self._dedup_sessions

    def run(
        self,
        signals: Iterable[BacktestSignal],
        *,
        bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
        spy_bars: Iterable[DailyBar],
        as_of: date | datetime | None = None,
    ) -> BacktestResult:
        """Evaluate supplied signals through a deterministic market calendar.

        ``spy_bars`` defines the market-session calendar.  A stock must have a
        bar on the exact calendar session for entry, each horizon exit, and
        MAE path; no nearest-date substitution is ever performed.
        """

        signal_rows = tuple(signals)
        stock_rows = _flatten_bars(bars)
        spy_rows = tuple(spy_bars)
        stock_by_symbol = _bar_index(stock_rows, label="stock")
        spy_by_symbol = _bar_index(spy_rows, label="SPY")
        if set(spy_by_symbol).difference({"SPY"}):
            raise BacktestError("spy_bars must contain only SPY daily bars")
        spy = spy_by_symbol.get("SPY", {})
        if not spy:
            raise BacktestError("at least one SPY daily bar is required")
        session_dates = tuple(sorted(spy))
        evaluation_as_of: date | datetime = (
            as_of if as_of is not None else us_equity_session_close(session_dates[-1])
        )
        cutoff = _as_cutoff(evaluation_as_of)
        windows = self._configured_windows or default_windows(cutoff)
        # This is deliberately strict even when the caller omitted ``as_of``:
        # the final SPY session is then the run's public information boundary.
        # For a complete outcome run, pass an as_of at or after its outcome bars.
        validate_evaluation_inputs(
            signals=signal_rows,
            bars=stock_rows,
            spy_bars=spy_rows,
            as_of=evaluation_as_of,
            require_scoring_provenance=True,
            windows=windows,
        )
        sessions = tuple(day for day in session_dates if day <= cutoff.date())
        if not sessions:
            raise BacktestError("no SPY sessions at or before as_of")
        evaluated, duplicate_ids = self._schedule_and_deduplicate(
            signal_rows, sessions=sessions, windows=windows, stock_by_symbol=stock_by_symbol
        )
        outcomes = tuple(
            self._outcome(
                signal,
                period,
                event_session,
                sessions=sessions,
                stock_by_symbol=stock_by_symbol,
                spy=spy,
            )
            for signal, period, event_session in evaluated
        )
        return self._result(outcomes, duplicate_ids=duplicate_ids, windows=windows)

    def _schedule_and_deduplicate(
        self,
        signals: Sequence[BacktestSignal],
        *,
        sessions: tuple[date, ...],
        windows: BacktestWindows,
        stock_by_symbol: Mapping[str, Mapping[date, DailyBar]],
    ) -> tuple[
        tuple[tuple[BacktestSignal, BacktestPeriod, date], ...],
        tuple[tuple[str, BacktestPeriod], ...],
    ]:
        scheduled: list[tuple[int, datetime, BacktestSignal, BacktestPeriod, date]] = []
        for signal in signals:
            available = _as_utc(signal.availability_at)
            event_index = self._event_index(available, sessions)
            if event_index is None:
                continue
            event_session = sessions[event_index]
            period = windows.period_for(event_session)
            if period is None:
                continue
            self._validate_signal_at_event(signal, event_session, stock_by_symbol)
            scheduled.append((event_index, available, signal, period, event_session))
        scheduled.sort(
            key=lambda row: (row[0], row[1], row[2].ticker, row[2].signal_type, row[2].signal_id)
        )
        retained: list[tuple[BacktestSignal, BacktestPeriod, date]] = []
        duplicates: list[tuple[str, BacktestPeriod]] = []
        last_by_key: dict[tuple[str, str], int] = {}
        for event_index, _available, signal, period, event_session in scheduled:
            key = (self._issuer_identity(signal), self._exposure_family(signal))
            previous = last_by_key.get(key)
            if previous is not None and event_index - previous <= self._dedup_sessions:
                duplicates.append((signal.signal_id, period))
                continue
            last_by_key[key] = event_index
            retained.append((signal, period, event_session))
        return tuple(retained), tuple(duplicates)

    @staticmethod
    def _issuer_identity(signal: BacktestSignal) -> str:
        """Use stable issuer identity where available, otherwise legacy ticker."""

        return f"CIK:{signal.issuer_cik}" if signal.issuer_cik else f"TICKER:{signal.ticker}"

    @staticmethod
    def _exposure_family(signal: BacktestSignal) -> str:
        """Normalize alert/signal spellings into one exposure family.

        Producers can supply ``exposure_family`` for domain-specific mappings.
        The fallback removes generic ``ALERT`` and ``SIGNAL`` suffix/tokens so
        that, for example, ``TURNING_ALERT`` and ``TURNING_SIGNAL`` cannot
        create overlapping exposure inside the deduplication window.
        """

        if signal.exposure_family:
            return signal.exposure_family
        tokens = [
            token
            for token in signal.signal_type.upper().replace("-", "_").split("_")
            if token not in {"ALERT", "SIGNAL"}
        ]
        return "_".join(tokens) or signal.signal_type.upper()

    @staticmethod
    def _event_index(available: datetime, sessions: tuple[date, ...]) -> int | None:
        candidate = bisect.bisect_left(sessions, available.date())
        if candidate == len(sessions):
            return None
        # A filing made after the market's daily close belongs to the following
        # market close.  This keeps a same-day 16:01 filing out of that close.
        if sessions[candidate] == available.date() and available > us_equity_session_close(
            sessions[candidate]
        ):
            candidate += 1
        return candidate if candidate < len(sessions) else None

    @staticmethod
    def _validate_signal_at_event(
        signal: BacktestSignal,
        event_session: date,
        stock_by_symbol: Mapping[str, Mapping[date, DailyBar]],
    ) -> None:
        event_close = us_equity_session_close(event_session)
        if signal.feature_as_of is not None:
            feature_later = (
                _as_utc(signal.feature_as_of) > event_close
                if isinstance(signal.feature_as_of, datetime)
                else signal.feature_as_of > event_session
            )
            if feature_later:
                raise LookaheadError("feature as_of later than signal evaluation as_of")
        if (
            signal.feature_available_at is not None
            and _as_utc(signal.feature_available_at) > event_close
        ):
            raise LookaheadError("feature available_at later than signal evaluation as_of")
        event_bar = stock_by_symbol.get(signal.ticker, {}).get(event_session)
        if event_bar is not None and event_bar.available_at is not None:
            if _as_utc(event_bar.available_at) > event_close:
                raise LookaheadError(
                    "event market bar available_at later than signal evaluation as_of"
                )

    def _outcome(
        self,
        signal: BacktestSignal,
        period: BacktestPeriod,
        event_session: date,
        *,
        sessions: tuple[date, ...],
        stock_by_symbol: Mapping[str, Mapping[date, DailyBar]],
        spy: Mapping[date, DailyBar],
    ) -> BacktestEvent:
        event_index = bisect.bisect_left(sessions, event_session)
        entry_index = event_index + 1
        if entry_index >= len(sessions):
            return BacktestEvent(
                signal=signal,
                period=period,
                event_session=event_session,
                entry_session=None,
                entry_open=None,
                forward_returns=self._empty_returns("MISSING_ENTRY_SESSION"),
                attrition_reasons=("MISSING_ENTRY_SESSION",),
            )
        entry_session = sessions[entry_index]
        stock = stock_by_symbol.get(signal.ticker, {})
        entry_bar = stock.get(entry_session)
        if entry_bar is None:
            reason = self._missing_reason(signal.ticker, "ENTRY")
            return BacktestEvent(
                signal=signal,
                period=period,
                event_session=event_session,
                entry_session=entry_session,
                entry_open=None,
                forward_returns=self._empty_returns(reason),
                attrition_reasons=(reason,),
            )
        entry_open = _bar_value(entry_bar.open)
        returns: dict[int, ForwardReturn] = {}
        reasons: list[str] = []
        spy_entry = spy.get(entry_session)
        for horizon in self._horizons:
            returns[horizon] = self._forward_return(
                ticker=signal.ticker,
                entry_open=entry_open,
                entry_index=entry_index,
                horizon=horizon,
                sessions=sessions,
                stock=stock,
                spy=spy,
                spy_entry=spy_entry,
            )
            outcome_reason = returns[horizon].attrition_reason
            if outcome_reason is not None:
                reasons.append(outcome_reason)
            reasons.extend(returns[horizon].quality_reasons)
        return BacktestEvent(
            signal=signal,
            period=period,
            event_session=event_session,
            entry_session=entry_session,
            entry_open=entry_open,
            forward_returns=returns,
            attrition_reasons=tuple(sorted(set(reasons))),
            adjustment_basis=entry_bar.adjustment_basis,
        )

    def _forward_return(
        self,
        *,
        ticker: str,
        entry_open: float,
        entry_index: int,
        horizon: int,
        sessions: tuple[date, ...],
        stock: Mapping[date, DailyBar],
        spy: Mapping[date, DailyBar],
        spy_entry: DailyBar | None,
    ) -> ForwardReturn:
        exit_index = entry_index + horizon
        if exit_index >= len(sessions):
            reason = self._missing_reason(ticker, f"RETURN_{horizon}")
            return ForwardReturn(horizon, None, None, None, None, None, reason)
        exit_session = sessions[exit_index]
        exit_bar = stock.get(exit_session)
        if exit_bar is None:
            reason = self._missing_reason(ticker, f"RETURN_{horizon}")
            return ForwardReturn(horizon, exit_session, None, None, None, None, reason)
        stock_return = _bar_value(exit_bar.close) / entry_open - 1.0
        path = [stock.get(session) for session in sessions[entry_index : exit_index + 1]]
        mae: float | None
        quality_reasons: tuple[str, ...] = ()
        if any(bar is None for bar in path):
            mae = None
            quality_reasons = (f"MISSING_INTERMEDIATE_BAR_{horizon}",)
        else:
            lows = [_bar_value(bar.low) for bar in path if bar is not None]
            mae = min(lows) / entry_open - 1.0
        exit_spy = spy.get(exit_session)
        if spy_entry is None:
            return ForwardReturn(
                horizon,
                exit_session,
                stock_return,
                None,
                None,
                mae,
                "MISSING_SPY_ENTRY",
                quality_reasons,
            )
        if exit_spy is None:
            return ForwardReturn(
                horizon,
                exit_session,
                stock_return,
                None,
                None,
                mae,
                f"MISSING_SPY_RETURN_{horizon}",
                quality_reasons,
            )
        spy_return = _bar_value(exit_spy.close) / _bar_value(spy_entry.open) - 1.0
        return ForwardReturn(
            horizon,
            exit_session,
            stock_return,
            spy_return,
            stock_return - spy_return,
            mae,
            quality_reasons=quality_reasons,
        )

    def _empty_returns(self, reason: str) -> dict[int, ForwardReturn]:
        return {
            horizon: ForwardReturn(horizon, None, None, None, None, None, reason)
            for horizon in self._horizons
        }

    def _missing_reason(self, ticker: str, kind: str) -> str:
        if ticker in self._delisted:
            return f"DELISTED_{kind}"
        return f"MISSING_{kind}"

    def _result(
        self,
        outcomes: tuple[BacktestEvent, ...],
        *,
        duplicate_ids: tuple[tuple[str, BacktestPeriod], ...],
        windows: BacktestWindows,
    ) -> BacktestResult:
        by_period: dict[BacktestPeriod, tuple[BacktestEvent, ...]] = {
            period: tuple(event for event in outcomes if event.period is period)
            for period in BacktestPeriod
        }
        groups = {period: self._groups(period, events) for period, events in by_period.items()}
        development = groups[BacktestPeriod.DEVELOPMENT]
        validation = groups[BacktestPeriod.VALIDATION]
        oos = groups[BacktestPeriod.OOS]
        non_oos = tuple(event for event in outcomes if event.period is not BacktestPeriod.OOS)
        visible_attrition = self._events_attrition(non_oos)
        oos_attrition = self._period_attrition(oos)
        visible_duplicates = tuple(
            signal_id for signal_id, period in duplicate_ids if period is not BacktestPeriod.OOS
        )
        oos_duplicates = tuple(
            signal_id for signal_id, period in duplicate_ids if period is BacktestPeriod.OOS
        )
        visible_caveats = self._caveats(visible_attrition, visible_duplicates, windows)
        oos_caveats = self._caveats(oos_attrition, oos_duplicates, windows)
        sealed_report = OOSReport(
            results=oos,
            attrition=oos_attrition,
            caveats=oos_caveats,
            duplicate_signal_ids=oos_duplicates,
        )
        return BacktestResult(
            development=development,
            validation=validation,
            attrition=visible_attrition,
            caveats=visible_caveats,
            duplicate_signal_ids=visible_duplicates,
            sealed_oos=SealedOOSResults(sealed_report),
        )

    @staticmethod
    def _groups(period: BacktestPeriod, events: tuple[BacktestEvent, ...]) -> PeriodResults:
        ordered = tuple(
            sorted(
                events,
                key=lambda event: (
                    event.event_session,
                    event.signal.ticker,
                    event.signal.signal_id,
                ),
            )
        )
        top: list[BacktestEvent] = []
        by_session: dict[date, list[BacktestEvent]] = defaultdict(list)
        for event in ordered:
            by_session[event.event_session].append(event)
        for event_session in sorted(by_session):
            # The score itself is frozen upstream.  This deterministic rank is
            # selection only; there is intentionally no weight/search API.
            candidates = sorted(
                by_session[event_session],
                key=lambda event: (
                    -event.signal.score,
                    event.signal.ticker,
                    event.signal.signal_id,
                ),
            )
            selected = max(1, (len(candidates) + 9) // 10)
            top.extend(candidates[:selected])
        return PeriodResults(
            period=period,
            top_decile=EventGroup("top_decile", period, tuple(top)),
            simple_benchmark=EventGroup("simple_benchmark", period, ordered),
        )

    @staticmethod
    def _period_attrition(results: PeriodResults) -> AttritionReport:
        return BacktestEngine._events_attrition(results.simple_benchmark.events)

    @staticmethod
    def _events_attrition(events: Iterable[BacktestEvent]) -> AttritionReport:
        event_rows = tuple(events)
        counts: Counter[str] = Counter()
        attrited = 0
        for event in event_rows:
            reasons = set(event.attrition_reasons)
            reasons.update(
                result.attrition_reason
                for result in event.forward_returns.values()
                if result.attrition_reason is not None
            )
            for result in event.forward_returns.values():
                reasons.update(result.quality_reasons)
            if reasons:
                attrited += 1
                counts.update(reasons)
        return AttritionReport(len(event_rows), attrited, dict(sorted(counts.items())))

    @staticmethod
    def _caveats(
        attrition: AttritionReport,
        duplicate_ids: tuple[str, ...],
        windows: BacktestWindows,
    ) -> tuple[BacktestCaveat, ...]:
        return (
            BacktestCaveat(
                "SURVIVORSHIP_UNIVERSE",
                "The supplied bar universe may omit securities that disappeared; delisted outcomes "
                "are retained only when supplied or identified through missing-return attrition.",
            ),
            BacktestCaveat(
                "TICKER_POINT_IN_TIME",
                "Tickers are used exactly as supplied on each signal; "
                "the backtest does not infer a "
                "present-day ticker for a historical issuer.",
            ),
            BacktestCaveat(
                "SECTOR_POINT_IN_TIME",
                "Sector labels are audit metadata only and must be supplied as valid-time values; "
                "no current sector classification is backfilled.",
            ),
            BacktestCaveat(
                "MISSING_RETURN_ATTRITION",
                f"{attrition.attrited_events} of {attrition.total_events} retained events "
                "have one or "
                "more missing/delisted outcomes; these outcomes are never imputed as zero.",
            ),
            BacktestCaveat(
                "DEDUPLICATION",
                f"{len(duplicate_ids)} signals were excluded within the configured "
                "issuer-identity/exposure-family deduplication window.",
            ),
            BacktestCaveat(
                "SEALED_OOS_WINDOW",
                f"OOS is sealed from {windows.oos_start.isoformat()} through "
                f"{windows.oos_end.isoformat()} "
                "and cannot be read by evaluators or tuners.",
            ),
        )


def run_backtest(
    signals: Iterable[BacktestSignal],
    *,
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
    spy_bars: Iterable[DailyBar],
    as_of: date | datetime | None = None,
) -> BacktestResult:
    """Convenience wrapper for the no-tuning default backtest engine."""

    return BacktestEngine().run(signals, bars=bars, spy_bars=spy_bars, as_of=as_of)


__all__ = [
    "BacktestEngine",
    "BacktestWindows",
    "default_windows",
    "last_complete_month_end",
    "run_backtest",
    "validate_evaluation_inputs",
    "validate_scoring_provenance",
]
