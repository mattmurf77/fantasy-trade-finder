#!/usr/bin/env python3
"""
TC-DB-001 — Schema integrity, migration idempotency, SQLite<->Postgres parity,
and live-data quality.

Three planes:
  A. SCHEMA PARITY — build a fresh schema on SQLite AND Postgres via the app's
     own init_db()/_migrate_db(); assert identical table sets and per-table
     columns. Catches dialect-specific schema drift before a prod cutover.
  B. MIGRATION + UPSERT — _migrate_db() is idempotent (re-runnable, no schema
     change, no error) on both dialects, and the dialect-branched upserts
     (league_members / member_rankings / user_player_skips / the F-1 league
     upsert) behave identically.
  C. LIVE-DATA QUALITY — read-only audit of data/trade_finder.db: orphan
     classification, enum domains, timestamp format, boolean storage.

Postgres plane is skipped (not failed) if no local server is reachable.

Usage:  python3 qa/db/tc_db_001.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
PG_URL = "postgresql://localhost:5432/ftf_qa_parity"
PG_ADMIN = "postgresql://localhost:5432/postgres"
PSQL = "/Applications/Postgres.app/Contents/Versions/latest/bin/psql"
rec = H.CheckRecorder()


def run_probe(database_url: str) -> dict | None:
    env = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(H.ROOT)}
    env.pop("CRON_SECRET", None)
    proc = subprocess.run([sys.executable, "qa/db/_dialect_probe.py"],
                          cwd=H.ROOT, env=env, capture_output=True, text=True, timeout=120)
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return json.loads(line)
    except Exception:
        rec.info(f"probe failed for {database_url}: {proc.stderr[-400:]}")
        return None


def pg_available() -> bool:
    try:
        r = subprocess.run([PSQL, "-h", "localhost", "-p", "5432", "-d", "postgres",
                            "-tAc", "SELECT 1"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and r.stdout.strip() == "1"
    except Exception:
        return False


def pg_reset_db():
    for sql in (f"DROP DATABASE IF EXISTS ftf_qa_parity;",
                f"CREATE DATABASE ftf_qa_parity;"):
        subprocess.run([PSQL, "-h", "localhost", "-p", "5432", "-d", "postgres", "-c", sql],
                       capture_output=True, text=True, timeout=30)


def check_smoke(label: str, probe: dict) -> None:
    m = probe["migration"]
    rec.check(f"{label}:migration-idempotent", m["ran_twice_ok"] and m["schema_stable"],
              f"re-run ok={m['ran_twice_ok']} schema-stable={m['schema_stable']} err={m['error']}")
    s = probe["smoke"]
    rec.check(f"{label}:upserts-ok", s.get("ok"), f"smoke error={s.get('error')}")
    rec.check(f"{label}:F1-second-member", s.get("f1_second_member_ok"),
              f"second-member league upsert ok={s.get('f1_second_member_ok')} "
              f"err={s.get('f1_error')}")
    rec.check(f"{label}:leagues-one-row", s.get("leagues_rows_after_two_members") == 1,
              f"leagues rows after 2 members = {s.get('leagues_rows_after_two_members')} (want 1)")
    rec.check(f"{label}:league-members-idem", s.get("league_members_rows") == 2,
              f"league_members rows = {s.get('league_members_rows')} (want 2, no dup)")
    rec.check(f"{label}:member-rankings-replace", s.get("member_rankings_rows") == 2,
              f"member_rankings rows = {s.get('member_rankings_rows')} (want 2, replace not append)")
    rec.check(f"{label}:skips-idem", s.get("skips_rows") == 1,
              f"user_player_skips rows = {s.get('skips_rows')} (want 1, idempotent)")


def schema_parity(sqlite_p: dict, pg_p: dict) -> None:
    print("\nSCHEMA PARITY — SQLite vs Postgres (fresh init on both)")
    st, pt = set(sqlite_p["tables"]), set(pg_p["tables"])
    rec.check("parity:same-tables", st == pt,
              f"tables match ({len(st)})" if st == pt
              else f"sqlite-only={st - pt} pg-only={pt - st}")
    col_diffs = {}
    for t in sorted(st & pt):
        sc, pc = set(sqlite_p["tables"][t]), set(pg_p["tables"][t])
        if sc != pc:
            col_diffs[t] = {"sqlite_only": sorted(sc - pc), "pg_only": sorted(pc - sc)}
    rec.check("parity:same-columns", not col_diffs,
              "all per-table columns match" if not col_diffs else f"column drift: {col_diffs}")


def live_data_quality() -> None:
    print("\nLIVE-DATA QUALITY — read-only audit of data/trade_finder.db")
    live = H.LIVE_DB

    def q(sql, args=()):
        return H.db_scalar(live, sql, args)

    # Orphans: league_members referencing a non-existent users row.
    orphans = q("SELECT COUNT(*) FROM league_members lm LEFT JOIN users u "
                "ON lm.user_id=u.sleeper_user_id WHERE u.sleeper_user_id IS NULL")
    orphan_users = q("SELECT COUNT(DISTINCT lm.user_id) FROM league_members lm "
                     "LEFT JOIN users u ON lm.user_id=u.sleeper_user_id "
                     "WHERE u.sleeper_user_id IS NULL")
    orphan_with_rank = q("SELECT COUNT(*) FROM league_members lm LEFT JOIN users u "
                         "ON lm.user_id=u.sleeper_user_id WHERE u.sleeper_user_id IS NULL "
                         "AND EXISTS (SELECT 1 FROM member_rankings mr WHERE mr.user_id=lm.user_id)")
    rec.info(f"orphaned league_members: {orphans} rows / {orphan_users} distinct users; "
             f"{orphan_with_rank} have rankings")
    # Benign IFF every orphan is a never-logged-in leaguemate (no rankings, not
    # in trade_matches). A ranked or match-bearing orphan would be a real leak.
    orphan_in_matches = q("SELECT COUNT(*) FROM trade_matches tm LEFT JOIN users u "
                          "ON tm.user_a_id=u.sleeper_user_id WHERE u.sleeper_user_id IS NULL")
    rec.check("live:orphans-benign", orphan_with_rank == 0 and orphan_in_matches == 0,
              f"orphans with rankings={orphan_with_rank}, orphans in trade_matches={orphan_in_matches} "
              f"(both must be 0 — orphans are never-logged-in leaguemates only)")

    # FK integrity on relationships that SHOULD be clean.
    bad_league_owner = q("SELECT COUNT(*) FROM leagues l LEFT JOIN users u "
                         "ON l.user_id=u.sleeper_user_id WHERE u.sleeper_user_id IS NULL")
    rec.check("live:league-owner-fk", bad_league_owner == 0,
              f"{bad_league_owner} leagues with a non-existent importer-owner")

    # Enum domains.
    bad_sd = q("SELECT COUNT(*) FROM swipe_decisions WHERE decision_type NOT IN "
               "('rank','trade','disposition')")
    bad_td = q("SELECT COUNT(*) FROM trade_decisions WHERE decision NOT IN ('like','pass')")
    bad_tm = q("SELECT COUNT(*) FROM trade_matches WHERE status NOT IN "
               "('pending','accepted','declined')")
    bad_fmt = q("SELECT COUNT(*) FROM member_rankings WHERE scoring_format NOT IN "
                "('1qb_ppr','sf_tep') AND scoring_format IS NOT NULL")
    rec.check("live:enum-domains", bad_sd == 0 and bad_td == 0 and bad_tm == 0 and bad_fmt == 0,
              f"swipe={bad_sd} trade_dec={bad_td} match={bad_tm} fmt={bad_fmt} out-of-domain")

    # Timestamp format: ISO-8601 TEXT across a sample of timestamp columns.
    bad_ts = 0
    for tbl, col in [("users", "created_at"), ("swipe_decisions", "created_at"),
                     ("trade_matches", "matched_at"), ("trade_decisions", "created_at")]:
        n = q(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL AND "
              f"({col} NOT LIKE '____-__-__T%' OR length({col}) < 19)")
        bad_ts += n or 0
    rec.check("live:iso-timestamps", bad_ts == 0,
              f"{bad_ts} non-ISO-8601 timestamps across sampled columns")

    # Boolean columns stored strictly as 0/1 (not 'true'/'yes'/NULL surprises).
    bad_bool = 0
    for tbl, col in [("notifications", "is_read"), ("draft_picks", "is_traded"),
                     ("trade_impressions", "likes_you")]:
        n = q(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col} NOT IN (0,1)")
        bad_bool += n or 0
    rec.check("live:boolean-storage", bad_bool == 0,
              f"{bad_bool} boolean cells outside {{0,1}}")

    # Duplicate guards on composite-unique tables.
    dup_lm = q("SELECT COUNT(*) FROM (SELECT league_id,user_id,COUNT(*) c "
               "FROM league_members GROUP BY league_id,user_id HAVING c>1)")
    rec.check("live:no-dup-members", (dup_lm or 0) == 0,
              f"{dup_lm} duplicate (league_id,user_id) pairs in league_members")


def main() -> int:
    print("TC-DB-001 — schema integrity, migration idempotency, SQLite<->Postgres parity")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sqlite_db = SCRATCH / "qa_db_fresh.db"
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(sqlite_db) + suffix)
        if p.exists():
            p.unlink()

    print("\nSQLITE PLANE")
    sqlite_probe = run_probe(f"sqlite:///{sqlite_db}")
    if not rec.check("sqlite:probe-ran", sqlite_probe is not None, "fresh SQLite init + probe"):
        return rec.summary()
    check_smoke("sqlite", sqlite_probe)

    print("\nPOSTGRES PLANE")
    pg_probe = None
    if pg_available():
        pg_reset_db()
        pg_probe = run_probe(PG_URL)
        if rec.check("pg:probe-ran", pg_probe is not None, "fresh Postgres init + probe"):
            check_smoke("pg", pg_probe)
    else:
        rec.info("no local Postgres reachable — Postgres parity plane SKIPPED "
                 "(install/run Postgres.app to cover the prod-cutover gap)")

    if sqlite_probe and pg_probe:
        schema_parity(sqlite_probe, pg_probe)

    live_data_quality()

    return rec.summary(SCRATCH / "TC-DB-001-run.json",
                       meta={"test_case": "TC-DB-001",
                             "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "pg_tested": pg_probe is not None})


if __name__ == "__main__":
    sys.exit(main())
