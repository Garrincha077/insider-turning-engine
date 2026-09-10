# Global SEC acquisition → market plan → daily inputs

The command-line data path is connected and tested offline. The scheduled daily
workflow has **not** been switched to this path: complete historical inputs,
identity evidence and a persistent canonical artifact store are still required.
These commands never deploy Pages, open OOS or send messages.

## 1. Acquire a completed global SEC filing day

With `SEC_USER_AGENT` configured:

```powershell
uv run insider-turning ingest-sec-day --day 2026-09-09 --max-filings 250 --execute
```

Repeat the command until complete. Successful per-filing normalization is cached
with its checksum, parser version, accession, index hash and original observation
time. A budget stop exits nonzero with `PENDING_BUDGET`; it is not a provider error.
Completed filings do not consume the next call's budget. Failed or quarantined
filings are retried. The raw HTTP cache prevents redundant submission downloads.

Output: `data/staging/sec-daily/2026-09-09/` contains `sec-batch.json`, an inventory
manifest and per-filing evidence. All are local, git-ignored acquisition artifacts,
not public dashboard data. A clean day additionally gets
`acquisition-complete.sha256`. This is explicitly **not** Gate 1's
`sec-batch-committed.sha256`; it never advances the production SEC cursor. Current
or future Eastern calendar dates are rejected, rather than cached as complete.
Select only known published index dates; a missing index fails, not an invented
zero-filing day. Multi-day/current-quarter enumeration remains to be connected.

Acceptance headers are interpreted as `America/New_York`, then converted to UTC,
including pre-2007 DST rules. Ambiguous/nonexistent clocks and acceptance after
retrieval fail closed. This corrects the previous assumption that an unzoned SGML
clock was UTC. Source: [SEC PDS specification, acceptance-time definition](https://www.sec.gov/files/edgar/pds_dissemination_spec.pdf).
Raw caches remain reusable; normalized evidence uses parser version
`ownership-eastern-v2.1`. Old normalized timestamps must be rederived, not silently
combined with this version. Observation/knowledge times are never backdated to
pretend a newly collected filing was known by an earlier close.

## 2. Plan market acquisition from actual canonical evidence

Supply canonical history, a complete new SEC envelope, and point-in-time identity
intervals. A bulk activity inventory is **not** a substitute for canonical history.

```powershell
uv run insider-turning plan-live-market --canonical data/warehouse/canonical.json --sec-batch data/staging/sec-daily/2026-09-09/sec-batch.json --identities data/warehouse/identities.json --as-of 2026-09-10T20:00:00Z
```

Use only a completed regular-session close for the eventual daily run; the date
above is an illustrative explicit cutoff, not a command to run before that close.
The planner writes `data/staging/market-plan/{plan.json,symbols.txt,benchmarks.txt}`.
It uses the same selection function as final input preparation: effective
amendments, positive priced P/A or S/D non-derivative activity in 365 days, observed
knowledge by as-of, eligible common-stock/exchange identity, SPY and sector ETFs.
It reports unmapped issuer CIKs rather than guessing tickers. Missing/ambiguous
issuer symbols in XML become null plus a quality flag; CIK identity is retained.

```powershell
uv run insider-turning update-market --symbols-file data/staging/market-plan/symbols.txt --benchmark-file data/staging/market-plan/benchmarks.txt --as-of 2026-09-10 --execute
```

Existing `update-market --csv-path <csv-or-parquet>` is the offline/import fallback.
The network command uses the existing Stooq adapter. It is not evidence of complete
adjustment/cross-provider validation, nor automatic switching to the experimental
Yahoo source. Coverage/benchmark evidence is carried forward for independent checks.

## 3. Connect artifacts to Gate 1

```powershell
uv run insider-turning prepare-live-inputs --canonical data/warehouse/canonical.json --sec-batch data/staging/sec-daily/2026-09-09/sec-batch.json --identities data/warehouse/identities.json --prior-state data/warehouse/prior-state.json --market-bars data/staging/market.parquet --market-quality data/staging/market-quality.json --as-of 2026-09-10T20:00:00Z --run-id run_live_daily_20260910
uv run insider-turning daily --execute --input-manifest work/live-daily/run_live_daily_20260910/daily-input-manifest.json
```

Preparation validates schemas/hashes and writes an immutable self-contained input
bundle. Reusing a run id with different inputs is rejected. Quarantined/incomplete
SEC envelopes are rejected before any prepared bundle is published. Optional
`--core-coverage` and `--backtest-report` consume existing evidence; their absence
is NOT an implicit PASS. The daily command independently computes quality and
keeps insufficient-data scores null and alerts suppressed.

## Actual probe and outstanding blockers

The 2026-09-09 index contains 553 unique ownership filings. The local probe fetched
them all: 552 normalized without quarantine; one has two derivative rows without
reported shares. 1,751 valid canonical transaction rows are retained. No values
were invented, no acquisition completion marker was written and no cursor moved.
This is one day of the current quarter, **not** full-quarter or 365-day coverage.

Regression tests cover DST/cutoff conversion, bounded replay, partial failures,
ambiguous tickers, future/missing-price exclusion, identical market selection
before/after acquisition, and the full offline CLI chain through daily execution.
The fixture chain intentionally remains blocked for publication: it is a contract
test, not a historical validation result.

Next integration requires explicit treatment of non-economic/insufficient SEC rows,
current-quarter index enumeration, complete canonical history and PIT identities,
then durable artifact restore and live market producer wiring in GitHub Actions.
Candidate methodology and experimental signals remain unchanged.
