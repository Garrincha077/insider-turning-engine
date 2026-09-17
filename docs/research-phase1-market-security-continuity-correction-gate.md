# Phase-1 market security-continuity correction gate

Frozen: 2026-09-17, after the top-10 security-continuity verification and **before recomputing any B1/B2/B4 development outcome with corrections**.

This gate is a data-validity protocol, not a new signal definition. It applies symmetrically to the full development event cohort, including winners and losers. It must not use realized return magnitude to decide whether an event is corrected or excluded.

## Trigger for this gate

The frozen top-tail verification found:

- two clear same-ticker/security-discontinuity cases (`OAS`, `AI`);
- one non-1:1 holder transformation (`LOV`, 10 old shares -> 1 successor ADS);
- seven continuous cases;
- no deterministic date/price sanity failures in the frozen top-59 set.

The existing market backfill requests Alpaca daily bars with `adjustment=all` and `asof=-`. Alpaca documents `all` as applying split, cash-dividend and spin-off adjustments, while `asof=-` disables symbol mapping. Therefore this gate must not double-adjust ordinary splits/dividends/spin-offs, but it must explicitly handle issuer/security identity changes, merger consideration, cancellation and ticker reuse.

## Frozen scope

- signal selection: unchanged B0/B1/B2/B4 event sets;
- development evaluation sessions: 2016-2020 only;
- outcome market data: through 2022 only;
- primary horizon: 126 XNYS sessions;
- secondary horizons: 21, 63 and 252 sessions;
- 2023+ OOS remains sealed;
- production scoring remains unchanged;
- correction decisions are based on corporate-action/security identity, never realized performance.

## Corporate-action source hierarchy

For cohort-wide machine-readable screening, use the Alpaca corporate-actions endpoint for 2016-2022 where available, including:

- `reverse_split`;
- `forward_split`;
- `unit_split`;
- `cash_dividend`;
- `stock_dividend`;
- `spin_off`;
- `cash_merger`;
- `stock_merger`;
- `stock_and_cash_merger`;
- `redemption`;
- `name_change`;
- `worthless_removal`;
- `rights_distribution`.

For identity-changing or ambiguous cases, primary SEC/exchange/issuer evidence controls over provider labels.

## Frozen performance-blind screening triggers

The pre-performance ledger must screen **every retained event/horizon** using only identity, dates, corporate actions and market-bar availability. It must not load or inspect `raw_*`, `excess_*`, MAE or any realized-performance field.

### Provider corporate-action trigger

An event/horizon becomes an affected candidate when an Alpaca corporate action whose effective/process date falls strictly after entry and on or before the target exit is associated with the event ticker/security and is one of:

- `unit_split`;
- `stock_dividend`;
- `cash_merger`;
- `stock_merger`;
- `stock_and_cash_merger`;
- `redemption`;
- `name_change`;
- `worthless_removal`;
- `rights_distribution`.

`forward_split`, `reverse_split`, `cash_dividend` and `spin_off` alone do **not** make an event affected because the frozen market feed already uses Alpaca `adjustment=all`. They are still counted in diagnostics.

A `name_change` with identical old/new CUSIP is initially a `SYMBOL_CHANGED_SAME_SECURITY` candidate. Merger/redemption/worthless/removal and changed-CUSIP actions require holder-consideration/identity resolution before performance is read.

### Long internal market-gap trigger

The provider corporate-action feed is known not to contain every cancellation/reorganization case. Therefore an independent, return-blind ticker-continuity screen is also frozen.

For each event/horizon:

1. use the XNYS calendar from the canonical entry session through the canonical target exit session;
2. inspect only whether an adjusted daily bar exists for the event's original ticker on each XNYS session;
3. find internal gaps bounded by an observed bar before and an observed bar after the gap;
4. if an internal gap contains **10 or more consecutive XNYS sessions without a bar**, mark the event/horizon `LONG_INTERNAL_TICKER_GAP_CANDIDATE`;
5. the gap trigger does not itself classify the security as invalid; absent authoritative resolution it maps to `UNRESOLVED_CONTINUITY` and blocks performance recomputation.

The threshold of 10 XNYS sessions is frozen before scanning the full cohort. It is not chosen from corrected returns. Its purpose is to catch delisting/relisting, old-symbol reuse and cancellation/reissue patterns such as the already verified OAS/AI cases while avoiding ordinary one-day/non-trading noise.

### Verified regression fixtures

The top-10 verification record may resolve its already frozen cases in tests/ledger output, but it may not be used as a hand-picked detection universe. In particular:

- OAS must never chain old common to reorganized new common;
- AI/Arlington must never chain to later C3.ai `AI` prices;
- LOV must retain the documented 10:1 holder exchange;
- HEAR must remain split-adjusted, not receive a second 4:1 correction.

All other events are processed by the same provider-action and long-gap rules.

## Frozen event classifications

Each event/horizon receives exactly one outcome-continuity state:

