# Ship-time entries — DRAFTED, NOT APPLIED

**For the session that merges `fix/package-benchmark-sweetener` to `main`.**
The merge is held for the operator's Monday boundary, and a DECISIONS/CHANGELOG
entry written before the ship would be a claim about something that has not
happened. Paste these when it does, after checking the two things below.

**Check before pasting:**

1. **ID collision.** These are numbered `D-142`…`D-144` against a
   `living-memory/DECISIONS.md` whose highest sequential heading was **D-141**
   on 2026-08-21. Sessions run concurrently in this repo — re-grep
   (`grep -oE "^## D-[0-9]+" living-memory/DECISIONS.md | sed 's/## D-//' | sort -n | tail -1`)
   and renumber if anything landed first. Fix the cross-references in the
   CHANGELOG entry if you renumber.
2. **The operator has ratified the six items** in
   [scope.md §6](scope.md) — especially the arm-A pin-instead-of-recapture
   (item 1) and the flag-off golden re-capture (item 2). D-142 states the
   first as settled; do not land it unratified.

---

## DECISIONS.md — three entries

```markdown
## D-142 — Package depth discount benchmarks the TRADE's best asset, and arm A is PINNED rather than re-captured
**Date:** 2026-08-21 (operator-approved; evidence `docs/reviews/2026-08-21-market-curve-comparison.md` §3b)
**Context:** `_package_value_market` benchmarked every piece of a package against the package's OWN best asset, so four similar mid-tier players buying a stud took only a ~5% haircut. The served Rice + Etienne + Swift + Corum → Puka Nacua card priced 0.939 — inside the ±15% serve band — while FantasyCalc priced the same package at 1.362× Nacua and KTC at 2.260×. The engine was calling a wild overpay fair.
**Decision:** A multi-asset side that does NOT hold the trade's best asset is depth-benchmarked against `v_max`, the best asset in the WHOLE trade (KTC's published shape), at a lower contribution floor `package_floor_cross` = 0.40. Knob `package_bench_trade_wide` (default 1.0); ≤ 0 restores the pre-fix own-max math. Single-asset sides and the side holding the trade's best asset are untouched, so every 1-for-1 fairness ratio and the consolidating stud-plus-filler shape are unchanged. **Arm A pins both knobs at 0.0 and its golden was NOT re-captured** — the kill value is a proven no-op, which is strictly better for D-075 than a moved baseline.
**Alternatives considered:** Re-capture the arm-A golden at the new engine (rejected: it would erase the only fixed point the bake-off has, for a change that is provably inert at arm A's settings). Lower `package_floor_market` globally (rejected: it would re-price the consolidating side too, which the competitor matrix says is already right). Smooth the 0.70 → 0.40 floor across the benchmark boundary (rejected: it moves the tuned Nacua number the operator approved; the discontinuity is bounded at ≈2.3% and is recorded instead — scope.md §6 ratification item 4).
**Consequences:** The Nacua card prices 0.709 and no longer serves — between FantasyCalc (0.734) and the pre-#214 heavy shape (0.692). Decks shrink ~4% across the served arm roster (fixture measurement, TEST_LEDGER 2026-08-21a); the operator accepted that cost up front. Arm A verified byte-identical across the change on both fixture leagues and both engine paths. Deploy-free rollback: `package_bench_trade_wide` = 0.
**Status:** Active.

## D-143 — Absolute consensus gaps above one late 1st are closed at GENERATION time, by adding an asset
**Date:** 2026-08-21 (operator-commissioned)
**Context:** The fairness gate is a RATIO and therefore scale-blind: 0.85 on a five-figure package still leaves more than a late 1st of consensus value on the table, and 15% of served cards carried exactly that (CHANGELOG 2026-08-21). The benchmark fix above makes this worse before it makes it better — pricing the multi-asset side lower widens the absolute gap on the cards that survive.
**Decision:** New knob `sweetener_gap_threshold` (default 1539.0 = one late 1st, the operator's agreed line). At generation time, per arm, a card whose `|give_value − receive_value|` exceeds it gets the smallest sufficient equalizer asset ADDED from the RICHER side's roster, re-earning the fairness band, 3.2 lineup feasibility and the calling path's own gate stack (`trade_optimizer.close_value_gap`, generalising the 3.4 `_try_sweeten` prior art). A card the pass cannot close is kept UNSWEETENED — the pass narrows gaps, it never shrinks the deck. Hooked into three paths in v1: the v2 divergence pair generator, the consensus generator, and the v3 optimizer. Arm C (`trade_gen_v2`) and the fit arm are named follow-ups, not skips.
**Alternatives considered:** Filter the offending cards out instead of fixing them (rejected: it shrinks the deck twice over, on top of the benchmark fix's own shrink, and it discards genuinely interesting trade ideas over a fixable imbalance). Do it post-draft, once per deck (rejected: it would touch the interleaver's output, which §3.4 Channel 2 forbids, and it would break per-arm attribution). Fold arm C in now (rejected on effort: arm C has its own value math, candidate pipeline and gate stack, and would need its own re-verification of the gen2 goldens for an arm that serves only quota-capped slots).
**Consequences:** Sweetened cards carry `gap_sweetener {player_id, side, gap_before, gap_after}` on the payload and in EVERY impression's `features_json` (null when absent), so the measurement splits cleanly. **Named cost, now quantified:** arm C inherits the benchmark fix in its displayed values but not the sweetener, so its share of cards above one late 1st RISES (0 → 3 of 22 on the 12-team fixture, 1 → 2 of 19 on the 16-team SF). The arm-C follow-up is a priority item because of it. Deploy-free rollback: `sweetener_gap_threshold` = 0.
**Status:** Active.

## D-144 — Ghost suggestions are dead in code, not merely switched off
**Date:** 2026-08-21 (operator ruling, batch-wide)
**Context:** The operator ruled ghosts out on 2026-08-21 — "I still am against the ghost cards" — after ghost accumulation was identified as the amplifier behind the six-card-repeat deck: a ghost can never be decided, so it never leaves the FFV3 candidate pool (one hash ghost-served 35 times; two decks were 100% ghost). The prod `model_config` row was set to 0 the same day, but the CODE default stayed at 10.
**Decision:** `ghost_holdout_one_in` default 10 → 0 at all three sites the value can be read from: `trade_service._DEFAULT_CFG`, `database._MODEL_CONFIG_DEFAULTS` (the seed — a fresh database must not start ghosting), and the inline `_cfg` fallback in `suggestion_telemetry.ghost_one_in`. Each site carries the ruling as a comment.
**Alternatives considered:** Leave the code default at 10 and rely on the prod row (rejected: it makes the ruling a live-DB artifact — one restore, one fresh environment, one missed lookup and ghosting is back). Delete the ghost machinery entirely (rejected: the counterfactual-logging design is sound and the operator's objection is to withholding cards from users, not to the analysis; the knob keeps it revivable without a revert).
**Consequences:** No environment ghosts by default. The `suggestion.telemetry` flag's other halves — policy versioning, candidate-set logging, the executed-trade matcher — are unaffected. `docs/config-reference.md` records the ruling on the knob's row. Re-enabling is a deliberate one-row change, not a default.
**Status:** Active.
```

