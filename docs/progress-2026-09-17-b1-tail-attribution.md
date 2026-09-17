# Progress checkpoint — B1 tail/year attribution

Date: 2026-09-17

## Why this checkpoint exists

The frozen B1 dependence/tail robustness gate raised blocking warnings before any 2023+ OOS was opened. Canonical B1 has 5,944 mature 126-session observations and a +9.7882% arithmetic mean SPY-excess return, but the top-1%-removed mean is negative and only two of five development years have positive mean excess.

This checkpoint records the next explanatory step without changing the signal definition.

## Frozen next gate

`docs/research-phase1-b1-tail-attribution-gate.md` was written before inspecting the identities of the largest B1 winners. It freezes:

- canonical B1 only;
- `excess_126` as the primary field;
- the 59 largest mature observations (`floor(5944 * 0.01)`);
- deterministic tie-breaking by excess return, evaluation session, issuer CIK and ticker;
- explicit 2020 attribution;
- within-year tail sensitivity for 2016–2020;
- deterministic data-sanity checks;
- a hard failure on any 2023+ date.

No ticker, issuer, year, industry, market-cap group or return threshold found in this audit may become an ex-post exclusion/filter.

## Implementation state

Added on branch `research/b1-tail-attribution`:

- `scripts/research_phase1_b1_tail_attribution.py`;
- `tests/test_research_phase1_b1_tail_attribution.py`;
- `.github/workflows/research-phase1-b1-tail-attribution.yml`.

The workflow reads only persisted `b1-events.csv` and `b1-summary.json` from `research-phase1-baselines-v1`, reproduces the canonical 126-session summary before attribution, asserts the research/OOS boundaries and uploads a deterministic JSON artifact.

## Boundaries

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- 2023+ OOS remains sealed.

## Next action

Run CI, merge only if green, execute the frozen tail-attribution workflow on `main`, inspect the resulting 59-event attribution and record the empirical result without changing B1 post hoc.
