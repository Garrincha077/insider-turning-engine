# Phase-1 F2 validation incomplete-stock-merger primary resolution gate

Frozen: 2026-09-22 after immutable residual-27 scope and before any validation
outcome is read.

## Source scope

Release:
`research-phase1-insider-feature-tournament-validation-residual27-scope-v1`.

Asset:
`validation-residual27-scope.json`.

SHA-256:
`sha256:04b4e2280e9059aed8c10f9a6d9ac1853f23f34f5028dba6482c014c1ff190a4`.

Source residual rows: **27**.

This gate resolves exactly the **8** rows routed as
`provider_incomplete_terms` with only a frozen `stock_mergers` action.

Eight-row semantic-key SHA-256:
`sha256:31296aeae352b58fc55a6eba4cbfaf2fa0d600134a004afcf6c7980782a5b776`.

The five frozen corporate-action identities are:

- SPRT — 2 validation rows;
- APO — 2;
- TSE — 1;
- DKNG — 2;
- AEI — 1.

## Frozen primary SEC terms

### SPRT -> GREE

Effective date: **2021-09-14**.

Primary closing evidence:
- Support.com Form 8-K, accession `0001193125-21-272911`;
- Greenidge Form 8-K, accession `0001193125-21-273493`.

At the merger effective time each outstanding SPRT common share was cancelled
and converted into **0.115** Greenidge Class A common shares, with cash only in
lieu of fractional shares.

Frozen one-entry-share holder economics:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_STOCK_MERGER`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: `GREE`;
- successorSharesPerEntryShare: `0.115`;
- cashPerEntryShare: `0`.

Fractional-share cash is not added for the frozen one-entry-share valuation.
The project values the deterministic share quantity; it does not fabricate a
fractional cash amount without the exact sale price.

### APO -> APO

Effective date: **2022-01-01**.

Primary evidence:
- Apollo/combined filing, accession `0001858681-22-000021`;
- Apollo legacy filing, accession `0001411494-21-000023`.

At the AGM merger effective time each outstanding legacy AGM Class A share was
converted automatically into **one** HoldCo share. HoldCo was renamed Apollo
Global Management, Inc. and continued publicly under APO.

Frozen holder economics:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: `APO`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`.

The separate 1.149 Athene exchange ratio does not apply to legacy APO holders.

### TSE -> TSE

Effective date: **2021-10-08**.

Primary evidence:
- Trinseo successor Form 8-K12B, accession
  `0001104659-21-124652`.

Trinseo S.A. merged into Trinseo PLC. All outstanding former Trinseo S.A.
ordinary shares, excluding treasury shares, were exchanged **one-for-one** for
Trinseo PLC ordinary shares. The successor continued to trade as TSE.

Frozen holder economics:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: `TSE`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`.

### DKNG -> DKNG

Effective date: **2022-05-05**.

Primary evidence:
- DraftKings successor filing, accession `0001883685-22-000026`;
- DraftKings/GNOG closing Form 8-K, accession
  `0001104659-22-056127`.

In the DraftKings holding-company reorganization each issued and outstanding
Old DraftKings Class A share was converted into **one** New DraftKings Class A
share. New DraftKings became the public parent and continued under DKNG.

Frozen holder economics:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: `DKNG`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`.

The 0.365 GNOG exchange ratio applies to GNOG holders, not to legacy DKNG
holders.

### AEI -> AEI

Effective date: **2022-10-04**.

Primary closing evidence:
- Alset successor Form 8-K, accession `0001493152-22-027770`.

The Delaware predecessor merged into its Texas subsidiary in a reincorporation.
Each outstanding predecessor common share automatically converted into **one**
successor Alset Inc. common share, and the successor continued to trade as
AEI.

Frozen holder economics:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: `AEI`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`.

## Resolver requirements

The resolver must verify for every row:

1. source category is `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`;
2. source resolution is `provider_incomplete_terms`;
3. candidate action types equal exactly `["stock_mergers"]`;
4. action ID equals the evidence contract for that historical ticker;
5. effective date satisfies
   `entrySession < effectiveDate <= targetExitSession`;
6. issuer CIK and ticker match the frozen evidence identity;
7. all economic terms are complete and non-negative.

Expected resolved rows: **8**.

Expected residual after this wave: **19** rows:
- 8 name-change + stock-merger/reorganization provider rows;
- 1 standalone name-change provider row;
- 10 long-gap rows.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

Validation performance remains blocked until continuity unresolved = 0.
