# SEC bulk history: acquisition gate

This is a resumable **local acquisition layer**, not a canonical or validated
signal universe. It does not publish Pages, send alerts, open OOS, or advance the
incremental cursor. The one-business-day preview remains separate.

## Run

Set the identifying `SEC_USER_AGENT` environment variable. No Telegram/email
credentials are needed. Preview a range without network access:

```powershell
uv run insider-turning backfill-sec-history --start-year 2006
```

Add `--execute` to ingest from 2006 through the last completed quarter. For a
bounded first run:

```powershell
uv run insider-turning backfill-sec-history --start-year 2025 --start-quarter 3 --end-year 2026 --end-quarter 2 --execute
uv run insider-turning inventory-sec-activity --as-of 2026-09-09
```

The end date is explicit here for reproducibility; advance it as quarters finish.
One process downloads sequentially with the shared SEC pacer, bounded streaming,
retry/backoff and ZIP preflight. Do not run overlapping backfills concurrently.

Archive locations are resolved from the official [SEC catalog](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets).
There is no guessed `{year}q{quarter}.zip` fallback: actual `_form345.zip`
directories vary. Missing/unpublished quarters fail explicitly. Catalog requests
enforce the SEC host allowlist, no redirects, HTML type and a 4 MiB response cap.

ZIP/checksum cache lives in `data/cache/sec/raw`; string-typed Parquet staging
lives in `data/staging/sec/year=YYYY/quarter=Q`. Both are ignored by git. Staging
retains source tables, including non-signal transactions, and is not a public
dashboard export. Do not publish reporting-owner contact/address fields.

## Evidence and recovery

`data/staging/sec/history-inventory.json` describes the **requested range in the
latest invocation**, with per-quarter URL, archive and table-manifest checksums,
filing/row counts and STAGED/FAILED status. It is atomically updated after each
quarter. A failed quarter does not prevent later quarters from being attempted,
but the command exits nonzero and reports INCOMPLETE. It writes no canonical
commit marker. Interrupting leaves INCOMPLETE evidence and reusable completed
partitions. Rerun the same range to resume.

Every reuse verifies all eight tables, checksums, actual row counts, zero
quarantine, submission and transaction key uniqueness, and accession foreign
keys. A corrupt staging partition is rebuilt from the validated ZIP. STAGED means
these acquisition checks passed, **not** that economic classification, amendment
semantics, historical market coverage or scoring validation passed.

`activity-inventory.json` contains only candidate issuer CIKs/counts and source
manifest hashes, not owner identities or addresses. It is deterministic for the
same partitions and as-of date. It uses positive finite shares/price on matching
non-derivative P/A or S/D rows, trade dates within the trailing 365-calendar-day
window, and filing dates strictly before as-of. It never joins reporting owners
onto transactions, which would multiply multi-owner dollar counts. Exact
cross-quarter duplicates collapse; conflicting transaction keys fail closed.

The SEC [bulk documentation](https://www.sec.gov/files/insider_transactions_readme.pdf)
provides FILING_DATE, not an exact acceptance timestamp. Date-only inventory is
not proof of point-in-time availability. Unlinked amendments are excluded and
reported; the bulk surrogate row key is not assumed to equal the XML ordinal.
`canonicalReady` and `eligibleUniverseReady` remain false even if all requested
quarters exist. Missing current-quarter data is visible, never extrapolated.

## Verified local probe, 2026-09-09

- 2006 Q1 plus 2025 Q3–2026 Q2: 5 quarters, 2,388,284 flattened table rows,
  zero parser quarantine; all acquisition integrity checks passed.
- Recent four-quarter input produced 4,198 **candidate issuer CIKs**, not 4,198
  eligible US common stocks. It includes 92,094 priced P/S candidate rows in the
  as-of window, excludes 2,338 amendment rows and explicitly lacks 2026 Q3.
- The other 77 completed historical quarters have not been ingested by this probe.
- Regression checks: `tests/test_sec_history.py`, `tests/test_sec_historical.py`.
  These executable fixtures preserve the exact quality checks and failure cases.

Next: fill current-quarter global EDGAR index coverage, hydrate canonical XML
with exact acceptance evidence and amendment links, then apply point-in-time
security/exchange identity. Only that canonical output may feed the existing
365-day universe and daily scoring adapter. Historical acquisition does not
remove Experimental status or satisfy the sealed-OOS release gate.
