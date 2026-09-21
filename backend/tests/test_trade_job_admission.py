"""Real job/route regression tests with isolated SQLite and no provider access."""
from concurrent.futures import ThreadPoolExecutor
import copy
import gc
import socket
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
import weakref

import pytest
from sqlalchemy import create_engine

from backend import database as db, feature_flags as ff, server
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService


UID, LID, TOKEN, FMT = "admission-user", "admission-league", "admission-token", "1qb_ppr"
PREFS = {"prefs": {"team_outlook": "balanced"}, "seeded_outlook": None}


@pytest.fixture
def world(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden in admission test")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    engine = create_engine("sqlite:///" + str(tmp_path / "isolated.sqlite3"))
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(ff, "_flags_cache", {key: False for key in ff.DEFAULT_FLAGS})
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "_trade_input_epochs", weakref.WeakValueDictionary())
    pool = [Player(pid, pid, "RB", "AAA", 24) for pid in ("give", "other", "receive")]
    ranker = RankingService(pool, seed_ratings={p.id: 1600 + i * 100 for i, p in enumerate(pool)})
    league = League(LID, "Admission", "mfl", [
        LeagueMember(UID, "Viewer", ["give", "other"], {}),
        LeagueMember("opponent", "Opponent", ["receive"], {})])
    trader = TradeService({p.id: p for p in pool})
    trader.add_league(league)
    session = dict(user_id=UID, verified=True, league=league, user_roster=["give", "other"],
        players=pool, service=ranker, trade_svc=trader, services={FMT: ranker},
        trade_svcs={FMT: trader}, active_format=FMT, last_active=0)
    monkeypatch.setitem(server._sessions, TOKEN, session)
    monkeypatch.setattr(server, "load_league_preference", Mock(return_value=PREFS["prefs"]))
    monkeypatch.setattr(server, "_infer_user_outlook", Mock(return_value=(None, None)))
    pending = []
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: pending.append(kw))
    yield SimpleNamespace(session=session, pending=pending, engine=engine)
    engine.dispose()


def kickoff(**kwargs):
    return server._kickoff_trade_job(TOKEN, UID, LID, FMT, **kwargs)


def test_two_simultaneous_admissions_claim_one_worker(world, monkeypatch):
    barrier = Barrier(2)
    original = server._capture_trade_execution
    def capture(*args):
        result = original(*args)
        # This would deadlock if capture held the job/session admission lock.
        barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(server, "_capture_trade_execution", capture)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda _: kickoff(prefs_preload=PREFS), range(2)))
    assert jobs[0] == jobs[1]
    assert len(world.pending) == len(server._trade_jobs) == 1


def test_sabotage_admission_lookup_red_then_restored_green(world, monkeypatch):
    class MissingLookup(dict):
        def get(self, key, default=None):
            return default
    def same_request_guard():
        first = kickoff(prefs_preload=PREFS)
        second = kickoff(prefs_preload=PREFS)
        assert first == second, "duplicate worker admitted"
    with monkeypatch.context() as broken:
        broken.setattr(server, "_trade_jobs_by_key", MissingLookup())
        with pytest.raises(AssertionError, match="duplicate worker admitted"):
            same_request_guard()
    same_request_guard()


def test_sabotage_invalidation_red_then_restored_green(world, monkeypatch):
    job_id = kickoff(prefs_preload=PREFS)
    def invalidation_guard():
        server._invalidate_trade_jobs(user_id=UID)
        assert not server._job_live(server._trade_jobs[job_id]), "stale worker may publish"
    with monkeypatch.context() as broken:
        broken.setattr(server, "_invalidate_trade_jobs", lambda **kwargs: 0)
        with pytest.raises(AssertionError, match="stale worker may publish"):
            invalidation_guard()
    invalidation_guard()


@pytest.mark.parametrize("change", ["fairness", "outlook", "intent", "preferences", "config"])
def test_changed_request_never_joins_old_running_work(world, monkeypatch, change):
    old = kickoff(prefs_preload=PREFS)
    kwargs = {"prefs_preload": copy.deepcopy(PREFS)}
    if change == "fairness":
        kwargs["fairness_threshold"] = .755  # Exact threshold, not previous ±.01 rule.
    elif change == "outlook":
        kwargs["prefs_preload"]["prefs"]["team_outlook"] = "rebuilder"
    elif change == "intent":
        kwargs["trade_intent"] = "tier_up"
    elif change == "preferences":
        kwargs["prefs_preload"]["prefs"]["acquire_positions"] = ["WR"]
    else:
        monkeypatch.setitem(server._trade_service_mod._cfg, "owner_bilateral_rank_floor", 999)
    new = kickoff(**kwargs)
    assert old != new
    assert server._trade_jobs[old]["status"] == "error"
    assert not server._job_live(server._trade_jobs[old])
    assert server._job_live(server._trade_jobs[new])


