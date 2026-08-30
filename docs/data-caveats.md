# Data caveats and interpretation

This project is research-only and is not investment advice. A score or state is
an explainable rule output, not a recommendation, probability, or guarantee.
Do not describe the checked-in sample dashboard or fixture results as live
validated performance.

## Caveats required on every report

The following caveat block must appear on every generated or manually written
report, including dashboards, backtest splits, OOS summaries, and alert
digests:

> Survivorship: the issuer universe may omit inactive, merged, bankrupt, or
> otherwise unavailable names. Coverage: missing SEC filings, market bars,
> reference data, or quarantined rows can change denominators and rankings.
> Tickers: ticker is a point-in-time attribute, not issuer identity; ticker
> changes and unresolved mappings can exclude observations. Sectors: sector and
> industry labels are versioned and may be unavailable or revised as of the
> historical date. Delisted attrition: a missing exit/return is retained with a
> reason (for example `DELISTED_RETURN_21`) and is not treated as zero. Research
> only; not investment advice.

Attach counts/rates for each report: requested and covered issuers, missing or
quarantined rows, unresolved ticker mappings, sector availability, delisted
events, and horizon-level attrition reasons. A zero denominator is
`NOT_EVALUATED`, never 100%.

## Source and temporal caveats

- SEC ownership data describes disclosed transactions, not every economic
  exposure. Filing/acceptance time is disclosure time; transaction date is not
  an availability timestamp.
- SEC and market providers can revise or arrive late. A historical snapshot is
  bound by `knowledge_at`/`available_at`; a later correction creates a new run,
  not a silent rewrite.
- Stooq daily data is an anonymous fallback/reference source and may have
  missing sessions, revisions, unadjusted prices, or provider-specific limits.
  The CSV fallback is deterministic but synthetic fixtures are fabricated.
- Adjustments, splits, holidays, and trading calendars affect returns and
  moving features. The report must state the adjustment basis used.
- No fundamental factor is silently imputed. A null fundamental is excluded
  and Total is renormalized; the exclusion is visible in the snapshot.

## Backtest caveats

Development is 2016–2020, validation is 2021–2022, and OOS is sealed from
2023-01-01 through the last complete month before the run reference date.
Event scheduling uses public knowledge time and next-session-open entry. The
21/63/126/252-session outcomes are conditional on having the required bars.
Attrition, duplicate suppression, coverage, and universe counts must be shown
beside any return statistic. OOS cannot be used to tune or evaluate a model;
only a final report may reveal it.
