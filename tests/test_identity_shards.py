import copy
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_identity_observations import NOW, _observation
from test_sec_checkpoints import FakeReleases

from insider_turning_engine.ingestion.sec import identity_store as module
from insider_turning_engine.ingestion.sec.identity_store import (
    SHARDED_PREFIX,
    ReleaseIdentityStore,
    decode_identity_bundle,
    encode_identity_bundle,
    encode_identity_history,
)


def observations(count=8):
    return [{**_observation(), "knowledge_at": (NOW + timedelta(days=i)).isoformat()}
            for i in range(count)]


class ShardReleases(FakeReleases):
    def __init__(self):
        super().__init__()
        self.bundles = {}
        self.fail_upload = False

    def _gh(self, *args):
        if args[:2] == ("release", "create"):
            result = super()._gh(*args)
            if "--draft" in args:
                tag, path = args[2], Path(args[3])
                self.bundles[tag] = {path.name: path.read_bytes()}
                self.releases[-1]["draft"] = True
            return result
        if args[:2] == ("release", "upload"):
            self.commands.append(args)
            if self.fail_upload:
                raise RuntimeError("fixture interrupted upload")
            tag = args[2]
            release = next(row for row in self.releases if row["tag_name"] == tag)
            for path in map(Path, args[3:args.index("--repo")]):
                assert path.name not in self.bundles[tag]
                self.bundles[tag][path.name] = path.read_bytes()
                release["assets"].append({"name": path.name, "size": path.stat().st_size,
                                           "state": "uploaded"})
            return ""
        if args[:2] == ("release", "edit"):
            self.commands.append(args)
            assert "--draft=false" in args
            next(row for row in self.releases if row["tag_name"] == args[2])["draft"] = False
            return ""
        if args[:2] == ("release", "download") and args[2] in self.bundles:
            self.commands.append(args)
            root = Path(args[args.index("--dir") + 1])
            for name, data in self.bundles[args[2]].items():
                (root / name).write_bytes(data)
            return ""
        return super()._gh(*args)


def _manifest(tag, files):
    name = "identity-manifest-" + tag.removeprefix(SHARDED_PREFIX) + ".json"
    return name, json.loads(files[name])


def _rewrite_manifest(tag, files, change):
    files = copy.deepcopy(files)
    name, value = _manifest(tag, files)
    change(value)
    del files[name]
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    files[f"identity-manifest-{digest}.json"] = raw
    return SHARDED_PREFIX + digest, files


def test_history_larger_than_single_archive_is_losslessly_sharded(monkeypatch):
    rows = observations()
    one_size = len(json.dumps({"schemaVersion": "1.0.0", "observations": rows[:1]},
                              sort_keys=True, separators=(",", ":")).encode())
    monkeypatch.setattr(module, "MAX_BYTES", one_size + 20)
    monkeypatch.setattr(module, "CHUNK_TARGET_BYTES", one_size)
    with pytest.raises(ValueError, match="size limit"):
        encode_identity_history(rows)
    tag, files = encode_identity_bundle(rows)
    assert tag.startswith(SHARDED_PREFIX)
    assert decode_identity_bundle(tag, files) == rows
    assert encode_identity_bundle(list(reversed(rows)) + rows) == (tag, files)
    _, manifest = _manifest(tag, files)
    assert len(manifest["shards"]) == len(rows)
    assert all(part["expandedBytes"] <= module.MAX_BYTES for part in manifest["shards"])


