# Insider Turning Engine — Research Log

This file is the persistent research notebook for the Insider Turning Engine.
It is intentionally separate from production code and frozen scoring configuration.
Research notes recorded here are hypotheses, evidence, risks, and proposed tests — not automatic instructions to change code or weights.

**Research policy**

- Keep production code unchanged unless the repository owner explicitly asks for implementation.
- Record the repository snapshot/commit reviewed when a finding depends on current implementation.
- Prefer primary sources, peer-reviewed research, SEC documentation, and reproducible tests.
- Distinguish `OBSERVATION`, `HYPOTHESIS`, `SUPPORTED`, `REJECTED`, and `NEEDS TEST`.
- Do not open sealed OOS results to tune methodology.
- Any proposed scoring change must first be evaluated on development/validation data and documented before OOS is opened.

---

## 2026-09-14 — Initial research pass

Repository reviewed: `Garrincha077/insider-turning-engine`

Main snapshot reviewed: commit `67f57a91862dad33c4565566b3c68e3657e0b0cf`

### R-001 — Opportunistic/routine insider classification

**Status:** `NEEDS TEST`  
**Priority:** High

**Current implementation observed**

`features/opportunistic.py` classifies purchases using a two-year history, transaction cadence, coefficient of variation of timing and dollar values, plus first-buy/re-entry logic. Sparse histories are neutralized rather than forced into either class.

**External research**

Cohen, Malloy and Pomorski (2012), *Decoding Inside Information*, find that predictable routine insider trades contain little predictive information, while opportunistic trades contain the predictive power in their sample. Their opportunistic-only portfolio produced a value-weight abnormal return of approximately 82 basis points per month; routine trades were approximately zero abnormal return. Their canonical timing classification identifies routine trading from repeated trading in the same calendar month across at least three consecutive years, with other eligible patterns treated as opportunistic.

Primary source: https://www.nber.org/papers/w16454

Supporting description of the timing rule: https://www.aeaweb.org/conference/2018/preliminary/paper/eEK893RK

**Research implication**

The engine's existing classifier is reasonable as an original heuristic, but it is not the canonical Cohen–Malloy–Pomorski classifier. We should not assume that the current `20 / 80 / 90` opportunistic scores dominate the literature rule.

**Proposed test**

Run at least three development/validation variants without changing sealed OOS:

1. Current engine classifier.
2. Canonical Cohen-style same-month/three-consecutive-year classifier.
3. Hybrid classifier that preserves `FIRST_BUY_3Y` / `INSIDER_REENTRY` but separately flags canonical routine timing.

Compare 1M, 3M, 6M and 12M SPY-excess returns, win rate, downside tail and MAE. Report coverage loss from the three-year-history requirement separately.

---

### R-002 — CEO/CFO/director role weights need empirical calibration

**Status:** `NEEDS TEST`  
**Priority:** High

**Current implementation observed**

The conviction model currently assigns fixed role priors: CEO 100, CFO 95, Chairman 90, Officer 75, Director 65, 10% Owner 55 and Other 35. Role contributes 20% of the transaction-level conviction score.

**External research**

The literature does not justify treating CEO purchases as mechanically the most informative class. Wang, Shin and Francis report that, in their 1992–2002 sample, CFO purchases earned an average 12-month excess return approximately 5 percentage points higher than CEO purchases, and the difference persisted after controls.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1787482

Related evidence also reports that CFO-based purchase portfolios remained more profitable than CEO-based portfolios post-SOX, although the magnitude declined.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1800202

**Research implication**

The present role ordering is a prior, not a validated empirical fact. This does not mean CFO should automatically receive a higher score; it means role weight must earn its place in development/validation data.

**Proposed test**

Ablation study:

1. Current role priors.
2. No role factor / neutral role factor.
3. Coarse groups only: executive / director / 10% owner / other.
4. Development-derived role coefficients with strong regularization and no OOS access.

Measure marginal improvement over a role-neutral conviction model and check stability by market-cap bucket and era.

---

### R-003 — Cluster buying direction is supported; thresholds are not yet validated

