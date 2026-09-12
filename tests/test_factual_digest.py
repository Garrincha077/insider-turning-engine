import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_research_snapshot import _record

from insider_turning_engine.domain.research import DayEvidence
from insider_turning_engine.notifications.channels import TelegramHTTPChannel
from insider_turning_engine.notifications.digest import (
    DigestPolicy,
    deliver_digest,
    delivery_reasons,
    digest_history,
    preview_digest,
    public_digest_status,
)
from insider_turning_engine.notifications.models import SendResult
from insider_turning_engine.pipeline.research_snapshot import build_research_snapshot

NOW = datetime(2026, 9, 1, 8, tzinfo=UTC)
DAY = datetime(2026, 8, 31, tzinfo=UTC).date()
POLICY = DigestPolicy(schemaVersion="1.0.0", enabled=True, channel="telegram",
                      minimumPurchaseUsd=250000, maximumItems=5)


def snapshot(*, complete=True, value=250000, count=1, joint=False):
    rows = []
    for index in range(count):
        row = _record(accession=f"0001234567-26-{index + 1:06d}")
        row.transaction.shares = value + index
        row.transaction.price_per_share = 1
        row.transaction.value = value + index
        rows.append(row)
        if joint:
            # Rebuild proper source/transaction/revision identity through the fixture parser.
            owner = _record(accession=f"0001234567-26-{index + 1:06d}", owner="0001999102")
            owner.transaction = row.transaction.model_copy(deep=True)
            rows.append(owner)
    return build_research_snapshot(rows, as_of=NOW, run_id="run_digest_fixture_001",
        identities={rows[0].issuer.cik: {"ticker": "ACME"}}, expected_sec_days=[DAY],
        sec_day_by_accession={row.source.accession_number: DAY for row in rows},
        day_evidence=[DayEvidence(day=DAY, discovered_filings=count, stored_filings=count,
            parse_rows=len(rows), quarantined_rows=0 if complete else 1, failures=0,
            complete=complete)])


def test_preview_boundaries_sort_joint_owners_no_scores():
    data = snapshot(count=7, joint=True)
    draft = preview_digest(data)
    assert len(draft.event_ids) == 5
    assert draft.event_ids[0] == sorted(data.economic_transactions,
                                      key=lambda row: -(row.value or 0))[0].event_id
    assert draft.text.count("Transaction:") == 5
    assert "250,006" in draft.text
    assert "score criteria" in draft.text
    assert "#view=company-lab&amp;issuer=" in draft.text
    assert data.research_scores[0].total is None
    assert not preview_digest(snapshot(value=249999)).event_ids
    assert len(preview_digest(snapshot()).event_ids) == 1


def test_incomplete_latest_day_does_not_fall_back_or_assert_empty():
    data = snapshot(complete=False)
    draft = preview_digest(data)
    assert draft.reasons == ("LATEST_SEC_DAY_INCOMPLETE",)
    assert not draft.text and not draft.event_ids
    data = snapshot()
    data.coverage.expected_sec_days.append(DAY + timedelta(days=1))
    assert preview_digest(data).reasons == ("LATEST_SEC_DAY_INCOMPLETE",)


def test_empty_unresolved_suppressed_and_html_escaped():
    data = snapshot()
    data.companies[0].identity_status = "UNRESOLVED"
    assert preview_digest(data).reasons == ("EMPTY_DIGEST_HAS_UNRESOLVED_INPUTS",)
    data = snapshot()
    data.companies[0].ticker = "<Acme&Co>"
    data.reporting_owners[0].name = "<script> & Owner"
    text = preview_digest(data).text
    assert "&lt;Acme&amp;Co&gt;" in text and "<script>" not in text


