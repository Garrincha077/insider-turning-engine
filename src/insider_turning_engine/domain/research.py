"""Public factual research v2 contract, independent of predictive readiness."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Cik = Annotated[str, Field(pattern=r"^\d{10}$")]
Amount = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class PublicModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid",
                              allow_inf_nan=False)


class Owner(PublicModel):
    owner_cik: Cik
    name: str


class OwnerLink(PublicModel):
    owner_cik: Cik
    role: str


class EconomicEvent(PublicModel):
    event_id: str
    issuer_cik: Cik
    accession: str
    table: Literal["NON_DERIVATIVE", "DERIVATIVE"]
    row_sequence: int = Field(ge=1)
    transaction_date: date
    sec_day: date | None = None
    security_title: str = ""
    accepted_at: datetime
    known_at: datetime
    code: str
    side: Literal["BUY", "SELL", "OTHER"]
    shares: Amount | None
    price: Amount | None
    value: Amount | None
    ownership: Literal["D", "I"]
    rule10b51: Literal["true", "false", "unknown"] = Field(alias="rule10b51")
    source_url: str = Field(pattern=r"^https://(?:www\.)?sec\.gov/")
    owners: list[OwnerLink] = Field(min_length=1)
    processing: Literal["EFFECTIVE", "UNRESOLVED_AMENDMENT"]
    qualified: bool
    aggregate_eligible: bool


class BasisWindow(PublicModel):
    days: Literal[30, 90]
    start: date
    end: date
    weighted_basis: Amount | None
    purchase_value: Amount | None
    purchase_count: int | None = Field(ge=0)
    coverage: Literal["OBSERVED_COMPLETE_SEC_WINDOW", "PARTIAL", "BLOCKED"]


class ResearchCompany(PublicModel):
    issuer_cik: Cik
    ticker: str | None
    name: str
    sector: str | None
    identity_status: Literal["RESOLVED", "UNRESOLVED"]
    insider_status: Literal["AVAILABLE", "UNRESOLVED_AMENDMENT", "SOURCE_QUARANTINE"]
    current_price: Amount | None
    basis: list[BasisWindow]


class ResearchScore(PublicModel):
    issuer_cik: Cik
    total: Score | None
    insider: Score | None
    divergence: Score | None
    turn: Score | None
    cluster: Score | None
    market_rs: float | None
    sector_rs: float | None
    state: Literal["UNKNOWN", "FALLING", "INSIDER_ACCUMULATION", "BASE_FORMING", "EARLY_TURN",
                   "CONFIRMED_TURN"]
    state_changed_at: datetime | None
    reasons: list[str]
    score_version: str
    methodology_hash: str | None
    config_hash: str | None
    run_id: str
    as_of: datetime


class Cluster(PublicModel):
    cluster_id: str
    issuer_cik: Cik
    start: date
    end: date
    owner_ciks: list[Cik] = Field(min_length=2)
    event_ids: list[str] = Field(min_length=2)
    purchase_value: Amount


class SeriesPoint(PublicModel):
    issuer_cik: Cik
    date: date
    price: Amount
    volume: Amount | None
    market_rs: float | None
    sector_rs: float | None


class DayEvidence(PublicModel):
    day: date
    discovered_filings: int = Field(ge=0)
    stored_filings: int = Field(ge=0)
    parse_rows: int = Field(ge=0)
    quarantined_rows: int = Field(ge=0)
    failures: int = Field(ge=0)
    complete: bool

    @model_validator(mode="after")
    def check_completeness(self) -> Self:
        measured = (self.discovered_filings == self.stored_filings
                    and self.failures == 0 and self.quarantined_rows == 0)
        if self.complete != measured:
            raise ValueError("day completeness disagrees with measured counts")
        return self


class ResearchCoverage(PublicModel):
    scope: str
    expected_sec_days: list[date]
    days: list[DayEvidence]
    missing_sec_days: list[date]
    canonical_owner_rows: int
    economic_events: int
    eligible_companies: int
    resolved_identities: int
    priced_companies: int
    complete_scores: int
    unresolved_amendment_issuers: list[Cik]
    exclusions: dict[str, int]


class Readiness(PublicModel):
    status: Literal["READY", "PARTIAL", "BLOCKED"]
    reasons: list[str]


class ResearchReadiness(PublicModel):
    dashboard: Readiness
    digest: Readiness
    predictive: Readiness


class ResearchSnapshot(PublicModel):
    schema_version: Literal["2.0.0", "2.1.0"] = "2.0.0"
    source: Literal["canonical-sec-research"] = "canonical-sec-research"
    run_id: str
    as_of: datetime
    score_version: str
    companies: list[ResearchCompany]
    economic_transactions: list[EconomicEvent]
    reporting_owners: list[Owner]
    research_scores: list[ResearchScore]
    clusters: list[Cluster]
    company_series: list[SeriesPoint]
    coverage: ResearchCoverage
    readiness: ResearchReadiness

    @model_validator(mode="after")
    def references_and_lineage(self) -> Self:
        if self.as_of.tzinfo is None:
            raise ValueError("snapshot asOf must be timezone-aware")
        companies = {row.issuer_cik for row in self.companies}
        owners = {row.owner_cik for row in self.reporting_owners}
        events = {row.event_id for row in self.economic_transactions}
        if (len(companies) != len(self.companies) or len(owners) != len(self.reporting_owners)
                or len(events) != len(self.economic_transactions)):
            raise ValueError("duplicate public identity")
        for row in self.economic_transactions:
            if (row.issuer_cik not in companies or len({link.owner_cik for link in row.owners})
                    != len(row.owners) or any(link.owner_cik not in owners for link in row.owners)):
                raise ValueError("broken event owner/company reference")
            if (row.accepted_at.tzinfo is None or row.known_at.tzinfo is None
                    or max(row.accepted_at, row.known_at) > self.as_of
                    or row.transaction_date > self.as_of.date()
                    or row.sec_day is not None and row.sec_day > self.as_of.date()):
                raise ValueError("future economic event")
            if row.aggregate_eligible and (row.processing != "EFFECTIVE" or not row.qualified):
                raise ValueError("unresolved event cannot enter aggregates")
            if row.shares is None and (row.table != "DERIVATIVE" or row.value is None
                                       or row.qualified or row.aggregate_eligible
                                       or self.schema_version != "2.1.0"):
                raise ValueError("unknown quantity requires a non-signal derivative amount")
        if len({row.issuer_cik for row in self.research_scores}) != len(self.research_scores):
            raise ValueError("duplicate score identity")
        for score in self.research_scores:
            if (score.issuer_cik not in companies or score.run_id != self.run_id
                    or score.as_of != self.as_of or score.score_version != self.score_version):
                raise ValueError("mixed score lineage")
            if score.state_changed_at is not None and (score.state_changed_at.tzinfo is None
                                                       or score.state_changed_at > self.as_of):
                raise ValueError("future state transition")
        by_event = {row.event_id: row for row in self.economic_transactions}
        for cluster in self.clusters:
            if (cluster.issuer_cik not in companies or not set(cluster.event_ids) <= events
                    or not set(cluster.owner_ciks) <= owners):
                raise ValueError("broken cluster reference")
            members = [by_event[key] for key in cluster.event_ids]
            if (len(set(cluster.event_ids)) != len(cluster.event_ids)
                    or any(row.issuer_cik != cluster.issuer_cik or not row.aggregate_eligible
                           or row.side != "BUY" for row in members)
                    or set(cluster.owner_ciks) != {link.owner_cik for row in members
                                                  for link in row.owners}
                    or abs(cluster.purchase_value - sum(row.value or 0 for row in members))
                    > 0.01):
                raise ValueError("inconsistent cluster economics")
        if any(sorted(row.days for row in company.basis) != [30, 90]
               for company in self.companies):
            raise ValueError("both unique basis windows required")
        if any(row.issuer_cik not in companies or row.date > self.as_of.date()
               for row in self.company_series):
            raise ValueError("invalid company series")
        return self
