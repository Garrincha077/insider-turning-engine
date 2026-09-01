# Insider Turning Engine

Insider Turning Engine is a research-only, point-in-time data pipeline for
normalizing SEC ownership filings, combining qualified insider activity with
market features, and producing explainable issuer states and alert candidates.
It is not investment advice, a trading system, or a claim of live validated
performance. The checked-in dashboard bundle is a real-data
`LIVE_EXPERIMENTAL` snapshot: official SEC ownership filings are combined with
Yahoo adjusted chart data as a temporary Stooq fallback. Its methodology and
backtest are not validated, Telegram remains off, and every limitation is
listed in the content-addressed manifest.

## Repository map

- `src/insider_turning_engine/`: Python ingestion, features, scoring, state,
  backtest, notifications, and dashboard export.
- `config/scoring.v1.yaml`: executable score weights, state gates, alert rules,
  provider pacing, and publication thresholds.
- `config/scoring.v1.lock.json`: immutable v1 hash, lineage, freeze timestamp,
  and source-commit attestation used by score/backtest/publication validators.
- `schemas/`: canonical transaction, signal snapshot, and dashboard manifest
  interchange contracts.
- `docs/architecture/`: accepted identity, point-in-time, provider, state, and
  threat-model decisions.
- `tests/fixtures/`: synthetic SEC XML and a compact synthetic market CSV; no
  fixture is an SEC filing or live performance sample.
- `app/`: Vite/React dashboard consuming `dashboard.json` and its manifest.

## Local setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22.13+
or newer, and npm. From the repository root:

```powershell
uv sync
Copy-Item .env.example .env
$env:SEC_USER_AGENT = "InsiderTurningEngine/0.1 (+you@example.com)"
uv run insider-turning --help
uv run pytest
uv run ruff check src tests
uv run mypy src
```

For the dashboard:

```powershell
Set-Location app
npm ci
npm run lint
npm run typecheck
npm run build
npm run dev
```

See [app/README.md](app/README.md) for the browser workflow and Pages artifact
boundary. Never commit `.env` or provider credentials.

## CLI

Every command is safe by default: omitted required inputs produce JSON
`DRY_RUN` output and do not contact a provider or send an alert. The complete
surface is:

| Command | Purpose | Safe example |
|---|---|---|
| `backfill-sec` | Download and stage one official SEC quarterly bulk archive | `uv run insider-turning backfill-sec` |
| `update-sec` | Normalize local ownership XML, or fetch and normalize incremental SEC filings from a CIK file with `--execute` | `uv run insider-turning update-sec` |
| `update-market` | Validate canonical CSV fallback and write provider-neutral Parquet | `uv run insider-turning update-market` |
| `build-features` | Build bounded price/state facts | `uv run insider-turning build-features` |
| `build-signals` | Apply frozen score weights to component JSON | `uv run insider-turning build-signals` |
| `backtest` | Run a point-in-time event backtest when both `--events` and `--bars` are supplied | `uv run insider-turning backtest` |
| `export-dashboard` | Validate and atomically publish browser artifacts | `uv run insider-turning export-dashboard` |
| `send-alerts` | Preview candidates; external delivery requires `--execute` | `uv run insider-turning send-alerts` |
| `daily` | Report the scheduled plan | `uv run insider-turning daily` |

The deterministic offline smoke run parses all synthetic filings and the
synthetic market panel without network or alerts:

```powershell
uv run insider-turning daily --fixture-only
```

Useful fixture-backed stages (these write only under `work/`, which is ignored
by git):

```powershell
New-Item -ItemType Directory -Force work | Out-Null
uv run insider-turning update-sec `
  --xml tests/fixtures/form4_original.xml `
  --accession 0001234567-26-000001 `
  --source-url https://www.sec.gov/Archives/edgar/data/fixture/form4_original.xml `
  --output work/sec-incremental.json
uv run insider-turning update-market `
  --csv-path tests/fixtures/daily_market.csv `
  --as-of 2020-01-31 `
  --output work/market.parquet
uv run insider-turning build-features `
  --market work/market.parquet `
  --as-of 2020-01-31 `
  --output work/price-features.parquet
```

Incremental SEC ingestion is also available when a deployment supplies a CIK
file. It is the network-enabled form of `update-sec`; retain the cursor file
between runs for bounded, replayable progress:

```powershell
uv run insider-turning update-sec `
  --cik-file data/incoming/ciks.txt `
  --cursor-file data/state/sec.cursor `
  --output work/sec-incremental.json `
  --execute
```

`backfill-sec --year YYYY --quarter 1..4 --execute` and
`update-sec --cik-file path/to/ciks.txt --execute` enable SEC network requests;
both require `SEC_USER_AGENT`. `update-sec --xml ...` is local-only.
`backtest` executes and writes its report when both `--events` and `--bars` are
provided; otherwise it returns `DRY_RUN`. `send-alerts --execute` is the
explicit external-delivery switch and reads `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`; keep it off until quality and backtest gates are reviewed.
Preview mode records candidates in the local SQLite outbox for audit and later
replay; it never contacts Telegram.

The scheduled workflow can consume deployment-provided
`data/incoming/sec.xml` plus `data/incoming/sec.json` (`accession` and
`sourceUrl`) and `data/incoming/market.csv`. The checked-in repository does not
yet contain the canonical aggregation adapter that must produce per-ticker
component JSON, `dashboard-input.json`, alert candidates, and SEC batch-commit
evidence. Those files are deliberately not synthesized or copied from an old
dashboard: their absence keeps publication and alerts blocked. A full live
universe and default universe files are also not checked in.

## Research protocol and limitations

Read [docs/methodology.md](docs/methodology.md),
[docs/data-caveats.md](docs/data-caveats.md), and
[docs/runbook.md](docs/runbook.md) before interpreting a report. Every report
must include the standard caveat block covering survivorship, universe and
market coverage, point-in-time ticker/sector mapping, and delisted/return
attrition. Results are for research only and are not investment advice.

## License and status

This repository is an engineering/research scaffold. A successful local test
run does not establish production readiness or investment performance. The
release process is defined in [docs/release-checklist.md](docs/release-checklist.md)
and security boundaries in [docs/security.md](docs/security.md).
