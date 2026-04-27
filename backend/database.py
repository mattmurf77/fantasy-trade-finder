"""
database.py — Fantasy Trade Finder
=====================================
Persistence layer using SQLAlchemy Core with SQLite (local dev).

Switch to PostgreSQL for production by setting the DATABASE_URL env var:
    DATABASE_URL=postgresql://user:pass@host/dbname
    pip install psycopg2-binary

Default: SQLite file alongside server.py — zero configuration required.
"""

import json
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Float, Index, Integer, MetaData, String, Table, Text, UniqueConstraint,
    create_engine, delete, insert, or_, select, update, and_, text,
)
from datetime import timedelta

# ---------------------------------------------------------------------------
# Engine — SQLite by default, PostgreSQL if DATABASE_URL is set
# ---------------------------------------------------------------------------

_DB_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(_DB_DIR, exist_ok=True)
_DB_PATH    = os.path.join(_DB_DIR, "trade_finder.db")
_DEFAULT_URL = f"sqlite:///{_DB_PATH}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_URL)

# Render provides postgres:// but SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# connect_args only needed for SQLite (enables WAL mode for concurrent reads)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine   = create_engine(DATABASE_URL, echo=False, future=True,
                         connect_args=_connect_args)
metadata = MetaData()

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

users_table = Table("users", metadata,
    Column("sleeper_user_id", String,  primary_key=True),
    Column("username",        String),
    Column("display_name",    String),
    Column("avatar",          String),
    Column("created_at",      String),
    Column("ranking_method",  String),   # null | 'trio' | 'manual' | 'tiers'
    Column("tiers_saved",     Text),     # JSON — dual-format shape:
                                          #   {"1qb_ppr": ["RB","WR"], "sf_tep": []}
    Column("tier_overrides",  Text),     # JSON — dual-format shape:
                                          #   {"1qb_ppr": {pid: elo}, "sf_tep": {pid: elo}}
    Column("invited_by",      String),   # sleeper username of referrer (null = direct)
    Column("unlocked_formats", Text),    # JSON list — which formats the user has
                                          # unlocked trade finder in, e.g. ["1qb_ppr"]
    # ── User-event denormalized hot-read columns (see user_events_table) ──
    Column("last_active_at",        String),
    Column("last_login_at",         String),
    Column("last_rank_at",          String),
    Column("last_match_seen_at",    String),
    Column("last_trade_proposed_at", String),
    Column("last_push_sent_at",     String),
    Column("signup_at",             String),
    Column("events_count",          Integer),
    Column("last_device_type",      String),
    Column("last_os_version",       String),
    Column("last_app_version",      String),
)

leagues_table = Table("leagues", metadata,
    Column("sleeper_league_id", String, primary_key=True),
    Column("user_id",           String, nullable=False),
    Column("name",              String),
    Column("season",            String),
    Column("roster_data",       Text),   # JSON: list of user's player IDs
    Column("opponent_data",     Text),   # JSON: list of {user_id, username, player_ids}
    Column("created_at",        String),
    Column("updated_at",        String),
    Column("default_scoring",   String), # '1qb_ppr' | 'sf_tep' (null → treated as '1qb_ppr')
)

# Each row = one pairwise (winner, loser) comparison extracted from a ranking or trade swipe.
# For a 3-player ranking A>B>C: we write 3 rows: (A,B), (A,C), (B,C) all with decision_type='rank'.
# For a trade swipe: we write pairwise rows with decision_type='trade' and a smaller k_factor.
swipe_decisions_table = Table("swipe_decisions", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("user_id",          String,  nullable=False),
    Column("winner_player_id", String,  nullable=False),
    Column("loser_player_id",  String,  nullable=False),
    Column("decision_type",    String,  nullable=False),  # 'rank' | 'trade'
    Column("k_factor",         Float,   nullable=False, default=32.0),
    Column("created_at",       String),
    Column("scoring_format",   String), # '1qb_ppr' | 'sf_tep' (null = legacy '1qb_ppr')
)

# High-level record of each trade card decision — human-readable audit trail.
trade_decisions_table = Table("trade_decisions", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("user_id",            String,  nullable=False),
    Column("league_id",          String,  nullable=False),
    Column("trade_id",           String),
    Column("give_player_ids",    Text,    nullable=False),    # JSON array
    Column("receive_player_ids", Text,    nullable=False),    # JSON array
    Column("decision",           String,  nullable=False),    # 'like' | 'pass'
    Column("created_at",         String),
)

# All members (including the logged-in user) for every league session_init has seen.
# Uniqueness enforced in code (select-then-update-or-insert pattern).
league_members_table = Table("league_members", metadata,
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("league_id",    String,  nullable=False),
    Column("user_id",      String,  nullable=False),
    Column("username",     String),
    Column("display_name", String),
    Column("roster_data",  Text),    # JSON: list of player IDs on this member's team
    Column("updated_at",   String),
    UniqueConstraint("league_id", "user_id", name="uq_league_member"),
)

# Latest ELO snapshot for each player as ranked by each user in each league.
# Replaced atomically (delete + insert) every time a user submits their rankings.
# This is what lets leaguemates see each other's actual valuations.
member_rankings_table = Table("member_rankings", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String,  nullable=False),
    Column("player_id",      String,  nullable=False),
    Column("elo",            Float,   nullable=False),
    Column("updated_at",     String),
    Column("scoring_format", String), # '1qb_ppr' | 'sf_tep' (null = legacy '1qb_ppr')
)

# Created when two users have BOTH swiped "like" on mirrored versions of the
# same trade (user A gives X / receives Y  ↔  user B gives Y / receives X).
#
# Disposition lifecycle:
#   status='pending'  → waiting for one or both users to decide
#   status='accepted' → both users accepted
#   status='declined' → at least one user declined (after both decided)
#
# user_a_decision / user_b_decision: 'accept' | 'decline' | NULL (not yet decided)
trade_matches_table = Table("trade_matches", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("league_id",        String,  nullable=False),
    Column("user_a_id",        String,  nullable=False),   # user who swiped first
    Column("user_b_id",        String,  nullable=False),   # counterparty
    Column("user_a_give",      Text,    nullable=False),   # JSON: player IDs user_a gives
    Column("user_a_receive",   Text,    nullable=False),   # JSON: player IDs user_a receives
    Column("matched_at",       String),
    Column("status",           String,  default="pending"),  # pending|accepted|declined
    Column("user_a_decision",  String),   # accept | decline | NULL
    Column("user_b_decision",  String),   # accept | decline | NULL
    Column("user_a_decided_at", String),
    Column("user_b_decided_at", String),
)

# Composite indexes on (user, league) — both single-league and the new
# cross-league /api/trades/matches/all queries hit one of these. Without
# them, a cross-league scan over a populated table would table-scan.
# `metadata.create_all()` picks these up on fresh DBs; `_migrate_db()`
# below adds them to existing DBs (idempotent CREATE INDEX IF NOT EXISTS).
Index(
    "ix_trade_matches_user_a_league",
    trade_matches_table.c.user_a_id,
    trade_matches_table.c.league_id,
)
Index(
    "ix_trade_matches_user_b_league",
    trade_matches_table.c.user_b_id,
    trade_matches_table.c.league_id,
)


# ---------------------------------------------------------------------------
# Canonical player reference table — synced from Sleeper bulk payload.
# Contains all skill-position players (QB/RB/WR/TE) that are Active or
# incoming prospects (years_exp = None).  Updated on server startup if
# empty or last_synced is older than 24 hours.
# ---------------------------------------------------------------------------

players_table = Table("players", metadata,
    Column("player_id",             String,  primary_key=True),
    Column("full_name",             String),
    Column("first_name",            String),
    Column("last_name",             String),
    Column("position",              String),   # QB | RB | WR | TE
    Column("team",                  String),   # Team abbrev or None (FA)
    Column("age",                   Integer),
    Column("birth_date",            String),   # "YYYY-MM-DD"
    Column("years_exp",             Integer),  # 0 = rookie; None = prospect
    Column("depth_chart_position",  String),   # Same as position; confirms starter
    Column("depth_chart_order",     Integer),  # 1=starter, 2=backup, etc.
    Column("status",                String),   # Active | Inactive | IR | etc.
    Column("injury_status",         String),   # Questionable | Doubtful | Out | IR
    Column("injury_body_part",      String),   # Knee | Hamstring | etc.
    Column("height",                String),   # Inches as string, e.g. "73"
    Column("weight",                String),   # Lbs as string, e.g. "215"
    Column("college",               String),
    Column("search_rank",           Integer),  # Sleeper's internal rank proxy
    Column("adp",                   Float),    # ADP if fetched from Sleeper ADP endpoint
    Column("last_synced",           String),   # ISO timestamp of last sync
)


# Stores each user's team-building outlook per league.
# Controls the score multiplier applied during trade card generation:
#   championship | contender | rebuilder | jets | not_sure
league_preferences_table = Table("league_preferences", metadata,
    Column("id",                  Integer, primary_key=True, autoincrement=True),
    Column("user_id",             String,  nullable=False),
    Column("league_id",           String,  nullable=False),
    Column("team_outlook",        String,  nullable=False),
    Column("acquire_positions",   Text,    default="[]"),  # JSON array e.g. ["WR","TE"]
    Column("trade_away_positions",Text,    default="[]"),  # JSON array e.g. ["QB"]
    Column("updated_at",          String),
    UniqueConstraint("user_id", "league_id", name="uq_league_pref"),
)


# ---------------------------------------------------------------------------
# Draft pick assets
# ---------------------------------------------------------------------------
# Every dynasty draft pick (traded or original) across all upcoming seasons.
#
# pick_id format:  "{league_id}_{season}_{round}_{original_roster_id}"
# Uniqueness guarantee: at most one record per (pick_id) — safe to re-sync.
#
# Ownership resolution:
#   Sleeper /v1/league/<id>/traded_picks gives traded picks only.
#   We generate the full pick grid (original picks per team per season) and
#   overlay the traded picks to determine the current owner of each pick.
#
# pick_value: dynasty fantasy value computed at sync time.
#   See compute_pick_value() below for the formula.
# ---------------------------------------------------------------------------

draft_picks_table = Table("draft_picks", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("pick_id",           String,  nullable=False),   # unique per pick
    Column("league_id",         String,  nullable=False),
    Column("season",            Integer, nullable=False),
    Column("round",             Integer, nullable=False),   # 1 / 2 / 3
    Column("owner_user_id",     String),                    # current owner (user_id)
    Column("owner_username",    String),
    Column("original_roster_id", String),                   # original team's Sleeper roster_id
    Column("original_user_id",  String),                    # original team's user_id
    Column("original_username", String),                    # original team display name
    Column("is_traded",         Integer, default=0),        # 1 if ownership changed
    Column("pick_value",        Float),                     # computed dynasty value
    Column("synced_at",         String),
    UniqueConstraint("pick_id", name="uq_draft_pick_id"),
)

# ---------------------------------------------------------------------------
# notifications_table — in-app notification inbox
# ---------------------------------------------------------------------------
#
# type: one of 'trade_match', 'trade_accepted', 'trade_declined'
# metadata_json: JSON-encoded dict with context fields, e.g.:
#   { "match_id": 42, "partner_username": "joe", "give": ["CeeDee Lamb"], "receive": ["Tyreek Hill"] }
# is_read: 0 = unread, 1 = read
# ---------------------------------------------------------------------------

notifications_table = Table("notifications", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("user_id",       String,  nullable=False),
    Column("type",          String,  nullable=False),   # trade_match | trade_accepted | trade_declined
    Column("title",         String),
    Column("body",          String),
    Column("metadata_json", Text,    default="{}"),
    Column("is_read",       Integer, default=0),        # 0 = unread, 1 = read
    Column("created_at",    String),
)

# ---------------------------------------------------------------------------
# Agent 1 additions — user_player_skips
# ---------------------------------------------------------------------------
# Persistent skip/dismiss decisions:
#   - Trios page: "I don't know this player" button
#   - Positional tiers page: × dismiss on unassigned cards
# Scoped per (user, player, scoring_format). Skipped players are filtered out
# of future trios and the unassigned pool for that format. No ELO update is
# written, so the signal does not pollute the ranking engine.
# ---------------------------------------------------------------------------

user_player_skips_table = Table("user_player_skips", metadata,
    Column("user_id",        String, primary_key=True, nullable=False),
    Column("player_id",      String, primary_key=True, nullable=False),
    Column("scoring_format", String, primary_key=True, nullable=False),
    Column("skipped_at",     String),
)

# ---------------------------------------------------------------------------
# elo_history — append-only log used by the Trends tab (Agent 2)
# ---------------------------------------------------------------------------
# One row per (user, league, player, format, snapshot_at).  Written on every
# `save_ranking_swipes` call — only for players whose ELO actually changed in
# this submission — so the Risers/Fallers chart has fresh data without a
# daily cron.  Small enough (a few KB per submit) that we don't worry about
# pruning in v1; a future maintenance job can compact snapshots older than
# 90 days.
# ---------------------------------------------------------------------------

elo_history_table = Table("elo_history", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String),                       # nullable — global rankings too
    Column("player_id",      String,  nullable=False),
    Column("scoring_format", String,  nullable=False),      # '1qb_ppr' | 'sf_tep'
    Column("elo",            Float,   nullable=False),
    Column("snapshot_at",    String,  nullable=False),      # ISO UTC
)

# ---------------------------------------------------------------------------
# model_config — runtime-tunable multiplier constants
# ---------------------------------------------------------------------------
# Stores every hardcoded constant used by the trade/ranking engine so they
# can be adjusted at runtime without touching code.
#
# key:         unique string identifier (snake_case)
# value:       numeric value (REAL)
# description: human-readable explanation of what this constant does
# ---------------------------------------------------------------------------

model_config_table = Table("model_config", metadata,
    Column("key",         String, primary_key=True),
    Column("value",       Float,  nullable=False),
    Column("description", String),
)

# ---------------------------------------------------------------------------
# Agent 6 additions — wrapped_events
# ---------------------------------------------------------------------------
# Silent event stream powering the "Fantasy Trade Wrapped" end-of-season recap.
# Every row captures a single user action with an opaque JSON payload.
# event_type is one of:
#   swipe | trade_match | trade_accepted | trade_declined |
#   tier_save | ranking_reorder | league_sync
# ---------------------------------------------------------------------------

