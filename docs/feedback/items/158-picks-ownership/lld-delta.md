# LLD delta — Owned draft picks (#158 + #170)

Concrete function/route/schema deltas. File paths absolute-relative to repo root. All behind
`picks.owned_sync` / `trade.picks_in_pool` (default off).

---

## 1. Schema (`backend/database.py`)

Extend `draft_picks_table` (~line 487) with two additive columns, plus idempotent ALTERs in
`_migrate_db()`:

```python
Column("pool_value", Float),   # engine/calculator scale (elo_to_value units)
Column("platform",   String),  # 'sleeper' | 'mfl'
```

`_migrate_db()` list (~line 1517, where `platform_future_picks` is registered):

```python
("draft_picks", "pool_value", "FLOAT"),
("draft_picks", "platform",   "TEXT"),
```

No new table (Decision D2). `load_draft_picks` returns the two new fields automatically
(`select(draft_picks_table)`).

## 2. Value reconciliation helper (shared, single source of truth)

New helper co-located with `GENERIC_PICK_SEEDS` in `backend/server.py` (or a small shared
module both `server` and `database` import — see note). Ties #157 to this item so the ladder
can't drift.

```python
YEAR_DISCOUNT = 0.85   # reuse database._PICK_YEAR_DISCOUNT value; single constant

def pick_pool_value(round_: int, years_out: int, scoring_format: str = "1qb_ppr") -> float:
    """Generic-ladder Mid-tier value of a round, year-discounted in VALUE space.

    years_out=0 → exactly the generic 'Mid <round>' pool pick's value, so a league
    1st reconciles with GENERIC_PICK_SEEDS[(1,'Mid')] by construction.
    """
    e2v      = _trade_service_mod.elo_to_value
    base_elo = GENERIC_PICK_SEEDS.get((round_, "Mid"),
                                      GENERIC_PICK_SEEDS[(4, "Mid")])  # clamp deep rounds
    base_val = e2v(base_elo)
    return round(base_val * (YEAR_DISCOUNT ** max(0, years_out)), 1)
```

**Placement note:** `sync_draft_picks` lives in `database.py`, which must not import
`server.py` (cycle). Two clean options: (a) move `GENERIC_PICK_SEEDS` + `pick_pool_value`
into a tiny new `backend/pick_values.py` imported by both; or (b) `sync_draft_picks` takes a
`pool_value_fn` callback passed from `server`. **Recommend (a)** — one home for the ladder,
also what #157 wants. `compute_pick_value` stays in `database.py` untouched (pick-share
scale).

## 3. Sleeper sync — revive + fix (`backend/database.py` `sync_draft_picks`)

Signature gains nothing structurally; callers must supply the real values:

```python
sync_draft_picks(
    league_id       = league_id,
    roster_ids      = [r["roster_id"] for r in rosters],
    traded_picks    = traded_picks,          # raw list from /traded_picks
    roster_id_to_user = {str(r["roster_id"]): r["owner_id"] for r in rosters},
    user_id_to_name = user_id_to_name,
    current_season  = int(league_meta["season"]),
    rounds          = int(league_meta["settings"]["draft_rounds"]),   # FIX: was hard 3
    seasons_ahead   = 3,
    league_size     = int(league_meta.get("total_rosters") or len(rosters)),
)
```

Inside `sync_draft_picks`, at each pick row add:

```python
"pool_value": pick_pool_value(rnd, season - current_season, scoring_format),
"platform":   "sleeper",
```

(Thread a `scoring_format` param, default `"1qb_ppr"`; pick value is format-agnostic in v1
per Decision D3, so the param is plumbing for later.)

Payload field mapping (confirmed live): `roster_id`=original, `owner_id`=current,
`season` is a **string** (`int(...)` already applied), `previous_owner_id` ignored.

## 4. Sync call site (`backend/server.py` `_session_init_background_writes`, ~line 8090)

Add a fail-soft block alongside the trade-block sync, gated on `picks.owned_sync`:

```python
if is_enabled("picks.owned_sync") and getattr(new_league, "platform", None) != "espn":
    try:
        if new_league.platform == "mfl":
            _sync_mfl_owned_picks(league_id)          # §6
        else:  # sleeper
            traded = _fetch_sleeper_traded_picks(league_id)   # public GET
            rosters = _fetch_league_rosters(league_id)        # existing helper (~5684)
            sync_draft_picks(..., traded_picks=traded, ...)   # §3
    except Exception:
        log.warning("owned-pick sync failed for league=%s", league_id, exc_info=True)
```

New tiny fetch helper (mirror `_fetch_league_rosters`):

```python
def _fetch_sleeper_traded_picks(league_id: str) -> list[dict]:
    # GET https://api.sleeper.app/v1/league/<id>/traded_picks  (public, unauth)
    # returns [] on any failure (fail-soft).
```

