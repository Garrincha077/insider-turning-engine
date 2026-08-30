# ADR 0002: Point-in-time and anti-lookahead semantics

- Status: Accepted
- Scope: ingestion, scoring, replay, backtests

## Context

Transaction dates precede disclosure, providers arrive late, market data can be revised, and present-day ticker or index membership can leak future knowledge into historical results.

## Decision

The engine records four clocks where applicable:

- `event_at`: when the underlying event occurred (for Form 4 rows, `transaction_date`).
- `source_at`: when the authoritative source made it public (SEC `accepted_at`).
- `observed_at`: when this system first received it.
- `recorded_at`: when this system persisted the revision.

`knowledge_at = max(source_at, observed_at)`; when source time is unavailable, `observed_at` is authoritative and the absence is flagged. A run at `as_of` may consume only records whose `knowledge_at <= as_of` and market/reference values whose `available_at <= as_of`.

Historical issuer attributes, security mappings, corporate actions, universe membership, fundamentals, and market bars are valid-time records. Queries must join on `as_of`, not current state. Vendor corrections received after `as_of` do not rewrite an existing snapshot; a replay emits a new snapshot with a new run and data-version identity.

Provider fetch time is not a substitute for SEC acceptance time, and transaction date is never disclosure time. Tests deliberately inject late arrivals and future revisions.

## Consequences

Backtests can be slower and may differ from a current-data recomputation, but live and historical outputs share one auditable information boundary.
