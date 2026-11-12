"""Command line: discover | pull | derive | run | report.

    python3 scripts/sleeper_universe.py run --limit 150
    python3 scripts/sleeper_universe.py report

Logs carry league ids and counts only: never a seed, username, user id or name.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION
from .client import DEFAULT_RATE, MAX_RATE, RateLimitStop, SleeperClient, USER_AGENT
from .derive import derive_all
from .discover import Discoverer
from .identity import Collector, KeyRing
from .pull import fetch_nfl_state, pull
from .report import build_report, format_report, leak_scan
from .store import SEED_FILE, Store

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "sleeper-universe"
DEFAULT_SEASONS = (2024, 2025, 2026)


def code_version() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        rev = ""
    return f"{VERSION}+{rev or 'unknown'}"


def read_seeds(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"seed file not found: {path.name} in the data folder "
                         "(one Sleeper username or user id per line)")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sleeper_universe", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["discover", "pull", "derive", "run", "report"])
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--seeds", type=Path, default=None,
                   help=f"seed file (default <data-dir>/{SEED_FILE})")
    p.add_argument("--seasons", type=int, nargs="+", default=list(DEFAULT_SEASONS))
    p.add_argument("--hops", type=int, default=2)
    p.add_argument("--cap", type=int, default=3000, help="max kept lineages")
    p.add_argument("--limit", type=int, default=None, help="max league-seasons to pull this run")
    p.add_argument("--refresh-incomplete", action="store_true",
                   help="re-pull league-seasons whose status was not 'complete'")
    p.add_argument("--rate", type=float, default=DEFAULT_RATE,
                   help=f"requests per second (max {MAX_RATE})")
    p.add_argument("--max-429", type=int, default=5, help="stop after N consecutive 429s")
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--user-agent", default=USER_AGENT)
    p.add_argument("--json", action="store_true", help="report: print JSON")
    p.add_argument("--allow-new-key", action="store_true",
                   help="accept an HMAC key that differs from the store's (breaks linkage)")
    return p


def main(argv=None, *, transport=None, sleep=None, clock=None, env=None, log=print) -> int:
    args = build_parser().parse_args(argv)
    if not (0 < args.rate <= MAX_RATE):
        raise SystemExit(f"--rate must be in (0, {MAX_RATE}]")
    data_dir = args.data_dir
    store = Store(data_dir)
    ring = KeyRing.load(data_dir, env=env)
    store.check_key(ring.fingerprint(), args.allow_new_key)
    seasons = sorted(set(args.seasons))

    if args.command == "report":
        rep = build_report(store.conn)
        leak = leak_scan(data_dir, ring, exclude=_exclusions(args, data_dir))
        if args.json:
            log(json.dumps({"report": rep, "leak_scan": leak}, indent=2, sort_keys=True))
        else:
            log(format_report(rep, leak))
        store.close()
        return 0 if leak["ok"] else 4

    if args.command == "derive":
        log(json.dumps(derive_all(store.conn)))
        store.close()
        return 0

    params = {"seasons": seasons, "hops": args.hops, "cap": args.cap, "limit": args.limit,
              "rate": args.rate, "max_429": args.max_429,
              "refresh_incomplete": args.refresh_incomplete, "key_source": ring.source}
    kw = {}
    if sleep is not None:
        kw["sleep"] = sleep
    if clock is not None:
        kw["clock"] = clock
    client = SleeperClient(transport, rate=args.rate, timeout=args.timeout,
                           max_consecutive_429=args.max_429, user_agent=args.user_agent, **kw)
    col = Collector()
    tclock = clock or time.monotonic
    t0 = tclock()
    run_id = store.start_run(args.command, _now(), params, code_version())
    status, summary, leak, state, code = "error", {}, None, None, 1
    try:
        if args.command in ("discover", "run"):
            seeds = read_seeds(args.seeds or data_dir / SEED_FILE)
            params["n_seeds"] = len(seeds)
            d = Discoverer(store, client, ring, col, seasons=seasons, max_hops=args.hops,
                           cap=args.cap, log=log)
            summary["discover"] = d.run(seeds)
            del seeds
            log(f"discover: {json.dumps(summary['discover'])}")
        if args.command in ("pull", "run"):
            state = fetch_nfl_state(client)
            summary["pull"] = pull(store, client, ring, col, seasons=seasons, run_id=run_id,
                                   limit=args.limit, refresh_incomplete=args.refresh_incomplete,
                                   nfl_state=state, log=log, clock=tclock)
            log(f"pull: {json.dumps(summary['pull'])}")
            summary["derive"] = derive_all(store.conn)
            log(f"derive: {json.dumps(summary['derive'])}")
        leak = leak_scan(data_dir, ring, names=col.names, raw_ids=col.raw_user_ids,
                         exclude=_exclusions(args, data_dir))
        log(f"leak scan: {'PASS' if leak['ok'] else 'FAIL'} ({leak['files_scanned']} files)")
        status, code = ("ok", 0) if leak["ok"] else ("leak_scan_failed", 4)
    except RateLimitStop as e:
        status, code = "stopped_429", 3
        log(str(e))
    except KeyboardInterrupt:
        status = "interrupted"
        raise
    finally:
        store.finish_run(run_id, _now(), status, client.requests, round(tclock() - t0, 3),
                         summary, leak, state)
        store.close()
    return code


def _exclusions(args, data_dir: Path):
    from .identity import KEY_FILE
    ex = [SEED_FILE, KEY_FILE]
    if args.seeds is not None:
        try:
            ex.append(str(Path(args.seeds).resolve().relative_to(Path(data_dir).resolve())))
        except ValueError:
            pass
    return tuple(ex)


if __name__ == "__main__":
    sys.exit(main())
