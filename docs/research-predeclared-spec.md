# Insider Turning Engine — Predeclared Research Spec

Status: **RESEARCH ONLY / NO PRODUCTION-SCORING CHANGE AUTHORIZED**  
Date: 2026-09-14  
OOS rule: **2023+ remains sealed.** Nothing in this document authorizes opening, inspecting, tuning on, or summarizing the sealed OOS period.

This specification continues the research sequence in `docs/research-log.md`. It freezes definitions for the next development/validation work before empirical results are seen.

---

## R-014 — Ownership change must be tested as a PIT ratio, not assumed to be conviction

### Repository facts

The canonical transaction contract already preserves:

- `postTransactionShares`;
- `ownershipNature` (`D` or `I`);
- `indirectOwnershipNature`.

That is enough to test ownership-change measures without altering production scoring.

### Primary candidate

For a qualified open-market purchase row with positive `postTransactionShares`:

`purchase_fraction_post = purchased_shares / postTransactionShares`

Also derive, where internally consistent:

`preTransactionShares = postTransactionShares - purchased_shares`

and report the purchase as a fraction of both pre- and post-transaction holdings.

### PIT/quality rules

1. Use only values from the filing revision known by `knowledge_at`.
2. Never use a later amendment to repair an earlier historical snapshot before that amendment became public.
3. Do not combine direct and indirect holdings into one denominator unless the ownership identity/nature mapping is deterministic.
4. Do not interpret reported beneficial ownership as the insider's total wealth.
5. Null or internally inconsistent denominators remain null/quarantined; do not impute from future filings.
6. Run coverage and amendment-sensitivity reports before using this variable in any feature tournament.

### Tournament

Compare:

- no holdings-relative variable;
- purchase dollars only;
- purchased shares / post-transaction shares;
- purchased shares / reconstructed pre-transaction shares;
- same-insider historical size percentile;
- two-dimensional absolute-size + holdings-relative specification.

Decision rule: holdings-relative size becomes a candidate feature only if it adds stable development/validation separation after opportunistic/cluster controls and does not depend on a small subset of unusually clean filings.

---

## R-015 — Direct vs indirect ownership is a required stratifier, not a score bonus

SEC Form 4 explicitly distinguishes direct (`D`) and indirect (`I`) beneficial ownership and separately reports the nature of indirect ownership. A recent JFE study using Norwegian administrative data finds abnormal returns after personal own-company purchases by executives below the top, while the paper's indirect-trade subsample does not provide the same evidence. That result is informative but is not automatically transferable to US Form 4 data.

Sources:

- SEC Form 4 structure/instructions: https://www.sec.gov/about/forms/form4.pdf
- *Flying below the radar: Insider trading by executives below the top*, Journal of Financial Economics 181 (2026), 104282: https://doi.org/10.1016/j.jfineco.2026.104282

### Predeclared test

Report qualified purchases separately as:

1. direct ownership;
2. indirect ownership;
3. indirect-family/trust/LLC/other categories only when `indirectOwnershipNature` can be normalized deterministically;
4. mixed owner-event clusters where both D and I purchases are present.

Primary comparison: direct versus indirect purchase outcomes at 21/63/126/252 sessions, with the same disclosure-time execution rule and identical liquidity controls.

Decision rule: `D/I` remains descriptive/stratification metadata unless validation shows stable incremental information. No hard-coded `D > I` scoring rule is authorized.

---

## R-016 — Drawdown context is supported as a contrarian interaction, not an automatic bonus

Prior literature consistently documents that insiders behave contrarianly: insider buying is greater after low recent returns / price declines, and insider trading can reflect both misvaluation and superior information.

Sources:

- Rozeff & Zaman, *Overreaction and Insider Trading: Evidence from Growth and Value Portfolios*, Journal of Finance 53 (1998): https://doi.org/10.1111/0022-1082.275500
- Piotroski & Roulstone, *Do insider trades reflect both contrarian beliefs and superior knowledge about future cash flow realizations?*, Journal of Accounting and Economics 39 (2005): https://doi.org/10.1016/j.jacceco.2004.01.003
- Gregory et al., *More than Just Contrarians: Insider Trading in Glamour and Value Firms*, European Financial Management: https://doi.org/10.1111/j.1468-036X.2011.00608.x

The current PIT price layer already computes `return_3m`, `drawdown_from_52_week_high`, `new_52_week_low`, and `no_new_52_week_low_20_sessions`.

### Predeclared drawdown variables

At the signal evaluation timestamp, using only eligible market bars:

- trailing 21-session return;
- trailing 63-session return;
- trailing 126-session return;
- trailing 252-session return where available;
- drawdown from trailing 252-session high;
- new-low / no-new-low state.

Test these as buckets and interactions with simple insider benchmarks. Do not optimize a continuous drawdown weight first.

Decision rule: drawdown can enter a candidate model only if it improves validation outcomes beyond simply selecting distressed/illiquid microcaps and remains useful after market-cap, price and dollar-ADV stratification.

---

## R-017 — Current “cost-basis reclaim” is an above-basis state, not yet a validated reclaim event

### Repository observation

The current `features/cost_basis.py` implementation:

- selects priced non-derivative open-market purchases;
- calculates share-weighted purchase bases over 30/90/180/365 **calendar-day** windows;
- defines the canonical 90-day `cost_basis_reclaim` as `current_price >= cost_basis_90d`;
- does not require a previous session below the same basis;
- does not model sale depletion of the insider's remaining inventory.

