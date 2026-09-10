import copy
import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from insider_turning_engine.cli import app
from insider_turning_engine.ingestion.sec.checkpoint import (
    build_checkpoint,
    decode_checkpoint,
    encode_checkpoint,
    restore_checkpoint,
    validate_checkpoint,
)
from insider_turning_engine.ingestion.sec.daily_history import ingest_day
from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.historical import RequestPacer
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore
from insider_turning_engine.pipeline.sec_acquisition import acquire_range

DAY = date(2026, 8, 31)
FIXTURE = Path(__file__).parent / "fixtures/form4_non_derivative.xml"
ACCESSIONS = ["0001234567-26-000001", "0001234567-26-000002"]


def provider(
    root: Path, *, requests: list[str] | None = None, broken: bool = False,
    invalid_rows: bool = False, clock_day: int = 2, revised: bool = False,
) -> SECDailyIndexSource:
    def respond(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request.url.path)
        if request.url.path.endswith("index.json"):
            return httpx.Response(200, json={"directory": {"item": [
                {"name": "master.20260831.idx", "type": "file"},
                {"name": "master.20260902.idx", "type": "file"},
                {"name": "company.20260831.idx", "type": "file"},
            ]}})
        if request.url.path.endswith(".idx"):
            index = "CIK|Company Name|Form Type|Date Filed|Filename\n----\n"
            for accession in ACCESSIONS:
                index += f"1234567|Owner|4|2026-08-31|edgar/data/1234567/{accession}.txt\n"
            return httpx.Response(200, text=index + ("\n" if revised else ""))
        if broken and request.url.path.endswith("000002.txt"):
            return httpx.Response(500)
        accession = Path(request.url.path).stem
        xml = FIXTURE.read_bytes()
        if invalid_rows:
            xml = xml.replace(b"<transactionShares>", b"<notShares>")
            xml = xml.replace(b"</transactionShares>", b"</notShares>")
        body = (f"<ACCEPTANCE-DATETIME>20260831160100\n<ACCESSION-NUMBER>{accession}\n"
                "<DOCUMENT>\n<TYPE>4\n<FILENAME>ownership.xml\n<TEXT>\n").encode()
        return httpx.Response(200, content=body + xml + b"\n</TEXT>\n</DOCUMENT>")
    return SECDailyIndexSource(
        "ITE test@example.com", client=httpx.Client(transport=httpx.MockTransport(respond)),
        cache_dir=root, clock=lambda: datetime(2026, 9, clock_day, 10, tzinfo=UTC),
        sleeper=lambda _: None, max_attempts=1, pacer=RequestPacer(sleeper=lambda _: None),
    )


def checkpoint(tmp_path: Path, *, invalid_rows: bool = False) -> dict[str, Any]:
    ingest_day(provider(tmp_path / "cache", invalid_rows=invalid_rows), day=DAY,
               output_root=tmp_path / "days")
    return build_checkpoint(tmp_path / "days" / DAY.isoformat(), day=DAY)


class MemoryStore:
    def __init__(self) -> None:
        self.content: dict[date, tuple[str, bytes]] = {}
        self.fail = False

    def latest(self, day: date) -> dict[str, Any] | None:
        stored = self.content.get(day)
        return decode_checkpoint(*stored, day=day) if stored else None

    def persist(self, value: dict[str, Any]) -> dict[str, str]:
        if self.fail:
            raise RuntimeError("upload failed")
        self.content[date.fromisoformat(value["day"])] = encode_checkpoint(value)
        return {"storageStatus": "VERIFIED", "sha256": "fixture"}


