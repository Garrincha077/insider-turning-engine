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
| 1. Candidate discovery | Radar, buys and clusters explain actual purchases and reporting roles; joint filers never inflate dollars or independent decisions | Grain/window/null regressions; desktop/mobile filtered drill-down | Published PR 32; factual shortlist follow-up below |
| 2. Accumulation and turn | Recorded phases are distinct; a few available price/RS checks explain support and missing evidence | Future invariance; missing-history checks; phase filtering | Published PR 32 |
| 3. Company Lab | Separate aligned price, volume and RS panels; dated actual transaction markers and today's observed basis | Chart options, marker/basis tests; rendered desktop/mobile review | Published PR 32; adjustment-label clarification below |
| 4. Market barometer | Own SEC event ratios aligned with SPY; source-scoped GuruFocus references rather than short-history BUY/SELL claims | Definition/population comparison; shared period; absent benchmark/history behavior | Published PR 34/36; actual v2.3 SPY rendered and independently verified |
| 5. Tracking | Local watchlist exposes actual new purchases/clusters/state changes between snapshots | Prior/current snapshot tests; candidate-to-Lab-to-watchlist flow | Published PR 33; actual public flow verified |

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
- Company Lab separates observed provider close, volume and market/sector Mansfield RS;
  marker availability and a single current observed basis are explicit.
- Three supporting price/RS checks are display evidence, not a recomputation of
  the state machine or all prerequisites. Recorded server phases remain authoritative.
- Typecheck, lint and production build pass. Focused desktop/mobile run: 90
  passing cases (including new facts, chart, future invariance and drill-down tests).
