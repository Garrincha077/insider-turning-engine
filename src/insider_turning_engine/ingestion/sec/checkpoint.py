"""Content-addressed acquisition checkpoints; never a signal/cursor commit.

Only typed canonical records and allow-listed acquisition evidence are exported.
Raw XML, HTTP cache, quarantine excerpts/messages and local paths stay local.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from insider_turning_engine.domain.models import CanonicalTransaction

from .daily_history import (
    LEGACY_PARSER_VERSION,
    PARSER_VERSION,
    SUPPORTED_PARSER_VERSIONS,
    _digest,
    _load_filing,
)
from .daily_index import daily_index_url
from .historical import _write_json, sha256_file

MAX_BYTES = 128 * 1024 * 1024
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_HASH = re.compile(r"sha256:[a-f0-9]{64}")
_PROVENANCE = frozenset({
    "discovery", "daily_index_url", "daily_index_hash", "complete_submission_hash",
    "filer_cik", "acceptance_timezone", "acceptance_parser_version",
})


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    accession = payload["accession"]
    if not isinstance(accession, str) or not _ACCESSION.fullmatch(accession):
        raise ValueError("invalid checkpoint accession")
    if (payload["schemaVersion"] != "1.0.0" or payload["source"] != "sec-daily-index"
        or payload["parserVersion"] not in SUPPORTED_PARSER_VERSIONS
        or not _HASH.fullmatch(payload["indexHash"])):
        raise ValueError("incompatible acquisition checkpoint")
    rows = []
    keys = set()
    for row in payload["records"]:
        typed = CanonicalTransaction.model_validate(row)
        if payload["parserVersion"] == LEGACY_PARSER_VERSION and typed.schema_version != "1.0.0":
            raise ValueError("legacy parser cannot claim new quantity semantics")
        key = (typed.transaction_id, typed.revision_id)
        url = urlparse(typed.source.source_url)
        if (typed.source.accession_number != accession or key in keys
            or typed.source.provider != "sec" or typed.timestamps.accepted_at is None
            or url.scheme != "https" or url.netloc != "www.sec.gov"
            or not url.path.startswith("/Archives/edgar/data/") or url.query or url.fragment):
            raise ValueError("checkpoint record identity mismatch or duplicate")
        keys.add(key)
        rows.append(typed.canonical_dump())
    quarantines = []
    for item in payload["quarantines"]:
        code = item["reason_code"]
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            raise ValueError("invalid quarantine reason code")
        # No free-form SEC excerpts, exception messages, recipient or local paths.
        row_key = item.get("source_row_key")
        if not isinstance(row_key, str) or not re.fullmatch(
            r"(?:NON_DERIVATIVE|DERIVATIVE):\d{1,6}:\d{10}", row_key,
        ):
            row_key = accession
        quarantines.append({"reason_code": code, "message": "Inspect original SEC filing",
                            "source_row_key": row_key})
    provenance = payload["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE:
        raise ValueError("unexpected checkpoint provenance")
    if (provenance["daily_index_hash"] != payload["indexHash"]
        or provenance["discovery"] != "edgar_daily_index"
        or not _HASH.fullmatch(provenance["complete_submission_hash"])
        or not re.fullmatch(r"\d{10}", provenance["filer_cik"])
        or provenance["acceptance_timezone"] != "America/New_York"
        or provenance["acceptance_parser_version"] != "2"):
        raise ValueError("invalid checkpoint availability provenance")
    result = {
        "schemaVersion": "1.0.0", "source": "sec-daily-index",
        "parserVersion": payload["parserVersion"],
        "accession": accession, "indexHash": payload["indexHash"],
        "provenance": provenance, "records": rows, "quarantines": quarantines,
    }
    if "repair" in payload:
        _validate_repair(payload)
        result["repair"] = payload["repair"]
    return result


def _validate_repair(payload: dict[str, Any]) -> None:
    receipt = payload["repair"]
    fields = {"previousFilingHash", "previousCheckpointHash", "previousParserVersion",
              "replayedAt", "previousRecordCount", "resolvedRowKeys"}
    if (payload["parserVersion"] != PARSER_VERSION or not isinstance(receipt, dict)
            or set(receipt) != fields or receipt["previousParserVersion"]
            not in SUPPORTED_PARSER_VERSIONS):
        raise ValueError("invalid derivative repair receipt")
    for name in ("previousFilingHash", "previousCheckpointHash"):
        if not isinstance(receipt[name], str) or not re.fullmatch(r"[a-f0-9]{64}", receipt[name]):
            raise ValueError("invalid repair ancestry hash")
    point = datetime.fromisoformat(receipt["replayedAt"])
    keys = receipt["resolvedRowKeys"]
    count = receipt["previousRecordCount"]
    if (point.tzinfo is None or not isinstance(count, int) or isinstance(count, bool) or count < 1
            or not isinstance(keys, list) or not keys or keys != sorted(set(keys))
            or any(not isinstance(key, str) or not re.fullmatch(r"DERIVATIVE:\d+:\d{10}", key)
                   for key in keys) or len(payload["records"]) != count + len(keys)):
        raise ValueError("invalid repaired row inventory")
    rows = {row["source"]["sourceRowKey"]: CanonicalTransaction.model_validate(row)
            for row in payload["records"]}
    if any(key not in rows or rows[key].schema_version != "1.1.0"
           or rows[key].timestamps.recorded_at != point for key in keys):
        raise ValueError("repaired row availability does not match receipt")


def validate_checkpoint(value: Any, *, day: date) -> dict[str, Any]:
    fields = {"schemaVersion", "day", "parserVersion", "indexHash", "discoveredAccessions",
              "filings", "failures", "signalReady"}
    if (not isinstance(value, dict) or set(value) != fields or value["schemaVersion"] != "1.0.0"
        or value["day"] != day.isoformat()
        or value["parserVersion"] not in SUPPORTED_PARSER_VERSIONS
        or value["signalReady"] is not False or not _HASH.fullmatch(value["indexHash"])):
        raise ValueError("invalid acquisition checkpoint contract")
    discovered = value["discoveredAccessions"]
    if (not isinstance(discovered, list) or len(discovered) > 10000
        or any(not isinstance(item, str) or not _ACCESSION.fullmatch(item) for item in discovered)
        or discovered != sorted(set(discovered))):
        raise ValueError("invalid checkpoint discovery set")
    seen: set[str] = set()
    for payload in value["filings"]:
        safe = _safe_payload(payload)
        if (value["parserVersion"] == LEGACY_PARSER_VERSION
                and payload["parserVersion"] != LEGACY_PARSER_VERSION):
            raise ValueError("legacy checkpoint cannot wrap new parser evidence")
        accession = safe["accession"]
        if (safe != payload or accession in seen or accession not in discovered
            or safe["indexHash"] != value["indexHash"]
            or safe["provenance"]["daily_index_url"] != daily_index_url(day)):
            raise ValueError("invalid checkpoint filing evidence")
        seen.add(accession)
    for failure in value["failures"]:
        if (set(failure) != {"providerRecordId", "status"}
            or not re.fullmatch(r"[A-Za-z_]{1,80}", failure["status"])):
            raise ValueError("invalid checkpoint failure evidence")
        accession = failure["providerRecordId"]
        if accession in seen or accession not in discovered:
            raise ValueError("checkpoint failures overlap or escape discovery")
        seen.add(accession)
    if seen != set(discovered):
        raise ValueError("checkpoint omits discovered filings")
    return dict(value)


def build_checkpoint(root: Path, *, day: date) -> dict[str, Any]:
    """Validate all local evidence before projecting a portable checkpoint."""
    report = json.loads((root / "manifest.json").read_text("utf-8"))
    batch_path = root / "sec-batch.json"
    if (report["day"] != day.isoformat() or report["parserVersion"] != PARSER_VERSION
        or sha256_file(batch_path) != report["batchSha256"]):
        raise ValueError("invalid local acquisition manifest")
    batch = json.loads(batch_path.read_text("utf-8"))
    payloads = []
    original_rows = []
    original_quarantines = []
    for proof in report["filings"]:
        accession = proof["accession"]
        if not isinstance(accession, str) or not _ACCESSION.fullmatch(accession):
            raise ValueError("invalid local filing identity")
        path = root / "filings" / f"{accession}.json"
        if sha256_file(path) != proof["sha256"]:
            raise ValueError("filing evidence checksum mismatch")
        payload = _load_filing(path, accession, report["indexHash"], retry_quarantined=False)
        if payload is None:
            raise ValueError("invalid local filing payload")
        original_rows.extend(payload["records"])
        original_quarantines.extend(payload["quarantines"])
        payloads.append(_safe_payload(payload))
    original_rows.sort(key=lambda row: (row["transactionId"], row["revisionId"]))
    if (original_rows != batch["records"] or original_quarantines != batch["quarantines"]
        or len(original_rows) != report["recordCount"]
        or len(original_quarantines) != report["quarantineCount"]):
        raise ValueError("batch disagrees with durable per-filing evidence")
    discovered = sorted([item["accession"] for item in payloads]
                        + [item["providerRecordId"] for item in batch["failures"]])
    if len(discovered) != report["discoveredFilings"]:
        raise ValueError("discovery count mismatch")
    return validate_checkpoint({
        "schemaVersion": "1.0.0", "day": day.isoformat(), "parserVersion": PARSER_VERSION,
        "indexHash": report["indexHash"], "discoveredAccessions": discovered,
        "filings": payloads, "failures": batch["failures"], "signalReady": False,
    }, day=day)


def encode_checkpoint(value: dict[str, Any]) -> tuple[str, bytes]:
    day = date.fromisoformat(value["day"])
    validate_checkpoint(value, day=day)
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(content) > MAX_BYTES:
        raise ValueError("checkpoint exceeds size limit")
    # Fixed gzip metadata makes identical input byte-identical across retries.
    with io.BytesIO() as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressor:
            compressor.write(content)
        compressed = stream.getvalue()
    digest = hashlib.sha256(compressed).hexdigest()
    return f"checkpoint-{digest}.json.gz", compressed


def decode_checkpoint(name: str, content: bytes, *, day: date) -> dict[str, Any]:
    expected = f"checkpoint-{hashlib.sha256(content).hexdigest()}.json.gz"
    if name != expected or len(content) > MAX_BYTES:
        raise ValueError("checkpoint checksum or compressed size mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("checkpoint expansion exceeds limit")
    return validate_checkpoint(json.loads(payload), day=day)


def restore_checkpoint(value: dict[str, Any], *, day: date, root: Path) -> None:
    """Restore only per-filing evidence; fresh discovery must rebuild any marker."""
    validate_checkpoint(value, day=day)
    if root.exists():
        raise ValueError("checkpoint restore requires a fresh day directory")
    for payload in value["filings"]:
        _write_json(root / "filings" / f"{payload['accession']}.json",
                    {"payload": payload, "sha256": _digest(payload)})
