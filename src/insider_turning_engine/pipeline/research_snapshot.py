"""Deterministic canonical-to-facts projection; no new score methodology."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction, TableType
from insider_turning_engine.domain.research import (
    BasisWindow,
    Cluster,
    DayEvidence,
    EconomicEvent,
    Owner,
    OwnerLink,
    Readiness,
    ResearchCompany,
    ResearchCoverage,
    ResearchReadiness,
    ResearchScore,
    ResearchSnapshot,
    SeriesPoint,
)
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.normalization.identity import _EXCLUDED_TEXT
from insider_turning_engine.pipeline.dashboard_input import _role
from insider_turning_engine.pipeline.live_inputs import _COMMON_STOCK


def _event_key(row: CanonicalTransaction) -> str:
    return "|".join((row.source.accession_number, row.security.table_type.value,
                     str(row.source.row_sequence)))


def _owner_locator(row: CanonicalTransaction) -> str:
    return "|".join((row.source.accession_number, row.reporting_owner.cik,
                     row.security.table_type.value, str(row.source.row_sequence)))


def _qualified(row: CanonicalTransaction) -> bool:
    tx = row.transaction
    return (row.security.table_type is TableType.NON_DERIVATIVE
            and (tx.code, tx.acquired_disposed) in {("P", "A"), ("S", "D")}
            and tx.shares is not None and tx.shares > 0 and tx.price_per_share is not None
            and tx.price_per_share > 0 and tx.value is not None)


def economic_events(
    records: Sequence[CanonicalTransaction], *, as_of: datetime,
) -> tuple[list[EconomicEvent], list[Owner], set[str], int]:
    """One SEC table row is one event, irrespective of reporting-owner count.

    Same facts in different accessions are never merged. Unlinked amendments
    stay inspectable but block issuer aggregates, not unrelated companies.
    Future observations are explicitly discarded BEFORE amendment resolution.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    available = [row for row in records if row.timestamps.accepted_at is not None
                and max(row.timestamps.knowledge_at, row.timestamps.recorded_at,
                        row.timestamps.accepted_at) <= as_of
                and row.transaction.transaction_date <= as_of.date()]
    unique: dict[tuple[str, str, str], CanonicalTransaction] = {}
    for row in sorted(available, key=lambda item: (item.timestamps.knowledge_at,
                                                  item.timestamps.recorded_at)):
        unique.setdefault((_event_key(row), row.reporting_owner.cik,
                           row.source.content_hash), row)
    eligible = list(unique.values())
    resolution = resolve_amendments(eligible, as_of=as_of)
    rejected = {row.locator for row in resolution.quarantines}
    unresolved = [row for row in eligible if _owner_locator(row) in rejected]
    blocked = {row.issuer.cik for row in unresolved}
    groups: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for row in [*resolution.effective_records, *unresolved]:
        groups[_event_key(row)].append(row)
    owners: dict[str, Owner] = {}
    events: list[EconomicEvent] = []
    for key, rows in sorted(groups.items()):
        rows.sort(key=lambda row: (row.timestamps.knowledge_at, row.reporting_owner.cik,
                                   row.revision_id))
        first = rows[0]
        # A source-row identity collision with conflicting economics is fatal.
        # Never resolve it by picking the larger amount or summing both versions.
        facts = {(row.issuer.cik, row.transaction.model_dump_json(),
                  row.security.model_dump_json(), row.timestamps.accepted_at) for row in rows}
        if len(facts) != 1:
            raise ValueError("conflicting economic event identity")
        links: dict[str, OwnerLink] = {}
        for row in rows:
            cik = row.reporting_owner.cik
            owners[cik] = Owner(owner_cik=cik, name=row.reporting_owner.name)
            links[cik] = OwnerLink(owner_cik=cik, role=_role(row))
        tx = first.transaction
        pending = any(_owner_locator(row) in rejected for row in rows)
        assert first.timestamps.accepted_at is not None
        events.append(EconomicEvent(
            event_id="evt_" + hashlib.sha256(key.encode()).hexdigest(),
            issuer_cik=first.issuer.cik, accession=first.source.accession_number,
            table=first.security.table_type.value, row_sequence=first.source.row_sequence,
            transaction_date=tx.transaction_date, accepted_at=first.timestamps.accepted_at,
            security_title=first.security.title,
            known_at=max(row.timestamps.knowledge_at for row in rows), code=tx.code,
            side="BUY" if tx.code == "P" else "SELL" if tx.code == "S" else "OTHER",
            shares=float(tx.shares) if tx.shares is not None else None,
            price=float(tx.price_per_share)
            if tx.price_per_share is not None else None,
            value=float(tx.value) if tx.value is not None else None,
            ownership="D" if tx.ownership_nature == "D" else "I",
            rule10b51=tx.rule_10b51.value,
            source_url=first.source.source_url, owners=[links[cik] for cik in sorted(links)],
            processing="UNRESOLVED_AMENDMENT" if pending else "EFFECTIVE",
            qualified=_qualified(first),
            aggregate_eligible=_qualified(first) and first.issuer.cik not in blocked,
        ))
    return events, [owners[cik] for cik in sorted(owners)], blocked, len(eligible)


