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

## Change log

- **2026-09-14:** Created research log and recorded initial findings R-001 through R-005. No production code or scoring configuration changed.