def test_checkpoint_round_trip_retains_original_knowledge_without_markers(tmp_path: Path) -> None:
    value = checkpoint(tmp_path)
    name, compressed = encode_checkpoint(value)
    assert (name, compressed) == encode_checkpoint(value)
    decoded = decode_checkpoint(name, compressed, day=DAY)
    restored = tmp_path / "restored" / DAY.isoformat()
    restore_checkpoint(decoded, day=DAY, root=restored)
    with pytest.raises(ValueError, match="fresh"):
        restore_checkpoint(decoded, day=DAY, root=restored)
    assert not list(restored.rglob("*.sha256"))
    calls: list[str] = []
    result = ingest_day(provider(tmp_path / "new-cache", requests=calls, clock_day=3), day=DAY,
                        output_root=restored.parent, retry_quarantined=False)
    assert result["status"] == "ACQUIRED"
    assert not any(path.endswith(".txt") for path in calls)
    assert build_checkpoint(restored, day=DAY) == value


def test_checkpoint_public_projection_has_no_free_text_quarantine_or_raw(tmp_path: Path) -> None:
    value = checkpoint(tmp_path, invalid_rows=True)
    assert any(item["quarantines"] for item in value["filings"])
    for payload in value["filings"]:
        for quarantine in payload["quarantines"]:
            assert set(quarantine) == {"reason_code", "message", "source_row_key"}
            assert quarantine["message"] == "Inspect original SEC filing"
    text = json.dumps(value)
    assert "<ownershipDocument>" not in text and "test@example.com" not in text
    assert "excerpt" not in text and str(tmp_path) not in text


@pytest.mark.parametrize("mutation", [
    "signal", "duplicate", "missing", "index", "source", "extra", "quarantine",
])
def test_tampered_checkpoint_contract_is_rejected(tmp_path: Path, mutation: str) -> None:
    value = checkpoint(tmp_path)
    if mutation == "signal":
        value["signalReady"] = True
    elif mutation == "duplicate":
        value["filings"].append(copy.deepcopy(value["filings"][0]))
    elif mutation == "missing":
        value["filings"].pop()
    elif mutation == "index":
        value["indexHash"] = "sha256:" + "0" * 64
    elif mutation == "source":
        value["filings"][0]["records"][0]["source"]["accessionNumber"] = ACCESSIONS[1]
    elif mutation == "extra":
        value["filings"][0]["rawXml"] = "secret"
    elif mutation == "quarantine":
        value["filings"][0]["quarantines"] = [{"reason_code": "BAD", "message": "secret"}]
    with pytest.raises(ValueError):
        validate_checkpoint(value, day=DAY)


def test_checksum_and_expansion_limits_fail_closed(tmp_path: Path, monkeypatch: Any) -> None:
    value = checkpoint(tmp_path)
    name, compressed = encode_checkpoint(value)
    with pytest.raises(ValueError, match="checksum"):
        decode_checkpoint(name, compressed + b"x", day=DAY)
    monkeypatch.setattr("insider_turning_engine.ingestion.sec.checkpoint.MAX_BYTES", 1000)
    large = gzip.compress(b" " * 10000, mtime=0)
    name = "checkpoint-" + hashlib.sha256(large).hexdigest() + ".json.gz"
    with pytest.raises(ValueError, match="expansion"):
        decode_checkpoint(name, large, day=DAY)


def test_local_batch_and_filing_hash_must_agree(tmp_path: Path) -> None:
    checkpoint(tmp_path)
    batch = tmp_path / "days" / DAY.isoformat() / "sec-batch.json"
    batch.write_text("{}")
    with pytest.raises(ValueError, match="manifest"):
        build_checkpoint(batch.parent, day=DAY)


def test_directory_enumerates_only_published_completed_days(tmp_path: Path) -> None:
    source = provider(tmp_path)
    assert source.discover_days(date(2026, 8, 30), date(2026, 9, 1)) == (DAY,)
    with pytest.raises(ValueError, match="completed"):
        source.discover_days(DAY, date(2026, 9, 2))
    with pytest.raises(ValueError, match="32 days"):
        source.discover_days(date(2026, 1, 1), DAY)


