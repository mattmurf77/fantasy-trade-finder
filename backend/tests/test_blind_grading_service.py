"""backend.blind_grading — the Calibration service (docs/plans/blind-grading/specs.md §5.1).

Covers: the neutral formatter (exact keys, sorted sides, arm-independence — hld G1/G5/G6),
the consensus catalog (history values, pool values, the neutral pick label), current-arm
selection (missing / stale / too_few refusals, first-20-then-drop-stale, standing offers,
duplicates), the value-core arm (bench snapshot fed with ServerInputs and the default
config; too_few / failed), merge (G3), the seeded shuffle (G4), the §3.3 split
start_session / build_session (building row, open, failed-never-raises, idempotency,
resume rules, no engine-table writes), the leaf rule (never imports server or tools),
summarize vs blind_grade._score, arm summaries, answer validation, the regrade → complete →
reject flow, results and the admin report. In-memory SQLite, stub engine, no network.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, insert, select

from backend import blind_grading as bg
from backend import database as db
from backend.eval import value_core_bench as bench
from backend.trade_service import elo_to_value
from backend.value_core.types import CoreConfig, RankConfig, Standing

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
SERVED = (NOW - timedelta(days=1)).isoformat()
POSITIONS = ("QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE")
ROSTER = {"u1": [f"p{i}" for i in range(1, 9)],
          "u2": [f"p{i}" for i in range(9, 17)],
          "u3": [f"p{i}" for i in range(17, 25)]}
TRADED_PICK, PLATFORM_PICK, USER_PICK = "L1_2027_1_3", "L1_2027_2_1", "L1_2027_3_1"


def trades_for(viewer):
    """128 unique (partner, give, receive) triples from `viewer`'s seat."""
    return [(partner, (give,), (receive,)) for partner in sorted(set(ROSTER) - {viewer})
            for give in ROSTER[viewer] for receive in ROSTER[partner]]


# u1's seat: current = [:20], value core = [19:39] (exactly one shared trade).
TRADES = trades_for("u1")
CURRENT = TRADES[:20]
VALUE_CORE = TRADES[19:39]
SERVER = bg.ServerInputs(lineup_slots=None, max_players=None, standings={}, completed_weeks=0)
NEUTRAL_KEYS = {"id", "name", "position", "nfl_team", "age", "value"}


def _elo(pid: str) -> float:
    return 1300.0 + 20.0 * int(pid[1:])


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id="L1", user_id="u1", name="Seed League", platform="sleeper",
            default_scoring="1qb_ppr"))
        conn.execute(insert(db.league_members_table), [
            {"league_id": "L1", "user_id": "u1", "username": "me", "display_name": "Me",
             "roster_data": json.dumps(ROSTER["u1"])},
            {"league_id": "L1", "user_id": "u2", "username": "jared", "display_name": "Jared",
             "roster_data": json.dumps(ROSTER["u2"])},
            {"league_id": "L1", "user_id": "u3", "username": "kim", "display_name": None,
             "roster_data": json.dumps(ROSTER["u3"])}])
        conn.execute(insert(db.players_table), [
            {"player_id": f"p{i}", "full_name": f"Player {i:02d}", "position": POSITIONS[(i - 1) % 8],
             "team": f"T{i % 5}", "age": 22 + (i % 9)} for i in range(1, 25)])
        conn.execute(insert(db.player_value_history_table), [
            {"player_id": f"p{i}", "scoring_format": "1qb_ppr", "consensus_elo": _elo(f"p{i}"),
             "snapshot_date": "2026-10-01"} for i in range(1, 24)])      # p24 has no history
        conn.execute(insert(db.draft_picks_table), [
            {"pick_id": TRADED_PICK, "league_id": "L1", "season": 2027, "round": 1,
             "owner_user_id": "u2", "is_traded": 1, "original_username": "Kim",
             "pick_value": 60.0, "pool_value": 2117.0, "source": None},
            {"pick_id": PLATFORM_PICK, "league_id": "L1", "season": 2027, "round": 2,
             "owner_user_id": "u1", "is_traded": 0, "original_username": None,
             "pick_value": 30.0, "pool_value": 700.0, "source": "platform"},
            {"pick_id": USER_PICK, "league_id": "L1", "season": 2027, "round": 3,
             "owner_user_id": "u1", "is_traded": 0, "original_username": None,
             "pick_value": 10.0, "pool_value": 300.0, "source": "user"}])
    with patch.object(db, "engine", eng):
        yield eng
    eng.dispose()


def seed_deck(conn, job, served_at, rows):
    """rows: dicts with card_index, give, receive, partner (+ optional deck_impressions overrides
    and a `features` dict merged into features_json)."""
    for r in rows:
        features = {"partner_user_id": r.get("partner"), "basis": "value", **r.get("features", {})}
        row = {"impression_id": f"{job}-{r['card_index']}", "user_id": r.get("user_id", "u1"),
               "league_id": "L1", "deck_job_id": job, "card_index": r["card_index"],
               "propensity": 1.0, "served_at": served_at,
               "model_arm": r.get("model_arm", "current"),
               "assets_json": (json.dumps({"give": list(r["give"]), "receive": list(r["receive"])})
                               if r.get("with_assets", True) else None),
               "features_json": json.dumps(features)}
        for k in ("is_ghost", "source_like_impression_id", "trade_intent"):
            if k in r:
                row[k] = r[k]
        conn.execute(insert(db.deck_impressions_table).values(**row))


def deck_rows(trades, start=0, user_id="u1"):
    return [{"card_index": start + i, "partner": p, "give": g, "receive": r, "user_id": user_id}
            for i, (p, g, r) in enumerate(trades)]


def seed_current_deck(engine, job="J1", served_at=SERVED, trades=CURRENT, user_id="u1"):
    with engine.begin() as conn:
        seed_deck(conn, job, served_at, deck_rows(trades, user_id=user_id))


def stub_engine(trades):          # trades: [(partner, give_ids, receive_ids)]
    from backend.value_core.types import (CoreDiagnostics, DeckEntry, FairTrade,
                                          PipelineResult, ScoredTrade, Scores)
    calls = []

    def run(snapshot, request, core_cfg, rank_cfg, **kw):
        calls.append((snapshot, request, core_cfg, rank_cfg))
        entries = [DeckEntry(i, ScoredTrade(FairTrade(p, tuple(g), tuple(r), 1.0, 1.0, 1.0,
                                                      0.0, None, False, (0, 0)),
                                            Scores(.5, .5, .5, .5), {}), .5, ("Fair on value",))
                   for i, (p, g, r) in enumerate(trades)]
        return PipelineResult(entries, CoreDiagnostics(), 5)
    run.calls = calls
    return run


