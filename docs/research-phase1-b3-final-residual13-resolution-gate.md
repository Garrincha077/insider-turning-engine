# Phase-1 B3 final residual-13 primary-source resolution gate

Frozen: 2026-09-20 after the exact residual-13 scope was frozen and before any
corrected B3 performance is opened.

## Exact scope

This gate applies to every row in `research-phase1-b3-residual13-scope-v1`:

- ARWA / CIK 0001622577 — 3 rows
- AAPC / CIK 0001630940 — 3 rows
- WYIG / CIK 0001641398 — 3 rows
- ATACU / CIK 0001680873 — 2 rows
- TPGE / CIK 0001698990 — 1 row
- NBA.U / CIK 0001823882 — 1 row

Exact key SHA-256:

`sha256:0183d2bb7d158cfa642cb02106eb1937d7e0a327db9e23efb4423188b13c5a18`

No row outside this scope may be resolved by this gate.

## Frozen identity-specific semantics

### ARWA — ordinary share, not unit

The frozen ticker is `ARWA`, the ordinary share. It must not inherit the
ARWA-unit right or warrant components.

The December 28, 2016 closing filing establishes that ARWA distributed its
6,088,200 VivoPower ordinary shares among ARWA ordinary shareholders,
rightholders and warrantholders; each right produced 0.1 VivoPower share and
each warrant produced 0.05 VivoPower share. The filed counts reconcile exactly
to one VivoPower share per surviving ARWA ordinary share. VVPR began Nasdaq
trading December 29, 2016.

Therefore:

- target 2016-09-30: same ARWA ordinary share;
- targets 2016-12-30 and 2017-07-03:
  `TRANSFORMED_HOLDER_CONSIDERATION`, effective 2016-12-28,
  successor `VVPR`, 1.0 share per ARWA share, 0 cash.

### AAPC — same ordinary share despite delisting

The proposed Kalyx merger was terminated on October 5, 2017 and never closed.
AAPC ordinary shares were delisted from Nasdaq on/after October 5, but later SEC
filings continue to identify the same outstanding AAPC ordinary shares.

All three rows resolve `SAME_SECURITY_CONTINUITY`. Delisting is not a holder
transformation and must not create a synthetic target price.

### WYIG — same common share through all scoped targets

The frozen security is JM Global common stock `WYIG`, not unit `WYIGU`.
All three scoped targets precede the February 6, 2018 Sunlong business
combination. SEC filings in August 2017 still identify WYIG common stock.

All three rows resolve `SAME_SECURITY_CONTINUITY`.

### ATACU — unit before closing, 1.1 HFFG common after closing

Each ATACU unit consisted of one Atlantic common share plus one right that
automatically received 0.1 common share upon the initial business combination.
The HF Foods combination closed August 22, 2018; units and rights ceased
trading, and Atlantic common continued under `HFFG` beginning August 23.

Therefore:

- target 2018-02-28: same ATACU unit;
- target 2018-08-28:
  `TRANSFORMED_HOLDER_CONSIDERATION`, effective 2018-08-22,
  successor `HFFG`, 1.1 common shares per ATACU unit, 0 cash.

### TPGE — same Class A common, symbol TPGE -> MGY

The frozen ticker `TPGE` is Class A common stock, not unit `TPGE.U`.
Magnolia filings state that Class A common traded as TPGE through July 30,
2018 and thereafter as `MGY`; the unit was a separate security.

The sole row resolves `SYMBOL_CHANGED_SAME_SECURITY`, effective 2018-08-01,
successor `MGY`, 1.0 share, 0 cash.

### NBA.U — multi-component holder consideration

Each NBA.U unit contained one NBA common share plus one public warrant.
The August 13, 2021 Airspan combination changed the registrant name, units
ceased, the common continued as `MIMO`, and the original public warrants
continued as `MIMO WS` with their warrant terms unchanged.

The sole NBA.U row therefore resolves to a deterministic two-component basket:

- 1.0 MIMO common share; plus
- 1.0 MIMO WS public warrant.

This is `TRANSFORMED_MULTI_COMPONENT_CONSIDERATION`, effective 2021-08-13.
The warrant component must not be discarded. Corrected performance may value
the basket only if both exact target-session component values are available
under the frozen market-data rules; otherwise the event remains explicitly
not completely valued, not imputed.

## Performance-blind boundary

This gate may not inspect realized prices, returns, MAE, tail membership,
robustness output, validation outcomes, or 2023+ OOS.

## Completion rule

A green run must classify all 13 exact rows. This makes the continuity
classification unresolved count zero, but it does **not** itself open corrected
performance. A separate final continuity-contract gate must first combine all
264 frozen resolution rows and validate exact key coverage.
