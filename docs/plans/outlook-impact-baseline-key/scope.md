# Feature Scope — outlook impact baseline: cache key covers every caller input

**Date:** 2026-11-03
**Entry point:** release-lead's independent QA of #512 (a separate finding about existing code on main), owned by league-eng (team-review)
**Builder:** league-eng (one backend worker)
**Operator sign-off on waivers:** pending. The waivers below (analytics (c), TestFlight checklist) go to the operator through league-eng.

---

## 0. Problem and fix

`_outlook_impact_baseline(league_id, basis, sess)` in `backend/server.py` builds the playoff baseline (a `LeagueState` and one baseline sim) and caches it for 15 min in `_OUTLOOK_IMPACT_CACHE`. The cache is the performance design: a 30-card deck shares one baseline instead of paying 60 simulations.

The key is `(league_id, basis)`, but the bundle also depends on three inputs read from the calling session:

| Input | Where it's read | Bases |
|---|---|---|
| `board_elo`: the caller's own board | `sess["service"].get_rankings(...)` | personal |
| `fmt = _active_format(sess)`: the caller's effective format | pool, `resim_baseline(scoring_format=fmt)`, returned in the bundle | both |
| `svc_seed = sess["service"]._seed` | merged over the pool seed | both |

So within 15 min, caller B in the same league can be served a baseline built from caller A's inputs. There are two consumers, and both flags are on:
- **`GET /api/league/team-review`:** every member's playoff band (`standing.outlook`, the window, the partners beat);
- **`POST /api/trade/evaluate`:** the `outlook_impact` block via `_trade_outlook_impact`, always consensus.

Mobile only sends `basis=consensus`, so the personal-board case needs a direct API call.

**Reproduction (2026-11-03, test-first, lines at `fd5390ac`):** all three are real.

| Input | How it varies between two callers in one league | Red on the old key |
|---|---|---|
| Board (personal) | `board_elo` is the caller's own board (`server.py:1469-1471`). This also fails for two co-owners of one roster, who rank separately | `B was served A's board` |
| Format | Per session and per request, never per league. `_require_session` takes a valid `X-Scoring-Format` header, else `sess["active_format"]` (`:2738-2740`). `active_format` is set at session init (`:28014-28033`) and changed per session by `/api/scoring/switch` (`:15658`); mobile uses both (`mobile/src/api/auth.ts:227`, `mobile/src/api/rankings.ts:52-58`) | `B was served A's format` |
| Session seed | `RankingService._seed` is set once, from the pool as it stood when the session was built (`ranking_service.py:408`; `server.py:27862-27888`). A players-refresh bumps the pool generation (`:2103`, `:2108`), but sessions keep the old seed and player list until their next init. The current pool wins on overlap (`:1461-1463`), so the leak is players the refresh dropped who are still on a roster: priced by an old session, 0 and position `"?"` for a fresh one | `B was served A's stale pool` |

