# 2026-08-21 — triple-ship sweep (Receipts, arm-C sweetener, per-slot pricing)

| tip sha | branch | merged as |
|---|---|---|
| `21ad574` | `feat/receipts` | squash PR #165 → `93f1fd0` |
| `4540679` | `ship/armc-sweetener` | squash PR #166 → `3df71c0` |
| (merge tip) | `feat/slot-pricing-unconditional` | squash PR #167 → `3192d13` |
| `9e4469f` | `feat/gap-sweetener-arm-c` (side-session original; content cherry-picked as b5e2f54 → #166) | superseded by #166 |

Verification by content markers on main: `receipts_service`/`receipts_grades` (165), `close_value_gap` in trade_gen_v2 path (166), `market_pick_slot_value`/`priced_pool_value` (167). CI green on each PR.
Remote branches deleted 2026-08-21. Recovery: `git branch <name> <sha>`.
