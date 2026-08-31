# Methodology

This document describes the intended, reproducible research contract. It does
not certify live data quality or performance. The executable authority for v1
weights and thresholds is [`config/scoring.v1.yaml`](../config/scoring.v1.yaml);
the matching [`config/scoring.v1.lock.json`](../config/scoring.v1.lock.json)
attests its exact bytes, lineage, freeze time, and source commit. The schemas
and accepted architecture decisions are the interchange and lineage contracts.

## Information boundary and data lifecycle

The pipeline is append-first and idempotent:

1. Fetch raw SEC or market payloads with provider identity, retrieval time,
   source timestamp, locator, and content hash. Raw payloads are evidence, not
   trusted facts.
2. Parse and normalize into canonical observations. Missing required identity,
   time, or economic fields are quarantined; they are not silently coerced.
3. Resolve issuer/owner identity. SEC CIK is the stable issuer key; ticker is a
   valid-time attribute and never identity. Amendments create revisions,
   superseded/void rows remain addressable, and duplicate delivery is a no-op.
4. Select only active revisions known at `as_of`. `knowledge_at` is the later
   of source-publication and first-observed time; market/reference facts use
   `available_at`. Future knowledge cannot enter an earlier snapshot.
5. Build bounded features, apply `scoring.v1`, evaluate `state.v1`, and persist
   immutable signal snapshots with input watermarks and provenance.
6. Create alert candidates separately from delivery. The outbox records emitted,
   suppressed, failed, and uncertain attempts with idempotency keys.
7. Export a compact browser projection only after schema, hash, temporal, and
   quality validation. Reprocessing creates a new run/snapshot; it does not
   rewrite history.

## Data sources and fallback

SEC quarterly bulk archives and the SEC submissions/ownership XML path are the
authoritative filing sources. SEC requests require an identifying
`SEC_USER_AGENT`, are paced at no more than 6 requests per second across the
process, and should be cached. Stooq is the anonymous daily OHLCV provider for
SPY and supported sector ETFs; its adapter uses bounded retries, no redirects,
and a five-minute in-memory cache. The canonical CSV provider is the offline
fallback and fixture path. Every provider maps into the same provider-neutral
`DailyBar` contract; provider-specific fields do not enter scoring.

## Scores

All component values and final scores are bounded to `[0, 100]`. Unknown model
components reject a score. Weights are frozen in `scoring.v1` and must sum to
1.0 per model.

| Model | Components and weights |
|---|---|
| Market Pulse | transaction 0.15; unique insiders 0.20; dollar 0.20; volume 0.10; company breadth 0.15; conviction-weighted 0.20 |
| Company Insider | conviction 0.45; cluster 0.25; opportunistic 0.20; net buying/absence of sales 0.10 |
| Divergence | price weakness 0.35; insider activity percentile 0.35; acceleration cluster 0.20; absence of relevant sales 0.10 |
| Turn | base structure 0.35; ordinary RS turn 0.25; Mansfield market 0.15; Mansfield sector 0.10; volume accumulation 0.10; cost-basis reclaim 0.05 |
| Total | divergence 0.25; conviction 0.15; cluster 0.10; opportunistic 0.10; base 0.10; ordinary RS 0.10; Mansfield RS 0.10; volume 0.05; fundamental 0.05 |

The current lock attests these weights and thresholds, but the configuration
does not yet specify every raw-feature-to-`[0, 100]` transform used by Turn and
Total. It is therefore a config-drift guard, not yet a complete methodological
freeze. Those transforms and their implementation lineage must be reviewed,
versioned, and re-locked on a clean commit before sealed OOS is opened.

The Total model is the sole exception: a null fundamental excludes that factor
and renormalizes the other weights (the null is recorded in
`excludedFactors`). Missing any other factor rejects the score. A score is
never a probability or a forecast return.

## State machine

The public states are exactly:

`FALLING -> INSIDER_ACCUMULATION -> BASE_FORMING -> EARLY_TURN -> CONFIRMED_TURN`.

Promotion is one edge per evaluation; skipped states are not allowed.

- `FALLING`: `return_3m < 0` and `close < ma50` (both strict).
- `INSIDER_ACCUMULATION`: drawdown from the 52-week high `<= -20%`, company
  insider score `>= 65`, and qualified buy age `<= 30` days.
- `BASE_FORMING`: prior accumulation, no new 52-week low for 20 sessions, and
  at least two of volatility contraction, volume dry-up, and MA20 flattening.
- `EARLY_TURN`: prior base, turn score `>= 60`, improving ordinary RS over four
  weeks, and strictly positive four-week Mansfield-market slope.
