# Feature Scope — Matches push arrival: scroll to the card and mark it (R2)

**Date:** 2026-10-31 (rounds 2 and 3 after release-lead's QA on #568, 2026-11-01)
**Entry point:** direct ask: head-eng's 11-06 bug-fix call on ux-lead's finding R2 (head-product ruled it into Update 1's scope on 2026-11-01, then pulled it forward as a bug fix). The spec is `docs/plans/action-banner/ux-states.md` §7 (draft 1.2) plus design-lead's mark spec. Both live on the org-bringup branch, not on `main` yet.
**Builder:** eng-mobile worker for engagement-eng (branch `fix/matches-push-scroll`, PR #568)
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
- That query (`MatchesScreen.tsx:350`) feeds only the Mutual FlatList: `visibleMatches` at `:803`, rendered at
  `:1591-1594` with key `match_id`.
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

- [x] **Structural guard:** `mobile/tests/check-matches-push-scroll.js` (`npm run test:matches-push-scroll`), 93 checks.
  - **Executed** (`utils/matchesDerive.ts`, transpiled and run under node):
    - `indexForMatch`;
    - `notFoundToast`: null → no line; a string → exactly that string, held 4 s;
    - the shipped `MATCH_NOT_FOUND_LINE === null`;
    - `clampOffset`: floors at 0, caps at the content end;
    - `scrollFailureJump`: the list's top padding + index × average − `viewOffset`, clamped; nothing measured (a fresh
      mount, average 0) → no jump;
    - `alreadyInView`: row 0 clears only with ≥ 8pt above it; any other row only when the row above is fully visible;
    - `endClamp`: a settle past the end pulls back to it.
  - **Structural pins:**
    - typed route params (no `useRoute<any>`); reads `match_id` and `ts`, with `ts` dedupe;
    - lands on Mutual before the wait;
    - **cancels on a blur or a segment change after Mutual has rendered** (`finishArrival` + `endMark`);
    - waits for the list, then refetches once;
    - the not-found and error branches;
    - the chip goes to All only when it hides the row;
    - `scrollToIndex` with `viewPosition 0` and **`viewOffset: ARRIVAL_VIEW_OFFSET` (a space token ≥ 8pt)**, on both the
      first scroll and the retry;
    - `onScrollToIndexFailed`: the clamped estimate from the top padding, then **at most 4 retries**; a jump that will be
      retried isn't the settle (`ignoreSettleRef = willRetry`, N-15);
    - the found path clears an earlier arrival's timers before arming its own (N-25);
    - the in-view skip goes through `alreadyInView` with the tracked scroll offset and `MATCHES_LIST_PAD` (the list's real
      padding);
    - the estimate clamped to the tracked content end; a settle past the end pulled back (a guard: Fabric already
      clamps `scrollTo` on iOS);
    - the drag guard;
    - momentum-settle, plus the 600 ms fallback; the 250 ms retry delay;
    - the overlay props, `ARRIVAL_MARK`'s values, and 2000 ms then 120 ms ease-out on the native driver;
    - Reduce Motion;
    - keyed on `ts`;
    - timers cleared on unmount, when the row goes, and inside `endMark`;
    - VoiceOver focus (and its deps);
    - the found path's order (`finishArrival` before the mark is armed, shown or scrolled to); `showMark(` called from
      exactly three places; `trustView` trusted only when Mutual was already up;
    - no analytics and no API call;
    - the producer contract in `deepLinks.ts` and `RootNav.tsx`.
  - **G-035 label:** it proves the wiring, not runtime behavior.
  - **Sabotage:** 43 mutants across three rounds, each run once, all RED. Files restored byte-identical (sha-checked).
    The round-2 "average-0 step" mutant is gone with the branch it tested.
    - Round 2:
      - drop `viewOffset` from the first scroll, or from the retry;
      - set `viewOffset` under 8pt;
      - leave `viewOffset` out of the estimate;
      - leave the arrival armed on a blur, or on a segment change;
      - remove the end pull-back, or the estimate clamp;
      - make the retries unbounded;
      - drop `finishArrival` from the found path;
      - add a fourth `showMark` call;
      - change the fallback from 600 to 1000 ms;
      - always trust viewability;
      - drop `ts` from the a11y deps;
      - make `endMark` keep its timers;
      - set the route back to `any`.
    - Round 3:
      - drop the found path's `clearMarkTimers()` (N-25);
      - set `ignoreSettleRef` to `false` instead of `willRetry` (N-15);
      - make the in-view test "fully visible" only, or let row 0 skip regardless of its gap;
      - bypass `alreadyInView` in the screen, or stop tracking the scroll offset;
      - drop the top padding from the estimate.
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
- `:135` types the params (`MatchesRouteParams`) and `:266` reads them. `:843-845` reads `match_id` and `ts` as strings.
- The arrival effect starts at `:951`.
  - **Blurred:** if an arrival had already reached Mutual, `:956` ends it (`finishArrival`) and clears the mark.
  - **Focused:** it returns at `:961` if this `ts` is already done.
- New arrival: `:972` switches to Mutual at once (§7 step 1).
- Same arrival, and the user has since picked Awaiting or Standing after Mutual rendered: `:973` cancels it. A later
  return to Mutual never scrolls, marks or re-chips.
- `:981` waits while the first fetch or a refetch runs (step 2).
- `:983` looks the id up in `hiddenAwareMatches` (every league, minus pending dismisses).
- Missing: `:991` refetches once, unless paused offline. The effect runs again when `isFetching` drops.
- Found: `:1012` sets the chip to All, but only when `visibleMatches` lacks the row (step 3).
- The effect waits for the Mutual list to render, calls `finishArrival`, clears any earlier arrival's timers (`:1018`),
  then sets the mark to pending.

**Effect → row visible → marked**
- `:1024-1033`: there's no scroll, and the mark shows at once, if the user dragged during the wait, or if
  `alreadyInView` says the row is already on screen with room for the outline's top stroke:
  - the row is fully visible (100% viewability, `onViewableItemsChanged`), trusted only when Mutual was up before the
    arrival; and
  - for row 0, the list's top padding minus the tracked scroll offset (`onScroll`, `:1607`) is ≥ 8pt;
  - for any other row, the row above it is fully visible too.
  - Otherwise it scrolls, so a fully visible row whose top is 0–6pt from the edge no longer gets a clipped top stroke.
- Otherwise `:1040` arms the 600 ms fallback.
- `:1041` calls `scrollToIndex({ index, viewPosition:0, viewOffset: ARRIVAL_VIEW_OFFSET })`. The row lands 8pt
  (`space.sm`, `:116`) below the list's top, so the outline's −6pt top stroke isn't clipped (P2-1).
- An unmeasured row calls `onScrollToIndexFailed` (`:1055`, wired at `:1596`).
  - With a measured average, `scrollFailureJump` (`:1066`) jumps to the row's estimated top: the list's 16pt top padding
    (`MATCHES_LIST_PAD`, `:119`) + `average × index − viewOffset`, clamped to the content end that
    `onContentSizeChange` / `onLayout` track (`:1601-1606`).
  - On a fresh mount nothing is measured yet (average 0), so there's no jump; the retry just waits for the first cells.
    The old "step to `highestMeasuredFrameIndex`" branch is removed. That index starts at 0, not −1
    (`ListMetricsAggregator.js:63`), so the step was always `scrollToIndex(0)` at −8, a no-op once iOS clamps it.
    Removing it changes no behavior.
  - A jump that will be retried is not the settle (`ignoreSettleRef = willRetry`, `:1062`).
  - It then retries `scrollToIndex` 250 ms later, in a `try`, at most `ARRIVAL_MAX_TRIES = 4` times (`:129`, `:1068`).
    After that, the last jump stands.
  - Why 4: the estimate renders the window round the target, so the second or third try normally lands. 4 bounds a list
    whose row heights vary enough that the estimate keeps missing.
- A drag (`onArrivalDrag`, `:1107`) cancels a pending retry.
- `onMomentumScrollEnd` (`onArrivalSettle`, `:1087`):
  - **Past the content end:** VirtualizedList never clamps `scrollToIndex`. `endClamp` (`:1092`) would pull back to the
    end once. On iOS this can't fire, because Fabric's `scrollTo` already clamps to the content bounds
    (`RCTScrollViewComponentView.mm`, `scrollTo:y:animated:`). It stays only as a guard.
  - **Otherwise:** it calls `showMark` (`:899`). The 600 ms fallback covers a scroll that moves nothing, because Fabric
    emits no momentum-end when the offset is unchanged.
- `showMark` sets full opacity and `shown`. The row's last child (`:1693`) then renders the `ARRIVAL_MARK` outline
  (`:95`).
  - It's `pointerEvents="none"`, `accessible={false}` and `importantForAccessibility="no-hide-descendants"`, keyed on `ts`.
  - It holds 2000 ms, then `Animated.timing` takes it 1 → 0 over 120 ms ease-out on the native driver (`:915`), then
    `endMark`.
  - Under Reduce Motion (`:907`) it's removed after the same hold, with no fade.
- The header ref (`:1630`) takes VoiceOver focus on show (`:948`, step 6).
- `:939` ends the mark and clears its timer if the row leaves `visibleMatches` or the segment changes.
- `:932` clears every timer on unmount.

**Not-found path**
- After the one refetch, the id is still missing at `:983`, so `finishArrival()` runs.
- If the fetch failed or is paused offline (`:998`), the arrival ends with no line and no scroll. The existing state
  shows, and a later pull to refresh can't jump, because the `ts` is done.
- Otherwise:
  - `endMark()` runs, so nothing is marked;
  - the list scrolls to the top unless the user dragged (`:1003`);
  - `notFoundToast(MATCH_NOT_FOUND_LINE)` returns `null`, so no Toast shows (`:1005`).

### §7 coverage

| §7 row | Covered by |
|---|---|
| Land on Mutual; chip to All only if it hides the row | code + check (P-3a, P-7). TestFlight 2, 3 |
| Wait for the list; refetch once when missing | code + check (P-4, P-5). TestFlight 5 |
| `scrollToIndex` (`viewPosition 0`, `viewOffset`), padded estimate, bounded retries | code + check (P-8, P-9, U-3, U-4). Visible landing: TestFlight 1, 4a–4c, 14 |
| A row already in view (with room for the top stroke) doesn't scroll | code + check (P-8c to P-8e, P-20d, U-6). TestFlight 3 |
| A drag drops the scroll | code + check (P-8c, P-10). Runtime: TestFlight 8 |
| An unfinished arrival never stays armed | code + check (P-3b, P-3c, P-9h). TestFlight 8b, 8c, 10 |
| Mark: whole row, 2000 ms, 120 ms native fade, Reduce Motion, once per `ts`, timers cleared | code + check (P-12 to P-17). Look and timing: TestFlight 1, 9, 12, 13, 14 |
| VoiceOver focus on the header | code + check (P-18). TestFlight 11 |
| Dismissed, or not found after a fresh fetch | code + check (P-6). TestFlight 6a, 6b |
| Declined / already sent | Found, because the list returns every status (`server.py:25298-25306`). TestFlight only |
| Expired | Can't happen (head-product's v1 ruling 2). n/a |
| Offline (paused) or fetch failed, with the id not cached | code + check (P-6a). TestFlight 7a (paused), 7b (failed) |
| Offline with the id cached | code: found in the cache, no refetch. TestFlight only |
| Mutual empty | code: the empty state; the line is `null`. TestFlight only |
| The not-found line | the constant, shipped `null`, plus check (U-2a to U-2c, P-6). The words go to marketing (~11-03) |
| No arrival, no change (tab press, League tiles, re-arrival probes) | code: no `match_id` means no effect; a done `ts` never replays. TestFlight 10 |

### Manual TestFlight checklist

This follows ux-states §7, with release-lead's QA additions on #568.

**Preconditions:**
- Two accounts: A on the phone, B on the web, in two shared leagues, with at least 12 mutual matches across them. B
  accepts on the web.
- Notifications on for A. Quiet hours off, or test between 08:00 and 22:00.
- Every push step needs a match B hasn't accepted yet. Repeats can use the bell-inbox "Trade match with @B" rows instead
  of a fresh push.
- Step 13 runs on a build that includes #488.

1. **Cold start:**
   - Kill the app on A. B accepts a **1-for-1** match (one player each side) that is **not the first card**.
   - Tap the "@B accepted your trade" push.
   - Matches opens on Mutual, scrolled to that card, with a flare outline round the whole row for about 2 s.
   - **All four sides of the outline are visible.** A 2-for-2 row is taller than an SE's list area (about 475pt in about
     331pt) by design; on one, check the top edge, then scroll to see the bottom edge.
