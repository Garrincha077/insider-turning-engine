# ADR 0004: Operational state and alert delivery

- Status: Accepted
- Scope: runs, checkpoints, state transitions, notifications

## Context

Retries, partial source outages, and repeated scoring can otherwise duplicate alerts or present incomplete data as healthy.

## Decision

A pipeline run is `PENDING`, `RUNNING`, `SUCCEEDED`, `DEGRADED`, or `FAILED`. Each stage records start/end time, attempt, input/output watermark, counts, and structured error class. Checkpoints advance atomically only after durable outputs. A manifest is publishable only after contract validation and quality-gate evaluation; degraded publication is visibly labeled.

Company states are persisted transitions, not labels recomputed without history. Normal promotion is `FALLING -> INSIDER_ACCUMULATION -> BASE_FORMING -> EARLY_TURN -> CONFIRMED_TURN`. A downgrade requires two consecutive failed evaluations; a new 52-week low resets immediately to `FALLING`. The scoring configuration is the executable authority for gates.

Alert candidates are immutable. Delivery is idempotent on `(issuer_cik, alert_type, trigger_snapshot_id)`. The default cooldown is 14 days per `(issuer_cik, alert_type)`. During cooldown, a new alert is emitted only when state, severity, or important flag changes, or absolute score delta is at least 7. Suppression and delivery outcomes remain auditable.

Operational alerts cover source lag, quota/throttle saturation, schema drift, quarantine spikes, gate failures, stale manifests, and delivery failure. Logs use correlation IDs and redact secrets and raw personal/contact data.

## Consequences

Users get stable, explainable alerts and explicit degraded states. State history and delivery ledgers are required durable data.
