import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from insider_turning_engine.notifications import (
    AlertCandidate,
    AlertType,
    DeliveryStatus,
    EmailHTTPChannel,
    NotificationPreview,
    SendResult,
    SQLiteOutbox,
    TelegramHTTPChannel,
    assess_quality_gates,
    build_settings_status,
    evaluate_alert_rules,
    format_email_html,
    format_telegram_html,
    load_notification_policy,
)


def test_alert_boundaries_and_turning_transition() -> None:
    base = {
        "issuer_cik": "0000000001",
        "snapshot_id": "snap_1",
        "conviction_score": 80,
        "transaction_value_usd": 250_000,
        "total_score": 75,
        "company_insider_score": 65,
        "divergence_score": 65,
        "transition_to": "EARLY_TURN",
    }
    found = evaluate_alert_rules(base)
    assert {candidate.alert_type for candidate in found} == {
        AlertType.MAJOR_INSIDER_BUY,
        AlertType.TURNING,
    }
    assert all(
        candidate.alert_type != AlertType.MAJOR_INSIDER_BUY
        for candidate in evaluate_alert_rules(
            {**base, "transaction_value_usd": 249_999, "conviction_score": 79}
        )
    )


def test_stealth_requires_strict_positive_slopes() -> None:
    snapshot = {
        "issuer_cik": "0000000001",
        "snapshot_id": "snap_2",
        "company_insider_score": 70,
        "divergence_score": 75,
        "turn_score": 45,
        "no_new_52_week_low": True,
        "ordinary_rs_3m_slope": 0.01,
        "mansfield_market_slope": 0.01,
    }
    assert evaluate_alert_rules(snapshot)[0].alert_type == AlertType.STEALTH_ACCUMULATION
    assert not evaluate_alert_rules({**snapshot, "mansfield_market_slope": 0})

    canonical = {
        **snapshot,
        "no_new_52_week_low": False,
        "no_new_52_week_low_20_sessions": True,
        "ordinary_rs_3m_slope_4w": 0.1,
        "mansfield_market_slope_4w": 0.1,
    }
    assert evaluate_alert_rules(canonical)[0].alert_type == AlertType.STEALTH_ACCUMULATION


def test_quality_suppression_is_global_and_html_escapes() -> None:
    candidate = evaluate_alert_rules(
        {
            "issuer_cik": "0000000001",
            "snapshot_id": "snap_3",
            "transaction_value_usd": 1_000_000,
            "ticker": "<X>",
            "quality": {"market_data_coverage_rate": 0.89},
        }
    )[0]
    assert "INSUFFICIENT_MARKET_DATA_COVERAGE_RATE" in candidate.suppression_reasons
    assert "&lt;X&gt;" in format_telegram_html(candidate)


def test_email_channel_is_deterministic_escaped_and_idempotent() -> None:
    captured: dict[str, object] = {}

    def transport(url, payload, headers):
        captured.update({"url": url, "payload": payload, "headers": headers})
        return {"status_code": 200, "json": {"id": "email-1"}}

    candidate = AlertCandidate(
        "0000000001",
        AlertType.TURNING,
        "snap_email",
        80,
        ticker="<X>",
        reasons=("a < b",),
    )
    channel = EmailHTTPChannel("secret", "from@example.com", "to@example.com", transport)
    preview = channel.preview(candidate)
    assert "&lt;X&gt;" in format_email_html(candidate)
    assert "a &lt; b" in preview.text
    result = channel.send(preview)
    assert result == SendResult.sent("email-1")
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Idempotency-Key"] == candidate.idempotency_key


def test_public_settings_status_never_contains_secrets_or_full_recipient() -> None:
    policy = load_notification_policy()
    status = build_settings_status(
        policy,
        environment="production",
        alerts_allowed=False,
        blocking_reasons=("BACKTEST_NOT_RUN",),
        secrets={
            "TELEGRAM_BOT_TOKEN": "bot-secret",
            "TELEGRAM_CHAT_ID": "123456789",
            "EMAIL_API_KEY": "email-secret",
            "ALERT_EMAIL_FROM": "alerts@example.com",
            "ALERT_EMAIL_TO": "luis@example.com",
        },
    )
    encoded = json.dumps(status)
    assert "bot-secret" not in encoded
    assert "email-secret" not in encoded
    assert "123456789" not in encoded
    assert "luis@example.com" not in encoded
    assert status["channels"]["telegram"]["recipientMasked"] == "••••6789"
    assert status["channels"]["email"]["recipientMasked"] == "l•••@example.com"


