"""Deck-level measurement harness for the below-market card reason
(`reason_below_market_frac`, 2026-09-02) — docs/plans/below-market-reason/.

Committed for REPRODUCIBILITY, not as a test — nothing in CI runs `main()`.
It answers ONE question: at a given knob value, what share of served cards
would carry the line? Too many and the line is noise; the number that sets
the live value is in results.md.

    cd <repo root>
    # argv[1] = fairness threshold (default 0.75 = prod with the pref ON)
    PYTHONHASHSEED=0 python3 docs/plans/below-market-reason/measure_below_market.py 0.75 \
        > docs/plans/below-market-reason/results-raw-f075.json
    PYTHONHASHSEED=0 python3 docs/plans/below-market-reason/measure_below_market.py 0.50 \
        > docs/plans/below-market-reason/results-raw-f050.json

This is a COPY of docs/plans/consensus-fit-sort-key/measure_consensus_fit.py
(the D-172 harness — prod pins, frozen clock (G-065), `search_rank` on
fixture players, the two no-need viewpoints, the mirror league) with the
sweep re-pointed at this knob and three deliberate changes:

1. **What is counted.** Per league × path × arm × knob: cards served, cards
   carrying the line (count and share), the same split by `basis`, and the
   distribution of the give-headliner's shrunk gap `(seed − user) / seed`
   over every served card at knob 0 — that distribution is what makes the
   share readable as a curve rather than a step, and it does not depend on
   the knob at all (the knob never changes the deck).
2. **Two board models, because the D-172 boards cannot grade a threshold.**
   The snake-drafted fixture boards offset 40% of players by exactly ±120
   Elo (`board_mode="binary"`) — a −120 offset is a 45% value gap, so every
   knob in [0.05, 0.45] fires on the same cards and the share is flat. A
   second mode (`board_mode="graded"`) draws each player's offset uniformly
   in [−200, +200] Elo from the same hash, so the gap distribution is
   continuous and the share falls as the knob rises. Both are reported;
   neither is a prod board.
3. **The viewer has comparison counts.** The D-172 harness passed no
   `confidence`, which makes `_shrink_user_elo` return the RAW board — the
   one board this feature never reads. Here every viewer player gets a
   hash-drawn count in {0, 1, 2, 4, 8, 16} (`conf_mode="hashed"`), so the
   stamp reads a genuinely shrunk board; `conf_mode="none"` (raw) is also
   run so the shrink's effect on the share is visible.

Arms: B_current (live), A_baseline (`model_a()` — the knob is EXCLUDED from
the profile, so arm A inherits the live row) and D_challenger.
"""
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.feature_flags as ff            # noqa: E402
import backend.trade_service as ts            # noqa: E402
from backend.trade_service import (           # noqa: E402
    League, LeagueMember, TradeService, elo_to_value, deck_give_headliner,
    is_pick_asset,
)

KNOB = "reason_below_market_frac"
SWEEP = (0.05, 0.10, 0.15, 0.25, 0.35)
FAIRNESS = float(sys.argv[1]) if len(sys.argv) > 1 and __name__ == "__main__" \
    else 0.75
FROZEN_CLOCK = 1.0e6
#: Gap bands for the headliner-gap histogram (value-space fractions).
BANDS = (0.0, 0.05, 0.10, 0.15, 0.25, 0.35, 0.50, 1.01)

#: The D-159 consolidation bundle as it sits in prod `model_config`, plus
#: the D-172 live value (shipped 2026-09-02 at 0.5).
PROD_PINS = {
    "filler_min_frac":      0.15,
    "overpay_adjusted":     0.0,
    "trade_elo_gap_max":    0.0,
    "v3_shape_max_delta":   2.0,
    "consensus_fit_weight": 0.5,
}


def freeze_clock():
    """G-065 — every generator deadline/budget reads a constant."""
    time.monotonic = lambda: FROZEN_CLOCK


@dataclass
class P:
    id: str
    name: str
    position: str
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None
    search_rank: Optional[int] = None
    pick_value: Optional[float] = None


def _elo(value: float) -> float:
    """Inverse of elo_to_value at the shipped curve (k=0.005, ref 1500)."""
    return 1500.0 + math.log(value / 1000.0) / 0.005


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _pool(fmt_key):
    raw = json.load(open(os.path.join(
        ROOT, "backend/tests/fixtures/player_pool_2026.json")))["players"]
    rows = [r for r in raw.values()
            if r.get("position") in ("QB", "RB", "WR", "TE")
            and (r.get(fmt_key) or 0) > 0]
    rows.sort(key=lambda r: -r[fmt_key])
    return rows


def _finish(players, seed_elo, viewer_id, viewer_roster, members, tag,
            scoring_format):
    svc = TradeService(players=players)
    svc.add_league(League(league_id=f"L_{tag}", name=tag, platform="demo",
                          members=members))
    return {
        "svc": svc, "players": players, "seed_elo": seed_elo,
        "viewer_id": viewer_id, "user_roster": viewer_roster,
        "league_id": f"L_{tag}", "scoring_format": scoring_format,
    }


