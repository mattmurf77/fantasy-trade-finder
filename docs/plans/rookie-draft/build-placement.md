# Build status — draft-surface placement (option B + seasonal A′)

**Date:** 2026-08-06 · **Wave:** draft-surface placement
**Parent:** [plan.md](plan.md) § "Operator decision — draft-surface placement (2026-08-06)" (binding)
**Approved mock:** `mockups/polish-lab-2026-08/draft-surface-placement.html` (frames B1/B2, A′1/A′2)
**Builds on:** [build-m4.md](build-m4.md) (the shipped `DraftRoomScreen` + `draft.room` / `draft.live_poll`)
**Gates:** `python3 -m pytest backend/tests -q` → **1763 passed / 1 skipped**, exit 0 (baseline 1759/1; +4) · `cd mobile && tsc --noEmit` → **clean**

No new feature flag. Both surfaces ride `draft.room` (already OFF); the
rookie-ranking bridge rides `ranks.rookie_subset` (already OFF). With
`draft.room` off, the mode strip renders today's five chips exactly, the tab
bar is the shipped four tabs, and the League tile keeps its M4 behavior.

---

## 1. What shipped

### B — the Draft chip LEADS the Acquire mode strip (permanent home)

| File | Change |
|---|---|
| `mobile/src/components/TradeFinderModeBar.tsx` | New optional `onDraft` prop + `DRAFT_CHIP`. When the host passes a handler the chip is **prepended**: `[DRAFT_CHIP, ...CHIPS]`. testID `trades.finder-mode.draft` |
| `mobile/src/screens/TradesScreen.tsx` | Reads `draft.room` (`draftRoomOn`) and passes `onDraft={() => navigation.navigate('DraftRoom')}` only when on |

**Why it leads and not trails.** The shipped five chips measure ≈402pt
against ≈361pt of usable width, so the strip is genuinely scrolled — an
*appended* sixth chip would sit off-screen and never be seen (mock, Option B
implementation row). Leading is the only position where the chip exists for
the user.

Passing the handler is what *creates* the chip, so the flag gates existence
rather than behavior: `draft.room` off ⇒ the chips array is the shipped five,
same order, same object identities.

Precedent, not a hack: Calc and Free agents are already push-chips in this
strip with deliberately no visual distinction from the three in-place deck
modes. There are exactly three ways to acquire a player in dynasty — trade
for him, pick him up, draft him — and two already lived here.

### A′ — the seasonal 5th bottom tab "Draft"

| File | Change |
|---|---|
| `backend/server.py` | `sleeper_leagues`: behind `is_enabled("draft.room")`, stamp each league row with `draft_status` + `draft_status_confidence` from the cached #207 columns. The wave's ONLY backend edit |
| `mobile/src/shared/types.ts` | `LeagueSummary.draft_status?` / `.draft_status_confidence?` (optional, additive) |
| `mobile/src/api/sleeper.ts` | `getLeagues` maps the two fields through |
| `mobile/src/state/draftLeagues.ts` | **new** — the predicate + the hydrate/refresh/read triple |
| `mobile/App.tsx` | `hydrateDraftLeagues()` joins the boot gate; `refreshDraftLeagues()` joins the post-revalidate detached refresh |
| `mobile/src/navigation/TabNav.tsx` | `DraftStackNav` + `DraftLeagueChooserScreen` + the conditional `<Tab.Screen name="Draft">` |
| `mobile/src/navigation/RootNav.tsx` | `DraftRoom` param type widened to `{ leagueId?: string } \| undefined` |
| `mobile/src/screens/DraftRoomScreen.tsx` | Optional `leagueId` override + `inTabs` FAB suppression |

Tab order matches the mock's A′1 frame: **Rank · Acquire · Draft · Matches ·
League**. Icon is the existing `flag` glyph (the same one the mock drew).
**No flare dot** — the tab's *presence* already means "a draft is pending",
and Sleeper exposes no trustworthy scheduled start time, so there is nothing
honest to count down to.

### The bridge back to rookie ranking (mock finding #2)

`DraftRoomScreen` renders a **"Rank the rookies"** row (testID
`draft-room.rank-rookies`) directly under the status bar, in every board
state including `unavailable` — pre-draft prep is exactly when the board has
least to show and the ranking board matters most. It navigates
`Main → Rank → RookieRanks` (deep link `app/rank/rookies`), which resolves
identically from the root-stack push and from inside the Draft tab.

Gated on `ranks.rookie_subset`: with that flag off `RookieRanksScreen`
renders its own "not available yet" state, and an entry point into a
dead end is worse than no entry point.

---

## 2. Tab-visibility state table

