# Tracking-plan addendum — Home hub (Direction D)

**Date:** 2026-10-10 · **Status:** adopted with the Phase 1 registration commit on `feat/home-hub` (both names registered before any emitter ships)
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** [../../plans/home-engagement/scope.md](../../plans/home-engagement/scope.md) §1 · flag `nav.home_hub`
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`) and `backend/analytics_queries.py` (`NON_INTENT_EVENTS`). **Not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS`. Pinned by `backend/tests/test_analytics_taxonomy_home_hub.py`.

The taxonomy is default-deny: an unregistered client event is counted and dropped at ingest behind a 200, and an unregistered prop is stripped while the response still says `dropped: 0`. This addendum is the precondition `analytics_taxonomy.py`'s docstring demands.

Mobile only. Web and the extension have no Home.

## The events

| Event | Screen | Class | Fires when | Props |
|---|---|---|---|---|
| `home_tile_tapped` | `Home` | **non-intent** (navigation, the `tab_selected` class) | any tap on a Home hub row, tile or button, before navigating | `tile`, and on `buy` / `sell` / `position_ranking` only: `position`, `band` |
| `standings_segment_changed` | `Standings` | **non-intent** (lens switch) | the user taps Current or Projected and the segment changes; never on mount | `segment` |

**`tile`** (closed): `outlook` · `standings` · `overall_rank` · `buy` · `sell` · `position_ranking` · `find_trade` · `rank` · `matches` · `trends` · `usage_rates` (added with Usage Trends, `usage_trends.enabled`) · `free_agents` · `link_league` · `retry`.
**`position`**: `QB` · `RB` · `WR` · `TE`. **`band`**: `seller` · `buyer` · `mid` — the user's own band at that position, so `band` + `tile` reads whether the suggested side was taken.
**`segment`**: `current` · `projected`.

No league id, team, player or device platform rides in any prop.

## Why both are non-intent

`INTENT_EVENTS` is derived by subtraction. Home is the **launch tab**, so a tile tap is often a session's first event; counted as intent it would turn every "open, tap, leave" into a user-day and step-change DAU on ship day. The destination's own events already carry intent: `league_candidate_pinned`, `find_trades_tapped`, `match_opened`. The Standings segment is a lens switch on a read-only page.

## Questions this answers, with events that already exist

- **Does Home move users into the buyers/sellers split?** `home_tile_tapped{tile: buy|sell, position: P}`, followed in the same session within 10 s by `league_pos_candidates_viewed{position: P, divider: shown}`. That is attribution by session sequence, with no new prop on the #300 exposure event (its emitter is pinned by `mobile/tests/check-analytics-300.js`).
- **Does it convert?** The same sessions reaching `league_candidate_pinned`, the #300 conversion moment, unchanged.
- **Is the suggested side the one taken?** `home_tile_tapped` where (`band: seller`, `tile: sell`) or (`band: buyer`, `tile: buy`).
- **What does Projected cost?** `standings_segment_changed{segment: projected}` counts the only path that runs `/api/league/outlook` from the Home flow.

`screen_viewed` (auto, `screen: Home` / `Standings`) and `tab_selected` (`tab: home`) keep their existing meanings.
