# HLD — Calibration: in-app blind grading (value-core Gate 2)

**Date:** 2026-10-02 · **Status:** spec · Companion: [scope.md](scope.md) · [prd.md](prd.md) · [lld.md](lld.md) · [specs.md](specs.md)

All file:line citations are to `feat/blind-grading` at `9e2fc45b`.

Users see the feature as **Calibration**. The code and data keep `grading`.

## 1. Shape of the system

```
 iOS app (mobile/)                          backend/server.py (routes only)                    backend/blind_grading.py (NEW service)
 ─────────────────                          ──────────────────────────────                    ─────────────────────────────────────
 TabNav (presence decided once at mount)    @_grading_gate — 404 unless BOTH:
   Rank · Acquire · [Calibration|Draft]       _grading_flag_for_caller(sess)  (global ∪ overlay)
           · Matches · League                 _calibration_allowed(sess)       (THE audience predicate)
   Calibration → CalibrationStackNav        @_gate_unverified_{read,write}   (403)
     → CalibrationHome = CalibrationScreen  POST /api/grading/sessions ────────────────────▶ create_session ─┬─ database.load_open_grading_session
        ├ GradingCard (neutral payload)       gathers ServerInputs:                           │              ├─ database.load_grading_legacy_deck  (current arm)
        ├ grade 1–5 · tags · Skip · Next       _value_core_standings (:7462)                  │              ├─ value_core_bench.read_league_inputs (app engine)
        └ GradingResults (post-completion)     _league_lineup_slots (:28686)                  │              │    → league_record → snapshot_for_seat
   (no own FeedbackFAB: RootNav's global      _sleeper_roster_limit (:29899)                 │              ├─ value_core.pipeline.run (default config)
    mount covers tab screens)                  load_asset_preferences (:7861 pattern)         │              ├─ merge → shuffle(seed) → neutral_trade
 api/grading.ts — api from ./client,        GET  /api/grading/sessions/current ────────────▶ current_session │              └─ database.insert_grading_session
   sends X-Device-Id on every call          GET  /api/grading/sessions/<id>/next ──────────▶ next_card       │
                                            POST /api/grading/cards/<id> ──────────────────▶ answer_card     │  (atomic completion on the last answer)
                                            GET  /api/grading/sessions/<id>/results ───────▶ results         │  (only reader of arms_json, with report)
                                            GET  /api/admin/grading/report (X-Cron-Secret) ─▶ report          │
                                                                                                             ▼
                                                                         backend/database.py: grading_sessions, grading_cards (+ helpers)
```

There are three backend layers, each with one job:
- **Routes (`server.py`)** gate access and gather the league facts only the server owns: Sleeper standings, the lineup template, roster capacity and preference lists. They map `GradingError` to JSON.
- **The service (`backend/blind_grading.py`)** owns everything else: arm sourcing, merge, shuffle, the one neutral formatter, validation and scoring. It never imports `backend.server` or `backend.tools`.
- **`database.py`** owns the two tables and their helpers (`backend/CLAUDE.md` § Database).

On mobile, Calibration is a **bottom tab in the Draft tab's third slot**. Its presence is decided once at launch from the merged flag map. When the tab is present it takes the slot ahead of Draft, so the bar never exceeds 5 tabs. The Draft tab itself is switched off for everyone (`draft.tab` → false); its code is untouched.

## 2. Data flow

### 2.1 Launch: which tabs exist

1. **Boot.** `App.tsx` gates the splash on the cached flags (`loadCachedFlags`). `revalidateFlags` then fetches `/api/feature-flags` in the background (`mobile/CLAUDE.md` § App.tsx boot contract).
2. **Merged flag map.**
   - The server returns global `flags` plus `configs` for the caller's device and account units (`server.py:26233-26294`).
   - The client merges `configs[*].flags` over the global map (`mobile/src/api/flags.ts:52-66`).
   - A tester inside `calibration_rollout` therefore gets `grading.blind = true`; everyone else gets the global `false`.
