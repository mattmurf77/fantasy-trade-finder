# #293 / #294 — Draft-pick value in Starters/Bench subsets and position filters

**Group:** G3 (polish path) · **Screen:** `LeagueRankings` · **Severity:** bug · **App:** 1.11.0
**Filed:** 2026-08-10 by `mattmurf77`
**Branch:** `feedback-289-294` (worktree `.claude/worktrees/fb-289-294`, based on `origin/main` @ `7cea1fa`)
**Phase:** 1 — PLAN ONLY. No production code in this document.

**Verbatim reports**

- **#293:** "Starters and bench tabs don't have the pick values"
- **#294:** "Neither do the position specific filters"

**Operator ruling (the contract):** *"I'm talking about picks for value."*

> A team's draft-pick value contribution is **subset-independent and filter-independent**.
> Switching to Starters or Bench, or filtering to a position, must never make a team's
> value silently drop by the amount of its draft capital.

---

## 0. Route confirmation

`LeagueRankings` is `mobile/src/screens/LeagueSummaryScreen.tsx`, registered at
`mobile/src/navigation/TabNav.tsx:450-451` (`name="LeagueRankings"
component={LeagueSummaryScreen}`) as the League tab stack's root; `LeagueHome`
(the classic `LeagueScreen`) is the pushed sub-route at `TabNav.tsx:455-460`.
Confirmed — the orchestrator's mapping is correct.

---

## 1. Current-behavior verdict on `origin/main` @ `7cea1fa`

**Answering the mandatory first question:** the shipped 1.11.0 behavior the tester
saw is still exactly what `origin/main` does today. **#285 did not partially cover
this.** Nothing has landed since that changes pick handling in the subsets or the
filters.

### 1.1 The single source of truth for a team's charted value

`LeagueSummaryScreen.tsx:260-270` — `activeTotal()`:

```ts
function activeTotal(tc: TeamComputed, subset: Subset, filter: Set<FilterKey>): number {
  if (filter.size === 0) {
    return subset === 'all' ? tc.team.total_value : tc.coreTotal;   // ← 262
  }
  let sum = 0;
  filter.forEach((p) => {
    if (p === 'PICKS') sum += subset === 'all' ? tc.team.picks?.value ?? 0 : 0;  // ← 266
    else sum += tc.posValues[p];                                    // ← 267
  });
  return sum;
}
```

`tc.coreTotal` is defined at `:251` as `QB+RB+WR+TE` only — the interface comment at
`:228` says it outright: *"Core-position value sum under the subset (players only, no
picks)."*

### 1.2 Behavior matrix (today)

| Subset | Filter | Team value shown | Picks counted? | Evidence |
|---|---|---|---|---|
| All | none | `team.total_value` (= `positions_value + picks.value`, server-authoritative) | **Yes** | `:262`; api-reference.md:350 |
| All | `{QB…TE}` any subset of positions | Σ `posValues[p]` | **No** | `:267` |
| All | `{PICKS}` | `team.picks.value` only — a picks-only ranking | Yes (exclusively) | `:266` |
| All | `{RB, PICKS}` | RB + picks | Yes | `:266-267` |
| **Starters** | none | `coreTotal` (players only) | **No** | `:262` |
| **Starters** | any | Σ positions; `PICKS` contributes literal `0` | **No** | `:266` |
| **Bench** | none | `coreTotal` (players only) | **No** | `:262` |
| **Bench** | any | Σ positions; `PICKS` contributes literal `0` | **No** | `:266` |

**#293 and #294 both reproduce, and are the same defect seen from two angles.**

### 1.3 The supporting machinery that enforces "picks only in All"

| What | Where | Effect |
|---|---|---|
| Picks pill + legend swatch gate | `:370` `const showPicksKey = hasPicks && subset === 'all';` (consumed `:760`, `:882`, `:948`) | The **Picks** pill and legend key literally disappear in Starters/Bench |
| Filter self-clean on subset switch | `:555-565` `switchSubset()` deletes `'PICKS'` from `posFilter` whenever `s !== 'all'` | A Picks selection is silently discarded on tapping Starters |
| Bar stack composition | `:1266-1271` `shownBase` omits `'PICKS'` unless `subset === 'all'` | No neutral base segment in Starters/Bench |
| Bar segment value | `:1277-1280` `segValue('PICKS') = subset === 'all' ? picks.value : 0` | Belt-and-braces zero |
| Drill-in "Draft capital" group | `:1016-1018` `subset === 'all' && (posFilter.size === 0 \|\| posFilter.has('PICKS')) && items.length > 0` | The pick list vanishes from the roster panel in Starters/Bench **and** under any position filter |
| Design intent, stated | header comment `:159-162`, `:255-259`, `:366-368`, `:553-554`, `:1013-1015`, `:1233-1240` | Six separate places document "picks are neither starters nor bench" |

