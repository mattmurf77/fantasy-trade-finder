"""Fairness-window replay: rebuild decks for real trades at each candidate default threshold.

Operator tooling, offline (docs/plans/fairness-window/spec.md, "Technical design"). For
every case in a JSONL file (one real trade: each team's assets with values and outlooks,
the viewer, the partner and what really moved), this builds the owner bilateral deck
(`trade_gen_bilateral_r4.generate_bilateral_trades`) once per candidate threshold, in the
same process, and records:

- the 1-based rank of the first card that is a CLOSE match to the real trade (same
  partner; matched value / union value >= 0.5) and of the first EXACT match;
- how many of the first 30 cards have a market ratio under 0.75;
- the deck build time.

`summarise` turns those rows into the candidate table (lineage-bootstrapped intervals on
the paired gain over 0.75) and applies the decision rule fixed in the spec before any
result was seen (`select`).

Case format (one JSON object per line; ids are opaque strings and are never printed):

    {"lineage": "...", "format": "1qb" | "sf", "viewer": "t0", "partner": "t1",
     "teams": {"t0": {"outlook": "contender" | null,
                      "assets": [{"id": "...", "pos": "QB|RB|WR|TE|PICK",
                                  "age": 24 | null, "value": 3120.0, "token": "..."}]}},
     "real_give": [{"token": "...", "value": 3120.0}],      # viewer -> partner
     "real_receive": [{"token": "...", "value": 2800.0}]}   # partner -> viewer

`token` identifies an asset for matching (a player id, or "P:<year>:<round>" for a pick,
so two picks of the same year and round match). The research extractor that writes this
file from the local dataset is not part of the repo; this module takes the file only as
a path argument.

    python -m backend.eval.fairness_window_replay run --cases CASES.jsonl --out part.json \
        [--shard 0 --of 4]
    python -m backend.eval.fairness_window_replay summarise --out table.json part*.json

No network (sockets are blocked by `run`), no production data, and `backend.server` is
never imported. `run` points the engine's database at an empty scratch SQLite file, so
model_config is the shipped defaults. Known limits: the generator's own order is the
deck (no ranker, presentment, deck-quality filters or first-page store), organic shapes
only (1-for-1, 1-for-2, 2-for-1), consensus boards only.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import statistics
import sys
import tempfile
import time

CANDIDATES = (0.75, 0.70, 0.65, 0.60, 0.55)
BASELINE = 0.75
FIRST_PAGE = 30
CLOSE_SHARE = 0.5
UNDER = 0.75
MAX_SLOWDOWN = 1.10
DRAWS = 2000
SEED = 20261114
_EPS = 1e-9


def load_engine(scratch_dir: str | None = None, *, under_pytest: bool = False):
    """Import the generator offline. Blocks sockets; points a fresh import of the
    database module at an empty scratch file (refuses if it is already imported
    against something else, which only happens inside pytest, where the test
    harness has already imported the server: `under_pytest` skips that check)."""
    import socket

    def _blocked(*_a, **_k):
        raise RuntimeError("network is blocked in the fairness-window replay")
    socket.socket.connect = _blocked
    socket.create_connection = _blocked
    if "backend.database" not in sys.modules:
        path = os.path.join(scratch_dir or tempfile.mkdtemp(prefix="fw-replay-"), "scratch.db")
        os.environ["DATABASE_URL"] = "sqlite:///" + path
    from backend import trade_service as ts
    from backend import trade_gen_bilateral_r4 as r4
    from backend.ranking_service import Player
    from backend.data_loader import seed_elo_for_value
    if not under_pytest:
        assert "backend.server" not in sys.modules, "the replay must not import backend.server"
    return ts, r4, Player, seed_elo_for_value


def _inputs(case, eng):
    ts, _r4, Player, seed_elo_for_value = eng
    players, seed, rosters, meta = {}, {}, {}, {}
    for uid, team in case["teams"].items():
        ids = []
        for a in team["assets"]:
            pid = a["id"]
            age = a.get("age")
            players[pid] = Player(pid, pid, a["pos"], "PICK" if a["pos"] == "PICK" else "NFL",
                                  int(round(age)) if age is not None else None)
            seed[pid] = seed_elo_for_value(a["value"])
            meta[pid] = (uid, a["token"], float(a["value"]))
            ids.append(pid)
        rosters[uid] = ids
    viewer = case["viewer"]
    members = [ts.LeagueMember(uid, uid, rosters[uid], {}, False) for uid in rosters if uid != viewer]
    outlooks = {uid: t.get("outlook") for uid, t in case["teams"].items()}
    kwargs = dict(players=players, league=ts.League("L", "replay", "sleeper", members),
                  user_id=viewer, user_roster=rosters[viewer], user_elo={}, seed_elo=seed,
                  scoring_format="%s_ppr" % case["format"], outlook=outlooks.get(viewer),
                  opponent_outlooks={k: v for k, v in outlooks.items() if k != viewer and v is not None},
                  config={"owner_bilateral_revision_4_enabled": 1.0})
    return kwargs, meta


def _overlap(real, card):
    """Value of `real` assets also present in `card` (by token, multiset), and the
    same measured from the card's side. Both lists are [(token, value)]."""
    def matched(src, other):
        left = collections.Counter(t for t, _ in other)
        total = 0.0
        for t, v in sorted(src, key=lambda x: -x[1]):
            if left[t] > 0:
                left[t] -= 1
                total += v
        return total
    return matched(real, card), matched(card, real)


