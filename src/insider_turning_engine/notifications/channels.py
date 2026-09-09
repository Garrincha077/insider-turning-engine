"""Channel contracts and the transport-injected Telegram adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from .formatters import preview_email_html, preview_telegram_html
from .models import AlertCandidate, NotificationPreview, SendResult


@runtime_checkable
class NotificationChannel(Protocol):
    """A channel's side effects are explicit and independently testable."""

    name: str

    def preview(self, candidate: AlertCandidate) -> NotificationPreview: ...

    def claim(self, candidate: AlertCandidate, idempotency_key: str) -> bool: ...

    def send(self, preview: NotificationPreview) -> SendResult: ...

    def record_result(self, candidate: AlertCandidate, result: SendResult) -> None: ...


Transport = Callable[[str, Mapping[str, Any]], Any]
EmailTransport = Callable[[str, Mapping[str, Any], Mapping[str, str]], Any]


class TelegramHTTPChannel:
    """Telegram Bot API adapter; ``transport`` is injected, never global."""

    name = "telegram"

    def __init__(self, token: str, chat_id: str | int, transport: Transport) -> None:
        if not token:
            raise ValueError("Telegram token is required")
        self._endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = str(chat_id)
        self._transport = transport
        self.results: list[tuple[str, SendResult]] = []

    def preview(self, candidate: AlertCandidate) -> NotificationPreview:
        return preview_telegram_html(candidate)

    def claim(self, candidate: AlertCandidate, idempotency_key: str) -> bool:
        # The durable outbox owns the atomic claim.  This hook lets channels
        # implement an additional provider-side lease when one is available.
        return True

    def send(self, preview: NotificationPreview) -> SendResult:
        payload = {
            "chat_id": self._chat_id,
            "text": preview.text,
            "parse_mode": preview.parse_mode or "HTML",
        }
        try:
            response = self._transport(self._endpoint, payload)
            if isinstance(response, Mapping):
                status = int(response.get("status_code", response.get("status", 200)))
                body = response.get("json", response)
            else:
                status = int(getattr(response, "status_code", 200))
                body = getattr(response, "json", None)
                body = body() if callable(body) else body
            if (
                200 <= status < 300
                and isinstance(body, Mapping)
                and body.get("ok") is True
                and isinstance(body.get("result"), Mapping)
                and body["result"].get("message_id") is not None
            ):
                provider_id = (
                    str(body.get("result", {}).get("message_id"))
                    if isinstance(body, Mapping)
                    and isinstance(body.get("result"), Mapping)
                    and body["result"].get("message_id") is not None
                    else None
                )
                return SendResult.sent(provider_id)
            if 200 <= status < 300:
                return SendResult.uncertain("TELEGRAM_RECEIPT_MISSING")
            return SendResult.failed(f"telegram HTTP status {status}")
        except Exception as exc:  # transport outcome is ambiguous: never retry automatically
            return SendResult.uncertain(type(exc).__name__)

    def record_result(self, candidate: AlertCandidate, result: SendResult) -> None:
        self.results.append((candidate.idempotency_key, result))


class EmailHTTPChannel:
    """Resend HTTP adapter with explicit credentials and injected transport."""

    name = "email"
    _endpoint = "https://api.resend.com/emails"

    def __init__(
        self,
        api_key: str,
        sender: str,
        recipient: str,
        transport: EmailTransport,
    ) -> None:
        if not api_key or not sender or not recipient:
            raise ValueError("email API key, sender, and recipient are required")
        self._api_key = api_key
        self._sender = sender
        self._recipient = recipient
        self._transport = transport
        self.results: list[tuple[str, SendResult]] = []

    def preview(self, candidate: AlertCandidate) -> NotificationPreview:
        return preview_email_html(candidate)

    def claim(self, candidate: AlertCandidate, idempotency_key: str) -> bool:
        return True

    def send(self, preview: NotificationPreview) -> SendResult:
        payload = {
            "from": self._sender,
            "to": [self._recipient],
            "subject": preview.subject or "Insider Turning Engine alert",
            "html": preview.text,
            "text": preview.alternative_text or "",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": preview.candidate.idempotency_key[:256],
            "User-Agent": "InsiderTurningEngine/0.1",
        }
        try:
            response = self._transport(self._endpoint, payload, headers)
            if isinstance(response, Mapping):
                status = int(response.get("status_code", response.get("status", 200)))
                body = response.get("json", response)
            else:
                status = int(getattr(response, "status_code", 200))
                body = getattr(response, "json", None)
                body = body() if callable(body) else body
            if (
                200 <= status < 300 and isinstance(body, Mapping)
                and isinstance(body.get("id"), str) and body["id"]
            ):
                provider_id = (
                    str(body.get("id"))
                    if isinstance(body, Mapping) and body.get("id") is not None
                    else None
                )
                return SendResult.sent(provider_id)
            if 200 <= status < 300:
                return SendResult.uncertain("EMAIL_RECEIPT_MISSING")
            return SendResult.failed(f"email HTTP status {status}")
        except Exception as exc:
            return SendResult.uncertain(type(exc).__name__)

    def record_result(self, candidate: AlertCandidate, result: SendResult) -> None:
        self.results.append((candidate.idempotency_key, result))


__all__ = [
    "EmailHTTPChannel",
    "EmailTransport",
    "NotificationChannel",
    "TelegramHTTPChannel",
    "Transport",
]
