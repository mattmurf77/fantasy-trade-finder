# Feature Scope — Home hub (Direction A: Trade market hero + position tiles + task grid)

**Date:** 2026-10-10
**Entry point:** direct ask (operator, via coordinator): "Home is bland; make it engaging, grounded in competitor research; surface trade opponents so users are pulled into League Summary's buyers/sellers split." Operator follow-up the same day: the FumbleAI Home hub is the intended reference; tiles, not text links.
**Builder:** design session 2026-10-10 (design only; no `mobile/` or `backend/` code). Research: [research.md](research.md). Mockup: [`mockups/home-engagement/index.html`](../../../mockups/home-engagement/index.html) §2 (Direction A), §6 (tap-through), §7 (states).
**Operator sign-off on waivers:** **pending.** No section below is waived. Four items need an explicit operator call before build (§0).

---

## 0. Operator calls needed before build

No template section is waived. These four items override an earlier written constraint or set a behaviour the operator should own:

| # | Item | Why it needs a call | Recommendation |
|---|---|---|---|
| W1 | **`docs/plans/home-tab/plan.md:59` ("No data fetching, no new state") and D-198's "No new analytics events" are overridden on the flag-on path.** | Both were true of the static Home and are written down. This design fetches one payload, holds a one-shot intent, and adds two events. | Accept. The flag-off path stays byte-identical, and `nav.home_tab` keeps its meaning. |
| W2 | **Arriving from Home resets League rankings to basis = consensus, subset = All, filter = {position}**, and closes any open drill-in. | League Summary's basis/subset are component state that survives tab switches. The Home claim ("4 teams are short at RB") is computed on consensus/All, so the screen must match it. That overwrites a user's My-board toggle. | Accept. The alternative is Home computing on whatever basis League Summary last used, which Home cannot see. |
| W3 | **The mockup's "before" pane is a labelled reconstruction, not a capture.** | `mockups/CLAUDE.md`'s embed rule is unsatisfiable (Home shipped 2026-10-08; `screens/` froze 2026-08-11 under D-056). The embed-vs-freeze conflict is a standing open operator question. | Accept under the interim posture. Only the real League Summary capture is embedded. |
| W4 | **The Seller/Buyer arithmetic is duplicated into a pure util rather than extracted from League Summary.** | `check-league-candidates-300.js` pins `cutAfter`/`bandFor` source text in `LeagueSummaryScreen.tsx`. Extracting would re-pin a shipped, guarded surface. Duplicating needs a parity guard. | Duplicate + parity guard for v1 (surgical). Extraction is a later cleanup with its own re-pin. |

---

## 1. Analytics scope

