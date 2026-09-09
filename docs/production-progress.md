# Production rollout and remaining evidence

The operational UI and notification adapters do not establish predictive validity.
The scoring lock remains CANDIDATE and external signal delivery is disabled in
`config/notifications.v1.yaml`.

Implemented: Settings, Alert Center, System Health, Data Coverage, hashed client
snapshot loading without sample fallback, Telegram/email adapters, channel-specific
cooldowns, secret-free public settings, and separate delivery-test history.

Before activating signals:

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
the signal cooldown. The test workflow retains the ledger as a run artifact;
its history is not yet automatically merged into the production state branch.

The emergency switch is `deliveryEnabled: false`. Channel selection and severity
filtering do not change frozen score weights. Quiet hours suppress that snapshot;
they do not queue a deferred message.

## Deployment boundaries

`main` is the stable release branch. The development branches remain available;
no reserve-model history is deleted. Production environment secrets are restricted
to `main`, while `codex/*` uses staging. Pages deployment validates hashes and runs
desktop/mobile smoke tests before artifact upload. Push/manual UI builds preserve
source timestamps; scheduled or explicit `refresh_data` builds fetch real preview
data without the former 50-symbol cap. The rolling preview still uses one SEC
business day; removing the cap does not create a full historical universe.

Settings builds currently use an empty local delivery ledger, so historical
delivery fields are not yet connected to persistent state. Do not interpret
`Never` as proof no delivery has ever occurred. The delivery-test ledger is
available separately in workflow artifacts. `SENT` means provider acceptance,
not confirmation that an email reached the recipient's inbox.

Current release verification: Python suite, strict mypy, Ruff, frontend lint,
typecheck/build, and desktop/mobile Playwright smoke including missing/tampered
snapshot rejection. Core branch coverage uses the explicit CI module allowlist;
it does not claim 85% coverage of all Python code.
