# B1/B4 development run results — 2026-09-17

## Run status

GitHub Actions run `35263058619` completed successfully on 2026-09-17.

The full `Run B1 and B4 development cohorts` job completed with all gates green:

- bounded research evidence downloaded
- bounded CMP classifier history view built
- bounded CMP history semantics asserted
- authoritative P0 exact-calendar tier recomputed
- exploratory-or-better P0 gate passed
- canonical B1 development cohort completed
- B1 research-boundary assertions passed
- predeclared B4 intersection development cohort completed
- B4 research-boundary assertions passed
- workflow artifact uploaded
- B1/B4 research evidence persisted

## Research boundaries

The research protocol remains unchanged:

- development cohort: 2016–2020
- outcome window: through 2022
- 2023+ remains sealed OOS
- production scoring is unchanged
- B3 remains blocked until a complete PIT sale-history contract exists
- B4 remains the exact same-issuer + same-XNYS-session intersection of B1 and B2 before issuer-level 20-session deduplication

## CMP history handling

Frozen CMP history for 2013–2019 remains immutable in `research-cmp-history-v1`.

The B1/B4 workflow uses a derived bounded analysis view only. It rejects any 2023+ filing date, excludes transaction years outside the predeclared 2013–2019 classifier-history window, and excludes transaction months that are impossible relative to the filing month. This does not alter the frozen source data or the signal definition.

## Current interpretation

This successful run is an infrastructure and evidence milestone, not a production-readiness decision. The next step is to extract and compare the persisted B0/B1/B2/B4 empirical results, with the 126-session horizon treated as primary, and then proceed to dependence-aware/calendar-time robustness work before any formal claim of alpha.

## Next gate

Extract the run artifact and persisted release evidence and record:

- retained selections / exact-entry matches / issuer counts
- 21, 63, 126 and 252 session raw returns
- SPY excess mean and median
- SPY-excess win rate
- MAE mean and median
- B1 and B4 deltas versus B0, and B4 versus B1/B2 where available

Do not relax the B4 intersection definition or open 2023+ OOS in response to sample size or empirical performance.
