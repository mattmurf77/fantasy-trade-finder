# Reuse map: what already exists

**Date:** 2026-11-10. Every citation was verified against `origin/main` `d6fc338f`. Line numbers drift, so re-grep before building. This is the evidence behind [prd.md](prd.md) §4–§8.

---

## Table of Contents
- [1. Preferences: storage, routes, editors](#1-preferences-storage-routes-editors)
- [2. Is there a per-player "want to move"?](#2-is-there-a-per-player-want-to-move)
- [3. Quick Set / Quick Rank](#3-quick-set--quick-rank)
- [4. How the owner/bilateral constructors consume the inputs](#4-how-the-ownerbilateral-constructors-consume-the-inputs)
- [5. Draft picks as roster assets](#5-draft-picks-as-roster-assets)
- [6. First-use and regeneration plumbing](#6-first-use-and-regeneration-plumbing)

---

## 1. Preferences: storage, routes, editors

There are **two tables**, split by granularity.

**`league_preferences`** (`database.py:1780-1789`): one row per (user, league). It holds `team_outlook`, `acquire_positions` (Chasing), `trade_away_positions` (Shopping) and `avoid_positions` (#360), the last three as JSON arrays of `QB|RB|WR|TE|PICK`.
- Write: `upsert_league_preference` (`database.py:12575-12641`). Passing `None` leaves a field unchanged.
- Routes: `GET /api/league/preferences` (`server.py:28107-28177`, which also returns `inferred_outlook` and `position_needs/surplus`) and `POST /api/league/preferences` (`server.py:28180-28275`). `team_outlook` is **required** on POST, or the route returns 400. Every POST invalidates the league's trade jobs (`:28259-28262`).

**`asset_preferences`** (`database.py:1809-1817`, comment block `:1793-1806`): one row per (user, league, player), with `list_type ∈ {untouchable, target, not_interested}` (`ASSET_PREF_LISTS`, `database.py:12739`).
- The unique constraint gives **single membership**: `set_asset_preference` deletes any prior tag before inserting (`database.py:12804-12838`).
- `player_id` is an unvalidated `String`, so pick IDs fit.
- Loaders: `load_asset_preferences` (`:12742-12763`) and the bulk version (`:12766-12801`).
- Routes: `GET /api/league/asset-prefs` (`server.py:28278-28296`) and `POST /api/league/asset-prefs {player_id, list}` (`server.py:28299-28347`). `list:'none'` deletes. The POST records the server event `asset_pref_added/removed` and invalidates the league's jobs.

**Mobile editors:**
- `TradeDnaSheet.tsx`: outlook, Chasing/Shopping/Avoiding chips, plus the untouchables management layers (#173 list/remove at `:330-340`, #259 add-from-roster at `:342-390`, roster from `findMyRoster`). It shows **players only**; picks are not offered.
- `MatchesScreen.tsx:742-800` and `:1966-1970`: long-press "Mark untouchable".
- `PlayerContextMenu.tsx:111-132`: not-interested.
- `DraftRoomScreen.tsx:525`: target.
- `TeamReviewScreen`: writes `league_preferences` levers through the same POST (`mobile/src/screens/CLAUDE.md`, TeamReviewScreen row).

API client: `mobile/src/api/league.ts:67-115`. Its `AssetPrefs` type is at `:89-94`.

## 2. Is there a per-player "want to move"?

**No.**

- The only "move" preference is **position-level**: `trade_away_positions`.
- `targets` is a per-player list, but it is read **only on the receive side**:
  - owner `_asset_interest` applies it only when `direction > 0` (`trade_gen_owner.py:586-587`);
  - owner priority counts only `incoming` (`:549`);
  - bilateral `declared` applies it only when `direction > 0` (`trade_gen_bilateral.py:156-158`).
- `untouchable` is the give-side negative.

So per-player give-side positive intent does not exist anywhere in storage or the engine. Hence prd Q1: a new `trade_block` list type.

## 3. Quick Set / Quick Rank

| | Quick Set | Quick Rank |
|---|---|---|
| Screen | `mobile/src/screens/QuickSetTiersScreen.tsx` (997 lines) | `mobile/src/screens/QuickRankScreen.tsx` (709 lines) |
| What the user does | Per position, walks the 8 tiers top→bottom and taps the players that belong in each tier (`:63-81`) | Per position, walks each tier with 2+ players and taps them in rank order. Unclicked players are appended (`:52-69`) |
| Write | `POST /api/tiers/save` (`via:'quickset'`), which calls `apply_tiers` and composes with the existing board (HOLD semantics, D-160) | `POST /api/rankings/reorder {position, ordered_ids, via:'quickrank'}` (`server.py:18096`), which calls `apply_reorder` (`ranking_service.py:2096-2142`) |
| Value effect | **Absolute**: puts the player into a tier band | **Permutation**: the posted IDs swap their own Elos. Total value is unchanged |
| Provenance in the trade engine | Placed → `explicit` (`_ranking_confidence`, `server.py:11702-11749`; `placement_bands`, `ranking_service.py:631`) | Pinned via `_pin` → also `explicit` |
| Interactions | Up to 8 saves per position, plus taps | (tiers with 2+ players) saves, plus about N−1 taps |
| Events | `quickset_started` (client), `quickset_completed` (server) | `quickrank_completed` (server, only when `via:'quickrank'`, `server.py:18142-18155`) |

**Can it be scoped to an arbitrary list?**
- **Reorder: yes, already.** `apply_reorder` is subset-safe: it permutes exactly the posted IDs, pinned by `backend/tests/test_tier_occupancy.py::test_subset_reorder_within_tier_*`. It filters to `_pool(position)` and needs at least 2 valid IDs. A roster subset therefore works with no server change. Rookie scope uses the same property: the comment at `QuickRankScreen.tsx:96-103` says it needs no save change.
- **Tier save: yes, by generalisation.** `apply_tiers_subset` (`ranking_service.py:1927`) implements the merged-band rule for any `scope_pids`. Today it is reachable only through `scope=rookie` (`_requested_scope`, `server.py:15239-15250`). A `scope=roster` would be a new value, out of v1 (prd Q4).
- **Trio matchups:** `/api/trio` takes `scope=rookie` only (`server.py:15303-15340`). Not used here.

## 4. How the owner/bilateral constructors consume the inputs

Context assembly is `_owner_generation_context` (`server.py:21769`).
- Opponent boards come from `load_member_rankings`. Each member's `confidence_sources` defaults to `legacy` (`:21790-21800`).
- League prefs come in bulk. Per-member asset prefs are merged in when `trade.preference_lists` is on, which it is (`:21803-21812`).
- Viewer sources are `explicit` if placed, `votes` if compared, `legacy` if off seed, and `consensus` otherwise (`:21839-21846`).
- `avoid_positions` is flag-gated at the loader (`:21860`).

**Constructor reads:**

| Input | `trade_gen_owner.py` | `trade_gen_bilateral.py` |
|---|---|---|
| Personal vs market value per player | `_team`: personal only if source ∈ `_PERSONAL_SOURCES = {explicit, votes, cross_format, legacy}` (`:42`, `:278-293`), otherwise `consensus_fallback` | `known` set and per-player `direction` = personal vs market coordinate (`:57-95`); `has_personal_board` |
| `untouchables` | Reject unless returned at a market gain with a same-position incoming player; `PICK` is exempt from the position rule (`:534-541`) | Inherited |
| `targets` / `not_interested` | ±priority on incoming (`:549-550`); ±0.1 interest when `direction > 0` (`:586-587`) | ±0.3 declared when `direction > 0` (`:156-158`); `focal_in in targets` → `declared` path (`:183`) |
| `acquire_positions` / `trade_away_positions` | ±priority on both sides (`:545-548`); ±0.1 interest (`:584-585`) | ±0.15 declared (`:154-155`); focal `declared` (`:184-185`) |
| Outlook | Declared, else inferred (`:294-300`) | `outlook_source == "declared"` gates `declared_plan` (`:193`) |
| Evidence | `preferences` keys copied into the card's private evidence (`:397`) | `path` ∈ `explicit_selection \| personal_board \| declared_intent \| missing_board \| unfulfilled` (`:194-196`) |

Arm selection: `bakeoff_runner.owner_arm` (`bakeoff_runner.py:286-291`) returns `owner_v2_bilateral` iff `model_config.owner_bilateral_enabled == 1.0`. The live value is not inferred here; see the `docs/plans/README.md` owner-v2 row and G-076.

Legacy and likes-you paths read untouchables and not-interested as **hard filters** (`server.py:9056-9060`, `:9244-9246`). More asset-pref loads happen at `:13039`, `:21630`, `:22300`.

## 5. Draft picks as roster assets

- **Storage:** the `draft_picks` table (`database.py:1875-1910`) holds `pick_id`, season, round, current owner, original owner, `pool_value`, and `source` (platform or user-asserted, ADR-010). Read with `load_draft_picks` (`database.py:13747`), which returns platform rows by default.
- **Into the engine:** `_owned_pick_assets` (`server.py:20469-20556`) prices each pick at read time (D-144, `market_slots`) and keeps the **top `picks_pool_cap` per owner**. It wraps each kept pick as a `Player(position="PICK", id=pick_id)`. `_inject_owned_picks` (`:20575-20644`) then appends them to every roster and primes the Elo maps. Pick IDs are prefixed `{league_id}_` (`:20612-20620`).
- **The viewer's board for picks is consensus** (`:20638`, "user board: consensus for picks"; docstring `:20590-20592`, "picks aren't matchup-rankable"). A personal order over *owned* picks would have no effect without engine work (prd Q5). Generic pick rungs (`pick_values.GENERIC_PICK_SEEDS`) are in the rankable pool and anchor the Pick Anchor wizard. They are not the user's owned picks.
- **Client read:** `GET /api/league/picks` (`server.py:19920`) returns the caller's owned picks plus league pick state. ESPN leagues carry no ownership unless members assert it (#158 / ADR-010).
- **Tags on picks:** the asset-prefs route accepts any `player_id`, and the untouchable rule already handles `PICK`. No UI tags picks today.

## 6. First-use and regeneration plumbing

- **Server first-deck marker:** `load_deck_serve_history` decides `first_deck` (`server.py:13671-13677`), which is stamped on the job (`:3868-3869`) behind `deck.first_session`. It is server-side and per (user, league). It would be an alternative entry signal, but it marks the *deck*, not the setup, so it can't tell "skipped setup" from "never saw it".
- **Device first-run store:** `useOnboardingState.ts` (`ftf_onboarding_state_v1`) and the per-league `teamReviewCompletion.ts` (`mobile/src/state/CLAUDE.md`). The latter is the model for `rosterSetup.ts`.
- **Deck regen after a ranking change:** `onboardingBus.setPendingQuicksetRegen` → `TradesScreen` focus effect `consumePendingQuicksetRegen` + `consumeGuidedRegenSource` → forced job (`TradesScreen.tsx:6227-6260`). The `force` flag exists because the server cache key does not see board changes (`server.py:21291-21292`).
- **Inline prompt precedent:** `QuickSetPromptCard` (`mobile/src/components/QuickSetPromptCard.tsx`), snooze, never dismissed forever (`TradesScreen.tsx:6050-6090`). The entry-card precedent is `TeamReviewEntryCard`.
