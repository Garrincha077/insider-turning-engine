# SEC derivative repair — verified read-only dry-run (2026-11-01)

## Scope and prior evidence

An immutable research snapshot (`run_research_20261101T104911Z`)
had 63/63 SEC day checkpoints and no missing daily indices, but
38 quarantined transaction rows across 15 SEC days. The source replay
workflows `41318595461`, `41318842112`, and `41319116836`
confirmed unchanged official SEC index and complete-submission provenance,
35 records parsable with current parser v2.4, and three genuine
non-derivative transactions with **no transaction code**. Those three
remain quarantined; nothing here infers a P/S code.

## Actual existing repair_checkpoint() dry-run

[GitHub Actions run 41320756872](https://github.com/Garrincha077/insider-turning-engine/actions/runs/41320756872)
ran the existing production `repair_checkpoint()` **in memory** on complete
verified checkpoints. It never called `ReleaseCheckpointStore.persist()`.
The original checkpoint encoding remained byte-for-byte unchanged.
Recovered records had new knowledge/recorded/observed/valid-from timestamps
equal to the simulated repair instant, not a backdated SEC acceptance time.

- The existing repair predicate covers 9 derivative-only filings / 13
  quarantined rows. An additional derivative row occurs in a mixed-quarantine
  filing, not eligible for this whole-filing repair predicate.
- Four derivative-only filings have original parsed-row lineage, while five
  have no original canonical rows. None of the four has mixed prior lineage.
- Two whole-day invocations passed the full dry-run (2026-09-02 and 2026-09-09),
  verifying four prospective recovered derivative rows.
- The other two lineage-backed filings (on 2026-09-03 and 2026-09-08)
  **could not be repaired as whole days**: each day also has a derivative
  candidate lacking original canonical lineage. Masking those candidates
  would modify the proof boundary and is not authorized.
- Three other days with only unproven derivative-only candidates
  are also blocked (2026-08-04, 2026-08-13, 2026-09-01).
- Eight of the 15 studied days had no candidate under the existing
  whole-filing derivative repair predicate.

## Release gate

**No existing or new SEC Release was altered or published.** The dry-run
does not constitute approval to release repaired rows, change the canonical
SEC cursor, mark historical PIT windows complete, change scoring, send alerts,
or enable production predictive readiness.

For a potential future explicitly controlled release of the two passing
full-day candidates, re-check unchanged source hashes/lineage and
rerun the repair with the actual new knowledge timestamp at execution time.
Respect the immutable release ancestry, canonical row-ID and original
byte-preservation guards; do not reuse a stale dry-run timestamp.

The two co-located lineage-backed filings require a separately designed
full-day source reconciliation strategy with new tests; selectively removing
the other quarantines to make `repair_checkpoint()` pass is unacceptable.
Cases with no original canonical rows require a different, source-verified
new-observation process, not a silent historical repair. No pipeline should
overwrite the three still-invalid code-less non-derivative records.

This is operational evidence only; the SEC parser, trading scores, backtests,
methodology, quality gates, publication policy, and Telegram ledger are unchanged.
