# Insider Turning Engine v1 test contract

This document defines release-blocking behavior, independent of implementation language. Tests use deterministic clocks, fixed trading calendars, and frozen provider fixtures. JSON Schema validation uses draft 2020-12 with format assertions enabled.

## Required suites

### 1. Interchange schemas

- A minimal and a fully populated canonical transaction validate. Each requires schema version, source, 'ingestedAt', and 'runId', plus normalized 'economicClassification' and tri-state 'rule10b51'. Unknown properties, non-padded CIK, numeric financial strings encoded as JSON numbers, malformed accession/hash, missing metadata/provenance, and out-of-range enum values fail.
- A manifest validates only with pinned versions, watermarks, quality measurements, immutable signal/artifact hashes, and score values in [0, 100].
- A signal snapshot validates all five score blocks, exact component names, state evidence, alerts, and provenance. A null fundamental requires 'fundamental' in 'excludedFactors'; a present fundamental forbids that exclusion.
- Compatibility rule: additive optional fields require a schema minor version; removing/renaming fields, changing meaning, or narrowing accepted values requires a major version.

### 2. Identity and lifecycle

- Redelivery of the same (provider, provider_record_id, content_hash) creates no new observation, transaction, or alert.
- 'transactionId' equals 'txn_' plus lowercase SHA-256 of normalized 'accessionNumber|ownerCIK|tableType|rowSequence'; identical tuples are stable across providers/runs and any changed tuple produces a different ID.
- The same provider ID with a new content hash creates a new observation and a drift/correction decision, never an overwrite.
- Ticker changes do not change issuer or transaction identity; point-in-time reads return the ticker valid at 'as_of'.
- One filing may map to multiple economic rows and multiple observations may support one transaction. Duplicate semantic rows remain distinct through source-row identity.
- An amendment creates a revision, closes the predecessor validity interval, and preserves both. A void has no active aggregate contribution. At most one revision is current.
- Low-confidence owner matches remain proposals; no silent fuzzy merge is allowed.

### 3. Point-in-time and replay

- For every selected input, assert 'knowledge_at <= as_of' or 'available_at <= as_of'.
- A trade dated Monday, accepted Wednesday, and first observed Thursday is absent Tuesday/Wednesday and eligible Thursday ('knowledge_at' is Thursday).
- A record accepted before but observed after 'as_of' is absent. A provider correction observed after 'as_of' cannot change an existing historical snapshot.
- Current ticker, sector, split factor, index membership, price revision, or fundamental release is never joined into an earlier 'as_of'.
- Replaying identical pinned inputs and configuration produces byte-equivalent normalized values, scores, state evidence, hashes, and alert candidates; IDs/timestamps derived from the run must be controlled or excluded from equality.

### 4. Provider contract

Run every adapter against the same conformance harness:

- opaque cursor pagination has no loss across page boundaries; a crash before checkpoint commit safely redelivers the page;
- retryable, throttled, permanent-invalid, and not-found outcomes remain distinct;
- retry obeys server delay, bounded exponential backoff, jitter under a seeded RNG, and attempt limits;
- a fake clock proves aggregate SEC traffic never exceeds 6 requests in any one-second interval;
- timeouts, truncated content, wrong content type, changed schema, and malformed rows quarantine safely;
- secrets and authorization values are absent from records, exceptions, logs, and fixtures.

### 5. Scoring

- Parse the versioned YAML; reject unknown factors/operators, non-numeric weights, duplicate keys, out-of-range thresholds, or any weight set whose sum is not exactly 1 within machine-safe decimal tolerance.
- Golden vector:

| Model | Ordered component values | Expected score |
|---|---|---:|
| Market Pulse | 80, 70, 60, 50, 40, 90 | 67.0 |
| Company Insider | 80, 60, 40, 90 | 68.0 |
| Divergence | 70, 80, 60, 50 | 69.5 |
| Turn | 80, 70, 60, 50, 40, 100 | 68.5 |
| Total | divergence 70, conviction 80, cluster 60, opportunistic 40, base 75, ordinary RS 65, Mansfield RS 55, volume 50, fundamental 90 | 66.0 |
| Total, null fundamental | same values, fundamental null | 64.73684210526316 |