wrapped_events_table = Table("wrapped_events", metadata,
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("user_id",      String),
    Column("league_id",    String),
    Column("season",       Integer, default=2026),
    Column("event_type",   String),
    Column("payload_json", Text),
    Column("created_at",   String),
)

# ---------------------------------------------------------------------------
# user_events — append-only log of user activity
# ---------------------------------------------------------------------------
# Every meaningful user action gets one row here (immutable). Hot reads
# (e.g. "when did this user last log in?", "who's been inactive 14 days?")
# read the denormalized `last_*_at` columns on `users` instead — see
# record_event() below for the dual-write.
#
# event_type taxonomy (extend as needed):
#   Session:    signup | login | logout | app_open
#   Ranking:    trio_swipe | tier_save | ranking_complete_first_time |
#               ranking_method_changed
#   Trade:      match_viewed | match_swiped | trade_proposed | counter_sent |
#               trade_accepted | trade_declined | trade_ratified
#   Engagement: push_sent | push_opened | notif_pref_changed | league_synced |
#               wrapped_viewed
#
# Device fields are snapshots at the time of the event — sourced from
# X-Device / X-OS-Version / X-App-Version request headers.
user_events_table = Table("user_events", metadata,
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("user_id",      String,  nullable=False, index=True),
    Column("event_type",   String,  nullable=False),
    Column("occurred_at",  String,  nullable=False),    # ISO UTC
    Column("league_id",    String),
    Column("session_id",   String),
    Column("device_type",  String),                     # 'iphone' | 'ipad' | 'macos' | 'web' | 'extension'
    Column("os_version",   String),                     # '17.4' | '18.1' | etc.
    Column("app_version",  String),                     # '1.2.3'
    Column("source",       String),                     # 'mobile' | 'web' | 'api' | 'cron'
    Column("props",        Text),                       # JSON — event-specific extras
    Index("ix_user_events_user_occurred", "user_id", "occurred_at"),
    Index("ix_user_events_type_occurred", "event_type", "occurred_at"),
)

# ── M5 Push additions — device_tokens ─────────────────────────────────
# Stores Expo push tokens so the match-create hook in server.py can send
# a push to both participants when a mutual trade match is persisted.
# Upsert on (user_id, device_token) — the same pair is idempotent; a
# user re-signing in on the same device refreshes last_seen_at only.
device_tokens_table = Table("device_tokens", metadata,
    Column("user_id",      String, nullable=False, index=True),
    Column("device_token", String, nullable=False, primary_key=True),
    Column("platform",     String, nullable=False),   # 'ios' | 'android'
    Column("created_at",   String),
    Column("last_seen_at", String),
)

# Default values seeded on first run.  Only inserted if the key doesn't
# already exist (INSERT OR IGNORE) so manual overrides survive re-deploys.
_MODEL_CONFIG_DEFAULTS = [
    # ── Team Outlook age thresholds ──────────────────────────────────────
    ("vet_age",               27,     "Age threshold (≥) for 'veteran' in championship/contender outlook"),
    ("youth_age",             26,     "Age threshold (≤) for 'youth' in rebuilder outlook"),
    ("jets_age",              25,     "Extreme youth threshold (≤) for NY Jets outlook"),
    # ── Team Outlook score multipliers ───────────────────────────────────
    ("boost_strong",          1.50,   "Strong boost multiplier (e.g. championship receiving vets)"),
    ("boost_moderate",        1.25,   "Moderate boost multiplier (e.g. contender receiving vets)"),
    ("neutral",               1.00,   "Neutral multiplier — no adjustment"),
    ("penalty_soft",          0.75,   "Soft penalty (contender receiving youth for vets)"),
    ("penalty_mod",           0.60,   "Moderate penalty (championship/rebuilder wrong direction)"),
    ("penalty_heavy",         0.30,   "Heavy penalty (NY Jets receiving players ≥26)"),
    # ── KTC dynasty value curve ───────────────────────────────────────────
    ("ktc_k",                 0.0126, "Exponential decay rate for KTC dynasty value curve"),
    ("ktc_max",           10000.0,    "Maximum KTC value (rank 1 player)"),
    ("ktc_fallback_rank",   300.0,    "Rank used when a player has no search_rank in DB"),
    # ── Package diminishing-returns weights (up to 5 players) ─────────────
    ("package_weight_1",      1.00,   "Value weight for 1st (best) player in a trade package"),
    ("package_weight_2",      0.75,   "Value weight for 2nd player in a trade package"),
    ("package_weight_3",      0.55,   "Value weight for 3rd player in a trade package"),
    ("package_weight_4",      0.40,   "Value weight for 4th player in a trade package"),
    ("package_weight_5",      0.28,   "Value weight for 5th player in a trade package"),
    # ── Positional preference multipliers ────────────────────────────────
    ("pos_acquire_bonus",     0.20,   "+N% per received player whose position is in acquire_positions"),
    ("pos_tradeaway_bonus",   0.15,   "+N% per given player whose position is in trade_away_positions"),
    ("pos_conflict_penalty",  0.15,   "-N% per received player whose position the user wants to shed"),
    ("pos_multiplier_cap",    2.00,   "Maximum composite multiplier from positional preferences"),
    # ── TradeService scoring thresholds ──────────────────────────────────
    ("min_mismatch_score",   40.0,    "Minimum raw mismatch score to surface a trade card"),
    ("max_value_ratio",       2.5,    "Maximum consensus value ratio between give/receive sides"),
    ("mismatch_weight",       0.70,   "Weight of mismatch component in composite trade score"),
    ("fairness_weight",       0.30,   "Weight of fairness component in composite trade score"),
    ("max_candidates",      500.0,    "Max candidate trades evaluated per opponent before sorting"),
    # ── ELO K-factors ────────────────────────────────────────────────────
    ("elo_k",                32.0,    "K-factor for a direct player ranking swipe"),
    ("trade_k_like",          8.0,    "K-factor for a trade 'Interested' swipe (~25% of elo_k)"),
    ("trade_k_pass",          4.0,    "K-factor for a trade 'Pass' swipe (~12% of elo_k)"),
    ("trade_k_accept",       20.0,    "K-factor when both parties accept a trade match"),
    ("trade_k_decline_correction", 20.0,
                                     "K-factor for reversal when a user declines after 'Interested' swipe"),
    # ── Tier Engine ──────────────────────────────────────────────────────
    ("tier_engine_enabled",    1.0,    "Feature flag: 1=tier-based trio filtering, 0=legacy (full pool)"),
    ("smart_matchup_enabled",  1.0,    "Feature flag: 1=Claude-powered matchup selection, 0=algorithmic only"),
    ("tier_size",             24.0,    "Players per tier in pre-unlock phase (top N by seed Elo per position)"),
    ("mix_in_rate_base",       0.35,   "Base probability of including a lower-tier player post-unlock"),
    ("mix_in_rate_max",        0.80,   "Maximum mix-in probability as top-tier comparisons saturate"),
    ("mix_in_saturation_pct",  0.70,   "Comparison saturation % at which mix-in rate reaches max"),
    ("mix_in_pre_unlock_start", 5.0,   "Interaction count at which pre-unlock mix-in begins"),
    # ── Trade ELO gap filter ─────────────────────────────────────────────
    ("trade_elo_gap_max",    250.0,   "Max user-ELO gap between give/receive sides before rejecting a trade (0=disabled)"),
    # ── Agent A8 — trade-math adjustments (flag-gated) ───────────────────
    ("qb_tax_rate",              0.075, "QB tax: % penalty to side receiving a premium QB without giving one back"),
    ("star_tax_per_tier_gap",    0.10,  "Star tax: % penalty per tier gap beyond 1 between top assets"),
    ("star_tax_elite_multiplier", 1.5,  "Star tax: multiplier on penalty when the higher-tier star is Tier 1 (elite)"),
    ("roster_spot_penalty",      0.05,  "Roster clogger: % penalty per extra roster spot used"),
    ("roster_clogger_penalty",   0.10,  "Roster clogger: ADDITIONAL % penalty per player beyond 2 for 3+ one-way trades"),
    ("roster_clogger_threshold", 3.0,   "Roster clogger: minimum one-side player count that triggers the clogger tag"),
]


# ---------------------------------------------------------------------------
# Initialisation — called once on server startup
# ---------------------------------------------------------------------------

def _migrate_db() -> None:
    """
    Add columns that may be missing from older DB schemas.
    Each ALTER TABLE is wrapped in try/except so it's idempotent — safe to
    call on a fresh DB or one that already has all columns.

    Also seeds model_config with default values (INSERT OR IGNORE so that
    any manually-tuned rows survive re-deploys).
    """
    migration_cols = [
        ("trade_matches",      "user_a_decision",      "VARCHAR"),
        ("trade_matches",      "user_b_decision",      "VARCHAR"),
        ("trade_matches",      "user_a_decided_at",    "VARCHAR"),
        ("trade_matches",      "user_b_decided_at",    "VARCHAR"),
        ("league_preferences", "acquire_positions",    "TEXT"),
        ("league_preferences", "trade_away_positions", "TEXT"),
        ("users",              "ranking_method",        "VARCHAR"),
        ("users",              "tiers_saved",           "TEXT"),
        ("users",              "tier_overrides",        "TEXT"),
        # Dual-format support (1QB PPR + SF TEP)
        ("swipe_decisions",    "scoring_format",        "VARCHAR"),
        ("member_rankings",    "scoring_format",        "VARCHAR"),
        ("leagues",            "default_scoring",       "VARCHAR"),
        ("users",              "invited_by",            "VARCHAR"),
        ("users",              "unlocked_formats",      "TEXT"),
        # Agent 4 additions — referral receipt feature reuses the existing
        # `notifications` table (no new columns needed). The new notification
        # `type` value is 'referral_joined'; see push_notification() below.
        # ── User-event denormalized hot-read columns (see user_events_table) ──
        # These mirror MAX(occurred_at) for specific event_types so notification
        # gating + re-engagement queries don't scan the full event log.
        ("users",              "last_active_at",        "VARCHAR"),
        ("users",              "last_login_at",         "VARCHAR"),
        ("users",              "last_rank_at",          "VARCHAR"),
        ("users",              "last_match_seen_at",    "VARCHAR"),
        ("users",              "last_trade_proposed_at", "VARCHAR"),
        ("users",              "last_push_sent_at",     "VARCHAR"),
        ("users",              "signup_at",             "VARCHAR"),
        ("users",              "events_count",          "INTEGER"),
        # Most-recent device snapshot — overwritten on every event
        ("users",              "last_device_type",      "VARCHAR"),
        ("users",              "last_os_version",       "VARCHAR"),
        ("users",              "last_app_version",      "VARCHAR"),
    ]
    # Each ALTER TABLE gets its own transaction so a "column already exists"
    # failure doesn't abort the whole block. PostgreSQL (unlike SQLite) marks the
    # entire transaction as aborted on any error — even if Python catches it.
    for table, col, col_type in migration_cols:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        except Exception:
            pass   # column already exists — safe to ignore

    # Backfill: tag existing rows with '1qb_ppr' format since that was the only one
    _backfill_dual_format()

    # ── Agent 1 additions — user_player_skips ─────────────────────────────
    # The table is created by metadata.create_all(); this block is for any
    # future additive ALTERs to that table. Kept idempotent like the rest.
    _agent1_skip_migrations = [
        # (table, column, type) — currently none; placeholder for future work
    ]
    for table, col, col_type in _agent1_skip_migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        except Exception:
            pass

    # ── Multi-league refactor: composite indexes on trade_matches ─────────
    # Existing tables won't have the indexes declared on trade_matches_table
    # above, so create them here idempotently. Postgres ≥9.5 + SQLite ≥3.3
    # both support `CREATE INDEX IF NOT EXISTS`. Each is wrapped in its own
    # try/except so a partial failure (e.g. concurrent migration) doesn't
    # cascade.
    _trade_match_indexes = [
        ("ix_trade_matches_user_a_league", "trade_matches", "user_a_id, league_id"),
        ("ix_trade_matches_user_b_league", "trade_matches", "user_b_id, league_id"),
    ]
    for idx_name, tbl, cols in _trade_match_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"
                ))
        except Exception:
            pass

    # Seed model_config defaults in a single clean transaction.
    with engine.begin() as conn:
        for key, value, description in _MODEL_CONFIG_DEFAULTS:
            if DATABASE_URL.startswith("sqlite"):
                conn.execute(text(
                    "INSERT OR IGNORE INTO model_config (key, value, description) "
                    "VALUES (:key, :value, :description)"
                ), {"key": key, "value": value, "description": description})
            else:
                conn.execute(text(
                    "INSERT INTO model_config (key, value, description) "
                    "VALUES (:key, :value, :description) "
                    "ON CONFLICT (key) DO NOTHING"
                ), {"key": key, "value": value, "description": description})


# Shared constants for dual-format support.
# Must match backend.data_loader.SCORING_FORMATS and the frontend's
# FORMAT_KEYS in web/js/app.js.
SCORING_FORMATS = ("1qb_ppr", "sf_tep")
DEFAULT_SCORING = "1qb_ppr"


