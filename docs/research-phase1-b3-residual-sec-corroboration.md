# Phase-1 B3 residual bounded-SEC corroboration gate

Status: **FROZEN BEFORE EXECUTION**  
Date: **2026-09-20**

Source residual:

- candidate release: `research-phase1-b3-continuity-candidates-v1`;
- candidate asset SHA-256:
  `806f49b3cc557f7989268f1214914efb6b587c783f270095a1d9546374a574f6`;
- residual rows: **162**.

Bounded SEC source:

- release: `research-sec-ps-pit-v1`;
- only 2016Q1 through 2022Q4 archives are downloaded;
- each quarter has already passed complete original P/S accession coverage,
  zero-failure hydration, and `knowledgeAt == acceptedAt`;
- 2023+ archives do not enter this run.

For each residual continuity row, this gate records the nearest same-issuer
original P/S filing before and after the frozen continuity pivot.

- long-gap pivot: the already frozen `firstMissingSession`;
- provider ambiguity pivot: earliest bounded corporate-action date in the frozen
  action set.

Recorded identity evidence is limited to issuer CIK, filing-time ticker,
acceptance/knowledge timestamp and accession.

This stage is **corroboration only**. Even
`EXPECTED_TICKER_BOTH_SIDES` cannot by itself prove holder continuity across a
bankruptcy, recapitalization, cancellation or replacement security.

Therefore this gate:

- changes zero continuity states;
- creates no final resolution contract;
- reads no returns, MAE or OHLC prices;
- opens no validation or 2023+ OOS;
- cannot open corrected B3 performance.
