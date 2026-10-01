"""Safe workflow reports and durable, at-most-once operational failure notices."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx

from insider_turning_engine.ingestion.sec.historical import _write_json

from .channels import TelegramHTTPChannel
from .models import SendResult
from .state_store import persist, restore


def status_report(repository: str, run_id: str, results: Mapping[str, str],
                  *, digest_expected: bool) -> dict[str, object]:
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or not re.fullmatch(r"[0-9]{1,20}", run_id)
            or set(results) != {"build", "deploy", "digest"}
            or any(value not in {"success", "failure", "cancelled", "skipped"}
                   for value in results.values())):
        raise ValueError("invalid workflow status")
    failed = (results["build"] != "success" or results["deploy"] != "success"
              or (digest_expected and results["digest"] != "success"))
    url = f"https://github.com/{repository}/actions/runs/{run_id}"
    text = ("Insider Turning Engine — operational warning\n"
            + ("Daily refresh did not complete. Previous public snapshot retained.\n"
               if results["deploy"] != "success"
               else "Dashboard updated, but the daily digest failed or was blocked.\n")
            + " · ".join(f"{name}: {value}" for name, value in sorted(results.items()))
            + f"\nDetails: {url}") if failed else ""
    return {"schemaVersion": "1.0.0", "runId": run_id, "url": url,
            "results": dict(results), "digestExpected": digest_expected,
            "status": "FAILED" if failed else "SUCCESS", "text": text}


def send_notice(report: Mapping[str, object], *, outbox: Path,
                save: Callable[[], None], send: Callable[[str], SendResult]) -> str:
    if report["status"] != "FAILED" or not report["text"]:
        return "NOT_NEEDED"
    key = str(report["runId"])
    with closing(sqlite3.connect(outbox)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS workflow_notices "
                   "(run_id TEXT PRIMARY KEY, status TEXT NOT NULL, recorded_at TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM workflow_notices WHERE run_id=?", (key,)).fetchone():
            return "ALREADY_CLAIMED"
        db.execute("INSERT INTO workflow_notices VALUES (?, 'CLAIMED', ?)",
                   (key, datetime.now(UTC).isoformat()))
    save()  # Remote claim must be durable before the one allowed send attempt.
    try:
        result = send(str(report["text"]))
        status = result.status.value
        if status not in {"SENT", "FAILED", "UNCERTAIN"}:
            status = "UNCERTAIN"
    except Exception:
        status = "UNCERTAIN"
    with closing(sqlite3.connect(outbox)) as db, db:
        db.execute("UPDATE workflow_notices SET status=?, recorded_at=? WHERE run_id=?",
                   (status, datetime.now(UTC).isoformat(), key))
    save()
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work/workflow-status.json"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = status_report(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"],
                           {name: os.environ[f"RESULT_{name.upper()}"]
                            for name in ("build", "deploy", "digest")},
                           digest_expected=os.environ.get("DIGEST_EXPECTED") == "true")
    notice = "PREVIEW" if report["status"] == "FAILED" else "NOT_NEEDED"
    if args.execute and report["status"] == "FAILED":
        production = (os.environ.get("GITHUB_ACTIONS") == "true"
                      and os.environ.get("GITHUB_REF") == "refs/heads/main"
                      and os.environ.get("GITHUB_RUN_ATTEMPT") == "1")
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not production or not token or not chat:
            notice = "NOT_CONFIGURED_OR_RERUN"
        else:
            store, outbox = Path("work/workflow-state"), Path("work/workflow-alerts.sqlite")
            try:
                restore(Path.cwd(), store, outbox)
                channel = TelegramHTTPChannel(token, chat,
                    lambda url, payload: httpx.post(url, data=payload, timeout=20))
                notice = send_notice(report, outbox=outbox,
                    save=lambda: persist(store, outbox),
                    send=channel.send_text)
            except Exception:
                notice = "STATE_PERSISTENCE_FAILED"
    report["notificationStatus"] = notice
    _write_json(args.output, report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"## Daily pipeline: {report['status']}\n\n")
            stream.write("| Stage | Result |\n| --- | --- |\n")
            for name in ("build", "deploy", "digest"):
                stream.write(f"| {name} | {os.environ[f'RESULT_{name.upper()}']} |\n")
            stream.write(f"\nOperational notice: {notice}\n\n[Run details]({report['url']})\n")
    print(json.dumps(report, sort_keys=True))
    if notice in {"FAILED", "UNCERTAIN", "STATE_PERSISTENCE_FAILED"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
