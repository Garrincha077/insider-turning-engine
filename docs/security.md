# Security and data handling

The pipeline treats regulatory documents, vendor responses, CSVs, and rendered
strings as untrusted input. Signals and alerts are research tooling only and
not investment advice.

## Network and provider controls

- SEC requests require an identifying `SEC_USER_AGENT` with a project name and
  contact email. Keep aggregate SEC traffic at or below 6 requests/second;
  honor retry guidance and bounded backoff.
- Cache SEC archives/submissions and Stooq bars for reproducibility and quota
  safety. The Stooq adapter uses a five-minute in-memory cache, bounded retries,
  and does not follow redirects.
- Allowlist approved SEC/Stooq hosts; reject redirects or resolved addresses
  outside approved endpoints. Do not fetch arbitrary URLs from input data.
- Enforce timeouts, content-size/decompression/nesting limits, strict encoding,
  safe XML parsing, schema validation, numeric bounds, and trading-calendar
  checks. Quarantine invalid required fields.

## Secrets and logs

Copy `.env.example` to `.env` as a local template; `.env` is ignored by git and
the CLI reads process-environment variables rather than loading that file. The
CLI reads `SEC_USER_AGENT` when `backfill-sec --execute` or
`update-sec --cik-file ... --execute` is used; `update-sec --xml ...` remains
local-only. The `update-sec` incremental adapter persists progress in its
`--cursor-file` (default `data/state/sec.cursor`), so retain that state for
auditable replay. `send-alerts --execute` reads `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` directly and requires both values. Use a runtime secret
store in CI/deployment, never source-control tokens, and never include secrets
in raw evidence, exceptions, manifests, fixtures, or logs. Redact
authorization headers, bot tokens, email addresses where not required, and raw
personal/contact data. Use correlation/run IDs for support.

## Content and publication safety

- Escape rendered strings and neutralize spreadsheet formula prefixes.
- Never execute raw markup or provider content.
- Validate canonical records, signal snapshots, dashboard JSON, and manifests
  before publication; fail closed on missing or hash-mismatched artifacts.
- Publish only point-in-time eligible inputs. A stale or degraded run must be
  visibly labeled and must not appear healthy.
- Keep alert candidate creation separate from delivery. Use idempotency keys,
  the 14-day cooldown, and an auditable outbox to prevent floods and duplicate
  sends.

Report source freshness, quality flags, exclusions, attrition, and the standard
survivorship/coverage/ticker/sector/delisted caveats on every report. Research
only; not investment advice.