`user_id_to_name` comes from the users the session already loaded (league members). Note:
Sleeper rosters give `owner_id` (user_id) directly; `roster_id_to_user` is
`{str(roster_id): owner_id}` — no extra fetch.

## 5. MFL normalization (`backend/server.py` new `_sync_mfl_owned_picks`)

```python
def _sync_mfl_owned_picks(league_id: str) -> None:
    lg = load_league_row(league_id)                    # has platform_future_picks
    picks = json.loads(lg.get("platform_future_picks") or "[]")
    fr_to_user = _mfl_franchise_to_user(league_id)     # franchise_id -> sleeper user_id
    current_season = int(lg.get("platform_season") or DEFAULT_YEAR)
    rows = []
    for pk in picks:
        yr, rnd = int(pk["year"]), int(pk["round"])
        orig = pk.get("original_owner") or pk["franchise_id"]
        rows.append({
            "pick_id":            f"{league_id}_{yr}_{rnd}_{orig}",
            "league_id":          league_id, "season": yr, "round": rnd,
            "owner_user_id":      fr_to_user.get(pk["franchise_id"], ""),
            "owner_username":     ...,
            "original_roster_id": str(orig),
            "original_user_id":   fr_to_user.get(orig, ""),
            "original_username":  ...,
            "is_traded":          int(orig != pk["franchise_id"]),
            "pick_value":         compute_pick_value(rnd, yr, current_season),
            "pool_value":         pick_pool_value(rnd, yr - current_season),
            "platform":           "mfl",
        })
    replace_draft_picks(league_id, rows)   # same delete+bulk-insert as sync_draft_picks
```

`_mfl_franchise_to_user`: reuse the franchise→member mapping the MFL link route already
computes (`mfl_service.map_franchises` returns rosters keyed by franchise_id; cross-reference
with stored league members to get user_ids). Factor the delete+insert tail of
`sync_draft_picks` into a shared `replace_draft_picks(league_id, rows)` so both paths reuse
it.

## 6. `GET /api/league/picks` enrichment (`backend/server.py` ~4959)

Current returns `{my_picks, all_picks}` straight from `load_draft_picks`. Add:

- `pool_value` + a display `label` per pick (e.g. `"2027 1st"`, or
  `"2026 2nd (from <orig_username>)"` when `is_traded`).
- `picks_supported`: `false` for ESPN leagues (and empty lists), `true` otherwise.

```python
supported = (g_league.platform != "espn")
def _label(p):
    base = f"{p['season']} {_PICK_ORDINALS[p['round']]}"
    return base if not p["is_traded"] else f"{base} (from {p['original_username']})"
picks = [{**p, "label": _label(p)} for p in load_draft_picks(league_id)]
return jsonify({
    "my_picks":  [p for p in picks if p["owner_user_id"] == g_user_id],
    "all_picks": picks,
    "picks_supported": supported,
})
```

Pick pseudo-id for the calculator/evaluate is the existing `pick_id`
(`{league}_{season}_{round}_{origroster}`).

## 7. `POST /api/trade/evaluate` — accept league-pick ids (`backend/server.py` ~4589)

Today `give/recv` are filtered to ids present in the universal-pool `seed`; league picks are
**not** in `seed`, so they'd be silently dropped into `dropped_player_ids`. Add a league-pick
value resolver when `league_id` is present:

```python
league_pick_vals = {}   # pick_id -> pool_value
if league_id:
    for p in load_draft_picks(league_id):
        league_pick_vals[p["pick_id"]] = p.get("pool_value") or 0.0

def seed_value(pid):
    if pid in league_pick_vals:
        return league_pick_vals[pid]          # already in value space
    return e2v(seed.get(pid, 1500.0))

give    = [p for p in give_raw if p in seed or p in league_pick_vals]
recv    = [p for p in recv_raw if p in seed or p in league_pick_vals]
dropped = [p for p in give_raw + recv_raw if p not in seed and p not in league_pick_vals]
```

`_consensus_packages` / `_fairness_v3` take the `seed_value` fn — no change to their math.
Generic-pick ids (`generic_pick_*`) already resolve via `seed` (they're pool players), so the
public "Real values" mode needs **no change** for generic picks. `pool_value` is already in
`elo_to_value` units, so it composes directly with player values. Mode B (both-boards) uses
consensus `pool_value` for picks (owners rarely rank picks personally — acceptable v1).

## 8. Calculator client (`mobile/src/components/InLeagueCalculator.tsx` + picker)

- Fetch owned picks via existing `getLeaguePicks(leagueId)` (add if absent) → for Side A show
  `my_picks`; for Side B show the opponent's picks (`all_picks` filtered to
  `owner_user_id == opponentId`).
- Merge picks into the `PlayerPickerModal` list as pseudo-`CalcPlayer` entries
  (`pos: 'PICK'`, `base: pool_value`, `id: pick_id`, `name: label`).
- On evaluate, `pick_id`s go into `give_player_ids`/`receive_player_ids` alongside player ids;
  the backend (§7) resolves them. Assert they don't land in `dropped_player_ids`.
