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
    assert full["user_weeks"] == 4 and half["user_weeks"] == 4
    assert full["band_move"] == {"median": 0, "p95": 0, "max": 0}
    assert full["rank_churn_per_board_mean"]["max"] > 0
    assert full["bar_5a"] == "PASS" and half["bar_5a"] == "PASS"


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


def test_metric_on_a_hand_built_case():
    def board(**players):            # pid -> (rank, tier)
        return {pid: (0.0, "WR", rank, tier) for pid, (rank, tier) in players.items()}

    a0 = board(x=(1, "second"), y=(2, "second"))
    a1 = board(x=(1, "second"), y=(2, "second"))
    b0 = board(x=(1, "second"), y=(2, "second"))
    b1 = board(x=(5, "fourth"), y=(1, "second"))   # x drops two bands, four ranks
    assert sr.user_week_metrics(a0, a1, b0, b1, {"x", "y"}) == (2, 2.5)
    # Moves A also made are not attributed to the restored swipes.
    assert sr.user_week_metrics(a0, b1, b0, b1, {"x", "y"}) == (0, 0.0)
    assert sr.band_index(None) == len(sr.ORDERED_TIERS)

    assert sr.p95([0, 0, 1, 1, 2]) == 2
    assert sr.summarize([{"band_move": v} for v in (0, 0, 1, 1, 2)], {})["bar_5a"] == "PASS"
    assert sr.summarize([{"band_move": v} for v in (0, 0, 1, 2, 3)], {})["bar_5a"] == "FAIL"
    assert sr.summarize([{"band_move": v} for v in (2, 2, 2)], {})["bar_5a"] == "FAIL"
    assert sr.summarize([], {})["bar_5a"] == "NO DATA"


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
    assert "bar 5a PASS" in printed and "5b(i)" in printed
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_module_never_imports_backend_server():
    probe = ("import sys, backend.eval.swipe_replay; "
             "print('backend.server' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
