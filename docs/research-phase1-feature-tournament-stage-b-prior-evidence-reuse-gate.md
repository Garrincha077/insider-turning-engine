# Phase-1 feature tournament Stage-B prior-evidence reuse gate

Frozen: 2026-09-21 after the exact 210-row unresolved continuity scope was
published and before any feature forward outcome was opened.

## Purpose

Reduce the frozen feature-tournament continuity residual by reusing only
already-frozen B1/B3 continuity decisions that match the **full historical
identity/event-horizon key**.

This is an evidence-reuse stage, not a performance stage. No forward return,
SPY-excess return, MAE, feature outcome, validation outcome or 2023+ OOS value
may be present or read.

## Immutable unresolved source

Source release:

- `research-phase1-feature-tournament-stage-b-unresolved-scope-v1`
- asset: `stage-b-unresolved-scope.json`
- SHA-256:
  `sha256:4882e009646ea117d123b5f95ae41ea700203dd470d3b24be2cd1592eebe9afd`
- unresolved rows: **210**
- unresolved scope-key SHA-256:
  `sha256:b8ce80581a293dcac248a73b88a715accb796a9c73c5851c2499a5a10c5ea378`
- unresolved evidence-key SHA-256:
  `sha256:fe057af7f707914f4edd11f9308a12fbb22f3ea30c867e6a5f764a505003b5d6`

## Frozen prior evidence

### B3 final continuity contract

- release: `research-phase1-b3-final-continuity-contract-v1`
- asset: `b3-final-continuity-contract.json`
- SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`
- classified rows: **264 / 264**
- unresolved rows: **0**
- performanceRead=false.

### B1 frozen continuity resolution

Repository contract:

- `research/b1-security-continuity-resolution-v1.json`
- frozen Git blob:
  `f56e88f1d1ec3b8c90f005bf7b7805b7ad25ade3`
- contract rows: **54**
- performanceRead=false;
- OOS remains closed.

The B3 final contract independently records the prior B1 continuity evidence
lineage as
`sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`.

## Exact-key rule

Prior evidence may be reused only when all six historical fields match exactly:

1. issuer CIK;
2. historical ticker;
3. evaluation session;
4. entry session;
5. horizon;
6. target exit session.

The feature-tournament event number is deliberately **not** part of the
cross-benchmark matching key because B0/B1/B3 assign different event numbers
to the same historical issuer event. The current Stage-B event number is
preserved in the new contract.

No fuzzy symbol, nearest-date, same-action-only or same-issuer-only match is
allowed.

If both B3 and B1 contain the same exact historical key, their normalized
continuity semantics must agree. B3 is then the recorded reuse source. A
semantic disagreement is a hard failure.

## Performance-blind overlap audit

The key-only audit, frozen before feature outcomes, found:

- exact B3 matches: **168**;
- additional B1-only exact matches: **8**;
- total prior-evidence reuse: **176 / 210**;
- residual requiring primary evidence: **34**.

The 8 B1-only rows are the exact historical rows for:

- JXSB: 3;
- DGICB: 2;
- LARK: 1;
- GNTY: 2.

The residual 34 rows comprise:

- **19** unique feature-tournament events;
- **14** unique issuers;
- **14** unique historical tickers;
- **17** `long_internal_gap` rows;
- **17** `provider` rows.

Residual horizons:

- 21 sessions: 1;
- 63 sessions: 6;
- 126 sessions: 8;
- 252 sessions: 19.

These are continuity/evidence counts only. They were not selected from
performance.

## Output contract

The workflow must publish two immutable JSON outputs:

1. `stage-b-prior-evidence-reuse.json`
   - exactly 176 reused rows;
   - full current Stage-B historical key;
   - normalized continuity decision;
   - reuse source and prior evidence event identity;
   - no performance fields.
2. `stage-b-residual-primary-evidence-scope.json`
   - exactly 34 rows not covered by an exact prior-evidence key;
   - preserves the frozen Stage-B continuity diagnostics;
   - becomes the only scope authorized for new primary evidence.

## Progression boundary

A successful reuse run authorizes only primary-evidence resolution of the
frozen 34-row residual.

Discovery outcomes remain closed until:

1. all 34 residual rows are deterministically classified;
2. the 176 reused rows and 34 new decisions are merged into a 210-row final
   Stage-B continuity contract;
3. that final contract reports **zero unresolved rows**.

Validation 2021-2022 remains untouched by feature selection/tuning. 2023+
remains sealed. Production scoring is unchanged.
