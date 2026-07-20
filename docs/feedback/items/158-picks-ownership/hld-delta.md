# HLD delta — Owned draft picks in calculator & suggestions (#158 + #170)

Deltas against `docs/architecture.md`. Additive; all behind flags `picks.owned_sync` and
`trade.picks_in_pool` (default off → today's data flow unchanged).

---

## 1. What changes at the system level

```
                       ┌──────────────────────────────────────────────┐
 Sleeper API           │  Owned-picks resolver (backend)               │
  /rosters ───────────▶│                                               │
  /traded_picks ──────▶│  resolve_owned_picks(league) ──▶ normalized   │──▶ draft_picks_table
  league settings ────▶│     (Sleeper: grid + overlay)     owned-pick        (+pool_value,
                       │     (MFL: franchise list)         rows (user_id       +platform)
 leagues.platform_ ───▶│     (ESPN: none)                  keyed)              │
   future_picks (MFL)  └──────────────────────────────────────────────┘        │
                                                                                 ▼
                          ┌───────────────────────┬──────────────────────────────────┐
                          │ GET /api/league/picks  │  trade generation candidate pool │
                          │  (+pool_value, label,  │  (inject owned picks per team →   │
                          │   picks_supported)     │   priced PICK pseudo-assets)      │
                          └───────────┬────────────┴───────────────┬──────────────────┘
                                      ▼                            ▼
                          Calculator In-league mode       Suggestion cards (#170)
                          (owned picks in picker, #158)    give/receive can be a pick
```

Two long-standing pieces are **revived / connected**, not invented:
`database.sync_draft_picks` (dead code, never called) and the `draft_picks_table` /
`load_draft_picks` / `GET /api/league/picks` chain (returns empty today).

## 2. Normalized owned-picks store (Decision D2 → extend, not new table)

Single store, platform-agnostic, **user_id-keyed** owner. Extend `draft_picks_table`
(`backend/database.py`) additively:

| New column | Type | Purpose |
|---|---|---|
| `pool_value` | Float | pick value on the **generic-ladder / engine** scale (calculator + suggestions). Distinct from legacy `pick_value` (pick-share ratios). |
| `platform` | String | `'sleeper' \| 'mfl'` — provenance; ESPN never writes rows. |

Everything else (`pick_id`, `season`, `round`, `owner_user_id`, `original_*`, `is_traded`)
already exists and already models the original-owner nuance. `load_draft_picks` and
`/api/league/picks` keep working; they just carry two more fields.

Rationale: reuses the existing sync/load/read surface, keeps `_user_pick_share` and outlook
seeds untouched, and gives a single normalized shape for Sleeper + MFL so all downstream
readers are platform-blind.

## 3. Sync placement — the existing league-sync path

`sync_draft_picks` must run whenever a league's roster state is refreshed. The natural home
is **`session_init`'s background writer** (`server._session_init_background_writes`, the
daemon thread that already does trade-block sync via `trade_block_service`). It runs
off the request's critical path, per-league, on every session init.

- **Sleeper:** the background writer fetches `traded_picks` server-side (public,
  unauthenticated — same trust level as `_fetch_league_rosters`), reads `draft_rounds` /
  `season` / `total_rosters` from the league meta already loaded, builds the
  `roster_id → user_id` map from the rosters, and calls `sync_draft_picks(...)`.
- **MFL:** when `league.platform == 'mfl'`, read `leagues.platform_future_picks`, map
  franchise→user, and write the same rows through a normalized path (§5).
- **ESPN:** skip entirely; mark `picks_supported=false` at the API layer.

Gated on `picks.owned_sync`. Failure is isolated (a pick-sync exception must never break
session_init) — mirrors the trade-block daemon's fail-soft contract.

## 4. Sleeper owned-picks algorithm (confirmed against live payload)

Probed `/v1/league/1312076055586050048/traded_picks` (55 rows). Each entry:

```json
{ "round": 1, "season": "2026", "roster_id": 1, "owner_id": 7, "previous_owner_id": 1 }
```

**All ids are integer roster_ids.** `roster_id` = the pick's **original** owner (its
identity); `owner_id` = **current** holder; `previous_owner_id` = last hop (informational —
we take the final `owner_id`).

Algorithm (already implemented correctly in `sync_draft_picks`, just uncalled + needs the
`rounds` fix):

