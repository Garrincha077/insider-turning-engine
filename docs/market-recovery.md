# Daily price acquisition and factual digest — October 2026

The daily market pass keeps three disjoint shards, four symbol workers per
shard, eight-second HTTP timeouts and a 30-minute per-shard budget. Symbols
that were never reached before that budget get one additional ten-minute pass.
Successful symbols and source-disagreement failures are not refetched by that
pass. There is no endless retry, stale-price substitution or SEC reacquisition.
The workflow leaves bounded time for acquisition, cache persistence and reports.

Both provider caches retain payload size, checksum and provenance verification.
New manifests include a last-session hint: it may reject an obviously stale
cache without materializing thousands of bars, but can never prove freshness.
Accepted caches still parse their actual dates; old manifests still work. Yahoo
cache bars are materialized once per lookup, and invalid network payloads are
not saved. No price values or adjustment formulas were changed.

market-status.json records requested/available counts, safe failure codes,
recoveryAttempted and recovered. Its provider population includes benchmarks;
the public selected-stock coverage has a different denominator. The independent
watchdog warns when actual selected-stock coverage falls below the accepted
80% daily-use target, even if deployment and factual digest succeeded. Missing
benchmark evidence also warns. The predictive 90% gate is unchanged. Published
SEC facts and a valid factual digest are not suppressed by missing stock prices.

The digest now selects up to ten distinct issuer CIKs with qualified purchases
of at least $25,000, showing the single largest qualifying purchase per company.
It does not sum a company's transactions into that displayed amount. Its day
claim, complete-current-SEC-day requirement and no-backlog/no-uncertain-retry
guards remain. A quiet day can legitimately produce fewer companies; even at
$10,000 the independently inspected October 8 SEC day had only CRBG and IMMR.
Policy changes do not resend an already claimed day.
