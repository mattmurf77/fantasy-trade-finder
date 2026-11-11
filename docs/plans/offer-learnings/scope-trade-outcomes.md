# Feature Scope — WS2: outcomes of sent trades, and consented Sleeper offer import (R3)

**Date:** 2026-11-10
**Entry point:** direct operator ask — `docs/plans/offer-learnings/plan.md` §3 WS2 (operator comment on R3:
"Yes. Ideally pulling from the users' sleeper account as well (with explicit user permission and a line in
the Ts & Cs).")
**Builder:** WS2 builder agent, branch `feat/trade-outcomes`
**Operator sign-off on waivers:** needed — §0 (Part B stopped), §1 (no analytics events), §3 (no mobile UI)

---

## 0. What the app can observe, and therefore what is built

Established from the code before designing (file:line on `origin/main` at `6017d64b`).

### Why `trade_proposals` has no rows in production

`trade_proposals` IS written on the live Sleeper send path: `_sleeper_propose_core` (the body of
`POST /api/trades/propose`, which the app calls from `mobile/src/api/sendInSleeper.ts`) calls
`_record_trade_proposal` after every confirmed send. `_record_trade_proposal` returns at its first line
unless `trade.valuation_telemetry` is on (`backend/trade_policy.py:143`). That flag is `false` in
`config/features.json`, but production turns it on through Render's `FTF_FLAGS` (G-076; on since
2026-09-05 per `docs/plans/shop-send-elo/scope.md`). So the write path is live in production, and the code
alone cannot say why the table is empty. Two explanations remain, and only a production read separates them:

1. **No confirmed Sleeper send since 2026-09-05.** Check:
   `SELECT count(*) FROM user_events WHERE event_type = 'sleeper_send_succeeded' AND occurred_at >= '2026-09-05'`.
   Zero means there is nothing to record, and the table is empty for that reason.
2. **The writes fail and the error is swallowed.** `_record_trade_proposal` catches everything, logs
   `trade proposal record failed (non-fatal)` and increments the process-local
   `trade_policy.HEALTH["proposal_write_failures"]`. A non-zero count from (1) with no rows means look
   for that log line on Render.

Not checked here: this work does not read production. Either way the only durable production record of
a Sleeper send is the `sleeper_send_succeeded` event, whose props carry the `transaction_id` and asset
counts but not the assets or the two roster ids. WS2 leaves `trade_proposals` alone and writes its own
row, gated by its own flag, so outcome tracking does not depend on the policy-telemetry flag.

### What each source can see

| Source | Credential | accepted | declined | countered (+ counter terms) | withdrawn | expired |
|---|---|---|---|---|---|---|
| Public REST `GET /v1/league/{id}/transactions/{leg}` — already captured into `sleeper_trades` by `sleeper_trades_service.sync_league_trades` (flag `market.trade_capture`, on) | none | **yes** — the sent `transaction_id` appears with `status: complete` | no | **partly** — only if the counter was itself *accepted*: a different completed trade between the same two rosters after the send. A counter that was never accepted is invisible | no | no |
| Private GraphQL `league_transactions_filtered(status_filters: …)` on `sleeper.com/graphql` | the user's Sleeper JWT (`sleeper_credentials`, held only for users who linked Send in Sleeper) | would see it | would see it, if Sleeper keeps rejected rows and the status word is known | would see it | would see it | would see it, if `expires_at` is returned |

The private read is **not in the app**. It is known only from a public `__schema` dump cited in
`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md` (addendum §1); it has never been captured, its
status vocabulary for declined/withdrawn/expired is unknown, and `backend/sleeper_write.py` implements only
`propose_trade`, `reject_trade` and the `ftf_token_probe` no-op. Adding it is a new endpoint on the
ToS-adverse surface.

### Consequences

