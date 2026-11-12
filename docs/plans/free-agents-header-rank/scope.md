# Feature Scope — Free Agents: league selector header + overall positional rank

**Date:** 2026-11-12
**Entry point:** direct ask (operator TestFlight feedback on the Free Agents page)
**Builder:** builder agent, branch `fix/free-agents-header-rank` (cut from `origin/main` `12ac0f1d`)
**Operator sign-off on waivers:** not needed for build; the waivers below (§1 analytics, no flag, no schema) are surfaced in the hand-off report

Operator, verbatim: "The free agents page breaks the behavior of other pages where the league
selector stays as a header. Additionally, the positional ranks present of all FAs (so Theo Johnson
shows as TE1). It should instead be overall at the position (regardless of who is owned or not)."

Two changes:

1. **Rank.** `pos_rank` on `GET /api/league/free-agents` is now the player's overall rank at the
   position on the caller's board: every non-pick pool player at that position, rostered or not,
   ordered by the same `board_value` the rows are priced from. A free-agent TE who is the 23rd TE on
   the board reads TE23, not TE1.
2. **Header.** The Free Agents push wears the same global `TopBar` (league cluster →
   `LeagueSwitcherSheet`) the tab screens sit under, with the Chalkline sub-header (JS back + title)
   beneath it. Switching league there reloads the list for the new league.

### Design choice: change what `pos_rank` means (no new field)

