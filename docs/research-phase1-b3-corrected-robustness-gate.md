# Phase-1 B3 continuity-corrected robustness gate

Frozen: 2026-09-21 before the continuity-corrected B3 development result was
observed.

## Source

This gate may consume only the immutable result of
`B3_CONTINUITY_CORRECTED_DEVELOPMENT_V1`.

The source must be development-only, 2016-2020 evaluation sessions with
outcomes bounded through 2022-12-31, and must keep validation and 2023+ OOS
sealed.

## Frozen diagnostic semantics

Reapply the existing Phase-1 B3 robustness arithmetic and warning thresholds
**unchanged**. This is the same diagnostic family already frozen and run on the
uncorrected B3 development series.

Primary horizon remains 126 XNYS sessions.

Required diagnostics:

- event-weighted SPY excess;
- issuer equal-weight SPY excess;
- entry-session equal-weight SPY excess;
- year-by-year development means;
- top-1%-removed event-weighted mean;
- existing tail concentration diagnostics.

The warning function and all thresholds must be imported/reused from the
already-frozen B1/B3 robustness implementation. No threshold, weighting,
grouping or year rule may be modified after observing the corrected result.

## Progression

If any frozen blocking warning is true:

`BLOCK_HAC_AND_OOS`.

Only if every frozen blocking warning is false may the result be:

`MAY_FREEZE_SEPARATE_DAILY_PATH_HAC_DESIGN`.

Even a clean corrected robustness result does not itself open HAC, validation
or OOS. HAC requires a separately frozen design.

## Guardrails

- no B3 feature/selection retuning;
- no production scoring changes;
- no validation performance;
- no 2023+ data;
- no interpretation as formal alpha;
- the uncorrected robustness result remains historical audit evidence and is
  not deleted or rewritten.