**Conclusion:** this is a deliberate, six-times-documented design, not an
oversight. #293/#294 is therefore a **design reversal**, not a bug fix, and the
plan must retire the old rule everywhere it is written down, not just patch the
arithmetic.

### 1.4 What #285 actually shipped (and why it did not cover this)

`docs/feedback/items/285-pick-sums/status.md` + `docs/api-reference.md:350`:

- #285 is **label-only** and **experiment-gated** (`aggregate_tier_labels`,
  `is_tester_allowlist` — operator's account only).
- It changed `total_value_label` from `_aggregate_pick_label(total_value)` to
  `_aggregate_pick_label(positions_value, _pick_firsts_equivalent(picks))` —
  a literal pick count (1st = 1.0, 2nd = 1/3.5, 3rd+ = 0).
- It states explicitly (§"The numeric `total_value` decision") that `total_value`,
  `picks.value` and every other numeric field are **byte-identical** before and
  after, deliberately, for three reasons including "it would reshuffle rank order".
- `_power_picks_by_owner` gained an inert `round` key (`backend/server.py:18876-18894`).

**Crucially:** `total_value_label` only renders where `subset === 'all' &&
posFilter.size === 0` (`:927-928` drill subline, `:1062-1063` `TeamRow`). So even
for the allowlisted operator, #285's label **never appears in Starters, Bench, or
under a position filter** — it degrades to the numeric `Math.round(active)`, which
is precisely the number that is missing the picks. #285 raised the operator's
expectation ("picks are in the total now") on exactly the one view where it was
already true, which is why the next thing they did was tap Starters and file #293.

### 1.5 Cross-client check

`web/league-rankings.html` renders the picks segment **unconditionally**
(`:768-769`, `:870-891`) and has **no** All/Starters/Bench control and **no**
position filter. There is no web behavior to keep in sync and no invariant
divergence to introduce. The extension does not consume `/api/league/power-rankings`.
**Mobile-only defect.**

---

## 2. Problem statement

Draft capital is a real, tradeable component of a dynasty team's value, priced
server-side on the generic ladder (`pick_pool_value`, `docs/cross-client-invariants.md:317`)
and already summed into `total_value`. On `LeagueRankings` that contribution
**silently evaporates** the moment the user narrows the view — three of the four
subset/filter axes drop it to zero with no caption, no dimmed pill, and no
explanation. A rebuilding team holding four 1sts ranks like a team holding none.

Encode the operator's rule: **draft-pick value is a permanent, subset-independent,
filter-independent component of a team's charted value. It may only be excluded by
an explicit, visible user action — never as a side effect of changing subset or
position.**

---

## 3. Spec decisions

### D1 — Starters / Bench: picks render identically in all three subsets (option (a))

**Decision.** Drop the `subset === 'all'` condition from every picks code path.
In All, Starters and Bench alike:

- `activeTotal` includes the team's full `picks.value`;
- the neutral Picks segment renders at the **base** of every bar (unchanged
  stacking order QB→RB→WR→TE→Picks, `:1272-1276`);
- the Picks legend swatch and the Picks filter pill are available;
- the drill-in "Draft capital" group renders.

Formally, with `filter.size === 0`:

| Subset | New value |
|---|---|
| All | `team.total_value` *(unchanged — already includes picks; must NOT add again)* |
| Starters | `coreTotal + (picks.value ?? 0)` |
| Bench | `coreTotal + (picks.value ?? 0)` |

**Alternatives rejected.**

- **(b) Keep Picks in All only, add a caption in Starters/Bench.** Rejected: the
  operator said *"picks for value"*, i.e. the value must be **counted**, not
  narrated. A caption leaves the bar heights, the sort order and the rank numerals
  all still wrong — the exact thing the ruling forbids. It also costs a new
  persistent text block on a screen the #243 dedup work just finished decluttering.
- **(c) Split pick value across starters/bench proportionally.** Rejected as
  fabrication. There is no defensible allocation (picks are future assets tied to
  neither group), it would break `picks.items` (individual picks cannot be halved
  and still list truthfully), and `docs/cross-client-invariants.md:317` forbids
  clients deriving pick values differently from the server's `pool_value`. The
  screen's own honest-degradation posture (`:352-359`, "never fabricate") points
  the same way.
