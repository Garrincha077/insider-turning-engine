# Daily research UX delivery ledger

Active goal: useful insider-led stock discovery, technical-turn investigation,
market context and candidate tracking. Historical predictive validation is a
separate goal; experimental scores must not become performance claims.

Baseline: `83e365a` on `origin/main`; implementation branch `codex/research-ux`.
Existing immutable SEC checkpoints, factual digest selection and parser/scoring
rules are preserved. Unrelated local diagnostics are not part of this change.

## Deliveries and proof

| Delivery | Required result | Evidence required | Status |
| --- | --- | --- | --- |
| 1. Candidate discovery | Radar, buys and clusters explain actual purchases and reporting roles; joint filers never inflate dollars or independent decisions | Grain/window/null regressions; desktop/mobile filtered drill-down | In progress |
| 2. Accumulation and turn | Recorded phases are distinct; a few available price/RS checks explain support and missing evidence | Future invariance; missing-history checks; phase filtering | In progress |
| 3. Company Lab | Separate aligned price, volume and RS panels; dated actual transaction markers and today's observed basis | Chart options, marker/basis tests; rendered desktop/mobile review | In progress |
| 4. Market barometer | Own SEC event ratios aligned with SPY; source-scoped GuruFocus references rather than short-history BUY/SELL claims | Definition/population comparison; shared period; absent benchmark/history behavior | Pending |
| 5. Tracking | Local watchlist exposes actual new purchases/clusters/state changes between snapshots | Prior/current snapshot tests; candidate-to-Lab-to-watchlist flow | Pending |

Cross-cutting: all retained views useful and honest, readable dark English UI,
stable filters/sorting/return/links, missing values distinct from zero, explicit
freshness and coverage. Daily-use market coverage target is >=80% of the active
universe, not permission to relax schema/hash/grain or benchmark correctness.

## Execution

- Package 1: factual candidate explanations, recorded phase evidence, Company
  Lab charts and focused regression/UI verification. No acquisition or Telegram
  behavior changes.
- Package 2: external-research market context, actual benchmark series and
  snapshot-to-snapshot watchlist changes. Version new export fields with tests.
- Package 3: remaining tab rough edges, consistent daily-use health/coverage
  messaging and complete operational/public verification.
- Each package: focused checks, full CI, safe commit/PR, public release only after
  green CI. Do not poll Actions more frequently than useful state changes; leave
  a run link or use a bounded longer wait.

## Market-context evidence

- [GuruFocus original research (2010)](https://www.gurufocus.com/news/99283/guru-insider-research-ii-can-aggregated-insider-trading-activities-predict-the-market)
  uses monthly event counts and primarily CEO examples. Its numbers are not
  automatically calibrated thresholds for all reporting owners in our universe.
- [GuruFocus interpretation](https://www.gurufocus.com/tutorial/article/80/how-to-screen-for-insider-trades)
  describes several sale motivations; a low buy/sell ratio alone is not proof of
  a market top.
- Do not derive a long-history z-score from a published mean alone. Mark an
  unavailable comparable distribution honestly without blocking SEC exploration.

## Completion still unproven

All five deliveries, desktop/mobile user flows, CI, a verified public release
and actual daily/Telegram outcome evidence are required. Test configuration or
a successful build alone is not completion. No historical backlog is sent.
Existing scheduled-cycle monitoring remains separate; no delivery is claimed
without an observed ledger/provider result.

## Package 1 implementation checkpoint

- Radar/Turning/Divergence now show indexed canonical 90D purchase facts,
  verified 30D clusters, dated observed-price drawdown and concise evidence.
  Joint-owner USD is counted once; absent or held facts are not fabricated zeros.
- Company Lab separates adjusted close, volume and market/sector Mansfield RS;
  marker availability and a single current observed basis are explicit.
- Three supporting price/RS checks are display evidence, not a recomputation of
  the state machine or all prerequisites. Recorded server phases remain authoritative.
- Typecheck, lint and production build pass. Focused desktop/mobile run: 90
  passing cases (including new facts, chart, future invariance and drill-down tests).
- [PR 32](https://github.com/Garrincha077/insider-turning-engine/pull/32)
  merged after green Python and dashboard CI (118 desktop/mobile cases).
  Desktop/mobile visual review of the actual Oct 4 snapshot passed locally.
  [UI-only deployment](https://github.com/Garrincha077/insider-turning-engine/actions/runs/37211657371)
  is running; public verification remains pending. No digest was requested.
- Market reference/SPY integration and actual snapshot-to-snapshot watchlist
  changes are still separate unfinished deliverables.

## Watchlist follow-up checkpoint

- The Radar watchlist panel compares the previous verified publication viewed
  in this browser with the current publication. It is not a server-synced list.
- New purchases >=$100K, new supplied cluster memberships supported by newly
  available purchases and recorded established-state transitions are shown.
  Older acceptance/knowledge, replay, unresolved issuer facts and score-version
  changes cannot become new activity.
- Compact local baselines persist across reload and UI-only deployments. Adding
  an issuer does not fabricate its predecessor; removing it erases its baseline.
- Local typecheck/lint/build and focused facts/storage/UI checks pass. Full
  CI/publication are pending for this follow-up; Telegram remains unchanged.
- Next: source-scoped GuruFocus market context with actual same-period SPY;
  then remaining tab/health/coverage checks and observed daily/delivery evidence.
