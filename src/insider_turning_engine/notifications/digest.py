"""Offline factual digest and fail-closed, channel/day at-most-once ledger.

Independent of score policy. A committed claim must be remotely durable before
HTTP. Every existing claim (including FAILED) blocks automatic redelivery.
"""

from __future__ import annotations

import hashlib
import html
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from insider_turning_engine.domain.research import EconomicEvent, ResearchSnapshot
from insider_turning_engine.domain.session_calendar import latest_closed_session

from .models import DeliveryStatus, SendResult
from .state_store import _validate_ledger

SITE = "https://garrincha077.github.io/insider-turning-engine/"


class DigestPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schemaVersion: Literal["1.0.0"]
    enabled: bool
    channel: Literal["telegram"]
    minimumPurchaseUsd: Literal[250000]
    maximumItems: Literal[5]


class DigestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    sec_day: date | None
    event_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    text: str = ""
    excluded_issuers: int | None = Field(default=None, ge=0)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def load_digest_policy(path: Path = Path("config/digest.v1.json")) -> DigestPolicy:
    return DigestPolicy.model_validate_json(path.read_bytes())


def preview_digest(snapshot: ResearchSnapshot) -> DigestDraft:
    """Use only the newest inventoried SEC day, never an older complete fallback.

    Preview does not inspect credentials, mutate state or contact any provider.
    Missing market data/score and incomplete earlier backfill do not suppress facts.
    """
    snapshot = ResearchSnapshot.model_validate(snapshot.model_dump())
    coverage = snapshot.coverage
    day = max(coverage.expected_sec_days, default=None)
    proof = [item for item in coverage.days if item.day == day]
    reason: tuple[str, ...] = (() if len(proof) == 1 and proof[0].complete
                               else ("LATEST_SEC_DAY_INCOMPLETE",))
    if snapshot.readiness.dashboard.status == "BLOCKED":
        reason += ("DASHBOARD_INVALID",)
    if any(row.sec_day is None for row in snapshot.economic_transactions):
        reason += ("DIGEST_EVENT_DAY_MISSING",)
    if reason:
        return DigestDraft(run_id=snapshot.run_id, sec_day=day, reasons=reason)
    companies = {row.issuer_cik: row for row in snapshot.companies}
    owners = {row.owner_cik: row.name for row in snapshot.reporting_owners}
    latest = [row for row in snapshot.economic_transactions if row.sec_day == day]
    excluded = {row.issuer_cik for row in latest
                if companies[row.issuer_cik].insider_status != "AVAILABLE"
                or companies[row.issuer_cik].identity_status != "RESOLVED"}

    def eligible(row: EconomicEvent) -> bool:
        company = companies[row.issuer_cik]
        return (row.aggregate_eligible and row.qualified and row.processing == "EFFECTIVE"
                and row.table == "NON_DERIVATIVE" and row.code == "P" and row.side == "BUY"
                and row.shares > 0 and row.price is not None and row.price > 0
                and row.value is not None and row.value >= 250000
                and company.identity_status == "RESOLVED" and company.insider_status == "AVAILABLE")

    selected = sorted((row for row in latest if eligible(row)),
                      key=lambda row: (-(row.value or 0), row.event_id))[:5]
    # An unknown purchase value cannot support a negative factual assertion.
    unknown = any(row.table == "NON_DERIVATIVE" and row.code == "P"
                  and row.value is None for row in latest)
    if not selected and (excluded or unknown):
        return DigestDraft(run_id=snapshot.run_id, sec_day=day, excluded_issuers=len(excluded),
                           reasons=("EMPTY_DIGEST_HAS_UNRESOLVED_INPUTS",))
    parts = [f"<b>Insider Turning Engine — daily facts</b>\nSEC day: {day}",
             "Observed eligible US common-stock purchases ≥ $250,000; largest five. "
             "Not a market-wide census. No score criteria or trading recommendations."]
    for row in selected:
        company = companies[row.issuer_cik]
        # Truncate individual labels, never an assembled HTML document/link.
        label = html.escape((company.ticker or company.name)[:80])
        names = html.escape(" / ".join(owners[link.owner_cik]
                                      for link in sorted(row.owners,
                                                         key=lambda link: link.owner_cik))[:180])
        parts.append(f"<b>{label} — ${row.value:,.0f}</b>\n{names}\n"
                     f"Transaction: {row.transaction_date}\n"
                     f'<a href="{html.escape(row.source_url, quote=True)}">SEC filing</a> · '
                     f'<a href="{SITE}#view=company-lab&amp;issuer={row.issuer_cik}">'
                     'Company Lab</a>')
    if not selected:
        parts.append("No new qualifying purchases in the resolved eligible universe.")
    if excluded:
        parts.append(f"{len(excluded)} unresolved issuer(s) excluded; see Data Coverage.")
    text = "\n\n".join(parts)
    if len(text.encode("utf-16-le")) // 2 > 4096:
        return DigestDraft(run_id=snapshot.run_id, sec_day=day,
                           reasons=("DIGEST_MESSAGE_TOO_LONG",))
    return DigestDraft(run_id=snapshot.run_id, sec_day=day, text=text,
                       event_ids=tuple(row.event_id for row in selected),
                       excluded_issuers=len(excluded))


