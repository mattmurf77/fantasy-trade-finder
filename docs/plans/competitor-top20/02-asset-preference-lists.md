# 2. Asset preference lists: untouchables + targets

> Tier 1 · #2 · NEW · Effort M · Sources: OP-adjacent (DDr/FPT watchlists as partial precedent)

## Summary

Two per-player lists the user maintains per league: **Untouchables** (never suggest trading these away — a hard filter in candidate generation) and **Targets** (bias the engine toward acquiring these — a composite-score multiplier). Competitors (DynastyDealer, FPTrack) have watchlists, but none feeds them into discovery; FTF can, because the engine already has the exact seams: `acquire_positions`/`trade_away_positions` flow from `league_preferences` into a hard positional filter (`_positions_ok` in both `trade_service.py` and `trade_optimizer.py`), and FB-47's pinned-player machinery (`pinned_give_players`/`pinned_receive_players`) proves per-player constraints survive the candidate prune.

The fastest way to lose user trust is suggesting they trade away a player they would never move — today the engine cannot know that. Beyond immediate suggestion quality, each tag is a high-information label for the deferred acceptance model (#65): an untouchable tag is a far stronger "would never give" signal than the ~20 opaque pass-swipes collected so far, and a target tag is an explicit "want" the swipe stream can't produce.

## PRD

### Problem & user story

> As a league manager, I want to mark players I'd never trade and players I'm hunting, so the engine stops proposing deals I'd reject on sight and starts building deals around what I actually want.

The engine currently expresses user intent only at position granularity (`acquire_positions`, `trade_away_positions`) or per-job pinning (FB-47). There is no persistent player-level preference, so every generation run can re-suggest trading away the user's franchise cornerstone.

### Goals / Non-goals

**Goals**
- Untouchables: zero suggested trades that give away a tagged player, in every generation path (v2, v3, consensus fallback, sweetener pass).
- Targets: tagged opponent players bubble up in suggestions without breaking the mutual-gain/fairness math.
- One-tap tagging from player rows on web and mobile.
- Tags persisted server-side, per league, and logged as preference labels.

**Non-goals**
- No notification/alerting on tagged players (that's watchlist #25, after push #18).
- No effect on the ranking (Elo) flow — tags never touch ratings.
- No cross-league "global untouchable" in v1 (open question below).
- Targets do not force trades (that's pinning, FB-47); they bias ranking.

### Functional requirements

- FR1: User can add/remove a player to Untouchables or Targets per league; a player can't be on both lists in the same league.
- FR2: No generated card's `give_player_ids` may contain an untouchable — including sweetener additions made by `_try_sweeten` (which adds a cheapest-consensus player from the user's roster) and the "ask for more" pass (#4) when the user is the under-payer.
- FR3: Cards whose `receive_player_ids` contain a target get a composite-score multiplier so they rank higher within the deck; targets also survive the divergence prune (same mechanism as FB-47 `pinned_recv_set`).
- FR4: Tag changes invalidate cached trade jobs for that (user, league) via the existing `_invalidate_trade_jobs` helper in `server.py` — same treatment outlook changes get via `_trade_job_is_fresh`.
- FR5: Tag add/remove events are persisted with timestamps (label stream for #65).
- FR6: Lists are capped (proposal: 5 untouchables, 10 targets per league) to keep the filter from strangling generation; cap values in `model_config`.
- FR7: Flag-off behavior is byte-identical to today (per the `feature_flags.py` ship-dark convention).

### UX notes

- **Web** (`web/index.html` + `web/js/app.js`): lock icon (untouchable) and crosshair/star icon (target) on player rows in rankings/tiers views; own-roster players offer Untouchable, opponent-roster players offer Target. A small "Your lists" section on the find-a-trade panel shows current tags with remove affordance.
- **Mobile** (`mobile/src/screens/` + `mobile/src/components/PlayerCard.tsx`): long-press on a player row opens an action sheet (Add to Untouchables / Add to Targets); chips render on `TradeCard.tsx` when a card features a target ("🎯 Your target").
- Copy: explain the consequence at tag time — "FTF will never suggest trading him away" / "We'll hunt trades that land him".
- When an untouchable filter empties a deck (small rosters + many tags), surface "Your untouchables list is limiting suggestions" rather than a silent empty state.

### Success metrics

- ≥30% of weekly-active users have ≥1 tag within 4 weeks of launch.
- Pass-rate on cards giving away a top-3 user-Elo player drops (the proxy for "would never trade him" rejections; measurable from `trade_impressions` × `trade_decisions`).
- Cards containing a target get a higher like-rate than position-matched cards without one.
- Label volume: tags accumulate faster than swipe decisions did (~20 to date).

### Acceptance criteria

- [ ] Tagged untouchable never appears on the give side across v2 (`_generate_for_pair_v2`), v3 (`generate_pair_trades_v3`), consensus fallback, and sweetener paths (unit tests per path).
- [ ] Target-containing cards rank above otherwise-equal cards (deterministic test with fixed Elo inputs).
- [ ] Tag write → next `/api/trades/generate` is a fresh job (cache invalidation test).
- [ ] Flag off → zero behavior or payload change.
- [ ] `docs/api-reference.md`, `docs/data-dictionary.md`, `docs/config-reference.md` updated.

## HLD

### Components touched

`backend/database.py` (new table + accessors), `backend/server.py` (prefs routes, job kickoff plumbing, cache invalidation), `backend/trade_service.py` (give-side filter, target multiplier), `backend/trade_optimizer.py` (same two touchpoints in the v3 path), `web/js/app.js`, `mobile/src/api/league.ts`, `mobile/src/components/PlayerCard.tsx`, `mobile/src/screens/TradesScreen.tsx`.

### Data flow

Client tags player → `POST /api/league/asset-prefs` → row in `asset_preferences` → `_invalidate_trade_jobs(user_id, league_id)`. Next generation: `_run_trade_job` loads tags alongside `load_league_preference` (server.py already reads prefs there) → passes `untouchable_ids` / `target_ids` into `generate_trades_v2` → untouchables excluded from `give_candidates`/`give_pool` before enumeration; targets kept through the prune and rewarded in `_consider`/`_composite`. Tag events also land in the label stream read by future #65 training.

### Flags & config interplay

- New flag `trade.preference_lists` (default `false` in `config/features.json`, attr `FLAGS.trade_preference_lists`).
- Interacts with FB-47 `trade.finder_targeting`: pinning a player the user marked untouchable is a contradiction — pin wins for that job (explicit beats persistent), with a client-side warning.
- The dormant config keys `pos_acquire_bonus` (0.20) / `pos_tradeaway_bonus` (0.15) describe a soft positional multiplier ("+N% per received player whose position is in acquire_positions" per the `model_config` seed in `database.py`), but the current v2/v3 code applies positions as a hard filter only (`_positions_ok`; see the `trade_service.py` comment "Apply positional preference hard filter (not a score multiplier)"). The target multiplier adopts the *pattern* those keys describe, at player granularity.

## LLD

### Engine changes

All in value space, no new math:

1. **Untouchable filter** — in `_generate_for_pair_v2` (`trade_service.py`), drop tagged ids from `_known_user` before `give_candidates` is built; in `generate_pair_trades_v3` (`trade_optimizer.py`), drop from `known_user` before `give_pool`. In `_try_sweeten`, exclude tagged ids from the `candidates` list when `side == "give"`. Filtering at pool level (not per-combo) keeps enumeration cost unchanged.
2. **Target multiplier** — new config key `target_acquire_bonus` (default `0.20`, mirroring `pos_acquire_bonus`) in `_DEFAULT_CFG` + `model_config` seed. In v2 `_consider` and v3 `_composite`, after the tier multiplier: `composite *= 1 + target_acquire_bonus * n_targets_received`, capped by existing `pos_multiplier_cap` (2.00). Applied *after* the `min_side_surplus` and fairness gates so a target never rescues a non-mutual-gain trade.
3. **Prune survival** — append target ids present on the opponent roster to `recv_candidates`/`recv_pool`, exactly as `pinned_recv_set` does today (FB-47 lines already establish the pattern).

### API changes

```
GET  /api/league/asset-prefs?league_id=...
  → {"untouchables": ["4046", ...], "targets": ["7564", ...]}

POST /api/league/asset-prefs
  {"league_id": "...", "player_id": "4046", "list": "untouchable" | "target" | "none"}
  → {"ok": true, "untouchables": [...], "targets": [...]}     # "none" removes
```

Follows the `/api/league/preferences` GET/POST shape. `trade_card_to_dict` (server.py) gains an optional `"target_hit": true` field, serialized only when set (the likes_you/sweetener pattern).

### Schema changes

```python
asset_preferences_table = Table("asset_preferences", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("league_id",  String,  nullable=False),
    Column("player_id",  String,  nullable=False),
    Column("list_type",  String,  nullable=False),   # 'untouchable' | 'target'
    Column("created_at", String),
    UniqueConstraint("user_id", "league_id", "player_id", name="uq_asset_pref"),
)
```

SQLAlchemy Core, portable to SQLite/Postgres. Removals are hard deletes; the add/remove history needed for labels comes from `record_event` (`user_events` table) with event types `asset_pref_added`/`asset_pref_removed`, avoiding a second log table. Update `docs/data-dictionary.md`.

### Client changes

- `web/js/app.js`: tag toggles on player rows; lists panel; refetch trades after tag change.
- `mobile/src/api/league.ts`: `getAssetPrefs` / `setAssetPref`; React Query key `['assetPrefs', leagueId]`.
- `mobile/src/components/PlayerCard.tsx`: long-press sheet + tag glyphs; `TradesScreen.tsx`: target chip on cards.
- `extension/`: none in v1.

### Rollout

Flag `trade.preference_lists`, default `false`. Ship dark → enable for operator league → verify deck composition + cache invalidation → default on. No data migration needed (empty table = no-op).

### Open questions

1. Per-league vs global lists — dynasty users often feel the same about a player everywhere; v1 is per-league (matches `league_preferences` scope), revisit a "apply to all my leagues" shortcut.
2. Should untouchables also be excluded from *opponents'* suggested receive sides (other users' decks suggesting they acquire your untouchable is fine engine-wise but may read oddly once social features land)? v1: no.
3. Cap values (5/10) are guesses — validate against median roster size and watch deck-emptiness telemetry (`/api/admin/engine-metrics`, #84).
4. Does a target tag imply a position in `acquire_positions` for partner-fit ranking (FB-47 `partner_fit_score`)? Probably yes, but deferred to keep v1 surgical.

## As-built (2026-06-11)

Shipped the backend core behind `trade.preference_lists` (default false). In scope and verified:
- `asset_preferences` table + `load_asset_preferences` / `set_asset_preference` (single membership: a new tag replaces any prior tag for that player; `None` removes).
- Engine: untouchables filtered from the give pool in `_generate_for_pair_v2` (`_known_user`), `generate_pair_trades_v3` (`known_user`), the consensus path (`give_pool`), and `_try_sweeten` give-side candidates. Targets survive the prune in all three paths and earn a capped `target_acquire_bonus` composite multiplier in v2 `_consider` + v3 `_composite` (applied *after* the mutual-gain gates, so a target never rescues a bad trade).
- Routes `GET/POST /api/league/asset-prefs`; tag writes invalidate the league's cached deck (`_invalidate_trade_jobs`) and log `asset_pref_added/removed` to `user_events` (#65 label stream).
- Tests: `backend/tests/test_asset_preferences.py` (6 cases incl. untouchable-blocks-give on v2 + consensus, target lifts composite, bonus capped, no-ids identity, single-membership/validation). Full suite 190 green.

Deferred (UI slice, consistent with #17's mobile deferral):
- **`target_hit` card payload field + client tag UI** (web row toggles, mobile long-press sheet, "🎯 Your target" chip). The ranking behavior is complete and tested server-side; the affordances ship with the web/mobile work.
- Pin-vs-untouchable contradiction handling (FB-47): pin currently still wins by construction (untouchable filter runs before pinned-give re-add only on the *receive* side; a pinned *give* of an untouchable is an unlikely edge case) — revisit with the client when both surfaces exist.

## Dependencies & sequencing

- **Feeds #7** (rejection reasons): the "Wouldn't trade him" chip auto-prompts adding the player to Untouchables — ship #2 first or together (Wave 2 order in the backlog: #2 → #7).
- **Feeds #65** (acceptance model): tags are the label stream that shortens the path to training.
- **Interacts with #3** (swap builder): swap-in candidates should exclude the *opponent's* nothing in v1, but the user's untouchables must be excluded from swap-in suggestions on the give side; swap events and tags share the preference-signal pipeline.
- **Independent of #1/#8** (outlook work) — can ship in parallel.
- **#25 watchlist** later reuses the targets list as its seed.
