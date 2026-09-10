"""Deterministic parser for SEC ``ownershipDocument`` XML (Forms 3/4/5).

The SEC payload is treated as untrusted input.  Rows with missing/invalid
required facts are quarantined independently so one malformed row does not
discard otherwise useful rows from a filing.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from insider_turning_engine.domain.models import (
    CanonicalTransaction,
    EconomicClassification,
    InsiderRole,
    Issuer,
    Lifecycle,
    ParseResult,
    Quality,
    QualityFlag,
    QualitySeverity,
    QualityStatus,
    QuarantineRecord,
    Relationship,
    ReportingOwner,
    Rule10b51,
    Security,
    Source,
    TableType,
    Timestamps,
    TransactionClassification,
    TransactionFacts,
    TriState,
    ValueDerivation,
)

_MAX_XML_BYTES = 10 * 1024 * 1024
_MAX_XML_DEPTH = 100
_MAX_TRANSACTION_ROWS = 50_000
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_TEN_B5_RE = re.compile(r"\brule\s*10b5[\s-]*1\b", re.IGNORECASE)
_CEO_RE = re.compile(r"\b(?:chief\s+executive\s+officer|ceo)\b", re.IGNORECASE)
_CFO_RE = re.compile(r"\b(?:chief\s+financial\s+officer|cfo)\b", re.IGNORECASE)
_CHAIRMAN_RE = re.compile(r"\b(?:chairman|chairwoman|chairperson|chair)\b", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [child for child in list(node) if _local(child.tag) == name]


def _first(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    for child in list(node):
        if _local(child.tag) == name:
            return child
    return None


def _text(node: ET.Element | None, *path: str, default: str | None = None) -> str | None:
    current = node
    for name in path:
        current = _first(current, name)
        if current is None:
            return default
    if current is None:
        return default
    value = "" if current.text is None else current.text.strip()
    return value if value else default


def _value_text(node: ET.Element | None, name: str) -> str | None:
    """Read SEC's either-direct-text or nested-``value`` representation."""

    child = _first(node, name)
    return _text(child, "value") or _text(node, name)


def _all_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join(part.strip() for part in node.itertext() if part.strip())


def _metadata_value(metadata: Any, *names: str, default: Any = None) -> Any:
    if metadata is None:
        return default
    if isinstance(metadata, Mapping):
        for name in names:
            if name in metadata and metadata[name] is not None:
                return metadata[name]
        base = metadata.get("_base_metadata")
        if base is not None:
            return _metadata_value(base, *names, default=default)
    else:
        for name in names:
            value = getattr(metadata, name, None)
            if value is not None:
                return value
    return default


def _utc(value: Any, default: datetime | None = None) -> datetime | None:
    if value is None:
        return default
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(candidate)
        except ValueError:
            return default
    if not isinstance(value, datetime):
        return default
    timestamp: datetime = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _norm_cik(value: str | None) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    if not clean.isdigit():
        return None
    if not clean or len(clean) > 10:
        return None
    return clean.zfill(10)


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    clean = value.strip().replace(",", "")
    if not clean:
        return None
    try:
        number = Decimal(clean)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _roles(relationship: Relationship) -> tuple[InsiderRole, ...]:
    """Normalize material insider roles without changing SEC source flags."""

    roles: list[InsiderRole] = []
    title = relationship.officer_title or ""
    if _CEO_RE.search(title):
        roles.append(InsiderRole.CEO)
    if _CFO_RE.search(title):
        roles.append(InsiderRole.CFO)
    if _CHAIRMAN_RE.search(title):
        roles.append(InsiderRole.CHAIRMAN)
    if relationship.is_director:
        roles.append(InsiderRole.DIRECTOR)
    if relationship.is_officer:
        roles.append(InsiderRole.OFFICER)
    if relationship.is_ten_percent_owner:
        roles.append(InsiderRole.TEN_PERCENT_OWNER)
    if relationship.is_other:
        roles.append(InsiderRole.OTHER)
    return tuple(roles)


