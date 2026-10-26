# Predictive validation — active research goal

Owner-authorized on 2026-10-26. This replaces the previous Compass/Turning UX
delivery contract as the active goal; it preserves implemented features and all
previously frozen research findings. The daily factual dashboard, local watchlist
and Telegram selection continue unchanged. Predictive delivery stays OFF.

## Questions and completion evidence

1. Do unusual insider purchases, valuation and early technical turns predict
   subsequent company returns? Compare insider-only, technical-only, valuation-only,
   their limited predeclared combinations, and the full model against SPY and
   simple purchase/cluster rules. Both incremental benefit and absolute performance
   matter; complexity is not an improvement without evidence.
2. Does aggregate insider buying/selling anticipate favourable SPY returns or
   elevated downside risk? This is a separate monthly market-level study, not a
   conclusion borrowed from stock-level event outcomes or GuruFocus thresholds.
3. Deliver pinned inputs, runnable code, coverage/attrition tables, costs, adverse
   excursion, uncertainty and an understandable report of positive, negative or
   inconclusive findings. A running app, green CI or descriptive mean is not proof.

## Current health and existing exposure

Read-only inspection on Oct26 independently checked the actual public manifest,
dashboard and settings hashes and rendered System Health on desktop/mobile.
The source is `run_research_20261024T115850Z`, as-of Oct24 12:46:29.895584 UTC;
market data through Oct23, 1833/1834 selected stocks priced. Latest scheduled run
`40092019370` succeeded. Public history records a Telegram digest SENT Oct24
13:14:59 UTC. These are operational observations, not historical model validation.
Old-day replay suppression is not a newly failed delivery. The Tuesday–Saturday
schedule does not promise a Monday refresh. No digest was dispatched in this study.

Already viewed evidence must remain marked as such:

- B1 formation in 2016–2020, outcomes through 2022; existing corrected robustness
  gate is `BLOCK_HAC_AND_OOS`. Reproducing or adding cost sensitivity cannot clear it.
- Other prior B0/B2/B4 development reports and previous research attempts must be
  retained in the exposure/variant inventory; their continuity is not certified by B1.
- Live 2026 observations have been viewed. The whole 2023+ calendar is therefore
  not honestly describable as untouched. No 2023+ historical research outcomes
  are opened by this package. Repository flags alone cannot prove non-exposure.
- Existing 2021–2022 market files were used for earlier development-event outcomes;
  that is not equivalent to testing 2021–2022 formations, but must be disclosed.

## Evaluation contract before the first ablation

Primary company outcome: 126-session stock return net of assumed execution costs,
minus same-entry/same-exit SPY return. Report mean, median, win rate, lower tail,
maximum adverse excursion and coverage; secondary horizons 21/63/252 sessions.
Do not select a model on its mean while hiding its negative median or tail.

Signals use the first scheduled daily close after every required input is public,
then enter the next market-session open. SEC acceptance time, price availability,
filing-linked financial publication and each amendment version must respect this
boundary. Historical identity/sector and corporate-action continuity cannot use
today's ticker map. Do not infer an acceptance clock from a civil filing date.

Record issuer/session eligibility before outcomes are loaded. Technical-only and
valuation-only baselines need an independently eligible PIT universe, not just
known insider buyers. Report both each rule's available population and a common
comparison population; otherwise missing fundamentals can manufacture improvement.
Use the same execution/overlap convention across comparisons, and show all lost
signals: missing entry, missing outcome, delisting/merger, stale/missing feature,
insufficient warmup, identity uncertainty and liquidity exclusion.

Predeclare a small initial rule set before viewing its returns. Register formulas,
thresholds, sector routes, history windows, liquidity rules and implementation/input
hashes. Do not introduce an arbitrary universal P/E or leverage cutoff for banks,
REITs and operating companies. Missing valuation remains unknown. Current Company
Facts is not sufficient PIT evidence without an exact accession/acceptance and
restatement/version audit. Price/share-basis comparability must also be proved.

Use a fixed cost sensitivity grid of 0/10/25/50 bps per leg, with entry premium
and exit haircut. This is an assumption, not measured fills. Stratify by price
and prior dollar-ADV; report capacity/spread limitations. Never backfill an unknown
delisting outcome with zero without marking a separate stress scenario.