def _backfill_dual_format() -> None:
    """
    One-time backfill after dual-format migration:

    1. Tag legacy rows in swipe_decisions / member_rankings with '1qb_ppr'
       (that was the only format in use before).
    2. Rewrite any legacy single-state JSON in users.tiers_saved and
       users.tier_overrides into the new {format: state} shape.
    3. Default users.unlocked_formats to '[]' where null.

    All operations are idempotent and safe to run on every startup.
    """
    try:
        with engine.begin() as conn:
            # Tag legacy swipe rows
            conn.execute(text(
                "UPDATE swipe_decisions SET scoring_format = :fmt "
                "WHERE scoring_format IS NULL"
            ), {"fmt": DEFAULT_SCORING})
            # Tag legacy member_rankings rows
            conn.execute(text(
                "UPDATE member_rankings SET scoring_format = :fmt "
                "WHERE scoring_format IS NULL"
            ), {"fmt": DEFAULT_SCORING})
    except Exception as e:
        # Logging via print since this module doesn't have `log`
        print(f"[backfill] swipe/member scoring_format tag failed: {e}")

    # Rewrite legacy JSON on users rows — one user at a time, skip rows
    # already in the new shape.
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    users_table.c.sleeper_user_id,
                    users_table.c.tiers_saved,
                    users_table.c.tier_overrides,
                    users_table.c.unlocked_formats,
                )
            ).fetchall()

        for row in rows:
            updates: dict = {}

            # tiers_saved: legacy = ["RB","WR"]; new = {"1qb_ppr": [...], "sf_tep": []}
            ts = row.tiers_saved
            if ts:
                try:
                    parsed = json.loads(ts)
                    if isinstance(parsed, list):
                        updates["tiers_saved"] = json.dumps({
                            "1qb_ppr": parsed,
                            "sf_tep":  [],
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

            # tier_overrides: legacy = {pid: elo}; new = {"1qb_ppr": {...}, "sf_tep": {}}
            to = row.tier_overrides
            if to:
                try:
                    parsed = json.loads(to)
                    # Detect legacy: flat dict of {pid: float}, no format keys
                    if isinstance(parsed, dict) and not any(
                        k in parsed for k in SCORING_FORMATS
                    ):
                        updates["tier_overrides"] = json.dumps({
                            "1qb_ppr": parsed,
                            "sf_tep":  {},
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

            # unlocked_formats: default to empty list if null
            if row.unlocked_formats is None:
                updates["unlocked_formats"] = "[]"

            if updates:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            update(users_table)
                            .where(users_table.c.sleeper_user_id == row.sleeper_user_id)
                            .values(**updates)
                        )
                except Exception as e:
                    print(f"[backfill] user {row.sleeper_user_id} update failed: {e}")
    except Exception as e:
        print(f"[backfill] users JSON rewrite failed: {e}")


def init_db() -> None:
    """Create all tables if they don't exist, then apply incremental migrations."""
    metadata.create_all(engine)
    _migrate_db()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# User-event logging
# ---------------------------------------------------------------------------
# Maps event_type → the column on `users` that should be bumped when this
# event fires. Events not in this map only get a row in user_events (no
# denorm pointer is updated).
_EVENT_TO_USER_COL: dict[str, str] = {
    "signup":                       "signup_at",
    "login":                        "last_login_at",
    "app_open":                     "last_active_at",
    "trio_swipe":                   "last_rank_at",
    "tier_save":                    "last_rank_at",
    "ranking_complete_first_time":  "last_rank_at",
    "match_viewed":                 "last_match_seen_at",
    "trade_proposed":               "last_trade_proposed_at",
    "counter_sent":                 "last_trade_proposed_at",
    "push_sent":                    "last_push_sent_at",
}


def touch_user_activity(
    user_id: str,
    *,
    device_type: str | None = None,
    os_version:  str | None = None,
    app_version: str | None = None,
) -> None:
    """Cheap denormalized update — bumps users.last_active_at + device snapshot
    columns. Called by the request middleware on every authed API call so we
    don't have to write a `user_events` row per request.

    Use record_event() instead when logging a discrete user action.
    """
    if not user_id:
        return
    updates: dict = {"last_active_at": _now()}
    if device_type:
        updates["last_device_type"] = device_type
    if os_version:
        updates["last_os_version"] = os_version
    if app_version:
        updates["last_app_version"] = app_version
    try:
        with engine.begin() as conn:
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == user_id)
                .values(**updates)
            )
    except Exception as e:
        print(f"[touch_user_activity] {user_id} failed: {e}")


def record_event(
    user_id: str,
    event_type: str,
    *,
    league_id:   str | None = None,
    session_id:  str | None = None,
    device_type: str | None = None,
    os_version:  str | None = None,
    app_version: str | None = None,
    source:      str | None = None,
    props:       dict | None = None,
) -> None:
    """Append one row to user_events AND bump the matching users.last_*_at
    column (and device snapshot columns) in a single transaction.

    Always inserts a new row — never overwrites prior events. The denorm
    columns on `users` are pointers to the most recent event of each type
    so notification gating queries don't have to scan the full log.

    Failures are logged and swallowed — event logging must never break the
    surrounding business logic.
    """
    if not user_id or not event_type:
        return
    now = _now()
    try:
        with engine.begin() as conn:
            conn.execute(
                insert(user_events_table).values(
                    user_id     = user_id,
                    event_type  = event_type,
                    occurred_at = now,
                    league_id   = league_id,
                    session_id  = session_id,
                    device_type = device_type,
                    os_version  = os_version,
                    app_version = app_version,
                    source      = source,
                    props       = json.dumps(props) if props else None,
                )
            )
            # Build the denorm UPDATE: always bumps last_active_at + events_count,
            # plus the event-specific pointer column when one is mapped, plus the
            # device snapshot columns when those headers were sent.
            user_updates: dict = {"last_active_at": now}
            ptr_col = _EVENT_TO_USER_COL.get(event_type)
            if ptr_col and ptr_col != "last_active_at":
                user_updates[ptr_col] = now
            if device_type:
                user_updates["last_device_type"] = device_type
            if os_version:
                user_updates["last_os_version"] = os_version
            if app_version:
                user_updates["last_app_version"] = app_version
            # events_count: portable increment via a subquery-free expression.
            # Using SQL expression here so we don't need to SELECT first.
            user_updates["events_count"] = (
                # COALESCE so the first event ever sets it to 1 instead of NULL+1.
                text("COALESCE(events_count, 0) + 1")
            )
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == user_id)
                .values(**user_updates)
            )
    except Exception as e:
        print(f"[record_event] {user_id}/{event_type} failed: {e}")


def load_user_events(
    user_id: str,
    *,
    event_type: str | None = None,
    limit:      int = 100,
) -> list[dict]:
    """Return the user's most-recent events (newest first), optionally
    filtered to one event_type. Returns deserialized props.
    """
    try:
        with engine.begin() as conn:
            stmt = (
                select(user_events_table)
                .where(user_events_table.c.user_id == user_id)
                .order_by(user_events_table.c.occurred_at.desc())
                .limit(limit)
            )
            if event_type:
                stmt = stmt.where(user_events_table.c.event_type == event_type)
            rows = conn.execute(stmt).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r._mapping)
            if d.get("props"):
                try:
                    d["props"] = json.loads(d["props"])
                except Exception:
                    pass
            out.append(d)
        return out
    except Exception as e:
        print(f"[load_user_events] {user_id} failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Model config operations
# ---------------------------------------------------------------------------

def get_config() -> dict[str, float]:
    """
    Return all model_config rows as a flat dict  { key: value }.
    Falls back to the hardcoded defaults if the table is empty or missing.
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(select(model_config_table)).fetchall()
        if rows:
            return {row.key: row.value for row in rows}
    except Exception:
        pass
    # Fallback: build from defaults (should never happen in normal operation)
    return {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}


def set_config(key: str, value: float) -> dict:
    """
    Update a single model_config value.  Returns the updated row as a dict.
    Raises KeyError if the key doesn't exist (we don't allow ad-hoc keys).
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(model_config_table).where(model_config_table.c.key == key)
        ).fetchone()
        if existing is None:
            raise KeyError(f"Unknown config key: {key!r}")
        conn.execute(
            update(model_config_table)
            .where(model_config_table.c.key == key)
            .values(value=value)
        )
    return {"key": key, "value": value}


def list_config() -> list[dict]:
    """Return all model_config rows as a list of dicts (key, value, description)."""
    with engine.begin() as conn:
        rows = conn.execute(
            select(model_config_table).order_by(model_config_table.c.key)
        ).fetchall()
    return [{"key": r.key, "value": r.value, "description": r.description} for r in rows]


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

def upsert_user(
    sleeper_user_id: str,
    username: str = "",
    display_name: str = "",
    avatar: str | None = None,
    invited_by: str | None = None,
) -> None:
    """Insert a new user or update their display fields if they already exist.

    `invited_by` is only set on INSERT — repeat logins never overwrite the
    original referrer, so referral attribution is immutable once recorded.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(users_table).where(
                users_table.c.sleeper_user_id == sleeper_user_id
            )
        ).fetchone()

        if existing:
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == sleeper_user_id)
                .values(username=username, display_name=display_name, avatar=avatar)
            )
        else:
            values: dict = {
                "sleeper_user_id": sleeper_user_id,
                "username":        username,
                "display_name":    display_name,
                "avatar":          avatar,
                "created_at":      _now(),
            }
            if invited_by:
                values["invited_by"] = invited_by
            conn.execute(insert(users_table).values(**values))


def set_ranking_method(user_id: str, method: str) -> None:
    """Save the user's chosen ranking method ('trio', 'manual', 'tiers')."""
    with engine.begin() as conn:
        conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(ranking_method=method)
        )


def get_ranking_method(user_id: str) -> str | None:
    """Return the user's stored ranking method, or None if not set."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.ranking_method).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        return row.ranking_method if row else None


def _parse_per_format_json(raw: str | None, is_list: bool) -> dict:
    """
    Parse a per-format JSON column. Returns a dict keyed by SCORING_FORMATS
    with the default empty value for any missing format.
    """
    empty = [] if is_list else {}
    out: dict = {fmt: (list(empty) if is_list else dict(empty)) for fmt in SCORING_FORMATS}
    if not raw:
        return out
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return out
    if isinstance(parsed, dict):
        for fmt in SCORING_FORMATS:
            val = parsed.get(fmt)
            if is_list and isinstance(val, list):
                out[fmt] = val
            elif not is_list and isinstance(val, dict):
                out[fmt] = val
    return out


def save_tiers_position(
    user_id: str,
    position: str,
    scoring_format: str = DEFAULT_SCORING,
) -> list[str]:
    """Mark a position as tier-saved for this user in the given format.
    Returns the updated list of saved positions for that format.

    Uses SELECT FOR UPDATE on Postgres (and a serialized transaction on SQLite)
    to prevent the read-modify-write race where two concurrent saves for
    different positions could each overwrite the other.
    """
    is_postgres = not DATABASE_URL.startswith("sqlite")
    with engine.begin() as conn:
        if is_postgres:
            row = conn.execute(
                text("SELECT tiers_saved FROM users WHERE sleeper_user_id = :uid FOR UPDATE"),
                {"uid": user_id},
            ).fetchone()
        else:
            row = conn.execute(
                select(users_table.c.tiers_saved).where(
                    users_table.c.sleeper_user_id == user_id
                )
            ).fetchone()

        all_saved = _parse_per_format_json(row.tiers_saved if row else None, is_list=True)
        saved = all_saved.get(scoring_format, [])
        if position not in saved:
            saved.append(position)
            all_saved[scoring_format] = saved
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == user_id)
                .values(tiers_saved=json.dumps(all_saved))
            )
        # Agent 6 — wrapped collector hook (non-throwing)
        try:
            from .wrapped_collector import record_event
            record_event(user_id, None, "tier_save",
                         {"position": position, "scoring_format": scoring_format})
        except Exception:
            pass
        return saved


def get_tiers_saved(
    user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> list[str]:
    """Return list of positions with saved tiers for this user + format."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.tiers_saved).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    all_saved = _parse_per_format_json(row.tiers_saved if row else None, is_list=True)
    return all_saved.get(scoring_format, [])


def save_tier_overrides(
    user_id: str,
    overrides: dict[str, float],
    scoring_format: str = DEFAULT_SCORING,
) -> None:
    """
    Persist the user's tier/reorder override map for one scoring format.
    Other formats' overrides are left untouched.
    """
    is_postgres = not DATABASE_URL.startswith("sqlite")
    with engine.begin() as conn:
        if is_postgres:
            row = conn.execute(
                text("SELECT tier_overrides FROM users WHERE sleeper_user_id = :uid FOR UPDATE"),
                {"uid": user_id},
            ).fetchone()
        else:
            row = conn.execute(
                select(users_table.c.tier_overrides).where(
                    users_table.c.sleeper_user_id == user_id
                )
            ).fetchone()
        all_overrides = _parse_per_format_json(row.tier_overrides if row else None, is_list=False)
        # Cast ELO values to float so JSON stays clean
        all_overrides[scoring_format] = {pid: float(elo) for pid, elo in overrides.items()}
        conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(tier_overrides=json.dumps(all_overrides))
        )