def match_card(case, meta, card):
    """(close, exact) for one card against the real trade."""
    if card.target_user_id != case["partner"]:
        return False, False
    give = [(meta[p][1], meta[p][2]) for p in card.give_player_ids]
    recv = [(meta[p][1], meta[p][2]) for p in card.receive_player_ids]
    rg = [(a["token"], float(a["value"])) for a in case["real_give"]]
    rr = [(a["token"], float(a["value"])) for a in case["real_receive"]]
    exact = (collections.Counter(t for t, _ in give) == collections.Counter(t for t, _ in rg)
             and collections.Counter(t for t, _ in recv) == collections.Counter(t for t, _ in rr))
    ov_real = ov_card = 0.0
    for real, mine in ((rg, give), (rr, recv)):
        a, b = _overlap(real, mine)
        ov_real += a
        ov_card += b
    union = sum(v for _, v in rg + rr) + sum(v for _, v in give + recv) - ov_card
    close = union > 0 and ov_real / union >= CLOSE_SHARE - _EPS
    return bool(close), bool(exact)


def _first(flags):
    for i, f in enumerate(flags):
        if f:
            return i + 1
    return None


def replay_case(case, eng, thresholds=CANDIDATES):
    """One case at every threshold -> {str(threshold): measures}."""
    _ts, r4, _P, _s = eng
    kwargs, meta = _inputs(case, eng)
    out = {}
    for thr in thresholds:
        t0 = time.perf_counter()
        cards, _report = r4.generate_bilateral_trades(fairness_threshold=thr, **kwargs)
        secs = time.perf_counter() - t0
        flags = [match_card(case, meta, c) for c in cards]
        head = cards[:FIRST_PAGE]
        out["%.2f" % thr] = {
            "n_cards": len(cards), "secs": round(secs, 4),
            "close_rank": _first(f[0] for f in flags), "exact_rank": _first(f[1] for f in flags),
            "first30_n": len(head),
            "first30_under": sum(1 for c in head if c.fairness_score < UNDER - _EPS),
            "deck": [(c.target_user_id, tuple(sorted(c.give_player_ids)), tuple(sorted(c.receive_player_ids)))
                     for c in head]}
    return out


def run(cases_path, out_path, shard=0, of=1, thresholds=CANDIDATES, eng=None, log=None):
    eng = eng or load_engine()
    rows = []
    with open(cases_path) as f:
        cases = [json.loads(line) for line in f if line.strip()]
    for k, case in enumerate(cases[shard::of]):
        try:
            res = replay_case(case, eng, thresholds)
            row = {"lineage": case["lineage"], "by_threshold": res}
        except Exception as e:                     # counted, never silently dropped
            row = {"lineage": case["lineage"], "skip": "error:" + type(e).__name__}
        rows.append(row)
        if log and k % 10 == 0:
            print(k, len(cases[shard::of]), row.get("skip"), file=log, flush=True)
            _dump(out_path, rows, False)
    _dump(out_path, rows, True)
    return rows


