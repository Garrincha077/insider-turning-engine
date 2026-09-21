# Phase-1 B3 continuity-corrected development-performance gate

Frozen: 2026-09-21 **before** reading or computing any continuity-corrected B3
outcome.

## Purpose

Recompute the already-frozen 2016-2020 B3 development cohort under the completed
264/264 performance-blind security-continuity contract. This is a data-validity
correction only. It does not alter B3 selection, thresholds, event construction,
deduplication, horizons, benchmark, validation/OOS boundaries or production
scoring.

## Immutable inputs

### Canonical B3 development cohort

- release: `research-phase1-b3-development-v1`
- asset: `b3-development-descriptive-2016-2020.tar.gz`
- SHA-256:
  `sha256:d90a2f08483d6710bb2f2715fa9049b64fd27a3979e7e63e5fb792f3c0274ae7`
- exact-entry matched events: **29,930**
- event-horizon rows: **119,720**
- development evaluation-session cohort: **2016-2020**
- outcome market boundary: **through 2022-12-31 only**

### Final B3 continuity contract

- workflow run: `35540610883`
- release: `research-phase1-b3-final-continuity-contract-v1`
- asset: `b3-final-continuity-contract.json`
- asset SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`
- classified rows: **264 / 264**
- unresolved: **0**
- exact key SHA-256:
  `sha256:6125fe42a9559ce937d385b4f49d1a74d33ce1caad7f5ec8487ce72bf854082b`

The 264 contract rows must map uniquely to the canonical B3 event-horizon rows
using issuer CIK, historical ticker, evaluation session, entry session,
horizon and exact target session. Event numbering must reproduce the frozen
canonical event order.

### Frozen market data

Release: `research-market-alpaca-v1`.

Only the already-pinned 2016-2022 annual archives may be used. The 2023 archive
must not be downloaded or present.

The market backfill was requested with:

- SIP feed;
- `adjustment=all`;
- `asof=-`, disabling current-symbol remapping.

The exact annual asset hashes remain those in
`research/b3-development-performance-v1.json`.

## Frozen target and benchmark rules

- horizons: **21 / 63 / 126 / 252 XNYS sessions**
- primary horizon: **126**
- entry: canonical exact `entrySession` open
- target: canonical exact `exit_<horizon>` session
- no nearest/later-bar substitution
- benchmark: SPY exact same entry open and target close
- cash consideration earns **0% nominal return** between effective date and the
  already-frozen target date
- missing outcomes are explicit; never impute zero and never silently drop

The corrected runner must also reproduce every canonical exact target date from
the XNYS/SPY session calendar. A target-date mismatch fails closed.

## Frozen terminal-holder valuation

For an event-horizon row not present in the final continuity contract:

`terminal value = 1.0 × original ticker exact-target adjusted close`.

For a contract row:

### SAME_SECURITY_CONTINUITY

Use the original ticker exact-target adjusted close with market quantity 1.0.

### SYMBOL_CHANGED_SAME_SECURITY

Use 1.0 × the contract successor ticker exact-target adjusted close.

### TRANSFORMED_HOLDER_CONSIDERATION

Default rule:

`terminal value = cashPerEntryShare + legal successor quantity × exact-target successor close`.

Cash-only consideration is valid when successor quantity is zero.

#### Adjusted-bar stock-dividend exception

The frozen market dataset uses Alpaca `adjustment=all`, which adjusts
historical bars for corporate actions. The final contract contains 50
`STOCK_DIVIDEND_QUANTITY` rows, all with successor ticker equal to the
original ticker.

For those exact rows only:

- preserve the legal share factor from the final contract as provenance;
- use **market valuation quantity = 1.0**, not the legal factor;
- use the same ticker exact-target adjusted close;
- do not apply a second stock-dividend/split quantity adjustment.

Any `STOCK_DIVIDEND_QUANTITY` row whose successor ticker differs from the
original ticker fails closed.

### TRANSFORMED_MULTI_COMPONENT_CONSIDERATION

For the single NBA.U row, value every basket leg independently at the exact
target session:

`terminal value = sum(quantity_i × close_i) + cash`.

The frozen basket is exactly:

- 1 × `MIMO` common stock;
- 1 × `MIMO WS` public warrant.

If any required basket component lacks a regular exact-target bar, the whole
event-horizon row is incomplete with an explicit reason. No component may be
dropped and no later bar may be substituted.

### DISCONTINUOUS_NO_COMPLETE_VALUATION

The row remains missing with explicit
`DISCONTINUOUS_NO_COMPLETE_VALUATION`. No price, cash value or zero return may
be invented.

## Corrected return calculation

For a valued row:

- `correctedRaw = terminalHolderValue / canonicalEntryOpen - 1`
- `spyReturn = SPY target close / SPY entry open - 1`
- `correctedExcess = correctedRaw - spyReturn`

For ordinary rows and contract `SAME_SECURITY_CONTINUITY` rows, recomputed
raw/excess must reproduce canonical B3 values within strict floating tolerance
whenever the canonical value exists. A mismatch fails closed.

## MAE boundary

This gate corrects terminal holder outcomes only.

- corrected MAE is **not recomputed**;
- no synthetic cross-security/merger/basket path is constructed;
- output and summary must state `maeRecomputed=false`;
- canonical MAE is not used to judge corrected continuity outcomes.

Any later holder-path/MAE research requires a separate predeclared gate.

## Output status

The corrected output is development-only descriptive evidence:

- status:
  `PHASE1_B3_CONTINUITY_CORRECTED_DEVELOPMENT_COMPLETE`
- result class: `research/descriptive`
- no formal alpha claim
- validation not opened
- calendar-time/HAC not opened by this gate
- 2023+ OOS sealed
- production scoring unchanged
- B3 definition/event construction/identity rules unchanged

After this corrected result is frozen, the already-frozen B3 robustness warning
semantics must be reapplied unchanged. They may not be retuned after observing
the corrected result.