def load_tier_overrides(
    user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict[str, float]:
    """Return {player_id: elo_float} overrides for this user + format."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.tier_overrides).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    all_overrides = _parse_per_format_json(row.tier_overrides if row else None, is_list=False)
    fmt_overrides = all_overrides.get(scoring_format, {})
    try:
        return {k: float(v) for k, v in fmt_overrides.items()}
    except (TypeError, ValueError):
        return {}


def mark_format_unlocked(user_id: str, scoring_format: str) -> None:
    """Add `scoring_format` to the user's unlocked_formats list if not already present.
    Monotonic — never removes a format once unlocked."""
    is_postgres = not DATABASE_URL.startswith("sqlite")
    with engine.begin() as conn:
        if is_postgres:
            row = conn.execute(
                text("SELECT unlocked_formats FROM users WHERE sleeper_user_id = :uid FOR UPDATE"),
                {"uid": user_id},
            ).fetchone()
        else:
            row = conn.execute(
                select(users_table.c.unlocked_formats).where(
                    users_table.c.sleeper_user_id == user_id
                )
            ).fetchone()
        unlocked: list = []
        if row and row.unlocked_formats:
            try:
                parsed = json.loads(row.unlocked_formats)
                if isinstance(parsed, list):
                    unlocked = parsed
            except (json.JSONDecodeError, TypeError):
                unlocked = []
        if scoring_format not in unlocked:
            unlocked.append(scoring_format)
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == user_id)
                .values(unlocked_formats=json.dumps(unlocked))
            )


def get_unlocked_formats(user_id: str) -> list[str]:
    """Return the list of scoring formats the user has unlocked trade finder in."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.unlocked_formats).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    if row and row.unlocked_formats:
        try:
            parsed = json.loads(row.unlocked_formats)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# ---------------------------------------------------------------------------
# League operations
# ---------------------------------------------------------------------------

def upsert_league(
    league_id: str,
    user_id: str,
    name: str,
    season: str,
    user_player_ids: list[str],
    opponent_rosters: list[dict],
) -> None:
    """Insert or update a league record with the latest roster snapshot."""
    roster_json   = json.dumps(user_player_ids)
    opponent_json = json.dumps(opponent_rosters)
    now = _now()

    with engine.begin() as conn:
        existing = conn.execute(
            select(leagues_table).where(
                (leagues_table.c.sleeper_league_id == league_id) &
                (leagues_table.c.user_id == user_id)
            )
        ).fetchone()

        if existing:
            conn.execute(
                update(leagues_table)
                .where(
                    (leagues_table.c.sleeper_league_id == league_id) &
                    (leagues_table.c.user_id == user_id)
                )
                .values(
                    name=name,
                    roster_data=roster_json,
                    opponent_data=opponent_json,
                    updated_at=now,
                )
            )
        else:
            conn.execute(insert(leagues_table).values(
                sleeper_league_id=league_id,
                user_id=user_id,
                name=name,
                season=season,
                roster_data=roster_json,
                opponent_data=opponent_json,
                created_at=now,
                updated_at=now,
            ))
    # Agent 6 — wrapped collector hook (non-throwing)
    try:
        from .wrapped_collector import record_event
        record_event(user_id, league_id, "league_sync",
                     {"name": name, "season": season,
                      "roster_size": len(user_player_ids)})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Swipe decision operations
# ---------------------------------------------------------------------------

def save_ranking_swipes(
    user_id: str,
    ordered_ids: list[str],
    k_factor: float = 32.0,
    scoring_format: str = DEFAULT_SCORING,
) -> None:
    """
    Decompose a 3-player (or N-player) ranking into pairwise comparisons
    and persist each to the DB, tagged with the current scoring_format.

    Mirrors the decomposition in RankingService.record_ranking() so that
    replaying these rows recreates identical ELO state.
    """
    now  = _now()
    rows = []
    for i in range(len(ordered_ids)):
        for j in range(i + 1, len(ordered_ids)):
            rows.append({
                "user_id":          user_id,
                "winner_player_id": ordered_ids[i],
                "loser_player_id":  ordered_ids[j],
                "decision_type":    "rank",
                "k_factor":         k_factor,
                "created_at":       now,
                "scoring_format":   scoring_format,
            })
    if rows:
        with engine.begin() as conn:
            conn.execute(insert(swipe_decisions_table), rows)
        # Agent 6 — wrapped collector hook (non-throwing)
        try:
            from .wrapped_collector import record_event
            record_event(user_id, None, "swipe",
                         {"count": len(rows), "scoring_format": scoring_format})
        except Exception:
            pass


def save_trade_swipes(
    user_id: str,
    winner_ids: list[str],
    loser_ids: list[str],
    k_factor: float,
    decision_type: str = "trade",
    scoring_format: str = DEFAULT_SCORING,
) -> None:
    """
    Persist pairwise trade-signal swipes.

    Mirrors the decomposition in RankingService.record_trade_signal() so
    replaying these rows recreates identical ELO state for trade signals.

    decision_type: 'trade' (default) | 'disposition' — both are replayed
    identically (non-rank swipes with stored k_factor); the label is just
    for auditing.
    """
    now  = _now()
    rows = []
    for wid in winner_ids:
        for lid in loser_ids:
            if wid == lid:
                continue
            rows.append({
                "user_id":          user_id,
                "winner_player_id": wid,
                "loser_player_id":  lid,
                "decision_type":    decision_type,
                "k_factor":         k_factor,
                "created_at":       now,
                "scoring_format":   scoring_format,
            })
    if rows:
        with engine.begin() as conn:
            conn.execute(insert(swipe_decisions_table), rows)


def load_swipe_decisions(
    user_id: str,
    scoring_format: str | None = None,
) -> list[dict]:
    """
    Return all stored swipe decisions for a user, in insertion order.
    Used to replay historical rankings into a freshly built RankingService.

    If scoring_format is provided, only returns swipes tagged with that
    format (or the legacy null format, which we treat as '1qb_ppr').
    """
    with engine.connect() as conn:
        q = (
            select(swipe_decisions_table)
            .where(swipe_decisions_table.c.user_id == user_id)
            .order_by(swipe_decisions_table.c.id)
        )
        if scoring_format is not None:
            if scoring_format == DEFAULT_SCORING:
                # Include legacy NULL rows (backfill tags them but be defensive)
                q = q.where(
                    (swipe_decisions_table.c.scoring_format == scoring_format) |
                    (swipe_decisions_table.c.scoring_format.is_(None))
                )
            else:
                q = q.where(swipe_decisions_table.c.scoring_format == scoring_format)
        rows = conn.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Trade decision operations
# ---------------------------------------------------------------------------

def save_trade_decision(
    user_id: str,
    league_id: str,
    trade_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
    decision: str,
) -> None:
    """Persist a high-level trade card decision (like/pass)."""
    with engine.begin() as conn:
        conn.execute(insert(trade_decisions_table).values(
            user_id            = user_id,
            league_id          = league_id,
            trade_id           = trade_id,
            give_player_ids    = json.dumps(give_player_ids),
            receive_player_ids = json.dumps(receive_player_ids),
            decision           = decision,
            created_at         = _now(),
        ))


def load_trade_decisions(
    user_id: str,
    league_id: str | None = None,
    since_days: int | None = None,
) -> list[dict]:
    """
    Load trade decisions for a user, optionally filtered by league and age.
    JSON fields are automatically decoded back to lists.

    since_days: if set, only return decisions from the last N days.
    """
    with engine.connect() as conn:
        q = select(trade_decisions_table).where(
            trade_decisions_table.c.user_id == user_id
        )
        if league_id:
            q = q.where(trade_decisions_table.c.league_id == league_id)
        if since_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
            q = q.where(trade_decisions_table.c.created_at >= cutoff)
        rows = conn.execute(q.order_by(trade_decisions_table.c.id)).fetchall()

    result = []
    for r in rows:
        d = dict(r._mapping)
        d["give_player_ids"]    = json.loads(d["give_player_ids"])
        d["receive_player_ids"] = json.loads(d["receive_player_ids"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# League member operations
# ---------------------------------------------------------------------------

def upsert_league_members(league_id: str, members: list[dict]) -> None:
    """
    Store the full membership snapshot for a league.

    members: list of dicts with keys:
        user_id, username, display_name (optional), player_ids (list)

    Called during session_init so every user who logs into the same league
    contributes their view of the membership roster.
    """
    now = _now()
    with engine.begin() as conn:
        for m in members:
            uid          = str(m.get("user_id", ""))
            username     = m.get("username", "")
            display_name = m.get("display_name", username)
            roster_json  = json.dumps(m.get("player_ids", []))

            existing = conn.execute(
                select(league_members_table).where(
                    (league_members_table.c.league_id == league_id) &
                    (league_members_table.c.user_id   == uid)
                )
            ).fetchone()

            if existing:
                conn.execute(
                    update(league_members_table)
                    .where(
                        (league_members_table.c.league_id == league_id) &
                        (league_members_table.c.user_id   == uid)
                    )
                    .values(
                        username=username,
                        display_name=display_name,
                        roster_data=roster_json,
                        updated_at=now,
                    )
                )
            else:
                conn.execute(insert(league_members_table).values(
                    league_id    = league_id,
                    user_id      = uid,
                    username     = username,
                    display_name = display_name,
                    roster_data  = roster_json,
                    updated_at   = now,
                ))


def load_league_members(league_id: str) -> list[dict]:
    """Return all stored members for a league with their rosters decoded."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(league_members_table).where(
                league_members_table.c.league_id == league_id
            )
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r._mapping)
        try:
            d["player_ids"] = json.loads(d.get("roster_data") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["player_ids"] = []
        result.append(d)
    return result


def set_league_scoring(league_id: str, scoring_format: str) -> None:
    """Save the league's default scoring format (shown on the league summary)."""
    if scoring_format not in SCORING_FORMATS:
        raise ValueError(f"Invalid scoring_format: {scoring_format!r}")
    with engine.begin() as conn:
        # Update ALL leagues rows for this league (there can be multiple user_id rows
        # under the same sleeper_league_id since the leagues table keys on the pair).
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == league_id)
            .values(default_scoring=scoring_format)
        )


def get_league_scoring(league_id: str) -> str:
    """Return the league's default scoring format, defaulting to '1qb_ppr'."""
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.default_scoring)
            .where(leagues_table.c.sleeper_league_id == league_id)
            .limit(1)
        ).fetchone()
    if row and row.default_scoring in SCORING_FORMATS:
        return row.default_scoring
    return DEFAULT_SCORING


def get_league_summary(league_id: str, user_id: str) -> dict:
    """
    Return a rollup for the League Summary page:

    {
        "league_name":              str,
        "default_scoring":          '1qb_ppr' | 'sf_tep',
        "matches_pending":          int,   # current user's pending matches in this league
        "matches_accepted":         int,   # current user's accepted matches in this league
        "leaguemates_total":        int,   # members other than current user
        "leaguemates_joined":       int,   # how many have a users row
        "leaguemates_unlocked_1qb": int,   # how many unlocked 1qb_ppr
        "leaguemates_unlocked_sf":  int,   # how many unlocked sf_tep
    }
    """
    from sqlalchemy import func

    with engine.connect() as conn:
        # League name and default scoring (first row wins)
        league_row = conn.execute(
            select(leagues_table.c.name, leagues_table.c.default_scoring)
            .where(leagues_table.c.sleeper_league_id == league_id)
            .limit(1)
        ).fetchone()
        league_name = league_row.name if league_row else ""
        default_scoring = (
            league_row.default_scoring
            if league_row and league_row.default_scoring in SCORING_FORMATS
            else DEFAULT_SCORING
        )

        # Match counts for the current user
        matches_pending = conn.execute(
            select(func.count()).select_from(trade_matches_table).where(
                (trade_matches_table.c.league_id == league_id) &
                (trade_matches_table.c.status == 'pending') &
                (
                    (trade_matches_table.c.user_a_id == user_id) |
                    (trade_matches_table.c.user_b_id == user_id)
                )
            )
        ).scalar() or 0

        matches_accepted = conn.execute(
            select(func.count()).select_from(trade_matches_table).where(
                (trade_matches_table.c.league_id == league_id) &
                (trade_matches_table.c.status == 'accepted') &
                (
                    (trade_matches_table.c.user_a_id == user_id) |
                    (trade_matches_table.c.user_b_id == user_id)
                )
            )
        ).scalar() or 0

        # Leaguemate IDs excluding current user
        leaguemate_rows = conn.execute(
            select(league_members_table.c.user_id).where(
                (league_members_table.c.league_id == league_id) &
                (league_members_table.c.user_id != user_id)
            )
        ).fetchall()
        leaguemate_ids = [r.user_id for r in leaguemate_rows]
        leaguemates_total = len(leaguemate_ids)

        if leaguemates_total == 0:
            return {
                "league_name":              league_name,
                "default_scoring":          default_scoring,
                "matches_pending":          matches_pending,
                "matches_accepted":         matches_accepted,
                "leaguemates_total":        0,
                "leaguemates_joined":       0,
                "leaguemates_unlocked_1qb": 0,
                "leaguemates_unlocked_sf":  0,
            }

        # Joined = users rows exist for these sleeper_user_ids
        joined_rows = conn.execute(
            select(users_table.c.sleeper_user_id, users_table.c.unlocked_formats).where(
                users_table.c.sleeper_user_id.in_(leaguemate_ids)
            )
        ).fetchall()
        leaguemates_joined = len(joined_rows)

        unlocked_1qb = 0
        unlocked_sf = 0
        for jr in joined_rows:
            if not jr.unlocked_formats:
                continue
            try:
                parsed = json.loads(jr.unlocked_formats)
                if isinstance(parsed, list):
                    if "1qb_ppr" in parsed:
                        unlocked_1qb += 1
                    if "sf_tep" in parsed:
                        unlocked_sf += 1
            except (json.JSONDecodeError, TypeError):
                continue

    return {
        "league_name":              league_name,
        "default_scoring":          default_scoring,
        "matches_pending":          matches_pending,
        "matches_accepted":         matches_accepted,
        "leaguemates_total":        leaguemates_total,
        "leaguemates_joined":       leaguemates_joined,
        "leaguemates_unlocked_1qb": unlocked_1qb,
        "leaguemates_unlocked_sf":  unlocked_sf,
    }


# ---------------------------------------------------------------------------
# Agent A4 additions — per-member unlock states & league activity feed.
# Used by the new /api/league/member-unlock-states and /api/league/activity
# endpoints behind the league.unlock_badges_per_member and
# league.activity_feed flags.
# ---------------------------------------------------------------------------

def load_league_member_unlock_states(league_id: str, exclude_user_id: str | None = None) -> list[dict]:
    """
    Return a per-leaguemate unlock-state list for the League view.

    Each row: {
        "user_id":          str,
        "username":         str,
        "display_name":     str,
        "avatar":           str | None,
        "joined":           bool,          # has a users row
        "unlocked_formats": list[str],     # subset of ('1qb_ppr','sf_tep')
        "unlocked_count":   int,           # 0..2
        "has_ranking_method": bool,        # users.ranking_method is not null
    }

    Rows are sorted: unlocked_count DESC, joined first, display_name ASC.
    """
    with engine.connect() as conn:
        member_rows = conn.execute(
            select(
                league_members_table.c.user_id,
                league_members_table.c.username,
                league_members_table.c.display_name,
            ).where(league_members_table.c.league_id == league_id)
        ).fetchall()

        if exclude_user_id:
            member_rows = [r for r in member_rows if r.user_id != exclude_user_id]

        if not member_rows:
            return []

        member_ids = [r.user_id for r in member_rows]

        user_rows = conn.execute(
            select(
                users_table.c.sleeper_user_id,
                users_table.c.username,
                users_table.c.display_name,
                users_table.c.avatar,
                users_table.c.unlocked_formats,
                users_table.c.ranking_method,
            ).where(users_table.c.sleeper_user_id.in_(member_ids))
        ).fetchall()

    by_id = {r.sleeper_user_id: r for r in user_rows}

    out: list[dict] = []
    for m in member_rows:
        u = by_id.get(m.user_id)
        unlocked: list[str] = []
        joined = False
        avatar = None
        display_name = m.display_name or m.username or ""
        username = m.username or ""
        has_method = False
        if u is not None:
            joined = True
            avatar = u.avatar
            if u.display_name:
                display_name = u.display_name
            if u.username:
                username = u.username
            has_method = bool(u.ranking_method)
            if u.unlocked_formats:
                try:
                    parsed = json.loads(u.unlocked_formats)
                    if isinstance(parsed, list):
                        for fmt in parsed:
                            if fmt in ("1qb_ppr", "sf_tep") and fmt not in unlocked:
                                unlocked.append(fmt)
                except (json.JSONDecodeError, TypeError):
                    pass

        out.append({
            "user_id":            m.user_id,
            "username":           username,
            "display_name":       display_name,
            "avatar":             avatar,
            "joined":             joined,
            "unlocked_formats":   unlocked,
            "unlocked_count":     len(unlocked),
            "has_ranking_method": has_method,
        })

    out.sort(key=lambda r: (
        -r["unlocked_count"],
        0 if r["joined"] else 1,
        (r["display_name"] or "").lower(),
    ))
    return out