def inputs_and_catalog():
    with db.engine.connect() as conn:
        inputs = bench.read_league_inputs(conn, "L1", NOW.date())
    return inputs, bg.build_catalog(inputs)


def rows_of(table):
    with db.engine.connect() as conn:
        return conn.execute(select(table)).mappings().all()


def count(table):
    with db.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


def start_and_build(engine, trades=VALUE_CORE, seed=11, server=SERVER):
    out = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW, seed=seed)
    bg.build_session(session_id=out["session"]["session_id"], server=server,
                     engine=stub_engine(trades))
    return out["session"]["session_id"]


def check_neutral(trade):
    assert set(trade) == {"partner_name", "give", "receive"}
    for side in ("give", "receive"):
        assert trade[side], side
        for a in trade[side]:
            assert set(a) == NEUTRAL_KEYS
        keys = [(-(a["value"] or 0), a["name"], a["id"]) for a in trade[side]]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Neutral formatter and catalog
# ---------------------------------------------------------------------------

def test_neutral_trade_has_exact_keys_and_sorted_sides(engine):
    _, cat = inputs_and_catalog()
    # values: pick 700 > p3 (elo 1360 -> 497) > p2 (1340 -> 449); 2117 > p17 (1640 -> 2014) > p24 (None)
    trade = bg.neutral_trade("u3", ("p2", "p3", PLATFORM_PICK), ("p24", "p17", TRADED_PICK), cat)
    check_neutral(trade)
    assert trade["partner_name"] == "kim"                    # display_name NULL -> username
    assert [a["id"] for a in trade["give"]] == [PLATFORM_PICK, "p3", "p2"]
    assert [a["id"] for a in trade["receive"]] == [TRADED_PICK, "p17", "p24"]
    assert trade["receive"][2]["value"] is None and trade["receive"][0]["value"] == 2117


def test_neutral_trade_identical_for_both_arms(engine):
    _, cat = inputs_and_catalog()
    a = bg.neutral_trade("u2", ("p1", "p2"), ("p9",), cat)
    b = bg.neutral_trade("u2", ("p2", "p1"), ("p9",), cat)
    assert a == b
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # The formatter has no arm/provenance parameter at all.
    import inspect
    assert list(inspect.signature(bg.neutral_trade).parameters) == ["partner_id", "give", "receive",
                                                                     "catalog"]


def test_pick_label_and_null_fields(engine):
    _, cat = inputs_and_catalog()
    pick = cat.assets[TRADED_PICK]
    assert pick == {"name": "2027 1st (from Kim)", "position": "PICK", "nfl_team": None,
                    "age": None, "value": 2117}
    assert cat.assets[PLATFORM_PICK]["name"] == "2027 2nd"
    assert bg.pick_label({"season": 2028, "round": 4, "is_traded": 1, "original_username": ""}) == "2028 4th"
    assert USER_PICK not in cat.assets                       # source='user' is never platform
    assert TRADED_PICK in cat.holdings["u2"] and PLATFORM_PICK in cat.holdings["u1"]


def test_assigned_picks_join_the_catalog_when_the_engine_prices_them(engine, monkeypatch):
    """ESPN has no readable pick ownership, so its picks are source='user' rows, which the
    engine reads (source 'any') while picks.assign_tradeable is on. Grading reads the same
    rows, or every current-arm card holding one is dropped as unknown (prod 2026-10-07)."""
    from backend import feature_flags
    on = {"picks.assign_tradeable": False}
    monkeypatch.setattr(feature_flags, "is_enabled", lambda key: on.get(key, False))
    db._invalidate_contested("L1")
    inputs, seat, cat = bg._league_inputs("L1", "u1", NOW)
    assert seat == "u1" and USER_PICK not in cat.assets       # switch off: platform rows only
    on["picks.assign_tradeable"] = True
    inputs, _, cat = bg._league_inputs("L1", "u1", NOW)
    assert cat.assets[USER_PICK] == {"name": "2027 3rd", "position": "PICK", "nfl_team": None,
                                     "age": None, "value": 300}
    assert USER_PICK in cat.holdings["u1"]
    assert {TRADED_PICK, PLATFORM_PICK} <= set(cat.assets)    # platform rows still there
    assert [p["pick_id"] for p in inputs["picks"]] == sorted(p["pick_id"] for p in inputs["picks"])
    with engine.begin() as conn:                              # no assigned rows ⇒ bench read as-is
        conn.execute(db.draft_picks_table.delete().where(db.draft_picks_table.c.source == "user"))
    db._invalidate_contested("L1")
    inputs, _, _ = bg._league_inputs("L1", "u1", NOW)
    assert inputs == inputs_and_catalog()[0]


def test_catalog_values_come_from_history_and_pool(engine):
    _, cat = inputs_and_catalog()
    assert cat.assets["p1"]["value"] == round(elo_to_value(_elo("p1")))
    assert isinstance(cat.assets["p1"]["value"], int)
    assert cat.assets["p1"]["nfl_team"] == "T1" and cat.assets["p1"]["age"] == 23
    assert cat.assets["p24"]["value"] is None                # no player_value_history row
    assert cat.assets[TRADED_PICK]["value"] == round(2117.0)
    assert cat.partner_names == {"u1": "Me", "u2": "Jared", "u3": "kim"}
    assert cat.holdings["u1"] == frozenset(ROSTER["u1"]) | {PLATFORM_PICK}


# ---------------------------------------------------------------------------
# Current arm
# ---------------------------------------------------------------------------

def _needs_fresh_deck(exc, reason, usable=None):
    assert exc.code == "needs_fresh_deck" and exc.status == 409
    assert exc.detail["reason"] == reason
    assert exc.detail["min_cards"] == 10 and exc.detail["max_age_days"] == bg.MAX_DECK_AGE_DAYS
    if usable is not None:
        assert exc.detail["usable"] == usable


