"""#214 deck sanity diff — operator's real league (Lakeview, sf_tep),
deck generated under stud-tax modes heavy (pre-#214) vs market (retuned)
vs off, same inputs otherwise. Read-only against the worktree DB copy.

Replicates the /api/trades/generate job's essentials: universal-pool
players + seed, roster/opponent data from the leagues row, the caller's
member_rankings as their board, opponents at consensus seed
(has_rankings=False -> consensus-basis cards, the production common case).

Run from the worktree root:  python3 feedback-workspace/214/deck_diff.py
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.server as srv
import backend.trade_service as ts
from backend.database import engine, leagues_table, member_rankings_table
from sqlalchemy import select

LEAGUE_ID = "1312076055586050048"
# The operator's saved board for this league is 1qb_ppr (503 member_rankings
# rows) — use that format so the diff exercises a real divergent user board.
FMT = "1qb_ppr"

with engine.connect() as conn:
    row = conn.execute(select(leagues_table).where(
        leagues_table.c.sleeper_league_id == LEAGUE_ID)).fetchone()
    USER_ID = row.user_id
    roster = [str(x) for x in json.loads(row.roster_data or "[]")]
    opponents = json.loads(row.opponent_data or "[]")
    mr = conn.execute(select(member_rankings_table).where(
        (member_rankings_table.c.league_id == LEAGUE_ID)
        & (member_rankings_table.c.user_id == USER_ID)
        & ((member_rankings_table.c.scoring_format == FMT)
           | (member_rankings_table.c.scoring_format.is_(None))))).fetchall()

pool, seed = srv._get_universal_pool(FMT)
players_dict = {p.id: p for p in pool}
user_roster = [p for p in roster if p in players_dict]
user_elo = {pid: seed.get(pid, 1500.0) for pid in seed}
n_overrides = 0
for r in mr:
    pid = str(r.player_id)
    if r.elo is not None and pid in seed:
        user_elo[pid] = float(r.elo)
        n_overrides += 1

members = []
for opp in opponents:
    opp_ids = [str(x) for x in opp.get("player_ids", []) if str(x) in players_dict]
    if not opp_ids:
        continue
    members.append(ts.LeagueMember(
        user_id=str(opp["user_id"]), username=opp.get("username", "?"),
        roster=opp_ids,
        elo_ratings={pid: seed.get(pid, 1500.0) for pid in opp_ids},
    ))

print(f"league={LEAGUE_ID} fmt={FMT} user={USER_ID} roster={len(user_roster)} "
      f"opponents={len(members)} user board overrides={n_overrides}")


def build_deck(mode, max_per_opponent=5):
    svc = ts.TradeService(players=players_dict)
    svc.add_league(ts.League(league_id=LEAGUE_ID, name="Lakeview",
                             platform="sleeper", members=members))
    with ts.stud_tax_override(mode):        # pinned mode wins over DB setting
        cards = svc.generate_trades(
            user_id=USER_ID, user_elo=dict(user_elo), user_roster=user_roster,
            league_id=LEAGUE_ID, seed_elo=dict(seed), scoring_format=FMT,
            max_per_opponent=max_per_opponent,
        )
    return cards


def describe(cards, label):
    shapes = Counter(f"{len(c.give_player_ids)}for{len(c.receive_player_ids)}"
                     for c in cards)
    uneven = [c for c in cards
              if len(c.give_player_ids) != len(c.receive_player_ids)]
    stud_recv = [c for c in uneven
                 if len(c.receive_player_ids) < len(c.give_player_ids)]
    stud_give = [c for c in uneven
                 if len(c.give_player_ids) < len(c.receive_player_ids)]
    fair = [c.fairness_score for c in cards if c.fairness_score is not None]
    print(f"\n[{label}] cards={len(cards)} shapes={dict(shapes)}")
    print(f"  uneven-count cards={len(uneven)} "
          f"(user consolidates / receives the stud side: {len(stud_recv)}; "
          f"user splits / sends the stud side: {len(stud_give)})")
    if fair:
        print(f"  fairness min/median/max = {min(fair):.3f}/"
              f"{sorted(fair)[len(fair)//2]:.3f}/{max(fair):.3f}")
    keys = {(frozenset(c.give_player_ids), frozenset(c.receive_player_ids),
             c.target_user_id) for c in cards}
    return keys


k_heavy = describe(build_deck("heavy"), "heavy (pre-#214)")
k_market = describe(build_deck("market"), "market (retuned default)")
k_off = describe(build_deck("off"), "off")
print(f"\noverlap heavy∩market={len(k_heavy & k_market)} "
      f"market-only={len(k_market - k_heavy)} heavy-only={len(k_heavy - k_market)}")
print(f"overlap market∩off={len(k_market & k_off)}")

# Widened per-opponent cap (30): 1-for-1s no longer crowd out the 2-for-1
# enumeration, so this directly probes whether 'market' floods the deck
# with stud-for-package consolidations once packages are reachable.
print("\n--- widened cap (max_per_opponent=30) — package-shape probe ---")
describe(build_deck("heavy", 30), "heavy, cap 30")
describe(build_deck("market", 30), "market, cap 30")
describe(build_deck("off", 30), "off, cap 30")

# Direct consolidation probe: pin the user's #2+#3 assets as a package
# ('all' mode → every card must send BOTH), so the deck can ONLY offer
# 2-for-1 consolidations. This is the exact "stud-for-package" shape the
# fairness + consolidation_raw_loss_frac gates must keep binding on.
by_val = sorted(user_roster, key=lambda p: seed.get(p, 0.0), reverse=True)
pin2 = by_val[1:3]
print(f"\n--- pinned 2-piece give package probe: "
      f"{[players_dict[p].name for p in pin2]} ---")


def build_pinned(mode):
    svc = ts.TradeService(players=players_dict)
    svc.add_league(ts.League(league_id=LEAGUE_ID, name="Lakeview",
                             platform="sleeper", members=members))
    with ts.stud_tax_override(mode):
        return svc.generate_trades(
            user_id=USER_ID, user_elo=dict(user_elo), user_roster=user_roster,
            league_id=LEAGUE_ID, seed_elo=dict(seed), scoring_format=FMT,
            max_per_opponent=30,
            pinned_give_players=list(pin2), pinned_give_mode="all",
        )


for mode in ("heavy", "market", "off"):
    describe(build_pinned(mode), f"pinned 2-for-1, {mode}")
