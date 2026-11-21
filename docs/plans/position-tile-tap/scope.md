# Feature Scope — Home position tile opens your roster at that position

**Date:** 2026-11-15
**Entry point:** direct ask (operator): "I want to have the position tiles be clickable. When clicked, navigate users to the league summary page, filtered to their team's position that was clicked." Follow-ups the same day: the destination screenshot (own team drilled in, All, the one position chip, "Ranked by QB value only — chart reordered.", the user's QB rows on screen) and "Should still have a back button that goes back to the home page too."
**Builder:** builder subagent on `feat/position-tile-tap` (D-269)
**Amended 2026-11-19 (D-276, [home-return-unify](../home-return-unify/scope.md)):** with flags `nav.home_return` and `nav.home_return_unified` both on (both ship on), the header "Home" control described below is NOT drawn: the arrival arms the shared "‹ Home" bar under the top bar instead, which shows for the visit to League and, when tapped, closes this drill-in (same `home_back` exit) and returns Home. Everything below about the header control describes `nav.home_return_unified` OFF.
**Operator sign-off on waivers:** one waiver is surfaced below (§3, Android hardware back); the main session raises it.

---

## What the user sees

On the Home hub, tapping the BODY of a position tile (label, badge, rank, value, median, meter) opens the League tab's rankings with:

- basis Consensus, subset **All**, the position filter set to exactly that position (no Buy/Sell banner: this is not a split arrival);
- the user's **own team drilled in**: the header shows "‹ All teams" and the team name, the chart caption reads "Ranked by QB value only — chart reordered." with the user's bar highlighted, and the roster panel lists the user's players at that position;
- the page lands so those player rows are on screen with no scroll when the layout allows; otherwise it scrolls just enough that the roster ends on screen, never past the roster panel's top (its All / position controls and the position header stay visible);
- a **"Home"** control in the header's right side for this arrival only. One tap closes the drill-in and returns to the Home tab as the user left it. (With `nav.home_return_unified` on, D-276: the shared "‹ Home" bar instead, same result.)

Buy, Sell and "See P ranking" do exactly what they did. With the flag off the tile is exactly as before.

### Edge cases

| Case | Behaviour |
|---|---|
| User's team not in the rankings (no `is_you` row) or the rankings read failed | The filtered list at the top, no drill-in, no Home control, no crash |
| "No clear split" tile | The body tap works the same; "See P ranking" unchanged; the VoiceOver label states no rank (the tile shows none) |
| Tile loading (`split` null) | Body not pressable; skeletons as before |
| Two arrivals in a row (QB, then Home, then RB) | The second consume resets the filter; the filter auto-exit closes the QB drill-in first (`league_team_closed` via `filter_change`), then the RB arrival opens the own team again. If the user left via the Home control, the drill-in is already closed |
| Filter or subset change after arrival | As today: the auto-exit returns to all teams; the Home control goes with the drill-in |
| Leaving League (tab bar), "All teams", opening another team, League tab re-tap | The Home control goes away; coming back to League on one's own never shows it |

### Placement of the Home control, and why

Header RIGHT, home glyph + "Home", same construction and styles as the existing "‹ All teams" header control (`styles.headerBack` / `headerBackText`), static testID `league-summary.back-home`, label "Back to Home".

- The header LEFT is already the drill-in's own exit ("‹ All teams", #302, pinned); the operator asked to keep it.
- The title is the team name; two back controls on the left would squeeze it on a 375pt phone.
- The right side is empty on the League tab root, so nothing moves.
- A left chevron on the right edge would read oddly, so the control uses the `home` glyph that names its destination.

TabNav's shared `HeaderBack` is not reused as-is: it is `canGoBack ? goBack : navigate(fallback)` inside one stack, and this destination is another tab, so it would go to the wrong place. The control reuses the in-screen header back construction instead.

### Buy / Sell today

The existing Buy/Sell arrival from Home has **no** way back to Home: League rankings is the tab's stack root, the header has no left control outside a drill-in, and the iOS back swipe has nothing to pop. Not changed here (out of scope).

## 1. Analytics scope

- [x] **(a) New property and values on existing events** (no new event name):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `home_tile_tapped` | `tile: 'position_roster'`, `position` (QB\|RB\|WR\|TE), `band` (seller\|buyer\|mid, the user's band), **`split`** (shown\|no_split\|no_median — the tile's state; new prop, rides only on `position_roster`) | the tile body tap, before navigating | mobile |
  | `league_team_opened` | existing props; new `via` value **`home_tile`** | the own-team drill-in the arrival opens | mobile |
  | `league_team_closed` | existing props; new `via` value **`home_back`** | the header Home control | mobile |

  Nothing identifying (no league, team or player id). `home_tile_tapped` stays NON_INTENT; the two League events keep their classes. `split` registered in `backend/analytics_taxonomy.py` in the same commit; the ingest test in `test_analytics_taxonomy_home_hub.py` now posts a `position_roster` row with `split` and proves it lands.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New flag: **`nav.home_position_roster`** — code default False (`backend/feature_flags.py` `FLAG_KEYS`), shipped **true** in `config/features.json` (operator asked for the feature), mirrored true in `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`, compiled mobile default true (`useFeatureFlags.ts`, matches config). Not in `FTF_FLAGS`. Client-only. Off ⇒ `HomeHub` passes no `onOpen` and `PositionTile` renders the original tree. Rollback: false + `POST /api/feature-flags/reload`. `docs/config-reference.md` row added.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-position-tile-tap.js` (`npm run test:position-tile-tap`) — the intent kind; the tile body as a sibling pressable with static ids, the flag/loading gate, pressed `--ink-3`, the VoiceOver label executed for shown and no-split tiles; the hub's flag read and track → intent → navigate order; the consume (filter, no banner, no selection); the own-team open after data, after the filter auto-exit, via `openTeam('home_tile')`; no own team ⇒ list top; the landing offset executed for fits / small phone / long roster; the Home control's show rule, single setter, clears (drill-in end, blur), `closeTeam('home_back')` then Home, testID, label, construction, header-right placement; flag and taxonomy registration. Updated: `check-home-hub.js` 6b/6c (vocabulary + `split`), `check-league-rankings-playoff-tile.js` T4c (taxonomy row).
- [x] **Unit tests:** `backend/tests/test_home_position_roster_flag.py` (registration, false code default, true in config + three fixtures, League event prop rows unchanged); `test_analytics_taxonomy_home_hub.py` (exact prop row now with `split`, ingest round trip).
- [x] **Code-walk proof:** `HomeHub.onOpenRoster` → `requestLeagueSummaryRoster` → `navigate('League', {screen:'LeagueRankings'})`; on focus `LeagueSummaryScreen`'s consume re-arms `filterSigRef`, sets Consensus / All / {position}, clears the banner and queues `ownArrival`; next commit the filter auto-exit closes any open drill-in, then the own-open effect (declared after it) waits for `query.isFetched || isError`, finds `myEntry` (`is_you`) and calls `openTeam(id, 'home_tile', rank)` and `setHomeBackId(id)`; `applyOwnLanding` runs on the drill panel / list / page layout callbacks until a drag. The header effect renders `headerRight` while `showHomeBack`.
- [x] **Manual TestFlight checklist** (operator):
  1. Home → tap the QB tile's body (not Buy/Sell). League opens: header "‹ All teams" + your team name, "Home" on the right; ALL selected; only QB lit; caption "Ranked by QB value only — chart reordered."; your bar highlighted; your QB rows visible without scrolling (on a small phone, the QB section header and rows are visible).
  2. Tap "Home": you are on Home where you left it. Tap the League tab: the plain list, no "Home" control.
  3. Home → tap WR body, then Home, then TE body: TE filter, your TE rows, Home control present.
  4. From an arrival tap "All teams": the list, and the Home control is gone.
  5. From an arrival change the position or subset: back to all teams (as today), no Home control.
  6. Buy and Sell on a tile: unchanged (banner, list landing), no Home control.
  7. A "No clear split" tile: body tap opens your roster at that position; "See P ranking" unchanged.
  8. On a cold launch, tap a tile body while the tiles still show skeletons: nothing happens.
  9. VoiceOver: the tile body reads "Your QBs, 3rd of 12. Opens your roster in League rankings." and Buy / Sell are still separate stops.
  10. A league where your team is not valued: the body tap opens the filtered list with no drill-in.
- [ ] **WAIVED — Android hardware back and the iOS back swipe during the arrival:** the iOS swipe has nothing to act on (League rankings is the tab's stack root; the Home tab is a sibling tab, not a stack entry). Android back on this screen is deliberately unregistered (#302, operator 2026-08-11: iOS-only release, untestable on Android), and `check-league-drill-in.js` / `check-analytics-297-302.js` pin that absence. Adding a BackHandler here would overturn that decision, so it is left for the operator.
- `testID`s added: `home.position.qb.open`, `home.position.rb.open`, `home.position.wr.open`, `home.position.te.open`, `league-summary.back-home` (testid-lint OK).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route changed |
| `living-memory/LLD.md` | updated | Cross-tab arrival intents: the `roster` kind and "consume resets, open runs through the existing path" |
| `docs/architecture.md` | n/a | no module wiring or data flow change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant or enum across clients (analytics values live in the taxonomy) |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` | updated | D-269 |
| Also | updated | `docs/config-reference.md`, `docs/design/components.md` (position tile), `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`, `mobile/src/state/CLAUDE.md`, `mobile/tests/README.md` |

## 5. Ship gate declaration

- **CI green:** backend tests, `tsc --noEmit`, testid-lint — run locally on the branch (see TEST_LEDGER 2026-11-15).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-15 entry.
- **TestFlight verification:** checklist above, for the operator.
- Express lane declared by the operator? No (flag and analytics surfaces: full gates).