def test_select_current_refuses_missing_stale_and_too_few(engine):
    _, cat = inputs_and_catalog()
    kw = dict(viewer_id="u1", catalog=cat, now=NOW)
    with pytest.raises(bg.GradingError) as e:
        bg.select_current_cards(None, None, [], **kw)
    _needs_fresh_deck(e.value, "missing", 0)
    rows = [{"impression_id": f"i{i}", "card_index": i, "model_arm": "current",
             "assets_json": json.dumps({"give": g, "receive": r}),
             "features_json": json.dumps({"partner_user_id": p})}
            for i, (p, g, r) in enumerate(CURRENT)]
    with pytest.raises(bg.GradingError) as e:
        bg.select_current_cards("J", (NOW - timedelta(days=bg.MAX_DECK_AGE_DAYS, seconds=1)).isoformat(),
                                rows, **kw)
    _needs_fresh_deck(e.value, "stale")
    # exactly MAX_DECK_AGE_DAYS old is still fresh; 9 usable rows is too few
    with pytest.raises(bg.GradingError) as e:
        bg.select_current_cards("J", (NOW - timedelta(days=bg.MAX_DECK_AGE_DAYS)).isoformat(),
                                rows[:9], **kw)
    _needs_fresh_deck(e.value, "too_few", 9)
    cards, meta = bg.select_current_cards("J", SERVED, rows, **kw)
    assert len(cards) == 20 and meta["candidates"] == 20


def test_select_current_takes_first_20_then_drops_stale(engine):
    _, cat = inputs_and_catalog()
    trades = list(CURRENT)
    trades[3] = ("u2", ("p9",), ("p10",))        # give not held by the viewer -> stale
    trades[7] = ("u9", ("p1",), ("p9",))         # partner no longer a member -> stale
    trades += [TRADES[40], TRADES[41]]           # rows 20, 21: valid but beyond the first 20
    seed_current_deck(engine, trades=trades)
    job, served_at, rows = db.load_grading_legacy_deck("u1", "L1")
    assert job == "J1" and len(rows) == 22
    cards, meta = bg.select_current_cards(job, served_at, rows, viewer_id="u1", catalog=cat, now=NOW)
    assert len(cards) == 18
    assert meta["dropped_stale"] == 2 and meta["dropped_unknown"] == 0 and meta["candidates"] == 20
    assert all(c.provenance["card_index"] < 20 for c in cards)
    assert all(c.arm == "current" for c in cards)
    assert cards[0].provenance == {"impression_id": "J1-0", "card_index": 0, "model_arm": "current"}


def test_select_current_drops_standing_offers_and_duplicates(engine):
    _, cat = inputs_and_catalog()
    rows = deck_rows(CURRENT)
    rows[0]["features"] = {"standing_offer": True}                 # excluded before the slice
    rows[1]["give"] = ("p1", "p2")                                  # duplicate key pair …
    rows[2] = {"card_index": 2, "partner": rows[1]["partner"], "give": ("p2", "p1"),
               "receive": rows[1]["receive"]}                       # … in the other order
    rows[5]["give"] = ("ghost-player",)                             # unknown id
    with engine.begin() as conn:
        seed_deck(conn, "J1", SERVED, rows)
    job, served_at, loaded = db.load_grading_legacy_deck("u1", "L1")
    cards, meta = bg.select_current_cards(job, served_at, loaded, viewer_id="u1", catalog=cat, now=NOW)
    indexes = [c.provenance["card_index"] for c in cards]
    assert 0 not in indexes and 2 not in indexes and 5 not in indexes
    assert 1 in indexes                                             # the first duplicate wins
    assert meta["candidates"] == 19 and meta["dropped_unknown"] == 1 and meta["dropped_stale"] == 0
    assert len(cards) == 17


# ---------------------------------------------------------------------------
# Value-core arm
# ---------------------------------------------------------------------------

def test_run_value_core_feeds_bench_snapshot_with_default_config(engine):
    inputs, _ = inputs_and_catalog()
    server = bg.ServerInputs(
        lineup_slots=("QB", "RB", "RB", "WR", "WR", "TE", "FLEX"), max_players=12,
        standings={"u1": Standing(6, 2, 0, 980.0), "u2": Standing(4, 4, 0, 900.0),
                   "u3": Standing(1, 7, 0, 700.0)},
        completed_weeks=8, untouchable_ids=frozenset({"p1", "not-an-asset"}),
        not_interested_ids=frozenset({"p9", "p99"}))
    stub = stub_engine(VALUE_CORE)
    cards, meta = bg.run_value_core(inputs, seat="u1", server=server, engine=stub)
    snapshot, request, core_cfg, rank_cfg = stub.calls[0]
    assert core_cfg == CoreConfig() and rank_cfg == RankConfig()
    assert request.viewer_team_id == "u1"
    assert request.untouchable_ids == frozenset({"p1"})
    assert request.not_interested_ids == frozenset({"p9"})
    assert snapshot.rules.lineup_slots == server.lineup_slots
    assert snapshot.rules.max_players == server.max_players
    assert snapshot.teams["u1"].window.pf_index is not None
    assert len(cards) == 20 and all(c.arm == "value_core" for c in cards)
    assert cards[0].provenance == {"deck_position": 0, "reasons": ["Fair on value"]}
    assert meta["engine_version"] == "value-core-2" and meta["core"]["band"] == 0.2
    assert meta["pool"] == 20 and meta["elapsed_ms"] == 5 and meta["budget_exhausted"] is False
    assert meta["completed_weeks"] == 8 and meta["max_players"] == 12
    assert meta["lineup_slots"] == list(server.lineup_slots)


def test_run_value_core_too_few_and_failed(engine):
    inputs, _ = inputs_and_catalog()
    with pytest.raises(bg.GradingError) as e:
        bg.run_value_core(inputs, seat="u1", server=SERVER, engine=stub_engine(VALUE_CORE[:3]))
    assert (e.value.code, e.value.status) == ("value_core_too_few", 409)
    assert e.value.detail == {"usable": 3, "min_cards": 10}

    def boom(*a, **kw):
        raise RuntimeError("engine exploded")
    with pytest.raises(bg.GradingError) as e:
        bg.run_value_core(inputs, seat="u1", server=SERVER, engine=boom)
    assert (e.value.code, e.value.status) == ("value_core_failed", 503)
    assert e.value.detail == {}


# ---------------------------------------------------------------------------
# Merge and shuffle
# ---------------------------------------------------------------------------

