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


def research_history(
    checkpoints: Sequence[dict[str, Any]], *, expected_days: Sequence[date],
) -> ResearchHistory:
    expected = tuple(sorted(set(expected_days)))
    if len(expected) != len(expected_days):
        raise ValueError("duplicate SEC-day inventory")
    evidence: dict[date, DayEvidence] = {}
    rows: list[CanonicalTransaction] = []
    accession_days: dict[str, date] = {}
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
            if accession in accession_days and accession_days[accession] != day:
                raise ValueError("filing appears in conflicting SEC day inventories")
            accession_days[accession] = day
            if filing["quarantines"]:
                # A filer CIK can be an owner: only parsed issuer evidence is usable.
                quarantined_issuers.update(CanonicalTransaction.model_validate(row).issuer.cik
                                           for row in filing["records"])
        rows.extend(filing_rows)
    return ResearchHistory(tuple(_merge_records(rows)), expected,
                           tuple(evidence[day] for day in sorted(evidence)), accession_days,
                           frozenset(quarantined_issuers))