def test_invalidation_fences_running_and_copied_snapshots_without_changing_ids(world):
    job_id = kickoff(prefs_preload=PREFS)
    job = server._trade_jobs[job_id]
    exact_offer = SimpleNamespace(trade_id="durable-old-trade", impression_id="durable-old-impression")
    world.session["trade_svc"]._trade_cards[exact_offer.trade_id] = exact_offer
    job["cards"] = [{"trade_id": exact_offer.trade_id, "impression_id": exact_offer.impression_id}]
    snapshot = copy.deepcopy(job)
    assert server._invalidate_trade_jobs(user_id=UID) == 1
    assert server._trade_job_revoked(snapshot)
    assert server._finish_trade_job(job_id) is None
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert not server._trade_job_is_fresh(job, .75, "balanced")
    assert world.session["trade_svc"]._trade_cards[exact_offer.trade_id] is exact_offer
    assert exact_offer.impression_id == "durable-old-impression"
    assert kickoff(prefs_preload=PREFS) != job_id


def test_invalidation_during_input_capture_never_starts_stale_worker(world, monkeypatch):
    original = server._capture_trade_execution
    def capture(*args):
        result = original(*args)
        server._invalidate_trade_jobs(user_id=UID, league_id=LID)
        return result
    monkeypatch.setattr(server, "_capture_trade_execution", capture)
    job = server._trade_jobs[kickoff(prefs_preload=PREFS)]
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert not world.pending and not server._trade_jobs_by_key


def test_generate_route_does_not_reuse_when_preferences_are_unavailable(world, monkeypatch):
    old = kickoff(prefs_preload=PREFS)
    monkeypatch.setattr(server, "load_league_preference", Mock(side_effect=RuntimeError("unavailable")))
    response = server.app.test_client().post("/api/trades/generate", json={},
                                            headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["job_id"] != old
    assert not server._job_live(server._trade_jobs[old])


@pytest.mark.parametrize("completed", [False, True])
def test_resolved_request_never_reuses_explicitly_unresolved_admission(world, monkeypatch, completed):
    with monkeypatch.context() as unavailable:
        unavailable.setattr(server, "load_league_preference", Mock(side_effect=RuntimeError("unavailable")))
        old_id = kickoff()
    old = server._trade_jobs[old_id]
    assert "request_signature" in old and old["request_signature"] is None
    # Keep outlook/fairness/intent identical: unknown request identity alone
    # must prevent reuse, for running and successfully completed jobs alike.
    monkeypatch.setattr(server, "load_league_preference", Mock(return_value={}))
    if completed:
        old["safety_policy"] = server._trade_safety_signature()
        server._finish_trade_job(old_id)
    assert kickoff() != old_id
    assert len(world.pending) == 2


def test_force_and_selected_jobs_have_separate_admission_but_shared_invalidation(world):
    organic = kickoff(prefs_preload=PREFS)
    selected = kickoff(prefs_preload=PREFS, pinned_give=["give"])
    selected_again = kickoff(prefs_preload=PREFS, pinned_give=["give"])
    forced = kickoff(prefs_preload=PREFS, force_fresh=True)
    assert len({organic, selected, selected_again, forced}) == 4
    assert server._trade_jobs_by_key[(UID, LID, FMT)] == forced
    assert server._job_live(server._trade_jobs[selected])
    assert not server._job_live(server._trade_jobs[organic])
    server._invalidate_trade_jobs(user_id=UID, league_id=LID)
    assert all(not server._job_live(job) for job in server._trade_jobs.values())


def test_background_preparation_does_not_replace_active_user_search(world):
    active = kickoff(prefs_preload=PREFS, fairness_threshold=.75, trade_intent="tier_up")
    background = kickoff(prefs_preload=PREFS, fairness_threshold=.5, preserve_running=True)
    assert background == active and len(world.pending) == 1
    assert server._job_live(server._trade_jobs[active])
    assert not server._trade_running_matches(server._trade_jobs[active], .5, "balanced",
                                             presentation_capture=server._capture_trade_presentation())


@pytest.mark.parametrize("change", ["presentation", "model", "significance", "safety"])
def test_background_replaces_obsolete_policy_even_when_user_intent_differs(world, monkeypatch, change):
    active = kickoff(prefs_preload=PREFS, fairness_threshold=.75, trade_intent="tier_up")
    server._trade_jobs[active]["safety_policy"] = server._trade_safety_signature()
    if change == "presentation":
        monkeypatch.setitem(server._trade_service_mod._cfg, "simple_player_presentment", 1)
    elif change == "model":
        monkeypatch.setitem(server._trade_service_mod._cfg, "owner_bilateral_enabled", 1)
    elif change == "significance":
        monkeypatch.setitem(server._trade_service_mod._cfg, "significance_mode", 2)
    else:
        monkeypatch.setattr(server._trade_policy, "policy_enabled", lambda: True)
    replacement = kickoff(prefs_preload=PREFS, fairness_threshold=.5, preserve_running=True)
    assert replacement != active and len(world.pending) == 2
    assert server._trade_jobs[active]["status"] == "error"
    assert server._trade_jobs[active]["error"] == "superseded"
    assert not server._job_live(server._trade_jobs[active])


def test_timeouts_and_late_worker_errors_cannot_resurrect_or_replace_terminal_state(world):
    job_id = kickoff(prefs_preload=PREFS)
    job = server._trade_jobs[job_id]
    job.update(status="error", error="timeout", finished_at=123)
    assert server._finish_trade_job(job_id) is None
    assert server._finish_trade_job(job_id, error="later_error") is None
    assert job["status"] == "error" and job["error"] == "timeout" and job["finished_at"] == 123
    assert server._job_superseded(job_id)


def test_thread_start_failure_returns_terminal_error_and_allows_retry(world, monkeypatch):
    def fail(**kwargs):
        assert server._trade_jobs_lock.acquire(blocking=False)
        server._trade_jobs_lock.release()
        raise RuntimeError("test start failure")
    monkeypatch.setattr(server, "_start_trade_job_thread", fail)
    first = kickoff(prefs_preload=PREFS)
    assert server._trade_jobs[first]["error"] == "worker_start_failed"
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: world.pending.append(kw))
    assert kickoff(prefs_preload=PREFS) != first


