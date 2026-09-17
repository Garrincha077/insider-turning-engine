# B1 runtime checkpoint — 2026-09-17

This note records the first real-data B1 runtime result after the Phase-1 B1/B4 workflow was unblocked. It does not change production scoring and does not open the sealed 2023+ OOS period.

## Run reached the real B1 evaluator

Workflow run `35261507885` successfully completed:

- frozen CMP artifact discovery for all years 2013-2019;
- research Ruff gate;
- B1/B2/B4 PIT semantic tests (`22 passed` before the new window test was added);
- bounded evidence download;
- authoritative P0 exact-calendar recomputation;
- P0 data-quality gate.

P0 remained `C_EXPLORATORY` with OOS closed and production scoring unchanged. The canonical B1 process then failed inside `_load_cmp_history` with:

`ValueError: sealed OOS boundary violated by CMP history`

## Root cause: impossible historical SEC transaction dates, not OOS filing leakage

Inspection of the frozen yearly CMP artifacts showed that `firstFiledDate` remained historical, but a small number of source transaction dates are impossible relative to their filing date. Examples include a 2013 filing with `tradeYear=2023` or `tradeYear=2031`.

Observed yearly diagnostics from the frozen 2013-2019 artifacts:

| archive year | rows before 2013 | rows after 2019 | in-window trade month later than filing month |
| --- | ---: | ---: | ---: |
| 2013 | 2,074 | 3 | 9 |
| 2014 | 530 | 2 | 14 |
| 2015 | 241 | 0 | 12 |
| 2016 | 69 | 0 | 10 |
| 2017 | 62 | 0 | 13 |
| 2018 | 52 | 0 | 7 |
| 2019 | 23 | 0 | 1 |

The large pre-2013 counts are mainly legitimate late-reported older history but are irrelevant to the predeclared B1 classifier window. The small future-dated counts are source-date anomalies and must not be allowed to create opportunistic/routine history.

## Resolution: derived bounded analysis view

The frozen source release `research-cmp-history-v1` remains unchanged. A new reproducible derived step, `scripts/research_cmp_history_window.py`, now builds the B1/B4 analysis view with the following rules:

1. retain only transaction years 2013-2019, the exact predeclared history needed for 2016-2020 annual classification;
2. exclude a transaction when its `(tradeYear, tradeMonth)` is later than the `(year, month)` of its first historical filing, because that transaction month is impossible at the time the filing became known;
3. treat any `firstFiledDate` in 2023+ as a hard error rather than filtering it;
4. preserve the original owner-month schema for the canonical B1/B4 evaluators;
5. persist a `window-summary.json` diagnostic so every exclusion remains auditable.

A dedicated regression test locks these semantics, including the observed 2013-style future-date anomaly and the hard sealed-filing failure.

This is a data-quality/PIT sanitation layer, not a signal-definition change. Production scoring remains unchanged and 2023+ remains sealed.
