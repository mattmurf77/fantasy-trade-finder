# #395 + #396 — Lineup-impact superflex attribution & "WR3" slot label — Mini-PRD

Date: 2026-08-24 · Author: Group C (fast-track bug path) · Branch context: `origin/main` @ ff153a0
Companion docs: [plan.md](plan.md) (planner findings), [scope.md](scope.md) (feature gates)
Items: #395 (bug, v1.16.2, TradesHome — SF lineup attribution) · #396 (bug, v1.16.2, TradesHome — "WR3" in a 2-WR league)

**Plain words:** #395 — the math is right; the display manufactures a phantom QB change.
We re-pair the before/after rows so a value-identical lineup shows the minimum honest set of
changes. #396 — ESPN/MFL/Fleaflicker leagues get a fabricated 3-WR template, so "WR3" appears
in leagues that have no third WR slot; we replace it with a 2-WR + 2-FLEX template. The rank
chip ("WR3 → WR12") also gets a one-character disambiguation so a positional rank can never
read as a slot name.

All file:line references below re-verified on `ff153a0` (2026-08-24). No drift from plan.md
was found; one addition: the calculator has a second rank-chip renderer
(`InLeagueCalculator.tsx:1570-1572`, `posRankLabel`) the plan did not list — dispositioned in
§Out-of-scope.

---

## 1. Repro + root cause

### #395 — two-row cascade in a superflex league

Pipeline: `POST /api/trade/evaluate` Mode B → `_starter_impact` (`backend/server.py:1167-1303`)
→ `power_rankings.optimal_starter_slots` (`backend/power_rankings.py:120-131`, shared greedy
`_fill_starter_slots` :50-96) → slot labeling (`backend/server.py:1285-1298`) → mobile
`CardImpactBlock` (`mobile/src/components/TradeCard.tsx:831` →
`CardImpactBlock.tsx:108-160`, changed rows only) and the calculator's `LineupImpactTable`
(`mobile/src/components/InLeagueCalculator.tsx:1511, 1598-`, full table).

Scripted repro (planner, template `QB RB RB WR WR TE FLEX SUPER_FLEX`, Daniels 9000 / Maye
6000 / Fannin 2800 + filler):

```
BEFORE:                      AFTER (Daniels traded):
  QB          daniels          QB          maye
  ...                          ...
  SUPER_FLEX  maye             SUPER_FLEX  fannin
CHANGED ROWS AS THE CARD SHOWS THEM:
  QB          daniels -> maye
  SUPER_FLEX  maye -> fannin
```

Root cause chain: the greedy fill assigns dedicated slots first (`power_rankings.py:78-83`),
then flexes narrowest-first (:84-95), so the best QB always canonically sits in the dedicated
QB slot. Daniels IS in the before lineup (no exclusion bug) and both totals are correct. The
user's mental model (Maye at QB, Daniels at SF) is **value-identical** — but
`_starter_impact` diffs the two canonical fills row-by-row with no churn minimization
(`server.py:1290-1298`), rendering a phantom "QB: Daniels › Maye" row plus "SF: Maye ›
Fannin". Presentation bug, not a correctness bug.

### #396 — literal "WR3" in a 2-WR league

`_league_lineup_slots` (`backend/server.py:24126-24178`) resolves the template. For
`platform in ('espn','mfl','fleaflicker')` it substitutes `_MOCK_DEFAULT_LINEUP =
["QB","RB","RB","WR","WR","WR","TE","FLEX"]` (`server.py:14588` — three WRs) at
:24171-24175, appending `SUPER_FLEX` when `default_scoring == 'sf_tep'`. The label numbering
at `server.py:1285-1293` then emits `WR1/WR2/WR3`. The player the real league starts at FLEX
is displayed under a dedicated "WR3" slot — matching the report word for word.

### Which sources can render "WR3" for a flex-started WR in a 2-WR league (verified per path)

