# Phase-1 F2 validation provider8 resolution gate

Frozen after the validation prior-evidence audit and before validation
performance is opened.

## Source

Release:
`research-phase1-insider-feature-tournament-validation-prior-evidence-v1`

Asset:
`validation-prior-evidence-audit.json`

SHA-256:
`sha256:6d261d773a47b311b18827fece4307105788be17ac6ece16d38daa4b27974361`

The source partitions 41 unresolved validation continuity rows into:

- 8 `PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE`;
- 1 `LONG_GAP_PRIOR_SECURITY_CANDIDATE`;
- 22 `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`;
- 10 `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`.

## Exact-action reuse

Only the eight provider rows may be resolved here.

Each row must preserve:

- current validation event/horizon identity;
- same issuer and original ticker;
- exact frozen action-ID set;
- one unique frozen economic fingerprint;
- one unique schema-label pair;
- effective date inside the current entry/target horizon.

Frozen ticker partition:

- BOTJ: 2
- CLDB: 3
- GNTY: 1
- HWBK: 1
- WPF: 1

Expected decision partition:

- 7 transformed-holder consideration;
- 1 same-security symbol change.

## Boundary

This stage does not resolve HSDT or any new-primary row.

After success:

- 8 provider rows are deterministically resolved;
- 33 validation continuity residual rows remain;
- validation returns remain unopened;
- 2023+ remains sealed;
- production scoring remains unchanged.
