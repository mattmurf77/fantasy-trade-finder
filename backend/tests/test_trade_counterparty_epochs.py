"""Counterparty revocation on actual admission, worker, SQLite and public views.

The original private RED diagnostic is preserved outside this module. These
regressions assert desired revocation, never retention of the known stale deck.
"""
import ast
import copy
import gc
import inspect
import json
import socket
import time
import weakref
from types import SimpleNamespace

import pytest

from backend import database as db, server, trade_service as ts
from backend import trade_gen_bilateral_candidate as candidate
from backend.ranking_service import RankingService
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, rows, ME, OPP, LEAGUE, TOKEN, SEED)

FMT = "1qb_ppr"
BTOKEN = "private-partner-token"


@pytest.fixture
def world(owner_harness, monkeypatch):
    client, engine, session, trader, league = owner_harness
    network = []
    def denied(*args, **kwargs):
        network.append(True)
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "_trade_input_epochs", weakref.WeakValueDictionary())
    for name in ("_deck_exploration_enabled", "_deck_first_session_enabled", "_likes_you_enabled",
                 "_suggestion_telemetry_enabled", "_deck_fatigue_enabled", "_deck_taste_enabled",
                 "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    for name in ("_record_trends_snapshot", "_note_ranking_method", "_refresh_taste_board_prior"):
        monkeypatch.setattr(server, name, lambda *a, **k: None)
    monkeypatch.setitem(server._FA_LEAGUE_META_CACHE, LEAGUE,
                        (time.time(), {"roster_positions": ["RB", "RB", "FLEX", "BN"]}))
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   bakeoff_owner_only=1.)
    board = {**SEED, "a1": 1700., "b1": 1500.}
    db.upsert_member_rankings(OPP, LEAGUE,
        [{"player_id": p, "elo": value} for p, value in board.items()],
        scoring_format=FMT, confidence_source="explicit")
    monkeypatch.setattr(server, "load_member_rankings", db.load_member_rankings)
    for uid in (ME, OPP):
        db.upsert_league_preference(uid, LEAGUE, "not_sure")
    ranker = RankingService(session["players"], seed_ratings=SEED)
    ranker._elo_overrides.update(board)
    partner_trader = ts.TradeService(dict(trader._players))
    partner_trader.add_league(league)
    partner = {**session, "user_id": OPP, "user_roster": list(league.members[1].roster),
               "service": ranker, "services": {FMT: ranker},
               "trade_svc": partner_trader, "trade_svcs": {FMT: partner_trader}}
    monkeypatch.setitem(server._sessions, BTOKEN, partner)
    pending = []
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: pending.append(kw))
    captures = []
    original = candidate.generate_bilateral_trades
    def observed(**kwargs):
        captures.append(copy.deepcopy(kwargs))
        return original(**kwargs)
    monkeypatch.setattr(candidate, "generate_bilateral_trades", observed)
    yield SimpleNamespace(client=client, engine=engine, session=session, pending=pending,
                          captures=captures, network=network)
    assert not network


def status(w, job_id, token=TOKEN):
    response = w.client.get("/api/trades/status", query_string={"job_id": job_id},
                            headers={"X-Session-Token": token})
    assert response.status_code == 200, response.json
    return response.json


