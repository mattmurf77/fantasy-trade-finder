# Status — #299 (32pt League roster tiles) + #302 (drill-in back affordance)

**Date:** 2026-08-11 · **Branch:** `feedback-build-league-299-302` · **Base:** `origin/main` @ `ab9368f`
**Verification:** static only (no simulator, no Maestro run) — see [Ship gate](#8-what-is-not-verified) and `scope.md` §5.

## Table of Contents

- [1. What changed, at file:line](#1-what-changed-at-fileline)
- [2. Measured geometry — before / after](#2-measured-geometry--before--after)
- [3. Right-cluster room, and the #300 chevron question](#3-right-cluster-room-and-the-300-chevron-question)
- [4. How the shared `PlayerCard` change was scoped — and the proof](#4-how-the-shared-playercard-change-was-scoped--and-the-proof)
- [5. Verification output](#5-verification-output)
- [6. Sabotage proof — 30 assertions, 30 falsifications](#6-sabotage-proof--30-assertions-30-falsifications)
- [7. Proposed shared-doc edits (orchestrator applies)](#7-proposed-shared-doc-edits-orchestrator-applies)
- [8. What is NOT verified — QA checklist](#8-what-is-not-verified--qa-checklist)
- [9. Where the decisions doc needs a correction](#9-where-the-decisions-doc-needs-a-correction)

---

## 1. What changed, at file:line

### `mobile/src/components/PlayerCard.tsx`

| Line | Change | Why |
|---|---|---|
| `:61-74` | New opt-in prop `denseSingleLine?: boolean` + its contract comment | The League caller passes no `statsSlot`, so the dense row's line 2 held one badge and nothing else. Opt-in, not a change to the shared `dense` branch — Tiers rows are pressable *and* drag-liftable (44pt binds there) and both other callers pass a `statsSlot`. |
| `:122` | Destructured with default `false` | Every existing caller keeps today's behaviour by omission. |
| `:222` | `denseSingleLine && styles.cardDenseSingle` added to the dense style array | The height override. Declared-but-unapplied is the regression this pins (sabotage S3). |
| `:262-271` | Line 2 (`styles.denseLine2`) rendered only when **not** single-line | There is no line 2 at 32pt; an unconditional one clips. |
| `:281-293` | Right cluster gains a row variant and takes the tier badge **before** `posRank` | The operator's literal spec: tier value "to the left of the position". Outer condition widened from `posRank ?` to `posRank \|\| (denseSingleLine && tier) ?` — for every other caller `denseSingleLine` is `false`, so it evaluates to exactly `posRank` as before. |
| `:466-474` | New style `cardDenseSingle: { height: 32 }` | 32 is derived: the tallest row element is `TierChalkBadge` = `Badge` at `type.label` lineHeight 14 + `paddingVertical` 2×2 + `borderWidth` 1×2 = **20pt**, plus 6pt above and below. |
| `:527-536` | New style `denseNumsRow` (row, `alignItems: center`, `gap: space.sm`) | Lays the cluster out horizontally. `flexShrink` left at the RN default 0 so `denseName` (`flexShrink: 1`) absorbs the squeeze. |
| `:461` | **unchanged** — `cardDense: { height: 60 }` | Load-bearing. Pinned by test + sabotage S4. |

### `mobile/src/screens/LeagueSummaryScreen.tsx`

| Line | Change | Why |
|---|---|---|
| `:10` | `BackHandler` added to the RN import | #302 — there were **zero** `BackHandler` registrations in this file. |
| `:23` | `fonts` added to the chalkline import | Needed by the local header-title style. |
| `:369-388` | `registerScrollToTop('League', …)` now clears `selectedId` before scrolling | **Decision:** re-tapping the *active* tab means "put this tab back to its root state". Scroll-to-top inside a focused roster is half a reset — the user is still in a drill-in. |
| `:704-763` | #302 core — effect calling `navigation.setOptions` to swap `headerTitle` → team name and mount `headerLeft` "‹ All teams"; reverts to `'League rankings'` / `headerLeft: undefined` when focus clears | Fixes all four causes at once: permanent (the header never scrolls), top-**left** (matches iOS and this app's own `subScreenOptions`), a full-size header control rather than an 11px caption, and the title answers "which team?" at any scroll depth. |
| `:733` | `if (!isTabRoot) return;` guards the whole swap | The legacy root-stack registration (`RootNav.tsx:508-530`, deep-link entry) already owns its `headerLeft` — the explicit JS back control that exists because native back is dead over `headerShown: false` (RNS#3294). Overwriting it strips that screen's only exit and it cannot be restored from here. |
| `:764-779` | `BackHandler` registered **only while `selectedId` is set**; clears focus and returns `true` | Android had no back affordance here at all. Returning `true` consumes the event so it doesn't fall through and leave the tab. |
| `:979` | In-card back link condition `selected` → `selected && !isTabRoot` | It moved to the header on the tab root. Exactly one of the two renders, so `league-summary.roster-close` is never duplicated on screen. |
| `:1003` | Refresh-button branch `) : (` → `) : selected ? null : (` | Without this, the tab root would show **refresh** while focused — the old `selected ?` ternary no longer carries that meaning. |
| `:1300-1310` | `denseSingleLine` passed to the roster `PlayerCard` | #299, the only opt-in site in the app. |
| `:2050-2067` | New local `StackHeaderTitle` component, `testID="league-summary.header-title"` | Deliberately a **local copy** of TabNav's private `HeaderTitle`: importing it would close the cycle `TabNav → LeagueSummaryScreen → TabNav`. |
| `:2071-2087` | New styles `headerBack` / `headerBackText` / `headerTitle`, mirroring TabNav's | So the focused League header is indistinguishable from every other pushed sub-screen's. |
| `:2366-2375` | `pickRow.minHeight` 40 → **32** | Draft-capital rows are not `PlayerCard`s and would not shrink with the tiles. `minHeight` not `height`: with a `MemberEnteredMarker` in the body the row is legitimately taller and must still grow. |

### New files

- `mobile/tests/check-league-drill-in.js` — 30 structural assertions (§6).
- `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` — the Maestro delta.

### `mobile/src/navigation/TabNav.tsx` — **not modified**

It was in this agent's ownership but needed no change: the tab-root screen is registered with `chalklineHeader('League rankings')`, which already sets `headerShown: true` with an empty `headerLeft`. That empty slot is exactly what `setOptions` fills, which is why V2 costs 0pt.

### Not touched, by ownership rule

`TradesScreen.tsx` and `InLeagueCalculator.tsx` (parallel agent). No change to either is needed — nothing here proposes one. Shared docs likewise untouched; proposed text is in §7.

---

## 2. Measured geometry — before / after

Every number below is read off token values in source, not estimated from a screenshot:
`space.xs = 4`, `space.sm = 8`, `space.lg = 16` (`theme/chalkline.ts:68-75`); `type.label` = 11/14 (`:115-122`); `Badge` = `paddingHorizontal 6, paddingVertical 2, borderWidth 1` (`components/chalkline/Badge.tsx`).

### Per-player tile

| Measure | Before | After | Δ |
|---|---|---|---|
| Tile height (`cardDense` → `+ cardDenseSingle`) | **60pt** | **32pt** | **−28pt (−46.7%)** |
| Row margin (`rosterRow: marginBottom: space.xs`) | 4pt | 4pt | unchanged |
| **Pitch per player** | **64pt** | **36pt** | **−28pt (−43.8%)** |
| Lines of content | 2 | 1 | line 2 held one badge and nothing else |
| Information dropped | — | **none** | name, team, RK, injury, tier, posRank all survive |

Derivation of 32: tallest row element is `TierChalkBadge` = 14 (lineHeight) + 4 (padding) + 2 (border) = **20pt**; + 6pt above + 6pt below = **32pt**. Under the `a11y.text_scaling` **dense** cap (×1.35, `theme/chalkline.ts:160-168`) the badge tops out at ~27pt, so the fixed height still clears its own content — the flag is ON in the release fixture, which is what makes a fixed height safe rather than a clipping risk.

### Roster block, 26-man roster

| | Before | After | Reclaimed |
|---|---|---|---|
| Roster height | 26 × 64 = **1,664pt** | 26 × 36 = **936pt** | **728pt** |

### Players above the fold

390×844 device, less 47 safe-top + 52 TopBar + 44 stack header + 83 tab bar → **618pt** of scroll viewport; less the #243 focused strip, the drill sub-line, the mirrored subset control and the position pills (~300pt) → **~318pt of roster before the fold**.

| | Before | After |
|---|---|---|
| Players visible | `⌊318/64⌋` = **4** | `⌊318/36⌋` = **8** |

### Draft-capital rows (`pickRow`)

| Measure | Before | After |
|---|---|---|
| `minHeight` | 40pt | **32pt** |
| Pitch (+1pt bottom hairline) | 41pt | **33pt** |

Now within 3pt of the tile pitch instead of 23pt taller than the tile. Carried out, not deferred — this was point 3 on the decisions doc's "carried forward regardless of variant" list.

---

## 3. Right-cluster room, and the #300 chevron question

**Asked:** the #300 mockup agent concluded, measured against this box model at `221c134`, that a minimal ice chevron glyph (no visible text) fits the 32pt tile's right cluster. **Confirm or refute from the implementation side.**

### Verdict: CONFIRMED horizontally — but the premise has a second half that does not hold. Read §3.3 before building #300.

### 3.1 The box model, as implemented

Card width = 390 − 2×16 (`scroll: { padding: space.lg }`) = **358pt**; less 1pt border each side = **356pt inner**. No horizontal padding is added by `drillPanel`, `drillList`, or `rosterRow` (verified — `:2341-2362`).

Fixed consumption: `denseMain` `paddingLeft: 13` + `paddingRight: 8`; `denseNums` `marginRight: 8`; `denseNumsRow` `gap: 8`.

Glyph advances used below: Archivo SemiBold 11px uppercase ≈ 6.8pt + 0.88 letterSpacing per glyph; IBM Plex Mono SemiBold 14px = 0.6em = 8.4pt/char; Archivo SemiBold 15px mixed-case name ≈ 7.8pt/char. **These are computed advances, not rendered measurements** — no simulator was available. Treat ±8% as the error bar.

### 3.2 Room, in points

| Element | Narrowest | Typical | Widest |
|---|---|---|---|
| Tier badge (14pt chrome + text) | `FA` **29pt** | `2nd` **37pt** | `4+ 1sts` **68pt** |
| gap | 8 | 8 | 8 |
| `posRank` | `NR` **17pt** | `WR61` **34pt** | `WR100` **42pt** |
| trailing `marginRight` | 8 | 8 | 8 |
| **Right cluster total** | **62pt** | **87pt** | **126pt** |

Name column = 356 − 13 − 8 − cluster − (team + micro-tags + their 6pt gaps), where team ≈ 18pt, `RK` ≈ 23pt, injury `Q` ≈ 15pt:

| Row shape | Name budget | ≈ chars |
|---|---|---|
| Clean row, typical badge | **224pt** | ~28 |
| Long name + `RK` + injury + `4+ 1sts` + `WR100` | **135pt** | ~17 |

Longest realistic dynasty names run 19–21 chars ("Marvin Harrison Jr.", "Christian McCaffrey"). So clean rows are comfortable and **only the worst case ellipsizes** — gracefully, because `denseName` sets `flexShrink: 1` (`PlayerCard.tsx:490`), so the name truncates instead of pushing the data off the edge.

### 3.3 What #300's chevron actually costs — and the constraint that matters more

**Horizontal cost: +24pt.** A 16pt `Icon` in the existing `rightSlot` (`denseRightSlot`, `marginRight: space.sm`) = 16 + 8. **Use `rightSlot`, not `denseNumsRow`** — it already renders at the trailing edge *after* the cluster (`PlayerCard.tsx:294`), so **#300 needs no change to `PlayerCard` at all**, and tier/posRank adjacency stays intact.

| Row shape | Name budget today | With chevron | ≈ chars |
|---|---|---|---|
| Clean row, typical badge | 224pt | **200pt** | ~25 |
| Worst case | 135pt | **111pt** | ~14 |
| Clean row on a 375pt device (SE 3 / 13 mini) | 209pt | **185pt** | ~23 |
| Worst case on 375pt | 120pt | **96pt** | ~12 |

So: fits, comfortably in the common case; the worst case loses ~3 characters on top of truncation it already had. Vertically a 16pt icon in a 32pt row is a non-issue.

**But the horizontal fit is not the binding constraint, and the #300 design should not be built on it alone:**

1. **A chevron inside the tile cannot be its own accessible control.** The dense branch renders one `Pressable` with `accessible: true` and a composed `accessibilityLabel` (`PlayerCard.tsx:193-206`) — VoiceOver reads the tile as a single utterance and collapses the subtree. Anything in `rightSlot` is invisible to VoiceOver **and to Maestro id-selectors** (flow-authoring law 3). An "Offer" affordance there is decoration unless it is surfaced as an `accessibilityAction` (the card already accepts `accessibilityActions` / `onAccessibilityAction`, `:84-85`) or the whole tile carries the action.
2. **The moment the tile gets an `onPress`, 32pt stops being safe.** The entire justification for 32pt is that *this* caller passes no `onPress`, so `accessibilityRole` stays undefined, the row is inert, and the 44pt minimum touch target does not bind (`PlayerCard.tsx:195-196`). A trailing "Offer" affordance that does something makes the row a tap target and re-opens exactly the question 32pt was predicated on avoiding.

**Recommendation to #300:** either (a) make the *affordance* the tap target — a `rightSlot` `Pressable` sized ≥44pt that overflows the 32pt row's bounds (`overflow: 'hidden'` on `styles.card` will clip it, so this needs a real decision, not an assumption), or (b) keep the row inert and put "Offer" on a row-level `accessibilityAction` + a long-press. **Do not make the whole 32pt row pressable without revisiting the height** — that reverses the #299 decision by a side effect.

---

## 4. How the shared `PlayerCard` change was scoped — and the proof

**The mechanism:** one opt-in boolean prop, defaulting to `false`. The 32pt layout is unreachable unless a caller explicitly asks for it. `styles.cardDense` still declares `height: 60`; the old line-2 render path is unchanged for anyone who doesn't opt in; the right-cluster condition widens to `posRank || (denseSingleLine && tier)`, which for `denseSingleLine === false` is identically `posRank`.

**Every dense caller in the app**, enumerated (`git grep -n "dense" -- 'mobile/src/**/*.tsx'`):

| Caller | Passes `statsSlot`? | Pressable / draggable? | `denseSingleLine`? |
|---|---|---|---|
| `TiersScreen.tsx:941`, `:982` | yes | **yes — both**; rows sit in `react-native-draggable-flatlist` inside `<View pointerEvents="none">` | **no — untouched** |
| `FreeAgentsScreen.tsx:523` | yes | pressable | **no — untouched** |
| `LeagueSummaryScreen.tsx:1300` | no | no `onPress`, inert | **yes** |

**Proof, not assertion:**

1. `git diff origin/main --stat` lists **`TiersScreen.tsx` and `FreeAgentsScreen.tsx` among the files not changed** — the change set is `PlayerCard.tsx`, `LeagueSummaryScreen.tsx`, plus the two new test/flow files.
2. The Tiers drag path is untouched by construction: nothing in this change adds a touch handler, a `pointerEvents`, or a `hitSlop` to the dense branch. The only new element is a `View` (`denseNumsRow`) inside the already-existing, already-non-interactive right cluster. Nothing captures list touches — the failure mode that has broken TestFlight builds before.
3. Three assertions pin it, each proven to fail on a sabotaged build: `cardDense` is still 60 (**S4**), `TiersScreen` does not opt in (**S5**), `FreeAgentsScreen` does not opt in (**S17**). Two more pin that those guards stay *meaningful* if someone stops using `dense` there at all (**S16**, **S18**).

---

## 5. Verification output

Actual output, not claims. Run in the worktree with `node_modules` installed by `npm ci` **inside the worktree** (never symlinked from the main checkout).

```
$ npx tsc --noEmit
$ echo $?
0
```
(no output — clean)

```
$ bash mobile/scripts/testid-lint.sh
testid-lint OK
$ echo $?
0
```

```
$ node mobile/tests/check-league-drill-in.js
PASS  #299 PlayerCard declares the `denseSingleLine` prop
PASS  #299 `cardDenseSingle` is height 32
PASS  #299 `cardDenseSingle` is applied in the dense branch style array
PASS  #299 the shared dense row is STILL 60pt
PASS  #299 src/screens/TiersScreen.tsx is still a dense PlayerCard caller (guard is meaningful)
PASS  #299 src/screens/TiersScreen.tsx does NOT opt in to the single-line row
PASS  #299 src/screens/FreeAgentsScreen.tsx is still a dense PlayerCard caller (guard is meaningful)
PASS  #299 src/screens/FreeAgentsScreen.tsx does NOT opt in to the single-line row
PASS  #299 the dense line-2 View is findable
PASS  #299 line 2 renders only when NOT in single-line mode
PASS  #299 the right cluster has a single-line (row) variant
PASS  #299 the tier badge is rendered INSIDE the right cluster
PASS  #299 the relocated badge is gated on `denseSingleLine`
PASS  #299 posRank is rendered inside the right cluster
PASS  #299 the tier badge is LEFT of the positional rank
PASS  #299 LeagueSummaryScreen renders exactly one PlayerCard site
PASS  #299 the League roster tile is a dense PlayerCard
PASS  #299 the League roster tile opts in to the 32pt single-line row
PASS  #299 the draft-capital rows are in proportion with the new tile (minHeight 32)
PASS  #302 the back control is mounted as the stack header's `headerLeft`
PASS  #302 the header title swaps to the focused team name
PASS  #302 clearing focus restores the bare tab-root header
PASS  #302 a navigation.setOptions call exists
PASS  #302 the header swap is scoped to the TAB ROOT registration
PASS  #302 the in-card back link still exists for the root-stack push
PASS  #302 the in-card back link does NOT render on the tab root
PASS  #302 an Android hardware-back handler is registered
PASS  #302 hardware back clears the focused team and CONSUMES the event
PASS  #302 the handler is registered ONLY while a team is focused
PASS  #302 re-tapping the active League tab also clears the focused team

All League drill-in checks passed (#299 + #302).
$ echo $?
0
```

**`mobile/package.json` was NOT edited** — it is outside this agent's file ownership and every other agent in the batch adds script lines to the same block, which is a guaranteed merge conflict. The orchestrator should add, after `"test:picks-subset-invariance"`:

```json
    "test:league-drill-in": "node tests/check-league-drill-in.js"
```

---

## 6. Sabotage proof — 30 assertions, 30 falsifications

Each sabotage was applied to the real working tree one at a time, the test re-run, the failing assertion recorded, and the file reverted (`git checkout --`). Working tree verified clean after every batch. **A test that passes on the defect it was written to catch is not a test** — and this pass caught one.

### The one that failed the falsification pass

**S21 — the relocated tier badge made unconditional (`{tier ? <TierChalkBadge/> : null}`).** The test **PASSED on the sabotage**. Cause: `enclosingConditionText()` walked six JSX parents and concatenated their conditions, and the badge sits inside the cluster's own `posRank || (denseSingleLine && tier) ? …` ternary — so the ancestor text contained `denseSingleLine` regardless of the badge's own gate. Fixed in `ba30464` by reading the **innermost** gate only (`nearestConditionText`); all three gate assertions (badge, line 2, in-card link) now use it, and S21 is detected. The false-pass would have shipped a build where Tiers/FreeAgents rows render the tier badge twice.

### Full matrix

| # | Sabotage | Assertion that fires |
|---|---|---|
| S1 | `denseSingleLine?: boolean` declaration removed | prop is declared |
| S2 | single-line height 32 → 44 | `cardDenseSingle` is height 32 |
| S3 | style declared but never added to the style array | style is *applied* |
| S4 | shared `cardDense` shrunk wholesale 60 → 32 | shared dense row is STILL 60pt |
| S5 | Tiers board opts in to `denseSingleLine` | TiersScreen does NOT opt in |
| S6 | line 2 rendered unconditionally | line 2 renders only when not single-line |
| S7 | tier badge dropped rather than relocated | badge is inside the right cluster |
| S8 | badge placed to the RIGHT of `posRank` | badge is LEFT of the positional rank |
| S9 | League call site drops the opt-in prop | League tile opts in |
| S10 | `pickRow.minHeight` reverted to 40 | picks rows in proportion |
| S11 | `headerLeft` back control removed | exit is mounted as `headerLeft` |
| S12 | `if (!isTabRoot) return;` removed | header swap scoped to the tab root |
| S13 | in-card link also renders on the tab root | in-card link NOT on the tab root |
| S14 | hardware back returns `false` (falls through to navigator) | back clears focus AND consumes |
| S15 | tab re-tap only scrolls, leaves focus | re-tap clears the focused team |
| S16 | TiersScreen stops being a dense caller | guard-the-guard: still a dense caller |
| S17 | FreeAgents opts in to `denseSingleLine` | FreeAgents does NOT opt in |
| S18 | FreeAgents stops being a dense caller | guard-the-guard: still a dense caller |
| S19 | dense line-2 View deleted outright | line-2 View is findable |
| S20 | right cluster loses its row variant (badge stacks under posRank) | cluster has a row variant |
| S21 | relocated badge rendered unconditionally | badge is gated on `denseSingleLine` |
| S22 | `posRank` dropped from the right cluster | posRank is in the cluster |
| S23 | a second `PlayerCard` site added to the screen | exactly one PlayerCard site |
| S24 | League roster tile stops being `dense` | tile is a dense PlayerCard |
| S25 | header title no longer swaps to the team name | title swaps to team name |
| S26 | clearing focus leaves a stale `headerLeft` | clearing restores the bare header |
| S27 | the `setOptions` header swap removed entirely | a setOptions call exists |
| S28 | in-card back link deleted (root-stack push loses its exit) | in-card link still exists |
| S29 | `BackHandler` registration removed | handler registered (+2 more) |
| S30 | handler registered unconditionally | registered ONLY while focused |

**Result: 30 sabotages applied, 30 detected, 0 missed** (after the S21 fix). Harness: `scratchpad/sabotage.sh` + `sabotage2.sh` — throwaway, not committed.

**Honest limit of this test class.** These are *structural* assertions: they prove the code says what the decision says, not that pixels land at 32pt or that Android back fires. That is what §8 is for.

---

## 7. Proposed shared-doc edits (orchestrator applies)

Not applied by this agent — shared docs are orchestrator-owned. Verbatim text follows.

### 7.1 `mobile/src/components/CLAUDE.md` — PlayerCard prop registry

> `denseSingleLine` (#299) — opt-in 32pt single-line variant of the `dense` row, used **only** by the League drill-in roster panel (`LeagueSummaryScreen.tsx`). Drops line 2 and renders the tier badge in the right cluster, left of `posRank`. **Incompatible with `statsSlot`** (there is no line 2 to hold it), and unsafe for any caller that passes `onPress`: 32pt is below the 44pt touch minimum, and the League tiles are inert, which is what makes it legal there. The Tiers board and the FA list keep the 60pt two-line row. Pinned by `mobile/tests/check-league-drill-in.js`.

### 7.2 `mobile/src/screens/CLAUDE.md` — testID registry, LeagueSummaryScreen

> `league-summary.header-title` — the stack-header title (#302). Reads "League rankings" on the all-teams view and swaps to the focused team's name while a team is drilled into. Tab-root registration only; the legacy root-stack `LeagueSummary` push keeps its static title.
>
> `league-summary.roster-close` / `league-summary.back-all-teams` — the drill-in exit. **Moved in #302** from the chart-card header (where it scrolled away) to the stack header's `headerLeft`. Ids deliberately unchanged, as in #243. On the legacy root-stack push it remains the in-card link, because that screen's `headerLeft` is already its own back control. Exactly one of the two renders at a time.

### 7.3 `living-memory/LLD.md` — mobile conventions

> **Per-caller density on shared presentational primitives is an opt-in prop, never a branch change** (2026-08-11, #299). `PlayerCard`'s `dense` row is consumed by three screens with different interaction contracts — the Tiers board's rows are pressable *and* drag-liftable (44pt touch minimum binds), the FA list passes a `statsSlot`, the League drill-in is inert and passes neither. When one caller needs different geometry, add a boolean prop defaulting to the existing behaviour so every other caller stays byte-identical; do not reshape the shared branch and then audit the fallout. Enforce with a structural test that pins both the *old* dimension and the non-opt-in of every other caller.

### 7.4 `living-memory/DECISIONS.md` — two entries (renumber to `max + 1`)

> **D-xxx — League roster tiles: 32pt via an opt-in prop, not the literal 30pt (2026-08-11, #299).**
> The operator asked to cut the tiles "to about half". Literal half is 30pt and needs `paddingVertical 2 → 1` on the shared `Badge` primitive, which renders position, tier, rookie and injury badges on every screen in the app. 32pt is the natural floor of the existing primitive (badge 20pt + 6pt above and below) and lands at −47%. Two points of gain is not worth an app-wide component fork. Scoped through a new `denseSingleLine` prop so the Tiers board — pressable, drag-liftable, and needing its `statsSlot` — is untouched. Draft-capital rows (`pickRow`) came down 40 → 32 in the same pass so the picks group doesn't read tall beside the roster.

> **D-xxx — League drill-in back affordance lives on the stack header, tab-root only (2026-08-11, #302).**
> The drill-in is component state (`selectedId`), not a stack push, so no system back works anywhere: no stack back (LeagueRankings is the stack root), no iOS edge-swipe, and no `BackHandler` was registered. The exit moved into the already-fixed stack header (`headerLeft` + title swap) at zero vertical cost, and an Android `BackHandler` is now registered while focused. **Scoped to the tab-root registration**: the legacy root-stack `LeagueSummary` (deep-link entry, `RootNav.tsx:508-530`) already owns its `headerLeft` — the explicit JS back control that exists because native back is dead over `headerShown: false` (RNS#3294) — and `setOptions` cannot restore it once overwritten. That variant keeps the in-card link; the two are mutually exclusive. Making the drill-in a real route push was considered and rejected: it breaks the 2026-07-26 Analyzer treatment (chart stays visible above the roster) and #237's shared filter state.

### 7.5 `living-memory/GOTCHAS.md` — one entry (renumber to `max + 1`)

> **G-xxx — A JSX "is this gated on X?" test that walks ancestors will false-pass (2026-08-11).**
> `check-league-drill-in.js` asserted that the relocated tier badge was gated on `denseSingleLine` by collecting the conditions of six JSX ancestors and regex-matching the token. The badge sits inside the cluster's own `posRank || (denseSingleLine && tier) ? …` ternary, so the token was always present — the assertion passed on a deliberately sabotaged build where the badge was unconditional. **Read the innermost conditional only, and stop at the enclosing JSX element boundary.** Found only because every assertion was run against a sabotaged tree; it would not have shown up in review.

### 7.6 `living-memory/TEST_LEDGER.md`

> **2026-08-11 — #299 + #302 (League drill-in), static gate only.** `npx tsc --noEmit` exit 0; `mobile/scripts/testid-lint.sh` → `testid-lint OK`; new `mobile/tests/check-league-drill-in.js` 30/30 PASS, **all 30 falsified against deliberate sabotages (30/30 detected, 1 false-pass found and fixed in `ba30464`)**. New flow `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` **authored but NOT run** — the batch ran static-only to avoid parallel agents contending for one simulator. **Tier-1 simulator gate is still owed** (full smoke + the feature flow + `league-summary` captures) and this must not merge to `main` without it.

### 7.7 `docs/api-reference.md`, `docs/cross-client-invariants.md`, `docs/architecture.md`, `living-memory/HLD.md`, `docs/glossary.md`

**No change.** Reasons per row in `scope.md` §4.

---

## 8. What is NOT verified — QA checklist

Static analysis cannot settle any of the following. All of it belongs to the batch QA round.

**#299 — geometry and legibility**
- [ ] Tile renders at **32pt** and the pitch at **36pt** on a real device/sim. Measure, don't eyeball.
- [ ] The tier badge sits **left of** the positional rank, vertically centred, on every position group.
- [ ] Rows with **no tier** (K / DEF / unpriceable) still render at 32pt without a ragged gap where the badge would be.
- [ ] Rows with **no posRank** — the caller passes `?? 'NR'`, so this should be unreachable; confirm no empty cluster renders.
- [ ] **Worst-case truncation:** a long-named rookie with an injury tag and a `4+ 1sts` badge (e.g. Marvin Harrison Jr. + Q). Name should ellipsize; badges and posRank must NOT be pushed off the right edge.
- [ ] **375pt device** (iPhone SE 3 / 13 mini) — the tightest width; §3.2 predicts ~12–23 chars of name.
- [ ] **OS text scaling.** `a11y.text_scaling` is ON in the release fixture, capping dense at ×1.35 → badge ~27pt inside 32pt. Check the largest accessibility size: **with the flag OFF, scaling is uncapped and a fixed 32pt height WILL clip.** Worth confirming the flag's state in prod.
- [ ] Draft-capital rows (32pt) read in proportion beside the roster, and a row carrying a `MemberEnteredMarker` still grows rather than clipping.

**#299 — the blast radius (the point of the opt-in prop)**
- [ ] **Tiers board rows are still 60pt, two-line, with their `statsSlot`.** Regression-critical.
- [ ] **Tiers drag still works** — press, lift, reorder, drop, no crash. `react-native-draggable-flatlist` inside `<View pointerEvents="none">` has broken TestFlight builds before.
- [ ] **Free Agents rows unchanged** (60pt, two-line, drop-candidate stats on line 2).

**#302 — the exit**
- [ ] Drill in → header title becomes the **team name**; "‹ All teams" appears **top-left**.
- [ ] Scroll to the bottom of a long roster → the exit is **still on screen** (this is the whole bug).
- [ ] Tap it → returns to all teams; header reverts to "League rankings"; **no stale back control** remains.
- [ ] **Android hardware back** clears focus instead of leaving the tab. **Never exercised — no Android device or emulator was used at any point in this build.** Highest-risk unverified item.
- [ ] Android back on the **unfocused** view still behaves normally (the handler should be unregistered).
- [ ] **Re-tap the active League tab while focused** → focus clears *and* it scrolls to top.
- [ ] **Legacy root-stack entry** (deep link to `LeagueSummary`): the in-card "All teams" link still renders and works, and that screen's own header back control is **intact and not overwritten**. This is the regression the `isTabRoot` guard exists to prevent.
- [ ] Switch **basis (Consensus ↔ My board) while focused** → the header title must follow the re-derived team, not go stale.
- [ ] Navigate League tab → `LeagueHome` → back, while a team was focused: confirm the header options don't leak across the push.
- [ ] `flows/league/01-picks-in-subsets.yaml` still passes — it taps `league-summary.roster-close`, which moved.
- [ ] Run `flows/league/05-drill-in-back-affordance.yaml` itself.

**Screen library**
- [ ] Capture the missing `league-summary` **`drill-in`** state (needs a new state in `mobile/.maestro/capture/league-summary.yaml` first). Every "current" frame for #299/#302 is a reconstruction until this exists — and #300 needs it too.

---

## 9. Where the decisions doc needs a correction

`OPERATOR-DECISIONS.md` and the two lab pages were accurate on every claim that could be checked against source, with three additions the build surfaced:

1. **The #302 fix cannot be applied uniformly to both registrations, and the lab does not mention the second one.** The lab says "implemented with `navigation.setOptions` … delete the in-card link at `:902-914` once it lands." Deleting it outright would leave the legacy root-stack `LeagueSummary` push (`RootNav.tsx:508-530`) relying on a `headerLeft` this screen would have overwritten — and `setOptions` cannot restore a control it doesn't own. The link is therefore **kept for `!isTabRoot`** and the swap is guarded. Not a contradiction of the decision; a case it didn't enumerate.
2. **The lab's right-cluster width table is slightly optimistic.** It budgets the `4+ 1sts` badge at 60pt; computed from the real `Badge` chrome (`paddingHorizontal 6×2 + borderWidth 1×2` = 14pt) plus 7 uppercase glyphs at `type.label` with 0.88 letterSpacing, it is closer to **68pt**. Direction of the conclusion is unchanged — clean rows are comfortable, the worst case ellipsizes — but the worst-case name budget is ~135pt, not the ~148pt quoted.
3. **The #300 premise needs the caveat in §3.3.** "A chevron fits" is true horizontally and false as a specification: inside the tile's single `accessible` Pressable a chevron is invisible to VoiceOver and to Maestro, and giving the row an `onPress` to make it actionable re-introduces the 44pt touch minimum that 32pt was explicitly predicated on avoiding.
