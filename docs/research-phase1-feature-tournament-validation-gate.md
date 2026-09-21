# Phase-1 insider feature tournament validation gate

Frozen: 2026-09-21 after immutable 2019-2020 confirmation and before any
2021-2022 validation-event outcome is read.

## Confirmed candidate entering validation

Source:
- release: `research-phase1-insider-feature-tournament-confirmation-v1`
- asset: `confirmation-results.json`
- SHA-256:
  `sha256:5776b17b452c23aaccf481b1484460c9ab8d860187eb554bef31f6a0387d234f`

Exactly one candidate may enter validation:

- family: **F2**
- variant: **F2_DIRECT_VS_INDIRECT**
- coverage: GENERAL_ELIGIBLE
- preferred: **INDIRECT_ONLY**
- complement: **DIRECT_ONLY**

F1 and F4 failed frozen confirmation. F3 never left discovery. None may be
reintroduced in validation.

## Validation event scope

Validation evaluation sessions are 2021-01-01 through 2022-12-31.

The original B0 issuer-event construction and 20-XNYS-session issuer
deduplication are reproduced across the complete 2016-2022 pre-2023 stream
before the validation slice is taken. This prevents the first 2021 event from
ignoring a late-2020 event inside the frozen dedup window.

Only the primary **126-session** horizon is used for the formal validation
decision.

2023+ remains sealed. Therefore an event is eligible for validation performance
only when its frozen 126-session target exit is no later than 2022-12-31.
Later-maturing events are right-censored before outcome read and cannot be
recovered with 2023 prices in this phase.

Exact entry requires the same regular-session rule as the earlier B0 feature
scope.

## F2 formation rule

The validation feature is rebuilt point-in-time from the frozen SEC amendment
history using the same Stage-A lifecycle and knowledge rules.

For qualified purchase rows assigned to the evaluation session:
- only D -> DIRECT_ONLY;
- only I -> INDIRECT_ONLY;
- both -> MIXED;
- neither valid D/I value -> UNKNOWN.

The validation contrast contains only DIRECT_ONLY and INDIRECT_ONLY.
MIXED/UNKNOWN are descriptive missingness strata and do not enter either side.

No feature threshold or orientation is estimated from validation.

## Frozen outcome clock

Entry:
- next XNYS regular session open after evaluation.

Exit:
- exact 126th XNYS session after entry;
- target must be <= 2022-12-31.

SPY excess:
- stock holder return minus SPY return using the same entry-open /
  target-close clock.

Before any validation outcome can be read, the exact frozen validation scope
must pass a performance-blind security-continuity program with zero unresolved
rows. The continuity decision may not use validation returns.

## Frozen validation PASS rule

The F2 candidate receives `VALIDATED_CANDIDATE` only if all of the following
are true on the frozen eligible validation scope:

1. preferred mature N >= **150**;
2. preferred distinct issuers >= **75**;
3. pooled event-weighted 126d SPY-excess incremental mean > 0;
4. pooled issuer-equal-weight incremental mean > 0;
5. pooled entry-session-equal-weight incremental mean > 0;
6. pooled top-1%-removed incremental mean > 0;
7. 2021 event-weighted incremental mean > 0;
8. 2022 event-weighted incremental mean > 0.

Top-1% removal uses the exact discovery rule: pool both groups, sort by 126d
SPY-excess descending with stable event-key tie-breaking, remove exactly
`ceil(1% * mature N)`, and recompute the event-weighted increment.

There is no validation reselection, alternate orientation, alternate cutoff,
replacement feature or composite fitting.

## ADV / market-cap boundary

The Stage-A raw formation-context input was frozen only through 2020. No new
2021-2022 raw provider is introduced after seeing confirmation.

Therefore:
- the confirmation ADV gate remains historical development evidence;
- validation does **not** add or substitute a 2021-2022 dollar-ADV PASS rule;
- PIT market cap remains unavailable;
- adjusted outcome prices may not be repurposed as a nominal raw-ADV or
  market-cap substitute.

This rule is frozen before validation outcomes.

## Interpretation

A validation pass is chronological holdout evidence for the already-frozen F2
candidate. It is not a formal alpha proof and does not authorize production.

A validation failure is final for this tournament version. No feature
replacement is allowed.

Regardless of PASS/FAIL:
- 2023+ OOS remains sealed;
- no production score changes are authorized;
- no generic Turning/technical overlay is opened by this gate.