**Status:** `SUPPORTED DIRECTION / NEEDS THRESHOLD TEST`  
**Priority:** Medium-High

**Current implementation observed**

`features/cluster.py` uses distinct reporting-owner CIKs over a 30-calendar-day window. Two independent owners produce a cluster score of 70; three or more produce 100.

**External research**

Alldredge (2019), *Do Insiders Cluster Trades with Colleagues? Evidence from Daily Insider Trading*, reports that clustered insider purchases were followed by abnormal returns in excess of 2% during the subsequent month, with clustering more common when information asymmetry was higher.

Source: https://onlinelibrary.wiley.com/doi/10.1111/jfir.12172

**Research implication**

Using independent insider clustering is economically well motivated. The paper does not, however, validate the engine's exact 30-day window or the current discrete `2 insiders = 70`, `3+ = 100` mapping.

**Proposed test**

On development/validation only, compare windows such as 7/14/30/60 days and owner-count formulations such as binary, capped linear, and dollar/role-weighted cluster intensity. Keep the current rule as the baseline.

---

### R-004 — Historical Rule 10b5-1 information has an important data-boundary problem

**Status:** `SUPPORTED`  
**Priority:** High for historical backtest integrity

**Current implementation observed**

The conviction model applies a 15-point penalty when a purchase is identified as Rule 10b5-1. Unknown status is retained separately in the parsing path.

**External/SEC evidence**

The SEC amended Forms 4 and 5 to require reporting persons to indicate by checkbox whether a reported transaction was intended to satisfy Rule 10b5-1(c). Compliance with the amended Forms 4 and 5 applies to beneficial-ownership reports filed on or after **April 1, 2023**.

SEC source: https://www.sec.gov/newsroom/modernizing-rule-10b5-1-insider-trading-plans

**Research implication**

For pre-April-2023 history, absence of the new structured checkbox cannot safely be interpreted as `NO 10b5-1`. Historical `UNKNOWN` must not silently behave like confirmed non-plan trading. Footnote-derived evidence may improve coverage but needs its own provenance/confidence flag.

**Proposed test / control**

Report 10b5-1 coverage by era. Evaluate the penalty only where plan status is genuinely observed, and run sensitivity with pre-2023 plan status excluded/neutral rather than assumed false.

---

### R-005 — Current long-horizon bootstrap may understate uncertainty when events overlap

**Status:** `STATISTICAL RISK / NEEDS TEST`  
**Priority:** High before any formal PASS claim

**Current implementation observed**

The backtest deduplicates issuer/exposure-family signals within 20 market sessions, while outcomes are evaluated at 63, 126 and 252 sessions. Reporting currently bootstraps individual observed event returns/median differences as if sampled event observations were independently resampled.

**External research**

Kolari and Pynnönen (2010) show that when event dates cluster, even relatively low cross-sectional correlation in abnormal returns can cause standard event-study tests to over-reject the null. Later work explicitly addresses partially overlapping event windows. Long-horizon event-study research likewise identifies overlapping periods as a source of cross-sectional dependence.

Sources:

- https://academic.oup.com/rfs/article-abstract/23/11/3996/1605665
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3167271
- https://www.sciencedirect.com/science/article/pii/S0927539818300124

**Research implication**

This is not yet proven to be a bug in the engine's reported medians, but the present independent-event bootstrap may produce confidence intervals that are too optimistic when many 3M/6M/12M outcome windows overlap in calendar time or are exposed to the same market/sector shocks.

**Proposed test**

Before formal performance certification, compare the current bootstrap with dependence-aware alternatives, for example:

1. Calendar-time / month-block bootstrap.
2. Issuer-clustered resampling where appropriate.
3. Two-way block structure by calendar period and issuer/sector where feasible.
4. Sensitivity after wider event de-duplication windows.

The final inferential method should be chosen on development/validation methodology grounds, not after inspecting sealed OOS performance.

---

## Repository-level research observation

**Status:** `OBSERVATION`