def test_policy_and_staleness_independent_of_predictive_gate():
    data = snapshot()
    draft = preview_digest(data)
    assert not delivery_reasons(draft, data, POLICY, now=NOW, production=True, configured=True)
    disabled = POLICY.model_copy(update={"enabled": False})
    reasons = delivery_reasons(draft, data, disabled, now=NOW + timedelta(days=3),
                               production=False, configured=False)
    assert set(reasons) == {"DIGEST_DISABLED_BY_POLICY", "DIGEST_SEC_DAY_STALE",
        "DIGEST_SNAPSHOT_STALE", "NON_PRODUCTION_ENVIRONMENT", "TELEGRAM_SECRETS_MISSING"}
    assert data.readiness.predictive.status == "BLOCKED"
    with pytest.raises(ValueError):
        DigestPolicy.model_validate({**POLICY.model_dump(), "enabled": "false"})


@pytest.mark.parametrize("outcome", [SendResult.sent("42"), SendResult.failed("provider detail"),
                                    SendResult.uncertain("secret exception text")])
def test_claim_durable_before_send_every_outcome_blocks_replay(tmp_path, outcome):
    path = tmp_path / "alerts.sqlite"
    draft = preview_digest(snapshot())
    order = []

    def persist():
        order.append("persist")
        assert digest_history(path)[0]["status"] in {"CLAIMED", outcome.status.value}

    def send(text):
        assert order == ["persist"]
        assert digest_history(path)[0]["status"] == "CLAIMED"
        order.append("send")
        return outcome

    assert deliver_digest(draft, outbox=path, now=NOW, persist=persist, send=send) \
        == outcome.status.value
    assert order == ["persist", "send", "persist"]
    assert deliver_digest(draft, outbox=path, now=NOW, persist=persist, send=send) \
        == "ALREADY_CLAIMED_OR_OLDER_DAY"
    assert "secret" not in json.dumps(digest_history(path))
    assert "provider detail" not in json.dumps(digest_history(path))


def test_persistence_failure_and_crash_never_redeliver(tmp_path):
    path = tmp_path / "alerts.sqlite"
    draft = preview_digest(snapshot())
    calls = []

    def broken_persist():
        raise RuntimeError("remote push failed")

    with pytest.raises(RuntimeError):
        deliver_digest(draft, outbox=path, now=NOW, persist=broken_persist,
                       send=lambda text: calls.append(text))
    assert calls == [] and digest_history(path)[0]["status"] == "CLAIMED"
    assert deliver_digest(draft, outbox=path, now=NOW, persist=broken_persist,
                          send=lambda text: calls.append(text)) == "ALREADY_CLAIMED_OR_OLDER_DAY"


def test_corrupt_ledger_fails_closed_and_preserves_predictive_tables(tmp_path):
    path = tmp_path / "alerts.sqlite"
    path.write_bytes(b"corrupt evidence")
    with pytest.raises(sqlite3.DatabaseError):
        deliver_digest(preview_digest(snapshot()), outbox=path, now=NOW,
                       persist=lambda: None, send=lambda text: pytest.fail("must not send"))
    assert path.read_bytes() == b"corrupt evidence"
    good = tmp_path / "good.sqlite"
    with sqlite3.connect(good) as db:
        db.execute("CREATE TABLE other_evidence (value TEXT)")
        db.execute("INSERT INTO other_evidence VALUES ('preserve')")
    deliver_digest(preview_digest(snapshot()), outbox=good, now=NOW,
                   persist=lambda: None, send=lambda text: SendResult.sent())
    with sqlite3.connect(good) as db:
        assert db.execute("SELECT value FROM other_evidence").fetchone() == ("preserve",)


def test_telegram_factual_text_and_ambiguous_server_error():
    channel = TelegramHTTPChannel("private-token", "private-recipient",
                                  lambda url, payload: {"status_code": 503})
    assert channel.send_text("facts").status == "UNCERTAIN"


def test_older_backfill_never_sent_after_latest_claim(tmp_path):
    path = tmp_path / "alerts.sqlite"
    draft = preview_digest(snapshot())
    deliver_digest(draft, outbox=path, now=NOW, persist=lambda: None,
                   send=lambda text: SendResult.sent())
    older = draft.model_copy(update={"sec_day": DAY - timedelta(days=1)})
    assert deliver_digest(older, outbox=path, now=NOW, persist=lambda: None,
                          send=lambda text: pytest.fail("no backlog")) \
        == "ALREADY_CLAIMED_OR_OLDER_DAY"