For the monthly market study, distinguish count ratio, dollar ratio and company
breadth, economic-event/joint-owner grain, private P/S and incomplete months.
Classify using strictly earlier comparable complete months. Evaluate future SPY
returns and drawdowns separately; high buying activity is not itself a calibrated
market-bottom probability. Freeze exact horizon/outcome/variant definitions before
reading that study's results. Stock-event sample size cannot substitute for the
number of independent market months.

## Sequence and holdout policy

1. Pin existing historical SEC/identity/market/financial inventories; reuse cached
   and Release data. Recompute availability by year and by component. Do not
   replace this with another full download or lower research gates to app gates.
2. Reproduce the already viewed baseline with costs/attrition (implemented below).
   Acquire/reconstruct missing PIT features and paths, then run development
   ablations with the limited predeclared rules. Maintain a variant/exposure ledger.
3. Freeze rules before evaluation on later formations. Verify purge/embargo against
   overlapping 252-session outcomes; merely changing the signal year is insufficient.
   Use dependence-aware calendar/issuer analysis, not an IID event confidence claim.
4. Select a final holdout only after the exposure audit and freeze. If no suitable
   untouched historical interval remains, label historical results exploratory and
   use future paper observations. Never manufacture a sealed OOS period.
5. Publish a reproducible comparison and plain-language conclusions. Integrate
   findings into Methodology & Validation without enabling predictive messages.

The entire goal remains open until both company and aggregate-market questions
have the appropriate real-data comparison and report. Missing inputs can yield
NOT_EVALUATED, not an invented FAIL/PASS. An inconclusive result is acceptable;
an unexecuted study is not completion.

The [input inventory](../research/predictive-input-inventory.v1.json) records
independently rehashed small source reports, reported rather than freshly computed
coverage, mutable Release status, missing pre-2016 technical warmup and outstanding
PIT/corporate-action/financial/path requirements. Existing market archives should
be reused; a new full-history acquisition is not the starting point.

## First reproducible package: viewed B1 baseline

`research/predictive-baseline-audit.v1.json` pins the two existing development
input files by SHA-256, dates, event inventory, horizons and cost grid. Run:

```powershell
uv run --frozen --offline python -m insider_turning_engine.backtest.baseline_audit `
  --csv <path-to-b1-corrected-event-horizons.csv> `
  --summary <path-to-corrected-summary.json> `
  --output work/predictive-validation/baseline-cost-audit.json
```

Exact source: run [35277369958](https://github.com/Garrincha077/insider-turning-engine/actions/runs/35277369958),
artifact `phase1-b1-continuity-corrected-performance-35277369958`.
Use the stored source hashes, not a mutable Release tag alone. Raw files stay
outside git. The compact generated result is committed under `research/results/`.

This audit verifies the supplied event identity, date order, hashes and arithmetic;
it does not independently reconstruct source filing clocks, features or executions.
Its denominator is the 6094 events with an entry, not every original signal.
The original selection also had 681 missing exact entries after 6775 retained
events, as recorded in the [prior run report](progress-2026-09-17-b1-b4-results.md).
These missing entries must not disappear from the eventual full-study attrition.
Corrected MAE paths and liquidity/capacity evidence are unavailable in this source,
so they remain explicitly unmeasured. No significance test, new filter, OOS
access or gate override is performed.

### Reproduced six-month baseline, including costs

| Assumed bps per side | Mean excess vs gross SPY | Median excess | Win rate |
| ---: | ---: | ---: | ---: |
| 0 | +3.08% | −3.30% | 44.09% |
| 10 | +2.86% | −3.52% | 43.69% |
| 25 | +2.52% | −3.87% | 43.08% |
| 50 | +1.95% | −4.40% | 42.25% |

There are 5965 observed and 129 missing six-month outcomes among 6094 entry
events. At 50 bps per side, treating every missing stock outcome as zero recovery
makes the mean excess about −0.36%; that is an explicit stress assumption, not
an estimate of actual delisting returns. The central result remains a negative
median. Nothing here establishes the full engine's predictive value.

Both the original archive bytes and the selected input files were independently
hashed in this inspection. Restoring them independently and rerunning the audit
produced byte-identical JSON. The manual **Audit predictive research baseline**
workflow repeats exact artifact identity/digest checks, runs contract tests before
real outcomes, and uploads only the report. It cannot publish Pages or send alerts.
