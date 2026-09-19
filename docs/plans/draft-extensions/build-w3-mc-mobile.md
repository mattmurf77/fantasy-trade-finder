# Build status — W3 M-C: member-entered provenance on priced pick surfaces (MOBILE half)

**Date:** 2026-08-08 · **Wave:** draft-extensions W3 M-C · **Status:** mobile half complete, gates green, **inert until the backend emits `source` and registers `picks.assign_tradeable`**
**Scope owned:** `mobile/` ONLY. A parallel agent owns every backend file (the seven read sites opting in, `_owned_picks_available`, the flag's 4-touch).
**Spec:** [plan.md](plan.md) §6 REVISED + the operator-decisions block · [lld.md](lld.md) §4.5 · [hld.md](hld.md) §329 · the shipped M-A/M-B contract in [build-w3-ma-mb.md](build-w3-ma-mb.md)

> **Contract source:** `build-w3-mc.md` **did not exist** at build time. Everything here is coded against `docs/cross-client-invariants.md`'s `source` vocabulary plus the plan/LLD copy string. Every place the registered contract was incomplete is listed under **Contract gaps** below — those are flags for the backend half, not workarounds hiding a problem.

---

## Headline

D17 — *"provenance is inescapable"* — is implemented as **one component that cannot be rendered wrong**, plus a source-level test that fails if any of the five priced surfaces stops rendering it or lets it drift into a conditional.

Nothing is visible today. `picks.assign_tradeable` is not a key in `config/features.json` (backend-owned), and `useFlag` on an absent key is falsy — so the marker returns `null` everywhere, no priced surface changes, and the flag-off posture is arrived at **fail-closed** rather than by a client default. No new network request is issued on any priced surface.

---

## The design decision that matters

The obvious implementation is `{pick.source === 'user' ? <Marker/> : null}` in five files. That is exactly the shape that rots: five predicates, five chances for one to acquire an extra `&&`, and the failure is invisible — a priced assertion with a suppressed marker looks **identical to platform truth**. There is no error, no empty state, nothing a screenshot would catch.

So the gates live **inside** the component and the hosts render it **unconditionally**:

```tsx
<MemberEnteredMarker source={…} pickId={…} season={…} leagueId={…} testID={…} />
```

`MemberEnteredMarker` returns `null` unless **all** of: `picks.assign_tradeable` is on · `isMemberEntered(source)` (`source === 'user'`, the ONE definition of the predicate) · a `pickId` and a `leagueId` exist to route with. A marker that cannot route is worse than none — it names a problem and hides the fix.

That turns D17 into a **structural** claim about five files, which is what makes `mobile/tests/check-member-entered-marker.js` possible: it parses the real TSX with the project's own TypeScript and walks the JSX tree, exactly like the shipped `check-mock-mode-marker.js`. A grep would pass on a marker that had become conditional.

---

## The five priced surfaces, as found

| # | Surface (plan wording) | File | What renders the price | Marker id |
|---|---|---|---|---|
| 1 | Trade-away picker | `components/PlayerPickerModal.tsx` | `ownerBoardValue(item).toLocaleString()` on a row Pressable | `calc.picker.member-entered.<pick_id>` |
| 2 | Swap-suggestions sheet | `components/SwapSuggestSheet.tsx` | `Math.round(e.value).toLocaleString()` on an option Pressable | `trade-card.swap-option.member-entered.<evener_id>` |
| 3 | Evener chip | `components/EvenerRows.tsx` | `Math.round(e.value).toLocaleString()` on a plain row View | `calc.evener.member-entered.<evener_id>` |
| 4 | Calculator pick rows | `components/TradeSide.tsx` | `valueOf(p).toLocaleString()` on a plain row View | `calc.member-entered.<pick_id>` |
| 5 | Power-rankings draft capital | `screens/LeagueSummaryScreen.tsx` | `Math.round(p.value).toLocaleString('en-US')` in the drill-in `Draft capital` group | `league-summary.member-entered.<pick_id>` |

Notes on what "as found" actually meant:

- **Surface 1 is the calculator's picker, not the deck's.** `PlayerPickerModal` has two hosts. `InLeagueCalculator` feeds it real league picks (both the give and the receive picker); `TradesScreen`'s FB-47 target picker builds its pool from `valueById` — **players only, no picks at all** — so it passes no `leagueId` and has nothing to mark. One component covers "trade-away" and "acquire" together.
- **Surfaces 1 and 4 render `CalcPlayer`, not the pick payload.** The marker there is only as honest as the mapping that builds those objects, so `CalcPlayer` gained `pickSource`/`pickSeason` and `InLeagueCalculator` copies them off `GET /api/league/picks`. The test pins that mapping too — without it both surfaces would silently render assertions as platform truth while every JSX check still passed.
- **Surface 3 is the highest-stakes one.** The evener is the sweetener FTF *actively recommends* ("ask them to add their 2027 1st") — plan §6.4's S4, the one the risk lens wanted held behind a measured gate and the operator opened anyway.
- **Surface 5 feeds the standings.** Draft capital is summed into `total_value`, so a wrong assertion reorders the league table, not just one row.
- `ConsensusVerdictCard` also mounts `EvenerRows` (the open calculator's generic-pick eveners). It has no league and its eveners carry no `source`, so nothing marks there — correct, not an omission.

### Accessibility: the two rows that are accessible containers

Surfaces 1 and 2 render inside a row `Pressable`, which on iOS swallows a nested a11y node (the caveat already documented in `components/CLAUDE.md`). Touch still reaches the nested marker on both platforms, but VoiceOver would not — so those two hosts *also* fold the disclosure into the row's own contract: the same `MEMBER_ENTERED_COPY` sentence is appended to `accessibilityLabel`, and a `correct` `accessibilityActions` entry ("Correct this pick") fires the same deep link. Both are gated by `usePicksTradeable()` + `isMemberEntered()`, so flag-off changes no label. Surfaces 3–5 are plain Views and need none of this.

---

## The correction path

`openPickCorrection(leagueId, pickId, season)` → `navigationRef.navigate('PickAssignment', {leagueId, season, focusPickId})` — the plan's exact triple. `navigationRef` rather than a navigation prop because three of the five surfaces are modals/sheets rendered far from any screen that owns a navigator.

The shipped grid already consumed `focusPickId` (switch season → expand round → highlight row). `season` was **not** on the route type, so the plan's triple could not be expressed; it is now additive on `AuthStack.PickAssignment` and used as the fallback when `focusPickId` is not in the payload — a re-seed with fewer rounds. Without it a stale correction link lands silently on the current season.

---

## Copy

**`Member-entered — not verified with ESPN`**, exported once as `MEMBER_ENTERED_COPY` and never re-typed by a host. The test asserts both halves: the constant equals the registered string, and **no surface file contains the literal** (a hard-coded copy is how three clients start disagreeing).

Chalkline: flare tick (informational highlight — ADR-005; never an action color), 11px `fonts.ui` in `chalk.dim` at the scale floor, one 12px ice chevron for the action. Deliberately quieter than the `type.data` / 13px / `chalk.base` price it qualifies — a marker louder than the number it qualifies gets tuned out — and deliberately not a warning tone: an assigned grid is the *intended* state, not an error.

`_owned_pick_label` is untouched by design (LLD §4.5.3): the display string ("2027 1st") is shared with Sleeper/MFL leagues, so provenance rides its own field.

---

## Also in this commit — assign from the Draft Room (operator, 2026-08-08)

> *"The drafts tab for ESPN leagues tells users to go assign draft picks in the league tab. They should just be able to set the picks directly from the draft page where that message sits."*

Same family of failure as an unmarked assertion: a screen that names a problem and puts the answer somewhere else. Landed on the same branch, gated on **`picks.assign`** (not `assign_tradeable` — this is entry, not trade math).

1. **`NoticeCode` gains `picks_not_assigned`** — the M-B client item that build-w3-ma-mb.md §8 left for "whoever lands M-B's server half" and that build-w3-mobile.md deferred for the same reason. It rides the OPEN `notice.code` set, so `state` stays `unavailable`, `schema` stays `1`, and an older binary renders `notice.message` and behaves correctly.
2. **The notice now OFFERS the job.** Client copy — *"Nobody has set this league's draft picks yet. Set them here and the board fills in."* — over a primary `draft-room.assign-picks` CTA that pushes `PickAssignment`. Unconfigured, not broken, per M-B's explicit instruction.
3. **Partially-assigned is no longer a dead end.** Any assignment makes the server render a *real* board (state B3), so a half-typed grid shows a board with rounds missing and nothing saying so. An assigned board now carries `draft-room.assign-progress` — the shared `pickAssignmentSubline` line + "Continue assigning" / "Edit the draft picks".
4. **Coming back reflects reality.** Returning from either push invalidates `['draft-board', leagueId]` — guarded by a ref so it fires **only** after such a push, never on ordinary focus (an unconditional refetch-on-focus would change behaviour for every league in the app).
5. **The League tab section survives.** This adds an entry point; it does not move one.

**Push, not a sheet — and why.** The grid is a full working surface: four season tabs, collapsible rounds, a drag-to-reorder setup step, and two sheets of its own (the owner picker and the CAS-conflict sheet). iOS will not stack sibling `Modal`s — the constraint that already forced `TradeDnaSheet` to nest its second layer inside one Modal — so presenting the grid as a sheet would have to re-home both of its sheets. A push also inherits the shipped `pick-assignment.back-btn` and the #151 iOS-26 `headerBackVisible:false` workaround, so back is guaranteed live.

**Fail-safe on a stale flag cache:** if the server emits `picks_not_assigned` while the client's flag cache still says off, the copy chain falls through to the server's own sentence — which names the League tab, a path that still works. The screen never describes a fix it cannot offer.

---

## Files changed

| File | Change |
|---|---|
| `src/components/MemberEnteredMarker.tsx` | **NEW.** `MEMBER_ENTERED_COPY`, `isMemberEntered`, `usePicksTradeable`, `openPickCorrection`, and the self-gating marker |
| `src/components/PlayerPickerModal.tsx` | Surface 1: `leagueId` prop, marker in the shared row renderer, row-level a11y label + `correct` action |
| `src/components/SwapSuggestSheet.tsx` | Surface 2: same treatment; the name cell became a stack |
| `src/components/EvenerRows.tsx` | Surface 3: `leagueId` prop + marker |
| `src/components/TradeSide.tsx` | Surface 4: `leagueId` prop + marker |
| `src/screens/LeagueSummaryScreen.tsx` | Surface 5: marker in the Draft-capital rows |
| `src/components/InLeagueCalculator.tsx` | Copies `source`/`season` onto owned-pick `CalcPlayer`s; threads `leagueId` into all four of its priced children |
| `src/screens/TradesScreen.tsx` | Passes `leagueId` to `SwapSuggestSheet` |
| `src/api/pickAssignment.ts` | Exports `PickSource` — one definition of the provenance enum |
| `src/api/league.ts` | `OwnedPick.source`; `picks.items[]` gains `pick_id`/`season`/`source` |
| `src/api/calc.ts` | `CalcEvener` gains `source`/`pick_id`/`season` |
| `src/api/draft.ts` | `NoticeCode` gains `picks_not_assigned` |
| `src/data/tradeCalcMock.ts` | `CalcPlayer` gains `pickSource`/`pickSeason` |
| `src/navigation/RootNav.tsx` | `PickAssignment` params gain `season` |
| `src/screens/PickAssignmentScreen.tsx` | Consumes `season` as the season-tab fallback |
| `src/screens/DraftRoomScreen.tsx` | The operator item: notice CTA, progress row, focus invalidation |
| `tests/check-member-entered-marker.js` | **NEW.** The AST test |
| `package.json` | `test:member-entered-marker` |
| `src/{api,components,navigation,screens}/CLAUDE.md` | Registry rows |
| `docs/cross-client-invariants.md` | **Registers the copy string** — see Contract gaps |

---

## Test — how the marker is enforced

`node tests/check-member-entered-marker.js` (`npm run test:member-entered-marker`). Parses real TSX with the project's TypeScript and walks the JSX tree. Per priced surface it asserts:

1. The marker is rendered **in the same row as the price** — located structurally as the innermost JSX ancestor that also contains a `.toLocaleString(` call. D17 is scoped to *priced* surfaces; a marker elsewhere on the screen does not discharge it.
2. It is **UNCONDITIONAL** within that row (no enclosing `?:`, `&&` or `??`).
3. It is passed all four things it needs to disclose **and** to route: `source`, `pickId`, `season`, `leagueId`, plus a `testID`.
4. The file **imports** the shared component and does **not** hard-code the copy.

Plus: the constant equals the registered string; `isMemberEntered` tests `source === 'user'`; `usePicksTradeable` reads exactly `picks.assign_tradeable`; the component's `return null` guard requires **both**; the marker is itself the tap target; `openPickCorrection` carries all three link fields; `InLeagueCalculator` copies `source`/`season` onto `CalcPlayer`; the route still accepts the params. A final section pins the Draft Room's assign-in-place affordances.

**Verify-failing-first.** Seven mutations were applied to the passing tree and each confirmed **RED** before the test was accepted:

| # | Mutation | Result |
|---|---|---|
| 1 | Marker drifts inside a `cond ? … : null` (EvenerRows) | RED |
| 2 | Marker deleted from one surface (TradeSide) | RED |
| 3 | Registered copy re-worded | RED |
| 4 | `pickSource: p.source` stops being copied onto `CalcPlayer` | RED |
| 5 | Flag gate removed from the marker | RED |
| 6 | A surface hard-codes the copy instead of importing it | RED |
| 7 | Marker loses its `pickId` (renders but cannot route) | RED |

Baseline restored ⇒ GREEN.

---

## Gates

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **clean** |
| `node tests/check-member-entered-marker.js` | **all checks passed** (7/7 mutations verified red first) |
| `node tests/check-mock-mode-marker.js` | passed — W2's contract untouched |
| `node tests/check-feedback-badge.js` · `check-session-rerank.js` | passed |
| `python3 -m pytest backend/tests -q` | **1927 passed, 1 skipped, exit 0** — the stated baseline, exactly |
| `git status --porcelain -- backend/ config/` | **empty** — zero backend files touched |

*(The worktree has no `mobile/node_modules`; the typecheck and node tests ran against the main checkout's install via a symlink, removed afterwards.)*

---

## Contract gaps — where the delivered backend contract did not carry `source`

`build-w3-mc.md` does not exist, so these are open items for the backend half rather than settled disagreements. **Every one of them fails safe**: an absent `source` simply means nothing is marked.

| # | Where | Gap | Client position |
|---|---|---|---|
| **G1** | `docs/cross-client-invariants.md` | **The copy string was never registered.** The §"Asserted pick ownership" paragraph (landed by the M-A backend agent) says clients "MUST surface the `source` field" but nowhere states *what they say*. The exact sentence lived only in `plan.md` §6.5 and `lld.md` §4.5.3 — i.e. in plans, not in the cross-client contract the three clients are supposed to share. **Registered by this build** as its own paragraph, including the flag, the five surfaces and the `_owned_pick_label` separation. If the backend agent registers it too, resolve by union-dedupe |
| **G2** | plan.md | The brief cited a *"Design-pass corrections"* block in `plan.md`. **No such block exists** anywhere in `docs/` (grep-verified). Built against §6 REVISED + the operator-decisions block, which are present and binding |
| **G3** | `GET /api/league/picks` | `OwnedPick` carries **no `source`** today (M-C is unbuilt). Typed as optional; surfaces 1 and 4 mark nothing until it ships. **`season` is already present**, so the correction link is complete the moment `source` appears |
| **G4** | `POST /api/trade/evaluate` → `eveners[]` | `CalcEvener` carries **no `source`, no `season`, no `pick_id`** — `id` is the `pick_id` for a single-pick evener, but there is no provenance and no season. Both surfaces 2 and 3 depend on this; **it is the largest gap**, and it covers S3/S4, the sites the operator deliberately opened. Typed all three as optional. `season` matters: without it a correction link can still route by `pick_id`, but a stale link loses its season fallback |
| **G5** | `GET /api/league/power-rankings` → `teams[].picks.items[]` | Items are `{label, value}` only — **no `pick_id`, no `season`, no `source`**. Surface 5 cannot mark or route without at least `pick_id` + `source`. Typed as optional; the testID falls back to the label so the id stays stable if only `source` ever lands |
| **G6** | flag registry | **`picks.assign_tradeable` is not a key** in `config/features.json` (build-w3-ma-mb.md §21: "do not reference it from a client"). Referenced anyway — deliberately: `useFlag` on an absent key is falsy, so this is the *fail-closed* posture, and wiring it now means the client half needs no second pass when the backend 4-touches the flag |
| **G7** | contested / orphaned | The plan withholds contested and orphaned slots from priced payloads by **row filter**, so they should never reach these five surfaces at all. The client therefore has **no contested branch** on a priced surface — if one ever appears, it will render as a normal marked pick. That is the correct client posture (the filter is the invariant), but it means a backend regression here would be invisible to mobile |

---

## Not built here (by scope)

- The seven read sites opting in, `_owned_picks_available`, `_has_assigned_picks`, `picks_supported` as a data test, and the `picks.assign_tradeable` 4-touch — **backend half**.
- The web + extension copies of the marker. The string is now registered in `docs/cross-client-invariants.md` for them.
- Maestro flows. Every affordance carries a testID in the shipped grammar; note the iOS accessible-container caveat on surfaces 1 and 2 (assert via the row's a11y label).
- M-D live offline recording (`draft.manual_picks`, separate wave).
