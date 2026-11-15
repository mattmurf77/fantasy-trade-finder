"""Fairness-formula replay: rebuild decks for real trades under each admission formula.

Operator tooling, offline (docs/plans/fairness-formula/spec.md, "Technical design"). Same
case file, engine set-up and match rule as `fairness_window_replay` (shared, not copied).
For every case this builds the r4 owner bilateral deck once per arm, in the same process,
in the order T, A, B, C, D, each inside `fairness_formula.override(...)`, and records the
close / exact match ranks, deck size, build time, and how many of the first 30 cards are
under 0.75 on TODAY's package math (the unchanged market side values).

`summarise` makes the arm table (lineage-bootstrapped intervals on the paired gain over T,
overall and on trades that do / do not move a pick) and applies the rule fixed in the spec
before any result was seen (`select`).

    python -m backend.eval.fairness_formula_replay run --cases CASES.jsonl --out part.json \\
        [--shard 0 --of 2]
    python -m backend.eval.fairness_formula_replay summarise --out table.json part*.json

No network (sockets are blocked by `load_engine`), no production data, and `backend.server`
is never imported. Known limits are the fairness-window replay's (see its results.md).
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time

from backend.eval import fairness_window_replay as fw

# (package_math, exponent, raw, threshold_power); None = today's math. Fixed in the spec.
ARMS = {
    "T": None,
    "A": (0.0, 0.7, 0.0, 1.0),
    "B": (0.0, 0.7, 0.0, 0.7),
    "C": (0.0, 1.0, 0.0, 1.0),
    "D": (0.0, 0.7, 1.0, 1.0),
}
BASELINE = "T"
THRESHOLD = 0.75
TIE_ORDER = ("T", "C", "B", "A", "D")      # equal estimates go to the arm closest to today
FIRST_PAGE = fw.FIRST_PAGE
UNDER = 0.75
MAX_SLOWDOWN = 1.10
DRAWS = 2000
SEED = 20261115
_EPS = 1e-9

load_engine = fw.load_engine


def arm_knobs(arm):
    from backend import fairness_formula as fx
    spec = ARMS[arm]
    return None if spec is None else dict(zip(fx.KNOBS, spec))


def involves_pick(case):
    return any(str(a["token"]).startswith("P:") for a in case["real_give"] + case["real_receive"])


def _today_ratio(card):
    g, r = card.give_value, card.receive_value
    return min(g, r) / max(g, r) if g > 0 and r > 0 else 0.0


def replay_case(case, eng, arms=tuple(ARMS)):
    """One case under every arm -> {arm: measures}."""
    from backend import fairness_formula as fx
    _ts, r4, _P, _s = eng
    kwargs, meta = fw._inputs(case, eng)
    out = {}
    for arm in arms:
        with fx.override(arm_knobs(arm)):
            t0 = time.perf_counter()
            cards, _report = r4.generate_bilateral_trades(fairness_threshold=THRESHOLD, **kwargs)
            secs = time.perf_counter() - t0
        flags = [fw.match_card(case, meta, c) for c in cards]
        head = cards[:FIRST_PAGE]
        out[arm] = {
            "n_cards": len(cards), "secs": round(secs, 4),
            "close_rank": fw._first(f[0] for f in flags), "exact_rank": fw._first(f[1] for f in flags),
            "first30_n": len(head),
            "first30_under_today": sum(1 for c in head if _today_ratio(c) < UNDER - _EPS),
            "deck": [(c.target_user_id, tuple(sorted(c.give_player_ids)), tuple(sorted(c.receive_player_ids)))
                     for c in head]}
    return out


def run(cases_path, out_path, shard=0, of=1, arms=tuple(ARMS), eng=None, log=None):
    eng = eng or load_engine()
    rows = []
    with open(cases_path) as f:
        cases = [json.loads(line) for line in f if line.strip()]
    for k, case in enumerate(cases[shard::of]):
        try:
            row = {"lineage": case["lineage"], "pick": involves_pick(case), "by_arm": replay_case(case, eng, arms)}
        except Exception as e:                     # counted, never silently dropped
            row = {"lineage": case["lineage"], "skip": "error:" + type(e).__name__}
        rows.append(row)
        if log and k % 10 == 0:
            print(k, len(cases[shard::of]), row.get("skip"), file=log, flush=True)
            fw._dump(out_path, rows, False)
    fw._dump(out_path, rows, True)
    return rows


# ── summary ─────────────────────────────────────────────────────────────────

def _hit(r, arm, col, k):
    rank = r["by_arm"][arm][col]
    return 1.0 if rank is not None and rank <= k else 0.0


def summarise(rows, arms=tuple(ARMS), draws=DRAWS, seed=SEED):
    ok = [r for r in rows if "skip" not in r]
    lin = [r["lineage"] for r in ok]
    subsets = {"pick": [r for r in ok if r["pick"]], "no_pick": [r for r in ok if not r["pick"]]}

    def boot(rs, fn):
        return fw._boot([r["lineage"] for r in rs], [fn(r) for r in rs], draws, seed)

    def gain(arm):
        return lambda r: _hit(r, arm, "close_rank", FIRST_PAGE) - _hit(r, BASELINE, "close_rank", FIRST_PAGE)
    table = []
    for arm in arms:
        row = {"arm": arm, "knobs": ARMS[arm],
               "close_first30": boot(ok, lambda r: _hit(r, arm, "close_rank", FIRST_PAGE)),
               "close_anywhere": boot(ok, lambda r: _hit(r, arm, "close_rank", 10 ** 9)),
               "exact_first30": boot(ok, lambda r: _hit(r, arm, "exact_rank", FIRST_PAGE)),
               "first30_share_under_075_today": boot(
                   ok, lambda r: (r["by_arm"][arm]["first30_under_today"], r["by_arm"][arm]["first30_n"])),
               "median_deck_size": statistics.median(r["by_arm"][arm]["n_cards"] for r in ok),
               "median_deck_seconds": round(statistics.median(r["by_arm"][arm]["secs"] for r in ok), 3),
               "median_time_ratio_vs_T": round(statistics.median(
                   r["by_arm"][arm]["secs"] / max(r["by_arm"][BASELINE]["secs"], 1e-9) for r in ok), 4),
               "first30_identical_to_T": sum(r["by_arm"][arm]["deck"] == r["by_arm"][BASELINE]["deck"]
                                             for r in ok)}
        for name, rs in subsets.items():
            row[name] = {"n_trades": len(rs), "n_lineages": len({r["lineage"] for r in rs}),
                         "close_first30": boot(rs, lambda r: _hit(r, arm, "close_rank", FIRST_PAGE)) if rs else None}
            if arm != BASELINE and rs:
                row[name]["gain_vs_T"] = boot(rs, gain(arm))
        if arm != BASELINE:
            row["gain_close_first30_vs_T"] = boot(ok, gain(arm))
        table.append(row)
    return {"n_trades": len(ok), "n_lineages": len(set(lin)),
            "skipped": dict(collections.Counter(r["skip"] for r in rows if "skip" in r)),
            "table": table, "selection": select(table)}


def select(table):
    """The pre-registered rule. An arm passes when (1) its paired gain over T has a 95%
    interval above zero, (2) its median build-time ratio is <= 1.10, and (3) its gain on
    trades involving a pick does not have an interval entirely below zero. The passing arm
    with the highest primary estimate wins; equal estimates go to the arm closest to today
    (T, C, B, A, D). None passing -> today's math is kept."""
    passing = []
    for r in table:
        if r["arm"] == BASELINE:
            continue
        pick = (r.get("pick") or {}).get("gain_vs_T")
        if (r["gain_close_first30_vs_T"]["ci95"][0] > 0
                and r["median_time_ratio_vs_T"] <= MAX_SLOWDOWN
                and (pick is None or pick["ci95"][1] >= 0)):
            passing.append(r)
    if not passing:
        return {"adopted": BASELINE, "passed": [],
                "reason": "no arm passed; the knobs stay at today's math"}
    best = max(passing, key=lambda r: (r["close_first30"]["estimate"], -TIE_ORDER.index(r["arm"])))
    return {"adopted": best["arm"], "passed": [r["arm"] for r in passing],
            "reason": "highest close-match-in-first-30 among passing arms"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--cases", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--of", type=int, default=1)
    s = sub.add_parser("summarise")
    s.add_argument("--out", required=True)
    s.add_argument("parts", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.cases, a.out, a.shard, a.of, log=sys.stderr)
    else:
        rows = []
        for p in a.parts:
            with open(p) as f:
                rows += json.load(f)["rows"]
        res = summarise(rows)
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
        print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
