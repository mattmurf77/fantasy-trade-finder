# Tracking-plan addendum — Max PF moves

**Date:** 2026-11-12 · **Status:** adopted with the registration commit on `feat/max-pf-moves` (registered in the same squash-merge as the app's emitters)
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** [../../plans/league-projections/max-pf-trade-away/contract.md](../../plans/league-projections/max-pf-trade-away/contract.md) §9 · flag `league.max_pf_moves` · D-258
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`, and the `finder_target_pinned.source` comment) and `backend/analytics_queries.py` (`NON_INTENT_EVENTS`). **Not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS`. Pinned by `backend/tests/test_maxpf_moves_analytics.py`.

Mobile only, all on the `Standings` screen, all from the user's own team card. No player id or name in any prop.

## The events

| Event | Class | Fires when | Props (allowed values) |
|---|---|---|---|
| `maxpf_moves_viewed` (new) | **non-intent** (impression on a read-only page) | the Max PF moves section body becomes visible: on render when it starts open, or on the tap that opens it; once per opening of the card | `state` ∈ `ready` \| `no_moves` \| `unavailable` \| `no_miss` \| `draft_order_not_maxpf` \| `after_trade_deadline` \| `season_over` (the server's `max_pf_moves.state`); `n_moves` int ≥ 0 (rows listed); `band` ∈ `jets` \| `rebuilder` \| `contender` \| `championship` \| `none` (the server's `baseline.playoff_band`) |
| `maxpf_move_expanded` (new) | intent | a listed row is opened | `position` (the row's position string); `rank` 1..8 |
| `draft_order_rule_answered` (new) | intent | the draft-order POST returns 200 | `answer` ∈ `maxpf_lowest_first` \| `reverse_standings` \| `lottery_or_other` \| `not_sure`; `source` ∈ `first_ask` \| `change` |
| `finder_target_pinned` (existing) | intent | "Find trades for [player]" is tapped | `side` = `give`; `source` = `maxpf_moves` (new value) |

`band` here is the playoff-chance band from the outlook classifier, not `home_tile_tapped.band` (a per-position seller / buyer / mid band).

## Questions they answer

- How many users with a list open it, by playoff band (`maxpf_moves_viewed` by `band`, `state`).
- Whether a listed move leads to a search (`maxpf_move_expanded` → `finder_target_pinned{source: maxpf_moves}` → `find_trades_tapped`, which keeps its own sources; the hand-off does not auto-run).
- How leagues answer the draft-order question, and how often the list is hidden because of it.
