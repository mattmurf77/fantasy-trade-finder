"""prod_analytics.py — run the analytics reports against PRODUCTION, read-only.

Why this exists: the local dev DB (`data/trade_finder.db`) contains only
test-suite artifacts, so every number computed there is noise. Real usage lives
in Render's Postgres. This points the same report code at prod WITHOUT the app,
without a deploy, and without any possibility of writing.

Safety (belt and braces — this touches production user data):
  • Connection forces `default_transaction_read_only=on` at the session level,
    so the SERVER rejects any write this process attempts, whatever the code says.
  • A `statement_timeout` bounds runaway scans against the live DB.
  • Only `analytics_queries` report builders run; nothing here calls a writer.
  • The prod engine is injected as `ro_engine` only — `db.engine` (the write
    engine) is left pointed at local SQLite and is never used by reports.

Usage (from repo root):
    python3 -m backend.tools.prod_analytics --diagnose
    python3 -m backend.tools.prod_analytics --report overview --days 28
    python3 -m backend.tools.prod_analytics --report rankquality
    python3 -m backend.tools.prod_analytics --list

Credentials: `DATABASE_URL_PROD` in `secrets.local.env` (gitignored, never
passed on the command line so it stays out of shell history).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "secrets.local.env"


def _load_prod_url() -> str:
    """Read DATABASE_URL_PROD from secrets.local.env (or the env var)."""
    url = os.environ.get("DATABASE_URL_PROD", "").strip()
    if not url and SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL_PROD="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not url:
        sys.exit("DATABASE_URL_PROD is not set in secrets.local.env — "
                 "paste the Render external Postgres URL there (never in chat).")
    # Render hands out postgres://; SQLAlchemy 2.x requires postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _connect_readonly(url: str, statement_timeout_ms: int = 15000):
    from sqlalchemy import create_engine
    return create_engine(
        url, future=True, pool_pre_ping=True,
        connect_args={"options": f"-c default_transaction_read_only=on "
                                 f"-c statement_timeout={statement_timeout_ms}"},
    )


def _diagnose(conn):
    """Answer the operator's actual question: is eventing working in prod, and
    do MY events show up? Prints a per-day/per-type/per-user picture."""
    from sqlalchemy import text
    out = []

    def q(sql, **p):
        return conn.execute(text(sql), p).fetchall()

    total = q("SELECT COUNT(*) FROM user_events")[0][0]
    out.append(f"user_events rows (all time): {total:,}")
    if not total:
        out.append("\n  ⚠  ZERO events in production. Either no traffic since the "
                   "table was created, or record_event is failing silently.")
        return "\n".join(out)

    rng = q("SELECT MIN(occurred_at), MAX(occurred_at) FROM user_events")[0]
    out.append(f"first event: {rng[0]}")
    out.append(f"last  event: {rng[1]}")

    out.append("\n--- events per day (last 21) ---")
    for d, n, t, u in q(
        "SELECT substr(occurred_at,1,10) d, COUNT(*) n, COUNT(DISTINCT event_type) t,"
        " COUNT(DISTINCT user_id) u FROM user_events GROUP BY substr(occurred_at,1,10)"
        " ORDER BY d DESC LIMIT 21"
    ):
        out.append(f"  {d}  rows={n:<7} types={t:<3} users={u}")

    out.append("\n--- event types (all time) ---")
    for et, n, u in q(
        "SELECT event_type, COUNT(*) n, COUNT(DISTINCT user_id) u FROM user_events"
        " GROUP BY event_type ORDER BY n DESC LIMIT 30"
    ):
        out.append(f"  {et:34} rows={n:<8} users={u}")

    out.append("\n--- client-capture health (envelope fill) ---")
    for col in ("event_id", "device_id", "platform", "screen", "client_ts",
                "session_id", "experiments"):
        n = q(f"SELECT COUNT({col}) FROM user_events")[0][0]
        pct = (n / total * 100) if total else 0
        state = "client events flowing" if n else "NULL — server-only"
        out.append(f"  {col:12} {n:>8,} ({pct:5.1f}%)  {state}")

    out.append("\n--- top users by event volume ---")
    for uid, n, first, last in q(
        "SELECT user_id, COUNT(*) n, MIN(occurred_at), MAX(occurred_at)"
        " FROM user_events GROUP BY user_id ORDER BY n DESC LIMIT 12"
    ):
        out.append(f"  {str(uid)[:26]:28} rows={n:<7} {str(first)[:10]} → {str(last)[:16]}")

    # Days-active-per-user is the direct answer to "do you see me most days?"
    out.append("\n--- distinct active days per user (last 30d) ---")
    since = (date.today() - timedelta(days=30)).isoformat()
    for uid, days, n in q(
        "SELECT user_id, COUNT(DISTINCT substr(occurred_at,1,10)) d, COUNT(*) n"
        " FROM user_events WHERE substr(occurred_at,1,10) >= :since"
        " GROUP BY user_id ORDER BY d DESC LIMIT 12", since=since
    ):
        out.append(f"  {str(uid)[:26]:28} active_days={days:<4} events={n}")

    users = q("SELECT COUNT(*) FROM users")[0][0]
    out.append(f"\nusers table: {users:,} rows")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Run FTF analytics against PROD (read-only).")
    ap.add_argument("--report", help="report name (see --list)")
    ap.add_argument("--days", type=int, default=28, help="window size, default 28")
    ap.add_argument("--start"), ap.add_argument("--end")
    ap.add_argument("--anchor", help="journeys anchor event_type")
    ap.add_argument("--include-demo", action="store_true")
    ap.add_argument("--diagnose", action="store_true",
                    help="eventing health check: per-day/type/user + envelope fill")
    ap.add_argument("--list", action="store_true", help="list report names")
    ap.add_argument("--json", action="store_true", help="raw JSON instead of a summary")
    args = ap.parse_args()

    # Import AFTER arg parsing so --list/--help never touch the DB layer.
    from .. import analytics_queries as aq

    if args.list:
        print("reports:", ", ".join(aq.VALID_REPORTS))
        return

    url = _load_prod_url()
    safe_host = url.split("@")[-1].split("/")[0] if "@" in url else "?"
    print(f"● connecting READ-ONLY to prod ({safe_host}) …", file=sys.stderr)
    engine = _connect_readonly(url)

    # Point the report layer at prod. db.engine (the WRITE engine) is deliberately
    # left alone — reports only ever read through ro_engine.
    from .. import database as db
    db.ro_engine = engine

    if args.diagnose:
        with engine.connect() as conn:
            print(_diagnose(conn))
        return

    if not args.report:
        sys.exit("pass --report <name> or --diagnose (see --list)")

    end = args.end or date.today().isoformat()
    start = args.start or (date.fromisoformat(end) - timedelta(days=args.days - 1)).isoformat()
    env, _ = aq.run_report(args.report, start=start, end=end,
                           include_demo=args.include_demo, anchor=args.anchor)

    if args.json:
        print(json.dumps(env, indent=1, default=str))
        return

    print(f"\n=== {env['report']}  {env['window']['start']} → {env['window']['end']} ===")
    if env.get("summary"):
        print("\nsummary:")
        for k, v in env["summary"].items():
            print(f"  {k}: {v}")
    rows = env.get("rows")
    if isinstance(rows, list):
        print(f"\nrows: {len(rows)}")
        for r in rows[:25]:
            print("  " + json.dumps(r, default=str)[:180])
    else:
        print("\n" + json.dumps(rows, indent=1, default=str)[:3000])
    if env.get("caveats"):
        print("\ncaveats:")
        for c in env["caveats"]:
            print(f"  [{c['code']}] {c['scope']} — {c['detail'][:140]}")


if __name__ == "__main__":
    main()
