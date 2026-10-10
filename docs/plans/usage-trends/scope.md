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
| Acting in another league | The availability sheet (A) and the expanded row (B) carry each league's own Add/Trade, as drawn. Acting in a league other than the focused one **switches the focused league first** (the MatchesScreen precedent), then pins or opens the claim sheet. | lead, from the approved mock |
| Platforms | **Mobile only** (operator, 2026-10-10). Web waived for v1. | operator |
| Ship posture | **Merge + deploy, flag off** (operator, 2026-10-10), **but not before the home-engagement redesign (`design/home-engagement`) is live** (operator, same day). The Home entry is re-homed onto that redesign at rebase. | operator |
| Visual direction | **Two views behind one pill** (operator, 2026-10-10). **Version A "Simple"** = draft A *as drawn* ("the mock is perfect as is"): story cards, the per-league availability sheet with its own Add/Trade per league, the visible podium Re-rank. **Version B "Raw stats"** = a plain table modeled on the operator's snap-count source sheet: one column per week for the selected stat and a total column on the right, then icon-only actions (+ add, stacked ⇄ trade, the podium Re-rank, and a chevron that expands the row into the other leagues). [Drafts](https://claude.ai/artifact/WUZmSymvTASsQvdjeK8yjo). | operator |

## 1. Analytics scope

