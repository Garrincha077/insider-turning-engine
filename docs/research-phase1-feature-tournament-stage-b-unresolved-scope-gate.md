# Phase-1 feature tournament Stage-B unresolved continuity scope gate

Frozen: 2026-09-21 after the initial performance-blind continuity audit and
before any feature forward outcome was opened.

## Immutable source

Audit release:

- `research-phase1-feature-tournament-stage-b-continuity-audit-v1`
- archive:
  `feature-tournament-stage-b-continuity-audit-v1.tar.gz`
- archive SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`
- audit summary SHA-256:
  `sha256:4f2f786fed89e61ee22ffb59c43c08b739e3ea55ff1ef2cd289530c8a894007b`

The source audit is performance-blind and covers exactly 24,190 events and
96,760 event-horizon rows.

## Observed audit state

The frozen audit found:

- 96,147 `PRICE_CONTINUOUS_ADJUSTED` rows;
- 251 `SYMBOL_CHANGED_SAME_SECURITY` rows;
- 152 `TRANSFORMED_HOLDER_CONSIDERATION` rows;
- **210 `UNRESOLVED_CONTINUITY` rows**.

The unresolved count is an audit result, not a performance-selected threshold.

The audit also reported:

- 158 long-internal-gap event-horizon rows;
- 372 affected unique events;
- 223 affected unique issuers;
- 225 affected unique tickers;
- 69,175 bounded corporate-action records available.

## Scope freeze

This stage must select exactly the 210 rows whose audit state is
`UNRESOLVED_CONTINUITY` and freeze:

- eventNumber;
- issuerCik;
- historical ticker;
- evaluationSession;
- entrySession;
- horizon;
- targetExitSession;
- audit resolution source;
- candidate corporate-action types and IDs;
- adjusted action types;
- maximum internal gap;
- long-gap flag.

No raw return, SPY excess, MAE, feature outcome or later OOS field may be
present or read.

## Resolution policy

The next stage may reuse already-frozen B1/B3 continuity evidence only when it
matches the unresolved historical identity and event-horizon facts. Reuse is
evidence reuse, not outcome reuse.

Rows not covered by prior frozen evidence require new primary, performance-blind
identity/holder-transformation evidence.

Every one of the 210 rows must be deterministically classified and the final
contract must reach **zero unresolved** before discovery outcomes can be opened.

## Boundary

- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false;
- 2023+ remains sealed.
