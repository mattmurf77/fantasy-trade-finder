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
- [Round 2 — Planner review](#round-2--planner-review)
  - [H. Independent re-measurement](#h-independent-re-measurement)
  - [I. Objections](#i-objections)
  - [J. Answers to the Author's six open questions](#j-answers-to-the-authors-six-open-questions)
  - [K. Where the Author improved on the plan](#k-where-the-author-improved-on-the-plan)
  - [L. Verdict](#l-verdict)

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

---

## Round 2 — Planner review

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` · **Reviewer:** planner agent

Everything the Author measured on `1qb_ppr` reproduces **exactly** — to three
decimals, independently, from a clean tree. The board table, the shipped
pathology, the `m = 2.5` result, the median-run figure, the two D-16 sites, the
five stale docs, the `testid-lint` pass and the 80-test baseline all hold. This is
the strongest Round-1 output I have reviewed.

It also has a defect that would have shipped a **deterministic 1.01 to every
superflex/TE-premium league**, and a test plan that passes on it. That is the
"test that passed on the very bug it named" pattern, and it is the reason for a
NO verdict.

### H. Independent re-measurement

Method: implemented `lld-delta.md` §2.2's `run_offset` **verbatim** in a scratch
script (no production code written, tree clean), drove the shipped
`mds.cpu_pick` over `backend.tests.test_mock_draft._rookie_ctx`'s board, N = 2000
seeded 12-team linear round-1 replays, `random.Random(s*10007+pk)`. Baseline
suite re-run: `python3 -m pytest backend/tests/test_mock_draft.py -q` →
**80 passed in 194s**, confirming A-4's denominator.

**H-1 — the board. CONFIRMS A-1 exactly.**

| | 1qb_ppr | sf_tep |
|---|---|---|
| 1 | Jeremiyah Love 1886.9 | Jeremiyah Love 1859.0 |
| **2** | **Carnell Tate 1817.5** | **Carnell Tate 1776.5** |
| 3 | Jordyn Tyson 1771.3 | Jordyn Tyson 1722.5 |
| 4 | Makai Lemon 1746.4 | Fernando Mendoza 1719.1 |

Pool size 89 both formats. **Tate is the consensus #2. Tate at 4th is a two-slot
fall, not a reach. A-1 is confirmed and Spike A is correctly closed.**

Top-of-board gaps — 1qb_ppr: `69.5 · 46.1 · 24.9 · 79.2 · 27.1 · 41.8 · 28.8 ·
27.5`; sf_tep: `82.6 · 54.0 · 3.4 · 17.3 · 86.0 · 8.5 · 14.4 · 31.0`.

**H-2 — behaviour. CONFIRMS A-2 and A-3 on `1qb_ppr`; REFUTES the generalisation
to `sf_tep`.**

| Format | Config | P(#1 at 1.01) | P(#1 past 3) | P(Tate past 4) | P(Tate **at** 4) | distinct top-4 |
|---|---|---|---|---|---|---|
| 1qb_ppr | SHIPPED | 0.451 | 0.158 | 0.165 | 0.101 | 173 |
| 1qb_ppr | m = 2.4 | **1.000** | 0.000 | 0.000 | 0.074 | **5** |
| 1qb_ppr | **m = 2.5** | 0.451 | 0.024 | 0.000 | 0.172 | 18 |
| 1qb_ppr | m = 2.6 | 0.451 | 0.024 | 0.000 | 0.172 | 18 |
| 1qb_ppr | m = 3.0 | 0.451 | 0.033 | 0.041 | 0.188 | 68 |
| sf_tep | SHIPPED | 0.451 | 0.158 | 0.165 | 0.101 | 173 |
| sf_tep | m = 2.4 | **1.000** | 0.000 | 0.054 | 0.205 | 22 |
| sf_tep | **m = 2.5** | **1.000** | 0.000 | **0.100** | 0.160 | 24 |
| sf_tep | m = 2.6 | **1.000** | 0.000 | 0.100 | 0.160 | 24 |
| sf_tep | m = 3.0 | 0.451 | 0.051 | 0.135 | 0.108 | 76 |

Every 1qb_ppr figure matches A-2/A-3 to three decimals, including "Tate still goes
4th about one time in six" (measured 0.172).

*Aside worth recording:* the SHIPPED rows are **identical across both formats**.
That is not a coincidence — it is the defect stated as a measurement. The shipped
model reads only list position, so a board reshuffle that moves 80 Elo around
changes nothing. Consider putting this in R-1's docstring; it is the cleanest
one-line proof of "rank-blind" in the whole package.

**H-3 — the structural cause, at the pre-draft head:**

| `run_offset(pool[:24], allow_cross=0)` | m=2.0 | m=2.4 | **m=2.5** | m=2.6 | m=3.0 |
|---|---|---|---|---|---|
| 1qb_ppr | 0 | 0 | **3** | 3 | 10 |
| sf_tep | 0 | 0 | **0** | 0 | 14 |

`run_offset = 0` ⇒ `cap = min(cap, 0) = 0` ⇒ `cpu_pick` truncates to `[:1]` ⇒
**pick 1.01 is forced.** On sf_tep, `82.6 ≥ 2.5 × median` because that board's top
is lumpier (`3.4`, `8.5`, `14.4` drag the local median down).

**H-4 — run-size definition. CONFIRMS 5.0 / 5.0, under one definition of two.**

| Definition | 1qb_ppr | sf_tep |
|---|---|---|
| One-pass boundaries over the full pool | **5.0** | **5.0** |
| Sequential `run_offset(pool[start:])` re-scan | 4.0 | 3.0 |

The Author used one-pass (also reproducing the `m=2.0` → 3.5 / 4.0 row exactly).
Both are defensible; the LLD pins neither. See O-9.

### I. Objections

#### I-1 — BLOCKING. `m = 2.5` forces pick 1.01 on `sf_tep`.

`lld-delta.md:40-46` will ship this in a constant docstring:

> "2.5 is not a taste call. On the pinned 2026 consensus board it yields a MEDIAN
> RUN OF 5 players on BOTH scoring formats … while leaving P(consensus #1 goes
> 1.01) exactly where the shipped engine has it (45.1%)."

The first clause is true (H-4). **The second is false on `sf_tep`, where the
measured value is 1.000, not 0.451** (H-2). Every superflex or TE-premium league
— `settings["scoring_format"]` is snapshotted per mock at
`mock_draft_service.py:783`, and `_lakeview_corpus` itself runs `sf_tep`
(`test_mock_draft.py:1546`) — gets a mock whose first pick is a foregone
conclusion and whose round-1 variety drops 173 → 24.

This is precisely the collapse D-6 was written to prevent, and the PRD's own
words for it (`prd.md`, R-12) are "the guard against 'fixed' silently meaning
'deterministic BPA'".

Root cause of the miss: the median-run statistic was computed on both formats, the
**behavioural** metrics on one, and the two were reported in adjacent rows of the
same table (A-3), which reads as though both were validated on both.

**Change required:** re-run the A-3 sweep on **both** formats and choose a
parameter that clears the cliff on both, or accept a per-format parameter with an
explicit operator ruling. Correct the `MOCK_RUN_GAP_MULTIPLE` docstring before it
ships. Note m = 3.0 restores 0.451 on both formats but widens the first run to 11
(1qb_ppr) / 15 (sf_tep), breaking R-2's 4-5 median — so there may be **no single
`m` that satisfies R-2 and R-11/R-12 simultaneously on both boards.** If so, that
is a finding for the operator, not something to tune around quietly.

#### I-2 — BLOCKING. `m = 2.5` is the edge of a cliff, not an optimum.

The orchestrator asked what happens at 2.4 and 2.6. Answer (H-2): **2.6 is
identical to 2.5; 2.4 collapses 1qb_ppr to P(#1 at 1.01) = 1.000 and 5 distinct
orderings.** A-3 attributes that collapse to `m = 2.0`; it actually arrives at
**2.4 — four percent below the chosen value.** The chosen parameter sits directly
on a discontinuity, on the good side by one board's worth of luck.

`prd.md` R-2 says the test "recomputed from the fixture so a consensus refresh
moves the test rather than silently invalidating the parameter." Given I-1 + I-2,
the opposite is true: **a routine consensus refresh can move a single top-of-board
gap across the threshold and silently force 1.01.** The KTC blend refreshes; this
is not hypothetical.

**Change required:** state the cliff explicitly in the constant's docstring and in
`scope.md`, with the measured 2.4 value; and add a **guard test** that fails if the
first-run offset at the pre-draft head is 0 on either format (a direct structural
assertion, not a distributional proxy — see I-3).

#### I-3 — BLOCKING. The test plan cannot detect I-1. Two tests pass on the collapsed board.

Against sf_tep at `m = 2.5` (H-2):

| Test | Assertion (`prd.md:532-533`) | Value on the collapsed board | Result |
|---|---|---|---|
| T-290-10 cl. 1 | `P(pool[0] at pick 1) >= 0.43` | **1.000** | **PASSES** |
| T-290-10 cl. 1 | `P(pool[0] past pick 3) <= 0.05` | **0.000** | **PASSES** |
| T-290-11 | `>= 12` distinct round-1 top-4 orderings | **24** | **PASSES** |

Both bars are **one-sided in the wrong direction.** The collapse pushes
`P(#1 at 1.01)` *up* and R-11 only floors it. And "distinct top-4 orderings" is a
poor proxy for "1.01 is free": sf_tep collapsed scores 24, *higher* than 1qb_ppr
healthy at 18, because picks 2-4 retain freedom while 1.01 is nailed shut. **The
variety guard is numerically incapable of catching the thing it exists to catch.**

**Change required, three parts:**
1. Add an **upper** bound to R-11 clause 1: `P(pool[0] at pick 1) <= 0.60`
   (shipped 0.451; collapse 1.000). This is the single assertion that catches it.
2. Add a direct structural assertion: `run_offset(pool[:24], allow_cross=0) >= 1`
   for **both** formats. Cheap, deterministic, no seeds, and it fails loudly at
   the cause rather than the symptom.
3. Raise T-290-11's bar or scope it per format — 12 is below both the collapsed
   sf_tep value (24) and the rejected `m=2.0` 1qb_ppr value it was meant to
   exclude only by accident.

#### I-4 — BLOCKING. T-290-10 does not say which scoring format, and one clause fails on `sf_tep`.

`prd.md:532` reads "N ≥ 500 seeds on the pinned board" — singular, unqualified —
while its sibling T-290-03 (`:525`) explicitly says "for `1qb_ppr` **and**
`sf_tep`". The clauses are also format-coupled by construction: clause 2 names
Carnell Tate, clause 3 indexes `pool[6]`.

Measured on sf_tep at `m = 2.5`: clause 2 (`P(Tate past 4) == 0`) is **0.100 —
it fails.** So a build agent handed this ambiguity will run T-290-10 on
`1qb_ppr`, where all four clauses pass, and the sf_tep collapse ships unobserved.
If they instead run it on sf_tep, they will see a Tate-clause failure and most
likely relax *that assertion* — diagnosing the symptom, never reaching the
forced-1.01 cause.

**Change required:** name the format(s) explicitly in T-290-10, T-290-11 and R-11,
and specify per-format expected values.

#### I-5 — BLOCKING. B-3 is right for one completed mock and wrong for the steady state.

Verified: `update_mock_draft`'s `WHERE` is id + user_id only
(`database.py:10798-10799`) and no route guard reads status
(`server.py:11794-11797`), so abandoning a `complete` row does return `{ok: true}`.
**B-3's premise is correct.** But `load_current_mock_draft`'s complete-fallback is
`ORDER BY id DESC LIMIT 1` (`database.py:10774-10781`), and `create_mock_draft`
abandons only prior **active** rows (`:10739`) — so complete rows accumulate, one
per finished mock, forever.

Consequence: **dismiss the newest completed mock and the previous one appears.**
The user must dismiss once per historical mock. For anyone past their second mock
— i.e. exactly the #292 population — the dead-end is not fixed, it is paginated.

R-14 / T-292-01 (`prd.md:536`) asserts only the single-row case ("a subsequent GET
returns `no_active_mock`"), so it passes while the defect stands. Same pattern as
I-3.

**Change required:** either loop the client dismissal until `GET` returns
`no_active_mock`, or give the complete-fallback a "dismissed" concept. Whichever
is chosen, T-292-01 must seed **two** completed mocks and assert the surface
clears. G2's release of its `database.py:10714-10805` region claim should be held
until this is settled.

#### I-6 — BLOCKING. D-5 is not delivered: the spec changes reach *frequency*, never reach *direction*.

The operator's sentence is *"reaching should more so be to fill a position of need
than just random"* — that is about **what** a bot reaches for. `effective_bpa_prob`
(`lld-delta.md:245-269`) modulates only **how often** it reaches. What it reaches
*for* is still the untouched additive `bonus = weight × severity × max_reach` at
`mock_draft_service.py:648` — the term this plan measured at ≤ 1.5 slots for a
`not_sure` bot and called "effectively inert", a diagnosis the Author adopted whole
(C-2). Nothing in R-7/R-8 strengthens it.

Worse, `max()` over positions makes the tilt near-binary. `slot_targets` gives TE
`(S,B) = (1,0)` — denominator 1 — so **a team with no viable TE scores
`max_severity = 1.0` and gets `effective_bpa_prob == bpa_prob`: today's behaviour,
exactly.** A 1280+ dynasty TE is not universal. The tilt only bites for teams full
at *every* position, which is the rare case, so R-8's 22.5 % is close to a
measure-zero state in production.

Supporting measurement — all 12 lakeview teams score `max_severity = 1.0` and
`effective_bpa_prob = 0.1000`, i.e. the change is a **complete no-op** on that
corpus. *Caveat, stated honestly:* that corpus builds `viable0` from
**rookie-only** Elo (`test_mock_draft.py:1546` + `_lakeview_corpus`), so veterans
price as `None` and every count is 0 — it is a harness artifact, not a production
roster distribution. It does not prove the production claim. It does prove I-9.

**Change required:** either (a) strengthen the positional term so need steers *what*
is taken — the only thing that actually answers the operator — or (b) state
plainly in `prd.md` and in O-1 that R-7/R-8 govern frequency only, that direction
is unchanged, and get the operator to confirm that satisfies D-5. **(b) is
acceptable; silence is not.** Also reconsider `max()` versus a
denominator-weighted aggregate, and say why in the docstring.

#### I-7 — NON-BLOCKING. B-2's "two tightest gaps" is overstated.

B-2 argues Tate→Tyson and Tyson→Lemon "are the two **tightest** gaps at the top".
On 1qb_ppr they are 46.1 and 24.9; 24.9 is indeed tightest, but 46.1 ranks **5th
of the first 8** (27.1, 27.5, 28.8 are all tighter). The conclusion — that Tate
shares a run with Tyson and Lemon — is correct and independently confirmed (H-3:
first run = Love/Tate/Tyson/Lemon at m=2.5). Only the superlative is wrong. Soften
the wording; the argument does not need it.

#### I-8 — NON-BLOCKING. B-4's "zero seeder work" is overstated.

`testid-lint.sh` exits 0 — confirmed. The ffv3 fixture is 12 teams, `pre_draft`,
linear — confirmed. `draft_order: null` only degrades `order_source`
(`server.py:11531-11532`, docstring `:11525-11526`) and blocks nothing — confirmed.
The seeder writes no `mock_drafts` rows and does not need to, since
`POST /api/mock-draft` creates its own — confirmed.

But `d2-draft-room-order-not-set.yaml:3` declares its profile as *"standard +
ffv3-predraft corpus merged into the fixture dir"* and **no tooling implements
that merge.** `seed_ui_test_db.py:830-832` builds the Leagues list purely from the
profile's own `leagues[]`, and `standard.json` declares one league
(`990000000000000001`); the ffv3 corpus contains no `user/…/leagues/nfl/*`
document, so a file copy cannot put `leagues.row.1312140920132497408` on screen.
Two wrinkles for the flow author: the fixture's **top-level `rounds` is `null`**
(the 4 lives in `settings.rounds`), and d1/d2 are referenced by no suite file or
runner, so their current green status is unverified.

**Change required (doc-only):** restate B-4 and the scope block as *"zero **new**
seeder work beyond the pre-existing corpus-merge gap `d1`/`d2` already depend on"*,
and name that gap as a precondition of the Maestro flow rather than an assumption.

#### I-9 — NON-BLOCKING, but it devalues D-10. The calibration harness never exercises the need term.

Because `_lakeview_corpus` prices rosters with rookie-only Elo, every owner enters
`simulate_reaches` at `max_severity = 1.0`. Under the new mixture weight that is
exactly `bpa_prob`, so **the need-conditional half of this change is invisible to
the calibration harness.** D-10's "run-and-record against a regression bar" will
therefore report the run rule's effect and *nothing* about R-7/R-8, and a
green-looking regression bar will be partly vacuous. Say so where D-10 is
recorded, so nobody reads that result as broader validation than it is. (The
harness artifact is pre-existing and out of scope to fix here.)

#### I-10 — NON-BLOCKING. The run rule substantially overrides the operator's round-2 cap.

Measured at `pool[24:]` (round-2 depth), 1qb_ppr: `run_offset(allow_cross=0) = 1`,
so the effective round-2 cap is **1** against the operator's stated 5. Contract-legal
— `min()` only tightens, R-5 holds — but the operator ruled that table verbatim in
W2e and should know their 3/5/15 is in practice often 3/1/x. One line in `scope.md`
under O-1.

#### I-11 — NON-BLOCKING. R-12's only test passes on unfixed code.

T-290-11 asserts `>= 12` distinct orderings; shipped is 173. It cannot fail on the
unfixed engine, so the orchestrator's "every requirement maps to ≥1 test that would
fail on the unfixed code" is not met for R-12. **This is acceptable** — R-12 is a
non-regression guard, not a fix verifier, and `prd.md:541` correctly marks only
T-290-04 and T-290-10 failing-first. Recommend adding T-290-11 to the failing-first
list *inverted* (assert it fails at `m = 2.0`), which is the only way to prove the
guard has teeth. Note I-3 raises the substantive problem with its threshold.

#### I-12 — NON-BLOCKING. Pin the run-size definition or T-290-03 is unimplementable.

H-4: one-pass gives 5.0/5.0, sequential re-scan gives 4.0/3.0 — **the sequential
value fails T-290-03's `4 <= median <= 5` on sf_tep.** Two engineers will read
"median run size" differently and one of them will have a red test. `lld-delta.md`
§2.2 specifies `run_offset` precisely but never defines the *partition*. Add the
one-pass algorithm explicitly to T-290-03, or express the test in terms of
`run_offset` calls so there is only one reading.

#### I-13 — NON-BLOCKING. Determinism is fine; say so.

All distributions here are exactly reproducible — `_pick_rng` stays a pure
function of `(rng_seed, pick_no)` and my replays reproduce to three decimals across
runs. No flake risk **provided the tests pin their seed range explicitly**; the PRD
gives N but not the seed base. Add `range(N)` (or an explicit constant) to
T-290-04/05/09/10/11 so a rerun cannot drift.

#### I-14 — Verified, no objection: the `min()` placement and the AST constraint.

`effective_cap <= round_reach_cap(r)` holds by construction — `min()` cannot
loosen — and `cap == 0` is skipped rather than `min()`'d, so "strict best
available" stays the operator's words. `test_w2_21…verbatim` (`:332`) and
`test_w2_21_a_round_never_spends_more_than_its_frequency_budget` (`:362`) are
untouched. `run_offset` as specced is a single forward walk with no `sorted`/`.sort`,
so `test_w2_14` (`:708`) stays green; `import statistics` clears the allow-list at
`:764`. The plan's §4.3.2 placement is adopted correctly and I withdraw nothing.

#### I-15 — Verified, no objection: the `_reach_draws` fixture change is legitimate.

I scrutinised this as instructed. `_reach_draws` builds
`board = _candidates(["WR"] * width)` (`test_mock_draft.py:233`) — a
**single-position** board — so `bonus = weight × needs["WR"] × max_reach` is
identical for every candidate and cancels out of the argmin. At `needs = 1.0`,
`effective_bpa_prob` returns exactly `bpa_prob`. The helper therefore measures the
**identical law** while restoring the branch the test names. **This is a fixture
correction, not an assertion weakening.** A-4's characterisation is accurate.

On the broader question — "80 passed is either good news or evidence the tests
don't constrain the behaviour": **it is the latter, and that is expected.** The
existing 80 tests pin invariants (determinism, resume identity, budget accounting,
the policy table, AST shape), not the reach *distribution*. The only existing test
that touches the distribution is `test_w2_04b…geometric`, and it did fire on the
first prototype. So the suite behaved correctly; it simply has almost no
distributional coverage, which is why all the constraint must come from the 13 new
tests — and why I-3 and I-4 are blocking rather than cosmetic.

### J. Answers to the Author's six open questions

**F-1 — Is B-1 right? YES. Adopt it; my plan's assertion was wrong.**
Independently confirmed: Tate is consensus #2 at 1817.5 / 1776.5 (H-1), and the
first run at `m = 2.5` is {Love, Tate, Tyson, Lemon} (H-3). `P(Tate ≤ 4) → 0`
would require either a size clamp (D-9 forbids) or a wall between players 46.1 Elo
apart — tighter than three other gaps in the same top-eight (I-7) — which would
shred the board. My §4.3.5 acceptance test encoded the wrong model and the
replacement is correct. **One caveat that is now blocking for a different reason:**
R-11's clauses are format-coupled and clause 2 fails on sf_tep (I-4).

**F-2 — Is `P(#7 ≤ 4) <= 0.02` too soft? NO, it is well judged.** Measured: shipped
**0.1105** on both formats (matching my plan's 10.9 %), and **0.0000** at `m = 2.5`
on both. The bar is pure robustness slack against a consensus refresh merging runs,
exactly as you reasoned. Keep 0.02. It is also the *only* clause of R-11 that
behaves identically on both formats — worth noting in its docstring.

**F-3 — Is the one-boundary allowance the right reading of D-6? YES.** I read D-6's
"penalty" as intent, not as a term in the scoring function, and your objection —
that a score penalty perturbs the noise family and costs the Gumbel-max identity —
is the stronger argument. It is also **not hand-waved**: measured at the pre-draft
head, `allow_cross` 0→1 moves the offset 3→10 (1qb_ppr) and 0→4 (sf_tep), and at
`pool[24:]` 1→5 and 4→7. The softening is real, parameterised, and testable by
T-290-05. Adopted.

**F-4 — Is `MOCK_IDIOSYNCRASY_FLOOR = 0.25` defensible? The floor is not the
problem — the aggregation is (I-6).** Measuring round-1 texture at 0.15/0.25/0.35
would not help, because on realistic rosters `max_severity` pins at 1.0 and the
floor is never reached. Fix the D-5 gap first; then the floor is a minor knob and
"say so loudly in the PRD" is sufficient. Do **not** spend a build-agent sweep on
it.

**F-5 — B-6's tier-label relocation. Endorsed.** You are right that leaving it to
design review hands a build agent a judgment call the LLD contract forbids, and
relocation is the only option that deletes no shipped information. Keep
`actionLabel={isUserTurn ? 'Pick' : undefined}` so the CPU-turn render stays
byte-identical — that detail is better than my §4.2. Flag it to the operator as a
#277 surface change (it already is, via O-1's neighbours).

**F-6 — Should the Maestro flow assert the second mock's board differs? NO.**
Leave it to T-292-04, which can compare `mock_id` directly and cheaply. A
`mock-draft.rail` state assertion is the right lightweight addition. Given I-5,
add one flow step that matters more: dismiss a completed mock **twice** and assert
the card reaches "No mock running".

### K. Where the Author improved on the plan

Recorded as audit trail. In each case the Author was right and I was wrong.

1. **A-1 / B-8 — Spike A and Spike B were not blocking.** I declared ~4-5 h of
   blocking spikes on the premise that the local DB was empty and the fixtures
   carried no names. The Author found the join I had myself cited
   (`_rookie_ctx`) reproduces the shipped board hermetically. **Two spikes and an
   operator sign-off gate removed from the critical path.** This is the single
   biggest improvement in the round.
2. **B-1 / B-2 — my headline acceptance test was wrong.** It would have encoded a
   model the value data does not support, and the layered "model form *and*
   possibly pricing, with tests that separate them" framing is better than my
   either/or.
3. **B-5 — the second D-16 site (`:11474`).** I cited neither. The resume path is
   the common case, and fixing only create would have left every reloaded mock
   rendering ids. Independently confirmed, including that `:11437` is right and
   G1's `:11438` is off by one.
4. **B-9 — five stale doc locations, not my two**, and my `config/features.json:145`
   was the wrong line (`:145` is `deck.first_session`). Confirmed, plus a sixth
   the Author did not list: `backend/feature_flags.py:462` carries the same stale
   "calibration gate FAILED" comment.
5. **B-3's premise** — the abandon route genuinely has no status guard. My §4.1
   proposed a route change that is not needed. (The multi-row consequence in I-5
   is a separate defect, not a defence of my original design.)
6. **B-6 and E row 2** — both resolve judgment calls I left open in a way a build
   agent can execute blind. That is the correct standard and my plan fell short of
   it in two places.
7. **A-4 — measuring the blast radius by prototyping rather than estimating**, then
   reverting. My R1 risk table guessed; the Author measured.

### L. Verdict

**NO — not ready for a build agent to implement blind.**

Six blocking objections. I-1 and I-3 are the pair that matter: the chosen
parameter forces pick 1.01 on every superflex/TE-premium league, and the two tests
written to prevent exactly that outcome both pass on it. I-2 shows the parameter
sits on a discontinuity 4 % wide. I-4 is the ambiguity that would route a build
agent away from ever seeing it. I-5 leaves #292 unfixed for any user past their
second mock, with a test that passes anyway. I-6 is a scope gap against D-5 that
needs either more work or an explicit operator waiver.

None of these is a rewrite. I-2, I-4 and I-8…I-13 are edits. I-3 and I-5 are test
additions. **I-1 is the only one that may need a new measurement round** — and it
may surface a genuine finding for the operator: that no single
`MOCK_RUN_GAP_MULTIPLE` satisfies R-2 and R-11/R-12 on both shipped boards at once.
That question should go up with O-1 rather than be tuned away.

Recommend Round 3: Author re-sweeps both formats, resolves I-1/I-5/I-6, patches the
test plan per I-3/I-4, and applies the doc corrections. No further Planner round
needed if the re-sweep is reported per-format.

---

## Round 3 — Author incorporation

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` · **Author agent**

The review is correct on all six blocking objections. I-1/I-3 in particular are a
real defect in my Round-1 output: I measured the median-run statistic on both
formats and the behavioural statistics on one, printed them in adjacent rows, and
the adjacency did the arguing. That is the exact failure the Planner named.

**All 14 objections are accepted.** Two are accepted with a correction to their
*framing* (I-6, I-8) where new measurement changes what the fix should be. Nothing
is rebutted outright. I also **withdraw a Round-1 adoption** (C-2) that further
measurement shows to be overstated.

### M. The re-sweep, reported per format

Method as Round 1: `run_offset` per `lld-delta.md` §2.2, shipped `mds.cpu_pick`,
`_rookie_ctx` board, 12-team linear, explicit order, user last, seeds `range(N)`,
N = 1500. Tree clean throughout (scratch scripts only, outside the repo).

**M-1 — structural sweep, both formats. CONFIRMS I-1 and the Planner's
"there may be no single `m`" prediction.**

`run_offset(pool[:24], allow_cross=0)` / median one-pass run size over the full pool:

| W | m | 1qb off | 1qb med | sf off | sf med | verdict |
|---|---|---|---|---|---|---|
| 9 | 2.2 | **0** | 4.0 | **0** | 5.0 | collapse both |
| 9 | 2.4 | **0** | 4.0 | **0** | 5.0 | collapse both |
| 9 | **2.5** | 3 | 5.0 | **0** | 5.0 | **collapse sf** |
| 9 | 2.6 | 3 | 5.0 | **0** | 4.5 | collapse sf |
| 9 | 2.8 | 10 | 8.5 | 14 | 5.0 | clears — but 1qb median 8.5 |
| 9 | 3.0 | 10 | 11.0 | 14 | 5.0 | clears — 1qb median 11.0 |
| 9 | 3.5 | 14 | 15.0 | 23 | 22.0 | clears — medians blown |
| 15 | 2.5 | 3 | 5.0 | **0** | 4.0 | collapse sf |
| 15 | 3.0 | 10 | 8.5 | **0** | 4.0 | collapse sf |
| 15 | 3.2 | 10 | 11.0 | 4 | 5.0 | clears — 1qb median 11.0 |
| head-median (no local window) | 2.2 – 4.0 | 0 – 23 | **1.0** | **0** | 1.0 | collapses everywhere |

**Finding: there is no `(m, W)` in this family that clears `run_offset >= 1` on
both formats AND holds a 4-5 median run on both.** The Planner predicted this; it
is confirmed across 27 configurations. I also tested a whole-head median (one
scale per 24-row slice) as a stabiliser — it is strictly worse, collapsing both
formats at every `m` and driving the median run to 1.0.

**M-2 — why, structurally.** 1qb_ppr top gaps `69.5 · 46.1 · 24.9 · 79.2 · 27.1 ·
41.8 · 28.8 · 27.5` give a 9-window median of 28.8, so gap[0] scores
`69.5 / 28.8 = 2.41` — the cliff sits at 2.41, and the chosen 2.5 clears it by
**3.7 %**. sf_tep's head is lumpier (`82.6 · 54.0 · 3.4 · 17.3 · 86.0 · 8.5 ·
14.4 · 31.0`); the small gaps drag the median down so gap[0] clears any `m` up to
~2.7 and walls Love off alone. **The parameter was not tuned, it was lucky** —
exactly as the Planner put it.

### N. Resolution of I-1 / I-2: a floor on the composed cap, not a different `m`

The tension M-1 exposes is between two *different things* that `m` was doing at
once: defining **where the runs are** (a property of the data — R-2) and deciding
**how tight a wall may be** (a property of the behaviour — R-11/R-12). One
parameter cannot serve both, which is why no `m` works.

**Resolution — separate them.** Keep `m = 2.5, W = 9` for the partition, and add a
floor to the *composition*:

```python
cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
if cap > 0:
    cap = min(cap, max(run_offset(head, allow_cross=…), MOCK_RUN_MIN_OFFSET))
```

Four properties, each load-bearing:

1. **It is not the clamp D-9 forbids.** D-9 rejects clamping runs *down* to 4-5,
   because that "manufactures boundaries where the values have none". A floor only
   ever **suppresses** a boundary's effect on the cap; it can never create one. It
   states a product rule — *"a bot may always consider at least N+1 available
   players, however large the gap above them"* — not a claim about the values.
2. **The partition is untouched, so R-2 survives.** Median run stays **5.0 / 5.0**
   on both formats at `m = 2.5` regardless of the floor. The Planner's "no single
   `m` satisfies R-2 and R-11/R-12" finding is *dissolved* rather than tuned
   around: R-2 is now measured on the partition and R-11/R-12 on the composition.
3. **It cannot loosen the operator's W2e cap.** The outer `min(round_reach_cap(r), …)`
   still binds, so `effective_cap <= round_reach_cap(r)` holds by construction and
   R-5 is unchanged. Tested (T-290-06, extended).
4. **It removes the cliff.** Measured below: with a floor, `m` from 2.2 to 2.6
   behaves smoothly instead of discontinuously.

**N-1 — the floor sweep, both formats** (N = 1500, `m = 2.5`, `W = 9`):

| Config | fmt | P(#1@1.01) | P(#1>3) | P(Tate>4) | P(Tate@4) | P(#7≤4) | distinct | med run | eff off |
|---|---|---|---|---|---|---|---|---|---|
| SHIPPED | 1qb_ppr | 0.455 | 0.155 | 0.171 | 0.100 | **0.1147** | 171 | — | — |
| SHIPPED | sf_tep | 0.455 | 0.155 | 0.171 | 0.100 | **0.1147** | 171 | — | — |
| MIN = 0 | 1qb_ppr | 0.455 | 0.025 | 0.000 | 0.177 | 0.0000 | 18 | 5.0 | 3 |
| MIN = 0 | sf_tep | **1.000** | 0.000 | 0.103 | 0.159 | 0.0000 | 24 | 5.0 | **0** |
| **MIN = 1** | 1qb_ppr | 0.455 | 0.089 | 0.073 | 0.103 | 0.0000 | 39 | 5.0 | 3 |
| **MIN = 1** | sf_tep | 0.638 | 0.042 | 0.073 | 0.107 | 0.0000 | 33 | 5.0 | 1 |
| MIN = 2 | 1qb_ppr | 0.455 | 0.127 | 0.128 | 0.094 | 0.0000 | 84 | 5.0 | 3 |
| MIN = 2 | sf_tep | 0.520 | 0.107 | 0.120 | 0.095 | 0.0000 | 74 | 5.0 | 2 |
| MIN = 3 | either | 0.455 | 0.155 | 0.171 | 0.100 | 0.1147 | 171 | 5.0 | 3 |

Three things worth stating plainly:

- **`MIN = 3` is a complete no-op in round 1** — the round-1 cap *is* 3, so
  `min(3, max(off, 3)) = 3` always, and every figure reverts to SHIPPED exactly.
  A boundary condition that must be pinned by a test, or a later "safety" bump of
  the floor would silently disable the whole feature.
- **The reported defect is fixed at every floor in 0…2.** `P(consensus #7 reaches
  pick ≤ 4)` goes `0.1147 → 0.0000` on **both** formats at MIN 0, 1 and 2. The
  thing the operator actually saw — a player far below the tier landing at the top
  of the draft — is gone regardless of which floor is chosen.
- **The floor is a dial between tier discipline and board variety**, and the
  choice is an operator call, not a modelling one. MIN = 0 pins the top-4 order
  hardest (18 orderings) but forces 1.01 on superflex. MIN = 2 keeps the most
  variety (84/74) but only recovers ~20 % of the fall defect.

**N-2 — recommendation: `MOCK_RUN_MIN_OFFSET = 1`.** It is the *minimum*
intervention that makes a forced pick structurally impossible (a run of one can
never truncate the candidate set to a single player), it roughly halves both fall
probabilities on both formats, it zeroes the #7 pathology, and its outcome is
nearly format-symmetric (`P(Tate past 4) = 0.073` on both). `P(#1 at 1.01) = 0.638`
on sf_tep is high — but Love is 82.6 Elo clear of Tate there, the largest gap in
that board's top eight, so a strong favourite for 1.01 is the *correct* reading of
the data, not a collapse. What matters is that it is no longer 1.000.

**N-3 — the cliff is gone, and `m = 2.5` now sits mid-plateau.** Sweeping `m`
at `MIN = 1`, N = 1500, both formats:

| m | fmt | P(#1@1.01) | P(#1>3) | P(Tate>4) | P(#7≤4) | distinct | med run | eff off |
|---|---|---|---|---|---|---|---|---|
| 2.2 | 1qb_ppr | 0.638 | 0.042 | 0.053 | 0.0000 | 19 | 4.0 | 1 |
| 2.2 | sf_tep | 0.638 | 0.042 | 0.073 | 0.0000 | 33 | 5.0 | 1 |
| 2.4 | 1qb_ppr | 0.638 | 0.042 | 0.053 | 0.0000 | 19 | 4.0 | 1 |
| 2.4 | sf_tep | 0.638 | 0.042 | 0.073 | 0.0000 | 33 | 5.0 | 1 |
| **2.5** | **1qb_ppr** | **0.455** | **0.089** | **0.073** | **0.0000** | **39** | **5.0** | **3** |
| **2.5** | **sf_tep** | **0.638** | **0.042** | **0.073** | **0.0000** | **33** | **5.0** | **1** |
| 2.6 | 1qb_ppr | 0.455 | 0.089 | 0.073 | 0.0000 | 39 | 5.0 | 3 |
| 2.6 | sf_tep | 0.638 | 0.042 | 0.073 | 0.0000 | 33 | 4.5 | 1 |
| 2.8 | 1qb_ppr | 0.455 | 0.098 | 0.103 | 0.0020 | 56 | 8.5 | 10 |
| 2.8 | sf_tep | 0.455 | 0.113 | 0.139 | **0.0173** | 81 | 5.0 | 14 |
| 3.0 | 1qb_ppr | 0.455 | 0.098 | 0.107 | **0.0507** | 86 | 11.0 | 10 |
| 3.0 | sf_tep | 0.455 | 0.113 | 0.139 | 0.0173 | 81 | 5.0 | 14 |

Three readings:

- **The discontinuity is gone.** Across `m` = 2.2 → 2.6 the worst movement on
  either format is `P(#1@1.01)` 0.638 → 0.455 on 1qb_ppr — a gentle slope, against
  the un-floored **0.455 → 1.000** collapse across the same 2.4 → 2.5 step. sf_tep
  is *identical* at every `m` in that band. A consensus refresh that moves a
  top-of-board gap across the threshold now degrades `off = 3 → 1`, not `3 → 0`.
- **There is a safe plateau, and `m = 2.5` is inside it, not on its edge.**
  `P(#7 ≤ 4) = 0.0000` on both formats for every `m` in [2.2, 2.6]. It starts
  leaking at 2.8 (0.0173 on sf_tep) and **breaks R-11's 0.02 bar at 3.0**
  (0.0507 on 1qb_ppr). So `m` must be **≤ 2.6**, which independently rules out the
  `m = 2.8`–3.2 configurations M-1 offered as the only ones clearing the structural
  test without a floor. The floor is not one option among several; it is the only
  route to a parameter that is both safe and robust.
- **Median run stays 4.0–5.0 on both formats throughout the plateau**, so R-2 holds
  across the whole safe band rather than at a single point.

### O. Resolution of I-6 — accepted in substance, framing corrected, and I withdraw a Round-1 adoption

**O-1 — the aggregation objection is confirmed exactly.** Measured on a standard
lineup (`slot_targets` → QB (1,0) · RB (2,1) · WR (3,1) · TE (1,0)) with a roster
full at QB/RB/WR and **no** viable TE:

| Aggregate | value | `bpa_effective` | P(reach) |
|---|---|---|---|
| `max` (as specced in Round 1) | **1.000** | **0.100** | **0.900 — today's behaviour exactly** |
| `mean` over the four positions | 0.250 | 0.606 | 0.394 |
| **denominator-weighted** | **0.111** | 0.700 | 0.300 |

The Planner is right: `max()` makes R-7/R-8 a near-no-op, because a 1280+ dynasty
TE is not universal and TE's denominator is 1. **Adopted:** replace `max` with a
denominator-weighted aggregate — the share of the team's *slots* that are
unfilled, `Σ severity_p·(S_p+B_p) / Σ (S_p+B_p)`. It also fixes a second defect
`mean` would not: a team missing its whole WR corps and a team missing one TE both
score 0.25 under `mean`, but 0.44 and 0.11 under denominator weighting, which is
the honest ordering. Interface cost is one optional parameter on `cpu_pick`
(`need_pressure: float | None = None`, falling back to `max()` so the existing
unit tests keep their meaning) plus hoisting `slot_targets` in the two callers.

**O-2 — but the *direction* half of I-6 is factually wrong, and so was my Round-1
adoption of the plan's C-2.** I measured direction directly rather than arguing
it: a `championship` bot with `severity[RB] = 1.0` and zero elsewhere, on the real
board head, N = 6000 seeded `cpu_pick` calls.

| Round / config | cap | P(picks an RB) | RB share of the reachable window | lift |
|---|---|---|---|---|
| r1, SHIPPED | 3 | **0.693** | 0.250 | **2.77×** |
| r1, run rule + MIN | 3 | 0.693 | 0.250 | 2.77× |
| r3, SHIPPED | 15 | 0.685 | 0.250 | 2.74× |
| r3, run rule + MIN | 10 | 0.683 | 0.182 | 3.75× |

**When severity is non-zero, the shipped engine already steers hard toward need —
2.77× over the window's base rate.** So the plan's "reaching today is ~entirely
random" (§1, §3(b)), which I adopted verbatim at C-2, is **overstated, and I
withdraw that adoption.** The additive `bonus` term is not weak; what is inert is
*severity itself*, which is 0 for most (team, position) pairs in August. When
severity is 0 there is no direction to have — the reach is random because there is
nothing to aim at.

That reframes what D-5 needs. The operator's *"reaching should more so be to fill
a position of need than just random"* is a statement about the **composition of
the reach population**: of all the deviations from BPA on a board, most should be
need-fills. `effective_bpa_prob` delivers exactly that — needy teams keep reaching
at 90 %, satisfied teams drop to 30 %, so the reaches that remain are
predominantly need-driven. **Per-pick direction is unchanged, and does not need to
change, because it is already 2.77×.**

**O-3 — so D-5 is delivered, but only with O-1's fix.** Under `max()` the
composition shift never happens (every realistic roster sits at 1.0), which is why
I-6's verdict is right even though its direction premise is not. Both go in:
the denominator-weighted aggregate, **and** an explicit paragraph in `prd.md` and
in the operator items stating that per-pick direction is unchanged at 2.77× and
that D-5 is answered by re-weighting *who* reaches. The operator confirms that
reading. Per the review's own wording, "(b) is acceptable; silence is not" — this
is (b), with a measurement attached.

### P. Resolution of I-5, I-8, and the remaining objections

**I-5 — ACCEPTED, and it costs a `database.py` edit.** Verified by reading:
`create_mock_draft` abandons only rows with `status == "active"`
(`database.py:10739`), and the complete-fallback is `ORDER BY id DESC LIMIT 1`
(`:10774-10781`), so completed rows accumulate forever and dismissing #N surfaces
#N-1. **Fix chosen:** on dismissal of a **complete** row, abandon *every* complete
row for that (user, league) in one `UPDATE`, via a new
`database.abandon_completed_mock_drafts(user_id, league_id)`. Rejected: a client
loop (N round trips, racy) and a "dismissed" status concept (a schema change to
solve a query problem). This destroys nothing observable — older complete rows are
**unreachable from any UI**, since every read path goes through
`load_current_mock_draft`, which only ever returns the newest. Consequences:
**G2 retains its `database.py:10714-10805` region claim** (Round 1's release of it
is withdrawn), and `docs/api-reference.md` moves from "n/a" to **"updated"** — one
clarifying sentence on `/abandon` semantics. Request/response shape and status
codes are unchanged. T-292-01 now seeds **two** completed mocks and asserts the
surface reaches `no_active_mock` after **one** dismissal.

**I-8 — ACCEPTED, and ESCALATED from doc-only to a named build precondition.**
The Planner is right and it is worse than a wording fix. Verified:
`backend/tests/fixtures/profiles/standard.json` declares exactly **one** league
(`990000000000000001`); d1 and d2 target `1312076055586050048` and
`1312140920132497408`, which appear in **no** profile; and `git grep` finds d1/d2
referenced only by docs and their own YAML — **no suite file or runner**. So the
"standard + corpus merged into the fixture dir" precondition is unimplemented and
d1/d2's green status is unverified. My B-4 "zero seeder work" is **wrong** and is
withdrawn. Correct claim: *zero new engine or route work — the mock is creatable
through the shipped UI against the ffv3 cassette — but the flow is blocked on the
pre-existing corpus-merge gap that d1/d2 already depend on.* Sized in `scope.md`
as two options (add ffv3 to a profile's `leagues[]`, or implement the merge step),
and named as a precondition of the Tier-1 sim gate rather than an assumption. Also
recorded for the flow author: ffv3's **top-level `rounds` is `null`** — the 4
lives in `settings.rounds`.

**I-7 — accepted.** 46.1 ranks 5th of the first eight gaps (27.1, 27.5, 28.8 are
tighter). The superlative goes; the conclusion — Tate, Tyson and Lemon share a run
— is independently confirmed by H-3 and does not depend on it.

**I-9 — accepted, and it survives O-1.** Because `_lakeview_corpus` prices rosters
with rookie-only Elo, every viable count is 0, so every owner sits at severity 1.0
under `max` **and** under the denominator-weighted aggregate. The need-conditional
half stays invisible to the calibration harness either way. Recorded where D-10 is
recorded, so no one reads a green regression bar as validation of R-7/R-8.

**I-10 — accepted.** One line in `scope.md` under the operator items: measured at
round-2 depth on 1qb_ppr, `run_offset = 1`, so the effective round-2 cap is often
**1** against the operator's stated 5. Contract-legal (`min()` only tightens) but
the operator ruled that table verbatim and should know.

**I-11 — accepted, and improved.** Rather than the suggested inverted run at
`m = 2.0`, adding an **upper** bound to T-290-11 makes it failing-first for free:
shipped is 171, so any upper bound below that fails on unfixed code. This resolves
I-11 and I-3 part 3 with one edit.

**I-12 — accepted.** T-290-03 now specifies the **one-pass** partition explicitly
(walk the full pool once, cut at every boundary, measure the resulting block
sizes) rather than the sequential `run_offset` re-scan, which gives 4.0/3.0 and
would fail its own bar on sf_tep.

**I-13 — accepted.** Every distributional test pins `seeds = range(N)` explicitly.

**Sixth stale doc — accepted.** `backend/feature_flags.py:462` joins the five in
`scope.md` §2.2.

### Q. Two-sidedness re-audit of every distributional test

The Planner's instruction was to re-audit the whole set, not just the two named.
Done — every test that asserts on a *distribution* now has bounds on both sides,
and the ones that do not are property assertions where one-sidedness is correct.

| Test | Round 1 | Round 3 | Why |
|---|---|---|---|
| T-290-03 median run | `4 <= med <= 5` | unchanged, + one-pass pinned, + **both formats named** | already two-sided |
| T-290-09 zero-need reach rate | `[0.18, 0.27]` | unchanged | already two-sided |
| T-290-10 cl.1 `P(#1@1.01)` | `>= 0.43` | **`0.43 <= p <= 0.75`**, per format | I-3: 1.000 passed a floor-only bar |
| T-290-10 cl.1b `P(#1>3)` | `<= 0.05` | **`0.02 <= p <= 0.11`**, per format | 0.000 (collapse) now fails the lower bound |
| T-290-10 cl.2 `P(Tate>4)` | `== 0` | **`<= 0.10`**, both formats | `== 0` is false at MIN ≥ 1 (measured 0.073) |
| T-290-10 cl.3 `P(#7≤4)` | `<= 0.02` | unchanged, **both formats** | F-2 upheld; identical on both formats (0.0000) |
| T-290-11 distinct orderings | `>= 12` | **`25 <= n <= 120` at a PINNED `N = 1500`**, per format | I-3 part 3 + I-11: upper bound fails on shipped (171), lower bound fails on the MIN=0 collapse (18/24). **This statistic scales with N**, so the spec's old "N >= 500" made it unimplementable — N is now pinned exactly, and T-290-14 (structural) is the real collapse guard; these bounds are a smoke alarm |
| T-290-06 `effective_cap <= round_cap` | one-sided | unchanged, + `>= min(round_cap, MIN)` | a property, not a distribution — but the floor gets its own side |
| **NEW T-290-14** | — | **`min(round_reach_cap(1), max(run_offset(pool[:24]), MIN)) >= 1` on both formats** | I-3 part 2: deterministic, seedless, fails at the cause |
| **NEW T-290-15** | — | `MOCK_RUN_MIN_OFFSET < round_reach_cap(1)` | pins the MIN = 3 no-op boundary |

T-290-10 and T-290-11 are now specified **per format with per-format expected
values** (I-4), and T-290-14 is the primary guard — the distributional bounds are
explicitly labelled smoke alarms, set generously rather than fitted to the chosen
configuration.

### R. Answer to the orchestrator's question

**Is the package implementable blind? YES — at `MOCK_RUN_MIN_OFFSET = 1`, with one
operator ruling outstanding that a build agent does not need to wait for.**

Every judgment call is now resolved in the documents: the partition parameters,
the floor, the aggregation, the composition, the two client fixes, the D-16 sites,
the database sweep, and per-format test expectations. The outstanding ruling — is
the floor 1 or 2? — changes **one constant and three test expectation rows**, all
of which are tabulated in N-1, so it can be applied after the fact in minutes. A
build agent should proceed on MIN = 1 unless the operator overrides.

**What I could not resolve and hand up rather than tune:** the choice itself. N-1
is a genuine product tradeoff between tier discipline and board variety, both
defensible, and the reported defect (`P(#7 ≤ 4)`) is fixed at every setting. It
belongs to the operator.

### S. Where the Planner improved on my Round 1

1. **I-1 + I-3 together** — a defect that would have shipped a deterministic 1.01
   to every superflex and TE-premium league, behind two tests that pass on it. My
   reporting of a two-format statistic beside one-format statistics is what
   concealed it, and the criticism of that presentation is exactly right.
2. **I-2** — the cliff is at 2.41, not 2.0. I attributed the collapse to the wrong
   value and called a lucky parameter a tuned one.
3. **I-5** — B-3's premise was right and its consequence was wrong. Complete rows
   accumulate; the dead-end is paginated, not fixed, for precisely the #292
   population. My test would have passed anyway. Same pattern as I-3, twice.
4. **I-6's aggregation half** — `max()` with TE's denominator of 1 makes the whole
   need-conditional change a no-op on ordinary rosters. I would have shipped a
   scalar that never moves.
5. **I-8** — "zero seeder work" was wrong; the corpus-merge precondition is
   unimplemented and d1/d2 have never demonstrably run.
6. **I-12** — two readings of "median run size", one of which fails its own bar.
7. **I-9 and I-10** — two honest caveats I had not noticed at all.
