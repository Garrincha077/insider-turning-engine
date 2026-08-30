# ADR 0003: Provider interfaces

- Status: Accepted
- Scope: SEC, market, reference, and fundamentals adapters

## Context

Sources differ in pagination, identifiers, correction behavior, rate limits, and availability timestamps. Provider-specific objects must not enter scoring code.

## Decision

Adapters implement a language-neutral port with these operations:

- `fetch(cursor, through) -> page(records, next_cursor, source_watermark)`
- `get(provider_record_id) -> raw_record`
- `normalize(raw_record) -> observations | quarantined_result`
- `health() -> availability, lag, quota_state`

Every raw record carries provider name, stable provider record ID, retrieval time, source time when known, content type, content hash, and an opaque replay locator. Delivery is at-least-once; consumers are idempotent. Cursors are opaque and committed only after the page and checkpoint are durable.

Adapters return typed outcomes—success, retryable, throttled, not-found, permanent-invalid—rather than provider exceptions. Retry honors server guidance, exponential backoff, jitter, and a bounded attempt budget. SEC traffic has a hard internal ceiling of 6 requests/second across workers. Secrets stay in runtime secret stores and never enter raw evidence or logs.

Normalization emits only canonical contracts. Provider payload changes first fail into quarantine and a schema-drift alert; they do not silently default required fields.

## Consequences

Provider swaps and deterministic fixtures are straightforward. Adapter code carries more metadata, but scoring remains source-agnostic.
