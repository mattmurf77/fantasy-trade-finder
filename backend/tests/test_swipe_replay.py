"""BL-001 — backend/eval/swipe_replay.py, the offline replay of frozen swipes.

Synthetic SQLite only (no production data): one board with trio votes, a
pre-freeze trade swipe, a match disposition and frozen-period trade likes and
passes; a second board below --min-swipes. Covers: (A) reproduces the stored
board, (B) moves it, the metric on a hand-built case, like/pass recovery,
the read-only guard, and that the module never imports backend.server.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.pool import StaticPool

from backend import database as db
from backend.eval import swipe_replay as sr
from backend.ranking_service import RankingService

REPO = Path(__file__).resolve().parents[2]
UTC = timezone.utc
SINCE = datetime(2026, 8, 19, tzinfo=UTC)
UNTIL = datetime(2026, 9, 16, tzinfo=UTC)
FMT = "1qb_ppr"
ME, OTHER = "user_bl001", "user_few"

SEEDS = {"q1": ("QB", 1700.0), "q2": ("QB", 1690.0), "q3": ("QB", 1680.0),
         "w1": ("WR", 1500.0), "w2": ("WR", 1495.0), "w3": ("WR", 1578.0),
         "w4": ("WR", 1450.0), "w5": ("WR", 1440.0), "w6": ("WR", 1430.0),
         "r1": ("RB", 1600.0), "t1": ("TE", 1400.0)}

LIKE_W2_OVER_W1 = (["w1"], ["w2"])     # give, receive
LIKE_W3_OVER_W6 = (["w6"], ["w3"])
PASS_KEEP_W4 = (["w4"], ["w5"])


def _iso(dt):
    return dt.isoformat()


def _seed(engine):
    """Write the synthetic world. Returns the frozen events written."""
    db.metadata.create_all(engine)
    swipes, decisions, frozen = [], [], []

    def swipe(user, win, lose, k, at, dtype="trade"):
        swipes.append({"user_id": user, "winner_player_id": win,
                       "loser_player_id": lose, "decision_type": dtype,
                       "k_factor": k, "created_at": _iso(at), "scoring_format": FMT})

    def card(user, kind, give, recv, at, record=True):
        if record:
            decisions.append({"user_id": user, "league_id": "lg", "trade_id": f"t{len(decisions)}",
                              "give_player_ids": json.dumps(give),
                              "receive_player_ids": json.dumps(recv), "decision": kind,
                              "created_at": _iso(at - timedelta(milliseconds=200))})
        win, lose = (recv, give) if kind == "like" else (give, recv)
        for w in win:
            for l in lose:
                swipe(user, w, l, 0.0, at)
        frozen.append((user, kind if record else None, at))

    # History before the window: trio votes and one unfrozen trade swipe.
    for a, b in (("q1", "q2"), ("q1", "q3"), ("q2", "q3")):
        swipe(ME, a, b, 32.0, datetime(2026, 8, 10, tzinfo=UTC), "rank")
    swipe(ME, "w5", "w6", 8.0, datetime(2026, 8, 1, tzinfo=UTC))
    # In the window: trio votes and a disposition keep their stored K.
    for a, b in (("q3", "q2"), ("q3", "q1"), ("q2", "q1")):
        swipe(ME, a, b, 32.0, datetime(2026, 8, 25, tzinfo=UTC), "rank")
    swipe(ME, "q1", "q3", 20.0, datetime(2026, 8, 22, tzinfo=UTC), "disposition")
    # Frozen trade swipes, one week at a time.
    for week in range(4):
        base = SINCE + timedelta(days=7 * week, hours=12)
        card(ME, "like", *LIKE_W2_OVER_W1, base)
        card(ME, "like", *LIKE_W3_OVER_W6, base + timedelta(hours=1))
        card(ME, "pass", *PASS_KEEP_W4, base + timedelta(hours=2))
    card(ME, "like", ["t1"], ["r1"], SINCE + timedelta(days=2), record=False)
    for i in range(3):
        card(OTHER, "like", *LIKE_W2_OVER_W1, SINCE + timedelta(days=1, hours=i))

    with engine.begin() as conn:
        conn.execute(insert(db.swipe_decisions_table), swipes)
        conn.execute(insert(db.trade_decisions_table), decisions)
        conn.execute(insert(db.players_table), [
            {"player_id": pid, "full_name": pid, "position": pos, "team": "T", "age": 25}
            for pid, (pos, _e) in SEEDS.items()])
        conn.execute(insert(db.player_value_history_table), [
            {"player_id": pid, "scoring_format": FMT, "consensus_elo": elo,
             "snapshot_date": "2026-08-01"} for pid, (_p, elo) in SEEDS.items()]
            + [{"player_id": "generic_pick_1_early", "scoring_format": FMT,
                "consensus_elo": 1800.0, "snapshot_date": "2026-08-01"}])
        conn.execute(insert(db.model_config_table), [
            {"key": "trade_k_like", "value": 8.0}, {"key": "trade_k_pass", "value": 4.0}])
    return frozen


@pytest.fixture()
def world():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    frozen = _seed(engine)
    sr._install_readonly_guard(engine)     # run() must never need a write
    return engine, frozen


def _stored_rows(engine, user=ME):
    with engine.connect() as conn:
        return sr.load_board_rows(conn, user, FMT)


def _pool(engine):
    with engine.connect() as conn:
        return sr.load_pool(conn, FMT, "2026-09-16")


def test_a_reproduces_the_stored_board_and_b_equals_a_before_the_window(world):
    engine, _ = world
    report = sr.run(engine, SINCE, UNTIL)
    check = report["check_5b_i"]
    assert check == {"boards": 1, "a_equals_restore_at_k0": 1,
                     "b_equals_a_at_since": 1, "pass": True}

    # Independently: prod's own rebuild (replay every stored row as-is).
    players, seed, snap = _pool(engine)
    # The rung's snapshot row (1800) is ignored: live seeds rungs from
    # GENERIC_PICK_SEEDS, so the replay does too.
    assert snap == "2026-08-01" and seed["generic_pick_1_early"] == 1720.0
    svc = RankingService(players=players, seed_ratings=seed)
    svc._scoring_format = FMT
    svc.replay_from_db(_stored_rows(engine))
    expected = {rp.player.id: rp.elo for rp in svc.get_rankings(None).rankings}
    board_a = sr.build_board(players, seed, FMT, _stored_rows(engine))
    assert {pid: v[0] for pid, v in board_a.items()} == expected
    # Frozen rows are inert in (A): the WRs the swipes touched sit at seed,
    # except w5/w6, which the pre-freeze K=8 swipe moved.
    for pid in ("w1", "w2", "w3", "w4"):
        assert board_a[pid][0] == SEEDS[pid][1]
    assert board_a["w5"][0] > SEEDS["w5"][1]


def test_b_moves_the_board_within_tiers_only(world):
    engine, _ = world
    players, seed, _ = _pool(engine)
    rows = _stored_rows(engine)
    with engine.connect() as conn:
        kinds = sr.classify_events(sr.load_frozen_events(conn, SINCE, UNTIL)[(ME, FMT)],
                                   [dict(r._mapping) for r in conn.execute(text(
                                       "SELECT created_at, decision, give_player_ids, "
                                       "receive_player_ids FROM trade_decisions "
                                       "WHERE user_id = :u"), {"u": ME})])
    a = sr.build_board(players, seed, FMT, rows)
    b = sr.build_board(players, seed, FMT,
                       sr.restore_rows(rows, SINCE, UNTIL, kinds, 8.0, 4.0, 1.0))
    assert b["w2"][2] < b["w1"][2] and a["w1"][2] < a["w2"][2], "liked w2 overtakes w1"
    assert b["w6"][0] < a["w6"][0] and b["w4"][0] > a["w4"][0]
    # The within-tier contract: w3 sits at 1578, in the gap just under
    # first_1 (1580). Four likes push him up and he doesn't move at all.
    assert b["w3"][0] == a["w3"][0] == 1578.0
    assert {pid: v[3] for pid, v in b.items()} == {pid: v[3] for pid, v in a.items()}

    report = sr.run(engine, SINCE, UNTIL)
    full, half = report["results"]["1.0"], report["results"]["0.5"]
    assert full["board_weeks_active"] == 4 and half["board_weeks_active"] == 4
    # Groups, with the generic rungs in their live tabs: WR `second` holds six
    # WRs + the three 2nds (36 pairs); RB `first_1` r1 + the three 1sts (6);
    # QB `first_1` three QBs (3) and QB `fourth` the three 4ths (3); TE
    # `third` the three 3rds (3); t1 is a singleton. 51 pairs. Week 1's like
    # flips w1/w2: 1 of 51, one place in a group of nine (12.5 points).
    weeks = report["boards"][0]["k_scale_1.0"]
    assert [(w["discordant_pairs"], w["same_tier_pairs"]) for w in weeks] == \
        [(1, 51), (0, 51), (0, 51), (0, 51)]
    assert full["kendall"] == {"median": 0.0, "p95": 1 / 51, "max": 1 / 51}
    assert full["max_pct_move"]["max"] == pytest.approx(12.5)
    assert full["pick_order"]["preexisting_inversions"] == 0
    assert full["pick_order"]["introduced_inversions"] == 0
    assert full["pick_order"]["verdict"] == "PASS"
    assert full["check_5b_ii"] == {"tier_membership_violations": 0, "verdict": "PASS"}
    assert full["bar_5a_i"] == full["bar_5a_ii"] == "PASS"
    assert half["bar_5a_i"] == half["bar_5a_ii"] == "PASS"
    assert full["kill_rule"]["would_have_fired"] is False
    assert report["ship_rule"] == "ship at full K"
    assert any("fit_mult = 1" in c for c in report["caveats"])
    assert any("unmatched" in c for c in report["caveats"])


def test_week_rows_isolate_one_weeks_trade_swipes(world):
    """WITH and WITHOUT share every row up to the week's end; they differ
    only in that week's trade swipes, whose K is restored vs 0. Earlier
    weeks' swipes are restored in both, and trio votes are in both."""
    engine, frozen = world
    rows = _stored_rows(engine)
    kinds = {_iso(at): kind for user, kind, at in frozen if user == ME}
    start, end = SINCE + timedelta(days=7), SINCE + timedelta(days=14)
    with_rows, without, swipes = sr.week_rows(rows, SINCE, start, end, kinds,
                                              8.0, 4.0, 1.0)
    assert swipes == 3 and len(with_rows) == len(without)
    for w, wo in zip(with_rows, without):
        ts = sr._ts(w["created_at"])
        assert w["id"] == wo["id"]
        if w["decision_type"] == "trade" and start <= ts < end:
            assert w["k_factor"] > 0 and wo["k_factor"] == 0.0
        else:
            assert w == wo
            if w["decision_type"] == "trade" and SINCE <= ts < start:
                assert w["k_factor"] > 0, "earlier weeks carry restored K"
    assert all(sr._ts(r["created_at"]) < end for r in with_rows)


