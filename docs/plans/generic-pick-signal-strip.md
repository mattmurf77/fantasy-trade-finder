# Feature Scope — generic-pick trade-signal strip (A2)

**Date:** 2026-10-24
**Entry point:** direct ask. Finding A2 is from models-eng, the ruling is from head-eng, and the replay ruling is from models-lead (5b(i)), all relayed by trades-eng.
**Builder:** trades-eng worker, branch `fix/generic-pick-signal-strip`
**Operator sign-off on waivers:** not needed. The only waivers are analytics (no event, by ruling) and the TestFlight checklist (server-only, no client change).

---

## Problem

The 12 generic pick rungs `generic_pick_{1..4}_{early,mid,late}` sit in every user's
RankingService pool so they can be ranked (`backend/server.py:1665-1691`). No engine
ever puts one on a trade card. But four routes build a trade signal from **client-sent**
give and receive ids, with no asset-kind check:

| Route | How a client id reaches the signal |
|---|---|
| `POST /api/trades/queue` | `_reconstruct_swipe_card` (`server.py:16673`) → `record_trade_signal` (`:16703`) → `save_trade_swipes` (`:16726`) |
| `POST /api/trades/swipe` | FB-46 rebuild (`:16143`) → `record_trade_signal` (`:16181` / `:16191`) → `save_trade_swipes` (`:16257`) |
| `POST /api/trades/pass-reason` | FB-46 fallback (`:17026`) → `_apply_reasoned_pass_elo_only` → `save_trade_swipes(pass_reason_key=…)` (`:17107`), then `record_trade_signal` if it wrote (`:17115`) |
| `POST /api/trades/matches/<id>/disposition` | a match minted from such a like → `record_disposition_signal` (`:20782`) → `save_trade_swipes` (`:20791`), for both users |

Before this change, both `record_trade_signal` and `record_disposition_signal` only skipped
ids that were not in the pool, and the rungs are always in the pool. So a client-sent
generic-pick pair moved that user's generic-pick ratings live, and again on every
`replay_from_db` at session init.

- **Disposition is live today.** Disposition K is never frozen (`database.py:10147-10148`).
- **The other three routes are dormant.** Their K is zeroed today by the `trade.bakeoff`
  freeze. They go live when release-lead lifts it with `bakeoff_freeze_trade_k`, a knob that
  is not on `main` as of `4697311b`.

## The fix — at the signal layer, not per route

One helper, `pick_values.strip_generic_pick_pair(winner_ids, loser_ids, *, site)`
(`backend/pick_values.py:246`). It is import-safe from anywhere, because `pick_values` imports
only `logging` at module load, and every caller imports it lazily.

- It drops every id where `parse_generic_pick_id(id) is not None`. Lookalike ids that
  `parse_generic_pick_id` rejects are kept.
- If either side is left empty, it returns `([], [])` (`:261`): the pair is skipped whole and
  a one-sided signal is never recorded. Mixed sides keep their players.
- **Counter:** module-level `GENERIC_PICK_STRIP_COUNTS[site]` (`:243`), plus one `log.info`
  per call that drops anything (`:264`). There is no analytics event.

It is applied in exactly three functions:

1. `RankingService.record_trade_signal` (`backend/ranking_service.py:709`). The strip runs at
   `:749`, before the pairwise decomposition.
2. `RankingService.record_disposition_signal` (`:763`). The strip runs at `:784`. Disposition
   K is unchanged: models-lead ruled that K 20 outside the freeze is intended.
3. `database.save_trade_swipes` (`backend/database.py:5960`). The strip runs at `:5996`, so a
   generic id is never persisted.

### `save_trade_swipes` return value: unchanged for every input

Today the function returns:
- `None` with no `pass_reason_key`, whether or not any rows were written;
- with a key, `False` when nothing decomposes or the reason is missing or already claimed;
- otherwise `True`, after claiming and inserting in one transaction.

Its only reader is `_apply_reasoned_pass_elo_only` (`server.py:17107-17120`: `if wrote:` …
`return bool(wrote)`). That value becomes the pass-reason route's `elo_written`
(`server.py:17084`). The swipe, queue and disposition callers ignore the return.