def admission(w):
    response = w.client.post("/api/trades/generate", json={"league_id": LEAGUE,
        "fairness_threshold": .5}, headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200, response.json
    return response.json


def mutate(w, actor, change):
    uid, token = (ME, TOKEN) if actor == "viewer" else (OPP, BTOKEN)
    if change == "board":
        before = db.load_member_rankings(LEAGUE, exclude_user_id="", scoring_format=FMT)[OPP]["elo_ratings"].copy()
        response = w.client.post("/api/tiers/save", json={"position": "RB",
            "tiers": {"first_1": ["b1"], "second": ["a1"]}},
            headers={"X-Session-Token": token})
        assert response.status_code == 200, response.json
        after = db.load_member_rankings(LEAGUE, exclude_user_id="", scoring_format=FMT)[uid]["elo_ratings"]
        assert after["a1"] != (1700. if actor == "partner" else 1500.)
        if actor == "partner":
            assert after != before
    else:
        response = w.client.post("/api/league/preferences", json={"league_id": LEAGUE,
            "team_outlook": "jets"}, headers={"X-Session-Token": token})
        assert response.status_code == 200, response.json
        assert db.load_league_preference(uid, LEAGUE)["team_outlook"] == "jets"


def assert_freshness_at_real_boundary(w, job_id, phase, actor, change):
    initial = status(w, job_id)
    assert initial["status"] == phase
    assert len(initial["cards"]) >= 2
    assert admission(w)["job_id"] == job_id
    assert not w.pending
    # The actual constructor consumed B's DB-backed board and declared outlook.
    assert len(w.captures) == 1
    ctx = w.captures[0]
    member = next(m for m in ctx["league"].members if m.user_id == OPP)
    assert member.elo_ratings["a1"] == 1700.
    assert member.elo_ratings["b1"] == 1500.
    assert ctx["opponent_outlooks"][OPP] == "not_sure"
    assert w.client.get("/api/trades/status", query_string={"job_id": job_id},
        headers={"X-Session-Token": BTOKEN}).status_code == 404
    # Seed one existing exact like through the real audit writer; other cards
    # remain undecided. We do not manufacture a client view or swipe update.
    records = rows(w.engine, db.deck_impressions_table)
    record = next(r for r in records if r["impression_id"] == initial["cards"][0]["impression_id"])
    proof = json.loads(record["valuation_json"])
    card = initial["cards"][0]
    db.save_trade_decision(ME, LEAGUE, card["trade_id"],
        [p["id"] for p in card["give"]], [p["id"] for p in card["receive"]], "like",
        impression_id=card["impression_id"])
    tables = (db.deck_impressions_table, db.trade_decisions_table, db.deck_outcomes_table)
    evidence = [rows(w.engine, table) for table in tables]
    assert proof and evidence[0] and evidence[1] and not evidence[2]
    baseline = status(w, job_id)
    dependent_undecided = {c["trade_id"] for c in baseline["cards"]
        if c["target_user_id"] == OPP and c["trade_id"] != card["trade_id"]
        and c["decision"] is None}
    assert dependent_undecided
    mutate(w, actor, change)
    viewed = status(w, job_id)
    adopted = admission(w)
    # Reads/revocation must not erase, reprice or relabel original audit data.
    assert [rows(w.engine, table) for table in tables] == evidence
    assert len(w.captures) == 1  # any replacement worker is only admitted
    actual = {"phase": phase, "actor": actor, "change": change,
              "before_cards": len(baseline["cards"]), "after_cards": len(viewed["cards"]),
              "same_job_adopted": adopted["job_id"] == job_id,
              "replacement_workers": len(w.pending), "status": viewed["status"],
              "error": viewed["error"], "history_unchanged": True,
              "dependent_undecided_before": len(dependent_undecided),
              "dependent_undecided_after": len(dependent_undecided.intersection(
                  c["trade_id"] for c in viewed["cards"]))}
    assert not dependent_undecided.intersection(c["trade_id"] for c in viewed["cards"]), \
        f"stale dependent undecided inventory remains public: {actual}"
    if actor == "viewer":
        assert viewed["cards"] == []
    assert viewed["status"] == "error" and viewed["error"] == "inputs_changed"
    assert adopted["job_id"] != job_id and len(w.pending) == 1
    assert admission(w)["job_id"] == adopted["job_id"] and len(w.pending) == 1


@pytest.mark.parametrize("phase", ["complete", "running"])
@pytest.mark.parametrize("actor", ["partner", "viewer"])
@pytest.mark.parametrize("change", ["board", "outlook"])
def test_changed_consumed_input_revokes_public_inventory(world, monkeypatch, phase, actor, change):
    if phase == "running":
        finish = server._finish_trade_job
        errors = []
        called = []
        def at_real_finish(job_id, error=None):
            if error is None and not called:
                called.append(job_id)
                try:
                    assert_freshness_at_real_boundary(world, job_id, phase, actor, change)
                except BaseException as exc:
                    # Worker normally catches exceptions: relay outside it so
                    # diagnostic failure cannot be hidden as an error job.
                    errors.append(exc)
            return finish(job_id, error)
        monkeypatch.setattr(server, "_finish_trade_job", at_real_finish)
    job_id = server._kickoff_trade_job(TOKEN, ME, LEAGUE, FMT,
        fairness_threshold=.5, synchronous=True)
    if phase == "running":
        assert called == [job_id], server._trade_jobs[job_id]
        if errors:
            raise errors[0]
    else:
        assert_freshness_at_real_boundary(world, job_id, phase, actor, change)


def kickoff(w, **kwargs):
    return server._kickoff_trade_job(TOKEN, ME, LEAGUE, FMT,
        fairness_threshold=.5, **kwargs)


def assert_revoked(w, job_id):
    public = status(w, job_id)
    assert public["status"] == "error" and public["error"] == "inputs_changed"
    assert public["cards"] == []
    assert server._trade_job_revoked(server._trade_jobs[job_id])
    return public


@pytest.mark.parametrize("change", ["board", "outlook"])
def test_outside_league_user_save_does_not_revoke_current_inventory(world, monkeypatch, change):
    job_id = kickoff(world, synchronous=True)
    initial = status(world, job_id)
    assert initial["cards"] and initial["status"] == "complete"
    outside_id, outside_league_id, outside_token = "outside-member", "outside-league", "outside-token"
    league = copy.deepcopy(world.session["league"])
    league.league_id = outside_league_id
    league.members = [ts.LeagueMember(outside_id, "outside", ["a1"], {})]
    ranker = RankingService(world.session["players"], seed_ratings=SEED)
    trader = ts.TradeService({p.id: p for p in world.session["players"]})
    trader.add_league(league)
    session = {**world.session, "user_id": outside_id, "league": league,
        "user_roster": ["a1"], "service": ranker, "services": {FMT: ranker},
        "trade_svc": trader, "trade_svcs": {FMT: trader}}
    monkeypatch.setitem(server._sessions, outside_token, session)
    if change == "board":
        response = world.client.post("/api/tiers/save", json={"position": "RB",
            "tiers": {"first_1": ["a1"]}}, headers={"X-Session-Token": outside_token})
        assert response.status_code == 200, response.json
        assert outside_id in db.load_member_rankings(outside_league_id, "", FMT)
    else:
        response = world.client.post("/api/league/preferences", json={
            "league_id": outside_league_id, "team_outlook": "jets"},
            headers={"X-Session-Token": outside_token})
        assert response.status_code == 200, response.json
        assert db.load_league_preference(outside_id, outside_league_id)["team_outlook"] == "jets"
    assert status(world, job_id) == initial
    assert admission(world)["job_id"] == job_id and not world.pending


@pytest.mark.parametrize("change", ["board", "outlook"])
def test_partner_league_scope_is_narrow_but_global_board_reaches_both_leagues(world, monkeypatch, change):
    first = kickoff(world, synchronous=True)
    league = copy.deepcopy(world.session["league"])
    league.league_id = "second-league"
    trader = ts.TradeService({p.id: p for p in world.session["players"]})
    trader.add_league(league)
    second_session = {**world.session, "league": league, "trade_svc": trader,
                      "trade_svcs": {FMT: trader}}
    monkeypatch.setitem(server._sessions, "second-token", second_session)
    second = server._kickoff_trade_job("second-token", ME, league.league_id, FMT,
        fairness_threshold=.5, prefs_preload={"prefs": {"team_outlook": "not_sure"},
                                             "seeded_outlook": None})
    second_before = status(world, second)
    assert second_before["status"] == "running" and len(world.pending) == 1
    mutate(world, "partner", change)
    assert_revoked(world, first)
    if change == "board":
        assert_revoked(world, second)
    else:
        assert status(world, second) == second_before
        assert server._job_live(server._trade_jobs[second])


@pytest.mark.parametrize("selection", ["give", "receive", "partner"])
@pytest.mark.parametrize("change", ["board", "outlook"])
def test_selected_real_jobs_retain_identity_but_revoke_undecided_inventory(world, selection, change):
    kwargs = {"give": {"pinned_give": ["a1"]}, "receive": {"pinned_receive": ["b1"]},
              "partner": {"opponent_user_id": OPP}}[selection]
    job_id = kickoff(world, synchronous=True, **kwargs)
    initial = status(world, job_id)
    assert initial["status"] == "complete" and initial["cards"]
    assert server._trade_jobs[job_id]["is_pinned"]
    assert job_id not in server._trade_jobs_by_key.values()
    originals = rows(world.engine, db.deck_impressions_table)
    mutate(world, "partner", change)
    assert_revoked(world, job_id)
    assert rows(world.engine, db.deck_impressions_table) == originals
    replacement = kickoff(world, **kwargs)
    assert replacement != job_id and len(world.pending) == 1
    assert server._job_live(server._trade_jobs[replacement])


@pytest.mark.parametrize("boundary", ["execution_capture", "viewer_preferences"])
def test_partner_extension_never_replaces_revoked_original_viewer_tokens(world, monkeypatch, boundary):
    originals = server._capture_trade_input_epochs(ME, LEAGUE)
    name = "_capture_trade_execution" if boundary == "execution_capture" else "_trade_job_preferences"
    original = getattr(server, name)
    observed = []
    def invalidate_originals(*args, **kwargs):
        captured = original(*args, **kwargs)
        observed.append(True)
        server._invalidate_trade_jobs(user_id=ME)
        return captured
    monkeypatch.setattr(server, name, invalidate_originals)
    job_id = kickoff(world, input_epochs=originals, synchronous=True)
    assert observed
    assert originals[0].revoked
    assert all(any(held is token for held in server._trade_jobs[job_id]["input_epochs"])
               for token in originals)
    assert_revoked(world, job_id)
    assert not world.pending and not world.captures
    assert not rows(world.engine, db.deck_impressions_table)


@pytest.mark.parametrize("read", ["board", "outlook"])
def test_partner_change_during_actual_input_read_cannot_publish(world, monkeypatch, read):
    name = "load_member_rankings" if read == "board" else "load_league_preferences_bulk"
    original = getattr(server, name)
    loaded = []
    def change_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        if not loaded:
            loaded.append(copy.deepcopy(result))
            mutate(world, "partner", read)
        return result
    monkeypatch.setattr(server, name, change_after_read)
    job_id = kickoff(world, synchronous=True)
    assert loaded
    if read == "board":
        assert loaded[0][OPP]["elo_ratings"]["a1"] == 1700.
    else:
        assert loaded[0][OPP]["team_outlook"] == "not_sure"
    assert_revoked(world, job_id)
    assert not rows(world.engine, db.deck_impressions_table)
    assert not world.pending


def test_partner_invalidation_between_dependency_capture_and_atomic_admission_stays_revoked(world, monkeypatch):
    original = server._trade_request_signature
    observed = []
    def invalidate_after_signature(*args, **kwargs):
        signature = original(*args, **kwargs)
        observed.append(True)
        server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)
        return signature
    monkeypatch.setattr(server, "_trade_request_signature", invalidate_after_signature)
    job_id = kickoff(world, synchronous=True)
    assert observed == [True]
    assert_revoked(world, job_id)
    assert not world.pending and not world.captures
    assert not rows(world.engine, db.deck_impressions_table)


