"""Stable data contracts for the point-in-time event backtest.

The package intentionally accepts scored *signals*, rather than score weights
or a scoring callback.  A backtest selects the supplied frozen score outputs;
it never tunes the production scoring model.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

HORIZONS: tuple[int, ...] = (21, 63, 126, 252)


class BacktestError(ValueError):
    """Base error for invalid deterministic backtest inputs."""


class LookaheadError(BacktestError):
    """Raised when an input would not have been known at evaluation time."""


class SealedOOSAccessError(PermissionError):
    """Raised when a tuner or evaluator tries to inspect sealed OOS results."""


class ScoringProvenanceError(BacktestError):
    """Raised when an evaluated score lacks immutable scoring evidence."""


class BacktestPeriod(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    OOS = "oos"


class SealedAccessPurpose(StrEnum):
    """The only supported readers for an OOS result.

    ``FINAL_REPORT`` deliberately represents a post-selection reporting step.
    The evaluator and tuner roles are explicitly rejected by the sealed API.
    """

    EVALUATOR = "evaluator"
    TUNER = "tuner"
    FINAL_REPORT = "final_report"


@dataclass(frozen=True, slots=True)
class BacktestSignal:
    """One already-scored signal available from a public filing.

    ``transaction_date`` is retained only for auditability.  It is never used
    to schedule a backtest event.  Scheduling always uses ``knowledge_at``
    where available, otherwise the SEC ``accepted_at`` timestamp.
    """

    signal_id: str
    ticker: str
    signal_type: str
    score: float
    accepted_at: datetime | None = None
    knowledge_at: datetime | None = None
    transaction_date: date | None = None
    feature_as_of: date | datetime | None = None
    feature_available_at: datetime | None = None
    sector: str | None = None
    issuer_cik: str | None = None
    exposure_family: str | None = None
    score_version: str = "scoring.v1"
    score_config_hash: str | None = None
    score_lineage: str | None = None
    frozen_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise BacktestError("signal_id must be non-empty")
        ticker = self.ticker.strip().upper()
        if not ticker:
            raise BacktestError("ticker must be non-empty")
        if not self.signal_type:
            raise BacktestError("signal_type must be non-empty")
        if not math.isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise BacktestError("score must be finite and within [0, 100]")
        if self.score_version != "scoring.v1":
            raise BacktestError("score_version must be scoring.v1")
        if self.accepted_at is None and self.knowledge_at is None:
            raise BacktestError("a signal requires accepted_at or knowledge_at")
        for name in (
            "accepted_at",
            "knowledge_at",
            "feature_available_at",
            "frozen_at",
        ):
            stamp = getattr(self, name)
            if stamp is not None and stamp.tzinfo is None:
                raise BacktestError(f"{name} must be timezone-aware")
        if isinstance(self.feature_as_of, datetime) and self.feature_as_of.tzinfo is None:
            raise BacktestError("feature_as_of datetime must be timezone-aware")
        if (
            self.accepted_at is not None
            and self.knowledge_at is not None
            and self.knowledge_at < self.accepted_at
        ):
            raise BacktestError("knowledge_at cannot precede accepted_at")
        cik = self.issuer_cik.strip() if self.issuer_cik is not None else None
        if cik:
            if not cik.isdigit() or len(cik) > 10:
                raise BacktestError("issuer_cik must contain at most ten digits")
            cik = cik.zfill(10)
        family = self.exposure_family.strip().upper() if self.exposure_family else None
        if self.exposure_family is not None and not family:
            raise BacktestError("exposure_family must be non-empty when supplied")
        for name in ("score_config_hash", "score_lineage"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise BacktestError(f"{name} must be non-empty when supplied")
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "issuer_cik", cik)
        object.__setattr__(self, "exposure_family", family)

    @property
    def availability_at(self) -> datetime:
        """Return the public knowledge timestamp used for event scheduling."""

        return self.knowledge_at or self.accepted_at  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ForwardReturn:
    """Outcome measured from next-open entry to an exact session horizon."""

    horizon_sessions: int
    exit_session: date | None
    stock_return: float | None
    spy_return: float | None
    spy_excess_return: float | None
    max_adverse_excursion: float | None
    attrition_reason: str | None = None
    quality_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestEvent:
    """One eligible (or explicitly attrited) event outcome."""

    signal: BacktestSignal
    period: BacktestPeriod
    event_session: date
    entry_session: date | None
    entry_open: float | None
    forward_returns: Mapping[int, ForwardReturn]
    attrition_reasons: tuple[str, ...] = ()
    adjustment_basis: str | None = None

    @property
    def is_attrited(self) -> bool:
        return bool(self.attrition_reasons) or any(
            result.attrition_reason is not None or result.quality_reasons
            for result in self.forward_returns.values()
        )


@dataclass(frozen=True, slots=True)
class EventGroup:
    """A deterministic selection of comparable event outcomes."""

    name: str
    period: BacktestPeriod
    events: tuple[BacktestEvent, ...]


@dataclass(frozen=True, slots=True)
class PeriodResults:
    """Backtest groups for one non-sealed historical split."""

    period: BacktestPeriod
    top_decile: EventGroup
    simple_benchmark: EventGroup


@dataclass(frozen=True, slots=True)
class AttritionReport:
    """Reason-level attrition accounting; missing outcomes are never zeroed."""

    total_events: int
    attrited_events: int
    reason_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class BacktestCaveat:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class OOSReport:
    """The material revealed only after an explicit final-report request."""

    results: PeriodResults
    attrition: AttritionReport
    caveats: tuple[BacktestCaveat, ...]
    duplicate_signal_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class SealedOOSResults:
    """Keep OOS results out of normal evaluation and tuning code paths."""

    _report: OOSReport
    access_log: list[SealedAccessPurpose] = field(default_factory=list, init=False)

    def read(self, purpose: SealedAccessPurpose | str) -> OOSReport:
        """Reveal OOS only for the final, non-tuning reporting step."""

        try:
            requested = SealedAccessPurpose(purpose)
        except ValueError as exc:
            raise SealedOOSAccessError("unknown sealed OOS access purpose") from exc
        if requested in {SealedAccessPurpose.EVALUATOR, SealedAccessPurpose.TUNER}:
            raise SealedOOSAccessError(
                f"sealed OOS results are unavailable to a {requested.value}; "
                "use development and validation only"
            )
        self.access_log.append(requested)
        return self._report

    def for_evaluator(self) -> OOSReport:
        return self.read(SealedAccessPurpose.EVALUATOR)

    def for_tuner(self) -> OOSReport:
        return self.read(SealedAccessPurpose.TUNER)

    def final_report(self) -> OOSReport:
        return self.read(SealedAccessPurpose.FINAL_REPORT)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Result with development/validation visible and OOS deliberately sealed.

    ``attrition``, ``caveats`` and ``duplicate_signal_ids`` intentionally cover
    only non-OOS events.  OOS equivalents are released by ``final_report``.
    """

    development: PeriodResults
    validation: PeriodResults
    attrition: AttritionReport
    caveats: tuple[BacktestCaveat, ...]
    duplicate_signal_ids: tuple[str, ...]
    sealed_oos: SealedOOSResults


__all__ = [
    "AttritionReport",
    "BacktestCaveat",
    "BacktestError",
    "BacktestEvent",
    "BacktestPeriod",
    "BacktestResult",
    "BacktestSignal",
    "EventGroup",
    "ForwardReturn",
    "HORIZONS",
    "LookaheadError",
    "OOSReport",
    "PeriodResults",
    "SealedAccessPurpose",
    "SealedOOSAccessError",
    "SealedOOSResults",
    "ScoringProvenanceError",
]
