# Synthetic SEC fixtures

These fixtures contain fake people, CIKs, issuer values, and prices. They are structurally realistic `ownershipDocument` XML files (schema `X0508`) intended for parser and normalization tests; they are not SEC filings.

| Fixture | Coverage |
| --- | --- |
| `form4_non_derivative.xml` | Ordinary non-derivative purchase (`P`) and sale (`S`) |
| `form4_special_codes.xml` | Award (`A`), gift (`G`), tax-liability withholding (`F`), and tender offer (`T`); option exercise code `M` is in `form4_derivative.xml` |
| `form4_derivative.xml` | Derivative option transaction, underlying security, exercise and expiration dates |
| `form4_missing_price.xml` | Non-derivative transaction with no `transactionPricePerShare` element |
| `form4_direct_indirect_multi_owner.xml` | Direct (`D`) and indirect (`I`) ownership plus two reporting owners |
| `form4_10b5_1_explicit.xml` | Document-level `aff10b5One=1` |
| `form4_10b5_1_footnote.xml` | `aff10b5One=0` with a footnote explicitly mentioning a Rule 10b5-1 plan |
| `form4_original.xml`, `form4_amendment.xml` | Matching original Form 4 and corrected Form 4/A (price 10.00 -> 10.50) |
| `daily_market.csv` | Compact 10-business-day panel for ACME, SPY, and XLF (sector ETF) |

The market panel is intentionally compact for repository size and deterministic unit tests. A longer history can be expanded mechanically by repeating the same three-ticker schema over business dates; no test should rely on the compact file having 260 rows. `XLF` is a synthetic sector-ETF proxy and all values are fabricated.
