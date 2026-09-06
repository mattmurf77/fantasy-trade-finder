"""419 T5/T8: actual cached/provisional/pending serve paths recheck history.

No remote-only retained mobile snapshot claim. Synthetic isolated decisions;
the server job's captured identity, not the caller's current league, owns cuts.
"""
import copy
import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import event, insert, select

from backend import database as db, server
from backend.tests.test_decline_reasons import (
    harness, mem_engine, LEAGUE, ME, OPP, TOKEN, TRADE, IMP, _post, _reason,
)
from backend.tests.test_trade_interest_disposition import Clock


@pytest.fixture
def replay(harness, monkeypatch):
    client, _ranking, svc, engine = harness
    monkeypatch.setattr(db, "datetime", Clock)
    monkeypatch.setattr(server, "datetime", Clock)
    monkeypatch.setattr(server, "_deck_cfg", lambda key, default: default)
    monkeypatch.setattr(server, "load_league_preference", lambda **kw: None)
    monkeypatch.setattr(server, "_infer_user_outlook", lambda *a: (None, None))
    snapshot = server.trade_card_to_dict(svc._trade_cards[TRADE], {})
    siblings = [dict(snapshot, trade_id="sibling_a", receive=[{"id": "r2"}], tier="browse"),
                dict(snapshot, trade_id="sibling_b", give=[{"id": "g2"}], lane="outlook")]
    rows = [siblings[0], snapshot, siblings[1]]
    job = dict(job_id="419-job", key=(ME, LEAGUE, "1qb_ppr"), status="complete",
               opponents_done=1, opponents_total=1, cards=rows, error=None,
               finished_at=time.monotonic(), fairness_threshold=.75, outlook_value=None,
               safety_policy=server._trade_safety_signature())
    monkeypatch.setitem(server._trade_jobs, job["job_id"], job)
    monkeypatch.setitem(server._trade_jobs_by_key, job["key"], job["job_id"])
    yield client, svc, engine, job, siblings


def _pass(engine, *, at="2026-09-05T11:59:59Z", league=LEAGUE, actor=ME):
    with engine.begin() as conn:
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=actor, league_id=league, trade_id="different_card_id",
            give_player_ids=json.dumps(["g1"]), receive_player_ids=json.dumps(["r1"]),
            decision="pass", created_at=at))


@pytest.mark.parametrize("status", ["complete", "running"])
@pytest.mark.parametrize("endpoint", ["status", "generate"])
def test_419_cached_and_running_public_routes_honor_exact_pass(replay, status, endpoint):
    client, _svc, engine, job, siblings = replay
    job["status"] = status
    before = copy.deepcopy(job["cards"])
    _pass(engine)
    with engine.connect() as conn:
        impressions_before = conn.execute(select(db.deck_impressions_table)).all()
    statements = []

    def audit(_conn, _cursor, statement, *_):
        assert not server._trade_jobs_lock.locked(), "DB work under global job lock"
        if "FROM trade_decisions" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", audit)
    try:
        if endpoint == "status":
            response = client.get("/api/trades/status?job_id=419-job",
                                  headers={"X-Session-Token": TOKEN})
        else:
            response = _post(client, {"league_id": LEAGUE, "fairness_threshold": .75},
                             path="/api/trades/generate")
    finally:
        event.remove(engine, "before_cursor_execute", audit)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["cards"] == siblings
    assert len(statements) == 1
    assert job["cards"] == before  # projection, not frozen snapshot mutation
    with engine.connect() as conn:
        assert conn.execute(select(db.deck_impressions_table)).all() == impressions_before


def test_419_old_job_uses_its_league_after_caller_switch(replay):
    client, _svc, engine, job, siblings = replay
    # Same exact package in caller's new league must not remove this old job.
    _pass(engine, league="other-league")
    server._sessions[TOKEN]["league"] = copy.copy(server._sessions[TOKEN]["league"])
    server._sessions[TOKEN]["league"].league_id = "other-league"
    headers = {"X-Session-Token": TOKEN, "X-Scoring-Format": "sf_tep"}
    assert client.get("/api/trades/status?job_id=419-job", headers=headers).get_json()["cards"] == job["cards"]
    _pass(engine)
    assert client.get("/api/trades/status?job_id=419-job", headers=headers).get_json()["cards"] == siblings