def test_result_persistence_failure_leaves_remote_claim_blocking_retry(tmp_path):
    import shutil

    path, remote = tmp_path / "local.sqlite", tmp_path / "remote.sqlite"
    draft = preview_digest(snapshot())
    calls = []

    def persist():
        if remote.exists():
            raise RuntimeError("result push failed")
        shutil.copyfile(path, remote)

    def send(text):
        calls.append(text)
        return SendResult.sent()

    with pytest.raises(RuntimeError):
        deliver_digest(draft, outbox=path, now=NOW, persist=persist, send=send)
    assert digest_history(remote)[0]["status"] == "CLAIMED"
    assert deliver_digest(draft, outbox=remote, now=NOW, persist=persist, send=send) \
        == "ALREADY_CLAIMED_OR_OLDER_DAY"
    assert len(calls) == 1


def test_cli_preview_validates_hashes_without_network_or_claim(tmp_path, monkeypatch, capsys):
    from test_dashboard_export import _data

    from insider_turning_engine.export.dashboard import DashboardExportError, export_dashboard
    from insider_turning_engine.notifications import digest_cli

    data = _data()
    data["researchSnapshot"] = snapshot().model_dump(mode="json", by_alias=True)
    data["generatedAt"] = NOW.isoformat()
    root, output = tmp_path / "public", tmp_path / "preview.json"
    export_dashboard(data, root, run_id="run_digest_fixture_001", as_of=NOW)
    monkeypatch.setattr(digest_cli.httpx, "post", lambda *a, **kw: pytest.fail("preview HTTP"))
    monkeypatch.setattr(digest_cli, "restore", lambda *a: pytest.fail("preview state write"))
    monkeypatch.setattr("sys.argv", ["digest", "--directory", str(root), "--output", str(output)])
    digest_cli.main()
    assert json.loads(output.read_text())["status"] == "PREVIEW"
    assert "daily facts" in capsys.readouterr().out
    (root / "research-v2.json").write_text("{}")
    with pytest.raises(DashboardExportError):
        digest_cli.main()


def test_public_settings_digest_schema_and_day_claim_status(tmp_path):
    import jsonschema

    from insider_turning_engine.notifications.config import load_notification_policy
    from insider_turning_engine.notifications.settings import build_settings_status

    data, path = snapshot(), tmp_path / "alerts.sqlite"
    draft = preview_digest(data)
    deliver_digest(draft, outbox=path, now=NOW, persist=lambda: None,
                   send=lambda text: SendResult.sent())
    status = build_settings_status(load_notification_policy(), environment="production",
        alerts_allowed=False, blocking_reasons=[], secrets={"TELEGRAM_BOT_TOKEN": "supersecret"},
        factual_history=digest_history(path))
    status["digest"] = public_digest_status(data, POLICY, now=NOW, production=True,
                                            configured=True, outbox=path)
    assert status["digest"]["reasons"] == ["ALREADY_CLAIMED_OR_OLDER_DAY"]
    assert status["deliveryHistory"][0]["kind"] == "DIGEST"
    assert "supersecret" not in json.dumps(status)
    schema = json.loads(Path("schemas/settings-status.schema.json").read_text())
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()).validate(status)


def test_derivative_total_value_is_never_invented_as_share_quantity():
    from insider_turning_engine.ingestion.sec.parser import parse_sec_xml

    xml = Path("tests/fixtures/form4_derivative.xml").read_text()
    xml = xml.replace("<transactionShares><value>50</value></transactionShares>",
                      "<transactionTotalValue><value>35000</value></transactionTotalValue>")
    result = parse_sec_xml(xml.encode(), {"accession_number": "0001234567-26-000009",
        "source_url": "https://www.sec.gov/Archives/test.xml", "accepted_at": NOW,
        "observed_at": NOW, "run_id": "run_derivative_total_value_001"})
    assert not result.records
    assert result.quarantines[0].reason_code == "INVALID_TRANSACTION"
    assert "shares are required" in result.quarantines[0].message
