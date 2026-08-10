# PRD — #293 / #294: draft-pick value in Starters/Bench subsets and position filters

- **Group:** G3 (polish path) · **Screen:** `LeagueRankings` = `mobile/src/screens/LeagueSummaryScreen.tsx`
- **Reporter:** `mattmurf77`, app 1.11.0, filed 2026-08-10
- **Branch:** `feedback-289-294` (worktree `.claude/worktrees/fb-289-294`), base `origin/main` @ `7cea1fa`
- **Input:** [plan.md](plan.md) (Planner, Phase 1). Disagreements + corrections logged in
  [reconciliation-log.md](reconciliation-log.md).
- **Phase:** 1 — contract only. No production code in this document.
- **Operator decisions (2026-08-10), all five items:** seeding → Option B · R-6 rule B → keep ·
  analytics → waived · `cross-client-invariants.md` append → approved (orchestrator applies) ·
  **flag → OVERRIDDEN: G3 ships behind a flag.** *"Aligned to all recommendations but ship with
  G3 flagged."* The flag is specified in **R-0** and is the reason every other requirement is
  now stated as flag-conditional.

**Verbatim reports**

- **#293:** "Starters and bench tabs don't have the pick values"
- **#294:** "Neither do the position specific filters"

**Operator ruling (the contract):** *"I'm talking about picks for value."*

> A team's draft-pick value contribution is **subset-independent and filter-independent**.
> Switching to Starters or Bench, or filtering to a position, must never make a team's
> value silently drop by the amount of its draft capital.

---

## 0. Verification status of the plan's citations

Every load-bearing citation in [plan.md](plan.md) was re-checked against the worktree.
**All code citations are accurate.** Six things the plan got wrong or did not cover are
corrected below and carried into the requirements; they are the reason this PRD is not a
restatement of the plan.

| # | Plan claim | Verdict |
|---|---|---|
| V1 | `activeTotal` at `:260-270`; `coreTotal` at `:251`; `showPicksKey` at `:370`; `switchSubset` at `:555-565`; `shownBase` `:1266-1271`; `segValue` `:1277-1280`; drill group `:1016-1018`; copy at `:779`/`:784`/`:931`; label gates `:927-928`/`:1062-1063`; `teamPosRank` `:498-511`; `boardsDifferInView` `:457-463` | **Correct**, verbatim |
| V2 | `picks {count,value,items}` is a team-level field, `mobile/src/api/league.ts` | **Correct** (block runs ~`:567-587`; field names verified). `docs/api-reference.md` `/api/league/power-rankings` row confirms `total_value = positions_value + picks.value` |
| V3 | `picks.value` is basis-independent (`_power_picks_by_owner` takes no `basis`) | **Correct** — `backend/server.py:18876` signature is `(league_id: str, fmt: str)`. D3's safety argument holds |
| V4 | `mobile/tests/check-member-entered-marker.js` is unaffected | **Correct** — its assertions are scoped to the priced row (`pricedRowAncestor`); the section-level gate is outside them |
| V5 | Zero Maestro coverage of the rankings chart | **Correct** — only `league-summary.league-home` is referenced, by 3 rookie flows |
| **C1** | "**no new testID, no lint exposure**" (§8, R12) | **WRONG.** Proven by probe: 6 templated ID families fail `testid-lint.sh`. See §7.1 |
| **C2** | Seed picks "confirm … if it does not, seeding is part of the work" (open item 1) | **Answered: the seed has NO picks at all.** See §7.2 — this is the largest correction |
| **C3** | Bar-segment composition | **Incomplete.** `segSum` (`:1283`) / segment heights (`:1348`) are unanalyzed; a partial implementation renders a bar that looks right and encodes a lie. See R-3 |
| **C4** | D2's `prev.size === 0` auto-add | **Incomplete.** The rule makes the position pill non-reversible. See R-6 / §8 |
| **C5** | "six comment sites" | **Seven.** The plan missed `PosFilterPills`' doc comment at `:1176-1181`. See R-9 |
| **C6** | `docs/cross-client-invariants.md` = "n/a, the neutral-Picks rule is preserved verbatim" | **WRONG.** That rule is **not in the doc**. See §9.3 |

---

## 1. Problem

Draft capital is a real, tradeable component of a dynasty roster, priced server-side on the
generic ladder and already summed into `total_value`
(`docs/cross-client-invariants.md:317`; `docs/api-reference.md` § `/api/league/power-rankings`).
On `LeagueRankings` that contribution **silently evaporates** the moment the user narrows
the view. Today:

| Subset | Filter | Picks counted? | Evidence |
|---|---|---|---|
| All | none | **Yes** | `:262` returns `team.total_value` |
| All | `{QB…TE}` | **No** | `:267` |
| All | `{PICKS}` | Yes, exclusively | `:266` |
| Starters / Bench | none | **No** | `:262` returns `coreTotal` (`:251`, players only) |
| Starters / Bench | any | **No** | `:266` — `'PICKS'` contributes a literal `0` |

Three of the four axes drop it to zero with no caption, no dimmed pill and no explanation.
A rebuilding team holding four 1sts ranks like a team holding none. #293 and #294 are the
same defect seen from two angles, and both reproduce on `origin/main` @ `7cea1fa`.

