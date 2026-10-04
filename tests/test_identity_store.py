import gzip
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_identity_observations import (
    NOW,
    _common_filing,
    _multi_listing_observation,
    _observation,
)
from test_sec_checkpoints import FakeReleases

from insider_turning_engine.ingestion.sec import identity_store
from insider_turning_engine.ingestion.sec.identity_store import (
    ReleaseIdentityStore,
    decode_identity_history,
    encode_identity_history,
)


def test_identity_release_roundtrip_idempotency_append_and_no_loss():
    store = ReleaseIdentityStore("owner/repo", target="a" * 40)
    remote = FakeReleases()
    store.transport = remote
    row = _observation()
    assert store.latest() is None
    receipt = store.persist([row])
    assert receipt["storageStatus"] == "VERIFIED"
    assert store.latest() == [row]
    assert store.persist([row]) == receipt
    assert len(remote.files) == 1
    new = {**row, "knowledge_at": (NOW + timedelta(days=1)).isoformat()}
    with pytest.raises(ValueError, match="discard"):
        store.persist([new])
    store.persist([row, new])
    assert len(remote.files) == 2
    assert store.latest() == [row, new]
    assert all("--clobber" not in args and "--force" not in args for args in remote.commands)
    assert any("--latest=false" in args for args in remote.commands)
    newest = remote.releases[-1]
    remote.files[newest["tag_name"]] = b"x" * newest["assets"][0]["size"]
    with pytest.raises(ValueError, match="checksum"):
        store.latest()  # Never silently fall back to the older successful release.


def test_identity_archive_excludes_raw_fields_and_checks_content(monkeypatch):
    row = _observation()
    name, content = encode_identity_history([row])
    assert decode_identity_history(name, content) == [row]
    assert content[9] == 255  # platform-independent gzip header (Windows/Linux replay)
    with pytest.raises(ValueError, match="unexpected fields"):
        encode_identity_history([{**row, "raw_xml": "not public", "token": "forbidden"}])
    with pytest.raises(ValueError, match="source URLs"):
        encode_identity_history([{**row, "provenance": {**row["provenance"],
                                 "metadata_url": "https://evil.example/token"}}])
    with pytest.raises(ValueError, match="checksum"):
        decode_identity_history(name, content + b"x")
    bomb = gzip.compress(b"x" * 5000)
    monkeypatch.setattr(identity_store, "MAX_BYTES", 200)
    with pytest.raises(ValueError, match="expanded"):
        decode_identity_history("identities-" + hashlib.sha256(bomb).hexdigest() + ".json.gz", bomb)


def test_archive_is_public_metadata_only():
    name, content = encode_identity_history([_observation()])
    payload = json.loads(gzip.decompress(content))
    assert name.startswith("identities-")
    assert set(payload) == {"schemaVersion", "observations"}
    assert "SEC_USER_AGENT" not in gzip.decompress(content).decode()
    assert "test@example.com" not in gzip.decompress(content).decode()
    assert not any(Path(key).suffix == ".xml" for key in payload)


def test_listing_proof_survives_immutable_release_readback_and_replay():
    row = _multi_listing_observation([_common_filing()])
    store = ReleaseIdentityStore("owner/repo", target="a" * 40)
    store.transport = FakeReleases()
    receipt = store.persist([row])
    assert store.latest() == [row]
    assert store.persist([row]) == receipt
    assert store.latest()[0]["provenance"]["common_stock_listing_evidence"] == (
        row["provenance"]["common_stock_listing_evidence"])


@pytest.mark.parametrize("changes", [
    {"source_url": "https://evil.example/data.xml"},
    {"source_url": "https://www.sec.gov/Archives/edgar/data/x.xml?token=secret"},
    {"source_hash": "sha256:invalid"},
    {"issuer_cik": "0000000008"},
    {"ticker": "OTHER"},
    {"knowledge_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"knowledge_at": NOW.replace(tzinfo=None).isoformat()},
    {"accepted_at": (NOW - timedelta(days=366)).isoformat()},
    {"security_title": "Warrants for Common Stock"},
    {"raw_xml": "not public"},
])
def test_listing_proof_rejects_invalid_or_private_nested_evidence(changes):
    row = _multi_listing_observation([_common_filing()])
    row["provenance"]["common_stock_listing_evidence"].update(changes)
    with pytest.raises(ValueError):
        encode_identity_history([row])


def test_listing_proof_flag_requires_archived_evidence():
    row = _multi_listing_observation([_common_filing()])
    del row["provenance"]["common_stock_listing_evidence"]
    with pytest.raises(ValueError, match="flag/evidence"):
        encode_identity_history([row])
