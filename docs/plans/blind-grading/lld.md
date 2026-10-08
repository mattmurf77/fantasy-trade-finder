# LLD — Calibration: in-app blind grading (value-core Gate 2)

**Date:** 2026-10-02 · **Status:** spec · Companion: [scope.md](scope.md) · [prd.md](prd.md) · [hld.md](hld.md) · [specs.md](specs.md)

Line numbers refer to `feat/blind-grading` at `9e2fc45b` and drift once other edits land, so anchor on the quoted code, not the number.

The two cross-package contracts are written out verbatim in [specs.md §3](specs.md#3-shared-contracts-verbatim):
- the service skeleton (service ↔ routes);
- the route JSON (routes ↔ mobile).

This document holds the algorithms, the schema and the exact edit points. Users see **Calibration**; code and storage say `grading`.

## Contents

1. [Module map](#1-module-map)
2. [Contracts (pointer)](#2-contracts-pointer)
3. [Schema](#3-schema)
4. [Database helpers](#4-database-helpers)
5. [Bench refactor: `backend/eval/value_core_bench.py`](#5-bench-refactor-backendevalvalue_core_benchpy)
6. [Service: `backend/blind_grading.py`](#6-service-backendblind_gradingpy)
7. [Routes: `backend/server.py`](#7-routes-backendserverpy)
8. [Flags and the overlay](#8-flags-and-the-overlay)
9. [Account deletion and export](#9-account-deletion-and-export)
10. [Mobile](#10-mobile)
11. [Error codes](#11-error-codes)
12. [Logging](#12-logging)

---

## 1. Module map

C = create, E = edit. The package letter is from [specs.md §2](specs.md#2-work-packages).

| File | Pkg | Change |
|---|---|---|
| `backend/blind_grading.py` | P1 | **C.** The service. Imports `backend.database` at module level. Imports `backend.eval.value_core_bench`, `backend.value_core.*` and `backend.trade_service` lazily inside functions. **Never** imports `backend.server` or `backend.tools`. |
| `backend/database.py` | P1 | E. Two `Table`s plus nine helpers |
| `backend/eval/value_core_bench.py` | P1 | E. Extract `read_league_inputs`; fix the pick predicate; add three SELECT columns |
| `backend/accounts.py` | P1 | E. Two names in `_ADDITIONAL_PRIVATE_TABLES` |
| `backend/server.py` | P2 | E. One section: two predicates, the gate, the input helper, six routes |
| `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/*.json` | P2 | E. Add `grading.blind`; set `draft.tab` → false |
| `backend/tests/test_rookie_ranks_editable.py` | P2 | E. The `draft.tab` "ships on" assertion flips to off |
| `mobile/src/api/grading.ts` | P3 | C |
| `mobile/src/components/GradingCard.tsx`, `GradingResults.tsx` | P3 | C |
| `mobile/src/screens/CalibrationScreen.tsx` | P3 | C |
| `mobile/src/navigation/TabNav.tsx`, `mobile/src/api/client.ts` | P3 | E |
| `mobile/tests/check-blind-grading.js`, `package.json`, `tests/README.md`, `src/screens/README.md`, `src/navigation/README.md` | P3 | C / E |
| `docs/*`, `living-memory/HLD.md`, `living-memory/LLD.md` | P4 | E. See the [specs.md §7](specs.md#7-docs-matrix) matrix. |

**No longer edited**, superseded by the operator's 2026-10-02 decision:
- `RootNav.tsx` (no root-stack screen);
- `TestingSection.tsx` (no Settings row);
- `check-settings-testids.js`;
- `deepLinks.ts`.

## 2. Contracts (pointer)

- Service API: [specs.md §3.1](specs.md#31-service-contract-backendblind_gradingpy-skeleton).
- Route JSON: [specs.md §3.2](specs.md#32-route-contract-json).

## 3. Schema

**Placement:** after `receipts_grade_runs_table` (`database.py:2781-2795`), before `_MODEL_CONFIG_DEFAULTS` (`:2798`).

**Migrations:** both tables are new, so `metadata.create_all` (`init_db`, `database.py:4192-4195`) creates them on SQLite and Postgres. **No `migration_cols` entry**: that list (`database.py:3265`) exists only for columns added to existing tables.

**Keys:** no FKs, per house style.

```python
# ═══════════════════════════════════════════════════════════════════════════
# Blind grading ("Calibration" in the app) — value-core Gate 2
# (docs/plans/blind-grading/, flag grading.blind resolved per caller)
# ═══════════════════════════════════════════════════════════════════════════
# Written ONLY by backend/blind_grading.py. Soft references, no FKs.
# arms_json is HIDDEN: nothing serializes it except blind_grading.results()
# (completed sessions, aggregates only) and the X-Cron-Secret admin report.
# user_id is the ACCOUNT id (sess["user_id"]) on BOTH tables — denormalized
# onto cards so account deletion/export cover them via
# accounts._ADDITIONAL_PRIVATE_TABLES.
grading_sessions_table = Table("grading_sessions", metadata,
    Column("session_id",   String,  primary_key=True),  # random 18-digit decimal string
    Column("user_id",      String,  nullable=False),    # account id
    Column("league_id",    String,  nullable=False),
    Column("status",       String,  nullable=False),    # 'open' | 'completed'
    Column("seed",         String,  nullable=False),    # decimal of a 63-bit int (String: PG INTEGER is 32-bit)
    Column("created_at",   String,  nullable=False),    # ISO UTC
    Column("completed_at", String),                     # ISO UTC; NULL while open
    Column("counts_json",  Text,    nullable=False),    # hidden per-arm counts (§6.5)
    Column("source_json",  Text,    nullable=False),    # hidden provenance (§6.5)
    Index("ix_grading_sessions_user_league", "user_id", "league_id", "status"),
)

grading_cards_table = Table("grading_cards", metadata,
    Column("card_id",    String,  primary_key=True),    # random 18-digit decimal string
    Column("session_id", String,  nullable=False),
    Column("user_id",    String,  nullable=False),      # = the session's user_id
    Column("position",   Integer, nullable=False),      # 1-based, shuffled order
    Column("arms_json",  Text,    nullable=False),      # HIDDEN {arm: provenance} (§6.5)
    Column("trade_json", Text,    nullable=False),      # neutral payload, served verbatim (§6.4)
    Column("grade",      Integer),                      # 1..5; NULL = unanswered or skipped
    Column("skipped",    Integer, nullable=False, server_default="0"),
    Column("tags_json",  Text,    nullable=False, server_default="[]"),
    Column("graded_at",  String),                       # ISO UTC of the latest answer
    UniqueConstraint("session_id", "position", name="uq_grading_card_position"),
    Index("ix_grading_cards_session", "session_id"),
)
```

**Invariants:**
- `grade IS NOT NULL` ⇒ `skipped = 0`.
- `skipped = 1` ⇒ `grade IS NULL` and `tags_json = '[]'`.
- A session is `completed` ⇔ every one of its cards is answered (`grade IS NOT NULL OR skipped = 1`).
- A session with zero cards is never created.

## 4. Database helpers

**Placement:** a `# ── Blind grading helpers` section at the end of `database.py` (after `load_league_scoring_map`, `:15184-15210`).

**Errors:** all helpers use `engine` and **propagate exceptions**. A swallowed read would masquerade as `needs_fresh_deck`.

```python
def load_grading_legacy_deck(user_id: str, league_id: str
                             ) -> tuple[str | None, str | None, list[dict]]:
    """(deck_job_id, served_at, rows) of the caller's newest deck job that has at least one
    QUALIFYING row; (None, None, []) when none. Qualifying (hld §3.1):
    COALESCE(is_ghost,0)=0, model_arm IS NOT NULL, model_arm <> 'value_core',
    source_like_impression_id IS NULL, trade_intent IS NULL, assets_json IS NOT NULL.
    Job = argmax MAX(served_at) over qualifying rows grouped by deck_job_id.
    rows = that job's qualifying rows ORDER BY card_index, each
    {impression_id, card_index, model_arm, assets_json, features_json} (JSON left as stored)."""

def insert_grading_session(session: dict, cards: list[dict]) -> None:
    """One engine.begin(): insert the session row, then every card row."""

def load_open_grading_session(user_id: str, league_id: str) -> dict | None:
    """Newest status='open' session for (user_id, league_id) by created_at."""

def load_grading_session(session_id: str, user_id: str) -> dict | None:
    """The session row only when it belongs to user_id; else None."""

def grading_progress(session_id: str) -> dict:
    """{"answered": count(grade IS NOT NULL OR skipped=1), "total": count(*)}."""

def load_next_grading_card(session_id: str) -> dict | None:
    """Lowest-position card with grade IS NULL AND skipped = 0, or None.
    Returns {card_id, position, trade_json} — never arms_json."""

def load_grading_cards(session_id: str) -> list[dict]:
    """Every card of the session ORDER BY position, all columns (results/report only)."""

def answer_grading_card(card_id: str, user_id: str, *, grade: int | None, skipped: bool,
                        tags_json: str, now: str) -> dict | None:
    """One engine.begin():
      1. SELECT cards.session_id, sessions.status FROM cards JOIN sessions
         ON cards.session_id = sessions.session_id
         WHERE cards.card_id = :card_id AND cards.user_id = :user_id AND sessions.user_id = :user_id
         → no row ⇒ return None (unknown or foreign card).
      2. status != 'open' ⇒ return {"session_id", "status", "rejected": True, "answered", "total"}.
      3. UPDATE the card: grade, skipped (0/1), tags_json, graded_at = now.
      4. remaining = count(grade IS NULL AND skipped = 0); total = count(*).
      5. remaining == 0 ⇒ UPDATE sessions SET status='completed', completed_at=now
         WHERE session_id = :sid AND status = 'open'.
    Returns {"session_id", "status": "open"|"completed", "rejected": False,
             "answered": total - remaining, "total": total}."""

def load_grading_report_rows(since: str | None, include_open: bool
                             ) -> tuple[list[dict], list[dict]]:
    """(sessions, cards). Sessions: status = 'completed' (any status when include_open),
    created_at >= since when given, ORDER BY created_at. Cards: every card of those sessions
    (session_id IN (...), chunked by 500 like load_league_scoring_map)."""
```

**SQLAlchemy notes:**
- **Joins** need an explicit onclause, because there are no FKs.
- **Ordering:** `func.max(t.c.served_at).desc()` orders the grouped query. ISO UTC strings sort in time order.
- **Imports:** `and_`, `func` and `update` are already imported (`database.py:28-31`).

## 5. Bench refactor: `backend/eval/value_core_bench.py`

**Goal:** a minimal change that gives server-path code the bench's DB read and snapshot builder, with **no** prod tooling and no network.

**Why it can be small:**
- The module imports nothing heavy at module level (`value_core_bench.py:20-40`).
- Only `freeze` imports `backend.tools.prod_analytics`, and it does so lazily, inside the function (`:285`).

So the refactor is one extraction plus one predicate fix.

### 5.1 New public function

Placed immediately before `_freeze_league` (`:229`):

```python
def read_league_inputs(conn, league_id: str, today: date) -> dict:
    """The DB half of a freeze: dialect-neutral reads on ANY SQLAlchemy connection — the app's
    own engine or the read-only prod one. No network, no prod tooling, no writes.
    Returns league_record's keyword arguments minus meta/state:
    {"league_row", "members", "picks", "rankings", "players", "consensus_elo", "declared"}.
    Raises ValueError when the league has no `leagues` row or no `league_members` rows."""
```

The body is `_freeze_league` `:230-270`, moved verbatim, with exactly three edits:

| Line | Was | Becomes | Why |
|---|---|---|---|
| `:245-247` (picks) | `… FROM draft_picks WHERE league_id = :lid AND source = 'platform' ORDER BY pick_id` | `SELECT pick_id, season, round, owner_user_id, pick_value, pool_value, is_traded, original_username FROM draft_picks WHERE league_id = :lid AND (source IS NULL OR source = 'platform') ORDER BY pick_id` | **Bug fix.** Platform rows have `source` NULL: `sync_draft_picks` never sets it, and `_pick_source_predicate` reads NULL as platform (`database.py:11074-11085`). The two new columns feed the neutral pick label (§6.2). |
| `:258` (players) | `SELECT player_id, full_name, position, age, search_rank FROM players …` | `SELECT player_id, full_name, position, team, age, search_rank FROM players …` | `nfl_team` for display. `league_record` ignores the extra key. |
| end | `return league_record(…)` after the Sleeper fetch | `return {"league_row": league_row, "members": members, "picks": picks, "rankings": rankings, "players": players, "consensus_elo": consensus, "declared": declared}` | Hand back the inputs, with no fetch |

### 5.2 `_freeze_league` after the change

`_freeze_league` (`:229-278`) becomes:

```python
def _freeze_league(conn, league_id: str, today: date, fetch_json) -> dict:
    inputs = read_league_inputs(conn, league_id, today)
    meta = state = None
    if (inputs["league_row"].get("platform") or "sleeper") == "sleeper":
        from backend.outlook.league_state import SleeperLeagueState
        meta = fetch_json(SLEEPER_LEAGUE_URL.format(league_id))
        state = SleeperLeagueState(fetch=fetch_json).load(league_id)
    return league_record(**inputs, meta=meta, state=state)
```

**Unchanged:** `league_record` (`:109-220`) and `snapshot_for_seat` (`:385-440`).

**Existing freeze test still passes** (`test_value_core_bench.py:383-477`): the `_ReadOnlyConn` wrapper sees the same `conn.execute(text(sql), params)` calls, `pk1` ('platform') is still in, and `pk2` ('user') is still out. P1 adds a NULL-source pick to that fixture and asserts it is frozen ([specs.md §5.1](specs.md#51-p1--backend-service--schema)).

## 6. Service: `backend/blind_grading.py`

### 6.1 Constants and ids

```python
VERSION = "blind-grading-1"
ARMS = ("current", "value_core")
TAGS = ("overpay", "they_wont_accept", "junk_filler", "too_small",
        "wrong_for_my_window", "wrong_for_their_window", "same_guy_again")
PER_ARM = 20
MIN_PER_ARM = 10
MAX_DECK_AGE_DAYS = 7
TARGET_MEAN = 4.0

def new_id() -> str:
    """Random 18-digit decimal string: str(secrets.randbelow(9 * 10**17) + 10**17).
    Decimal on purpose: the client's api_request_failed route normaliser folds digit runs
    to ':id' (client.ts:365), so a failed grading call never puts a random id into analytics."""
```

**Seed:** `secrets.randbits(63)`, stored as `str(seed)`. Used only by `random.Random(seed)`, and never returned.

### 6.2 Catalog

```python
@dataclass(frozen=True)
class Catalog:
    assets: Mapping[str, Mapping[str, object]]  # id -> {"name","position","nfl_team","age","value"}
    partner_names: Mapping[str, str]            # league user id -> display name
    holdings: Mapping[str, frozenset[str]]      # league user id -> held asset ids

def build_catalog(inputs: Mapping) -> Catalog:
```

`inputs` is the output of `read_league_inputs`.

- **Players.** For each id in any member's `roster_data` that has a `players` row:

  ```
  {name: full_name or id,
   position,
   nfl_team: team or None,
   age: int(age) if age is not None else None,
   value: round(elo_to_value(consensus_elo[id])) if id in consensus_elo else None}
  ```

  `trade_service.elo_to_value` is the same transform `league_record` uses (`value_core_bench.py:172`).
- **Picks.** Every platform pick row, uncapped:

  ```
  {name: pick_label(row),
   position: "PICK",
   nfl_team: None,
   age: None,
   value: round(pool_value) if pool_value else None}
  ```

  - `pick_label(row)` = `f"{season} {ordinal(round)}"`, plus `f" (from {original_username})"` when both `is_traded` and `original_username` are truthy.
  - `ordinal` gives 1st / 2nd / 3rd / Nth, as `value_core_bench._pick_name` does (`:104-106`).
  - This is a slot-free mirror of the server-bound `server._owned_pick_label`.
- **`partner_names`:** `{str(m["user_id"]): m.get("display_name") or m.get("username") or str(m["user_id"])}`.
- **`holdings`:** `roster_data` ids (all positions) ∪ the member's owned platform pick ids.

### 6.3 Arm sourcing

```python
@dataclass(frozen=True)
class ArmCard:
    arm: str                          # "current" | "value_core"
    partner_id: str                   # league identity (league_members.user_id)
    give: tuple[str, ...]
    receive: tuple[str, ...]
    provenance: Mapping[str, object]  # hidden; becomes arms_json[arm]

    @property
    def key(self) -> tuple[str, frozenset[str], frozenset[str]]:
        return (self.partner_id, frozenset(self.give), frozenset(self.receive))
```

#### Current arm: `select_current_cards`

```python
def select_current_cards(job_id: str | None, served_at: str | None, rows: Sequence[Mapping], *,
                         viewer_id: str, catalog: Catalog, now: datetime
                         ) -> tuple[list[ArmCard], dict]:
```

1. **No job.** `job_id is None` ⇒ `raise GradingError("needs_fresh_deck", 409, reason="missing", usable=0, min_cards=MIN_PER_ARM, max_age_days=MAX_DECK_AGE_DAYS)`.
2. **Too old.** `now - datetime.fromisoformat(served_at) > timedelta(days=MAX_DECK_AGE_DAYS)` ⇒ the same error, with `reason="stale"`.
3. **Parse.** For `features_json` and `assets_json`: `json.loads(x) if isinstance(x, str) else (x or {})`. Structured features may already be dicts (`server.py:5375`).
4. **Standing offers.** Drop rows with `features.get("standing_offer") is True`.
5. **Candidates.** `candidates = rows[:PER_ARM]`. Rows arrive already in `card_index` order.
6. **Per candidate:**
   - Read `give = tuple(str(i) for i in assets["give"])`, `receive = …`, and `partner = str(features.get("partner_user_id") or "")`.
   - **Unknown** (counted in `dropped_unknown`): any id not in `catalog.assets`.
   - **Stale** (counted in `dropped_stale`): give or receive is empty; `partner not in catalog.partner_names`; `partner == viewer_id`; `not set(give) <= catalog.holdings.get(viewer_id, ∅)`; or `not set(receive) <= catalog.holdings.get(partner, ∅)`.
   - **Duplicate key within the arm:** skip; the first one wins.
   - **Otherwise** emit `ArmCard("current", partner, give, receive, {"impression_id": r["impression_id"], "card_index": r["card_index"], "model_arm": r["model_arm"]})`.
7. **Too few.** `len(cards) < MIN_PER_ARM` ⇒ `GradingError("needs_fresh_deck", 409, reason="too_few", usable=len(cards), …)`.
8. **Meta.** `meta = {"deck_job_id", "served_at", "candidates", "dropped_stale", "dropped_unknown"}`.

#### Value-core arm: `run_value_core`

```python
def run_value_core(inputs: Mapping, *, seat: str, server: ServerInputs,
                   engine: Callable | None = None) -> tuple[list[ArmCard], dict]:
```

1. **Imports (lazy).** `from backend.eval import value_core_bench as bench`; `from backend.value_core import pipeline`; `from backend.value_core.types import CoreConfig, RankConfig, Request, ENGINE_VERSION`.
2. **Record.** `record = bench.league_record(**inputs, meta=None, state=None)`.
3. **Server overrides:**

   ```
   if server.lineup_slots: record["lineup_slots"] = list(server.lineup_slots)
   record["max_players"] = server.max_players
   record["standings"] = {uid: {"wins": s.wins, "losses": s.losses, "ties": s.ties,
                                "points_for": s.points_for} for uid, s in server.standings.items()}
   record["completed_weeks"] = int(server.completed_weeks)
   ```
4. **Snapshot.** `snapshot, board = bench.snapshot_for_seat(record, seat, standings_weight=bench.DEFAULT_STANDINGS_WEIGHT)`.
5. **Request:**

   ```
   request = Request(viewer_team_id=seat, board=board,
       untouchable_ids=frozenset(i for i in server.untouchable_ids if i in snapshot.assets),
       not_interested_ids=frozenset(i for i in server.not_interested_ids if i in snapshot.assets))
   ```
6. **Run.** `core_cfg, rank_cfg = CoreConfig(), RankConfig()` (D8), then `result = (engine or pipeline.run)(snapshot, request, core_cfg, rank_cfg)`.
7. **Cards.** For `e in result.entries[:PER_ARM]`, with `t = e.scored.trade`:
   - drop it if any id is not in the catalog (counted);
   - otherwise emit `ArmCard("value_core", t.partner_team_id, tuple(t.give), tuple(t.receive), {"deck_position": e.position, "reasons": list(e.reasons)})`.
8. **Failure.** Steps 2–7 run inside `try`. Any exception ⇒ `log.exception("blind-grading: value core failed league=%s", …)`, then `raise GradingError("value_core_failed", 503)`.
9. **Too few.** `len(cards) < MIN_PER_ARM` ⇒ `GradingError("value_core_too_few", 409, usable=len(cards), min_cards=MIN_PER_ARM)`.
10. **Meta:**

    ```
    {"engine_version": ENGINE_VERSION,
     "core": dataclasses.asdict(core_cfg), "rank": dataclasses.asdict(rank_cfg),
     "standings_weight": bench.DEFAULT_STANDINGS_WEIGHT,
     "completed_weeks": …, "lineup_slots": …, "max_players": …,
     "pool": len(result.entries), "elapsed_ms": result.elapsed_ms,
     "budget_exhausted": result.core.budget_exhausted}
    ```

### 6.4 The neutral formatter

```python
def neutral_trade(partner_id: str, give: Sequence[str], receive: Sequence[str],
                  catalog: Catalog) -> dict:
    """THE ONLY producer of trade_json. Receives no arm, no provenance, no engine object.
    {"partner_name": catalog.partner_names[partner_id],
     "give":    [asset(i) for i in sorted_side(give)],
     "receive": [asset(i) for i in sorted_side(receive)]}
    asset(i) = {"id": i, **{k: catalog.assets[i][k] for k in
                ("name", "position", "nfl_team", "age", "value")}}
    sorted_side = sorted(ids, key=lambda i: (-(catalog.assets[i]["value"] or 0),
                                             catalog.assets[i]["name"], i))"""
```

**Convention** (P4 records it in `living-memory/LLD.md`):
- every grading payload passes through `neutral_trade`;
- a field added to it must be computable from `(partner_id, give, receive, catalog)` alone.

### 6.5 Merge, shuffle, persist (`create_session`)

```python
def create_session(*, user_id: str, league_user_id: str, league_id: str, server: ServerInputs,
                   now: datetime | None = None, seed: int | None = None,
                   engine: Callable | None = None) -> dict:
```

1. **Clock.** `now = now or datetime.now(timezone.utc)`.
2. **Resume.** `existing = db.load_open_grading_session(user_id, league_id)`. If found, return `{"session": session_view(existing), "resumed": True}`.
3. **Legacy deck.** `job_id, served_at, rows = db.load_grading_legacy_deck(user_id, league_id)`.
4. **League inputs.** `with db.engine.connect() as conn: inputs = bench.read_league_inputs(conn, league_id, now.date())`. A `ValueError` ⇒ `GradingError("league_not_synced", 409)`.
5. **Seat.** `seat = str(league_user_id)`. If it is not among `{str(m["user_id"]) for m in inputs["members"]}` ⇒ `GradingError("league_not_synced", 409)`.
6. **Catalog.** `catalog = build_catalog(inputs)`.
7. **Current arm.** `current, cur_meta = select_current_cards(job_id, served_at, rows, viewer_id=seat, catalog=catalog, now=now)`. This runs first because it is cheap.
8. **Value-core arm.** `vc, vc_meta = run_value_core(inputs, seat=seat, server=server, engine=engine)`.
9. **Merge:**

   ```
   merged = {}
   for c in [*current, *vc]:
       m = merged.setdefault(c.key, {"partner_id": c.partner_id, "give": c.give,
                                     "receive": c.receive, "arms": {}})
       m["arms"].setdefault(c.arm, dict(c.provenance))
   ```
10. **Shuffle.** `seed = secrets.randbits(63) if seed is None else seed`; `order = list(merged.values())`; `random.Random(seed).shuffle(order)`.
11. **Rows.**
    - Session id: `session_id = new_id()`.
    - Card rows, for `pos, m in enumerate(order, 1)`:

      ```
      {"card_id": new_id(), "session_id": session_id, "user_id": user_id, "position": pos,
       "arms_json": json.dumps(m["arms"], sort_keys=True),
       "trade_json": json.dumps(neutral_trade(m["partner_id"], m["give"], m["receive"], catalog), sort_keys=True),
       "grade": None, "skipped": 0, "tags_json": "[]", "graded_at": None}
      ```
    - Counts:

      ```
      {"total": len(order), "current": len(current), "value_core": len(vc),
       "shared": sum(1 for m in order if len(m["arms"]) > 1),
       "current_candidates": …, "current_dropped_stale": …,
       "current_dropped_unknown": …, "value_core_pool": vc_meta["pool"]}
      ```
    - Source:

      ```
      {"version": VERSION, "seat": seat,
       "scoring_format": inputs["league_row"].get("default_scoring") or "1qb_ppr",
       "current": {"deck_job_id", "served_at"}, "value_core": vc_meta}
      ```
    - Session row: `{session_id, user_id, league_id, "status": "open", "seed": str(seed), "created_at": now.isoformat(), "completed_at": None, "counts_json": json.dumps(counts, sort_keys=True), "source_json": json.dumps(source, sort_keys=True)}`.
12. **Persist.** `db.insert_grading_session(session_row, card_rows)`, then return `{"session": session_view(session_row), "resumed": False}`.

### 6.6 Answer validation

```python
def validate_answer(body: object) -> tuple[int | None, bool, list[str]]:
    """(grade, skipped, tags). GradingError("invalid_body", 400, message=...) when:
      body is not a dict; both or neither of "grade" / "skip" present (skip counts only when it
      is exactly True); grade not an int, a bool, or outside 1..5; "tags" present and not a list
      of str, or any tag not in TAGS; skip with a non-empty tags list.
    Tags are de-duplicated and returned in TAGS order. Unknown body keys are ignored."""

def answer_card(*, user_id: str, card_id: str, body: object, now: datetime | None = None) -> dict:
    """validate_answer → db.answer_grading_card(...). None ⇒ GradingError("not_found", 404);
    rejected ⇒ GradingError("session_completed", 409).
    Returns {"card_id", "session_id", "session_status", "progress": {"answered", "total"}}."""
```

### 6.7 Views, results and report

```python
def session_view(row: Mapping) -> dict:
    """{"session_id", "league_id", "status", "created_at", "completed_at",
        "progress": db.grading_progress(row["session_id"])}"""

def current_session(*, user_id: str, league_id: str) -> dict:
    """{"session": session_view(open row) | None}"""

def next_card(*, user_id: str, session_id: str) -> dict:
    """Foreign/unknown ⇒ GradingError("not_found", 404). Open session with an unanswered card ⇒
      {"done": False, "session_id", "progress", "card": {"card_id", "position",
                                                          "trade": json.loads(trade_json)}}
    otherwise {"done": True, "session_id", "progress"}."""

def summarize(graded: Sequence[tuple[int, Sequence[str]]]) -> dict:
    """{"n", "mean", "share_ge_4", "tag_counts"} — the arithmetic of blind_grade._score
    (blind_grade.py:99-105): mean and share rounded to 4 dp, None when n == 0,
    tag_counts a key-sorted dict."""

def arm_summaries(cards: Sequence[Mapping]) -> tuple[dict, int]:
    """({arm: {"cards", "skipped", **summarize(graded)}} for arm in ARMS, shared_count).
    A card credits every arm key in its arms_json; graded = (grade, tags) for cards with a grade."""

def results(*, user_id: str, session_id: str) -> dict:
    """Foreign/unknown ⇒ not_found 404; status 'open' ⇒ GradingError("session_incomplete", 409,
    progress=...). Else {"session_id", "league_id", "completed_at", "total", "shared",
    "target_mean": TARGET_MEAN, "arms": arm_summaries(cards)[0]}."""

def report(*, since: str | None = None, include_open: bool = False) -> dict:
    """since must parse with date.fromisoformat (YYYY-MM-DD) else GradingError("invalid_since", 400).
    sessions, cards = db.load_grading_report_rows(since, include_open). Per session:
      {"session_id", "user_id", "league_id", "status", "created_at", "completed_at",
       "counts": json.loads(counts_json), "source": json.loads(source_json),
       "arms": arm_summaries(session cards)[0], "delta_mean": delta(arms)}
    overall over all selected cards: {"sessions", "graders", "cards", "shared", "arms", "delta_mean"};
    by_grader grouped by session user_id: {"user_id", "sessions", "arms", "delta_mean"}.
    delta(arms) = round(vc.mean - current.mean, 4) when both are non-None, else None.
    Returns {"generated_at", "version": VERSION, "target_mean": TARGET_MEAN,
             "filters": {"since", "include_open"}, "overall", "by_grader", "sessions"}."""
```

## 7. Routes: `backend/server.py`

**Placement.** One new section, between the end of `delete_test_user_route` (`server.py:26931`) and the `# ─── Account auth` banner (`:26934`). This puts it next to the other tester surface, after `_load_tester_allowlist` is imported (`:26789`).

**Existing names it uses:**

| Name | Where |
|---|---|
| `functools`, `is_enabled`, `FLAGS` | imports (`:265`) |
| `_get_session` | `:2491` |
| `_require_session` | `:2545` |
| `_require_initialized_session` | `:2570` |
| `_league_user_id` | `:2594` |
| `_gate_unverified_write` | `:2663` |
| `_gate_unverified_read` | `:2699` |
| `_value_core_standings` | `:7462` |
| `_league_lineup_slots` | `:28686` |
| `_sleeper_roster_limit` | `:29899` |
| `load_asset_preferences` | used at `:7861` |
| `_require_cron_auth` | `:24339` |

```python
# ─── Calibration / blind grading (docs/plans/blind-grading/) ───────────────
# Tester-only value-core Gate 2: grade value-core vs current-engine cards
# without knowing which made them. All logic is in backend/blind_grading.py;
# these routes gate, gather the league facts only the server has, and map
# GradingError. They never touch trade_service, impressions or swipes.

from . import blind_grading as _blind_grading


def _calibration_allowed(sess) -> bool:
    """THE Calibration audience predicate (operator 2026-10-02: testers only).
    Session user id OR league user id on the tester allowlist — the
    _value_core_live rule (:7456-7458). Opening Calibration to everyone is
    `return True` here (plus grading.blind on for them; prd.md FR-2)."""
    allow = _load_tester_allowlist()
    league_uid = sess.get("league_user_id")
    return (str(sess.get("user_id") or "") in allow
            or (league_uid is not None and str(league_uid) in allow))


def _grading_flag_for_caller(sess) -> bool:
    """grading.blind as THIS caller's app resolves it: the global map, overlaid
    by running-experiment client_config.flags for the caller's device unit
    (X-Device-Id, sent by mobile/src/api/grading.ts) and account unit — the
    per-unit resolution /api/feature-flags performs (:26252-26290) and the
    merge mobile/src/api/flags.ts:52-66 applies. Fail closed: any resolution
    error reads as False."""
    if is_enabled("grading.blind"):
        return True
    try:
        from . import experiments as _exp
        device_id = (request.headers.get("X-Device-Id") or "").strip()
        units = [f"device:{device_id}" if device_id else None,
                 str(sess.get("user_id") or "") or None]
        for unit in units:
            if not unit:
                continue
            _, configs = _exp.resolve_for_unit(unit, None)
            if any(((cfg or {}).get("flags") or {}).get("grading.blind") is True
                   for cfg in configs.values()):
                return True
    except Exception:
        return False
    return False


def _grading_gate(fn):
    """OUTERMOST decorator (directly under @app.route): 404 before the verified
    gates or any session work unless the caller resolves grading.blind true
    AND passes _calibration_allowed — no existence signal (the
    _test_users_denied posture, :26792-26809)."""
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        sess = _get_session(request.headers.get("X-Session-Token", ""))
        if (sess is None or not _grading_flag_for_caller(sess)
                or not _calibration_allowed(sess)):
            return jsonify({"error": "not_found"}), 404
        return fn(*args, **kwargs)
    return _wrapper


def _grading_error(err):
    return jsonify({"error": err.code, **err.detail}), err.status


def _grading_server_inputs(sess, league_id: str):
    """League facts mirroring _run_value_core_job (:7495-7505); every source fail-soft."""
    g_league = sess.get("league")
    platform = getattr(g_league, "platform", None)
    standings, completed_weeks = _value_core_standings(league_id, platform)
    try:
        slots = _league_lineup_slots(league_id)
    except Exception:
        slots = None
    try:
        max_players = (_sleeper_roster_limit(league_id)
                       if (platform or "sleeper") == "sleeper" else None)
    except Exception:
        max_players = None
    untouchable, not_interested = set(), set()
    if FLAGS.trade_preference_lists:
        try:
            ap = load_asset_preferences(user_id=sess["user_id"], league_id=league_id)
            untouchable = set(ap.get("untouchables", []))
            not_interested = set(ap.get("not_interested", []))
        except Exception as err:
            log.warning("blind-grading: asset prefs load failed: %s", err)
    return _blind_grading.ServerInputs(
        lineup_slots=tuple(slots) if slots else None, max_players=max_players,
        standings=standings, completed_weeks=int(completed_weeks or 0),
        untouchable_ids=frozenset(map(str, untouchable)),
        not_interested_ids=frozenset(map(str, not_interested)))


@app.route("/api/grading/sessions", methods=["POST"])
@_grading_gate
@_gate_unverified_write
def grading_create_session_route():
    sess = _require_initialized_session()
    body = request.get_json(silent=True)
    league_id = str(body.get("league_id") or "").strip() if isinstance(body, dict) else ""
    if not league_id:
        return jsonify({"error": "invalid_body", "message": "league_id is required"}), 400
    g_league = sess.get("league")
    if g_league is None or str(g_league.league_id) != league_id:
        return jsonify({"error": "league_not_active"}), 400
    user_id = str(sess["user_id"])
    try:
        current = _blind_grading.current_session(user_id=user_id, league_id=league_id)
        if current["session"] is not None:                    # resume: no network
            return jsonify({"session": current["session"], "resumed": True}), 200
        out = _blind_grading.create_session(
            user_id=user_id, league_user_id=_league_user_id(sess), league_id=league_id,
            server=_grading_server_inputs(sess, league_id))
    except _blind_grading.GradingError as err:
        return _grading_error(err)
    log.info("blind-grading: session %s league=%s resumed=%s", out["session"]["session_id"],
             league_id, out["resumed"])
    return jsonify(out), (200 if out["resumed"] else 201)


@app.route("/api/grading/sessions/current")
@_grading_gate
@_gate_unverified_read
def grading_current_session_route():
    sess = _require_session()
    league_id = (request.args.get("league_id") or "").strip()
    if not league_id:
        return jsonify({"error": "invalid_body", "message": "league_id is required"}), 400
    return jsonify(_blind_grading.current_session(user_id=str(sess["user_id"]),
                                                  league_id=league_id))


@app.route("/api/grading/sessions/<session_id>/next")
@_grading_gate
@_gate_unverified_read
def grading_next_card_route(session_id: str):
    sess = _require_session()
    try:
        return jsonify(_blind_grading.next_card(user_id=str(sess["user_id"]),
                                                session_id=session_id))
    except _blind_grading.GradingError as err:
        return _grading_error(err)


@app.route("/api/grading/cards/<card_id>", methods=["POST"])
@_grading_gate
@_gate_unverified_write
def grading_answer_card_route(card_id: str):
    sess = _require_session()
    try:
        return jsonify(_blind_grading.answer_card(user_id=str(sess["user_id"]), card_id=card_id,
                                                  body=request.get_json(silent=True)))
    except _blind_grading.GradingError as err:
        return _grading_error(err)


@app.route("/api/grading/sessions/<session_id>/results")
@_grading_gate
@_gate_unverified_read
def grading_results_route(session_id: str):
    sess = _require_session()
    try:
        return jsonify(_blind_grading.results(user_id=str(sess["user_id"]),
                                              session_id=session_id))
    except _blind_grading.GradingError as err:
        return _grading_error(err)


@app.route("/api/admin/grading/report")
def admin_grading_report_route():
    """Cron-secret only and deliberately NOT flag- or audience-gated (prd.md D4):
    results stay readable after calibration_rollout is stopped."""
    _require_cron_auth()
    try:
        return jsonify(_blind_grading.report(
            since=(request.args.get("since") or None),
            include_open=request.args.get("include_open") == "1"))
    except _blind_grading.GradingError as err:
        return _grading_error(err)
```

**Decorator order is load-bearing.** Flask registers the outermost wrapper, so `_grading_gate` runs before `_gate_unverified_*`. A non-tester or overlay-less caller with an unverified session therefore gets 404, not 403. `test_gate_404_precedes_verification_403` pins this.

**`_calibration_allowed` and `_grading_flag_for_caller` are the only two places that decide the audience.** Tests monkeypatch them by name.

## 8. Flags and the overlay

### 8.1 Flag files

| File | Edit |
|---|---|
| `backend/feature_flags.py` | After `"trade.value_core",` (`:1172`), add `"grading.blind",` with the comment `# docs/plans/blind-grading/ — Calibration tab + /api/grading/*; ships false, reaches testers only via the calibration_rollout overlay`. `DEFAULT_FLAGS` derives from `FLAG_KEYS` (`:1175`). The attribute is `FLAGS.grading_blind` (`_key_to_attr`, `:1178`). |
| `config/features.json` | After `"trade.value_core": false,` (`:268`), insert `"_comment_grading_blind": "<text below>",` and `"grading.blind": false,`. At `:230`, set `"draft.tab": false`, and append to `_comment_draft_tab` (`:229`): ` 2026-10-02 OFF (operator): the Calibration tab (grading.blind, testers only) takes the third slot and the Draft tab leaves the bar for everyone. Code kept; flip back on next draft season. The Draft Room stays reachable via League > Rookie draft (draft.room) and the Acquire Draft chip.` |
| `backend/tests/fixtures/flags/release.json` | Mirror both changes. It is an exact mirror (`test_seed_ui_test_db.py:107-113`): `grading.blind` lines after `:236`, `draft.tab` → false at `:203`, and the same `_comment_*` texts. |
| `…/profiles-on.json`, `…/onboarding-v2.json` | `grading.blind` lines after `:230`; `draft.tab` → false at `:200` |
| `…/release-300.json`, `…/release-espn-send-off.json` | `draft.tab` → false only (`:173` / `:159`). They carry no `trade.value_core`, so they get no `grading.blind`. |
| `…/all-on.json` | **No change.** It carries neither key. |
| `backend/tests/fixtures/profiles/draft.json`, `draft-pre.json` | **No change.** They keep `"draft.tab": true` (`:22`); they are draft-room QA worlds. |
| `backend/tests/test_rookie_ranks_editable.py` | Rename `test_draft_tab_flag_is_mirrored_and_ships_on` (`:248-257`) to `…_mirrored_and_ships_off`. The docstring records the 2026-10-02 operator decision. The final assert becomes `assert features["draft.tab"] is False`. Leave the rest of the file alone, including `:260-275` (the TabNav predicate is unchanged). |

`_comment_grading_blind` text:

> 2026-10-02 Calibration = in-app blind grading, value-core Gate 2 (docs/plans/blind-grading/). SHIPS FALSE and stays false here: it reaches testers only through the calibration_rollout experiment overlay (targeting is_tester_allowlist). The mobile Calibration tab is decided once at launch from the merged flag map and takes the Draft tab's slot. Server: /api/grading/* answer only when grading.blind resolves true for the caller (global OR overlay, server._grading_flag_for_caller) AND server._calibration_allowed (tester allowlist); otherwise 404. GET /api/admin/grading/report (X-Cron-Secret) is not gated. Kill = stop calibration_rollout. Requires deck.signal_v2 + suggestion.telemetry + trade.bakeoff for the current-engine arm.

### 8.2 The `calibration_rollout` overlay

This is an operator action, not code. It is modelled on [`../ram-mascot/experiment.md` §3-§4](../ram-mascot/experiment.md).

| Field | Value | Why |
|---|---|---|
| key / version | `calibration_rollout` v1 | — |
| layer | a layer with free buckets. Check `GET /api/admin/experiments` first; `onboarding` and `growth` are full. | In-layer bucket exclusivity (D3) |
| unit_type | **`account`** | The server resolves it from `sess["user_id"]` alone. Mobile also sends `X-Device-Id`, so a device unit would also resolve. |
| buckets | `[0, 10000)` | Targeting narrows; bucketing must never drop a tester |
| targeting | `{"is_tester_allowlist": true}` | **Only** this attribute. `_grading_flag_for_caller` passes no header attrs, so targeting on platform or app_version would resolve differently on the server than in `/api/feature-flags`. |
| variants | `control` 0 bp; `treatment` 10000 bp with `client_config: {"flags": {"grading.blind": true}}` | A 0-weight control makes treatment certain |
| primary_metric / exposure_surface | `activation_rate` (required, carried and not claimed) / `calibration_tab` | Required fields |
| launch | `/transition` → `running` with `override_underpowered: true`, reason "allowlist rollout for Gate 2 grading, not a powered test" | — |
| kill | `/transition` → `stopped` | 404 within 60 s; the tab disappears at the next launch |

**Verification:**
- `GET /api/feature-flags` with a tester's session shows `configs.calibration_rollout.flags["grading.blind"] === true`.
- With a non-tester's session, the key is absent.

## 9. Account deletion and export

Append `"grading_sessions", "grading_cards",` to `_ADDITIONAL_PRIVATE_TABLES` (`backend/accounts.py:652-658`). Both tables have `user_id`, so the existing machinery covers them:
- `_del` deletes them (loop at `:780-781`);
- `_EXPORT_TABLES` exports them (`:988-992`);
- `test_account_deletion_coverage.py:48-55` parametrises over them.

The comment at `:616-619` already covers "newer private tables", so it needs no prose change.

## 10. Mobile

### 10.1 API module — `mobile/src/api/grading.ts`

The exact text is in [specs.md §3.2](specs.md#32-route-contract-json). Rules:
- **Plain module:** no React, no state (`api/CLAUDE.md`).
- **Transport:** uses `api` from `./client`.
- **Path params:** pass through `encodeURIComponent`.
- **Device id:** every call attaches `X-Device-Id` from `getDeviceId()`, best effort, exactly as `api/flags.ts:35-40` does. The server can then resolve a device-unit overlay.

### 10.2 Navigation and component tree

```
TabNav  (presence decided ONCE at mount)
  Rank · Acquire(Trades) · [ Calibration  |  Draft  |  — ] · Matches · League
                                  │
  <Tab.Screen name="Calibration" component={CalibrationStackNav}
     options={{ tabBarIcon: tabIcon('check'), tabBarLabel: 'Calibration',
                tabBarAccessibilityLabel: 'Calibration', tabBarButtonTestID: 'tab.calibration' }}
     listeners: tabPress → trackTab('calibration', navigation); focused re-tap → popNestedToTop />
  └─ CalibrationStackNav  (createNativeStackNavigator, screenOptions headerShown:false)
     └─ CalibrationStack.Screen name="CalibrationHome" component={CalibrationScreen}
                                options={chalklineHeader('Calibration')}
        └─ CalibrationScreen                (screens/CalibrationScreen.tsx) — NO FeedbackFAB
           ├─ SafeAreaView edges={['bottom']} → ScrollView
           │  ├─ loading     → ActivityIndicator (ice)                          testID calibration.loading
           │  ├─ no-league   → Text body "Pick a league first."                 testID calibration.no-league
           │  ├─ unavailable → Text heading + body                              testID calibration.unavailable
           │  ├─ needs-deck  → Text body + Button primary "Open Acquire"        testID calibration.open-acquire
           │  ├─ error       → Text body + Button secondary "Try again"         testID calibration.retry
           │  ├─ intro       → TickLabel "Calibration" + Text body (two sentences)
           │  │                + Button primary "Start"                         testID calibration.start
           │  │                | Button primary "Resume (k of N answered)"   testID calibration.resume
           │  ├─ grading     → progress row: Text data "{position} / {total}"   testID calibration.progress
           │  │                + Meter (answered/total)
           │  │                View testID calibration.card → GradingCard trade={card.trade}
           │  │                Text title "Would you send this?"
           │  │                5 × Pressable  testID calibration.grade-{1..5}    (static literals)
           │  │                Text bodySm anchors "1 · No way" … "5 · Send it"
           │  │                7 × Pressable  testID calibration.tag.<tag>       (static literals)
           │  │                Button primary "Next" (disabled until a grade)   testID calibration.submit
           │  │                Button ghost "Skip"                              testID calibration.skip
           │  └─ results     → View testID calibration.results → GradingResults results={…}
           │                   Button primary "Done" (→ intro)                  testID calibration.done
           └─ Toast (answer failures)
```

**Static testIDs:** two const tables of literal strings, mapped over, and no template literals:

```ts
const GRADE_BUTTONS = [
  { grade: 1, testID: 'calibration.grade-1' }, { grade: 2, testID: 'calibration.grade-2' },
  { grade: 3, testID: 'calibration.grade-3' }, { grade: 4, testID: 'calibration.grade-4' },
  { grade: 5, testID: 'calibration.grade-5' },
] as const;
const TAG_CHIPS = [
  { tag: 'overpay',                testID: 'calibration.tag.overpay' },
  { tag: 'they_wont_accept',       testID: 'calibration.tag.they_wont_accept' },
  { tag: 'junk_filler',            testID: 'calibration.tag.junk_filler' },
  { tag: 'too_small',              testID: 'calibration.tag.too_small' },
  { tag: 'wrong_for_my_window',    testID: 'calibration.tag.wrong_for_my_window' },
  { tag: 'wrong_for_their_window', testID: 'calibration.tag.wrong_for_their_window' },
  { tag: 'same_guy_again',         testID: 'calibration.tag.same_guy_again' },
] as const;   // labels come from GRADING_TAG_LABELS in api/grading.ts
```

**Visual spec** (Chalkline, `docs/design/design-system.md` + `components.md`):

| Element | Spec |
|---|---|
| Grade buttons | Five equal-width Pressables, `minHeight: 44`, radius `radii.sm`, numeral in `type.dataLg`. Unselected: transparent fill, 1px `ink.lineStrong` border, `chalk.base` numeral. Selected: `ink.ink3` fill, 1px `ice.base` border, `ice.base` numeral (ice = selection). `accessibilityLabel` "Grade N of 5", `accessibilityState={{selected}}`. |
| Tag chips | Badges & chips construction: radius `radii.xs`, `type.label`, 1px border, `minHeight: 32`, `hitSlop={6}` for an effective 44pt target. Unselected: `ink.lineStrong` border. Selected: `ice.base` border and text. |
| Buttons | Next = `Button variant="primary"`; Skip = `Button variant="ghost"` |
| Banned | No flare (nothing here is an informational highlight), no emoji, no gradients, no radius above 8 |

### 10.3 Screen state (`CalibrationScreen`)

**Data:** TanStack Query. The `['grading', …]` keys are not in `PERSIST_KEYS` (`App.tsx:61`), so nothing is persisted.

| Hook | Key | Enabled | Notes |
|---|---|---|---|
| `currentQ = useQuery` | `['grading','current',leagueId]` | `!!leagueId && leagueId !== NO_LEAGUE_ID` | `retry: false`, `staleTime: 0`, `refetchOnMount: 'always'` |
| `startM = useMutation(() => startGradingSession(leagueId))` | — | — | onSuccess: `setSessionId(r.session.session_id)` |
| `nextQ = useQuery` | `['grading','next',sessionId]` | `!!sessionId && !completedId` | `retry: false`. `data.done` ⇒ `setCompletedId(sessionId)` (in an effect). |
| `answerM = useMutation((a) => answerGradingCard(cardId, a))` | — | — | onSuccess: clear the selection; then `r.session_status === 'completed'` ⇒ `setCompletedId(r.session_id)`, else `qc.invalidateQueries({queryKey: ['grading','next',sessionId]})`. onError: `session_completed` ⇒ `setCompletedId(sessionId)`; otherwise Toast "Couldn't save that grade. Try again." and keep the selection. |
| `resultsQ = useQuery` | `['grading','results',completedId]` | `!!completedId` | `retry: false` |

**Local state:**
- `sessionId: string | null`;
- `completedId: string | null`;
- `grade: 1|2|3|4|5|null`;
- `tags: GradingTag[]`.

Reset `grade` and `tags` whenever `nextQ.data?.card?.card_id` changes.

**Behaviour:**
- **Resume:** `setSessionId(currentQ.data.session.session_id)`.
- **Done:** clear `sessionId` and `completedId`, then `qc.invalidateQueries({queryKey: ['grading','current',leagueId]})`. This returns to intro, which offers Start.
- **League switch:** an effect on `leagueId` clears `sessionId` and `completedId`, because a session belongs to one league.
- **Tab switch:** the component stays mounted (tab screens persist), so state survives.

**Phase** (derived in render, first match wins):
1. no league ⇒ `no-league`
2. any query or mutation error that is an `ApiError` with status 404 ⇒ `unavailable`
3. `startM.error` with status 409 and `body.error === 'needs_fresh_deck'` ⇒ `needs-deck`
4. `startM.error`, any other ⇒ `error` (copy by code, §10.6)
5. `completedId` set ⇒ `results` (`loading` while `resultsQ` is pending)
6. `sessionId` set ⇒ `grading` (`loading` while `nextQ` is pending)
7. `currentQ` or `startM` pending ⇒ `loading`
8. otherwise ⇒ `intro`

**Open Acquire:** `navigation.getParent()?.navigate('Trades')`. The Acquire tab's route name is `Trades` (`TabNav.tsx:803`). `getParent()` of a tab-stack screen is the Tab navigator.

### 10.4 `GradingCard` — `mobile/src/components/GradingCard.tsx`

```ts
import type { GradingTrade } from '../api/grading';
export default function GradingCard({ trade }: { trade: GradingTrade }): JSX.Element
```

**Imports allowed:** `react`, `react-native`, `../theme/chalkline`, `./chalkline` (`Card`, `Text`, `TickLabel`, `Badge`, `PositionBadge`), and the type-only `../api/grading`.

**Layout:**
- **Container:** Chalkline `Card` (`--ink-1`, hairline, radius 8, padding `lg`).
- **Header:** `Text variant="label"` "TRADE WITH", then `Text variant="title"` `trade.partner_name`.
- **Columns:** two, GIVE-LEFT / GET-RIGHT, as in `check-dna-side-order`. Each is headed by a `TickLabel`, "You give" / "You get".
- **Asset row:**
  - name in the `title-compact` composition (`[type.title, {fontSize: type.bodySm.fontSize, lineHeight: type.bodySm.lineHeight}]`, `numberOfLines={2}`);
  - a meta row: `PositionBadge` for QB/RB/WR/TE, or `<Badge label="PICK" />` for a pick, plus `Text variant="data"` `${nfl_team ?? 'FA'}` with `· ${age}` when `age != null` (picks show neither);
  - the value as `Text variant="data"` `value ?? '—'`.
- **Column footer:** `Text variant="label"` "TOTAL", then `Text variant="data"` with the sum of non-null values.
- **Never:** a meter, reasons, lanes, a narrative, the likes-you pill, Send, colours beyond the position badges, emoji or gradients.

### 10.5 `GradingResults` — `mobile/src/components/GradingResults.tsx`

```ts
import type { GradingResults as Results } from '../api/grading';
export default function GradingResults({ results }: { results: Results }): JSX.Element
```

**The ONLY component that names an arm:** `const ARM_LABEL = { current: "Today's engine", value_core: 'New engine' } as const`.

**One Chalkline `Card` per arm**, in `['current','value_core']` order:
- **Header:** a `TickLabel` with the arm's label.
- **Rows** (label: `Text bodySm` in `chalk.dim`; value: `Text data`):

  | Label | Value |
  |---|---|
  | Cards | `cards` |
  | Graded | `n` |
  | Skipped | `skipped` |
  | Average | `mean?.toFixed(2) ?? '—'` |
  | Would send (4–5) | `share_ge_4 == null ? '—' : Math.round(share_ge_4 * 100) + '%'` |
- **"Top reasons":** the three highest `tag_counts`, written like "Overpay ×4", using `GRADING_TAG_LABELS`.

**Footer:** `Text bodySm` in `chalk.dim`: "{shared} trades were suggested by both engines and count for both."

### 10.6 Copy

| Where | Text |
|---|---|
| intro | "Grade up to 40 trade ideas for {league_name}, one at a time. Some come from today's trade engine and some from the new one, shuffled — you won't know which is which." |
| needs-deck | "Open Acquire for this league first so there's a fresh deck to compare against, then come back." |
| unavailable | heading "Not available" · body "Calibration isn't turned on for this account." |
| `value_core_too_few` | "The new engine found too few trades for this league right now. Try another league." |
| `league_not_synced` / `league_not_active` | "This league isn't loaded yet. Reopen it from the league picker and try again." |
| other errors | "Something went wrong starting the session. Try again." |
| prompt / anchors | "Would you send this?" · "1 · No way" … "5 · Send it" |

### 10.7 Edits in existing files

**`mobile/src/navigation/TabNav.tsx`:**

| Where | Edit |
|---|---|
| after `:67` (`import DraftRoomScreen …`) | `import CalibrationScreen from '../screens/CalibrationScreen';` |
| after `DraftStackNav` (ends `:639`) | Add the block below |
| after `showDraftTab` (`:716-718`) | Add the `showCalibrationTab` block below |
| `:844-865` (the `{showDraftTab ? (<Tab.Screen name="Draft" …/>) : null}` block) | Replace it with the slot block below. The Draft `<Tab.Screen …/>` element is moved **verbatim** into the else-branch, and its options, listeners and testID are unchanged. |

The stack, after `DraftStackNav`:

```tsx
// ── Calibration (docs/plans/blind-grading/) ──────────────────────────────
// Tester-only blind grading of today's engine vs the value core (Gate 2).
// Occupies the Draft tab's third slot (operator 2026-10-02). A TAB-stack
// screen: it mounts NO FeedbackFAB — RootNav's global mount covers it (the
// #196/#197 double-FAB rule; see DraftStackNav's inTabs note above).
const CalibrationStack = createNativeStackNavigator();

function CalibrationStackNav() {
  return (
    <CalibrationStack.Navigator screenOptions={{ headerShown: false }}>
      <CalibrationStack.Screen
        name="CalibrationHome"
        component={CalibrationScreen}
        options={chalklineHeader('Calibration')}
      />
    </CalibrationStack.Navigator>
  );
}
```

The presence flag, after `showDraftTab`:

```tsx
// Calibration tab — presence decided ONCE at mount, exactly like
// showDraftTab: read IMPERATIVELY so a mid-session flag revalidation cannot
// insert or remove a tab. grading.blind ships false and reaches testers
// only through the calibration_rollout overlay (merged into this map by
// api/flags.ts). When present it takes the third slot AHEAD of Draft.
const [showCalibrationTab] = useState(
  () => !!useFeatureFlags.getState().flags['grading.blind'],
);
```

The slot, replacing `:844-865`:

```tsx
{/* Third slot: Calibration (testers) takes it ahead of the seasonal Draft
    tab, so the bar never exceeds five tabs. */}
{showCalibrationTab ? (
  <Tab.Screen
    name="Calibration"
    component={CalibrationStackNav}
    options={{
      tabBarIcon: tabIcon('check'),
      tabBarLabel: 'Calibration',
      tabBarAccessibilityLabel: 'Calibration',
      tabBarButtonTestID: 'tab.calibration',
    }}
    listeners={({ navigation, route }) => ({
      tabPress: () => {
        trackTab('calibration', navigation);
        if (retapOn && navigation.isFocused()) {
          popNestedToTop(navigation, route);
        }
      },
    })}
  />
) : showDraftTab ? (
  /* the existing Draft <Tab.Screen …/>, verbatim */
) : null}
```

**Other mobile edits:**

| File | Where | Edit |
|---|---|---|
| `mobile/src/api/client.ts` | `:249` | `const SLOW_POST_PATHS = ['/api/session/init', '/api/trades/generate', '/api/grading/sessions'];` with a comment pointing to `docs/plans/blind-grading/hld.md §7` |
| `mobile/package.json` | between `:15` and `:16` | `"test:blind-grading": "node tests/check-blind-grading.js",` |
| `mobile/tests/README.md` | `:3`, and the table after `:32` | Count 87 → 88. New row: `\| Calibration \| check-blind-grading (Gate 2: neutral card, arm names only in results, no own FAB, mount-once tab in the Draft slot, static ids) \|` |
| `mobile/src/screens/README.md` | after the Draft-tab row (or `:23`) | `\| Calibration tab \| CalibrationHome \| CalibrationScreen.tsx \|` |
| `mobile/src/navigation/README.md` | `:34` tree | A line before or after `Draft`: `├─ Calibration (Stack) CalibrationHome — renders only when grading.blind resolves true at mount; takes the third slot ahead of Draft` |

**Not edited:**
- `RootNav.tsx`: the tab screen is covered by the global FAB, and there is no root-stack route.
- `SettingsHubScreen.tsx`, `TestingSection.tsx`.
- `deepLinks.ts`: tab screens resolve through `Main`, and Calibration is never linked externally.
- `testRouteEntry.ts:97` (`TAB_NAMES`, dormant UI-test harness).
- `shared/types.ts`: the wire types live in `api/grading.ts`, as in `api/teamReview.ts`.
- `mobile/src/navigation/CLAUDE.md` and `mobile/src/screens/CLAUDE.md` map rows are lead-only ([specs.md §8](specs.md#8-lead-only-items)).

### 10.8 Structural guard — `mobile/tests/check-blind-grading.js`

**Setup:** dependency-free node, using `typescript` for the AST, resolved as `check-settings-nav.js:42-48` does.

**Forbidden-token regexes**, run on comment-stripped source:

```
CARD_FORBIDDEN   = /\b(reasons?|arms?|model_arm|value_core|valueCore|engine|basis|lane|narrative|composite|fairness|mismatch|match_context|valuation|impression|trade_id|tradeId|preserve_server_order|likes_you|score)\b/i
SCREEN_FORBIDDEN = CARD_FORBIDDEN without `engine` and `score`
```

`SCREEN_FORBIDDEN` drops two tokens because the intro copy legitimately says "today's trade engine … the new one". Neither word identifies a card's arm.

| # | Assertion |
|---|---|
| 0 | **Self-test.** The scanner hits on the planted `'const x = card.reasons;'` and stays clean on `'const x = card.trade;'`. |
| 1 | **`src/components/GradingCard.tsx`:** no `CARD_FORBIDDEN` token. Import specifiers ⊆ {`react`, `react-native`, `../theme/chalkline`, `./chalkline`, `../api/grading`}. |
| 2 | **`src/api/grading.ts` interface keys:** `GradingAsset` = {id, name, position, nfl_team, age, value}; `GradingTrade` = {partner_name, give, receive}; `GradingCard` = {card_id, position, trade}. Each `GradingNext` union member has no key matching `/arm\|reason\|engine\|basis\|lane\|score/`. The file references `X-Device-Id` and `getDeviceId`. |
| 3 | **`src/screens/CalibrationScreen.tsx`:** no `SCREEN_FORBIDDEN` token. `<GradingResults` occurs exactly once. No import of `TradeCard`, `api/trades` or `shared/types`. **No `<FeedbackFAB` and no `FeedbackFAB` import.** |
| 4 | **Arm names stay in one place.** Walking `src/`: the literal `value_core` appears only in `api/grading.ts` and `components/GradingResults.tsx`, and `Today's engine` / `New engine` appear only in `components/GradingResults.tsx`. |
| 5 | **testIDs.** Every `testID=` in the three new files is a string literal or a `.testID` member of the two const tables. Every `'calibration.…'` literal is in the required set ([scope.md §3](scope.md#3-evidence-scope)), and every required id is present. |
| 6 | **`TabNav.tsx`:** `const [showCalibrationTab] = useState(` with `useFeatureFlags.getState().flags['grading.blind']`. No `useFlag('grading.blind')`. A `<Tab.Screen name="Calibration"` whose options contain `'tab.calibration'` and whose listeners contain `trackTab('calibration'`. The source order is `showCalibrationTab ?` … `name="Calibration"` … `: showDraftTab ?` … `name="Draft"`. `tabBarButtonTestID: 'tab.draft'` is still present. |
| 7 | **`client.ts`:** `SLOW_POST_PATHS` contains `'/api/grading/sessions'`. |
| 8 | **`api/grading.ts` routes:** imports `{ api` … `}` from `'./client'`. References `/api/grading/sessions`, `/current`, `/next`, `/api/grading/cards/` and `/results`. Does not reference `/api/admin/`. |
| 9 | **`package.json`:** `scripts["test:blind-grading"] === "node tests/check-blind-grading.js"`. |

**Output** follows the neighbours: PASS/FAIL lines, and a non-zero exit on failure.

**Header:** a WHY THIS EXISTS block and an "HONEST LABEL" note saying it proves code shape, not runtime behavior.

## 11. Error codes

| Status | `error` | Extra keys | Route(s) | When |
|---|---|---|---|---|
| 404 | `not_found` | — | all `/api/grading/*` | No session; `grading.blind` not true for the caller; caller fails `_calibration_allowed`; unknown or foreign session or card |
| 401 | (existing `_SessionExpired` body) | — | all | Token expired between the gate and the handler (a race) |
| 403 | `verification_required` | — | all | Unverified session (existing decorators, after the gate) |
| 409 | `session_not_initialized` | (existing) | create | `/api/session/init` not finished; the client retries |
| 400 | `invalid_body` | `message` | create, current, answer | Missing `league_id`; bad grade, skip or tags |
| 400 | `league_not_active` | — | create | `league_id` ≠ the session's active league |
| 409 | `league_not_synced` | — | create | No `leagues` row or `league_members` rows; caller's seat not a member |
| 409 | `needs_fresh_deck` | `reason` (`missing` \| `stale` \| `too_few`), `usable`, `min_cards`, `max_age_days` | create | §6.3 |
| 409 | `value_core_too_few` | `usable`, `min_cards` | create | Value core gave fewer than 10 usable cards |
| 503 | `value_core_failed` | — | create | The value core raised |
| 409 | `session_completed` | — | answer | Answer after completion |
| 409 | `session_incomplete` | `progress` | results | Results while open |
| 400 | `invalid_since` | — | report | `since` is not `YYYY-MM-DD` |
| 401 / 503 | (Flask abort) | — | report | Bad or missing `X-Cron-Secret`; secret unset in prod (`server.py:24339-24358`) |

## 12. Logging

| Where | Level | What |
|---|---|---|
| Route, after create or resume | `info` | `"blind-grading: session %s league=%s resumed=%s"` |
| Service, after insert | `info` | `"blind-grading: session %s cards=%d shared=%d vc_ms=%d"` |
| `value_core_failed` | `exception` | The failure |
| Preference-list load failure | `warning` | The failure |

Never per-card arms at INFO, and nothing else. Grades are data, not logs.
