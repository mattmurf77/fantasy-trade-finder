# Feature Scope — bake-off outlook lane fills zero slots (D-086)

**Date:** 2026-08-19
**Entry point:** direct ask — "the bake-off's outlook lane fills zero slots, every run"
**Builder:** agent session `fix/bakeoff-outlook-lane`, branched from `origin/main` @ `a130dfc`
**Operator sign-off on waivers:** not needed (no waivers — §1 answered (b), §3 answered with unit tests + code-walk)

---

## 0. Diagnosis — which of the three hypotheses was true

Read-only prod (`DATABASE_URL_PROD`, `SET TRANSACTION READ ONLY`), all 18
`bakeoff_runs` rows written on 2026-08-19, 54 group-runs, 527 pooled cards.

| Group | cards/run | `value` | `window` | `(none)` | window share | outlook slots filled |
|---|---:|---:|---:|---:|---:|---:|
| `current_divergence` | 1.3 | 23 | **0** | 0 | **0.0%** | 0 / 90 |
| `current_consensus` | 22.5 | 291 | 114 | 0 | 28.1% | 63 / 90 |
| `gen_v2` | 5.5 | 83 | 16 | 0 | 16.2% | 16 / 90 |
| **all** | 29.3 | 397 | **130** | **0** | **24.7%** | 79 / 270 |

**Hypothesis 2 (plumbing) is FALSE, and provably so.** The `(none)` bucket is
empty in **all 54** group-runs: every single pooled card carried a `lane`, so
`classify_lane` ran on every card of every arm and returned a label every time.
`window` is 24.7% of live supply — not ~0%. (The one plumbing instance of this
class, gen-v2 cards carrying no `lane` at all, was already found and fixed
before this work began; `backend/bakeoff_runner.py:1153` is that fix, and the
`gen_v2` row above — 16 window cards — is it working.)

**Hypothesis 1 (supply) is TRUE, but only for one group.** `current_divergence`
averages **1.3 cards of any lane** against a 10-card group size. Its outlook
quota is not merely unfilled, its *group* is empty: 161 of its 180 slots went
short, 90 of them outlook. 0/23 window there is a real and interesting finding
(the same user, same window, same week, got 16.2% window out of arm `gen_v2`,
which is also divergence-basis) — but n=23 is too small to call it a defect,
and it is now recorded rather than guessed at. Logged as an open question.

**Hypothesis 3 (quota) is TRUE at the deck level, and is the fixable one.** A
5/5 split asks every group for **50% outlook** against a supply that is
**24.7% outlook**. That is unfillable by arithmetic. But the damage was not the
empty outlook slots — it was that **the value lane was simultaneously capped at
5 and could not use them**:

| | cards/run |
|---|---:|
| target (`bakeoff_deck_limit`) | 30.0 |
| total supply generated | 29.3 |
| within-group capacity — `Σ min(pool, 10)`, i.e. the ceiling the *group partition* allows | 16.0 |
| **actually served** | **13.8** |

The last two lines are this defect: **40 of 288 fillable slots (14%) were
destroyed by the lane split alone.** The 10:33 pair is the clearest case —
group 2 held ten value cards for ten slots and served five.

The 16.0 → 30.0 gap is a *different* defect: the group partition strands
surplus. In the 06:39 run, `current_consensus` held 37 cards while the other
two groups held zero, and the operator received a 10-card deck. That is the
arm-C forfeit / cross-group problem, owned by a concurrent session; it is not
touched here.

**Fix chosen: lane reallocation, not a re-tuned split.** Replaying the 54 real
group pools through candidate quotas:

| `bakeoff_group_value_slots` | fixed quota | with reallocation |
|---|---:|---:|
| 5 (today) | 13.8 /run | 16.0 /run |
| 6 | 14.9 | 16.0 |
| 7 | 15.6 | 16.0 |
| 8 | 15.7 | 16.0 |
| 10 | 15.0 | 16.0 |

A re-tuned split (7/3 is the closest match to 24.7% supply) recovers 15.6 and
needs re-tuning whenever supply drifts. Reallocation reaches **16.0 at every
split**, keeps the 5/5 ask and its `short` column intact, and needs no magic
number. So the quota does not move.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new events. The measurement surface
  is `bakeoff_runs.groups_json` (already written every run, in dark mode too)
  and `deck_impressions.lane_slot` / `.group_key` (already stamped). One new
  **key** is added inside the existing `groups_json` blob — `realloc` — so the
  spill is read, not inferred from `filled` minus `quota`.