The engineering architecture is materially ahead of the empirical validation. The repository already enforces point-in-time information boundaries, amendment lifecycle handling, scoring provenance, state transitions and sealed OOS design. However, the repository itself states that the scoring lock remains a candidate, predictive validity is not established, historical acquisition is incomplete, and a full real historical development/validation run is still required before enabling production signal delivery.

This is the correct place to focus research effort: validate economic features and statistical inference before optimizing UI or adding more indicators.

---

## Research queue

Next high-value questions:

- Does insider purchase size work better as absolute dollars, percentile within issuer, percentile within insider history, market-cap-normalized dollars, or ownership-change percentage?
- Does `first buy` mean first observed buy ever, first in 3 years, first after becoming an officer, or first after a major drawdown — and which definition predicts best?
- How should sales enter the model: absence-of-sales only, routine/opportunistic sale classification, CEO/CFO sale asymmetry, or no role in a turning signal?
- Are insider signals materially stronger in small/mid caps than large caps after liquidity and survivorship controls?
- Does insider cost-basis reclaim add incremental information after base/RS signals, or simply duplicate price momentum?
- Does Mansfield RS improve post-insider purchase selection independently of ordinary relative strength?
- What is the optimal lag after public Form 4 availability: next open, next close, or a multi-session execution robustness test?
- How much signal survives realistic delisting, corporate-action and stale-price handling?

---

# Research Roadmap v1 — 2026-09-14

## Objective

Build an empirically defensible Insider Turning Engine that answers two separate questions:

1. **Insider information:** which publicly observable insider behaviors identify unusually informative purchases?
2. **Turning confirmation:** which post-purchase market/price conditions improve timing without merely adding redundant momentum filters?

The engine should beat transparent simple insider benchmarks on development and validation data before sealed OOS is opened. Statistical significance alone is not enough: improvements must be economically meaningful, stable across eras, and reasonably tradable after public Form 4 availability.

## Non-negotiable research rules

- Never tune on sealed OOS.
- Never promote a feature because one subgroup or one horizon looks good after broad searching.
- Keep a simple benchmark in every experiment.
- Report missing/delisted outcomes and coverage loss, never silently discard them.
- Report both equal-weight and liquidity-aware results where feasible.
- Separate **feature discovery**, **threshold selection**, and **final validation**.
- Prefer ablations and monotonic bucket tests before continuous weight optimization.
- Any methodology choice that could materially change a PASS/FAIL result must be frozen before opening OOS.

## Phase 0 — Data readiness and information boundary

**Goal:** ensure the historical dataset is good enough that feature research is not measuring data artifacts.

Required evidence:

- canonical Form 4 history sufficiently deep for routine/opportunistic and owner-history features;
- amendments/superseded rows handled point-in-time;
- accepted/knowledge timestamps preserved;
- valid-time issuer/ticker mapping and delisted securities;
- adjusted prices and corporate-action basis reconciled;
- market-cap, volume/liquidity and sector observations available point-in-time;
- explicit Rule 10b5-1 coverage by era.

**Gate P0:** no formal model-comparison claim until historical coverage and attrition are quantified. Partial datasets remain useful for parser and exploratory research only.

## Phase 1 — Reproduce simple insider baselines

Before testing the full engine, establish transparent benchmark strategies from the same PIT dataset:

- any qualified open-market purchase;
- simple purchase/sale ratio;
- unique buyers / unique sellers;
- largest purchase bucket;
- cluster purchases;
- canonical opportunistic purchases;
- company net buying.

Evaluate 21/63/126/252-session outcomes, SPY excess, factor/calendar-time results, win rate, median, downside tail, MAE, event count, attrition and coverage.

**Gate P1:** the dataset should broadly reproduce the direction of well-established purchase informativeness. Failure to do so triggers a data/methodology audit before adding complexity.

## Phase 2 — Insider-information feature tournament

Test features individually and incrementally, not as one optimized score.

Priority order:

1. routine vs opportunistic classification;
2. purchase-size normalization;
3. insider role / hierarchy;
4. independent-owner cluster buying;
5. same-owner trading sequences;
6. first-buy / re-entry definitions;
7. ownership increase / direct versus indirect ownership;
8. sales and absence-of-sales;
9. drawdown/contrarian context;
10. Rule 10b5-1 observed status.

