"""Current SEC identity observations, never a backfilled security master.

Each requested issuer produces an observation, including unresolved tombstones.
This prevents a failed refresh or delisting from silently reusing an old mapping.
Common-stock eligibility still requires independent ownership-filing evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from insider_turning_engine.ingestion.sec.identity import (
    COMPANY_TICKERS_EXCHANGE_URL,
    CompanyTickerIdentity,
    SECCompanyTickerSource,
)
from insider_turning_engine.ingestion.sec.incremental import (
    SEC_SUBMISSIONS_URL,
    SECIncrementalSource,
)
from insider_turning_engine.normalization.identity import (
    DEFAULT_SIC_MAPPING_PATH,
    evaluate_security_universe,
    map_sic_to_sector_etf,
    normalize_ticker,
)

_US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
LIVE_SIC_MAPPING_PATH = DEFAULT_SIC_MAPPING_PATH.with_name("sic-sector.v1.1.yaml")


def _cik(value: object) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,10}", text) or int(text) == 0:
        raise ValueError("identity requires a positive numeric CIK")
    return text.zfill(10)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("identity observation requires a timezone")
    return value.astimezone(UTC)


def _json(value: Any) -> bytes:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode()


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def identity_observation(
    cik: str, listings: Iterable[CompanyTickerIdentity], *,
    metadata: bytes | None, observed_at: datetime, map_observed_at: datetime,
    map_hash: str, run_id: str,
) -> dict[str, Any]:
    """Reconcile two official current sources without guessing ticker-array alignment."""
    cik = _cik(cik)
    observed = max(_utc(observed_at), _utc(map_observed_at))
    matches = [row for row in listings if row.cik == cik]
    row: dict[str, Any] = {
        "schema_version": "1.0.0", "source": "sec-current-identity",
        "run_id": run_id, "cik": cik, "knowledge_at": observed.isoformat(),
        "ingested_at": observed.isoformat(), "valid_from": observed.date().isoformat(),
        "valid_to": None, "identity_status": "UNRESOLVED", "ticker": None,
        "current_mapping": True, "survivorship_caveat": True,
        "quality_flags": ["CURRENT_MAPPING_ONLY", "COMMON_STOCK_EVIDENCE_REQUIRED"],
        "provenance": {
            "exchange_url": COMPANY_TICKERS_EXCHANGE_URL, "exchange_hash": map_hash,
            "exchange_observed_at": _utc(map_observed_at).isoformat(),
            "metadata_url": SEC_SUBMISSIONS_URL.format(cik=cik),
            "metadata_hash": _digest(metadata) if metadata is not None else None,
            "metadata_observed_at": _utc(observed_at).isoformat(),
            "sector_mapping_hash": _digest(LIVE_SIC_MAPPING_PATH.read_bytes()),
        },
    }
    reason = None
    if metadata is None:
        reason = "METADATA_FETCH_FAILED"
    else:
        try:
            profile = json.loads(metadata)
            if not isinstance(profile, dict) or _cik(profile.get("cik")) != cik:
                raise ValueError("metadata CIK mismatch")
            if not isinstance(profile.get("name"), str) or not profile["name"].strip():
                raise ValueError("metadata name missing")
            row["name"] = profile["name"].strip()
            if profile.get("entityType") != "operating":
                reason = "NOT_OPERATING_ENTITY"
            elif profile.get("stateOfIncorporation") not in _US_STATES:
                reason = "US_INCORPORATION_UNCONFIRMED"
            elif not re.fullmatch(r"\d{4}", str(profile.get("sic", ""))):
                reason = "MISSING_SIC"
            elif len({(item.ticker, item.exchange.upper()) for item in matches}) != 1:
                reason = "AMBIGUOUS_LISTING" if matches else "NO_CURRENT_LISTING"
            else:
                ticker, exchange = matches[0].ticker, matches[0].exchange.upper()
                tickers, exchanges = profile.get("tickers"), profile.get("exchanges")
                # No arbitrary pairing of independent multi-valued arrays.
                if (not isinstance(tickers, list) or not isinstance(exchanges, list)
                    or any(not isinstance(value, str) for value in [*tickers, *exchanges])
                    or set(tickers) != {ticker}
                    or {value.upper() for value in exchanges} != {exchange}
                    or normalize_ticker(ticker) is None):
                    reason = "SOURCE_LISTING_DISAGREEMENT"
                else:
                    sector = map_sic_to_sector_etf(
                        profile["sic"], mapping_path=LIVE_SIC_MAPPING_PATH,
                    )
                    row.update(ticker=ticker, exchange=exchange, sic=profile["sic"],
                               country="US", sector_etf=sector.sector_etf)
                    row["provenance"]["sector_mapping_version"] = sector.mapping_version
                    row["provenance"]["country_evidence"] = profile["stateOfIncorporation"]
                    decision = evaluate_security_universe(row, as_of=observed)
                    if not decision.include:
                        reason = "EXCLUDED_UNIVERSE"
                        row["provenance"]["exclusion_reasons"] = decision.reason
                    elif sector.sector_etf == "UNKNOWN":
                        row["quality_flags"].append("SECTOR_UNMAPPED")
        except (ValueError, TypeError, KeyError):
            reason = "INVALID_COMPANY_METADATA"
    if reason:
        row["quality_flags"].append(reason)
        row["ticker"] = None
    else:
        row["identity_status"] = "RESOLVED"
    return row


def merge_observations(
    previous: Iterable[Mapping[str, Any]], current: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Append immutable observations; conflicting same-instant revisions are errors."""
    selected: dict[tuple[str, datetime], dict[str, Any]] = {}
    for item in [*previous, *current]:
        row = dict(item)
        cik = _cik(row.get("cik"))
        if (row.get("schema_version") != "1.0.0" or row.get("source") != "sec-current-identity"
            or row.get("identity_status") not in {"RESOLVED", "UNRESOLVED"}):
            raise ValueError("unsupported identity observation history")
        known = _utc(datetime.fromisoformat(str(row.get("knowledge_at"))))
        ingested = _utc(datetime.fromisoformat(str(row.get("ingested_at"))))
        if known < ingested:
            raise ValueError("identity knowledge time cannot precede observation")
        key = cik, known
        if key in selected and selected[key] != row:
            raise ValueError("conflicting identity observations at the same instant")
        selected[key] = row
    return [selected[key] for key in sorted(selected)]


