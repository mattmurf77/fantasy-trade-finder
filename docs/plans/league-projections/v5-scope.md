# Feature Scope — Projected playoff model v5 and outlook suggestion

**Date:** 2026-11-11
**Entry point:** direct ask (operator spec, "updating the projected playoff teams")
**Builder:** this session, with three helpers (mobile UI, web UI, existing-test update)
**Operator sign-off on waivers:** not obtained before build; the operator was away. Two waivers below, both surfaced in the hand-back.

---

## What ships

1. **Model `projected-lineup-universal-sd-v5`.** Each unplayed team-week is `Normal(projected
   best-lineup total, 25.0)`. No historical blend (was 60% history), no per-team variance, no
   persistent team strength. Max PF uses its own eligible-roster projection with the same SD.
   Completed scores, records, PF, PA, official Max PF, locked starters and observed Max PF floors
   stay facts.
2. **No history fallback.** A team-week with no projected player stops the run
   (`missing_weekly_projections`, state `incomplete_projections`); the last successful forecast
   stays, dated and stale. A lineup slot left empty while a rostered eligible player has no
   projection marks the forecast `incomplete` and is explained.
3. **Universal SD** chosen and recorded as provisional: [universal-sd/README.md](universal-sd/README.md).
4. **Outlook suggestion** from the saved probability (0–15% Tanking, over 15–45% Rebuilding,
   over 45–75% Contender, over 75% All-in; unrounded; only for a current, complete, current-model
   forecast; only shown when it differs from the saved outlook; never written without the user
   choosing it).
5. **UI.** "Compare history weights" and "Forecast details" removed (web and app). Home tile is one
   compact row: the percentage is the link; Weekly, date, Partial, Buy a player and View are gone.
6. **Migration.** Old-model forecasts are kept and shown as stale; the scheduled batch refreshes
   each league once at its next 15-minute tick; nothing is simulated on app entry.

## Decisions made here (D-229, D-230)

- **45% is code, 15% and 75% are configuration.** `recommendation.REBUILDING_MAX`; the outer cuts
  are `config/league_projections.json` → `outlook_recommendation`.
- **Precedence** (stated once in `backend/league_projections/recommendation.py`): the saved outlook
  → the projection suggestion when available → the roster-shape reads (age, picks, starter value,
  three-band odds). In Team Review an available suggestion sets `window.inferred` with
  `window.source = "projection"`; the composite and the three-band odds cannot replace it, and
  `window.roster_inferred` still carries the old verdict. The trade engine's own fallback
  (`inferred_outlook` when nothing is saved) is unchanged.
- **"Incomplete" is narrow on purpose.** `coverage.estimated` is true for every saved production
  run (any rostered player without a projection sets it), so it cannot gate the suggestion.
  Incomplete means a starting slot is empty AND a rostered, slot-eligible player has no projection
  (or a starter who already played has no recorded score, or an IDP starter is on bye and the
  league has no replacement average to stand in). A bye at an offensive slot, a roster with nobody
  for the slot, a player with no NFL team, and a player with no position data are known zeros. One such slot anywhere in a league withholds the suggestion for every
  team in it, because every team's chance depends on every team's scores.
- **One refresh per model change.** Weekly dispatch first marks targets whose last attempt was
  admitted under another model version as due. It keys on the last attempt, so a failing league is
  not retried every 15 minutes.
- **A scenario request cannot bring its own SD** (`score_sd_is_app_wide`). The POST route stays
  for same-input scenarios (seed, iterations, draft round); neither client calls it now.
- **Labels.** The app says "Contending", the web says "Contender"; each client uses its own
  existing outlook names. Server sentences never name a band.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** "Review outlook" on Home fires the existing
  `home_tile_tapped {tile: 'outlook'}`; the percentage link fires `home_tile_tapped
  {tile: 'standings'}`; a confirmed change fires the existing `outlook_saved`. The Home Buy/Sell
  buttons are gone, so `home_tile_tapped {tile: 'buy'|'sell'}` now comes only from the position
  tiles. No event name or property added.
- **Not covered (waived, for the operator to rule on):** there is no event for "a suggestion was
  shown" or "shown and not taken", so acceptance rate cannot be measured. Adding one is an
  analytics-taxonomy change and was left out rather than specced without the operator.

## 2. Schema & flag scope

- Tables/columns: none. `result_json` gains keys (`viewer_roster_id`, `score_sd`, `score_model`,
  `coverage.estimate_status` and friends) and loses the history keys; it is an opaque JSON column.
- Flags: new **`league.projection_outlook`** (code default false; `config/features.json` and the
  three fixtures true). Graduation: none planned; it is the kill switch for the suggestion. Rides
  `league.projections` (on in production via `FTF_FLAGS`).