---

## CHANGELOG.md — one dated H2, newest at the top

Merge into the existing `## 2026-08-21` entry if the ship lands the same day;
otherwise paste as its own dated H2. Keep it under the ~1,200-byte per-entry
cap — detail lives in `docs/plans/package-benchmark-sweetener/`.

```markdown
## 2026-08-21b — Package math benchmarks the TRADE's best asset; gaps above a late 1st get sweetened; ghosts die in code

- **Four quarters no longer buy a dollar** (D-142). `_package_value_market` benchmarked
  each piece against its own package's best asset, so the served Rice+Etienne+Swift+Corum
  → Nacua card priced 0.939 "fair" against FantasyCalc 1.362 / KTC 2.260. A multi-asset
  side that lacks the trade's best asset is now benchmarked against it
  (`package_bench_trade_wide` 1.0, floor `package_floor_cross` 0.40) — the card prices
  0.709 and is blocked. 1-for-1s and the consolidating side are untouched.
- **Gap auto-sweetener** (D-143). `sweetener_gap_threshold` 1539 (one late 1st): at
  generation time the richer side adds its smallest sufficient equalizer, re-earning every
  gate; unclosable cards ship unsweetened. Live in v2 divergence, consensus and v3. Arm C
  and the fit arm are named follow-ups — **arm C's over-the-line share goes UP** because it
  inherits the pricing fix without the sweetener.
- **Ghosts dead in code** (D-144). `ghost_holdout_one_in` 10 → 0 at all three read sites,
  per the operator ruling; prod row was already 0.
- **Measured, not asserted:** deck shrink **−3.9%** across the served arm roster on the two
  fixture leagues (178 → 171 cards), worst cell −20%; arm A **byte-identical** at
  `origin/main` and branch tip on every league × path, which is the live proof of the
  kill-value pins. Suite **3786 passed, 1 skipped**. TEST_LEDGER 2026-08-21a.
- **Round-2 review caught two defects** in the first sweetener build: the consensus path's
  pinned-give / acquire-position pool pruning was bypassed (a "trade away exactly G" job
  shipped an unpinned player), and v3 left a stale 1-for-1 `fit_premium` on sweetened
  cards. Both fixed with regression tests that go red on the pre-review commit.
- **Owed:** operator runs `docs/plans/package-benchmark-sweetener/testflight-checklist.md`
  on the built app; the six ratification items in that plan's scope.md §6.
```