Therefore the current field is best interpreted in research as **price above recent insider purchase VWAP**, not proof that a technical reclaim transition occurred and not the insider's true accounting cost basis.

A targeted literature review found strong evidence that insider purchases are informative but no established peer-reviewed rule that crossing above a recent insider purchase VWAP independently predicts abnormal returns. Beneish & Markarian also report that immediate post-disclosure price behavior is often small/negative and is not itself informative about later purchase profitability, which argues against treating a price-level heuristic as established evidence.

Source: Beneish & Markarian, *When Are Insider Purchases Credible?* (2023 working paper): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3478344

### Predeclared variants

1. No insider-cost-basis variable.
2. State: price below versus above a frozen qualified-purchase cohort VWAP.
3. Distance: `(price / frozen_purchase_vwap) - 1`, bucketed before any continuous transform.
4. True reclaim event: previous eligible session below the **same frozen basis** and current eligible session at/above it.
5. Reclaim persistence: remains above the frozen basis for 2/5 sessions.
6. Compare every variant against ordinary MA/RS confirmation to determine whether insider anchoring adds information beyond generic trend recovery.

For event tests, freeze the purchase-cohort basis using transactions public by formation time. Do not allow later purchases or amendments to move the historical anchor retroactively.

Decision rule: retain reclaim only if it adds incremental validation value versus simple insider-only and ordinary technical baselines.

---

# Phase-1 simple benchmark table — predeclared before results

All benchmarks use qualified open-market purchases and the same PIT disclosure/execution clock. No 2023+ data may be read.

| ID | Benchmark | Definition |
|---|---|---|
| B0 | Any qualified purchase | At least one eligible open-market purchase public by formation time |
| B1 | Canonical opportunistic purchase | Routine/opportunistic classification using only owner history available at formation time |
| B2 | Independent-owner cluster | At least the predeclared number of distinct reporting-owner CIKs buying the issuer inside the trailing cluster window |
| B3 | Company net buying | PIT company-level buying intensity using qualified buys and classified relevant sales |
| B4 | Opportunistic + cluster | Intersection only; used to test incremental corroboration, not as the default winner |

### Outcome horizons

Report exact 21/63/126/252 trading-session outcomes. **126 sessions is the primary medium-horizon comparison**; the other horizons are secondary and must all be shown.

### Primary descriptive outputs

For every benchmark/horizon report:

- event count and distinct issuers;
- raw return;
- SPY excess return;
- mean and median;
- win rate;
- 5th/10th percentile downside tail;
- MAE where path data are available;
- missing/attrition rate;
- results by era, market-cap bucket, price bucket and dollar-ADV bucket.

### Inference

Event-level results remain diagnostic. Formal evidence must include a calendar-time portfolio companion because issuer clustering and overlapping long-horizon windows violate an IID event assumption.

Primary calendar-time baseline:

- equal-weight active-signal portfolio;
- monthly observations;
- 126-session active holding horizon for the primary benchmark;
- SPY excess return;
- HAC/Newey-West inference with lag choice fixed before result inspection and reported explicitly;
- factor-adjusted results as a secondary output when a reproducible factor dataset is available.

No formal `PASS` may be based solely on the existing IID event bootstrap.

### Execution robustness

Baseline execution remains the existing conservative sequence:

`public knowledge_at -> first eligible daily evaluation close -> next market-session open`

Sensitivity runs:

- next close;
- one full additional session delay;
- two full additional session delay;
- predeclared spread/slippage scenarios;
- liquidity/capacity buckets.

---

# Minimum PIT market-cap / liquidity contract

These fields are required before R-006/R-008/R-012 can receive a quantitative PASS/FAIL.

## Shares outstanding

Each observation must carry:

- issuer/security identity;
- shares outstanding value;
- source period/effective date;
- public/knowledge timestamp where available;
- source/provider/provenance;
- observation age in days at signal formation;
- quality/status flag.

Rules:

- never backfill a historical signal with a future-reported share count;
- stale but historically known values may be retained with explicit age, not silently presented as current;
- ambiguous split/security identity is quarantined;
- missing values remain missing.

## Market capitalization

`PIT market cap = eligible session close × PIT shares outstanding`

The exact price field/adjustment convention must be frozen together with the security/corporate-action contract. Market-cap buckets are computed only from values known at formation time.

## Dollar liquidity

Primary liquidity variables:

- trailing 20-session average daily dollar volume: mean(`close × volume`);
- trailing 60-session average daily dollar volume as sensitivity;
- current stock price;
- observed-session count and missing-bar count.

No future volume, future constituent status or survivorship-screened universe may enter these measures.

## Coverage report

Before feature testing, publish coverage by:

- calendar year;
- exchange/security identity status;
- market-cap bucket;
- dollar-ADV bucket;
- price bucket;
- direct/indirect ownership;
- `postTransactionShares` availability;
- amendment/quarantine status.

A result concentrated in the least tradable tail cannot receive a general predictive `PASS` without explicit qualification.

---

# Freeze boundary

This document freezes research definitions only. It does **not** modify:

- `config/scoring.v1.yaml`;
- `config/scoring.v1.lock.json`;
- production feature weights or thresholds;
- alert behavior;
- state-machine thresholds;
- the sealed 2023+ OOS dataset.

Any production-scoring change requires separate explicit user authorization after development/validation evidence is reviewed.