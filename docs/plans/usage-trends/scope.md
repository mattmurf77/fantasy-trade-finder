# Feature Scope — Usage Trends

**Date:** 2026-10-10
**Entry point:** direct ask (operator, 2026-10-10, with a ChatGPT usage-analysis transcript + Weeks 1–4 snap/target CSVs as the brief)
**Builder:** session 2026-10-10 (lead + design-draft agent + mobile build agent)
**Operator sign-off on waivers:** yes — web waived (operator chose "Mobile only"), see §3/§4

---

## 0. What it is, and the decisions it rests on

An in-season screen listing NFL **RBs, WRs and TEs** with their usage over the **last four completed weeks**. Three metrics (**snaps, carries, targets**), each viewable as a raw count or as a **% of the team's total that week**. Every row shows one plain-language headline signal. The server orders the list so the user never has to sort stats (operator, 2026-10-10: "simple, easy to understand without much reading or sorting of stats … even casual dynasty players").

Per row, three actions:

- **Trade / Add / Yours.** League-specific, against the focused league.
  - **Trade:** the player is on another manager's roster. Pins him on the receive side, hands off that manager, and runs Find a Trade.
  - **Add:** the player is a free agent. Sleeper leagues get the existing #179 claim-prep sheet, which hands off to Sleeper (Sleeper has no roster-move API). ESPN/MFL/Fleaflicker get the existing honest "can't add here" explanation.
  - **Yours:** the player is on the caller's roster. Shown as a label, not a button.
- **Availability.** A compact summary across all of the user's leagues. It opens a sheet listing each league: free agent / on your roster / rostered by <manager>. Modelled on Sleeper's "Availability in other leagues".
- **Re-rank** (operator addition, 2026-10-10). Opens Quick Set (`QuickSetTiers`) on the player's position.

Ownership filter: **All** (default) · **Rostered** (on any roster in the focused league) · **Free agents** (on none).

