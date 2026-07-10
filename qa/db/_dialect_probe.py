"""Dialect probe — run by TC-DB-001 once per backend (SQLite, Postgres).

Given DATABASE_URL in the env, builds a fresh schema, then emits a JSON
snapshot on stdout describing: the schema (tables -> columns), migration
idempotency, and a dialect-branched upsert smoke battery (including the
F-1 second-member league upsert that must NOT raise post-fix).

Invoked in a subprocess so backend.database binds its module-level engine to
the right DATABASE_URL at import.
"""
import json
import sys

import backend.database as db
from sqlalchemy import inspect, text


def schema_snapshot():
    insp = inspect(db.engine)
    tables = {}
    indexes = {}
    for t in sorted(insp.get_table_names()):
        tables[t] = sorted(c["name"] for c in insp.get_columns(t))
        idx = []
        for ix in insp.get_indexes(t):
            idx.append(tuple(ix.get("column_names") or []))
        # include unique constraints as index-like coverage
        for uc in insp.get_unique_constraints(t):
            idx.append(tuple(uc.get("column_names") or []))
        indexes[t] = sorted(str(x) for x in idx)
    return tables, indexes


def migration_idempotency():
    """Run the additive migration a second time; nothing should change or throw."""
    before, before_idx = schema_snapshot()
    error = None
    try:
        db._migrate_db()
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    after, after_idx = schema_snapshot()
    return {
        "ran_twice_ok": error is None,
        "error": error,
        "schema_stable": before == after and before_idx == after_idx,
    }


def _count(table, where="", args=None):
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with db.engine.connect() as c:
        return c.execute(text(sql), args or {}).scalar()


def upsert_smoke():
    """Exercise the dialect-branched upserts and the F-1 fix."""
    out = {}
    LG, U1, U2 = "qa_probe_lg", "qa_probe_u1", "qa_probe_u2"
    try:
        db.upsert_user(U1, username="u1")
        db.upsert_user(U2, username="u2")
        # F-1: first member imports the league, second member must NOT crash.
        db.upsert_league(LG, U1, "QA", "2026", ["1", "2"], [])
        f1_err = None
        try:
            db.upsert_league(LG, U2, "QA", "2026", ["3", "4"], [])
        except Exception as e:  # noqa: BLE001
            f1_err = f"{type(e).__name__}: {e}"
        out["f1_second_member_ok"] = f1_err is None
        out["f1_error"] = f1_err
        out["leagues_rows_after_two_members"] = _count(
            "leagues", "sleeper_league_id=:l", {"l": LG})  # must be 1 (PK = league_id)

        # league_members: bulk upsert, idempotent (newest-wins, no dup).
        members = [{"user_id": U1, "username": "u1", "player_ids": ["1", "2"]},
                   {"user_id": U2, "username": "u2", "player_ids": ["3", "4"]}]
        db.upsert_league_members(LG, members)
        db.upsert_league_members(LG, members)            # second call = idempotent
        out["league_members_rows"] = _count(
            "league_members", "league_id=:l", {"l": LG})  # must be 2

        # member_rankings: replace-snapshot, idempotent count.
        ranks = [{"player_id": "1", "elo": 1500.0}, {"player_id": "2", "elo": 1490.0}]
        db.upsert_member_rankings(U1, LG, ranks, "1qb_ppr")
        db.upsert_member_rankings(U1, LG, ranks, "1qb_ppr")  # replace, not append
        out["member_rankings_rows"] = _count(
            "member_rankings", "user_id=:u AND league_id=:l", {"u": U1, "l": LG})  # 2

        # user_player_skips: INSERT OR IGNORE / ON CONFLICT idempotent.
        db.add_skip(U1, "1", "1qb_ppr")
        db.add_skip(U1, "1", "1qb_ppr")                  # idempotent
        out["skips_rows"] = _count(
            "user_player_skips", "user_id=:u", {"u": U1})  # 1
        out["ok"] = True
        out["error"] = None
    except Exception as e:  # noqa: BLE001
        out["ok"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def main():
    db.init_db()
    tables, indexes = schema_snapshot()
    print(json.dumps({
        "dialect": "sqlite" if db.DATABASE_URL.startswith("sqlite") else "postgresql",
        "tables": tables,
        "indexes": indexes,
        "migration": migration_idempotency(),
        "smoke": upsert_smoke(),
    }))


if __name__ == "__main__":
    main()