def _offset(tag, owner, pid, board_mode):
    if board_mode == "binary":                 # the D-172 fixture boards
        if _h(tag, owner, pid) % 100 < 40:
            return 120.0 if _h("sgn", tag, owner, pid) % 2 else -120.0
        return 0.0
    # graded: uniform in [-200, +200] Elo
    return (_h("grd", tag, owner, pid) % 40001) / 100.0 - 200.0


def build_league(*, teams, roster_size, fmt_key, scoring_format, tag,
                 viewer=0, board_mode="binary"):
    """Snake-drafted fixture league (see the D-172 harness): DP values
    rescaled onto FTF's real top-asset price, 3 owned-pick pseudo-assets per
    team, hash-offset synthetic boards, odd-numbered teams boarded."""
    rows = _pool(fmt_key)[:teams * roster_size]
    players, seed_elo = {}, {}
    top = rows[0][fmt_key]
    scale = 7737.0 / top
    for rank, r in enumerate(rows, 1):
        pid = r["player_id"]
        players[pid] = P(id=pid, name=r["full_name"], position=r["position"],
                         team=r.get("team") or "FA", age=r.get("age") or 25,
                         search_rank=rank)
        seed_elo[pid] = _elo(max(r[fmt_key] * scale, 5.0))

    rosters = [[] for _ in range(teams)]
    for i, r in enumerate(rows):                       # snake draft
        rnd, slot = divmod(i, teams)
        t = slot if rnd % 2 == 0 else teams - 1 - slot
        rosters[t].append(r["player_id"])

    for t in range(teams):                             # 3 owned picks each
        for k, (label, elo) in enumerate(
                (("2027 1st", _elo(2400.0)), ("2027 2nd", _elo(700.0)),
                 ("2028 1st", _elo(2200.0)))):
            pid = f"{tag}_pick_{t}_{k}"
            players[pid] = P(id=pid, name=f"T{t} {label}", position="PICK",
                             team="PICK", age=21)
            seed_elo[pid] = elo
            rosters[t].append(pid)

    def board(owner, roster_all):
        return {pid: seed_elo[pid] + _offset(tag, owner, pid, board_mode)
                for pid in roster_all}

    all_ids = list(seed_elo)
    members = []
    for t in range(teams):
        if t == viewer:
            continue
        members.append(LeagueMember(
            user_id=f"u{t}", username=f"team{t}", roster=rosters[t],
            elo_ratings=board(f"u{t}", all_ids),
            has_rankings=(t % 2 == 1)))
    L = _finish(players, seed_elo, f"u{viewer}", rosters[viewer], members,
                f"{tag}v{viewer}", scoring_format)
    L["user_elo"] = board(f"u{viewer}", all_ids)
    L["confidence"] = {pid: (0, 1, 2, 4, 8, 16)[_h("conf", tag, pid) % 6]
                       for pid in all_ids}
    return L


_LADDER = (1650.0, 1620.0, 1590.0, 1560.0, 1530.0, 1500.0)


def build_mirror_league(viewer="u"):
    """The D-172 mirror fixture as a league. The viewer's raw board IS the
    seed, so by construction NO card can ever carry the line here — kept as
    the null cell that proves the share is a board property, not a deck
    property."""
    players, seed = {}, {}

    def add(pid, pos, elo, rank):
        players[pid] = P(id=pid, name=pid, position=pos, search_rank=rank)
        seed[pid] = elo

    u, a, b = [], [], []
    for i, e in enumerate(_LADDER, 1):
        add(f"uWR{i}", "WR", e, 10 + i); u.append(f"uWR{i}")
        add(f"aRB{i}", "RB", e, 10 + i); a.append(f"aRB{i}")
    for i, e in enumerate(_LADDER[:3], 1):
        add(f"bWR{i}", "WR", e, 10 + i); b.append(f"bWR{i}")
        add(f"bRB{i}", "RB", e, 10 + i); b.append(f"bRB{i}")
    add("uRB1", "RB", 1600.0, 15); u.append("uRB1")
    add("aWR1", "WR", 1600.0, 15); a.append("aWR1")
    add("uQB", "QB", 1550.0, 30);  u.append("uQB")
    add("aQB", "QB", 1700.0, 5);   a.append("aQB")
    add("bQB", "QB", 1550.0, 30);  b.append("bQB")
    for side, lst in (("u", u), ("a", a), ("b", b)):
        add(f"{side}TE", "TE", 1500.0, 40); lst.append(f"{side}TE")

    teams = {"u": ("wr_heavy", u), "a": ("mirror", a), "b": ("balanced", b)}
    members = [LeagueMember(user_id=k, username=n, roster=r,
                            elo_ratings={}, has_rankings=False)
               for k, (n, r) in teams.items() if k != viewer]
    L = _finish(players, seed, viewer, teams[viewer][1], members,
                f"mirror_{viewer}", "1qb_ppr")
    L["user_elo"] = dict(seed)
    L["confidence"] = {pid: 8 for pid in seed}
    return L


