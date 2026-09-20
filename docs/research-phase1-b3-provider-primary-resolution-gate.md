# Phase-1 B3 provider-ambiguity primary-source resolution gate

Frozen: 2026-09-20 after the exact residual-91 scope was frozen and before any
provider-ambiguity continuity state is changed.

## Scope

This gate applies only to the four residual rows whose frozen source is
`provider` and whose residual reason is
`PROVIDER_AMBIGUOUS_REQUIRES_PRIMARY_EVIDENCE`.

The four rows reduce to two issuer/security facts:

- CIK 0001679688, CLNY -> DBRG, effective trading-symbol change 2021-06-22
- CIK 0001717547, CLNC -> BRSP, effective trading-symbol change 2021-06-25

No other residual row may be resolved by this gate.

## Primary-source hierarchy

The official issuer Form 8-K filed with the SEC controls over the provider's
name-change/CUSIP fields.

A row may be classified `SYMBOL_CHANGED_SAME_SECURITY` only when all of the
following are established by the pinned official filing:

1. the SEC registrant CIK is unchanged;
2. the filing identifies the post-change company as the same corporation
   formerly known by the old company name;
3. the affected listed class remains Class A common stock;
4. the filing states that the trading symbol changes from the frozen old symbol
   to the successor symbol in connection with the corporate name change;
5. there is no holder exchange ratio, cash consideration, cancellation,
   redemption, merger consideration, or successor-holder transformation in
   that name-change event;
6. the effective symbol date is strictly after entry and on/before the target
   exit;
7. all evidence dates are before 2023.

A CUSIP change alone does not force a holder transformation when the official
filing establishes the same registrant, same corporation and same listed
security class continuing under a new corporate name/ticker. The official SEC
CUSIP, if stated, is authoritative over a conflicting provider field.

## Frozen resolution semantics

Qualifying rows are resolved as:

- `resolutionDecision=SYMBOL_CHANGED_SAME_SECURITY`
- `resultState=SYMBOL_CHANGED_SAME_SECURITY`
- `transformationKind=SAME_SECURITY_SYMBOL_CHANGE`
- `successorSharesPerEntryShare=1.0`
- `cashPerEntryShare=0.0`
- successor symbol and effective date from the pinned SEC evidence

This stage is performance-blind and may not inspect market prices, returns,
MAE, top-tail membership, robustness output, validation, or 2023+ OOS.

## Pinned primary evidence

### Colony Capital -> DigitalBridge

SEC Form 8-K accession `0001679688-21-000065`, event date 2021-06-21.
The filing identifies DigitalBridge Group, Inc. as the registrant and Colony
Capital, Inc. as the former name, describes the Maryland corporation's charter
amendment as a name change, and states that effective 2021-06-22 the Class A
common-stock NYSE symbol changed from CLNY to DBRG. It states the new Class A
common-stock CUSIP as `25401T108`.

### Colony Credit Real Estate -> BrightSpire

SEC Form 8-K accession `0001717547-21-000024`, event date 2021-06-24.
The filing identifies BrightSpire Capital, Inc. as the same Maryland
corporation formerly known as Colony Credit Real Estate, Inc., and the filed
press-release exhibit states that the company will continue to be publicly
traded on the NYSE with trading under BRSP beginning at market open on
2021-06-25. The Class A common-stock CUSIP is `10949T109`.

## Fail-closed behavior

If the exact four frozen keys, CIKs, symbols, dates, security class, official
accessions or resolution terms do not match the evidence contract, the gate
fails. It must not infer a resolution for any additional row.

Corrected B3 performance remains closed after this gate because the other
residual continuity rows remain unresolved.
