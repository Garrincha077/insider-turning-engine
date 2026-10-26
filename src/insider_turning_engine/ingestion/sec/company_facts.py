"""Filing-linked SEC Company Facts, not latest-frame or date-only PIT inference.

Offline normalization deliberately requires exact acceptance evidence supplied
by a verified submissions/header adapter. It does not infer missing acceptance
from filing dates, fiscal years, XBRL frames or the API retrieval timestamp.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_TAXONOMIES = {"us-gaap", "ifrs-full", "dei"}
_UNITS = {"USD", "shares", "USD/shares", "pure"}


@dataclass(frozen=True)
class FinancialFact:
    issuer_cik: str
    taxonomy: str
    tag: str
    unit: str
    value: Decimal
    start: date | None
    end: date
    accession: str
    accepted_at: datetime
    filed: date
    form: str
    source_url: str


@dataclass(frozen=True)
class FactIssue:
    code: str
    concept: str
    accession: str | None


@dataclass(frozen=True)
class CompanyFactsResult:
    facts: tuple[FinancialFact, ...]
    issues: tuple[FactIssue, ...]
    blocked_contexts: tuple[FinancialFact, ...] = ()


@dataclass(frozen=True)
class FactSelection:
    fact: FinancialFact | None
    reason: Literal["AVAILABLE", "MISSING_FINANCIAL_FACT", "CONFLICTING_FINANCIAL_FACTS"]


def _instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("financial evidence timestamps must be timezone-aware")
    return value.astimezone(UTC)


def normalize_company_facts(
    document: Mapping[str, Any], *, issuer_cik: str,
    acceptance_by_accession: Mapping[str, datetime], as_of: datetime,
    concepts: Mapping[str, Sequence[str]],
) -> CompanyFactsResult:
    """Keep only requested concepts with verified filing clocks and finite units.

    Later filings (including restatements) are discarded before row selection.
    Missing acceptance evidence is explicit quarantine, never a fabricated clock.
    Conflicting values within the same filing/context are entirely withheld.
    """
    cutoff = _instant(as_of)
    if not re.fullmatch(r"\d{10}", issuer_cik) or str(document.get("cik")).zfill(10) != issuer_cik:
        raise ValueError("Company Facts issuer does not match requested CIK")
    root = document.get("facts")
    if not isinstance(root, Mapping):
        raise ValueError("Company Facts envelope is missing facts")
    found: dict[tuple[str, str, str, date | None, date, str], FinancialFact] = {}
    conflicts: set[tuple[str, str, str, date | None, date, str]] = set()
    issues: set[FactIssue] = set()
    for taxonomy, tags in sorted(concepts.items()):
        if taxonomy not in _TAXONOMIES:
            raise ValueError("unsupported financial taxonomy")
        group = root.get(taxonomy, {})
        if not isinstance(group, Mapping):
            raise ValueError("invalid Company Facts taxonomy")
        for tag in sorted(set(tags)):
            concept = f"{taxonomy}:{tag}"
            body = group.get(tag, {})
            units = body.get("units", {}) if isinstance(body, Mapping) else {}
            if not isinstance(units, Mapping):
                issues.add(FactIssue("INVALID_FINANCIAL_UNITS", concept, None))
                continue
            for unit, rows in units.items():
                if unit not in _UNITS or not isinstance(rows, list):
                    issues.add(FactIssue("UNSUPPORTED_FINANCIAL_UNIT", concept, None))
                    continue
                for row in rows:
                    accession = row.get("accn") if isinstance(row, Mapping) else None
                    if not isinstance(accession, str) or not _ACCESSION.fullmatch(accession):
                        issues.add(FactIssue("INVALID_FINANCIAL_ACCESSION", concept, None))
                        continue
                    accepted = acceptance_by_accession.get(accession)
                    if accepted is None:
                        issues.add(FactIssue("FINANCIAL_ACCEPTANCE_MISSING", concept, accession))
                        continue
                    accepted = _instant(accepted)
                    if accepted > cutoff:
                        continue
                    try:
                        form = row["form"]
                        if form not in _FORMS or isinstance(row["val"], bool):
                            raise ValueError("invalid form or boolean amount")
                        value = Decimal(str(row["val"]))
                        start = date.fromisoformat(row["start"]) if row.get("start") else None
                        end = date.fromisoformat(row["end"])
                        filed = date.fromisoformat(row["filed"])
                        if (not value.is_finite() or end > cutoff.date()
                                or start is not None and start > end
                                or filed != accepted.astimezone(ZoneInfo("America/New_York")).date()
                                or end > filed):
                            raise ValueError("invalid period, value or filing clock")
                    except (KeyError, TypeError, ValueError, InvalidOperation):
                        issues.add(FactIssue("INVALID_FINANCIAL_FACT", concept, accession))
                        continue
                    key = (taxonomy, tag, unit, start, end, accession)
                    fact = FinancialFact(issuer_cik, taxonomy, tag, unit, value, start, end,
                        accession, accepted, filed, form,
                        f"https://www.sec.gov/Archives/edgar/data/{int(issuer_cik)}/"
                        f"{accession.replace('-', '')}/")
                    previous = found.get(key)
                    if previous is not None and previous != fact:
                        conflicts.add(key)
                        issues.add(FactIssue("CONFLICTING_FINANCIAL_FACTS", concept, accession))
                        # Stable representative for the blocked context only;
                        # neither value can enter a financial calculation.
                        fact = min((previous, fact), key=lambda row: (row.value, row.form))
                    found[key] = fact
    ordered = sorted((row for key, row in found.items() if key not in conflicts),
                     key=lambda row: (row.taxonomy, row.tag, row.unit, row.end,
                                      row.start or date.min, row.accepted_at, row.accession))
    blocked = sorted((found[key] for key in conflicts),
                     key=lambda row: (row.taxonomy, row.tag, row.unit, row.end,
                                      row.start or date.min, row.accepted_at, row.accession))
    return CompanyFactsResult(tuple(ordered), tuple(sorted(issues,
        key=lambda issue: (issue.code, issue.concept, issue.accession or ""))), tuple(blocked))


def select_financial_fact(
    result: CompanyFactsResult, *, taxonomy: str, tag: str, unit: str,
    as_of: datetime, kind: Literal["instant", "annual", "quarter"],
    start: date | None = None, end: date | None = None,
) -> FactSelection:
    """Latest available period, then latest accepted filing for that exact period.

    Annual/quarter durations are explicit, not fiscal-year labels or XBRL frames;
    53-week annual statements are supported. YTD is never mistaken for a quarter.
    This selector does not manufacture TTM figures from incomplete periods.
    """
    cutoff = _instant(as_of)
    if kind not in {"instant", "annual", "quarter"}:
        raise ValueError("unknown financial period kind")
    rows: list[FinancialFact] = []
    for fact in (*result.facts, *result.blocked_contexts):
        if (_instant(fact.accepted_at) > cutoff or fact.end > cutoff.date()
                or (fact.taxonomy, fact.tag, fact.unit) != (taxonomy, tag, unit)
                or start is not None and fact.start != start
                or end is not None and fact.end != end):
            continue
        days = (fact.end - fact.start).days + 1 if fact.start is not None else None
        eligible = (days is None if kind == "instant" else
                    days is not None and (350 <= days <= 380 if kind == "annual"
                                          else 70 <= days <= 110))
        if eligible:
            rows.append(fact)
    if not rows:
        return FactSelection(None, "MISSING_FINANCIAL_FACT")
    newest = max(row.end for row in rows)
    latest = max(row.accepted_at for row in rows if row.end == newest)
    candidates = [row for row in rows if row.end == newest and row.accepted_at == latest]
    if (any(row in result.blocked_contexts for row in candidates)
            or len({(row.value, row.start, row.end) for row in candidates}) != 1):
        return FactSelection(None, "CONFLICTING_FINANCIAL_FACTS")
    return FactSelection(min(candidates, key=lambda row: row.accession), "AVAILABLE")
