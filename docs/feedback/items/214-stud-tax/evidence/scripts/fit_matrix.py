"""#214 stud-tax retune — constant fit loop over the T1-T6 matrix.

Replays the 6-trade x 2-format matrix through POST /api/trade/evaluate
(in-process Flask test client, worktree copy of the dev DB) for each
candidate constant set, and scores final skew against the competitor
medians pooled from research/competitor-values.md (2026-08-02, 5 sources)
+ research/side-by-side-live.md (2026-08-04 live KTC + Dynasty Nerds).

Gate (tuning-proposal.md §Validation): FTF final skew within +-15pp of the
competitor median on >=4 of 6 trades (per-trade delta = mean of available
format-cell deltas, results.md convention), AND T1 SF final skew > 0
(package-favored).

Run from the worktree root:  python3 feedback-workspace/214/fit_matrix.py
"""
import itertools
import json
import statistics
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.server as srv
import backend.trade_service as ts

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

# Pooled per-cell competitor skew observations (%, package-positive), both
# capture sessions. KTC appears in both sessions (crowd values drifted);
# both readings kept as observations. DN's single-basis numbers are filed
# under 1QB per side-by-side-live.md's basis note; its T5 number is
# excluded (basis mismatch flagged 'directional only' in that doc).
COMP = {
    ("T1", "sf_tep"):  [73.7, 63.6, 25.6, 62.0, 51.1, 26.7, 73.4],
    ("T1", "1qb_ppr"): [61.2, 28.9, 60.6, 60.8, 16.6],
    ("T2", "sf_tep"):  [-26.4, -32.0, -24.1, -34.7],
    ("T2", "1qb_ppr"): [-21.8, -20.8, -22.2, -9.4],
    ("T3", "sf_tep"):  [68.4, 60.8, 42.5, 29.9, 67.9],
    ("T3", "1qb_ppr"): [73.1, 65.1, 73.1, 70.4],
    ("T4", "sf_tep"):  [34.5, 25.4, 68.8],
    ("T4", "1qb_ppr"): [31.4, 77.2, 28.6],
    ("T5", "sf_tep"):  [68.0, 42.5, 67.7],
    ("T5", "1qb_ppr"): None,   # no competitor sources (SF-only probe)
    ("T6", "sf_tep"):  [1.1, -10.3, -8.4, 6.0],
    ("T6", "1qb_ppr"): [8.3, 21.5, 3.1],
}
MEDIAN = {k: (statistics.median(v) if v else None) for k, v in COMP.items()}


def resolve(name):
    return PID.get(name, name)


def run_matrix():
    out = {}
    with srv.app.test_client() as c:
        for tid, give_name, recv_names in MATRIX:
            for fmt in FORMATS:
                r = c.post("/api/trade/evaluate", json={
                    "give_player_ids": [resolve(give_name)],
                    "receive_player_ids": [resolve(n) for n in recv_names],
                    "scoring_format": fmt,
                })
                assert r.status_code == 200, (tid, fmt, r.status_code)
                d = r.get_json()
                gv, rv = d["give_value"], d["receive_value"]
                out[(tid, fmt)] = {
                    "skew": 100.0 * (rv - gv) / gv,
                    "verdict": d["verdict"], "favors": d["favors"],
                    "adjustments": d.get("adjustments"),
                    "naive": d.get("naive_totals"),
                    "gv": gv, "rv": rv,
                }
    return out


def score(res, verbose=True):
    per_trade = {}
    for tid, _, _ in MATRIX:
        deltas = []
        for fmt in FORMATS:
            med = MEDIAN[(tid, fmt)]
            if med is None:
                continue
            d = med - res[(tid, fmt)]["skew"]
            deltas.append(d)
            if verbose:
                print(f"  {tid} {fmt:8s} skew={res[(tid,fmt)]['skew']:+7.1f}  "
                      f"median={med:+7.1f}  delta={d:+6.1f}  "
                      f"verdict={res[(tid,fmt)]['verdict']}")
        per_trade[tid] = sum(deltas) / len(deltas)
    n_pass = sum(1 for v in per_trade.values() if abs(v) <= 15.0)
    t1_sf_pkg = res[("T1", "sf_tep")]["skew"] > 0
    if verbose:
        print("  per-trade mean deltas:",
              {k: round(v, 1) for k, v in per_trade.items()})
        print(f"  trades within +-15pp: {n_pass}/6 ; T1 SF package-favored: {t1_sf_pkg}")
    return n_pass, t1_sf_pkg, per_trade


def set_cfg(**kw):
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(kw)


if __name__ == "__main__":
    sweep = os.environ.get("SWEEP")
    if sweep:
        best = []
        for floor, gamma, rate, po, cap in itertools.product(
                [0.15, 0.30, 0.50, 0.60],
                [1.5, 1.0, 0.75],
                [0.08, 0.05, 0.03],
                [0.5, 0.4],
                [0.35, 0.25]):
            set_cfg(package_floor_market=floor, package_adj_gamma_market=gamma,
                    crown_rate_market=rate, skew_phaseout=po,
                    package_discount_cap=cap)
            res = run_matrix()
            n, t1, per = score(res, verbose=False)
            mad = sum(abs(v) for v in per.values()) / 6
            best.append((n, t1, -mad, floor, gamma, rate, po, cap,
                         {k: round(v, 1) for k, v in per.items()}))
        best.sort(reverse=True)
        for row in best[:12]:
            n, t1, negmad, floor, gamma, rate, po, cap, per = row
            print(f"pass={n}/6 t1sf_pkg={t1} meanabs={-negmad:5.1f} "
                  f"floor={floor} gamma={gamma} rate={rate} po={po} cap={cap} {per}")
    else:
        set_cfg()   # defaults as committed in _DEFAULT_CFG
        res = run_matrix()
        score(res)
        for (tid, fmt), d in res.items():
            adj = d["adjustments"]
            rows = []
            if adj:
                for side in ("give", "receive"):
                    for r_ in adj[side]:
                        rows.append(f"{side}:{r_['key']}={r_['amount']:+.0f}")
            print(f"{tid} {fmt:8s} gv={d['gv']:8.1f} rv={d['rv']:8.1f} "
                  f"skew={d['skew']:+6.1f} {' '.join(rows)}")
