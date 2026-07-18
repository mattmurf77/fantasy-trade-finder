# #147 — Trade-block engine hook (`block_boost`)

Wired 2026-07-18, branch `trade-engine-v2`. This is the trade-generation
consumer of the FB-147 trade-block signal (import + display shipped 2026-07-17;
see [status.md](status.md)). Operator-approved scope: **SOFT boost, acquire side
only.**

## What it does

A trade card whose **acquire side** (`receive_player_ids`) holds ≥1 player the
**counterparty** flagged "on the block" in Sleeper is a more landable deal, so it
earns a bounded composite bump:

```
composite_score *= 1 + block_boost_weight        # flat, regardless of count
```

The bump only reorders trades the engine already deemed acceptable — it is
applied **after every gate** (fairness, #108 user-gain, surplus, junk-filler),
exactly like FB-96 `need_fit`. It can never rescue a gated trade.

Out of scope (operator's call): the **give side** and the **user's own** flagged
players. Only "a player the opponent put on the block, that I would acquire"
boosts.

## Mirror of `need_fit` (FB-96)

The design deliberately clones the `need_fit` pattern so the two behave
identically w.r.t. gates and serialization:

| Aspect | `need_fit` (FB-96) | `block_boost` (FB-147) |
|---|---|---|
| Flag | `trade.need_fit` | `trade.block_boost` (default **true**) |
| Knob (`model_config`) | `need_fit_weight` (0.15) | `block_boost_weight` (0.15) |
| Where applied | `_generate_trades_v2` per-opponent post-pass, after gates | same block, immediately after `need_fit` |
| Coverage | divergence + v3 + consensus (orchestrator-level) | same — identical placement |
| Formula | `× (1 + w·(fit − 0.5))` | `× (1 + w)` when acquire side is blocked |
| Card field | `need_fit` (serialized) | `block_boosted` (in-process; **not** separately serialized) |
| Off / knob 0 | composite unchanged | composite **byte-identical**, nothing stamped |

Because the boost is applied in the orchestrator against the `cards` a generator
returns — not inside any one generator — it covers the **v2 pair, v3 optimizer,
and consensus** paths with no edit to `trade_optimizer.py`, the same way
`need_fit` does.

## Wiring locations (`backend/trade_service.py`)

1. **Signal loader** — `_load_on_block_by_uid(league_id)` (module function next to
   `need_fit_score`). Reads `database.load_trade_block(league_id)` and groups the
   rows into `{flagging_owner_user_id: frozenset(player_ids)}`. Ownership was
   already validated at sync time (stale flags dropped in
   `trade_block_service.parse_trade_block`), so every id is genuinely on that
   owner's block. Any read failure → empty map → boost silently no-ops.

2. **Load once per generation** — near `_need_fit_on = FLAGS.trade_need_fit` at the
   top of `_generate_trades_v2`:
   ```python
   _block_boost_w = _c("block_boost_weight") if FLAGS.trade_block_boost else 0.0
   _on_block_by_uid = _load_on_block_by_uid(league_id) if _block_boost_w else {}
   ```
   Loaded once, like the untouchable set. Knob 0 ⇒ skip the DB read entirely.

3. **Apply per-opponent** — immediately after the `need_fit` application block, in
   the same per-opponent loop (so `member.user_id` is the counterparty):
   ```python
   if _block_boost_w:
       _blk = _on_block_by_uid.get(member.user_id)
       if _blk:
           for c in cards:
               if _blk.intersection(c.receive_player_ids):
                   c.block_boosted = True
                   c.composite_score = round(c.composite_score * (1.0 + _block_boost_w), 3)
   ```

## Why gates stay authoritative

The boost multiplies `composite_score` on the list of cards a generator **has
already returned**. A gated trade (fails fairness / user-gain / surplus) never
enters that list, so there is nothing to boost — the multiplier cannot resurrect
it. `block_boost` touches neither `fairness_score` nor `mismatch_score` nor any
gate threshold; it is purely an ordering nudge among survivors. Covered by
`test_block_boost_does_not_override_gate` (an unfair blocked-star grab stays dark
while a fair blocked trade is still boosted).

## Acquire-side-only correctness

`_on_block_by_uid` is keyed by the flagging **owner**, and the per-opponent apply
looks up `_on_block_by_uid.get(member.user_id)` — the counterparty. Since
`receive_player_ids` are by construction owned by that counterparty and the block
is ownership-validated, intersecting them is exactly "opponent-flagged players I
would acquire." A player the *user* flagged (give side) lives under the user's own
key, never the opponent's, so it can't boost. Covered by
`test_block_boost_give_side_not_boosted`.

## Serialization / inspectability

No new serialized field. The in-process `TradeCard.block_boosted` flag records
the boost for tests/QA, but client-side inspectability **reuses #147's existing
per-player `on_block` receive-row flag** (`server.trade_card_to_dict`, gated by
`sleeper.trade_block`). That flag is present exactly when the boost can fire —
the boost needs synced block data, which only exists when `sleeper.trade_block`
is on — so the acquire-side blocked asset already shows `on_block: true` on its
receive row. `server.py` was intentionally **not** touched (owned by a concurrent
thread; no duplication of the display signal).

## Byte-identity guarantees

- **Flag off** (`trade.block_boost` false) → `_block_boost_w = 0.0` → loader
  skipped, apply block skipped → composite unchanged, nothing stamped.
- **Knob 0** (`block_boost_weight = 0`) → same short-circuit → byte-identical.

Both pinned by `test_block_boost_flag_off_parity` and
`test_block_boost_knob_zero_byte_identical`.

## Config

- Flag `trade.block_boost` — `config/features.json` (+ `feature_flags.py`
  `FLAG_KEYS`, + `backend/tests/fixtures/flags/release.json` mirror). Default
  **true**: bounded, kill-switchable, acquire-side reorder only.
- Knob `block_boost_weight` — default `0.15` in both
  `trade_service._DEFAULT_CFG` and `database._MODEL_CONFIG_DEFAULTS` (live-tunable
  via `model_config`; 0 disables, byte-identical).

## Tests

`backend/tests/test_block_boost.py` (8 tests, all green):

1. `_load_on_block_by_uid` groups by flagging owner (str-coercion, blank-owner drop)
2. loader read failure → empty map (no-op, never breaks generation)
3. reorders a blocked-acquire card above its symmetric plain twin; stamps
   `block_boosted`; composite = `plain × (1 + w)`; fairness/mismatch untouched
4. flag-off parity (no stamp, composites tied)
5. knob-0 byte-identity (flag on, weight 0 → composites identical to flag-off)
6. give-side / non-counterparty flags never boost
7. gate authority — a gated (unfair) blocked-acquire trade stays dark
8. multi-blocked is flat — a card acquiring several blocked players gets one
   `(1 + w)` factor, not compounded or graded

## Files

- `backend/trade_service.py` — `_load_on_block_by_uid`, `TradeCard.block_boosted`,
  `block_boost_weight` in `_DEFAULT_CFG`, signal load + per-opponent apply in
  `_generate_trades_v2`
- `backend/database.py` — `block_boost_weight` in `_MODEL_CONFIG_DEFAULTS` (default only)
- `backend/feature_flags.py` + `config/features.json` +
  `backend/tests/fixtures/flags/release.json` — `trade.block_boost` flag
- `backend/tests/test_block_boost.py` — new tests
- docs: `config-reference.md`, `glossary.md`, `architecture.md`, this file + `status.md`

`trade_optimizer.py` and `server.py` were **not** touched — coverage comes from
the orchestrator-level placement, and the display signal is reused rather than
duplicated.
