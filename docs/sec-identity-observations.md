# Point-in-time SEC identity observations

`observe-sec-identities` supplies the previously missing current-identity producer
for `plan-live-market` and `prepare-live-inputs`. It does **not** produce signals,
change a cursor, publish Pages, or send alerts.

## Source and time contract

- The official [exchange map](https://www.sec.gov/files/company_tickers_exchange.json)
  supplies CIK/ticker/exchange associations. It is fetched freshly each run, not
  replayed indefinitely from a current-map cache.
- The [SEC submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
  supplies current issuer metadata, including SIC and listing corroboration.
  Existing bounded, non-redirecting SEC transport shares the 6 req/s pacer.
- `knowledge_at` is the later retrieval instant of the two sources. No user
  override backdates it to a filing date or a previous session close. After-close
  retrieval cannot affect the closed session, so daily acquisition must build
  observations in advance of a later signal session.
- US incorporation is confirmed only by a US state/DC code. Foreign/unknown
  incorporation, non-operating entities, missing SIC, excluded securities, absent
  listings and conflicting/multiple classes remain unresolved, with reason codes.
  This is a conservative v1 selection bias, not a complete security master.
- A resolved identity is **not** proof of common-stock eligibility. The market
  planner still requires a point-in-time non-derivative common-stock title from
  canonical ownership data. Multiple share classes need a future explicit
  security-level contract; they are not resolved by lexical ticker sorting.
- New live observations map through `config/sic-sector.v1.1.yaml`; its version and hash are retained.
  The old `sic-sector.v1.yaml` remains unchanged for replay.
  Unknown sectors stay `UNKNOWN`, never SPY. SIC is a sector proxy, not historical GICS.

## Run locally

Create an ignored CIK text file containing one issuer CIK per line. The input must
come from the intended insider-active inventory; this command does not certify that
inventory as complete. Duplicate CIKs are removed deterministically.

```powershell
uv run insider-turning observe-sec-identities --ciks-file work/active-ciks.txt --output work/identity-run-001 --run-id run_identity_20260911
```

The default is network-free preview. Add `--execute` to fetch using `SEC_USER_AGENT`.
On later runs, use a fresh output directory and
`--previous work/identity-run-001/identities.json` to append observation history.

The output directory contains:

- `identities.json`: immutable old and new observations, stable ordering.
- `identity-manifest.json`: counts, unresolved reasons, previous-input hash and
  identities checksum; all signal/publication/alert gates remain false.
- `raw/`: source responses and exchange cache evidence. Keep this out of git and
  out of public Pages; it is local provenance, not a dashboard payload.

The directory appears atomically, after all files are written. An existing output
is never overwritten. A global exchange-source failure produces no usable bundle.
One issuer metadata failure produces an unresolved observation and exit code 1
(`PARTIAL`), with other results preserved. Partial identity data must never be
treated as complete coverage.

Pass the resulting `identities.json` to `plan-live-market`/`prepare-live-inputs` at
a later eligible session cutoff. The planner selects the newest observation before
checking eligibility: an unresolved/expired/newly excluded listing cannot fall
back to an older usable row. Simultaneous conflicting observations are excluded.
Source provenance survives the prepared manifest, and common-stock types use the
daily core's canonical `COMMON_STOCK` spelling.

## Live acquisition check

At `2026-09-10T23:24:04Z`, a local probe requested the first 20 distinct issuer CIKs
(numeric order) with non-derivative P/S rows in the acquired September 9 SEC batch.
Seventeen had unambiguous corroborated current listings; three were excluded for
multiple listings (`AMBIGUOUS_LISTING`). No issuer metadata requests failed.
Four resolved identities had unmapped SIC sectors, retained as `UNKNOWN`. The
existing coarse SIC-sector table also needs an independent mapping audit before
these observations drive public sector-relative signals; this change does not
alter that table or certify its classifications.
This is a small acquisition check, **not** a representative coverage measurement
or a complete/validated active universe. The global exchange-map parser also
reported 210 quarantined rows, separately from these 20 requested issuers.
The command correctly returned `PARTIAL`/exit 1 and kept every publication gate false.

The local identities artifact SHA-256 is
`4410b5e743497a3d85bbd10e6261c33c823d720a75502d7c27ea63a775705d45`.
The ignored bundle is `work/identity-probe-20260911`; no raw responses entered git.

## Remaining production work

The **Experimental Pages workflow now uses this adapter**. On each refresh it
restores the latest checksum-verified identity history from a non-latest prerelease,
appends current observations for purchase-active issuers in the selected SEC window,
and uploads an immutable `sec-identity-v1-<SHA256>` Release. A read-back check must
succeed before the new dashboard is produced. No prior observation may be discarded.
Only allow-listed public issuer metadata and source hashes enter these Releases;
raw payloads and the operational `state` branch remain separate.

Pages refresh runs at **07:15 UTC Tuesday–Saturday**, after the previous Eastern
SEC day is complete. It reads actually published indices within the trailing five
weekday window, not assumed holiday files, and has a 30-minute timeout. UI-only
deploys still preserve source dates and do not refresh identity history. There is
one serialized Pages writer; do not run independent concurrent identity publishers.

The standalone observation command remains local-only and sequential. Large
365-day inventories still need bounded sharding/resume before unattended use.

Current observations cannot repair missing historical ticker/sector evidence for
backtests. The full SEC history/amendment gate, historical identity coverage,
methodology freeze and sealed OOS remain separate release blockers. Identity/universe
selection must be included in the final methodology lineage audit before freezing.

## SIC v1.1 scoped correction

The reviewed [SEC industry descriptions](https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list)
identify 1040 as gold/silver ores, 1623 as heavy infrastructure construction,
2320 as apparel, and 2510 as household furniture. The previous table put all
1000–1399 into Energy and omitted the latter three categories. The new live-only
mapping uses Materials (XLB) for metal mining 1000–1099, Industrials (XLI) for
1600–1699, and Consumer Discretionary (XLY) for 2300–2399 and 2510–2519.
This sector-ETF assignment is the engine's documented proxy inference, not an
official SEC or GICS classification. Other broad rules are inherited, not newly certified.

The five affected issuer observations in the 20-CIK probe can now map without
inventing company-specific overrides. Golden tests check the changed boundaries
and preserve the original v1.0 result for historical replay. The public preview
now fetches actual sector ETFs; it never substitutes SPY for an unknown sector.
Missing required sector benchmarks or <90% selected-symbol price coverage block
publication. Unknown-sector issuers cannot receive a complete technical score.

The preview remains a current materialization over a limited purchase-active window,
not a sealed historical daily-close backtest or a full 365-day insider-active universe.
Every candidate carries identity time, source hash, sector version/hash and the
immutable identity Release link in `sourceReferences`. Alerts stay off.
