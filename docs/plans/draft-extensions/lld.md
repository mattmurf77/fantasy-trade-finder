# LLD — Draft-Surface Extensions (W1 draft-room actions · W2 FTF-native mock · W3 ESPN pick assignment)

**Date:** 2026-08-06 · **Status:** Draft for build briefing
**Parents (normative):** [plan.md](plan.md) — **FINAL and BINDING**, including the *"Operator decisions — ESPN pick assignment (2026-08-06)"* block · [hld.md](hld.md). D0–D18, W0–W3, M-A–M-D, S1–S4, KD-*, RB-*, I-* resolve to those documents. **Nothing here re-opens a plan decision.**
**Inherited (also normative):** [../rookie-draft/plan.md](../rookie-draft/plan.md) · [../rookie-draft/hld.md](../rookie-draft/hld.md) · [../rookie-draft/lld.md](../rookie-draft/lld.md) · [../rookie-draft/mock-draft-plan.md](../rookie-draft/mock-draft-plan.md) (W2's spec — adopted with the plan's three binding amendments) · [../rookie-draft/build-placement.md](../rookie-draft/build-placement.md).
**Grounding:** every `file:line` is an `origin/main` line at `20c2a54`. Backend suite baseline: **1764 collected** (`python3 -m pytest backend/tests -q --collect-only`).
**Stance:** every interface states exact types, nullability and error returns; every race is named with its resolution; every invariant names the test that proves it.

> ### ⚠️ RE-VERIFY AT BUILD TIME
> `backend/server.py` is ~18.5k lines and **three waves edit it**. **Line numbers rot; symbols do not.** Before each wave: `git fetch origin && git merge origin/main`, abort on conflict, then re-locate by symbol and re-check the anchors in §1.2. Items tagged **[RV-n]** are the specific places where a moved or changed tree invalidates this document — each names what to re-check and what it would mean. `backend/server.py`, `backend/database.py` and `mobile/src/screens/DraftRoomScreen.tsx` are **single-writer resources across all three waves**; never run two waves in one of them concurrently. Other sessions are live in this repo: never commit, stash, or discard foreign WIP.

---

## 1. Scope & Reference

### 1.1 Covers / excludes

**Covers:** W1 (draft-room per-player actions + instrumentation, plan §4) · W2 (FTF-native mock draft, plan §5, adopting `mock-draft-plan.md` §4–9 with the three binding amendments) · W3 (ESPN pick assignment, Draft Room state, offline recording — plan §6 REVISED + the operator-decisions block).

**Excludes:** M12 (viewing a Sleeper mock — REJECT unless S-2 passes; recommend no) · P-2 (making the seasonal Draft tab ESPN-aware — **cut for V1**) · any platform write · web/extension parity · startup-draft support (O5 stands) · a manual ESPN board grid beyond the assignment grid · pick trades, timers or multi-user inside the mock.

**Deleted / retired criteria a builder MUST NOT implement** (plan §6.0): **D2** (import-graph proof that no manual module reaches the engine) is DELETED — a builder honoring it cannot build W3; it is replaced by D12/D13. **D4** (platform-wins supersede machinery) is RETIRED from W3 — ESPN has no draft object, so nothing can supersede. **D3** survives only as flag-OFF byte-identity; with the flags ON, responses must change, and that is the point.

### 1.2 Grounding anchors (symbols, not lines)

| Anchor | Symbol | Why it is load-bearing |
|---|---|---|
| A-1 | `database.draft_picks_table` (`backend/database.py:723-740`) | The store W3 writes. Only UNIQUE is `pick_id` (`:739`); **no index on `league_id`**; `platform` carries the "ESPN never writes rows" comment (`:737`) this wave reverses |
| A-2 | `database.load_draft_picks` (`backend/database.py:7468-7489`) | THE containment seam. Seven production call sites, all in `server.py` |
| A-3 | `database.replace_draft_picks` (`backend/database.py:7447-7465`) | Unconditional `DELETE … WHERE league_id = ?` + chunked insert (200). Scoped to the league and **nothing else** |
| A-4 | `database.sync_draft_picks` (`backend/database.py:7311-7444`) + `server._sync_mfl_owned_picks` (`backend/server.py:8744-8840`) | The two platform writers. Both call A-3. The MFL one is the precedent for building rows outside the Sleeper sync |
| A-5 | `database._migrate_db` (`backend/database.py:1735-2110`) — `migration_cols` (`:1744-1848`), the executor (`:1852-1857`), the `#158` entries (`:1828-1830`), the `CREATE INDEX IF NOT EXISTS` block (`:1962-1975`), the sqlite/postgres branch (`:2100-2110`) | The dual-dialect convention W3's DDL must match exactly |
| A-6 | `pick_values.pick_pool_value` (`:104-123`) · `market_pick_pool_value` (`:245`) · `priced_pool_value` (`:294`) · `database.compute_pick_value` (`backend/database.py:7291-7308`) | The **only** legal price sources. D13's byte-equality bar names `priced_pool_value` (see §4.5) |
| A-7 | The two ESPN engine guards: `backend/server.py:4570-4572` (`_run_trade_job`) and `:9309-9311` (`asset_trade_ideas`) | Duplicated **three-clause** literals. The helper must preserve all three conjuncts |
| A-8 | `server.get_league_picks` (`backend/server.py:8538-8567`) — `supported` computed `:8553-8554`, emitted `:8556` + `:8564`; `_owned_pick_label` (`:8570`) | `picks_supported` becomes a data test here and nowhere else |
| A-9 | `draft_board_service.build_board` (`:331`), `unsupported_board` (`:1150`), `_render_unavailable` (`:1164`), `_payload` (`:1107`), `_notice` (`:1203`), `_undrafted` (`:885`), `_NOTICE_MESSAGES` (`:107-118`) | The ESPN board reuses the payload vocabulary and adds one notice code. `build_board` is **not** modified |
| A-10 | `server.draft_board_route` (`backend/server.py:10086-10207`) — flag gate `:10136-10137`, platform resolution `:10156-10164`, the fallback `if platform != dbs.SLEEPER` `:10201-10202` | The ESPN branch is inserted here, so `build_board`'s golden diff is untouched |
| A-11 | `database.record_event` (`backend/database.py:2356-2434`) + `analytics_taxonomy` (`ALLOWED_CLIENT_EVENTS` `:38`, `SERVER_FIRED_EVENTS` `:86`, `CLIENT_EVENT_PROPS` `:128`, the import-time disjointness assert `:216`) | Default-deny. Two registry entries per new **client** event; one per new **server** event |
| A-12 | `mobile/src/api/events.ts` — constants `:45-54`, `QueuedEvent` `:62-70`, `uuidv4` `:79-91`, `trimQueue` `:173-184`, `applyBackoff` `:228-240`, `sendBatch` `:283-341` | The offline-queue contract copied verbatim by M-D |
| A-13 | `mobile/src/state/useSession.ts` — `connectLeague` `:404-451`, the replace at `:420-435`, `SLG_KEY` `:25`, `setLeagues` `:303-309` | P-1. `mobile/src/api/sleeper.ts:17` additionally coerces `platform` to `'sleeper'` when absent |
| A-14 | `backend/tests/test_draft_board.py` — `_imported_names` (`:387-395`), `test_m3_07` (`:398-412`), the docstring-identity-exclusion variant (`:258-287`) | The AST-containment precedent D12 copies |
| A-15 | `mobile/src/components/PlayerContextMenu.tsx:33-52` (`PlayerMenuAction`, props) · `TradeCard.tsx:290-294` (`longPressFor`), `:304` + `:329` (`accessibilityActions`) | W1's menu host and the shipped long-press/a11y vocabulary |
| A-16 | `mobile/src/api/rankings.ts:378-384` (`saveAnchor`) · `mobile/src/screens/PickAnchorScreen.tsx:39-52` (`ANCHOR_ROWS`), `:202-204` (the mutation) | W1's anchor lane. **There is no sheet — W1 builds one** (HLD RB-11) |

**Conventions:** timestamps are ISO-8601 UTC via `database._now()`; JSON is stored as `Text` and parsed in Python (no json1/JSONB — dual-dialect); booleans are `Integer` 0/1; additive columns are appended to `migration_cols` as `(table, col, "VARCHAR"|"INTEGER"|"TEXT"|"FLOAT")` with **no** `DEFAULT` and **no** `NOT NULL`; new flag keys are appended to `feature_flags.FLAG_KEYS` (`backend/feature_flags.py:47-418`), which makes them default-`False` (`:420`).

---

## 2. Interfaces / API

### 2.1 W1 — `POST /api/anchor/save` gains an optional `via` / `surface`

The route is `backend/server.py:7192-7194` (`@app.route(..., methods=["POST"])` + `@_gate_unverified_write`). It reads exactly two body fields today (`:7211-7218`) and fires `anchor_answered` with three props (`:7273-7285`).

```python
# backend/server.py — module constant, beside VALID_ANCHORS (:1144)
_ANCHOR_VIA = ("anchors", "draft_room")

# inside save_anchor_route, beside the player_id/anchor parse (:7211-7218)
raw_via = str(body.get("via") or body.get("surface") or "").strip()
via = raw_via if raw_via in _ANCHOR_VIA else "anchors"
```

- **Request-only.** The response (`:7291-7300`) is byte-unchanged, so D10's byte-identical-*response* bar is satisfied structurally, not by diffing.
- An unrecognised value **falls back**, never 400s — mirroring the tiers-`via` convention at `backend/server.py:7136-7143` ("the whitelist is EXTENDED, never replaced").
- `via` is added to the existing `record_event` props at `:7278-7280`: `{"player_id": …, "pick_value": anchor, "skipped": False, "via": via}`. `anchor_answered` is **server-fired** (`analytics_taxonomy.SERVER_FIRED_EVENTS`), and `CLIENT_EVENT_PROPS` filters client events only — so **no taxonomy change is required for this field**.
- **Do NOT touch `backend/server.py:7140-7143`.** That whitelist belongs to `POST /api/tiers/save` — the lane W1 forbids — and it already carries the `rookie_*` members M2 added. **[RV-1]**

**Client:** `saveAnchor` (`mobile/src/api/rankings.ts:378-384`) gains an optional third argument:

```ts
export async function saveAnchor(playerId: string, anchor: AnchorKey, via?: 'anchors' | 'draft_room') {
  return api.post<AnchorSaveResponse>(
    '/api/anchor/save',
    via ? { player_id: playerId, anchor, via } : { player_id: playerId, anchor },
    { headers: await formatHeader() },
  );
}
```
Omitting `via` sends today's exact body, so `PickAnchorScreen`'s call site (`:202-204`) is untouched.

### 2.2 W1 — new client analytics events

The taxonomy is **default-deny with two registries** (A-11). Each new event needs an entry in **both** or it is counted-and-dropped at ingest; a missing `CLIENT_EVENT_PROPS` entry raises at **import** (`analytics_taxonomy.py:229-235`). Names must not collide with `SERVER_FIRED_EVENTS` (import-time assert, `:216`).

| Event | Props | Fired when |
|---|---|---|
| `draft_room_row_menu_opened` | `{surface, player_id, valued, rank}` | The context menu opens on an undrafted row |
| `draft_room_action_taken` | `{action, player_id, valued}` — `action` ∈ `set_value`\|`rank_rookies`\|`add_target` | A menu action is chosen |
| `draft_room_coverage_nudge_shown` | `{unvalued_count, window}` | The "N of the top 25 have no value on your board" nudge renders |
| `draft_room_rank_rookies_tapped` | `{state, from}` | The existing bridge row is tapped (it emits nothing today) |