1. **Pristine grid:** for every `roster_id` in the league × every season in
   `[current_season … current_season + seasons_ahead]` × every round in
   `[1 … draft_rounds]`, create one pick owned by that roster's user. `pick_id =
   f"{league_id}_{season}_{round}_{orig_roster_id}"`.
2. **Overlay traded picks:** for each `traded_picks` entry, look up the grid pick by
   `(season, round, roster_id=orig)`, set `owner_user_id = user_of(owner_id)`,
   `is_traded = (owner_id != roster_id)`. Original owner columns stay pinned to `roster_id`.
   A pick traded twice appears once with the final `owner_id` — correct by construction.
3. **Value:** compute both `pick_value` (legacy, pick-share) and `pool_value` (HLD §6 of
   the PRD / LLD §4) per pick.
4. **Replace-sync:** delete this league's rows, bulk-insert fresh (existing behavior).

**Fixes vs current code:** pass `rounds = settings.draft_rounds` (probed league = 4, default
was 3 → dropped 4ths); pass real `current_season`/`league_size` from league meta.

**Original-owner nuance:** a team can own multiple picks in the same season+round (their own
+ acquired). The grid+overlay handles this: each grid pick is keyed by *original* roster, so
acquired picks land on distinct `pick_id`s and both show under the current owner.

## 5. MFL normalization

`mfl_service.parse_bundle` already yields `future_picks:
[{franchise_id, year, round, original_owner}]`, persisted to
`leagues.platform_future_picks`. MFL gives the **owned list directly** (no grid needed):
each entry is a pick the `franchise_id` currently owns, `original_owner` = the franchise it
came from.

Normalize into `draft_picks_table` rows:
- `owner_user_id = user_of(franchise_id)` via the MFL franchise→member map (the same map the
  MFL link route builds; `mfl_service.map_franchises` + the stored member roster).
- `original_user_id = user_of(original_owner)` (or `owner` when `original_owner` is empty /
  self).
- `pick_id = f"{league_id}_{year}_{round}_{original_franchise}"` (same scheme, franchise as
  the original-owner token).
- `platform = 'mfl'`, `pool_value` via the same §6 formula.

Coverage is whatever MFL exports — full, since ownership is explicit.

## 6. Value scale & the calculator/suggestion inclusion (high level)

- **Reconciliation:** `pool_value` = generic-ladder Mid-tier value of the round,
  year-discounted in value space (PRD §6). At `years_out=0` a league 1st equals the generic
  "Mid 1st" pool player exactly. Legacy `pick_value` is left alone.
- **Calculator (#158):**
  - Generic picks already ride `/api/trade/values` and already evaluate — surface them in
    the picker.
  - Owned picks are league-scoped → surfaced through the **In-league** calculator
    (`InLeagueCalculator`) from an enriched `GET /api/league/picks`. `/api/trade/evaluate`
    gains the ability to resolve league-pick pseudo-ids to a value (currently it only knows
    universal-pool `seed` ids; league picks aren't in `seed`). See LLD §5.
- **Suggestions (#170):** the trade job injects each team's owned picks (top-N by
  `pool_value`) as `position="PICK"` pseudo-Players into the per-format player dict and
  appends their ids to `user_roster` / `member.roster`. The engine's existing PICK pricing
  (`dynasty_value`) values them; nothing else in scoring changes here.

## 7. Engine-hook boundary (explicit)

This item delivers **data into the candidate pool**. The seam:

```
trade_service.generate_trades / _generate_trades_v2
   ├── candidate assets per team  ← THIS ITEM adds owned picks here (flag trade.picks_in_pool)
   └── scoring / gates / ranking  ← TRADE-LOGIC THREAD owns (unchanged by this item)
```

- **We provide:** owned pick pseudo-assets on each side, each with a `pool_value`, registered
  in the engine player dict, with a per-team cap (D4).
- **We do NOT touch:** `min_side_surplus`, consolidation/clogger/star weighting, harmonic
  ranking, or any pick-specific tax. If picks should be weighted specially, that lands in the
  trade-logic thread. The hook is: "picks are now in `user_roster`/`member.roster` and in
  `self._players`; score them like any asset."

## 8. Combinatorial cost + cap

Adding ~`seasons_ahead × draft_rounds` picks per team (≈12 in a 4-round Sleeper league)
roughly doubles per-team asset count, and package enumeration is combinatorial in assets per
side (`v3_pool_size`, `max_candidates`). Mitigations:

- Cap owned picks entering the pool to **top-N by `pool_value` per team** (D4, N≈6, config
  knob `picks_pool_cap`). Low-value late picks rarely move a suggestion and cost the most
  combinatorially.
- Picks join the *same* per-side candidate shortlist the engine already bounds
  (`max_candidates`, `v3_pool_size`) — no new enumeration layer.
- The trade-logic thread owns the final perf validation of N against v3 enumeration (D4).

## 9. Identity crosswalk summary

| Platform | Pick key in payload | → owner resolution | store key |
|---|---|---|---|
| Sleeper | roster_id (int) | league `/rosters` `roster_id→owner_id(user)` | user_id |
| MFL | franchise_id (str) | MFL franchise→member map | user_id |
| ESPN | — | — | — (no rows) |

Store is user_id-keyed on both owner and original owner → every downstream reader
(calculator, suggestions, pick-share) is platform-agnostic.

## 10. Docs to update when built

`data-dictionary.md` (draft_picks new columns), `api-reference.md` (`/api/league/picks`
`picks_supported`+`pool_value`; `/api/trade/evaluate` accepts pick ids),
`config-reference.md` (`picks.owned_sync`, `trade.picks_in_pool`, `picks_pool_cap`),
`cross-client-invariants.md` (the `pool_value` = ladder-Mid × discount formula — clients must
not recompute it differently), `architecture.md` (pick sync in the session_init daemon).
