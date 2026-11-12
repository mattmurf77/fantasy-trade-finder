"""The local research store: one SQLite file plus compressed raw responses.

Layout of ``data_dir`` (default ``data/sleeper-universe/``, git-ignored):

    universe.sqlite              normalised tables (schema below)
    raw/<season>/<league>.json.gz  identity-stripped responses, one per league-season
    hmac.key                     the HMAC key (unless the env var is set)
    seeds.txt                    the operator's seed list (input; never read back into the store)

Base tables are written by ``pull`` inside one transaction per league-season
(the checkpoint). Derived tables are rebuilt from base tables by ``derive``.
Lineage lives only in ``league_index`` so a lineage relabel never touches
pulled rows.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
from pathlib import Path

DB_NAME = "universe.sqlite"
SEED_FILE = "seeds.txt"
SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, command TEXT, started_at TEXT,
  finished_at TEXT, status TEXT, params_json TEXT, request_counts_json TEXT,
  requests INTEGER, seconds REAL, code_version TEXT, summary_json TEXT,
  nfl_state_json TEXT, leak_scan_json TEXT);
CREATE TABLE IF NOT EXISTS user_keys (user_key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS discovery_users (
  user_key TEXT PRIMARY KEY, hop INTEGER, seasons_json TEXT);
CREATE TABLE IF NOT EXISTS league_index (
  league_id TEXT PRIMARY KEY, season INTEGER, hop INTEGER, lineage_id TEXT,
  previous_league_id TEXT, kept INTEGER, skip_reason TEXT, status TEXT,
  expanded INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS skipped_leagues (
  league_id TEXT PRIMARY KEY, season INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS pull_checkpoints (
  league_id TEXT PRIMARY KEY, season INTEGER, completed_at TEXT, run_id INTEGER,
  requests INTEGER, seconds REAL, league_status TEXT, raw_path TEXT);
CREATE TABLE IF NOT EXISTS pull_failures (
  league_id TEXT PRIMARY KEY, season INTEGER, run_id INTEGER, kind TEXT);
CREATE TABLE IF NOT EXISTS leagues (
  league_id TEXT PRIMARY KEY, season INTEGER, previous_league_id TEXT,
  status TEXT, teams INTEGER, roster_positions_json TEXT, n_starters INTEGER,
  bench_slots INTEGER, taxi_slots INTEGER, reserve_slots INTEGER,
  superflex INTEGER, two_qb INTEGER, idp INTEGER, te_premium REAL, ppr REAL,
  pass_td REAL, median_game INTEGER, playoff_teams INTEGER,
  playoff_week_start INTEGER, trade_deadline INTEGER, waiver_type INTEGER,
  faab INTEGER, faab_budget INTEGER, best_ball INTEGER, league_type INTEGER,
  unusual_scoring INTEGER, scoring_settings_json TEXT, settings_json TEXT);
CREATE TABLE IF NOT EXISTS league_members (
  league_id TEXT, user_key TEXT, is_commissioner INTEGER,
  PRIMARY KEY (league_id, user_key));
CREATE TABLE IF NOT EXISTS rosters (
  league_id TEXT, roster_id INTEGER, owner_key TEXT, co_owner_keys_json TEXT,
  players_json TEXT, starters_json TEXT, reserve_json TEXT, taxi_json TEXT,
  wins INTEGER, losses INTEGER, ties INTEGER, fpts REAL, fpts_against REAL,
  ppts REAL, division INTEGER, waiver_budget_used INTEGER,
  PRIMARY KEY (league_id, roster_id));
CREATE TABLE IF NOT EXISTS roster_weeks (
  league_id TEXT, week INTEGER, roster_id INTEGER, matchup_id INTEGER,
  players_json TEXT, starters_json TEXT, players_points_json TEXT,
  starters_points_json TEXT, points REAL, played INTEGER, has_points INTEGER,
  PRIMARY KEY (league_id, week, roster_id));
CREATE TABLE IF NOT EXISTS matchups (
  league_id TEXT, week INTEGER, roster_id INTEGER, matchup_id INTEGER,
  opponent_roster INTEGER, paired INTEGER, points REAL, phase TEXT,
  played INTEGER, PRIMARY KEY (league_id, week, roster_id));
CREATE TABLE IF NOT EXISTS transactions (
  league_id TEXT, transaction_id TEXT, type TEXT, status TEXT, leg INTEGER,
  created REAL, status_updated REAL, creator_key TEXT, roster_ids_json TEXT,
  consenter_ids_json TEXT, adds_json TEXT, drops_json TEXT,
  draft_picks_json TEXT, waiver_budget_json TEXT, waiver_bid REAL,
  notes_code TEXT, PRIMARY KEY (league_id, transaction_id));
CREATE TABLE IF NOT EXISTS drafts (
  draft_id TEXT PRIMARY KEY, league_id TEXT, season TEXT, type TEXT,
  status TEXT, start_time REAL, last_picked REAL, rounds INTEGER,
  teams INTEGER, slot_to_roster_json TEXT, draft_order_json TEXT);
CREATE TABLE IF NOT EXISTS draft_picks (
  draft_id TEXT, pick_no INTEGER, round INTEGER, draft_slot INTEGER,
  roster_id INTEGER, player_id TEXT, picked_by_key TEXT, is_keeper INTEGER,
  position TEXT, PRIMARY KEY (draft_id, pick_no));
CREATE TABLE IF NOT EXISTS traded_picks (
  league_id TEXT, season TEXT, round INTEGER, orig_roster INTEGER,
  owner_roster INTEGER, previous_owner_roster INTEGER,
  PRIMARY KEY (league_id, season, round, orig_roster));
CREATE TABLE IF NOT EXISTS brackets (
  league_id TEXT, bracket TEXT, r INTEGER, m INTEGER, t1 INTEGER, t2 INTEGER,
  w INTEGER, l INTEGER, p INTEGER, PRIMARY KEY (league_id, bracket, m));

CREATE TABLE IF NOT EXISTS trades (
  league_id TEXT, transaction_id TEXT, season INTEGER, lineage_id TEXT,
  leg INTEGER, created REAL, status_updated REAL, n_rosters INTEGER,
  roster_ids_json TEXT, creator_key TEXT, n_players INTEGER, n_picks INTEGER,
  faab_total REAL, timing TEXT, recon_method TEXT, recon_agree INTEGER,
  flags_json TEXT, PRIMARY KEY (league_id, transaction_id));
CREATE TABLE IF NOT EXISTS trade_assets (
  league_id TEXT, transaction_id TEXT, asset_idx INTEGER, asset_type TEXT,
  player_id TEXT, pick_season TEXT, pick_round INTEGER,
  pick_orig_roster INTEGER, faab_amount REAL, from_roster INTEGER,
  to_roster INTEGER, pick_resolution TEXT, pick_no INTEGER, pick_slot INTEGER,
  pick_player_id TEXT, orig_rank_at_trade INTEGER, orig_wins INTEGER,
  orig_losses INTEGER, orig_ties INTEGER, orig_points_for REAL,
  standing_basis TEXT, PRIMARY KEY (league_id, transaction_id, asset_idx));
CREATE TABLE IF NOT EXISTS trade_rosters (
  league_id TEXT, transaction_id TEXT, roster_id INTEGER, method TEXT,
  base_league_id TEXT, base_week INTEGER, players_json TEXT,
  alt_method TEXT, alt_agrees INTEGER,
  PRIMARY KEY (league_id, transaction_id, roster_id));
CREATE TABLE IF NOT EXISTS standings_weeks (
  league_id TEXT, week INTEGER, roster_id INTEGER,
  h2h_wins INTEGER, h2h_losses INTEGER, h2h_ties INTEGER,
  median_wins INTEGER, median_losses INTEGER, median_ties INTEGER,
  wins INTEGER, losses INTEGER, ties INTEGER, points_for REAL,
  points_against REAL, rank INTEGER, division INTEGER, division_rank INTEGER,
  games_back REAL, week_result TEXT, week_opponent INTEGER,
  PRIMARY KEY (league_id, week, roster_id));
CREATE TABLE IF NOT EXISTS outcomes (
  league_id TEXT, roster_id INTEGER, seed INTEGER, made_playoffs INTEGER,
  playoff_round_reached INTEGER, winners_place INTEGER, losers_place INTEGER,
  final_place INTEGER, finish_basis TEXT, champion INTEGER,
  PRIMARY KEY (league_id, roster_id));
CREATE TABLE IF NOT EXISTS standings_checks (
  league_id TEXT PRIMARY KEY, status TEXT, matched INTEGER, kinds_json TEXT);
CREATE TABLE IF NOT EXISTS reconstruction_checks (
  league_id TEXT, kind TEXT, week INTEGER, roster_id INTEGER, matched INTEGER,
  n_missing INTEGER, n_extra INTEGER, n_no_add_event INTEGER,
  n_no_drop_event INTEGER, n_wrong_roster INTEGER, n_other INTEGER,
  PRIMARY KEY (league_id, kind, week, roster_id));
"""

