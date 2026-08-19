# Three-model bake-off — parallel generation, interleaved serving, per-model verdicts

> **Operator intent (2026-08-18):** run the original trade-finder logic, the current
> (post-fix) logic, and `trade_gen.v2` **side by side**, serving trade chips round-robin
> from all three, so the decline-reason feedback attributes quality to a specific model.
> Outcome options stay open: pick a winner, blend, or use agreement between models as a
> signal. **Step one is only: make all three runnable in parallel and capture clean
> attributed data.**

---

## 1. What "three models" precisely means

| Arm | Name | What it is | How it is invoked |
|---|---|---|---|
| **A** | `baseline` | The engine as it behaved **before** the 2026-08-16 wave — no G6 presentment rules, none of the pick/diversity fixes | Same code, run under a pinned config profile that sets every post-08-16 knob to its kill value |
| **B** | `current` | The engine **after** G6 + the pick-spam/diversity fixes | Live defaults |
| **C** | `gen_v2` | `backend/trade_gen_v2.py` — the matchmaking-research pipeline (divergence-driven, dual-board ε, MESO, exposure shaping) | Separate module, invoked directly |

**A is a config profile, not a code branch.** This matters and is the single most
important design constraint: the original logic was modified *in place*, so "original"
exists only as a set of knob values. That profile must be **pinned as a named constant
and golden-tested**, or it silently drifts every time someone adds a knob.

```python
MODEL_A_PROFILE = {                 # pinned 2026-08-18; DO NOT edit without re-golden
    "max_overpay_frac":          0.0,   # G6 R1 off
    "pos_net_cap":               0.0,   # G6 R2 off
    "pick_gap_frac":             0.0,   # G6 R3 off
    "need_gate_min_value":       0.0,   # G6 R5 off
    "rank_div_min_frac":         0.0,   # pick-spam fix off
    "min_package_band":          0.0,
    "pick_pair_strip_frac":      0.0,
    "deck_headliner_cap":        0.0,
    "mismatch_confidence_damp":  0.0,
}
```
Plus `trade.presentment_rules` — a **flag**, not a knob, so arm A additionally needs the
R4 exclusion bypassed per-invocation (see §3.3, the one real code change G6 forces on us).

**Golden test (mandatory):** assert arm A's output on a fixture league is byte-identical
to output captured from a worktree at the pre-wave SHA. Without this, arm A is "whatever
the knobs happen to mean today" and the whole comparison is unfalsifiable.

---

## 2. Why this is buildable today

`backend/trade_service.py` already has the exact seam required:

```python
_cfg_local = threading.local()

@contextmanager
def _cfg_override(overrides: dict): ...

def _c(key): # thread-local overrides win over process config
```

Built for #189's relaxed fallback pass, it is **thread-local** — concurrent trade jobs
cannot leak into each other — and `trade_optimizer` (v3) imports `_c` from this module,
so the v3 optimizer honors the same overrides. Arms A and B are therefore the *same code*
executed under two different thread-local contexts, with no forking and no duplicated
engine. Arm C is a direct module call.

**No new configuration machinery is needed.** This is the finding that makes the whole
plan cheap.

---

## 3. Architecture

### 3.1 Generation
One trade job fans out into three generations:

```
run_bakeoff(job):
    with _cfg_override(MODEL_A_PROFILE):  cards_A = generate(...)   # + R4 bypass
    cards_B = generate(...)                                          # live defaults
    cards_C = trade_gen_v2.generate_league_suggestions(...)          # direct
```

Run them **sequentially inside the existing daemon thread**, not in parallel threads:
the seam is thread-local, so concurrent arms in sibling threads would each need their own
context, and the enumeration is CPU-bound anyway — parallelism buys little and risks the
`_cfg_local` discipline. Budget: expect ~3× generation cost. The existing 3s deadline is
per-opponent enumeration, not per-job, so the practical cost is wall-clock on the pregen
path — acceptable because pregen is already fire-and-forget.

### 3.2 Arm C's known shortfalls (design for them, do not paper over)
- `trade_gen_v2` is **divergence-only by design**; unranked opponents produce nothing.
- Its acceptance prior is unwired (neutral) and its knobs are unmeasured.
- It will therefore under-produce relative to A/B, especially early.

**Consequence for the interleave:** arms must be allowed to return fewer cards than their
slot quota. A short arm forfeits its slot to the next arm in rotation — and *the forfeit
is itself recorded*, because "how often could this model produce nothing" is a first-class
result, not an error.

