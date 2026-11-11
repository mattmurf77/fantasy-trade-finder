"""How often a revised-offer card is found (WS8). Reproducibility, not a test.

The same synthetic leagues as `measure_next_move.py` (the real-player fixture,
a seeded snake draft, noisy personal boards, seeded outlooks). For each league
and engine revision the viewer's deck is generated with that revision's own
generator and its first CARDS cards are treated as SENT offers that were:

  * declined   -> `propose_revision(..., kinds=(SWAP,))` at 5-15% (the card a
                  declined offer gets);
  * countered, and the counter declined -> `propose_middle_ground`, with a
                  synthetic counter that asks for one more asset from the
                  viewer's roster: the cheapest one worth at least COUNTER_ASK
                  of the trade (consensus), the shape the offer data shows
                  counters taking (about 20 points more).

Prints aggregates only.

    PYTHONHASHSEED=0 PYTHONPATH=. python docs/plans/offer-learnings/measure_revised_offers.py
"""
import os
import statistics
import sys
import time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import bakeoff_runner as bo, feature_flags as ff, trade_next_move as nm  # noqa: E402
from backend import trade_service as ts  # noqa: E402
from measure_next_move import ARMS, CARDS, LEAGUES, ROSTER, TEAMS, league, pool, with_evidence  # noqa: E402

COUNTER_ASK = .15


def counter_for(sent, args):
    value = ts.make_consensus_value_fn(args["seed_elo"], args["players"])
    trade = sum(value(p) for p in sent.receive_player_ids)
    pool_ = sorted((value(p), p) for p in args["user_roster"]
                   if p not in sent.give_player_ids and p in args["players"] and value(p) > 0)
    ask = next((p for v, p in pool_ if v >= COUNTER_ASK * trade), None)
    if ask is None:
        return None
    return ts.TradeCard("", sent.league_id, sent.proposing_user_id, sent.target_user_id,
                        sent.target_username, list(sent.give_player_ids) + [ask],
                        list(sent.receive_player_ids), 0, 0, 0)


def main():
    ts._cfg = dict(ts._DEFAULT_CFG)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, nm.FLAG: True}
    rows = pool()
    print(f"{LEAGUES} leagues x {TEAMS} teams x {ROSTER} players; first {CARDS} cards of each deck as sent offers")
    for arm, cfg in ARMS.items():
        rev, mid, offers, counters, steps, shares, secs_r, secs_m = 0, 0, 0, 0, [], [], [], []
        shapes, changes = Counter(), Counter()
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
                offers += 1
                start = time.perf_counter()
                move = nm.propose_revision(sent, args, step_min=nm.SWAP_STEP_MIN,
                                           step_max=nm.SWAP_STEP_MAX, kinds=(nm.SWAP,))
                secs_r.append(time.perf_counter() - start)
                if move:
                    rev += 1
                    steps.append(move.step_fraction)
                counter = counter_for(sent, args)
                if counter is None:
                    continue
                counters += 1
                start = time.perf_counter()
                mg = nm.propose_middle_ground(sent, counter, args)
                secs_m.append(time.perf_counter() - start)
                if mg:
                    mid += 1
                    shares.append(mg.change["gap_share"])
                    changes[f"+{len(mg.change['added_give'])}g-{len(mg.change['removed_give'])}g"
                            f"+{len(mg.change['added_receive'])}r-{len(mg.change['removed_receive'])}r"] += 1
        print(f"\n{arm} ({bo.owner_version(cfg)}): offer shapes {dict(shapes)}")
        print(f"  declined -> revision: {rev}/{offers} ({rev / offers:.0%})"
              + (f"; step median {statistics.median(steps):.1%}, range {min(steps):.1%}-{max(steps):.1%}"
                 if steps else ""))
        print(f"  declined counter -> middle ground: {mid}/{counters} ({(mid / counters if counters else 0):.0%})"
              + (f"; gap share median {statistics.median(shares):.0%}; changes {dict(changes)}" if shares else ""))
        if secs_r:
            print(f"  time: revision median {statistics.median(secs_r) * 1000:.0f} ms (max {max(secs_r) * 1000:.0f}),"
                  f" middle ground median {statistics.median(secs_m) * 1000 if secs_m else 0:.0f} ms"
                  f" (max {max(secs_m) * 1000 if secs_m else 0:.0f})")


if __name__ == "__main__":
    main()
