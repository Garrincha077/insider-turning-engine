# Phase-1 feature tournament validation — COMPLETE / F2 FAIL

Date: 2026-09-22

This checkpoint records the terminal result of the frozen Phase-1 insider
feature tournament. It is a status document only; it does not alter any
predeclared selection, continuity, valuation, validation, or OOS rule.

## Validation continuity — COMPLETE

The performance-blind 2021-2022 validation continuity program is complete.

Frozen validation scope:

- rows: **7,493**;
- primary horizon: **126 XNYS sessions**;
- candidate: `F2_DIRECT_VS_INDIRECT`;
- preferred: `INDIRECT_ONLY`;
- complement: `DIRECT_ONLY`;
- scope semantic key:
  `sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3`.

The original continuity audit had:

- 7,302 ordinary adjusted-price rows;
- 99 provider-complete same-security symbol changes;
- 51 provider-complete holder transformations;
- 41 unresolved rows.

All 41 unresolved rows were resolved without reading validation performance:

- exact-action prior evidence: 8;
- HSDT primary: 1;
- stock-dividend primary: 5;
- incomplete-stock-merger primary: 8;
- SPAC share-exchange primary: 8;
- CBTX symbol-change primary: 1;
- final long-gap primary SEC evidence: 10.

Final continuity workflow run: **35708221515 — SUCCESS**.

Final release:
`research-phase1-insider-feature-tournament-validation-final-continuity-v1`.

Final contract:
`validation-final-continuity.json`.

Asset SHA-256:
`sha256:16a9814003c232d58d9e0f70a85b72beb7e37d04c81b390dbd3cfd6199c7956a`.

Final affected-row contract:

- classified rows: **191 / 191**;
- unresolved rows: **0**;
- same-security continuity: **11**;
- same-security symbol changes: **101**;
- transformed holder consideration: **79**;
- affected-key SHA-256:
  `sha256:fe81e31a04a4e5f69eb07778685bc8799860eef37653af5479d79c5aefc1c18f`.

## Frozen F2 validation — COMPLETE

Validation workflow run: **35708794327 — SUCCESS**.

Release:
`research-phase1-insider-feature-tournament-validation-v1`.

Result asset:
`validation-results.json`.

Result SHA-256:
`sha256:1c2b9107b520e360e7251519a5a5a945febeb41cac307d8d5e3e6e05adf1682c`.

Archive SHA-256:
`sha256:7470bacd8417d28f27a910c946e6d45d6ee2a0549f0585535ff78b0600cef861`.

The workflow itself is green. The frozen candidate result is:

**`VALIDATION_FAIL_FROZEN`**

This is a research result, not an infrastructure failure.

### Primary 126-session validation result

Preferred `INDIRECT_ONLY`:

- mature N: **1,646**;
- distinct issuers: **950**;
- SPY-excess mean: **+46.2971%**;
- SPY-excess median: **-9.9211%**;
- excess win rate: **35.2369%**.

Complement `DIRECT_ONLY`:

- mature N: **5,143**;
- distinct issuers: **2,411**;
- SPY-excess mean: **+48.3845%**;
- SPY-excess median: **-6.1212%**;
- excess win rate: **39.2378%**.

Frozen incremental comparisons, preferred minus complement:

- pooled event-weighted: **-2.0874 percentage points**;
- issuer equal-weight: **-20.1160 pp**;
- entry-session equal-weight: **-11.6794 pp**;
- top-1%-removed: **-3.7717 pp**;
- 2021 event-weighted: **+1.0837 pp**;
- 2022 event-weighted: **-5.3152 pp**.

Validation maturity:

- valued rows: **7,375**;
- missing rows: **118**;
- all 118 missing rows are
  `MISSING_EXACT_TERMINAL_HOLDER_BAR`;
- no nearest-bar substitution was used.

### Frozen eight-check decision

PASS:

- preferred mature N >= 150;
- preferred distinct issuers >= 75;
- 2021 event-weighted incremental mean > 0.

FAIL:

- pooled event-weighted incremental mean > 0;
- pooled issuer-equal-weight incremental mean > 0;
- pooled entry-session-equal-weight incremental mean > 0;
- pooled top-1%-removed incremental mean > 0;
- 2022 event-weighted incremental mean > 0.

All eight checks were required, so the candidate fails the frozen validation
rule.

## Current research boundary

- validated candidate count: **0**;
- feature reselection: **not allowed in this frozen tournament version**;
- orientation flip: **not allowed**;
- threshold retuning: **not allowed**;
- replacement feature: **not allowed**;
- 2023+ OOS: **still sealed**;
- production scoring: **unchanged**.

The correct terminal action for this tournament version is to preserve the
failure exactly as observed. Do not open 2023+ OOS for this failed F2 candidate.

Any future feature research must start as a separately predeclared version. The
known 2021-2022 result can no longer be treated as untouched validation for a
new rule chosen after seeing this outcome.
