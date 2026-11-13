# Feature Scope — Max PF moves (v1)

**Date:** 2026-11-12
**Entry point:** direct ask. Operator, 2026-11-12: "Build v1 of the max pf trade feature",
accepting [exploration.md](exploration.md) §14's eleven recommendations as written.
**Builder:** backend builder (this file, [contract.md](contract.md), [plan.md](plan.md)); an
app builder codes the Standings section from the contract in parallel.
**Operator sign-off on waivers:** pending — see §0.

The wire contract both builders follow is [contract.md](contract.md). Decision id **D-258** is
reserved for this feature; its DECISIONS entry is written in the build, not now.

---

## 0. For operator sign-off before build

**Waivers**

| # | Waiver | Reason |
|---|---|---|
| W1 | No Maestro flow, no simulator capture, no `screens/` capture (template §3's dead rows and §5's tier) | D-056 retired them. Evidence is §3 below instead |
| W2 | No website (`web/`) surface in v1 | Exploration §13: the old tab survives only on the website (`web/js/league-projections.js`); the operator's v1 is the app's Standings card. The web page is unchanged and keeps working |
| W3 | Flag stays off at merge; the leave-one-out backtest is not part of this build | Operator decision 11: the backtest runs before the flag is turned on, by a separate validation agent. This build only makes the calculation callable for it (`maxpf_moves.compute`) |
| W4 | No auto-run of the trade search from "Find trades" | Needs a new R1 `find_trades_tapped.source` value and opponent-less auto-run support in TradesScreen; v1 pins the give side and lands on the deck (contract §12). Follow-up |

**Choices the operator has not yet seen (each with a recommendation)**

| # | Question | Recommendation |
|---|---|---|
| Q1 | Who may answer the draft-order question for a league? | Any member, last answer wins, stored per league (contract §7.1). It only shows or hides this section in v1 |
| Q2 | Should a "reverse standings" or "lottery or other" answer also stop projected-slot pick pricing (D-240) for that league? | Not in v1 (contract §7.3); follow-up item, because it changes trade values league-wide and every member's deck |
| Q3 | The ESPN/MFL forecast design treats `leagues.draft_order_rule` as operator-set only and feeds it to the simulation. This build makes the same column member-written | Keep one column; when that design is built, it adds a source/lock column or reads only `maxpf_lowest_first`/`reverse_standings`. Flag in its scope |
| Q4 | Trade deadline: Sleeper's `settings.trade_deadline` is a week number; the code cannot tell whether trades are allowed during that week | Hide the list once `completed_weeks ≥ trade_deadline` (the deadline week is under way or over), i.e. lean to hiding. Exploration §15 lists this as unknown |
| Q5 | "Show all" | Lists only rows that pass the threshold (contract §14 row 2) |

## 1. Analytics scope

- [x] **(a) New events specced** (exact properties and values in contract §9):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `maxpf_moves_viewed` (new, impression → `NON_INTENT_EVENTS`) | `state`, `n_moves`, `band` | The section body becomes visible on the user's own card | app |
  | `maxpf_move_expanded` (new, intent) | `position`, `rank` | A listed row is opened | app |
  | `finder_target_pinned` (existing) | `side: give`, `source: maxpf_moves` (new value) | "Find trades for [player]" tapped | app |
  | `draft_order_rule_answered` (new, intent) | `answer`, `source` (`first_ask` \| `change`) | The draft-order POST returns 200 | app |

  → follow-through: registered in `backend/analytics_taxonomy.py` and classified in
  `backend/analytics_queries.NON_INTENT_EVENTS` in the same commit as the app emitter (root
  CLAUDE.md). No player id or name in any property. `docs/data-dictionary.md` unaffected
  (events land in the existing `user_events` table). The `band` property departs from the
  exploration (contract §14 row 1).

## 2. Schema & flag scope

- **New columns:** `leagues.draft_order_rule TEXT NULL`, `leagues.draft_order_rule_set_at TEXT
  NULL`, added to `leagues_table` and `_migrate_db` → `docs/data-dictionary.md`. No new table.
  **New stored JSON:** `league_projection_runs.result_json["max_pf_moves"]` (baseline runs,
  flag on only; contract §13) → data dictionary note on `result_json`. Retention unchanged:
  the block lives and dies with `result_json` under the existing 7-day / 90-day rules
  (`store.py:17-45`).
- **New flag:** `league.max_pf_moves`, default False in `backend/feature_flags.py`
  (`FLAG_KEYS` + `DEFAULT_FLAGS`), `false` in `config/features.json` with a `_comment_` line,
  mirrored in `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json` →
  `docs/config-reference.md`. Requires `league.projections`. **Graduation criterion:** the
  leave-one-out backtest (exploration §11) is written up and the operator accepts the size of
  the bench-depth bias (risk 2), then the TestFlight checklist below passes.
- **New settings** (`config/league_projections.json`, a new top-level `max_pf_moves` object,
  read and validated only while the flag is on): `simulations_per_candidate` 5000,
  `candidates` 8, `min_drop_points` 5, `min_pick_change` 0.1, `min_top3_change` 0.02,
  `time_budget_seconds` 60 → `docs/config-reference.md`. No env vars, no `model_config` keys.
