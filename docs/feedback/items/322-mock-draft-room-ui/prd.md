# G2 PRD — Mock draft room UI (#322–#327)

> Build-ready spec for group G2 of the 2026-08-16 feedback wave. Polish path:
> this PRD + [`scope.md`](scope.md) are the deliverables — no separate
> lld-delta.md is owed, so **§2 carries the full API contract delta**.
> Derived from [`plan.md`](plan.md); every code claim re-verified against
> `origin/main` @ `d3fe3ac` (v1.13.4). Verification notes in §7.
> Batch context: [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> **Round 2 (2026-08-16):** incorporates the critic's round-1 review
> ([`review-round-1.md`](review-round-1.md)) — dispositions in
> [`reconciliation-log.md`](reconciliation-log.md). Headline changes: §3 now
> states the TRUE G2/G3 overlap and the Phase-2 serialization order; T-S9 is
> scoped and the `sinceUserPick` manual-mode consequence is stated (R-4).

All six items are screen `MockDraft` (`mobile/src/screens/MockDraftScreen.tsx`).
Platforms: mobile, plus one additive backend payload field (§2). QA regime:
D-056 (Maestro/simulator retired 2026-08-15) — structural suites + unit tests
+ operator TestFlight checklist.

## 1. Requirements

Each requirement names its feedback item(s) and its test(s); tests are defined
in §5. Chalkline applies throughout (`docs/design/design-system.md` +
`docs/design/components.md`): no emoji icons, no gradients, radius ≤ 8px,
no text below 11px.

### Ticker (#322, #325 — one section, per operator decision)

- **R-1 — Ascending window.** The "Just picked / Since your last pick" ticker
  renders the last `TICKER_DEPTH` (8) picks **ascending by `pick_no`** —
  earliest of the window at top, newest at bottom. The render source is a new
  pure helper `tickerWindow(picks, depth, newest)` (new file
  `mobile/src/utils/tickerWindow.ts`) returning `{ rows, firstNewIndex }`
  where `rows = [...picks].sort((a, b) => a.pick_no - b.pick_no).slice(-depth)`.
  `picks[]` arrives in pick order today by construction (`next_pick` walks
  slots sequentially), but nothing pins that server-side — the defensive
  ascending sort inside the helper makes the window's ordering a *local*
  guarantee instead of an unpinned assumption (NB-2), replacing the current
  `[...picks].reverse().slice(0, TICKER_DEPTH)` (`MockDraftScreen.tsx:734`
  @ d3fe3ac). Items: #322, #325. Tests: T-U1, T-S1, T-F1/T-F2.
- **R-2 — Growth phase at draft start.** With fewer than 8 picks made, the
  section renders exactly `min(picks.length, 8)` rows — 1.01 is literally the
  top row from the first pick on. No placeholder rows, no reserved empty
  space. It grows one fixed-height row per pick until it holds 8. Items:
  #322, #325. Tests: T-U1 (0- and 3-pick cases), T-F1.
- **R-3 — Fixed height in steady state.** From the 9th pick on, the section's
  height is constant: each new pick appears at the bottom and the earliest
  visible row falls off the **top**. No animation — the CPU tail arrives as
  one mutation response (up to 8 rows change at once). Item: #325. Tests:
  T-U1 (20-pick case), T-F2.
- **R-4 — Highlight re-derivation.** The "new since your last pick" tint
  currently keys on `i < newest` (newest-first order,
  `MockDraftScreen.tsx:748`). In ascending order the new rows sit at the
  bottom: row `i` is tinted iff not mine and
  `i >= rows.length - min(newest, rows.length)` — i.e.
  `firstNewIndex = rows.length - min(newest, rows.length)`, computed inside
  `tickerWindow` so the off-by-one lives in one tested place (`newest === 0`
  ⇒ `firstNewIndex === rows.length` ⇒ no row tinted). The "mine" tint
  (`picked_by_user_id === userOwnerId`) is order-independent and unchanged.
  Unchanged: `TICKER_DEPTH = 8` (:101), header copy ("Since your last pick"
  when `newest > 0`, else "Just picked", :738), row layout, testIDs
  `mock-draft.ticker-row.<pick_no>` (:744).
  **Also deliberately unchanged: `newest`'s source.** `newest` is fed by
  `sinceUserPick` (`MockDraftScreen.tsx:408–:413`), which finds the user's
  last pick via `p.by === 'user'`. G2 does not touch it (surgical-change
  principle — none of the six items asks to redefine "since your last
  pick"). **Stated consequence:** in manual mode every pick is
  `by: 'user'`, so `newest` is always 0 — the header reads "Just picked"
  and no new-pick tint ever renders. Defensible (the user makes every pick
  and is never away from the room), and T-F8 tests exactly this. The
  `picked_by_user_id`-based re-derivation ("since your *team's* last
  pick") is a real alternative but a behavior change beyond these items —
  logged as deferred (§4, reconciliation log B-2). Items: #322, #325.
  Tests: T-U1, T-S1/T-S2, T-F1.

### Tier + position on "Your picks" chips (#323)

- **R-5 — Server-computed tier on `picks[]`.** `state_payload()`
  (`backend/mock_draft_service.py:1328`) adds a `"tier"` key to every
  `picks[]` entry (and therefore every `my_picks[]` entry — `my_picks` is a
  filter of the same list, :1413). Full contract in §2. The value is
  `RankingService.tier_for_elo(ctx.consensus_elo.get(player_id), position,
  ctx.scoring_format)` — the standing band walk every other server tier
  consumer uses (`backend/ranking_service.py:1272` @ d3fe3ac, a
  `@classmethod`; `tier_for_elo` guards `elo is None` and returns `None`).
  Both inputs already live on `MockContext` (`consensus_elo` :398,
  `scoring_format` :412) — **no `server.py` change.** `ranking_service` is a
  **NEW import** into `mock_draft_service` (today: stdlib +
  `draft_board_service` only). This preserves INV-10's stance:
  `ranking_service` imports only stdlib (no backend-package imports, so no
  cycle) and loads the checked-in `tier_config.json` once at module import —
  a module `server.py` already imports at boot; the per-pick walk is pure
  and in-memory, so "zero platform egress after creation" is untouched. The
  build also extends `mock_draft_service.py`'s own header note (:41–:44,
  the INV-10 block) the same way scope.md §4 amends the architecture.md row,
  so the "performs no I/O of any kind" claim stays honest where the next
  reader looks first. Item: #323. Tests: T-P1…T-P4.
- **R-6 — Mobile type additions.** `MockPick`
  (`mobile/src/api/mockDraft.ts:68`) gains `tier: Tier | null` plus the
  already-emitted-but-untyped `consensus_rank: number | null`,
  `consensus_delta: number | null`, `valued: boolean` (typing only — no new
  UI for the consensus fields, plan §7 defers rendering them). All four are
  optional-safe against an old server (absent ⇒ treated as `null`/`false`).
  Item: #323. Tests: T-S3 (type presence via structural grep), tsc.
- **R-7 — Chip rendering through the shared tier components.** A made pick's
  chip renders: the slot numeral (`pickLabelOf(slot)`, unchanged) plus a meta
  line of position (colored via `positionOf`, the existing import) and the
  tier via the existing `TierBadge` component (`mobile/src/components/
  TierBadge.tsx` — it maps the enum through its `TIER_LABEL` record and
  **returns `null` for a falsy tier**, so `null`/absent ⇒ no badge, never a
  fabricated one — exactly the cross-client rule), then the player surname
  (`lastName`, unchanged). The client **never** derives a tier from Elo,
  rank, or label — the structural suite asserts no `tierForElo` call in the
  screen. Unpicked future slots keep today's states ("on the clock" /
  "from {team}") with no position/tier. Item: #323. Tests: T-S3, T-F3.

### Chip grid layout (#324 — operator delegated the layout to this spec)

- **R-8 — Fixed 3-per-row equal-width grid; wrap, never an inner scroll.**
  `styles.myPicksRow` already wraps (`flexWrap: 'wrap'`, :1021 — #324 as
  filed does not reproduce; this requirement is the layout spec for the
  redesigned chip). Chips become equal-width three-across
  (`flexBasis`-based), `minHeight ≥ 44` — for vertical rhythm and
  two-line-content headroom only; the chips are **non-interactive**, so this
  is not a touch-target requirement — 1px `flare.base` border (chips are
  the user's own picks — flare is the informational accent, ADR-005), radius
  `radii.xs` (2 — the badges/chips token), `space.sm` (8) gaps, `space.sm`/
  `space.xs` internal padding. Text: slot numeral in the existing data style;
  meta line at `type.bodySm` (13px) with `TierBadge`'s own `type.label`
  (11px) — nothing below the 11px floor — all `numberOfLines={1}`. Width
  math at the 375pt baseline: 375 − 2×`space.lg`(16) − 2×`space.sm`(8) ⇒
  ~109pt per chip. N picks ⇒ ⌈N/3⌉ rows, always fully rendered; **no
  internal scroll at any count** (a nested scrollable is the gesture-capture
  class that broke TestFlight builds #11/#12 — lessons.md 2026-07-12).
  Item: #324. Tests: T-S4, T-F3.

### Team sheet + position filter (#326)

- **R-9 — `MockTeamSheet` modal.** New component
  `mobile/src/components/draft/MockTeamSheet.tsx`, a Modal bottom sheet per
  components.md § Sheets (`--ink-2` fill, top radius `--r-md` (8), 1px
  `--line` border, solid scrim `rgba(9,10,8,0.78)` — no blur, 32×4 grabber).
  Mounted as a sibling of the existing `PlayerContextMenu` (:621) and
  `AnchorSheet` (:627) modals, after the ScrollView, **inside the screen's
  single return** — no new mock branch, so `check-mock-mode-marker.js` and
  `check-mock-lifecycle.js` contracts hold. Entry: a "Your team" ice text
  link on `OnTheClockCard` (:657), testID `mock-draft.view-team`, rendered
  on every active turn. Dismiss via grabber/scrim/close; the screen never
  unmounts. Item: #326. Tests: T-S5, T-F4.
- **R-10 — Sheet content: two sections.** A SectionList in the
  `SwapPlayerSheet` sectioned-picker construction (TickLabel banners; rows =
  position chip + name + right-aligned data value):
  1. **Roster** — the user's real dynasty roster grouped by position, from
     the shared power-rankings read (react-query key
     `['league-power-rankings', leagueId, 'consensus']` — the same source
     `InLeagueCalculator.tsx:157` uses, usually already cached; grouping
     keys on the caller's league identity via `myOwnerId` per ADR-012).
     Loading/error get honest one-line copy inside the sheet — no spinner
     states beyond the standing pattern.
  2. **Drafted in this mock** — `my_picks` rendered with R-7's position +
     tier. Distinct banners keep real-roster vs simulation legible.
  v1 always shows the *session user's* team, including manual-mode turns
  taken for another team (per-team rosters deferred, plan §7). Item: #326.
  Tests: T-S5, T-F4.
- **R-11 — Position filter row.** A segmented chip row above the undrafted
  list — All · QB · RB · WR · TE — in the PositionTabs construction
  (hairline group; active segment `--ink-3` well + position-color underline,
  ice for All; precedent: `FreeAgentsScreen.tsx:158`). testIDs
  `mock-draft.pos-filter.<all|qb|rb|wr|te>`. The undrafted list's render
  source becomes `filterPool(state.undrafted, position, query)` — a new pure
  helper (new file `mobile/src/utils/mockPool.ts`) that applies the position
  filter and then the search, so the composition lives in tested code, not
  inline screen JSX (NB-3). The tap-to-draft flow through rows and the
  confirm bar is unchanged. A player whose position is outside the four
  (edge case) appears
  only under All. Zero matches ⇒ honest line ("No RBs left on the board")
  with the All chip still present to clear. Item: #326. Tests: T-S6, T-U2,
  T-F5.
- **R-12 — Reset on turn advance (operator decision).** A `useEffect` keyed
  on `on_the_clock?.pick_no` resets the filter to All **and clears the
  search (R-13)** whenever the clock advances, in both modes — a stale
  narrow view silently hiding the pool on a new turn is the trap this kills.
  Items: #326, #327. Tests: T-S7, T-F5.

### Pool search (#327)

- **R-13 — Search input.** A `TextInput` between the filter row and the
  list, per `PlayerPickerModal`'s search construction (`--ink-1` fill,
  hairline border, radius `radii.sm`), testID `mock-draft.pool-search`, with
  a clear (`×`) affordance. Case-insensitive substring match on player name;
  no debounce (in-memory list). **Scope (operator decision): search filters
  the currently active position-filter subset** — composition order is
  filter first, then search, enforced inside `filterPool` (R-11) rather
  than by screen-code ordering. Resets on every turn per R-12. Item: #327.
  Tests: T-S6, T-U2, T-F6.
- **R-14 — Keyboard behavior.** The screen's ScrollView gets
  `keyboardShouldPersistTaps="handled"` so a row tap while the keyboard is
  up drafts in one tap; the confirm bar must be verified above the keyboard
  on-device (T-F7 — fallback if occluded: dismiss the keyboard on row
  select). Item: #327. Tests: T-F7.

### Analytics (#326, #327 — see scope.md §1 for the full spec)

- **R-15 — Three new events**, registered backend-first per the mock-family
  precedent (`backend/analytics_taxonomy.py:254–266` + `:841–862`):
  `mock_team_sheet_opened`, `mock_pool_filtered`, `mock_pool_searched`.
  Emitted from mobile via the screen's existing `track` import. Proposed —
  **needs operator sign-off** (new analytics events are a bright-line
  surface). Tests: T-S8.

### Manual-mode invariant (all items)

- **R-16 — "Mine" keys on `settings_echo.user_owner_id`, never `by`.**
  Chips, sheet, and ticker "mine"-tint logic — the predicates G2 adds or
  changes — reuse `resolveUserOwnerId` (`MockDraftScreen.tsx:896`);
  regressions here re-open #305. (`sinceUserPick`'s `by` keying is outside
  this rule and deliberately untouched — R-4.) Tests: T-S9, T-F8.

## 2. API contract delta — `picks[].tier` (the one backend change)

`GET/POST /api/mock-draft` (+ `/pick`) state payload, built by
`mock_draft_service.state_payload()` (:1328):

| Aspect | Spec |
|---|---|
| Field | `picks[].tier` — and therefore `my_picks[].tier` (`my_picks` is `[p for p in picks if …]`, :1413; the entries are the same dicts) |
| Type | `string \| null` |
| Enum values | Exactly the 8-rung cross-client Tier ladder, verbatim: `"firsts_4plus"`, `"firsts_3"`, `"firsts_2"`, `"first_1"`, `"second"`, `"third"`, `"fourth"`, `"waivers"` (`ORDERED_TIERS`, `backend/ranking_service.py`; `docs/cross-client-invariants.md`). No new enum, no new labels. |
| Computed | `RankingService.tier_for_elo(ctx.consensus_elo.get(str(pick["player_id"])), position, ctx.scoring_format)` at payload-build time — the same band walk as every other server tier consumer. Frozen inputs ⇒ stable across reads of the same mock. |
| Nullability | `null` when the walk returns `None`: the player has no consensus Elo (`ctx.consensus_elo` has no entry — the `valued: false` rows), or his Elo sits below the `waivers` floor (1150 ⇒ unranked). `null` means "show no tier", **never** a fabricated one. |
| Basis-independence | The tier is computed from `ctx.consensus_elo` **always** — it does NOT switch to `board_elo` when `basis=my_board`. `state_payload`'s `basis` parameter re-sorts the *undrafted* list only; a pick's tier is a property of the pick, stable across basis toggles and across reads of the same mock. Accepted consequence, deliberately: a player the user saw badged under My board (the client-side walk over the user's board Elo, the room's #277 path) may show a *different* tier on the chip after drafting — chip tiers are consensus-denominated because they must not flip when the user toggles basis. The build agent must NOT wire `board_elo` into the tier computation. |
| When absent | Only from a pre-change server. Clients MUST treat absent identically to `null` (render no tier — `TierBadge` already no-ops on falsy). |
| Schema | `"schema"` stays `1` (`SCHEMA`, `mock_draft_service.py:57`) — additive key under the plan-D10 open-payload convention; the client type is open and unknown keys are ignored. Note: the plan calls this constant `MOCK_DRAFT_SCHEMA`; its real name is `SCHEMA`. |
| Docs | `docs/api-reference.md` § Mock draft payload table gains the field row; `docs/cross-client-invariants.md` § tier-enum Locations gains `picks[].tier` as a consumer (the enum semantics and the null-⇒-hidden rule are already stated there — no rule change). |

## 3. Shared-file boundary with G3 (#328) — Phase 2 is SERIALIZED, not disjoint

**Correction (round 2, B-1):** this section previously claimed function-level
disjointness. That was wrong against G3's actual plan — G3 edits
`state_payload()` itself and both of G2's mobile files. The true overlap is
**five shared files, one shared function**; the *regions* within them are
non-overlapping. Region ownership (language mirrored in G3's PRD §4):

| File | G3 owns (reserved regions) | G2 owns |
|---|---|---|
| `backend/mock_draft_service.py` | Module constants block (`ORDER_SOURCE_*` / new `OWNERSHIP_SOURCE_*`, :67–68); `build_settings()` (:995); **`state_payload()`'s `settings_echo` dict** (:1414 block — the `ownership_source` echo lands here) | **`state_payload()`'s pick-dict build loop** (:1373–:1400, the `picks.append` dict at :1378 — the `tier` key) and the module import block (`ranking_service`) + header note. G2 must NOT modify G3's three regions |
| `mobile/src/screens/MockDraftScreen.tsx` | Ownership disclosure caption helper + its two mounts (clock card + recap card, G3 lld §4.2) | Everything else G2 specs: ticker, chips, filter/search controls, sheet mount, reset effect |
| `mobile/src/api/mockDraft.ts` | `MockOwnershipSource` type + `MockSettingsEcho.ownership_source` | `MockPick` additions (`tier`, `consensus_rank`, `consensus_delta`, `valued`) |
| `backend/tests/test_mock_draft.py` | G3's T-1…T-11 additions | G2's T-P1…T-P4 additions |
| `docs/api-reference.md` § Mock draft payload block; `docs/cross-client-invariants.md` | G3's `ownership_source` rows | G2's `picks[].tier` rows |

`backend/server.py`: G3 touches it (create-path wiring); G2 does not — that
file is genuinely single-owner.

**Serialization requirement (orchestrator's Phase-2 decision — binding on
both build agents): G3 builds and merges FIRST. G2's build agent branches
from the group branch AFTER G3's merge and rebases G2's regions on G3's
edits.** Concretely for the G2 builder: `state_payload()` will already carry
the `settings_echo.ownership_source` echo — add the pick-loop `tier` key
without touching that dict; `MockDraftScreen.tsx` will already mount the
ownership caption — add G2's controls around it; `mockDraft.ts` will already
declare the ownership types — extend `MockPick` alongside them. The regions
are non-overlapping, so the rebase is mechanical, but the *claim* is
serialization, not disjointness. The batch disjointness table carries the
corrected rows.

## 4. Out of scope

- **G3 (#328)** — mock pick-ownership assignment (region split in §3; G3
  builds first).
- Re-deriving `sinceUserPick` off `picked_by_user_id` ("since your *team's*
  last pick" — the #305-consistent reading): a real candidate, but a
  behavior change beyond these six items — deferred deliberately (R-4,
  reconciliation log B-2).
- **G6** — the trade-presentment backend; no shared files with G2.
- Rendering `consensus_rank` / `consensus_delta` (the recap "+/− vs
  consensus" column): the server already sends them (since 1.13.3); R-6
  types them, nothing renders them. Future item.
- Per-team roster views on manual-mode turns for other teams.
- Tier labels on ticker or recap rows — #323 asked for "Your picks" only
  (surgical-change principle).
- No changes to: `DraftRoomScreen.tsx`, `components/draft/DraftRows.tsx`,
  `MockChrome.tsx`, `MockSetupSheet.tsx`, `MockEntryPanel.tsx`,
  `backend/server.py`, any feature flag, any DB table.

## 5. Test plan (D-056: no Maestro, no simulator)

Per the 2026-08-10 rule (feedback lessons.md), every behavioral test names
its SABOTAGE — the deliberate break, applied and reverted during test
authoring, that proves the test can fail.

### 5.1 Backend pytest — `backend/tests/test_mock_draft.py` (additions)

| ID | Test | SABOTAGE |
|---|---|---|
| T-P1 | `test_state_payload_picks_carry_tier` — a valued pick's `tier` equals `RankingService.tier_for_elo` over the same (elo, position, format) inputs, for a fixture player in a known band | emit tier from `pick_no` parity instead of the walk |
| T-P2 | `test_state_payload_tier_null_when_unvalued` — a player absent from `consensus_elo` gets `tier: None` (and keeps `valued: False`) | default missing Elo to `"waivers"` |
| T-P3 | `test_my_picks_rows_carry_tier` — each `my_picks[]` entry is the same dict as its `picks[]` twin, `tier` included | rebuild `my_picks` dropping the key |
| T-P4 | `test_schema_still_1` — payload `"schema" == 1` with the new key present | bump `SCHEMA` to 2 |

### 5.2 Pure-helper unit tests (transpile-and-call, the existing suite pattern)

| ID | Test | SABOTAGE |
|---|---|---|
| T-U1 | `tickerWindow` at 0, 3, 8, and 20 picks × `newest` ∈ {0, 2, 9}: rows ascending by `pick_no`, length `min(n, 8)`, `firstNewIndex` correct at every combination (incl. `newest = 0` ⇒ no tint; `newest > rows.length` ⇒ all tinted); plus a deliberately shuffled input ⇒ rows still ascending (the R-1 defensive sort) | reintroduce `.reverse()`; separately, flip `>=` to `>` in the boundary; separately, drop the sort (the shuffled case must fail) |
| T-U2 | `filterPool` composition on a fixture pool (QB/RB/WR/TE rows): RB filter + a QB-only name ⇒ empty; All + same name ⇒ found; case-insensitive substring; empty query ⇒ filter subset unchanged | compose search over the full pool instead of the filter subset |

### 5.3 Structural suite — NEW `mobile/tests/check-mock-g2-ui.js`

AST over the real TSX with the project's TypeScript, like
`check-mock-lifecycle.js`. Assertions:

1. `PickTicker`'s row map iterates `tickerWindow(...)` output; no
   `.reverse()` anywhere in the ticker path; no `slice(0,` over `picks`.
   (T-S1)
2. The `tickerRowNew` style application references the helper's
   `firstNewIndex` — no inline `i < newest` predicate survives. (T-S2)
3. The my-pick chip subtree renders a `TierBadge` element whose `tier` prop
   is a member read of `pick.tier`, and the screen contains **no**
   `tierForElo` call and no import of it from `utils/tierBands` — the tier
   is never client-derived. The subtree also renders position through
   `positionOf`. `MockPick` declares `tier` in `mobile/src/api/mockDraft.ts`.
   (T-S3)
4. The chip style is a three-across `flexBasis` construction and no
   ScrollView/FlatList wraps `myPicksRow` (no nested scroll). (T-S4)
5. `MockTeamSheet` is rendered Modal-based, as a sibling after the
   ScrollView, inside the screen's single top-level return; testID
   `mock-draft.view-team` exists on the `OnTheClockCard` subtree and
   `mock-draft.team-sheet` on the sheet. (T-S5)
6. The undrafted list's render source is `filterPool(...)` output — the
   screen applies no inline position/search predicate of its own (the
   composition order lives in the T-U2-tested helper); testIDs
   `mock-draft.pos-filter.all/.qb/.rb/.wr/.te` and `mock-draft.pool-search`
   exist. (T-S6)
7. A `useEffect` dependency array contains `on_the_clock`'s `pick_no`
   member read, and its body resets both the filter state and the search
   state. (T-S7)
8. The screen `track`s the three R-15 event names (string-literal check) —
   skipped if the operator declines the events. (T-S8)
9. **Scoped to the regions G2 adds or changes** (chip meta line, sheet
   my-team logic, ticker mine-tint): each resolves through
   `resolveUserOwnerId` / `settings_echo.user_owner_id`, and no `by ===`
   comparison appears in any of *those* predicates. Explicitly EXCLUDED:
   `sinceUserPick` (:408–:413) keeps its `by === 'user'` keying — untouched
   per R-4, and the suite must not flag it. (T-S9)
10. The screen imports no `PanResponder` / `react-native-gesture-handler`
    (the builds-#11/#12 gesture class). (T-S10)

Each structural assertion is proven-failable the same way: apply the
corresponding sabotage from §5.1/§5.2 (or, for 5/9/10, temporarily violate
the shape) and watch the suite go red before reverting.

### 5.4 Existing suites stay green

`check-mock-mode-marker.js`, `check-mock-lifecycle.js`,
`check-mock-draft-modes.js`, `check-mock-user-not-in-draft.js` (all four
exist at d3fe3ac), `mobile/scripts/testid-lint.sh`, `tsc`.

### 5.5 Operator TestFlight checklist (runtime proof, per D-056)

| # | Step | Expected |
|---|---|---|
| T-F1 | Start a CPU mock; watch round 1 arrive | Ticker shows 1.01 as the TOP row; rows read downward in pick order; rows since your last pick are tinted at the bottom |
| T-F2 | Draft past 8 total picks | Earliest rows fall off the TOP; section height stops changing once 8 rows are held |
| T-F3 | Make 4+ picks; inspect "Your picks" | Chips show slot + position (position color) + tier badge + surname; 3 chips per row, wrapping to new rows; no chip missing a tier unless the player is unvalued (then no badge, no placeholder) |
| T-F4 | On the clock, tap "Your team" | Sheet opens over the live draft with Roster (grouped by position) and "Drafted in this mock" sections; dismiss via scrim; still on the clock, state intact |
| T-F5 | Filter to RB; draft a player | Pick succeeds; on your next turn the filter is back on All |
| T-F6 | Under a WR filter, search a known RB's name; then switch to All | No result under WR (search scopes to the filter); found under All; × clears; next turn the box is empty |
| T-F7 | With the keyboard up, tap a player row | Drafts in one tap; confirm bar visible above the keyboard |
| T-F8 | Repeat T-F3–T-F6 in a MANUAL mock, including a turn taken for another team | "Your picks"/"Your team"/ticker "mine" tint all track the user's own team only. Expected in manual mode: the header always reads "Just picked" and NO new-pick tint renders (structural — every pick is `by: 'user'`, so `newest` is 0; see R-4). Not a bug |
| T-F9 | End/Clear the mock | Recap and dismissal behave exactly as on 1.13.4 (no regression) |
| T-F10 | Airplane-mode relaunch into an active mock (old-payload guard is server-side; this checks render resilience) | Screen renders; any pick row without `tier` simply shows no badge |

## 6. New/changed testIDs

`mock-draft.view-team`, `mock-draft.team-sheet`,
`mock-draft.pos-filter.all|qb|rb|wr|te`, `mock-draft.pool-search` (+ its
clear affordance if separately targetable). All must pass
`mobile/scripts/testid-lint.sh`. No existing testIDs are renamed.

## 7. Verification notes — plan claims checked against d3fe3ac

Everything load-bearing verified true; three precision corrections, no data-flow
change (Polish path stands):

1. **Constant name:** the backend schema constant is `SCHEMA` (= 1,
   `mock_draft_service.py:57`); `MOCK_DRAFT_SCHEMA` (= 1) is the *mobile*
   pin (`mobile/src/api/mockDraft.ts:26`) — the plan's name referred to the
   client side. Same convention (plan D10), same guarantee on both ends.
2. **Type token:** `type.bodySm` is **13px**, not 11px — 11px is the
   design-system type floor and `TierBadge`'s internal `type.label` size.
   R-8 uses the correct tokens; nothing lands below the floor.
3. **New import not flagged by the plan:** `ranking_service` into
   `mock_draft_service` is a new module edge. Verified safe for INV-10
   (stdlib-only module, config read at import, pure runtime walk) and
   recorded in the docs table (architecture row, scope.md §4).

Also verified: ticker/highlight/chip/undrafted/search claims at the exact
cited lines; `my_picks` is a filter of `picks` (:1413); `consensus_rank`/
`consensus_delta`/`valued` already emitted (:1393–:1399) and untyped on
mobile; `ctx.scoring_format` exists (:412) so no `server.py` change is
needed; `TierBadge` no-ops on falsy tier; the four `check-mock-*.js` suites,
`test_mock_draft.py`, and `testid-lint.sh` all exist; the power-rankings
query key matches `InLeagueCalculator.tsx:157`; `origin/main` has advanced
past d3fe3ac (to `0b2dcee`) but **none of the G2-touched files changed** in
between, so the analysis holds on the branch-from-origin/main convention.