- **(d) Add a fourth "Picks" subset segment.** Rejected: over-build, and it does
  not fix #294 at all.

**Design-system justification.** Zero new tokens. `PICKS_COLOR = chalk.faint`
(`:171`) and `GRAY_SEGMENT.PICKS = ink.ink3` (`:187`) already exist and already
satisfy `docs/cross-client-invariants.md` — Picks stays a **neutral ink tone,
never a position hex**, in every subset. No new hue, no gradient, no radius change,
no emoji. The change makes an already-specced element render in more states.

**Named consequence (must be stated in the PRD, not discovered in QA):** Starters
and Bench stop being a partition. `starters_total + bench_total` now equals
`positions_value + 2 × picks.value`, not `total_value`. This is intrinsic to the
operator's ruling — the same constant is deliberately counted in both halves. It
is invisible in the UI (the two subsets are never summed on screen) but it must be
written down, and the hint copy must stop claiming "only" (see D5).

### D2 — Position filters: picks are additive by default, explicitly deselectable (option (c), the "better" one)

**Decision.** Selecting a position filter does **not** remove draft capital. Two
coupled rules:

1. **Arithmetic:** `activeTotal`'s `'PICKS'` branch drops the `subset === 'all'`
   guard, so whenever `PICKS ∈ filter`, `picks.value` contributes in every subset.
