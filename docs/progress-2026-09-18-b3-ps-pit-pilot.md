# Phase-1 B3 P/S PIT pilot — PASS

Date: **2026-09-18**  
Workflow run: **35282934646**  
Artifact: `phase1-b3-ps-pit-pilot-35282934646`  
Artifact id: **10524833187**  
Artifact digest: `sha256:0ddaff2b57329c29537146fe3ec7fb5c4c19127b543dd08f85965c5653b33aa1`  
Pilot commit: `2f23a30ff27cb9f4952b66f28a1452be8e380f1c`

## Gate result

**P/S PIT scale pilot: PASS.**

The frozen 2016-Q1 pilot completed successfully without changing the predeclared >=99.5% bulk-to-canonical accession concordance threshold.

## Frozen pilot population

- original P/S candidate filings: **13,088**
- hydrated filings: **13,088**
- canonical records: **50,871**
- buy-only filings: **5,424**
- sale-only filings: **7,606**
- mixed buy/sale filings: **58**
- unique issuer CIKs: **2,904**
- unique reporting-owner CIKs: **8,395**

## Bulk-to-canonical concordance

### Buy side

- bulk buy-candidate accessions: **5,482**
- canonical-concordant accessions: **5,482**
- missing accessions: **0**
- concordance: **100.00%**
- qualified canonical buy rows: **19,213**

### Sale side

- bulk sale-candidate accessions: **7,664**
- canonical-concordant accessions: **7,664**
- missing accessions: **0**
- concordance: **100.00%**
- qualified canonical sale rows: **19,056**

Both sides exceeded the frozen **99.5%** threshold without changing the rule after observing results.

## Data-quality gates

All passed:

- complete accession coverage;
- zero hydration/parser failures;
- unique transaction IDs;
- unique revision IDs;
- unique exact SEC row identities;
- `knowledgeAt == acceptedAt`;
- sale-only filings present;
- no 2023+ evidence;
- production scoring unchanged.

The historical parser applied the already-audited legacy transaction-date normalization in **32 filings / 56 values**. This did not change the frozen P/S economic classification.

## Boundary after PASS

The PASS authorizes scaling the **same acquisition contract** to 2013–2022.

It does **not** authorize B3 performance testing.

The state remains:

- `researchOnly=true`
- `fullPsHistoryComplete=false`
- `amendmentsReconciledForPsUniverse=false`
- `b3DefinitionFrozen=false`
- `b3Eligible=false`
- `oosOpened=false`
- `productionScoringChanged=false`
- `canonicalReady=false`
- `signalReady=false`

## Next gate

Build the complete original P/S PIT history for **2013 Q1 through 2022 Q4** from the already frozen SEC bulk source artifacts, using this pilot artifact as the immutable scale authorization.

After all 40 quarters pass, run the separately predeclared broader P/S amendment-reconciliation gate before freezing or evaluating the actual B3 company-net-buying rule.
