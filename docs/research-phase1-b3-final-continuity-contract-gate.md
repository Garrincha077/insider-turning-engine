# Phase-1 B3 final 264-row continuity contract gate

Frozen: 2026-09-20 after every one of the original 264 unresolved B3
event-horizon rows received a performance-blind deterministic classification.

## Purpose

This gate does not perform any new continuity inference. It only aggregates and
proves exact coverage of the already frozen classifications before corrected B3
performance may be opened.

The gate must demonstrate all of the following simultaneously:

1. the original frozen continuity universe contains exactly 264 unique keys;
2. the first 173 deterministic classifications are exactly the
   `combinedCandidateRowsData` from
   `research-phase1-b3-residual-multisource-v1`;
3. the later eight resolution releases contain exactly 91 unique keys;
4. those 91 later keys are exactly the residual-91 key set from the multisource
   release;
5. the 173 and 91 key sets are disjoint;
6. their union has 264 keys and its key digest equals the upstream
   `frozenScopeKeySha256`;
7. every row has exactly one final continuity classification;
8. every source remained performance-blind and kept 2023+ OOS closed.

## Pinned source releases

The aggregation is restricted to these immutable assets:

- `research-phase1-b3-residual-multisource-v1`
  - `b3-residual-multisource-synthesis.json`
  - SHA-256 `b88512259b21b31b1defa63328cba4f2e56ba32f6fbf071452ff32251777f56a`
  - 173 final candidates + frozen residual-91 scope
- `research-phase1-b3-provider-primary-resolution-v1`
  - SHA-256 `4f37195c3fda7a2db119f7391c8dbad4571d928aca80b78bc6e5630cdc48dfc1`
  - 4 rows
- `research-phase1-b3-spac-unit-primary-resolution-v1`
  - SHA-256 `0a6e5f9b271508959f3628babc86965254fe715720790958fd5883202e612065`
  - 4 rows
- `research-phase1-b3-one-sided-primary-resolution-v1`
  - SHA-256 `2b4e30dcac2d032e9f27495f72e67ed1cb70fc14d11ed58abe8d4e2a73d5c45b`
  - 20 rows
- `research-phase1-b3-spac-unit2-primary-resolution-v1`
  - SHA-256 `1a4e0b9fb67ce72a80d49b39ec827b3ad2ca8e5ce53ca36bcdf44470bf2ecb04`
  - 8 rows
- `research-phase1-b3-multiclass-reorg-primary-resolution-v1`
  - SHA-256 `a844ea830b9503a045b55a490c30b9e3cd77456974b741a696f16617caf75969`
  - 12 rows
- `research-phase1-b3-common-security-primary-resolution-v1`
  - SHA-256 `fec6e91a78c665686d5a00baa1baef9a9c6493c4bf53841e8b39bc0e20cc2ac4`
  - 19 rows
- `research-phase1-b3-surviving-unit-primary-resolution-v1`
  - SHA-256 `65ce412c1bee4abdb0e47851f13afa9c8cfa2abd33190c8ac401da29c5c5c8f9`
  - 11 rows
- `research-phase1-b3-final-residual13-resolution-v1`
  - SHA-256 `6ac4dc4adee77e32747ad4e536fec3036c99c23bb664f3ccf5be2b4ab5b4981e`
  - 13 rows

The later-resolution counts must sum to exactly 91:
`4 + 4 + 20 + 8 + 12 + 19 + 11 + 13 = 91`.

## Contract output

The final artifact must contain all 264 resolution rows with source provenance,
plus:

- `status=B3_FINAL_CONTINUITY_CONTRACT_COMPLETE`
- `sourceUnresolvedRows=264`
- `classifiedRows=264`
- `unresolvedRows=0`
- `finalResolutionContractCreated=true`
- `correctedPerformanceOpened=false`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`

The contract must preserve the NBA.U multi-component basket explicitly. It may
not collapse that basket to common stock alone.

## Boundary after this gate

A green final-contract run authorizes only the next research step: a separately
frozen corrected-development-performance implementation using the final
continuity contract.

It does not authorize validation, HAC/OOS progression, production scoring
changes, or 2023+ data access. The previously frozen B3 robustness semantics
remain unchanged and must be reapplied after corrected development performance.