- No client emits anything new; nothing user-facing is instrumented.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `bakeoff_runs.groups_json` gains a
  `realloc` key inside its existing JSON payload → `docs/data-dictionary.md`
  updated (`groups_json` row + `deck_impressions.lane_slot` row).
- **New/changed feature flags:** none. `trade.bakeoff` still gates everything
  and stays as it is; `bakeoff_serve_interleaved` **is not touched** — it stays
  0.0 (dark), and re-lighting it is the operator's call.
- **New `model_config` keys:** `bakeoff_lane_reallocate`, default **1.0 (on)**
  → `docs/config-reference.md`. **Ship-the-knob:** setting it to `0` restores
  the pre-D-086 composition byte-for-byte with no deploy, asserted end-to-end
  by `test_lane_reallocation_is_wired_to_its_knob_end_to_end`.
  Graduation criterion: none needed — it is a revert lever, not a rollout.

## 3. Evidence scope

- [x] **Unit tests** — `backend/tests/test_bakeoff_composition.py`, 7 added /
  3 rewritten:
  - `test_lane_reallocation_fills_the_group_without_softening_the_shortfall` —
    the core claim: the group reaches 10, and `short` still reads
    `{"outlook": 3}`.
  - `test_lane_reallocation_is_a_no_op_when_both_lanes_meet_their_quota` — the
    rich case is unchanged.
  - `test_lane_reallocation_runs_in_both_directions` — a *value* shortfall
    reallocates to outlook; the rule is "slots follow supply".
  - `test_lane_reallocation_cannot_invent_supply` — a genuinely card-poor group
    still serves short.
  - `test_reallocation_leaves_backfill_only_the_unlabelled_remainder` — the two
    policies compose without double-counting.
  - `test_lane_reallocation_is_wired_to_its_knob_end_to_end` — the revert lever
    reaches `compose_group` through `compose_deck`.
  - `test_measured_prod_shape_reaches_the_group_size` — regression pinned to the
    **actual measured 10:33 pools** (7/0, 10/0, 13/3): 18 cards before, 27 after.
  - Rewritten to assert the pre-D-086 behaviour explicitly under
    `reallocate=False`: `test_outlook_shortfall_is_recorded_and_not_backfilled`,
    `test_backfill_policy_fills_residual_slots_and_flags_every_substitute`,
    `test_run_row_records_the_per_group_under_fill`.
- [x] **Code-walk proof** — see §6.
- [x] **Structural guard:** n/a — backend-only, no mobile surface.
- [x] **Manual TestFlight checklist:** n/a — the bake-off is dark
  (`bakeoff_serve_interleaved` 0.0), so no served deck changes for any user.
  What changes is the composition recorded in `bakeoff_runs`, verifiable from
  the operator's own admin read of `groups_json` after the next organic deck:
  `filled.value + filled.outlook` should equal `min(pool total, 10)` per group,
  and `short` should be unchanged in character from today's rows.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed or contract-changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant *convention* shifted — one new `model_config` key inside an existing family, one new key inside an existing JSON blob |