def test_merge_shared_trade_one_card_both_arms():
    cur = bg.ArmCard("current", "u2", ("p1", "p2"), ("p9",), {"impression_id": "i0"})
    vc = bg.ArmCard("value_core", "u2", ("p2", "p1"), ("p9",), {"deck_position": 3})
    other = bg.ArmCard("value_core", "u3", ("p1",), ("p17",), {"deck_position": 4})
    merged = bg.merge_cards([cur, vc, other])
    assert len(merged) == 2
    assert set(merged[0]["arms"]) == {"current", "value_core"}
    assert merged[0]["arms"]["current"] == {"impression_id": "i0"}
    assert merged[0]["give"] == ("p1", "p2")                 # the first occurrence's sides
    assert set(merged[1]["arms"]) == {"value_core"}


def test_shuffle_is_deterministic_for_a_seed():
    order = [{"n": i} for i in range(30)]
    assert bg.shuffle_cards(order, 42) == bg.shuffle_cards(order, 42)
    assert bg.shuffle_cards(order, 42) != bg.shuffle_cards(order, 43)
    assert sorted(bg.shuffle_cards(order, 42), key=lambda m: m["n"]) == order
    assert order == [{"n": i} for i in range(30)]           # input untouched


# ---------------------------------------------------------------------------
# start_session / build_session (specs §3.3 split)
# ---------------------------------------------------------------------------

def test_start_session_inserts_building_row_and_runs_no_value_core(engine, monkeypatch):
    from backend.value_core import pipeline
    monkeypatch.setattr(pipeline, "run", lambda *a, **kw: pytest.fail("value core ran in start_session"))
    seed_current_deck(engine)
    out = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW, seed=7)
    assert out["resumed"] is False and out["needs_build"] is True
    view = out["session"]
    assert set(view) == {"session_id", "league_id", "status", "created_at", "completed_at",
                         "progress", "error"}
    assert view["status"] == "building" and view["league_id"] == "L1"
    assert view["progress"] == {"answered": 0, "total": 0} and view["error"] is None
    assert view["completed_at"] is None and view["created_at"] == NOW.isoformat()
    assert re.fullmatch(r"\d{18}", view["session_id"])
    (row,) = rows_of(db.grading_sessions_table)
    assert row["seed"] == "7" and row["counts_json"] == "{}" and row["error_json"] is None
    source = json.loads(row["source_json"])
    assert source["version"] == "blind-grading-1" and source["seat"] == "u1"
    assert source["scoring_format"] == "1qb_ppr"
    assert source["current"]["deck_job_id"] == "J1" and source["current"]["served_at"] == SERVED
    assert len(source["current"]["cards"]) == 20
    assert "value_core" not in source
    assert count(db.grading_cards_table) == 0


def test_start_session_refuses_unsynced_league_and_foreign_seat(engine):
    seed_current_deck(engine)
    with pytest.raises(bg.GradingError) as e:
        bg.start_session(user_id="u1", league_user_id="u1", league_id="L-none", now=NOW)
    assert (e.value.code, e.value.status) == ("league_not_synced", 409)
    with pytest.raises(bg.GradingError) as e:
        bg.start_session(user_id="u1", league_user_id="u9", league_id="L1", now=NOW)
    assert (e.value.code, e.value.status) == ("league_not_synced", 409)
    assert count(db.grading_sessions_table) == 0


def test_start_session_needs_fresh_deck_writes_nothing(engine):
    with pytest.raises(bg.GradingError) as e:
        bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)
    _needs_fresh_deck(e.value, "missing", 0)
    assert count(db.grading_sessions_table) == 0


def test_build_session_end_to_end(engine):
    seed_current_deck(engine)
    sid = start_and_build(engine, seed=11)
    (session,) = rows_of(db.grading_sessions_table)
    assert session["status"] == "open" and session["error_json"] is None
    cards = rows_of(db.grading_cards_table)
    assert len(cards) == 39                                   # 20 + 20 - 1 shared
    assert sorted(c["position"] for c in cards) == list(range(1, 40))
    ids = [c["card_id"] for c in cards]
    assert all(re.fullmatch(r"\d{18}", i) for i in ids) and len(set(ids)) == 39
    assert all(c["user_id"] == "u1" and c["session_id"] == sid for c in cards)
    assert all(c["grade"] is None and c["skipped"] == 0 and c["tags_json"] == "[]" for c in cards)
    arm_sets = []
    for c in cards:
        check_neutral(json.loads(c["trade_json"]))
        arms = json.loads(c["arms_json"])
        assert set(arms) <= set(bg.ARMS) and arms
        arm_sets.append(frozenset(arms))
    assert arm_sets.count(frozenset(bg.ARMS)) == 1
    assert arm_sets.count(frozenset({"current"})) == 19
    assert arm_sets.count(frozenset({"value_core"})) == 19
    counts = json.loads(session["counts_json"])
    assert counts == {"total": 39, "current": 20, "value_core": 20, "shared": 1,
                      "current_candidates": 20, "current_dropped_stale": 0,
                      "current_dropped_unknown": 0, "value_core_pool": 20}
    source = json.loads(session["source_json"])
    assert source["current"] == {"deck_job_id": "J1", "served_at": SERVED}
    assert source["value_core"]["core"]["band"] == 0.2
    assert source["value_core"]["engine_version"] == "value-core-2"
    assert source["seat"] == "u1" and source["version"] == "blind-grading-1"
    view = bg.current_session(user_id="u1", league_id="L1")["session"]
    assert view["status"] == "open" and view["progress"] == {"answered": 0, "total": 39}
    # The shared trade is served once, as one card.
    shared = [json.loads(c["trade_json"]) for c in cards if json.loads(c["arms_json"]).keys() >= set(bg.ARMS)]
    p, g, r = TRADES[19]
    assert shared[0]["partner_name"] == ("Jared" if p == "u2" else "kim")
    assert [a["id"] for a in shared[0]["give"]] == list(g)
    assert [a["id"] for a in shared[0]["receive"]] == list(r)


def test_build_session_shuffle_follows_the_stored_seed(engine):
    seed_current_deck(engine)
    orders = []
    for seed in (1, 1, 2):
        sid = start_and_build(engine, seed=seed)
        cards = db.load_grading_cards(sid)
        orders.append([c["trade_json"] for c in cards])
        # finish it so the next start_session opens a fresh one
        for c in cards:
            bg.answer_card(user_id="u1", card_id=c["card_id"], body={"skip": True}, now=NOW)
    assert orders[0] == orders[1] and orders[0] != orders[2]
    arms = [set(json.loads(c["arms_json"])) for c in db.load_grading_cards(sid)]
    assert arms != sorted(arms, key=lambda s: s != {"current"})   # not all-current-then-value-core


