# Insider Compass & Turning Engine — active delivery contract

Status update 2026-10-26: superseded as the active goal by
[Predictive validation](predictive-validation-goal.md). This file preserves the
previous scope and evidence; it does not claim all former requirements finished.

Started 2026-10-26. Source objective: owner-provided goal, reproduced by the
requirements below. This supersedes earlier MVP exclusions of fundamentals,
not earlier frozen research results. Working branch: codex/insider-compass-turning-v2.

## Purpose and evidence of completion

1. Market Compass: monthly economic-event buy/sell count ratio, separate dollar
   ratio, distinct buying/selling-company breadth, same-period actual SPY graph,
   clearly partial months, and prior-history percentile plus descriptive reading.
   Proof: golden tests, future-row/duplicate/denominator invariants, actual public
   source verification and rendered desktop/mobile. Calibration needs comparable
   long history; today's 90-day window is not long history or the whole market.
2. Turning Engine: separate insider significance, sector-appropriate valuation
   and financial sustainability, and early/confirmed/extended technical evidence.
   Per issuer: actual state/change date, up to three reasons, principal risk and
   invalidation, source references and freshness. Proof: PIT fixtures, source-backed
   outputs and Company Lab rendering. No neutral valuation imputation.
3. Historical comparison: declare success/early-failure outcomes before testing;
   compare insider-only, technical-only, valuation-only and combined models with
   identical clocks/liquidity/costs. Account for adverse excursion, missing and
   delisted securities, multiple attempts and event dependence. Proof: frozen
   protocol/hash, input lineage, reproducible results and honest negative results.
4. UX: home shows market context, current candidates and actual daily changes;
   reuse existing tabs/Company Lab. Preserve local watchlist, refresh and factual
   Telegram. Predictive delivery stays OFF until separately authorized.
5. Operational proof: actual completed daily cycles, public snapshot integrity,
   current SEC completeness, market freshness/coverage and durable delivery. CI
   alone proves neither live recovery nor predictive utility. No paid data or new
   infrastructure without owner approval.

## Baseline inspected, not assumed

- Remote main: d4f13edadd19082b2443c540510c0043ed3585ec. Existing local main
  is stale; implementation uses the separate app-data-loading worktree.
- Public manifest inspected Oct26: run_research_20261024T115850Z, as-of
  2026-10-24T12:46:29.895584Z; 1833/1834 selected stocks priced; benchmarks
  through Oct23; canonical valid. This is manifest evidence, not an independent
  full payload/delivery verification. Last three scheduled workflow runs succeed.
- Existing Insider Ratio has monthly count ratios/SPY and scope notes but still
  leads with rolling 30D, omits monthly dollar/breadth context and has no usable
  prior-history classification. No historical fundamental adapter exists.
- Prior B1 development results already inspected: 2016–2020 formation, outcomes
  through 2022. The corrected result is NOT validated alpha: primary median
  negative; positive mean is regime-concentrated. See Sep18 temporal-clustering
  report and its BLOCK_HAC_AND_OOS gate. Preserve those results verbatim.
- Existing documentation says 2023+ evaluation remains sealed. Current live
  2026 observations have been viewed; do not label the entire 2023+ calendar
  untouched. Audit actual evaluation/artifact access before any final holdout.

## Delivery sequence

A. Compass: improve existing Insider Ratio (no new tab), calculation/test contract,
   population distinctions and explicit insufficient-history state. In progress.
B. Fundamentals: cached SEC Company Facts + filing acceptance linkage; period/unit
   and restatement handling; financial vs operating-company metric routes;
   profitability, leverage and dilution alongside modest valuation measures.
   Never use a present-day XBRL frame as historical PIT data. Add public export
   and Company Lab evidence together, keep missing inputs explicit.
C. Turning v2: small candidate definitions and three separate evidence columns,
   not another arbitrary weighted score. Freeze limited variants and outcome
   definition before computing their returns. Preserve scoring.v1 lineage.
