# HLD delta — G2: mock draft engine, lifecycle, interactivity (#290 / #291 / #292 / D-16)

> **Delta against [`docs/architecture.md`](../../../architecture.md) — not a rewrite.**
> Only the rows and claims listed here change. Everything else in the mock-draft
> architecture (module boundaries, injection discipline, zero-egress property,
> INV-10 determinism, the one-consensus amendment) is unchanged and is
> deliberately re-affirmed below.
>
> Author: G2 author agent, Phase 1, 2026-08-10.
> Worktree `.claude/worktrees/fb-289-294`, branch `feedback-289-294`, base `origin/main` @ `7cea1fa`.
> Inputs: [`plan.md`](./plan.md) · [`batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md) (D-5…D-16) ·
> [`prd.md`](./prd.md) · [`lld-delta.md`](./lld-delta.md) · [`scope.md`](./scope.md) ·
> [`reconciliation-log.md`](./reconciliation-log.md)

---

## Table of Contents

- [1. What changes, in one paragraph](#1-what-changes-in-one-paragraph)
- [2. The measured picture this delta is built on](#2-the-measured-picture-this-delta-is-built-on)
- [3. New engine notion: the run](#3-new-engine-notion-the-run)
- [4. Where the run sits relative to the reach policy](#4-where-the-run-sits-relative-to-the-reach-policy)
- [5. Need-conditional reaching](#5-need-conditional-reaching)
- [6. Components touched](#6-components-touched)
- [7. Data flow](#7-data-flow)
- [8. Lifecycle architecture (#292) — the correction](#8-lifecycle-architecture-292--the-correction)
- [9. Identity sourcing (D-16)](#9-identity-sourcing-d-16)
- [10. Decisions taken, alternatives rejected](#10-decisions-taken-alternatives-rejected)
- [11. Properties preserved (no-regression contract)](#11-properties-preserved-no-regression-contract)
- [12. `docs/architecture.md` rows to amend](#12-docsarchitecturemd-rows-to-amend)

---

## 1. What changes, in one paragraph

The mock-draft CPU model gains **one new internal concept and two new inputs to an
existing decision** — nothing else moves. The concept is the **run**: a
gap-derived cluster of adjacent players in the already-ordered consensus pool,
computed by a single forward walk inside `backend/mock_draft_service.py` and
never leaving that module. Its output composes with the shipped round-tiered
reach cap through `min()`, so it can only *tighten* the operator's W2e policy,
never loosen it. The second input is **positional need**, which now conditions
the *probability* of taking the idiosyncrasy branch rather than only the size of
the need bonus. On the client side there is **no architectural change at all**:
#291 is a render-condition change in one shared row component, and #292 is
client lifecycle work over a route contract that — contrary to the plan — already
supports everything it needs.

---

## 2. The measured picture this delta is built on

Every number below was produced in this worktree against the pinned consensus
board the calibration harness builds (`_rookie_ctx` →
`rookie_universe_2026.json` × `ktc_blend_pipeline_2026-07-17.json` through the
shipped `_apply_consensus_blend` + `seed_elo_for_value`), driving the **shipped**
`mds.build_settings` / `new_state` / `advance_cpu`. Method is reproduced in
[`prd.md` §4](./prd.md#4-the-tate-case).

**Finding A — Carnell Tate is consensus #2, not #7.** On both scoring formats:

| Rank | 1qb_ppr | value | Δ to next | | Rank | sf_tep | value |
|---|---|---|---|---|---|---|---|
| 1 | Jeremiyah Love (RB) | 1886.9 | 69.5 | | 1 | Jeremiyah Love | 1859.0 |
| **2** | **Carnell Tate (WR)** | **1817.5** | 46.1 | | **2** | **Carnell Tate** | **1776.5** |
| 3 | Jordyn Tyson (WR) | 1771.3 | 25.0 | | 3 | Jordyn Tyson | 1722.5 |
| 4 | Makai Lemon (WR) | 1746.4 | **79.2** | | 4 | Fernando Mendoza | 1719.1 |
| 5 | Jadarian Price (RB) | 1667.2 | 27.1 | | 5 | Makai Lemon | 1701.8 |

**Tate going 4th overall is a two-slot fall, not a reach.** The plan's blocking
Spike A is therefore closed, and its "strong expectation" that #290 is purely a
model-form defect is **half wrong** — see §10 D-4 and [`prd.md` §4](./prd.md#4-the-tate-case).

**Finding B — the shipped engine randomises the top of the board.** 12-team
linear, 1qb_ppr, N = 2000 seeded round-1 replays through the shipped `advance_cpu`:

| Statistic | Shipped |
|---|---|
| P(consensus #1 Love goes 1.01) | **45.1 %** |
| P(Love falls past pick 3) | 15.8 % |
| P(Tate taken in picks 2–4) | 58.2 % · **P(Tate falls past 4) = 16.5 %** |
| Who goes 4th overall | Lemon 17.7 % · Tyson 16.0 % · **Love 15.8 %** · Price 15.3 % · Concepcion ~13 % · Sadiq ~11 % · Tate 10.1 % |
| Distinct top-4 orderings over 2000 seeds | 173 |

A near-flat distribution across the top seven, with the consensus **#1** landing
4th more often than the player the operator complained about. That is the defect,
and it is exactly the class of failure the plan diagnosed (`rank`-only scoring,
`row["value"]` never read at `mock_draft_service.py:646-651`) — just localised to
a different player than the report named.

**Finding C — the run rule fixes B without collapsing the board, at m = 2.5.**
Same harness, same seeds, prototype run rule composed at the `reach_cap` seam:

| | Shipped | m = 2.0, W = 9 | **m = 2.5, W = 9** |
|---|---|---|---|
| P(Love goes 1.01) | 45.1 % | **100 %** (forced) | **45.1 %** (unchanged) |
| P(Love falls past 3) | 15.8 % | 0 % | **2.4 %** |
| P(Tate taken 2–4) | 58.2 % | 100 % | **74.7 %** |
| P(Tate falls past 4) | 16.5 % | 0 % | **0 %** |
| Distinct top-4 orderings | 173 | **5** | **18** |
| Median run size, 1qb_ppr / sf_tep | — | 3.5 / 4.0 | **5.0 / 5.0** |

`m = 2.0` is the "chalky and lifeless" collapse D-6 warns about, arriving in
round 1: five distinct openings across two thousand drafts. `m = 2.5` keeps 1.01
exactly as varied as today while eliminating the top-of-board fall, and — with
**no size clamp**, per D-9 — produces a **median run of 5 players on both
formats**, which is the operator's "tight groups of 4-5" as an emergent property
of the value curve rather than an imposed one. That coincidence is the parameter's
justification; it is not a taste call.

---

## 3. New engine notion: the run

**Definition.** A *run* is a maximal block of adjacent rows in the consensus pool
between two **locally significant** value drops. A drop between rows `i` and
`i+1` is locally significant when it is at least `MOCK_RUN_GAP_MULTIPLE` times
the **median** of the gaps in a `MOCK_RUN_MEDIAN_WINDOW`-wide window around it.
Exact algorithm, boundary conditions and tie handling: [`lld-delta.md` §2](./lld-delta.md#2-run-detection).

**Four properties that make it an *engine* notion and not a tier.**

1. **It is adaptive, not absolute** (D-9). The threshold is a dimensionless
   multiple of a local median, so it survives the value curve flattening in the
   tail — the documented property behind W2c's split failure
   (`mock_draft_service.py:231`, *"a rank distance over a value curve that
   flattens in the tail"*). An absolute Elo gap `G` would cut the top of the
   board into singletons and the tail into one 50-long block.
2. **It has no size clamp** (D-9). "Tight groups of 4-5" is a target the gap rule
   is *checked against*, not a rule it enforces. On the measured board the deep
   tail is genuinely one 53-long flat block; a clamp would manufacture four
   boundaries inside it where the values state none. Harmless in practice: the
   deepest round cap is 15, so a run longer than 15 is indistinguishable from no
   run at all.
3. **It is computed by a single forward walk**, modelled on `_block_rank`
   (`mock_draft_service.py:1127-1148`), which already walks neighbours in the
   sorted run to average tied blocks. This satisfies amendment 1's AST
   prohibition on `sorted` / `.sort` anywhere in the module
   (`test_mock_draft.py:708`) **without a waiver**. Confirmed by running the
   suite against a prototype (§11).
4. **It never leaves the module.** It is not a payload field, not persisted in
   `mock_drafts.settings`, not a cross-client enum, and not a `model_config`
   key. Nothing outside `backend/mock_draft_service.py` can observe a run except
   through the picks the bots make.

**Why not the 8-tier ladder.** Endorsed from the plan §4.3.1, verified: `first_1`
spans Elo 1580–1785 and `second` spans 1400–1575
(`docs/cross-client-invariants.md` § Tier band Elo cutoffs), which on the
measured 89-row rookie pool puts the entire top-11 into at most two bands — not
"groups of 4-5". The tier keys are also a cross-client enum shipped verbatim on
four routes, and #279 already refused to widen that enum for an adjacent purpose
(`docs/feedback/items/279-aggregate-tier-labels/status.md`). A run is a fourth
engine-internal lookalike alongside `web/css`'s 4-level set, `tier_depth` and
`tier_mult_*`, and gets a line in the quarantine paragraph at
`docs/cross-client-invariants.md` (§ Tier colors, closing note).

---

## 4. Where the run sits relative to the reach policy

The run is expressed as **one tighter truncation at the existing seam**, not as a
new stage.

```
                       ┌──────────────── advance_cpu / simulate_reaches ─────────────────┐
 consensus_pool ──►  _available ──► head = available[:candidate_window]
                                       │
                       W2e product cap │  cap = round_reach_cap(round)          ◄── unchanged
                       W2e budget      │        if spent < round_reach_budget(round) else 0
                                       │
                       NEW             │  if cap > 0:
                                       │      cap = min(cap, run_offset(head, allow_cross))
                                       ▼
                                    cpu_pick(head, …, reach_cap=cap)
                                       │
                                       │  candidates_ranked[:cap+1]     ◄── shipped, :637-638
                                       │  reaching = rng.random() >= effective_bpa_prob(…)   ◄── NEW weight
                                       │  argmin(rank − need_bonus − Gumbel)                 ◄── unchanged
                                       ▼
                                    player_id
```

**`allow_cross` is the D-6 round softening, and it is the only place rounds 1–2
and 3+ differ:**

| Round | `allow_cross` | Effect |
|---|---|---|
| 1, 2 | `0` | **Hard wall.** The bot may not pass the head's run boundary at all. |
| 3+ | `MOCK_RUN_CROSS_ALLOWANCE_LATE = 1` | **Softer.** The bot may cross exactly one boundary — its window is the head's run *plus the next one*, still capped by the round's 15. |

D-6 asked for "a softer penalty in rounds 3+" and left the form open. A
**one-boundary allowance** is chosen over a score penalty for three reasons: it
is expressed in the same units as the thing it softens (candidate-set width, not
score), it keeps `cpu_pick`'s scoring function byte-identical — so the
Gumbel-max identity and `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`
survive conditional on reaching — and it is a single integer parameter that a
test can pin exactly. A score penalty would perturb the noise family per pick,
which is the failure mode W2b closed and the plan correctly rejected for the
magnitude variant (§10 D-6).

**Why `min()` at this seam and nowhere else** (endorsed from plan §4.3.2, verified):

- It can only tighten. `test_w2_21_the_policy_table_is_the_operators_rule_verbatim`
  (`test_mock_draft.py:332`) reads `round_reach_cap` / `round_reach_budget`
  directly and is untouched. The operator's verbatim W2e rule stands.
- `reaches_spent` (`:861-887`) re-derives spend from persisted picks by pool
  position `> 0`; the definition of a reach does not change, so
  `test_w2_21_the_budget_survives_a_resume_from_the_row` (`:402`) holds.
- `reach_cap` is already a per-pick caller-supplied product cap with a documented
  contract (`cpu_pick` docstring, `:620-633`). One seam, one place to get wrong.
- **Both call sites must change together** — `advance_cpu:936` *and* the
  calibration harness's mirror `simulate_reaches:1247`. The module's own comment
  says the simulator "and the product cannot diverge on the policy"; a run rule
  applied in only one of them would silently invalidate the harness.

---

## 5. Need-conditional reaching

Today `reaching = scale > 0.0 and rng.random() >= bpa_prob`
(`mock_draft_service.py:643`) — **one unconditional Bernoulli**, drawn before and
independently of any need. The change makes the mixture weight a function of the
team's worst positional hole:

```
bpa_effective = 1 − (1 − bpa_prob) × ( floor + (1 − floor) × max_severity )
```

with `floor = MOCK_IDIOSYNCRASY_FLOOR = 0.25` and
`max_severity = max(needs_for_team.values())`.

| Team state | `max_severity` | P(reach) today | P(reach) after |
|---|---|---|---|
| Desperate hole | 1.0 | 90 % | **90 %** (unchanged) |
| Half-filled | 0.5 | 90 % | 56 % |
| Nothing needed | 0.0 | 90 % | **22.5 %** |

This is **D-5 exactly**: need dominates, idiosyncrasy survives. A satisfied roster
still reaches roughly once in four-and-a-half picks, so the board keeps texture
even in August when `severity == 0` for most (team, position) pairs
(`VIABLE_ELO_FLOOR = 1280`, `:194`).

**Architecturally this is the smallest possible perturbation.** It changes one
scalar, consumes the **same single** `rng.random()` call in the same stream
position, and does not touch the noise family — so the geometric reach law, the
Gumbel-max identity and the persona-independence of the idiosyncrasy branch are
all preserved *conditional on reaching*. The alternative the plan rejected
(scaling the Gumbel `scale` by severity) would reparameterise the noise per pick
and re-open W2b; that rejection is endorsed.

**One shipped test measures the branch at zero need and therefore moves.** See
§11 and [`prd.md` R-14](./prd.md#3-requirements).

---

## 6. Components touched

| Component | Change | Item |
|---|---|---|
| `backend/mock_draft_service.py` | New `run_offset()` + `effective_bpa_prob()`; `cpu_pick` reads the new mixture weight; `advance_cpu` and `simulate_reaches` compose the cap | #290 |
| `backend/server.py` (`/api/mock-draft` region, G2-owned) | `usernames` sourcing in `_mock_league_context` **and** `_mock_context_from_row` | D-16 |
| `mobile/src/screens/DraftRoomScreen.tsx` (`UndraftedRowView`) | Trailing-slot render condition; tier label relocated to the meta line while on the clock | #291 |
| `mobile/src/screens/DraftRoomScreen.tsx` (mock entry wiring) | Complete-state button priority; `postRefusal` clearing; `retry` wiring | #292 |
| `mobile/src/screens/MockDraftScreen.tsx` | `actionLabel` gating; section-header copy; on-the-clock hint; header action in the complete state | #291, #292 |
| `mobile/src/components/draft/MockEntryPanel.tsx` | `retry` control in the `errorText` branch | #292 |
| `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` | New — the repo's first mock flow | all |
| `backend/tests/test_mock_draft.py` | Additions; one helper corrected | all |

**Not touched, and named so:** `backend/draft_board_service.py` and
`backend/mfl_service.py` (G1), `mobile/src/screens/LeagueSummaryScreen.tsx` (G3),
`backend/database.py` (see §8 — the plan expected a change here; none is needed),
`backend/tier_config.json`, `config/features.json` and
`docs/cross-client-invariants.md` (orchestrator-owned; text proposed in
[`scope.md`](./scope.md)).

**The seam the run must NOT take.** The run scan naturally wants to live beside
`_undrafted` in `draft_board_service.py`. It must not: that file is G1's, and a
run computed there would become board-payload surface — a new field on a shipped
contract that the Draft Room, the extension and the web client would all inherit.
Keep it entirely inside `mock_draft_service.py`, consuming the rows `_undrafted`
already returns. (Endorsed verbatim from plan §7.)

---

## 7. Data flow

Unchanged in every respect except the two new pure functions. Restated so the
delta is auditable:

```
server._get_universal_pool(fmt) ──► consensus_elo (the ONE consensus, amendment 1)
        │
        ├─ create:  _mock_league_context ─► MockContext{consensus_elo, player_rows,
        │                                   rosters, lineup_slots, usernames*}
        └─ resume:  _mock_context_from_row ─► same shape, from settings + session

MockContext ─► consensus_pool = dbs._undrafted(basis="consensus")   [value-descending]
            ─► _available (minus this mock's picks) ─► head[:24]
                                                        │
                        run_offset(head) ───────────────┤  NEW, pure, no I/O, no RNG
                        _severities(ctx, state, owner) ─┤  existing
                                                        ▼
                                                     cpu_pick
```

`*` = D-16's correction (§9). No new module dependency, no new import that can
reach a platform (`test_w2_13_the_engine_imports_nothing_that_can_reach_a_platform`,
`test_mock_draft.py:764`, stays green — `statistics` is stdlib and non-I/O).

---

## 8. Lifecycle architecture (#292) — the correction

**The plan proposed a backend change. None is required.** Verified on `7cea1fa`:

`mock_draft_abandon_route` (`backend/server.py:11781-11794`) calls
`update_mock_draft(mock_id, user_id, status=STATUS_ABANDONED)`, whose `WHERE`
clause is **id + user_id only** (`backend/database.py:10786-10805`) — it does not
filter on status. A **completed** mock is therefore already dismissible by the
shipped route, owner-scoped, idempotent.

So the plan's "Option A: extend the abandon route to accept a `complete` row" is
already true, and its Option B (age-bounding the complete fallback in
`load_current_mock_draft`) stays rejected. The architectural consequence is
material:

- **No route contract change.** `docs/api-reference.md` needs no edit for #292.
- **No `backend/database.py` edit**, so G2 drops its region claim on
  `:10714-10805` entirely.
- **The change class for #292 drops from "backend route + mobile" to
  "mobile-only"** — though the group's sim tier stays 1 because #291 changes a
  mobile screen regardless.

What remains is genuinely client-side, and it is a **panel-contract** change, not
an architecture change: `MockEntryPanel` has four mutually exclusive early
returns (`block` → `loading` → `errorText` → card, `:72-96`) and three of them
render zero interactive controls. The fix is an invariant, stated once and
tested: **no reachable state of the Mock card may render zero controls.**

| Dead-end | Today | After |
|---|---|---|
| Completed mock is permanently "current" (`database.py:10774` fallback; abandon control hidden once `status !== 'active'`, `MockDraftScreen.tsx:198-212`) | primary = "View recap" → returns you to the recap you just left; only escape is the ghost "Run it back" (`DraftRoomScreen.tsx:823-830`) | primary = **"Start a new mock"**, secondary = "View recap"; the recap screen gains a header action that abandons the complete row |
| One failed create replaces the panel with a buttonless error view (`MockEntryPanel.tsx:90-96`; no `onError` on `createMock`, `:278-294`) | dead until the screen unmounts | `retry` control in the error branch: `createMock.reset()` + refetch |
| `postRefusal` never clears (`:300`), muting the card for the session | dead for the session | cleared on re-entering Mock mode and on opening the setup sheet |

---

## 9. Identity sourcing (D-16)

`state_payload` resolves owner names through `ctx.usernames`
(`mock_draft_service.py:1013`, `:1014`), which the routes build as
`{str(m.user_id): m.username for m in members}` off the **session league
object** — at `backend/server.py:11437` (`_mock_league_context`) **and again at
`:11474`** (`_mock_context_from_row`). G1's PRD §11 records this site as
`:11438` and as a single occurrence; **both are wrong** — it is `:11437`, and
there are **two** call sites. Fixing only the create path would leave every
*resumed* mock still rendering ids, which is the common case.

Architecturally this is a **sourcing** change, not a new seam: the mock adopts the
identity ladder G1 is establishing (our `players` row → DP crosswalk `by_mfl_id`
→ `Player <mfl_id>`; franchise: member `username` → `display_name` →
`Team <fid>`) by reading the same `league_members` rows through the same
`load_league_members` call the Draft Room's `_mfl_board_binding` already makes.
No new module dependency; `mock_draft_service` still receives names by injection
and never reads the database itself.

**Hazard inherited from G1 (R-7 / T-289-06), and it applies here.** `picks[]`
carries the **raw MFL player id** when the crosswalk missed, and MFL and Sleeper
ids share a numeric range — so a `players` lookup keyed on a raw MFL id can
return **a different, wrong player**. The mock's player half is already safe
(`ctx.player_rows` is keyed on `_rookie_player_ids`, our own id space), and the
delta must keep it that way: **no lookup list may be built from ids that have not
been crosswalked.** Exact contract: [`lld-delta.md` §5](./lld-delta.md#5-d-16--owner-identity-sourcing).

---

## 10. Decisions taken, alternatives rejected

| ID | Decision | Alternatives rejected, and why |
|---|---|---|
| **D-1** | The run lives in `mock_draft_service.py`, computed per pick over the windowed candidate head. | *Beside `_undrafted` in `draft_board_service.py`* — G1's file, and it would become shipped board-payload surface. *Precomputed once per mock and snapshotted into `settings`* — the pool shrinks every pick, so a frozen run table would drift from the board it describes; and it would put a model-internal in a persisted contract. |
| **D-2** | Adaptive local-median threshold, `m = 2.5`, `W = 9`. | *Absolute Elo gap* — settled by D-9; also verified to fail on the flattening tail. *`m = 2.0`* — measured: collapses round 1 to 5 distinct openings and forces 1.01. *`m = 3.0`* — median run 11 on 1qb_ppr; stops being "tight groups". |
| **D-3** | No size clamp on runs. | *Clamp to 4-5* — settled by D-9; and the measured board's tail is one genuinely flat 53-row block, so a clamp invents boundaries. Mooted anyway by the 15-slot round cap. |
| **D-4** | The Tate case is re-specced as a **top-of-board integrity** assertion, not "P(Tate ≤ 4) → 0". | *The plan's secondary assertion* — falsified by measurement: Tate is consensus **#2** and shares a run with Tyson and Lemon, so Tate at pick 4 is legitimate under the very rule the operator asked for. Driving it to zero would be wrong. Full argument and the operator-facing consequence: [`prd.md` §4](./prd.md#4-the-tate-case). |
| **D-5′** | D-6's rounds-3+ softening is a **one-boundary allowance**. | *A score penalty* — perturbs the noise family per pick and breaks the geometric-law test. *A different multiple in late rounds* — a second parameter to fit with no evidence to fit it on. |
| **D-6′** | Need conditions the mixture **weight**. | *Scale the Gumbel `scale` by severity* — reparameterises the noise family per pick; re-opens W2b. *Raise `mock_max_reach_slots`* — makes reaching stronger, never conditional. *Drop the reach branch when severity == 0* — violates D-5's "idiosyncrasy survives". |
| **D-7′** | #292 is **mobile-only**; the abandon route already accepts a complete row. | *A new `/api/mock-draft/reset` route* — the create route already abandons-and-inserts atomically. *Age-bounding the complete fallback in `load_current_mock_draft`* — an invisible time bound turns "where did my recap go" into a new bug class and changes a documented contract to fix a UI problem. |
| **D-8′** | #291 renders the action label unconditionally on the user's turn and **relocates** the #277 tier label to the meta line for those rows. | *Evict the TierBadge* — silently deletes #277's shipped information. *Render both in the trailing slot* — ~40 pt from a `numberOfLines={1}` name column on a 375 pt screen. *A chevron or glyph* — `DraftRoomScreen.tsx:1367-1371` records that a visible glyph is net-new to Chalkline and needs a `components.md` spec first. *Header copy only* — dodges D-7, which names the row. |
| **D-9′** | No new feature flag; recommend shipping on `draft.mock`. | *A second kill switch* — the surface already has one, it is already on, and the revert lever for the engine half is a two-constant edit. Reasoning and the operator ask: [`scope.md` §2](./scope.md#2-schema--flag-scope). |

---

## 11. Properties preserved (no-regression contract)

Verified by running `python3 -m pytest backend/tests/test_mock_draft.py -q`
against a **prototype** of the full engine change in this worktree (then reverted
— no production code is delivered in Phase 1). Result recorded in
[`prd.md` §7](./prd.md#7-test-plan) and [`reconciliation-log.md`](./reconciliation-log.md).

| Property | Mechanism | Status under the prototype |
|---|---|---|
| **INV-10 determinism** | `_pick_rng` stays a pure function of `(rng_seed, pick_no)` (`:820-823`); `run_offset` and `effective_bpa_prob` consume no RNG | holds |
| **Amendment 1 — one consensus** | run scan is a forward walk; zero `sorted`/`.sort` in the module | holds (`test_w2_14`, `:708`) |
| **No platform egress** | `statistics` is stdlib, non-I/O | holds (`test_w2_13`, `:764`) |
| **W2e policy verbatim** | `min()` only tightens; the tables are untouched | holds (`test_w2_21`, `:332`) |
| **Budget semantics + resume identity** | "reach" still means pool position > 0 | holds (`:402`) |
| **Geometric reach law** | noise family untouched; measured at maximal need | holds after the helper correction (§5, R-14) |
| **Calibration tripwire** | `test_w2_16` asserts `all_pass is False` | **did not fire** under the prototype |

**Accepted, and stated once:** a persisted mock created before this change
replays *differently* after it, because truncating the candidate list changes how
many `_gumbel` draws the scoring loop consumes. This breaks no test (`:584`,
`:724`, `:402` all compare two runs of the *same* code) and no invariant — INV-10
promises that one build replays a seed identically, not that two builds agree.

---

## 12. `docs/architecture.md` rows to amend

The `mock_draft_service.py` row (`docs/architecture.md:135`) is the only row that
moves. Four clauses in it are wrong or incomplete after this change — and **two
are already wrong today**, independent of this work:

| Clause in the shipped row | Status | Replacement |
|---|---|---|
| *"One scoring function, `argmin(rank − need_bonus − reach_noise)`, with the persona … as the only per-team parameter"* | needs amending | add: the mixture **weight** is now need-conditional (`effective_bpa_prob`), so a team with nothing it needs drafts near best-available while a desperate team reaches at the fitted rate; the noise family and the persona's role in the need term are unchanged |
| *"Since W2e the reach is bounded by the operator's round-tiered policy"* | needs amending | add: **and, more tightly, by the head's gap-derived *run*** — a locally-significant value drop, hard-walled in rounds 1–2 and crossable once from round 3; composed as `min()` so the operator's policy is never loosened |
| *"The CPU half is currently gated OFF by its own calibration verdict — `CPU_MODEL_VALIDATED = False`"* | **STALE since `6caca35` (2026-08-08)** | the constant is `True` by explicit operator override; the statistical verdict is still FAILED and `test_w2_16` pins it |
| *"`advance_cpu` raise[s] unless a caller explicitly opts in … the routes never do"* | **STALE, same cause** | the routes do reach `advance_cpu`; mocks serve bot picks in production today |

`docs/glossary.md:30` (**Mock draft**) and `:42` (**Calibration gate**) carry the
same stale `CPU_MODEL_VALIDATED = False` claim and need the same correction.
`docs/glossary.md` also gains a new **Run (draft)** term. Exact proposed text for
every orchestrator-owned file: [`scope.md` §4](./scope.md#4-docs-scope-mandatory--hld--lld--api).

**`living-memory/HLD.md`:** no entry. This is a change to a model's internals
inside an existing module — no new module, no new client, no new major flow. The
convention shift (a gap-derived cluster as an engine-internal notion, quarantined
from the tier enum) belongs in `living-memory/LLD.md`, which does get an entry.
