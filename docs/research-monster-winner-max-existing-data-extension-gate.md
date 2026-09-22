# Monster Winner Enrichment v1 — maximum existing-data extension gate

Frozen: 2026-09-22 after F3_DRAWDOWN_252 and F4_DISTANCE_BELOW were
chronologically confirmed on 2019-2020 and before reading Monster outcomes
outside the completed 2016-2020 development period.

## User-requested extension interpretation

Use the broadest **already supportable comparable research period**, not an
artificial "through today" endpoint and not a new ad-hoc provider mix.

Available frozen research coverage:

- SEC insider PIT / amendments: 2013-2022;
- adjusted Alpaca SIP market corpus: 2016-2022;
- raw feature-formation market corpus:
  - 2016-2020 immutable v1;
  - 2021-2022 extension acquired with the same Alpaca SIP
    `adjustment=raw`, `asof=-` method before extension outcomes are read.

Therefore the comparable Monster feature universe begins in **2016**.
2013-2015 SEC warm-up cannot be scored under v1 because no matching frozen
market corpus exists for feature formation and path outcomes.

The maximum existing outcome boundary is **2022-12-30 / last XNYS session of
2022**. No 2023+ market data is opened.

## Frozen candidates

Only:
- `F3_DRAWDOWN_252`;
- `F4_DISTANCE_BELOW`.

Definitions, directions and Stage-A 2016-2018 cutpoints remain unchanged.

No F1/F2 resurrection and no F3+F4 composite is fitted.

## Extension cohort

Rebuild the canonical B0 issuer-event stream across complete 2016-2022 SEC
history with the same:
- exact evaluation-session mapping;
- exact next-XNYS entry;
- 20-XNYS issuer dedup across year boundaries;
- ambiguous identity exclusion.

Then slice evaluation sessions:
- 2021-01-01 through 2022-12-31.

Feature formation is outcome-blind.

## Feature formation

F3_DRAWDOWN_252:
- adjusted market only;
- exact evaluation-session close;
- trailing 252 regular observations;
- same formula and frozen Q5 cutpoint from Stage A.

F4_DISTANCE_BELOW:
- same 90-calendar-day PIT insider purchase basis;
- same raw-price semantics;
- same frozen Q1 cutpoint from Stage A;
- raw market extension must use the same Alpaca SIP feed / raw adjustment /
  disabled symbol mapping semantics as 2016-2020.

## Outcome maturity

The primary label remains:
`M100_252_CLOSE`.

For an extension event, compute a full primary label only if:
- exact entry exists;
- exact 252-session target is <= last available 2022 XNYS session;
- holder-path continuity and market coverage satisfy the already-frozen Monster
  outcome rules.

If the 252 target falls in 2023 or later:
- primary status = `RIGHT_CENSORED_AT_DATA_BOUNDARY`;
- it is excluded from primary positive-density/lift denominators;
- it is never converted to NEGATIVE or UNKNOWN due merely to unavailable
  post-2022 sessions.

Secondary 126-session labels may be reported when their exact target is <= the
2022 boundary.

## Reporting

Produce:
- 2021 and 2022 event counts;
- mature / right-censored counts by horizon;
- F3 and F4 preferred/complement counts;
- M100/252 POSITIVE / NEGATIVE / UNKNOWN for mature events only;
- density and lift on mature comparable cohorts only;
- M100 capture / review share;
- M200/M500 and 126-session diagnostics where mature;
- annual metrics;
- one combined longitudinal table joining immutable 2016-2018 discovery,
  2019-2020 confirmation, and the new 2021-2022 available-data extension.

The 2021-2022 section is labelled:
`KNOWN_SAMPLE_MAX_AVAILABLE_EXTENSION`.

It is not called fresh validation or OOS.

## Hard boundary

- no 2023+ market data;
- no current/today data;
- no alternate data source to fill missing 2013-2015 market history;
- no retuning;
- no composite fitting;
- no production change.
