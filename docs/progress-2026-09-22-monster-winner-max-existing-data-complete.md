# Monster Winner Enrichment v1 — maximum existing-data extension complete

Date: 2026-09-22

This checkpoint extends the already-confirmed Monster Winner development
candidates only as far as the existing comparable research corpus supports.

No 2023+ market data was opened.

## Maximum comparable data boundary

Available frozen research corpus:
- SEC insider PIT/amendments: 2013-2022;
- adjusted Alpaca SIP market: 2016-2022;
- raw feature context: 2016-2022 after the outcome-blind 2021-2022 extension.

Therefore:
- 2013-2015 remain warm-up/history only because comparable market data are not
  available under the same frozen market framework;
- the comparable Monster period starts in 2016;
- market outcomes stop at 2022-12-30.

## Raw feature context extension — COMPLETE

Workflow run: **35754695209 — SUCCESS**

Release:
`research-market-alpaca-raw-feature-context-2021-2022-v1`

- 2021 raw asset SHA-256:
  `sha256:774998d2d64b8f439c3384f1c8d5a91d11a689feb393395d0158cac5df431500`;
- 2022 raw asset SHA-256:
  `sha256:bd6d8d9c1164a4fbf20bc8debca87a39627ff7c3907ef2beae5227077e3848fe`.

Same Alpaca SIP / adjustment=raw / asof=- semantics as 2016-2020.
No outcomes were read in this acquisition stage.

## 2021-2022 feature/maturity scope — COMPLETE

Workflow run: **35755092335 — SUCCESS**

Release:
`research-monster-winner-max-existing-feature-scope-v1`

Archive SHA-256:
`sha256:6c139ff5d2efcdb8dfdfc5d7023c875ff96385f6ccb27eb327fcb66b8336c27a`

Summary SHA-256:
`sha256:df8e763163943464f258f6c99997848d856f9ce9cab1a7148e56b3f06e563703`

Outcome-blind extension events:
- 2021: **4,596**;
- 2022: **5,276**;
- total: **9,872**;
- distinct issuers: **3,395**.

Maturity by the 2022-12-30 data boundary:
- 126 sessions: **7,493**
  - 2021: 4,596
  - 2022: 2,897;
- 252 sessions: **4,582**
  - 2021: 4,582
  - 2022: 0.

The latest 2022 evaluation session with a mature 126-session outcome is
**2022-06-30**.

Therefore:
- full primary M100/252 evidence extends through 2021;
- 2022 is available only as a partial-year 126-session diagnostic.

## Extension continuity — COMPLETE

Workflow run: **35756167797 — SUCCESS**

Release:
`research-monster-winner-max-existing-continuity-v1`

Archive SHA-256:
`sha256:9a28b8d0f1de2d9a8aa602caa28eb6abbf6e84982821f511efe8badde76e3ca6`

Summary SHA-256:
`sha256:bc9e3880651121f6b943ed27c592a9c187d08515f3c5baa2ccece077bf7dff5a`

Mature event-horizon rows:
- 126: 7,493;
- 252: 4,582;
- total: 12,075.

252-session unresolved rows:
- **68 / 4,582 = 1.4841%**.

Frozen extension outcome rule:
- unresolved 252 rows can establish POSITIVE from an exact observed crossing;
- without a crossing they remain UNKNOWN;
- UNKNOWN remains in the density denominator.

This is conservative and prevents unresolved continuity from improving lift.

## Maximum existing-data outcome extension — COMPLETE

Workflow run: **35757195887 — SUCCESS**

Release:
`research-monster-winner-max-existing-outcomes-v1`

Result SHA-256:
`sha256:198bf4f6219bcdf19bfa69bef78f477a54ee0283e16a61cec157f187ca8c1f45`

Archive SHA-256:
`sha256:9eeb44d5c8632493d0b6a2139a13f9905cda13e30d3a8eec1fef9bae9008c3fb`

No 2023+ market data were opened.

## F3_DRAWDOWN_252

### 2021 full M100/252

Feature-observed cohort: **3,459**.

Preferred deepest-drawdown group:
- N: **781**;
- M100 positive: **67**;
- negative: 674;
- unknown: 40;
- observed M100 density: **8.5787%**.

Complement:
- N: **2,678**;
- M100 positive: **129**;
- negative: 2,424;
- unknown: 125;
- observed M100 density: **4.8170%**.

Result:
- M100 lift: **1.7809×**;
- M100 capture: **34.1837%**;
- review share: **22.5788%**;
- review reduction: **77.4212%**.

Tail:
- M200/252 lift: **2.8411×**;
- M500/252 lift: **4.6758×**.