- `CONFIRMED_TURN`: prior early turn, close above MA50 on at least 5 of the
  last 10 sessions, and Mansfield market `>= 0` or a cost-basis reclaim.

One failed evaluation is held with `DOWNGRADE_PENDING`; the second consecutive
failure downgrades one edge. A passing evaluation clears the failure counter.
A new 52-week low immediately resets to `FALLING`. State evidence and the
evaluation sequence are part of the snapshot.

## Alerts

The exact public alert types are `MAJOR_INSIDER_BUY`, `STEALTH_ACCUMULATION`,
and `TURNING`.

- `MAJOR_INSIDER_BUY`: conviction `>= 80` with transaction value `>= $250,000`,
  or value `>= $1,000,000`, or any `strong_cluster`, `first_buy`, or
  `largest_buy` flag.
- `STEALTH_ACCUMULATION`: company insider `>= 70`, divergence `>= 75`, turn
  `>= 45`, no new 52-week low for 20 sessions, and both ordinary-RS and
  Mansfield-market slopes strictly positive.
- `TURNING`: transition to `EARLY_TURN` or `CONFIRMED_TURN`, total `>= 75`,
  company insider `>= 65`, and divergence `>= 65`.

Delivery is separate from candidate creation. The default cooldown is 14 days
per issuer and alert type. A cooldown may be overridden by a state, severity,
important-flag, or absolute score change of at least 7. Suppressed candidates
remain auditable; quality failures suppress delivery rather than erase the
candidate.

## Backtest design

The deterministic event study uses frozen scored signals, not a tuner or scoring
callback. Windows are:

| Split | Sessions |
|---|---|
| Development | 2016-01-01 through 2020-12-31 |
| Validation | 2021-01-01 through 2022-12-31 |
| Sealed OOS | 2023-01-01 through the last complete calendar month before the reference date |

The OOS endpoint is bounded: for example, a run during August uses July 31 as
the last complete month end. OOS is inaccessible to evaluator and tuner APIs;
only an explicit final-report path may reveal it. Signals are scheduled from
`knowledge_at` (or SEC `accepted_at`), evaluated at the first daily close at or
after that timestamp, and entered at the next market-session open. Outcomes
use exact 21-, 63-, 126-, and 252-session horizons, SPY excess return, and
maximum adverse excursion. Signals are deduplicated within the configured
20-session window by issuer CIK when supplied (otherwise legacy ticker) and
exposure family, including matching `*_ALERT` / `*_SIGNAL` families. A
timestamped feature must be available no later than that event session's
daily close; timezone-aware timestamps are compared at full precision.

Each evaluated signal carries `scoring.v1`, the frozen scoring-config hash,
lineage, and the exact timezone-aware `frozen_at` value from the checked-in
lock. One run must share that provenance. The lock proves which configuration
was frozen and when; it does not by itself prove that an analyst had not
already inspected historical OOS outcomes. Formal PASS therefore separately
requires an explicit `temporal_valid` attestation that the OOS result remained
sealed until the scoring decision was final. Missing future bars, including a
missing intermediate low/bar in the MAE path, are retained as named attrition or
quality evidence, never converted to zero return. The final report also lists
adjustment-basis, survivorship, missing issuer/ticker identity, missing sector,
and missing-return counts.

## Report disposition

Use these labels in reports and release notes:

- `PASS`: the positive lower confidence bound is based on at least 200
  observed, eligible 6M OOS outcomes in both compared selections (retained
  event count is not a substitute); all required schemas/hashes and
  point-in-time checks pass; canonical parse success is at least 99.5%, market
  coverage at least 90%, core branch coverage at least 85%, and the benchmark
  is current.
- `INCONCLUSIVE`: the run is structurally usable but a required outcome or
  denominator is incomplete/unknown, including any missing validation evidence
  (parse, market, coverage, canonical/schema/hash/temporal validity, or
  benchmark freshness), an unfinished result, or a sealed OOS report. Do not
  promote it to a performance claim.
- `FAIL`: any look-ahead violation, corrupt or mismatched artifact, invalid
  canonical input, stale benchmark, explicit quality-gate failure, or below-
  threshold quality metric. Block publication or mark it visibly degraded per
  run policy; never show a green/healthy status.

## Required caveat block

Every report—development, validation, OOS, dashboard, and alert summary—must
carry this limitation block, with counts where available:

> Research-only output; not investment advice. Results may be affected by
> survivorship and universe selection, incomplete issuer/market coverage,
> ticker changes and point-in-time mapping, sector classification revisions,
> delisted securities and return attrition, corporate actions, stale or
> missing prices, and quarantined or amended filings. Missing outcomes are
> reported as attrition and are not zero-return observations.
