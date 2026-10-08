# Daily publication recovery

The daily SEC/market pipeline and factual digest policy are unchanged. A separate
Daily publication watchdog runs after the Pages workflow completes, including
a workflow-level failure that never starts its deploy/digest/report jobs. A
Tuesday–Saturday 17:45 UTC fallback checks the current public SEC day and the
durable Telegram ledger. Healthy, running and deliberately cancelled runs do
not produce a warning. Scheduled starts can still be delayed by GitHub.

## What can be recovered

Only an original, completed, failed Pages run from this repository's main branch
is eligible. Its build must have succeeded, deployment must not have succeeded,
its commit must still be the current main, and it must be less than 24 hours
old. Re-runs, forks, failed data validation, expired artifacts, missing proof,
and a newer public snapshot are never repaired automatically.

The original build seals publication-proof.json after validation: source
run/commit, original digest intent, snapshot run, and SHA-256 of the manifest
and HTML entry point. Recovery checks the GitHub artifact checksum, extracts
only bounded regular files, and repeats the existing complete schema/hash/run
and publication-policy checks. No downloaded scripts are executed; no SEC or
market data are reacquired and no parser or scores are changed.

A claim in the existing state-branch SQLite ledger is persisted **before** any
recovery publication. A lost/uncertain claim write blocks deployment. Only one
recovery execution is reserved for each original run. That execution can attempt
deployment once, then retry after 15 and 30 minutes (two retries maximum).
There is no recursive recovery trigger or endless retry. The shared production
concurrency lock and non-forcing state writes remain in place.

Every workflow sharing the production lock uses queue: max with cancellation
disabled. GitHub's default single-pending queue replaces an older waiting run
even when cancel-in-progress is false; the expanded queue prevents a watchdog
or UI-only deployment from replacing a waiting daily run. At most 100 runs may
wait, and only one may execute. Queue ordering follows when runs start waiting,
not their dispatch time; this is not a guarantee of scheduled start times.
See [GitHub concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

If the exact HTML and manifest are already public, recovery does not redeploy
or create another publication claim.

## Telegram is not a deployment retry

After a recovered publication, the factual digest runs only if the original
sealed run explicitly expected it. It uses the same validated data and unchanged
freshness, completeness, policy, production and durable day-claim checks.
Already-claimed, failed or uncertain deliveries are not resent automatically.
A digest-only failure does not trigger publication recovery.

Late manual refreshes may update the dashboard while the previous SEC day's
digest is blocked after a newer market close. Never disable that guard to send
a missed historical day. The next normal daily cycle uses the newest eligible
day; it does not replay the backlog.

The independent failure notice uses the existing at-most-once operational
notice ledger. A pre-send public settings export or daily-report.digestReady
is not authoritative delivery evidence. The fallback requires a durable
factual_digest_claims row with SENT for the expected day.

## Operator procedure

Check watchdog-plan, watchdog-status and recovered-digest-status artifacts.
If no safe recovery is possible, the last valid public snapshot remains active
and the warning links to the original run. Inspect the new watchdog run for the
specific recovery gate.

The watchdog can also be manually dispatched with an original source run ID.
It does not bypass a prior recovery claim or allow historical Telegram delivery.
Missing/corrupt state, unavailable public evidence or failed integrity checks
require operator investigation, not a forced retry.

No workflow hosted on GitHub can guarantee availability during a platform-wide
GitHub outage. This provides bounded recovery and independent reporting,
not guaranteed uptime.
