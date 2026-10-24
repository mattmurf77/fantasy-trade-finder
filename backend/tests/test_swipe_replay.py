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
    assert snap == "2026-08-01" and "generic_pick_1_early" not in seed
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
    # Groups: six WRs in `second` (15 pairs) + three QBs in `first_1` (3);
    # r1 and t1 are singletons. Week 1's like flips w1/w2: 1 of 18 pairs,
    # and each moves one place in a group of six (20 percentile points).
    weeks = report["boards"][0]["k_scale_1.0"]
    assert [(w["discordant_pairs"], w["same_tier_pairs"]) for w in weeks] == \
        [(1, 18), (0, 18), (0, 18), (0, 18)]
    assert full["kendall"] == {"median": 0.0, "p95": 1 / 18, "max": 1 / 18}
    assert full["max_pct_move"]["max"] == pytest.approx(20.0)
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


def test_kill_rule_thresholds():
    def week(kendalls, moves):
        return [{"week_start": "w", "kendall": k, "max_pct_move": m}
                for k, m in zip(kendalls, moves)]

    calm = sr.kill_indicators(week([0.0] * 19 + [0.3], [0.0] * 20))
    assert calm["weeks"][0]["p95_kendall"] == 0.0     # nearest rank: 19th of 20
    assert calm["would_have_fired"] is False
    edge = sr.kill_indicators(week([0.25] * 20, [74.9] * 20))
    assert edge["weeks"][0]["fires_a"] is False and edge["weeks"][0]["fires_b"] is False
    a = sr.kill_indicators(week([0.0] * 18 + [0.26, 0.26], [0.0] * 20))
    assert a["weeks"][0]["fires_a"] is True and a["would_have_fired"] is True
    b = sr.kill_indicators(week([0.0] * 20, [75.0] + [0.0] * 19))   # 1 of 20 = 5%
    assert b["weeks"][0]["share_pct_move_ge_75"] == 0.05
    assert b["weeks"][0]["fires_b"] is True and b["weeks"][0]["fires_a"] is False


def test_tier_violation_counter():
    without = _hand_board(a=("WR", 1, "second"), b=("WR", 2, "second"),
                          u=("TE", 1, None))
    assert sr.tier_violations(without, without) == 0
    moved = _hand_board(a=("WR", 1, "first_1"), b=("WR", 2, "second"),
                        u=("TE", 1, "waivers"))
    assert sr.tier_violations(moved, without) == 2   # a promoted, u became ranked
    weeks = [{"trade_swipes": 1, "kendall": 0.0, "max_pct_move": 0.0,
              "tier_violations": v, "week_start": "w"} for v in (0, 2)]
    assert sr.summarize(weeks)["check_5b_ii"] == {
        "tier_membership_violations": 2, "verdict": "FAIL"}


def test_bars_and_ship_rule():
    def weeks(kendalls, moves):
        return [{"trade_swipes": 1, "kendall": k, "max_pct_move": m,
                 "tier_violations": 0, "week_start": "w"} for k, m in zip(kendalls, moves)]

    ok = sr.summarize(weeks([0.0, 0.05, 0.15], [0.0, 10.0, 50.0]))
    assert ok["bar_5a_i"] == ok["bar_5a_ii"] == "PASS"
    assert sr.summarize(weeks([0.0, 0.06, 0.06], [0.0] * 3))["bar_5a_i"] == "FAIL"
    assert sr.summarize(weeks([0.0, 0.0, 0.16], [0.0] * 3))["bar_5a_i"] == "FAIL"
    bad = sr.summarize(weeks([0.0] * 3, [0.0, 0.0, 51.0]))
    assert bad["bar_5a_ii"] == "FAIL"
    inactive = sr.summarize([{"trade_swipes": 0, "kendall": None, "max_pct_move": 0.0,
                              "tier_violations": 0, "week_start": "w"}])
    assert inactive["bar_5a_i"] == "NO DATA" and inactive["board_weeks_inactive"] == 1
    assert sr.ship_rule({"1.0": ok, "0.5": ok}, True) == "ship at full K"
    assert sr.ship_rule({"1.0": bad, "0.5": ok}, True) == "ship at half K (4/2)"
    assert sr.ship_rule({"1.0": bad, "0.5": bad}, True).startswith("hold")
    assert sr.ship_rule({"1.0": ok, "0.5": ok}, False).startswith("hold")
    assert sr.p95([0, 0, 1, 1, 2]) == 2


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
                 "kill rule (a)/(b) would have fired: no", "5b(i)",
                 "ship rule: ship at full K", "caveat: Upper bound: fit_mult = 1"):
        assert line in printed, line
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_module_never_imports_backend_server():
    probe = ("import sys, backend.eval.swipe_replay; "
             "print('backend.server' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
