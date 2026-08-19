# Feature Scope — Engine quality: pick-fairness, minimality, pick-pair churn, headliner diversity, confidence damping

**Date:** 2026-08-18
**Entry point:** direct ask (operator field report — "the live suggestion engine is producing mostly nonsensical trades"), diagnosed against the live production corpus (563 impressions / last 8h)
**Builder:** backend build agent, branch `feat/engine-pick-and-diversity`
**Operator sign-off on waivers:** needed — §1 (c), §3 Maestro waiver. Both are stated below; the change is backend-only with no mobile diff.

---

## 0. Problem statement (why this exists)

Two defects were diagnosed from the live corpus.

**Defect A — picks are free fairness.** Draft picks carry ZERO board divergence by
construction: every board is primed with the same bridged Elo (see the `pick_swap_ok`
docstring). The ranking score is
`composite = mismatch_weight(0.70)·mismatch + fairness_weight(0.30)·fairness`.
The consensus `fairness` term rises when a pick closes the give/receive value gap, while
the pick contributes no information about *mutual gain* — the whole point of the
divergence engine. Nothing anywhere penalises package size. Measured: **63% of live
cards involve a pick**; shapes like `PICK PICK PICK -> RB WR` (18 cards) and
`PICK PICK -> RB` (16). 25% of multi-asset pick cards end with a <10% value gap — the
pick is pure fine-tuning on a trade that was already fair. Operator: "the random
insertion of picks when a trade would be fair without them is by far the most
nonsensical behavior."

**Defect B — one player floods the whole deck.** `_dedup_and_sort` does EXACT-KEY dedup
only (frozenset give/receive vs past decisions) and then sorts by composite. It has no
notion of a repeated headliner. `mismatch` is largest for whichever asset diverges most
between the two boards, so that asset generates many distinct high-scoring packages and
all of them survive. Measured: Colston Loveland in 18/18 cards of one deck (100%); 8/8
in another; MarShawn Lloyd 13/33; Trevor Lawrence 12/36. A single valuation error is
therefore catastrophic instead of survivable — mismatch is LARGEST exactly where a
valuation is most wrong.

Five changes, each behind its own `model_config` knob with a documented kill value,
following the existing G6 per-rule kill-switch pattern (`max_overpay_frac` /
`pos_net_cap` / `pick_gap_frac`).

**These knobs change LIVE behavior for every user.** The v1 engine path
(`trade_engine.v2` + `trade_engine.v3`, both ON in `config/features.json`) is what
everyone is on. `trade_gen.v2` is dark and is NOT a target of this work —
`backend/trade_gen_v2.py` is untouched. The knobs default **ON** because the current
behavior *is* the bug; every kill value is a one-line, deploy-free revert
(`PUT /api/admin/config/<key>`), and each disable value restores byte-identical prior
behavior (proven by test, one per knob).

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** all five changes are ranking/gating
  math inside the existing generation path. No new user-visible surface, no new user
  action, no new client code. The existing suggestion telemetry
  (`deck_impressions`, incl. `centerpiece_id` and `assets_json`) already captures every
  quantity needed to measure the effect: pick-share per card, package size, and
  headliner concentration per deck are all derivable from rows that are already written.
  The measurement plan is a re-run of the same corpus query that produced the numbers in
  §0 — no new event is required to answer "did pick-share and headliner concentration
  fall?".

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** none. Deliberate: the operator's directive is that each
  change gets its OWN knob (per-rule kill switch), not a shared group flag. A group flag
  would make the five changes un-revertible independently, which is exactly the failure
  mode the G6 per-rule knobs were introduced to avoid.
- **New `model_config` keys** (all → `docs/config-reference.md`):

  | Key | Default (ON) | Kill value (restores prior behavior) | Change |
  |---|---|---|---|
  | `rank_div_min_frac` | `0.02` | `0` | 1 — divergence-gated ranking fairness (kill also reverts the tie-break it owns) |
  | `min_package_band` | `0.10` (fairness units) | `0` | 2 — prefer the minimal package among near-equivalents |
  | `pick_pair_strip_frac` | `0.85` | `0` | 3 — strip matched pick pairs before the churn gate |
  | `deck_headliner_cap` | `2` | `0` | 4 — max cards per centerpiece in one deck |
  | `mismatch_confidence_damp` | `1.0` | `0` | 5 — confidence damping of the mismatch term |

  **All five defaults are UNMEASURED against the live corpus.** They are reasoned from the
  fixtures in §3, not fitted to the 563 impressions — each knob is the named tuning lever, and
  a re-run of the corpus query is the measurement.

