# Filing-linked financial evidence — first component

Status: implemented offline normalization/selection/calculation, **not yet wired
into public snapshots or ranking**. Part of the active Compass & Turning goal.
No predictive delivery, production score or historical performance claim changes.

## Source and availability contract

The free SEC Company Facts API provides standard-taxonomy facts associated with
accessions, units and reporting periods. The frames endpoint is latest-filed and
is not a historical availability clock. Exact filing acceptance timestamps must
come from verified submissions/header evidence and join by accession.
https://www.sec.gov/search-filings/edgar-application-programming-interfaces

The normalizer takes a requested issuer, a bounded concept manifest, an explicit
acceptance index and an as-of timestamp. Wrong issuers/naive clocks fail. Missing
acceptance, unsupported units, invalid/nonfinite values and ambiguous contexts
are recorded rather than silently repaired. Filing dates must match acceptance's
New York civil date, not its UTC date. Negative earnings are valid losses.

Future filings/restatements are removed before selection. A later available
amendment can replace an earlier value for the same period only at its acceptance
time. Conflicting values in a newest context block that context; selection does
not resurrect an older healthy value to disguise it. Exact duplicate observations
and input ordering leave normalized output unchanged.

Instant, annual and quarterly durations are distinct. Annual duration350–380days
supports53-week years; quarterly70–110days never consumes year-to-date9M figures.
There is no invented TTM aggregation or currency conversion. Source-standard tags
are preserved; superficially similar tags are not automatically substituted.

## Small evidence panel (not a value score)

- Annual net margin requires same start/end income/revenue facts.
- Liabilities/assets requires the same balance date and is not applied as a
  generic leverage/cheapness factor to financials, REITs or unknown sectors.
- Annual return on reported stockholders' equity uses beginning/ending equity
  of that income year, never a newer quarterly denominator.
- Annual diluted-share change compares complete annual periods; it cannot be
  altered by a future reported previous-year value. It is descriptive dilution
  context, not automatically net capital raised or raw-share split inference.
- Reported annual P/E is explicitly **annual, not TTM**. It additionally requires
  an as-of public unadjusted price, market-calendar freshness within one session,
  explicit comparable share/split-basis proof and positive annual diluted EPS.
  Available time includes BOTH filing and price. REIT GAAP EPS is not substituted
  for FFO/AFFO. No proof means unavailable, not a neutral/positive valuation.

Every metric retains period, accessions, SEC URLs, available time and reason codes;
P/E also retains price provenance/session. Period age beyond550days is explicitly
flagged. No metric currently calls an issuer cheap without relevant comparisons.
Financial-specific book/tangible-book measures and REIT FFO remain open, not
faked by applying industrial EV ratios or generic net-income multiples.

## Actual-source probe, Oct26

Read two official SEC documents for issuer0000320193 (Apple): current Company
Facts and submissions. No credentials, price acquisition, returns or delivery.
Source SHA25673a86c6aedc31f77cac2ea4df5f80f0b3bd7e6eb58bb4e01444fbedf3afb9c43;
submissionsSHA2565891cf875f690e38f26ca628f7091184c9d73ca34ca7646b9cecd5013aeac4ab.
The requested initial concepts produced406 joined facts and240 unresolved older
concept/accession rows without current-submissions acceptance evidence. These
are not claimed complete history; archived submissions hydration remains needed.

Latest selected annual net income:112010000000USD,end2025-09-27,
accession0000320193-25-000079,accepted2025-10-31T10:01:26Z.
Latest selected assets:383266000000USD,end2026-06-27,
accession0000320193-26-000020,accepted2026-07-31T10:01:02Z.
Annual dilutedEPS7.46USD/shares uses the annual accession, not the newer assets'
date. This is an availability/grain probe, not a complete Apple valuation or a
historical investable-performance demonstration.

Raw/cache and the local receipt stay outside git in .codex/fundamentals-20261026.

## Remaining before delivery

The next component adds bounded identified SEC acquisition, an exact-byte
checksum-backed persistent cache, source receipts and at most three archived
submissions documents per issuer. It reuses the six-request/second transport,
host/redirect/content-type/size guards and two-attempt bounded retry policy.
Recent submissions expire after six hours. Company Facts can replay for seven
days only when it already includes the newest relevant financial accession;
a newly observed filing forces refresh. Archives are chosen by their actual
filing-to metadata, not an assumption about filename ordering. Invalid/misaligned
acceptance arrays, conflicting timestamps and unsafe archive names fail closed.

Actual Apple seven-concept cache probe: three official sources,132 financial
acceptance joins,976 usable facts and164 unresolved/invalid context issues.
One archive was requested with no remaining archive inventory. Repeated replay
was byte/hash-identical and all three resources came from verified disk cache.
This does not mean every requested historical context is usable: the164 issues
remain explicit, not silently date-imputed. The four non-price financial metrics
were reproducible; P/E stayed null without price/share-basis evidence. This is
not yet a scheduled fundamental-refresh or public Company Lab delivery.

Next: hydrate relevant current candidates,
measure actual concept/sector coverage, extend public schema/export/TypeScript
together and display the panel in Company Lab without blocking independent facts.
Only then consider the separate Turning v2 candidate/valuation integration.

Historical claims additionally require preserved source versions and a documented
restatement/filing provenance audit. Current Company Facts retrieval plus this
selector is not by itself proof of a complete historical PIT fundamental dataset.
