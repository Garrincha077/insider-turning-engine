"""Typed notification contracts.

The notification layer deliberately accepts the small, storage-neutral signal
mapping produced by the scoring layer.  It does not import scoring or mutate a
signal snapshot: an :class:`AlertCandidate` is an immutable audit record.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AlertType(StrEnum):
    MAJOR_INSIDER_BUY = "MAJOR_INSIDER_BUY"
    STEALTH_ACCUMULATION = "STEALTH_ACCUMULATION"
    TURNING = "TURNING"


class Severity(StrEnum):
    INFO = "INFO"
    WATCH = "WATCH"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DeliveryStatus(StrEnum):
    CLAIMED = "CLAIMED"
    SENT = "SENT"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"
    SUPPRESSED = "SUPPRESSED"
    DUPLICATE = "DUPLICATE"


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    """An immutable match of one rule at one signal snapshot."""

    issuer_cik: str
    alert_type: AlertType
    trigger_snapshot_id: str
    score: float
    severity: Severity = Severity.INFO
    important_flag: bool = False
    reasons: tuple[str, ...] = ()
    ticker: str | None = None
    state: str | None = None
    previous_state: str | None = None
    previous_severity: Severity | None = None
    previous_important_flag: bool | None = None
    absolute_score_delta: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    suppression_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _utc(self.created_at))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "suppression_reasons", tuple(self.suppression_reasons))
        if (
            not self.issuer_cik
            or not self.issuer_cik.isdigit()
            or len(self.issuer_cik) != 10
            or not self.trigger_snapshot_id
        ):
            raise ValueError("issuer_cik and trigger_snapshot_id are required")
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(float(self.score))
        ):
            raise ValueError("score must be finite and within [0, 100]")
        if not 0.0 <= self.score <= 100.0:
            raise ValueError("score must be finite and within [0, 100]")
        if not isinstance(self.important_flag, bool):
            raise ValueError("important_flag must be a boolean")
        if self.previous_important_flag is not None and not isinstance(
            self.previous_important_flag, bool
        ):
            raise ValueError("previous_important_flag must be a boolean or null")
        if self.absolute_score_delta is not None and (
            isinstance(self.absolute_score_delta, bool)
            or not isinstance(self.absolute_score_delta, (int, float))
            or not math.isfinite(float(self.absolute_score_delta))
            or float(self.absolute_score_delta) < 0
        ):
            raise ValueError("absolute_score_delta must be a finite non-negative number")
        if not isinstance(self.alert_type, AlertType):
            object.__setattr__(self, "alert_type", AlertType(self.alert_type))
        if not isinstance(self.severity, Severity):
            object.__setattr__(self, "severity", Severity(self.severity))
        if self.previous_severity is not None and not isinstance(self.previous_severity, Severity):
            object.__setattr__(self, "previous_severity", Severity(self.previous_severity))

    @property
    def idempotency_key(self) -> str:
        return f"{self.issuer_cik}:{self.alert_type.value}:{self.trigger_snapshot_id}"

    @property
    def alert_id(self) -> str:
        return self.idempotency_key

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AlertCandidate:
        """Build a candidate from a JSON-like record, including camelCase keys."""

        def get(name: str, default: Any = None) -> Any:
            if name in value:
                return value[name]
            camel = name.split("_")[0] + "".join(p.title() for p in name.split("_")[1:])
            return value.get(camel, default)

        reasons = get("reasons", ())
        if isinstance(reasons, str):
            reasons = (reasons,)
        suppression = get("suppression_reasons", ())
        if isinstance(suppression, str):
            suppression = (suppression,)
        important_flag = get("important_flag", False)
        previous_important_flag = get("previous_important_flag")
        if not isinstance(important_flag, bool):
            raise ValueError("important_flag must be a JSON boolean")
        if previous_important_flag is not None and not isinstance(previous_important_flag, bool):
            raise ValueError("previous_important_flag must be a JSON boolean or null")
        return cls(
            issuer_cik=str(get("issuer_cik")),
            alert_type=AlertType(get("alert_type")),
            trigger_snapshot_id=str(get("trigger_snapshot_id")),
            score=float(get("score", get("total_score", 0))),
            severity=Severity(get("severity", Severity.INFO)),
            important_flag=important_flag,
            reasons=tuple(str(item) for item in reasons),
            ticker=get("ticker"),
            state=get("state"),
            previous_state=get("previous_state"),
            previous_severity=(
                Severity(get("previous_severity")) if get("previous_severity") is not None else None
            ),
            previous_important_flag=previous_important_flag,
            absolute_score_delta=(
                float(get("absolute_score_delta"))
                if get("absolute_score_delta") is not None
                else None
            ),
            created_at=get("created_at"),
            suppression_reasons=tuple(str(item) for item in suppression),
        )


@dataclass(frozen=True, slots=True)
class NotificationPreview:
    candidate: AlertCandidate
    text: str
    content_type: str = "text/plain"
    parse_mode: str | None = None
    subject: str | None = None
    alternative_text: str | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    status: DeliveryStatus
    provider_id: str | None = None
    error: str | None = None

    @classmethod
    def sent(cls, provider_id: str | None = None) -> SendResult:
        return cls(DeliveryStatus.SENT, provider_id=provider_id)

    @classmethod
    def failed(cls, error: str) -> SendResult:
        return cls(DeliveryStatus.FAILED, error=error)

    @classmethod
    def uncertain(cls, error: str) -> SendResult:
        return cls(DeliveryStatus.UNCERTAIN, error=error)


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    allowed: bool
    reasons: tuple[str, ...] = ()
    checks: Mapping[str, bool] = field(default_factory=dict)


__all__ = [
    "AlertCandidate",
    "AlertType",
    "DeliveryStatus",
    "NotificationPreview",
    "QualityGateResult",
    "SendResult",
    "Severity",
]