2. **Wrong segment and chip:**
   - Leave Matches on Awaiting, with the chip on the other league.
   - Tap the push: Mutual opens, the chip goes to All, and the card is scrolled to and outlined.
3. **Right chip:** with the chip on the match's own league, tap the push. The chip stays. If the card is already fully in
   view and the card above it is fully in view too (or it's the first card, unscrolled), the list doesn't move and the
   outline shows at once.
4. **Long list:**
   - **4a. Warm:** with Matches already open on Mutual and the chip on All, tap the push for a row ≥ 6. It scrolls so the
     row's top, its league badge, lands 8pt below the list's top, outlined.
   - **4b. Remount:** leave Matches on Awaiting, with 12 or more matches. Tap the push for a row ≥ 11. Mutual remounts
     and the card scrolls into view, outlined.
   - **4c. The last card, on the biggest phone:** tap the push for the last card. It scrolls as far as the list allows
     (iOS clamps at the content end), with no blank band under it, and the outline shows.
5. **Brand-new match:** open Matches, then have the match form and tap its push within 15 s. The card is scrolled to and
   outlined (the one refetch found it), and nothing else shows.
6. **Dismissed:**
   - **6a.** Dismiss a match and wait past Undo. Tap its old notification in the TopBar inbox. The Mutual list shows at
     its top, nothing is outlined, and **no line shows**: `MATCH_NOT_FOUND_LINE` ships `null` until marketing's words
     land.
   - **6b.** Dismiss a match, and **during the Undo window** tap its inbox row. Same as 6a: the top, nothing outlined, no
     line. Then tap Undo: the card comes back, unmarked, and the list doesn't jump.
7. **Offline.** Airplane mode pauses queries rather than failing them (NetInfo → `onlineManager`, `App.tsx:254-266`),
   so it never shows the error state.
   - **7a. Paused:**
     - Receive a push for a match this phone hasn't loaded.
     - Turn airplane mode on, then tap the push from Notification Center.
     - Matches opens on Mutual with the cached list (if one is under 30 min old) or "No mutual matches yet". There's no
       outline, no line and no jump.
     - Turn airplane mode off: the list loads, and doesn't jump or outline. Pull to refresh: no jump either.
   - **7b. Failed (the real error state):**
     - Join a hotspot with no internet (connected, no route), then tap a push for an unloaded match.
     - The "Could not load matches." error state shows, with no line.
     - Restore internet and pull to refresh: the list loads and doesn't jump.
8. **Drag first:** on 3G (Network Link Conditioner; it needs Developer Mode on the phone), tap a push and start scrolling
   at once. The list never jumps under your finger.
   - **8b. Cancel mid-wait, segment:** on 3G, tap a push, then pick Awaiting before the list lands. Go back to Mutual:
     no scroll, no outline, and the chip is as you left it.
   - **8c. Cancel mid-wait, tab:** on 3G, tap a push, then switch to another tab before the list lands. Come back to
     Matches after it has loaded: no scroll and no outline.
9. **Repeat:**
   - After the outline fades, scroll away, then tap the same inbox notification again. It scrolls and outlines again.
   - **Fast double-tap** on an inbox row: one scroll and one outline, with no stutter.
10. **No arrival, no change:** none of these ever scroll, outline or show a line:
    - a plain Matches tab press, and League home's Matches tiles;
    - **re-arrival probes** after an arrival: tab away and back, background then foreground, pull to refresh, and
      dismiss *another* match.
11. **VoiceOver on:** after the scroll, VoiceOver reads "New match with @B" first. The outline isn't announced.
12. **Reduce Motion on:** the outline disappears at about 2 s, with no fade. **Screen-record it.**
13. **Send while outlined** (a build with #488): tap Send in Sleeper while the outline shows, then **cancel at "Send
    this trade?"**. The dialog works normally (the overlay passes touches through), and nothing is sent.
14. **The look:**
    - A 2pt flare outline, 6pt outside the row, radius 8. No fill, tint or glow.
    - **The top edge is visible after a scroll** (the row sits 8pt below the list's top).
    - The green header and the secondary Send in Sleeper button are unchanged. The card has no ice button (only the
      YOU SEND / YOU GET ticks are ice).

**Render:** `renders/arrival-mark.png` (v3: a local react-native-web render of the real code by release-lead's QA, not
a device capture).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added or changed. The refetch is the existing `GET /api/trades/matches/all` |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. It's a client-side screen effect |
| `living-memory/HLD.md` | n/a | Not an architecture shift |
| `docs/cross-client-invariants.md` | n/a | No shared enum, colour or threshold. The mark uses the existing `flare.base`, `radii.md`, `duration.fast` and `space.sm` tokens |
| `docs/glossary.md` | n/a | No new domain term |
| ADR or `DECISIONS.md` | n/a | The behavior is ux-lead's §7 and design-lead's mark spec. Not a new architectural choice |
| `docs/design/components.md` | updated | Feedback & status: an "Arrival mark" row (design-lead's spec) |
| `mobile/tests/README.md` | updated | Matches row: `check-matches-push-scroll` |
| `mobile/src/screens/CLAUDE.md` | updated | `MatchesScreen` row: the arrival behavior |
| `docs/plans/README.md` | updated | New thread row |

## 5. Ship gate declaration

- **CI:** on the worker's machine, `tsc --noEmit` is clean, all `mobile/tests/check-*.js` pass, and `testid-lint`
  is OK. CI on the pushed sha is the lead's to confirm.
- **Evidence:** `living-memory/TEST_LEDGER.md` is written at merge by the lead or release-lead. This worker commits only.
- **TestFlight:** the steps above, run by the operator or release-lead QA, with the outcome logged in TEST_LEDGER.
- **Express lane:** no. The full gates apply, kept lean for a bug fix.
- **Open edges:**
  - The not-found line ships `null`. Marketing's words (~11-03) are a one-constant swap.
  - When the line is set, it replaces an Undo toast that's showing at that moment.
  - **No tail overshoot on iOS.** Fabric's `scrollTo` clamps to the content bounds, so a tail row's `scrollToIndex`
    target never passes the end, and no band shows. `endClamp`'s pull-back is kept only as a guard and never fires on an
    iPhone. The estimate jump is also clamped up front.
