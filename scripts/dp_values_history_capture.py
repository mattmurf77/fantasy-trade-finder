"""One-time NETWORK capture of dated DynastyProcess value boards.

Mints the committed fixtures that `backend/dp_values_history.py` serves
offline. Run once; re-run only to add seasons/weeks or refresh a snapshot.

For each (season, week) in the grid below it resolves the nearest
`files/values-players.csv` commit at-or-before that calendar date via the
GitHub commits API, fetches that sha's copy of the file, slims it to the five
columns anything here actually reads, and writes it plus an index entry under
`backend/tests/fixtures/dp-values-history/`.

    python3 scripts/dp_values_history_capture.py            # full grid
    python3 scripts/dp_values_history_capture.py --seasons 2024 2025
    python3 scripts/dp_values_history_capture.py --dry-run  # resolve only

Only reads two public, unauthenticated GitHub endpoints (`api.github.com`
commits list + `raw.githubusercontent.com`). Writes nothing but fixtures.
Source is CC-BY DynastyProcess — see `docs/integrations/dynastyprocess.md`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import dp_values_history as dvh  # noqa: E402

# Weeks the #169 backtests ask boards for: 0 = kickoff (preseason, the board a
# preseason prediction is allowed to know), 3/6/9/12 = the calibration report's
# as-of weeks, 14 = end of the regular season (all six fixtures are 14-week).
WEEKS = (0, 3, 6, 9, 12, 14)
SEASONS = (2022, 2023, 2024, 2025)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="*", default=list(SEASONS))
    ap.add_argument("--weeks", type=int, nargs="*", default=list(WEEKS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(dvh.SNAPSHOT_DIR, exist_ok=True)
    try:
        index = dvh.load_index()
    except FileNotFoundError:
        index = {"snapshots": {}}
    index.setdefault("snapshots", {})
    index["_provenance"] = {
        "source": "https://github.com/dynastyprocess/data — files/values-players.csv, git history",
        "license": "CC-BY (DynastyProcess); see docs/integrations/dynastyprocess.md",
        "captured": time.strftime("%Y-%m-%d"),
        "note": ("Slimmed to %s; rows with no 1QB and no SF value dropped. Each "
                 "snapshot is the nearest commit AT OR BEFORE its key date, so a "
                 "board never contains information from after the date it is used "
                 "to price." % (", ".join(dvh.SLIM_COLUMNS))),
        "purpose": ("dated dynasty value boards for the #169 outlook backtests "
                    "(preseason roster_value source + pick-capital hypothesis 1b)"),
    }

    for season in args.seasons:
        for week in args.weeks:
            target = dvh.week_boundary(season, week)
            key = target.isoformat()
            ref = dvh.resolve_commit(target)
            print("%s (season %d wk %d) -> %s @ %s"
                  % (key, season, week, ref.sha[:12], ref.committed_at))
            if args.dry_run:
                continue
            raw = dvh.fetch_values_csv(ref.sha)
            slim = dvh.slim_csv(raw)
            fname = "values-%s.csv" % key
            with open(os.path.join(dvh.SNAPSHOT_DIR, fname), "w") as f:
                f.write(slim)
            n_rows = slim.count("\n") - 1
            scrape = slim.split("\n")[1].split(",")[-1].strip('"') if n_rows else ""
            index["snapshots"][key] = {
                "season": season, "week": week, "file": fname,
                "sha": ref.sha, "committed_at": ref.committed_at,
                "scrape_date": scrape, "rows": n_rows,
                "raw_bytes": len(raw), "slim_bytes": len(slim),
            }
            time.sleep(0.4)   # be a polite client

    if not args.dry_run:
        with open(dvh.INDEX_PATH, "w") as f:
            json.dump(index, f, indent=2, sort_keys=True)
            f.write("\n")
        print("\nwrote %d snapshots -> %s" % (len(index["snapshots"]), dvh.SNAPSHOT_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