@pytest.mark.parametrize("mutation", ["membership_list", "member_identity"])
def test_dependency_identity_comes_from_owned_capture_not_later_session_mutation(world, monkeypatch, mutation):
    capture = server._capture_trade_execution
    owned = []
    def mutate_live_session(*args, **kwargs):
        context = capture(*args, **kwargs)
        owned.append(context)
        live = world.session["league"]
        if mutation == "membership_list":
            live.members = [m for m in live.members if m.user_id != OPP]
            live.members.append(ts.LeagueMember("late-outsider", "late", ["b1"], {}))
        else:
            next(m for m in live.members if m.user_id == OPP).user_id = "late-outsider"
        return context
    monkeypatch.setattr(server, "_capture_trade_execution", mutate_live_session)
    job_id = kickoff(world)
    assert OPP in {m.user_id for m in owned[0].league.members}
    assert OPP not in {m.user_id for m in world.session["league"].members}
    server._invalidate_trade_jobs(user_id="late-outsider")
    assert server._job_live(server._trade_jobs[job_id])
    server._invalidate_trade_jobs(user_id=OPP)
    assert_revoked(world, job_id)


@pytest.mark.parametrize("boundary", ["detached_copy", "during_projection"])
@pytest.mark.parametrize("change", ["board", "outlook"])
def test_counterparty_revocation_survives_copied_public_projection(world, monkeypatch, boundary, change):
    job_id = kickoff(world, synchronous=True)
    assert status(world, job_id)["cards"]
    originals = rows(world.engine, db.deck_impressions_table)
    if boundary == "detached_copy":
        copied = copy.deepcopy(server._trade_jobs[job_id])
        # The copied tokens alone must fence this snapshot, even if registry
        # cleanup removes its original job before the status result is shaped.
        monkeypatch.delitem(server._trade_jobs, job_id)
        mutate(world, "partner", change)
        public = server._trade_job_public_view(copied)
    else:
        project = server._project_trade_dispositions
        calls = []
        def mutate_during_projection(*args, **kwargs):
            projected = project(*args, **kwargs)
            calls.append(True)
            mutate(world, "partner", change)
            return projected
        monkeypatch.setattr(server, "_project_trade_dispositions", mutate_during_projection)
        public = status(world, job_id)
        assert calls == [True]
    assert public["cards"] == []
    assert public["status"] == "error" and public["error"] == "inputs_changed"
    assert rows(world.engine, db.deck_impressions_table) == originals