| `docs/architecture.md` | n/a | module wiring unchanged; `bakeoff_runner.compose_group` keeps its callers and its signature shape |
| `living-memory/HLD.md` | n/a | no new module, client or major flow |
| `docs/cross-client-invariants.md` | n/a | `lane` / `basis` enum strings are unchanged; no client reads `realloc` |
| `docs/glossary.md` | **updated** | **Under-fill (bake-off)** rewritten with measured numbers; new **Lane reallocation (bake-off)** entry |
| `docs/config-reference.md` | **updated** | `bakeoff_lane_reallocate` row added, `bakeoff_fill_policy` row rewritten to say what it now governs, measured-supply paragraph added under the `trade.lanes` note |
| `docs/data-dictionary.md` | **updated** | `bakeoff_runs.groups_json` (adds `realloc`, corrects the ~19% claim), `deck_impressions.lane_slot` (reallocation never produces `fill`) |
| `DECISIONS.md` entry | **updated** | **D-086** |
| `docs/plans/three-model-bakeoff/scope-composition.md` | **updated** | amendment note recording that D-086 refines D-078 |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated** | knob-inventory exclusion row for the composition-knob family (required by `test_no_generation_knob_was_added_without_an_arm_a_decision`) |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` → **3448 passed, 1 skipped**
  (baseline on `a130dfc`: 3441 passed, 1 skipped; +7 = the 7 tests added).
  `tsc --noEmit` and `testid-lint` are unaffected — no file under `mobile/` is
  touched.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** n/a (no checklist written — see §3).
- **Express lane declared by the operator?** No. Full gates.

## 6. Code-walk proof

The claim to prove: *after this change a group serves `min(pool, size)` cards
whenever one lane's shortfall is covered by the other lane's own surplus, and
the recorded under-fill is bit-identical to what it was before.*

1. **The lane label is computed for every card of every arm.**
   `backend/trade_service.py:4271-4276` stamps `c.lane = classify_lane(...)`
   inside the per-opponent loop of `_generate_trades_impl`, so it covers both
   the v3/divergence branch (`:4123`) and the consensus branch (`:4186`,
   `:4188`) — arm `current` in full. `backend/bakeoff_runner.py:1150-1156`
   does the same for arm `gen_v2`. `classify_lane`
   (`backend/trade_service.py:2184-2206`) returns `None` **only** when the
   user's outlook is absent or `not_sure`; otherwise it returns `"window"` or
   `"value"`. Prod confirms the code-walk: `(none)` is 0 in all 54 group-runs.

2. **Bucketing is unchanged.** `compose_group` filters to the group's basis and
   buckets by `lane_of` (`backend/bakeoff_runner.py:504-510`, `:588-592`).
   `res.pool` still counts raw supply.

3. **`short` is computed before reallocation and cannot be softened.**
   `backend/bakeoff_runner.py:613-617`: `take_v`/`take_o` are the nominal
   `value_slots` / `outlook_slots` slices, and `res.short` is
   `nominal − len(take)` per lane, assigned before any reallocation statement
   runs. Nothing later in the function writes `res.short`. This is what makes
   the D-078 finding survive: `test_lane_reallocation_is_wired_to_its_knob_end_to_end`
   asserts `on[G1]["short"] == off[G1]["short"]`.

4. **Reallocation draws only from the receiving lane's own bucket.**
   `backend/bakeoff_runner.py:619-631`: `extra_v` is sliced from
   `buckets[LANE_VALUE]`, `extra_o` from `buckets[LANE_OUTLOOK]` — never the
   other lane, never `LANE_NONE`. Therefore every card in `take_v` has
   `lane == "value"` and every card in `take_o` has `lane == "window"`, and the
   slot stamps at `:650-651` (`SLOT_VALUE` for `take_v`, `SLOT_OUTLOOK` for
   `take_o`) remain true statements about each card. That is the property
   `test_lane_reallocation_fills_the_group_without_softening_the_shortfall`
   asserts card-by-card, and it is the whole distinction from
   `bakeoff_fill_policy` = 1, where a `value` card is deliberately placed in an
   outlook slot and flagged `SLOT_FILL` (`:652`) so analysis discounts it.

5. **Reallocation cannot exceed the group size or the group's supply.**
   `spare = max(0, size - len(take_v) - len(take_o))` (`:624`), and the two
   slices are bounded by `spare` and by `spare - len(extra_v)` (`:626-628`), so
   `len(take_v) + len(take_o) <= size`. Both slices are of the *tails* of
   buckets already sliced at the nominal quota, so they cannot re-take a card
   already taken and cannot exceed the bucket. Hence
   `served = min(pool_lane_total, size)` exactly when the surplus lane has
   enough tail — `test_lane_reallocation_cannot_invent_supply` pins the
   opposite case.

6. **Priority between the two extensions is provably irrelevant.** `spare > 0`
   requires `len(take_v) < value_slots` or `len(take_o) < outlook_slots`, and a
   short slice means that bucket was **exhausted** — so at most one lane can
   have a tail, and the order of the `extra_v` / `extra_o` statements cannot
   change the outcome. (`test_lane_reallocation_runs_in_both_directions` covers
   the outlook-wins direction.)

7. **The backfill path is set-identical when reallocation is off.** Old:
   `buckets[VALUE][value_slots:] + buckets[OUTLOOK][outlook_slots:] +
   buckets[NONE]`, re-sorted by index within `pool`. New (`:635-638`): every
   card of `pool` not in `take_v ∪ take_o`, in `pool` order. With
   `reallocate=False` the taken set is exactly the two nominal slices, so the
   two expressions produce the same cards in the same order — `pool` order *is*
   the rank order the old code sorted back to. `residual` is likewise equal:
   `size − len(take_v) − len(take_o)` collapses to
   `short["value"] + short["outlook"]` when `value_slots + outlook_slots == size`.
   `test_backfill_policy_fills_residual_slots_and_flags_every_substitute`
   (now pinned at `reallocate=False`) is unchanged and still passes.

8. **Ordering and interleaving are untouched.** The lane-alternating loop
   (`:641-648`) already handles unequal list lengths by appending the longer
   list's tail, so a 8/2 realized split alternates for the first two pairs and
   then runs out the value tail. `group_draft` reads `res.cards` and
   `res.slots` exactly as before.