BASE_TABLES = ("leagues", "league_members", "rosters", "roster_weeks", "matchups",
               "transactions", "traded_picks", "brackets")
DERIVED_TABLES = ("trades", "trade_assets", "trade_rosters", "standings_weeks",
                  "outcomes", "standings_checks", "reconstruction_checks")


def _j(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:
            pass
        self.db_path = self.data_dir / DB_NAME
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        # Autocommit; save_league_season opens its own explicit transaction.
        self.conn.isolation_level = None
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                          (SCHEMA_VERSION,))
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def close(self):
        self.conn.close()

    # -- meta / key --------------------------------------------------------
    def check_key(self, fingerprint: str, allow_new: bool = False) -> None:
        row = self.conn.execute("SELECT value FROM meta WHERE key='key_fingerprint'").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO meta VALUES ('key_fingerprint', ?)", (fingerprint,))
            self.conn.commit()
        elif row[0] != fingerprint:
            if allow_new:
                self.conn.execute("UPDATE meta SET value=? WHERE key='key_fingerprint'",
                                  (fingerprint,))
                self.conn.execute("INSERT OR REPLACE INTO meta VALUES ('key_changed', ?)",
                                  ("owner keys before this point were made under another key",))
                return
            raise SystemExit(
                "HMAC key differs from the one this store was built with. "
                "Owner keys would not link across pulls. Restore the key "
                "(env SLEEPER_UNIVERSE_HMAC_KEY or the key file) or start a new "
                "--data-dir.")

    # -- runs --------------------------------------------------------------
    def start_run(self, command, started_at, params, code_version) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (command, started_at, status, params_json, code_version)"
            " VALUES (?,?,?,?,?)", (command, started_at, "running", _j(params), code_version))
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id, finished_at, status, request_counts, seconds,
                   summary=None, leak=None, nfl_state=None):
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, request_counts_json=?, requests=?,"
            " seconds=?, summary_json=?, nfl_state_json=?, leak_scan_json=? WHERE run_id=?",
            (finished_at, status, _j(dict(request_counts)), sum(request_counts.values()),
             seconds, _j(summary or {}), _j(nfl_state) if nfl_state is not None else None,
             _j(leak) if leak is not None else None, run_id))

    # -- discovery ---------------------------------------------------------
    def add_user_keys(self, keys) -> None:
        self.conn.executemany("INSERT OR IGNORE INTO user_keys VALUES (?)",
                              [(k,) for k in keys if k])

    def user_seasons_done(self, key) -> set[int]:
        row = self.conn.execute("SELECT seasons_json FROM discovery_users WHERE user_key=?",
                                (key,)).fetchone()
        return set(json.loads(row[0])) if row else set()

    def mark_user(self, key, hop, seasons) -> None:
        done = self.user_seasons_done(key) | set(seasons)
        self.conn.execute(
            "INSERT INTO discovery_users VALUES (?,?,?) ON CONFLICT(user_key) DO UPDATE"
            " SET seasons_json=excluded.seasons_json, hop=MIN(hop, excluded.hop)",
            (key, hop, _j(sorted(done))))

    def league_row(self, league_id):
        return self.conn.execute("SELECT * FROM league_index WHERE league_id=?",
                                 (str(league_id),)).fetchone()

    def successor_of(self, league_id):
        return self.conn.execute(
            "SELECT * FROM league_index WHERE previous_league_id=? LIMIT 1",
            (str(league_id),)).fetchone()

    def add_league(self, league_id, season, hop, lineage_id, prev, kept, reason, status):
        self.conn.execute(
            "INSERT OR REPLACE INTO league_index (league_id, season, hop, lineage_id,"
            " previous_league_id, kept, skip_reason, status, expanded) VALUES"
            " (?,?,?,?,?,?,?,?,0)",
            (str(league_id), season, hop, lineage_id, prev, 1 if kept else 0, reason, status))
        if kept:
            self.conn.execute("DELETE FROM skipped_leagues WHERE league_id=?", (str(league_id),))
        else:
            self.conn.execute("INSERT OR REPLACE INTO skipped_leagues VALUES (?,?,?)",
                              (str(league_id), season, reason))

    def relabel_lineage(self, old, new) -> int:
        cur = self.conn.execute("UPDATE league_index SET lineage_id=? WHERE lineage_id=?",
                                (new, old))
        return cur.rowcount

    def lineage_exists(self, lineage_id) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM league_index WHERE lineage_id=? AND kept=1 LIMIT 1",
            (lineage_id,)).fetchone() is not None

    def kept_lineage_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(DISTINCT lineage_id) FROM league_index WHERE kept=1").fetchone()[0]

    def next_league_to_expand(self, max_hops, seasons, skip=()):
        q = ",".join("?" * len(seasons))
        k = ",".join("?" * len(skip)) or "''"
        return self.conn.execute(
            f"SELECT league_id, hop FROM league_index WHERE kept=1 AND expanded=0"
            f" AND hop < ? AND season IN ({q}) AND league_id NOT IN ({k})"
            f" ORDER BY hop, season DESC, league_id LIMIT 1",
            (max_hops, *seasons, *sorted(skip))).fetchone()

    def mark_expanded(self, league_id):
        self.conn.execute("UPDATE league_index SET expanded=1 WHERE league_id=?", (league_id,))

    def deferred_leagues(self):
        return self.conn.execute(
            "SELECT league_id, hop FROM league_index WHERE skip_reason='cap_reached'"
            " ORDER BY hop, league_id").fetchall()

    def drop_league(self, league_id):
        self.conn.execute("DELETE FROM league_index WHERE league_id=?", (league_id,))
        self.conn.execute("DELETE FROM skipped_leagues WHERE league_id=?", (league_id,))

    def unlinked_kept(self, seasons):
        """Kept leagues whose predecessor is not indexed: candidates for a
        backward lineage walk when the season range grows."""
        q = ",".join("?" * len(seasons))
        return self.conn.execute(
            f"SELECT * FROM league_index li WHERE kept=1 AND season IN ({q})"
            " AND previous_league_id IS NOT NULL AND previous_league_id NOT IN ('', '0')"
            " AND NOT EXISTS (SELECT 1 FROM league_index p WHERE p.league_id=li.previous_league_id)"
            " ORDER BY season DESC, league_id", tuple(seasons)).fetchall()

    def commit(self):
        self.conn.commit()

    # -- pull ---------------------------------------------------------------
    def leagues_to_pull(self, seasons, refresh_incomplete=False):
        q = ",".join("?" * len(seasons))
        cond = "c.league_id IS NULL"
        if refresh_incomplete:
            cond += " OR c.league_status != 'complete'"
        return self.conn.execute(
            f"SELECT li.league_id, li.season, li.lineage_id, li.hop FROM league_index li"
            f" LEFT JOIN pull_checkpoints c ON c.league_id=li.league_id"
            f" WHERE li.kept=1 AND li.season IN ({q}) AND ({cond})"
            f" ORDER BY li.hop, li.lineage_id, li.season, li.league_id", tuple(seasons)).fetchall()

    def raw_path(self, season, league_id) -> Path:
        return self.data_dir / "raw" / str(season) / f"{league_id}.json.gz"

    def save_league_season(self, bundle: dict, rows: dict, *, league_id, season, run_id,
                           requests, seconds, completed_at, user_keys) -> None:
        """One transaction: replace this league-season's base rows, write the
        raw file, record the checkpoint. A kill before COMMIT leaves no
        checkpoint, so the next run redoes the league-season whole."""
        # Keyed by the index's id and season, never by a value from the
        # response; the caller has already checked the response's league_id.
        league_id = str(league_id)
        if str(rows["leagues"][0]["league_id"]) != league_id:
            raise ValueError("league_id of the rows differs from the league pulled")
        path = self.raw_path(season, league_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        data = gzip.compress(_j(bundle).encode("utf-8"), mtime=0)
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        c = self.conn
        try:
            c.execute("BEGIN")
            for table in BASE_TABLES:
                c.execute(f"DELETE FROM {table} WHERE league_id=?", (league_id,))
            old_drafts = [r[0] for r in c.execute(
                "SELECT draft_id FROM drafts WHERE league_id=?", (league_id,))]
            for d in old_drafts:
                c.execute("DELETE FROM draft_picks WHERE draft_id=?", (d,))
            c.execute("DELETE FROM drafts WHERE league_id=?", (league_id,))
            for table, items in rows.items():
                for item in items:
                    cols = ",".join(item)
                    c.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES"
                              f" ({','.join('?' * len(item))})", tuple(item.values()))
            c.executemany("INSERT OR IGNORE INTO user_keys VALUES (?)",
                          [(k,) for k in sorted(user_keys) if k])
            os.replace(tmp, path)
            c.execute("DELETE FROM pull_failures WHERE league_id=?", (league_id,))
            c.execute("INSERT OR REPLACE INTO pull_checkpoints VALUES (?,?,?,?,?,?,?,?)",
                      (league_id, season, completed_at, run_id, requests, seconds,
                       rows["leagues"][0]["status"],
                       str(path.relative_to(self.data_dir))))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def record_failure(self, league_id, season, run_id, kind):
        self.conn.execute("INSERT OR REPLACE INTO pull_failures VALUES (?,?,?,?)",
                          (league_id, season, run_id, kind))
        self.conn.commit()
