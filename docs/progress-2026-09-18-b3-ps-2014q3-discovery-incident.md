# Phase-1 B3 P/S — 2014Q3 accession-discovery incident

Date: **2026-09-18**  
Scope: research-only data-quality recovery for the original P/S PIT history.  
OOS: **2023+ remains sealed.**  
Production scoring: unchanged.

## Observed incident

The full-history P/S run reached 2014 Q3 after successfully persisting:

- 2013 Q1-Q4;
- 2014 Q1-Q2;
- the previously frozen 2016 Q1 pilot quarter.

2014 Q3 failed repeatedly at the unchanged quality gate:

`P/S accession discovery is incomplete`

The failure occurred after the normal daily-index discovery plus the pre-existing archive fallback. It did **not** arise from:

- B3 signal logic;
- market outcomes;
- buy/sale concordance threshold tuning;
- parser rule relaxation;
- 2023+ evidence.

The 100% discovery/hydration gate remains unchanged.

## Root-cause finding

The pre-existing archive fallback constructed complete-submission paths only from verified **reporting-owner CIKs**.

SEC's documented EDGAR archive structure uses:

`/Archives/edgar/data/{CIK}/{accession-without-dashes}/{accession}.txt`

SEC also documents that the first ten digits of an accession identify the submitting entity and can therefore differ from the archive parent entity when a filing agent submits the filing.

Historical Form 4 examples confirm that the archive parent directory is the **issuer CIK** even where the accession prefix is a third-party filer and the reporting-owner CIK is different.

Primary SEC references used for the data-integrity correction:

- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- https://www.sec.gov/Archives/edgar/data/1013237/000143774914022256/0001437749-14-022256-index-headers.html
- https://www.sec.gov/Archives/edgar/data/105319/000120919114050967/0001209191-14-050967-index-headers.html

## Frozen recovery rule

For an accession that is not found through the bounded daily-index search:

1. try the archive path derived from the already verified quarterly-bulk **issuer CIK**;
2. if not found, try each distinct already verified **reporting-owner CIK** as a secondary path;
3. do not use ticker, company name, fuzzy matching, market outcomes or future mappings;
4. regardless of path, the fetched filing must still pass:
   - exact accession/header validation;
   - issuer CIK equality with the frozen quarterly-bulk candidate;
   - ownership XML extraction;
   - canonical parser validation;
   - exact SEC acceptance datetime;
   - `knowledgeAt == acceptedAt`;
   - 2023+ seal.

A successful issuer-CIK fallback is not represented as daily-index discovery. Its provenance records `archiveCik`, `archiveCikBasis` and `VERIFIED_ACCESSION_ARCHIVE_FALLBACK`.

## Why this is not performance tuning

This rule is based exclusively on SEC archive addressing and filing identity. No price, return, winner/loser label, B3 score or later outcome is consulted.

The B3 signal definition remains unopened.

## Workflow behavior

The full-history hydration matrix is now resumable with `fail-fast: false`.

A failed quarter:

- remains absent from the persistent quarter release;
- does not cause later independent quarters to be dropped;
- retains the 100% coverage requirement;
- is retried only under deterministic recovery rules.

Failed shard diagnostics are persisted on later attempts so exact accessions and failure reasons remain auditable.

## Current state at this checkpoint

- original P/S persistent quarters: **7 / 40**;
- 2014 Q3: unresolved discovery incident;
- 2014 Q4: continuing independently;
- P/S amendment gate: not opened;
- B3 definition: not frozen;
- B3 performance: not computed;
- `oosOpened=false`;
- `productionScoringChanged=false`.