2. **Default membership:** on the **empty → non-empty** transition of `posFilter`
   (i.e. the user's first position tap out of "All"), `'PICKS'` is auto-added to
   the set, *when the league actually has draft capital* (`hasPicks`, `:369`).
   Tapping RB yields `{RB, PICKS}` — and the **Picks pill visibly lights up**, so
   the inclusion is disclosed by the existing control, not hidden.

Resulting behavior:

| User action from "All" | Filter set | Value shown |
|---|---|---|
| tap RB | `{RB, PICKS}` | RB + picks |
| tap RB, then tap Picks off | `{RB}` | RB only *(explicit, visible opt-out)* |
| tap RB, then WR | `{RB, WR, PICKS}` (Picks not re-added if the user removed it — see below) | RB + WR + picks |
| tap Picks from All | `{PICKS}` | picks only *(today's draft-capital ranking, preserved)* |
| tap All | `{}` | full value incl. picks |

The auto-add fires **only** when `prev.size === 0`, so a deliberate Picks
deselection is never re-asserted by a subsequent position tap. Tapping **All**
resets to the default, which is correct — All means everything.

**Why not the two obvious alternatives.**

- **"A position filter should show only that position's value" (the competing
  literal reading).** This reading is coherent and is what ships today, but it
  loses to the operator's explicit ruling, which names position filters directly:
  *"or filtering to a position, must never make a team's value silently drop."*
  D2 does not discard the reading — it demotes it from *default* to *one tap away*,
  and makes the tap a visible pill state rather than an invisible side effect.
- **"Picks become an always-on additive component; remove the Picks pill."** This
  is the simplest possible model and the strongest reading of the ruling. Rejected
  because it **deletes shipped capability**: `{PICKS}` alone is today the only
  league-wide draft-capital ranking anywhere in the app (`/api/league/picks` and
  `LeagueScreen`'s "Draft picks" section are per-team, not a ranked league view).
  #294 asked for pick value to stop vanishing; it did not ask to lose the
  picks-only view. Retiring a feature to fix a bug fails coding-guidelines
  principle 3 (surgical changes).
- **"Add a separate `includePicks` boolean + a new control."** Rejected under
  principle 2 (simplicity first): it introduces a second state axis, a second
  control style, and a new #237 mirroring surface, to express something the
  existing multi-select pill already expresses truthfully.

**Design-system justification.** No new control, no new pill variant, no new copy
block. The Picks pill's rendering is already specced (`:1216-1228`: neutral
outline, solid `PICKS_COLOR` fill when selected, label carries the encoding
alongside color per the a11y floor) and its `accessibilityState={{ selected }}`
(`:1221`) already announces inclusion to VoiceOver. D2 changes *when the pill is
pre-selected*, not how it looks.

**One truthfulness invariant this buys us, stated for the PRD:** *the Picks pill's
selected state is exactly equal to whether pick value is in the chart.* Today
that invariant holds by accident (Picks hidden ⇒ excluded). Any design where picks
contribute while the pill reads unselected would break it, which is the concrete
reason D2 is preferred over "silently always add picks".

### D3 — Ranking / sort coherence

**Decision: no changes needed to the ranking, overlay, or rank-numeral machinery.
The additive-constant property makes D1/D2 safe.**

The load-bearing fact, verified: **`picks.value` is basis-independent.**
`backend/server.py:18876` — `_power_picks_by_owner(league_id: str, fmt: str)` takes
**no `basis` argument**; pick prices come from the stored `pool_value` /
`pick_values.pick_pool_value(round, years_out)` ladder
(`docs/cross-client-invariants.md:317`, api-reference.md:350). The consensus and
personal payloads therefore carry **identical** `picks.value` for every team.

Consequences, walked one by one:

| Mechanism | Where | Effect of D1/D2 |
|---|---|---|
| `ranked` sort + rank numerals | `:381-391` | Re-sorts, as it should — the ruling *wants* pick capital to move teams. Numerals are still `idx + 1` over `ranked`, so **#208's finding ("numerals are an index into `ranked`, the server's `team.rank` is read nowhere") is untouched.** |
| `boardsDiffer` (identity) | `:410-414` | Uses `total_value`, which already includes picks on both bases. **Unchanged.** |
| `boardsDifferInView` / `ticksOn` (#208's fix) | `:457-467` | Compares `activeTotal` across bases. Both sides gain the **same** per-team constant `picks.value` ⇒ every `o.active !== r.active` comparison is invariant. **#208's fix is preserved exactly** — a QB-filtered view where the boards agree still hides the ticks. Verified by construction; must be pinned by a test (see §8). |
| `otherByTeam` ranks + `otherCount` | `:430-444` | Same constant added to every other-basis row ⇒ the other-basis ordering shifts identically to the bars'. Dual-rank captions stay coherent. |
| `scaleMax` / tick placement | `:471-478`, `:832-836` | Bars and ticks both grow by the same constant on the same shared scale — a tick still cannot clip. |
| Δ chips (`\|Δ\| ≥ 2`) | `:818`, `:837` | Since both orderings shift by the same constant, the *set* of rank swings can only change where picks genuinely break a near-tie. That is correct behavior, not a regression. |
| `avgActive` league-average line | `:487-493` | Derived from `ranked`, recomputes automatically. Its comment at `:485` ("no filter = full-roster average including picks") becomes true in more cases. |
| `teamPosRank` (drill-in group rank chips) | `:498-511` | Reads `posValues` **only**. **Must stay that way** — "your RB room is 3rd of 12" must never be inflated by draft capital. No change. |
| `playerPosRank` | `:516-529` | Player-level, picks-free. No change. |
| `total_value_label` (#279/#285) render gates | `:927-928`, `:1062-1063` | **Leave the `subset === 'all' && posFilter.size === 0` gate exactly as-is.** The server computes the label from `positions_value` + a whole-team pick count; there is no server-side starters/bench decomposition, so the label is only valid on the unfiltered All view. Widening it would fabricate. The numeric fallback (now picks-inclusive) is the correct display in every other state. |

**#248 combined-bars interaction, explicitly:** the overlay's inputs
(`computeSubset` + `activeTotal` over the *other* payload — `:424-439`) are the
identical functions the bars use, so both signals change together by construction.
The `otherStartersAvailable` degradation (`:415-418`, `:467`) is unaffected: if the
other payload cannot derive starters, ticks still hide in Starters/Bench rather
than fabricate. No `boardsDiffer` / `boardsDifferInView` semantics move.

### D4 — Drill-in roster panel (#237 / #243)

**Decision. One rule, both surfaces — enforced structurally by keeping the shared
state model untouched.**

The chart card and the drill-in already read the *same* `subset` and `posFilter`
(`:296-304`, `:936-949`) and the *same* `showPicksKey` (`:760`, `:948`). D1/D2 are
implemented **only** in the shared derivations (`activeTotal`, `showPicksKey`,
`togglePos`, `switchSubset`) and in `BarColumn`'s segment functions, so mirroring
holds automatically — #237 is not reopened.

Two drill-in-specific edits follow from D1/D2:

1. **`:1016-1018`** — the "Draft capital" group's render condition drops
   `subset === 'all' &&`, becoming
   `(posFilter.size === 0 || posFilter.has('PICKS')) && items.length > 0`.
   The pick list now appears in Starters/Bench and under position filters, matching
   the bar's base segment. Under D2's default membership, a user filtered to RB sees
   the RB group **and** the Draft capital group — which is exactly the value the bar
   is showing, so panel and chart reconcile row-for-row.
2. **`:951` `groupRows(...)`** — unchanged. Picks are not a roster section
   (`:1086-1087`); the Draft-capital group is rendered separately, below the
   position groups. Correct as-is.

**#243 slim-strip caption (`:570-580`, `:765-771`)** needs no logic change: it
already appends `Picks` in canonical last position when `posFilter.has('PICKS')`
(`:576`), so a focused user filtered to RB reads *"Filtered by: Starters · RB +
Picks"* — truthful, and it is the one place the D2 default is spelled out in words.

**`MemberEnteredMarker` (D17, W3 M-C):** unaffected and, if anything,
strengthened — the marker now reaches the priced pick rows in more states.
`mobile/tests/check-member-entered-marker.js:240-244, 264-288` asserts the marker
is unconditional **within the priced row** and imports the shared module; the
section-level condition above the row is outside its assertions. **This check must
still pass unmodified** — that is the acceptance criterion, not an exemption.

### D5 — Copy (falls out of D1/D2; small but load-bearing)

Three strings become untrue and must change with the behavior:

1. **`:779` subset prefix.** `'Best starting lineup only. '` / `'Bench only. '` —
   "only" is now false whenever picks contribute. Proposed, conditioned on a new
   local `picksInView = hasPicks && (posFilter.size === 0 || posFilter.has('PICKS'))`:
   - starters, picks in view → `'Best starting lineup + draft capital. '`
   - bench, picks in view → `'Bench + draft capital. '`
   - picks deselected → today's `'… only. '` strings, unchanged.
2. **`:784` filtered branch.** `Ranked by ${[...posFilter].join(' + ')} value only`
   currently prints the raw enum — with Picks now routinely in the set it would read
   *"Ranked by RB + PICKS value only"*. Reuse the already-computed
   `filterPosLabel` (`:574-577`), which renders canonical `"RB + Picks"`. This is a
   pre-existing wart that D2 makes user-visible, so fixing it is in scope by
   necessity, not a drive-by.
3. **`:931` drill subline suffix.** `' starter' | ' bench'` + `' value'` — append
   `' + picks'` when `picksInView && subset !== 'all'`, e.g. *"#3 of 12 · 14,205
   starter + picks value"*.

**Type-floor check (teardown S2 PRD-04, `docs/design/design-system.md:107`):** all
three strings reuse existing styles — `type.bodySm` (13px,
`mobile/src/theme/chalkline.ts:135-139`) and `type.data` (13px, `:148-153`). **No
new text style, nothing at or below 11px, no new component.** Dynamic Type caps
(`:109`) are inherited unchanged.

---

## 4. Approach: client-only. Proven.

**The payload already carries everything needed. No backend change.**

Proof, three legs:

1. **Shape.** `picks: {count, value, items[]}` is a **team-level** field on every
   `PowerRankedTeam` (`mobile/src/api/league.ts:569-587`), emitted for every team on
   every response, with no dependency on `starters` or on `positions`
   (`docs/api-reference.md:350`: *"`total_value = positions_value + picks.value`
   (`positions_value` = players-only sum, so clients can decompose)"*). Leagues
   without pick data get `{count:0, value:0.0, items:[]}` — the client's `hasPicks`
   guard (`:369`) already handles that and old servers that omit the field.
2. **Already read in the subset code paths.** The client reads `team.picks.value`
   at `:266`, `:369`, `:1279` and `team.picks.items` at `:1018-1048` — all inside
   functions that run for **every** subset. The values are in scope right now and
   are being multiplied by zero. The fix is deleting guards, not adding data.
3. **Nothing subset-scoped is missing.** The only server-derived subset artifact is
   `teams[].starters` (a `player_id` list). Picks have no player ids and belong to
   no lineup slot, so there is nothing for the server to compute per subset — which
   is exactly why D1 chose "identical in all three" over "allocate".

**Therefore: mobile-only, single file, no API-contract change, no schema change, no
new flag.** This keeps G3 on the **polish path** (the orchestrator's stated
condition for feature-path escalation — "if the payload lacks the data" — does not
fire).

**Sketch of the change surface** (for the Author's PRD; not code):

| # | `LeagueSummaryScreen.tsx` | Change |
|---|---|---|
| 1 | `:260-270` `activeTotal` | empty-filter branch: `subset === 'all' ? total_value : coreTotal + (picks?.value ?? 0)`; `'PICKS'` branch: drop the `subset === 'all' ?` guard |
| 2 | `:370` `showPicksKey` | `= hasPicks` |
| 3 | `:542-551` `togglePos` | auto-add `'PICKS'` on the `prev.size === 0 → non-empty` transition when `hasPicks` and `pos !== 'PICKS'` |
| 4 | `:555-565` `switchSubset` | delete the PICKS-stripping block; becomes a plain `setSubset` |
| 5 | `:779-785` hint copy | D5.1 + D5.2 (introduce `picksInView`) |
| 6 | `:931` drill subline | D5.3 |
| 7 | `:1016-1018` drill picks group | drop `subset === 'all' &&` |
| 8 | `:1266-1271` `shownBase` | include `'PICKS'` in the unfiltered base for every subset |
| 9 | `:1277-1280` `segValue` | drop the `subset === 'all' ?` guard |
| 10 | `:159-162`, `:255-259`, `:366-368`, `:553-554`, `:1013-1015`, `:1233-1240` | **Retire the "picks are neither starters nor bench" rule in all six comment sites** and state the new rule + the D1 double-count consequence. A reversal that leaves five contradicting comments behind is a half-done reversal. |

Note that after change 9, `BarColumn`'s `subset` prop is read by nothing except the
(now-removed) guards. **Do not delete the prop** — it is still passed at `:826` and
removing it is an unrelated refactor (principle 3). Flag it for a follow-up only if
lint complains.

---

## 5. Platforms touched

| Platform | Touched | Why |
|---|---|---|
| **Mobile** (`mobile/src/screens/LeagueSummaryScreen.tsx`) | **Yes** | The entire defect and the entire fix |
| **Mobile Maestro** (`mobile/.maestro/flows/…`) | **Yes** | Feature-gate 2 — new flow (§8) |
| **Backend** (`backend/`) | **No** | §4 proves the payload is complete. Also: G1 and G2 own backend files; staying out is both correct and collision-free |
| **Web** (`web/league-rankings.html`) | **No** | §1.5 — no subset control, no position filter, picks already unconditional |
| **Extension** | **No** | Does not consume `/api/league/power-rankings` |
| **Docs** | **Yes** (see §7) | `docs/api-reference.md` not required (no route change); the screen's own header comment + this item folder carry the rule |

**Decisive answer to the orchestrator's escalation question: no backend dependency.
G3 stays a polish-path, mobile-only change.**

---

## 6. Risks

| # | Risk | Assessment | Mitigation |
|---|---|---|---|
| R1 | **Re-sort / rank coherence (#208)** | **Low.** `picks.value` is basis-independent (`_power_picks_by_owner` has no `basis` param, `backend/server.py:18876`), so it is the *same* constant on both bases. `boardsDifferInView` (`:457-463`) compares differences and is invariant under a shared constant. #208's fix survives. | Pin with a test that a QB-filtered view with identical QB boards still hides ticks (§8, T5) |
| R2 | **Mirrored filters (#237)** | **Low.** All edits land in shared derivations + `BarColumn`; neither control set gains local state. | T4 asserts chart-card and drill-panel pills agree after every toggle |
| R3 | **#248 combined bars / `boardsDiffer`** | **Low.** Overlay reuses `computeSubset`+`activeTotal` verbatim (`:424-439`), so ticks/chips move with the bars. `otherStartersAvailable` degradation untouched. | T5; visual check that no tick clips (shared `scaleMax`) |
| R4 | **Starters + Bench no longer partition All** (picks counted twice across the two views) | **Accepted, intrinsic to the ruling.** Never surfaced as a sum on screen. | Must be written in the PRD and in the header comment; D5.1 copy stops claiming "only" |
| R5 | **A position filter now reads as "position + picks"** — a team with heavy draft capital can outrank a better RB room in the RB view | **Accepted; this IS the ruling.** Mitigated by three visible signals: the colored Picks base segment, the lit Picks pill, and the #243 caption text | D2's one-tap opt-out preserves the position-pure view |
| R6 | **11px type floor** (`design-system.md:107`) | **None.** D5 adds no new style; both reused styles are 13px | Restate in the PRD's docs table |
| R7 | **A Maestro flow asserts "Picks only in All"** | **None found.** `grep -rn "league-summary" mobile/.maestro/` returns only `league-summary.league-home` (3 rookie flows). `flows/smoke/09-league.yaml` taps `tab.league` then waits on `league.hero` (a `LeagueScreen` testID, `LeagueScreen.tsx:417`) and never touches the chart. **No existing flow can break, and the rankings chart currently has zero Maestro coverage** | Fix the gap with T1–T4 (§8) |
| R8 | `mobile/tests/check-member-entered-marker.js` (surface 5/5, `:240-244`) | **Low.** It asserts the marker is unconditional *inside the priced row* and imported from the shared module — the section-level gate is outside its scope, and broadening it only makes the marker render more | Run `node mobile/tests/check-member-entered-marker.js` **unmodified**; if it fails, the implementation is wrong, not the test |
| R9 | **#279/#285 label vs. the now-picks-inclusive number** | **Low, by leaving the gate alone.** `total_value_label` stays confined to All + no filter, where `active === total_value` and the label reconciles | Explicit "do not widen the label gate" line in the PRD; T6 |
| R10 | **`hasPicks === false` leagues** (ESPN without `picks.assign_tradeable`, demo) | **None.** `hasPicks` (`:369`) short-circuits the pill, the legend, the auto-add and (via `items.length`) the drill group. Zero-value segments are already skipped at `:1344` | T7 asserts no Picks pill appears in a demo league |
| R11 | **`positions_value` vs `coreTotal` drift** — All-unfiltered returns the server's `total_value` (which counts out-of-core "Other" players, all currently valued 0) while Starters/Bench resum `coreTotal` | **Pre-existing**, unchanged by this work. Out-of-pool rows are priced 0 (api-reference.md:350) and IDP/DST rows are omitted from `roster` (#183) | Note only; do not "fix" it here (principle 3) |
| R12 | **testID lint** | Only if the Author adds a testID. Any new one must exist in `mobile/src` and pass `mobile/scripts/testid-lint.sh`; registry conventions in `docs/plans/mobile-testing/lld.md` §2.6/§4.4 | Prefer reusing existing IDs (§8) — the flows below need **no new testID** |

---

## 7. File ownership — proposed, and collision-checked

**G3 owns, exclusively:**

| Path | Kind |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | code (sole code file) |
| `mobile/.maestro/flows/league/lr1-picks-in-subsets.yaml` | new test flow |
| `mobile/.maestro/flows/league/lr2-picks-in-position-filter.yaml` | new test flow |
| `docs/feedback/items/293-picks-in-subsets/` (`plan.md`, `prd.md`, `status.md`, screenshots) | docs |
| `docs/feedback/items/INDEX.md` | docs — **shared-append risk, see below** |
| `living-memory/CHANGELOG.md`, `living-memory/TEST_LEDGER.md` | docs — **shared-append risk, see below** |

**Collision check against the parallel groups:**

| Group | Owns | Overlap with G3 |
|---|---|---|
| G1 | `backend/draft_board_service.py`, `backend/mfl_service.py` | **None** — G3 touches no backend file |
| G2 | `backend/mock_draft_service.py`, `mobile/src/screens/MockDraftScreen.tsx` | **None** — different screen file |

**No code collisions.** Two coordination notes for the orchestrator, flagged now
rather than at merge:

- **`docs/feedback/items/INDEX.md`, `living-memory/CHANGELOG.md`,
  `living-memory/TEST_LEDGER.md`** are append-only files all three groups will
  write. Either the orchestrator serializes those writes at ship time, or each
  group appends a single self-contained block and conflicts are resolved by
  keeping both. G3 will write one block per file.
- **`mobile/.maestro/flows/league/`** does not exist yet. If G2 also creates flows,
  keep them in separate subdirectories (`flows/draft/` vs `flows/league/`) so the
  directory creation is not a shared edit.

---

## 8. Test plan seed

**Feature-gate 2 (Maestro delta) applies** — this is a user-visible mobile change,
and §R7 established the rankings chart has **zero** existing Maestro coverage. New
flows are required, not optional.

**Existing testIDs sufficient for all four flows (no new IDs, no lint exposure):**
`league-summary.subset.{all,starters,bench}` (`:1159`),
`league-summary.roster-subset.*` (`:938`),
`league-summary.posfilter.{qb,rb,wr,te}` + `league-summary.posfilter.picks`
(`:1218`, prefix at `:757`),
`league-summary.roster-posfilter.*` (`:944`),
`league-summary.bar.<user_id>` (`:1292`),
`league-summary.roster-picks` (`:1019`),
`league-summary.filter-caption` (`:765`),
`league-summary.roster-close` (per the #243 comment),
`league-summary.avg-line` (`:859`).

Conventions: **id selectors only**, no fixed `sleep`, no coordinate taps, no
text-selector taps (`mobile/scripts/testid-lint.sh:16-23`); registry + rules in
`docs/plans/mobile-testing/lld.md` §2.6 / §4.4. Seed against the hermetic
`qa_standard` profile used by `flows/smoke/09-league.yaml`, extended so the seeded
league carries owned picks (a league with `hasPicks === false` cannot exercise any
of this — **confirm the seed has pick rows before writing the flows; if it does
not, seeding them is part of the work**).

| # | Flow / check | Asserts |
|---|---|---|
| **T1** | `lr1-picks-in-subsets.yaml` — land on `LeagueRankings`, screenshot All; tap `league-summary.subset.starters`; then `.bench` | The **Picks pill** (`league-summary.posfilter.picks`) and the Picks legend entry are visible in **all three** subsets (today they vanish in two). Screenshot per subset for the visual diff |
| **T2** | same flow, drill-in leg — tap `league-summary.bar.<id>`, switch subset via `league-summary.roster-subset.starters` | `league-summary.roster-picks` is **visible** in Starters and Bench (today: absent). Panel and chart agree |
| **T3** | `lr2-picks-in-position-filter.yaml` — from All, tap `league-summary.posfilter.rb` | `league-summary.posfilter.picks` renders **selected** (D2 auto-add). Tap it → deselected. Tap `league-summary.posfilter.all` → reset. Screenshots at each step |
| **T4** | same flow, mirror leg — open the drill-in, toggle `league-summary.roster-posfilter.rb`, close via `league-summary.roster-close`, re-read `league-summary.filter-caption` | #237 mirroring intact; the caption reads `Starters · RB + Picks` |
| **T5** | **Unit-style guard** (Jest/`node` check under `mobile/tests/`, or an added structural assertion) | `activeTotal`'s basis-invariance: adding the same `picks.value` to both bases leaves `boardsDifferInView` unchanged — the direct #208/#248 regression pin. Preferable to a Maestro flow, which cannot see the boolean |
| **T6** | Manual / flow assertion | With the `aggregate_tier_labels` experiment on (operator account), the `≈N firsts` label still appears **only** in All + no filter, and the Starters/Bench/filtered numeric now includes picks |
| **T7** | Flow against a demo / no-picks league | **No** Picks pill, **no** legend entry, **no** Draft-capital group, in any subset (`hasPicks` guard) |
| **T8** | `node mobile/tests/check-member-entered-marker.js` — **unmodified** | Surface 5/5 still passes (R8) |
| **T9** | `bash mobile/scripts/testid-lint.sh` | New flows reference only existing IDs; no banned patterns |
| **T10** | `cd mobile && npx tsc --noEmit` | Type-clean |

**Existing flows expected to break: none** (R7). `flows/smoke/09-league.yaml` and the
three `flows/rookie/*` flows only use `league-summary.league-home`, which this work
does not touch. If the pre-ship sim gate's tier (matrix in `docs/runbook.md`
§ Pre-ship simulator gate) includes the smoke set, it should pass unchanged — a
useful independent signal that the change is contained.

**Pre-ship gate (feature-gate 4):** run the required tier, log it in
`living-memory/TEST_LEDGER.md`, write `qa/sim-runs/last-sim-run.json`. **No express
declaration has been made by the operator for this group** — full gates apply
(scope block, Maestro delta, docs table, sim run). Agents never self-select express.

**Feature-gate 1 (scope block):** the Author must copy
`docs/templates/feature-scope.md` into `docs/feedback/items/293-picks-in-subsets/`
and fill it. Two rows deserve explicit answers rather than silence:
- **Analytics:** no new events proposed. If the operator wants to know whether the
  Picks opt-out is used, that is a scoped addition specced against the taxonomy up
  front — not a silent add.
- **Docs:** `docs/api-reference.md` = *n/a, no route change*;
  `docs/cross-client-invariants.md` = *n/a, the neutral-Picks rule is preserved
  verbatim*; `docs/data-dictionary.md` / `docs/config-reference.md` = *n/a*;
  `living-memory/LLD.md` = **update** — "picks are neither starters nor bench" is a
  retired client convention and the LLD should not outlive it.

---

## 9. Open items for the Author's PRD

1. **Confirm the hermetic QA seed (`qa_standard`, league
   `990000000000000001`) has owned draft picks.** Every flow in §8 is vacuous
   without them. If absent, seeding is in scope.
2. **Exact final copy for D5.1–D5.3.** The strings above are proposals; the
   operator has overruled copy before (#281 collapsed the chart-encoding hint).
   Keep them short — the #243 dedup work traded away vertical space deliberately.
3. **D2's auto-add: confirm the `prev.size === 0` guard** (auto-add only on the
   first tap out of All, never re-asserted after a deliberate Picks deselection)
   is the behavior the operator wants. This is the one place the plan chose a
   reading the ruling is silent on, and it is the difference between "helpful
   default" and "the pill won't stay off".