- **Part A (built, flag `trade.outcome_tracking`, off).** Every confirmed Sleeper send (deck, match,
  calculator, shop, overhaul — they all go through `_sleeper_propose_core`) writes one
  `trade_offer_outcomes` row with status `sent`. A reconciler reads `sleeper_trades` (public data the app
  already captures) and moves the row to:
  - `accepted` — the sent `transaction_id` completed; `status_at` = Sleeper's completion time;
  - `completed_different_terms` — the sent offer did not complete, but the same two rosters completed a
    different two-team trade after the send. Its terms are stored from the user's side. This is the only
    form of "countered, with the counter's terms" the public data shows, and it is labelled for what it
    is: an *observed later trade between the same two teams*, not a confirmed counter. It is not
    terminal: if the original later completes, `accepted` wins.
  - Everything else stays `sent`. **Declined, countered-and-not-accepted, withdrawn and expired are not
    recorded, because the app cannot observe them.** No status is inferred from silence.
- **Part B (stopped).** Importing offers the user sent or received outside the app, with their outcomes,
  needs the private read above. The app holds the credential only for Send-in-Sleeper users, and does not
  hold the operation at all. Per the spec ("If Part B needs an endpoint or credential the app does not hold
  today, stop and report"), nothing was built: no consent table, no import, no `trade.sleeper_offer_import`
  flag (a flag with no consumer would be dead config). Completed trades in the user's linked leagues are
  already captured league-wide from the public API, so the "outcomes" half of Part B for accepted trades
  exists today without consent; it is public league data, not the user's account data.
- **ESPN and MFL (follow-up, not built).** MFL has a documented, owner-scoped `pendingTrades` export
  (`mfl_service.fetch_pending_trades`) that could show pending → gone, and ESPN has its own write path.
  Neither shares the `sleeper_trades` seam, so each is its own small piece of work.

### Part B, if the operator wants it later

1. Operator decision: accept extending the private GraphQL surface with a *read* (the feasibility memo
   records the operator's 2026-08-12 statement that FTF has Sleeper's written agreement; this would be the
   first read on that surface).
2. Capture `league_transactions_filtered` from live traffic (runbook-style), including the status words for
   rejected / withdrawn / expired and whether rejected rows are retained at all.
3. Consent model (to build then): one append-only row per grant or withdrawal in a new
   `offer_import_consents` table, mirroring `platform_write_consents` — `user_id`, `kind` grant|withdrawal,
   `terms_version`, `consented_at`; revoking writes a withdrawal row and deletes every imported row of that
   user in the same transaction; account deletion removes both (`_ADDITIONAL_PRIVATE_TABLES`). Imported
   rows store only `transaction_id`, `league_id`, the two roster ids, the asset ids, status and times — no
   message or chat fields are requested from the query. Reads are filtered by `user_id` so no user ever
   sees another's imports.
4. App screen (Settings → Sleeper, beside the existing Send-in-Sleeper connection): one switch, "Use my
   Sleeper trade offers to improve suggestions", with the Terms line below it and a link to the Terms;
   off by default; switching it off says "Imported offers deleted".

### Draft Terms line (for operator approval — NOT applied to `web/terms.html`)

`web/terms.html` is a static page with no flag mechanism, so it cannot carry a dark line; it is untouched.
Proposed wording, for §5 next to "Sending trade proposals … is optional":

> **Trade outcomes.** When you send a trade from the app, we record what happens to it in your league — for
> example, whether it was accepted — using league information the platform makes available, to improve
> the trades we suggest. If you choose to turn on "Use my Sleeper trade offers", we also read the trade
> offers you send and receive on Sleeper in the leagues you've linked, and what happened to each. We read
> only the offers and their outcomes, never your messages or chats. You can turn this off at any time in
> Settings, and when you do we delete the offers we imported.

The first sentence covers Part A (built); the rest covers Part B (not built) and should go live only with
Part B.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics event needed because:** the outcome is durable state in its own table,
  read offline by the acceptance evaluation; the send itself is already the `sleeper_send_succeeded`
  event. No event was added, so `analytics_taxonomy.py` / `NON_INTENT_EVENTS` are unchanged.

## 2. Schema & flag scope

- New table `trade_offer_outcomes` (created by `metadata.create_all`; a new table needs no `migration_cols`
  row) → `docs/data-dictionary.md` updated. Deleted and exported with the account
  (`accounts._ADDITIONAL_PRIVATE_TABLES`).
- New flag `trade.outcome_tracking`, default **off** → `config/features.json`, `feature_flags.FLAG_KEYS`,
  `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`, `docs/config-reference.md`.
  Off = no row written at send, no reconcile at session init, daily-tick step `trade_outcomes` skipped.
  Graduation criterion: on in production for 30 days with every confirmed Sleeper send producing exactly
  one row (`sleeper_send_succeeded` count == `trade_offer_outcomes` count) and no reconcile errors in the
  daily-tick log. Rollback lever: the flag (hot via `POST /api/feature-flags/reload`); rows left behind are
  inert.
- `trade.sleeper_offer_import`: **not added** — Part B stopped (§0).
- No env vars or `model_config` keys. The daily-tick budget (`OUTCOME_SYNC_LEAGUE_BUDGET`, 50 leagues) and
  the watch window (`OUTCOME_WATCH_DAYS`, 30) are module constants in `backend/trade_outcomes.py`.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_trade_outcomes.py` — send-time row from the real route (flag on),
  flag-off byte-identity (no row, no reconcile, step skipped), each reachable transition from fixtures
  (`sent`→`accepted`, `sent`→`completed_different_terms` with terms, `completed_different_terms`→`accepted`,
  stays `sent` for: unrelated trade, three-team trade, trade before the send), idempotent re-sync and
  duplicate send, the session-init and daily-tick seams. `test_daily_tick_route.py` STEP_KEYS updated.
  Deletion coverage: `test_account_deletion_coverage.py` is parametrized over `_ADDITIONAL_PRIVATE_TABLES`,
  so adding the table there extends it.
- [x] **Code-walk proof:** §0 above (why `trade_proposals` is empty; what each source sees).
- [x] **WAIVED — structural guard / TestFlight checklist / testIDs:** backend-only, no user-visible surface.
- Sabotages (each proven RED on `test_trade_outcomes.py`, GREEN on revert; recorded in TEST_LEDGER):
  `accepted-never-matches`, `no-roster-pair-check`, `no-after-send-check`, `terms-perspective-flipped`,
  `different-terms-terminal`, `resend-resets-status`, `send-hook-ignores-flag`, `send-hook-removed`,
  `session-init-hook-ignores-flag`, `session-init-hook-removed`, `daily-step-ignores-flag`,
  `daily-step-ignores-capture-flag`, `watch-window-ignored`, `tick-stops-on-error`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | no route added; `POST /api/cron/daily-tick` gains step (4) `trade_outcomes` (eleven steps, renumbered); response shape unchanged |
| `docs/runbook.md` | updated | daily-tick step order, step numbers and expected log lines |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | updated | new leaf module `trade_outcomes.py` and its two triggers |
| `living-memory/HLD.md` | n/a | no new client or major flow; a leaf module behind existing triggers |
| `docs/cross-client-invariants.md` | n/a | no client reads the status vocabulary |
| `docs/glossary.md` | updated | "Trade outcome" |
| `docs/data-dictionary.md` | updated | `trade_offer_outcomes` |
| `docs/config-reference.md` | updated | `trade.outcome_tracking` |
| `docs/integrations/sleeper.md` | updated | §5.2: the daily tick can now run the existing `transactions/{leg}` capture for leagues with open offers |
| ADR or `DECISIONS.md` entry | `D-216` | record observed statuses only; Part B stopped |

## 5. Ship gate declaration

- **CI green:** backend-tests (no mobile change).
- **Evidence recorded:** TEST_LEDGER entry by the integrating session.
- Express lane declared by the operator? No.

## 6. Acceptance evaluation (`backend/eval/acceptance_eval.py`, coordinator branch)

It can read outcomes from `trade_offer_outcomes`: `user_id`, `league_id`, `provider`,
`provider_transaction_id`, `proposal_event_id` (joins `trade_proposals` when that table is written),
`impression_id` (joins `deck_impressions` / the deck card), `give_asset_ids`, `receive_asset_ids`,
`sent_at`, `status`, `status_at`, `observed_terms_json`. An acceptance label is `status = 'accepted'`;
"not accepted" must be read as "no completion observed by `checked_at`", never as declined.