def test_build_session_failure_marks_failed_never_raises(engine):
    seed_current_deck(engine)
    # 1. the engine raises -> value_core_failed
    sid = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)["session"]["session_id"]

    def boom(*a, **kw):
        raise RuntimeError("engine exploded")
    bg.build_session(session_id=sid, server=SERVER, engine=boom)
    row = db.load_grading_session(sid)
    assert row["status"] == "failed" and json.loads(row["error_json"]) == {"code": "value_core_failed"}
    assert count(db.grading_cards_table) == 0
    view = bg.current_session(user_id="u1", league_id="L1")["session"]
    assert view["status"] == "failed" and view["error"] == {"code": "value_core_failed"}
    assert view["progress"] == {"answered": 0, "total": 0}
    # 2. too few value-core cards -> value_core_too_few with its detail
    sid2 = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)["session"]["session_id"]
    assert sid2 != sid
    bg.build_session(session_id=sid2, server=SERVER, engine=stub_engine(VALUE_CORE[:4]))
    assert json.loads(db.load_grading_session(sid2)["error_json"]) == {
        "code": "value_core_too_few", "usable": 4, "min_cards": 10}
    # 3. the persist step itself fails -> still 'failed', still no raise
    sid3 = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)["session"]["session_id"]
    with patch.object(db, "finish_grading_session_build", side_effect=RuntimeError("db down")):
        bg.build_session(session_id=sid3, server=SERVER, engine=stub_engine(VALUE_CORE))
    assert db.load_grading_session(sid3)["status"] == "failed"
    # 4. even marking failed blows up -> swallowed
    sid4 = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)["session"]["session_id"]
    with patch.object(db, "finish_grading_session_build", side_effect=RuntimeError("db down")), \
            patch.object(db, "fail_grading_session", side_effect=RuntimeError("still down")):
        bg.build_session(session_id=sid4, server=SERVER, engine=stub_engine(VALUE_CORE))
    assert db.load_grading_session(sid4)["status"] == "building"
    # 5. an unknown session id is a no-op
    bg.build_session(session_id="000000000000000000", server=SERVER, engine=boom)


def test_build_session_is_idempotent_for_non_building_sessions(engine):
    seed_current_deck(engine)
    sid = start_and_build(engine)
    before = rows_of(db.grading_cards_table)
    stub = stub_engine(VALUE_CORE)
    bg.build_session(session_id=sid, server=SERVER, engine=stub)          # open: left alone
    assert stub.calls == [] and rows_of(db.grading_cards_table) == before
    assert db.load_grading_session(sid)["status"] == "open"


def test_start_session_resumes_open_session(engine):
    seed_current_deck(engine)
    sid = start_and_build(engine)
    out = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)
    assert out["resumed"] is True and out["needs_build"] is False
    assert out["session"]["session_id"] == sid and out["session"]["status"] == "open"
    assert count(db.grading_sessions_table) == 1 and count(db.grading_cards_table) == 39
    # Another grader's session in the same league is not the caller's.
    seed_current_deck(engine, job="J2", trades=trades_for("u2")[:20], user_id="u2")
    other = bg.start_session(user_id="u2", league_user_id="u2", league_id="L1", now=NOW)
    assert other["resumed"] is False and other["session"]["session_id"] != sid
    assert count(db.grading_sessions_table) == 2


def test_start_session_resumes_building_session_and_flags_needs_build(engine):
    seed_current_deck(engine)
    first = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)
    second = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)
    assert second["resumed"] is True and second["needs_build"] is True
    assert second["session"]["session_id"] == first["session"]["session_id"]
    assert count(db.grading_sessions_table) == 1
    # Two builds of the same building row: the loser writes nothing.
    sid = first["session"]["session_id"]
    bg.build_session(session_id=sid, server=SERVER, engine=stub_engine(VALUE_CORE))
    bg.build_session(session_id=sid, server=SERVER, engine=stub_engine(VALUE_CORE))
    assert count(db.grading_cards_table) == 39


def test_failed_session_is_not_resumed(engine):
    seed_current_deck(engine)
    failed = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1", now=NOW)
    bg.build_session(session_id=failed["session"]["session_id"], server=SERVER,
                     engine=stub_engine(VALUE_CORE[:2]))
    assert db.load_grading_session(failed["session"]["session_id"])["status"] == "failed"
    fresh = bg.start_session(user_id="u1", league_user_id="u1", league_id="L1",
                             now=NOW + timedelta(seconds=1))
    assert fresh["resumed"] is False and fresh["needs_build"] is True
    assert fresh["session"]["session_id"] != failed["session"]["session_id"]
    assert fresh["session"]["status"] == "building"
    assert count(db.grading_sessions_table) == 2
    # current_session shows the newest (building), not the failed one …
    assert bg.current_session(user_id="u1", league_id="L1")["session"]["session_id"] == \
        fresh["session"]["session_id"]
    # … and never a completed one.
    bg.build_session(session_id=fresh["session"]["session_id"], server=SERVER,
                     engine=stub_engine(VALUE_CORE))
    for c in db.load_grading_cards(fresh["session"]["session_id"]):
        bg.answer_card(user_id="u1", card_id=c["card_id"], body={"grade": 3}, now=NOW)
    assert bg.current_session(user_id="u1", league_id="L1") == {"session": None}


def test_build_session_writes_no_engine_tables(engine, monkeypatch):
    seed_current_deck(engine)
    engine_tables = (db.deck_impressions_table, db.trade_impressions_table,
                     db.trade_decisions_table, db.swipe_decisions_table,
                     db.deck_candidate_sets_table)

    def others():       # every table but the two grading ones
        return {name: count(t) for name, t in db.metadata.tables.items()
                if name not in ("grading_sessions", "grading_cards")}
    before, before_all = [count(t) for t in engine_tables], others()
    sid = start_and_build(engine)
    assert db.load_grading_session(sid)["status"] == "open"
    assert [count(t) for t in engine_tables] == before
    assert others() == before_all
    for c in db.load_grading_cards(sid)[:5]:
        bg.answer_card(user_id="u1", card_id=c["card_id"], body={"grade": 4, "tags": ["overpay"]}, now=NOW)
    assert others() == before_all
    # The TradeCard registry is per TradeService instance (trade_service._trade_cards is not a
    # module global), so the engine-side check is static: the module never names it.
    src = (REPO / "backend" / "blind_grading.py").read_text()
    for forbidden in ("_trade_cards", "TradeService", "log_trade_impressions",
                      "_log_deck_signal_impressions", "record_event", "RankingService"):
        assert forbidden not in src, forbidden