- **Ship-the-knob:** every row above is the deploy-free rollback lever for its own
  change. Setting all five to their kill value returns the engine to `origin/main`
  behavior with no deploy.

## 3. Test scope

- [x] **WAIVED (Maestro):** backend-only change. No file under `mobile/` is touched, no
  `testID` is added or renamed, and no screen renders anything new — the deck is the
  same list of the same card component, differently ordered and filtered. There is no
  user-visible affordance for a Maestro flow to assert on. The existing smoke flows that
  cross the deck surface (`trades`, `matches`) are unchanged and remain valid.
- `testID`s added/renamed: none.
- **Capture delta:** none — no visual change.
- **Smoke-suite impact:** the trades-deck smoke flows exercise generation end-to-end; they
  assert cards render, not which cards. Unaffected.
- **Backend pytest:** two new files.
  - `backend/tests/test_engine_quality.py` (22 tests) — per change: a behaviour test and a
    kill-value no-op test, plus for change 1 the brief's explicit property test ("adding a pick
    to a fair package does not raise composite"), each with a **fixture-validity assertion that
    the defect IS live at the kill value** so the test cannot silently stop reproducing anything.
    Change 4 ships the Defect B fixture deck: one asset headlining cards against three
    counterparties (**21 of 36** cards uncapped → **2** capped; it floods ACROSS opponents on
    purpose, since a per-opponent cap of 2 would still have served six).
  - `backend/tests/test_engine_quality_golden.py` (3 tests) — the byte-identity CLAIM, proven
    rather than asserted: goldens captured by running the same fixtures in a throwaway worktree at
    `origin/main` @ `90fb19a`, then compared against all-five-knobs-killed output. A third test
    asserts the goldens are not vacuous (the live defaults must differ), so the proof cannot rot
    into a tautology. Re-capture procedure is in the file's docstring.
  - Existing suites that pin engine behaviour (`test_trade_engine_v2.py`,
    `test_pick_swap_gate.py`, `test_presentment_rules.py`, `test_asset_ideas.py`,
    `test_fairness_gate_golden.py`, `test_trade_optimizer.py`, `test_outlook_direction.py`) stay
    green **unchanged** — three of them caught real defects in this build (§5) and none was
    weakened to make the wave pass. Result: 3150 passed / 1 skipped, against a 3125 baseline.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. The five knobs are read through the existing `model_config` surface and are set with the already-documented `PUT /api/admin/config/<key>`. |
| `living-memory/LLD.md` | updated | New "Ranking-vs-gate separation" convention: a gate judges the REAL package, a ranking term may judge the divergence-bearing core. Recorded because it is a convention future engine work must follow, not a one-off. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. Same call graph; `pick_swap_ok` gains an optional kwarg, no new module. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or color changes. The knobs are backend-only ranking parameters no client reads. |
| `docs/glossary.md` | updated | New terms: **signal core**, **centerpiece**, **headliner cap**, **matched pick pair**. |
| `DECISIONS.md` | updated | **D-074** (renumbered from D-068 — ID collision) — design (b) divergence-gated fairness chosen over (a) a package-size penalty, with the full alternatives list and the accepted consequences. |
| `living-memory/TEST_LEDGER.md` | updated | Suite totals, the before/after fixture numbers, the golden-capture procedure, and what is NOT covered. |

## 5. Design decision for change 1 (recorded, per the brief)

Two designs were on the table.

**(a) Per-asset package-size penalty on composite.** A multiplicative tax per extra
asset. Rejected on three grounds. First, it mis-names the defect: the problem is not
package size, it is that a *zero-information* asset purchases score — a 3-for-2 of five
genuinely divergent players is a good trade and would be taxed identically to the same
shape padded with three picks. Second, it needs calibration against the composite scale
to guarantee anything, and the guarantee it buys is conditional (the tax must exceed the
largest possible fairness gain, which is unbounded on an unfair base package). Third, it
punishes legitimate consolidation, which the existing `crown_asset` math deliberately
rewards — two knobs pulling opposite ways.

**(b) Divergence-weighted fairness contribution. CHOSEN.** The fairness term used for
RANKING is computed on the *signal core* — the sub-package of assets whose two boards
actually disagree (relative divergence ≥ `rank_div_min_frac`). Assets with ~zero board
divergence are excluded from that computation entirely, so they cannot move the ratio.
This is closer to the actual defect and gives an *exact, unconditional* invariance rather
than a calibrated one: adding a zero-divergence asset to either side leaves the
ranking-fairness term bit-for-bit unchanged, for any base package, fair or not.

