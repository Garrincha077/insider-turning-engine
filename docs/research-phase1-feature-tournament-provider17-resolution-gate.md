# Phase-1 feature tournament provider17 resolution gate

Frozen: 2026-09-21 after the residual34 evidence audit completed and before
any feature outcome was opened.

## Purpose

Resolve exactly the 17 residual rows whose frozen corporate-action identity
matches already-frozen continuity evidence.

This stage is narrower than issuer/ticker reuse. A provider row may be resolved
only because the **same frozen corporate-action ID set** was previously
classified under a performance-blind continuity contract.

## Immutable source

Residual evidence audit:

- release: `research-phase1-feature-tournament-residual-evidence-audit-v1`;
- asset: `residual-evidence-audit.json`;
- SHA-256:
  `sha256:e17e7bc3a103be988a99b50a9080003c50b7acf8db84d2d80a91cedb40db56cd`;
- audited rows: **34**;
- provider rows: **17**;
- long-gap rows: **17**;
- performanceRead=false;
- featureOutcomesRead=false.

The audit itself was produced from pinned residual34, Stage-B unresolved,
B3 final-continuity and B1 frozen-continuity inputs.

## Authorized provider reuse

The frozen audit partition is:

- **16** `PROVIDER_ACTION_REUSE_B3`;
- **1** `PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND`.

For every provider resolution the resolver must verify:

1. current residual source is `provider`;
2. the current candidate corporate-action ID set is non-empty;
3. that ID set exactly equals the frozen evidence action-ID set;
4. the prior frozen evidence has at least one matching row;
5. the corporate action effective date is after entry and no later than the
   target exit session;
6. normalized economic terms are present and internally valid.

The B1 fallback remains restricted to
`STOCK_DIVIDEND_QUANTITY`. No B1 merger/election semantics can enter through
this gate.

## Expected economic partition

The 17 resolved rows must contain exactly:

- **13** `STOCK_DIVIDEND_QUANTITY`;
- **4** `STOCK_AND_CASH_MERGER`.

The four merger rows are the four horizons of the same frozen FG/FNF action
identity and carry the already-frozen economic terms:

- successor: FNF;
- successor shares per FG share: 0.2558;
- cash per FG share: 12.5.

Stock-dividend rows must preserve the same ticker as successor and the frozen
quantity factor from the action-level evidence.

## Outputs

A successful stage publishes two immutable outputs.

### provider17-resolution.json

Exactly 17 deterministic continuity resolutions including:

- full current event-horizon key;
- action IDs;
- effective date;
- resolution decision and result state;
- transformation kind;
- successor symbol;
- successor-share factor;
- cash consideration;
- frozen evidence class/source lineage.

### long-gap17-scope.json

Exactly the 17 non-provider residual rows, preserving the audit evidence state:

- 7 `LONG_GAP_PRIOR_SECURITY_CANDIDATE`;
- 10 `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`.

No long-gap candidate is resolved by this stage.

## Progression boundary

After a successful provider17 release:

- 175 safe prior-evidence rows are resolved;
- 1 POPE row is primary-evidence adjudicated;
- 17 provider rows are exact-action resolved;
- **193 / 210** Stage-B unresolved rows are now deterministically covered;
- 17 long-gap rows remain;
- feature discovery outcomes remain closed;
- validation remains untouched by selection/tuning;
- 2023+ remains sealed;
- production scoring remains unchanged.

The next authorized step is date/security validation of the seven long-gap
prior-security candidates. Only after that should the ten genuinely new
primary-evidence rows be researched.