def load_league_activity(league_id: str, limit: int = 20) -> list[dict]:
    """
    Pull the most recent wrapped_events for a league and format them as
    human-readable activity-feed entries.

    Returns a list (newest first) of:
        {
            "ts":            ISO timestamp string,
            "emoji":         str,
            "message":       str,
            "actor_user_id": str | None,
            "event_type":    str,
        }
    """
    from datetime import datetime, timezone
    NARRATIVE_TYPES = {
        "trade_match",
        "trade_accepted",
        "trade_declined",
        "tier_save",
        "league_sync",
    }

    with engine.connect() as conn:
        rows = conn.execute(
            select(
                wrapped_events_table.c.user_id,
                wrapped_events_table.c.event_type,
                wrapped_events_table.c.payload_json,
                wrapped_events_table.c.created_at,
            )
            .where(wrapped_events_table.c.league_id == league_id)
            .order_by(wrapped_events_table.c.id.desc())
            .limit(max(limit * 4, 40))
        ).fetchall()

        filtered = [r for r in rows if r.event_type in NARRATIVE_TYPES][:limit]
        if not filtered:
            return []

        user_ids = list({r.user_id for r in filtered if r.user_id})
        user_map: dict[str, dict] = {}
        if user_ids:
            user_rows = conn.execute(
                select(
                    users_table.c.sleeper_user_id,
                    users_table.c.username,
                    users_table.c.display_name,
                    users_table.c.invited_by,
                ).where(users_table.c.sleeper_user_id.in_(user_ids))
            ).fetchall()
            user_map = {
                r.sleeper_user_id: {
                    "username":     r.username or "",
                    "display_name": r.display_name or r.username or "",
                    "invited_by":   r.invited_by or "",
                }
                for r in user_rows
            }

    def _handle_name(uid):
        if not uid:
            return "someone"
        u = user_map.get(uid)
        if not u:
            return "someone"
        return u["username"] or u["display_name"] or "someone"

    def _ago(iso_ts):
        if not iso_ts:
            return "recently"
        try:
            ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        except Exception:
            return "recently"
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = now - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"

    FMT_LABELS = {"1qb_ppr": "1QB PPR", "sf_tep": "SF TEP"}

    out: list[dict] = []
    for r in filtered:
        try:
            payload = json.loads(r.payload_json) if r.payload_json else {}
            if not isinstance(payload, dict):
                payload = {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        actor = _handle_name(r.user_id)
        ago = _ago(r.created_at)
        et = r.event_type
        emoji = "•"
        message = ""

        if et == "trade_accepted":
            emoji = "✅"
            other = _handle_name(payload.get("other_user_id"))
            message = f"✅ @{actor} accepted a trade with @{other} ({ago})"
        elif et == "trade_declined":
            emoji = "✖️"
            other = _handle_name(payload.get("other_user_id"))
            message = f"✖️ @{actor} declined a trade with @{other} ({ago})"
        elif et == "trade_match":
            emoji = "🤝"
            other = _handle_name(payload.get("other_user_id"))
            message = f"🤝 @{actor} matched a trade with @{other} ({ago})"
        elif et == "tier_save":
            emoji = "📋"
            pos = (payload.get("position") or "").upper()
            fmt_key = payload.get("scoring_format") or payload.get("format") or ""
            fmt_lbl = FMT_LABELS.get(fmt_key, "")
            if pos and fmt_lbl:
                message = f"📋 @{actor} saved their {pos} tiers ({fmt_lbl}) ({ago})"
            elif pos:
                message = f"📋 @{actor} saved their {pos} tiers ({ago})"
            else:
                message = f"📋 @{actor} saved their tiers ({ago})"
        elif et == "league_sync":
            u = user_map.get(r.user_id or "", {})
            inviter = u.get("invited_by") if u else ""
            if inviter:
                emoji = "🤝"
                message = f"🤝 @{actor} joined via @{inviter}'s invite ({ago})"
            else:
                emoji = "🔄"
                message = f"🔄 @{actor} synced the league ({ago})"
        else:
            message = f"• @{actor} — {et} ({ago})"

        # If a tier_save also flipped the format to unlocked, surface a
        # separate unlock milestone entry.
        if et == "tier_save" and payload.get("unlocked_format"):
            fmt_key = payload.get("unlocked_format")
            fmt_lbl = FMT_LABELS.get(fmt_key, fmt_key)
            out.append({
                "ts":            r.created_at,
                "emoji":         "🎯",
                "message":       f"🎯 @{actor} unlocked trades in {fmt_lbl} ({ago})",
                "actor_user_id": r.user_id,
                "event_type":    "unlock",
            })

        out.append({
            "ts":            r.created_at,
            "emoji":         emoji,
            "message":       message,
            "actor_user_id": r.user_id,
            "event_type":    et,
        })

    return out[:limit]


def load_local_leagues_for_user(user_id: str) -> list[dict]:
    """
    Return all locally-stored (non-Sleeper) leagues where this user is a member,
    formatted like Sleeper's /user/{id}/leagues/nfl/{year} response.
    Local leagues have non-numeric IDs (e.g. 'test_league_lakeview').
    """
    from sqlalchemy import func
    with engine.connect() as conn:
        member_rows = conn.execute(
            select(league_members_table.c.league_id).where(
                league_members_table.c.user_id == user_id
            )
        ).fetchall()

        local_ids = [r.league_id for r in member_rows if not r.league_id.isdigit()]
        if not local_ids:
            return []

        result = []
        for lid in local_ids:
            league_row = conn.execute(
                select(leagues_table).where(leagues_table.c.sleeper_league_id == lid)
            ).fetchone()
            if not league_row:
                continue
            member_count = conn.execute(
                select(func.count()).select_from(league_members_table).where(
                    league_members_table.c.league_id == lid
                )
            ).scalar() or 0
            result.append({
                "league_id":        lid,
                "name":             league_row.name,
                "total_rosters":    member_count,
                "scoring_settings": {"rec": 1},   # assume PPR
                "status":           "in_season",
                "season":           league_row.season or "2026",
                "_local":           True,
            })
        return result


def load_local_league_rosters(league_id: str) -> list[dict]:
    """
    Return rosters for a local league in Sleeper roster format:
    [{"roster_id": i+1, "owner_id": uid, "players": [...], "league_id": lid}, ...]
    """
    members = load_league_members(league_id)
    return [
        {
            "roster_id": i + 1,
            "owner_id":  m["user_id"],
            "players":   m.get("player_ids", []),
            "league_id": league_id,
        }
        for i, m in enumerate(members)
    ]


def load_local_league_users(league_id: str) -> list[dict]:
    """
    Return users for a local league in Sleeper user format:
    [{"user_id": uid, "display_name": name, "username": uname}, ...]
    """
    members = load_league_members(league_id)
    return [
        {
            "user_id":      m["user_id"],
            "display_name": m.get("display_name") or m.get("username") or m["user_id"],
            "username":     m.get("username") or m["user_id"],
        }
        for m in members
    ]


# ---------------------------------------------------------------------------
# Member rankings operations
# ---------------------------------------------------------------------------

def upsert_member_rankings(
    user_id: str,
    league_id: str,
    rankings: list[dict],
    scoring_format: str = DEFAULT_SCORING,
) -> None:
    """
    Replace a user's ranking snapshot for a league + scoring format.

    rankings: list of {player_id: str, elo: float}

    Atomically deletes all existing rows for this (user_id, league_id,
    scoring_format) and bulk-inserts the fresh snapshot.  The OTHER
    format's snapshot is left untouched, so toggling scoring doesn't
    wipe the rank set you're not currently using.
    """
    now  = _now()
    rows = [
        {
            "user_id":        user_id,
            "league_id":      league_id,
            "player_id":      r["player_id"],
            "elo":            float(r["elo"]),
            "updated_at":     now,
            "scoring_format": scoring_format,
        }
        for r in rankings
        if r.get("player_id") and r.get("elo") is not None
    ]

    with engine.begin() as conn:
        # Delete only this format's rows. Legacy NULL-tagged rows (before
        # dual-format migration) are cleaned up when the default format
        # matches, but other-format rows stay put.
        if scoring_format == DEFAULT_SCORING:
            conn.execute(
                delete(member_rankings_table).where(
                    (member_rankings_table.c.user_id   == user_id) &
                    (member_rankings_table.c.league_id == league_id) &
                    (
                        (member_rankings_table.c.scoring_format == scoring_format) |
                        (member_rankings_table.c.scoring_format.is_(None))
                    )
                )
            )
        else:
            conn.execute(
                delete(member_rankings_table).where(
                    (member_rankings_table.c.user_id        == user_id) &
                    (member_rankings_table.c.league_id      == league_id) &
                    (member_rankings_table.c.scoring_format == scoring_format)
                )
            )
        if rows:
            conn.execute(insert(member_rankings_table), rows)


def load_member_rankings(
    league_id: str,
    exclude_user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict:
    """
    Load stored member rankings for a league + scoring format, excluding
    one user (the logged-in user, who already has their ELO in memory).

    Returns:
    {
        user_id: {
            "username":    str,
            "elo_ratings": { player_id: elo, ... }
        },
        ...
    }

    Only users who have submitted at least one ranking in this format
    are included.
    """
    with engine.connect() as conn:
        # Username lookup from league_members
        member_rows = conn.execute(
            select(league_members_table).where(
                league_members_table.c.league_id == league_id
            )
        ).fetchall()
        username_map = {
            r.user_id: r.username or r.display_name or r.user_id
            for r in member_rows
        }

        # All stored rankings for this format except the current user.
        # Legacy NULL rows are treated as '1qb_ppr' so pre-migration data
        # keeps working for the default format.
        q = (
            select(member_rankings_table).where(
                (member_rankings_table.c.league_id == league_id) &
                (member_rankings_table.c.user_id   != exclude_user_id)
            )
        )
        if scoring_format == DEFAULT_SCORING:
            q = q.where(
                (member_rankings_table.c.scoring_format == scoring_format) |
                (member_rankings_table.c.scoring_format.is_(None))
            )
        else:
            q = q.where(member_rankings_table.c.scoring_format == scoring_format)
        ranking_rows = conn.execute(q).fetchall()

    result: dict = {}
    for r in ranking_rows:
        uid = r.user_id
        if uid not in result:
            result[uid] = {
                "username":    username_map.get(uid, uid),
                "elo_ratings": {},
            }
        result[uid]["elo_ratings"][r.player_id] = r.elo

    return result


def get_ranking_coverage(league_id: str, exclude_user_id: str) -> dict:
    """
    Return how many leaguemates have submitted rankings for a given league.

    exclude_user_id: the logged-in user (not counted as a "leaguemate").

    Returns:
    {
        "ranked": int,       # leaguemates with at least one stored ranking
        "total":  int,       # total leaguemates (excludes the current user)
        "members": [         # per-member detail
            {"user_id": str, "username": str, "has_rankings": bool}, ...
        ]
    }
    """
    with engine.connect() as conn:
        member_rows = conn.execute(
            select(league_members_table).where(
                (league_members_table.c.league_id == league_id) &
                (league_members_table.c.user_id   != exclude_user_id)
            )
        ).fetchall()

        ranked_rows = conn.execute(
            select(member_rankings_table.c.user_id).distinct().where(
                (member_rankings_table.c.league_id == league_id) &
                (member_rankings_table.c.user_id   != exclude_user_id)
            )
        ).fetchall()

    ranked_ids = {r.user_id for r in ranked_rows}
    member_list = [
        {
            "user_id":      m.user_id,
            "username":     m.username or m.display_name or m.user_id,
            "has_rankings": m.user_id in ranked_ids,
        }
        for m in member_rows
    ]

    return {
        "ranked":  len(ranked_ids),
        "total":   len(member_rows),
        "members": member_list,
    }


# ---------------------------------------------------------------------------
# Trade match operations
# ---------------------------------------------------------------------------

def check_for_match(
    current_user_id: str,
    league_id: str,
    target_user_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
) -> bool:
    """
    Check whether target_user_id has already liked a mirrored trade.

    A mirror trade means: target_user gives what current_user receives,
    and target_user receives what current_user gives.

    Uses set comparison so JSON ordering doesn't matter.

    Returns True if a matching "like" decision exists.
    """
    give_set    = set(give_player_ids)
    receive_set = set(receive_player_ids)

    with engine.connect() as conn:
        rows = conn.execute(
            select(trade_decisions_table).where(
                and_(
                    trade_decisions_table.c.user_id    == target_user_id,
                    trade_decisions_table.c.league_id  == league_id,
                    trade_decisions_table.c.decision   == "like",
                )
            )
        ).fetchall()

    for r in rows:
        try:
            their_give    = set(json.loads(r.give_player_ids))
            their_receive = set(json.loads(r.receive_player_ids))
        except (json.JSONDecodeError, TypeError):
            continue
        # Their give == what current user receives, their receive == what current user gives
        if their_give == receive_set and their_receive == give_set:
            return True

    return False


def match_already_exists(
    league_id: str,
    user_a_id: str,
    user_b_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
) -> bool:
    """
    Return True if this exact trade match has already been recorded.

    Checks both orderings (A→B and B→A) and uses set-based player ID comparison.
    """
    give_str    = json.dumps(sorted(give_player_ids))
    receive_str = json.dumps(sorted(receive_player_ids))

    with engine.connect() as conn:
        rows = conn.execute(
            select(trade_matches_table).where(
                and_(
                    trade_matches_table.c.league_id == league_id,
                )
            )
        ).fetchall()

    give_set    = set(give_player_ids)
    receive_set = set(receive_player_ids)

    for r in rows:
        # Check both orderings
        try:
            a_give    = set(json.loads(r.user_a_give))
            a_receive = set(json.loads(r.user_a_receive))
        except (json.JSONDecodeError, TypeError):
            continue

        # Ordering 1: user_a_id is already the "a" side
        if (r.user_a_id == user_a_id and r.user_b_id == user_b_id
                and a_give == give_set and a_receive == receive_set):
            return True

        # Ordering 2: users are flipped — a_give is the receive side
        if (r.user_a_id == user_b_id and r.user_b_id == user_a_id
                and a_give == receive_set and a_receive == give_set):
            return True

    return False


def create_trade_match(
    league_id: str,
    user_a_id: str,
    user_b_id: str,
    user_a_give: list[str],
    user_a_receive: list[str],
) -> dict:
    """
    Persist a new trade match and return it as a dict.

    user_a is the user whose swipe *triggered* the match detection
    (i.e. the current user who just swiped "like").
    user_b is the counterparty who had already swiped "like" earlier.
    """
    now = _now()
    with engine.begin() as conn:
        result = conn.execute(
            insert(trade_matches_table).values(
                league_id    = league_id,
                user_a_id    = user_a_id,
                user_b_id    = user_b_id,
                user_a_give  = json.dumps(user_a_give),
                user_a_receive = json.dumps(user_a_receive),
                matched_at   = now,
                status       = "active",
            )
        )
        match_id = result.inserted_primary_key[0]

    # Agent 6 — wrapped collector hook (non-throwing)
    try:
        from .wrapped_collector import record_event
        record_event(user_a_id, league_id, "trade_match",
                     {"match_id": match_id, "partner_id": user_b_id,
                      "give": user_a_give, "receive": user_a_receive})
    except Exception:
        pass

    return {
        "id":          match_id,
        "league_id":   league_id,
        "user_a_id":   user_a_id,
        "user_b_id":   user_b_id,
        "user_a_give": user_a_give,
        "user_a_receive": user_a_receive,
        "matched_at":  now,
        "status":      "active",
    }


def load_matches(user_id: str, league_id: str | None = None) -> list[dict]:
    """
    Return ALL trade matches for a user, optionally scoped to one league.

    `league_id`:
      - When provided, returns only matches in that league (existing
        single-league behavior, used by the legacy /api/trades/matches route).
      - When None, returns matches across EVERY league the user is in (used
        by /api/trades/matches/all). Each match still carries its `league_id`
        so the caller can group / filter client-side.

    Returns each match from the caller's perspective:
      - my_give / my_receive are normalised so "give" always means what THIS
        user gives away.
      - my_decision is the caller's own accept/decline (or None).
      - their_decision is the partner's decision — but ONLY revealed after the
        caller has already made their own decision (privacy gate).
      - status is normalised: legacy 'active' rows are treated as 'pending'.

    Sorted by matched_at descending (most recent first) so the frontend
    can render in order without additional sorting.
    """
    # User membership is filtered in SQL — Python-side filtering was fine for
    # one league but would over-fetch every other user's match across leagues.
    user_filter = or_(
        trade_matches_table.c.user_a_id == user_id,
        trade_matches_table.c.user_b_id == user_id,
    )
    where_clauses = [user_filter]
    if league_id is not None:
        where_clauses.append(trade_matches_table.c.league_id == league_id)

    with engine.connect() as conn:
        rows = conn.execute(
            select(trade_matches_table)
            .where(and_(*where_clauses))
            .order_by(trade_matches_table.c.matched_at.desc())
        ).fetchall()

        # Build a (league_id, user_id) → display name map. For the
        # single-league case this is one query; for cross-league we fan out
        # to every league we found in the result set.
        if league_id is not None:
            league_ids_for_members = {league_id}
        else:
            league_ids_for_members = {r.league_id for r in rows}

        username_map: dict[tuple[str, str], str] = {}
        if league_ids_for_members:
            member_rows = conn.execute(
                select(league_members_table).where(
                    league_members_table.c.league_id.in_(league_ids_for_members)
                )
            ).fetchall()
            for mr in member_rows:
                username_map[(mr.league_id, mr.user_id)] = (
                    mr.username or mr.display_name or mr.user_id
                )

    result = []
    for r in rows:
        is_a = r.user_a_id == user_id
        is_b = r.user_b_id == user_id
        # Should not fire — SQL filter restricts to user's matches — but
        # keep as a defense against join surprises.
        if not (is_a or is_b):
            continue

        try:
            a_give    = json.loads(r.user_a_give)
            a_receive = json.loads(r.user_a_receive)
        except (json.JSONDecodeError, TypeError):
            a_give, a_receive = [], []

        if is_a:
            my_give          = a_give
            my_receive       = a_receive
            partner_id       = r.user_b_id
            my_decision      = r.user_a_decision
            my_decided_at    = r.user_a_decided_at
            their_raw_dec    = r.user_b_decision
            their_decided_at = r.user_b_decided_at
        else:
            my_give          = a_receive
            my_receive       = a_give
            partner_id       = r.user_a_id
            my_decision      = r.user_b_decision
            my_decided_at    = r.user_b_decided_at
            their_raw_dec    = r.user_a_decision
            their_decided_at = r.user_a_decided_at

        # Privacy gate: only reveal partner's decision after caller has decided
        their_decision      = their_raw_dec    if my_decision else None
        their_revealed_at   = their_decided_at if my_decision else None

        # Normalise legacy 'active' status
        status = r.status or "pending"
        if status == "active":
            status = "pending"

        result.append({
            "match_id":        r.id,
            "league_id":       r.league_id,
            "partner_id":      partner_id,
            "partner_name":    username_map.get((r.league_id, partner_id), partner_id),
            "my_give":         my_give,
            "my_receive":      my_receive,
            "matched_at":      r.matched_at,
            "status":          status,
            "my_decision":     my_decision,
            "my_decided_at":   my_decided_at,
            "their_decision":  their_decision,
            "their_decided_at": their_revealed_at,
        })

    return result


# K-factors for disposition ELO signals — loaded live from model_config.
# These local lambdas fall back to the hardcoded defaults if the table
# isn't available yet (e.g. during the very first init_db() call).
_K_ACCEPT             = lambda: get_config().get("trade_k_accept",             20.0)
_K_DECLINE_CORRECTION = lambda: get_config().get("trade_k_decline_correction", 20.0)


def record_match_disposition(
    match_id: int,
    user_id: str,
    decision: str,
) -> dict:
    """
    Record a user's accept/decline decision on a trade match.

    Returns a result dict:
    {
        'status':        'ok' | 'not_found' | 'already_decided',
        'match_id':      int,
        'both_decided':  bool,
        'outcome':       'accepted' | 'declined' | None,
        'elo_signals':   [    # only present when both_decided=True
            {
                'user_id':       str,
                'winner_ids':    list[str],
                'loser_ids':     list[str],
                'k_factor':      float,
                'decision_type': 'disposition',
            }, ...
        ],
    }

    ELO signal semantics
    ────────────────────
    Both accept   → for each user: winner=receive, loser=give, K=20
    Any decline   → for each decliner: winner=give, loser=receive, K=20
                    (net effect ≈ −12 after the original +8 like nudge)
    """
    now = _now()

    with engine.begin() as conn:
        row = conn.execute(
            select(trade_matches_table).where(
                trade_matches_table.c.id == match_id
            )
        ).fetchone()

        if row is None:
            return {"status": "not_found", "match_id": match_id,
                    "both_decided": False, "outcome": None, "elo_signals": []}

        is_a = row.user_a_id == user_id
        is_b = row.user_b_id == user_id
        if not (is_a or is_b):
            return {"status": "not_found", "match_id": match_id,
                    "both_decided": False, "outcome": None, "elo_signals": []}

        # Check already decided
        current_dec = row.user_a_decision if is_a else row.user_b_decision
        if current_dec is not None:
            return {"status": "already_decided", "match_id": match_id,
                    "both_decided": False, "outcome": None, "elo_signals": []}

        # Write the decision
        if is_a:
            conn.execute(
                update(trade_matches_table)
                .where(trade_matches_table.c.id == match_id)
                .values(user_a_decision=decision, user_a_decided_at=now)
            )
            a_dec = decision
            b_dec = row.user_b_decision
        else:
            conn.execute(
                update(trade_matches_table)
                .where(trade_matches_table.c.id == match_id)
                .values(user_b_decision=decision, user_b_decided_at=now)
            )
            a_dec = row.user_a_decision
            b_dec = decision

        both_decided = (a_dec is not None) and (b_dec is not None)
        outcome      = None
        elo_signals  = []

        if both_decided:
            outcome = "accepted" if (a_dec == "accept" and b_dec == "accept") else "declined"
            conn.execute(
                update(trade_matches_table)
                .where(trade_matches_table.c.id == match_id)
                .values(status=outcome)
            )

            # Decode player ID lists
            try:
                a_give    = json.loads(row.user_a_give)
                a_receive = json.loads(row.user_a_receive)
            except (json.JSONDecodeError, TypeError):
                a_give, a_receive = [], []

            # user_b perspective is the mirror
            b_give    = a_receive
            b_receive = a_give

            # Build ELO signal for user_a
            if a_dec == "accept":
                elo_signals.append({
                    "user_id":       row.user_a_id,
                    "winner_ids":    a_receive,
                    "loser_ids":     a_give,
                    "k_factor":      _K_ACCEPT(),
                    "decision_type": "disposition",
                })
            else:
                elo_signals.append({
                    "user_id":       row.user_a_id,
                    "winner_ids":    a_give,
                    "loser_ids":     a_receive,
                    "k_factor":      _K_DECLINE_CORRECTION(),
                    "decision_type": "disposition",
                })

            # Build ELO signal for user_b
            if b_dec == "accept":
                elo_signals.append({
                    "user_id":       row.user_b_id,
                    "winner_ids":    b_receive,
                    "loser_ids":     b_give,
                    "k_factor":      _K_ACCEPT(),
                    "decision_type": "disposition",
                })
            else:
                elo_signals.append({
                    "user_id":       row.user_b_id,
                    "winner_ids":    b_give,
                    "loser_ids":     b_receive,
                    "k_factor":      _K_DECLINE_CORRECTION(),
                    "decision_type": "disposition",
                })

    return {
        "status":       "ok",
        "match_id":     match_id,
        "both_decided": both_decided,
        "outcome":      outcome,
        "elo_signals":  elo_signals,
    }


# ---------------------------------------------------------------------------
# League preference operations
# ---------------------------------------------------------------------------

_VALID_OUTLOOKS = frozenset({"championship", "contender", "rebuilder", "jets", "not_sure"})


def upsert_league_preference(
    user_id: str,
    league_id: str,
    team_outlook: str,
    acquire_positions: list[str] | None = None,
    trade_away_positions: list[str] | None = None,
) -> None:
    """
    Store or update a user's team-building outlook and positional preferences
    for a specific league.

    team_outlook must be one of:
        championship | contender | rebuilder | jets | not_sure

    acquire_positions / trade_away_positions: lists of position strings
        e.g. ["WR", "TE"] or ["QB"].  Pass None to leave existing value unchanged.
    """
    if team_outlook not in _VALID_OUTLOOKS:
        raise ValueError(f"team_outlook must be one of {sorted(_VALID_OUTLOOKS)}")

    now = _now()
    with engine.begin() as conn:
        existing = conn.execute(
            select(league_preferences_table).where(
                and_(
                    league_preferences_table.c.user_id   == user_id,
                    league_preferences_table.c.league_id == league_id,
                )
            )
        ).fetchone()

        # Build the values dict; only include positional fields when supplied
        vals: dict = {"team_outlook": team_outlook, "updated_at": now}
        if acquire_positions is not None:
            vals["acquire_positions"]    = json.dumps(acquire_positions)
        if trade_away_positions is not None:
            vals["trade_away_positions"] = json.dumps(trade_away_positions)

        if existing:
            conn.execute(
                update(league_preferences_table)
                .where(
                    and_(
                        league_preferences_table.c.user_id   == user_id,
                        league_preferences_table.c.league_id == league_id,
                    )
                )
                .values(**vals)
            )
        else:
            conn.execute(insert(league_preferences_table).values(
                user_id              = user_id,
                league_id            = league_id,
                acquire_positions    = vals.get("acquire_positions",    "[]"),
                trade_away_positions = vals.get("trade_away_positions", "[]"),
                updated_at           = now,
                **{k: v for k, v in vals.items()
                   if k not in ("acquire_positions", "trade_away_positions", "updated_at")},
            ))


def load_league_preference(user_id: str, league_id: str) -> dict | None:
    """
    Return a dict with all stored preferences for (user_id, league_id), or
    None if no preference has been saved yet.

    Returned dict shape:
        {
            "team_outlook":        str | None,
            "acquire_positions":   list[str],   # e.g. ["WR", "TE"]
            "trade_away_positions": list[str],  # e.g. ["QB"]
        }
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(league_preferences_table).where(
                and_(
                    league_preferences_table.c.user_id   == user_id,
                    league_preferences_table.c.league_id == league_id,
                )
            )
        ).fetchone()
    if row is None:
        return None

    def _parse_positions(raw) -> list[str]:
        if not raw:
            return []
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "team_outlook":          row.team_outlook,
        "acquire_positions":     _parse_positions(getattr(row, "acquire_positions",    None)),
        "trade_away_positions":  _parse_positions(getattr(row, "trade_away_positions", None)),
    }


# ---------------------------------------------------------------------------
# Player sync operations
# ---------------------------------------------------------------------------

_SYNC_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


def needs_player_sync() -> bool:
    """
    Return True if the players table is empty or the most recent
    last_synced timestamp is older than 24 hours.
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(players_table.c.last_synced)
            .order_by(players_table.c.last_synced.desc())
            .limit(1)
        ).fetchone()
    if row is None:
        return True   # table is empty
    try:
        synced_at = datetime.fromisoformat(row.last_synced)
        if synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - synced_at) > timedelta(hours=24)
    except Exception:
        return True   # unparseable timestamp — re-sync to be safe