3. **Mount.** `TabNav` mounts and reads `useFeatureFlags.getState().flags` **once**:
   - `showCalibrationTab = !!flags['grading.blind']`;
   - `showDraftTab = !!flags['draft.tab']`, which is unchanged code (`TabNav.tsx:716-718`).

   The third slot renders `showCalibrationTab ? Calibration : showDraftTab ? Draft : nothing`.
4. **Lag.** The flag map that is current at mount wins until the next launch. The first launch after the overlay starts may still show the old bar, because the cached map loads before the fetch lands. This is the documented `draft.tab` behavior (`TabNav.tsx:700-718`); the checklist says to relaunch.

### 2.2 Create (`POST /api/grading/sessions {league_id}`)

1. **`_grading_gate` (outermost).** Look up the session by token; none ⇒ 404. Then two predicates, both required:
   - **`_grading_flag_for_caller(sess)`.** True if `is_enabled("grading.blind")` is true globally. Otherwise, true if any running-experiment overlay for the caller's `device:<X-Device-Id>` or account unit (`sess["user_id"]`) sets `grading.blind: true`. The overlay comes from `experiments.resolve_for_unit` (`experiments.py:320-342`), the same per-unit resolution and merge `/api/feature-flags` performs. Server and client agree by construction.
   - **`_calibration_allowed(sess)`.** THE audience predicate: the session `user_id` or league user id is in `_load_tester_allowlist()` (`server.py:26789`, the `_value_core_live` rule at `:7456-7458`). Opening to everyone later means this function returns `True`.

   Either false ⇒ 404 `not_found`. After the gate, `_gate_unverified_write` applies (403 for unverified).
2. **`_require_initialized_session()`** (`server.py:2570`). `league_id` must equal the session's active league, else 400 `league_not_active`. This keeps `_league_user_id` (`server.py:2594`) unambiguous.
3. **Resume short-circuit.** `blind_grading.current_session(...)`. An open session ⇒ 200 `{session, resumed: true}`, with no network.
4. **The route builds `ServerInputs`**, mirroring the value-core serving path `_run_value_core_job` (`server.py:7495-7505`):

   | Input | Source |
   |---|---|
   | standings | `_value_core_standings(league_id, platform)` (`:7462`; Sleeper only, fail-soft to `({}, 0)`) |
   | lineup slots | `_league_lineup_slots` |
   | roster limit | `_sleeper_roster_limit` (Sleeper only) |
   | untouchables / not-interested | `load_asset_preferences`, when `trade.preference_lists` is on (`server.py:7859-7866`) |