def test_default_capture_compatibility_participant_deduplication_and_weak_reclamation(world):
    original = server._capture_trade_input_epochs(ME, LEAGUE)
    assert len(original) == 2
    extended = server._capture_trade_input_epochs(ME, LEAGUE, participant_ids=(ME, OPP, OPP))
    assert len(extended) == len({id(token) for token in extended}) == 4
    assert extended[:2] == original
    assert set(server._trade_input_epochs) == {(ME, None), (ME, LEAGUE), (OPP, None), (OPP, LEAGUE)}
    references = [weakref.ref(token) for token in extended]
    del original, extended
    gc.collect()
    assert all(reference() is None for reference in references)
    assert not server._trade_input_epochs


def test_job_holds_partner_epochs_until_last_owned_snapshot_is_released(world):
    job_id = kickoff(world)
    copied = copy.deepcopy(server._trade_jobs[job_id])
    references = [weakref.ref(token) for token in copied["input_epochs"]]
    assert (OPP, LEAGUE) in server._trade_input_epochs
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    world.pending.clear()
    gc.collect()
    assert all(reference() is not None for reference in references)
    del copied
    gc.collect()
    assert all(reference() is None for reference in references)
    assert not server._trade_input_epochs


def test_unrelated_invalidation_does_not_revisit_an_already_revoked_job(world):
    job_id = kickoff(world)
    server._invalidate_trade_jobs(user_id=OPP)
    assert_revoked(world, job_id)
    before = copy.deepcopy(server._trade_jobs[job_id])
    assert server._invalidate_trade_jobs(user_id="outside-member") == 0
    assert server._trade_jobs[job_id] == before


