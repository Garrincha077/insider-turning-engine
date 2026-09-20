# ChatGPT Project Instructions — Insider Turning Engine

## Project identity

Repository: Garrincha077/insider-turning-engine  
Primary research branch: research/b3-ps-pit-history  
Current documentation authority: docs/HANDOFF.md  
Compact checkpoint: docs/progress-2026-09-20-phase1-current-status.md

This ChatGPT Project is the working research environment for the Insider Turning Engine. The goal is to build an empirically defensible, point-in-time insider-trading research engine that distinguishes informative insider behavior from noise and later tests whether price/volume turning confirmation adds incremental value.

## Read-first order

At the start of a new chat or after losing context, read in this order:

1. docs/HANDOFF.md
2. docs/progress-2026-09-20-phase1-current-status.md
3. docs/research-log.md
4. docs/research-predeclared-spec.md
5. docs/P0_PHASE1_IMPLEMENTATION.md
6. docs/research-phase1-b3-ps-pit-history-gate.md
7. docs/research-phase1-b3-ps-amendment-gate.md
8. research/b3-company-net-buying-v1.json
9. the most recent dated progress file relevant to the active task

Treat docs/HANDOFF.md as the operational source of truth for current state. Treat older dated progress/result files as historical audit evidence, not current instructions, unless HANDOFF explicitly points to them.

## Repository / Project synchronization

The ChatGPT Project files are a context snapshot, not an authoritative live mirror of GitHub.

At the beginning of any development or research-continuation task:

1. Check the live GitHub branch `research/b3-ps-pit-history`.
2. Read the live `docs/HANDOFF.md`.
3. Check the relevant workflow runs, releases, artifacts and current commit SHA.
4. Compare those facts with the Project files before acting.

Conflict resolution:

- Live GitHub wins for current code, workflow status, run results, release contents and current operational state.
- Live `docs/HANDOFF.md` wins for current research progress/status.
- Frozen/predeclared research specifications and gate definitions remain authoritative for methodology even if newer code, summaries or Project files conflict with them.
- Historical dated progress/result files remain audit evidence and must not be rewritten merely to match the latest state.
- Project-uploaded copies never override a newer verified GitHub state.
- A newer GitHub file does not automatically override a frozen methodology. A methodological change after freeze must be explicitly versioned as a new research definition/gate rather than silently replacing the frozen one.

If a material mismatch is discovered:

1. identify which authority applies using the rules above;
2. reconcile the difference before continuing;
3. update live `docs/HANDOFF.md` and the current-status checkpoint when appropriate;
4. preserve the older dated/frozen artifact as audit history;
5. only then continue the research sequence.

Never use a stale Project copy as justification to rerun, skip, change or reinterpret a research gate.

## Hard research boundaries

- Warm-up/history context: 2013-2015.
- Development cohort: 2016-2020.
- Validation: 2021-2022.
- Sealed OOS: 2023+.
- Do not read, search, hydrate, inspect, summarize, or use 2023+ project filings, market outcomes, or performance unless the owner explicitly authorizes opening OOS.
- Outcome data for development/validation work may not extend past 2022-12-31.
- Production scoring, production weights, production thresholds, production alert logic and production state-machine behavior must not be changed unless the owner explicitly asks.
- Do not present exploratory development results as validated alpha or production evidence.
- Do not lower a data-quality, coverage, reconciliation, or statistical gate because a performance result is attractive.
- Missing or ambiguous data remain explicit attrition/quarantine. Never silently impute, fuzzily match, or substitute future/current identity.

## PIT contract

For historical SEC evidence:

- SEC accepted_at is the historical public-information clock.
- knowledgeAt must equal acceptedAt for SEC-derived historical evidence.
- actual later retrieval time remains separate.
- amendments change historical state only from their own acceptance time onward.
- no later amendment may retroactively repair an earlier information state.
- issuer CIK is identity; ticker is a valid-time attribute.
- no current/future ticker or company mapping may be used as historical truth.

For market execution:

- use XNYS/SPY as the exact session calendar;
- evaluation from public knowledge time;
- entry on the exact next eligible XNYS session open;
- no nearest/later stock-bar substitution;
- missing/delisted outcomes remain explicit.

## Current Phase-1 benchmark family

B0 — any qualified open-market insider purchase. Development descriptive run complete.

B1 — canonical Cohen-Malloy-Pomorski-style opportunistic insider purchase. Development run complete, followed by continuity correction, corrected performance, robustness, tail/year attribution and temporal-clustering diagnostics. Do not treat the large arithmetic mean as sufficient alpha evidence.

B2 — independent-owner cluster. Primary definition: at least 2 distinct reporting-owner CIKs in 30 calendar days; 3+ owners is a secondary subgroup. Development run complete.

B3 — company net buying. Complete P/S history and broader amendment reconciliation are now available. Data gate passed and B3 v1 definition is frozen before development performance. Current work is finishing the performance-blind raw signal/event construction.

B4 — exact same-issuer + same-XNYS-session intersection of B1 and B2 before common issuer-level dedup. Development run complete. Do not retune it after its weaker descriptive result.

Do not invent B5/B6 labels casually. New benchmark labels should correspond to separately predeclared features or benchmark definitions.

## Current B3 state

Original P/S PIT history:
- 2013-2022 original Form 4/5 P/S universe;
- 570,291 filings;
- 40/40 quarters PASS;
- 2023+ sealed.

B3 amendment evidence:
- scope run 35471756336 PASS;
- 1,551 unique supporting predecessors required;
- 596 zero-transaction amendments on P/S roots;
- hydration run 35472366209 PASS;
- 1,551/1,551 supporting predecessors hydrated;
- 596/596 zero-transaction amendments hydrated;
- 0 hydration failures.

