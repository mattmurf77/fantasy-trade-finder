# Ship-time entries — DRAFTED, NOT APPLIED (arm C follow-up)

**For the session that merges `feat/gap-sweetener-arm-c` to `main`.**
Same posture as the parent's [decisions-draft.md](decisions-draft.md): the
merge is held, and a DECISIONS/CHANGELOG entry written before the ship
would be a claim about something that has not happened.

**Check before pasting:**

1. **Merge order.** This branch is STACKED on
   `fix/package-benchmark-sweetener` @ `480cce0`. The parent lands first.
   Merging this alone would ship arm C's hook without `close_value_gap`
   existing — it does not build.
2. **ID collision.** These are numbered `D-145`/`D-146`, assuming the
   parent's `D-142`…`D-144` land first against a `DECISIONS.md` whose
   highest sequential heading was **D-141**. Sessions run concurrently —
   re-grep
   (`grep -oE "^## D-[0-9]+" living-memory/DECISIONS.md | sed 's/## D-//' | sort -n | tail -1`)
   and renumber both these and the CHANGELOG cross-references.
3. **`G-053` is already applied** to `living-memory/GOTCHAS.md` on this
   branch (harness seed determinism) — it is a record of what happened,
   not a claim about shipped state, so it did not need drafting. Check it
   did not collide.

---

## DECISIONS.md — two entries