def _basis(
    events: list[EconomicEvent], days: int, *, as_of: datetime, blocked: bool,
    expected: set[date], evidence: Mapping[date, DayEvidence],
) -> BasisWindow:
    start = as_of.date() - timedelta(days=days - 1)
    buys = [row for row in events if row.aggregate_eligible and row.side == "BUY"
            and start <= row.transaction_date <= as_of.date()]
    value = sum(row.value or 0 for row in buys)
    shares = sum(row.shares for row in buys if row.shares is not None)
    relevant = {day for day in expected if start <= day <= as_of.date()}
    complete = (bool(expected) and min(expected) <= start and bool(relevant)
                and all(day in evidence and evidence[day].complete for day in relevant))
    return BasisWindow(
        days=30 if days == 30 else 90, start=start, end=as_of.date(),
        weighted_basis=None if blocked or not shares else value / shares,
        purchase_value=None if blocked or not buys and not complete else value,
        purchase_count=None if blocked or not buys and not complete else len(buys),
        coverage="BLOCKED" if blocked else "OBSERVED_COMPLETE_SEC_WINDOW"
        if complete else "PARTIAL",
    )


def _clusters(events: list[EconomicEvent], *, as_of: datetime) -> list[Cluster]:
    grouped: dict[str, list[EconomicEvent]] = defaultdict(list)
    start = as_of.date() - timedelta(days=29)
    for row in events:
        if row.aggregate_eligible and row.side == "BUY" and row.transaction_date >= start:
            grouped[row.issuer_cik].append(row)
    result: list[Cluster] = []
    for cik, buys in sorted(grouped.items()):
        # Conservative independence: disjoint reporting-owner sets in distinct
        # filings. Two rows or two joint owners of the same filing do not qualify.
        independent = any(
            left.accession != right.accession
            and {link.owner_cik for link in left.owners}.isdisjoint(
                link.owner_cik for link in right.owners)
            for index, left in enumerate(buys) for right in buys[index + 1:]
        )
        if not independent:
            continue
        event_ids = sorted(row.event_id for row in buys)
        result.append(Cluster(
            cluster_id="clu_" + hashlib.sha256("|".join(event_ids).encode()).hexdigest(),
            issuer_cik=cik, start=min(row.transaction_date for row in buys),
            end=max(row.transaction_date for row in buys), event_ids=event_ids,
            owner_ciks=sorted({link.owner_cik for row in buys for link in row.owners}),
            purchase_value=sum(row.value or 0 for row in buys),
        ))
    return result