**Fix:** the key is `(league_id, basis, fmt, board_owner, sess["pool_generation"])`. `fmt` is `_active_format(sess)`, now read before the cache check. `board_owner` is `sess["user_id"]` (the account id, not `_league_user_id`, so co-owners don't share a personal board) on `basis=personal` with a service, else `None`. Consensus callers with the same format and pool generation keep sharing one entry. TTL, sim counts and the bundle shape are unchanged. The comment above the cache states the new key and drops the old "(league, basis, completed_weeks)", which was never the key. The matching line in `resim_baseline`'s docstring (`backend/outlook/trade_delta.py`) is corrected too.

## 1. Analytics scope

- [x] **(c) WAIVED.** No event is added, changed or removed. This is a server-internal cache-key correction with no new user action or surface.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. The rollback lever for the affected blocks is the existing `outlook.odds` / `outlook.trade_impact`.
- New env vars / `model_config` keys: none

## 3. Evidence scope

- [ ] **Structural guard:** n/a (backend only; no mobile file touched).
- [x] **Unit tests:** new `backend/tests/test_outlook_impact_baseline_key.py`, 5 tests. It fakes Sleeper, the pool, the league context and `get_config`, builds sessions with the real `server._RequestSession`, and runs the real simulator at `DELTA_SIM_COUNT`. Each repro computes B's bundle alone first, then lets A fill the cache and asks again as B.

  | Test | Proves | Sabotage → result |
  |---|---|---|
  | (a) personal board, league-mates | B's values come from B's board | the old key → red |
  | (a) personal board, co-owners of one roster | each co-owner gets their own board | `board_owner` = `_league_user_id(sess)` → red (the only failure) |
  | (b) format | B on `sf_tep` never gets A's `1qb_ppr` bundle | format dropped from the key → red (the only failure) |
  | (c) pool generation | a fresh session never gets an old session's prices for dropped players | generation dropped from the key → red (the only failure) |
  | sharing | two consensus callers with different boards, same format and generation: one `resim_baseline` call, the same bundle object, one cache entry | `board_owner` set for consensus too → red (the only failure) |

  On the unmodified key: 4 failed, 1 passed (the sharing test also passes on the old code). With the fix: 5 passed. Regression: `test_team_review.py` + `test_bakeoff_arm_a_golden.py` 35 passed; `backend/tests/test_outlook_*.py` 185 passed, 1 skipped (the env-gated backtest). Local Python 3.14.4; CI runs 3.12.
- [x] **Code-walk proof:**
  - **The key** (`server.py:1453-1458`) is built before the lock. A hit returns the cached bundle, and a miss builds and stores under the same key. Each session-derived read below the key (`fmt`, `board_elo`, `svc_seed`, `players_meta`) is a function of format, board owner or pool generation.
  - **Both consumers read only the bundle.** `_trade_outlook_impact` unpacks `(state, baseline, player_value, player_pos, seed_type, fmt)` and re-sims the with-trade half from it. Team-review reads `base_payload["teams"]` for the bands. Neither reads the session again for anything the bundle stands in for.
- [x] **WAIVED: TestFlight checklist,** because this is server-only with no client change, and the response shape is unchanged. Only which cached baseline a caller receives changes.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No contract change. The cache isn't documented there, and the team-review and evaluate response shapes are unchanged |
| `living-memory/LLD.md` | n/a | No convention shift |
| `docs/architecture.md` | n/a | No wiring change. The baseline cache isn't described there |
| `living-memory/HLD.md` | n/a | No architecture shift |
| `docs/cross-client-invariants.md` | n/a | No shared constant |
| `docs/glossary.md` | n/a | No new term |
| ADR or `DECISIONS.md` entry | n/a | The choice (key on every caller input) is the cache's own stated contract, not a new decision |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry at merge
- **TestFlight verification:** none (waived above)
- Express lane declared by the operator? no

## Known limits (accepted)

- **Pool generation is close to, but not exactly, the seed.** Two sessions on the same old generation could still disagree on a dropped player's value. That needs two refreshes, plus that player's consensus value changing between them, plus only one of the two sessions being rebuilt by carrying values forward.
- **Sessions without a `pool_generation`** (extension, account-only, restored) share the `None` slot. Extension and restored Sleeper sessions can't reach team-review, which needs an initialized session.
- **Staleness right after a players-refresh** is unchanged. An entry built before the refresh can still be served for up to 15 min to sessions on the old generation. That isn't caused by the caller, so it's out of scope; fresh sessions get a new entry.

## Launch integration addendum — 2026-11-04

The launch batch includes the original `f2e759b7` fix and #512 together. Account deletion independently purges **both** personal outlook caches for every working/account alias returned by `accounts.deletion_scope`; consensus entries and other callers remain warm. Baseline computations register short-lived tickets under the cache lock; deletion removes matching tickets so a simulation already running cannot refill a deleted personal entry. Tickets are removed in `finally`, including on failure. #512's result-cache flights similarly become non-cacheable when their owner is purged. Existing requests may finish, but cannot reinsert that private output. No deleted-id tombstones are retained.

Additional evidence: deterministic threaded tests for deletion during baseline/result computation (personal discarded, consensus retained), baseline failure ticket cleanup, alias-aware deletion of both caches, and independence when either purge raises. The full combined launch evidence is in `living-memory/TEST_LEDGER.md`. Key fields, TTL, simulator counts, response shapes, flags and numeric defaults are unchanged.
