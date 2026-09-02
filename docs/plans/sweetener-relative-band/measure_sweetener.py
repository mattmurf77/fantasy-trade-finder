"""Deck-level measurement harness for the gap-sweetener relative band +
best-effort fallback (`sweetener_gap_frac`, `sweetener_best_effort`,
2026-09-02, #414) — docs/plans/sweetener-relative-band/.

Committed for REPRODUCIBILITY, not as a test — nothing in CI runs `main()`.
It is the sweep behind results.md.

    cd <repo root>
    # argv[1] = fairness threshold (default 0.75 = prod with the pref ON)
    # argv[2] = output path. The engine's flag/experiment loaders PRINT to
    #           stdout, so a `>` redirect captures thousands of log lines
    #           ahead of the JSON — write the JSON to a file instead.
    PYTHONHASHSEED=0 python3 docs/plans/sweetener-relative-band/measure_sweetener.py 0.75 \
        docs/plans/sweetener-relative-band/results-raw-f075.json
    PYTHONHASHSEED=0 python3 docs/plans/sweetener-relative-band/measure_sweetener.py 0.50 \
        docs/plans/sweetener-relative-band/results-raw-f050.json

This is a COPY of docs/plans/package-benchmark-sweetener/measure_gap_distribution.py
(the 2026-08-21 harness; its docstring explains the fixture leagues and the
value-curve choice) carrying the consensus-fit harness's corrections
(docs/plans/consensus-fit-sort-key/measure_consensus_fit.py — prod pins,
frozen clock, `search_rank`, extra viewpoints) with these changes:

1. **Baseline pinned to PROD values** as read 2026-09-01/02: the D-159
   bundle (`filler_min_frac` 0.15, `overpay_adjusted` 0, `trade_elo_gap_max`
   0, `v3_shape_max_delta` 2), `asset_floor_abs` 450, `max_overpay_frac`
   0.25, `sweetener_gap_threshold` 1539, and D-172's `consensus_fit_weight`
   **0.5** (live since 2026-09-02). What is measured is the change against
   the engine users actually get.
2. **The clock is frozen** (G-065) and `PYTHONHASHSEED=0` is required
   (G-053); the baseline is run TWICE per cell and asserted byte-identical
   before any delta is read.
3. **Variants, not a sweep** (results.md § Variants): V0 the prod baseline;
   V1 threshold 750 alone — QA's known-regressing cell (all-or-nothing
   closer, so a card partially closable to 1,535 ships at its original
   gap); V2 750 + best-effort; V3 750 + frac 0.12 + best-effort (the
   proposed live bundle); V4 750 + frac 0.15 + best-effort.
4. **Per league × path × arm × variant** the sweep reports, over the
   WHOLE deck: cards; sweetened share split full vs partial; the share
   over the 1,539 line; gap p10/p50/p90; the D-159 sub-450 body share; the
   partner-favourable share (receive ≤ give on consensus values); top-5
   and whole-set Jaccard against the same cell's V0 deck; and how many
   sweeteners are PICK pseudo-assets vs players.
5. **A #414-shaped league** (`414_1x1@u4`): the 12-team 1QB fixture viewed
   from team 4, with the viewer's best WR re-priced to London's 5,932.8
   and an UNBOARDED partner's (team 2) best WR to CeeDee's seed 6,965.6
   (packages to the served 7,328.9 — see
   backend/tests/test_sweetener_relative_band.py), so the deck can carry a
   WR-for-WR 1x1 at the operator's 19% gap on the consensus path. Each
   cell reports that card's status: absent, plain, full close or partial
   close, and the equalizer's value. (Viewer 0's `["RB"]` need filters
   WRs out of the receive pool; on the no-need viewers the 0.81 1x1 loses
   the deck cut — viewer 4 is where the card is served.)

Arms: B (`current`, no overlay — reads the row), A (`baseline`,
`MODEL_A_PROFILE`, sweetener pinned OFF), D (`challenger`, inherits the
row), and C (`gen_v2`, its own `close_value_gap` call; path-independent,
run once per league under the v3 label).
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
    League, LeagueMember, TradeService, elo_to_value, is_pick_asset,
)

KNOB_THR = "sweetener_gap_threshold"
KNOB_FRAC = "sweetener_gap_frac"
KNOB_BEST = "sweetener_best_effort"

#: (name, overrides on top of PROD_PINS)
VARIANTS = [
    ("V0_prod",           {}),
    ("V1_thr750",         {KNOB_THR: 750.0}),
    ("V2_thr750_be",      {KNOB_THR: 750.0, KNOB_BEST: 1.0}),
    ("V3_thr750_f12_be",  {KNOB_THR: 750.0, KNOB_FRAC: 0.12, KNOB_BEST: 1.0}),
    ("V4_thr750_f15_be",  {KNOB_THR: 750.0, KNOB_FRAC: 0.15, KNOB_BEST: 1.0}),
]

FAIRNESS = float(sys.argv[1]) if len(sys.argv) > 1 and __name__ == "__main__" \
    else 0.75
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 and __name__ == "__main__" \
    else None
GAP_LINE = 1539.0          # one late 1st — the 2026-08-21 line
JUNK_LINE = 450.0          # asset_floor_abs — the D-159 "sub-450 body"
FROZEN_CLOCK = 1.0e6
LONDON, CEEDEE = 5932.8, 6965.6

#: Prod `model_config` as read 2026-09-01/02.
PROD_PINS = {
    "filler_min_frac":      0.15,
    "asset_floor_abs":      450.0,
    "max_overpay_frac":     0.25,
    "overpay_adjusted":     0.0,
    "trade_elo_gap_max":    0.0,
    "v3_shape_max_delta":   2.0,
    "sweetener_gap_threshold": 1539.0,
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


def build_league(*, teams, roster_size, fmt_key, scoring_format, tag,
                 viewer=0, plant_414=False):
    """Snake-drafted fixture league (see the 2026-08-21 harness): DP values
    rescaled onto FTF's real top-asset price, 3 owned-pick pseudo-assets per
    team, hash-offset synthetic boards, odd-numbered teams boarded.

    `plant_414`: re-price the viewer's best WR to London (5,932.8) and the
    best WR of the first UNBOARDED partner (team 2) to CeeDee's seed
    (6,965.6) so the deck carries the operator's card shape."""
    rows = _pool(fmt_key)[:teams * roster_size]
    players, seed_elo = {}, {}
    top = rows[0][fmt_key]
    scale = 7737.0 / top
    for rank, r in enumerate(rows, 1):
        pid = r["player_id"]
        players[pid] = P(id=pid, name=r["full_name"], position=r["position"],
                         team=r.get("team") or "FA", age=25,
                         search_rank=rank)
        seed_elo[pid] = _elo(max(r[fmt_key] * scale, 5.0))

    rosters = [[] for _ in range(teams)]
    for i, r in enumerate(rows):                       # snake draft
        rnd, slot = divmod(i, teams)
        t = slot if rnd % 2 == 0 else teams - 1 - slot
        rosters[t].append(r["player_id"])

    planted = {}
    if plant_414:
        def best_wr(t):
            wrs = [p for p in rosters[t] if players[p].position == "WR"]
            return max(wrs, key=lambda p: seed_elo[p])
        london, ceedee = best_wr(viewer), best_wr(2 if viewer != 2 else 4)
        seed_elo[london], seed_elo[ceedee] = _elo(LONDON), _elo(CEEDEE)
        planted = {"london": london, "ceedee": ceedee,
                   "partner": f"u{2 if viewer != 2 else 4}"}

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
    svc = TradeService(players=players)
    ltag = f"{tag}v{viewer}" + ("p414" if plant_414 else "")
    svc.add_league(League(league_id=f"L_{ltag}", name=ltag, platform="demo",
                          members=members))
    return {
        "svc": svc, "players": players, "seed_elo": seed_elo,
        "viewer_id": f"u{viewer}", "user_roster": rosters[viewer],
        "user_elo": board(f"u{viewer}", all_ids),
        "league_id": f"L_{ltag}", "scoring_format": scoring_format,
        "planted": planted,
    }


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


