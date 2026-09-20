# Phase-1 B3 frozen residual-91 continuity scope gate

Frozen: 2026-09-20, after the strict multi-source continuity synthesis and
before any additional primary-source resolution work.

## Purpose

Freeze the exact residual continuity universe that remains after all currently
accepted performance-blind deterministic candidates. This prevents silent
scope expansion/contraction while the remaining cases are investigated.

## Authoritative source

- release: `research-phase1-b3-residual-multisource-v1`
- asset: `b3-residual-multisource-synthesis.json`
- asset SHA-256:
  `sha256:b88512259b21b31b1defa63328cba4f2e56ba32f6fbf071452ff32251777f56a`
- source status: `B3_RESIDUAL_MULTISOURCE_SYNTHESIS_COMPLETE`
- source unresolved universe: 264 rows
- accepted deterministic candidates: 173 rows
- residual rows: **91**
- frozen residual-key SHA-256:
  `sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58`

## Frozen boundaries

- development cohort: 2016-2020
- outcomes/evidence: no later than 2022-12-31
- 2023+ OOS remains sealed
- horizons: 21/63/126/252 XNYS sessions
- primary horizon: 126
- performance remains unread for this resolution stage
- production scoring remains unchanged

## Required scope output

The scope artifact must preserve, for every one of the 91 rows:

- event key: event number, issuer CIK, ticker, evaluation session, entry
  session, horizon, target exit session;
- original continuity source and residual reason;
- frozen pivot date/kind;
- P/S PIT corroboration status;
- SEC security-title status;
- all-Form345 corroboration status;
- provider candidate action types/IDs, when present;
- max internal gap sessions;
- the exact evidence bucket used for triage.

It must also persist:

- exact 91-row residual key digest;
- issuer/ticker target list;
- counts by evidence bucket;
- counts by resolution source and residual reason;
- `performanceRead=false`;
- `priceFieldsRead=[]`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `finalResolutionContractCreated=false`;
- `correctedPerformanceOpened=false`.

## Scope immutability

Any later resolution artifact must prove that each resolved row is a member of
this exact scope. No new row may be introduced and no residual row may be
silently dropped.

A row can leave the residual set only through a separately frozen,
performance-blind resolution rule backed by deterministic primary evidence.
Rows may remain unresolved; fail-closed is preferred to unsupported continuity.

## Next evidence priority

1. the 4 provider-ambiguity rows;
2. ticker-change / security-title-change cases;
3. one-sided identity evidence;
4. same-ticker rows with title overlap/change;
5. any remaining contradictory evidence.

Corrected B3 performance remains blocked until a later final continuity gate
has zero unresolved rows.