@pytest.mark.parametrize("arm", ["legacy", "owner", "bilateral", "revision"])
def test_dependency_admission_is_not_selected_by_generation_arm(world, arm):
    ts._cfg.update(bakeoff_include_owner=float(arm != "legacy"),
                   bakeoff_serve_owner=float(arm != "legacy"),
                   owner_bilateral_enabled=float(arm in ("bilateral", "revision")),
                   owner_bilateral_revision_enabled=float(arm == "revision"))
    job_id = kickoff(world)
    assert server._job_live(server._trade_jobs[job_id])
    server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)
    assert_revoked(world, job_id)


def test_capture_rejects_explicit_wrong_league_before_any_worker_read(world):
    with pytest.raises(RuntimeError, match="session league changed before trade job started"):
        server._capture_trade_execution(world.session, ME, "wrong-requested-league", FMT)
    assert not world.captures and not world.pending


@pytest.mark.parametrize("source", ["registry", "retained_headless_session"])
def test_session_rebind_before_capture_cannot_mix_dependency_and_worker_leagues(world, monkeypatch, source):
    retained = world.session
    other = copy.deepcopy(retained["league"])
    other.league_id = "rebound-league"
    capture_epochs = server._capture_trade_input_epochs
    calls = []
    def rebind_after_original_epoch_capture(*args, **kwargs):
        tokens = capture_epochs(*args, **kwargs)
        if not calls:
            calls.append(True)
            retained["league"] = other
        return tokens
    monkeypatch.setattr(server, "_capture_trade_input_epochs", rebind_after_original_epoch_capture)
    options = {"session_context": retained} if source == "retained_headless_session" else {}
    job_id = kickoff(world, synchronous=True, **options)
    public = status(world, job_id)
    assert calls == [True]
    assert public["status"] == "error"
    assert public["error"] == "session league changed before trade job started"
    assert not public["cards"] and not world.captures and not world.pending
    assert not rows(world.engine, db.deck_impressions_table)


