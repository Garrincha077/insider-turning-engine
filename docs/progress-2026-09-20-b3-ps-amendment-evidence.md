# B3 P/S supporting-evidence hydration

Date: 2026-09-20

Status: **COMPLETE / PASS**

Authoritative frozen scope:
- workflow run: `35471756336`;
- artifact: `phase1-b3-ps-amendment-scope-35471756336`;
- digest: `sha256:8ed756ea1ddb2dfd2dcdf8ec478b82a2a8c4d4715c6d5223f1772e18b81fbb8d`.

Targets are fixed before hydration:
- 1,551 unique supporting predecessor filings;
- 596 zero-transaction amendments on P/S roots.

Hydration uses only verified issuer/reporting-owner CIK accession archive paths
from frozen SEC evidence. It retains exact SEC acceptance timestamps, raw XML
hashes, and the normalized primary ownership XML for zero-transaction
amendments. Supporting-predecessor canonical rows are marked
`supportingPredecessorOnly=true`.

This stage does not classify zero-transaction amendment economics, reconcile
lifecycles, define B3, compute returns, open 2023+, or change production
scoring.

## Result

Workflow run: 35472366209.

- supporting predecessor targets: **1,551**;
- supporting predecessors hydrated: **1,551**;
- zero-transaction amendment targets on P/S roots: **596**;
- zero-transaction amendments hydrated: **596**;
- failures: **0**;
- PIT acceptance-time contract preserved;
- 2023+ remained sealed;
- production scoring remained unchanged.

The next gate was zero-transaction semantic classification plus deterministic
P/S lifecycle reconciliation. That later gate passed in run 35499189795.