- [PR 32](https://github.com/Garrincha077/insider-turning-engine/pull/32)
  merged after green Python and dashboard CI (118 desktop/mobile cases).
  Desktop/mobile visual review of the actual Oct 4 snapshot passed locally.
  [UI-only deployment](https://github.com/Garrincha077/insider-turning-engine/actions/runs/37211657371)
  completed successfully. Public Radar now shows factual purchase/drawdown/phase
  columns. No digest was requested.
- The initial package preserved acquisition and Telegram behavior. Market
  reference/SPY and watchlist follow-ups are documented below.

## Watchlist follow-up checkpoint

- The Radar watchlist panel compares the previous verified publication viewed
  in this browser with the current publication. It is not a server-synced list.
- New purchases >=$100K, new supplied cluster memberships supported by newly
  available purchases and recorded established-state transitions are shown.
  Older acceptance/knowledge, replay, unresolved issuer facts and score-version
  changes cannot become new activity.
- Compact local baselines persist across reload and UI-only deployments. Adding
  an issuer does not fabricate its predecessor; removing it erases its baseline.
- Local typecheck/lint/build and focused facts/storage/UI checks pass.
  [PR 33](https://github.com/Garrincha077/insider-turning-engine/pull/33) merged
  after green Python/dashboard CI. Its
  [UI-only deployment](https://github.com/Garrincha077/insider-turning-engine/actions/runs/37212893668)
  completed successfully. Actual public Radar -> add DUOT -> Company Lab flow
  was verified; the first viewed baseline did not label old purchases as new.
  Telegram is unchanged.
- Next: source-scoped GuruFocus market context with actual same-period SPY;
  then remaining tab/health/coverage checks and observed daily/delivery evidence.

## Market-context package checkpoint

- Snapshot v2.3 carries actual SPY observations with source, adjustment basis and
  availability. Earlier v2 versions remain readable without invented benchmarks.
- Monthly event counts are the default; the existing daily rolling mode remains.
  Ratio and SPY use aligned windows and separate scales. Missing denominator,
  unavailable SPY and incomplete SEC windows stay explicit. Three-month means
  require three fully covered calendar-month ratios, not overlapping daily points.
- Removed short-history 20th/80th-percentile BUY/SELL labels: 20 overlapping
  observations do not establish a long-history calibrated market-extremes signal.
- The public GuruFocus overall-market indicator lists a mean of 0.39, reviewed
  2026-10-04. An optional monthly/all-sector reference is clearly external. CEO
  examples in the 2010 study cannot become all-owner universal thresholds.
- Detailed research views wait for v2 validation rather than briefly showing a
  potentially conflicting legacy phase during lazy loading.
- Focused backend tests: 28 passed. Ruff and strict mypy pass. Frontend type/lint
  and build pass; focused desktop/mobile checks pass.
  [PR 34](https://github.com/Garrincha077/insider-turning-engine/pull/34) merged
  after green Python and dashboard CI. Its UI-only deployment completed.
  [Fresh v2.3 data refresh](https://github.com/Garrincha077/insider-turning-engine/actions/runs/37225254899)
  is running with `send_digest=false`. Actual public SPY verification remains
  pending; an earlier v2.2 snapshot correctly shows SPY as unavailable.
  No parser/score/delivery change.

## Final daily-use UX package

- A single optional Radar shortlist uses observed 90D purchases >=$100K and a
  price at least 20% below the exported-window high. It works without a score,
  excludes absent/held facts, persists locally and exports exactly its filtered
  rows. It does not establish a 52W high or change methodology. On the actual
  Oct 4 snapshot it finds 184 of 4,183 companies; partial windows stay disclosed.
- Insider Buys excludes held/unresolved aggregate events; Live SEC Tape keeps
  their facts inspectable. Missing sales denominators display `—`, not infinity.
- Company charts call the input an observed provider close (adjusted where
  supplied), not a proven uniformly split/dividend-adjusted series. Markers are
  dated observed closes, not transaction execution prices.
- System Health separates the accepted >=80% daily-use market target from the
  unchanged >=90% predictive validation gate. Predictive suppressions are not
  presented as suppressions of the independent factual digest.
- Client date checks use the UTC as-of date and reject future SEC days; added
  regression cases cover offset-local dates and held events. A newer incomplete
  SEC day is explicitly disclosed rather than silently substituted as complete.
- Local typecheck/lint/build pass. Focused desktop/mobile regressions pass.
  [PR 35](https://github.com/Garrincha077/insider-turning-engine/pull/35) merged
  after green CI: 694 Python cases, 88.80% core branch coverage, 196 desktop/mobile
  cases. All retained tabs were inspected against actual data at 1440/390px;
  meaningful content, no browser errors or whole-page horizontal overflow.
  Its public deployment is queued behind the running refresh.

## Operational evidence and exact remaining proof

- Actual manual refresh 37197685282 succeeded on 2026-10-04 without digest
  sending: SEC 2026-10-02 complete (1,572 filings, 2,820 stored rows), latest-day
  quarantine 0; market 1,611/1,871 (86.1%), benchmarks through Oct 2. Global
  unresolved issuer count was 276, not zero; affected aggregates remain held.
- Read-only restoration of the durable state branch verified a Telegram test
  SENT on 2026-10-01 and operational notices SENT on Oct 3/4. The user previously
  confirmed receipt of both TEST and warning. The most recent factual digest
  SENT in the inspected ledger is SEC day 2026-09-15; this is not evidence of a
  current post-repair scheduled digest. No historic day has been resent.
- Existing quiet monitoring follows the next five scheduled Tue-Sat 07:15 UTC
  cycles. Sunday has no scheduled cycle. A fresh scheduled digest/provider
  result and the new public v2.3 benchmark output remain required proof; neither
  is replaced by a green build or an enabled policy.

## SEC-day boundary correction

- Actual Oct 2 data contains 41 eligible events (3 buys, 38 sales) accepted
  after UTC midnight but still during the same New York SEC day. More broadly,
  all 253 eligible Oct 2 events were known locally after the SEC day ended.
  Capping a current snapshot at the source day-end excluded these valid imports.
- Historical rolling points use America/New_York day end with the actual
  summer/winter offset, capped at as-of. The latest point and calendar-month
  revisions include imports known by the current as-of, while still excluding
  incomplete/newer SEC days and future knowledge. They are not archived live
  historical readings; that distinction is explicit in the calculation notes.
- Against the exact same Oct 4 snapshot, current 30D counts change from 788/4,612
  to 824/4,863 (0.16944x). Partial October changes to 32/200 (0.16x); it is not a
  full-month estimate. No source amounts or transactions are modified.
- Regression checks cover summer, winter, both DST transitions, late US-evening
  acceptance, knowledge after historical day end and current-snapshot imports.
  Type/lint/build and 36 focused desktop/mobile cases pass. Parser, scores and
  digest policy are unchanged. A separate PR/CI gate covers this display fix.

## Publication-loading UX

- A real public-browser check found a 13.4 MB detailed snapshot taking nearly
  four minutes to transfer. Research-tab navigation also restarted the download.
  The new transfer is shared across research tabs, shows received/total bytes,
  exposes an explicit restart and times out with a retryable error instead of
  waiting indefinitely. It never replaces missing data with sample observations.
- HTTP cache entries are revalidated; each body still must match the current
  manifest's size and SHA-256. Compressed and decompressed sizes are bounded and
  both hashes are checked before schema/semantic validation or rendering facts.
- Regression coverage includes streaming progress, declared-size overflow,
  cancellation, a stalled body/manifest, navigation without duplicate transfers
  and restarting a pending transfer. No data acquisition, parser, scores or
  Telegram policy changes are included.
- Typecheck, lint, production build and 28 focused desktop/mobile cases pass.
  A rendered local review against the actual Oct 4 dataset confirms the loaded
  Radar and mobile shortlist. Full CI and publication are the next gate.

## Final rendered barometer correction

- Public desktop/mobile review of fresh v2.3 data confirms actual SPY aligned
  with monthly insider ratios. PR36's current 30D reading is 825/4,863 (0.16965x)
  in the newer snapshot; the earlier 824 numerator belonged to the prior snapshot.
- In the small monthly range, one-decimal axis formatting incorrectly repeated
  0.1x for different tick levels. Three significant digits keep these labels
  distinct without changing observations, chart coordinates or calculations.
- Mobile route changes also preserved a deep prior scroll position, leaving the
  next view's title and primary facts off-screen. Tab/company route changes now
  begin at the top; local filters, watchlists and same-tab interactions persist.
- Type/lint/build, 28 barometer cases and six focused desktop/mobile
  candidate/navigation/transfer cases pass. Rendered local mobile navigation
  confirms scroll reset without whole-page overflow. Full CI covers this package.

## Transaction-code scope clarification

- [SEC Form 4 instructions](https://www.sec.gov/files/form4.pdf), instruction 8,
  define P/S to include exchange or private purchases/sales. Our existing parser
  maps those codes to its legacy open-market classification; that mapping is not
  independent proof of execution venue or market-price terms.
- Insider Buys and the digest preview now call these qualified reported SEC
  purchases. Barometer calculation details disclose the private-transaction
  limitation alongside GuruFocus's exclusion of non-market-price placements.
  Parser, eligibility, scores, source amounts and Telegram selection are unchanged.
- PR 38 merged after all Python/dashboard CI checks succeeded: 694 Python tests,
  88.80% core branch coverage, strict mypy, lint/type/build and 226 desktop/mobile
  cases. Its UI deployment queues behind the single running recovery refresh.
- Public v2.3 run `run_research_20261004T185540Z` has complete latest SEC day
  2026-10-02 and actual same-period SPY. Market coverage is 1332/1872 (71.15%),
  below the accepted 80%: 540 symbols exhausted the shard time budget. Recovery
  run 37230735273 has digest sending disabled; its result remains unproven.

## Verified closed-session market cache replay

- Recovery run 37230735273 and the subsequent UI-only deployment both succeeded.
  Acquisition diagnostics still contain 476 unrequested symbols after the shard
  time budget was exhausted. A successful deployment is not proof that the
  accepted 80% selected-universe coverage target has been met.
  Independent public size/hash/schema/run-lineage verification confirms
  `run_research_20261004T200609Z`: 1395/1871 selected stocks (74.56%), complete
  SEC Oct 2 (1572/1572 filings, 2820 rows, quarantine/failures 0), fresh benchmarks
  and a factual GME/CRBG/FGBI digest preview. This manual refresh did not send it.
- An explicit required closed session now permits redundant EOD selection to
  inspect the adapters' existing checksum/provenance-verified caches before HTTP.
  Replaying that same session does not recontact an unavailable source when
  another source already has the required observation. Newer sessions, missing,
  invalid or corrupt caches retain the existing bounded network path.
- Two available fresh cached sources still undergo the original disagreement
  checks. A single cached source is not labelled cross-validated; skipped network
  requests are not fabricated provider failures. Dates and point-in-time filters,
  configured source tie-breaks and all quality thresholds remain unchanged.
- Regression checks cover offline real-adapter reads, checksums, required-session
  misses, invalid metadata, cross-source disagreement, source ordering and
  clearing per-symbol metadata between calls. This is a replay/performance fix,
  not a claim that free-provider quality or future daily coverage is guaranteed.
- Parser, score formulas, source amounts and Telegram selection are unchanged.
  The next verification is an actual refresh on the merged code, with digest
  sending disabled, followed by independent public hash/lineage/coverage checks.
- Local checks pass: 703 Python tests, Ruff over the CI source/test scope and
  strict mypy over 83 modules. Public PR37-39 desktop/mobile review confirms
  distinct ratio-axis ticks, actual aligned SPY, preserved research scope notes
  and route scroll reset; full merged-head CI remains required for this package.

## Reported-price review across research views

- An extreme SEC-reported price is a review prompt, not proof of an erroneous
  filing. Preserve the reported price, quantity and economic amount. Never
  reinterpret a reported per-share price as total dollars or guess a correction.
- Reuse the existing Pulse display screen: a positive, finite reported price
  at least 1,000 times above or below the available snapshot market close.
  Dates and adjustment bases can differ. This does not establish execution venue,
  market-price terms, or a validated source amount.
- Radar, Insider Buys, Live SEC Tape, Clusters, Company Lab and Cost Basis now
  disclose affected amounts. Basis warnings follow the selected 30D/90D calendar
  window. Future knowledge/acceptance and held issuer aggregates do not create
  review facts; duplicate economic IDs do not inflate review counts.
- Tape CSV preserves numeric values and adds REVIEW, NO_FLAG or UNAVAILABLE;
  NO_FLAG is not a validation stamp. Basis CSV includes flagged-event counts
  without replacing unknown comparison availability with zero.
- Pulse also discloses when one reported purchase supplies at least half of its
  displayed purchase dollars, linking the original SEC record. If the market
  reference is missing, disclose that rather than inventing a price anomaly.
  Existing Pulse exclusions and count-based barometer methodology are unchanged.
- Parser, canonical amounts, scores, ranking, watchlist change selection and
  Telegram eligibility are unchanged. These are interpretation safeguards,
  not source repairs or new predictive rules.
- Rendered review also found repeated 0.1x/0x tick labels in Pulse's existing
  monthly ratio chart. Three significant digits, matching the barometer axis,
  keep small levels and tooltip values distinct. Observations, scales and
  ratios are unchanged; a missing denominator remains a gap.
