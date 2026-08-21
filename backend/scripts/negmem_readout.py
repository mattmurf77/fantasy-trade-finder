#!/usr/bin/env python3
"""negmem_readout.py — the R8 operator dump for negative-results memory.

Spec: docs/plans/negative-results-memory/LLD.md §7.1 (output format) and §8.5
(the operator TestFlight checklist, whose expected values ARE these fields — so
runtime behaviour is verified against numbers, not vibes).

Prints `negmem.negmem_readout(...)` as indented JSON. There is no route (OQ-5):
R8 ships as a function plus this script.

Reading it:
  • `allowlisted` is DATA, not a gate — the builder runs with the allowlist
    check BYPASSED, so "why are there no stamps in league X" is answerable.
  • `likes_net` is PRE-CLAMP and readout-only. Do NOT expect
    `n_decayed + likes_net` to equal the gross evidence: the fold clamps at
    zero after every step, so the mass a like actually cancelled can be less.
  • `floored` is RESERVED and always false in v1 — a true means the §4.4 curve
    changed.
  • `dropped_unmapped_partner_ids` must be read WITH `m2`: under
    "killed (…)" or "degraded" the M2 queries never ran, so 0 means
    "not counted", never "no drops".

Usage (from the repo root):
    python3 -m backend.scripts.negmem_readout --user U123 --league 987654321
    python3 -m backend.scripts.negmem_readout --user U123 --league 9876 \
        --as-of 2026-09-01T00:00:00+00:00
    python3 -m backend.scripts.negmem_readout --user U123 --league 9876 --prod

`--prod` points the SAME builder at production Postgres, READ-ONLY: the
connection forces `default_transaction_read_only=on` at session level, so the
server rejects any write whatever the code says. Credentials come from
`DATABASE_URL_PROD` in the gitignored `secrets.local.env` (never a command-line
argument, so the URL stays out of shell history) — the same idiom as
`backend/tools/prod_analytics.py`. Nothing here ever prints a secret.

Exit codes: 0 ok · 1 readout failed · 2 missing/blank prod credentials ·
3 missing model_config seed rows (run init_db).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "secrets.local.env"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import database as db          # noqa: E402
from backend import negmem                  # noqa: E402


def _load_prod_url() -> str:
    """DATABASE_URL_PROD from the environment or secrets.local.env. The value
    is never echoed — only its absence is reported."""
    url = os.environ.get("DATABASE_URL_PROD", "").strip()
    if not url and SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL_PROD="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not url:
        print("DATABASE_URL_PROD is not set in secrets.local.env — paste the "
              "Render external Postgres URL there (never in chat, never on the "
              "command line).", file=sys.stderr)
        raise SystemExit(2)
    if url.startswith("postgres://"):        # Render hands out the old scheme
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _readonly_engine(url: str, statement_timeout_ms: int = 15000):
    from sqlalchemy import create_engine
    return create_engine(
        url, future=True, pool_pre_ping=True,
        connect_args={"options": f"-c default_transaction_read_only=on "
                                 f"-c statement_timeout={statement_timeout_ms}"},
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--user", required=True,
                    help="the deck owner's user id (league identity)")
    ap.add_argument("--league", required=True, help="league id")
    ap.add_argument("--as-of", default=None,
                    help="ISO UTC instant to reconstruct at (default: now)")
    ap.add_argument("--prod", action="store_true",
                    help="run against production Postgres, read-only "
                         "(DATABASE_URL_PROD in secrets.local.env)")
    args = ap.parse_args(argv)

    if args.prod:
        db.engine = _readonly_engine(_load_prod_url())

    try:
        out = negmem.negmem_readout(args.user, args.league, args.as_of)
    except KeyError as err:
        print(f"negmem readout failed: {err}", file=sys.stderr)
        return 3
    except Exception as err:                 # operator tool — loud is correct
        print(f"negmem readout failed: {err}", file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2, sort_keys=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
