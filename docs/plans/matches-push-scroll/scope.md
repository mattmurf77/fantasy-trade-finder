# Feature Scope — Matches push arrival: scroll to the card and mark it (R2)

**Date:** 2026-10-31
**Entry point:** direct ask: head-eng's 11-06 bug-fix call on ux-lead's finding R2 (head-product ruled it into Update 1's scope on 2026-11-01, then pulled it forward as a bug fix). The spec is `docs/plans/action-banner/ux-states.md` §7 (draft 1.2) plus design-lead's mark spec. Both live on the org-bringup branch, not on `main` yet.
**Builder:** eng-mobile worker for engagement-eng (branch `fix/matches-push-scroll`)
**Operator sign-off on waivers:** not needed. The waivers below are "n/a" rows; none touches a gate the operator owns.

---

## The bug

A push tap on "@Alex accepted your trade" opens the Matches list, not that trade. `RootNav.tsx:367-371` sends every
match push through `utils/deepLinks.ts:360` `routeNotificationTap`, which passes `{ match_id, src: 'push', ts }` into
Matches (`:366` on the v2 path route, `:374` on the imperative fallback). But `MatchesScreen` read `route.params` only
for `guidedArrival`, `segment` and `leagueId`. Nothing read `match_id`. Every card also reads "New match with @…",
whatever state it's in (§7 R9), so a mark is the only thing that can say which card the push meant.

## Segment finding

**Every `match_id` is in the Mutual segment.**
- `match_accepted` is pushed with `data.match_id` (`backend/server.py:26072-26078`). It resolves to Matches with that id
  (`deepLinks.ts:287`, `:335-337`).
- The id is a `trade_matches` row. `GET /api/trades/matches/all` returns every row the user is party to, in every
  status (`server.py:25298-25306`, `database.py:11191`).
- That query (`MatchesScreen.tsx:308`) feeds only the Mutual FlatList: `visibleMatches` at `:761`, rendered at `:1486-1488`
  with key `match_id`.
- Awaiting rows have no `match_id`: they're keyed `league_id:trade_id`. Standing holds offers.
- So the effect switches the segment to Mutual and never looks anywhere else.

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED. No analytics are needed for a bug fix** (ux-states §7 "Analytics"; head-eng's addendum item 8).
  An outcome event (found, not found or error) would need analytics-lead's grant, taxonomy registration and
  `NON_INTENT` classification in the emitter's commit. The guard pins that the arrival block calls no `track(` (P-19a).

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. Arrival only fires when route params carry a `match_id`, which today only
  `notif.tap_routing_v2` (ON) produces. With that flag off, the legacy tap drops `match_id` (`RootNav.tsx:373-379`), so
  nothing changes.
- New env vars / `model_config` keys: none. The not-found line is the code constant `MATCH_NOT_FOUND_LINE`
  (`utils/matchesDerive.ts:92`), shipped `null`.

## 3. Evidence scope

**Maestro delta / simulator-gate tier: dead sections (D-056).** No flows and no captures.

- [x] **Structural guard:** `mobile/tests/check-matches-push-scroll.js` (`npm run test:matches-push-scroll`), 60 checks.
  - **Executed:** `indexForMatch`, `notFoundToast` (null → no line; a string → exactly that string, 4 s), and the shipped
    `MATCH_NOT_FOUND_LINE === null`.
  - **Structural pins:**
    - reads `match_id` and `ts`, with ts dedupe;
    - lands on Mutual before the wait;
    - waits for the list, then refetches once;
    - the not-found and error branches;
    - the chip goes to All only when it hides the row;
    - `scrollToIndex` with `viewPosition 0`;
    - `onScrollToIndexFailed` jumps to the estimate, then retries once;
    - the drag guard;
    - momentum-settle, plus a fallback;
    - the overlay props, `ARRIVAL_MARK`'s values, and 2000 ms then 120 ms ease-out on the native driver;
    - Reduce Motion;
    - keyed on `ts`;
    - timers cleared on unmount and when the row goes;
    - VoiceOver focus;
    - no analytics and no API call;
    - the producer contract in `deepLinks.ts` and `RootNav.tsx`.
  - **G-035 label:** it proves the wiring, not runtime behavior.
  - **Sabotage:** 21 mutants, each run once, all RED. Files restored byte-identical (sha-checked).
- [x] **Unit tests:** no backend change, so no pytest.
- [x] **Code-walk proof:** below.
- [x] **Manual TestFlight checklist:** below. This is the only runtime evidence.
- `testID`s added/renamed: none (`testid-lint` OK).

### Code-walk (paths under `mobile/src/`)

**Push tap → param**
- `hooks/usePushNotifications.ts:179-180` decodes `data.type` through `resolveNotificationTarget` (`utils/deepLinks.ts:337`)
  and gets `{ tab:'Matches', matchId }`.
- `navigation/RootNav.tsx:370` calls `routeNotificationTap`.
- With `ux.deeplink_router_v2` on, `utils/deepLinks.ts:366` routes `app/matches/<id>?src=push&ts=<now>`. The path route
  `matches/:match_id?` (`:201`) turns that into params `{ match_id, src, ts }`, with `ts` as a string. The fallback at
  `:374` passes a numeric `ts`.

**Param → effect (`screens/MatchesScreen.tsx`)**
- `:801-803` reads `match_id` and `ts` as strings.
- The effect at `:893` waits for `isFocused` and returns at `:894` if this `ts` is already done.
- New arrival: `:904` switches to Mutual at once (§7 step 1).
- `:907` waits while the first fetch or a refetch runs (step 2).
- `:913` looks the id up in `hiddenAwareMatches` (every league, minus pending dismisses).
- Missing: `:921` refetches once, unless paused offline. The effect runs again when `isFetching` drops.
- Found: `:942` sets the chip to All, but only when `visibleMatches` lacks the row (step 3).
- The effect waits for the Mutual list to render, then sets `markRef` and `mark` to pending.

**Effect → row visible → marked**
- `:954`: if the user dragged during the wait, or the row is already fully on screen (100% viewability config,
  `onViewableItemsChanged`), there's no scroll and the mark shows at once.
- Otherwise `:961` calls `scrollToIndex({ index, animated:true, viewPosition:0 })`, which puts the badge and header at
  the top (step 4).
- An unmeasured row calls `onScrollToIndexFailed` (`:969`, wired at `:1491`). That jumps to
  `averageItemLength × index`, without animation and ignoring that jump's own momentum-end, then retries `scrollToIndex`
  once, 250 ms later, in a `try`.
- A drag (`onArrivalDrag`, `:1002`) cancels a pending retry.
- `onMomentumScrollEnd` (`onArrivalSettle`, `:997`) calls `showMark` (`:845`). A 600 ms fallback covers a scroll that
  moves nothing: Fabric emits no momentum-end when the offset is unchanged.
- `showMark` sets full opacity and `shown`. The row's last child (`:1579`) then renders the `ARRIVAL_MARK` outline.
  - It's `pointerEvents="none"`, `accessible={false}` and `importantForAccessibility="no-hide-descendants"`, keyed on `ts`.
  - It holds 2000 ms, then `Animated.timing` takes it 1 → 0 over 120 ms ease-out on the native driver (`:861`), then
    `endMark`.
  - Under Reduce Motion (`:853`) it's removed after the same hold, with no fade.
- The header ref (`:1516`) takes VoiceOver focus on show (`:889`, step 6).
- `:880` ends the mark and clears its timer if the row leaves `visibleMatches` or the segment changes.
- `:873` clears every timer on unmount.

**Not-found path**
- After the one refetch, the id is still missing at `:913`, so `finish()` runs.
- If the fetch failed or is paused offline (`:928`), the arrival ends with no line and no scroll. The existing error or
  empty state shows, and a later pull to refresh can't jump, because the `ts` is done.
- Otherwise:
  - `endMark()` runs, so nothing is marked;
  - the list scrolls to the top unless the user dragged (`:933`);
  - `notFoundToast(MATCH_NOT_FOUND_LINE)` returns `null`, so no Toast shows (`:935`).
- There's no toast, no error and no event. The arrival shows the Mutual list, or its empty state.

### §7 coverage

| §7 row | Covered by |
|---|---|
| Land on Mutual; chip to All only if it hides the row | code + check (P-3, P-7) |
| Wait for the list; refetch once when missing | code + check (P-4, P-5) |
| `scrollToIndex` with `viewPosition 0`, estimate, then one retry | code + check (P-8, P-9). Visible landing: TestFlight 1, 4 |
| A row already fully in view doesn't scroll | code + check (P-8b, P-8c). TestFlight 3 |
| A drag drops the scroll | code + check (P-8b, P-10). Runtime: TestFlight 8 |
| Mark: whole row, 2000 ms, 120 ms native fade, Reduce Motion, once per `ts`, timers cleared | code + check (P-12 to P-17). Look and timing: TestFlight 1, 9, 12, 13, 14 |
| VoiceOver focus on the header | code + check (P-18). TestFlight 11 |
| Dismissed, or not found after a fresh fetch | code + check (P-6). TestFlight 6 |
| Declined / already sent | Found, because the list returns every status (`server.py:25298-25306`). TestFlight only |
| Expired | Can't happen (head-product's v1 ruling 2). n/a |
| Fetch failed, or offline with the id not cached | code + check (P-6a). TestFlight 7 |
| Offline with the id cached | code: found in the cache, no refetch. TestFlight only |
| Mutual empty | code: the empty state; the line is `null`. TestFlight only |
| The not-found line | the constant, shipped `null`, plus check (U-2a to U-2c, P-6). The words go to marketing (~11-03) |
| No arrival, no change (tab press, League tiles) | code: no `match_id` means no effect; a stale `ts` is already done. TestFlight 10 |

### Manual TestFlight checklist

This follows ux-states §7. Use two accounts, A on the phone and B on the web, in one league, with mutual matches
between them. B accepts on the web.

1. **Cold start:**
   - Kill the app on A. B accepts.
   - Tap the "@B accepted your trade" push.
   - Matches opens on Mutual, scrolled to that card, with a flare outline round the whole row for about 2 s.
2. **Wrong segment and chip:**
   - Leave Matches on Awaiting, with the chip on another league.
   - Tap the push: Mutual opens, the chip goes to All, and the card is scrolled to and outlined.
3. **Right chip:** with the chip on the match's own league, tap the push. The chip stays. If the card is already fully in
   view, the list doesn't move and the outline shows at once.
4. **Long list:** with 8 or more matches, tap the push for the bottom one. It scrolls fully into view, with its header at
   the top.
5. **Brand-new match:** tap a new-match push within seconds. The card is scrolled to and outlined, and nothing else shows.
6. **Dismissed:**
   - Dismiss a match and wait past Undo.
   - Tap its old notification in the TopBar inbox.
   - The Mutual list shows at its top, nothing is outlined, and **no line shows**: `MATCH_NOT_FOUND_LINE` ships `null`
     until marketing's words land.
7. **Offline:**
   - Turn on airplane mode, then tap a push for a match this phone hasn't loaded.
   - The normal error state shows, with no line.
   - Turn the network back on and pull to refresh: the list doesn't jump.
8. **Drag first:** on 3G (Network Link Conditioner), tap a push and start scrolling at once. The list never jumps under
   your finger.
9. **Repeat:** after the outline fades, scroll away, then tap the same inbox notification again. It scrolls and outlines
   again.
10. **No arrival, no change:** a plain Matches tab press, and League home's Matches tiles, never scroll, outline or show
    a line.
11. **VoiceOver on:** after the scroll, focus is on "New match with @‹name›". The outline isn't announced.
12. **Reduce Motion on:** the outline disappears at about 2 s, with no fade.
13. **Send while outlined:** tap Send in Sleeper while the outline shows. It works normally (the overlay passes touches
    through).
14. **The look:** a 2pt flare outline, 6pt outside the row, radius 8. No fill, tint or glow. The green header and the ice
    Send button are unchanged.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added or changed. The refetch is the existing `GET /api/trades/matches/all` |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. It's a client-side screen effect |
| `living-memory/HLD.md` | n/a | Not an architecture shift |
| `docs/cross-client-invariants.md` | n/a | No shared enum, colour or threshold. The mark uses the existing `flare.base`, `radii.md` and `duration.fast` tokens |
| `docs/glossary.md` | n/a | No new domain term |
| ADR or `DECISIONS.md` | n/a | The behavior is ux-lead's §7 and design-lead's mark spec. Not a new architectural choice |
| `mobile/tests/README.md` | updated | Matches row: `check-matches-push-scroll` |
| `mobile/src/screens/CLAUDE.md` | updated | `MatchesScreen` row: the arrival behavior |
| `docs/plans/README.md` | updated | New thread row |

## 5. Ship gate declaration

- **CI:** on the worker's machine, `tsc --noEmit` is clean, all 135 `mobile/tests/check-*.js` pass, and `testid-lint`
  is OK. CI on the pushed sha is the lead's to confirm.
- **Evidence:** `living-memory/TEST_LEDGER.md` is written at merge by the lead or release-lead. This worker commits only.
- **TestFlight:** the 14 steps above, run by the operator or release-lead QA, with the outcome logged in TEST_LEDGER.
- **Express lane:** no. The full gates apply, kept lean for a bug fix.
- **Open edges:**
  - The not-found line ships `null`. Marketing's words (~11-03) are a one-constant swap.
  - When the line is set, it replaces an Undo toast that's showing at that moment.
