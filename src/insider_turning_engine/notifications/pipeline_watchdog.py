"""Independent daily-run diagnostics and durable failure notices, not signal alerts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from insider_turning_engine.domain.session_calendar import latest_closed_session
from insider_turning_engine.export.restore import PUBLIC_DATA
from insider_turning_engine.ingestion.sec.historical import _write_json

from .channels import TelegramHTTPChannel
from .publication_recovery import gh_json, source_is_trusted
from .state_store import persist, restore
from .workflow_status import send_notice, status_report


def public_status() -> tuple[dict[str, Any], dict[str, Any]]:
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        def fetch(name: str) -> bytes:
            response = client.get(PUBLIC_DATA + name, headers={"Cache-Control": "no-cache"})
            response.raise_for_status()
            if len(response.content) > 10_000_000:
                raise ValueError("public status exceeds limit")
            return response.content

        manifest_bytes = fetch("manifest.json")
        manifest = json.loads(manifest_bytes)
        raw = fetch("settings-status.json")
        entries = [row for row in manifest["files"] if row["path"] == "settings-status.json"]
        if (len(entries) != 1 or len(raw) != entries[0]["size"]
                or hashlib.sha256(raw).hexdigest() != entries[0]["sha256"]):
            raise ValueError("public settings integrity mismatch")
        manifest["_content_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        return manifest, json.loads(raw)


def public_index_hash() -> str:
    response = httpx.get(PUBLIC_DATA.removesuffix("data/") + "index.html", timeout=30,
                         follow_redirects=False, headers={"Cache-Control": "no-cache"})
    response.raise_for_status()
    if len(response.content) > 10_000_000:
        raise ValueError("public index exceeds limit")
    return hashlib.sha256(response.content).hexdigest()


def job_results(jobs: list[dict[str, Any]]) -> dict[str, str]:
    results = {}
    for name in ("build", "deploy", "digest"):
        rows = [job for job in jobs if job.get("name") == name]
        result = rows[-1].get("conclusion") if rows else "skipped"
        results[name] = result if result in {"success", "failure", "skipped", "cancelled"} \
            else "failure"
    return results


def digest_sent(outbox: Path, day: str) -> bool:
    if not outbox.exists():
        return False
    with closing(sqlite3.connect(outbox.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='factual_digest_claims'").fetchone():
            return False
        row = db.execute("SELECT status FROM factual_digest_claims "
                         "WHERE channel='telegram' AND sec_day=?", (day,)).fetchone()
        return bool(row and row[0] == "SENT")


def expected_digest_day(now: datetime) -> str:
    # Judge the morning cycle, not a later/early market close that same day.
    if now.tzinfo is None:
        raise ValueError("watchdog clock must be timezone-aware")
    point = now.astimezone(UTC)
    anchor = point.replace(hour=7, minute=15, second=0, microsecond=0)
    if point < anchor:
        anchor -= timedelta(days=1)
    return latest_closed_session(anchor).isoformat()


def inspect_source(repository: str, source_run: str | None) -> dict[str, Any]:
    base = f"repos/{repository}"
    if source_run:
        if not re.fullmatch(r"[0-9]{1,20}", source_run):
            raise ValueError("invalid source run")
        run = gh_json(f"{base}/actions/runs/{source_run}")
    else:
        runs = gh_json(f"{base}/actions/workflows/pages.yml/runs?per_page=30")["workflow_runs"]
        trusted = [row for row in runs if source_is_trusted(row, repository)]
        if any(row.get("status") != "completed" for row in trusted):
            return {"status": "WAIT", "recover": False, "source_run": ""}
        if not trusted:
            return {"status": "MISSING_RUN", "recover": False, "source_run": ""}
        run = trusted[0]
    if not source_is_trusted(run, repository):
        return {"status": "UNTRUSTED_SOURCE", "recover": False, "source_run": ""}
    if run.get("status") != "completed":
        return {"status": "WAIT", "recover": False, "source_run": str(run["id"])}
    if run.get("conclusion") == "cancelled":
        return {"status": "IGNORED", "recover": False, "source_run": str(run["id"])}
    jobs = gh_json(f"{base}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
    results = job_results(jobs)
    recover = (run.get("conclusion") == "failure" and run.get("run_attempt") == 1
               and results["build"] == "success" and results["deploy"] != "success")
    return {"status": "FAILED" if run.get("conclusion") != "success" else "SUCCESS",
            "recover": recover, "source_run": str(run["id"]), "results": results,
            "digest_expected": run.get("event") == "schedule" or results["digest"] == "failure"}


def report_health(plan: dict[str, Any], *, repository: str, recovery_deployed: bool,
                  recovery_digest: str, digest_expected: bool, now: datetime,
                  outbox: Path) -> dict[str, object]:
    source = plan.get("source_run") or os.environ["GITHUB_RUN_ID"]
    results = plan.get("results", {"build": "failure", "deploy": "skipped", "digest": "skipped"})
    if plan["status"] in {"WAIT", "IGNORED", "UNTRUSTED_SOURCE"}:
        return {"status": "WAIT", "runId": source, "text": ""}
    if recovery_deployed:
        results = {"build": "success", "deploy": "success", "digest": recovery_digest}
    report = status_report(repository, source, results, digest_expected=digest_expected)
    # Check durable SENT even after a successful job: ALREADY_CLAIMED is not
    # proof of delivery. Only the scheduled fallback imposes the morning date.
    if report["status"] == "SUCCESS" and (
            digest_expected or not plan.get("explicit_source")):
        expected_day = expected_digest_day(now) if not plan.get("explicit_source") else ""
        try:
            _manifest, settings = public_status()
            observed = settings.get("digest", {}).get("secDay")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            observed = "UNVERIFIED"
        try:
            day = date.fromisoformat(str(observed))
            current = (not expected_day or date.fromisoformat(expected_day) <= day) \
                and day <= now.astimezone(UTC).date()
        except ValueError:
            current = False
        # SEC may have a complete filing day while NYSE is closed (e.g. Good Friday).
        if not current or not digest_sent(outbox, str(observed)):
            report.update(status="FAILED", text=(
                "Insider Turning Engine — operational warning\n"
                f"Expected SEC day: {expected_day or 'original published day'}. "
                f"Public SEC day: {observed}.\n"
                "Current public snapshot or durable Telegram delivery is missing/unverified.\n"
                "No automatic historical digest will be sent.\n"
                f"Details: https://github.com/{repository}/actions/runs/{source}"))
    if plan["status"] == "PROBE_FAILED":
        report["text"] = (
            "Insider Turning Engine — operational warning\n"
            "Independent publication check could not verify the workflow status.\n"
            "This is not proof that the daily data or delivery failed. No recovery was initiated.\n"
            f"Details: https://github.com/{repository}/actions/runs/{source}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["inspect", "report"])
    parser.add_argument("--source-run")
    parser.add_argument("--plan", type=Path, default=Path("work/watchdog-plan.json"))
    parser.add_argument("--output", type=Path, default=Path("work/watchdog-status.json"))
    args = parser.parse_args()
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise ValueError("watchdog requires an original trusted main run")
    repository = os.environ["GITHUB_REPOSITORY"]
    if args.operation == "inspect":
        plan = inspect_source(repository, args.source_run)
        plan["explicit_source"] = bool(args.source_run)
        _write_json(args.plan, plan)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
            stream.write(f"recover={str(plan['recover']).lower()}\n")
            stream.write(f"source_run={plan['source_run']}\n")
        print(json.dumps(plan, sort_keys=True))
        return
    # A missing probe must also yield an independent warning, not fail before reporting.
    plan = json.loads(args.plan.read_text("utf-8")) if args.plan.exists() else {
        "status": "PROBE_FAILED", "source_run": args.source_run or "", "recover": False,
        "explicit_source": True,
    }
    store, outbox = Path("work/watchdog-state"), Path("work/watchdog-alerts.sqlite")
    restore(Path.cwd(), store, outbox)
    report = report_health(plan, repository=repository,
        recovery_deployed=os.environ.get("RECOVERY_DEPLOYED") == "true",
        recovery_digest=os.environ.get("RECOVERY_DIGEST", "skipped"),
        digest_expected=(os.environ.get("RECOVERY_DIGEST_EXPECTED") == "true"
                         or bool(plan.get("digest_expected"))),
        now=datetime.now(UTC), outbox=outbox)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    notice = "NOT_NEEDED"
    if report["status"] == "FAILED":
        notice = "NOT_CONFIGURED"
        if token and chat:
            channel = TelegramHTTPChannel(token, chat,
                lambda url, payload: httpx.post(url, data=payload, timeout=20))
            notice = send_notice(report, outbox=outbox, save=lambda: persist(store, outbox),
                                 send=channel.send_text)
    report["notificationStatus"] = notice
    _write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))
    if report["status"] == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
