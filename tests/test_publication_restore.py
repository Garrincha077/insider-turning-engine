import json
from pathlib import Path

import httpx
import pytest

from insider_turning_engine.export.dashboard import DashboardExportError
from insider_turning_engine.export.restore import PUBLIC_DATA, restore_publication


def test_restore_preserves_published_dates_and_run_id(tmp_path: Path) -> None:
    source = Path("app/public/data")

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url).removeprefix(PUBLIC_DATA)
        return httpx.Response(200, content=(source / path).read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        restore_publication(tmp_path / "output", client)
    previous = json.loads((source / "manifest.json").read_text())
    restored = json.loads((tmp_path / "output/manifest.json").read_text())
    assert {key: restored[key] for key in ("runId", "asOf", "generatedAt")} == {
        key: previous[key] for key in ("runId", "asOf", "generatedAt")
    }


def test_corrupt_remote_does_not_replace_existing_output(tmp_path: Path) -> None:
    (tmp_path / "sentinel").write_text("previous publication")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("manifest.json"):
            return httpx.Response(200, content=Path("app/public/data/manifest.json").read_bytes())
        return httpx.Response(200, content=b"invalid")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DashboardExportError, match="integrity mismatch"):
            restore_publication(tmp_path, client)
    assert (tmp_path / "sentinel").read_text() == "previous publication"


@pytest.mark.parametrize("path", ["../escape.json", "/absolute.json", "manifest.json"])
def test_restore_rejects_unsafe_remote_paths(tmp_path: Path, path: str) -> None:
    manifest = {"files": [{"path": path, "size": 10, "sha256": "0" * 64}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json=manifest
    ))) as client:
        with pytest.raises(DashboardExportError, match="unsafe"):
            restore_publication(tmp_path, client)
