# FB-422 mini-PRD — Win Now on FFV3: refuse K/IDP lineups early and say why

**Date:** 2026-09-08 · **Path:** fast-track bug (backend only) · **Group:** G-422 · **Status:** planned, not built
**Inputs:** [investigation.md](investigation.md) (root cause, full reason table, local reproduction) · [scope.md](scope.md) · batch [plan.md](plan.md)

## 1. Repro

1. Sign in as mattmurf77, switch to FFV3 (`1312140920132497408`; starting slots `QB RB RB WR WR TE FLEX K DL DL LB LB DB DB IDP_FLEX`).
2. League → "Season projections & Win Now" (or Trades → "Win Now").
3. Server fetches 17 weeks of Sleeper projections (~10 s), then answers 200 `{"status":"unavailable","reason":"unsupported_roster_slots","message":"Unsupported roster slots"}` (98 bytes; production 2026-09-06 17:50:19Z, reproduced locally byte-for-byte).
4. Screen shows only "Unsupported roster slots" under `win-now.unavailable`. No standings, no search, no explanation → "Winnow still not working on ffv3".

## 2. Root cause (evidence tier 1: production body size + unmodified code path run locally on live public data)

- `season_simulator._validate` (`backend/season_simulator.py:54-56`) refuses any active slot outside `SLOT_POSITIONS` (`:21-23`: QB/RB/WR/TE/FLEX/SUPER_FLEX/REC_FLEX/WRRB_FLEX) or more than 12 active slots. FFV3 has 15 active slots, 8 of them K/DL/LB/DB/IDP_FLEX. Sole reason returned: `unsupported_roster_slots`.
- `win_now_service.load_bundle` raises `Unavailable(reasons[0])` with no message (`backend/win_now_service.py:261-263`); `Unavailable` auto-generates "Unsupported roster slots" (`:34-38`). Route serialises it as-is (`backend/win_now_api.py:48-49,58-59`).
- The slot check runs only after `load_league` has fetched rosters/users/14 matchup weeks and `_forecast_batch` has fetched 17 projection weeks (`:183-209`), although `roster_positions` was in the very first response (`:165`).
- Clients render `message` verbatim (`mobile/src/screens/WinNowScreen.tsx:195`; `web/js/win-now.js:231`). The four-word message is the whole user experience.
- This is the specified behaviour for K/DEF/IDP formats (`docs/plans/win-now/BUILD.md:78`, `HISTORICAL-VALIDATION.md:34`). Not a regression of #420, whose PRD §1 never claimed FFV3 forecasts were available.

## 3. Fix — option (b): legitimate refusal made honest, specific and early

Not (a): supporting K/IDP means a new projection position set, IDP/kicker stat keys, `DL/LB/DB/IDP_FLEX` eligibility and model re-validation — a model change, not a bug. Not (c): nothing is cached; the refusal recomputes from source every call and reproduced against an empty store.

**Backend, `backend/win_now_service.py` only:**

