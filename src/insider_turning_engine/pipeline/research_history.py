"""Read verified SEC checkpoints as explicitly partial factual research inputs.

This does not weaken the sealed/backtest history contract or create a cursor.
Completeness evidence remains attached to every day, including zero-row days.
"""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.domain.research import DayEvidence
from insider_turning_engine.ingestion.sec.checkpoint import validate_checkpoint
from insider_turning_engine.pipeline.live_inputs import _merge_records


@dataclass(frozen=True)
class ResearchHistory:
    records: tuple[CanonicalTransaction, ...]
    expected_days: tuple[date, ...]
    evidence: tuple[DayEvidence, ...]
    sec_day_by_accession: dict[str, date]
    quarantined_issuers: frozenset[str] = frozenset()
    # Diagnostic-only reason counts, not scoring evidence or a cursor.
    quarantine_reason_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    # Same canonical XML/economics but different complete-submission transport bytes.
    # Not a failed source day, not a signal and not a cursor transition.
    transport_republication_days: tuple[tuple[date, date], ...] = ()


def _filing_identity(filing: dict[str, Any]) -> tuple[Any, ...]:
    """Prove a repeated index entry is the same source filing and parse result."""
    return (
        filing["provenance"]["complete_submission_hash"],
        tuple(sorted(
            (
                row["transactionId"], row["revisionId"],
                row["source"]["sourceRowKey"], row["source"]["contentHash"],
                json.dumps({field: row[field] for field in (
                    "issuer", "reportingOwner", "relationship", "security",
                    "transaction", "quality",
                )}, sort_keys=True, separators=(",", ":")),
            )
            for row in filing["records"]
        )),
        tuple(sorted(
            (row["reason_code"], row["source_row_key"])
            for row in filing["quarantines"]
        )),
    )



def _same_canonical_source_except_submission_transport(
    previous: dict[str, Any], current: dict[str, Any],
    old_identity: tuple[Any, ...], new_identity: tuple[Any, ...],
) -> bool:
    """Accept a republished accession only if the parsed source is *identical*.

    SEC may repack a complete submission (header / container bytes) without
    changing its primary ownership XML. Source content hashes, all canonical
    economics/owner/quality fields, quarantines and primary-document locations
    must still match. Never use this exception for changed facts or parser
    versions, and never revise the first-observed point-in-time attribution.
    """
    if (old_identity[0] == new_identity[0]
            or old_identity[1:] != new_identity[1:]
            or previous["parserVersion"] != current["parserVersion"]
            or previous["provenance"]["filer_cik"] != current["provenance"]["filer_cik"]):
        return False

    def source_urls(filing: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(
            (row["source"]["sourceRowKey"], row["source"]["sourceUrl"])
            for row in filing["records"]
        ))

    return source_urls(previous) == source_urls(current)


def research_history(
    checkpoints: Sequence[dict[str, Any]], *, expected_days: Sequence[date],
) -> ResearchHistory:
    expected = tuple(sorted(set(expected_days)))
    if len(expected) != len(expected_days):
        raise ValueError("duplicate SEC-day inventory")
    evidence: dict[date, DayEvidence] = {}
    rows: list[CanonicalTransaction] = []
    accession_days: dict[str, date] = {}
    selected_filings: dict[str, tuple[date, dict[str, Any], list[CanonicalTransaction]]] = {}
    quarantined_issuers: set[str] = set()
    quarantine_reason_counts: dict[str, dict[str, int]] = {}
    transport_republication_days: list[tuple[date, date]] = []
    for item in checkpoints:
        day = date.fromisoformat(item["day"])
        if day not in expected or day in evidence:
            raise ValueError("unexpected or duplicate SEC checkpoint day")
        checkpoint = validate_checkpoint(item, day=day)
        filing_rows = [CanonicalTransaction.model_validate(value)
                       for filing in checkpoint["filings"] for value in filing["records"]]
        quarantines = sum(len(filing["quarantines"]) for filing in checkpoint["filings"])
        # Preserve source-reported parser reason codes without exposing free text,
        # accession IDs, owner identities or raw SEC payloads in diagnostics.
        reason_counts = Counter(
            reason if isinstance(reason, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason)
            else "UNRECOGNIZED_REASON_CODE"
            for filing in checkpoint["filings"]
            for quarantine in filing["quarantines"]
            for reason in [quarantine["reason_code"]]
        )
        if reason_counts:
            quarantine_reason_counts[day.isoformat()] = dict(sorted(reason_counts.items()))
        failures = len(checkpoint["failures"])
        discovered = len(checkpoint["discoveredAccessions"])
        stored = len(checkpoint["filings"])
        evidence[day] = DayEvidence(
            day=day, discovered_filings=discovered, stored_filings=stored,
            parse_rows=len(filing_rows), quarantined_rows=quarantines, failures=failures,
            complete=discovered == stored and failures == 0 and quarantines == 0,
        )
        for filing in checkpoint["filings"]:
            accession = str(filing["accession"])
            typed = [CanonicalTransaction.model_validate(row) for row in filing["records"]]
            previous = selected_filings.get(accession)
            if previous is not None:
                prior_identity = _filing_identity(previous[1])
                current_identity = _filing_identity(filing)
                if prior_identity != current_identity:
                    if _same_canonical_source_except_submission_transport(
                        previous[1], filing, prior_identity, current_identity,
                    ):
                        # Explicit source-transport-only reconciliation. The
                        # earlier SEC day keeps PIT attribution; one economics
                        # inventory survives. Keep a sanitized audit count.
                        transport_republication_days.append((previous[0], day))
                    else:
                        components = ("submission_hash", "parsed_records", "quarantines")
                        differing = [name for name, old, new in zip(
                            components, prior_identity, current_identity, strict=True
                        ) if old != new]
                        if previous[1]["parserVersion"] != filing["parserVersion"]:
                            differing.append("parser_version")
                        if (previous[1]["provenance"]["filer_cik"]
                                != filing["provenance"]["filer_cik"]):
                            differing.append("filer_cik")
                        if (sorted(row["source"]["sourceUrl"] for row in previous[1]["records"])
                                != sorted(row["source"]["sourceUrl"]
                                          for row in filing["records"])):
                            differing.append("source_urls")
                        fingerprint = hashlib.sha256(accession.encode("utf-8")).hexdigest()[:12]
                        raise ValueError(
                            "filing appears in conflicting SEC day inventories"
                            f"; first_day={previous[0].isoformat()}"
                            f"; duplicate_day={day.isoformat()}"
                            f"; accession_sha256_prefix={fingerprint}"
                            f"; changed_components={','.join(differing)}"
                        )
                # SEC can republish an unchanged accession in a later master
                # index. Attribute it to the first observed index and count its
                # economics once; each day's acquisition evidence remains intact.
                if day >= previous[0]:
                    continue
            selected_filings[accession] = (day, filing, typed)
    for accession, (day, filing, typed) in selected_filings.items():
        accession_days[accession] = day
        if filing["quarantines"]:
            # A filer CIK can be an owner: only parsed issuer evidence is usable.
            quarantined_issuers.update(row.issuer.cik for row in typed)
        rows.extend(typed)
    return ResearchHistory(tuple(_merge_records(rows)), expected,
                           tuple(evidence[day] for day in sorted(evidence)), accession_days,
                           frozenset(quarantined_issuers), quarantine_reason_counts,
                           tuple(sorted(transport_republication_days)))
