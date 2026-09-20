# Phase-1 B3 multi-class/reorganization primary-source resolution gate

Frozen: 2026-09-20 after the exact residual-55 scope was frozen and before any
row in this identity-specific 12-row subset is resolved.

## Exact scope

This gate applies only to the following residual-55 issuer/ticker identities:

- CIK 0001635193 — GGO — 8 rows
- CIK 0001471824 — TAGS — 1 row
- CIK 0001647088 — EAGL — 2 rows
- CIK 0001697152 — FMCIU — 1 row

Exact 12-row key SHA-256:

`sha256:d9103eb5d9b5e04e18f955f4f6361ba39932ad285dff823a1046f72b613c2e91`

No other residual row may be resolved by this gate.

## Frozen identity-specific semantics

### GGO — same common security, separate preferred class

Primary SEC evidence establishes that The Gabelli Go Anywhere Trust had common
shares and Series A Preferred Shares as separate securities after the 2016
combination period. The common and preferred began trading separately on
2016-11-02. A later insider-reporting symbol of `GGO.A` therefore identifies
the preferred class and does not establish that the original `GGO` common
shares changed ticker or ceased to exist.

All eight GGO rows resolve to:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- successor symbol `GGO`
- 1.0 shares per entry share
- 0 cash consideration

### TAGS — same series security inside a multi-series trust

Teucrium Commodity Trust is a series trust containing distinct funds including
`CORN` and the Teucrium Agricultural Fund `TAGS`. Primary SEC reports in
2019 continue to identify TAGS as its own series issuing its own shares. A Form
3/4/5 issuer-level reporting symbol of CORN therefore does not establish that
the TAGS series was converted into CORN.

The single TAGS row resolves to:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- successor symbol `TAGS`
- 1.0 shares per entry share
- 0 cash consideration

### EAGL — one-for-one domestication and symbol continuation to WSC

Primary SEC evidence states that Double Eagle's Class A ordinary shares
automatically converted by operation of law, one-for-one, into WillScot Class A
common stock in the domestication. Holders retained the same proportional
equity interest. WillScot common began trading under `WSC` on 2017-11-30.

The two EAGL rows resolve to:

- `SYMBOL_CHANGED_SAME_SECURITY`
- `SYMBOL_CHANGED_SAME_SECURITY`
- effective symbol date 2017-11-30
- successor symbol `WSC`
- 1.0 successor share per entry share
- 0 cash consideration

### FMCIU — complete unit holder value not representable by frozen share/cash schema

Forum Merger units consisted of:

- one Class A common share;
- one right to receive 0.1 common share upon the business combination; and
- one-half warrant.

At the 2018-02-22 business combination the unit was separated/suspended, the
right converted into 0.1 common share, and the common/warrant continued as
`CVON` and `CVONW`.

The frozen continuity protocol forbids silently discarding a warrant or
pretending the original unit became only one common share. The existing
resolution schema carries successor-share quantity plus cash, but does not
carry a separately valued warrant leg. Therefore the single FMCIU row resolves
conservatively to:

- `DISCONTINUOUS_NO_COMPLETE_VALUATION`
- effective date 2018-02-22
- no same-ticker or common-only stitch
- no imputed zero return
- no corrected outcome until a separately frozen protocol can completely value
  all holder consideration

## Performance-blind boundary

This gate may not inspect prices, raw/excess returns, MAE, tail membership,
robustness output, validation data or 2023+ OOS. Decisions are based only on
security identity and primary corporate-action terms.

## Fail-closed behavior

Any mismatch in the exact 12 keys, issuer identity, security class/series,
one-for-one EAGL terms, or FMCIU unit composition fails the gate. No generic
ticker-change or same-CIK rule is permitted.
