"""Read verified SEC checkpoints as explicitly partial factual research inputs.

This does not weaken the sealed/backtest history contract or create a cursor.
Completeness evidence remains attached to every day, including zero-row days.
"""

from collections.abc import Sequence
from dataclasses import dataclass
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


def _filing_identity(filing: dict[str, Any]) -> tuple[Any, ...]:
    """Prove a repeated index entry is the same source filing and parse result."""
    return (
        filing["parserVersion"],
        filing["provenance"]["complete_submission_hash"],
        tuple(sorted(
            (
                row["transactionId"], row["revisionId"],
                row["source"]["sourceRowKey"], row["source"]["contentHash"],
            )
            for row in filing["records"]
        )),
        tuple(sorted(
            (row["reason_code"], row["source_row_key"])
            for row in filing["quarantines"]
        )),
    )


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
    for item in checkpoints:
        day = date.fromisoformat(item["day"])
        if day not in expected or day in evidence:
            raise ValueError("unexpected or duplicate SEC checkpoint day")
        checkpoint = validate_checkpoint(item, day=day)
        filing_rows = [CanonicalTransaction.model_validate(value)
                       for filing in checkpoint["filings"] for value in filing["records"]]
        quarantines = sum(len(filing["quarantines"]) for filing in checkpoint["filings"])
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
                if _filing_identity(previous[1]) != _filing_identity(filing):
                    raise ValueError("filing appears in conflicting SEC day inventories")
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
                           frozenset(quarantined_issuers))