```markdown
## D-145 — Arm C's gap sweetener runs inside `_pair_survivors` and rebuilds the candidate, not at the card-build site
**Date:** 2026-08-21 (operator-approved follow-up to D-143)
**Context:** D-143 hooked the sweetener into three paths and named arm C (`trade_gen_v2`) a follow-up. Arm C meanwhile INHERITED the D-142 trade-wide package benchmark — which widens absolute consensus gaps — through `_consensus_packages`, without the closer. Measured: its share of cards above one late 1st sat at 13.6 % (3/22) and 10.5 % (2/19) on the two fixtures while every other served arm read 0–5.3 %, with its deck card-for-card identical across the parent. Inheriting the widener without the closer is a one-directional regression.
**Decision:** Arm C's sweetener is hooked **inside `_pair_survivors`, immediately after gate c**, and the entire `_Candidate` is rebuilt from the sweetened ids — NOT at `generate_league_suggestions`'s call to `_consensus_packages`, which is the only place the gap is directly computable and therefore the textually obvious site. `close_value_gap` is called with `fairness_threshold=0.0`, making its built-in consensus-ratio gate inert, because arm C's real fairness gate is the `consolidated_value` band; that band, the dual-board ε-gains, #141 filler, #227 pick-churn, G6 #341/#339 and the `past_decision_keys` ban are all re-earned in `extra_ok_fn`.
**Alternatives considered:** Sweeten at the card-build site and patch the affected card fields (rejected: TEN derived values are computed earlier from the `_Candidate` — `_dedup_batch` keys, `_meso_variants`, `_rationale`, `classify_package_shape`'s `len(ids) == 1` "consolidation" label, `card.health`'s seven entries, `mismatch_score`, `fairness_score`, `composite_score`, and the Stage 6/7 exposure + tier ranking — so patching is an open-ended list that silently rots as arm C grows; this is the same defect class as the v3 stale `fit_premium`, with a much larger surface). Pass `1 − gen2_band` as the helper's fairness threshold (rejected: it imposes on arm C a ratio constraint it has never had, in a value space it does not use).
**Consequences:** Arm C stops being null on the existing `gap_sweetener` payload + `deck_impressions.features_json` key, with **no `server.py` change** — both consumers already read it generically. `GenerationReport` gains a `gap_sweetened` counter. **One behaviour differs from the other three paths and is accepted:** D-143 says the pass "narrows gaps, never shrinks the deck", which does not hold for arm C, the only path with `_dedup_batch` downstream — its bucket key includes the give×receive SHAPE, so a sweetened card can land in an occupied bucket and evict the lower-ranked occupant. Observed once in arm C's own suite, where both colliding cards were themselves over the line, so the deck went 3 → 2 and the over-line count 2 → 0. Deploy-free rollback unchanged: `sweetener_gap_threshold` = 0, proven a byte-identical no-op for arm C too.
**Status:** Active.

## D-146 — The sweetener's equalizer universe is arm C's SEMANTIC pools, not its enumeration-budget slices
**Date:** 2026-08-21 (operator ruling, made with the measurement in hand)
**Context:** The round-2 review of the parent (`49c1d76`) established that a path which PRUNES its candidate pools must have those pools passed to `close_value_gap`, or the sweetener smuggles in assets the path would never enumerate. Arm C prunes — but in two layers, and the naive reading (pass the pools the enumerator literally uses) makes the feature a measured no-op: wired to `give_pool`/`extras` the pass fires but the deck metric does not move at all, because **78 of 112 and 63 of 86 rejected equalizers are undershoot** — nothing in the slice is large enough — against only 8 and 13 killed by arm C's own gates.
**Decision:** Distinguish the two layers. The **semantic** pools — `user_assets` (ranked on BOTH boards, not untouchable) and `extras_all` (divergence-positive, not not-interested) — encode real rules and are the equalizer universe. The **budget** slices `[:gen2_give_pool]` and `[:gen2_recv_extra_pool]` are enumeration cost only, documented as bounding "SEARCH BREADTH, never output length" alongside `gen2_centerpiece_top_k`, and the sweetener deliberately reaches past them.
**Alternatives considered:** Pass the budget slices (rejected: measured no-op, above — it would have shipped the feature's justification unmet). Add a `gen2_sweetener_full_pool` knob defaulting OFF (rejected: a fourth knob on an arm that already carries ~15, plus a default-OFF path no golden covers, to defer a decision the measurement already answers). Allow multi-asset equalizers (not rejected on merit — out of scope here; the 24 and 7 *overshoot* rejections suggest granularity is a smaller second-order limit worth its own look).
**Consequences:** 12-team fixture goes **3 → 1 over the line (13.6 % → 4.6 %), p90 1665 → 951**; 16-team holds at 2 but mean gap falls 551 → 488. This is expressly NOT the `49c1d76` defect relaxed: that one crossed a semantic line — a #174 pinned "trade away G" job smuggling in an unpinned player, i.e. a broken user instruction — whereas a rank-11 give asset breaks no rule and `close_value_gap` still takes the CHEAPEST sufficient equalizer, so the reach buys coverage, not overpayment. Pinned by `test_arm_c_equalizer_reaches_past_the_budget_slice`, which is the single test that separates this decision from its alternative. Costs: an equalizer may be a give asset the opponent does not over-value, or a low-divergence receive asset, slightly diluting the card's divergence story — IR is re-gated, so it cannot break acceptance.
**Status:** Active.
```

---

## CHANGELOG.md — one entry (merge with the parent's if both ship together)

```markdown
### Gap auto-sweetener extended to bake-off arm C

Arm C (`trade_gen_v2`) had inherited the trade-wide package benchmark —
which widens absolute consensus gaps — without the sweetener that closes
them, leaving 13.6 % / 10.5 % of its fixture cards above one late 1st
against 0–5.3 % for every other served arm. It now runs the pass.

Not a fourth copy of the same hook: arm C's sweetener runs inside
`_pair_survivors` and rebuilds the whole `_Candidate`, because ten derived
values — dedup keys, MESO variants, the rationale, the package-shape
label, `card.health`, the fairness/mismatch/composite scores and the
exposure + tier ranking — are computed before the card exists ([D-145]).
The equalizer is drawn from arm C's semantic pools rather than its
enumeration-budget slices, which is what makes the change measurable at
all ([D-146]): 12-team fixture 3 → 1 cards over the line, p90 1665 → 951.

No new knob, no flag, no `server.py` change. `sweetener_gap_threshold` = 0
remains a byte-identical no-op for arm C too. Goldens re-verified and
unmoved — instrumented, not assumed: no golden fixture reaches arm C's
generator at all, confirmed by forcing the gap line to 1.0.
```