def test_like_pass_recovery_and_restored_k(world):
    engine, frozen = world
    report = sr.run(engine, SINCE, UNTIL)
    c = report["counts"]
    assert c["boards_with_frozen_swipes"] == 2
    assert c["boards_below_min_swipes"] == 1          # OTHER: 3 swipes
    assert c["boards_included"] == 1
    assert (c["frozen_swipes"], c["frozen_swipes_like"], c["frozen_swipes_pass"],
            c["frozen_swipes_unmatched"]) == (13, 8, 4, 1)
    assert report["k"]["trade_k_like"] == 8.0 and report["k"]["trade_k_pass"] == 4.0

    rows = _stored_rows(engine)
    kinds = {_iso(at): kind for user, kind, at in frozen if user == ME}
    for scale, like_k, pass_k in ((1.0, 8.0, 4.0), (0.5, 4.0, 2.0)):
        out = sr.restore_rows(rows, SINCE, UNTIL, kinds, 8.0, 4.0, scale)
        for before, after in zip(rows, out):
            if not sr.is_frozen_trade(before, SINCE, UNTIL):
                assert after == before                 # trio, disposition, pre-freeze
                continue
            kind = kinds[before["created_at"]]
            assert after["k_factor"] == (pass_k if kind == "pass" else like_k)


