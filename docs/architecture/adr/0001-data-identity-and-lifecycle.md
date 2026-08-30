# ADR 0001: Data identity and lifecycle

- Status: Accepted
- Scope: filings, transactions, derived signals

## Context

Provider identifiers, amended filings, duplicate delivery, ticker changes, and late corrections make a mutable “one row per trade” model unsafe.

## Decision

1. The legal issuer key is normalized SEC CIK; ticker is a point-in-time attribute, never identity. Canonical transactions require a normalized reporting-owner CIK. Observations lacking it remain quarantined until resolved.
2. Each provider observation is immutable and idempotent on `(provider, provider_record_id, content_hash)`. Raw payloads and parse results are retained as evidence.
3. Canonical `transaction_id` is deterministic: `txn_` plus lowercase SHA-256 of the UTF-8 string `accessionNumber|ownerCIK|tableType|rowSequence`, using normalized accession/CIK/table values and a one-based authoritative row sequence. Provider observations map to it through explicit identity links; fuzzy matching may propose, but never silently merge, identities.
4. Corrections create canonical revisions. Revisions have `valid_from`, optional `valid_to`, and `status`; only one revision may be current. Amendments supersede or void records rather than deleting them.
5. Every canonical record carries schema version, source provenance, `ingested_at`, and `run_id`. Every derived signal and dashboard manifest is an immutable snapshot keyed by issuer, `as_of`, model version, and input watermarks. Reprocessing emits a new snapshot and preserves the old one.
6. Retention is append-first. Purges, if policy requires them, target raw payloads only after provenance hashes and normalized evidence are durable.

## Consequences

Reads must select the correct revision and point-in-time identity attributes. Storage is larger, but ingestion is replayable, corrections are auditable, and dashboard outputs can be reproduced.
