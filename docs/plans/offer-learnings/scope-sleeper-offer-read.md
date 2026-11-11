# Feature Scope — WS2b: read the user's own Sleeper offers (R3 Part B)

**Date:** 2026-11-10
**Entry point:** direct operator ask — `plan.md` §3 WS2b; the operator approved the private read on
2026-11-10 ("I'm aligned on the private read"). What Sleeper returns:
[sleeper-offers-read.md](sleeper-offers-read.md); the consent design is WS2's
([scope-trade-outcomes.md](scope-trade-outcomes.md) §0 "Part B, if the operator wants it later").
**Builder:** WS2b builder, branch `feat/sleeper-offer-read` (from `feat/offer-learnings`)
**Operator sign-off on waivers:** needed — §1 (no analytics event), and the four decisions in §0.6.

---

## 0. What is built

### 0.1 The read

One GraphQL operation, `league_transactions_filtered`, on `https://sleeper.com/graphql`, sent by
`sleeper_write.league_trade_offers` through the same `_post_graphql_data` transport as
`propose_trade` (raw JWT in `authorization`, the browser headers, `api_observability.observe_call`
labelled `graphql.league_transactions_filtered`, the same auth classification). `_post_graphql` was
split in two so the read gets the list Sleeper returns; the propose path's behaviour is unchanged.

- Variables: `league_id`, `type_filters: ["trade"]`, `limit: 200`. No `status_filters` (every
  status comes back), no `roster_id_filters` / `leg_filters` (the capture never exercised them).
  Variables rather than inlined literals: standard GraphQL, and nothing user-supplied reaches the
  query text. **Assumption:** Sleeper accepts the operation with variables; the capture records the
  argument names and types, not whether the web app inlines them.
- Selection: `transaction_id type status created status_updated creator roster_ids consenter_ids adds
  drops draft_picks waiver_budget metadata settings`. No `player_map`, no message or chat field.
- Credential: the Send-in-Sleeper token already stored for the user (`sleeper_credentials`,
  decrypted per call, never logged or persisted elsewhere). No new credential, no other private call.

### 0.2 When it runs

