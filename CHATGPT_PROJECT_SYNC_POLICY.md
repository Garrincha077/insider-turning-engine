# ChatGPT Project ↔ GitHub synchronization policy

## Purpose

Files uploaded to a ChatGPT Project are snapshots. GitHub continues to evolve after those files are uploaded. This policy defines which source is authoritative when the two differ.

## Authority hierarchy

### 1. Current implementation and execution state

**Live GitHub wins** for:

- current branch contents;
- current commit SHA;
- workflow/job status;
- workflow logs;
- release contents;
- artifact existence/digests;
- current code and tests;
- current operational state.

Primary branch: `research/b3-ps-pit-history`.

### 2. Current research status

The **live GitHub copy of `docs/HANDOFF.md`** is the operational source of truth for what has passed, what is active and what comes next.

The compact current-status file is secondary to HANDOFF.

### 3. Frozen methodology

A frozen/predeclared specification or gate remains authoritative for the methodology it froze.

Examples include:

- `docs/research-predeclared-spec.md`;
- `docs/P0_PHASE1_IMPLEMENTATION.md`;
- `docs/research-phase1-*-gate.md`;
- persisted frozen definition artifacts/releases.

A newer code file, Project summary or HANDOFF note must not silently redefine a frozen methodology after results are known.

If methodology genuinely changes after freeze, create a new explicitly versioned definition/gate. Preserve the older frozen version as audit evidence.

### 4. Historical progress/results

Dated `progress-*.md` and result files are historical audit trail.

Do not rewrite old results merely because the current state moved on.

### 5. ChatGPT Project copies

Project-uploaded files are working context only.

They never override:

- a newer verified live GitHub operational state; or
- an older frozen methodological contract that is still the governing definition.

## Required startup procedure

Before continuing development or research from a ChatGPT Project:

1. inspect the live branch `research/b3-ps-pit-history`;
2. read the live `docs/HANDOFF.md`;
3. inspect relevant workflow runs and releases;
4. compare the live commit/state with the Project snapshot;
5. resolve any material mismatch before taking action.

## Mismatch procedure

If Project and GitHub differ:

1. classify the mismatch as **operational/current-state** or **methodological/frozen**;
2. for operational state, use verified live GitHub;
3. for frozen methodology, use the governing predeclared/frozen artifact;
4. update HANDOFF/current-status when they are stale;
5. leave historical dated results unchanged;
6. continue only after the authority conflict is resolved.

## Examples

**Project says B3 recovery is in progress; GitHub says it completed successfully.**  
Use GitHub. Update HANDOFF/current-status, then continue from the completed result.

**Current code uses a 45-day B3 window but the frozen B3 v1 definition says 30 days and the change happened after performance was viewed.**  
Do not silently accept 45 days as B3 v1. The 30-day frozen definition remains authoritative. A 45-day rule requires a separately versioned new research definition.

**Old progress file says P/S history is 7/40, live HANDOFF says 40/40 and releases confirm 40/40.**  
Keep the old progress file as historical evidence; use the live verified 40/40 state operationally.

## Snapshot metadata

Every exported ChatGPT Project bundle should include a manifest with repository, branch, source commit and hashes. The manifest identifies what the Project snapshot contained; it does not make that snapshot permanently authoritative.
