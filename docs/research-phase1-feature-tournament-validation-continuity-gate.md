# Phase-1 F2 validation continuity-audit gate

Frozen after the outcome-blind validation scope and before any 2021-2022
validation-event return is read.

## Frozen validation scope

Release:
`research-phase1-insider-feature-tournament-validation-scope-v1`.

Pinned summary asset:
- `summary.json`
- SHA-256:
  `sha256:c30fe291ddab95f9022c4d7e9b6c11655c6bf34822bae0d8fe94a417d51b021b`

Semantic scope key:
`sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3`.

Frozen scope facts:
- 7,493 eligible 126-session validation rows;
- 3,037 distinct issuers;
- 6,886 rows with F2 primary-contrast observation;
- 1,687 INDIRECT_ONLY;
- 5,199 DIRECT_ONLY;
- 606 MIXED;
- 1 UNKNOWN;
- 2,645 events right-censored before outcome read because the 126-session
  target would exceed 2022-12-31;
- validationOpened=false;
- outcomesRead=false;
- oosOpened=false.

The release tar may be re-created byte-for-byte differently by GitHub because
of archive timestamps. Therefore downstream consumers must pin the summary
digest and recompute the semantic scope key from the extracted CSV. The CSV is
accepted only if the recomputed key equals the value above.

## Audit inputs

Corporate actions:
- Alpaca corporate-actions endpoint;
- bounded to 2016-01-01 through 2022-12-31;
- frozen action-type list already used by Phase-1 continuity work;
- event tickers restricted to the exact validation scope.

Market-presence evidence:
- frozen `research-market-alpaca-v1` archives 2016-2022;
- only date, ticker, volume, trade_count and terminal_candidate are used for
  long-gap diagnosis;
- no OHLC value or return is read by the continuity audit.

## Initial continuity classification

For every validation row:

1. inspect bounded corporate actions inside
   `entrySession < actionDate <= targetExitSession`;
2. apply the already-frozen provider-state rules;
3. fail closed when a transformed-holder provider row lacks complete
   deterministic economic terms;
4. compute the maximum internal gap from regular-session presence only;
5. if an otherwise ordinary adjusted-price row has a gap of at least 10 XNYS
   sessions, classify it `UNRESOLVED_CONTINUITY` from
   `long_internal_gap`;
6. preserve every candidate action ID/type and gap diagnostic.

A provider transformation is economically complete only if the exact single
provider action supplies all terms required by its frozen type:
- cash merger: non-negative cash rate;
- stock merger: positive acquiree/acquirer rates plus successor symbol;
- stock-and-cash merger: the same plus non-negative cash rate;
- redemption: non-negative redemption rate.

Anything incomplete is unresolved even if the provider state label alone would
otherwise say transformed holder consideration.

## Boundary

This stage is an **audit**, not a validation-performance run.

It may publish unresolved continuity rows for later evidence resolution.
Validation performance remains blocked until:
- every unresolved row is deterministically resolved; and
- provider holder-consideration semantics are complete for every valued
  transformed row.

No validation return, SPY-excess value, validation PASS/FAIL result, 2023+
price or production score may be read or changed here.
