# Tracking-plan addendum — Roster setup: one-page tier placement

**Date:** 2026-11-11 · **Status:** adopted with the build on `feat/roster-setup-tier-rank` (the name is registered in the same PR as its emitter)
**Parent:** [2026-11-10-roster-setup-events.md](2026-11-10-roster-setup-events.md) (the setup's six events) · [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** [../../plans/roster-first-trade-setup/scope-tier-rank.md](../../plans/roster-first-trade-setup/scope-tier-rank.md) §4 · flag `trades.roster_tier_rank`
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`, the `roster_setup_skipped.stage` enum comment). **Not** `NON_INTENT_EVENTS`, **not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS`. Pinned by `backend/tests/test_analytics_taxonomy_roster_setup.py`

Mobile only, as the parent addendum.

## The new event

| Event | Class | Fires when | Props |
|---|---|---|---|
| `roster_setup_tiers_saved` | intent | every per-position `POST /api/tiers/save` from one Save tap has returned 2xx, and at least one player moved. Never on a partial failure, never when nothing moved | `league_id`, `entry`, `moved_count`, `moved_up_count`, `moved_down_count`, `players_total`, `positions_saved`, `duration_ms` |

**Counts.** `moved_count` is players whose tier on the page differs from the tier they opened in; `moved_up_count` + `moved_down_count` = `moved_count`. `players_total` is the on-board players on the page (greyed off-board players are not counted). `positions_saved` is how many positions were posted (1 to 4). `duration_ms` runs from the page's first render to the last successful save.

`entry` is the parent addendum's closed enum, unchanged. No player id, name, tier key or free text rides in any prop.

## Existing events widened

- **`roster_setup_skipped {stage}`** gains the value `tiers` (Skip or Back on the tier page). `stage` is now `toggles` · `rank` · `tiers`.
- **`tier_save` (server) `{via}`** gains the value `roster_setup`, once per position posted. The whitelist lives in `save_tiers_route`.
- **`roster_setup_rank_saved`** still fires only on the per-position step, which is now the flag-off fallback.

## The question it answers

Do users who re-tier their own players, especially upward, pass fewer cards for "giving too much value" in the following 7 days? Join `roster_setup_tiers_saved.moved_up_count` to `value_giving` pass reasons, read stratified as in [analytics.md](../../plans/roster-first-trade-setup/analytics.md) §4.
