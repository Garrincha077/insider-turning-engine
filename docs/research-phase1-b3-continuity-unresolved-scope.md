# Phase-1 B3 frozen unresolved continuity scope

Status: **FROZEN BEFORE RESOLUTION RESEARCH**  
Date: **2026-09-20**

Authoritative performance-blind B3 continuity ledger:

- run: `35502394856`;
- release: `research-phase1-b3-continuity-ledger-v1`;
- archive SHA-256:
  `34b2a8bd2b0244b5bca8767b88623ca51d7b5a37f10f57f44a9d513445f6a95f`;
- event rows: **29,930**;
- event-horizon rows: **119,720**;
- unresolved rows: **264**.

The unresolved scope is frozen before any resolution decision:

- 200 `long_internal_gap` rows;
- 64 provider-action ambiguity rows;
- 146 unique events;
- 67 unique issuer/ticker identities.

The scope builder reads only continuity identity/provenance fields. It does not
read raw returns, SPY excess, MAE or OHLC prices.

A companion diagnostic re-runs the already frozen long-gap bracketing logic on
the 200 gap rows using only session presence, volume, trade count and terminal
flags from the bounded 2016–2022 market release.

The output key digest must be used unchanged by any B3 resolution contract.
Automatic scope expansion is prohibited.

Prior B1 continuity decisions may be reused only when the same issuer/security
evidence applies independently of B3 performance. All remaining decisions must
be supported by bounded corporate-action/SEC evidence and may not reference B3
realized returns.
