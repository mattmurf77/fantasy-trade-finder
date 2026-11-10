"""Deterministic synthetic league for owner/bilateral generator benchmarks.

Operator and test tooling only: no server, database, provider or network
access, and no production data. ``build`` returns the keyword arguments the
owner-family generators accept (``generate_bilateral_trades(**build())``).

The shape is a production-sized cold search: 12 teams of 20 players and four
picks, the viewer and a few league-mates with personal boards, the rest
unranked. With the default pool of 16 that is 4,096 small-shape candidates per
opponent, the same per-pair budget the live constructor explores.
"""

import random

from .. import trade_service as ts
from ..ranking_service import Player

_POSITIONS = ["QB"] * 3 + ["RB"] * 6 + ["WR"] * 8 + ["TE"] * 3
_PICK_VALUES = [2600, 1100, 450, 180]
_OUTLOOKS = ["contender", "rebuilder", "not_sure", "championship", "jets"]


def build(seed=7, teams=12, ranked_opponents=4, players_per_team=20,
          picks_per_team=4, fairness_threshold=.75, viewer_outlook="contender"):
    rng = random.Random(seed)
    players, values, rosters = {}, {}, {}
    for team in range(teams):
        uid = "me" if team == 0 else f"u{team:02d}"
        roster = []
        for index in range(players_per_team):
            pid = f"p{team:02d}_{index:02d}"
            players[pid] = Player(pid, pid, _POSITIONS[index % len(_POSITIONS)],
                                  "TST", rng.randint(21, 32))
            values[pid] = min(9500, max(60, int(rng.lognormvariate(6.6, .9))))
            roster.append(pid)
        for index in range(picks_per_team):
            pid = f"k{team:02d}_{index}"
            players[pid] = Player(pid, pid, "PICK", "PICK", None)
            values[pid] = _PICK_VALUES[index % len(_PICK_VALUES)] + rng.randint(-80, 80)
            roster.append(pid)
        rosters[uid] = roster

    def board(noise):
        return {pid: ts.value_to_elo(max(30, value * rng.lognormvariate(0, noise)))
                for pid, value in values.items()}

    members, opponent_outlooks = [], {}
    for team in range(1, teams):
        uid = f"u{team:02d}"
        ranked = team <= ranked_opponents
        members.append(ts.LeagueMember(uid, uid, rosters[uid],
                                       board(.25) if ranked else {}, ranked))
        opponent_outlooks[uid] = _OUTLOOKS[team % len(_OUTLOOKS)]
    return dict(players=players, league=ts.League("L", "Synthetic", "sleeper", members),
                user_id="me", user_roster=rosters["me"],
                seed_elo={pid: ts.value_to_elo(value) for pid, value in values.items()},
                user_elo=board(.3), outlook=viewer_outlook,
                opponent_outlooks=opponent_outlooks,
                fairness_threshold=fairness_threshold)
