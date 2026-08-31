"""Incremental SEC company-submissions adapter.

The implementation is intentionally HTTP-client agnostic: tests and replay
jobs inject a client exposing ``get`` while production may supply ``httpx``.
Only the SEC submissions envelope and each filing's primary XML cross the
transport boundary; malformed provider data becomes typed quarantine.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast

import httpx

from insider_turning_engine.domain.models import ParseResult, QuarantineRecord

from .base import (
    SecOutcomeStatus,
    SecPage,
    SecProviderHealth,
    SecRawRecord,
    SecResult,
    utc,
)
from .historical import (
    _SEC_PACER,
    MAX_RETRY_DELAY_SECONDS,
    RequestPacer,
    _bounded_response_body,
    _response_context,
    _validate_sec_response,
    _validate_sec_url,
    validate_sec_user_agent,
)
from .parser import parse_sec_ownership_document

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
OWNERSHIP_FORMS = frozenset({"3", "3/A", "4", "4/A", "5", "5/A"})
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_CURSOR_VERSION = 1
MAX_SUBMISSIONS_BYTES = 25 * 1024 * 1024
MAX_FILING_BYTES = 10 * 1024 * 1024
_JSON_CONTENT_TYPES = frozenset({"application/json"})
_XML_CONTENT_TYPES = frozenset({"application/xml", "text/xml"})


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: object, *, date_only: bool = False) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("acceptanceDateTime must be a non-empty ISO timestamp")
    text = value.strip()
    if date_only and len(text) == 10:
        parsed = date.fromisoformat(text)
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return utc(parsed)


def _as_cik(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("CIK must be a numeric SEC identifier")
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError("CIK must contain at most ten digits")
    return text.zfill(10)


def _as_instant(value: datetime | date | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    return _parse_time(value, date_only=True)


def _quarantine(
    code: str,
    message: str,
    *,
    locator: str | None = None,
    row_key: str | None = None,
    run_id: str | None = None,
) -> QuarantineRecord:
    return QuarantineRecord(
        reason_code=code,
        message=message[:500],
        source_row_key=row_key,
        locator=locator,
        run_id=run_id,
    )


def encode_cursor(accepted_at: datetime, accession_number: str, issuer_cik: str) -> str:
    """Encode an opaque, deterministic cursor for the filing sort key."""

    body = json.dumps(
        [_CURSOR_VERSION, utc(accepted_at).isoformat(), accession_number, _as_cik(issuer_cik)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, str, str] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("cursor must be an opaque non-empty string")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        version, accepted, accession, cik = json.loads(base64.urlsafe_b64decode(padded))
        if version != _CURSOR_VERSION:
            raise ValueError("unsupported cursor version")
        if not isinstance(accession, str) or not _ACCESSION_RE.fullmatch(accession):
            raise ValueError("cursor accession is invalid")
        return _parse_time(accepted), accession, _as_cik(cik)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid SEC cursor") from exc


def _key(record: SecRawRecord) -> tuple[datetime, str, str]:
    return record.accepted_at, record.accession_number, record.issuer_cik


class SECIncrementalSource:
    """Read ownership filings for a fixed issuer-CIK universe.

    The SEC requires an identifying ``User-Agent`` on every request.  A
    process-shared six-requests/second pacer is used by default; callers that
    coordinate across processes can inject a distributed-compatible pacer.
    """

    name = "sec"

    def __init__(
        self,
        issuer_ciks: Iterable[str | int] | None = None,
        user_agent: str | None = None,
        *,
        ciks: Iterable[str | int] | None = None,
        cache_dir: str | Path | None = None,
        client: Any | None = None,
        pacer: RequestPacer | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
        max_submissions_bytes: int = MAX_SUBMISSIONS_BYTES,
        max_filing_bytes: int = MAX_FILING_BYTES,
        clock: Callable[[], datetime] = _now,
        run_id: str | None = None,
    ) -> None:
        values = issuer_ciks if issuer_ciks is not None else ciks
        if values is None:
            raise ValueError("issuer_ciks is required")
        normalized = sorted({_as_cik(value) for value in values})
        if not normalized:
            raise ValueError("issuer_ciks must not be empty")
        user_agent = validate_sec_user_agent(user_agent or "")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if max_submissions_bytes < 1 or max_filing_bytes < 1:
            raise ValueError("SEC response size limits must be positive")
        self.issuer_ciks = tuple(normalized)
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.client = client
        self.pacer = pacer or _SEC_PACER
        self.sleeper = sleeper
        self.max_attempts = max_attempts
        self.max_submissions_bytes = max_submissions_bytes
        self.max_filing_bytes = max_filing_bytes
        self.clock = clock
        self.run_id = run_id
        self._records: dict[str, SecRawRecord] = {}
        self._submissions: dict[str, tuple[bytes, str, str]] = {}
        self._last_check: datetime | None = None
        self._latest: datetime | None = None
        self._available = False
        self._message = "not checked"
        self._quota_state = "unknown"
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def submissions_urls(self) -> tuple[str, ...]:
        return tuple(SEC_SUBMISSIONS_URL.format(cik=cik) for cik in self.issuer_ciks)

    def _cache_path(self, kind: str, key: str, suffix: str) -> Path | None:
        if self.cache_dir is None:
            return None
        safe = key.replace("/", "_").replace("\\", "_")
        return self.cache_dir / kind / f"{safe}{suffix}"

    def _request(
        self,
        url: str,
        accept: str,
        *,
        accepted_content_types: frozenset[str],
        max_bytes: int,
    ) -> tuple[bytes, Mapping[str, str], int]:
        if self.client is None:
            self.client = httpx.Client(timeout=60.0)
        try:
            _validate_sec_url(url)
        except ValueError as exc:
            raise SECRequestError(str(exc), 400) from exc
        headers = {"User-Agent": self.user_agent, "Accept": accept}
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self.pacer.wait()
            try:
                with _response_context(self.client, url, headers) as response:
                    try:
                        _validate_sec_response(
                            response,
                            url,
                            accepted_content_types=accepted_content_types,
                        )
                    except ValueError as exc:
                        raise SECRequestError(str(exc), 400) from exc
                    status = int(getattr(response, "status_code", 200))
                    response_headers = getattr(response, "headers", {})
                    if status == 429 or 500 <= status <= 599:
                        if attempt + 1 < self.max_attempts:
                            advised = _retry_after(response_headers)
                            delay = advised if advised is not None else min(2**attempt, 16)
                            self.sleeper(min(MAX_RETRY_DELAY_SECONDS, max(0.0, delay)))
                            continue
                    if status >= 400:
                        raise SECRequestError(f"SEC request returned HTTP {status}", status)
                    try:
                        body = _bounded_response_body(response, max_bytes)
                    except ValueError as exc:
                        raise SECRequestError(str(exc), 400) from exc
                    return body, response_headers, status
            except SECRequestError as exc:
                last_error = exc
                if (
                    exc.status is not None
                    and exc.status >= 400
                    and not (exc.status == 429 or 500 <= exc.status <= 599)
                ):
                    raise
                if attempt + 1 >= self.max_attempts:
                    raise
            except (httpx.HTTPError, OSError, ValueError) as exc:
                last_error = exc
                if attempt + 1 >= self.max_attempts:
                    break
                self.sleeper(min(MAX_RETRY_DELAY_SECONDS, 2**attempt))
        raise SECRequestError(
            f"SEC request failed after {self.max_attempts} attempts"
        ) from last_error

    def _read_submissions(self, cik: str) -> tuple[dict[str, Any] | None, list[QuarantineRecord]]:
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        try:
            body, _, _ = self._request(
                url,
                "application/json",
                accepted_content_types=_JSON_CONTENT_TYPES,
                max_bytes=self.max_submissions_bytes,
            )
        except SECRequestError as exc:
            self._available = False
            self._quota_state = "throttled" if exc.status == 429 else "error"
            self._message = str(exc)
            return None, [
                _quarantine("SEC_REQUEST_FAILED", str(exc), locator=url, run_id=self.run_id)
            ]
        digest = _hash(body)
        self._submissions[cik] = (body, digest, url)
        path = self._cache_path("submissions", cik, ".json")
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_bytes(body)
            os.replace(temp, path)
            meta = path.with_suffix(".manifest.json")
            mtemp = meta.with_suffix(meta.suffix + ".tmp")
            mtemp.write_text(
                json.dumps({"url": url, "content_hash": digest}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(mtemp, meta)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, [
                _quarantine(
                    "SEC_SUBMISSIONS_JSON", f"invalid JSON: {exc}", locator=url, run_id=self.run_id
                )
            ]
        if not isinstance(decoded, dict):
            return None, [
                _quarantine(
                    "SEC_SUBMISSIONS_SCHEMA",
                    "submissions payload must be an object",
                    locator=url,
                    run_id=self.run_id,
                )
            ]
        return decoded, []

    def _records_from_payload(
        self, cik: str, payload: Mapping[str, Any], locator: str
    ) -> tuple[list[SecRawRecord], list[QuarantineRecord]]:
        filings = payload.get("filings")
        if not isinstance(filings, dict):
            return [], [
                _quarantine(
                    "SEC_SUBMISSIONS_SCHEMA",
                    "filings must be an object",
                    locator=locator,
                    run_id=self.run_id,
                )
            ]
        recent = filings.get("recent")
        if not isinstance(recent, dict):
            return [], [
                _quarantine(
                    "SEC_SUBMISSIONS_SCHEMA",
                    "filings.recent must be an object",
                    locator=locator,
                    run_id=self.run_id,
                )
            ]
        required = ("accessionNumber", "form", "acceptanceDateTime", "primaryDocument")
        arrays: dict[str, list[object]] = {}
        quarantines: list[QuarantineRecord] = []
        for name in required:
            value = recent.get(name)
            if not isinstance(value, list):
                quarantines.append(
                    _quarantine(
                        "SEC_SUBMISSIONS_ARRAY",
                        f"{name} must be an array",
                        locator=locator,
                        run_id=self.run_id,
                    )
                )
                continue
            arrays[name] = value
        if len(arrays) != len(required):
            return [], quarantines
        size = len(arrays[required[0]])
        if any(len(value) != size for value in arrays.values()):
            return [], quarantines + [
                _quarantine(
                    "SEC_SUBMISSIONS_ARRAY_MISMATCH",
                    "recent filing arrays have different lengths",
                    locator=locator,
                    run_id=self.run_id,
                )
            ]
        optional_arrays: dict[str, list[object] | None] = {}
        for name in ("filingDate", "reportDate"):
            value = recent.get(name)
            if value is not None and (not isinstance(value, list) or len(value) != size):
                quarantines.append(
                    _quarantine(
                        "SEC_SUBMISSIONS_ARRAY_MISMATCH",
                        f"{name} must match required array length",
                        locator=locator,
                        run_id=self.run_id,
                    )
                )
                optional_arrays[name] = None
            else:
                optional_arrays[name] = value
        if any(
            recent.get(name) is not None and optional_arrays[name] is None
            for name in ("filingDate", "reportDate")
        ):
            return [], quarantines
        body_hash = self._submissions.get(cik, (b"", "", ""))[1]
        records: list[SecRawRecord] = []
        for index in range(size):
            accession = arrays["accessionNumber"][index]
            form = arrays["form"][index]
            primary = arrays["primaryDocument"][index]
            try:
                if not isinstance(accession, str) or not _ACCESSION_RE.fullmatch(accession):
                    raise ValueError("accessionNumber has invalid SEC format")
                if not isinstance(form, str):
                    raise ValueError("form must be a string")
                form = form.upper()
                # Company submissions includes every SEC form.  Those outside
                # the ownership universe are intentionally not a source error.
                if form not in OWNERSHIP_FORMS:
                    continue
                if (
                    not isinstance(primary, str)
                    or not primary.strip()
                    or "/" in primary
                    or "\\" in primary
                    or primary in {".", ".."}
                ):
                    raise ValueError("primaryDocument is invalid")
                accepted = _parse_time(arrays["acceptanceDateTime"][index])
                filing_date = optional_arrays["filingDate"]
                report_date = optional_arrays["reportDate"]
                if (
                    isinstance(filing_date, list)
                    and filing_date[index] is not None
                    and not isinstance(filing_date[index], str)
                ):
                    raise ValueError("filingDate contains a non-string value")
                if (
                    isinstance(report_date, list)
                    and report_date[index] is not None
                    and not isinstance(report_date[index], str)
                ):
                    raise ValueError("reportDate contains a non-string value")
                filing_date_value = (
                    filing_date[index]
                    if isinstance(filing_date, list) and isinstance(filing_date[index], str)
                    else None
                )
                report_date_value = (
                    report_date[index]
                    if isinstance(report_date, list) and isinstance(report_date[index], str)
                    else None
                )
                issuer_path = cik.lstrip("0") or "0"
                compact = accession.replace("-", "")
                source_url = f"{SEC_ARCHIVES_URL}/{issuer_path}/{compact}/{primary}"
                records.append(
                    SecRawRecord(
                        provider="sec",
                        provider_record_id=accession,
                        issuer_cik=cik,
                        accession_number=accession,
                        form_type=form,
                        accepted_at=accepted,
                        source_url=source_url,
                        replay_locator=source_url,
                        retrieved_at=utc(self.clock()),
                        primary_document=primary,
                        filing_date=cast(str | None, filing_date_value),
                        report_date=cast(str | None, report_date_value),
                        provenance={
                            "submissions_url": locator,
                            "submissions_content_hash": body_hash,
                        },
                    )
                )
            except (TypeError, ValueError, OverflowError) as exc:
                row_key = accession if isinstance(accession, str) else None
                quarantines.append(
                    _quarantine(
                        "SEC_INVALID_FILING",
                        str(exc),
                        locator=locator,
                        row_key=row_key,
                        run_id=self.run_id,
                    )
                )
        return records, quarantines

    def fetch(
        self,
        cursor: str | None = None,
        through: datetime | date | str | None = None,
        *,
        since: datetime | date | str | None = None,
    ) -> SecPage:
        """List filings in deterministic order, filtered by availability time."""

        cursor_key = decode_cursor(cursor)
        lower = _as_instant(since)
        upper = _as_instant(through)
        all_records: list[SecRawRecord] = []
        quarantines: list[QuarantineRecord] = []
        checked = self.clock()
        for cik in self.issuer_ciks:
            url = SEC_SUBMISSIONS_URL.format(cik=cik)
            payload, bad = self._read_submissions(cik)
            quarantines.extend(bad)
            if payload is None:
                continue
            records, bad = self._records_from_payload(cik, payload, url)
            quarantines.extend(bad)
            all_records.extend(records)
        all_records.sort(key=_key)
        unique: dict[str, SecRawRecord] = {}
        for record in all_records:
            if lower is not None and record.accepted_at < lower:
                continue
            if upper is not None and record.accepted_at > upper:
                continue
            if cursor_key is not None and _key(record) <= cursor_key:
                continue
            unique[record.provider_record_id] = record
        selected = tuple(sorted(unique.values(), key=_key))
        for record in selected:
            self._records[record.provider_record_id] = record
        watermark = (
            selected[-1].accepted_at if selected else (cursor_key[0] if cursor_key else None)
        )
        next_cursor = (
            encode_cursor(
                selected[-1].accepted_at, selected[-1].accession_number, selected[-1].issuer_cik
            )
            if selected
            else cursor
        )
        self._last_check = utc(checked)
        self._available = not any(q.reason_code == "SEC_REQUEST_FAILED" for q in quarantines)
        self._quota_state = "ok" if self._available else self._quota_state
        self._message = "ok" if self._available else "one or more issuer requests failed"
        if all_records:
            self._latest = max(record.accepted_at for record in all_records)
        return SecPage(selected, next_cursor, watermark, tuple(quarantines))

    def iter_filings(
        self,
        cursor: str | datetime | date | None = None,
        through: datetime | date | str | None = None,
        *,
        since: datetime | date | str | None = None,
    ) -> Iterable[SecRawRecord]:
        # For convenience, an availability timestamp may be supplied as the
        # first positional argument when callers do not need a cursor.
        if isinstance(cursor, (datetime, date)):
            since = cursor
            cursor = None
        return iter(self.fetch(cursor, through, since=since).records)

    # Explicit names are useful to callers that distinguish listing from the
    # generic ADR ``fetch`` operation.
    def fetch_filings(
        self,
        since: datetime | date | str | None = None,
        through: datetime | date | str | None = None,
        cursor: str | None = None,
    ) -> SecPage:
        return self.fetch(cursor, through, since=since)

    def iter_incremental(
        self,
        since: datetime | date | str | None = None,
        through: datetime | date | str | None = None,
        cursor: str | None = None,
    ) -> Iterable[SecRawRecord]:
        return self.iter_filings(cursor, through, since=since)

    def historical_quarters(
        self, start_year: int, end_year: int | None = None
    ) -> list[tuple[int, int]]:
        from .historical import list_quarters

        return list_quarters(start_year, end_year)

    def get(self, provider_record_id: str) -> SecRawRecord | SecResult:
        """Fetch and cache a filing's primary XML."""

        record = self._records.get(provider_record_id)
        if record is None:
            return SecResult(SecOutcomeStatus.NOT_FOUND, message="unknown provider record id")
        if record.payload is not None and record.content_hash is not None:
            self._cache_hits += 1
            return record
        path = self._cache_path("filings", record.issuer_cik, f"/{record.accession_number}.xml")
        if path is not None and path.is_file():
            manifest = path.with_suffix(".manifest.json")
            cached_payload: bytes | None = None
            cached_retrieved_at: datetime | None = None
            cached_content_type: str | None = None
            if manifest.is_file():
                try:
                    if path.stat().st_size > self.max_filing_bytes:
                        raise ValueError("cached SEC filing exceeds configured size limit")
                    candidate = path.read_bytes()
                    digest = _hash(candidate)
                    value = json.loads(manifest.read_text(encoding="utf-8"))
                    if not isinstance(value, dict):
                        raise ValueError("SEC cache manifest must be an object")
                    retrieved_at = _parse_time(value.get("retrieved_at"))
                    content_type = str(value.get("content_type", ""))
                    media_type = content_type.split(";", 1)[0].strip().casefold()
                    valid_cache = (
                        value.get("content_hash") == digest
                        and value.get("url") == record.source_url
                        and value.get("provider") == record.provider
                        and value.get("provider_record_id") == record.provider_record_id
                        and media_type in _XML_CONTENT_TYPES
                    )
                    if valid_cache:
                        cached_payload = candidate
                        cached_retrieved_at = retrieved_at
                        cached_content_type = content_type
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    cached_payload = None
            if cached_payload is not None and cached_retrieved_at is not None:
                self._cache_hits += 1
                updated = self._with_payload(
                    record,
                    cached_payload,
                    content_type=cached_content_type,
                    retrieved_at=cached_retrieved_at,
                )
                self._records[provider_record_id] = updated
                return updated
        self._cache_misses += 1
        try:
            payload, response_headers, _ = self._request(
                record.source_url,
                "application/xml,text/xml",
                accepted_content_types=_XML_CONTENT_TYPES,
                max_bytes=self.max_filing_bytes,
            )
        except SECRequestError as exc:
            self._available = False
            self._quota_state = "throttled" if exc.status == 429 else "error"
            self._message = str(exc)
            if exc.status == 429:
                status = SecOutcomeStatus.THROTTLED
            elif exc.status == 404:
                status = SecOutcomeStatus.NOT_FOUND
            elif exc.status is not None and 400 <= exc.status < 500:
                status = SecOutcomeStatus.PERMANENT_INVALID
            else:
                status = SecOutcomeStatus.RETRYABLE
            return SecResult(status, message=str(exc))
        content_type = next(
            (
                str(value)
                for key, value in response_headers.items()
                if str(key).lower() == "content-type"
            ),
            record.content_type,
        )
        retrieved_at = utc(self.clock())
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_bytes(payload)
            os.replace(temp, path)
            manifest = path.with_suffix(".manifest.json")
            mtemp = manifest.with_suffix(manifest.suffix + ".tmp")
            mtemp.write_text(
                json.dumps(
                    {
                        "url": record.source_url,
                        "content_hash": _hash(payload),
                        "retrieved_at": retrieved_at.isoformat(),
                        "content_type": content_type,
                        "provider": record.provider,
                        "provider_record_id": record.provider_record_id,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(mtemp, manifest)
        updated = self._with_payload(
            record,
            payload,
            content_type=content_type,
            retrieved_at=retrieved_at,
        )
        self._available = True
        self._quota_state = "ok"
        self._last_check = updated.retrieved_at
        self._message = "ok"
        self._records[provider_record_id] = updated
        return updated

    @staticmethod
    def _with_payload(
        record: SecRawRecord,
        payload: bytes,
        *,
        content_type: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> SecRawRecord:
        return replace(
            record,
            payload=payload,
            content_hash=_hash(payload),
            content_type=content_type or record.content_type,
            retrieved_at=retrieved_at or record.retrieved_at,
        )

    def normalize(self, raw_record: SecRawRecord) -> ParseResult:
        if raw_record.payload is None:
            fetched = self.get(raw_record.provider_record_id)
            if not isinstance(fetched, SecRawRecord):
                return ParseResult(
                    quarantines=[
                        _quarantine(
                            "SEC_XML_NOT_AVAILABLE",
                            fetched.message,
                            row_key=raw_record.provider_record_id,
                            run_id=self.run_id,
                        )
                    ]
                )
            raw_record = fetched
        payload = raw_record.payload
        assert payload is not None
        return parse_sec_ownership_document(
            payload,
            {
                "provider": raw_record.provider,
                "provider_record_id": raw_record.provider_record_id,
                "accession_number": raw_record.accession_number,
                "form_type": raw_record.form_type,
                "source_url": raw_record.source_url,
                "accepted_at": raw_record.accepted_at,
                "observed_at": raw_record.retrieved_at,
                "recorded_at": raw_record.retrieved_at,
                "run_id": self.run_id,
            },
        )

    def health(self) -> SecProviderHealth:
        lag = None
        if self._latest is not None and self._last_check is not None:
            lag = max(0.0, (self._last_check - self._latest).total_seconds())
        return SecProviderHealth(
            provider=self.name,
            available=self._available,
            lag=lag,
            quota_state=self._quota_state,
            checked_at=self._last_check,
            message=self._message,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
        )


class SECIncrementalAdapter(SECIncrementalSource):
    """Compatibility name for applications that call sources adapters."""


class SECRequestError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(str(value))
            return max(0.0, (utc(when) - _now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


__all__ = [
    "OWNERSHIP_FORMS",
    "SECIncrementalAdapter",
    "SECIncrementalSource",
    "SECCompanySubmissionsSource",
    "SECRequestError",
    "SEC_SUBMISSIONS_URL",
    "IncrementalSECSource",
    "decode_cursor",
    "encode_cursor",
]

# Compatibility spellings used by integrations that prefer CamelCase SEC
# names.  They intentionally point to the same implementation and contracts.
IncrementalSECSource = SECIncrementalSource
SECCompanySubmissionsSource = SECIncrementalSource
