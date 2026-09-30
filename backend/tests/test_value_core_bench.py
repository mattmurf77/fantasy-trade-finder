"""value_core_bench: guardrails, synthetic league, seat snapshots, run verdict, freeze.

WP1-WP3 modules (windows, adapter, pipeline) are stubbed through sys.modules the
same way as WP3's vc_stubs (specs.md section 4); after integration the stubs patch
the real modules and these tests keep passing. Nothing here touches the network
or production.
"""
import importlib
import json
import stat
import sys
import types as _t
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from backend.eval import value_core_bench as bench
from backend.trade_service import elo_to_value, value_to_elo
from backend.value_core.types import (
    DEFAULT_WINDOW, CoreDiagnostics, DeckEntry, FairTrade, LeagueSnapshot, PipelineResult,
    RosterRules, ScoredTrade, Scores, Standing,
)

FIRST, ELITE = 1492.0, 8457.0
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX")


@pytest.fixture
def vc_stubs(monkeypatch):
    mods = {}
    for name in ("windows", "adapter", "pipeline"):
        full = f"backend.value_core.{name}"
        try:
            mod = importlib.import_module(full)
        except ImportError:
            mod = _t.ModuleType(full)
            monkeypatch.setitem(sys.modules, full, mod)
        mods[name] = mod
    calls = []

    def infer_windows(**kw):
        calls.append(kw)
        return {}
    monkeypatch.setattr(mods["windows"], "infer_windows", infer_windows, raising=False)
    monkeypatch.setattr(mods["adapter"], "tier_values", lambda fmt: (FIRST, ELITE), raising=False)
    monkeypatch.setattr(mods["adapter"], "default_lineup_slots", lambda fmt: SLOTS, raising=False)
    mods["window_calls"] = calls
    return mods


def _snapshot():
    return LeagueSnapshot("L", "1qb_ppr", {}, {}, RosterRules(SLOTS, None), FIRST, ELITE)


def _entry(i, give, receive, g, r, *, starter, best_in, partner="P"):
    trade = FairTrade(partner, tuple(give), tuple(receive), float(g), float(r), r / g,
                      0.0, None, False, (0, 0))
    detail = {"value": {"delta_ln": 0.0, "s_delta": 0.5, "best_in_id": receive[0],
                        "best_in_market": float(best_in), "best_in_starter": starter,
                        "s_piece": 1.0},
              "outlook": {}, "rank": {}}
    return DeckEntry(i, ScoredTrade(trade, Scores(0.5, 0.5, 0.5, 0.5), detail), 0.5,
                     ("Fair on value",))


def test_guardrails_exact_numbers():
    entries = [
        _entry(0, ["x"], ["b1"], 1000, 1000, starter=True, best_in=1000),
        _entry(1, ["x"], ["b2"], 1000, 1300, starter=False, best_in=1600),
        _entry(2, ["x"], ["b3"], 1200, 1000, starter=False, best_in=1000, partner="Q"),
        _entry(3, ["y"], ["b4"], 1000, 950, starter=True, best_in=950),
    ]
    g = bench.guardrails(entries, _snapshot())
    assert g["insult_rate"] == 0.25                      # (1300 - 1000) / 1300 > 0.20
    assert g["real_piece_back_share"] == 0.75
    assert g["median_value_given"] == pytest.approx(-0.025)
    assert g["max_asset_appearances"] == 3               # "x" given three times: reported only
    assert g["max_acquired_appearances"] == 1
    assert g["most_repeated_asset"] == "x"
    assert g["partners"] == 2
    assert g["cards"] == 4
    assert g["pass"] == {"insult": False, "real_piece": True, "median_given": True,
                         "appearances": True, "near_duplicates": True}
    assert g["near_duplicates"] == 0 and g["acquisition_repeats"] == 0
    assert g["max_partner_cards"] == 3


def test_guardrails_count_near_duplicates_and_repeat_acquisitions():
    """Same partner + same headliners (throw-ins differ) is a near-duplicate; acquiring the
    same headliner from the same partner twice is a repeat acquisition."""
    entries = [
        _entry(0, ["x"], ["b1", "m1"], 1000, 1000, starter=True, best_in=1000),
        _entry(1, ["x"], ["b1", "m2"], 1000, 1000, starter=True, best_in=1000),   # near-duplicate
        _entry(2, ["z"], ["b1"], 1000, 1000, starter=True, best_in=1000),          # repeat acquisition
        _entry(3, ["y"], ["c1"], 1000, 1000, starter=True, best_in=1000, partner="Q"),
    ]
    g = bench.guardrails(entries, _snapshot())
    assert g["near_duplicates"] == 1
    assert g["acquisition_repeats"] == 2
    assert g["pass"]["near_duplicates"] is False


