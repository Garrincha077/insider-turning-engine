# Phase-1 B3 frozen residual-87 continuity scope gate

Frozen: 2026-09-20 after the residual-91 scope and the four-row provider
primary-source resolution were independently frozen.

## Purpose

Create the next immutable performance-blind continuity work queue by subtracting
only the four exact provider-resolution keys from the frozen 91-row scope.

## Authoritative inputs

Residual-91 scope:

- release: `research-phase1-b3-residual91-scope-v1`
- asset: `b3-residual91-scope.json`
- asset SHA-256:
  `sha256:f6ac0a711148af6229e7461b64c3034d3272646fbb7490219947f16b14267891`
- source key SHA-256:
  `sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58`

Provider primary resolution:

- release: `research-phase1-b3-provider-primary-resolution-v1`
- asset: `b3-provider-primary-resolution.json`
- asset SHA-256:
  `sha256:4f37195c3fda7a2db119f7391c8dbad4571d928aca80b78bc6e5630cdc48dfc1`
- exact resolution-key SHA-256:
  `sha256:8db525671fcc4381ca8b5e906f132df28fe64f5d6c7d5000699b48730cfc5f2c`

## Frozen residual-87 scope

The subtraction must produce exactly:

- **87 rows**
- **33 issuer/ticker identities**
- all rows sourced from `long_internal_gap`
- all rows with residual reason `NO_MATCHING_PRIOR_B1_EVIDENCE`
- residual key SHA-256:
  `sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742`

No provider row may remain. No row outside the residual-91 source may enter.

## Boundaries

- development cohort remains 2016-2020
- outcome/evidence ceiling remains 2022-12-31
- 2023+ OOS remains sealed
- 21/63/126/252 horizons remain frozen; 126 primary
- no price, return, MAE, tail, robustness, validation or OOS field is read
- production scoring remains unchanged
- corrected performance remains closed

## Next evidence work

The 87-row scope should be triaged only by pre-existing evidence buckets and
primary security/corporate-action evidence. Priority is:

1. ticker changed after the frozen long-gap pivot;
2. one-sided identity evidence;
3. same ticker on both sides but changed/overlapping security titles;
4. residual contradictory Form345 observations.

Every later rule must prove membership in this exact 87-row scope and remain
performance-blind.
