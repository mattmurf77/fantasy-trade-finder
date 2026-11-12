# Feature Scope — Playoff forecasts for league-median leagues; store the median setting on link

**Date:** 2026-11-11
**Entry point:** direct ask (operator, 2026-11-11): "Let's make the model change to solve for median scoring leagues. Ensure we also include checking that when users link a new league and update the DB to store that setting"
**Builder:** Opus subagent, worktree `feat/projection-median-leagues`
**Operator sign-off on waivers:** not needed. The waivers below (analytics, mobile evidence, flag) follow from a backend-only change with no new client surface; they are listed for the operator to see.

---

## What changes

**Part A — the model.** Sleeper leagues with `settings.league_average_match == 1` play a second game every week, against the median of the whole league's scores that week. `provider.capture` refused them (`unsupported_divisions_median_bestball_or_manual_seeding`). Now:

- capture admits them, books each completed week's median result per team, and still checks the rebuilt record against Sleeper's official one (`standings_include_unfinalized_or_adjusted_points` if it differs);
- `simulate` books, for every simulated week, each team's head-to-head result and its result against that week's median of the drawn (or, for a completed lineup, recorded) scores. Standings, tiebreaks, seeding, byes, playoff chance and the non-playoff draft order all read the combined record;
- the snapshot and the result carry `league_format: {median_game, games_per_week}` on every league (`false, 1` for head-to-head);
- `core.VERSION` is unchanged: a head-to-head league's snapshot and result are byte-identical to before apart from the marker (golden digests from origin/main 455d1265 in `test_league_projection_median.py`).

**The median rule** (`core.median_outcomes`). The median is taken over every team's score that week. A score above it wins, below it loses. With an even team count that is the mean of the two middle scores, so the top half wins and the bottom half loses. A score exactly equal to it ties. Points against are unchanged: the median game adds a result, not points.

**How the rule was verified.** One real 12-team median league's public Sleeper data (weeks 1 to 9 complete) was run read-only, outside the repo, through both a standalone reconstruction and the real `provider.capture`: reconstructed records matched the official records for all 12 teams over 9 weeks (18 results each), and points for and points against (head-to-head opponents only) matched for all 12. Read as head-to-head only, the same league fails capture's reconciliation. No week in the sample had a tie at the cutoff (the two middle scores were never equal), so **the tie rule is unverified**; the repo's Sleeper notes do not document it, so a score exactly equal to the median is a tie, which is also what `season_history.py` has always done. Nothing from that league is in the repo; the committed tests use invented scores.

**Tiebreakers.** The model already sorts on win credit (wins + ½ ties), then points for, then points against, then a seeded lottery (`seeding: record_pf_higher_pa_random`). The median game changes only the win credit. It adds nothing to points for or against (verified above), so no tiebreaker changes.

**Part B — the stored setting.** One nullable column `leagues.median_game` (1 / 0 / NULL). Session init passes `league_median_setting(<the league payload it already fetched>)` to `upsert_league`, which writes it on first link and refreshes it on every later sync (insert and update-only paths). NULL means unknown: not a Sleeper league, a missing or unexpected setting, or not synced since the column arrived. An existing row is filled at that league's next sync; there is no backfill. ESPN, MFL and Fleaflicker rows stay NULL: none of the three adapters reads an equivalent setting. The forecast does not read this column; capture reads the live Sleeper setting every run.

**Getting the forecast right after deploy.** A median league refused before this change keeps its `unsupported_policy` attempt until its weekly slot. `POST /api/cron/league-projections` now accepts `{"retry_unsupported": true}`, a sibling of `retry_incomplete` (one helper, `batch._retry_baselines(now, status)`): every unleased target whose last attempt was `unsupported_policy` under the current model is made due now (`retried_unsupported` in the response). Operator-only, weekly mode only; scheduled ticks never pass it. Call it once after deploy. Tests: `test_league_projection_batch.py` (`retry_unsupported` block).

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** no new user action or surface. The forecast's output gains a field; the link path stores one more value. No event is added or changed.

## 2. Schema & flag scope

