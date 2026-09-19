# Low-Level Design — FTF Self-Training Loops (Plan 1)

> **Purpose:** the mechanic's-eye view. Column-level schemas, module maps, function signatures, and config keys — the level at which a build agent can implement without re-deriving anything.
>
> **Companions:** [`loop-hld.md`](loop-hld.md) (architecture, trade-offs) and [`loop-prd.md`](loop-prd.md) (requirements, tests, work breakdown).
>
> **Conventions inherited from the repo:** SQLAlchemy Core tables in `backend/database.py`; ISO-8601 UTC strings for all timestamps (`str` columns, matching every existing table); JSON stored as TEXT; idempotent `_migrate_db()` ALTERs; **no dialect-specific SQL** — aggregation happens in Python (the `load_engine_telemetry` pattern) so SQLite now / Postgres later both work. All types below are portable: `Integer`, `Float`, `String`, `Text`.
>
> **Privacy rule (applies to every schema here):** payloads carry Sleeper user IDs and player IDs only. No usernames, display names, push tokens, or free text in `props`/`payload_json`/`deck_json`.

---

## Table of Contents
- [New tables](#new-tables)
- [Altered tables](#altered-tables)
- [Event taxonomy additions (`user_events`)](#event-taxonomy-additions-user_events)
- [Module map](#module-map)
- [Function signatures](#function-signatures)
- [API routes](#api-routes)
- [Config keys](#config-keys)
- [Config files](#config-files)
- [Metric definitions (pre-registered)](#metric-definitions-pre-registered)
- [Guardrail definitions](#guardrail-definitions)
- [Checklists and review docs](#checklists-and-review-docs)

---

## New tables

All defined in `backend/database.py` (`metadata`), created by `create_tables()`, with `_migrate_db()` no-ops for fresh installs.

### `league_state_snapshots` (1A)

Frozen league state at trade-generation time. Content-hash deduped: identical state across consecutive jobs stores one row.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK autoincrement | |
| `snapshot_hash` | String, UNIQUE, not null | sha256 hex of the canonical (sorted-keys) JSON payload |
| `league_id` | String, not null | |
| `scoring_format` | String | `'1qb_ppr'` / `'sf_tep'` |
| `schema_version` | Integer, default 1 | bump when payload shape changes; replay code switches on it |
| `payload_json` | Text, not null | see payload contract below |
| `captured_at` | String | ISO UTC |

Indexes: `ix_lss_league_at` on `(league_id, captured_at)`.

**`payload_json` contract (schema_version 1):**

```json
{
  "rosters":            {"<sleeper_user_id>": ["<player_id>", "..."]},
  "member_rankings":    {"<sleeper_user_id>": {"<player_id>": 1612.4}},
  "comparison_counts":  {"<player_id>": 7},
  "league_preferences": {"<sleeper_user_id>": {"team_outlook": "contender",
                          "acquire_positions": ["WR"], "trade_away_positions": ["QB"]}},
  "draft_picks":        [{"pick_id": "...", "owner_user_id": "...", "season": 2027,
                          "round": 1, "pick_value": 2350.0}],
  "model_config":       {"elo_value_k": 0.005, "...": 0},
  "flags":              {"trade_engine.v2": true, "...": false}
}
```

IDs only — usernames/display names are deliberately absent (re-joinable via `league_members` at replay time if ever needed for display).

### `engine_proposal_log` (1A)

One row per completed trade-generation job: which engine, against which frozen state, produced which ordered deck. The offline-replay substrate.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK autoincrement | |
| `job_id` | String, UNIQUE, not null | uuid4 hex, minted in `_run_trade_job`; also stamped on `trade_impressions` rows |
| `user_id` | String, not null | deck owner |
| `league_id` | String, not null | |
| `engine_version` | String, not null | from `current_engine_version()`, e.g. `v3+three_team` |
| `config_hash` | String, not null | from `current_config_hash()` — sha256 over effective `model_config` + flags |
| `variant` | String, nullable | experiment variant (`control`/`treatment`) or null when no live experiment |
| `snapshot_id` | Integer, not null | FK → `league_state_snapshots.id` |
| `deck_json` | Text, not null | ordered cards: see contract below |
| `generated_at` | String | ISO UTC |

Indexes: `ix_epl_league_at` on `(league_id, generated_at)`, `ix_epl_version_at` on `(engine_version, generated_at)`.

**`deck_json` contract** — array, served order:

```json
[{"trade_id": "a1b2c3d4", "target_user_id": "...",
  "give": ["<player_id>"], "receive": ["<player_id>", "<pick_id>"],
  "basis": "divergence", "likes_you": 0, "sweetener_player_id": null,
  "mismatch_score": 312.5, "fairness_score": 0.91, "composite_score": 0.44,
  "position_in_deck": 0}]
```

### `experiment_assignments` (1A/1B/1D)

Sticky record of each unit's first exposure to the live experiment.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK autoincrement | |
| `experiment_key` | String, not null | from `config/experiment.json` |
| `unit_type` | String, not null | `'user'` or `'league'` |
| `unit_id` | String, not null | sleeper_user_id or sleeper_league_id |
| `variant` | String, not null | `'control'` / `'treatment'` |
| `assigned_at` | String | ISO UTC of first exposure |

Uniqueness: `UNIQUE(experiment_key, unit_type, unit_id)` (insert-or-ignore on exposure).

### `loop_rollups` (1A–1E)

Generic daily/weekly metric store written only by `rollup_daily` (idempotent upsert).

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK autoincrement | |
| `loop` | String, not null | `'1A'`…`'1E'` |
| `metric` | String, not null | snake_case, see [Metric definitions](#metric-definitions-pre-registered) |
| `period` | String, not null | `'day'` / `'week'` |
| `period_start` | String, not null | ISO date (`YYYY-MM-DD`; Mondays for weeks) |
| `dims_json` | Text, not null, default `"{}"` | canonical sorted-keys JSON of dimensions: any of `client`, `engine_version`, `variant`, `cohort`, `league_id`, `season_window`, `kind`, `stage` |
| `value` | Float, not null | the metric value |
| `n` | Integer | denominator / sample size (read thin-data guards off this) |
| `computed_at` | String | ISO UTC |

Uniqueness: `UNIQUE(loop, metric, period, period_start, dims_json)`. Upsert = delete-then-insert on the key (portable across SQLite/Postgres without `ON CONFLICT` dialect concerns).

---

## Altered tables

### `trade_impressions` — five new nullable columns (via `_migrate_db()` idempotent ALTERs)

| New column | Type | Notes |
|---|---|---|
| `trade_id` | String | the card's 8-char id — primary downstream join key |
| `job_id` | String | links to `engine_proposal_log.job_id` |
| `engine_version` | String | denormalized from the job for cheap grouping |
| `variant` | String | experiment variant at serve time, nullable |
| `client` | String | requesting client: `'web'` / `'mobile'` / `'extension'` (from the session's device headers) |

New index: `ix_trade_impressions_trade_id` on `trade_id`. Legacy rows keep nulls; rollups fall back to the documented give/receive-set join for pre-migration data.

No other existing table changes.

---

## Event taxonomy additions (`user_events`)

New `event_type` values (extend the taxonomy list in `docs/data-dictionary.md` and the cross-client list). All emitted with the existing envelope (`device_type`, `source`, `league_id`, `session_id`); `props` schemas below are exhaustive — unknown keys are stripped at ingestion.

| event_type | Loop | Emitted by | `props` |
|---|---|---|---|
| `trade_card_view_detail` | 1A | clients via `POST /api/events` | `{"trade_id", "league_id", "basis", "position_in_deck"}` |
| `trade_card_shared` | 1A | clients | `{"trade_id", "league_id", "channel": "share_page"\|"og_image"\|"copy_link"}` |
| `invite_nudge_shown` | 1B | clients | `{"surface": "cold_start"\|"league_tab", "league_id"}` |
| `invite_nudge_dismissed` | 1B | clients | `{"surface", "league_id"}` |
| `invite_sent` | 1B | clients | `{"league_id", "channel": "share"\|"copy_link"\|"sms"}` |
| `server_cold_start` | 1E | server (first request post-boot) | `{"boot_ms": 4180, "commit": "<short sha>"}` |

Reused existing types (no change): `signup`, `login`, `league_synced`, `trio_swipe`, `ranking_complete_first_time`, `push_sent` (gains optional `"variant"` prop), `push_opened`, `notif_pref_changed`.

---

## Module map

| File | Status | Role |
|---|---|---|
| `backend/loop_logging.py` | NEW | Snapshot + proposal-deck writers; engine-version/config-hash derivation |
| `backend/experiments.py` | NEW | Experiment config loader, deterministic bucketing, assignment recording |
| `backend/loop_metrics.py` | NEW | `rollup_daily` + all per-loop report builders + season-window table |
| `backend/guardrails.py` | NEW | Breach checks (fairness, nudge fatigue, notification opt-out); pure reads |
| `backend/scripts/fairness_audit.py` | NEW | CLI fairness audit over `engine_proposal_log` (per-release gate) |
| `backend/scripts/check_invariants.py` | NEW | CI invariant checker driven by `config/invariants.json` |
| `backend/scripts/synthetic_check.py` | NEW | Post-deploy perf probe vs `config/perf-budgets.json` |
| `backend/database.py` | EDIT | New tables, ALTERs, `log_trade_impressions` enrichment, loop read/write helpers |
| `backend/feature_flags.py` | EDIT | Experiment-aware flag resolution (`flag_with_experiment`) |
| `backend/trade_service.py` | EDIT | Expose effective engine/config identity to `loop_logging` |
| `backend/server.py` | EDIT | `POST /api/events`, `/api/admin/loop/*` routes, daily-tick hook, job-time logging call-sites, nudge frequency-cap check, cold-start event |
| `web/js/app.js`, `mobile/src/api/events.ts` (NEW), `mobile/src/components/TradeCard.tsx`, `extension/content.js` | EDIT/NEW | Client event emission (batched, fire-and-forget) |

---

## Function signatures

### `backend/loop_logging.py`

```python
def current_engine_version() -> str:
    """Deterministic engine identity from active flags:
    'legacy' | 'v2' | 'v3', '+' -joined with active modifier flags in fixed
    order (e.g. 'v3+three_team'). Pure function of feature_flags state."""

def current_config_hash() -> str:
    """sha256 hex (first 12 chars) over canonical JSON of effective
    model_config values + flag booleans. Changes whenever tuning changes."""

def snapshot_league_state(league_id: str, scoring_format: str,
                          state: dict) -> int:
    """Canonicalize `state` (payload contract, schema_version 1), hash,
    INSERT OR IGNORE on snapshot_hash, return snapshot id (existing or new).
    `state` is assembled by the caller from data _run_trade_job already
    loaded — no extra DB reads."""

def log_proposal_deck(job_id: str, user_id: str, league_id: str,
                      snapshot_id: int, cards: list, *,
                      engine_version: str, config_hash: str,
                      variant: str | None) -> None:
    """Serialize served deck (deck_json contract) and insert one
    engine_proposal_log row. Called once per job, after deck ordering,
    alongside log_trade_impressions. Demo league excluded (same rule)."""
```

### `backend/experiments.py`

```python
def live_experiment() -> dict | None:
    """Parse config/experiment.json. Returns the experiment dict when
    status == 'live', else None. Raises ValueError on malformed config
    (fail loud at boot, not silently mid-assignment)."""

def variant_for(unit_id: str) -> str | None:
    """None when no live experiment. Else deterministic:
    treatment iff int(sha256(f'{salt}:{unit_id}').hexdigest(), 16) % 10_000
    < split * 10_000. Stateless — same answer in every process."""

def record_exposure(unit_id: str) -> str | None:
    """variant_for + INSERT OR IGNORE into experiment_assignments.
    Call at the moment the variant takes behavioral effect."""

def flag_with_experiment(flag_key: str, unit_id: str | None) -> bool:
    """Resolve a feature flag with the experiment overlay: if a live
    experiment targets flag_key and unit_id is given → treatment gets
    `treatment_value`, control gets the features.json value. Otherwise
    plain feature_flags.flag_enabled(flag_key)."""
```

### `backend/loop_metrics.py`

```python
SEASON_WINDOWS: list[tuple[str, str, str]]
    # [(start_mmdd, end_mmdd, label)] — code constant, calibrated as a set:
    # ('03-01','07-31','offseason'), ('08-01','09-05','preseason'),
    # ('09-06','12-15','in_season'), ('12-16','02-28','playoffs')

def season_window(date_iso: str) -> str: ...

def action_score(counts: dict) -> float:
    """counts: {'dismiss': n, 'view': n, 'save': n, 'share': n}.
    Returns Σ action_w_<k> * n_k, weights read from model_config."""

def rollup_daily(day: str | None = None) -> dict:
    """Compute every loop metric for `day` (default: yesterday UTC) and
    upsert loop_rollups (delete+insert per unique key — idempotent).
    Also recomputes the containing ISO week's 'week' rows.
    Returns {'rows_written': int, 'day': str}. Called from daily-tick."""

def engine_report(days: int = 28) -> dict:
    """1A. Per (engine_version, variant): decks, impressions, like/pass/
    view/share counts, action_score_per_deck, fairness distribution
    summary (p10/p50/share_below_floor). Thin-data flag when n < min_n."""

def growth_report(weeks: int = 8) -> dict:
    """1B. Per ISO week: nudges shown/dismissed, invites sent, accepts,
    activations, stage conversions, k = invites_per_active_user *
    accept_rate * activation_rate."""

def activation_report(cohorts: int = 8) -> dict:
    """1C. Per signup-week cohort: stage funnel (signup → league_synced →
    first trio_swipe → first impression), activation rate (stage 4 within
    14d), and matchups_before_value / matchups_before_abandon histograms
    (p25/p50/p75)."""

def retention_report(cohorts: int = 12) -> dict:
    """1D. Per signup-week cohort with a closed horizon: D7, D30,
    season_window tag, per-variant push open + opt-out rates. Rows are
    grouped by season_window; the report never aggregates across windows."""
```

### `backend/guardrails.py`

```python
def check_guardrails(days: int = 14) -> list[dict]:
    """Run all guardrail checks; return breach dicts:
    {'guardrail': str, 'loop': str, 'value': float, 'threshold': float,
     'window_days': int, 'breached': bool, 'detail': str}.
    Checks: fairness_distribution (1A), nudge_dismiss_rate (1B),
    notification_optout_delta (1D). Pure reads; humans actuate."""
```

### `backend/scripts/fairness_audit.py` (CLI)

```python
# python3 backend/scripts/fairness_audit.py --days 28 [--strict]
def run_audit(days: int = 28) -> dict:
    """Read engine_proposal_log decks in window. Compute per-card
    consensus value delta = |give_value - receive_value| via
    fairness_score (delta_ratio = 1 - fairness_score). Assert:
      p10(fairness_score) >= cfg.fairness_audit_min_p10
      share(fairness_score < cfg.fairness_audit_floor) <= cfg.fairness_audit_max_below_floor_pct
      1-for-1 subset (len(give)==len(receive)==1): min fairness >=
        cfg.fairness_audit_1for1_floor      # the seed check
    Returns report dict; --strict exits 1 on any breach (release gate)."""
```

### `backend/scripts/check_invariants.py` (CLI)

```python
# python3 backend/scripts/check_invariants.py [--manifest config/invariants.json]
# For each invariant: for each location {file, pattern (regex with one
# capture group), expected}: read file, assert every match's capture ==
# expected. Missing file or zero matches = failure (guards against the
# pattern rotting). Exit 0 clean / 1 with per-invariant diagnostics.
```

### `backend/scripts/synthetic_check.py` (CLI)

```python
# python3 backend/scripts/synthetic_check.py --host https://<render-host> [--strict]
# For each budget in config/perf-budgets.json: probe (GET page or API
# route, N=3 samples, report median), compare to budget_ms, print table.
# Cold-start budgets probe immediately post-deploy by design.
# v1 default is advisory (exit 0 with warnings); --strict exits 1.
```

---

## API routes

All in `backend/server.py`; admin routes follow the existing `/api/admin/*` conventions.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/events` | Batched client event ingestion. Body `{"events": [{"event_type", "occurred_at", "league_id"?, "props"?}]}`, max 50/batch. Session-authed; `device_type`/`source` from existing headers. event_type must be in the client-emittable whitelist (the 6 new types minus `server_cold_start`); `props` filtered to the declared keys per type (PII defense). Each accepted event → `record_event()`. Returns `{accepted, rejected}` |
| GET | `/api/admin/loop/engine-report` | `?days=28` → `engine_report()` |
| GET | `/api/admin/loop/growth-report` | `?weeks=8` → `growth_report()` |
| GET | `/api/admin/loop/activation-report` | `?cohorts=8` → `activation_report()` |
| GET | `/api/admin/loop/retention-report` | `?cohorts=12` → `retention_report()` |
| GET | `/api/admin/loop/guardrails` | `?days=14` → `check_guardrails()` |
| GET | `/api/admin/loop/experiment` | Live experiment config + assignment counts per variant |

Changed behavior (no new route): `POST /api/cron/daily-tick` additionally calls `rollup_daily()` then `check_guardrails()` (breaches logged to the debug ring buffer). Existing `GET /api/admin/engine-metrics` is unchanged (superseded for loop work by `engine-report`, kept for compatibility).

---

## Config keys

New `model_config` keys — add to `_MODEL_CONFIG_DEFAULTS` in `backend/database.py` so they're DB-seeded and admin-tunable (note: per [config-reference.md](../config-reference.md), keys not in `_MODEL_CONFIG_DEFAULTS` can't be tuned via the admin API).

### 1A — action-score weights (pre-registered 2026-06; revisit quarterly at most, with checklist sign-off)

| Key | Default | Meaning |
|---|---|---|
| `action_w_dismiss` | 0.0 | weight per pass/dismiss |
| `action_w_view` | 1.0 | weight per `trade_card_view_detail` |
| `action_w_save` | 3.0 | weight per like (save) |
| `action_w_share` | 8.0 | weight per `trade_card_shared` / proposal sent |

### 1A — fairness audit bounds

| Key | Default | Meaning |
|---|---|---|
| `fairness_audit_min_p10` | 0.65 | p10 of `fairness_score` over audited decks must be ≥ this |
| `fairness_audit_floor` | 0.60 | "unacceptably lopsided" threshold |
| `fairness_audit_max_below_floor_pct` | 5.0 | max % of cards below the floor |
| `fairness_audit_1for1_floor` | 0.75 | min fairness for any 1-for-1 card (the seed check from the v2 watch item) |

### 1B — nudge guardrails

| Key | Default | Meaning |
|---|---|---|
| `nudge_max_per_user_per_week` | 2.0 | server-side cap before rendering an invite nudge |
| `nudge_dismiss_kill_rate` | 0.60 | trailing-14d dismissed/shown above this → guardrail breach |

### 1D — retention guardrails / reporting

| Key | Default | Meaning |
|---|---|---|
| `retention_optout_kill_delta` | 0.02 | treatment opt-out rate may exceed control by at most this (absolute) |
| `loop_min_n` | 30.0 | below this denominator, reports mark the row `thin: true` and guardrails stay silent |

---

## Config files

### `config/experiment.json` (NEW) — exactly one experiment object (one-live-variant rule is structural)

```json
{
  "_comment": "At most ONE experiment may be live. status: 'off' | 'live'.",
  "experiment_key": "none",
  "status": "off",
  "flag": "trade.deck_diversity",
  "unit": "user",
  "split": 0.5,
  "salt": "set-a-fresh-salt-per-experiment",
  "treatment_value": true,
  "primary_metric": "action_score_per_deck",
  "min_runtime_days": 14,
  "started_at": null
}
```

Loader validation: `split ∈ (0,1)`, `flag` must exist in `feature_flags.FLAG_KEYS`, `unit ∈ {user, league}`, non-empty salt when live. Document in `docs/config-reference.md`.

### `config/invariants.json` (NEW) — machine-readable mirror of `docs/cross-client-invariants.md`

```json
{
  "_comment": "CI source of truth for cross-client values. Keep in lockstep with docs/cross-client-invariants.md — changing an invariant means editing the manifest, every listed location, and the doc in one commit.",
  "invariants": [
    {
      "id": "tier_color_elite",
      "doc_section": "Tier color tokens",
      "expected": "gold",
      "locations": [
        {"file": "mobile/src/theme/colors.ts", "pattern": "elite:\\s*['\"]?#?(\\w+)"},
        {"file": "web/css/styles.css",         "pattern": "--tier-elite:\\s*(\\w+)"},
        {"file": "extension/content.css",      "pattern": "--tier-elite:\\s*(\\w+)"}
      ]
    },
    {
      "id": "progress_gate_qb",
      "doc_section": "Progress gating thresholds",
      "expected": "10",
      "locations": [
        {"file": "backend/server.py", "pattern": "\"QB\":\\s*(\\d+)\\s*#\\s*gate"}
      ]
    }
  ]
}
```

Build note: the WP that creates this file derives one entry per row of the invariants doc (tier colors ×5, position colors ×4, gating thresholds ×4, K-factor defaults ×5, fairness-meter `*100` in both clients, scoring-format strings, copy strings ×4), fixing patterns against the *actual* source lines (the patterns above are illustrative). Every location named in the doc gets an entry; if a value can't be pinned by regex, the invariant gets `"check": "manual"` and the checker reports it as SKIPPED (visible, not silent).

### `config/perf-budgets.json` (NEW) — checked-in time-to-first-action budgets

```json
{
  "_comment": "Budgets in ms. TTFA = navigation start to first meaningful action available. Synthetic checks probe API routes; client TTFA budgets are verified in persona walkthroughs until client-side RUM exists.",
  "api": {
    "session_init_cold_ms":   8000,
    "session_init_warm_ms":   1500,
    "trio_ms":                 800,
    "trades_list_ms":          800,
    "trades_generate_job_ms": 20000,
    "tier_config_ms":          300
  },
  "client_ttfa": {
    "web.index_ms":        2500,
    "web.trades_ms":       3000,
    "mobile.Rank_ms":      2000,
    "mobile.Trades_ms":    3000,
    "extension.popup_ms":  1500
  },
  "cold_start": {
    "render_boot_to_first_response_ms": 15000
  }
}
```

`backend/profile_session_init.py` already measures the dominant cold path; its cold/warm numbers seed `session_init_*` budgets at build time.

---

## Metric definitions (pre-registered)

Written to `loop_rollups` by `rollup_daily`. `dims_json` lists the dimensions each metric is split by.

| loop | metric | period | dims | Definition |
|---|---|---|---|---|
| 1A | `action_score_per_deck` | day | engine_version, variant, client | Σ weighted actions on cards served that day ÷ decks served. Joins on `trade_id`; legacy fallback join on (user, league, give/receive sets) |
| 1A | `like_rate` / `view_rate` / `share_rate` | day | engine_version, variant | per-impression action rates |
| 1A | `fairness_p10` / `fairness_below_floor_pct` | day | engine_version | from `engine_proposal_log.deck_json` |
| 1B | `nudges_shown` / `nudges_dismissed` / `invites_sent` / `invites_accepted` / `invites_activated` | week | client, surface | funnel stage counts; accepted = signups with `invited_by`; activated = `ranking_complete_first_time` within 14d of signup |
| 1B | `viral_coefficient` | week | — | invites_sent_per_weekly_active × accept_rate × activation_rate |
| 1C | `funnel_stage_reached` | week | cohort, stage | users in signup-week cohort whose furthest stage ≥ stage (1 signup, 2 league_synced, 3 trio_swipe, 4 first impression) |
| 1C | `activation_rate` | week | cohort | stage-4-within-14d ÷ cohort size |
| 1C | `matchups_before_value_p50` / `matchups_before_abandon_p50` | week | cohort | medians of rank-decision counts (`swipe_decisions`, `decision_type='rank'`, ÷3 per trio) at first impression / at abandonment (no impression + 14d inactive) |
| 1D | `d7_retention` / `d30_retention` | week | cohort, season_window | cohort users with any `user_events` row in day 7 / days 1–30 windows ÷ cohort size |
| 1D | `push_open_rate` / `notif_optout_rate` | week | variant, kind | per-variant `push_opened`/`push_sent`; opt-outs from `notif_pref_changed` flips to 0 |
| 1E | `cold_start_p50_ms` / `cold_start_p95_ms` | day | — | from `server_cold_start` events |

**Season-window comparability rule (1D, normative):** every 1D rollup row carries `season_window`; `retention_report` groups by window and never returns a comparison across windows. Experiments must start and be read inside one window.

---

## Guardrail definitions

| Guardrail | Loop | Check (trailing window) | Threshold source |
|---|---|---|---|
| `fairness_distribution` | 1A | p10 + below-floor share + 1-for-1 floor over `engine_proposal_log` | `fairness_audit_*` keys |
| `nudge_dismiss_rate` | 1B | `invite_nudge_dismissed` ÷ `invite_nudge_shown`, 14d | `nudge_dismiss_kill_rate` |
| `notification_optout_delta` | 1D | treatment minus control opt-out rate, since experiment start | `retention_optout_kill_delta` |

All guardrails respect `loop_min_n` (silent below it) and **flag only** — disabling a nudge/experiment/engine flag is a human action recorded in `living-memory/CHANGELOG.md`.

---

## Checklists and review docs

| File | Status | Content |
|---|---|---|
| `docs/loop-reviews/quarterly-reward-hacking.md` | NEW | Checklist: (1) pull stratified sample of 30 proposals across action-score deciles from `engine_proposal_log`; (2) inspect top decile for flashy-lopsided patterns (star-for-quantity, sweetener abuse, consensus-basis spam); (3) compare action-score winners' fairness distribution vs deck average; (4) review any requested `action_w_*` change against this evidence; (5) dated sign-off table (reviewer, verdict, weight changes approved) |
| `docs/release-checklists/persona-walkthroughs.md` | NEW | Per release, per client (web/mobile/extension), three scripted personas: *new user* (Sleeper login → league import → first trio ≤ 2 min), *active trader* (open app → first trade card ≤ 4 taps/clicks → share a card), *inviter* (reach invite surface ≤ 3 taps, send invite). Each step has a pass/fail box + TTFA stopwatch column cross-referenced to `config/perf-budgets.json` `client_ttfa` budgets |

---

## Docs-sync obligations (per the root CLAUDE.md table)

| Change in this design | Doc to update at build time |
|---|---|
| New tables + `trade_impressions` columns (`backend/database.py`) | `docs/data-dictionary.md` |
| New routes (`backend/server.py`) | `docs/api-reference.md` |
| New `model_config` keys, `config/experiment.json`, `config/perf-budgets.json`, `config/invariants.json` | `docs/config-reference.md` |
| New event types + experiment/variant enum strings | `docs/cross-client-invariants.md` (taxonomy + enums), `docs/data-dictionary.md` (user_events list) |
| New modules (`loop_logging`, `experiments`, `loop_metrics`, `guardrails`) | `docs/architecture.md` |
| New terms (action score, viral coefficient, season window, engine version string) | `docs/glossary.md` |
| Guardrail runbooks (what to do on breach) | `docs/runbook.md` |
| One-live-experiment + pre-registered-weights decisions | new ADR in `docs/adr/` |
