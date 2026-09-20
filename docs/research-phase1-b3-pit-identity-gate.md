# Phase-1 B3 PIT identity-attachment gate

Status: **PREDECLARED BEFORE B3 DEVELOPMENT OUTCOMES**  
Date: **2026-09-20**  
Scope: attach historical ticker identity to the frozen B3 pre-outcome events.  
Performance/price fields: **prohibited**.  
2023+ OOS: **sealed**.  
Production scoring: unchanged.

## Frozen source

Pre-outcome event construction:

- release: `research-phase1-b3-event-construction-v1`;
- retained events: **35,829**;
- source asset SHA-256:
  `839326d9ce1d3000a476b1d483a71a6501921c58d8012ba4daba4a09cd3d2610`.

Authoritative P/S reconciliation:

- release: `research-phase1-b3-ps-reconciliation-v1`;
- source asset SHA-256:
  `8fe6707768b7703b2d8b8b8ec1f270c7202710a388739d02d91ddf809483a665`.

Definition: `research/b3-pit-identity-attachment-v1.json`.

## Performance-blind signal-lineage verification

For every frozen B3 event, reconstruct the active qualified P/S state at its
`knowledgeBoundaryAt` from the reconciled revision history using the same:

- lifecycle validFrom/validTo rule;
- 30-calendar-day economic-event window;
- qualified BUY/SALE rule;
- companyEconomicKey dedup;
- latest valid revision semantics.

The reconstructed buy and sale dollars must exactly equal the frozen event's
`buyDollars` and `saleDollars`.

A mismatch is a hard failure, not an attrition bucket.

## Historical ticker evidence

Ticker evidence may come only from issuer.ticker values present on reconciled
rows that are PIT-active inside the event's frozen B3 state.

Rules:

- no current ticker lookup;
- no future filing lookup;
- no fuzzy issuer/ticker mapping;
- placeholders `NA` and `NONE` are not real tickers;
- exactly one real ticker is required for identity eligibility;
- zero real tickers -> explicit `MISSING_REAL_TICKER` attrition;
- multiple real tickers -> explicit `MULTIPLE_REAL_TICKERS` attrition.

## Cross-issuer collision rule

After provisional ticker attachment, if the same ticker +
`evaluationSession` maps to more than one issuer CIK, all affected events are
quarantined as `TICKER_SESSION_CIK_COLLISION`.

No collision is resolved by choosing the issuer with better coverage or later
performance.

## Gate outputs

- identity-eligible event JSONL;
- explicit identity-quarantine JSONL;
- coverage and reason counts;
- annual eligible counts;
- exact signal-lineage verification flag.

Required flags:

- currentTickerFallbackUsed=false;
- fuzzyIdentityMatchingUsed=false;
- marketPricesRead=false;
- returnsRead=false;
- developmentPerformanceComputed=false;
- validationPerformanceComputed=false;
- oosOpened=false;
- productionScoringChanged=false.

Only after this gate passes may identity-eligible B3 events be joined to the
bounded 2016-2022 market dataset for development outcomes.
