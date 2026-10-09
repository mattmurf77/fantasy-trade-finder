"""Calibration (in-app blind grading) — end-to-end over the REAL service.

docs/plans/blind-grading/specs.md §5.2 (package P2, INTEGRATION-ONLY: it needs
P1's blind_grading bodies and the two grading tables, so it is excluded from
P2's isolated run and lives in the lead's §6 checklist). Routes, gate, service
and database run together on an in-memory SQLite seeded with the §5 common
seed; only the value core itself (backend.value_core.pipeline.run) is replaced
by the §5 stub engine, and every Sleeper-touching server helper is stubbed.

Covered:
  - blinding (G1): no response body before `results` names an arm, an engine,
    a seed, provenance or any impression / trade id, and every served card is
    exactly a NeutralTrade;
  - the shared trade (same key from both arms) is served once;
  - grading writes no engine table and touches no trade cards;
  - the shuffle interleaves the arms;
  - stopping the overlay kills the routes mid-session but not the report.

Clock: the route does not inject `now`, so the deck is served relative to the
real clock (one day ago) — a fixed date would make this file rot after the
7-day freshness window.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from itertools import combinations, cycle
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, insert, select

import backend.blind_grading as bg
import backend.database as db
import backend.experiments as experiments
import backend.server as server
import backend.value_core.pipeline as vc_pipeline

TOKEN = "grading-e2e-sess-tok"
USER = "u1"
LEAGUE = "L1"
JOB = "J"
AUTH = {"X-Session-Token": TOKEN}
SESSIONS = "/api/grading/sessions"
CURRENT = f"/api/grading/sessions/current?league_id={LEAGUE}"
REPORT = "/api/admin/grading/report"
CRON = "e2e-cron-secret"

NOW = datetime.now(timezone.utc)
SERVED_AT = (NOW - timedelta(days=1)).isoformat()
VALUE_DATE = (NOW - timedelta(days=1)).date().isoformat()

OVERLAY = ({"calibration_rollout": "treatment"},
           {"calibration_rollout": {"flags": {"grading.blind": True}}})
NO_OVERLAY = ({}, {})

FORBIDDEN_KEYS = {"arm", "arms", "arms_json", "model_arm", "reasons", "engine", "seed", "source",
                  "source_json", "counts", "counts_json", "impression_id", "deck_job_id",
                  "trade_id", "trade_concept_id", "basis", "lane", "scores", "priority",
                  "policy_variant", "valuation_json"}
FORBIDDEN_VALUES = {"current", "value_core", "value-core-1", "value-core-2", "legacy", "bakeoff", "gen_v2",
                    "baseline"}
TRADE_KEYS = {"partner_name", "give", "receive"}
ASSET_KEYS = {"id", "name", "position", "nfl_team", "age", "value"}

# ---------------------------------------------------------------------------
# the §5 common seed
# ---------------------------------------------------------------------------

POSITIONS = ("QB", "RB", "WR", "TE")
TEAMS = ("KC", "ATL", "SF", "DAL", "BUF", "MIA", "PHI", "DET")
MEMBERS = {"u1": ("me", "Me"), "u2": ("jared", "Jared"), "u3": ("kim", "Kim")}
ROSTERS = {uid: [f"p{n:02d}" for n in range(8 * i + 1, 8 * i + 9)]
           for i, uid in enumerate(MEMBERS)}
# 20 qualifying current-engine cards: 1-for-1s, ten per partner, distinct keys.
PAIRS = [(g, r) for g in range(8) for r in range(8)][:10]
CURRENT_CARDS = [(partner, [ROSTERS["u1"][g]], [ROSTERS[partner][r]])
                 for partner in ("u2", "u3") for g, r in PAIRS]
# 20 value-core trades: the first EQUALS current card 0 (the shared card); the
# rest are 2-for-1s with distinct give pairs, so no other key collides.
VC_TRADES = [CURRENT_CARDS[0]] + [
    (partner, [ROSTERS["u1"][a], ROSTERS["u1"][b]], [ROSTERS[partner][k % 8]])
    for k, ((a, b), partner) in enumerate(zip(list(combinations(range(8), 2))[:19],
                                              cycle(("u2", "u3"))))]
SHARED = CURRENT_CARDS[0]


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


def seed_deck(conn, job: str, served_at: str, rows) -> None:
    """rows: [(card_index, partner, give_ids, receive_ids)] → qualifying deck_impressions."""
    conn.execute(insert(db.deck_impressions_table), [
        {"impression_id": f"imp-{job}-{idx:02d}", "user_id": USER, "league_id": LEAGUE,
         "deck_job_id": job, "card_index": idx, "trade_hash": f"h{idx}",
         "features_json": json.dumps({"partner_user_id": partner, "basis": "value"}),
         "assets_json": json.dumps({"give": give, "receive": receive}),
         "propensity": 1.0, "served_at": served_at, "is_ghost": 0, "model_arm": "current"}
        for idx, partner, give, receive in rows])


def _seed(eng) -> None:
    with eng.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=LEAGUE, user_id=USER, name="Grading League", season="2026",
            platform="sleeper", default_scoring="1qb_ppr"))
        conn.execute(insert(db.league_members_table), [
            {"league_id": LEAGUE, "user_id": uid, "username": uname, "display_name": dname,
             "roster_data": json.dumps(ROSTERS[uid])}
            for uid, (uname, dname) in MEMBERS.items()])
        players = [pid for roster in ROSTERS.values() for pid in roster]
        conn.execute(insert(db.players_table), [
            {"player_id": pid, "full_name": f"Player {pid[1:]}", "position": POSITIONS[i % 4],
             "team": TEAMS[i % 8], "age": 23 + i % 9, "search_rank": i + 1}
            for i, pid in enumerate(players)])
        conn.execute(insert(db.player_value_history_table), [
            {"player_id": pid, "scoring_format": "1qb_ppr", "consensus_elo": 1900.0 - 20 * i,
             "snapshot_date": VALUE_DATE}
            for i, pid in enumerate(players)])
        conn.execute(insert(db.draft_picks_table), [
            {"pick_id": f"{LEAGUE}_2027_1_4", "league_id": LEAGUE, "season": 2027, "round": 1,
             "owner_user_id": "u2", "owner_username": "jared", "original_user_id": "u3",
             "original_username": "Kim", "is_traded": 1, "pick_value": 50.0,
             "pool_value": 2117.0, "platform": "sleeper", "source": None},
            {"pick_id": f"{LEAGUE}_2027_2_1", "league_id": LEAGUE, "season": 2027, "round": 2,
             "owner_user_id": USER, "owner_username": "me", "original_user_id": USER,
             "original_username": "Me", "is_traded": 0, "pick_value": 30.0,
             "pool_value": 900.0, "platform": "sleeper", "source": "platform"}])
        seed_deck(conn, JOB, SERVED_AT,
                  [(i, p, g, r) for i, (p, g, r) in enumerate(CURRENT_CARDS)])


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

@pytest.fixture
def world(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    _seed(eng)

    real_is_enabled = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: False if k == "grading.blind" else real_is_enabled(k))
    overlay = {"on": True}
    monkeypatch.setattr(experiments, "resolve_for_unit",
                        lambda unit, attrs=None: (OVERLAY if overlay["on"] and unit == USER
                                                  else NO_OVERLAY))
    monkeypatch.setattr(server, "_load_tester_allowlist", lambda: {USER})
    monkeypatch.setattr(server, "_value_core_standings", lambda league_id, platform: ({}, 0))
    monkeypatch.setattr(server, "_league_lineup_slots", lambda league_id: None)
    monkeypatch.setattr(server, "_sleeper_roster_limit", lambda league_id: None)
    monkeypatch.setattr(server, "_CRON_SECRET", CRON)
    engine = stub_engine(VC_TRADES)
    monkeypatch.setattr(vc_pipeline, "run", engine)

    real_thread = server.threading.Thread

    class _InlineThread(real_thread):
        def start(self):
            if self.name == "grading-build":
                self.run()
            else:
                super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineThread)

    sess = {"user_id": USER, "league_user_id": USER, "verified": True,
            "league": SimpleNamespace(league_id=LEAGUE, platform="sleeper"),
            "players": [], "trade_svc": SimpleNamespace(_trade_cards={}), "last_active": 0.0}
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db, "engine", eng):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield SimpleNamespace(client=client, eng=eng, sess=sess, overlay=overlay,
                                  engine=engine)
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


ANSWERS = ({"grade": 4, "tags": ["overpay"]}, {"grade": 2}, {"skip": True})


def _start(w, bodies: list) -> str:
    """POST (202 building; the build thread ran inline) then one poll (open)."""
    r = w.client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert r.status_code == 202, r.get_json()
    bodies.append(r.get_json())
    assert bodies[-1]["session"]["status"] == "building"
    r = w.client.get(CURRENT, headers=AUTH)
    assert r.status_code == 200
    bodies.append(r.get_json())
    assert bodies[-1]["session"]["status"] == "open", bodies[-1]
    return bodies[-1]["session"]["session_id"]


def _grade_all(w, sid: str, bodies: list) -> list:
    """Loop next / answer until done; returns every served card."""
    answers = cycle(ANSWERS)
    cards = []
    while True:
        r = w.client.get(f"/api/grading/sessions/{sid}/next", headers=AUTH)
        assert r.status_code == 200, r.get_json()
        nxt = r.get_json()
        bodies.append(nxt)
        if nxt["done"]:
            return cards
        cards.append(nxt["card"])
        r = w.client.post(f"/api/grading/cards/{nxt['card']['card_id']}", json=next(answers),
                          headers=AUTH)
        assert r.status_code == 200, r.get_json()
        bodies.append(r.get_json())


def _walk(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in FORBIDDEN_KEYS, f"{path}.{k} reveals an arm"
            _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        assert obj not in FORBIDDEN_VALUES and not obj.startswith("vc_"), f"{path} = {obj!r}"


def _key(trade: dict) -> tuple:
    return (trade["partner_name"], frozenset(a["id"] for a in trade["give"]),
            frozenset(a["id"] for a in trade["receive"]))


def _count(eng, table) -> int:
    with eng.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_no_response_reveals_an_arm_until_results(world):
    bodies: list = []
    sid = _start(world, bodies)
    cards = _grade_all(world, sid, bodies)

    for body in bodies:
        _walk(body)
    for card in cards:
        assert set(card["trade"]) == TRADE_KEYS
        for side in ("give", "receive"):
            assert card["trade"][side], card
            for asset in card["trade"][side]:
                assert set(asset) == ASSET_KEYS
    total = len(cards)
    assert total == len(CURRENT_CARDS) + len(VC_TRADES) - 1          # 39: one shared card
    assert sorted(c["position"] for c in cards) == list(range(1, total + 1))

    r = world.client.get(f"/api/grading/sessions/{sid}/results", headers=AUTH)
    assert r.status_code == 200, r.get_json()
    res = r.get_json()
    assert res["total"] == total
    assert res["shared"] == 1
    arms = res["arms"]
    assert set(arms) == {"current", "value_core"}
    assert arms["current"]["cards"] + arms["value_core"]["cards"] == res["total"] + res["shared"]
    assert res["target_mean"] == bg.TARGET_MEAN


def test_shared_trade_served_once(world):
    bodies: list = []
    sid = _start(world, bodies)
    cards = _grade_all(world, sid, bodies)
    partner, give, receive = SHARED
    shared_key = (MEMBERS[partner][1], frozenset(give), frozenset(receive))
    keys = [_key(c["trade"]) for c in cards]
    assert keys.count(shared_key) == 1
    assert len(set(keys)) == len(keys)                                 # every key once


def test_grading_leaves_deck_and_swipes_untouched(world):
    tables = (db.deck_impressions_table, db.trade_impressions_table, db.trade_decisions_table,
              db.swipe_decisions_table)
    before = [_count(world.eng, t) for t in tables]
    assert before[0] == len(CURRENT_CARDS)
    cards_before = len(world.sess["trade_svc"]._trade_cards)

    bodies: list = []
    sid = _start(world, bodies)
    _grade_all(world, sid, bodies)
    assert world.client.get(f"/api/grading/sessions/{sid}/results", headers=AUTH).status_code == 200

    assert [_count(world.eng, t) for t in tables] == before
    assert len(world.sess["trade_svc"]._trade_cards) == cards_before
    assert len(world.engine.calls) == 1                                # the value core ran once


def test_order_is_not_blocked_by_arm(world, monkeypatch):
    monkeypatch.setattr(bg.secrets, "randbits", lambda k: 0x5DEECE66D)
    bodies: list = []
    sid = _start(world, bodies)
    with world.eng.connect() as conn:
        rows = conn.execute(
            select(db.grading_cards_table.c.arms_json)
            .where(db.grading_cards_table.c.session_id == sid)
            .order_by(db.grading_cards_table.c.position)).fetchall()
    arms = [set(json.loads(r.arms_json)) for r in rows]
    only_current = [i for i, a in enumerate(arms) if a == {"current"}]
    only_vc = [i for i, a in enumerate(arms) if a == {"value_core"}]
    assert only_current and only_vc
    assert min(only_vc) < max(only_current), "all current cards precede every value-core card"
    assert min(only_current) < max(only_vc), "all value-core cards precede every current card"


def test_stopping_the_overlay_kills_routes_not_the_report(world):
    bodies: list = []
    sid = _start(world, bodies)
    r = world.client.get(f"/api/grading/sessions/{sid}/next", headers=AUTH)
    card_id = r.get_json()["card"]["card_id"]
    assert world.client.post(f"/api/grading/cards/{card_id}", json={"grade": 5},
                             headers=AUTH).status_code == 200

    world.overlay["on"] = False                      # calibration_rollout stopped
    r = world.client.get(f"/api/grading/sessions/{sid}/next", headers=AUTH)
    assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert world.client.get(CURRENT, headers=AUTH).status_code == 404

    r = world.client.get(f"{REPORT}?include_open=1", headers={"X-Cron-Secret": CRON})
    assert r.status_code == 200, r.get_json()
    report = r.get_json()
    assert sid in [s["session_id"] for s in report["sessions"]]
    assert report["version"] == bg.VERSION
    r = world.client.get(REPORT, headers={"X-Cron-Secret": CRON})   # completed only by default
    assert sid not in [s["session_id"] for s in r.get_json()["sessions"]]
