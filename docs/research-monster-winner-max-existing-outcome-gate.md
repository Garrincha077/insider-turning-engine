# Monster Winner v1 — maximum existing-data outcome gate

Frozen: 2026-09-22 after the 2021-2022 feature/maturity scope and
performance-blind 126/252 continuity audit, and before any new 2021-2022
Monster Winner price outcome is read.

## Purpose

Complete the user's requested extension to the broadest comparable period
already supported by the frozen research data, without opening 2023+ and
without letting unresolved 252-session continuity improve F3/F4 results.

## Immutable scope

Feature scope release:
`research-monster-winner-max-existing-feature-scope-v1`

Archive SHA-256:
`sha256:6c139ff5d2efcdb8dfdfc5d7023c875ff96385f6ccb27eb327fcb66b8336c27a`

Summary SHA-256:
`sha256:df8e763163943464f258f6c99997848d856f9ce9cab1a7148e56b3f06e563703`

Frozen extension events:
- 2021: **4,596**;
- 2022: **5,276**;
- total: **9,872**.

Maturity at the 2022-12-30 market boundary:
- 126-session: **7,493** events
  - 2021: 4,596
  - 2022: 2,897;
- 252-session: **4,582** events
  - 2021: 4,582
  - 2022: 0.

Thus the full primary `M100_252_CLOSE` comparable extension ends in 2021.
The available 2022 extension is secondary 126-session evidence only.

## Immutable continuity audit

Release:
`research-monster-winner-max-existing-continuity-v1`

Archive SHA-256:
`sha256:9a28b8d0f1de2d9a8aa602caa28eb6abbf6e84982821f511efe8badde76e3ca6`

Summary SHA-256:
`sha256:bc9e3880651121f6b943ed27c592a9c187d08515f3c5baa2ccece077bf7dff5a`

Rows:
- 126: 7,493;
- 252: 4,582;
- total: 12,075.

252-session unresolved rows:
**68 / 4,582 = 1.4841%**.

The audit is performance-blind.

## Frozen candidates

Only:
- `F3_DRAWDOWN_252`;
- `F4_DISTANCE_BELOW`.

Use their already-frozen Stage-A 2016-2018 cutpoints and directions unchanged.

## 126-session holder paths

For the 7,493 mature 126-session rows, use the already-complete immutable
validation continuity contract:

Release:
`research-phase1-insider-feature-tournament-validation-final-continuity-v1`.

Asset:
`validation-final-continuity.json`.

SHA-256:
`sha256:16a9814003c232d58d9e0f70a85b72beb7e37d04c81b390dbd3cfd6199c7956a`.

It contains zero unresolved continuity for the exact mature 126-session
2021-2022 scope.

Match rows by semantic identity:
issuer CIK, historical ticker, evaluation session, entry session, horizon and
target exit session. Event number is not a matching key.

## 252-session holder paths

For rows classified by the extension audit as deterministic:

- ordinary adjusted continuity follows the original adjusted ticker;
- deterministic same-security symbol change switches on the provider effective
  date;
- deterministic cash/stock/stock-and-cash merger uses the frozen provider
  economic terms;
- deterministic cash consideration remains cash after the effective date.

For the **68 unresolved 252-session rows**, v1 applies a conservative
one-sided rule rather than post-outcome adjudication:

### Provider ambiguity / incomplete terms

- before the earliest frozen candidate corporate-action date, exact observed
  closes of the historical security may establish a positive crossing;
- on and after that date, holder value is unavailable unless the row is already
  deterministic under the frozen audit;
- no-crossing state = `UNKNOWN`.

### Long internal market gap

- use exact observed closes of the unchanged historical ticker where present;
- missing sessions are not imputed;
- an observed crossing may establish `POSITIVE`;
- because the frozen continuity audit classified the path unresolved,
  no-crossing state = `UNKNOWN`.

Therefore an unresolved 252 row can never become NEGATIVE.

## Denominator rule

For every mature feature-observed group:

`observed_positive_density = POSITIVE / all mature group events`.

This denominator includes:
- NEGATIVE;
- UNKNOWN;
- conservatively unresolved 252 paths.

Therefore unresolved continuity cannot improve a feature's lift by disappearing.

## Outcome fields authorized

Only:
- exact entry-session open;
- exact regular-session close along the relevant holder path.

No intraday high, nearest/later-bar substitution or 2023+ price is authorized.

## Labels

252:
- M50: >=1.50x entry open;
- M100: >=2.00x;
- M200: >=3.00x;
- M500: >=6.00x.

126:
- M100: >=2.00x;
- M200: >=3.00x.

For a deterministic path, no crossing is NEGATIVE only when the already-frozen
Monster path completeness rule is met:
- coverage >=95%;
- max consecutive missing sessions <=5;
- complete mandatory holder consideration.

Otherwise no crossing = UNKNOWN.

## Required reporting

For each candidate and horizon:
- mature feature-observed cohort N;
- preferred/complement N;
- POSITIVE / NEGATIVE / UNKNOWN;
- observed-positive density;
- evaluable hit rate;
- lift;
- capture;
- review share;
- unknown share.

Also report:
- 2021 full M100/252 and tail results;
- 2021 M100/126;
- available mature 2022 M100/126, explicitly marked partial-year/right-censored;
- combined longitudinal table:
  - 2016-2018 discovery;
  - 2019-2020 confirmation;
  - 2021 max-existing primary extension;
  - 2022 available 126-session extension.

No pass/fail threshold is retroactively added for this known-sample extension.

## Boundary

- 2023+ remains unopened;
- 2013-2015 remain unscored because comparable market history is unavailable;
- no retuning;
- no F3+F4 composite;
- no production scoring change.
