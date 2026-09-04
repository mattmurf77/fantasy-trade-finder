# Code-walk proof — personal-market policy

Review note: line references below identify the first agent's implementation snapshot. The integrated revision and additional regression coverage are traced in [the roster/review code-walk](../post-trade-roster-evaluation/code-walk.md).

**Date:** 2026-09-04
**Scope block:** [scope.md](scope.md)
**Baseline:** branched from a freshly fetched `origin/main` @ `606e512c`.
**Evidence type:** written code-walk (D-056 retired Maestro and the simulator; this is
what replaces a capture for behavior that is not mechanically checkable).

Line numbers are on this branch. Re-derive before trusting them if the branch has moved.

---

## 1. The claim

> No finder card reaches a user without passing `trade_policy.evaluate_trade_policy`
> on the exact package it will be served as.

This has to be a *proof*, not a promise, because the failure it prevents is the one that
already happened: threshold logic lived in three modules, and `fairness_floor_divergence`
at 0.55, the relaxed fallback, sweeteners, swaps, likes-you injection, wildcards and
weekly replenishment were six separate routes to the deck under six different bars.

## 2. The choke point

`backend/server.py:7358` — inside `_run_trade_job`, the call is placed:

* **after** the whole mutation stack: v2/v3 generation, the gap sweetener, the 3.4
  sweetener, `_inject_likes_you_cards`, the wildcard insert, first-session shaping, and
  the replenishment kickoff's cards (a replenished deck is produced by the same job
  function);
* **before** the ghost split (`served_final` / `ghost_cards`) and before
  `_log_deck_signal_impressions`.

That placement is the argument. The list it evaluates, `final_cards`, is *the same list*
the impression writer receives — the breaker block immediately below it says so in its
own comment, and it has been true since that block was written. A card added or altered
by any layer above is therefore judged on the package it will actually be served as, and
a layer that mutates a card after this point would have to be inserted between two
adjacent statements.