def test_fresh_runner_resumes_and_third_run_fetches_no_filings(tmp_path: Path) -> None:
    store = MemoryStore()
    first = acquire_range(provider(tmp_path / "cache1"), store, start=DAY, end=DAY,
                          root=tmp_path / "run1", max_filings=1)
    assert first["storageStatus"] == "VERIFIED" and first["acquisitionStatus"] == "INCOMPLETE"
    assert first["days"][0]["pendingFilings"] == 1
    calls: list[str] = []
    second = acquire_range(provider(tmp_path / "cache2", requests=calls, clock_day=3), store,
                           start=DAY, end=DAY, root=tmp_path / "run2", max_filings=1)
    assert second["acquisitionStatus"] == "ACQUIRED"
    assert sum(path.endswith(".txt") for path in calls) == 1
    saved = store.content[DAY]
    calls.clear()
    third = acquire_range(provider(tmp_path / "cache3", requests=calls), store, start=DAY,
                          end=DAY, root=tmp_path / "run3")
    assert third["days"][0]["reused"] and store.content[DAY] == saved
    assert not any(path.endswith(".txt") for path in calls)
    assert not third["publishable"] and not third["alertsAllowed"] and not third["signalReady"]
    assert not list(tmp_path.rglob("sec.cursor"))
    assert not list(tmp_path.rglob("sec-batch-committed.sha256"))


def test_remote_storage_failure_preserves_previous_checkpoint(tmp_path: Path) -> None:
    store = MemoryStore()
    acquire_range(provider(tmp_path / "cache1"), store, start=DAY, end=DAY,
                  root=tmp_path / "run1", max_filings=1)
    saved = store.content[DAY]
    store.fail = True
    result = acquire_range(provider(tmp_path / "cache2"), store, start=DAY, end=DAY,
                           root=tmp_path / "run2")
    assert result["storageStatus"] == "INCOMPLETE" and store.content[DAY] == saved
    assert result["days"][0]["storageStatus"] == "FAILED"


def test_quarantine_is_durable_but_never_ready_or_retimed(tmp_path: Path) -> None:
    store = MemoryStore()
    first = acquire_range(provider(tmp_path / "cache1", invalid_rows=True), store,
                          start=DAY, end=DAY, root=tmp_path / "run1")
    assert first["storageStatus"] == "VERIFIED" and first["acquisitionStatus"] == "INCOMPLETE"
    saved = store.content[DAY]
    calls: list[str] = []
    second = acquire_range(provider(tmp_path / "cache2", requests=calls, clock_day=3), store,
                           start=DAY, end=DAY, root=tmp_path / "run2")
    assert second["acquisitionStatus"] == "INCOMPLETE" and store.content[DAY] == saved
    assert not any(path.endswith(".txt") for path in calls)


def test_index_revision_blocks_reuse_and_keeps_checkpoint(tmp_path: Path) -> None:
    store = MemoryStore()
    acquire_range(provider(tmp_path / "cache1"), store, start=DAY, end=DAY, root=tmp_path / "run1")
    saved = store.content[DAY]
    result = acquire_range(provider(tmp_path / "cache2", revised=True), store,
                           start=DAY, end=DAY, root=tmp_path / "run2")
    assert result["storageStatus"] == "INCOMPLETE" and store.content[DAY] == saved


def test_transport_failure_is_stored_but_never_acquired(tmp_path: Path) -> None:
    store = MemoryStore()
    result = acquire_range(provider(tmp_path / "cache", broken=True), store,
                           start=DAY, end=DAY, root=tmp_path / "run")
    assert result["storageStatus"] == "VERIFIED"
    assert result["acquisitionStatus"] == "INCOMPLETE"
    assert result["days"][0]["failureCount"] == 1
    assert result["days"][0]["storedFilings"] == 1


