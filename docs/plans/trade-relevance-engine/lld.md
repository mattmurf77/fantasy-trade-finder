# LLD: Trade Relevance Engine

> **Purpose:** low-level design for the trade relevance initiative — precise enough
> that an engineer writes the code without guessing. Parent: [hld.md](hld.md)
> (SIGNED OFF; every D-number is binding here). Ground truth for current code:
> [ftf-current-state.md](ftf-current-state.md). Dual-agent authored (Implementer
> lens + Reviewer lens); reconciliation in
> [reconciliation-log.md](reconciliation-log.md). All file:line anchors verified at
> HEAD 2026-08-14.
>
> Status: **SIGNED OFF** — dual-agent converged, 4 rounds, 2026-08-14.
> Amended 2026-08-14 during PRD review (deltas marked ⟨PRD-AMENDED⟩ in place;
> rationale in the reconciliation log's PRD section): §2.3 why-route
> `score_components`; §2.3 vblend `actor`/audit (pending P1 OQ-4); §3.3
> `player_archetypes` + `user_value_profiles` comments; §4.9 standings
> catch-up; §4.11 coverage denominator + season blend; §4.12 writer
> invariant; §6.1 P2 flag order; §7 T-35.

---

## Table of Contents
- [1. Scope & Reference](#1-scope--reference)
- [2. Interfaces / API](#2-interfaces--api)
- [3. Data Structures & Schema](#3-data-structures--schema)
- [4. Core Logic](#4-core-logic)
- [5. Error Handling & Edge Cases](#5-error-handling--edge-cases)
- [6. Backward Compatibility & Migration](#6-backward-compatibility--migration)
- [7. Testing](#7-testing)
- [8. Open Questions](#8-open-questions)

---

## 1. Scope & Reference

Covers P0–P4, organized by **build order** (each step ships alone):

| Step | Item | Depends on |
|---|---|---|
| B1 | Pass ledger (`cron_pass_runs`, registry refactor of daily-tick) — D1 | — |
| B2 | `backend/relevance/` package skeleton: `batch_write`, D10 config resolver — D12, D10 | — |
| B3 | P0-1 taxonomy registration (28 events) | — |
| B4 | P0-6 `decided_by` gate counters (`deck_job_stats`) | — |
| B5 | P0-3 impression threading: swipe→decision→match→disposition — D2 | — |
| B6 | P0-4 flag aggregation + class demotion — D11 | B1, B2 |
| B7 | P0-5 near-dup dedup in `_order_deck` | — |
| B8 | Propensity freeze keys + nightly drift check (HLD §2.3/§5.3) | B1 |
| B9 | P1-1/P1-2 F6 v2 multi-head + vblend — D5, D10 | B2, B5 |
| B10 | D4 promotion machinery (pin, counting, `train.value_model` split) | B1, B9 |
| B11 | P1-3 `surface` column + reader sweep + push eligibility — D6 | B8 |
| B12 | P2 ingest substrate: cursors, budget, capture widening, backfill, standings — D7 | B1, B2 |
| B13 | P2-1/P2-3/P2-5 profile derivations | B12 |
| B14 | P3-1/P3-2 archetypes + value decomposition — D9 | B2 |
| B15 | P4 hooks, `/api/trades/why/<impression_id>`, trading-profile surface | B13, B14 |

Seams this LLD binds to, verified by anchor:

| Seam | Anchor |
|---|---|
| Migration idiom (per-column ALTER, own txn each) | `database.py:1998-2006` |
| `deck_impressions` / `deck_outcomes` DDL | `database.py:481-531` |
| `trade_matches` DDL | `database.py:398-417` |
| `bad_trade_flags` (no impression_id, no trade_hash) | `database.py:917-940` |
| `model_config` (key, **Float value**, description) | `database.py:1019-1023` |
| Engines: product WAL+5000ms; ingest 150ms `BEGIN IMMEDIATE`; ro | `database.py:60-131` |
| `_order_deck` multiplier stack + `capture` out-param | `server.py:3344-3463` |
| F6 seam `_deck_value_scores` | `server.py:3050-3077` |
| Impression logging (uuid4 hex, features freeze) | `server.py:3570-3654` |
| `_save_deck_outcome_safe` (**no ownership validation today**) | `server.py:3657-3689` |
| Swipe route → `check_for_match` → `create_trade_match` | `server.py:10152-10297`, `database.py:6554`, `:6684` |
| Disposition route + `record_match_disposition` | `server.py:13060-13260`, `database.py:7054` |
| Daily tick (inline passes, the D1 target) | `server.py:16494-16673` |
| Replenishment pass + its push | `server.py:16151-16226` |
| `_send_typed_push`; `log_notification_send` | `server.py:15743-15811`; `database.py:10421` |
| F6 v1 (heads, Platt, `models.jsonl`, loader) | `value_model.py` (loader `:646-670`) |
| Eval loader / scorers / replay / nightly | `eval/data.py:94-205`, `scorers.py`, `replay.py:79-146`, `nightly.py:35-60` |
| Sleeper trades sweep (weeks 1–18, Chrome UA) | `sleeper_trades_service.py:40-144`; call site `server.py:15281-15287` |
| Flag registry drops unknown keys | `feature_flags.py:696-715` |
| `experiments.variant_overlay` | `experiments.py:361-377` |
| Taste sync on outcome (trusts impression owner) | `taste_service.py:314-355` |

## 2. Interfaces / API

### 2.1 New package `backend/relevance/` (D12)

```
backend/relevance/
  __init__.py        # nothing heavy at import; ZERO Flask imports anywhere
  registry.py        # pass registry + ledger claims + tick driver
  batch.py           # batch_write + chunk pacing (product engine ONLY)
  config.py          # resolve() — the D10 resolver; valve() for operational valves
  vblend.py          # V-vector read/write/validation (D10)
  promotion.py       # D4 counting state + CLI (--pin/--status/--unpin)
  ingest.py          # cursor machine, budget_take, backfill chain walk (D7)
  dedup.py           # P0-5 metric + pass
  push_eligibility.py
  passes/
    flag_agg.py  market_model.py  opponent_profiles.py  standings.py
    user_activity.py  archetypes.py  value_decomp.py  join_repair.py  drift_check.py
```

Public signatures:

```python
# registry.py
@dataclass(frozen=True)
class PassSpec:
    name: str                        # ledger key; kill valve cron.pass_disabled.<name>
    fn: Callable[[PassContext], dict]  # returns counters; raising ⇒ status 'error'
    budget_s: float                  # per-pass wall budget
    klass: str = "resumable"         # 'resumable' | 'must_complete_today'
    max_same_day_retries: int = 2    # read only for must_complete_today
    push_kinds: tuple[str, ...] = () # every push kind this pass may dispatch.
                                     # Registration asserts each kind is in
                                     # _NOTIF_FREQ_CAPS or the documented
                                     # dedup-key whitelist (HLD §2.1 invariant);
                                     # a T-28 sibling lint forbids
                                     # _send_typed_push calls inside
                                     # relevance/passes/ for undeclared kinds.
    # budget_s semantics: passes run synchronously and are never preempted
    # mid-flight (§4.1); budget_s only (a) marks post-hoc 'timeout' status and
    # (b) feeds the 2×-budget stale-claim rule (§3.3). Do not build preemption.

def run_ledger(now: datetime, *, wall_budget_s: float = 600.0) -> dict:
    """Iterates REGISTRY in order. Per pass: ledger claim (§3.3) → valve check
    (model_config['cron.pass_disabled.<name>'], absent ⇒ runs; direct read,
    resolver-exempt) → global-deadline check between passes (must_complete_today
    exempt) → run under own try/except + budget. Returns {'statuses': {...},
    'counters': {...}} for the tick response."""

# batch.py — the HLD §2.2 discipline
def batch_write(table, rows: list[dict], *, mode: str = "insert_ignore",
                chunk: int = 200, pace_s: float = 0.05,
                upsert_keys: tuple[str, ...] | None = None) -> int:
    """One engine.begin() per chunk on the PRODUCT engine (5000ms busy_timeout);
    NEVER the ingest engine (150ms + BEGIN IMMEDIATE is the analytics fail-fast
    path — wrong tool). Caller contract: no open network socket while calling.
    mode ∈ insert | insert_ignore | upsert. Dialect-portable (ON CONFLICT)."""

# config.py
KNOB_EXPERIMENTS: dict[str, str] = {}   # knob key → experiment key. THE overlay
    # discovery mechanism: variant_overlay(unit_id, exp_key) requires a specific
    # experiment key (the sole precedent hardcodes "trade.aggression",
    # trade_service.py:3189). resolve() consults the overlay ONLY for registered
    # knobs; unregistered knobs skip the overlay tier entirely — merge-all-running-
    # experiments would let any experiment override any relevance knob.
def resolve(key: str, default: float, *, user_id: str | None = None) -> float:
    """D10 precedence: per-user setting > variant_overlay(user_id,
    KNOB_EXPERIMENTS[key]).get(key) when registered > model_config row > code
    default. THE only legal read path for relevance knobs (T-28 enforces)."""
def valve(key: str, default: float = 0.0) -> float:
    """Operational valves ONLY (cron.pass_disabled.*, ingest.daily_budget):
    raw model_config read, no overlay — an experiment can never resurrect a
    killed pass (HLD §2.1). Whitelist enforced by T-28."""

# database.py — P0-3 (D2)
def find_matching_like(...) -> dict | None
    # SAME parameters as check_for_match (database.py:6554); replaces its
    # boolean interior; returns {'decision_id', 'impression_id' | None,
    # 'exact': bool} of the matched like (newest mirror wins: ORDER BY
    # created_at DESC). check_for_match stays as
    # `find_matching_like(...) is not None` for any other caller.
def save_deck_outcome(..., join_quality: str | None = None,
                      source_match_id: int | None = None) -> None
    # widened writer for the §3.2 columns; rejects action ∉ DECK_OUTCOME_ACTIONS
def _save_deck_outcome_safe(impression_id, action, *, acting_user_id: str,
                            join_quality: str | None = None,
                            source_match_id: int | None = None,
                            **engagement) -> str | None
    # server.py:3657 — returns the VALIDATED impression_id (None on rejection)
    # so the swipe route passes the same validated id to save_trade_decision;
    # validation per §4.3. SIX call sites gain acting_user_id (required kwarg —
    # a missed site fails loudly as TypeError, never silently): events
    # side-channel server.py:7146, swipe :10214, flag :10519, and the three
    # propose routes :12694, :22217, :22702.
def save_trade_decision(..., impression_id: str | None = None) -> None   # :4373
def create_trade_match(..., impression_id_a: str | None = None,
                       impression_id_b: str | None = None,
                       join_quality_b: str | None = None) -> dict        # :6684
def record_match_disposition(match_id, user_id, decision,
                             *, write_outcomes: bool = False) -> dict    # :7054
    # result gains: my_impression_id, partner_impression_id,
    # outcome_rows_written (0 on already_decided)

# value_model.py — v2
HEAD_REGISTRY = ("like", "calc_open", "detail_expand", "propose", "flag",
                 "accepted", "declined", "accepted_by_partner", "declined_by_partner")
def train_model_v2(decks, *, now) -> "ValueModelV2 | None"
def load_active_model() -> "ValueModelV1 | ValueModelV2 | None"   # pin-aware (§4.7)

# push_eligibility.py — called at ASSEMBLY sites (D6), never in _send_typed_push
def push_eligible(user_id, league_id, *, top_card_score: float,
                  card_meta: dict) -> tuple[bool, str]            # (verdict, reason)
    # card_meta keys (all read by §4.13 rules): centerpiece_id, archetype,
    # relaxed, basis, partner_user_id. Source: _replenish_deck_for
    # (server.py:16179) extends its return from (deck_size, expired_count) to
    # also carry the top card's final_score + these meta fields.
```

### 2.2 D10 value-blend storage — DECIDED: per-head keyed `model_config` rows

`vblend.<id>.<head>` rows (e.g. `vblend.3.propose` = 6.0) plus pointer row
`vblend.active_id` (Float holding the integer id). Rationale: the V-vector is ~9
floats + a pointer — exactly the shape `model_config` already stores; it inherits
live-write/no-deploy rollback (one UPDATE of the pointer), the admin surface, and
the INSERT-OR-IGNORE seeding idiom, while a dedicated table would add a migration
and a second read path for a few dozen rows. Head names ride the key string, so
the Float-typed `value` column is never asked to hold structure (the HLD D10
constraint).

```python
# vblend.py
NEGATIVE_HEADS = frozenset({"flag", "declined", "declined_by_partner"})
DEFAULT_VBLEND = {"like": 1.0, "calc_open": 0.5, "detail_expand": 0.2,
                  "propose": 6.0, "flag": -50.0, "accepted": 20.0,
                  "declined": -12.0, "accepted_by_partner": 10.0,
                  "declined_by_partner": -6.0}
def active_vblend() -> tuple[int, dict[str, float]]:
    # (id, weights). id 0 = DEFAULT_VBLEND (no rows needed). Missing per-head
    # row ⇒ that head's default. Cached 60s. Pointer at missing rows ⇒ fall
    # back to DEFAULT_VBLEND, log once, stamp vblend_id=null (E16).
def write_vblend(blend_id: int, weights: dict[str, float]) -> None:
    # Validates: heads ∈ HEAD_REGISTRY; |V| ≤ 100; sign matches head class;
    # blend_id strictly greater than any existing. NO weight-space negative-mass
    # rule — a P=1 mass bound would reject DEFAULT_VBLEND itself (Σ|neg| 68 vs
    # 0.8·Σpos 30.2) and every X-style outsized-negative blend D5 prescribes;
    # sparse-negative-head protection is the D5 RUNTIME clamp on realized
    # contributions (§4.7), not a weight bound. Never touches active_id;
    # activation = POST {"activate": <id>} on the §2.3 route, validated to
    # point at a fully-written blend (all HEAD_REGISTRY rows present or
    # intentionally defaulted).
```

### 2.3 New/changed HTTP routes (every row → `docs/api-reference.md`)

| Route | Method | Auth | Change |
|---|---|---|---|
| `/api/cron/daily-tick` | POST | `X-Cron-Secret` | body unchanged; response gains `"passes": {name: status}`; re-POST resumes (skips `ok`) |
| `/api/trades/swipe` | POST | session | no wire change; server-side impression validation (§4.3) + threading |
| `/api/trades/matches/<id>/disposition` | POST | session | no wire change; writes D2 labels atomically (§4.5) |
| `/api/trades/why/<impression_id>` | GET | session | NEW (flag `ui.why_this`). ⟨PRD-AMENDED⟩ 200 → `{impression_id, served_at, score_components: <relative-contribution labels per component ("major"/"minor"), computed server-side — raw propensity/multiplier values never serialized (P4 PRD R7: Thompson internals must not be harvestable)>, features: <whitelisted subset excluding all opp_*, partner valuations, vblend_id/model_record_id>, hooks: [...]}` from the frozen row only. Serializer test asserts the full payload. **Uniform 404** on: absent, `user_id != session user`, or `surface != 'deck'` — one indistinguishable answer (no impression-id oracle). Rate-limited 60/hr/user (in-process fixed-window counter, resets on deploy — acceptable for an oracle-hardening limit; no new dependency). |
| `/api/admin/relevance/vblend` | GET/POST | `X-Cron-Secret` | §2.2 validation (400 names the failing rule); body `{"blend_id", "weights"}` to write, `{"activate": <id>}` to flip the pointer. ⟨PRD-AMENDED, pending P1 OQ-4⟩ body gains a required `actor` string persisted with timestamp+payload in a config-audit row; activation refused without it (P1 PRD R19 governance) |
| `/api/admin/analytics/relevance` | GET | admin-analytics auth | HLD §6 report; ro engine; reads only ledger + counter tables |

### 2.4 Flags & config keys (final names)

`FLAG_KEYS` additions (`feature_flags.py:47`; all default False — registration is
part of each PR's diff since the registry drops unknown keys `:708-714`):
`train.value_model`, `deck.class_demotion`, `deck.dedup`, `push.eligibility_bar`,
`market.transactions_all`, `market.history_backfill`, `market.standings_sync`,
`relevance.profiles`, `data.archetypes`, `ui.personal_hooks`, `ui.why_this`,
`ui.trading_profile`. `deck.value_model` stays the **single serving gate** (v1 vs
v2 = artifact family via the activate pointer, §4.7 — never a second flag).

`MODEL_CONFIG_DEFAULTS` seeds: `ingest.daily_budget` 2000,
`class_demotion_floor` 0.5, `class_demotion_min_views` 200, `dedup_overlap_tau`
0.75, `push_elig_percentile` 75, `push_elig_min_decks` 5,
`push_elig_partner_active_days` 14, `value_decomp_ridge_lambda` 25,
`value_model_min_user_outcomes` 20 (the HLD §5.3 cold-start gate),
`fast_pass_dwell_ms` 2000.
`cron.pass_disabled.*` and `vblend.*` are deliberately **unseeded** (absent ⇒
pass runs / default blend — inverted-polarity fail-safe).

## 3. Data Structures & Schema

### 3.1 SQLite ALTER reality — binding rules

The repo's only migration mechanism: `metadata.create_all()` for new tables + the
per-column `ALTER TABLE ADD COLUMN` list, each statement in its own transaction
(`database.py:1998-2006`). Rules for everything below:

- **Allowed:** nullable ADD COLUMN, or with a **constant** default; new tables
  with any DDL; `CREATE INDEX IF NOT EXISTS` (the `_user_events_env_indexes`
  pattern, `database.py:2064`).
- **Forbidden (SQLite):** ADD COLUMN NOT NULL without default; non-constant
  defaults; adding UNIQUE/CHECK/FK via ALTER; renames/retypes. Anything needing
  those gets a new table.
- **Enum "widening" is app-level:** `deck_outcomes.action` is a bare String with
  no CHECK (`database.py:521`). The four D2 labels are added by (a) one
  authoritative constant `DECK_OUTCOME_ACTIONS` beside the table, (b)
  `save_deck_outcome` rejecting actions outside it (today it accepts any string),
  (c) reader whitelists (§6.2). No DDL for the widening.

### 3.2 Column adds (append to `migration_cols`, `database.py:1877`)

```python
# P0-3 — disposition join spine (D2)
("trade_decisions", "impression_id",   "VARCHAR"),   # NULL = pre-P0-3 / web
("trade_matches",   "impression_id_a", "VARCHAR"),   # triggering swiper; exact when set
("trade_matches",   "impression_id_b", "VARCHAR"),   # recovered; NULL = recovery failed
("trade_matches",   "join_quality_b",  "VARCHAR"),   # 'exact'|'fuzzy'|NULL
("deck_outcomes",   "join_quality",    "VARCHAR"),   # set only on disposition rows
("deck_outcomes",   "source_match_id", "INTEGER"),   # idempotency/attribution key (§4.5)
# P1-3 — surface split (D6)
("deck_impressions","surface",         "TEXT DEFAULT 'deck'"),  # constant default: legal both dialects
("deck_impressions","vblend_id",       "INTEGER"),   # also in features_json; column for SQL audit
# P2-2 — capture widening
("sleeper_trades",  "kind",            "VARCHAR"),   # NULL = 'trade' (all existing rows ARE trades — zero-write backfill)
("sleeper_trades",  "source",          "VARCHAR"),   # NULL = 'live'
```

Repo idiom note: each `migration_cols` entry is paired with the matching
`Column(...)` added to the Table declaration itself (so fresh `create_all()` DBs
match migrated ones — T-25 enforces), and every schema row here gets its
`docs/data-dictionary.md` entry per the docs gate. Readers use the NULL-tolerant
predicate `COALESCE(surface,'deck')='deck'` (belt-and-braces across the
mixed-fleet window). New indexes (idempotent list):
`ix_deck_impressions_surface_served (surface, served_at)`,
`ix_deck_outcomes_action (action, acted_at)`,
`ix_trade_decisions_impression (impression_id)`,
`ix_sleeper_trades_kind (league_id, kind)`.

### 3.3 New tables (all `metadata.create_all()`, all additive)

```python
cron_pass_runs = Table("cron_pass_runs", metadata,
    Column("pass_name",  String, nullable=False),
    Column("run_date",   String, nullable=False),      # UTC "YYYY-MM-DD"
    Column("status",     String, nullable=False),      # running|ok|error|skipped|timeout
    Column("started_at", String, nullable=False),
    Column("duration_ms", Integer), Column("items", Integer),
    Column("error_text", Text),
    Column("attempt",    Integer, nullable=False, default=1),
    UniqueConstraint("pass_name", "run_date", name="uq_pass_run"))
```

`uq_pass_run` is the **double-POST answer**: a pass starts by INSERT-claiming
`status='running'`. IntegrityError ⇒ read the row: `ok` ⇒ skip; `running`
younger than 2× the pass budget ⇒ skip (someone owns it); `running` and older ⇒
stale corpse from a killed worker — UPDATE to `error`, re-claim `attempt+1`.
**Stale-`running` recovery is mandatory** — without it a mid-pass OOM wedges that
pass for the day, the exact silent-skip failure D1 exists to kill. Retention 90d
via the existing retention endpoint — **registering `cron_pass_runs` in that
endpoint's table list is part of the B1 diff**, not an assumption.

```python
deck_class_stats  ((archetype, shape_bucket, value_band, stat_date) unique;
    exposures Int, flags Int, flag_rate_shrunk Float, demotion Float [0.5,1.0],
    computed_at)                    # latest stat_date live; 30d history; older pruned
ingest_cursors    (id autoincrement PK; (league_id, season, kind) unique;
    last_week Int default 0,        # weeks ≤ last_week are DONE; resume at last_week+1
    status default 'pending',       # pending|active|done|done_empty|stuck
    attempts Int default 0, next_eligible_at, claimed_at, updated_at,
    waiver_budget Integer)          # settings.waiver_budget captured at the
                                    # /league/{id} fetch (§4.9.5) — the
                                    # faab_aggression denominator. Lives HERE
                                    # because it is per-(league, season) and
                                    # ancestor leagues have cursor rows but no
                                    # `leagues` row; NULL = no FAAB / not yet
                                    # fetched. Read as MAX(waiver_budget) over
                                    # the (league, season)'s kind rows so a NULL
                                    # standings-kind sibling never shadows it
ingest_budget     (day TEXT PK, calls_used Int default 0)     # §3.4 token bucket
league_lineage    ((league_id, ancestor_league_id) unique; season Int,
    depth Int NOT NULL,             # ≤ 3 (D7 cap)
    discovered_at)
league_market_profiles (league_id PK; trades_per_month Float, shape_histogram JSON,
    positional_flow JSON, price_level JSON, n_trades Int, computed_at)
manager_trade_profiles ((platform, platform_user_id, league_id) unique;
    trade_pace Float, positions_bought JSON, positions_sold JSON,
    consolidation_lean Float, faab_aggression Float, waiver_churn Float,
    age_lean Float, seasons_observed Int, confidence_n Int, computed_at)
    # league-scoped; NEVER cross-league joined; server-internal; deleted on
    # league unlink (hook in the existing unlink path) — HLD §5.2
league_standings  ((league_id, week, roster_id) unique; season Int, wins, losses,
    points_for Float, pf_by_position JSON|NULL, synced_at)   # retention: season+1
user_activity_profiles (user_id PK; calc_sessions_wk Float,
    board_edit_recency_d Float, notif_tap_rate Float, sessions_wk Float,
    swipes_wk Float, computed_at)
player_archetypes ((sleeper_player_id, season) unique; archetype_json Text,
    stat_snapshot Text, archetype_confidence Float, computed_at)
    # ⟨PRD-AMENDED⟩ consumer read = the §4.11 blend rule (serve prior-season
    # row until current games ≥ 6; season_source key inside archetype_json);
    # unmapped ⇒ no row ⇒ neutral
user_value_profiles ((user_id, scoring_format) unique; coefficients JSON,
    declared JSON,                  # user corrections; outrank inferred (D10)
    n_obs Int, fit_r2 Float, confidence 'ok'|'insufficient', computed_at)
    # insufficient ⇒ P4 renders nothing.
    # ⟨PRD-AMENDED⟩ declared semantics: per-key overrides AND null-tombstones
    # (deleted keys persist as {"key": null} across recomputes); WRITER
    # INVARIANT: the nightly value_decomposition pass overwrites coefficients
    # ONLY, never declared — sabotage test lands with B14 (P3), not B15.
    # Full delete = opt-out STUB row (coefficients NULL,
    # confidence='insufficient', declared={"opt_out": true}); nightly pass
    # skips stubs; stub covered by §6.5 cascade/export/T-32.
deck_job_stats    (deck_job_id PK; user_id, league_id, decided_by JSON, created_at)
    # P0-6: one insert per completed job, counters only
```

### 3.4 The token bucket is a table, not a process variable

```sql
INSERT INTO ingest_budget(day, calls_used) VALUES (:day, 0) ON CONFLICT(day) DO NOTHING;
UPDATE ingest_budget SET calls_used = calls_used + :n
  WHERE day = :day AND calls_used + :n <= :budget;      -- rowcount 0 ⇒ denied
```

`:budget` = `valve("ingest.daily_budget", 2000)` read fresh per call (0 = kill
switch, immediate). Restart-proof (E11); two workers cannot double-spend (the
WHERE is the check-and-take). Day boundary UTC; rows >90d pruned by the ingest
pass.

### 3.5 `models.jsonl` v2 records (versioning that cannot crash — or fool — v1)

The v1 loader accepts any record where `rec["model"]` is a dict
(`value_model.py:659-665`); a v2 record reusing that key would deserialize into a
`LogisticHead` with empty weights scoring a constant 0.5 — no crash, worse. So:

```json
{"schema_version": 2, "record_id": "…", "kind": "model", "train_date": "…",
 "feature_set": "fs2",
 "model_v2": {"heads": {…}, "head_meta": {"like": {"n_pos": 812, "active": true}, …},
              "partner_rates": {…}, "global_rates": {…}, "trained_at": "…"}}
{"schema_version": 2, "kind": "activate", "record_id": "…", "recorded_at": "…"}
```

v2 model records carry **no top-level `"model"` key** ⇒ a v1 binary mid-deploy
skips them and keeps serving its last v1 record (E13). `activate` records are the
serving pointer: `load_active_model()` scans in reverse for the newest
`activate`, loads that `record_id`; none ⇒ newest parseable model (v1 semantics
preserved). Serving rollback = append an `activate` pointing at the prior record
— one CLI append, no deploy. Torn-line appends are already skipped by the reader
(`:637`). Eval pinning is separate from activation (§4.7).

### 3.6 `features_json` additions (inside the JSON; all optional; absent ⇒ 0.0)

`feature_set: "fs2"` · frozen applied multipliers `fatigue_mult`, `taste_mult`,
`diversity_mult`, `class_demotion` (HLD §2.3 corollary) · `vblend_id`,
`model_record_id` · `surface` mirror · feature families: `market_pace`,
`market_price_pos`, `opp_trade_pace`, `opp_consolidation_lean`, `opp_age_lean`,
`user_calc_wk`, `user_notif_tap_rate`, `arch_match_recv`, `arch_match_give` ·
`hook_id` (P4). Absent key ⇒ 0.0 in `extract_features` (the F6 v1 no-signal
anchor, `value_model.py:121,172`) — D8 train/serve identity and pre-fs2 replay
compatibility hold by construction (E22).

## 4. Core Logic

### 4.1 B1 — pass-ledger tick loop

`cron_daily_tick` (`server.py:16494`) becomes: auth → `run_ledger(now)` →
jsonify legacy counters + `passes`. REGISTRY order (existing bodies moved
**verbatim** into `PassSpec.fn` closures):

1. `pushes` (lines 16503-16588; `resumable`) — the Aug-25 `season_start` fan-out
   (`:16512`) is **split into its own pass** `season_start`
   (`must_complete_today`, retries ≤2 same-day, then `error` + operator-alert log
   line) so the date-gated work can't be lost to a deadline skip while ordinary
   push scans stay resumable. **The split must not repeal the Aug-25 winback
   suppression**: today the fan-out's `continue` (`:16529`) means a
   `season_start` recipient gets nothing else that day; the `pushes` pass
   therefore retains an `is_aug25` skip (its scan is suppressed on the fan-out
   date; the `season_start` pass owns all sends that day), and T-1's fixture set
   explicitly includes an Aug-25 day.
2. `replenish` (16590-16598) · 3. `eval` (16600-16616) · 4. `refit`
   (16618-16631; gate becomes `train.value_model` — the D4 split) ·
   5. `players_guard` (16633-16652) · 6. `class_load` (16654-16663) · then new:
   `flag_agg`, `join_repair`, `drift_check`, `standings`, `ingest_advance`,
   `market_model`, `opponent_profiles`, `user_activity`, `archetypes`,
   `value_decomp`.

Budgets: pushes/replenish 120s; eval/refit 180s; new passes 60s; `ingest_advance`
240s (it advances the queue's daily budget and runs the §4.9.6/§3.4 retention
pruning — the daemon worker owns the fetch work). Global
deadline checked **between** passes (never preempts mid-flight).
Behavior-preservation requirement: with all valves absent and no new passes, the
tick's side effects and response JSON (minus `passes`) are identical to today —
enforced by T-1. Concurrency: the `uq_pass_run` claim (§3.3) makes overlapping
POSTs safe without a lock; each pass body executes at most once per day.

### 4.2 B4 — gate counters (P0-6)

`trade_service._consider` (`trade_service.py:3444`) gains a `counters: dict`
out-param, incremented by gate name at each early return. `_run_trade_job` writes
one `deck_job_stats` row per completed job. **Counting only — any diff touching a
gate's boolean is rejected in review.** Surfaced in the §2.3 admin report.

### 4.3 B5 — swipe-time validation + threading (D2, first leg)

`_save_deck_outcome_safe` (`server.py:3657`) today writes any ≤64-char string,
and `taste_service.update_taste_from_outcome` (`taste_service.py:314`) then
mutates the **impression owner's** taste vector — a stale/foreign id poisons
another user. Fix (all **six** call sites per §2.1: events side-channel `:7146`, swipe
`:10214`, flag `:10519`, propose routes `:12694`/`:22217`/`:22702`): new
required kwarg `acting_user_id`; one PK read of
the impression; require (a) row exists, (b) `user_id == acting_user_id`, (c)
`served_at ≥ now − 14d`, (d) `COALESCE(surface,'deck')='deck'` for deck-native
actions. Any failure ⇒ no outcome write, no taste write, counter
`outcome_rejected{reason}` (§2.3 report); the route still 200s (label capture is
best-effort by contract `:3665`). A swipe racing a job-cache refresh carries an
older-but-valid impression id, which passes — the spine keys on impression, not
cache generation. Then `save_trade_decision(..., impression_id=validated_id)`.

### 4.4 B5 — match creation (D2, second leg)

`find_matching_like` replaces `check_for_match`'s boolean interior
(`database.py:6554`): same exact-mirror + fuzzy passes, but returns the matched
like row's `id`, `impression_id`, and whether the match was exact. Call site
(`server.py:10286`): `create_trade_match(..., impression_id_a=<validated swipe
id>, impression_id_b=mirror["impression_id"], join_quality_b=('exact' if
mirror["exact"] and mirror["impression_id"] else 'fuzzy' if
mirror["impression_id"] else None))` — side B inherits the match's own fuzziness
(D2); a NULL on the like row (web, pre-P0-3) ⇒ `impression_id_b=NULL`. No
outcome rows at match time (a match is not a disposition).

### 4.5 B5 — disposition (D2, third leg): atomic, idempotent, per-perspective

`record_match_disposition` (`database.py:7054`) already has the state machine
(per-side decision columns; `already_decided` short-circuit `:7110`; conflict ⇒
route 409; same-decision ⇒ idempotent 200, `server.py:13117`). The D2 label
writes go **inside the same `engine.begin()`** (`:7088`) — decision + labels
commit or roll back together:

- On the single `ok` transition with `write_outcomes=True`
  (`_deck_signal_v2_enabled()`): actor's impression (side a or b by caller) gets
  `accepted`/`declined`; counterpart impression gets
  `accepted_by_partner`/`declined_by_partner`. `join_quality` = that side's
  quality (`exact` for side a); `source_match_id = match_id`. NULL impression ⇒
  that side's label simply not written.
- **Idempotency key** `(impression_id, action, source_match_id)`: pre-insert
  SELECT inside the txn (no UNIQUE index — `deck_outcomes` legally duplicates
  rows for other actions, and ALTER can't add partial constraints §3.1). The
  state machine makes re-disposal unreachable; the guard covers replayed
  requests racing the first commit.
- Elo/K semantics untouched (`:7167-7193`); the −12 decline correction and
  30-day suppression (`server.py:13145`) continue to fire from the route.

**Fuzzy repair (broken threads), nightly pass `join_repair`:** for matches
decided in the last 7d with a NULL impression on either side: compute that
side's `trade_hash` via `_deck_trade_hash` (`server.py:3639`) **in that user's
perspective** (side B's give = `user_a_receive`); find `deck_impressions` rows
with that hash, `surface='deck'`, `served_at` within 7d before `matched_at`.
**Unique hit ⇒** write the missing labels `join_quality='fuzzy'`; zero or
multiple ⇒ leave NULL (ambiguity is label poison — D2). Fuzzy rows are
default-excluded from training (§4.8).

### 4.6 B6 — flag aggregation + demotion (D11); B7 — dedup (P0-5)

**Flag aggregation** (`passes/flag_agg.py`, nightly): `bad_trade_flags` has no
join key (`database.py:917`) — attribution rides the impression-keyed
`not_interested` outcome row the flag route already writes (`server.py:10519`).
Exposures = `viewed` outcomes ⋈ impressions (`surface='deck'`, trailing 30d)
grouped by (archetype, shape_bucket, **`receive_value_band`** — chosen over the
give band to match the flagger's receive side; both bands live inside
`features_json` with no SQL column, so the nightly group-by is a Python-side
JSON parse over the window's rows, and the serving cache lookup uses the same
key); flags = `not_interested` in the same group; EB shrinkage `(flags + 50·ρ)/(views + 50)` toward global rate ρ;
`views < class_demotion_min_views (200)` ⇒ demotion 1.0 exactly; else
`clamp(ρ/max(shrunk,1e-9), class_demotion_floor (0.5), 1.0)`. Rows written for
`stat_date=today`; consumers read `MAX(stat_date)`; failed pass ⇒ yesterday's
rows live (fail-soft by data layout).

**Serving** (flag `deck.class_demotion`): in-process cache of the latest stats
(TTL 6h, the `_thompson_prior_cache` pattern `server.py:3172`); missing class ⇒
1.0; **the applied multiplier is frozen into `features_json.class_demotion`**
(HLD §2.3 corollary), clamped at write AND read.

**Dedup** (flag `deck.dedup`), in `_order_deck` **on the base-keyed list before
the Thompson draw** — deterministic given the candidate set (contract clause
(a)), never interacting with the stochastic layer, and **pre-capture** so
dropped cards are never logged (replay reorders only logged cards; drops are
invisible to it by construction). Metric (DECIDED): cards A,B near-dup iff same
`partner_user_id` AND same centerpiece (`_fatigue_centerpiece`) AND
`J(assets_A, assets_B) ≥ dedup_overlap_tau (0.75)`, `assets` = give ∪ receive
player-id sets, J = Jaccard. Greedy keep-highest-base-key; `likes_you` cards
never dropped; stop dropping when `len(kept) < _DECK_MIN_CARDS` (restore
best-dropped — the `_cap_per_target` pattern). O(n²) over ≤40 cards.

### 4.7 B9/B10 — F6 v2 multi-head (D5) + promotion (D4)

**Feature extraction:** `extract_features` (`value_model.py:133-177`) stays the
single canonical function, extended with the fs2 numeric families (`_num`,
0.0-default — absent keys are the no-signal anchor; pre-fs2 replay stays valid).

**Heads:** `{action: LogisticHead}` over `HEAD_REGISTRY` with parent chains
`accepted→propose→like`, `declined→propose→like`, partner labels → their
first-person parent, `calc_open/detail_expand/flag → like`. A head trains only
at **≥300 positives in trailing 90d of matured rows**; below: `active=false`,
scoring walks to the first live parent with the child's V-weight zeroed (D5).
The like head keeps v1's `MIN_LIKE_ROWS` floor — below it no model persists.

**Training** (`train_model_v2`, in the `refit` pass, flag `train.value_model`):
dataset = `load_decks(surface='deck', mature_before=now−14d)` (§4.8); per-head
labels from the reduce; fuzzy-joined disposition labels excluded. Class
imbalance at 1–5% positives: class-weighted loss `w⁺ = clamp(n_neg/n_pos, 1,
20)` (deterministic; no downsampling). **Platt guard:** calibration slice must
have ≥50 rows AND ≥8 positives, else identity `(1,0)`; fitted `platt_a` clamped
[0.25, 4.0], `platt_b` [−4, 4] — an unlucky sparse slice otherwise saturates a
negative head, which × its outsized V-weight is the deck-zeroing failure D5's
clamp exists for. Determinism: rows sorted `(served_at, impression_id)`; no RNG;
same DB ⇒ byte-identical artifact (T-15).

**Scoring** (`rank_score_v2`): `Σ V_a·P(a)` with `propose` composed as
`P(like)·P(propose|like)` (v1 semantics) and disposition heads composed on the
propose chain; negative contribution clamped ≥ −0.8 × positive sum (D5); stamps
`vblend_id` + `model_record_id` into the frozen features (via an
`extra_features` out-param on `_deck_value_scores`, merged in
`_log_deck_signal_impressions`). Any exception ⇒ None ⇒ composite,
byte-identical (v1 contract `value_model.py:735-770`).

**Promotion (D4):** *pinning for eval ≠ activation for serving.*
`data/value_model/promotion.json` holds `{pinned_record_id, criterion: {nights:
21, wins_needed: 15, ci_level: 0.90, ess_min, baseline_scorer: "production"},
counted: [...]}`; `promotion.py` CLI `--pin/--status/--unpin` (refuses re-pin
mid-count). The baseline scorer name is **frozen in the criterion at pin time**
— `"production"` (nightly's existing default baseline, `nightly.py:43`, matching
F8's graduation convention), not the `base_score` scorer; the ambiguity would
otherwise change verdicts.

**Replay-harness deltas (the machinery D4 needs that `backend/eval/` lacks):**

- `replay.py` `METRICS` (today `("like","propose")`, `:85`) gains `flag`
  (reward = `not_interested` outcome), `fast_pass` (a `pass` outcome with
  `dwell_ms < fast_pass_dwell_ms (2000)`), and `accepted` (disposition label,
  **matured-only**: rows pass the §4.8 maturity + non-fuzzy filters before
  entering rewards). `_reward` gains the corresponding cases.
- **Paired lift CI:** `evaluate()` gains a paired cluster-bootstrap over deck
  jobs computing the **candidate − baseline SNIPS difference** per resample,
  with a `ci_level` parameter (D4 demands 90%; today's harness computes only
  per-scorer 95% CIs and `verdict()` compares a CI to a point estimate,
  `replay.py:341` — not a lift CI). `win` iff the lift CI's lower bound > 0.
- **Pinned-artifact loading:** `get_scorer` (`scorers.py:50`) has no parameter
  channel; the eval pass registers a factory when a pin exists —
  `register_factory("value_model_pinned", _pinned_scorer_factory)` — so the
  scorer name, not a new signature, carries the pin. Registration is
  **idempotent** (skip-if-present — `register_factory` raises on duplicates, and
  the pass runs nightly in a long-lived process), and the factory reads
  `promotion.json` **at call time**, never capturing the record id in a closure
  (a re-pin must not serve a stale artifact).

A night is *counted* iff ESS ≥ `ess_min` AND no `untrusted-<date>` drift marker;
`win` additionally requires guardrail metrics (`flag`, `fast_pass`) within their
CIs. `wins ≥ 15` ⇒ log `PROMOTION CRITERION MET` (operator appends `activate` +
flips `deck.value_model` + starts the 50% A/B — human steps by design);
`counted ≥ 21 ∧ wins < 15` ⇒ verdict `killed`, counting stops, bar never lowered.

**Cold-start serving gate (HLD §5.3, easy to lose):** the v2 serving path
replaces the boolean `user_has_outcome_history` (`value_model.py:713`, ≥1 row)
with `COUNT(outcomes ⋈ surface='deck' impressions) ≥
resolve("value_model_min_user_outcomes", 20)` — below it, that user's deck
serves composite even with the flag on. v1 path untouched.

### 4.8 Shared reader rules (training + eval)

`load_decks` (`eval/data.py:94`) gains `surface="deck"` (default predicate
`COALESCE(surface,'deck')='deck'`; push readers opt in explicitly) and
`mature_before` (rows newer than the horizon flagged `immature`, dropped by
trainers and by replay's disposition metrics — D4(d)). The outcome reduce
(`:157-172`) adds the four D2 actions + `calc_opened`/`detail_expanded` booleans
and continues ignoring unknown actions (what makes the widening backward-safe).
`join_quality='fuzzy'` reduces into `*_fuzzy` booleans, excluded unless a
trainer opts in. Same-diff surface sweep (B11): refit builder (via
`load_decks`), F9 `load_deck_serve_history` (`database.py:4700`), Thompson arm
loader (`database.py:~4814`), fatigue events (`database.py:~4930`), D11
exposure query (§4.6 has it), **and `user_has_outcome_history`
(`value_model.py:713`)** — a push impression must not flip a user's cold-start
status.

### 4.9 B12 — ingestion machine (D7)

Unified worker (refactor of the session-init sweep, `server.py:15281` →
`relevance/ingest.py`): one daemon thread per process, started lazily by either
trigger (session_init enqueues that league's cursor; `ingest_advance` enqueues
per backlog), draining:

1. `claim_next_cursor` — **portable two-step claim** (an
   `UPDATE … ORDER BY LIMIT` would be illegal on Postgres and
   compile-flag-dependent on SQLite, breaking §6.4 exactly at the tripwire
   cutover): `SELECT id … WHERE status='pending' AND (next_eligible_at IS NULL
   OR next_eligible_at <= :now) ORDER BY id LIMIT 1`, then
   `UPDATE ingest_cursors SET status='active', claimed_at=:now WHERE id=:id AND
   status='pending'`; rowcount 0 ⇒ lost the race, re-select (loop). Claims older
   than 15min are re-claimable (crash recovery); a re-fetched week is idempotent
   on `transaction_id` (`database.py:372`).
2. Work unit = (league, season, week): `budget_take(1)` — denied ⇒ requeue,
   sleep; fetch **with no DB transaction open**; parse; `batch_write`
   (`insert_ignore`); `last_week = week` (weeks 1..18; resume at `last_week+1` —
   the off-by-one is settled at the schema comment, once).
3. `parse_all_transactions` generalizes `parse_trade_transactions`
   (`sleeper_trades_service.py:80`): `market.transactions_all` on ⇒ also keep
   completed `waiver`/`free_agent`, `kind` stamped; `source='backfill'` for
   backfill cursors. Existing `isinstance` guards (`:77,:91`) preserved;
   non-dict entries skipped, never fatal.
4. HTTP 404 (pre-2021 season, deleted league) = **terminal answer, not
   failure**: `status='done_empty'`, attempts NOT incremented. 429/5xx/timeout ⇒
   `attempts+=1`, `next_eligible_at = now + min(60s·2^attempts, 6h)`; attempts
   ≥5 ⇒ `stuck` (operator report; never auto-retried).
5. Chain walk (P2-3, flag `market.history_backfill`, new-links only until OQ-1):
   read `previous_league_id` from `/league/{id}` (budget-counted), insert
   `league_lineage` + ancestor cursors, visited-set + depth ≤ 3 (cycle/404 end
   the chain cleanly); per ancestor one `/rosters` fetch for the
   `roster_id → owner_id` map the profiles pass consumes. **Every `/league/{id}`
   fetch (live league at cursor creation, and each ancestor) also persists
   `settings.waiver_budget` into that (league, season)'s `ingest_cursors.
   waiver_budget` column (§3.3)** — the `faab_aggression` denominator (§4.10);
   today the only reader of that setting is the live trade-block path
   (`server.py:20544`), which persists nothing.
6. **Raw retention (HLD §3.1/§5.2):** the final step of the **synchronous
   `ingest_advance` pass body** (ledger-budgeted — NOT the daemon worker thread)
   deletes `sleeper_trades` rows with `traded_at` older than the start of
   `current_season − 2` (the 3-season rolling window; backfill-sourced rows
   first if staged). Without this, no pass ever prunes raws and backfill
   triples their volume.

**Standings** (flag `market.standings_sync`): weekly pass; current-season
leagues; reuses the matchups fetcher (`backend/outlook/league_state.py:260`),
budget-counted, upsert `league_standings`. ⟨PRD-AMENDED⟩ First sync of a
league linked in week W **catch-up backfills weeks 1..W (≤18 calls, W ≤ 18)**;
thereafter one week per league per run — without catch-up, a week-15 link
waits ~15 weekly runs for usable win-now features.

### 4.10 B13 — profile derivations

`market_model` (P2-1), per league with rows: `trades_per_month` =
recency-weighted count (`exp(−age_days/90)`, answers R13); `shape_histogram`
from adds-per-roster splits; `positional_flow[pos]` = (adds−drops)/total;
`price_level[pos]` = median over trades of (consensus value received / paid) − 1
at current seed Elo via `elo_to_value`; `n_trades < 5` ⇒ NULL price_level
(consumers treat NULL as neutral). `opponent_profiles`: group by (league, owner
via the cached roster map); **formulas (spelled out — nothing else defines
them):**

- `trade_pace` = trades participated in per season observed;
- `consolidation_lean` = mean(assets sent − assets received) over their trades
  (positive = consolidator);
- `positions_bought` / `positions_sold` = counts of adds/drops by position;
- `age_lean` = value-weighted mean age of players acquired − players sent
  (values at current seed Elo);
- `waiver_churn` = waiver+FA adds per week, recency-weighted (`exp(−age_days/90)`);
- `faab_aggression` = Σ `waiver_bid` (from `sleeper_trades.raw` waiver rows) /
  `ingest_cursors.waiver_budget` for that (league, season) (§4.9.5), per season
  observed; NULL when the league has no FAAB or the budget is unfetched;
- `seasons_observed`, `confidence_n` = distinct seasons / transactions observed;
  `confidence_n < 5` ⇒ consumers ignore. `user_activity` (P2-5): per user with
events in 28d, exponential decay half-life 14d over `user_events` —
`calc_sessions_wk` (distinct `screen_viewed` sessions, `screen='Calculator'`),
`board_edit_recency_d` (MAX of `trio_swipe|tier_save|anchor_answered`),
`notif_tap_rate` (`notif_row_tapped` / sends in `notification_events_log`, 30d,
denominator floor 1), `sessions_wk`, `swipes_wk`.

Serving-path reads (`_run_trade_job`): one keyed SELECT per table per job,
`try/except → {}`, threaded down — never per-card queries. Consumed as (a)
frozen features (§3.6) and (b) two bounded composite multipliers behind
`relevance.profiles`: partner-pace `1 + clamp(0.1·tanh(opp_trade_pace −
league_mean), −0.1, 0.1)`; market-pace as a deck-size input to F10.

### 4.11 B14 — archetypes (D9)

`archetypes` pass: download nflverse season stats
(`player_stats_season_<yyyy>.csv` from nflverse-data releases; temp-file +
`os.replace`, players-cache pattern). **Schema validation before any math:**
`REQUIRED_COLS` registry per file; missing column ⇒ `status='error'`,
yesterday's rows stay live, report names the column (nflverse renames
season-to-season — the R11 tripwire). Crosswalk gsis→sleeper via `db_playerids`;
unmapped ⇒ no row ⇒ neutral; mapped-rostered coverage < 90% ⇒ `error` +
keep-yesterday. Axes (per-game rates, g = max(games,1)):

| Axis (pos) | Formula | Tag threshold |
|---|---|---|
| `rushing_qb` (QB) | rushing_yards/g | ≥ 25 |
| `workhorse` (RB) | (carries+targets)/g | ≥ 16 |
| `pass_catching_back` (RB) | targets/g | ≥ 3.5 |
| `early_down_grinder` (RB) | carries/g, targets/g < 2 | carries/g ≥ 10 |
| `deep_threat` (WR/TE) | aDOT = receiving_air_yards/max(targets,1) | ≥ 12.5 |
| `possession` (WR) | aDOT ≤ 8.5 ∧ receptions/g ≥ 4 | both |
| `alpha_target` (WR/TE) | target_share season mean | ≥ 0.22 WR / 0.17 TE |
| `featured_te` (TE) | wopr | ≥ 0.45 |

`archetype_json = {"axes": {...float}, "tags": [...], "season_source": ...}`
⟨PRD-AMENDED⟩; continuous axes are model features; tags feed taste dimensions
(P3-3: `card_taste_attrs` gains `arch:<tag>` for the top receive-side asset),
the F7 wildcard pool, and P4 copy. `archetype_confidence = clamp(games/17, 0,
1)`. ⟨PRD-AMENDED⟩ Coverage-gate denominator **excludes `years_exp = 0`
players and picks** (rookies get age-only rows: `axes:{}`, `tags:[]`,
confidence 0 — else the gate fails every August on rookie-heavy dynasty
rosters). **Season blend:** serve the prior-season row until current-season
games ≥ 6, stamping `season_source`; **tags travel with the served row**, the
games<6 suppression evaluated on the served row's own games (veterans keep
prior-season tags through September; rookies stay tag-suppressed). Thresholds
live as reviewed constants in `archetypes.py`, not runtime config, changeable
only with a P3-panel rerun.

### 4.12 B14 — value decomposition (P3-2 + absorbed P3-4)

Per (user, format) with `member_rankings`: target `y_p = user_elo_p −
seed_elo_p`; gates `n ≥ 25` ranked and ≥10 rows with `|y| ≥ 50`, else
`confidence='insufficient'` (P4 renders nothing). Design matrix: intercept;
position one-hots (PICK excluded); `age_centered` (age−26, clip ±6); the §4.11
continuous axes (0 when absent). Ridge via normal equations, λ =
`value_decomp_ridge_lambda (25)`, pure-Python Gauss-Jordan on a **14×14** system
(intercept + 4 position one-hots + age_centered + 8 archetype axes; D3: no
numpy). Coefficients clamped ±300 Elo (D9 plausible band). Build-philosophy keys
appended to the same JSON: `stars_and_scrubs` (roster-value Gini − league mean),
`age_barbell` (value-weighted age variance − league mean), `qb_premium` (QB
coefficient alias). `declared` corrections override inferred per key at read
(D10: per-user first). ⟨PRD-AMENDED⟩ Writer invariant: this pass overwrites
`coefficients` only, **never `declared`** (tombstones and opt-out stubs
survive every recompute — §3.3); skips opt-out stub rows entirely.

### 4.13 B11 — push eligibility (D6); B8 — drift check

**Push eligibility** — insertion points named; `_send_typed_push`
(`server.py:15743`) stays kind-agnostic and untouched:
`_run_weekly_replenishment` calls `push_eligible` before its send (`:16215`);
fail ⇒ inbox row still written (`:16204` already precedes — ordering correct),
push skipped, counted. Match/response kinds (`match_accepted` `:13195`,
match-created `:10319`, `match_expiring`, digests) **bypass** — the helper is
simply not called there; the review checklist item is "no `push_eligible` call
added to user-initiated kinds." Rules (fail-soft reads): percentile of
`top_card_score` among the user's trailing-30d `surface='deck'` `final_score`s ≥
`push_elig_percentile (75)` (accepted dark-launch artifact: if
`deck.value_model` flips mid-window the sample mixes score scales for ≤30d —
monitored, not engineered around); **thin history (< `push_elig_min_decks (5)`
distinct jobs) ⇒ PASS with `reason='no_history'`** — fail-open, because the
no-history cohort is exactly the new-user cohort the replenish push activates
(R12), and the percentile bar exists to suppress mediocre-relative-to-known-
taste pushes, a judgment requiring history; counted + monitored per-segment in
dark launch. Zero fatigue debt on centerpiece/archetype; `relaxed` falsy;
`basis != 'consensus'`; partner `users.last_active_at ≥ now −
push_elig_partner_active_days (14)`. Push impressions log `surface='push'`,
`propensity=1.0`, synthetic `deck_job_id="push-<hex12>"`, `card_index=0`; only
push-native outcomes may attach (HLD §3.1 closed set).

**Drift check** (`passes/drift_check.py`, nightly): sample ≤200 yesterday
impressions with `feature_set='fs2'`; assert `|final_score −
base·propensity·Π(frozen multipliers)| ≤ 1%·max(|final|, 1e-6)`; >2% violators ⇒
pass `error` + marker file `data/eval_runs/untrusted-<date>` (the promotion
counter skips those nights, §4.7). This is the tripwire for "someone added a
reorder without logging it" (R4).

## 5. Error Handling & Edge Cases

| # | Path | Failure | Specified behavior |
|---|---|---|---|
| E1 | Tick POSTed twice / Render retry | duplicate pass execution | `uq_pass_run` INSERT-claim; `ok` ⇒ skip; fresh `running` ⇒ skip; stale `running` (>2× budget) ⇒ mark `error`, re-claim `attempt+1` |
| E2 | Worker killed mid-pass | pass wedged all day | same stale-claim rule; `resumable` next day; `must_complete_today` retried same-day ≤2 |
| E3 | Foreign/stale/push impression_id on swipe | outcome + taste poisoning of the impression owner | §4.3 validation; drop + `outcome_rejected{reason}` counter; taste never runs on a rejected id |
| E4 | Disposition replayed concurrently | duplicate label rows | decision UPDATE serializes in-txn; second hits `already_decided` ⇒ `outcome_rows_written=0`; pre-insert existence check on `(impression_id, action, source_match_id)` |
| E5 | Match re-disposed | state corruption | unchanged state machine: same ⇒ idempotent 200, conflict ⇒ 409; labels only on the single `ok` transition |
| E6 | `impression_id_b` unrecoverable | missing counterpart labels | NULL; nightly `join_repair` unique-hit fuzzy; still-NULL ⇒ side unlabeled, never guessed |
| E7 | Two deck jobs same user racing | spine corruption | none: distinct `deck_job_id`s, impressions written once per job (`server.py:3653`); dedup is per-job in-memory; profile reads keyed |
| E8 | Sleeper 404 (pre-2021 / deleted) | infinite retry | terminal `done_empty`, zero attempts burned |
| E9 | Sleeper null/non-list/garbage entries | parse crash | existing `isinstance` guards preserved; per-entry skip |
| E10 | Budget exhausted mid-backfill | starvation/burst | atomic deny; cursors keep state; next UTC day resumes; budget 0 = kill switch |
| E11 | Restart mid-day | budget resets, real volume doubles | bucket is the `ingest_budget` row, not memory |
| E12 | `models.jsonl` torn append during read | serving crash | reader skips unparseable lines (`value_model.py:637`); cache re-reads on (mtime,size) change |
| E13 | v1 process reads v2 records (mixed deploy) | silent constant-0.5 scoring | v2 records omit the `"model"` key ⇒ v1 skips (§3.5) |
| E14 | Platt slice <8 positives | saturated calibration → deck zeroing | identity Platt + slope clamp + D5 blend clamp |
| E15 | Head <300 positives | overfit sparse head | inactive; parent fallback; child V zeroed |
| E16 | `vblend.active_id` → missing rows | undefined blend | DEFAULT_VBLEND fallback, log once, `vblend_id=null` stamped |
| E17 | nflverse column renamed | garbage archetypes | REQUIRED_COLS gate ⇒ `error` + keep-yesterday |
| E18 | Crosswalk coverage <90% | fleet-wide silent degradation | keep-yesterday + report line |
| E19 | Push percentile history empty | new-user push starvation | fail-open `no_history`, counted, dark-launch monitored |
| E20 | `deck_class_stats` empty/corrupt | deck breaks | `try/except → {}` ⇒ all 1.0; recovery = DELETE stat_date + re-run |
| E21 | `database is locked` under batch load | request-path stalls | `batch_write` short-txn/pacing on product engine; per-chunk single retry then pass `error`; locked-count in ledger feeds the §2.2 Postgres tripwire |
| E22 | Replay meets pre-fs2 impressions | scorer crash / skew | absent keys ⇒ 0.0 anchors; per-window feature_set mix reported |
| E23 | `why` route probed with harvested ids | counterparty data leak | ownership+surface check, uniform 404, rate limit |
| E24 | Demotion/vblend read racing writer | half-applied config | single-row UPDATEs atomic; applied values frozen per-impression ⇒ replay self-consistent even mid-flip |
| E25 | Dedup would empty the deck | thin deck | `_DECK_MIN_CARDS` restore; likes_you immune |
| E26 | Pinned record_id missing from `models.jsonl` | counting corrupted | eval pass `error`, night not counted, operator line |
| E27 | `previous_league_id` cycle | infinite walk | visited-set + depth ≤ 3 |

## 6. Backward Compatibility & Migration

### 6.1 Rollout order (flags flip only left→right)

```
P0: schema adds (dark) → ledger refactor (T-1 green) → P0-1 registration
 → P0-6 counters + P0-3 threading (write-only) → deck.dedup ON
 → flag_agg runs dark ≥7d → deck.class_demotion ON
P1: reader surface-filters land (§4.8 — BEFORE any push row can exist)
 → train.value_model ON (dark refit) → pin → 21-night counted eval
 → operator activate + deck.value_model ON (50% A/B) → push.eligibility_bar ON
P2: market.transactions_all ON → market.standings_sync ON → profile passes
 (dark-derive) → market.history_backfill (new links) → relevance.profiles ON
 (⟨PRD-AMENDED⟩ decoupled from data.archetypes: flips at end of P2 gating the
 two P2 multipliers, A/B-scoped — else P2's success metric is unmeasurable
 until P3) → fleet backfill ⛔ OQ-1 + Postgres call
P3: data.archetypes ON → P3 wiring extends relevance.profiles (holdback cell)
P4: ui.why_this → ui.personal_hooks → ui.trading_profile
```

Reviewer-enforced constraints: **surface filters merge before
`push.eligibility_bar` can flip** (one premature push row poisons F9, Thompson,
fatigue, and replay the same night); **T-1 gates every later pass PR**; **the
`train.value_model` split merges before the first count starts** (else the
window grades a stale artifact — D4's trap).

### 6.2 Reader whitelists (widening blast radius)

Rule: **readers whitelist, never blacklist.** Audited list, updated in the
P0-3/P1-3 diffs: `eval/data.py:157-172` (if/elif chain already ignores unknown;
gains explicit new-action reduce); `value_model.build_training_rows` (consumes
reduce booleans); Thompson v2 counts (viewed-gated — unaffected); fatigue reads
(`viewed`/`pass` only); taste `_reward_for` (unknown → 0.0 reward — correct
fail-safe until the new labels get explicit rewards in a later, separate PR);
`user_has_outcome_history` (gains the surface predicate).

### 6.3 Rollback inventory (what each step leaves behind; does it mislead?)

| Rolled back | Residue | Misleads? |
|---|---|---|
| Ledger refactor | `cron_pass_runs` rows | No (report-only). Stale `running` rows inert via the claim rule |
| P0-3 | columns + disposition rows | No — truthful history; trainers gate on maturation/quality |
| dedup / demotion | `deck_class_stats`; frozen stamps | No — stamps describe what was truly applied (replay correct *because* of the freeze) |
| F6 v2 | v2 records in `models.jsonl` | No — activate pointer decides serving; rollback = append pointer to prior record |
| Push impressions | `surface='push'` rows | **Yes, if filters were skipped** — §6.1 orders filters first; with them, inert |
| Ingestion | cursors, budget days, partial backfill | Partial backfill safe: derivations recompute from whatever raws exist; `confidence_n` carries the honesty |
| Archetypes/profiles | derived tables | No — `computed_at`/`confidence` visible; truncate + re-run is the stated recovery |

### 6.4 Postgres portability

Every statement here is dialect-portable: `ON CONFLICT DO NOTHING`,
constant-default ADD COLUMN, guarded check-and-take UPDATEs (no
`UPDATE … ORDER BY/LIMIT` anywhere — the cursor claim is the two-step in §4.9.1),
no partial indexes, no CHECK constraints. The §2.2 tripwire cutover needs zero
relevance-layer changes.

### 6.5 Data-rights registry rule

**Every new user- or platform-identity-keyed table ships in the same PR that
adds it to the account-deletion path — `delete_user_data` (`accounts.py:619`),
an imperative list of `_del()` calls, not a registry — AND to the data-export
tuple `_EXPORT_TABLES` (`accounts.py:754`)**, since export mirrors the deletion
matrix and a table deleted but never exported breaks that symmetry:
`user_value_profiles`, `user_activity_profiles`, and (by platform identity, per
HLD §5.2) `manager_trade_profiles`. "Row DELETEd on user request" for one table
is not a cascade. Sabotage test T-32: delete an account ⇒ zero rows remain in
all three.

## 7. Testing

House convention: **sabotage-proven structural tests** — each test names the
sabotage that must make it fail; review checks the sabotage list, not the green
run. Pure-Python, tmp SQLite; the `relevance/` package tests import no Flask.

| ID | Test | Fails when (sabotage) |
|---|---|---|
| T-1 | Ledger equivalence: recorder-patched legacy bodies; old inline tick vs registry tick on identical fixtures — **fixture set includes an Aug-25 day** (season_start suppression, §4.1) ⇒ identical call sequence + response JSON (minus `passes`) | refactor drift; pass dropped/reordered; winback double-send on the fan-out date |
| T-2 | Double-POST: two concurrent `run_ledger` on one day ⇒ each body executes exactly once | claim logic non-atomic |
| T-3 | Stale-`running`: seeded row 3× budget old ⇒ re-claim runs, `attempt=2` | stale rule dropped (permanent wedge) |
| T-4 | Propensity integrity: recompute order from `base × propensity × frozen multipliers` ⇒ equals served order; inject an unlogged ×1.3 ⇒ drift check reports | §2.3 contract violation |
| T-5 | Dedup: identical drops across 100 runs; tau=1.0 ⇒ none; survivor = higher base key; likes_you immune; min-cards restore | stochastic dedup; tau off-by-one |
| T-6 | Label attribution: full 2×2 disposition matrix ⇒ mapped labels on the correct impression per cell; 2 rows/event on two different impressions; ≤4 total; `source_match_id` set; 0 rows on `already_decided` | swapped map; double-count |
| T-7 | Disposition atomicity: forced outcome-insert failure ⇒ decision column rolled back too | route-level label writes |
| T-8 | Foreign/stale/push impression rejection: (a) other user's, (b) 15d-old, (c) push-surface ⇒ 0 outcome + 0 taste rows + counter; 13d-old valid ⇒ accepted | validation dropped (taste poisoning) |
| T-9 | Idempotent replay: same decision twice ⇒ 200, `outcome_rows_written=0`; conflict ⇒ 409, 0 rows | E4/E5 |
| T-10 | Surface filter: planted `push` row ⇒ excluded from `load_decks`, `user_has_outcome_history`, F9 history, Thompson, fatigue; opt-in loader sees it | any reader missing the predicate |
| T-11 | v1-loader-on-v2-file: v1 record + v2 records ⇒ v1 loader returns the v1 model, never an empty-weight shell | v2 reuses `"model"` key |
| T-12 | Pin/activate: 3 models + activate on #2 ⇒ #2 served; none ⇒ #3; activate on missing id ⇒ newest parseable + warning | pointer scan order |
| T-13 | Platt guard: 60 rows/3 pos ⇒ identity; 200/20 ⇒ fitted within clamps | guard or clamp dropped |
| T-14 | Head gating: 299 ⇒ inactive + parent + child V zeroed; 300 ⇒ active | ≥ floor off-by-one |
| T-15 | Determinism: train twice on same fixture ⇒ byte-identical artifact | RNG/dict-order nondeterminism |
| T-16 | Maturation: accept label at now−13d excluded; now−15d included | horizon inversion |
| T-17 | Pre-fs2 replay compat: old features_json scores without error; fs mix reported | extractor hard-requires fs2 keys |
| T-18 | Budget: budget=3, 5 concurrent takes ⇒ exactly 3 grants; new process, same DB ⇒ 0 remaining; budget=0 ⇒ all denied | in-memory bucket; take race |
| T-19 | Cursor machine: 404 ⇒ `done_empty` attempts=0; 5×5xx ⇒ `stuck` with backoff 2,4,8,16,32min; resume at `last_week+1`; claim expiry re-claims | E8; week off-by-one |
| T-20 | Sleeper shape fuzz: {null, {}, [null, 7, {no txid}]} ⇒ 0 rows, no raise | defensive parsing dropped |
| T-21 | Push eligibility: below-P75 blocked w/ reason; above allowed; <5 decks ⇒ `no_history` allowed; `match_accepted` path never calls the helper (spy) | percentile off-by-one; bar leaking into user-initiated kinds |
| T-22 | Replenish: ineligible push ⇒ inbox row still written, weekly marker set, no double-push next tick | ordering regression at `server.py:16186-16221` |
| T-23 | Flag-agg floors: 3/40 ⇒ 1.0; high-rate 250-exposure ⇒ clamped ≥0.5; frozen stamp = applied | D11 floor/clamp dropped |
| T-24 | nflverse drift: renamed column ⇒ `error`, yesterday served | REQUIRED_COLS bypassed |
| T-25 | Migration equivalence: fresh `create_all()` vs migrated legacy fixture ⇒ identical `PRAGMA table_info` per touched table; `_migrate_db()` ×2 ⇒ no error | non-idempotent/illegal DDL |
| T-26 | vblend validation: unknown head / sign-class violation (e.g. positive weight on a `NEGATIVE_HEADS` head) / non-monotonic id ⇒ 400; **DEFAULT_VBLEND itself passes the validator**; pointer flip ⇒ next job stamps new id | R10 fat-finger defenses; validator rejecting the D5-prescribed outsized-negative blends |
| T-27 | `why` authz: own ⇒ 200; other's/push/absent ⇒ identical 404 bodies | id-oracle regression |
| T-28 | Config lint: `model_config` reads in `backend/relevance/` outside `config.py` ⇒ fail; `valve()` callers outside the whitelist ⇒ fail | R10 resolver bypass |
| T-29 | Gate counters: sabotaged gate boolean flips a fixture verdict ⇒ counter test fails (proves counters ride the real gates); counters-only diff leaves verdicts identical | P0-6 touching gate behavior |
| T-30 | Decomposition: ridge recovers planted coefficients within tolerance; clamps a planted outlier; insufficient-confidence renders nothing through the P4 serializer | formula/gate regression |
| T-31 | Cold-start gate: user with 19 deck outcomes ⇒ composite even with `deck.value_model` on; 20 ⇒ model scores | HLD §5.3 minimum regressing to ≥1 |
| T-32 | Deletion cascade: delete account ⇒ zero rows in `user_value_profiles`, `user_activity_profiles`, `manager_trade_profiles` for that identity | table missing from the `delete_user_data` path or the export tuple |
| T-33 | Raw retention: planted 4-season-old `sleeper_trades` row pruned; 2-season-old kept | retention step dropped (§4.9.6) |
| T-34 | Lift CI: paired bootstrap on a fixture where candidate beats baseline by a planted margin ⇒ `ci_lo > 0` at 0.90; noise fixture ⇒ straddles 0 | verdict computed from per-scorer CIs instead of the paired difference |
| T-35 | ⟨PRD-AMENDED, P2⟩ Last-unlink of a league ⇒ zero `manager_trade_profiles` + `league_market_profiles` rows for that league and its cursor rows deleted (capture stops; re-link recreates); a non-last unlink deletes nothing | unlink deletion asserted but untested; multi-linked league clobbered by one user's unlink |

Maestro deltas (feature-gate #2): P4 surfaces only — `why-this-sheet.yaml`,
`personal-hooks.yaml`, `trading-profile.yaml` (stretch). Backend-only steps
B1–B14 file written Maestro waivers in their scope blocks. Sim-gate tier per
`docs/runbook.md` matrix; TEST_LEDGER rows per shipped item.

## 8. Open Questions

1. **Web swipes carry no `impression_id` today** — side-A exactness on web rides
   the nightly fuzzy repair. A ~20-line web diff (echo `impression_id` like
   mobile) would materially raise the exact-join rate the whole D4 promotion
   timeline depends on. Recommend adding to P0-3's scope block.
2. `match_already_exists` is an O(matches-in-league) scan per like
   (`database.py:6652`) — P2 features will raise like volume. Opportunistic
   index + WHERE in the P0-3 diff; reviewer's call, not HLD-required.
3. D4's 21 *counted* nights may take 6–10 calendar weeks at current volume
   (ESS-failing nights don't count). Operator expectation-setting only; the §2.3
   report shows "n of 21 counted / m elapsed."
4. `deck_outcomes.join_quality` and `trade_matches.join_quality_b` overlap
   deliberately: trainers filter on the outcome row without joining back to
   matches; the match row keeps provenance for repair. Kept both.
5. `price_level` and opponent-profile formulas are untested against real trade
   volume; the n<5 NULL guard may need raising to 10 after a first real-data
   look.
6. nflverse `target_share`/`wopr` presence in the current season-file release
   should be verified in the P3-1 scope block; the REQUIRED_COLS error path
   covers drift either way.
7. The Chrome-spoof UA on `sleeper_trades_service` (`:44-50`) is left untouched
   pending the HLD's operator question 3 — flagged so the P2 scope block doesn't
   silently inherit it.
