# Feature Scope — One Home control after a Home tile tap

**Date:** 2026-11-19
**Entry point:** direct ask (operator, through the main session): one "back to Home" control that looks and behaves the same everywhere, replacing the two kinds that exist today: D-275's "‹ Home" bar (`nav.home_return`) and D-269's header "Home" control in League rankings (`nav.home_position_roster`).
**Builder:** builder subagent on `feat/home-return-unify` (D-276)
**Operator sign-off on waivers:** GIVEN 2026-11-21. The operator answered "Yes, sign off" to the main session's question naming the analytics waiver (§1 (c)) and the missing feature-scope block for the D-277 bug fix shipped in the same PR (#708). The Android back item (§3) is carried over from D-269 and D-275, not a new waiver.

---

## What the user sees

New client flag **`nav.home_return_unified`**. Unified mode is on only when **both** `nav.home_return` and `nav.home_return_unified` are on.

| | Unified (both flags on, the shipped values) | Either flag off (today on main) |
|---|---|---|
| Position tile **body** tap on Home | League rankings, your team open at that position, with the **"‹ Home" bar** under the top bar, like every other tile that crosses tabs | League rankings, your team open, with the **header "Home" control** on the right (D-269) |
| Header "Home" control in League rankings | never drawn | drawn for that drill-in only (D-269 rule) |
| Tap "‹ Home" | the drill-in that arrival opened is closed if it is still the open one (`league_team_closed` via `home_back`, once), then the Home tab, as you left it | (no bar for this arrival) |
| How long the control shows | the bar's rule: for the visit to League (opening another team, "All teams" or a filter change keep it; leaving the tab another way ends it) | D-269's rule: only while that team is open |
| Other tiles (Team outlook, Review outlook, Overall rank, Buy, Sell, See P ranking, Find a trade, View matches) | unchanged ("‹ Home") | unchanged ("‹ Home" while `nav.home_return` is on) |
| Rank players, Check trends (rank pages) | no "‹ Home" (2026-08-16 one-exit ruling) | no "‹ Home" |

So in unified mode every Home tile that crosses tabs shows the same control: "‹ Home", chevron and word, under the top bar, VoiceOver "Back to Home", testID `home-return.back`.

### Mechanism

- **Decision in the pure module** `mobile/src/navigation/navContinuity.ts` (import-free, executed by `check-nav-continuity.js`): `homeReturnUnifiedOn(homeReturnOn, unifiedOn)`; `homeReturnTabFor(tap, unified)` returns League for `position_roster` only when unified; `rosterHeaderHomeVisible(isTabRoot, arrivalTeamId, selectedTeamId, unified)` is D-269's rule with `!unified` in front; `rosterClosesOnHomeReturn(unified, signal, isTabRoot, arrivalTeamId, selectedTeamId)` decides the close; `homeReturnSignal(prev, armedTab)` builds the tap signal.
- **A one-shot signal in the `homeReturn` store**: `returned: {seq, tab}`. The bar's tap calls `requestReturn()` (a new `seq`, naming the armed tab) and then navigates to Home. The bar knows nothing about League rankings.
- **League rankings listens** with `useHomeReturn.subscribe` (tab root only, and only subscribed in unified mode). zustand calls listeners synchronously inside `set`, so the close happens inside the bar's `onPress`, before its `navigate`: the same order as D-269's `backToHome` (`closeTeam('home_back')`, then Home). `closeTeam` is the screen's one exit path, so `league_team_closed {via: 'home_back'}` fires once (`emitTeamClosed` clears `focusRef`).
- The arrival's team id (`homeBackId`) keeps D-269's lifecycle (set at the own-team open, cleared when another team / no team is open, cleared on blur). In unified mode it only decides what the bar's tap closes; it no longer decides what is shown.

## What is not built, and why

