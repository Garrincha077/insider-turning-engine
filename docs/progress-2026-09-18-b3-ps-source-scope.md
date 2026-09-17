# B3 P/S PIT source scope — 2026-09-18

This checkpoint records the source-universe inventory measured from already frozen SEC bulk candidate artifacts **before** the 2016-Q1 P/S hydration pilot produced any concordance result.

It is research/data-scope evidence only. It does not define B3 and does not contain market outcomes.

## Frozen source families

- 2013–2015: warm-up source artifacts from workflow run `35060455633`.
- 2016–2022: P/S candidate artifacts from run `34884538222`, backed by verified SEC bulk history run `34883719192`.
- Exact source artifact identities and digests are frozen in `research/b3-ps-source-manifest-v1.json`.

All source years are <= 2022. 2023+ OOS was not opened.

## Original Form 4/5 P/S candidate scope

Candidates are original Forms 4/5 with at least one verified SEC bulk non-derivative priced positive-share `P/A` or `S/D` row.

| year | P/S original filings | buy-only | sale-only | mixed buy/sale |
| ---: | ---: | ---: | ---: | ---: |
| 2013 | 64,485 | 15,557 | 48,745 | 183 |
| 2014 | 62,323 | 17,108 | 44,967 | 248 |
| 2015 | 59,470 | 19,831 | 39,426 | 213 |
| 2016 | 52,967 | 16,995 | 35,761 | 211 |
| 2017 | 54,772 | 14,647 | 39,993 | 132 |
| 2018 | 55,281 | 18,643 | 36,468 | 170 |
| 2019 | 52,504 | 16,840 | 35,523 | 141 |
| 2020 | 56,699 | 18,030 | 38,517 | 152 |
| 2021 | 62,726 | 14,015 | 48,549 | 162 |
| 2022 | 49,064 | 16,668 | 32,281 | 115 |
| **Total** | **570,291** | **168,334** | **400,230** | **1,727** |

Thus:

- filings containing a qualified buy candidate: **170,061**;
- filings containing a qualified sale candidate: **401,957**;
- sale-only filings: **400,230**, or **70.18%** of the full original P/S filing universe.

This is why the existing original-buy PIT history cannot be used as a complete company-net-buying denominator: sale-only filings are not a marginal omission.

## 2016-Q1 frozen pilot scope

The 2016-Q1 P/S pilot contains:

- total original P/S filings: **13,088**;
- buy-only: **5,424**;
- sale-only: **7,606**;
- mixed: **58**;
- buy-candidate accessions: **5,482**;
- sale-candidate accessions: **7,664**.

The pilot gate, including the predeclared >=99.5% bulk/canonical accession concordance threshold for each side, was frozen before any pilot concordance result was observed.

## Boundary

- `researchOnly=true`
- `oosOpened=false`
- `productionScoringChanged=false`
- no B3 window, threshold, weighting or performance has been selected;
- the full P/S backfill remains blocked on the frozen 2016-Q1 pilot;
- B3 remains blocked after original P/S backfill until the separately predeclared broader P/S amendment-reconciliation gate passes.