Interpretation:
F3 weakened materially versus 2019-2020, but retained positive M100 enrichment
and became progressively stronger deeper in the right tail.

### 2021 M100/126

- lift: **2.4951×**;
- preferred density: **5.2097%**;
- complement density: **2.0880%**;
- capture: **42.2680%**;
- review share: **22.6867%**.

M200/126 lift: **4.9807×**.

### Available 2022 M100/126 — partial year only

This sample includes evaluation sessions only through **2022-06-30**.

- feature-observed cohort: **2,310**;
- preferred N: **955**;
- complement N: **1,355**;
- preferred M100 density: **6.1780%**;
- complement M100 density: **0.6642%**;
- M100 lift: **9.3013×**;
- M100 capture: **86.7647%**;
- review share: **41.3420%**.

M200/126:
- preferred positives: **15**;
- complement positives: **0**;
- numeric lift is undefined because complement density is zero.

This is strong but must remain labelled a partial-year 2022 diagnostic.

## F4_DISTANCE_BELOW

### 2021 full M100/252

Feature-observed cohort: **4,443**.

Preferred below-insider-basis group:
- N: **839**;
- M100 positive: **50**;
- negative: 749;
- unknown: 40;
- observed M100 density: **5.9595%**.

Complement:
- N: **3,604**;
- M100 positive: **189**;
- negative: 3,201;
- unknown: 214;
- observed M100 density: **5.2442%**.

Result:
- M100 lift: **1.1364×**;
- M100 capture: **20.9205%**;
- review share: **18.8836%**.

Tail:
- M200/252 lift: **0.8844×**;
- M500/252 lift: **0.2603×**.

Interpretation:
F4 retained only weak M100 enrichment in 2021 and failed to enrich the deeper
M200/M500 right tail that year.

### 2021 M100/126

- lift: **1.3715×**;
- preferred density: **3.7960%**;
- complement density: **2.7678%**.

M200/126 lift: **0.8792×**.

### Available 2022 M100/126 — partial year only

Evaluation sessions only through **2022-06-30**.

- preferred M100 density: **5.2805%**;
- complement density: **2.5039%**;
- M100 lift: **2.1089×**;
- M100 capture: **50.0%**;
- review share: **32.1656%**.

M200/126 lift: **1.0545×**.

## Longitudinal primary M100/252 view

These rows use the already-frozen phase-specific cohorts; no new rule is fitted.

| Candidate | Period | M100 lift |
| --- | ---: | ---: |
| F3_DRAWDOWN_252 | 2016-2018 discovery | 4.3331× |
| F3_DRAWDOWN_252 | 2019-2020 confirmation | 3.6357× |
| F3_DRAWDOWN_252 | 2021 max-existing extension | 1.7809× |
| F4_DISTANCE_BELOW | 2016-2018 discovery | 1.7731× |
| F4_DISTANCE_BELOW | 2019-2020 confirmation | 1.4433× |
| F4_DISTANCE_BELOW | 2021 max-existing extension | 1.1364× |

Descriptive pooled count aggregation across 2016-2021:

### F3
- preferred N: **5,086**;
- preferred M100 positives: **1,619**;
- preferred density: **31.8325%**;
- complement N: **13,311**;
- complement positives: **994**;
- complement density: **7.4675%**;
- pooled descriptive lift: **4.2628×**;
- pooled capture: **61.9594%**;
- pooled review share: **27.6458%**.

### F4
- preferred N: **6,106**;
- preferred M100 positives: **1,194**;
- preferred density: **19.5545%**;
- complement N: **21,949**;
- complement positives: **2,580**;
- complement density: **11.7545%**;
- pooled descriptive lift: **1.6636×**;
- pooled capture: **31.6375%**;
- pooled review share: **21.7644%**.

The pooled figures are descriptive arithmetic aggregation of already-frozen
phases, not a new fitted or validated rule.

## Current conclusion boundary

The maximum comparable existing-data extension is complete.

Evidence available:
- primary 252-session: 2016 through 2021;
- secondary 126-session: 2016 through evaluation date 2022-06-30.

The existing corpus cannot produce a complete 252-session 2022 result without
opening 2023 market data.

Current research interpretation:
- **F3_DRAWDOWN_252 remains the materially stronger and more persistent
  monster-enrichment feature**;
- F3's 2021 M100 lift declined versus earlier periods but remained >1, while
  M200/M500 enrichment strengthened relative to its M100 lift;
- F4 weakened substantially in 2021, especially in the deeper right tail;
- partial 2022 126-session evidence is favorable for both, particularly F3, but
  it is not a full-year or 252-session test.

No production change is authorized by this checkpoint.
