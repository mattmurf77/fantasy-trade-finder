# #189 — Acquire/trade-away should always present offers — status

**Status: built (backend field shipped; client labeling belongs to the client owner)** · 2026-07-25 · branch `teardown-remediation` worktree

Operator: "When trading away or trading for a player using the acquire or trade features, I expect that some trade offers are always presented."

## Behavior

`TradeService.generate_trades` (v2 engine path): when a **targeted** job — `pinned_give_players`, `pinned_receive_players`, `acquire_positions` and/or `trade_away_positions` — produces **zero** cards under the normal gates, `_relaxed_targeted_pass` reruns generation with staged, labeled relaxation. First non-empty stage wins:

1. **`fairness_band`** — effective fairness threshold (the caller's request AND `fairness_floor_divergence`) drops to `min(caller's threshold, relaxed_fairness_threshold)` (default 0.55). Never tightens: a caller already below the knob keeps their own looser bar.
2. **`fairness_band+surplus_floor`** — additionally `min_side_surplus` / `min_side_surplus_marginal` drop to `relaxed_surplus_floor` (default 0.0 — both boards must still show NON-NEGATIVE surplus; mutual gain is floored, never inverted).

Never relaxed (safety, not taste): the #108 user-board gates (`user_gain_epsilon`, `fit_premium_1for1` / `user_gain_ok_1for1`), untouchables, `not_interested` exclusions, past-decision dedup (already-swiped trades never resurface as "relaxed").

Mechanics: overrides ride a new **thread-local** `_cfg` overlay (`trade_service._cfg_override`; `_c()` reads it, and `trade_optimizer` imports `_c`, so v3 obeys it too) — concurrent jobs on other threads are untouched. The relaxed pass never re-streams progress (`on_opponent_done=None`).

Honest labeling: every relaxed card carries `relaxed=True` + `relaxed_reason` (`"fairness_band"` | `"fairness_band+surplus_floor"`), serialized **additively** by `trade_card_to_dict` (ordinary card payloads byte-identical). Suggested client copy: "Stretch idea — outside your usual fairness band" — client rendering is another agent's scope; this item ships the field + docs.

No feature flag: the behavior only activates on otherwise-empty targeted results; normal jobs and non-empty targeted jobs are byte-identical (verified by test). Knobs `relaxed_fairness_threshold` / `relaxed_surplus_floor` are DB-seeded `model_config` keys (live-tunable via `PUT /api/admin/config/<key>`). Legacy (flag-off) engine path is untouched.

## Files

- `backend/trade_service.py` — `_cfg_override` thread-local overlay, `_DEFAULT_CFG` knobs, `TradeCard.relaxed`/`relaxed_reason`, fallback wiring in `generate_trades`, `_relaxed_targeted_pass`.
- `backend/server.py` — `trade_card_to_dict` additive serialization.
- `backend/database.py` — `_MODEL_CONFIG_DEFAULTS` seeds for the two knobs.
- Docs: `docs/api-reference.md` (card payload), `docs/config-reference.md` (knobs), `docs/glossary.md` ("Relaxed card").

## Tests

`backend/tests/test_relaxed_fallback.py` (8): empty targeted job returns ≥1 relaxed card with the field set (`test_empty_targeted_job_returns_relaxed_cards`); non-targeted empty stays empty; targeted-with-normal-cards never invokes the pass (byte-identical); stage order + knob values + no-callback verified (`test_stage_order_and_reason_stamping`, incl. no override leak after the pass); relaxation never tightens a looser caller threshold; `user_gain_epsilon` and untouchables hold through both stages; serialization additive both ways.

Full backend suite: **1105 passed, 1 skipped**.