The null-fundamental case divides the remaining weighted sum 61.5 by 0.95. Missing any other factor fails scoring. Boundary inputs 0 and 100 remain in range. Production rounding, if introduced, occurs only after rule evaluation and is versioned.

### 6. State machine

- 'FALLING' requires both 'return_3m < 0' and 'close < ma50'; equality fails each strict comparison.
- 'INSIDER_ACCUMULATION' accepts exactly -20% drawdown, insider score 65, and qualified buy age 30 days; crossing any inclusive boundary the wrong way fails.
- 'BASE_FORMING' requires prior accumulation, no new 52-week low for 20 sessions, and exactly two or three of volatility contraction, volume dry-up, and MA20 flattening. One fails.
- 'EARLY_TURN' requires 'BASE_FORMING', turn score 60, improving 3-month ordinary RS over four weeks, and strictly positive four-week Mansfield-market slope. Slope zero fails.
- 'CONFIRMED_TURN' requires 'EARLY_TURN', close above MA50 on at least 5 of 10 sessions, and either Mansfield market at least zero or cost-basis reclaim.
- One failed evaluation does not downgrade; the second consecutive failure does. A passing evaluation resets the failure counter. A new 52-week low resets immediately to 'FALLING'.
- Transition tests prove no skipped promotion and preserve evidence and evaluation sequence.

### 7. Alerts and delivery

- 'MAJOR_INSIDER_BUY' triggers at conviction 80 plus value USD 250,000, at value USD 1,000,000 alone, or for any of 'strong_cluster', 'first_buy', 'largest_buy'; test just-below boundaries.
- 'STEALTH_ACCUMULATION' triggers only when insider 70, divergence 75, turn 45, no low for 20 sessions, and both required RS slopes are strictly positive.
- 'TURNING' triggers only on a transition to 'EARLY_TURN' or 'CONFIRMED_TURN' with total 75, insider 65, and divergence 65.
- Repeat delivery within 14 days is suppressed per (issuer_cik, alert_type). It is allowed when state, severity, or important flag changes, or absolute score delta is exactly 7 or more. Delta 6.999 remains suppressed.
- Candidate creation is idempotent; retries cannot duplicate a delivery. Emitted and suppressed decisions retain reasons.

### 8. Quality and threat controls

- Parse success 995/1000 passes and 994/1000 fails; market coverage 90/100 passes and 89/100 fails; core branch coverage 85/100 passes and 84/100 fails.
- Zero denominators yield 'NOT_EVALUATED', never an invented 100% rate. Each metric persists numerator, denominator, exclusions, time, and rule version.
- Below-gate output cannot appear healthy; blocked or degraded disposition is explicit and consistent between run and manifest.
- Adversarial fixtures cover oversized documents, compressed/entity expansion, deep nesting, invalid encoding, redirect/SSRF targets, formula-prefix strings, markup/script strings, extreme decimals, log newlines, duplicate replay, invalid revision chains, and alert floods.

### 9. Publication/consumer contract

- A consumer can render the dashboard using only a valid manifest and its referenced signal snapshots; no provider-specific field is required.
- Missing or hash-mismatched artifacts fail closed. Stale/degraded status, 'as_of', source watermarks, quality flags, score versions, state evidence, and alert reasons are visible to the consumer.
- Contract fixtures include at least one issuer in every state, each alert type, a suppressed alert, null fundamental renormalization, an amendment, a void, and a degraded manifest.

## Release gate

All schema, identity/lifecycle, point-in-time, scoring, state, alert, and security tests must pass. Provider live smoke tests may be conditionally skipped only when the provider is unavailable and the run is visibly degraded; deterministic provider conformance tests may not be skipped. Measured canonical parse success must be at least 99.5%, market coverage at least 90%, and core branch coverage at least 85%.