Ghost rows are inside `final_cards` at this moment, so they get the same snapshot served
rows do — which is what the brief requires ("write the snapshot for served, shadow and
ghost impressions").

## 3. What the choke point does in each mode

`backend/server.py:5257`, `_evaluate_deck_policy`:

| Flags | Behaviour |
|---|---|
| both off | `return cards, {}, []` after two boolean reads. No context built, no card touched, no row written. |
| telemetry only | Every card evaluated; verdicts kept for the snapshot; **the returned list is the input list, unchanged**. Cards the treatment would have rejected are additionally written to `trade_policy_shadow`. |
| policy on | Ineligible cards removed; survivors sorted by `PolicyResult.rank_key`; `compose_deck` applies the Core/Conviction quotas; drops recorded as shadow rows. |

After the Codex review, shadow failures preserve the existing deck, while enforced failures publish no unchecked cards and record a diagnostic. Progressive snapshots wait for the final enforcing checks. See `../post-trade-roster-evaluation/code-walk.md` for the revised publication and roster seams.

## 4. The in-generator gates

The choke point is the *last* check, not the only one. Under the live flag the generators
also gate, so an impossible floor starves the deck rather than being filtered afterwards:

| Path | File:line | Note |
|---|---|---|
| v2 pair candidate loop | `trade_service.py:7078` | inside `_consider`, after `_fairness` |
| v2 gap sweetener re-gate | `trade_service.py:7218` | inside `_gap_extra_ok` |
| v3 candidate loop | `trade_optimizer.py:632` | after `_fairness_v3` |
| v3 §3.4 sweetener re-gate | `trade_optimizer.py:730` | on the sweetened package |
| v3 gap sweetener re-gate | `trade_optimizer.py:769` | inside `_gap_extra_ok` |

Both sweetener sites re-ask **because the package changed** — a pre-mutation verdict is
void, and a sweetener is allowed to move the consensus ratio, which is exactly the
quantity the policy gates on.

## 5. Why each named bypass is closed

| Path | Why it cannot bypass |
|---|---|
| **Range overlap** | `_fairness` / `_fairness_v3` can admit a card whose *point* ratio is under the bar when the two value intervals overlap. The evaluator re-judges the point ratio against `effective_floor` immediately after, so overlap can no longer rescue a market-imbalanced trade. Pinned by `test_trade_policy.py::test_uncertainty_can_never_rescue_a_point_ratio_below_the_hard_floor`. |
| **Relaxed fallback** | `_relaxed_targeted_pass` lowers `fairness_threshold` and overrides `fairness_floor_divergence`. Under the policy neither knob is read as a gate, and the lowered request is composed with `max`, so relaxation cannot descend past the policy floor. Pinned by `test_trade_policy_wiring.py::test_the_relaxed_fallback_cannot_reach_below_the_policy_floor`. |
| **Sweeteners (both)** | Re-gated at the two sites above, and again at the choke point. |
| **Swap / remove / edit returning a card to the deck** | Those paths rebuild the card and it re-enters `final_cards`; the choke point runs on the rebuilt package. |
| **Likes-you injection** | Injected cards are appended to `final_cards` before the choke point. They are *not* exempt: an injected mirror still has to clear the floor. `source_like_impression_id` records why it was there. |
| **Wildcard / exploration** | Inserted into `final_cards` above the choke point. |
| **Weekly replenishment** | Produced by `_run_trade_job` itself (the cron kickoff sets `job["source"]`), so it is the same code path and the same choke point. |
| **`gen_v2` (arm C)** | Takes no `fairness_threshold` — its bar is the `gen2_*` stack — so it has no in-loop gate. Its cards pass the choke point like every other arm's. The brief specifies exactly this: the treatment applies the evaluator to *each arm's output*. |

## 6. The flag-off byte-identity argument

Three independent legs, so a single mistake cannot silently break all of them:

1. **The generators allocate nothing.** `trade_policy.make_pair_evaluator` returns `None`
   when the flag is off (`trade_policy.py`, first statement). `trade_service.py:6821` and
   `trade_optimizer.py:353` therefore hold `None`, and each gate is a single
   `if _policy_eval is not None` that short-circuits. The legacy
   `fairness_threshold = min(..., fairness_floor_divergence)` composition still runs,
   guarded by `if not _policy_on`.
2. **The choke point returns early.** Two boolean reads, then the input list.
3. **The impression writer assigns nothing.** The stamp block in
   `_log_deck_signal_impressions` is gated on `if policy_results:` — a per-JOB condition,
   not per card, following the same every-row rule the bake-off block already uses,
   because `save_deck_impressions` inserts with `executemany` and compiles the statement
   from the first row's keys.

**Pinned by:** `test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden`
(the committed pre-bake-off golden, with the four new columns asserted NULL in
`NEW_COLUMNS`), `test_breaker_seam.py::test_flag_off_features_json_byte_identical`, and
`test_trade_policy_wiring.py::test_flag_off_produces_no_policy_state_at_all` +
`::test_telemetry_on_does_not_change_which_cards_are_served`.

**Sabotage-proved:** `test_trade_policy_wiring.py::test_removing_the_choke_point_would_be_caught`
neuters `_evaluate_deck_policy` to a pass-through and asserts the below-floor cards come
back and the shadow log empties. If that test can be deleted with the suite still green,
the choke point is not load-bearing.

## 7. Symmetric confidence — the plumbing

| Step | Where |
|---|---|
| Persist | `database.upsert_member_rankings` writes `comparison_count` / `confidence_weight` / `confidence_source`; the weight is computed by `trade_policy.confidence_weight_for` so write and read cannot drift. |
| Provenance | `server._ranking_confidence` (`server.py:5767`) decides **per player**: in `placement_bands()` ⇒ `explicit`, else the live vote count; the copy-from-format publish stamps the whole snapshot `cross_format`. Threaded into all seven `upsert_member_rankings` call sites. |
| Load | `database.load_member_rankings` returns the two maps plus `confidence_source` and `board_updated_at` as **additive keys** — every pre-existing consumer reads `username` / `elo_ratings` and is unaffected. |
| Carry | `server._run_trade_job` sets `LeagueMember.comparison_counts` / `.confidence_weights` / `.confidence_source` / `.board_updated_at` **only on the `has_rankings=True` branch** — a member whose Elo is seeded noise must not be handed a map that dresses that noise as evidence. |
| Apply | `trade_policy.shrink_board` — the identical function for both boards. Deliberately not `_shrink_user_elo`, which returns the board **raw** when confidence is None and skips shrinkage entirely at `user_elo_shrink = 0`; both would let the floor's confidence discount buy relief from evidence the values never used. |

## 8. Where the value bases deliberately differ — the open item

The policy prices personal values as `elo_to_value(effective_elo)`. The generators' own
`min_side_surplus` gate prices them as **marginal (over-replacement)** values when
`trade.marginal_value` is on, which it is in production.

That is a real, load-bearing divergence, and it is why two-sided gain is a **Conviction**
requirement rather than a blanket veto (`trade_policy.py`, the verdict block): a Core
card is market-plausible on its own terms, and applying the policy's basis as a second
universal gate would silently re-litigate every card the generator already cleared under
a definition the generator does not use. The first draft of this change did apply it
universally, and the wiring fixture caught it by emptying the deck.

The consequence to watch in the live phase: Conviction supply depends on cards showing
positive two-sided gain on **raw** confidence-shrunk boards, which is a stricter test
than the marginal one. Logged as `OPEN_QUESTIONS.md` Q-038.

## 9. One consensus definition

`trade_service.make_consensus_value_fn` is now the single accessor. v2's `_vs`
(`trade_service.py`), v3's `_sv` (`trade_optimizer.py`), `trade_gen_v2.cval` and
`trade_policy.compute_market_ratio` all build from it, and the body is byte-identical to
what each of the three previously had, memoization included. This is what makes
"finder and calculator consensus package values remain identical" true by construction
rather than by three mirrored copies each carrying a comment telling the next reader to
keep them in sync. Pinned by `test_trade_policy.py::test_the_policy_prices_consensus_with_the_calculators_own_function`
and `::test_all_four_consensus_accessors_are_one_function`.