def sync_players(player_db: dict, adp_map: dict | None = None) -> int:
    """
    Upsert all skill-position players from the Sleeper bulk payload into
    the players table.

    Filtering rules (dynasty-relevant subset):
      • Position must be QB, RB, WR, or TE
      • Must have a full_name
      • Removed only if status != 'Active' AND years_exp is not None
        (i.e., retired/Inactive players who actually played; prospects
        with years_exp=None are kept as potential draft targets)

    player_db : dict of {player_id: raw_sleeper_player_data}
    adp_map   : optional {player_id: float} — ADP values from the Sleeper
                ADP endpoint (https://api.sleeper.app/v1/players/nfl/adp).
                If provided, stored alongside each player record.

    Returns the number of players written.
    """
    now  = _now()
    rows = []

    for pid, p in player_db.items():
        pos = p.get("position", "")
        if pos not in _SYNC_POSITIONS:
            continue
        if not p.get("full_name"):
            continue

        # Keep Active players; also keep anyone with no years_exp data
        # (undrafted rookies / prospects).  Remove Inactive/IR players
        # who have actually played before (years_exp is not None).
        status    = p.get("status") or ""
        years_exp = p.get("years_exp")
        if status != "Active" and years_exp is not None:
            continue

        # Safely coerce numeric fields
        age  = p.get("age")
        try:
            age = int(age) if age is not None else None
        except (TypeError, ValueError):
            age = None

        yr = years_exp
        try:
            yr = int(yr) if yr is not None else None
        except (TypeError, ValueError):
            yr = None

        dc_order = p.get("depth_chart_order")
        try:
            dc_order = int(dc_order) if dc_order is not None else None
        except (TypeError, ValueError):
            dc_order = None

        sr = p.get("search_rank")
        try:
            sr = int(sr) if sr is not None else None
        except (TypeError, ValueError):
            sr = None

        adp_val = None
        if adp_map:
            raw_adp = adp_map.get(str(pid))
            if raw_adp is not None:
                try:
                    adp_val = float(raw_adp)
                except (TypeError, ValueError):
                    pass

        rows.append({
            "player_id":            str(pid),
            "full_name":            p.get("full_name"),
            "first_name":           p.get("first_name"),
            "last_name":            p.get("last_name"),
            "position":             pos,
            "team":                 p.get("team"),
            "age":                  age,
            "birth_date":           p.get("birth_date"),
            "years_exp":            yr,
            "depth_chart_position": p.get("depth_chart_position"),
            "depth_chart_order":    dc_order,
            "status":               status or None,
            "injury_status":        p.get("injury_status"),
            "injury_body_part":     p.get("injury_body_part"),
            "height":               p.get("height"),
            "weight":               p.get("weight"),
            "college":              p.get("college"),
            "search_rank":          sr,
            "adp":                  adp_val,
            "last_synced":          now,
        })

    if not rows:
        return 0

    # Bulk delete + re-insert — fast for our ~2 k-row reference table
    with engine.begin() as conn:
        conn.execute(delete(players_table))
        # Insert in chunks to avoid hitting SQLite variable limits
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            conn.execute(insert(players_table), rows[i: i + chunk_size])

    return len(rows)