def test_guardrails_top_window_only():
    entries = [_entry(i, [f"g{i}"], [f"r{i}"], 1000, 1000, starter=True, best_in=1000)
               for i in range(40)]
    g = bench.guardrails(entries, _snapshot())
    assert g["cards"] == 30
    assert g["max_asset_appearances"] == 1
    assert bench.guardrails([], _snapshot())["cards"] == 0


RECORD_KEYS = {"league_id", "name", "platform", "scoring_format", "lineup_slots", "max_players",
               "completed_weeks", "standings", "assets", "teams", "boards", "seed_elo"}
ASSET_KEYS = {"kind", "position", "name", "age", "market", "search_rank", "pick_value"}
TEAM_KEYS = {"team_id", "name", "asset_ids", "other_players", "declared_outlook", "pick_share"}


def test_synthetic_league_valid_and_deterministic():
    frozen = bench.synthetic_league(7)
    assert frozen == bench.synthetic_league(7)
    assert frozen != bench.synthetic_league(8)
    assert frozen["schema"] == bench.SCHEMA
    json.dumps(frozen, allow_nan=False)
    (league,) = frozen["leagues"]
    assert set(league) == RECORD_KEYS
    assert len(league["teams"]) == 12
    for team in league["teams"]:
        assert set(team) == TEAM_KEYS
        assert all(a in league["assets"] for a in team["asset_ids"])
        kinds = [league["assets"][a]["kind"] for a in team["asset_ids"]]
        assert kinds.count("player") == 22 and kinds.count("pick") == 4
    for asset in league["assets"].values():
        assert set(asset) == ASSET_KEYS
        assert 100.0 <= asset["market"] <= 9500.0
    assert len(league["boards"]) == 2
    assert all(set(b) == {"elo", "comparisons"} for b in league["boards"].values())
    assert all(set(s) == {"wins", "losses", "ties", "points_for"}
               for s in league["standings"].values())
    assert set(league["standings"]) == {t["team_id"] for t in league["teams"]}


def _mini_league(boards=None):
    return {"league_id": "L1", "name": "Mini", "platform": "sleeper", "scoring_format": "1qb_ppr",
            "lineup_slots": list(SLOTS), "max_players": 20, "completed_weeks": 3,
            "standings": {"me": {"wins": 2, "losses": 1, "ties": 0, "points_for": 300.5}},
            "assets": {"p1": {"kind": "player", "position": "WR", "name": "P One", "age": 24.0,
                              "market": elo_to_value(1600.0), "search_rank": 10, "pick_value": None},
                       "p2": {"kind": "player", "position": "RB", "name": "P Two", "age": None,
                              "market": 900.0, "search_rank": 40, "pick_value": None},
                       "k1": {"kind": "pick", "position": "PICK", "name": "2027 1st", "age": None,
                              "market": 2117.0, "search_rank": None, "pick_value": 60.0}},
            "teams": [{"team_id": "me", "name": "Mine", "asset_ids": ["p1", "k1"],
                       "other_players": 1, "declared_outlook": "jets", "pick_share": 0.6},
                      {"team_id": "opp", "name": "Theirs", "asset_ids": ["p2"],
                       "other_players": 0, "declared_outlook": None, "pick_share": 0.4}],
            "boards": boards or {}, "seed_elo": {"p1": 1600.0, "p2": 1450.0}}


def test_snapshot_for_seat_shrinks_board(vc_stubs):
    league = _mini_league({"me": {"elo": {"p1": 1700.0}, "comparisons": {"p1": 4}}})
    snapshot, board = bench.snapshot_for_seat(league, "me", standings_weight=0.3)
    assert board.values["p1"] == pytest.approx(elo_to_value(1650.0))   # w = 4 / (4 + 4)
    assert board.comparisons == {"p1": 4}
    assert (snapshot.first_round_value, snapshot.elite_value) == (FIRST, ELITE)
    assert snapshot.teams["me"].asset_ids == ("p1", "k1")
    assert snapshot.teams["me"].other_players == 1
    assert snapshot.teams["me"].window == DEFAULT_WINDOW
    assert snapshot.assets["k1"].kind == "pick" and snapshot.assets["k1"].age is None
    assert snapshot.rules == RosterRules(SLOTS, 20)
    (call,) = vc_stubs["window_calls"]
    assert call["team_rosters"] == {"me": ["p1", "k1"], "opp": ["p2"]}
    assert call["standings"] == {"me": Standing(2, 1, 0, 300.5)}
    assert call["declared"] == {"me": "jets", "opp": None}
    assert call["pick_shares"] == {"me": 0.6, "opp": 0.4}
    assert (call["completed_weeks"], call["standings_weight"]) == (3, 0.3)
    assert call["players"]["k1"].pick_value == 60.0
    # the opponent has no board -> no personal values
    assert bench.snapshot_for_seat(league, "opp", standings_weight=0.3)[1] is None


