"""Channel contracts and the transport-injected Telegram adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from .formatters import preview_telegram_html
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
            if 200 <= status < 300 and (not isinstance(body, Mapping) or body.get("ok", True)):
                provider_id = (
                    str(body.get("result", {}).get("message_id"))
                    if isinstance(body, Mapping)
                    and isinstance(body.get("result"), Mapping)
                    and body["result"].get("message_id") is not None
                    else None
                )
                return SendResult.sent(provider_id)
            return SendResult.failed(f"telegram HTTP status {status}")
        except Exception as exc:  # transport outcome is ambiguous: never retry automatically
            return SendResult.uncertain(type(exc).__name__)

    def record_result(self, candidate: AlertCandidate, result: SendResult) -> None:
        self.results.append((candidate.idempotency_key, result))


__all__ = ["NotificationChannel", "TelegramHTTPChannel", "Transport"]
