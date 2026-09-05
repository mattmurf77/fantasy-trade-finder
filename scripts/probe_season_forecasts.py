"""Read-only weekly projection horizon probe; no database writes or credentials.

Example: python3 -m scripts.probe_season_forecasts --season 2026 --weeks 1-17
An optional output file records the actually captured snapshot for prospective
validation. It is not historical as-of data and cannot be backdated.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request

from backend.season_forecasts import fetch_projection_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--weeks", default="1-17")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    weeks = []
    for part in args.weeks.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            weeks.extend(range(start, end + 1))
        else:
            weeks.append(int(part))
    payloads = {}

    def fetch(url):
        with urllib.request.urlopen(url, timeout=20) as response:
            payloads[url] = json.load(response)
        return payloads[url]

    # Capture completion time rather than the start of a potentially long probe.
    result = fetch_projection_snapshot(args.season, weeks, fetch, datetime.now(timezone.utc))
    result = fetch_projection_snapshot(args.season, weeks, payloads.__getitem__, datetime.now(timezone.utc))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"provider": result["provider"], "captured_at": result["captured_at"],
                      "supported": result["supported"], "reasons": result["reasons"],
                      "historical_as_of": False,
                      "weeks": {str(w): {"raw_rows": len(next((p for u, p in payloads.items() if f"/{w}?" in u), [])),
                                           "normalized_stat_rows": sum(r["week"] == w for r in result["forecasts"]),
                                           "unknown_availability": sum(r["week"] == w and r["availability"] is None for r in result["forecasts"])} for w in weeks}}, indent=2))


if __name__ == "__main__":
    main()