def test_live_league_id_change_after_owned_capture_does_not_retarget_scope(world, monkeypatch):
    capture = server._capture_trade_execution
    owned = []
    def rebind_after_capture(*args, **kwargs):
        context = capture(*args, **kwargs)
        owned.append(context)
        world.session["league"].league_id = "late-league"
        return context
    monkeypatch.setattr(server, "_capture_trade_execution", rebind_after_capture)
    job_id = kickoff(world)
    assert owned[0].league_id == owned[0].league.league_id == LEAGUE
    server._invalidate_trade_jobs(user_id=OPP, league_id="late-league")
    assert server._job_live(server._trade_jobs[job_id])
    server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)
    assert_revoked(world, job_id)


@pytest.mark.parametrize("missing", ["league", "service", "players", "user_roster"])
def test_partial_context_keeps_original_missing_state_failure(world, missing):
    partial = dict(world.session)
    partial[missing] = None
    if missing == "service":
        partial["services"] = {}
    job_id = kickoff(world, synchronous=True, session_context=partial)
    public = status(world, job_id)
    assert public["status"] == "error"
    assert public["error"] == "session missing required state for trade gen"
    assert not public["cards"] and not world.captures and not world.pending


def test_real_tier_save_revokes_job_admitted_after_early_fence_before_board_publish(world, monkeypatch):
    write = server.upsert_member_rankings
    observed = []
    def admit_before_actual_write(*args, **kwargs):
        assert kwargs["user_id"] == OPP
        job_id = kickoff(world, synchronous=True)
        public = status(world, job_id)
        assert public["status"] == "complete" and public["cards"]
        assert admission(world)["job_id"] == job_id and not world.pending
        context = world.captures[-1]
        member = next(m for m in context["league"].members if m.user_id == OPP)
        assert member.elo_ratings["a1"] == 1700.
        assert db.load_member_rankings(LEAGUE, "", FMT)[OPP]["elo_ratings"]["a1"] == 1700.
        card = public["cards"][0]
        db.save_trade_decision(ME, LEAGUE, card["trade_id"],
            [p["id"] for p in card["give"]], [p["id"] for p in card["receive"]],
            "like", impression_id=card["impression_id"])
        observed.append((job_id, [rows(world.engine, table) for table in
            (db.deck_impressions_table, db.trade_decisions_table, db.deck_outcomes_table)]))
        return write(*args, **kwargs)
    monkeypatch.setattr(server, "upsert_member_rankings", admit_before_actual_write)
    mutate(world, "partner", "board")
    assert len(observed) == len(world.captures) == 1
    job_id, originals = observed[0]
    assert [rows(world.engine, table) for table in
        (db.deck_impressions_table, db.trade_decisions_table, db.deck_outcomes_table)] == originals
    assert_revoked(world, job_id)
    assert admission(world)["job_id"] != job_id and len(world.pending) == 1