A **tracking-plan addendum** in `docs/business/analytics/` is a precondition for merging these (the registries' own comment states default-deny requires it). **`draft-room.rank-rookies` currently emits no analytics at all** — this is D0's first deliverable, not a nice-to-have.

### 2.3 W2 — mock-draft routes

Thin shims in `server.py` over `backend/mock_draft_service.py`. Every route returns `404 {"error":"feature_disabled"}` before any session work unless `is_enabled("draft.mock")` (the `backend/server.py:10136-10137` convention). All carry `@_gate_unverified_write` (POST) / `@_gate_unverified_read` (GET) and `_require_initialized_session()`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/mock-draft` | `{league_id, rounds?, type?}` | Creates (abandoning any prior active row for that user+league in the same transaction), resolves order/ownership/personas, advances CPU to the user's first turn. `400 {"error":"not_rookie_draft"}` when the board's `kind != "rookie"`; `200 {empty:true, reason:"class_not_loaded"}` mirroring M2's typed-empty contract |
| GET | `/api/mock-draft` | `?league_id=&basis=consensus\|my_board` | The active (or most recent complete) state |
| POST | `/api/mock-draft/pick` | `{mock_id, player_id}` | `409 {"error":"not_your_turn"}` · `400 {"error":"player_unavailable"}` · else the advanced state |
| POST | `/api/mock-draft/abandon` | `{mock_id}` | `{ok:true}` |

**State payload** reuses the shipped I-6 vocabulary verbatim so the M4 render components are reused unchanged:
`{schema:1, mock_id, status, on_the_clock:{pick_no, round, slot, roster_id, is_user}, order[], picks[], undrafted[], my_picks[], settings_echo, notice}` — `order[]`/`picks[]`/`undrafted[]` entry shapes exactly as `backend/draft_board_service.py:730-742`, `:866-876`, `:916-925`. `undrafted[]` honours D7 verbatim: `valued:false` rows are present and sorted last, never dropped.

**O-M7 (operator-confirmed by plan §5's access rule):** a league with **no draft object at all** may still create a mock — that is the *primary* case. Order is randomized-and-labelled (`order_source:"randomized"`), rounds default 4.

### 2.4 W3 M-A — assignment routes

All three carry `@_gate_unverified_write` (or `_read` for the GET) + `_require_initialized_session()`, resolve the actor as `sess["user_id"]` (**a body `user_id` is ignored** — the teardown S6B-01 precedent at `backend/server.py:11522-11532`), and assert league membership server-side against `league_members`. All 404 `feature_disabled` unless `is_enabled("picks.assign")`.

**`GET /api/league/pick-assignments?league_id=&season=`**

```jsonc
{
  "league_id": "1234567890",
  "settings": { "rounds": 4, "order_type": "linear", "order": ["u1","u2", "..."] },
  "seasons": [
    { "season": 2026,
      "slots": [ { "pick_id": "1234567890_2026_1_3",
                   "season": 2026, "round": 1,
                   "original_roster_id": "3",
                   "original_user_id": "u3", "original_username": "Dana",
                   "owner_user_id": "u7",  "owner_username": "Sam",
                   "is_traded": true,
                   "source": "user",
                   "assigned_by": "u7",
                   "assigned_at": "2026-08-06T18:03:11.204+00:00",
                   "contested": false,
                   "orphaned": false } ] }
  ],
  "progress": { "assigned": 192, "total": 192, "traded": 3, "contested": 0, "orphaned": 0 },
  "seeded": true
}
```
- `seasons[]` is **always** current + 3 (operator decision 3), ascending. The client defaults to the current season and collapses the other three (KD-5); the payload does not paginate — 192 slots is ~40 KB and one round-trip beats four.
- `assigned_at` is **also the CAS token**. It is `null` on a never-assigned row.
- `progress.assigned` counts rows with `source='user'`; `total` = `rounds × teams × 4`.

**`PUT /api/league/pick-assignments`**

```jsonc
// request
{ "league_id": "…", "pick_id": "1234567890_2026_1_3",
  "owner_user_id": "u7", "if_assigned_at": "2026-08-06T18:03:11.204+00:00" }
```
| Outcome | Response |
|---|---|
| OK | `200 {"ok":true, "slot": <the updated slot object>, "progress": {…}}` |
| Unknown `pick_id` for this league | `404 {"error":"pick_not_found"}` |
| `owner_user_id` not in `league_members` for this league | `400 {"error":"owner_not_in_league"}` |
| **Stale CAS** — the row's `assigned_at` differs from `if_assigned_at` | `409 {"error":"stale_assignment", "current": <the current slot object>}` |
| Row already assigned and `if_assigned_at` omitted | `409 {"error":"stale_assignment", "current": …}` — a blind overwrite is never allowed |
| Any value field present in the body (`value`, `pool_value`, `pick_value`, `elo`, …) | `400 {"error":"values_not_accepted"}` — **D13, enforced at the edge** |
| Flag off | `404 {"error":"feature_disabled"}` |

The 409 body carries the **whole current row** so the client can render "Dana changed this 4 minutes ago — keep theirs, or use yours?" without a second round trip.

**`POST /api/league/pick-assignments/order`** — the seeder and the order/rounds setter.

```jsonc
{ "league_id": "…", "rounds": 4, "order_type": "linear", "order": ["u1","u2","…"], "reseed": false }
```
| Outcome | Response |
|---|---|
| OK | `200 {"ok":true, "seeded": <int slots written>, "progress": {…}}` |
| `rounds` outside `1..8` | `400 {"error":"rounds_out_of_range", "max": 8}` — **clamped server-side**; `ROOKIE_MAX_ROUNDS = 8` (`backend/draft_status.py:65`) is the conservation bound's only lever (KD-4) |
| `order` not a permutation of the league's member ids | `400 {"error":"bad_order"}` |
| `order_type` ∉ `{linear, snake}` | `400 {"error":"bad_order_type"}` |
| `reseed: true` with existing edits | `200` with a `reseeded_over` count in the body; the audit event records every overwritten slot |

`order_type` and `order` change **slot numbering only, never ownership** (execution-lens finding, plan §6.5) — so the toggle is safe at any time and never triggers a CAS conflict.

### 2.5 W3 M-B — the ESPN branch of `GET /api/draft/board`

Inserted in `draft_board_route` **immediately before** the existing `if platform != dbs.SLEEPER: return jsonify(dbs.unsupported_board(req))` (`backend/server.py:10201-10202`):

```python
    if platform == "espn" and is_enabled("picks.assign"):
        return jsonify(dbs.assigned_board(req, grid=_assignment_grid(league_id, season)))
```

`build_board` is **not** modified (KD-8), so its golden diff is untouched. Flag off ⇒ the existing line runs and the payload is byte-identical to today's `platform_unsupported`.

**New notice code**, appended to `backend/draft_board_service.py:101-105` + `_NOTICE_MESSAGES` `:107-118`:

```python
NOTICE_PICKS_NOT_ASSIGNED = "picks_not_assigned"
...
    NOTICE_PICKS_NOT_ASSIGNED:
        "Nobody has set this league's draft picks yet.",
```
**No closed enum gains a member.** `state` stays `"unavailable"` (B2) or becomes `"upcoming"` (B3) — both are existing values; `kind` and `order_confidence` are unchanged. The mobile `NoticeCode` TypeScript union (`mobile/src/api/draft.ts:28-33`) is extended and one branch is added to the if-else chain at `DraftRoomScreen.tsx:390-401`; an **old** binary renders the server's `message` via the verified fallback at `:401`. The notice testID is templated off the code (`:404`), so `draft-room.notice.picks_not_assigned` exists for free.

**Copy rule (binding).** The operator called this state an "error". It is an *unconfigured state with a user-performable fix*. The copy must read that way and the CTA must route to M-A. Never "Something went wrong."

### 2.6 W3 M-D — `POST /api/league/recorded-picks`

Batch-shaped, because the client's queue drains in batches (A-12: `BATCH_MAX = 50`).

```jsonc
// request
{ "league_id": "…", "season": 2026,
  "picks": [ { "event_id": "8f1c…", "overall": 3, "round": 1, "slot": 3,
               "picking_team_id": "u7", "player_id": "11635",
               "client_ts": "2026-05-11T18:02:07.113Z" } ] }
```
```jsonc
// response — the SAME reconciliation shape mobile/src/api/events.ts already parses (:316-320)
{ "accepted": 1, "deduped": 0, "rejected": [] }
// rejected entries: { "index": 0, "reason": "slot_out_of_range" | "unknown_player" | "not_in_league" | "voided" }
```
- **Idempotency key is `(league_id, season, overall)`** (plan §6.5), enforced by `uq_recorded_pick_slot` (§3.2). A replayed batch produces `deduped`, never a duplicate row and never a 4xx.
- `event_id` is stored for audit and lets the client match rejections to queue items, but it is **not** the uniqueness key — two different devices recording the same physical pick must dedupe, and they will not share a uuid.
- **`overall` never leaves this table.** D18's test asserts no `draft_picks` write path carries an `overall` key.

**`POST /api/league/recorded-picks/void`** — `{league_id, season, overall}` → sets `voided_at`, returns the recomputed board slice. Non-destructive: nothing is ever DELETEd.

---

## 3. Data Structures & Schema

### 3.1 W3 — the three additive `draft_picks` columns

**Table declaration**, appended inside `draft_picks_table` (`backend/database.py:723-740`) between `platform` (`:737`) and `synced_at` (`:738`):

```python
    # draft-extensions W3 (ADR-010) — user-asserted pick ownership.
    # source: NULL or 'platform' = platform-written (every pre-W3 row reads as
    #   platform). 'user' = a league member asserted it. This column IS the
    #   containment: load_draft_picks defaults to platform-only.
    Column("source",      String),
    Column("assigned_by", String),   # FTF user_id of the LAST editor ('user' rows only)
    # ISO-8601 UTC. ALSO the optimistic-concurrency token: a PUT carries the
    # value it read and the UPDATE's WHERE compares it (§4.3).
    Column("assigned_at", String),
```

**Migration**, appended to `migration_cols` (`backend/database.py:1744-1848`) beside the `#158` block at `:1828-1830`:

```python
        # draft-extensions W3 — user-asserted pick ownership (ADR-010).
        ("draft_picks",        "source",                "VARCHAR"),
        ("draft_picks",        "assigned_by",           "VARCHAR"),
        ("draft_picks",        "assigned_at",           "VARCHAR"),
```
`VARCHAR`, not `TEXT`, to match the `Column(..., String)` declaration — the `platform` column's `String`/`TEXT` asymmetry (`:737` vs `:1830`) is an existing wart; do not add a second one. **No backfill**: every existing row keeps `source IS NULL`, which the default read predicate treats as platform (§4.3).

**Index.** `draft_picks` already exists in production, so `metadata.create_all` will **not** add an index to it. It needs the explicit idempotent form, following `_trade_match_indexes` (`backend/database.py:1962-1975`), placed in the same region of `_migrate_db`:

```python
    # draft-extensions W3 — every read filters league_id (there is no index on
    # it today, A-1) and the containment predicate adds source. Both dialects
    # support CREATE INDEX IF NOT EXISTS (Postgres >=9.5, SQLite >=3.3).
    _draft_picks_indexes = [
        ("ix_draft_picks_league_source", "draft_picks", "league_id, source"),
    ]
    for idx_name, tbl, cols in _draft_picks_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"
                ))
        except Exception:
            pass
```
This is **part of M-A, not a later optimization** (HLD §5.2): a 192-row grid per league turns every un-indexed `league_id` scan into a real cost at seven read sites.

### 3.2 W3 M-D — `recorded_picks` (new table)

Declared beside `draft_picks_table`; `metadata.create_all(engine)` (`backend/database.py:2263`) creates it on both fresh and existing DBs, so **no `_migrate_db` entry is needed for the table itself**.

```python
# ---------------------------------------------------------------------------
# recorded_picks — the live offline-draft feed (draft-extensions W3 M-D).
#
# An OFF-PLATFORM rookie draft has no platform object to read (operator ruling:
# ESPN has no rookie drafts), so this is the only record that a pick happened.
# It projects into GET /api/draft/board's `picks[]` and NOWHERE else — it never
# writes draft_picks, never sets leagues.draft_status*, and never marks a draft
# complete.
#
# `overall` is legitimate HERE and must never leak onto a draft_picks row (D18):
# draft_picks' grain is (league, season, round, original_roster) and its pick_id
# format cannot express a slot.
#
# Undo is non-destructive: voided_at follows deck_suppressions.lifted_at
# (database.py:539) — a nullable ISO string, IS NULL means live, never a DELETE.
# A correction at an already-recorded `overall` UPDATEs the row in place
# (voided_at back to NULL); the durable history is the user_events trail.
# ---------------------------------------------------------------------------
recorded_picks_table = Table("recorded_picks", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("league_id",       String,  nullable=False),
    Column("season",          Integer, nullable=False),
    Column("round",           Integer, nullable=False),
    Column("slot",            Integer, nullable=False),
    Column("overall",         Integer, nullable=False),   # 1-based, league-wide
    Column("picking_team_id", String),                    # league_members.user_id on the clock
    Column("player_id",       String,  nullable=False),   # OUR id space
    Column("recorded_by",     String,  nullable=False),   # FTF user_id of the recorder
    Column("event_id",        String),                    # client uuid — audit + rejection matching
    Column("recorded_at",     String,  nullable=False),   # ISO UTC
    Column("voided_at",       String),                    # IS NULL = live
    # The unique constraint IS the idempotency gate (the deck_replenish_log
    # framing, database.py:559-564). Named so the Postgres upsert path can
    # target it by constraint name, per upsert_league_members (:5052-5075).
    UniqueConstraint("league_id", "season", "overall", name="uq_recorded_pick_slot"),
    Index("ix_recorded_picks_league_season", "league_id", "season"),
)
```

**Deviations from the plan's column list, each justified:** `id` (every table in this repo has a surrogate PK), `event_id` (lets the client match `rejected[i]` back to a queue item without positional trust), `recorded_at` (the audit needs a server time; `client_ts` is untrusted).

**Why a partial unique index is not used.** `UNIQUE(league, season, overall)` blocks re-recording a voided slot. The resolution is that a correction is an **UPDATE in place** (§4.6), not a void-then-insert — which keeps one row per physical slot forever and keeps the constraint dialect-portable. A partial unique index (`WHERE voided_at IS NULL`) is dialect-divergent across SQLite/Postgres and is rejected for exactly the reason `mock-draft-plan.md:72` rejects it for `mock_drafts`.

### 3.3 W2 — `mock_drafts` (new table)

Exactly `mock-draft-plan.md` §4, restated here so the builder does not have to cross-reference:

```python
mock_drafts_table = Table("mock_drafts", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("league_id",  String,  nullable=False),
    Column("season",     Integer, nullable=False),
    Column("status",     String,  nullable=False, server_default="active"),  # active|complete|abandoned
    Column("settings",   Text,    nullable=False),   # JSON — see below
    Column("picks",      Text,    nullable=False, server_default="[]"),      # JSON array, append-only
    Column("rng_seed",   Integer, nullable=False),
    Column("created_at", String),
    Column("updated_at", String),
    Index("ix_mock_drafts_user_league", "user_id", "league_id"),
)
```
- `settings` JSON: `{rounds, type, order:[user_id…], order_source:"assigned"|"randomized"|"none", ownership:{pick_no: user_id}, personas:{user_id:{outlook, source}}, basis_teams, scoring_format, noise:{jitter_slots, max_reach}}`. The fitted noise parameters are **snapshotted into the row** so a resumed mock replays identically even if `model_config` is retuned.
- `picks` JSON rows: `{pick_no, round, slot, roster_id, player_id, by:"user"|"cpu"}`.
- Per-pick RNG is `Random(rng_seed * 10_007 + pick_no)`.
- One active mock per user+league is enforced **in application code** inside the create transaction, not by a constraint (a naive `UniqueConstraint(user_id, league_id, status)` would also block a second *abandoned* row; a partial index is dialect-divergent).
- `server_default` (not Python `default`) so a raw-SQL insert cannot produce NULL — the `referrals_table` precedent (`backend/database.py:1439`).

### 3.4 In-process structures

```python
# ── backend/database.py — contested derivation (W3) ───────────────────────
# Keyed by league_id. Mirrors the _COMMUNITY_ELO_CACHE pattern (:5880-5881):
# a process-local cache with explicit invalidation on write.
_CONTESTED_TTL_SECONDS = 60.0
_CONTESTED_CACHE: dict[str, tuple[float, frozenset[str]]] = {}
_CONTESTED_LOCK = threading.Lock()
```
No new cache in `draft_board_service` — the ESPN board reads the DB directly and **must not** participate in `_cache` / `_inflight` / the breaker / the budget (there is no upstream to protect).

### 3.5 Invariants

| # | Invariant | Proven by |
|---|---|---|
| **INV-1** | **Containment by default.** With `picks.assign_tradeable` off, every one of the seven `load_draft_picks` call sites returns byte-identical rows in byte-identical order to the pre-W3 tree, for every league and every provenance mix | T-W3-01 (golden diff) + T-W3-02 (AST enumeration) |
| **INV-2** | **A writer only ever deletes rows it could have written.** No `replace_draft_picks` call can remove a row of a provenance it does not own | T-W3-03 **VFF** |
| **INV-3** | **No user-entered values, ever.** No assignment route accepts a value field, and every `source='user'` row's price equals `priced_pool_value(row, scoring_format=fmt, mode=m)` for **both** `m` — i.e. equals the shipped function's output for its coordinates | T-W3-04 (edge rejection) + T-W3-05 (property, both modes) |
| **INV-4** | **Conservation bound.** For any league, `Σ pool_value` over `source='user'` rows equals `Σ pick_pool_value(round, years_out, fmt)` over the pristine `rounds × teams × 4` grid — independent of who owns what | T-W3-06 (property test over random ownership permutations) |
| **INV-5** | **Contested ⇒ unpriced, by row filtering.** A contested slot appears in **zero** priced payloads. Nulling `pool_value` is forbidden: `_power_picks_by_owner` re-derives a price from NULL (`backend/server.py:17241-17244`) | T-W3-07 **VFF** (assert the naive nulling implementation fails) |
| **INV-6** | **`overall` never reaches `draft_picks`.** No write path into `draft_picks` carries an `overall` key; `recorded_picks` never writes `draft_picks` | T-W3-08 (AST + runtime) |
| **INV-7** | **O9 survives, pinned behaviorally.** No path writes `leagues.draft_status` / `_confidence` / `_checked_at` from user input | T-W3-09 (behavioral, not source-text identity) |
| **INV-8** | **`pick_id` has exactly one construction.** All four producers emit identical ids for identical inputs | T-W3-10 |
| **INV-9** | **Zero platform egress from the ESPN board**, in all three states | T-W3-11 (fixture-seam counters, the `test_m1_01` pattern) |
| **INV-10** | **The mock is deterministic and self-contained.** Same `rng_seed` ⇒ byte-identical full draft; zero platform egress after creation | T-W2-05, T-W2-13 |
| **INV-11** | **W1 never touches the completeness markers.** No `tiers_saved` entry before ⇒ none after; `/api/tiers/status.all_done` unchanged; `save_tiers_position` unreachable from any W1 surface | T-W1-03 **VFF** |
| **INV-12** | **Offline replay changes nothing.** Replaying the entire queue after reconnect yields `deduped == n`, `accepted == 0`, and a byte-identical board | T-W3-12 **VFF** |

---

## 4. Core Logic — per wave / milestone

### 4.1 W1 — Draft-room actions + instrumentation (1 batch, high confidence)

**File ownership:** `backend/server.py` (the `via` parse only — ~6 lines), `backend/analytics_taxonomy.py`, `mobile/src/screens/DraftRoomScreen.tsx`, `mobile/src/api/rankings.ts`, one new `mobile/src/components/AnchorSheet.tsx`, `docs/api-reference.md`, `config/features.json` + the 3 flag siblings.

**4.1.1 Per-player testIDs (D0 — a precondition, not an output).**
`UndraftedRowView` (`mobile/src/screens/DraftRoomScreen.tsx:594-614`) renders `<View testID="draft-room.undrafted-row">` at `:596` — **shared and non-unique across every row**, which is why the flow is untestable today. Change to `testID={\`draft-room.undrafted-row.${r.player_id}\`}` per the grammar in `mobile/src/components/CLAUDE.md` ("the qualifier is a stable domain id … never a list index"). `draft-room.order-row` (`:484`) and `draft-room.pick-row` (`:518`) have the same defect; qualify them in the same commit — they are one-line changes and leaving them makes the Maestro flow half-targetable.

**4.1.2 The interaction (RB-12 — read this before writing UI).**
There is **no "⋯" affordance anywhere in `mobile/src/`**. The shipped vocabulary is:

```tsx
// mobile/src/components/TradeCard.tsx:290-294, :304, :329 — the precedent
onLongPress={longPressFor(p, side)}
accessibilityActions={[{ name: 'menu', label: 'Player options' }]}
onAccessibilityAction={(e) => { if (e.nativeEvent.actionName === 'menu') onPlayerMenu(p, side); }}
```
**Mandatory:** the long-press **and** the `accessibilityActions` custom action — that pair already satisfies the accessibility requirement the plan cites, because a long-press-only control is otherwise unreachable to assistive tech.
**Requires a design decision:** a *visible* glyph. It would be net-new to the Chalkline system, which forbids emoji-as-icons and constrains the icon set (ADR-004/005, `docs/design/components.md`). **A build agent must not invent it inline** — either ship long-press + custom action (recommended, zero new design surface) or get a component spec first. **[RV-2]**

**4.1.3 The menu.**
`PlayerContextMenu` is shipped (`mobile/src/components/PlayerContextMenu.tsx:33-52`) and its flag `ux.player_context_menu` is already `true` (`config/features.json:103`). Actions are plain data:

```tsx
const actions: PlayerMenuAction[] = [
  { key: 'set-value',    label: 'Set my value',   hint: 'Anchor this rookie on your board',
    testID: 'draft-room.action.set-value',    onPress: () => setAnchorTarget(player) },
  { key: 'rank-rookies', label: 'Rank the rookies',
    testID: 'draft-room.action.rank-rookies', onPress: goToRookieRanks },
  { key: 'add-target',   label: 'Add to targets',
    testID: 'draft-room.action.add-target',   onPress: () => addTarget(player) },
];
```
The mount copies `MatchesScreen.tsx:746-751`. Fire `draft_room_row_menu_opened` **before** `setMenuTarget`, mirroring `MatchesScreen.tsx:635-647`.

**4.1.4 The anchor sheet (net-new — HLD RB-11).**
`saveAnchor` has exactly one caller today and it is a **full screen**, not a sheet (`mobile/src/screens/PickAnchorScreen.tsx`). Build `mobile/src/components/AnchorSheet.tsx` that:
- imports the **same** `ANCHOR_ROWS` constant (`PickAnchorScreen.tsx:39-52`) — extract it to a shared module rather than copying, so a rung can never diverge between the two surfaces;
- calls the **same** `saveAnchor` with `via:'draft_room'`;
- is a `Modal`, therefore **exempt from the `FeedbackFAB` rule** (root `CLAUDE.md`: "Exceptions: modals/sheets and onboarding flows");
- commits on the rung tap — D1's bar is "≤3 taps **and** no navigation away", and long-press → *Set my value* → rung is already three gestures, so there is no budget for a confirm step. Provide **undo** instead of confirmation.

Optimistic update: write the new value into the `['draft-board', leagueId, basis]` query cache, then invalidate on success; roll back and toast on failure.

**4.1.5 The coverage nudge.**
Source is `undrafted[].valued` — the field already exists (`backend/draft_board_service.py:923`). Copy: "N of the top 25 have no value on your board." Compute over the first 25 entries of `undrafted[]` (which is already `rank`-ordered, `:939`). Fire `draft_room_coverage_nudge_shown{unvalued_count, window:25}`.

**4.1.6 The bridge becomes two-way.**
`RankRookiesRow` (`:351-374`) navigates `Main → Rank → RookieRanks` (`:181-185`). Pass a return route in params and render a "Back to the draft room" affordance on `RookieRanksScreen`, so the bridge is not one-way. The deep link `app/rank/rookies` (`mobile/src/utils/deepLinks.ts:134`) is unchanged.

**Flag:** `draft.rank_inline`, lands OFF. Off ⇒ no menu, no long-press handler, no nudge; rows are the inert `View`s they are today. The testID qualification ships **unflagged** (it is inert and it is what makes the flag testable).

---

### 4.2 W2 — FTF-native mock draft (3.5 batches, medium confidence)

Adopt `mock-draft-plan.md` §4–9 verbatim except where the plan's three binding amendments apply. Sequence: **W2a** engine + calibration → **W2b** mobile → **W2c** access + polish.

**4.2.1 The service.** `backend/mock_draft_service.py` — a flat module beside `draft_board_service.py` (KD-1), pure, injected inputs:

```python
def create_mock(league_ctx, user_roster_id, settings, rng_seed) -> MockState
def advance_cpu(state, pool, needs, personas, rng) -> MockState
def apply_user_pick(state, player_id) -> MockState
def cpu_pick(candidates_ranked, persona, needs_for_team, rng) -> str      # player_id
def positional_needs(roster_rows, lineup_slots) -> dict[str, float]
```

**4.2.2 Amendment 1 — CPU basis is market consensus, and there is exactly ONE definition of it.**
The mock consumes the **shipped seam**: `server._get_universal_pool(fmt)` → `consensus_seed`, which is already injected into the board as `BoardRequest.consensus_elo` (`backend/draft_board_service.py:183`) and is the same source `BASIS_CONSENSUS` (`:93`) uses. Do **not** derive a second consensus. A second definition means the room's undrafted order and the mock's bots visibly disagree on one screen. The user's board (`basis=my_board`) affects **only** how the *user's* own undrafted list is sorted; it never enters a CPU decision.

**4.2.3 Amendment 2 — the noise model is FITTED, and fit is SEPARATED from validation.**

*Scoring function* (`mock-draft-plan.md` §6.1, unchanged):
```
score(c)   = rank(c) − need_bonus(t, pos(c)) − jitter(c)
need_bonus = need_weight(t) × severity(t, pos) × MOCK_MAX_REACH
jitter(c)  ~ Uniform(0, MOCK_JITTER_SLOTS)          ← THE fitted parameter
need_weight(t) = trade_service.outlook_alpha(persona_outlook(t))   # reused verbatim
```

*Observable.* For each real pick *i* in a recorded draft, define the **reach**
`d_i = consensus_rank_at_time_of_pick(player_i) − i`
where the consensus rank is 1-based over the pool **as it stood at that pick** (drafted players removed). `d_i > 0` = a reach; `d_i < 0` = a fall. The empirical target is the distribution of `d`.

*Corpora.*
| Corpus | Where | Role |
|---|---|---|
| `lakeview-complete/` (48 picks) | `backend/tests/fixtures/draft/` (M1) | fit + hold-out |
| `mfl-complete` (30/30) | M5's committed grids | **independent** validation |
| `mfl-partial` (36/72) | M5's committed grids | independent validation |
| `mfl-multi-unit` | M5's committed grids | **EXCLUDED — startup-shaped** |
**Precondition:** check rookie-vs-startup shape on `mfl-complete` and `mfl-partial` *before* using either (`draft_status.ROOKIE_MAX_ROUNDS = 8` / `STARTUP_MIN_ROUNDS = 15`, `backend/draft_status.py:65-66`). A startup corpus has a different reach distribution by construction and would silently poison the fit.

*Procedure.*
1. **Split.** Primary: fit on Lakeview rounds 1–2 (picks 1–24), validate on rounds 3–4 (picks 25–48). Robustness: 4-fold CV over four contiguous 12-pick blocks.
2. **Fit.** Grid-search `MOCK_JITTER_SLOTS` over `[0.25, 3.00]` step `0.25`, with `MOCK_MAX_REACH` fixed at the product-specified `3.0` (it is a product cap, not a fitted parameter — fitting both is unidentifiable at n=24). For each candidate, run **1000** seeded simulations of the fit block and pick the value minimising the 1-D Wasserstein distance between simulated and observed `|d|`.
3. **Validate on the hold-out.** Two bars, **both** must pass:
   - a two-sample **KS test** between simulated and observed `|d|` on the hold-out block is **not rejected at α = 0.05**; and
   - `|mean(|d|)_sim − mean(|d|)_obs| ≤ 1.0` rank slots.
   The KS test alone is underpowered at n = 24, which is exactly why the paired mean bar exists — state this in the artifact so nobody drops it as redundant.
4. **Validate independently.** Replay `mfl-complete` with the fitted value, **no refit**. Both bars must hold again.
5. **Publish.** Write `docs/plans/draft-extensions/mock-calibration-2026-08.md`: the corpora used and their shape check, the split, the grid, the fitted value, both bars' numbers on the hold-out and on the independent corpus, and the verdict. This is interface **I-10** — a **gate artifact**, not a report.

*Failure.* **W2's abort criterion fires** (plan §5): practice/replay ships as a QA-only surface (tester allowlist) and the CPU-bot mock is **cut**. Do not retune until it passes — that is the fit-on-the-validation-set failure the amendment exists to prevent.

**4.2.4 Amendment 3 — access.**
- A **"Mock draft" CTA inside `DraftRoomScreen`**, rendered in `upcoming` / `unavailable` / no-draft-object states — **not** restricted to `kind == "rookie"`, because an unscheduled draft is the *primary* mock case.
- The **Acquire chip** already exists year-round whenever `draft.room` is on (`TradeFinderModeBar`, `build-placement.md` §1), so the mock inherits a 12-month home with **no new tab and no new chip**. The strip already measures ≈402pt against ≈361pt usable, so nothing may be appended.
- **One canonical deep link, on the root stack only** — `MockDraft: 'app/league/mock-draft'` in `mobile/src/utils/deepLinks.ts` (the `V2_SCREENS` table at `:95`, following the single-path rule recorded at `:108-115`).
- `MockDraftScreen` is a root-stack push copying the `FreeAgents` block (`mobile/src/navigation/RootNav.tsx:492-519`) **including the `headerBackVisible:false` + custom `HeaderBack` iOS-26 workaround** — omitting it leaves back dead. It mounts its own `<FeedbackFAB activeScreen="MockDraft" aboveTabBar={false} />` (`FreeAgentsScreen.tsx:275` pattern); the **setup sheet** is a modal and therefore exempt.
- **Honest seasonality:** a real-league rookie mock needs an undrafted class, so it is dead Sept 2026 – Apr 2027. The year-round surface is **practice/replay** (2026 class vs pre-draft roster snapshots from the M1 corpora) — ship it as the dogfood/QA surface and the calibration harness, **not** as a marketed year-round feature (O5: allowlist).

**Flag:** `draft.mock`, OFF. Effective gating is `draft.room` **AND** `draft.mock`. It depends on neither `draft.live_poll` (no polling — the mock never touches the `refetchInterval` machinery) nor `draft.mfl` nor `picks.slot_values`.

---

### 4.3 W3 M-A — assignment: store, seeder, routes (flag `picks.assign`)

**File ownership:** `backend/database.py` (schema + the three functions), `backend/server.py` (three routes + helpers), `mobile/src/screens/PickAssignmentScreen.tsx` (new), `mobile/src/screens/LeagueScreen.tsx` (the section below Explore), `mobile/src/state/useSession.ts` (P-1), `mobile/src/navigation/RootNav.tsx` + `utils/deepLinks.ts`.

**4.3.1 `load_draft_picks` — the exact contract.**

```python
# backend/database.py — replaces the body at :7468-7489. Signature is ADDITIVE.
_PICK_SOURCE_PLATFORM = "platform"
_PICK_SOURCE_USER     = "user"
_PICK_SOURCE_ANY      = "any"

def load_draft_picks(
    league_id: str,
    owner_user_id: str | None = None,
    source: str = _PICK_SOURCE_PLATFORM,
    include_contested: bool = False,
) -> list[dict]:
    """Draft picks for a league, optionally filtered to one owner.

    `source` is THE containment (ADR-010). It defaults to platform-only, so
    every pre-existing call site is byte-identical until it explicitly opts in:

      "platform"  ->  source IS NULL OR source = 'platform'   (DEFAULT)
                      Every pre-W3 row has source IS NULL, so this selects
                      exactly today's rows, in today's order.
      "user"      ->  source = 'user'
      "any"       ->  no source predicate

    When the result CAN contain user rows ("user"/"any") and
    `include_contested` is False, contested slots are dropped — see
    `contested_pick_ids`. Contested exclusion is a ROW FILTER and must never
    be implemented by nulling `pool_value`: server._power_picks_by_owner
    re-derives a price from a NULL pool_value (server.py:17241-17244), so
    nulling would silently re-price the very row the rule withholds (INV-5).

    Ordering (season ASC, round ASC, pick_value DESC) is unchanged.
    """
```
Implementation notes:
- Build the predicate with SQLAlchemy `or_` / `is_(None)`; do **not** hand-write SQL (the module has no raw `SELECT`).
- The contested drop happens **in Python** after the fetch — `contested_pick_ids` is memoised, and pushing it into SQL would need a JSON extraction that is dialect-divergent.
- `owner_user_id is not None` (not truthiness) is preserved exactly: passing `""` still filters to empty-string owners.

**4.3.2 The seven opt-in call sites — enumerated (operator decision 4).**

All seven opt in, implemented in **S1 → S4 build order**, each golden-diffed independently, **all landing behind `picks.assign_tradeable`**. The opt-in is a literal keyword argument at each site so the AST test has something to enumerate:

```python
# backend/server.py — module helper, defined beside _picks_pool_cap (:8587)
def _assigned_picks_source() -> str:
    """'any' when asserted picks are live, else the platform-only default.

    ONE function so a single flag flip lights or kills all seven sites, and so
    the D12 AST test has exactly one sanctioned expression to look for.
    """
    return "any" if is_enabled("picks.assign_tradeable") else "platform"
```

| Stage | Site | Symbol | Current line | Change |
|---|---|---|---|---|
| **S1** | `/api/league/picks` | `get_league_picks` | `backend/server.py:8558` | `load_draft_picks(league_id=league_id, source=_assigned_picks_source(), include_contested=True)` — **the one site that asks for contested rows**, rendering them unpriced as open questions |
| **S1** | `/api/trade/evaluate` | `_trade_evaluate_impl` | `:8104` | `source=_assigned_picks_source()`. Prices through `priced_pool_value` already (`:8105-8106`) |
| **S2** | power rankings + rank chip | `_power_picks_by_owner` | `:17230` | `source=_assigned_picks_source()`. **Reads stored `pool_value` and re-derives on NULL** (`:17241-17244`) — the reason INV-5 forbids nulling |
| **S2** | own outlook seed | `_user_pick_share` | `:4387` | `source=_assigned_picks_source()`. Sums the **legacy** `pick_value`, not `pool_value` |
| **S3** | owned-pick injection | `_owned_pick_assets` | `:8629` | `source=_assigned_picks_source()`. Prices through `priced_pool_value` (`:8633-8634`) |
| **S3** | opponent pick shares | `_run_trade_job` | `:4526` | `source=_assigned_picks_source()`. Sums the legacy `pick_value` |
| **S4** | evener candidates | `_roster_eveners` | `:953` | `source=_assigned_picks_source()`. **Reads raw `pool_value`** (`:955`) — blind to the M6b mode, see §4.5 |

**[RV-3]** All seven line numbers were verified undrifted at `20c2a54`; re-locate by **symbol** at build time.

**4.3.3 `replace_draft_picks` — provenance-scoped deletion (INV-2).**

```python
def replace_draft_picks(league_id: str, rows: list[dict],
                        preserve_source: str | None = None) -> None:
    """Snapshot-replace one PROVENANCE's draft-pick rows for one league.

    `preserve_source` names the provenance THE CALLER OWNS. The DELETE is
    scoped to exactly that provenance and never crosses it — the whole
    invariant is "a writer only ever deletes rows it could have written"
    (INV-2). Read the two branches literally; the parameter name is the
    plan's and it reads backwards on the default branch:

      None (default)  -> DELETE WHERE league_id = ? AND (source IS NULL
                         OR source <> 'user')
                         The historical behavior, NARROWED. Every existing
                         caller (sync_draft_picks, _sync_mfl_owned_picks) keeps
                         this and therefore can no longer destroy assertions.
      'user'          -> DELETE WHERE league_id = ? AND source = 'user'
                         The assignment projection is the ONLY caller passing
                         this, and it cannot touch a platform row.

    Rows still carry their own `synced_at`.
    """
```
The insert half (chunked at 200, `:7462-7465`) is unchanged. Callers to update: `database.sync_draft_picks:7443` (leave the default), `server._sync_mfl_owned_picks:8780` + `:8839` (leave the default), and the new assignment projection (`preserve_source='user'`).

**[RV-4]** Re-grep `replace_draft_picks(` before the wave. Today there are exactly three production call sites; a fourth appearing means a new platform writer landed and must be re-checked against INV-2.

**4.3.4 `seed_pick_grid` — the pristine seeder.**

```python
# backend/database.py — beside sync_draft_picks (:7311)

def seed_pick_grid(
    league_id: str,
    member_user_ids: list[str],          # ordered; index i => original_roster_id str(i+1)
    user_id_to_name: dict[str, str],
    actor_user_id: str,
    current_season: int,
    rounds: int,
    seasons_ahead: int = 3,              # operator decision 3: current + 3
    league_size: int | None = None,
    scoring_format: str = "1qb_ppr",
    reseed: bool = False,
) -> dict:
    """Write the PRISTINE grid: every team owns its own picks, every season.

    Returns {"seeded": int, "reseeded_over": int, "total": int}.
    Idempotent: re-running without `reseed` preserves every edited slot (D14).
    """
```

```
seed_pick_grid(...):

    # ── 0. CLAMP. The conservation bound's only lever (KD-4, operator dec. 2).
    rounds = max(1, min(int(rounds), draft_status.ROOKIE_MAX_ROUNDS))     # == 8
    teams  = league_size or len(member_user_ids)
    assert teams >= 1

    existing = {r["pick_id"]: r for r in
                load_draft_picks(league_id, source="user")}      # NOT "any"

    rows, seeded, reseeded_over = [], 0, 0

    # ── 1. current + 3 seasons. A loop bound, effectively free (operator dec. 3).
    #    The UX cost is NOT free: the client defaults to the current season and
    #    collapses the other three, and the confirm-the-board review step is
    #    PER SEASON, never one 192-row scroll (KD-5).
    for season in range(current_season, current_season + seasons_ahead + 1):
        years_out = season - current_season
        for idx, uid in enumerate(member_user_ids):
            orig_rid = str(idx + 1)                # opaque, league-local slot label.
                                                   # league_members has NO roster_id
                                                   # column (database.py:304-313), so this
                                                   # is never resolved against a platform.
            for rnd in range(1, rounds + 1):
                pick_id = make_pick_id(league_id, season, rnd, orig_rid)   # INV-8
                prior = existing.get(pick_id)
                if prior is not None and not reseed:
                    rows.append(prior)             # PRESERVE the edit verbatim (D14)
                    continue
                if prior is not None:
                    reseeded_over += 1
                seeded += 1
                rows.append({
                    "pick_id":            pick_id,
                    "league_id":          league_id,
                    "season":             season,
                    "round":              rnd,
                    "owner_user_id":      uid,             # pristine: own your own picks
                    "owner_username":     user_id_to_name.get(uid, f"Team {orig_rid}"),
                    "original_roster_id": orig_rid,
                    "original_user_id":   uid,
                    "original_username":  user_id_to_name.get(uid, f"Team {orig_rid}"),
                    "is_traded":          0,
                    # ── D13: the SHIPPED functions, never a user value. ──
                    "pick_value":  compute_pick_value(rnd, season, current_season, teams),
                    "pool_value":  pick_pool_value(rnd, years_out, scoring_format),
                    "platform":    "espn",          # provenance of the LEAGUE, not the row
                    "source":      "user",
                    "assigned_by": actor_user_id,
                    "assigned_at": _now(),
                    "synced_at":   _now(),
                })

    replace_draft_picks(league_id, rows, preserve_source="user")   # INV-2
    _invalidate_contested(league_id)
    return {"seeded": seeded, "reseeded_over": reseeded_over, "total": len(rows)}
```

**Why each part is what it is** (so a reviewer catches a "simplification"):
- The clamp is step **0** because everything below it is bounded by `rounds`. Moving it into the route leaves the DB function unclamped and the conservation bound unenforced.
- `existing` is loaded with `source="user"`, not `"any"` — the seeder must never read, and therefore never rewrite, a platform row.
- The pristine default is what makes 192 slots tractable: a league with 3 trades leaves 189 untouched, and the 3 float into the "Traded picks" review summary. This is why entry correctness matters more than conflict resolution (HLD RB-3).
- `platform: "espn"` records where the *league* lives; `source: "user"` records who asserted the *row*. They answer different questions and both are needed — the two engine guards read `platform`, the containment reads `source`.
- Orphaned owners are not handled here (the seeder writes only current members); they arise when a member leaves **after** seeding, and are surfaced by the read path (§4.3.6).

**`make_pick_id` (INV-8).** `pick_id` is built by three duplicated f-strings today (`backend/database.py:7369`, `:7404`, `backend/server.py:8823`). M-A adds a fourth unless it introduces the single constructor:
```python
def make_pick_id(league_id: str, season: int, round_: int, original_roster_id: str) -> str:
    """THE pick_id format: {league}_{season}_{round}_{original_roster}.
    Round is unpadded, so pick_id is NOT lexicographically sortable."""
    return f"{league_id}_{season}_{int(round_)}_{original_roster_id}"
```
Rebase all four sites onto it and pin with T-W3-10. **This is the one refactor W3 is allowed** — it is required by the invariant, not a drive-by.

**4.3.5 The CAS write.**

```python
# backend/database.py
def assign_draft_pick(league_id: str, pick_id: str, owner_user_id: str,
                      owner_username: str, actor_user_id: str,
                      if_assigned_at: str | None) -> tuple[str, dict | None]:
    """Compare-and-swap one slot. Returns (outcome, row).

    outcome ∈ 'ok' | 'stale' | 'not_found'. On 'stale' the row is the CURRENT
    row so the route can 409 with it in one round trip.

    The comparison lives in the UPDATE's WHERE clause, so it is atomic under
    both dialects without SELECT-then-UPDATE. `IS NOT DISTINCT FROM` is
    Postgres-only, so the NULL case is a separate portable predicate.
    """
```
```
assign_draft_pick(...):
    with engine.begin() as conn:
        row = SELECT * FROM draft_picks WHERE pick_id = :pick_id
                                          AND league_id = :league_id
        if row is None: return ('not_found', None)

        token_pred = (draft_picks.c.assigned_at.is_(None) if if_assigned_at is None
                      else draft_picks.c.assigned_at == if_assigned_at)

        is_traded = int(owner_user_id != row.original_user_id)
        result = UPDATE draft_picks
                 SET owner_user_id  = :owner_user_id,
                     owner_username = :owner_username,
                     is_traded      = :is_traded,
                     source         = 'user',
                     assigned_by    = :actor_user_id,
                     assigned_at    = :now
                 WHERE pick_id = :pick_id AND league_id = :league_id AND <token_pred>

        if result.rowcount == 0:
            return ('stale', SELECT * ...)          # re-read INSIDE the txn
        return ('ok', SELECT * ...)
```
**Never writes a value column.** `pool_value` / `pick_value` are a function of `(round, season)` and ownership does not change either, so an assignment UPDATE touching them would be a bug (D13). The seeder is the only writer of those two.

Immediately after an `ok`, the route emits the audit event and invalidates the contested memo:
```python
record_event(actor_user_id, "pick_assignment_changed", league_id=league_id, props={
    "pick_id": pick_id, "season": season, "round": round_,
    "original_team": original_roster_id,
    "old_owner": prior_owner, "new_owner": owner_user_id, "actor": actor_user_id,
})
_invalidate_contested(league_id)
```
`pick_assignment_changed` is appended to `analytics_taxonomy.SERVER_FIRED_EVENTS` (`:86`). It must **not** appear in `ALLOWED_CLIENT_EVENTS` — the import-time disjointness assert (`:216`) would raise, and a client-forgeable audit row is a forgeable audit trail.

**4.3.6 Contested derivation (KD-6, INV-5).**

```python
# backend/database.py
def contested_pick_ids(league_id: str) -> frozenset[str]:
    """Slots ≥2 distinct users assigned to ≥2 DIFFERENT owners (plan §6.3).

    Derived from the pick_assignment_changed audit trail — there is no
    contested column (the plan specifies three additive columns and names
    user_events as the audit trail).

    Memoised per league for _CONTESTED_TTL_SECONDS and invalidated explicitly
    on every write (_invalidate_contested), so a correction un-contests a slot
    at the next read rather than after a TTL.
    """
```
```
contested_pick_ids(league_id):
    cached = _CONTESTED_CACHE.get(league_id)
    if cached and now - cached[0] < _CONTESTED_TTL_SECONDS: return cached[1]

    rows = SELECT props FROM user_events
           WHERE event_type = 'pick_assignment_changed' AND league_id = :league_id
           # covered by ix_user_events_type_occurred (database.py:1011)

    by_pick: dict[str, set[tuple[str, str]]] = {}      # pick_id -> {(actor, new_owner)}
    for r in rows:
        p = json.loads(r.props or "{}")   # try/except (JSONDecodeError, TypeError) -> skip
        by_pick.setdefault(p["pick_id"], set()).add((p["actor"], p["new_owner"]))

    contested = frozenset(
        pid for pid, pairs in by_pick.items()
        if len({a for a, _ in pairs}) >= 2 and len({o for _, o in pairs}) >= 2
    )
    _CONTESTED_CACHE[league_id] = (now, contested)
    return contested
```
**Both conditions are required.** Two actors agreeing on the same owner is not a disagreement; one actor changing their own mind twice is not a disagreement either.

**Orphaned owners (D14).** A slot whose `owner_user_id` is not in `league_members` for that league is **orphaned**: excluded from the priced union (same row filter as contested) and surfaced in the assignment payload as `orphaned: true` so it becomes a re-assign row. **Never silently dropped** — a dropped slot is value that vanishes with no explanation.

**4.3.7 P-1 — the `connectLeague` merge fix (BLOCKING for M-A).**

`useSession.connectLeague` (`mobile/src/state/useSession.ts:404-451`) builds `merged` from `getLeagues()` output plus at most the league being connected, then calls `setLeagues(merged)` (`:420-435`). The prior `state.leagues` is **never read**, so it is a full replace. `getLeagues` hits `/api/sleeper/leagues/<user_id>`, whose local-league append filters to **non-numeric** ids (`backend/database.py:5738`), and platform-imported leagues carry numeric platform-native ids (`backend/server.py:12307-12310`). Net effect: connecting any Sleeper league silently drops every ESPN row — which is already why the ESPN re-sync button disappears.

```ts
// mobile/src/state/useSession.ts — replacing the merge at :425-435
const prior = get().leagues ?? [];
const fresh = new Set(lgs.map((l) => l.league_id));
// P-1: /api/sleeper/leagues cannot contain a linked-platform league (its local
// append filters to non-numeric ids, database.py:5738), so a wholesale replace
// drops every ESPN/MFL/Fleaflicker row. Carry those forward.
const carried = prior.filter(
  (l) => (l.platform ?? 'sleeper') !== 'sleeper' && !fresh.has(l.league_id),
);
const merged: LeagueSummary[] = [...lgs, ...carried];
if (!merged.some((l) => l.league_id === result.league_id)) {
  merged.push({ league_id: result.league_id, name: result.league_name });
}
await get().setLeagues(merged);
```
**[RV-5] — the `platform` field is only trustworthy when `draft.room` is on.** `mobile/src/api/sleeper.ts:17` coerces `platform: lg.platform ?? 'sleeper'`, and the server stamps `platform` **only** inside the `if is_enabled("draft.room")` block (`backend/server.py:12281-12297`). `draft.room` is currently `true` (`config/features.json:145`), so the field is real today — but any predicate reading `platform` off a cached league inherits the exact trap commit `ab5050f` fixed for the draft-tab predicate. Re-verify before relying on it.

**4.3.8 Entry point + screen.**

- **A dedicated "Draft picks" section BELOW Explore**, inserted at `mobile/src/screens/LeagueScreen.tsx:542` — immediately after the Explore grid's closing `</View>` and before `<MarketPulseStrip />` at `:547`. **Not** a 4th Explore tile: that row is a fold-budgeted 3-across grid (`:499-542`) whose third slot is already a one-slot/two-occupant conditional (`:516-541`). Follow the sibling convention there: a bare `<View style={styles.divider} />` then a `<TickLabel>`, with **no** `marginTop` on the divider (the #243 double-margin fix).
- Sub-line: `"Not assigned yet"` / `"48 of 48 · 3 traded"` — computed from `progress`. This also keeps assignment visibly "separate from the draft feature", as the operator asked.
- `PickAssignmentScreen` is a root-stack push copying the `FreeAgents` block (`RootNav.tsx:492-519`) **including** the `headerBackVisible:false` + `HeaderBack` workaround; it mounts its own `<FeedbackFAB activeScreen="PickAssignment" aboveTabBar={false} />`; it gets exactly **one** deep-link path in `V2_SCREENS` (`mobile/src/utils/deepLinks.ts:95`). Per `mobile/src/navigation/CLAUDE.md`, URL-addressability is definition-of-done.
- **The 48-tap problem — three defaults, in priority order:** (1) the pristine seed, so a league with 3 trades leaves 189 of 192 slots untouched; (2) order is set **once** — a drag list of N teams for round 1 plus a linear/snake toggle (numbering only, never ownership, so the toggle is safe); (3) edit only the traded ones, which float into a **"Traded picks"** review summary. Progress is explicit, saves are **per slot**, and there is **no giant dirty form**.
- **Season handling (KD-5):** default to the current season with the other three collapsed behind season tabs/accordions. The confirm-the-board review step is **per season**.

---

### 4.4 W3 M-B — the ESPN Draft Room state (same flag `picks.assign`)

```python
# backend/draft_board_service.py — a NEW public function. build_board is NOT modified.

def assigned_board(req: BoardRequest, *, grid: "AssignmentGrid",
                   fetchers: Fetchers | None = None) -> dict:
    """The ESPN room, built entirely from the assignment grid.

    ZERO platform egress in every state (D15) — ESPN has no draft object, now
    or ever. This function therefore does NOT participate in _cache, _inflight,
    the breaker or the budget: there is no upstream to protect and a DB read is
    cheaper than a cache lookup plus a staleness decision.

    `fetchers` is optional and used ONLY for rookie_ids/players (the same two
    lazily-imported DB reads _undrafted already needs).
    """
```
```
assigned_board(req, grid):
    if not grid.slots:
        return _render_unavailable(req, "espn",
                                   notice=_notice(NOTICE_PICKS_NOT_ASSIGNED))

    order = [ {slot, round, pick_no, owner_user_id, owner_username,
               original_user_id, original_username, is_traded}
              for each grid slot of req.season, ordered by (round, slot) ]
        # pick_no from the linear/snake toggle: linear -> (round-1)*teams + slot
        #                                       snake  -> reverse even rounds
        # Slot NUMBERING only. Ownership is never derived from the toggle.

    order = _cap_order(order)                    # the shipped 500-entry guard (:841)
    picks = _recorded_picks_projection(...)      # [] until M-D lands (I-7)
    drafted  = {p["player_id"] for p in picks}
    rostered = set(req.rostered_ids or ())
    # NOTE the SHIPPED signature returns a TUPLE (:885-888):
    undrafted, class_loaded = _undrafted(req.season, drafted, rostered, req.basis,
                                         req.board_elo, req.consensus_elo, fetchers)

    return _payload(req, "espn",
        state = COMPLETE if picks and len(picks) >= len(order) else
                (LIVE if picks else UPCOMING),
        kind = KIND_ROOKIE,
        season = req.season, rounds = grid.rounds, teams = grid.teams,
        order = order, order_confidence = ORDER_ASSIGNED,
        picks = picks, undrafted = undrafted,
        undrafted_suppressed = not class_loaded,
        entry = _synthetic_entry(as_of = grid.newest_assigned_at),
        notice = None if class_loaded else _notice(NOTICE_CLASS_NOT_LOADED),
        deep_link = None)                     # D9: no platform CTA exists for ESPN
```
- `_render_unavailable` (`:1164-1191`) and `_payload` (`:1107-1147`) both emit the **same 18 keys**; `assigned_board` must not invent a 19th. `slot_value_approx` remains conditional and is inert while `picks.slot_values` is off.
- `_synthetic_entry` is a minimal `_Entry` with `loaded=True`, `degraded=None`, `fetched_at=_now_monotonic()` and `state` set, so `_is_stale` (`:1194-1200`) returns `False` for a freshly-read grid. **A grid is never "stale"** — it is a fact in our own database, not a cached remote read.
- **The route branch** is the only `server.py` edit (§2.5). Flag off ⇒ `dbs.unsupported_board(req)` at `:10201-10202`, byte-identical.

---

### 4.5 W3 M-C — trade-math activation (SEPARATE flag `picks.assign_tradeable`)

**4.5.1 The one helper replacing two duplicated literals (I-4).**

```python
# backend/server.py — beside _owned_pick_assets (:8597)
def _owned_picks_available(league_id: str, league) -> bool:
    """Whether owned picks may enter engine math for this league.

    Replaces the duplicated three-clause literals at :4570-4572 and :9309-9311.
    ALL THREE conjuncts are preserved — factoring out only the platform test
    would silently re-enable picks for demo leagues and with the flag off.

    ESPN becomes a DATA test rather than a platform test (plan §6.1): an ESPN
    league with assignments qualifies; without them it honestly does not.
    """
    if not FLAGS.trade_picks_in_pool:
        return False
    if league_id == "league_demo":
        return False
    if getattr(league, "platform", None) != "espn":
        return True
    return is_enabled("picks.assign_tradeable") and _has_assigned_picks(league_id)
```
```python
def _has_assigned_picks(league_id: str) -> bool:
    """SELECT 1 FROM draft_picks WHERE league_id=? AND source='user' LIMIT 1.
    Memoised per (league_id) for 60s; invalidated by _invalidate_contested's
    sibling so an assignment lights the league up immediately."""
```
Both call sites become `if _owned_picks_available(league_id, g_league):`. With `picks.assign_tradeable` off the function is **exactly** today's expression for every league, which is what makes the golden diff green.

**4.5.2 `picks_supported` as a data test (I-5).**

```python
# backend/server.py:8553-8554, inside get_league_picks
platform  = getattr(g_league, "platform", None) if g_league else None
supported = platform != "espn" or (
    is_enabled("picks.assign") and _has_assigned_picks(league_id))
```
Two emit sites (`:8556`, `:8564`) are unchanged. It is a **display label only** — it gates no engine path (the guards are §4.5.1's). ESPN with no assignments still honestly says `false`. Client consumers unchanged: `mobile/src/api/league.ts:142`, `mobile/src/components/InLeagueCalculator.tsx:219`.

**4.5.3 Provenance on every priced payload (D17).**

Each of the five priced surfaces carries, per asserted pick: `source: "user"`, and a correction deep link `{leagueId, season, focusPickId}`. The client label is **"Member-entered — not verified with ESPN"** — exact copy, on all five, no abbreviation. `_owned_pick_label` (`backend/server.py:8570`) is **not** modified: the label is a display string shared with Sleeper/MFL leagues and changing it would relabel every league's picks. Provenance rides its own field.

**4.5.4 D13's bar, restated against the code that actually prices (HLD RB-1).**

The plan words D13 as "byte-equal to `compute_pick_value`/`pick_pool_value`". Since M6b shipped, the read-time price is mode-dependent:

| Site | Prices via | Mode-aware? |
|---|---|---|
| `/api/trade/evaluate` `:8105-8106` | `priced_pool_value` | yes |
| `_owned_pick_assets` `:8633-8634` | `priced_pool_value` | yes |
| `_roster_eveners` `:955` | `float(pk.get("pool_value") or 0.0)` | **no** |
| `_power_picks_by_owner` `:17241-17244` | stored `pool_value`, re-derives via `pick_pool_value` on NULL | **no** |

**Restatement (binding for the test, not a change to the decision):** *every `source='user'` row's stored `pool_value` is byte-equal to `pick_pool_value(round, season − current_season, scoring_format)`, and its rendered price at every read site is byte-equal to `priced_pool_value(row, scoring_format=fmt, mode=m)` for the caller's mode `m` ∈ `{tier_ladder, market_slots}`.* The property test runs under **both** modes. The conservation bound survives unchanged because both modes are pure functions of the pick's coordinates — `market_pick_pool_value` keys off absolute `season`, `pick_pool_value` off `years_out`, and neither reads ownership.

**4.5.5 Build order.** Implement and golden-diff **S1 → S2 → S3 → S4** in that order, each site independently verified, **all four landing together** behind `picks.assign_tradeable` (operator decision 4). The §6.8 thresholds are monitoring and rollback triggers, **not** ship gates.

---

### 4.6 W3 M-D — live offline recording (flag `draft.manual_picks`, separate wave)

**4.6.1 The offline queue contract — copied from `mobile/src/api/events.ts` (A-12), field by field.**

| Property | `events.ts` value | M-D value | Notes |
|---|---|---|---|
| AsyncStorage key | `'ftf.events.queue.v1'` (`:42`) | `'ftf.recpicks.queue.v1'` | Own namespace; the shape-version suffix convention is preserved |
| Persisted blob | `{ v: 1, events: [...] }` (`:167`) | `{ v: 1, picks: [...] }` | Any other shape ⇒ counted + `removeItem` (`:132-143`) |
| Idempotency | `event_id: uuidv4()` at enqueue (`:201`); `crypto.getRandomValues`, **never** `Math.random` (`:72-91`) | identical — **reuse the same `uuidv4` by extracting it to a shared module** | Two devices recording the same pick will not share a uuid, which is why the *server* key is `(league, season, overall)` |
| Cap | `MAX_QUEUE = 500` (`:46`) | `MAX_QUEUE = 500` | A 192-slot draft cannot overflow it; a hit is a bug |
| Batch | `BATCH_MAX = 50` (`:47`) | `50` | |
| Eager flush | `FLUSH_AT = 20` (`:48`) | **`1`** | The only deliberate divergence: a pick is a user-visible commitment, so send immediately when online. The batching path still exists for the offline backlog |
| Interval | `FLUSH_INTERVAL_MS = 10_000` (`:49`) | `10_000` | |
| Timeout | `SEND_TIMEOUT_MS = 10_000` (`:52`) | `10_000` | Own `AbortController` (`:298-299`) |
| Backoff | `[30_000, 120_000, 600_000]` with **±20% jitter** (`:53`, `:238`) | identical | `applyBackoff(toMax)` semantics (`:228-240`) |
| Reset | on any consumed batch (`:257`) and on foreground `active` (`:148`) | identical | Foregrounding does **not** flush; it clears the backoff window so the next tick sends |
| Trim policy | drop oldest **non-critical** first, then slice the critical remainder (`:173-184`) | every recorded pick is critical ⇒ FIFO slice only | And **count it** — `record_queue_dropped` non-zero blocks the release (zero tolerance, §6.8) |
| Transport | raw `fetch`, **not** `apiRequest` (`:296-297` — the wrapper's 401 handling clears the session token) | identical | Headers: `getClientHeaders()` + `Content-Type` + `X-Device-Id` + `X-Session-Token` when present |
| Reconciliation | `{accepted, deduped, rejected:[{index,reason}], disposition}` (`:316-320`) | identical | Ladder: 5xx ⇒ retry; other `!ok` ⇒ consumed + purgeAll; unparseable ⇒ purgeAll; `sum < batch.length` ⇒ purge only the rejected indices, requeue survivors via `splice` (`:261-267`) |
| Guards | `inFlight` (`:244`), flag re-checked every loop iteration (`:251`), every public path try/catch-swallowed | identical | |

**Do not invent a second queue.** Extract `uuidv4`, the backoff ladder and the `sendBatch` disposition ladder into a shared `mobile/src/api/_queue.ts` and have **both** `events.ts` and the recorder consume it — otherwise the two drift and only one of them has production evidence behind it.

**4.6.2 Server-side recording.**

```python
# backend/database.py
def record_draft_picks(league_id: str, season: int, rows: list[dict],
                       recorded_by: str) -> dict:
    """Idempotent batch insert. Returns {'accepted', 'deduped', 'rejected'}.

    Dedup is by the UNIQUE (league_id, season, overall). A row whose (league,
    season, overall) already exists with the SAME player_id counts as
    `deduped`; with a DIFFERENT player_id it is a CORRECTION and UPDATEs in
    place (voided_at back to NULL) — which is why undo is voided_at rather
    than a partial unique index (§3.2).
    """

def void_recorded_pick(league_id: str, season: int, overall: int,
                       actor: str) -> dict | None:
    """Non-destructive undo: SET voided_at = now(). Never DELETEs."""

def load_recorded_picks(league_id: str, season: int) -> list[dict]:
    """Live rows only: WHERE voided_at IS NULL, ORDER BY overall.
    The .is_(None) predicate mirrors deck_suppressions (database.py:4485)."""
```
The insert uses the same dialect-branched upsert shape as `upsert_league_members` (`backend/database.py:5052-5075`): SQLite `INSERT OR REPLACE`, Postgres `pg_insert(...).on_conflict_do_update(constraint="uq_recorded_pick_slot", ...)` with the **function-local** `pg_insert` import. Conflict targeting is by **constraint name**, which is why `uq_recorded_pick_slot` carries an explicit `name=`.

**4.6.3 The recording UX.**
With the grid assigned, attribution costs **zero extra gestures**: the app knows whose pick 1.03 is, so recording is tap player → confirm, with the cursor auto-advancing through `overall`. The team is editable **only** when the grid was wrong. **One recorder for all 48 picks, any linked user** — no designated-recorder role. This is why M-D sequences after M-A.

---

## 5. Error Handling, Races & Budgets

### 5.1 Named races

| # | Race | Resolution |
|---|---|---|
| RC-1 | Two users `PUT` the same slot concurrently | The CAS predicate is inside the UPDATE's WHERE (§4.3.5). The loser's `rowcount == 0` ⇒ `409` + the current row, re-read **inside the same transaction** |
| RC-2 | Two users `PUT` different slots | Different `pick_id`s ⇒ different rows ⇒ both succeed. No table-level lock is taken |
| RC-3 | A seed runs while another user is editing | `seed_pick_grid` preserves every `source='user'` row unless `reseed=true` (§4.3.4), and its `replace_draft_picks(preserve_source='user')` is one transaction. Worst case the editor's next `PUT` 409s on a token that moved |
| RC-4 | A platform sync fires for a league with assertions | Impossible for ESPN today (nothing calls it), and closed structurally: the sync's DELETE cannot cross provenance (INV-2), and D12 asserts no path outside the assignment routes reaches `replace_draft_picks`/`sync_draft_picks` for an ESPN league |
| RC-5 | Contested memo is stale after a correction | `_invalidate_contested(league_id)` runs in the same request as every write. The 60 s TTL is a backstop for cross-process staleness, not the primary mechanism |
| RC-6 | Two devices record the same physical pick offline, then both reconnect | The server key is `(league, season, overall)`, **not** the client uuid, so the second is `deduped`. Same player ⇒ dedupe; different player ⇒ the later write is a correction and the audit trail shows both |
| RC-7 | A recorded pick arrives for a slot the grid later reassigns | `recorded_picks.picking_team_id` is a snapshot; the board renders the recorded team. The grid is truth for *ownership*, the recording is truth for *what happened* — the two are deliberately not reconciled |
| RC-8 | A mock is resumed after `model_config` is retuned | The fitted noise parameters are snapshotted into `settings.noise` at creation (§3.3), so a resume replays identically |
| RC-9 | `connectLeague` fires while an assignment write is in flight | Independent stores. P-1's merge is client-side cache only and never touches `draft_picks` |

### 5.2 Timeout & budget table

| Path | Budget | On expiry |
|---|---|---|
| ESPN board render | One indexed `draft_picks` read + the shipped `_undrafted` DB reads | No upstream, no breaker, no budget. A DB failure degrades to `unsupported_board` |
| Contested derivation | Memoised 60 s per league; index-covered scan of `user_events` | On failure, treat the contested set as **empty** and log — a failure must not silently unprice a whole league |
| Assignment `PUT` | One transaction, no I/O beyond the DB | 409 or 5xx; the client retries with the fresh token from the 409 body |
| Recorded-picks batch | ≤50 rows, one transaction | 5xx ⇒ the client's `{kind:'retry'}` ladder + backoff |
| Client record queue | 500 items · 50/batch · 10 s interval · backoff `[30 s, 2 m, 10 m]` ±20% | Trim is FIFO and **counted**; any drop blocks the release |
| Mock CPU tail | ≤192 picks × ≤10 candidates, in-request | No timeout needed; the work is microseconds |
| W1 anchor save | The shipped route's own budget | Optimistic rollback + toast |

### 5.3 Unbounded-resource guards

`order[]` reuses the shipped `_cap_order` 500-entry guard (`backend/draft_board_service.py:841`) · `undrafted[]` reuses `_UNDRAFTED_CAP = 300` (`:141`) · the assignment grid is bounded by `rounds ≤ 8 × teams × 4 seasons` and the route refuses `rounds` outside `1..8` · the contested memo holds one frozenset per league and is invalidated on write · `recorded_picks` is bounded by the same grid · `mock_drafts` holds one active row per user+league, enforced in the create transaction.

---

## 6. Flags, Docs & Compatibility

### 6.1 The 4-touch flag convention (test-enforced)

Two tests make this non-optional: `backend/tests/test_seed_ui_test_db.py:105-111` (`flags/release.json` must be an **exact** mirror of `config/features.json` after stripping `_`-prefixed keys — dict equality, so a missing key *or* a diverging value fails) and `backend/tests/test_entitlements.py:88-98` (every non-`_` key in `features.json` must exist in `DEFAULT_FLAGS`).

Per new flag, in order:
1. **`backend/feature_flags.py`** — append to the `FLAG_KEYS` tuple (`:47-418`), with a comment stating what it gates **and the flag-off behavior**. `DEFAULT_FLAGS = {key: False for key in FLAG_KEYS}` (`:420`) makes it default-`False` mechanically.
2. **`config/features.json`** — add the key with `false`, plus a `_comment_draft_extensions` prose block introducing the tranche (the `_comment_rookie_draft` pattern at `:143`).
3. **`backend/tests/fixtures/flags/release.json`** — mirror the exact key/value.
4. **`docs/config-reference.md` → `## Feature flags`** (intro at `:42`) — one row per flag in a new `### Draft extensions` sub-section.

**A conditional 5th touch:** `mobile/src/state/useFeatureFlags.ts` → `LAUNCHED_FLAG_DEFAULTS` (`:44-51`) — added **only** when a flag ships ON. All five of these ship dark, so **none of them touch it**.

`backend/tests/fixtures/flags/all-on.json` is a partial 42-key overlay for flag-sweep matrix cells and is **not** part of the convention.

The five flags: `draft.rank_inline` (W1) · `draft.mock` (W2) · `picks.assign`, `picks.assign_tradeable` (W3 M-A/M-B/M-C) · `draft.manual_picks` (W3 M-D). *(The plan §9's `draft.manual_tracking` / `draft.manual_import` name the pre-revision design and are superseded by §6 REVISED — the mirror test needs exactly one target list.)*

Flag-pinning idiom in tests (there is **no `conftest.py`**):
```python
import backend.feature_flags as ff
saved = ff._flags_cache
ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.assign": True}
... ; ff._flags_cache = saved
```

### 6.2 Docs each milestone must touch

| Milestone | Docs |
|---|---|
| **W1** | 4-touch for `draft.rank_inline` · `docs/api-reference.md` — the `via`/`surface` field on `POST /api/anchor/save` (in the Ranking/Anchors region) · `docs/business/analytics/` — a **tracking-plan addendum** for the four new client events (a precondition for the taxonomy registration) · `docs/design/components.md` **only if** a visible overflow affordance is specced (RB-12) |
| **W2** | 4-touch for `draft.mock` · `docs/data-dictionary.md` — new `## mock_drafts` section · `docs/api-reference.md` — a new `## Mock draft (flag draft.mock)` section after `## Draft room` (`:311`) · `docs/config-reference.md` §model_config — `mock_max_reach_slots`, `mock_jitter_slots` · `docs/glossary.md` — "Mock draft", "Drafter persona", "Need severity", "Reach" · `docs/plans/draft-extensions/mock-calibration-2026-08.md` (I-10, the gate artifact) |
| **W3 M-A** | 4-touch for `picks.assign` · `docs/data-dictionary.md` §`draft_picks` (`:409-427`) — the three columns **and the containment rule** (`load_draft_picks` defaults to platform-only), plus the new index · `docs/api-reference.md` §League — the three assignment routes and the CAS/409 contract · `docs/architecture.md` §Data flow — assignment → projection → the seven read sites · `docs/glossary.md` — "Pick assignment", "Provenance", "Contested slot", "Pristine grid" · `docs/runbook.md` — a new `## Pick-assignment recovery` section (how to reconstruct a league's grid from `pick_assignment_changed` events) · **`docs/adr/adr-010-user-asserted-pick-ownership.md`** — see §6.3 |
| **W3 M-B** | `docs/api-reference.md` §Draft room (`:311`) — the ESPN branch, the three states, and `notice.code = picks_not_assigned` added to the enumerated code list · `docs/cross-client-invariants.md` — a note that `notice.code` is an **open** set with a client message fallback, while `state`/`kind`/`order_confidence` are closed |
| **W3 M-C** | 4-touch for `picks.assign_tradeable` · `docs/cross-client-invariants.md` §Owned-pick `pool_value` (`:300`) — asserted rows price identically and provenance is server-authoritative · `docs/api-reference.md` §League — `picks_supported` is now a data test, not a platform test · `docs/data-dictionary.md` — the `source` column's engine visibility |
| **W3 M-D** | 4-touch for `draft.manual_picks` · `docs/data-dictionary.md` — new `## recorded_picks` section incl. the `overall`-never-leaks rule · `docs/api-reference.md` §League — the recording routes and the `{accepted, deduped, rejected}` contract · `docs/runbook.md` — the queue's zero-tolerance integrity rule |

### 6.3 The new ADR (required by the plan)

`docs/adr/adr-010-user-asserted-pick-ownership.md` — **ADR-009 is taken** by the rookie-scope view filter, so the next number is **010**. Header format per `adr-008`; add the index row to `docs/adr/README.md`.

**Title:** *User-asserted pick ownership is league-scoped truth in `draft_picks`.*
**It must record, at minimum:** that it **reverses** the documented `draft_picks.platform` invariant "ESPN never writes rows" (`backend/database.py:737`, `docs/data-dictionary.md:424`) and the prior plan's "the schema must not be able to express ownership"; the rejected alternative (a parallel asserted-pick store) and why (five pieces of shared pricing/labelling machinery, seven read sites); why one row per slot with **no user dimension** is correct under the operator's league-shared model; the conservation bound and the `ROOKIE_MAX_ROUNDS` clamp that makes it hold; contested ⇒ unpriced; the two-flag kill structure; and the residual risk the operator accepted knowingly (a leaguemate can change what FTF recommends to you, including active sweeteners).

### 6.4 Backward compatibility

- Every schema change is **additive and nullable**; no backfill, no rollback rehearsal. Every milestone rolls back by flipping its flag; the data survives.
- Old mobile binaries: `notice.code = picks_not_assigned` renders the server's `message` via the verified fallback (`DraftRoomScreen.tsx:401`). `schema` stays `1`, so `DraftSchemaError` (`mobile/src/api/draft.ts:13`, `:114`) never fires.
- Old binaries never send `via` on the anchor route; the field is optional and absent-by-default.
- `picks_supported` keeps its type and its two emit sites; only its computation changes, and only when `picks.assign` is on.
- **`schema` stays `1` across all three waves.** Nothing in this design changes an existing field's type, nullability, or meaning.

---

## 7. Test Matrix

Run `python3 -m pytest backend/tests` from the repo root. **There is no CI and no `conftest.py`** — this is a human gate. Check the **exit code**, not the last line (`tail -1` hides failures). Baseline on `20c2a54`: **1764 collected**. Each wave states its command and its expected count at exit.
**VFF = verify-failing-first**: the test must be shown red against the pre-change tree before the fix lands.

### W1 — `backend/tests/test_draft_room_actions.py` + Jest/Maestro

| ID | Proves | Criterion |
|---|---|---|
| T-W1-01 | `POST /api/anchor/save` with `via:"draft_room"` returns a **byte-identical response** to the same call without it; the `anchor_answered` row carries `props.via` | D10, §2.1 |
| T-W1-02 | An unrecognised `via` falls back to `"anchors"` and never 400s | §2.1 |
| T-W1-03 **VFF** | **Completeness untouched:** no W1 surface reaches `save_tiers_position`, `apply_tiers` or `apply_tiers_subset`; no `tiers_saved` entry before ⇒ none after; `/api/tiers/status.all_done` unchanged. AST + runtime | D1, INV-11 |
| T-W1-04 | The tiers-`via` whitelist at `backend/server.py:7140-7143` is **byte-unchanged** by this wave | §2.1 |
| T-W1-05 | Every new client event name is in **both** `ALLOWED_CLIENT_EVENTS` and `CLIENT_EVENT_PROPS`, and collides with nothing in `SERVER_FIRED_EVENTS` | §2.2 |
| T-W1-06 (Jest) | Each undrafted row's testID is `draft-room.undrafted-row.<player_id>` and is unique across a 25-row list | D0 |
| T-W1-07 (Jest) | Long-press opens the menu **and** the `accessibilityActions` custom action dispatches the same handler | RB-12 |
| T-W1-08 (Jest) | The anchor sheet's rung set is **object-identical** to `PickAnchorScreen`'s (imported, not copied) | §4.1.4 |
| T-W1-09 (Jest) | A failed `saveAnchor` rolls the optimistic value back and the row's rendered value is unchanged | §4.1.4 |
| T-W1-10 (Maestro) | Long-press → Set my value → rung = **3 gestures**, no navigation away, value visibly updates | D1 |
| T-W1-11 (Maestro) | `draft.rank_inline` off ⇒ long-press does nothing, no menu, no nudge | D10 |

### W2 — `backend/tests/test_mock_draft.py` (the `mock-draft-plan.md` §9 matrix, restated with the amendments)

| ID | Proves |
|---|---|
| T-W2-01 | Flag off ⇒ every mock route 404s `feature_disabled`; no other route's response changes |
| T-W2-02 | Snake vs linear turn order; the ownership map puts the right roster on the clock, incl. back-to-back picks |
| T-W2-03 | Reach cap: with `need_weight=1.0`, `severity=1.0`, jitter zeroed, the needed-position player goes **exactly** ≤ `mock_max_reach_slots` early — and never earlier |
| T-W2-04 | BPA persona: `jets` over 500 seeded draws never deviates >1 slot from consensus at the fitted jitter |
| T-W2-05 | **Determinism:** same `rng_seed` ⇒ byte-identical full CPU draft; different seeds differ statistically |
| T-W2-06 | Need-severity table: the `mock-draft-plan.md` §6.3 examples verbatim (0-viable-RB ⇒ 1.0; 1QB-with-QB ⇒ 0.0; superflex `B(QB)=1`) |
| T-W2-07 | Persona precedence declared > inferred > `not_sure`; inference never yields `championship`/`jets` |
| T-W2-08 | Per-team need decrements after that team's pick (no RB triple-tap) |
| T-W2-09 | `not_your_turn` 409; `player_unavailable` 400 for both drafted-in-mock and already-rostered |
| T-W2-10 | D7 in the mock pool: unvalued rookies present, ranked last, CPU-draftable only after the valued pool exhausts |
| T-W2-11 | Resume from the row ⇒ identical state; abandon ⇒ create allows a fresh mock |
| T-W2-12 | `kind != "rookie"` ⇒ `not_rookie_draft`; class-not-loaded ⇒ typed `200 {empty:true}`; **no draft object at all ⇒ ALLOWED**, `order_source:"randomized"` |
| T-W2-13 | **Zero platform egress after creation** (fixture-seam counters, the `test_m1_01` pattern) |
| T-W2-14 | **CPU basis is consensus:** injecting a wildly divergent user board changes the user's undrafted sort and **nothing** about CPU picks |
| T-W2-15 | **One consensus definition:** the mock's ordering of a fixed pool equals `_undrafted(..., basis="consensus")`'s ordering, element for element |
| T-W2-16 **(the calibration gate)** | Fit on rounds 1–2 ⇒ hold-out rounds 3–4 passes **both** bars (KS not rejected at α=0.05 **and** `|Δ mean|d|| ≤ 1.0`); `mfl-complete` passes both with **no refit**; the artifact exists and states the numbers |
| T-W2-17 | Corpus shape check: `mfl-multi-unit` is excluded as startup-shaped; `mfl-complete`/`mfl-partial` are asserted rookie-shaped before use |
| T-W2-18 (Jest) | The mock screen never polls — **zero** refetches while idle, instrumented not assumed |

### W3 M-A — `backend/tests/test_pick_assignment.py`

| ID | Proves | Criterion |
|---|---|---|
| T-W3-01 | **Golden diff:** with both W3 flags off, all seven read sites plus `/api/league/picks`, `/api/trade/evaluate`, `/api/trade/suggestions`, `/api/rankings`, `/api/league/power-rankings` and `GET /api/draft/board` are byte-identical to the pre-change tree, **with assigned rows present in the DB** | D10, INV-1 |
| T-W3-02 | **AST enumeration** (the `test_m3_07` shape, A-14): every `load_draft_picks` call site is enumerated; exactly the seven sanctioned ones carry `source=`; a new unsanctioned site fails the test | D12 |
| T-W3-03 **VFF** | `replace_draft_picks` with the default never deletes a `source='user'` row; with `preserve_source='user'` never deletes a platform row | INV-2 |
| T-W3-04 | Every assignment route rejects a body carrying `value`/`pool_value`/`pick_value`/`elo` with `400 values_not_accepted` | D13 |
| T-W3-05 | **Property, both modes:** for 200 random grids, every `source='user'` row's stored `pool_value` equals `pick_pool_value(round, years_out, fmt)` and its rendered price equals `priced_pool_value(row, mode=m)` for both `m` | D13, INV-3 |
| T-W3-06 | **Conservation:** `Σ pool_value` over any ownership permutation equals the pristine grid's sum; `rounds > 8` is refused server-side | INV-4, KD-4 |
| T-W3-07 | **Pristine seed:** exactly `rounds × teams × 4` slots, each owned by its original team; re-seed without `reseed` is idempotent and preserves every edit | D14 |
| T-W3-08 | **Orphans:** an owner id absent from `league_members` surfaces as `orphaned:true`, is excluded from pricing, and is **never silently dropped** | D14 |
| T-W3-09 | **CAS:** a stale `if_assigned_at` ⇒ `409` + the current row; two different slots both succeed; an omitted token on an assigned row ⇒ `409` | D16 |
| T-W3-10 | **`pick_id` identity:** all four producers emit identical ids for identical inputs | INV-8 |
| T-W3-11 | Every successful write emits `pick_assignment_changed` with the full prop set; the name is in `SERVER_FIRED_EVENTS` and **not** in `ALLOWED_CLIENT_EVENTS` | D16 |
| T-W3-12 | **O9 pinned behaviorally:** no assignment path changes `leagues.draft_status`/`_confidence`/`_checked_at` | D12, INV-7 |
| T-W3-13 | Membership: a `PUT` from a non-member 403s; a body `user_id` is ignored and the actor is the session user | §5.3 |
| T-W3-14 (Jest) | **P-1:** `connectLeague` after a Sleeper connect preserves every cached non-Sleeper league | P-1 |
| T-W3-15 (Maestro) | Seed → the traded-picks review → per-season confirm; progress is explicit; a save is per-slot | §4.3.8 |

### W3 M-B — extends `backend/tests/test_draft_board.py`

| ID | Proves | Criterion |
|---|---|---|
| T-W3-20 | Flag off ⇒ an ESPN league's board is **byte-identical** to today's `platform_unsupported` payload | D15, D10 |
| T-W3-21 | Flag on, no assignments ⇒ `state:"unavailable"`, `notice.code:"picks_not_assigned"`, `order:[]`, `picks:[]` | D15 |
| T-W3-22 | Flag on, assignments present ⇒ `state:"upcoming"`, `order_confidence:"assigned"`, order from the grid, `picks:[]`, full rookie class undrafted | D15 |
| T-W3-23 | **Zero platform egress** in all three states (fixture-seam counters) | D15, INV-9 |
| T-W3-24 | `state`/`kind`/`order_confidence` gain **no new member**; the payload key set equals `_payload`'s exactly | D10, KD-9 |
| T-W3-25 | The linear/snake toggle changes `pick_no`/`slot` and **never** any `owner_user_id` | §4.4 |
| T-W3-27 | Class-not-loaded inside the ESPN room ⇒ `undrafted_suppressed:true` + `notice.class_not_loaded`, board still renders the order (`_undrafted` returns a **tuple**, `:885-888`) | D15 |
| T-W3-26 | `build_board` is unreachable for `platform == "espn"` (the branch precedes it) | KD-8 |

### W3 M-C — extends `backend/tests/test_owned_picks.py`

| ID | Proves | Criterion |
|---|---|---|
| T-W3-30 | S1 only: `/api/league/picks` + `/api/trade/evaluate` change; the other five are byte-identical | §4.5.5 |
| T-W3-31 | S2 adds power-rankings + outlook seed; S1's diffs are unchanged |  |
| T-W3-32 | S3 adds injection + opponent shares |  |
| T-W3-33 | S4 adds `_roster_eveners`; all seven now price asserted picks |  |
| T-W3-34 **VFF** | **Contested ⇒ unpriced by ROW FILTER.** Assert the naive nulling implementation fails: with `pool_value = NULL`, `_power_picks_by_owner` re-derives a price (`:17241-17244`) and the row is priced anyway | INV-5 |
| T-W3-35 | `_owned_picks_available` preserves all three conjuncts: demo leagues and `trade.picks_in_pool` off both still return `False` | I-4 |
| T-W3-36 | `picks_supported` is `false` for ESPN with no assignments and `true` with them; flag off ⇒ always `false` for ESPN | I-5 |
| T-W3-37 | Provenance: `source` appears on every payload that prices an asserted pick, on **all five** priced surfaces, each with the correction deep link | D17 |
| T-W3-38 | `_owned_pick_label` is byte-unchanged (asserted picks do not relabel anyone's picks) | §4.5.3 |

### W3 M-D — `backend/tests/test_recorded_picks.py`

| ID | Proves | Criterion |
|---|---|---|
| T-W3-40 **VFF** | **Replay changes nothing:** re-POSTing an entire batch yields `deduped == n`, `accepted == 0`, and a byte-identical board | D18, INV-12 |
| T-W3-41 | `UNIQUE(league, season, overall)` absorbs cross-device duplicates; a different `player_id` at the same `overall` is a **correction**, not a duplicate |  |
| T-W3-42 | Undo sets `voided_at`; nothing is DELETEd; the board recomputes; re-recording the same `overall` revives the row | D18 |
| T-W3-43 | **`overall` never reaches `draft_picks`:** AST over every `draft_picks` write path + a runtime assertion after a full 48-pick recording | D18, INV-6 |
| T-W3-44 (Jest) | The offline queue matches `events.ts` field for field: uuid idempotency, backoff ladder + jitter, foreground reset, the `sendBatch` disposition ladder, `{accepted, deduped, rejected}` reconciliation, FIFO trim **with a counter** | I-8 |
| T-W3-45 (Jest) | Any trim drop increments `record_queue_dropped` — **zero tolerance**, a non-zero value fails the release gate | §6.8 |

### Flag mirror (D10, all waves)
`test_seed_ui_test_db.py:105-111` + `test_entitlements.py:88-98` already enforce the mirror. Each wave re-runs them and confirms its flags exist in all four touch points and default `False`.

---

## 8. Open Items & Re-Verify Register

**Re-verify at build time** (each named inline above):
**[RV-1]** The tiers-`via` whitelist at `backend/server.py:7140-7143` still belongs to `/api/tiers/save` and already carries the `rookie_*` members — W1 must not touch it.
**[RV-2]** No "⋯"/overflow-glyph pattern has appeared in `mobile/src/`; if one has, use it rather than inventing a second.
**[RV-3]** All seven `load_draft_picks` call sites — re-locate by **symbol** (`_roster_eveners`, `_user_pick_share`, `_run_trade_job`, `_trade_evaluate_impl`, `get_league_picks`, `_owned_pick_assets`, `_power_picks_by_owner`). An eighth appearing means the AST test's sanctioned set must be re-decided, not silently widened.
**[RV-4]** `replace_draft_picks(` still has exactly three production call sites. A fourth = a new platform writer to re-check against INV-2.
**[RV-5]** `mobile/src/api/sleeper.ts:17` still coerces `platform ?? 'sleeper'`, and the server still stamps `platform` only inside the `draft.room` block (`backend/server.py:12281-12297`). Any predicate reading `platform` off a cached league inherits the `ab5050f` trap.
**[RV-6]** `draft_board_service._payload` (`:1107-1147`) and `_render_unavailable` (`:1164-1191`) still emit the **same key set** — `assigned_board` must match whichever they became.
**[RV-7]** `priced_pool_value`'s mode resolution (`backend/pick_values.py:294-317`) and `trade_service.current_pick_pricing_mode` still exist and still have two modes. A third mode (the operator's flagged "personalized pick pricing" direction) changes D13's two-mode property test into an N-mode one.
**[RV-8]** `analytics_taxonomy`'s import-time asserts (`:216`, `:229-235`) are unchanged — a name collision or a missing props entry is an **import failure**, not a test failure, and will take the whole app down at boot.
**[RV-9]** `mobile/src/api/events.ts`'s constants (`:45-54`) and `sendBatch` disposition ladder (`:283-341`) are unchanged before M-D transcribes them. If `events.ts` has moved on, copy the **new** contract, not this document's snapshot.
**[RV-10]** The `_migrate_db` ALTER executor still wraps each statement in its **own** `engine.begin()` (`backend/database.py:1852-1857`) — Postgres aborts the whole transaction on any error even when Python catches it, so a shared transaction would silently skip every column after the first already-exists.

**Also re-diff before each wave:** `DraftRoomScreen.tsx` (contended by W1 / W2-access / W3 M-B), `LeagueScreen.tsx` (W3 M-A's section vs the Explore grid), `RootNav.tsx` + `utils/deepLinks.ts` (W2 and W3 both add a root-stack route), and `docs/api-reference.md` (all three waves edit it).

**Plan-verified assumptions carried, not re-verified locally:** the operator's ruling that ESPN has no rookie-draft concept (which is why W3 is unconditional and D4 is retired) · the Acquire strip's ≈402pt-vs-≈361pt measurement (`build-placement.md` §1) · the ~99.2% ESPN→Sleeper crosswalk coverage that makes an undrafted list computable for an ESPN league at all.

**Left to the build PRDs, not this document:** the exact copy for every designed state (especially B2's "unconfigured, not an error" framing and the D17 provenance label) · the visual design of the per-season collapse and the "Traded picks" review summary · the tracking-plan addendum text for W1's four client events · S-2's go/no-go on M12 (recommend: no) and S-3's population measurement, neither of which gates any wave.
