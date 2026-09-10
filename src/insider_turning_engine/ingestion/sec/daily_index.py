"""Global EDGAR daily-index discovery for ownership filings.

The daily index is the discovery surface; the complete submission text is the
authority for the exact acceptance timestamp, issuer CIK, primary ownership
document and payload. This avoids per-CIK polling and does not treat the
index's filing date as an availability timestamp.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import httpx

from insider_turning_engine.domain.models import QuarantineRecord

from .base import SecPage, SecRawRecord
from .historical import (
    _SEC_PACER,
    RequestPacer,
    _bounded_response_body,
    _response_context,
    _validate_sec_url,
    validate_sec_user_agent,
)
from .incremental import OWNERSHIP_FORMS

DAILY_INDEX_ROOT = "https://www.sec.gov/Archives/edgar/daily-index"
ARCHIVES_ROOT = "https://www.sec.gov/Archives"
_ACCESSION_RE = re.compile(r"\d{10}-\d{2}-\d{6}")
_ACCESSION_HEADER_RE = re.compile(
    r"(?:<ACCESSION-NUMBER>\s*|^ACCESSION NUMBER:\s*)(\d{10}-\d{2}-\d{6})",
    re.IGNORECASE | re.MULTILINE,
)
_ACCEPTED_RE = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", re.IGNORECASE)
_ISSUER_RE = re.compile(r"<issuerCik>\s*(\d{1,10})\s*</issuerCik>", re.IGNORECASE)
_DOCUMENT_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class DailyIndexEntry:
    filer_cik: str
    company_name: str
    form_type: str
    filing_date: date
    submission_path: str
    accession_number: str

    @property
    def submission_url(self) -> str:
        return f"{ARCHIVES_ROOT}/{self.submission_path}"


def daily_index_url(day: date) -> str:
    quarter = (day.month - 1) // 3 + 1
    return f"{DAILY_INDEX_ROOT}/{day.year}/QTR{quarter}/master.{day:%Y%m%d}.idx"


def parse_daily_master_index(payload: bytes | str) -> tuple[DailyIndexEntry, ...]:
    """Parse and filter one official ``master.YYYYMMDD.idx`` payload."""

    text = payload.decode("latin-1") if isinstance(payload, bytes) else payload
    rows: list[DailyIndexEntry] = []
    in_body = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not in_body:
            if line and set(line) == {"-"}:
                in_body = True
            continue
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 5:
            raise ValueError("SEC daily master index row must have five fields")
        cik, company, form, filed, submission = (part.strip() for part in parts)
        form = form.upper()
        if form not in OWNERSHIP_FORMS:
            continue
        if not cik.isdigit() or len(cik) > 10:
            raise ValueError("SEC daily index CIK is invalid")
        path = PurePosixPath(submission)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) != 4
            or path.parts[:2] != ("edgar", "data")
            or not path.parts[2].isdigit()
            or path.suffix.lower() != ".txt"
        ):
            raise ValueError("SEC daily index submission path is invalid")
        match = re.fullmatch(r"(\d{10}-\d{2}-\d{6})\.txt", path.name)
        if match is None:
            raise ValueError("SEC daily index accession is invalid")
        rows.append(
            DailyIndexEntry(
                cik.zfill(10),
                company,
                form,
                date.fromisoformat(filed),
                path.as_posix(),
                match.group(1),
            )
        )
    if not in_body:
        raise ValueError("SEC daily master index header terminator is missing")
    # Ownership filings can appear once for the issuer and again for one or
    # more reporting owners.  The accession is the filing identity; fetching
    # every index alias wastes requests and duplicates canonical rows.  Prefer
    # the entry whose CIK matches the accession filer prefix when available,
    # then use a stable lexical tie-break.
    selected: dict[str, DailyIndexEntry] = {}
    for row in rows:
        current = selected.get(row.accession_number)
        prefix = row.accession_number.split("-", 1)[0]
        rank = (row.filer_cik.lstrip("0") != prefix.lstrip("0"), row.filer_cik, row.company_name)
        if current is None:
            selected[row.accession_number] = row
            continue
        if row.form_type != current.form_type or row.filing_date != current.filing_date:
            raise ValueError("daily index aliases disagree on form or filing date")
        current_rank = (
            current.filer_cik.lstrip("0") != prefix.lstrip("0"),
            current.filer_cik,
            current.company_name,
        )
        if rank < current_rank:
            selected[row.accession_number] = row
    return tuple(
        sorted(selected.values(), key=lambda row: (row.filing_date, row.accession_number))
    )


def _field(block: str, name: str) -> str | None:
    match = re.search(rf"<{name}>\s*([^\r\n<]+)", block, re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_complete_submission(
    payload: bytes,
    entry: DailyIndexEntry,
    *,
    retrieved_at: datetime,
    index_url: str,
    index_hash: str,
) -> SecRawRecord:
    """Recover exact filing availability and the primary ownership XML."""

    text = payload.decode("utf-8", errors="replace")
    accepted_match = _ACCEPTED_RE.search(text)
    if accepted_match is None:
        raise ValueError("complete submission has no acceptance timestamp")
    # SGML's unzoned acceptance clock is Eastern, NOT the UTC submissions API
    # representation. The IANA zone handles DST, including the pre-2007 rule.
    wall_time = datetime.strptime(accepted_match.group(1), "%Y%m%d%H%M%S")
    eastern = ZoneInfo("America/New_York")
    local = wall_time.replace(tzinfo=eastern)
    if (local.utcoffset() != wall_time.replace(tzinfo=eastern, fold=1).utcoffset()
        or local.astimezone(UTC).astimezone(eastern).replace(tzinfo=None) != wall_time):
        raise ValueError("ambiguous or nonexistent SEC acceptance time")
    accepted = local.astimezone(UTC)
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must include a timezone")
    if accepted > retrieved_at.astimezone(UTC):
        raise ValueError("SEC acceptance is later than retrieval")
    accession_match = _ACCESSION_HEADER_RE.search(text[:100_000])
    accession_header = accession_match.group(1) if accession_match is not None else None
    if accession_header != entry.accession_number:
        raise ValueError("complete submission accession disagrees with daily index")

    selected: tuple[str, str] | None = None
    issuer_cik: str | None = None
    for match in _DOCUMENT_RE.finditer(text):
        block = match.group(1)
        document_type = (_field(block, "TYPE") or "").upper()
        filename = _field(block, "FILENAME")
        body_match = re.search(r"<TEXT>(.*)</TEXT>", block, re.IGNORECASE | re.DOTALL)
        if document_type != entry.form_type or filename is None or body_match is None:
            continue
        if PurePosixPath(filename).name != filename or not filename.lower().endswith(".xml"):
            continue
        body = body_match.group(1).strip()
        # Real EDGAR complete submissions commonly wrap the primary XML in
        # an SGML ``<XML>`` transport element inside ``<TEXT>``.  The
        # ownership parser must receive the XML document itself, not that
        # outer submission wrapper.
        wrapper = re.fullmatch(r"<XML>\s*(.*?)\s*</XML>", body, re.IGNORECASE | re.DOTALL)
        if wrapper is not None:
            body = wrapper.group(1).strip()
        cik_match = _ISSUER_RE.search(body)
        if cik_match is None:
            continue
        selected = filename, body
        issuer_cik = cik_match.group(1).zfill(10)
        break
    if selected is None or issuer_cik is None:
        raise ValueError("complete submission has no primary ownership XML")
    primary, xml = selected
    compact = entry.accession_number.replace("-", "")
    source_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{entry.filer_cik.lstrip('0') or '0'}/{compact}/{primary}"
    )
    xml_bytes = xml.encode("utf-8")
    return SecRawRecord(
        provider="sec",
        provider_record_id=entry.accession_number,
        issuer_cik=issuer_cik,
        accession_number=entry.accession_number,
        form_type=entry.form_type,
        accepted_at=accepted,
        source_url=source_url,
        replay_locator=entry.submission_url,
        retrieved_at=retrieved_at.astimezone(UTC),
        content_hash="sha256:" + hashlib.sha256(xml_bytes).hexdigest(),
        payload=xml_bytes,
        primary_document=primary,
        filing_date=entry.filing_date.isoformat(),
        provenance={
            "discovery": "edgar_daily_index",
            "daily_index_url": index_url,
            "daily_index_hash": index_hash,
            "complete_submission_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "filer_cik": entry.filer_cik,
            "acceptance_timezone": "America/New_York",
            "acceptance_parser_version": "2",
        },
    )


class SECDailyIndexSource:
    """Discover all daily ownership filings with SEC-compliant request pacing."""

    def __init__(
        self,
        user_agent: str,
        *,
        client: httpx.Client | None = None,
        cache_dir: str | Path | None = None,
        pacer: RequestPacer | None = None,
        max_attempts: int = 4,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.user_agent = validate_sec_user_agent(user_agent)
        self.client = client or httpx.Client(timeout=60.0, follow_redirects=False)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.pacer = pacer or _SEC_PACER
        self.max_attempts = max(1, max_attempts)
        self.sleeper = sleeper
        self.clock = clock

    def _get(self, url: str, *, maximum_bytes: int) -> bytes:
        _validate_sec_url(url)
        error: Exception | None = None
        for attempt in range(self.max_attempts):
            self.pacer.wait()
            try:
                with _response_context(
                    self.client, url, {"User-Agent": self.user_agent, "Accept": "text/plain"}
                ) as response:
                    if response.history or 300 <= response.status_code < 400:
                        raise ValueError("SEC redirects are not accepted")
                    if str(response.url) != url:
                        raise ValueError("SEC response URL changed")
                    response.raise_for_status()
                    return _bounded_response_body(response, maximum_bytes)
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if attempt + 1 < self.max_attempts:
                    self.sleeper(min(16.0, float(2**attempt)))
        raise RuntimeError(f"SEC daily-index request failed: {error}") from error

    def _cache_paths(self, name: str) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        target = self.cache_dir / "daily-index" / name
        return target, target.with_suffix(target.suffix + ".manifest.json")

    def _cached(self, name: str, *, maximum_bytes: int) -> tuple[bytes, datetime] | None:
        paths = self._cache_paths(name)
        if paths is None:
            return None
        target, manifest_path = paths
        try:
            payload = target.read_bytes()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        retrieved_at = manifest.get("retrievedAt") if isinstance(manifest, dict) else None
        if (
            len(payload) > maximum_bytes
            or not isinstance(manifest, dict)
            or manifest.get("schemaVersion") != "1.1.0"
            or manifest.get("sha256") != digest
            or not isinstance(retrieved_at, str)
        ):
            return None
        try:
            cached_at = datetime.fromisoformat(retrieved_at)
        except ValueError:
            return None
        if cached_at.tzinfo is None:
            return None
        return payload, cached_at.astimezone(UTC)

    def _cache(self, name: str, payload: bytes, *, retrieved_at: datetime) -> None:
        paths = self._cache_paths(name)
        if paths is None:
            return
        target, manifest_path = paths
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = (
            json.dumps(
                {
                    "schemaVersion": "1.1.0",
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "retrievedAt": retrieved_at.astimezone(UTC).isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        for path, content in ((target, payload), (manifest_path, metadata)):
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

    def discover_day(self, day: date) -> tuple[DailyIndexEntry, ...]:
        """Discover a complete archived index without fetching every submission."""
        index_url = daily_index_url(day)
        index_name = f"master.{day:%Y%m%d}.idx"
        cached_index = self._cached(index_name, maximum_bytes=25 * 1024 * 1024)
        if cached_index is None:
            index_payload = self._get(index_url, maximum_bytes=25 * 1024 * 1024)
            self._cache(index_name, index_payload, retrieved_at=self.clock())
        else:
            index_payload, _index_retrieved_at = cached_index
        entries = parse_daily_master_index(index_payload)
        self.last_index_hash = "sha256:" + hashlib.sha256(index_payload).hexdigest()
        if any(entry.filing_date != day for entry in entries):
            raise ValueError("daily index contains a different filing date")
        return entries

    def fetch_entry(self, entry: DailyIndexEntry, *, index_hash: str) -> SecRawRecord:
        submission_name = f"{entry.accession_number}.txt"
        cached = self._cached(submission_name, maximum_bytes=25 * 1024 * 1024)
        if cached is None:
            submission = self._get(entry.submission_url, maximum_bytes=25 * 1024 * 1024)
            retrieved_at = self.clock()
            self._cache(submission_name, submission, retrieved_at=retrieved_at)
        else:
            submission, retrieved_at = cached
        return parse_complete_submission(
            submission, entry, retrieved_at=retrieved_at,
            index_url=daily_index_url(entry.filing_date), index_hash=index_hash,
        )

    def fetch_day(self, day: date) -> SecPage:
        entries = self.discover_day(day)
        # discover_day caches the source; when caching is disabled, retain the
        # index hash from the exact response instead of issuing a second request.
        index_hash = self.last_index_hash
        records: list[SecRawRecord] = []
        quarantines: list[QuarantineRecord] = []
        for entry in entries:
            try:
                records.append(self.fetch_entry(entry, index_hash=index_hash))
            except (RuntimeError, ValueError) as exc:
                quarantines.append(
                    QuarantineRecord(
                        reason_code="SEC_DAILY_INDEX_FILING_INVALID",
                        message=str(exc)[:500],
                        source_row_key=entry.accession_number,
                        locator=entry.submission_url,
                    )
                )
        ordered = tuple(sorted(records, key=lambda row: (row.accepted_at, row.accession_number)))
        # A partial day is replayed as a unit.  Exposing a watermark while any
        # filing is quarantined invites callers to checkpoint past that filing.
        watermark = (
            max((row.accepted_at for row in ordered), default=None)
            if not quarantines
            else None
        )
        return SecPage(ordered, source_watermark=watermark, quarantines=tuple(quarantines))

    def close(self) -> None:
        self.client.close()


__all__ = [
    "DAILY_INDEX_ROOT",
    "DailyIndexEntry",
    "SECDailyIndexSource",
    "daily_index_url",
    "parse_complete_submission",
    "parse_daily_master_index",
]