def test_legacy_read_transition_draft_resume_and_complete_publication(monkeypatch):
    store = ReleaseIdentityStore("owner/repo", target="a" * 40)
    remote = ShardReleases()
    store.transport = remote
    old = observations(1)
    assert store.persist(old)["tag"].startswith(module.PREFIX)
    monkeypatch.setattr(module, "CHUNK_TARGET_BYTES", 1200)
    rows = observations()
    remote.fail_upload = True
    with pytest.raises(RuntimeError, match="interrupted"):
        store.persist(rows)
    assert remote.releases[-1]["draft"]
    assert store.latest() == old  # No partial manifest becomes current.
    remote.fail_upload = False
    receipt = store.persist(rows)
    assert receipt["tag"].startswith(SHARDED_PREFIX)
    assert not remote.releases[-1]["draft"]
    assert store.latest() == rows
    assert store.persist(list(reversed(rows))) == receipt
    assert len(remote.releases) == 2
    assert all("--clobber" not in args and "--force" not in args for args in remote.commands)
    with pytest.raises(ValueError, match="discard"):
        store.persist(rows[1:])
    tag = receipt["tag"]
    name = next(name for name in remote.bundles[tag] if name.endswith(".gz"))
    remote.bundles[tag][name] = b"x" * len(remote.bundles[tag][name])
    with pytest.raises(ValueError, match="checksum"):
        store.latest()  # Never hide a corrupt current bundle by restoring v1.


@pytest.mark.parametrize("fault", ["missing", "extra", "corrupt", "wrong_issuer_bucket",
                                  "row_count", "false_expanded_size", "unsafe_path"])
def test_shard_inventory_and_hashes_fail_closed(monkeypatch, fault):
    monkeypatch.setattr(module, "CHUNK_TARGET_BYTES", 1200)
    tag, files = encode_identity_bundle(observations())
    name = next(name for name in files if name.endswith(".gz"))
    if fault == "missing":
        del files[name]
    elif fault == "extra":
        files["token.txt"] = b"not allowed"
    elif fault == "corrupt":
        files[name] += b"x"
    else:
        def change(manifest):
            part = manifest["shards"][0]
            if fault == "wrong_issuer_bucket":
                part["bucket"] = (part["bucket"] + 1) % 16
            elif fault == "row_count":
                part["observationCount"] += 1
            elif fault == "false_expanded_size":
                part["expandedBytes"] = 1
            else:
                part["file"] = "../outside.json.gz"
        tag, files = _rewrite_manifest(tag, files, change)
    with pytest.raises(ValueError):
        decode_identity_bundle(tag, files)


def test_manifest_and_total_expansion_budgets_are_enforced(monkeypatch):
    monkeypatch.setattr(module, "CHUNK_TARGET_BYTES", 1200)
    tag, files = encode_identity_bundle(observations())
    monkeypatch.setattr(module, "MAX_BUNDLE_BYTES", 100)
    with pytest.raises(ValueError, match="size limit"):
        decode_identity_bundle(tag, files)
    with pytest.raises(ValueError, match="bounded"):
        encode_identity_bundle(observations())


def test_sharded_roundtrip_retains_point_in_time_tombstones(monkeypatch):
    from insider_turning_engine.pipeline.live_inputs import _identity_candidates

    monkeypatch.setattr(module, "CHUNK_TARGET_BYTES", 1200)
    rows = observations()
    rows[-1].update(identity_status="UNRESOLVED", ticker=None)
    tag, files = encode_identity_bundle(rows)
    decoded = decode_identity_bundle(tag, files)
    before = _identity_candidates(decoded, as_of=NOW,
                                  common_stock_titles={rows[0]["cik"]: "Common Stock"})
    assert before[rows[0]["cik"]]["ticker"] == "ACME"
    assert _identity_candidates(decoded, as_of=NOW + timedelta(days=7),
                                common_stock_titles={rows[0]["cik"]: "Common Stock"}) == {}


def test_partitioned_issuers_keep_every_issuer_and_original_observation():
    row = _observation()
    other = copy.deepcopy(row)
    other["cik"] = "0000000008"
    other["provenance"]["metadata_url"] = "https://data.sec.gov/submissions/CIK0000000008.json"
    tag, files = encode_identity_bundle([other, row])
    assert decode_identity_bundle(tag, files) == [row, other]
    _, manifest = _manifest(tag, files)
    assert {part["bucket"] for part in manifest["shards"]} == {7, 8}