`server._sleeper_offers_sync(user, league)` is the only caller. It reads only when there is a reason
(an app-sent offer in that league that Sleeper may still move, or the user's import consent), the
user has a credential that has not expired, the league is a Sleeper league, and the throttle allows:

| Trigger | Where |
|---|---|
| Find a Trade opened | `POST /api/trades/generate` → `_sleeper_offers_kick` → one daemon thread (never on the request path) |
| Daily tick | step `sleeper_offers` (after `trade_outcomes`): app-sent targets in the last 30 days, then the consenting users' leagues synced in the last 45 days; at most 100 reads |

Throttle (`sleeper_offer_read.due`, process-local, one gunicorn worker): at most one read per
(user, league) per 30 minutes; after an auth failure (401/403, auth-worded GraphQL error, or an
expired token) no read for that user in any league for 24 h; after any other failure (HTTP error,
transport, a non-list answer, the public rosters read failing) none for that league for 6 h.
**A failure changes nothing**: the credential is not deleted (unlike a failed send), no row is
written, and one WARNING is logged; inside the back-off there is no call and no log. Never a loop.

### 0.3 Status mapping (offers sent through the app)

| Sleeper | Rule | Stored `status` |
|---|---|---|
| `proposed` | | `sent` (unchanged; `checked_at` refreshed) |
| `complete` | | `accepted` (`resolved_transaction_id` = the offer) |
| `rejected` | `metadata.rejecter_id` on the other side | `declined` |
| `rejected` | rejecter on the creator's side | `withdrawn` (never seen in the capture; defensive) |
| `cancelled` | rejecter on the creator's side | `withdrawn` |
| `cancelled` | no rejecter | `lapsed` |
| `cancelled` | rejecter on the other side (never seen) | `lapsed` (no revised-offer card can come from it) |
| `declined` or `lapsed`, with a linked counter | | `countered`, plus `counter_status` |

"On my side" means the user id owns or co-owns the user's roster (`sleeper_roster`'s predicate,
from one public `rosters` read per sync). `accepted`, `declined`, `withdrawn` and `lapsed` are final:
the read never moves them. `sent`, `completed_different_terms` (WS2's public reconcile) and
`countered` (its counter may still move) are updated.

The linked counter's own state (`counter_status`): `pending` (proposed), `accepted` (complete),
`declined` (the user rejected it), `withdrawn` (the other manager cancelled it), `lapsed`
(cancelled, no rejecter), `countered` (the user countered back: a later `is_counter` offer from the
user linked to it). Its terms are stored from the user's side (`counter_terms_json`).

### 0.4 Counter linking, and how often it could be wrong

Sleeper flags a counter (`settings.is_counter`) but does not name the offer it answers. Rule
(`link_counters`): an offer T that is no longer `proposed` is answered by the earliest unclaimed
`is_counter` transaction C with the same two rosters, created by the **other** side of T, with
`C.created` in `[T.status_updated − 60 s, T.status_updated + 10 min]`. Offers are matched in the order
they closed; each counter answers at most one offer.

It can be wrong only when the same two rosters have two offers closed within ~10 minutes of each other
and a counter between them (it then goes to the one that closed first), or when a manager sends a
fresh `is_counter` offer minutes after an unrelated offer between the same pair closed. In the
operator's capture (170 trades, 20 counters, three leagues) the counters could not be checked
against a ground truth: the capture kept counts, not pairs. Measuring the error rate needs the
operator to label a sample (TestFlight checklist item 6); until then it is an untested assumption
that the 10-minute window is tight enough. A wrong link changes the status word between `declined`
and `countered`, and WS8's card between a revision and a middle ground; it never shows one user
another's offer.

### 0.5 Consent and import

- Table `offer_import_consents`, append-only: `(user_id, kind grant|withdrawal, terms_version,
  recorded_at, via)`. Consent = the latest row is a grant at `TERMS_VERSION`
  (`offer-import-draft-1`); a grant at an older version is not consent.
- `GET/POST/DELETE /api/sleeper/offer-import`, verified sessions only. POST echoes the terms version
  the app showed (409 `terms_changed` otherwise) and needs a Send-in-Sleeper link (409
  `sleeper_not_linked`). DELETE works with the flag off.
- **Revoke deletes what was imported in the same transaction** as the withdrawal row
  (`database.withdraw_offer_import_consent`; a failure inside it rolls both back, tested). Rows for
  offers sent through the app are kept: they are WS2 Part A's data, not an import.
- Account deletion: `offer_import_consents` joins `accounts._ADDITIONAL_PRIVATE_TABLES`
  (`test_account_deletion_coverage.py` is parametrized over it); `trade_offer_outcomes` already was.
- Import (only while consented): every two-team trade in the answer that involves the user's
  roster and is not already an app row is stored with `source = 'sleeper_import'`, `direction`
  `sent` | `received`, the other side as a league roster id, asset ids from the user's side (players
  as Sleeper ids, picks as this league's FTF pick id `{league}_{season}_{round}_{original_roster}`,
  FAAB counted in `extras_json`), status and counter fields by the same rules, `sent_at` = Sleeper's
  `created`. Three-team trades and other managers' completed trades are skipped.
- Privacy: trades only. The read returns only the signed-in user's own non-complete offers (per the
  capture); rows are keyed by the account id and every read filters by it, so one user never sees
  another's. Two consenting managers of one league each get their own row (the unique key became
  `(user_id, provider, provider_transaction_id)`). Never stored: the token, `metadata`, `settings`,
  any Sleeper user id from the answer (tested by scanning every stored row).
- App: one switch in Settings › Leagues (`components/SleeperOfferImportRow`), off by default, shown
  only with the flag on, a server answer and a Sending-in-Sleeper link. Every word is the server's.

### 0.6 Decisions for the operator