def test_module_never_imports_server_or_tools():
    code = ("import sys, backend.blind_grading; "
            "assert 'backend.server' not in sys.modules, 'server imported'; "
            "assert 'backend.tools.prod_analytics' not in sys.modules, 'tools imported'; "
            "assert 'backend.tools' not in sys.modules, 'tools pkg imported'; "
            "print('clean')")
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "clean"
    src = (REPO / "backend" / "blind_grading.py").read_text().splitlines()
    imports = [l for l in src if re.match(r"\s*(from|import)\s", l)]
    assert not [l for l in imports if re.search(r"\bserver\b|\btools\b", l)], imports


# ---------------------------------------------------------------------------
# Scoring and answers
# ---------------------------------------------------------------------------

def test_summarize_matches_blind_grade_score():
    from backend.eval.blind_grade import _score
    graded = [(4, ["overpay"]), (2, []), (5, ["overpay", "too_small"])]
    assert bg.summarize(graded) == _score(graded)
    assert bg.summarize(graded) == {"n": 3, "mean": 3.6667, "share_ge_4": 0.6667,
                                    "tag_counts": {"overpay": 2, "too_small": 1}}
    assert bg.summarize([]) == _score([]) == {"n": 0, "mean": None, "share_ge_4": None,
                                              "tag_counts": {}}


def test_arm_summaries_shared_card_counts_for_both_arms():
    def card(arms, grade=None, skipped=0, tags=()):
        return {"arms_json": json.dumps(arms), "grade": grade, "skipped": skipped,
                "tags_json": json.dumps(list(tags))}
    cards = [card({"current": {}, "value_core": {}}, grade=5, tags=["overpay"]),
             card({"current": {}}, grade=3),
             card({"value_core": {}}, skipped=1),
             card({"value_core": {}})]                        # unanswered
    arms, shared = bg.arm_summaries(cards)
    assert shared == 1
    assert arms["current"] == {"cards": 2, "skipped": 0, "n": 2, "mean": 4.0, "share_ge_4": 0.5,
                               "tag_counts": {"overpay": 1}}
    assert arms["value_core"] == {"cards": 3, "skipped": 1, "n": 1, "mean": 5.0, "share_ge_4": 1.0,
                                  "tag_counts": {"overpay": 1}}
    assert set(arms) == set(bg.ARMS)


@pytest.mark.parametrize("body,expected", [
    ({"grade": 4}, (4, False, [])),
    ({"grade": 1, "tags": ["overpay", "overpay"]}, (1, False, ["overpay"])),
    ({"grade": 5, "tags": ["too_small", "overpay"]}, (5, False, ["overpay", "too_small"])),
    ({"skip": True}, (None, True, [])),
    ({"skip": True, "tags": []}, (None, True, [])),
    ({"grade": 3, "ignored": "key"}, (3, False, [])),
])
def test_validate_answer_valid(body, expected):
    assert bg.validate_answer(body) == expected


@pytest.mark.parametrize("body", [
    None, [], {}, {"grade": 0}, {"grade": 6}, {"grade": "4"}, {"grade": True},
    {"grade": 3, "skip": True}, {"skip": "yes"}, {"grade": 3, "tags": ["bogus"]},
    {"skip": True, "tags": ["overpay"]}, {"grade": 3, "tags": "overpay"},
    {"grade": 3, "tags": [1]}, {"grade": 2.0}, {"skip": False},
])
def test_validate_answer_invalid(body):
    with pytest.raises(bg.GradingError) as e:
        bg.validate_answer(body)
    assert (e.value.code, e.value.status) == ("invalid_body", 400)
    assert isinstance(e.value.detail["message"], str) and e.value.detail["message"]


def test_answer_card_regrade_then_complete_then_reject(engine):
    seed_current_deck(engine)
    sid = start_and_build(engine)
    nxt = bg.next_card(user_id="u1", session_id=sid)
    assert nxt["done"] is False and nxt["progress"] == {"answered": 0, "total": 39}
    assert set(nxt["card"]) == {"card_id", "position", "trade"} and nxt["card"]["position"] == 1
    check_neutral(nxt["card"]["trade"])
    first = nxt["card"]["card_id"]
    res = bg.answer_card(user_id="u1", card_id=first, body={"grade": 2}, now=NOW)
    assert res == {"card_id": first, "session_id": sid, "session_status": "open",
                   "progress": {"answered": 1, "total": 39}}
    # a re-grade overwrites and does not double count
    res = bg.answer_card(user_id="u1", card_id=first, body={"grade": 5, "tags": ["overpay"]},
                         now=NOW + timedelta(seconds=5))
    assert res["progress"] == {"answered": 1, "total": 39}
    card = {c["card_id"]: c for c in db.load_grading_cards(sid)}[first]
    assert (card["grade"], card["skipped"], card["tags_json"]) == (5, 0, '["overpay"]')
    assert card["graded_at"] == (NOW + timedelta(seconds=5)).isoformat()
    # next moves on to position 2
    assert bg.next_card(user_id="u1", session_id=sid)["card"]["position"] == 2
    # a skip clears the grade and tags
    bg.answer_card(user_id="u1", card_id=first, body={"skip": True}, now=NOW)
    card = {c["card_id"]: c for c in db.load_grading_cards(sid)}[first]
    assert (card["grade"], card["skipped"], card["tags_json"]) == (None, 1, "[]")
    # foreign / unknown card and session
    with pytest.raises(bg.GradingError) as e:
        bg.answer_card(user_id="u2", card_id=first, body={"grade": 3})
    assert (e.value.code, e.value.status) == ("not_found", 404)
    with pytest.raises(bg.GradingError) as e:
        bg.next_card(user_id="u2", session_id=sid)
    assert (e.value.code, e.value.status) == ("not_found", 404)
    with pytest.raises(bg.GradingError) as e:
        bg.answer_card(user_id="u1", card_id="123456789012345678", body={"grade": 3})
    assert e.value.code == "not_found"
    # invalid body is rejected before any write
    with pytest.raises(bg.GradingError) as e:
        bg.answer_card(user_id="u1", card_id=first, body={"grade": 9})
    assert e.value.code == "invalid_body"
    # answer the rest; the last answer completes the session
    done_at = NOW + timedelta(minutes=10)
    remaining = [c for c in db.load_grading_cards(sid) if c["grade"] is None and not c["skipped"]]
    assert len(remaining) == 38
    for i, c in enumerate(remaining):
        res = bg.answer_card(user_id="u1", card_id=c["card_id"],
                             body={"grade": 1 + i % 5, "tags": ["junk_filler"]} if i % 3 else {"skip": True},
                             now=done_at)
    assert res["session_status"] == "completed" and res["progress"] == {"answered": 39, "total": 39}
    row = db.load_grading_session(sid)
    assert row["status"] == "completed" and row["completed_at"] == done_at.isoformat()
    assert bg.next_card(user_id="u1", session_id=sid) == {
        "done": True, "session_id": sid, "progress": {"answered": 39, "total": 39}}
    with pytest.raises(bg.GradingError) as e:
        bg.answer_card(user_id="u1", card_id=first, body={"grade": 3})
    assert (e.value.code, e.value.status) == ("session_completed", 409)


