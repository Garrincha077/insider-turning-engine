"""Static contracts for the production automation boundary.

These checks intentionally do not execute GitHub Actions.  They keep the
schedule, least-privilege permissions, fail-closed publication gate, and
state-branch allow-list reviewable in normal CI.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"
PAGES = ROOT / ".github" / "workflows" / "pages.yml"


def _workflow(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text)
    assert isinstance(value, dict)
    # PyYAML 5/6 resolves the YAML 1.1 spelling ``on`` as True.
    trigger = value.get("on", value.get(True))
    assert isinstance(trigger, dict)
    return value, text


def test_daily_schedule_dispatch_lock_and_runtime_contract() -> None:
    workflow, text = _workflow(DAILY)
    trigger = workflow["on"] if "on" in workflow else workflow[True]
    assert isinstance(trigger, dict)
    schedules = [item["cron"] for item in trigger["schedule"]]
    assert "30 2 * * 2-6" in schedules
    assert "0 3 1 1,4,7,10 *" in schedules
    assert "workflow_dispatch" in trigger
    assert workflow["concurrency"] == {
        "group": "daily-research-pipeline",
        "cancel-in-progress": False,
    }
    assert "python-version: ${{ env.PYTHON_VERSION }}" in text
    assert "uv sync --all-groups --frozen" in text
    assert "SEC_USER_AGENT: ${{ vars.SEC_USER_AGENT }}" in text
    assert "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}" in text
    assert "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}" in text


def test_daily_has_fixture_mode_quality_gate_state_lease_and_release() -> None:
    _, text = _workflow(DAILY)
    for required in (
        "fixture-dry-run:",
        "daily:",
        "quarterly-sec-backfill:",
        "publish-pages:",
        "release:",
        "insider-turning daily --fixture-only",
        "steps.quality.outputs.alerts_allowed == 'true'",
        "steps.quality.outputs.publishable == 'true'",
        "--force-with-lease",
        "git ls-remote origin refs/heads/state",
        "git -C state-next ls-files",
        "actions/upload-artifact@v4",
        "retention-days:",
        "PAGES_BASE_PATH",
        "group: pages",
        "MANIFEST_ID_MISMATCH",
        "QUALITY_STATUS_MISMATCH",
    ):
        assert required in text
    assert "state branch contains forbidden paths" in text
    assert "raw filings" in text
    assert "--execute" in text


def test_daily_uses_live_sec_incremental_cursor_and_fail_closed_universe() -> None:
    workflow, text = _workflow(DAILY)
    daily = workflow["jobs"]["daily"]
    assert daily["timeout-minutes"] == 30
    restore = text.index("Restore SEC cursor from orphan state branch")
    incremental = text.index("SEC incremental stage")
    assert restore < incremental
    assert '--cik-file "$cik_file"' in text
    assert "--cursor-file run/state/sec.cursor" in text
    assert "--outbox run/state/alerts.sqlite" in text
    assert "update-sec" in text and "--execute" in text
    assert "config/universe-ciks.txt" in text
    assert "SEC CIK universe is unavailable; marking run degraded" in text
    assert "never an invented universe" in text
    assert r"sec\.cursor" in text
    assert "state branch contains forbidden paths" in text
    assert "alerts.sqlite" in text
    assert "10 MiB operational-state limit" in text
    assert "publishable_quality" in text


def test_quarterly_release_contains_only_normalized_staging() -> None:
    workflow, text = _workflow(DAILY)
    quarterly = workflow["jobs"]["quarterly-sec-backfill"]
    assert quarterly["timeout-minutes"] == 30
    assert quarterly["permissions"] == {"contents": "write"}
    release = text.split("Publish idempotent versioned SEC Release artifact", 1)[1].split(
        "\n  daily:", 1
    )[0]
    assert "Validate normalized SEC Parquet staging" in text
    assert "find \"$partition\" -maxdepth 1 -type f -name '*.parquet'" in text
    assert 'tar -czf "$archive" -C data/staging/sec' in release
    assert 'gh release upload "$release_tag" "$archive" --clobber' in release
    assert 'gh release create "$release_tag" "$archive"' in release
    assert "data/cache/sec" not in release
    assert ".zip" not in release


def test_fixture_job_is_offline_and_state_allowlist_includes_only_small_state() -> None:
    workflow, text = _workflow(DAILY)
    fixture = workflow["jobs"]["fixture-dry-run"]
    assert fixture["permissions"] == {"contents": "read"}
    fixture_text = text.split("  quarterly-sec-backfill:", 1)[0]
    assert "--fixture-only" in fixture_text
    assert "--execute" not in fixture_text
    assert "watermarks\\.json|sec\\.cursor|prior-scores\\.json" in text
    assert "grep -Ev '^(watermarks\\.json|sec\\.cursor|prior-scores\\.json" in text
    assert "run/public/data" in text


def test_pages_validates_manifest_and_hashes_before_upload() -> None:
    _, text = _workflow(PAGES)
    assert "manifest.json" in text
    assert "hash mismatch" in text
    assert "semantic id mismatch" in text
    assert "artifact content hash mismatch" in text
    assert "frozen contracts" in text
    assert text.index("Validate atomic dashboard snapshot") < text.index(
        "actions/upload-pages-artifact@v3"
    )
    assert "PAGES_BASE_PATH" in text
