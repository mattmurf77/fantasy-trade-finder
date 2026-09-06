"""#214 stud-tax validation — run the 6-trade matrix through FTF's own
POST /api/trade/evaluate (Mode A, consensus, no league context), in-process
via the Flask test client against the real local DB (data/trade_finder.db).

Read-only: this script only POSTs to /api/trade/evaluate (no DB writes) and
never touches production. Run from the repo root:

    python feedback-workspace/214/run_matrix.py

Player ids resolved by hand from `players` table (see results.md for the
lookup). No substitutions were needed — every matrix player exists in the
local DB.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.server as srv

# player_id lookups (data/trade_finder.db, `players` table)
PID = {
    "Justin Jefferson":   "6794",
    "CeeDee Lamb":        "6786",
    "Bo Nix":             "11563",
    "Ja'Marr Chase":      "7564",
    "Nico Collins":       "7569",
    "Brian Thomas Jr.":   "11631",
    "Bijan Robinson":     "9509",
    "Jahmyr Gibbs":       "9221",
    "De'Von Achane":      "9226",
    "Josh Allen":         "4984",
    "Jayden Daniels":     "11566",
    "Drake Maye":         "11564",
    "Malik Nabers":       "11632",
    "Tetairoa McMillan":  "12526",
    "DK Metcalf":         "5846",
}

# T4's "2027 1st (mid)" pick has no year-dated equivalent in FTF's Mode A
# calculator (only generic, year-agnostic pool picks are addressable outside
# a real league_id) — substituted with generic_pick_1_mid per the plan's
# nearest-value substitution rule. Documented as a limitation in results.md.
PICK_MID_1ST = "generic_pick_1_mid"

MATRIX = [
    ("T1", "Justin Jefferson", ["CeeDee Lamb", "Bo Nix"]),
    ("T2", "Ja'Marr Chase", ["Nico Collins", "Brian Thomas Jr."]),
    ("T3", "Bijan Robinson", ["Jahmyr Gibbs", "De'Von Achane"]),
    ("T4", "Justin Jefferson", ["CeeDee Lamb", PICK_MID_1ST]),
    ("T5", "Josh Allen", ["Jayden Daniels", "Drake Maye"]),
    ("T6", "Malik Nabers", ["Tetairoa McMillan", "DK Metcalf"]),
]

FORMATS = ["1qb_ppr", "sf_tep"]


def resolve(name):
    return PID.get(name, name)  # pick ids pass through unchanged


def run_one(give_name, recv_names, fmt):
    give_ids = [resolve(give_name)]
    recv_ids = [resolve(n) for n in recv_names]
    with srv.app.test_client() as c:
        r = c.post("/api/trade/evaluate", json={
            "give_player_ids": give_ids,
            "receive_player_ids": recv_ids,
            "scoring_format": fmt,
        })
        assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
        return r.get_json()


def main():
    results = {}
    for tid, give_name, recv_names in MATRIX:
        results[tid] = {}
        for fmt in FORMATS:
            d = run_one(give_name, recv_names, fmt)
            results[tid][fmt] = d
            dropped = d.get("dropped_player_ids") or []
            if dropped:
                print(f"WARNING {tid} {fmt}: dropped ids {dropped}", file=sys.stderr)

    with open("feedback-workspace/214/ftf_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Quick console summary
    for tid, give_name, recv_names in MATRIX:
        for fmt in FORMATS:
            d = results[tid][fmt]
            gv, rv = d["give_value"], d["receive_value"]
            skew = (rv - gv) / gv if gv else None
            naive = d.get("naive_totals")
            if naive:
                ngv, nrv = naive["give"], naive["receive"]
                naive_skew = (nrv - ngv) / ngv if ngv else None
            else:
                naive_skew = skew  # no adjustments applied -> naive == final
            print(f"{tid} {fmt:8s} give={gv:>8} recv={rv:>8} "
                  f"final_skew={skew:+.3f} naive_skew={naive_skew:+.3f} "
                  f"verdict={d['verdict']} favors={d['favors']}")


if __name__ == "__main__":
    main()
