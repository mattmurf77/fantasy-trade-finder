# Tracking-plan addendum — Playoff targets

**Date:** 2026-11-14 · **Status:** registered on `feat/playoff-targets` in the same commit as the app's emitters; the feature is behind flag `league.playoff_targets`, off, so nothing fires yet
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** [../../plans/league-projections/playoff-targets/contract.md](../../plans/league-projections/playoff-targets/contract.md) §9 · D-264
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`, and the `finder_target_pinned.source` comment) and `backend/analytics_queries.py` (`NON_INTENT_EVENTS`). **Not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS`. Pinned by `backend/tests/test_playoff_targets_analytics.py` and `mobile/tests/check-playoff-targets.js` (group H).

Mobile only, all on the `Standings` screen, all from the user's own team card. No player id, player name or team name in any prop.

## The events

| Event | Class | Fires when | Props (allowed values) |
|---|---|---|---|
| `playoff_targets_viewed` (new) | **non-intent** (impression on a read-only page) | the Playoff targets section body becomes visible: on render when it starts open, or on the tap that opens it; once per opening of the card | `state` ∈ `ready` \| `no_targets` \| `no_sellers` \| `near_certain` \| `clinched` \| `eliminated` \| `after_trade_deadline` \| `season_over` \| `unavailable` (the server's `playoff_targets.state`); `n_listed` int ≥ 0 (rows listed); `any_pass` bool (a listed row gains at least a percentage point); `n_sellers` int ≥ 0 (teams selling now, the server's `eligible_teams`); `band` ∈ `jets` \| `rebuilder` \| `contender` \| `championship` \| `none` (the server's `baseline.playoff_band`) |
| `playoff_target_expanded` (new) | intent | a listed row is opened | `position` (the row's position string); `rank` 1..8 |
| `finder_target_pinned` (existing) | intent | "Find trades for [player]" is tapped | `side` = `receive`; `source` = `playoff_targets` (new value) |

## Questions they answer

- How many users with a list open it, by playoff band, and how often the section has nothing to list (`playoff_targets_viewed` by `band`, `state`, `n_sellers`).
- Whether a listed target leads to a search (`playoff_target_expanded` → `finder_target_pinned{source: playoff_targets}` → `find_trades_tapped`, which keeps its own sources; the hand-off does not auto-run).
- With `maxpf_moves_viewed`: which of the two sections on the card a user opens, by band.
