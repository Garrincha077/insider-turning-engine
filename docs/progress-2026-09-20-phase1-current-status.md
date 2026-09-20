# Phase-1 current status — 2026-09-20

This is the compact live checkpoint. For operational continuation,
`docs/HANDOFF.md` remains authoritative. Older dated progress files are audit
history.

## Benchmark family

| Benchmark | Meaning | Current state |
| --- | --- | --- |
| B0 | any qualified open-market purchase | development descriptive complete |
| B1 | canonical CMP opportunistic purchase | continuity-corrected development/robustness work complete; HAC/OOS blocked |
| B2 | independent-owner cluster | development complete |
| B3 | company net buying | development + robustness complete; performance-blind continuity resolution active |
| B4 | B1 AND B2 exact-session intersection | development complete |

## B3 completed data/methodology gates

- original P/S PIT history: **40/40 quarters PASS**, 570,291 filings
- amendment scope: run **35471756336**
- supporting evidence: run **35472366209**, 1,551/1,551 predecessor filings and 596/596 zero-transaction amendments
- lifecycle reconciliation: run **35499189795**, **8/8 shards PASS + merge PASS**
- effective qualified P/S rows end-2022: **1,570,066**
- B3 definition frozen before performance: `research-phase1-b3-definition-v1`
- raw candidates 2016-2020: **147,164**
- exact-XNYS dedup retained events: **35,829**
- PIT identity eligible: **34,472** / 35,829
- 2023+ OOS: **sealed**
- production scoring: **unchanged**

## B3 development result — COMPLETE

Workflow run **35502095184**.

- exact-entry matched events: **29,930**
- exact-entry coverage: **86.8241%**
- coverage tier: **C_EXPLORATORY**
- 126-session matured: **29,069**
- 126-session raw mean / median: **+14.01% / +6.54%**
- 126-session SPY excess mean / median: **+4.09% / -2.73%**
- 126-session excess win rate: **44.84%**

These are development-only descriptive figures, not an alpha or production
claim.

## B3 robustness result — BLOCK_HAC_AND_OOS

Latest green robustness run: **35502779482**.

At the primary 126-session horizon:

- event-weighted SPY excess mean: **+4.0915%**
- issuer equal-weight mean: **+5.0763%**
- entry-session equal-weight mean: **+3.4260%**
- positive-mean years: **3 / 5**
- top-1%-removed mean: **-0.1974%**
- blocking warning: **true**
- progression: **BLOCK_HAC_AND_OOS**

The frozen warning that fires is
`top1PctRemovedMeanNonPositive=true`. Do not retune the rule after observing
this result.

## B3 performance-blind continuity resolution — CURRENT ACTIVE WORK

Authoritative continuity ledger run **35502394856**:

- event-horizon rows: **119,720**
- unresolved rows: **264**
- unique affected events: **146**
- unique issuer/ticker identities: **67**
- 200 long-internal-gap rows
- 64 provider-action ambiguity rows

Deterministic candidate run **35502978548** reduced this to:

- deterministic candidates: **102**
- residual: **162**

Evidence-only residual work then completed successfully:

- bounded P/S PIT corroboration: run **35503316854**
- successor corporate-action inventory: run **35503492411**
- accession-pinned SEC security-title audit: run **35503698067**
- bounded all-Form345 corroboration: run **35504002615**

Strict multi-source synthesis run **35507255962** then added **71**
performance-blind same-security candidates.

Subsequent performance-blind continuity gates:

- residual-91 scope freeze: run **35507445541**, 91 rows / 35 issuer-tickers;
- provider primary-source resolution: run **35507604004**, **4 / 4** provider
  ambiguities resolved as same-security symbol changes;
- residual-87 scope freeze: run **35507696537**.

Current frozen state:

- SPAC-unit primary resolution: run **35507997799**, 4 rows resolved;
- one-sided primary resolution: run **35508257853**, 20 rows resolved;
- residual-63 scope freeze: run **35508340176**;
- deterministic continuity candidates/resolutions: **201 / 264**
- residual unresolved rows: **63**
- residual issuer/tickers: **27**
- residual-63 key digest:
  `sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50`
- release: `research-phase1-b3-residual63-scope-v1`
- corrected performance remains **closed**
- final resolution contract remains **not created**
- 2023+ remains **sealed**

See `docs/progress-2026-09-20-b3-residual63.md`.

## Immediate sequence

1. Preserve the exact 63-row residual continuity scope.
2. Resolve ticker-change/title-change identities only from pinned primary
   evidence, without reading returns.
3. Continue through overlapping/changed security-title and remaining one-sided
   buckets with fail-closed rules.
4. Create the final B3 continuity contract only when every frozen row is
   deterministically classified.
5. Recompute corrected B3 development performance only after a zero-unresolved
   continuity gate.
6. Reapply the already frozen B3 robustness semantics. No retuning.
7. HAC/OOS remains blocked unless the frozen progression rules later permit it.
8. Keep 2023+ sealed until the owner explicitly authorizes OOS after all prior
   methodology/validation gates are satisfied.