D. Research: audited development/validation inventory, reproducible ablations,
   dependence-aware uncertainty and sealed/future evaluation only after freeze.
E. Integrate home/Company Lab, full CI, public source/render verification and
   daily operation checks. Do not mark the full goal complete after A alone.

## Research choices and source boundaries (reviewed 2026-10-26)

- GuruFocus 2010 study: monthly transaction counts, principally executive examples,
  market-price trades; excluded non-market private placements. Our economic events
  count a joint-owner event once, across all roles; P/S includes private trades.
  Therefore its values/thresholds are external references, not calibrated zones.
  https://www.gurufocus.com/news/99283/guru-insider-research-ii-can-aggregated-insider-trading-activities-predict-the-market
- SEC Form4 instruction 8 documents P/S including private purchases/sales:
  https://www.sec.gov/files/form4.pdf
- Choose empirical midrank percentile instead of a normal z-score: ratios are
  skewed and no-sale denominators are undefined. Require at least 24 consecutive
  fully inventoried prior calendar months with defined ratios. That is an explicit
  descriptive sample sufficiency choice, NOT a predictive threshold from a paper.
  Prior mean is arithmetic mean of comparable monthly ratios, not dollar ratio
  or pooled event counts. Partial current months are provisional, not classified
  against full months. Percentile is historical position, never success probability.
- Cohen/Malloy/Pomorski motivates testing routine/opportunistic distinctions, not
  importing their reported returns into our engine: https://www.nber.org/papers/w16454
- Momentum evidence is not proof of our early-turn rule:
  https://www.nber.org/papers/w7159
- SEC Company Facts is free and filing-linked; the frames API selects latest-filed
  values and cannot establish historical availability:
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Remaining full-objective items stay open until individually proven. No performance
data or formal OOS is opened by this first descriptive Compass delivery.

## Oct26 first-delivery evidence and next action

Previous goal turn classification: initial goal intake; this turn makes progress
through implemented/tested code plus independent actual-source verification.

- A now implements separate monthly count/dollar ratios, buying/selling-company
  breadth, calendar-month-first cards, all-exported-history control, and a guarded
  empirical percentile/prior mean. It keeps the existing tab/URL/sector controls.
  No sale denominator stays null, unknown dollar totals do not erase counts, and
  future observations/duplicate economic IDs cannot change prior results.
- Full local suite: 780 Python tests, 89.41% core branch coverage, Ruff and strict
  mypy. Frontend lint/type/build and 262 desktop/mobile cases passed. Additional
  focused checks cover final significant-digit labels. CI/deploy evidence is
  recorded separately once available; local tests are not public release proof.
- Actual public source schema/hash/run verified independently, including gzip and
  canonical bytes. Its observed population includes 515 buyer issuers and 1363
  seller issuers, including 1169 seller-only issuers. These refer to the exported
  observed history, not a US-market census. Latest inventory spans Jul27–Oct23.
- Independent current-month reproduction on the Oct24 snapshot: 243 buy / 2492
  sale events, 65 buying / 413 selling issuers, purchase USD 558805598.5422921 /
  sale USD 3505383242.3354344. Desktop1440/mobile390 actual-source render agrees,
  with no document overflow or page errors. This month/history is partial;
  percentile stays unavailable rather than manufacturing a market-bottom signal.
- Local evidence (not committed raw data): .codex/compass-20261026/source-receipt.json,
  render-receipt.json and screenshots. These explicitly identify a local rendering
  of verified actual public data, not proof of a newly deployed frontend.
- Full 24-month comparable history is still missing. The current all-history
  control exposes existing exported history; it does not solve historical data
  acquisition. Long-history compact server aggregates remain required, rather
  than shipping decades of raw events to the browser.

Next: finish first-delivery PR/CI/publication verification, then implement free
SEC filing-linked Company Facts ingestion/selection and valuation/financial-risk
evidence. No fundamental input or Turning v2 validation is claimed complete.
