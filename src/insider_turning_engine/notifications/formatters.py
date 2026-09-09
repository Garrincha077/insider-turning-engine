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


def format_email_subject(candidate: AlertCandidate) -> str:
    """Render a compact subject without accepting provider header injection."""

    identity = candidate.ticker or candidate.issuer_cik
    subject = f"[{candidate.severity.value}] {candidate.alert_type.value}: {identity}"
    return subject.replace("\r", " ").replace("\n", " ")[:160]


def format_email_html(candidate: AlertCandidate) -> str:
    """Render deterministic email HTML with every candidate value escaped."""

    lines = _lines(candidate)
    parts = [
        "<div style=\"font-family:system-ui,sans-serif;color:#111827\">",
        f"<h2>{escape(lines[0])}</h2>",
    ]
    parts.extend(f"<p>{escape(line)}</p>" for line in lines[1:5])
    if candidate.reasons:
        parts.append("<h3>Reasons</h3><ul>")
        parts.extend(f"<li>{escape(reason)}</li>" for reason in candidate.reasons)
        parts.append("</ul>")
    parts.append(
        "<p style=\"color:#6b7280;font-size:12px\">Research signal only; "
        "not investment advice.</p></div>"
    )
    return "".join(parts)


def preview_plain(candidate: AlertCandidate) -> NotificationPreview:
    return NotificationPreview(candidate, format_plain(candidate))


def preview_telegram_html(candidate: AlertCandidate) -> NotificationPreview:
    return NotificationPreview(candidate, format_telegram_html(candidate), "text/html", "HTML")


def preview_email_html(candidate: AlertCandidate) -> NotificationPreview:
    return NotificationPreview(
        candidate,
        format_email_html(candidate),
        "text/html",
        subject=format_email_subject(candidate),
        alternative_text=format_plain(candidate),
    )


__all__ = [
    "format_plain",
    "format_email_html",
    "format_email_subject",
    "format_telegram_html",
    "preview_email_html",
    "preview_plain",
    "preview_telegram_html",
]
