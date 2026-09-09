"""Build the public, secret-free notification settings projection."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .config import NotificationPolicy


def _instant(value: datetime) -> str:
    point = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return point.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _mask_chat_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4 or not value.lstrip("-").isdigit():
        return "••••"
    suffix = value[-4:]
    return f"••••{suffix}"


def _mask_email(value: str | None) -> str | None:
    if not value or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", value
    ):
        return None
    local, domain = value.rsplit("@", 1)
    if not local or not domain:
        return None
    return f"{local[0]}•••@{domain}"


def _latest(
    rows: Sequence[Mapping[str, Any]], *, channel: str, status: str | None = None
) -> str | None:
    candidates = [
        str(row["recorded_at"])
        for row in rows
        if row.get("channel") == channel
        and (status is None or row.get("status") == status)
        and row.get("recorded_at") is not None
    ]
    return max(candidates) if candidates else None


def build_settings_status(
    policy: NotificationPolicy,
    *,
    environment: str,
    alerts_allowed: bool,
    blocking_reasons: Sequence[str],
    secrets: Mapping[str, str],
    delivery_history: Sequence[Mapping[str, Any]] = (),
    test_history: Sequence[Mapping[str, Any]] = (),
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a schema-ready status document containing no credential values."""

    if environment not in {"local", "staging", "production"}:
        raise ValueError("environment must be local, staging, or production")
    telegram_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = secrets.get("TELEGRAM_CHAT_ID", "")
    email_key = secrets.get("EMAIL_API_KEY", "")
    email_from = secrets.get("ALERT_EMAIL_FROM", "")
    email_to = secrets.get("ALERT_EMAIL_TO", "")
    quiet_hours = (
        {
            "start": policy.quiet_hours.start.strftime("%H:%M"),
            "end": policy.quiet_hours.end.strftime("%H:%M"),
        }
        if policy.quiet_hours is not None
        else None
    )

    def channel_status(
        name: str, *, enabled: bool, configured: bool, masked: str | None
    ) -> dict[str, Any]:
        failures = sum(
            1
            for row in delivery_history
            if row.get("channel") == name and row.get("status") in {"FAILED", "UNCERTAIN"}
        )
        tests = sorted(
            (row for row in test_history if row.get("channel") == name),
            key=lambda row: str(row.get("recorded_at", "")),
        )
        return {
            "enabled": enabled,
            "configured": configured,
            "recipientMasked": masked,
            "lastTestAt": _latest(test_history, channel=name),
            "lastTestStatus": tests[-1]["status"] if tests else None,
            "testFailureCount": sum(row["status"] in {"FAILED", "UNCERTAIN"} for row in tests),
            "lastSuccessAt": _latest(delivery_history, channel=name, status="SENT"),
            "failureCount": failures,
        }

    reasons = set(blocking_reasons)
    if not alerts_allowed:
        reasons.add("QUALITY_GATE_NOT_PASS")
    if not policy.delivery_enabled:
        reasons.add("DELIVERY_DISABLED_BY_POLICY")
    if environment != "production":
        reasons.add("NON_PRODUCTION_ENVIRONMENT")
    configured = {
        "telegram": bool(telegram_token and telegram_chat),
        "email": bool(email_key and email_from and email_to),
    }
    if not policy.enabled_channels:
        reasons.add("NO_ENABLED_CHANNELS")
    for name in policy.enabled_channels:
        if not configured[name]:
            reasons.add(f"{name.upper()}_SECRETS_MISSING")
    return {
        "schemaVersion": "1.0.0",
        "generatedAt": _instant(generated_at or datetime.now(UTC)),
        "environment": environment,
        "alertsAllowed": not reasons,
        "blockingReasons": sorted(reasons),
        "deliveryHistory": sorted(
            [
                {"kind": kind, "channel": row["channel"], "status": row["status"],
                 "at": row["recorded_at"]}
                for kind, history in (("TEST", test_history), ("SIGNAL", delivery_history))
                for row in history
                if row.get("channel") in {"telegram", "email"}
                and row.get("status") in {"SENT", "FAILED", "UNCERTAIN", "SUPPRESSED", "CLAIMED"}
            ], key=lambda row: str(row["at"]), reverse=True,
        )[:100],
        "policy": {
            "deliveryEnabled": policy.delivery_enabled,
            "minimumSeverity": policy.minimum_severity.value,
            "alertTypes": [value.value for value in policy.alert_types],
            "cooldownDays": policy.cooldown_days,
            "timezone": policy.timezone,
            "quietHours": quiet_hours,
        },
        "channels": {
            "telegram": channel_status(
                "telegram",
                enabled=policy.telegram_enabled,
                configured=bool(telegram_token and telegram_chat),
                masked=_mask_chat_id(telegram_chat),
            ),
            "email": channel_status(
                "email",
                enabled=policy.email_enabled,
                configured=bool(email_key and email_from and email_to),
                masked=_mask_email(email_to),
            ),
        },
    }


__all__ = ["build_settings_status"]
