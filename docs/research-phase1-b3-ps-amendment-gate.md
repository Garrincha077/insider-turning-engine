# Phase-1 B3 P/S amendment-reconciliation gate

Status: **PREDECLARED / NOT YET EXECUTED**  
Date: **2026-09-18**  
Scope: research-only completion of the B3 buy/sale PIT history prerequisite.  
OOS: **2023+ remains sealed.**  
Production scoring: unchanged.

## Why a broader amendment gate is required

The existing 2013–2022 amendment acquisition is broad, but the completed reconciliation was anchored to the narrower original-buy universe. That result is valid for its stated scope and must not be relabeled as a complete company buy/sale history.

The B3 P/S history must preserve both directions symmetrically and must also handle amendments that introduce, remove or correct a qualified P/S row.

## Frozen qualified P/S row

For this gate only, a qualified economic P/S row is a canonical:

- non-derivative transaction;
- positive finite shares;
- positive finite transaction price;
- `P/A` with `OPEN_MARKET_PURCHASE`, or
- `S/D` with `OPEN_MARKET_SALE`.

Derivative transactions, option exercises, tax withholding, gifts, awards, transfers and other acquisitions/dispositions are not B3 P/S rows.

This definition is identical to the original-P/S history gate and may not be broadened after reconciliation results are seen.

## Required chain scope

An amendment chain is in scope if **either**:

1. its original predecessor filing belongs to the completed original-P/S PIT universe; or
2. a transaction-bearing amendment contains at least one qualified P/S row even though its predecessor filing was outside the original-P/S universe.

Case 2 is essential: otherwise an amendment that first makes a buy/sale economically relevant would be systematically omitted.

When case 2 occurs, the predecessor original filing may be hydrated as **supporting linkage evidence** even if it contains no qualified P/S row. Supporting predecessor rows do not become B3 events merely because they were hydrated.

## Existing evidence that may be reused

The already completed transaction-bearing Form 4/A and 5/A acquisition for 2013–2022 may be reused only after exact artifact identities are frozen and verified.

The existing predecessor catalogs may be reused as deterministic linkage evidence. They do not by themselves substitute for canonical acceptance-time hydration of a supporting predecessor when exact row/revision evidence is required.

## PIT policy

- `knowledgeAt == acceptedAt` for every historical canonical revision used.
- An original state remains effective until an amendment becomes public.
- No later amendment may retroactively alter an earlier information state.
- Multi-amendment chains use the immediate predecessor revision after root linkage.
- 2023+ evidence is prohibited.

## Linkage evidence

Permitted deterministic evidence:

- issuer CIK;
- SEC `DATE_OF_ORIG_SUB`;
- reporting-owner CIK;
- form family;
- exact owner/table/row sequence;
- immediate `supersedesRevisionId` after root linkage.

Not permitted:

- fuzzy price matching;
- fuzzy share matching;
- nearest transaction date;
- future ticker/current issuer mappings;
- choosing a predecessor because it improves B3 coverage or performance.

Ambiguous or unresolved chains remain quarantined.

## Supporting-predecessor rule

For an in-scope qualified P/S amendment whose deterministic predecessor is outside the original-P/S universe:

1. identify the predecessor accession from frozen SEC catalog evidence;
2. hydrate that original filing with the same SEC acceptance-time contract;
3. mark it `supportingPredecessorOnly=true` unless it independently qualifies under the original-P/S gate;
4. use its canonical rows only to establish lifecycle/revision identity;
5. do not count its non-P/S economic rows as B3 buys or sales.

If a unique predecessor cannot be established, the amendment remains quarantined.

## Completion requirements

The P/S amendment gate passes only if:

- all 40 quarters of original P/S PIT history already passed;
- all frozen amendment acquisition evidence is present;
- every in-scope amendment is classified as linked, explicitly outside economic scope, or quarantined with a deterministic reason;
- required supporting predecessor accessions are completely hydrated or explicitly quarantined;
- transaction/revision IDs remain unique;
- lifecycle intervals are deterministic;
- every canonical historical clock equals SEC acceptance time;
- 2023+ remains unopened;
- no production code/scoring changes are made.

The summary must report separately:

- original-P/S-root chains;
- qualified-P/S amendments whose predecessor was initially outside the P/S universe;
- supporting predecessor filings hydrated;
- linked amendment rows;
- unresolved/ambiguous chains;
- qualified buy rows added/removed/corrected by amendment;
- qualified sale rows added/removed/corrected by amendment.

## Progression

A PASS may set:

- `fullPsHistoryComplete=true`;
- `amendmentsReconciledForPsUniverse=true`.

It still must keep:

- `b3Eligible=false`;
- `b3DefinitionFrozen=false`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

Only after this data gate passes may a separate document freeze the actual B3 company-net-buying definition, window, weighting and execution rules before any B3 development performance is computed.
