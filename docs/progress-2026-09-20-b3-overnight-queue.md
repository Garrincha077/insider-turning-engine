# B3 overnight queue: reconciliation -> freeze -> signal inputs

Date: 2026-09-20

The queue is deliberately performance-blind until the B3 definition is frozen.

Sequence:
1. Verify frozen P/S, amendment, scope and supporting-evidence gates.
2. Reconcile eight issuer-safe lifecycle shards.
3. Merge deterministically and require the P/S amendment gate to pass.
4. Freeze the already-committed B3 company-net-buying v1 definition.
5. Build 2016-2020 raw B3 signal candidates without reading market outcomes.

The queue stops automatically on any failed gate. It does not read 2023+,
does not compute development returns, and does not modify production scoring.

The primary B3 definition is fixed before performance:
- 30 calendar-day company window;
- dollar-weighted qualified buys and sales;
- net dollars = buys - sales;
- intensity = net / gross;
- raw positive-net signal when buy dollars > 0 and net dollars > 0;
- no role, D/I, or 10b5-1 score weights;
- company economic rows deduplicated across reporting-owner aliases;
- downstream 20-XNYS-session issuer dedup remains required.

## Execution status

- supporting-evidence prerequisite: PASS;
- eight lifecycle reconciliation shards: **8 / 8 PASS**;
- deterministic merge: **PASS**;
- reconciliation status: B3_PS_AMENDMENT_RECONCILIATION_PASS;
- B3 company-net-buying v1 definition: **FROZEN BEFORE PERFORMANCE**;
- first raw-signal build: interrupted by GitHub runner shutdown while processing the merged ~2.32M-revision file;
- this was an infrastructure/memory-path failure, not a research-gate failure;
- recovery implementation now streams by issuer and consumes the persisted reconciliation + frozen definition directly;
- recovery workflow: Recover Phase-1 B3 raw signal inputs;
- 2023+ remains sealed and no B3 development outcomes have been read.
