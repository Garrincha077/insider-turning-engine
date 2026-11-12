"""Bounded SEC financial reads with exact-byte cache and filing-acceptance joins.

Reuse the ownership adapter's identified/paced/allow-listed/bounded transport,
not its ownership parser or cursor. A corrupt cache is never a valid source.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .company_facts import CompanyFactsResult, normalize_company_facts
from .historical import RequestPacer
from .incremental import SECIncrementalSource

MAX_FINANCIAL_BYTES = 32 * 1024 * 1024
FINANCIAL_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A",
                             "20-F", "20-F/A", "40-F", "40-F/A"})


@dataclass(frozen=True)
class FinancialDocument:
    document: dict[str, Any]
    url: str
    sha256: str
    fetched_at: datetime
    cache_hit: bool


@dataclass(frozen=True)
class FinancialAcquisition:
    result: CompanyFactsResult
    sources: tuple[FinancialDocument, ...]
    acceptance_count: int
    archives_requested: int
    remaining_archives: int


def acceptance_index(documents: Sequence[Mapping[str, Any]]) -> dict[str, datetime]:
    """Accept official recent/archived arrays; reject conflicting or naive clocks."""
    result: dict[str, datetime] = {}
    for document in documents:
        filings = document.get("filings", {})
        if "filings" in document and not isinstance(filings, Mapping):
            raise ValueError("invalid SEC financial filing envelope")
        arrays = filings.get("recent", {}) if "filings" in document else document
        if not isinstance(arrays, Mapping):
            raise ValueError("invalid SEC financial acceptance arrays")
        accessions, forms, instants = (arrays.get(key, []) for key in
                                       ("accessionNumber", "form", "acceptanceDateTime"))
        if (not all(isinstance(values, list) for values in (accessions, forms, instants))
                or len({len(accessions), len(forms), len(instants)}) != 1):
            raise ValueError("misaligned SEC financial acceptance arrays")
        for accession, form, instant in zip(accessions, forms, instants, strict=True):
            if not isinstance(form, str):
                raise ValueError("invalid SEC financial form")
            if form not in FINANCIAL_FORMS:
                continue
            if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                raise ValueError("invalid SEC financial acceptance accession")
            if not isinstance(instant, str):
                raise ValueError("missing SEC financial acceptance timestamp")
            accepted = datetime.fromisoformat(instant)
            if accepted.tzinfo is None:
                raise ValueError("naive SEC financial acceptance timestamp")
            accepted = accepted.astimezone(UTC)
            if accession in result and result[accession] != accepted:
                raise ValueError("conflicting SEC financial acceptance timestamps")
            result[accession] = accepted
    return dict(sorted(result.items()))


class SECFinancialSource:
    """Current company facts plus at most three explicit acceptance archives.

    Recent submissions expire in six hours. Facts can reuse seven-day cache only
    if it already contains the newest relevant filing; a new filing forces a
    refresh. Source versions/hashes stay visible for later historical auditing.
    """

    def __init__(
        self, user_agent: str, *, cache_dir: Path, client: httpx.Client | None = None,
        pacer: RequestPacer | None = None, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self._owns_client = client is None
        self.cache_dir = cache_dir
        self.clock = clock or (lambda: datetime.now(UTC))
        self.user_agent, self.pacer = user_agent, pacer

    def _read(
        self, transport: SECIncrementalSource, cik: str, url: str, name: str,
        ttl: timedelta, *, required_accession: str | None = None,
    ) -> FinancialDocument:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("financial retrieval clock must be timezone-aware")
        path = self.cache_dir / cik / f"{name}.json"
        try:
            if path.is_symlink() or path.stat().st_size > 2 * MAX_FINANCIAL_BYTES:
                raise ValueError("unsafe financial cache")
            envelope = json.loads(path.read_bytes())
            body = base64.b64decode(envelope["payload"], validate=True)
            fetched = datetime.fromisoformat(envelope["fetchedAt"])
            digest = hashlib.sha256(body).hexdigest()
            if (envelope["schemaVersion"] != "1.0.0" or envelope["issuerCik"] != cik
                    or envelope["url"] != url or envelope["sha256"] != digest
                    or len(body) > MAX_FINANCIAL_BYTES or envelope["size"] != len(body)
                    or fetched.tzinfo is None or not timedelta(0) <= now - fetched < ttl):
                raise ValueError("invalid financial cache evidence")
            document = json.loads(body)
            if not isinstance(document, dict):
                raise ValueError("invalid financial document")
            if name in {"submissions", "companyfacts"} \
                    and str(document.get("cik")).zfill(10) != cik:
                raise ValueError("financial cache issuer mismatch")
            if required_accession is not None and required_accession.encode() not in body:
                raise ValueError("new financial filing requires fresh Company Facts")
            return FinancialDocument(document, url, digest, fetched, True)
        except (OSError, KeyError, TypeError, ValueError):
            pass
        body, _, _ = transport._request(url, "application/json",
            accepted_content_types=frozenset({"application/json"}), max_bytes=MAX_FINANCIAL_BYTES)
        document = json.loads(body)
        if not isinstance(document, dict):
            raise ValueError("invalid financial document")
        if name in {"submissions", "companyfacts"} \
                and str(document.get("cik")).zfill(10) != cik:
            raise ValueError("financial source issuer mismatch")
        digest = hashlib.sha256(body).hexdigest()
        fetched = self.clock()
        if fetched.tzinfo is None:
            raise ValueError("financial retrieval clock must be timezone-aware")
        envelope = {"schemaVersion": "1.0.0", "issuerCik": cik, "url": url,
                    "sha256": digest, "size": len(body), "fetchedAt": fetched.isoformat(),
                    "payload": base64.b64encode(body).decode("ascii")}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".financial-", delete=False) as stream:
                temporary = stream.name
                json.dump(envelope, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        return FinancialDocument(document, url, digest, fetched, False)

    def fetch(
        self, issuer_cik: str, *, as_of: datetime, concepts: Mapping[str, Sequence[str]],
        max_archives: int = 2,
    ) -> FinancialAcquisition:
        if not re.fullmatch(r"\d{10}", issuer_cik) or not 0 <= max_archives <= 3:
            raise ValueError("invalid financial CIK or archive bound")
        if as_of.tzinfo is None:
            raise ValueError("financial as_of must be timezone-aware")
        transport = SECIncrementalSource([issuer_cik], user_agent=self.user_agent,
            client=self.client, pacer=self.pacer, max_attempts=2)
        root = "https://data.sec.gov/"
        recent = self._read(transport, issuer_cik, f"{root}submissions/CIK{issuer_cik}.json",
                            "submissions", timedelta(hours=6))
        if str(recent.document.get("cik")).zfill(10) != issuer_cik:
            raise ValueError("SEC submissions issuer mismatch")
        accepted = acceptance_index([recent.document])
        newest = max((key for key in accepted if accepted[key] <= as_of),
                     key=lambda key: (accepted[key], key), default=None)
        facts = self._read(transport, issuer_cik,
            f"{root}api/xbrl/companyfacts/CIK{issuer_cik}.json", "companyfacts",
            timedelta(days=7), required_accession=newest)
        if str(facts.document.get("cik")).zfill(10) != issuer_cik:
            raise ValueError("SEC Company Facts issuer mismatch")
        archives = recent.document.get("filings", {}).get("files", [])
        if not isinstance(archives, list):
            raise ValueError("invalid SEC submissions archive inventory")
        names: dict[str, date] = {}
        for row in archives:
            name = row.get("name") if isinstance(row, dict) else None
            if not isinstance(name, str) or not re.fullmatch(
                    rf"CIK{issuer_cik}-submissions-\d{{3}}\.json", name):
                raise ValueError("unsafe SEC submissions archive name")
            if name in names:
                raise ValueError("duplicate SEC submissions archive")
            try:
                names[name] = date.fromisoformat(row["filingTo"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("invalid SEC submissions archive date") from None
        sources = [recent, facts]
        selected_archives = sorted(names, key=lambda name: (names[name], name), reverse=True)
        for name in selected_archives[:max_archives]:
            sources.append(self._read(transport, issuer_cik, f"{root}submissions/{name}",
                                      name.removesuffix(".json"), timedelta(days=7)))
        accepted = acceptance_index([recent.document, *(row.document for row in sources[2:])])
        result = normalize_company_facts(facts.document, issuer_cik=issuer_cik,
            acceptance_by_accession=accepted, as_of=as_of, concepts=concepts)
        return FinancialAcquisition(result, tuple(sources), len(accepted),
                                    min(max_archives, len(names)),
                                    max(0, len(names) - max_archives))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> SECFinancialSource:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
