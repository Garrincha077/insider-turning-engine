# Phase-1 B3 pre-outcome event-construction gate

Status: **PREDECLARED BEFORE B3 DEVELOPMENT OUTCOMES**  
Date: **2026-09-20**  
Scope: map frozen B3 raw positive state-boundary candidates to exact XNYS
evaluation/entry sessions and apply the already frozen 20-session issuer dedup.  
Market returns: **prohibited in this gate**.  
OOS: **2023+ remains sealed**.  
Production scoring: unchanged.

## Inputs

The source is the completed performance-blind raw B3 release:

- release: `research-phase1-b3-signal-input-v1`;
- asset: `b3-raw-signal-inputs-2016-2020.tar.gz`;
- asset SHA-256:
  `c39c704bd59e861397be42f8b9a40fa5a6674d68e1cf088372f2f2fdf983ec87`;
- raw candidates: **147,164**;
- source definition: `B3_COMPANY_NET_BUYING_V1`;
- returns read: false.

The exact event-construction definition is frozen in
`research/b3-event-construction-v1.json`.

## Evaluation clock

Use the same XNYS mapping function already used by the authoritative Phase-1
market audit.

For each public `knowledgeBoundaryAt`:

1. if the timestamp is on an XNYS session and is at or before that eligible
   session close, `evaluationSession` is that session;
2. if it is after that close, use the next XNYS session;
3. if it is on a non-session date, use the next XNYS session;
4. `entrySession` is the **exact next XNYS session** after
   `evaluationSession`.

No stock price, market return, nearest-bar fallback, or future market outcome is
required or permitted here.

## Development cohort boundary

Development membership is based on **evaluation session**, matching B0:

`2016-01-01 <= evaluationSession <= 2020-12-31`.

A raw candidate with a 2020 public-knowledge timestamp that maps to a 2021
evaluation session is excluded from the development cohort rather than pulled
back into 2020.

## Frozen issuer dedup

Candidate ordering:

1. evaluation-session index ascending;
2. public knowledge timestamp ascending;
3. issuer CIK ascending;
4. signal ID ascending.

Dedup key: issuer CIK.

Retain the first ordered candidate. For each later candidate of the same issuer:

- suppress when its evaluation index is **<=20 XNYS sessions** after the last
  retained event;
- a suppressed candidate does **not** move the retained anchor;
- retain when the gap is **>=21 sessions**.

This is the same 20-session exposure-spacing convention used by the existing
Phase-1 baseline plumbing.

## Same-session positive boundaries

The B3 v1 source definition emits **positive state-changing boundaries**. This
gate treats those frozen raw boundaries as event candidates; it does not
retroactively reconstruct a different intraday state rule after observing
returns.

If multiple positive boundaries for one issuer map to the same evaluation
session, deterministic knowledge-time ordering plus issuer dedup retains the
first candidate and suppresses later candidates in that exposure window.

Any alternate same-session/state-persistence formulation must be a separately
versioned research definition and may not silently replace B3 v1.

## Required outputs

- retained pre-outcome event JSONL;
- explicitly dedup-suppressed JSONL;
- raw source count;
- development-boundary exclusions;
- retained count;
- suppressed count;
- distinct retained issuers;
- annual retained/suppressed counts;
- exact evaluation and entry sessions.

Required flags:

- `marketDataJoined=false`;
- `returnsRead=false`;
- `developmentPerformanceComputed=false`;
- `validationPerformanceComputed=false`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

## Progression

Only after this gate passes and its artifact is persisted may B3 events be
joined to bounded PIT historical identity/market data for the first development
outcome run.

Development outcomes remain restricted to evidence through **2022-12-31**.
2023+ remains sealed.
