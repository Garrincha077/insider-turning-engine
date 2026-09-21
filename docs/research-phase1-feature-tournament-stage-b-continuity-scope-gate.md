# Phase-1 feature tournament Stage-B continuity-scope gate

Frozen: 2026-09-21 before Stage-A coverage/cutpoint output was observed.

## Purpose

Create the exact event-horizon universe that must receive a performance-blind
security-continuity audit before any insider-feature forward outcome is opened.

## Source

Only the immutable Stage-A feature matrix may define the event universe.

Expected frozen event scope:

- benchmark event unit: B0 exact-entry issuer event;
- events: **24,192**;
- distinct issuers: **4,729**;
- evaluation sessions: 2016-2020;
- issuer deduplication: 20 XNYS sessions;
- no forward-return, SPY-excess, MAE or robustness field may be present/read.

## Event-horizon expansion

Every Stage-A event is expanded mechanically to the already-frozen horizons:

- 21 XNYS sessions;
- 63 XNYS sessions;
- 126 XNYS sessions;
- 252 XNYS sessions.

Expected rows: **96,768**.

Target session is exactly `horizon` XNYS sessions after the exact Stage-A
entry session. No nearest/later market bar may define the target.

The expansion reads the XNYS calendar only. It does not read market prices.

## Frozen key

Each scope row contains exactly the identity needed by later continuity work:

- eventNumber;
- issuerCik;
- historical ticker;
- evaluationSession;
- entrySession;
- horizon;
- targetExitSession.

The scope-key SHA-256 is computed from those fields in eventNumber/horizon
order and becomes immutable only after the Stage-A source asset itself is
published and pinned.

## Boundary

- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false;
- 2023+ remains sealed.

This scope does not itself decide continuity. A later performance-blind
continuity ledger/resolution stage must classify every affected row and reach
**zero unresolved** before 2016-2018 feature discovery outcomes may be read.