- ESPN: if `picks_supported === false`, render a one-line note; no picker rows.
- `TradeCalculatorScreen.tsx` "Real values" (live) mode: generic picks already arrive in
  `getTradeValues` — ensure the picker doesn't filter out `pos === 'PICK'`. (Owned picks stay
  out of live mode — it's league-agnostic.)

## 9. Suggestions — inject owned picks into the candidate pool (#170)

**Where:** `backend/server.py` `_run_trade_job` (~2146) assembles `g_user_roster`,
`g_players`, and `members` before calling `service.generate_trades(...)`. Add, gated on
`trade.picks_in_pool`:

```python
if FLAGS.trade_picks_in_pool and g_league.platform != "espn":
    pick_assets = _owned_pick_assets(league_id, active_format)   # {user_id: [Player(PICK)...]}
    # 1. register pick pseudo-Players in the engine dict
    for uid, assets in pick_assets.items():
        for pa in assets:
            trade_service._players[pa.id] = pa      # PICK-position, pick_value set
    # 2. append to each side's roster asset list (capped)
    g_user_roster = g_user_roster + [pa.id for pa in pick_assets.get(g_user_id, [])]
    for m in g_league.members:
        m.roster = m.roster + [pa.id for pa in pick_assets.get(m.user_id, [])]
```

`_owned_pick_assets` builds capped (`picks_pool_cap`, default 6, top-N by `pool_value`)
`Player` objects from `load_draft_picks`:

```python
Player(id=p["pick_id"], name=p["label"], position="PICK", team="PICK",
       age=0, years_experience=0,
       pick_value=(p["pool_value_as_pick_value"]),   # see note
       search_rank=<round-derived, like generic picks>)
```

**pick_value note:** the engine's `dynasty_value` for PICK does
`elo_to_value(1200 + 6*pick_value)`. To feed it a value in the SAME space as `pool_value`,
set `pick_value = (value_to_elo(pool_value) - 1200) / 6` so the round-trip reproduces
`pool_value` exactly. (Equivalently, extend `dynasty_value`/`player_value` to accept a
precomputed value — but the inverse keeps the engine untouched, honoring the boundary.)

**Boundary reminder:** steps above only place priced assets in the pool. Package
enumeration, gates, ranking, and any pick weighting are the trade-logic thread's — unchanged
here.

**Cap / perf (Decision D4):** `picks_pool_cap = 6`. With ≈12 picks/team in a 4-round league,
uncapped roughly doubles per-side assets feeding `v3_pool_size`(12)/`max_candidates`(30)
enumeration; capping to the 6 most valuable keeps growth bounded. Trade-logic thread owns
final N validation.

## 10. Flags (`config/features.json`)

```json
"picks.owned_sync":    false,   // revive sync + MFL normalization + calculator owned picks
"trade.picks_in_pool": false    // inject owned picks into suggestion candidate pool (#170)
```

Model-config knob: `picks_pool_cap` (default 6). Register in the same place other trade knobs
live so `/api/feature-flags/reload` and model_config seeding pick them up.

## 11. Test hooks (offline)

- `backend/tests/test_pick_value_scaling.py` (exists) — extend: `pick_pool_value(1,0)` ==
  `elo_to_value(GENERIC_PICK_SEEDS[(1,'Mid')])` within 0.1; discount monotonic in years_out;
  round-trip `value_to_elo`/`elo_to_value` reproduces `pool_value` for the injected asset.
- New `test_sync_draft_picks.py` — probed `traded_picks` fixture (roster_id-keyed), 4-round
  league, double-traded pick resolves to final owner; MFL fixture → identical row shape.
- `/api/trade/evaluate` with a league_id + a `pick_id` on each side → pick not in
  `dropped_player_ids`, `give_value`/`receive_value` include the pick's `pool_value`.

## 12. Summary of files touched (when built)

| File | Change |
|---|---|
| `backend/pick_values.py` (new) | `GENERIC_PICK_SEEDS` + `pick_pool_value` shared home |
| `backend/database.py` | `draft_picks` +2 cols, `_migrate_db` ALTERs, `sync_draft_picks` `pool_value`/`platform` + `rounds` fix, `replace_draft_picks` factor-out |
| `backend/server.py` | `_fetch_sleeper_traded_picks`, sync call in `_session_init_background_writes`, `_sync_mfl_owned_picks`, `/api/league/picks` enrich, `/api/trade/evaluate` pick resolver, `_owned_pick_assets` + injection in `_run_trade_job` |
| `mobile/src/components/InLeagueCalculator.tsx`, `PlayerPickerModal`, `api/calc.ts` | owned-pick picker rows, ESPN note, pick ids in evaluate |
| `config/features.json` | 2 flags + `picks_pool_cap` |
| `docs/*` | data-dictionary, api-reference, config-reference, cross-client-invariants, architecture |
