# Feature Scope — Calibration (in-app blind grading, value-core Gate 2)

**Date:** 2026-10-02
**Entry point:** direct ask. The lead asked on the operator's behalf; the operator decided the entry point and audience on 2026-10-02. This is Gate 2 of the value-core plan (does the plain value core grade as well as today's engine?), run as an app feature instead of the CSV in `backend/eval/blind_grade.py`.
**Builder:** spec author (this folder). The build runs as 4 parallel packages ([specs.md](specs.md)).
**Operator sign-off on waivers:** **pending.** One waiver, §1 (no grading-specific events). It must be shown to the operator before build.

Companion docs: [prd.md](prd.md) · [hld.md](hld.md) · [lld.md](lld.md) · [specs.md](specs.md). All file:line citations are to `feat/blind-grading` at `9e2fc45b`.

**Naming.** Users see **Calibration**. Code and storage keep `grading`: flag `grading.blind`, routes `/api/grading/*`, tables `grading_*`, service `backend/blind_grading.py`, wire module `mobile/src/api/grading.ts`.

> **2026-10-05 operator update.** Calibration is open to **every app user** (the app is TestFlight-only, under ten users): `grading.blind` is true in `config/features.json` and the three flags fixtures (code default still false), and `server._calibration_allowed` returns `True`. No `calibration_rollout` overlay and no allowlist edit are needed; the flag is the kill switch. `blind_grading.MAX_DECK_AGE_DAYS` is 14 (7 left four prod users eligible; 14 leaves eight). A new cron-secret route, `POST /api/admin/grading/pregenerate`, pre-builds a session for every candidate. §0 and §2 below describe the 2026-10-02 tester-only posture as scoped; the dated change-control line in [specs.md §3.3](specs.md#33-change-control) covers all five changes and their tests.

---

## 0. User-visible behavior (what changes for whom)

| Who | Before | After |
|---|---|---|
| Testers (tester allowlist, with the `calibration_rollout` overlay) | 5 tabs: Rank · Acquire · Draft · Matches · League | 5 tabs: Rank · Acquire · **Calibration** · Matches · League. Calibration sits in the Draft tab's third slot. |
| Everyone else | 5 tabs, Draft included | **4 tabs**: Rank · Acquire · Matches · League. **The Draft tab is gone**, because its seasonal switch `draft.tab` goes to false. |
| Everyone | Draft Room reachable from the Draft tab | Still reachable without the tab: League › **Rookie draft** tile (`LeagueScreen.tsx:697-704`, gated by `draft.room`, true at `config/features.json:215`) and the Draft chip on the Trades mode bar (`TradesScreen.tsx:6853-6861`). Both push the root-stack `DraftRoom`. |

**Draft tab handling.**
- The Draft tab's code is **not** deleted (operator, 2026-10-02).
- Turning `draft.tab` back on next draft season restores it with no code change.
- While a tester has Calibration, Calibration occupies the third slot, so that tester gets no Draft tab even if `draft.tab` is on ([lld.md §10.7](lld.md#107-edits-in-existing-files)).
- Tab presence is decided once, at app launch (`TabNav.tsx:700-718` convention), so a flag change shows on the next launch.

## 1. Analytics scope

- [ ] **(a) New events specced.** Alternative only, not recommended: server-fired `grading_session_started {league_id, total, resumed}` and `grading_session_completed {league_id, total, skipped}`. They would be registered in `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` (`analytics_queries.py:63`) in the same commit as the emitter.
- [x] **(b) Existing events cover the navigation half.** No new event names.

  | Existing event | What changes | Question it answers |
  |---|---|---|
  | `tab_selected {tab, from_tab, refocus, intercepted}` (`TabNav.tsx:725-737`; props `analytics_taxonomy.py:1046-1047`; NON_INTENT, `analytics_queries.py:75`) | A new value **`tab: "calibration"`** from `trackTab('calibration', …)`, and `from_tab: "calibration"` (the lowercased route name). **`tab: "draft"` / `from_tab: "draft"` stop arriving** while `draft.tab` is off. `tab` is a free string, not an enum, so no taxonomy edit is needed. | Do testers open Calibration, and from where. Any dashboard reading `tab = 'draft'` reads zero from the flip date; that is a real behavior change, not a data loss. |
  | `screen_viewed` / `screen_left` (`RootNav.tsx:503-511`) | A new `screen` value, **`CalibrationHome`** | Dwell on the grading screen |
  | `api_request_failed` (`client.ts:413-447`) | Covers failed grading calls. Session and card ids are 18-digit decimals, so `_normalizeRoute` (`client.ts:360-367`) folds them to `:id`. | Grading-call failures |

  Because `tab_selected` and `screen_viewed` are NON_INTENT, the new values cannot move DAU, WAU or intent metrics.
- [x] **(c) WAIVED for the grading data itself:** no `grading_*` events. The reasons:
  1. **The tables are the record.** `grading_sessions` / `grading_cards` hold who graded, when, the grade, the tags, skips and completion.
  2. **The admin report is the readout.** Gate 2 is read from `GET /api/admin/grading/report`.
  3. **Events would outlive the tool.** This is a 1–3-person tool that goes dark after Gate 2, and taxonomy entries are permanent schema.
  4. **No experiment readout exists.** The overlay rollout is an allowlist rollout, not a powered test.

  **Needs operator sign-off.**

→ Follow-through (P4): `docs/data-dictionary.md` gets the two tables, plus a note on the `tab_selected` value set (`calibration` added; `draft` absent while `draft.tab` is off).

## 2. Schema & flag scope

- **New tables:** `grading_sessions` and `grading_cards` ([lld.md §3](lld.md#3-schema)).
  - `metadata.create_all` in `init_db()` (`database.py:4192-4195`) creates them. `migration_cols` (`database.py:3265`) is unchanged, because no existing table gains a column.
  - Both carry `user_id`, and both join `accounts._ADDITIONAL_PRIVATE_TABLES` (`accounts.py:652-658`), so account deletion and data export cover them. The parametrised `test_account_deletion_coverage.py:48` then includes them.
  - → `docs/data-dictionary.md`.
- **New flag: `grading.blind`, global default false, and it stays false.**
  - **Registration:** `FLAG_KEYS` after `trade.value_core` (`feature_flags.py:1172`); `config/features.json` after `:268` with `_comment_grading_blind`; the three full-map fixtures `backend/tests/fixtures/flags/release.json` (exact mirror, `test_seed_ui_test_db.py:107-113`), `profiles-on.json` and `onboarding-v2.json`. **Not** `all-on.json`, which is a curated 42-key overlay (`backend/tests/CLAUDE.md` § Fixtures), and **not** the frozen 163-key snapshots `release-300.json` / `release-espn-send-off.json`, which lack it.
  - **Delivery:** it reaches testers **per unit**, through an allowlist-targeted experiment overlay, `calibration_rollout`. That follows the `mascot_ram_rollout` pattern ([../ram-mascot/experiment.md §2-§4](../ram-mascot/experiment.md)).
  - **Client resolution:** the client's merged flag map (`mobile/src/api/flags.ts:52-66`) decides the tab.
  - **Server resolution:** the server resolves the same per-caller value ([hld.md §6](hld.md#6-gating)) and **also** requires the tester allowlist predicate `_calibration_allowed`.
  - **Graduation criterion: none.** It is a measuring tool, switched off after the lead reads Gate 2.
- **Changed flag: `draft.tab` true → false**, in `config/features.json:230` and the five fixtures that carry it:
  - `release.json:203`, `profiles-on.json:200`, `onboarding-v2.json:200`, `release-300.json:173`, `release-espn-send-off.json:159`.
  - `_comment_draft_tab` (`:229`) gets the 2026-10-02 decision appended.
  - `test_rookie_ranks_editable.py:248-257` (`…_ships_on`) becomes `…_mirrored_and_ships_off`.
  - The UI-test world profiles `backend/tests/fixtures/profiles/draft.json:22` / `draft-pre.json:22` **keep `true`**. They are draft-room QA worlds for the dormant harness, not shipping config.
- **Depends on (all true today):**
  - `experiments.engine` (`config/features.json:117`), for the overlay;
  - `deck.signal_v2` (:202), `suggestion.telemetry` (:212) and `trade.bakeoff` (:246), for the current-engine arm.

  If any of the last three is off, session creation returns `409 needs_fresh_deck`.
- **Not required:** `trade.value_core`. Keep it off while grading ([prd.md D2](prd.md#11-decisions)).
- **New env vars / `model_config` keys:** none.
- **Operator data actions** (production writes, held for the operator):
  1. Each grader's account id goes into `config/tester_allowlist.json` (deploy).
  2. Create and launch the `calibration_rollout` experiment ([lld.md §8.2](lld.md#82-the-calibration_rollout-overlay)).
- **Ship-the-knob (deploy-free kill):** `POST /api/admin/experiments/calibration_rollout/transition {"to": "stopped"}`.
  - Server: every `/api/grading/*` route 404s once the 60 s experiment cache expires (`experiments.py` `_CACHE_TTL_S`).
  - Client: the tab disappears on the next launch after a flag refetch.
  - The global flag was never on, so there is nothing to un-flip.
  - `GET /api/admin/grading/report` stays readable ([prd.md D4](prd.md#11-decisions)).
  - Draft tab rollback: `draft.tab` → true, then `POST /api/feature-flags/reload`; it is back at the next launch.

## 3. Evidence scope

- [x] **Structural guard: `mobile/tests/check-blind-grading.js`** (`npm run test:blind-grading`; it runs in CI through the glob at `.github/workflows/ci.yml:47`). It pins:
  1. `components/GradingCard.tsx` names no reason, arm or engine field (a forbidden-token scan over comment-stripped source), and imports nothing from `TradeCard`, `api/trades` or `shared/types`.
  2. The `api/grading.ts` wire types have exactly the allowed keys, and every grading call sends `X-Device-Id`.
  3. Arm names render only in `components/GradingResults.tsx`. `CalibrationScreen.tsx` contains no `value_core` or `.arms` token, and `<GradingResults` appears exactly once.
  4. `CalibrationScreen.tsx` does **not** mount `FeedbackFAB`. It is a tab-stack screen covered by RootNav's global mount; a second FAB is the #196/#197 bug.
  5. `TabNav.tsx`:
     - `showCalibrationTab` is decided once at mount from `useFeatureFlags.getState().flags['grading.blind']`, never from `useFlag('grading.blind')`;
     - a `Tab.Screen name="Calibration"` with `tabBarButtonTestID: 'tab.calibration'` and `trackTab('calibration', navigation)`;
     - the render is `showCalibrationTab ? <Calibration/> : showDraftTab ? <Draft/> : null`;
     - the Draft `Tab.Screen` block survives unchanged.
  6. Every `testID` in the new files is a static `calibration.`-namespaced literal, and the required ids exist.
  7. `client.ts` `SLOW_POST_PATHS` contains `/api/grading/sessions`.
  8. The `package.json` script exists.
  9. A self-test proves the scanner fires on a planted token.
- [x] **Unit tests (backend).** Names, asserts and fixtures are in [specs.md §5](specs.md#5-package-specs).
  - P1: `test_blind_grading_service.py`, `test_blind_grading_db.py`, and one added case in `test_value_core_bench.py`.
  - P2: `test_blind_grading_routes.py`, an edit to `test_rookie_ranks_editable.py`, and `test_blind_grading_e2e.py` (integration only).

  The blinding test is `test_blind_grading_e2e.py::test_no_response_reveals_an_arm_until_results`.
- [x] **Code-walk proof**, written at build time into this folder:
  - **`code-walk-backend.md` (P2).** Cites file:line for:
    1. a caller whose resolved `grading.blind` is false, or who fails `_calibration_allowed`, gets 404 before any other check, including the verified gate;
    2. no grading path writes `deck_impressions`, `trade_impressions`, `trade_decisions`, `swipe_decisions` or `trade_service._trade_cards`;
    3. only `results` and `report` read `arms_json`.
  - **`code-walk-mobile.md` (P3).** Cites file:line for:
    1. the tab set at launch for (overlay on, `draft.tab` off), (overlay off, `draft.tab` off), (overlay on, `draft.tab` on) and (overlay off, `draft.tab` on);
    2. the card loop renders only `GradingCard` fed by `GradingNext.card.trade`;
    3. a 409 `needs_fresh_deck` leads to the Acquire tab;
    4. resume lands on the first unanswered card.
- [x] **Manual TestFlight checklist.** The operator runs it on a build containing P3.

  **Prerequisites:**
  - the operator's account id is in the allowlist;
  - `calibration_rollout` is running;
  - `GET /api/feature-flags` with the operator's session shows `configs.calibration_rollout.flags["grading.blind"] = true`;
  - `draft.tab` is false and reloaded;
  - `trade.value_core` is false;
  - Acquire (Trades) was opened for **League A** within the last 7 days, as an organic deck (no "what can I get for X", no partner, no intent).

  **Steps:**
  1. **Force-quit and relaunch.** Expected: the tab bar reads **Rank · Acquire · Calibration · Matches · League**. There is no Draft tab.
  2. **League › Explore.** Expected: the **Rookie draft** tile opens the Draft Room, which shows its back control.
  3. **Tap Calibration.** Expected: the header "Calibration" and an intro explaining that some ideas come from today's engine and some from the new one, plus a **Start** button.
  4. **Start.** Expected: within ~15 s, card **1 / N** with 20 ≤ N ≤ 40. The card shows:
     - the partner's name;
     - "You give" / "You get" lists (name, position badge or PICK, team, age, value);
     - side totals.

     There are **no** reason lines, fairness meter, lane chips, "They're interested" pill or Send button.
  5. **Tap 4, tap the Overpay chip, then Next.** Expected: **2 / N**, with no grade or chip pre-selected.
  6. **Skip.** Expected: **3 / N**.
  7. **Switch to Matches, then back to Calibration.** Expected: still on card 3.
  8. **Force-quit, relaunch, tap Calibration.** Expected: **Resume (2 of N answered)**, and Resume lands on card 3.
  9. **Re-tap the focused Calibration tab.** Expected: nothing breaks; the stack has one screen, so it stays put.
  10. **Open Acquire for League A.** Expected: the deck is unchanged by grading. There are no new likes in Matches and no new "passed" dispositions.
  11. **Grade the rest.** Expected: after the last answer, **Results** shows two blocks, "Today's engine" and "New engine". Each shows graded / skipped / average / "Would send (4–5)" share and top reasons, and Overpay appears.
  12. **Done, then reopen Calibration.** Expected: **Start** (no open session).
  13. **Switch the active league to League B,** where Acquire was not opened in the last 7 days, then Start. Expected: "Open Acquire for this league first…", and **Open Acquire** lands on the Acquire tab.
  14. **Tap the feedback button on the Calibration screen.** Expected: exactly **one** button, and the sheet pre-fills screen **CalibrationHome**.
  15. **The lead runs `curl -s -H "X-Cron-Secret: $CRON_SECRET" "$API/api/admin/grading/report"`.** Expected: the step 11 session is present, and its per-arm numbers match the Results screen.
  16. **On a second device signed in as a non-allowlisted account.** Expected: 4 tabs, no Calibration and no Draft.
  17. **Stop `calibration_rollout`, wait at least 60 s.** Expected: the next grading action on the tester device shows "Calibration isn't turned on for this account". After a relaunch, the tab is gone.
- **`testID`s added:**
  - `tab.calibration`
  - `calibration.loading`, `.no-league`, `.unavailable`, `.open-acquire`, `.retry`, `.start`, `.resume`, `.progress`, `.card`
  - `calibration.grade-1` … `.grade-5`
  - `calibration.tag.overpay`, `.tag.they_wont_accept`, `.tag.junk_filler`, `.tag.too_small`, `.tag.wrong_for_my_window`, `.tag.wrong_for_their_window`, `.tag.same_guy_again`
  - `calibration.submit`, `.skip`, `.results`, `.done`

  All are static literals. `tab.draft` survives in source: the Draft block stays, so `testid-lint.sh` still resolves `mobile/.maestro/capture/draft-room@draft.yaml:138`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (P4)** | New H2 "Calibration — blind grading (`/api/grading/*`, flag `grading.blind` per caller)" after "Test users" (`api-reference.md:1079`), with a TOC entry near `:106` and a row in "Admin" (`:946`) for `GET /api/admin/grading/report` |
| `living-memory/LLD.md` | **updated (P4)** | New section "Blind grading: one neutral formatter, hidden arms, per-caller flag resolution" ([lld.md §6.4](lld.md#64-the-neutral-formatter), [§7](lld.md#7-routes-backendserverpy)) |
| `docs/architecture.md` | **updated (P4)** | New section after "Value-core trade engine" (`architecture.md:258`), and a Components › Backend row (`:472`) for `backend/blind_grading.py` |
| `living-memory/HLD.md` | **updated (P4)** | A Major Components row (`HLD.md:80`) and "Flow C″ — Calibration (blind grading)" after Flow C′ (`:150`) |
| `docs/cross-client-invariants.md` | **updated (P4)** | New section "Calibration tags and scale": the 7 tag keys and the 1–5 scale, shared by `backend/blind_grading.py` and `mobile/src/api/grading.ts`. Plus a note in the tab inventory that the third slot is Calibration or Draft, never both. |
| `docs/glossary.md` | **updated (P4)** | New: Calibration (tab), blind grading (in-app), grading session, grading card, arm (current / value core), shared card. The existing **Blind grade** entry (`glossary.md:544`) points to the in-app tool. **Receipts grading** is a different thing, and the glossary says so. |
| `docs/data-dictionary.md` | **updated (P4)** | New `## Blind grading tables` after Receipts (`data-dictionary.md:1810`). The `tab_selected` note (§1). |
| `docs/config-reference.md` | **updated (P4)** | The `grading.blind` row (per-unit overlay, never global) next to `trade.value_core` (`config-reference.md:351`). The `draft.tab` row: now false (2026-10-02, Calibration takes the slot), still the seasonal switch. `test_rookie_ranks_editable.py:260-263` requires the words "`draft.tab`" and "seasonal" to stay. |
| `docs/runbook.md` | **updated (P4)** | Under "Value-core bench" (`runbook.md:421`): a "Gate 2 — Calibration" subsection covering the allowlist, launching and stopping `calibration_rollout`, the report curl, and local dev (`POST /api/cron/value-snapshot` so `player_value_history` has rows) |
| ADR or `DECISIONS.md` entry | **DECISIONS by the lead** | One entry (grep for the max D-id; D-197 records it (D-195 went to decline reasons on main; value core is D-196)). It records the operator's 2026-10-02 decisions (Calibration tab in the Draft slot; `draft.tab` off with the code kept; tester-only via overlay plus allowlist), the §1 waiver, and D1–D8 ([prd.md §11](prd.md#11-decisions)). No ADR. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, plus `mobile-typecheck` (which runs every `check-*.js`), plus `maestro-testid-lint`, all on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry by the lead. It names:
  - the pytest counts;
  - `check-blind-grading` PASS;
  - the e2e blinding test;
  - the TestFlight checklist outcome.
- **TestFlight verification:** the §3 checklist, run by the operator and logged in TEST_LEDGER. A client release is **required**: the tab and the screen are new code.
- **Express lane declared by the operator?** **No.** This change adds schema, an API surface and a flag, and flips `draft.tab`. Full gates apply.

---

## Addendum 2026-10-07 — targeted pre-generation

**Entry point:** direct ask ("Generate a calibration deck for bcork, mangopatti, lofman"). Their Acquire decks were missing (Bcork) or 18 days old (MangoPatti, lofman), so the bulk path skipped them. The weekly replenishment that would have refreshed them gets through about one user-league a day.
**Change:** `POST /api/admin/grading/pregenerate` takes an optional `{"targets": [{user_id, league_id}]}`. On one daemon thread, each pair is first refreshed with `_replenish_deck_for` (the weekly-replenishment path), then `start_session` and `_build_grading_session` run. Without a body the route behaves exactly as before.
**Operator sign-off on waivers:** not needed (no waivers below that change behavior).

1. **Analytics:** (b) existing coverage. The refresh logs `trade_impressions` / `deck_impressions` with source `replenish`, the same as the weekly cron. Session creation is already visible in `grading_sessions` and the admin report. No new events.
2. **Schema & flags:** none. No new tables, columns, flags or env vars.
3. **Evidence:**
   - **Unit test:** `test_blind_grading_routes.py::test_admin_pregenerate_targets_refresh_then_build_each_pair`. It covers auth, the four `invalid_body` shapes, the order "refresh → start → build" per pair, a failed refresh skipping its pair, a resumed open session not rebuilt, and the platform hand-off.
   - **Prod proof:** `deck_replenish_log` rows plus their `deck_impressions` jobs (2026-10-04 and 2026-10-07) show the replenish path writes qualifying rows (`model_arm = owner_v2_bilateral`). Then the run for the requested users, read back via `report?include_open=1`.
   - **TestFlight:** the requesting users open Calibration and see Start, not "Open Acquire…".
4. **Docs:**

   | Doc | Updated? |
   |---|---|
   | `docs/api-reference.md` | **updated**, Admin row for the pregenerate route ("Targeted mode") |
   | `docs/runbook.md` | **updated**, § Gate 2 pre-generation (curl + caveats) |
   | `living-memory/LLD.md`, `HLD.md`, `docs/architecture.md` | n/a: no convention, module or flow shift. It reuses existing helpers on an existing admin route |
   | `docs/cross-client-invariants.md`, `docs/glossary.md` | n/a: no shared constant or new term |
   | ADR / DECISIONS | n/a: no non-obvious choice. Refreshing via the replenish path, rather than relaxing `MAX_DECK_AGE_DAYS`, keeps both arms on today's values |

5. **Ship gate:** CI green on the pushed sha, plus a TEST_LEDGER entry. Express lane: **no**. This changes an API contract (admin), so full gates apply.