For each feature use bucket plots, monotonicity checks, ablation versus baseline and era/size/liquidity stability.

**Gate P2:** a feature enters the candidate conviction model only if it adds stable validation information or materially improves downside/precision without unacceptable coverage loss.

## Phase 3 — Turning overlay tournament

Only after the insider component is defensible, test whether technical confirmation adds incremental value:

- base formation / no-new-low;
- volatility contraction;
- volume dry-up versus accumulation;
- ordinary relative strength turn;
- Mansfield RS versus market;
- Mansfield RS versus sector;
- MA20/MA50 slope and reclaim;
- insider cost-basis reclaim;
- state persistence / hysteresis.

Key test: compare `INSIDER ONLY` versus `INSIDER + ONE TECHNICAL FEATURE` before testing the full state machine.

**Gate P3:** technical filters must improve incremental risk-adjusted outcome or timing, not merely remove events until only obvious winners remain.

## Phase 4 — Statistical robustness and tradability

Run two complementary evaluation families:

**Event-level diagnostics**

- 21/63/126/252-session returns;
- median and mean SPY excess;
- win rate, downside tail, MAE;
- dependence-aware confidence intervals;
- event-date and issuer clustering sensitivity.

**Calendar-time diagnostics**

- monthly/weekly portfolios of active signals;
- equal-weight and tradability-aware weighting;
- factor-adjusted alpha where data permit;
- HAC/Newey-West or another pre-specified dependence-robust inference method.

Tradability tests:

- next-open baseline;
- next-close and delayed-entry sensitivity;
- minimum liquidity/price buckets;
- spread/slippage scenarios;
- capacity proxy as a fraction of ADV.

**Gate P4:** no formal PASS based solely on an IID event bootstrap.

## Phase 5 — Development/validation freeze

Use development data for feature definition and coarse threshold exploration. Use validation for confirmation and simplification.

Freeze:

- transaction eligibility;
- every raw-to-component transform;
- feature list;
- weights and thresholds;
- deduplication policy;
- statistical test;
- benchmark family;
- execution rule;
- missing-data policy;
- subgroup reports that will be examined OOS.

Then update the methodology lock once, on a clean commit.

**Gate P5:** validation should show economically meaningful advantage over simple benchmarks without relying on a single era, sector, microcap tail or a handful of extreme winners.

## Phase 6 — Sealed OOS

Open OOS once under the frozen methodology.

Primary comparison should be predeclared. Suggested primary target:

`FULL TURNING ENGINE` versus the strongest predeclared simple insider benchmark at 126 sessions, with 21/63/252 sessions as secondary horizons.

A failed OOS is a valid result. Do not retune and relabel the same OOS as a new holdout.

## Phase 7 — Shadow production

If OOS is acceptable:

- keep alerts in shadow mode first;
- compare generated signal timestamps with actual tradable prices;
- measure provider latency, stale data, SEC late filings, duplicate/amendment behavior;
- record paper execution and slippage;
- compare live feature distributions with historical distributions.

Only after this should external alerts be treated as a production signal rather than a research preview.

---

## First research sprint — STARTED 2026-09-14

The first sprint deliberately focuses on high-leverage methodology questions that can invalidate an otherwise impressive backtest:

1. `R-001` canonical opportunistic/routine replication.
2. `R-006` purchase-size normalization.
3. `R-007` dependence-aware inference and calendar-time portfolio benchmark.
4. `R-008` disclosure-time execution and liquidity realism.
5. `R-009` same-owner trade sequences versus independent-owner clusters.

No production code changes are authorized by these findings.

---

### R-006 — Purchase size is useful as a candidate feature, but the correct normalization is unresolved

**Status:** `MIXED EVIDENCE / NEEDS TOURNAMENT`  
**Priority:** High

**Current implementation observed**

The conviction code uses a point-in-time log-dollar percentile relative to the same insider's prior purchases. Company-level aggregation then dollar-weights qualified purchase scores, with a 99.5% prior-universe winsor cap when enough prior observations exist.

**External research**