def _stub_engine(*, repeat, seen=None):
    def engine(snapshot, request, core_cfg, rank_cfg):
        if seen is not None:
            seen.append((request, core_cfg, rank_cfg))
        viewer = snapshot.teams[request.viewer_team_id]
        partner_id = next(t for t in sorted(snapshot.teams) if t != request.viewer_team_id)
        partner = snapshot.teams[partner_id]
        entries = []
        for i in range(30):
            receive = (partner.asset_ids[0] if repeat and i < 4 else partner.asset_ids[i],)
            entries.append(_entry(i, (viewer.asset_ids[i],), receive, 1000, 1000,
                                  starter=True, best_in=1000, partner=partner_id))
        return PipelineResult(entries, CoreDiagnostics(partners=1, fair=30), 5)
    return engine


def _tiny_frozen():
    assets, teams = {}, []
    for tid in ("user_a", "user_b"):
        ids = [f"{tid}_w{i:02d}" for i in range(40)]
        for aid in ids:
            assets[aid] = {"kind": "player", "position": "WR", "name": aid.upper(), "age": 25.0,
                           "market": 1000.0, "search_rank": 50, "pick_value": None}
        teams.append({"team_id": tid, "name": f"Team {tid[-1].upper()}", "asset_ids": ids,
                      "other_players": 0, "declared_outlook": None, "pick_share": 0.5})
    league = {"league_id": "L2", "name": "Tiny", "platform": "sleeper",
              "scoring_format": "1qb_ppr", "lineup_slots": list(SLOTS), "max_players": None,
              "completed_weeks": 0, "standings": {}, "assets": assets, "teams": teams,
              "boards": {}, "seed_elo": {}}
    return {"schema": bench.SCHEMA, "frozen_on": "2026-09-30", "leagues": [league]}


def test_run_verdict_with_stub_engine(vc_stubs):
    frozen = _tiny_frozen()
    dirty = bench.run(frozen, variants={"default": {}}, engine=_stub_engine(repeat=True))
    v = dirty["variants"]["default"]
    assert v["worst_seat_acquired_appearances"] == 4
    assert v["pass"]["appearances"] is False
    assert v["verdict"] == "FAIL"

    seen = []
    clean = bench.run(frozen, variants={"tight": {"core": {"band": 0.05},
                                                  "rank": {"w_rank": 2.0}}},
                      engine=_stub_engine(repeat=False, seen=seen))
    v = clean["variants"]["tight"]
    assert v["verdict"] == "PASS"
    assert (v["cards"], v["insult_rate"], v["real_piece_back_share"],
            v["median_value_given"], v["worst_seat_acquired_appearances"]) == (60, 0.0, 1.0, 0.0, 1)
    assert [s["team"] for s in v["seats"]] == ["Team A", "Team B"]
    assert all(s["core"]["fair"] == 30 and s["pool"] == 30 for s in v["seats"])
    assert {r.viewer_team_id for r, _, _ in seen} == {"user_a", "user_b"}
    assert all(c.band == 0.05 and rk.w_rank == 2.0 for _, c, rk in seen)
    cards = clean["card_sets"]["tight"]
    assert cards["source"] == "value_core_bench" and len(cards["cards"]) == 60
    assert set(cards["cards"][0]) == {"league", "seat", "partner", "give", "receive", "reasons"}

    assert bench.run(frozen, variants={"d": {}}, seats="boarded",
                     engine=_stub_engine(repeat=False))["variants"]["d"]["cards"] == 0
    with pytest.raises(ValueError):
        bench.run(frozen, variants={"d": {"bogus": 1}}, engine=_stub_engine(repeat=False))


