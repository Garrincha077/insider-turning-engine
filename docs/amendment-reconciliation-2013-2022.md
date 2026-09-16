# SEC PIT Amendment Reconciliation 2013–2022

**Status:** `PASS`  
**Completed:** 2026-09-16  
**Scope:** Research-only historical SEC Form 4/A and 5/A reconciliation, 2013–2022  
**OOS boundary:** 2023+ remained sealed  
**Production scoring:** unchanged  
**Production parser:** unchanged

## Executive summary

The SEC amendment-reconciliation gate for 2013–2022 is complete.

The original monolithic reconciliation job was interrupted twice by GitHub-hosted runner shutdowns rather than by a data-contract or reconciliation failure. The process was therefore restructured into eight resumable issuer-safe shards. Sharding was based on issuer CIK so that every predecessor/successor amendment chain remained inside one shard. All eight shards passed, followed by a successful deterministic global merge and audit.

The resulting amendment-reconciled historical transaction dataset is now ready for the next research gate: historical market-data joining.

## Workflow evidence

- Workflow run: `35115489296`
- Workflow: `Finalize SEC PIT amendment reconciliation (sharded)`
- Commit: `08339ef60391eb002c2f3b63c5b95289177b83ab`
- Preflight evidence gate: `PASS`
- Issuer shards: `8/8 PASS`
- Deterministic global merge and audit: `PASS`
- Persistent release asset: `sec-amendment-reconciliation-2013-2022.tar.gz`
- Reconciliation archive SHA-256: `74935001c86c4e4852f06f715dadf0a85ffc61e77a2daa1855e643bb2bb6e363`

## Dataset counts

| Metric | Count |
| --- | ---: |
| Original canonical rows | 573,322 |
| Amendment canonical rows | 102,901 |
| Transaction-bearing amendment filings hydrated | 39,817 |
| Zero-transaction amendment filings observed | 2,174 |
| Linked amendment rows | 9,619 |
| Reconciled revision rows | 582,925 |
| Effective rows at end of 2022 | 573,322 |
| Research quarantine rows | 18,916 |
| Resolver quarantine rows | 16 |

## Filing-level linkage results

| Linkage status | Filings |
| --- | ---: |
| `LINKED_TO_ORIGINAL_BUY_UNIVERSE` | 3,214 |
| `PARTIALLY_LINKED_EXACT_ROWS` | 359 |
| `PREDECESSOR_OUTSIDE_ORIGINAL_BUY_UNIVERSE` | 31,836 |
| `UNRESOLVED` | 4,408 |

`PREDECESSOR_OUTSIDE_ORIGINAL_BUY_UNIVERSE` is not treated as a reconciliation error. The research universe contains qualified original-buy history rather than every historical Form 4/5 transaction, so many amendments legitimately refer to predecessor filings outside that narrower original-buy universe.

Unresolved or ambiguous evidence was not force-matched. It remained quarantined.

## PIT and linkage policy

The reconciliation kept the historical information boundary explicit and fail-closed.

- Historical lifecycle `validFrom` was normalized to `knowledgeAt == SEC acceptedAt` for research reconciliation.
- The production parser was not changed.
- Primary date evidence: `SEC SUBMISSION.DATE_OF_ORIG_SUB`.
- Identity evidence:
  - issuer CIK;
  - reporting-owner CIK;
  - Form family;
  - exact owner / table / row sequence.
- Multi-amendment chains use the immediate `supersedesRevisionId` once the root predecessor is established.
- No fuzzy matching on transaction price, share count, or transaction date was used.
- Ambiguous links were quarantined rather than guessed.
- No 2023+ OOS evidence was opened.

## Sharding design

The reconciliation was split into eight deterministic issuer-safe shards using:

`sha256(issuer_cik)[0:8] mod 8`

This is valid for the reconciliation algorithm because issuer identity is a required invariant for every amendment predecessor/successor link. Therefore a valid chain cannot cross issuer shards.

The global merge was deterministic and produced hashes for the merged research files:

- `amendment-linkage.jsonl`: `4937a80ba3def8270b51842e450612c3410af01738159c1bf7ab91cb3402b65b`
- `effective-end-2022.jsonl`: `4e113ae5fcf7cd1e27735b029c04bf8b2460bc64d2d442e4d279e0b7c60e93f1`
- `quarantines.jsonl`: `e739fdd369268e63bc0506b258db03d1419a49b714d673441d47764c7a456c55`
- `reconciled-all-revisions.jsonl`: `fadcc8b4fc274386e09a71a7a3e7bd0bc14294d4f9f1cce7029c315d047ec145`

## Gate decision

**Amendment reconciliation 2013–2022: `PASS`.**

This gate is closed for purposes of continuing the predeclared research sequence. It does not imply that the model, scoring system, or signal engine has predictive validity, and it does not authorize production scoring changes.

The reconciliation output remains:

- `canonicalReady = false`
- `marketDataJoined = false`
- `signalReady = false`
- `oosOpened = false`

## Next gate

Proceed to the **historical market-data gate** before running formal insider-signal benchmarks.

Required work includes:

1. Historical adjusted OHLCV.
2. Delisted securities and delisting outcomes.
3. Valid-time security identity and historical ticker/CIK mapping.
4. Split/dividend/corporate-action reconciliation.
5. SPY benchmark series.
6. Trailing dollar ADV / liquidity measures.
7. PIT market-cap observations or a documented PIT-safe substitute.
8. Explicit missing-data and attrition policy.

Only after this gate passes should the project proceed to the simple insider benchmark phase on 2016–2020 development and 2021–2022 validation data.

## Research constraints carried forward

- Do not open 2023+ OOS without explicit authorization.
- Do not change `config/scoring.v1.yaml`, `config/scoring.v1.lock.json`, production weights, thresholds, alerts, or state-machine thresholds without explicit authorization.
- Keep market-data work research-only until its data-quality gate is complete.
- Preserve delisted names and report attrition rather than silently dropping missing outcomes.