def _hand_board(**players):
    """pid -> (position, positional rank, tier), as build_board shapes it."""
    return {pid: (0.0, pos, rank, tier) for pid, (pos, rank, tier) in players.items()}


def test_kendall_on_a_hand_built_case():
    without = _hand_board(
        a=("WR", 1, "second"), b=("WR", 2, "second"), c=("WR", 3, "second"),
        d=("WR", 4, "second"), x=("QB", 1, "first_1"), y=("QB", 2, "first_1"),
        z=("RB", 1, "second"), u1=("TE", 1, None), u2=("TE", 2, None))
    with_ = _hand_board(
        b=("WR", 1, "second"), a=("WR", 2, "second"), d=("WR", 3, "second"),
        c=("WR", 4, "second"), x=("QB", 1, "first_1"), y=("QB", 2, "first_1"),
        z=("RB", 1, "second"), u2=("TE", 1, None), u1=("TE", 2, None))
    # WR group: a/b and c/d flip (2 of 6 pairs); QB pair holds (0 of 1); the
    # RB singleton has no pairs; the unranked TEs are not a tier and don't count.
    discordant, pairs, move = sr.within_tier_moves(with_, without)
    assert (discordant, pairs) == (2, 7)
    assert move == pytest.approx(100 / 3)            # one place in a group of 4


def test_percentile_move_on_a_hand_built_case():
    without = _hand_board(**{p: ("WR", i + 1, "second") for i, p in enumerate("ebcdf")})
    with_ = _hand_board(**{p: ("WR", i + 1, "second") for i, p in enumerate("bcdfe")})
    discordant, pairs, move = sr.within_tier_moves(with_, without)
    assert move == 100.0                             # e: top of 5 -> bottom
    assert (discordant, pairs) == (4, 10)
    assert sr.within_tier_moves(without, without) == (0, 10, 0.0)