B3 lifecycle reconciliation:
- run 35499189795;
- 8/8 issuer-safe shards PASS;
- deterministic merge PASS;
- status B3_PS_AMENDMENT_RECONCILIATION_PASS;
- linked amendment rows: 31,048;
- reconciled revision rows: 2,320,279;
- effective qualified P/S rows at end-2022: 1,570,066;
- 2023+ sealed;
- production scoring unchanged.

B3 definition:
- persistent release research-phase1-b3-definition-v1;
- frozen before development performance;
- primary window 30 calendar days;
- qualified non-derivative priced P/A buys and S/D sales;
- buy/sale dollars = shares × price;
- net dollars = buy dollars - sale dollars;
- gross dollars = buy dollars + sale dollars;
- net-buying intensity = net/gross;
- raw positive-net candidate requires buy dollars > 0 and net dollars > 0;
- no role, direct/indirect, or 10b5-1 score weighting;
- downstream issuer dedup = 20 XNYS sessions;
- development = 2016-2020;
- outcomes may not exceed 2022-12-31.

Latest known B3 raw-signal recovery run when this file was created:
- workflow: Recover Phase-1 B3 raw signal inputs;
- run: 35500436177;
- state at packaging time: in progress, building performance-blind raw candidates.

Always live-check GitHub before relying on that last run state.

## Immediate execution sequence

When continuing development:

1. Check the latest GitHub workflow status first.
2. If the B3 raw signal recovery passed, retrieve and verify its summary and persisted release.
3. Map raw B3 candidates to the exact XNYS evaluation/entry clock.
4. Apply the already frozen 20-session issuer-level dedup.
5. Freeze/assert the final B3 event construction artifact before looking at outcomes.
6. Only then run B3 development performance on 2016-2020 with outcomes bounded through 2022.
7. Run dependence-aware B3 robustness: calendar-time/HAC, issuer clustering, tail sensitivity, year stability and concentration of returns.
8. Compare B0/B1/B2/B3/B4 without post-hoc threshold changes.
9. Then move to the insider-information feature tournament.
10. Only after the insider component is defensible should turning/technical overlays be tested incrementally.
11. Freeze the complete methodology before opening 2021-2022 validation.
12. Keep 2023+ sealed until validation/methodology freeze and explicit owner authorization.

## Feature-tournament direction after B3

Candidate families include:
- purchase-size normalization;
- first-buy/re-entry definitions;
- same-owner sequence behavior;
- role/hierarchy as a tested feature rather than assumed prior;
- direct vs indirect ownership as stratification first;
- ownership-change ratios;
- sales/absence-of-sales;
- drawdown/contrarian context;
- observed Rule 10b5-1 status;
- cluster intensity and recency.

Test features individually and incrementally. Use bucket/monotonicity checks, ablations, stability by era/size/liquidity and dependence-aware inference. Do not build one opaque optimized score first.

## Turning overlay direction

Only after the insider-information component survives validation work, test:
- base formation/no-new-low;
- volatility contraction;
- volume dry-up/accumulation;
- ordinary RS turn;
- Mansfield RS vs market;
- Mansfield RS vs sector;
- MA20/MA50 slope/reclaim;
- insider purchase-VWAP/cost-basis state;
- state persistence/hysteresis.

Always compare INSIDER ONLY versus INSIDER + ONE TECHNICAL FEATURE before testing the full turning engine.

## Statistical discipline

Do not rely only on IID event bootstrap.

Use, where applicable:
- calendar-time active-signal portfolios;
- HAC/Newey-West;
- issuer-clustered uncertainty;
- temporal clustering checks;
- tail sensitivity;
- concentration in largest winners;
- year stability;
- exact-session execution sensitivity;
- explicit attrition.

Mean, median and win rate must all be shown where relevant. A positive arithmetic mean with negative median and sub-50% win rate is not automatically broad alpha.

## Working style in this Project

- Prefer action over repeated clarification when the existing HANDOFF/spec already answers the question.
- For GitHub tasks, inspect the repo and current workflow state before proposing manual steps.
- Keep research work on a dedicated research branch unless explicitly told otherwise.
- Use deterministic gates and resumable workflows for large SEC/GitHub jobs.
- When a long job can safely run unattended, queue independent performance-blind work, but never cross a frozen methodological or OOS boundary automatically.
- Keep the owner updated with concise progress messages during multi-step work.
- Do not promise background work outside actual scheduled/GitHub jobs.
- Preserve auditability: record run IDs, artifact/release names, digests when material, commit SHAs and gate decisions.
- When a run fails, diagnose the actual failure and fix the cause; do not weaken research gates.

## Documentation policy

- docs/HANDOFF.md = current operational truth.
- docs/progress-YYYY-MM-DD-*.md = dated checkpoint/audit trail.
- docs/research-phase1-*-gate.md = predeclared/frozen gate plus execution result.
- docs/research-log.md = persistent research notebook.
- docs/research-predeclared-spec.md and P0_PHASE1_IMPLEMENTATION.md = frozen research specs; do not rewrite their historical definitions to fit later outcomes.
- Update current-status/HANDOFF when a major gate passes, but do not rewrite old result files.

## Production/OOS authorization boundary

Without explicit owner instruction, do not:
- open 2023+ OOS;
- tune on 2023+;
- change production config/scoring weights;
- enable production signals based on research;
- replace production methodology from exploratory results.

Research-only acquisition, hydration, auditing, deterministic reconciliation, development/validation preparation, robustness diagnostics and documentation are authorized while respecting the boundaries above.
