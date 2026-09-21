# Phase-1 feature tournament prior continuity overlap v2 gate

Frozen: 2026-09-21 after conservative v1 overlap reported 38 conflicts, exactly
equal to the 38 rows covered by both B1 and B3 contracts.

## Purpose

Distinguish substantive continuity disagreement from harmless schema
representation differences between the already-frozen B1 and B3 contracts.

No prior resolution is changed. No feature outcome is read.

## Inputs

The v2 pass consumes the same immutable inputs as v1:

- 210-row unresolved feature-tournament scope, asset SHA-256
  `4882e009646ea117d123b5f95ae41ea700203dd470d3b24be2cd1592eebe9afd`;
- B1 54-row frozen resolution contract, SHA-256
  `88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`;
- B3 264-row final continuity contract, SHA-256
  `22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`.

## Economic-equivalence rule

Exact semantic-key matching is unchanged.

For rows covered by both prior contracts, v2 compares substantive holder
economics:

- final result state;
- successor symbol;
- normalized share quantity factor;
- normalized cash consideration;
- normalized multi-component basket.

Numeric formatting differences such as `1` versus `1.0` are equivalent.
Missing cash in the older B1 schema is treated as zero; therefore any non-zero
cash consideration in B3 still creates a conflict.

Schema labels such as `resolutionDecision` and `transformationKind` are
reported but do not by themselves create an economic conflict.

Any disagreement in result state, successor, quantity, non-zero cash or basket
remains fail-closed.

## Boundary

This is still an overlap/diagnostic stage only:

- resolutionApplied=false;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false.