1. **Settled at integration (coordinator, operator away): consent covers every private read.** The
   operator's condition was "with explicit user permission", so `_sleeper_offers_sync` returns
   `no_consent` and makes no private call unless the user has turned the switch on, for offers
   sent through the app as much as for the import. A user who has not opted in keeps WS2's
   public-data outcomes (accepted, completed on different terms) and gets no revised-offer cards.
2. **Counter terms** are therefore stored only for consenting users.
3. **The Terms line** (below) was approved by the operator on 2026-11-10 ("New wording approved")
   and is published verbatim in `web/terms.html` §6, with matching lines in `web/privacy.html`
   (§1, §3, §4, §5, §6); both pages' effective date moved to November 10, 2026 and the consent
   version became `offer-import-1`. The switch shows its own short version, served by the backend
   (`sleeper_offer_read.TERMS_LINE`). The published line says the read also covers trades sent from
   the app; the app is stricter than that and reads nothing until the switch is on (decision 1).
4. **WS2's unique key changed** to include `user_id`. WS2 is not on `main`, so no production table
   has the old constraint; a local DB created from the integrated branch before this commit keeps the
   old one (re-create it, or two consenting managers of one league collide on import).

### 0.7 Terms line (approved 2026-11-10; published in `web/terms.html` §6)

> **Trade outcomes.** When you send a trade from the app, we record what happens to it in your
> league, for example whether it was accepted or declined, to improve the trades we suggest. To do
> that for a Sleeper league we use the Sleeper sign-in you gave us for Send in Sleeper to read the
> trade offers in your own account. If you turn on "Use my Sleeper trade offers", we also keep the
> other trade offers you send and receive on Sleeper in your linked leagues, and what happened to
> each. We read only trade offers and their outcomes, never your messages or chats. You can turn this
> off at any time in Settings, and when you do we delete the offers we imported.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics event needed because:** consent is a durable append-only record
  (`offer_import_consents`), outcomes are durable rows, and a read's result is one structured log
  line (`sleeper offers read league=… trigger=… {stats}`) plus `api_observability`'s outbound
  `graphql.league_transactions_filtered` event when `obs.api_events` is on. `analytics_taxonomy.py`
  and `NON_INTENT_EVENTS` are unchanged.

## 2. Schema & flag scope

- `trade_offer_outcomes`: seven columns (`source`, `direction`, `counter_transaction_id`,
  `counter_status`, `counter_status_at`, `counter_terms_json`, `extras_json`) in the `Table` and in
  `migration_cols`; unique key `(user_id, provider, provider_transaction_id)`.
- New table `offer_import_consents` (create_all).
- `docs/data-dictionary.md` updated for both.
- Flag `trade.sleeper_offer_import`, default **off**, registered in `feature_flags.FLAG_KEYS`,
  `config/features.json` (+ comment), `release.json` / `onboarding-v2.json` / `profiles-on.json`,
  `docs/config-reference.md`. Off ⇒ no call (sync returns before any read), no thread spawned
  from Find a Trade, the tick step `skipped flag off`, `GET`/`POST` 404, no payload key anywhere.
- No env var, no `model_config` key: the throttle, window and budget are module constants.
- Graduation: on for the operator's account for two weeks with the TestFlight checklist below
  passing in all three leagues and no `sleeper offers read failed (auth)` lines beyond token expiry.

## 3. Evidence scope

- [x] **Unit / route tests:** `backend/tests/test_sleeper_offer_read.py` (65 tests) — the client's
  request shape and failure classes; each status from the fixture; each counter state; linking rules
  (pair, side, flag, window both ends, one counter per offer, none for a pending offer); import with
  and without consent, idempotence, per-user rows, final statuses never moved; consent grant /
  repeat / version / link / revoke + same-transaction delete + atomicity / flag-off withdraw /
  verification; flag off no call; throttle; failed and unauthorised reads change nothing, back off,
  log once; expired token; failed rosters read; linked-platform league; the Find a Trade kick; the
  daily-tick step; nothing stored carries the token, metadata, settings or a user id; registration.
  Fixture: `backend/tests/fixtures/sleeper/offer-read/` (synthetic ids, every status word, both pick
  shapes, FAAB, three-team, counters inside and outside the window, a counter countered back).
  `test_daily_tick_route.py` STEP_KEYS gains `sleeper_offers`.