| Source | Verdict |
|---|---|
| (a) Slot-label numbering (`server.py:1285-1293`) | **Cannot mislabel a flex.** Labels come only from template slot names; a flex renders `FLEX`/`SUPER_FLEX`, numbered (`FLEX1/FLEX2`) only when the template repeats it. "WR3" requires three literal `WR` entries in the template. No fix needed. |
| (b) Platform default template (`server.py:24171-24175`) | **Guaranteed "WR3"** for every ESPN/MFL/Fleaflicker league, regardless of the real lineup. Sleeper leagues use real `roster_positions` (`_sleeper_lineup_slots`, :24102-24123) — a 2-WR + FLEX Sleeper league labels `WR1 WR2 FLEX` and can never show WR3; only an honest 3-WR Sleeper league can. **This is Fix B.** |
| (c) Rank chip (flag `trade.position_impact`, ON — `config/features.json:219`) | **Can read "WR3" in ANY league incl. Sleeper.** `CardImpactBlock.tsx:155` renders `` `${position}${rank}` `` ("WR3 → WR12") on the same row as the slot label. It is a positional rank by design (#169), not a slot — but on the card row it is visually adjacent to slot labels. One-line disambiguation is in scope (R-6). A second renderer, `InLeagueCalculator.tsx:1570-1572` (`posRankLabel`, "4th · TE21" inside `TierBadge`), is tier-prefixed and out of this fix's file ownership — out of scope with a note. |

Because Fix B is a real bug regardless of which league the report came from, it ships
unconditionally; the TestFlight checklist covers both league types so the operator's pass
disambiguates the report empirically.

## 2. Requirements

Every requirement carries at least one mechanical acceptance criterion (§4 maps them to tests).

- **R-1 — `align_starter_slots` contract.** New **pure** function in
  `backend/power_rankings.py`:
  `align_starter_slots(before, after) -> tuple[list[dict], list[dict]]`, where `before`/
  `after` are two `optimal_starter_slots` outputs over the same template (parallel
  `{"slot", "player"}` row lists). Behavior:
  - Applies only **same-side pairwise swaps** of two rows' `player` contents where every
    non-None player involved is eligible for its destination slot per
    `LINEUP_SLOT_ELIGIBILITY` (`power_rankings.py:38-47`).
  - A swap is applied only when it **strictly increases** the count of indices `k` where
    `before[k]` and `after[k]` hold the same `player_id` (None counts as a match with None).
  - **Pinned scan order (contract, not implementation freedom):** scan the **before** side
    first. Within a side, visit index pairs `(i, j)`, `i < j`, in ascending lexicographic
    order; on the first strictly-improving eligibility-valid swap, apply it and **restart
    that side's scan from `(0, 1)`**. A side is done when a full scan applies nothing; then
    scan the other side the same way, alternating until both sides pass a full scan clean
    (fixpoint). Termination is bounded: every applied swap strictly increases the match
    count (≤ template length ≤ ~12). The order is contractual because the result is
    order-dependent when multiple 1-changed-row optima exist — two mutually-eligible FLEX
    slots, before `[A, B]` / after `[B, C]`: a before-side-first scan swaps before to
    `[B, A]` and displays the change on `FLEX2` (`A → C`); an after-side-first scan would
    display it on `FLEX1`. Before-first is pinned (and is the natural reading: the after
    lineup stays the engine's canonical post-trade fill; the before display is re-arranged
    toward it). Two conforming implementations must therefore produce byte-identical output.
  - **Deterministic** (the pinned order above; no randomness) and **does not mutate its
    inputs** (returns aligned copies).
  - Slot names/order are untouched — only which row a player occupies moves, and only among
    rows that player set already occupies on that side. Per-side value totals and starter
    *sets* are therefore invariant by construction; tests assert it anyway (R-3).
- **R-2 — Single call site.** `align_starter_slots` is called **only** inside
  `_starter_impact`, between the two `optimal_starter_slots` calls (`server.py:1278-1281`)
  and the labeling loop (:1285-1298). `optimal_starter_slots` / `optimal_starters`
  themselves and every other caller — power-rankings starters split, Team Review
  weakest-slot (`server.py:24617`, `backend/team_review.py`), mock draft — are byte-identical.
  `your_delta` / `their_delta` / `note` (computed at :1229-1247 from `optimal_starters`,
  before the breakdown) are untouched.
- **R-3 — #395 rendered outcome, two-sided.** On the repro fixture (template
  `QB RB RB WR WR TE FLEX SUPER_FLEX`; Daniels/Maye/Fannin shape), the aligned `slots`
  payload has **exactly one** row where `before.player_id != after.player_id`:
  `SUPER_FLEX`, Daniels → Fannin. The QB row shows Maye on both sides (no QB row appears in
  the changed-row set). Tests are two-sided: they assert (i) `your_delta`/`their_delta` and
  the per-side lineup value totals are equal to the unaligned computation, **and** (ii) the
  display rows actually differ from the unaligned diff in the repro case (unaligned = 2
  changed rows, aligned = 1) — so an identity "alignment" cannot pass.
- **R-4 — Fix B template.** New constant
  `_PLATFORM_DEFAULT_LINEUP = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]`, used
  **only** in the `_league_lineup_slots` platform branch (`server.py:24171-24175`), with
  `SUPER_FLEX` appended when `default_scoring == 'sf_tep'` (exact list then:
  `QB RB RB WR WR TE FLEX FLEX SUPER_FLEX`). `_MOCK_DEFAULT_LINEUP` (`server.py:14588`) and
  its mock-draft call sites (:14759, :14807) are untouched.
