# Phase-1 B3 continuity-corrected development + robustness — 2026-09-21

## Corrected development result

Workflow run **35634832574** — SUCCESS.

Release: `research-phase1-b3-continuity-corrected-development-v1`.

Assets:

- `b3-continuity-corrected-development-2016-2020.tar.gz`
  SHA-256 `sha256:b7b058a2e82cb072876804178e9af6e247fa9dc70b6f93a3f3c8e32ffe67c8be`
- `summary.json`
  SHA-256 `sha256:2de0fdd83e2cfbce9f4978bfed33fe34c7d30a2f4d207850d2e5e1f55e64760f`

Frozen scope:

- 29,930 exact-entry development events;
- 119,720 event-horizon rows;
- 264 final continuity-contract rows applied;
- 50 same-ticker stock-dividend rows normalized to market quantity 1.0 because
  the frozen Alpaca dataset uses `adjustment=all`;
- MAE not recomputed;
- validation unopened;
- 2023+ OOS sealed;
- production scoring unchanged.

At the primary 126-session horizon:

- matured outcomes: **29,072** vs canonical **29,069**;
- raw mean: **+13.9458%**;
- raw median: **+6.5495%**;
- SPY excess mean: **+4.0286%**;
- SPY excess median: **-2.7248%**;
- SPY excess win rate: **44.8473%**.

Versus the canonical uncorrected 126-session result:

- matured outcomes: **+3**;
- raw mean delta: **-0.0635 percentage points**;
- SPY excess mean delta: **-0.0629 percentage points**;
- median and win-rate changes are negligible.

The correction therefore validates security continuity without materially
changing the descriptive B3 development profile.

## Corrected robustness result

Workflow run **35635187501** — SUCCESS.

Release: `research-phase1-b3-continuity-corrected-robustness-v1`.

Asset:

- `b3-corrected-robustness.json`
  SHA-256 `sha256:06e5a5b133de599d6179fbbb6a2dc9cdcc47e906f3b617564da5a818fac95e96`

The robustness rule was frozen before corrected outcomes were observed and
reuses the prior B1/B3 warning semantics unchanged.

Primary 126-session diagnostics:

- event-weighted SPY excess mean: **+4.0286%**;
- issuer equal-weight mean: **+5.0390%**;
- entry-session equal-weight mean: **+3.3464%**;
- positive-mean development years: **3 / 5**;
- top-1%-removed mean: **-0.2021%**.

Frozen warning conditions:

- issuer equal-weight mean non-positive: **false**;
- entry-session equal-weight mean non-positive: **false**;
- fewer than three positive-mean years: **false**;
- top-1%-removed mean non-positive: **true**.

Final corrected progression:

`BLOCK_HAC_AND_OOS`

Continuity correction therefore does not remove the right-tail sensitivity that
blocked the original B3 robustness progression.

## Current research boundary

- B3 continuity contract: **264 / 264 classified, 0 unresolved**
- corrected development: **complete**
- corrected frozen robustness: **complete**
- HAC stage: **not opened**
- validation 2021-2022: **not opened for the next methodology stage**
- 2023+ OOS: **sealed**
- production scoring: **unchanged**

## Next research step

The benchmark family can now be compared on its completed development evidence,
with B3 represented by the continuity-corrected result.

Because corrected B3 remains tail-sensitive and `BLOCK_HAC_AND_OOS`, do not
promote B3 to formal-alpha evidence and do not open OOS.

The next methodology work should be a predeclared benchmark/feature-tournament
transition: document what the simple B0/B1/B2/B3/B4 benchmarks establish,
freeze the insider-feature candidate set and anti-overfitting rules, and only
then run development feature comparisons. Turning/technical confirmation
remains downstream of the insider-only feature tournament.
