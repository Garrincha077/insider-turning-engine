# Phase-1 B3 residual all-Form345 identity corroboration

Status: **FROZEN BEFORE EXECUTION**  
Date: **2026-09-20**

Purpose: fill identity-evidence gaps left by the priced P/S PIT subset without
opening any new period or performance field.

Frozen source residual/title evidence:

- release: `research-phase1-b3-residual-sec-title-v1`;
- asset:
  `b3-residual-sec-title-corroboration.json`;
- SHA-256:
  `f065a343437aa2499ea614de53bfea6c7a9dc852c7e1e77f69656ecea6e68eba`.

SEC source is the already frozen official Form 3/4/5 quarterly-bulk history
used upstream by B3:

- history run: `34883719192`;
- years: 2016–2022 only;
- exact annual artifact digests are pinned in the workflow.

Read fields are restricted to the SUBMISSION table:

- ACCESSION_NUMBER;
- FILING_DATE;
- DOCUMENT_TYPE;
- ISSUERCIK;
- ISSUERNAME;
- ISSUERTRADINGSYMBOL.

No transaction table, OHLC, return, MAE or 2023+ source is read.

Because the bulk dataset exposes filing date rather than exact acceptance time,
this evidence is marked `FILING_DATE_ONLY` and remains corroborative. It does
not independently authorize a continuity-state change.
