# Phase-1 B1 security-continuity / corporate-action verification gate

Frozen: 2026-09-17, after the predeclared tail-attribution audit completed and **before deciding whether any extreme event is economically valid or invalid**.

This is a development-only data-validity audit. It cannot create a performance filter, optimize B1, open 2023+ OOS, or change production scoring.

## Why this gate is required

The frozen tail-attribution audit showed that the 59 largest B1 `excess_126` observations contribute more than 100% of the full cohort signed excess, and that the largest observation alone is extremely influential. Mechanical date/price sanity checks passed, but those checks cannot detect bankruptcy equity cancellation, ticker reuse, delisting/relisting, merger consideration, spin-offs, or security replacement.

A large return is not itself evidence of bad data. Security continuity must be verified from corporate-action evidence before any return is treated as invalid.

## Frozen verification set

Primary verification set: the **10 largest observations from the already frozen global top-59 audit**, in their frozen rank order. No additional issuer is added because it looks suspicious after external research.

The set is:

1. OAS — issuer CIK `0001486159` — evaluation 2020-10-07;
2. AI — issuer CIK `0001209028` — evaluation 2020-09-24;
3. OSTK — issuer CIK `0001130713` — evaluation 2020-03-19;
4. LOV — issuer CIK `0001314475` — evaluation 2017-08-28;
5. CRDF — issuer CIK `0001213037` — evaluation 2020-05-14;
6. TST — issuer CIK `0001080056` — evaluation 2018-12-12;
7. CWEI — issuer CIK `0000880115` — evaluation 2016-04-05;
8. APPS — issuer CIK `0000317788` — evaluation 2020-03-18;
9. PEIX — issuer CIK `0000778164` — evaluation 2020-07-10;
10. HEAR — issuer CIK `0001493761` — evaluation 2017-11-17.

The verification window for each event is from its canonical entry session through its canonical 126-session exit session, inclusive.

## Evidence hierarchy

Use evidence in this order where available:

1. SEC filings by the event issuer or successor entity (8-K, 10-K, 10-Q, registration statements, bankruptcy/emergence filings);
2. exchange or FINRA corporate-action/ticker notices;
3. issuer investor-relations releases;
4. authoritative market-data/corporate-action records;
5. secondary news only to locate or corroborate primary evidence.

For every conclusion, preserve the source date and distinguish the effective corporate-action date from the publication date.

## Questions to answer for each event

1. Did the ticker on the canonical entry session refer to the event issuer CIK/security represented by the insider filing?
2. Did the ticker on the canonical exit session still refer to the same economically continuous security?
3. Between entry and exit, was there a split/reverse split, merger, acquisition, bankruptcy, cancellation, exchange, distribution, ticker change, delisting, relisting, or new-equity issuance?
4. If a corporate action occurred, what did a holder of one entry-session share actually receive?
5. Can the canonical raw return be reproduced from a holder-continuity basis rather than by naively connecting two same-ticker prices?
6. Does the market series appear to cross from an old security into a new/reused ticker/security without valid holder continuity?

## Frozen classifications

Each verified event must receive exactly one of these classifications:

- `CONTINUOUS`: the entry security remained economically continuous through the exit; ordinary splits/ticker changes are acceptable when holder continuity is preserved and prices are consistently adjusted.
- `TRANSFORMED_WITH_CONSIDERATION`: a merger/exchange/distribution changed the security but entry holders received identifiable successor/cash consideration. A holder-basis return may be computed separately if evidence is sufficient.
- `DISCONTINUOUS_CANCELED_OR_REUSED`: the entry security was canceled/extinguished or the ticker/market series later referred to a new/different security that entry holders did not receive. The naive entry-to-exit same-ticker return is not economically valid.
- `UNRESOLVED`: primary evidence is insufficient or contradictory.

Classification is a data-validity conclusion, not a performance judgment.

## Anti-selection rule

Even if one of the top ten is found invalid, **do not simply delete that winner from B1**. First define a general point-in-time/security-continuity correction rule capable of being applied to the full development cohort symmetrically, including losing observations.

No correction may depend on realized return magnitude, year performance, ticker identity, or membership in the top tail.

## Required outputs

Create a deterministic verification record for all ten events containing:

- frozen rank;
- issuer CIK and ticker;
- evaluation, entry and exit sessions;
- canonical entry open, raw 126 and excess 126;
- identified corporate actions in-window;
- holder-continuity conclusion;
- one of the four frozen classifications;
- supporting primary-source references;
- whether the canonical raw return is economically reproducible;
- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `formalAlphaClaim=false`;
- no automatic event deletion.

If any event is `DISCONTINUOUS_CANCELED_OR_REUSED`, the next gate must freeze a cohort-wide correction procedure before recomputing B1. If all are `CONTINUOUS`/`TRANSFORMED_WITH_CONSIDERATION`, retain the heavy-tail finding as genuine unless further evidence shows otherwise.
