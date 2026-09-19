"""
One-shot script: dump all Sleeper ↔ DynastyProcess name mismatches to a JSON file.
Run from the project root:  python3 dump_mismatches.py
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from backend.data_loader import load_consensus_values, normalise_name, _fetch_dynasty_process

# 1. Load DP data (fetches from GitHub)
print("Fetching DynastyProcess values...")
elo_map, dp_vals = _fetch_dynasty_process(scoring="1qb", timeout=15)
dp_names = set(dp_vals.keys())
print(f"  DP players with value > 0: {len(dp_names)}")

# Also build a reverse map: normalised -> (raw_name, position, value)
# We need the raw names for display
import csv, io, urllib.request
VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
req = urllib.request.Request(VALUES_URL, headers={"User-Agent": "FantasyTradeFinder/1.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    raw_csv = resp.read().decode("utf-8")

dp_detail = {}  # normalised -> {raw_name, pos, value}
reader = csv.DictReader(io.StringIO(raw_csv))
for row in reader:
    pos = (row.get("pos") or "").strip().upper()
    if pos not in {"QB", "RB", "WR", "TE"}:
        continue
    name_raw = (row.get("player") or "").strip()
    value = float((row.get("value_1qb") or "0").strip() or "0")
    normed = normalise_name(name_raw)
    if value > 0:
        dp_detail[normed] = {"raw_name": name_raw, "pos": pos, "value": value}

# 2. Load Sleeper cache
cache_path = os.path.join(os.path.dirname(__file__), "data", ".sleeper_players_cache.json")
print(f"Loading Sleeper cache from {cache_path}...")
with open(cache_path) as f:
    sleeper = json.load(f)

VALID_POS = {"QB", "RB", "WR", "TE"}

# 3. Categorise
exact_matches = []
mismatches = []

for pid, p in sleeper.items():
    pos = (p.get("position") or "").upper()
    if pos not in VALID_POS:
        continue
    name = p.get("full_name") or ""
    if not name:
        continue
    normed = normalise_name(name)
    if normed in dp_vals:
        exact_matches.append({"sleeper_id": pid, "sleeper_name": name, "normed": normed, "pos": pos})
    else:
        mismatches.append({"sleeper_id": pid, "sleeper_name": name, "normed": normed, "pos": pos})

print(f"  Exact matches: {len(exact_matches)}")
print(f"  Mismatches (no exact DP hit): {len(mismatches)}")

# 4. For each mismatch, find candidate DP names (fuzzy)
# We'll include ALL DP names so subagents can do their own matching
output = {
    "dp_players": {k: v for k, v in dp_detail.items()},  # all DP entries with value > 0
    "sleeper_mismatches": mismatches,
    "exact_match_count": len(exact_matches),
}

out_path = os.path.join(os.path.dirname(__file__), "data", "name_mismatches.json")
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✅ Wrote {out_path}")
print(f"   {len(mismatches)} Sleeper mismatches + {len(dp_detail)} DP entries for fuzzy matching")
