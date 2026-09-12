"""Preview by default; execute only against a verified publication and fresh state."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from insider_turning_engine.domain.research import ResearchSnapshot
from insider_turning_engine.export.dashboard import validate_dashboard_directory
from insider_turning_engine.ingestion.sec.historical import _write_json

from .channels import TelegramHTTPChannel
from .digest import deliver_digest, delivery_reasons, load_digest_policy, preview_digest
from .state_store import persist, restore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("config/digest.v1.json"))
    parser.add_argument("--output", type=Path, default=Path("work/digest-status.json"))
    parser.add_argument("--store", type=Path, default=Path("work/digest-state"))
    parser.add_argument("--outbox", type=Path, default=Path("work/digest-alerts.sqlite"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    # Hash/schema/run validation is global. An unlisted research file is never usable.
    manifest = validate_dashboard_directory(args.directory, require_settings=True)
    if (not any(row["path"] == "research-v2.json" for row in manifest["files"])
            or manifest["quality"]["canonicalValid"] is not True):
        raise ValueError("canonical v2 publication required")
    snapshot = ResearchSnapshot.model_validate_json(
        (args.directory / "research-v2.json").read_bytes())
    draft = preview_digest(snapshot)
    policy = load_digest_policy(args.policy)
    report = draft.model_dump(mode="json")
    report["policyEnabled"] = policy.enabled
    report["status"] = "PREVIEW" if not draft.reasons else "BLOCKED"
    if args.execute:
        now = datetime.now(UTC)
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        production = (os.environ.get("GITHUB_ACTIONS") == "true"
                      and os.environ.get("GITHUB_REF") == "refs/heads/main"
                      and os.environ.get("ITE_ENVIRONMENT") == "production")
        reasons = delivery_reasons(draft, snapshot, policy, now=now,
                                   production=production, configured=bool(token and chat))
        if reasons:
            report.update(status="BLOCKED", reasons=list(reasons))
        else:
            # Fresh restore AFTER prior-score/state writer, never reuse its stale checkout.
            restore(Path.cwd(), args.store, args.outbox)
            channel = TelegramHTTPChannel(token, chat,
                lambda url, payload: httpx.post(url, data=payload, timeout=20.0))
            try:
                report["status"] = deliver_digest(draft, outbox=args.outbox, now=now,
                    persist=lambda: persist(args.store, args.outbox), send=channel.send_text)
            except Exception:
                # Do not expose HTTP URLs/secrets or automatically retry uncertain operations.
                report.update(status="BLOCKED", reasons=["DIGEST_STATE_PERSISTENCE_FAILED"])
                _write_json(args.output, report)
                raise RuntimeError("digest state persistence failed; inspect claim") from None
    _write_json(args.output, report)
    # Public SEC facts only; provider configuration is never serialized.
    print(json.dumps(report, sort_keys=True))
    if report["status"] in {"FAILED", "UNCERTAIN"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