The shipped binary renders `${row.position}${row.pos_rank}` (`FreeAgentsScreen.tsx:300`) and the
claim sheet header renders `row.pos_rank`. Only a change to `pos_rank` itself reaches the testers'
build without an app update; a new field would need a new binary to read it. The route's
`pos_rank` has exactly two readers, both on the Free Agents surface (`git grep pos_rank`):
`FreeAgentsScreen.tsx:300` (the row) and `ClaimSheet.tsx:693` (the sheet header, reached from that
row; Usage Trends' claim targets carry no `pos_rank`). The other `pos_rank`s in the repo belong to
other routes and are untouched: `/api/extension/rankings` (`server.py` ~36387, read by
`extension/content.js:222`), Team Review (`team_review.py`), Trends (`TrendsScreen`),
`consensus_pos_rank` on `/api/rankings`, and the trade engine's `_positional_rank_map`. No web
client reads the free-agents route. So the meaning changes in one place and nothing else shifts.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** none exists for a league switch. `TopBar`'s switcher emits
      no event on the tab screens either, and this change reuses that component unchanged, so the
      Free Agents switch behaves identically (no event). The page's existing events
      (`fa_move_*`, `claim_*` from `ClaimSheet`) are unchanged.
- [x] **(c) WAIVED — no analytics needed because:** the change reuses the existing header selector
      (which has never emitted) and changes a number's definition, not a user action. If the
      operator wants league-switch usage measured, that is one new event for all TopBar instances,
      specced separately.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: **none.** Argued: the rank fix is a correction the operator asked for
  in testers' hands now; a flag would ship the wrong number by default or need a flip to deliver
  the fix. The header is a layout change to one push with no data or server dependency; the
  rollback lever is a revert of `RootNav.tsx`'s FreeAgents options (one block). The server rank
  change is deploy-free to roll back by reverting `free_agent_service.py` (one function).
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-free-agents-header.js` (`npm run test:free-agents-header`),
      23 assertions — pins: RootNav renders FreeAgents' header as `LeagueTopBarHeader` with the
      `free-agents.back-btn` JS back (`canGoBack ? goBack : navigate('Main')`) and no native
      `headerLeft`; `LeagueTopBarHeader` renders `<TopBar />` unconditionally, then the back control
      and title, the title layer `pointerEvents="none"`; TopBar's `topbar.league` cluster opens its
      `LeagueSwitcherSheet`; FreeAgentsScreen builds no second selector or TopBar, mounts exactly one
      `FeedbackFAB activeScreen="FreeAgents" aboveTabBar={false}`, pads only the bottom inset; the
      list is keyed and fetched by the session `leagueId`; a league change drops an open claim; the
      claim sheet mounts only while its league is active; "Claim pending" stays league-keyed; the row
      renders the server `pos_rank` as-is. Each assertion sabotage-proven (table below).
- [x] **Unit tests:** `backend/tests/test_free_agents.py` — replaced
      `test_pos_rank_is_within_position_over_the_fa_pool` (it pinned the old meaning) with
      `test_pos_rank_is_overall_at_the_position_not_among_free_agents`, and added
      `test_pos_rank_counts_the_callers_own_roster_too`,
      `test_free_agent_te_who_is_the_23rd_te_reads_te23`,
      `test_pos_rank_does_not_depend_on_which_rosters_loaded`,
      `test_pos_rank_follows_the_callers_board`, `test_picks_are_never_ranked`,
      `test_pos_rank_ties_keep_pool_order`. The existing
      `test_position_filter_keeps_global_pos_rank` still pins filter stability.
- [x] **Code-walk proof:** below.
- [x] **Manual TestFlight checklist:** below. Part A (rank) needs only the server deploy; Part B
      (header) needs a new build.
- `testID`s added/renamed: none. Reused: `topbar.league`, `topbar.format`, `topbar.settings`
  (TopBar), `free-agents.back-btn` (kept, now inside the custom header; still a literal at the
  registration so `testid-lint` resolves it).

### Code-walk proof

**Rank (server).**
1. `server.py:41597` calls `compute_free_agents(pool_players, seed, user_elo, rostered_ids=rostered,
   user_roster, position, tier_fn)`; `user_elo` is the caller's whole board (`server.py` ~41418).
2. `free_agent_service.py:125–129` sorts the **whole** board at QB/RB/WR/TE by
   `board_value(p.id, user_elo, seed_elo)` (personal Elo, seed fallback), picks excluded via
   `is_pick_asset` (#222). `sorted` is stable, so equal values keep pool order — the existing rule.
3. `:136–138` numbers each position over that board, before any roster exclusion or filter, so
   `pos_rank` depends only on the pool and the caller's board — not on `rostered`, `user_roster` or
   `position`.
4. `:140` drops rostered players from the list (`ranked`); a stable sort followed by a filter keeps
   exactly the order the old code produced by sorting the free agents alone, so the list order,
   drop suggestions (`:147–155`), the position filter (`:156`) and the 50-row limit are unchanged.
5. `:180` writes `pos_rank[p.id]` onto each row; the shipped app renders it unchanged
   (`FreeAgentsScreen.tsx:300`, `ClaimSheet.tsx:696`).

**Header and league switch (app).**
1. `RootNav.tsx:889–918`: FreeAgents' options set `header: () => <LeagueTopBarHeader title="Free agents"
   back={<HeaderBack testID="free-agents.back-btn" …/>} />`. Native-stack renders a custom `header`
   in a View above the screen and hides the native bar
   (`@react-navigation/native-stack` 7.14.11, `NativeStackView.native.tsx:292, 455–471`), so the
   iOS 26 dead native back (RNS#3294) is never on screen; the JS `HeaderBack` is the only back.
2. `RootNav.tsx:289–306` `LeagueTopBarHeader` renders `<TopBar />` (owns the top safe-area inset,
   as above `TabNav`) and a 44pt sub-header: `{back}` + the centred `HeaderTitle`.
3. `TopBar.tsx:334–335` the `topbar.league` cluster opens `TopBar.tsx:431` `LeagueSwitcherSheet`.
   A row tap runs `LeagueSwitcherSheet.tsx:51` `switchLeague`, which awaits the backend session
   init and then `useSession.ts:538` `setLeague` → `useSession.ts:494` `set({ league: lg })`.
4. `FreeAgentsScreen.tsx:51` reads `leagueId` from that slice; `:68` keys the list on
   `['free-agents', leagueId, filter]`, so the new id is a new query: the screen shows the spinner
   (`isLoading`, no placeholder data) and then the new league's rows, drop suggestions,
   `move` capability, roster capacity, waivers and drop candidates — all from the one response. The
   position filter is kept.
5. Claim sheet: `:95–99` an effect on `[leagueId]` clears `claimTarget`, `claimMove` and
   `claimLeagueId`; `:108` records the league at the tap; `:243` mounts `ClaimSheet` only while
   `claimLeagueId === leagueId`, so even the render between the switch and the effect cannot pair an
   old row with the new league. In practice the ClaimSheet is a Modal over the header, so the header
   can't be tapped while it is open; the guard covers a switch from anywhere else.
6. `useClaimsPending`: `:235` `isClaimPending(pendingClaims, leagueId, item.player_id)` is keyed by
   (league, player), so "Claim pending" shows only for the league the claim was made in.
7. "See usage trends" (`:207`) navigates with `{ ownership: 'free_agents' }` only; Usage Trends
   reads the session league when it mounts, so after a switch it opens on the new league.
8. An open sheet at the moment of the switch: the switch is made from `LeagueSwitcherSheet`, a
   Modal; iOS does not stack sibling RN Modals, so no ClaimSheet or bell sheet can be open at the
   same time from this screen. The switcher closes itself on success (`LeagueSwitcherSheet.tsx:53`).
9. `FeedbackFAB` (`FreeAgentsScreen.tsx:260`) unchanged; `SafeAreaView edges={['bottom']}` (`:118`)
   unchanged, now correct for a TopBar that pads the top.

### Manual TestFlight checklist (operator)

**Part A — rank (server deploy only; the current TestFlight build is enough).**
1. League tab → Free agents, ALL. Find a free-agent tight end (e.g. Theo Johnson). Expected: it no
   longer reads TE1; it reads TE*n* where *n* is his rank among all TEs on your board. Cross-check:
   Rank → Overall ranks, TE filter — his position there matches *n*.
2. Tap the TE pill. Expected: the same player shows the same TE*n* as under ALL.
3. Tap Add on that row (Sleeper league). Expected: the sheet header reads "<team> · FA TE*n*"
   on the current build (new build: "<team> · TE*n*").
4. Pull to refresh twice. Expected: the numbers don't change.
5. Expected for every row: no two rows at one position share a number, and a lower row never has a
   smaller number than a row above it at the same position.

**Part B — header (needs a build from this branch).**
6. Open Free agents. Expected: the top bar matches the tab screens (brand tick, "LEAGUE", league
   name, format tile, ice chevron, bell, gear); under it a bar with a back chevron and "FREE AGENTS".
   Nothing overlaps the status bar or the notch.
7. Tap the back chevron. Expected: returns to the League tab. Re-open; swipe from the left edge.
   Expected: also returns.
8. Open Free agents, tap the league name. Expected: the "Switch league" sheet. Pick another league.
   Expected: the sheet closes, the header shows the new name, the list shows a spinner and then that
   league's free agents (different rows, different drop lines). The position pill you had selected
   is kept.
9. After the switch, tap Add on a row (Sleeper league). Expected: the sheet names the NEW league
   and its roster/FAAB, not the old one.
10. Submit (or start) a claim in league A so the row reads "Claim pending"; switch to league B.
    Expected: no row in B reads "Claim pending" for that player. Switch back to A. Expected: it does.
11. Tap "See usage trends" after a switch. Expected: Usage Trends opens on the new league.
12. Tap back to the League tab. Expected: its top bar shows the league you switched to.
13. Tap the bell and the gear on the Free agents page. Expected: the notifications sheet opens /
    Settings pushes, as on the tab screens; back returns to Free agents.
14. The feedback button still floats bottom-right with no tab bar under it, and opens with
    "FreeAgents" as the screen.

### Sabotage table

Each row: the guarded line broken in place, the test run red, the file restored byte-for-byte, the
test run green, and the file's md5 compared before and after. Runner kept in the builder's scratch
directory (not committed).

| # | Sabotage | File | Sabotaged | Restored | md5 before = after |
|---|---|---|---|---|---|
| 1 | Rank over the FA pool only (rostered excluded from the board) | `backend/free_agent_service.py` | 6 tests red | green | same |
| 2 | Picks ranked (`is_pick_asset` dropped) | `backend/free_agent_service.py` | red | green | same |
| 3 | Rank by consensus seed, not the caller's board | `backend/free_agent_service.py` | red | green | same |
| 4 | Ties ordered by id, not pool order | `backend/free_agent_service.py` | red | green | same |
| 5–27 | Each of the 23 guard assertions 1a–6a, one mutation each (route name, component, `header`, back testID, back fallback, a native `headerLeft`, header function, TopBar import, TopBar render, back/title, title pass-through, cluster `onPress`, sheet `visible`, a second selector import, FAB `aboveTabBar`, top inset, league source, query key, effect deps, claim league record, sheet league gate, pending key, rank render) | `RootNav.tsx`, `TopBar.tsx`, `FreeAgentsScreen.tsx` | all red | all green | all same |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | `GET /api/league/free-agents` row: `pos_rank` is the overall rank at the position |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | no convention shifted; living-memory is the operator's to write (brief) |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | no module wiring changed |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | no architecture shift |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | `pos_rank` here is read by the mobile app only |
| `docs/glossary.md` (new domain term) | updated | "Free agent finder": `pos_rank` meaning |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a in this branch | the redefine-not-add choice is recorded above; DECISIONS.md is the operator's to write |

Also updated: `mobile/src/api/league.ts` contract comment, `backend/free_agent_service.py` module
header + docstring, `server.py` route docstring, `mobile/src/screens/CLAUDE.md` (FreeAgentsScreen
row), `mobile/src/components/CLAUDE.md` (TopBar row), `mobile/tests/README.md`.

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` — runs recorded in the
  hand-off report; CI on the pushed sha is the operator's.
- **Evidence recorded:** for the operator to log in `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist above, unrun.
- Express lane declared by the operator? no.

---

## Addendum 2026-11-12b — the league selector on four more pushed pages

**Entry point:** operator reply to the builder's list of league-scoped pushes without the
selector: "Yes add the selector to the recommended pages". **Builder:** branch
`feat/league-selector-pushed-pages`, stacked on `fbc8cdc2` (needs `LeagueTopBarHeader` from this
plan's branch). **Scope:** Standings, Usage Trends, Track record (`Receipts`) and Win Now. Not
changed, on purpose: League summary (legacy push), Draft room, Mock draft, Pick assignment, Record
picks, Shop asset (they take a league from route params, so a selector there needs a decision
first; D-249 consequence 5).

Same posture as the parent scope: no flag, no new analytics event (there is no league-switch event
anywhere; `TopBar` is reused unchanged), no schema, no route, no backend change.

### What changed, per screen

| Screen | Change (file:line) |
|---|---|
| all four | `RootNav.tsx` registrations now use `header: () => <LeagueTopBarHeader …/>` with the screen's existing title, literal back testID and `canGoBack ? goBack : navigate('Main')` fallback: WinNow `:886`, Standings `:948`, UsageTrends `:979`, Receipts `:1015`. The native `headerTitle` / `headerStyle` / `headerTintColor` / `headerBackVisible` / `headerLeft` options are gone because no native header renders under a custom `header` (the #151 / RNS#3294 workaround is preserved: the JS `HeaderBack` is the only back control). None of the four had modal presentation or gesture options. |
| header | `LeagueTopBarHeader` (`RootNav.tsx:291`) gains an optional `right` slot rendered after the centred title layer (`:312`, style `leagueSubHeaderRight :1356`), so it is tappable above it. |
| Usage Trends | The registration passes `right={options.headerRight?.({ canGoBack })}` (`RootNav.tsx:997`), so the screen's own `setOptions({ headerRight })` info button (`UsageTrendsScreen.tsx:232`, testID `usage-trends.info`) renders in the slot unchanged. League-switch fixes below. The league-name line above "Weeks 6–9" is removed (`UsageTrendsScreen.tsx` controls row, ~`:730`): the header's league cluster names the league directly above it. The weeks label and the Simple \| Raw stats pill stay. |
| Standings | `LeagueProjectionSection` is keyed by league (`StandingsScreen.tsx:204`). |
| Track record, Win Now | Registration only. |

### League-switch walk

What the header's switch changes: `useSession.league` (TopBar → `LeagueSwitcherSheet` →
`switchLeague`). Each screen reads it directly; none of the four takes a league route param
(`RootNav.tsx` param list: `WinNow: undefined`, `UsageTrends: { ownership? }`, `Standings:
{ segment? }`, `Receipts: undefined`), so there is no param/header conflict to resolve.

**Standings.** `leagueId` from the session (`StandingsScreen.tsx:50`); every query is keyed by it —
`['league-rosters', leagueId]` `:67`, `['league-users', leagueId]` `:73`, `['league-outlook',
leagueId, 'consensus']` `:81` — so a switch renders the new league's table (spinner while uncached).
The platform follows the switched league (`:54`), so switching to ESPN/MFL shows the honest
unavailable card / `OutlookUnsupportedRow`. The selected Current \| Projected segment is a lens and
stays; if Projected is selected, the new league's outlook loads (a Projected choice was made).
**Fixed:** under `league.projections` the Projected body is `LeagueProjectionSection`, whose
`ProjectionTables` holds `selected` (an expanded team row) as a roster id; Sleeper roster ids repeat
across leagues (1…N), so a switch would have opened the same-numbered team in the new league. It is
now keyed by league (`:204`), remounting on a switch. `standings_segment_changed` carries no
`league_id` (unchanged; it never did).

**Usage Trends.** `focusId` is the session league (`UsageTrendsScreen.tsx:163`) and keys the list
(`:172`). **Fixed:** the query used `placeholderData: keepPreviousData`, so after a switch the OLD
league's players, statuses and Add/Trade actions stayed on screen under the new league's name until
the fetch landed (and `statusIn(focus, …)` read the old league's rosters while `onAdd` targeted the
new `focusId`). The placeholder is now kept only when the previous query had the same league
(`:180`): week and period changes keep the list up as before; a league switch shows the spinner.
**Fixed:** league-bound local state is dropped on a switch (`:188–192`): the expanded Raw-stats row,
the availability sheet, and a claim opened in another league. A claim for the NEW league is kept,
because a cross-league Add (`doAdd`) switches first and then opens its sheet; a trade hand-off's
sheet that is mid-dismissal is left alone (`doTrade` awaits its dismissal promise). The list is
keyed by league (`:606`), so a switch to an already-cached league starts at the top. Kept, as the
user's choices: metric, ownership, position, unit, weeks, view, order, period, column sort.
Analytics: `usage_trends_view_changed` and `usage_trends_availability_opened` read `focusId`;
`usage_trends_action` reads the acted league — all current after a switch. Empty/error states for the
new league: flag off → `usage-trends.unavailable`; off-season → `usage-trends.off-season`; error →
`usage-trends.error` with retry; no matches → `usage-trends.empty` (all unchanged).

**Track record.** `leagueId` from the session (`ReceiptsScreen.tsx:200`) keys and fetches the one
payload (`:204`); no placeholder, so an uncached league shows the loading branch, then its own
ledger (a league with nothing tracked gets the designed "0 suggestions on record" ledger state, not
an error). The selected window chip (14/28/56) is a lens and stays. `receipts_opened` (`:222`) fires
again for the new league's resolved payload with its `league_id`; `receipts_window_changed` (`:236`)
reads the current `leagueId`.

**Win Now.** `WinNowScreen` renders `<WinNowContent key={`${userId}:${leagueId}`} />`
(`WinNowScreen.tsx:66`): a switch remounts the content, dropping baseline, results, editor,
evaluation, decisions, protected assets, budget/fairness inputs and the post-verify search, and
the unmount cleanups abort in-flight loads and searches (`:122`, `:127`). Flag off or no league →
`win-now.disabled`; an unsupported league → `win-now.unavailable`. Nothing to change.

### Safe area and FAB

All four already pad only the bottom (`edges={['bottom']}`) and mount their root-stack
`FeedbackFAB` (`aboveTabBar={false}`; three branch mounts on Track record, one on the others);
`TopBar` owns the top inset. Unchanged.

### Height on a 375×667 pt screen (iPhone SE: 20 pt status bar, 0 pt home indicator)

| | Before | After |
|---|---|---|
| Header | 64 (20 + 44 native bar) | 116 (20 + 52 `TOP_BAR_HEIGHT` + 44 sub-header) |
| Standings / Track record / Win Now body | 603 | 551 |
| Usage Trends fixed controls (8 top pad + 38 sub row + 8 + 46 metric + 8 + 44 ownership + 1 rule) | 153 | 153 |
| Usage Trends list area | 450 (67 %) | 398 (60 %) |

Removing the league-name line does not shorten the Usage Trends sub row at default text size: the
row is as tall as the 38 pt view pill, and the two text lines it held were 36 pt. It does at larger
Dynamic Type sizes. In Simple view the order and period pills (wrapped onto two lines on a 375 pt
phone, ~96 pt) are the list header and scroll away. **Flag:** 398 pt is tight but usable; not
restructured, per the brief.

### Evidence

- `mobile/tests/check-league-header-pages.js` (new, `npm run test:league-header-pages`): 43
  assertions — 1a–1e per screen (registration, `LeagueTopBarHeader` + title, literal back testID,
  fallback, no native `headerLeft`); 2a–2c the right slot and Usage Trends' info button; 3a–3b per
  screen (FAB count/props, bottom-only inset); 4a–4j + 4b2 the league-switch fixes and keys; 5a the removed
  league-name line.
- Updated to the new truth: `check-home-destinations.js` 5d (Standings registers through
  `LeagueTopBarHeader`, no `headerLeft`), `check-usage-trends.js` 2p2 (placeholder same-league
  only). `check-receipts.js`, `check-win-now.js`, `check-home-hub.js` pass unchanged.
- Sabotage: all 45 new or changed assertions (47 mutations; 4h three ways) broken in place, run red on that assertion, restored,
  run green, file hash equal before and after (table in the hand-off report; runner in the builder's
  scratch directory, not committed).
- Code walk: above.

### Docs

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route changed |
| `living-memory/LLD.md` / `HLD.md` / `DECISIONS.md` | n/a here | living-memory is the operator's to write (brief) |
| `docs/architecture.md` | n/a | no module wiring changed |
| `docs/cross-client-invariants.md` | n/a | nothing shared across clients |
| `docs/glossary.md` | n/a | no new term |
| `docs/plans/README.md` | updated | this plan's row |
| `mobile/src/screens/CLAUDE.md` | updated | Standings and Usage Trends rows; new Receipts and Win Now rows; the HeaderBack sharp edge |
| `mobile/src/navigation/CLAUDE.md` | updated | root pushes list; new "League selector as the header" bullet |
| `mobile/tests/README.md` | updated | the new suite; the Standings route and week-selection notes |

### TestFlight checklist (needs a build from this branch; have two leagues, one Sleeper)

**Standings**
1. Home → Standings. Expected: the same top bar as the tabs (league name, format tile, bell, gear),
   and under it a back chevron and "STANDINGS". Nothing under the status bar.
2. Back chevron → Home. Re-open; edge-swipe back → Home.
3. Tap the league name, pick the other league. Expected: the table reloads for that league (its
   team names); an ESPN/MFL league shows "ESPN standings coming".
4. Select Projected, then switch league. Expected: Projected stays selected and shows the new
   league's outlook. With batch projections on: expand a team row, switch league; expected: no row
   is expanded in the new league.

**Usage Trends**
5. Open from the Home hub's Usage Rates tile. Expected: top bar, then back chevron, "USAGE TRENDS"
   and the info (i) button at the right. Tap (i): the "How Usage Trends works" alert.
6. Under the header: "Weeks N–M" beside the Simple | Raw stats pill; no league-name line.
7. Scroll down the list, then switch league in the header. Expected: a spinner (not the old
   league's players), then the new league's list from the top. Your metric, ownership, filters and
   Simple/Raw choice are unchanged.
8. Raw stats: expand a row (chevron), switch league. Expected: no row is expanded after the switch.
9. Switch back to the first league (now cached). Expected: its list shows at once, from the top.
10. Change weeks in Filters (same league). Expected: the current list stays up while the new weeks
    load (unchanged behaviour).
11. Open a player's league pips, tap Add in the OTHER league (Sleeper). Expected: the app switches
    league (header name changes) and the claim sheet opens for that league — not dropped.
12. Same from Trade. Expected: switches league and lands in Find a Trade with that player pinned.
13. Free agents → "See usage trends". Expected: opens on Free agents ownership, same header.

**Track record**
14. Trades → Track record. Expected: top bar, back chevron, "TRACK RECORD".
15. Pick the 56D chip, switch league. Expected: the new league's ledger (spinner first if not
    loaded); the 56D chip stays selected.

**Win Now**
16. League summary or Trades → Win Now. Expected: top bar, back chevron, "WIN NOW".
17. Run a search (or tick a protected asset), then switch league. Expected: results, editor and
    protected chips are cleared; the new league's projections load.

**All four**
18. The feedback button floats bottom-right with no tab bar, and opens with the page's route name.
19. Bell and gear in the top bar open the inbox sheet / Settings; back returns to the page.
20. Back to the tabs after a switch: the tab top bar shows the league you switched to.