### 3.3 The one code change G6 forces
`trade.presentment_rules` gates R4 (windowless awaiting/matched exclusion) with **no knob**
— the flag is its only switch. For arm A to be a faithful baseline it needs R4 bypassed
per-invocation. Add a thread-local bypass alongside `_cfg_override` rather than flipping
the global flag (which would disable R4 for arms B and C too, and for every other user).

### 3.4 Measurement hygiene — what must be held still, and what must NOT be

*(Added 2026-08-18 after the operator asked whether re-ranking should be off during the
bake-off. Two distinct contamination channels, needing opposite treatments.)*

**Channel 1 — arms teaching the board.** A trade swipe writes Elo (`trade_k_like` 8.0,
`trade_k_pass` 4.0, against `elo_k` 32.0 for a ranking vote), so a user's response to arm
A's card changes the board arms B and C read on the next generation. The arms are not
independent across decks.

Note the limit of the damage: **within one deck all three arms read the same board at the
same instant**, so the team-draft comparison inside a deck is clean. The drift is a shared
moving baseline across decks, not a per-arm bias.

**Requirement:** the bake-off profile sets `trade_k_like = 0` and `trade_k_pass = 0` for
its duration — config only, no deploy. This severs the arm→board→arm loop exactly.

**Channel 2 — post-generation reordering (the one that silently voids the experiment).**
Five layers currently reorder the deck AFTER generation: `deck.thompson_v2`,
`deck.fatigue`, `deck.session_rerank`, `deck.taste_vectors`, `deck.exploration` — all ON.
If any of them reorders the merged deck after interleaving, **the team-draft position
balance is destroyed** and the bake-off silently reverts to measuring deck position rather
than model quality, with no visible symptom. `fatigue` and `thompson` are additionally
*learning* layers, so left live they also start steering which shapes get served — a second
contamination channel independent of Elo.

**Requirement:** for bake-off decks these layers are either bypassed, or applied to each
arm's own list *before* interleaving — never to the merged deck. A bake-off run with these
layers live on the merged deck is not measuring what it claims to, and any result from such
a run must be discarded rather than caveated.

**What must NOT be frozen** (the instinct to hold everything still is wrong here):
- **Ranking votes** (`elo_k`, the Trios/matchup UI) stay live. Phase 0 exists to unfreeze
  boards; re-freezing them for the bake-off would defeat it and measure models against
  stale values again.
- **Decline-reason capture** stays live — it writes no Elo and it is the measurement.
- **Phase 0's unpinning** stays live, for the same reason.

---

---

## 4. Interleaving policy

Round-robin naively (A, B, C, A, B, C…) **confounds model with deck position** — the
research is explicit that acceptance falls ~27% across a session from position alone, so a
model permanently in slot 3 looks worse than it is.

**Use team-draft interleaving** (round-3 research, `02-acceptance-modeling…` §Part 3):

1. Each arm supplies its own ranked list.
2. Randomize arm order **per deck** (seeded on `league_id + iso_week` for reproducibility).
3. Arms take turns picking their top not-yet-taken card.
4. If arm X's pick is already in the deck (another arm proposed the same trade), X picks
   its next choice, and the card is credited to **whoever picked it first**, with the
   duplicate recorded (§5) — model agreement is one of the most interesting signals here.
5. Record, per card: the arm that contributed it, its rank within that arm, and the
   deck position it landed in.

Why this and not an A/B split by user: at 3–5 users a user-level split has no power at
all. Interleaving needs roughly **100× less traffic** than an equivalent A/B (Thumbtack:
~400 samples vs ~40,000) because every user sees every arm and acts as their own control.

---

## 5. Attribution and capture — mostly already built

The telemetry shipped 2026-08-17 already carries what this needs:

| Need | Existing field |
|---|---|
| Which model produced this card | `deck_impressions.policy_version` — extend to encode the arm |
| Where it sat in the deck | `deck_impressions.card_index` |
| What the user did | `deck_outcomes.action` (+ dwell, expand) |
| **Why they passed** | `trade_pass_reasons.reason` / `.detail` / `.free_text` |
| Counterfactual set | `deck_candidate_sets` |

**Additions required (small):**
- `deck_impressions.model_arm` (`baseline` | `current` | `gen_v2`) — denormalized from
  `policy_version` so every query doesn't have to parse it.
- `deck_impressions.arm_rank` — the card's rank *within its own arm's* list.
- A per-job `bakeoff_runs` row: job id, arm order used, per-arm card counts, per-arm
  generation ms, and per-arm **empty/short** count.
- Duplicate ledger: when arms propose the same trade, record `also_proposed_by` so
  agreement is measurable.

This is why the feedback instrument shipped first — the expensive half of the bake-off is
already live and collecting.

