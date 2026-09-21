# Phase-1 F2 validation HSDT long-gap interval diagnostic gate

Frozen: 2026-09-21 after the immutable validation residual-33 scope and before
any validation outcome is read.

## Source residual

Release:
`research-phase1-insider-feature-tournament-validation-residual33-scope-v1`.

Asset:
`validation-residual33-scope.json`.

SHA-256:
`sha256:0dab36d7553ec3ceb0838c79cf7ad70a85fa240686d7493930de160c55adb946`.

Frozen source scope:
- 33 unresolved validation rows;
- semantic-key SHA-256:
  `sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2`;
- exactly one `LONG_GAP_PRIOR_SECURITY_CANDIDATE`.

That row must be:
- eventNumber: 3657;
- issuer CIK: 0001610853;
- ticker: HSDT;
- entrySession: 2021-11-16;
- horizon: 126;
- targetExitSession: 2022-05-18;
- previously measured max internal gap: 29 XNYS sessions.

## Market-presence inputs

Use only the frozen adjusted Alpaca market archives:
- 2021:
  `alpaca-market-2021.tar.gz`,
  SHA-256
  `550ff3456ad16a045692a5d9d567d13ef2b8788283f4c39c3baa5d8aecd7a704`;
- 2022:
  `alpaca-market-2022.tar.gz`,
  SHA-256
  `8a71037090cda77bc3937409ffa9fcb9c463545b5f3a7d9a73995a92759d187a`.

The diagnostic may read only:
- date;
- ticker;
- volume;
- trade_count;
- terminal_candidate.

OHLC, adjusted close, VWAP and returns are not read.

## Diagnostic rule

Reproduce the exact regular-session presence definition used by the validation
continuity audit:

`terminal_candidate == false AND volume > 0 AND trade_count > 0`.

Bound observed HSDT sessions to the frozen entry/target interval. Compute every
gap between consecutive observed sessions as:

`nextObservedIndex - currentObservedIndex - 1`.

Report all intervals tied for the maximum. For each interval report:
- left observed XNYS session;
- right observed XNYS session;
- first missing XNYS session;
- last missing XNYS session;
- missing-session count.

The maximum must reproduce **29** or the diagnostic fails closed.

## Boundary

This is diagnostic only:
- resolutionApplied=false;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

The diagnostic does not authorize reuse of prior HSDT evidence. Primary
security-continuity evidence must be checked against the exact resulting gap
interval before resolution.
