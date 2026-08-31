# Release checklist

This is a research artifact release gate. It does not establish live validated
performance and must not be presented as investment advice.

## Reproducibility and tests

- [ ] Use Python 3.12 and Node 22; run `uv sync --all-groups --frozen` and
      `npm ci` in `app/`.
- [ ] Run `uv run ruff check src tests`, `uv run mypy src`, and `uv run pytest`.
- [ ] Enforce core branch coverage with the CI command and confirm `>= 85%`.
- [ ] Run `uv run insider-turning daily --fixture-only`; confirm no network,
      alert, or secret side effect.
- [ ] Validate JSON Schemas and deterministic replay/hash behavior.
- [ ] Confirm the frozen score contract includes every raw-to-0--100 component
      transform, not only model weights. Pin the exact implementation and
      config lineage on a clean reviewed commit before opening sealed OOS.

## Data and quality

- [ ] Pin SEC/market source watermarks, run ID, `as_of`, model/config versions,
      and adjustment basis.
- [ ] Confirm SEC identity and pacing: identifying User-Agent, cache, and no
      more than 6 requests/second.
- [ ] Confirm canonical parse success `>= 99.5%`, market coverage `>= 90%`,
      and core branch coverage `>= 85%`; persist numerator, denominator,
      exclusions, timestamp, and rule version.
- [ ] Check stale benchmark, source lag, quarantine spike, split gaps,
      unresolved ticker/sector mapping, and delisted attrition.
- [ ] Ensure every report includes the caveat block in
      [data-caveats.md](data-caveats.md), including survivorship, coverage,
      ticker, sector, and delisted/return attrition.

## Backtest and interpretation

- [ ] Verify development 2016–2020, validation 2021–2022, and sealed OOS from
      2023-01-01 through the last complete month before the reference date.
- [ ] Confirm knowledge-time scheduling, next-open entry, exact session
      horizons (21/63/126/252), SPY excess, MAE, 20-session deduplication, and
      named attrition rather than zero returns.
- [ ] Confirm evaluator/tuner code cannot access sealed OOS. Reveal only via
      the final-report path.
- [ ] Assign exactly one disposition: `PASS`, `INCONCLUSIVE`, or `FAIL`.
      `PASS` requires all quality, temporal, benchmark, schema, and hash gates;
      incomplete/unknown evidence is `INCONCLUSIVE`; violations or below-gate
      quality are `FAIL` and block healthy publication.

## Dashboard and GitHub Pages artifacts

- [ ] Confirm the daily run itself produces score components,
      `dashboard-input.json`, alert candidates, and SEC batch-commit evidence
      from canonical inputs. File-existence checks or pre-baked fixture output
      do not satisfy this end-to-end gate.
- [ ] Run `uv run insider-turning export-dashboard --source <source> --output
      app/public/data` and inspect `dashboard.json` plus `manifest.json`.
- [ ] Confirm the manifest pins versions/watermarks and SHA-256 hashes for all
      files and that dashboard status is visibly `VALIDATED`, `EXPERIMENTAL`,
      or `STALE`.
- [ ] In `app/`, run `npm run lint`, `npm run typecheck`, `npm run build`, and
      `npm run test:e2e`.
- [ ] Confirm `app/dist/index.html` and `app/dist/data/dashboard.json` are
      non-empty and valid JSON. The Pages workflow publishes only `app/dist`;
      do not document or assume a deployed URL until the deployment reports
      one.
- [ ] Keep `.env`, tokens, raw payloads, caches, staging, warehouse files, and
      unreviewed generated artifacts out of the commit.

## Alerts and rollback

- [ ] Keep `send-alerts` in preview mode until all gates pass and a human
      reviews candidate reasons/cooldowns.
- [ ] Verify outbox idempotency, suppression, failure, and uncertain delivery
      records; use no secrets in logs.
- [ ] If publication fails, retain the previous valid snapshot, inspect hashes
      and watermarks, and replay as a new run. Never overwrite evidence or make
      a stale/partial artifact look green.
