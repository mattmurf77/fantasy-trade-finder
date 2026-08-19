#!/usr/bin/env python3
"""Fetch and update FTF in-app feedback via the admin API.

Usage (run from anywhere inside the repo):
  python3 .claude/skills/feedback/scripts/fetch_feedback.py list
  python3 .claude/skills/feedback/scripts/fetch_feedback.py list --all          # include closed items
  python3 .claude/skills/feedback/scripts/fetch_feedback.py list --json        # raw JSON instead of a table
  python3 .claude/skills/feedback/scripts/fetch_feedback.py set 112 planned    # set status
  python3 .claude/skills/feedback/scripts/fetch_feedback.py set 112 in_progress --severity bug

Auth: reads CRON_SECRET from secrets.local.env at the repo root and sends it
as X-Cron-Secret (same pattern as /api/cron/*). Base URL defaults to prod;
override with --base http://localhost:5000 for local testing.

Open = status in (new, planned, in_progress). fixed/shipped/declined are closed.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROD_BASE = "https://fantasy-trade-finder.onrender.com"
OPEN_STATUSES = ("new", "planned", "in_progress")
STATUSES = ("new", "planned", "in_progress", "fixed", "shipped", "declined")
SEVERITIES = ("bug", "polish", "idea")


def repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "secrets.local.env").exists() or (parent / ".git").exists():
            return parent
    sys.exit("Could not locate repo root (no secrets.local.env or .git found)")


def cron_secret() -> str:
    env = repo_root() / "secrets.local.env"
    if not env.exists():
        sys.exit(f"Missing {env} — CRON_SECRET is required for the admin API")
    for line in env.read_text().splitlines():
        if line.startswith("CRON_SECRET="):
            val = line.split("=", 1)[1].strip()
            if val:
                return val
    sys.exit("CRON_SECRET is blank in secrets.local.env — ask the operator to fill it in")


def request(base: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(
        base + path,
        method=method,
        headers={"X-Cron-Secret": cron_secret(), "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {path}: {e.read().decode()[:500]}")


def fetch_all(base: str) -> list:
    items, since = [], 0
    while True:
        page = request(base, f"/api/feedback/admin?since_id={since}&limit=100")
        items.extend(page["items"])
        if page["count"] < 100:
            return items
        since = page["next_since_id"]


def cmd_list(args) -> None:
    items = fetch_all(args.base)
    if not args.all:
        items = [i for i in items if (i.get("status") or "new") in OPEN_STATUSES]
    if args.json:
        print(json.dumps(items, indent=2))
        return
    if not items:
        print("No open feedback.")
        return
    print("| # | Sev | Status | Screen | Ver | User | Feedback |")
    print("|---|-----|--------|--------|-----|------|----------|")
    for i in items:
        text = (i.get("text") or "").replace("\n", " ").replace("|", "\\|")
        if len(text) > 110:
            text = text[:107] + "..."
        print(f"| {i['id']} | {i.get('severity') or '?'} | {i.get('status') or 'new'} "
              f"| {i.get('screen') or '?'} | {i.get('app_version') or '?'} "
              f"| {i.get('username') or 'anon'} | {text} |")
    print(f"\n{len(items)} open item(s).")


def cmd_set(args) -> None:
    body = {}
    if args.status:
        body["status"] = args.status
    if args.severity:
        body["severity"] = args.severity
    result = request(args.base, f"/api/feedback/admin/{args.id}/status", "PUT", body)
    print(json.dumps(result, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=PROD_BASE, help="API base URL (default: prod)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List feedback (open only by default)")
    p_list.add_argument("--all", action="store_true", help="Include closed items")
    p_list.add_argument("--json", action="store_true", help="Raw JSON output")
    p_list.set_defaults(func=cmd_list)

    p_set = sub.add_parser("set", help="Set status/severity on one item")
    p_set.add_argument("id", type=int)
    p_set.add_argument("status", nargs="?", choices=STATUSES)
    p_set.add_argument("--severity", choices=SEVERITIES)
    p_set.set_defaults(func=cmd_set)

    args = ap.parse_args()
    if args.cmd == "set" and not args.status and not args.severity:
        ap.error("set requires a status and/or --severity")
    args.func(args)


if __name__ == "__main__":
    main()
