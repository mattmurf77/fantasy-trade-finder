"""Deck-level measurement harness for the consensus roster-fit SORT KEY
(`consensus_fit_weight`, 2026-09-02) — docs/plans/consensus-fit-sort-key/.

Committed for REPRODUCIBILITY, not as a test — nothing in CI runs `main()`.
`backend/tests/test_consensus_fit_sort_key.py::test_junk_guard_on_harness_fixtures`
imports `build_league` / `build_mirror_league` / `stats` from here (the
D-159 sub-450 guardrail); `main()` is the sweep behind results.md.

    cd <repo root>
    # argv[1] = fairness threshold (default 0.75 = prod with the pref ON)
    PYTHONHASHSEED=0 python3 docs/plans/consensus-fit-sort-key/measure_consensus_fit.py 0.75 \
        > docs/plans/consensus-fit-sort-key/results-raw-f075.json
    PYTHONHASHSEED=0 python3 docs/plans/consensus-fit-sort-key/measure_consensus_fit.py 0.50 \
        > docs/plans/consensus-fit-sort-key/results-raw-f050.json
    PYTHONHASHSEED=0 python3 docs/plans/consensus-fit-sort-key/measure_consensus_fit.py 0.85 \
        > docs/plans/consensus-fit-sort-key/results-raw-f085.json

This is a COPY of docs/plans/package-benchmark-sweetener/measure_gap_distribution.py
(the 2026-08-21 harness; its docstring explains the fixture leagues and the
value-curve choice) with four deliberate changes:

1. **Baseline pinned to PROD values** rather than the code defaults —
   `filler_min_frac` 0.15, `overpay_adjusted` 0.0, `trade_elo_gap_max` 0.0,
   `v3_shape_max_delta` 2.0 (the D-159 consolidation bundle as flipped in
   `model_config`). What is measured is the change against the engine users
   actually get, not against `_DEFAULT_CFG`.
2. **The clock is frozen** (G-065). `_generate_for_pair_v2` carries a real
   1 s `time.monotonic()` deadline and the optimizer / breaker carry
   budgets, so an unfrozen baseline disagrees with itself by a few cards on a
   loaded machine. `main()` sets `time.monotonic` to a constant for the
   whole process; the pytest consumer monkeypatches it for the test only.
   Together with `PYTHONHASHSEED=0` (G-053) the baseline is run TWICE and
   asserted byte-identical before any delta is read.
3. **Fixture players carry a `search_rank`** (their pool rank) so
   `analyze_roster_strengths` bins them by value rather than falling back to
   `ktc_fallback_rank` for everyone; without it every roster profile has the
   same shape and the positional need/surplus metric below is meaningless.
4. **Two extra viewpoints.** `12t_1qb@u8` and `mirror@b` view the same
   leagues from a team with NO need position: half of the 12-team league
   (u1/u4/u6/u7/u8/u9/u11) and every balanced roster in prod look like
   this, and there the receive pool is the partner's whole roster — the
   sort key is the only ranking. Team 0's `["RB"]` need pre-filters the
   pool before the sort key ever runs.
5. **A third league, `mirror`**, built from the unit-test mirror fixture
   (user 6 WR + 1 RB, partner 6 RB + 1 WR, plus a balanced second partner,
   no boards anywhere). The snake-drafted leagues have little positional
   asymmetry by construction (the knob sweep found `need_fit_score` ≡ 0.5 on
   them), so they bound the DISRUPTION of the change; the mirror league is
   where its intended EFFECT has to show.

Per league × path × arm × w the sweep reports, over the deck's
`basis == "consensus"` cards: count, shape mix, sub-450 body share (any
traded asset priced under `asset_floor_abs`), distinct centrepieces (top
receive asset), top-5 and whole-set Jaccard against the same cell's w = 0
deck, mean `consensus_fit`, and the number of cards that move an asset from
a position where the user is at/above `_SURPLUS_AT` to a partner below
`_STARTER_NEED` (give side; the receive-side mirror is reported too).
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
    League, LeagueMember, TradeService, elo_to_value,
    analyze_roster_strengths, _SURPLUS_AT, _STARTER_NEED,
)

KNOB = "consensus_fit_weight"
SWEEP = (0.0, 0.25, 0.5, 1.0)
#: The fairness bar the deck is generated at. PROD sends 0.75 with the
#: fairness preference ON (`mobile/src/api/tradePregen.ts:25`, also the
#: server default at `server.py:11994`) and 0.50 with it OFF; the 2026-08-21
#: harness used 0.85, which gates out the very cards a value sort leads with
#: (a partner's lone high-value asset) before the sort key can matter.
#: `main()` takes it as argv[1]; results.md reports 0.75, 0.50 and 0.85.
FAIRNESS = float(sys.argv[1]) if len(sys.argv) > 1 and __name__ == "__main__" \
    else 0.75
JUNK_LINE = 450.0          # asset_floor_abs — the D-159 "sub-450 body"
FROZEN_CLOCK = 1.0e6

#: The D-159 consolidation bundle as it sits in prod `model_config`.
PROD_PINS = {
    "filler_min_frac":    0.15,
    "overpay_adjusted":   0.0,
    "trade_elo_gap_max":  0.0,
    "v3_shape_max_delta": 2.0,
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
    prof = {viewer_id: analyze_roster_strengths(viewer_roster, players,
                                                scoring_format)}
    for m in members:
        prof[m.user_id] = analyze_roster_strengths(m.roster, players,
                                                   scoring_format)
    return {
        "svc": svc, "players": players, "seed_elo": seed_elo,
        "viewer_id": viewer_id, "user_roster": viewer_roster,
        "league_id": f"L_{tag}", "scoring_format": scoring_format,
        "prof": prof,
    }


def build_league(*, teams, roster_size, fmt_key, scoring_format, tag,
                 viewer=0):
    """Snake-drafted fixture league (see the 2026-08-21 harness): DP values
    rescaled onto FTF's real top-asset price, 3 owned-pick pseudo-assets per
    team, hash-offset synthetic boards, odd-numbered teams boarded.

    `viewer` picks which team is the user. Team 0 (the original harness's
    viewer) has `position_needs == ["RB"]`, so its receive pools are
    need-filtered before the sort key sees them; a viewer with NO need
    position (half of this league — u1/u4/u6/u7/u8/u9/u11) receives from
    the partner's WHOLE roster, sorted, which is the shape where the sort
    key is the only ranking there is. Boarded parity is unchanged, so the
    same teams are boarded whoever is viewing."""
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
        out = {}
        for pid in roster_all:
            off = 0.0
            if _h(tag, owner, pid) % 100 < 40:
                off = 120.0 if _h("sgn", tag, owner, pid) % 2 else -120.0
            out[pid] = seed_elo[pid] + off
        return out

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
    return L


_LADDER = (1650.0, 1620.0, 1590.0, 1560.0, 1530.0, 1500.0)


def build_mirror_league(viewer="u"):
    """The unit-test mirror fixture as a league. Three teams: `u` = 6 WR +
    1 RB + QB + TE; `a` = the mirror (6 RB + 1 WR + a 1700 QB + TE); `b` =
    balanced (3 WR + 3 RB + QB + TE on the same rungs, `position_needs`
    empty). `viewer` names the user; the other two are partners. Nobody has
    a board — every pairing is the consensus path — and the viewer's raw
    board IS consensus, so the no-divergence premise holds exactly."""
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


def gen(L, fairness=None, **kw):
    """`max_per_opponent=5` is what the deck serves; prod over-generates 8
    (`exploration_base_per_opp` + `exploration_overgen`) and trims back to 5,
    so 5 is the binding cap either way."""
    return L["svc"].generate_trades(
        user_id=L["viewer_id"], user_elo=dict(L["user_elo"]),
        user_roster=L["user_roster"], league_id=L["league_id"],
        seed_elo=dict(L["seed_elo"]),
        fairness_threshold=FAIRNESS if fairness is None else fairness,
        max_per_opponent=5, scoring_format=L["scoring_format"], **kw)


def card_key(c):
    return (frozenset(c.give_player_ids), frozenset(c.receive_player_ids),
            c.target_user_id)


def _jaccard(a, b):
    a, b = set(a), set(b)
    return round(len(a & b) / len(a | b), 3) if (a | b) else None


def stats(cards, L, baseline=None):
    """Consensus-card metrics for one deck. `baseline` is the same cell's
    w = 0 deck (a list of cards) for the Jaccard columns."""
    seed = L["seed_elo"]
    players = L["players"]
    fmt = L["scoring_format"]

    def sv(pid):
        return elo_to_value(seed[pid])

    def pos(pid):
        return getattr(players.get(pid), "position", None)

    def starters(prof, p):
        td = prof["tier_depth"].get(p, {})
        return td.get("elite", 0) + td.get("starter", 0)

    def need_thr(p):
        return 2 if (p == "QB" and fmt.startswith("sf")) else _STARTER_NEED[p]

    cons = [c for c in cards if c.basis == "consensus"]
    prof_u = L["prof"][L["viewer_id"]]
    shapes: dict[str, int] = {}
    junk = 0
    moves_give = 0
    moves_recv = 0
    from_user_surplus = 0
    from_partner_surplus = 0
    centres = set()
    fits = []
    for c in cons:
        sh = f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
        shapes[sh] = shapes.get(sh, 0) + 1
        if any(sv(p) < JUNK_LINE
               for p in c.give_player_ids + c.receive_player_ids):
            junk += 1
        prof_o = L["prof"][c.target_user_id]
        if any(pos(p) in _SURPLUS_AT
               and starters(prof_u, pos(p)) >= _SURPLUS_AT[pos(p)]
               and starters(prof_o, pos(p)) < need_thr(pos(p))
               for p in c.give_player_ids):
            moves_give += 1
        if any(pos(p) in _SURPLUS_AT
               and starters(prof_o, pos(p)) >= _SURPLUS_AT[pos(p)]
               and starters(prof_u, pos(p)) < need_thr(pos(p))
               for p in c.receive_player_ids):
            moves_recv += 1
        if any(pos(p) in _SURPLUS_AT
               and starters(prof_u, pos(p)) >= _SURPLUS_AT[pos(p)]
               for p in c.give_player_ids):
            from_user_surplus += 1
        if any(pos(p) in _SURPLUS_AT
               and starters(prof_o, pos(p)) >= _SURPLUS_AT[pos(p)]
               for p in c.receive_player_ids):
            from_partner_surplus += 1
        centres.add(max(c.receive_player_ids, key=sv))
        if getattr(c, "consensus_fit", None) is not None:
            fits.append(c.consensus_fit)

    out = {
        "cards_total": len(cards),
        "consensus_cards": len(cons),
        "shapes": dict(sorted(shapes.items())),
        "sub450_cards": junk,
        "sub450_share": round(junk / len(cons), 4) if cons else None,
        "distinct_centerpieces": len(centres),
        "mean_consensus_fit": (round(sum(fits) / len(fits), 3)
                               if fits else None),
        "surplus_to_need_give": moves_give,
        "surplus_to_need_recv": moves_recv,
        "give_from_user_surplus": from_user_surplus,
        "recv_from_partner_surplus": from_partner_surplus,
        "top5": [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
                  c.target_user_id] for c in cons[:5]],
    }
    if baseline is not None:
        bcons = [c for c in baseline if c.basis == "consensus"]
        out["top5_jaccard"] = _jaccard([card_key(c) for c in cons[:5]],
                                       [card_key(c) for c in bcons[:5]])
        out["set_jaccard"] = _jaccard([card_key(c) for c in cons],
                                      [card_key(c) for c in bcons])
    return out


def _fingerprint(cards):
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.basis] for c in cards]


_12T = dict(teams=12, roster_size=26, fmt_key="dp_value_1qb",
            scoring_format="1qb_ppr", tag="12t")
_16T = dict(teams=16, roster_size=21, fmt_key="dp_value_2qb",
            scoring_format="sf_tep", tag="16t")

#: (name, builder). The `@` suffix names the viewer; the first three are the
#: 2026-08-21 harness's viewpoints, the last two are the no-need viewers.
LEAGUES = [
    ("12t_1qb@u0", lambda: build_league(**_12T)),
    ("16t_sf@u0", lambda: build_league(**_16T)),
    ("mirror@u", lambda: build_mirror_league("u")),
    ("12t_1qb@u8", lambda: build_league(**_12T, viewer=8)),
    ("mirror@b", lambda: build_mirror_league("b")),
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
    for lname, build in LEAGUES:
        for path, v3 in (("v3", True), ("v2_only", False)):
            live_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3,
                          "trade.bakeoff": False})
            L = build()
            for arm, ctx in arms:
                def run(w):
                    reset_cfg(**{KNOB: w})
                    if ctx is None:
                        return gen(L)
                    with ctx():
                        return gen(L)
                base1, base2 = run(0.0), run(0.0)
                identical = _fingerprint(base1) == _fingerprint(base2)
                for w in SWEEP:
                    cards = base1 if w == 0.0 else run(w)
                    out["cells"].append({
                        "league": lname, "path": path, "arm": arm, "w": w,
                        "baseline_identical": identical,
                        **stats(cards, L, baseline=base1),
                    })
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
