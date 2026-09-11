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

Removed: score-derived CEO/CFO cluster claims, market-wide claims based on a
buyer-selected population, unverified dollar totals across joint-owner records,
arbitrary cost-basis progress bars, empty backtest charts, inactive drill-down
buttons and today's purchase basis masquerading as a historical series.

The v1 adapter does **not** invent missing CIKs, owner relationships, transaction
dates/shares/10b5-1, coverage windows or state-change dates. Those remain visibly
unavailable until Package 2. Price history shows only actual exported dates, with
today's basis explicitly marked as a current reference line.

Verification: frontend lint/typecheck/build; 18 Playwright checks across desktop
and mobile; rendered desktop/mobile review. Full GitHub CI and public readback are
required before this package is considered published.

## Package 2 — canonical v2 producer

Next: versioned company/event/owner/score/series/cluster/coverage export; economic
event key includes accession, table and source row (never cross-filing fuzzy
deduplication). All owner links retained. Unresolved amendments suppress only
affected issuer aggregates and digest eligibility. Transaction-only companies
remain visible despite missing market data. Measure actual SEC-day completeness.

Reuse immutable normalized SEC Release checkpoints, process current days before
resumable 90-day backfill, persist prior states and daily history, and consolidate
the daily graph at 07:15 UTC Tue–Sat. Retire duplicate acquisition schedule only
after replacement is connected. Use a pinned exchange calendar for market
freshness. Snapshot/hash/run validation remains atomic and fail-closed.

## Package 3 — factual digest and operational acceptance

Separate policy and preview: latest complete SEC day, up to five new qualified
open-market purchases >= $250,000, largest first, no score predicate or advice.
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
