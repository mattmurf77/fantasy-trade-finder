# Analytics spec — Roster-first setup

**Date:** 2026-11-10 · **Status:** spec only. Nothing is registered and nothing is emitted yet.
**Checked against:** `backend/analytics_taxonomy.py` and `backend/analytics_queries.py` on `origin/main` `d6fc338f`.
**Rule followed:** register in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` and classify in `analytics_queries.NON_INTENT_EVENTS` **in the same commit as the emitter** (root `CLAUDE.md` § Common tasks; the NULL-`platform` incident). A tracking-plan addendum under `docs/business/analytics/` must land first, because `CLIENT_EVENT_PROPS` is default-deny and new props require it (`analytics_taxonomy.py:1103-1116`).

---

## Table of Contents
- [1. Why existing events are not enough](#1-why-existing-events-are-not-enough)
- [2. New events](#2-new-events)
- [3. Taxonomy checks](#3-taxonomy-checks)
- [4. Questions this answers](#4-questions-this-answers)

---

## 1. Why existing events are not enough

| Existing event | What it gives us | Why it falls short |
|---|---|---|
| `asset_pref_added` / `asset_pref_removed` (server, `server.py:28328-28334`, registered `analytics_taxonomy.py:905`) | One row per tag write, props `{player_id, list_type}` | No `source`, so a setup tap can't be told from a deck lock or a DNA-sheet edit. It also can't see "shown but untouched", which is the main adoption question. **Kept as is**: it remains the authoritative write log, and `list_type='trade_block'` arrives through it with no change. |
| `ranking_reorder` (server, `server.py:18124-18136`) | `{moves_count}` per reorder | It fires for Manual Ranks and Quick Rank too, and carries no position or source. Kept as is. |
| `quickrank_completed` (server, fires only on `via:'quickrank'`, `server.py:18142-18155`) | Quick Rank funnel | The step **deliberately does not send `via:'quickrank'`**, so the Quick Rank funnel (`analytics_queries.py:475-488`) is not inflated by a different flow. |
| `untouchable_toggled {marked}` (client, `analytics_taxonomy.py:1694`) | The Matches long-press toggle | Different surface, two states only. Reusing it would merge two funnels. |
| `team_review_*` (client) | Closest precedent in shape | Different flow. Copied as a pattern (league_id prop, NON_INTENT split), not reused. |

## 2. New events

All of these are client-fired from mobile, through `track(name, props, 'RosterSetup')` (`mobile/src/api/events`). Props are IDs, counts and closed enums only, with no names or free text.

| Event | Properties (closed enums in brackets) | Fires when | Intent class |
|---|---|---|---|
| `roster_setup_shown` | `league_id`; `entry` [`first_use` \| `roster_changed` \| `manual_dna` \| `entry_card`]; `roster_size` (players); `pick_count`; `prefilled_count` (assets already tagged) | The screen's first render for one entry. Once per entry, not per re-render. | **NON_INTENT**: an impression the user did not ask for on `first_use` (the `team_review_beat_viewed` class) |
| `roster_setup_toggles_done` | `league_id`; `entry`; `move_count`; `keep_count`; `open_count`; `pick_move_count`; `pick_keep_count`; `changed_count` (assets whose state differs from the prefill); `duration_ms` | The user leaves Step 1 through **Continue** | INTENT |
| `roster_setup_rank_saved` | `league_id`; `position` [`QB` \| `RB` \| `WR` \| `TE`]; `players_ranked` (explicitly tapped); `players_total` (roster players at the position) | One position's `POST /api/rankings/reorder` returns 2xx. Not fired on failure. | INTENT |
| `roster_setup_completed` | `league_id`; `entry`; `ranked_positions` (count 0–4); `changed` (bool: any tag or rank changed); `duration_ms` (screen open → done) | The done state renders | INTENT |
| `roster_setup_skipped` | `league_id`; `entry`; `stage` [`toggles` \| `rank`] | **Skip for now**, or a back gesture, on either step. The terminator for a non-completing entry. | **NON_INTENT**: a dismissal/terminator (the `quickset_abandoned` / `team_review_exited` class) |
| `roster_setup_prompt_tapped` | `league_id`; `surface` [`entry_card` \| `roster_changed_card` \| `dna_row`]; `new_asset_count` (0 except on `roster_changed_card`) | The user taps a return entry point | INTENT |

**Property notes:**

- `position` is a **core position**, never a device platform. Write the same comment `quickset_started` carries (`analytics_taxonomy.py:1739-1742`).
- `league_id` as a prop follows `team_review_opened` (`analytics_taxonomy.py:1727`).
- No per-tap client event. Per-asset writes are already logged server-side by `asset_pref_added/removed`, and a client twin would double-count and look like extra intent.
- Re-prompt and entry-card **impressions** reuse the existing `prompt_shown {surface}` event (`analytics_taxonomy.py:1667`). They add `roster_setup_card` to its `surface` enum, which is an enum widening and not a new event, the same move SPEC §2 made for decline `detail` (`analytics_taxonomy.py:1745-1760`). That needs a matching addition to the mobile `InterruptSurface` enum (`useInterruptCoordinator.ts`) only if the card goes through the interrupt coordinator. Otherwise fire `prompt_shown` directly.

## 3. Taxonomy checks

| Check | Result |
|---|---|
| Name collision with `ALLOWED_CLIENT_EVENTS` or `SERVER_FIRED_EVENTS` | None. `git grep -n "roster_setup" -- backend/` returns nothing. The module's import-time disjointness check (`analytics_taxonomy.py` header) passes because all six are client-only. |
| Prefix convention | `<flow>_<verb>` like `quickset_*` and `team_review_*`. |
| `FUNNEL_CRITICAL` | Not added. Only auth/first-open events are in it (`analytics_taxonomy.py:1094-1099`). |
| NON_INTENT classification | `roster_setup_shown` and `roster_setup_skipped` go in `analytics_queries.NON_INTENT_EVENTS` (next to `team_review_beat_viewed` / `team_review_exited`, `analytics_queries.py:105-106`). INTENT is a deny-list, so without this a first-use impression would mint a user-day for every new Find a Trade user and step-change DAU on the ship date. |
| Rank-class streak events (`_RANK_STREAK_EVENTS`) | Not touched. The server's `ranking_reorder` already counts for streaks. |
| `board_started` funnel rung (`analytics_queries.py:475-476`) | Not changed in v1. Decide at build whether `roster_setup_rank_saved` should count as starting a board. Recommendation: no. `ranking_reorder` already reaches the user-level rollups, and adding it would change a historic funnel. |

## 4. Questions this answers

1. **Adoption:** of users `shown` on `first_use`, what share reach `toggles_done`, `rank_saved` (any) and `completed`? What share `skipped`, and at which `stage`?
2. **Effort:** the `duration_ms` distribution, and `players_ranked / players_total` per position. Do users stop after RB?
3. **Data yield:** the per-user `move_count` and `keep_count` distribution. This is the first per-player give-side preference the app has ever collected. Watch for `keep_count` near roster size, which is the starvation risk.
4. **Outcome (the point):** deck like rate and the `value_giving` pass-reason share over 7 days after `completed`, against users who `skipped`. Join `user_events` on `user_id, league_id`. Read it as stratified, not causal: completers self-select. The acceptance eval's "≥10 distinct responding users" bar applies before any claim.
5. **Counterparty coverage:** share of served cards whose counterparty has an `explicit`-source board or any `trade_block` tag, before and after rollout. This needs no new event; it reads the owner evidence's `counterparty_source`.