def test_input_reads_capture_and_start_are_outside_job_lock(world, monkeypatch):
    def check_lock():
        assert server._trade_jobs_lock.acquire(blocking=False)
        server._trade_jobs_lock.release()
    original = server._capture_trade_execution
    def capture(*args):
        check_lock()
        return original(*args)
    def prefs(**kwargs):
        check_lock()
        return PREFS["prefs"]
    monkeypatch.setattr(server, "_capture_trade_execution", capture)
    monkeypatch.setattr(server, "load_league_preference", prefs)
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: check_lock())
    kickoff()


def test_epoch_index_reclaims_scopes_after_jobs_and_admissions_expire(world):
    epochs = server._capture_trade_input_epochs("temporary-user", "temporary-league")
    assert len(server._trade_input_epochs) == 2
    del epochs
    gc.collect()
    assert not server._trade_input_epochs


@pytest.mark.parametrize("route,payload", [
    ("/api/tiers/save", {"position": "RB", "tiers": {"first_1": ["give"]}}),
    ("/api/anchor/save", {"player_id": "give", "anchor": "2_firsts"}),
    ("/api/rankings/reorder", {"ordered_ids": ["other", "give"]}),
    ("/api/rankings/import-apply", {"ordered_player_ids": ["other", "give"]}),
])
def test_successful_board_routes_revoke_existing_selected_and_organic_work(world, monkeypatch, route, payload):
    monkeypatch.setitem(ff._flags_cache, "ranks.import", True)
    monkeypatch.setattr(server, "_record_trends_snapshot", Mock())
    monkeypatch.setattr(server, "_note_ranking_method", Mock())
    monkeypatch.setattr(server, "_refresh_taste_board_prior", Mock())
    organic = kickoff(prefs_preload=PREFS)
    selected = kickoff(prefs_preload=PREFS, pinned_give=["give"])
    response = server.app.test_client().post(route, json=payload, headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200, response.get_json()
    assert server._trade_jobs[organic]["error"] == "inputs_changed"
    assert server._trade_jobs[selected]["error"] == "inputs_changed"


@pytest.mark.parametrize("platform,fmt", [("mfl", "sf_tep"), ("espn", "1qb_ppr")])
def test_headless_reconstruction_uses_actual_platform_and_scoring_pool(world, monkeypatch, platform, fmt):
    monkeypatch.setattr(server, "load_league_members", lambda _: [
        {"user_id": UID, "player_ids": ["give"]}, {"user_id": "opponent", "player_ids": ["receive"]}])
    payload = dict(world.session)
    payload["services"] = {fmt: world.session["service"]}
    monkeypatch.setattr(server, "_extension_build_session", lambda **_: (TOKEN, payload))
    monkeypatch.setattr(server, "get_league_scoring", lambda _: fmt)
    monkeypatch.setattr(server, "get_league_draft_context", lambda _: {"platform": platform})
    requested = []
    def pool(scoring):
        requested.append(scoring)
        return world.session["players"], world.session["service"]._seed
    monkeypatch.setattr(server, "_get_universal_pool", pool)
    assert server._build_replenish_session(UID, LID) == TOKEN
    assert requested == [fmt]
    assert payload["league"].platform == platform and payload["active_format"] == fmt
