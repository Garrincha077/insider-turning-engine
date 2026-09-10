# Durable SEC daily acquisition

This closes **acquisition persistence**, not the complete production daily graph.
The dashboard remains experimental and actionable alerts remain disabled.

## Operational contract

- `Durable SEC daily acquisition` runs at 06:30 UTC Tuesday–Saturday, after the
  previous Eastern calendar day has ended. It lists the official SEC quarterly
  `index.json` directory and processes only published `master.YYYYMMDD.idx` dates.
  Holidays are not invented as empty filing days. Directory errors fail closed.
- The default scope is the trailing seven calendar days. At most three new or
  partial days are attempted, oldest first, with 750 new filings and a soft
  four-minute acquisition budget per day. The current in-flight request can run
  past that budget. A fifteen-minute outer budget leaves time to persist evidence.
- Every attempted day is normalized and persisted separately. Completed filings
  retain their original observation/knowledge timestamps across fresh runners.
  Quarantined filings remain quarantined and are not repeatedly retimed/refetched.
  All unprocessed and failed accessions are explicitly accounted for.
- Checkpoints are content-addressed `.json.gz` assets in non-latest prereleases
  named `sec-day-v1-YYYY-MM-DD-<sha256>`. Distinct progress gets a new version;
  existing releases/assets are never overwritten or deleted. An interrupted
  publish cannot replace the previous version. Identical replay creates no release.
- Upload is followed by a download, compressed hash/size check, bounded expansion,
  schema validation, and comparison with local bytes before storage is VERIFIED.
  Restoration validates the newest published evidence; corruption is an error,
  not a reason to silently substitute an older checkpoint. Interrupted draft
  releases are not checkpoints and require operator review if they block retry.
- Raw XML, SEC HTTP cache, quarantine excerpts/free-form messages and local paths
  are excluded from Releases. Assets contain public SEC canonical records (including
  public owner identities), structured row-error codes and acquisition provenance.
  Only the compact status report is uploaded as a workflow run artifact.
- The state branch is untouched. Neither acquisition markers nor release receipts
  are `sec-batch-committed.sha256` or authority to advance a production cursor.
- Source index hash/accessions are rechecked on replay. A changed archived index
  requires explicit repair rather than silently mixing discovery versions.

## Interpreting results

`storageStatus: VERIFIED` means every selected day's checkpoint is durable and
read-back verified. `acquisitionStatus: ACQUIRED` additionally requires no pending,
failed or quarantined rows. A partial day may be safely **stored but incomplete**.
The workflow summary displays both, with per-day stored/found counts, quarantine
and pending counts. Signal readiness, publication and delivery are always false.

Missing directories, failed storage or deferred days make the acquisition command
exit nonzero. Quarantines alone do not lose valid stored records, but still block
signal use. A successful storage workflow is **not** one of the five required
staging signal sessions and does not satisfy a backtest gate.

The old disconnected `daily.yml` producer graph no longer runs on its daily cron;
its manual fixture/import/replay paths and quarterly bulk acquisition remain.
The independent Pages preview schedule is unchanged. No snapshot is replaced here.

## Manual replay and recovery

Run the workflow with explicit `start`, `end`, `max_days` and `max_filings`, or:

```powershell
uv run insider-turning acquire-sec-daily --repository Garrincha077/insider-turning-engine --target <full-audited-commit-sha> --start 2026-09-09 --end 2026-09-09 --output-root work/sec-acquisition-manual --execute
```

Without `--execute` this is a network-free preview. Use a **fresh output root** on
every execution; the durable progress is restored from GitHub, not local cache.
An operator may rerun an incomplete range safely. Source errors and invalid
credentials never mean "no historical checkpoint". Do not delete assets to retry.

The rolling window is not a complete calendar coverage ledger: after an outage
longer than seven days, or if deferred work ages out of that window, explicitly
replay the missed ranges (at most 32 calendar days per command). The status reports
the exact requested scope; it makes no whole-history completeness claim.

## Remaining producer-graph work

1. Evidence-backed policy/repair for invalid non-economic rows; P/S-affecting errors
   must not become silent exclusions. No quarantine relaxation is introduced here.
2. Cross-day canonical manifest, deduplicated effective amendments and complete
   calendar coverage ledger, then point-in-time security/sector identity inputs.
3. Market acquisition, Gate 1 scoring and validated snapshot publication from those
   inputs. The acquired checkpoints alone are not effective or PIT-complete history.
4. Methodology freeze, real validation/OOS, durable signal outbox and operational
   release gates before enabling delivery or removing experimental labels.