def test_league_record_pure_transform():
    picks = [{"pick_id": f"u1_p{i}", "season": 2027, "round": 1 + i % 3, "owner_user_id": "u1",
              "pick_value": 10.0, "pool_value": 1000.0 + 100 * i} for i in range(8)]
    picks += [{"pick_id": "u2_p0", "season": 2028, "round": 2, "owner_user_id": "u2",
               "pick_value": 20.0, "pool_value": 600.0},
              {"pick_id": "ghost_p0", "season": 2027, "round": 1, "owner_user_id": "ghost",
               "pick_value": 20.0, "pool_value": 2000.0}]
    record = bench.league_record(
        league_row={"sleeper_league_id": "L9", "name": "Bench League", "platform": "sleeper",
                    "default_scoring": "sf_tep"},
        members=[{"user_id": "u1", "username": "alpha", "display_name": "Alpha",
                  "roster_data": json.dumps(["p1", "k1", "p2"])},
                 {"user_id": "u2", "username": "beta", "display_name": None,
                  "roster_data": ["p3", "p1"]}],
        picks=picks,
        rankings=[{"user_id": "u1", "player_id": "p1", "elo": 1700.0, "comparison_count": 9},
                  {"user_id": "u1", "player_id": "p3", "elo": 1500.0, "comparison_count": None},
                  {"user_id": "u1", "player_id": "zz", "elo": 1900.0, "comparison_count": 3},
                  {"user_id": "u2", "player_id": "p2", "elo": 1600.0, "comparison_count": 3},
                  {"user_id": "stranger", "player_id": "p1", "elo": 1800.0,
                   "comparison_count": 5}],
        players={"p1": {"full_name": "Pat One", "position": "WR", "age": 24, "search_rank": 31},
                 "p2": {"full_name": "Pete Two", "position": "RB", "age": None,
                        "search_rank": 80},
                 "p3": {"full_name": "Paul Three", "position": "QB", "age": 29,
                        "search_rank": 12},
                 "k1": {"full_name": "Kick Er", "position": "K", "age": 30, "search_rank": 400}},
        consensus_elo={"p1": 1650.0, "p2": 1550.0},
        declared={"u2": "rebuilder"},
        meta={"roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K",
                                   "BN", "BN", "BN"],
              "settings": {"reserve_slots": 2, "taxi_slots": 3}},
        state=SimpleNamespace(completed_weeks=5, teams=[
            SimpleNamespace(user_id="u1", wins=3, losses=2, ties=0, points_for=512.4),
            SimpleNamespace(user_id="u2", wins=2, losses=3, ties=0, points_for=498.0),
            SimpleNamespace(user_id="x9", wins=5, losses=0, ties=0, points_for=700.0)]))

    def pick(pid, season, rnd, pool):
        return {"kind": "pick", "position": "PICK", "name": f"{season} {rnd}", "age": None,
                "market": pool, "search_rank": None,
                "pick_value": round((value_to_elo(pool) - 1200.0) / 6.0, 3)}
    u1_picks = [f"u1_p{i}" for i in (7, 6, 5, 4, 3, 2)]            # top 6 by pool_value
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}
    expected_assets = {
        "p1": {"kind": "player", "position": "WR", "name": "Pat One", "age": 24.0,
               "market": elo_to_value(1650.0), "search_rank": 31, "pick_value": None},
        "p2": {"kind": "player", "position": "RB", "name": "Pete Two", "age": None,
               "market": elo_to_value(1550.0), "search_rank": 80, "pick_value": None},
        "p3": {"kind": "player", "position": "QB", "name": "Paul Three", "age": 29.0,
               "market": 0.0, "search_rank": 12, "pick_value": None},
        **{f"u1_p{i}": pick(f"u1_p{i}", 2027, ordinal[1 + i % 3], 1000.0 + 100 * i)
           for i in (7, 6, 5, 4, 3, 2)},
        "u2_p0": pick("u2_p0", 2028, "2nd", 600.0),
    }
    assert record == {
        "league_id": "L9", "name": "Bench League", "platform": "sleeper",
        "scoring_format": "sf_tep",
        "lineup_slots": ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"],
        "max_players": 15,                                         # 10 slots + 2 IR + 3 taxi
        "completed_weeks": 5,
        "standings": {"u1": {"wins": 3, "losses": 2, "ties": 0, "points_for": 512.4},
                      "u2": {"wins": 2, "losses": 3, "ties": 0, "points_for": 498.0}},
        "assets": expected_assets,
        "teams": [{"team_id": "u1", "name": "Alpha", "asset_ids": ["p1", "p2"] + u1_picks,
                   "other_players": 1, "declared_outlook": None, "pick_share": 80.0 / 120.0},
                  {"team_id": "u2", "name": "beta", "asset_ids": ["p3", "u2_p0"],
                   "other_players": 0, "declared_outlook": "rebuilder",
                   "pick_share": 20.0 / 120.0}],
        "boards": {"u1": {"elo": {"p1": 1700.0, "p3": 1500.0}, "comparisons": {"p1": 9}},
                   "u2": {"elo": {"p2": 1600.0}, "comparisons": {"p2": 3}}},
        "seed_elo": {"p1": 1650.0, "p2": 1550.0},
    }
    json.dumps(record, allow_nan=False)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeConn:
    def __init__(self, value):
        self.value, self.sql = value, []

    def execute(self, clause, params=None):
        self.sql.append(str(clause))
        return _Result(self.value)


