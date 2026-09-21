# Phase-1 F2 validation prior-evidence reuse audit

Frozen after the 7,493-row validation continuity audit identified 41
performance-blind unresolved rows and before any validation outcome is read.

## Source audit

Release:
`research-phase1-insider-feature-tournament-validation-continuity-audit-v1`.

Pinned assets:
- archive:
  `phase1-insider-feature-tournament-validation-continuity-audit-v1.tar.gz`
- archive SHA-256:
  `sha256:e1e34180cbd8e115412d88e75abc39711b1645515396b4f6bb52b19a6d7716d5`
- summary SHA-256:
  `sha256:28fee890338376b1024184cb6ecf3c5bb6a19519b86287a0c294f012c1ffcac1`

Frozen source facts:
- 7,493 validation rows;
- 41 unresolved;
- 22 provider ambiguity;
- 8 provider-incomplete-terms;
- 11 long-internal-gap;
- performanceRead=false;
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false.

## Frozen prior evidence sources

The audit may inspect only already-frozen, performance-blind continuity
contracts:

1. B1 continuity resolution:
   - repo file:
     `research/b1-security-continuity-resolution-v1.json`
   - SHA-256:
     `sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`.

2. B3 final continuity:
   - release:
     `research-phase1-b3-final-continuity-contract-v1`
   - asset:
     `b3-final-continuity-contract.json`
   - SHA-256:
     `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`.

3. Feature-tournament Stage-B final continuity:
   - release:
     `research-phase1-feature-tournament-stage-b-final-continuity-v1`
   - asset:
     `stage-b-final-continuity.json`
   - SHA-256:
     `sha256:24947122c8fa776dc6f5e8f628c5b45cdbec6551cf15df334421b405439b4518`.

4. Provider-completeness amendment:
   - release:
     `research-phase1-feature-tournament-provider-completeness-amendment-v1`
   - asset:
     `provider-completeness-amendment.json`
   - SHA-256:
     `sha256:faf787e918b953dcffbcc2b714c34873d6228031e25a09e509ee58e1a067fbb2`.

## Provider reuse rule

A provider unresolved row receives
`PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE` only when a frozen prior row has:

- the same issuer CIK;
- the same original ticker;
- the exact same non-empty corporate-action ID set.

All matching frozen sources must agree on the substantive holder economics:

- result state;
- successor symbol;
- successor quantity;
- cash per entry share;
- multi-component basket, if any.

Schema labels may differ across historical contracts. A label-only difference
does not create an economic conflict.

If exact-action matches disagree economically, the row is
`PROVIDER_PRIOR_EVIDENCE_CONFLICT`.

If no exact-action prior evidence exists, it is
`PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`.

This audit does not itself apply a resolution.

## Long-gap rule

Long-gap rows are deliberately more conservative.

Same issuer+ticker prior continuity evidence may create
`LONG_GAP_PRIOR_SECURITY_CANDIDATE` only when the frozen prior economic
fingerprint is internally consistent.

That status is **not** a resolution. Exact validation-gap dates must later be
checked against the underlying evidence interval before reuse is authorized.

No same-security prior evidence ->
`LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`.

Conflicting prior fingerprints ->
`LONG_GAP_PRIOR_SECURITY_CONFLICT`.

## Boundary

This is an audit-only stage:

- no validation return is read;
- no validation PASS/FAIL is computed;
- no 2023+ data is opened;
- no production score changes;
- no unresolved validation row is silently converted into a valued outcome.

The output partitions all 41 residual rows into reusable candidates, conflicts,
or genuinely new primary-evidence work.
