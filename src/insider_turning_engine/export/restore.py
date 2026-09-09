"""Preserve the last published data when deploying UI-only changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from .dashboard import DashboardExportError, export_dashboard, validate_dashboard_directory

PUBLIC_DATA = "https://garrincha077.github.io/insider-turning-engine/data/"


def restore_publication(output: Path, client: httpx.Client) -> None:
    """Download to scratch, validate fully, then atomically replace the output."""

    def download(path: str, limit: int) -> bytes:
        with client.stream("GET", PUBLIC_DATA + quote(path, safe="/")) as response:
            response.raise_for_status()
            payload = bytearray()
            for block in response.iter_bytes():
                payload.extend(block)
                if len(payload) > limit:
                    raise DashboardExportError("published file exceeds size limit")
            return bytes(payload)

    raw = download("manifest.json", 10_000_000)
    manifest = json.loads(raw)
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 20_000:
        raise DashboardExportError("invalid published file inventory")
    names: set[str] = set()
    total_size = 0
    for entry in files:
        path, size = entry.get("path"), entry.get("size")
        if (
            not isinstance(path, str) or not path or "\\" in path or ":" in path
            or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
            or path == "manifest.json" or path in names
            or not isinstance(size, int) or not 0 < size <= 10_000_000
        ):
            raise DashboardExportError("unsafe published file inventory")
        names.add(path)
        total_size += size
    if total_size > 200_000_000:
        raise DashboardExportError("published snapshot exceeds size limit")
    with tempfile.TemporaryDirectory(prefix="ite-published-") as temporary:
        root = Path(temporary)
        (root / "manifest.json").write_bytes(raw)

        def fetch(index: int) -> None:
            entry = files[index]
            payload = download(entry["path"], entry["size"])
            if (len(payload) != entry["size"]
                    or hashlib.sha256(payload).hexdigest() != entry["sha256"]):
                raise DashboardExportError("published file integrity mismatch")
            target = root / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(fetch, range(len(files))))
        checked = validate_dashboard_directory(root)
        dashboard = json.loads((root / "dashboard.json").read_text("utf-8"))
        dashboard["quality"] = checked["quality"]
        dashboard["watermarks"] = checked["watermarks"]
        dashboard["signals"] = [
            json.loads((root / item["uri"]).read_text("utf-8"))
            for item in checked["signals"]
        ]
        if (root / "settings-status.json").exists():
            dashboard["settingsStatus"] = json.loads(
                (root / "settings-status.json").read_text("utf-8")
            )
        export_dashboard(
            dashboard, output, run_id=checked["runId"], as_of=checked["asOf"],
            generated_at=checked["generatedAt"], chunk_by_ticker=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        restore_publication(args.output, client)


if __name__ == "__main__":
    main()