def test_explicit_submit_publishes_current_partner_board_and_revokes_old_inventory(world):
    job_id = kickoff(world, synchronous=True)
    assert status(world, job_id)["cards"]
    originals = rows(world.engine, db.deck_impressions_table)
    # The explicit submit publishes current session rankings; no earlier
    # invalidation call is manufactured by this fixture setup.
    server._sessions[BTOKEN]["service"]._elo_overrides["a1"] = 1400.
    response = world.client.post("/api/rankings/submit", json={"league_id": LEAGUE},
                                 headers={"X-Session-Token": BTOKEN})
    assert response.status_code == 200 and response.json["ok"]
    assert db.load_member_rankings(LEAGUE, "", FMT)[OPP]["elo_ratings"]["a1"] == 1400.
    assert rows(world.engine, db.deck_impressions_table) == originals
    assert_revoked(world, job_id)
    assert admission(world)["job_id"] != job_id and len(world.pending) == 1


@pytest.mark.parametrize("route", ["tiers", "submit"])
@pytest.mark.parametrize("failure", ["before_commit", "after_commit"])
def test_real_publish_failure_fences_jobs_created_during_the_write_attempt(world, monkeypatch, route, failure):
    write = server.upsert_member_rankings
    jobs = []
    originals = []
    def interleaved_failure(*args, **kwargs):
        jobs.append(kickoff(world, synchronous=True))
        assert status(world, jobs[-1])["status"] == "complete"
        originals.append(rows(world.engine, db.deck_impressions_table))
        if failure == "after_commit":
            write(*args, **kwargs)
        raise RuntimeError("synthetic board publication failure")
    monkeypatch.setattr(server, "upsert_member_rankings", interleaved_failure)
    if route == "tiers":
        response = world.client.post("/api/tiers/save", json={"position": "RB",
            "tiers": {"first_1": ["b1"], "second": ["a1"]}},
            headers={"X-Session-Token": BTOKEN})
        assert response.status_code == 200  # Existing fail-soft route contract.
    else:
        server._sessions[BTOKEN]["service"]._elo_overrides["a1"] = 1400.
        response = world.client.post("/api/rankings/submit", json={"league_id": LEAGUE},
                                     headers={"X-Session-Token": BTOKEN})
        assert response.status_code == 500 and response.json == {"error": "internal_error"}
    assert len(jobs) == len(world.captures) == len(originals) == 1
    captured = next(m for m in world.captures[0]["league"].members if m.user_id == OPP)
    assert captured.elo_ratings["a1"] == 1700.
    persisted = db.load_member_rankings(LEAGUE, "", FMT)[OPP]["elo_ratings"]["a1"]
    assert (persisted == 1700.) == (failure == "before_commit")
    assert rows(world.engine, db.deck_impressions_table) == originals[0]
    assert_revoked(world, jobs[0])
    assert admission(world)["job_id"] != jobs[0] and len(world.pending) == 1


