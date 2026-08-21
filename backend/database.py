"""
database.py — Fantasy Trade Finder
=====================================
Persistence layer using SQLAlchemy Core with SQLite (local dev).

Switch to PostgreSQL for production by setting the DATABASE_URL env var:
    DATABASE_URL=postgresql://user:pass@host/dbname
    pip install psycopg2-binary

Default: SQLite file alongside server.py — zero configuration required.
"""

import hashlib
import hmac
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo  # py3.9+
except ImportError:                # pragma: no cover
    ZoneInfo = None  # type: ignore

from sqlalchemy import (
    Column, Float, Index, Integer, MetaData, String, Table, Text, UniqueConstraint,
    create_engine, delete, func, insert, or_, select, update, and_, text,
)
from sqlalchemy import event as sa_event
from datetime import timedelta

# #158 — shared pick ladder + owned-pick pool_value reconciliation. Lives in a
# tiny standalone module (no cycle: pick_values imports trade_service lazily,
# and never imports database) so sync_draft_picks can price on the engine scale.
from .pick_values import pick_pool_value

log = logging.getLogger(__name__)

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

# connect_args only needed for SQLite — check_same_thread lets Flask worker
# threads share pooled connections. (It does NOT enable WAL; the earlier
# comment here claiming so was wrong. WAL is set by the on-connect listener
# below — analytics-platform LLD §3.3, NFR-2.)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine   = create_engine(DATABASE_URL, echo=False, future=True,
                         connect_args=_connect_args)
metadata = MetaData()

# ---------------------------------------------------------------------------
# Analytics platform engines & PRAGMAs (docs/plans/analytics-platform/lld.md §3.3)
# ---------------------------------------------------------------------------
# Three engines, one DB:
#   engine        — product path (WAL, busy_timeout 5000 — today's pysqlite
#                   default, now explicit)
#   ingest_engine — /api/events writes only: 150 ms lock budget so a Sunday
#                   ingest burst sheds instead of stalling product writes
#                   (KD-12); BEGIN IMMEDIATE up front kills the
#                   SQLITE_BUSY_SNAPSHOT lock-upgrade race (RC-8)
#   ro_engine     — read-only report queries (P2 consumers); mode=ro URI on
#                   SQLite, default_transaction_read_only on Postgres

if engine.dialect.name == "sqlite":
    @sa_event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")         # persistent; set per-connect (cheap)
        cur.execute("PRAGMA synchronous=NORMAL")       # WAL-safe durability point
        cur.execute("PRAGMA busy_timeout=5000")        # product-path budget (explicit now)
        cur.execute("PRAGMA wal_autocheckpoint=1000")  # ~4 MB; Health surfaces wal_file_bytes
        cur.close()

    ingest_engine = create_engine(DATABASE_URL, future=True,
        connect_args={"check_same_thread": False, "timeout": 0.15})

    @sa_event.listens_for(ingest_engine, "connect")
    def _sqlite_on_connect_ingest(dbapi_conn, _rec):        # SEPARATE listener — do NOT attach
        dbapi_conn.isolation_level = None                    # canonical pysqlite recipe: disable the
        cur = dbapi_conn.cursor()                            # driver's implicit BEGIN so our explicit
        cur.execute("PRAGMA journal_mode=WAL")               # BEGIN IMMEDIATE below is the only txn
        cur.execute("PRAGMA synchronous=NORMAL")             # start (driver autocommit checks have
        cur.execute("PRAGMA busy_timeout=150")               # churned across Python versions).
        cur.close()                                          # Do NOT attach _sqlite_on_connect: its
                                                             # busy_timeout=5000 PRAGMA runs post-
                                                             # connect and would WIN over 150 (T-23b)

    # RC-8 (SQLITE_BUSY_SNAPSHOT): the ingest SELECT-then-INSERT txn must take
    # the write lock UP FRONT — a deferred txn's read snapshot fails its lock
    # upgrade IMMEDIATELY (busy handler not invoked) whenever any product write
    # committed in between, so under the very Sunday burst this design centers
    # on, ingest would shed near-always without this.
    @sa_event.listens_for(ingest_engine, "begin")
    def _ingest_begin_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")              # write lock first, then SELECT+insert

    _sqlite_db_file = engine.url.database or _DB_PATH
    ro_engine = create_engine(
        f"sqlite:///file:{_sqlite_db_file}?mode=ro&uri=true", future=True,
        connect_args={"check_same_thread": False, "uri": True},
        pool_size=2, max_overflow=1)
    # SQLite has no statement timeout; report queries (P2) install a
    # per-connection progress-handler watchdog (~5 s vm-ops abort) as the
    # honest substitute — see analytics_queries.py when it lands.
else:
    ingest_engine = engine   # Postgres: same engine; ingest txns issue
                             # SET LOCAL lock_timeout='150ms' (self-reverting;
                             # MVCC has no snapshot-upgrade class — RC-8 is
                             # sqlite-only)
    ro_engine = create_engine(
        DATABASE_URL, future=True, pool_size=2, max_overflow=1,
        connect_args={"options": "-c default_transaction_read_only=on "
                                 "-c statement_timeout=5s"})


def analytics_boot_status() -> dict:
    """Post-migration boot check (LLD §3.3): {wal, event_id_index_present}.

    wal is None on Postgres ("n/a", rendered green by the Health tab),
    True/False on SQLite. Never raises and never refuses to serve (HLD G-C)
    — a False just renders red on /api/admin/analytics/health.
    """
    status: dict = {"wal": None, "event_id_index_present": False}
    try:
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
                status["wal"] = (str(mode).lower() == "wal")
                idx_rows = conn.exec_driver_sql(
                    "PRAGMA index_list('user_events')").fetchall()
                status["event_id_index_present"] = any(
                    r[1] == "ix_user_events_event_id" for r in idx_rows)
        else:
            with engine.connect() as conn:
                found = conn.execute(text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'user_events' "
                    "AND indexname = 'ix_user_events_event_id'")).first()
                status["event_id_index_present"] = found is not None
    except Exception as e:
        print(f"[analytics_boot_status] check failed: {e}")
    return status


def wal_file_bytes() -> int | None:
    """Current size of the SQLite -wal file (0 when absent); None on Postgres.
    Surfaced by /api/admin/analytics/health next to wal_autocheckpoint."""
    if engine.dialect.name != "sqlite":
        return None
    try:
        wal_path = (engine.url.database or _DB_PATH) + "-wal"
        return os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

users_table = Table("users", metadata,
    Column("sleeper_user_id", String,  primary_key=True),
    Column("username",        String),
    Column("display_name",    String),
    Column("avatar",          String),
    Column("created_at",      String),
    # P0-1: written at the point of USE by the four save handlers (first-use
    # wins; 'anchor' upgradable) as well as by POST /api/ranking-method.
    Column("ranking_method",  String),   # null | 'trio' | 'manual' | 'tiers'
                                          #      | 'anchor' | 'quickset'
    Column("tiers_saved",     Text),     # JSON — dual-format shape:
                                          #   {"1qb_ppr": ["RB","WR"], "sf_tep": []}
    Column("tier_overrides",  Text),     # JSON — dual-format shape:
                                          #   {"1qb_ppr": {pid: elo}, "sf_tep": {pid: elo}}
    Column("invited_by",      String),   # sleeper username of referrer (null = direct)
    Column("unlocked_formats", Text),    # JSON list — which formats the user has
                                          # unlocked trade finder in, e.g. ["1qb_ppr"]
    Column("anchor_scale",    Text),     # JSON — per-format pick-value scale (#111):
                                          #   {"1qb_ppr": 3, "sf_tep": 2}
                                          # value = "a top-tier asset is worth N firsts";
                                          # absent format key = default (2, legacy math)
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
    # ── Ranking streak ────────────────────────────────────────────────────
    # Updated by record_event() when a rank-class event fires (trio_swipe,
    # tier_save, ranking_complete_first_time). Streak math runs in the
    # user's local-day frame — last_rank_local_date stores a date string
    # (YYYY-MM-DD) in last_rank_tz so DST shifts and travel don't reset.
    Column("current_streak",        Integer),
    Column("longest_streak",        Integer),
    Column("last_rank_local_date",  String),
    Column("last_rank_tz",          String),
    # ── Verified session persistence (account-auth plan P1/P2) ───────────
    # verified_via: 'sleeper' | 'apple' | 'google' | 'mfl_login' — the source
    # that proved control of this user record. NULL = never verified
    # (username-only). 'mfl_login' = a successful MFL username/password login
    # (POST /api/mfl/auth-link — operator decision 2026-08-11).
    Column("verified_at",           String),
    Column("verified_via",          String),
    # ── Public-profile opt-in (teardown 06-04, flag profiles.user_toggle) ─
    # 1 = user opted into /u/<username> exposure; NULL/0 = private. Checked
    # by the public profile routes IN ADDITION to the global
    # profiles.public_pages flag, so flipping the global flag can never
    # publish a user who didn't opt in.
    Column("profile_public",        Integer),
    # ── #214/#215 stud-tax mode ───────────────────────────────────────────
    # 'market' (default/NULL — retuned shapes) | 'heavy' (pre-#214 legacy
    # math) | 'off' (naive sums, no crown/depth adjustments). Read by
    # trade_service.stud_tax_mode_for_user for /api/trade/evaluate and
    # deck generation.
    Column("stud_tax_mode",         String),
    # ── M6b draft-pick pricing mode (flag `trade.slot_pricing`) ───────────
    # 'tier_ladder' (default/NULL — today's shipped ladder, unchanged) |
    # 'market_slots' (DynastyProcess per-slot market curve). Read at pick
    # PRICING time by trade_service.pick_pricing_mode_for_user; it never
    # rewrites draft_picks.pool_value, which is league-shared.
    Column("pick_pricing_mode",     String),
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
    Column("total_rosters",     Integer),# Sleeper's total_rosters (all teams, owned or orphaned)
    # ── ESPN league linking (Phase 1, flag `espn.link`) ───────────────────
    # For platform='espn' rows the PK column holds the numeric ESPN league
    # id (the plan chose a platform column over magic-prefix ids; the PK
    # name is accepted as slightly a lie). NULL platform reads as 'sleeper'.
    Column("platform",          String),  # 'sleeper' (default/NULL) | 'espn' | 'mfl' | 'fleaflicker'
    Column("espn_season",       Integer), # ESPN seasonId used at import (re-sync key)
    Column("espn_auth",         String),  # 'public' | 'cookie' — how the league was read
    Column("espn_my_team_id",   Integer), # the linking user's ESPN team id (binding)
    # ── Generic multi-platform linking (MFL / Fleaflicker; flags
    # `mfl.link` / `fleaflicker.link`) — plan
    # docs/plans/multi-platform-linking-plan-2026-07-17.md. Reuses this row
    # (the PK holds the platform-native league id) instead of adding
    # per-platform tables. ESPN keeps its own espn_* columns for
    # back-compat; new platforms use these generic ones.
    Column("platform_season",   Integer), # season/year used at import (re-sync key)
    Column("platform_host",     String),  # MFL wwwNN host (NULL for others)
    Column("platform_auth",     String),  # 'public' | 'cookie'
    Column("platform_my_team",  String),  # linking user's franchise/team key (string id)
    Column("platform_future_picks", Text),# MFL/Fleaflicker futureDraftPicks stored raw
                                           # (JSON list) — NOT wired into the engine yet
                                           # (pick-inclusive trades = +M follow-up)
    # ── #207 rookie-draft status cache (backend/draft_status.py) ──────────
    # Detection costs 1–2 platform reads + a roster scan, so the verdict is
    # cached on the league row and refreshed on the league-sync path + the
    # hourly tick (see server._refresh_league_draft_status). NULL status =
    # never checked, which the fail-safe reads as "show current-year picks".
    Column("draft_status",            String),  # 'drafted'|'not_drafted'|'unknown'
    Column("draft_status_confidence", String),  # 'high'|'medium'|'low'
    Column("draft_status_checked_at", String),  # ISO UTC of the last check
    # ── draft-extensions W3 M-A (ADR-010) — pick-assignment NUMBERING ─────
    # JSON {rounds:int, order_type:'linear'|'snake', order:[user_id, ...]}.
    # OWNERSHIP is never stored here — that lives one row per slot in
    # draft_picks. This holds only what the grid cannot express: the round-1
    # pick sequence and the linear/snake shape, both of which change slot
    # NUMBERING and never who owns a pick. NULL = never configured.
    Column("pick_assignment_settings", Text),
    # ── D-090 — resolved CURRENT-season draft order (backend/pick_slots.py) ─
    # JSON {schema, season, teams, type, reversal_round, slots:{roster_id:slot},
    # source}. Written by the Sleeper owned-pick sync from the `draft_order`
    # already present on the /league/<id>/drafts payload it fetches, so it
    # costs no extra upstream call. Same rule as the column above and for the
    # same reason: the ORDER is stored, the SLOT never is — a commissioner
    # reordering the draft must renumber every slot without touching a single
    # owner, which a denormalized draft_picks.slot could not express (D18).
    # Season-stamped, so a future season resolves nothing (#273).
    # NULL = unresolved → owned picks keep today's generic round label.
    Column("draft_slot_order", Text),
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
    # #318 — awaiting-dismiss. ISO UTC when the user retracted this like from
    # the "Awaiting them" list; NULL = live. A retracted like is invisible to
    # load_awaiting_trades / load_recent_league_likes / check_for_match, but
    # the row itself is never rewritten: swipe-Elo history, impressions
    # training joins and _past_decision_keys deliberately still see it (a
    # dismissed offer must not resurface in the DISMISSER's own deck). A
    # later re-like writes a fresh row with NULL — that is the revive path.
    Column("retracted_at",       String),
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

# FB-147 — Sleeper trade-block snapshot, per league. One row per asset a
# manager currently has "on the block" in the Sleeper app. Replaced
# atomically on every sync (delete + insert, snapshot semantics like
# member_rankings). Source: Sleeper GraphQL `league_players` (public,
# unauthenticated read; settings.otb = flagging roster_id,
# settings.otb_added_at = epoch ms) — see backend/trade_block_service.py.
# Only flags whose flagging roster still owns the player survive a sync
# (Sleeper never clears stale otb rows after a player moves).
trade_block_table = Table("trade_block", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("league_id",  String,  nullable=False),
    Column("player_id",  String,  nullable=False),
    Column("user_id",    String),   # Sleeper user who owns + flagged the player
    Column("roster_id",  Integer),  # Sleeper roster_id that flagged it (raw otb value)
    Column("flagged_at", String),   # ISO UTC from otb_added_at; NULL on legacy leagues
    Column("synced_at",  String,  nullable=False),
    UniqueConstraint("league_id", "player_id", name="uq_trade_block"),
)

# Market-data readiness (PRD #43 Phase-1 data foundation, backlog #26) —
# executed Sleeper league trades, captured RAW during session_init's
# background daemon (backend/sleeper_trades_service.py, flag
# `market.trade_capture`). Capture only: no scoring, no aggregation, no UI.
# `raw` retains the full Sleeper transaction payload so a future
# observed-market model can re-derive anything the normalized columns
# don't carry. Idempotent on transaction_id (append-only; a trade never
# mutates after completion).
sleeper_trades_table = Table("sleeper_trades", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("transaction_id", String,  nullable=False),  # Sleeper transaction id
    Column("league_id",      String,  nullable=False),
    Column("week",           Integer),                  # Sleeper `leg`
    Column("traded_at",      String),                   # ISO UTC from status_updated (ms)
    Column("synced_at",      String,  nullable=False),  # ISO UTC capture time
    Column("roster_ids",     Text),                     # JSON: participating roster_ids
    Column("adds",           Text),                     # JSON: {player_id: receiving roster_id}
    Column("drops",          Text),                     # JSON: {player_id: sending roster_id}
    Column("draft_picks",    Text),                     # JSON: traded pick objects (season/round/owners)
    Column("waiver_budget",  Text),                     # JSON: FAAB transfers in the trade
    Column("raw",            Text,    nullable=False),  # JSON: full Sleeper transaction payload
    UniqueConstraint("transaction_id", name="uq_sleeper_trade_txid"),
)
Index("ix_sleeper_trades_league", sleeper_trades_table.c.league_id)

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
    # Per-user "archived from my inbox" flag (0|1|NULL). Distinct from
    # decision: dismissing carries NO ELO signal and never reveals/affects
    # the other party — it just hides the match from THIS user's Matches
    # list permanently (see dismiss_match + load_matches filter).
    Column("user_a_dismissed", Integer),
    Column("user_b_dismissed", Integer),
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


# Every trade card SHOWN to a user (one row per card per completed generation
# job) — the implicit-negative side of the acceptance-model training data
# (Tier 2 work item 2.4). Decisions live in trade_decisions; joining the two
# on (user_id, league_id, give/receive sets) labels each impression.
# Written by log_trade_impressions(), called from server._run_trade_job when
# a finished deck snapshot is stored (once per job, not per poll).
trade_impressions_table = Table("trade_impressions", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("user_id",            String,  nullable=False),  # user the deck was generated for
    Column("league_id",          String,  nullable=False),
    Column("target_user_id",     String),                   # counterparty on the card
    Column("give_player_ids",    Text,    nullable=False),  # JSON array (user's give side)
    Column("receive_player_ids", Text,    nullable=False),  # JSON array (user's receive side)
    Column("basis",              String),                   # 'divergence' | 'consensus'
    Column("likes_you",          Integer),                  # 0|1 — counterparty pre-liked mirror
    Column("mismatch_score",     Float),
    Column("fairness_score",     Float),
    Column("composite_score",    Float),
    Column("position_in_deck",   Integer),                  # 0 = top card
    Column("shown_at",           String),                   # ISO timestamp
)

# Training queries scan one user-league at a time; new table so
# metadata.create_all() creates table + index together on both dialects.
Index(
    "ix_trade_impressions_user_league",
    trade_impressions_table.c.user_id,
    trade_impressions_table.c.league_id,
)


# ── TikTok-discovery F1 (flag deck.signal_v2) — impression_id spine ─────────
# docs/plans/tiktok-discovery/prds/F1-signal-foundation.md. Additive tables:
# trade_impressions / trade_decisions / the Elo pipeline are untouched.
#
# deck_impressions: ONE row per card in the FINAL SERVED deck order, written
# once per completed generation job by server._run_trade_job (never per
# /status poll), only when the flag is on. features_json is FROZEN at serve
# time (never recomputed at label time — training/serving skew) and carries
# the card attributes the generation path already computed (shape, archetype/
# lane, basis, positions, values + bands, pick involvement, partner id,
# surplus margin) plus board-state-at-serve (ranked_player_count,
# last_board_update_at, user_value_basis). `propensity` is the Thompson
# sort-key multiplier ACTUALLY applied to this card (1.0 when ordering was
# off/deterministic) — the off-policy-evaluation prerequisite.
deck_impressions_table = Table("deck_impressions", metadata,
    Column("impression_id", String,  primary_key=True),  # uuid4 hex, minted at serve
    Column("user_id",       String,  nullable=False),    # user the deck was served to
    Column("league_id",     String,  nullable=False),
    Column("deck_job_id",   String,  nullable=False),    # _trade_jobs job_id
    Column("card_index",    Integer, nullable=False),    # 0 = top card, final served order
    Column("trade_hash",    String),                     # stable hash of give|receive|partner
    Column("features_json", Text),                       # frozen at serve time (JSON object)
    Column("propensity",    Float,   nullable=False),    # Thompson multiplier drawn for this card
    Column("base_score",    Float),                      # composite_score before presentation
    Column("final_score",   Float),                      # ordering key after multipliers/penalties
    Column("archetype",     String),                     # lane/basis-derived label when available
    Column("shape_bucket",  String),                     # "1x1", "2x1", … (Thompson arm)
    Column("served_at",     String,  nullable=False),    # ISO UTC
    # F3 (deck.fatigue) — highest-consensus asset in the package, the
    # per-item fatigue key. Populated only while deck.fatigue is on
    # (NULL otherwise / on pre-F3 rows); additive via _migrate_db.
    Column("centerpiece_id", String),
    # ── suggestion.telemetry (matchmaking item 1; scope block:
    # docs/plans/matchmaking-engine/telemetry-scope.md) — counterfactual
    # columns, all NULL while the flag is off / on pre-telemetry rows;
    # additive via _migrate_db, no backfill.
    #   is_ghost: 1 = ghost suggestion — logged fully but deterministically
    #     WITHHELD from display (per league × ISO week × trade_hash, ~1-in-N
    #     via model_config ghost_holdout_one_in). Ghost rows never receive
    #     deck_outcomes, so outcome-joined reads ignore them naturally; their
    #     card_index is the WOULD-HAVE-BEEN rank in the pre-withhold order
    #     (served rows keep true served positions).
    #   policy_version: serving-policy id (engine version + ordering-layer
    #     flags + suggestion_telemetry.POLICY_REV) — the OPE attribution key.
    #   candidate_set_id / candidate_set_size: join key + denormalized size
    #     of the deck_candidate_sets row this card was chosen from.
    #   assets_json: {"give": [...], "receive": [...]} asset-id bundle,
    #     first-class (trade_hash alone can't be inverted) — what the
    #     executed-trade matcher compares against Sleeper trades.
    Column("is_ghost",           Integer),
    Column("policy_version",     String),
    Column("candidate_set_id",   String),
    Column("candidate_set_size", Integer),
    Column("assets_json",        Text),
    # ── trade.bakeoff (three-model bake-off Phase 3; scope block:
    # docs/plans/three-model-bakeoff/scope-phase3.md) — per-card model
    # attribution. NULL while the flag is off / on every pre-bake-off row;
    # additive via _migrate_db, no backfill.
    #   model_arm: 'baseline' | 'current' | 'gen_v2' — the arm that PRODUCED
    #     this card. Denormalized from policy_version (which also encodes it
    #     as '<policy>/bo:<arm>') so no query has to parse a string. NULL on
    #     a served card no arm produced — e.g. a likes-you injection.
    #   arm_rank: the card's 0-based rank within its OWN arm's ranked list,
    #     never its deck position (that is card_index). The pair
    #     (model_arm, arm_rank, card_index) is what separates model quality
    #     from deck-position effects.
    Column("model_arm",          String),
    Column("arm_rank",           Integer),
    #   fairness_threshold: the consensus fairness bar this card ACTUALLY had
    #     to clear. The client sends a per-request value (0.75 fairness toggle
    #     on / 0.50 off) which the engine then composes per card — relaxed
    #     (#189) cards ride min(requested, relaxed_fairness_threshold), and
    #     divergence cards ride min(…, fairness_floor_divergence) while
    #     consensus cards keep the full bar. Before this it was persisted
    #     NOWHERE (docs/reviews/2026-08-18-trade-logic-archaeology.md), so a
    #     per-arm comparison spanning sessions with different client settings
    #     compared arms AND thresholds at once. NULL on an arm `gen_v2` card
    #     (trade_gen_v2 takes no fairness_threshold — its bar is the gen2_*
    #     stack), which is the honest answer, not missing data.
    Column("fairness_threshold", Float),
    #   group_key / group_rank / lane_slot: the deck-composition half of the
    #     attribution (operator decision 2026-08-18, scope block
    #     docs/plans/three-model-bakeoff/scope-composition.md). The served
    #     deck is built from GROUPS — (arm, basis) units quota'd 5 value /
    #     5 outlook — and the groups, not the arms, are what interleave.
    #     group_key: 'current_divergence' | 'current_consensus' | 'gen_v2'
    #       on the default roster; which group's quota this card filled.
    #     group_rank: 0-based rank inside that group's composed list. Distinct
    #       from arm_rank (rank in the arm's own FULL ranked list) and from
    #       card_index (deck position) — the three answer different questions
    #       and all three are recorded.
    #     lane_slot: 'value' | 'outlook' | 'fill'. 'fill' means the card took
    #       a residual slot its own lane did not earn (only reachable under
    #       model_config bakeoff_fill_policy = 1, or when the lane axis is
    #       undefined for the deck), so no analysis can mistake a backfill for
    #       a card that genuinely filled an outlook quota. NOTE (D-086): lane
    #       REALLOCATION does not produce 'fill' — a value card that took a
    #       slot the outlook lane could not use is still stamped 'value',
    #       because it is a value-lane card in a value slot; the group's
    #       realized split is groups_json[key].filled and the spill is
    #       groups_json[key].realloc.
    #     All three NULL on a card no group produced — a likes-you injection,
    #     a dark-mode deck, or a run with composition killed.
    #     The card's own `basis` and `lane` are already on features_json (and
    #     `lane` additionally on the `archetype` column), so the arm / basis /
    #     lane / group / rank slice PLAN.md §6 needs is complete without
    #     duplicating either field here.
    Column("group_key",          String),
    Column("group_rank",         Integer),
    Column("lane_slot",          String),
    #   trade_intent: the EFFECTIVE #172 intent lens this card was filtered
    #     under — 'consolidate' | 'tier_up' | 'tier_down', or NULL for an
    #     unfiltered deck. Like fairness_threshold this was persisted NOWHERE
    #     before, and like it the requested and effective values genuinely
    #     diverge: `_generate_trades_impl` resolves the request to None
    #     whenever `trades.intent_modes` is off, and the route already drops
    #     values outside the three modes. The user-facing trade settings stay
    #     visible during the bake-off (operator decision 2026-08-18 — testers
    #     are briefed verbally), so a tester CAN switch the intent chip
    #     mid-test; the resulting shift in each group's basis/lane mix would
    #     otherwise be invisible in the data.
    Column("trade_intent",       String),
)

Index(
    "ix_deck_impressions_user_league",
    deck_impressions_table.c.user_id,
    deck_impressions_table.c.league_id,
)
Index(
    "ix_deck_impressions_job",
    deck_impressions_table.c.deck_job_id,
)

# ── suggestion.telemetry — candidate-set reconstruction ─────────────────────
# One row per completed generation job while the flag is on: the FULL action
# set the serving policy chose from at ordering time — the post-gate,
# pre-withhold deck (served + ghost cards) plus the untrimmed F7 exploration
# over-generation pool (D-scope-6). candidates_json members:
# {trade_hash, partner, give, receive, base_score, in_deck}. set_hash =
# sha256 over the sorted member trade_hashes (16 hex chars, same truncation
# as trade_hash itself) — the cheap "same candidate set?" comparator across
# jobs. Soft-referenced from deck_impressions.candidate_set_id (no FK,
# matching this schema's style).
deck_candidate_sets_table = Table("deck_candidate_sets", metadata,
    Column("candidate_set_id", String,  primary_key=True),  # uuid4 hex
    Column("deck_job_id",      String,  nullable=False),
    Column("user_id",          String,  nullable=False),
    Column("league_id",        String,  nullable=False),
    Column("size",             Integer, nullable=False),
    Column("set_hash",         String,  nullable=False),
    Column("candidates_json",  Text,    nullable=False),
    Column("created_at",       String,  nullable=False),    # ISO UTC
)

Index(
    "ix_deck_candidate_sets_user_league",
    deck_candidate_sets_table.c.user_id,
    deck_candidate_sets_table.c.league_id,
)

# ── suggestion.telemetry — executed-trade tagging ───────────────────────────
# One row per captured sleeper_trades transaction examined by the matcher
# (suggestion_telemetry.match_league_trades, hooked after every
# sync_league_trades pass). was_recommended = 1 iff the trade matched a
# NON-ghost (actually rendered) logged suggestion under the D-scope-5
# similarity rule; the best GHOST match is linked separately — the
# ghost_* columns are the incrementality read (did a withheld suggestion
# execute anyway?). Multi-team / unresolvable trades get a row with
# match_type NULL so the always-on per-league ratio
# (SUM(was_recommended) / COUNT(*)) keeps an honest denominator.
suggestion_trade_links_table = Table("suggestion_trade_links", metadata,
    Column("id",                    Integer, primary_key=True, autoincrement=True),
    Column("transaction_id",        String,  nullable=False),  # sleeper_trades.transaction_id
    Column("league_id",             String,  nullable=False),
    Column("was_recommended",       Integer, nullable=False, default=0),
    Column("matched_impression_id", String),   # best non-ghost match
    Column("match_type",            String),   # 'exact' | 'partial' | NULL
    Column("overlap_score",         Float),
    Column("ghost_impression_id",   String),   # best ghost match
    Column("ghost_match_type",      String),
    Column("ghost_overlap_score",   Float),
    Column("traded_at",             String),
    Column("computed_at",           String,  nullable=False),
    UniqueConstraint("transaction_id", name="uq_suggestion_link_txid"),
)

Index(
    "ix_suggestion_trade_links_league",
    suggestion_trade_links_table.c.league_id,
)

# ── trade.bakeoff — three-model bake-off run ledger ─────────────────────────
# docs/plans/three-model-bakeoff/PLAN.md §5. ONE row per organic trade job
# while the flag is on: the per-JOB half of the bake-off record (the per-CARD
# half rides deck_impressions.model_arm / .arm_rank). Written best-effort
# after the deck is assembled — a failure here never fails the job.
#
#   arm_order       — JSON list, the team-draft rotation this deck used
#                     (randomised per deck, seeded league_id + ISO week).
#   served_arm      — 'current' in Phase-4 dark validation (all three arms
#                     generated and logged, one arm served); NULL once
#                     interleaved serving is lit.
#   deck_size       — cards in the INTERLEAVED deck (computed and logged even
#                     in dark mode, where it is not what got served).
#   total_ms        — wall clock for all three generations.
#   arms_json       — {arm: {cards, gen_ms, empty, forfeits, served, error}}.
#                     `empty` is the PLAN.md §3.2 empty-arm rate's numerator;
#                     `forfeits` counts rotation slots the arm could not fill
#                     (arm gen_v2 is expected to forfeit — that is data, not
#                     an error). `error` is non-NULL only when an arm raised.
#   agreement_json  — {"armA+armB": n} counts of served cards both arms
#                     proposed (first picker credited; the duplicate ledger).
#                     Per ARM, not per group: groups 1 and 2 are the same arm
#                     on disjoint bases and can never collide.
#   groups_json     — {group_key: {arm, basis, quota, filled, short, pool,
#                     composed, served, lane_split_active}}. `short` is the
#                     per-(group, lane) UNDER-FILL and is the reason this
#                     column exists: `window` is ~19% of live divergence
#                     supply, so the divergence groups are expected to miss
#                     their outlook quota, and arm gen_v2's lane mix has never
#                     been observed. Recording the hole is the finding;
#                     backfilling it silently would erase it. `{}` when
#                     model_config bakeoff_group_size = 0 kills composition.
bakeoff_runs_table = Table("bakeoff_runs", metadata,
    Column("run_id",         String,  primary_key=True),   # uuid4 hex
    Column("deck_job_id",    String,  nullable=False),     # _trade_jobs job_id
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String,  nullable=False),
    Column("arm_order",      Text,    nullable=False),
    Column("served_arm",     String),                      # NULL ⇒ interleaved
    Column("deck_size",      Integer, nullable=False),
    Column("total_ms",       Integer),
    Column("arms_json",      Text,    nullable=False),
    Column("agreement_json", Text),
    Column("groups_json",    Text),
    #   config_json — {"base": <arm current's effective trade_service config>,
    #     "arm_delta": {arm: {changed keys}}}. `model_config` has no
    #     `updated_at`, so a knob's change date is otherwise unknowable after
    #     the fact; snapshotting per run makes every card traceable to the
    #     configuration that produced it. Stored whole rather than hashed — a
    #     fingerprint would say the config changed without saying to what.
    Column("config_json",    Text),
    Column("created_at",     String,  nullable=False),     # ISO UTC
)

Index(
    "ix_bakeoff_runs_league",
    bakeoff_runs_table.c.league_id,
)
Index(
    "ix_bakeoff_runs_job",
    bakeoff_runs_table.c.deck_job_id,
)

# deck_outcomes: append-only labels joined to deck_impressions by
# impression_id (soft reference — no FK constraint, matching this schema's
# style; late/duplicate labels are legal and rows are NEVER mutated).
# action ∈ viewed | like | pass | not_interested | propose | undo.
# `viewed` = card was front-of-deck ≥500ms client-side (served ≠ viewed);
# `not_interested` rides the bad-trade flag; `undo` appends alongside (not
# instead of) whatever the original outcome row was.
deck_outcomes_table = Table("deck_outcomes", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("impression_id",   String,  nullable=False),  # deck_impressions.impression_id
    Column("action",          String,  nullable=False),
    Column("dwell_ms",        Integer),                  # card-front → disposition, capped 120s
    Column("detail_expanded", Integer),                  # 0|1|NULL — opened menu/swap/keep-side
    Column("calc_opened",     Integer),                  # 0|1|NULL — edit-in-calculator (#190)
    Column("acted_at",        String,  nullable=False),  # ISO UTC (server clock)
)

Index(
    "ix_deck_outcomes_impression",
    deck_outcomes_table.c.impression_id,
)

# ── TikTok-discovery F3 (flag deck.fatigue) — durable decline suppression ───
# docs/plans/tiktok-discovery/prds/F3-fatigue-suppression.md. One row per
# decline/proposal-kill: near-duplicates (same centerpiece + same shape
# bucket + package value within ±fatigue_decline_value_band) are removed
# from that user's decks until expires_at. After expiry the row grants
# exactly ONE low-exposure retest card (retested_at/retest_trade_hash record
# it); a pass on the retest re-arms the row for another window — resolved
# lazily at the next generation, no write hooks in the swipe path. `lifted_at`
# is the user's "Undo": a lifted row is permanently inert. Soft pass-fatigue
# is NOT stored here — it is derived on read from deck_impressions ⨝
# deck_outcomes (F2 pattern); the only stored soft-fatigue state is the
# per-user reset marker below.
deck_suppressions_table = Table("deck_suppressions", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("user_id",           String,  nullable=False),
    Column("league_id",         String,  nullable=False),
    Column("centerpiece_id",    String,  nullable=False),  # highest-consensus asset in the declined package
    Column("shape_bucket",      String,  nullable=False),  # "1x1", "2x1", …
    Column("package_value",     Float),                    # consensus give+receive value at decline; NULL ⇒ band test skipped
    Column("declined_at",       String,  nullable=False),  # ISO UTC
    Column("expires_at",        String,  nullable=False),  # declined_at + fatigue_decline_suppress_days
    Column("retested_at",       String),                   # ISO — when the ONE post-window retest card was served
    Column("retest_trade_hash", String),                   # F1 trade_hash of the served retest card
    Column("lifted_at",         String),                   # user undo — row inert once set
    Column("created_at",        String,  nullable=False),
)

Index(
    "ix_deck_suppressions_user_league",
    deck_suppressions_table.c.user_id,
    deck_suppressions_table.c.league_id,
)

# F3 — per-user-league soft-fatigue reset marker ("Refresh my deck").
# Fatigue reads ignore viewed/pass events before reset_at; decline
# suppressions (table above) and not-interested/untouchables are unaffected.
deck_fatigue_resets_table = Table("deck_fatigue_resets", metadata,
    Column("user_id",   String, primary_key=True),
    Column("league_id", String, primary_key=True),
    Column("reset_at",  String, nullable=False),   # ISO UTC
)

# ── TikTok-discovery F10 (flag deck.replenishment) — weekly marker ──────────
# docs/plans/tiktok-discovery/prds/F10-deck-replenishment.md. One row per
# (user, league, ISO week) the weekly replenishment cron pre-generated a deck
# for. The unique constraint IS the idempotency gate: re-running daily-tick
# in the same week finds the row and skips both the regeneration and the
# push (hard 1/week/league cap). deck_size / expired_count are kept for
# operator inspection of what the push claimed.
deck_replenish_log_table = Table("deck_replenish_log", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("user_id",       String,  nullable=False),
    Column("league_id",     String,  nullable=False),
    Column("iso_week",      String,  nullable=False),   # e.g. "2026-W30"
    Column("deck_size",     Integer),                   # cards in the pre-generated deck
    Column("expired_count", Integer),                   # prior-deck cards dropped past 7d expiry
    Column("created_at",    String,  nullable=False),   # ISO UTC
    UniqueConstraint("user_id", "league_id", "iso_week",
                     name="uq_deck_replenish_week"),
)

# ── TikTok-discovery F5 (flag deck.taste_vectors) — taste vectors ───────────
# docs/plans/tiktok-discovery/prds/F5-taste-vectors.md. Per-user decayed
# attribute-preference weights (the Monolith long/short interest split
# without embeddings): one lazily-created row per (user, attribute key),
# updated synchronously on every F1 deck_outcomes write and GC'd on
# read/update when both decayed weights fall below the taste_epsilon floor
# (Monolith admission/expiry in SQL). Rows whose attr carries the "prior:"
# prefix hold the BOARD-DERIVED long-τ prior (PRD amendment 2026-07-26):
# they are rewritten wholesale on board saves by replace_user_taste_prior,
# never touched by outcome updates, and folded into the effective long
# vector at read time — so swipe-learned weights accumulate on top and
# dominate with volume. Math (decay, rewards, cosine, prior aggregation)
# lives in backend/taste_service.py; this table + the thin helpers below
# are the only storage. User-scoped by design (PRD schema): taste follows
# the manager across leagues; partner attrs are global user ids.
user_taste_table = Table("user_taste", metadata,
    Column("user_id",    String, primary_key=True),
    Column("attr",       String, primary_key=True),    # e.g. "recvpos:RB", "prior:pick:premium"
    Column("w_short",    Float,  nullable=False),      # τ_short decayed weight (21d default)
    Column("w_long",     Float,  nullable=False),      # τ_long decayed weight (180d default)
    Column("updated_at", String, nullable=False),      # ISO UTC of last decay+reward write
)

# ── TikTok-discovery F7 (flag deck.exploration) — archetype audition ─────────
# docs/plans/tiktok-discovery/prds/F7-exploration-slots.md §3. One GLOBAL row
# per archetype label (archetype = deck_impressions.archetype — lane today):
# the follower-blind staged pool. status ∈ test | general | retired:
#   test    — new/low-data archetype; served ONLY via wildcard slots until it
#             accrues audition_min_views viewed impressions across all users.
#   general — graduated (like-rate ≥ audition_like_rate_frac × the global
#             base rate at n ≥ audition_min_views) or grandfathered in with
#             enough all-time views; serves normally.
#   retired — failed its audition; excluded from decks AND wildcard draws
#             until retired_at + audition_retire_days, then re-enters test.
# viewed_impressions / likes are the counts of the CURRENT audition window
# (since entered_at), refreshed lazily at wildcard-draw time from
# deck_impressions ⨝ deck_outcomes (no cron; state machine lives in
# server._audition_statuses). entered_at/retired_at timestamps double as the
# transition log.
archetype_auditions_table = Table("archetype_auditions", metadata,
    Column("archetype",          String,  primary_key=True),
    Column("status",             String,  nullable=False),   # test | general | retired
    Column("viewed_impressions", Integer, nullable=False),   # viewed count since entered_at
    Column("likes",              Integer, nullable=False),   # liked-and-viewed count since entered_at
    Column("entered_at",         String,  nullable=False),   # ISO UTC — current window start
    Column("retired_at",         String),                    # ISO UTC — set while status='retired'
)


# ── Decline-reason capture (flag feedback.decline_reasons) ─────────────────
# docs/plans/decline-reason-capture/SPEC.md. The trade card's ✕ is replaced
# by three layer-1 tiles (Value · Fit · Neither); tapping one IS the pass, and
# layer 2 sharpens it. ONE row per passed card, keyed on the F1
# `impression_id` (deck_impressions.impression_id — soft reference, no FK,
# matching this schema's style).
#
# UPSERT, not append-only — and that is the one place this table deliberately
# departs from its deck_outcomes sibling. SPEC §3 is explicit: every tap
# commits on its own and a later tap must never lose an earlier one, so the
# row grows in place (layer 1 → layer 2 → free text). deck_outcomes could not
# host this: its rows are NEVER mutated by contract, it carries several rows
# per impression (viewed / pass / undo), and it has no unique key to upsert
# on. The pass DISPOSITION still lands in deck_outcomes as action='pass',
# exactly as the ✕ wrote it — this table is the reason, not the disposition.
#
# Column semantics:
#   reason         layer-1 code — value | fit | other. Never NULL once the
#                  row exists: the row is CREATED by the layer-1 tap, and a
#                  layer-2-first write derives it from the detail prefix.
#   detail         layer-2 code — value_giving | value_getting | value_other |
#                  fit_outlook | fit_new_weakness | fit_duplicate | fit_other |
#                  other_player_keep | other_player_avoid | other_text.
#                  NULL = the user stopped at layer 1, which is a first-class
#                  answer (SPEC §6: layer-1-without-layer-2 must be directly
#                  measurable). The two `other_player_*` codes were added
#                  2026-08-19 (SPEC §2 amendment): the "Neither" bucket was
#                  47% of the first production burst and its free text was
#                  overwhelmingly ONE reason — player-level preference — so it
#                  gained structured options and stopped being a black box.
#   free_text      the user's own words. STORED HERE AND NOWHERE ELSE — it
#                  is never an analytics property (SPEC §3.4), so no free text
#                  ever reaches user_events.props.
#   switched_from  the PRIOR layer-1 reason when the user moved to another
#                  tile, else NULL. Switching is a refinement, not a reset:
#                  a stored detail is kept even when it belonged to the prior
#                  reason (losing it would violate SPEC §3's never-lose rule).
#   elo_signal_at  ISO UTC of the Elo write this pass produced, or NULL when
#                  the reason suppressed it (SPEC §4). Doubles as the
#                  once-only guard: the write is claimed with a conditional
#                  UPDATE ... WHERE elo_signal_at IS NULL, so no sequence of
#                  retries or re-taps can double-count a pass into Elo.
#   key_source     'impression' | 'local' — whether the PK is a real
#                  deck_impressions id or the degraded surrogate (operator
#                  decision 2026-08-17: a client with no impression_id must
#                  still be recorded, never refused). Only 'impression' rows
#                  join to the F1 spine and are usable for off-policy
#                  evaluation; 'local' rows are honest reason counts with no
#                  card features behind them. Storing it explicitly means
#                  analysis never has to infer the distinction from a key
#                  prefix — the kind of implicit encoding that rots.
trade_pass_reasons_table = Table("trade_pass_reasons", metadata,
    Column("impression_id", String, primary_key=True),   # deck_impressions.impression_id
    Column("user_id",       String, nullable=False),
    Column("league_id",     String),
    Column("trade_id",      String),
    Column("key_source",    String),                     # impression | local
    Column("reason",        String),                     # value | fit | other
    Column("detail",        String),                     # 10 layer-2 codes; NULL = layer-1 only
    Column("free_text",     Text),                       # never an analytics prop
    Column("switched_from", String),                     # prior layer-1 reason, or NULL
    Column("elo_signal_at", String),                     # ISO UTC, or NULL = suppressed
    Column("created_at",    String, nullable=False),     # ISO UTC — the layer-1 tap
    Column("updated_at",    String, nullable=False),     # ISO UTC — the latest tap
)

Index(
    "ix_trade_pass_reasons_user_league",
    trade_pass_reasons_table.c.user_id,
    trade_pass_reasons_table.c.league_id,
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
    # #207 — Sleeper's `metadata.rookie_year` ("2026"), the exact "class of
    # YYYY" field. `years_exp` counts ACCRUED seasons, so a 2023 UDFA who
    # spent two years on a practice squad reads years_exp=1 — it is not a
    # class field. NULL when Sleeper carries no class year (camp bodies /
    # UDFAs) or when it serves the bogus "0"; consumers fall back to
    # years_exp==0 AND team IS NOT NULL. Read by draft_status detection.
    Column("rookie_year",           String),   # "YYYY" | None
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
# asset_preferences — per-player trade preferences (backlog #2, #163)
# ---------------------------------------------------------------------------
# Where league_preferences expresses intent at POSITION granularity, this
# table expresses it at PLAYER granularity, per league:
#   list_type='untouchable'    → never suggest trading this player AWAY
#                                (hard filter on the give side, all gen paths)
#   list_type='target'         → bias suggestions toward ACQUIRING this player
#                                (survives the prune + composite multiplier)
#   list_type='not_interested' → never suggest ACQUIRING this player (#163 —
#                                hard filter on the receive side; give side
#                                untouched)
# A player can't be on two lists in the same league (the unique constraint
# is on the player; the route enforces single membership). Add/remove history
# for the #65 label stream is captured via record_event (user_events), not here.
# ---------------------------------------------------------------------------
asset_preferences_table = Table("asset_preferences", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("league_id",  String,  nullable=False),
    Column("player_id",  String,  nullable=False),
    Column("list_type",  String,  nullable=False),   # 'untouchable' | 'target'
    Column("created_at", String),
    UniqueConstraint("user_id", "league_id", "player_id", name="uq_asset_pref"),
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
    Column("pick_value",        Float),                     # legacy 0-100 round-tier scale (pick-share ratios)
    Column("pool_value",        Float),                     # #158: engine/calculator value scale (elo_to_value units)
    # #158 introduced this as 'sleeper' | 'mfl' provenance and documented
    # "ESPN never writes rows". draft-extensions W3 (ADR-010) REVERSES that:
    # an ESPN league's picks can now be entered by its own members, so ESPN
    # rows exist and carry platform='espn'. `platform` records where the
    # LEAGUE lives; the new `source` column below records who asserted the
    # ROW. They answer different questions and both are load-bearing — the
    # two engine guards read `platform`, the containment reads `source`.
    Column("platform",          String),                    # 'sleeper' | 'mfl' | 'espn' — the LEAGUE's provenance
    # ── draft-extensions W3 (ADR-010) — user-asserted pick ownership ──────
    # source: NULL or 'platform' = platform-written. EVERY pre-W3 row has
    #   source IS NULL, and `load_draft_picks` DEFAULTS to platform-only, so
    #   every pre-existing read site is byte-identical with no backfill.
    #   THIS COLUMN IS THE CONTAINMENT.
    Column("source",            String),
    Column("assigned_by",       String),                    # FTF user_id of the LAST editor ('user' rows only)
    # ISO-8601 UTC. ALSO the optimistic-concurrency token: a PUT carries the
    # value it read and the UPDATE's WHERE compares it (assign_draft_pick).
    Column("assigned_at",       String),
    Column("synced_at",         String),
    UniqueConstraint("pick_id", name="uq_draft_pick_id"),
)

# ---------------------------------------------------------------------------
# recorded_picks — the live offline-draft feed (draft-extensions W3 M-D).
#
# An OFF-PLATFORM rookie draft has no platform object to read (operator
# ruling: ESPN has no rookie-draft concept), so this is the only record that
# a pick happened. It projects into GET /api/draft/board's picks[] and
# NOWHERE else — it never writes draft_picks, never sets
# leagues.draft_status*, and never marks a draft complete.
#
# `overall` is legitimate HERE and must NEVER leak onto a draft_picks row:
# draft_picks' grain is (league, season, round, original_roster) and its
# pick_id format cannot express a slot.
#
# Undo is non-destructive: voided_at is a nullable ISO string, IS NULL means
# live, never a DELETE. A correction at an already-recorded `overall` UPDATEs
# the row in place (voided_at back to NULL) — see record_draft_picks.
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
    # THE idempotency gate for the offline queue: (league_id, season, overall).
    UniqueConstraint("league_id", "season", "overall", name="uq_recorded_pick_slot"),
    Index("ix_recorded_picks_league_season", "league_id", "season"),
)

# ---------------------------------------------------------------------------
# notifications_table — in-app notification inbox
# ---------------------------------------------------------------------------
#
# type: a CROSS-CLIENT ENUM — both clients map it to a glyph and a tap
#   destination from independent tables, and an unknown value degrades to a
#   grey bell with a dead tap rather than an error. Adding a value here
#   without adding it to BOTH clients is therefore silent, not loud. The
#   authoritative list is docs/cross-client-invariants.md § Notification
#   types; mirrors are mobile TopBar.tsx ROW_GLYPHS + deepLinks.ts V2_*
#   sets, and web/js/app.js notifTypeIcon + clickNotif.
#     trade_match · trade_accepted · trade_declined · referral_joined ·
#     league_member_joined · league_member_unlocked_trades ·
#     match_expiring · deck_replenished · counter_offer
# metadata_json: JSON-encoded dict with context fields, e.g.:
#   { "match_id": 42, "partner_username": "joe", "give": ["CeeDee Lamb"], "receive": ["Tyreek Hill"] }
# is_read: 0 = unread, 1 = read
# dismissed_at: ISO UTC when the user cleared the row, NULL = live. Read
#   filters it out (get_notifications). Distinct from is_read on purpose —
#   "I have seen this" and "I am done with this" are different facts, and
#   collapsing them is what made "Clear all" a lie on both clients.
# ---------------------------------------------------------------------------

notifications_table = Table("notifications", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("user_id",       String,  nullable=False),
    Column("type",          String,  nullable=False),   # see the enum above
    Column("title",         String),
    Column("body",          String),
    Column("metadata_json", Text,    default="{}"),
    Column("is_read",       Integer, default=0),        # 0 = unread, 1 = read
    Column("created_at",    String),
    Column("dismissed_at",  String),                    # NULL = live
)

# ---------------------------------------------------------------------------
# app_feedback_table — in-app feedback notes synced from clients
# ---------------------------------------------------------------------------
#
# Authoritative store for feedback notes that users save via the mobile
# FeedbackSheet (and eventually web). Mobile keeps a local copy in
# AsyncStorage and POSTs to /api/feedback in the background; this table is
# the canonical record so external TestFlight testers' notes land without
# any manual share-sheet action.
#
# client_id: load-bearing dedup key. Mobile may retry the same note
#   multiple times (background sync, foreground retry); we ignore
#   duplicates so retries are idempotent.
# user_id / username: best-effort session attribution. Null = anonymous
#   submission (pre-sign-in flows are allowed).
# severity: 'bug' | 'polish' | 'idea' — see cross-client-invariants.md.
# ---------------------------------------------------------------------------

app_feedback_table = Table("app_feedback", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("client_id",         String,  nullable=False, unique=True),
    Column("user_id",           String),                  # nullable — anonymous allowed
    Column("username",          String),                  # denormalized snapshot
    Column("screen",            String,  nullable=False),
    Column("severity",          String,  nullable=False), # bug | polish | idea
    Column("text",              Text,    nullable=False),
    Column("app_version",       String),
    Column("platform",          String),                  # ios | android
    Column("device_type",       String),                  # iphone | ipad | macos
    Column("os_version",        String),
    Column("client_created_at", String),                  # ISO from client
    Column("created_at",        String,  nullable=False), # ISO from server (canonical)
    # Operator-managed lifecycle status. NULL is read as 'new' so the
    # submission INSERT never has to mention the column (keeps the locked
    # POST /api/feedback contract byte-identical — see save_feedback).
    Column("status",            String),                  # see FEEDBACK_STATUSES
    Column("status_updated_at", String),                  # ISO, set on status change
    Index("idx_app_feedback_created_at", "created_at"),
    Index("idx_app_feedback_user_id",    "user_id"),
)

# Lifecycle vocabulary for app_feedback.status. Mirrored by the mobile
# inbox's status chips (mobile/src/screens/FeedbackInboxScreen.tsx) — keep
# docs/cross-client-invariants.md in sync if this changes.
FEEDBACK_STATUSES = ("new", "planned", "in_progress", "fixed", "shipped", "declined")
# Terminal statuses hidden from the user's in-app inbox (FB privacy/cleanup,
# 2026-07-04). "fixed" stays VISIBLE — its chip ("Fixed — in next update")
# is the notification that a fix is coming; it flips to "shipped" (hidden)
# when the build ships. Mirrored client-side in mobile/src/api/feedback.ts
# (CLOSED_FEEDBACK_STATUSES) — keep the two in sync.
FEEDBACK_CLOSED_STATUSES = ("shipped", "declined")
# Severity vocabulary — mirrors the POST /api/feedback contract (locked;
# the submit route validates inline and is deliberately untouched).
FEEDBACK_SEVERITIES = ("bug", "polish", "idea")

# ---------------------------------------------------------------------------
# bad_trade_flags — engine-quality feedback loop (FB #85)
# ---------------------------------------------------------------------------
# "This is a bad trade" flags from the TradesHome swipe deck. Distinct from a
# pass (not interested): a flag means "the engine got this one wrong" and is
# reviewed by the operator to iterate on the trade-generation logic. Each row
# snapshots everything needed to reproduce/critique the card later — the
# package, the counterparty, and the engine telemetry at flag time.
#
# dedupe_key = "user|league|sorted(give)|sorted(receive)" — one flag per user
# per trade package. Retries / re-flags of the same card hit the unique
# constraint and are dropped (same idempotent-insert pattern as
# app_feedback.client_id; see save_bad_trade_flag).
# ---------------------------------------------------------------------------

bad_trade_flags_table = Table("bad_trade_flags", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("dedupe_key",         String,  nullable=False, unique=True),
    Column("user_id",            String,  nullable=False),
    Column("username",           String),                  # denormalized snapshot
    Column("league_id",          String,  nullable=False),
    Column("target_user_id",     String),                  # counterparty on the card
    Column("target_username",    String),                  # denormalized snapshot
    Column("give_player_ids",    Text,    nullable=False), # JSON array (flagger's give side)
    Column("receive_player_ids", Text,    nullable=False), # JSON array (flagger's receive side)
    Column("scoring_format",     String),                  # '1qb_ppr' | 'sf_tep'
    Column("trade_id",           String),                  # ephemeral card id (correlation only)
    # Engine telemetry at flag time — nullable; sourced from the in-memory
    # card when it's still alive, else from client-echoed fallback values.
    Column("mismatch_score",     Float),
    Column("fairness_score",     Float),                   # 0–1
    Column("composite_score",    Float),
    Column("need_fit",           Float),                   # 0–1 (FB-96), null when flag off
    Column("partner_fit",        Float),                   # 0–1 (FB-47), null when not stamped
    Column("basis",              String),                  # 'divergence' | 'consensus'
    Column("reason",             Text),                    # optional user free-text
    Column("created_at",         String,  nullable=False), # ISO from server (canonical)
    Index("idx_bad_trade_flags_created_at", "created_at"),
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
# player_value_history — daily CONSENSUS value snapshots (backlog #57 / #17)
# ---------------------------------------------------------------------------
# elo_history above logs each USER's personal Elo. This table logs the
# market/consensus side: one row per universal-pool player per scoring
# format per day, written by POST /api/cron/value-snapshot. The
# DynastyProcess-seeded universal pool is rebuilt from the live CSV on every
# boot, so yesterday's consensus numbers are otherwise lost forever — this is
# pure data retention, started before the profile UI (#17) so value-history
# charts, the movers digest (#33), and Wrapped (#46) have history to draw on.
#
# consensus_value is stored denormalised alongside consensus_elo so a later
# elo_value_* config change does not silently rewrite recorded history.
# ---------------------------------------------------------------------------
player_value_history_table = Table("player_value_history", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("player_id",       String,  nullable=False),
    Column("scoring_format",  String,  nullable=False),    # '1qb_ppr' | 'sf_tep'
    Column("consensus_elo",   Float,   nullable=False),    # seed Elo at snapshot time
    Column("consensus_value", Float),                      # elo_to_value(consensus_elo)
    Column("search_rank",     Integer),                    # Sleeper rank proxy, if known
    Column("adp",             Float),                       # ADP, if known
    Column("snapshot_date",   String,  nullable=False),    # "YYYY-MM-DD" UTC
    UniqueConstraint("player_id", "scoring_format", "snapshot_date",
                     name="uq_value_snapshot"),
)

# ---------------------------------------------------------------------------
# league_roster_history — append-only league-state snapshots (#46 Wrapped)
# ---------------------------------------------------------------------------
# ADR-011. player_value_history above logs the MARKET side daily; this logs
# the OWNERSHIP side. A team's value is roster x values — this is the half
# that league_members.roster_data was overwriting on every sync (zero rows
# of history before 2026-08).
#
# WRITTEN FROM three triggers, one idempotent writer (roster_history.py):
#   A. on-sync — beside the two league_members writers, in its OWN
#      transaction AFTER theirs commits. NEVER inside
#      replace_espn_league_members' engine.begin() block: a snapshot
#      failure there would roll back the delete+insert and leave the league
#      with ZERO members (and G-040 rules out begin_nested as a middle
#      ground on main-engine SQLite).
#   B. the daily-tick weekday >= gate (server-side fetch, every platform,
#      every team — YR-6/YR-8).
#   C. POST /api/cron/roster-snapshot — the manual/external lever.
#
# team_key is the platform-native TEAM SLOT, never derived from a user id:
#   sleeper:<lid>.r<roster_id> | espn:<lid>.t<team_id>
#   | mfl:<lid>.f<franchise_id> | fleaflicker:<lid>.t<team_id>
# ESPN's synthetic member id is SWID-first and SWID rotates on re-import
# (see the orphaned-pick notes below), so a user_id-derived key would split
# one team's season into partial charts with no error anywhere.
# owner_user_id is a nullable, RE-STAMPABLE attribute — resolved forward
# via leagues.espn_my_team_id / platform_my_team when a manager later
# links. The re-stamp does not violate append-only: the FACT ("team T held
# roster R in period P") never changes; only our knowledge of who was
# behind T does.
#
# PRECEDENCE, NOT RECENCY, on upsert: 'weekly' (server-fetched, every team,
# orphans included) outranks 'sync' (client-posted, drops ownerless
# rosters). The on-sync writer does nothing when a 'weekly' row already
# holds the period; the weekly writer does a full update. Recency here
# would let a Friday app-open silently delete the week's orphan teams and
# break YR-6 invisibly.
#
# team_value is denormalised alongside the roster ids for the reason
# player_value_history denormalises consensus_value: a later model change
# must not rewrite the shape of a season chart already shown to a user.
# It is compute_power_rankings' consensus-basis players total — NEVER a
# fresh summation (or the Wrapped chart and the Power Rankings screen show
# different numbers for the same team). NULL, never 0, when nothing
# prices: a zero renders as a roster wipe; a NULL renders as a gap. Charts
# grey any week where team_value IS NULL or valued_player_count <
# 0.8 * player_count, and never interpolate.
# ---------------------------------------------------------------------------
league_roster_history_table = Table("league_roster_history", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("league_id",          String,  nullable=False),
    Column("team_key",           String,  nullable=False),
    # 'strong' = platform-native slot id. 'weak' = user_id-derived fallback
    # (Sleeper sync with no roster map in hand). The recap DECLINES to
    # chart weak-keyed teams rather than fragmenting them silently — weak
    # keys are visible and countable; silent fragmentation is neither.
    Column("team_key_quality",   String,  nullable=False),  # 'strong'|'weak'
    Column("platform",           String,  nullable=False),  # sleeper|espn|mfl|fleaflicker
    Column("owner_user_id",      String),  # NULLABLE ATTRIBUTE, never part of the key
    Column("scoring_format",     String,  nullable=False),  # '1qb_ppr'|'sf_tep'
    # BUCKET LABEL, not an instant — '2026-W33' from now.isocalendar(),
    # the deck_replenish_log.iso_week shape. Uses the ISO week-numbering
    # YEAR, never .year: 2026-12-31 is 2027-W01, and a %Y-keyed label
    # would sort and dedupe wrong at the boundary. An instant in the key
    # (the plan's original snapshot_at sketch) enforces nothing — two runs
    # in one week would make two rows and "value at week W" two answers.
    Column("period_key",         String,  nullable=False),
    Column("period_kind",        String,  nullable=False),  # 'week' today; 'day' later
    Column("snapshot_date",      String,  nullable=False),  # 'YYYY-MM-DD' — the pvh join key
    Column("snapshot_at",        String,  nullable=False),  # ISO UTC instant of the write
    Column("player_ids",         Text,    nullable=False),  # JSON array, SORTED
    Column("starter_ids",        Text),   # platform-set lineup (the historical FACT;
                                          # the optimal lineup is an ANALYSIS, derivable
                                          # at read time — capture inputs, compute outputs)
    Column("pick_ids",           Text),   # JSON array of draft_picks.pick_id —
                                          # uncontested, unorphaned only (P1 fold-in;
                                          # nullable from day one)
    # Contested/orphaned slots excluded from pick_ids at snapshot time, so
    # an ESPN league with contested assertions is DISTINGUISHABLE from one
    # that owned no picks. Non-empty => the recap suppresses pick flow for
    # this league entirely rather than rendering it partially.
    Column("pick_ids_excluded",  Text),
    Column("pick_source",        String),  # 'platform'|'user'|'mixed' — ADR-010:
                                           # 'user' => never render pick flow as fact
    # sha256(",".join(sorted ids)).hexdigest()[:16] — set semantics. NEVER
    # suppresses the weekly write: team_value moves weekly even when the
    # roster does not, and a hash-suppressed grid puts holes in exactly the
    # chart YR-2 exists to stabilise. Its jobs are changed_from_prev and
    # suppressing EXTRA intra-week on-sync writes.
    Column("roster_hash",        String,  nullable=False),
    Column("changed_from_prev",  Integer),  # 0|1|NULL(first observation)
    Column("player_count",       Integer, nullable=False),
    # Of player_count, how many priced. The universal pool is DP-seeded
    # skill positions only, while league_members stores RAW client ids
    # including K/DEF (#151) — so a roster is never fully priced, and this
    # is what keeps the gap legible instead of invisible.
    Column("valued_player_count", Integer, nullable=False),
    Column("team_value",         Float),   # players only; NULL when nothing prices
    Column("team_value_picks",   Float),   # SEPARATE: pick pool_value is a different
                                           # pipeline than player consensus
    Column("value_basis_date",   String),  # the pvh snapshot_date actually used
                                           # (nearest <= target)
    Column("in_season",          Integer), # 0|1|NULL — distinguishes an alarming gap
                                           # from an off-season no-op; NULL in P0
    # 'sync' (client-posted at a league open) | 'weekly' (server-fetched
    # sweep — daily-tick gate or the manual cron route) | 'backfill'.
    # DOUBLE DUTY: the rollback lever (DELETE … WHERE source='sync' AND
    # snapshot_at > '<bad-deploy>') and the cron liveness detector (zero
    # 'weekly' rows one week post-ship => daily-tick is not firing).
    Column("source",             String,  nullable=False),
    UniqueConstraint("league_id", "team_key", "scoring_format", "period_key",
                     name="uq_roster_snapshot"),
)
Index("ix_lrh_team_period",   league_roster_history_table.c.league_id,
                              league_roster_history_table.c.team_key,
                              league_roster_history_table.c.period_key)
Index("ix_lrh_league_period", league_roster_history_table.c.league_id,
                              league_roster_history_table.c.period_key)
Index("ix_lrh_owner_period",  league_roster_history_table.c.owner_user_id,
                              league_roster_history_table.c.period_key)

# ---------------------------------------------------------------------------
# league_board_history — weekly COMPLETE board snapshots (C5 + C6, YR-3)
# ---------------------------------------------------------------------------
# NOT a fork of elo_history, which stays exactly as it is: the event-driven
# "what moved when" log. elo_history writes only players whose Elo CHANGED
# in a submission, so it structurally cannot rebuild a complete board at
# date D without folding forward from row one; it has no uniqueness
# constraint of any kind, so a weekly append to it would not be idempotent
# (a double run silently doubles every board); and row-per-player weekly is
# ~1.6M rows at 100 leagues vs ~6,000 JSON-per-board here (270x).
# Different grain, different question.
#
# NOT related to wrapped_events (below), which is a FROZEN behavioural
# EVENT stream and stores no valuations.
#
# YR-3 permits in-app, authenticated, league-context display of one
# manager's valuations to another. Every P3 read accessor must take
# league_id AND a caller identity and assert league membership, as
# load_member_rankings does. There is no public-URL read path — that is
# the half of D-P1-12 still standing, and growth.tier_board_share stays
# false.
# ---------------------------------------------------------------------------
league_board_history_table = Table("league_board_history", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("user_id",          String,  nullable=False),
    Column("league_id",        String,  nullable=False),
    Column("scoring_format",   String,  nullable=False),
    Column("period_key",       String,  nullable=False),   # '2026-W33'
    Column("snapshot_date",    String,  nullable=False),   # 'YYYY-MM-DD'
    Column("snapshot_at",      String,  nullable=False),   # ISO UTC
    Column("elos",             Text,    nullable=False),   # JSON {player_id: round(elo,1)}
    Column("player_count",     Integer, nullable=False),
    # member_rankings.updated_at at capture. Distinguishes "re-ranked this
    # week" from "we re-snapshotted an unchanged board" — without it, one
    # observation repeated five times reads as five observations, and
    # "Your calls" (P3) is built on exactly that distinction.
    Column("board_updated_at", String),
    Column("source",           String,  nullable=False),   # 'sync'|'weekly'|'backfill'
    UniqueConstraint("user_id", "league_id", "scoring_format", "period_key",
                     name="uq_board_snapshot"),
)
Index("ix_lbh_league_period", league_board_history_table.c.league_id,
                              league_board_history_table.c.period_key)
Index("ix_lbh_user_period",   league_board_history_table.c.user_id,
                              league_board_history_table.c.period_key)

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
    # ── M1 (fit-challenger measurement rail, LLD §5.1) ───────────────────
    # ISO UTC instant of the last write that went through set_config().
    # NULL on rows never touched since the column landed (additive, no
    # backfill). A raw-SQL bypass write leaves it stale — the per-run
    # config_json snapshot diff is what catches those (PLAN-v2 R-5).
    Column("updated_at",  String),
)

# ---------------------------------------------------------------------------
# model_config_changes — append-only log of every funneled knob write (M1).
# One row per set_config() call, written in the SAME transaction as the
# value update, so a knob's change date is knowable after the fact and every
# measurement window can be censored at the logged timestamp (PLAN-v2 R-5).
#
# key:        the model_config key that changed
# old_value:  prior value (NULL on the first logged write of a key)
# new_value:  the value written
# changed_at: ISO UTC
# source:     who/what wrote it — 'operator' (set_knob.py), 'admin-api'
#             (PUT /api/admin/config default), 'operator-local', tests, …
# ---------------------------------------------------------------------------

model_config_changes_table = Table("model_config_changes", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("key",        String,  nullable=False),
    Column("old_value",  Float),                    # NULL on first logged write
    Column("new_value",  Float,   nullable=False),
    Column("changed_at", String,  nullable=False),  # ISO UTC
    Column("source",     String),                   # 'operator' | 'admin-api' | …
)
Index("ix_model_config_changes_key",
      model_config_changes_table.c.key, model_config_changes_table.c.changed_at)

# ---------------------------------------------------------------------------
# Agent 6 additions — wrapped_events  ***FROZEN (analytics P0 cutover)***
# ---------------------------------------------------------------------------
# Silent event stream that powered the "Fantasy Trade Wrapped" recap.
# event_type was one of:
#   swipe | trade_match | trade_accepted | trade_declined |
#   tier_save | ranking_reorder | league_sync
#
# FROZEN at the `analytics.wrapped_cutover_at` model_config instant
# (docs/plans/analytics-platform/lld.md §6.4): all five writers now land in
# user_events and this table receives ZERO writes. It is retained read-only
# for pre-cutover history — load_league_activity unions it (created_at <
# cutover) with user_events (occurred_at >= cutover). Do not add writers.
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
#
# Tracking plan v2 §S1 (docs/business/analytics/2026-07-17-tracking-plan-v2.md)
# added the nullable envelope columns (event_id … experiments) so client-fired
# events land in the same lineage. Pre-auth events use
# user_id = 'device:<device_id>'; identity_links (below) stitches them to the
# user after sign-in.
user_events_table = Table("user_events", metadata,
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("user_id",      String,  nullable=False, index=True),
    Column("event_type",   String,  nullable=False),
    Column("occurred_at",  String,  nullable=False),    # ISO UTC (server receive time)
    Column("league_id",    String),
    Column("session_id",   String),
    Column("device_type",  String),                     # 'iphone' | 'ipad' | 'macos' | 'web' | 'extension'
    Column("os_version",   String),                     # '17.4' | '18.1' | etc.
    Column("app_version",  String),                     # '1.2.3'
    Column("source",       String),                     # 'mobile' | 'web' | 'api' | 'cron'
    Column("props",        Text),                       # JSON — event-specific extras
    Column("event_id",     String),                     # client UUID — idempotent retries / dedup (unique index below)
    Column("device_id",    String),                     # stable per-install anon id ('dev_' + UUID)
    Column("platform",     String),                     # 'ios' | 'web' | 'extension' | 'server'
    Column("screen",       String),                     # screen/view the event fired from
    Column("client_ts",    String),                     # client wall-clock ISO; occurred_at stays server time
    Column("experiments",  Text),                       # JSON {exp_key: variant} snapshot at event time
    Column("country",      String),                     # ISO-3166 alpha-2, CDN-header-derived at ingest (never raw IP); NULL when no geo header
    Index("ix_user_events_user_occurred", "user_id", "occurred_at"),
    Index("ix_user_events_type_occurred", "event_type", "occurred_at"),
    # FULL unique index — NULLS DISTINCT on both dialects, so unlimited
    # v1/server-fired NULL rows coexist legally (LLD §3.1, invariant I-1).
    # Conflict-ignore inserts must target it WITHOUT index_where.
    Index("ix_user_events_event_id", "event_id", unique=True),
    # Composite read index for device attribution scans (LLD §3.1); replaces
    # the earlier single-column ix_user_events_device_id (dropped in
    # _migrate_db — the composite is a strict superset).
    Index("ix_user_events_device_occurred", "device_id", "occurred_at"),
)

# identity_links — stitches pre-auth device rows to the signed-in identity.
# Written (idempotently) on every successful sign-in that carries a
# device_id. Queries resolve 'device:<device_id>' user_events rows through
# this table. Tracking plan v2 §S1.
identity_links_table = Table("identity_links", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("device_id",       String,  nullable=False),
    Column("sleeper_user_id", String),                  # null for account-only sessions
    Column("account_id",      String),                  # acct_… anchor when known
    Column("linked_at",       String,  nullable=False), # ISO UTC
    # Composite (device_id, linked_at) — exactly the shape FR-21 attribution
    # scans want (nearest linked_at ≤ occurred_at). NEW NAME on purpose:
    # CREATE INDEX IF NOT EXISTS would silently no-op on the old
    # single-column ix_identity_links_device name and the composite would
    # never materialize in prod (LLD §3.2); the old index is dropped in
    # _migrate_db. Code-enforced CHECK (see link_identity): at least one of
    # sleeper_user_id / account_id must be non-null.
    Index("ix_identity_links_device_linked", "device_id", "linked_at"),
    Index("ix_identity_links_user", "sleeper_user_id"),
)

# ── Saved analytics segments (Fullstory-style cohorts) ─────────────────
# A named filter over users; evaluated live per query window by
# analytics_queries.evaluate_segment. The definition is a small closed
# grammar (did / did_not / platform / min_events) — every operand maps to a
# code-controlled SQL fragment, so no user string reaches SQL unparameterized.
analytics_segments_table = Table("analytics_segments", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("name",            String, nullable=False),
    Column("definition_json", Text,   nullable=False),
    Column("created_at",      String, nullable=False),
    UniqueConstraint("name", name="uq_analytics_segment_name"),
)

# ── Experiment engine (analytics platform P3, LLD §3.2) ────────────────
# Layered A/B + multivariate. All append-only except experiments.status.
# The layer salt is minted once per layer and NEVER rotated while any
# experiment in the layer is un-decided (rotating it reshuffles every bucket).
experiment_layers_table = Table("experiment_layers", metadata,
    Column("layer",      String, primary_key=True),   # onboarding|ranking|trades_ui|engine|growth
    Column("salt",       String, nullable=False),      # secrets.token_hex(16), IMMUTABLE
    Column("created_at", String, nullable=False),
)

# One row per (key, version). Edits to a running experiment mint a new version
# (metrics reset); status is the only mutable field.
experiments_table = Table("experiments", metadata,
    Column("key",             String,  nullable=False),
    Column("version",         Integer, nullable=False),
    Column("layer",           String,  nullable=False),
    Column("status",          String,  nullable=False),   # draft|running|paused|stopped|decided
    Column("unit_type",       String,  nullable=False),   # account|device
    Column("hypothesis",      Text),
    Column("bucket_start",    Integer, nullable=False),    # in-layer claim [start,end), 0..10000
    Column("bucket_end",      Integer, nullable=False),
    Column("targeting_json",  Text),      # {"platform":["ios"],"app_version_gte":"1.9.0",…}
    Column("variants_json",   Text),      # [{"name","weight_bp","model_overlay":{},"client_config":{}}]
    Column("primary_metric",  String,  nullable=False),    # program-plan catalog key
    Column("guardrails_json", Text),      # auto-seeded five PFO guardrails + bands
    Column("exposure_surface",String,  nullable=False),    # event_type/screen naming the varied surface
    Column("scope_json",      Text),      # FR-32 stamp scope {"event_types":[…],"screens":[…]}
    Column("mde",             Float),
    Column("alpha",           Float),
    Column("power",           Float),
    Column("override_underpowered", Integer),   # 0|1
    Column("created_at",      String,  nullable=False),
    Column("started_at",      String),
    Column("ended_at",        String),
    Column("decision",        String),   # ship|revert|iterate
    Column("decision_rationale", Text),
    Column("decided_at",      String),
    UniqueConstraint("key", "version", name="uq_experiments_key_version"),
)

experiment_transitions_table = Table("experiment_transitions", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("experiment_key",  String,  nullable=False),
    Column("version",         Integer, nullable=False),
    Column("from_status",     String),
    Column("to_status",       String,  nullable=False),
    Column("actor",           String),
    Column("reason",          Text),
    Column("at",              String,  nullable=False),
)

# Assignment is AUDIT, not truth — the variant is always re-derivable from the
# deterministic hash. PK (unit, key, version) + conflict-ignore makes concurrent
# first evaluations race benignly.
experiment_assignments_table = Table("experiment_assignments", metadata,
    Column("unit_id",         String,  nullable=False),
    Column("experiment_key",  String,  nullable=False),
    Column("version",         Integer, nullable=False),
    Column("variant",         String,  nullable=False),
    Column("assigned_at",     String,  nullable=False),
    Column("context_json",    Text),     # attrs at assignment (first-writer-wins)
    UniqueConstraint("unit_id", "experiment_key", "version",
                     name="uq_assignment_unit_key_ver"),
    Index("ix_assignments_key_ver", "experiment_key", "version"),
)

# Daily rollup per (key, version, variant, metric, UTC-day window). On-request
# at beta scale; the schema is cron-ready for Postgres scale.
experiment_metric_snapshots_table = Table("experiment_metric_snapshots", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("experiment_key",  String,  nullable=False),
    Column("version",         Integer, nullable=False),
    Column("variant",         String,  nullable=False),
    Column("metric_key",      String,  nullable=False),
    Column("window_start",    String,  nullable=False),
    Column("window_end",      String,  nullable=False),
    Column("n",               Integer, nullable=False),   # exposed units in window
    Column("numerator",       Float),   # proportion metrics
    Column("denominator",     Float),
    Column("mean",            Float),   # continuous: winsorized mean
    Column("m2",              Float),   # continuous: Σ(x−x̄)² (Welford)
    Column("computed_at",     String,  nullable=False),
    Index("ix_snapshots_key_ver_metric",
          "experiment_key", "version", "metric_key", "window_end"),
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

# ---------------------------------------------------------------------------
# Notification preferences + send log + queued (deferred) pushes
# ---------------------------------------------------------------------------
# Three tables that together power typed push delivery:
#
# notification_prefs        — per-user opt-in for each bucket + tz + quiet hrs.
#                             Defaults assumed when no row exists (see
#                             get_notification_prefs()), so we don't need to
#                             write a row at signup.
# notification_events_log   — append-only record of every push actually sent
#                             (or coalesced into a bundle), keyed by user_id +
#                             kind. Powers frequency caps (e.g. winback_dormant
#                             1/30d) without scanning user_events.
# notification_queue        — pushes generated during a user's quiet hours that
#                             will be drained + bundled into a single summary
#                             push at the user's local 8am.
#
# Buckets ('trade_matches' | 'weekly_digest' | 'reengagement') map kinds →
# user-facing toggle in get_pref_bucket() in server.py's push dispatcher.
notification_prefs_table = Table("notification_prefs", metadata,
    Column("user_id",            String,  primary_key=True),
    Column("trade_matches",      Integer),  # 0|1, default 1
    Column("weekly_digest",      Integer),  # 0|1, default 1
    Column("reengagement",       Integer),  # 0|1, default 1
    Column("quiet_hours_enabled",Integer),  # 0|1, default 1
    Column("tz",                 String),   # IANA, e.g. 'America/New_York'
    Column("updated_at",         String),
)

notification_events_log_table = Table("notification_events_log", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("kind",       String,  nullable=False),  # 'new_match' | 'winback_dormant' | etc.
    Column("dedup_key",  String),                   # e.g. match_id, week-stamp
    Column("sent_at",    String,  nullable=False),
    Index("ix_notif_events_user_kind_sent", "user_id", "kind", "sent_at"),
)

# Pushes deferred by quiet hours land here; the 8am tick collapses them per
# user into one summary push and clears the rows.
notification_queue_table = Table("notification_queue", metadata,
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("user_id",      String,  nullable=False, index=True),
    Column("kind",         String,  nullable=False),
    Column("title",        String),
    Column("body",         String),
    Column("data_json",    Text),                # original push data payload
    Column("dedup_key",    String),              # original dedup_key from _send_typed_push
    Column("queued_at",    String,  nullable=False),
    Column("deliver_after",String,  nullable=False),  # ISO UTC timestamp when eligible
)

# ---------------------------------------------------------------------------
# sleeper_credentials_table — encrypted Sleeper write tokens ("Send in Sleeper")
# ---------------------------------------------------------------------------
#
# ⚠️ FLAGGED-BETA / ToS-adverse. Backs the `trade.send_in_sleeper` feature
# (default OFF). One row per FTF user_id who has linked their Sleeper account
# via the webview capture (docs/plans/sleeper-write-capture-runbook.md §C1).
#
# token_encrypted: Fernet ciphertext of the user's Sleeper JWT — a FULL-ACCOUNT
#   credential. NEVER stored in plaintext, NEVER logged. Encrypt/decrypt live in
#   backend/sleeper_write.py; the key is the SLEEPER_TOKEN_KEY env var.
# sleeper_user_id / expires_at: read from the (unverified) JWT claims at link
#   time — used to resolve the proposing roster and to prompt reconnect before
#   the 365-day token lapses. This is an interim home; folds into the auth
#   epic's `linked_sources` when that lands (docs/plans/auth-multiplatform-*).
# ---------------------------------------------------------------------------

sleeper_credentials_table = Table("sleeper_credentials", metadata,
    Column("user_id",         String,  primary_key=True),   # FTF user_id (one link per user)
    Column("sleeper_user_id", String),                      # linked Sleeper account (from JWT)
    Column("token_encrypted", Text,    nullable=False),     # Fernet ciphertext — never plaintext
    Column("expires_at",      String),                      # ISO UTC of JWT exp (reconnect hint)
    Column("created_at",      String,  nullable=False),
    Column("updated_at",      String,  nullable=False),
)

# ---------------------------------------------------------------------------
# espn_credentials_table — encrypted ESPN session cookies (league linking #101)
# ---------------------------------------------------------------------------
#
# Backs private-league reads for the `espn.link` feature (default OFF). One
# row per FTF user_id who supplied the `espn_s2` + `SWID` cookies from a
# logged-in espn.com session (Phase 1: manual paste; WebView capture is
# Phase 1b). espn_s2 is a full-session credential: Fernet-encrypted at rest
# using the SAME key as sleeper_credentials (SLEEPER_TOKEN_KEY — one
# credential-encryption key per deployment), never logged. SWID doubles as
# the user's ESPN member id in league payloads, so it is stored plaintext.
# expires_hint_at: cookie lifetime is undocumented (~1 year community
# consensus) — a NULL hint means "unknown"; 401s drive the reconnect UX.
# verified_at (2026-08-12, credential-honesty fix): when this pair last
# PROVED itself against ESPN. It means EXACTLY ONE THING — the SERVER
# observed a successful AUTHENTICATED read from ESPN using this pair
# (server._espn_verify_credential: an authenticated read of a linked private
# league, else a fan-profile probe that returned account-specific data, with
# the RESULT ASSERTED — a bare 200 is not a stamp). It is NOT "the client
# captured cookies", NOT "the user appeared signed in", and NOT "no exception
# was raised". NULL means never proven (legacy rows, or a store path that
# skipped verification): GET /api/espn/link reports such a row as NOT
# connected, so the client re-runs the sign-in.
# DO NOT WIDEN THIS COLUMN: any device-reported or heuristic "looks connected"
# signal added later needs its OWN column. The 2026-08-12 incident (a pair
# stamped verified after a probe that proved nothing, surfacing as a 409 at
# the next trade send) is what this narrowness protects against.
# Folds into the auth epic's `linked_sources` when that lands.
# ---------------------------------------------------------------------------

espn_credentials_table = Table("espn_credentials", metadata,
    Column("user_id",           String, primary_key=True),  # FTF user_id (one link per user)
    Column("swid",              String),                     # braced GUID — ESPN member id
    Column("espn_s2_encrypted", Text,   nullable=False),     # Fernet ciphertext — never plaintext
    Column("expires_hint_at",   String),                     # ISO UTC guess; NULL = unknown
    Column("verified_at",       String),                     # ISO UTC of last successful live auth; NULL = never proven
    Column("created_at",        String, nullable=False),
    Column("updated_at",        String, nullable=False),
)

# ---------------------------------------------------------------------------
# mfl_credentials_table — encrypted MFL session cookies (#177, flag mfl.auth_link)
# ---------------------------------------------------------------------------
#
# Backs authenticated MFL linking. One row per FTF user_id who signed in with
# MFL credentials via POST /api/mfl/auth-link. The user's PASSWORD is used
# transiently for the single MFL login call and is NEVER stored or logged —
# what we keep is the MFL_USER_ID session cookie MFL returns, which is a
# full-session credential: Fernet-encrypted at rest with the SAME key as
# sleeper/espn credentials (SLEEPER_TOKEN_KEY — one credential-encryption key
# per deployment), never logged. mfl_username is the login handle (an
# identifier, not a secret) kept for "connected as" display. Cookie lifetime
# is undocumented; MFL auth errors (401/403) drive the reconnect UX. Folds
# into the auth epic's `linked_sources` when that lands.
# ---------------------------------------------------------------------------

mfl_credentials_table = Table("mfl_credentials", metadata,
    Column("user_id",          String,  primary_key=True),  # FTF user_id (one link per user)
    Column("mfl_username",     String),                      # MFL login handle — identifier only
    Column("cookie_encrypted", Text,    nullable=False),     # Fernet ciphertext — never plaintext
    Column("year",             Integer),                     # season the cookie was minted for
    Column("created_at",       String,  nullable=False),
    Column("updated_at",       String,  nullable=False),
)

# ---------------------------------------------------------------------------
# accounts + linked_identities — identity anchor layer (account-auth plan P2)
# ---------------------------------------------------------------------------
#
# Thin identity layer above the app's working key (`sleeper_user_id`) — see
# docs/plans/account-auth-plan-2026-07-11.md §2d / §3-P2. Engine/ranking/match
# tables stay keyed on sleeper_user_id; an account is the durable anchor a
# provider identity (Sign in with Apple / Google) hangs off, and it *binds*
# to at most one sleeper_user_id (accounts.sleeper_user_id, nullable until
# the first bind). Binding is sticky — see backend/accounts.py bind rules.
#
# linked_identities: one row per (provider, provider_subject). We key on the
# provider's stable `sub` claim — NEVER on email (Apple only returns email on
# first authorization). email_hash is an optional SHA-256 of the provider
# email for support lookups; the raw email is never stored.
# ---------------------------------------------------------------------------

accounts_table = Table("accounts", metadata,
    Column("account_id",      String, primary_key=True),   # opaque hex id
    Column("sleeper_user_id", String),                     # bound working key (nullable)
    Column("created_at",      String, nullable=False),
    # ── Email capture (docs/business/product/2026-07-17-email-capture-spec.md) ──
    # Dark until flag `auth.email_capture` + the capture UI + privacy-policy
    # flip ship together. Deleted with the accounts row (delete_user_data).
    Column("email",                 String),  # plaintext, normalized lower/trim
    Column("email_source",          String),  # 'apple' | 'user'
    Column("email_consent_at",      String),  # ISO — consent stamped at capture
    Column("email_unsubscribed_at", String),  # ISO — never send when set
)

linked_identities_table = Table("linked_identities", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("account_id",       String,  nullable=False),
    Column("provider",         String,  nullable=False),   # 'apple' | 'google'
    Column("provider_subject", String,  nullable=False),   # provider's stable `sub`
    Column("email_hash",       String),                    # SHA-256 hex of email, nullable
    Column("linked_at",        String,  nullable=False),
    UniqueConstraint("provider", "provider_subject", name="uq_linked_identity"),
)

# ---------------------------------------------------------------------------
# Persistent sessions (teardown 06-03 PRD, flag `auth.persistent_sessions`)
#
# Durable identity layer under server.py's in-memory `_sessions` dict. Only
# VERIFIED sessions (Sleeper-JWT proof or Apple/Google anchor) are ever
# written here — username-only unverified sessions deliberately stay
# memory-only so they keep the 4h idle eviction + restart loss that limits
# the squatting window. Tokens are stored as SHA-256 hashes (a DB leak must
# not hand out live bearer tokens). Rows are the source of truth for
# "session survives a deploy": on a memory miss the server rebuilds the
# in-memory session from this row (90d rolling idle expiry, enforced at
# read time + purged by the cleanup loop).
# ---------------------------------------------------------------------------

sessions_table = Table("sessions", metadata,
    Column("token_hash",   String, primary_key=True),   # SHA-256 hex of the bearer token
    Column("user_id",      String, nullable=False),     # sleeper id or acct_* working key
    Column("account_id",   String),                     # accounts.account_id when anchored
    Column("verified_via", String),                     # 'sleeper' | 'apple' | 'google' | 'mfl_login'
    Column("account_only", Integer),                    # 1 = acct_* session (no Sleeper source)
    Column("username",     String),                     # for session rebuild after restart
    Column("display_name", String),
    Column("created_at",   String, nullable=False),     # ISO UTC
    Column("last_seen_at", String, nullable=False),     # ISO UTC — throttled refresh
    Index("ix_sessions_user", "user_id"),
)

# ---------------------------------------------------------------------------
# Shared trade packages (teardown S7 PRD-01 follow-up, flag
# `growth.share_landing`) — landing objects for calculator / unmatched-trade
# shares, which previously had no /s/ page and fell back to the site root.
# A row is a compact public snapshot: two player-id lists chosen by the
# sharer. Retention: kept indefinitely (share links shouldn't rot);
# created_at is recorded so a future sweep can prune. The sharer's user_id
# is stored for rate limiting/abuse tracing but never rendered on the page.
# ---------------------------------------------------------------------------

shared_packages_table = Table("shared_packages", metadata,
    Column("short_id",    String, primary_key=True),    # url token, e.g. 8 chars
    Column("user_id",     String, nullable=False),      # sharer (server-side only)
    Column("give_ids",    Text,   nullable=False),      # JSON list[str] of player ids
    Column("receive_ids", Text,   nullable=False),      # JSON list[str] of player ids
    Column("created_at",  String, nullable=False),      # ISO UTC
    Index("ix_shared_packages_user", "user_id"),
)

# ---------------------------------------------------------------------------
# Monetization platform foundation
# (docs/plans/monetization/00-platform-foundation.md §2.1)
#
# entitlements is the single source of truth for who has paid access. Rows
# are written ONLY by (a) the billing webhook projector, (b) referral /
# group-unlock reward granting, (c) the manual-grant admin routes — never
# from client-supplied receipts. Resolution is read-time (expires_at
# evaluated at query time); the hygiene cron that stamps stale rows
# status='expired' is reporting-only, never a correctness dependency.
# All timestamps ISO-8601 UTC strings, matching every other table here.
# ---------------------------------------------------------------------------

entitlements_table = Table("entitlements", metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("user_id",     String,  nullable=False),  # working key (sleeper id or acct_*)
    Column("account_id",  String),                   # accounts.account_id when known —
                                                     # lets grants survive Sleeper re-links
    Column("entitlement", String,  nullable=False),  # 'pro' | 'ad_free' (glossary)
    Column("source",      String,  nullable=False),  # apple_iap | stripe | founder_iap |
                                                     # season_pass_iap | promo_referral |
                                                     # promo_group_unlock | manual_grant |
                                                     # trial | rankset_purchase
    Column("product_id",  String),                   # store SKU (subs unlabeled, e.g.
                                                     # ftf_pro_annual; season SKUs
                                                     # year-labeled, e.g. ftf_season_pass_2026)
    Column("status",      String,  nullable=False, server_default="active"),
                                                     # active | expired | revoked | refunded
    Column("starts_at",   String,  nullable=False),
    Column("expires_at",  String),                   # NULL = perpetual (founder, manual)
    Column("granted_by",  String),                   # 'operator' for manual grants;
                                                     # webhook event id otherwise
    Column("note",        String),                   # operator note on manual grants
    Column("metadata",    Text),                     # JSON: original_transaction_id,
                                                     # stripe sub id, referral id, …
    Column("created_at",  String,  nullable=False),
    Column("updated_at",  String,  nullable=False),
    Index("ix_entitlements_user",    "user_id"),
    Index("ix_entitlements_account", "account_id"),
)

# Append-only billing ledger — every webhook lands here verbatim before the
# projector touches entitlements ("tracking subscriptions"). event_id gives
# idempotency: replays and provider retries no-op on the unique constraint.
subscription_events_table = Table("subscription_events", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("source",        String,  nullable=False),  # revenuecat | stripe | app_store_notification
    Column("event_type",    String,  nullable=False),  # INITIAL_PURCHASE, RENEWAL, CANCELLATION,
                                                       # BILLING_ISSUE, EXPIRATION, REFUND, …
    Column("user_id",       String),
    Column("account_id",    String),
    Column("product_id",    String),
    Column("event_id",      String,  nullable=False),  # provider event id → idempotency
    Column("payload",       Text,    nullable=False),  # raw JSON, never trimmed
    Column("occurred_at",   String,  nullable=False),
    Column("processed_at",  String),                   # NULL until projector applied it
    Column("process_error", String),
    UniqueConstraint("event_id", name="uq_subscription_event"),
    Index("ix_subscription_events_user", "user_id"),
)

# Give-get referral program (foundation §5). Fraud control is structural:
# rewards only for verified co-members of the referrer's real Sleeper league,
# one reward per unique referred user ever (uq below), activation-gated.
referrals_table = Table("referrals", metadata,
    Column("id",                    Integer, primary_key=True, autoincrement=True),
    Column("referrer_user_id",      String,  nullable=False),
    Column("referred_user_id",      String),                  # filled when invitee identified
    Column("league_id",             String,  nullable=False), # the shared Sleeper league
    Column("invite_token",          String,  nullable=False), # carried by share-card deep link
    Column("status",                String,  nullable=False, server_default="pending"),
                                                              # pending → joined → activated →
                                                              # rewarded | rejected | expired
    Column("qualifying_event",      String),                  # e.g. 'matchups_completed>=25'
    Column("reward_entitlement_id", Integer),                 # entitlements.id of the grant
    Column("created_at",            String,  nullable=False),
    Column("joined_at",             String),
    Column("activated_at",          String),
    Column("rewarded_at",           String),
    UniqueConstraint("invite_token", name="uq_referral_token"),
    UniqueConstraint("referrer_user_id", "referred_user_id",
                     name="uq_referral_pair"),
    Index("ix_referrals_referrer", "referrer_user_id"),
    Index("ix_referrals_referred", "referred_user_id"),
)

# Outbound affiliate click ledger. subid joins partner payout reports back to
# placement/user cohort (no PII in subids). Reconciliation columns are
# populated by scripts/affiliate_reconcile.py from monthly partner CSVs.
affiliate_clicks_table = Table("affiliate_clicks", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("user_id",       String),                   # NULL for DNT / anonymous
    Column("partner",       String,  nullable=False),  # underdog | draftkings | fanduel | …
    Column("placement",     String,  nullable=False),  # web_bestball_card, web_offers_hub, …
    Column("subid",         String,  nullable=False),
    Column("clicked_at",    String,  nullable=False),
    Column("converted_at",  String),                   # reconciliation write-back
    Column("payout_cents",  Integer),                  # reconciliation write-back
    Column("reconciled_at", String),                   # reconciliation write-back
    UniqueConstraint("subid", name="uq_affiliate_subid"),
    Index("ix_affiliate_clicks_user", "user_id"),
)

# ---------------------------------------------------------------------------
# Rankings marketplace foundation
# (docs/business/product/2026-07-17-rankings-marketplace-plan.md)
#
# rank_sets is format-agnostic BY SCHEMA (operator decision #6): set_type
# declares which benchmark/window family scores the set. dynasty + rookie
# are the launch types; redraft/bestball ship behind ranks.set_types_extended.
# A "published set" is immutable per version — publishing again bumps
# version; accuracy scoring locks onto (rank_set_id, version) snapshots.
# ---------------------------------------------------------------------------

rank_sets_table = Table("rank_sets", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("owner_user_id",  String,  nullable=False),  # contributor's working key
    Column("owner_type",     String,  nullable=False, server_default="user"),
                                                        # 'user' | 'publisher'
    Column("set_type",       String,  nullable=False, server_default="dynasty"),
                                                        # dynasty | rookie | redraft | bestball
    Column("scoring_format", String,  nullable=False),  # '1qb_ppr' | 'sf_tep' (matches
                                                        # member_rankings convention)
    Column("title",          String,  nullable=False),
    Column("description",    Text),
    Column("version",        Integer, nullable=False, server_default="1"),
    Column("visibility",     String,  nullable=False, server_default="private"),
                                                        # private | published | delisted
    Column("price_credits",  Integer),                  # NULL = free / not for sale
    Column("published_at",   String),
    Column("created_at",     String,  nullable=False),
    Column("updated_at",     String,  nullable=False),
    Index("ix_rank_sets_owner", "owner_user_id"),
    Index("ix_rank_sets_type",  "set_type"),
)

rank_set_entries_table = Table("rank_set_entries", metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("rank_set_id", Integer, nullable=False),
    Column("version",     Integer, nullable=False),
    Column("player_id",   String,  nullable=False),  # players.player_id (picks use the
                                                     # draft-pick pseudo-player ids)
    Column("rank",        Integer, nullable=False),
    Column("elo",         Float),                    # optional — present when exported
                                                     # from a live Elo board; rank is
                                                     # the canonical ordering
    UniqueConstraint("rank_set_id", "version", "player_id",
                     name="uq_rank_set_entry"),
    Index("ix_rank_set_entries_set", "rank_set_id", "version"),
)

# One row per adoption event. mode mirrors the plan's adoption mechanics;
# entitlement_id links a paid adoption to its rankset_purchase entitlement.
rank_set_adoptions_table = Table("rank_set_adoptions", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("rank_set_id",    Integer, nullable=False),
    Column("version",        Integer, nullable=False),
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String,  nullable=False),  # adoption is per-league (format guard)
    Column("mode",           String,  nullable=False),  # seed | replace | track
    Column("entitlement_id", Integer),                  # NULL for free adoptions
    Column("adopted_at",     String,  nullable=False),
    Index("ix_rank_set_adoptions_set",  "rank_set_id"),
    Index("ix_rank_set_adoptions_user", "user_id"),
)

# Quarterly accuracy scoring output (plan §Accuracy engine). One row per
# (snapshot, benchmark, horizon) — peer_percentile is recomputed per window
# across the scored population; badge tiers derive from rolling windows in
# the scoring job, never stored denormalized here.
accuracy_scores_table = Table("accuracy_scores", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("rank_set_id",     Integer),                  # NULL for passive user-board scores
    Column("user_id",         String,  nullable=False),  # board owner (passive) or set owner
    Column("set_type",        String,  nullable=False),
    Column("scoring_format",  String,  nullable=False),
    Column("snapshot_at",     String,  nullable=False),  # lock timestamp of the scored board
    Column("benchmark",       String,  nullable=False),  # production | market | rookie_tiers
    Column("horizon",         String,  nullable=False),  # '13wk' | '1yr' | '2yr' | 'season'
    Column("raw_score",       Float),                    # benchmark-native score (lower=better
                                                         # for gap metrics; documented per job)
    Column("peer_zscore",     Float),                    # peer-relative within the window
    Column("peer_percentile", Float),                    # 0-100 within scored population
    Column("sample_weight",   Float),                    # relevance-weighted assets scored
    Column("scored_at",       String,  nullable=False),
    UniqueConstraint("user_id", "rank_set_id", "snapshot_at", "benchmark",
                     "horizon", name="uq_accuracy_score"),
    Index("ix_accuracy_scores_user", "user_id"),
)

# ── draft-extensions W2 — FTF-native mock draft (plan §5, lld §3.3) ────────
# A resumable simulation is genuinely stateful: in-memory state dies on a
# Render spin-down, which is a real event on the free plan. `server_default`
# (not Python `default`) so a raw-SQL insert cannot produce NULL — the
# referrals_table precedent above.
#
# One active mock per (user, league) is enforced in APPLICATION CODE inside
# the create transaction, not by a constraint: `UniqueConstraint(user_id,
# league_id, status)` would also block a second *abandoned* row, and the
# partial unique index that fixes that is dialect-divergent across
# SQLite/Postgres.
mock_drafts_table = Table("mock_drafts", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("league_id",  String,  nullable=False),
    Column("season",     Integer, nullable=False),
    Column("status",     String,  nullable=False, server_default="active"),
                                                  # active | complete | abandoned
    Column("settings",   Text,    nullable=False),  # JSON — mock_draft_service.build_settings
    Column("picks",      Text,    nullable=False, server_default="[]"),
                                                  # JSON array, append-only
    Column("rng_seed",   Integer, nullable=False),
    Column("created_at", String),
    Column("updated_at", String),
    Index("ix_mock_drafts_user_league", "user_id", "league_id"),
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
    # ── Consensus seed blend (#145/#148 — data_loader, applied at pool build) ──
    ("ktc_blend_weight",      0.5,    "#145: KeepTradeCut weight in the consensus seed blend (0=DP-only kill switch, 1=KTC ordering only); takes effect on next pool build/boot"),
    ("tep_te_uplift",         1.18,   "#148: TE value multiplier for sf_tep seeds (TE premium); 1=off; calibrated 2026-07-17 so top-8 sf_tep TE seeds clear their 1qb analogs"),
    ("qb_1qb_cap_elo",     1785.0,    "#313: max seed Elo a QB may reach in 1qb_ppr (top of the first_1 band) — 1QB QB values are compressed onto it, order preserved; <=0 disables the compression"),
    ("qb_1qb_cap_knee_elo", 1580.0,   "#313: seed Elo below which 1qb_ppr QB values pass through untouched (the first_1 floor); compression applies only above it; <=0 disables"),
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
    # ── Trios → tier calibration + variety ───────────────────────────────
    ("trio_boundary_rate",     0.4,   "Share of trios that probe a value-band boundary (cross-tier); 0=off"),
    ("trio_boundary_margin",  60.0,   "Elo window on each side of a tier edge to pull boundary straddlers from"),
    ("trio_within_tier_rate",  0.35,  "Share of trios comparing top-vs-bottom of the SAME tier (intra-tier order); remainder after boundary+within = tightest local ordering"),
    ("trio_repeat_avoid",      8.0,   "Avoid reusing a player seen in the last N served trios (anti-repeat); relaxes gracefully (oldest-seen first) when the pool is too small"),
    # ── Forced deck regeneration (docs/reviews/2026-08-18-bug-sweep) ─────
    ("force_supersedes_running", 1.0, "/api/trades/generate: 1 = `force: true` supersedes an already-RUNNING job for the same key (the superseded worker finishes quietly — no further snapshots, no impression rows, no trades_generated event); 0 restores the pre-2026-08-18 behaviour where a forced request silently returned the in-flight job and the regeneration never happened"),
    # ── Board-override pins (docs/reviews/2026-08-18-valuation-age-audit.md) ──
    # Read by ranking_service. pin_tier_bounded=0 with the other three at their
    # shipped values restores the pre-2026-08-18 freeze exactly (goldens:
    # backend/tests/test_pin_tier_bounded.py, test_override_pin_unpin.py).
    ("pin_tier_bounded",        1.0,  "Tier-bounded voting: a pinned (tier/reorder-placed) player is no longer frozen — his Elo evolves from votes but is CLAMPED to the band of the tier he was placed in (tier_config.json). Re-ranking inside a tier works; nothing moves across tiers. A pin below the lowest band (the #161 demotion Elo / anchor 'no value') has no band and stays frozen. 0 restores the total freeze"),
    ("pin_exclude_comparisons", 1.0,  "F1: count only the comparisons that actually MOVED a player's Elo in comparison_counts() — a pinned player's votes no longer raise the direction-blind shrinkage weight (which made down-voting a pin RAISE its trade value). 0 disables"),
    ("pin_unpin_on_newer_swipe", 0.0, "F2 — SUPERSEDED by pin_tier_bounded and therefore OFF: a ranking swipe recorded strictly AFTER a tier/reorder pin released that player outright. Full release is no longer the model (a pin is a durable band constraint, not something that expires); kept as the revert path to Phase 0 — set pin_tier_bounded=0 and this to 1"),
    ("pin_legacy_at_epoch",     0.0,  "F2 legacy policy — SUPERSEDED (inert while pin_unpin_on_newer_swipe is 0): 0 = a pin with no stored write time is PERMANENT; 1 = treat it as written at the epoch, so ANY recorded swipe — including historical ones — releases it. Only meaningful on the Phase 0 revert path; see docs/config-reference.md"),
    # ── Trade ELO gap filter ─────────────────────────────────────────────
    ("trade_elo_gap_max",    250.0,   "Max user-ELO gap between give/receive sides before rejecting a trade (0=disabled)"),
    # ── Agent A8 — trade-math adjustments (flag-gated) ───────────────────
    ("qb_tax_rate",              0.075, "QB tax: % penalty to side receiving a premium QB without giving one back"),
    ("star_tax_per_tier_gap",    0.10,  "Star tax: % penalty per tier gap beyond 1 between top assets"),
    ("star_tax_elite_multiplier", 1.5,  "Star tax: multiplier on penalty when the higher-tier star is Tier 1 (elite)"),
    ("roster_spot_penalty",      0.05,  "Roster clogger: % penalty per extra roster spot used"),
    ("roster_clogger_penalty",   0.10,  "Roster clogger: ADDITIONAL % penalty per player beyond 2 for 3+ one-way trades"),
    ("roster_clogger_threshold", 3.0,   "Roster clogger: minimum one-side player count that triggers the clogger tag"),
    # ── Trade engine v2 — Tier 1 (flag trade_engine.v2) ──────────────────
    ("elo_value_k",             0.0050, "v2: steepness of the Elo→value exponential curve"),
    ("elo_value_ref",         1500.0,   "v2: Elo that maps to the reference value"),
    ("elo_value_base",        1000.0,   "v2: value at the reference Elo"),
    ("package_adj_gamma",        1.5,   "v2: KTC-style package adjustment exponent (lesser assets discounted)"),
    ("min_side_surplus",       150.0,   "v2: min per-side perceived value gain to surface a trade"),
    ("mutual_gain_cap",       1500.0,   "v2: normalization ceiling for the harmonic-mean mutual gain"),
    ("waiver_slot_cost",       425.0,   "v2: value cost per extra player received (waiver-drop proxy)"),
    ("shrink_pseudocount",       4.0,   "v2: n0 in w=n/(n+n0) confidence shrinkage toward seed"),
    ("range_base",               0.35,  "v2: value half-width fraction at 0 comparisons (range-overlap fairness)"),
    # ── Trade engine Tier 2 ──────────────────────────────────────────────
    ("bench_credit_rate",        0.15,  "2.1: fraction of raw value retained by bench depth in marginal valuation"),
    ("waiver_baseline_value",  250.0,   "2.1: replacement value when a position is too thin to have one"),
    ("min_side_surplus_marginal", 60.0, "2.1: per-side surplus gate when marginal valuation is on"),
    ("outlook_alpha_championship", 1.0, "2.2: now-value weight for championship outlook"),
    ("outlook_alpha_contender",  0.75,  "2.2: now-value weight for contender outlook"),
    ("outlook_alpha_not_sure",   0.5,   "2.2: now-value weight for not-sure/unknown outlook"),
    ("outlook_alpha_rebuilder",  0.25,  "2.2: now-value weight for rebuilder outlook"),
    ("outlook_alpha_jets",       0.1,   "2.2: now-value weight for jets (extreme rebuild) outlook"),
    ("fuzzy_match_tau",          0.8,   "2.3b: Jaccard threshold per side for fuzzy mirror matching"),
    ("likes_you_min_user_delta", -500.0, "2.3a/D-055: min net consensus value (receive - give, summed player values) the VIEWER must clear for a leaguemate's liked trade to be injected into their deck; very negative disables the floor"),
    # ── FB-47 finder targeting (flag trade.finder_targeting) ─────────────
    ("fit_consensus_weight",     0.5,   "FB-47: partner-fit blend weight on consensus-card composites"),
    ("fit_divergence_weight",    0.15,  "FB-47: partner-fit blend weight on divergence-card composites (tiebreak strength)"),
    # 0.30 → 0.15 per interview 2026-07-17 ("light multiplier"); existing
    # DB rows still at the old default are updated by the seeding pass.
    ("need_fit_weight",          0.15,  "FB-96: composite blend weight for automatic positional-need fit (0 disables the reordering)"),
    # ── FB-147 engine hook (flag trade.block_boost) ──────────────────────
    ("block_boost_weight",       0.15,  "FB-147: SOFT acquire-side trade-block boost — composite *= 1 + w when a card acquires a counterparty-flagged on-the-block player, applied after all gates (0 disables, composite byte-identical)"),
    ("diversity_window_days",    7.0,   "A6: lookback window for league impression saturation counts"),
    ("diversity_user_cap",       3.0,   "A6: other-member count at which a target player is 'saturated'"),
    ("diversity_penalty",        0.6,   "A6: ordering-key multiplier applied to saturated targets"),
    ("deck_max_per_target",      3.0,   "A6: intra-deck cap on cards sharing the same top receive asset"),
    # ── Trade engine Tier 3 (flags trade_engine.v3, trade.three_team) ────
    ("v3_pool_size",            12.0,   "v3: per-side candidate pool size for exact enumeration"),
    ("sweetener_band",           0.15,  "v3: fairness shortfall band eligible for a sweetener rescue"),
    ("sweetener_gap_threshold",  1539.0, "2026-08-21 gap auto-sweetener: close absolute consensus gaps above this (value units; 1539 = one late 1st) by adding the smallest sufficient asset from the richer side's roster; <=0 disables"),
    ("sweetener_max_cards",      2.0,   "v3: max sweetened cards per opponent pair"),
    ("cycle_edge_min_gain",    100.0,   "v3: min per-transfer marginal gain for a 3-team cycle edge"),
    ("cycle_min_net",          200.0,   "v3: min net gain per team for a 3-team cycle"),
    ("cycle_max_results",        3.0,   "v3: max 3-team cycles returned per league"),
    ("v3_diversity_max_overlap", 0.4,   "v3: max asset Jaccard between two cards from one opponent pair"),
    ("consensus_score_scale",    0.3,   "v2: composite multiplier keeping consensus fallback cards below divergence finds"),
    # ── #170/#171 owned draft picks in the candidate pool (flag trade.picks_in_pool) ──
    ("picks_pool_cap",           6.0,   "#170: max owned picks per team injected into the suggestion candidate pool (top-N by pool_value)"),
    # ── Backlog #1 opponent outlook inference (flag trade.outlook_infer) ──
    ("infer_w_vet_share",        1.0,   "#1: weight on vet (age≥vet_age) value share in outlook inference"),
    ("infer_w_youth_share",      1.0,   "#1: weight on youth (age≤youth_age) value share in outlook inference"),
    ("infer_w_pick_share",       2.0,   "#1: weight on pick-capital share (centred on equal split) in outlook inference"),
    ("infer_contender_cut",      0.08,  "#1: inferred-outlook score at/above which a team is a contender"),
    ("infer_rebuilder_cut",     -0.08,  "#1: inferred-outlook score at/below which a team is a rebuilder"),
    # ── Backlog #2 asset preference lists (flag trade.preference_lists) ──
    ("target_acquire_bonus",     0.20,  "#2: +N composite per received TARGET player, capped by pos_multiplier_cap"),
    # ── Backlog #10 crown-asset premium (flag trade.crown_asset) ──
    ("crown_rate",               0.12,  "#10: max consolidation premium on a smaller-count side's top asset (at 100% share)"),
    ("crown_share_floor",        0.50,  "#10: top-asset share below which the crown premium is zero"),
    # ── #141 junk-filler gate (trade engine v2 / v3 / consensus paths) ───
    ("filler_min_frac",          0.25,  "#141: min added-piece value as a fraction of its side's headliner, on max(user board, opp board); 0 disables"),
    # ── Interview 2026-07-17 — trade-logic recalibration ─────────────────
    ("asset_floor_abs",        450.0,   "interview: absolute value floor for non-headliner pieces (max-of-boards); 0 disables"),
    ("crown_elite_value",     6000.0,   "interview: crown-asset value earning the full crown_rate; premium scales linearly below it; <=0 disables scaling"),
    # ── #214 stud-tax retune — 'market' mode shapes (default stud_tax_mode) ──
    ("skew_phaseout",            0.5,   "#214: naive-skew at which the market-mode crown credit phases to zero (scale = max(0, 1 - |skew|/this)); <=0 disables the phase-out"),
    ("crown_rate_market",        0.08,  "#214: market-mode crown credit per elite asset (value >= crown_elite_value), BOTH sides, count-independent"),
    ("package_floor_market",     0.70,  "#214: market-mode depth-discount contribution floor (piece contributes at least this fraction of face value)"),
    ("package_adj_gamma_market", 0.5,   "#214: market-mode depth-discount exponent, benchmarked against the package's OWN best asset"),
    ("package_discount_cap",     0.35,  "#214: cap on a side's total market-mode depth discount as a fraction of its naive sum"),
    ("package_bench_trade_wide", 1.0,   "2026-08-21 benchmark fix: >0 = depth-discount a multi-asset side that lacks the trade's best asset against the TRADE's best asset (v_max); <=0 = pre-fix own-max benchmark (arm A's pin)"),
    ("package_floor_cross",      0.40,  "2026-08-21 benchmark fix: contribution floor on the cross-benchmarked (stud-buying) side; inert while package_bench_trade_wide <= 0"),
    ("fairness_floor_divergence", 0.55, "interview: consensus fairness gate for divergence cards = min(fairness_threshold, this) — extreme-case veto only"),
    # ── #189 — relaxed fallback for empty targeted sweeps ────────────────
    ("relaxed_fairness_threshold", 0.55, "#189: stage-1 fairness bar for the relaxed fallback pass on empty targeted jobs (never tightens below the caller's threshold)"),
    ("relaxed_surplus_floor",      0.0,  "#189: stage-2 value for min_side_surplus(_marginal) in the relaxed pass; 0 still requires non-negative surplus both sides"),
    # ── #172/#189 follow-up — asset-centric trade ideas (trade.asset_ideas) ──
    ("asset_ideas_lateral_band", 0.10,  "asset ideas: ± consensus-value band around the pinned asset classifying a counterpart as Lateral; above=Upgrade, below=Downgrade piece"),
    ("asset_ideas_group_cap",    6.0,   "asset ideas: max ideas returned per group (upgrade/lateral/downgrade), ordered by |difference|"),
    ("bench_credit_qb",          0.10,  "interview: bench credit for QB depth in 1QB formats"),
    ("bench_credit_rb",          0.30,  "interview: bench credit for RB depth (near-startable insurance)"),
    ("bench_credit_wr",          0.30,  "interview: bench credit for WR depth (near-startable insurance)"),
    ("bench_credit_te",          0.10,  "interview: bench credit for TE depth in non-TEP formats"),
    ("bench_credit_qb_sf",       0.35,  "interview: bench credit for QB depth in superflex formats"),
    ("bench_credit_te_tep",      0.25,  "interview: bench credit for TE depth in TE-premium formats"),
    # ── Interview phase 2 — lanes / fit premium / aggression A/B ─────────
    ("lane_shift_frac",          0.10,  "phase2: min value-weighted now-lean shift for a card to label as a window move"),
    ("fit_premium_max_loss",   300.0,   "phase2: max raw-board value a flagged need-fill 1-for-1 may pay"),
    ("aggression_weight",        0.20,  "phase2: composite reweight strength for the light/fair/generous offer buckets"),
    # ── Feedback #175 directional outlook weighting (flag trade.outlook_direction) ──
    ("outlook_dir_penalty",      3.0,   "#175: rebuild-side composite penalty weight on a positive (win-now-acquiring) now-lean shift"),
    ("outlook_dir_boost",        1.0,   "#175: rebuild-side composite boost weight on a negative (future-capital-acquiring) now-lean shift"),
    ("outlook_dir_contend_weight", 0.5, "#175: contend-side mild mirror weight (symmetric term only, no age-gap rule)"),
    ("outlook_dir_age_tolerance", 1.0,  "#175: years an older primary return may exceed the primary give before the age-gap rule fires"),
    ("outlook_dir_age_gap_mult", 0.15,  "#175: near-exclusion composite multiplier for unrescued older-primary returns (rebuild-side only)"),
    ("outlook_dir_rescue_frac",  0.5,   "#175: min fraction of the primary give's consensus value a pick/younger return component needs to rescue the age-gap rule"),
    # ── Fit-congruence signal weighting (D-060, no feature flag) ─────────
    ("fit_k_explained_mult",     0.4,   "fit-congruence: K multiplier when the user's window already explains the swipe (like on a window-congruent card, pass on an anti-window one); 1.0 = kill switch, restores pre-D-060 flat-K behavior"),
    ("fit_k_defying_mult",       1.0,   "fit-congruence: K multiplier when the swipe defies the window (pass on a window-congruent card, like on an anti-window one); 1.0 = full baseline K, deliberately not boosted above it"),
    # ── Analytics platform P1 (docs/plans/analytics-platform/lld.md §3.4) ─
    ("analytics_events_per_hr", 600.0,  "P1 ingest: per-device client-event budget per hour; over-budget batches are accepted-and-dropped (never 429)"),
    ("obs_success_sample_n",     10.0,  "API observability (obs.api_events): record 1-in-N SUCCESSFUL api_call/api_request events (errors always recorded); 1 = record every call; cached 60s in api_observability"),
    # ── Deck-eval 2026-07-17 — consensus consolidation sanity gate ───────
    ("consolidation_raw_loss_frac", 0.15, "deck-eval: max RAW consensus loss on a user-give-side consolidation as a fraction of the raw give total (consensus path); 0 disables"),
    # ── #169 Outlook odds pipeline (backend/outlook/) — numeric knobs ─────
    # (The STRING knob outlook_strength_source lives in env FTF_OUTLOOK_STRENGTH_SOURCE
    #  because model_config.value is Float-typed; see docs/config-reference.md.)
    ("outlook_mean_points",          110.0, "#169: assumed league-average weekly fantasy score (RosterValueStrength affine anchor); FLAGGED heuristic"),
    ("outlook_points_per_value_sd",   12.0, "#169: weekly points added per 1 SD of starting-lineup roster value (RosterValueStrength slope); FLAGGED heuristic"),
    ("outlook_sigma_default",         25.0, "#169: default weekly-score standard deviation when not derived from data; FLAGGED heuristic"),
    ("outlook_trailing_min_weeks",     3.0, "#169: K — min completed weeks before TrailingScoresStrength/auto switch off roster-value"),
    ("outlook_sim_count",          10000.0, "#169: Monte-Carlo season simulations per outlook request"),
    ("outlook_seed",                   0.0, "#169: config seed XORed with stable_hash(league_id) for the deterministic RNG"),
    # ── #169 bye-week mu multiplier (backend/outlook/bye_multiplier.py) ───
    # EVALUATED variant, NOT consulted by pipeline.py — see the ship/no-ship
    # verdict in docs/feedback/items/169-outlook-league-summary/
    # bye-week-multiplier-2026-08-09.md before ever reading these knobs live.
    ("outlook_bye_multiplier_enabled", 0.0, "#169: gate for the (evaluated, unshipped) per-week bye multiplier; 0=off (default) — pipeline.py does not read this yet"),
    ("outlook_bye_multiplier_scale",   1.0, "#169: linear scale from starting-lineup value-fraction-on-bye to mu multiplier haircut; FLAGGED heuristic, unshipped"),
    # ── G6 trade presentment rules (flag trade.presentment_rules) ─────────
    # docs/feedback/items/304-positional-need-filter/lld-delta.md §2. Each
    # knob is that rule's deploy-free kill switch via PUT /api/admin/config.
    ("max_overpay_frac",         0.25,  "G6 R1 #340: kill when raw consensus gap >= max_overpay_min_value AND gap/max(side) >= this, BOTH sides, independent of fairness_threshold; <=0 disables R1"),
    ("max_overpay_min_value",   500.0,  "G6 R1 #340: absolute gap floor (D-055 materiality) below which R1 never fires"),
    ("pos_net_cap",               1.0,  "G6 R2 #341: max |count(recv at P) - count(give at P)| per position over QB/RB/WR/TE (picks uncounted); 0 disables"),
    ("pick_gap_frac",             0.8,  "G6 R3 #339: two-sided band — kill when a heavier-side pick sits in [frac*gap, gap/frac]; 0 disables. UNMEASURED default (no pick cards in the D-055 corpus) — the R-12 pick-league replay is the tuning task"),
    ("pick_gap_min_value",      300.0,  "G6 R3 #339: consensus gap floor below which R3 never fires"),
    ("need_gate_min_value",     500.0,  "G6 R5 #304: min consensus value of the primary received player before the need gate applies (untargeted decks only); <=0 disables the whole gate"),
    ("need_gate_upgrade_margin",  0.0,  "G6 R5 #304: primary must beat the post-give incumbent by this fraction to count as a starter upgrade; 0 = any strict upgrade passes"),

    # Dismiss ("pass") cooldown — docs/plans/pass-cooldown/plan.md, D-067.
    # The UI's "dismiss" is the API's decision='pass'. Deploy-free revert to
    # the pre-fix behavior: set this to 7.0.
    ("pass_cooldown_days",       14.0,  "Dismiss cooldown: a passed trade is excluded from generation for this many days (was hard-coded 7 alongside likes). Set 7.0 to restore pre-fix behavior; likes keep their own 7-day window"),
    ("pass_cooldown_start_epoch", 1787005800.0, "Legacy-dismiss amnesty (D-067): unix epoch; dismisses recorded BEFORE this instant are exempt from the cooldown because they predate decline-reason capture (D-066, live 2026-08-17T22:22:56Z) and carry no reason. Default 2026-08-17T22:30:00Z. Raise it to the moment the reason-carrying MOBILE build reaches testers; 0 disables the amnesty"),
    # ── D-079 per-round draft-pick year decay (pick_values.year_decay) ───
    # Multiplicative value RETAINED per season the pick is in the future.
    # 1.0 = flat (a 2029 1st prices like a 2026 1st). Setting all four to
    # 0.85 restores the pre-D-079 uniform discount with no deploy.
    ("pick_year_decay_r1", 1.00, "D-079: per-year value multiplier for a 1st-round pick; 1.0 = firsts hold value YoY (operator direction 2026-08-19). Set 0.85 to restore the pre-D-079 uniform discount"),
    ("pick_year_decay_r2", 0.85, "D-079: per-year value multiplier for a 2nd-round pick (KTC 1QB crowd rate 0.860)"),
    ("pick_year_decay_r3", 0.85, "D-079: per-year value multiplier for a 3rd-round pick (KTC 1QB crowd rate 0.860)"),
    ("pick_year_decay_r4", 0.85, "D-079: per-year value multiplier for a 4th-round pick and deeper (KTC 1QB crowd rate 0.856)"),
    # ── Fit-challenger arm knobs (docs/plans/fit-challenger/LLD.md §4) ────
    # All 17 seeded in PR-M so set_config/PUT never KeyErrors on them (HLD
    # F-1); backend/trade_gen_fit.py consumes them from PR-F1/F2/F3 on.
    # Generation knobs are dark: arm A never imports the fit module.
    ("fit_score_scale",           400.0, "fit arm: tanh surplus scale — surplus 400 → score ≈ 88.1"),
    ("fit_score_even",             50.0, "fit arm: score of a zero-surplus (even) trade — the tanh curve midpoint"),
    ("fit_w_board",                0.40, "fit arm: lens weight L1 (own-board surplus) in the per-side combine"),
    ("fit_w_div",                  0.30, "fit arm: lens weight L2 (board-vs-consensus divergence) in the combine"),
    ("fit_w_cons",                 0.30, "fit arm: lens weight L3 (consensus surplus) in the combine"),
    ("fit_pool_consensus",          8.0, "fit arm pool: top-N roster assets by consensus value"),
    ("fit_pool_div_seed",           8.0, "fit arm pool: top-N assets by viewer-board-over-seed divergence"),
    ("fit_pool_div_opp",            8.0, "fit arm pool: top-N assets by opponent-board divergence"),
    ("fit_pool_cap",               15.0, "fit arm pool: hard cap on unique asset ids per roster (picks compete under it)"),
    ("fit_max_packages_per_pair", 20000.0, "fit arm: enumeration ceiling per viewer-opponent pair — the ms relief valve"),
    ("fit_expand_from",            25.0, "fit arm: top-N 1-for-1 survivors used as seeds for multi-asset expansion"),
    ("fit_min_them",                0.0, "fit arm post-score filter: min them-score to surface; 0 = off (PRD default)"),
    ("fit_min_aggregate",           0.0, "fit arm post-score filter: min you+them aggregate to surface; 0 = off"),
    ("fit_r5_mode",                 1.0, "fit arm K7: 1 = R5 need-gate failure kills (live-as-written); 0 = score + tag r5_fail"),
    ("fit_junk_floor",              0.0, "fit arm: 1 = kill sides padded below asset_floor_abs; 0 = lens 3 tanks junk instead"),
    # ── Bake-off serving knobs (seeded 2026-08-20, W1 re-light) ─────────────
    # These pre-date the fit build but were NEVER seeded, so `set_config`
    # KeyError'd on them and every "deploy-free flip" of the serving posture
    # was actually a code-default edit + deploy (the 2026-08-18/19 dance).
    # Values here MATCH trade_service._DEFAULT_CFG exactly — seeding is
    # behavior-neutral; it only makes the knobs remotely settable (HLD F-1).
    ("bakeoff_serve_interleaved",   0.0, "bake-off serving: 1 = interleaved deck served; 0 = dark (arm B only)"),
    ("bakeoff_deck_limit",         30.0, "bake-off: max cards in the served interleaved deck (0 = uncapped)"),
    ("bakeoff_group_size",         10.0, "bake-off composition: cards per group; 0 kills the composition layer (plain per-arm draft)"),
    ("bakeoff_group_value_slots",   5.0, "bake-off composition: value-lane slots per group (outlook = remainder)"),
    ("bakeoff_fill_policy",         0.0, "bake-off: 1 = backfill residual lane slots cross-lane (flagged); 0 = leave short"),
    ("bakeoff_lane_reallocate",     1.0, "bake-off: 1 = lanes may spill into slots the other lane cannot fill (own bucket only)"),
    ("bakeoff_include_baseline",    0.0, "bake-off roster bit: 1 = arm A (baseline) generates; 0 = out (default)"),
    ("bakeoff_include_challenger",  1.0, "bake-off roster bit: 1 = arm D (challenger) generates; 0 = out"),
    ("bakeoff_include_gen_v2",      1.0, "bake-off roster bit: 1 = arm C (gen_v2) generates; 0 = out"),
    # OPERATOR RULING 2026-08-21 (batch-wide): ghosts are ruled out
    # entirely, so the SEED default is 0 — a fresh DB must not start
    # ghosting. <=0 disables ghosting inside the flag.
    ("ghost_holdout_one_in",        0.0, "suggestion telemetry: withhold ~1-in-N organic deck cards as ghosts; <=0 disables ghosting. DEFAULT 0 per the operator ruling 2026-08-21 (ghosts ruled out entirely)"),
    ("bakeoff_include_fit",         0.0, "bake-off roster bit: 1 = arm fit generates + logs; 0 = not rostered (default)"),
    ("bakeoff_serve_fit",           0.0, "bake-off serve bit: 1 = fit cards join the served draft; 0 = dark (generate + log only)"),
    # ── Counterparty-breaker knobs (docs/plans/counterparty-breaker/LLD.md §4) ─
    # All 25 seeded here so `set_config` / PUT /api/admin/config never KeyError
    # on them and the LLD §6 rollback ladder is real rather than theater.
    # Consumed by backend/trade_breaker.py, which runs AFTER generation and
    # ranking; no generator or ranker imports it. `waiver_slot_cost` above is
    # reused by the breaker and is NOT part of the 25.
    ("breaker_ms_budget",                   250.0, "breaker: per-deck eval budget ms; 0 disables (minimal markers)"),
    ("breaker_budget_checkpoint_frac",        0.6, "breaker: budget fraction at which pass 2 is dropped whole; 1.0 disables"),
    ("breaker_degraded_share_max",           0.05, "breaker: graduation bar — max share of degraded (rung 1-3) rows; 1.0 off"),
    ("breaker_min_severity",                 0.60, "breaker: global narration bar over the per-class floors; 1.1 silences all"),
    ("breaker_max_repeat_frac",              0.34, "breaker: per-(partner,code) narration share cap before suppression; 1.0 off"),
    ("breaker_shadow_run",                    1.0, "breaker: 1 = viewer-seat shadow eval; 0 = breaker_shadow null everywhere"),
    ("breaker_outlook_haircut_legacy",       0.70, "breaker: fit_outlook severity multiplier when outlook_src='legacy'; 1.0 none"),
    ("breaker_outlook_narrate_margin",       0.06, "breaker: inferred-window margin over the cut required to NARRATE fit_outlook"),
    ("breaker_board_div_min",                25.0, "breaker: Elo divergence from seed for a board row to count as divergent"),
    ("breaker_board_min_divergent",          10.0, "breaker: divergent rows needed for board_auth='board'; below ⇒ board_suspect"),
    ("breaker_value_scale",                 400.0, "breaker: their-seat negative margin mapping value_giving severity to 1.0"),
    ("breaker_crunch_scale",                850.0, "breaker: slot-cost total mapping roster_crunch severity to 1.0"),
    ("breaker_floor_fit_outlook",            0.35, "breaker: top-selection floor for fit_outlook; 1.1 removes it from selection"),
    ("breaker_floor_fit_new_weakness",       0.30, "breaker: top-selection floor for fit_new_weakness; 1.1 removes it"),
    ("breaker_floor_fit_duplicate",          0.30, "breaker: top-selection floor for fit_duplicate; 1.1 removes it"),
    ("breaker_floor_value_giving",           0.30, "breaker: value_giving floor on the BOARD basis; 1.1 removes it"),
    ("breaker_floor_value_giving_consensus", 0.75, "breaker: value_giving floor on the CONSENSUS basis (higher — D-7); 1.1 off"),
    ("breaker_floor_other_player_keep",      0.50, "breaker: top-selection floor for other_player_keep; 1.1 removes it"),
    ("breaker_floor_roster_crunch",          0.40, "breaker: top-selection floor for roster_crunch; 1.1 removes it"),
    ("breaker_narrate_fit_outlook",           0.0, "breaker: 1 = fit_outlook may narrate; 0 (default) = stamp only"),
    ("breaker_narrate_fit_new_weakness",      0.0, "breaker: 1 = fit_new_weakness may narrate; 0 (default) = stamp only"),
    ("breaker_narrate_fit_duplicate",         0.0, "breaker: 1 = fit_duplicate may narrate; 0 (default) = stamp only"),
    ("breaker_narrate_value_giving",          0.0, "breaker: 1 = value_giving may narrate (CONSENSUS basis only — D-7); 0 = off"),
    ("breaker_narrate_other_player_keep",     0.0, "breaker: symmetry only — the D-6 whitelist blocks this class even at 1"),
    ("breaker_narrate_roster_crunch",         0.0, "breaker: 1 = roster_crunch may narrate; 0 (default) = stamp only"),
    # ── Negative-results memory (docs/plans/negative-results-memory/LLD.md §3.4) ─
    # All 6 seeded here so `set_config` / PUT /api/admin/config never KeyError on
    # them — a knob with no row cannot be flipped remotely, which is what makes
    # the LLD §6 kill ladder (negmem_strength = 0 for M1) real rather than
    # theater. Values MATCH trade_service._DEFAULT_CFG exactly; seeding is
    # behavior-neutral. M2's strength knob is the existing
    # `gen2_accept_prior_strength`, not one of these 6.
    ("negmem_strength",       1.0,  "negmem M1 strength; 0 = byte-identical M1 disable (M1-only — M2 is governed by gen2_accept_prior_strength)"),
    ("negmem_floor",          0.6,  "negmem clamp floor for the effective multiplier; also the evidence-curve asymptote"),
    ("negmem_min_evidence",   3.0,  "negmem shrinkage threshold: cells with decayed evidence below this are identity"),
    ("negmem_halflife_days", 45.0,  "negmem evidence exponential-decay half-life (days); read horizon = 4x this"),
    ("negmem_sat_k",          3.0,  "negmem evidence-curve saturation pseudo-count (mult = 1 - (1-floor)*n_eff/(n_eff+k))"),
    ("negmem_like_net",       1.0,  "negmem: evidence mass one admitted viewed like nets against every (partner, *) cell"),
]


# ---------------------------------------------------------------------------
# Initialisation — called once on server startup
# ---------------------------------------------------------------------------

# ── #321 ESPN identity-binding release (2026-08-16) — R10 residue eviction ──
# Cutoff for evicting pre-release `espn_credentials.verified_at` stamps.
# WHY every pre-release stamp: no stamp minted before identity binding
# shipped proves IDENTITY — the weak oracle vacuously accepts any account,
# the public-league import gap stamped with no verify at all, and the strong
# oracle passes any league member's pair. Under-eviction re-opens #321;
# over-eviction costs one harmless re-sign-in.
# CUTOFF MECHANICS: `_migrate_db` runs on every boot, so the UPDATE must
# stay date-bounded — an unbounded "null all stamps" would sign users out on
# every deploy. This literal is FINALIZED AT SHIP: the observed
# deploy-completion time of the identity-binding release, else push-to-main
# time plus a generous margin — erring LATER is safe (a stamp minted by the
# new identity-bound code inside the margin is re-nulled once at the next
# boot; that user re-signs-in one extra time, nothing worse), erring EARLIER
# is not (a dishonest stamp survives as trusted). Reference timestamps
# (verified from git, PRD §8): 2fa1ff2 (introduces the column)
# 2026-08-12T04:25:58Z; 7dfcd16 (real-oracle fix) 2026-08-13T02:27:03Z.
# Comparison is lexicographic over ISO-UTC strings — valid because
# verified_at is always written via datetime.now(timezone.utc).isoformat()
# (uniform +00:00 offset; a microsecond-bearing stamp still sorts after a
# seconds-precision literal because '.' > '+').
_ESPN_VERIFIED_AT_RELEASE_CUTOFF = "2026-08-17T06:00:00+00:00"


def _evict_prerelease_espn_verified_stamps() -> int:
    """#321 R10 — null every `espn_credentials.verified_at` stamp minted
    before the identity-binding release (see the cutoff constant above).

    Idempotent by construction, not by accident of data: after the first
    run every matched row is NULL, and `NULL < '<cutoff>'` is NULL under
    SQL three-valued logic — not matched — so re-runs are structural
    no-ops. Rows are NOT deleted: the encrypted pair stays (forensics),
    exactly how born-NULL legacy rows already behave, and the GET honesty
    gate reads the nulled row as not connected → one re-sign-in through
    the now identity-bound flow. Returns the evicted row count."""
    with engine.begin() as conn:
        res = conn.execute(
            espn_credentials_table.update()
            .where(espn_credentials_table.c.verified_at
                   < _ESPN_VERIFIED_AT_RELEASE_CUTOFF)
            .values(verified_at=None)
        )
        return res.rowcount or 0


def _migrate_db() -> None:
    """
    Add columns that may be missing from older DB schemas.
    Each ALTER TABLE is wrapped in try/except so it's idempotent — safe to
    call on a fresh DB or one that already has all columns.

    Also seeds model_config with default values (INSERT OR IGNORE so that
    any manually-tuned rows survive re-deploys).
    """
    migration_cols = [
        # Email capture (2026-07-17 spec) — dark behind auth.email_capture
        ("accounts",           "email",                 "VARCHAR"),
        ("accounts",           "email_source",          "VARCHAR"),
        ("accounts",           "email_consent_at",      "VARCHAR"),
        ("accounts",           "email_unsubscribed_at", "VARCHAR"),
        ("trade_matches",      "user_a_decision",      "VARCHAR"),
        ("trade_matches",      "user_b_decision",      "VARCHAR"),
        ("trade_matches",      "user_a_decided_at",    "VARCHAR"),
        ("trade_matches",      "user_b_decided_at",    "VARCHAR"),
        # Per-user inbox dismissal (archive, no ELO) — see dismiss_match.
        ("trade_matches",      "user_a_dismissed",     "INTEGER"),
        ("trade_matches",      "user_b_dismissed",     "INTEGER"),
        ("league_preferences", "acquire_positions",    "TEXT"),
        ("league_preferences", "trade_away_positions", "TEXT"),
        # Feedback lifecycle status (operator-managed; NULL reads as 'new')
        ("app_feedback",       "status",                "VARCHAR"),
        ("app_feedback",       "status_updated_at",     "VARCHAR"),
        ("users",              "ranking_method",        "VARCHAR"),
        ("users",              "tiers_saved",           "TEXT"),
        ("users",              "tier_overrides",        "TEXT"),
        # Dual-format support (1QB PPR + SF TEP)
        ("swipe_decisions",    "scoring_format",        "VARCHAR"),
        ("member_rankings",    "scoring_format",        "VARCHAR"),
        ("leagues",            "default_scoring",       "VARCHAR"),
        # FB #41 — Sleeper's total_rosters, persisted at session_init so the
        # League tile can show the league's true team count.
        ("leagues",            "total_rosters",         "INTEGER"),
        ("users",              "invited_by",            "VARCHAR"),
        ("users",              "unlocked_formats",      "TEXT"),
        # #111 — per-user pick-value scale for the anchor wizard
        ("users",              "anchor_scale",          "TEXT"),
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
        # Ranking streak — see _recompute_streak_on_rank_event()
        ("users",              "current_streak",        "INTEGER"),
        ("users",              "longest_streak",        "INTEGER"),
        ("users",              "last_rank_local_date",  "VARCHAR"),
        ("users",              "last_rank_tz",          "VARCHAR"),
        # PR3 — dedup_key threading on quiet-hours queue
        ("notification_queue", "dedup_key",             "VARCHAR"),
        # Account-auth plan (docs/plans/account-auth-plan-2026-07-11.md) —
        # verified-session persistence. Written by P1 (Sleeper-JWT proof,
        # verified_via='sleeper') and P2 (identity anchors,
        # verified_via='apple'|'google'). Guards are idempotent, so it is
        # safe for both phases to declare the same columns.
        ("users",              "verified_at",           "VARCHAR"),
        ("users",              "verified_via",          "VARCHAR"),
        # Public-profile opt-in (teardown 06-04, flag profiles.user_toggle)
        ("users",              "profile_public",        "INTEGER"),
        # #214/#215 — per-user stud-tax mode ('market'|'heavy'|'off')
        ("users",              "stud_tax_mode",         "VARCHAR"),
        # M6b — per-user pick-pricing mode ('tier_ladder'|'market_slots')
        ("users",              "pick_pricing_mode",     "VARCHAR"),
        # ESPN league linking Phase 1 (flag `espn.link`; plan
        # docs/plans/espn-league-linking-plan-2026-07-11.md) — see
        # leagues_table column comments.
        ("leagues",            "platform",              "VARCHAR"),
        ("leagues",            "espn_season",           "INTEGER"),
        ("leagues",            "espn_auth",             "VARCHAR"),
        ("leagues",            "espn_my_team_id",       "INTEGER"),
        # Generic multi-platform linking (MFL / Fleaflicker; plan
        # docs/plans/multi-platform-linking-plan-2026-07-17.md).
        ("leagues",            "platform_season",       "INTEGER"),
        ("leagues",            "platform_host",         "VARCHAR"),
        ("leagues",            "platform_auth",         "VARCHAR"),
        ("leagues",            "platform_my_team",      "VARCHAR"),
        ("leagues",            "platform_future_picks", "TEXT"),
        # #158 — owned draft picks: engine-scale value + platform provenance.
        ("draft_picks",        "pool_value",            "FLOAT"),
        ("draft_picks",        "platform",              "TEXT"),
        # draft-extensions W3 (ADR-010) — user-asserted pick ownership.
        # VARCHAR, not TEXT, to match the Column(..., String) declarations;
        # `platform` above is the existing String/TEXT wart, not a precedent.
        # NO BACKFILL: every existing row keeps source IS NULL, which the
        # default read predicate treats as platform.
        ("draft_picks",        "source",                "VARCHAR"),
        ("draft_picks",        "assigned_by",           "VARCHAR"),
        ("draft_picks",        "assigned_at",           "VARCHAR"),
        ("leagues",            "pick_assignment_settings", "TEXT"),
        # D-090 — the CURRENT season's resolved draft order, so an owned pick
        # can be labelled by its real slot ("2026 1.08") instead of its round.
        # NULL = unresolved, which is every pre-existing row and every league
        # whose platform does not publish an order; the label path falls back
        # to today's generic string, so there is no backfill.
        ("leagues",            "draft_slot_order",      "TEXT"),
        # #207 — rookie class year from Sleeper's metadata.rookie_year, and
        # the per-league rookie-draft verdict cache (backend/draft_status.py).
        ("players",            "rookie_year",           "VARCHAR"),
        ("leagues",            "draft_status",          "VARCHAR"),
        ("leagues",            "draft_status_confidence", "VARCHAR"),
        ("leagues",            "draft_status_checked_at", "VARCHAR"),
        # Tracking plan v2 §S1 envelope columns (all nullable — v1 rows and
        # v1 record_event() call sites are untouched).
        ("user_events",        "event_id",              "VARCHAR"),
        ("user_events",        "device_id",             "VARCHAR"),
        ("user_events",        "platform",              "VARCHAR"),
        ("user_events",        "screen",                "VARCHAR"),
        ("user_events",        "client_ts",             "VARCHAR"),
        ("user_events",        "experiments",           "TEXT"),
        ("user_events",        "country",               "VARCHAR"),
        # F3 (deck.fatigue) — per-item fatigue key on the impression spine.
        ("deck_impressions",   "centerpiece_id",        "VARCHAR"),
        # ESPN credential-honesty fix (2026-08-12) — last successful live
        # auth proof; NULL = never proven → GET /api/espn/link reads false.
        ("espn_credentials",   "verified_at",           "VARCHAR"),
        # notif-inbox-growth (2026-08-13) — server-side "Clear all" (GD-4).
        # NULL = live; existing rows are all live, which is the correct
        # backfill and needs no separate pass.
        ("notifications",      "dismissed_at",          "VARCHAR"),
        # #318 — awaiting-dismiss retraction marker. NULL = live like;
        # existing rows are all live, which is the correct backfill and
        # needs no separate pass (same shape as dismissed_at above).
        ("trade_decisions",    "retracted_at",          "VARCHAR"),
        # suggestion.telemetry — counterfactual columns on the F1 spine
        # (see deck_impressions_table comments). NULL on all pre-telemetry
        # rows; no backfill by design.
        ("deck_impressions",   "is_ghost",              "INTEGER"),
        ("deck_impressions",   "policy_version",        "VARCHAR"),
        ("deck_impressions",   "candidate_set_id",      "VARCHAR"),
        ("deck_impressions",   "candidate_set_size",    "INTEGER"),
        ("deck_impressions",   "assets_json",           "TEXT"),
        # trade.bakeoff — per-card model attribution on the F1 spine (see
        # deck_impressions_table comments). NULL on all pre-bake-off rows;
        # no backfill by design (no arm produced them).
        ("deck_impressions",   "model_arm",             "VARCHAR"),
        ("deck_impressions",   "arm_rank",              "INTEGER"),
        ("deck_impressions",   "fairness_threshold",    "FLOAT"),
        # trade.bakeoff deck composition — group attribution + the effective
        # #172 intent lens. NULL on all pre-composition rows; no backfill.
        ("deck_impressions",   "group_key",             "VARCHAR"),
        ("deck_impressions",   "group_rank",            "INTEGER"),
        ("deck_impressions",   "lane_slot",             "VARCHAR"),
        ("deck_impressions",   "trade_intent",          "VARCHAR"),
        ("bakeoff_runs",       "groups_json",           "TEXT"),
        # M1 (fit-challenger measurement rail) — stamp of the last funneled
        # write; NULL until a key's first set_config() after this landed.
        ("model_config",       "updated_at",            "VARCHAR"),
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

    # #258 — entity-decode MFL names stored before #210's import-time cleaning
    _backfill_mfl_name_entities()

    # P0-1 (audit 2026-08-09) — users who completed a Quick Set board before
    # the point-of-use ranking_method writes shipped are stuck on the trio
    # branch with unlocked:false. Same slot, same idempotent-every-boot
    # contract as the two backfills above. See docs/runbook.md.
    backfill_ranking_method_from_tiers()

    # P1-7 (audit A-16) — 'anchor' gains an unlock rule, so the pre-existing
    # anchor cohort would fan out retroactively on their first poll. Same
    # slot, same idempotent-every-boot contract. Imported lazily to keep the
    # unlock bar defined in exactly one place (ranking_service).
    try:
        from .ranking_service import RankingService as _RS
        backfill_anchor_unlocked_formats(_RS.ANCHOR_UNLOCK_MIN)
    except Exception as e:
        print(f"[backfill] anchor unlock backfill skipped: {e}")

    # ── #321 R10 — evict pre-identity-binding ESPN verified_at stamps ─────
    # Date-bounded + NULL-fails-`<` idempotent (see the function's
    # docstring); named its own try/except so a permanently-failing UPDATE
    # is at least VISIBLE in boot logs instead of silently swallowed.
    try:
        n = _evict_prerelease_espn_verified_stamps()
        if n:
            print(f"[migrate] espn verified_at eviction: {n} pre-release "
                  f"stamp(s) nulled (cutoff {_ESPN_VERIFIED_AT_RELEASE_CUTOFF})")
    except Exception as e:
        print(f"[migrate] espn verified_at eviction FAILED: {e}")

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

    # ── app_feedback migrations ────────────────────────────────────────────
    # The table itself is created by metadata.create_all(); this block is
    # for any future additive ALTERs. Indexes are declared on the Table
    # definition so create_all() handles them on fresh DBs.
    _app_feedback_migrations: list[tuple[str, str, str]] = [
        # (table, column, type) — currently none; placeholder for future work
    ]
    for table, col, col_type in _app_feedback_migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        except Exception:
            pass

    # ── user_events / identity_links analytics indexes ────────────────────
    # Tracking plan v2 §S1/S2 + analytics-platform LLD §3.1/§3.2. All
    # idempotent (IF NOT EXISTS / IF EXISTS), each in its own transaction.
    # The FULL unique index on event_id relies on NULLS-DISTINCT semantics
    # (both dialects): unlimited v1 server-fired NULL rows coexist legally.
    # The old single-column ix_user_events_device_id / ix_identity_links_device
    # are dropped — their composite replacements are strict supersets.
    _user_events_env_indexes = [
        ("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_events_event_id "
         "ON user_events (event_id)"),
        ("CREATE INDEX IF NOT EXISTS ix_user_events_device_occurred "
         "ON user_events (device_id, occurred_at)"),
        "DROP INDEX IF EXISTS ix_user_events_device_id",
        ("CREATE INDEX IF NOT EXISTS ix_identity_links_device_linked "
         "ON identity_links (device_id, linked_at)"),
        ("CREATE INDEX IF NOT EXISTS ix_identity_links_user "
         "ON identity_links (sleeper_user_id)"),
        "DROP INDEX IF EXISTS ix_identity_links_device",
    ]
    for ddl in _user_events_env_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception:
            pass

    # ── Analytics P0 — wrapped_events cutover timestamp (LLD §6.4, FR-4) ──
    # Set ONCE (INSERT-or-ignore) at the first boot of the deploy that flips
    # the five wrapped_collector writers to user_events. Stored as UNIX epoch
    # seconds because model_config.value is Float; get_wrapped_cutover_iso()
    # converts for ISO-TEXT comparisons. Wrapped rows are created_at <
    # cutover; user_events narrative rows are occurred_at >= cutover — the
    # union reader in load_league_activity depends on zero overlap.
    try:
        with engine.begin() as conn:
            _cut_params = {
                "k": "analytics.wrapped_cutover_at",
                "v": datetime.fromisoformat(_now()).timestamp(),
                "d": ("Epoch-seconds boundary of the wrapped_events -> "
                      "user_events writer cutover (analytics platform P0); "
                      "wrapped_events is frozen at this instant"),
            }
            if DATABASE_URL.startswith("sqlite"):
                conn.execute(text(
                    "INSERT OR IGNORE INTO model_config "
                    "(key, value, description) VALUES (:k, :v, :d)"
                ), _cut_params)
            else:
                conn.execute(text(
                    "INSERT INTO model_config (key, value, description) "
                    "VALUES (:k, :v, :d) ON CONFLICT (key) DO NOTHING"
                ), _cut_params)
    except Exception as e:
        print(f"[migrate] wrapped cutover seed failed: {e}")

    # Ensure indexes exist on DBs that pre-date this table's index declarations.
    _app_feedback_indexes = [
        ("idx_app_feedback_created_at", "app_feedback", "created_at"),
        ("idx_app_feedback_user_id",    "app_feedback", "user_id"),
    ]
    for idx_name, tbl, cols in _app_feedback_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"
                ))
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
        # ── draft-extensions W3 M-A (ADR-010) ─────────────────────────────
        # `draft_picks` already exists in production, so metadata.create_all
        # will NOT add an index to it — this needs the explicit idempotent
        # form. EVERY read of this table filters `league_id` and there is no
        # index on it today; the containment predicate adds `source`. A
        # 192-slot grid per league turns each un-indexed scan into a real
        # cost at seven read sites, so this is part of M-A, not a later
        # optimization.
        ("ix_draft_picks_league_source",  "draft_picks",   "league_id, source"),
    ]
    for idx_name, tbl, cols in _trade_match_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"
                ))
        except Exception:
            pass

    # ── Hot-cold-start indexes (review #B1) ────────────────────────────────
    # These tables were declared with no composite indexes and full-scan on
    # every session_init / swipe / trends tab. Add idempotently — same
    # `CREATE INDEX IF NOT EXISTS` pattern as above. Column lists are
    # aligned to the actual hot-path readers:
    #   - swipe_decisions.(user_id, scoring_format) → load_swipe_decisions
    #     full-scans for one user's format-tagged rows on every session_init
    #     (table has no league_id column; format is the second filter).
    #   - trade_decisions.(user_id, league_id, decision) → check_for_match
    #     filters on `user_id = ? AND league_id = ? AND decision = 'like'`
    #     per swipe.
    #   - member_rankings.(league_id, scoring_format, user_id) →
    #     load_member_rankings filters by `(league_id, scoring_format)`;
    #     adding user_id covers the per-user upsert delete.
    #   - elo_history.(user_id, scoring_format, snapshot_at) →
    #     /api/trends/risers-fallers scans per user+format ordered by ts.
    _hot_path_indexes = [
        ("ix_swipe_dec_user_format", "swipe_decisions",
         "user_id, scoring_format"),
        ("ix_trade_dec_user_league_decision", "trade_decisions",
         "user_id, league_id, decision"),
        ("ix_member_rankings_league_fmt_user", "member_rankings",
         "league_id, scoring_format, user_id"),
        ("ix_elo_history_user_fmt_at", "elo_history",
         "user_id, scoring_format, snapshot_at"),
        ("ix_players_position", "players",
         "position"),
        # ADR-011 (roster-history P0) — player_value_history's only index
        # today is uq_value_snapshot, which leads with player_id. The
        # league-wide recap query (WHERE scoring_format = ? AND
        # snapshot_date IN (...)) has no leading-column match and would
        # full-scan a table projected at ~0.5M rows/yr. Free now.
        ("ix_pvh_format_date", "player_value_history",
         "scoring_format, snapshot_date"),
    ]
    for idx_name, tbl, cols in _hot_path_indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"
                ))
        except Exception:
            pass

    # ── trade_matches.status: 'active' → 'pending' (review P0) ─────────────
    # Earlier code wrote status='active' on insert; every cron reader filters
    # on status='pending'. Idempotent — only flips rows currently 'active'.
    # Safe to run repeatedly: once flipped, the WHERE clause matches nothing.
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE trade_matches SET status = 'pending' "
                "WHERE status = 'active'"
            ))
    except Exception:
        pass

    # ── #117 consensus-seed recalibration: rescale player_value_history ────
    # 2026-07-12: the DP→Elo consensus seed map changed from linear
    # (elo = 1200 + dp/10000 × 600, ceiling 1800) to value-affine
    # (data_loader.seed_elo_for_value: DP maps linearly onto the trade-value
    # scale, DP 10000 → the 4-firsts rung ≈ Elo 1927). Rows written before
    # the recalibration store OLD-scale consensus_elo/consensus_value; left
    # alone, the FB-61 30d trend baseline and the profile tier timeline
    # would compute garbage cross-scale deltas. The old map is invertible,
    # so rescale in place: recover the DP value from the old linear map,
    # re-apply the new map. Runs ONCE, guarded by a model_config marker row
    # (re-running after the marker exists is a no-op; the whole rescale +
    # marker write is a single transaction). See docs/runbook.md.
    try:
        with engine.begin() as conn:
            # Atomic claim: whoever INSERTS the marker row does the rescale,
            # inside the same transaction (a crash rolls back both; a
            # concurrent booter conflicts on the key → rowcount 0 → skips).
            _marker_params = {
                "k": "value_history_seed_scale", "v": 2.0,
                "d": ("Marker: player_value_history rows rescaled to the "
                      "#117 value-affine consensus seed map"),
            }
            if DATABASE_URL.startswith("sqlite"):
                claim = conn.execute(text(
                    "INSERT OR IGNORE INTO model_config "
                    "(key, value, description) VALUES (:k, :v, :d)"
                ), _marker_params)
            else:
                claim = conn.execute(text(
                    "INSERT INTO model_config (key, value, description) "
                    "VALUES (:k, :v, :d) ON CONFLICT (key) DO NOTHING"
                ), _marker_params)
            if claim.rowcount == 1:
                # Old-scale rows are bounded by the old formula's range
                # [1200, 1800]; the BETWEEN guard is belt-and-braces only —
                # the marker claim is the real protection.
                rows = conn.execute(text(
                    "SELECT id, consensus_elo FROM player_value_history "
                    "WHERE consensus_elo BETWEEN 1200 AND 1800.5"
                )).fetchall()
                v_floor = 1000.0 * math.exp(0.005 * (1200.0 - 1500.0))
                v_ceil  = 4.0 * 1000.0 * math.exp(0.005 * (1650.0 - 1500.0))
                for r in rows:
                    dp_frac = max(0.0, min(
                        1.0, (float(r.consensus_elo) - 1200.0) / 600.0))
                    v = v_floor + dp_frac * (v_ceil - v_floor)
                    e = 1500.0 + math.log(v / 1000.0) / 0.005
                    conn.execute(text(
                        "UPDATE player_value_history "
                        "SET consensus_elo = :e, consensus_value = :v "
                        "WHERE id = :id"
                    ), {"e": round(e, 1), "v": round(v, 1), "id": r.id})
    except Exception as e:
        print(f"[migrate] value-history seed rescale failed: {e}")

    # Seed model_config defaults in a single clean transaction.
    with engine.begin() as conn:
        # Interview 2026-07-17: need_fit_weight default dropped 0.30 → 0.15.
        # INSERT OR IGNORE can't retune an already-seeded row, so migrate
        # rows still sitting at the OLD default; operator-tuned values
        # (anything ≠ 0.30) are left alone. Idempotent.
        conn.execute(text(
            "UPDATE model_config SET value = 0.15 "
            "WHERE key = 'need_fit_weight' AND value = 0.30"
        ))
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


def _backfill_mfl_name_entities() -> None:
    """#258 — entity-decode MFL display names stored before #210.

    `mfl_service._clean_text` (#210, 2026-08-01) decodes HTML entities
    ('&amp;', '&#201;', double-escaped forms) on every MFL ingest path —
    parse_bundle (franchise + league names, player names via _flip_name) and
    fetch_my_leagues (auth league list). But leagues linked BEFORE #210
    stored the raw entity-bearing strings, and MFL leagues have no automatic
    re-import, so every surface that reads the stored rows (trade deck
    counterparty names, matches, power rankings, pick labels) kept serving
    them. This is the "already-stored rows" fix: one idempotent pass over
    the three places an MFL name persists —

      1. league_members.username / display_name (the authoritative member
         store; session_init and trade generation names flow from here),
      2. leagues.name for platform='mfl',
      3. the denormalized draft_picks.owner_username / original_username
         snapshots (platform='mfl'), which _sync_mfl_owned_picks copies
         from league_members and only rewrites on a link/refresh event.

    Scoped strictly to MFL rows — Sleeper names are user-typed strings that
    Sleeper itself renders verbatim, so decoding them could change intended
    display. Uses the same _clean_text the import paths use (deferred import;
    mfl_service has no import back into this module). A clean row set writes
    nothing, so running on every startup is free. Chosen over read/serialize-
    time decoding because the dirty copies live in three tables consumed by
    many serializers — fixing the stored data once covers them all.
    """
    try:
        from backend.mfl_service import _clean_text
    except Exception as e:                          # pragma: no cover
        print(f"[backfill] mfl name entities skipped (import): {e}")
        return

    def _cleaned(value):
        """Decoded replacement, or None when no rewrite is needed."""
        if not value:
            return None
        out = _clean_text(value)
        return out if out and out != value else None

    try:
        with engine.begin() as conn:
            lg_rows = conn.execute(
                select(leagues_table.c.sleeper_league_id, leagues_table.c.name)
                .where(leagues_table.c.platform == "mfl")
            ).fetchall()
            mfl_ids = [r.sleeper_league_id for r in lg_rows]
            if not mfl_ids:
                return

            # 2. leagues.name
            for r in lg_rows:
                new_name = _cleaned(r.name)
                if new_name is not None:
                    conn.execute(
                        update(leagues_table)
                        .where(leagues_table.c.sleeper_league_id == r.sleeper_league_id)
                        .values(name=new_name)
                    )

            # 1. league_members for those leagues
            mem_rows = conn.execute(
                select(
                    league_members_table.c.league_id,
                    league_members_table.c.user_id,
                    league_members_table.c.username,
                    league_members_table.c.display_name,
                )
                .where(league_members_table.c.league_id.in_(mfl_ids))
            ).fetchall()
            for m in mem_rows:
                vals = {}
                new_u = _cleaned(m.username)
                new_d = _cleaned(m.display_name)
                if new_u is not None:
                    vals["username"] = new_u
                if new_d is not None:
                    vals["display_name"] = new_d
                if vals:
                    conn.execute(
                        update(league_members_table)
                        .where(
                            (league_members_table.c.league_id == m.league_id)
                            & (league_members_table.c.user_id == m.user_id)
                        )
                        .values(**vals)
                    )

            # 3. denormalized draft_picks username snapshots
            pick_rows = conn.execute(
                select(
                    draft_picks_table.c.pick_id,
                    draft_picks_table.c.owner_username,
                    draft_picks_table.c.original_username,
                )
                .where(draft_picks_table.c.platform == "mfl")
            ).fetchall()
            for p in pick_rows:
                vals = {}
                new_o = _cleaned(p.owner_username)
                new_g = _cleaned(p.original_username)
                if new_o is not None:
                    vals["owner_username"] = new_o
                if new_g is not None:
                    vals["original_username"] = new_g
                if vals:
                    conn.execute(
                        update(draft_picks_table)
                        .where(draft_picks_table.c.pick_id == p.pick_id)
                        .values(**vals)
                    )
    except Exception as e:
        print(f"[backfill] mfl name entities failed: {e}")


def backfill_ranking_method_from_tiers() -> int:
    """P0-1 (audit 2026-08-09) — one-time repair for users who completed a
    Quick Set / Tiers board BEFORE the point-of-use writes shipped, and are
    therefore stuck on the trio branch of get_rankings_progress with
    unlocked:false forever.

    COHORT (deliberately narrow):
        ranking_method IS NULL (or '')  AND  tiers_saved names all four of
        QB/RB/WR/TE for AT LEAST ONE scoring format
      → ranking_method = 'quickset'
      → unlocked_formats gains every qualifying format (see below)

    STRICTLY IMPROVING. For every row it touches the tiers branch returns
    True, which is >= whatever the trio branch was returning. A user with a
    PARTIAL tier board plus a full trio board is a real shape; tagging them
    would move them from the trio rule to the tiers rule and could RE-LOCK
    them, so they are excluded. They lose nothing: their next full-board save
    writes the method at the point of use anyway.

    THE unlocked_formats PRE-SEED IS NOT COSMETIC — it is the fan-out
    suppression required by hld.md S-03. See lld-p0-1.md §2.2.3.

    Idempotent by predicate (after the first run the cohort is empty), safe on
    every boot, and never raises: a failure prints and returns what it wrote.
    Returns the number of rows written.
    """
    _POS = ("QB", "RB", "WR", "TE")
    col  = users_table.c.ranking_method
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(users_table.c.sleeper_user_id,
                       users_table.c.tiers_saved,
                       users_table.c.unlocked_formats)
                .where(or_(col.is_(None), col == ""))
            ).fetchall()
    except Exception as e:
        print(f"[backfill] ranking_method cohort read failed: {e}")
        return 0

    # (uid, merged unlocked_formats JSON) for every qualifying row.
    plan: list[tuple[str, str]] = []
    for row in rows:
        saved    = _parse_per_format_json(row.tiers_saved, is_list=True)
        complete = [f for f in SCORING_FORMATS
                    if all(p in (saved.get(f) or []) for p in _POS)]
        if not complete:
            continue
        try:
            existing = json.loads(row.unlocked_formats) if row.unlocked_formats else []
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, TypeError):
            existing = []
        merged = list(existing) + [f for f in complete if f not in existing]
        plan.append((row.sleeper_user_id, json.dumps(merged)))

    written = 0
    for i in range(0, len(plan), 500):
        chunk = plan[i:i + 500]
        try:
            with engine.begin() as conn:
                for uid, uf in chunk:
                    conn.execute(
                        update(users_table)
                        .where(users_table.c.sleeper_user_id == uid)
                        .values(ranking_method="quickset", unlocked_formats=uf)
                    )
            written += len(chunk)
        except Exception as e:
            print(f"[backfill] ranking_method chunk at {i} failed: {e}")

    if plan:
        # scope-p0-1.md §2 makes the affected ids a BUILD REQUIREMENT: the
        # scoped SQL undo is only expressible if the cohort was logged.
        print(f"[backfill] ranking_method: tagged {written}/{len(plan)} user(s) "
              f"'quickset' — cohort: {[uid for uid, _ in plan]}")
    return written


def backfill_anchor_unlocked_formats(min_overrides: int) -> int:
    """P1-7 (audit A-16) — the fan-out suppression for the anchor cohort.

    THIS EXISTS FOR ONE REASON, and it is the same reason
    backfill_ranking_method_from_tiers pre-seeds unlocked_formats.

    P1-7 gives `ranking_method = 'anchor'` its own unlock rule, so a user who
    anchored 40+ players months ago flips locked -> unlocked on their FIRST
    /api/rankings/progress poll after the deploy. That transition takes the
    `was_first` branch, which emits ranking_complete_first_time AND pushes
    "@user just unlocked Trade Finder" to every joined leaguemate. Without
    this pre-seed the deploy produces a retroactive burst of pushes for work
    nobody did today — the exact failure P0-1 raised and answered the same
    way (hld.md S-03). Pre-seeding unlocked_formats short-circuits
    mark_format_unlocked, so `was_first` is False and neither fires.

    COHORT: ranking_method == 'anchor' AND, for at least one scoring format,
    >= `min_overrides` stored tier_overrides entries in that format.

    THE COUNT IS A DELIBERATE SUPERSET of the runtime predicate.
    RankingService.board_override_count() restricts to pool-RESIDENT pids;
    this cannot, because the player pool is not a database concept. Stored
    count >= pool-resident count, so this may include a user sitting one or
    two stale pids short of the bar. The direction is generous (it grants an
    unlock a hair early; it can never lock anyone), and being generous is the
    right side to err on for a suppression pass — a missed row costs a real
    user a spurious push to their whole league.

    NOT DONE FOR 'manual'. That arm was `unlocked = True` unconditionally, so
    P1-7 only ever TIGHTENS it: no manual user can newly unlock, so no manual
    user can newly fan out. (Anyone already unlocked keeps it through the
    monotonic floor in get_rankings_progress.)

    Idempotent by predicate, safe on every boot, and never raises: a failure
    prints and returns what it wrote. Returns the number of rows written.
    """
    col = users_table.c.ranking_method
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(users_table.c.sleeper_user_id,
                       users_table.c.tier_overrides,
                       users_table.c.unlocked_formats)
                .where(col == "anchor")
            ).fetchall()
    except Exception as e:
        print(f"[backfill] anchor unlock cohort read failed: {e}")
        return 0

    plan: list[tuple[str, str]] = []
    for row in rows:
        overrides = _parse_per_format_json(row.tier_overrides, is_list=False)
        qualifying = [f for f in SCORING_FORMATS
                      if len(overrides.get(f) or {}) >= min_overrides]
        if not qualifying:
            continue
        try:
            existing = json.loads(row.unlocked_formats) if row.unlocked_formats else []
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, TypeError):
            existing = []
        new = [f for f in qualifying if f not in existing]
        if not new:
            continue                      # already suppressed on an earlier boot
        plan.append((row.sleeper_user_id, json.dumps(list(existing) + new)))

    written = 0
    for i in range(0, len(plan), 500):
        chunk = plan[i:i + 500]
        try:
            with engine.begin() as conn:
                for uid, uf in chunk:
                    conn.execute(
                        update(users_table)
                        .where(users_table.c.sleeper_user_id == uid)
                        .values(unlocked_formats=uf)
                    )
            written += len(chunk)
        except Exception as e:
            print(f"[backfill] anchor unlock chunk at {i} failed: {e}")

    if plan:
        # Same rule scope-p0-1.md §2 set for its own backfill: a scoped SQL
        # undo is only expressible if the cohort was logged.
        print(f"[backfill] anchor unlock: pre-seeded {written}/{len(plan)} user(s) "
              f"— cohort: {[uid for uid, _ in plan]}")
    return written


EXPERIMENT_LAYERS = ("onboarding", "ranking", "trades_ui", "engine", "growth")


def _layer_salt(layer: str) -> str:
    """Per-layer bucketing salt. **Prod:** HMAC(EXPERIMENT_SALT_KEY, layer) —
    cryptographically strong AND stable across restarts/DR (a random per-init
    salt would reshuffle every bucket on a fresh DB). **Dev/test/seed:** the env
    is unset, so a fixed deterministic derivation — no cryptographic secrecy is
    needed off-prod, and it keeps the UI-test seed DB byte-reproducible. Set
    EXPERIMENT_SALT_KEY in Render + secrets.local.env before launching real
    experiments (rotating it reshuffles every bucket — treat as launch-blocking
    once an experiment runs)."""
    base = os.environ.get("EXPERIMENT_SALT_KEY")
    if base:
        return hmac.new(base.encode(), layer.encode(), hashlib.sha256).hexdigest()[:32]
    return hashlib.sha256(f"ftf-dev-layer-salt:{layer}".encode()).hexdigest()[:32]


def _seed_experiment_layers() -> None:
    """Seed the reserved layers with their derived salts (INSERT OR IGNORE —
    never rotate a stored salt). Idempotent + deterministic given the env."""
    try:
        with engine.begin() as conn:
            existing = {r[0] for r in conn.execute(
                select(experiment_layers_table.c.layer)).fetchall()}
            now = _now()
            for layer in EXPERIMENT_LAYERS:
                if layer not in existing:
                    conn.execute(insert(experiment_layers_table).values(
                        layer=layer, salt=_layer_salt(layer), created_at=now))
    except Exception as e:   # never break boot on a seeding hiccup
        print(f"[experiment_layers] seed skipped: {e}")


def reseed_experiment_layers() -> dict:
    """Launch-enablement one-shot. `_seed_experiment_layers` runs at boot with
    INSERT-OR-IGNORE, so if the platform first booted (seeding the layers)
    BEFORE `EXPERIMENT_SALT_KEY` was set in the environment, the layers hold
    the dev-fallback salt and setting the key later can't fix them. This
    deletes + re-seeds the reserved layers so their salts derive from the
    CURRENT env key — but ONLY while no experiment has ever assigned a unit
    (a stored salt is immutable once an experiment runs; changing it would
    reshuffle every bucket). Refuses (no-op) once assignments exist.
    Idempotent; returns a non-secret status (never the salt itself)."""
    key_present = bool(os.environ.get("EXPERIMENT_SALT_KEY"))
    with engine.begin() as conn:
        has_assignment = conn.execute(
            select(experiment_assignments_table).limit(1)).first() is not None
        if has_assignment:
            return {"reseeded": False, "reason": "assignments_exist",
                    "key_present": key_present}
        conn.execute(experiment_layers_table.delete())
    _seed_experiment_layers()
    return {"reseeded": True, "layers": list(EXPERIMENT_LAYERS),
            "key_present": key_present}


def init_db() -> None:
    """Create all tables if they don't exist, then apply incremental migrations."""
    metadata.create_all(engine)
    _migrate_db()
    _seed_experiment_layers()


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
    # #152 residual: the anchor wizard + manual board are rank surfaces too —
    # without these, notification-nudge gating (keyed off last_rank_at)
    # undercounted users who rank exclusively via anchors or reorders.
    "anchor_answered":              "last_rank_at",
    "ranking_reorder":              "last_rank_at",
    "match_viewed":                 "last_match_seen_at",
    "trade_proposed":               "last_trade_proposed_at",
    "counter_sent":                 "last_trade_proposed_at",
    "push_sent":                    "last_push_sent_at",
}

# Event types that count toward the daily ranking streak. Adding a new rank
# surface? Add it here too — and make sure the corresponding call site is
# wired through user-events `record_event()` (NOT the legacy
# wrapped_collector.record_event, which is frozen — analytics P0 cutover,
# docs/plans/analytics-platform/lld.md §6.4).
#
# tier_save joined at the P0 cutover: the tiers-save route now records it
# via record_event(), so tier saves advance the streak like trio swipes.
#
# anchor_answered + ranking_reorder joined for #152: the Pick Anchor wizard
# and the manual board (which Quick Rank also posts through) are first-class
# ranking surfaces, but they never advanced the streak — a user who ranked
# daily via anchors or reorders was stuck at whatever streak an earlier
# trio/tier day had left behind ("my streak always stays at 1").
_RANK_STREAK_EVENTS: frozenset[str] = frozenset({
    "trio_swipe",
    "tier_save",
    "ranking_complete_first_time",
    "anchor_answered",
    "ranking_reorder",
})


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
    tz:          str | None = None,
) -> dict | None:
    """Append one row to user_events AND bump the matching users.last_*_at
    column (and device snapshot columns) in a single transaction.

    Always inserts a new row — never overwrites prior events. The denorm
    columns on `users` are pointers to the most recent event of each type
    so notification gating queries don't have to scan the full log.

    Returns the post-event streak snapshot when `event_type` is a
    rank-class event (so callers don't need a follow-up SELECT). Returns
    None for non-rank events or when logging fails.

    Failures are logged and swallowed — event logging must never break the
    surrounding business logic.
    """
    if not user_id or not event_type:
        return None
    now = _now()
    streak_result: dict | None = None
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
            # Streak transition runs inside the same transaction so a crash
            # mid-write can't desync user_events from the streak counter.
            # Return the post-state so the caller doesn't need a follow-up
            # SELECT (eliminates a separate read transaction + race window).
            if event_type in _RANK_STREAK_EVENTS:
                streak_result = _recompute_streak_on_rank_event(conn, user_id, tz)
    except Exception as e:
        print(f"[record_event] {user_id}/{event_type} failed: {e}")
        return None
    return streak_result


def _recompute_streak_on_rank_event(conn, user_id: str, tz: str | None) -> dict | None:
    """Advance the user's daily ranking streak using the local day implied
    by `tz` (IANA name, e.g. 'America/New_York'). Falls back to UTC when tz
    is missing/invalid. Idempotent — multiple ranks on the same local day
    are a no-op for streak math.

    Same day      → no-op
    +1 local day  → current_streak += 1, longest = max(longest, current)
    Gap > 1       → reset current_streak to 1
    First ever    → set current_streak = longest_streak = 1

    Returns the post-state (current/longest/last_rank_local_date) for the
    caller to inline in its response — None only if the user row is missing.
    """
    zone = None
    if tz and ZoneInfo is not None:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = None
    today_local = datetime.now(zone or timezone.utc).date()

    row = conn.execute(
        select(
            users_table.c.current_streak,
            users_table.c.longest_streak,
            users_table.c.last_rank_local_date,
        ).where(users_table.c.sleeper_user_id == user_id)
    ).first()
    if row is None:
        return None  # user row not found — nothing to update

    current  = row.current_streak  or 0
    longest  = row.longest_streak  or 0
    last_str = row.last_rank_local_date

    last_date = None
    if last_str:
        try:
            last_date = datetime.strptime(last_str, "%Y-%m-%d").date()
        except Exception:
            last_date = None

    if last_date == today_local:
        # Same-day re-rank: no write, but return the current state so the
        # caller can still inline it in its response.
        return {
            "current":              current,
            "longest":              longest,
            "last_rank_local_date": last_str,
        }

    if last_date is None or (today_local - last_date).days > 1:
        new_current = 1
    else:  # exactly +1 day
        new_current = current + 1

    new_longest = max(longest, new_current)
    today_iso   = today_local.isoformat()
    conn.execute(
        update(users_table)
        .where(users_table.c.sleeper_user_id == user_id)
        .values(
            current_streak       = new_current,
            longest_streak       = new_longest,
            last_rank_local_date = today_iso,
            last_rank_tz         = tz,
        )
    )
    return {
        "current":              new_current,
        "longest":              new_longest,
        "last_rank_local_date": today_iso,
    }


# insert_client_events() (the v0 per-row-autocommit write half of POST
# /api/events) was retired in analytics-platform P1: the ingest pipeline now
# lives in backend/analytics_ingest.py, which writes one batch in a single
# transaction on the dedicated ingest_engine (150 ms lock budget,
# BEGIN IMMEDIATE). The old per-row-transaction pattern was the self-inflicted
# lock-contention the LLD (FR-8/KD-12) exists to prevent — do not reintroduce.


def link_identity(
    device_id: str,
    *,
    sleeper_user_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Idempotent upsert of an identity_links row (tracking plan v2 §S1).

    Called on every successful sign-in that carries a device_id — stitches
    pre-auth 'device:<device_id>' user_events rows to the signed-in identity.
    Re-linking the same (device, identity) pair is a no-op. Best-effort:
    failures are logged and swallowed.
    """
    if not device_id or not (sleeper_user_id or account_id):
        return
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                select(identity_links_table.c.id).where(and_(
                    identity_links_table.c.device_id == device_id,
                    identity_links_table.c.sleeper_user_id.is_(None)
                        if sleeper_user_id is None
                        else identity_links_table.c.sleeper_user_id == sleeper_user_id,
                    identity_links_table.c.account_id.is_(None)
                        if account_id is None
                        else identity_links_table.c.account_id == account_id,
                )).limit(1)
            ).first()
            if exists:
                return
            conn.execute(
                insert(identity_links_table).values(
                    device_id       = device_id,
                    sleeper_user_id = sleeper_user_id,
                    account_id      = account_id,
                    linked_at       = _now(),
                )
            )
    except Exception as e:
        print(f"[link_identity] {device_id} failed: {e}")


def _streak_lapsed(last_local_date_str: str | None, tz: str | None) -> bool:
    """True when a stored streak is stale for display: last_rank_local_date
    is missing/unparseable, or more than 1 day behind "today" in `tz`
    (IANA name; missing/invalid falls back to UTC — same rule as the write
    side). Mirrors the write-side transition exactly — a gap > 1 local day
    is what resets the counter — so "yesterday" still displays (ranking
    today would increment it), and a date at/ahead of today displays too
    (tz-frame skew, e.g. reading in UTC a date written in UTC+14).
    """
    if not last_local_date_str:
        return True
    try:
        last_date = datetime.strptime(last_local_date_str, "%Y-%m-%d").date()
    except Exception:
        return True
    zone = None
    if tz and ZoneInfo is not None:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = None
    today_local = datetime.now(zone or timezone.utc).date()
    return (today_local - last_date).days > 1


def get_user_streak(user_id: str, tz: str | None = None) -> dict:
    """Read-only streak snapshot for the streak chip + leaderboard.

    `current` is the EFFECTIVE streak: the stored counter decays to 0 at
    display time once the last rank is more than 1 local day old (the next
    rank event would reset it to 1 anyway — the stored row only rewrites
    then, so without read-time decay a lapsed user shows their old streak
    forever). The stored row is never mutated here; write-side math in
    _recompute_streak_on_rank_event() keys off the stored value + date and
    is unaffected. `longest` never decays.

    Local-day frame: `tz` (the viewer's X-User-TZ header, threaded by the
    routes) when provided, else the stored last_rank_tz the date was
    written in, else UTC.
    """
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    users_table.c.current_streak,
                    users_table.c.longest_streak,
                    users_table.c.last_rank_local_date,
                    users_table.c.last_rank_tz,
                ).where(users_table.c.sleeper_user_id == user_id)
            ).first()
        if row is None:
            return {"current": 0, "longest": 0, "last_rank_local_date": None}
        current = row.current_streak or 0
        if current and _streak_lapsed(row.last_rank_local_date,
                                      tz or row.last_rank_tz):
            current = 0
        return {
            "current":              current,
            "longest":              row.longest_streak or 0,
            "last_rank_local_date": row.last_rank_local_date,
        }
    except Exception as e:
        print(f"[get_user_streak] {user_id} failed: {e}")
        return {"current": 0, "longest": 0, "last_rank_local_date": None}


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------
# Powers GET /api/leaderboard. Two scopes (league / universal) × two metrics
# (streak / ranks-in-window). Universal queries are 5-min cached server-side
# in server.py — these functions are the uncached reads.
#
# All ordering + pagination is pushed into SQL: the top slice is `ORDER BY
# value DESC, user_id ASC LIMIT N`, and a per-user "what's my rank" query
# avoids reading the full set when a viewer is below the top slice. Both
# DBs we target (Postgres on Render, SQLite for dev) support this shape.

# Tie-break ordering: secondary ASC on user_id so the order is deterministic
# across calls + matches what the cache stored on its first miss. The
# self-rank query below uses the same comparison so its rank lines up.
def _resolve_league_user_ids(league_id: str) -> list[str] | None:
    """Return the list of member user_ids in a league, or [] if the league
    has no members on file. Returns None on DB error."""
    try:
        with engine.begin() as conn:
            return [
                r.user_id for r in conn.execute(
                    select(league_members_table.c.user_id)
                    .where(league_members_table.c.league_id == league_id)
                ).fetchall()
            ]
    except Exception as e:
        print(f"[_resolve_league_user_ids] failed: {e}")
        return None


def load_leaderboard(
    *,
    metric:    str,                 # 'streak' | 'ranks'
    window:    str | None = None,   # 'week' | 'month' | 'season' | 'all' — only used by metric=ranks
    league_id: str | None = None,   # required when scope='league', omitted for universal
    limit:     int = 50,
) -> dict:
    """Return the top `limit` rows. is_self is always False here — the
    endpoint stamps it on the way out so a single cached payload can
    personalize for every viewer. self_row is computed separately by
    `get_self_leaderboard_row()`.
    """
    if metric not in ("streak", "ranks"):
        raise ValueError(f"unsupported metric: {metric}")
    if metric == "ranks" and window not in ("week", "month", "season", "all"):
        raise ValueError(f"unsupported window: {window}")

    league_user_ids: list[str] | None = None
    if league_id:
        league_user_ids = _resolve_league_user_ids(league_id) or []
        if not league_user_ids:
            return {"metric": metric, "window": window, "league_id": league_id,
                    "rows": [], "self_row": None}

    if metric == "streak":
        top = _streak_top(league_user_ids, limit)
    else:
        top = _rank_count_top(_window_since(window), league_user_ids, limit)

    if not top:
        return {"metric": metric, "window": window, "league_id": league_id,
                "rows": [], "self_row": None}

    user_meta = _user_meta({uid for uid, _ in top})
    rows = [
        _build_row(rank=i + 1, uid=uid, value=val, meta=user_meta, self_user_id=None)
        for i, (uid, val) in enumerate(top)
    ]
    return {"metric": metric, "window": window, "league_id": league_id,
            "rows": rows, "self_row": None}


def get_self_leaderboard_row(
    *,
    metric:    str,
    window:    str | None,
    league_id: str | None,
    user_id:   str,
) -> dict | None:
    """Return the viewer's own (rank, value, display fields) on the given
    leaderboard, or None if they aren't on it. Runs an O(log N)-ish query
    that doesn't touch the cache — kept cheap by computing rank in SQL via
    a single COUNT-of-better-positions, not by re-ranking everyone."""
    league_user_ids: list[str] | None = None
    if league_id:
        league_user_ids = _resolve_league_user_ids(league_id) or []
        if not league_user_ids or user_id not in league_user_ids:
            return None

    if metric == "streak":
        result = _streak_self_rank(user_id, league_user_ids)
    else:
        result = _rank_count_self_rank(user_id, _window_since(window), league_user_ids)
    if result is None:
        return None
    rank, value = result
    meta = _user_meta({user_id})
    return _build_row(rank=rank, uid=user_id, value=value, meta=meta, self_user_id=user_id)


def _build_row(*, rank: int, uid: str, value: int, meta: dict, self_user_id: str | None) -> dict:
    m = meta.get(uid, {})
    return {
        "rank":         rank,
        "user_id":      uid,
        "username":     m.get("username"),
        "display_name": m.get("display_name") or m.get("username") or uid,
        "avatar":       m.get("avatar"),
        "value":        value,
        "is_self":      (uid == self_user_id),
    }


def _streak_top(
    league_user_ids: list[str] | None,
    limit: int,
) -> list[tuple[str, int]]:
    """Top-N (user_id, current_streak) ordered DESC, ties broken by user_id ASC.

    Only EFFECTIVE (non-lapsed) streaks make the board: the stored counter
    only rewrites on a user's next rank event, so without read-time decay a
    user who stopped ranking would squat on top spots forever. Each row is
    checked against its own local today (frame = the row's stored
    last_rank_tz, UTC fallback — see _streak_lapsed). SQL prefilters to
    last_rank_local_date within 2 UTC days — a date older than that is
    lapsed in EVERY timezone (offsets span UTC-12..+14) — so the fetch is
    bounded by recently-active users; Python then applies the exact
    per-row tz check. Survivors keep effective == stored value, so the SQL
    ordering is already final — filter and slice, no re-sort needed.
    """
    try:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
        with engine.begin() as conn:
            stmt = select(
                users_table.c.sleeper_user_id,
                users_table.c.current_streak,
                users_table.c.last_rank_local_date,
                users_table.c.last_rank_tz,
            ).where(users_table.c.current_streak.is_not(None)) \
             .where(users_table.c.current_streak > 0) \
             .where(users_table.c.last_rank_local_date >= cutoff) \
             .order_by(users_table.c.current_streak.desc(), users_table.c.sleeper_user_id.asc())
            if league_user_ids is not None:
                stmt = stmt.where(users_table.c.sleeper_user_id.in_(league_user_ids))
            rows = conn.execute(stmt).fetchall()
        return [
            (r.sleeper_user_id, r.current_streak)
            for r in rows
            if not _streak_lapsed(r.last_rank_local_date, r.last_rank_tz)
        ][:limit]
    except Exception as e:
        print(f"[_streak_top] failed: {e}")
        return []


def _streak_self_rank(
    user_id: str,
    league_user_ids: list[str] | None,
) -> tuple[int, int] | None:
    """Return (rank, current_streak) for the user, or None if their
    streak is null/0/lapsed or the user row is missing. Rank is
    1 + count-of-better-positions:
        rank = 1 + COUNT(WHERE streak > mine OR (streak == mine AND uid < mine))
    restricted to non-lapsed rows so the rank lines up with _streak_top's
    board. The lapse check needs each row's own last_rank_tz frame, so the
    "better" rows are fetched (bounded by the same 2-UTC-day prefilter as
    _streak_top) and counted in Python instead of a pure SQL COUNT.
    """
    try:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    users_table.c.current_streak,
                    users_table.c.last_rank_local_date,
                    users_table.c.last_rank_tz,
                ).where(users_table.c.sleeper_user_id == user_id)
            ).first()
            if row is None or not row.current_streak or row.current_streak <= 0:
                return None
            if _streak_lapsed(row.last_rank_local_date, row.last_rank_tz):
                return None  # lapsed viewers aren't on the board at all
            my_streak = row.current_streak

            stmt = select(
                users_table.c.sleeper_user_id,
                users_table.c.last_rank_local_date,
                users_table.c.last_rank_tz,
            ).where(users_table.c.last_rank_local_date >= cutoff) \
             .where(
                or_(
                    users_table.c.current_streak > my_streak,
                    and_(
                        users_table.c.current_streak == my_streak,
                        users_table.c.sleeper_user_id < user_id,
                    ),
                )
            )
            if league_user_ids is not None:
                stmt = stmt.where(users_table.c.sleeper_user_id.in_(league_user_ids))
            better = conn.execute(stmt).fetchall()
            ahead = sum(
                1 for r in better
                if not _streak_lapsed(r.last_rank_local_date, r.last_rank_tz)
            )
            return (ahead + 1, int(my_streak))
    except Exception as e:
        print(f"[_streak_self_rank] {user_id} failed: {e}")
        return None


# Per-player action weighting (operator rule 2026-07-26): one PLAYER placed =
# one action, regardless of surface. A trio swipe or anchor answer touches one
# comparison/rung → weight 1 (no prop). A Quick Set tier save batches N
# players into ONE event carrying props.changed_count; a Quick Rank / manual
# reorder carries props.moves_count. COUNT(*) over events would score a
# 12-player tier save the same as a single swipe, underweighting QuickSet
# users on the Ranks leaderboard — so both leaderboard readers aggregate
# weights in Python (props is a JSON TEXT column; cross-dialect JSON
# extraction in SQL isn't worth it at current scale, and both readers sit
# behind the 5-min leaderboard cache).
_RANK_EVENT_WEIGHT_PROP = {"tier_save": "changed_count",
                           "ranking_reorder": "moves_count"}


def _rank_event_weight(event_type: str, props_raw) -> int:
    prop = _RANK_EVENT_WEIGHT_PROP.get(event_type)
    if prop is None:
        return 1
    try:
        val = json.loads(props_raw or "{}").get(prop)
        # Missing prop (old rows) → 1; explicit 0 (empty save/skip) → 0.
        return max(0, int(val)) if val is not None else 1
    except (TypeError, ValueError):
        return 1


def _rank_action_counts(
    since_iso: str | None,
    league_user_ids: list[str] | None,
) -> dict[str, int]:
    """user_id → per-player-weighted action count for rank-class events."""
    with engine.begin() as conn:
        stmt = select(
            user_events_table.c.user_id,
            user_events_table.c.event_type,
            user_events_table.c.props,
        ).where(user_events_table.c.event_type.in_(list(_RANK_STREAK_EVENTS)))
        if since_iso:
            stmt = stmt.where(user_events_table.c.occurred_at >= since_iso)
        if league_user_ids is not None:
            stmt = stmt.where(user_events_table.c.user_id.in_(league_user_ids))
        totals: dict[str, int] = {}
        for r in conn.execute(stmt):
            totals[r.user_id] = totals.get(r.user_id, 0) \
                + _rank_event_weight(r.event_type, r.props)
        return totals


def _rank_count_top(
    since_iso: str | None,
    league_user_ids: list[str] | None,
    limit: int,
) -> list[tuple[str, int]]:
    """Top-N (user_id, weighted_action_count) for rank-class events since
    `since_iso` — one player placed = one action (see _rank_event_weight)."""
    try:
        totals = _rank_action_counts(since_iso, league_user_ids)
        ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(uid, cnt) for uid, cnt in ranked[:limit] if cnt > 0]
    except Exception as e:
        print(f"[_rank_count_top] failed: {e}")
        return []


def _rank_count_self_rank(
    user_id: str,
    since_iso: str | None,
    league_user_ids: list[str] | None,
) -> tuple[int, int] | None:
    """Return (rank, count) for the viewer on the rank-count leaderboard,
    using the same per-player weighting as _rank_count_top."""
    try:
        totals = _rank_action_counts(since_iso, league_user_ids)
        my_cnt = totals.get(user_id, 0)
        if not my_cnt:
            return None
        ahead = sum(
            1 for uid, cnt in totals.items()
            if cnt > my_cnt or (cnt == my_cnt and uid < user_id)
        )
        return (ahead + 1, my_cnt)
    except Exception as e:
        print(f"[_rank_count_self_rank] {user_id} failed: {e}")
        return None


def _user_meta(user_ids: set[str]) -> dict[str, dict]:
    """Bulk-fetch username/display_name/avatar for the IDs we'll render."""
    if not user_ids:
        return {}
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    users_table.c.sleeper_user_id,
                    users_table.c.username,
                    users_table.c.display_name,
                    users_table.c.avatar,
                ).where(users_table.c.sleeper_user_id.in_(list(user_ids)))
            ).fetchall()
        return {
            r.sleeper_user_id: {
                "username":     r.username,
                "display_name": r.display_name,
                "avatar":       r.avatar,
            }
            for r in rows
        }
    except Exception as e:
        print(f"[_user_meta] failed: {e}")
        return {}


def _window_since(window: str | None) -> str | None:
    """Convert a leaderboard window label to an ISO-UTC cutoff. None = all-time."""
    if not window or window == "all":
        return None
    now = datetime.now(timezone.utc)
    if window == "week":
        return (now - timedelta(days=7)).isoformat()
    if window == "month":
        return (now - timedelta(days=30)).isoformat()
    if window == "season":
        # NFL season starts ~Sept 1. If today is before Sept 1, use the
        # prior year's Sept 1 — keeps the leaderboard meaningful in the
        # April–August offseason instead of returning an empty list.
        today = now.date()
        cutoff_year = today.year if today.month >= 9 else today.year - 1
        return datetime(cutoff_year, 9, 1, tzinfo=timezone.utc).isoformat()
    return None


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


def get_wrapped_cutover_iso() -> str:
    """ISO-UTC boundary of the wrapped_events → user_events cutover.

    Reads the `analytics.wrapped_cutover_at` model_config row (epoch seconds,
    seeded once by _migrate_db) and converts to the ISO-TEXT frame every
    timestamp column uses. Returns "" when the key is missing (fresh DB that
    never had legacy wrapped writers) — "" compares below every ISO string,
    so the union reader then serves user_events only.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(model_config_table.c.value)
                .where(model_config_table.c.key == "analytics.wrapped_cutover_at")
            ).first()
        if row and row[0] is not None:
            return datetime.fromtimestamp(float(row[0]), timezone.utc).isoformat()
    except Exception as e:
        print(f"[get_wrapped_cutover_iso] failed: {e}")
    return ""


def set_config(key: str, value: float, source: str = "unspecified") -> dict:
    """
    Update one model_config value, stamping updated_at and appending a
    model_config_changes row — one transaction (M1, fit-challenger LLD §5.1).
    Raises KeyError for unknown keys (unchanged contract — no ad-hoc keys).
    """
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        existing = conn.execute(
            select(model_config_table).where(model_config_table.c.key == key)
        ).fetchone()
        if existing is None:
            raise KeyError(f"Unknown config key: {key!r}")
        conn.execute(
            update(model_config_table)
            .where(model_config_table.c.key == key)
            .values(value=value, updated_at=now)
        )
        conn.execute(insert(model_config_changes_table).values(
            key=key, old_value=existing.value, new_value=value,
            changed_at=now, source=source))
    return {"key": key, "value": value, "old_value": existing.value}


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


# The method strings POST /api/ranking-method validates (server.py:6303),
# mirrored in backend/tests/fixtures/seed_ui_test_db.py:138.
RANKING_METHODS = ("trio", "manual", "tiers", "anchor", "quickset")


def set_ranking_method_if_unset(
    user_id: str,
    method: str,
    allow_over: tuple[str, ...] = (),
) -> bool:
    """P0-1 — record the ranking method at the point of USE, first-use wins.

    A SINGLE conditional UPDATE, so it is race-free under concurrent saves:
    there is no read-then-write window in which two requests can both decide
    the column is empty. Returns True iff this call wrote the value.

    FIRST-USE WINS, not last-use wins. The unlock rule in
    get_rankings_progress is method-dependent, so overwriting an established
    method can RE-LOCK a user who already qualified under the old one — the
    exact regression the monotonic unlocked_formats floor was added for
    (server.py:6177-6187).  Writing only where there was nothing means this
    helper can never subtract an unlock.

    `allow_over` is the one deliberate widening: 'anchor' is the only method
    string whose unlock rule can never succeed (it falls to the trio branch),
    so a completeness-marking tiers/quickset save is allowed to overwrite it
    and ONLY it. See docs/plans/audit-p0-remediation/lld-p0-1.md §4.2.
    """
    if method not in RANKING_METHODS:
        return False
    col  = users_table.c.ranking_method
    cond = or_(col.is_(None), col == "")
    if allow_over:
        cond = or_(cond, col.in_(tuple(allow_over)))
    with engine.begin() as conn:
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .where(cond)
            .values(ranking_method=method)
        )
    return bool(res.rowcount)


def get_ranking_method(user_id: str) -> str | None:
    """Return the user's stored ranking method, or None if not set."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.ranking_method).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        return row.ranking_method if row else None


def get_profile_public(user_id: str) -> bool:
    """Public-profile opt-in (teardown 06-04). Missing row/NULL = private."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.profile_public).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        return bool(row.profile_public) if row else False


def set_profile_public(user_id: str, public: bool) -> None:
    """Persist the user's public-profile opt-in. Creates the users row if
    the toggle beats session_init's background upsert (same race guard as
    the verified marker)."""
    val = 1 if public else 0
    with engine.begin() as conn:
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(profile_public=val)
        )
        if res.rowcount == 0:
            conn.execute(insert(users_table).values(
                sleeper_user_id=user_id,
                profile_public=val,
                created_at=_now(),
            ))


STUD_TAX_MODES = ("market", "heavy", "off")


def get_stud_tax_mode(user_id: str) -> str:
    """#215 — the user's stored stud-tax mode. Missing row / NULL / unknown
    value = 'market' (the #214 retuned default)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.stud_tax_mode).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    mode = row.stud_tax_mode if row else None
    return mode if mode in STUD_TAX_MODES else "market"


def set_stud_tax_mode(user_id: str, mode: str) -> None:
    """#215 — persist the user's stud-tax mode. Validates against
    STUD_TAX_MODES; creates the users row if the setting write beats
    session_init's background upsert (same race guard as profile_public)."""
    if mode not in STUD_TAX_MODES:
        raise ValueError(f"invalid stud_tax_mode: {mode!r}")
    with engine.begin() as conn:
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(stud_tax_mode=mode)
        )
        if res.rowcount == 0:
            conn.execute(insert(users_table).values(
                sleeper_user_id=user_id,
                stud_tax_mode=mode,
                created_at=_now(),
            ))


PICK_PRICING_MODES = ("tier_ladder", "market_slots")


def get_pick_pricing_mode(user_id: str) -> str:
    """M6b — the user's stored pick-pricing mode. Missing row / NULL /
    unknown value = 'tier_ladder' (today's shipped behaviour). Callers go
    through trade_service.pick_pricing_mode_for_user, which also applies the
    `trade.slot_pricing` flag gate."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.pick_pricing_mode).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    mode = row.pick_pricing_mode if row else None
    return mode if mode in PICK_PRICING_MODES else "tier_ladder"


def set_pick_pricing_mode(user_id: str, mode: str) -> None:
    """M6b — persist the user's pick-pricing mode. Same validation + row-race
    guard as set_stud_tax_mode."""
    if mode not in PICK_PRICING_MODES:
        raise ValueError(f"invalid pick_pricing_mode: {mode!r}")
    with engine.begin() as conn:
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(pick_pricing_mode=mode)
        )
        if res.rowcount == 0:
            conn.execute(insert(users_table).values(
                sleeper_user_id=user_id,
                pick_pricing_mode=mode,
                created_at=_now(),
            ))


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


def _parse_extra_keys(raw: str | None) -> dict:
    """Top-level keys of a per-format JSON column that are NOT scoring formats.

    `_parse_per_format_json` deliberately narrows its output to SCORING_FORMATS;
    any writer that round-trips the column through it must merge these back or
    it silently DELETES them. That is not hypothetical — the rookie-scope
    pre-save snapshot (`__PRE_ROOKIE_SCOPE_KEY__`) lives as a sibling key in
    `users.tier_overrides`, and without this merge the very next tier save of
    either format would destroy it.

    Deliberately NOT applied to `tiers_saved` / `anchor_scale`: nothing stores
    sibling keys there, and narrowing is the correct behaviour for a column
    with no extras.
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
        # Analytics P0 cutover (LLD §6.4): the legacy wrapped_collector
        # tier_save hook that lived here is gone — the tiers-save route
        # records tier_save into user_events via record_event() (which now
        # also advances the ranking streak; see _RANK_STREAK_EVENTS).
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


# ── Override write timestamps (F2, 2026-08-18) ───────────────────────────────
# `docs/reviews/2026-08-18-valuation-age-audit.md` §8 F2: a swipe recorded
# AFTER a pin should release it, which needs to know WHEN the pin was written.
# Stored as a SIBLING key — {fmt: {pid: iso8601}} — rather than by changing the
# per-format value shape from `{pid: elo}` to `{pid: {elo, at}}`. The sibling
# form needs no migration, cannot break `load_tier_overrides`' float cast, and
# leaves every existing reader (og_image, accounts, the restore path) untouched.
# A pid with an override but no stamp is a LEGACY pin; ranking_service's
# `pin_legacy_at_epoch` knob decides what that means (default: permanent).
PIN_STAMPS_KEY = "__override_at__"


def _stamps_from_extras(extras: dict, scoring_format: str) -> dict[str, str]:
    """The {pid: iso} stamp map for one format out of a parsed extras blob."""
    blob = extras.get(PIN_STAMPS_KEY)
    if not isinstance(blob, dict):
        return {}
    fmt = blob.get(scoring_format)
    if not isinstance(fmt, dict):
        return {}
    return {str(k): str(v) for k, v in fmt.items() if v}


def save_tier_overrides(
    user_id: str,
    overrides: dict[str, float],
    scoring_format: str = DEFAULT_SCORING,
    stamps: dict[str, str] | None = None,
) -> None:
    """
    Persist the user's tier/reorder override map for one scoring format.
    Other formats' overrides are left untouched.

    `stamps` — {pid: iso8601} write times for those overrides (F2). Passing
    None keeps whatever stamps are already stored, so a caller that has not
    been updated cannot silently strip them. Either way the stored map is
    pruned to the pids actually present in `overrides`: a stamp without an
    override is dead weight, and leaving it would re-stamp a pin the user
    cleared and later re-created.
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
        raw = row.tier_overrides if row else None
        all_overrides = _parse_per_format_json(raw, is_list=False)
        # Non-format sibling keys (the pre-rookie-scope snapshot, the override
        # stamps) survive the round-trip. `extras` FIRST so a format key can
        # never be shadowed.
        extras = _parse_extra_keys(raw)
        # Cast ELO values to float so JSON stays clean
        all_overrides[scoring_format] = {pid: float(elo) for pid, elo in overrides.items()}

        stored = _stamps_from_extras(extras, scoring_format)
        if stamps is not None:
            stored = {str(pid): str(at) for pid, at in stamps.items() if at}
        stored = {pid: at for pid, at in stored.items() if pid in overrides}
        blob = extras.get(PIN_STAMPS_KEY)
        blob = dict(blob) if isinstance(blob, dict) else {}
        if stored:
            blob[scoring_format] = stored
        else:
            blob.pop(scoring_format, None)
        if blob:
            extras[PIN_STAMPS_KEY] = blob
        else:
            extras.pop(PIN_STAMPS_KEY, None)

        conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(tier_overrides=json.dumps({**extras, **all_overrides}))
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


def load_tier_override_stamps(
    user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict[str, str]:
    """Return {player_id: iso8601} write times for this user + format's pins.

    Missing pids are LEGACY pins written before F2 shipped. Deliberately a
    separate read from `load_tier_overrides` so the override load path keeps
    its exact shape and failure modes.
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.tier_overrides).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    return _stamps_from_extras(
        _parse_extra_keys(row.tier_overrides if row else None), scoring_format)


# ── Rookie-scope pre-save snapshot (M2, LLD §3.2) ─────────────────────────
# `tier_overrides` is a wholesale-overwritten JSON blob with NO history: a
# prior filtering bug permanently destroyed a user's board. Rookie scope is
# the first feature that writes a PARTIAL board, so a one-time snapshot of
# the whole blob is taken before the first scoped save — the operator restore
# path (docs/runbook.md § "Rookie-scope board restore") is a precondition for
# flipping `ranks.rookie_subset`.
#
# Stored as a sibling key INSIDE the same column — no new table, no
# migration. `_parse_extra_keys` above is what keeps it alive.
PRE_ROOKIE_SCOPE_KEY = "__pre_rookie_scope__"
_PRE_ROOKIE_SCOPE_VERSION = 1


def take_tier_override_snapshot(user_id: str,
                                reason: str = "pre_scope_v1") -> bool:
    """One-shot snapshot of every format's tier overrides. Idempotent.

    Returns True iff a snapshot was written; False when one already exists
    (or the user has no row). Cheap after the first call — one indexed read.
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
        if row is None:
            return False
        raw = row.tier_overrides
        extras = _parse_extra_keys(raw)
        if PRE_ROOKIE_SCOPE_KEY in extras:
            return False
        all_overrides = _parse_per_format_json(raw, is_list=False)
        extras[PRE_ROOKIE_SCOPE_KEY] = {
            "v":        _PRE_ROOKIE_SCOPE_VERSION,
            "taken_at": _now(),
            "reason":   reason,
            "formats":  {fmt: dict(all_overrides.get(fmt) or {})
                         for fmt in SCORING_FORMATS},
        }
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(tier_overrides=json.dumps({**extras, **all_overrides}))
        )
        return bool(res.rowcount)


def load_tier_override_snapshot(user_id: str) -> dict | None:
    """The stored pre-scope snapshot object, or None."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.tier_overrides).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    snap = _parse_extra_keys(row.tier_overrides if row else None).get(
        PRE_ROOKIE_SCOPE_KEY)
    return snap if isinstance(snap, dict) else None


def restore_tier_overrides_from_snapshot(
    user_id: str,
    scoring_format: str | None = None,
) -> dict[str, int]:
    """Operator restore. `scoring_format=None` restores BOTH formats.

    Returns {format: override_count_restored}. Does NOT delete the snapshot —
    a restore must be repeatable. The caller must have the user re-init their
    session; in-memory `_elo_overrides` are only re-read at session_init.
    """
    targets = ([scoring_format] if scoring_format
               else list(SCORING_FORMATS))
    is_postgres = not DATABASE_URL.startswith("sqlite")
    counts: dict[str, int] = {}
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
        if row is None:
            return counts
        raw = row.tier_overrides
        extras = _parse_extra_keys(raw)
        snap = extras.get(PRE_ROOKIE_SCOPE_KEY)
        if not isinstance(snap, dict):
            return counts
        formats = snap.get("formats")
        if not isinstance(formats, dict):
            return counts
        all_overrides = _parse_per_format_json(raw, is_list=False)
        for fmt in targets:
            if fmt not in SCORING_FORMATS:
                continue
            stored = formats.get(fmt)
            restored = ({pid: float(elo) for pid, elo in stored.items()}
                        if isinstance(stored, dict) else {})
            all_overrides[fmt] = restored
            counts[fmt] = len(restored)
            # The snapshot predates F2 and carries no write times, so the
            # restored pins come back as LEGACY (permanent under the default
            # pin_legacy_at_epoch). Keeping the current stamps would be worse:
            # they describe pins the restore just threw away.
            stamp_blob = extras.get(PIN_STAMPS_KEY)
            if isinstance(stamp_blob, dict):
                stamp_blob.pop(fmt, None)
                if stamp_blob:
                    extras[PIN_STAMPS_KEY] = stamp_blob
                else:
                    extras.pop(PIN_STAMPS_KEY, None)
        conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(tier_overrides=json.dumps({**extras, **all_overrides}))
        )
    return counts


def reset_user_rankings(user_id: str) -> dict[str, int]:
    """Wipe every persisted ranking artifact for one user (all formats).

    The account-auth P1 "reset my rankings" action (POST
    /api/account/reset-rankings): a newly VERIFIED owner inheriting
    squatter-authored data gets a clean slate. Unlike /api/reset (in-memory
    service state only), this deletes the PERSISTED inputs that session_init
    replays — swipe history, tier/reorder overrides, saved-tier markers,
    ranking method — plus the published member_rankings other members' trade
    math reads. elo_history snapshots are kept (telemetry trail, not
    replayed into rankings).

    Known void (M2): clearing `tier_overrides` also drops the sibling
    `__pre_rookie_scope__` snapshot. That is correct — the user asked for a
    clean slate — but it means the rookie-scope restore path does not survive
    a self-service reset. Recorded in docs/runbook.md.

    Returns row/field counts for the route's response + support log.
    """
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        res = conn.execute(
            delete(swipe_decisions_table)
            .where(swipe_decisions_table.c.user_id == user_id)
        )
        counts["swipe_decisions_deleted"] = res.rowcount or 0
        res = conn.execute(
            delete(member_rankings_table)
            .where(member_rankings_table.c.user_id == user_id)
        )
        counts["member_rankings_deleted"] = res.rowcount or 0
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(tier_overrides=None, tiers_saved=None, ranking_method=None)
        )
        counts["user_rows_cleared"] = res.rowcount or 0
    return counts


def save_anchor_scale(
    user_id: str,
    top_tier_firsts: float,
    scoring_format: str = DEFAULT_SCORING,
) -> None:
    """
    Persist the user's pick-value scale (#111) for one scoring format:
    "a top-tier asset is worth N firsts". Other formats' values are left
    untouched. Stored as JSON on users.anchor_scale, e.g. {"1qb_ppr": 3}.
    """
    is_postgres = not DATABASE_URL.startswith("sqlite")
    with engine.begin() as conn:
        if is_postgres:
            row = conn.execute(
                text("SELECT anchor_scale FROM users WHERE sleeper_user_id = :uid FOR UPDATE"),
                {"uid": user_id},
            ).fetchone()
        else:
            row = conn.execute(
                select(users_table.c.anchor_scale).where(
                    users_table.c.sleeper_user_id == user_id
                )
            ).fetchone()
        try:
            all_scales = json.loads(row.anchor_scale) if row and row.anchor_scale else {}
        except (json.JSONDecodeError, TypeError):
            all_scales = {}
        if not isinstance(all_scales, dict):
            all_scales = {}
        all_scales[scoring_format] = float(top_tier_firsts)
        conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .values(anchor_scale=json.dumps(all_scales))
        )


def load_anchor_scale(
    user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> float | None:
    """Return the user's pick-value scale for this format, or None when
    the user never set one (caller applies the legacy default)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.anchor_scale).where(
                users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
    try:
        all_scales = json.loads(row.anchor_scale) if row and row.anchor_scale else {}
        val = all_scales.get(scoring_format) if isinstance(all_scales, dict) else None
        return float(val) if val is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def mark_format_unlocked(user_id: str, scoring_format: str) -> dict:
    """Add `scoring_format` to the user's unlocked_formats list if not already present.
    Monotonic — never removes a format once unlocked.

    Returns {'inserted': bool, 'was_first': bool} so callers can detect
    first-time-ever unlock without racing — both flags are computed inside
    the same transaction as the write (postgres uses SELECT FOR UPDATE; on
    SQLite the global write lock serializes us).
    """
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
        was_first = (len(unlocked) == 0)
        inserted = scoring_format not in unlocked
        if inserted:
            unlocked.append(scoring_format)
            conn.execute(
                update(users_table)
                .where(users_table.c.sleeper_user_id == user_id)
                .values(unlocked_formats=json.dumps(unlocked))
            )
        return {"inserted": inserted, "was_first": was_first and inserted}


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
    """Insert or refresh a league record.

    The `leagues` table is keyed on `sleeper_league_id` ALONE, so there is
    exactly one row per league — owned by the first member to import it (the
    "importer-owner", recorded in `user_id`). When a *second* member of an
    already-imported league calls session_init, we must NOT INSERT a fresh
    row: that violated the PK and raised
    `UNIQUE constraint failed: leagues.sleeper_league_id`, which the caller
    swallowed as "DB upsert failed (continuing)". Instead we upsert on the
    PK and refresh only league-level metadata (`name`, `updated_at`),
    preserving the importer-owner's row.

    Per-member rosters are NOT stored here — `league_members` is the
    authoritative per-(league, user) roster store. `roster_data` /
    `opponent_data` therefore hold only the importer-owner's initial
    snapshot (kept for provenance; not read back anywhere) and are never
    overwritten by other members.
    """
    roster_json   = json.dumps(user_player_ids)
    opponent_json = json.dumps(opponent_rosters)
    now = _now()

    row = {
        "sleeper_league_id": league_id,
        "user_id":           user_id,
        "name":              name,
        "season":            season,
        "roster_data":       roster_json,
        "opponent_data":     opponent_json,
        "created_at":        now,
        "updated_at":        now,
    }

    with engine.begin() as conn:
        # Single atomic upsert on the PK — race-safe against two members of
        # the same league hitting session_init concurrently (both would
        # otherwise SELECT-miss then INSERT, and the loser would crash).
        if DATABASE_URL.startswith("sqlite"):
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        stmt = dialect_insert(leagues_table).values(row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sleeper_league_id"],
            set_={
                "name":       stmt.excluded.name,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        conn.execute(stmt)
    # Analytics P0 cutover (LLD §6.4): the legacy wrapped_collector
    # 'league_sync' hook that lived here is gone — session_init records
    # 'league_synced' into user_events via record_event() right after this
    # upsert (server.py), which is the surviving writer.


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
        # Analytics P0 cutover (LLD §6.4): 'swipe' now lands in user_events
        # (equivalent props to the frozen wrapped_events writer). Non-throwing
        # inside record_event itself.
        record_event(user_id, "swipe", source="api",
                     props={"count": len(rows),
                            "scoring_format": scoring_format})


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

# G-049 / D-068 — replay window for save_trade_decision's idempotency guard.
#
# Sized from prod (2026-08-18, 933 trade_decisions rows). Grouping by
# (user_id, league_id, trade_id, decision) and measuring the gap to the
# previous row gives two cleanly separated populations:
#   * 40 double-writes, the WIDEST 0.200 s apart  (client double-fire)
#   * 23 genuine re-decisions, the CLOSEST 147.7 s apart (card re-served
#     by a deck regeneration and swiped again)
# Nothing at all falls between 0.2 s and 147.7 s — a 738x empty band. 10 s
# sits in the middle of it with 50x headroom on the duplicate side and 14x
# on the re-decision side. Raising this past ~120 s would start swallowing
# decisions the user really made; lowering it below ~1 s would start
# letting double-fires through.
TRADE_DECISION_DEDUPE_SECONDS = 10.0


def _decision_replay_gap_ok(prev_created_at: str | None, now_iso: str) -> bool:
    """True when `prev_created_at` is recent enough to call the incoming
    write a replay of it. Any unparseable/absent timestamp returns False —
    the guard FAILS OPEN, because losing a real decision is strictly worse
    than keeping a duplicate row."""
    if not prev_created_at:
        return False
    try:
        prev = datetime.fromisoformat(prev_created_at)
        now  = datetime.fromisoformat(now_iso)
    except (TypeError, ValueError):
        return False
    # Legacy rows may be naive; treat those as UTC rather than crashing on a
    # naive/aware subtraction.
    if prev.tzinfo is None:
        prev = prev.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = (now - prev).total_seconds()
    return 0 <= delta <= TRADE_DECISION_DEDUPE_SECONDS


def save_trade_decision(
    user_id: str,
    league_id: str,
    trade_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
    decision: str,
) -> bool:
    """Persist a high-level trade card decision (like/pass).

    Returns **True** when a row was written and **False** when the call was
    recognised as a REPLAY of the row immediately preceding it and skipped
    (G-049).

    `save_trade_swipes()` MUST be skipped on a False return. The duplicated
    row here is only the fingerprint; the actual harm is the doubled
    `trade_k_pass`, and `swipe_decisions` carries no trade/league identity
    of its own, so this return value is the single point in the write path
    where a replay can still be recognised.

    `RankingService.record_trade_signal()` is deliberately NOT gated on it
    (D-073). It fires before this call in both routes and appends to an
    in-memory list that `replay_from_db` rebuilds from `swipe_decisions` at
    every session_init — derived state, never persisted, so the doubling it
    keeps is bounded by one session and self-heals. Gating it would make an
    in-session board movement depend on the DB being reachable, trading a
    bounded 2x overcount for an unbounded 0x undercount on a DB blip.

    Why a *window* and not a unique constraint
    ------------------------------------------
    Duplicate `(user_id, league_id, trade_id)` rows are legitimate in two
    separate ways, so no unique index over that triple is correct:
      * the #318 **revive path** — like -> retract -> re-like deliberately
        writes a fresh row with `retracted_at` NULL (see the column comment
        on the table definition above);
      * a **genuine re-decision** of a re-served card — 23 such rows in
        prod, none closer together than 147.7 s.
    A unique index would break both, and could not even be created on the
    live table (63 pre-existing duplicate rows would reject it).

    So the guard fires only for the narrow signature of a double-write: a
    still-**live** (`retracted_at IS NULL`) row, same `decision`, with a
    byte-identical give/receive payload, written less than
    `TRADE_DECISION_DEDUPE_SECONDS` ago. Everything else falls through and
    is written, so no decision the user actually made is ever dropped.

    Not a distributed lock: two genuinely simultaneous requests on separate
    workers can still both miss the SELECT under READ COMMITTED. That window
    is one statement wide instead of unbounded, and closing it fully would
    need the unique index that the revive path forbids.
    """
    give_json    = json.dumps(give_player_ids)
    receive_json = json.dumps(receive_player_ids)
    now          = _now()

    with engine.begin() as conn:
        # `trade_id` is the card identity; without one there is nothing to
        # match a replay against, so such writes always insert.
        if trade_id:
            prev = conn.execute(
                select(
                    trade_decisions_table.c.created_at,
                    trade_decisions_table.c.give_player_ids,
                    trade_decisions_table.c.receive_player_ids,
                ).where(
                    and_(
                        trade_decisions_table.c.user_id   == user_id,
                        trade_decisions_table.c.league_id == league_id,
                        trade_decisions_table.c.trade_id  == trade_id,
                        trade_decisions_table.c.decision  == decision,
                        # A retracted row must NOT suppress the re-like that
                        # revives it (#318).
                        trade_decisions_table.c.retracted_at.is_(None),
                    )
                ).order_by(trade_decisions_table.c.id.desc()).limit(1)
            ).fetchone()

            if (
                prev is not None
                and prev.give_player_ids    == give_json
                and prev.receive_player_ids == receive_json
                and _decision_replay_gap_ok(prev.created_at, now)
            ):
                log.info(
                    "save_trade_decision: replay suppressed (G-049) "
                    "user=%s league=%s trade=%s decision=%s",
                    user_id, league_id, trade_id, decision,
                )
                return False

        conn.execute(insert(trade_decisions_table).values(
            user_id            = user_id,
            league_id          = league_id,
            trade_id           = trade_id,
            give_player_ids    = give_json,
            receive_player_ids = receive_json,
            decision           = decision,
            created_at         = now,
        ))
    return True


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


def load_recent_league_likes(
    league_id: str,
    exclude_user_id: str,
    days: int = 90,
) -> list[dict]:
    """
    All 'like' decisions by league-mates (everyone EXCEPT exclude_user_id) in
    this league within the last `days` days, newest first. Feeds the
    likes-you queue (Tier 2 work item 2.3a): each row is a trade the
    counterparty already wants, from THEIR perspective.

    Returns dicts: {user_id, give_player_ids: list, receive_player_ids: list,
    created_at}. Rows with undecodable JSON are skipped.
    """
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None)
              - timedelta(days=days)).isoformat()
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                trade_decisions_table.c.user_id,
                trade_decisions_table.c.give_player_ids,
                trade_decisions_table.c.receive_player_ids,
                trade_decisions_table.c.created_at,
            ).where(
                and_(
                    trade_decisions_table.c.league_id  == league_id,
                    trade_decisions_table.c.user_id    != exclude_user_id,
                    trade_decisions_table.c.decision   == "like",
                    trade_decisions_table.c.created_at >= cutoff,
                    # #318 — a retracted like must not feed the receiver's
                    # likes-you deck injection.
                    trade_decisions_table.c.retracted_at.is_(None),
                )
            ).order_by(trade_decisions_table.c.id.desc())
        ).fetchall()

    result = []
    for r in rows:
        try:
            give    = json.loads(r.give_player_ids)
            receive = json.loads(r.receive_player_ids)
        except (json.JSONDecodeError, TypeError):
            continue
        result.append({
            "user_id":            r.user_id,
            "give_player_ids":    give,
            "receive_player_ids": receive,
            "created_at":         r.created_at,
        })
    return result


# ---------------------------------------------------------------------------
# Trade impressions (Tier 2 work item 2.4 — training-data pipeline)
# ---------------------------------------------------------------------------

def log_trade_impressions(user_id: str, league_id: str, cards: list) -> None:
    """
    Batch-insert one trade_impressions row per card in deck order.

    `cards` may be TradeCard dataclass instances or plain dicts carrying the
    same field names (give_player_ids/receive_player_ids as lists). Called by
    server._run_trade_job once per completed generation job. Best-effort:
    any failure is swallowed here (and again at the call site) — impression
    logging must never break trade generation.
    """
    if not cards:
        return

    def _f(card, name, default=None):
        if isinstance(card, dict):
            return card.get(name, default)
        return getattr(card, name, default)

    shown_at = datetime.now(timezone.utc).isoformat()
    rows = []
    try:
        for pos, card in enumerate(cards):
            give = _f(card, "give_player_ids") or []
            recv = _f(card, "receive_player_ids") or []
            rows.append({
                "user_id":            user_id,
                "league_id":          league_id,
                "target_user_id":     _f(card, "target_user_id"),
                "give_player_ids":    json.dumps(list(give)),
                "receive_player_ids": json.dumps(list(recv)),
                "basis":              _f(card, "basis", "divergence"),
                "likes_you":          1 if _f(card, "likes_you", False) else 0,
                "mismatch_score":     _f(card, "mismatch_score"),
                "fairness_score":     _f(card, "fairness_score"),
                "composite_score":    _f(card, "composite_score"),
                "position_in_deck":   pos,
                "shown_at":           shown_at,
            })
        with engine.begin() as conn:
            conn.execute(insert(trade_impressions_table), rows)
    except Exception:
        pass  # training-data logging is strictly best-effort


# ── TikTok-discovery F10 (flag deck.replenishment) — weekly replenishment ───

def load_active_deck_user_leagues(days: int = 30) -> list[dict]:
    """Distinct (user_id, league_id) pairs with deck activity in the trailing
    `days` window — a trade disposition (trade_decisions) or a deck
    generation (trade_impressions). The F10 replenishment cron's eligibility
    query: only these pairs get a weekly pre-generated deck (no zombie
    churn). Demo league excluded, matching the impression writers.

    Naive-UTC cutoff mirrors load_recent_league_likes — trade_decisions
    stores naive ISO timestamps, trade_impressions stores +00:00-suffixed
    ones; both compare correctly against the naive prefix lexically.
    """
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None)
              - timedelta(days=days)).isoformat()
    pairs: set[tuple] = set()
    with engine.connect() as conn:
        for tbl, ts_col in (
            (trade_decisions_table,   trade_decisions_table.c.created_at),
            (trade_impressions_table, trade_impressions_table.c.shown_at),
        ):
            rows = conn.execute(
                select(tbl.c.user_id, tbl.c.league_id)
                .where(and_(ts_col >= cutoff,
                            tbl.c.league_id != "league_demo"))
                .distinct()
            ).fetchall()
            for r in rows:
                if r.user_id and r.league_id:
                    pairs.add((r.user_id, r.league_id))
    return [{"user_id": u, "league_id": l} for u, l in sorted(pairs)]


def load_latest_trade_impression_batch(user_id: str, league_id: str) -> list[dict]:
    """Rows of the MOST RECENT generation batch for this user-league —
    log_trade_impressions stamps every row of a job with one shared
    shown_at, so `shown_at == max(shown_at)` selects exactly the last
    served deck. Feeds F10's expiry-honesty count (cards older than the
    7-day TradeCard expiry that dropped out of the replenished deck).
    Give/receive JSON decoded; empty list when the user has no deck history.
    """
    with engine.connect() as conn:
        latest = conn.execute(
            select(func.max(trade_impressions_table.c.shown_at)).where(
                and_(trade_impressions_table.c.user_id   == user_id,
                     trade_impressions_table.c.league_id == league_id)
            )
        ).scalar()
        if not latest:
            return []
        rows = conn.execute(
            select(trade_impressions_table).where(
                and_(trade_impressions_table.c.user_id   == user_id,
                     trade_impressions_table.c.league_id == league_id,
                     trade_impressions_table.c.shown_at  == latest)
            )
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        try:
            d["give_player_ids"]    = json.loads(d["give_player_ids"])
            d["receive_player_ids"] = json.loads(d["receive_player_ids"])
        except (json.JSONDecodeError, TypeError):
            continue
        out.append(d)
    return out


def replenish_week_done(user_id: str, league_id: str, iso_week: str) -> bool:
    """True when this user-league already has a replenishment marker for
    `iso_week` — the F10 idempotency check (skip regeneration AND push)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(deck_replenish_log_table.c.id).where(
                and_(deck_replenish_log_table.c.user_id   == user_id,
                     deck_replenish_log_table.c.league_id == league_id,
                     deck_replenish_log_table.c.iso_week  == iso_week)
            )
        ).fetchone()
    return row is not None


def log_deck_replenish(user_id: str, league_id: str, iso_week: str,
                       deck_size: int, expired_count: int) -> None:
    """Write the F10 weekly marker row. Callers check replenish_week_done
    first; the uq_deck_replenish_week constraint backstops a race by
    raising, which the cron loop treats as already-done."""
    with engine.begin() as conn:
        conn.execute(insert(deck_replenish_log_table).values(
            user_id       = user_id,
            league_id     = league_id,
            iso_week      = iso_week,
            deck_size     = int(deck_size),
            expired_count = int(expired_count),
            created_at    = _now(),
        ))


def save_deck_impressions(rows: list[dict]) -> None:
    """F1 (deck.signal_v2) — batch-insert pre-built deck_impressions rows.

    Row assembly (features_json freezing, propensity capture, trade hashing)
    lives in server._log_deck_signal_impressions where the card objects,
    players_dict and the ordering-capture map are in scope; this is the thin
    write. Caller wraps in try/except — like log_trade_impressions, signal
    logging must never break trade generation.
    """
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(insert(deck_impressions_table), rows)


def save_deck_outcome(
    impression_id: str,
    action: str,
    dwell_ms: int | None = None,
    detail_expanded: bool | None = None,
    calc_opened: bool | None = None,
) -> None:
    """F1 (deck.signal_v2) — append ONE deck_outcomes row.

    Append-only by design: an undo appends alongside the original outcome,
    never mutates it; duplicate/late labels are legal. `action` is validated
    here (closed enum) so a malformed client payload can't mint junk labels.
    """
    if action not in ("viewed", "like", "pass", "not_interested", "propose", "undo"):
        raise ValueError(f"unknown deck outcome action: {action!r}")
    with engine.begin() as conn:
        conn.execute(insert(deck_outcomes_table).values(
            impression_id   = impression_id,
            action          = action,
            dwell_ms        = int(dwell_ms) if dwell_ms is not None else None,
            detail_expanded = (None if detail_expanded is None
                               else (1 if detail_expanded else 0)),
            calc_opened     = (None if calc_opened is None
                               else (1 if calc_opened else 0)),
            acted_at        = datetime.now(timezone.utc).isoformat(),
        ))


# ── Decline-reason capture (flag feedback.decline_reasons) — storage ────────
# docs/plans/decline-reason-capture/SPEC.md §3. Three thin helpers; every
# policy decision (which codes are legal, which write Elo, who may call)
# lives in the route + ranking_service, not here.

#: Layer-1 codes — the three tiles. Closed set; do not improvise labels.
PASS_REASON_LAYER1: tuple[str, ...] = ("value", "fit", "other")

#: layer-1 code → its legal layer-2 codes (SPEC §2, exact).
#:
#: `other` ("Neither") carried NO option list until 2026-08-19 — it opened the
#: free-text box directly and its only code was `other_text`. The first
#: production burst made that untenable: "Neither" was the single largest
#: bucket (9 of 19 passes, 47%), all free text, and reading it showed one
#: reason dominating — the tester did not want to trade a SPECIFIC PLAYER.
#: That is neither a price judgement nor a roster-construction judgement, so
#: it had nowhere structured to land.
#:
#: It is TWO codes, not one, because the free text points in two directions
#: with two different engine fixes behind them (D-080):
#:   other_player_keep   "won't trade one of my players"   → a give-side
#:                       keep-list signal; the package builder should stop
#:                       sourcing that player OUT of this user's roster.
#:   other_player_avoid  "don't want one of their players" → a receive-side
#:                       avoid-list signal; the candidate generator should
#:                       stop offering that player TO this user.
#: Collapsing them would force reading free text to route the fix, which is
#: the exact failure that made "Neither" a black box in the first place.
#:
#: `other_text` keeps its meaning and its rows: free text under "Neither".
#: Its POPULATION changed on 2026-08-19 — before, it was every Neither
#: answer; after, it is the Neither answers the two player codes did not
#: absorb. Cohort any before/after comparison on that date.
PASS_REASON_LAYER2: dict[str, tuple[str, ...]] = {
    "value": ("value_giving", "value_getting", "value_other"),
    "fit":   ("fit_outlook", "fit_new_weakness", "fit_duplicate", "fit_other"),
    "other": ("other_player_keep", "other_player_avoid", "other_text"),
}

#: The layer-2 code → layer-1 code inverse, so a layer-2 write that arrives
#: without (or before) its layer-1 sibling can still name its own reason
#: instead of storing a half row.
PASS_REASON_PARENT: dict[str, str] = {
    detail: parent
    for parent, details in PASS_REASON_LAYER2.items()
    for detail in details
}

#: Free text is capped at storage time. Same bound as the bad-trade flag's
#: `reason` field, for the same reason: it is read by a human, not parsed.
PASS_REASON_TEXT_MAX = 500


def upsert_trade_pass_reason(
    impression_id: str,
    user_id: str,
    *,
    league_id: str | None = None,
    trade_id: str | None = None,
    reason: str | None = None,
    detail: str | None = None,
    free_text: str | None = None,
    key_source: str | None = None,
) -> dict:
    """Upsert ONE trade_pass_reasons row; return what the write did.

    The load-bearing contract (SPEC §3): **a later write never loses an
    earlier one.** Only the fields passed non-None are written, so a
    layer-2 tap cannot blank the layer-1 reason, and a free-text send
    cannot blank the detail it upgrades. Nothing here is ever deleted.

    Returns::

        {"created":       bool,   # True ⇒ this call minted the row, i.e.
                                  #        THIS is the tap that passed the card
         "reason":        str|None,   # post-write state
         "detail":        str|None,
         "switched_from": str|None,
         "prior_reason":  str|None,   # pre-write state, for the caller's event
         "prior_detail":  str|None,
         "elo_signal_at": str|None}

    `switched_from` is derived HERE, from the stored row — never taken from
    the client — so it cannot disagree with the row it describes. It is
    (re)set only when an incoming `reason` differs from the stored one, and
    always names the most recent prior answer.
    """
    now = _now()
    with engine.begin() as conn:
        prior = conn.execute(
            select(trade_pass_reasons_table).where(
                trade_pass_reasons_table.c.impression_id == impression_id
            )
        ).first()

        if prior is None:
            row_reason = reason or (PASS_REASON_PARENT.get(detail or "") or None)
            conn.execute(insert(trade_pass_reasons_table).values(
                impression_id = impression_id,
                user_id       = user_id,
                league_id     = league_id,
                trade_id      = trade_id,
                key_source    = key_source,
                reason        = row_reason,
                detail        = detail,
                free_text     = free_text,
                switched_from = None,
                elo_signal_at = None,
                created_at    = now,
                updated_at    = now,
            ))
            return {
                "created": True, "reason": row_reason, "detail": detail,
                "switched_from": None, "prior_reason": None,
                "prior_detail": None, "elo_signal_at": None,
                "key_source": key_source,
            }

        p = dict(prior._mapping)
        values: dict = {"updated_at": now}
        if reason and reason != p.get("reason"):
            # A different tile. Record where we came from; the stored detail
            # is DELIBERATELY kept (SPEC §3: a refinement, not a reset).
            values["switched_from"] = p.get("reason")
            values["reason"] = reason
        elif reason and not p.get("reason"):
            values["reason"] = reason
        if detail is not None:
            values["detail"] = detail
            # A layer-2 code implies its parent — adopt it when the row has
            # no reason yet (writes that arrived out of order).
            if not p.get("reason") and "reason" not in values:
                values["reason"] = PASS_REASON_PARENT.get(detail)
        if free_text is not None:
            values["free_text"] = free_text
        if league_id and not p.get("league_id"):
            values["league_id"] = league_id
        if trade_id and not p.get("trade_id"):
            values["trade_id"] = trade_id

        conn.execute(
            update(trade_pass_reasons_table)
            .where(trade_pass_reasons_table.c.impression_id == impression_id)
            .values(**values)
        )
        return {
            "created": False,
            "reason":        values.get("reason", p.get("reason")),
            "detail":        values.get("detail", p.get("detail")),
            "switched_from": values.get("switched_from", p.get("switched_from")),
            "prior_reason":  p.get("reason"),
            "prior_detail":  p.get("detail"),
            "elo_signal_at": p.get("elo_signal_at"),
            # Never rewritten: the key a row was minted under is a fact about
            # the row, not a field a later tap gets to revise.
            "key_source":    p.get("key_source"),
        }


def claim_trade_pass_elo(impression_id: str) -> bool:
    """Claim the ONE Elo write this passed card is allowed (SPEC §4).

    True exactly once per impression: the conditional UPDATE succeeds only
    while `elo_signal_at` is NULL, so re-taps, client retries and a
    layer-1-then-layer-2 sequence can never double-count one pass into the
    ranking math. Callers write Elo only when this returns True.
    """
    with engine.begin() as conn:
        res = conn.execute(
            update(trade_pass_reasons_table)
            .where(and_(
                trade_pass_reasons_table.c.impression_id == impression_id,
                trade_pass_reasons_table.c.elo_signal_at.is_(None),
            ))
            .values(elo_signal_at=_now())
        )
    return bool(res.rowcount)


def load_trade_pass_reason(impression_id: str) -> dict | None:
    """The single row for one passed card, or None. Operator/test read."""
    with engine.connect() as conn:
        row = conn.execute(
            select(trade_pass_reasons_table).where(
                trade_pass_reasons_table.c.impression_id == impression_id
            )
        ).first()
    return dict(row._mapping) if row else None


# ── suggestion.telemetry — thin storage helpers ─────────────────────────────
# Matching/scoring logic lives in backend/suggestion_telemetry.py; these are
# the writes/reads only (the save_deck_impressions contract).

def save_deck_candidate_set(row: dict) -> None:
    """One pre-built deck_candidate_sets row per job (flag on). Caller wraps
    in try/except — telemetry must never break trade generation."""
    with engine.begin() as conn:
        conn.execute(insert(deck_candidate_sets_table).values(**row))


def save_bakeoff_run(row: dict) -> None:
    """trade.bakeoff — ONE pre-built bakeoff_runs row per job (flag on).
    Caller wraps in try/except: bake-off bookkeeping never fails a trade job."""
    with engine.begin() as conn:
        conn.execute(insert(bakeoff_runs_table).values(**row))


def load_unlinked_league_trades(league_id: str) -> list[dict]:
    """Captured sleeper_trades rows for this league with no
    suggestion_trade_links row yet — the matcher's idempotent work queue."""
    with engine.connect() as conn:
        linked = select(suggestion_trade_links_table.c.transaction_id).where(
            suggestion_trade_links_table.c.league_id == league_id
        )
        rows = conn.execute(
            select(sleeper_trades_table).where(
                and_(
                    sleeper_trades_table.c.league_id == league_id,
                    sleeper_trades_table.c.transaction_id.notin_(linked),
                )
            )
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def load_impressions_for_matching(
    league_id: str, since_iso: str, until_iso: str
) -> list[dict]:
    """Telemetry-era impressions (assets_json present) in the lookback
    window, shaped for suggestion_telemetry._score_impression:
    [{impression_id, user_id, league_id, partner_user_id, assets, is_ghost,
    served_at}]. Pre-telemetry rows carry no assets_json and are honestly
    unmatchable — they are excluded here, not fuzzed around."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                deck_impressions_table.c.impression_id,
                deck_impressions_table.c.user_id,
                deck_impressions_table.c.league_id,
                deck_impressions_table.c.features_json,
                deck_impressions_table.c.assets_json,
                deck_impressions_table.c.is_ghost,
                deck_impressions_table.c.served_at,
            ).where(
                and_(
                    deck_impressions_table.c.league_id == league_id,
                    deck_impressions_table.c.assets_json.isnot(None),
                    deck_impressions_table.c.served_at >= since_iso,
                    deck_impressions_table.c.served_at <= until_iso,
                )
            )
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            assets = json.loads(r.assets_json) if r.assets_json else {}
        except (TypeError, ValueError):
            assets = {}
        partner = None
        try:
            partner = (json.loads(r.features_json) or {}).get("partner_user_id")
        except (TypeError, ValueError):
            partner = None
        out.append({
            "impression_id":   r.impression_id,
            "user_id":         r.user_id,
            "league_id":       r.league_id,
            "partner_user_id": partner,
            "assets":          assets,
            "is_ghost":        r.is_ghost,
            "served_at":       r.served_at,
        })
    return out


def save_suggestion_trade_links(rows: list[dict]) -> int:
    """Append suggestion_trade_links rows, idempotent on transaction_id
    (select-then-insert, the record_sleeper_trades pattern). Returns the
    number of NEW rows inserted."""
    if not rows:
        return 0
    txids = [r["transaction_id"] for r in rows]
    with engine.begin() as conn:
        existing = {
            r.transaction_id
            for r in conn.execute(
                select(suggestion_trade_links_table.c.transaction_id)
                .where(suggestion_trade_links_table.c.transaction_id.in_(txids))
            ).fetchall()
        }
        new_rows = [r for r in rows if r["transaction_id"] not in existing]
        if new_rows:
            conn.execute(insert(suggestion_trade_links_table), new_rows)
    return len(new_rows)


def suggestion_ratio_by_league(league_id: str | None = None) -> list[dict]:
    """The always-on endorsement dashboard: per league, executed trades
    examined, how many matched a rendered suggestion (was_recommended), the
    ratio, and how many matched a withheld ghost (the incrementality read)."""
    q = select(
        suggestion_trade_links_table.c.league_id,
        func.count(suggestion_trade_links_table.c.id).label("executed"),
        func.sum(suggestion_trade_links_table.c.was_recommended).label("recommended"),
        func.count(suggestion_trade_links_table.c.ghost_impression_id).label("ghost_matches"),
    ).group_by(suggestion_trade_links_table.c.league_id)
    if league_id:
        q = q.where(suggestion_trade_links_table.c.league_id == league_id)
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
    out = []
    for r in rows:
        executed = int(r.executed or 0)
        recommended = int(r.recommended or 0)
        out.append({
            "league_id":     r.league_id,
            "executed":      executed,
            "recommended":   recommended,
            "ratio":         round(recommended / executed, 4) if executed else None,
            "ghost_matches": int(r.ghost_matches or 0),
        })
    return out


def load_board_state(
    user_id: str,
    league_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> tuple[int, str | None]:
    """F1 (deck.signal_v2) — board-state-at-serve, one query.

    Returns (ranked_player_count, last_board_update_at) from the user's
    member_rankings snapshot for this league+format (legacy NULL-format rows
    count toward the default format, mirroring load_swipe_decisions). Feeds
    the frozen features_json: a deck generated right after a ranking session
    is built on fresher values than one from a stale board.
    """
    with engine.connect() as conn:
        q = select(
            func.count(member_rankings_table.c.id),
            func.max(member_rankings_table.c.updated_at),
        ).where(
            and_(
                member_rankings_table.c.user_id   == user_id,
                member_rankings_table.c.league_id == league_id,
            )
        )
        if scoring_format == DEFAULT_SCORING:
            q = q.where(
                (member_rankings_table.c.scoring_format == scoring_format) |
                (member_rankings_table.c.scoring_format.is_(None))
            )
        else:
            q = q.where(member_rankings_table.c.scoring_format == scoring_format)
        row = conn.execute(q).first()
    return (int(row[0] or 0), row[1]) if row else (0, None)


def load_deck_serve_history(
    user_id: str,
    league_id: str,
) -> tuple[bool, str | None]:
    """F9 (deck.first_session) — has this user+league ever been served a
    deck, and when was the newest F1-spine deck served?

    Returns (has_prior_deck, last_deck_served_at):
      has_prior_deck      — True when ANY deck_impressions row (F1 spine) OR
                            any legacy trade_impressions row exists. The
                            legacy check protects pre-F1 users: their decks
                            predate the spine, and F9's first-deck shaping
                            must never fire for them (existing-user no-op
                            contract).
      last_deck_served_at — MAX(deck_impressions.served_at); None when the
                            F1 spine has no rows for this user+league (the
                            board_refresh header is then omitted — there is
                            no "previous deck" timestamp to compare against).

    Two cheap indexed lookups (ix_deck_impressions_user_league /
    ix_trade_impressions_user_league); the legacy EXISTS only runs when the
    spine is empty.
    """
    with engine.connect() as conn:
        last = conn.execute(
            select(func.max(deck_impressions_table.c.served_at)).where(and_(
                deck_impressions_table.c.user_id   == user_id,
                deck_impressions_table.c.league_id == league_id,
            ))
        ).scalar()
        if last is not None:
            return True, last
        legacy = conn.execute(
            select(trade_impressions_table.c.id).where(and_(
                trade_impressions_table.c.user_id   == user_id,
                trade_impressions_table.c.league_id == league_id,
            )).limit(1)
        ).first()
        return legacy is not None, None


def load_trade_decision_shape_counts(
    user_id: str,
    league_id: str,
    since_days: int | None = None,
) -> dict[str, tuple[int, int]]:
    """
    Read-only — per package-shape like/pass counts for one user in one league.

    Shape is f"{len(give)}x{len(receive)}" ('1x1', '2x1', …), derived purely
    from the JSON array lengths on each trade_decisions row — the only card
    feature both decisions and live cards can compute without a fragile join
    to trade_impressions. Feeds the A5 Thompson-sampling Beta posteriors in
    server._order_deck.

    Returns {shape: (likes, passes)}. Rows with undecodable JSON or a
    decision other than like/pass are skipped.
    """
    with engine.connect() as conn:
        q = select(
            trade_decisions_table.c.give_player_ids,
            trade_decisions_table.c.receive_player_ids,
            trade_decisions_table.c.decision,
        ).where(
            and_(
                trade_decisions_table.c.user_id   == user_id,
                trade_decisions_table.c.league_id == league_id,
            )
        )
        if since_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
            q = q.where(trade_decisions_table.c.created_at >= cutoff)
        rows = conn.execute(q).fetchall()

    counts: dict[str, tuple[int, int]] = {}
    for r in rows:
        try:
            give = json.loads(r.give_player_ids)
            recv = json.loads(r.receive_player_ids)
        except (json.JSONDecodeError, TypeError):
            continue
        if r.decision not in ("like", "pass"):
            continue
        shape = f"{len(give)}x{len(recv)}"
        likes, passes = counts.get(shape, (0, 0))
        if r.decision == "like":
            likes += 1
        else:
            passes += 1
        counts[shape] = (likes, passes)
    return counts


def load_deck_arm_events(user_id: str, league_id: str) -> list[tuple]:
    """F2 (deck.thompson_v2) — viewed-gated bandit events for one user+league.

    Read-only. Returns [(archetype|None, shape_bucket, action, acted_at), …]
    for every like/pass deck_outcomes row whose impression ALSO has a
    `viewed` outcome (cascade rule: a card served but never fronted must
    update nothing, so its like/pass rows — which can't legitimately exist
    without a view, but might via late/duplicated labels — are excluded at
    the source). Decay/aggregation is the caller's job (server-side, lazy):
    this stays a dumb event read so late `viewed` labels self-heal on the
    next read with no stored state to reconcile.
    """
    viewed_alias = deck_outcomes_table.alias("viewed_evt")
    has_viewed = (
        select(viewed_alias.c.id)
        .where(and_(
            viewed_alias.c.impression_id == deck_outcomes_table.c.impression_id,
            viewed_alias.c.action == "viewed",
        ))
        .exists()
    )
    q = (
        select(
            deck_impressions_table.c.archetype,
            deck_impressions_table.c.shape_bucket,
            deck_outcomes_table.c.action,
            deck_outcomes_table.c.acted_at,
        )
        .select_from(deck_outcomes_table.join(
            deck_impressions_table,
            deck_impressions_table.c.impression_id
            == deck_outcomes_table.c.impression_id,
        ))
        .where(and_(
            deck_impressions_table.c.user_id   == user_id,
            deck_impressions_table.c.league_id == league_id,
            deck_outcomes_table.c.action.in_(("like", "pass")),
            has_viewed,
        ))
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
    return [(r.archetype, r.shape_bucket, r.action, r.acted_at) for r in rows]


def load_legacy_shape_counts(
    user_id: str,
    league_id: str,
) -> dict[str, tuple[int, int, str]]:
    """F2 (deck.thompson_v2) — FROZEN pre-impression-spine shape counts.

    The legacy/F1 seam: trade_decisions rows created BEFORE this user+
    league's first deck_impressions row (MIN(served_at)) predate the
    impression spine and can never be viewed-gated — they form the frozen
    starting state of the v2 posteriors. Rows at/after the seam only ever
    count through the viewed-gated deck_outcomes path (load_deck_arm_events),
    so nothing is double counted; the legacy set stops growing the moment
    the first impression lands. No impressions yet ⇒ every decision is
    legacy.

    Returns {shape: (likes, passes, last_created_at)} — last_created_at is
    the newest legacy decision per shape, the `last_updated` the caller's
    lazy γ-decay runs from. Same shape derivation and skip rules as
    load_trade_decision_shape_counts.
    """
    with engine.connect() as conn:
        seam = conn.execute(
            select(func.min(deck_impressions_table.c.served_at)).where(and_(
                deck_impressions_table.c.user_id   == user_id,
                deck_impressions_table.c.league_id == league_id,
            ))
        ).scalar()
        q = select(
            trade_decisions_table.c.give_player_ids,
            trade_decisions_table.c.receive_player_ids,
            trade_decisions_table.c.decision,
            trade_decisions_table.c.created_at,
        ).where(
            and_(
                trade_decisions_table.c.user_id   == user_id,
                trade_decisions_table.c.league_id == league_id,
            )
        )
        if seam is not None:
            q = q.where(trade_decisions_table.c.created_at < seam)
        rows = conn.execute(q).fetchall()

    counts: dict[str, tuple[int, int, str]] = {}
    for r in rows:
        try:
            give = json.loads(r.give_player_ids)
            recv = json.loads(r.receive_player_ids)
        except (json.JSONDecodeError, TypeError):
            continue
        if r.decision not in ("like", "pass"):
            continue
        shape = f"{len(give)}x{len(recv)}"
        likes, passes, last_at = counts.get(shape, (0, 0, ""))
        if r.decision == "like":
            likes += 1
        else:
            passes += 1
        last_at = max(last_at, r.created_at or "")
        counts[shape] = (likes, passes, last_at)
    return counts


def load_global_like_rate(days: int = 30) -> tuple[int, int]:
    """F2 (deck.thompson_v2) — trailing-window GLOBAL like/pass volume.

    Across ALL users and leagues (the pessimistic-prior base rate p̂ is a
    product-wide quantity — per-user rates are what the posteriors learn).
    Returns (likes, total) so the caller can apply its own minimum-sample
    rule before trusting the rate.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = (
        select(trade_decisions_table.c.decision, func.count())
        .where(and_(
            trade_decisions_table.c.decision.in_(("like", "pass")),
            trade_decisions_table.c.created_at >= cutoff,
        ))
        .group_by(trade_decisions_table.c.decision)
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
    by_decision = {r[0]: int(r[1]) for r in rows}
    likes = by_decision.get("like", 0)
    return likes, likes + by_decision.get("pass", 0)


# ---------------------------------------------------------------------------
# F3 (flag deck.fatigue) — fatigue event reads + decline-suppression state
# ---------------------------------------------------------------------------

def load_deck_fatigue_events(
    user_id: str,
    league_id: str,
    since_iso: str,
) -> list[tuple]:
    """F3 (deck.fatigue) — raw viewed/pass events for the fatigue multiplier.

    Read-only. Returns [(trade_hash, centerpiece_id, archetype, shape_bucket,
    deck_job_id, action, acted_at), …] for every `viewed` or `pass`
    deck_outcomes row on this user+league's impressions with
    acted_at >= since_iso (the caller passes max(lookback cutoff, fatigue
    reset marker)). Aggregation (imp counts, last-seen ages, per-job session
    pass counts) is the caller's job — dumb event read, same derive-on-read
    pattern as load_deck_arm_events.
    """
    q = (
        select(
            deck_impressions_table.c.trade_hash,
            deck_impressions_table.c.centerpiece_id,
            deck_impressions_table.c.archetype,
            deck_impressions_table.c.shape_bucket,
            deck_impressions_table.c.deck_job_id,
            deck_outcomes_table.c.action,
            deck_outcomes_table.c.acted_at,
        )
        .select_from(deck_outcomes_table.join(
            deck_impressions_table,
            deck_impressions_table.c.impression_id
            == deck_outcomes_table.c.impression_id,
        ))
        .where(and_(
            deck_impressions_table.c.user_id   == user_id,
            deck_impressions_table.c.league_id == league_id,
            deck_outcomes_table.c.action.in_(("viewed", "pass")),
            deck_outcomes_table.c.acted_at >= since_iso,
        ))
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
    return [(r.trade_hash, r.centerpiece_id, r.archetype, r.shape_bucket,
             r.deck_job_id, r.action, r.acted_at) for r in rows]


def save_deck_suppression(
    user_id: str,
    league_id: str,
    centerpiece_id: str,
    shape_bucket: str,
    package_value: float | None,
    declined_at: str,
    expires_at: str,
) -> None:
    """F3 — record a decline/proposal-kill suppression window.

    Re-declaring a concept that already has a LIVE (unlifted, unexpired) row
    for the same (centerpiece, shape) refreshes that row's window and clears
    any retest state instead of inserting a duplicate — one row per live
    concept, so the one-retest-per-window rule can't be multiplied.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(deck_suppressions_table.c.id).where(and_(
                deck_suppressions_table.c.user_id        == user_id,
                deck_suppressions_table.c.league_id      == league_id,
                deck_suppressions_table.c.centerpiece_id == centerpiece_id,
                deck_suppressions_table.c.shape_bucket   == shape_bucket,
                deck_suppressions_table.c.lifted_at.is_(None),
                deck_suppressions_table.c.expires_at > declined_at,
            )).limit(1)
        ).scalar()
        if existing is not None:
            conn.execute(
                update(deck_suppressions_table)
                .where(deck_suppressions_table.c.id == existing)
                .values(declined_at=declined_at, expires_at=expires_at,
                        package_value=package_value,
                        retested_at=None, retest_trade_hash=None)
            )
            return
        conn.execute(insert(deck_suppressions_table).values(
            user_id        = user_id,
            league_id      = league_id,
            centerpiece_id = centerpiece_id,
            shape_bucket   = shape_bucket,
            package_value  = package_value,
            declined_at    = declined_at,
            expires_at     = expires_at,
            created_at     = _now(),
        ))


def load_deck_suppressions(user_id: str, league_id: str, limit: int = 200) -> list[dict]:
    """F3 — every non-lifted suppression row for one user+league (newest
    declines first, bounded). Expired rows are included: an expired row that
    was never retested still owes its ONE retest card, and a retested row may
    need the lazy re-suppress check."""
    q = (
        select(deck_suppressions_table)
        .where(and_(
            deck_suppressions_table.c.user_id   == user_id,
            deck_suppressions_table.c.league_id == league_id,
            deck_suppressions_table.c.lifted_at.is_(None),
        ))
        .order_by(deck_suppressions_table.c.declined_at.desc())
        .limit(limit)
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


def mark_deck_suppression_retested(row_id: int, trade_hash: str, at_iso: str) -> None:
    """F3 — stamp the ONE post-window retest card onto its suppression row."""
    with engine.begin() as conn:
        conn.execute(
            update(deck_suppressions_table)
            .where(deck_suppressions_table.c.id == row_id)
            .values(retested_at=at_iso, retest_trade_hash=trade_hash)
        )


def resuppress_deck_suppression(row_id: int, declined_at: str, expires_at: str) -> None:
    """F3 — the retest card was passed: re-arm the row for a fresh window
    (clearing retest state so the NEXT window grants exactly one retest again)."""
    with engine.begin() as conn:
        conn.execute(
            update(deck_suppressions_table)
            .where(deck_suppressions_table.c.id == row_id)
            .values(declined_at=declined_at, expires_at=expires_at,
                    retested_at=None, retest_trade_hash=None)
        )


def lift_latest_deck_suppression(user_id: str, league_id: str) -> int:
    """F3 — the deck-note "Undo": permanently lift the NEWEST non-lifted
    suppression (by declined_at). Returns rows lifted (0 or 1)."""
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        row_id = conn.execute(
            select(deck_suppressions_table.c.id)
            .where(and_(
                deck_suppressions_table.c.user_id   == user_id,
                deck_suppressions_table.c.league_id == league_id,
                deck_suppressions_table.c.lifted_at.is_(None),
            ))
            .order_by(deck_suppressions_table.c.declined_at.desc())
            .limit(1)
        ).scalar()
        if row_id is None:
            return 0
        conn.execute(
            update(deck_suppressions_table)
            .where(deck_suppressions_table.c.id == row_id)
            .values(lifted_at=now)
        )
        return 1


def load_deck_pass_after(
    user_id: str,
    league_id: str,
    trade_hash: str,
    after_iso: str,
) -> str | None:
    """F3 — earliest `pass` outcome on any of this user+league's impressions
    of `trade_hash` acted after `after_iso` (the lazy retest-failed check).
    Returns the acted_at ISO string, or None when the retest wasn't passed."""
    q = (
        select(func.min(deck_outcomes_table.c.acted_at))
        .select_from(deck_outcomes_table.join(
            deck_impressions_table,
            deck_impressions_table.c.impression_id
            == deck_outcomes_table.c.impression_id,
        ))
        .where(and_(
            deck_impressions_table.c.user_id    == user_id,
            deck_impressions_table.c.league_id  == league_id,
            deck_impressions_table.c.trade_hash == trade_hash,
            deck_outcomes_table.c.action == "pass",
            deck_outcomes_table.c.acted_at > after_iso,
        ))
    )
    with engine.connect() as conn:
        return conn.execute(q).scalar()


def set_deck_fatigue_reset(user_id: str, league_id: str) -> str:
    """F3 — "Refresh my deck": stamp the soft-fatigue reset marker to now.
    Fatigue reads ignore events before it; decline suppressions unaffected.
    Delete+insert (one txn) keeps the upsert portable across dialects."""
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(delete(deck_fatigue_resets_table).where(and_(
            deck_fatigue_resets_table.c.user_id   == user_id,
            deck_fatigue_resets_table.c.league_id == league_id,
        )))
        conn.execute(insert(deck_fatigue_resets_table).values(
            user_id=user_id, league_id=league_id, reset_at=now,
        ))
    return now


def load_deck_fatigue_reset(user_id: str, league_id: str) -> str | None:
    """F3 — the user's soft-fatigue reset marker (ISO), or None."""
    with engine.connect() as conn:
        return conn.execute(
            select(deck_fatigue_resets_table.c.reset_at).where(and_(
                deck_fatigue_resets_table.c.user_id   == user_id,
                deck_fatigue_resets_table.c.league_id == league_id,
            ))
        ).scalar()


# ---------------------------------------------------------------------------
# F5 (flag deck.taste_vectors) — taste-vector storage (thin reads/writes;
# all math lives in backend/taste_service.py)
# ---------------------------------------------------------------------------

def load_deck_impression(impression_id: str) -> dict | None:
    """F5 — one impression row's owner + frozen features, for the
    synchronous taste update riding an outcome write. Read-only; None for
    an unknown id (late/junk labels update nothing)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(
                deck_impressions_table.c.user_id,
                deck_impressions_table.c.league_id,
                deck_impressions_table.c.features_json,
                deck_impressions_table.c.served_at,
            ).where(deck_impressions_table.c.impression_id == impression_id)
        ).first()
    if row is None:
        return None
    return {"user_id": row.user_id, "league_id": row.league_id,
            "features_json": row.features_json, "served_at": row.served_at}


def load_user_taste(user_id: str) -> list[dict]:
    """F5 — every stored taste row for one user (prior rows included).
    Decay/GC decisions are the caller's job (derive-on-read pattern)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                user_taste_table.c.attr,
                user_taste_table.c.w_short,
                user_taste_table.c.w_long,
                user_taste_table.c.updated_at,
            ).where(user_taste_table.c.user_id == user_id)
        ).fetchall()
    return [{"attr": r.attr, "w_short": float(r.w_short),
             "w_long": float(r.w_long), "updated_at": r.updated_at}
            for r in rows]


def replace_user_taste_rows(
    user_id: str,
    upserts: dict,
    deletes: list | tuple = (),
) -> None:
    """F5 — one-transaction upsert+GC for a set of attrs.

    upserts: {attr: (w_short, w_long, updated_at_iso)} — row replaced.
    deletes: attrs whose decayed weights fell below ε — row removed.
    Delete+insert (one txn) keeps the upsert portable across dialects
    (same idiom as set_deck_fatigue_reset)."""
    attrs = list(upserts.keys()) + [a for a in deletes if a not in upserts]
    if not attrs:
        return
    with engine.begin() as conn:
        conn.execute(delete(user_taste_table).where(and_(
            user_taste_table.c.user_id == user_id,
            user_taste_table.c.attr.in_(attrs),
        )))
        if upserts:
            conn.execute(insert(user_taste_table), [
                {"user_id": user_id, "attr": a, "w_short": float(ws),
                 "w_long": float(wl), "updated_at": ts}
                for a, (ws, wl, ts) in upserts.items()
            ])


def replace_user_taste_prior(user_id: str, prior: dict, now_iso: str) -> None:
    """F5 — rewrite the user's board-derived prior wholesale (PRD amendment):
    every existing "prior:"-prefixed row is dropped, then one row per prior
    attr is inserted with the prior mass in w_long (w_short stays 0 — the
    prior is a long-interest warm start, not a session signal). An empty
    prior clears the block (a board that stopped diverging stops priming)."""
    with engine.begin() as conn:
        conn.execute(delete(user_taste_table).where(and_(
            user_taste_table.c.user_id == user_id,
            user_taste_table.c.attr.like("prior:%"),
        )))
        if prior:
            conn.execute(insert(user_taste_table), [
                {"user_id": user_id, "attr": f"prior:{a}", "w_short": 0.0,
                 "w_long": float(v), "updated_at": now_iso}
                for a, v in prior.items()
            ])


# ---------------------------------------------------------------------------
# F7 (flag deck.exploration) — archetype-audition storage + engagement counts
# (state machine lives in server._audition_statuses; these stay thin)
# ---------------------------------------------------------------------------

def load_archetype_auditions() -> dict[str, dict]:
    """F7 — every audition row, keyed by archetype. Read-only; the lazy
    draw-time evaluation in server decides transitions."""
    with engine.connect() as conn:
        rows = conn.execute(select(
            archetype_auditions_table.c.archetype,
            archetype_auditions_table.c.status,
            archetype_auditions_table.c.viewed_impressions,
            archetype_auditions_table.c.likes,
            archetype_auditions_table.c.entered_at,
            archetype_auditions_table.c.retired_at,
        )).fetchall()
    return {r.archetype: {
        "archetype":          r.archetype,
        "status":             r.status,
        "viewed_impressions": int(r.viewed_impressions or 0),
        "likes":              int(r.likes or 0),
        "entered_at":         r.entered_at,
        "retired_at":         r.retired_at,
    } for r in rows}


def upsert_archetype_audition(
    archetype: str,
    *,
    status: str,
    viewed_impressions: int,
    likes: int,
    entered_at: str,
    retired_at: str | None,
) -> None:
    """F7 — replace one archetype's audition row wholesale. Delete+insert in
    one txn keeps the upsert portable across dialects (same idiom as
    set_deck_fatigue_reset / replace_user_taste_rows)."""
    with engine.begin() as conn:
        conn.execute(delete(archetype_auditions_table).where(
            archetype_auditions_table.c.archetype == archetype))
        conn.execute(insert(archetype_auditions_table).values(
            archetype          = archetype,
            status             = status,
            viewed_impressions = int(viewed_impressions),
            likes              = int(likes),
            entered_at         = entered_at,
            retired_at         = retired_at,
        ))


def count_archetype_engagement(
    archetype: str,
    since_iso: str | None = None,
) -> tuple[int, int]:
    """F7 — (viewed, likes) for one archetype across ALL users/leagues (the
    audition pool is follower-blind and global by design).

    viewed = distinct deck_impressions rows carrying this archetype label
    with a `viewed` outcome (served ≠ viewed — F1's cascade rule); likes =
    the subset of those that ALSO have a `like` outcome, so the like-rate
    numerator and denominator share the same viewed-gated base. since_iso
    scopes both to impressions served in the current audition window."""
    viewed_alias = deck_outcomes_table.alias("f7_viewed")
    like_alias   = deck_outcomes_table.alias("f7_like")
    has_viewed = (
        select(viewed_alias.c.id)
        .where(and_(
            viewed_alias.c.impression_id == deck_impressions_table.c.impression_id,
            viewed_alias.c.action == "viewed",
        )).exists()
    )
    has_like = (
        select(like_alias.c.id)
        .where(and_(
            like_alias.c.impression_id == deck_impressions_table.c.impression_id,
            like_alias.c.action == "like",
        )).exists()
    )
    conds = [deck_impressions_table.c.archetype == archetype, has_viewed]
    if since_iso:
        conds.append(deck_impressions_table.c.served_at >= since_iso)
    q_viewed = (select(func.count())
                .select_from(deck_impressions_table).where(and_(*conds)))
    q_likes = (select(func.count())
               .select_from(deck_impressions_table)
               .where(and_(*conds, has_like)))
    with engine.connect() as conn:
        viewed = int(conn.execute(q_viewed).scalar() or 0)
        likes  = int(conn.execute(q_likes).scalar() or 0)
    return viewed, likes


def load_recent_impression_target_user_counts(
    league_id: str,
    exclude_user_id: str,
    days: int = 7,
) -> dict[str, int]:
    """
    Read-only — for each player id appearing as a RECEIVE asset in this
    league's trade_impressions within the last `days` days, the number of
    DISTINCT users (excluding `exclude_user_id`) whose decks featured him.

    Feeds the A6 diversification penalty in server._order_deck: a player can
    only be traded once, so saturating every member's deck with him
    mathematically caps total possible matches.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                trade_impressions_table.c.user_id,
                trade_impressions_table.c.receive_player_ids,
            ).where(
                and_(
                    trade_impressions_table.c.league_id == league_id,
                    trade_impressions_table.c.user_id   != exclude_user_id,
                    trade_impressions_table.c.shown_at  >= cutoff,
                )
            )
        ).fetchall()

    users_by_pid: dict[str, set] = {}
    for r in rows:
        try:
            recv = json.loads(r.receive_player_ids)
        except (json.JSONDecodeError, TypeError):
            continue
        for pid in recv:
            users_by_pid.setdefault(pid, set()).add(r.user_id)
    return {pid: len(users) for pid, users in users_by_pid.items()}


def load_engine_telemetry(days: int = 30, league_id: str | None = None) -> dict:
    """
    Read-only — aggregate trade-engine health metrics over the last `days`
    days, optionally scoped to one league. Powers GET /api/admin/engine-metrics.

    Impressions are deduped to unique cards on (user_id, league_id,
    give-set, receive-set), keeping the latest showing — regenerated decks
    re-log the same card. Decisions are joined to cards on that same key
    (the documented labeling join for the acceptance-model training data).
    Volumes are one row per card shown, so aggregation happens in Python
    rather than dialect-specific JSON SQL.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    with engine.connect() as conn:
        imp_q = select(
            trade_impressions_table.c.user_id,
            trade_impressions_table.c.league_id,
            trade_impressions_table.c.give_player_ids,
            trade_impressions_table.c.receive_player_ids,
            trade_impressions_table.c.basis,
            trade_impressions_table.c.likes_you,
            trade_impressions_table.c.position_in_deck,
            trade_impressions_table.c.shown_at,
        ).where(trade_impressions_table.c.shown_at >= cutoff)
        dec_q = select(
            trade_decisions_table.c.user_id,
            trade_decisions_table.c.league_id,
            trade_decisions_table.c.give_player_ids,
            trade_decisions_table.c.receive_player_ids,
            trade_decisions_table.c.decision,
            trade_decisions_table.c.created_at,
        ).where(trade_decisions_table.c.created_at >= cutoff)
        match_q = select(
            trade_matches_table.c.league_id,
            trade_matches_table.c.status,
        ).where(trade_matches_table.c.matched_at >= cutoff)
        if league_id:
            imp_q   = imp_q.where(trade_impressions_table.c.league_id == league_id)
            dec_q   = dec_q.where(trade_decisions_table.c.league_id == league_id)
            match_q = match_q.where(trade_matches_table.c.league_id == league_id)
        imp_rows   = conn.execute(imp_q).fetchall()
        dec_rows   = conn.execute(dec_q).fetchall()
        match_rows = conn.execute(match_q).fetchall()

    def _key(uid, lid, give_json, recv_json):
        try:
            return (uid, lid,
                    frozenset(json.loads(give_json)),
                    frozenset(json.loads(recv_json)))
        except (json.JSONDecodeError, TypeError):
            return None

    # Unique cards, latest showing wins (re-logged decks overwrite).
    cards: dict[tuple, dict] = {}
    for r in imp_rows:
        k = _key(r.user_id, r.league_id, r.give_player_ids, r.receive_player_ids)
        if k is None:
            continue
        prev = cards.get(k)
        if prev is None or (r.shown_at or "") >= prev["shown_at"]:
            try:
                shape = (f"{len(json.loads(r.give_player_ids))}"
                         f"x{len(json.loads(r.receive_player_ids))}")
            except (json.JSONDecodeError, TypeError):
                shape = "?"
            cards[k] = {
                "league_id": r.league_id,
                "basis":     r.basis or "divergence",
                "likes_you": bool(r.likes_you),
                "position":  r.position_in_deck,
                "shown_at":  r.shown_at or "",
                "shape":     shape,
            }

    # Latest decision per card key.
    decisions: dict[tuple, str] = {}
    dec_seen_at: dict[tuple, str] = {}
    legacy_decisions = 0   # decisions with no logged impression (pre-telemetry)
    likes = passes = 0
    for r in dec_rows:
        if r.decision not in ("like", "pass"):
            continue
        if r.decision == "like":
            likes += 1
        else:
            passes += 1
        k = _key(r.user_id, r.league_id, r.give_player_ids, r.receive_player_ids)
        if k is None:
            continue
        if k not in cards:
            legacy_decisions += 1
            continue
        if (r.created_at or "") >= dec_seen_at.get(k, ""):
            decisions[k] = r.decision
            dec_seen_at[k] = r.created_at or ""

    def _rate_bucket():
        return {"shown": 0, "liked": 0, "passed": 0}

    def _finalize(b):
        decided = b["liked"] + b["passed"]
        b["like_rate"] = round(b["liked"] / decided, 3) if decided else None
        return b

    by_basis: dict[str, dict] = {}
    by_likes_you = {"likes_you": _rate_bucket(), "organic": _rate_bucket()}
    by_position = {"top3": _rate_bucket(), "4-10": _rate_bucket(), "11+": _rate_bucket()}
    by_shape: dict[str, dict] = {}
    by_league: dict[str, dict] = {}

    for k, c in cards.items():
        decision = decisions.get(k)
        pos = c["position"]
        pos_bucket = ("top3" if pos is not None and pos < 3
                      else "4-10" if pos is not None and pos < 10
                      else "11+")
        buckets = [
            by_basis.setdefault(c["basis"], _rate_bucket()),
            by_likes_you["likes_you" if c["likes_you"] else "organic"],
            by_position[pos_bucket],
            by_shape.setdefault(c["shape"], _rate_bucket()),
        ]
        league_b = by_league.setdefault(c["league_id"], _rate_bucket())
        buckets.append(league_b)
        for b in buckets:
            b["shown"] += 1
            if decision == "like":
                b["liked"] += 1
            elif decision == "pass":
                b["passed"] += 1

    match_status: dict[str, int] = {}
    for r in match_rows:
        match_status[r.status or "pending"] = match_status.get(r.status or "pending", 0) + 1
    matches_total = sum(match_status.values())

    return {
        "window_days":     days,
        "league_id":       league_id,
        "impressions":     {
            "rows":         len(imp_rows),
            "unique_cards": len(cards),
        },
        "decisions": {
            "likes":  likes,
            "passes": passes,
            "like_rate": round(likes / (likes + passes), 3) if (likes + passes) else None,
            "without_impression": legacy_decisions,
        },
        "by_basis":     {k: _finalize(v) for k, v in sorted(by_basis.items())},
        "by_likes_you": {k: _finalize(v) for k, v in by_likes_you.items()},
        "by_position":  {k: _finalize(v) for k, v in by_position.items()},
        "by_shape":     {k: _finalize(v) for k, v in sorted(by_shape.items())},
        "by_league":    {k: _finalize(v) for k, v in sorted(by_league.items())},
        "matches": {
            "total":     matches_total,
            "by_status": match_status,
            "per_like":  round(matches_total / likes, 3) if likes else None,
        },
    }


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

    Uses a single dialect-aware bulk upsert (INSERT OR REPLACE for SQLite,
    INSERT … ON CONFLICT DO UPDATE for PostgreSQL) to replace the old N+1
    select-then-insert/update loop.
    """
    if not members:
        return

    now = _now()
    rows = [
        {
            "league_id":    league_id,
            "user_id":      str(m.get("user_id", "")),
            "username":     m.get("username", ""),
            "display_name": m.get("display_name") or m.get("username", ""),
            "roster_data":  json.dumps(m.get("player_ids", [])),
            "updated_at":   now,
        }
        for m in members
        if m.get("user_id")
    ]
    if not rows:
        return

    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            # INSERT OR REPLACE honours the uq_league_member constraint and
            # always writes the freshest values (newest-wins).
            conn.execute(text(
                "INSERT OR REPLACE INTO league_members "
                "(league_id, user_id, username, display_name, roster_data, updated_at) "
                "VALUES (:league_id, :user_id, :username, :display_name, :roster_data, :updated_at)"
            ), rows)
        else:
            # PostgreSQL: upsert on the unique constraint using the
            # dialect-specific insert that supports on_conflict_do_update.
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(league_members_table).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_league_member",
                set_={
                    "username":     stmt.excluded.username,
                    "display_name": stmt.excluded.display_name,
                    "roster_data":  stmt.excluded.roster_data,
                    "updated_at":   stmt.excluded.updated_at,
                },
            )
            conn.execute(stmt)


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


def replace_trade_block(league_id: str, entries: list[dict]) -> None:
    """FB-147 — replace the league's Sleeper trade-block snapshot.

    entries: list of dicts with keys player_id, user_id, roster_id,
    flagged_at (ISO or None). Delete + insert in one transaction so readers
    never see a half-synced league (same snapshot semantics as
    member_rankings). An empty list is a valid snapshot — it clears the
    league (everyone took their players off the block).
    """
    now = _now()
    rows = [
        {
            "league_id":  league_id,
            "player_id":  str(e["player_id"]),
            "user_id":    e.get("user_id"),
            "roster_id":  e.get("roster_id"),
            "flagged_at": e.get("flagged_at"),
            "synced_at":  now,
        }
        for e in entries
    ]
    with engine.begin() as conn:
        conn.execute(
            trade_block_table.delete().where(
                trade_block_table.c.league_id == league_id
            )
        )
        if rows:
            conn.execute(trade_block_table.insert(), rows)


def load_trade_block(league_id: str) -> list[dict]:
    """FB-147 — return the league's current trade-block snapshot rows.

    The documented read hook for the trade engine (weighting is owned by
    the trade-logic thread; see docs/feedback/items/147-trade-blocks/status.md).
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(trade_block_table).where(
                trade_block_table.c.league_id == league_id
            )
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def record_sleeper_trades(rows: list[dict]) -> int:
    """Market-data readiness — append captured Sleeper trade transactions.

    Idempotent on transaction_id: rows whose transaction_id is already
    stored are skipped (a completed trade never mutates, so skip — not
    upsert — is correct and keeps the first-captured raw payload).

    Returns the number of NEW rows inserted.
    """
    if not rows:
        return 0
    txids = [r["transaction_id"] for r in rows]
    with engine.begin() as conn:
        existing = {
            r.transaction_id
            for r in conn.execute(
                select(sleeper_trades_table.c.transaction_id)
                .where(sleeper_trades_table.c.transaction_id.in_(txids))
            ).fetchall()
        }
        new_rows = [r for r in rows if r["transaction_id"] not in existing]
        if new_rows:
            conn.execute(sleeper_trades_table.insert(), new_rows)
    return len(new_rows)


def load_sleeper_trades(league_id: str, limit: int = 200) -> list[dict]:
    """Return a league's captured trades, newest first (future read seam
    for League Trade History / observed-market derivation — PRD #43)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(sleeper_trades_table)
            .where(sleeper_trades_table.c.league_id == league_id)
            .order_by(sleeper_trades_table.c.traded_at.desc())
            .limit(limit)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def set_league_scoring(league_id: str, scoring_format: str) -> None:
    """Save the league's default scoring format (shown on the league summary)."""
    if scoring_format not in SCORING_FORMATS:
        raise ValueError(f"Invalid scoring_format: {scoring_format!r}")
    with engine.begin() as conn:
        # One row per league (PK = sleeper_league_id), so this matches the
        # single importer-owner row. See upsert_league for the keying rules.
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == league_id)
            .values(default_scoring=scoring_format)
        )


def set_league_total_rosters(league_id: str, total_rosters: int) -> None:
    """Persist Sleeper's total_rosters for the league (FB #41).

    Written by session_init's background daemon whenever Sleeper league meta
    is fetched. This is the league's TRUE team count — it includes orphaned
    (ownerless) rosters that never make it into league_members, so the
    League tile can't undercount when a manager leaves the league.
    """
    if not isinstance(total_rosters, int) or total_rosters <= 0:
        return
    with engine.begin() as conn:
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == league_id)
            .values(total_rosters=total_rosters)
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
        "matches_mutual":           int,   # mutual matches visible in the user's Matches inbox
        "matches_awaiting":         int,   # user's one-sided likes not yet matured into a match
        "matches_pending":          int,   # DEPRECATED (pre-1.4 clients): status='pending' rows
        "matches_accepted":         int,   # DEPRECATED (pre-1.4 clients): status='accepted' rows
        "total_teams":              int,   # TOTAL teams in the league (incl. caller)
        "leaguemates_total":        int,   # members other than current user
        "leaguemates_joined":       int,   # how many have a users row
        "leaguemates_unlocked_1qb": int,   # how many unlocked 1qb_ppr
        "leaguemates_unlocked_sf":  int,   # how many unlocked sf_tep
    }

    total_teams (FB #41) is Sleeper's total_rosters when we have it (persisted
    by session_init's meta fetch). The old client-side leaguemates_total + 1
    derivation undercounts when a roster is ownerless (departed manager —
    clients drop it from opponent_rosters) and overcounts when league_members
    holds stale rows for managers who left. Falls back to the derived count
    for local leagues / rows that pre-date the total_rosters column.

    Bucketing (feedback #91) mirrors the Matches screen's two segments so the
    League tiles count exactly what the user sees there, and every trade lives
    in exactly one bucket:
      - matches_mutual   = trade_matches rows involving the user (any status),
                           excluding rows the user dismissed — i.e. the
                           "Mutual matches" segment filtered to this league.
      - matches_awaiting = the user's likes with no trade_matches row for the
                           same players — the "Awaiting them" segment filtered
                           to this league (see load_awaiting_trades).
    The legacy matches_pending / matches_accepted split partitioned match rows
    by disposition status and counted dismissed rows, so its numbers disagreed
    with the Matches list; kept only so pre-1.4 builds keep rendering.
    """
    from sqlalchemy import func

    with engine.connect() as conn:
        # League name and default scoring (first row wins)
        league_row = conn.execute(
            select(
                leagues_table.c.name,
                leagues_table.c.default_scoring,
                leagues_table.c.total_rosters,
            )
            .where(leagues_table.c.sleeper_league_id == league_id)
            .limit(1)
        ).fetchone()
        league_name = league_row.name if league_row else ""
        stored_total_rosters = league_row.total_rosters if league_row else None
        default_scoring = (
            league_row.default_scoring
            if league_row and league_row.default_scoring in SCORING_FORMATS
            else DEFAULT_SCORING
        )

        # Mutual matches — every match row involving the user that the user
        # has NOT dismissed, regardless of disposition status. This is the
        # exact set the Matches tab's "Mutual matches" segment renders for
        # this league (load_matches applies the same per-user dismissal
        # filter), so the tile count always equals the visible list.
        _not_dismissed_a = (
            (trade_matches_table.c.user_a_id == user_id) &
            ((trade_matches_table.c.user_a_dismissed.is_(None)) |
             (trade_matches_table.c.user_a_dismissed == 0))
        )
        _not_dismissed_b = (
            (trade_matches_table.c.user_b_id == user_id) &
            ((trade_matches_table.c.user_b_dismissed.is_(None)) |
             (trade_matches_table.c.user_b_dismissed == 0))
        )
        matches_mutual = conn.execute(
            select(func.count()).select_from(trade_matches_table).where(
                (trade_matches_table.c.league_id == league_id) &
                (_not_dismissed_a | _not_dismissed_b)
            )
        ).scalar() or 0

        # Legacy status-split counts (deprecated — pre-1.4 clients only)
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

    # Awaiting-them — one-sided likes that have not matured into a match.
    # Reuses the same query the Matches tab's "Awaiting them" segment is
    # built on (load_awaiting_trades), filtered to this league, so the two
    # surfaces can never disagree. Outside the connection block: it opens
    # its own connection.
    matches_awaiting = sum(
        1 for a in load_awaiting_trades(user_id) if a["league_id"] == league_id
    )

    with engine.connect() as conn:
        # Leaguemate IDs excluding current user
        leaguemate_rows = conn.execute(
            select(league_members_table.c.user_id).where(
                (league_members_table.c.league_id == league_id) &
                (league_members_table.c.user_id != user_id)
            )
        ).fetchall()
        leaguemate_ids = [r.user_id for r in leaguemate_rows]
        leaguemates_total = len(leaguemate_ids)

        # True team count: Sleeper's total_rosters wins; fall back to the
        # derived members-plus-caller count for local leagues / unbackfilled
        # rows (matches the pre-FB-41 client arithmetic).
        total_teams = (
            stored_total_rosters
            if isinstance(stored_total_rosters, int) and stored_total_rosters > 0
            else leaguemates_total + 1
        )

        if leaguemates_total == 0:
            return {
                "league_name":              league_name,
                "default_scoring":          default_scoring,
                "matches_mutual":           matches_mutual,
                "matches_awaiting":         matches_awaiting,
                "matches_pending":          matches_pending,
                "matches_accepted":         matches_accepted,
                "total_teams":              total_teams,
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
        "matches_mutual":           matches_mutual,
        "matches_awaiting":         matches_awaiting,
        "matches_pending":          matches_pending,
        "matches_accepted":         matches_accepted,
        "total_teams":              total_teams,
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
    # Analytics P0 cutover (LLD §6.4): the feed reads the UNION of the frozen
    # legacy table and the live lineage, split on each table's own timestamp
    # column — wrapped_events.created_at < cutover ∪ user_events.occurred_at
    # >= cutover (zero overlap; T-16). A missing cutover key reads as "" which
    # compares below every ISO string → user_events only (fresh DB).
    NARRATIVE_TYPES = {          # legacy wrapped_events names
        "trade_match",
        "trade_accepted",
        "trade_declined",
        "tier_save",
        "league_sync",
    }
    UE_NARRATIVE_TYPES = {       # user_events successors ('league_synced' is
        "trade_match",           # the live server name for 'league_sync';
        "trade_accepted",        # trade_accepted/declined gained real writers
        "trade_declined",        # in user_events — they were writer-less in
        "tier_save",             # wrapped_events)
        "league_synced",
    }
    cutover = get_wrapped_cutover_iso()
    fetch_n = max(limit * 4, 40)

    # Normalized entries: {user_id, event_type (legacy name), payload_raw, ts}
    entries: list[dict] = []
    with engine.connect() as conn:
        legacy_rows = conn.execute(
            select(
                wrapped_events_table.c.user_id,
                wrapped_events_table.c.event_type,
                wrapped_events_table.c.payload_json,
                wrapped_events_table.c.created_at,
            )
            .where(and_(
                wrapped_events_table.c.league_id == league_id,
                wrapped_events_table.c.created_at < cutover,
            ))
            .order_by(wrapped_events_table.c.id.desc())
            .limit(fetch_n)
        ).fetchall()
        for r in legacy_rows:
            if r.event_type in NARRATIVE_TYPES:
                entries.append({"user_id": r.user_id, "event_type": r.event_type,
                                "payload_raw": r.payload_json, "ts": r.created_at})

        ue_rows = conn.execute(
            select(
                user_events_table.c.user_id,
                user_events_table.c.event_type,
                user_events_table.c.props,
                user_events_table.c.occurred_at,
            )
            .where(and_(
                user_events_table.c.league_id == league_id,
                user_events_table.c.occurred_at >= cutover,
                user_events_table.c.event_type.in_(sorted(UE_NARRATIVE_TYPES)),
            ))
            .order_by(user_events_table.c.id.desc())
            .limit(fetch_n)
        ).fetchall()
        for r in ue_rows:
            et = "league_sync" if r.event_type == "league_synced" else r.event_type
            entries.append({"user_id": r.user_id, "event_type": et,
                            "payload_raw": r.props, "ts": r.occurred_at})

        entries.sort(key=lambda e: e["ts"] or "", reverse=True)
        filtered = entries[:limit]
        if not filtered:
            return []

        user_ids = list({e["user_id"] for e in filtered if e["user_id"]})
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
            payload = json.loads(r["payload_raw"]) if r["payload_raw"] else {}
            if not isinstance(payload, dict):
                payload = {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        actor = _handle_name(r["user_id"])
        ago = _ago(r["ts"])
        et = r["event_type"]
        emoji = "•"
        message = ""
        # user_events trade rows carry partner_id (trade_match) rather than
        # other_user_id — alias so both eras render the counterparty.
        other_uid = payload.get("other_user_id") or payload.get("partner_id")

        if et == "trade_accepted":
            emoji = "✅"
            other = _handle_name(other_uid)
            message = f"✅ @{actor} accepted a trade with @{other} ({ago})"
        elif et == "trade_declined":
            emoji = "✖️"
            other = _handle_name(other_uid)
            message = f"✖️ @{actor} declined a trade with @{other} ({ago})"
        elif et == "trade_match":
            emoji = "🤝"
            other = _handle_name(other_uid)
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
            u = user_map.get(r["user_id"] or "", {})
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
                "ts":            r["ts"],
                "emoji":         "🎯",
                "message":       f"🎯 @{actor} unlocked trades in {fmt_lbl} ({ago})",
                "actor_user_id": r["user_id"],
                "event_type":    "unlock",
            })

        out.append({
            "ts":            r["ts"],
            "emoji":         emoji,
            "message":       message,
            "actor_user_id": r["user_id"],
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


def is_linked_platform_league(league_id: str) -> bool:
    """True when this id belongs to a platform-imported league (ESPN / MFL /
    Fleaflicker — a leagues row whose `platform` column was set by the link
    routes).

    Their platform-NATIVE ids are numeric, so the isdigit() "local vs
    Sleeper" split in the /api/sleeper/rosters|league_users proxies would
    misroute them to Sleeper, which 404s (feedback #149/#150 — empty
    trade-away picker + swap sheet on ESPN leagues). Callers use this to
    serve the DB membership snapshot instead.
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.platform).where(
                leagues_table.c.sleeper_league_id == str(league_id)
            )
        ).fetchone()
    return bool(row) and (row.platform or "sleeper") != "sleeper"


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

    # Invalidate community-ELO cache so the next Trends call gets fresh data.
    _COMMUNITY_ELO_CACHE.pop((league_id, scoring_format), None)


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
        "members": [         # per-member detail — ranked_formats (#191/#192)
                             # lists which scoring formats the member has
                             # stored rankings in (legacy NULL rows count as
                             # the default format), so clients can tell
                             # "ranked in the active format" from "ranked in
                             # the other format only" (derivable, R*) from
                             # "never ranked" (NR). has_rankings stays the
                             # format-blind any-format boolean.
            {"user_id": str, "username": str, "has_rankings": bool,
             "ranked_formats": ["sf_tep", ...]}, ...
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
            select(
                member_rankings_table.c.user_id,
                member_rankings_table.c.scoring_format,
            ).distinct().where(
                (member_rankings_table.c.league_id == league_id) &
                (member_rankings_table.c.user_id   != exclude_user_id)
            )
        ).fetchall()

    ranked_ids = {r.user_id for r in ranked_rows}
    formats_by_user: dict = {}
    for r in ranked_rows:
        fmt = r.scoring_format or DEFAULT_SCORING
        formats_by_user.setdefault(r.user_id, set()).add(fmt)
    member_list = [
        {
            "user_id":        m.user_id,
            "username":       m.username or m.display_name or m.user_id,
            "has_rankings":   m.user_id in ranked_ids,
            "ranked_formats": sorted(formats_by_user.get(m.user_id, ())),
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

def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity of two sets — 1.0 when both empty (vacuously equal)."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _all_low_value_players(player_ids: set, max_search_rank: int) -> bool:
    """True iff EVERY player in `player_ids` is a low-consensus-value asset.

    Value proxy: players.search_rank — the only consensus value-ish column in
    the players table (Sleeper's internal rank; LOWER number = MORE valuable;
    adp is rarely populated). A player counts as "low value" when
    search_rank >= max_search_rank, i.e. outside startable territory.
    Missing/NULL search_rank is treated as HIGH value (guard fails) so a
    hyped prospect with no rank can never slip through a fuzzy match.
    """
    if not player_ids:
        return True
    with engine.connect() as conn:
        rows = conn.execute(
            select(players_table.c.player_id, players_table.c.search_rank)
            .where(players_table.c.player_id.in_(list(player_ids)))
        ).fetchall()
    ranks = {r.player_id: r.search_rank for r in rows}
    for pid in player_ids:
        rank = ranks.get(pid)
        if rank is None or rank < max_search_rank:
            return False
    return True


def check_for_match(
    current_user_id: str,
    league_id: str,
    target_user_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
    fuzzy: bool = False,
    fuzzy_tau: float = 0.8,
    fuzzy_guard_rank: int = 120,
) -> bool:
    """
    Check whether target_user_id has already liked a mirrored trade.

    A mirror trade means: target_user gives what current_user receives,
    and target_user receives what current_user gives.

    Uses set comparison so JSON ordering doesn't matter.

    Fuzzy mode (Tier 2 work item 2.3b, flag trade.fuzzy_match — caller passes
    `fuzzy=True`): when no exact mirror exists, a counterparty like also
    counts as a mirror when
        jaccard(their_give, my_receive)    >= fuzzy_tau
        jaccard(their_receive, my_give)    >= fuzzy_tau
    AND every asset in the symmetric differences is a low-consensus-value
    player (players.search_rank >= fuzzy_guard_rank — see
    _all_low_value_players). The guard prevents a similar-but-lopsided pair
    (same package ± a star) from auto-matching. `fuzzy_tau` comes from
    model_config key "fuzzy_match_tau" (default 0.8), resolved by the caller
    so this module stays config-free.

    Returns True if a matching "like" decision exists.
    """
    give_set    = set(give_player_ids)
    receive_set = set(receive_player_ids)

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                trade_decisions_table.c.give_player_ids,
                trade_decisions_table.c.receive_player_ids,
            ).where(
                and_(
                    trade_decisions_table.c.user_id    == target_user_id,
                    trade_decisions_table.c.league_id  == league_id,
                    trade_decisions_table.c.decision   == "like",
                    trade_decisions_table.c.created_at >= cutoff.isoformat(),
                    # #318 — a retracted like can never mature into a match.
                    trade_decisions_table.c.retracted_at.is_(None),
                )
            )
        ).fetchall()

    parsed: list[tuple[set, set]] = []
    for r in rows:
        try:
            their_give    = set(json.loads(r.give_player_ids))
            their_receive = set(json.loads(r.receive_player_ids))
        except (json.JSONDecodeError, TypeError):
            continue
        parsed.append((their_give, their_receive))

    # Exact set-equality mirror — always checked first, behavior unchanged.
    for their_give, their_receive in parsed:
        # Their give == what current user receives, their receive == what current user gives
        if their_give == receive_set and their_receive == give_set:
            return True

    if not fuzzy:
        return False

    # Fuzzy pass — near-mirrors that differ only by low-value pieces.
    for their_give, their_receive in parsed:
        if _jaccard(their_give, receive_set) < fuzzy_tau:
            continue
        if _jaccard(their_receive, give_set) < fuzzy_tau:
            continue
        differing = (their_give ^ receive_set) | (their_receive ^ give_set)
        if _all_low_value_players(differing, fuzzy_guard_rank):
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
                status       = "pending",
            )
        )
        match_id = result.inserted_primary_key[0]

    # Analytics P0 cutover (LLD §6.4): 'trade_match' now lands in user_events
    # (equivalent props to the frozen wrapped_events writer; partner_id keeps
    # its name — the narrative reader aliases it to other_user_id).
    # Non-throwing inside record_event itself.
    record_event(user_a_id, "trade_match", league_id=league_id, source="api",
                 props={"match_id": match_id, "partner_id": user_b_id,
                        "give": user_a_give, "receive": user_a_receive})

    return {
        "id":          match_id,
        "league_id":   league_id,
        "user_a_id":   user_a_id,
        "user_b_id":   user_b_id,
        "user_a_give": user_a_give,
        "user_a_receive": user_a_receive,
        "matched_at":  now,
        "status":      "pending",
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

        # Per-user dismissal: a match the caller archived stays out of THEIR
        # inbox for good (the other party still sees it). getattr-guarded so
        # a pre-migration row (column absent) is simply treated as not
        # dismissed. Only the caller's own flag is consulted.
        if is_a and getattr(r, "user_a_dismissed", None):
            continue
        if is_b and getattr(r, "user_b_dismissed", None):
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


def load_matches_for_exclusion(user_id: str, league_id: str) -> list[dict]:
    """G6 R4 #336 — narrow read feeding the trade-generation exclusion set.

    Returns the user's `pending`/`accepted` trade_matches rows in ONE
    league, keyed from the USER's orientation (user_a_give/receive,
    mirrored when the user is user_b): [{"my_give": [...],
    "my_receive": [...]}]. `declined` rows deliberately do NOT block
    (Q-G6-2: a market-rejected trade regenerating later is defensible —
    "blocked" means currently live in the match pipeline). Windowless by
    design — the #336 bug was the 7-day window on generation dedup. Hits
    the ix_trade_matches_user_{a,b}_league composite indexes.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                trade_matches_table.c.user_a_id,
                trade_matches_table.c.user_a_give,
                trade_matches_table.c.user_a_receive,
            ).where(
                and_(
                    or_(
                        trade_matches_table.c.user_a_id == user_id,
                        trade_matches_table.c.user_b_id == user_id,
                    ),
                    trade_matches_table.c.league_id == league_id,
                    trade_matches_table.c.status.in_(("pending", "accepted")),
                )
            )
        ).fetchall()

    result = []
    for r in rows:
        try:
            a_give    = json.loads(r.user_a_give)
            a_receive = json.loads(r.user_a_receive)
        except (json.JSONDecodeError, TypeError):
            continue
        if r.user_a_id == user_id:
            my_give, my_receive = a_give, a_receive
        else:
            my_give, my_receive = a_receive, a_give
        result.append({"my_give": my_give, "my_receive": my_receive})
    return result


def load_awaiting_trades(user_id: str) -> list[dict]:
    """
    Return cross-league trades the user has swiped "like" on that have NOT
    yet matured into mutual matches. Used by /api/trades/awaiting to power
    the "Awaiting them" segment on MatchesScreen.

    A trade decision is "awaiting" when:
      - decision == 'like'
      - no trade_matches row exists for the same league + same player sets
        (in either user_a/user_b orientation).

    Counterparty resolution: the trade_decisions row does NOT store the
    target user, so we recover it by looking up which league member's
    roster contains the receive_player_ids. This adds one league_members
    fetch per league touched, batched.

    Returns dicts shaped to mirror load_matches() output where it overlaps
    so the mobile client can render them with the same tile component:
      { trade_id, league_id, partner_id, partner_name,
        my_give, my_receive, liked_at }
    Sorted by liked_at descending (most recent first).
    """
    # Pull recent "like" decisions for the user across every league.
    # Bounded to the 500 most recent so a long-tenured user with thousands
    # of historical swipes doesn't pull an unbounded result set into memory.
    with engine.connect() as conn:
        like_rows = conn.execute(
            select(trade_decisions_table).where(
                and_(
                    trade_decisions_table.c.user_id  == user_id,
                    trade_decisions_table.c.decision == "like",
                    # #318 — a retracted like never renders in Awaiting.
                    trade_decisions_table.c.retracted_at.is_(None),
                )
            ).order_by(trade_decisions_table.c.created_at.desc()).limit(500)
        ).fetchall()

        if not like_rows:
            return []

        # Pull recent matches the user is part of so we can filter out the
        # already-matured ones. Set comparison handles JSON ordering. Same
        # 500-row defense as above.
        # NOTE: trade_matches has no created_at column — matched_at is its
        # timestamp. Ordering by .c.created_at raised AttributeError here,
        # which the /api/trades/awaiting route swallowed into an empty list
        # for ANY user with likes (found while fixing feedback #91).
        match_rows = conn.execute(
            select(trade_matches_table).where(
                or_(
                    trade_matches_table.c.user_a_id == user_id,
                    trade_matches_table.c.user_b_id == user_id,
                )
            ).order_by(trade_matches_table.c.matched_at.desc()).limit(500)
        ).fetchall()

        # Fan out one league_members fetch covering every league the user
        # has liked trades in — needed to resolve the counterparty by
        # roster ownership.
        league_ids = {r.league_id for r in like_rows}
        member_rows = []
        if league_ids:
            member_rows = conn.execute(
                select(league_members_table).where(
                    league_members_table.c.league_id.in_(league_ids)
                )
            ).fetchall()

    # Build a per-(league_id, player_id) → owner_user_id index from rosters.
    # Multiple owners of the same player ID inside a single league shouldn't
    # exist (Sleeper rosters are exclusive), but if the data is dirty we
    # take the first hit.
    owner_by_league_pid: dict[tuple[str, str], str] = {}
    owner_username_by_id: dict[tuple[str, str], str] = {}
    for mr in member_rows:
        try:
            roster_ids = json.loads(mr.roster_data) if mr.roster_data else []
        except (json.JSONDecodeError, TypeError):
            roster_ids = []
        owner_username_by_id[(mr.league_id, mr.user_id)] = (
            mr.username or mr.display_name or mr.user_id
        )
        for pid in roster_ids:
            owner_by_league_pid.setdefault((mr.league_id, pid), mr.user_id)

    # Build a set of matched player-set keys so we can skip already-matched
    # trades. We normalise by league + frozenset(give) + frozenset(receive)
    # from the caller's perspective.
    matched_keys: set[tuple[str, frozenset, frozenset]] = set()
    for r in match_rows:
        try:
            a_give    = json.loads(r.user_a_give)
            a_receive = json.loads(r.user_a_receive)
        except (json.JSONDecodeError, TypeError):
            continue
        if r.user_a_id == user_id:
            my_give, my_receive = a_give, a_receive
        else:
            # Caller is user_b — flip perspective.
            my_give, my_receive = a_receive, a_give
        matched_keys.add(
            (r.league_id, frozenset(my_give), frozenset(my_receive))
        )

    result = []
    seen_keys: set[tuple[str, frozenset, frozenset]] = set()
    for r in like_rows:
        try:
            give    = json.loads(r.give_player_ids)
            receive = json.loads(r.receive_player_ids)
        except (json.JSONDecodeError, TypeError):
            continue

        key = (r.league_id, frozenset(give), frozenset(receive))
        if key in matched_keys:
            continue   # already matured into a match
        if key in seen_keys:
            continue   # same trade re-liked across deck regenerations —
                       # one awaiting entry per underlying trade (#91)
        seen_keys.add(key)

        # Recover counterparty: owner of any of the receive players in this
        # league. If we can't find one (stale roster cache, missing member
        # data), skip — we can't render a useful tile without naming the
        # other owner.
        partner_id: str | None = None
        for pid in receive:
            cand = owner_by_league_pid.get((r.league_id, pid))
            if cand and cand != user_id:
                partner_id = cand
                break
        if not partner_id:
            continue

        partner_name = owner_username_by_id.get(
            (r.league_id, partner_id), partner_id
        )

        result.append({
            "trade_id":     r.trade_id,
            "league_id":    r.league_id,
            "partner_id":   partner_id,
            "partner_name": partner_name,
            "my_give":      give,
            "my_receive":   receive,
            "liked_at":     r.created_at,
        })

    return result


def retract_awaiting_likes(
    user_id: str,
    league_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
) -> int:
    """#318 — dismiss an "Awaiting them" trade by retracting its like rows.

    Marks EVERY live like row of `user_id` in `league_id` whose give/receive
    sets are set-equal to the given lists (order-insensitive, frozenset —
    the exact key load_awaiting_trades dedups by, so one dismiss kills every
    re-liked duplicate of the same underlying trade) with
    retracted_at = now (ISO UTC).

    Returns the number of rows NEWLY marked; 0 for an idempotent repeat or
    an absent/already-matured key — callers treat 0 as success, never 404.

    Deliberately NOT deleted and decision NOT rewritten: swipe-Elo history,
    impressions training joins and _past_decision_keys keep seeing the row
    (a dismissed offer must not resurface in the dismisser's own deck).
    Set-equality is compared in Python — give/receive live as JSON text, so
    SQL cannot compare them order-insensitively.
    """
    give_key    = frozenset(str(p) for p in give_player_ids)
    receive_key = frozenset(str(p) for p in receive_player_ids)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    with engine.begin() as conn:
        rows = conn.execute(
            select(
                trade_decisions_table.c.id,
                trade_decisions_table.c.give_player_ids,
                trade_decisions_table.c.receive_player_ids,
            ).where(
                and_(
                    trade_decisions_table.c.user_id      == user_id,
                    trade_decisions_table.c.league_id    == league_id,
                    trade_decisions_table.c.decision     == "like",
                    trade_decisions_table.c.retracted_at.is_(None),
                )
            )
        ).fetchall()

        ids: list[int] = []
        for r in rows:
            try:
                g  = frozenset(str(p) for p in json.loads(r.give_player_ids))
                rc = frozenset(str(p) for p in json.loads(r.receive_player_ids))
            except (json.JSONDecodeError, TypeError):
                continue
            if g == give_key and rc == receive_key:
                ids.append(r.id)

        if not ids:
            return 0
        conn.execute(
            trade_decisions_table.update()
            .where(trade_decisions_table.c.id.in_(ids))
            .values(retracted_at=now)
        )
    return len(ids)


# K-factors for disposition ELO signals — loaded live from model_config.
# These local lambdas fall back to the hardcoded defaults if the table
# isn't available yet (e.g. during the very first init_db() call).
_K_ACCEPT             = lambda: get_config().get("trade_k_accept",             20.0)
_K_DECLINE_CORRECTION = lambda: get_config().get("trade_k_decline_correction", 20.0)


def dismiss_match(match_id: int, user_id: str) -> dict:
    """
    Archive a trade match from ONE user's inbox — no ELO, no effect on the
    counterparty. Sets the caller's `user_{a,b}_dismissed` flag so
    `load_matches` filters it out for them from now on (survives sessions /
    redeploys). Idempotent: re-dismissing an already-dismissed match is a
    no-op 'ok'.

    Returns: {'status': 'ok' | 'not_found', 'match_id': int}

    Deliberately separate from record_match_disposition — dismissing is a
    UI-hide, NOT a decline. A decline emits a corrective ELO signal
    (winner=give, loser=receive, K=20); a dismiss must not touch rankings.
    """
    with engine.begin() as conn:
        row = conn.execute(
            select(trade_matches_table).where(
                trade_matches_table.c.id == match_id
            )
        ).fetchone()

        if row is None:
            return {"status": "not_found", "match_id": match_id}

        is_a = row.user_a_id == user_id
        is_b = row.user_b_id == user_id
        if not (is_a or is_b):
            return {"status": "not_found", "match_id": match_id}

        col = "user_a_dismissed" if is_a else "user_b_dismissed"
        conn.execute(
            trade_matches_table.update()
            .where(trade_matches_table.c.id == match_id)
            .values(**{col: 1})
        )
        return {"status": "ok", "match_id": match_id}


def record_match_disposition(
    match_id: int,
    user_id: str,
    decision: str,
) -> dict:
    """
    Record a user's accept/decline decision on a trade match.

    Returns a result dict:
    {
        'status':           'ok' | 'not_found' | 'already_decided',
        'match_id':         int,
        'both_decided':     bool,
        'outcome':          'accepted' | 'declined' | None,
        'partner_user_id':  str | None,   # the OTHER party (always set on 'ok')
        'elo_signals':      [    # only present when both_decided=True
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

        # Check already decided. Include the existing decision + the match's
        # current both_decided/outcome so the route can treat a repeat of the
        # SAME decision as an idempotent success (feedback #77) instead of a
        # blanket 409 — without re-emitting ELO signals.
        current_dec = row.user_a_decision if is_a else row.user_b_decision
        if current_dec is not None:
            prior_both = (row.user_a_decision is not None
                          and row.user_b_decision is not None)
            prior_outcome = (
                ("accepted" if (row.user_a_decision == "accept"
                                and row.user_b_decision == "accept")
                 else "declined")
                if prior_both else None
            )
            return {"status": "already_decided", "match_id": match_id,
                    "existing_decision": current_dec,
                    "league_id": row.league_id,
                    "both_decided": prior_both, "outcome": prior_outcome,
                    "elo_signals": []}

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

    # F3 (deck.fatigue) — additive context for the decline-suppression hook:
    # the package from the CALLER's perspective plus the partner's current
    # decision. Decoded defensively; failures degrade to empty lists.
    try:
        _a_give    = json.loads(row.user_a_give)
        _a_receive = json.loads(row.user_a_receive)
    except (json.JSONDecodeError, TypeError):
        _a_give, _a_receive = [], []

    return {
        "status":           "ok",
        "match_id":         match_id,
        "league_id":        row.league_id,
        "both_decided":     both_decided,
        "outcome":          outcome,
        "partner_user_id":  (row.user_b_id if is_a else row.user_a_id),
        "partner_decision": (b_dec if is_a else a_dec),
        "user_give":        (_a_give if is_a else _a_receive),
        "user_receive":     (_a_receive if is_a else _a_give),
        "elo_signals":      elo_signals,
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


def load_league_preferences_bulk(user_ids: list, league_id: str) -> dict:
    """Bulk sibling of `load_league_preference` — {user_id: prefs_row_dict}
    for every user in `user_ids` that has a row (absent users simply missing).

    Counterparty breaker LLD §2.2: ONE `IN (...)` select instead of a
    per-partner query loop on the trade-job thread. Read-only; identical
    per-row shape to `load_league_preference`.
    """
    ids = [u for u in dict.fromkeys(user_ids or ()) if u]
    if not ids:
        return {}

    def _parse_positions(raw) -> list:
        if not raw:
            return []
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    out: dict = {}
    with engine.connect() as conn:
        rows = conn.execute(
            select(league_preferences_table).where(
                and_(
                    league_preferences_table.c.user_id.in_(ids),
                    league_preferences_table.c.league_id == league_id,
                )
            )
        ).fetchall()
    for row in rows:
        out[row.user_id] = {
            "team_outlook":          row.team_outlook,
            "acquire_positions":     _parse_positions(
                getattr(row, "acquire_positions", None)),
            "trade_away_positions":  _parse_positions(
                getattr(row, "trade_away_positions", None)),
        }
    return out


# ---------------------------------------------------------------------------
# Asset preferences — untouchables + targets + not-interested (backlog #2, #163)
# ---------------------------------------------------------------------------

ASSET_PREF_LISTS = ("untouchable", "target", "not_interested")


def load_asset_preferences(user_id: str, league_id: str) -> dict:
    """Return {"untouchables": [player_id, ...], "targets": [...],
    "not_interested": [...]} for (user_id, league_id). Empty lists when none
    saved."""
    out = {"untouchables": [], "targets": [], "not_interested": []}
    with engine.connect() as conn:
        rows = conn.execute(
            select(asset_preferences_table).where(
                and_(
                    asset_preferences_table.c.user_id   == user_id,
                    asset_preferences_table.c.league_id == league_id,
                )
            )
        ).fetchall()
    for r in rows:
        if r.list_type == "untouchable":
            out["untouchables"].append(r.player_id)
        elif r.list_type == "target":
            out["targets"].append(r.player_id)
        elif r.list_type == "not_interested":
            out["not_interested"].append(r.player_id)
    return out


def load_asset_preferences_bulk(user_ids: list, league_id: str) -> dict:
    """Bulk sibling of `load_asset_preferences` — {user_id: {list_key: [...]}}
    for every user in `user_ids` that has rows (absent users simply missing,
    so callers can distinguish "no prefs saved" from "not asked about").

    Counterparty breaker LLD §2.2: ONE `IN (...)` select instead of a
    per-partner query loop on the trade-job thread. Read-only; per-user shape
    identical to `load_asset_preferences` (plural list keys, `ASSET_PREF_LISTS`
    row types).
    """
    ids = [u for u in dict.fromkeys(user_ids or ()) if u]
    if not ids:
        return {}
    _KEY = {"untouchable":    "untouchables",
            "target":         "targets",
            "not_interested": "not_interested"}
    out: dict = {}
    with engine.connect() as conn:
        rows = conn.execute(
            select(asset_preferences_table).where(
                and_(
                    asset_preferences_table.c.user_id.in_(ids),
                    asset_preferences_table.c.league_id == league_id,
                )
            )
        ).fetchall()
    for r in rows:
        key = _KEY.get(r.list_type)
        if key is None:
            continue
        bucket = out.get(r.user_id)
        if bucket is None:
            bucket = out[r.user_id] = {"untouchables": [], "targets": [],
                                       "not_interested": []}
        bucket[key].append(r.player_id)
    return out


def set_asset_preference(
    user_id: str, league_id: str, player_id: str, list_type: str | None,
) -> dict:
    """Add/move/remove a player's tag for a league, returning the refreshed
    lists. `list_type` ∈ {'untouchable','target','not_interested'} adds
    (replacing any prior tag for that player — single membership), None
    removes. Idempotent. Raises ValueError on an unknown list_type."""
    if list_type is not None and list_type not in ASSET_PREF_LISTS:
        raise ValueError(f"list_type must be one of {ASSET_PREF_LISTS} or None")
    pid = str(player_id)
    now = _now()
    with engine.begin() as conn:
        # Remove any existing tag for this player first (enforces single
        # membership and makes 'none' a plain delete) ...
        conn.execute(
            asset_preferences_table.delete().where(
                and_(
                    asset_preferences_table.c.user_id   == user_id,
                    asset_preferences_table.c.league_id == league_id,
                    asset_preferences_table.c.player_id == pid,
                )
            )
        )
        if list_type is not None:
            conn.execute(insert(asset_preferences_table), [{
                "user_id":    user_id,
                "league_id":  league_id,
                "player_id":  pid,
                "list_type":  list_type,
                "created_at": now,
            }])
    return load_asset_preferences(user_id, league_id)


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
        AND the player has no team (retired/out-of-league veterans;
        rostered Inactive/IR players and years_exp=None prospects are kept)

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
        # (undrafted rookies / prospects).  Remove non-Active veterans ONLY
        # when they carry no team: Sleeper marks rostered-but-unavailable
        # players (IR / suspended / NFI) "Inactive" while they still hold a
        # team slot, and those are real dynasty assets — dropping them made
        # Ricky Pearsall (SF, status Inactive) vanish from the pool and fail
        # a premium rankings import (G-008 class, found 2026-08-16). A
        # teamless non-Active veteran is retired / out of the league.
        status    = p.get("status") or ""
        years_exp = p.get("years_exp")
        if status != "Active" and years_exp is not None and not p.get("team"):
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

        # #207 — keep Sleeper's rookie class year. Only a plausible 4-digit
        # year survives: the dump serves "0" for ~5 % of years_exp==0 players
        # and omits the field entirely for camp bodies / UDFAs. NULL falls
        # back to the years_exp proxy at read time (draft_status.is_rookie_row).
        rookie_year = (p.get("metadata") or {}).get("rookie_year") \
            if isinstance(p.get("metadata"), dict) else None
        rookie_year = str(rookie_year).strip() if rookie_year is not None else ""
        if not (len(rookie_year) == 4 and rookie_year.isdigit()
                and rookie_year != "0000"):
            rookie_year = None

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
            "rookie_year":          rookie_year,
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


def load_players(
    position: str | None = None,
    columns: list[str] | None = None,
) -> list[dict]:
    """
    Return all synced players, optionally filtered by position.
    Sorted by search_rank ascending (lower = more relevant); players
    without a search_rank are appended last.

    ``columns`` restricts the SELECT to the named DB columns (e.g.
    ``['player_id', 'full_name', 'team', 'age', 'search_rank']``).
    Unknown column names are silently ignored.  Pass ``None`` (default)
    to return every column.
    """
    with engine.connect() as conn:
        if columns:
            valid = [players_table.c[c] for c in columns if c in players_table.c]
            q = select(*valid) if valid else select(players_table)
        else:
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


def load_rookies(season: int = 2026) -> list[dict]:
    """
    Return `season`'s rookie class from the DB, suitable for displaying on a
    dynasty rookie draft board. Sorted by search_rank (lower = higher-ranked
    prospect), NULLs last.

    **Rebased onto THE rookie predicate** (rookie-draft M0): membership is
    `load_rookie_player_ids(season)` — `rookie_year == season`, falling back
    to `years_exp == 0 AND team IS NOT NULL` only when the class year is
    missing. The previous rule here (`years_exp == 0 OR years_exp IS NULL`,
    no team requirement and no `rookie_year` test) was a THIRD, looser
    definition that swept in the whole teamless pre-NFL-draft prospect tail
    plus every unclassifiable camp body — 157 phantom "rookies" against the
    April-2026 dev cache. See docs/cross-client-invariants.md § Rookie
    predicate. This function and `GET /api/rookies` are retired in M4.
    """
    ids = load_rookie_player_ids(season)
    if not ids:
        return []
    id_list = sorted(ids)
    rows: list = []
    # Chunked so a large class can never trip SQLite's bound-variable limit.
    for i in range(0, len(id_list), 500):
        with engine.connect() as conn:
            rows.extend(conn.execute(
                select(players_table).where(
                    and_(
                        players_table.c.position.in_(["QB", "RB", "WR", "TE"]),
                        players_table.c.player_id.in_(id_list[i:i + 500]),
                    )
                )
            ).fetchall())
    out = [dict(r._mapping) for r in rows]
    out.sort(key=lambda r: (r.get("search_rank") is None,
                            r.get("search_rank") or 0))
    return out


def count_rookie_class_rows(season: int) -> int:
    """How many `players` rows carry `rookie_year == season` EXACTLY.

    Deliberately the exact test only — no `years_exp` proxy. The proxy is
    season-independent, so it would report the current class as present for
    every future season and make the class-load monitor (M0) fire on day one.
    """
    yr = str(int(season))
    with engine.connect() as conn:
        return int(conn.execute(
            select(func.count()).select_from(players_table)
            .where(players_table.c.rookie_year == yr)
        ).scalar() or 0)


def load_rookie_player_ids(season: int) -> set[str]:
    """#207 — player_ids belonging to `season`'s rookie class.

    Exact test first (`rookie_year == season`), then the proxy for rows whose
    class year Sleeper never carried (`years_exp == 0 AND team IS NOT NULL` —
    the team requirement drops the teamless pre-NFL-draft prospect tail).
    Mirrors draft_status.is_rookie_row; kept as SQL so the roster heuristic
    costs one indexed scan instead of loading the whole player table.
    """
    yr = str(int(season))
    with engine.connect() as conn:
        rows = conn.execute(
            select(players_table.c.player_id).where(
                or_(
                    players_table.c.rookie_year == yr,
                    and_(
                        players_table.c.rookie_year.is_(None),
                        players_table.c.years_exp == 0,
                        players_table.c.team.isnot(None),
                        players_table.c.team != "",
                    ),
                )
            )
        ).fetchall()
    return {str(r.player_id) for r in rows}


def count_known_player_ids(player_ids) -> int:
    """How many of `player_ids` exist in our players table (#207 staleness
    guard — a big unknown tail means the snapshot is stale, not that the
    league has no rookies)."""
    ids = [str(p) for p in player_ids if p]
    if not ids:
        return 0
    found = 0
    with engine.connect() as conn:
        for i in range(0, len(ids), 500):   # SQLite variable limit
            chunk = ids[i: i + 500]
            found += len(conn.execute(
                select(players_table.c.player_id)
                .where(players_table.c.player_id.in_(chunk))
            ).fetchall())
    return found


# ---------------------------------------------------------------------------
# #207 — per-league rookie-draft status cache
# ---------------------------------------------------------------------------

def set_league_draft_status(league_id: str, status: str,
                            confidence: str | None) -> None:
    """Persist a league's rookie-draft verdict + the check timestamp.

    Always stamps `draft_status_checked_at`, including for `unknown`, so the
    cheap-skip in server._refresh_league_draft_status can back off a league
    whose platform read keeps flaking instead of retrying every tick.
    """
    if not league_id:
        return
    with engine.begin() as conn:
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .values(draft_status=status,
                    draft_status_confidence=confidence,
                    draft_status_checked_at=_now())
        )


def get_league_draft_context(league_id: str) -> dict | None:
    """Season + cached draft verdict for one league, or None when unknown.

    Returns {season:int|None, platform:str, total_rosters:int|None,
             status:str|None, confidence:str|None, checked_at:str|None}.
    """
    if not league_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.season,
                   leagues_table.c.platform,
                   leagues_table.c.total_rosters,
                   leagues_table.c.draft_status,
                   leagues_table.c.draft_status_confidence,
                   leagues_table.c.draft_status_checked_at)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .limit(1)
        ).fetchone()
    if not row:
        return None
    try:
        season = int(row.season) if row.season else None
    except (TypeError, ValueError):
        season = None
    return {
        "season":        season,
        "platform":      row.platform or "sleeper",
        "total_rosters": row.total_rosters,
        "status":        row.draft_status,
        "confidence":    row.draft_status_confidence,
        "checked_at":    row.draft_status_checked_at,
    }


def load_league_ids_for_draft_status_refresh(limit: int = 500) -> list[str]:
    """Leagues the hourly tick should re-check, freshest-last.

    Ordered so never-checked leagues come first, then the stalest — the tick
    applies its own per-status TTL (see server._draft_status_is_fresh), this
    just bounds the scan.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(leagues_table.c.sleeper_league_id)
            .order_by(leagues_table.c.draft_status_checked_at.is_(None).desc(),
                      leagues_table.c.draft_status_checked_at)
            .limit(int(limit))
        ).fetchall()
    return [str(r.sleeper_league_id) for r in rows]


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
# ⚠️  SUPERSEDED as a pricing rate by pick_values.year_decay(round) (D-079).
# Kept only so the constant's old meaning stays readable next to _PICK_BASE;
# no pricing site reads it any more.
_PICK_YEAR_DISCOUNT = 0.85   # 15 % off per year out (pre-D-079, all rounds)


def compute_pick_value(
    round_: int,
    season: int,
    current_season: int,
    league_size: int = 12,
) -> float:
    """
    Return the dynasty fantasy value for a draft pick.

    Uses the mid-tier base value for the round, scales by league size
    (12-team baseline, clamped to [0.5, 1.5]), and applies the round's
    per-year decay for each year the pick is in the future.

    D-079: that rate is PER ROUND (`pick_values.year_decay`), not the flat
    15 % this used to apply — round 1 is flat by default, so a 2029 1st on
    this legacy scale now prices like a 2026 1st, exactly as it does on the
    `pool_value` scale. Routing both scales through the one shared helper is
    the whole point of the ladder living in `pick_values` (see that module's
    docstring); a second, quietly different rate here is the drift the
    original split was created to prevent.
    """
    from .pick_values import year_decay
    base       = _PICK_BASE.get(round_, _PICK_DEFAULT_VALUE)
    scale      = max(0.5, min(1.5, league_size / 12.0))
    years_out  = max(0, season - current_season)
    discounted = base * scale * (year_decay(round_) ** years_out)
    return round(discounted, 2)


# ---------------------------------------------------------------------------
# draft-extensions W3 M-A — user-asserted pick ownership (ADR-010)
# ---------------------------------------------------------------------------
#
# Three provenance columns on `draft_picks` (`source` / `assigned_by` /
# `assigned_at`) let a league member assert who owns each slot of a league
# whose platform has no readable draft object (ESPN, per the operator ruling
# that ESPN has no rookie-draft concept at all).
#
# THE CONTAINMENT IS THE READ DEFAULT, not a table split: `load_draft_picks`
# defaults to `source='platform'`, which selects exactly the rows it selected
# before this wave, in the same order, for every league. A read site opts into
# asserted rows one at a time, explicitly, and an AST test enumerates them.
#
# The safety property that makes assertion tolerable at all: price is a pure
# server-side function of `(round, season - current_season, format)` via the
# SHIPPED `pick_pool_value` / `compute_pick_value`, and every owner must be an
# existing `league_members` row inside a fixed `rounds x teams x seasons`
# grid. So a bad or malicious assignment can REDISTRIBUTE value; it can never
# CREATE it. The only inflation lever is `rounds`, clamped server-side to
# `draft_status.ROOKIE_MAX_ROUNDS`.

PICK_SOURCE_PLATFORM = "platform"
PICK_SOURCE_USER     = "user"
PICK_SOURCE_ANY      = "any"

ORDER_TYPE_LINEAR = "linear"
ORDER_TYPE_SNAKE  = "snake"

#: Contested/orphaned derivation is memoised per league and invalidated
#: explicitly on every write, so a correction un-contests a slot at the next
#: read rather than after a TTL. The TTL is only a cross-process backstop.
#: Mirrors the `_COMMUNITY_ELO_CACHE` pattern already in this module.
_CONTESTED_TTL_SECONDS = 60.0
_CONTESTED_CACHE: dict[str, tuple[float, frozenset[str], frozenset[str]]] = {}
#: `has_assigned_picks` memo — the DATA half of W3 M-C's engine guard and of
#: `picks_supported`. Same lock, same TTL, same invalidation hook.
_ASSIGNED_CACHE: dict[str, tuple[float, bool]] = {}
_CONTESTED_LOCK = threading.Lock()


def make_pick_id(league_id: str, season: int, round_: int,
                 original_roster_id: str) -> str:
    """THE `pick_id` format: ``{league}_{season}_{round}_{original_roster}``.

    `round` is unpadded, so a `pick_id` is NOT lexicographically sortable —
    never order by it. This constructor exists because the format was three
    duplicated f-strings before W3 and the assignment store would have made a
    fourth; every producer now goes through here (INV-8).
    """
    return f"{league_id}_{season}_{int(round_)}_{original_roster_id}"


def _pick_source_predicate(source: str):
    """SQLAlchemy predicate for the `source` containment, or None for 'any'."""
    if source == PICK_SOURCE_ANY:
        return None
    if source == PICK_SOURCE_USER:
        return draft_picks_table.c.source == PICK_SOURCE_USER
    # 'platform' (the default) — NULL reads as platform, so this selects
    # exactly the pre-W3 row set.
    return or_(draft_picks_table.c.source.is_(None),
               draft_picks_table.c.source == PICK_SOURCE_PLATFORM)


def _invalidate_contested(league_id: str) -> None:
    """Drop the memoised contested/orphaned sets for one league.

    Also drops the `has_assigned_picks` memo, which W3 M-C's engine guard
    reads on every trade job: an assignment must light a league up at the
    next read, not after a TTL.
    """
    with _CONTESTED_LOCK:
        _CONTESTED_CACHE.pop(str(league_id), None)
        _ASSIGNED_CACHE.pop(str(league_id), None)


#: Public alias — the assignment routes invalidate AFTER writing the audit
#: event (contested is derived from `user_events`, so invalidating before the
#: event lands would re-memoise the stale answer).
invalidate_pick_assignment_cache = _invalidate_contested


def _derive_excluded(league_id: str) -> tuple[frozenset[str], frozenset[str]]:
    """``(contested, orphaned)`` pick ids for one league.

    **Contested** = a slot that at least two DISTINCT users assigned to at
    least two DIFFERENT owners. Both conditions are required: two actors
    agreeing on the same owner is not a disagreement, and one actor changing
    their own mind twice is not one either. Derived from the
    `pick_assignment_changed` audit trail — there is no contested column.

    **Orphaned** = a `source='user'` row whose `owner_user_id` is not a
    current `league_members` row (a SWID rotation on re-import, or a manager
    who left). Surfaced as a re-assign row and excluded from pricing, NEVER
    silently dropped: a dropped slot is value that vanishes with no
    explanation.

    Both sets are withheld from the priced union by ROW FILTERING. Nulling
    `pool_value` instead is forbidden — `server._power_picks_by_owner`
    re-derives a price when `pool_value` is NULL, so nulling would silently
    re-price the very row the rule exists to withhold (INV-5).
    """
    lid = str(league_id)
    contested: set[str] = set()
    orphaned:  set[str] = set()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(user_events_table.c.props).where(
                    (user_events_table.c.event_type == "pick_assignment_changed")
                    & (user_events_table.c.league_id == lid)
                )
            ).fetchall()
            by_pick: dict[str, set[tuple[str, str]]] = {}
            for r in rows:
                try:
                    p = json.loads(r.props or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                pid = p.get("pick_id")
                if not pid:
                    continue
                by_pick.setdefault(str(pid), set()).add(
                    (str(p.get("actor") or ""), str(p.get("new_owner") or "")))
            contested = {
                pid for pid, pairs in by_pick.items()
                if len({a for a, _ in pairs}) >= 2 and len({o for _, o in pairs}) >= 2
            }

            members = {
                str(r.user_id) for r in conn.execute(
                    select(league_members_table.c.user_id).where(
                        league_members_table.c.league_id == lid)
                ).fetchall()
            }
            if members:
                owned = conn.execute(
                    select(draft_picks_table.c.pick_id,
                           draft_picks_table.c.owner_user_id)
                    .where((draft_picks_table.c.league_id == lid)
                           & (draft_picks_table.c.source == PICK_SOURCE_USER))
                ).fetchall()
                orphaned = {str(r.pick_id) for r in owned
                            if str(r.owner_user_id or "") not in members}
    except Exception as e:                      # pragma: no cover - DB optional
        # A derivation failure must NOT silently unprice a whole league.
        log.warning("contested/orphan derivation failed for %s: %s", lid, e)
        return frozenset(), frozenset()
    return frozenset(contested), frozenset(orphaned)


def _excluded_pick_ids(league_id: str) -> tuple[frozenset[str], frozenset[str]]:
    lid = str(league_id)
    with _CONTESTED_LOCK:
        cached = _CONTESTED_CACHE.get(lid)
        if cached and (time.time() - cached[0]) < _CONTESTED_TTL_SECONDS:
            return cached[1], cached[2]
    contested, orphaned = _derive_excluded(lid)
    with _CONTESTED_LOCK:
        _CONTESTED_CACHE[lid] = (time.time(), contested, orphaned)
    return contested, orphaned


def contested_pick_ids(league_id: str) -> frozenset[str]:
    """Slots ≥2 distinct users assigned to ≥2 DIFFERENT owners."""
    return _excluded_pick_ids(league_id)[0]


def orphaned_pick_ids(league_id: str) -> frozenset[str]:
    """Asserted slots whose owner is no longer a league member."""
    return _excluded_pick_ids(league_id)[1]


def has_assigned_picks(league_id: str) -> bool:
    """Does this league hold ANY `source='user'` row? (W3 M-C.)

    THE data half of two decisions the plan words as "a data test, not a
    platform test":

      * the engine guard `server._owned_picks_available` — an ESPN league
        with assignments qualifies for pick math, one without it does not;
      * `picks_supported` on `/api/league/picks` — ESPN with nothing
        assigned still honestly reports `false`.

    Deliberately ignores contested/orphaned exclusion: a league whose only
    asserted rows are contested still HAS assignments (the answer to "is this
    configured at all"), and the exclusion is applied per-row by
    `load_draft_picks`, which is where it belongs. Memoised for
    `_CONTESTED_TTL_SECONDS` and invalidated on every assignment write.
    """
    lid = str(league_id)
    with _CONTESTED_LOCK:
        hit = _ASSIGNED_CACHE.get(lid)
        if hit and (time.time() - hit[0]) < _CONTESTED_TTL_SECONDS:
            return hit[1]
    try:
        with engine.connect() as conn:
            found = conn.execute(
                select(draft_picks_table.c.pick_id)
                .where((draft_picks_table.c.league_id == lid)
                       & (draft_picks_table.c.source == PICK_SOURCE_USER))
                .limit(1)
            ).first() is not None
    except Exception as e:                      # pragma: no cover - DB optional
        # Fail CLOSED: an unreadable store must not light up pick math.
        log.warning("assigned-pick probe failed for %s: %s", lid, e)
        return False
    with _CONTESTED_LOCK:
        _ASSIGNED_CACHE[lid] = (time.time(), found)
    return found


def sync_draft_picks(
    league_id: str,
    roster_ids: list[int],
    traded_picks: list[dict],
    roster_id_to_user: dict[str, str],
    user_id_to_name: dict[str, str],
    current_season: int = 2026,
    rounds: int = 3,
    seasons_ahead: int = 3,
    league_size: int = 12,
    scoring_format: str = "1qb_ppr",
    exclude_seasons: tuple[int, ...] | set[int] = (),
) -> list[dict]:
    """
    Build the full pick grid for a dynasty league and persist it to the DB.

    Algorithm
    ---------
    1. Generate the "pristine" grid: every (season, round, roster_id) tuple
       for the league's REAL pick horizon (`draft_status.pick_horizon`) —
       three consecutive rookie classes anchored to the first class that has
       not yet been drafted. Under `picks.league_horizon` OFF this falls back
       to the historical [current_season … current_season + seasons_ahead].
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
    seasons_ahead      : LEGACY window width, used only when the kill switch
                         `picks.league_horizon` is OFF. With the flag ON the
                         window comes from `draft_status.pick_horizon` instead
                         (#355: a fixed current_season+3 invented a 4th class
                         that pre-draft Sleeper leagues do not have, so cards
                         offered picks the user could never execute)
    exclude_seasons    : seasons whose picks must NOT be synced (#228 —
                         the caller passes the current season when that
                         season's rookie draft is already complete; the
                         replace-sync then also cleans previously synced
                         rows for those seasons)

    #220 guard: with NO roster_ids the "grid" would be empty and the
    replace-sync below would WIPE the league's existing picks — the only
    real producer of that input is an upstream Sleeper fetch failure
    (the #200 clobber class), so this is a no-op that keeps the prior
    snapshot instead. Returns [] without touching the DB.
    """
    if not roster_ids:
        return []

    now = _now()
    exclude = {int(s) for s in exclude_seasons}

    # Step 0 (#355): the league's REAL pick horizon. A fixed `seasons_ahead`
    # measured from `current_season` over-reached by exactly one class for
    # every pre-draft league — the source of the phantom 2029 picks. Kill
    # switch `picks.league_horizon` restores the historical window verbatim.
    try:
        from .feature_flags import is_enabled
        _horizon_on = is_enabled("picks.league_horizon")
    except Exception:                       # pragma: no cover - config optional
        _horizon_on = False
    if _horizon_on:
        from . import draft_status as _ds
        first_season, last_season = _ds.pick_horizon(
            current_season,
            exclude_seasons=exclude,
            observed_seasons=[tp.get("season") for tp in (traded_picks or [])
                              if isinstance(tp, dict)],
        )
    else:
        first_season = int(current_season)
        last_season = int(current_season) + int(seasons_ahead)

    # Step 1: build the pristine pick grid (everyone keeps their own picks)
    picks: dict[str, dict] = {}
    for rid in roster_ids:
        rid_str  = str(rid)
        user_id  = roster_id_to_user.get(rid_str, "")
        username = user_id_to_name.get(user_id, f"Roster {rid_str}")
        for season in range(first_season, last_season + 1):
            if season in exclude:               # #228 — draft already held
                continue
            for rnd in range(1, rounds + 1):
                pick_id = make_pick_id(league_id, season, rnd, rid_str)
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
                    "pick_value":         compute_pick_value(rnd, season, current_season, league_size),
                    "pool_value":         pick_pool_value(rnd, season - current_season, scoring_format),
                    "platform":           "sleeper",
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

        # #355 — floor at the horizon ANCHOR, not `current_season`: once a
        # class is drafted its picks are spent, so a stale traded row for it
        # must not resurrect a grid slot. Deliberately NO upper bound here —
        # a pick the platform actually reports is existence proof, and
        # `pick_horizon` has already widened `last_season` to cover it.
        if not orig_rid or not new_rid or rnd < 1 or season < first_season:
            continue
        if season in exclude:                   # #228 — draft already held
            continue

        pick_id = make_pick_id(league_id, season, rnd, orig_rid)

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
                "pick_value":         compute_pick_value(rnd, season, current_season, league_size),
                "pool_value":         pick_pool_value(rnd, season - current_season, scoring_format),
                "platform":           "sleeper",
            }

        is_traded = int(new_rid != orig_rid)
        picks[pick_id].update({
            "owner_user_id":  new_user,
            "owner_username": new_username,
            "is_traded":      is_traded,
        })

    # Step 3: replace-sync all picks for this league (delete + bulk-insert)
    rows = [
        {**p, "synced_at": now}
        for p in picks.values()
    ]
    replace_draft_picks(league_id, rows)
    return rows


def replace_draft_picks(league_id: str, rows: list[dict],
                        preserve_source: str | None = None) -> None:
    """Snapshot-replace ONE PROVENANCE's draft-pick rows for one league.

    Delete the league's existing rows of the caller's own provenance, then
    bulk-insert `rows` fresh. Shared by the Sleeper grid+overlay sync
    (`sync_draft_picks`), the MFL normalization path
    (`server._sync_mfl_owned_picks`) and W3's assignment projection, so all
    three write through one code path. Rows are expected to carry `synced_at`;
    callers that build rows outside `sync_draft_picks` stamp it themselves.

    `preserve_source` names the provenance THE CALLER OWNS. The DELETE is
    scoped to exactly that provenance and never crosses it — the whole
    invariant is "a writer only ever deletes rows it could have written"
    (INV-2). The parameter name reads backwards on the default branch, so
    read the two branches literally:

      None (default) -> DELETE WHERE league_id = ? AND (source IS NULL
                        OR source <> 'user')
                        The historical behavior, NARROWED. Every platform
                        caller keeps this and therefore can no longer destroy
                        a league's asserted rows — including on a sync fired
                        by a future platform writer nobody has written yet.
      'user'         -> DELETE WHERE league_id = ? AND source = 'user'
                        W3's assignment projection is the ONLY caller passing
                        this, and it cannot touch a platform row.
    """
    if preserve_source == PICK_SOURCE_USER:
        scope = draft_picks_table.c.source == PICK_SOURCE_USER
    else:
        scope = or_(draft_picks_table.c.source.is_(None),
                    draft_picks_table.c.source != PICK_SOURCE_USER)
    with engine.begin() as conn:
        conn.execute(
            delete(draft_picks_table).where(
                (draft_picks_table.c.league_id == league_id) & scope
            )
        )
        if rows:
            chunk_size = 200
            for i in range(0, len(rows), chunk_size):
                conn.execute(insert(draft_picks_table), rows[i: i + chunk_size])


def load_draft_picks(
    league_id: str,
    owner_user_id: str | None = None,
    source: str = PICK_SOURCE_PLATFORM,
    include_contested: bool = False,
) -> list[dict]:
    """
    Return draft picks for a league, optionally filtered to a single owner.
    Sorted by season ASC, round ASC, pick_value DESC.

    `source` is THE containment (ADR-010). It defaults to platform-only, so
    every pre-W3 call site is byte-identical until it explicitly opts in:

      "platform"  ->  source IS NULL OR source = 'platform'   (DEFAULT)
                      Every pre-W3 row has source IS NULL, so this selects
                      exactly today's rows, in today's order.
      "user"      ->  source = 'user'
      "any"       ->  no source predicate

    When the result CAN contain user rows ("user"/"any") and
    `include_contested` is False, contested and orphaned slots are dropped —
    see `_derive_excluded`. That exclusion is a ROW FILTER and must never be
    implemented by nulling `pool_value`: `server._power_picks_by_owner`
    re-derives a price from a NULL `pool_value`, so nulling would silently
    re-price the very row the rule withholds (INV-5).
    """
    predicate = _pick_source_predicate(source)
    with engine.connect() as conn:
        q = select(draft_picks_table).where(
            draft_picks_table.c.league_id == league_id
        )
        if predicate is not None:
            q = q.where(predicate)
        if owner_user_id is not None:
            q = q.where(draft_picks_table.c.owner_user_id == owner_user_id)
        q = q.order_by(
            draft_picks_table.c.season,
            draft_picks_table.c.round,
            draft_picks_table.c.pick_value.desc(),
        )
        rows = conn.execute(q).fetchall()
    out = [dict(r._mapping) for r in rows]
    if source != PICK_SOURCE_PLATFORM and not include_contested:
        # In PYTHON, after the fetch: the exclusion sets are memoised and
        # pushing them into SQL would need a dialect-divergent JSON extraction.
        contested, orphaned = _excluded_pick_ids(league_id)
        if contested or orphaned:
            drop = contested | orphaned
            out = [r for r in out
                   if not (r.get("source") == PICK_SOURCE_USER
                           and str(r.get("pick_id")) in drop)]
    return out


def seed_pick_grid(
    league_id: str,
    member_user_ids: list[str],
    user_id_to_name: dict[str, str],
    actor_user_id: str,
    current_season: int,
    rounds: int,
    seasons_ahead: int = 3,
    league_size: int | None = None,
    scoring_format: str = "1qb_ppr",
    platform: str = "espn",
    reseed: bool = False,
) -> dict:
    """Write the PRISTINE grid: every team owns its own picks, every season.

    Returns ``{"seeded", "reseeded_over", "carried", "skipped", "total"}``.
    Idempotent:
    re-running without `reseed` preserves every edited slot byte-for-byte
    (D14). Never writes a user-supplied value — `pick_value` / `pool_value`
    come only from the shipped `compute_pick_value` / `pick_pool_value`.

    `original_roster_id` is an OPAQUE, LEAGUE-LOCAL slot label. `league_members`
    has no `roster_id` column, so this is never resolved against a platform,
    and it is STABLE: a member who already has slots keeps them, and a new
    member takes the next free integer. (The LLD specified `index i =>
    str(i+1)` off the passed member list; that silently re-points every
    `pick_id`'s "original team" the moment the roster changes, so this
    preserves the established mapping instead.)
    """
    from . import draft_status

    # ── 0. CLAMP. The conservation bound's ONLY lever, and it is enforced
    #    here rather than in the route so no caller can bypass it.
    rounds = max(1, min(int(rounds), draft_status.ROOKIE_MAX_ROUNDS))
    seasons_ahead = max(0, int(seasons_ahead))
    member_user_ids = [str(u) for u in member_user_ids if str(u or "")]
    if not member_user_ids:
        return {"seeded": 0, "reseeded_over": 0, "carried": 0, "total": 0}
    teams = int(league_size or len(member_user_ids))

    # NOT source="any": the seeder must never read, and therefore never
    # rewrite, a platform row.
    existing_rows = load_draft_picks(league_id, source=PICK_SOURCE_USER,
                                     include_contested=True)
    existing = {str(r["pick_id"]): r for r in existing_rows}

    # `pick_id`'s unique key has NO provenance dimension, so one slot cannot
    # hold both a platform row and an asserted one. The platform wins — it is
    # the authoritative reading — and the seeder SKIPS that slot rather than
    # raising an IntegrityError. This is normally empty: assignment exists for
    # leagues whose platform writes no pick rows at all.
    taken_by_platform = {str(r["pick_id"]) for r in
                         load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)}

    # Stable slot labels — reuse what the grid already established.
    slot_by_user: dict[str, str] = {}
    used: set[str] = set()
    for r in existing_rows:
        ou  = str(r.get("original_user_id") or "")
        rid = str(r.get("original_roster_id") or "")
        if ou and rid and ou not in slot_by_user:
            slot_by_user[ou] = rid
            used.add(rid)
    next_slot = 1
    for uid in member_user_ids:
        if uid in slot_by_user:
            continue
        while str(next_slot) in used:
            next_slot += 1
        slot_by_user[uid] = str(next_slot)
        used.add(str(next_slot))

    now = _now()
    seasons = list(range(int(current_season), int(current_season) + seasons_ahead + 1))
    rows: list[dict] = []
    seeded = reseeded_over = skipped = 0
    generated: set[str] = set()

    for season in seasons:
        years_out = season - int(current_season)
        for uid in member_user_ids:
            orig_rid = slot_by_user[uid]
            for rnd in range(1, rounds + 1):
                pick_id = make_pick_id(league_id, season, rnd, orig_rid)
                if pick_id in taken_by_platform:
                    skipped += 1
                    continue
                generated.add(pick_id)
                prior = existing.get(pick_id)
                if prior is not None and not reseed:
                    rows.append(prior)          # PRESERVE the edit verbatim
                    continue
                if prior is not None:
                    reseeded_over += 1
                seeded += 1
                rows.append({
                    "pick_id":            pick_id,
                    "league_id":          league_id,
                    "season":             season,
                    "round":              rnd,
                    "owner_user_id":      uid,          # pristine: own your own
                    "owner_username":     user_id_to_name.get(uid, f"Team {orig_rid}"),
                    "original_roster_id": orig_rid,
                    "original_user_id":   uid,
                    "original_username":  user_id_to_name.get(uid, f"Team {orig_rid}"),
                    "is_traded":          0,
                    # ── No user-entered values, EVER. The shipped functions. ──
                    "pick_value":  compute_pick_value(rnd, season, int(current_season), teams),
                    "pool_value":  pick_pool_value(rnd, years_out, scoring_format),
                    "platform":    platform,    # provenance of the LEAGUE
                    "source":      PICK_SOURCE_USER,    # provenance of the ROW
                    "assigned_by": actor_user_id,
                    "assigned_at": now,
                    "synced_at":   now,
                })

    # Slots whose ORIGINAL team has left the league still exist and may be
    # owned by someone who is still here — carry them so nothing vanishes.
    # Bounded to the grid's own (season, round) box, so shrinking `rounds` or
    # the season horizon is an explicit user action rather than a silent drop.
    carried = 0
    season_set = set(seasons)
    for pick_id, prior in existing.items():
        if pick_id in generated:
            continue
        try:
            if int(prior.get("season")) not in season_set:
                continue
            if not (1 <= int(prior.get("round") or 0) <= rounds):
                continue
        except (TypeError, ValueError):
            continue
        rows.append(prior)
        carried += 1

    replace_draft_picks(league_id, rows, preserve_source=PICK_SOURCE_USER)
    _invalidate_contested(league_id)
    return {"seeded": seeded, "reseeded_over": reseeded_over,
            "carried": carried, "skipped": skipped, "total": len(rows)}


def load_pick_assignment_settings(league_id: str) -> dict | None:
    """The league's stored NUMBERING settings, or None when never configured.

    ``{rounds:int, order_type:'linear'|'snake', order:[user_id, ...]}``.
    Ownership is never stored here — see the column comment.
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.pick_assignment_settings)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .limit(1)
        ).fetchone()
    if not row or not row.pick_assignment_settings:
        return None
    try:
        parsed = json.loads(row.pick_assignment_settings)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def save_pick_assignment_settings(league_id: str, settings: dict) -> None:
    """Persist the league's NUMBERING settings (rounds / order_type / order)."""
    with engine.begin() as conn:
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .values(pick_assignment_settings=json.dumps(settings))
        )


def load_draft_slot_order(league_id: str) -> dict | None:
    """The league's resolved CURRENT-season draft order, or None (D-090).

    Shape is ``backend/pick_slots``' blob; see the column comment. None means
    "no slot is resolvable for this league" and every owned-pick label falls
    back to its generic round, which is the pre-D-090 string exactly.
    """
    if not league_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.draft_slot_order)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .limit(1)
        ).fetchone()
    if not row or not row.draft_slot_order:
        return None
    try:
        parsed = json.loads(row.draft_slot_order)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def save_draft_slot_order(league_id: str, order: dict | None) -> None:
    """Persist (or clear, with None) the resolved current-season draft order.

    Clearing is the honest write when the order was set and has since been
    UNSET upstream — leaving a stale blob would keep labelling picks with an
    order the league no longer uses.
    """
    if not league_id:
        return
    with engine.begin() as conn:
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .values(draft_slot_order=(json.dumps(order) if order else None))
        )


def assign_draft_pick(league_id: str, pick_id: str, owner_user_id: str,
                      owner_username: str, actor_user_id: str,
                      if_assigned_at: str | None) -> tuple[str, dict | None]:
    """Compare-and-swap ONE slot. Returns ``(outcome, row)``.

    `outcome` is ``'ok'`` | ``'stale'`` | ``'not_found'``. On ``'stale'`` the
    row returned is the CURRENT row, so the route can answer 409 with it in
    one round trip and the client can say "Dana changed this 4 minutes ago —
    keep theirs, or use yours?" without a second request.

    The comparison lives in the UPDATE's WHERE clause, so it is atomic under
    both dialects without a SELECT-then-UPDATE window. `IS NOT DISTINCT FROM`
    is Postgres-only, so the NULL-token case is a separate portable predicate.

    **Never writes a value column.** `pool_value` / `pick_value` are pure
    functions of `(round, season)` and ownership changes neither, so an
    assignment UPDATE touching them would be a bug. `seed_pick_grid` is the
    only writer of those two.
    """
    lid, pid = str(league_id), str(pick_id)
    with engine.begin() as conn:
        def _read():
            r = conn.execute(
                select(draft_picks_table).where(
                    (draft_picks_table.c.pick_id == pid)
                    & (draft_picks_table.c.league_id == lid))
            ).fetchone()
            return dict(r._mapping) if r else None

        row = _read()
        if row is None:
            return ("not_found", None)

        token_pred = (draft_picks_table.c.assigned_at.is_(None)
                      if if_assigned_at is None
                      else draft_picks_table.c.assigned_at == if_assigned_at)
        is_traded = int(str(owner_user_id) != str(row.get("original_user_id") or ""))
        result = conn.execute(
            update(draft_picks_table)
            .where((draft_picks_table.c.pick_id == pid)
                   & (draft_picks_table.c.league_id == lid)
                   & token_pred)
            .values(owner_user_id  = str(owner_user_id),
                    owner_username = owner_username,
                    is_traded      = is_traded,
                    source         = PICK_SOURCE_USER,
                    assigned_by    = str(actor_user_id),
                    assigned_at    = _now())
        )
        if result.rowcount == 0:
            return ("stale", _read())           # re-read INSIDE the txn
        return ("ok", _read())


# ---------------------------------------------------------------------------
# draft-extensions W3 M-D — live offline pick recording (flag
# `draft.manual_picks`). Writes ONLY `recorded_picks` — never `draft_picks`,
# never `leagues.draft_status*` (INV-6 / D18, O9 survives).
# ---------------------------------------------------------------------------

def record_draft_picks(league_id: str, season: int, rows: list[dict],
                       recorded_by: str) -> dict:
    """Idempotent batch insert. Returns ``{'accepted', 'deduped', 'rejected'}``.

    Idempotency key is ``(league_id, season, overall)`` — the offline queue's
    idempotency contract, NOT `event_id` (two devices recording the same
    physical pick will not share a uuid).

    Per incoming row, against any existing row at the same
    ``(league_id, season, overall)``:

      no existing row              -> INSERT, accepted
      existing, live, SAME player  -> deduped (a replayed queue item)
      existing, live, DIFF player  -> UPDATE in place, accepted (a correction)
      existing, VOIDED, any player -> UPDATE in place, accepted, voided_at
                                       reset to NULL (a revival — the
                                       "undo the undo" path; see database.py's
                                       recorded_picks_table comment: undo is
                                       non-destructive, so re-recording a
                                       voided slot is how you reverse an undo)

    Validated per row before it can ever reach a write: `round`/`slot`/
    `overall` are positive ints, bounded against the league's stored
    assignment-grid settings when one exists (`slot_out_of_range`);
    `player_id` must resolve to a real player (`unknown_player`);
    `picking_team_id`, when given, must be a current league member
    (`not_in_league`). A batch never partially corrupts the table — every
    row is independently validated/classified before any write executes.
    """
    lid = str(league_id)
    season_i = int(season)
    now = _now()

    settings = load_pick_assignment_settings(lid) or {}
    try:
        grid_rounds = int(settings.get("rounds") or 0) or None
    except (TypeError, ValueError):
        grid_rounds = None
    grid_order = [str(u) for u in (settings.get("order") or [])]
    grid_teams = len(grid_order) or None

    try:
        member_ids = {str(m.get("user_id")) for m in load_league_members(lid)
                      if m.get("user_id")}
    except Exception as e:                       # pragma: no cover - DB optional
        log.warning("record_draft_picks: member load failed for %s: %s", lid, e)
        member_ids = set()

    accepted = 0
    deduped = 0
    rejected: list[dict] = []
    to_write: list[dict] = []
    # Keyed by overall so a later item in the SAME batch that targets the
    # same slot classifies against the item just staged, not stale DB state.
    staged: dict[int, dict] = {}

    with engine.begin() as conn:
        existing = conn.execute(
            select(recorded_picks_table).where(
                (recorded_picks_table.c.league_id == lid)
                & (recorded_picks_table.c.season == season_i))
        ).fetchall()
        by_overall = {int(r.overall): dict(r._mapping) for r in existing}

        player_cache: dict[str, bool] = {}

        for i, item in enumerate(rows or []):
            if not isinstance(item, dict):
                rejected.append({"index": i, "reason": "slot_out_of_range"})
                continue
            try:
                overall = int(item.get("overall"))
                round_ = int(item.get("round"))
                slot = int(item.get("slot"))
            except (TypeError, ValueError):
                rejected.append({"index": i, "reason": "slot_out_of_range"})
                continue
            if overall < 1 or round_ < 1 or slot < 1:
                rejected.append({"index": i, "reason": "slot_out_of_range"})
                continue
            if grid_rounds and round_ > grid_rounds:
                rejected.append({"index": i, "reason": "slot_out_of_range"})
                continue
            if grid_teams and slot > grid_teams:
                rejected.append({"index": i, "reason": "slot_out_of_range"})
                continue

            player_id = str(item.get("player_id") or "").strip()
            if not player_id:
                rejected.append({"index": i, "reason": "unknown_player"})
                continue
            if player_id not in player_cache:
                player_cache[player_id] = bool(load_players_by_ids([player_id]))
            if not player_cache[player_id]:
                rejected.append({"index": i, "reason": "unknown_player"})
                continue

            team_id = item.get("picking_team_id")
            team_id = str(team_id).strip() if team_id else None
            if team_id and member_ids and team_id not in member_ids:
                rejected.append({"index": i, "reason": "not_in_league"})
                continue

            event_id = str(item.get("event_id") or "").strip() or None

            prior = staged.get(overall) or by_overall.get(overall)
            if (prior is not None and not prior.get("voided_at")
                    and str(prior.get("player_id")) == player_id):
                deduped += 1
                continue

            accepted += 1
            row = {
                "league_id":       lid,
                "season":          season_i,
                "round":           round_,
                "slot":            slot,
                "overall":         overall,
                "picking_team_id": team_id,
                "player_id":       player_id,
                "recorded_by":     str(recorded_by),
                "event_id":        event_id,
                "recorded_at":     now,
                "voided_at":       None,
            }
            staged[overall] = row
            to_write.append(row)

        if to_write:
            if DATABASE_URL.startswith("sqlite"):
                conn.execute(text(
                    "INSERT OR REPLACE INTO recorded_picks "
                    "(league_id, season, round, slot, overall, picking_team_id, "
                    " player_id, recorded_by, event_id, recorded_at, voided_at) "
                    "VALUES (:league_id, :season, :round, :slot, :overall, "
                    " :picking_team_id, :player_id, :recorded_by, :event_id, "
                    " :recorded_at, :voided_at)"
                ), to_write)
            else:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(recorded_picks_table).values(to_write)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_recorded_pick_slot",
                    set_={
                        "round":            stmt.excluded.round,
                        "slot":             stmt.excluded.slot,
                        "picking_team_id":  stmt.excluded.picking_team_id,
                        "player_id":        stmt.excluded.player_id,
                        "recorded_by":      stmt.excluded.recorded_by,
                        "event_id":         stmt.excluded.event_id,
                        "recorded_at":      stmt.excluded.recorded_at,
                        "voided_at":        stmt.excluded.voided_at,
                    },
                )
                conn.execute(stmt)

    return {"accepted": accepted, "deduped": deduped, "rejected": rejected}


def void_recorded_pick(league_id: str, season: int, overall: int,
                       actor: str) -> dict | None:
    """Non-destructive undo: ``SET voided_at = now()``. Never DELETEs.

    Returns the voided row, or ``None`` when no live row exists at that
    ``(league_id, season, overall)`` (already voided, or never recorded).
    """
    lid = str(league_id)
    season_i = int(season)
    overall_i = int(overall)
    now = _now()
    with engine.begin() as conn:
        result = conn.execute(
            update(recorded_picks_table)
            .where((recorded_picks_table.c.league_id == lid)
                   & (recorded_picks_table.c.season == season_i)
                   & (recorded_picks_table.c.overall == overall_i)
                   & (recorded_picks_table.c.voided_at.is_(None)))
            .values(voided_at=now)
        )
        if result.rowcount == 0:
            return None
        row = conn.execute(
            select(recorded_picks_table).where(
                (recorded_picks_table.c.league_id == lid)
                & (recorded_picks_table.c.season == season_i)
                & (recorded_picks_table.c.overall == overall_i))
        ).fetchone()
    return dict(row._mapping) if row else None


def load_recorded_picks(league_id: str, season: int) -> list[dict]:
    """Live rows only (``voided_at IS NULL``), ordered by ``overall``.

    Mirrors the ``deck_suppressions.lifted_at`` ``.is_(None)`` convention
    (database.py — active row predicate).
    """
    lid = str(league_id)
    season_i = int(season)
    with engine.connect() as conn:
        rows = conn.execute(
            select(recorded_picks_table).where(
                (recorded_picks_table.c.league_id == lid)
                & (recorded_picks_table.c.season == season_i)
                & (recorded_picks_table.c.voided_at.is_(None)))
            .order_by(recorded_picks_table.c.overall)
        ).fetchall()
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


def notification_exists_with_meta(
    user_id:  str,
    type_:    str,
    meta_key: str,
    meta_val,
    scan_limit: int = 500,
) -> bool:
    """True if this user already has a `type_` row whose metadata carries
    `meta_key == meta_val`.

    THE IDEMPOTENCY GATE FOR CRON-DRIVEN INBOX ROWS, and the reason it has
    to exist: the push dispatcher's dedup lives inside _send_typed_push
    (_freq_cap_blocks → notification_events_log), and that log is only
    written when a push actually LEAVES. A push suppressed by a bucket
    toggle or quiet hours writes nothing — so an inbox row that reused the
    push's dedup would re-fire on every tick. /api/cron/realtime-tick runs
    every 15 minutes over the same pending matches, which is 96 duplicate
    rows a day for one match. The inbox needs its own gate, keyed off the
    inbox's own rows.

    Compared in Python rather than SQL: metadata is a JSON text column and
    a portable JSON predicate across SQLite and Postgres is not worth the
    coupling here. Bounded by `scan_limit` newest-first so the scan cannot
    grow with account age.

    DISMISSED ROWS STILL COUNT — deliberately. "Once written, never
    rewritten": a user who clears an expiring-match row has said they are
    done with it, and re-writing it 15 minutes later is precisely the nag
    this surface exists to avoid.
    """
    if not user_id or not type_ or not meta_key:
        return False
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(notifications_table.c.metadata_json)
                .where(notifications_table.c.user_id == user_id)
                .where(notifications_table.c.type    == type_)
                .order_by(notifications_table.c.created_at.desc())
                .limit(scan_limit)
            ).fetchall()
        target = str(meta_val)
        for r in rows:
            try:
                meta = json.loads(r[0] or "{}")
            except Exception:
                continue
            if meta_key in meta and str(meta[meta_key]) == target:
                return True
        return False
    except Exception as e:
        print(f"[notification_exists_with_meta] {user_id}/{type_} failed: {e}")
        # Fail CLOSED: on a read error, claim the row exists. A missing
        # inbox row is a lost receipt; a duplicated one on every cron tick
        # is the surface losing the user's trust. The former is recoverable
        # by the next real event, the latter is not.
        return True


def create_or_coalesce_league_join_notification(
    user_id:      str,
    league_id:    str,
    league_name:  str,
    new_username: str,
    body:         str,
) -> dict | None:
    """Write (or fold into) the `league_member_joined` inbox row for this
    user + league + UTC day. Operator decision GD-8: **one row per league
    per day** — a five-person onboarding wave should read as one event,
    because it is one.

    Folding an arrival into an existing row REWRITES it and resets it to
    unread, bumping created_at to now. That is deliberate on a
    recency-ordered list (GD-3): the row is not a stale receipt of the
    first join, it is the current state of today's wave, and it is news
    again each time it changes.

    Returns the row dict, or None on failure (never raises — an inbox
    write must not be able to fail a session_init).
    """
    if not user_id or not league_id:
        return None
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(notifications_table.c.id,
                       notifications_table.c.metadata_json)
                .where(notifications_table.c.user_id    == user_id)
                .where(notifications_table.c.type       == "league_member_joined")
                .where(notifications_table.c.created_at >= day_start)
                # A dismissed row is NOT a coalescing target — folding a new
                # arrival into it would resurrect something the user cleared.
                # A genuinely new joiner starts a fresh row instead.
                .where(notifications_table.c.dismissed_at.is_(None))
                .order_by(notifications_table.c.created_at.desc())
                .limit(50)
            ).fetchall()

        existing_id, meta = None, {}
        for r in rows:
            try:
                m = json.loads(r[1] or "{}")
            except Exception:
                continue
            if str(m.get("league_id")) == str(league_id):
                existing_id, meta = r[0], m
                break

        # Names accumulate in order of arrival, deduped, capped. The cap is
        # a storage bound, not a display one — `joined_count` stays exact so
        # the title never under-reports a wave bigger than the list.
        names: list = list(meta.get("new_usernames") or [])
        if meta.get("new_username") and meta["new_username"] not in names:
            names.insert(0, meta["new_username"])
        if new_username and new_username not in names:
            names.append(new_username)
        count = int(meta.get("joined_count") or 0)
        count = count + 1 if existing_id else 1

        if count <= 1:
            title = (f"@{new_username} joined {league_name}"
                     if league_name else f"@{new_username} joined your league")
        else:
            title = (f"{count} leaguemates joined {league_name}"
                     if league_name else f"{count} leaguemates joined your league")

        new_meta = {
            **meta,
            "league_id":     league_id,
            "league_name":   league_name,
            "new_username":  new_username,
            "new_usernames": names[:10],
            "joined_count":  count,
        }

        if existing_id is None:
            return create_notification(
                user_id=user_id, type_="league_member_joined",
                title=title, body=body, metadata=new_meta,
            )

        row = {
            "title":         title,
            "body":          body,
            "metadata_json": json.dumps(new_meta),
            "is_read":       0,
            "created_at":    _now(),
        }
        with engine.begin() as conn:
            conn.execute(
                notifications_table.update()
                .where(notifications_table.c.id == existing_id)
                .values(**row)
            )
        return {"id": existing_id, "user_id": user_id,
                "type": "league_member_joined", **row}
    except Exception as e:
        print(f"[create_or_coalesce_league_join_notification] "
              f"{user_id}/{league_id} failed: {e}")
        return None


def dismiss_all_notifications(user_id: str) -> int:
    """Server-side "Clear all" (operator decision GD-4). Stamps
    `dismissed_at` on every live row for the user and marks them read.
    Returns the number of rows affected.

    Before this, "Clear all" was a lie on both clients in two different
    ways: mobile emptied a zustand store and the rows re-hydrated on the
    next open, and web hid ids in localStorage so the same account cleared
    on a phone was still full on a laptop. One server-side dismissal
    replaces both — it does not add a third mechanism.
    """
    if not user_id:
        return 0
    try:
        with engine.begin() as conn:
            res = conn.execute(
                notifications_table.update()
                .where(notifications_table.c.user_id == user_id)
                .where(notifications_table.c.dismissed_at.is_(None))
                .values(dismissed_at=_now(), is_read=1)
            )
        return int(res.rowcount or 0)
    except Exception as e:
        print(f"[dismiss_all_notifications] {user_id} failed: {e}")
        return 0


def get_notifications(user_id: str, read_limit: int = 20) -> list[dict]:
    """
    Return notifications for a user, newest first.
    Always returns ALL unread + the most recent `read_limit` read notifications.

    Dismissed rows (`dismissed_at IS NOT NULL`) are excluded from both legs —
    that is what makes "Clear all" true rather than cosmetic (GD-4). The rows
    are retained, not deleted: they are the only history this surface has.
    """
    with engine.connect() as conn:
        # All unread
        unread_rows = conn.execute(
            select(notifications_table)
            .where(
                and_(
                    notifications_table.c.user_id  == user_id,
                    notifications_table.c.is_read  == 0,
                    notifications_table.c.dismissed_at.is_(None),
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
                    notifications_table.c.dismissed_at.is_(None),
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

def load_user_cross_league_exposure(
    user_id: str,
    league_ids: list[str] | None = None,
) -> list[dict]:
    """
    Aggregate this user's player exposure across every league they own a
    roster in.  Joins league_members (to get the user's own rosters) with
    leagues (for human-readable league names) and players (for name/position).

    league_ids (FB-48): when provided, restrict aggregation to these leagues.
    Sleeper mints a NEW league_id every season, so league_members accumulates
    last season's instance of each league alongside the current one — without
    this filter every carried-over player counts twice. Clients pass their
    current-season league list (the same one the switcher shows).

    Returns a list of dicts sorted by exposure count desc:
        [{player_id, name, pos, exposure, total_leagues,
          leagues: [{league_id, league_name}, ...],
          league_names: [...]}, ...]

    total_leagues is identical on every row — it's the number of leagues
    this user has a roster in.  exposure is the subset where the player
    is on this user's team.

    `leagues` is the authoritative per-league exposure list — it pairs
    each league_id with its display name so the client can disambiguate
    identically-named leagues (Sleeper allows duplicate league names
    across a user's account; two same-named leagues otherwise render as
    indistinguishable chips and look like double-counting).
    `league_names` is preserved for any existing consumers.
    """
    with engine.connect() as conn:
        # Pull every (league_id, roster_data) row where this user owns the team.
        member_q = select(
            league_members_table.c.league_id,
            league_members_table.c.roster_data,
        ).where(league_members_table.c.user_id == user_id)
        if league_ids:
            member_q = member_q.where(
                league_members_table.c.league_id.in_([str(x) for x in league_ids])
            )
        member_rows = conn.execute(member_q).fetchall()

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
        # Sort leagues by display name (stable), tie-break on league_id so
        # same-named leagues have a deterministic order.
        leagues_list = sorted(
            (
                {"league_id": lid, "league_name": league_name_map.get(lid, lid)}
                for lid in lid_set
            ),
            key=lambda x: (x["league_name"].lower(), x["league_id"]),
        )
        result.append({
            "player_id":     pid,
            "name":          meta.get("name") or pid,
            "pos":           meta.get("pos") or "",
            "exposure":      len(lid_set),
            "total_leagues": total_leagues,
            "leagues":       leagues_list,
            "league_names":  [lg["league_name"] for lg in leagues_list],
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


# ---------------------------------------------------------------------------
# player_value_history accessors (backlog #57 / #17)
# ---------------------------------------------------------------------------

def upsert_roster_snapshots(rows: list[dict]) -> dict:
    """One league's snapshot batch, one transaction (ADR-011).

    PRECEDENCE, NOT RECENCY. 'weekly' rows are server-fetched (every team,
    orphans included); 'sync' rows are client-posted (ownerless rosters
    already dropped). So:

      weekly   -> full update, always. Never hash-suppressed: team_value
                  moves weekly even when the roster does not, and a
                  hash-suppressed grid puts holes in exactly the chart
                  YR-2 exists to stabilise.
      sync     -> nothing when a 'weekly' row already holds the period
                  (recency would silently delete the week's orphan teams
                  and break YR-6, invisibly). Over an earlier 'sync' row:
                  update when the hash changed, skip when it did not (the
                  hash's job is suppressing EXTRA intra-week sync writes).
      backfill -> insert-only; never overwrites any observation.

    Returns counters {'inserted','updated','skipped_precedence',
    'skipped_unchanged'} so tick responses and tests can see what happened.
    """
    stats = {"inserted": 0, "updated": 0,
             "skipped_precedence": 0, "skipped_unchanged": 0}
    if not rows:
        return stats
    t = league_roster_history_table
    with engine.begin() as conn:
        for row in rows:
            existing = conn.execute(
                select(t.c.id, t.c.source, t.c.roster_hash).where(
                    (t.c.league_id      == row["league_id"]) &
                    (t.c.team_key       == row["team_key"]) &
                    (t.c.scoring_format == row["scoring_format"]) &
                    (t.c.period_key     == row["period_key"])
                )
            ).fetchone()
            if existing is None:
                conn.execute(insert(t).values(**row))
                stats["inserted"] += 1
                continue
            src = row.get("source")
            if src == "weekly":
                conn.execute(t.update().where(t.c.id == existing.id).values(**row))
                stats["updated"] += 1
            elif src == "sync":
                if existing.source == "weekly":
                    stats["skipped_precedence"] += 1
                elif existing.roster_hash == row.get("roster_hash"):
                    stats["skipped_unchanged"] += 1
                else:
                    conn.execute(t.update().where(t.c.id == existing.id).values(**row))
                    stats["updated"] += 1
            else:  # backfill — never overwrite a real observation
                stats["skipped_precedence"] += 1
    return stats


def load_prev_roster_hashes(league_id: str, scoring_format: str,
                            before_period: str) -> dict[str, str]:
    """Latest roster_hash per team_key from any period BEFORE
    `before_period`, for changed_from_prev. period_key labels
    ('2026-W33') compare correctly as strings — zero-padded weeks and the
    ISO week-numbering year keep lexicographic order == chronological
    order, including the December boundary ('2026-W53' < '2027-W01')."""
    t = league_roster_history_table
    out: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(t.c.team_key, t.c.period_key, t.c.roster_hash)
                .where(
                    (t.c.league_id      == league_id) &
                    (t.c.scoring_format == scoring_format) &
                    (t.c.period_key     <  before_period)
                )
                .order_by(t.c.team_key, t.c.period_key.desc())
            ).fetchall()
        for r in rows:
            out.setdefault(r.team_key, r.roster_hash)   # first = latest per team
    except Exception as e:
        print(f"[load_prev_roster_hashes] {league_id} failed: {e}")
    return out


def restamp_roster_history_owner(league_id: str, team_key: str,
                                 owner_user_id: str) -> int:
    """Resolve a team's history to a newly-linked manager (ADR-011).

    Not a violation of append-only: the fact ("team T held roster R in
    period P") never changes; owner_user_id is a late-resolving pointer to
    who we now know was behind T. This is what makes the late-joiner growth
    claim (plan §5.3) true on ESPN/MFL — a manager who links in November
    inherits their team's full season on day one. Idempotent."""
    if not league_id or not team_key or not owner_user_id:
        return 0
    t = league_roster_history_table
    try:
        with engine.begin() as conn:
            res = conn.execute(
                t.update()
                .where((t.c.league_id == league_id) & (t.c.team_key == team_key))
                .values(owner_user_id=owner_user_id)
            )
        return int(res.rowcount or 0)
    except Exception as e:
        print(f"[restamp_roster_history_owner] {league_id}/{team_key} failed: {e}")
        return 0


def latest_value_snapshot_date(scoring_format: str,
                               on_or_before: str) -> str | None:
    """Newest player_value_history snapshot_date <= on_or_before for a
    format (the load_value_snapshot_baseline nearest-<= idiom) — recorded
    on each roster snapshot as value_basis_date so the December read can
    grey unjoinable weeks with a reason instead of a guess."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(func.max(player_value_history_table.c.snapshot_date))
                .where(
                    (player_value_history_table.c.scoring_format == scoring_format) &
                    (player_value_history_table.c.snapshot_date <= on_or_before)
                )
            ).fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        print(f"[latest_value_snapshot_date] {scoring_format} failed: {e}")
        return None


def upsert_board_snapshots(rows: list[dict]) -> dict:
    """league_board_history batch upsert (C5/C6). Same transaction-per-batch
    shape as upsert_roster_snapshots; precedence is simpler because every
    trigger reads the SAME local member_rankings rows — 'sync' and 'weekly'
    carry identical content, so either may refresh the period. 'backfill'
    is insert-only."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    if not rows:
        return stats
    t = league_board_history_table
    with engine.begin() as conn:
        for row in rows:
            existing = conn.execute(
                select(t.c.id).where(
                    (t.c.user_id        == row["user_id"]) &
                    (t.c.league_id      == row["league_id"]) &
                    (t.c.scoring_format == row["scoring_format"]) &
                    (t.c.period_key     == row["period_key"])
                )
            ).fetchone()
            if existing is None:
                conn.execute(insert(t).values(**row))
                stats["inserted"] += 1
            elif row.get("source") == "backfill":
                stats["skipped"] += 1
            else:
                conn.execute(t.update().where(t.c.id == existing.id).values(**row))
                stats["updated"] += 1
    return stats


def load_member_boards_for_league(league_id: str) -> list[dict]:
    """Every member's full board for a league, grouped:
    [{user_id, scoring_format, elos: {pid: elo}, board_updated_at}].
    Legacy NULL scoring_format rows count as '1qb_ppr', mirroring
    load_member_rankings."""
    t = member_rankings_table
    grouped: dict[tuple, dict] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(t.c.user_id, t.c.scoring_format, t.c.player_id,
                       t.c.elo, t.c.updated_at)
                .where(t.c.league_id == league_id)
            ).fetchall()
        for r in rows:
            fmt = r.scoring_format or DEFAULT_SCORING
            key = (str(r.user_id), fmt)
            g = grouped.setdefault(key, {"user_id": str(r.user_id),
                                         "scoring_format": fmt,
                                         "elos": {},
                                         "board_updated_at": None})
            g["elos"][str(r.player_id)] = round(float(r.elo), 1)
            if r.updated_at and (g["board_updated_at"] is None
                                 or r.updated_at > g["board_updated_at"]):
                g["board_updated_at"] = r.updated_at
    except Exception as e:
        print(f"[load_member_boards_for_league] {league_id} failed: {e}")
    return list(grouped.values())


def load_history_sweep_leagues(period_key: str) -> list[dict]:
    """Sweep work-list for the weekly roster snapshot, STALEST-FIRST:
    leagues with no 'weekly' row for the current period first (never swept
    or missed), then by how recently they got one. Each entry carries what
    the per-platform fetch adapters need."""
    lt, ht = leagues_table, league_roster_history_table
    try:
        with engine.connect() as conn:
            leagues = conn.execute(
                select(lt.c.sleeper_league_id, lt.c.platform,
                       lt.c.default_scoring, lt.c.user_id,
                       lt.c.espn_auth, lt.c.espn_season, lt.c.espn_my_team_id,
                       lt.c.platform_auth, lt.c.platform_season,
                       lt.c.platform_host, lt.c.platform_my_team)
            ).fetchall()
            done = {
                r.league_id for r in conn.execute(
                    select(ht.c.league_id).distinct()
                    .where((ht.c.period_key == period_key) &
                           (ht.c.source == "weekly"))
                ).fetchall()
            }
        out = []
        for r in leagues:
            m = dict(r._mapping)
            m["league_id"] = m.pop("sleeper_league_id")
            m["platform"] = m.get("platform") or "sleeper"
            m["has_current_weekly"] = m["league_id"] in done
            out.append(m)
        out.sort(key=lambda m: m["has_current_weekly"])   # missing first
        return out
    except Exception as e:
        print(f"[load_history_sweep_leagues] failed: {e}")
        return []


def record_value_snapshots(rows: list[dict]) -> int:
    """
    Idempotent daily upsert of consensus value snapshots. Each row must carry
    player_id, scoring_format, consensus_elo, consensus_value, search_rank,
    adp, snapshot_date. Re-running for the same (player, format, date)
    overwrites rather than duplicating, so a same-day cron retry is safe.

    Returns the number of rows written.

    Dialect-aware upsert mirroring upsert_league_members: INSERT OR REPLACE
    on SQLite, ON CONFLICT DO UPDATE on PostgreSQL, both keyed on the
    uq_value_snapshot constraint.
    """
    if not rows:
        return 0
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text(
                "INSERT OR REPLACE INTO player_value_history "
                "(player_id, scoring_format, consensus_elo, consensus_value, "
                " search_rank, adp, snapshot_date) "
                "VALUES (:player_id, :scoring_format, :consensus_elo, "
                ":consensus_value, :search_rank, :adp, :snapshot_date)"
            ), rows)
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(player_value_history_table).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_value_snapshot",
                set_={
                    "consensus_elo":   stmt.excluded.consensus_elo,
                    "consensus_value": stmt.excluded.consensus_value,
                    "search_rank":     stmt.excluded.search_rank,
                    "adp":             stmt.excluded.adp,
                },
            )
            conn.execute(stmt)
    return len(rows)


def load_value_history(
    player_id: str,
    scoring_format: str = DEFAULT_SCORING,
    since_days: int = 90,
) -> list[dict]:
    """
    Return one player's consensus snapshots for `scoring_format` within the
    last `since_days` days, OLDEST first (matches load_elo_history ordering so
    callers can zip the two series for the value chart).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)
              ).strftime("%Y-%m-%d")
    with engine.connect() as conn:
        rows = conn.execute(
            select(player_value_history_table)
            .where(player_value_history_table.c.player_id      == str(player_id))
            .where(player_value_history_table.c.scoring_format == scoring_format)
            .where(player_value_history_table.c.snapshot_date  >= cutoff)
            .order_by(player_value_history_table.c.snapshot_date.asc())
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def load_value_snapshot_baseline(
    scoring_format: str = DEFAULT_SCORING,
    days: int = 30,
) -> dict[str, float]:
    """
    Consensus 30d-trend BASELINE (FB4-61 tile stats): { player_id:
    consensus_elo } for the OLDEST snapshot_date within the trailing `days`
    window, excluding today (UTC) — a same-day snapshot is no trend baseline.

    Returns {} while history hasn't accrued yet (callers serve the trend as
    null and clients omit the segment). Mirrors compute_risers_fallers'
    earliest-in-window semantics, so early-life deltas span however much
    history exists rather than a strict 30 days.
    """
    now    = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    today  = now.strftime("%Y-%m-%d")
    with engine.connect() as conn:
        baseline_date = conn.execute(
            select(func.min(player_value_history_table.c.snapshot_date))
            .where(player_value_history_table.c.scoring_format == scoring_format)
            .where(player_value_history_table.c.snapshot_date  >= cutoff)
            .where(player_value_history_table.c.snapshot_date  <  today)
        ).scalar()
        if not baseline_date:
            return {}
        rows = conn.execute(
            select(
                player_value_history_table.c.player_id,
                player_value_history_table.c.consensus_elo,
            )
            .where(player_value_history_table.c.scoring_format == scoring_format)
            .where(player_value_history_table.c.snapshot_date  == baseline_date)
        ).fetchall()
    return {r.player_id: r.consensus_elo for r in rows}


def load_value_movers_window(
    scoring_format: str = DEFAULT_SCORING,
    days: int = 30,
) -> tuple[str | None, dict[str, float], dict[str, float]]:
    """
    Market-movers read (#243 "Market pulse" strip): consensus_value at the
    two ends of the trailing `days` window, for every player with rows.

    Returns (as_of, now_values, then_values):
      as_of       — the LATEST snapshot_date for the format (None: no history)
      now_values  — {player_id: consensus_value} at as_of
      then_values — {player_id: consensus_value} at the OLDEST snapshot_date
                    within [as_of − days, as_of), strictly before as_of — a
                    single accrued day yields no baseline (never a fake 0%).

    Thin history is empty-safe: no rows → (None, {}, {}); one distinct day →
    (as_of, now_values, {}). Mirrors load_value_snapshot_baseline's
    earliest-in-window semantics so early-life deltas span however much
    history exists rather than a strict `days`.
    """
    with engine.connect() as conn:
        as_of = conn.execute(
            select(func.max(player_value_history_table.c.snapshot_date))
            .where(player_value_history_table.c.scoring_format == scoring_format)
        ).scalar()
        if not as_of:
            return None, {}, {}
        cutoff = (datetime.strptime(as_of, "%Y-%m-%d")
                  - timedelta(days=days)).strftime("%Y-%m-%d")
        baseline_date = conn.execute(
            select(func.min(player_value_history_table.c.snapshot_date))
            .where(player_value_history_table.c.scoring_format == scoring_format)
            .where(player_value_history_table.c.snapshot_date  >= cutoff)
            .where(player_value_history_table.c.snapshot_date  <  as_of)
        ).scalar()

        def _values_at(day: str) -> dict[str, float]:
            rows = conn.execute(
                select(
                    player_value_history_table.c.player_id,
                    player_value_history_table.c.consensus_value,
                )
                .where(player_value_history_table.c.scoring_format == scoring_format)
                .where(player_value_history_table.c.snapshot_date  == day)
                .where(player_value_history_table.c.consensus_value.isnot(None))
            ).fetchall()
            return {r.player_id: r.consensus_value for r in rows}

        now_values  = _values_at(as_of)
        then_values = _values_at(baseline_date) if baseline_date else {}
    return as_of, now_values, then_values


def load_value_extremes(
    player_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict | None:
    """
    All-time (since tracking began) high/low consensus value for a player,
    with the dates they occurred and the earliest snapshot date
    (`tracking_since`). Returns None if no snapshots exist yet.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                player_value_history_table.c.consensus_value,
                player_value_history_table.c.snapshot_date,
            )
            .where(player_value_history_table.c.player_id      == str(player_id))
            .where(player_value_history_table.c.scoring_format == scoring_format)
            .where(player_value_history_table.c.consensus_value.isnot(None))
            .order_by(player_value_history_table.c.snapshot_date.asc())
        ).fetchall()
    if not rows:
        return None
    hi = max(rows, key=lambda r: r.consensus_value)
    lo = min(rows, key=lambda r: r.consensus_value)
    return {
        "high":           {"value": hi.consensus_value, "date": hi.snapshot_date},
        "low":            {"value": lo.consensus_value, "date": lo.snapshot_date},
        "tracking_since": rows[0].snapshot_date,
    }


def value_snapshot_formats_for(snapshot_date: str) -> set[str]:
    """Scoring formats that already have consensus snapshot rows for the
    given UTC date. Used by the hourly-tick fallback guard to decide
    whether today's daily value snapshot still needs writing."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(player_value_history_table.c.scoring_format)
            .where(player_value_history_table.c.snapshot_date == snapshot_date)
            .distinct()
        ).fetchall()
    return {r.scoring_format for r in rows}


# In-process cache for load_community_elo_for_league.
# Keyed on (league_id, scoring_format) — exclude_user_id is NOT part of the key
# because the same leaguemate snapshot is shared across callers in the same
# process (Trends tab hits this repeatedly for different users in the same league).
# Invalidated by upsert_member_rankings so the next Trends call gets fresh data.
_COMMUNITY_ELO_CACHE: dict = {}   # (league_id, scoring_format) → (timestamp_str, result)
_COMMUNITY_ELO_TTL = 300          # 5 minutes


def load_community_elo_for_league(
    league_id: str,
    exclude_user_id: str,
    scoring_format: str = DEFAULT_SCORING,
) -> dict:
    """
    Thin alias around `load_member_rankings` — kept here so the Trends
    service has a dedicated, clearly-named dependency separate from the
    trade engine's usage of the same data.

    Returns the same shape as load_member_rankings(). Results are cached for
    up to 5 minutes and invalidated on each upsert_member_rankings call.
    """
    cache_key = (league_id, scoring_format)
    entry = _COMMUNITY_ELO_CACHE.get(cache_key)
    if entry is not None:
        ts, result = entry
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(ts)).total_seconds()
        if age < _COMMUNITY_ELO_TTL:
            return result

    result = load_member_rankings(
        league_id       = league_id,
        exclude_user_id = exclude_user_id,
        scoring_format  = scoring_format,
    )
    _COMMUNITY_ELO_CACHE[cache_key] = (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), result)
    return result


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


# ---------------------------------------------------------------------------
# Sleeper write credentials ("Send in Sleeper") — see sleeper_credentials_table
# ---------------------------------------------------------------------------
#
# These store/read the Fernet-encrypted Sleeper JWT. They take the ciphertext
# already produced by backend/sleeper_write.encrypt_token — this module never
# sees the plaintext token. Unlike save_device_token, write failures RAISE so
# the caller can surface a real error (a silently-dropped credential would look
# "linked" but never work).

def upsert_sleeper_credential(user_id: str, sleeper_user_id: str | None,
                              token_encrypted: str, expires_at: str | None) -> None:
    """Insert or replace the Sleeper link for a user (one row per user_id)."""
    if not user_id or not token_encrypted:
        raise ValueError("user_id and token_encrypted are required")
    now = _now()
    payload = {
        "user_id":         user_id,
        "sleeper_user_id": sleeper_user_id,
        "token_encrypted": token_encrypted,
        "expires_at":      expires_at,
        "created_at":      now,
        "updated_at":      now,
    }
    with engine.begin() as conn:
        # keep created_at stable across re-links
        existing = conn.execute(
            select(sleeper_credentials_table.c.created_at)
            .where(sleeper_credentials_table.c.user_id == user_id)
        ).fetchone()
        if existing and existing[0]:
            payload["created_at"] = existing[0]
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text(
                "INSERT OR REPLACE INTO sleeper_credentials "
                "(user_id, sleeper_user_id, token_encrypted, expires_at, created_at, updated_at) "
                "VALUES (:user_id, :sleeper_user_id, :token_encrypted, :expires_at, :created_at, :updated_at)"
            ), payload)
        else:
            conn.execute(text(
                "INSERT INTO sleeper_credentials "
                "(user_id, sleeper_user_id, token_encrypted, expires_at, created_at, updated_at) "
                "VALUES (:user_id, :sleeper_user_id, :token_encrypted, :expires_at, :created_at, :updated_at) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "sleeper_user_id = EXCLUDED.sleeper_user_id, "
                "token_encrypted = EXCLUDED.token_encrypted, "
                "expires_at = EXCLUDED.expires_at, "
                "updated_at = EXCLUDED.updated_at"
            ), payload)


def get_sleeper_credential(user_id: str) -> dict | None:
    """Return {sleeper_user_id, token_encrypted, expires_at, created_at,
    updated_at} for a user, or None if they haven't linked Sleeper."""
    if not user_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(
                sleeper_credentials_table.c.sleeper_user_id,
                sleeper_credentials_table.c.token_encrypted,
                sleeper_credentials_table.c.expires_at,
                sleeper_credentials_table.c.created_at,
                sleeper_credentials_table.c.updated_at,
            ).where(sleeper_credentials_table.c.user_id == user_id)
        ).fetchone()
    if not row:
        return None
    return {
        "sleeper_user_id": row.sleeper_user_id,
        "token_encrypted": row.token_encrypted,
        "expires_at":      row.expires_at,
        "created_at":      row.created_at,
        "updated_at":      row.updated_at,
    }


def delete_sleeper_credential(user_id: str) -> None:
    """Remove a user's stored Sleeper token (disconnect / dead-token cleanup)."""
    if not user_id:
        return
    with engine.begin() as conn:
        conn.execute(
            delete(sleeper_credentials_table)
            .where(sleeper_credentials_table.c.user_id == user_id)
        )


# ---------------------------------------------------------------------------
# ESPN league linking (#101, flag `espn.link`) — credentials + league/member
# persistence. Rosters are stored as CROSSWALKED SLEEPER player ids (the
# app's working key); ESPN-native ids never leave backend/espn_service.py.
# ---------------------------------------------------------------------------

def upsert_espn_credential(user_id: str, swid: str | None,
                           espn_s2_encrypted: str,
                           expires_hint_at: str | None = None,
                           verified_at: str | None = None) -> None:
    """Insert or replace a user's ESPN cookie pair (one row per user_id).
    Mirrors upsert_sleeper_credential — created_at survives re-links.

    verified_at (credential-honesty fix, 2026-08-12): ISO timestamp of the
    live authenticated ESPN read that proved THIS pair works. Callers that
    just verified pass it; a store without it leaves the row unproven and
    GET /api/espn/link reports it as not connected. A re-store deliberately
    REPLACES the previous value (each stored pair carries its own proof —
    an old pair's verification never vouches for a new one)."""
    if not user_id or not espn_s2_encrypted:
        raise ValueError("user_id and espn_s2_encrypted are required")
    now = _now()
    payload = {
        "user_id":           user_id,
        "swid":              swid,
        "espn_s2_encrypted": espn_s2_encrypted,
        "expires_hint_at":   expires_hint_at,
        "verified_at":       verified_at,
        "created_at":        now,
        "updated_at":        now,
    }
    with engine.begin() as conn:
        existing = conn.execute(
            select(espn_credentials_table.c.created_at)
            .where(espn_credentials_table.c.user_id == user_id)
        ).fetchone()
        if existing and existing[0]:
            payload["created_at"] = existing[0]
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text(
                "INSERT OR REPLACE INTO espn_credentials "
                "(user_id, swid, espn_s2_encrypted, expires_hint_at, verified_at, created_at, updated_at) "
                "VALUES (:user_id, :swid, :espn_s2_encrypted, :expires_hint_at, :verified_at, :created_at, :updated_at)"
            ), payload)
        else:
            conn.execute(text(
                "INSERT INTO espn_credentials "
                "(user_id, swid, espn_s2_encrypted, expires_hint_at, verified_at, created_at, updated_at) "
                "VALUES (:user_id, :swid, :espn_s2_encrypted, :expires_hint_at, :verified_at, :created_at, :updated_at) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "swid = EXCLUDED.swid, "
                "espn_s2_encrypted = EXCLUDED.espn_s2_encrypted, "
                "expires_hint_at = EXCLUDED.expires_hint_at, "
                "verified_at = EXCLUDED.verified_at, "
                "updated_at = EXCLUDED.updated_at"
            ), payload)


def get_espn_credential(user_id: str) -> dict | None:
    """Return {swid, espn_s2_encrypted, expires_hint_at, verified_at,
    created_at, updated_at} for a user, or None if they haven't linked
    ESPN cookies."""
    if not user_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(espn_credentials_table)
            .where(espn_credentials_table.c.user_id == user_id)
        ).fetchone()
    if not row:
        return None
    d = dict(row._mapping)
    d.pop("user_id", None)
    return d


def delete_espn_credential(user_id: str) -> None:
    """Remove a user's stored ESPN cookies (disconnect / dead-cookie cleanup)."""
    if not user_id:
        return
    with engine.begin() as conn:
        conn.execute(
            delete(espn_credentials_table)
            .where(espn_credentials_table.c.user_id == user_id)
        )


def clear_espn_credential_verification(user_id: str) -> None:
    """#321 identity binding (2026-08-16): null a user's `verified_at` stamp
    WITHOUT deleting the row — the encrypted pair stays for forensics, and
    the GET honesty gate already reads a stamp-less row as not connected, so
    the user is routed through the verifying, identity-bound sign-in.

    Called when a stored credential's SWID conclusively fails the membership
    assertion (team-binding step / re-sync) — the stamp was lying about
    identity, so it must stop vouching. No-op when nothing is stored."""
    if not user_id:
        return
    with engine.begin() as conn:
        conn.execute(
            espn_credentials_table.update()
            .where(espn_credentials_table.c.user_id == user_id)
            .values(verified_at=None, updated_at=_now())
        )


# ---------------------------------------------------------------------------
# MFL authenticated linking (#177, flag `mfl.auth_link`) — cookie credentials.
# These take the ciphertext already produced by sleeper_write.encrypt_token;
# this module never sees the plaintext cookie (and never the password at all).
# ---------------------------------------------------------------------------

def upsert_mfl_credential(user_id: str, mfl_username: str | None,
                          cookie_encrypted: str, year: int | None = None) -> None:
    """Insert or replace a user's MFL session cookie (one row per user_id).
    Mirrors upsert_espn_credential — created_at survives re-links."""
    if not user_id or not cookie_encrypted:
        raise ValueError("user_id and cookie_encrypted are required")
    now = _now()
    payload = {
        "user_id":          user_id,
        "mfl_username":     mfl_username,
        "cookie_encrypted": cookie_encrypted,
        "year":             year,
        "created_at":       now,
        "updated_at":       now,
    }
    with engine.begin() as conn:
        existing = conn.execute(
            select(mfl_credentials_table.c.created_at)
            .where(mfl_credentials_table.c.user_id == user_id)
        ).fetchone()
        if existing and existing[0]:
            payload["created_at"] = existing[0]
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text(
                "INSERT OR REPLACE INTO mfl_credentials "
                "(user_id, mfl_username, cookie_encrypted, year, created_at, updated_at) "
                "VALUES (:user_id, :mfl_username, :cookie_encrypted, :year, :created_at, :updated_at)"
            ), payload)
        else:
            conn.execute(text(
                "INSERT INTO mfl_credentials "
                "(user_id, mfl_username, cookie_encrypted, year, created_at, updated_at) "
                "VALUES (:user_id, :mfl_username, :cookie_encrypted, :year, :created_at, :updated_at) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "mfl_username = EXCLUDED.mfl_username, "
                "cookie_encrypted = EXCLUDED.cookie_encrypted, "
                "year = EXCLUDED.year, "
                "updated_at = EXCLUDED.updated_at"
            ), payload)


def get_mfl_credential(user_id: str) -> dict | None:
    """Return {mfl_username, cookie_encrypted, year, created_at, updated_at}
    for a user, or None if they haven't signed in with MFL."""
    if not user_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(mfl_credentials_table)
            .where(mfl_credentials_table.c.user_id == user_id)
        ).fetchone()
    if not row:
        return None
    d = dict(row._mapping)
    d.pop("user_id", None)
    return d


def delete_mfl_credential(user_id: str) -> None:
    """Remove a user's stored MFL cookie (disconnect / dead-cookie cleanup)."""
    if not user_id:
        return
    with engine.begin() as conn:
        conn.execute(
            delete(mfl_credentials_table)
            .where(mfl_credentials_table.c.user_id == user_id)
        )


def upsert_espn_league(league_id: str, user_id: str, name: str,
                       espn_season: int, espn_auth: str,
                       espn_my_team_id: int, total_rosters: int | None) -> None:
    """Insert or refresh an ESPN-imported league row (platform='espn').

    Same importer-owner keying rules as upsert_league; re-links refresh the
    league metadata AND the ESPN binding columns (season / auth mode / the
    linking user's team id). `league_id` is the numeric ESPN league id
    stored in the sleeper_league_id PK column (see leagues_table comments).
    """
    now = _now()
    row = {
        "sleeper_league_id": str(league_id),
        "user_id":           user_id,
        "name":              name,
        "season":            str(espn_season),
        "roster_data":       "[]",
        "opponent_data":     "[]",
        "created_at":        now,
        "updated_at":        now,
        "platform":          "espn",
        "espn_season":       int(espn_season),
        "espn_auth":         espn_auth,
        "espn_my_team_id":   int(espn_my_team_id),
        "total_rosters":     total_rosters,
    }
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        stmt = dialect_insert(leagues_table).values(row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sleeper_league_id"],
            set_={
                "name":            stmt.excluded.name,
                "updated_at":      stmt.excluded.updated_at,
                "platform":        stmt.excluded.platform,
                "espn_season":     stmt.excluded.espn_season,
                "espn_auth":       stmt.excluded.espn_auth,
                "espn_my_team_id": stmt.excluded.espn_my_team_id,
                "total_rosters":   stmt.excluded.total_rosters,
            },
        )
        conn.execute(stmt)


def get_espn_league(league_id: str) -> dict | None:
    """Return the leagues row for an ESPN-imported league, or None when the
    id is unknown or the row isn't platform='espn'."""
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
        ).fetchone()
    if not row or (row._mapping.get("platform") or "sleeper") != "espn":
        return None
    return dict(row._mapping)


def replace_espn_league_members(league_id: str, members: list[dict]) -> None:
    """Replace the full membership snapshot for an ESPN league.

    members: [{user_id, username, display_name, player_ids}] where user_id
    is the linking user's real FTF id for their own team and a synthetic
    `espn:` id for counterparties (never routable to push/notifications —
    same class as unlinked Sleeper members). Delete-then-insert (one
    transaction) so teams that vanish from ESPN don't leave stale rows —
    unlike Sleeper leagues, ESPN membership has no other writer to
    reconcile against.
    """
    now = _now()
    rows = [
        {
            "league_id":    str(league_id),
            "user_id":      str(m.get("user_id", "")),
            "username":     m.get("username", ""),
            "display_name": m.get("display_name") or m.get("username", ""),
            "roster_data":  json.dumps(m.get("player_ids", [])),
            "updated_at":   now,
        }
        for m in members
        if m.get("user_id")
    ]
    with engine.begin() as conn:
        conn.execute(
            delete(league_members_table)
            .where(league_members_table.c.league_id == str(league_id))
        )
        if rows:
            conn.execute(insert(league_members_table), rows)


def load_espn_leagues_for_user(user_id: str) -> list[dict]:
    """Return every ESPN-imported league this user is bound to, with the
    full membership snapshot (rosters already in Sleeper player-id space) so
    the mobile client can build a standard /api/session/init payload.
    """
    if not user_id:
        return []
    with engine.connect() as conn:
        member_rows = conn.execute(
            select(league_members_table.c.league_id).where(
                league_members_table.c.user_id == user_id
            )
        ).fetchall()
        league_ids = sorted({r.league_id for r in member_rows})
        if not league_ids:
            return []
        league_rows = conn.execute(
            select(leagues_table).where(
                (leagues_table.c.sleeper_league_id.in_(league_ids)) &
                (leagues_table.c.platform == "espn")
            )
        ).fetchall()
    out = []
    for lg in league_rows:
        m = dict(lg._mapping)
        out.append({
            "league_id":      m["sleeper_league_id"],
            "name":           m.get("name"),
            "platform":       "espn",
            "season":         m.get("espn_season"),
            "espn_auth":      m.get("espn_auth"),
            "my_team_id":     m.get("espn_my_team_id"),
            "total_rosters":  m.get("total_rosters"),
            "members":        load_league_members(m["sleeper_league_id"]),
        })
    return out


# ---------------------------------------------------------------------------
# Generic multi-platform league linking (MFL / Fleaflicker; flags
# `mfl.link` / `fleaflicker.link`). Plan:
# docs/plans/multi-platform-linking-plan-2026-07-17.md. Same storage seam as
# ESPN (leagues row keyed by the platform-native id in the PK column, members
# in league_members with CROSSWALKED SLEEPER player ids), but using the
# generic platform_* columns so one code path serves every non-ESPN platform.
# Reuses replace_espn_league_members (already platform-agnostic — it only
# touches league_members). Phase 1 is public/zero-auth: no credentials table.
# ---------------------------------------------------------------------------

def upsert_platform_league(league_id: str, user_id: str, name: str, platform: str,
                           season: int, auth: str, my_team: str,
                           total_rosters: int | None, host: str | None = None,
                           future_picks: list | None = None) -> None:
    """Insert or refresh a non-ESPN linked league row (platform='mfl' |
    'fleaflicker'). Idempotent on the PK (platform-native league id). Refreshes
    the league metadata AND the generic binding columns (season / host / auth /
    the linking user's team key) on re-link. `future_picks` is stored raw as a
    JSON list (MFL/Fleaflicker) for the pick-inclusive follow-up; it is NOT
    read by the trade engine today."""
    now = _now()
    row = {
        "sleeper_league_id": str(league_id),
        "user_id":           user_id,
        "name":              name,
        "season":            str(season),
        "roster_data":       "[]",
        "opponent_data":     "[]",
        "created_at":        now,
        "updated_at":        now,
        "platform":          platform,
        "platform_season":   int(season),
        "platform_host":     host,
        "platform_auth":     auth,
        "platform_my_team":  str(my_team),
        "platform_future_picks": json.dumps(future_picks or []),
        "total_rosters":     total_rosters,
    }
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        stmt = dialect_insert(leagues_table).values(row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sleeper_league_id"],
            set_={
                "name":              stmt.excluded.name,
                "updated_at":        stmt.excluded.updated_at,
                "platform":          stmt.excluded.platform,
                "platform_season":   stmt.excluded.platform_season,
                "platform_host":     stmt.excluded.platform_host,
                "platform_auth":     stmt.excluded.platform_auth,
                "platform_my_team":  stmt.excluded.platform_my_team,
                "platform_future_picks": stmt.excluded.platform_future_picks,
                "total_rosters":     stmt.excluded.total_rosters,
            },
        )
        conn.execute(stmt)


def set_platform_future_picks(league_id: str, future_picks: list) -> None:
    """Refresh ONLY `leagues.platform_future_picks` for a linked league.

    #207/#228 MFL parity: the snapshot used to be written once, at link/import
    (`upsert_platform_league`), so a league linked before its rookie draft
    kept that season's picks forever. `server._refresh_mfl_future_picks`
    re-fetches MFL's `futureDraftPicks` export on the draft-status refresh
    cadence and writes it back through here. Deliberately narrow: it must not
    touch the binding columns (host / auth / my_team / season), which only a
    real re-link may change.
    """
    if not league_id:
        return
    with engine.begin() as conn:
        conn.execute(
            update(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
            .values(platform_future_picks=json.dumps(future_picks or []),
                    updated_at=_now())
        )


def get_platform_league(league_id: str, platform: str) -> dict | None:
    """Return the leagues row for a linked league of the given platform, or
    None when the id is unknown or the row's platform doesn't match."""
    with engine.connect() as conn:
        row = conn.execute(
            select(leagues_table)
            .where(leagues_table.c.sleeper_league_id == str(league_id))
        ).fetchone()
    if not row or (row._mapping.get("platform") or "sleeper") != platform:
        return None
    return dict(row._mapping)


def load_platform_leagues_for_user(user_id: str, platform: str) -> list[dict]:
    """Return every linked league of `platform` this user is bound to, with
    the full membership snapshot (rosters already in Sleeper player-id space)
    so the mobile client can build a standard /api/session/init payload."""
    if not user_id:
        return []
    with engine.connect() as conn:
        member_rows = conn.execute(
            select(league_members_table.c.league_id).where(
                league_members_table.c.user_id == user_id
            )
        ).fetchall()
        league_ids = sorted({r.league_id for r in member_rows})
        if not league_ids:
            return []
        league_rows = conn.execute(
            select(leagues_table).where(
                (leagues_table.c.sleeper_league_id.in_(league_ids)) &
                (leagues_table.c.platform == platform)
            )
        ).fetchall()
    out = []
    for lg in league_rows:
        m = dict(lg._mapping)
        out.append({
            "league_id":      m["sleeper_league_id"],
            "name":           m.get("name"),
            "platform":       platform,
            "season":         m.get("platform_season"),
            "host":           m.get("platform_host"),
            "auth":           m.get("platform_auth"),
            "my_team":        m.get("platform_my_team"),
            "total_rosters":  m.get("total_rosters"),
            "members":        load_league_members(m["sleeper_league_id"]),
        })
    return out


# ---------------------------------------------------------------------------
# Notification prefs / send-log / quiet-hours queue helpers
# ---------------------------------------------------------------------------

# Default values used when no notification_prefs row exists for the user.
# Matches the plan: all 3 buckets ON, quiet hours ON.
NOTIF_PREF_DEFAULTS: dict = {
    "trade_matches":       1,
    "weekly_digest":       1,
    "reengagement":        1,
    "quiet_hours_enabled": 1,
    "tz":                  "America/New_York",
}

# Map every push `kind` to one of three pref-bucket column names. Anything
# absent is treated as transactional and ignored by the bucket gate (i.e.
# always sent if the user has push enabled at the OS level).
NOTIF_KIND_TO_BUCKET: dict[str, str] = {
    # Trade matches bucket
    "new_match":                       "trade_matches",
    "counter_offer":                   "trade_matches",
    "match_accepted":                  "trade_matches",
    "match_expiring":                  "trade_matches",
    "first_match":                     "trade_matches",
    "league_member_joined":            "trade_matches",
    "league_member_unlocked_trades":   "trade_matches",
    # Weekly digest bucket
    "weekly_digest":                   "weekly_digest",
    "pending_review":                  "weekly_digest",
    # Re-engagement bucket
    "winback_matches":                 "reengagement",
    "winback_dormant":                 "reengagement",
    "finish_ranking":                  "reengagement",
    "season_start":                    "reengagement",
    # F10 (flag deck.replenishment) — weekly fresh-deck push. Deliberately
    # in the re-engagement bucket so `notif.reengagement_default_off`
    # applies: without a stored opt-in the push is skipped.
    "deck_replenished":                "reengagement",
}

def _notif_pref_effective_defaults() -> dict:
    """NOTIF_PREF_DEFAULTS adjusted for feature flags.

    `notif.reengagement_default_off` (teardown 05-04a): the push primer's
    consent language promises only transactional match events, so the
    re-engagement bucket must not default ON — users with no stored pref
    are served (and, on first row write, persisted) reengagement=0.
    Stored values always win. Lazy import + swallow, mirroring
    accounts._email_capture_enabled: a flags problem must never break
    notification reads.
    """
    out = dict(NOTIF_PREF_DEFAULTS)
    try:
        from .feature_flags import is_enabled
        if is_enabled("notif.reengagement_default_off"):
            out["reengagement"] = 0
    except Exception:
        pass
    return out


def get_notification_prefs(user_id: str) -> dict:
    """Return the user's prefs row merged onto NOTIF_PREF_DEFAULTS (flag-
    adjusted — see _notif_pref_effective_defaults). Always returns a
    complete dict — callers don't need to handle missing rows.
    """
    out = _notif_pref_effective_defaults()
    if not user_id:
        return out
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(notification_prefs_table)
                .where(notification_prefs_table.c.user_id == user_id)
            ).fetchone()
        if row:
            d = dict(row._mapping)
            for k in ("trade_matches", "weekly_digest", "reengagement", "quiet_hours_enabled"):
                if d.get(k) is not None:
                    out[k] = int(d[k])
            if d.get("tz"):
                out["tz"] = d["tz"]
    except Exception as e:
        print(f"[get_notification_prefs] {user_id} failed: {e}")
    return out


def upsert_notification_prefs(user_id: str, **fields) -> dict:
    """Partial update — only the keys passed are written. Returns the
    post-update merged prefs dict. Booleans accepted as 0/1/True/False.
    """
    if not user_id:
        return _notif_pref_effective_defaults()
    allowed = {"trade_matches", "weekly_digest", "reengagement",
               "quiet_hours_enabled", "tz"}
    updates: dict = {}
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        if k == "tz":
            updates[k] = str(v)
        else:
            updates[k] = 1 if bool(v) else 0
    if not updates:
        return get_notification_prefs(user_id)
    updates["user_id"]    = user_id
    updates["updated_at"] = _now()
    try:
        with engine.begin() as conn:
            existing = conn.execute(
                select(notification_prefs_table.c.user_id)
                .where(notification_prefs_table.c.user_id == user_id)
            ).fetchone()
            if existing:
                conn.execute(
                    update(notification_prefs_table)
                    .where(notification_prefs_table.c.user_id == user_id)
                    .values(**{k: v for k, v in updates.items() if k != "user_id"})
                )
            else:
                # Fill missing columns with defaults so the row is complete.
                row = _notif_pref_effective_defaults()
                row.update(updates)
                conn.execute(insert(notification_prefs_table).values(**row))
    except Exception as e:
        print(f"[upsert_notification_prefs] {user_id} failed: {e}")
    return get_notification_prefs(user_id)


def log_notification_send(user_id: str, kind: str, dedup_key: str | None = None) -> None:
    """Append one row to notification_events_log. Called by the push
    dispatcher right after a push leaves _send_expo_push().
    """
    if not user_id or not kind:
        return
    try:
        with engine.begin() as conn:
            conn.execute(insert(notification_events_log_table).values(
                user_id   = user_id,
                kind      = kind,
                dedup_key = dedup_key,
                sent_at   = _now(),
            ))
    except Exception as e:
        print(f"[log_notification_send] {user_id}/{kind} failed: {e}")


def notification_dedup_sent(user_id: str, kind: str, dedup_key: str) -> bool:
    """True if a (user_id, kind, dedup_key) row already exists in
    notification_events_log. Powers per-event lifetime caps like
    `match_expiring` (1 per match) and `first_match` (1 lifetime).
    """
    if not user_id or not kind or not dedup_key:
        return False
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(notification_events_log_table.c.id)
                .where(notification_events_log_table.c.user_id == user_id)
                .where(notification_events_log_table.c.kind == kind)
                .where(notification_events_log_table.c.dedup_key == dedup_key)
                .limit(1)
            ).fetchone()
            return row is not None
    except Exception as e:
        print(f"[notification_dedup_sent] {user_id}/{kind} failed: {e}")
        return False


def count_notification_sends_since(user_id: str, kind: str, since_iso: str) -> int:
    """Count rows in notification_events_log for (user_id, kind) with
    sent_at >= since_iso. Powers frequency-cap checks.
    """
    if not user_id or not kind or not since_iso:
        return 0
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COUNT(*) AS n FROM notification_events_log "
                "WHERE user_id = :u AND kind = :k AND sent_at >= :s"
            ), {"u": user_id, "k": kind, "s": since_iso}).fetchone()
            return int(row.n) if row else 0
    except Exception as e:
        print(f"[count_notification_sends_since] {user_id}/{kind} failed: {e}")
        return 0


def queue_notification(
    user_id: str,
    kind: str,
    *,
    title: str,
    body: str,
    data: dict | None = None,
    deliver_after: str,
    dedup_key: str | None = None,
) -> None:
    """Defer a push by writing it to notification_queue. The 8am cron
    drains rows where deliver_after <= now() per user and bundles them.
    `dedup_key` is the original key from _send_typed_push; it gets
    threaded through the bundle drain so frequency caps remain accurate.
    """
    if not user_id or not kind or not deliver_after:
        return
    try:
        with engine.begin() as conn:
            conn.execute(insert(notification_queue_table).values(
                user_id        = user_id,
                kind           = kind,
                title          = title,
                body           = body,
                data_json      = json.dumps(data) if data else None,
                dedup_key      = dedup_key,
                queued_at      = _now(),
                deliver_after  = deliver_after,
            ))
    except Exception as e:
        print(f"[queue_notification] {user_id}/{kind} failed: {e}")


def drain_due_queued_notifications(now_iso: str) -> dict[str, list[dict]]:
    """Return + delete all queue rows where deliver_after <= now_iso, grouped
    by user_id. Caller is responsible for collapsing into bundled push(es).

    Atomic: rows are SELECTed and DELETEd in the same transaction so the
    same row never drains twice.
    """
    out: dict[str, list[dict]] = {}
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(notification_queue_table)
                .where(notification_queue_table.c.deliver_after <= now_iso)
            ).fetchall()
            if not rows:
                return out
            ids = [r.id for r in rows]
            for r in rows:
                d = dict(r._mapping)
                if d.get("data_json"):
                    try: d["data"] = json.loads(d["data_json"])
                    except Exception: d["data"] = None
                else:
                    d["data"] = None
                out.setdefault(d["user_id"], []).append(d)
            conn.execute(
                delete(notification_queue_table)
                .where(notification_queue_table.c.id.in_(ids))
            )
    except Exception as e:
        print(f"[drain_due_queued_notifications] failed: {e}")
    return out


# ---------------------------------------------------------------------------
# Cron-tick helpers — iterate users / match state for re-engagement + reminders
# ---------------------------------------------------------------------------

def load_pending_matches_older_than(cutoff_iso: str) -> list[dict]:
    """Pending trade_matches whose `matched_at` < cutoff_iso. Used by the
    15-min realtime tick to find matches eligible for an `match_expiring`
    push. Each row returns enough to address both participants individually.
    """
    out: list[dict] = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    trade_matches_table.c.id,
                    trade_matches_table.c.league_id,
                    trade_matches_table.c.user_a_id,
                    trade_matches_table.c.user_b_id,
                    trade_matches_table.c.user_a_decision,
                    trade_matches_table.c.user_b_decision,
                    trade_matches_table.c.matched_at,
                )
                .where(trade_matches_table.c.status == "pending")
                .where(trade_matches_table.c.matched_at < cutoff_iso)
            ).fetchall()
        for r in rows:
            out.append(dict(r._mapping))
    except Exception as e:
        print(f"[load_pending_matches_older_than] failed: {e}")
    return out


def load_unread_match_count(user_id: str) -> int:
    """Count of pending matches where this user has not yet decided AND the
    match has been created since the user last viewed Matches. Used for
    pending_review (Wed 9am) and winback_matches (7d inactive + unread).
    """
    if not user_id:
        return 0
    try:
        with engine.connect() as conn:
            seen_row = conn.execute(
                select(users_table.c.last_match_seen_at)
                .where(users_table.c.sleeper_user_id == user_id)
            ).fetchone()
            seen_at = (seen_row.last_match_seen_at if seen_row else None) or "1970-01-01T00:00:00+00:00"
            row = conn.execute(text(
                "SELECT COUNT(*) AS n FROM trade_matches "
                "WHERE status = 'pending' AND matched_at > :seen "
                "AND ((user_a_id = :uid AND user_a_decision IS NULL) "
                "  OR (user_b_id = :uid AND user_b_decision IS NULL))"
            ), {"uid": user_id, "seen": seen_at}).fetchone()
            return int(row.n) if row else 0
    except Exception as e:
        print(f"[load_unread_match_count] {user_id} failed: {e}")
        return 0


def load_all_signed_up_users() -> list[dict]:
    """Return a minimal dict per user with the fields cron ticks need to
    reason about engagement state. One row per user — no JOINs because
    notification_prefs is read separately via get_notification_prefs() to
    keep the default-merge logic in one place.
    """
    out: list[dict] = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    users_table.c.sleeper_user_id,
                    users_table.c.username,
                    users_table.c.display_name,
                    users_table.c.signup_at,
                    users_table.c.last_active_at,
                    users_table.c.last_rank_at,
                    users_table.c.unlocked_formats,
                ).where(users_table.c.signup_at.is_not(None))
            ).fetchall()
        for r in rows:
            d = dict(r._mapping)
            try:
                d["unlocked_formats"] = json.loads(d["unlocked_formats"]) if d.get("unlocked_formats") else []
            except Exception:
                d["unlocked_formats"] = []
            out.append(d)
    except Exception as e:
        print(f"[load_all_signed_up_users] failed: {e}")
    return out


# ---------------------------------------------------------------------------
# app_feedback — save / load helpers
# ---------------------------------------------------------------------------

def save_feedback(
    *,
    client_id: str,
    screen: str,
    severity: str,
    text_body: str,
    user_id: str | None = None,
    username: str | None = None,
    app_version: str | None = None,
    platform: str | None = None,
    device_type: str | None = None,
    os_version: str | None = None,
    client_created_at: str | None = None,
) -> dict:
    """Insert (idempotently on client_id) a feedback row and return
    {server_id, created_at, duplicate}.

    Retries with the same client_id are dropped: we look up the existing
    row and return its ids so the mobile client can move on. SQLite uses
    INSERT OR IGNORE; Postgres uses ON CONFLICT (client_id) DO NOTHING.
    """
    is_postgres = not DATABASE_URL.startswith("sqlite")
    now_iso = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        # Postgres: ON CONFLICT … DO NOTHING RETURNING id; if a row was
        # actually inserted we get the new id back, otherwise empty.
        if is_postgres:
            res = conn.execute(
                text(
                    """
                    INSERT INTO app_feedback
                        (client_id, user_id, username, screen, severity, text,
                         app_version, platform, device_type, os_version,
                         client_created_at, created_at)
                    VALUES
                        (:client_id, :user_id, :username, :screen, :severity, :text,
                         :app_version, :platform, :device_type, :os_version,
                         :client_created_at, :created_at)
                    ON CONFLICT (client_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "client_id": client_id,
                    "user_id": user_id,
                    "username": username,
                    "screen": screen,
                    "severity": severity,
                    "text": text_body,
                    "app_version": app_version,
                    "platform": platform,
                    "device_type": device_type,
                    "os_version": os_version,
                    "client_created_at": client_created_at,
                    "created_at": now_iso,
                },
            ).fetchone()
            if res:
                return {"server_id": int(res[0]), "created_at": now_iso, "duplicate": False}
        else:
            # SQLite: INSERT OR IGNORE. Use rowcount (==1 on insert, 0 on
            # conflict) to detect dedup — `lastrowid` is unreliable here
            # because SQLite returns the previous successful insert's id
            # on this connection when the current insert was ignored.
            cur = conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO app_feedback
                        (client_id, user_id, username, screen, severity, text,
                         app_version, platform, device_type, os_version,
                         client_created_at, created_at)
                    VALUES
                        (:client_id, :user_id, :username, :screen, :severity, :text,
                         :app_version, :platform, :device_type, :os_version,
                         :client_created_at, :created_at)
                    """
                ),
                {
                    "client_id": client_id,
                    "user_id": user_id,
                    "username": username,
                    "screen": screen,
                    "severity": severity,
                    "text": text_body,
                    "app_version": app_version,
                    "platform": platform,
                    "device_type": device_type,
                    "os_version": os_version,
                    "client_created_at": client_created_at,
                    "created_at": now_iso,
                },
            )
            if cur.rowcount == 1 and cur.lastrowid:
                return {"server_id": int(cur.lastrowid), "created_at": now_iso, "duplicate": False}

        # Duplicate path — fetch the pre-existing row's id + created_at so
        # the client gets a consistent response and can mark its local
        # copy synced without another retry.
        existing = conn.execute(
            select(app_feedback_table.c.id, app_feedback_table.c.created_at)
            .where(app_feedback_table.c.client_id == client_id)
        ).fetchone()
        if existing:
            return {
                "server_id": int(existing[0]),
                "created_at": existing[1] or now_iso,
                "duplicate": True,
            }
        # Shouldn't happen — either we just inserted (handled above) or a
        # duplicate exists. Defensive fallback.
        return {"server_id": 0, "created_at": now_iso, "duplicate": True}


def list_feedback(*, since_id: int = 0, limit: int = 100) -> list[dict]:
    """Return feedback rows with id > since_id, oldest first, capped at
    `limit`. Used by GET /api/feedback/admin so an operator can stream
    new captures since their last poll. Caller must enforce auth.
    """
    limit = max(1, min(int(limit), 500))
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                app_feedback_table.c.id,
                app_feedback_table.c.client_id,
                app_feedback_table.c.user_id,
                app_feedback_table.c.username,
                app_feedback_table.c.screen,
                app_feedback_table.c.severity,
                app_feedback_table.c.text,
                app_feedback_table.c.app_version,
                app_feedback_table.c.platform,
                app_feedback_table.c.device_type,
                app_feedback_table.c.os_version,
                app_feedback_table.c.client_created_at,
                app_feedback_table.c.created_at,
                app_feedback_table.c.status,
                app_feedback_table.c.status_updated_at,
            )
            .where(app_feedback_table.c.id > int(since_id))
            .order_by(app_feedback_table.c.id.asc())
            .limit(limit)
        ).fetchall()
    return [
        {
            "id": int(r[0]),
            "client_id": r[1],
            "user_id": r[2],
            "username": r[3],
            "screen": r[4],
            "severity": r[5],
            "text": r[6],
            "app_version": r[7],
            "platform": r[8],
            "device_type": r[9],
            "os_version": r[10],
            "client_created_at": r[11],
            "created_at": r[12],
            "status": r[13] or "new",
            "status_updated_at": r[14],
        }
        for r in rows
    ]


def set_feedback_status(
    feedback_id: int,
    status: str | None = None,
    severity: str | None = None,
) -> dict | None:
    """Operator update for one feedback row: lifecycle status and/or a
    severity reclassification (e.g. a note filed as 'bug' that is really
    an 'idea'). Returns the applied changes {id, ...}, or None when the id
    doesn't exist. status_updated_at only moves when the STATUS changes.
    Caller validates vocabularies and enforces auth.
    """
    values: dict = {}
    out: dict = {"id": int(feedback_id)}
    if status is not None:
        now_iso = datetime.now(timezone.utc).isoformat()
        values["status"] = status
        values["status_updated_at"] = now_iso
        out["status"] = status
        out["status_updated_at"] = now_iso
    if severity is not None:
        values["severity"] = severity
        out["severity"] = severity
    if not values:
        return None
    with engine.begin() as conn:
        res = conn.execute(
            app_feedback_table.update()
            .where(app_feedback_table.c.id == int(feedback_id))
            .values(**values)
        )
        if res.rowcount == 0:
            return None
    return out


def list_feedback_for_user(user_id: str, limit: int = 200) -> list[dict]:
    """Return this user's own feedback notes, newest first — the read side
    of the in-app feedback widget's status display. Only fields the widget
    needs; NULL status reads as 'new'.

    Scope guarantees (2026-07-04):
      • strictly `user_id == user_id` — never returns another user's notes
        or anonymous (NULL-user) notes; falsy user_id short-circuits to [].
      • closed notes (FEEDBACK_CLOSED_STATUSES: shipped/declined) are
        excluded — once the operator closes a note it disappears from the
        user's inbox. The admin readback (list_feedback) is unaffected.
    """
    if not user_id:
        return []
    limit = max(1, min(int(limit), 500))
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                app_feedback_table.c.id,
                app_feedback_table.c.client_id,
                app_feedback_table.c.screen,
                app_feedback_table.c.severity,
                app_feedback_table.c.text,
                app_feedback_table.c.created_at,
                app_feedback_table.c.status,
                app_feedback_table.c.status_updated_at,
            )
            .where(app_feedback_table.c.user_id == user_id)
            .where(
                or_(
                    app_feedback_table.c.status.is_(None),
                    app_feedback_table.c.status.not_in(FEEDBACK_CLOSED_STATUSES),
                )
            )
            .order_by(app_feedback_table.c.id.desc())
            .limit(limit)
        ).fetchall()
    return [
        {
            "server_id": int(r[0]),
            "client_id": r[1],
            "screen": r[2],
            "severity": r[3],
            "text": r[4],
            "created_at": r[5],
            "status": r[6] or "new",
            "status_updated_at": r[7],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Bad-trade flags (FB #85) — engine-quality feedback loop
# ---------------------------------------------------------------------------

def _bad_trade_dedupe_key(
    user_id: str,
    league_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
) -> str:
    """Canonical uniqueness key: one flag per (user, league, trade package).
    Player-id order is irrelevant to the package, so both sides are sorted."""
    give = ",".join(sorted(str(p) for p in give_player_ids))
    recv = ",".join(sorted(str(p) for p in receive_player_ids))
    return f"{user_id}|{league_id}|{give}|{recv}"


def save_bad_trade_flag(
    *,
    user_id: str,
    league_id: str,
    give_player_ids: list[str],
    receive_player_ids: list[str],
    username: str | None = None,
    target_user_id: str | None = None,
    target_username: str | None = None,
    scoring_format: str | None = None,
    trade_id: str | None = None,
    mismatch_score: float | None = None,
    fairness_score: float | None = None,
    composite_score: float | None = None,
    need_fit: float | None = None,
    partner_fit: float | None = None,
    basis: str | None = None,
    reason: str | None = None,
) -> dict:
    """Insert (idempotently on the derived dedupe_key) a bad-trade flag and
    return {server_id, created_at, duplicate}.

    Re-flagging the same package (same user + league + give/receive sets,
    order-insensitive) is dropped: the existing row's ids are returned so
    the client can move on. Same dual-dialect pattern as save_feedback —
    SQLite INSERT OR IGNORE; Postgres ON CONFLICT (dedupe_key) DO NOTHING.
    """
    dedupe_key = _bad_trade_dedupe_key(
        user_id, league_id, give_player_ids, receive_player_ids)
    is_postgres = not DATABASE_URL.startswith("sqlite")
    now_iso = datetime.now(timezone.utc).isoformat()
    params = {
        "dedupe_key":         dedupe_key,
        "user_id":            user_id,
        "username":           username,
        "league_id":          league_id,
        "target_user_id":     target_user_id,
        "target_username":    target_username,
        "give_player_ids":    json.dumps(list(give_player_ids)),
        "receive_player_ids": json.dumps(list(receive_player_ids)),
        "scoring_format":     scoring_format,
        "trade_id":           trade_id,
        "mismatch_score":     mismatch_score,
        "fairness_score":     fairness_score,
        "composite_score":    composite_score,
        "need_fit":           need_fit,
        "partner_fit":        partner_fit,
        "basis":              basis,
        "reason":             reason,
        "created_at":         now_iso,
    }
    cols = ", ".join(params.keys())
    binds = ", ".join(f":{k}" for k in params)
    with engine.begin() as conn:
        if is_postgres:
            res = conn.execute(
                text(
                    f"INSERT INTO bad_trade_flags ({cols}) VALUES ({binds}) "
                    "ON CONFLICT (dedupe_key) DO NOTHING RETURNING id"
                ),
                params,
            ).fetchone()
            if res:
                return {"server_id": int(res[0]), "created_at": now_iso, "duplicate": False}
        else:
            # rowcount==1 on insert, 0 on conflict — `lastrowid` alone is
            # unreliable on ignored inserts (see save_feedback).
            cur = conn.execute(
                text(f"INSERT OR IGNORE INTO bad_trade_flags ({cols}) VALUES ({binds})"),
                params,
            )
            if cur.rowcount == 1 and cur.lastrowid:
                return {"server_id": int(cur.lastrowid), "created_at": now_iso, "duplicate": False}

        existing = conn.execute(
            select(bad_trade_flags_table.c.id, bad_trade_flags_table.c.created_at)
            .where(bad_trade_flags_table.c.dedupe_key == dedupe_key)
        ).fetchone()
        if existing:
            return {
                "server_id": int(existing[0]),
                "created_at": existing[1] or now_iso,
                "duplicate": True,
            }
        return {"server_id": 0, "created_at": now_iso, "duplicate": True}


def list_bad_trade_flags(*, since_id: int = 0, limit: int = 100) -> list[dict]:
    """Return bad-trade flags with id > since_id, oldest first, capped at
    `limit`. Used by GET /api/trades/flags/admin so the operator can stream
    new flags since their last poll. Caller must enforce auth. JSON-encoded
    player-id arrays are decoded back to lists."""
    limit = max(1, min(int(limit), 500))
    with engine.connect() as conn:
        rows = conn.execute(
            select(bad_trade_flags_table)
            .where(bad_trade_flags_table.c.id > int(since_id))
            .order_by(bad_trade_flags_table.c.id.asc())
            .limit(limit)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        d.pop("dedupe_key", None)   # internal uniqueness key, not operator data
        for field in ("give_player_ids", "receive_player_ids"):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Persistent sessions — helpers for server.py's session store
# (teardown 06-03, flag `auth.persistent_sessions`; see sessions_table)
# ---------------------------------------------------------------------------

def session_token_hash(token: str) -> str:
    """SHA-256 hex of a bearer token — the only form ever stored at rest."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def persist_session(
    token: str,
    *,
    user_id: str,
    account_id: str | None = None,
    verified_via: str | None = None,
    account_only: bool = False,
    username: str | None = None,
    display_name: str | None = None,
) -> None:
    """Upsert the durable row for a verified session. Refreshes
    last_seen_at (and identity fields) when the row already exists —
    callers throttle, so this doubles as the rolling-expiry heartbeat."""
    if not token or not user_id:
        return
    th = session_token_hash(token)
    now = _now()
    vals = {
        "user_id":      user_id,
        "account_id":   account_id,
        "verified_via": verified_via,
        "account_only": 1 if account_only else 0,
        "username":     username,
        "display_name": display_name,
        "last_seen_at": now,
    }
    with engine.begin() as conn:
        res = conn.execute(
            update(sessions_table)
            .where(sessions_table.c.token_hash == th)
            .values(**vals)
        )
        if res.rowcount == 0:
            try:
                conn.execute(insert(sessions_table).values(
                    token_hash=th, created_at=now, **vals))
            except Exception:
                pass  # raced concurrent insert — the other writer's row wins


def load_persisted_session(token: str) -> dict | None:
    """Row for this bearer token, or None. Keys mirror sessions_table."""
    if not token:
        return None
    th = session_token_hash(token)
    with engine.connect() as conn:
        row = conn.execute(
            select(sessions_table).where(sessions_table.c.token_hash == th)
        ).fetchone()
    return dict(row._mapping) if row is not None else None


def touch_persisted_session(token: str) -> None:
    """Bump last_seen_at for the rolling 90d idle expiry. No-op on miss."""
    if not token:
        return
    with engine.begin() as conn:
        conn.execute(
            update(sessions_table)
            .where(sessions_table.c.token_hash == session_token_hash(token))
            .values(last_seen_at=_now())
        )


def delete_persisted_session(token: str) -> bool:
    """Remove one session row (sign-out). True when a row was deleted."""
    if not token:
        return False
    with engine.begin() as conn:
        res = conn.execute(
            delete(sessions_table)
            .where(sessions_table.c.token_hash == session_token_hash(token))
        )
    return bool(res.rowcount)


def delete_persisted_sessions_for_user(user_id: str) -> int:
    """Remove every session row for a user (account deletion, working-key
    migration, test-user teardown). Returns the number of rows deleted."""
    if not user_id:
        return 0
    with engine.begin() as conn:
        res = conn.execute(
            delete(sessions_table).where(sessions_table.c.user_id == user_id)
        )
    return int(res.rowcount or 0)


def purge_stale_persisted_sessions(max_idle_days: int = 90) -> int:
    """Delete rows idle past the rolling expiry. ISO-8601 UTC strings
    compare lexicographically, so a computed cutoff string suffices."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=max_idle_days)).isoformat()
    with engine.begin() as conn:
        res = conn.execute(
            delete(sessions_table).where(sessions_table.c.last_seen_at < cutoff)
        )
    return int(res.rowcount or 0)


# ---------------------------------------------------------------------------
# Shared trade packages — helpers for the /s/p/<id> share landing
# (teardown S7 PRD-01 follow-up, flag `growth.share_landing`)
# ---------------------------------------------------------------------------

def create_shared_package(
    short_id: str,
    user_id: str,
    give_ids: list[str],
    receive_ids: list[str],
) -> bool:
    """Insert one share snapshot. False on a short_id collision (caller
    re-mints and retries)."""
    try:
        with engine.begin() as conn:
            conn.execute(insert(shared_packages_table).values(
                short_id=short_id,
                user_id=user_id,
                give_ids=json.dumps([str(x) for x in give_ids]),
                receive_ids=json.dumps([str(x) for x in receive_ids]),
                created_at=_now(),
            ))
        return True
    except Exception:
        return False


def load_shared_package(short_id: str) -> dict | None:
    """{short_id, user_id, give_ids: list, receive_ids: list, created_at}
    or None."""
    if not short_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(shared_packages_table)
            .where(shared_packages_table.c.short_id == short_id)
        ).fetchone()
    if row is None:
        return None
    d = dict(row._mapping)
    for field in ("give_ids", "receive_ids"):
        try:
            d[field] = json.loads(d[field])
        except (json.JSONDecodeError, TypeError):
            d[field] = []
    return d


def count_recent_shared_packages(user_id: str, *, hours: int = 1) -> int:
    """Sharer's rows newer than the window — the POST rate-limit input."""
    if not user_id:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with engine.connect() as conn:
        n = conn.execute(
            select(func.count())
            .select_from(shared_packages_table)
            .where(and_(shared_packages_table.c.user_id == user_id,
                        shared_packages_table.c.created_at >= cutoff))
        ).scalar()
    return int(n or 0)


# ---------------------------------------------------------------------------
# Mock drafts — draft-extensions W2 (plan §5, lld §3.3)
# ---------------------------------------------------------------------------
# Thin persistence for `backend/mock_draft_service`. The engine owns every
# rule; these four functions only move rows. `settings` and `picks` are opaque
# JSON strings here on purpose — the shapes belong to the service, and
# re-parsing them in two places is how two vocabularies start.

def create_mock_draft(user_id: str, league_id: str, season: int,
                      settings_json: str, picks_json: str,
                      rng_seed: int, status: str = "active") -> int:
    """Insert one mock, abandoning any prior ACTIVE row for the same
    (user, league) in the SAME transaction. Returns the new row id.

    The abandon-then-insert pair is what enforces "one active mock per user
    per league" (lld §3.3); doing it in one transaction is what stops a
    double-tapped create from leaving two active rows behind.
    """
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            mock_drafts_table.update()
            .where(and_(mock_drafts_table.c.user_id == str(user_id),
                        mock_drafts_table.c.league_id == str(league_id),
                        mock_drafts_table.c.status == "active"))
            .values(status="abandoned", updated_at=now)
        )
        result = conn.execute(insert(mock_drafts_table).values(
            user_id=str(user_id), league_id=str(league_id), season=int(season),
            status=status, settings=settings_json, picks=picks_json,
            rng_seed=int(rng_seed), created_at=now, updated_at=now,
        ))
    return int(result.inserted_primary_key[0])


def load_mock_draft(mock_id: int, user_id: str | None = None) -> dict | None:
    """One mock by id, optionally scoped to its owner (the authz check)."""
    conditions = [mock_drafts_table.c.id == int(mock_id)]
    if user_id is not None:
        conditions.append(mock_drafts_table.c.user_id == str(user_id))
    with engine.connect() as conn:
        row = conn.execute(
            select(mock_drafts_table).where(and_(*conditions))
        ).fetchone()
    return dict(row._mapping) if row else None


def load_current_mock_draft(user_id: str, league_id: str) -> dict | None:
    """The user's ACTIVE mock for this league, else its most recent COMPLETE
    one (the resume-or-recap contract of `GET /api/mock-draft`)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(mock_drafts_table)
            .where(and_(mock_drafts_table.c.user_id == str(user_id),
                        mock_drafts_table.c.league_id == str(league_id),
                        mock_drafts_table.c.status == "active"))
            .order_by(mock_drafts_table.c.id.desc())
            .limit(1)
        ).fetchone()
        if row is None:
            row = conn.execute(
                select(mock_drafts_table)
                .where(and_(mock_drafts_table.c.user_id == str(user_id),
                            mock_drafts_table.c.league_id == str(league_id),
                            mock_drafts_table.c.status == "complete"))
                .order_by(mock_drafts_table.c.id.desc())
                .limit(1)
            ).fetchone()
    return dict(row._mapping) if row else None


def abandon_completed_mock_drafts(user_id: str, league_id: str) -> int:
    """Retire EVERY completed mock for this user+league. Returns the count.

    #292 — "can't do a second mock draft". `load_current_mock_draft`'s
    complete-fallback is `ORDER BY id DESC LIMIT 1` over `status = "complete"`,
    and nothing ever prunes a complete row. So abandoning one completed mock
    only uncovers the one beneath it: the next `GET /api/mock-draft` returns
    mock N-1's recap and the room is blocked all over again. Dismissal
    PAGINATED through the history instead of clearing it, which is why the
    dead-end looked unfixable from the client.

    Owner-scoped (`user_id` is in the WHERE, so one user can never retire
    another's rows) and idempotent — a second call matches nothing and returns
    0. `active` and already-`abandoned` rows are left alone: this closes out
    the recap backlog, it does not cancel a draft in progress.
    """
    with engine.begin() as conn:
        result = conn.execute(
            mock_drafts_table.update()
            .where(and_(mock_drafts_table.c.user_id == str(user_id),
                        mock_drafts_table.c.league_id == str(league_id),
                        mock_drafts_table.c.status == "complete"))
            .values(status="abandoned", updated_at=_now())
        )
    return int(result.rowcount or 0)


def update_mock_draft(mock_id: int, user_id: str, *, picks_json: str | None = None,
                      status: str | None = None) -> bool:
    """Persist an advanced (or abandoned) mock. Owner-scoped; False when the
    row is not the caller's."""
    values: dict = {"updated_at": _now()}
    if picks_json is not None:
        values["picks"] = picks_json
    if status is not None:
        values["status"] = status
    with engine.begin() as conn:
        result = conn.execute(
            mock_drafts_table.update()
            .where(and_(mock_drafts_table.c.id == int(mock_id),
                        mock_drafts_table.c.user_id == str(user_id)))
            .values(**values)
        )
    return bool(result.rowcount)
