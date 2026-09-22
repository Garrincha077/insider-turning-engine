# Phase-1 F2 validation final continuity contract gate

Frozen: 2026-09-22 after the final ten validation long-gap rows were resolved
and before any 2021-2022 validation outcome is read.

## Purpose

Create one immutable performance-blind contract for every validation row whose
terminal holder security or holder economics cannot be treated as an ordinary
unchanged adjusted-price row.

The source validation continuity audit contains **7,493** 126-session rows:

- 7,302 ordinary adjusted-price rows;
- 99 provider-complete same-security symbol changes;
- 51 provider-complete holder transformations;
- 41 originally unresolved rows.

The final contract therefore covers exactly **191 affected rows**. Ordinary
adjusted-price rows remain outside the overlay.

## Frozen audit source

Release:
`research-phase1-insider-feature-tournament-validation-continuity-audit-v1`.

Archive:
`phase1-insider-feature-tournament-validation-continuity-audit-v1.tar.gz`.

Archive SHA-256:
`sha256:e1e34180cbd8e115412d88e75abc39711b1645515396b4f6bb52b19a6d7716d5`.

Extracted audit CSV SHA-256:
`sha256:11608f09dc09f81a8bb467301ca14ccfed12caac55e79652c6b144e9091b599e`.

Extracted corporate-action inventory SHA-256:
`sha256:c45e1c5ea5263d2384527359a544f3b81e49fa9f5b64fc9ff792153ad1fb0457`.

Validation scope semantic key:
`sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3`.

## Provider-complete rows

The 150 rows already deterministic in the original audit are reconstructed
directly from their exact frozen corporate-action IDs.

For the 99 same-CUSIP name changes:

- decision: `SYMBOL_CHANGED_SAME_SECURITY`;
- quantity: 1;
- cash: 0;
- successor: the frozen provider new symbol.

For the 51 complete holder transformations:

- 29 are deterministic cash mergers;
- 22 are deterministic stock mergers;
- cash-merger value is the frozen provider cash rate;
- stock-merger quantity is
  `acquirer_rate / acquiree_rate`;
- successor is the frozen provider acquirer symbol.

Every provider action must remain unique and effective strictly after entry and
no later than the frozen target session.

## Explicit 41-row resolution union

The originally unresolved key set must be reproduced exactly by these immutable
resolution assets:

| Group | Rows | Asset SHA-256 |
| --- | ---: | --- |
| exact-action prior evidence | 8 | `6e238d29f9e8a31b388b84cb5f11964079f81b68985b44cf28b290e1fbb29bdc` |
| HSDT primary | 1 | `b5348aa135082da6a2d07510125ffde4b67b4f327a522597301782d3b2e37a03` |
| stock-dividend primary | 5 | `fcac9796cb768fda95f0b2c1fdffc083379f3140500fca68c48a39bd5b007ba9` |
| incomplete-stock-merger primary | 8 | `73722b4c87590a8a1fc0ad748534ce19a0d788281b965df1e475bc0dc789d584` |
| SPAC share-exchange primary | 8 | `ebc41a7a0e65c6bcb696330f6e6121deff55e954bcafde6fe4fe83ea59ca4581` |
| CBTX primary | 1 | `bf074cb873959b5da66fdb98af015349a1ec09bf6e5192785bac1e23699cdf5f` |
| long-gap10 primary | 10 | `6d8c661cf00ff1bfd0a99cc7d469503ced8e7a5350f83a2917e149fc1a68a28c` |

The 41-row union must equal the original audit's unresolved key set exactly.
No extra row may be introduced and no unresolved row may disappear by
subtraction.

## Required final partition

The complete 191-row overlay must contain exactly:

- 11 `SAME_SECURITY_CONTINUITY`;
- 101 `SYMBOL_CHANGED_SAME_SECURITY`;
- 79 `TRANSFORMED_HOLDER_CONSIDERATION`.

The same counts must appear in the corresponding final result states:
11 adjusted-price continuity, 101 same-security symbol changes and 79
deterministic holder transformations.

## Boundary

This contract is still performance-blind. It may read security identity,
corporate-action economics and primary continuity evidence, but it may not read
stock returns, SPY returns or any validation PASS/FAIL result.

A green contract proves:

- all 191 affected rows are classified;
- all 41 formerly unresolved rows are deterministically resolved;
- unresolved continuity is **0**;
- the 7,493-row validation scope is unchanged;
- 2023+ remains sealed.

Only after this release is immutable may the already-frozen F2 validation
performance rule be executed. That next stage may not alter the feature,
orientation, 126-session horizon, top-1% rule or pass criteria.
