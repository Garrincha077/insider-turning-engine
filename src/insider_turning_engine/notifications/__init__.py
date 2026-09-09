"""Alert rule evaluation, formatting, channels, and durable delivery."""

from .channels import EmailHTTPChannel, NotificationChannel, TelegramHTTPChannel
from .config import (
    DEFAULT_NOTIFICATION_POLICY,
    NotificationPolicy,
    NotificationPolicyError,
    QuietHours,
    load_notification_policy,
)
from .formatters import (
    format_email_html,
    format_email_subject,
    format_plain,
    format_telegram_html,
    preview_email_html,
    preview_plain,
    preview_telegram_html,
)
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
from .settings import build_settings_status

__all__ = [
    "AlertCandidate",
    "AlertType",
    "DeliveryStatus",
    "EmailHTTPChannel",
    "DEFAULT_NOTIFICATION_POLICY",
    "NotificationChannel",
    "NotificationPreview",
    "NotificationPolicy",
    "NotificationPolicyError",
    "QualityGateResult",
    "QuietHours",
    "SQLiteOutbox",
    "SendResult",
    "Severity",
    "TelegramHTTPChannel",
    "assess_quality_gates",
    "build_settings_status",
    "evaluate_alert_rules",
    "evaluate_alerts",
    "format_plain",
    "format_email_html",
    "format_email_subject",
    "format_telegram_html",
    "match_alert_rules",
    "load_notification_policy",
    "preview_email_html",
    "preview_plain",
    "preview_telegram_html",
]
