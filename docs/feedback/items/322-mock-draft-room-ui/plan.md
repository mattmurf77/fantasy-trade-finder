# G2 plan — Mock draft room UI (#322–#327)

> Phase-1 planning deliverable for group G2 of the 2026-08-16 feedback wave.
> Batch context: [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> Base for all analysis: `origin/main` @ `d3fe3ac` (v1.13.4). Path: Polish, one
> platform (mobile) — plus one small additive backend payload field forced by
> the operator's #323 tier decision (see §3.2). Plan only; no code here.

All six items are screen `MockDraft` (`mobile/src/screens/MockDraftScreen.tsx`),
filed on v1.13.2 by mattmurf77. The screen last changed in v1.13.3
(`e71a654`, #295/#296/#305 — membership repair + manual mode); v1.13.4 did not
touch it.

## 1. Reproduce check on current code (mandatory first step)

Each item re-verified against `d3fe3ac` source, not the working tree.

| Item | Still reproduces? | Evidence (all `MockDraftScreen.tsx` @ d3fe3ac) |
|---|---|---|
| #322 ticker order | **Yes** | `PickTicker`: `const recent = [...picks].reverse().slice(0, TICKER_DEPTH)` — newest pick renders at the TOP; the tester wants earliest-first |
| #323 chip labels | **Yes** | My-pick chips render `pickLabelOf(slot)` + `lastName(pick.name)` only — no position, no tier |
| #324 chips wrap | **No — not as filed.** `styles.myPicksRow` has carried `flexWrap: 'wrap'` since v1.12.0 (`6c304c7`) and it's unchanged; chips already collapse to multiple rows. But #323's bigger chips re-open the layout question, and the operator delegated an explicit layout — so #324 becomes the layout spec for the redesigned chip (§3.3), not a wrap fix. Do **not** close it; fold it into #323's build |
| #325 ticker height | **Yes** (same section as #322) | The `slice(0, TICKER_DEPTH)` cap already gives the steady-size behavior mid-draft; what changes is *which end* rows fall off once the order flips |
| #326 team view + position filter | **Yes** | No team view anywhere on the screen; the undrafted list renders `state.undrafted.map(...)` unfiltered |
| #327 pool search | **Yes** | No `TextInput` on the screen; no search of any kind |

The 1.13.3 diff (`git diff 6c304c7 d3fe3ac -- mobile/src/screens/MockDraftScreen.tsx`)
touched owner naming, manual-mode attribution, and analytics — none of the six
asks. One pleasant surprise: `state_payload()` **already emits**
`consensus_rank` / `consensus_delta` / `valued` on every `picks[]` entry
(gap G3 was closed server-side in 1.13.3) — the mobile `MockPick` type just
never picked them up. #323's payload work is smaller than the recap's G3 note
suggests.

## 2. Problem statements

- **#322 + #325 (one section, per operator):** the "Just picked / Since your
  last pick" ticker shows the most recent pick at the top and runs downward
  into older picks. Wanted: chronological reading order — earliest pick
  (1.01) at the top — inside a section whose footprint stays constant, with
  the *earliest* picks scrolling up and off the top as new picks land.
- **#323:** the "Your picks" chips name a slot and a surname; the user can't
  see what position he drafted or what the pick is worth in the app's own
  tier vocabulary.
- **#324:** with #323's richer chips, the chip row needs a stated layout —
  chips per row, wrap behavior — instead of intrinsic-width wrapping.
- **#326:** while on the clock there is no way to check your own roster
  (what do I need?) and no way to narrow the pool to a position.
- **#327:** no way to find a specific player in an 80-row pool.

## 3. Approach

### 3.1 #322/#325 — the ticker, respecified as one section

**Window:** the last `TICKER_DEPTH` (8) picks, rendered **ascending by
`pick_no`** — earliest of the window at top, newest at bottom. Concretely the
render source becomes `picks.slice(-TICKER_DEPTH)` (no `.reverse()`), extracted
into a pure helper `tickerWindow(picks, depth)` so it can be unit-tested.

**Behavior at draft start (list shorter than the window):** the section renders
exactly `min(picks.length, 8)` rows — 1.01 literally at the top from the first
pick. It *grows* one fixed-height row per pick until it holds 8, then its
height is constant for the rest of the draft: each new pick appears at the
bottom and pushes the topmost (earliest) visible row off the top. No
placeholder rows and no reserved empty space — rendering rows for picks that
don't exist yet fails the "designed states, not spinners" bar this screen was
built on. "The view remains the same size" is a steady-state property (window
full), which is the state the tester described; the brief growth phase covers
picks 1–8 only.

**Highlight re-index:** the "new since your last pick" tint currently keys on
`i < newest` (newest-first order). Flipped, the new rows sit at the *bottom*:
tint when `i >= recent.length - min(newest, recent.length)`. The "mine" tint
(`picked_by_user_id === userOwnerId`) is order-independent and unchanged.

**Unchanged:** `TICKER_DEPTH = 8`; header copy ("Since your last pick" when
`newest > 0`, else "Just picked"); row layout and testIDs
(`mock-draft.ticker-row.<pick_no>`). No animation — the CPU tail arrives as one
mutation response, so up to 8 rows change at once; an animated scroll would
fire them all simultaneously.

### 3.2 #323 — position + tier on the "Your picks" chips

**Tier source is the server (operator decision, #263/#277/#278 precedent).**
`picks[]` entries carry no value today, so:

- **Backend (additive, one function):** `state_payload()`
  (`backend/mock_draft_service.py:1328`) adds `"tier": <tier key | null>` to
  every `picks[]` entry (and therefore `my_picks[]`, which is a filter of the
  same list). Computed with the existing `ranking_service.tier_for_elo` walk
  over the pick's consensus Elo (`ctx.consensus_elo`), the league's scoring
  format, and the player's position — the same walk every other server tier
  consumer uses. `null` when consensus doesn't price him (the existing
  `valued: false` rows): the chip then shows no tier, never a fabricated one.
  The key is the standing 8-rung `Tier` enum verbatim (`firsts_4plus` …
  `waivers`, `docs/cross-client-invariants.md`) — no new enum, no new labels.
  Additive key ⇒ `MOCK_DRAFT_SCHEMA` stays 1 (the D10 open-payload
  convention; the client type is open and unknown keys are ignored).
- **Mobile:** `MockPick` in `mobile/src/api/mockDraft.ts` gains
  `tier: Tier | null` (and, while we're in the type, the already-emitted
  `consensus_rank` / `consensus_delta` / `valued` — typing only, no new UI).
  Chips render the enum key through the existing `TIER_LABEL` map /
  `TierBadge` — the client **never** derives a tier from a displayed value,
  rank, or label. Old-server fallback: `tier` absent ⇒ render no tier (same
  as `null`).
- **Chip content (made pick):** slot numeral (`type.data`, e.g. `2.05`), then
  a meta line: position in its position color (`positionOf`), tier label in
  its tier color, player surname. **Unpicked future slots** keep today's
  states ("on the clock" / "from {team}") with no position/tier — nothing has
  been drafted.

### 3.3 #324 — proposed chip layout (operator delegated)

**Proposal: a fixed 3-per-row equal-width chip grid; wrap, never an inner
scroll.**

- **Chips per row: 3.** Precedent: the Quick-set walk's 3-per-row grid of
  small player chips (components.md §Tier bins, the #140 spec). Math at the
  375pt baseline: 375 − 2×`space.lg`(16) content padding = 343pt; minus
  2×`space.sm`(8) gaps ⇒ ~109pt per chip — comfortably fits `2.05` +
  `RB · 2nd` + a surname at `type.bodySm`/11px floor with `numberOfLines={1}`.
- **Chip construction:** equal width (flex-basis three-across), `minHeight`
  ≥ 44, 1px `flare.base` border (unchanged — the chips are the user's own
  picks, flare is the informational highlight per ADR-005), radius `radii.xs`
  (2px, the badges/chips token), `space.sm` gaps, `space.sm`/`space.xs`
  internal padding.
- **Wrap/scroll threshold:** N picks ⇒ ⌈N/3⌉ rows, always fully rendered —
  4 picks = 2 rows, 8 picks = 3 rows, 12 picks = 4 rows. **No internal
  scroll at any count.** Rationale: a scrollable strip nested inside the
  screen's ScrollView is exactly the gesture-capture class that broke
  TestFlight builds #11/#12 (lessons.md 2026-07-12), and "Your picks" is the
  user's own inventory — hiding some of it behind a nested scroll trades a
  crash-risk for an information loss. A 20-pick outlier league costs ~7 rows
  of a screen that already scrolls; acceptable.

### 3.4 #326 — team sheet + position filter

**Team view is a sheet, never navigation (operator decision).**

- **New `MockTeamSheet`** (`mobile/src/components/draft/MockTeamSheet.tsx`):
  Modal bottom sheet per components.md §Sheets — `--ink-2` fill, top radius
  `--r-md` (8), 1px `--line` border, solid scrim `rgba(9,10,8,0.78)` (no
  blur), 32×4 grabber. Rendered as a sibling of the existing
  `PlayerContextMenu`/`AnchorSheet` modals, after the ScrollView, **inside
  the screen's single return** — the mode-marker structural contract
  (`check-mock-mode-marker.js`) is untouched because no mock *branch* is
  added.
- **Entry:** a "Your team" ice text link on the `OnTheClockCard`
  (testID `mock-draft.view-team`), rendered on every active turn (in manual
  mode every turn is the user's). Dismiss via grabber/scrim/close — the
  session screen never unmounts.
- **Content, two sections** (SectionList, the SwapPlayerSheet sectioned-picker
  construction: TickLabel banners, rows = position chip + name + right-aligned
  `data` value):
  1. **Roster** — the user's current dynasty roster grouped by position.
     Data: the shared power-rankings read
     (`['league-power-rankings', leagueId, 'consensus']` →
     `rosterByOwner[myOwnerId]`), the same source `InLeagueCalculator` uses —
     no new endpoint, and usually already cached. Loading/error states get
     honest one-line copy inside the sheet.
  2. **Drafted in this mock** — `my_picks` with #323's position + tier.
     The distinct banner keeps real-roster vs simulation legible inside a
     sheet that covers the MockRail.
  v1 always shows the *session user's* team, including manual-mode turns
  taken for another team (the item asks for "their team"; per-team rosters
  are a later enhancement, noted in §7).
- **Position filter:** a segmented chip row above the undrafted list —
  All · QB · RB · WR · TE (the `PositionTabs` construction: hairline group,
  active segment `--ink-3` well + position-color underline; testIDs
  `mock-draft.pos-filter.<pos|all>`). Filters `state.undrafted` before
  mapping; the "Tap to draft" flow through rows and confirm bar is unchanged.
  Zero matches ⇒ honest line ("No RBs left on the board") + the All chip
  still present to clear.
- **Reset each turn (operator decision):** a `useEffect` keyed on
  `on_the_clock?.pick_no` resets the filter to All — and clears the search
  (§3.5) — whenever the clock advances. A stale narrow view silently hiding
  the pool on a new turn is the trap this kills; it applies in both modes.

### 3.5 #327 — pool search

- `TextInput` between the filter row and the list, per `PlayerPickerModal`'s
  search construction (`--ink-1` fill, hairline border, radius `radii.sm`;
  testID `mock-draft.pool-search`). Case-insensitive substring match on
  player name; no debounce needed (in-memory list).
- **Scope (operator decision):** search filters the *currently active
  position-filter subset* — composition order is filter first, then search.
  A clear (`×`) affordance empties it; it also resets on every turn (§3.4).
- ScrollView gets `keyboardShouldPersistTaps="handled"` so a row tap while
  the keyboard is up drafts in one tap, and the confirm bar must be verified
  above the keyboard on-device (TestFlight checklist item).

## 4. Risks

1. **Gesture history (lessons.md 2026-07-12):** builds #11/#12 crashed when a
   new gesture captured list touches. This plan adds **no** gesture
   recognizers — only Pressables, a TextInput, and a Modal — and §3.3
   explicitly rejects a nested scrollable for the chip grid. The sheet's
   SectionList lives inside a Modal, not nested in the screen's ScrollView.
2. **`check-mock-mode-marker.js` / `check-mock-lifecycle.js` are pinned to
   this file's shape** (single return, rail above the branch, specific
   affordance assertions). The build must run both before and after; the
   sheet and controls are added inside the existing single return.
3. **Same-file overlap with G3 (#328):** G3's pick-ownership work is also in
   `backend/mock_draft_service.py` (settings/ownership resolution). G2's
   backend edit is confined to `state_payload()` pick serialization —
   different functions, but same file: whichever branch lands second rebases;
   noted for the batch's disjointness table.
4. **Ticker off-by-one:** the highlight re-index (§3.1) is the classic
   flipped-window bug; the pure `tickerWindow` helper exists precisely so the
   indices are unit-tested at 0/3/8/20 picks, not eyeballed.
5. **Manual-mode semantics:** chips, sheet, and ticker "mine" logic must keep
   keying on `settings_echo.user_owner_id` (never `by`) — reuse
   `resolveUserOwnerId`; regressions here re-open #305.
6. **Keyboard vs confirm bar:** a selected row plus an open keyboard could
   occlude the confirm bar — on-device checklist item; fallback is
   dismissing the keyboard on row select.
7. **Old server / new client:** `tier` absent from `picks[]` ⇒ chips render
   without tier (identical to `null`); no crash path.

## 5. File ownership (for cross-group disjointness)

Will touch:

- `mobile/src/screens/MockDraftScreen.tsx` — ticker, chips, filter, search,
  sheet mount (sole owner this wave)
- `mobile/src/components/draft/MockTeamSheet.tsx` — **new**
- `mobile/src/components/draft/MockPoolControls.tsx` — **new** (filter chips +
  search input, kept out of the screen file)
- `mobile/src/api/mockDraft.ts` — `MockPick` type additions
- `backend/mock_draft_service.py` — `state_payload()` only (⚠ shared file
  with G3; see risk 3)
- `backend/tests/test_mock_draft.py` — tier-field pins
- `mobile/tests/check-mock-g2-ui.js` — **new** structural suite
- `docs/api-reference.md` (mock-draft payload `tier` field),
  `docs/cross-client-invariants.md` (add `picks[].tier` to the tier-enum
  consumer locations), this folder's `status.md`

Will **not** touch: `DraftRoomScreen.tsx`, `components/draft/DraftRows.tsx`,
`MockChrome.tsx`, `MockSetupSheet.tsx`, `MockEntryPanel.tsx`,
`backend/server.py`.

## 6. Test plan (per D-056 — Maestro retired; no flows, no sim)

1. **Backend unit (`backend/tests/test_mock_draft.py`):** `picks[].tier`
   present and equal to the `tier_for_elo` walk for a known Elo/position/
   format; `null` for an unvalued player; `my_picks` entries carry it;
   schema stays 1.
2. **Structural (`mobile/tests/check-mock-g2-ui.js`, AST over the real TSX
   like `check-mock-lifecycle.js`):** ticker render source is the ascending
   window helper (no `.reverse()` feeding it); my-pick chip subtree renders
   position and tier nodes with the tier read off `pick.tier` (no
   `tierForElo` call in the chip path); the reset effect is keyed on
   `on_the_clock`'s `pick_no`; search is applied to the filter subset
   (composition order); `MockTeamSheet` mounts as a Modal sibling inside the
   single return; required testIDs exist (`mock-draft.view-team`,
   `mock-draft.pos-filter.*`, `mock-draft.pool-search`).
3. **Transpile-and-call unit halves** (the suite's existing pattern):
   `tickerWindow` ordering + highlight indices at 0, 3, 8, and 20 picks;
   filter+search composition on a fixture pool.
4. **Existing suites stay green:** `check-mock-mode-marker.js`,
   `check-mock-lifecycle.js`, `check-mock-draft-modes.js`,
   `check-mock-user-not-in-draft.js`, `testid-lint`.
5. **Operator TestFlight checklist (runtime proof):** start a mock → ticker
   shows 1.01 at top after round 1; make picks until >8 → earliest rows fall
   off the top, section height constant; chips show slot + position + tier
   and wrap 3-per-row; open "Your team" mid-turn → sheet over the live
   draft, dismiss, still on the clock; filter to RB, draft, filter is back
   to All next turn; search "Jeanty" under a WR filter → no result (scoped),
   under All → found; keyboard up + row tap drafts in one tap; manual-mode
   pass of the same; End/Clear still works.

## 7. Deferred / out of scope

- Recap "+/− vs consensus" column: the server now sends `consensus_delta`,
  but rendering it is not one of these six items — left for a future item.
- Per-team roster view on manual-mode turns for other teams (§3.4).
- Tier labels on ticker/recap rows (#323 asked for "Your picks" only —
  surgical-change principle).
