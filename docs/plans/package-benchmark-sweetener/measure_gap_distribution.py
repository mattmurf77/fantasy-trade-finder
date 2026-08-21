"""One-shot deck-size / gap-distribution measurement for the 2026-08-21
package-benchmark + gap-sweetener branch (W0-style, fixture-only).

Committed for REPRODUCIBILITY, not as a test — nothing runs it in CI. It is
the harness behind the numbers in living-memory/TEST_LEDGER.md 2026-08-21a.

    # branch tip
    cd <repo>            && python3 docs/plans/package-benchmark-sweetener/measure_gap_distribution.py
    # the before side
    git archive origin/main | tar -x -C /tmp/main_tree
    cd /tmp/main_tree    && python3 <abs path to this file>

It builds the two constructed fixture leagues the fit-challenger W0 dry run
used (TEST_LEDGER 2026-08-20b) — 12-team 1QB 26-man and 16-team SF 21-man,
drafted from backend/tests/fixtures/player_pool_2026.json with 3 owned-pick
pseudo-assets per team and hash-offset synthetic boards — and runs each
bake-off arm through each engine path, printing cards, |give − receive|
distribution, and the share above 1539 (one late 1st).

ONE DEVIATION FROM THE W0 RECIPE, and it is load-bearing: W0 seeded Elo from
a flat rank ladder (1750 → 1250), which compresses the whole board into
286..3490 value units — a 1539 gap is then almost arithmetically unreachable
and the measurement reads zero everywhere regardless of the engine. Here the
seeds come from the pool's own DynastyProcess values rescaled so the #1 asset
lands on FTF's real top-asset price (~7737, the served Nacua number in
docs/reviews/2026-08-21-market-curve-comparison.md), which reproduces the
production value CURVE, not just its ordering.

Fixture-only and DB-free: _cfg is pinned to the code defaults (_DEFAULT_CFG),
flags come from config/features.json (the live posture). Synthetic boards mean
the levels are DIRECTIONAL; the main-vs-branch DELTAS are the result.
"""
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__))) \
    if False else os.getcwd()
sys.path.insert(0, ROOT)

import backend.feature_flags as ff            # noqa: E402
import backend.trade_service as ts            # noqa: E402
from backend.trade_service import (           # noqa: E402
    League, LeagueMember, TradeService, elo_to_value,
)

GAP_LINE = 1539.0          # one late 1st — the operator's agreed line


@dataclass
class P:
    id: str
    name: str
    position: str
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None


def _elo(value: float) -> float:
    """Inverse of elo_to_value at the shipped curve (k=0.005, ref 1500)."""
    import math
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


def build_league(*, teams, roster_size, fmt_key, scoring_format, tag):
    """Rank-ladder Elo seeds (1750 -> 1250) over the pool, snake-drafted into
    `teams` rosters, + 3 owned-pick pseudo-assets per team.  Personal boards
    are hash offsets (+/-120 on ~40% of a member's assets); the viewer and
    every other member is boarded (has_rankings=True on half of them)."""
    rows = _pool(fmt_key)[:teams * roster_size]
    players, seed_elo = {}, {}
    # Value scale: the pool's DP values rescaled so the #1 asset lands on
    # FTF's own top-asset value (~7737 = the served Nacua price, memo
    # docs/reviews/2026-08-21-market-curve-comparison.md).  A flat
    # rank-ladder (the fit W0's 1750->1250) compresses the whole board into
    # 286..3490 value units, where a 1539 gap is arithmetically almost
    # unreachable — it cannot measure this branch at all.
    top = rows[0][fmt_key]
    scale = 7737.0 / top
    for r in rows:
        pid = r["player_id"]
        players[pid] = P(id=pid, name=r["full_name"], position=r["position"],
                         team=r.get("team") or "FA", age=r.get("age") or 25)
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
    for t in range(1, teams):                          # team 0 is the viewer
        members.append(LeagueMember(
            user_id=f"u{t}", username=f"team{t}", roster=rosters[t],
            elo_ratings=board(f"u{t}", all_ids),
            has_rankings=(t % 2 == 1)))
    svc = TradeService(players=players)
    svc.add_league(League(league_id=f"L_{tag}", name=tag, platform="demo",
                          members=members))
    return {
        "svc": svc, "players": players, "seed_elo": seed_elo,
        "user_elo": board("u0", all_ids), "user_roster": rosters[0],
        "league_id": f"L_{tag}", "scoring_format": scoring_format,
    }


