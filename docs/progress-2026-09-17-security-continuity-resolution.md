# Phase-1 security continuity resolution — progress checkpoint (2026-09-17)

This document freezes the current research state before any corrected-performance recomputation. It is intended as the handoff point for the next research session/chat.

## Non-negotiable research boundaries

- Development cohort: 2016–2020.
- Outcome window: through 2022 only.
- 2023+ OOS remains sealed and must not be opened, read, searched, or used for decisions.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- Continuity/security-identity resolution must remain performance-blind: do not read `raw_*`, `excess_*`, `mae_*`, OHLC, or realized performance while deciding identity/continuity rules.
- Do not change the predeclared 10-XNYS-session long-gap threshold after seeing results.
- Do not change B1/B2/B4 definitions or production scoring based on these continuity findings.

## Baseline research state

The frozen B1/B4 work is already complete and persisted. The primary evaluation horizon remains 126 trading sessions, with 21/63/126/252 also evaluated. P0 remains exploratory rather than formal alpha evidence.

## Successful full-cohort continuity run

Workflow run: `35272112415`

Artifact: `phase1-security-continuity-ledger-35272112415`

Artifact digest:

`sha256:7e67aa271d60f8f3837e3db76f3a8a0e20312fdea5baf7f031e387d25349c4b8`

The run completed successfully after fixing the Alpaca corporate-actions wire contract. The correct raw API structure is `payload["corporate_actions"][bucket]`; the research request remains restricted to the frozen 13 corporate-action types.

The full ledger scanned:

- 6,094 B1 events.
- 24,376 event-horizon rows.
- 105 unique events affected by continuity/corporate-action diagnostics.
- 54 event-horizon rows initially classified `UNRESOLVED_CONTINUITY`.
- Corrected-performance stage correctly remained blocked.

Initial unresolved composition:

- 34 rows: `long_internal_gap` only.
- 18 rows: `stock_dividends`.
- 2 rows: same-day cash + stock merger provider records (FG and POPE).

The unresolved set represented 31 unique events and 18 tickers.

## Repo checkpoints already merged

- PR #13 — recorded the frozen continuity-ledger result and unresolved set.
  - merge SHA: `2f5b7f3689c3ed3f98392c15ea8aa274af7efd41`
- PR #14 — added frozen performance-blind long-gap diagnostics.
  - merge SHA / current main at this checkpoint: `818953aac0dda3c71197a1f5bb1409a07ead6aa4`

The working branch for the next stage is:

`research/security-continuity-resolution`

At the time of this checkpoint it is identical to `main` at `818953aac0dda3c71197a1f5bb1409a07ead6aa4`.

## Frozen long-gap diagnostic

Workflow run: `35272945732`

Artifact: `phase1-security-gap-diagnostics-35272945732`

Artifact digest:

`sha256:f203552b0b52e51ec91338827ea8d87b2989fe5bbe462a4e36b3862f36ccee08`

The diagnostic completed successfully and remained performance-blind:

- 34 frozen long-gap event-horizon rows.
- 16 unique events.
- 12 tickers.
- All gaps were bracketed by observed regular bars.
- `priceFieldsRead=[]`.
- `performanceRead=false`.
- `oosOpened=false`.
- Market fields used only for presence diagnostics: `date`, `ticker`, `volume`, `trade_count`, `terminal_candidate`.

## Performance-blind identity/continuity findings

### Long-gap cases that should resolve as same-security continuity

Primary/public filing and exchange-history checks support same-security continuity across the frozen gap for these tickers:

- `KMPH` — Nasdaq → OTCQB → Nasdaq under the same common equity identity; later 1:16 reverse split is an adjusted corporate action, not a new economic security.
- `GIX.U` — same GigCapital2 SPAC unit through the relevant frozen window.
- `SBE.U` — same Switchback SPAC unit through the relevant frozen window; the later business-combination separation occurs outside the relevant unresolved window.
- `LMFA`
- `JXSB`
- `DGICB`
- `NEN`
- `VBFC`
- `NSEC`
- `MGYR`
- `CMCT`

These account for 33 of the 34 initially unresolved long-gap event-horizon rows and should resolve to same-security price continuity after a frozen fixture/contract is implemented.

### IPAS must NOT be treated as same-security continuity

`IPAS` is the important exception.

Pareteum completed its acquisition of iPass on 2019-02-13. Each iPass share was converted into **1.17 TEUM shares**. This transformation occurs before the relevant 252-session exit.

