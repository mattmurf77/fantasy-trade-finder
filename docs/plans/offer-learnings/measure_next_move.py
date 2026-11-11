"""How often the next-move generator finds a revision (WS5). Reproducibility, not a test.

Builds synthetic 12-team leagues from the real-player fixture
(`backend/tests/fixtures/player_pool_2026.json`, 340 players with
DynastyProcess 1QB values): a seeded snake draft with noise, personal boards
that are the market times seeded noise, and seeded outlooks. For each league
and engine revision it generates the viewer's deck with that revision's own
generator, treats the first CARDS cards as sent offers, and asks
`trade_next_move.propose_revision` for each. Prints aggregates only.

    PYTHONHASHSEED=0 PYTHONPATH=. python docs/plans/offer-learnings/measure_next_move.py
"""
import json
import os
import random
import statistics
import sys
import time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, ROOT)

from backend import bakeoff_runner as bo, feature_flags as ff, trade_next_move as nm  # noqa: E402
from backend import trade_service as ts  # noqa: E402
from backend.ranking_service import Player  # noqa: E402
from backend.trade_input_evidence import PoolInputEvidence, detached_context, request_evidence  # noqa: E402

LEAGUES = 8
TEAMS = 12
ROSTER = 22
CARDS = 10
OUTLOOKS = ("contender", "championship", "not_sure", "rebuilder", "jets")
ARMS = {
    "owner-v1": {},
    "bilateral-1": {"owner_bilateral_enabled": 1.},
    "bilateral-2": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.},
    "bilateral-3": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
                    "owner_outlook_evidence_enabled": 1.},
}


def pool():
    rows = json.load(open(os.path.join(ROOT, "backend/tests/fixtures/player_pool_2026.json")))["players"]
    return [r for r in rows.values() if (r.get("dp_value_1qb") or 0) > 0]


def league(seed, rows):
    rng = random.Random(seed)
    order = sorted(rows, key=lambda r: -r["dp_value_1qb"] * rng.lognormvariate(0, .35))
    teams = [[] for _ in range(TEAMS)]
    for i, r in enumerate(order[:TEAMS * ROSTER]):
        rnd, pos = divmod(i, TEAMS)
        teams[pos if rnd % 2 == 0 else TEAMS - 1 - pos].append(r["player_id"])
    players = {r["player_id"]: Player(r["player_id"], r["full_name"], r["position"], r["team"] or "FA",
                                      r["age"] or 26) for r in rows}
    market = {r["player_id"]: float(r["dp_value_1qb"]) for r in rows}
    seed_elo = {pid: ts.value_to_elo(v) for pid, v in market.items()}

    def board():
        return {pid: ts.value_to_elo(v * rng.lognormvariate(0, .25)) for pid, v in market.items()}

    members = []
    for t in range(1, TEAMS):
        ranked = rng.random() < .6
        elo = board() if ranked else {}
        members.append(ts.LeagueMember(f"m{t}", f"M{t}", teams[t], elo, ranked,
                                       confidence_sources=dict.fromkeys(elo, "explicit")))
    user_elo = board()
    return dict(players=players, league=ts.League(f"L{seed}", "Synthetic", "sleeper", members),
                user_id="viewer", user_roster=teams[0], seed_elo=seed_elo, user_elo=user_elo,
                user_sources=dict.fromkeys(user_elo, "explicit"),
                opponent_sources={m.user_id: dict(m.confidence_sources) for m in members},
                outlook=rng.choice(OUTLOOKS),
                opponent_outlooks={m.user_id: rng.choice(OUTLOOKS) for m in members},
                fairness_threshold=.75, scoring_format="1qb_ppr")


def with_evidence(args):
    collector = PoolInputEvidence()
    for player in args["players"].values():
        collector.record(player, raw={"age": player.age})
    args = detached_context(args, collector)
    args["input_evidence"] = request_evidence(args)
    from backend.trade_gen_outlook_evidence import INPUT_VERSION
    args["input_evidence"].update(schema_version=INPUT_VERSION, used_in_model=True)
    return args


def main():
    ts._cfg = dict(ts._DEFAULT_CFG)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, nm.FLAG: True}
    rows = pool()
    print(f"{LEAGUES} leagues x {TEAMS} teams x {ROSTER} players; first {CARDS} cards of each deck as sent offers")
    for arm, cfg in ARMS.items():
        found, offers, kinds, steps, shapes, secs = 0, 0, Counter(), [], Counter(), []
        for seed in range(LEAGUES):
            args = league(seed, rows)
            args["config"] = dict(cfg)
            if arm == "bilateral-3":
                args = with_evidence(args)
            cards, _ = bo.owner_generator(cfg)(**args)
            for card in cards[:CARDS]:
                sent = ts.TradeCard("", card.league_id, card.proposing_user_id, card.target_user_id,
                                    card.target_username, list(card.give_player_ids),
                                    list(card.receive_player_ids), 0, 0, 0)
                shapes[f"{len(sent.give_player_ids)}x{len(sent.receive_player_ids)}"] += 1
                start = time.perf_counter()
                move = nm.propose_revision(sent, args)
                secs.append(time.perf_counter() - start)
                offers += 1
                if move:
                    found += 1
                    kinds[move.change["kind"]] += 1
                    steps.append(move.step_fraction)
        share = found / offers if offers else 0
        print(f"\n{arm} ({bo.owner_version(cfg)}): {found}/{offers} sent offers get a revision ({share:.0%})")
        print(f"  offer shapes: {dict(shapes)}   revision kinds: {dict(kinds)}")
        if steps:
            print(f"  step: median {statistics.median(steps):.1%}, range {min(steps):.1%}-{max(steps):.1%}")
        if secs:
            print(f"  time per offer: median {statistics.median(secs) * 1000:.0f} ms, max {max(secs) * 1000:.0f} ms")


if __name__ == "__main__":
    main()