- Config: `config/league_projections.json` → `model.score_sd` (new, required),
  `outlook_recommendation` (new, required); `model.historical_weight`, `model.persistent_sd`,
  `model.maxpf_variance` removed. Rollback levers, deploy-free: `league.projection_outlook` off
  (suggestion), `league.projections` off (everything). The model itself rolls back by reverting
  the commit; v4 results are then current again and v5 results stale.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_league_projection_model_v5.py` (history cannot move
  future means; one SD; convergence; completed games no noise; obsolete options rejected;
  tiebreakers; Max PF own projection and floor; no fallback; incomplete slot; bye is a known
  zero), `backend/tests/test_league_projection_outlook.py` (every boundary incl. exactly 45% and
  the next float; unrounded; availability matrix; route never writes; stale model; flag off;
  scenario SD; refresh-once; Team Review precedence). Existing `test_league_projection_*` files
  updated to the new model.
- [x] **Structural guards:** `mobile/tests/check-league-projections.js`,
  `check-league-projections-web.js`, `check-home-playoff-banner.js` (and the Home/Team Review
  guards touched).
- [x] **Backtest and sensitivity:** `universal-sd/`.
- [x] **Manual TestFlight checklist:** below. Nothing here has been seen on a device.
- **WAIVED:** scope block was written during the build, not before it (operator away, explicit
  detailed spec in hand).

### Manual TestFlight checklist (needs the next build)

1. Home, Sleeper league with a saved forecast: one compact "Playoff chance" row about the height
   of "Team outlook". No "Weekly", date, "Partial", "Buy a player", "View". Tap the percentage →
   Standings, same number there.
2. Tap the info control on that row: an explanation opens; tap again: it closes.
3. Before the first v5 forecast lands: the row shows the old percentage marked last saved and no
   outlook prompt.
4. After it lands, with a saved outlook that differs: "Consider …" with "Review outlook". Tap it:
   the outlook selector opens, the suggested card is marked "Suggested", your saved card is still
   the selected one. Close without tapping: Home still shows your old outlook.
5. Tap the suggested card: outlook saves; back on Home the prompt is gone.
6. Saved outlook equal to the suggestion: no prompt at all.
7. Standings → Projected: no "Compare history weights", no "Forecast details". Team rows, sort and
   weekly projections still open.
8. Team Review → window beat: with a differing suggestion, "{n}% playoff chance · Consider …" and
   the roster read shown as secondary. Nothing saves until you press the action.
9. Switch league: no number or prompt from the previous league appears, even briefly.
10. ESPN/MFL league: no playoff row, no prompt.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | League projections: `model_current`, `outlook_recommendation`, scenario SD rule, result keys; Team Review `window.projection` |
| `living-memory/LLD.md` | updated | League projections: model v5 conventions |
| `docs/architecture.md` | updated | `league_projections` paragraph: v5 and `recommendation.py` |
| `living-memory/HLD.md` | updated | League projections line |
| `docs/cross-client-invariants.md` | updated | New "Playoff chance → suggested outlook" |
| `docs/glossary.md` | updated | Universal score SD; outlook suggestion; incomplete forecast |
| `docs/config-reference.md` | updated | Weekly league projections; new flag |
| ADR / `DECISIONS.md` | updated | D-229 (model v5), D-230 (suggestion and precedence) |

## 5. Ship gate declaration

- CI green on the pushed sha; evidence in `living-memory/TEST_LEDGER.md`.
- TestFlight verification: checklist above, operator.
- Express lane declared by the operator? No.

## Addendum — 2026-11-12: league-level free-agent line removed

Model v6 (D-234, commit `cf0a7552`, no scope file of its own, so it is recorded here) added a line under the Projected standings status line saying how many open lineup slots use the best available free agent and how many count as 0 (for example "12 open lineup slots use the best available free agent; 1 has none and counts as 0."). The operator asked for it to be removed: "For projected standings, we can remove the copy underneath the 'Weekly estimate - partial sleeper data' line."

- **What changed:** the app (`mobile/src/components/LeagueProjectionSection.tsx`) and web (`web/js/league-projections.js`) no longer render it in any of its three wordings, and the `freeAgentFillSentence` helper is gone from both clients. The status line, the incomplete sentence (a played starter with no recorded score) and the per-row "(free agent)" marker in a team's lineup detail are unchanged. No backend change: `coverage.fa_filled_slots` / `zero_filled_slots` and `projection_coverage.free_agent_fills` stay in the payload.
- **Evidence:** `mobile/tests/check-league-projections.js` and `check-league-projections-web.js` now require the line and helper to be absent (web: rendered with free-agent counts of 12/1, 1/0, 0/3 and 0/1, alone and beside an incomplete estimate) while the status line, the incomplete sentence and the row marker stay. Each new or changed assertion was sabotaged red and restored green with an unchanged checksum. TestFlight check for the operator: on a Sleeper league whose forecast has open slots, Projected standings shows the "Weekly estimate · Partial Sleeper data" line with no free-agent sentence under it; opening a team's week still marks a free-agent starter "(free agent)".
