# Phase-1 F2 validation exact long-gap diagnostics gate

Frozen after the validation continuity audit and before any validation
performance is read.

## Source

Release:
`research-phase1-insider-feature-tournament-validation-continuity-audit-v1`

Archive SHA-256:
`sha256:e1e34180cbd8e115412d88e75abc39711b1645515396b4f6bb52b19a6d7716d5`

The source contains exactly 11 unresolved rows whose
`resolutionSource=long_internal_gap`.

## Diagnostic rule

Reuse the frozen Phase-1 gap diagnostic algorithm.

For each unresolved long-gap row, read only:

- date;
- ticker;
- volume;
- trade_count;
- terminal_candidate.

Recompute the maximum internal XNYS-session gap between entry and the frozen
126-session target. The recomputed gap must equal the value frozen by the
validation continuity audit.

Publish:

- previous observed session;
- first missing session;
- last missing session;
- next observed session;
- max gap sessions.

Every gap must be bracketed by observed regular bars.

## Market source

Only the pinned 2016-2022
`research-market-alpaca-v1` corpus is allowed. 2023 must not be mounted.

No OHLC value, return, SPY-excess outcome or validation result is read.

## Boundary

These diagnostics do not resolve a continuity row.

They are evidence-location metadata for:

- the one HSDT prior-security candidate;
- the ten long-gap rows requiring new primary evidence.

Validation performance remains blocked until every continuity residual has a
deterministic final decision.
