"""Alert rule evaluation, formatting, channels, and durable delivery."""

from .channels import NotificationChannel, TelegramHTTPChannel
from .formatters import format_plain, format_telegram_html, preview_plain, preview_telegram_html
from .models import (
    AlertCandidate,
    AlertType,
    DeliveryStatus,
    NotificationPreview,
    QualityGateResult,
    SendResult,
    Severity,
)
from .outbox import SQLiteOutbox
from .rules import assess_quality_gates, evaluate_alert_rules, evaluate_alerts, match_alert_rules

__all__ = [
    "AlertCandidate",
    "AlertType",
    "DeliveryStatus",
    "NotificationChannel",
    "NotificationPreview",
    "QualityGateResult",
    "SQLiteOutbox",
    "SendResult",
    "Severity",
    "TelegramHTTPChannel",
    "assess_quality_gates",
    "evaluate_alert_rules",
    "evaluate_alerts",
    "format_plain",
    "format_telegram_html",
    "match_alert_rules",
    "preview_plain",
    "preview_telegram_html",
]