@pytest.mark.parametrize("body", [{}, {"id": None}, {"ok": True, "result": {}}])
def test_success_without_provider_receipt_is_uncertain(body) -> None:
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_receipt", 80)
    channels = [
        TelegramHTTPChannel("secret", "12345", lambda *_: {"json": body}),
        EmailHTTPChannel("secret", "from@example.com", "to@example.com",
                         lambda *_: {"json": body}),
    ]
    for channel in channels:
        assert channel.send(channel.preview(candidate)).status == DeliveryStatus.UNCERTAIN


def test_cooldown_is_independent_for_each_channel() -> None:
    first, second = FakeChannel(), FakeChannel()
    first.name, second.name = "telegram", "email"
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_channels", 80)
    ledger = SQLiteOutbox()
    try:
        assert ledger.deliver(candidate, first) == DeliveryStatus.SENT
        assert ledger.deliver(candidate, second) == DeliveryStatus.SENT
        assert first.sent == second.sent == 1
    finally:
        ledger.close()


def test_settings_cannot_enable_missing_channels_or_disabled_policy() -> None:
    status = build_settings_status(
        load_notification_policy(), environment="production", alerts_allowed=True,
        blocking_reasons=(), secrets={},
    )
    assert not status["alertsAllowed"]
    assert "DELIVERY_DISABLED_BY_POLICY" in status["blockingReasons"]
    assert "TELEGRAM_SECRETS_MISSING" in status["blockingReasons"]


def test_missing_or_stale_benchmark_fails_closed() -> None:
    missing = assess_quality_gates({"canonical_valid": True})
    assert not missing.allowed
    assert "MISSING_BENCHMARK" in missing.reasons

    stale = assess_quality_gates({"canonical_valid": True, "stale_benchmark": True})
    assert not stale.allowed
    assert "STALE_BENCHMARK" in stale.reasons


def test_benchmark_fresh_alias_is_supported_without_relaxing_missing_checks() -> None:
    quality = {
        "benchmark_fresh": True,
        "canonical_valid": True,
        "scoring_methodology_complete": True,
        "parse_success_rate": 1.0,
        "market_data_coverage_rate": 0.95,
        "core_branch_coverage_rate": 0.90,
        "quality_gate_passed": True,
    }
    result = assess_quality_gates(quality)
    assert not result.allowed
    assert result.reasons == ("SCORING_METHODOLOGY_INCOMPLETE",)
    assert result.checks["stale_benchmark"] is True

    string_rate = assess_quality_gates({**quality, "parse_success_rate": "1.0"})
    assert not string_rate.allowed
    assert "INSUFFICIENT_PARSE_SUCCESS_RATE" in string_rate.reasons

    incomplete = assess_quality_gates({**quality, "scoring_methodology_complete": False})
    assert not incomplete.allowed
    assert "SCORING_METHODOLOGY_INCOMPLETE" in incomplete.reasons


def test_candidate_rejects_truthy_string_flags_and_non_finite_scores() -> None:
    base = {
        "issuer_cik": "0000000001",
        "alert_type": "TURNING",
        "trigger_snapshot_id": "snap_strict",
        "score": 80,
    }
    with pytest.raises(ValueError, match="JSON boolean"):
        AlertCandidate.from_mapping({**base, "important_flag": "false"})
    with pytest.raises(ValueError, match="finite"):
        AlertCandidate.from_mapping({**base, "score": math.nan})
    with pytest.raises(ValueError, match="important_flag"):
        evaluate_alert_rules(
            {
                "issuer_cik": "0000000001",
                "snapshot_id": "snap_rule_strict",
                "transaction_value_usd": 1_000_000,
                "important_flag": "false",
            }
        )


class FakeChannel:
    name = "fake"

    def __init__(self) -> None:
        self.sent = 0

    def preview(self, candidate: AlertCandidate) -> NotificationPreview:
        return NotificationPreview(candidate, "preview")

    def claim(self, candidate: AlertCandidate, idempotency_key: str) -> bool:
        return True

    def send(self, preview: NotificationPreview) -> SendResult:
        self.sent += 1
        return SendResult.sent("fake-1")

    def record_result(self, candidate: AlertCandidate, result: SendResult) -> None:
        return None


def test_outbox_claim_is_idempotent_and_cooldown_has_score_override() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    channel = FakeChannel()
    outbox = SQLiteOutbox()
    first = AlertCandidate("0000000001", AlertType.TURNING, "snap_a", 75, created_at=now)
    second = AlertCandidate(
        "0000000001", AlertType.TURNING, "snap_b", 76, created_at=now + timedelta(days=1)
    )
    assert outbox.deliver(first, channel, at=now) == DeliveryStatus.SENT
    assert outbox.deliver(first, channel, at=now) == DeliveryStatus.SENT
    assert outbox.deliver(second, channel, at=now + timedelta(days=1)) == DeliveryStatus.SUPPRESSED
    third = AlertCandidate(
        "0000000001", AlertType.TURNING, "snap_c", 82, created_at=now + timedelta(days=2)
    )
    assert outbox.deliver(third, channel, at=now + timedelta(days=2)) == DeliveryStatus.SENT
    assert channel.sent == 2