def acquire_identity_observations(
    ciks: Iterable[str], *, user_agent: str, run_id: str, output: Path,
    previous: Path | None = None, client: httpx.Client | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Write a fresh local bundle atomically; no publication, cursor or alert writes.

    A fresh exchange map is required each run. Existing snapshots, rather than
    an indefinitely reused current-map cache, retain prior knowledge timestamps.
    """
    requested = sorted({_cik(value) for value in ciks})
    if not requested or len(requested) > 10000:
        raise ValueError("request between 1 and 10000 distinct issuer CIKs")
    if not re.fullmatch(r"run_[A-Za-z0-9_-]{8,64}", run_id):
        raise ValueError("invalid identity run_id")
    if output.exists():
        raise ValueError("use a fresh immutable identity output directory")
    previous_payload = previous.read_bytes() if previous is not None else None
    history = json.loads(previous_payload) if previous_payload is not None else []
    if not isinstance(history, list) or any(not isinstance(row, dict) for row in history):
        raise ValueError("previous identity history must be an array of observations")
    merge_observations(history, [])  # Validate before requests or filesystem writes.
    output.parent.mkdir(parents=True, exist_ok=True)
    http = client or httpx.Client(timeout=30.0, follow_redirects=False)
    try:
        with tempfile.TemporaryDirectory(prefix=".sec-identity-", dir=output.parent) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            raw = stage / "raw"
            raw.mkdir()
            source = SECCompanyTickerSource(user_agent, client=http, cache_dir=raw,
                                            clock=clock, filter_universe=False)
            mapping = source.fetch()
            if mapping.retrieved_at is None or mapping.content_hash is None:
                raise ValueError("exchange map observation evidence missing")
            profiles = SECIncrementalSource(requested, user_agent, client=http, clock=clock)
            observations = []
            for cik in requested:
                try:
                    payload, observed = profiles.fetch_company_metadata(cik)
                except (RuntimeError, ValueError, httpx.HTTPError):
                    payload, observed = None, _utc(clock())
                if payload is not None:
                    _write(raw / f"CIK{cik}.json", payload)
                observations.append(identity_observation(
                    cik, mapping.records, metadata=payload, observed_at=observed,
                    map_observed_at=mapping.retrieved_at, map_hash=mapping.content_hash,
                    run_id=run_id,
                ))
            content = _json(merge_observations(history, observations))
            _write(stage / "identities.json", content)
            resolved = sum(row["identity_status"] == "RESOLVED" for row in observations)
            report = {
                "schemaVersion": "1.0.0", "source": "sec-current-identity", "runId": run_id,
                "observedThrough": max(row["knowledge_at"] for row in observations),
                "status": "OBSERVED" if resolved == len(requested) else "PARTIAL",
                "requestedIssuerCount": len(requested), "resolvedIssuerCount": resolved,
                "unresolvedIssuerCount": len(requested) - resolved,
                "exchangeMapQuarantineCount": len(mapping.quarantines),
                "previousIdentityHash": _digest(previous_payload) if previous_payload else None,
                "artifacts": {"identities.json": _digest(content)},
                "unresolved": [{"cik": row["cik"], "reasons": row["quality_flags"][2:]}
                               for row in observations if row["identity_status"] != "RESOLVED"],
                "historicalIdentityComplete": False, "signalReady": False,
                "publishable": False, "alertsAllowed": False,
            }
            _write(stage / "identity-manifest.json", _json(report))
            os.rename(stage, output)
        return report
    finally:
        if client is None:
            http.close()