The predicate lives in one place — `leagueQualifiesForDraftTab()` in
`mobile/src/state/draftLeagues.ts` — and reads **only** the shipped #207
columns. The tab shows when **ANY** linked league qualifies.

| `draft_status` | `draft_status_confidence` | Source that produces it | Tab | Why |
|---|---|---|---|---|
| `not_drafted` | `high` | `sleeper_verdict` — every current-season **rookie-shaped** draft object is `pre_draft`/`drafting`; or `mfl_verdict` — rookie-sized grid with unmade picks | **VISIBLE** | Exactly the operator's condition: a current-season rookie-shaped draft object exists and has not run |
| `not_drafted` | `medium` | `rosters_verdict` — "zero rookies on any roster" | hidden | The heuristic says nothing about a draft object *existing*. A league with no draft at all reads the same way |
| `drafted` | any | Sleeper `complete` + `last_picked`, MFL `made == total`, or the rosters veto | hidden | Recap lives on the League tile (option C, unchanged). The Acquire tab should not hold a permanent recap — recaps are not acquisition |
| `unknown` | any | `_fall_back` with no usable signal | hidden | Fail-safe matches `current_year_picks_visible()`: absence is self-correcting, a tab that lies is not |
| null (no `leagues` row) | null | Never synced | hidden | Same rule |
| any | any, **flag `draft.room` OFF** | — | hidden | The server never stamps the field; the client finds nothing that qualifies |
| startup-shaped draft | — | `sleeper_verdict` falls through to the heuristic on a startup-only season | hidden | Never `not_drafted`+`high`, so it can't reach the tab. Startup label-and-degrade stands (operator O5) |

**Multi-league rule** (plan's operator decision, which *overrides* the mock's
"drive off the active league" suggestion):

| Qualifying leagues | Tab | Lands on |
|---|---|---|
| 0 | absent | — |
| 1 | present | that league's room directly (`initialParams.leagueId`) |
| >1 | present | `DraftLeaguePicker` chooser (`draft-chooser.league.<id>` rows) → pushes the room for the chosen league |

The room takes a **`leagueId` param override** rather than switching the
active league: reading one league's board must not reset rankings, the trade
deck and the scoring format. Every pre-existing entry point (League tile,
Acquire chip, deep link) passes nothing and keeps reading the session's
active league exactly as before.

---

## 3. First-mount-only contracts (the risk the mock flagged as A′'s highest)

Conditionally rendering a `<Tab.Screen>` rewrites the navigator's route
array, which reshuffles indices and can reset nested stack state. Three
shipped contracts are "first mount only" and a mid-session tab insertion
would violate all three. What protects them:

1. **The decision is frozen at mount.** `showDraftTab` is a
   `useState(() => …)` initializer — the same shape as `initialTab` above it
   and `#244`'s `launch` in `RankStackNav`. The bar changes at most once per
   launch.
2. **The flag is read imperatively**, `useFeatureFlags.getState().flags['draft.room']`,
   *not* via `useFlag`. A mid-session flag revalidation must not be able to
   insert or remove a tab under the user's thumb.
3. **The snapshot converges next launch, never mid-session.**
   `refreshDraftLeagues()` persists to AsyncStorage after `revalidateSession`;
   `hydrateDraftLeagues()` reads it in the App.tsx boot gate *before* the
   navigator mounts. Identical two-beat shape to `#244`'s
   `state/quicksetProgress.ts`.

Consequently, unchanged whether the tab is present or absent:

- **`initialRouteName={initialTab}`** — resolves by NAME (`'Rank'` / `'Trades'`),
  never by index. A sibling tab cannot move it.
- **#244 completion-aware Rank launch routing** — lives entirely inside
  `RankStackNav` (`PREF_ROUTE`, `nextQuicksetPosition()`, `initialParams`).
  Untouched.
- **#245/#246 Acquire semantics** — the label "Acquire", route name `Trades`,
  `TradesHome` = TradesScreen with `initialParams {mode:'guided'}`, `TradeDeck`
  registration, the prefetch listener. All inside `TradesStackNav` and the
  Trades `<Tab.Screen>`. Untouched; the only Acquire-side change is the extra
  chip inside the strip.

**Known, accepted lag:** a brand-new install has no snapshot, so the tab does
not appear until the launch *after* the first successful refresh. That is the
designed cost of "at most one bar change per launch", and the Acquire chip —
the draft's permanent home — is present immediately whenever `draft.room` is
on. Absence is the fail-safe direction.

---

## 4. Deep links with the tab hidden (and with it present)

`DraftRoom` is now **dual-registered**: on the root stack (unconditional,
since M4) and inside the Draft tab's stack. `utils/deepLinks.ts` keeps
`DraftRoom: 'app/league/draft-room'` as the **one canonical URL**, mapped to
the **root-stack** registration. The tab's copy deliberately has **no path of
its own** — two paths for one screen is how a link starts resolving
differently depending on the season.

