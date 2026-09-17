# B1 top-10 security-continuity verification results — 2026-09-17

Frozen verification protocol: `docs/research-phase1-b1-security-continuity-gate.md`  
Frozen verification record: `research/b1-security-continuity-top10.json`

This is a development-only data-validity audit. No event is automatically deleted, no signal definition changes, production scoring is unchanged, and 2023+ OOS remains sealed.

## Classification summary

| Class | Count |
| --- | ---: |
| `CONTINUOUS` | 7 |
| `TRANSFORMED_WITH_CONSIDERATION` | 1 |
| `DISCONTINUOUS_CANCELED_OR_REUSED` | 2 |
| `UNRESOLVED` | 0 |

## Frozen top-10 conclusions

| Rank | Ticker | Classification | Canonical raw return economically reproducible? | Finding |
| ---: | --- | --- | --- | --- |
| 1 | OAS | `DISCONTINUOUS_CANCELED_OR_REUSED` | No | Legacy common was canceled in Chapter 11 on 2020-11-19; old common holders received warrants, while new common went to allowed note claims. The later OAS common is reorganized successor common, not one-for-one continuation of the entry share. |
| 2 | AI | `DISCONTINUOUS_CANCELED_OR_REUSED` | No | Arlington changed ticker AI -> AAIC effective 2020-10-26. C3.ai later listed different issuer common under AI. The canonical same-ticker chain crosses issuers. |
| 3 | OSTK | `CONTINUOUS` | Yes for common-price path | Common remained OSTK. A Series A-1 preferred digital dividend was distributed; this is additional holder consideration but did not replace/cancel common. |
| 4 | LOV | `TRANSFORMED_WITH_CONSIDERATION` | No as a 1:1 same-ticker chain | Ten old Spark Networks, Inc. shares converted into one successor Spark Networks SE ADS. The later LOV ADS cannot be treated as one successor share for each old common share. |
| 5 | CRDF | `CONTINUOUS` | Yes | Trovagene -> Cardiff Oncology / CRDF change became effective before the canonical entry; same issuer/security remained CRDF through exit. |
| 6 | TST | `CONTINUOUS` | Yes | Maven acquisition was announced inside the window but did not close until 2019-08-07, after the canonical 2019-06-17 exit. |
| 7 | CWEI | `CONTINUOUS` | Yes | Noble acquisition agreement and closing occurred after the canonical 2016-10-04 exit. |
| 8 | APPS | `CONTINUOUS` | Yes | Digital Turbine remained the same APPS registrant/common through the canonical exit. |
| 9 | PEIX | `CONTINUOUS` | Yes | PEIX remained the ticker through 2021-01-31; ALTO began 2021-02-01, after the canonical 2021-01-11 exit. |
| 10 | HEAR | `CONTINUOUS` | Yes | Turtle Beach had a 1-for-4 reverse split in April 2018, but the research backfill explicitly uses Alpaca `adjustment=all`, so the canonical market series is split-adjusted. |

## Primary evidence highlights

### OAS

SEC Form 8-K dated 2020-11-19 states that Legacy Oasis existing equity interests were canceled on emergence from Chapter 11. It also states that old common holders received warrants, while 100% of new common stock was issued to allowed note claims. This directly invalidates a naive old-common-to-new-common same-ticker chain.

Primary: https://www.sec.gov/Archives/edgar/data/1486159/000148615920000115/oas-20201119.htm

### AI

Arlington Asset Investment announced that its Class A common ticker would change from `AI` to `AAIC` effective 2020-10-26. C3.ai's December 2020 SEC filing identifies its separate Class A common stock under `AI`. The original Arlington holder therefore continued in AAIC rather than into C3.ai.

Primary:
- https://www.sec.gov/Archives/edgar/data/1209028/000156459020047280/ai-ex991_6.htm
- https://www.sec.gov/Archives/edgar/data/1577526/000162828020017407/c3ai-closing8xk.htm

### LOV

Spark Networks disclosed that old Spark Networks, Inc. stockholders were entitled to **one newly issued Spark Networks SE ADS for every ten old common shares** immediately before the merger effective time. This is genuine holder continuity, but not one-for-one price continuity.

Primary: https://www.sec.gov/Archives/edgar/data/1314475/000114420417055907/tv478498_ex99-1.htm

### HEAR and adjusted market-data convention

Turtle Beach disclosed a 1-for-4 reverse split effective after the 2018-04-06 close, with split-adjusted trading beginning 2018-04-09.

Primary: https://www.sec.gov/Archives/edgar/data/1493761/000149376118000016/hear201846-8k.htm

The repo market backfill sends Alpaca `adjustment=all`, stores `is_adjusted=true`, and records `adjustment_basis=alpaca-adjustment-all`. Alpaca's Historical Bars documentation defines `all` as split + cash-dividend + spin-off adjustment. Therefore no separate 4:1 HEAR price correction is applied by this audit.

## Consequence for canonical B1

The top-tail result is not merely heavy-tailed market behavior: at least two of its most influential observations contain genuine security-identity discontinuities, and one more contains a non-1:1 holder transformation.

However, the frozen anti-selection rule prohibits deleting only OAS/AI/LOV after observing that they are large winners. The correction must be **cohort-wide and performance-blind**, including any affected losing observations.

Accordingly, `docs/research-phase1-market-security-continuity-correction-gate.md` is frozen before any corrected B1/B2/B4 performance is read. It defines a whole-cohort continuity ledger and holder-basis correction procedure.

## Current research state

- `researchOnly=true`
- `oosOpened=false`
- `productionScoringChanged=false`
- `formalAlphaClaim=false`
- corrected performance: **not yet read**
- next required stage: generate/freeze the full development continuity ledger before any corrected performance rerun.