- New/changed tables or columns: `leagues.median_game` INTEGER, nullable, in `leagues_table` and in `_migrate_db`'s `migration_cols` (SQLite and Postgres) → `docs/data-dictionary.md` updated.
- New/changed feature flags: none. Median leagues ride the existing `league.projections` gates; a head-to-head league's output is unchanged, so there is nothing to stage behind a flag.
- New env vars / `model_config` keys: none.
- Failure reason renamed: `unsupported_divisions_median_bestball_or_manual_seeding` → `unsupported_divisions_bestball_or_manual_seeding`; new `unsupported_median_setting` (a `league_average_match` that is not 0, 1 or absent). No client reads either string (clients key on the `unsupported_policy` state); saved failed runs keep the old string until their next run. `docs/runbook.md` lists both.

## 3. Evidence scope

- [ ] **Structural guard:** n/a — no mobile change.
- [x] **Unit tests:** `backend/tests/test_league_projection_median.py` (32 tests: the rule; capture admission, completed-week results, reconciliation and the remaining refusals; zero-SD exact records; noisy conservation; the "misses head-to-head, makes it on median wins" seeding case; non-median golden digests; scenario POST + worker on a stored median snapshot and on a pre-marker saved result; outlook suggestion). `backend/tests/test_league_median_setting.py` (16 tests: migration, the payload reader, insert/refresh/NULL-fill on `upsert_league`, ESPN NULL, session init on link and re-sync with the meta call count unchanged, MFL NULL). Three existing tests that expected median leagues to be refused were changed to drop that case and use the new reason string. Every behavioural test was proven RED against a named sabotage (table in the report / TEST_LEDGER).
- [x] **Code-walk proof:** capture `backend/league_projections/provider.py` (median admission + completed-week median results after the head-to-head loop; marker in the returned snapshot); simulate `backend/league_projections/simulation.py` (marker read, record-scale check, median results after each simulated week's head-to-head loop, weekly `median_*_probability`, `league_format` in the result); session init `backend/server.py` `upsert_league(..., median_game=...)` in `_session_init_background_writes_impl`.
- [ ] **Manual TestFlight checklist:** waived — no client change. The operator's median league is the runtime check: after the next weekly run its forecast should exist, its current record should match Sleeper's, and records should total two games a week.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | League projections: `league_format`, two-games-a-week record fields, weekly `median_*_probability`, the renamed/new unsupported reasons |
| `living-memory/LLD.md` | n/a here | builder may not edit `living-memory/`; the main session writes back (no convention shift beyond the column) |
| `docs/architecture.md` | n/a because it lists no supported or unsupported league formats for forecasts | |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a because no shared enum changed: clients key on the `unsupported_policy` state, never on the reason string | |
| `docs/glossary.md` | updated | "League median (median game)" |
| `docs/data-dictionary.md` | updated | `leagues.median_game` |
| `docs/runbook.md` | updated | Playoff forecasts reasons table |
| `docs/integrations/sleeper.md` | updated | `league_average_match`: meaning, the verified rule, where it is stored |
| ADR or `DECISIONS.md` entry | for the main session | the tie rule (unverified, tie) and keeping VERSION are worth a D- entry |

## 5. Ship gate declaration

- **CI green:** `backend-tests` on the pushed sha (no mobile or web change).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry with the two new files, the sabotage names and the aggregate sample check — written by the main session.
- **TestFlight verification:** none needed (no client change).
- Express lane declared by the operator? no.

## Not built (reported)

- **Client copy.** The weekly detail row says "vs <opponent>: win X%"; for a median league it could add "vs league median: win Y%" from `median_win_probability`. Records already render as numbers, so "13–5" displays correctly. Files: `mobile/src/components/LeagueProjectionSection.tsx` (weekly line), `web/js/league-projections.js` (weekly line). No client string says median leagues are unsupported.
- **Exposing `median_game` to clients.** `get_league_summary` (`backend/database.py`) is the natural place, but it builds several return dicts, so it is more than a one-line field. Left.
- **Completed-season forecast targets** (`season_state_mismatch` every week): see the report.
