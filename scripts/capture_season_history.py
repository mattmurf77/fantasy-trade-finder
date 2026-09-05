"""Capture bounded Sleeper historical outcomes; see Win Now historical validation scope.

Public GET only, no DB imports, user profiles, or final rosters. Output creation
is exclusive: select a fresh output path for every research capture.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.season_history import collect_history


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--league-id', action='append', required=True)
    parser.add_argument('--seasons', type=int, nargs='+', default=[2022, 2023, 2024, 2025])
    parser.add_argument('--max-chain', type=int, default=8)
    parser.add_argument('--max-seasons', type=int, default=16)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output already exists; use a new immutable capture path')
    last_request = 0.0
    def fetch(path):
        nonlocal last_request
        # Five requests/second, far below Sleeper's 1,000/minute guidance.
        time.sleep(max(0.0, 0.2 - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        request = urllib.request.Request('https://api.sleeper.app/v1/' + path,
                                         headers={'User-Agent': 'FTF-Historical-Outcomes/1'}, method='GET')
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    capture = collect_history(args.league_id, args.seasons, fetch,
                              max_chain=args.max_chain, max_seasons=args.max_seasons)
    capture['started_at'] = capture['captured_at']
    capture['captured_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    rendered = json.dumps(capture, indent=2, sort_keys=True, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(rendered)
    valid = sum(r['outcomes']['status'] == 'valid' for r in capture['seasons'])
    print(f'Wrote {args.output}: {valid} valid seasons; {len(capture["exclusions"])} exclusions')
    return 0 if valid else 2


if __name__ == '__main__':
    raise SystemExit(main())
