"""Pydantic v2 models for the canonical transaction contract.

The SEC adapter keeps the models deliberately storage-neutral.  Python callers
use snake_case, while ``model_dump(by_alias=True)`` emits the camelCase names
from ``schemas/canonical-transaction.schema.json``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part[:1].upper() + part[1:] for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
    )


class TransactionClassification(StrEnum):
    OPEN_MARKET_PURCHASE = "OPEN_MARKET_PURCHASE"
    OPEN_MARKET_SALE = "OPEN_MARKET_SALE"
    AWARD = "AWARD"
    OPTION_EXERCISE = "OPTION_EXERCISE"
    GIFT = "GIFT"
    TAX_WITHHOLDING = "TAX_WITHHOLDING"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"


class EconomicClassification(StrEnum):
    """Classifications used in the canonical interchange schema."""

    OPEN_MARKET_PURCHASE = "OPEN_MARKET_PURCHASE"
    OPEN_MARKET_SALE = "OPEN_MARKET_SALE"
    OPTION_EXERCISE = "OPTION_EXERCISE"
    GRANT_AWARD = "GRANT_AWARD"
    GIFT = "GIFT"
    TAX_WITHHOLDING = "TAX_WITHHOLDING"
    CONVERSION = "CONVERSION"
    OTHER_ACQUISITION = "OTHER_ACQUISITION"
    OTHER_DISPOSITION = "OTHER_DISPOSITION"
    UNKNOWN = "UNKNOWN"


class Rule10b51(StrEnum):
    YES = "true"
    NO = "false"
    UNKNOWN = "unknown"


class TriState(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class TableType(StrEnum):
    NON_DERIVATIVE = "NON_DERIVATIVE"
    DERIVATIVE = "DERIVATIVE"


class ValueDerivation(StrEnum):
    SOURCE = "SOURCE"
    SHARES_TIMES_PRICE = "SHARES_TIMES_PRICE"
    UNAVAILABLE = "UNAVAILABLE"


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    VOID = "VOID"


class QualityStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    QUARANTINED = "QUARANTINED"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Issuer(_Model):
    cik: str = Field(min_length=10, max_length=10, pattern=r"^[0-9]{10}$")
    name: str = Field(min_length=1, max_length=300)
    ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


class ReportingOwner(_Model):
    owner_id: str = Field(min_length=8, max_length=100)
    cik: str = Field(pattern=r"^[0-9]{10}$")
    name: str = Field(min_length=1, max_length=300)


class InsiderRole(StrEnum):
    """Normalized reporting-owner roles used by ranking and display code."""

    CEO = "CEO"
    CFO = "CFO"
    CHAIRMAN = "CHAIRMAN"
    DIRECTOR = "DIRECTOR"
    OFFICER = "OFFICER"
    TEN_PERCENT_OWNER = "TEN_PERCENT_OWNER"
    OTHER = "OTHER"


class Relationship(_Model):
    is_director: bool = False
    is_officer: bool = False
    is_ten_percent_owner: bool = False
    is_other: bool = False
    officer_title: str | None = Field(default=None, max_length=200)
    # The canonical v1 interchange schema intentionally contains the original
    # SEC relationship flags and title only.  This normalized convenience view
    # is kept typed, but excluded so schema projections remain exact.
    normalized_roles: tuple[InsiderRole, ...] = Field(default=(), exclude=True)


class Security(_Model):
    title: str = Field(min_length=1, max_length=300)
    table_type: TableType
    underlying_title: str | None = Field(default=None, max_length=300)


class TransactionFacts(_Model):
    transaction_date: date
    code: str = Field(pattern=r"^[A-Z]$")
    acquired_disposed: str = Field(pattern=r"^[AD]$")
    shares: Decimal
    price_per_share: Decimal | None = None
    value: Decimal | None = None
    value_derivation: ValueDerivation
    economic_classification: EconomicClassification = EconomicClassification.UNKNOWN
    rule_10b51: Rule10b51 = Rule10b51.UNKNOWN
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    post_transaction_shares: Decimal | None = None
    ownership_nature: str = Field(pattern=r"^[DI]$")
    indirect_ownership_nature: str | None = Field(default=None, max_length=500)

    # These source-normalized fields are useful to scoring code but are not
    # part of the interchange schema.  They are omitted from schema dumps.
    classification: TransactionClassification = Field(
        default=TransactionClassification.OTHER, exclude=True
    )
    ten_b5_1: TriState = Field(default=TriState.UNKNOWN, exclude=True)
    footnotes: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def non_negative_quantities(self) -> TransactionFacts:
        for field in ("shares", "price_per_share", "value", "post_transaction_shares"):
            value = getattr(self, field)
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError(f"{field} must be finite and non-negative")
        return self

    @field_serializer("shares", "price_per_share", "value", "post_transaction_shares")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")

    @property
    def transaction_type(self) -> TransactionClassification:
        return self.classification

    @property
    def is_10b5_1(self) -> TriState:
        return self.ten_b5_1

    @property
    def rule10b51(self) -> Rule10b51:
        return self.rule_10b51

    @property
    def economicClassification(self) -> EconomicClassification:
        return self.economic_classification

    @property
    def acquired_disposed_code(self) -> str:
        return self.acquired_disposed

    @property
    def transaction_code(self) -> str:
        return self.code

    @property
    def direct_or_indirect_ownership(self) -> str:
        return self.ownership_nature

    @property
    def transaction_price_per_share(self) -> Decimal | None:
        return self.price_per_share

    @property
    def shares_owned_following_transaction(self) -> Decimal | None:
        return self.post_transaction_shares


class Source(_Model):
    provider: str = Field(default="sec", min_length=1, max_length=80)
    provider_record_id: str = Field(min_length=1, max_length=300)
    accession_number: str = Field(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
    form_type: str = Field(pattern=r"^(3|3/A|4|4/A|5|5/A)$")
    row_sequence: int = Field(default=1, ge=1)
    source_row_key: str = Field(min_length=1, max_length=300)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_url: str = Field(min_length=1, max_length=2000)
    # Audit metadata is retained on the typed object.  It is excluded from the
    # canonical interchange projection because the original schema predates it.
    run_id: str | None = Field(default=None, exclude=True)
    # SEC XML does not carry a machine-readable predecessor accession.  A
    # fetcher may supply it from the filing index or amendment metadata.  It
    # is internal matching evidence, not part of canonical v1 interchange.
    amends_accession_number: str | None = Field(
        default=None,
        pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$",
        exclude=True,
    )

    @field_validator("source_url")
    @classmethod
    def absolute_uri(cls, value: str) -> str:
        if not urlparse(value).scheme:
            raise ValueError("source_url must be an absolute URI")
        return value


class Timestamps(_Model):
    accepted_at: datetime | None = None
    observed_at: datetime
    knowledge_at: datetime
    recorded_at: datetime

    @model_validator(mode="after")
    def utc_instants(self) -> Timestamps:
        for name in ("accepted_at", "observed_at", "knowledge_at", "recorded_at"):
            value = getattr(self, name)
            if value is None:
                continue
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            setattr(self, name, value.astimezone(UTC))
        if self.knowledge_at < self.observed_at:
            raise ValueError("knowledge_at cannot precede observed_at")
        if self.accepted_at is not None and self.knowledge_at < self.accepted_at:
            raise ValueError("knowledge_at cannot precede accepted_at")
        return self

    @property
    def ingested_at(self) -> datetime:
        """Alias used by ingestion callers for the persistence timestamp."""

        return self.recorded_at


class Lifecycle(_Model):
    revision: int = Field(default=1, ge=1)
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    is_amendment: bool = False
    supersedes_revision_id: str | None = None
    valid_from: datetime
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> Lifecycle:
        valid_from = self.valid_from
        valid_to = self.valid_to
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=UTC)
        if valid_to is not None and valid_to.tzinfo is None:
            valid_to = valid_to.replace(tzinfo=UTC)
        self.valid_from = valid_from.astimezone(UTC)
        self.valid_to = valid_to.astimezone(UTC) if valid_to is not None else None
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        if self.status is LifecycleStatus.SUPERSEDED and self.valid_to is None:
            raise ValueError("a superseded revision requires valid_to")
        if self.status is LifecycleStatus.ACTIVE and self.valid_to is not None:
            raise ValueError("an active revision cannot have valid_to")
        return self


class QualityFlag(_Model):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    severity: QualitySeverity
    message: str = Field(min_length=1, max_length=500)
    path: str = Field(default="", max_length=300)


class Quality(_Model):
    status: QualityStatus = QualityStatus.PASS
    flags: list[QualityFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_flags(self) -> Quality:
        identities = {(flag.code, flag.severity, flag.message, flag.path) for flag in self.flags}
        if len(identities) != len(self.flags):
            raise ValueError("quality flags must be unique")
        return self


class CanonicalTransaction(_Model):
    schema_version: str = Field(default="1.0.0", pattern=r"^1\.0\.0$")
    run_id: str = Field(
        default="run_parser_default_20260830",
        pattern=r"^run_[A-Za-z0-9_-]{16,64}$",
    )
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transaction_id: str = Field(pattern=r"^txn_[a-f0-9]{64}$")
    revision_id: str = Field(pattern=r"^txr_[A-Za-z0-9_-]{16,64}$")
    issuer: Issuer
    reporting_owner: ReportingOwner
    relationship: Relationship
    security: Security
    transaction: TransactionFacts
    source: Source
    timestamps: Timestamps
    lifecycle: Lifecycle
    quality: Quality

    @model_validator(mode="after")
    def canonical_timestamps(self) -> CanonicalTransaction:
        ingested_at = self.ingested_at
        if ingested_at.tzinfo is None:
            ingested_at = ingested_at.replace(tzinfo=UTC)
        self.ingested_at = ingested_at.astimezone(UTC)
        if self.ingested_at != self.timestamps.recorded_at:
            raise ValueError("ingested_at must equal timestamps.recorded_at")
        return self

    def canonical_dump(self) -> dict[str, object]:
        """Return the JSON-compatible canonical-schema projection.

        Fields retained only for parser ergonomics (for example normalized
        roles and raw footnotes) are declared ``exclude=True`` above, so this
        projection has no properties outside the canonical v1 schema.
        """

        return cast(dict[str, object], self.model_dump(by_alias=True, mode="json"))

    @property
    def transaction_type(self) -> TransactionClassification:
        return self.transaction.classification

    @property
    def ten_b5_1(self) -> TriState:
        return self.transaction.ten_b5_1

    @property
    def is_10b5_1(self) -> TriState:
        return self.transaction.ten_b5_1

    @property
    def accepted_at(self) -> datetime | None:
        return self.timestamps.accepted_at

    @property
    def knowledge_at(self) -> datetime:
        return self.timestamps.knowledge_at

    @property
    def source_url(self) -> str:
        return self.source.source_url

    @property
    def transaction_classification(self) -> TransactionClassification:
        return self.transaction.classification


class QuarantineRecord(_Model):
    reason_code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    source_row_key: str | None = Field(default=None, max_length=300)
    locator: str | None = Field(default=None, max_length=300)
    excerpt: str | None = Field(default=None, max_length=500)
    run_id: str | None = None


class ParseResult(_Model):
    records: list[CanonicalTransaction] = Field(default_factory=list)
    quarantines: list[QuarantineRecord] = Field(default_factory=list)

    def as_tuple(self) -> tuple[list[CanonicalTransaction], list[QuarantineRecord]]:
        """Return parser output in the legacy ``records, quarantines`` shape."""

        return self.records, self.quarantines

    def __getitem__(self, index: int) -> list[CanonicalTransaction] | list[QuarantineRecord]:
        if index == 0:
            return self.records
        if index == 1:
            return self.quarantines
        raise IndexError(index)


__all__ = [
    "CanonicalTransaction",
    "CanonicalRecord",
    "EconomicClassification",
    "Issuer",
    "InsiderRole",
    "Lifecycle",
    "LifecycleStatus",
    "ParseResult",
    "Quality",
    "QualityFlag",
    "QualitySeverity",
    "QualityStatus",
    "QuarantineRecord",
    "Relationship",
    "ReportingOwner",
    "Rule10b51",
    "Security",
    "Source",
    "TableType",
    "Timestamps",
    "Transaction",
    "TransactionClassification",
    "TransactionFacts",
    "TriState",
    "ValueDerivation",
]

# Compatibility aliases for adapters that use shorter domain terminology.
Transaction = TransactionFacts
CanonicalRecord = CanonicalTransaction
