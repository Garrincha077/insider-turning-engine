import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from test_dashboard_export import _data
from test_research_snapshot import POINT, _build, _record

from insider_turning_engine.export.dashboard import export_dashboard
from insider_turning_engine.export.research_policy import validate_publication
from insider_turning_engine.export.restore import PUBLIC_DATA, restore_publication
from insider_turning_engine.pipeline.research_archive import ResearchArchive, decode_snapshot


def _publication(output):
    data = _data()
    data["researchSnapshot"] = _build([_record()]).model_dump(by_alias=True, mode="json")
    # Factual publication explicitly does not require market or model validation.
    data["quality"].update(benchmarkFresh=False, methodologyComplete=False)
    export_dashboard(data, output, run_id="run_research_fixture_001", as_of=POINT)


def test_factual_policy_and_ui_restore_preserve_v2_without_predictive_permission(tmp_path):
    source = tmp_path / "source"
    _publication(source)
    assert validate_publication(source).startswith("DAILY_RESEARCH")

    def fetch(request):
        path = str(request.url).split("?", 1)[0].removeprefix(PUBLIC_DATA)
        return httpx.Response(200, content=(source / path).read_bytes())

    output = tmp_path / "restored"
    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        restore_publication(output, client)
    assert (output / "research-v2.json").read_bytes() == (source / "research-v2.json").read_bytes()
    assert validate_publication(output).startswith("DAILY_RESEARCH")
    (output / "research-v2.json").write_text("{}")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        validate_publication(output)


def test_research_archive_verified_immutable_replay(tmp_path, monkeypatch):
    output = tmp_path / "public"
    _publication(output)
    store = ResearchArchive("owner/repo", target="a" * 40)
    releases = []
    assets = {}
    creates = []

    def gh(*args):
        if args[0] == "api" and "releases?" in args[1]:
            return json.dumps([releases])
        if args[:2] == ("release", "create"):
            tag, path = args[2], Path(args[3])
            creates.append(tag)
            assets[path.name] = path.read_bytes()
            releases.append({"tag_name": tag, "draft": False, "prerelease": True,
                "assets": [{"name": path.name, "state": "uploaded", "size": path.stat().st_size}]})
            return ""
        if args[0] == "api":
            return json.dumps(releases[0])
        if args[:2] == ("release", "download"):
            name = args[args.index("--pattern") + 1]
            (Path(args[args.index("--dir") + 1]) / name).write_bytes(assets[name])
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(store, "_gh", gh)
    first = store.publish(output)
    # A fresh process sees the existing immutable asset, not a clobber upload.
    store._inventory = None
    assert store.publish(output) == first
    assert first["storageStatus"] == "VERIFIED" and len(creates) == 1
    name = next(iter(assets))
    assets[name] = bytes(len(assets[name]))
    with pytest.raises((ValueError, OSError)):
        store.publish(output)


def test_archive_rejects_hash_mismatch_and_decompression_bomb(monkeypatch):
    from insider_turning_engine.pipeline import research_archive

    raw = _build([_record()]).model_dump_json().encode()
    with pytest.raises(ValueError, match="checksum"):
        decode_snapshot(gzip.compress(raw), "0" * 64)
    monkeypatch.setattr(research_archive, "MAX_SNAPSHOT_BYTES", 100)
    bomb = b"x" * 1000
    with pytest.raises(ValueError, match="size"):
        decode_snapshot(gzip.compress(bomb), hashlib.sha256(bomb).hexdigest())
