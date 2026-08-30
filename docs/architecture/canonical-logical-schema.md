# Canonical logical schema

This is the storage-neutral contract for Insider Turning Engine v1. Physical schemas may add indexes and audit columns, but may not weaken keys, temporal semantics, or lineage.

## Conventions

- IDs are opaque strings; CIK is a zero-padded 10-character string.
- Times are UTC RFC 3339 instants; market sessions and transaction dates are ISO dates.
- Financial quantities are fixed-point decimals, serialized as decimal strings at boundaries.
- `as_of` is inclusive. `available_at`/`knowledge_at` determine eligibility, not event date.
- Mutable business facts use revisions with `[valid_from, valid_to)`; `valid_to = null` is current.
- Every canonical record carries schema version, source provenance, `ingested_at`, and `run_id`. All derived rows also carry model/config version and input watermarks.

## Entities and grains

| Entity | Grain / key | Required facts |
|---|---|---|
| `Issuer` | one legal issuer per `issuer_id`; unique CIK | CIK, legal name, status |
| `IssuerAttributeRevision` | issuer attribute validity interval | ticker, exchange, sector/industry, valid interval, knowledge time, source |
| `ReportingOwner` | one reconciled owner per `owner_id` | owner CIK or namespaced synthetic key, normalized name |
| `OwnerIdentityLink` | provider identity to owner validity interval | provider, provider owner ID, confidence, decision provenance |
| `FilingObservation` | immutable provider payload observation | provider record ID, accession, form type, content hash, accepted/observed/knowledge/recorded times, raw locator, parse status |
| `CanonicalTransaction` | one deterministic economic transaction | `transaction_id = txn_ + sha256(accessionNumber|ownerCIK|tableType|rowSequence)`, issuer, owner, first observation, ingestion run/time |
| `TransactionRevision` | one version of a canonical transaction; unique (`transaction_id`, `revision`) | transaction/security facts, normalized economic classification, tri-state Rule 10b5-1 indicator, lifecycle status, valid interval, knowledge time, source observation |
| `MarketBarRevision` | security/session/provider revision | OHLCV, adjustment basis, available time, valid interval |
| `ReferenceRevision` | named point-in-time reference fact | subject, fact name/value, effective period, available time, source |
| `PipelineRun` | one ingestion/scoring/publication attempt | run type, as-of, status, versions, start/end, correlation ID |
| `StageCheckpoint` | one stage attempt in a run | cursor/watermarks, counts, status, structured error |
| `SignalSnapshot` | one issuer/model/as-of result per run | component scores, total, state, evidence, provenance |
| `StateTransition` | one accepted issuer state change | exact public from/to label, triggering snapshot, reason set, evaluation sequence |
| `AlertCandidate` | one alert rule match at a snapshot | issuer, exact public type, score, severity, important flag, reasons |
| `AlertDelivery` | one channel attempt for a candidate | idempotency key, cooldown decision, status, attempt/error metadata |
| `DashboardManifest` | one published run/as-of bundle | watermarks, quality summary, snapshot references, artifact hashes |
| `QualityMeasurement` | one rule/population/run measurement | numerator, denominator, rate, threshold, result, exclusions |
| `QuarantineRecord` | one rejected observation or normalized record | reason code, safe excerpt/locator, first/last seen, repair status |

## Relationships and invariants

- `Issuer 1 -> many IssuerAttributeRevision`; validity intervals for the same attribute may not overlap.
- `ReportingOwner 1 -> many OwnerIdentityLink`; automated links below the configured confidence remain proposals.
- `FilingObservation many -> many CanonicalTransaction` through an explicit evidence link containing source row key and match method.
- `CanonicalTransaction 1 -> many TransactionRevision`; exactly one current revision exists unless the transaction is terminally void.
- Transaction identity inputs use normalized accession number, zero-padded owner CIK, canonical table type, and one-based authoritative row sequence. Changing economic facts in an amendment creates a revision without changing that identity tuple.
- A revision marked `SUPERSEDED` has a successor; `VOID` remains addressable and is excluded from active economic aggregates.
- Every `SignalSnapshot` references the exact transaction revision IDs and market/reference watermarks used. Inputs must have `knowledge_at` or `available_at <= snapshot.as_of`.
- State transitions are ordered per issuer. Promotion follows the configured path; downgrade debouncing and immediate-low reset are recorded as evidence.
- Alert candidate creation and delivery are separate. A suppressed candidate remains stored with the cooldown/override decision.
- A manifest references immutable snapshots and artifacts by ID plus SHA-256 hash. It never points at a mutable “latest” object without also pinning its identity.

## Aggregate semantics

Only active transaction revisions known at `as_of` enter aggregates. Acquisition/disposition direction is explicit; shares and values are non-negative magnitudes. Netting applies direction after filtering. Dollar value is source value when authoritative, otherwise `shares * price_per_share` with derivation metadata. Split-adjusted comparisons name their adjustment basis. Null is distinct from zero; only the v1 total-score fundamental factor may be excluded and weights renormalized.

## State and publication boundary

Public state labels are exactly `FALLING`, `INSIDER_ACCUMULATION`, `BASE_FORMING`, `EARLY_TURN`, and `CONFIRMED_TURN`. Public alert types are exactly `MAJOR_INSIDER_BUY`, `STEALTH_ACCUMULATION`, and `TURNING`.

The scoring configuration owns score weights, state gates, alert rules, cooldowns, rate limits, and publication quality thresholds. JSON Schemas own interchange shape. A dashboard manifest is valid only when its referenced snapshots validate, hashes match, all data is point-in-time eligible, and the quality result is `PASS` or an explicitly labeled `DEGRADED` publication allowed by run policy.
