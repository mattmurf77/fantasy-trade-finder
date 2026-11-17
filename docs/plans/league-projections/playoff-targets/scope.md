# Feature Scope — Playoff targets (v1)

**Date:** 2026-11-14
**Entry point:** direct ask. Operator, 2026-11-14: "Build the opposite of the Max PF moves
features. The purpose is to identify the players to trade for that maximize playoff chances.
This feature should only suggest players on teams that are rebuilding, tanking for team outlook
or have a less than 50% chance of making the playoffs."
**Builder:** one builder subagent (backend, app, docs), branch `feat/playoff-targets`.
**Operator sign-off on waivers:** **not yet.** §0 lists every waiver and every product choice
made on the operator's behalf. The flag ships off and stays off until they are answered.

The wire contract is [contract.md](contract.md). Decision id **D-264**.

---

## 0. For operator sign-off before the flag is turned on

**Waivers**

| # | Waiver | Reason |
|---|---|---|
| W1 | No Maestro flow, no simulator capture, no `screens/` capture | D-056 retired them. Evidence is §3 |
| W2 | No website (`web/`) surface | Max PF moves has none either; the Standings card in the app is where its mirror lives |
| W3 | No backtest of the number against real seasons | The forecast's own accuracy is unmeasured at horizon; this feature reads it and adds one assumption (P4). A backtest is a separate piece of work, as it was for Max PF moves |
| W4 | ~~No operator re-run for forecasts saved before the flag is turned on~~ **Closed 2026-11-16 (D-273):** the cron route's `retry_missing_targets` re-runs blocks that are missing, not computed or saved under other settings (runbook) | Max PF moves got one later (D-260). Without it the section reads "appear after the next update" until the next weekly forecast |
| W5 | No auto-run of the trade search from "Find trades" | Same as Max PF moves' W4: the hand-off pins and lands on the canvas |

**Product choices made for the operator** (each is a default; say which to change)

