# Reconciliation log — #293 / #294 (G3)

> Adversarial review record for the G3 planning artifacts. The Planner authored
> [plan.md](plan.md); the Author turned it into [prd.md](prd.md) + [scope.md](scope.md).
> Disagreements are logged here rather than silently absorbed.

## Contents

- [Round 1 — Author](#round-1--author)
- [Round 1.5 — Operator decisions](#round-15--operator-decisions)
- [Round 2 — Planner review](#round-2--planner-review)
- [Round 3 — Author incorporation](#round-3--author-incorporation)
- [Round 2 — Planner review](#round-2--planner-review)

---

## Round 1 — Author

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa`, worktree `.claude/worktrees/fb-289-294`

### What I verified and agree with

I re-checked every load-bearing citation in plan.md against the worktree. **All of the code
citations are accurate**, which is unusual and worth saying: `activeTotal` `:260-270`,
`coreTotal` `:251`, `showPicksKey` `:370`, `switchSubset` `:555-565`, `shownBase` `:1266-1271`,
`segValue` `:1277-1280`, the drill group `:1016-1018`, the copy sites `:779`/`:784`/`:931`, the
label gates `:927-928`/`:1062-1063`, `teamPosRank` `:498-511`, `boardsDifferInView` `:457-463`.
The `picks {count, value, items}` shape in `mobile/src/api/league.ts` is as described.

Three of the plan's structural arguments I independently confirmed and adopted wholesale:

1. **Basis-independence is real and is the load-bearing safety argument.**
   `backend/server.py:18876` — `_power_picks_by_owner(league_id: str, fmt: str)` takes no
   `basis`. Both payloads therefore carry the identical per-team `picks.value`, so
   `boardsDifferInView` (a difference comparison) is invariant under adding it, and #208's fix
   plus #248's overlay survive with no change. D3's "no ranking machinery changes" verdict is
   correct, and I promoted it from analysis to a hard guardrail (R-10).
2. **`check-member-entered-marker.js` is unaffected.** Its assertions are scoped to the priced
   row via `pricedRowAncestor`; the section-level `subset === 'all' &&` gate sits above them.
   R8's "run it unmodified; if it fails the implementation is wrong" is exactly right.
3. **Zero existing Maestro coverage of the chart.** Confirmed: only `league-summary.league-home`
   is referenced anywhere in `mobile/.maestro/`, by three rookie flows.

I also adopt D1 (identical in all three subsets) and D2's core (arithmetic + default membership)
and reject the same alternatives for the same reasons. Proportional allocation in particular is
fabrication and would violate `docs/cross-client-invariants.md:317`.

### Disagreements and corrections

**C1 — "no new testID, no lint exposure" is wrong, and it would have failed CI.**
plan.md §8 states the flows need no new testIDs and R12 says lint exposure arises "only if the
Author adds a testID". I wrote a probe flow using the plan's ten ids and ran
`mobile/scripts/testid-lint.sh`: **exit 1**, six failures. The lint cross-checks each flow id
against a literal `testID=` grep in `mobile/src`, and six families are built from template
literals (`` testID={`${idPrefix}.${s.key}`} ``) with **no `league-summary.*` entry** in
`mobile/scripts/testid-lint-allow.txt`. `maestro-testid-lint` is a CI job
(`.github/workflows/ci.yml:38-42`), so a build agent following the plan verbatim would have
shipped a red PR. Corrected in prd.md §7.1 with all eleven ids tabulated by source line and
static-vs-templated status, and the five required allowlist globs given verbatim (R-12).
*The plan was right that no new testID is needed — the error is the inference that therefore
the lint is not exposed.*

**C2 — the hermetic QA seed has no draft picks at all, so four of the six flows are vacuous.**
plan.md open item 1 left this to me. Answered definitively:
`backend/tests/fixtures/seed_ui_test_db.py` writes zero `draft_picks` rows (its only direct
inserts are `elo_history_table`, `wrapped_events_table`, `app_feedback_table`; none of its
fourteen DB-helper calls touches picks), `build_cassettes` (`:822-868`) emits no `traded_picks`
or `drafts` path, and `standard.json` has no picks key. So `_power_picks_by_owner` returns `{}`,
every team gets `{count:0, value:0.0, items:[]}`, and **`hasPicks === false`** in league
`990000000000000001`. T1–T4 cannot see the Picks pill, legend key, base segment or
Draft-capital group, and T7 (no-picks) would pass with **zero implementation**.

This matters beyond the flows: it means plan.md §5's "Backend: **No**" and §4's "mobile-only,
single file" are true of production code but **not** of the test artifacts the plan's own
Maestro delta requires. I did not paper over that. prd.md §7.2 gives both options with
evidence and recommends **Option B** (Tier A flows + a seed-independent structural check now, a
written partial waiver, manual verification on a real league, seeding as a follow-up) over
**Option A** (seed a new `picks` profile now), because tripling a two-line polish item's blast
radius into backend fixtures — in the same change whose gate is a full smoke run — is the wrong
trade. Escalated to the orchestrator as the largest open decision in G3.

One piece of good news the plan did not establish: the *subset* control does work hermetically.
`_league_meta` (`:778-808`) supplies a real Sleeper `roster_positions` template, so
`starters_available` is true.

**C3 — the bar's segment composition is unanalyzed, and a partial implementation is invisible.**
plan.md changes 8 and 9 (`shownBase`, `segValue`) are listed as separate rows in the change
table with no statement of how they relate to change 1 (`activeTotal`). They are **atomic**.
`BarColumn` sets the bar's *height* from `active` (`:1284`) but each segment's height from
`v / segSum` (`:1348`), where `segSum = Σ segValue(p)` (`:1283`). If `activeTotal` starts
including `P` while `shownBase`/`segValue` still exclude it, the Starters bar grows by `P` and
the four position segments — being percentages of `segSum` — **silently stretch to fill it**,
misattributing every point of draft capital to the position groups. The bar looks right; the
encoding is a lie; a screenshot diff would not catch it. Promoted to a named requirement (R-3)
with the checkable invariant `segSum === active` for every (subset, filter) pair, and the
pre-existing All-unfiltered exception documented.

**C4 — D2's auto-add makes the position pill non-reversible; the plan did not surface it.**
Under plan.md's rule (auto-add only when `prev.size === 0`), `{RB, PICKS}` → tap RB → `{PICKS}`.
Tapping a position *off* drops the user into a picks-only ranking they never asked for, and the
RB pill stops being an involution — tap-on then tap-off no longer returns you where you
started. That is a real defect the fix would introduce. I added **rule B (exit)**: removing a
core position that leaves no core position in the set clears the filter to All (prd.md R-6, full
state machine tabulated).

I considered and rejected making rule B provenance-aware (only auto-remove a `PICKS` that was
auto-added): that requires tracking whether `PICKS` was auto-added or hand-selected, i.e. a
hidden state axis with no visible control — the same thing D2 rightly rejects when it dismisses
the `includePicks` boolean. So rule B costs one path a surprise (deliberate `{PICKS}` → add RB →
remove RB lands on All, not back on `{PICKS}`). I judged protecting the common gesture worth it
and said so explicitly, with the reverse trade offered to the operator. **This, plus the
auto-add itself, is the zone where the ruling is silent** — flagged in prd.md §8 for the
orchestrator to surface, per the brief.

**C5 — seven comment sites, not six.** plan.md change 10 lists `:159-162`, `:255-259`,
`:366-368`, `:553-554`, `:1013-1015`, `:1233-1240`. It misses **`:1176-1181`**, the
`PosFilterPills` doc comment: *"The neutral 'Picks' pill (#14 FR1) appears only when the league
actually has draft capital **and the All subset is active**."* That becomes false under R-4.
Since the plan's own (correct) principle is that "a reversal that leaves five contradicting
comments behind is a half-done reversal", leaving a sixth would have been the same mistake.
I also identified two comments that must **not** be touched: `:227-228` (`coreTotal` "players
only, no picks" — still true after R-1, because `coreTotal` itself is unchanged) and `:485`
(the avg-line comment, already correctly worded).

**C6 — the cross-client-invariants row is wrong; the rule is not in the document.**
plan.md §8 proposes `docs/cross-client-invariants.md` = *"n/a, the neutral-Picks rule is
preserved verbatim"*. I grepped: there **is no neutral-Picks rule** in that file. The
"Position color tokens (segmented progress bar)" section (`:186-194`) lists only the four
position hexes. `LeagueSummaryScreen.tsx:159-162` cites the document for a rule the document
does not state. So the honest row is not "n/a" but "gap, widened by this change" — the neutral
Picks segment will now render in three subsets instead of one. Proposed append text is in
prd.md §9.3; per the brief I propose it and do **not** make the edit. Its last sentence encodes
the subset/filter-independence rule cross-client, which is what stops a future web subset
control from re-introducing #293.

**Smaller corrections.**

- plan.md D5.2 quotes `:784` as ``Ranked by ${...} value only`` and drops the actual
  ` — chart reordered.` suffix. It also names one defect (raw `PICKS`); there are **two** —
  `[...posFilter].join(' + ')` prints the raw enum **in tap order**, whereas `filterPosLabel`
  fixes both the casing and the canonical QB→RB→WR→TE order. Exact before/after strings in
  prd.md R-8.2.
- plan.md gives no **sim-gate tier**. Per the `docs/runbook.md` matrix the change class is
  "Mobile screen / navigation / state change" ⇒ **Tier 1** (full 11-flow smoke + feature flows).
  Declared in scope.md §5.
- plan.md T8/T9 read as though the `mobile/tests/check-*.js` family runs in CI. It does not —
  CI is pytest + `tsc --noEmit` + `testid-lint.sh` only. Stated honestly in prd.md §7.3 and
  scope.md §3 rather than implying coverage that isn't there.
- plan.md notes `BarColumn`'s `subset` prop becomes unused and says "flag it for a follow-up
  only if lint complains". I checked instead of leaving it to chance: `mobile/tsconfig.json`
  sets only `strict` and `expo/tsconfig.base` sets no `noUnusedLocals`/`noUnusedParameters`, so
  the unused prop cannot break `tsc`. Keeping the prop is safe (R-10).
- plan.md does not mention that the #208 PRD (`docs/feedback/items/208-ranks-follow-position-filter/prd.md`
  §6) specced a Maestro flow `league-rankings-filter-ranks` on **this exact screen** that was
  **never created**. Noted so G3's flows do not collide with a later attempt to honour it, and
  so the orchestrator knows there is a pre-existing unfulfilled Maestro commitment here.
- Pre-existing hazard I chose to log rather than fix: `posFilter` is never reset on a session
  league change, so a `{PICKS}` selection can survive into a league with no pick data (pill
  hidden, every bar zero). Already reachable today on the All subset; R-5 does not make it more
  reachable, it only removes an incidental cleanup on one path. Fixing it would be a drive-by
  (principle 3). Recorded in prd.md §9.2.

### Things I deliberately did not change

- I did **not** widen the #279/#285 `total_value_label` gate, and made "do not widen it" a hard
  guardrail. plan.md D3's reasoning is correct: the server computes that label from
  `positions_value` plus a whole-team literal pick count, with no starters/bench decomposition,
  so it is only valid unfiltered on All.
- I did **not** authorize any refactor. plan.md's change surface is nine guard deletions plus
  one derived local, and prd.md §6 says so explicitly ("no new component, no new token, no new
  hook, no extracted helper").
- I did **not** propose a feature flag, despite this being a reversal of shipped behavior on a
  live surface. scope.md §2 weighs it in a table and recommends unflagged, because the flag would
  thread through nine sites — more code than the fix — and the bright line (schema, API,
  flag surface, analytics) is untouched. That recommendation is surfaced to the operator as W2
  rather than assumed.
- I did **not** claim analytics were covered by existing events. `screen_viewed` measures
  arrival on `LeagueRankings` but cannot answer whether the Picks opt-out is used; the taxonomy
  is default-deny, so a new event needs the full four-touch registration. Written waiver with
  the reason, plus a concrete offer, in scope.md §1.

### Open items handed to the orchestrator

| # | Item | Author's position |
|---|---|---|
| 1 | Seed picks into the hermetic world now, or ship Tier A + partial Maestro waiver? | **Option B** (waiver + follow-up) — prd.md §7.2 |
| 2 | R-6 rule B: does removing the last position clear the whole filter? Ruling is silent | **Keep rule B** — prd.md §8 |
| 3 | Flag or unflagged? | **Unflagged**, rollback = revert one commit — scope.md §2 |
| 4 | Analytics waiver | **Waive**, offer `rankings_filter_changed` separately — scope.md §1 |
| 5 | `docs/cross-client-invariants.md` neutral-Picks gap | Text proposed in prd.md §9.3; **orchestrator makes the edit** |

**Awaiting Planner review.**

---

## Round 1.5 — Operator decisions

**Date:** 2026-08-10 · **Relayed by:** orchestrator · **Verbatim:**
*"Aligned to all recommendations but ship with G3 flagged."*

All five open items from Round 1 are closed. Four accepted as recommended (seeding Option B,
R-6 rule B, the analytics waiver, the `cross-client-invariants.md` append). **One overridden.**

### W2 — unflagged → FLAGGED

I recommended shipping unflagged; the operator overrode it. **Rationale accepted and recorded,
not re-argued:** the change reverses shipped behavior on a live surface, so it gets a kill
switch. My Round-1 counter-arguments (nine gating sites, doubled QA state space) were weighed
and lost to reversibility, which is the operator's call to make. Logged here because a future
reader deserves to see that the flag was contested and why it won — that is the entry
`DECISIONS.md` will carry (scope.md §4).

One Round-1 argument turned out to be **wrong in my favour's disfavour**, and I want it on the
record: I wrote that "the bright line is untouched: no schema, no API contract, no flag surface,
no analytics event." Adding a flag *creates* a flag surface, so under CLAUDE.md's bright-line
rule this change could never have been an express-lane candidate anyway. That weakens one of my
five reasons for unflagged. Noted in prd.md §7.7.

### What the flag forced me to add

The override is not a one-line edit, and I did not treat it as one. New material:

- **prd.md R-0** — name (`league.picks_always_counted`) with the namespace argument
  (`league.*` over `picks.*`, because `picks.*` governs pick data and pricing, which this flag
  provably does not touch); default OFF; one read site.
- **prd.md R-0.1** — OFF defined normatively, per requirement, against the current line
  numbers, so "flag off ⇒ no observable change" is confirmable by reading one table. Includes
  the easy-to-miss consequence that `picksInView` must itself be gated, or the copy would change
  while the arithmetic did not.
- **prd.md R-0.2** — the atomicity invariant. This is the one I think matters most: it is
  **C3 (the `segSum` hazard) resurfacing at the flag boundary**, and a flagged implementation is
  strictly more exposed to it than an unflagged one, because nine sites now get individually
  wrapped by hand. If R-1/R-2 are gated but R-3 is not, a Starters bar grows by the pick value
  while its four position segments silently stretch to fill it — right-looking, wrong-encoding,
  invisible to every screenshot. One boolean, read once, gating the whole set; no per-site
  reads; no second flag; `BarColumn` must receive it as a prop rather than calling `useFlag`
  again.
- **prd.md R-0.3** — the `LAUNCHED_FLAG_DEFAULTS` trap. `useFlag` is `!!s.flags[key]`, so an
  absent key is `false`, which is what we want. The flag must **not** go in the defaults map
  while dark — that map exists because of the feedback-#115 recurrence where `{}` hid every
  gated surface on first boot, and it makes *launched* features visible from first paint. Adding
  a dark flag there would ship the new behavior to every first boot, the exact inverse of a kill
  switch. The graduation note (flip `config/features.json` **and** the defaults map in the same
  change, or first-boot users silently stay on the old behavior) is written into the PRD so it
  travels with the flip.
- **prd.md R-13** — four registration touches, each with the verified reason it is load-bearing
  rather than ceremonial: without the `FLAG_KEYS` entry, `FTF_FLAGS` overrides are dropped
  (`feature_flags.py:668`); without the `release.json` entry, a profile override naming the key
  is refused (`seed_ui_test_db.py:234-236`). Also verified the key does **not** join
  `INVENTORY_FLAG_KEYS`, so the five existing profiles stay valid — the hermetic default is OFF
  everywhere with no fixture edit.
- **prd.md §6.1** — exact `config/features.json` insert including the `_comment_*` in house
  style, modelled on `_comment_pick_assign_tradeable` (long, precise about ON vs OFF, and
  explicit that no backend behavior rides the flag). Orchestrator-owned; proposed, not applied.
- **Test plan** — T-S1 grows 9 → 12 assertions (three of them pinning the flag structure itself,
  the only mechanical check of R-0.2); new Maestro flow **T7** at the default OFF as the
  no-regression proof; new manual control **T-S6b**, which is the *only* test that sees flag-OFF
  with real pick data, because the hermetic seed has none; new **§7.6** on how the flag is forced
  per context.

### Two traps found while speccing the flag-ON test run

Both would produce a **false PASS against old behavior**, not an error, so they are worth more
than a footnote:

1. **`sim-run.sh --flags` replaces the seeded flag map rather than merging with it.** The script
   sets `FTF_FLAGS` from the seeder's `--print-env` block (`:53-54`) and then overwrites it
   wholesale at `:55`. A one-key `--flags '{"league.picks_always_counted":true}'` therefore
   discards every one of the profile's `flag_overrides` and silently reverts them to
   `config/features.json`. Pass the seeded map with the one key flipped.
2. **`--flags @file` is documented (`:5`) but not implemented (`:22`).** No `@` expansion exists
   in the script; the literal string is exported, `json.loads` fails, `_env_overrides` returns
   `{}` with only a stdout warning (`feature_flags.py:659-663`), and the run proceeds with every
   flag from `config/features.json` — i.e. the new flag OFF, with the flag-ON flows quietly
   asserting old behavior.

Trap 2 is a pre-existing `sim-run.sh` doc/impl mismatch. Not introduced here, not fixed here
(principle 3) — logged in prd.md §9.2 and scope.md §6.2 as a follow-up, because it will bite
the next flag-gated feature too.

### Unchanged by the override

Every behavioral requirement R-1…R-12, the §3/§4 behavioral specification, the exact copy
strings, the seven comment sites, the R-10 guardrails, the §7.1 testid-lint finding and the
§7.2 seeding analysis all stand exactly as written in Round 1. Sim-gate tier **1** is
reconfirmed, with the reasoning now explicit: the matrix keys on change class, not on
risk-after-mitigation, and the flag *adds* to the gate because both states must be exercised.

**Still awaiting Planner review** — the Round-1 disagreements (C1–C6) have not yet been
adversarially reviewed, and R-0 is new material that has had no second read at all.

---

## Round 2 — Planner review

**Date:** 2026-08-10 · **Reviewer:** Planner (author of [plan.md](plan.md)) · **Base:**
`origin/main` @ `7cea1fa`, worktree `.claude/worktrees/fb-289-294` · **Scope:** adversarial
read of [prd.md](prd.md) + [scope.md](scope.md), with independent re-verification of the
Author's C1–C6 and of the two `sim-run.sh` traps. Every claim below was checked against the
worktree; nothing is taken on the Author's word.

### 2.0 My own corrections — conceded, with evidence

The Author was right on all three counts against my draft. Stated plainly, because this is an
audit trail and not a defence:

| # | My plan said | Reality | How I verified |
|---|---|---|---|
| **C1** | plan.md §8: "no new testID, **no lint exposure**"; R12 said exposure arises "only if the Author adds a testID" | **Wrong.** I wrote my own probe flow against the ten ids from plan.md §8 and ran `bash mobile/scripts/testid-lint.sh`: **exit 1**, and the failure list is byte-identical to the Author's §7.1 output — `league-summary.{bar.900000000000000001, posfilter.picks, posfilter.rb, roster-posfilter.wr, roster-subset.bench, subset.starters}`. `grep -c league-summary mobile/scripts/testid-lint-allow.txt` = **0**. `league-summary.roster-picks` and `.filter-caption` pass (static). My inference "no new id ⇒ no lint exposure" was simply invalid — the lint checks *reference resolvability*, not novelty | independent probe, reproduced exactly |
| **C2** | plan.md open item 1 punted the seed question to the Author | **The seed has no picks at all.** `grep -c draft_picks backend/tests/fixtures/seed_ui_test_db.py` = **0**. Four of my six planned tests were vacuous and my T7 would have passed against zero implementation. Leaving this open was the single worst call in my draft — it is a *precondition*, not an open item | direct grep |
| **C5** | "six comment sites" | **Seven.** `:1176-1181` confirmed verbatim: *"The neutral 'Picks' pill (#14 FR1) appears only when the league actually has draft capital **and the All subset is active**."* My own stated principle condemned my own omission | `sed -n '1176,1182p'` |
| **C6** | `docs/cross-client-invariants.md` = "n/a, the neutral-Picks rule is preserved verbatim" | **Wrong — the rule is not in the document.** The "Position color tokens (segmented progress bar)" section (`:186-194`) is a four-row QB/RB/WR/TE hex table plus a Locations line; there is no mention of picks, draft capital or neutral tones anywhere in it. `LeagueSummaryScreen.tsx:159-162` cites a rule that does not exist. §9.3's "gap, widened by this change" is the honest framing | `sed -n '184,196p'` |

C3 (the `segSum` hazard) and C4 (pill reversibility) are both real defects I missed and both are
now better-specified than anything in my draft. **R-0.2 in particular is the best single idea in
these documents** — recognising that C3 *recurs at the flag boundary*, and that a flagged build is
strictly more exposed to it than the unflagged one I recommended, is exactly the reasoning the
override needed. Objections O-1 and O-2 below are attacks on its *enforcement*, not on the idea.

---

### 2.1 Objections

#### O-1 — BLOCKING · `activeTotal` has TWO call sites, and R-10 forbids touching the second one. As written, the PRD guarantees the #208 regression it claims to prevent.

PRD §6 row 1 gates `activeTotal` (`:260-270`) and stops there. But `activeTotal` is a
**module-scope pure function** (`:260`, outside the component), so the flag cannot reach it by
closure — it must be threaded as an argument. And it is called **twice**:

```
384:      active: activeTotal(tc, subset, posFilter),   // ranked — the BARS
433:      active: activeTotal(tc, subset, posFilter),   // otherByTeam — the #248 OVERLAY
```

R-10's first guardrail says, verbatim: *"**No ranking / overlay / rank-numeral machinery
changes** | `:381-391`, `:410-414`, **`:424-467`**, `:471-478`, `:818`, `:837`"* — and `:433` sits
inside `:424-467`. A build agent reading R-1/R-2 ("gate `activeTotal`") together with R-10 ("do
not change `:424-467`") has exactly one way to satisfy both: give the new parameter a **default**
(`picksAlwaysCounted = false`) and thread it only at `:384`.

The consequence is not cosmetic. `boardsDifferInView` (`:457-463`) compares `r.active` against
`o.active`. With picks in the bars and not in the overlay, every team's two values differ by `P`,
so `boardsDifferInView` becomes **true in every picks-holding league**, `ticksOn` fires, and
Starters/Bench draw a dashed tick and a rank-swing chip on every column — asserting a
board-divergence comparison the view does not contain. That is #208's exact reported symptom,
reintroduced. `scaleMax` (`:471-478`) is corrupted the same way.

The safety argument I supplied in plan.md D3 and the Author promoted to R-10 — *"both bases gain
the same per-team constant, so the difference comparison is invariant"* — is **only true if both
call sites receive the flag**. R-10 currently asserts the conclusion while forbidding the edit
that makes it true.

**Worse: this passes every one of the 12 T-S1 assertions.** Assertion 3 checks that "the 9 gated
sites branch on the same identifier"; `activeTotal` *is* site 1 and it does branch correctly
internally. `:433` is a **call site**, not one of the nine, so nothing looks at it.

**Change required (three edits):**
1. **R-1/R-2:** state that `activeTotal` gains `picksAlwaysCounted: boolean` as a **required
   fourth parameter with no default value** — no default, so `tsc --noEmit` (T-S4, already in the
   gate) catches an unthreaded call site instead of silently passing `undefined`.
2. **R-10:** amend the first guardrail to *"no changes to `:381-391` / `:410-414` / `:424-467` /
   `:471-478` **except** passing the `picksAlwaysCounted` argument at the `activeTotal` call on
   `:433`, which is mandatory — the basis-invariance argument depends on it."*
3. **T-S1: add assertion 13** — *both* `activeTotal(...)` call sites pass the identifier bound at
   assertion 1, and there are exactly two such call sites.

#### O-2 — BLOCKING · T-S1 assertion 3 cannot be satisfied across the `BarColumn` prop boundary, and nothing checks the value actually passed. A half-gated bar passes all 12 assertions.

R-0.2 mandates: *"`BarColumn` must receive it as a prop rather than calling `useFlag` again… **Do
not** call `useFlag` a second time inside `BarColumn`."* T-S1 assertion 3 then requires *"every
one of the 9 gated sites branches on the **same identifier** bound at assertion 1."*

Sites 8 and 9 (`shownBase` `:1266-1271`, `segValue` `:1277-1280`) live **inside `BarColumn`**
(`:1249-1361`), a separate module-scope function. A parameter binding there is a *different*
symbol from the `useFlag` result in the component body. Assertion 3 is therefore either
(a) unsatisfiable if read as same-symbol resolution, or (b) a bare name match — which is
trivially gameable and checks nothing.

The gap this leaves is precisely the R-0.2 hazard. `BarColumn` is instantiated once, at `:820`.
A build agent can satisfy assertions 1, 2 and 3 completely while writing:

```
<BarColumn … picksAlwaysCounted={false} … />        // or: {subset === 'all'}
```

`tsc` is happy (the prop exists and is a boolean), assertion 2 is happy (no `useFlag` in
`BarColumn`), assertion 1 is happy (one read site). Result: `activeTotal` includes `P` and the
bar grows, while `shownBase`/`segValue` exclude it and the four position segments stretch to fill
— **the exact "looks right, encodes a lie" failure R-3 and R-0.2 exist to prevent**, shipped with
a green test suite.

**Change required:**
1. Restate assertion 3 to be scoped and checkable: *"every gated site **in the component body**
   branches on the identifier bound at assertion 1; `BarColumn`'s gated sites branch on its
   `picksAlwaysCounted` parameter."*
2. **Add assertion 14** — the `<BarColumn>` JSX at `:820` passes `picksAlwaysCounted={<the
   identifier from assertion 1>}`, as a bare identifier reference: **not** a literal, **not** an
   expression. This is the only mechanical link between the two halves of the atomicity
   invariant, and it is currently missing.
3. Declare the prop **required** (no `?`, no default) so omission is a `tsc` error.

Answering the orchestrator's question directly: **yes — a build agent can satisfy every stated
assertion and still ship a half-gated screen.** Two independent ways (O-1, O-2). Both close with
one assertion each.

#### O-3 — BLOCKING · The ON→OFF transition strands `PICKS` in the filter, so flag-OFF is *not* byte-identical to `origin/main`. This fires exactly when the kill switch is used.

R-0.1's acceptance bar is *"flag off ⇒ no observable change."* That holds for a session that
starts OFF. It does **not** hold for a session that transitions ON→OFF — which is the flag's
entire purpose.

On `origin/main`, the state (`subset ∈ {starters, bench}` ∧ `PICKS ∈ posFilter`) is **unreachable**:
`switchSubset` strips PICKS on the way out of All (`:555-565`) and `showPicksKey` hides the pill so
it cannot be re-added (`:370`). After this change, flag ON makes it routine (R-5 removes the strip,
R-4 shows the pill). Now the operator pulls the kill switch. `useFeatureFlags` revalidates over the
network and the server map wins (R-0.3 table, row 3, `useFeatureFlags.ts:82`) — **mid-session, with
the screen mounted**. `posFilter` is component state and does not reset. The user is now in:

- `activeTotal` OFF branch (`:266`) → `PICKS` contributes a literal `0`;
- `showPicksKey` OFF (`:370`) → the Picks pill is **not rendered**;
- so a filter member exists that is invisible and unremovable, silently zeroing part of the view —
  the precise failure the `:553-554` comment names (*"a stale PICKS selection would zero bars"*).

Worst case `posFilter === {PICKS}` in Starters: every bar reads 0, no pill on screen to explain
it, and the only escape is the All pill.

This is a *new* failure mode introduced by the flag, so it is not covered by R-0.1, and neither
T7 (starts OFF, never transitions) nor T-S1 (source-level) can see it.

**Change required:** add **R-0.4** — a flag-transition reconciliation effect, modelled directly on
the existing precedent in this same file at `:362-364`:

```
// existing precedent — startersAvailable disappearing falls back to All
useEffect(() => { if (!startersAvailable && subset !== 'all') setSubset('all'); },
          [startersAvailable, subset]);
```

The new effect: when `picksAlwaysCounted` is false and `subset !== 'all'` and
`posFilter.has('PICKS')`, drop `PICKS` — i.e. re-apply exactly what `switchSubset` does on the OFF
path, so the OFF state is reachable-consistent from any direction. Add a T-S1 assertion that the
effect exists and that its body runs only on the OFF branch. Note it is a **no-op** in a
never-ON session, so it does not weaken R-0.1's first-render byte-identity.

#### O-4 — BLOCKING · R-6's stated invariant is false in three of the nine rows of the PRD's own §3.1, and R-6 orders it written into the code.

R-6 closes with: *"**Invariant this preserves — state it in the code comment:** the Picks pill's
selected state is exactly equal to whether pick value is in the chart."*

§3.1 contradicts it three times:

| §3.1 row | Filter | Team value | Picks in the bar? | Picks pill |
|---|---|---|---|---|
| 1 | `{}` (All) | `T` — **includes `P`** | Yes, base segment | **unselected** |
| 2 | `{}` (Starters) | `C + P` | Yes | **unselected** |
| 3 | `{}` (Bench) | `C + P` | Yes | **unselected** |

The *behavior* is correct and conventional — an empty set means "all keys", and the QB pill is
likewise unselected in All while QB value is charted. The **invariant is mis-stated**, and R-6
instructs an implementer to encode a false statement in a comment on a screen whose comments are a
named deliverable (R-9). The live risk is that an implementer resolves the contradiction the other
way and makes the Picks pill render *selected* in the All state to satisfy the invariant —
inconsistent with all four position pills and a visible regression.

I introduced this wording in plan.md D2 and it was carried forward unexamined; the error is mine
in origin and the Author's in adoption.

**Change required:** restate as *"**whenever the filter is non-empty**, the Picks pill's selected
state is exactly equal to whether pick value is in the chart; an empty filter means every key,
including picks, with no pill selected."* Use that text in R-6, in the code comment, and in
scope.md §4's `living-memory/LLD.md` row, which currently propagates the unqualified version.

#### O-5 — BLOCKING · R-8.2's gate is unspecified, and §6 row 6 conflates three strings with two different gate conditions.

R-8 introduces **one** local, `picksInView = hasPicks && (posFilter.size === 0 ||
posFilter.has('PICKS'))`, and §6 row 5 says it is "itself flag-gated". R-8.1 and R-8.3 correctly
branch on it. **R-8.2 cannot.**

R-8.2 replaces `[...posFilter].join(' + ')` with `filterPosLabel` — a *casing and ordering* fix
that must apply whenever the flag is ON, including when the user has deselected Picks (filter
`{RB, WR}`, `picksInView === false`). But R-0.1's R-8 row requires that flag-OFF renders the raw
enum in tap order. So R-8.2 needs its own gate on the **raw flag boolean**, not on `picksInView`:
`picksAlwaysCounted ? filterPosLabel : [...posFilter].join(' + ')`.

The PRD never says this. §6 row 6 lumps `:779`, `:784`, `:931` into a single "copy" row, T-S1
assertion 10 pins only `picksInView`'s initializer, and nothing pins `:784`. A build agent that
gates all three on `picksInView` produces a real divergence from R-0.1: with flag ON, filter
`{WR, RB}` (tapped in that order), Picks deselected, the hint prints `WR + RB` where the spec says
`RB + WR`.

Consequently the "**9 gated sites**" count used by R-0.2 and T-S1 assertion 3 is wrong — there are
**ten** distinct gated expressions.

**Change required:** split §6 row 6 into 6a (`:779` + `:931`, gated via `picksInView`) and 6b
(`:784`, gated on `picksAlwaysCounted` directly); state R-8.2's gate expression verbatim in R-8.2;
update every "nine sites" reference in R-0.2, §6 and T-S1 assertion 3 to **ten**; add a T-S1
assertion pinning `:784`'s flag-OFF arm to `[...posFilter].join(' + ')`.

#### O-6 — BLOCKING · T6 is mapped to R-5 but cannot exercise R-5. R-5 has no executable test.

§7.4 T6: *"tap `league-summary.posfilter.rb` → `league-summary.subset.starters` → `.bench` →
`.all`; pass: the filter unchanged at every step"*, mapped to **R-5** and marked "**runs today**"
/ Tier A.

R-5 is *"`switchSubset` never mutates the filter"* — but the only thing `switchSubset` has **ever**
stripped is `'PICKS'` (`:558-562`). `RB` survives every subset switch on `origin/main` today. So
T6 passes identically on unfixed code, on fixed code, flag ON and flag OFF. It tests nothing.

Exercising R-5 requires `PICKS ∈ posFilter`, which requires `hasPicks === true`, which the
hermetic seed cannot provide (C2). So under Option B — which the operator accepted (D-11) — **R-5's
only coverage is T-S1 assertion 8 (source-level) plus the manual T-S6 pass.** That may well be an
acceptable posture, but the PRD currently claims executable Tier-A coverage that does not exist,
and a QA sign-off against §7.4 would record a false green.

**Change required:** remove R-5 from T6's Req column (leave T6 as a cheap navigation regression
mapped to nothing, or fold it into T7); add a line to §7.2's Option B waiver naming **R-5** as a
requirement with **no executable coverage** under Option B; add it explicitly to the §7.4 "Tier B"
set so the follow-up seeding item knows R-5 is waiting on it.

#### O-7 — NON-BLOCKING · R-9's seven-site enumeration is incomplete: the screen's header comment states the retired rule and is not listed.

The Author correctly found a seventh site I missed (`:1176-1181`). **We both missed `:54-57`** —
the top-of-file header block, the first thing any reader of this screen sees:

```
54  //   - Position filter (single OR multi, "All" default): on change the bars
55  //     RE-VALUE to the selected position(s) only and RE-SORT teams — a pure
56  //     client-side transform over per-position values (no refetch).
```

*"RE-VALUE to the selected position(s) **only**"* is exactly the rule R-2 and R-6 reverse. It is
the canonical description of the position filter in this file and it is absent from R-9's table,
so §9.1 criterion 4 ("the seven comment sites no longer state the retired rule") could be signed
off while the file still teaches the old behavior in its opening paragraph.

**Change required:** R-9 becomes **eight** sites, adding `:54-57`. Judgment call, flagged not
mandated: `:63-65` (*"Selecting either recomputes EVERY team's per-position values from that
subset and re-ranks the whole league"*) remains literally true — it describes per-position
values — but reads as a complete account of the subset recompute and no longer is. I would extend
it; I would not block on it.

#### O-8 — NON-BLOCKING · T7's assertion (c) does not prove what §7.4 claims.

§7.4 says of T7: *"**(c)** after switching to Starters with RB selected, the filter still shows RB —
**proving the OFF path is exercised, not merely absent**."*

It proves no such thing. RB survives a subset switch on `origin/main`, in a hypothetical build with
no flag at all, and in a build where the flag was never wired up. (c) is satisfied by every
possible implementation, so it distinguishes nothing — the same defect as O-6.

The PRD is otherwise commendably honest here (it already concedes (a) and (b) are doubly-caused by
`hasPicks === false`). The overclaim is confined to (c). The genuine flag-OFF evidence is T-S1
assertions 4–10 and the T-S6b manual control, both of which the PRD names elsewhere.

**Change required:** delete the "proving the OFF path is exercised" clause; state instead that T7
is a **navigation + no-regression** proof and that the OFF *arm* is evidenced by T-S1 (source) and
T-S6b (real data). Keep T7 — a screenshot baseline against `origin/main` is worth having.

#### O-9 — NON-BLOCKING · T4's pass criterion does not match T4's steps.

§7.4 T4 steps: *"tap a bar → tap `league-summary.roster-posfilter.rb` → `assertVisible:
league-summary.filter-caption` → tap `league-summary.roster-close`"*. Pass criterion: *"the
caption's text asserts as **`Starters · RB + Picks`**"*.

The flow never taps a Starters control. `filterCaptionLabel` (`:573-580`) is
`${subsetLabel} · ${filterPosLabel}` with `subsetLabel` from the live `subset`, which is still
`all`. The caption will read **`All · RB + Picks`** and the assertion fails on a correct build.

**Change required:** either insert `tapOn: id: league-summary.roster-subset.starters` before the
caption assertion, or change the expected string to `All · RB + Picks`. (scope.md §3 repeats the
same `Starters · RB + Picks` expectation and needs the same fix.)

#### O-10 — NON-BLOCKING · T3 rests on an unverified claim that Maestro cannot read `selected`.

§7.4 T3: *"the pill exposes `accessibilityState={{selected}}` (`:1221`) but **Maestro cannot read
it**, so the screenshot is the artifact."* That claim is asserted without evidence. Maestro's
element matchers do accept selection-state attributes in recent versions; I could not settle it
from the repo — `grep -rn "selected:" mobile/.maestro/` returns **nothing**, so there is no local
precedent either way.

This matters because T3 is the **only** test of the R-6 state machine, and a screenshot is an
eyeball check, not a gate. If the matcher works, T3 becomes three mechanical assertions.

**Change required:** verify against the installed Maestro version before authoring T3. If
supported, use `assertVisible: id: … selected: true|false` and demote the screenshots to evidence;
if not, keep the current wording and add the version you checked, so the next author does not
re-litigate it.

---

### 2.2 The two `sim-run.sh` traps — independently confirmed, plus a third

The orchestrator asked how confident to be. **Both traps are real; I reproduced the mechanism for
each from source. Confidence: high.** The Author's line citations are exact — I checked all four.

**Trap 1 — `--flags` REPLACES the seeded map. CONFIRMED.**

```
53  ENVBLOCK="$(cd "$REPO" && python3 "$SEEDER" --profile "$PROFILE" --seed "$SEED" --print-env)" || exit 2
54  set -a; eval "$ENVBLOCK"; set +a
55  [[ -n "$FLAGS" ]] && export FTF_FLAGS="$FLAGS"
```

`seed_ui_test_db.py:1052` emits `f"FTF_FLAGS={q(flags_json)}"` inside `--print-env`, so line 54
exports the profile's **full** flag manifest. Line 55 then overwrites the variable wholesale —
there is no merge anywhere in the script. A one-key `--flags` discards every `flag_overrides`
entry the profile declared, reverting them to `config/features.json`. **Silent: no warning, no
non-zero exit.** The Author's remedy (build the override from the profile manifest with the one
key flipped) is correct.

**Trap 2 — `--flags @file` documented but unimplemented, fails OPEN. CONFIRMED.**

`:5` advertises `[--flags <json-or-@file>]`; `:22` is a bare `--flags) FLAGS="$2"; shift 2 ;;` and
`@` appears nowhere else in the file. The literal `@flags.json` is exported, and
`feature_flags.py` `_load_from_env` swallows it:

```
659      try:
660          parsed = json.loads(raw)
661      except Exception as e:
662          print(f"[feature_flags] could not parse FTF_FLAGS env var: {e}")
663          return {}
```

`{}` merges onto `DEFAULT_FLAGS` + `config/features.json` (`_compute_flags`), so the run proceeds
with the flag **OFF** while flag-ON flows assert ON behavior — a **false PASS against old
behavior**, exit 0, one stdout line in `flask.log`.

**Third finding, mine — the guard that would have caught either trap is documented but does not
exist.** `sim-run.sh:61` comments the handshake as: *"Handshake (30 s budget): whoami reports our
profile **AND flags round-trip**."* The assertion block that follows (`:67-74`) checks
`test_mode`, `fixtures`, `profile` and `pid` — **and nothing about flags**. Two lines later the
script fetches the effective map and merely archives it:

```
75  PINNED="$(curl -sf "$URL/api/feature-flags")" || { echo "INFRA: flags fetch failed" >&2; exit 2; }
76  echo "$PINNED" > "$REPORT_DIR/flags.json"
```

Fetched, written, **never asserted**. That is the root cause of both traps' silence: the harness
already has the effective flag map in hand at the one moment it could fail loudly, and throws the
opportunity away. The fix is a few lines — assert that every key/value requested via `--flags`
appears with that value in `PINNED`, exit 2 otherwise — and it would convert both traps from
false-PASS generators into infra errors.

**Impact beyond G3: yes.** Any flag-gated flow in this batch or any future one is exposed. G3 is
merely the first consumer to notice. I agree with the Author that fixing `sim-run.sh` is out of
scope here (principle 3), but I would raise the follow-up's priority: as of today **the repo has
no way to run a flag-ON Maestro tier and know that it did.** Concretely, for G3's own gate: T5/T6
are specced flag-ON, so the person running them hits trap 1 on the first invocation.
Recommend the orchestrator either (a) fixes the `PINNED` assertion before the G3 gate run — it is
~5 lines and is itself the verification that the gate is meaningful — or (b) requires the operator
to paste `report-dir/flags.json` into the TEST_LEDGER entry as manual proof of the flag state,
which scope.md §5 already half-asks for ("record each flow's flag state in the ledger entry").

### 2.3 Verified and endorsed — where the Author improved on my plan

Beyond C1/C2/C5/C6 (conceded above) and C3/C4 (real defects I missed):

- **R-0.2 atomicity** is the strongest single contribution in either document; O-1 and O-2 exist
  only because I take it seriously enough to test its enforcement.
- **R-0.3 / `LAUNCHED_FLAG_DEFAULTS`** is correct and I verified it end to end: `useFlag` is
  `!!s.flags[key]` (`useFeatureFlags.ts:101-104`), the map is `:44-51`, and its own comment at
  `:40-43` says *"Only add flags here once they are launched — dark features must stay absent so
  they default hidden."* Keeping the key out is right, and the graduation note (flip
  `config/features.json` **and** the map together) is the kind of thing that is only ever written
  down after it bites someone.
- **R-13's four touches** — I verified both load-bearing claims rather than trusting them.
  `feature_flags.py:668` is literally `if k in DEFAULT_FLAGS:` inside `_load_from_env`, so an
  unregistered key **is** dropped from `FTF_FLAGS`. `seed_ui_test_db.py:234-236` is
  `unknown = [k for k in overrides if k not in base]` → `_refuse`, so `release.json` **is** a
  precondition for any profile override. Both citations exact.
- **`INVENTORY_FLAG_KEYS` non-impact** verified: `:231-233` requires a decision only for inventory
  keys, so the five existing profiles are unaffected.
- **G1/G2 collision check — clears.** `docs/feedback/items/289-mfl-draft-room-ids/batch-plan.md`
  lists G1 as backend `draft_board_service.py`/`mfl_service.py`/`server.py:10411-10493` and G2 as
  the mock-draft route shims + `MockDraftScreen.tsx`; its only flag mention (`:167`) is the
  **existing** `draft.room`/`draft.mfl`/`draft.mock` state on the base commit — neither group
  registers a new flag. `backend/feature_flags.py` and `backend/tests/fixtures/flags/release.json`
  are uncontested, and the residual `FLAG_KEYS` append-only conflict the Author names is the
  correct characterisation.
- **Sim-gate tier 1** and the reasoning that a flag *adds* to the gate rather than lowering it is
  right, and the "it lands dark so users see nothing" counter is correctly refused.
- **§9.3's proposed cross-client text** is better than a fix: its last sentence encodes the
  ruling cross-client and is what stops a future web subset control from re-creating #293.
- **The self-correction in Round 1.5** — that adding a flag *creates* a flag surface and therefore
  puts this change on CLAUDE.md's bright line, weakening one of the Author's own five arguments —
  is the single most credible paragraph in the log.

### 2.4 Scope and repo-invariant check

- **No unauthorised refactor.** §6 ("no new component, no new token, no new hook, no extracted
  helper") and §9.2 hold. The two additions O-1 and O-3 request are a required function parameter
  and one `useEffect` with an in-file precedent (`:362-364`) — neither is an abstraction.
  Principle 3 is respected; the PRD is notably disciplined about naming pre-existing warts
  (`positions_value`/`coreTotal` drift, the `posFilter` league-change reset, `--flags @file`) and
  refusing to fix them.
- **Four gates:** scope block ✔ (`scope.md`, every section answered or waived with reason);
  Maestro delta ✔ (with an operator-accepted partial waiver, D-11); docs table ✔ (row-by-row,
  including two n/a→required moves caused by the flag); sim run ✔ (tier 1 declared, evidence
  path + `githooks/pre-push` named). Express correctly not self-selected, and the bright-line
  note is present.
- **`docs/coding-guidelines.md`:** principle 1 (assumptions surfaced) is met unusually well — §8
  isolates the operator-silent zone instead of quietly choosing.
- **11px type floor:** confirmed independently — `type.bodySm` is 13px
  (`mobile/src/theme/chalkline.ts:135-139`), `type.data` is 13px (`:148-153`). No new style.

### 2.5 Required-changes checklist

| # | Sev | Change | Where |
|---|---|---|---|
| O-1 | **BLOCK** | `activeTotal` gains a required (no-default) flag param; R-10 explicitly permits threading it at `:433`; T-S1 assertion 13 pins both call sites | R-1, R-2, R-10, §7.3 |
| O-2 | **BLOCK** | Rescope assertion 3 to the component body; add assertion 14 pinning the `<BarColumn>` prop value at `:820` to the flag identifier; prop declared required | R-0.2, §7.3 |
| O-3 | **BLOCK** | New **R-0.4**: ON→OFF reconciliation effect dropping `PICKS` from `posFilter`, modelled on `:362-364`; T-S1 assertion | R-0.1, R-0.4 |
| O-4 | **BLOCK** | Restate the pill invariant as *"whenever the filter is non-empty…"* in R-6, the code comment, and scope.md §4's LLD row | R-6, scope.md §4 |
| O-5 | **BLOCK** | Split §6 row 6; give R-8.2 its own gate on the raw flag; renumber "nine sites" → **ten** everywhere; pin `:784`'s OFF arm | R-8.2, R-0.2, §6, §7.3 |
| O-6 | **BLOCK** | Unmap T6 from R-5; record R-5 as having no executable coverage under Option B; add to the Tier B follow-up | §7.4, §7.2 |
| O-7 | non-block | R-9 becomes **eight** sites (`:54-57`); consider `:63-65` | R-9, §9.1.4 |
| O-8 | non-block | Delete T7's "proving the OFF path is exercised" clause | §7.4 |
| O-9 | non-block | Fix T4: add the Starters tap, or expect `All · RB + Picks` | §7.4, scope.md §3 |
| O-10 | non-block | Verify Maestro's `selected:` matcher before authoring T3; record the version checked | §7.4 |
| — | non-block | Orchestrator: fix `sim-run.sh`'s missing `PINNED` assertion before the G3 gate run, or require `flags.json` in the ledger entry as manual proof | §7.6, batch-level |

**Verdict: NO — not ready for a build agent to implement blind.** Six blocking items, five of
which (O-1, O-2, O-5 and their knock-ons) let a build agent ship a half-gated screen with a green
suite, and one (O-3) breaks the kill switch at the moment it is pulled. All six are cheap —
roughly two new T-S1 assertions, one required parameter, one `useEffect`, one gate expression and
three wording fixes — and none disturbs the behavioral spec, the operator's five decisions, or the
change's one-file shape. Fix them and this is the most implementable PRD I have reviewed in this
pipeline.

---

## Round 3 — Author incorporation

**Date:** 2026-08-10 · **Author** · **Input:** Planner Round 2 (6 blocking, 4 non-blocking) ·
**Outcome: all ten objections adopted.** Zero rejected. Every one was re-verified against the
worktree before adoption — the Planner's standard, applied back to it — which turned up two
line-citation corrections and three refinements where its case was slightly over- or
under-stated. Those are recorded below not as pushback but because a contract that overstates a
failure teaches a build agent to discount it.

### Disposition

| Obj | Sev | Verified? | Outcome | Landed in |
|---|---|---|---|---|
| O-1 | BLOCK | **Yes** — `grep -n "activeTotal("` returns the declaration plus exactly `:384` and `:433`; `activeTotal` is module-scope (`:260`, before `export default function` at `:272`) | **Adopted in full**, plus the no-default rule | R-1 (signature + both call sites), R-10 (exception), T-S1 #13, §6 rows 1/1c |
| O-2 | BLOCK | **Yes** — `<BarColumn>` at `:820-841`; nothing reads the prop's value | **Adopted in full** | R-0.2 (three gating symbols, required prop), T-S1 #3 rescoped, #14 |
| O-3 | BLOCK | **Yes** — traced the transition through `useFeatureFlags.ts:82`, `activeTotal:266`, `showPicksKey:370`, `heightPct:1284`, `groupRows:1101` | **Adopted in full** | New **R-0.4**, T-S1 #16, manual drill **T-S6c**, §9.1 criterion 6 |
| O-4 | BLOCK | **Yes** — §3.1 rows 1–3 contradict the unqualified wording | **Adopted in full** | R-6 (qualified form, verbatim), scope.md §4 LLD row |
| O-5 | BLOCK | **Yes** — `picksInView` is `false` for `{WR, RB}`, so a `picksInView` gate prints tap order | **Adopted, with a different fix for the count** | R-8.2 (explicit gate expression), §6 rows 6a/6b, T-S1 #15, R-0.2 **G1–G14 enumeration** |
| O-6 | BLOCK | **Yes** — only `'PICKS'` was ever stripped (`:558-562`) | **Adopted, extended** | T6 unmapped; §7.2 coverage-gap table naming **R-5 and R-0.4** |
| O-7 | non-block | **Yes**, with correction | **Adopted** | R-9 → **eight** sites |
| O-8 | non-block | **Yes** | **Adopted — assertion deleted, not reworded** | §7.4 T7 |
| O-9 | non-block | **Yes** — `filterCaptionLabel` (`:573-580`) reads `subsetLabel` from live `subset`, never tapped to Starters | **Adopted** | §7.4 T4, scope.md §3 |
| O-10 | non-block | **Could not verify here** | **Adopted, converted to an instruction** | §7.4 T3 |

### Where I diverged from the Planner's text (all in its favour's direction, none rejecting it)

**1. O-1's blast radius is narrower than stated, and `scaleMax` is not corrupted.** The review
says `boardsDifferInView` goes true "in every picks-holding league" and that `scaleMax` is
"corrupted the same way". Both need qualifying. `boardsDifferInView` is `boardsDiffer && …`
(`:457-458`), and `boardsDiffer` (`:410-414`) is an unfiltered `total_value` identity check — so
the regression only reaches callers who *have* a distinct personal board; for everyone else
`ticksOn` never fires. And `scaleMax` (`:471-478`) takes a **max** over other-basis values that
the bug makes strictly *lower*, so the max is unchanged and no tick can clip. The real damage is
the tick heights (systematically low by `P`) and the spurious delta chips. I wrote the narrower,
accurate version into R-1 — a build agent who checks the claim and finds it overstated is a
build agent who discounts the whole guardrail.

**2. "Ten gated expressions" is replaced by an enumeration, not by a different number.** O-5 is
right that "nine" was wrong, but I could not make "ten" come out either: the count depends on
whether `activeTotal`'s two branches are one site or two, whether rule A and rule B are one
expression, and whether the new `useEffect` counts. The number was never the problem — the
*ambiguity* was, because assertions were being written against a count nobody could reproduce.
R-0.2 now carries a **G1–G14 table** (ID, expression, line, gating symbol, requirement), and
§6, §7.3 and R-0.1 reference G-IDs only. This also made the O-2 fix expressible: the three
gating symbols fall straight out of the table.

**3. R-0.4 inherits R-5's coverage gap — O-6 did not notice.** O-6 correctly says R-5 has no
executable coverage under Option B. The same argument applies to the effect O-3 demands:
exercising R-0.4 needs `PICKS` reachable in a non-All subset (⇒ pick data) *and* a live flag
transition. §7.2 now names **both**, and both join Tier B. Left unstated, the PRD would have
gained a new requirement with silently zero coverage in the same round it fixed that exact
problem elsewhere.

**4. Two line citations corrected.** O-7's header block is **`:53-56`**, not `:54-57` (`:53` is
the "Position filter (single OR multi…" line, `:56` the "colored outline pills" line). Its
secondary candidate is **`:61-63`**, not `:63-65`. Both verified by `grep -n`. Recorded in R-9
because an implementer working from a wrong range edits the wrong comment.

**5. O-10 could not be closed here, and I said so rather than guessing.** `maestro --version` in
this worktree fails with *"Unable to locate a Java Runtime"*; no Maestro version is pinned
anywhere in the repo; `grep -rn "selected:" mobile/.maestro/` returns nothing. So T3's spec now
carries an explicit two-branch instruction plus a requirement to record the version checked in
the flow header — converting an unverified claim into a bounded task instead of laundering it
into a second unverified claim.

### On O-3, which I think is the most important of the six

O-1, O-2 and O-5 are enforcement holes: real, cheap to close, and caught by better assertions.
O-3 is different in kind. The operator overrode my unflagged recommendation on one ground — a
reversal of shipped behavior on a live surface should have a kill switch. O-3 shows the switch,
as specced, **corrupts view state at the moment it is pulled**: an invisible, unremovable
`PICKS` member left in `posFilter`, and in the `{PICKS}`-only case a chart with no bars and
nothing on screen explaining why. That does not merely weaken the flag; it inverts the
justification for having one. I have added the reconciliation effect (R-0.4), and — because a
switch nobody has pulled is a switch nobody has tested — a **manual kill-switch drill (T-S6c)**
as a §9.1 done-criterion. The operator should not be the first person to pull it.

I also recorded the two constraints that keep the fix honest: it must be a **no-op in a
never-ON session** (so R-0.1's first-render byte-identity is untouched), and it must **not**
replace `switchSubset`'s synchronous OFF-path strip (G6) — the effect runs after a render, so
substituting it would introduce one frame of zeroed bars on every OFF-path subset switch. A
build agent "simplifying" the pair into one is a regression the PRD now forbids explicitly.

### Harness — noted, not acted on

The Planner confirmed both `sim-run.sh` traps and found the third and most useful one: the
handshake comment at `:61` claims flags round-trip, the assertion block at `:67-74` checks four
other things, and the effective map fetched at `:75-76` is archived to `flags.json` and
**never asserted** — which is precisely why the other two are silent. Per the orchestrator, the
harness is being fixed in a separate lane and **G3 edits no `qa/` or `sim-run.sh` file**. I have
stated the dependency explicitly in prd.md §7.6 and scope.md §5, including the fallback
(paste `report-dir/flags.json` into the ledger; build `--flags` from the profile manifest with
one key flipped, never a one-key object, never `@file`). I agree with the Planner's framing that
this is a batch-level exposure, not a G3 one.

### Verdict

**Yes — implementable blind**, with two preconditions that are not the build agent's to satisfy:
the harness fix (blocks *evidence* for flag-ON runs, not implementation) and T3's Maestro
selector question (blocks *authoring one flow*, not the code). Full statement in **prd.md §10**.

**Nothing remains unresolved between the Planner and me** — there is no position for the
orchestrator to arbitrate. If one thing gets a second look before build, make it **T-S1
assertions 13 and 14**: they are the entire difference between this contract and a green suite
on a half-gated screen.