def test_assert_read_only():
    with pytest.raises(ValueError):
        bench.assert_read_only(_FakeConn("off"))
    conn = _FakeConn("on")
    bench.assert_read_only(conn)
    assert conn.sql == ["SHOW transaction_read_only"]


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_outputs_private_and_fresh(vc_stubs, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(vc_stubs["pipeline"], "run", _stub_engine(repeat=False), raising=False)
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps(_tiny_frozen()))
    out = tmp_path / "run1"
    assert bench.main(["run", "--frozen", str(frozen_path), "--output", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["cards-default.json", "results.json"]
    assert all(_mode(p) == 0o600 for p in out.iterdir())
    assert _mode(out) == 0o700
    stdout = capsys.readouterr().out
    assert "verdict default: PASS" in stdout
    assert "user_a" not in stdout and "user_b" not in stdout      # no team (user) ids
    results = json.loads((out / "results.json").read_text())
    assert "card_sets" not in results and results["variants"]["default"]["verdict"] == "PASS"

    with pytest.raises(SystemExit):
        bench.main(["run", "--frozen", str(frozen_path), "--output", str(out)])
    with pytest.raises(FileExistsError):
        bench.fresh_dir(out)
    with pytest.raises(FileExistsError):
        bench.write_private_json(out / "results.json", {})
    (tmp_path / "not-frozen.json").write_text("{}")
    with pytest.raises(ValueError):
        bench.load_frozen(tmp_path / "not-frozen.json")


# ---------------------------------------------------------------------------
# freeze: the I/O shell against an in-memory SQLite standing in for prod
# ---------------------------------------------------------------------------

class _ReadOnlyConn:
    """Answers SHOW transaction_read_only like a read-only Postgres session."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, clause, params=None):
        if str(clause).strip() == "SHOW transaction_read_only":
            return _Result("on")
        return self._conn.execute(clause, params or {})


class _FakeEngine:
    def __init__(self, engine):
        self.engine, self.disposed = engine, False

    @contextmanager
    def connect(self):
        with self.engine.connect() as conn:
            yield _ReadOnlyConn(conn)

    def dispose(self):
        self.disposed = True


def test_freeze_reads_through_read_only_connection(monkeypatch, tmp_path):
    from sqlalchemy import create_engine, insert

    from backend import database as db
    from backend.tools import prod_analytics

    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(db.leagues_table), [{
            "sleeper_league_id": "1234", "user_id": "u1", "name": "Bench",
            "platform": "sleeper", "default_scoring": "1qb_ppr"}])
        conn.execute(insert(db.league_members_table), [
            {"league_id": "1234", "user_id": "u1", "username": "a", "display_name": "A",
             "roster_data": json.dumps(["p1"])},
            {"league_id": "1234", "user_id": "u2", "username": "b", "display_name": "B",
             "roster_data": json.dumps(["p2"])}])
        conn.execute(insert(db.players_table), [
            {"player_id": "p1", "full_name": "One", "position": "WR", "age": 25},
            {"player_id": "p2", "full_name": "Two", "position": "RB", "age": 23}])
        conn.execute(insert(db.player_value_history_table), [
            {"player_id": "p1", "scoring_format": "1qb_ppr", "consensus_elo": 1500.0,
             "snapshot_date": "2026-09-01"},
            {"player_id": "p1", "scoring_format": "1qb_ppr", "consensus_elo": 1600.0,
             "snapshot_date": "2026-09-29"},
            {"player_id": "p1", "scoring_format": "1qb_ppr", "consensus_elo": 9999.0,
             "snapshot_date": "2026-10-05"},
            {"player_id": "p2", "scoring_format": "1qb_ppr", "consensus_elo": 1550.0,
             "snapshot_date": "2026-09-29"}])
        conn.execute(insert(db.member_rankings_table), [
            {"user_id": "u1", "league_id": "1234", "player_id": "p2", "elo": 1650.0,
             "scoring_format": None, "comparison_count": 6},
            {"user_id": "u1", "league_id": "1234", "player_id": "p1", "elo": 1400.0,
             "scoring_format": "sf_tep", "comparison_count": 6}])
        conn.execute(insert(db.draft_picks_table), [
            {"pick_id": "pk1", "league_id": "1234", "season": 2027, "round": 1,
             "owner_user_id": "u2", "pick_value": 60.0, "pool_value": 2117.0,
             "source": "platform"},
            {"pick_id": "pk2", "league_id": "1234", "season": 2027, "round": 2,
             "owner_user_id": "u2", "pick_value": 30.0, "pool_value": 700.0, "source": "user"}])
        conn.execute(insert(db.league_preferences_table), [
            {"user_id": "u2", "league_id": "1234", "team_outlook": "jets"}])

    fake = _FakeEngine(engine)
    monkeypatch.setattr(prod_analytics, "_load_prod_url", lambda: "postgresql://prod")
    monkeypatch.setattr(prod_analytics, "_connect_readonly", lambda url, timeout: fake)
    fetched = []

    def fetch(url):
        fetched.append(url)
        path = url.split("/v1/", 1)[1]
        if path == "league/1234":
            return {"roster_positions": ["QB", "RB", "WR", "BN"], "status": "in_season",
                    "settings": {"reserve_slots": 1, "taxi_slots": 0, "playoff_week_start": 3}}
        if path == "league/1234/rosters":
            return [{"roster_id": 1, "owner_id": "u1", "players": ["p1"],
                     "settings": {"wins": 1, "losses": 0, "fpts": 100}},
                    {"roster_id": 2, "owner_id": "u2", "players": ["p2"],
                     "settings": {"wins": 0, "losses": 1, "fpts": 90}}]
        if path == "league/1234/users":
            return []
        return []                                    # matchups: no completed weeks

    output = tmp_path / "frozen.json"
    summary = bench.freeze(secrets=tmp_path / "secrets.env", league_ids=["1234"], output=output,
                           today=date(2026, 9, 30), fetch_json=fetch)
    assert summary == {"leagues": 1, "teams": 2, "assets": 3, "boards": 1,
                       "standings_leagues": 1}
    assert "u1" not in json.dumps(summary) and "u2" not in json.dumps(summary)
    assert fake.disposed and all(u.startswith("https://api.sleeper.app/v1/") for u in fetched)
    assert _mode(output) == 0o600
    frozen = bench.load_frozen(output)
    (league,) = frozen["leagues"]
    assert league["assets"]["p1"]["market"] == pytest.approx(elo_to_value(1600.0))
    assert league["assets"]["pk1"]["market"] == 2117.0 and "pk2" not in league["assets"]
    assert league["boards"] == {"u1": {"elo": {"p2": 1650.0}, "comparisons": {"p2": 6}}}
    assert league["teams"][1]["declared_outlook"] == "jets"
    assert league["lineup_slots"] == ["QB", "RB", "WR"] and league["max_players"] == 5
    assert league["standings"]["u1"]["wins"] == 1
    with pytest.raises(FileExistsError):
        bench.freeze(secrets=tmp_path / "secrets.env", league_ids=["1234"], output=output,
                     fetch_json=fetch)


def test_freeze_refuses_non_read_only(monkeypatch, tmp_path):
    from backend.tools import prod_analytics

    class _Writable(_FakeEngine):
        @contextmanager
        def connect(self):
            yield _FakeConn("off")
    fake = _Writable(None)
    monkeypatch.setattr(prod_analytics, "_load_prod_url", lambda: "postgresql://prod")
    monkeypatch.setattr(prod_analytics, "_connect_readonly", lambda url, timeout: fake)
    with pytest.raises(ValueError):
        bench.freeze(secrets=tmp_path / "s.env", league_ids=["1"], output=tmp_path / "f.json",
                     fetch_json=lambda url: pytest.fail("no fetch before the read-only check"))
    assert fake.disposed and not (tmp_path / "f.json").exists()
