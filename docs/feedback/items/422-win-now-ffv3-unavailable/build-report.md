# FB-422 build report — early, specific K/IDP refusal in `win_now_service`

**Date:** 2026-09-08 · **Branch:** `feat/fb422-win-now-slot-refusal` (base `8bd536df`) · **Builder:** G-422 backend build agent
**Spec:** [prd.md](prd.md) §3–5 · rulings in [reconciliation-log.md](reconciliation-log.md) (fix (b), copy as drafted, no client change)

## 1. What changed

| File | Change |
|---|---|
| `backend/win_now_service.py` | module import of `SLOT_POSITIONS`; pure helper `unsupported_slots_message`; early slot gate in `load_league`; the late `slots` comprehension moved up (no duplicate) |
| `backend/tests/test_win_now_service.py` | `ffv3_source_fixture()` (real FFV3 shape) + 4 tests |
| `backend/tests/test_win_now_api.py` | 1 route pass-through test |
| `docs/api-reference.md:1005` | one sentence in § Season projections and Win Now |

Not changed (per PRD §6): `season_simulator._validate` backstop, `SLOT_POSITIONS`, reason string `unsupported_roster_slots`, route contract, mobile, web, flags, schema, analytics.

## 2. Code walk (file:line on this branch)

- `backend/win_now_service.py:24` — `from .season_simulator import SLOT_POSITIONS` at module level. No import cycle: `season_simulator` imports only `season_forecasts` (`backend/season_simulator.py:18`), which `win_now_service` already imported at `:23`. The lazy `from .season_simulator import simulate_season` inside `load_bundle` is untouched, so tests that monkeypatch `simulator.simulate_season` still take effect.
- `backend/win_now_service.py:42-61` — `unsupported_slots_message(slots)`: distinct slots outside `SLOT_POSITIONS`, in roster order (`:49-52`); count of unsupported slots and total active slots (`:55-56`); the PRD §3(1) sentence verbatim (`:53,57-59`); the offense-only >12 sentence (`:60-61`).
- `backend/win_now_service.py:136-140` — the early gate. It sits immediately after the `missing_scoring_settings` check (`:134-135`) and **before** the standings loop (`:141-151`), the `/matchups/{week}` fetches (`:180`), and `_forecast_batch` (`:211`, called from `load_bundle:246`). Only `league`, `/rosters`, `/users` have been fetched at that point (`:123-126`). Condition mirrors `_validate` (`backend/season_simulator.py:54-56`): `len(slots) > 12 or any(s not in SLOT_POSITIONS for s in slots)`; the empty-lineup case is left to the backstop.
- `backend/win_now_service.py:138` — the `slots` comprehension formerly at old `:165` now runs here; `league["roster_slots"]` (`:196`) and `normalize_scoring_for_slots` (`:196`) read the same list.
- Serialisation unchanged: `backend/win_now_api.py:48-49` (`unavailable`) and `:58-59` (`guarded`) emit `{status:"unavailable", reason, message}` with HTTP 200. Rendering unchanged: `mobile/src/screens/WinNowScreen.tsx:195`, `web/js/win-now.js:231` show `message` verbatim.

Message produced for FFV3 (`python3 -c` against the fixed module):

> Win Now can't model this league yet. Its starting lineup uses K, DL, LB, DB, IDP_FLEX (8 of 15 starting slots), and season projections cover QB, RB, WR and TE only. Kicker and IDP projections are not supported, so standings and trade search stay off for this league.

## 3. Tests — RED before the fix, GREEN after

Fixture `ffv3_source_fixture()` (`backend/tests/test_win_now_service.py:580`): the real FFV3 36-entry `roster_positions`, the PRD's ten `settings`, the real 55-key `scoring_settings` (12 `idp_*`, 9 kicker keys — fetched from the public Sleeper API 2026-09-08 and pinned as literals), 12 rosters at 0-0-0 with synthetic ids, 14 weeks of 6-pair matchups, and a fetch stub that records `calls` and returns `[]` for any `/projections/` URL. The load_bundle test also stubs `backend.outlook.bye_weeks.fetch_byes` so the pre-fix path never reaches the network.

