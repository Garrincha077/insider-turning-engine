# Phase-1 security continuity ledger checkpoint

Frozen: 2026-09-17 after successful workflow run `35272112415` at main commit `3516ba5cf3737e5782714d820667f8a8852b89c6`, before any corrected performance recomputation.

## Provenance and invariants

- workflow artifact: `phase1-security-continuity-ledger-35272112415`
- artifact id: `10519701567`
- artifact digest: `sha256:7e67aa271d60f8f3837e3db76f3a8a0e20312fdea5baf7f031e387d25349c4b8`
- period: 2016-01-01 through 2022-12-31
- 2023+ OOS opened: **false**
- performance read during continuity screening: **false**
- production scoring changed: **false**
- research only: **true**
- frozen long-internal-gap threshold: **10 XNYS sessions**
- frozen corporate-action scope: the predeclared 13 action types only

The CA inventory successfully scanned 2,199 event tickers in 50 requests and retained 32,842 bounded provider corporate-action records.

## Whole-cohort ledger result

The performance-blind ledger scanned **6,094 B1 event rows** and generated **24,376 event-horizon rows**.

Continuity-state counts:

| State | Event-horizon rows |
| --- | ---: |
| `PRICE_CONTINUOUS_ADJUSTED` | 24,199 |
| `SYMBOL_CHANGED_SAME_SECURITY` | 66 |
| `TRANSFORMED_HOLDER_CONSIDERATION` | 54 |
| `DISCONTINUOUS_NO_COMPLETE_VALUATION` | 3 |
| `UNRESOLVED_CONTINUITY` | 54 |

A total of **105 unique events / 71 issuers / 71 tickers** were affected by at least one continuity/corporate-action flag.

At the primary 126-session horizon the states are:

- `PRICE_CONTINUOUS_ADJUSTED`: 6,051
- `SYMBOL_CHANGED_SAME_SECURITY`: 16
- `TRANSFORMED_HOLDER_CONSIDERATION`: 12
- `DISCONTINUOUS_NO_COMPLETE_VALUATION`: 1
- `UNRESOLVED_CONTINUITY`: 14

The corrected-performance stage remains **blocked** because unresolved continuity rows remain. No corrected B1/B2/B4 result has been read or computed at this checkpoint.

## Unresolved set frozen before resolution

There are **54 unresolved event-horizon rows**, representing **31 unique B1 events across 18 tickers**.

Breakdown by resolution trigger:

- 34 rows: `long_internal_gap` with no identity-changing provider action in the canonical window;
- 18 rows: provider `stock_dividends` requiring holder-basis/adjustment treatment to be resolved under the frozen protocol;
- 2 rows: both `cash_mergers` and `stock_mergers` in the same window, requiring deterministic transaction-term resolution.

Frozen unresolved ticker inventory:

- `BOTJ`: events 5580, 5892; provider stock dividend
- `CMCT`: event 5550; 19-session internal gap
- `DGICB`: event 471; 10-session internal gap
- `FG`: event 4127; cash + stock merger actions
- `GIX.U`: event 3846; 24-session internal gap
- `GNTY`: events 4605, 4976, 5285, 5477, 5759, 5889; provider stock dividend
- `HWBK`: events 4143, 5315, 5556, 5726; provider stock dividend
- `IPAS`: event 2242; 11-session internal gap
- `JXSB`: event 50; 12-16-session internal gaps
- `KMPH`: event 4789; 160-session internal gap
- `LARK`: event 2000; provider stock dividend
- `LMFA`: event 38; 14-33-session internal gaps
- `MGYR`: event 3137; 10-session internal gap
- `NEN`: events 1800, 2383; 12-session internal gap
- `NSEC`: events 2799, 3539, 3893; 12-session internal gap
- `POPE`: event 3898; cash + stock merger actions
- `SBE.U`: event 3970; 11-17-session internal gaps
- `VBFC`: events 2173, 2542; 10-11-session internal gaps

## Next gate

Resolve the frozen unresolved set using only security identity, corporate-action terms, bounded market-session presence and primary SEC/exchange/issuer evidence. Realized `raw_*`, `excess_*` and `mae_*` values must remain unread while these classifications are decided.

Only after the unresolved set is deterministically classified and the resulting resolution ledger is frozen may corrected development performance be recomputed. Any remaining evidence ambiguity must stay `UNRESOLVED_CONTINUITY`; the rule or threshold must not be loosened to improve B1 results.
