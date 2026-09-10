"""Authenticated, non-forcing persistence of small allow-listed operational state."""

from __future__ import annotations

import argparse
import json
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


def _restore_store(repo: Path, store: Path) -> str:
    if store.exists():
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
        _validate_state_files(store, _git(store, "ls-files").splitlines())
        return _git(store, "rev-parse", "HEAD")
    return ""


def restore(repo: Path, store: Path, outbox: Path) -> None:
    if outbox.exists():
        raise ValueError("restore requires fresh working paths")
    _restore_store(repo, store)
    if (store / "alerts.sqlite").exists():
        outbox.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store / "alerts.sqlite", outbox)


def _validate_state_files(root: Path, names: list[str]) -> None:
    for name in names:
        path = root / name
        if name not in ALLOWED or path.is_symlink() or not path.is_file():
            raise ValueError("state contains a forbidden path")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("state file exceeds the 10 MiB operational-state limit")
        if name == "alerts.sqlite":
            _validate_ledger(path)
        elif name.endswith(".jsonl"):
            for line in path.read_text("utf-8").splitlines():
                if line.strip():
                    json.loads(line)
        else:
            json.loads(path.read_text("utf-8"))


def persist_operational(
    repo: Path, store: Path, incoming: Path, *, expected_head: str,
) -> None:
    """Merge validated files without deletion; refuse a changed remote baseline.

    Cursor advancement evidence is the caller's responsibility. This layer only
    validates serialization, preserves other writers' history and transports state.
    Both an early head check and the non-forcing push protect against races.
    """
    if incoming.is_symlink() or not incoming.is_dir():
        raise ValueError("incoming state must be a regular directory")
    names = sorted(path.name for path in incoming.iterdir())
    _validate_state_files(incoming, names)
    actual_head = _restore_store(repo, store)
    if actual_head != expected_head:
        raise RuntimeError("state branch changed during run; no state was overwritten")
    for name in names:
        shutil.copyfile(incoming / name, store / name)
    if names:
        _git(store, "add", "--", *names)
    _commit_and_push(store, "Persist operational state")


def persist(store: Path, outbox: Path) -> None:
    _validate_ledger(outbox)
    shutil.copyfile(outbox, store / "alerts.sqlite")
    _git(store, "add", "--", "alerts.sqlite")
    _commit_and_push(store, "Persist delivery evidence")


def _commit_and_push(store: Path, message: str) -> None:
    if not _git(store, "diff", "--cached", "--name-only"):
        return
    _git(store, "config", "user.name", "github-actions[bot]")
    _git(store, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    _git(store, "commit", "-m", message)
    # A concurrent update is rejected, never force-pushed over another writer.
    _git(store, "push", "origin", "HEAD:refs/heads/state")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["restore", "persist", "sync"])
    parser.add_argument("--store", type=Path, default=Path("work/notification-state"))
    parser.add_argument("--outbox", type=Path, default=Path("work/alerts.sqlite"))
    parser.add_argument("--incoming", type=Path)
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    if args.operation == "restore":
        restore(Path.cwd(), args.store, args.outbox)
    elif args.operation == "persist":
        persist(args.store, args.outbox)
    else:
        if args.incoming is None or args.expected_head is None:
            parser.error("sync requires --incoming and --expected-head (empty for initial state)")
        persist_operational(Path.cwd(), args.store, args.incoming, expected_head=args.expected_head)


if __name__ == "__main__":
    main()