- **R-5 — Platform slot labels.** For a platform league, `starter_impact.slots` labels are
  `QB RB1 RB2 WR1 WR2 TE FLEX1 FLEX2` (+ `SUPER_FLEX` for sf_tep); `"WR3"` appears nowhere.
  The numbering path itself (:1285-1293) needs no change (verified — see §1 table row a);
  the existing behavior (repeat → numbered, single → bare) is asserted for the new
  double-FLEX case.
- **R-6 — Rank-chip disambiguation (one line).** `CardImpactBlock.tsx:155` changes from
  `` `${position}${rank}` `` to `` `${position} #${rank}` `` on **both** halves (renders
  "WR #3 → WR #12"), so a positional rank can no longer be read as a slot name. The chip
  stays a positional rank (its #169 design); no layout, color, or logic change; the adjacent
  header comment's example is updated. Pin via a small extension to the existing
  `mobile/tests/check-card-impact-order.js` guard, **anchored to the rank literal itself** —
  match `position ?? ''} #${beforeRank}` and its `afterRank` twin, never a bare `/#\$\{/`
  over the file (a bare match is satisfiable by any future unrelated `#${` and fails the
  non-vacuity bar). This file joins the ownership set with the one-liner.
- **R-7 — Docs.** `docs/api-reference.md`'s `/api/trade/evaluate` row is updated: (i) the
  platform template description ("QB/2RB/3WR/TE/FLEX") becomes QB/2RB/2WR/TE/2FLEX
  (+SUPER_FLEX for sf_tep); (ii) a one-sentence `slots` semantics note: before/after rows
  are pairwise-aligned to minimize displayed churn among value-identical assignments —
  totals and deltas unchanged. No contract/shape change (same keys).

## 3. Out of scope

- **Real per-league templates for ESPN/MFL** (ESPN `lineupSlotCounts`, MFL
  `starters.position` limits via `backend/mfl_service.py`) — #311's own logged phase-2
  follow-up. Not this fix.
- **`_MOCK_DEFAULT_LINEUP` and the mock-draft call sites** (`server.py:14588, 14759, 14807`)
  — untouched by R-4's construction.
- **Web/extension** — re-verified 2026-08-24: `git grep "starter_impact" -- web/ extension/`
  returns nothing; mobile is the only `starter_impact` consumer.
- **`InLeagueCalculator.tsx:1570-1572` `posRankLabel`** ("4th · TE21" inside `TierBadge`) —
  the same positional-rank convention, but tier-prefixed (reads as a stat, not a slot) and
  outside this group's file ownership. Noted for a follow-up if the operator's checklist pass
  still reads it as a slot; do not change here.
- **Respecting the user's real Sleeper lineup** (`power_rankings.py:100-113` — value-optimal
  by design, real lineups stale/empty preseason). Alignment usually reconstructs the
  intuitive assignment; a user who benches a stud on purpose still sees the value-optimal
  lineup. Unchanged posture.