def test_results_and_report(engine):
    seed_current_deck(engine)
    sid = start_and_build(engine)
    with pytest.raises(bg.GradingError) as e:
        bg.results(user_id="u1", session_id=sid)
    assert (e.value.code, e.value.status) == ("session_incomplete", 409)
    assert e.value.detail == {"progress": {"answered": 0, "total": 39}}
    with pytest.raises(bg.GradingError) as e:
        bg.results(user_id="u2", session_id=sid)
    assert e.value.code == "not_found"
    # Grade by arm (reading arms_json directly, as results() may): current 4s, value core 2s,
    # the shared card 5, two value-core skips.
    cards = db.load_grading_cards(sid)
    vc_only = [c for c in cards if set(json.loads(c["arms_json"])) == {"value_core"}]
    for c in cards:
        arms = set(json.loads(c["arms_json"]))
        if arms == set(bg.ARMS):
            body = {"grade": 5, "tags": ["overpay"]}
        elif arms == {"current"}:
            body = {"grade": 4, "tags": ["overpay", "too_small"]}
        elif c in vc_only[:2]:
            body = {"skip": True}
        else:
            body = {"grade": 2}
        bg.answer_card(user_id="u1", card_id=c["card_id"], body=body, now=NOW)
    res = bg.results(user_id="u1", session_id=sid)
    assert set(res) == {"session_id", "league_id", "completed_at", "total", "shared",
                        "target_mean", "arms"}
    assert res["session_id"] == sid and res["league_id"] == "L1"
    assert res["completed_at"] == NOW.isoformat() and res["total"] == 39 and res["shared"] == 1
    assert res["target_mean"] == 4.0
    cur, vc = res["arms"]["current"], res["arms"]["value_core"]
    assert cur == {"cards": 20, "skipped": 0, "n": 20, "mean": 4.05, "share_ge_4": 1.0,
                   "tag_counts": {"overpay": 20, "too_small": 19}}
    assert vc == {"cards": 20, "skipped": 2, "n": 18, "mean": round((17 * 2 + 5) / 18, 4),
                  "share_ge_4": round(1 / 18, 4), "tag_counts": {"overpay": 1}}
    # Second grader with an open (incomplete) session.
    seed_current_deck(engine, job="J2", trades=trades_for("u2")[:20], user_id="u2")
    other = bg.start_session(user_id="u2", league_user_id="u2", league_id="L1",
                             now=NOW + timedelta(days=1))
    bg.build_session(session_id=other["session"]["session_id"], server=SERVER,
                     engine=stub_engine(trades_for("u2")[19:39]))
    rep = bg.report()
    assert set(rep) == {"generated_at", "version", "target_mean", "filters", "overall",
                        "by_grader", "sessions"}
    assert rep["version"] == "blind-grading-1" and rep["target_mean"] == 4.0
    assert rep["filters"] == {"since": None, "include_open": False}
    assert [s["session_id"] for s in rep["sessions"]] == [sid]
    s = rep["sessions"][0]
    assert s["status"] == "completed" and s["user_id"] == "u1" and s["league_id"] == "L1"
    assert s["counts"]["shared"] == 1 and s["counts"]["current_candidates"] == 20
    assert s["source"]["current"]["deck_job_id"] == "J1"
    assert s["source"]["value_core"]["core"]["band"] == 0.2
    assert s["arms"] == res["arms"]
    assert s["delta_mean"] == round(vc["mean"] - cur["mean"], 4)
    assert rep["overall"] == {"sessions": 1, "graders": 1, "cards": 39, "shared": 1,
                              "arms": res["arms"], "delta_mean": s["delta_mean"]}
    assert rep["by_grader"] == [{"user_id": "u1", "sessions": 1, "arms": res["arms"],
                                 "delta_mean": s["delta_mean"]}]
    open_rep = bg.report(include_open=True)
    assert [s["status"] for s in open_rep["sessions"]] == ["completed", "open"]
    assert open_rep["overall"]["sessions"] == 2 and open_rep["overall"]["graders"] == 2
    assert open_rep["overall"]["cards"] == 78
    assert [g["user_id"] for g in open_rep["by_grader"]] == ["u1", "u2"]
    assert open_rep["by_grader"][1]["delta_mean"] is None     # nothing graded yet
    assert open_rep["filters"] == {"since": None, "include_open": True}
    assert bg.report(since="2026-10-03", include_open=True)["overall"]["sessions"] == 1
    assert bg.report(since="2026-10-02")["overall"]["sessions"] == 1
    assert bg.report(since="2026-10-03")["overall"] == {
        "sessions": 0, "graders": 0, "cards": 0, "shared": 0, "delta_mean": None,
        "arms": {"current": {"cards": 0, "skipped": 0, "n": 0, "mean": None, "share_ge_4": None,
                             "tag_counts": {}},
                 "value_core": {"cards": 0, "skipped": 0, "n": 0, "mean": None,
                                "share_ge_4": None, "tag_counts": {}}}}
    with pytest.raises(bg.GradingError) as e:
        bg.report(since="bad")
    assert (e.value.code, e.value.status) == ("invalid_since", 400)


