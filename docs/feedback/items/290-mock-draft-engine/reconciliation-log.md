# Reconciliation log — G2 (#290 / #291 / #292 / D-16)

> Dual-agent record for Phase 1 of the `/feedback` pipeline. The Author drafts,
> the Planner reviews adversarially, and every departure from `plan.md` is
> recorded here with its reasoning so the disagreement is visible rather than
> silently resolved.
>
> Deliverables: [`hld-delta.md`](./hld-delta.md) · [`lld-delta.md`](./lld-delta.md) ·
> [`prd.md`](./prd.md) · [`scope.md`](./scope.md)

---

## Table of Contents

- [Round 1 — Author](#round-1--author)
  - [A. New evidence produced this round](#a-new-evidence-produced-this-round)
  - [B. Departures from the plan](#b-departures-from-the-plan)
  - [C. Where the plan was right and is adopted verbatim](#c-where-the-plan-was-right-and-is-adopted-verbatim)
  - [D. Citation corrections](#d-citation-corrections)
  - [E. Decisions made where the plan left a choice open](#e-decisions-made-where-the-plan-left-a-choice-open)
  - [F. Open questions for the Planner's review](#f-open-questions-for-the-planners-review)
  - [G. Open items for the operator](#g-open-items-for-the-operator)

---

## Round 1 — Author

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` ·
**Worktree:** `.claude/worktrees/fb-289-294`

The plan is unusually strong — it ran the shipped `cpu_pick` and measured the
defect rather than inferring it, and its structural analysis of `cpu_pick`,
`MockEntryPanel` and `UndraftedRowView` is correct in every load-bearing
particular. Six of its claims are nevertheless overturned by further measurement,
and two of those change the shape of the build materially.

### A. New evidence produced this round

Four measurements the plan did not have. All hermetic (no DB, no network),
reproducible from the repo.

**A-1 — Carnell Tate is the consensus #2 rookie.** The plan's Spike A was
declared blocking because `data/trade_finder.db` is empty here and the value
fixtures carry no names. It is not blocking: the plan's own cited harness
(`backend.tests.test_mock_draft._rookie_ctx`) joins `rookie_universe_2026.json`
(names) to `ktc_blend_pipeline_2026-07-17.json` (values) through the **shipped**
blend and reproduces the product board exactly.

| | 1qb_ppr | sf_tep |
|---|---|---|
| 1 | Jeremiyah Love 1886.9 | Jeremiyah Love 1859.0 |
| **2** | **Carnell Tate 1817.5** | **Carnell Tate 1776.5** |
| 3 | Jordyn Tyson 1771.3 | Jordyn Tyson 1722.5 |
| 4 | Makai Lemon 1746.4 | Fernando Mendoza 1719.1 |

**Tate at 4th is a two-slot fall, not a reach.** Spike A is **closed**.

**A-2 — the shipped engine's real pathology, measured on the real board.**
N = 2000 seeded round-1 replays, 12-team linear, explicit order, user last:

| | Shipped |
|---|---|
| P(consensus #1 Love goes 1.01) | 45.1 % |
| P(Love falls past pick 3) | 15.8 % |
| P(Tate falls past pick 4) | 16.5 % |
| Who goes 4th | Lemon 17.7 · Tyson 16.0 · **Love 15.8** · Price 15.3 · Concepcion ~13 · Sadiq ~11 · **Tate 10.1** (%) |
| Distinct top-4 orderings | 173 |

The plan's diagnosis (rank-blind scoring, random reaching) is **confirmed** — but
the player it attached to is wrong. The consensus **#1** lands 4th more often
than the player the report named.

**A-3 — a run-rule parameter sweep, and why `m = 2.5, W = 9`.** The plan
recommended the adaptive family but could not choose a parameter without Spike B.
Measured on the real board:

| | Shipped | m = 2.0 | **m = 2.5** | m = 3.0 |
|---|---|---|---|---|
| P(Love 1.01) | 45.1 % | **100 %** | **45.1 %** | — |
| P(Love past 3) | 15.8 % | 0 % | **2.4 %** | — |
| P(Tate past 4) | 16.5 % | 0 % | **0 %** | — |
| Distinct top-4 orderings | 173 | **5** | **18** | — |
| Median run size, 1qb_ppr / sf_tep | — | 3.5 / 4.0 | **5.0 / 5.0** | 11.0 / 5.0 |

`m = 2.0` is exactly the collapse D-6 warns about, arriving in round 1. `m = 2.5`
leaves 1.01 as varied as today, eliminates the top-of-board fall, and — **with no
size clamp**, per D-9 — produces a median run of **5 on both formats**, which is
the operator's "tight groups of 4-5" as an emergent property. **Spike B is
closed**: it was a two-hour measurement, and it has been done.

**A-4 — the blast radius, measured rather than estimated.** The full engine
change was applied as a prototype and `test_mock_draft.py` run, twice; the tree
was then restored to `7cea1fa` (`git status` clean apart from these docs).

| Prototype | Result |
|---|---|
| Need-conditional weight alone | **1 failed, 79 passed** — `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`. Tripwire did **not** fire. |
| Full change (run rule both call sites + need-conditional + the one helper correction) | **80 passed, 0 failed.** Tripwire did **not** fire. |

So #290's entire test blast radius is **one test-helper line**, and it is not an
assertion weakening: `_reach_draws` measures the reach law at `needs = 0.0`,
which under the new mixture weight is no longer the branch it names; on a
single-position board the need bonus is a constant that cancels out of the
argmin, so `needs = 1.0` measures the identical law while making
`effective_bpa_prob == bpa_prob` exactly.

### B. Departures from the plan

| # | Plan says | This PRD says | Why |
|---|---|---|---|
| **B-1** | §4.3.5: the acceptance test is *"`P(Carnell Tate taken at pick ≤ 4)` falls from its measured pre-change value to ≈ 0"* | **Rejected and replaced** by R-11's three top-of-board integrity assertions (consensus #1 holds 1.01 / Tate never falls past 4 / consensus #7 essentially never reaches pick 4) | Falsified by A-1. Tate is #2 and shares a run with Tyson and Lemon (46.1 and 71.1 Elo). Under the value-gap rule the operator asked for, Tate at 4 is *legitimate* — driving it to zero needs either a size clamp (D-9 forbids) or a wall between players 46 Elo apart (which would wall nearly every adjacent pair). The plan's assertion would encode the wrong model. |
| **B-2** | §4.3.5 / §8: "Tate 4th" is *"the model behaving exactly as specified … a defect in the model's form"* (strong expectation), with a pricing defect as the alternative | **Both, and the tests separate them.** Model form is real and R-3/R-11 fix it. But the operator's *stated reason* ("value gaps between him and the other WRs") does not match the board — Tate→Tyson and Tyson→Lemon are the two **tightest** gaps at the top. If the operator still objects post-fix, it is a **pricing** complaint in a different lane. | The plan framed these as mutually exclusive and expected to resolve them in a spike. The measurement resolves them as layered, and [`prd.md` §4.4](./prd.md#44-how-the-tests-distinguish-the-two) states which test catches which — including that **no** test may catch the pricing half, because R-12 requires within-run order to stay varied. |
| **B-3** | §4.1: #292 needs a backend change — "Option A: extend the abandon route to accept a `complete` row … plus (optionally) relaxing `mock_draft_pick_route`'s sibling guard" | **No backend change at all.** `mock_draft_abandon_route` (`server.py:11781-11794`) → `update_mock_draft` (`database.py:10786-10805`), whose `WHERE` is **id + user_id only**. A completed mock is already dismissible, owner-scoped, idempotent. | Verified by reading the SQL. Consequences: no route contract change ⇒ `docs/api-reference.md` is **n/a**; no `database.py` edit ⇒ G2 **releases** its region claim on `:10714-10805`; #292's change class drops to mobile-only. |
| **B-4** | R9: *"Hermetic mock seeding does not exist … `ffv3-predraft` is blocked by `draft_order: null`"*; the flow must either drive the mock live "slowly" or a `mock_drafts` seed knob must be added to `seed_ui_test_db.py` | **A hermetic mock flow is authorable today with zero seeder work.** `draft_order: null` only makes `_mock_real_draft` return `order_source: randomized` (`server.py:11555-11557`); it blocks nothing. The fixture is **12 teams, `pre_draft`, 4 rounds, linear**, so all six `mockBlock` predicates pass, and `d2` already proves the rookie class loads on this league under the `standard` profile. Setting rounds to 1 in the setup sheet makes it a one-user-pick flow. | Confirms G3's finding that `seed_ui_test_db.py` writes no `draft_picks` (it writes no `mock_drafts` either) **and** shows it does not bite here. Removes a whole harness workstream. |
| **B-5** | §3 / §7: the D-16 site is `mock_draft_service.py:1013` fed from `server.py:11438` (G1's PRD §11 "corrects" the plan's `:11437` to `:11438`) | **The line is `:11437`, and there are TWO sites** — `_mock_league_context` at `:11437` (create) and `_mock_context_from_row` at **`:11474`** (every GET and every /pick). | G1's correction is itself wrong, and the missed second site is the more important one: a mock is read far more often than it is created, so fixing only the create path would leave every *resumed* mock rendering ids. |
| **B-6** | §4.2 / R11: the #291 fix is *"`actionLabel ? … : row.valued ? …`"*, with the TierBadge tension left to "decide in design review" | **Decided:** render the action label unconditionally on the user's turn **and relocate** #277's tier label to the row's meta line for those rows, so nothing is deleted. Plus `actionLabel={isUserTurn ? 'Pick' : undefined}` so the CPU-turn render stays byte-identical. | Leaving it to design review would hand a build agent a judgment call, which the LLD contract forbids. Rendering both in the trailing slot costs ~40 pt from a `numberOfLines={1}` name column at 375 pt; a glyph is barred by `DraftRoomScreen.tsx:1367-1371`; evicting the badge silently deletes shipped information. Relocation is the only option that loses nothing. |
| **B-7** | §5: sequencing step 0 is *"Reproduce #292 first (~30 min)"* | **Dropped.** | D-8 cancels the diagnostic spike and rules all three dead-ends in scope, so there is nothing for the reproduction to decide. The rest of the plan's sequencing (#292 → #291, #290 parallel to #291) is **confirmed**, with D-16 riding with #290 and #290 ordered *before* D-16 inside the backend lane so the tripwire risk is faced before an identity refactor. |
| **B-8** | §8: two blocking spikes (A: the real board + Tate; B: run-size distribution), ~4-5 h total, "operator sign-off before build" | **Both closed this round** (A-1, A-3). No spike blocks build. | Both were measurements, and the harness to run them was already cited in the plan. |
| **B-9** | R10: two stale docs (`config/features.json:145`, `docs/config-reference.md:565`) | **Five locations, and the features.json line is `:155`.** Add `docs/config-reference.md:309` (the flag row, whose *default column* still reads `false`), `docs/architecture.md:135` and `docs/glossary.md:30`/`:42`. `architecture.md` additionally claims *"the routes never do [opt in]"*, which is now false. | Same defect class, wider than the plan found. Exact replacement text for all five is in [`scope.md` §2.2](./scope.md#22-stale-flagconfig-documentation--a-real-defect-to-correct-plan-r10-extended). |

### C. Where the plan was right and is adopted verbatim

Recorded so the Planner can see what is *not* in dispute.

1. **The root-cause analysis of `cpu_pick`** — rank-not-value scoring at
   `:646-651`, `row["value"]` never read, the reach cap and truncation as pure
   rank arithmetic, and the independent-additive-terms diagnosis of the need
   term. All verified line by line.
2. **The magnitude argument for need inertia** — `0.5 × 1.0 × 3.0 = 1.5` slots of
   need pull against a 12.3 %-of-the-time 3-slot noise reach, with severity
   pinned at 0 by `VIABLE_ELO_FLOOR = 1280` for most August (team, position)
   pairs. This is the quantitative case for D-5 and it is adopted whole.
3. **The refusal to reuse the 8-tier ladder** (§4.3.1), including the #279
   precedent and the `cross-client-invariants.md` quarantine paragraph. Adopted,
   with the ladder-width argument re-verified against the measured 89-row pool.
4. **The placement at the existing `reach_cap` seam via `min()`** (§4.3.2) and
   every one of its four justifications — never loosens the operator's rule,
   preserves the Gumbel-max identity, preserves budget accounting, one seam.
   Adopted exactly, and the plan's insistence on the `simulate_reaches` mirror is
   promoted to a numbered requirement (R-6) with its own structural test.
5. **The AST constraint analysis** — that the run scan must be a forward walk
   modelled on `_block_rank`, satisfiable without a waiver. Adopted, and
   **verified empirically**: `test_w2_14` passes under the prototype.
6. **The determinism note** (§4.3.2) — truncation changes RNG consumption, old
   seeds replay differently, no test and no invariant breaks. Verified and
   adopted as guardrail G-5.
7. **The rejection of scaling the Gumbel `scale` by severity** (§4.3.3) and of
   raising `mock_max_reach_slots`. Adopted.
8. **The rejection of Option B for #292** (age-bounding the complete fallback) and
   of a new `/api/mock-draft/reset` route. Adopted.
9. **#291's verdict** — the capability exists, the affordance does not; the
   `accessibilityHint` asymmetry; "do not build an interactivity feature."
   Adopted, and it is what makes D-7 the right ruling.
10. **The three #292 dead-ends**, each independently verified.
11. **The `check-mock-mode-marker.js` risk (R5)** and its enumerated constraints.
    Adopted as guardrail G-4 and expanded in `lld-delta.md` §6.5.
12. **R7 (ships lit), R12 (`MOCK_MIN_TEAMS` disagreement), and the "keep the run
    out of `draft_board_service.py`" note in §7.** All adopted.

### D. Citation corrections

Full table in [`lld-delta.md` §10](./lld-delta.md#10-citation-corrections-to-planmd).
Summary: three cosmetic drifts (`:646-652`→`:646-651`; `:1170`→`:231` for the
"flattens in the tail" quote; `MockDraftScreen.tsx:200-212`→`:198-212`); one
material (`server.py:11437` + a second site at `:11474`); one wrong-file
(`config/features.json:145`→`:155`); and three claims overturned outright
(B-3, B-4, B-8). Every other cited line was verified correct.

### E. Decisions made where the plan left a choice open

| Choice | Decision | Basis |
|---|---|---|
| Run threshold family and parameter | adaptive, `m = MOCK_RUN_GAP_MULTIPLE = 2.5`, `W = MOCK_RUN_MEDIAN_WINDOW = 9` | D-9 + measurement A-3: median run 5.0 on both formats, 1.01 variety preserved |
| Form of D-6's rounds-3+ softening | a **one-boundary allowance** (`MOCK_RUN_CROSS_ALLOWANCE_LATE = 1`), not a score penalty | expressed in the same units as the thing it softens; keeps `cpu_pick`'s scoring loop byte-identical so the geometric law survives; one integer a test can pin |
| Shape of the need-conditional weight | `bpa_eff = 1 − (1 − bpa_prob) × (floor + (1 − floor)·max_severity)`, `MOCK_IDIOSYNCRASY_FLOOR = 0.25` | D-5 exactly: 90 % reach at maximal need (unchanged), 22.5 % at zero need (survives). `max` not mean, because "how badly does this team need anything" is the worst hole |
| Where the run is computed | per pick, over the **windowed candidate head** (`available[:24]`), the same object `cpu_pick` scores | makes the two call sites provably agree; a run longer than the 15-slot cap is indistinguishable from no run, so the 24-wide head loses nothing |
| Kill switch | none; ship on `draft.mock` | a flag read inside the calibration harness is a correctness hazard; W2e set the precedent; reasoning and the alternative in [`scope.md` §2.1](./scope.md#21-does-the-engine-change-need-its-own-kill-switch) |
| ADR? | **no ADR; one `DECISIONS.md` entry** | no new module, boundary, storage or contract. W2b and W2e — both larger changes to this model — took none. The durable, reusable decision is "an engine-internal cluster must never use the cross-client tier enum", now made twice (#279 was the first) |
| Glossary term? | **yes** — "Run (draft)" | it is a new domain term that appears in code, comments and a design doc |

### F. Open questions for the Planner's review

Ordered by how much a disagreement would cost.

**F-1 — Is B-1 right?** This is the largest departure. The plan's headline
acceptance test is deleted and replaced. My case: Tate is #2, he shares a run with
Tyson and Lemon, and a test asserting `P(Tate ≤ 4) → 0` would encode a model
neither D-9 nor the value data supports. If you think the operator's sentence
should be read as "Tate should go 1st or 2nd, full stop", say so — that is a
*pricing* position and it would need a different fix in a different lane, not a
different test here.

**F-2 — Is R-11's third clause the right bar?** `P(consensus #7 at pick ≤ 4) <= 0.02`
against a shipped ~11 %. I chose 0.02 rather than 0 because the run structure is
data-dependent: if a future consensus refresh puts #7 in the same run as #4, a
hard 0 would be wrong. Is a strictly positive bar too soft for a falsification
handle the operator is meant to trust?

**F-3 — Is the one-boundary allowance the right reading of D-6?** D-6 says
"softer penalty in rounds 3+" and I chose a candidate-set allowance over a score
penalty (E, row 2). A penalty is closer to the word "penalty"; my objection is
that it perturbs the noise family. Do you read D-6 as requiring a score term?

**F-4 — Is `MOCK_IDIOSYNCRASY_FLOOR = 0.25` defensible, or is it the one
un-measured number left?** Everything else in this PRD is backed by a
measurement; the floor is a judgment that 22.5 % "feels like idiosyncrasy
surviving". I could not find evidence to fit it on — neither calibration corpus
carries the roster state needed to condition observed reaches on severity. Should
the PRD say so more loudly, or should the build agent measure the resulting
round-1 texture (distinct-ordering count) at 0.15 / 0.25 / 0.35 and pick?

**F-5 — B-6's tier-label relocation.** It changes a #277 surface. I judged
"relocate to the meta line" strictly better than the three alternatives, but it
is the one place where I made a visual-design call that a design review would
normally own. Push back if you think the section-header + on-the-clock hint alone
satisfies D-7 without touching the row.

**F-6 — Should the Maestro flow assert the *second* mock's board differs from the
first's?** It currently asserts only that a second mock reaches
`mock-draft.on-the-clock`. Asserting a different board would catch a
"create returns the old row" regression, but it needs a stable id to compare and
the flow has none. Worth a `mock-draft.rail` state assertion instead, or leave it
to T-292-04?

### G. Open items for the operator

Reproduced from [`scope.md` §7](./scope.md#7-open-items-for-the-operator) so the
Planner can weigh in before they go up:

- **O-1** — the Tate reframe (§B-1/B-2). **Tate will still go 4th about one time
  in six after the fix**, and the operator should agree that is correct before
  the build runs.
- **O-2** — accept the analytics waiver.
- **O-3** — accept "no new kill switch".
- **O-4** — accept the partial Maestro waiver.
- **O-5** — file-ownership: G2 needs `DraftRoomScreen.tsx` and
  `MockEntryPanel.tsx`, which the batch plan's table does not assign to anyone.