@pytest.mark.parametrize("outcome", ["success", "fail_before", "commit_then_fail"])
def test_publication_wrapper_preserves_exact_arguments_result_exception_and_global_fence(world, monkeypatch, outcome):
    job_id = kickoff(world, synchronous=True)
    originals = rows(world.engine, db.deck_impressions_table)
    payload = {"user_id": OPP, "league_id": LEAGUE, "scoring_format": FMT,
        "rankings": [{"player_id": "a1", "elo": 1400., "comparison_count": 7}],
        "comparison_counts": {"a1": 7}, "confidence_source": "explicit"}
    write, invalidate = server.upsert_member_rankings, server._invalidate_trade_jobs
    events = []
    marker, failure = object(), RuntimeError("original writer exception")
    def observed_write(*args, **kwargs):
        assert not args and kwargs == payload
        assert kwargs["rankings"] is payload["rankings"]
        assert kwargs["comparison_counts"] is payload["comparison_counts"]
        events.append("write_enter")
        if outcome == "fail_before":
            raise failure
        write(**kwargs)
        events.append("write_committed")
        if outcome == "commit_then_fail":
            raise failure
        return marker
    def observed_fence(**kwargs):
        assert kwargs == {"user_id": OPP}
        events.append("global_fence")
        return invalidate(**kwargs)
    monkeypatch.setattr(server, "upsert_member_rankings", observed_write)
    monkeypatch.setattr(server, "_invalidate_trade_jobs", observed_fence)
    if outcome == "success":
        assert server._publish_member_rankings_for_trade_refresh(**payload) is marker
    else:
        with pytest.raises(RuntimeError) as error:
            server._publish_member_rankings_for_trade_refresh(**payload)
        assert error.value is failure
    assert events == (["write_enter", "global_fence"] if outcome == "fail_before"
                      else ["write_enter", "write_committed", "global_fence"])
    persisted = db.load_member_rankings(LEAGUE, "", FMT)[OPP]["elo_ratings"]["a1"]
    assert persisted == (1700. if outcome == "fail_before" else 1400.)
    assert rows(world.engine, db.deck_impressions_table) == originals
    assert_revoked(world, job_id)


_PUBLICATION_CALLS = {
    "post_rank3": "user_id=g_user_id, league_id=g_league.league_id, rankings=ranking_payload, scoring_format=fmt, **_conf",
    "copy_tiers_from_format_route": "user_id=g_user_id, league_id=g_league.league_id, rankings=ranking_payload, scoring_format=to_format, **_conf",
    "save_tiers_route": "user_id=g_user_id, league_id=g_league.league_id, rankings=ranking_payload, scoring_format=fmt, **_conf",
    "save_anchor_route": "user_id=g_user_id, league_id=g_league.league_id, rankings=ranking_payload, scoring_format=fmt, **_conf",
    "reorder_rankings": "user_id=g_user_id, league_id=g_league.league_id, rankings=ranking_payload, scoring_format=fmt, **_conf",
    "rankings_import_apply": "user_id=g_user_id, league_id=g_league.league_id, rankings=_import_payload, scoring_format=fmt, **_conf",
    "submit_rankings": "user_id=user_id, league_id=league_id, rankings=payload, scoring_format=_active_format(sess), **_conf",
}


@pytest.mark.parametrize("name,arguments", _PUBLICATION_CALLS.items())
def test_each_explicit_publication_keeps_original_payload_and_confidence_arguments(name, arguments):
    source = ast.parse(inspect.getsource(inspect.unwrap(getattr(server, name))))
    calls = [node for node in ast.walk(source) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"_publish_member_rankings_for_trade_refresh", "upsert_member_rankings"}]
    assert len(calls) == 1
    expected = ast.parse(f"_publish_member_rankings_for_trade_refresh({arguments})").body[0].value
    assert ast.dump(calls[0], include_attributes=False) == ast.dump(expected, include_attributes=False)


def test_only_seven_explicit_publish_sites_use_wrapper_not_init_or_replenishment():
    source = ast.parse(inspect.getsource(server))
    wrappers, raw_writes = [], []
    for function in source.body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "_publish_member_rankings_for_trade_refresh":
                wrappers.append(function.name)
            elif node.func.id == "upsert_member_rankings":
                raw_writes.append(function.name)
    assert sorted(wrappers) == sorted(_PUBLICATION_CALLS)
    assert raw_writes == ["_publish_member_rankings_for_trade_refresh"]
