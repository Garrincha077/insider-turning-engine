"""Deterministic, injection-safe notification rendering."""

from __future__ import annotations

from html import escape

from .models import AlertCandidate, NotificationPreview


def _lines(candidate: AlertCandidate) -> list[str]:
    lines = [
        candidate.alert_type.value,
        f"Issuer: {candidate.ticker + ' ' if candidate.ticker else ''}{candidate.issuer_cik}",
        f"Score: {candidate.score:g}",
        f"Severity: {candidate.severity.value}",
    ]
    if candidate.state:
        lines.append(f"State: {candidate.state}")
    lines.append(f"Important: {'yes' if candidate.important_flag else 'no'}")
    if candidate.reasons:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in candidate.reasons)
    return lines


def format_plain(candidate: AlertCandidate) -> str:
    return "\n".join(_lines(candidate))


def format_telegram_html(candidate: AlertCandidate) -> str:
    """Render stable Telegram HTML with all user-derived values escaped."""

    title, issuer, score, severity = _lines(candidate)[:4]
    lines = [
        f"<b>{escape(title)}</b>",
        escape(issuer),
        escape(score),
        escape(severity),
    ]
    if candidate.state:
        lines.append(escape(f"State: {candidate.state}"))
    lines.append(escape(f"Important: {'yes' if candidate.important_flag else 'no'}"))
    if candidate.reasons:
        lines.append("<b>Reasons</b>")
        lines.extend(f"• {escape(reason)}" for reason in candidate.reasons)
    return "\n".join(lines)


def preview_plain(candidate: AlertCandidate) -> NotificationPreview:
    return NotificationPreview(candidate, format_plain(candidate))


def preview_telegram_html(candidate: AlertCandidate) -> NotificationPreview:
    return NotificationPreview(candidate, format_telegram_html(candidate), "text/html", "HTML")


__all__ = [
    "format_plain",
    "format_telegram_html",
    "preview_plain",
    "preview_telegram_html",
]