**The choice:** the return keys off the **unstripped** pair (`had_pairs`, `database.py:5994`).
A pair that the strip empties still opens the transaction, claims the reason (sets
`elo_signal_at`) and returns `True`; it simply inserts no rows (`:6011`, `:6020`).

Why:
- `elo_written` and the reason-claim state stay exactly as before for every request.
- Consuming the claim is right: the signal was handled, and a retry would strip the same pair
  again anyway.
- The follow-on `record_trade_signal` call (`server.py:17115`) receives the same generic ids
  and strips them too, so the live board and the persisted rows still agree.

### Unchanged

Cards, `save_trade_decision` rows, every route, every response, `replay_from_db`.
There is no API, schema, flag, `model_config` or event change.

## Replay: unchanged

Replay is unchanged, and historical rows stay (models-lead 5b(i)). Correcting existing
boards is BL-003, a later, operator-approved job. The parked strip is on the local branch
`hold/bl-003-replay-strip`, which is not pushed. Its tip sha is in the trades-eng hand-off,
because a commit cannot name the sha of a commit built on top of it.

The STOP-check finding behind this ruling:
- `replay_from_db` uses each row's **write-time** `k_factor` (`ranking_service.py:1247`), and
  `_compute_elo` applies it as is.
- The bake-off freeze (`bakeoff_runner.elo_freeze_mult`) is applied only at write time, and
  disposition K is never frozen.
- So a replay strip would change existing boards whenever generic rows with `k > 0` exist in
  prod: both the rung and the ordinary player on the other side of the row would move.
- A read-only prod count of such rows is pending on the operator's list.
- `test_replay_is_forward_only_a_historical_generic_row_still_moves_the_board` pins that this
  branch leaves replay alone.

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED. No analytics needed:** the head-eng ruling allows a log counter only, so
  there is no event. Engines never emit generic ids on cards, so the strip fires only on
  client-echoed context. `GENERIC_PICK_STRIP_COUNTS` and the `generic-pick strip [...]` log
  line are enough to see whether it ever fires in prod.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `swipe_decisions` simply stops receiving generic-id rows.
- **New/changed feature flags:** none. The change is unflagged: it is a correctness fix with no
  user-visible surface. The rollback lever is `git revert` of the single commit.
- **New env vars / `model_config` keys:** none.

## 3. Evidence scope

- [ ] **Structural guard:** n/a. There is no mobile change.
- [x] **Unit tests:** `backend/tests/test_generic_pick_signal_strip.py`, 17 tests.
  - All four routes go through the Flask test client, each with a mixed card and a
    generic-only card. Each runs twice, once with the pre-fix pass-through helper and once
    with the real one. The tests assert:
    - an identical status and body;
    - identical `trade_decisions` rows and pass-reason claims;
    - the generic pairs gone, live and persisted;
    - every generic rating at its seed;
    - ordinary pairs kept at the same K;
    - the pre-fix run really leaked, so no test passes vacuously.
  - Ordinary-only cards per route: everything is identical, with K equal to the configured value.
  - The pass-reason `elo_written` / claim pin.
  - Helper unit tests, covering the counter and the log line.
  - `save_trade_swipes`' `None` return.
  - Forward-only replay.
- [x] **Code-walk proof:** see "The fix" above (file:line).
- [ ] **Manual TestFlight checklist:** WAIVED. The change is server-only, and no response
  changes, so there is nothing for a device to observe.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route was added, renamed or removed, and no contract changed. Every response is byte-identical, which the route tests pin. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `docs/config-reference.md` | n/a | No env var, flag or `model_config` key. |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted. The invariant "trade-signal K is mirrored in the persisted row" still holds. |
| `docs/architecture.md` | n/a | No module wiring or data flow changed. One helper was added to an existing module. |
| `living-memory/HLD.md` | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` | n/a | No shared constant or enum. |
| `docs/glossary.md` | n/a | No new domain term ("generic pick rung" already exists). |
| ADR or `DECISIONS.md` entry | n/a here | The decisions are head-eng's (signal-layer strip) and models-lead's (5b(i), forward-only). Logging them is the lead's call. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha. trades-eng pushes.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry is written at ship by trades-eng. This branch edits no living-memory files, per its brief.
- **TestFlight verification:** none (§3 waiver).
- **Express lane declared by the operator?** No. The full gates apply.