- **Rollback lever:** turning the flag off removes the block from every read at once and
  stops the extra job work; no deploy needed. Saved blocks stay in `result_json`, unread.

## 3. Evidence scope

- [x] **Structural guard (app builder):** `mobile/tests/check-maxpf-moves.js` + `npm run
      test:maxpf-moves` — pins: the section mounts only when `team.roster_id ===
      result.viewer_roster_id`; it renders under "Draft pick odds"; every server `state` and
      every `reason` in contract §4 has its copy-table string; the Find trades handler calls
      `setSide('give', …)` and `setSide('receive', [])` and tracks `finder_target_pinned` with
      `source: 'maxpf_moves'`; no "Find trades" button renders for a `keep` row; the word
      "tank" appears nowhere in the section's source; no colours outside Chalkline tokens.
- [x] **Unit tests (backend):** `backend/tests/test_maxpf_moves.py` (pure module),
      `test_maxpf_moves_capture.py` (side channel), `test_maxpf_moves_job.py` (service hook,
      budget, failure isolation), `test_maxpf_moves_routes.py` (read block, strip, draft-order
      route); updates to the flag-mirror tests. Each with the sabotages listed in
      [plan.md](plan.md).
- [x] **Code-walk proof:** written at build end into `build-backend.md` (this folder),
      file:line through capture → job → saved block → read → app; and by the app builder for
      the Standings section and the hand-off.
- [x] **Manual TestFlight checklist** (operator, flag on for a test account, after the
      backtest):
      1. Own team in a Sleeper league with a current forecast and playoff chance ≤ 45%: Standings
         → open your team → "Max PF moves" is open under "Draft pick odds", with the baseline
         line and up to 5 rows.
      2. Open any other team's card: no "Max PF moves" section.
      3. Open the top row: its replacement names for week N match Weekly projections → Week N
         lineup when that player is mentally removed (the bench player who would start).
      4. Baseline "pick … on average" equals Draft pick odds → "Expected pick if this team
         misses" to one decimal.
      5. Tap "Find trades for …": Trades opens with that player pinned on the give side and
         nothing on the receive side; Find a Trade returns cards that send him.
      6. A row tagged Keep shows no Find trades button.
      7. Answer the draft-order question "Reverse standings": the list is replaced by the
         not-max-PF line with "Change answer"; change it back to "Lowest max PF": the list
         returns. Sign in as a second member of the same league: the answer is shared, the
         question does not appear.
      8. A league where your playoff chance is above 45%: the section is collapsed with the
         playoff line; "Show moves" opens the list.
      9. Trade away a listed player on Sleeper, reopen Standings: the roster-changed notice
         shows and that player's row is gone.
      10. An ESPN or MFL league: Standings shows its existing unavailable card and no section.
      11. Turn the flag off: the section disappears; Standings otherwise unchanged.
- [ ] **WAIVED** — not waived; there is a user-visible surface.
- `testID`s added (app builder): `standings.maxpf.section`, `standings.maxpf.row.<rank>`,
  `standings.maxpf.find-trades`, `standings.maxpf.question`, `standings.maxpf.show-all`
  (template ids go in `scripts/testid-lint-allow.txt`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

Every doc from exploration §12, "to update in build" until the build fills the row.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | to update in build | `GET /api/leagues/<id>/projection-runs/latest` gains `max_pf_moves`; `public()` strip; new `POST /api/leagues/<id>/draft-order-rule` |
| `docs/data-dictionary.md` | to update in build | `leagues.draft_order_rule`, `leagues.draft_order_rule_set_at`; `league_projection_runs.result_json.max_pf_moves` |
| `docs/config-reference.md` | to update in build | Flag `league.max_pf_moves`; the six `max_pf_moves` settings |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | to update in build | `state`/`reason` enums, `draft_order_rule` values, rounding rules (contract §11), the "largest possible change" wording rule, the 0.45 open rule |
| `docs/glossary.md` (new domain term) | to update in build | Max PF, replacement, pick if you miss, Max PF moves, paired re-run |
| `docs/plans/league-projections/implementation.md` | to update in build | The weekly job's extra step and the capture side channel |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | to update in build | "A raw saved sub-block of `result_json` is never served; reads compose it" convention; capture side channel |
| `docs/architecture.md` | to update in build, or n/a with reason | Judged at build end: a new leaf module in an existing package and one extra step in an existing worker is likely not an architecture change |
| `living-memory/HLD.md` | to update in build, or n/a with reason | Same judgement as architecture.md |
| `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | to update in build (app builder) | The new section in `LeagueProjectionDetail`, Standings' new props |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | to update in build | D-258: per-league draft-order answer, saved-not-served raw block, side channel outside the snapshot hash |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` | to update in build | Dated entry; suite + sabotage evidence |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) +
  `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the tests, the sabotages
  that turned them red, and the code-walk.
- **TestFlight verification:** the §3 checklist, run by the operator after the backtest and
  before the flag is turned on in production; outcome logged in TEST_LEDGER. Merging with
  the flag off does not wait for it.
- Express lane declared by the operator? No. The change touches schema, an API contract, a
  flag and analytics events, so it would not qualify as a quick fix in any case.
