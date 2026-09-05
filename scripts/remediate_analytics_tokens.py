"""Offline database remediation of historical auth tokens in user_events.

Run on an explicitly selected offline database, with every app worker stopped:
    python3 scripts/remediate_analytics_tokens.py --database /absolute/offline.db
    python3 scripts/remediate_analytics_tokens.py --database /absolute/offline.db --apply

For PostgreSQL, explicitly supply the NAME of an environment variable containing
an operator-selected maintenance URL (never paste the URL in shell arguments):
    python3 scripts/remediate_analytics_tokens.py --database-url-env REMEDIATION_DB_URL
    python3 scripts/remediate_analytics_tokens.py --database-url-env REMEDIATION_DB_URL --apply

Default is a read-only dry run. No default database or credentials are loaded.
All application writers must be stopped for either database type. Before applying, review counts and arrange recovery
under your restricted backup policy. Backups/exports/WAL may retain credentials;
restrict and expire them, and preserve the revocations if restoring any backup.
This tool does not create a new credential-bearing backup or print tokens.
Restart all workers only after applying: DB deletion cannot evict memory caches.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


PREFIX = "analytics_v1:"


def remediate(database: Path | str, *, apply: bool = False) -> dict:
    """Scrub known server-token writes and revoke exactly matching sessions.

    Match all legacy signup/app_open/league_synced API identifiers, including
    expired/in-memory-only tokens. Also match identifiers in other event types
    if their hash corresponds to a durable session. No user-wide revocation.
    All event copies of identified tokens are nulled in the same transaction.
    """
    if isinstance(database, Path):
        database = database.resolve(strict=True)
        mode = "rw" if apply else "ro"
        url = "sqlite:///" + database.as_uri() + f"?mode={mode}&uri=true"
    else:
        url = database
    engine = create_engine(url, echo=False, hide_parameters=True)
    try:
        if engine.dialect.name not in {"sqlite", "postgresql"}:
            raise ValueError("Unsupported database")
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE" if apply else "BEGIN")
                if not apply:
                    conn.exec_driver_sql("PRAGMA query_only = ON")
            elif not apply:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            else:
                conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
                conn.exec_driver_sql("LOCK TABLE user_events, sessions IN EXCLUSIVE MODE")
            active_hashes = {r[0] for r in conn.execute(text("SELECT token_hash FROM sessions"))}
            candidates = set()
            for sid, source, event_type in conn.execute(text(
                "SELECT DISTINCT session_id, source, event_type FROM user_events "
                "WHERE session_id IS NOT NULL"
            )):
                if not sid or sid.startswith(PREFIX):
                    continue
                digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()
                if digest in active_hashes or (
                    source == "api" and event_type in {"signup", "app_open", "league_synced"}
                ):
                    candidates.add(sid)
            matched_hashes = {
                hashlib.sha256(sid.encode("utf-8")).hexdigest() for sid in candidates
            } & active_hashes
            rows = sum(conn.execute(text(
                "SELECT COUNT(*) FROM user_events WHERE session_id = :sid"
            ), {"sid": sid}).scalar_one() for sid in candidates)
            if apply:
                for sid in candidates:
                    conn.execute(text("UPDATE user_events SET session_id = NULL WHERE session_id = :sid"),
                                 {"sid": sid})
                for digest in matched_hashes:
                    conn.execute(text("DELETE FROM sessions WHERE token_hash = :digest"),
                                 {"digest": digest})
                conn.commit()
            else:
                conn.rollback()
            return {"mode": "apply" if apply else "dry_run", "event_rows": rows,
                    "distinct_identifiers": len(candidates),
                    "durable_sessions_revoked" if apply else "durable_sessions_to_revoke": len(matched_hashes)}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", type=Path,
                        help="Explicit path to existing OFFLINE SQLite database")
    target.add_argument("--database-url-env", help="Name of env var with explicit maintenance URL")
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed remediation")
    args = parser.parse_args()
    try:
        database = args.database or os.environ[args.database_url_env]
        result = remediate(database, apply=args.apply)
    except (OSError, SQLAlchemyError, ValueError, KeyError):
        # Do not expose SQL parameters, paths or credential-bearing row values.
        parser.exit(1, "Remediation failed; check the offline file and required schema.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
