# Feature Scope — Landability challenger (bake-off arm D)

**Date:** 2026-08-19
**Entry point:** direct ask (operator: “I want these changes to be the new Arm A for the bakeoff. Let's treat this overhaul as a new challenger model first”)
**Builder:** unassigned — EM tasks from [PRD.md](PRD.md)
**Operator sign-off on waivers:** needed on §1 (c) for Track A (dark, no new client events) and §3 mobile waiver. Track B if promoted is user-visible and is **not** waived.

Parent: [PRD.md](PRD.md). Historical arm A is **not** this work ([scope-phase2.md](../three-model-bakeoff/scope-phase2.md), D-075).

---

## 0. What this builds

A fourth bake-off arm, `challenger`, that runs the live v1/v3 engine under `MODEL_CHALLENGER_PROFILE`. Generated and logged on every organic bake-off job. **Not served** while `bakeoff_serve_interleaved = 0`. Live `_DEFAULT_CFG` generation behavior is unchanged: new knobs default to the live identity.

What it is not:

- Not a replacement of arm A (`baseline` / `MODEL_A_PROFILE`).
- Not a `trade_gen_v2` change.
- Not a live product-identity change (viewer-first stays on `current`).
- Not shrink-both (no comparison_counts on `member_rankings`).

Ticket split, estimates, and acceptance: [PRD.md](PRD.md) §5–§9.

---

## 1. Analytics scope

- [x] **(b) Existing events cover Track A.** No new client events. The arm rides the bake-off spine that already exists:

  | Question | Field |
  |---|---|
  | which model produced this card | `deck_impressions.model_arm` |
  | rank within the arm | `deck_impressions.arm_rank` |
  | group / basis / lane | `deck_impressions.group_key`, `.lane_slot`; `TradeCard.basis` |
  | what the user did | `deck_outcomes.action` (only once interleaved is lit — out of this scope) |
  | did the arm run, and what did it cost | `bakeoff_runs.arms_json[challenger]` |
  | per-group under-fill | `bakeoff_runs.groups_json[challenger_divergence\|challenger_consensus].short` |
  | what config produced it | `bakeoff_runs.config_json` (snapshot inside `model_challenger()`) |
  | what fairness bar it actually cleared | `deck_impressions.fairness_threshold` (already card-dependent; challenger consensus cards should record `max(requested, 0.75)`) |

- [ ] **(c) WAIVED for Track A client events** — dark generation, no user-visible surface, no new swipe kinds. Track B (likes-you, copy) if promoted uses existing impression/outcome rows; copy is display-only.

Track C (offline 3-cell count) is a one-shot eval note, not a new event.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** `model_arm` is a VARCHAR; `"challenger"` is a new value of an existing column, not a migration. Same for `bakeoff_runs.arms_json` keys.
- New/changed feature flags: **none.** `trade.bakeoff` already gates the fan-out. `bakeoff_serve_interleaved` stays `0`. Do not add `trade.challenger`.
- New env vars: **none.**
- New `_DEFAULT_CFG` / `model_config` keys (Track A):

  | Key | Default (live identity) | Challenger overlay | Rollback |
  |---|---:|---:|---|
  | `user_elo_shrink` | 1.0 | 0.0 | overlay off, or set 1.0 |
  | `consensus_both_ways` | 0.0 | 1.0 | overlay off, or set 0.0 |
  | `consensus_fairness_floor` | 0.0 | 0.75 | overlay off, or set 0.0 |
  | `bakeoff_include_challenger` | 1.0 | n/a (composition) | set 0.0 — restores pre-challenger roster |
  | `bakeoff_include_gen_v2` | 1.0 | n/a (composition) | set 0.0 drops arm C |

  These keys are **not** added to `MODEL_A_PROFILE`. Defaults are the pre-challenger engine; pinning the kill value would *change* arm A. Exclusion reason goes in [scope-phase2.md](../three-model-bakeoff/scope-phase2.md). Keys go in `_PINNED_KNOBS`.

  Profile-only (existing keys, live defaults untouched): `need_gate_min_value`, `tier_mult_elite|starter|solid|depth|bench`.

- Track B if promoted: `likes_you_min_user_delta` −500 → 0 is a live default change (deploy-free via `PUT /api/admin/config/likes_you_min_user_delta`). Copy may take `copy.honest_fairness` default ON if the EM wants a flag; not required.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED — backend-only for Track A. No mobile diff, no `check-*.js`. Track B2 (copy) adds or extends a copy-string guard if one exists; otherwise a unit test on `build_narrative` / the client formatter.
- [x] **Unit tests:** `backend/tests/test_bakeoff_challenger.py` (new); updates to `test_bakeoff_composition.py`, `test_bakeoff_runner.py`, `test_bakeoff_serving.py` (PHASE3_KNOBS pins `bakeoff_include_challenger=0`), `test_bakeoff_arm_a_golden.py` (`_PINNED_KNOBS`), `test_user_gain_gate.py` still green with overlay off. See PRD §5 A4.
- [x] **Code-walk proof:** PRD §4 table cites the live sites. Builder records file:line in TEST_LEDGER after implementation.
- [ ] **Manual TestFlight checklist:** WAIVED for Track A — dark, no user-visible surface. Required for Track B if promoted (one likes-you you-pay card must not appear; one “balanced” card at fairness 0.58 must not say balanced).
- `testID`s added/renamed: **none** for Track A.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no schema/route convention shift |
| `docs/architecture.md` | update after merge | bake-off arm list (A/B/C → A/B/C/D) |
| `living-memory/HLD.md` | n/a | no new module; profile on existing engine |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | update after merge | `challenger` / arm D |
| ADR or `DECISIONS.md` | **yes, at merge** | D-092 (proposed): challenger is a new arm, not a new Arm A |
| `docs/config-reference.md` | update after merge | the five new knobs |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **yes, in A2** | exclusion rows for the new knobs |
| `docs/plans/three-model-bakeoff/PLAN.md` | update after merge | arm table footnote: D exists, A is untouched |
| `living-memory/TEST_LEDGER.md` | at merge | A4 pytest |

## 5. Ship gate declaration

- **CI green:** `backend-tests` on the pushed sha. Mobile jobs unchanged for Track A.
- **Evidence recorded:** TEST_LEDGER naming the files in A4 and what they proved.
- **TestFlight verification:** none for Track A. Track B if promoted: operator run, logged.
- Express lane: **no.**
- **User-visible serving:** none. `bakeoff_serve_interleaved` stays 0. Promoting the challenger to a served arm is a separate operator decision, not this scope.

## 6. Open operator decisions (do not block A1–A4)

1. Track B in the same sprint, later, or never? Recommendation: B1 in the same sprint (required under both product calls); B2 can follow.
2. Default `bakeoff_include_gen_v2` — keep 1 (roster is current + challenger + gen_v2) or set 0 so the head-to-head is clean? Recommendation: keep 1 in code, set 0 in prod config when the operator wants a two-arm test.
3. C1 before merge, or C1 in parallel? Recommendation: parallel; **do not light interleaved without C1**.