def _kill_week(kendalls, moves_n4, introduced=None):
    introduced = introduced or [0] * len(kendalls)
    return [{"week_start": "w", "board": f"b{i}", "kendall": k,
             "max_pct_move_n4": m, "pick_inversions_introduced": d}
            for i, (k, m, d) in enumerate(zip(kendalls, moves_n4, introduced))]


def test_kill_rule_thresholds():
    calm = sr.kill_indicators(_kill_week([0.0] * 19 + [0.3], [0.0] * 20))
    assert calm["weeks"][0]["p95_kendall"] == 0.0     # nearest rank: 19th of 20
    assert calm["would_have_fired"] is False and calm["status"] == "OK"
    edge = sr.kill_indicators(_kill_week([0.25] * 20, [74.9] * 20))
    w = edge["weeks"][0]
    assert (w["fires_a"], w["fires_b"], w["alert_b"], w["status"]) == (False, False, False, "OK")
    a = sr.kill_indicators(_kill_week([0.0] * 18 + [0.26, 0.26], [0.0] * 20))
    assert a["weeks"][0]["fires_a"] is True and a["status"] == "KILL"


def test_revised_kill_b_one_board_is_an_alert_two_boards_kill():
    one = sr.kill_indicators(_kill_week([0.0] * 3, [75.0, 0.0, 0.0])).get("weeks")[0]
    assert (one["boards_ge75_n4"], one["fires_b"], one["alert_b"], one["status"]) == \
        (1, False, True, "ALERT")
    assert one["boards_ge75_n4_hashes"] == ["b0"] and one["share_ge75_n4"] == 1 / 3
    two = sr.kill_indicators(_kill_week([0.0] * 40, [75.0, 80.0] + [0.0] * 38))
    w = two["weeks"][0]
    assert (w["boards_ge75_n4"], w["share_ge75_n4"]) == (2, 0.05)
    assert (w["fires_b"], w["alert_b"], w["status"]) == (True, False, "KILL")
    thin = sr.kill_indicators(_kill_week([0.0] * 41, [75.0, 80.0] + [0.0] * 39))
    w = thin["weeks"][0]                       # 2 boards but under 5%: alert only
    assert (w["fires_b"], w["alert_b"], w["status"]) == (False, True, "ALERT")


def test_kill_b_ignores_groups_smaller_than_four():
    # A WR group of 3: the top player drops to the bottom (a 100-point move
    # for 5a-ii), but kill (b) only counts groups of n >= 4.
    without = _hand_board(a=("WR", 1, "second"), b=("WR", 2, "second"),
                          c=("WR", 3, "second"))
    with_ = _hand_board(b=("WR", 1, "second"), c=("WR", 2, "second"),
                        a=("WR", 3, "second"))
    assert sr.within_tier_moves(with_, without)[2] == 100.0
    assert sr.kill_b_move(with_, without) == 0.0
    # The same slide in a group of four counts.
    without4 = {**without, "d": (0.0, "WR", 4, "second")}
    with4 = _hand_board(b=("WR", 1, "second"), c=("WR", 2, "second"),
                        d=("WR", 3, "second"), a=("WR", 4, "second"))
    assert sr.kill_b_move(with4, without4) == 100.0


def test_kill_d_fires_on_any_introduced_pick_inversion():
    w = sr.kill_indicators(_kill_week([0.0] * 3, [0.0] * 3, [0, 1, 0]))["weeks"][0]
    assert (w["fires_d"], w["introduced_pick_inversions"], w["status"]) == (True, 1, "KILL")


def test_tier_violation_counter():
    without = _hand_board(a=("WR", 1, "second"), b=("WR", 2, "second"),
                          u=("TE", 1, None))
    assert sr.tier_violations(without, without) == 0
    moved = _hand_board(a=("WR", 1, "first_1"), b=("WR", 2, "second"),
                        u=("TE", 1, "waivers"))
    assert sr.tier_violations(moved, without) == 2   # a promoted, u became ranked
    weeks = [{"trade_swipes": 1, "kendall": 0.0, "max_pct_move": 0.0,
              "tier_violations": v, "week_start": "w", **NO_PICK_INVERSIONS}
             for v in (0, 2)]
    assert sr.summarize(weeks)["check_5b_ii"] == {
        "tier_membership_violations": 2, "verdict": "FAIL"}


NO_PICK_INVERSIONS = {"pick_inversions_without": 0, "pick_inversions_introduced": 0,
                      "board": "b", "max_pct_move_n4": 0.0}


