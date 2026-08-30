# Insider Turning Engine dashboard

This Vite/React app is a static consumer of the compact dashboard projection
under `public/data/`. It is a research interface only; it is not investment
advice. The checked-in `public/data/dashboard.json` is sample data with status
`EXPERIMENTAL`; its checked-in `public/data/manifest.json` is `DEGRADED` with
the `ILLUSTRATIVE_SAMPLE` issue. This illustrative bundle is not a live
validated result or a deployed URL.

## Local development

Use Node.js 22.13+ and npm from this directory:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
npm run dev
```

The dev server reads `public/data/dashboard.json`. Open the URL printed by Vite
after `npm run dev`; no API or credentials are required for the sample.

For browser checks:

```powershell
npx playwright install --with-deps chromium
npm run test:e2e
```

## Data contract and publication

The app fetches `${BASE_URL}data/dashboard.json`; the Python exporter writes a
validated `dashboard.json`, optional ticker chunks, signal snapshots, and a
content-addressed `manifest.json` to `app/public/data`. The manifest pins
`asOf`, source watermarks, scoring/state versions, quality measurements, and
SHA-256 file hashes. A consumer must fail closed on missing or mismatched
artifacts and visibly show stale/degraded or experimental status.

Publish a new local projection from the repository root:

```powershell
uv run insider-turning export-dashboard `
  --source path/to/dashboard-source.json `
  --output app/public/data
```

Then run the checks above. The GitHub Pages workflow builds `app/`, validates
`app/dist/index.html` and `app/dist/data/dashboard.json`, uploads `app/dist`,
and deploys from `main` or a manual workflow dispatch. It does not provide a
stable URL in this repository; use the URL reported by GitHub for the specific
deployment.

## Interpretation and caveats

Visible views include radar candidates, market pulse, turning stocks,
divergence, smart buys, clusters, cost basis, SEC tape, company lab, and the
backtest lab. These views are projections, not provider records. Every report
or export must include survivorship, coverage, point-in-time ticker mapping,
sector revision, and delisted/return attrition caveats. See
[`../docs/methodology.md`](../docs/methodology.md) and
[`../docs/data-caveats.md`](../docs/data-caveats.md).
