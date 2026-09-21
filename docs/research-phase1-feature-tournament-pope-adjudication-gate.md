# Phase-1 feature tournament POPE continuity adjudication gate

Frozen: 2026-09-21 after the sole substantive B1/B3 economic conflict was
isolated and before any feature outcome was opened.

## Frozen row

Exactly one row is adjudicated: POPE, CIK 0000784011, evaluation 2019-06-24,
entry 2019-06-25, 252-session target 2020-06-24.

The frozen contracts agree on successor RYN and quantity 3.929 but disagree on
cash:

- B1: 3.929 RYN + $0;
- B3: 3.929 RYN + $125.

Prior-evidence reuse workflow run `35644868282` correctly failed closed on
this conflict.

## Primary evidence

The frozen evidence contract is
`research/phase1-feature-tournament-pope-primary-evidence-v1.json`.

It cites Rayonier Form 8-K accession `0000052827-20-000138`. Final election
results establish that cash, Rayonier shares, and Opco units were alternative
elections. Cash elections were oversubscribed and prorated. Units for which no
valid election was submitted were contractually treated as Stock Elections and
received 3.929 Rayonier shares per POPE unit.

Therefore 3.929 RYN plus $125 cash is not a valid single-holder outcome.

## Passive-holder policy

When holder-specific election data are not observable, continuity replay uses
the legally specified default for a passive holder who submits no valid
election. That rule is frozen before any performance is opened and matches the
older B1 label `PASSIVE_HOLDER_STOCK_MERGER`.

POPE therefore resolves as:

- `TRANSFORMED_HOLDER_CONSIDERATION`;
- effective date 2020-05-08;
- successor RYN;
- 3.929 successor shares per POPE unit;
- $0 cash;
- `PASSIVE_HOLDER_STOCK_MERGER`.

## Provenance

The POPE conflict diagnostic was regenerated after correcting its provenance
field and republished at the same frozen diagnostic release before
adjudication. The adjudication pins the corrected whole-file SHA-256:

`cb6cea59cb91c7ff580c2216d4c9f022f6ab3a35cbf7a2a5ad26e57d943de49a`.

The corrected diagnostic itself binds the independently frozen residual-scope
asset SHA-256:

`bba0f3fd8c46c04e0ccd27a6b6a2a6ac0f8fcf074d89fee7239d5477f0574e01`.

The adjudicator verifies both values before applying the primary-evidence
resolution.

## Correct partition

After adjudication:

- 175 rows are direct conflict-free prior-evidence reuse;
- 1 POPE row is separately adjudicated from primary evidence;
- 34 rows still require new primary-evidence research.

The earlier 176/34 wording is superseded only as to attribution: 176 rows are
resolved before new residual research, but only 175 are direct prior reuse.

## Boundary

Performance remains closed, validation remains unused for selection, 2023+
remains sealed, and production scoring is unchanged.