| Decision | Ruling | By |
|---|---|---|
| Data source | Sleeper's public weekly **actual-stats** feed `api.sleeper.app/stats/nfl/{season}/{week}`, the sibling of the projections feed already read by `season_forecasts.py` / `fit_engine.py`. No new vendor and no scraping. **Validated 2026-10-10** against the operator's two files: snaps matched on 1652 of 1656 RB/WR/TE player-weeks; targets (Footballguys export) matched on 1648 of 1652. Team totals match too (NYJ snaps 66→32, CHI 72→93, PHI targets 25/25, DAL 40→43). Carries come from the same feed. | lead |
| Window | The last 4 **completed** regular-season weeks (Sleeper `state.week` is the week in progress). Pre-season, post-season and week 1 return an out-of-season payload. | lead |
| Byes | Left out of the average's divisor (operator brief). A bye is a week where the player's team has no offensive snaps. | operator |
| Missed games (team played, player didn't) | **Also left out of the average** and shown as "out" on the chart (operator, 2026-10-10, chose this over "count as zero"). | operator |
| Team share | Snaps ÷ `tm_off_snp`. Carries and targets ÷ the team's sum over every QB/RB/WR/TE/FB row. **QB carries count in the carry denominator.** | lead |
| Spike | A played week whose **team share** beats both the player's earlier-week average and his previous game by 15 pp of snaps, 10 pp of carries or 8 pp of targets. The week also needs at least 20 snaps, 6 carries or 4 targets. **Share-driven, not count-driven**: Braelon Allen's Week 4 snaps fell 34→30 while his share rose 52%→94%, and Tee Higgins' snaps rose 53→60 while his share fell 93%→79%. The previous-game clause stops a steady riser from reading as a spike. The most recent week's spikes rank first. Week 4 yields 32 snap, 27 target and 13 carry spikes NFL-wide, and the top of each list is the transcript's standouts. | lead (thresholds tunable in `backend/usage_trends.py`) |
| Other signals | `return` (back after missed games), `new` (first game of the window with real volume), `out` (missed the latest week), `rising` / `falling` (share slope of at least 5 pp a week over 3 or more games). | lead |
| Naming | **"Usage Trends"**, everywhere (route `UsageTrends`, `/api/usage-trends`, `usage_trends.*`). "Trends" is already the Rank stack's Elo risers/fallers screen (`TrendsScreen`, `/api/trends/*`). | lead |
| Entry points | Home tab row, plus a link on the Free Agents screen that opens pre-filtered to free agents (operator, 2026-10-10). | operator |
| Platforms | **Mobile only** (operator, 2026-10-10). Web waived for v1. | operator |
| Ship posture | **Merge + deploy, flag off** (operator, 2026-10-10). | operator |
| Visual direction | See [design drafts](https://claude.ai/artifact/WUZmSymvTASsQvdjeK8yjo); the build follows the direction recorded in §5. | operator |

## 1. Analytics scope

- [x] **(a) New events specced.** Addendum: [`docs/business/analytics/2026-10-10-usage-trends-events.md`](../../business/analytics/2026-10-10-usage-trends-events.md). Registered in `backend/analytics_taxonomy.py`; the two non-intent events are listed in `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitters.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `usage_trends_action` (INTENT) | `league_id, action (trade\|add\|rerank), player_id, position, metric, signal, focus_status, ownership` | Trade, Add or Re-rank tapped on a row | mobile |
  | `usage_trends_availability_opened` (non-intent) | `league_id, player_id, n_leagues, n_free_agent` | Availability sheet opened | mobile |
  | `usage_trends_view_changed` (non-intent) | `league_id, metric, ownership` | Metric or ownership chip changed | mobile |

  Screen opens are the auto-emitted `screen_viewed {screen: 'UsageTrends'}`. Entry source is its `prev_screen` (`Home` vs `FreeAgents`).

## 2. Schema & flag scope

- New/changed tables or columns: **none**. In-process caches only (`server._usage_cache`), following the outlook and free-agent cache precedent.
- New/changed feature flags: **`usage_trends.enabled`**, default **false**.
  - Registered in `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, `backend/tests/fixtures/flags/release.json` and `docs/config-reference.md`.
  - Gates `GET /api/usage-trends` (404 when off) and both mobile entry points.
  - **Graduation criterion:** one TestFlight build has run §3's checklist clean with the flag on for the operator, and the operator turns it on for everyone.
- New env vars / `model_config` keys: **none**.
  - Spike thresholds are module constants in `backend/usage_trends.py`. They are not `model_config` knobs because they are not trade-engine math, and a code change is the right review gate for them.
  - Rollback lever: `usage_trends.enabled` false, then `POST /api/feature-flags/reload`. Takes effect without a deploy.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-usage-trends.js` (`npm run test:usage-trends`, also run by CI's check-*.js loop). It pins:
  - route registered in `RootNav` + `deepLinks`
  - Home row and Free Agents link both gated on `usage_trends.enabled`
  - one `FeedbackFAB` on the screen
  - the three action testIDs
  - Re-rank navigates to `QuickSetTiers` with `position`
  - Trade uses the `useFinderTargets` pin + handoff
  - Add reuses the shared `ClaimSheet`
  - only registered analytics names are emitted
  - the client never re-sorts stats (it orders by the server `rank`)
- [x] **Unit tests:** `backend/tests/test_usage_trends.py`, 24 tests:
  - window
  - team share incl. QB carries
  - bye and out left out of the average
  - share-driven spikes, the volume floor, the previous-game clause
  - return / new / rising
  - rank order
  - low-usage trim
  - partial-window refusal
  - real-data regression on a trimmed 2026 NYJ + PHI capture
  - route: flag gate, roster join incl. orphaned roster, non-member league withheld, ESPN snapshot path, 503 without caching the failure, out-of-season shape, stats cache

  Six named sabotages, each proven red, then green on revert (TEST_LEDGER).
- [x] **Code-walk proof:** file:line trace of focus status → action routing, recorded in `living-memory/TEST_LEDGER.md` with the ship entry.
- [x] **Manual TestFlight checklist** (the only runtime evidence mobile gets). Turn on `usage_trends.enabled` for the test, then relaunch twice; flags are cached.
  1. Home shows a **Usage Trends** row. Tap it: the screen opens with a back control, the focused league's name and "Weeks 1–N", and exactly one feedback button.
  2. Default view is **Snaps / All**. The first rows are the latest week's spikes. Each row shows one plain-language line, a 4-week mini chart and one number. No sort control exists.
  3. Switch to **Targets**, then **Carries**: the order changes. Toggle count vs **% of team** and the numbers change. Spot-check two players against Sleeper's game log, e.g. CeeDee Lamb Week 4 targets = 21.
  4. **Free agents** filter: every row's first action reads **Add**. Tap Add on a Sleeper league: the claim sheet opens (FAAB/drop) and "Open in Sleeper to claim" lands on the league's players page. On an ESPN/MFL league: the "can't add here" alert.
  5. **Rostered** filter: rows show **Trade**, or a **Yours** label for your own players. Tap Trade: Find a Trade opens with the player pinned on the receive side and his manager selected, and the search runs.
  6. Tap the **availability** control on a player you know is owned in one of your leagues and free in another. The sheet lists every league with the right status and manager name.
  7. Tap **Re-rank** on a WR: Quick Set opens on **WR**. Go back, tap Re-rank on a TE: Quick Set switches to **TE** (it was already mounted).
  8. Free Agents screen shows a **See usage trends** link. It opens Usage Trends pre-filtered to **Free agents**.
  9. A player who missed a game shows that week as "Out" on the chart, and his average matches his played games only.
  10. Kill switch: `usage_trends.enabled` false + relaunch twice. No Home row, no Free Agents link, and `GET /api/usage-trends` returns 404.
- [x] **WAIVED — web:** operator chose mobile only for v1.
- `testID`s added: `home.option.trends`, `free-agents.usage-trends-link`, `usage-trends.screen`, `usage-trends.back-btn`, `usage-trends.metric.<snaps|carries|targets>`, `usage-trends.unit.<count|share>`, `usage-trends.ownership.<all|rostered|free_agents>`, `usage-trends.row.<id>`, `usage-trends.action.<id>`, `usage-trends.availability.<id>`, `usage-trends.rerank.<id>`, `usage-trends.availability-sheet`

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | new `GET /api/usage-trends` row + contract |
| `living-memory/LLD.md` | updated | route + in-process cache convention entry |
| `docs/architecture.md` | updated | `usage_trends.py` in the module map; Sleeper stats feed in data flow |
| `living-memory/HLD.md` | n/a | one read-only route + one screen over existing seams; no new subsystem |
| `docs/cross-client-invariants.md` | n/a | mobile only; the signal kinds are a server→client enum documented in api-reference, with no second client yet |
| `docs/glossary.md` | updated | Usage Trends, team share, spike, return, new role |
| ADR or `DECISIONS.md` entry | updated | D-199: share-driven spikes; byes AND missed games out of averages; Sleeper stats feed as the usage source |
| `docs/config-reference.md` | updated | `usage_trends.enabled` row |
| `docs/data-dictionary.md` | n/a | no schema change |
| `mobile/src/navigation/{CLAUDE,README}.md`, `mobile/src/screens/{CLAUDE,README}.md` | updated | route tree + screen inventory |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs the `check-*.js` suites) + `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved.
- **TestFlight verification:** the §3 checklist, run by the operator on the first build carrying the screen; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No**, full gates.
- Design direction built: *(filled in at build: the draft the operator picked, or the recommendation if they deferred)*.
