# Tracking-plan addendum — Roster-first setup for Find a Trade

**Date:** 2026-11-10 · **Status:** adopted with the mobile build commit on `feat/roster-setup-mobile` (all six names registered in the same commit as their emitters)
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** [../../plans/roster-first-trade-setup/analytics.md](../../plans/roster-first-trade-setup/analytics.md) (the spec; this file is its registration record) · flag `trades.roster_setup`
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`, and the `prompt_shown.surface` enum comment) and `backend/analytics_queries.py` (`NON_INTENT_EVENTS`). **Not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS`. Pinned by `backend/tests/test_analytics_taxonomy_roster_setup.py` and `mobile/tests/check-roster-setup.js`.

The taxonomy is default-deny: an unregistered client event is counted and dropped at ingest behind a 200, and an unregistered prop is stripped while the response still says `dropped: 0`. This addendum is the precondition `analytics_taxonomy.py`'s docstring demands.

Mobile only. The web client has no Trade DNA parity, so the step is not built there (scope.md §3 waiver).

## The events

All fire through `track(name, props, screen)` in `mobile/src/api/events.ts`. Screen is `RosterSetup` for the screen's own events and `Trades` for the TradesHome card and the Trade DNA row.

| Event | Class | Fires when | Props |
|---|---|---|---|
| `roster_setup_shown` | **non-intent** (impression) | the setup screen's first render with a roster, once per entry | `league_id`, `entry`, `roster_size`, `pick_count`, `prefilled_count` |
| `roster_setup_toggles_done` | intent | **Continue** on Step 1 | `league_id`, `entry`, `move_count`, `keep_count`, `open_count`, `pick_move_count`, `pick_keep_count`, `changed_count`, `duration_ms` |
| `roster_setup_rank_saved` | intent | one position's `POST /api/rankings/reorder` returned 2xx (never on failure, never for a position with no taps) | `league_id`, `position`, `players_ranked`, `players_total` |
| `roster_setup_completed` | intent | the done state renders | `league_id`, `entry`, `ranked_positions`, `changed`, `duration_ms` |
| `roster_setup_skipped` | **non-intent** (terminator) | **Skip for now** / **Skip to trades** on Step 1, or Back on Step 1 or Step 2 | `league_id`, `entry`, `stage` |
| `roster_setup_prompt_tapped` | intent | a return entry point is tapped | `league_id`, `surface`, `new_asset_count` |

**Closed enums.**
`entry`: `first_pass` · `roster_changed` · `manual_dna` · `entry_card`. `first_pass` is the automatic entry: the setup is pushed when the user's first declined (passed) Find a Trade suggestion in a league has committed (operator amendment, 2026-11-10; it replaced a push on TradesHome focus before anything shipped).
`stage`: `toggles` · `rank`.
`surface` (on `roster_setup_prompt_tapped`): `entry_card` · `roster_changed_card` · `dna_row`.
`position`: `QB` · `RB` · `WR` · `TE` — a core position, never a device platform.

**Counts.** `roster_size` counts players (QB/RB/WR/TE), `pick_count` owned picks, `prefilled_count` assets already tagged Move or Keep when the screen opened. The `*_count` props on `roster_setup_toggles_done` are over the whole roster, also on the filtered roster-changed entry. `changed_count` counts assets whose state differs from the prefill. `players_ranked` is the number of chips tapped, `players_total` the caller's board-ranked roster players at that position. `ranked_positions` is 0–4. `new_asset_count` is 0 except on `roster_changed_card`. `duration_ms` runs from screen open.

No player id, name, free text or device platform rides in any prop.

## Existing events reused

- **`prompt_shown {surface}`** gains the value `roster_setup_card` for the TradesHome return card's full-card impression (once per league, card kind and session). An enum widening, not a new prop: the card is fired directly, not through the interrupt coordinator, so `InterruptSurface` in `useInterruptCoordinator.ts` is unchanged.
- **`asset_pref_added` / `asset_pref_removed`** (server) stay the authoritative per-tap write log; a Move tap arrives as `list_type: 'trade_block'`. There is no client per-tap event, so nothing double-counts.
- **`ranking_reorder`** (server) still fires for each rank save. The step sends **no `via`**, so `quickrank_completed` does not fire and the Quick Rank funnel is not inflated.

## Why two are non-intent

`INTENT_EVENTS` is derived by subtraction. `roster_setup_shown` fires on the `first_pass` entry whether or not the user asked for the setup, so counted as intent it would mint a user-day for every new Find a Trade user and step-change DAU on the ship date (the `team_review_beat_viewed` class). `roster_setup_skipped` is a dismissal that terminates an entry (the `quickset_abandoned` / `team_review_exited` class).

## Not changed

`FUNNEL_CRITICAL`, `_RANK_STREAK_EVENTS`, and the `board_started` funnel rung. `roster_setup_rank_saved` does not count as starting a board; the server's `ranking_reorder` already reaches the user-level rollups.