---

## 6. Metrics — what "better" means

Primary, per arm:
1. **Pass rate** (passes / viewed impressions) — the blunt one.
2. **Reason mix** — the real payoff. Not just *how often* an arm fails but *how*:
   `value_giving` vs `value_getting` vs `fit_*` vs `other`. An arm with a high pass rate
   concentrated in `fit_outlook` is mis-reading rosters; one concentrated in
   `value_giving` is over-asking. These are different fixes.
3. **Interest rate** — ✓ taps per viewed.
4. **Executed-trade attribution** — via `suggestion_trade_links`; the ground truth, and
   sparse enough that it will take weeks. Report it, do not gate on it.

Secondary / health:
5. **Empty-arm rate** — how often an arm produces nothing (expected to bite arm C).
6. **Agreement rate** — how often two arms propose the same trade. High agreement between
   A and B means the fixes changed little; agreement between B and C is the interesting
   number for a future blend.
7. **Deck concentration** — max share of one deck's cards sharing a headliner, per arm
   (this is the defect the diversity cap fixed; it should differ sharply between A and B).
8. **Pick share** — % of cards containing a pick, per arm (the pick-spam defect; A should
   be visibly worse).

**Report with uncertainty.** At this sample size, quote intervals, not point estimates,
and prefer *within-user paired* comparisons (every user sees all three arms, so pair on
user and compare arms within that user's decks).

---

## 7. Sequencing — and the confound that must be settled first

> **The pin bug contaminates all three arms equally.** The 2026-08-18 audit found 67.8% of
> ranking comparisons are inert (both players override-pinned), and that votes on a pinned
> player move value *toward* the pin regardless of direction. All three models read the
> same boards. Running the bake-off before fixing this measures **which model best mines a
> frozen board** — a real result, but not the one intended, and the ranking could reorder
> once boards start moving.

Recommended order:

- **Phase 0 — unblock the boards.** Ship the override fix (exclude pinned players from
  `comparison_counts`; timestamp overrides so a newer swipe unpins). Without this the
  bake-off's inputs are frozen. *This is a prerequisite, not a parallel track.*
- **Phase 1 — merge the engine fixes** (`feat/engine-pick-and-diversity`), so arm B is a
  stable, known thing rather than a moving target.
- **Phase 2 — pin arm A.** Capture goldens at the pre-wave SHA; write `MODEL_A_PROFILE`
  and the golden test. Nothing else in the bake-off is trustworthy until this passes.
- **Phase 3 — build the runner.** Fan-out, R4 thread-local bypass, team-draft interleave,
  arm attribution, `bakeoff_runs`, **and the §3.4 measurement-hygiene profile**. Behind
  flag `trade.bakeoff`, default OFF.
- **Phase 4 — dark validation.** Run the fan-out with serving still single-model: generate
  all three, log all three, serve only arm B. Confirms cost, empty-arm rates and
  attribution plumbing with zero user-visible risk.
- **Phase 5 — light it.** Interleaved serving on. Watch generation latency and empty-arm
  rate for a week.
- **Phase 6 — read it.** First per-arm report once each arm has ≥100 viewed impressions
  and ≥50 reasons.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| **Arm A drifts** and stops being "original" | Pinned profile constant + golden test vs pre-wave SHA; CI fails if it moves |
| 3× generation cost blows the pregen budget | Phase 4 measures it before any user sees it; per-arm card quota is knobbed |
| Arm C under-produces and looks bad for the wrong reason | Empty-arm rate is a reported metric, not a silent failure; do not compare pass rates without it |
| Position bias fakes a winner | Team-draft with per-deck randomized arm order; `card_index` recorded for a positional control |
| Sample too small to conclude | Interleaving (~100× more efficient than A/B); report intervals; within-user pairing |
| Duplicate trades across arms muddy credit | First-picker credited, `also_proposed_by` recorded — agreement becomes a feature |
| A "winner" is declared on a frozen board | Phase 0 gates the whole thing |
| Post-generation re-rankers reorder the interleaved deck, voiding the position control | §3.4 Channel 2 — bypass them for bake-off decks or apply per-arm pre-interleave; discard any run where they were live |
| Arms teach the shared board between decks | §3.4 Channel 1 — zero the trade-swipe K factors for the run |

---

## 9. What this explicitly is not

Not an A/B test with a p-value and a ship decision. It is an **instrumented bake-off** to
learn how three generators fail differently, on a tiny user base, using the richest
feedback channel available. The plausible outcomes — pick one, blend, or serve only trades
two arms agree on — all stay open, and the data model above supports all three without
rework.