def _dump(path, rows, done):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"rows": rows, "done": done}, f)
    os.replace(tmp, path)


# ── summary ─────────────────────────────────────────────────────────────────

def _boot(lineages, values, draws=DRAWS, seed=SEED):
    """Point estimate and 95% percentile interval of mean(values), resampling whole
    lineages. `values` may be a list of numbers or of (num, den) pairs (ratio of sums)."""
    groups = collections.defaultdict(list)
    for lin, v in zip(lineages, values):
        groups[lin].append(v)
    keys = sorted(groups)

    def stat(sel):
        items = [v for k in sel for v in groups[k]]
        if items and isinstance(items[0], tuple):
            den = sum(d for _, d in items)
            return sum(n for n, _ in items) / den if den else 0.0
        return sum(items) / len(items)
    point = stat(keys)
    rng = random.Random(seed)
    sims = sorted(stat([rng.choice(keys) for _ in keys]) for _ in range(draws))
    lo, hi = sims[int(0.025 * draws)], sims[int(0.975 * draws) - 1]
    return {"estimate": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)]}


def summarise(rows, thresholds=CANDIDATES, draws=DRAWS):
    ok = [r for r in rows if "skip" not in r]
    lin = [r["lineage"] for r in ok]
    base = "%.2f" % BASELINE

    def hit(r, key, col, k):
        rank = r["by_threshold"][key][col]
        return 1.0 if rank is not None and rank <= k else 0.0
    table = []
    for thr in thresholds:
        key = "%.2f" % thr
        row = {"threshold": thr,
               "close_first30": _boot(lin, [hit(r, key, "close_rank", FIRST_PAGE) for r in ok], draws),
               "close_anywhere": _boot(lin, [hit(r, key, "close_rank", 10 ** 9) for r in ok], draws),
               "exact_first30": _boot(lin, [hit(r, key, "exact_rank", FIRST_PAGE) for r in ok], draws),
               "first30_share_under_075": _boot(
                   lin, [(r["by_threshold"][key]["first30_under"], r["by_threshold"][key]["first30_n"]) for r in ok],
                   draws),
               "median_deck_seconds": round(statistics.median(r["by_threshold"][key]["secs"] for r in ok), 3),
               "median_deck_size": statistics.median(r["by_threshold"][key]["n_cards"] for r in ok),
               "median_time_ratio_vs_075": round(statistics.median(
                   r["by_threshold"][key]["secs"] / max(r["by_threshold"][base]["secs"], 1e-9) for r in ok), 4),
               "first30_identical_to_075": sum(r["by_threshold"][key]["deck"] == r["by_threshold"][base]["deck"]
                                               for r in ok)}
        if thr != BASELINE:
            row["gain_close_first30_vs_075"] = _boot(
                lin, [hit(r, key, "close_rank", FIRST_PAGE) - hit(r, base, "close_rank", FIRST_PAGE) for r in ok],
                draws)
        table.append(row)
    return {"n_trades": len(ok), "n_lineages": len(set(lin)),
            "skipped": dict(collections.Counter(r["skip"] for r in rows if "skip" in r)),
            "table": table, "selection": select(table)}


def select(table):
    """The pre-registered rule. A candidate passes when its paired gain's 95% interval
    lies above zero and its median time ratio is <= 1.10. The passing candidate with the
    highest primary estimate wins; equal estimates go to the higher threshold. None
    passing -> 0.75 is kept."""
    passing = [r for r in table if r["threshold"] != BASELINE
               and r["gain_close_first30_vs_075"]["ci95"][0] > 0
               and r["median_time_ratio_vs_075"] <= MAX_SLOWDOWN]
    if not passing:
        return {"adopted": BASELINE, "passed": [], "reason": "no candidate passed; the default stays 0.75"}
    best = max(passing, key=lambda r: (r["close_first30"]["estimate"], r["threshold"]))
    return {"adopted": best["threshold"], "passed": [r["threshold"] for r in passing],
            "reason": "highest close-match-in-first-30 among passing candidates"}


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
