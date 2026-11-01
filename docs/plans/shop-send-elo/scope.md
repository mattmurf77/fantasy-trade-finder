# Feature Scope — Shop send keeps its Elo signal (#531 follow-up, stacked on #574)

**Date:** 2026-11-01
**Entry point:** direct ask. head-product's call: keep the Elo signal for Shop sends. head-eng: build it as a stacked server PR, with the `send` row as the anchor.
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. The one waiver (§3 TestFlight) is a backend-only change whose client half is #574's checklist.

## The change

#574 replaced the Shop tile's queue button ("Show it to @name") with the platform send router, and send-only dropped the Elo signal. head-product kept the signal, without the deck card. #574 tags a Shop send's propose request `source: "shop"`. This PR answers that tag on all three propose routes (Sleeper, MFL, ESPN), before the platform call:

- **The anchor:** a `trade_decisions` row with `decision = "send"` and the queue's deterministic `calcq_` id. It is never a like, so the counterparty gets no likes-you card, and there is no match or Awaiting entry.
- **The Elo:** exactly the queue route's path, through the same functions. `fit_congruence_mult(None, "like")`, the bake-off `elo_freeze_mult`, `record_trade_signal`, then `save_trade_swipes` at `trade_k_like`.
- **The event:** `trade_proposed` with `props.source = "shop"`, fired iff the row is written.
- **Once per package:** nothing happens when the package already has a send row, or a live like with any `trade_id` (deck, calculator, or a pre-#574 Shop queue).
- **The bar:** the queue's D-170 bar. The session's league, and a counterparty this session resolves to a league-mate who isn't the caller.
- **Intent, not outcome:** it records before the platform call and stands whatever the platform answers.
- **Never fails the send:** every error is logged and swallowed.

`trade_proposals.source` also gains `shop` (`_PROPOSE_SOURCES`). An unknown or absent value is still `deck`.

## 1. Analytics scope

- [x] **(b) Existing events cover it:** `trade_proposed`, server-fired, with `props.source = "shop"`, a value already in the closed set (`_SWIPE_SURFACES`).
  - It fires once per recorded `send` row, timed to the write (analytics-lead's rule, via head-eng). So a Shop-only ESPN or MFL user still counts toward WAT and first opinion.
  - It no longer carries the "calculator" mislabel the pre-#574 Shop queue had.
  - **`props.decision = "send"`** (analytics-lead, 11-01): the event mirrors the row, so `trade_proposed.decision` becomes the closed set `like` | `send`. It is on record in analytics-lead's report. There's no history and no coded reader of `props.decision`, so there is no series break. Experiment `like_rate` matches on event type only; analytics-lead has recorded a `decision = 'like'` filter as a precondition before any experiment uses it.
  - **Also for analytics-lead:** the `traded` segment (`analytics_queries._product_op`) now reads `decision IN ('like', 'pass')`. That's its documented definition, so a send-only user is not "traded".
  - The event and the props are unchanged; the taxonomy comment and the invariants enum note are updated.

## 2. Schema & flag scope

- **Tables/columns:** none new. `trade_decisions.decision` gains the value `send`. It is a plain string column with no CHECK and no enum; the only index is the plain `(user_id, league_id, decision)`. `docs/data-dictionary.md` is updated.
- **Flags:** none. The propose routes' own flags gate it: `trade.send_in_sleeper`, `trade.send_in_mfl`, `espn.send`. A flag-off route records nothing.
- **Env vars / `model_config`:** none. Elo rides the existing `trade_k_like` and the bake-off freeze.
- **Rollback lever:** deploy-free, two ways. The Elo half is inert unless a client sends `source: "shop"`, so turning a send flag off stops it with that route. A revert of this PR restores today's behaviour, in which `shop` is ledgered as `deck`. Existing send rows stay invisible to like readers either way.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_shop_send_elo.py`, 61 tests (60 pass; one skips until #389 merges). It reuses `test_calc_trade_queue.py`'s harness, so the queue and the send run in the same world.
  - **The record:** the row, the Elo and the event.
  - **Parity with the queue:** same pairs, same K, with the bake-off freeze live.
  - **#389:** a generic pick takes no signal. It skips on this base, and was verified against #389's diff: it passes, and goes red with the strip disabled.
  - **No deck card:** likes-you, the injector, mirror-match, Awaiting, the analytics `traded` and `liked_trades_min`, and the offline replay.
  - **A send never acts as a pass barrier,** even with no timestamp.
  - **The deck's decided keys:** 7 days, never a pass.
  - **Account deletion and export** of send rows.
  - **Once only:** a repeat send, a queued package, a deck like (by package), a league-mate's like, a retracted like, and a like renewed by a later pass.
  - **The G-049 replay skip:** no event and no persisted Elo.
  - **The D-170 bar:** six cases, plus the caller in the test-only member shape.
  - **Never raises.**
  - **Routes:** all three. They record before the platform call, stand whatever the platform answers, record nothing for any other source (the ledger value is checked for each), record nothing with the flag off, and a failing signal never blocks the send.
- [x] **Sabotage:** 33 single-rule breaks, each RED (TEST_LEDGER lists them). Two readers filter twice: Awaiting (its SQL, then `history.actionable`) and the global like rate (its SQL, then the `like`/`pass` keys). Their sabotages break both layers.
- [x] **release-lead's QA notes at 4996e091:**
  - The Awaiting test now seeds `league_members`, so a real like in the same world is awaiting. It was vacuous before.
  - A parametrised pin covers the Thompson shape counts, the global like rate, engine telemetry and negmem's retraction leg. Each is zero for a send and one for a like.
  - The event now fires even if `save_trade_swipes` raises after the row commits (tested).
- [x] **Code-walk proof:** the reader audit below, file:line-cited.
- [x] **Manual TestFlight checklist — WAIVED because:** backend-only. The client half (`source: "shop"`) is #574's and is covered by its guard. Runtime proof of the Elo half is a server read, which is out of scope for agents (no prod reads).
- `testID`s: none.

### Reader audit: every reader of `trade_decisions`, and what it does with a `send` row

| Reader | Treatment of `send` |
|---|---|
| `save_trade_decision` replay window (`database.py`) | matches only earlier `send` rows (`decision == decision`) |
| `TradeInterestHistory.__init__` barrier | **hardened:** an unstamped row is a barrier only if like/pass |
| `.discovery_keys` (D-067; `_load_trade_disposition_keys`, prepared runtime, bake-off, likes-you skips) | **decided like a like:** 7-day window, never a pass. That matches the pre-#574 Shop queue's like row, so the deck doesn't re-serve a package just sent |
| `.resolved`, `.actionable`, `.renewable`, `.likes`, `_queue_like_resolved` | ignored: like-only or pass-only |
| `load_recent_league_likes` → likes-you injector | ignored (`.likes`) |
| `find_live_trade_like` → queue idempotency | ignored (`decision == "like"`) |
| `find_mirror_like` / `check_for_match` | ignored (`.likes`) |
| `load_awaiting_trades`, `retract_awaiting_likes`, R4 exclusions | ignored (SQL `decision == "like"`) |
| `ensure_reasoned_trade_pass` | ignored (pass/like filters) |
| `load_trade_decision_shape_counts`, `load_legacy_shape_counts`, `load_global_like_rate`, `load_engine_telemetry` | ignored (`IN ('like', 'pass')`) |
| `negmem` retraction leg | ignored (`IN ('pass', 'like')`) |
| analytics `traded` segment | **fixed:** now `WHERE decision IN ('like', 'pass')`, its documented definition |
| analytics `liked_trades_min` | ignored (`decision = 'like'`) |
| `scripts/replay_trade_decisions.py` | **fixed:** like/pass only |
| `load_active_deck_user_leagues` (F10 replenish cron) | counted as league activity, which is the intent |
| `prepared_trade_runtime.dependency_receipt` | hashed like any row; cache churn only, the same as a like/pass |
| `eval/scorecard_evidence.py` | exported raw, no decision interpreted |
| `load_trade_decisions` | no filter; no production caller |
| `accounts.delete_user_data` / `export_user_data` | deleted and exported by `user_id`, like any row (tested) |
| `deletion_scrub` (#557/#559/#562, not on main) | doesn't touch `trade_decisions`. A send row has no partner column; its `calcq_` id is a hash, the same exposure as a calculator like today |

**Known, unchanged, and open with head-product** (release-lead P3-3, against "no double count"):
- A calculator ✓ of a package already sent adds a second Elo signal. `find_live_trade_like` reads likes only, so the queue doesn't see the send row's shared `calcq_` id.
- A sent package can come back to the deck after 7 days. The pre-#574 Shop like sat in Awaiting, and R4 excluded it for as long as it was live.

Both are small to change; they wait on head-product's call. The rest is unchanged:
- A later deck like or calculator queue of a package already sent adds its own Elo. That is the same as today's deck like plus a queue of one package. The 7-day decided window keeps the deck from re-serving it.
- The probe and the write are serialised by the per-user `service._lock` in one process. Production runs one worker.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | the propose routes' `source` values gain `shop`, plus the Elo half's contract |
| `living-memory/LLD.md` | updated | `trade_decisions` gains `send`, and new readers must filter like/pass |
| `docs/architecture.md` | n/a | no module wiring change: three routes call one helper in `server.py` |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | updated | the `trade_proposed` `source` enum note: `shop` is also server-stamped by the propose routes |
| `docs/data-dictionary.md` | updated | `trade_decisions.decision` gains `send`; `trade_proposals.source` gains `shop` |
| `docs/glossary.md` | n/a | no new user-facing term |
| ADR or `DECISIONS.md` entry | updated | D-210 |
| `backend/analytics_taxonomy.py` | updated | `trade_proposed.decision` is `like` \| `send`, and the `source` props comment |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` | updated | the Elo half's `trade_proposed` (`send`), no series break, the experiment `like_rate` precondition |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`.
- **Evidence recorded:** TEST_LEDGER.
- **Order:** after #574, which carries the client tag. There is no binary dependency: until this lands, the tag is ledgered as `deck`.
- **Deploy before the 11-06 binary reaches users** (analytics-lead's condition). #574 also passes the Shop idea's impression, so without this PR's allow-list every Shop send lands in `trade_proposals` as `deck` and inflates the deck's confirmed sends. Shop sends would also emit no `trade_proposed`; if the binary reaches users first, that needs a SERIES_BREAKS row dated that day. analytics-lead's confirmed-send read is `trade_proposals WHERE source = 'shop'`, which needs `trade.valuation_telemetry` on (it is, via env, since 09-05).
- **Merge hold:** none left. analytics-lead's `props.decision` answer is on record.
- Express lane declared by the operator? No.