Evidence supports the idea that size can matter in some contexts, but not one universal transformation. Research on discretionary director purchases reports that larger discretionary purchases are followed by higher abnormal returns; the same study also finds stronger effects in smaller firms and firms with greater information asymmetry.

Source: https://www.sciencedirect.com/science/article/pii/S0927538X16300506

Other research explicitly scales insider trading intensity relative to the insider's existing holdings when constructing weighted net-purchase measures, recognizing that nominal dollars are constrained by insider wealth and are not directly comparable across insiders.

Source: https://doi.org/10.1111/jbfa.12666

The broader literature is not uniformly monotonic: studies in other markets have found transaction value or relative trade size to be insignificant or even negatively related to subsequent price impact. This makes a hard-coded assumption that a larger dollar purchase always means stronger conviction unsafe.

**Research implication**

Do not replace the current history-relative percentile with another single measure on theoretical grounds. Run a predeclared feature tournament.

**Proposed development/validation variants**

1. No purchase-size factor.
2. Current same-insider prior-history log-dollar percentile.
3. Cross-sectional PIT dollar percentile.
4. Purchase dollars / issuer market capitalization.
5. Purchased shares / post-transaction direct holdings, when reliably observed.
6. Change in reported ownership percentage, when denominator quality is sufficient.
7. Two-dimensional specification: absolute/cross-sectional size plus insider-relative size, without forcing monotonicity.

Required diagnostics: quintile/decile monotonicity, sample coverage, stability by market cap/liquidity, and incremental lift after opportunistic/cluster controls.

**Decision rule:** prefer the simplest measure that produces stable validation separation. If none is stable, size should be reduced to a descriptive field rather than a scoring weight.

---

### R-007 — Add a calendar-time portfolio test before treating long-horizon event CIs as formal evidence

**Status:** `SUPPORTED METHODOLOGY CHANGE FOR RESEARCH / IMPLEMENTATION NOT AUTHORIZED`  
**Priority:** Critical before formal PASS

**Current implementation observed**

The current event engine schedules signals carefully from public availability, enters at the next session open, measures exact 21/63/126/252-session outcomes, and reports SPY excess. Its bootstrap resamples observed events individually.

**External research**

Jeng, Metrick and Zeckhauser explicitly use rolling insider-purchase portfolios partly to avoid the statistical difficulties of long-horizon event studies. In their US 1975–1996 sample the purchase portfolio earned roughly 40 basis points of abnormal return per month, while sales did not show abnormal performance.

Source: https://www.nber.org/papers/w6913

Long-horizon event-study literature documents serious issues from skewness, cross-sectional correlation and overlapping event periods. Dutta, Knif, Kolari and Pynnönen specifically note that overlapping long-run windows create cross-sectional dependence; calendar-time portfolios address this correlation problem, albeit sometimes with lower statistical power.

Sources:

- https://www.sciencedirect.com/science/article/pii/S0927539818300124
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3167271

**Research implication**

Keep the current event study because it is excellent for interpretability, MAE and exact signal-level diagnostics. But formal predictive-validity evidence should not rely on its IID event bootstrap alone.

**Proposed validation design**

Run both:

1. **Event study:** current PIT event returns with block/cluster sensitivity.
2. **Calendar-time strategy:** on each calendar week/month form a portfolio of currently active qualifying signals using only information public by formation time.

Predeclare equal-weight as the clean research baseline. Add a liquidity-aware/capacity-aware version separately rather than letting value weighting hide microcap concentration. Where data permit, report market/factor-adjusted alpha with dependence-robust standard errors.

**Decision rule:** strongest evidence is concordance — the signal should look useful in both event-level outcomes and calendar-time performance. If significance exists only under an IID event bootstrap and disappears under dependence-aware/calendar-time analysis, classify the result as `INCONCLUSIVE`, not `PASS`.

---

### R-008 — Public-filings alpha must survive realistic execution and liquidity constraints

**Status:** `SUPPORTED RISK / NEEDS EXECUTION ROBUSTNESS TEST`  
**Priority:** High

**Current implementation observed**

