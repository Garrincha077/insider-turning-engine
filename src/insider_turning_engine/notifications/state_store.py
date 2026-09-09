"""Restore/persist only the alert ledger, preserving unrelated operational state."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

ALLOWED = {
    "watermarks.json", "sec.cursor", "prior-scores.json", "prior-states.json",
    "alert-outbox.jsonl", "alert-history.jsonl", "alerts.sqlite",
}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        # Neither command arguments nor stderr may expose an authentication header.
        raise RuntimeError("state Git operation failed; no state was overwritten")
    return result.stdout.strip()


def _validate_ledger(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("state ledger must be a regular file below 10 MiB")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as database:
        if database.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("state ledger is corrupt")


def restore(repo: Path, store: Path, outbox: Path) -> None:
    if store.exists() or outbox.exists():
        raise ValueError("restore requires fresh working paths")
    remote = _git(repo, "remote", "get-url", "origin")
    reference = _git(repo, "ls-remote", "--heads", "origin", "refs/heads/state")
    store.mkdir(parents=True)
    _git(store, "init")
    _git(store, "remote", "add", "origin", remote)
    # actions/checkout stores a scoped header in local config. Keep it only in .git.
    header = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "http.https://github.com/.extraheader"],
        capture_output=True, text=True, check=False,
    )
    if header.returncode == 0:
        _git(store, "config", "http.https://github.com/.extraheader", header.stdout.strip())
    if reference:
        _git(store, "fetch", "--depth=1", "origin", "refs/heads/state")
        _git(store, "checkout", "--detach", "FETCH_HEAD")
        for name in _git(store, "ls-files").splitlines():
            if name not in ALLOWED or (store / name).is_symlink():
                raise ValueError("state contains a forbidden path")
        if (store / "alerts.sqlite").exists():
            _validate_ledger(store / "alerts.sqlite")
            outbox.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(store / "alerts.sqlite", outbox)


def persist(store: Path, outbox: Path) -> None:
    _validate_ledger(outbox)
    shutil.copyfile(outbox, store / "alerts.sqlite")
    _git(store, "add", "--", "alerts.sqlite")
    if not _git(store, "diff", "--cached", "--name-only"):
        return
    _git(store, "config", "user.name", "github-actions[bot]")
    _git(store, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    _git(store, "commit", "-m", "Persist delivery evidence")
    # A concurrent update is rejected, never force-pushed over another writer.
    _git(store, "push", "origin", "HEAD:refs/heads/state")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["restore", "persist"])
    parser.add_argument("--store", type=Path, default=Path("work/notification-state"))
    parser.add_argument("--outbox", type=Path, default=Path("work/alerts.sqlite"))
    args = parser.parse_args()
    if args.operation == "restore":
        restore(Path.cwd(), args.store, args.outbox)
    else:
        persist(args.store, args.outbox)


if __name__ == "__main__":
    main()
