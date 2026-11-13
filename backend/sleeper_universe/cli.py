"""Command line: discover | pull | derive | run | report.

    python3 scripts/sleeper_universe.py run --limit 150
    python3 scripts/sleeper_universe.py report

Logs carry league ids and counts only: never a seed, username, user id or name.

Exit codes: 0 ok; 1 error; 3 stopped on 429s; 4 leak scan failed; 5 blocked
(403 / Cloudflare); 6 a 200 that is not JSON; 7 circuit breaker (outage or
three failed leagues in a row); 8 another crawler process holds the lock;
9 report: derived tables were written by an older derive (run ``derive``).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION
from .client import DEFAULT_RATE, HardStop, MAX_429, MAX_RATE, SleeperClient, USER_AGENT
from .derive import derive_all
from .discover import Discoverer
from .identity import Collector, KeyRing, default_key_path
from .pull import fetch_nfl_state, pull
from .report import build_report, format_report, leak_scan
from .store import SEED_FILE, Store

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "sleeper-universe"
DEFAULT_SEASONS = (2024, 2025, 2026)
# Machine-wide, not per data folder: one crawler process on this machine at a
# time, whatever folder it writes, so the request rate cannot be multiplied.
LOCK_PATH = Path("/tmp/ftf-sleeper-universe-crawler.lock")
LOCK_HELD_EXIT = 8
DERIVE_NEEDED_EXIT = 9
REQUESTS_PER_LEAGUE_SEASON = 44
DISCOVERY_REQUESTS_PER_LINEAGE = 8   # estimate; the pilot measures it


class LockHeld(SystemExit):
    pass


def acquire_lock(path: Path = LOCK_PATH):
    """Exclusive, non-blocking flock held for the life of the process (the
    OS releases it if the process dies). Raises LockHeld if another crawler
    holds it."""
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise LockHeld(f"another Sleeper crawler process is running on this machine "
                       f"(lock {path}); only one may run at a time") from None
    return fd


def release_lock(fd) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def planned_budget(cap: int, n_seasons: int) -> tuple[int, int]:
    """(pull, discovery) request estimates for a run up to ``cap`` lineages."""
    return (cap * n_seasons * REQUESTS_PER_LEAGUE_SEASON,
            cap * DISCOVERY_REQUESTS_PER_LINEAGE)


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
    p.add_argument("--retry-failed", action="store_true",
                   help="pull again league-seasons that failed MAX_PULL_ATTEMPTS times")
    p.add_argument("--refresh-incomplete", action="store_true",
                   help="re-pull league-seasons whose status was not 'complete'")
    p.add_argument("--rate", type=float, default=DEFAULT_RATE,
                   help=f"requests per second (max {MAX_RATE})")
    p.add_argument("--max-429", type=int, default=5,
                   help=f"stop after N consecutive 429s (1 to {MAX_429})")
    p.add_argument("--nfl-schedule", type=Path, default=None,
                   help="nflverse games CSV; with --player-teams, snapshots use each "
                        "player's own kickoff (derive, pull, run)")
    p.add_argument("--player-teams", type=Path, default=None,
                   help='JSON {"<season>": {"<player_id>": "<team>"}} or {"<player_id>": "<team>"}')
    p.add_argument("--key-file", type=Path, default=None,
                   help="HMAC key file (default ~/.config/ftf-sleeper-universe/hmac.key; "
                        "must be outside the data folder)")
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--user-agent", default=USER_AGENT)
    p.add_argument("--json", action="store_true", help="report: print JSON")
    p.add_argument("--allow-new-key", action="store_true",
                   help="accept an HMAC key that differs from the store's (breaks linkage)")
    return p


def main(argv=None, *, transport=None, sleep=None, clock=None, env=None, log=print,
         lock_path: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (0 < args.rate <= MAX_RATE):
        raise SystemExit(f"--rate must be in (0, {MAX_RATE}]")
    if not (1 <= args.max_429 <= MAX_429):
        raise SystemExit(f"--max-429 must be in [1, {MAX_429}]")
    data_dir = args.data_dir
    lock = None
    if args.command in ("discover", "pull", "run"):
        try:
            lock = acquire_lock(lock_path or LOCK_PATH)
        except LockHeld as e:
            log(str(e))
            return LOCK_HELD_EXIT
    try:
        return _main(args, data_dir, transport, sleep, clock, env, log)
    finally:
        if lock is not None:
            release_lock(lock)


def _main(args, data_dir, transport, sleep, clock, env, log) -> int:
    ring = KeyRing.load(args.key_file or default_key_path(), env=env, data_dir=data_dir)
    store = Store(data_dir)
    store.check_key(ring.fingerprint(), args.allow_new_key)
    seasons = sorted(set(args.seasons))

    if args.command == "report":
        rep = build_report(store.conn)
        leak = leak_scan(data_dir, ring, report_mode=True)
        if args.json:
            log(json.dumps({"report": rep, "leak_scan": leak}, indent=2, sort_keys=True))
        else:
            log(format_report(rep, leak))
        store.close()
        if rep.get("derive_needed"):
            return DERIVE_NEEDED_EXIT
        return 0 if leak["ok"] else 4

    if args.command == "derive":
        log(json.dumps(derive_all(store.conn, clock=_clock(args))))
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
    status, summary, state, code = "error", {}, None, 1
    try:
        if args.command == "run":
            pull_est, disc_est = planned_budget(args.cap, len(seasons))
            log(f"planned budget: up to {args.cap} lineages x {len(seasons)} seasons x "
                f"{REQUESTS_PER_LEAGUE_SEASON} = {pull_est} pull requests, plus about {disc_est} "
                f"for discovery; about {(pull_est + disc_est) / args.rate / 3600:.1f} h at "
                f"{args.rate:g} requests a second (limit {args.limit or 'none'})")
        if args.command in ("discover", "run"):
            seeds = read_seeds(args.seeds or data_dir / SEED_FILE)
            params["n_seeds"] = len(seeds)
            d = Discoverer(store, client, ring, col, seasons=seasons, max_hops=args.hops,
                           cap=args.cap, log=log)
            summary["discover"] = d.run(seeds)
            del seeds
            log(f"discover: {json.dumps(summary['discover'])}")
        if args.command in ("pull", "run"):
            if args.retry_failed:
                log(f"retry-failed: {store.reset_failures()} failed league-seasons requeued")
            queued = len(store.leagues_to_pull(seasons, args.refresh_incomplete))
            n = min(queued, args.limit) if args.limit is not None else queued
            log(f"pull plan: {n} league-seasons x {REQUESTS_PER_LEAGUE_SEASON} = about "
                f"{n * REQUESTS_PER_LEAGUE_SEASON} requests, about "
                f"{n * REQUESTS_PER_LEAGUE_SEASON / args.rate / 60:.0f} min at {args.rate:g}/s")
            state = fetch_nfl_state(client)
            summary["pull"] = pull(store, client, ring, col, seasons=seasons, run_id=run_id,
                                   limit=args.limit, refresh_incomplete=args.refresh_incomplete,
                                   nfl_state=state, log=log, clock=tclock)
            log(f"pull: {json.dumps(summary['pull'])}")
            if client.nulls:
                log(f"null answers accepted as none, by endpoint: {json.dumps(dict(client.nulls))}")
            summary["derive"] = derive_all(store.conn, clock=_clock(args))
            log(f"derive: {json.dumps(summary['derive'])}")
        status, code = "ok", 0
    except HardStop as e:
        status, code = e.status, e.exit_code
        log(str(e))
    except KeyboardInterrupt:
        status = "interrupted"
        raise
    finally:
        summary["null_as_none"] = dict(client.nulls)
        store.finish_run(run_id, _now(), status, client.requests, round(tclock() - t0, 3),
                         summary, None, state)
        store.close()
    # The scan runs after everything the run writes, finish_run included. Its
    # own result (file names and counts only) is the one write after it.
    leak = leak_scan(data_dir, ring, names=col.name_sources, raw_ids=col.raw_user_ids)
    log(f"leak scan: {'PASS' if leak['ok'] else 'FAIL'} ({leak['files_scanned']} files; "
        f"ambiguous names skipped: {leak.get('ambiguous_names_skipped', 0)})")
    store = Store(data_dir)
    store.record_leak(run_id, leak)
    store.close()
    if not leak["ok"] and code == 0:
        code = 4
    return code


def _clock(args):
    from .reconstruct import SnapshotClock, load_kickoffs
    if bool(args.nfl_schedule) != bool(args.player_teams):
        raise SystemExit("--nfl-schedule and --player-teams go together")
    if not args.nfl_schedule:
        return SnapshotClock()
    return SnapshotClock(load_kickoffs(args.nfl_schedule),
                         json.loads(Path(args.player_teams).read_text()))


if __name__ == "__main__":
    sys.exit(main())