def gen(L, **kw):
    """`max_per_opponent=5` is what the deck serves (prod over-generates 8
    and trims back to 5, so 5 is the binding cap either way)."""
    return L["svc"].generate_trades(
        user_id=L["viewer_id"], user_elo=dict(L["user_elo"]),
        user_roster=L["user_roster"], league_id=L["league_id"],
        seed_elo=dict(L["seed_elo"]), fairness_threshold=FAIRNESS,
        max_per_opponent=5, scoring_format=L["scoring_format"], **kw)


def gen_arm_c(L):
    import backend.bakeoff_runner as bo
    return bo.gen_v2_cards(L["svc"], dict(
        user_id=L["viewer_id"], user_elo=dict(L["user_elo"]),
        user_roster=L["user_roster"], league_id=L["league_id"],
        seed_elo=dict(L["seed_elo"]), fairness_threshold=FAIRNESS,
        max_per_opponent=5, scoring_format=L["scoring_format"]))


def card_key(c):
    return (frozenset(c.give_player_ids), frozenset(c.receive_player_ids),
            c.target_user_id)


def _jaccard(a, b):
    a, b = set(a), set(b)
    return round(len(a & b) / len(a | b), 3) if (a | b) else None


def _pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1)


def stats(cards, L, baseline=None):
    seed, players = L["seed_elo"], L["players"]

    def sv(pid):
        return elo_to_value(seed[pid])

    gaps = [abs((c.give_value or 0.0) - (c.receive_value or 0.0))
            for c in cards]
    sweet = [c for c in cards if getattr(c, "gap_sweetener", None)]
    partial = [c for c in sweet if c.gap_sweetener.get("partial")]
    junk = sum(1 for c in cards
               if any(sv(p) < JUNK_LINE
                      for p in c.give_player_ids + c.receive_player_ids))
    partner_fav = sum(1 for c in cards
                      if (c.receive_value or 0.0) <= (c.give_value or 0.0))
    pick_sw = sum(1 for c in sweet
                  if is_pick_asset(players.get(c.gap_sweetener["player_id"])))
    n = len(cards)
    out = {
        "cards": n,
        "sweetened": len(sweet),
        "sweetened_full": len(sweet) - len(partial),
        "sweetened_partial": len(partial),
        "sweetened_share": round(len(sweet) / n, 4) if n else None,
        "gap_over_1539": sum(1 for g in gaps if g > GAP_LINE),
        "gap_over_1539_share": (round(sum(1 for g in gaps if g > GAP_LINE) / n, 4)
                                if n else None),
        "gap_p10": _pct(gaps, 0.10), "gap_p50": _pct(gaps, 0.50),
        "gap_p90": _pct(gaps, 0.90),
        "gap_mean": round(sum(gaps) / n, 1) if n else None,
        "sub450_cards": junk,
        "sub450_share": round(junk / n, 4) if n else None,
        "partner_fav": partner_fav,
        "partner_fav_share": round(partner_fav / n, 4) if n else None,
        "sweetener_pick": pick_sw,
        "sweetener_player": len(sweet) - pick_sw,
        "shapes": {},
    }
    for c in cards:
        sh = f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
        out["shapes"][sh] = out["shapes"].get(sh, 0) + 1
    out["shapes"] = dict(sorted(out["shapes"].items()))
    if baseline is not None:
        out["top5_jaccard"] = _jaccard([card_key(c) for c in cards[:5]],
                                       [card_key(c) for c in baseline[:5]])
        out["set_jaccard"] = _jaccard([card_key(c) for c in cards],
                                      [card_key(c) for c in baseline])
    planted = L.get("planted")
    if planted:
        hit = [c for c in cards
               if planted["london"] in c.give_player_ids
               and planted["ceedee"] in c.receive_player_ids]
        if not hit:
            out["card414"] = "absent"
        else:
            c = hit[0]
            gs = c.gap_sweetener
            out["card414"] = ("plain" if not gs
                              else "partial" if gs.get("partial") else "full")
            out["card414_shape"] = f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
            out["card414_gap"] = round(abs(c.give_value - c.receive_value), 1)
            out["card414_fairness"] = c.fairness_score
            out["card414_basis"] = c.basis
            if gs:
                out["card414_equalizer_value"] = round(sv(gs["player_id"]), 1)
    return out


