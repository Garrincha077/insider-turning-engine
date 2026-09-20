# B3 continuity resolution candidate policy

Status: **FROZEN BEFORE CANDIDATE GENERATION**  
Date: **2026-09-20**

This stage does not create a final continuity overlay and does not open corrected
performance. It reduces the frozen unresolved scope only where continuity terms
are already deterministic from performance-blind evidence.

Permitted evidence:

1. direct provider corporate-action terms from the frozen 2016–2022 inventory;
2. the already frozen B1 continuity-resolution contract, but only for the same
   issuer/security evidence and only when the B3 event horizon contains the same
   effective continuity fact.

Direct provider candidate rules:

- one stock-dividend action with positive explicit rate -> same ticker,
  transformed holder quantity equal to the provider rate;
- paired cash + stock merger on the same effective date -> preserve both the
  successor-share ratio and cash per entry share;
- a same-CUSIP name change paired with a 1:1 stock action -> same security,
  successor symbol from the name-change record.

A name change with a changed CUSIP and no independent continuity evidence stays
unresolved.

Prior B1 evidence reuse is allowed because the B1 contract was frozen without
B3 performance. It may not be generalized to a different issuer/security or to
a different ambiguous continuity fact.

Every unmatched row remains in a residual unresolved list. No threshold is
changed and no B3 raw/excess/MAE value is read.
