# Operations runbook

This runbook is for local/reproducible research runs. It does not authorize
production delivery or imply live validation. Keep alert delivery disabled
until the release checklist passes.

## First run and daily dry run

```powershell
uv sync
Copy-Item .env.example .env
$env:SEC_USER_AGENT = "InsiderTurningEngine/0.1 (+you@example.com)"
uv run insider-turning daily
uv run insider-turning daily --fixture-only
```

The first command reports the network/quality prerequisites without fetching.
The fixture command parses `tests/fixtures/form*.xml` and
`tests/fixtures/daily_market.csv` without network or alerts and is the safest
smoke test. `daily` without `--fixture-only` reports the scheduled plan; it
does not itself execute the scheduled stages. The scheduled workflow can read
deployment-provided `data/incoming/sec.xml` and `data/incoming/sec.json` (with
`accession` and `sourceUrl`) plus `data/incoming/market.csv`. The repository
does not yet implement the canonical aggregation adapter that produces
per-ticker score components, `dashboard-input.json`, alert candidates, and the
SEC canonical commit marker. The workflow therefore remains intentionally
fail-closed for live publication; existence checks and fixture data are not a
substitute for that missing producer graph.

## Source ingestion

SEC quarterly staging (explicit network opt-in):

```powershell
uv run insider-turning backfill-sec `
  --year 2024 --quarter 1 `
  --cache-dir data/cache/sec `
  --staging-dir data/staging/sec `
  --execute
```

The process requires a non-empty identifying `SEC_USER_AGENT`, caches raw
archives, validates safe extraction, and paces requests at no more than 6 per
second. Keep `data/raw`, `data/cache`, and staged outputs outside commits.

Incremental XML normalization and offline market staging:

```powershell
uv run insider-turning update-sec `
  --xml path/to/ownership.xml `
  --accession 0001234567-24-000001 `
  --source-url https://www.sec.gov/Archives/edgar/data/.../ownership.xml `
  --accepted-at 2024-02-01T14:30:00+00:00 `
  --output data/staging/sec-incremental.json

uv run insider-turning update-market `
  --csv-path tests/fixtures/daily_market.csv `
  --as-of 2020-01-31 `
  --output data/staging/market.parquet
```

For real incremental SEC ingestion, provide a newline- or comma-separated CIK
file and explicitly opt in to the network request. `SEC_USER_AGENT` is
required, and the cursor should be retained between runs:

```powershell
uv run insider-turning update-sec `
  --cik-file data/incoming/ciks.txt `
  --cursor-file data/state/sec.cursor `
  --output data/staging/sec-incremental.json `
  --execute
```

The `--xml` form above is local-only and does not contact SEC. A malformed
cursor is preserved with a `.corrupt-<timestamp>` suffix and the source can
replay safely using downstream idempotency.

Stooq is the daily OHLCV provider for supported benchmark/sector symbols. Use
the CSV provider for fixtures, replay, and an offline fallback; both must
produce the provider-neutral `DailyBar` contract.

## Features, signals, backtest, and publication

```powershell
uv run insider-turning build-features `
  --market data/staging/market.parquet `
  --as-of 2020-01-31 `
  --output data/warehouse/price-features.parquet

uv run insider-turning build-signals `
  --components path/to/components.json `
  --output data/warehouse/scores.json

uv run insider-turning backtest `
  --events path/to/events.json `
  --bars data/staging/market.parquet

uv run insider-turning export-dashboard `
  --source path/to/dashboard-source.json `
  --output app/public/data
```

Supplying both files executes the backtest and writes an `EXPERIMENTAL`
report; omitting either input returns the command's `DRY_RUN` plan.
Each event may set `exposure_family` to `FULL_ENGINE`, `SIMPLE_PS`,
`UNIQUE_BUYER_RATIO`, `LARGEST_BUYS`, or `CLUSTER_BUYS`. The formal gate uses
only separately supplied benchmark streams; it never relabels full-engine
events as a simple strategy. Missing benchmark families therefore keep the
result `INCONCLUSIVE`.

Formal PASS also requires `--validation-evidence path/to/evidence.json` with
numeric parse/market/core-coverage rates and actual JSON booleans for
canonical, schema, hash, temporal, benchmark-freshness, and
`scoring_methodology_complete` controls. Omitting the file or the methodology
attestation can never produce PASS. The `temporal_valid` flag is an explicit
review attestation that the sealed OOS result was not inspected before
`config/scoring.v1.lock.json` froze the exact v1 config; do not infer it merely
from historical event dates.

`export-dashboard` validates the compact dashboard shape and atomically replaces
the destination only after files and the manifest validate. Check
`app/public/data/dashboard.json` and `manifest.json`; the manifest includes
versions, watermarks, quality, file sizes, and SHA-256 hashes. Treat
`EXPERIMENTAL` or `STALE` dashboard data as non-validated. The checked-in
bundle is a real-data rolling-window preview: `dashboard.json` is
`EXPERIMENTAL`, while `manifest.json` is `DEGRADED` with
`LIVE_EXPERIMENTAL_ROLLING_WINDOW` and provider/methodology caveats.

## Alerts

Preview only:

```powershell
uv run insider-turning send-alerts --candidates path/to/candidates.json
```

External delivery is a separate, explicit action:

```powershell
uv run insider-turning send-alerts `
  --candidates path/to/candidates.json `
  --execute
```

With `--execute`, the CLI reads `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` from the environment and requires both. Without it,
candidate delivery remains a preview, is retained in the SQLite outbox, and no
network send occurs.
Before enabling it, review quality flags, stale benchmark status, alert
reasons, and the SQLite outbox. Delivery is idempotent, subject to the 14-day
cooldown, and must record suppressed/failed/uncertain attempts. Never put a
bot token or personal contact data in logs or reports.

## Recovery and failure handling

### Partial stage or fetch failure

Do not manually edit a checkpoint to skip a page. Preserve raw payloads and
quarantine rows, inspect the structured error and source watermark, then rerun
the same bounded stage. Cursors/checkpoints advance only after durable output;
replay is expected to be idempotent.

The scheduled state branch also carries only the compact `alerts.sqlite`
delivery ledger (WAL-checkpointed before close); raw filings, caches, Parquet,
and dashboard bundles remain outside that branch.

### Stale benchmark or market source

Stop publication and alert delivery. Confirm the latest session and
`available_at`, provider health, cache age, and coverage report. Refresh Stooq
or use a pinned canonical CSV fallback, then rebuild features and snapshots.
Label the run `INCONCLUSIVE` while incomplete and `FAIL` when stale data is
used as if current. Never backfill a stale value into a prior `as_of`.

### Corrupt state, manifest, or artifact

Fail closed. Verify JSON Schema, SHA-256 file hashes, version pins, and
watermarks. Keep the prior published snapshot intact, restore the last known
valid immutable artifact, and replay into a new run directory. Do not delete
or overwrite evidence to make a check pass.

### Quarantine spike or schema drift

Stop the affected publication, sample only safe excerpts/locators, compare
provider schema and parser version, and repair through a new revision. Required
fields must remain quarantined until resolved; do not coerce malformed values.

## Completion record

Record run ID, `as_of`, source watermarks, quality numerators/denominators,
quarantine and attrition counts, artifact hashes, disposition (`PASS`,
`INCONCLUSIVE`, or `FAIL`), and the required caveat block from
[data-caveats.md](data-caveats.md). This is research output, not investment
advice.
