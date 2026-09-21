# Phase-1 feature tournament prior continuity evidence overlap gate

Frozen: 2026-09-21 after the exact 210-row unresolved Stage-B scope was
published and before any feature outcome was opened.

## Purpose

Measure how much of the feature-tournament continuity problem can be resolved
using continuity evidence that was already frozen for B1 and B3. This gate does
not apply any resolution. It only identifies exact semantic event-horizon
matches and conflicts.

## Immutable inputs

Feature-tournament unresolved scope:

- release: `research-phase1-feature-tournament-stage-b-unresolved-scope-v1`
- asset: `stage-b-unresolved-scope.json`
- asset SHA-256:
  `sha256:4882e009646ea117d123b5f95ae41ea700203dd470d3b24be2cd1592eebe9afd`
- unresolved scope-key SHA-256:
  `sha256:b8ce80581a293dcac248a73b88a715accb796a9c73c5851c2499a5a10c5ea378`

Frozen B1 resolution contract:

- repo file: `research/b1-security-continuity-resolution-v1.json`
- SHA-256:
  `sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`
- rows: 54;
- final B1 unresolved: 0.

Frozen B3 final continuity contract:

- release: `research-phase1-b3-final-continuity-contract-v1`
- asset: `b3-final-continuity-contract.json`
- SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`
- rows: 264;
- final B3 unresolved: 0.

## Cross-cohort semantic key

Cohort-specific `eventNumber` is deliberately excluded from matching because
the same issuer event may have a different ordinal in B0, B1 and B3.

The exact portable key is:

- issuerCik;
- historical ticker;
- evaluationSession;
- entrySession;
- horizon;
- targetExitSession.

No fuzzy ticker/date matching is permitted.

## Conflict rule

If one prior contract matches, the row is a candidate for safe evidence reuse.

If both B1 and B3 match the same semantic key, their frozen classification
fingerprints must be identical. Any disagreement is reported as a conflict and
is not reusable automatically.

The comparison fingerprint includes final result state, successor symbol,
resolution decision, transformation kind, quantity factor, cash consideration,
and any multi-component basket.

## Boundary

This stage reads no return, excess, MAE or feature-outcome field and applies no
new resolution. 2021-2022 remains reserved from feature selection, 2023+
remains sealed, and production scoring is unchanged.