def delivery_reasons(
    draft: DigestDraft, snapshot: ResearchSnapshot, policy: DigestPolicy, *,
    now: datetime, production: bool, configured: bool,
) -> tuple[str, ...]:
    if now.tzinfo is None:
        raise ValueError("delivery clock must be timezone-aware")
    reasons = list(draft.reasons)
    if not policy.enabled:
        reasons.append("DIGEST_DISABLED_BY_POLICY")
    if not production:
        reasons.append("NON_PRODUCTION_ENVIRONMENT")
    if not configured:
        reasons.append("TELEGRAM_SECRETS_MISSING")
    if not timedelta(0) <= now - snapshot.as_of <= timedelta(hours=24):
        reasons.append("DIGEST_SNAPSHOT_STALE")
    if draft.sec_day is None or draft.sec_day < latest_closed_session(now):
        reasons.append("DIGEST_SEC_DAY_STALE")
    return tuple(sorted(set(reasons)))


def _connect(path: Path) -> sqlite3.Connection:
    # No automatic corruption recovery: losing a claim could duplicate delivery.
    if path.exists():
        _validate_ledger(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS factual_digest_claims (
        channel TEXT NOT NULL, sec_day TEXT NOT NULL, run_id TEXT NOT NULL,
        content_hash TEXT NOT NULL, claimed_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('CLAIMED','SENT','FAILED','UNCERTAIN')),
        provider_id TEXT, claim_id TEXT NOT NULL,
        PRIMARY KEY(channel, sec_day))""")
    return db


def deliver_digest(
    draft: DigestDraft, *, outbox: Path, now: datetime,
    persist: Callable[[], None], send: Callable[[str], SendResult],
) -> str:
    """Caller validates publication/policy/clock/secrets before invoking this.

    In a crash after remote claim, the remote CLAIMED row remains a permanent
    retry blocker. Failed result persistence also leaves that safe remote claim.
    Never persist text, recipient, token, provider errors or URLs in this ledger.
    """
    if draft.reasons or draft.sec_day is None or not draft.text or now.tzinfo is None:
        raise ValueError("cannot claim an invalid digest")
    instant = now.astimezone(UTC).isoformat()
    key = ("telegram", draft.sec_day.isoformat())
    with closing(_connect(outbox)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        latest = db.execute("SELECT MAX(sec_day) FROM factual_digest_claims WHERE channel=?",
                            (key[0],)).fetchone()[0]
        if latest is not None and latest >= key[1]:
            return "ALREADY_CLAIMED_OR_OLDER_DAY"
        # Unique lease prevents two isolated writers producing an identical Git
        # commit/no-op push even if their run ID, content and clocks coincide.
        db.execute("INSERT INTO factual_digest_claims "
                   "VALUES (?, ?, ?, ?, ?, ?, 'CLAIMED', NULL, ?)",
                   (*key, draft.run_id, draft.content_hash, instant, instant, uuid4().hex))
    persist()  # MUST succeed before the only possible provider call.
    provider_id = None
    try:
        result = send(draft.text)
        status = result.status if result.status in {
            DeliveryStatus.SENT, DeliveryStatus.FAILED, DeliveryStatus.UNCERTAIN,
        } else DeliveryStatus.UNCERTAIN
        if (result.provider_id is not None and result.provider_id.isascii()
                and result.provider_id.isdigit() and len(result.provider_id) <= 20):
            provider_id = result.provider_id
    except Exception:
        status = DeliveryStatus.UNCERTAIN
    with closing(_connect(outbox)) as db, db:
        db.execute("UPDATE factual_digest_claims SET status=?, recorded_at=?, provider_id=? "
                   "WHERE channel=? AND sec_day=? AND status='CLAIMED'",
                   (status.value, datetime.now(UTC).isoformat(), provider_id, *key))
    persist()
    return status.value


def digest_history(path: Path) -> list[dict[str, str]]:
    """Read-only, safe public projection; never create/reset a missing ledger."""
    if not path.exists():
        return []
    _validate_ledger(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                      "AND name='factual_digest_claims'").fetchone() is None:
            return []
        rows = db.execute("SELECT channel, sec_day, status, recorded_at "
                          "FROM factual_digest_claims ORDER BY sec_day DESC LIMIT 100").fetchall()
    return [{"channel": channel, "secDay": day, "status": status, "recorded_at": at}
            for channel, day, status, at in rows]


def public_digest_status(
    snapshot: ResearchSnapshot, policy: DigestPolicy, *, now: datetime,
    production: bool, configured: bool, outbox: Path,
) -> dict[str, object]:
    """Operational projection shares the exact backend selection and gates."""
    draft = preview_digest(snapshot)
    reasons = delivery_reasons(draft, snapshot, policy, now=now,
                               production=production, configured=configured)
    history = digest_history(outbox)
    if draft.sec_day is not None and any(row["secDay"] >= draft.sec_day.isoformat()
                                        for row in history):
        reasons += ("ALREADY_CLAIMED_OR_OLDER_DAY",)
    return {"enabled": policy.enabled, "secDay": str(draft.sec_day) if draft.sec_day else None,
            "status": "BLOCKED" if reasons else "READY", "reasons": sorted(set(reasons)),
            "eventIds": list(draft.event_ids), "excludedIssuers": draft.excluded_issuers}
