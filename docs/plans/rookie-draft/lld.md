# LLD — Rookie Rankings + Live Draft Support

**Date:** 2026-08-05 · **Status:** Draft for build briefing
**Parents (normative):** [plan.md](plan.md) (FINAL, dual-agent converged) · [hld.md](hld.md). D1–D10, M0–M8, O1–O10, KD-*, RB-*, I-* resolve to those documents. **Nothing here re-opens a plan decision.**
**Grounding:** every `file:line` is an `origin/main` line (`0118efc`). The local `teardown-remediation` tree lags and has ~8 modified tracked files including `docs/api-reference.md`, which M3 also edits — **commit or stash before any wave and expect that conflict.**
**Stance:** every interface states exact types, nullability and error returns; every race is named with its resolution; every invariant names the test that proves it.

> ### ⚠️ RE-VERIFY AT BUILD TIME
> `server.py` is 17,918 lines on `origin/main` and four milestones edit it. **Line numbers rot; symbols do not.** Before each wave, `git pull` and re-locate by symbol, then re-check the eight anchors in §1.2. Items tagged **[RV-n]** throughout are the specific places where a moved or changed tree invalidates this document's assumptions — each names what to re-check and what it would mean.

---

## 1. Scope & Reference

### 1.1 Covers / excludes

**Covers:** M0–M6 implementation — the player-cache refresh path and pool generation counter, the fixture/replay harness, the `scope=rookie` seam and merged-band tier save, `backend/draft_board_service.py` + `GET /api/draft/board`, the mobile Draft Room and shared scope control, MFL parity, and the DP `values.csv` PICK reader.
**Excludes:** M7 (on-the-clock push, recap analysis, `platform_future_picks` refresh from the live grid, ESPN `mDraftDetail`, web parity, full startup support) and M8 (spring rehearsal — calendar-gated, resourced but not specified here).

### 1.2 Grounding anchors (symbols, not lines)

| Anchor | Symbol | Why it is load-bearing |
|---|---|---|
| A-1 | `server._load_sleeper_cache` / `PLAYERS_CACHE_FILE` (`server.py:397-419`) | No TTL; module-global early-return. M0 replaces the lifecycle, not the reader. |
| A-2 | `server._ensure_universal_pools` (`server.py:1316-1407`) | Early-return at `:1324`; in-place mutation of `g_universal_players` / `g_universal_seed` / `dp_values` at `:1403-1407`. |
| A-3 | `server._player_sync_lock` (`server.py:1482`) | Serializes **syncs**, not pool readers. The single-flight guard is a *different* lock. |
| A-4 | `session_init`'s `need_rebuild` (`server.py:11688`) | The one session-boundary rebuild seam. |
| A-5 | `RankingService._pool` / `_compute_elo` / `apply_tiers` / `apply_reorder` / `apply_anchor` (`ranking_service.py:795, 953, 1261, 1345, 1327`) | The write lanes. `apply_reorder`/`apply_anchor` are already subset-safe; `apply_tiers` is not. |
| A-6 | `database._parse_per_format_json` (`database.py:3188-3208`) + `save_tier_overrides` (`:3269-3298`) | **Discards unknown top-level keys.** See §3.2 — this is a correctness precondition for the snapshot. |
| A-7 | `server._sleeper_get` + `_sleeper_fixture_path` (`server.py:476-511`) | The replay seam. Only rewrites URLs containing `api.sleeper.app/v1/`. |
| A-8 | `draft_status.is_rookie_row` (`draft_status.py:94-108`) + `database.load_rookie_player_ids` (`database.py:6915-6939`) | THE predicate and its SQL mirror. `database.load_rookies` (`:6886-6912`) is the LOOSE legacy rule. |

**Conventions:** timestamps ISO-8601 UTC via `database._now()`; JSON stored as `Text`, parsed in Python (no json1/JSONB — dual-dialect); new flag keys appended to `feature_flags.FLAG_KEYS` (`feature_flags.py:47-355`), which makes them default-`False` (`:357`).

---

## 2. Interfaces / API

### 2.1 `GET /api/draft/board` (M3; shim in `server.py` → `draft_board_service.build_board()`)

**Route decorators (exact, in order):**
```python
@app.route("/api/draft/board")
@_gate_unverified_read                      # server.py:1918 — same posture as /api/rankings:5240
def draft_board_route():
    if not is_enabled("draft.room"):
        return jsonify({"error": "feature_disabled"}), 404      # repo convention (espn.link, mfl.link)
```

**Query params:** `league_id` (optional, default = session league) · `basis` ∈ `consensus` | `my_board` (default `consensus`).

**[RV-1]** The blanket `@_gate_unverified_read` is what the plan specifies. Note the precedent it differs from: `GET /api/league/power-rankings` applies the read gate **inline, only for `basis=personal`** (`server.py:7373` — "the route can't take `@_gate_unverified_read` wholesale"), because consensus output is a league-shared aggregate. The blanket decorator therefore gates the consensus path more tightly than the nearest precedent. Ship the plan's blanket gate; record the divergence in `docs/api-reference.md`'s gated-read matrix so a future reader does not read it as an oversight.

**Response — `200`, `schema:1`. Field-by-field:**

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `schema` | int | no | Always `1`. Clients MUST reject unknown values rather than best-effort parse. |
| `league_id` | string | no | Echo of the resolved league. |
| `platform` | `"sleeper"` \| `"mfl"` | no | Source. Any other platform ⇒ `state:"unavailable"`. |
| `state` | `"upcoming"` \| `"live"` \| `"complete"` \| `"unavailable"` | no | Closed enum. `unavailable` = no usable source (unsupported platform, no draft object, nothing cached). |
| `kind` | `"rookie"` \| `"startup"` \| `"unknown"` | no | From the rounds shape (`draft_status.ROOKIE_MAX_ROUNDS=8`, `STARTUP_MIN_ROUNDS=15`, `draft_status.py:65-66`). `startup` ⇒ `undrafted` is `[]` and `undrafted_suppressed` is `true`. |
| `season` | int | no | Draft season, coerced from the platform's string (`draft.season` is a string — `research-platforms.md:76-78`). |
| `rounds` | int | yes | `settings.rounds` / MFL `total/franchises`. |
| `teams` | int | yes | `settings.teams` / `total_rosters`. |
| `order_confidence` | `"assigned"` \| `"unset"` \| `"unknown"` | no | `assigned` **iff** `draft_order != null` (Sleeper) or the grid carries a franchise on every pick (MFL). `unset` ⇒ `order[]` carries round-level ownership with `slot: null`. **Never** derive an order from `slot_to_roster_id` (D5). |
| `order[]` | array | no (may be `[]`) | One entry per pick slot. See below. |
| `picks[]` | array | no (may be `[]`) | Picks actually made, ascending `pick_no`. See below. |
| `undrafted[]` | array | no (may be `[]`) | See below + D7. |
| `undrafted_basis` | `"consensus"` \| `"my_board"` | no | Echo of `basis`. |
| `undrafted_suppressed` | bool | no | `true` for `kind:"startup"` and for the pre-class-load state. |
| `my_picks[]` | array | no (may be `[]`) | Subset of `order[]` where `owner_user_id == session user`. |
| `as_of` | ISO-8601 UTC string | no | When the underlying upstream read succeeded. **Always rendered by the client.** |
| `stale` | bool | no | `true` when `now - as_of` exceeds 2× the state's TTL, or the breaker is open. |
| `degraded` | object \| null | yes | `{reason, since}`; `reason` ∈ `upstream_error` \| `breaker_open` \| `budget_exceeded` \| `auth_expired`. |
| `notice` | object \| null | yes | `{code, message}` for designed honest states: `order_not_set` \| `startup_draft` \| `platform_unsupported` \| `class_not_loaded` \| `mfl_reconnect`. |
| `deep_link` | string \| null | yes | The platform's draft room (terminal CTA, D9). Never a write. |