def _source_url_is_valid(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _transaction_id(
    accession: str,
    owner_cik: str,
    table_type: TableType,
    row_sequence: int,
) -> str:
    """Return the ADR-mandated canonical Form 4 row identity."""

    return _sha("txn_", f"{accession}|{owner_cik}|{table_type.value}|{row_sequence}")


def _footnote_ids(node: ET.Element) -> set[str]:
    return {
        identifier.strip()
        for child in node.iter()
        if _local(child.tag) == "footnoteId"
        for identifier in (child.get("id"), (child.text or ""))
        if identifier and identifier.strip()
    }


def _within_xml_depth_limit(root: ET.Element) -> bool:
    """Bound pathological nesting before traversing untrusted XML further."""

    pending: list[tuple[ET.Element, int]] = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        if depth > _MAX_XML_DEPTH:
            return False
        pending.extend((child, depth + 1) for child in node)
    return True


def _classify(code: str) -> TransactionClassification:
    return {
        "P": TransactionClassification.OPEN_MARKET_PURCHASE,
        "S": TransactionClassification.OPEN_MARKET_SALE,
        "A": TransactionClassification.AWARD,
        "M": TransactionClassification.OPTION_EXERCISE,
        "G": TransactionClassification.GIFT,
        "F": TransactionClassification.TAX_WITHHOLDING,
        # Tender/issuer transfers are dispositions/acquisitions outside the
        # open-market categories; the canonical v1 bucket is TRANSFER.
        "T": TransactionClassification.TRANSFER,
        "X": TransactionClassification.TRANSFER,
    }.get(code, TransactionClassification.OTHER)


def _economic_classification(
    classification: TransactionClassification, acquired_disposed: str
) -> EconomicClassification:
    if classification is TransactionClassification.AWARD:
        return EconomicClassification.GRANT_AWARD
    if classification is TransactionClassification.TRANSFER:
        return (
            EconomicClassification.OTHER_ACQUISITION
            if acquired_disposed == "A"
            else EconomicClassification.OTHER_DISPOSITION
        )
    try:
        return EconomicClassification(classification.value)
    except ValueError:
        return (
            EconomicClassification.OTHER_ACQUISITION
            if acquired_disposed == "A"
            else EconomicClassification.OTHER_DISPOSITION
        )


def _rule_10b51(value: TriState) -> Rule10b51:
    return {
        TriState.TRUE: Rule10b51.YES,
        TriState.FALSE: Rule10b51.NO,
        TriState.UNKNOWN: Rule10b51.UNKNOWN,
    }[value]


def _sha(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _quarantine(
    code: str,
    message: str,
    *,
    row_key: str | None = None,
    locator: str | None = None,
    excerpt: str | None = None,
    run_id: str | None = None,
) -> QuarantineRecord:
    return QuarantineRecord(
        reason_code=code,
        message=message[:500],
        source_row_key=row_key,
        locator=locator,
        excerpt=excerpt[:500] if excerpt else None,
        run_id=run_id,
    )


def parse_sec_ownership_document(
    payload: bytes | str | Path,
    filing_metadata: Mapping[str, Any] | Any | None = None,
    **metadata: Any,
) -> ParseResult:
    """Parse an SEC ownership document into canonical records and quarantines.

    ``filing_metadata`` may be a mapping or an object with attributes.  Keyword
    metadata is merged on top, making both of these forms valid::

        parse_sec_xml(xml, {"accession_number": "...", "source_url": "..."})
        parse_sec_xml(xml, accession_number="...", source_url="...")

    The parser emits immutable filing observations.  Amendment resolution and
    effective-view selection are deliberately performed by
    :mod:`insider_turning_engine.normalization.amendments`, where multiple
    observations are available for a row-level chain.
    """

    if metadata:
        # Some callers use ``metadata=...`` while others pass the mapping as
        # the second positional argument.  Accept both forms explicitly.
        nested_metadata = metadata.pop("metadata", None)
        if isinstance(nested_metadata, Mapping):
            combined = dict(nested_metadata)
            combined.update(metadata)
            metadata = combined
        merged: dict[str, Any] = {}
        if isinstance(filing_metadata, Mapping):
            merged.update(filing_metadata)
        elif filing_metadata is not None:
            # Attribute objects are read by _metadata_value below; retain them
            # and let explicit keywords shadow them through a tiny proxy map.
            merged["_base_metadata"] = filing_metadata
        merged.update(metadata)
        filing_metadata = merged

    run_id = _metadata_value(filing_metadata, "run_id", "runId")
    if run_id is None and isinstance(filing_metadata, Mapping):
        run_id = _metadata_value(filing_metadata.get("_base_metadata"), "run_id", "runId")
    if run_id is None:
        run_id = "run_parser_default_20260830"

    if isinstance(payload, Path):
        payload_bytes = payload.read_bytes()
    elif isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        payload_bytes = payload
    else:
        return ParseResult(
            quarantines=[
                _quarantine(
                    "INVALID_PAYLOAD",
                    "payload must be bytes, string, or Path",
                    run_id=run_id,
                )
            ]
        )

    if len(payload_bytes) > _MAX_XML_BYTES:
        return ParseResult(
            quarantines=[
                _quarantine("PAYLOAD_TOO_LARGE", "XML payload exceeds 10 MiB limit", run_id=run_id)
            ]
        )

    # ``ElementTree`` does not resolve external entities, but rejecting DTDs
    # up front also blocks internal entity expansion payloads and makes the
    # parser's supported XML subset explicit.
    if b"<!DOCTYPE" in payload_bytes.upper() or b"<!ENTITY" in payload_bytes.upper():
        return ParseResult(
            quarantines=[
                _quarantine(
                    "UNSAFE_XML",
                    "DTD and entity declarations are not accepted in SEC ownership XML",
                    run_id=run_id,
                )
            ]
        )

    content_hash = "sha256:" + hashlib.sha256(payload_bytes).hexdigest()
    try:
        root = ET.fromstring(payload_bytes)
    except (ET.ParseError, ValueError, UnicodeError) as exc:
        return ParseResult(
            quarantines=[
                _quarantine("INVALID_XML", f"unable to parse ownership XML: {exc}", run_id=run_id)
            ]
        )

    if _local(root.tag) != "ownershipDocument":
        return ParseResult(
            quarantines=[
                _quarantine(
                    "UNSUPPORTED_DOCUMENT", "root element is not ownershipDocument", run_id=run_id
                )
            ]
        )
    if not _within_xml_depth_limit(root):
        return ParseResult(
            quarantines=[
                _quarantine(
                    "XML_NESTING_LIMIT",
                    "ownership XML exceeds the maximum supported nesting depth",
                    run_id=run_id,
                )
            ]
        )

    # Metadata aliases intentionally include SEC's common API names.
    accession = _metadata_value(
        filing_metadata,
        "accession_number",
        "accessionNumber",
        "accession",
        default="0000000000-00-000000",
    )
    accession = str(accession)
    if not _ACCESSION_RE.fullmatch(accession):
        return ParseResult(
            quarantines=[
                _quarantine(
                    "INVALID_ACCESSION", "accession number has invalid SEC format", run_id=run_id
                )
            ]
        )
    provider = str(_metadata_value(filing_metadata, "provider", default="sec"))
    provider_record_id = str(
        _metadata_value(
            filing_metadata, "provider_record_id", "providerRecordId", default=accession
        )
    )
    source_url = _metadata_value(
        filing_metadata,
        "source_url",
        "sourceUrl",
        "filing_url",
        "filingUrl",
        "url",
    )
    issuer_node = _first(root, "issuer")
    issuer_cik = _norm_cik(_text(issuer_node, "issuerCik"))
    issuer_name = _text(issuer_node, "issuerName")
    ticker = _text(issuer_node, "issuerTradingSymbol")
    if issuer_cik is None or not issuer_name:
        return ParseResult(
            quarantines=[
                _quarantine("MISSING_ISSUER", "issuer CIK and name are required", run_id=run_id)
            ]
        )
    ticker = ticker.upper() if ticker else None
    unresolved_ticker = (
        ticker is not None and re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", ticker) is None
    )
    if unresolved_ticker:
        # CIK is the issuer identity. N/A or multiple listed classes do not
        # invalidate otherwise valid transactions, nor identify a tradable ticker.
        ticker = None
    try:
        issuer = Issuer(cik=issuer_cik, name=issuer_name, ticker=ticker)
    except ValueError as exc:
        return ParseResult(quarantines=[_quarantine("INVALID_ISSUER", str(exc), run_id=run_id)])

    form_type = _metadata_value(filing_metadata, "form_type", "formType") or _text(
        root, "documentType"
    )
    form_type = str(form_type or "").upper()
    if form_type not in {"3", "3/A", "4", "4/A", "5", "5/A"}:
        return ParseResult(
            quarantines=[
                _quarantine(
                    "UNSUPPORTED_FORM",
                    f"unsupported ownership form {form_type!r}",
                    run_id=run_id,
                )
            ]
        )
    is_amendment = form_type.endswith("/A")

    # The metadata supplied by the fetcher is authoritative for source times.
    now = datetime.now(UTC)
    observed_at = (
        _utc(
            _metadata_value(
                filing_metadata, "observed_at", "observedAt", "ingested_at", "ingestedAt"
            ),
            now,
        )
        or now
    )
    recorded_at = (
        _utc(
            _metadata_value(
                filing_metadata, "recorded_at", "recordedAt", "ingested_at", "ingestedAt"
            ),
            observed_at,
        )
        or observed_at
    )
    accepted_at = _utc(
        _metadata_value(
            filing_metadata,
            "accepted_at",
            "acceptedAt",
            "acceptance_datetime",
            "acceptance_time",
            "sec_accepted_at",
        ),
        None,
    )
    knowledge_at = max(observed_at, accepted_at or observed_at)

    if source_url is None:
        issuer_path = issuer_cik.lstrip("0") or "0"
        accession_path = accession.replace("-", "")
        source_url = (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{issuer_path}/{accession_path}/{accession}-ownership.xml"
        )
    source_url = str(source_url)
    if not _source_url_is_valid(source_url):
        return ParseResult(
            quarantines=[
                _quarantine(
                    "INVALID_SOURCE_URL",
                    "source URL must be an absolute HTTP(S) URI",
                    run_id=run_id,
                )
            ]
        )

    footnotes_by_id = {
        (node.get("id") or "").strip(): _all_text(node)
        for node in _children(_first(root, "footnotes"), "footnote")
        if (node.get("id") or "").strip()
    }
    explicit_10b5 = _text(root, "aff10b5One")
    if explicit_10b5 in {"1", "true", "TRUE", "yes", "Y"}:
        document_10b5_1 = TriState.TRUE
    elif explicit_10b5 in {"0", "false", "FALSE", "no", "N"}:
        document_10b5_1 = TriState.FALSE
    else:
        document_10b5_1 = TriState.UNKNOWN

    amends_accession = _metadata_value(
        filing_metadata,
        "amends_accession_number",
        "amendsAccessionNumber",
        "supersedes_accession_number",
        "supersedesAccessionNumber",
        "original_accession_number",
        "originalAccessionNumber",
    )
    if amends_accession is not None:
        amends_accession = str(amends_accession)
        if not _ACCESSION_RE.fullmatch(amends_accession):
            return ParseResult(
                quarantines=[
                    _quarantine(
                        "INVALID_AMENDMENT_LINK",
                        "amendment predecessor accession has invalid SEC format",
                        run_id=run_id,
                    )
                ]
            )
    supersedes_revision_id = _metadata_value(
        filing_metadata,
        "supersedes_revision_id",
        "supersedesRevisionId",
    )
    if supersedes_revision_id is not None:
        supersedes_revision_id = str(supersedes_revision_id)
        if not re.fullmatch(r"txr_[A-Za-z0-9_-]{16,64}", supersedes_revision_id):
            return ParseResult(
                quarantines=[
                    _quarantine(
                        "INVALID_AMENDMENT_LINK",
                        "amendment predecessor revision ID has invalid format",
                        run_id=run_id,
                    )
                ]
            )

    owner_nodes = _children(root, "reportingOwner")
    if not owner_nodes:
        return ParseResult(
            quarantines=[
                _quarantine(
                    "MISSING_OWNER", "at least one reportingOwner is required", run_id=run_id
                )
            ]
        )
    owners: list[tuple[ReportingOwner, Relationship]] = []
    quarantines: list[QuarantineRecord] = []
    for owner_node in owner_nodes:
        owner_id_node = _first(owner_node, "reportingOwnerId")
        owner_cik_text = _text(owner_id_node, "rptOwnerCik")
        owner_cik = _norm_cik(owner_cik_text)
        owner_name = _text(owner_id_node, "rptOwnerName")
        if not owner_name:
            quarantines.append(
                _quarantine(
                    "MISSING_OWNER_IDENTITY",
                    "reporting owner name is required",
                    run_id=run_id,
                )
            )
            continue
        if owner_cik is None:
            quarantines.append(
                _quarantine(
                    "MISSING_OWNER_CIK",
                    "canonical SEC transactions require a reporting owner CIK",
                    run_id=run_id,
                )
            )
            continue
        relation_node = _first(owner_node, "reportingOwnerRelationship")
        relationship = Relationship(
            is_director=_bool(_text(relation_node, "isDirector")),
            is_officer=_bool(_text(relation_node, "isOfficer")),
            is_ten_percent_owner=_bool(_text(relation_node, "isTenPercentOwner")),
            is_other=_bool(_text(relation_node, "isOther")),
            officer_title=_text(relation_node, "officerTitle"),
        )
        relationship.normalized_roles = _roles(relationship)
        owners.append(
            (ReportingOwner(owner_id=owner_cik, cik=owner_cik, name=owner_name), relationship)
        )

    rows: list[tuple[TableType, ET.Element, int]] = []
    for table_type, table_name, row_name in (
        (TableType.NON_DERIVATIVE, "nonDerivativeTable", "nonDerivativeTransaction"),
        (TableType.DERIVATIVE, "derivativeTable", "derivativeTransaction"),
    ):
        table = _first(root, table_name)
        rows.extend((table_type, row, seq) for seq, row in enumerate(_children(table, row_name), 1))

    if len(rows) > _MAX_TRANSACTION_ROWS:
        return ParseResult(
            quarantines=[
                _quarantine(
                    "TRANSACTION_ROW_LIMIT",
                    "ownership XML exceeds the maximum supported transaction row count",
                    run_id=run_id,
                )
            ]
        )

    records: list[CanonicalTransaction] = []
    for table_type, row, row_seq in rows:
        row_key_base = f"{table_type.value}:{row_seq}"
        security_title = _value_text(row, "securityTitle")
        tx_date_text = _value_text(row, "transactionDate")
        code = (_text(_first(row, "transactionCoding"), "transactionCode") or "").upper()
        amounts = _first(row, "transactionAmounts")
        shares_text = _value_text(amounts, "transactionShares")
        price_text = _value_text(amounts, "transactionPricePerShare")
        acquired = (
            _text(_first(amounts, "transactionAcquiredDisposedCode"), "value") or ""
        ).upper()
        post = _first(row, "postTransactionAmounts")
        post_shares_text = _value_text(post, "sharesOwnedFollowingTransaction")
        nature = _first(row, "ownershipNature")
        ownership = (_value_text(nature, "directOrIndirectOwnership") or "").upper()
        indirect_nature = _value_text(nature, "natureOfOwnership")
        underlying = _first(row, "underlyingSecurity")
        underlying_title = _value_text(underlying, "underlyingSecurityTitle")
        table_label = table_type.value
        row_footnotes = [
            footnotes_by_id[identifier]
            for identifier in sorted(_footnote_ids(row))
            if identifier in footnotes_by_id
        ]
        row_10b5_1 = (
            TriState.TRUE
            if document_10b5_1 is TriState.TRUE
            or any(_TEN_B5_RE.search(note) for note in row_footnotes)
            else document_10b5_1
        )
        for owner, relationship in owners:
            row_key = f"{row_key_base}:{owner.cik}"
            transaction_id = _transaction_id(accession, owner.cik, table_type, row_seq)
            revision_id = _sha("txr_", f"{transaction_id}|{content_hash}")
            try:
                if (
                    not security_title
                    or not tx_date_text
                    or not code
                    or code == " "
                    or not acquired
                ):
                    raise ValueError("security title, transaction date, code, and A/D are required")
                tx_date = date.fromisoformat(tx_date_text)
                shares = _decimal(shares_text)
                if shares is None:
                    raise ValueError("transaction shares are required and must be non-negative")
                if _decimal(price_text) is None and price_text not in {None, ""}:
                    raise ValueError("transaction price is invalid")
                price = _decimal(price_text)
                post_shares = _decimal(post_shares_text)
                if post_shares_text not in {None, ""} and post_shares is None:
                    raise ValueError("post-transaction shares are invalid")
                if acquired not in {"A", "D"}:
                    raise ValueError("acquired/disposed code must be A or D")
                if ownership not in {"D", "I"}:
                    raise ValueError("direct/indirect ownership must be D or I")
                if price is not None:
                    value = shares * price
                    derivation = ValueDerivation.SHARES_TIMES_PRICE
                else:
                    value = None
                    derivation = ValueDerivation.UNAVAILABLE
                transaction = TransactionFacts(
                    transaction_date=tx_date,
                    code=code,
                    acquired_disposed=acquired,
                    shares=shares,
                    price_per_share=price,
                    value=value,
                    value_derivation=derivation,
                    currency="USD",
                    post_transaction_shares=post_shares,
                    ownership_nature=ownership,
                    indirect_ownership_nature=indirect_nature,
                    classification=_classify(code),
                    ten_b5_1=row_10b5_1,
                    economic_classification=_economic_classification(_classify(code), acquired),
                    rule_10b51=_rule_10b51(row_10b5_1),
                    footnotes=row_footnotes,
                )
                flags: list[QualityFlag] = []
                if unresolved_ticker:
                    flags.append(QualityFlag(
                        code="UNRESOLVED_ISSUER_TICKER", severity=QualitySeverity.WARNING,
                        message="SEC symbol is unavailable or ambiguous; use PIT CIK mapping",
                        path="issuer.ticker",
                    ))
                if price is None:
                    flags.append(
                        QualityFlag(
                            code="MISSING_PRICE",
                            severity=QualitySeverity.WARNING,
                            message=(
                                "Transaction price per share was not reported; "
                                "value is unavailable."
                            ),
                            path="transaction.pricePerShare",
                        )
                    )
                quality = Quality(
                    status=QualityStatus.WARN if flags else QualityStatus.PASS,
                    flags=flags,
                )
                security = Security(
                    title=security_title,
                    table_type=table_type,
                    underlying_title=underlying_title,
                )
                source = Source(
                    provider=provider,
                    provider_record_id=provider_record_id,
                    accession_number=accession,
                    form_type=form_type,
                    row_sequence=row_seq,
                    source_row_key=row_key,
                    content_hash=content_hash,
                    source_url=source_url,
                    run_id=run_id,
                    amends_accession_number=amends_accession,
                )
                records.append(
                    CanonicalTransaction(
                        run_id=run_id,
                        ingested_at=recorded_at,
                        transaction_id=transaction_id,
                        revision_id=revision_id,
                        issuer=issuer,
                        reporting_owner=owner,
                        relationship=relationship,
                        security=security,
                        transaction=transaction,
                        source=source,
                        timestamps=Timestamps(
                            accepted_at=accepted_at,
                            observed_at=observed_at,
                            knowledge_at=knowledge_at,
                            recorded_at=recorded_at,
                        ),
                        lifecycle=Lifecycle(
                            is_amendment=is_amendment,
                            supersedes_revision_id=supersedes_revision_id,
                            valid_from=recorded_at,
                        ),
                        quality=quality,
                    )
                )
            except (ValueError, TypeError) as exc:
                quarantines.append(
                    _quarantine(
                        "INVALID_TRANSACTION",
                        str(exc),
                        row_key=row_key,
                        locator=f"{table_label}.row[{row_seq}]",
                        excerpt=_all_text(row),
                        run_id=run_id,
                    )
                )

    return ParseResult(records=records, quarantines=quarantines)


# Public aliases keep adapter naming ergonomic and backwards compatible.
parse_ownership_document = parse_sec_ownership_document
parse_sec_xml = parse_sec_ownership_document
parse_filing = parse_sec_ownership_document
parse_sec_filing = parse_sec_ownership_document
parse_sec_document = parse_sec_ownership_document


class SECParser:
    """Small state-free adapter wrapper for dependency-injection call sites."""

    def parse(
        self,
        payload: bytes | str | Path,
        filing_metadata: Mapping[str, Any] | Any | None = None,
        **metadata: Any,
    ) -> ParseResult:
        return parse_sec_ownership_document(payload, filing_metadata, **metadata)


SecParser = SECParser

__all__ = [
    "parse_filing",
    "parse_sec_document",
    "parse_sec_filing",
    "parse_ownership_document",
    "parse_sec_ownership_document",
    "parse_sec_xml",
    "SECParser",
    "SecParser",
]
