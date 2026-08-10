"""One-time network capture for the #169 pick-capital hypothesis test (1a/1b).

Fetches, for each of the 6 backtested league-seasons already captured in
`backend/tests/fixtures/outlook-calibration/`, the data NOT already present
there that `outlook_pick_capital_hypothesis.py` needs:

  * `traded_picks` (the league's own current snapshot) — used only as an
    independent cross-check on the transaction-replay reconstruction below,
    never as the primary source (see the script's module docstring for why).
  * `transactions/{week}` for weeks 1-18, filtered down to
    `type == "trade" and status == "complete"` rows only (the full per-week
    payload is mostly waiver/free-agent noise this analysis does not need;
    filtering here keeps the committed fixture small and reviewable).

Writes one fixture per league-season to
`backend/tests/fixtures/outlook-hypotheses/<name>.json`. Touches the network
(public, unauthenticated Sleeper REST v1 — same endpoints already documented
in docs/integrations/sleeper.md). Run once; the hypothesis script itself is
fully offline against the committed output.

    python3 scripts/outlook_pick_capital_capture.py
"""

from __future__ import annotations

import json
import os
import urllib.request

LEAGUES = {
    "lakeview-2025": "1180999595377590272",
    "lakeview-2024": "1101407304802574336",
    "ffv3-2025": "1181674778942836736",
    "ffv3-2024": "1048263304533188608",
    "ffv3-2023": "916436765509046272",
    "ffv3-2022": "867593839303598080",
}

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "tests", "fixtures", "outlook-hypotheses",
)


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def capture_one(name: str, league_id: str) -> dict:
    print(f"  fetching {name} ({league_id}) ...")
    traded_picks = _get(f"https://api.sleeper.app/v1/league/{league_id}/traded_picks")

    transactions_trades: dict[str, list] = {}
    for week in range(1, 19):
        rows = _get(f"https://api.sleeper.app/v1/league/{league_id}/transactions/{week}")
        trades = [
            r for r in rows
            if isinstance(r, dict) and r.get("type") == "trade" and r.get("status") == "complete"
        ]
        if trades:
            transactions_trades[str(week)] = trades

    return {
        "label": name,
        "league_id": league_id,
        "_note": (
            "Captured 2026-08-09 for the #169 pick-capital hypothesis test "
            "(1a/1b). `transactions_trades` is pre-filtered to "
            "type=='trade', status=='complete' rows from the raw "
            "/transactions/{week} response (weeks 1-18 swept, empty weeks "
            "omitted) -- the unfiltered payload is mostly waiver/free-agent "
            "noise this analysis does not use. `traded_picks` is the raw, "
            "unfiltered /traded_picks response for the league's own "
            "(current) instance -- a cross-check only, see the hypothesis "
            "script's module docstring for why it is not the primary "
            "pick-ownership source."
        ),
        "traded_picks": traded_picks,
        "transactions_trades": transactions_trades,
    }


def main() -> None:
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    for name, league_id in LEAGUES.items():
        data = capture_one(name, league_id)
        out_path = os.path.join(FIXTURES_DIR, f"{name}.json")
        with open(out_path, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        n_trades = sum(len(v) for v in data["transactions_trades"].values())
        print(f"    -> {out_path} ({n_trades} trade transactions, "
              f"{len(data['traded_picks'])} traded_picks rows)")


if __name__ == "__main__":
    main()