- [x] **Structural guard:** `mobile/tests/check-offer-import.js` (24 checks), `npm run test:offer-import`.
- [x] **Code-walk proof:** §0 above, file-cited.
- Sabotages (each proven RED, then GREEN on revert; recorded in TEST_LEDGER): see the ledger entry.
- testIDs added: `settings.sleeper-offer-import.switch`.

### Manual TestFlight checklist (the operator's three Sleeper leagues)

Server: `FTF_FLAGS` with `trade.sleeper_offer_import` and `trade.outcome_tracking` on; app build
with this commit. Sign in, Settings › Leagues shows Send in Sleeper connected.

1. Settings › Leagues: the switch "Use my Sleeper trade offers to improve suggestions" is there,
   **off**, with the line about trade offers, never messages. With Send in Sleeper disconnected the
   switch is gone.
2. In league 1, send a trade through the app to a league-mate you can ask to decline it. After they
   decline in Sleeper, open Find a Trade (wait ~10 s), then check the row (operator query on the
   server DB: `SELECT status, status_at FROM trade_offer_outcomes WHERE provider_transaction_id =
   '<tx>'`): `declined`, with Sleeper's time.
3. Send another, then withdraw it in Sleeper: `withdrawn`. Send a third and let it expire: `lapsed`
   once its `expires_at` passes and Find a Trade is reopened 30+ minutes later.
4. Send a fourth; have the league-mate counter it in Sleeper; open Find a Trade: `countered`,
   `counter_status = pending`. Decline the counter in Sleeper; 30+ minutes later reopen: `counter_status
   = declined`.
5. Turn the switch on. Reopen Find a Trade in each league (30+ minutes apart per league). Rows with
   `source = 'sleeper_import'` appear for offers made in Sleeper directly, sent and received, none
   from trades between two other managers.
6. Counter linking check: for each `countered` row, confirm in Sleeper that the linked counter
   (`counter_transaction_id`) really answered that offer. Report any wrong link (this is the only
   measure of the 10-minute window).
7. Turn the switch off: the line "Imported offers deleted." shows; every `sleeper_import` row is gone;
   the app-sent rows remain.
8. Server logs (Render): `sleeper offers read league=` lines appear at most once per league per 30
   minutes per user, and `sleeper offers read failed` never shows a token.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET/POST/DELETE /api/sleeper/offer-import`; daily-tick step (4b) `sleeper_offers` |
| `docs/data-dictionary.md` | updated | `trade_offer_outcomes` columns + key; `offer_import_consents` |
| `docs/config-reference.md` | updated | `trade.sleeper_offer_import` |
| `docs/integrations/sleeper.md` | updated | operation 18 `league_transactions_filtered`; failure row |
| `docs/runbook.md` | updated | daily-tick order |
| `docs/architecture.md` | updated | `sleeper_offer_read.py` |
| `docs/glossary.md` | updated | Trade outcome; Imported offer; Linked counter |
| `living-memory/LLD.md` | n/a | no convention shift (same leaf-module + flag pattern as WS2) |
| `living-memory/HLD.md` | n/a | no new client or major flow; one read behind existing triggers |
| `docs/cross-client-invariants.md` | n/a | no client reads the status vocabulary |
| `web/terms.html`, `web/privacy.html` | updated | §0.7's line, approved 2026-11-10; privacy §1, §3, §4, §5, §6 |
| `DECISIONS.md` | updated | `D-225` — the private read, its throttle and consent |

## 5. Ship gate declaration

- **CI green:** full backend suite on this branch (TEST_LEDGER); `npx tsc --noEmit`,
  `check-offer-import.js`, `testid-lint.sh` clean.
- **Express lane declared by the operator?** No.