Three consequences were considered and accepted:

1. **The GATE is untouched.** `fairness` as a gate still judges the REAL package on real
   consensus values, because a pick genuinely does transfer value and genuinely can make
   an unfair trade fair. Only the RANKING term is core-based. This is the convention
   recorded in `living-memory/LLD.md`.
2. **Degenerate cores fall back.** If stripping empties either side's core — the
   legitimate "buy a player with a pick" shape, and every consensus-basis card, where
   nothing diverges by definition — the full-package fairness is used unchanged. Without
   this, every pick-for-player trade would lose the whole 0.30 fairness term and be
   systematically demoted, which is not the defect and would be a new one.
3. **The mismatch term is deliberately NOT core-gated.** A pick added to the short side of
   an imbalanced deal really does move value to the user on the user's own board; the
   harmonic-mean surplus gain is real, not free. It is left alone on purpose. This is why
   the required property holds anyway: on an *otherwise-fair* package the two surpluses
   are already near-balanced, so adding a pick pushes them apart and the harmonic mean
   FALLS (or the card fails a surplus gate outright) while the fairness term is pinned —
   composite cannot rise. The test pins both halves: the invariance directly, and the
   composite property on a fixture.

**Three findings that changed the build, recorded because they were not obvious up front:**

1. **C1 creates ties, so C1 had to own them.** Pricing on the core removes not only the pick's
   ability to RAISE fairness but also its ability to LOWER it, so a package and its padded
   sibling now score *identically*. The v2 heap's pre-existing tie-break is `_tb` descending —
   later-enumerated wins — and 1-for-1s are enumerated first, so the bare deal lost every tie it
   now made and was evicted by its own padding.
   `test_fairness_gate_golden.py::test_v2_v3_fairness_score_parity` caught this. The fix is a
   minimality tie-break in the same heap, gated on the same knob so the kill value reverts both
   halves together. v3 already ordered ties toward the smaller package and needed no change.
   **Accepted trade-off:** where padding used to be penalised (it worsened full-package
   fairness), it is now merely tied. The composite gap between a bare deal and its padded
   sibling narrows; the tie-break keeps the bare one first, and C4's headliner cap collapses the
   siblings that remain. This is a real softening in one direction, taken because the exact
   invariance in the other direction is what the brief asked to establish.
2. **C2's band had to be measured in fairness, not in gap.** The first implementation bucketed
   raw gaps by a fraction of the pinned asset's value. `test_asset_ideas.py::
   test_receive_direction_mirrors_grouping` caught that this makes a 0.572-fairness bare deal
   tie with its 0.697 sweetened sibling and win on piece count — simpler, but worse. A tolerance
   in fairness units, measured from the best variant of the same search, says the thing actually
   meant: *these variants are about equally proposable, so take the simplest one*.
3. **An empty job seed map makes "centerpiece" meaningless.** With no consensus values every
   asset ties at the 1500 default and `deck_centerpiece` degenerates to "largest player id", so
   the C4 cap would drop cards for no reason. `test_outlook_direction.py` (which calls
   `_generate_trades_v2` directly) caught it. No seed map ⇒ no cap.

**Binary gate rather than graded weights.** `rank_div_min_frac` is a threshold, not a
continuous weight. A graded weight would multiply each asset's value by its divergence
before the package math; that is strictly more machinery and, because
`package_value_v2`'s 'heavy' mode branches on `len(values) < n_other` for the crown
premium, a zero-*weighted* asset still changes the asset COUNT and can therefore still
move the ratio. Dropping the asset outright makes the invariance exact in every stud-tax
mode, and it is less code. Simplicity-first per `docs/coding-guidelines.md` §2.

## 6. Ship gate declaration

- **Simulator-gate tier:** Tier 4 — none, CI only. Backend-only diff; no `mobile/` file is
  touched, so there is nothing for the simulator to exercise that the backend suite does
  not already cover. Declared by the operator in the build brief.
- **Evidence:** full `backend/tests` run recorded in `living-memory/TEST_LEDGER.md`.
  `qa/sim-runs/last-sim-run.json` not written — Tier 4 runs no simulator.
- **Operator deviation from the matrix:** the Tier 4 declaration IS the operator's call,
  stated in the build brief alongside the Maestro waiver. No further deviation.
