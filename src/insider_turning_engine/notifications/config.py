"""Strict, versioned notification policy configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml  # type: ignore[import-untyped]

from .models import AlertCandidate, AlertType, Severity

DEFAULT_NOTIFICATION_POLICY = Path("config/notifications.v1.yaml")
_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.WATCH: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


class NotificationPolicyError(ValueError):
    """Raised when a notification policy is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class QuietHours:
    start: time
    end: time

    def contains(self, value: time) -> bool:
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= value < self.end
        return value >= self.start or value < self.end


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    schema_version: str
    delivery_enabled: bool
    telegram_enabled: bool
    email_enabled: bool
    minimum_severity: Severity
    alert_types: tuple[AlertType, ...]
    cooldown_days: int
    timezone: str
    quiet_hours: QuietHours | None

    @property
    def enabled_channels(self) -> tuple[str, ...]:
        channels: list[str] = []
        if self.telegram_enabled:
            channels.append("telegram")
        if self.email_enabled:
            channels.append("email")
        return tuple(channels)

    def suppression_reasons(
        self, candidate: AlertCandidate, *, at: datetime | None = None
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.delivery_enabled:
            reasons.append("DELIVERY_DISABLED_BY_POLICY")
        if candidate.alert_type not in self.alert_types:
            reasons.append("ALERT_TYPE_DISABLED_BY_POLICY")
        if _SEVERITY_ORDER[candidate.severity] < _SEVERITY_ORDER[self.minimum_severity]:
            reasons.append("BELOW_MINIMUM_SEVERITY")
        if self.quiet_hours is not None and at is not None:
            local = at.astimezone(ZoneInfo(self.timezone)).timetz().replace(tzinfo=None)
            if self.quiet_hours.contains(local):
                reasons.append("QUIET_HOURS")
        return tuple(reasons)


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise NotificationPolicyError(f"{field} must be a boolean")
    return value


def _parse_clock(value: Any, *, field: str) -> time:
    if not isinstance(value, str):
        raise NotificationPolicyError(f"{field} must be HH:MM")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise NotificationPolicyError(f"{field} must be HH:MM") from exc
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        raise NotificationPolicyError(f"{field} must be a local HH:MM value")
    return parsed


def load_notification_policy(
    path: str | Path = DEFAULT_NOTIFICATION_POLICY,
) -> NotificationPolicy:
    """Load a fail-closed notification policy with no permissive coercions."""

    target = Path(path)
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NotificationPolicyError(f"notification policy is unreadable: {target}") from exc
    if not isinstance(raw, dict):
        raise NotificationPolicyError("notification policy must be an object")
    expected = {
        "schemaVersion",
        "deliveryEnabled",
        "channels",
        "minimumSeverity",
        "alertTypes",
        "cooldownDays",
        "timezone",
        "quietHours",
    }
    if set(raw) != expected:
        raise NotificationPolicyError("notification policy fields do not match v1")
    if raw["schemaVersion"] != "1.0.0":
        raise NotificationPolicyError("unsupported notification policy schemaVersion")
    channels = raw["channels"]
    if not isinstance(channels, dict) or set(channels) != {"telegram", "email"}:
        raise NotificationPolicyError("channels must define only telegram and email")
    try:
        minimum_severity = Severity(raw["minimumSeverity"])
    except (TypeError, ValueError) as exc:
        raise NotificationPolicyError("minimumSeverity is invalid") from exc
    alert_types_raw = raw["alertTypes"]
    if not isinstance(alert_types_raw, list) or not alert_types_raw:
        raise NotificationPolicyError("alertTypes must be a non-empty list")
    try:
        alert_types = tuple(AlertType(value) for value in alert_types_raw)
    except (TypeError, ValueError) as exc:
        raise NotificationPolicyError("alertTypes contains an invalid value") from exc
    if len(set(alert_types)) != len(alert_types):
        raise NotificationPolicyError("alertTypes must be unique")
    cooldown_days = raw["cooldownDays"]
    if isinstance(cooldown_days, bool) or not isinstance(cooldown_days, int):
        raise NotificationPolicyError("cooldownDays must be an integer")
    if not 1 <= cooldown_days <= 90:
        raise NotificationPolicyError("cooldownDays must be between 1 and 90")
    timezone = raw["timezone"]
    if not isinstance(timezone, str) or not timezone:
        raise NotificationPolicyError("timezone must be a non-empty IANA timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise NotificationPolicyError("timezone is not available") from exc
    quiet_raw = raw["quietHours"]
    quiet_hours: QuietHours | None = None
    if quiet_raw is not None:
        if not isinstance(quiet_raw, dict) or set(quiet_raw) != {"start", "end"}:
            raise NotificationPolicyError("quietHours must contain start and end")
        quiet_hours = QuietHours(
            _parse_clock(quiet_raw["start"], field="quietHours.start"),
            _parse_clock(quiet_raw["end"], field="quietHours.end"),
        )
    return NotificationPolicy(
        schema_version="1.0.0",
        delivery_enabled=_strict_bool(raw["deliveryEnabled"], field="deliveryEnabled"),
        telegram_enabled=_strict_bool(channels["telegram"], field="channels.telegram"),
        email_enabled=_strict_bool(channels["email"], field="channels.email"),
        minimum_severity=minimum_severity,
        alert_types=alert_types,
        cooldown_days=cooldown_days,
        timezone=timezone,
        quiet_hours=quiet_hours,
    )


__all__ = [
    "DEFAULT_NOTIFICATION_POLICY",
    "NotificationPolicy",
    "NotificationPolicyError",
    "QuietHours",
    "load_notification_policy",
]