def _fingerprint(cards):
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.give_value, c.receive_value, getattr(c, "gap_sweetener", None)]
            for c in cards]


_12T = dict(teams=12, roster_size=26, fmt_key="dp_value_1qb",
            scoring_format="1qb_ppr", tag="12t")
_16T = dict(teams=16, roster_size=21, fmt_key="dp_value_2qb",
            scoring_format="sf_tep", tag="16t")

LEAGUES = [
    ("12t_1qb@u0", lambda: build_league(**_12T)),
    ("16t_sf@u0", lambda: build_league(**_16T)),
    ("12t_1qb@u8", lambda: build_league(**_12T, viewer=8)),
    # Viewer 4, deliberately: team 0's `position_needs == ["RB"]` filters the
    # consensus receive pool to RBs (a WR never enters it), and on the
    # no-need viewers u1/u6/u8 the 0.81-fairness 1x1 loses the deck cut to
    # the body-for-body swaps at every variant. Viewer 4 is the roster on
    # which the card is served, so it is the one that can be measured.
    ("414_1x1@u4", lambda: build_league(**_12T, viewer=4, plant_414=True)),
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
                    "prod_pins": PROD_PINS,
                    "variants": {k: v for k, v in VARIANTS},
                    "fairness_threshold": FAIRNESS,
                    "frozen_clock": FROZEN_CLOCK},
           "cells": []}
    for lname, build in LEAGUES:
        for path, v3 in (("v3", True), ("v2_only", False)):
            live_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3,
                          "trade.bakeoff": False})
            L = build()
            arm_list = list(arms) + ([("C_gen_v2", "C")] if v3 else [])
            for arm, ctx in arm_list:
                def run(over):
                    reset_cfg(**over)
                    if ctx == "C":
                        return gen_arm_c(L)
                    if ctx is None:
                        return gen(L)
                    with ctx():
                        return gen(L)
                base1, base2 = run({}), run({})
                identical = _fingerprint(base1) == _fingerprint(base2)
                for vname, over in VARIANTS:
                    cards = base1 if not over else run(over)
                    out["cells"].append({
                        "league": lname, "path": path, "arm": arm,
                        "variant": vname, "baseline_identical": identical,
                        **stats(cards, L, baseline=base1),
                    })
    blob = json.dumps(out, indent=1)
    if OUT_PATH:
        with open(OUT_PATH, "w") as fh:
            fh.write(blob + "\n")
    else:
        print(blob)


if __name__ == "__main__":
    main()
