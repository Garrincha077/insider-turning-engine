# Phase-1 F2 validation exact-action prior-evidence resolution gate

Frozen: 2026-09-21 after the performance-blind validation prior-evidence audit
and before any validation outcome is read.

## Source audit

Release:
`research-phase1-insider-feature-tournament-validation-prior-evidence-v1`.

Asset:
`validation-prior-evidence-audit.json`.

SHA-256:
`sha256:6d261d773a47b311b18827fece4307105788be17ac6ece16d38daa4b27974361`.

The source audit contains 41 unresolved validation continuity rows partitioned
as:

- 8 `PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE`;
- 1 `LONG_GAP_PRIOR_SECURITY_CANDIDATE`;
- 22 `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`;
- 10 `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`.

This gate resolves **only** the 8 exact-action provider candidates.

Frozen 8-row semantic-key digest:
`sha256:fbd00d6952afad146499ae0cc998c1c79bee8ab15084eae4bdd45899bab8cb34`.

## Resolution rule

A row is eligible only when the source audit category is exactly
`PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE` and all frozen matching prior
contracts agreed on one substantive holder-economic fingerprint.

The resolver copies the audit-frozen normalized economics, not a newly chosen
provider record:

- result state;
- successor symbol;
- normalized successor quantity factor;
- normalized cash per entry share;
- normalized basket, if any;
- the sole schema-label pair
  (`resolutionDecision`, `transformationKind`);
- the exact candidate corporate-action ID set;
- the audit-frozen example effective date.

The effective date must satisfy:

`entrySession < effectiveDate <= targetExitSession`.

No row is resolved if the audit-frozen schema-label set is not singular, the
economic fingerprint is incomplete, the action-ID set is empty, or the
effective date is outside the row horizon.

Classification source:
`VALIDATION_EXACT_ACTION_PRIOR_EVIDENCE_REUSE`.

Evidence class:
`PRIOR_FROZEN_EXACT_ACTION_ECONOMIC_AGREEMENT`.

## Expected normalized economics

The 8 rows contain only these already-frozen holder outcomes:

- BOTJ stock dividend: BOTJ × 1.1;
- GNTY stock dividend: GNTY × 1.1;
- HWBK stock dividend: HWBK × 1.04;
- CLDB stock-and-cash merger: FMNB × 1.75 + USD 28 per entry share;
- WPF same-security symbol change: ALIT × 1.

No new security interpretation is created by this resolver.

## Residual after this stage

The exact-action resolver must output exactly 8 resolved rows and leave
**33 unresolved** validation continuity rows.

The one long-gap prior-security candidate remains unresolved. It requires a
separate interval-specific evidence check before any reuse.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false;
- 2023+ remains sealed.

No validation return may be read until all residual continuity rows reach zero
unresolved under separately frozen rules.
