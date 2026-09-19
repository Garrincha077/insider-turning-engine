# B3 P/S amendment scope execution

Date: 2026-09-19

Status: **READY TO EXECUTE**

The original P/S PIT history prerequisite has now passed **40/40 quarters** and
the persistent release `research-sec-ps-pit-v1` contains the full-history
index.

This step remains performance-blind. It builds only the predeclared amendment
scope inventory described in `docs/research-phase1-b3-ps-amendment-gate.md`.

Frozen inputs:

- original P/S source evidence: workflow run `35469045909`;
- persistent original P/S release: `research-sec-ps-pit-v1`;
- transaction-bearing amendment/predecessor source evidence: workflow run
  `35081263705`;
- persistent amendment acquisition release: `research-sec-amendments-v1`;
- period: 2013-2022 only;
- 2023+ OOS remains sealed.

The exact artifact names and GitHub artifact digests are frozen in
`research/b3-ps-amendment-scope-inputs-v1.json`.

The scope inventory must not set `amendmentsReconciledForPsUniverse=true`.
Its purpose is to enumerate original-P/S-root amendments, qualified P/S
amendments requiring supporting predecessors, zero-transaction amendments on
P/S roots, and deterministic quarantines. Supporting-predecessor hydration and
zero-transaction semantic resolution remain later gates.
