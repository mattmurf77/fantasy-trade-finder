# Feature Scope — Home hub (Direction D)

**Date:** 2026-10-10
**Entry point:** direct ask. The operator approved building Direction D as drawn in [`mockups/home-engagement/index.html`](../../../mockups/home-engagement/index.html) through `c330274b`, and shipping it to Render and TestFlight.
**Builder:** Phase 0+1 (this scope + foundations) on `feat/home-hub`. Phase 2 is two parallel mobile agents, **M-Home** and **M-Dest**, per the BUILD CONTRACT (§6).
**Operator sign-off on waivers:** **given 2026-10-10.** No section below is waived. Every operator call is recorded in §0.

Research: [research.md](research.md). Tracking plan: [`docs/business/analytics/2026-10-10-home-hub-addendum.md`](../../business/analytics/2026-10-10-home-hub-addendum.md).

---

## 0. Operator rulings (final)

| # | Ruling |
|---|---|
| R1 | **Scope:** build D as drawn through `c330274b`. |
| R2 | **Flag `nav.home_hub` ships ON.** Flag off ⇒ today's Home, byte-identical. |
| W1 | **Approved:** with the flag on, Home fetches data and emits new analytics events. This overrides `docs/plans/home-tab/plan.md:59` and D-198's "no new analytics events" on the flag-on path only. |
| W2 | **Approved:** arriving on League rankings from Home resets it to basis **Consensus**, subset **All**, filter = the position (or none), and closes any open drill-in. |
| W3 | The mockup's "before" pane is a labelled reconstruction (interim posture, `mockups/CLAUDE.md`). |
| W4 | **Approved:** the buyer/seller arithmetic is duplicated into `utils/positionSplit.ts`, with an executable parity guard (`check-position-split-parity.js`). League Summary's inline code is untouched. |
| R3 | Status rows are 40pt. The Buy/Sell banner ships, pinned. **Sell** lands at the **end** of the list, **Buy** at the **top of the list**. |
| R4 | Team outlook "View" opens the **Trade DNA sheet**. Home shows **current** standings only. |
| R5 | **`Standings` is a root-stack push.** Back returns to Home. It mounts its own `FeedbackFAB aboveTabBar={false}` and an explicit `HeaderBack` (RNS#3294). |
| R6 | League Summary's Season-outlook strip is **unchanged** in this build (follow-up F1). |
| R7 | **ESPN/MFL current standings are out of v1**, and so is any `/api/league/standings` endpoint (follow-up F2). **No route or API change in this build.** ESPN/MFL get the honest row and page states as drawn. Sleeper standings come client-side from cached rosters. |

**Follow-ups (logged, not in this build):**
- **F1:** League Summary's Season-outlook strip still runs `/api/league/outlook` on League-tab mount. Should it move to the Standings page?
- **F2:** `GET /api/league/standings` for ESPN (the importer already parses the record, `backend/espn_service.py:445-513`) and MFL (a new `leagueStandings` export read).
- **F3:** a per-opponent Contender/Rebuilding chip on power-rankings.

**One deviation from the brief, for the coordinator:** there is **no Trade DNA intent store**. `TradesScreen` already consumes a `editDna: true` route param that opens the Trade DNA sheet (`TradesScreen.tsx:1039-1045`). It is live because `trades.finder_hub` is on, and MatchesScreen already ships the same `navigate('Trades', {screen: 'TradesHome', params})` shape (`MatchesScreen.tsx:598-608`). A second mechanism would be a second source of truth. M-Home navigates with that param, and **TradesScreen is not touched**.

## 1. Analytics scope

- [x] **(a) New events specced.** Both are registered in Phase 1 in `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`) **and** classified in `backend/analytics_queries.NON_INTENT_EVENTS` in the **same commit**. Both are pinned by `backend/tests/test_analytics_taxonomy_home_hub.py`.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `home_tile_tapped` | `tile` (closed: `outlook` · `standings` · `overall_rank` · `buy` · `sell` · `position_ranking` · `find_trade` · `rank` · `matches` · `trends` · `free_agents` · `link_league` · `retry`). On `buy` / `sell` / `position_ranking` **only**: `position` (`QB\|RB\|WR\|TE`) and `band` (`seller\|buyer\|mid`, the user's own band at that position). | On press of any Home hub row, tile or button, **before** navigating. Screen `Home`. | mobile (M-Home) |
  | `standings_segment_changed` | `segment` (`current\|projected`, the segment the tap selected) | The user taps a segment **and it changes**. Never on mount, never on a re-tap of the active segment. Screen `Standings`. | mobile (M-Dest) |

  - **Why NON_INTENT.** Home is the launch tab, so counting a tile tap as intent would step-change DAU on ship day. The destinations' events carry intent. The segment switch is a lens change.
  - **Existing events reused, unchanged:**
    - `screen_viewed` (`Home`, `Standings`);
    - `tab_selected`;
    - `league_pos_candidates_viewed` (fires on its own when a Buy/Sell arrival applies the filter; **not** re-emitted);
    - `league_team_opened` / `league_candidate_pinned` (the conversion);
    - `league_team_closed{via: 'filter_change'}` (the W2 drill-in close rides the existing auto-exit).
  - **Attribution:** Home → split is measured by session sequence. No new prop goes on the #300 event.
  - **Follow-through:** the tracking-plan addendum is written (`docs/business/analytics/2026-10-10-home-hub-addendum.md`). Nothing new is stored beyond `user_events`, so there is no data-dictionary row.
- [ ] (b) Existing events cover it: no.
- [ ] (c) Waived: no.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** **`nav.home_hub`**, default **true** (R2), client-only (no route reads it).
  - **Registered in Phase 1:**
    - `config/features.json` (+ `_comment_nav_home_hub`);
    - `backend/feature_flags.py` `FLAG_KEYS` (code default False, as every key);
    - `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json` (the 3-touch mirror);
    - `mobile/src/state/useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS` (true, so a fresh install's first Home is the hub);
    - `docs/config-reference.md`.
  - **Read:** imperatively, once per `HomeScreen` mount (`useRef`, below). A mid-session revalidation never swaps Home under the user.
  - **Dependencies:**
    - `nav.home_tab` off ⇒ no Home, moot.
    - `league.pos_candidates` off ⇒ the position tiles are not rendered (the split they open wouldn't draw). The status rows and task tiles still render.
  - **Graduation:** remove the flag once one TestFlight build has run the §3 checklist clean and the operator confirms the hub stays.
- **New env vars / `model_config` keys:** none. **Rollback lever:** `nav.home_hub` → false + `POST /api/feature-flags/reload`; takes effect on the next Home mount, no deploy.
- **New client state:** `mobile/src/state/leagueSummaryIntent.ts`, a one-shot arrival intent (session-only, never persisted, cleared on league switch). Exact API in §6.
- **Wire type (no backend change):** `api/sleeper.ts` `RosterRow` gains optional `settings` (Sleeper's raw rosters already carry it through the proxy, `backend/server.py:21843-21845`).
- **Route/API changes:** **none** (R7).

## 3. Evidence scope

D-056: no Maestro, no simulator, no captures.

- [x] **Structural guards.**

  | Guard | Owner | Pins |
  |---|---|---|
  | `check-position-split-parity.js` | foundation, **done** (25 checks) | 16 named fixtures (4/4/4, 3/4/3, 5/4/5, 3/2/3, median-on-team ⇒ seller side, flat ⇒ no_split, no median ⇒ no_median, user_id tiebreak, canSplit, suggestedSide, ordinal…), plus **executable parity**: the guard extracts and runs LeagueSummaryScreen's own `computeSubset` / `activeTotal` / `ranked` / `cutAfter` / `bandSize` / `bandFor` beside the util over 16,000 randomised position views (1–32 teams). Sabotage-proven 3 ways: util `>=`→`>`, screen `idx < bandSize`→`<=`, screen `0.33`→`0.34`. |
  | `check-standings-order.js` | foundation, **done** (15 checks) | Win % (a tie counts half), then points for, then roster_id. `fpts + fpts_decimal/100`. The en-dash record. The you row. Before week 1 ⇒ `no_games`. No `settings` (ESPN/MFL) ⇒ `unavailable`. Zero runtime imports. `RosterRow.settings` declared. |
  | `check-home-hub.js` | **M-Home** | See §6 "M-Home guard must pin". |
  | `check-home-destinations.js` | **M-Dest** | See §6 "M-Dest guard must pin". |
  | `check-home-tab.js` | **must pass UNMODIFIED** | It is the flag-off regression net: the heading copy, the four OPTIONS rows, no FeedbackFAB, and no `useQuery\|useState\|useEffect\|fetch(` in `HomeScreen.tsx`. |
  | `check-league-candidates-300.js`, `check-analytics-300.js`, `check-analytics-297-302.js`, `check-guide-spotlight-tracking.js`, `check-session-seed.js`, `check-position-split-parity.js` | **must pass UNMODIFIED** | M-Dest edits LeagueSummaryScreen next to everything these pin. |

- [x] **Unit tests:** `backend/tests/test_analytics_taxonomy_home_hub.py` (6 tests). It covers allowlisted names, exact prop rows, no device-platform prop, NON_INTENT classification, no duplicate of the #300 events, and both names landing with every prop through `POST /api/events`.
- [x] **Code-walk proof** (written at ship into TEST_LEDGER, file:line-cited). It traces:
  1. Home Sell RB `onPress` → `track('home_tile_tapped', {tile: 'sell', position: 'RB', band: 'seller'}, 'Home')` → `requestLeagueSummarySplit(leagueId, 'RB', 'sell')` → `navigate('League', {screen: 'LeagueRankings'})`.
  2. LeagueSummaryScreen consume effect (`isTabRoot`, keyed on the intent `seq`) → `takeLeagueSummaryIntent(leagueId)` → `setBasis('consensus')`, `setSubset('all')`, `setPosFilter(new Set(['RB']))`.
  3. The existing auto-exit closes any drill-in (`via: 'filter_change'`).
  4. The existing `candidatePos` → `cutAfter` → `bandFor` → divider render → the existing `league_pos_candidates_viewed` emit. The pinned banner renders.
  5. `scrollToEnd()` after the filtered content settles.
  6. The same trace for Buy (`scrollTo({y: listTop})`) and Overall rank (`kind: 'all'`, no filter, no banner, top).
  7. Standings: `navigate('Standings')` → the Current table from seeded rosters (no request); Projected tap → `standings_segment_changed` → the outlook query enables.
  8. Team outlook → `navigate('Trades', {screen: 'TradesHome', params: {mode: 'guided', editDna: true}})` → `TradesScreen.tsx:1039-1045` opens the sheet.
  9. The proof states that Home's band for RB equals the band League rankings renders: both come from the same arithmetic, pinned by the parity guard.
- [x] **Manual TestFlight checklist** (operator; `nav.home_hub` on; the only runtime evidence):
  1. **Returning user, Sleeper league, cold launch** → Home. Top to bottom:
     - "What would you like to do today?";
     - three 40pt rows: **Team outlook**, **Standings** "W–L · Nth of N", **Overall rank** "Nth of N";
     - four position tiles QB/RB/WR/TE in a 2×2, each with a rank, your value vs the median, a meter, a badge (Seller / Buyer / Mid-pack), and **Buy** + **Sell** inside the tile;
     - five full-width task tiles: Find a trade, Rank players, View matches, Check trends, Search free agents.
     All three rows and all four tiles are visible without scrolling on a 6.1" phone.
  2. **Note** your band at RB on Home. Tap **RB → Sell** → the League tab opens on League rankings with **only RB** selected, **Consensus**, **All**, a pinned banner "Selling RB…", and the **end** of the list in view, shortest team last. Your row's badge equals Home's band.
  3. **Tap a team below the line** → the drill-in reads "Tap a player to offer them to <team>." Tap a player → Acquire opens scoped to that team with the player pinned.
  4. **Back on Home, tap RB → Buy** → League rankings at the **top of the list**, banner "Buying RB…". Tap a team above the line → "Tap a player to target them from <team>."
  5. **On League rankings, switch to My board, tap QB and open any team**, then go back to Home and tap **WR → Sell** → League rankings returns to **Consensus · All · WR**, no drill-in open, end of list.
  6. **Banner:** tap its close → it disappears. Tap another position pill → it does not come back. Leave the tab and return → no banner.
  7. **Overall rank → View** → League rankings, **no position filter**, no banner, top. Its rank equals the Overall rank row.
  8. **Standings → View** → the Standings page slides over Home (no tab bar), **Current** selected, a table with rank, team, W–L, PF and your row highlighted. Its place equals Home's row. Tap **Projected** → a spinner, then the Season-outlook list with Likely / Toss-up / Unlikely and **no percentages**. Tap **Back** → Home. Exactly one feedback button on the Standings page.
  9. **Team outlook → View** → the Acquire tab with the Trade DNA sheet open. Change the outlook, close the sheet, return to Home → the row shows the new outlook.
  10. **Task tiles:**
      - Find a trade → Acquire.
      - Rank players → Rank.
      - View matches → Matches. Its badge equals the Mutual count there.
      - Check trends → Trends.
      - Search free agents → Free agents (Back → Home).
  11. **ESPN or MFL league** (switch via the TopBar):
      - Standings row reads "Not available for ESPN yet" with no View.
      - Team outlook, Overall rank and the four tiles work.
      - Open Standings another way (deep link): Current shows the unavailable card, Projected shows "Season outlook needs schedule and scoring history — Sleeper leagues only for now."
  12. **Airplane mode, then switch league:**
      - The position grid shows "Couldn't load rosters" + Try again.
      - The status rows that can't load show Retry.
      - The task tiles still work.
      - Network back, Try again → recovers.
  13. **Largest Dynamic Type:** nothing clipped; the Buy/Sell buttons are still tappable and still inside their tiles.
  14. **Kill switch:** `nav.home_hub` false, reload flags, relaunch → Home is the four plain text rows exactly as today.
  15. **Fresh install, first run** → lands on Acquire with the guide (D-198), not Home.
- [ ] WAIVED: not waived.
- **`testID`s:** fixed in §6. All static literals, and all must pass `mobile/scripts/testid-lint.sh`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or contract-changed (R7). Home and Standings read existing routes as documented. |
| `living-memory/LLD.md` | updated at ship | Two conventions: cross-tab arrival goes through a one-shot intent store (`leagueSummaryIntent`); a duplicated arithmetic needs an executable parity guard (W4). |
| `docs/architecture.md` | n/a | No backend module or data-flow change. |
| `living-memory/HLD.md` | n/a | Two client screens recomposed from existing reads; no new module, client or flow. |
| `docs/cross-client-invariants.md` | n/a | The band rule and standings order are mobile-only. Web has no Home, no Standings and no position split. |
| `docs/glossary.md` | updated at ship | Add **Home hub**, **Buyer / Seller band** (the #300 term, never glossed) and **current vs projected standings**. |
| ADR or `DECISIONS.md` entry | updated at ship | New D-: Home hub (Direction D) with R1–R7 and W1–W4 as ruled; narrows D-198's "no new analytics events". |
| `docs/config-reference.md` | **updated (Phase 1)** | `nav.home_hub` row. |
| Tracking-plan addendum | **updated (Phase 1)** | `docs/business/analytics/2026-10-10-home-hub-addendum.md`. |
| `docs/design/components.md` | updated at ship | New constructions:<br>• Status row (40pt)<br>• Position tile with in-tile Buy/Sell (36pt visible / 44pt hit)<br>• Task tile (full-width 58pt)<br>• Pinned Buy/Sell banner (Banner construction)<br>• Standings table<br>• The Current/Projected segment (the Matches segment construction) |
| Mobile CLAUDE maps | updated at ship (integrator) | `mobile/src/screens/CLAUDE.md` (HomeScreen, StandingsScreen, LeagueSummaryScreen arrival), `mobile/src/navigation/CLAUDE.md` (Standings root push), `mobile/src/state/CLAUDE.md` (leagueSummaryIntent), `mobile/src/utils/CLAUDE.md` (positionSplit, standings), `mobile/src/components/CLAUDE.md` (`components/home/`, SeasonOutlook if extracted), `mobile/tests/README.md` (4 guards). |
| `docs/plans/README.md` | updated at ship | Flip the `home-engagement/` row to shipped. |

## 5. Ship gate declaration

- **CI green:**
  - `backend-tests`, incl. `test_analytics_taxonomy_home_hub.py` and the flag-mirror tests;
  - `mobile-typecheck` (tsc + every `tests/check-*.js`, incl. the four new guards and the six "unmodified" ones);
  - `maestro-testid-lint`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the guard counts, the pytest result, the parity sabotage names, and the §3 code-walk proof.
- **TestFlight verification:** the operator runs the §3 checklist; the outcome is logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. Full gates (flag + analytics events: bright line).

---

## 6. BUILD CONTRACT

Two parallel mobile agents, **disjoint file ownership**. Branch from `feat/home-hub` at the Phase 1 commit. **Foundation files are frozen.** If an agent needs a foundation change, it stops and asks; it does not edit.

### 6.1 Foundation (Phase 1, committed, FROZEN)

| File | What |
|---|---|
| `mobile/src/utils/positionSplit.ts` | Split arithmetic (W4 duplicate) |
| `mobile/src/utils/standings.ts` | Sleeper rosters → current standings |
| `mobile/src/state/leagueSummaryIntent.ts` | One-shot League-rankings arrival intent |
| `mobile/src/api/sleeper.ts` | `RosterRow.settings` (type only) |
| `mobile/src/state/useFeatureFlags.ts` | `'nav.home_hub': true` baked default |
| `mobile/tests/check-position-split-parity.js`, `mobile/tests/check-standings-order.js` | Foundation guards |
| `mobile/package.json` | Scripts `test:position-split-parity`, `test:standings-order`, **and pre-added** `test:home-hub`, `test:home-destinations` |
| `config/features.json`, `backend/feature_flags.py`, `backend/tests/fixtures/flags/*.json`, `docs/config-reference.md` | Flag |
| `backend/analytics_taxonomy.py`, `backend/analytics_queries.py`, `backend/tests/test_analytics_taxonomy_home_hub.py`, `docs/business/analytics/2026-10-10-home-hub-addendum.md` | Events |

**Exact APIs (verbatim).**

`mobile/src/utils/positionSplit.ts`:
```ts
export type SplitPos = 'QB' | 'RB' | 'WR' | 'TE';
export const SPLIT_POSITIONS: readonly SplitPos[] = ['QB', 'RB', 'WR', 'TE'];
export type Band = 'Seller' | 'Buyer';
export type SplitSide = 'buy' | 'sell';
export const MIN_SPLIT_TEAMS = 3;
export interface SplitTeamInput {
  user_id: string;
  username?: string;
  display_name?: string;
  is_you: boolean;
  positions?: Partial<Record<SplitPos, { value: number; value_label?: string }>>;
}
export interface SplitPayloadInput {
  teams: readonly SplitTeamInput[];
  medians?: Partial<Record<SplitPos, { value: number; value_label?: string }>>;
}
export interface SplitRow {
  userId: string; name: string; value: number; valueLabel?: string; isYou: boolean;
  rank: number;                 // 1-based under this position's ordering
  band: Band | null;
  aboveLine: boolean | null;    // null when no line is drawn
}
export type SplitState = 'shown' | 'no_median' | 'no_split';
export interface PositionSplit {
  position: SplitPos; state: SplitState; teamCount: number;
  median: { value: number; valueLabel?: string } | null;
  cutAfter: number | null; bandSize: number; rows: SplitRow[]; you: SplitRow | null;
}
export function teamName(t: SplitTeamInput): string;
export function positionValue(t: SplitTeamInput, pos: SplitPos): number;
export function rankByPosition<T extends SplitTeamInput>(teams: readonly T[], pos: SplitPos): T[];
export function cutAfterFor(values: readonly number[], median: number): number | null;
export function bandSizeFor(teamCount: number, cutAfter: number | null): number;
export function bandAt(idx: number, teamCount: number, bandSize: number): Band | null;
export function positionSplit(payload: SplitPayloadInput, pos: SplitPos): PositionSplit;
export function positionSplits(payload: SplitPayloadInput): PositionSplit[];   // QB, RB, WR, TE
export function canSplit(payload: SplitPayloadInput): boolean;                 // >= 3 teams && a median somewhere
export function suggestedSide(band: Band | null): SplitSide | null;            // Seller→'sell', Buyer→'buy'
export function rankPercentile(rank: number, teamCount: number): number;       // meter fill 0..1
export function ordinal(n: number): string;                                    // 1st 2nd 3rd 11th 21st
```
`PowerRankingsResponse` (`api/league.ts`) is structurally assignable to `SplitPayloadInput`; pass the query data straight in.

`mobile/src/utils/standings.ts`:
```ts
export interface SleeperRosterSettings {
  wins?: number | null; losses?: number | null; ties?: number | null;
  fpts?: number | null; fpts_decimal?: number | null;
}
export interface StandingsRosterInput { roster_id: number; owner_id: string | null; settings?: SleeperRosterSettings | null; }
export interface StandingsUserInput { user_id: string; display_name?: string | null; username?: string | null; }
export interface StandingsRow {
  rosterId: number; ownerId: string | null; name: string;
  wins: number; losses: number; ties: number; games: number; winPct: number; pointsFor: number;
  place: number;   // 1-based, unique
  isYou: boolean;
}
export interface CurrentStandings {
  rows: StandingsRow[]; teamCount: number;
  gamesPlayed: boolean;   // false ⇒ every record 0–0
  hasRecords: boolean;    // false ⇒ no `settings` at all (not a Sleeper payload)
  you: StandingsRow | null;
}
export function pointsFor(s: SleeperRosterSettings | null | undefined): number;
export function winPct(wins: number, losses: number, ties: number): number;
export function formatRecord(wins: number, losses: number, ties: number): string;  // "5–1", "5–1–1"
export function currentStandings(
  rosters: readonly StandingsRosterInput[],
  users: readonly StandingsUserInput[],
  myRosterId: number | null,
): CurrentStandings;
export type StandingsSummary =
  | { kind: 'record'; record: string; place: number; teamCount: number }
  | { kind: 'no_games' }
  | { kind: 'unavailable' };
export function standingsSummary(st: CurrentStandings): StandingsSummary;
```
`myRosterId = findMyRoster(rosters, user.user_id)?.roster_id ?? null` (`api/sleeper.ts`; that function owns the co-owner rule; never re-implement it).

`mobile/src/state/leagueSummaryIntent.ts`:
```ts
export type LeagueSummaryIntent =
  | { kind: 'split'; leagueId: string; position: SplitPos; side: SplitSide; seq: number }
  | { kind: 'all'; leagueId: string; seq: number };
export type LeagueSummaryIntentInput =
  | { kind: 'split'; leagueId: string; position: SplitPos; side: SplitSide }
  | { kind: 'all'; leagueId: string };
export const useLeagueSummaryIntent: UseBoundStore<StoreApi<{
  pending: LeagueSummaryIntent | null;
  set: (i: LeagueSummaryIntentInput) => void;
  take: (leagueId: string | null | undefined) => LeagueSummaryIntent | null;   // one-shot; clears always
  clear: () => void;
}>>;
export function requestLeagueSummarySplit(leagueId: string, position: SplitPos, side: SplitSide): void;
export function requestLeagueSummaryAll(leagueId: string): void;
export function takeLeagueSummaryIntent(leagueId: string | null | undefined): LeagueSummaryIntent | null;
```
How it behaves:
- **`seq`:** monotonic for the session, stamped by the store.
- **`take` for another league:** discards the intent.
- **League switch:** clears the pending intent (`useSession` subscription).
- **Persistence:** none.

### 6.2 Cross-agent interface (both sides code to this, neither changes it)

| From Home | Call |
|---|---|
| Position **Buy / Sell** | `track('home_tile_tapped', {tile, position, band}, 'Home')` → `requestLeagueSummarySplit(leagueId, pos, side)` → `navigation.navigate('League', { screen: 'LeagueRankings' })` |
| No-split **See P ranking** | same, `tile: 'position_ranking'`, side **`'buy'`** (lands at the list top; the screen draws no banner when the split state isn't `shown`) |
| **Overall rank** row | `requestLeagueSummaryAll(leagueId)` → `navigate('League', { screen: 'LeagueRankings' })` |
| **Standings** row | `navigation.navigate('Standings')`. Root-stack route **`Standings`**, no params, reads the session league. |
| **Team outlook** row | `navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true } })` (existing contract) |
| Find a trade / Rank / Matches | `navigate('Trades')` / `navigate('Rank')` / `navigate('Matches')` |
| Check trends | `navigation.navigate('Rank', { screen: 'Trends' })` |
| Search free agents | `navigation.navigate('FreeAgents')` |
| Link a league | `navigation.navigate('LeaguePicker')` |

**Query contracts.** Same keys as today, so caches are shared. Every Sleeper-roster consumer keeps `staleTime: 5 * 60_000` and the bare fetcher (the `check-session-seed.js` S-2 rule). Assert it in **your own** guard; do **not** edit `check-session-seed.js`.

| Data | Key | Fetcher | Options |
|---|---|---|---|
| Power rankings | `['league-power-rankings', leagueId, 'consensus']` | `getPowerRankings(leagueId, 'consensus')` | `staleTime: 60_000`, `placeholderData: (prev) => prev` |
| Preferences | `['league-prefs', leagueId]` | `getLeaguePreferences(leagueId)` | default |
| League summary | `['league-summary', leagueId]` | `getLeagueSummary(leagueId)` | as TopBar |
| Progress | `['progress', leagueId, activeFormat]` | `getProgress` | as RootNav (`activeFormat` = `useSession(s => s.activeFormat)`) |
| Sleeper rosters | `['league-rosters', leagueId]` | `getLeagueRosters(leagueId)` | `staleTime: 5 * 60_000`; **enabled only for Sleeper** |
| Sleeper users | `['league-users', leagueId]` | `getLeagueUsers(leagueId)` | `staleTime: 5 * 60_000`; **enabled only for Sleeper** |
| Outlook (Standings · Projected only) | `['league-outlook', leagueId, 'consensus']` | `getOutlook(leagueId, 'consensus')` | `enabled: segment === 'projected' && useFlag('outlook.odds') && isSleeper && !!leagueId`, `staleTime: 60_000` |

`isSleeper` uses the rule LeagueSummary uses (`LeagueSummaryScreen.tsx:558-562`): `(useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform) ?? 'sleeper') === 'sleeper'`. Unknown resolves to supported.

**Chalkline.**
- Tokens only.
- **Ice ≤ 3 on Home:** the suggested Buy/Sell side on banded positions (`suggestedSide(band)`) plus the active tab. Every other Buy/Sell is the Secondary button, and every "View" is chalk-dim.
- Seller/Buyer badges are the neutral Badge (never pos/neg).
- Buy/Sell buttons: 36pt visible, 44pt hit (`hitSlop` 4 vertical), entirely inside the tile.
- **The position tile is not itself pressable** (no nested controls).
- New text uses `components/chalkline/Text`.

### 6.3 M-Home — files it may touch (nothing else)

- `mobile/src/screens/HomeScreen.tsx`: **minimal change only.** `import { useRef } from 'react'`, then `const hubOn = useRef(!!useFeatureFlags.getState().flags['nav.home_hub']).current;`, then `if (hubOn) return <HomeHub />;` before today's JSX. (`nav.home_tab` needs no check here: with it off, TabNav never mounts HomeScreen.)
  - Today's `OPTIONS` table, heading and rows stay **byte-identical**.
  - **No `useQuery` / `useState` / `useEffect` / `fetch(` in this file.** `check-home-tab.js` §4h forbids them, and it must pass unmodified.
- `mobile/src/components/home/**` (new; e.g. `HomeHub.tsx`, `StatusRows.tsx`, `PositionTile.tsx`, `TaskTile.tsx`). All queries, state and analytics live here.
- `mobile/tests/check-home-hub.js` (new).

**M-Home testIDs:**
- `home.hub`
- `home.status.outlook`, `home.status.standings`, `home.status.rank`
- `home.position.<qb|rb|wr|te>`, `home.position.<pos>.buy`, `home.position.<pos>.sell`, `home.position.<pos>.ranking` (no-split)
- `home.tile.find-trade`, `home.tile.rank`, `home.tile.matches`, `home.tile.trends`, `home.tile.free-agents`
- `home.positions.error`, `home.positions.retry`, `home.link-league`

**Write them as static literals per position.** Template-literal ids need an entry in `scripts/testid-lint-allow.txt`, which is not in M-Home's file list.

**M-Home guard must pin:**
1. The flag is read once (`useRef`) and never via `useFlag`.
2. The flag-off body is byte-identical. `check-home-tab.js` still passes, and the guard re-asserts the OPTIONS literal is untouched.
3. `components/home/*` imports `positionSplit` / `standings` and contains **no** band or median arithmetic (`0.33`, `medians[`, `.sort(`, `>= median`).
4. The position tiles render only when `league.pos_candidates` is on and `canSplit`.
5. Buy/Sell call `requestLeagueSummarySplit` and navigate to `LeagueRankings`.
6. Exactly one `track('home_tile_tapped'` call site per tile kind, with the closed `tile` vocabulary, and `position`/`band` only on buy/sell/position_ranking.
7. The Standings row reads current standings only: no `getOutlook` / `league-outlook` anywhere under `components/home/`.
8. The roster/user queries use `staleTime: 5 * 60_000` and are Sleeper-gated.
9. No `FeedbackFAB` under `components/home/` or in HomeScreen.
10. No hex/`rgba(` literals.
11. Every listed testID is present.
12. The Team outlook row navigates with `editDna: true`.

### 6.4 M-Dest — files it may touch (nothing else)

**`mobile/src/screens/LeagueSummaryScreen.tsx`:** the arrival only.
- **Consume:** a `useFocusEffect` / effect keyed on `useLeagueSummaryIntent(s => s.pending?.seq)`, **tab root only** (`isTabRoot`). It calls `takeLeagueSummaryIntent(leagueId)` → `setBasis('consensus')`, `setSubset('all')`, `setPosFilter(new Set([position]))` (or `new Set()` for `kind: 'all'`).
- **Drill-in:** an open drill-in closes through the **existing** auto-exit / `closeTeam`, never a new `setSelectedId(null)` (the one-`setSelectedId(null)` sharp edge in `screens/CLAUDE.md`).
- **Pinned banner:** a new View **outside** the ScrollView, between header and page; `kind: 'split'` only, and only while that position's split state is `shown`. Copy as drawn:
  - Buying: "**Buying P.** Teams above the line are deepest at P. Tap one to target their players."
  - Selling: "**Selling P.** Teams below the line are shortest at P, shortest last. Tap one to offer them your players."
  - Close with a ghost ✕ icon button.
  - It clears on close, on any `posFilter`/`subset` change, and on blur.
- **Scroll:**
  - `sell` → `scrollRef.current?.scrollToEnd()` once the filtered content settles (next `onContentSizeChange`).
  - `buy` → `scrollTo({ y: listTop })` from one `onLayout` on the list container (`:2193`).
  - `kind: 'all'` → `scrollTo({ y: 0 })`.
- **Must not touch:** the inline `ranked` / `cutAfter` / `bandSize` / `bandFor` / exposure emitter (pinned by `check-league-candidates-300.js`, `check-analytics-300.js` and the parity guard).
- **Keep:** `notifyGuideTargetsMoved` wiring (`check-guide-spotlight-tracking.js` rule 12).

**`mobile/src/screens/StandingsScreen.tsx`** (new): root-stack push.
- `<FeedbackFAB activeScreen="Standings" aboveTabBar={false} />`.
- Current | Projected segment (the Matches segment construction), Current by default, local state.
- **Current:** the table from `currentStandings(...)` (columns `#` · Team · W–L(–T) · PF; you row ink-2 + ice numeral + ice "You" badge; caption "Week N · ordered by record, then points for" + the tiebreak note).
- **Non-Sleeper Current:** the unavailable card, copy as drawn.
- **Projected:** reuses the existing Season-outlook rendering. M-Dest **may extract** `SeasonOutlookSection` / `OutlookRow` / `OutlookUnsupportedRow` / `orderOutlookTeams` / `playoffBand` (and their styles) into `mobile/src/components/SeasonOutlook.tsx`, with LeagueSummaryScreen importing them back.
  - Testids must stay verbatim (`league-summary.odds.*`), so testid-lint still finds them.
  - **No guard pins these renderers today** (verified). The calibration rules must survive: no %, no title odds, records only when `!meta.beta`.
- **Analytics:** `standings_segment_changed` on a changing tap only.
- **testIDs:** `standings.screen`, `standings.segment.current`, `standings.segment.projected`, `standings.current.table`, `standings.current.unavailable`, `standings.back-btn`, plus the reused `league-summary.odds.*`.

**Other M-Dest files:**
- `mobile/src/components/SeasonOutlook.tsx` (new, only if extracting).
- `mobile/src/navigation/RootNav.tsx`: register `<Stack.Screen name="Standings">` **unconditionally**, FreeAgents-style options (`headerShown: true`, `HeaderTitle` "Standings", `headerBackVisible: false`, `headerLeft: HeaderBack testID="standings.back-btn"`, `canGoBack ? goBack : navigate('Main')`).
- `mobile/src/utils/deepLinks.ts`: add `Standings` at `app/league/standings`.
- `mobile/tests/check-home-destinations.js` (new).

**M-Dest guard must pin:**
1. The consume is tab-root only and one-shot (`takeLeagueSummaryIntent`).
2. It sets consensus / all / filter, with no new `setSelectedId(null)`.
3. The banner is outside the ScrollView, `split` only, and clears on filter change.
4. `scrollToEnd` for sell; `listTop` for buy.
5. The Standings route is registered unconditionally in RootNav with `HeaderBack` and the screen mounts exactly one `FeedbackFAB` with `aboveTabBar={false}`.
6. The outlook query is `enabled` only on `projected`.
7. `standings_segment_changed` sits in a tap handler, never an effect.
8. The deep link exists.
9. The Season-outlook calibration rules hold wherever the renderer now lives (no `%`, no `title_pct`, `showRecords = !meta.beta`).
10. Roster/user queries use `staleTime: 5 * 60_000` and are Sleeper-gated.

**M-Dest does NOT touch:** `TradesScreen.tsx` (the `editDna` param already works), `TabNav.tsx`, anything under `components/home/`, `HomeScreen.tsx`.

### 6.5 Neither agent touches

The foundation files (§6.1), `check-home-tab.js`, `check-league-candidates-300.js`, `check-analytics-300.js`, `check-analytics-297-302.js`, `check-guide-spotlight-tracking.js`, `check-session-seed.js`, `scripts/testid-lint-allow.txt`, `mobile/package.json`, anything under `backend/`, `config/`, `docs/`, `living-memory/` or `mockups/`. Docs, LLD, DECISIONS and TEST_LEDGER are the integrator's at ship (§4).

### 6.6 Per-agent exit gate

`cd mobile && npx tsc --noEmit` clean. Your new guard, plus every guard in §3 "must pass UNMODIFIED", plus `node tests/check-position-split-parity.js` and `check-standings-order.js`. `bash scripts/testid-lint.sh` OK. One commit on your branch; no push.
