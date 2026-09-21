# Phase-1 feature tournament Stage-B exact long-gap diagnostics gate

Frozen: 2026-09-21 after provider17 resolution and before any long-gap
continuity decision or feature outcome is opened.

## Purpose

Recover the exact XNYS session interval of every frozen Stage-B unresolved
`long_internal_gap` row.

The initial Stage-B continuity ledger stored the maximum internal gap size but
not the exact bracketing sessions. This stage recomputes only session presence
from the same frozen 2016-2022 market corpus and must reproduce the frozen gap
size exactly before publishing:

- previous observed session;
- first missing session;
- last missing session;
- next observed session.

No OHLC value, return, excess return, MAE or feature outcome is read.

## Immutable continuity source

Stage-B continuity audit:

- release:
  `research-phase1-feature-tournament-stage-b-continuity-audit-v1`;
- archive:
  `feature-tournament-stage-b-continuity-audit-v1.tar.gz`;
- SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`;
- source event-horizon rows: 96,760;
- frozen unresolved rows: 210;
- frozen unresolved `long_internal_gap` rows: **155**.

## Frozen market-presence corpus

Release: `research-market-alpaca-v1`.

Pinned archive digests:

- 2016: `sha256:df531881b67f9f42e40b2c2fff03f6ca19c0b5f9b13deb6190132b7987fb69ca`;
- 2017: `sha256:7515a3807249bbead7cf7edc2a2aa1d267b01fc49ddf72885c40746520e762d0`;
- 2018: `sha256:4a99eafc6cac31ee30d23bf82c1feccb4bbe14919f7c4df2d59e792f8a5b2f54`;
- 2019: `sha256:c701d559a7d5128fd07ec19e2d5d3b39eb5ae8c0d9bd51a8b278d34c9b6f9238`;
- 2020: `sha256:5577a548576e81c5e468b9e5027c9a8ec1ba8e1dd14ed38a0f223e797c5358e2`;
- 2021: `sha256:550ff3456ad16a045692a5d9d567d13ef2b8788283f4c39c3baa5d8aecd7a704`;
- 2022: `sha256:8a71037090cda77bc3937409ffa9fcb9c463545b5f3a7d9a73995a92759d187a`.

Only these presence fields may be read:

- date;
- ticker;
- volume;
- trade_count;
- terminal_candidate.

The diagnostic code ignores price fields entirely.

## Frozen diagnostic rule

The existing
`scripts/research_phase1_security_gap_diagnostics.py` algorithm must:

1. select only rows with
   `state=UNRESOLVED_CONTINUITY`,
   `resolutionSource=long_internal_gap`, and the frozen long-gap flag;
2. reproduce `maxInternalGapSessions` from regular observed XNYS sessions;
3. fail closed if the recomputed maximum differs from the ledger;
4. require both an observed session before and after the maximum gap;
5. preserve the 2023+ seal.

## Progression boundary

This stage applies **zero** continuity resolutions.

A successful release authorizes the next long-gap validator to combine exact
gap intervals with already-frozen primary identity evidence for only the seven
`LONG_GAP_PRIOR_SECURITY_CANDIDATE` rows:

- CKX: 4 rows;
- LOV: 1 row;
- CMCT: 1 row;
- NSEC: 1 row.

The other ten long-gap rows remain new-primary-evidence scope:

- AVGR: 3;
- HMG: 2;
- OAS: 3;
- SNES: 2.

Feature outcomes, validation and 2023+ OOS remain closed.
