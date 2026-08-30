# ADR 0005: Data quality and threat model

- Status: Accepted
- Scope: untrusted inputs, derived data, publication

## Context

Regulatory documents and vendor feeds can be malformed, adversarial, stale, duplicated, or economically implausible. The product is decision support, so silent corruption is a greater risk than temporary incompleteness.

## Decision

Raw source content is untrusted. Parsers enforce content-type and size limits, bounded decompression and nesting, safe XML settings, strict encodings, schema validation, numeric bounds, and timeouts. Fetchers allowlist hosts and block redirects or resolved addresses outside approved endpoints. Rendered strings are escaped; CSV exports neutralize formula prefixes. No raw markup is executed.

Quality checks run at field, record, batch, and cross-source levels. Required identity/time fields, decimal precision, sign conventions, duplicate keys, amendment chains, transaction-value arithmetic, ticker/CIK mapping, trading-calendar alignment, split adjustments, and impossible holdings are checked. Invalid required data is quarantined, never coerced. Warnings may publish only with explicit flags.

Publication gates are:

- canonical parse success at least 99.5%;
- market-data coverage at least 90%;
- core branch coverage at least 85%.

Below-gate output is blocked or explicitly `DEGRADED` according to the run policy; no green status is permitted. Metrics include numerator, denominator, excluded population, timestamp, and rule version.

Primary threats include source spoofing, SSRF, decompression/entity bombs, schema drift, replay/duplication, identifier collision, poisoned prices/fundamentals, lookahead, secret leakage, log injection, and alert flooding. Mitigations are allowlisted transport, hashes and provenance, idempotency, quarantine, point-in-time joins, secret redaction, bounded values, cooldowns, least privilege, and audit logs. Signals are not investment advice; the UI must expose provenance, freshness, and limitations.

## Consequences

Some source records remain unavailable until repaired, but failures are measurable, isolated, and reversible rather than silently entering scores.