| # | Choice | Default taken | Why |
|---|---|---|---|
| P1 | Declared or inferred outlook? | **Saved (declared) only.** `rebuilder` and `jets` in `league_preferences.team_outlook` | The ask says "rebuilding, tanking for team outlook", the saved setting. The inferred projection read is Rebuilding at or below 45%, which the under-50% rule already covers; the roster read is a guess |
| P2 | A row for a team at or above 50% implies its manager saved Rebuilding or Tanking. The app has not shown a league-mate's saved outlook before (`partner_outlook.public`) | **The block and the row never state the outlook or which rule made the team eligible.** The row shows the team's name and its playoff chance; the footer states the rule | The implication follows from the operator's rule itself. Naming the outlook on the row would be a clearer read and a plainer disclosure: the operator's call |
| P3 | "Less than 50%" | **Strictly below 0.5 on the unrounded probability**, in the same forecast run the numbers come from. A constant, not a setting | The operator's words; a team printing "50%" at 0.4996 is selling |
| P4 | What the number assumes | **The player joins the viewer and leaves his own team; the viewer gives up no starter and his team gets no starter back.** Stated in the footer | The mirror of Max PF moves, which removes a player and models no return. Removing him from his own team matters when that team is on the viewer's schedule or near the playoff line; leaving him on both rosters would count him twice |
| P5 | Where each eligibility test runs | **Both in the weekly job and on every read** (contract §2). A team that stops selling loses its rows at once; a team that starts selling gets rows with the next weekly forecast, and the section says so | The saved outlook can change between the two. The read can drop rows cheaply; it cannot compute new ones |
| P6 | Placement | A fifth disclosure, "Playoff targets", on the viewer's own Standings team card, after "Max PF moves" | "Next to Max PF moves"; no new screen, no new FeedbackFAB |
| P7 | Open or closed by default | Open when the viewer's playoff chance is above 45% and the saved outlook is not Rebuilding or Tanking: the exact complement of Max PF moves' rule | One of the two sections starts open, the one that fits the team |
| P8 | How many rows | 8 re-simulated, 5 shown, then "Show all". Every row is listed, passing or not, with "None of these raises your playoff chance by a visible amount on its own." when none passes | Max PF moves' numbers and D-261's lesson (hiding rows left half the league with nothing) |
| P9 | Threshold for "a visible amount" | A gain of at least 1 percentage point (`min_playoff_gain` 0.01) | A whole-percent display cannot show less. **Raised to 2 points (0.02) on 2026-11-16, D-272:** the backtest (PR #698) found 1-2 point rows came true 0.3% of the time against 1.5% shown |
| P10 | Already near certain | At or above 99% (`near_certain_min` 0.99) the section shows one line and no list. Proven clinched and proven eliminated get their own lines | Above 99% no gain can pass P9 |
| P11 | Which players are checked | Every player on a selling team except reserve (the forecast's `ir_maxpf: exclude`) and players with no usable projection in an unplayed week. The 8 with the largest projected lineup gain are re-simulated | The time budget (§3 risks). Ordering by points, not by playoff chance, is a shortcut: a player outside the top 8 by points is never re-simulated |
| P12 | After the trade deadline, season over, forecast unusable | The same rules and reasons as Max PF moves | One vocabulary on one card |
| P13 | Hand-off | "Find trades for [player]" pins the player on the **receive** side, clears the give side, and opens the trade canvas with his team as the partner | The mirror of Max PF moves' give-side pin |
| P14 | A selling team's Keep players | Still listed | The number is true whether or not the manager would sell. The trade finder will not generate a trade for another manager's Keep player, but the canvas the hand-off opens still lets the user build an offer |
| P15 | Copy | [contract.md](contract.md) §10, 37 rows | Plain; the footer says what the number is not |

## 1. Analytics scope

- [x] **(a) New events specced** (exact properties in contract §9):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `playoff_targets_viewed` (new, impression → `NON_INTENT_EVENTS`) | `state`, `n_listed`, `any_pass`, `n_sellers`, `band` | The section body becomes visible on the user's own card | app |
  | `playoff_target_expanded` (new, intent) | `position`, `rank` | A listed row is opened | app |
  | `finder_target_pinned` (existing) | `side: receive`, `source: playoff_targets` (new value) | "Find trades for [player]" tapped | app |

  → follow-through: registered in `backend/analytics_taxonomy.py` and classified in
  `backend/analytics_queries.NON_INTENT_EVENTS` in the same commit as the app emitter. No
  player id or name in any property. `docs/data-dictionary.md` unaffected (events land in the
  existing `user_events` table).

## 2. Schema & flag scope

- **New/changed tables or columns:** none. **New stored JSON:**
  `league_projection_runs.result_json["playoff_targets"]` (baseline runs, flag on only;
  contract §6) → data dictionary note on `result_json`. It holds each other roster's Sleeper
  owner ids so the read can look saved outlooks up again. Retention unchanged.
- **New flag:** `league.playoff_targets`, default False in `backend/feature_flags.py`, `false`
  in `config/features.json` with a `_comment_` line, mirrored in
  `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json` →
  `docs/config-reference.md`. Requires `league.projections`. **Graduation criterion:** the
  operator answers §0, then the TestFlight checklist in [evidence.md](evidence.md) passes on a
  test account.
- **New settings** (`config/league_projections.json`, a new top-level `playoff_targets` object,
  read and validated only while the flag is on): `simulations_per_candidate` 5000, `candidates`
  8, `min_playoff_gain` 0.01, `near_certain_min` 0.99, `time_budget_seconds` 60 →
  `docs/config-reference.md`. No env vars, no `model_config` keys.
- **Rollback lever:** turning the flag off removes the block from every read at once and stops
  the extra job work; no deploy needed. Saved blocks stay in `result_json`, unread.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-playoff-targets.js` + `npm run
      test:playoff-targets`. Pins: the mount rule (flag, block, Sleeper, own card, version,
      known state); placement after Max PF moves; every state and reason has its copy (the §10
      table compared both ways, the §5 payloads parsed from contract.md); the default-open rule
      is the complement of Max PF moves'; the roster drop; 5 then Show all; the hand-off pins
      receive, clears give, sends the partner and fires `finder_target_pinned {receive,
      playoff_targets}`; no number is computed in the app; tokens only.
- [x] **Unit tests (backend):** `test_playoff_targets.py` (the rule, the calculation, the
      composer), `test_playoff_targets_job.py` (the weekly job), `test_playoff_targets_read.py`
      (the forecast read), `test_playoff_targets_analytics.py` (events and the flag endpoint).
      One named sabotage for each of the three seller conditions and the rest:
      `living-memory/TEST_LEDGER.md` 2026-11-14.
- [x] **Code-walk proof:** [evidence.md](evidence.md) §1.
- [x] **Manual TestFlight checklist:** [evidence.md](evidence.md) §3.
- [ ] **WAIVED** — not waived; there is a user-visible surface.
- `testID`s added: `standings.targets.toggle`, `.body`, `.line`, `.baseline`, `.changed`,
  `.roster-changed`, `.no-targets`, `.none-alone`, `.row.<rank>`, `.detail.<rank>`,
  `.find.<rank>`, `.show-all` (all under `standings.targets`).

### Risks (known, accepted for v1)

| Risk | Handling |
|---|---|
| The number is not a trade evaluation | P4; the footer says so in the app |
| The step adds time to the weekly job | Measured on the 12-team, 14-week fixture league: [evidence.md](evidence.md) §2. Its own 60 s budget, the shared 480 s line, and it runs after Max PF moves, so it can only lose its own block |
| Top 8 by lineup points is a shortcut (P11) | Stated; a wider search is a settings change (`candidates`) at about one second per extra player on the fixture |
| A league-mate keyed by an account id rather than a Sleeper id | Their saved outlook is not found, as in the trade engine's own lookup. They are still listed when under 50% |
| With `calc.inline_home` off the hand-off's canvas prefill is ignored | Same as Max PF moves; that flag is on |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | "Scheduled league projection sidecar": the `playoff_targets` block on `/latest` and the strip |
| `docs/data-dictionary.md` | updated | `league_projection_runs` → `result_json.playoff_targets` |
| `docs/config-reference.md` | updated | Flag `league.playoff_targets` and the five `playoff_targets` settings |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | updated | "Playoff targets": the seller rule, the state enum, the 0.45 complement rule |
| `docs/glossary.md` (new domain term) | updated | Playoff targets, selling team |
| `docs/plans/league-projections/implementation.md` | updated | "Implemented": the weekly job's second extra step, `sidecar["owners"]` |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | updated | "Specific patterns": a rule that depends on live data is applied in the job and again on the read |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | One leaf module inside the existing `league_projections` package and one bounded step in the existing worker; the read path is the existing route |
| `living-memory/HLD.md` | n/a | Same reason |
| `mobile/src/components/CLAUDE.md`, `mobile/src/utils/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | updated | The new component, util and copy module, and the screen's props. `mobile/src/api/CLAUDE.md` has no row for `leagueProjections.ts`, where the new types live, so it is unchanged |
| `docs/business/analytics/2026-11-14-playoff-targets-events.md` | added | Tracking-plan addendum for the two events and the new `finder_target_pinned.source` |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | updated | D-264 |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md` | updated | 2026-11-14 entries; the operator's choices, the checklist and the flag flip in NEXT |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) +
  `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the tests, the sabotages
  that turned them red, the measured job time and the code walk.
- **TestFlight verification:** the checklist in evidence.md §3, run by the operator before the
  flag is turned on in production. Merging with the flag off does not wait for it.
- Express lane declared by the operator? No. The change touches an API contract, a flag and
  analytics events, so it would not qualify as a quick fix in any case.
