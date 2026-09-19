# Fit-challenger PRD review — against the audit corpus and fresh prod data (2026-08-20)

**Status:** point-in-time review, not reference. Reviews [`docs/plans/fit-challenger/PRD.md`](../plans/fit-challenger/PRD.md)
(operator-ruled, 2026-08-19, not built) against the arm-B audit corpus, the knockout waterfall,
and the 2026-08-20 read-only prod pull recorded in
[`docs/plans/trade-engine-accuracy/PLAN.md`](../plans/trade-engine-accuracy/PLAN.md) (appendix).

**Verdict up front: build it.** The architecture — thin category knockouts → dual 0–100 scores →
post-score user filters — is the correct structural answer to the audit's central finding, and it
is the only proposed arm that gives *every* league a two-sided signal rather than only the one
league that has boards. The concerns below are refinements and couplings, not objections.

---

## 1. Where the PRD is right, with the evidence

| PRD claim | Corroboration |
|---|---|
| Value knockouts are "do we like this?" dressed as "must not show" (§2) | Audit: `rv ≥ gv` (ε=0) makes the user win on 7,094/7,094 consensus cards; waterfall: it first-kills 71.7% of the consensus universe but uniquely kills only 1,156 — the *information* it encodes is nearly free to keep as a score |
| Scoring instead of deleting is the volume unlock (§1) | Waterfall: 74,330 candidates killed by exactly one rule across three pipelines; #141 filler alone uniquely kills 57,815 — more than every other rule combined in each arm |
| K1 widening (3-for-1, 1-for-3, 3-for-2, 2-for-3) | Prod: **zero** `1x2` packages have ever existed (6,635 `1x1`, 459 `2x1`) — partner-favourable consolidation is unrepresentable in arm B, exactly as claimed |
| Lens 3 always-on gives unranked partners a score (§4) | Board supply: exactly one league has ≥3 boards (6, 2, 1, 1, 1, 1, 1). Real launch traffic is boardless; an arm that degrades to consensus-only *per team* is the only launch-relevant two-sided design |
| Preferences filter after scoring, never shrink the search (§6) | Matches the matchmaking corpus (pool hygiene: a preference hides, it does not delete the idea from the partner's universe) and fixes the class of bug where boarding *reduced* a member's tradability |
| Enumeration honesty (§5) | The 7e6 risk is named, the cap is mandatory, 1-for-1-first + expand is the right budget shape |
| Reuse live predicates, don't fork (§3) | Correct — and see trap T1 below, which makes *how* they are imported load-bearing |

The operator's stated rationale — limited idea volume; rank-vs-consensus in all combinations
gives variety bounded by reasonable value — is confirmed by the data: median deck 26.5 post-dedup,
`current_divergence` filled 153 of 790 group slots over 79 runs, the outlook lane fills ~1/3, and
K4 (R1 overpay, ±25%) remains as the value boundary. The union pool (consensus top-8 ∪
board-vs-seed top-8 ∪ board-vs-board top-8) is literally "all combinations of consensus vs ranks."

## 2. Concerns, in order of importance

**C1 — The PRD does not address serving, and serving is where the last two arms died.**
Arms C and D generate, attribute, and log; neither has ever produced a user decision, because
`bakeoff_serve_interleaved = 0`. Prod today: `model_arm` ∈ {`current`, NULL} on all 9,111
impressions ever. An unserved `fit` arm produces diagnostics, not accuracy. The build plan must
couple F5 with re-lighting interleaved serving for tester leagues — with the lane-quota fix
(`bakeoff_group_value_slots = bakeoff_group_size`, or `group_size = 0`) so the 2026-08-18
deck-shrink revert doesn't repeat.

**C2 — K7 (R5) as a knockout contradicts the arm's own thesis, and the data is against it.**
R5 is the third-largest unique excluder on the consensus path (1,919), it takes no partner
argument, it killed 61 shapes with *dual* `need_fit ≥ 0.75`, and 10 of 12 declared prod outlooks
are contend-side — R5's kill demographic is almost the entire user base. The operator ruling
(§12.4) stands and v1 keeps it; but v1 should pre-wire the deploy-free demotion
(`fit_r5_mode: 1 = kill (default) | 0 = score into the viewer lens`) and the dry run must report
`killed[K7]` prominently, so F7 is a knob flip with evidence rather than a new build.

**C3 — Like-rate will misread this arm unless the readout is bucketed.** The arm deliberately
serves `you_tilt`/`them_tilt` cards; a pooled like-rate comparison against arm B (whose consensus
cards the user wins by construction) is biased in arm B's favor — the D-095 tension, doubled.
§7 already splits buckets; make it binding: **co-primary metrics = like-rate on
`both_high` + `mixed` only, and `value_giving` share of decline reasons** (40% today — the #1
user complaint, and the thing dual scores exist to fix). Pooled like-rate is a guardrail, not
the verdict.

**C4 — `basis` is overloaded.** Arm B stamps which *generator path* ran; `fit` would stamp
"divergence iff both boarded." A per-basis metric split across arms compares different concepts.
Either stamp `fit`'s data-availability on a separate feature key and hold `basis` to the arm-B
meaning, or document the divergence loudly in the analytics notes. (LLD decision.)

**C5 — Junk and pick flooding return through the open door.** Filler and the divergence prune are
gone as kills; picks are always in the pool (K0) and were historically unprunable (both boards
share one `pick_elos` number, so every prune test degenerates to `x ≥ 0.97x`). Lens-3 scoring
*should* tank junk-padded sides — but this is asserted, not measured. The §10 mitigation (filler
back as a default-off knob) is right; the dry run must report the pick-share and junk-share of
top-quartile-aggregate cards before the arm rosters.

**C6 — Job budget.** Bake-off runs already hit 7.5s at 3 arms on the boarded league. A fourth
arm at `fit_max_packages_per_pair = 20,000` × 11 opponents adds real work against
`_JOB_HARD_TIMEOUT = 60` — likely fine (scoring is sums; K3 feasibility is the expensive
predicate, so run it *last* in the K-order despite its K3 name), but the dry-run ms bar in
scope §6 is the gate and the arm-roster knob is the relief valve.

**C7 — Spec nits for the LLD.** (a) The tanh comment is wrong: `score(400) = 50 + 50·tanh(1) ≈ 88`,
not ~84 — fix the comment or set `fit_score_scale ≈ 493`; pin the curve with a value table in
tests. (b) `composite_score` on a 0–200 scale is safe for the group draft (rank-based) but must
never be compared across arms as a magnitude — assert that nothing downstream does.
(c) `score_you + score_them` double-weights lens 3 when both teams are unranked (both sides are
the same consensus number mirrored: aggregate ≈ 100 always) — fine for ranking *within* a pair,
meaningless *across* pairs; the ranker should be aware (e.g., tie-break unranked-pair cards by
consensus fairness, or accept and document).

## 3. Traps the implementer inherits (from the audit's warnings)

- **T1 — Import-time binding.** `trade_optimizer.py` and `trade_gen_v2.py` bind live predicates
  **by value** at import; an agent measuring a wrapped-not-edited gate saw a perfect no-op on a
  gate firing 1.17M times. `trade_gen_fit.py` must import the *module* (`from . import
  trade_service as ts; ts.overpay_ok(...)`) or import inside the call, so knob changes and
  D-096-style edits propagate.
- **T2 — `executemany` column drop.** Stamping any new per-card column on only some rows silently
  drops it for the whole deck. Every row, every column.
- **T3 — Provenance.** Consensus path passes raw values where v3 passes shrunk (audit bug 3).
  The fit scorer must pin, in writing, which board object each lens reads.
- **T4 — Golden hygiene.** Arm A's knob-inventory test fails BY NAME on any `_DEFAULT_CFG` key
  added — every `fit_*` knob needs its arm-A disposition recorded (they are generation knobs for
  a module arm A never calls; the guard still demands the sentence).

## 4. Relationship to the accuracy plan

The fit arm slots into [`trade-engine-accuracy/PLAN.md`](../plans/trade-engine-accuracy/PLAN.md)
as the Phase-1/Phase-3 vehicle: it *is* the multi-model test's new treatment, the tester protocol
is its readout, and the launch gates don't move. It does not replace the two measured arm-B
levers (`user_elo_shrink`, soft R5) — those fix the engine 100% of traffic sees while `fit`
is an experiment; the bake-off decides whether `fit` earns the serving path.