- [x] **(a) New events specced** (mobile only; web and the extension have no Home):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `home_viewed` | `state` ∈ `market \| mid_pack \| no_split \| thin_league \| no_league \| error`; `hero_position` ∈ `QB\|RB\|WR\|TE` or absent; `hero_side` ∈ `seller\|buyer` or absent; `team_count` (int); `platform` = the **league** platform (`sleeper\|espn\|mfl\|fleaflicker`, same meaning as on `league_view`) | Once per Home **focus**, after the power-rankings query settles (`isFetched`), or immediately for `no_league`. Deduped per focus in a ref, so a background refetch never mints a second row. Never fires on the flag-off path. | mobile |
  | `home_tile_tapped` | `tile` ∈ `market \| position \| rank \| trades \| matches \| league \| link_league \| retry`; `position` (only for `market`/`position`); `side` ∈ `seller\|buyer\|mid` (only for `market`/`position`: the user's band at that position) | On press of any Home hub tile, before navigation | mobile |

  **Classification: both go in `analytics_queries.NON_INTENT_EVENTS`, in the same commit that registers them.**
  - `home_viewed` is an impression, the `league_view` class.
  - `home_tile_tapped` is navigation, the `tab_selected` class. Home is the launch tab, so counting a tile tap as intent would turn every "open app, tap a tile, leave" into a user-day and step-change DAU on ship day, which is the seam `NON_INTENT_EVENTS` exists to prevent (`analytics_queries.py:63-75`).
  - The destination's own events carry intent: `league_team_opened`, `league_candidate_pinned`, `find_trades_tapped`, `match_opened`.

  **No prop is added to existing events.** Home→split attribution uses the session sequence: a `home_tile_tapped {tile ∈ market|position, position: P}` followed, in the same session, by `league_pos_candidates_viewed {position: P}` within 10 s. The envelope already carries a per-session `seq` (`mobile/src/api/events.ts`). This keeps the #300 exposure emitter, pinned by `check-analytics-300.js`, untouched. If the operator wants exact attribution instead, the alternative is an `entry ∈ pill|home` prop on `league_pos_candidates_viewed`, at the cost of re-pinning that guard.

  **Funnel this answers:**
  1. `home_viewed{state:market}`
  2. `home_tile_tapped{tile:market|position}`
  3. `league_pos_candidates_viewed{divider:shown}`
  4. `league_team_opened`
  5. `league_candidate_pinned`, the #300 conversion moment (unchanged)

  The question it answers: does Home move the share of active users who ever reach the split (today near zero, per the ask)?

  → **follow-through at build:**
  - A tracking-plan addendum at `docs/business/analytics/<build-date>-home-hub-addendum.md`. The taxonomy is default-deny ("New client event types require a tracking-plan addendum first", `analytics_taxonomy.py:8-10`).
  - Register both names in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` and classify them in `NON_INTENT_EVENTS`, in **one registration-only commit that lands before any emitter**, following the T1 precedent (`analytics_taxonomy.py`, P1 remediation block). An unregistered name or prop is counted and dropped behind a 200.
  - Nothing is stored beyond `user_events`, so there is no data-dictionary change.
- [ ] (b) Existing events cover it: no. `screen_viewed` / `tab_selected` cannot say which hero state was shown or which tile was tapped.
- [ ] (c) Waived

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** **`nav.home_hub`**, **default `false` (dark)**, client-only (no route reads it).
  - **Files:** `config/features.json` (+ `_comment_nav_home_hub`), `backend/feature_flags.py` `FLAG_KEYS` + `DEFAULT_FLAGS`, `backend/tests/fixtures/flags/*.json` (the mirror test), `docs/config-reference.md`. It does **not** go in `LAUNCHED_FLAG_DEFAULTS` (`mobile/src/state/useFeatureFlags.ts:45`), because absent ⇒ false is the intended cold-start value.
  - **Read:** imperatively, once per `HomeScreen` mount (`useState(() => !!useFeatureFlags.getState().flags['nav.home_hub'])`), so a mid-session revalidation never swaps Home's layout under the user. The `check-home-tab.js` precedent pins the same shape for `nav.home_tab`.
  - **Dependencies:**
    - `nav.home_tab` off ⇒ no Home at all; this flag is moot.
    - `nav.home_hub` on and `league.pos_candidates` off ⇒ header + live line + task grid only. The hero and position tiles promise a split that would not render.
    - `onboarding.trades_first` first-run carve-out (D-198) unchanged: first-run users never land on Home.
  - **Graduation criterion:**
    1. Lit after one operator TestFlight build passes the §3 checklist clean.
    2. Remove the flag after 30 days lit, provided:
       - `home_viewed{state:market}` → `league_pos_candidates_viewed` (session-sequence attributed) is non-zero and the operator accepts the rate;
       - the Acquire landing's own traffic shows no drop the operator attributes to Home.
- **New env vars / `model_config` keys:** none. **Rollback lever:** `nav.home_hub` → false + `POST /api/feature-flags/reload`; takes effect on each device's next Home mount. No deploy.
- **New client state (no schema):** `mobile/src/state/leagueSummaryIntent.ts`, a one-shot zustand store. It is the only cross-tab preselection contract, matching `useFinderTargets`' handoff pattern and FumbleAI's `env.selectedLens`.
  - **Shape:** `{ pending: { leagueId, position: 'QB'|'RB'|'WR'|'TE', seq } | null; set(); take() }`. Written only by `HomeScreen`; `take()`n only by `LeagueSummaryScreen` when `isTabRoot`.
  - **League switch:** a `leagueId` mismatch is discarded.
  - **Persistence:** never persisted, so a cold start never replays a stale intent.

## 3. Evidence scope

D-056: no Maestro, no simulator, no captures.

- [x] **Structural guard: new `mobile/tests/check-home-hub.js`** (`npm run test:home-hub`). Dependency-free text assertions over comment-stripped source. It pins:
  1. **Flag read.** `nav.home_hub` is read imperatively, once per mount, never via `useFlag`.
  2. **Flag-off parity.** The flag-off branch renders the existing `OPTIONS` table and the shipped heading byte-identically. `check-home-tab.js` must keep passing **unmodified**; it is the flag-off regression net.
  3. **Gating.** The hero and position tiles render only when `league.pos_candidates` is on.
  4. **No local arithmetic.** `HomeScreen.tsx` imports `utils/positionMarket` and contains no band/median arithmetic of its own (no `0.33`, no `medians[` indexing, no `.sort(` over teams).
  5. **Single writer.** `HomeScreen.tsx` is the only writer of `leagueSummaryIntent` (`git grep`-style scan of `src/`).
  6. **Consumer.** `LeagueSummaryScreen.tsx` consumes it only behind `isTabRoot`. The consume block sets exactly `setBasis('consensus')`, `setSubset('all')` and `setPosFilter(new Set([position]))`, and contains no second `track('league_pos_candidates_viewed'` call (one interaction, one event; the existing emitter fires on its own).
  7. **FAB.** No `FeedbackFAB` import in `HomeScreen.tsx` (#188, #196/#197).
  8. **Tokens.** No hex or `rgba(` literals in `HomeScreen.tsx`.
  9. **testIDs.** Every Home hub tile carries a static literal `testID` from the list below (testid-lint compatibility).
  10. **Analytics registration.** `home_viewed` and `home_tile_tapped` appear in `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` **and** in `backend/analytics_queries.py` `NON_INTENT_EVENTS`.
  11. **Tile targets.** Each task tile navigates by route name to `Rank` / `Trades` / `Matches` / `League`, the same targets `check-home-tab.js` pins for the text rows.
- [x] **Unit tests for the pure util: new `mobile/tests/check-position-market.js`** (`npm run test:position-market`). It transpiles `mobile/src/utils/positionMarket.ts` (zero runtime imports, per `mobile/src/CLAUDE.md` "Adding a feature" §4) and runs fixtures:
  - **Band sizes:** 12 teams (4/4/4), 10 (3/4/3), 14 (5/4/5), 8 (3/2/3).
  - **Median position:** an odd team count (the team on the median sits on the seller side, `>=`).
  - **Ties:** equal values break by `user_id` asc.
  - **Degenerate inputs:**
    - a flat league ⇒ `no_split`;
    - `medians` absent ⇒ `no_median`;
    - fewer than 3 teams ⇒ `thin_league`;
    - the user mid-pack everywhere ⇒ no hero;
    - no `is_you` team ⇒ no hero, no position tiles.
  - **Hero choice:** the largest `|you − median| / median` among banded positions, with the tie order QB, RB, WR, TE.
  - **Parity (W4):** reads `LeagueSummaryScreen.tsx` and asserts its `cutAfter` / `bandFor` / `ranked` sort still match the exact regexes `check-league-candidates-300.js` pins, **and** that the util's equivalents match the same shapes. Changing one side without the other fails.
- [x] **Backend pytest:** extend `backend/tests/test_analytics_p0.py` (the file that already asserts `CLIENT_EVENT_PROPS` per event) with:
  - `CLIENT_EVENT_PROPS["home_viewed"] == {"state","hero_position","hero_side","team_count","platform"}`
  - `CLIENT_EVENT_PROPS["home_tile_tapped"] == {"tile","position","side"}`
  - both names ∈ `NON_INTENT_EVENTS`
  - both names ∉ `SERVER_FIRED_EVENTS` (the import-time disjointness invariant already enforces this)
- [x] **Code-walk proof** (written at build into the TEST_LEDGER entry, file:line-cited). The trace:
  1. Hero `onPress` → `track('home_tile_tapped', …)` → `leagueSummaryIntent.set({leagueId, position:'RB', seq})` → `navigation.navigate('League', {screen:'LeagueRankings'})`.
  2. `LeagueSummaryScreen` focus effect (`isTabRoot`) → `take()` → `setBasis('consensus')`, `setSubset('all')`, `setPosFilter(new Set(['RB']))`.
  3. The existing `candidatePos` memo (`LeagueSummaryScreen.tsx:860-866`) resolves to RB.
  4. `medianAtPos` / `cutAfter` (`:875-892`) and `bandFor` (`:1027-1033`) compute.
  5. The divider renders (`:2214-2224`).
  6. The existing exposure effect (`:931-946`) fires `league_pos_candidates_viewed {position:'RB', divider:'shown'}`, and the existing drill-in auto-exit (`:1124-1136`) closes any open team via `closeTeam('filter_change')`.
  7. The scroll lands on the list.
  8. The proof must also show that Home's "4 teams" equals the number of `Buyer` badges rendered for the same payload: the same function, the same inputs.
- [x] **Manual TestFlight checklist** (operator; the only runtime evidence; run with `nav.home_hub` lit):
  1. **Returning user, Sleeper league, cold launch** → lands on Home.
     - The title reads "What would you like to do today?".
     - A one-line live summary sits under it.
     - Under YOUR LEAGUE there is a Trade market tile naming one position, a "You · Seller" or "You · Buyer" badge, a sentence with your rank and two `≈N firsts` values, a bar strip, and four team names.
  2. **Write down** the hero's position P, the count N in its headline, and the four names.
  3. **Tap the hero** → the League tab opens on League rankings with **only P selected** in the pills, **Consensus** basis, **All** subset, and the list in view.
     - Exactly N rows carry **Buyer** (if you're a Seller) or **Seller** (if you're a Buyer).
     - The four names from step 2 are among them.
     - Your row carries the same badge Home showed.
     - A "League median · ≈… firsts" divider sits in the list.
  4. **Tap a Buyer team** → the drill-in opens with "Tap a player to offer them to <team>." Tap one of your players → the Acquire tab opens scoped to that team with that player pinned. (This is the shipped #300 path, unchanged; it confirms Home reaches it.)
  5. **On League rankings, switch to My board and tap QB**, then go back to Home and tap the **RB position tile** → League rankings returns to **Consensus**, **RB only**. No drill-in is left open.
  6. **Position tiles:** each shows your rank "Nth /T" and either a Seller/Buyer badge or "Mid-pack". Tapping each lands on that position's split.
  7. **Task tiles:**
     - Rank → Rank tab.
     - Find a trade → Acquire.
     - Matches → Matches. Its badge number equals the "Mutual" segment count on the Matches tab.
     - League → League rankings with **no** position filter applied.
  8. **Exactly one feedback button** is visible on Home, and it covers no tile's text at the bottom of the scroll.
  9. **ESPN or MFL league** (switch via the TopBar): Home renders the Trade market tile with that league's teams and no error.
  10. **Airplane mode, pull to Home after a fresh league switch:** the YOUR LEAGUE section shows "Couldn't load rosters" with Try again. The four task tiles still work. Re-enable the network and tap Try again → the hero loads.
  11. **Largest Dynamic Type size:** the task grid collapses to one column, nothing is clipped, and every tile is still tappable.
  12. **Kill switch:** set `nav.home_hub` false, reload flags, relaunch → Home is the four plain text rows exactly as today.
  13. **Fresh install, first run:** sign in, pick a league → lands on **Acquire** with the analyst guide (not Home), as today (D-198).
- [ ] WAIVED: not waived.
- **`testID`s added** (static literals):
  - `home.hub`, `home.live-line`
  - `home.market`, `home.market.empty`, `home.market.retry`, `home.market.link-league`
  - `home.position.qb`, `home.position.rb`, `home.position.wr`, `home.position.te`
  - `home.tile.rank`, `home.tile.trades`, `home.tile.matches`, `home.tile.league`

  Unchanged on the flag-off path: `home.screen`, `home.option.rank|trades|matches|league`. All must pass `mobile/scripts/testid-lint.sh`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or contract-changed. Home reads `/api/league/power-rankings` (consensus), `/api/league/summary` and `/api/rankings/progress` exactly as documented. |
| `living-memory/LLD.md` | updated | New convention: **cross-tab preselection goes through a one-shot intent store, never route params** (`state/leagueSummaryIntent.ts`), mirroring `useFinderTargets`' handoff; plus the "Home claims must use the League Summary arithmetic" parity rule. |
| `docs/architecture.md` | n/a | No backend module or data flow changes. |
| `living-memory/HLD.md` | n/a | One screen re-composed from existing reads; no new module, client or major flow. |
| `docs/cross-client-invariants.md` | n/a | The band rule (`round(n·0.33)`, `>=` median) is mobile-only. Web has no position split and no Home. Parity is pinned mobile-side by `check-position-market.js`. |
| `docs/glossary.md` | updated | Add **Trade market (Home)**: the Home hero that surfaces one position's buyers/sellers split. Add **Buyer / Seller band**: the #300 term, absent from the glossary today. |
| ADR or `DECISIONS.md` entry | updated | New D-: the operator's direction pick (A/B/C) and W1–W4 as ruled. Narrows D-198's "No new analytics events" for the flag-on path. |
| `docs/config-reference.md` | updated | `nav.home_hub` row: default, read-once semantics, dependency on `league.pos_candidates`, rollback. |
| `docs/design/components.md` | updated | Four constructions, all built from existing primitives:<br>• **Trade market tile** (hero card + bar strip + brackets)<br>• **Position tile** (3px position rail, mono rank, neutral band badge)<br>• **Task tile** (MethodTile variant: 40pt ink-2 icon well, badge top-right, title + detail, min 124pt, 2 columns → 1 at accessibility sizes)<br>• **Live line** (Banner variant with flare count emphasis) |
| Tracking-plan addendum | updated | `docs/business/analytics/<build-date>-home-hub-addendum.md` (§1). |
| Mobile CLAUDE maps | updated | `mobile/src/screens/CLAUDE.md` (HomeScreen row), `mobile/src/state/CLAUDE.md` (new store), `mobile/src/utils/CLAUDE.md` (new util), `mobile/tests/README.md` (two new guards), `mobile/src/navigation/CLAUDE.md` (the Home bullet). |
| `docs/plans/README.md` | updated | Row for `home-engagement/`, added in this design commit. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (incl. the extended `test_analytics_p0.py`) + `mobile-typecheck` + `maestro-testid-lint`, all passing on the pushed sha. The two new guards and `check-home-tab.js` / `check-league-candidates-300.js` / `check-analytics-300.js` must pass. The latter two must pass **unmodified**: this design does not touch the #300 arithmetic or emitter.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guards run, the pytest result, and the code-walk proof from §3.
- **TestFlight verification:** the operator runs the §3 checklist on a build with `nav.home_hub` lit; the outcome is logged in TEST_LEDGER before the flag is lit for everyone.
- **Express lane declared by the operator?** No. Full gates. This change adds analytics events and a feature flag, which the bright-line rule says is never a quick fix.

---

## Appendix A — what Direction A renders (build reference)

Order on screen (mockup §2):

1. **Header.**
   - Subline `<your display name> · <rank>th of <n> overall`, from the `is_you` team's `rank` in the payload.
   - Title "What would you like to do today?": D-198 copy, Barlow Condensed, sentence case.
2. **Live line.** Banner construction; flare numerals. Order:
   1. the hero position's split;
   2. `matches_mutual` if > 0;
   3. otherwise the all-clear "Your board is live. Pick a position below to see who's short."
3. **YOUR LEAGUE → Trade market hero.** One `Pressable`; the whole tile is the button (no nested controls; `mockups/candidates-300-v2` VoiceOver finding). Copy by side:

   | Your band at P | Headline | Sentence | Names line | CTA |
   |---|---|---|---|---|
   | Seller | "N teams are short at P" | "You're Xth of T: ≈A firsts of P value against a league median of ≈M firsts." | "Shortest P rooms: …" (the bottom band, shortest first) | "See P buyers and sellers" |
   | Buyer | "You're Xth of T at P" | same sentence | "N teams are deep: …" (the top band, deepest first) | same |
   | none anywhere | "You're mid-pack at every position" | "No position puts you in the top or bottom N. Pick one to see who's short and who's deep." | none | none (position tiles are the doors) |

   - **Copy rules:**
     - "short" / "deep", never "wants" / "is shopping" (trade-quality research `:101`).
     - Values are always the server's `value_label` strings, never raw numbers (#277/#279).
     - The count is the band size, so it equals the badges League Summary renders.
   - **Bar strip:** bars sorted by P value, yours in the P position hex, the others ink-3, a dashed median line, and Sellers/Buyers brackets under the band columns. It is decorative; `accessibilityElementsHidden`, with the sentence carrying the meaning.
4. **Position tiles** (4 across). Each shows your rank `Xth /T`, then a neutral `Seller`/`Buyer` badge or "Mid-pack", or "No clear split" for `no_split`/`no_median`. Tap → that position's split.
5. **GET THINGS DONE → 2×2 task tiles.**

   | Tile | Detail | Badge | Tap |
   |---|---|---|---|
   | Rank players | from `/api/rankings/progress` | flare `n/4` only when not `unlocked` | Rank tab |
   | Find a trade | static detail | none | Acquire |
   | Matches | `N mutual · M awaiting them` | flare mono `matches_mutual` when > 0 | Matches |
   | League | static detail | `Xth` | League tab, no filter |

6. **States** (mockup §7):
   - **Loading:** static ink-2 skeleton; the task grid renders immediately.
   - **No league:** a setup card with "Link a league" → LeaguePicker.
   - **ESPN/MFL:** unchanged.
   - **Fewer than 3 valued teams:** "Not enough rosters yet".
   - **Mid-pack everywhere:** as in the copy table above.
   - **No split at a position:** that tile says so; if no position splits at all, YOUR LEAGUE collapses to one League rankings tile.
   - **Error:** "Couldn't load rosters" + Try again.
   - **`league.pos_candidates` off:** YOUR LEAGUE is absent.

**Network cost:** one new request, `GET /api/league/power-rankings?basis=consensus`, on the query key League Summary and the in-league calculator already share (`['league-power-rankings', leagueId, 'consensus']`, `staleTime` 60 s). `['league-summary', id]` (TopBar.tsx:175) and `['progress', id, format]` (RootNav.tsx:396-402) are already warm when Home mounts. No outlook request.

**Files touched at build (expected):**
- **New:**
  - `mobile/src/utils/positionMarket.ts`
  - `mobile/src/state/leagueSummaryIntent.ts`
  - `mobile/tests/check-home-hub.js`
  - `mobile/tests/check-position-market.js` (+ two `npm run` scripts)
- **Edited:**
  - `mobile/src/screens/HomeScreen.tsx` (flag-off branch unchanged)
  - `mobile/src/screens/LeagueSummaryScreen.tsx` (one focus effect + scroll-to-list; no change to the #300 code)
  - `backend/analytics_taxonomy.py`, `backend/analytics_queries.py`, `backend/feature_flags.py`, `config/features.json`, flag fixtures, `backend/tests/test_analytics_p0.py`
  - the docs in §4

## Appendix B — backend gaps (not in v1)

| Gap | Would enable | Where it would come from |
|---|---|---|
| Per-opponent window chip (Contender / Rebuilding) on power-rankings | A later "named buyers" line in the hero that says *why* a team trades (Direction C's team tiles) | `infer_team_outlook` already runs per member for cards (`trade_service.py:3999`, `:6495`) and Team Review (`team_review.py:448`); it would need serializing onto `/api/league/power-rankings` behind a flag |
| A cheap "deck ready · N ideas" read | A live badge on the Find a trade tile | No current endpoint; the pre-gen worker's job state is not exposed as a count |