1. Add a pure helper `unsupported_slots_message(slots) -> str`. Distinct unsupported slot names in roster order, plus counts. Target copy (final wording is the builder's, must keep every fact):
   > Win Now can't model this league yet. Its starting lineup uses K, DL, LB, DB, IDP_FLEX (8 of 15 starting slots), and season projections cover QB, RB, WR and TE only. Kicker and IDP projections are not supported, so standings and trade search stay off for this league.

   Offense-only lineups with more than 12 active slots get: "… It starts N players and season projections support at most 12 starting slots."
2. In `load_league`, compute `slots` immediately after the `missing_scoring_settings` check (today `:111-112`; move the list comprehension from `:165`) and, before any standings/`/matchups` work, `raise Unavailable("unsupported_roster_slots", unsupported_slots_message(slots))` when any slot is outside `season_simulator.SLOT_POSITIONS` or `len(slots) > 12`. Import `SLOT_POSITIONS` at module level (no cycle: `season_simulator` imports only `season_forecasts`).
3. Leave `season_simulator._validate` untouched as the backstop. Reason string `unsupported_roster_slots` is unchanged (simulator vocabulary, `season_history.model_support`, api-reference).

Effect: FFV3 is refused in one round-trip (league meta + rosters + users), no projection burst, and the message names the slots, the supported positions, and that nothing the user can do in-app changes it. Permanent-format refusal now precedes transient ones (`live_week_unsupported`, forecast gaps), so FFV3's message is stable across the week.

**Mobile: no change.** `WinNowScreen.tsx:195` already prefers `baseline.message`; the fallback copy "This league format or forecast source is not supported yet." and `win-now.unavailable`/`win-now.disabled` testIDs stay. No new binary needed — 1.17.1 (149) shows the new text on the next Render deploy. **Web: no change** (`win-now.js:231` same pattern).

## 4. Files

| File | Change |
|---|---|
| `backend/win_now_service.py` | `unsupported_slots_message`, early slot gate in `load_league`, module import of `SLOT_POSITIONS` |
| `backend/tests/test_win_now_service.py` | FFV3-shape fixture + 4 tests (§5) |
| `backend/tests/test_win_now_api.py` | 1 route pass-through test (§5) |
| `docs/api-reference.md` § Season projections and Win Now (~`:1005`) | one sentence: active K/DEF/IDP slots (or >12 active slots) return `unsupported_roster_slots` before any projection fetch, with the slot names in `message` |
| `docs/feedback/items/422-win-now-ffv3-unavailable/status.md`, `INDEX.md`, `living-memory/TEST_LEDGER.md` | phase log / ledger by the build+QA agents |

## 5. Regression guards (pytest; each defect test must be shown RED on `b8d37085` before the fix)

Fixture `ffv3_source_fixture()` in `test_win_now_service.py`: the **real FFV3 shape** — the exact 36-entry `roster_positions`, `settings` {`playoff_week_start` 15, `playoff_teams` 6, `league_average_match` 0, `divisions` 0, `start_week` 1, `playoff_round_type` 0, `playoff_seed_type` 0, `best_ball` 0, `trade_deadline` 12, `trade_review_days` 0}, the real 55-key `scoring_settings` (13 `idp_*`, 8 kicker keys), 12 rosters at 0-0-0 with synthetic ids, 14 weeks of 6-pair matchups, fetch stub recording `calls` and returning `[]` for any `/projections/` URL.

| Test | Proves | RED today because |
|---|---|---|
| `test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch` | `load_league` raises `Unavailable`, `reason == "unsupported_roster_slots"`, message contains `K`, `DL`, `LB`, `DB`, `IDP_FLEX`, `8 of 15`, `QB, RB, WR and TE`; no `/matchups/` or `/projections/` URL in `calls` | `load_league` returns a league today (`pytest.raises` fails) |
| `test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason` | `load_bundle` raises `unsupported_roster_slots` with the specific message; `calls` has zero `/projections/` URLs | today raises `missing_forecast_week:1` (forecast gap wins because the slot check runs last) and 17 projection URLs were fetched |
| `test_unsupported_slots_message_names_distinct_slots_in_roster_order` | helper: `["QB","K","DL","DL","LB","IDP_FLEX"]` → "K, DL, LB, IDP_FLEX (5 of 6 …" (the count is unsupported starting SLOTS, matching the FFV3 "8 of 15" sentence; amended 2026-09-08 at build); 13 offense-only slots → the "at most 12" sentence | helper does not exist |
| `test_offense_only_lakeview_slots_pass_the_slot_gate` | Lakeview's 24-entry `roster_positions` (10 active, incl. `SUPER_FLEX`) → `load_league` succeeds with 10 slots | guard against over-refusal (GREEN before and after; stated as such) |
| `test_win_now_api.py::test_projection_route_returns_slot_refusal_message_verbatim` | 200, `status == "unavailable"`, `reason == "unsupported_roster_slots"`, message contains `IDP_FLEX`, no `teams` key | helper missing → the test's own `Unavailable(...)` construction fails |

Existing backstops stay green: `test_season_simulator.py::test_unsupported_rules_fail_closed[K]`, `test_season_history.py:103`, `test_season_forecasts.py:240`. Mobile: `tsc --noEmit`, `check-win-now.js`, `check-win-now-recovery.js`, testid-lint unchanged. Code-walk proof for rendering: `WinNowScreen.tsx:99-101` (200 body → `baseline`), `:125` (`available` false), `:195` (message shown).

## 6. Not changed

- No K/DEF/IDP projection support; no change to `SLOT_POSITIONS`, `SUPPORTED_SCORING_KEYS`, `normalize_scoring_for_slots`, or `_validate`.
- No reason-string rename, no schema, no flag, no analytics event, no route contract change (still 200 `{status,reason,message}`).
- No mobile/web code; no new binary. Entry points still advertise Win Now for every league (flag-gated, unchanged).
- The injury-tag availability policy (`season_forecasts.py:273-276`, `season_simulator.py:201-203`) — see §7.

## 7. Open questions for the operator

1. **Lakeview is also unavailable** (investigation §6): the 17:57:29Z 114-byte body is `unknown_starter_availability:1:1` (roster 1 starts three `Questionable` players). In-season this will refuse most offense-only leagues most weeks with an equally opaque message. Recommend a separate item: (i) decide the policy (treat `Questionable` as available, or exclude the player, or keep refusing), and (ii) humanise the coverage messages by naming team and player. Not folded into G-422 unless you say so — it is a model-policy call.
2. Copy sign-off on the sentence in §3(1).

## 8. Operator checklist (after Render is LIVE on the merge sha; existing 1.17.1 (149) binary)

1. FFV3 → League → "Season projections & Win Now". **Expect** within ~2 s: the new sentence naming K, DL, LB, DB, IDP_FLEX and "QB, RB, WR and TE only"; no standings, no priority buttons, no "Find Win Now trades". **Fail** if it still reads "Unsupported roster slots" or takes ~10 s.
2. Tap "Refresh season projections" → same sentence, again fast.
3. Render logs: `GET /api/league/season-projections?league_id=1312140920132497408` → 200, body ≈ 300 bytes, **no** `projections/nfl/2026/<w>` burst immediately before it.
4. Lakeview → Win Now. **Expect** anything *except* the K/IDP sentence — today that is "Unknown starter availability:1:1" (or "Current-week play may have started…" while week-1 games are live). **Fail** if Lakeview shows the slot sentence.
