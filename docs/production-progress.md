# Production rollout and remaining evidence

The operational UI and notification adapters do not establish predictive validity.
The scoring lock remains CANDIDATE and external signal delivery is disabled in
`config/notifications.v1.yaml`.

Implemented: Settings, Alert Center, System Health, Data Coverage, hashed client
snapshot loading without sample fallback, Telegram/email adapters, channel-specific
cooldowns, secret-free public settings, and separate delivery-test history.

Before activating signals:

Historical acquisition now has a catalog-backed, resumable range importer and
fail-closed table-integrity validation. Five real quarters have been verified
locally; this is not complete canonical history. See [SEC history](sec-history.md)
for exact evidence, commands, limitations and the next enrichment boundary.
The [live daily CLI bridge](live-daily-bridge.md) now connects bounded global
SEC-day acquisition, common PIT market selection, market artifacts and Gate 1 input
preparation. One real day was acquired with two derivative rows still quarantined;
the scheduled full producer graph remains a release blocker.

- Materialize canonical SEC history from 2006 and a complete trailing 365-day
  insider-active universe. The preview window is not that universe.
- Replace current-identity and SPY-sector proxies with evidenced temporal mapping.
- Reconcile adjusted market history, corporate actions, missing and delisted bars.
- Run development/validation on real historical inputs, review methodology, and
  freeze before opening sealed OOS. Do not manufacture a PASS or adjust thresholds
  after examining the holdout.
- Persist outbox claims remotely BEFORE sending. Runner-local SQLite followed by
  a post-send state push alone cannot guarantee at-most-once across runner loss.
- Collect five distinct successful staging sessions, both channel delivery tests,
  and seven actual days of shadow alerts. Repeated fixture runs are not substitutes.
- Complete a release audit and review the delivery switch before enabling it.

## Owner setup

Open the repository's Settings > Environments > production. Add secrets there:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EMAIL_API_KEY`, `ALERT_EMAIL_FROM`,
`ALERT_EMAIL_TO`. Never put secrets in Vite variables or public data. Settings
shows a generated status snapshot; secret edits appear after the next status build.

Email uses [Resend](https://resend.com/docs/api-reference/emails/send-email).
Use a sending-only key and verified sender. Telegram requires starting the bot or
adding it to the intended chat. No token or recipient is accepted by the public UI.

`insider-turning test-alert-delivery --channel all` previews without network access.
Add `--execute` for an explicit test to configured recipients. Tests do not enter
the signal cooldown. The test workflow persists an UNCERTAIN intent in the orphan
state branch before contacting providers, then persists the result. A lost runner
leaves unconfirmed evidence, never a fabricated success. Workflow reruns cannot
send again; an owner must inspect the outcome before a new explicit test dispatch.
The ledger is also retained as a run artifact for recovery.

The emergency switch is `deliveryEnabled: false`. Channel selection and severity
filtering do not change frozen score weights. Quiet hours suppress that snapshot;
they do not queue a deferred message.

## Deployment boundaries

`main` is the stable release branch. The development branches remain available;
no reserve-model history is deleted. Production environment secrets are restricted
to `main`, while `codex/*` uses staging. Pages deployment validates hashes and runs
desktop/mobile smoke tests before artifact upload. Push/manual UI builds preserve
source timestamps by restoring and hash-validating the published bundle (restore
failure blocks deployment instead of falling back to older committed data).
Only `main` can deploy public Pages. Scheduled or explicit `refresh_data` builds fetch real preview
data without the former 50-symbol cap. The rolling preview still uses one SEC
business day; removing the cap does not create a full historical universe.

Settings restores the state-branch SQLite ledger before projection. Last test
result and test failure count are separate from signal delivery success/failures;
Alert Center exposes the latest 100 recipient-free ledger entries. History is
updated on the next Pages build, not immediately after a delivery. Legacy tests
that predate state persistence may exist only in workflow artifacts. `SENT` means
provider acceptance, not confirmation that an email reached the recipient's inbox.
State writes preserve all other allow-listed files and reject concurrent updates.
The test workflow shares the daily state-writer concurrency lock. This closes
delivery-test durability, not the remaining production signal-outbox release gate.

The daily state writer now reuses checkout authentication through the shared
isolated Git adapter instead of creating an unauthenticated replacement orphan.
Updates preserve commit history, validate the allow-listed JSON/SQLite files,
check the expected remote baseline and use a non-forcing push. Failed restores
cannot enter the persist step. Degraded runs preserve prior SEC/score/state
checkpoints; only delivery evidence can change independently of signal quality.
A successful workflow with a blocked data gate is operational evidence only,
not one of the five required successful staging data sessions.

Current release verification: Python suite, strict mypy, Ruff, frontend lint,
typecheck/build, and desktop/mobile Playwright smoke including missing/tampered
snapshot rejection. Core branch coverage uses the explicit CI module allowlist;
it does not claim 85% coverage of all Python code.