def live_flags(**over):
    cfg = json.load(open(os.path.join(ROOT, "config/features.json")))
    flags = {k: v for k, v in cfg.items() if isinstance(v, bool)}
    base = dict(ff.DEFAULT_FLAGS)
    base.update(flags)
    base.update(over)
    ff._flags_cache = base


def reset_cfg():
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)


def gen(L, **kw):
    return L["svc"].generate_trades(
        user_id="u0", user_elo=dict(L["user_elo"]),
        user_roster=L["user_roster"], league_id=L["league_id"],
        seed_elo=dict(L["seed_elo"]), fairness_threshold=0.85,
        max_per_opponent=5, scoring_format=L["scoring_format"], **kw)


def stats(cards):
    gaps = [abs((c.give_value or 0.0) - (c.receive_value or 0.0))
            for c in cards]
    over = [g for g in gaps if g > GAP_LINE]
    gaps_s = sorted(gaps)

    def pct(p):
        if not gaps_s:
            return None
        return round(gaps_s[min(len(gaps_s) - 1, int(p * len(gaps_s)))], 1)
    return {
        "cards": len(cards),
        "gap_over_line": len(over),
        "gap_over_share": round(len(over) / len(cards), 4) if cards else None,
        "gap_p50": pct(0.50), "gap_p90": pct(0.90),
        "gap_mean": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "sweetened": sum(1 for c in cards
                         if getattr(c, "gap_sweetener", None)),
    }


def main():
    leagues = [
        ("12t_1qb", dict(teams=12, roster_size=26, fmt_key="dp_value_1qb",
                         scoring_format="1qb_ppr", tag="12t")),
        ("16t_sf", dict(teams=16, roster_size=21, fmt_key="dp_value_2qb",
                        scoring_format="sf_tep", tag="16t")),
    ]
    from backend.bakeoff_profiles import model_a, model_challenger
    import backend.bakeoff_runner as bo

    out = []
    for lname, spec in leagues:
        for path, v3 in (("v2_only", False), ("v3", True)):
            reset_cfg()
            live_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3,
                          "trade.bakeoff": False})
            L = build_league(**spec)

            def rec(arm, cards):
                out.append({"league": lname, "path": path, "arm": arm,
                            **stats(cards)})

            reset_cfg()
            rec("B_current", gen(L))
            if "sweetener_gap_threshold" in ts._DEFAULT_CFG:
                reset_cfg()
                ts._cfg["sweetener_gap_threshold"] = 0.0
                rec("B_current_sweet_off", gen(L))
            reset_cfg()
            with model_a():
                rec("A_baseline", gen(L))
            reset_cfg()
            with model_challenger():
                rec("D_challenger", gen(L))
            if not v3:                      # arm C is path-independent
                reset_cfg()
                try:
                    rec("C_gen_v2", bo.gen_v2_cards(L["svc"], dict(
                        user_id="u0", user_elo=dict(L["user_elo"]),
                        user_roster=L["user_roster"],
                        league_id=L["league_id"],
                        seed_elo=dict(L["seed_elo"]),
                        fairness_threshold=0.85, max_per_opponent=5,
                        scoring_format=L["scoring_format"])))
                except Exception as e:      # noqa: BLE001
                    out.append({"league": lname, "path": path,
                                "arm": "C_gen_v2", "error": repr(e)[:200]})
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