- **Power-rankings route template resolution** — still `_sleeper_lineup_slots` only
  (deliberate #311 deferral). Team Review and platform-league starter impact pick up Fix B's
  template via `_league_lineup_slots`; that value shift (a 3rd RB / 2nd TE can now start
  over a fabricated 3rd WR) is a strict accuracy improvement, named in the ship message.

## 4. Test plan (D-056)

**Baseline (rerun by this author, 2026-08-24, this worktree @ ff153a0):**
`python3 -m pytest backend/tests/test_power_rankings.py backend/tests/test_trade_evaluate.py -q`
→ **113 passed, 6.53s** (60 + 53 tests). Matches the planner's stated baseline.

### (a) Unit tests — each proven red by a named sabotage, none self-satisfying

All tests assert output **values** on non-trivial fixtures (named players, real templates),
never mere non-crash; count/total assertions are two-sided (equality of totals AND changed-row
deltas asserted against exact expected sets).

| # | Test (file) | Asserts | Named sabotage → red |
|---|---|---|---|
| 1 | `test_align_starter_slots_superflex_cascade` (`test_power_rankings.py`) | #395 shape: aligned before shows Daniels at `SUPER_FLEX`, Maye at `QB`; exactly one changed row (`SUPER_FLEX`: Daniels→Fannin); unaligned diff has two changed rows (proves alignment did something) | Make `align_starter_slots` the identity → changed-row count is 2, and before-QB is Daniels → red |
| 2 | `test_align_starter_slots_wr_flex_cascade` (`test_power_rankings.py`) | `WR WR FLEX` template, trade the top WR: single changed row and it is `FLEX`; the two WR rows byte-equal before/after | Identity alignment → three changed rows → red |
| 3 | `test_align_preserves_totals_and_eligibility` (`test_power_rankings.py`) | Across several rosters (incl. duplicate FLEX/SUPER_FLEX slots): per-side summed values **exactly equal** pre-alignment (`==`, byte-equal — alignment does no arithmetic); per-side starter `player_id` sets identical; every non-None aligned row satisfies `LINEUP_SLOT_ELIGIBILITY[slot]`; inputs not mutated; repeated calls return identical output (pinned-order determinism). **Pinned mixed-flex fixture (mandatory):** template containing `WRRB_FLEX` + `REC_FLEX`; before `{WRRB_FLEX: wrP, REC_FLEX: teQ}`, after `{WRRB_FLEX: rbR, REC_FLEX: wrP}`. Here the ONLY match-improving swaps are eligibility-invalid — before-side `teQ → WRRB_FLEX` (TE ∉ {RB,WR}); after-side `rbR → REC_FLEX` (RB ∉ {WR,TE}) — so a correct implementation applies nothing and both changed rows stand | Drop the eligibility check → on the pinned mixed-flex fixture the sabotaged implementation applies an invalid improving swap (no valid alternative exists to mask it) → eligibility-validity assert red. Hand-verified |
| 4 | `test_align_forced_change_is_noop` (`test_power_rankings.py`) | Trade the ONLY QB, template includes a second TE slot the roster cannot fill (before `TE2 = None`): the genuine forced change is preserved exactly — changed-row set is exactly `{QB: daniels → —}`, alignment is a no-op (the only zero-or-better swap is the invalid net-0 `QB ↔ TE2`: +1 at QB, −1 at the vacated TE2) | Drop BOTH guards — relax strict-improvement to net-≥0 AND drop the eligibility check (single pass) → the net-0 `QB ↔ TE2` swap applies, before renders `QB: —, TE2: daniels`; exact-row-set assert red (changed set becomes `{TE2}`) and eligibility assert red (a QB in a TE row). Hand-verified: a sabotage dropping eligibility alone is a no-op here (no strictly-improving swap exists), which is why both guards must fall |
| 5 | `test_starter_impact_slots_aligned_display` (`test_trade_evaluate.py`) | End-to-end Mode B via the `_install_starter_world` seam (`test_trade_evaluate.py:625-649` — patches `_league_lineup_slots` directly): #395-shaped world returns `slots` with exactly one changed row labeled `SUPER_FLEX`, and `your_delta`/`their_delta` equal the values computed from `optimal_starters` totals | Remove the `align_starter_slots` call from `_starter_impact` → changed-row assert red |
| 6 | `test_platform_template_has_no_wr3` (`test_trade_evaluate.py`) | Platform-league template (leagues-row branch or seam): labels are exactly `["QB","RB1","RB2","WR1","WR2","TE","FLEX1","FLEX2"]`; `"WR3" not in labels`; sf_tep variant appends `SUPER_FLEX`. Additionally asserts the literal `srv._MOCK_DEFAULT_LINEUP == ["QB","RB","RB","WR","WR","WR","TE","FLEX"]` — pins the mock-draft constant's divergence from `_PLATFORM_DEFAULT_LINEUP` in CI (after the :1034 update nothing else would catch a swap) | Revert :24172 to `_MOCK_DEFAULT_LINEUP` → exact-label-list assert red; edit the mock constant (or point it at the platform constant) → literal assert red |
| 7 | Existing 113 tests in both suites stay green; `test_trade_evaluate.py:1034`'s `slots == list(srv._MOCK_DEFAULT_LINEUP)` assertion is updated to `_PLATFORM_DEFAULT_LINEUP` (this is the one deliberate expected-value change — recorded, not loosened) | Any regression → red |

Full suite (`python3 -m pytest backend/tests -q`) green before merge; results logged in
`living-memory/TEST_LEDGER.md` with the sabotage names, per repo convention.

Mobile: `npx tsc --noEmit` green; `check-card-impact-order.js` extension (R-6) red when the
`#` prefix is removed from the rank template literal (its named sabotage) — the guard matches
the anchored literals (`position ?? ''} #${beforeRank}` / `#${afterRank}`), not a bare `#${`.

### (b) Code-walk proof outline (written at build time, file:line-cited)

Trace: evaluate Mode B → `_starter_impact` fills (`server.py:1278-1281`) →
`align_starter_slots` (new call, between :1281 and :1285) → labeling (:1285-1298) →
`CardImpactBlock.tsx:108-111` changed-row filter → row render (:136-158). Shows: (i) the #395
payload carries one changed slot and the QB row falls out of the changed filter; (ii) a
platform league's labels contain no `WR3` (template from `_PLATFORM_DEFAULT_LINEUP` at
:24171-24175); (iii) the rank chip renders `WR #3 → WR #12`; (iv) totals path (:1220-1247)
is not reachable from the alignment call.