def load_players(position: str | None = None) -> list[dict]:
    """
    Return all synced players, optionally filtered by position.
    Sorted by search_rank ascending (lower = more relevant); players
    without a search_rank are appended last.
    """
    with engine.connect() as conn:
        q = select(players_table)
        if position:
            q = q.where(players_table.c.position == position.upper())
        # Rows with no search_rank sort last
        q = q.order_by(
            players_table.c.search_rank.is_(None),
            players_table.c.search_rank,
        )
        rows = conn.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


def load_player(player_id: str) -> dict | None:
    """Return a single player record by Sleeper player_id, or None."""
    with engine.connect() as conn:
        row = conn.execute(
            select(players_table).where(
                players_table.c.player_id == str(player_id)
            )
        ).fetchone()
    return dict(row._mapping) if row else None


def load_players_by_ids(player_ids: list[str]) -> dict[str, dict]:
    """
    Bulk-fetch player records by a list of player IDs.
    Returns a {player_id: player_dict} mapping for all found IDs.
    Missing IDs are simply absent from the result.
    """
    if not player_ids:
        return {}
    str_ids = [str(pid) for pid in player_ids]
    with engine.connect() as conn:
        rows = conn.execute(
            select(players_table).where(
                players_table.c.player_id.in_(str_ids)
            )
        ).fetchall()
    return {row.player_id: dict(row._mapping) for row in rows}


def load_rookies() -> list[dict]:
    """
    Return all rookie / prospect players from the DB, suitable for
    displaying on a dynasty rookie draft board.

    Includes:
      • years_exp = 0  (players in their first NFL season)
      • years_exp IS NULL  (pre-draft prospects / UDFAs with no league record yet)

    Sorted by search_rank (lower = higher-ranked prospect), NULLs last.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(players_table).where(
                and_(
                    players_table.c.position.in_(["QB", "RB", "WR", "TE"]),
                    or_(
                        players_table.c.years_exp == 0,
                        players_table.c.years_exp.is_(None),
                    ),
                )
            ).order_by(
                players_table.c.search_rank.is_(None),
                players_table.c.search_rank,
            )
        ).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Draft pick operations
# ---------------------------------------------------------------------------

# Base dynasty values by round (mid-range of each tier, pre-year-discount).
# Round 1 tiers from spec: 1.01-1.03≈90, 1.04-1.06≈75, 1.07-1.10≈60,
# 1.11-1.12≈45.  Midpoint ≈ 67.5.  We store the midpoint as the default
# since we often don't know the exact pick slot for future picks.
_PICK_BASE: dict[int, float] = {
    1: 67.5,   # mid-first (see tiers above for slot-specific values)
    2: 25.0,   # mid-second (early≈30, late≈20)
    3: 10.0,   # third round
}
_PICK_DEFAULT_VALUE = 5.0    # 4th round and beyond
_PICK_YEAR_DISCOUNT = 0.85   # 15 % off per year out


def compute_pick_value(round_: int, season: int, current_season: int) -> float:
    """
    Return the dynasty fantasy value for a draft pick.

    Uses the mid-tier base value for the round and applies a 15 % discount
    for each year the pick is in the future.

    round_         : pick round (1, 2, 3, …)
    season         : year the draft will be held (e.g. 2026)
    current_season : current NFL season (e.g. 2026)
    """
    base       = _PICK_BASE.get(round_, _PICK_DEFAULT_VALUE)
    years_out  = max(0, season - current_season)
    discounted = base * (_PICK_YEAR_DISCOUNT ** years_out)
    return round(discounted, 2)


def sync_draft_picks(
    league_id: str,
    roster_ids: list[int],
    traded_picks: list[dict],
    roster_id_to_user: dict[str, str],
    user_id_to_name: dict[str, str],
    current_season: int = 2026,
    rounds: int = 3,
    seasons_ahead: int = 3,
) -> list[dict]:
    """
    Build the full pick grid for a dynasty league and persist it to the DB.

    Algorithm
    ---------
    1. Generate the "pristine" grid: every (season, round, roster_id) tuple
       for [current_season … current_season + seasons_ahead].
    2. Overlay the traded_picks list (from Sleeper) to update ownership for
       any pick that changed hands.
    3. Compute pick_value for each pick, upsert into draft_picks_table.
    4. Return the full list of pick dicts (for in-memory use in session_init).

    Parameters
    ----------
    roster_ids         : list of Sleeper roster IDs in the league (ints)
    traded_picks       : raw Sleeper traded_picks response list
    roster_id_to_user  : {str(roster_id): user_id} mapping
    user_id_to_name    : {user_id: display_name} mapping
    current_season     : current NFL year (default 2026)
    rounds             : number of draft rounds (default 3)
    seasons_ahead      : how many future seasons to include (default 3)
    """
    now = _now()

    # Step 1: build the pristine pick grid (everyone keeps their own picks)
    picks: dict[str, dict] = {}
    for rid in roster_ids:
        rid_str  = str(rid)
        user_id  = roster_id_to_user.get(rid_str, "")
        username = user_id_to_name.get(user_id, f"Roster {rid_str}")
        for season in range(current_season, current_season + seasons_ahead + 1):
            for rnd in range(1, rounds + 1):
                pick_id = f"{league_id}_{season}_{rnd}_{rid_str}"
                picks[pick_id] = {
                    "pick_id":            pick_id,
                    "league_id":          league_id,
                    "season":             season,
                    "round":              rnd,
                    "owner_user_id":      user_id,
                    "owner_username":     username,
                    "original_roster_id": rid_str,
                    "original_user_id":   user_id,
                    "original_username":  username,
                    "is_traded":          0,
                    "pick_value":         compute_pick_value(rnd, season, current_season),
                }

    # Step 2: overlay traded picks
    for tp in (traded_picks or []):
        try:
            season  = int(tp.get("season", 0))
            rnd     = int(tp.get("round", 0))
            orig_rid = str(tp.get("roster_id", ""))   # original team's roster_id
            new_rid  = str(tp.get("owner_id", ""))    # current owner's roster_id
        except (TypeError, ValueError):
            continue

        if not orig_rid or not new_rid or rnd < 1 or season < current_season:
            continue

        pick_id = f"{league_id}_{season}_{rnd}_{orig_rid}"

        new_user     = roster_id_to_user.get(new_rid, "")
        new_username = user_id_to_name.get(new_user, f"Roster {new_rid}")

        if pick_id in picks:
            orig_user     = picks[pick_id]["original_user_id"]
            orig_username = picks[pick_id]["original_username"]
        else:
            # Pick from a season/round not in our grid — add it
            orig_user     = roster_id_to_user.get(orig_rid, "")
            orig_username = user_id_to_name.get(orig_user, f"Roster {orig_rid}")
            picks[pick_id] = {
                "pick_id":            pick_id,
                "league_id":          league_id,
                "season":             season,
                "round":              rnd,
                "original_roster_id": orig_rid,
                "original_user_id":   orig_user,
                "original_username":  orig_username,
                "is_traded":          0,
                "pick_value":         compute_pick_value(rnd, season, current_season),
            }

        is_traded = int(new_rid != orig_rid)
        picks[pick_id].update({
            "owner_user_id":  new_user,
            "owner_username": new_username,
            "is_traded":      is_traded,
        })

    # Step 3: upsert all picks into the DB
    rows = [
        {**p, "synced_at": now}
        for p in picks.values()
    ]

    with engine.begin() as conn:
        # Remove stale picks for this league then bulk-insert fresh state
        conn.execute(
            delete(draft_picks_table).where(
                draft_picks_table.c.league_id == league_id
            )
        )
        if rows:
            chunk_size = 200
            for i in range(0, len(rows), chunk_size):
                conn.execute(insert(draft_picks_table), rows[i: i + chunk_size])

    return rows


def load_draft_picks(
    league_id: str,
    owner_user_id: str | None = None,
) -> list[dict]:
    """
    Return draft picks for a league, optionally filtered to a single owner.
    Sorted by season ASC, round ASC, pick_value DESC.
    """
    with engine.connect() as conn:
        q = select(draft_picks_table).where(
            draft_picks_table.c.league_id == league_id
        )
        if owner_user_id is not None:
            q = q.where(draft_picks_table.c.owner_user_id == owner_user_id)
        q = q.order_by(
            draft_picks_table.c.season,
            draft_picks_table.c.round,
            draft_picks_table.c.pick_value.desc(),
        )
        rows = conn.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def create_notification(
    user_id:  str,
    type_:    str,
    title:    str,
    body:     str,
    metadata: dict | None = None,
) -> dict:
    """
    Insert a new notification for a user.

    Parameters
    ----------
    user_id  : Sleeper user_id of the recipient.
    type_    : 'trade_match', 'trade_accepted', or 'trade_declined'.
    title    : Short headline shown in bold.
    body     : Full notification text.
    metadata : Optional dict stored as JSON — e.g. match_id, partner_username,
               give/receive player name lists.

    Returns
    -------
    Dict with the inserted row data including the new id.
    """
    row = {
        "user_id":       user_id,
        "type":          type_,
        "title":         title,
        "body":          body,
        "metadata_json": json.dumps(metadata or {}),
        "is_read":       0,
        "created_at":    _now(),
    }
    with engine.begin() as conn:
        result = conn.execute(insert(notifications_table).values(**row))
        row["id"] = result.inserted_primary_key[0]
    return row


def get_notifications(user_id: str, read_limit: int = 20) -> list[dict]:
    """
    Return notifications for a user, newest first.
    Always returns ALL unread + the most recent `read_limit` read notifications.
    """
    with engine.connect() as conn:
        # All unread
        unread_rows = conn.execute(
            select(notifications_table)
            .where(
                and_(
                    notifications_table.c.user_id  == user_id,
                    notifications_table.c.is_read  == 0,
                )
            )
            .order_by(notifications_table.c.created_at.desc())
        ).fetchall()

        # Most recent `read_limit` read
        read_rows = conn.execute(
            select(notifications_table)
            .where(
                and_(
                    notifications_table.c.user_id == user_id,
                    notifications_table.c.is_read == 1,
                )
            )
            .order_by(notifications_table.c.created_at.desc())
            .limit(read_limit)
        ).fetchall()

    def _row_to_dict(r) -> dict:
        d = dict(r._mapping)
        try:
            d["metadata"] = json.loads(d.get("metadata_json") or "{}")
        except Exception:
            d["metadata"] = {}
        return d

    combined = [_row_to_dict(r) for r in unread_rows] + \
               [_row_to_dict(r) for r in read_rows]
    # Re-sort combined list newest-first (unread first within same timestamp)
    combined.sort(key=lambda x: (x["is_read"], x["created_at"] or ""), reverse=True)
    return combined


def mark_notifications_read(
    user_id:          str,
    notification_ids: list[int] | None = None,
) -> int:
    """
    Mark notifications as read.

    If `notification_ids` is provided, only those IDs are updated (they must
    belong to `user_id`).  If None, ALL unread notifications for the user are
    marked read (i.e. "mark all as read").

    Returns the number of rows updated.
    """
    with engine.begin() as conn:
        q = (
            update(notifications_table)
            .where(notifications_table.c.user_id == user_id)
            .where(notifications_table.c.is_read == 0)
        )
        if notification_ids:
            q = q.where(notifications_table.c.id.in_(notification_ids))
        result = conn.execute(q.values(is_read=1))
        return result.rowcount


# ---------------------------------------------------------------------------
# Agent 6 — Cross-league portfolio
# ---------------------------------------------------------------------------

def load_user_cross_league_exposure(user_id: str) -> list[dict]:
    """
    Aggregate this user's player exposure across every league they own a
    roster in.  Joins league_members (to get the user's own rosters) with
    leagues (for human-readable league names) and players (for name/position).

    Returns a list of dicts sorted by exposure count desc:
        [{player_id, name, pos, exposure, total_leagues, league_names}, ...]

    total_leagues is identical on every row — it's the number of leagues
    this user has a roster in.  exposure is the subset where the player
    is on this user's team.
    """
    with engine.connect() as conn:
        # Pull every (league_id, roster_data) row where this user owns the team.
        member_rows = conn.execute(
            select(
                league_members_table.c.league_id,
                league_members_table.c.roster_data,
            ).where(league_members_table.c.user_id == user_id)
        ).fetchall()

        if not member_rows:
            return []

        # Map league_id -> display name (prefer latest known leagues row)
        league_ids = list({r.league_id for r in member_rows})
        league_name_map: dict[str, str] = {}
        if league_ids:
            lrows = conn.execute(
                select(
                    leagues_table.c.sleeper_league_id,
                    leagues_table.c.name,
                ).where(leagues_table.c.sleeper_league_id.in_(league_ids))
            ).fetchall()
            for lr in lrows:
                if lr.sleeper_league_id not in league_name_map and lr.name:
                    league_name_map[lr.sleeper_league_id] = lr.name

        # Build exposure: player_id -> set of league_ids it appears in
        exposure: dict[str, set[str]] = {}
        for r in member_rows:
            try:
                pids = json.loads(r.roster_data or "[]")
            except (json.JSONDecodeError, TypeError):
                pids = []
            for pid in pids:
                if not pid:
                    continue
                exposure.setdefault(str(pid), set()).add(r.league_id)

        if not exposure:
            return []

        # Resolve player metadata in one query
        prows = conn.execute(
            select(
                players_table.c.player_id,
                players_table.c.full_name,
                players_table.c.position,
            ).where(players_table.c.player_id.in_(list(exposure.keys())))
        ).fetchall()
        player_meta = {
            p.player_id: {"name": p.full_name, "pos": p.position}
            for p in prows
        }

    total_leagues = len(league_ids)
    result = []
    for pid, lid_set in exposure.items():
        meta = player_meta.get(pid, {})
        result.append({
            "player_id":     pid,
            "name":          meta.get("name") or pid,
            "pos":           meta.get("pos") or "",
            "exposure":      len(lid_set),
            "total_leagues": total_leagues,
            "league_names":  sorted(
                league_name_map.get(lid, lid) for lid in lid_set
            ),
        })

    # Primary sort: exposure desc; secondary: name asc for stability
    result.sort(key=lambda d: (-d["exposure"], d["name"].lower()))
    return result


# ---------------------------------------------------------------------------
# Agent 1 additions — user_player_skips helpers
# ---------------------------------------------------------------------------

def add_skip(user_id: str, player_id: str, scoring_format: str = DEFAULT_SCORING) -> None:
    """
    Record a persistent skip/dismiss for (user, player, scoring_format).

    Idempotent — already-skipped rows are silently ignored so the caller can
    fire-and-forget without checking first.
    """
    if not user_id or not player_id:
        return
    if scoring_format not in SCORING_FORMATS:
        scoring_format = DEFAULT_SCORING
    payload = {
        "user_id":        user_id,
        "player_id":      player_id,
        "scoring_format": scoring_format,
        "skipped_at":     _now(),
    }
    try:
        with engine.begin() as conn:
            if DATABASE_URL.startswith("sqlite"):
                conn.execute(text(
                    "INSERT OR IGNORE INTO user_player_skips "
                    "(user_id, player_id, scoring_format, skipped_at) "
                    "VALUES (:user_id, :player_id, :scoring_format, :skipped_at)"
                ), payload)
            else:
                conn.execute(text(
                    "INSERT INTO user_player_skips "
                    "(user_id, player_id, scoring_format, skipped_at) "
                    "VALUES (:user_id, :player_id, :scoring_format, :skipped_at) "
                    "ON CONFLICT (user_id, player_id, scoring_format) DO NOTHING"
                ), payload)
    except Exception as e:
        # Non-fatal: log and continue. Callers swallow to keep UX snappy.
        print(f"[add_skip] failed for user={user_id} pid={player_id} fmt={scoring_format}: {e}")


def load_skips(user_id: str, scoring_format: str = DEFAULT_SCORING) -> set:
    """Return the set of player_ids this user has persistently skipped in this format."""
    if not user_id:
        return set()
    if scoring_format not in SCORING_FORMATS:
        scoring_format = DEFAULT_SCORING
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(user_player_skips_table.c.player_id)
                .where(user_player_skips_table.c.user_id == user_id)
                .where(user_player_skips_table.c.scoring_format == scoring_format)
            ).fetchall()
        return {r.player_id for r in rows}
    except Exception as e:
        print(f"[load_skips] failed for user={user_id} fmt={scoring_format}: {e}")
        return set()


# Aliases — the tiers-page feature is conceptually a "dismiss", the trios-page
# feature is a "skip" — same underlying table.
dismiss_player = add_skip
load_dismissed_players = load_skips


# ---------------------------------------------------------------------------
# Agent 4 additions — referral receipt helpers
# ---------------------------------------------------------------------------
#
# Reuses the existing `notifications` table (no schema change needed). The new
# `type` value 'referral_joined' is emitted from session_init when a user's
# first INSERT carries an invited_by attribution.
#
# push_notification / load_notifications are thin aliases over the existing
# create_notification / get_notifications helpers so Agent 4's documented
# surface matches the spec, while keeping all data in one table.
# ---------------------------------------------------------------------------

def user_exists(sleeper_user_id: str) -> bool:
    """Return True if a users row already exists for this sleeper_user_id.

    Used by session_init to detect a "fresh INSERT" so the referral receipt
    notification only fires once (on the referred user's first session).
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.sleeper_user_id).where(
                users_table.c.sleeper_user_id == sleeper_user_id
            )
        ).fetchone()
    return row is not None


