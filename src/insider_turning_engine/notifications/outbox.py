"""Durable, local alert candidate and delivery ledger."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from .channels import NotificationChannel
from .models import AlertCandidate, DeliveryStatus, SendResult


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


class SQLiteOutbox:
    """SQLite ledger with ``BEGIN IMMEDIATE`` at-most-once claims."""

    def __init__(self, path: str | Path = ":memory:", cooldown_days: int = 14) -> None:
        self.cooldown = timedelta(days=cooldown_days)
        self._lock = threading.RLock()
        self.recovered_path: Path | None = None
        self._path = None if str(path) == ":memory:" else Path(path)
        self._db = self._open_database(path)
        try:
            self._initialize()
            self._recover_abandoned_claims()
        except sqlite3.DatabaseError as exc:
            self._db.close()
            if self._path is None or not self._is_corrupt_database(exc):
                raise
            self.recovered_path = self._quarantine_corrupt_database(self._path)
            self._db = self._open_database(self._path)
            self._initialize()

    @staticmethod
    def _open_database(path: str | Path) -> sqlite3.Connection:
        database = sqlite3.connect(str(path), check_same_thread=False)
        database.row_factory = sqlite3.Row
        return database

    def _initialize(self) -> None:
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS candidates (
                idempotency_key TEXT PRIMARY KEY,
                issuer_cik TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                trigger_snapshot_id TEXT NOT NULL,
                candidate_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                error TEXT,
                provider_id TEXT,
                UNIQUE(idempotency_key, channel)
            );
            CREATE TABLE IF NOT EXISTS delivery_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                error TEXT,
                provider_id TEXT
            );
            CREATE TABLE IF NOT EXISTS delivery_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                error TEXT,
                provider_id TEXT
            );
            """
        )

    def _recover_abandoned_claims(self) -> None:
        """Make claims left by a stopped process terminal before any send.

        A durable ``CLAIMED`` row is intentionally ambiguous after restart:
        the previous process may have reached the provider before it stopped.
        At-most-once delivery therefore forbids reclaiming it automatically.
        """

        rows = self._db.execute(
            "SELECT idempotency_key, channel FROM deliveries WHERE status='CLAIMED'"
        ).fetchall()
        if not rows:
            return
        at = datetime.now(UTC)
        error = "process restarted with an unresolved durable claim"
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for row in rows:
                    cursor = self._db.execute(
                        """UPDATE deliveries
                           SET status=?, attempted_at=?, error=?
                           WHERE idempotency_key=? AND channel=? AND status='CLAIMED'""",
                        (
                            DeliveryStatus.UNCERTAIN.value,
                            _iso(at),
                            error,
                            row["idempotency_key"],
                            row["channel"],
                        ),
                    )
                    if cursor.rowcount == 1:
                        self._record_history(
                            row["idempotency_key"],
                            row["channel"],
                            DeliveryStatus.UNCERTAIN,
                            at,
                            error,
                        )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    @staticmethod
    def _is_corrupt_database(error: sqlite3.DatabaseError) -> bool:
        message = str(error).lower()
        return any(
            marker in message
            for marker in (
                "file is not a database",
                "database disk image is malformed",
                "malformed",
            )
        )

    @staticmethod
    def _quarantine_corrupt_database(path: Path) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        recovered = path.with_name(f"{path.name}.corrupt-{stamp}")
        # A stale WAL can make a newly created database inherit the same
        # invalid state, so preserve it beside the corrupt main file too.
        for source, target in (
            (path, recovered),
            (Path(f"{path}-wal"), Path(f"{recovered}-wal")),
            (Path(f"{path}-shm"), Path(f"{recovered}-shm")),
        ):
            if source.exists():
                os.replace(source, target)
        return recovered

    def close(self) -> None:
        with self._lock:
            # Actions persists the SQLite file between runs.  Checkpoint the
            # WAL before closing so the allow-listed main file is a complete
            # ledger even when the runner does not preserve sidecar files.
            try:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                self._db.close()

    def put_candidate(self, candidate: AlertCandidate) -> bool:
        payload = json.dumps(_candidate_dict(candidate), sort_keys=True)
        with self._lock:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO candidates VALUES (?, ?, ?, ?, ?, ?)",
                (
                    candidate.idempotency_key,
                    candidate.issuer_cik,
                    candidate.alert_type.value,
                    candidate.trigger_snapshot_id,
                    payload,
                    _iso(candidate.created_at),
                ),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def get_candidate(self, idempotency_key: str) -> AlertCandidate | None:
        row = self._db.execute(
            "SELECT candidate_json FROM candidates WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return AlertCandidate.from_mapping(json.loads(row["candidate_json"])) if row else None

    def history(self, idempotency_key: str | None = None) -> tuple[sqlite3.Row, ...]:
        query = "SELECT * FROM delivery_history"
        args: tuple[str, ...] = ()
        if idempotency_key:
            query += " WHERE idempotency_key = ?"
            args = (idempotency_key,)
        query += " ORDER BY id"
        return tuple(self._db.execute(query, args).fetchall())

    def test_history(self) -> tuple[sqlite3.Row, ...]:
        return tuple(self._db.execute("SELECT * FROM delivery_tests ORDER BY id").fetchall())

    def record_delivery_test(
        self,
        channel: str,
        result: SendResult,
        *,
        at: datetime | None = None,
    ) -> None:
        if result.status not in {
            DeliveryStatus.SENT,
            DeliveryStatus.FAILED,
            DeliveryStatus.UNCERTAIN,
        }:
            raise ValueError("test result must be SENT, FAILED, or UNCERTAIN")
        point = at or datetime.now(UTC)
        with self._lock:
            self._db.execute(
                """INSERT INTO delivery_tests
                   (channel, status, recorded_at, error, provider_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (channel, result.status.value, _iso(point), result.error, result.provider_id),
            )
            self._db.commit()

    def _latest_sent(
        self, candidate: AlertCandidate, channel: str, at: datetime
    ) -> sqlite3.Row | None:
        cutoff = _iso(at - self.cooldown)
        row = self._db.execute(
            """SELECT d.*, c.candidate_json
               FROM deliveries d JOIN candidates c
                 ON c.idempotency_key = d.idempotency_key
               WHERE c.issuer_cik = ? AND c.alert_type = ?
                 AND d.status = 'SENT'
                 AND d.channel = ?
                 AND d.attempted_at >= ?
               ORDER BY d.attempted_at DESC LIMIT 1""",
            (candidate.issuer_cik, candidate.alert_type.value, channel, cutoff),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _cooldown_override(candidate: AlertCandidate, previous: AlertCandidate) -> bool:
        state_changed = candidate.state is not None and candidate.state != previous.state
        severity_changed = previous.severity is not None and candidate.severity != previous.severity
        important_changed = candidate.important_flag and not previous.important_flag
        delta = candidate.absolute_score_delta
        if delta is None:
            delta = abs(candidate.score - previous.score)
        return state_changed or severity_changed or important_changed or abs(delta) >= 7

    def claim(
        self, candidate: AlertCandidate, channel: str = "default", *, at: datetime | None = None
    ) -> DeliveryStatus:
        """Atomically claim a candidate before any channel send occurs."""
        at = at or datetime.now(UTC)
        self.put_candidate(candidate)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT status FROM deliveries WHERE idempotency_key=? AND channel=?",
                    (candidate.idempotency_key, channel),
                ).fetchone()
                if existing:
                    status = DeliveryStatus(existing["status"])
                    if status == DeliveryStatus.CLAIMED:
                        # A second owner cannot distinguish an in-flight send
                        # from a process that stopped after provider acceptance.
                        # Resolve the durable ambiguity without sending again.
                        status = DeliveryStatus.UNCERTAIN
                        error = "durable claim already exists"
                        self._db.execute(
                            """UPDATE deliveries
                               SET status=?, attempted_at=?, error=?
                               WHERE idempotency_key=? AND channel=? AND status='CLAIMED'""",
                            (
                                status.value,
                                _iso(at),
                                error,
                                candidate.idempotency_key,
                                channel,
                            ),
                        )
                        self._record_history(candidate.idempotency_key, channel, status, at, error)
                else:
                    claim_error: str | None = None
                    if self.recovered_path is not None:
                        # The quarantined ledger may contain sends and cooldown
                        # history that cannot be reconstructed safely.
                        status = DeliveryStatus.UNCERTAIN
                        claim_error = "outbox recovered from corruption; delivery disabled"
                    else:
                        latest = self._latest_sent(candidate, channel, at)
                        if latest:
                            previous = AlertCandidate.from_mapping(
                                json.loads(latest["candidate_json"])
                            )
                            status = (
                                DeliveryStatus.CLAIMED
                                if self._cooldown_override(candidate, previous)
                                else DeliveryStatus.SUPPRESSED
                            )
                        else:
                            status = DeliveryStatus.CLAIMED
                    self._db.execute(
                        """INSERT INTO deliveries
                           (idempotency_key, channel, status, attempted_at, error)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            candidate.idempotency_key,
                            channel,
                            status.value,
                            _iso(at),
                            claim_error,
                        ),
                    )
                    self._record_history(
                        candidate.idempotency_key, channel, status, at, claim_error
                    )
                self._db.commit()
                return status
            except Exception:
                self._db.rollback()
                raise

    def record_result(
        self,
        candidate: AlertCandidate,
        channel: str,
        result: SendResult,
        *,
        at: datetime | None = None,
    ) -> DeliveryStatus:
        at = at or datetime.now(UTC)
        status = result.status
        if status not in {DeliveryStatus.SENT, DeliveryStatus.FAILED, DeliveryStatus.UNCERTAIN}:
            raise ValueError("result must be SENT, FAILED, or UNCERTAIN")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._db.execute(
                    """UPDATE deliveries
                       SET status=?, attempted_at=?, error=?, provider_id=?
                       WHERE idempotency_key=? AND channel=? AND status='CLAIMED'""",
                    (
                        status.value,
                        _iso(at),
                        result.error,
                        result.provider_id,
                        candidate.idempotency_key,
                        channel,
                    ),
                )
                if cursor.rowcount == 1:
                    self._record_history(
                        candidate.idempotency_key,
                        channel,
                        status,
                        at,
                        result.error,
                        result.provider_id,
                    )
                else:
                    existing = self._db.execute(
                        "SELECT status FROM deliveries WHERE idempotency_key=? AND channel=?",
                        (candidate.idempotency_key, channel),
                    ).fetchone()
                    if existing is None:
                        raise ValueError("delivery result has no durable claim")
                    status = DeliveryStatus(existing["status"])
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return status

    def deliver(
        self, candidate: AlertCandidate, channel: NotificationChannel, *, at: datetime | None = None
    ) -> DeliveryStatus:
        """Preview, atomically claim, then send exactly once."""
        at = at or datetime.now(UTC)
        self.put_candidate(candidate)
        if candidate.suppression_reasons:
            status = self.claim(candidate, channel.name, at=at)
            if status == DeliveryStatus.CLAIMED:
                return self._suppress_claim(candidate, channel.name, at)
            return status
        preview = channel.preview(candidate)
        status = self.claim(candidate, channel.name, at=at)
        if status != DeliveryStatus.CLAIMED:
            return status
        try:
            if not channel.claim(candidate, candidate.idempotency_key):
                result = SendResult.failed("channel claim rejected")
            else:
                result = channel.send(preview)
        except Exception as exc:
            # A thrown transport/claim error is ambiguous: the provider may
            # have accepted the message, so this terminal state is never retried.
            result = SendResult.uncertain(type(exc).__name__)
        recorded = self.record_result(candidate, channel.name, result, at=at)
        channel.record_result(candidate, result)
        return recorded

    def _suppress_claim(
        self, candidate: AlertCandidate, channel: str, at: datetime
    ) -> DeliveryStatus:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    """UPDATE deliveries SET status=?
                       WHERE idempotency_key=? AND channel=? AND status=?""",
                    (
                        DeliveryStatus.SUPPRESSED.value,
                        candidate.idempotency_key,
                        channel,
                        DeliveryStatus.CLAIMED.value,
                    ),
                )
                self._record_history(
                    candidate.idempotency_key,
                    channel,
                    DeliveryStatus.SUPPRESSED,
                    at,
                    "; ".join(candidate.suppression_reasons),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return DeliveryStatus.SUPPRESSED

    def _record_history(
        self,
        key: str,
        channel: str,
        status: DeliveryStatus,
        at: datetime,
        error: str | None = None,
        provider_id: str | None = None,
    ) -> None:
        self._db.execute(
            """INSERT INTO delivery_history
               (idempotency_key, channel, status, recorded_at, error, provider_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (key, channel, status.value, _iso(at), error, provider_id),
        )


def _candidate_dict(candidate: AlertCandidate) -> dict[str, Any]:
    return {
        "issuer_cik": candidate.issuer_cik,
        "alert_type": candidate.alert_type.value,
        "trigger_snapshot_id": candidate.trigger_snapshot_id,
        "score": candidate.score,
        "severity": candidate.severity.value,
        "important_flag": candidate.important_flag,
        "reasons": list(candidate.reasons),
        "ticker": candidate.ticker,
        "state": candidate.state,
        "previous_state": candidate.previous_state,
        "previous_severity": candidate.previous_severity.value
        if candidate.previous_severity
        else None,
        "previous_important_flag": candidate.previous_important_flag,
        "absolute_score_delta": candidate.absolute_score_delta,
        "created_at": _iso(candidate.created_at),
        "suppression_reasons": list(candidate.suppression_reasons),
    }


__all__ = ["SQLiteOutbox"]