5. **`blind_grading.create_session`**, in order:
   1. **Current arm** ([§3.1](#31-current-arm-todays-engine)), first because it is cheap.
   2. **League inputs:** `value_core_bench.read_league_inputs(conn, league_id, today)` on `database.engine`. This is the app's own DB, never prod tooling.
   3. **Catalog:** one consensus catalog for display (G6).
   4. **Value-core arm** ([§3.2](#32-value-core-arm)).
   5. **Merge** by (partner, give set, receive set).
   6. **Shuffle** with `random.Random(seed)`, where `seed = secrets.randbits(63)`.
   7. **Format** each card with `neutral_trade`.
   8. **Mint ids, then insert** the session and its cards in one transaction.
6. **201** `{session, resumed: false}`.

### 2.3 Grade

- **`GET …/<id>/next`** returns the lowest-`position` card with `grade IS NULL AND skipped = 0`, as `{card_id, position, trade}` (`trade` is the stored `trade_json` verbatim). When none remain it returns `{done: true}`.
- **`POST /api/grading/cards/<id>`** runs in one transaction:
  1. validate (grade 1–5, or `skip: true`; tags ⊂ the fixed 7);
  2. check ownership and that the session is open;
  3. update the card;
  4. count what remains, and if nothing does, set the session `completed` with `completed_at`.

  The response carries `session_status`.

### 2.4 Reveal

- **`GET …/<id>/results`.**
  - Completed ⇒ a per-arm summary over the session's cards. A card credits every arm in its `arms_json`.
  - Open ⇒ 409 `session_incomplete`.
- **`GET /api/admin/grading/report`.** `_require_cron_auth()` (`server.py:24339`). Not gated by the flag or audience (D4). It aggregates overall, per grader and per session.

## 3. Arm sourcing

### 3.1 Current arm (today's engine)

**What it reads.** `deck_impressions`, through `database.load_grading_legacy_deck(user_id, league_id)`. `user_id` is the **account** id: impressions are written with `g_user_id` (legacy job `server.py:9007-9008`; value-core job `:7562-7563`).

**Qualifying row** — every predicate below runs in SQL:

| Predicate | Why |
|---|---|
| `COALESCE(is_ghost,0)=0` | Ghosts were withheld from display (`database.py:950-956`) |
| `model_arm IS NOT NULL` | NULL means no arm produced the card, which is a likes-you injection (`server.py:5428-5437`). It is also NULL on every row of a pinned or partner deck, because the bake-off runs on organic decks only (`bakeoff_runner.py:455-467`). |
| `model_arm <> 'value_core'` | Value-core serving rows (`server.py:5505-5518`) |
| `source_like_impression_id IS NULL` | Injected because the partner liked the mirror |
| `trade_intent IS NULL` | Intent-filtered decks answer a different brief from the value core, which has no intents |
| `assets_json IS NOT NULL` | The package is needed; `trade_hash` can't be inverted |

**Which job.** The newest `deck_job_id` by `MAX(served_at)` **among qualifying rows** (D1).

**Then, in Python:**
1. Drop rows whose `features_json.standing_offer` is true (`server.py:5244-5245`).
2. Take the first 20 by `card_index`, which is the final served position (`database.py:933`).
3. Drop **stale** cards. A card is stale if the partner is no longer a member or is the viewer, if any give id is no longer held by the viewer, or if any receive id is no longer held by the partner. "Held" means `league_members.roster_data` ∪ the member's owned platform picks.
4. Drop **unknown** cards, meaning any asset missing from the catalog.

**Refusals: 409 `needs_fresh_deck`,** with `reason`:
- `missing`: no qualifying job;
- `stale`: `served_at` is more than 7 days old;
- `too_few`: fewer than 10 usable cards.

**Dependencies:** `deck.signal_v2` (writes the rows), `suggestion.telemetry` (`assets_json`) and `trade.bakeoff` (`model_arm`). All three are true today.

### 3.2 Value-core arm

1. **`read_league_inputs`** ([lld.md §5](lld.md#5-bench-refactor-backendevalvalue_core_benchpy)) is the DB half of `_freeze_league`, extracted unchanged except for:
   - the pick predicate fix (D6);
   - three additive display columns: `players.team`, `draft_picks.is_traded`, `draft_picks.original_username`.
2. **`league_record(**inputs, meta=None, state=None)`** (`value_core_bench.py:109`). Then override from `ServerInputs`: `lineup_slots` (when known), `max_players`, `standings` and `completed_weeks`. This gives the snapshot the serving path's sources rather than the bench's offline Sleeper fetch.
3. **`snapshot_for_seat(record, seat, standings_weight=0.30)`** (`value_core_bench.py:385`) builds the windows, the partner boards and the viewer's shrunk board.
4. **`Request`:** `viewer_team_id=seat`, `board`, and the untouchable / not-interested ids cut to the snapshot's assets.
5. **`pipeline.run(snapshot, request, CoreConfig(), RankConfig())`** (`value_core/pipeline.py:15`). Keep the first 20 entries.
   - Fewer than 10 ⇒ 409 `value_core_too_few`.
   - Any exception ⇒ logged, then 503 `value_core_failed`.
   - **Seat** = `_league_user_id(sess)`.

## 4. Blinding guarantees

| # | Guarantee | Mechanism | Enforced by |
|---|---|---|---|
| G1 | One formatter | Every `trade_json` comes from `neutral_trade(partner_id, give, receive, catalog)`, which is never passed arm data. Output keys are fixed: `{partner_name, give, receive}`, and per asset `{id, name, position, nfl_team, age, value}`. | `test_neutral_trade_has_exact_keys…`, `test_neutral_trade_identical_for_both_arms`, `check-blind-grading` rule 2 |
| G2 | Arms are stored once and hidden | Arm membership and provenance live only in `grading_cards.arms_json`. Only `results()` (completed sessions) and `report()` (cron secret) read it. | code-walk-backend claim 3; e2e |
| G3 | A shared trade is one card | Merge key = (partner, frozenset(give), frozenset(receive)). One card is credited to both arms; a duplicate would reveal "this one is in both". | `test_merge_shared_trade_one_card_both_arms` |
| G4 | Order and ids carry nothing | A secret 63-bit seed drives `random.Random(seed).shuffle` and is never returned. Positions are assigned after the shuffle. Ids are random 18-digit decimals. | `test_shuffle_deterministic_for_seed…`; e2e |
| G5 | Sides are normalised | Each side is sorted by (−value, name, id), whatever order the engine used | `test_neutral_trade_has_exact_keys_and_sorted_sides` |
| G6 | One value source | Players: `elo_to_value(player_value_history.consensus_elo)`. Picks: `draft_picks.pool_value`. Never the legacy row's `give_value`/`receive_value` (stud tax), never any value-core score. | `test_neutral_trade_identical_for_both_arms` |
| G7 | Counts are hidden until completion | Per-arm counts live in `counts_json`. Before completion a response exposes only `progress {answered, total}`. | e2e |
| G8 | No engine ids | No `impression_id`, `trade_id`, `deck_job_id`, `trade_concept_id`, reasons, scores, `basis`, `lane` or `model_arm` in any non-admin response before results | e2e deep scan |
| G9 | The client renders neutral fields only | A dedicated `GradingCard`, not `TradeCard` with props stripped. Arm labels appear only in `GradingResults`, rendered once in the results phase. | `check-blind-grading` rules 1–3 |

**Residuals** (accepted, [prd.md §10](prd.md#10-risks-and-residuals)):
- **R1 familiarity.** The current arm is the deck the grader just opened.
- **R2 card properties.** The fairness-band shape hints at the engine.
- **R3 data export.** `arms_json` is included.
- **R4 admin route.** Cron-secret holders see arms.
- **R5 timing.** Creation latency is per session, not per card.

## 5. Isolation from the real deck

**Grading never touches:**
- `trade_service._trade_cards`, the `TradeCard` registry swipes resolve against (registered at e.g. `server.py:7551`, `:8120`);
- `log_trade_impressions` or `_log_deck_signal_impressions`;
- `record_event`;
- any `/api/trades/*` route;
- `RankingService`.

Card ids are not trade ids, so a grading answer cannot reach `/api/trades/swipe`. `value_core.pipeline.run` is pure: no logging, no I/O (`pipeline.py:1-7`). The only writes are `insert_grading_session` and `answer_grading_card`. Pinned by `test_create_session_writes_no_engine_tables` and code-walk claim 2.

## 6. Gating

| Layer | Rule | Kill |
|---|---|---|
| **Server** | `_grading_gate`, the outermost decorator: 404 unless `_grading_flag_for_caller(sess)` **and** `_calibration_allowed(sess)`. It runs before the verified gates, so flag-off and non-tester callers get the same 404 with no existence signal (the `_test_users_denied` posture, `server.py:26792-26809`). | Stop `calibration_rollout`. 404 within the 60 s experiment cache (`experiments.py:82`). |
| **Client tab** | `showCalibrationTab` comes from the merged map at mount. Not reactive: a mid-session flag change cannot insert or remove a tab under the user's thumb (`TabNav.tsx:700-718`). | Next launch after the flag refetch |
| **Client screen** | Any 404 renders "Calibration isn't turned on for this account". This covers a stale tab between kill and relaunch. | — |
| **Audience widening (future)** | `_calibration_allowed` → `return True`, plus `grading.blind` true globally or the overlay retargeted. | — |

**Why the server resolves the overlay instead of reading the global flag.**
- The operator wants the tab for testers only. The client tab therefore keys off a value only testers receive: the overlay.
- If the server checked only the global flag, the global flag would have to be on, and every user would see the tab.
- If the server checked nothing, stopping the experiment would leave the routes answering.
- Resolving the caller's effective flag keeps one meaning for `grading.blind` on both sides, and makes stopping the experiment a real kill.

## 7. Performance

**Create.**

| Step | Cost |
|---|---|
| DB reads | well under 1 s (`ix_deck_impressions_user_league`; one league's members, players and history) |
| Standings | 0.2–2 s (`build_league_state`; weekly matchups cached by `_outlook_sleeper_fetch`) |
| Lineup and roster meta | cached (#179) |
| Value core | typically 1–4 s, hard budget 8 s |
| Gate: `resolve_for_unit` ×≤2 | the experiment cache (60 s TTL) plus one indexed `users` read for the account unit (`experiments.py:241-267`). Every grading call pays this. |
| **Total** | **2–8 s expected, ~12 s worst case** |

**Mobile timeout.** POSTs default to 15 s (`client.ts:245`). `/api/grading/sessions` joins `SLOW_POST_PATHS` for 30 s (`client.ts:249`). POSTs never auto-retry on gateway errors (`client.ts:519-521`), and the resume rule makes a manual retry safe.

**Single sync worker** (`render.yaml:16`). Creation blocks other requests for its duration. Acceptable for 1–3 graders (D5).

## 8. Failure modes

| Failure | Behavior |
|---|---|
| Overlay absent / not allowlisted / no session | 404 `not_found` on every user route |
| Unverified session | 403 `verification_required` (existing decorators, after the gate) |
| Session not initialized (create) | 409 `session_not_initialized` (existing; the client retries, `client.ts:276-292`) |
| `league_id` ≠ active league | 400 `league_not_active` |
| League not synced, or the caller's seat is not a member | 409 `league_not_synced` |
| No fresh legacy deck | 409 `needs_fresh_deck` + `reason` |
| Standings / lineup / roster fetch fails | Fail-soft defaults, the same as serving |
| Experiment engine off or erroring | `resolve_for_unit` returns `{}`, so the caller is treated as overlay-off ⇒ 404. Fail closed. |
| No `player_value_history` rows (e.g. local dev) | Markets are 0 ⇒ 409 `value_core_too_few`. The runbook says to run `POST /api/cron/value-snapshot` first. |
| Value core raises | `log.exception`, 503 `value_core_failed`. Nothing is written. |
| Answer after completion / results before completion | 409 `session_completed` / 409 `session_incomplete` |
| Double-tap Start | Resumes the open session (the single sync worker serialises requests) |
| Tab still visible after a kill (pre-relaunch) | Every call 404s, and the screen shows the "isn't turned on" state |

## 9. Reused vs new

| Concern | Reused | New |
|---|---|---|
| Tester allowlist | `experiments.load_tester_allowlist` (`experiments.py:120`) | `_calibration_allowed` wraps it: the one predicate |
| Per-unit flag overlay | `experiments.resolve_for_unit` (`experiments.py:320`), plus the merge rule in `/api/feature-flags` | `_grading_flag_for_caller` (server-side mirror of `flags.ts:52-66`) |
| League inputs → snapshot | `value_core_bench.league_record` / `snapshot_for_seat` | `read_league_inputs`, extracted from `_freeze_league` |
| Standings / slots / capacity | `_value_core_standings`, `_league_lineup_slots`, `_sleeper_roster_limit` | — |
| Engine | `value_core.pipeline.run` | — |
| Scoring arithmetic | The definitions in `blind_grade._score` (`blind_grade.py:99-105`) | `summarize` (re-implemented; the private function is not imported) |
| Account deletion / export | The `accounts._ADDITIONAL_PRIVATE_TABLES` loop (`accounts.py:780`, `:989`) | two names |
| Tabs | The `DraftStackNav` pattern, mount-once presence, `trackTab`, `popNestedToTop` re-tap (`TabNav.tsx:620-640`, `:716-737`, `:844-865`) | `CalibrationStackNav`, `showCalibrationTab` |
| Mobile primitives | `Card`, `Badge`/`PositionBadge`, `Button`, `Meter`, `Text`, `TickLabel`, `Icon` | `GradingCard`, `GradingResults`, `CalibrationScreen` |