def build_research_snapshot(
    records: Sequence[CanonicalTransaction], *, as_of: datetime, run_id: str,
    identities: Mapping[str, Mapping[str, Any]],
    expected_sec_days: Sequence[date] = (), day_evidence: Sequence[DayEvidence] = (),
    candidate_rows: Sequence[Mapping[str, Any]] = (),
    company_series: Sequence[SeriesPoint] = (),
    sec_day_by_accession: Mapping[str, date] | None = None,
    quarantined_issuers: frozenset[str] = frozenset(),
) -> ResearchSnapshot:
    """Build facts from the entire input population, not a scored/buyer subset.

    Identity mappings must already be filtered point-in-time by the caller.
    No observations or SEC-day evidence are invented to complete a window.
    """
    as_of = as_of.astimezone(UTC) if as_of.tzinfo is not None else as_of
    events, owners, blocked, owner_rows = economic_events(records, as_of=as_of)
    for event in events:
        # The caller supplies only eligible, point-in-time common-stock identities.
        # A common-stock issuer may also file preferred/warrant transactions.
        event.aggregate_eligible = bool(event.aggregate_eligible
            and event.issuer_cik not in quarantined_issuers
            and identities.get(event.issuer_cik, {}).get("ticker")
            and _COMMON_STOCK.search(event.security_title)
            and not _EXCLUDED_TEXT.search(event.security_title))
        event.sec_day = (sec_day_by_accession or {}).get(event.accession)
    expected = set(expected_sec_days)
    evidence = {row.day: row for row in day_evidence}
    if (len(evidence) != len(day_evidence) or not set(evidence) <= expected
            or any(day > as_of.date() for day in expected)):
        raise ValueError("invalid SEC-day coverage evidence")
    candidates = {str(row["issuerCik"]): row for row in candidate_rows}
    if len(candidates) != len(candidate_rows) or any(
        row.get("sourceReferences", {}).get("runId") != run_id for row in candidate_rows
    ):
        raise ValueError("duplicate or mixed-run research scores")
    series = [row for row in company_series if row.date <= as_of.date()]
    prices = {row.issuer_cik: row.price for row in sorted(series, key=lambda item: item.date)}
    groups: dict[str, list[EconomicEvent]] = defaultdict(list)
    for row in events:
        groups[row.issuer_cik].append(row)
    names = {row.issuer.cik: row.issuer.name for row in sorted(
        records, key=lambda item: item.timestamps.knowledge_at)
        if max(row.timestamps.knowledge_at, row.timestamps.recorded_at) <= as_of
        and row.transaction.transaction_date <= as_of.date()}
    companies: list[ResearchCompany] = []
    scores: list[ResearchScore] = []
    for cik, issuer_events in sorted(groups.items()):
        identity = identities.get(cik, {})
        candidate = candidates.get(cik, {})
        for known_key in ("knowledge_at", "knownAt"):
            if identity.get(known_key) and datetime.fromisoformat(str(identity[known_key])) > as_of:
                raise ValueError("future identity observation")
        companies.append(ResearchCompany(
            issuer_cik=cik, ticker=identity.get("ticker"),
            name=str(identity.get("name") or names.get(cik) or cik),
            sector=identity.get("sector"),
            identity_status="RESOLVED" if identity.get("ticker") else "UNRESOLVED",
            insider_status="UNRESOLVED_AMENDMENT" if cik in blocked else
            "SOURCE_QUARANTINE" if cik in quarantined_issuers else "AVAILABLE",
            current_price=prices.get(cik, candidate.get("currentPrice")),
            basis=[_basis(issuer_events, days, as_of=as_of,
                          blocked=(cik in blocked | quarantined_issuers
                                   or not identity.get("ticker")),
                          expected=expected, evidence=evidence) for days in (30, 90)],
        ))
        # Legacy scores may include duplicated joint-owner dollar weights.
        # Retain factual events, but don't present those scores as recomputed v2.
        joint = any(len(row.owners) > 1 for row in issuer_events)
        score_block = (cik in blocked | quarantined_issuers or joint or not candidate
                       or not identity.get("ticker"))
        reasons = (["UNRESOLVED_AMENDMENT"] if cik in blocked else
                   ["SOURCE_QUARANTINE"] if cik in quarantined_issuers else
                   ["UNRESOLVED_IDENTITY"] if not identity.get("ticker") else
                   ["JOINT_OWNER_SCORE_NOT_RECOMPUTED"] if joint else
                   list(candidate.get("reasons", ["INSUFFICIENT_COMPONENT_DATA"])))
        references = candidate.get("sourceReferences", {})
        scores.append(ResearchScore(
            issuer_cik=cik, total=None if score_block else candidate.get("total"),
            insider=None if score_block else candidate.get("insider"),
            divergence=None if score_block else candidate.get("divergence"),
            turn=None if score_block else candidate.get("turn"),
            cluster=None if score_block else candidate.get("cluster"),
            market_rs=candidate.get("marketRs"), sector_rs=candidate.get("sectorRs"),
            state="UNKNOWN" if score_block else candidate.get("state", "UNKNOWN"),
            state_changed_at=candidate.get("stateChangedAt"), reasons=reasons,
            score_version="scoring.v1", methodology_hash=references.get("methodologyHash"),
            config_hash=references.get("configHash"), run_id=run_id, as_of=as_of,
        ))
    missing = sorted(expected - evidence.keys())
    incomplete = missing or any(not row.complete for row in day_evidence) or not expected
    return ResearchSnapshot(
        schema_version="2.1.0" if any(row.shares is None for row in events) else "2.0.0",
        run_id=run_id, as_of=as_of, score_version="scoring.v1", companies=companies,
        economic_transactions=events, reporting_owners=owners, research_scores=scores,
        clusters=_clusters(events, as_of=as_of), company_series=series,
        coverage=ResearchCoverage(
            scope="Observed SEC filings; not a census of the US market or complete 90D history",
            expected_sec_days=sorted(expected), days=sorted(day_evidence, key=lambda row: row.day),
            missing_sec_days=missing, canonical_owner_rows=owner_rows,
            economic_events=len(events), eligible_companies=len({row.issuer_cik
                for row in events if row.aggregate_eligible}),
            resolved_identities=sum(row.identity_status == "RESOLVED" for row in companies),
            priced_companies=sum(row.current_price is not None for row in companies),
            complete_scores=sum(row.total is not None for row in scores),
            unresolved_amendment_issuers=sorted(blocked),
            exclusions={"UNRESOLVED_IDENTITY": sum(row.identity_status == "UNRESOLVED"
                        for row in companies), "UNRESOLVED_AMENDMENT": len(blocked),
                        "SOURCE_QUARANTINE": len(quarantined_issuers),
                        "INELIGIBLE_OR_UNRESOLVED_EVENTS": sum(not row.aggregate_eligible
                                                               for row in events)},
        ),
        readiness=ResearchReadiness(
            dashboard=Readiness(status="PARTIAL" if incomplete or blocked else "READY",
                                reasons=["SEC_WINDOW_PARTIAL"] if incomplete else []),
            digest=Readiness(status="BLOCKED", reasons=["DIGEST_DELIVERY_CHECK_REQUIRED"]),
            predictive=Readiness(status="BLOCKED", reasons=["NOT_HISTORICALLY_VALIDATED"]),
        ),
    )