1. `PRICE_CONTINUOUS_ADJUSTED`
   - same economically continuous common security through the target exit;
   - or only split/dividend/spin-off actions already covered by Alpaca `adjustment=all`;
   - use canonical adjusted market prices without another adjustment.

2. `SYMBOL_CHANGED_SAME_SECURITY`
   - same issuer/economic security continues under a new symbol;
   - stitch the old and successor symbols using authoritative effective date/security identity;
   - never use a later reused old ticker.

3. `TRANSFORMED_HOLDER_CONSIDERATION`
   - merger/exchange/reorganization transforms the entry security and entry holders receive identifiable cash and/or successor securities;
   - value the actual holder consideration, not a one-for-one same-ticker chain.

4. `DISCONTINUOUS_NO_COMPLETE_VALUATION`
   - entry security is canceled/extinguished/reused and complete holder consideration cannot be valued deterministically with the frozen evidence contract;
   - outcome is marked missing for data-validity reasons, not set to zero and not replaced by the later same-ticker price.

5. `UNRESOLVED_CONTINUITY`
   - evidence is insufficient/contradictory;
   - outcome remains missing until resolved; never fall back to a naive same-ticker chain.

## Frozen holder-basis valuation rules

The target horizon remains the original XNYS target exit session.

### Continuous adjusted security

Use the existing Alpaca adjusted open/close path. Do not separately apply split, cash-dividend or spin-off factors already represented by `adjustment=all`.

### Pure symbol/name change

Continue the same economic security under the successor symbol at the authoritative effective date. The target exit session does not change.

### Stock exchange / stock merger

For one entry share, carry the documented exchange ratio into successor shares. At the target exit session, value the successor share quantity using the same adjusted market-data convention. Fractional-share cash terms are included only when deterministically documented.

### Cash merger / redemption before target exit

For one entry share, use the documented cash consideration on the effective/settlement date and carry that cash at **0% nominal return** through the original target exit session. This is a measurement convention, not an investment reinvestment assumption.

### Stock-and-cash transformation

Carry both components: documented cash consideration at 0% after receipt plus documented successor-share quantity valued at the original target exit session.

### Cancellation / bankruptcy / worthless removal

Do not connect entry common to later new/reorganized common merely because the ticker or issuer name is similar. If old holders receive warrants, rights or other securities, value them only if the exact distribution ratio and a valid market value through the target exit are available under this frozen protocol. Otherwise classify `DISCONTINUOUS_NO_COMPLETE_VALUATION` and leave the outcome missing.

## Benchmark and excess-return rule

- Keep the canonical entry session and canonical target exit session for each horizon.
- SPY benchmark return remains the canonical adjusted SPY return over those same sessions.
- Corrected raw holder return = terminal holder value at target exit / canonical entry holder value - 1.
- Corrected excess return = corrected raw holder return - canonical SPY return.
- A corporate action must never move the signal/evaluation date or use future information to change event selection.

## Identity safeguards

A ticker string alone is never a security identifier.

For every identity-changing action, the correction ledger must preserve at minimum:

- event issuer CIK;
- original ticker;
- effective/process date;
- action type;
- successor ticker where applicable;
- successor issuer/security identifier where available;
- exchange/consideration terms;
- evidence source;
- deterministic classification.

If the old ticker later maps to a different issuer/security, later prices under that ticker are forbidden for the original event.

## Cohort-wide anti-selection rule

The correction detector runs over **all retained development events before looking at corrected performance**. It must output counts/identities of affected events first. Only after that ledger is frozen may corrected B1/B2/B4 horizon metrics be computed.

No rule may refer to:

- top-tail membership;
- realized gain/loss;
- development year performance;
- a hand-picked ticker/issuer list;
- whether the correction improves or worsens B1.

The already verified top-10 cases are regression fixtures only; they do not define the universe of corrections.

## Required pre-performance outputs

Before recomputing returns, persist a deterministic continuity ledger and summary containing:

- total retained events scanned;
- affected events by action type and continuity state;
- unique affected issuers/tickers;
- affected counts by development year;
- long internal gap counts/distribution;
- unresolved count;
- source coverage diagnostics;
- explicit `performanceRead=false` for this screening stage;
- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

Regression tests must include at least:

- OAS -> discontinuous/canceled; no successor-common chaining;
- AI/Arlington -> symbol changed to AAIC and old `AI` ticker reuse by C3.ai must not be chained;
- LOV -> 10:1 old-common-to-successor-ADS transformation;
- HEAR -> split remains price-continuous because adjusted bars already handle it;
- a synthetic >=10-XNYS-session internal gap -> unresolved candidate;
- a shorter gap -> not affected by the gap rule;
- a normal unaffected security -> price-continuous;
- any 2023+ evidence/date -> hard failure.

## Performance stage remains blocked

Do not recompute corrected B1/B2/B4 performance until the full cohort continuity ledger has been generated and frozen without reading corrected performance. The first performance rerun after that freeze must retain both the original canonical metrics and corrected metrics side-by-side and must not relabel a signal as alpha or production-ready.
