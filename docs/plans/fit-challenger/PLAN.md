# Build plan — Fit challenger

Order is the tickets in [PRD.md](PRD.md) §8. Do not start F5 until F3’s scores exist; F1 can land dark.

```text
F1 knockouts (wrap live K2–K7 + K1 + K3-everywhere)
        │
        ▼
F2 enumerator (union pool, 1-for-1 then expand, caps)
        │
        ▼
F3 dual 0–100 scorer + payload
        │
        ├─► F4 post-score filters
        ├─► F6 tests (parallel once F1 fixtures exist)
        └─► F5 bake-off arm `fit` (roster default OFF)
                │
                ▼
         dry run → operator sets ms bar → bakeoff_include_fit=1
```

## Implementation notes (binding)

1. **New file** `backend/trade_gen_fit.py`. Import live helpers (`overpay_ok`, `pos_net_ok`, `pick_gap_ok`, `need_gate_ok`, `pick_swap_ok`, `package_value_v2`, `_feasible_after`, `elo_to_value`). Do not copy their bodies.
2. **Do not** add a branch in `_generate_trades_impl`. Bake-off calls `generate_league_suggestions` like `trade_gen_v2`.
3. **Do not** `_cfg_override` live knobs to fake this arm. Landability-challenger is that pattern; this is a different generator.
4. Enumeration **must** implement `fit_max_packages_per_pair` before any real-league run.
5. `TradeCard.composite_score` = aggregate 0–200. Keep `fairness_score` as the live consensus ratio so existing UI doesn’t break.
6. `basis`: `divergence` iff both members `has_rankings`, else `consensus`.
7. Prefs: generate first, filter in F4. Unit test that an untouchable id is in `enumerated` and absent from the returned list.

## Suggested PR cuts

| PR | Contains | Merge when |
|---|---|---|
| 1 | F1 + F6 skeleton (knockout unit tests only) | tests green, no bake-off hook |
| 2 | F2 + F3 + F6 scorer tests | fixture pair scores frozen |
| 3 | F4 + F5 + dry-run TEST_LEDGER | operator yes on rostering |

## Out of this build

Dual R5, likes-you, client 0–100 meters, PPG, organic serving, changing G6 math.