This is a **deliberate, seven-times-documented design** ("picks are neither starters nor
bench"), so the work is a **design reversal**, not a patch: the old rule must be retired
everywhere it is written down, not just where it is arithmetic.

## 2. Goal

Encode the ruling: **draft-pick value is a permanent, subset-independent, filter-independent
component of a team's charted value. It may be excluded only by an explicit, visible user
action — never as a side effect of changing subset or position.**

---

## 3. Behavioral specification — every view, exhaustively

> **Flag scope of this section.** Everything in §3 and §4 describes the **flag-ON** state
> (`league.picks_always_counted = true`). With the flag **OFF** — the default, and what every
> user gets until the operator flips it — every cell marked *(new)* reverts to the value in its
> *(was …)* annotation, i.e. exactly `origin/main` @ `7cea1fa`. R-0 defines OFF normatively.

Notation: `P` = `team.picks.value ?? 0` · `C` = `coreTotal` (`:251`, QB+RB+WR+TE under the
subset, players only) · `T` = `team.total_value` (server-authoritative, already includes `P`)
· `posValues[p]` per `:239-250`. `hasPicks` = `teams.some(t => (t.picks?.value ?? 0) > 0)`
(`:369`). All rows below assume `hasPicks === true`; §3.3 covers the false case.

### 3.1 Chart card — team value, bar composition, sort key

| # | Subset | Filter | Team value (`active`) | Picks in the bar? | Picks pill | Picks legend key | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | All | `{}` | `T` *(unchanged)* | Yes, base segment | rendered, **unselected** | rendered | `active` desc, `user_id` asc tiebreak |
| 2 | Starters | `{}` | **`C + P`** *(was `C`)* | **Yes, base segment** *(new)* | **rendered**, unselected *(new)* | **rendered** *(new)* | same |
| 3 | Bench | `{}` | **`C + P`** *(was `C`)* | **Yes** *(new)* | **rendered** *(new)* | **rendered** *(new)* | same |
| 4 | All | `{p}`, one core position | `posValues[p] + P` *(auto-add, R-6)* | Yes | rendered, **selected** | rendered | same |
| 5 | Starters / Bench | `{p}` | **`posValues[p] + P`** *(was `posValues[p]`)* | **Yes** *(new)* | **rendered, selected** *(new)* | **rendered** *(new)* | same |
| 6 | any | `{p, q, …}` multi-position | `Σ posValues + P` | Yes | rendered, selected | rendered | same |
| 7 | any | `{p}` with Picks deselected | `posValues[p]` — picks excluded | **No** | rendered, **unselected** | rendered | same |
| 8 | All | `{PICKS}` alone | `P` — the picks-only league ranking, **preserved** | Yes (the whole bar) | rendered, selected | rendered | same |
| 9 | **Starters / Bench** | `{PICKS}` alone | **`P`** *(was `0`)* | **Yes** *(new)* | rendered, selected | rendered | same |

Rows 2, 3, 5, 9 are #293/#294. Rows 1, 7, 8 are unchanged behavior and are listed so a build
agent can see what must **not** move.

**Stacking order is unchanged** in every row: QB→RB→WR→TE top-down, Picks at the base
(`:1272-1276`, `#195`).

### 3.2 Drill-in roster panel (the focused state)

The panel shares `subset` and `posFilter` with the chart card (`:936-949`, `#237`) — one
state, two mirrored control sets — so every row of §3.1 applies unchanged to the panel's
`SubsetControl` and `PosFilterPills`.

| # | Subset | Filter | Position groups shown | "Draft capital" group |
|---|---|---|---|---|
| 10 | All | `{}` | QB, RB, WR, TE, Other | rendered *(unchanged)* |
| 11 | **Starters / Bench** | `{}` | QB, RB, WR, TE | **rendered** *(was: absent)* |
| 12 | any | `{p, …}` incl. `PICKS` | only the selected core positions, canonical order (`:1101-1103`) | **rendered** *(was: absent under any position filter)* |
| 13 | any | `{p, …}` Picks deselected | only the selected core positions | not rendered |
| 14 | any | `{PICKS}` alone | **none** — `groupRows` returns `[]` (`:1101`, `selected` is empty) | rendered — the only content in the panel |

Row 14 is verified, not assumed: `groupRows(rows, filter)` builds `order` from
`CORE_POSITIONS.filter(k => filter.has(k))` when `filter.size > 0`, which is `[]` for
`{PICKS}`. A picks-only panel showing only draft capital is correct and honest.

The `items.length > 0` term of the render condition stays — a team with no owned picks shows
no group even in a league that has them.

### 3.3 `hasPicks === false` (ESPN without `picks.assign_tradeable`, demo, old servers)

**Nothing on this screen changes in any subset or filter.** No Picks pill, no legend key, no
base segment (`P = 0`, and zero-value segments are already skipped at `:1344`), no
Draft-capital group (`items.length` is 0), no auto-add (R-6 is gated on `hasPicks`), and
none of the three copy strings takes its new branch (`picksInView` is gated on `hasPicks`).

---

## 4. The named consequence: Starters + Bench no longer partition All

Under this ruling `P` is counted in **both** halves:

```
starters_active + bench_active  =  (C_start + P) + (C_bench + P)
                                =  positions_value + 2·P     ≠  total_value
```

This is **intrinsic to the operator's ruling**, not a defect of the implementation. The same
constant is deliberately present in both views because draft capital belongs to neither
lineup group and the ruling forbids zeroing it in either.

**How this is communicated in the UI — the honesty requirement.** The screen never displays
`starters + bench` as a sum, so no double-count is ever shown to a user. What *would* be
dishonest is the current copy, which claims exclusivity. Three signals carry the disclosure,
and **no new banner, caption or text block is added** (the #243 dedup work traded that
vertical space away deliberately):

1. **The hint copy stops claiming "only"** and names the second component — R-8.1. This is
   the primary, explicit disclosure: *"Best starting lineup + draft capital."*
2. **The bar visibly contains a neutral Picks block** at its base in Starters and Bench, with
   the matching legend swatch — a user can see the pick contribution, not just be told.
3. **The drill subline names it** — *"#3 of 12 · 14,205 starter + picks value"* (R-8.3) — and
   the Draft-capital group is listed in the panel.

The non-partition fact is additionally recorded in the screen's own header comment (R-9), so
the next reader of this file does not re-derive the old rule.

---

## 5. Requirements

Every requirement is independently verifiable and maps to ≥1 test in §7.
Mapping to the reports: **#293** → R-1, R-3, R-4, R-5, R-7, R-8.1, R-8.3.
**#294** → R-2, R-3, R-4, R-6, R-7, R-8.2. Shared: R-0, R-9…R-13.

**Flag conditionality — read this before implementing anything.**

| Requirement | Conditional on the flag? |
|---|---|
| R-1, R-2, R-3, R-4, R-5, R-6, R-7, R-8 | **Yes** — new behavior only when the flag is ON |
| R-0 | The flag itself |
| R-9 (comments), R-12 (lint allowlist), R-13 (registration) | **No** — build-time / documentation, correct in both states |
| R-10 (guardrails), R-11 (no-picks leagues) | **No** — must hold in **both** states |

### R-0 — The kill switch: `league.picks_always_counted`, default OFF

**Name and namespace.** `league.picks_always_counted`.

- **`league.*` is the right family.** It already holds this screen's siblings —
  `league.power_rankings` (the #14 power-rankings feature this screen *is*),
  `league.activity_feed`, `league.unlock_badges_per_member`, `league.unlock_badges_nav_pill`,
  `league.rookie_board_entry`. All are League-surface UI features, which is exactly what this
  is.
- **`picks.*` was considered and rejected.** That family (`picks.owned_sync`,
  `picks.rank_year_labels`, `picks.slot_values`, `picks.assign`, `picks.assign_tradeable`) is
  about pick **data availability and pricing**, cross-client and mostly backend. This flag
  changes neither: `pool_value` and `picks.value` are byte-identical in both states. Filing it
  under `picks.*` would imply it affects pick pricing, which it must not.
- **`_always_counted`, not `_in_subsets`.** The flag governs #293 (subsets) *and* #294
  (position filters); "subsets" would under-describe the second and invite a future reader to
  assume filters are unflagged. The name states the invariant the switch reverses.

**Default: OFF**, per the project's lands-dark convention. The operator flips it at the release
gate. It is a kill switch for a behavior reversal, not a dark launch of new machinery.

**Read site.** Exactly **one**, in `LeagueSummaryScreen.tsx`, alongside the two existing reads
(`useFlag('ux.retap_active_tab')` `:283`, `useFlag('outlook.odds')` `:342`):

```
const picksAlwaysCounted = useFlag('league.picks_always_counted');
```

placed with the other derived state near `hasPicks` (`:369`) so every consumer below it is in
scope. `useFlag` comes from `mobile/src/state/useFeatureFlags.ts` (**note the path — `state/`,
not `hooks/`**).

#### R-0.1 — OFF is byte-identical to `origin/main`

With `picksAlwaysCounted === false`, every one of R-1…R-8 reverts to current behavior. A
reviewer must be able to confirm "flag off ⇒ no observable change" from this table alone:

| Req | Flag OFF — the required behavior | Current line |
|---|---|---|
| R-1 | `filter.size === 0` ⇒ `subset === 'all' ? tc.team.total_value : tc.coreTotal` — **no `+ P`** | `:262` |
| R-2 | `'PICKS'` branch ⇒ `subset === 'all' ? tc.team.picks?.value ?? 0 : 0` — the literal `0` returns | `:266` |
| R-3 | `shownBase` omits `'PICKS'` unless `subset === 'all'`; `segValue('PICKS')` returns `0` unless `subset === 'all'`. `segSum` math unchanged | `:1266-1271`, `:1277-1280` |
| R-4 | `showPicksKey === hasPicks && subset === 'all'` — pill and legend key vanish in Starters/Bench | `:370` |
| R-5 | `switchSubset` strips `'PICKS'` from `posFilter` whenever `s !== 'all'` | `:555-565` |
| R-6 | `togglePos` is the plain toggle — **no** rule A auto-add, **no** rule B exit | `:542-551` |
| R-7 | Drill-in Draft-capital group keeps `subset === 'all' &&` in its condition | `:1016-1018` |
| R-8 | All three strings render exactly today's text: `Best starting lineup only. ` / `Bench only. ` · `` `Ranked by ${[...posFilter].join(' + ')} value only — chart reordered.` `` (raw enum, tap order) · `' starter'`/`' bench'` with no `' + picks'` | `:779`, `:784`, `:931` |

**"Byte-identical" is the acceptance bar, and it is testable:** with the flag OFF, the T-S1
structural check's flag-OFF arm and the Maestro flag-OFF flow (T7, §7.4) must observe today's
behavior. `picksInView` (G7) must itself be flag-gated —
`picksAlwaysCounted && hasPicks && (…)` — or the copy would change while the arithmetic did
not. **G9 (`:784`) is the exception that must NOT gate on `picksInView`** — see R-8.2.

**Scope of this table: a session that starts OFF, at first render.** It is *not* sufficient for
a session that transitions ON→OFF, which is what actually happens when the kill switch is
pulled. That case is **R-0.4**, and it is a separate requirement because the table above cannot
express it.

**Guardrails are NOT flag-gated.** R-10 and R-11 hold in both states: they describe things
that must not move at all.

#### R-0.2 — The flag switches the whole set atomically

**Invariant:** the flag is read **once** into a single boolean, and every gated expression
resolves to **that same value** within a render. There must be **no** state, view or code path
in which some picks behaviors are ON and others OFF.

This is R-3's `segSum` hazard restated at the flag boundary, and it is the specific way a
flagged implementation can go wrong that an unflagged one cannot. Segment heights are
`v / segSum` (`:1348`), not `v / active`: if the flag gates `activeTotal` (R-1/R-2) but not
`shownBase`/`segValue` (R-3) — an easy mistake when a dozen expressions are wrapped one at a
time — a Starters bar grows by `P` while its four position segments silently stretch to fill
it. The bar looks right and misattributes all draft capital to the positions.
**Forbidden:** per-site `useFlag` reads, a second flag, any partial gating.

##### The gated expressions, enumerated

Earlier drafts said "nine sites". That count was wrong (Planner O-5) and, worse, ambiguous —
"site" conflated files, functions, statements and branches, so the assertions built on it could
not be written precisely. **Replaced with an explicit enumeration.** Every gated expression has
an ID; §6, §7.3 and R-0.1 all reference these IDs and nothing else.

| ID | Expression | Line | Gating symbol | Req |
|---|---|---|---|---|
| **G1** | `activeTotal` empty-filter branch | `:262` | `activeTotal` param | R-1 |
| **G2** | `activeTotal` `'PICKS'` branch | `:266` | `activeTotal` param | R-2 |
| **G3** | `showPicksKey` initializer | `:370` | body identifier | R-4 |
| **G4** | `togglePos` rule A (auto-add) | `:542-551` | body identifier | R-6 |
| **G5** | `togglePos` rule B (exit) | `:542-551` | body identifier | R-6 |
| **G6** | `switchSubset` PICKS-strip block | `:555-565` | body identifier | R-5 |
| **G7** | `picksInView` initializer | new, `~:369` | body identifier | R-8 |
| **G8** | hint subset prefix | `:779` | **`picksInView`** (G7) | R-8.1 |
| **G9** | hint filtered branch | `:784` | **body identifier — NOT `picksInView`** | R-8.2 |
| **G10** | drill subline suffix | `:931` | **`picksInView`** (G7) | R-8.3 |
| **G11** | drill Draft-capital group condition | `:1016-1018` | body identifier | R-7 |
| **G12** | `shownBase` | `:1266-1271` | **`BarColumn` prop** | R-3 |
| **G13** | `segValue` `'PICKS'` arm | `:1277-1280` | **`BarColumn` prop** | R-3 |
| **G14** | ON→OFF reconciliation effect | new | body identifier (OFF branch only) | R-0.4 |

**Fourteen expressions, three gating symbols.** The flag reaches them by exactly three routes,
and a build agent must not invent a fourth:

1. **The component-body identifier** — `const picksAlwaysCounted = useFlag('league.picks_always_counted')`,
   the single `useFlag` call. Gates G3–G7, G9, G11, G14 directly, and G8/G10 transitively
   through `picksInView`.
2. **`activeTotal`'s required 4th parameter** (R-1) — because `activeTotal` is module-scope
   (`:260`, declared before `export default function LeagueSummaryScreen()` at `:272`) and
   cannot close over the identifier. Gates G1, G2.
3. **`BarColumn`'s required prop** (below) — same reason: `BarColumn` is module-scope at
   `:1249`. Gates G12, G13.

##### Both boundary crossings are typed, not conventional

Routes 2 and 3 cross a function boundary, and a boundary crossed by convention is a boundary a
build agent can silently fail to cross. Both are therefore made **`tsc`-enforced**:

- **`activeTotal`'s 4th parameter takes no default value.** A defaulted param would let an
  unthreaded call site compile and silently behave as OFF — which is exactly the O-1 defect
  (below). With no default, `npx tsc --noEmit` (T-S4, already in the gate) fails on any missed
  call site.
- **`BarColumn`'s `picksAlwaysCounted` prop is required** — no `?`, no default in the
  destructure. Omitting it is a `tsc` error.
- **Do not** call `useFlag` a second time inside `BarColumn` or inside `activeTotal`.

Pinned by T-S1 assertions 1–3, 13 and 14 (§7.3). Assertions 13 and 14 exist because assertions
1–3 alone are **provably insufficient** — see the two escape hatches documented there.

#### R-0.3 — Client behavior when the flag is absent from the map

`useFlag` is `!!s.flags[key]` (`mobile/src/state/useFeatureFlags.ts:101-103`), so **an absent
key is `false`** — which is today's behavior. That is correct and required here.

**The flag must NOT be added to `LAUNCHED_FLAG_DEFAULTS` (`:44-51`) in this change.** That map
exists because of the feedback-#115 recurrence: a first-ever boot has no cached flag map, and
`{}` hid every gated surface (the operator's build 44 showed no ESPN linking despite the flag
being live). It makes **launched** features visible from first paint. The file says so at
`:42-43`: *"Only add flags here once they are launched — dark features must stay absent so they
default hidden."* A dark flag added there would ship the new behavior to every first boot,
which is precisely the opposite of a kill switch.

Behavior in each first-boot path, all of which must resolve to OFF:

| Path | Result | Why |
|---|---|---|
| First-ever boot, no cache, network pending | `flags = {...LAUNCHED_FLAG_DEFAULTS}` → key absent → **false** | `:54` |
| AsyncStorage hydrate | `{...LAUNCHED_FLAG_DEFAULTS, ...cached}` → key absent from both → **false** | `:67` |
| Network revalidate succeeds | server map carries the key explicitly → server value wins | `:82` |
| Network revalidate fails | hydrated/default map retained → **false** | `:89-91` |

#### R-0.4 — ON→OFF reconciliation: the kill switch must not strand `PICKS` in the filter

**R-0.1 covers a session that starts OFF. It does not cover a session that transitions ON→OFF —
which is the flag's entire purpose.** Adopted from Planner O-3; verified independently below.

On `origin/main` the state (`subset ∈ {starters, bench}` ∧ `PICKS ∈ posFilter`) is
**unreachable**: `switchSubset` strips `PICKS` on the way out of All (`:555-565`) and
`showPicksKey` hides the pill so it cannot be re-added (`:370`). Flag ON makes that state
routine — R-5 removes the strip and R-4 shows the pill, and R-6 rule A puts `PICKS` there by
default. Then the operator pulls the switch. The client picks up the server `false`
**mid-session, with the screen mounted** (`useFeatureFlags.ts:82`), and `posFilter` is component
state that does not reset. The user lands in:

- `activeTotal` OFF branch (`:266`) ⇒ `PICKS` contributes a literal `0`;
- `showPicksKey` OFF (`:370`) ⇒ the Picks pill is **not rendered**;
- ⇒ **an invisible, unremovable filter member silently zeroing part of the view** — precisely
  the failure the `:553-554` comment names ("a stale PICKS selection would zero bars").

Worst case `posFilter === {PICKS}` in Starters: `active` is `0` for every team, so
`heightPct` is `0` (`:1284`) and **no bars render at all**; `avgActive` is `0` so the average
line is hidden (`:849`); the drill panel shows no position groups (`groupRows` returns `[]` for
a picks-only filter, `:1101`) and no Draft-capital group (OFF keeps `subset === 'all' &&`). A
blank chart with nothing on screen explaining it. The only escape is the **All** pill, which is
rendered unconditionally (`:1193`) — so the state is recoverable, but only by a user who
guesses.

**This matters disproportionately.** The whole justification for shipping G3 flagged is that
the flag is a safe instant rollback. A kill switch that corrupts view state at the moment it is
pulled is worse than no kill switch, because it converts "the operator changed their mind" into
"the app broke for whoever was mid-session".

**Requirement.** Add a reconciliation effect, modelled directly on the in-file precedent at
`:362-364` (which falls back to All when `startersAvailable` disappears):

```
useEffect(() => {
  if (!picksAlwaysCounted && subset !== 'all' && posFilter.has('PICKS')) {
    setPosFilter(prev => { const next = new Set(prev); next.delete('PICKS'); return next; });
  }
}, [picksAlwaysCounted, subset, posFilter]);
```

Three constraints on it:

- **It must be a no-op in a never-ON session.** With the flag OFF from first render, `PICKS`
  can never be in `posFilter` while `subset !== 'all'` (G6 strips it, G3 hides the pill), so the
  condition never fires and **R-0.1's first-render byte-identity is not weakened**.
- **It does NOT replace G6.** `switchSubset`'s OFF-path strip is synchronous; the effect runs
  after a render. Removing G6 in favour of the effect alone would introduce one frame of
  zeroed bars on every OFF-path subset switch. Both exist; they are complementary, not
  duplicative. A build agent must not "simplify" one away.
- **Only the OFF branch acts.** With the flag ON the effect must do nothing — `PICKS` in
  Starters is the *correct* state under R-2.

**Scope check:** this is one `useEffect` with an exact in-file precedent four hundred lines
above it. It is not an abstraction and does not breach §9.2.

**Coverage, stated honestly:** R-0.4 has **no executable coverage under Option B** — exercising
it needs `hasPicks === true`, which the hermetic seed cannot provide (§7.2). It is covered by
T-S1 assertion 16 (source-level) and manual pass T-S6c. It joins R-5 on that list (§7.2).

#### R-0.5 — Graduation

**Graduation note — carry this into the flip.** Whoever turns
`league.picks_always_counted` on must, **in the same change**: set it `true` in
`config/features.json`, and add `'league.picks_always_counted': true` to
`LAUNCHED_FLAG_DEFAULTS`. Flipping the server value alone leaves first-boot users on the old
behavior until their first successful `/api/flags` fetch — a silent, hard-to-reproduce split.
The server map stays authoritative both ways, so a later server `false` still kill-switches on
the next revalidate.

### R-13 — Register the flag in all four touches

A flag registered in fewer than four places is a flag that silently does nothing somewhere.
Per the convention recorded for `outlook.odds`
(`docs/api-reference.md`: *"registered dark in all four touches"*):

| # | File | Edit | Verified constraint |
|---|---|---|---|
| 1 | `backend/feature_flags.py` | add `"league.picks_always_counted"` to the `FLAG_KEYS` tuple (`:47`) | `DEFAULT_FLAGS = {key: False for key in FLAG_KEYS}` (`:608`) ⇒ default False automatically. **`FTF_FLAGS` env overrides drop any key not in `DEFAULT_FLAGS` (`:668`), so without this entry the test override in §7.6 is silently ignored** |
| 2 | `config/features.json` | the `_comment_*` + key insert in §6.1 | orchestrator-owned |
| 3 | `backend/tests/fixtures/flags/release.json` | `"league.picks_always_counted": false` | `_validate_profile` refuses a profile override naming a key absent from the base set (`seed_ui_test_db.py:234-236`) — so the flag-ON test run in §7.6 **requires** this entry |
| 4 | `docs/config-reference.md` | new row in the flag table | see scope.md §4 |

**Verified non-impact:** the flag does **not** join `INVENTORY_FLAG_KEYS`
(`seed_ui_test_db.py:108-122`, a separate hardcoded 13-key tuple), so adding it to
`release.json` does **not** force a decision in the five existing profiles and does **not**
invalidate `standard.json`. The hermetic default is therefore OFF everywhere, which is what
§7.6 relies on.

### R-1 — Unfiltered value includes draft capital in every subset *(flag-ON, G1)*

**Signature change, and it is load-bearing.** `activeTotal` is module-scope (`:260`) and cannot
close over the flag, so it gains a **fourth parameter with no default value**:

```
function activeTotal(tc, subset, filter, picksAlwaysCounted: boolean): number
```

**No default.** A defaulted parameter would let a missed call site compile and silently behave
as OFF, which is the O-1 defect below. With no default, `tsc --noEmit` fails on any unthreaded
caller.

**Both call sites must be threaded — this is mandatory, not optional:**

| Line | Memo | Feeds |
|---|---|---|
| `:384` | `ranked` | the **bars**, rank numerals, list rows, avg line, drill subline |
| `:433` | `otherByTeam` | the **#248 other-basis overlay** — ticks, delta chips, dual-rank captions |

Verified: `grep -n "activeTotal("` returns exactly these two call sites plus the declaration.
**If a third ever appears, it must be threaded too** (T-S1 assertion 13 pins the count).

**Why `:433` is not optional** — the trap this PRD previously walked into. `:433` sits inside
`:424-467`, which R-10's first guardrail forbade changing. A build agent satisfying both would
have defaulted the parameter and threaded only `:384`. Then `r.active` includes `P` and
`o.active` does not, so for every team holding picks the two differ by exactly `P`, and
`boardsDifferInView` (`:457-463`) — a pure difference comparison — flips true wherever
`boardsDiffer` already holds. `ticksOn` fires, and **Starters/Bench draw a dashed tick and a
rank-swing chip on every column**, with each tick sitting systematically low by `P`: a
fabricated, biased "your other board rates this team lower" signal on every bar. That is
**#208's exact reported symptom, reintroduced by the fix for #293** — and R-10 previously
mandated it. R-10 is amended accordingly.

Precision note on the failure, since the spec should not overstate it either: the regression is
bounded by `boardsDiffer` (`:410-414`, an unfiltered `total_value` identity check), so it hits
only callers who *have* a distinct personal board — for everyone else `ticksOn` stays false and
nothing draws. `scaleMax` (`:471-478`) is **not** corrupted: the understated other-basis values
are strictly lower, so the max is unchanged and no tick clips. The delta chips and the tick
heights are the real damage.

**Behavior.** `activeTotal`'s `filter.size === 0` branch (`:261-263`) returns `T` for `all` and
**`C + P`** for `starters` and `bench`.

`all` must keep returning `T` and must **not** add `P` again — `T` already contains it
(`docs/api-reference.md`: `total_value = positions_value + picks.value`). Adding it would
double-count on the one view that was already correct.

`coreTotal` itself stays picks-free; its interface comment at `:227-228` ("players only, no
picks") remains **true** and must not be edited.

**Pass:** for a team with `picks.value > 0`, the Starters and Bench bar values each exceed
their pre-change values by exactly `picks.value`; the All value is byte-identical.

### R-2 — Filtered value includes draft capital in every subset

`activeTotal`'s `'PICKS'` branch (`:266`) drops the `subset === 'all' ?` guard and
unconditionally contributes `tc.team.picks?.value ?? 0` whenever `PICKS ∈ filter`.

**Pass:** with `filter = {PICKS}` the value is `P` in all three subsets (today: `P`, `0`, `0`).

### R-3 — Bar composition stays consistent with the bar's value *(atomic with R-1/R-2)*

`BarColumn` derives segment heights as `v / segSum` where
`segSum = Σ segValue(p) over shown` (`:1283`, `:1348`) — **not** from `active`, which sets
only the bar's overall height (`:1284`). Two edits, which must land **together with R-1/R-2**:

- **`shownBase` (`:1266-1271`)** includes `'PICKS'` in the unfiltered base for **every**
  subset, not just `all`.
- **`segValue` (`:1277-1280`)** drops its `subset === 'all' ?` guard.

**Why atomic.** If R-1 lands without these, a Starters bar grows by `P` while its stack still
contains only the four position segments — which, being percentages of `segSum`, silently
stretch to fill the taller bar. The result *looks* correct and misattributes every point of
draft capital to the position groups. That failure is invisible to a screenshot diff, which
is why it is a named requirement rather than an implementation detail.

**Invariant (mechanically checkable):** for every `(subset, filter)` pair in §3.1,
`segSum === active`, except row 1 (All + no filter), where `active = T` and
`segSum = C + P`; those differ only by out-of-core "Other" players, which are priced 0 today.
That gap is **pre-existing** (plan R11) and is explicitly **not** fixed here.

### R-4 — The Picks pill and legend key render in every subset

`showPicksKey` (`:370`) becomes `hasPicks`, dropping `&& subset === 'all'`. Both consumers of
the pill (`:760` chart card, `:948` drill panel) and the legend swatch (`:882`) follow
automatically. No change to `PosFilterPills`' own rendering (`:1216-1228`).

**Pass:** `league-summary.posfilter.picks` and `league-summary.roster-posfilter.picks` are
present in All, Starters and Bench; the legend shows the "Picks" swatch in all three.

### R-5 — Switching subset never mutates the filter

`switchSubset` (`:555-565`) loses its PICKS-stripping block and becomes a plain `setSubset`.
**Keep the named function** — both `SubsetControl` instances take it as `onSwitch`
(`:940`, and the chart card's instance); inlining it is an unrelated refactor.

**Pass:** with `filter = {RB, PICKS}`, tapping Starters then Bench then All leaves the filter
set and both pill rows unchanged at every step.

### R-6 — Position-filter default membership (the #294 state machine)

Selecting a position must not remove draft capital. `togglePos` (`:542-551`) — the single
shared factory used by **both** pill rows, so the drill panel mirrors automatically — gains
two rules:

| Rule | Condition | Effect |
|---|---|---|
| **A — auto-add** | `pos !== 'ALL'`, `pos !== 'PICKS'`, `prev.size === 0`, `hasPicks` | result is `{pos, 'PICKS'}` |
| **B — exit** | `pos !== 'ALL'`, `pos !== 'PICKS'`, `pos ∈ prev` (a removal), and the result contains **no** core position | result is `new Set()` (= All) |

Existing behavior (`'ALL'` clears; otherwise toggle membership) is otherwise untouched.

Complete state machine, from All (`hasPicks === true`):

| From | Tap | To | Rendered value | Rule |
|---|---|---|---|---|
| `{}` | RB | `{RB, PICKS}` | RB + picks | A |
| `{RB, PICKS}` | Picks | `{RB}` | RB only — explicit, visible opt-out | — |
| `{RB}` | WR | `{RB, WR}` | RB + WR, **no** picks — the opt-out sticks | — (`prev.size ≠ 0`) |
| `{RB, WR}` | RB | `{WR}` | WR only | — (a core position remains) |
| `{RB, PICKS}` | RB | `{}` = All | full value incl. picks | **B** |
| `{}` | Picks | `{PICKS}` | picks only — **shipped capability preserved** | — (`pos === 'PICKS'`) |
| `{PICKS}` | RB | `{PICKS, RB}` | RB + picks | — (`prev.size ≠ 0`) |
| `{PICKS, RB}` | RB | `{}` = All | full value | **B** *(see §8)* |
| any | All | `{}` | full value | existing |
| `{}` (`hasPicks` false) | RB | `{RB}` | RB only | A does not fire |

**Rule B is a correction to the plan, not a restatement.** Without it, `{RB, PICKS}` → tap RB
→ `{PICKS}`: tapping a position off drops the user into a picks-only ranking they never asked
for, and the RB pill stops being reversible — tap-on then tap-off no longer returns you where
you started. Rule B restores the involution for the common gesture. Its one cost is the
second-to-last row, discussed in §8.

**No new state variable.** Rules A and B are memoryless functions of `prev`, `pos` and
`hasPicks`. A sticky "the user turned picks off" flag was rejected: it is a second state axis
with no visible control, and it would make the pill's behavior unexplainable.

**Invariant this preserves — state it in the code comment, in exactly this form:**

> *Whenever the filter is non-empty, the Picks pill's selected state is exactly equal to whether
> pick value is in the chart. An empty filter means every key — including picks — with no pill
> selected.*

**The qualifier is mandatory.** The unqualified version ("the pill's selected state is exactly
equal to whether pick value is in the chart") is **false** in §3.1 rows 1–3: with an empty
filter, `P` is in the chart and the Picks pill reads unselected. That behavior is correct and
conventional — an empty set means "all keys", and the QB pill is likewise unselected in All
while QB value is charted — but the unqualified sentence contradicts it, and R-9 orders these
comments written into a file whose comments are a named deliverable.

The live risk is concrete: an implementer who trusts the unqualified invariant resolves the
contradiction the other way and renders the Picks pill **selected** in the All state, which is
inconsistent with all four position pills and a visible regression. Caught by Planner O-4;
originated in plan.md D2 and adopted here unexamined — a shared miss. The qualified form must
also be used in scope.md §4's `living-memory/LLD.md` row.

### R-7 — Drill-in Draft-capital group renders in every subset and filter

`:1016-1018` drops `subset === 'all' &&`, becoming
`(posFilter.size === 0 || posFilter.has('PICKS')) && (picks?.items?.length ?? 0) > 0`.

`groupRows` (`:951`, `:1088-1111`) is **unchanged** — picks are not a roster section
(`:1086-1087`); the group renders separately, below the position groups.

**Pass:** `league-summary.roster-picks` is visible in Starters and Bench, and under a
position filter with Picks selected; absent when Picks is deselected (row 13).

### R-8 — Copy: three strings, exact before/after

Introduce one local, computed after `hasPicks` (`:369`) and before the return (`:595`):

```
picksInView = hasPicks && (posFilter.size === 0 || posFilter.has('PICKS'))
```

All three strings reuse existing styles — `type.bodySm` (13px,
`mobile/src/theme/chalkline.ts:135-139`) and `type.data` (13px, `:148-153`). **No new text
style, no new component, nothing at or below the 11px floor**
(`docs/design/design-system.md`, Rules line under the type table). Sentence case, no emoji,
no new accent; ice stays on actions, flare is untouched. Dynamic Type caps are inherited.

**R-8.1 — subset prefix (`:779`).** The word "only" is false whenever picks contribute.

| State | Before | After |
|---|---|---|
| `starters`, `picksInView` | `Best starting lineup only. ` | `Best starting lineup + draft capital. ` |
| `starters`, not `picksInView` | `Best starting lineup only. ` | *unchanged* |
| `bench`, `picksInView` | `Bench only. ` | `Bench + draft capital. ` |
| `bench`, not `picksInView` | `Bench only. ` | *unchanged* |
| `all` | `` (empty) | *unchanged* |

**R-8.2 — filtered branch (`:784`).** Two defects, both made user-visible by R-6:
`[...posFilter].join(' + ')` prints the **raw enum** (`PICKS`) **in tap order**. Reuse the
already-computed `filterPosLabel` (`:574-577`), which renders the canonical QB→RB→WR→TE order
with Picks last and title-cased.

**Gate: the raw flag identifier — NOT `picksInView` (G9).** This is the one copy string whose
gate differs, and getting it wrong produces a real spec divergence. Exact expression:

```
picksAlwaysCounted ? filterPosLabel : [...posFilter].join(' + ')
```

**Why not `picksInView`.** R-8.2 is a *casing and ordering* fix, and it must apply whenever the
flag is ON — including when the user has deselected Picks. With filter `{WR, RB}` tapped in that
order, `picksInView` is `false` (no `PICKS` in a non-empty set), so a `picksInView` gate would
fall through to the raw join and print **`WR + RB`** where §3.1 and `filterPosLabel`'s canonical
QB→RB→WR→TE order (`:574-577`, #195) require **`RB + WR`**. Meanwhile R-0.1 requires the raw
enum in tap order when the flag is OFF. Only the raw flag satisfies both. Caught by Planner
O-5; the PRD previously lumped all three strings under one gate and never stated this one.

| | String |
|---|---|
| Before | `` `Ranked by ${[...posFilter].join(' + ')} value only — chart reordered.` `` |
| After | `` `Ranked by ${picksAlwaysCounted ? filterPosLabel : [...posFilter].join(' + ')} value only — chart reordered.` `` |
| Renders, flag ON, filter `{RB, PICKS}` | `Ranked by RB + Picks value only — chart reordered.` |
| Renders, flag ON, filter `{WR, RB}` tapped in that order | `Ranked by RB + WR value only — chart reordered.` |
| Renders, flag OFF | `Ranked by RB + PICKS value only — chart reordered.` — the raw enum in tap order, unchanged |

This is a pre-existing wart (named as a non-goal by the #208 PRD §4) that R-6 promotes from
cosmetic to routinely visible. Fixing it is in scope **by necessity**, not as a drive-by — and
keeping it behind the flag is what preserves R-0.1.

**Considered and rejected: shipping R-8.2 unflagged** as a pure copy fix applying in both
states. It reads cleaner, but it breaks byte-identity on the OFF path, which is the single
property the operator asked for when overriding the unflagged recommendation. A kill switch
that leaves a visible copy change behind is not a kill switch.

**R-8.3 — drill subline suffix (`:931`).**

| | String |
|---|---|
| Before | `` `${subset === 'all' ? '' : subset === 'starters' ? ' starter' : ' bench'} value` `` |
| After | `` `${subset === 'all' ? '' : subset === 'starters' ? ' starter' : ' bench'}${picksInView && subset !== 'all' ? ' + picks' : ''} value` `` |
| Renders | before: `#3 of 12 · 14,205 starter value` · after: `#3 of 12 · 14,205 starter + picks value` |

No other copy changes. The pill label stays `Picks`; the legend label stays `Picks`; the
group header stays `Draft capital`.

### R-9 — Retire the old rule in all **eight** comment sites

A reversal that leaves contradicting comments behind is a half-done reversal. Each site below
states "picks are neither starters nor bench" or a consequence of it, and each becomes false:

| # | Lines | What it says today | Found by |
|---|---|---|---|
| 1 | **`:53-56`** | **file header** — "Position filter …: on change the bars RE-VALUE to the selected position(s) **only** and RE-SORT teams" | **Planner O-7** |
| 2 | `:159-162` | `FilterKey` — "the Picks key only exists in the All subset" | plan |
| 3 | `:255-259` | `activeTotal` header — "picks are neither starters nor bench" | plan |
| 4 | `:366-368` | `showPicksKey` — "AND the All subset is active" | plan |
| 5 | `:553-554` | `switchSubset` — "a stale PICKS selection would zero bars" | plan |
| 6 | `:1013-1015` | drill group — "All subset only" | plan |
| 7 | `:1176-1181` | `PosFilterPills` — "appears only when … the All subset is active" | Author C5 |
| 8 | `:1233-1240` | `BarColumn` — "the neutral Picks segment at the BASE **in the All view**" | plan |

Site 1 is the one **both** the Planner's draft and this PRD missed until Round 2: it is the
top-of-file description of the position filter, the first thing any reader of this screen sees,
and "RE-VALUE to the selected position(s) **only**" is exactly the rule R-2 and R-6 reverse.
Without it, §9.1 criterion 4 could be signed off while the file still teaches the old behavior
in its opening paragraph.

**Line-number correction:** the Planner cited this block as `:54-57`; it is **`:53-56`**
(verified — `:53` is "`//   - Position filter (single OR multi, "All" default): on change the bars`",
`:56` is "`//     to colored outline pills, selected = solid fill.`").

Each site is rewritten to the new rule **and states that it is gated on
`league.picks_always_counted`**, so a reader of the OFF build is not confused by a comment
describing behavior they cannot see. **Exactly one** of them (site 3, `activeTotal`) also
records the §4 non-partition consequence and the R-6 pill invariant in its qualified form.

**Judgment call, flagged not mandated** (Planner's, and I agree with the disposition): `:61-63`
— *"Selecting either recomputes EVERY team's per-position values from that subset and re-ranks
the whole league"* — remains **literally true** (it describes per-position values, which stay
picks-free per R-10) but now reads as a complete account of the subset recompute when it no
longer is. **Extend it; do not block on it.** *(Planner cited `:63-65`; verified as `:61-63`.)*

**Do not edit** `:227-228` (`coreTotal` "players only, no picks" — still true) or `:485`
(the avg-line comment — becomes true in more cases, already correctly worded).

### R-10 — Out-of-scope guardrails (must remain true after the change)

These are requirements, not suggestions; a build agent that "improves" any of them has
failed the PRD.

| Guardrail | Where | Why |
|---|---|---|
| **No ranking / overlay / rank-numeral machinery changes — with ONE mandatory exception** | `:381-391`, `:410-414`, `:424-467`, `:471-478`, `:818`, `:837` | **Exception (required, not permitted-but-optional):** the `activeTotal` call at **`:433`** MUST receive the `picksAlwaysCounted` argument, exactly as `:384` does. Nothing else in these ranges may change — no new memo, no reordering, no altered dependency array beyond what threading the argument requires. **Rationale:** `picks.value` is basis-independent (`_power_picks_by_owner(league_id, fmt)` — no `basis` param, `backend/server.py:18876`), so both bases gain the **same** per-team constant and `boardsDifferInView`, a difference comparison, is invariant under it. That argument — the one this guardrail exists to protect — **is only true if both call sites receive the flag.** The earlier wording asserted the conclusion while forbidding the edit that makes it true (Planner O-1); threading `:433` is what preserves #208's fix and #248's overlay, not what threatens them |
| **`teamPosRank` stays picks-free** | `:498-511` | "your RB room is 3rd of 12" must never be inflated by draft capital. Reads `posValues` only — do not change |
| **`playerPosRank` stays picks-free** | `:516-529` | Player-level. Do not change |
| **Do NOT widen the `total_value_label` gate** | `:927-928`, `:1062-1063` | `subset === 'all' && posFilter.size === 0` stays exactly as-is. #285 computes the label from `positions_value` + a literal whole-team pick count; there is no server-side starters/bench decomposition, so the label is only valid unfiltered on All. Widening it would fabricate. The numeric fallback — now picks-inclusive — is the correct display everywhere else |
| **`BarColumn`'s `subset` prop is not deleted** | `:826`, `:1249-1254` | After R-3 nothing reads it, but removing it is an unrelated refactor. Verified safe: `mobile/tsconfig.json` sets only `strict`, and `expo/tsconfig.base` sets no `noUnusedLocals`/`noUnusedParameters`, so the unused prop does **not** break `tsc` |
| **No backend production *logic* change** | `backend/` | The payload already carries everything — no route, serializer, pricing or query change. **Amended by the flag override:** R-13 adds one string to the `FLAG_KEYS` tuple in `backend/feature_flags.py` and one key to `backend/tests/fixtures/flags/release.json`. Those are registry entries with no behavioral effect (`DEFAULT_FLAGS` makes it False), and they are the *only* permitted backend edits. G1 owns `draft_board_service.py`/`mfl_service.py` and G2 owns `mock_draft_service.py` — **neither touches `feature_flags.py`, so this stays collision-free**; if another group adds a flag in the same window, the `FLAG_KEYS` tuple is an append-only conflict resolved by keeping both. (Test **fixtures** beyond `release.json` are a separate question — §7.2) |
| **No web / extension change** | `web/league-rankings.html` | Renders the picks segment unconditionally and has neither a subset control nor a position filter; the extension does not consume this route. Mobile-only defect |
| **`positions_value` vs `coreTotal` drift is not fixed here** | R-3 note | Pre-existing (plan R11) |

### R-11 — No-picks leagues are untouched

§3.3 in full: with `hasPicks === false`, every rendered element and every value on the screen
is byte-identical to today, in all three subsets and under every filter.

### R-12 — `testid-lint.sh` stays green

`mobile/scripts/testid-lint-allow.txt` gains the entries listed in §7.1, so the new flows do
not fail the CI job `maestro-testid-lint` (`.github/workflows/ci.yml:38-42`).

---

## 6. Change surface (informative — R-0…R-13 are the contract)

Rows carrying a **G-ID** are gated expressions (R-0.2's enumeration). Where the table says
"drop the guard", read: "take the new branch when the flag is ON, the current branch when it is
OFF".

| # | Site | Change | G | Req |
|---|---|---|---|---|
| 0 | `~:369` | `const picksAlwaysCounted = useFlag('league.picks_always_counted')` — **the only `useFlag` read** | — | R-0 |
| 1 | `:260` `activeTotal` **signature** | **required 4th param, no default** | — | R-1 |
| 1a | `:262` empty-filter branch | `+ P` for starters/bench when ON | **G1** | R-1 |
| 1b | `:266` `'PICKS'` branch | drop the `subset === 'all' ?` guard when ON | **G2** | R-2 |
| 1c | `:384` **and `:433`** call sites | thread the argument at **both** — `:433` is mandatory | — | R-1, R-10 |
| 2 | `:370` `showPicksKey` | `= hasPicks` when ON | **G3** | R-4 |
| 3 | `:542-551` `togglePos` | rule A (auto-add) + rule B (exit) when ON | **G4, G5** | R-6 |
| 4 | `:555-565` `switchSubset` | skip the stripping block when ON | **G6** | R-5 |
| 5 | `~:369` | new local `picksInView`, itself flag-gated | **G7** | R-8 |
| **6a** | `:779` + `:931` | copy, gated **via `picksInView`** | **G8, G10** | R-8.1, R-8.3 |
| **6b** | `:784` | copy, gated on the **raw flag** — *not* `picksInView` | **G9** | R-8.2 |
| 7 | `:1016-1018` | drop `subset === 'all' &&` when ON | **G11** | R-7 |
| 8 | `:820` `<BarColumn>` | **new required prop** `picksAlwaysCounted={picksAlwaysCounted}` — bare identifier | — | R-0.2 |
| 8a | `:1249-1264` `BarColumn` signature | prop **required** (no `?`, no default) | — | R-0.2 |
| 8b | `:1266-1271` `shownBase` | include `'PICKS'` in every subset when ON | **G12** | R-3 |
| 9 | `:1277-1280` `segValue` | drop the guard when ON | **G13** | R-3 |
| **10** | new `useEffect` near `:362-364` | ON→OFF reconciliation, OFF branch only | **G14** | R-0.4 |
| 11 | **8** comment sites (R-9 table) | retire the old rule, **and state the flag** | — | R-9 |
| 12 | `mobile/scripts/testid-lint-allow.txt` | 5 glob entries | — | R-12 |
| 13 | `backend/feature_flags.py` `FLAG_KEYS` | one tuple entry | — | R-13 |
| 14 | `backend/tests/fixtures/flags/release.json` | `"league.picks_always_counted": false` | — | R-13 |
| 15 | `config/features.json` | `_comment_*` + key (§6.1) — **orchestrator-owned** | — | R-13 |
| 16 | `docs/config-reference.md` | flag-table row | — | R-13 |

**One code file.** `mobile/src/screens/LeagueSummaryScreen.tsx`, plus the allowlist, the two
flag-registry entries, and the test artifacts in §7. No new component, no new token, no new
hook, no extracted helper, **no second flag** — the change is guard-swapping plus two derived
locals. **This PRD does not authorize a refactor** (`docs/coding-guidelines.md` principle 3).

**R-9 amendment under the flag:** each of the **eight** comment sites states the new rule **and**
that it is gated on `league.picks_always_counted`, so a reader of the OFF build is not
confused by a comment describing behavior they cannot see.

### 6.1 Proposed `config/features.json` insert (orchestrator-owned)

Placed in the `league.*` neighbourhood, next to `league.rookie_board_entry` /
`league.power_rankings`. House style matched to `_comment_pick_assign_tradeable` — long, and
precise about ON vs OFF:

```json
  "_comment_league_picks_always_counted": "2026-08-10 feedback #293/#294 (docs/feedback/items/293-picks-in-subsets/). Kill switch for a REVERSAL of shipped behavior on the League rankings chart (mobile LeagueSummaryScreen, route LeagueRankings). The screen shipped with the rule 'picks are neither starters nor bench', so a team's draft capital was counted ONLY in the All subset with no position filter, and evaporated the moment the user tapped Starters, Bench, or any position pill - a rebuilding team holding four 1sts ranked like a team holding none. Operator ruling: 'I'm talking about picks for value' - pick value is subset-independent and filter-independent. ON = activeTotal adds the team's full picks.value in ALL THREE subsets and whenever PICKS is in the position filter; the neutral Picks bar segment, the legend swatch and the Picks pill render in every subset; tapping the first position pill auto-adds PICKS (visible as a lit pill, one tap to opt out) and removing the last position clears the filter; the drill-in 'Draft capital' group renders under every subset and filter; and three hint strings stop claiming 'only' ('Best starting lineup + draft capital.', 'Bench + draft capital.', '... starter + picks value'). A consequence the UI states rather than hides: with picks counted in both, Starters + Bench deliberately no longer partition All (the two are never summed on screen). OFF (default) = every one of those paths takes its pre-#293 branch and the screen is byte-identical to the shipped 1.11.0 build, including the raw 'PICKS' enum in the filtered hint line. The switch is read ONCE into a single boolean and gates the whole set atomically - never a subset of it, because bar SEGMENT heights are percentages of their own sum while the bar's HEIGHT comes from the team total, so a partially-gated build would grow the bar by the pick value while silently stretching the four position segments to fill it. No backend behavior rides this flag: picks.value and pool_value are byte-identical in both states, the payload is unchanged, and _power_picks_by_owner takes no basis argument, so both value bases carry the same per-team constant and the #208/#248 tick-and-delta overlay is invariant either way.",
  "league.picks_always_counted": false,
```

Graduation to `true` must land together with the `LAUNCHED_FLAG_DEFAULTS` entry — R-0.3.

---

## 7. Test plan

Feature-gate 2 applies: this is a user-visible mobile change and the rankings chart has
**zero** existing Maestro coverage (V5). Two blockers found during verification shape the
plan; both are corrections to [plan.md](plan.md) §8.

### 7.1 Blocker C1 — the flows will fail `testid-lint.sh` as written

The plan asserts "no new testID, no lint exposure". **Proven false.** A probe flow referencing
the plan's ten IDs was run through `mobile/scripts/testid-lint.sh` in this worktree:

```
testid-lint: flow references missing testID: league-summary.bar.900000000000000001
testid-lint: flow references missing testID: league-summary.posfilter.picks
testid-lint: flow references missing testID: league-summary.posfilter.rb
testid-lint: flow references missing testID: league-summary.roster-posfilter.wr
testid-lint: flow references missing testID: league-summary.roster-subset.bench
testid-lint: flow references missing testID: league-summary.subset.starters
exit=1
```

The lint cross-checks each flow id against a literal `testID=` grep in `mobile/src`. These six
families are built from template literals (`` testID={`${idPrefix}.${s.key}`} ``, `:1159`,
`:1193`, `:1206`, `:1218`, `:1292`, `:1379`), so the grep cannot see them, and
`mobile/scripts/testid-lint-allow.txt` has **no `league-summary.*` entry**. The job
`maestro-testid-lint` is a CI check.

**Every testID this plan relies on, verified with its source line:**

| testID | Source | Static or templated | Lint |
|---|---|---|---|
| `league-summary.subset.{all,starters,bench}` | `:1159` | templated | **needs allow entry** |
| `league-summary.roster-subset.{…}` | `:1159` (same component, `idPrefix` `:938`) | templated | **needs allow entry** |
| `league-summary.posfilter.{all,qb,rb,wr,te}` | `:1193`, `:1206` (prefix `:757`) | templated | **needs allow entry** |
| `league-summary.posfilter.picks` | `:1218` | templated | covered by the `posfilter.*` entry |
| `league-summary.roster-posfilter.{…}` | `:1193`/`:1206`/`:1218` (prefix `:944`) | templated | **needs allow entry** |
| `league-summary.bar.<user_id>` | `:1292` | templated | **needs allow entry** |
| `league-summary.roster-picks` | `:1019` | **static** | passes today |
| `league-summary.filter-caption` | `:765` | **static** | passes today |
| `league-summary.roster-close` | `:704` | **static** | passes today |
| `league-summary.avg-line` | `:859` | **static** | passes today |
| `league-summary.league-home` | `:616` | **static** | passes today (3 rookie flows use it) |

**R-12 deliverable** — append to `mobile/scripts/testid-lint-allow.txt`, with the constructing
file noted per that file's own convention:

```
# LeagueSummaryScreen.tsx: SubsetControl / PosFilterPills / BarColumn template their ids
league-summary.subset.*
league-summary.roster-subset.*
league-summary.posfilter.*
league-summary.roster-posfilter.*
league-summary.bar.*
```

Add `league-summary.team.*` only if a flow references a list row. Do not add a bare
`league-summary.*` — that would blanket-exempt the four static ids the lint currently checks.

No new testID is created. Flow conventions per `mobile/scripts/testid-lint.sh:16-23` and
`docs/plans/mobile-testing/lld.md` §2.6/§4.4: **id selectors only**, no fixed `sleep`, no
coordinate taps, no text-selector taps. Use `extendedWaitUntil` with a timeout, matching
`flows/smoke/09-league.yaml`.

### 7.2 Blocker C2 — the hermetic QA seed has **no draft picks at all**

The plan left this open ("confirm the seed has pick rows; if it does not, seeding is part of
the work"). **Answered definitively: it does not, and it cannot today.**

- `backend/tests/fixtures/seed_ui_test_db.py` writes **zero** `draft_picks` rows. Its only
  direct table inserts are `elo_history_table` (`:609`), `wrapped_events_table` (`:666`) and
  `app_feedback_table` (`:690`); its DB-helper calls are `upsert_user`, `upsert_league`,
  `upsert_league_members`, `upsert_member_rankings`, `sync_players`, `set_league_scoring`,
  `set_league_total_rosters`, `mark_format_unlocked`, `set_ranking_method`,
  `save_ranking_swipes`, `save_trade_decision`, `create_trade_match`, `create_notification`.
  None of them touches `draft_picks`.
- `build_cassettes` (`:822-868`) emits no `traded_picks` and no `drafts` path, so no sync can
  create rows either.
- `backend/tests/fixtures/profiles/standard.json` has no picks key.
- Therefore `_power_picks_by_owner` returns `{}` → every team gets
  `{count:0, value:0.0, items:[]}` → **`hasPicks === false`** in league `990000000000000001`.

**Consequence:** the plan's T1, T2, T3, T4 are **vacuous** against today's seed — the Picks
pill, legend key, base segment and Draft-capital group can never appear — and T7 (the
no-picks assertion) would pass with **zero implementation**. A flow that cannot see picks
cannot test a picks fix.

**Good news, verified:** the *subset* control is fine. `_league_meta` (`:778-808`) supplies a
real Sleeper `roster_positions` template
(`QB,RB,RB,WR,WR,WR,TE,FLEX,FLEX,SUPER_FLEX` + bench for SF TEP), so `starters_available` is
true and All/Starters/Bench renders in the hermetic world.

**Requirements with NO executable coverage under Option B.** Two, and the PRD must not imply
otherwise:

| Req | Why nothing can exercise it | What covers it instead |
|---|---|---|
| **R-5** (`switchSubset` never mutates the filter) | The only thing `switchSubset` has **ever** stripped is `'PICKS'` (`:558-562`). `RB` survives a subset switch on `origin/main` today, so a position-filtered flow passes identically on fixed and unfixed code, flag ON and OFF. Exercising R-5 needs `PICKS ∈ posFilter` ⇒ needs `hasPicks` ⇒ needs the seed | T-S1 assertion 8 (source) + manual T-S6 |
| **R-0.4** (ON→OFF reconciliation) | Same root cause — needs `PICKS` reachable in a non-All subset, **and** a live flag transition | T-S1 assertion 16 (source) + manual T-S6c |

This is why T6 is now mapped to **no requirement** (Planner O-6): it was previously credited to
R-5 while testing nothing, which would have recorded a false green at QA sign-off. Both rows
join the **Tier B** set, so the follow-up seeding item knows R-5 and R-0.4 are waiting on it.
*(R-0.4's inclusion is mine — the Planner raised R-5 but did not notice that the fix it demands
in O-3 inherits the identical gap.)*

**Two options. Recommendation: Option B.**

**Option A — seed picks now (full coverage, larger blast radius).**
Add an optional `draft_picks` key to the profile schema and a **new** profile
`backend/tests/fixtures/profiles/picks.json` (cloned from `standard`, distinct user/league
ids), plus a seeder step writing `draft_picks` rows via `database.replace_draft_picks`
(`backend/database.py:7896`) with `platform='sleeper'`, `source` NULL, and a `pool_value` from
`pick_values.pick_pool_value(round, years_out, fmt)` — never a hand-written value. Register in
`MVP_PROFILES` (`backend/tests/test_seed_ui_test_db.py:33`).

Use a **new** profile, not `standard`: adding picks to `standard` changes `total_value` for
every team in the league the **whole 11-flow smoke suite** runs against, and owned picks are
injected into suggestion pools (`server._inject_owned_picks`), so deck contents could shift —
destabilising the smoke suite in the same change whose sim gate is a full smoke run (§7.7) is
the wrong trade.

Cost: this makes G3 touch **backend test fixtures**, contradicting the plan's "mobile-only,
single file, no backend change" and roughly tripling the change size for a two-line polish
item.

**Option B — ship Tier A now, defer Tier B (recommended).**
Cover this change with the structural check (T-S1, which needs no seed and pins all nine code
sites mechanically), the no-picks flow, and the mirroring/regression flows; take a **written,
operator-surfaced partial waiver** for the picks-visible Maestro assertions; verify those
manually against the operator's real Sleeper dynasty league during the QA round; and file the
seeding as an immediate follow-up. This keeps G3 surgical and the sim gate stable.

Either way, the underlying gap — **the hermetic world can exercise none of the five priced
pick surfaces** (trade-away picker, swap-suggestions sheet, evener chip, calculator pick rows,
power-rankings draft capital) — is systemic, predates #293, and should be logged rather than
absorbed into a polish item.

**This is the single biggest open decision in G3 and is flagged for the orchestrator.**

### 7.3 T-S1 — structural check (required, seed-independent)

New: `mobile/tests/check-picks-subset-invariance.js`, plus
`"test:picks-subset-invariance": "node tests/check-picks-subset-invariance.js"` in
`mobile/package.json`.

Precedent: six such checks already exist (`check-member-entered-marker.js`,
`check-mock-mode-marker.js`, …). They parse the real TSX with the project's own `typescript`
compiler API and walk the AST — a grep would pass on a guard that merely moved. This is the
direct, mechanical encoding of the operator's ruling, and it is the only test in this plan
that runs with no simulator and no seed.

**Amended for the flag.** Under a flag both branches exist in the source, so the original
"contains no `subset` identifier" assertions would now fail against a correct implementation.
Each is restated as *"the flag-ON arm does X"*, and six flag-structure assertions are added —
these are the ones that catch the R-0.2 atomicity hazard, which no screenshot and no Maestro
flow can see.

| # | Assertion | Pins |
|---|---|---|
| 1 | **exactly one** `useFlag('league.picks_always_counted')` call site in the file | R-0.2 |
| 2 | no `useFlag` call inside `BarColumn` or inside `activeTotal` | R-0.2 |
| **3** | every gated expression **in the component body** (G3–G11, G14) branches on the identifier bound at assertion 1; `BarColumn`'s gated expressions (G12, G13) branch on its `picksAlwaysCounted` **parameter**; `activeTotal`'s (G1, G2) branch on its 4th **parameter** | R-0.2 |
| 4 | `activeTotal`'s flag-ON, empty-filter arm adds `picks` for the non-`all` subset; its flag-OFF arm returns bare `coreTotal` | R-1, R-0.1 |
| 5 | `activeTotal`'s flag-ON `'PICKS'` arm has no `subset` ternary; its flag-OFF arm keeps `subset === 'all' ? … : 0` | R-2, R-0.1 |
| 6 | `showPicksKey`'s flag-ON arm is bare `hasPicks`; its flag-OFF arm keeps `&& subset === 'all'` | R-4, R-0.1 |
| 7 | `segValue`'s flag-ON `'PICKS'` arm has no `subset` ternary; `shownBase`'s flag-ON unfiltered branch includes `'PICKS'` for every subset | R-3 |
| 8 | `switchSubset` calls `setPosFilter` **only** on the flag-OFF path | R-5, R-0.1 |
| 9 | the drill picks group's JSX condition contains `subset === 'all'` **only** under the flag-OFF branch | R-7, R-0.1 |
| 10 | `picksInView`'s initializer references the flag identifier | R-8, R-0.1 |
| 11 | `teamPosRank`'s body contains no `picks` reference | R-10 |
| 12 | `total_value_label`'s two render gates still contain `subset === 'all' && posFilter.size === 0`, and neither references the flag | R-10 |
| **13** | `activeTotal` has **exactly two** call sites and **both** pass the flag identifier as the 4th argument; the declaration's 4th parameter has **no default initializer** | R-1, R-10 |
| **14** | the `<BarColumn>` JSX (`:820`) passes `picksAlwaysCounted={<the identifier from assertion 1>}` as a **bare identifier reference** — not a literal, not a member expression, not any other expression; and the prop is declared **required** in `BarColumn`'s type | R-0.2, R-3 |
| **15** | `:784`'s flag-OFF arm is exactly `[...posFilter].join(' + ')` and its flag-ON arm is `filterPosLabel`; the expression does **not** reference `picksInView` | R-8.2, R-0.1 |
| **16** | the R-0.4 reconciliation `useEffect` exists, its body runs only under `!picksAlwaysCounted`, and it deletes `'PICKS'` from `posFilter` | R-0.4 |

##### Why assertions 13 and 14 are not optional

The orchestrator asked the Planner whether a build agent could satisfy every assertion and still
ship a half-gated screen. **With assertions 1–12 alone the answer was yes, two independent
ways** — both verified against the code, both now closed:

- **Escape hatch 1 (O-1).** `activeTotal` is module-scope with **two** call sites (`:384`,
  `:433`). Assertion 3 checks the function's internals; `:433` is a *call site*, so nothing
  looked at it. A defaulted parameter threaded only at `:384` passes 1–12 and reintroduces
  #208. **Closed by assertion 13** — plus the no-default rule, which makes `tsc` catch it first.
- **Escape hatch 2 (O-2).** G12/G13 live inside `BarColumn`, a separate module-scope function,
  so a parameter binding there is a *different symbol* from the component-body identifier.
  Assertion 3's original "same identifier" wording was therefore either unsatisfiable (read as
  symbol resolution) or a bare name match (gameable). Nothing checked the value actually passed
  at `:820`, so literally `picksAlwaysCounted={false}` — or `{subset === 'all'}` — passed all
  twelve assertions while shipping the exact C3 `segSum` failure. **Closed by the rescoped
  assertion 3 plus assertion 14.**

Assertion 14 is the only mechanical link between the two halves of the atomicity invariant.
Assertions 1–3, 13 and 14 together are the highest-value checks in this plan.

**Honest note:** the six existing checks are **not** wired into CI
(`.github/workflows/ci.yml` runs pytest + `tsc --noEmit` + `testid-lint.sh` only). T-S1 is a
manual / pre-ship check, run via `npm run` and recorded in the ledger. Adding the family to CI
is a worthwhile but separate change — out of scope here.

### 7.4 Maestro flows

New directory `mobile/.maestro/flows/league/` (does not exist yet; G2 should keep its flows in
`flows/draft/` so the directory creation is not a shared edit). Numbered per the sibling
convention in `flows/smoke/` and `flows/rookie/`; header comments carry `tc:`, `profile:`,
`flags:`, `tags:` exactly as `flows/smoke/09-league.yaml` does.

Every flow's header comment records its flag state in the existing `# flags:` field
(`flows/smoke/09-league.yaml` uses `# flags: release`). Flag-ON flows carry
`# flags: release+league.picks_always_counted`; flag-OFF flows carry `# flags: release`.
Forcing mechanics — including two traps — are in §7.6.

| # | Flow | Flag | Steps | Mechanically checkable pass criterion | Req | Seed |
|---|---|---|---|---|---|---|
| **T1** | `01-picks-in-subsets.yaml` | **ON** | sign in → league → `tab.league` → wait `league-summary.subset.all` → screenshot → tap `league-summary.subset.starters` → screenshot → tap `.bench` → screenshot | `assertVisible: id: league-summary.posfilter.picks` **after each** of the three subset taps (today: absent in two of three) | R-1, R-4 | needs picks |
| **T2** | `01-…` drill leg | **ON** | tap `league-summary.bar.<user_id>` → tap `league-summary.roster-subset.starters` → then `.bench` | `assertVisible: id: league-summary.roster-picks` in Starters **and** Bench (today: absent in both) | R-7 | needs picks |
| **T3** | `02-picks-in-position-filter.yaml` | **ON** | from All tap `league-summary.posfilter.rb` → screenshot → tap `league-summary.posfilter.picks` → screenshot → tap `league-summary.posfilter.rb` → screenshot | after step 1 `league-summary.posfilter.picks` is **selected**; after step 2 **unselected**; after step 3 `league-summary.posfilter.all` is **selected** (rule B). **Selector question is OPEN — resolve before authoring, see below.** | R-6 | needs picks |
| **T4** | `02-…` mirror leg | **ON** | tap a bar → tap `league-summary.roster-posfilter.rb` → `assertVisible: league-summary.filter-caption` → tap `league-summary.roster-close` | caption text asserts as **`All · RB + Picks`** (#237 mirroring intact, #243 caption truthful) | R-6, R-8.2 | needs picks |
| **T5** | `03-no-picks-league.yaml` | **ON** | demo / no-pick league → All → Starters → Bench | `assertNotVisible: id: league-summary.posfilter.picks` in all three subsets; `assertNotVisible: id: league-summary.roster-picks` in the drill-in | R-11 | **runs today** |
| **T6** | `03-…` navigation leg | **ON** | tap `league-summary.posfilter.rb` → `league-summary.subset.starters` → `.bench` → `.all` | the subset control and pills survive the round trip without a crash or a blank chart. **Mapped to no requirement** — see below | *(none)* | **runs today** |
| **T7** | `04-picks-flag-off.yaml` — **the no-regression proof** | **OFF** (default) | identical navigation to T1/T6: land on `LeagueRankings` → tap `league-summary.subset.starters` → `.bench` → back to `.all` → tap `league-summary.posfilter.rb` → tap `league-summary.subset.starters` | **(a)** `assertNotVisible: id: league-summary.posfilter.picks` after the Starters and Bench taps — the pill vanishes exactly as it does on `origin/main` (R-4 OFF); **(b)** after tapping RB from All, `assertNotVisible` on the Picks pill — rule A did **not** fire (R-6 OFF); **(c)** screenshots at each step, diffed against the same steps captured on `origin/main` @ `7cea1fa` before the change lands | **R-0.1** | **runs today** |

**T7 is the flow the override adds** and it must pass in the gate regardless of the §7.2
seeding decision. It runs against the **default** hermetic flag set, so it needs no flag forcing
and no pick data.

**What T7 does and does not prove — stated precisely, because the previous draft overclaimed.**
With `hasPicks === false` in the seed, assertions (a) and (b) hold for two independent reasons
(flag OFF *and* no picks), so T7 alone cannot distinguish them. A third assertion —
*"after switching to Starters with RB selected, the filter still shows RB"* — was previously
described as "proving the OFF path is exercised". **It proves nothing** (Planner O-8): `RB`
survives a subset switch on `origin/main`, in a build with no flag at all, and in a build where
the flag was never wired up. Only `PICKS` was ever stripped. That assertion has been **deleted**
rather than reworded — it is the same defect as O-6 and keeping it would launder a false green.

T7's honest job is a **navigation + screenshot-baseline no-regression check**: the screen still
mounts, navigates and renders identically to `origin/main` under the shipped default. The
flag-OFF *arm* is evidenced elsewhere — by T-S1 assertions 4–10 and 15 (source-level,
seed-independent) and by the manual control T-S6b (real pick data). The screenshot baseline in
(c) is genuinely worth having and is why the flow is kept.

T1–T5 are flag-ON. Of those, T1–T4 are additionally **Tier B** under §7.2 Option B — authored
now, tagged `tags: [league, picks]`, and skipped in the gate run until the seed carries picks.
**T5, T6 and T7 are Tier A and run immediately**, T7 with no flag override at all.

##### T3's selector — an open question the build agent must close, not inherit

The previous draft asserted that *"Maestro cannot read `accessibilityState={{selected}}`"*
(`:1221`) and fell back to screenshots. **That claim was unverified, and I could not settle it
here:** `maestro --version` in this worktree fails with *"Unable to locate a Java Runtime"*, no
Maestro version is pinned anywhere in the repo (`docs/plans/mobile-testing/lld.md` names the
binary but not a version), and `grep -rn "selected:" mobile/.maestro/` returns **nothing**, so
there is no local precedent either way.

This matters because **T3 is the only test of the R-6 state machine**, and a screenshot is an
eyeball check, not a gate.

**Required of whoever authors T3:** run `maestro --version` on the gate machine and check that
version's element-matcher docs for selection state. Then either

- **supported** ⇒ use `assertVisible: id: league-summary.posfilter.picks, selected: true|false`
  and demote the screenshots to evidence — T3 becomes three mechanical assertions; or
- **not supported** ⇒ keep the screenshot artifact, and **record the version you checked in the
  flow header comment**, so the next author does not re-litigate this.

Either way the fallback signal stands: the visible Picks base segment corroborates inclusion.

### 7.5 Non-Maestro checks

| # | Check | Pass criterion | Req |
|---|---|---|---|
| T-S1 | `node mobile/tests/check-picks-subset-invariance.js` | all **12** assertions PASS (§7.3) — including 1–3, the only mechanical proof of R-0.2 atomicity | R-0…R-7, R-10 |
| T-S2 | `node mobile/tests/check-member-entered-marker.js` — **unmodified** | surface 5/5 still passes. If it fails, the implementation is wrong, not the test | R-7 |
| T-S3 | `bash mobile/scripts/testid-lint.sh` | exit 0 | R-12 |
| T-S4 | `cd mobile && npx tsc --noEmit` | exit 0. **Baseline confirmed clean in this worktree** (`node_modules` is a real install here — do not symlink the main checkout's, which lacks `@react-native-cookies/cookies`) | all |
| T-S5 | manual, operator account with `aggregate_tier_labels` on | the `≈N firsts` label still appears **only** in All + no filter; Starters/Bench/filtered show the numeric, now picks-inclusive | R-10 |
| T-S6 | manual, real Sleeper dynasty league, **flag ON** (covers T1–T4 under Option B) | walk §3.1 rows 2, 3, 5, 9 and §3.2 rows 11, 12, 14; screenshot each into this item folder | R-1…R-7 |
| **T-S6c** | manual, real league, **live ON→OFF transition** — the kill-switch drill | With the flag ON, filter to Starters and leave `PICKS` in `posFilter` (the R-6 rule A default). Flip `league.picks_always_counted` to `false` server-side and force a client revalidate (background→foreground past the 30-min throttle, or cold start). **Pass:** the chart returns to the `origin/main` Starters view — `PICKS` is gone from the filter, no bars are zeroed, and no invisible filter member remains. **This is the only test of R-0.4, and it is the drill that proves the kill switch actually works.** Run it before the operator is ever asked to rely on it | **R-0.4** |
| **T-S6b** | manual, **same real league, flag OFF** — the paired control | the screen is indistinguishable from the shipped 1.11.0 build: Picks pill and legend absent in Starters/Bench, no Draft-capital group outside All, `Best starting lineup only. `, and the filtered hint still prints the raw `PICKS` enum. **This is the only test that exercises flag-OFF *with real pick data*** — T7 cannot, because the hermetic seed has none. Screenshot the same seven views as T-S6 for a side-by-side | **R-0.1** |

### 7.6 How the flag is forced in each test context

| Context | Flag OFF | Flag ON |
|---|---|---|
| **Maestro / `sim-run.sh`** | nothing to do — `release.json` carries `false` (R-13 touch 3), the profile does not override it, so the hermetic default is OFF | `sim-run.sh … --flags '<json>'` → exported as `FTF_FLAGS` (`mobile/scripts/sim-run.sh:55`) |
| **T-S1 structural check** | n/a — reads source, both branches asserted | n/a |
| **Manual (T-S5, T-S6, T-S6b)** | dev backend with the shipped `config/features.json` | flip the key to `true` in `config/features.json` locally, **or** set `FTF_FLAGS` |
| **Production graduation** | — | operator flips `config/features.json` **plus** `LAUNCHED_FLAG_DEFAULTS` in the same change (R-0.3) |

Precedence is `DEFAULT_FLAGS` → `config/features.json` → `FTF_FLAGS` env
(`backend/feature_flags.py:673-676`), so `FTF_FLAGS` is the right lever for a per-run override.

> **Harness dependency — the orchestrator is fixing `sim-run.sh` in a separate lane.** The
> Planner independently reproduced both traps below and found the root cause: the handshake at
> `sim-run.sh:61` is commented *"whoami reports our profile AND flags round-trip"*, but the
> assertion block (`:67-74`) checks `test_mode`, `fixtures`, `profile` and `pid` and **nothing
> about flags**; two lines later the effective map is fetched and merely archived
> (`:75-76`, `PINNED` → `flags.json`) — never asserted. That is why both traps are silent.
>
> **This test plan therefore assumes that a flag-ON Maestro run will be verifiably flag-ON once
> that fix lands.** Until it does, the repo has no way to run a flag-ON tier and know that it
> did. **Do not edit `qa/` or `mobile/scripts/sim-run.sh` as part of G3** — the two traps below
> are documented here so the person running the gate can work around them by hand, not so a
> build agent fixes them. If the harness fix has not landed by the G3 gate run, the fallback is
> scope.md §5's requirement to paste `report-dir/flags.json` into the TEST_LEDGER entry as
> manual proof of the flag state.

**Two verified traps for whoever runs the flag-ON tier — both would silently produce a
false PASS on flag-OFF behavior, not an error:**

1. **`--flags` REPLACES the seeded map; it does not merge with it.** `sim-run.sh` sets
   `FTF_FLAGS` to the profile's full flag manifest via the seeder's `--print-env` block
   (`:53-54`), then line 55 **overwrites** it wholesale with `--flags`. A partial
   `--flags '{"league.picks_always_counted":true}'` therefore discards every one of the
   profile's `flag_overrides` (for `standard`: `landing.try_before_sync`,
   `trade.finder_targeting`, `trades.queue_2k`, and ten more), silently reverting them to
   `config/features.json` values and changing what the flow is testing. **Pass the seeded map
   with the one key flipped**, e.g. build it from the profile's
   `<out>/<name>.manifest.json` `flags` object rather than hand-writing a one-key object.
2. **`--flags @file` is documented but NOT implemented.** The usage header advertises
   `<json-or-@file>` (`sim-run.sh:5`), but the parser does a bare `FLAGS="$2"` (`:22`) with no
   `@` expansion anywhere in the script. Passing `@flags.json` exports the literal string,
   `_env_overrides` fails the `json.loads` and returns `{}` with only a stdout warning
   (`backend/feature_flags.py:659-663`) — the run proceeds with **every flag from
   `config/features.json`**, i.e. the new flag OFF, and the flag-ON flows quietly assert
   against old behavior. **Use inline JSON.**

Both traps are pre-existing defects in `sim-run.sh`, **not** introduced here and **not** fixed
here — see the harness-dependency note above. Logged in §9.2.

### 7.7 Regression and sim gate

**Existing flows expected to break: none.** `flows/smoke/09-league.yaml` taps `tab.league`
then waits on `league.hero` (a `LeagueScreen` testID) and never touches the chart; the three
`flows/rookie/*` flows use only `league-summary.league-home`. **Re-run as regression:** the
full 11-flow smoke suite (`flows/smoke/01`…`11`) — required by the tier below anyway — plus
`flows/rookie/d1`, `d2`, `r5` as the only other consumers of this screen's ids.

`mobile/tests/check-member-entered-marker.js` — **affected in scope, not in outcome** (T-S2);
run unmodified. `mobile/scripts/testid-lint.sh` — **affected**, see R-12/§7.1.

**Sim-gate tier: 1 — reconfirmed under the flag override.** `docs/runbook.md` § Pre-ship
simulator gate, change class "Mobile screen / navigation / state change": full smoke suite
(11 flows) + this feature's own flows, on simulator, before merge to `main`.

The flag does **not** lower the tier, for two reasons worth stating rather than assuming:

- The matrix keys on **change class**, not on risk-after-mitigation. This is still a mobile
  screen/state change; adding a kill switch does not reclassify it.
- The flag **adds** to the gate rather than subtracting: **both** states must now be exercised.
  Concretely the tier-1 run is the 11 smoke flows (all flag-OFF, unchanged world) **plus**
  T7 flag-OFF **plus** T5/T6 flag-ON — and T1–T4 flag-ON if §7.2 Option A is taken.

A tempting argument for tier 2 — "it lands dark, so users see nothing" — is wrong here: the
whole point of the gate is to validate the build the operator will flip, and an unexercised ON
path is exactly what a kill switch cannot protect against. The 11 smoke flows run flag-OFF and
are the byte-identity evidence.

Log in `living-memory/TEST_LEDGER.md` (recording the flag state of each flow) and write
`qa/sim-runs/last-sim-run.json`. **No express declaration has been made for this group** —
full gates apply; agents never self-select express. Note that a feature-flag surface is on
CLAUDE.md's **bright line**, so express would not have been available for this change without
an explicit confirming yes in any case.

---

## 8. Where the operator's ruling was silent — flagged for the orchestrator

The ruling settles *whether* pick value counts. It says nothing about **what the Picks pill
should do by default once a position filter is active**. R-6 chooses; both halves of the
choice belong to the operator, not to an agent.

**R-6 rule A (auto-add).** The alternative readings and why they lose:

- *"A position filter should show only that position's value"* — coherent, and what ships
  today, but it is exactly what the ruling forbids ("or filtering to a position, must never
  make a team's value silently drop"). R-6 does not discard it: it demotes it from **default**
  to **one visible tap away**.
- *"Picks always count; delete the Picks pill"* — the simplest model and the strongest reading
  of the ruling, but it **deletes shipped capability**: `{PICKS}` alone is today the only
  league-wide draft-capital ranking anywhere in the app. #294 asked for pick value to stop
  vanishing, not for the picks-only view to be removed.
- *"Add an `includePicks` boolean and a new control"* — a second state axis and a second
  control style to express what the existing multi-select pill already expresses truthfully.

**R-6 rule B (exit) is my addition, and its cost is real.** Without it the position pill is
not reversible (`{RB, PICKS}` → tap RB → `{PICKS}`, a picks-only ranking the user never
asked for). With it, one path surprises instead: a user who deliberately started at `{PICKS}`,
added RB, then removes RB lands on **All** rather than back on `{PICKS}`. Distinguishing the
two would require tracking whether `PICKS` was auto-added or hand-selected — a hidden state
axis R-6 explicitly rejects. The common gesture (un-filtering a position you just filtered by)
is protected; the rare one (picks-only → add a position → remove it) costs one extra tap on
the Picks pill. **If the operator prefers the reverse trade, drop rule B** — R-1…R-5 and R-7…R-12
are unaffected.

**Also for the operator, from §7.2:** whether to seed draft picks into the hermetic QA world
now (Option A) or ship Tier A with a written partial Maestro waiver and follow up (Option B,
recommended).

---

## 9. Success criteria

### 9.1 Done means

1. Every row of §3.1 and §3.2 renders as specified **with the flag ON**, verified per §7; and
   **with the flag OFF the screen is byte-identical to `origin/main` @ `7cea1fa`** (R-0.1),
   evidenced by T7 and the T-S6b screenshot pair.
2. R-0…R-13 all pass their named tests; T-S1 (**16** assertions) …T-S4 green; sim-gate tier 1 run
   logged **with each flow's flag state recorded**.
2b. The flag is registered in **all four** touches (R-13) and is **absent** from
   `LAUNCHED_FLAG_DEFAULTS` (R-0.3).
3. #293 and #294 are answerable in one sentence each with a screenshot: *"Starters and Bench
   now include pick value, and the Picks pill and bar segment show it"* / *"A position filter
   keeps pick value by default, and the lit Picks pill says so."*
4. All **eight** comment sites (R-9, including the file header at `:53-56`) no longer state the
   retired rule; each names the flag; and the §4 non-partition consequence plus the R-6 pill
   invariant **in its qualified form** are written down in the file.
5. No guardrail in R-10 has moved — and the one mandatory exception (threading `activeTotal` at
   `:433`) **has** been made.
6. The kill-switch drill T-S6c has been run once: flipping the flag ON→OFF mid-session returns
   the screen to the `origin/main` view with no stranded `PICKS` (R-0.4). The operator is not
   asked to rely on a switch nobody has pulled.

### 9.2 Explicitly out of scope

- Any change to the ranking, overlay, tick, delta-chip or rank-numeral machinery (R-10).
- Widening the #279/#285 `total_value_label` gate (R-10).
- Making `teamPosRank` or `playerPosRank` picks-aware (R-10).
- The `positions_value` vs `coreTotal` "Other"-players drift (R-3 note, plan R11).
- Deleting `BarColumn`'s now-unused `subset` prop (R-10).
- Extracting or refactoring anything in this file.
- Any backend production change; any web or extension change.
- Wiring the `mobile/tests/check-*.js` family into CI (§7.3).
- **Flipping the flag on.** This change lands it dark. Graduation is an operator action with
  its own checklist (R-0.3: `config/features.json` **and** `LAUNCHED_FLAG_DEFAULTS`, same
  change).
- **Any second flag, or gating anything beyond R-1…R-8 on this one.** R-0.2 forbids partial
  gating; it equally forbids scope creep through the flag.
- **Any change to `mobile/scripts/sim-run.sh` or `qa/`.** Three defects are documented in §7.6
  (`--flags` replaces rather than merges; `--flags @file` unimplemented and fails open; the
  handshake never asserts the `PINNED` flag map). All three are pre-existing and all three are
  being fixed by the **orchestrator in a separate lane** — G3 documents them so the gate can be
  run by hand, and touches none of them.
- Fixing the systemic "hermetic world has no priced pick surfaces" gap (§7.2).
- Analytics instrumentation for the Picks opt-out (see [scope.md](scope.md) §1 — waived, with
  the reason, and surfaced to the operator).
- **Pre-existing, not introduced here, not fixed here:** `posFilter` is not reset when the
  session league changes, so a `{PICKS}` selection can survive into a league with no pick
  data (pill hidden, every bar zero). Reachable today on the All subset; R-5 does not make it
  more reachable, only removes an incidental cleanup on one path. Logged, not fixed
  (principle 3).

### 9.3 Doc edit this PRD proposes but does **not** make

`docs/cross-client-invariants.md` is **orchestrator-owned**. The plan proposed the row
"n/a — the neutral-Picks rule is preserved verbatim". **That is wrong: the rule is not in the
document.** `LeagueSummaryScreen.tsx:159-162` cites cross-client-invariants for
*"Picks isn't a position, so it renders in a neutral ink tone, never a position hex
(cross-client-invariants)"*, but the **Position color tokens** section (`:186-194`) lists only
QB/RB/WR/TE hexes and says nothing about draft capital. The code cites a rule the doc does not
state — a genuine gap this change widens, because the neutral Picks segment will now render in
three subsets instead of one.

**Proposed text, to be appended to the "Position color tokens (segmented progress bar)"
section by the orchestrator:**

> **Draft capital is NOT a position, and never takes a position hex (#14 FR1, reaffirmed
> #293/#294 2026-08-10).** Wherever a chart or bar decomposes a roster's value, the owned-pick
> group renders in a **neutral ink/chalk tone** — never orange/green/blue/purple — because a
> position hex would assert that picks are a fifth position. Mobile uses `chalk.faint` for the
> live segment and `ink.ink3` for its grayed-out (drill-in defocus) state
> (`mobile/src/screens/LeagueSummaryScreen.tsx`: `PICKS_COLOR`, `GRAY_SEGMENT.PICKS`); web's
> `league-rankings.html` picks segment follows the same rule. The group's label is
> **"Picks"** in legends and filter pills and **"Draft capital"** as a section header.
> Pick value is **subset- and filter-independent**: a client that offers
> starters/bench or position views must include the team's full `picks.value` in every one of
> them, so the two subsets deliberately do **not** partition the total.

The last sentence is the cross-client encoding of the operator's ruling and is what stops a
future web subset control from re-introducing #293.

---

## 10. Implementability statement (Round 3)

**Yes — the PRD is now implementable blind, with two named preconditions that are not the build
agent's to satisfy.**

All six blocking objections from the Planner's Round 2 review are closed in the contract, and
each was independently re-verified against the worktree before adoption (two of its line
citations needed correcting — see [reconciliation-log.md](reconciliation-log.md) § Round 3):

| Obj | Closed by |
|---|---|
| O-1 | R-1's required no-default 4th param + the amended R-10 exception mandating `:433` + T-S1 assertion 13 |
| O-2 | Rescoped T-S1 assertion 3 (three gating symbols, not one identifier) + assertion 14 pinning the `<BarColumn>` prop to a bare identifier + required prop |
| O-3 | New R-0.4 reconciliation effect + T-S1 assertion 16 + manual drill T-S6c |
| O-4 | R-6's invariant restated in its qualified form, propagated to the code comment and scope.md §4's LLD row |
| O-5 | R-8.2 gates on the raw flag; §6 row 6 split into 6a/6b; "nine sites" replaced by the enumerated G1–G14 table; T-S1 assertion 15 |
| O-6 | T6 unmapped from R-5; R-5 **and** R-0.4 recorded in §7.2 as having no executable coverage under Option B, both added to Tier B |

Non-blocking O-7…O-10 are all incorporated: R-9 is now eight sites (with the header block's line
range corrected to `:53-56`), T7's false assertion (c) is **deleted** rather than reworded, T4
expects `All · RB + Picks`, and T3's selector question is converted from an unverified claim
into an explicit instruction with the reason it could not be settled here.

**The two preconditions:**

1. **The `sim-run.sh` harness fix** (orchestrator's separate lane). Until it lands, a flag-ON
   Maestro run cannot be *known* to be flag-ON. The fallback — pasting `report-dir/flags.json`
   into the TEST_LEDGER entry — is specified in scope.md §5. This blocks *evidence*, not
   implementation: a build agent can write all the code and pass T-S1…T-S4 without it.
2. **T3's Maestro selector question** (§7.4), which requires running `maestro --version` on a
   machine with a JRE. This blocks *authoring one flow*, not the code.

**Nothing is left unresolved between the Planner and me.** I adopted all ten objections; the
only places I diverged are refinements that make its case *more* precise rather than less, and
each is argued in the log: the O-1 blast radius is bounded by `boardsDiffer` and `scaleMax` is
not corrupted; the "ten gated expressions" count is replaced by an enumeration rather than a
different number; R-0.4 inherits R-5's coverage gap, which O-6 did not notice; and two of its
line citations were off by one and two. If the orchestrator wants a single thing double-checked
before build, make it **T-S1 assertions 13 and 14** — they are what stand between this contract
and a green suite on a half-gated screen.