Therefore the relevant IPAS row should resolve as:

- state: `TRANSFORMED_HOLDER_CONSIDERATION`
- successor: `TEUM`
- stock consideration: `1.17` successor shares per IPAS share

Do not classify IPAS as merely continuous through a trading suspension/gap.

## Stock-dividend cases

Frozen Alpaca corporate-action records and primary filings are consistent on the holder quantity multipliers:

- `BOTJ`: 10% stock dividend → factor `1.10`.
- `GNTY`: 10% stock dividend → factor `1.10`.
- `HWBK`: 4% stock dividend → factor `1.04`.
- `LARK`: 5% stock dividend → factor `1.05`.

Alpaca `adjustment=all` does not itself make these stock-dividend holder quantities disappear from the continuity problem, so the resolution contract must explicitly carry the share multiplier rather than silently treating these rows as ordinary unchanged-share price continuity.

These 18 initially unresolved event-horizon rows should become deterministic holder-consideration transformations.

## FG and POPE merger cases

The initial provider view showed separate same-day cash-merger and stock-merger records. Do not add those records together mechanically.

Primary merger documents establish deterministic treatment for a passive/non-electing holder:

### FG

For F&G (`FG`), a non-electing holder receives:

- `0.2558` FNF shares per FG share.

Use this as the frozen passive-holder/no-election contract for the research correction rather than inventing an average election or summing provider cash + stock records.

### POPE

For Pope Resources (`POPE`), a non-electing holder is treated as a stock-election holder and receives:

- `3.929` RYN shares per POPE unit.

Use this frozen passive-holder/no-election contract.

Thus the two initially unresolved merger rows should resolve to `TRANSFORMED_HOLDER_CONSIDERATION`.

## Current interpretation of the original 54 unresolved rows

Before implementation/rerun, the evidence supports the following deterministic resolution map:

- 33 long-gap rows → same-security continuity.
- 1 IPAS long-gap row → transformed holder consideration (`1.17 TEUM`).
- 18 stock-dividend rows → transformed holder quantity using the frozen stock-dividend factor.
- 1 FG row → transformed holder consideration (`0.2558 FNF`).
- 1 POPE row → transformed holder consideration (`3.929 RYN`).

Total: 54 rows.

This is a performance-blind research conclusion only. It must be encoded and tested before any corrected performance is read.

## Exact next implementation gate

Continue on `research/security-continuity-resolution` and do the following in order:

1. Create a machine-readable frozen resolution/fixture contract covering all 54 formerly unresolved rows.
2. Encode the 33 same-security gap resolutions without changing the 10-session diagnostic threshold.
3. Encode IPAS → TEUM `1.17`.
4. Encode stock-dividend holder multipliers for BOTJ/GNTY/HWBK/LARK.
5. Encode passive/no-election merger transformations:
   - FG → FNF `0.2558`.
   - POPE → RYN `3.929`.
6. Add regression tests proving:
   - fixtures apply only on/after their effective dates;
   - no 2023+ metadata is accepted;
   - performance fields are not read during continuity resolution;
   - no unresolved row can silently fall through to ordinary price continuity;
   - frozen provider/identity rules cannot expand without an explicit research change.
7. Add/run a performance-blind resolution workflow using the already frozen continuity and market evidence.
8. Require `UNRESOLVED_CONTINUITY == 0` before opening the corrected-performance gate.
9. Only after that gate is green, create a separate corrected-performance workflow. Preserve B1/B2/B4 definitions and primary horizon 126.
10. When corrected performance is eventually computed, label it research/descriptive and preserve the current P0 exploratory limitation; do not call mean excess return formal alpha without dependence-aware/calendar-time/HAC robustness.

## Do not do next

- Do not inspect 2023+ OOS.
- Do not inspect returns to decide which continuity rule to use.
- Do not relax the 10-session threshold because a case is inconvenient.
- Do not drop difficult rows merely because they hurt performance.
- Do not alter B1/B2/B4 definitions or production scoring.
- Do not reinterpret FG/POPE provider cash + stock records by naive addition.
- Do not treat IPAS as simple same-ticker continuity through its full 252-session window.

## Target end state for the next session

A green, auditable, performance-blind continuity-resolution artifact with zero unresolved rows, committed through normal CI. Only then proceed to a separately gated corrected-performance recomputation.