`order[]` entry: `{slot: int|null, round: int, pick_no: int|null, owner_user_id: str|null, owner_username: str|null, original_user_id: str|null, original_username: str|null, is_traded: bool, slot_value: float|null}`.
`slot_value` is present **only** when `picks.slot_values` is on and the M6 read succeeded (I-7); otherwise the key is omitted entirely (the repo's omit-when-absent convention, `player_to_dict`).

`picks[]` entry: `{round: int, pick_no: int, slot: int|null, player_id: str, name: str, position: str, team: str|null, picked_by_user_id: str|null, picked_at: ISO|null}`. `player_id` is our own id space (`research-platforms.md:141-142`).

`undrafted[]` entry: `{player_id: str, name: str, position: str, team: str|null, rookie_year: str|null, value: float|null, valued: bool, rank: int}`. **`valued:false` rows are rendered, never dropped (D7)** — the client shows "no consensus value". `rank` is 1-based over the ordered list.

**Errors:** `404 {"error":"feature_disabled"}` (flag off) · `404 {"error":"league_not_found"}` · `401` via `_require_session` · `403 {"error":"verification_required"}` via the read gate. **Never 5xx for an upstream failure** — that is `state`/`degraded`/`stale`.

### 2.2 `scope=rookie` request contract (M2)

Applies to `GET /api/rankings` (`server.py:5239`) and `GET /api/trio` (`server.py:4857`).

```
?scope=rookie          # the only non-default value in V1
```

- **Flag `ranks.rookie_subset` off ⇒ the parameter is never read.** Not parsed, not validated, not logged. This is how D4 (flag on vs off ⇒ byte-identical) is achieved structurally rather than by diffing.
- Unknown `scope` values with the flag on ⇒ `400 {"error":"bad_scope"}`.
- **`GET /api/trio` carries no read gate today** (`server.py:4857-4858` — no `@_gate_unverified_read`, unlike `/api/rankings:5240`). Adding `scope` does not change that posture. Do **not** add the decorator as a drive-by; it is a separate auth decision with its own blast radius. **[RV-2]** re-check both decorators before M2.

**Thin-pool response (replaces today's `ValueError → 400`):**
```json
{ "empty": true, "reason": "thin_pool", "position": "TE", "scope": "rookie", "count": 2 }
```
`200`, not `400`. `reason` ∈ `thin_pool` (fewer than 3 scoped candidates — the `ranking_service.py:391-392` bar) \| `class_not_loaded` (zero rows with `rookie_year == season`). **Only on the scoped path** — the unscoped path keeps today's `400` byte-for-byte.

**Scoped save body** (`POST /api/tiers/save`, `server.py:6342`), additive:
```json
{ "position":"RB", "tiers":{...}, "cleared_pids":[...], "demoted_pids":[...],
  "scope":"rookie", "via":"rookie_tiers" }
```
- `via` ∈ `rookie_tiers` \| `rookie_quickset` \| `rookie_anchors` when `scope=="rookie"` — the forensic tag (KD-10). The existing `via` whitelist at `server.py:6449` (`("tiers","quickset")`) must be **extended, not replaced**; an unrecognised `via` still falls back to `"tiers"`.
- **The response must NOT contain `saved` or `all_done` changes.** A scoped save returns today's shape with `saved`/`all_done` read (not written) from `get_tiers_saved` — see §4.3.

### 2.3 `POST /api/cron/players-refresh` (M0)

```python
@app.route("/api/cron/players-refresh", methods=["POST"])
def cron_players_refresh():
    _require_cron_auth()                       # server.py:13058 — constant-time, prod fail-closed 503
    started = _refresh_players_cache_async(force=request.args.get("force") == "1")
    return jsonify({"ok": True, "started": started,
                    "generation": pool_generation(),
                    "cache_age_s": _players_cache_age_seconds()}), 202
```
`202` always (even when `started` is `False` because a refresh is already in flight, or the cache is fresher than the TTL). Never blocks. Never returns the payload.

**Fallback trigger inside `cron_daily_tick`** (`server.py:13278`), following the value-snapshot fallback-guard precedent at `server.py:13149-13163`: if `_players_cache_age_seconds() > _PLAYERS_CACHE_TTL_SECONDS`, call `_refresh_players_cache_async()` inside its own `try/except` and add `"players_refresh_started": bool` to the response. Failure-isolated — it must never touch the push work.

**Operational kill (implementation addition, not a plan decision):** env `FTF_PLAYERS_REFRESH=0` makes `_refresh_players_cache_async` a no-op returning `False`. Documented in `docs/config-reference.md` §Environment variables and `docs/runbook.md`, mirroring the KTC kill-switch precedent. This exists because M0 is **not** flag-gated and there must be a lever that does not require a code deploy.

---

## 3. Data Structures & Schema

**No new tables. No migrations. No new datastore.** `_migrate_db()` is untouched by every milestone.

### 3.1 In-process structures (all in `server.py` unless noted)

```python
# ── M0 ────────────────────────────────────────────────────────────────
_PLAYERS_CACHE_TTL_SECONDS = 20 * 3600     # < 24h so a daily tick never skips on jitter
_players_refresh_lock   = threading.Lock() # guards the in-flight flag ONLY (never held across I/O)
_players_refresh_active = False
_pool_build_lock        = threading.Lock() # single-flight for _ensure_universal_pools (A-3: NOT _player_sync_lock)
_pool_generation        = 0                # int, monotonic; read under _pool_build_lock
_last_refresh_status: dict = {}            # {"at","ok","error","players","generation"} — health/observability
```

```python
# ── M3, in backend/draft_board_service.py ────────────────────────────
_TTL_BY_STATE = {"upcoming": 300, "live": 20, "complete": 86_400, "unavailable": 60}
_CACHE_MAX_ENTRIES = 200
_BREAKER_FAILS = 3          # consecutive upstream failures to open
_BREAKER_OPEN_SECONDS = 120
_BUDGET_PER_MIN = 3         # upstream fetches per draft per rolling 60 s (D6)

_cache: dict[CacheKey, _Entry] = {}
_cache_lock = threading.Lock()          # guards _cache structure only
_inflight: dict[CacheKey, threading.Lock] = {}   # per-key single-flight
```

- **Cache key:** `CacheKey = tuple[str, str, str]` = `(platform, league_id, draft_id)`. `draft_id` is `""` when none is resolvable (the `unavailable` path), so a league with no draft still caches its negative result for 60 s instead of re-probing per request.
- **Entry:** `_Entry = {fetched_at: float(monotonic), as_of: str(ISO), state: str, last_picked: int|None, detail: dict, picks: list, fails: int, opened_until: float, budget: deque[float]}`. **The rendered payload is NOT cached** — only upstream material is. Rendering is cheap and `basis`-dependent; caching the payload would multiply keys by basis and by session user (`my_picks`).
- **Eviction:** on every `build_board()` call, before the lookup: drop entries whose `fetched_at` is older than `2 × _TTL_BY_STATE[entry.state]`; if `len(_cache) > _CACHE_MAX_ENTRIES`, drop the oldest `fetched_at` entries down to the cap. LRU is unnecessary — TTL does the real work and the cap only bounds a pathological league count.
- **Single-flight:** a miss acquires `_inflight[key]` (created under `_cache_lock`), re-checks the cache after acquiring (double-checked), then fetches. N concurrent viewers ⇒ 1 upstream read (D6). The `_inflight` entry is removed under `_cache_lock` when the last waiter releases.
- **Budget:** `budget` is a deque of monotonic timestamps of upstream fetches; an entry older than 60 s is popped on access; a fetch is refused (→ serve stale + `degraded.reason="budget_exceeded"`) when `len(budget) >= _BUDGET_PER_MIN`. This is the mechanical enforcement of D6, not a comment.

### 3.2 The pre-scope snapshot (M2) — and the bug it must not walk into

**Storage:** a sibling key inside the existing `users.tier_overrides` JSON column (`database.py:179`), per the plan. Shape:

```json
{
  "1qb_ppr": { "<pid>": 1712.4, ... },
  "sf_tep":  { "<pid>": 1688.0, ... },
  "__pre_rookie_scope__": {
    "v": 1,
    "taken_at": "2026-08-14T18:03:11.204Z",
    "reason": "pre_scope_v1",
    "formats": { "1qb_ppr": { "<pid>": 1712.4, ... }, "sf_tep": { ... } }
  }
}
```

> ### 🔴 BLOCKING PRECONDITION — the snapshot is destroyed by the very next save unless this lands first
> `database._parse_per_format_json` (`database.py:3188-3208`) seeds its output with **only** `SCORING_FORMATS` keys and copies **only** those keys out of the parsed JSON. `save_tier_overrides` (`:3269-3298`) round-trips the column through it (`all_overrides = _parse_per_format_json(...)` at `:3291`, `json.dumps(all_overrides)` at `:3297`). **Any sibling key is silently dropped on the first subsequent save of either format.** The plan's storage decision is sound; its mechanism is not yet true of the code.

**Required change (M2, first commit of the wave), in `backend/database.py`:**

```python
def _parse_extra_keys(raw: str | None) -> dict:
    """Top-level keys of a per-format JSON column that are NOT scoring formats.

    _parse_per_format_json deliberately narrows to SCORING_FORMATS; writers that
    round-trip the column must merge these back or they silently delete them
    (the #? pre-scope snapshot lives here).
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items() if k not in SCORING_FORMATS}
```

and in `save_tier_overrides`, between `:3291` and `:3294`:
```python
extras = _parse_extra_keys(row.tier_overrides if row else None)
...
.values(tier_overrides=json.dumps({**extras, **all_overrides}))
```
`{**extras, **all_overrides}` (extras first) guarantees a format key can never be shadowed by an extra. **Test T-M2-01 proves a sibling key survives 3 alternating-format saves.** Do **not** apply the same treatment to `tiers_saved`/`anchor_scale` — no requirement needs it, and surgical-changes applies.

**API:**
```python
# backend/database.py
def take_tier_override_snapshot(user_id: str, reason: str = "pre_scope_v1") -> bool:
    """One-shot. Returns False (no-op) if __pre_rookie_scope__ already exists."""

def load_tier_override_snapshot(user_id: str) -> dict | None:
    """The stored snapshot object, or None."""

def restore_tier_overrides_from_snapshot(user_id: str,
                                         scoring_format: str | None = None) -> dict[str, int]:
    """Operator restore. scoring_format=None restores both. Returns per-format
    counts. Does NOT delete the snapshot (restore must be repeatable)."""
```

**Call site:** `take_tier_override_snapshot(user_id)` runs in the `POST /api/tiers/save` handler **before** `service.apply_tiers*`, only when `scope == "rookie"`. It is idempotent, so it costs one indexed read per scoped save after the first.

**Operator restore procedure** (goes in `docs/runbook.md` as a new `## Rookie-scope board restore` section):
1. Confirm the damage window from the user's `via:'rookie_*'` events in `user_events`.
2. `python3 -c "from backend.database import load_tier_override_snapshot as l; print(l('<user_id>'))"` — verify `taken_at` predates the window.
3. `python3 -c "from backend.database import restore_tier_overrides_from_snapshot as r; print(r('<user_id>'))"`.
4. Have the user re-init their session (`POST /api/session/init`) — in-memory `_elo_overrides` are only re-read at `server.py:11752`.
5. **Known void:** `reset_user_rankings` sets `tier_overrides=None` (`database.py:3349`), which deletes the snapshot with the board. That is correct (the user asked for a clean slate) but it means the restore path does not survive a self-service reset. State this in the runbook.

### 3.3 Invariants

- **I-1 (Elo identity, D2):** for every rookie pid, `scoped_elo(pid) == unscoped_elo(pid)` exactly. Proven by T-M2-02.
- **I-2 (write shape, D2):** `apply_reorder`/`apply_anchor` under scope produce byte-identical `_elo_overrides` to the same call unscoped on that subsequence. Proven by T-M2-03. *(They already do — `ranking_service.py:1362-1387`, `:1327-1343`. The test pins it against future edits; no code change.)*
- **I-3 (no respread, D3):** after a scoped tier save, every `_elo_overrides` entry for a pid **not** in scope is byte-identical to its pre-save value; a non-rookie with no override before has none after. Proven by T-M2-04 (**verify-failing-first**).
- **I-4 (completeness markers untouched):** a scoped save never calls `save_tiers_position`; `get_tiers_saved` returns the same list before and after; `GET /api/tiers/status.all_done` is unchanged. Proven by T-M2-05 (**verify-failing-first**).
- **I-5 (no cross-user blast):** the scoped save publishes the **full** board via `upsert_member_rankings` exactly as the unscoped save does (`server.py:6410-6424`), and never passes a scope into it. Proven by T-M2-06.
- **I-6 (membership-only bumps, D1):** a generation bump changes the pool member set; every pid present both before and after retains its prior seed Elo. Proven by T-M0-04.
- **I-7 (board is never sourced from `draft_picks`):** `draft_board_service` does not import `load_draft_picks` for the `live`/`complete` board. Proven by T-M3-07 (import-graph/AST assertion, the analytics T-2 pattern).
- **I-8 (no platform writes, D9):** `draft_board_service` contains no `POST`/`PUT` and does not import `sleeper_write`. Proven by T-M3-08 (grep/AST).

---

## 4. Core Logic — per milestone

### 4.0 M0 — Data foundation (BE, solo wave, blocks everything rookie)

**File placement:** all in `backend/server.py` (it owns the cache globals and HTTP), except the measurement script.

```python
# backend/server.py — near _load_sleeper_cache (server.py:406)

def _players_cache_age_seconds() -> float | None:
    """Age of the on-disk cache file, or None when it does not exist."""

def _refresh_players_cache_async(force: bool = False) -> bool:
    """Start ONE background refresh. Returns True iff a thread was started.
    Never blocks; never raises. No-ops when FTF_PLAYERS_REFRESH == '0', when a
    refresh is already active, or when the cache is younger than the TTL and
    force is False."""

def _players_refresh_worker() -> None:
    """Daemon body. Fetch → atomic write → ordered invalidation → bump."""

def _fetch_players_bulk() -> dict:
    """GET /v1/players/nfl, filtered to QB/RB/WR/TE with full_name — the SAME
    filter as _ensure_sleeper_cache_populated (server.py:11449-11453). Routed
    through the fixture seam (see [RV-3])."""

def _atomic_write_players_cache(relevant: dict) -> None:
    """tempfile.NamedTemporaryFile(dir=PLAYERS_CACHE_FILE.parent, delete=False)
    → write → flush → os.fsync → os.replace(tmp, PLAYERS_CACHE_FILE).
    Same-directory temp is required: os.replace is only atomic within a
    filesystem. No reader can ever observe a partial file."""

def _invalidate_player_pipeline(relevant: dict) -> None:
    """THE ordered invalidation (plan §M3/M0). Order is load-bearing."""

def pool_generation() -> int: ...
def _bump_pool_generation() -> int: ...
```

**`_invalidate_player_pipeline` — exact order (each step's *why* is why the order is fixed):**

1. **Disk** — already written atomically by the caller. Doing this first means a crash anywhere below still leaves the next boot with fresh data.
2. **`_sleeper_cache` global** — `global _sleeper_cache; _sleeper_cache = relevant`. A single assignment; Python's GIL makes it atomic for readers at `server.py:409`.
3. **`sync_players(relevant, adp_map=_fetch_sleeper_adp() or None)`** under `_player_sync_lock` (`server.py:1482`). Call it **directly**, bypassing `needs_player_sync()` — we know the data is new, and the gate would skip (`database.py:6684-6705`). `sync_players` stamps `last_synced` itself (`database.py:6809`), so no manual reset is needed. **[RV-4]** re-check that `sync_players` still stamps `last_synced`; if it stops, the gate must be reset explicitly.
4. **DP value maps** — `dp_values_by_format.clear()`, `dp_elo_by_format.clear()`, `dp_pos_by_format.clear()`, `_dp_fetch_retry_at.clear()`. These are *inputs* to the build; clearing them is safe because nothing reads them outside `_ensure_universal_pools`.
5. **Pools — build-new-then-rebind, never clear-in-place.** Under `_pool_build_lock`:
   ```python
   new_by_format = {}                       # build into a LOCAL dict
   for fmt in DL_SCORING_FORMATS:
       players, seed = build_universal_pool(...)      # server.py:1175
       if players:
           new_by_format[fmt] = {"players": players, "seed": seed}
   if not new_by_format:
       return                               # keep the previous world entirely
   prior = dict(g_universal_by_format)
   g_universal_by_format.update(new_by_format)        # rebind, per format
   # legacy aliases: REBIND, do not clear-in-place (server.py:1403-1407)
   default = g_universal_by_format.get("1qb_ppr", {})
   g_universal_players[:] = default.get("players", [])
   g_universal_seed.clear(); g_universal_seed.update(default.get("seed", {}))
   dp_values.clear();        dp_values.update(dp_values_by_format.get("1qb_ppr", {}))
   ```
   The three legacy aliases are the one place a clear-then-update is unavoidable (external code holds references to the objects). They are rebound **last**, after `g_universal_by_format` is already consistent, and the window is a few microseconds of pure Python with no I/O. `_get_universal_pool` (`server.py:1416-1424`) reads `g_universal_by_format`, not the aliases, so no request path observes the window. **[RV-5]** if any new reader of `g_universal_seed`/`dp_values` has appeared, re-evaluate: those two are the only torn-read surface in the design.
6. **Bump** — `_bump_pool_generation()` under `_pool_build_lock`, **after** the rebind. Marking stale before the new world exists would send a session boundary to a half-built pool.

**Single-flight on `_ensure_universal_pools`** — wrap the existing body (`server.py:1316-1407`):
```python
def _ensure_universal_pools() -> None:
    if g_universal_by_format.get("1qb_ppr") and g_universal_by_format.get("sf_tep"):
        return                                   # unchanged fast path, no lock
    with _pool_build_lock:
        if g_universal_by_format.get("1qb_ppr") and g_universal_by_format.get("sf_tep"):
            return                               # double-checked
        ...existing body...
```
This is the fix for the race the plan names: `_player_sync_lock` guards syncs only, so the refresh daemon and a request worker could otherwise each fan out a DP fetch (`server.py:1364-1381`).

**Generation → session boundary (I-1 of the HLD).** At `server.py:11688`:
```python
existing_generation = existing_sess.get("pool_generation") if existing_sess else None
current_generation  = pool_generation()
user_changed = existing_services is None or existing_tagged_user != user_id
gen_changed  = existing_services is not None and existing_generation != current_generation
need_rebuild = user_changed or gen_changed
```
and store `sess["pool_generation"] = current_generation` wherever the session dict is written.

**Rule G-SEED (D1's "existing members carry their prior seed Elo forward"):** `_build_service_for_format` (`server.py:11693`) takes a new optional parameter `carry_seed: dict[str,float] | None`.
- **User-change rebuild** ⇒ `carry_seed=None` ⇒ `seed_ratings = fmt_seed` — today's behavior, byte-identical.
- **Generation-change rebuild** ⇒ `carry_seed = prior_service._seed` ⇒ `seed_ratings = {pid: carry_seed.get(pid, fmt_seed[pid]) for pid in fmt_seed}`. New members get fresh seeds; existing members carry theirs. Re-seeding of existing members therefore stays on the user-change cadence, exactly as D1 words it.

**Pinned rookie predicate.** `load_rookie_player_ids(season)` (`database.py:6915`) is THE predicate. Memoise per `(season, pool_generation())` in a module dict so a scoped request costs one indexed scan per generation, not per request. Record the invariant in `docs/cross-client-invariants.md` (§6).

**Dev cache-age guard.** At the top of the scoped path (M2 consumes it, M0 provides it):
```python
def _rookie_scope_allowed() -> tuple[bool, str | None]:
    if _TEST_MODE:                       # server.py:457 — the Maestro harness pins the cache file
        return True, None
    if _IS_PROD_ENV:
        return True, None
    age = _players_cache_age_seconds()
    if age is not None and age > 7 * 86_400:
        return False, "stale_player_cache"
    return True, None
```
Also log the cache-file mtime at boot, beside the existing `_load_sleeper_cache()` call at `server.py:17911`.

**Class-load monitor.** In `cron_daily_tick`, one query: `SELECT 1 FROM players WHERE rookie_year = :next_season LIMIT 1`. First non-empty result ⇒ `log.warning("CLASS-LOAD %s rookie class has appeared", next_season)` + a counter. One-shot per process; the log line is the alert (there is no pager).

**Measurement script (blocks all UI, per the M0 done bar).** `backend/scripts/measure_rookie_pool.py` — for each scoring format × position, count pool members with `rookie_year == season` and DP value > 0. Writes `docs/plans/rookie-draft/measurements-2026-08.md`. **Abort criterion:** any format with <15 valued rookies ⇒ rookie scope ships for Pick Anchors + Tiers only and the Draft Room becomes the primary deliverable (plan §6).

---

### 4.1 M1 — Draft replay & fixture harness (BE, parallel with M0)

**Sleeper half — rides the existing seam.** `_sleeper_fixture_path` (`server.py:476-478`) maps a URL to `<FTF_SLEEPER_FIXTURES_DIR>/<path-after-v1>.json`, so recording is free for every draft endpoint:

```
$FTF_SLEEPER_FIXTURES_DIR/
  league/<league_id>/drafts.json          # GET /v1/league/<id>/drafts
  league/<league_id>/traded_picks.json    # GET /v1/league/<id>/traded_picks
  league/<league_id>/rosters.json
  draft/<draft_id>.json                   # GET /v1/draft/<id>          (the 1.2 KB detail object)
  draft/<draft_id>/picks.json             # GET /v1/draft/<id>/picks    (the 20 KB pick list)
```

Named corpora (committed under `backend/tests/fixtures/draft/`, copied into a temp dir per test):
| Corpus | Pins |
|---|---|
| `lakeview-complete/` | 48 picks + `traded_picks` + populated `draft_order`; D5's complete-board case |
| `ffv3-predraft/` | `draft_order: null`, `start_time: null`, `last_picked: null`; **the identity `slot_to_roster_id` trap** |
| `empty-drafts/` | `drafts.json == []`; the ambiguous read (`server.py:9186-9202`) |
| `startup-shaped/` | `settings.rounds: 28`; the labeled-and-degraded path |

> **[RV-3] — the plan's implied mechanism does not cover the bulk players fetch.** `_ensure_sleeper_cache_populated` fetches `/v1/players/nfl` with **raw urllib** (`server.py:11439-11444`) and says so out loud (`:11431-11436`); only `_sleeper_get` consults the fixture dir. **M0's refresh must therefore route `_fetch_players_bulk` through `_sleeper_get`** (the URL already matches the `api.sleeper.app/v1/` prefix, so the cassette lands at `players/nfl.json` with no other change), **or** carry its own hermetic override. Route it through `_sleeper_get`; that is one line and it makes M0 replayable and keeps the `FTF_TEST_MODE` egress rail honest.

> **[RV-6] — record mode refuses a non-empty dir.** `server.py:469-473` exits if `FTF_SLEEPER_RECORD=1` and the fixtures dir already holds any `**/*.json`. Record **one corpus per dir**, then move it under `backend/tests/fixtures/draft/`.

**MFL half — a different mechanism.** `mfl_service` has **no** env fixture seam; it injects `_opener` (`mfl_service.py:281-303`) and the repo's existing MFL tests use a committed snapshot (`backend/tests/fixtures/mfl_league_snapshot_2026-07-17.json`). MFL corpora are therefore committed JSON + an `_opener` stub:
```
backend/tests/fixtures/draft/mfl-<case>/draftResults.json   # made==0 | partial | complete | multi-draftUnit
```
`draft_board_service`'s MFL path must accept an injectable `_opener` all the way down (M5, §4.5), or M5 is untestable.

**Replayer.** `backend/tests/support/draft_replay.py`:
```python
class DraftReplay:
    def __init__(self, corpus_dir: Path, tmp_dir: Path): ...
    def truncate_picks(self, k: int) -> None:
        """Rewrite draft/<id>/picks.json to the first k picks and set the detail
        object's last_picked to pick k's timestamp (or None when k == 0), so the
        poll-detail-then-fetch-picks logic sees a genuine in-progress draft."""
    def set_status(self, status: str) -> None:      # pre_draft | drafting | complete
    def advance(self, n: int = 1) -> None:          # truncate_picks(current + n)
    @property
    def env(self) -> dict[str, str]:                # {"FTF_SLEEPER_FIXTURES_DIR": str(tmp_dir)}
```
Fake clock: tests monkeypatch `draft_board_service._now_monotonic` (a module-level indirection introduced for exactly this) rather than `time.monotonic`, so TTL expiry is deterministic without patching the stdlib.

**Done bar:** the replayer drives the full M3–M5 matrix; `truncate_picks(k)` for k ∈ {0, 1, 24, 48} reproduces every state deterministically in CI.

---

### 4.2 M2a — The rookie-scope seam (BE solo wave; after M0)

**File placement:** the seam lives in `server.py` (response/selection layer). `ranking_service.py` gains exactly **one** new method (§4.3) and nothing else.

```python
# backend/server.py — beside _apply_pick_rung_year_labels (server.py:4835)

def _requested_scope(sess) -> str | None:
    """'rookie' or None. Returns None unconditionally when ranks.rookie_subset
    is off — the parameter is never read, which is how D4 holds structurally."""
    if not is_enabled("ranks.rookie_subset"):
        return None
    raw = request.args.get("scope")
    if raw is None:
        return None
    if raw != "rookie":
        abort(400, "bad_scope")
    return "rookie"

def _rookie_scope_ids(sess) -> set[str]:
    """Player ids in scope for the session league's season, PLUS the generic
    pick rungs (O10 = YES, year-labeled, listed after players)."""
    season = _scope_season(sess)                  # league season, else current NFL season
    ids = _rookie_ids_memo(season)                # memoised per (season, pool_generation())
    return ids | set(GENERIC_PICK_IDS)            # pick_values.GENERIC_PICK_SEEDS keys → pick ids

def _apply_rookie_scope(rankings: list[dict], sess) -> list[dict]:
    """THE seam. Filters an ALREADY-COMPUTED, ALREADY-ENRICHED response list.
    Players first (original relative order preserved), then pick rungs.
    Re-numbers `rank` 1..n over the filtered list; every other field untouched."""
```

**Insertion point in `get_rankings` (`server.py:5241-5311`)** — after the `#207` relabel and both enrichment blocks, immediately before `jsonify`:
```python
scope = _requested_scope(sess)
if scope == "rookie":
    ok, reason = _rookie_scope_allowed()
    if not ok:
        return jsonify({"empty": True, "reason": reason, "position": position,
                        "scope": "rookie", "count": 0})
    rankings = _apply_rookie_scope(rankings, sess)
    if not rankings:
        return jsonify({"empty": True, "reason": "class_not_loaded", ...})
```
Placing the filter **after** the enrichments is deliberate: the consensus-rank and tile-score blocks (`server.py:5257-5303`) are keyed by pid and are already best-effort, so filtering first would only save work while creating a second place that has to know about scope.

**Trios (`server.py:4857`).** Scope filters **candidate selection**, never the Elo update. Two edits:
1. Pass a scope-derived exclusion into `service.get_next_trio(position, skipped_player_ids=skipped | non_scope_ids)`. Reusing the existing `skipped_player_ids` channel means no new parameter threads through `_boundary_trio`/`_within_tier_trio`/`_algorithmic_trio`, and those lanes already honour it (`ranking_service.py:388-389`).
2. **Lane audit (the plan's explicit requirement).** Two lanes bypass that channel:
   - `_cross_position_trio` (`ranking_service.py:586`) reaches across the full pool by design and is selected at `ranking_service.py:412-417`. **Under scope, `_pick_trio_variety` must not return `cross_pos`.** Simplest correct form: pass `scoped: bool` into `_pick_trio_variety` and drop `cross_pos` from its weight table when true.
   - The QC-trio path (`server.py:4882-4911`) builds its own `_pool` at `:4893` and filters only `skipped_ids` at `:4894-4895`. **Under scope, either apply the same scope filter at `:4895` or skip the QC branch entirely.** Skipping is the smaller change and QC compliments on a thin rookie pool are low-value; do that, and record it as a deliberate degradation.
3. Thin pool: catch the `ValueError` from `ranking_service.py:391-392` **only on the scoped path** and return the typed `200 {empty:true, reason:"thin_pool", count:n}`. The unscoped `except Exception → 400` at `server.py:4964-4966` is untouched.

**Rankings submit / reorder / anchor.** No scope parameter and no change: `apply_reorder` (`ranking_service.py:1345`) and `apply_anchor` (`:1327`) are already subset-safe, and the route already filters submitted ids to the pool. **Do not "fix" them** (plan, verbatim). The only client-visible difference is that the submitted subset happens to be rookies.

---

### 4.3 M2b — The merged-band tier save (BE, same solo wave)

**New method** in `backend/ranking_service.py`, immediately after `apply_tiers` (`:1261-1325`). `apply_tiers` itself is **not modified** — that is how D4's byte-identity is guaranteed on the unscoped lane.

```python
def apply_tiers_subset(
    self,
    position: Optional[str],
    tiers: dict[str, list[str]],
    scope_pids: set[str],
    scoring_format: str = "1qb_ppr",
    cleared_pids: Optional[list[str]] = None,
    demoted_pids: Optional[list[str]] = None,
) -> dict[str, list[str]]:
    """Scoped tier save — the merged-band rule (plan D2/D3).

    Returns {tier_name: merged_full_band_order} so the ROUTE can assert the
    equivalence bar without recomputing the merge (see T-M2-07).
    """
```

**The equivalence bar, stated so it is testable.** Define, per tier, the *merged full-band order* `M`. The bar is:

> A scoped save with submitted scoped order `S` must leave every scoped pid at exactly the Elo that `apply_tiers(position, {tier: M}, ...)` would give it, and must leave every non-scoped pid's override byte-unchanged.

T-M2-07 implements this literally: it computes `M`, clones the service, runs the unscoped `apply_tiers` with `M` on the clone, and diffs.

**Constructing `M` (pseudocode; the whole algorithm):**

```
apply_tiers_subset(position, tiers, scope_pids, fmt, cleared_pids, demoted_pids):

    pool      = self._pool(position)                  # FULL position pool — never filtered
    pool_ids  = {p.id for p in pool}
    bands     = self.tier_bands_for(position, fmt)    # ranking_service.py:1208
    current   = self._compute_elo(pool)               # FULL-pool Elo — every rookie-vs-vet swipe

    def value_of(pid):                                # "where this pid sits right now"
        return self._elo_overrides.get(pid, current[pid])

    # ── clears and demotions, SCOPED (D3 / #161 / O4) ────────────────────
    for pid in (cleared_pids or []):
        if pid in scope_pids:                         # a clear for an unshown vet is ignored
            self._elo_overrides.pop(pid, None)
    for pid in (demoted_pids or []):
        if pid in scope_pids and pid in pool_ids:     # only VISIBLE, scoped, unselected pids
            self._elo_overrides[pid] = self.DEMOTED_ELO      # 1100.0, ranking_service.py:1259

    merged_orders = {}
    for tier_name, submitted in tiers.items():
        band = bands.get(tier_name)
        if band is None:
            continue
        lo, hi = band

        scoped = [pid for pid in submitted if pid in pool_ids and pid in scope_pids]
        if not scoped:
            continue                                  # nothing to write for this tier

        # 1. INCUMBENTS — current full-band membership, minus everything in scope.
        incumbents = [pid for pid in pool_ids
                      if pid not in scope_pids and lo <= value_of(pid) <= hi]
        incumbents.sort(key=lambda p: (-value_of(p), p))          # value desc, pid asc = deterministic

        # 2. ANCHOR the scoped block by its CURRENT values, clamped into the band.
        #    A promotion (current > hi) anchors at the top; a demotion (< lo) at
        #    the bottom. Ties resolve to the user's submitted order.
        anchors = {pid: min(max(value_of(pid), lo), hi) for pid in scoped}

        # 3. MERGE two descending sequences into positional slots.
        M = []
        i = 0                                          # incumbent cursor
        for pid in sorted(scoped, key=lambda p: (-anchors[p], scoped.index(p))):
            while i < len(incumbents) and value_of(incumbents[i]) > anchors[pid]:
                M.append(incumbents[i]); i += 1
            M.append(("SCOPED_SLOT",))                 # placeholder — filled in step 4
        M.extend(incumbents[i:])

        # 4. FILL the scoped slots, top-to-bottom, with the USER'S submitted order.
        it = iter(scoped)                              # `submitted` order, pool-filtered
        M = [next(it) if s == ("SCOPED_SLOT",) else s for s in M]

        # 5. SPREAD over the FULL merged list — arithmetic IDENTICAL to apply_tiers:1319-1323
        n = len(M)
        for idx, pid in enumerate(M):
            v = hi if n == 1 else hi - (hi - lo) * idx / (n - 1)
            # 6. PERSIST SCOPED PIDS ONLY. This line is the whole of D3.
            if pid in scope_pids:
                self._elo_overrides[pid] = v

        merged_orders[tier_name] = M

    self._version += 1
    return merged_orders
```

**Why each step is what it is** (so a reviewer can catch a "simplification"):
- Step 1 excludes scope from incumbents so a pid can never appear twice in `M`.
- Step 2's clamp is what makes a *promotion into the tier* well-defined; without it a scoped pid outside the band has no merge position and the algorithm is undefined.
- Step 3's tie-break `scoped.index(p)` keeps the user's submitted order authoritative among equal anchors.
- Step 5 spreads over `len(M)`, **not** `len(scoped)` — spreading over the scoped list alone is the "naive scoped-list spread" the plan rejects, and it silently promotes every rookie to the top of the band.
- Step 6 is the only write. Removing the `if` produces the "full-band persist" the plan also rejects, which rewrites every untouched member.
- **RB-7 (plan round 4, non-blocking):** because incumbents are positioned but not rewritten, a partial save can cosmetically invert against stale neighbours until the next full-band save. This is inherent to any partial save; it belongs in the build PRD's copy, not in the algorithm.

**Route wiring** in `save_tiers_route` (`server.py:6342-6495`):
```python
scope = body.get("scope") if is_enabled("ranks.rookie_subset") else None
if scope == "rookie":
    take_tier_override_snapshot(g_user_id)                 # §3.2 — BEFORE any mutation
    service.apply_tiers_subset(position=position, tiers=tiers,
                               scope_pids=_rookie_scope_ids(sess), scoring_format=fmt,
                               cleared_pids=cleared_pids, demoted_pids=demoted_pids)
else:
    service.apply_tiers(...)                               # server.py:6393-6399, untouched
```
Everything from `save_tier_overrides` (`:6404`) through `_record_trends_snapshot` (`:6436`) is **shared and unchanged** — including the full-board `upsert_member_rankings` publish (I-5).

**The exclusion (I-4).** Replace `server.py:6440-6441` with:
```python
if scope == "rookie":
    saved = get_tiers_saved(g_user_id, scoring_format=fmt)     # READ, never write
else:
    saved = save_tiers_position(g_user_id, position, scoring_format=fmt)
all_done = all(p in saved for p in ("QB", "RB", "WR", "TE"))
```
**[RV-7]** re-verify at build time that `save_tiers_position` still has no other caller that a scoped save reaches. A scoped save marking a position complete cascades into `LeagueScreen`'s ranked count, `quicksetProgress`'s cache (`mobile/src/state/quicksetProgress.ts`), the web celebration, and **#244 launch routing** (`mobile/src/navigation/TabNav.tsx:217-225`) — four surfaces, one line.

**Client half (M2, MOB batches).** ONE shared scope control, modelled on `mobile/src/navigation/rankChooserModel.ts` (one exported model, two consuming surfaces, "so the two can never diverge"). Session-only state (#133 precedent) — never persisted, never a flag. Rollout ladder: **Anchors → Tiers → Quick Set → Overall/Quick Rank (inherit) → Trios last**, Trios gated on M0's measurement. Quick Set under scope starts the ladder at the first rookie-bearing rung and **must not** write `quicksetCompletedPositions` (`mobile/src/screens/QuickSetTiersScreen.tsx:192-197`) — the mirror of I-4 on the client.

---

### 4.4 M3 — `backend/draft_board_service.py` (BE; after M1; 2 batches)

**Batch 1 — payload + states.** **Batch 2 — cache + breaker + budget.**

```python
# backend/draft_board_service.py  (NEW — flat module, beside ranking_service.py; KD-1)

SCHEMA = 1

@dataclass(frozen=True)
class BoardRequest:
    league_id: str
    platform: str
    season: int
    user_id: str
    basis: str = "consensus"                 # "consensus" | "my_board"
    board_elo: dict[str, float] | None = None    # caller-supplied; None ⇒ consensus

def build_board(req: BoardRequest, fetchers: "Fetchers") -> dict:
    """THE entry point. Returns the schema:1 payload. Never raises; never writes."""

class Fetchers(Protocol):
    """Injected by the route so this module is import-free of Flask and of
    server.py's HTTP helpers — and so M1's corpora can drive it directly."""
    def drafts(self, league_id: str) -> list[dict]: ...
    def draft_detail(self, draft_id: str) -> dict | None: ...
    def draft_picks(self, draft_id: str) -> list[dict]: ...
    def traded_picks(self, league_id: str) -> list[dict]: ...
    def rosters(self, league_id: str) -> list[dict]: ...
    def mfl_draft_results(self, league_id: str, year: int, host: str) -> dict | None: ...

# ── internals ────────────────────────────────────────────────────────────
def _classify(detail: dict, rounds: int | None, teams: int | None) -> tuple[str, str]:
    """→ (state, kind). state from detail['status'] ('pre_draft'|'drafting'|
    'complete', treated as an OPEN set — anything unrecognised is 'upcoming');
    kind from the rounds shape via draft_status.ROOKIE_MAX_ROUNDS/STARTUP_MIN_ROUNDS."""

def _order_from(detail: dict, traded: list[dict], rosters: list[dict]) -> tuple[list[dict], str]:
    """→ (order[], order_confidence). Returns ([], 'unset') when
    detail.get('draft_order') is None — NEVER reads slot_to_roster_id (D5)."""

def _undrafted(season: int, drafted_ids: set[str], rostered_ids: set[str],
               basis: str, board_elo: dict | None) -> list[dict]:
    """D7: load_rookie_player_ids(season) − drafted − rostered, ordered by
    consensus seed or the caller's board. Unvalued rows keep valued=False and
    sort LAST (value None), never dropped."""

def _now_monotonic() -> float:     # indirection so M1's fake clock can patch it
    return time.monotonic()
```

**The poll rule (D6/KD-8), exact:**
```
on a cache miss or expired entry, under the per-key single-flight lock:
    if budget exhausted → serve stale, degraded.reason = "budget_exceeded", return
    detail = fetchers.draft_detail(draft_id)              # ~1.2 KB, s-maxage 30
    if detail is None → fails += 1; serve stale or state="unavailable"
    if detail["last_picked"] != entry.last_picked or entry.picks is None:
        picks = fetchers.draft_picks(draft_id)            # ~20 KB — ONLY on change
        entry.picks = picks
    entry.last_picked = detail["last_picked"]
    entry.as_of = _now_iso(); entry.fails = 0; entry.budget.append(_now_monotonic())
```
**Never poll `/picks` directly** — complete drafts are CDN-cached ~24 h, so a direct poll reads a stale list while believing it is live. **ASSUMPTION (plan-verified live):** the CDN TTLs; M3's first task is to re-confirm them against one live read plus the corpora.

**Breaker:** `fails >= _BREAKER_FAILS` ⇒ `opened_until = _now_monotonic() + _BREAKER_OPEN_SECONDS`; while open, no upstream call, `degraded.reason = "breaker_open"`, `stale = True`. One success closes it.

**Divergence rule, enforced structurally:** `draft_board_service` does **not** import `load_draft_picks`. `order[]` for the `upcoming` state is built from `traded_picks` + `rosters`; `draft_picks` rows are read **only** by the route shim, and only for the pre-draft ownership overlay, and are passed in — never fetched inside this module. T-M3-07 asserts the import graph. This is what prevents the #228 finish-line emptying (`server.py:8149-8156`, `:8078-8079`).

**Route shim in `server.py`** (~15 lines): resolve session + league, build `Fetchers` from the existing `_fetch_sleeper_drafts` (`:9186`), `_fetch_sleeper_traded_picks` (`:9170`), `_fetch_league_rosters`, plus two new one-liners `_fetch_sleeper_draft_detail(draft_id)` / `_fetch_sleeper_draft_picks(draft_id)` wrapping `_sleeper_get` (which gives fixture replay for free, A-7), call `build_board`, `jsonify`.

---

### 4.5 M4 — Draft Room UI (MOB; after M3; 2 batches)

**Route registration** — `mobile/src/navigation/RootNav.tsx`: add `DraftRoom: undefined;` to the `AuthStack` type (beside `FreeAgents` at `:54`) and a `<Stack.Screen name="DraftRoom" .../>` copying the `FreeAgents` block at `:485-508` **including the `headerBackVisible:false` + custom `HeaderBack` #151/RNS#3294 workaround** (`:492-497`) — omitting it leaves iOS 26 back dead.

**Entry point (O1, conditional replacement).** `mobile/src/screens/LeagueScreen.tsx:96` currently reads `useFlag('league.rookie_board_entry')` and `:513-522` renders the tile that opens `RookieDraftBoardSheet`. Change to:
```tsx
const showDraftRoom  = useFlag('draft.room');
const showRookieBoard = useFlag('league.rookie_board_entry');
// draft.room ON  → "Rookie draft" tile → navigation.navigate('DraftRoom')   (the :509 precedent)
// draft.room OFF → today's "Rookie board" tile, unchanged                    (no user is stranded)
```
Leave the `RookieDraftBoardSheet` mount at `:662-669` in place — it is deliberately outside the flag so an in-flight open survives a flag revalidation.

**FeedbackFAB:** root-stack pushes mount their own — `<FeedbackFAB activeScreen="DraftRoom" aboveTabBar={false} />`, the `FreeAgentsScreen.tsx:275` pattern.

**Reusable patterns:** the Consensus | My-board toggle is `BasisChip` (`mobile/src/screens/LeagueSummaryScreen.tsx:1017`, rendered `:592-610`) — screen-local, so copy it or extract it; the fallback notice is `FreeAgentsScreen.tsx:238-243` + the `consensusNote` style at `:594`.

**Live polling — behind `draft.live_poll`, separate flag.**
```tsx
useQuery({
  queryKey: ['draft-board', leagueId, basis],
  queryFn:  () => getDraftBoard(leagueId, basis),
  refetchInterval: (q) =>
    livePollEnabled && isFocused && appActive && q.state.data?.state === 'live' ? 15_000 : false,
  refetchIntervalInBackground: false,          // explicit; the default is already false
});
```
> **[RV-8] — this is the app's FIRST recurring poll.** `refetchInterval` has **zero** occurrences in `mobile/` on `origin/main`, and the app-wide default is `refetchOnWindowFocus: false` (`mobile/src/state/queryClient.ts:21-33`). Three gates are required and all three must be verified by instrumentation, not by reading the code: `livePollEnabled` (flag), `isFocused` (`useIsFocused` — note `useFocusEffect` has exactly one call site in the app today), and `appActive` (AppState, wired at `mobile/App.tsx:185-202`). **QA pass threshold for background/blur is literally ZERO requests.** A manual **Refresh** control is always present, flag on or off.

**Designed states** (each a distinct render, none a spinner): `order_not_set`, `startup_draft` ("Startup draft — rookie list hidden"), `platform_unsupported`, `class_not_loaded` ("The 2027 class loads after the NFL draft (late April). Showing last year's class" + toggle), `stale` (`as_of` always visible), `unavailable`.

**M4 also retires `/api/rookies`** (I-2): delete `getRookies` (`mobile/src/api/rankings.ts:349-352`) and `RookieDraftBoardSheet` once `draft.room` is flipped on and stable — a separate, post-flip commit, not part of the wave.

---

### 4.6 M5 — MFL parity (BE; after M3's contract freezes; 1 batch)

Same `schema:1` payload from `TYPE=draftResults`. `mfl_service.fetch_draft_results` already exists (`mfl_service.py:337-362`) and is already used by #207 (`server.py:9331-9332`).

```python
# backend/draft_board_service.py
def _board_from_mfl(results: dict, league_size: int, franchise_to_user: dict[str,str]) -> dict:
    """draftUnit may be a dict OR a list (division/conference drafts) — aggregate
    with mfl_service._as_list (mfl_service.py:423), mirrored by draft_status._as_list
    (draft_status.py:231-236). made = count(player != ''); total = len(draftPick).
    MFL pre-populates the grid, so EVERY unmade pick carries its franchise — which
    makes MFL's pre-draft order strictly better than Sleeper's."""
```
- `state`: `made == 0` ⇒ `upcoming` · `0 < made < total` ⇒ `live` · `made == total` ⇒ `complete`. `order_confidence` is `assigned` whenever every pick carries a franchise.
- `kind`: `total / franchises` vs the same 8/15 round thresholds (`draft_status.py:270-274` does this already).
- `liveDraft` is dead (**ASSUMPTION (plan-verified live)**); `draftResults` + per-pick `timestamp` **is** the live feed. Server poll 30 s; honour `mfl_service._REQUEST_SPACING_SECONDS = 1.0` (`mfl_service.py:71`).
- Auth failure ⇒ stored snapshot + `notice.code = "mfl_reconnect"` + `stale:true`. **Never stale-as-live.**
- **`draft.mfl` live mode is gated** on a timed probe against a genuinely drafting MFL league (mid-draft update latency is UNVERIFIED). Until then MFL ships `upcoming` + manual refresh.
- **Testability requirement (RB-3):** thread `_opener` from `build_board` down to `fetch_draft_results` (which already accepts it, `mfl_service.py:339`), or M5 cannot be tested against the committed corpora.

---

### 4.7 M6 — Slot values, display-only (BE; after M3; not on the critical path)

```python
# backend/data_loader.py — beside VALUES_URL (data_loader.py:60)
PICK_VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv"

def load_pick_slot_values(scoring: str = DEFAULT_SCORING) -> dict[str, float]:
    """{'2026 Pick 1.01': 1817.0, ...} → seed-Elo space via seed_elo_for_value
    (data_loader.py:83). Same 24 h in-memory TTL as the KTC blend. Fetch failure
    → {} (the field is simply absent from the board payload)."""
```

> **Hermetic seam is a precondition.** `FTF_TEST_MODE` today only pins `values-players.csv` via `FTF_DP_VALUES_FILE` (`data_loader.py:504-507`, asserted at `server.py:462`). `values.csv` is a **second** remote file. **M6 must add `FTF_DP_PICK_VALUES_FILE` and extend the `server.py:461-466` startup assertion before any fetch lands** — otherwise `FTF_TEST_MODE=1` gains a live-egress hole, which the assertion exists to forbid.

- Rendered **only** on `order[]` entries, behind `picks.slot_values` (default OFF).
- `GENERIC_PICK_SEEDS` (`pick_values.py:24`), the 8-tier ladder, tier bands and the trade engine are **untouched**. Engine adoption is O2 — a repricing decision with the #214-toggle precedent.
- Non-12-team leagues: percentile map (O3, recommended), and the payload carries `slot_value_approx: true` so the client can label it.

---

## 5. Error Handling, Races & Budgets

### 5.1 Named races

| # | Race | Resolution |
|---|---|---|
| RC-1 | Refresh daemon rebinds pools while a request thread is inside `_ensure_universal_pools` | Both take `_pool_build_lock`; the request thread's double-checked fast path returns the (new) built pools. |
| RC-2 | Refresh daemon rebinds while `session_init` reads `_get_universal_pool` | `_get_universal_pool` reads `g_universal_by_format` (`server.py:1416-1424`), which is rebound per format under the lock, never cleared. A reader gets a whole old pool or a whole new one. |
| RC-3 | Two cron POSTs overlap | `_players_refresh_active` under `_players_refresh_lock`; the second returns `202 {"started": false}`. |
| RC-4 | Generation bumps twice while one user is mid-session | Nothing reads the generation mid-session; the next `session_init` rebuilds once at the latest value. |
| RC-5 | N viewers hit a cold draft simultaneously | Per-key `_inflight` lock + double-check ⇒ exactly one upstream read (D6). |
| RC-6 | A draft flips `complete` between the detail read and the picks read | The next TTL (24 h) window re-reads the detail; the picks list is already final, so the payload is correct either way. |
| RC-7 | Scoped save concurrent with an unscoped save in another tab | `save_tier_overrides` serialises (SELECT-FOR-UPDATE on Postgres, `database.py:3280-3284`). Last writer wins on the whole blob — today's behavior, unchanged; the snapshot is the recovery path. |
| RC-8 | Snapshot taken concurrently by two scoped saves | `take_tier_override_snapshot` is a no-op when the key exists; both paths converge on the earlier snapshot, which is the more conservative one. |

### 5.2 Timeout & budget table

| Path | Budget | On expiry |
|---|---|---|
| Players bulk fetch (M0 daemon) | 45 s (matches `server.py:11443`) | No write, counter, next tick retries |
| DP fetch during rebuild | existing `_DP_FETCH_RETRY_SECONDS = 60` backoff (`server.py:1374`) | That format stays unbuilt; the other still rebinds |
| Sleeper draft detail / picks | 15 s (`_sleeper_get` default, `server.py:496`) | `fails += 1`, serve stale |
| MFL export | 15 s + 1.0 s spacing (`mfl_service.py:71`) | `notice.mfl_reconnect` or stale |
| Upstream per draft | ≤3 fetches / rolling 60 s | `degraded.budget_exceeded`, serve stale |
| Breaker open | 120 s after 3 consecutive failures | No upstream call at all |
| Client poll | 15 s, focused + `state=="live"` only | n/a — hard zero when blurred/backgrounded |

### 5.3 Unbounded-resource guards

Draft cache ≤200 entries with TTL-based purge · `undrafted[]` capped at 300 rows (the class is ~250 skill players; the cap is a bound, not a filter — a hit is a bug and logs) · `order[]` bounded by `rounds × teams` and refused above 500 · rookie-id memo keyed by `(season, generation)` with the prior generation dropped on bump · one in-flight refresh process-wide.

---

## 6. Flags, Docs & Compatibility

### 6.1 The 4-touch flag convention (test-enforced)

Two tests make this non-optional: `backend/tests/test_seed_ui_test_db.py:106-112` (`flags/release.json` must exactly mirror `config/features.json` after stripping `_`-prefixed keys) and `backend/tests/test_entitlements.py:88-98` (every non-`_` key in `features.json` must exist in `DEFAULT_FLAGS`).

Per new flag, in order:
1. **`backend/feature_flags.py`** — append to `FLAG_KEYS` (`:47-355`), with a comment stating what it gates **and the flag-off behavior** ("Off ⇒ the query param is never read; responses byte-identical"). This alone makes it default-`False` (`:357`).
2. **`config/features.json`** — add the key with `false`. Add a `_comment_rookie_draft` string introducing the tranche (the `_comment_teardown` / `_comment_tiktok_discovery` pattern).
3. **`backend/tests/fixtures/flags/release.json`** — mirror the exact key/value.
4. **`docs/config-reference.md` → `## Feature flags`** (`:38`) — a new `### Rookie draft + Draft Room` sub-section with a `| Flag | Default | Gates |` row each.

Plus the expected companion: a `backend/tests/test_<feature>.py` pinning flag-off (404 / byte-identical) and flag-on, using the repo's flag-pinning idiom (there is **no `conftest.py`**):
```python
import backend.feature_flags as ff
saved = ff._flags_cache
ff._flags_cache = {**ff.DEFAULT_FLAGS, "draft.room": True}
... ; ff._flags_cache = saved
```

### 6.2 Docs each milestone must touch

| Milestone | Docs |
|---|---|
| **M0** | `docs/cross-client-invariants.md` — **new `## Rookie predicate` section** after `## Pick anchor keys` (`:283`), following the mandatory `**Locations:**` format (see `:70-76` for the shape), naming `backend/draft_status.py:94` + `backend/database.py:6915` and calling out `load_rookies` as the deprecated loose rule · `docs/config-reference.md` §Environment variables (`FTF_PLAYERS_REFRESH`) · `docs/api-reference.md` §Cron ticks (`:365`) · `docs/runbook.md` — new `## Player-cache refresh` section (appended at the bottom, dated heading, per that file's convention) · `docs/architecture.md` §Data flow (`:5`) |
| **M1** | `docs/runbook.md` §Mobile UI-test harness (`:195`) — the draft corpora + the record-mode empty-dir rule |
| **M2** | 4-touch for `ranks.rookie_subset` · `docs/api-reference.md` §Ranking (`:106`) + §Tiers (`:130`) — the `scope` param, the typed-empty contract, and the "scoped saves never mark a position complete" rule · `docs/data-dictionary.md` §`users` (`:7`) — the `__pre_rookie_scope__` sibling key and the `_parse_extra_keys` preservation rule · `docs/glossary.md` — "Rookie scope", "Merged-band save" · `docs/runbook.md` — the restore procedure (§3.2) · **`docs/adr/adr-009-rookie-scope-view-filter.md`** (next number; header format per `adr-008` `:1-7`, index row in `docs/adr/README.md:36-43`) recording the post-Elo view filter and the merged-band rule |
| **M3** | 4-touch for `draft.room` · `docs/api-reference.md` — a new `## Draft room (flag draft.room)` section after `## League` (`:285`), plus a row in the **gated-read matrix** (`:53`) noting the RV-1 divergence · `docs/architecture.md` §Components (`:66`) — `draft_board_service.py` · `docs/glossary.md` — "Draft Room", "Order confidence" |
| **M4** | 4-touch for `draft.live_poll` · `docs/design/components.md` if any new component is extracted · `docs/runbook.md` — the polling budget + the zero-request-when-backgrounded rule |
| **M5** | 4-touch for `draft.mfl` · `docs/api-reference.md` §MFL league linking (`:322`) — `draftResults` as a board source |
| **M6** | 4-touch for `picks.slot_values` · `docs/config-reference.md` §Environment variables (`FTF_DP_PICK_VALUES_FILE`) · `docs/cross-client-invariants.md` — a note that slot values are display-only and are **not** the ladder |

### 6.3 Backward compatibility

- Old binaries never send `scope`; every scoped path is additive and absent-by-default.
- `schema:1` is explicit so a future `schema:2` can be rejected rather than mis-parsed.
- `/api/rookies` + `load_rookies` stay live until M4's post-flip cleanup commit — the web overlay (`web/js/app.js` `openRookieBoard`) still consumes it and has no flag.
- No migration, so no rollback rehearsal is needed: every milestone rolls back by flipping its flag, except M0, which rolls back via `FTF_PLAYERS_REFRESH=0`.

---

## 7. Test Matrix

Run: `python3 -m pytest backend/tests/` from the repo root. **There is no CI and no `conftest.py`** — this is a human gate; each milestone's exit states the command and the expected pass count (baseline on `origin/main`: 1414 passed / 1 skipped).
**VFF = verify-failing-first**: the test must be shown red against the pre-change tree before the fix lands.

### M0 — `backend/tests/test_players_refresh.py`
| ID | Proves | Criterion |
|---|---|---|
| T-M0-01 | Atomic write: a reader during `_atomic_write_players_cache` sees old-or-new, never partial | D1 |
| T-M0-02 | Invalidation order: after a forced refresh, disk mtime, `_sleeper_cache`, `players.last_synced` and pool membership all reflect the new payload | D1 |
| T-M0-03 | Refresh never touches a request worker: `/api/rankings` p95 unchanged during a forced refresh (timed harness) | D1 |
| T-M0-04 **VFF** | Membership-only bump: seed the pool with pid X, refresh adding pid Y, assert X's seed Elo is byte-identical and Y is present (rule G-SEED) | D1, I-6 |
| T-M0-05 | Single-flight: 10 concurrent `_ensure_universal_pools` ⇒ exactly one DP fan-out | plan §M0 |
| T-M0-06 | A failed upstream leaves the previous pool fully intact (never an empty pool) | KD-4 |
| T-M0-07 | Concurrent cron POSTs ⇒ one thread, second returns `started:false` | RC-3 |
| T-M0-08 | Dev cache-age guard refuses rookie scope >7 days outside prod, **and does not** under `FTF_TEST_MODE` | plan §M0 |
| T-M0-09 | `load_rookie_player_ids` vs `is_rookie_row` agree on a table exercising: `rookie_year` set/absent, `years_exp` 0/1/None, `team` set/NULL/"" | I-2 |

### M1 — `backend/tests/test_draft_replay.py`
| T-M1-01 | Each of the four corpora replays with zero live egress (`test_support.counters['sleeper_live_egress_attempts'] == 0`) |
| T-M1-02 | `truncate_picks(k)` for k ∈ {0,1,24,48} yields `state` ∈ {upcoming, live, live, complete} and a matching `last_picked` |
| T-M1-03 | The fake clock drives TTL expiry deterministically (no `time.sleep` anywhere in the suite) |
| T-M1-04 | **[RV-3]** the bulk players fetch is intercepted by the fixture seam (fails until `_fetch_players_bulk` routes through `_sleeper_get`) |

### M2 — `backend/tests/test_rookie_scope.py`
| ID | Proves | Criterion |
|---|---|---|
| T-M2-01 **VFF** | A sibling key in `tier_overrides` survives 3 alternating-format `save_tier_overrides` calls | §3.2 |
| T-M2-02 | **Elo identity:** for every rookie pid, scoped Elo == unscoped Elo exactly, on a fixture with ≥50 rookie-vs-vet swipes | D2, I-1 |
| T-M2-03 | **Write identity by shape:** `apply_reorder` / `apply_anchor` on a rookie subsequence ⇒ byte-identical `_elo_overrides` to the unscoped equivalent | D2, I-2 |
| T-M2-04 **VFF** | **No respread:** after a scoped tier save, every non-scoped pid's override is byte-unchanged; a non-rookie with no override before has none after | D3, I-3 |
| T-M2-05 **VFF** | **Completeness untouched:** no `tiers_saved` entry before ⇒ none after; `/api/tiers/status.all_done` unchanged | D3, I-4 |
| T-M2-06 | `upsert_member_rankings` receives the FULL board on a scoped save; scope is never passed | I-5 |
| T-M2-07 | **The equivalence bar:** compute `M`, run unscoped `apply_tiers({tier: M})` on a clone, assert scoped pids' Elos are identical | D2/D3 |
| T-M2-08 | #161 under scope: a scoped save demotes only rookies that were **visible and unselected**; an unshown vet is never demoted | O4 |
| T-M2-09 | Promotion/demotion into a band: a scoped pid with current value above `hi` anchors at the top, below `lo` at the bottom | §4.3 step 2 |
| T-M2-10 | Thin pool ⇒ `200 {empty:true, reason:"thin_pool"}` on the scoped path; the unscoped path still `400`s | plan §M2 |
| T-M2-11 | Lane audit: under scope, `_pick_trio_variety` never returns `cross_pos` and the QC branch is skipped — **no non-rookie ever appears in a scoped trio** over 500 draws | plan §M2 |
| T-M2-12 | **Golden diff (D4):** same build, `ranks.rookie_subset` on vs off, data held constant ⇒ `/api/rankings` and `/api/trio` responses byte-identical | D4 |
| T-M2-13 | Snapshot: taken before the first scoped save, idempotent on the second; `restore_tier_overrides_from_snapshot` reproduces the pre-scope blob exactly | D3 |

### M3 — `backend/tests/test_draft_board.py`
| T-M3-01 | Complete draft (Lakeview corpus) ⇒ full board, 48 picks, `order_confidence:"assigned"` | D5 |
| T-M3-02 | Pre-draft with assigned order ⇒ true slots + traded-pick overlay | D5 |
| T-M3-03 **VFF** | `draft_order:null` ⇒ `order_confidence:"unset"`, `notice.order_not_set`, round-level ownership only — **the identity `slot_to_roster_id` map is never read** | D5 |
| T-M3-04 | `drafts == []` ⇒ `state:"unavailable"`, never a fabricated board | KD-6 |
| T-M3-05 | Fan-in: 20 concurrent `build_board` calls on one cold draft ⇒ 1 upstream detail fetch, 1 picks fetch | D6 |
| T-M3-06 | Poll rule: `last_picked` unchanged ⇒ **zero** `/picks` fetches across 10 TTL cycles | D6 |
| T-M3-07 | Import graph: `draft_board_service` does not import `load_draft_picks` | I-7 |
| T-M3-08 | No platform writes: no `POST`/`PUT`, no `sleeper_write` import | D9, I-8 |
| T-M3-09 | Undrafted = rookie_year − drafted − rostered; unvalued rows present with `valued:false`, sorted last | D7 |
| T-M3-10 | Startup-shaped ⇒ `kind:"startup"`, `undrafted_suppressed:true`, `notice.startup_draft` | plan §2 |
| T-M3-11 | Breaker: 3 failures ⇒ open, zero upstream calls for 120 s, `stale:true`; one success closes | HLD §5.1 |
| T-M3-12 | Budget: a 4th fetch inside 60 s is refused with `degraded.budget_exceeded` | D6 |
| T-M3-13 | Flag off ⇒ `404 feature_disabled`, no other route's response changes | D10 |

### M4 — Maestro + Jest
| T-M4-01 (Maestro) | Every designed state renders with its copy: order-not-set, startup, unsupported, class-not-loaded, stale, unavailable | D5/D7 |
| T-M4-02 (instrumented) | **Zero** requests when blurred or backgrounded; ≤1 per 15 s focused + live | D6, RV-8 |
| T-M4-03 (Maestro) | `draft.room` off ⇒ the Explore tile is today's rookie-board tile; no user is stranded | KD-10 |
| T-M4-04 (Jest) | The shared scope control is session-only — a remount clears it | #133 |
| T-M4-05 (Jest) | Quick Set under scope does not write `quicksetCompletedPositions` | I-4 client mirror |
| T-M4-06 (live, **release gate**) | Throwaway-league live test: picks appear ≤30 s while focused (O7) | D6 |

### M5 / M6
| T-M5-01..04 | MFL `made==0` / partial / complete / multi-`draftUnit` ⇒ correct `state`, `kind`, `order_confidence` | D8 |
| T-M5-05 | Auth failure ⇒ stored snapshot + `notice.mfl_reconnect` + `stale:true`, never stale-as-live | plan §M5 |
| T-M6-01 | `FTF_TEST_MODE=1` without `FTF_DP_PICK_VALUES_FILE` ⇒ `SystemExit` at import (the rail extension) | §4.7 |
| T-M6-02 | Flag off ⇒ `slot_value` key absent entirely; `GENERIC_PICK_SEEDS` and tier bands byte-unchanged | KD-9 |
| T-M6-03 | Fetch failure ⇒ the board renders without the axis | KD-9 |

### Flag mirror (D10, all milestones)
`test_seed_ui_test_db.py` + `test_entitlements.py` already enforce the mirror; each wave must re-run them and confirm each new flag is present in all four touch points and defaults `False`.

---

## 8. Open Items & Re-Verify Register

**Re-verify at build time** (each named inline above): **[RV-1]** `/api/draft/board`'s blanket read gate vs the `power-rankings` inline precedent · **[RV-2]** `/api/trio` still carries no read gate · **[RV-3]** the bulk players fetch is routed through `_sleeper_get` (fails T-M1-04 otherwise) · **[RV-4]** `sync_players` still stamps `last_synced` · **[RV-5]** no new reader of `g_universal_seed`/`dp_values` (the only torn-read surface) · **[RV-6]** record mode's empty-dir rule · **[RV-7]** `save_tiers_position` has no other reachable caller from a scoped save · **[RV-8]** `refetchInterval` still has zero precedent, and `queryClient` defaults are unchanged.

**Also re-diff before each wave** (the plan's own precondition): `TabNav`, `quicksetProgress`, and the pick regions — #244/#246 landed the same day this design was written. And `docs/api-reference.md`, which the working tree already modifies and M3 also edits.

**Plan-verified-live assumptions carried, not re-verified locally:** Sleeper CDN TTLs (`s-maxage=30` on the detail object, ~24 h on complete `/picks`) · MFL `draftResults` zero-auth on public leagues and `liveDraft` being dead · DP `values.csv` carrying `2026 Pick 1.01…5.12` rows in the exact scale `seed_elo_for_value` consumes. Each is the first task of the milestone that depends on it.

**Left to the build PRD, not this document:** the copy for each designed state; the RB-7 sentence about cosmetic inversion after a partial save; and the O1/O3/O5/O8/O10 operator confirmations the plan already records (O10 = generic pick rungs under scope is implemented as **YES, year-labeled, after players**, per the plan's recommendation).