def test_419_expired_amnestied_pass_resolves_cached_interest_not_organic(replay):
    client, _svc, engine, job, siblings = replay
    job["cards"][1]["likes_you"] = True
    with engine.begin() as conn:
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=OPP, league_id=LEAGUE, trade_id="old_source",
            give_player_ids='["r1"]', receive_player_ids='["g1"]',
            decision="like", created_at="2026-08-14T12:00:00Z"))
    _pass(engine, at="2026-08-16T12:00:00Z")
    response = client.get("/api/trades/status?job_id=419-job", headers={"X-Session-Token": TOKEN})
    assert response.get_json()["cards"] == siblings
    job["cards"][1].pop("likes_you")
    response = client.get("/api/trades/status?job_id=419-job", headers={"X-Session-Token": TOKEN})
    assert response.get_json()["cards"] == job["cards"]


def test_419_pending_new_id_cannot_replay_reasoned_exact_pass(replay):
    client, svc, _engine, _job, _siblings = replay
    assert _post(client, _reason({"reason": "fit"})).get_json()["passed"] is True
    copied = copy.copy(svc._trade_cards[TRADE])
    copied.trade_id, copied.decision = "new_same_package", None
    svc._trade_cards[copied.trade_id] = copied
    response = client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200 and response.get_json() == []


def test_419_standing_offer_retains_lifecycle_but_active_pass_wins(replay):
    client, _svc, engine, job, siblings = replay
    job["cards"][1].update(likes_you=True, standing_offer_reason="Available for a pick")
    headers = {"X-Session-Token": TOKEN}
    assert client.get("/api/trades/status?job_id=419-job", headers=headers).get_json()["cards"] == job["cards"]
    _pass(engine)
    assert client.get("/api/trades/status?job_id=419-job", headers=headers).get_json()["cards"] == siblings


def test_419_unverifiable_nonstanding_badge_is_not_affirmative_interest(replay):
    client, _svc, _engine, job, siblings = replay
    job["cards"][1]["likes_you"] = True  # deliberately no source decision
    response = client.get("/api/trades/status?job_id=419-job", headers={"X-Session-Token": TOKEN})
    assert response.get_json()["cards"] == siblings


def test_419_initial_generate_snapshot_is_projected(replay, monkeypatch):
    client, _svc, engine, job, siblings = replay
    _pass(engine)

    def kickoff(**kwargs):
        fresh = copy.deepcopy(job)
        fresh.update(job_id="419-new", status="running")
        monkeypatch.setitem(server._trade_jobs, fresh["job_id"], fresh)
        return fresh["job_id"]

    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)
    response = _post(client, {"league_id": LEAGUE, "force": True}, path="/api/trades/generate")
    assert response.status_code == 200
    assert response.get_json()["job_id"] == "419-new"
    assert response.get_json()["cards"] == siblings


def test_419_pass_during_real_worker_is_removed_before_impression_publication():
    from backend.tests.support import bakeoff_harness as H
    original = server.trade_card_to_dict
    passed = []

    def pass_while_serializing(card, players):
        if not passed:
            passed.append((frozenset(card.give_player_ids), frozenset(card.receive_player_ids)))
            db.save_trade_decision(H.ME, H.LEAGUE, "419-mid-worker",
                card.give_player_ids, card.receive_player_ids, "pass")
        return original(card, players)

    _capture, job, engine = H.run_capture(extra_patches=[
        patch.object(server, "trade_card_to_dict", pass_while_serializing)])
    assert job["status"] == "complete", job.get("error")
    assert len(passed) == 1
    for row in job["cards"]:
        assert (frozenset(p["id"] for p in row["give"]),
                frozenset(p["id"] for p in row["receive"])) != passed[0]
    with engine.connect() as conn:
        impressions = conn.execute(select(db.trade_impressions_table)).all()
    for row in impressions:
        assert (frozenset(json.loads(row.give_player_ids)),
                frozenset(json.loads(row.receive_player_ids))) != passed[0]


def test_419_serve_projection_has_no_global_job_lock_and_worker_precedes_impressions():
    import ast
    import inspect
    for fn in (server.generate_trades, server.trade_job_status):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.With) and any(
                    isinstance(item.context_expr, ast.Name)
                    and item.context_expr.id == "_trade_jobs_lock" for item in node.items):
                assert not any(isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_trade_job_public_view" for call in ast.walk(node))
    source = inspect.getsource(server._run_trade_job)
    assert source.index("final_cards = _project_trade_dispositions(") < source.index("log_trade_impressions(")
    assert "_project_trade_dispositions(" in inspect.getsource(server.get_trades)