- [x] **(a) New events specced.** Addendum: [`docs/business/analytics/2026-10-10-usage-trends-events.md`](../../business/analytics/2026-10-10-usage-trends-events.md). Registered in `backend/analytics_taxonomy.py`; the two non-intent events are listed in `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitters.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `usage_trends_action` (INTENT) | `league_id, action (trade\|add\|rerank), player_id, position, metric, signal, focus_status, ownership, view` | Trade, Add or Re-rank tapped (row, availability sheet, or expanded table row) | mobile |
  | `usage_trends_availability_opened` (non-intent) | `league_id, player_id, n_leagues, n_free_agent, view` | Availability sheet opened / table row expanded | mobile |
  | `usage_trends_view_changed` (non-intent) | `league_id, metric, ownership, view` | View pill, metric or ownership changed | mobile |

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
  - only registered analytics names and props are emitted
  - the client never re-sorts stats (it orders by the server `rank`)
  - the pure readers in `utils/usageTrends.ts` are EXECUTED under node:
    - league status, with orphan rosters never free agents;
    - the filter;
    - the mock's headline copy and its no-jargon vocabulary;
    - table cells and the total;
    - the availability label.
  - the A/B pill, B's icon-only actions and inline league expansion, and A's podium Re-rank

  Six named sabotages, each proven red, then green on revert (TEST_LEDGER).
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
  1. Home shows a **Usage Trends** row. Tap it: the screen opens with a back control and an info (i) button. It shows the focused league's name and "Weeks 1–N", a **Simple | Raw stats** pill, and exactly one feedback button.
  2. **Simple** (Version A), **Snaps / All**. Under "Biggest jumps last week", each card shows:
     - the name, position and team;
     - one sentence, e.g. "Jumped to 90% of Eagles plays";
     - four bars with the newest jump in pink;
     - Add, Trade or Yours, the league pips with "FA n/m", and Re-rank.

     "Everyone else" follows. There is no sort control.
  3. Switch to **Targets**, then **Carries**: the order and the sentences change.
     - Open **Filters → Count**: sentences read in counts, e.g. "Jumped to 21 targets".
     - **Filters → WR** shows only receivers.
     - Spot-check CeeDee Lamb's Week 4 targets = 21 against Sleeper.
  4. Tap a player's **FA n/m** pill. The sheet lists every league with its status ("Free agent", "On your roster", "Rostered by <manager>"), and the focused league is tagged "This league".
     - Tap **Add** on the focused Sleeper league: the claim sheet opens (FAAB / drop) and "Open in Sleeper to claim" lands on the league's players page.
     - Tap **Trade** on ANOTHER league: the app switches to that league, then Find a Trade opens with the player pinned and his manager selected.
  5. On an ESPN or MFL league row, **Add** shows the "can't add here" explanation and does not switch leagues.
  6. Flip the pill to **Raw stats** (Version B). You see a table: Player · W1–W4 · **Tot**. Each row's actions are icon-only:
     - **+** for a free agent;
     - stacked arrows for another manager's player;
     - a check for yours;
     - then the podium and a chevron.

     A missed week reads OUT, a bye reads BYE, and the newest jump is pink. Tot equals the sum of the played weeks. **Filters → % of team** switches the cells to % and the last column to **Avg**.
  7. Tap a row's **chevron** (or the row): it expands to list your leagues with each league's Add/Trade. The chevron points down, and tapping again collapses it.
  8. Tap the **podium** on a WR: Quick Set opens on **WR**. Go back, then tap the podium on a TE: Quick Set switches to **TE** (it was already open). The **Re-rank** button in Simple view does the same.
  9. The **Free agents** filter in either view shows only Add actions. **Rostered** shows Trade or Yours. The Free Agents screen's **See usage trends** link opens pre-filtered to Free agents.
  10. A player who missed a game shows an amber tick and "–" (Simple) or OUT (Raw stats), and his average and total cover only the games he played.
  11. Leave the screen in **Raw stats**, open it again: it reopens on Raw stats (remembered until the app restarts).
  12. Kill switch: `usage_trends.enabled` false + relaunch twice. No Home row, no Free Agents link, and `GET /api/usage-trends` returns 404.
- [x] **WAIVED — web:** operator chose mobile only for v1.
- `testID`s added: `home.option.trends`, `free-agents.usage-trends-link`, `usage-trends.screen`, `usage-trends.back-btn`, `usage-trends.info`, `usage-trends.view.<simple|stats>`, `usage-trends.metric.<snaps|carries|targets>`, `usage-trends.ownership.<all|rostered|free_agents>`, `usage-trends.filters`, `usage-trends.filters-sheet`, `usage-trends.position.<all|rb|wr|te>`, `usage-trends.unit.<share|count>`, `usage-trends.filters-done`, `usage-trends.list`, `usage-trends.row.<id>`, `usage-trends.action.<id>`, `usage-trends.yours.<id>`, `usage-trends.availability.<id>`, `usage-trends.rerank.<id>`, `usage-trends.expand.<id>`, `usage-trends.availability-sheet`, `usage-trends.availability-close`, `usage-trends.league.<id>.<league>`, `usage-trends.league-action.<id>.<league>`, `usage-trends.unavailable`, `usage-trends.no-league`, `usage-trends.pick-league`, `usage-trends.error`, `usage-trends.off-season`, `usage-trends.empty`. None is referenced by a retained Maestro flow, so testid-lint needs no allowlist entry

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | new `GET /api/usage-trends` row + contract |
| `living-memory/LLD.md` | updated | route + in-process cache convention entry |
| `docs/architecture.md` | updated | `usage_trends.py` in the module map; Sleeper stats feed in data flow |
| `living-memory/HLD.md` | n/a | one read-only route + one screen over existing seams; no new subsystem |
| `docs/cross-client-invariants.md` | n/a | mobile only; the signal kinds are a server→client enum documented in api-reference, with no second client yet |
| `docs/glossary.md` | updated | Usage Trends, team share, spike, return, new role |
| ADR or `DECISIONS.md` entry | updated | D-201: share-driven spikes; byes AND missed games out of averages; Sleeper stats feed as the usage source |
| `docs/config-reference.md` | updated | `usage_trends.enabled` row |
| `docs/data-dictionary.md` | n/a | no schema change |
| `mobile/src/navigation/{CLAUDE,README}.md`, `mobile/src/screens/{CLAUDE,README}.md` | updated | route tree + screen inventory |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs the `check-*.js` suites) + `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved.
- **TestFlight verification:** the §3 checklist, run by the operator on the first build carrying the screen; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No**, full gates.
- Design direction built: **both**, behind the Simple | Raw stats pill. Version A is draft A as drawn; Version B is the per-week stats table (see §0).