def test_pregenerate_starts_a_session_per_fresh_candidate(engine):
    """Operator 2026-10-05: one Calibration deck per user with a fresh enough deck. Only
    members with a qualifying deck inside MAX_DECK_AGE_DAYS are candidates; a re-run
    resumes instead of duplicating."""
    seed_current_deck(engine)                                      # u1 in L1, served 1 day ago
    seed_current_deck(engine, job="J9", user_id="u2",
                      served_at=(NOW - timedelta(days=bg.MAX_DECK_AGE_DAYS + 1)).isoformat())
    out = bg.pregenerate(now=NOW)
    assert out["candidates"] == 1 and out["skipped"] == {}
    assert [(j["user_id"], j["league_id"]) for j in out["to_build"]] == [("u1", "L1")]
    again = bg.pregenerate(now=NOW)                                # still building: re-kicked
    assert [j["session_id"] for j in again["to_build"]] == [out["to_build"][0]["session_id"]]


def test_retire_unanswered_only_retires_untouched_sessions(engine):
    """Targeted rebuild (operator 2026-10-09): an open session nobody has answered is retired
    as failed/superseded and the next start builds a fresh one; one answered card keeps it."""
    seed_current_deck(engine)
    sid = start_and_build(engine)
    assert bg.retire_unanswered(user_id="u1", league_id="L1") == sid
    row = db.load_grading_session(sid)
    assert row["status"] == "failed" and json.loads(row["error_json"]) == {"code": "superseded"}
    assert bg.retire_unanswered(user_id="u1", league_id="L1") is None      # nothing open now
    fresh = start_and_build(engine, seed=12)
    assert fresh != sid and db.load_grading_session(fresh)["status"] == "open"
    card = db.load_next_grading_card(fresh)
    bg.answer_card(user_id="u1", card_id=card["card_id"], body={"grade": 4})
    assert bg.retire_unanswered(user_id="u1", league_id="L1") is None      # answered: kept
    assert db.load_grading_session(fresh)["status"] == "open"


def test_add_fit_arms_folds_blind_and_keeps_answered_cards(engine, monkeypatch):
    """Operator 2026-10-09: fold the fit arms into an OPEN session. Answered cards keep their
    positions; unanswered + new cards are re-shuffled into the rest; a fit card equal to an
    existing trade is merged into it (arm added); two fit arms producing the same new trade
    share one card; idempotent; a session that is not open is left alone."""
    from backend import fit_engine as fe

    seed_current_deck(engine)
    sid = start_and_build(engine)                                  # 39 cards, positions 1..39
    first = [db.load_next_grading_card(sid) for _ in range(1)][0]
    bg.answer_card(user_id="u1", card_id=first["card_id"], body={"grade": 5})
    second = db.load_next_grading_card(sid)
    bg.answer_card(user_id="u1", card_id=second["card_id"], body={"skip": True})
    answered = {first["card_id"]: first["position"], second["card_id"]: second["position"]}

    extra = trades_for("u1")[40:43]
    ft = lambda t: fe.FitTrade(t[0], tuple(t[1]), tuple(t[2]), 0.2, 0.1, 0.1)
    produced = {"fit_a": [ft(CURRENT[0]), ft(extra[0]), ft(extra[1])],
                "fit_b": [ft(extra[0]), ft(extra[2])]}
    monkeypatch.setattr(fe, "generate", lambda snap, req, scorer: (produced[scorer.arm], {"stub": 1}))
    monkeypatch.setattr(fe, "assemble", lambda trades, snap, size=fe.DECK_SIZE: list(trades))

    out = bg.add_fit_arms(session_id=sid, server=SERVER, ros_points={}, ros_meta={"weeks": 13}, now=NOW)
    assert out == {"status": "added", "inserted": 3, "merged": 1, "total": 42, "fit_a": 3, "fit_b": 2}
    cards = db.load_grading_cards(sid)
    assert sorted(c["position"] for c in cards) == list(range(1, 43))
    assert {c["card_id"]: c["position"] for c in cards if c["card_id"] in answered} == answered
    by_trade = {}
    for c in cards:
        t = json.loads(c["trade_json"])
        by_trade[(frozenset(a["id"] for a in t["give"]), frozenset(a["id"] for a in t["receive"]))] = c
    key = lambda t: (frozenset(t[1]), frozenset(t[2]))
    assert set(json.loads(by_trade[key(CURRENT[0])]["arms_json"])) == {"current", "fit_a"}
    assert set(json.loads(by_trade[key(extra[0])]["arms_json"])) == {"fit_a", "fit_b"}
    assert set(json.loads(by_trade[key(extra[2])]["arms_json"])) == {"fit_b"}
    assert NEUTRAL_KEYS >= set(json.loads(by_trade[key(extra[2])]["trade_json"])["give"][0])
    row = db.load_grading_session(sid)
    source, counts = json.loads(row["source_json"]), json.loads(row["counts_json"])
    assert source["fit_a"]["version"] == fe.VERSIONS["fit_a"] and source["fit_b"]["ros"] == {"weeks": 13}
    assert (counts["total"], counts["fit_a"], counts["fit_b"], counts["fit_merged"]) == (42, 3, 2, 1)
    arms, _ = bg.arm_summaries(cards)
    assert list(arms) == ["current", "value_core", "fit_a", "fit_b"]
    assert (arms["fit_a"]["cards"], arms["fit_a"]["n"], arms["fit_b"]["cards"]) == (3, 0, 2)
    assert db.grading_progress(sid) == {"answered": 2, "total": 42}
    # Idempotent, and never on a session that is not open.
    assert bg.add_fit_arms(session_id=sid, server=SERVER, ros_points={}, now=NOW)["reason"] == "already_added"
    assert db.retire_grading_session(sid, "{}") is False                  # answered: not retirable
    assert bg.add_fit_arms(session_id="nope", server=SERVER, ros_points={}, now=NOW)["reason"] == "not_open"


def test_fold_aborts_when_a_moving_card_was_answered(engine):
    """The guard: a card the fold would move that got answered meanwhile -> nothing written."""
    seed_current_deck(engine)
    sid = start_and_build(engine)
    card = db.load_next_grading_card(sid)
    bg.answer_card(user_id="u1", card_id=card["card_id"], body={"grade": 2})
    before = sorted((c["card_id"], c["position"]) for c in db.load_grading_cards(sid))
    assert db.fold_grading_cards(sid, inserts=[], positions={card["card_id"]: 39},
                                 arms_updates={}, counts_json="{}", source_json="{}") is False
    assert sorted((c["card_id"], c["position"]) for c in db.load_grading_cards(sid)) == before
    assert json.loads(db.load_grading_session(sid)["counts_json"]) != {}
