# Phase-1 F2 validation CBTX symbol-change continuity gate

Frozen: 2026-09-22 after immutable residual-11 scope and before any validation
outcome is read.

## Source

Release:
`research-phase1-insider-feature-tournament-validation-residual11-scope-v1`.

Asset:
`validation-residual11-scope.json`.

SHA-256:
`sha256:9f240f9c4fd4f565449ef5261d6a696bc70beb9725213f4a7c5f73d01781915d`.

Exact row:
- eventNumber: 7087;
- issuer CIK: 0001473844;
- ticker: CBTX;
- evaluationSession: 2022-06-08;
- entrySession: 2022-06-09;
- horizon: 126;
- targetExitSession: 2022-12-08;
- action ID: `a3cb78f9-b741-4301-93d4-6bfa64c30882`;
- action type: `name_changes`.

Single-row semantic-key SHA-256:
`sha256:a8705b17cd9f57eab966148e2ecaef12126e7010698ee812090b26151bed0e75`.

## Primary SEC evidence

Merger effective date: **2022-10-01**.

Primary evidence:
- Stellar/CBTX closing Form 8-K, accession
  `0001104659-22-104952`;
- CBTX/Stellar Q3 2022 Form 10-Q, accession
  `0001558370-22-015589`.

The filings establish:
1. Allegiance Bancshares merged **into CBTX**.
2. CBTX was the surviving legal corporation.
3. At the effective time CBTX changed its name to Stellar Bancorp, Inc.
4. The public ticker changed from CBTX to **STEL**.
5. The 1.4184 exchange ratio applied to Allegiance common shares, not to
   pre-existing CBTX shares.

Therefore an original CBTX common holder remains in the same surviving common
security, under the new symbol STEL, one-for-one.

## Frozen resolution

- resolutionDecision: `SYMBOL_CHANGED_SAME_SECURITY`;
- transformationKind: `SAME_SECURITY_SYMBOL_CHANGE`;
- resultState: `SYMBOL_CHANGED_SAME_SECURITY`;
- successorSymbol: `STEL`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`;
- sourceActionIds: exact frozen name-change action ID;
- effectiveDate: `2022-10-01`;
- evidenceClass: `PRIMARY_SEC_SURVIVING_CORPORATION_SYMBOL_CHANGE`;
- classificationSource: `VALIDATION_PRIMARY_CBTX_STEL_SYMBOL_CHANGE`.

The Allegiance 1.4184 exchange ratio must not be applied to a historical CBTX
holder.

## Expected residual

Exactly one row is resolved. Expected unresolved continuity after this stage:
**10 long-gap rows**.

## Boundary

performanceRead=false; priceFieldsRead=[]; featureOutcomesRead=false;
validationOpened=false; validationPerformanceOpened=false; oosOpened=false;
productionScoringChanged=false.

Validation performance remains blocked until all 10 long-gap rows are resolved.
