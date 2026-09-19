"""Hydrate frozen B3 P/S supporting predecessors and zero-transaction amendments.

Research-only. Targets are fixed by the completed B3 P/S amendment-scope
inventory. Exact accession archive paths are derived only from frozen issuer
and reporting-owner CIK evidence. No fuzzy matching, market outcomes, current
identity mappings, or 2023+ evidence are permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC
from pathlib import Path
from typing import Any

from insider_turning_engine.ingestion.sec.daily_index import (
    MAX_CONFIGURABLE_SUBMISSION_BYTES,
    SECDailyIndexSource,
)
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing

import research_sec_hydrate as base
import research_sec_hydrate_with_fallback as fallback


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_all(root: Path, filename: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob(filename)):
        rows.extend(_read_jsonl(path))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _unique_index(
    rows: list[dict[str, Any]], *, label: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        accession = str(row.get("accession") or "")
        if not accession:
            raise ValueError(f"{label} row is missing accession")
        if accession in result:
            raise ValueError(f"duplicate {label} accession: {accession}")
        result[accession] = row
    return result


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    accession = str(row["accession"])
    issuer = str(row.get("issuerCik") or "").strip()
    if not issuer.isdigit() or len(issuer) > 10:
        raise ValueError(f"invalid issuer CIK for {accession}")
    filed = base._bulk_date(row["filingDate"])
    if not 2013 <= filed.year <= 2022:
        raise ValueError("hydration target is outside frozen 2013-2022 period")
    form = str(row.get("documentType") or "").upper()
    if form not in {"4", "5", "4/A", "5/A"}:
        raise ValueError(f"unsupported ownership form for {accession}")
    owners = row.get("reportingOwnerCiks") or []
    if not isinstance(owners, list):
        raise ValueError(f"reportingOwnerCiks must be a list for {accession}")
    return {
        **row,
        "accession": accession,
        "issuerCik": issuer.zfill(10),
        "documentType": form,
        "reportingOwnerCiks": [str(value).zfill(10) for value in owners],
        "_filed": filed,
    }


def _build_targets(
    *, scope_root: Path, catalog_root: Path, year: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 2013 <= year <= 2022:
        raise ValueError("target year must be within 2013-2022")

    supporting_scope = _read_all(scope_root, "supporting-predecessors.jsonl")
    scope_rows = _read_all(scope_root, "amendment-ps-scope.jsonl")
    predecessors = _unique_index(
        _read_all(catalog_root, "predecessor-catalog.jsonl"),
        label="predecessor catalog",
    )
    zero_catalog = _unique_index(
        _read_all(catalog_root, "zero-transaction-amendments.jsonl"),
        label="zero-transaction catalog",
    )

    supporting: list[dict[str, Any]] = []
    for target in supporting_scope:
        filing_date = base._bulk_date(target["rootFilingDate"])
        if filing_date.year != year:
            continue
        accession = str(target["rootPredecessorAccession"])
        evidence = predecessors.get(accession)
        if evidence is None:
            raise ValueError(f"missing predecessor catalog evidence for {accession}")
        candidate = _candidate(evidence)
        if candidate["issuerCik"] != str(target["issuerCik"]).zfill(10):
            raise ValueError(f"supporting predecessor issuer mismatch for {accession}")
        if candidate["_filed"] != filing_date:
            raise ValueError(f"supporting predecessor filing-date mismatch for {accession}")
        if candidate["documentType"] != str(target["rootForm"]).upper():
            raise ValueError(f"supporting predecessor form mismatch for {accession}")
        candidate["_evidenceKind"] = "SUPPORTING_PREDECESSOR"
        candidate["_supportingPredecessorOnly"] = True
        supporting.append(candidate)

    zero: list[dict[str, Any]] = []
    for target in scope_rows:
        if target.get("status") != "ZERO_TRANSACTION_AMENDMENT_ON_PS_ROOT":
            continue
        accession = str(target["amendmentAccession"])
        evidence = zero_catalog.get(accession)
        if evidence is None:
            continue
        candidate = _candidate(evidence)
        if candidate["_filed"].year != year:
            continue
        if candidate["documentType"] not in {"4/A", "5/A"}:
            raise ValueError(f"zero-transaction target is not an amendment: {accession}")
        if int(candidate.get("transactionCount", -1)) != 0:
            raise ValueError(f"zero-transaction catalog disagrees for {accession}")
        if candidate["issuerCik"] != str(target["issuerCik"]).zfill(10):
            raise ValueError(f"zero-transaction issuer mismatch for {accession}")
        candidate["_evidenceKind"] = "ZERO_TRANSACTION_AMENDMENT"
        candidate["_rootPredecessorAccession"] = target[
            "resolvedRootPredecessorAccession"
        ]
        zero.append(candidate)

    supporting.sort(key=lambda row: (row["_filed"], row["accession"]))
    zero.sort(key=lambda row: (row["_filed"], row["accession"]))
    return supporting, zero


def _clean_provenance(
    raw: Any, *, entry: Any, candidate: dict[str, Any]
) -> dict[str, Any]:
    clean = {
        key: value
        for key, value in raw.provenance.items()
        if key not in {"discovery", "daily_index_url", "daily_index_hash"}
    }
    clean.update(
        {
            "discovery": "verified_accession_archive_evidence",
            "archive_cik": entry.filer_cik,
            "archive_cik_basis": fallback._archive_cik_basis(entry, candidate),
            "submission_path_derived_from_verified_cik": True,
            "submission_maximum_bytes": MAX_CONFIGURABLE_SUBMISSION_BYTES,
            "candidate_filing_date": candidate["_filed"].isoformat(),
        }
    )
    return clean


def _parse_payload(raw: Any, accession: str) -> tuple[Any, bytes, int, str, str]:
    if raw.payload is None:
        raise ValueError("complete submission did not yield ownership XML")
    raw_hash = base._sha256(raw.payload)
    normalized, transforms = base.normalize_legacy_transaction_dates(raw.payload)
    normalized_hash = base._sha256(normalized)
    run_id = "run_b3_ps_evidence_" + hashlib.sha256(accession.encode()).hexdigest()[:20]
    parsed = parse_sec_filing(
        normalized,
        {
            "provider": "sec",
            "provider_record_id": raw.provider_record_id,
            "accession_number": raw.accession_number,
            "form_type": raw.form_type,
            "source_url": raw.source_url,
            "accepted_at": raw.accepted_at,
            "observed_at": raw.accepted_at,
            "recorded_at": raw.retrieved_at,
            "run_id": run_id,
        },
    )
    return parsed, normalized, transforms, raw_hash, normalized_hash


def _manifest(
    *,
    raw: Any,
    entry: Any,
    candidate: dict[str, Any],
    raw_hash: str,
    normalized_hash: str,
    transforms: int,
    canonical_count: int,
) -> dict[str, Any]:
    return {
        "accession": candidate["accession"],
        "evidenceKind": candidate["_evidenceKind"],
        "issuerCik": raw.issuer_cik,
        "formType": raw.form_type,
        "acceptedAt": raw.accepted_at.astimezone(UTC).isoformat(),
        "actualRetrievedAt": raw.retrieved_at.astimezone(UTC).isoformat(),
        "bulkFilingDate": candidate["_filed"].isoformat(),
        "sourceUrl": raw.source_url,
        "replayLocator": raw.replay_locator,
        "primaryDocument": raw.primary_document,
        "archiveCik": entry.filer_cik,
        "archiveCikBasis": fallback._archive_cik_basis(entry, candidate),
        "rawOwnershipXmlHash": raw_hash,
        "normalizedOwnershipXmlHash": normalized_hash,
        "legacyTransactionDateOffsetTransforms": transforms,
        "canonicalRecordCount": canonical_count,
        "provenance": _clean_provenance(raw, entry=entry, candidate=candidate),
    }


def hydrate_year(
    *,
    scope_root: Path,
    catalog_root: Path,
    output: Path,
    year: int,
    workers: int,
    user_agent: str,
) -> dict[str, Any]:
    if not 1 <= workers <= 6:
        raise ValueError("workers outside SEC research safety bounds")
    if not user_agent.strip():
        raise ValueError("SEC_USER_AGENT is required")

    supporting, zero = _build_targets(
        scope_root=scope_root,
        catalog_root=catalog_root,
        year=year,
    )
    targets = supporting + zero
    output.mkdir(parents=True, exist_ok=True)
    zero_xml = output / "zero-transaction-xml"
    zero_xml.mkdir(exist_ok=True)

    local = threading.local()
    sources: list[SECDailyIndexSource] = []
    sources_lock = threading.Lock()

    def worker_source() -> SECDailyIndexSource:
        source = getattr(local, "source", None)
        if source is None:
            source = SECDailyIndexSource(
                user_agent,
                cache_dir=output / "sec-cache",
                max_attempts=1,
                submission_maximum_bytes=MAX_CONFIGURABLE_SUBMISSION_BYTES,
            )
            local.source = source
            with sources_lock:
                sources.append(source)
        return source

    def hydrate_one(candidate: dict[str, Any]) -> dict[str, Any]:
        accession = str(candidate["accession"])
        try:
            raw, entry = fallback._fetch_verified_archive(
                candidate=candidate,
                source=worker_source(),
            )
            if raw.issuer_cik != candidate["issuerCik"]:
                raise ValueError("hydrated issuer CIK disagrees with frozen evidence")
            if raw.accepted_at.astimezone(UTC).year >= 2023:
                raise ValueError("sealed OOS boundary violated by 2023+ SEC acceptance")
            parsed, normalized, transforms, raw_hash, normalized_hash = _parse_payload(
                raw, accession
            )
            if parsed.quarantines:
                raise ValueError(
                    "ownership parser quarantine: "
                    + ",".join(item.reason_code for item in parsed.quarantines[:5])
                )

            records = list(parsed.records)
            if candidate["_evidenceKind"] == "ZERO_TRANSACTION_AMENDMENT":
                if records:
                    raise ValueError(
                        "zero-transaction amendment unexpectedly emitted canonical rows"
                    )
                xml_path = zero_xml / f"{accession}.xml"
                xml_path.write_bytes(normalized)
                return {
                    "ok": True,
                    "kind": candidate["_evidenceKind"],
                    "accession": accession,
                    "manifest": _manifest(
                        raw=raw,
                        entry=entry,
                        candidate=candidate,
                        raw_hash=raw_hash,
                        normalized_hash=normalized_hash,
                        transforms=transforms,
                        canonical_count=0,
                    )
                    | {
                        "rootPredecessorAccession": candidate[
                            "_rootPredecessorAccession"
                        ],
                        "xmlEvidencePath": f"zero-transaction-xml/{accession}.xml",
                        "zeroTransactionSemanticClassification": None,
                    },
                    "records": [],
                }

            dumped: list[dict[str, Any]] = []
            for record in records:
                if record.timestamps.accepted_at != raw.accepted_at:
                    raise ValueError("canonical accepted_at disagrees with raw evidence")
                if record.timestamps.knowledge_at != raw.accepted_at:
                    raise ValueError("historical knowledge_at does not equal accepted_at")
                if record.timestamps.recorded_at != raw.retrieved_at:
                    raise ValueError("canonical recorded_at lost retrieval time")
                item = record.canonical_dump()
                item["researchBackfill"] = {
                    "historicalAvailabilityBasis": "SEC_ACCEPTANCE_DATETIME",
                    "actualRetrievedAt": raw.retrieved_at.astimezone(UTC).isoformat(),
                    "bulkFilingDate": candidate["_filed"].isoformat(),
                    "rawOwnershipXmlHash": raw_hash,
                    "normalizedOwnershipXmlHash": normalized_hash,
                    "legacyTransactionDateOffsetTransforms": transforms,
                    "discoveryMethod": "VERIFIED_ACCESSION_ARCHIVE_EVIDENCE",
                    "archiveCik": entry.filer_cik,
                    "archiveCikBasis": fallback._archive_cik_basis(entry, candidate),
                    "supportingPredecessorOnly": True,
                    "canonicalReady": False,
                }
                dumped.append(item)
            return {
                "ok": True,
                "kind": candidate["_evidenceKind"],
                "accession": accession,
                "manifest": _manifest(
                    raw=raw,
                    entry=entry,
                    candidate=candidate,
                    raw_hash=raw_hash,
                    normalized_hash=normalized_hash,
                    transforms=transforms,
                    canonical_count=len(dumped),
                )
                | {"supportingPredecessorOnly": True},
                "records": dumped,
            }
        except (ET.ParseError, RuntimeError, ValueError, OSError, TypeError) as exc:
            return {
                "ok": False,
                "kind": candidate["_evidenceKind"],
                "accession": accession,
                "stage": "B3_PS_EVIDENCE_HYDRATION",
                "reason": type(exc).__name__,
                "message": str(exc)[:500],
            }

    results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(hydrate_one, row) for row in targets]
            for future in as_completed(futures):
                results.append(future.result())
    finally:
        for source in sources:
            source.close()

    good = sorted(
        (row for row in results if row["ok"]),
        key=lambda row: (row["kind"], row["accession"]),
    )
    bad = sorted(
        (row for row in results if not row["ok"]),
        key=lambda row: (row["kind"], row["accession"]),
    )
    supporting_good = [
        row for row in good if row["kind"] == "SUPPORTING_PREDECESSOR"
    ]
    zero_good = [
        row for row in good if row["kind"] == "ZERO_TRANSACTION_AMENDMENT"
    ]
    supporting_records = [
        item for row in supporting_good for item in row["records"]
    ]

    _write_jsonl(
        output / "supporting-predecessor-manifest.jsonl",
        [row["manifest"] for row in supporting_good],
    )
    _write_jsonl(
        output / "supporting-predecessor-canonical.jsonl",
        sorted(
            supporting_records,
            key=lambda row: (
                row["source"]["accessionNumber"],
                int(row["source"]["rowSequence"]),
                row["transactionId"],
            ),
        ),
    )
    _write_jsonl(
        output / "zero-transaction-manifest.jsonl",
        [row["manifest"] for row in zero_good],
    )
    _write_jsonl(output / "failures.jsonl", bad)

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 P/S amendment supporting evidence hydration",
        "year": year,
        "researchOnly": True,
        "supportingPredecessorTargets": len(supporting),
        "supportingPredecessorsHydrated": len(supporting_good),
        "supportingCanonicalRecordCount": len(supporting_records),
        "zeroTransactionAmendmentTargets": len(zero),
        "zeroTransactionAmendmentsHydrated": len(zero_good),
        "zeroTransactionXmlFiles": len(list(zero_xml.glob("*.xml"))),
        "failureCount": len(bad),
        "allSupportingKnowledgeEqualAccepted": all(
            row["timestamps"]["knowledgeAt"] == row["timestamps"]["acceptedAt"]
            for row in supporting_records
        ),
        "allAcceptedBefore2023": all(
            int(row["manifest"]["acceptedAt"][:4]) <= 2022 for row in good
        ),
        "supportingPredecessorHydrationComplete": (
            len(supporting_good) == len(supporting)
        ),
        "zeroTransactionHydrationComplete": len(zero_good) == len(zero),
        "zeroTransactionSemanticReviewComplete": False,
        "amendmentsReconciledForPsUniverse": False,
        "b3Eligible": False,
        "b3DefinitionFrozen": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "signalReady": False,
        "nextGate": (
            "classify zero-transaction amendment semantics and run deterministic "
            "P/S lifecycle reconciliation"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-root", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    summary = hydrate_year(
        scope_root=args.scope_root,
        catalog_root=args.catalog_root,
        output=args.output,
        year=args.year,
        workers=args.workers,
        user_agent=os.environ.get("SEC_USER_AGENT", ""),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if int(summary["failureCount"]) != 0:
        raise SystemExit("B3 P/S evidence hydration contains failures")


if __name__ == "__main__":
    main()
