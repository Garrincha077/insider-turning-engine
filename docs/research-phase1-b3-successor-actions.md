# Phase-1 B3 successor corporate-action evidence expansion

Status: **FROZEN BEFORE EXECUTION**  
Date: **2026-09-20**

The original B3 continuity ledger queried corporate actions for the canonical
event ticker only. Bounded SEC PIT corroboration subsequently identified
historical ticker changes across 36 residual rows.

This gate expands the corporate-action query **only** to ticker symbols already
present in the frozen SEC corroboration artifact:

- source release: `research-phase1-b3-residual-sec-corroboration-v1`;
- source asset SHA-256:
  `702784fc368b4e5def9fe4cdeb83c6120920431a4a33e1f9843467c9cd599e0e`.

No ticker is added from current market data, realized returns, web search or
2023+ evidence.

The existing `research_market_corporate_action_inventory.py` is reused
unchanged:

- start: 2016-01-01;
- end: 2022-12-31;
- same frozen corporate-action types;
- `performanceRead=false`;
- `oosOpened=false`.

The result is evidence-only. It does not change continuity state, create a final
resolution contract or open corrected performance.
