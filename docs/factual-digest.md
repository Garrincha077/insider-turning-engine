# Factual daily digest (rollout)

This is independent of predictive alerts. `config/digest.v1.json` is the sole
factual delivery switch; it is currently **OFF** pending clean SEC-day evidence.
`config/notifications.v1.yaml` remains unchanged with predictive delivery OFF.

## Implemented

- Backend selection: newest inventoried SEC day only, complete acquisition and
  parsing required. No fallback to an older complete day or backfill backlog.
- At most five resolved, eligible, non-derivative P purchases ≥ $250,000, ranked
  by dollars and stable event ID. Joint-owner economic events count once.
- No score, market-price or backtest requirements. Unknown purchase amounts or
  unresolved issuers prevent an unsupported empty-day assertion.
- Exact immutable publication artifact passed from build to the post-Pages job;
  every schema/hash/run is checked again before preview and delivery.
- Preview has no credentials, provider calls or state writes. Run locally with:

  ```sh
  uv run python -m insider_turning_engine.notifications.digest_cli --directory app/public/data
  ```

- Execute additionally checks production/main environment, fresh snapshot and
  SEC day, separate policy and configured Telegram secrets. UI-only deploys and
  workflow reruns never initiate delivery.
- Fresh state checkout is restored after the daily score/state writer. SQLite
  `(telegram, SEC day)` claim is committed, closed and pushed before HTTP.
  A failed claim push means no send. A crash, failed result push, any existing
  claim, or ambiguous receipt means **no automatic resend**, including FAILED.
- Public Settings/Alert Center share backend selection and suppression. The
  delivery ledger projects only kind/channel/status/time; no token, recipient,
  free-form provider error or provider message ID is public. History updates on
  the next publication. Current attempt diagnostics live in Actions artifacts.

## Current concrete source blocker

2026-09-11 has 497/497 stored filings and one quarantined derivative row in
[SEC accession 0001493152-26-042331](https://www.sec.gov/Archives/edgar/data/315545/000149315226042331/ownership.xml).
The convertible note uses `transactionTotalValue=35000` and has no
`transactionShares`. Treating dollars or underlying shares as the reported
derivative quantity would invent data. The regression test deliberately keeps
this row quarantined until a typed quantity/unit contract can represent it.
This is not an unresolved open-market purchase. Existing day-level completeness
still blocks the digest; no quarantine was deleted or attested away.

The September 3 checkpoint stored 750/1,056 filings within its first bounded run;
306 were pending and three rows quarantined. Storage success is not completeness.

## Remaining activation checks

1. Represent reported derivative amounts without fabricating shares; replay only
   affected evidence into a new verified immutable checkpoint. Preserve prior
   observation/acceptance times and original checkpoint provenance.
2. Verify clean latest-day selection, successful Telegram delivery test and
   persisted claim/result using production state. Set the separate digest policy
   enabled only after these checks; never toggle the predictive policy.
3. Observe two distinct real daily cycles. Repeated runs of one SEC day do not
   establish multi-day operational readiness.

If delivery is uncertain, inspect the durable claim and Telegram manually. Do not
delete claims or retry blindly. Email and historically validated scoring remain
separate goals; neither is required for factual daily use.