def test_discovery_failure_is_not_missing_checkpoint_success(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = provider(tmp_path / "cache")
    def failed(*args: Any) -> None:
        raise RuntimeError("SEC unavailable")
    monkeypatch.setattr(source, "discover_days", failed)
    result = acquire_range(source, MemoryStore(), start=DAY, end=DAY, root=tmp_path / "run")
    assert result["storageStatus"] == "INCOMPLETE"
    assert "SEC_DIRECTORY_DISCOVERY_FAILED" in result["issues"]


def test_wall_clock_budget_stores_pending_without_fetching(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    calls: list[str] = []
    # Monotonic start is zero, then the budget expires before the first filing.
    ticks = iter([0.0, 2.0, 2.0])
    monkeypatch.setattr("insider_turning_engine.ingestion.sec.daily_history.time.monotonic",
                        lambda: next(ticks, 2.0))
    source = provider(tmp_path / "cache", requests=calls)
    result = ingest_day(source, day=DAY, output_root=tmp_path / "days", max_seconds=1)
    assert result["pendingFilings"] == 2 and result["status"] == "INCOMPLETE"
    assert not any(path.endswith(".txt") for path in calls)
    assert len(build_checkpoint(tmp_path / "days" / DAY.isoformat(), day=DAY)["failures"]) == 2


def test_no_published_day_is_not_an_empty_success(tmp_path: Path) -> None:
    result = acquire_range(provider(tmp_path / "cache"), MemoryStore(),
                           start=date(2026, 9, 1), end=date(2026, 9, 1), root=tmp_path / "run")
    assert result["storageStatus"] == "INCOMPLETE"
    assert "NO_PUBLISHED_INDEX_IN_REQUESTED_RANGE" in result["issues"]


class FakeReleases(ReleaseCheckpointStore):
    def __init__(self) -> None:
        super().__init__("owner/repo", target="a" * 40)
        self.releases: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.commands: list[tuple[str, ...]] = []

    def _gh(self, *args: str) -> str:
        self.commands.append(args)
        if args[0] == "api":
            if "--paginate" in args:
                return json.dumps([self.releases])
            return json.dumps(next(item for item in self.releases
                                   if args[1].endswith(item["tag_name"])))
        tag = args[2]
        if args[1] == "create":
            path = Path(args[3])
            self.files[tag] = path.read_bytes()
            self.releases.append({
                "id": len(self.releases) + 1, "tag_name": tag, "draft": False, "prerelease": True,
                "assets": [{"name": path.name, "size": path.stat().st_size, "state": "uploaded"}],
            })
        elif args[1] == "download":
            name = args[args.index("--pattern") + 1]
            root = Path(args[args.index("--dir") + 1])
            (root / name).write_bytes(self.files[tag])
        else:
            raise AssertionError(args)
        return ""


def test_release_persist_verifies_readback_and_is_idempotent(tmp_path: Path) -> None:
    store = FakeReleases()
    value = checkpoint(tmp_path)
    first = store.persist(value)
    assert first["storageStatus"] == "VERIFIED"
    assert store.latest(DAY) == value
    assert store.persist(value) == first
    assert sum(args[:2] == ("release", "create") for args in store.commands) == 1
    assert all("--clobber" not in args for args in store.commands)
    assert any("--latest=false" in args for args in store.commands)
    store.files[first["tag"]] += b"x"
    with pytest.raises(ValueError, match="size"):
        store.latest(DAY)


def test_cli_preview_never_contacts_sec_or_github(monkeypatch: Any, tmp_path: Path) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("preview contacted network")
    monkeypatch.setattr(ReleaseCheckpointStore, "_gh", forbidden)
    monkeypatch.setattr(SECDailyIndexSource, "_get", forbidden)
    result = CliRunner().invoke(app, ["acquire-sec-daily", "--repository", "owner/repo",
                                     "--target", "a" * 40, "--output-root", str(tmp_path / "out")])
    assert result.exit_code == 0 and '"status": "DRY_RUN"' in result.stdout
    assert not (tmp_path / "out").exists()
