# Feature Scope — Max PF moves (v1)

**Date:** 2026-11-12
**Entry point:** direct ask. Operator, 2026-11-12: "Build v1 of the max pf trade feature",
accepting [exploration.md](exploration.md) §14's eleven recommendations as written.
**Builder:** backend builder (this file, [contract.md](contract.md), [plan.md](plan.md)); an
app builder codes the Standings section from the contract in parallel.
**Operator sign-off on waivers:** W1–W4 stand (coordinator, 2026-11-12, reported to the
operator); Q1–Q5 settled with the recommendations below.

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

**Choices settled 2026-11-12 (coordinator's defaults, reported to the operator)**

| # | Question | Recommendation |
|---|---|---|
| Q1 | Who may answer the draft-order question for a league? | Any member, last answer wins, stored per league (contract §7.1). It only shows or hides this section in v1 |
| Q2 | Should a "reverse standings" or "lottery or other" answer also stop projected-slot pick pricing (D-240) for that league? | Not in v1 (contract §7.3); follow-up item, because it changes trade values league-wide and every member's deck |
| Q3 | The ESPN/MFL forecast design treats `leagues.draft_order_rule` as operator-set only and feeds it to the simulation. This build makes the same column member-written | Keep one column; when that design is built, it adds a source/lock column or reads only `maxpf_lowest_first`/`reverse_standings`. Flag in its scope |
| Q4 | Trade deadline: Sleeper's `settings.trade_deadline` is a week number; the code cannot tell whether trades are allowed during that week | Hide the list once `completed_weeks ≥ trade_deadline` (the deadline week is under way or over), i.e. lean to hiding; 0, 99, absent or a non-integer mean no deadline. Exploration §15 lists this as unknown |
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

- [x] **Structural guard (app builder, `feat/max-pf-moves-app` 18bfb448):**
      `mobile/tests/check-max-pf-moves.js` + `npm run test:max-pf-moves`, 119 assertions
      (groups A–N): mount only on the own card and only with flag + block; placement under
      "Draft pick odds"; every state and reason has its copy (the §10 table compared both ways,
      the four §5 example payloads parsed from contract.md); the hand-off pins give, clears
      receive, sends `canvasPrefill` + `canvasPrefillSeq` with `pop: true` via `popTo`, and fires
      `finder_target_pinned {give, maxpf_moves}`; no button on a Keep row; no "tank"; tokens only.
      54 of 54 sabotages caught. All 185 `check-*.js` suites, `tsc --noEmit` and testid-lint
      clean. Detail: [app-evidence.md](app-evidence.md) §4 (on the app branch until merged).
- [x] **Unit tests (backend):** `test_maxpf_moves_settings.py` (12),
      `test_maxpf_moves_capture.py` (7), `test_maxpf_moves.py` (18),
      `test_maxpf_moves_job.py` (6), `test_maxpf_moves_draft_order.py` (10),
      `test_maxpf_moves_read.py` (6), `test_maxpf_moves_analytics.py` (5). Sabotages and the
      full-suite run: `living-memory/TEST_LEDGER.md` 2026-11-12 Max PF moves.
- [x] **Code-walk proof:** backend [build-backend.md](build-backend.md); app
      [app-evidence.md](app-evidence.md) §2–§3.
- [x] **Manual TestFlight checklist** (operator, flag on for a test account, after the
      backtest): [app-evidence.md](app-evidence.md) §5, eleven steps (own card, other cards,
      collapsed, pick owned elsewhere, the draft-order question each way and shared across
      members, roster changed, Keep, the hand-off onto the canvas, non-Sleeper, flag off, large
      text). Add one backend check: the Weekly projections lineup for a week, with the top row's
      player mentally removed, starts the replacement the row names for that week.
- [ ] **WAIVED** — not waived; there is a user-visible surface.
- `testID`s: listed in app-evidence.md (app builder); testid-lint clean.

### Risks (known, accepted for v1)

| Risk | Handling |
|---|---|
| The bench-depth bias (exploration risk 2): projected max PF is the projected best lineup, real max PF is the hindsight best | The leave-one-out backtest runs before the flag is turned on (W3); `maxpf_moves.compute` and `resolve` are pure and documented for it |
| With `calc.inline_home` OFF (true today) the hand-off's canvas prefill is ignored; the give pin is then not shown on the guided landing and is sent only if no model search has run since the last reset | Follow-up in NEXT.md; smallest fix is a TradesScreen effect calling `resetDeckForNewTargets()` on an outside pin change (about 8 lines). Not built |
| A member's mistaken draft-order answer hides the list for the whole league | Visible "Change answer" on the hidden state; last answer wins |
| A week's change can be positive when a free agent outprojects the removed player | Shown with `+`; a listed row's season total is always a drop (contract §3.5) |
| The step's cost grows with weeks remaining | Measured about 6.5 s for 14 weeks on a laptop; hard stop at 60 s / 480 s, and the forecast is saved without the block on a stop |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | "Scheduled league projection sidecar": the `max_pf_moves` block on `/latest`, the strip, `POST /api/leagues/{id}/draft-order-rule` |
| `docs/data-dictionary.md` | updated | `leagues.draft_order_rule`, `draft_order_rule_set_at`; `league_projection_runs` → `result_json.max_pf_moves` |
| `docs/config-reference.md` | updated | Flag `league.max_pf_moves` and the six `max_pf_moves` settings, before "Model v5" |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | updated | "Max PF moves": state/reason/draft-order enums, formatting, the 0.45 open rule, the "largest possible change" and no-"tank" rules |
| `docs/glossary.md` (new domain term) | updated | Max PF moves, replacement, pick if you miss, paired re-run (beside "Official Max PF") |
| `docs/plans/league-projections/implementation.md` | updated | "Implemented": the weekly job's extra step and the capture side channel |
| `docs/business/analytics/2026-11-12-max-pf-moves-events.md` | added | Tracking-plan addendum for the three events and the new `finder_target_pinned.source` |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | updated | "Specific patterns": saved sub-block composed on read; capture side channel |
| `docs/architecture.md` | n/a | No new module wiring or data flow at the architecture's level: one leaf module inside the existing `league_projections` package and one bounded step in the existing worker; the read path is the existing route |
| `living-memory/HLD.md` | n/a | Same reason as architecture.md |
| `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | app builder | Owned by the app branch (`mobile/` is the app builder's) |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | updated | D-258 |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md` | updated | 2026-11-12 Max PF moves entries; follow-ups in NEXT |

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