RED run against the unmodified `backend/win_now_service.py` (tests written first; fix not yet applied):

```
FAILED test_win_now_service.py::test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch
    Failed: DID NOT RAISE <class 'backend.win_now_service.Unavailable'>
FAILED test_win_now_service.py::test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason
    AssertionError: assert 'missing_forecast_week:1' == 'unsupported_roster_slots'
FAILED test_win_now_service.py::test_unsupported_slots_message_names_distinct_slots_in_roster_order
    AttributeError: module 'backend.win_now_service' has no attribute 'unsupported_slots_message'
3 failed, 1 passed   (the pass is test_offense_only_lakeview_slots_pass_the_slot_gate — GREEN before and after, as the PRD states)
FAILED test_win_now_api.py::test_projection_route_returns_slot_refusal_message_verbatim
    AttributeError: module 'backend.win_now_service' has no attribute 'unsupported_slots_message'
1 failed
```

GREEN run after the fix: `5 passed in 0.36s` (the five tests by node id).

| Test | Line | Proves |
|---|---|---|
| `test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch` | `test_win_now_service.py:612` | `load_league` raises `unsupported_roster_slots`; message names K, DL, LB, DB, IDP_FLEX, "8 of 15", "QB, RB, WR and TE"; no `/matchups/` or `/projections/` URL fetched |
| `test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason` | `:623` | `load_bundle` refuses with the slot reason and message; zero projection URLs fetched (was 17 + `missing_forecast_week:1`) |
| `test_unsupported_slots_message_names_distinct_slots_in_roster_order` | `:633` | helper: `["QB","K","DL","DL","LB","IDP_FLEX"]` → "K, DL, LB, IDP_FLEX (5 of 6 starting slots)"; 13 offense-only slots → the "at most 12" sentence, no IDP wording |
| `test_offense_only_lakeview_slots_pass_the_slot_gate` | `:645` | Lakeview's 24-entry `roster_positions` → `load_league` succeeds with the 10 active slots (over-refusal guard) |
| `test_win_now_api.py::test_projection_route_returns_slot_refusal_message_verbatim` | `test_win_now_api.py:574` | 200, `status == "unavailable"`, `reason == "unsupported_roster_slots"`, `message` passed through verbatim (contains `IDP_FLEX`, `8 of 15`), no `teams` key |

## 4. Suite results

- Owned files + backstops: `python3 -m pytest backend/tests/test_win_now_service.py backend/tests/test_win_now_api.py backend/tests/test_season_simulator.py backend/tests/test_season_history.py backend/tests/test_season_forecasts.py -q` → **184 passed in 2.94s** (includes `test_unsupported_rules_fail_closed[K]`, `test_season_history.py`, `test_season_forecasts.py` backstops).
- Full suite: `python3 -m pytest backend/tests -q` → ****5872 passed, 1 skipped in 664.45s (0:11:04)**, exit 0 — the pre-fix baseline (~5,867 / 1 skipped) plus the five new tests. Started in the foreground; the harness moved it to a background task when it passed the 600 s ceiling, and the completion notification carried the result line above.**

Scratch SQLite only (`data/trade_finder.db*` removed before each run); no production database, no live network (the fixture literals were captured once from Sleeper's public league endpoint to pin the real shape).

## 5. PRD deviations

1. **Helper test count "4 of 6" → "5 of 6".** PRD §5 row 3 expects `["QB","K","DL","DL","LB","IDP_FLEX"]` → "(4 of 6 …". Four is the number of *distinct* unsupported names; the signed-off FFV3 sentence uses the *slot* count ("8 of 15", where distinct would be 5). The two cannot both hold, so the helper counts slots (matching the operator-approved FFV3 copy) and the test asserts "5 of 6". Flagged for the QA agent/operator.
2. The offense-only sentence ends exactly as drafted ("… support at most 12 starting slots.") without the "so standings and trade search stay off" clause, because the PRD quotes it that way.

## 6. Operator checklist

Unchanged from `prd.md` §8 — runs after Render is LIVE on the merge sha with the existing 1.17.1 (149) binary.