def live_flags(**over):
    cfg = json.load(open(os.path.join(ROOT, "config/features.json")))
    flags = {k: v for k, v in cfg.items() if isinstance(v, bool)}
    base = dict(ff.DEFAULT_FLAGS)
    base.update(flags)
    base.update(over)
    ff._flags_cache = base


def reset_cfg(**over):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(PROD_PINS)
    ts._cfg.update(over)


def gen(L, conf_mode, fairness=None):
    """`max_per_opponent=5` is what the deck serves (see the D-172 harness)."""
    L["svc"]._trade_cards.clear()
    return L["svc"].generate_trades(
        user_id=L["viewer_id"], user_elo=dict(L["user_elo"]),
        user_roster=L["user_roster"], league_id=L["league_id"],
        seed_elo=dict(L["seed_elo"]),
        fairness_threshold=FAIRNESS if fairness is None else fairness,
        max_per_opponent=5, scoring_format=L["scoring_format"],
        confidence=(dict(L["confidence"]) if conf_mode == "hashed" else None))


def _fingerprint(cards):
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.basis] for c in cards]


def headliner_gaps(cards, L, conf_mode):
    """The shrunk give-headliner gap of every served card (None for a
    picks-only give side) — the knob-independent quantity the share is a
    function of. Recomputes the shrink exactly as the generator does."""
    seed = L["seed_elo"]
    conf = dict(L["confidence"]) if conf_mode == "hashed" else None
    shrunk = ts._shrink_user_elo(dict(L["user_elo"]), seed, conf)
    out = []
    for c in cards:
        head = deck_give_headliner(c.give_player_ids, seed, L["players"])
        p = L["players"].get(head) if head else None
        if p is None or is_pick_asset(p):
            out.append(None)
            continue
        sv = elo_to_value(seed.get(head, 1500.0))
        uv = elo_to_value(shrunk.get(head, seed.get(head, 1500.0)))
        out.append(round((sv - uv) / sv, 4))
    return out


def stats(cards, gaps):
    n = len(cards)
    carrying = [c for c in cards if c.reasons]
    by_basis = {}
    for c in cards:
        b = by_basis.setdefault(c.basis, {"cards": 0, "carrying": 0})
        b["cards"] += 1
        b["carrying"] += 1 if c.reasons else 0
    hist = {}
    for lo, hi in zip(BANDS, BANDS[1:]):
        hist[f"[{lo:.2f},{hi:.2f})"] = sum(
            1 for g in gaps if g is not None and lo <= g < hi)
    return {
        "cards_total": n,
        "carrying": len(carrying),
        "share": round(len(carrying) / n, 4) if n else None,
        "by_basis": by_basis,
        "distinct_named": len({c.reasons[0] for c in carrying}),
        "headliner_gap_hist": hist,
        "picks_only_give": sum(1 for g in gaps if g is None),
        "above_market": sum(1 for g in gaps if g is not None and g < 0),
    }


_12T = dict(teams=12, roster_size=26, fmt_key="dp_value_1qb",
            scoring_format="1qb_ppr", tag="12t")
_16T = dict(teams=16, roster_size=21, fmt_key="dp_value_2qb",
            scoring_format="sf_tep", tag="16t")

LEAGUES = [
    ("12t_1qb@u0", lambda bm: build_league(**_12T, board_mode=bm)),
    ("16t_sf@u0", lambda bm: build_league(**_16T, board_mode=bm)),
    ("mirror@u", lambda bm: build_mirror_league("u")),
    ("12t_1qb@u8", lambda bm: build_league(**_12T, viewer=8, board_mode=bm)),
]


def main():
    freeze_clock()
    from backend.bakeoff_profiles import model_a, model_challenger
    arms = (
        ("B_current", None),
        ("A_baseline", model_a),
        ("D_challenger", model_challenger),
    )
    out = {"meta": {"pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                    "prod_pins": PROD_PINS, "sweep": list(SWEEP),
                    "fairness_threshold": FAIRNESS,
                    "frozen_clock": FROZEN_CLOCK},
           "cells": []}
    live_flags(**{"trade_engine.v2": True, "trade_engine.v3": True,
                  "trade.bakeoff": False})
    for lname, build in LEAGUES:
        for board_mode in ("binary", "graded"):
            if lname.startswith("mirror") and board_mode == "graded":
                continue
            L = build(board_mode)
            for conf_mode in ("hashed", "none"):
                for arm, ctx in arms:
                    def run(w):
                        reset_cfg(**({KNOB: w} if w else {}))
                        if ctx is None:
                            return gen(L, conf_mode)
                        with ctx():
                            return gen(L, conf_mode)
                    base1, base2 = run(0.0), run(0.0)
                    identical = _fingerprint(base1) == _fingerprint(base2)
                    gaps = headliner_gaps(base1, L, conf_mode)
                    for w in (0.0,) + SWEEP:
                        cards = base1 if w == 0.0 else run(w)
                        out["cells"].append({
                            "league": lname, "board": board_mode,
                            "conf": conf_mode, "arm": arm, "w": w,
                            "baseline_identical": identical,
                            "deck_invariant": (_fingerprint(cards)
                                               == _fingerprint(base1)),
                            **stats(cards, gaps),
                        })
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