The backtest does not trade on the transaction date. It waits for the filing's public `knowledge_at/accepted_at`, evaluates at the first eligible daily close, and enters at the following market-session open. This is conservative and protects against look-ahead.

**External research**

A 2025 study using intraday data on SEC Form 4 filings finds positive abnormal percentage returns for outsiders reacting to public insider filings, but substantially weaker economic results than many earlier insider studies. When the authors constrain signals to reasonable tradable dollar amounts, returns vanish or become negative; profitability is strongly tied to low liquidity. The study concludes that scalability is limited even before transaction costs.

Source: https://www.sciencedirect.com/science/article/pii/S1544612324015435

Older evidence also finds meaningful market reaction around Form 4 filing dates and shows that more timely post-SOX disclosure improved the information available to outside investors.

Source: https://www.sciencedirect.com/science/article/abs/pii/S1058330014000408

**Research implication**

A statistically attractive microcap/illiquidity signal can be real yet not economically copyable. The Turning Engine should report this rather than silently converting percentage alpha into assumed executable alpha.

**Proposed tests**

- baseline next-open entry;
- next-close entry;
- one-full-session delay and two-session delay;
- results by ADV/liquidity quintile;
- results by stock-price bucket;
- conservative spread/slippage scenarios;
- capacity proxy using fixed fractions of trailing ADV;
- percentage-return and dollar-P&L/capacity views kept separate.

**Decision rule:** signal discovery can include illiquid names, but any claim of practical tradability must survive predeclared liquidity and delayed-entry tests.

---

### R-009 — Same-owner trading sequences are a separate information signal from cross-owner cluster buying

**Status:** `SUPPORTED DIRECTION / NEEDS PIT DEFINITION`  
**Priority:** High

**Current implementation observed**

The engine already has a strong concept of cross-owner clustering: multiple independent reporting-owner CIKs purchasing the same issuer inside a bounded window. The current conviction/opportunistic components also use prior owner history, but the public scoring model does not treat the *duration and structure of one insider's purchase sequence* as a distinct candidate component.

**External research**

Biggerstaff, Cicero and Wintoki (2020), *Insider trading patterns*, show that the temporal structure of an insider's trades contains information. They report positive abnormal returns after both isolated purchases and purchase sequences, with stronger outcomes for sequences in their sample. They also find that after-hours disclosure is associated with longer trading series, larger overall trading volume and larger abnormal returns.

Source: https://www.sciencedirect.com/science/article/pii/S0929119920300985

**Research implication**

`cluster buying` and `trade sequence` should not be conflated:

- cluster = several independent insiders expressing a similar view;
- sequence = one insider repeatedly executing a view over time.

They can contain different information and may interact.

**Proposed test**

Define PIT sequence candidates without looking forward from the event date, e.g. count and dollar intensity of same-owner qualified purchases over trailing 5/10/20/40 sessions, elapsed days since sequence start, and acceleration versus that owner's earlier cadence. Compare:

1. isolated purchase;
2. same-owner sequence only;
3. independent-owner cluster only;
4. sequence + cluster simultaneously.

Do not define a sequence using its future endpoint when scoring the first trade; every snapshot must use only sequence evidence already public at that time.

---

## Sprint conclusions so far

- The strongest immediate methodological priority is **not adding more indicators**; it is making the simple insider signal, inference and execution assumptions hard to fool.
- `purchase size` should enter a tournament, not receive a stronger prior automatically.
- The existing event engine should be retained, but a calendar-time/dependence-aware companion is needed before formal performance claims.
- Liquidity/capacity must be a first-class report dimension because recent evidence suggests public Form 4 percentage alpha can concentrate in names that are difficult to scale.
- Same-owner sequences deserve a separate test from independent-owner clusters.

---

## Change log

- **2026-09-14:** Created research log and recorded initial findings R-001 through R-005. No production code or scoring configuration changed.
- **2026-09-14:** Added Research Roadmap v1 and started first sprint. Added R-006 through R-009 covering purchase-size normalization, dependence-aware/calendar-time inference, execution/liquidity realism, and insider trade sequences. No production code or scoring configuration changed.
