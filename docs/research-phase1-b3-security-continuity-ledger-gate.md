# Phase-1 B3 performance-blind security-continuity ledger gate

Status: **FROZEN BEFORE B3 CONTINUITY LEDGER EXECUTION**  
Date: **2026-09-20**  
Scope: canonical B3 development exact-entry events only.  
Performance fields: **must not be read**.  
Validation: unopened.  
2023+ OOS: sealed.  
Production scoring: unchanged.

## Motivation

The canonical B3 development run contains missing exact exit bars and the
robustness gate is blocked by tail sensitivity.

As with B1, a large positive or negative realized return is not evidence that a
market series is valid or invalid. Security continuity must be audited
independently from performance.

This stage therefore applies the already frozen Phase-1 continuity mechanics to
the entire B3 development cohort before any corrected B3 performance is
computed.

## Frozen source

Canonical B3 development source:

- workflow run: `35502095184`;
- release: `research-phase1-b3-development-v1`;
- archive: `b3-development-descriptive-2016-2020.tar.gz`;
- SHA-256:
  `d90a2f08483d6710bb2f2715fa9049b64fd27a3979e7e63e5fb792f3c0274ae7`;
- exact-entry events: **29,930**;
- development evaluation cohort: 2016–2020;
- outcomes bounded through 2022.

The event file may contain raw/excess/MAE columns because it is the canonical
persisted source, but the continuity ledger implementation must enumerate and
ignore every such performance column.

## Corporate-action evidence

Use the existing frozen Alpaca corporate-action inventory semantics in
`scripts/research_market_corporate_action_inventory.py`:

- period 2016-01-01 through 2022-12-31 only;
- frozen action types only;
- no 2023+ query;
- performanceRead=false.

The existing bounded Alpaca market release
`research-market-alpaca-v1` supplies only presence/absence of regular adjusted
bars for the continuity ledger.

## B3 fixture rule

B1 performance-selected verification fixtures are **not** reused.

B3 starts with:

`research/b3-security-continuity-empty-fixtures-v1.json`

whose fixture set is empty.

Therefore the first B3 ledger is driven only by:

1. frozen corporate-action provider evidence;
2. frozen market-bar presence/gap evidence;
3. the already frozen general continuity state machine.

If unresolved rows remain, their exact key set must be frozen before any manual
resolution research. No unresolved scope may be expanded or selected using B3
realized performance.

## Frozen continuity mechanics

Reuse `scripts/research_phase1_security_continuity_ledger.py` unchanged.

Key rules include:

- long internal gap threshold: **10 XNYS sessions**;
- ordinary splits/dividends/spin-offs remain adjusted-price diagnostics;
- qualifying same-security name changes may preserve continuity;
- identifiable mergers/redemptions may become
  `TRANSFORMED_HOLDER_CONSIDERATION`;
- worthless removals become
  `DISCONTINUOUS_NO_COMPLETE_VALUATION`;
- ambiguous action combinations or unexplained long gaps become
  `UNRESOLVED_CONTINUITY`.

No classification may use raw return, SPY excess, MAE, tail rank, year sign or
membership in a winner/loser group.

## Required outputs

Persist:

- bounded corporate-action inventory;
- `continuity-ledger.csv`;
- deterministic summary.

Summary must record:

- event rows scanned;
- event-horizon rows;
- continuity state counts;
- unresolved row count;
- affected events/issuers/tickers;
- action-type counts;
- long-gap counts;
- ignored performance columns;
- `performanceRead=false`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

## Progression

If `UNRESOLVED_CONTINUITY > 0`:

- corrected B3 performance remains blocked;
- freeze the exact unresolved key set;
- resolve it performance-blind from corporate/security evidence;
- do not open validation/HAC/OOS.

If unresolved is zero, a separately frozen corrected-performance stage may
apply the continuity states symmetrically across the full B3 cohort.

The already observed canonical B3 performance must not be used to alter any
continuity rule.