class AmbiguousChannel(FakeChannel):
    def send(self, preview: NotificationPreview) -> SendResult:
        self.sent += 1
        raise TimeoutError("provider outcome unknown")


def test_transport_crash_after_claim_is_terminal_and_never_retried() -> None:
    channel = AmbiguousChannel()
    outbox = SQLiteOutbox()
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_timeout", 80)

    assert outbox.deliver(candidate, channel) == DeliveryStatus.UNCERTAIN
    assert outbox.deliver(candidate, channel) == DeliveryStatus.UNCERTAIN
    assert channel.sent == 1


def test_corrupt_outbox_is_quarantined_before_recovery(tmp_path: Path) -> None:
    path = tmp_path / "alerts.sqlite"
    path.write_bytes(b"not a sqlite database")

    outbox = SQLiteOutbox(path)
    try:
        assert outbox.recovered_path is not None
        assert outbox.recovered_path.read_bytes() == b"not a sqlite database"
        assert path.is_file()
        candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_corrupt", 80)
        channel = FakeChannel()
        assert outbox.deliver(candidate, channel) == DeliveryStatus.UNCERTAIN
        assert channel.sent == 0
    finally:
        outbox.close()


def test_cooldown_important_override_only_fires_when_flag_is_added() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    channel = FakeChannel()
    outbox = SQLiteOutbox()
    first = AlertCandidate(
        "0000000001",
        AlertType.TURNING,
        "snap_important",
        80,
        important_flag=True,
        created_at=now,
    )
    removed = AlertCandidate(
        "0000000001",
        AlertType.TURNING,
        "snap_removed",
        80,
        important_flag=False,
        created_at=now + timedelta(days=1),
    )

    assert outbox.deliver(first, channel, at=now) == DeliveryStatus.SENT
    assert outbox.deliver(removed, channel, at=now + timedelta(days=1)) == (
        DeliveryStatus.SUPPRESSED
    )
    assert channel.sent == 1


def test_outbox_checkpoint_survives_process_restart(tmp_path: Path) -> None:
    path = tmp_path / "alerts.sqlite"
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_persist", 80)
    first = SQLiteOutbox(path)
    try:
        assert first.claim(candidate, "fake") == DeliveryStatus.CLAIMED
        first.record_result(candidate, "fake", SendResult.sent("provider-1"))
    finally:
        first.close()

    second = SQLiteOutbox(path)
    try:
        assert second.history(candidate.idempotency_key)[-1]["status"] == DeliveryStatus.SENT.value
    finally:
        second.close()


def test_delivery_tests_are_durable_but_do_not_claim_signal_cooldown(tmp_path: Path) -> None:
    path = tmp_path / "alerts.sqlite"
    ledger = SQLiteOutbox(path)
    try:
        ledger.record_delivery_test("telegram", SendResult.sent("test-1"))
        candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_after_test", 80)
        channel = FakeChannel()
        assert ledger.deliver(candidate, channel) == DeliveryStatus.SENT
        assert ledger.test_history()[0]["provider_id"] == "test-1"
    finally:
        ledger.close()


def test_restart_after_durable_claim_is_uncertain_and_never_sends(tmp_path: Path) -> None:
    path = tmp_path / "alerts.sqlite"
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_crash", 80)
    first = SQLiteOutbox(path)
    try:
        assert first.claim(candidate, "fake") == DeliveryStatus.CLAIMED
    finally:
        first.close()

    channel = FakeChannel()
    second = SQLiteOutbox(path)
    try:
        assert second.deliver(candidate, channel) == DeliveryStatus.UNCERTAIN
        assert channel.sent == 0
        assert second.history(candidate.idempotency_key)[-1]["status"] == "UNCERTAIN"
    finally:
        second.close()


def test_second_claim_cannot_steal_an_inflight_delivery() -> None:
    outbox = SQLiteOutbox()
    candidate = AlertCandidate("0000000001", AlertType.TURNING, "snap_inflight", 80)

    assert outbox.claim(candidate, "fake") == DeliveryStatus.CLAIMED
    assert outbox.claim(candidate, "fake") == DeliveryStatus.UNCERTAIN
    assert outbox.record_result(candidate, "fake", SendResult.sent("late")) == (
        DeliveryStatus.UNCERTAIN
    )
    assert [row["status"] for row in outbox.history(candidate.idempotency_key)] == [
        "CLAIMED",
        "UNCERTAIN",
    ]
