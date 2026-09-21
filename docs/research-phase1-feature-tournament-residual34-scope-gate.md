# Phase-1 feature tournament residual34 continuity scope gate

Frozen: 2026-09-21 after the POPE primary-evidence adjudication and before any
feature outcome was opened.

## Inputs

Residual35 scope:

- release `research-phase1-feature-tournament-residual-continuity-scope-v1`;
- asset SHA-256
  `bba0f3fd8c46c04e0ccd27a6b6a2a6ac0f8fcf074d89fee7239d5477f0574e01`;
- 35 rows = 1 prior-contract conflict + 34 unmatched rows.

POPE adjudication:

- release `research-phase1-feature-tournament-pope-adjudication-v1`;
- asset SHA-256
  `8c87c27a3689c1aa10c5d8881cf91de0bb078e97d6133968f1c7d0528afd18a4`;
- one conflict resolved from SEC primary evidence;
- passive/no-election outcome = 3.929 RYN per POPE unit, $0 cash.

## Mechanical exclusion

The adjudicated POPE semantic key is removed from residual35. No other key may
be removed.

Every surviving row must have the frozen overlap status
`NO_PRIOR_EVIDENCE_MATCH`.

Expected residual:

- **34 event-horizon rows**;
- **19 issuer events**;
- **14 issuers/tickers**;
- horizons: 21=1, 63=6, 126=8, 252=19;
- initial-audit sources: 17 long-internal-gap, 17 provider.

## Next research

Residual34 is the only scope requiring new event-coverage work. Existing B3
primary documents may be reused as factual evidence when their dates and
security identity cover a residual34 row, even though no old event-horizon
classification matched exactly.

Such document reuse must be coverage-based and performance-blind.

## Boundary

No returns, excess returns, MAE or feature outcomes are read. Validation remains
reserved, 2023+ OOS remains sealed, and production scoring is unchanged.