### (c) Operator TestFlight checklist (runtime evidence; covers BOTH league types so the pass disambiguates which league #396 came from)

Superflex Sleeper league (the operator's own):

1. TradesHome → evaluate a trade sending **Jayden Daniels away for picks only** (build
   Daniels → picks in the In-league calculator if no such card fronts — an incoming *starter*
   legitimately adds rows, so the exactly-one-row expectation holds only for a picks-only
   return). Expected: "Your starting lineup" shows **exactly one** row — `SF: Jayden Daniels
   › <his backup/replacement>` — and **no QB row** claiming Maye was displaced.
2. Same trade in the In-league calculator. Expected: BEFORE column shows Daniels at `SF` and
   Maye at `QB`; totals row present.
3. Compare lineup **totals and deltas** for the same trade against a pre-update screenshot if
   one exists (or the pre-update build). Expected: numbers identical — alignment moves rows,
   never numbers.
4. Any changed row with rank chips. Expected: reads `WR #3 → WR #12` style (with `#`), never
   `WR3`.

ESPN or MFL league (operator has both linked):

5. Front a card (or calculator-evaluate) involving a WR. Expected: **no `WR3` label anywhere**
   on lineup impact; slots read `QB RB1 RB2 WR1 WR2 TE FLEX1 FLEX2` (+`SF` in sf_tep; the
   calculator table shortens `SUPER_FLEX`→`SF` per its `SLOT_SHORT` map); a flex-started WR's
   row is labeled `FLEX1`/`FLEX2`.
6. Sanity: `your_delta`-driven note and totals still render; slight value shifts vs the old
   build are expected here (honest template: a 3rd RB / 2nd TE may start over a 3rd WR).

Outcome interpretation: if the #396 league was ESPN/MFL, step 5 clears the report; if the
operator saw "WR3" in a Sleeper 2-WR league, only the rank chip could have produced it, and
step 4 clears it. Either way both sources are fixed; log which it was in status.md.

## 5. Requirements → mechanical criteria map

| Req | Mechanical criterion |
|---|---|
| R-1 | Tests 1-4 (purity: test 3 asserts inputs unmutated + repeated-call equality; the pinned before-first scan order is what makes test 1's changed-row *label* assertable across implementations) |
| R-2 | Test 5 (delta equality through the route); `git grep -n "align_starter_slots" backend/` shows exactly one call site outside `power_rankings.py`/tests; existing 113 green (no other caller moved) |
| R-3 | Tests 1, 2, 5 (two-sided: totals equal AND changed-row set differs from unaligned) |
| R-4 | Test 6 (incl. its literal `_MOCK_DEFAULT_LINEUP` pin) + test 7's updated `_PLATFORM_DEFAULT_LINEUP` assert; `git grep -n "_MOCK_DEFAULT_LINEUP" backend/server.py` still lists :14588, :14759, :14807 unchanged |
| R-5 | Test 6 exact-label list (incl. `FLEX1/FLEX2`) |
| R-6 | `check-card-impact-order.js` extension asserts the anchored rank literals (`position ?? ''} #${beforeRank}` + `#${afterRank}` twin); `tsc --noEmit` green; TestFlight step 4 |
| R-7 | api-reference row diff present in the PR; scope.md §4 row marked "updated" |

## 6. File ownership (no overlap with groups A/B/D/F)

| File | Change |
|---|---|
| `backend/power_rankings.py` | new pure `align_starter_slots` |
| `backend/server.py` | `_starter_impact` alignment call (~:1281-1285) + `_PLATFORM_DEFAULT_LINEUP` and its use at :24171-24175 — those two regions only |
| `backend/tests/test_power_rankings.py` | tests 1-4 |
| `backend/tests/test_trade_evaluate.py` | tests 5-6 + the :1034 expected-template update |
| `docs/api-reference.md` | R-7 row updates |
| `mobile/src/components/CardImpactBlock.tsx` | R-6 one-liner (:155) + comment example |
| `mobile/tests/check-card-impact-order.js` | R-6 pin (rides with the one-liner) |
| `docs/feedback/items/395-lineup-impact-superflex/` + `../396-flex-slot-label/status.md` | this PRD, scope, status |
