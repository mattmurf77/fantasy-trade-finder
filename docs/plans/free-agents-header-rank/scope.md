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
