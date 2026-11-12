"""Dated market values (DynastyProcess + KeepTradeCut) for the Sleeper
trade-universe research store. Research tool; the app never imports it.

Library: `backend/universe_values.py` (store, DP history, lookups, coverage)
and `backend/ktc_history.py` (KTC pull + ingest). Design note:
`docs/plans/sleeper-trade-universe/values-history.md`.

    # DynastyProcess (network only in clone-dp; git may fetch blobs lazily in build-dp)
    python3 scripts/universe_values.py clone-dp --dest data/sleeper-universe/dp-data
    python3 scripts/universe_values.py inspect-dp --repo data/sleeper-universe/dp-data
    python3 scripts/universe_values.py build-dp --repo data/sleeper-universe/dp-data

    # KeepTradeCut (pull-ktc is the network step: ~540 pages, one per 3 s)
    python3 scripts/universe_values.py pull-ktc [--extra extra_slugs.txt]
    python3 scripts/universe_values.py ingest-ktc --repo data/sleeper-universe/dp-data

    # Reading
    python3 scripts/universe_values.py coverage [--lookups traded.csv]
    python3 scripts/universe_values.py value-on --date 2024-10-01 --asset 4046 --format sf

Writes only under data/sleeper-universe/ (git-ignored) unless --db/--out say otherwise.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import ktc_history as kh  # noqa: E402
from backend import universe_values as uv  # noqa: E402


def _date(s):
    return dt.date.fromisoformat(s)


def _crosswalk(args) -> uv.DPCrosswalk:
    if args.crosswalk_csv:
        with open(args.crosswalk_csv, encoding="utf-8") as f:
            return uv.crosswalk_from_text(f.read())
    if not args.repo:
        sys.exit("need --repo (a DynastyProcess clone) or --crosswalk-csv")
    r = uv.GitReader(args.repo)
    try:
        text = r.read("HEAD", uv.PLAYERIDS_PATH)
    finally:
        r.close()
    if text is None:
        sys.exit("no %s at HEAD in %s" % (uv.PLAYERIDS_PATH, args.repo))
    return uv.crosswalk_from_text(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("clone-dp", help="blobless clone of the DynastyProcess data repo (NETWORK)")
    p.add_argument("--dest", required=True)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("inspect-dp", help="list distinct file headers over the history")
    p.add_argument("--repo", required=True)
    p.add_argument("--start", type=_date, default=uv.DEFAULT_START)

    p = sub.add_parser("build-dp", help="rebuild source 'dp' from a local clone")
    p.add_argument("--repo", required=True)
    p.add_argument("--db", default=uv.DEFAULT_DB)
    p.add_argument("--start", type=_date, default=uv.DEFAULT_START)
    p.add_argument("--end", type=_date)
    p.add_argument("--crosswalk-csv", help="db_playerids.csv to use instead of the clone's HEAD copy")

    p = sub.add_parser("pull-ktc", help="fetch KTC pages into a checkpoint dir (NETWORK)")
    p.add_argument("--out", default=kh.DEFAULT_OUT)
    p.add_argument("--interval", type=float, default=3.0, help="seconds between requests (min 1)")
    p.add_argument("--extra", help="file of extra slugs / KTC ids, one per line")
    p.add_argument("--refresh-list", action="store_true", help="re-fetch the rankings page")
    p.add_argument("--keep-html", action="store_true", help="debug: keep raw HTML (about 4 MB a page)")
    p.add_argument("--limit", type=int, help="fetch at most N pages this run")

    p = sub.add_parser("ingest-ktc", help="rebuild source 'ktc' from the checkpoint dir")
    p.add_argument("--out", default=kh.DEFAULT_OUT)
    p.add_argument("--db", default=uv.DEFAULT_DB)
    p.add_argument("--since", type=_date, default=uv.DEFAULT_START)
    p.add_argument("--series", choices=sorted(kh.SERIES), default="crowd")
    p.add_argument("--repo")
    p.add_argument("--crosswalk-csv")

    p = sub.add_parser("load-csv", help="load a generic dated-values CSV as SOURCE")
    p.add_argument("--file", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--db", default=uv.DEFAULT_DB)
    p.add_argument("--repo")
    p.add_argument("--crosswalk-csv")

    p = sub.add_parser("coverage", help="coverage report")
    p.add_argument("--db", default=uv.DEFAULT_DB)
    p.add_argument("--lookups", help="CSV asset_key,date (e.g. the crawler's traded assets)")
    p.add_argument("--max-age", type=int, default=14)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("value-on", help="one lookup")
    p.add_argument("--db", default=uv.DEFAULT_DB)
    p.add_argument("--date", required=True)
    p.add_argument("--asset", required=True, help="Sleeper player id or pick key")
    p.add_argument("--format", required=True)
    p.add_argument("--source", default="dp")

    args = ap.parse_args(argv)

    if args.cmd == "clone-dp":
        cmd = ["git", "clone", "--filter=blob:none", "--no-checkout", uv.DP_REPO_URL, args.dest]
        print(" ".join(cmd))
        if not args.dry_run:
            subprocess.run(cmd, check=True)
    elif args.cmd == "inspect-dp":
        for e in uv.inspect_dp(args.repo, start=args.start):
            print("%-26s %4d boards  %s .. %s  (%s .. %s)\n    %s" % (
                e["file"], e["boards"], e["first"], e["last"],
                e["first_commit"][:10], e["last_commit"][:10], e["header"]))
    elif args.cmd == "build-dp":
        xtext = None
        if args.crosswalk_csv:
            with open(args.crosswalk_csv, encoding="utf-8") as f:
                xtext = f.read()
        print(json.dumps(uv.build_dp(args.repo, args.db, start=args.start, end=args.end,
                                     crosswalk_text=xtext), indent=1))
    elif args.cmd == "pull-ktc":
        extra = kh.read_extra(args.extra) if args.extra else None
        fetcher = kh.PoliteFetcher(interval=args.interval)
        try:
            s = kh.run_pull(args.out, fetcher=fetcher, extra=extra,
                            refresh_list=args.refresh_list, keep_html=args.keep_html,
                            limit=args.limit)
        except kh.HardStop as e:
            print("HARD STOP: %s. Checkpoint kept; re-run later to resume." % e)
            return 2
        print(json.dumps(s, indent=1))
    elif args.cmd == "ingest-ktc":
        s = kh.ingest(args.out, args.db, xw=_crosswalk(args), since=args.since, series=args.series)
        print(json.dumps(s, indent=1))
    elif args.cmd == "load-csv":
        xw = _crosswalk(args) if (args.repo or args.crosswalk_csv) else None
        print(json.dumps(uv.load_dated_csv(args.file, args.db, source=args.source, xw=xw)))
    elif args.cmd == "coverage":
        lookups = uv.read_lookups(args.lookups) if args.lookups else None
        rep = uv.coverage_report(args.db, lookups=lookups, max_age=args.max_age)
        print(json.dumps(rep, indent=1) if args.json else uv.format_report(rep))
    elif args.cmd == "value-on":
        print(uv.value_on(args.date, args.asset, args.format, source=args.source, db_path=args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
