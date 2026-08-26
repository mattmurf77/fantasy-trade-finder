#!/usr/bin/env python3
"""set_knob.py — the blessed CLI for model_config knob flips (M1, fit-challenger).

Why a CLI instead of raw SQL: every write here goes through
`PUT /api/admin/config/<key>`, which (a) appends a `model_config_changes` row
with a `source`, so measurement windows can be censored at the logged
timestamp (PLAN-v2 R-5), and (b) triggers the server's live `reload_config()`
pair, so the flip takes effect without a deploy or restart. A direct prod DB
write would log the change and change NOTHING until restart — never do that.

Usage (from repo root):
    python3 scripts/set_knob.py KEY VALUE [--base URL] [--source NAME] [--local]

Credentials: `CRON_SECRET` (and optionally `FTF_API_BASE`) come from the
gitignored `secrets.local.env` at the repo root, or the environment — never
from a CLI arg, never prompted, never printed (repo secrets convention).

`--local` writes the local DB directly via `backend.database.set_config`
(source `operator-local`); a RUNNING local server still reloads only via the
PUT route or a restart.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SECRETS = REPO / "secrets.local.env"

UNKNOWN_KEY_MSG = ("unknown key {key!r} — every knob needs its "
                   "_MODEL_CONFIG_DEFAULTS row (fit-challenger LLD §4)")


def _from_secrets(name: str) -> str:
    """Env var first, then secrets.local.env (the prod_analytics idiom)."""
    val = os.environ.get(name, "").strip()
    if not val and SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return val


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Flip one model_config knob through the logged, "
                    "live-reloading admin route.")
    ap.add_argument("key")
    ap.add_argument("value")
    ap.add_argument("--base", help="API base URL (default: FTF_API_BASE from "
                                   "secrets.local.env)")
    ap.add_argument("--source", default="operator",
                    help="attribution written to model_config_changes.source "
                         "(default: operator)")
    ap.add_argument("--local", action="store_true",
                    help="write the local DB directly instead of the route")
    args = ap.parse_args()

    # Refusal 1 — model_config is Float-only.
    try:
        value = float(args.value)
    except ValueError:
        sys.exit(f"refusing: VALUE {args.value!r} is not a float — "
                 "model_config values are Float-only")

    now = datetime.now(timezone.utc).isoformat()

    if args.local:
        # Refusal 5 — a direct write against prod Postgres would skip the
        # live reload; use the route.
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if db_url and not db_url.startswith("sqlite"):
            sys.exit("refusing: --local with DATABASE_URL pointing at a "
                     f"non-SQLite URL ({db_url.split('@')[-1]}) — a direct "
                     "write would skip the live reload_config(); use the "
                     "PUT route (drop --local)")
        sys.path.insert(0, str(REPO))
        from backend.database import set_config  # noqa: PLC0415
        try:
            result = set_config(args.key, value, source="operator-local")
        except KeyError:
            sys.exit("refusing: " + UNKNOWN_KEY_MSG.format(key=args.key))
        print(f"{result['key']}: {result['old_value']} -> {result['value']} "
              f"(source=operator-local, logged {now})")
        print("note: a RUNNING local server reloads config only via the PUT "
              "route or a restart.")
        return

    # Refusal 4 — no base URL resolvable in default mode.
    base = (args.base or _from_secrets("FTF_API_BASE")).strip()
    if not base:
        sys.exit("refusing: no API base URL — pass --base or set "
                 "FTF_API_BASE in secrets.local.env")

    # Refusal 3 — the secret lives in the file, never in chat or argv.
    secret = _from_secrets("CRON_SECRET")
    if not secret:
        sys.exit("refusing: CRON_SECRET is not set in secrets.local.env — "
                 "fill it in there (never paste it into chat)")

    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/admin/config/{args.key}",
        method="PUT",
        data=json.dumps({"value": value, "source": args.source}).encode(),
        headers={"Content-Type": "application/json", "X-Cron-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Refusal 2 — the route 404s on an unregistered key.
        if e.code == 404:
            sys.exit("refusing: " + UNKNOWN_KEY_MSG.format(key=args.key))
        sys.exit(f"refusing: route returned HTTP {e.code}: "
                 f"{e.read().decode(errors='replace')[:200]}")
    except urllib.error.URLError as e:
        sys.exit(f"refusing: could not reach {base}: {e.reason}")

    print(f"{result['key']}: {result.get('old_value')} -> {result['value']} "
          f"(source={args.source}, logged {now})")


if __name__ == "__main__":
    main()