| Situation | `app/league/draft-room` | Result |
|---|---|---|
| Tab hidden (out of season, or `draft.room` off) | resolves to root-stack `DraftRoom` | pushes the room over the tabs; Back returns to where the user was. **Never a 404** — the route was already unconditional, the flag gates entry points |
| Tab present, user anywhere | resolves to root-stack `DraftRoom` | identical push, identical back behavior. The tab is not disturbed |
| Tab present, user standing in the Draft tab | resolves to root-stack `DraftRoom` | a room pushed *over* the tab's room; Back returns to the tab. Same as tapping the League tile from inside the tab today |

`navigate('DraftRoom')` from the Acquire chip resolves the same way in both
tab states: react-navigation searches the current navigator and its
**parents**, never a sibling's children — the Trades stack has no
`DraftRoom`, the tab navigator has no `DraftRoom`, so it lands on the root
stack. The Draft tab's nested copy is reachable only from inside that tab.

`FeedbackFAB`: the tab registration passes `inTabs: true`, which suppresses
the screen's own FAB — as a tab-stack screen it is already covered by
RootNav's global mount, and two FABs is the #196/#197 bug. The root-stack
push passes nothing and keeps its local FAB (`aboveTabBar={false}`) exactly
as M4 shipped it.

---

## 5. The one backend edit

`GET /api/sleeper/leagues/<user_id>` stamps `draft_status` +
`draft_status_confidence` per league from `get_league_draft_context`.

Why this route and not a new one, or `session_init`: the tab bar is global
while #207's verdict is per-league, so the predicate needs **every** linked
league answerable synchronously at first mount. `session_init` resolves one
league. This route is already the sole source of `useSession.leagues`, so the
verdict rides the payload the client was going to read anyway.

- **Cached columns only.** No detection, no platform read — refresh already
  belongs to the hourly tick and `session_init`'s sync path.
- **A league with no row gets explicit nulls**, not a missing key: the client
  reads the field unconditionally and an absent key would be
  indistinguishable from the flag being off.
- **Wrapped in try/except per league.** The league list is sign-in-critical;
  a verdict lookup that raises degrades to nulls and never 500s the picker.
- **Flag off ⇒ the block is skipped entirely** and the response is
  byte-identical to what shipped.

`database.py` untouched (the columns shipped with #207);
`trade_service.py` / `pick_values.py` untouched (owned by the concurrent M6b
wave); rank screens, `ranking_service.py` and `LeagueScreen.tsx` untouched.

---

## 6. Test coverage added

`backend/tests/test_draft_board.py`, 4 cases (the 43 pre-existing ones are
untouched):

| Test | Proves |
|---|---|
| `test_placement_leagues_payload_is_byte_identical_with_the_flag_off` | Flag off ⇒ neither key present, no DB read |
| `test_placement_leagues_payload_carries_the_207_verdict_with_the_flag_on` | `not_drafted`+`high` and `drafted` both stamped honestly |
| `test_placement_a_league_with_no_row_is_stamped_null_not_omitted` | Explicit nulls, not a missing key |
| `test_placement_a_draft_context_failure_never_breaks_the_league_list` | A raising lookup degrades to nulls, still 200 |

## 7. Not done here (by design)

- **Maestro coverage** for the new chip, the tab, the chooser and the
  rookie-ranks bridge — QA's wave. New testIDs: `trades.finder-mode.draft`,
  `tab.draft`, `draft-chooser.league.<league_id>`, `draft-room.rank-rookies`.
- **The optional "your rookie draft is live" tail row** under the deck (mock
  B1's second entry, ~62pt, live/upcoming only). The operator decision
  approved the chip; the tail row needs live board state on the Acquire
  landing, which today only `DraftRoomScreen`'s focused query holds.
- **Option D** (Rank-tab adjacency) — explicitly "not now"; revisit if QA
  shows draft prep starting on Rank.
- **The N-day post-draft recap window** the mock proposed for A′. The
  operator decision names only `not_drafted`/`drafting` as visible, so
  `drafted` hides immediately and the recap stays on the League tile (C).

## 8. Before flipping `draft.room` on

1. Re-run the flag-mirror pair; confirm the leagues payload is byte-identical
   flag-off.
2. Confirm on-device that the Draft chip is the FIRST chip and visible
   without scrolling the strip.
3. Confirm the tab appears/disappears only across launches, and that
   `app/league/draft-room` resolves in both states.
4. M4's own preconditions still apply (zero background requests before
   `draft.live_poll` follows).