| Item | Why |
|---|---|
| "‹ Home" on Rank players / Check trends | Rank pages keep their one exit (2026-08-16 ruling); the brief says leave them as they are |
| A new analytics event for the "‹ Home" tap | The brief: keep the existing event and reason, add none (see §1) |
| Closing a drill-in the user opened themselves on the bar's tap | Not D-269's behaviour: its control existed only for the arrival's own drill-in. Another open team is left as it is, as a tab-bar tap would leave it |
| Removing D-269's header control code | It is the flag-off branch; graduation removes it after a TestFlight cycle |
| Android hardware back for "‹ Home" | iOS-only release (same as D-269 and D-275) |
| `nav.home_return_unified` without `nav.home_return` | Does nothing on its own by design: the bar it relies on is `nav.home_return`'s |

## 1. Analytics scope

- [ ] (a) New events specced — none.
- [x] **(b) Existing events cover it:** `home_tile_tapped {tile: 'position_roster', …}` (unchanged), `league_team_opened {via: 'home_tile'}` (unchanged), `league_team_closed {via: 'home_back'}` (same value, now emitted by the bar's tap in unified mode instead of the header control; exactly one of the two emitters exists per flag state), `screen_viewed` Home with `prev_screen` LeagueRankings.
- [x] **(c) WAIVED, operator sign-off 2026-11-21 ("Yes, sign off"):** no way to tell, from `league_team_closed {via: 'home_back'}` alone, whether the tap was on the header control (flag off) or on the bar (unified). Rationale: the brief says keep the existing event and reason and add none; the flag state at the time separates the two. If the operator wants it split, the follow-up is a new `via` value registered in `analytics_taxonomy.py` in the same commit.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New flag: **`nav.home_return_unified`**, client-only, no route reads it. Code default False (`backend/feature_flags.py` `FLAG_KEYS`), shipped **true** in `config/features.json` (with `_comment_nav_home_return_unified`), mirrored true in the `release`, `onboarding-v2`, `profiles-on` fixtures, compiled client default true in `mobile/src/state/useFeatureFlags.ts` (same as config, so the first paint agrees with the fetched map). Not in `FTF_FLAGS`. Documented in `docs/config-reference.md`. Graduation: after one TestFlight cycle with the checklist below passed, remove D-269's header control and the flag.
- Rollback lever (deploy-free): `nav.home_return_unified` false + `POST /api/feature-flags/reload`; applies at the next flag revalidate. Both LeagueSummaryScreen and HomeHub read it live through `useFlag`.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-nav-continuity.js`, now **149 assertions** (was 111 on main). New: A1d-A1f (the flag key, unified only with both flags, exactly one tap changes), A2m-A2t (the real store: the roster arrival arms League only when unified, lasts for the visit, the tap signal is one per tap and names the tab), A6a-A6l (the header-control rule executed in both flag states over every combination, the close rule's seven cases, and the tap → one `home_back` → Home sequence driven through the real store), B1a/B1b/B1c/B1f updated and B1k/B1l added (the bar signals before it navigates and holds no League knowledge), B9a-B9g (League rankings' call site), C1-C4 for the new flag.
- [x] `mobile/tests/check-position-tile-tap.js` **56 assertions** (was 54): 7a now pins `showHomeBack` to `rosterHeaderHomeVisible(…, homeReturnUnified)`; 7a2 executes it with unified off against D-269's exact rule; 7a3 executes it with unified on (never shown).
- [x] **Sabotage runs** (each made red, then restored, all green after): roster tap arms the bar with unified off (B1f red); header control shown in unified mode (A6b, 7a3 red); unified roster tap arms nothing (A1f, A2n-A2p, A6j, A6k, B1c red); the bar signals after navigating (B1k red); the listener without the new-signal check (B9d red).
- [x] **Unit tests:** `backend/tests/test_home_return_unified_flag.py` (registration with False code default, true in config with its comment and in three fixtures alongside `nav.home_return`, not env-forced, client default matches).
- [x] **Code-walk proof:** below.
- [x] **Manual TestFlight checklist:** below.
- `testID`s added: none (`home-return.back` and `league-summary.back-home` unchanged).

### Code-walk proof

1. **Arm.** `HomeHub.tsx:107` `homeReturnUnified = homeReturnUnifiedOn(homeReturnOn, unifiedOn)`; `:109` every arm passes it to the store; `:237` the body tap arms `position_roster` only when unified, after its `track` and before the roster intent and navigate. `navContinuity.ts:62-65` maps it to League only when unified. Off: no arm call at all, as on main.
2. **Show.** `TabNav.tsx:857` reports the League focus; the bar shows on League for the visit (`navContinuity.homeReturnVisible`, unchanged). `LeagueSummaryScreen.tsx:1485-1489` `showHomeBack = rosterHeaderHomeVisible(…, homeReturnUnified)`, false whenever unified, so the header-right branch renders nothing.
3. **Tap.** `HomeReturnBar.tsx:38` `requestReturn()` → `homeReturn.ts` `set({returned: homeReturnSignal(prev, tab)})`. zustand 5.0.12 `vanilla.js:6-11` runs every listener synchronously inside `setState`, so `LeagueSummaryScreen.tsx:1501-1508`'s listener runs before `HomeReturnBar.tsx:39`'s navigate: a new `seq`, then `rosterClosesOnHomeReturn` → `closeTeam('home_back')` (`:494`), whose `emitTeamClosed` tracks once and clears `focusRef` (`:482`). Then the Home focus disarms the bar; the blur cleanup clears `homeBackId` (`:1348`) as before.
4. **Either flag off.** `LeagueSummaryScreen.tsx:1501` returns before subscribing; the bar's signal changes a store field nothing reads; `rosterHeaderHomeVisible(…, false)` equals D-269's expression (executed, A6a / 7a2).

### Manual TestFlight checklist (operator)

Setup: a TestFlight build with this branch. "Unified off" = `nav.home_return_unified` false in `config/features.json` on the server + `POST /api/feature-flags/reload`, then pull to refresh or relaunch.

**Unified (shipped values)**

1. Home → tap the QB tile's **body**. Expect: League rankings with your team open at QB, "‹ All teams" on the header's left, **no** "Home" on the header's right, and the "‹ Home" bar under the top bar (same look as after Overall rank).
2. Tap "‹ Home". Expect: Home as you left it. Then tap the League tab: the plain list (your team NOT still open), no "‹ Home" bar.
3. Home → RB body → tap "All teams" → the bar is still there → tap "‹ Home". Expect: Home. League tab: plain list.
4. Home → WR body → "All teams" → open another team from the list → "‹ Home". Expect: Home; League tab shows that other team as you left it (only the arrival's own drill-in is closed).
5. Home → TE body → tap the Matches tab, then the League tab. Expect: no "‹ Home" (the visit ended).
6. Home → Overall rank, Buy, Sell, See P ranking, Team outlook, Find a trade, View matches: "‹ Home" each time, same look as step 1.
7. Home → Rank players and → Check trends: NO "‹ Home".
8. (optional, analytics) After step 2, the events show one `league_team_closed` with `via: home_back` for the tap.

**Unified off (or `nav.home_return` off)**

9. Home → a position tile body. Expect: the header "Home" on the right, NO "‹ Home" bar; tapping it closes the team and returns Home (D-269 exactly).
10. With `nav.home_return` off too: no "‹ Home" anywhere; the position tile body still shows D-269's header "Home".

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted; the navigation conventions live in `mobile/src/navigation/CLAUDE.md` (updated) |
| `docs/architecture.md` | n/a | no backend wiring or data flow changed |
| `living-memory/HLD.md` | n/a | no new module, client or major flow |
| `docs/cross-client-invariants.md` | n/a | mobile-only navigation |
| `docs/glossary.md` | n/a | no new domain term |
| `DECISIONS.md` | updated | D-276 |
| Also | updated | `docs/config-reference.md` (new row, `nav.home_return` row), `docs/design/components.md` (position tile), `docs/plans/nav-continuity/scope.md` and `docs/plans/position-tile-tap/scope.md` (amendment notes, flag-off wording), `mobile/src/navigation/CLAUDE.md` + `README.md`, `mobile/src/state/CLAUDE.md`, `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`, `mobile/tests/README.md` |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha (main session pushes).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-19 entry.
- **TestFlight verification:** the checklist above, by the operator; outcome to TEST_LEDGER.
- Express lane declared by the operator? No (flag surface: full gates).