def test_bars_and_ship_rule():
    def weeks(kendalls, moves, introduced=0):
        return [{"trade_swipes": 1, "kendall": k, "max_pct_move": m,
                 "tier_violations": 0, "week_start": "w", "board": f"b{i}",
                 "max_pct_move_n4": 0.0,
                 "pick_inversions_without": 0, "pick_inversions_introduced": introduced}
                for i, (k, m) in enumerate(zip(kendalls, moves))]

    ok = sr.summarize(weeks([0.0, 0.05, 0.15], [0.0, 10.0, 50.0]))
    assert ok["bar_5a_i"] == ok["bar_5a_ii"] == "PASS"
    assert sr.summarize(weeks([0.0, 0.06, 0.06], [0.0] * 3))["bar_5a_i"] == "FAIL"
    assert sr.summarize(weeks([0.0, 0.0, 0.16], [0.0] * 3))["bar_5a_i"] == "FAIL"
    bad = sr.summarize(weeks([0.0] * 3, [0.0, 0.0, 51.0]))
    assert bad["bar_5a_ii"] == "FAIL"
    inactive = sr.summarize([{"trade_swipes": 0, "kendall": None, "max_pct_move": 0.0,
                              "tier_violations": 0, "week_start": "w",
                              **NO_PICK_INVERSIONS}])
    assert inactive["bar_5a_i"] == "NO DATA" and inactive["board_weeks_inactive"] == 1
    assert sr.ship_rule({"1.0": ok, "0.5": ok}, True) == "ship at full K"
    assert sr.ship_rule({"1.0": bad, "0.5": ok}, True) == "ship at half K (4/2)"
    assert sr.ship_rule({"1.0": bad, "0.5": bad}, True).startswith("hold")
    assert sr.ship_rule({"1.0": ok, "0.5": ok}, False).startswith("hold")
    # A2: an introduced pick inversion fails the ship rule even when every
    # other bar passes.
    flipped = sr.summarize(weeks([0.0] * 3, [0.0] * 3, introduced=1))
    assert flipped["bar_5a_i"] == flipped["bar_5a_ii"] == "PASS"
    assert flipped["pick_order"]["verdict"] == "FAIL"
    assert sr.ship_rule({"1.0": flipped, "0.5": ok}, True) == "ship at half K (4/2)"
    assert sr.ship_rule({"1.0": flipped, "0.5": flipped}, True).startswith("hold")
    assert sr.p95([0, 0, 1, 1, 2]) == 2


# ---------------------------------------------------------------------------
# A2: the pool mirrors the live ranking pool; picks are classified; pick order
# ---------------------------------------------------------------------------

