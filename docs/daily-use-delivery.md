# Daily-use delivery (2026-09-11)

The immediate product goal is a trustworthy SEC research workspace and a factual
daily Telegram digest. Predictive validation is a separate goal, not a reason to
hide valid SEC facts. Scores remain experimental and predictive delivery stays off.

## Package 1 — legacy-compatible UI

Implemented: grouped desktop/mobile navigation, system font stacks, shared tab and
issuer links, CIK-keyed local watchlist, timezone/reset preferences, per-view saved
filters/sort, null-last sorting, numeric rounding, source links, row details,
paginated tape, filtered CSV (spreadsheet formula escaping), scoreless companies,
honest rank, actual turning-state and divergence screens, searchable Company Lab,
price-period selection, and explicit unavailable/empty states.
Company explorers and the v2 purchase-basis table render 25/50/100 rows per page,
with first/previous/next/last navigation. Filters and sort changes reset the page;
CSV exports retain every matching row. Page size is saved locally.

Removed: score-derived CEO/CFO cluster claims, market-wide claims based on a
buyer-selected population, unverified dollar totals across joint-owner records,
arbitrary cost-basis progress bars, empty backtest charts, inactive drill-down
buttons and today's purchase basis masquerading as a historical series.

The v1 adapter does **not** invent missing CIKs, owner relationships, transaction
dates/shares/10b5-1, coverage windows or state-change dates. Those remain visibly
unavailable until Package 2. Price history shows only actual exported dates, with
today's basis explicitly marked as a current reference line.

Published as `6de541e`: full branch/main CI and Pages passed; public desktop/mobile
readback showed 68 known companies and no JavaScript errors or horizontal overflow.

## Package 2 — canonical v2 producer

Implemented: versioned company/event/owner/score/series/cluster/coverage export; economic
event key includes accession, table and source row (never cross-filing fuzzy
deduplication). All owner links retained. Unresolved amendments suppress only
affected issuer aggregates and digest eligibility. Transaction-only companies
remain visible despite missing market data. Measure actual SEC-day completeness.

Reuse immutable normalized SEC Release checkpoints, process current days before
resumable 90-day backfill, persist prior states and daily history, and consolidate
the daily graph at 07:15 UTC Tue–Sat. Retire duplicate acquisition schedule only
after replacement is connected. Use a pinned exchange calendar for market
freshness (`exchange-calendars==4.13.2`, XNYS holidays and early closes).
Snapshot/hash/run validation remains atomic and fail-closed. UI-only restore and
settings attachment preserve the optional v2 document.

Factual snapshots are archived as immutable `research-day-v2-*` Releases with
read-back verification before allow-listed prior state is committed. Repeated
runs for the same market session do not advance state hysteresis. Joint-owner
facts count once, but legacy scores with unreconciled owner weights are withheld.
Unresolved identities and non-common-stock transactions remain inspectable but
are excluded from common-stock aggregates. No-market and stale-benchmark cases
retain valid SEC facts; predictive delivery remains blocked.

Multiple current SEC listings are resolved only when a recent, already-known
non-derivative common-stock filing corroborates exactly one current ticker.
The observation retains the filing accession, source hash, URL and knowledge
timestamp. Conflicting common-class evidence, source disagreement, foreign
incorporation and unsupported securities still fail closed. No ticker is chosen
by suffix, alphabetical order or transaction value.

Market caches are checksum/source validated and reusable while they contain the
latest closed XNYS session, including over weekends and holidays. A missing new
session forces refresh despite an unexpired TTL. Each of the three bounded
market shards has 30 minutes; the producer has a 60-minute workflow limit.
The 90% coverage target and benchmark freshness checks are unchanged.
Production overlaps the two provider requests instead of adding their latencies.
One shared source pool per shard caps concurrency at eight requests (four symbols
across two sources), with at most three shards. Source order still breaks freshness
ties, every successful source is cross-checked, and HTTP clients close only after
in-flight requests and cache writes finish. No extra retries or wider time budget
are introduced; SEC request pacing and score/digest policies are unaffected.

Identity history remains append-only in immutable Releases. Small legacy v1
archives are readable; larger v2 releases use CIK buckets and bounded chunks
with a content-addressed manifest. Publish occurs only after every draft asset
passes remote checksum, row-inventory, provenance and history-preservation
checks. Interrupted uploads remain drafts, never the current identity history.
No historical observations are deleted or assigned new knowledge timestamps.

The existing per-day immutable SEC checkpoint ledger tracks resumable progress.
Publishing a partial factual snapshot does **not** advance the older global
canonical cursor or claim that the full 90-day window is complete. The manual
SEC acquisition workflow remains available for bounded historical batches.

Verification: replay/economic grain/amendment/partial history/holiday calendar/
outage state/hash/schema/archive/restore and workflow contracts; 24 desktop and
mobile Playwright checks. CI and a real daily run are still required to confirm
the live integration, not inferred from offline fixtures.

## Package 3 — factual digest and operational acceptance

Separate policy and preview: latest complete SEC day, up to ten new qualified
open-market purchases >= $25,000 (`config/digest.v1.json`), largest first,
no score predicate or advice.
Durably persist channel/day claim before sending; uncertain delivery is never
retried automatically. Initial enablement never sends historical backlog. Existing
email configuration stays optional and predictive kill switch stays off.

Completion evidence must include real Telegram test delivery and two distinct
successful daily processing cycles. Replays and fixtures do not satisfy that
operational criterion. No completion or validated-model claim may be inferred
from an attractive UI or a green frontend test run.

## Preserved work

Incomplete amendment changes were checkpointed locally as `456da17` on
`codex/sec-amendment-evidence`, not merged into `main`. This implementation starts
at `354d61a` on `codex/daily-use-app`. Unrelated local probe files are untouched.