def get_user_by_username(username: str) -> dict | None:
    """Look up a user row by their Sleeper username (case-insensitive).

    Returns a dict with sleeper_user_id/username/display_name/avatar/etc.,
    or None if no matching user was found. Used to resolve an `invited_by`
    username back to the referrer's sleeper_user_id so we can post them a
    notification.
    """
    if not username:
        return None
    from sqlalchemy import func
    with engine.connect() as conn:
        # Case-insensitive match — invited_by is stored as-typed by the
        # inviter when they built the share URL, and Sleeper usernames are
        # not case-sensitive.
        row = conn.execute(
            select(users_table).where(
                func.lower(users_table.c.username) == username.lower()
            )
        ).fetchone()
    return dict(row._mapping) if row else None


def push_notification(
    user_id: str,
    type: str,
    body: str,
    meta: dict | None = None,
) -> dict:
    """Agent 4 alias — push a notification into a user's inbox.

    Delegates to create_notification(); the title defaults to the body for
    types like 'referral_joined' where the single-line body is the whole
    message. Extra context lives in `meta` (JSON-encoded on write).
    """
    return create_notification(
        user_id=user_id,
        type_=type,
        title=body,
        body=body,
        metadata=meta or {},
    )


def load_notifications(user_id: str, unread_only: bool = False) -> list[dict]:
    """Agent 4 alias — read a user's notifications.

    Wraps get_notifications() so Agent 4's documented surface matches the
    spec. When unread_only=True, returns just the unread subset.
    """
    rows = get_notifications(user_id=user_id)
    if unread_only:
        rows = [r for r in rows if not r.get("is_read")]
    return rows


# ---------------------------------------------------------------------------
# elo_history — snapshots for Trends tab
# ---------------------------------------------------------------------------

def record_elo_snapshot(
    user_id: str,
    league_id: str | None,
    scoring_format: str,
    changed_ratings: dict[str, float],
) -> int:
    """
    Append ELO-history rows for every (player, new_elo) pair in
    `changed_ratings`.  Caller decides which players actually changed —
    this function is a pure insert.

    Returns the number of rows inserted.
    """
    if not changed_ratings:
        return 0
    now = _now()
    rows = [
        {
            "user_id":        user_id,
            "league_id":      league_id,
            "player_id":      str(pid),
            "scoring_format": scoring_format or DEFAULT_SCORING,
            "elo":            float(elo),
            "snapshot_at":    now,
        }
        for pid, elo in changed_ratings.items()
        if pid is not None and elo is not None
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(elo_history_table), rows)
    return len(rows)


def load_elo_history(
    user_id: str,
    scoring_format: str = DEFAULT_SCORING,
    since_days: int = 30,
    league_id: str | None = None,
) -> list[dict]:
    """
    Return the user's ELO-history rows for `scoring_format` within the last
    `since_days` days, ordered OLDEST first so the caller can pick the
    earliest snapshot per player as the "previous" value.

    If `league_id` is provided, filters to rows tagged with that league
    (or globally tagged rows where league_id IS NULL).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    with engine.connect() as conn:
        q = (
            select(elo_history_table)
            .where(elo_history_table.c.user_id        == user_id)
            .where(elo_history_table.c.scoring_format == scoring_format)
            .where(elo_history_table.c.snapshot_at    >= cutoff)
            .order_by(elo_history_table.c.snapshot_at.asc(),
                      elo_history_table.c.id.asc())
        )
        if league_id:
            q = q.where(
                (elo_history_table.c.league_id == league_id) |
                (elo_history_table.c.league_id.is_(None))
            )
        rows = conn.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


def load_community_elo_for_league(
    league_id: str,
    exclude_user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict:
    """
    Thin alias around `load_member_rankings` — kept here so the Trends
    service has a dedicated, clearly-named dependency separate from the
    trade engine's usage of the same data.

    Returns the same shape as load_member_rankings().
    """
    return load_member_rankings(
        league_id       = league_id,
        exclude_user_id = exclude_user_id,
        scoring_format  = scoring_format,
    )


# ---------------------------------------------------------------------------
# Agent 5 additions — invite K-factor / referral dashboard helpers
# ---------------------------------------------------------------------------
#
# The users.invited_by column stores the referrer's Sleeper username as typed
# by the inviter (preserved case-insensitively, see get_user_by_username).
# To compute a user's "invited leaguemates" count we count rows whose
# invited_by matches either the caller's sleeper_user_id OR their username.
# The frontend only knows one of these at a time so we accept either.
# ---------------------------------------------------------------------------

def count_referrals(username_or_user_id: str) -> int:
    """Return the number of users referred by this user.

    Accepts either a Sleeper username (matched case-insensitively against
    invited_by) OR a sleeper_user_id (resolved to a username first, then
    matched). Returns 0 for unknown / empty input.
    """
    if not username_or_user_id:
        return 0
    from sqlalchemy import func
    target = str(username_or_user_id).strip()
    if not target:
        return 0

    with engine.connect() as conn:
        # If they passed a sleeper_user_id, resolve it to their username so
        # we can match against invited_by. If they passed a username, this
        # lookup returns None and we fall through to the direct match.
        row = conn.execute(
            select(users_table.c.username).where(
                users_table.c.sleeper_user_id == target
            )
        ).fetchone()
        username = (row.username if row and row.username else target).strip()
        if not username:
            return 0

        count_row = conn.execute(
            select(func.count()).select_from(users_table).where(
                func.lower(users_table.c.invited_by) == username.lower()
            )
        ).fetchone()
    return int(count_row[0]) if count_row else 0


def list_referral_activity(username_or_user_id: str) -> list[dict]:
    """Return a list of {sleeper_user_id, username, has_swiped} for each
    user referred by this caller.

    `has_swiped` is True when the referred user has at least one row in
    swipe_decisions — a cheap proxy for "actively ranking". Used by the
    K-factor dashboard to show "N invited · M actively ranking".
    """
    if not username_or_user_id:
        return []
    from sqlalchemy import func
    target = str(username_or_user_id).strip()
    if not target:
        return []

    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.username).where(
                users_table.c.sleeper_user_id == target
            )
        ).fetchone()
        username = (row.username if row and row.username else target).strip()
        if not username:
            return []

        referred = conn.execute(
            select(
                users_table.c.sleeper_user_id,
                users_table.c.username,
                users_table.c.display_name,
            ).where(
                func.lower(users_table.c.invited_by) == username.lower()
            )
        ).fetchall()

        out: list[dict] = []
        for r in referred:
            uid = r.sleeper_user_id
            swipe_row = conn.execute(
                select(func.count()).select_from(swipe_decisions_table).where(
                    swipe_decisions_table.c.user_id == uid
                )
            ).fetchone()
            swipe_count = int(swipe_row[0]) if swipe_row else 0
            out.append({
                "sleeper_user_id": uid,
                "username":        r.username or "",
                "display_name":    r.display_name or "",
                "has_swiped":      swipe_count > 0,
                "swipe_count":     swipe_count,
            })
        return out


# ---------------------------------------------------------------------------
# M5 Push additions — device_tokens helpers
# ---------------------------------------------------------------------------

def save_device_token(user_id: str, device_token: str, platform: str) -> None:
    """Register an Expo push token for a user+device.

    Idempotent — re-calling with the same (user_id, device_token) refreshes
    last_seen_at without creating a new row. Tokens can migrate between
    users (e.g., phone re-signed in as a different account) by upserting
    user_id.
    """
    if not user_id or not device_token or platform not in ("ios", "android"):
        return
    now = _now()
    payload = {
        "user_id":      user_id,
        "device_token": device_token,
        "platform":     platform,
        "created_at":   now,
        "last_seen_at": now,
    }
    try:
        with engine.begin() as conn:
            if DATABASE_URL.startswith("sqlite"):
                # SQLite: upsert via INSERT OR REPLACE. Keep created_at stable
                # by checking existing first.
                existing = conn.execute(
                    select(device_tokens_table.c.created_at)
                    .where(device_tokens_table.c.device_token == device_token)
                ).fetchone()
                if existing and existing[0]:
                    payload["created_at"] = existing[0]
                conn.execute(text(
                    "INSERT OR REPLACE INTO device_tokens "
                    "(user_id, device_token, platform, created_at, last_seen_at) "
                    "VALUES (:user_id, :device_token, :platform, :created_at, :last_seen_at)"
                ), payload)
            else:
                conn.execute(text(
                    "INSERT INTO device_tokens "
                    "(user_id, device_token, platform, created_at, last_seen_at) "
                    "VALUES (:user_id, :device_token, :platform, :created_at, :last_seen_at) "
                    "ON CONFLICT (device_token) DO UPDATE SET "
                    "user_id = EXCLUDED.user_id, "
                    "platform = EXCLUDED.platform, "
                    "last_seen_at = EXCLUDED.last_seen_at"
                ), payload)
    except Exception as e:
        print(f"[save_device_token] failed for user={user_id}: {e}")


def load_device_tokens_for_users(user_ids: list) -> list:
    """Return [{user_id, device_token, platform}] for all given users.

    Used by the match-create hook in server.py so one DB round-trip finds
    every device to push to.
    """
    if not user_ids:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    device_tokens_table.c.user_id,
                    device_tokens_table.c.device_token,
                    device_tokens_table.c.platform,
                ).where(device_tokens_table.c.user_id.in_(list(user_ids)))
            ).fetchall()
        return [
            {"user_id": r.user_id, "device_token": r.device_token, "platform": r.platform}
            for r in rows
        ]
    except Exception as e:
        print(f"[load_device_tokens_for_users] failed: {e}")
        return []