def test_pool_mirrors_the_live_ranking_pool(world):
    """The 12 generic rungs are in, seeded from GENERIC_PICK_SEEDS, in the
    live builder's tabs. The tab map is pinned to server.py's `_PICK_POS`
    literal by reading the source (the module must not import server)."""
    import ast
    from backend.pick_values import GENERIC_PICK_SEEDS, parse_generic_pick_id

    engine, _ = world
    players, seed, _ = _pool(engine)
    rungs = {p.id: p for p in players if p.id.startswith("generic_pick_")}
    assert len(rungs) == 12 and list(rungs) == sr.GENERIC_LADDER
    for pid, p in rungs.items():
        rnd, tier = parse_generic_pick_id(pid)
        assert seed[pid] == GENERIC_PICK_SEEDS[(rnd, tier)]
        assert p.position == sr.GENERIC_PICK_TABS[rnd] and p.team == "PICK"

    tree = ast.parse((REPO / "backend" / "server.py").read_text())
    live = [ast.literal_eval(n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", None) == "_PICK_POS" for t in n.targets)]
    assert live == [sr.GENERIC_PICK_TABS]


def test_pick_rows_are_classified_by_id_form(world):
    engine, _ = world
    pool = {p.id for p in _pool(engine)[0]}

    def kind(w, l):
        return sr.pair_kind({"winner_player_id": w, "loser_player_id": l}, pool)

    assert kind("w1", "w2") == "applied"
    assert kind("generic_pick_2_mid", "w4") == "generic_pick_applied"
    assert kind("w6", "lg1_2027_1_3") == "skipped_league_pick"
    assert kind("espn_77_2028_2_0004", "w1") == "skipped_league_pick"
    assert kind("w5", "9999") == "skipped_other"
    assert kind("generic_pick_9_early", "w1") == "skipped_other"   # not a real rung

    # And through run(): a third board whose frozen swipes mix the forms.
    rows = []
    at = SINCE + timedelta(days=3)

    def swipe(win, lose, n):
        nonlocal at
        for _ in range(n):
            at += timedelta(minutes=5)
            for w in win:
                for l in lose:
                    rows.append({"user_id": "user_picks", "winner_player_id": w,
                                 "loser_player_id": l, "decision_type": "trade",
                                 "k_factor": 0.0, "created_at": _iso(at),
                                 "scoring_format": FMT})

    swipe(["generic_pick_2_mid"], ["w4"], 4)              # 4 generic rows applied
    swipe(["w6"], ["lg1_2027_1_3"], 3)                    # 3 league-pick rows skipped
    swipe(["w5"], ["9999"], 3)                            # 3 other rows skipped
    swipe(["generic_pick_1_late"], ["w1", "lg1_2028_2_4"], 1)  # 1 applied + 1 skipped
    mixed = create_engine("sqlite://", poolclass=StaticPool,
                          connect_args={"check_same_thread": False})
    _seed(mixed)
    with mixed.begin() as conn:
        conn.execute(insert(db.swipe_decisions_table), rows)
    sr._install_readonly_guard(mixed)
    report = sr.run(mixed, SINCE, UNTIL)
    c = report["counts"]
    assert (c["generic_pick_rows_applied"], c["skipped_league_pick_rows"],
            c["skipped_other_rows"]) == (5, 4, 3)
    assert c["boards_included"] == 2 and c["restored_rows"] == 13 + 12


def test_pick_order_inversions_inside_a_tier_are_caught(world):
    """What `_feedback_bounds` actually allows: Early and Mid 1st (1720 /
    1650) share `first_1`, so repeated Mid-over-Early swipes invert them and
    the check catches it, with no tier change. Late 1st (1580, `first_1`)
    against Early 2nd (1470, `second`) straddles a band, so the same pressure
    is clamped and cannot invert them."""
    engine, _ = world
    players, seed, _ = _pool(engine)

    def rows(win, lose, k, n=40):
        return [{"winner_player_id": win, "loser_player_id": lose,
                 "decision_type": "trade", "k_factor": k,
                 "created_at": "2026-09-01T00:00:00+00:00"} for _ in range(n)]

    def boards(win, lose):
        with_b = sr.build_board(players, seed, FMT, rows(win, lose, 8.0))
        without_b = sr.build_board(players, seed, FMT, rows(win, lose, 0.0))
        return with_b, without_b

    with_b, without_b = boards("generic_pick_1_mid", "generic_pick_1_early")
    assert sr.pick_inversions(without_b) == set()
    assert sr.pick_inversions(with_b) - sr.pick_inversions(without_b) == {
        ("generic_pick_1_early", "generic_pick_1_mid")}
    assert sr.tier_violations(with_b, without_b) == 0

    with_b, without_b = boards("generic_pick_2_early", "generic_pick_1_late")
    assert with_b["generic_pick_2_early"][0] > without_b["generic_pick_2_early"][0]
    assert sr.pick_inversions(with_b) == set(), "the band edge holds the ladder"


def test_pick_order_is_clean_on_a_clean_board(world):
    engine, _ = world
    players, seed, _ = _pool(engine)
    assert sr.pick_inversions(sr.build_board(players, seed, FMT, [])) == set()
    assert sr.pick_inversions(
        sr.build_board(players, seed, FMT, _stored_rows(engine))) == set()


# ---------------------------------------------------------------------------
# Monitor mode (the 14-day post-flip watch, stored K)
# ---------------------------------------------------------------------------

FLIP = datetime(2026, 10, 1, tzinfo=UTC)
MON_UNTIL = datetime(2026, 10, 15, tzinfo=UTC)


def _monitor_engine(*events, matches=()):
    """The base world plus post-flip rows: (user, win, lose, k, dtype, at, n),
    and trade_matches rows: (user_a, user_b, a_give, a_receive)."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    _seed(engine)
    rows = []
    for user, win, lose, k, dtype, at, n in events:
        for i in range(n):
            rows.append({"user_id": user, "winner_player_id": win,
                         "loser_player_id": lose, "decision_type": dtype,
                         "k_factor": k, "created_at": _iso(at + timedelta(minutes=i)),
                         "scoring_format": FMT})
    with engine.begin() as conn:
        conn.execute(insert(db.swipe_decisions_table), rows)
        for a, b, give, recv in matches:
            conn.execute(insert(db.trade_matches_table).values(
                league_id="lg", user_a_id=a, user_b_id=b,
                user_a_give=json.dumps(give), user_a_receive=json.dumps(recv)))
    sr._install_readonly_guard(engine)
    return engine


def _board_weeks(report, user):
    key = sr._hash(f"{user}|{FMT}")
    return next(b for b in report["boards"] if b["board"] == key)[f"k_scale_{sr.MONITOR_KEY}"]


def test_monitor_reads_stored_k_and_reports_ok():
    """Post-flip likes stored at K 4 move the live board; a pre-flip trio
    inversion of the 1st-round rungs is pre-existing and never fires (d)."""
    at = FLIP + timedelta(days=1)
    engine = _monitor_engine(
        ("user_live", "w2", "w1", 4.0, "trade", at, 3),
        ("user_pre", "generic_pick_1_mid", "generic_pick_1_early", 32.0, "rank",
         FLIP - timedelta(days=30), 6),
        ("user_pre", "w2", "w1", 4.0, "trade", at, 1))
    report = sr.run(engine, FLIP, MON_UNTIL, min_swipes=1, mode="monitor")
    assert report["mode"] == "monitor"
    assert report["check_5b_i"] is None and report["ship_rule"] is None
    assert report["counts"]["boards_included"] == 2     # the frozen-period boards are out

    live = _board_weeks(report, "user_live")
    assert [(w["trade_swipes"], w["discordant_pairs"]) for w in live] == [(3, 1), (0, 0)]

    pre = _board_weeks(report, "user_pre")
    assert pre[0]["pick_inversions_without"] > 0       # trio votes inverted the rungs
    assert pre[0]["pick_inversions_introduced"] == 0

    res = report["results"][sr.MONITOR_KEY]
    assert res["check_5b_ii"]["tier_membership_violations"] == 0
    assert res["kill_rule"]["status"] == "OK"
    assert [w["fires_d"] for w in res["kill_rule"]["weeks"]] == [False]
    text = sr.summary_text(report)
    assert "swipe monitor" in text and "overall: OK" in text
    assert "week 2026-10-01: OK" in text


def test_monitor_kill_d_on_an_introduced_pick_inversion():
    engine = _monitor_engine(
        ("user_rung", "generic_pick_1_mid", "generic_pick_1_early", 4.0, "trade",
         FLIP + timedelta(days=2), 40))
    report = sr.run(engine, FLIP, MON_UNTIL, min_swipes=1, mode="monitor")
    weeks = _board_weeks(report, "user_rung")
    assert weeks[0]["pick_inversions_without"] == 0
    assert weeks[0]["pick_inversions_introduced"] == 1
    kill = report["results"][sr.MONITOR_KEY]["kill_rule"]
    assert kill["weeks"][0]["fires_d"] is True and kill["status"] == "KILL"
    text = sr.summary_text(report)
    assert "week 2026-10-01: KILL (kill d)" in text and "overall: KILL" in text


E1, L1 = "generic_pick_1_early", "generic_pick_1_late"


def _disposition_world(users):
    """Each user: 30 disposition rows pushing Late 1st over Early 1st (K 20,
    a 100-point move in the n = 4 RB `first_1` group) plus three trade
    swipes that week (w2 over w1, K 4: they swap, a 12.5-point move in a
    group of nine). d1's rows are accepts (its match side gives E1 for L1),
    d2's declines (it gives L1 for E1), and d2 has one disposition no match
    explains."""
    at = FLIP + timedelta(days=2)
    events, matches = [], []
    for u in users:
        events += [(u, L1, E1, 20.0, "disposition", at, 30),
                   (u, "w2", "w1", 4.0, "trade", at + timedelta(hours=1), 3)]
    if "d1" in users:
        matches.append(("d1", "x", [E1], [L1]))              # accept: receive won
    if "d2" in users:
        matches.append(("d2", "x", [L1], [E1]))              # decline: give won
        events.append(("d2", "w4", "w5", 20.0, "disposition",
                       at + timedelta(hours=2), 1))           # unmatched
    return _monitor_engine(*events, matches=matches)


def test_monitor_counts_dispositions_and_alerts_on_two_boards():
    report = sr.run(_disposition_world(["d1", "d2"]), FLIP, MON_UNTIL,
                    min_swipes=1, mode="monitor")
    c = report["counts"]
    assert (c["dispositions_accept"], c["dispositions_decline"],
            c["dispositions_unmatched"]) == (30, 30, 1)
    disp = report["results"][sr.MONITOR_KEY]["dispositions"]
    w = disp["weeks"][0]
    assert (w["boards"], w["accepts"], w["declines"], w["unmatched"]) == (2, 30, 30, 1)
    assert w["max_pct_move_n4"] == 100.0 and w["boards_ge75_n4"] == 2
    assert w["alert"] is True and disp["alert"] is True
    text = sr.summary_text(report)
    assert "DISPOSITION ALERT: yes" in text
    assert "disposition alert (models-lead review, not a kill): ALERT" in text


def test_monitor_one_disposition_board_is_no_alert():
    report = sr.run(_disposition_world(["d1"]), FLIP, MON_UNTIL,
                    min_swipes=1, mode="monitor")
    w = report["results"][sr.MONITOR_KEY]["dispositions"]["weeks"][0]
    assert (w["boards_ge75_n4"], w["alert"]) == (1, False)
    assert "DISPOSITION ALERT: no" in sr.summary_text(report)


def test_dispositions_never_reach_the_kill_metrics():
    """Two boards with a 100-point disposition-driven move in an n = 4 group
    would trip kill (b) if dispositions were toggled. They aren't: the kill
    sees only the trade swipe's 12.5-point move, and the pick inversion the
    dispositions made sits in WITH and WITHOUT alike, so (d) stays quiet."""
    report = sr.run(_disposition_world(["d1", "d2"]), FLIP, MON_UNTIL,
                    min_swipes=1, mode="monitor")
    res = report["results"][sr.MONITOR_KEY]
    for user in ("d1", "d2"):
        week = _board_weeks(report, user)[0]
        assert week["max_pct_move_n4"] == pytest.approx(12.5)
        assert week["disposition_max_pct_move_n4"] == 100.0
        assert week["pick_inversions_without"] > 0
        assert week["pick_inversions_introduced"] == 0
    kill = res["kill_rule"]["weeks"][0]
    assert (kill["boards_ge75_n4"], kill["fires_b"], kill["fires_d"]) == (0, False, False)
    assert res["kill_rule"]["status"] == "OK"
    # A disposition-only board is watched but never active for the kill.
    alone = sr.run(_monitor_engine(("d3", L1, E1, 20.0, "disposition",
                                    FLIP + timedelta(days=2), 30)),
                   FLIP, MON_UNTIL, min_swipes=1, mode="monitor")
    res = alone["results"][sr.MONITOR_KEY]
    assert res["board_weeks_active"] == 0 and res["kill_rule"]["status"] == "OK"
    assert res["dispositions"]["weeks"][0]["max_pct_move_n4"] == 100.0


def test_monitor_cli_needs_the_flip_time(tmp_path):
    path = tmp_path / "snap.db"
    _seed(create_engine(f"sqlite:///{path}"))
    with pytest.raises(SystemExit):
        sr.main(["--db", str(path), "--mode", "monitor", "--output",
                 str(tmp_path / "m.json")])
    assert sr.main(["--db", str(path), "--mode", "monitor", "--since", "2026-10-01",
                    "--until", "2026-10-15", "--output", str(tmp_path / "m.json")]) == 0
    assert json.loads((tmp_path / "m.json").read_text())["min_swipes"] == 1


def test_readonly_guard_refuses_writes(tmp_path):
    path = tmp_path / "snap.db"
    _seed(create_engine(f"sqlite:///{path}"))
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    engine = sr.open_readonly_engine(str(path))
    for stmt in ("INSERT INTO model_config (key, value) VALUES ('x', 1)",
                 "UPDATE swipe_decisions SET k_factor = 8",
                 "DELETE FROM swipe_decisions",
                 "CREATE TABLE t (x INTEGER)"):
        with pytest.raises(sr.ReadOnlyViolation):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    with engine.connect() as conn:          # reads still work
        assert conn.execute(text("SELECT COUNT(*) FROM swipe_decisions")).scalar() > 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    with pytest.raises(SystemExit):
        sr.open_readonly_engine("postgresql://u@h/db")
    with pytest.raises(SystemExit):
        sr.open_readonly_engine(str(tmp_path / "missing.db"))
    # With the flag: Render's postgres:// form is accepted (no connection is
    # made here) and the password never reaches the report.
    url = "postgres://u:s3cret@h/db"
    pg = sr.open_readonly_engine(url, allow_postgres_readonly=True)
    assert pg.url.drivername.startswith("postgresql")
    prov = sr._provenance(url, pg, argparse.Namespace(db=url))
    assert "s3cret" not in json.dumps(prov, default=str)


def test_cli_writes_report_and_leaves_the_file_untouched(tmp_path, capsys):
    path = tmp_path / "snap.db"
    _seed(create_engine(f"sqlite:///{path}"))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    out = tmp_path / "report.json"
    assert sr.main(["--db", str(path), "--since", "2026-08-19", "--until",
                    "2026-09-16", "--output", str(out)]) == 0
    report = json.loads(out.read_text())
    assert set(report["results"]) == {"1.0", "0.5"}
    assert report["check_5b_i"]["pass"] is True
    assert report["provenance"]["database_sha256"] == before
    assert ME not in out.read_text(), "boards are reported by hash, not user id"
    printed = capsys.readouterr().out
    for line in ("5a-i  Kendall", "5a-ii pct move", "5b(ii) tier-membership violations 0",
                 "kill rule (a)/(b)/(d) would have fired: no; (b) alert weeks: none",
                 "5b(i)",
                 "ship rule: ship at full K", "caveat: Upper bound: fit_mult = 1",
                 "pick order: pre-existing inversions 0, introduced 0 -> PASS",
                 "generic-pick pairs applied 0, skipped league-pick 0, skipped other 0"):
        assert line in printed, line
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_module_never_imports_backend_server():
    probe = ("import sys, backend.eval.swipe_replay; "
             "print('backend.server' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
