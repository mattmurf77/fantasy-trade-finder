"""Real preparation -> SQL -> fresh-process-like adoption -> action fidelity."""
from datetime import datetime, timedelta, timezone
import copy
import json
import time
import uuid

import pytest
from sqlalchemy import insert, update

from backend import database as db, server, trade_service as ts, feature_flags as ff
from backend import prepared_trade_runtime as runtime, prepared_trade_store as store, user_data_lifecycle
from backend import prepared_trade_read_guard as read_guard
from backend.prepared_trade_payload import PreparedEvidenceCapture
from backend.tests.test_prepared_trade_capture import prepare
from backend.tests.test_owner_generator_routes import harness, owner_harness, rows, ME, LEAGUE, TOKEN
from backend.tests.test_owner_only_routes import exclusive, large_exclusive

REAL_RECEIPT = runtime.dependency_receipt


@pytest.fixture
def prepared(large_exclusive, monkeypatch):
    fixture = large_exclusive
    client, engine, session, service, league = fixture
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   prepared_trade_inventory_enabled=1.)
    ff._flags_cache["trade.prepared_inventory"] = True
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr", {
        "players": list(session["players"]), "seed": dict(session["service"]._seed)})
    monkeypatch.setattr(server, "_sleeper_cache", {p.id: {
        "fantasy_positions": [p.position], "injury_status": None} for p in session["players"]})
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: 60.)
    monkeypatch.setitem(server._FA_LEAGUE_META_CACHE, LEAGUE, (time.time(), {
        "roster_positions": ["WR", "WR", "BN"], "scoring_settings": {"rec": 1.}}))
    with engine.begin() as conn:
        if not conn.execute(db.users_table.select().where(db.users_table.c.sleeper_user_id == ME)).first():
            conn.execute(insert(db.users_table).values(sleeper_user_id=ME, created_at="2026-01-01"))
        if not conn.execute(db.leagues_table.select().where(db.leagues_table.c.sleeper_league_id == LEAGUE)).first():
            conn.execute(insert(db.leagues_table).values(sleeper_league_id=LEAGUE, user_id=ME,
                roster_data=json.dumps(session["user_roster"]), season="2026", default_scoring="1qb_ppr"))
        for member in league.members:
            if not conn.execute(db.league_members_table.select().where(
                    db.league_members_table.c.league_id == LEAGUE,
                    db.league_members_table.c.user_id == member.user_id)).first():
                conn.execute(insert(db.league_members_table).values(league_id=LEAGUE,
                    user_id=member.user_id, roster_data=json.dumps(member.roster)))
    job, isolated = prepare(fixture, monkeypatch)
    assert job["status"] == "complete", job.get("error")
    scope = runtime.scope_for(ME, LEAGUE, ME, "1qb_ppr", .5)
    participants = sorted({ME, *(m.user_id for m in league.members)})
    sweep = store.create_sweep(uuid.uuid4().hex, [{"scope": scope.as_dict(),
        "participants": participants, "binding": {"fairness": .5}}], started=user_data_lifecycle.snapshot())
    claim = store.claim_target(sweep)
    receipt, identity = {"inputs": "same"}, runtime.model_identity(server)
    target = {"user_roster": list(session["user_roster"]),
        "opponents": [{"user_id": m.user_id, "player_ids": m.roster} for m in league.members
                      if m.user_id != ME]}
    now = datetime.now(timezone.utc)
    store.save_inventory(claim, payload={"inventory": job["prepared_bundle"],
        "generation_job_id": job["job_id"], "mutations": [], "target": target,
        "job_fields": {"first_deck": True}}, dependency_receipt=receipt,
        model_identity=identity, participants=participants, created_at=now,
        expires_at=now + timedelta(hours=24))
    monkeypatch.setattr(runtime, "refresh_target", lambda *a: target)
    monkeypatch.setattr(runtime, "dependency_receipt", lambda *a, **k: receipt)
    return fixture, job, scope, isolated


def adopt(prepared, monkeypatch, job_id="adoption"):
    fixture, original, scope, isolated = prepared
    _, _, session, service, league = fixture
    context = server._capture_trade_execution(session, ME, LEAGUE, "1qb_ppr")
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
        "started_at": time.monotonic(), "cards": [], "error": None, "finished_at": None,
        "opponents_done": 0, "opponents_total": len(league.members), "is_pinned": False,
        "fairness_threshold": .5, "owner_model": server._bakeoff.owner_arm(),
        "owner_model_version": server._bakeoff.owner_version(),
        "significance_capture": server._capture_trade_significance()}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    handled = runtime.try_adopt(server, job_id=job_id, context=context, fairness=.5, prefs={})
    return handled, job


def test_restart_like_adoption_preserves_full_inventory_action_fields_and_ids(prepared, monkeypatch):
    fixture, original, _, isolated = prepared
    _, engine, session, service, _ = fixture
    committed = []
    real_save = store.ensure_adoption_evidence
    def observe(*args, **kwargs):
        before = len(service._trade_cards)
        try:
            result = real_save(*args, **kwargs)
        except Exception as exc:
            pytest.fail(f"adoption evidence writer rejected test batch: {exc}")
        committed.append((len(kwargs["rows"]), before))
        assert len(service._trade_cards) == before  # Commit strictly before publish.
        return result
    monkeypatch.setattr(store, "ensure_adoption_evidence", observe)
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["status"] == "complete", job
    assert committed[0] == (30, 0)
    assert len(job["cards"]) == original["prepared_count"] >= 64
    assert [r["trade_id"] for r in job["cards"]] == [r["runtime"]["trade_id"]
        for r in original["prepared_bundle"]["cards"]]
    assert len(rows(engine, db.deck_impressions_table)) == len(job["cards"])
    assert not rows(engine, db.trade_decisions_table)
    for public in job["cards"]:
        card = service._trade_cards[public["trade_id"]]
        before = isolated._trade_cards[card.trade_id]
        assert card.lane_shift == before.lane_shift
        assert card.owner_evaluation.snapshot_json == before.owner_evaluation.snapshot_json
        rebuilt = runtime.restore_action_card(server, body=public, user_id=ME, league_id=LEAGUE)
        assert rebuilt is not None and rebuilt.lane_shift == before.lane_shift
        assert rebuilt.owner_evaluation.snapshot_json == before.owner_evaluation.snapshot_json
    assert not rows(engine, db.user_events_table)


def test_first_commit_failure_exposes_nothing(prepared, monkeypatch):
    _, engine, _, service, _ = prepared[0]
    def fail(*a, **k):
        raise RuntimeError("synthetic writer failure")
    monkeypatch.setattr(store, "ensure_adoption_evidence", fail)
    handled, job = adopt(prepared, monkeypatch)
    assert not handled and not job["cards"]
    assert not service._trade_cards and not rows(engine, db.deck_impressions_table)


def test_stale_inputs_fall_back_without_evidence(prepared, monkeypatch):
    monkeypatch.setattr(runtime, "dependency_receipt", lambda *a, **k: {"inputs": "changed"})
    handled, job = adopt(prepared, monkeypatch)
    assert not handled and not job["cards"]
    assert not rows(prepared[0][1], db.deck_impressions_table)


def test_retry_reuses_original_commit_timestamps_and_identity(prepared, monkeypatch):
    handled, first = adopt(prepared, monkeypatch)
    assert handled and first["status"] == "complete"
    before = rows(prepared[0][1], db.deck_impressions_table)
    prepared[0][3]._trade_cards.clear()
    handled, second = adopt(prepared, monkeypatch, "after-process-restart")
    assert handled and second["status"] == "complete"
    assert before == rows(prepared[0][1], db.deck_impressions_table)
    assert first["cards"] == second["cards"]


def test_prepare_config_dark_disables_adoption_without_source_reads(prepared, monkeypatch):
    ts._cfg["prepared_trade_inventory_enabled"] = 0.
    monkeypatch.setattr(runtime, "refresh_target", lambda *a: pytest.fail("dark source read"))
    handled, job = adopt(prepared, monkeypatch)
    assert not handled and not job["cards"]


def test_admin_requires_operator_secret_and_dry_run_boolean(large_exclusive, monkeypatch):
    client = large_exclusive[0]
    monkeypatch.setattr(server, "_CRON_SECRET", "synthetic-prepared-secret")
    for method in (client.get, client.post, client.delete):
        assert method("/api/admin/prepared-trades").status_code in (401, 403)
    response = client.post("/api/admin/prepared-trades", headers={"X-Cron-Secret": "synthetic-prepared-secret"},
        json={"idempotency_key": "x", "dry_run": "yes"})
    assert response.status_code == 400


def test_real_receipt_reads_every_registered_dependency_without_provider_egress(large_exclusive, monkeypatch):
    _, _, session, _, league = large_exclusive
    context = server._capture_trade_execution(session, ME, LEAGUE, "1qb_ppr")
    session = runtime._session_for_context(context)
    scope = runtime.scope_for(ME, LEAGUE, ME, "1qb_ppr", .5)
    target = {"opponents": [{"user_id": m.user_id} for m in league.members if m.user_id != ME],
        "source": {"league_id": LEAGUE, "observed_at": datetime.now(timezone.utc).isoformat(),
                   "metadata": {}, "teams": []}, "binding_evidence": {"kind": "fixture"}}
    before = REAL_RECEIPT(server, scope, session, target)
    assert before == REAL_RECEIPT(server, scope, session, target)
    session["services"]["1qb_ppr"]._elo_overrides[next(iter(session["services"]["1qb_ppr"]._seed))] = 2222.
    after = REAL_RECEIPT(server, scope, session, target)
    assert before != after


def test_normalize_retest_never_hides_another_action():
    before = {"declined_at": "old", "expires_at": "expired", "retested_at": None,
              "retest_trade_hash": None, "lifted_at": None}
    mutation = {"kind": "retest", "id": 1, "trade_id": "t", "trade_hash": "hash", "before": before}
    row = {"id": 1, **before, "retested_at": "served", "retest_trade_hash": "hash"}
    runtime.normalize_own_mutations([row], [mutation], "served")
    assert row == {"id": 1, **before}
    row.update(retested_at="served", retest_trade_hash="hash", lifted_at="undo")
    runtime.normalize_own_mutations([row], [mutation], "served")
    assert row["lifted_at"] == "undo" and row["retested_at"] == "served"


def test_local_market_change_rejects_adopted_status_and_pending_without_erasing_evidence(prepared, monkeypatch):
    client, engine, _, service, _ = prepared[0]
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["status"] == "complete"
    assert server._trade_job_public_view(copy.deepcopy(job))["cards"]
    before = rows(engine, db.deck_impressions_table)
    assert client.get("/api/trades", headers={"X-Session-Token": TOKEN}).json
    server.g_universal_by_format["1qb_ppr"]["seed"]["g"] += 1.
    assert not server._prepared_job_matches(job)
    assert not server._trade_job_public_view(copy.deepcopy(job))["cards"]
    assert not client.get("/api/trades", headers={"X-Session-Token": TOKEN}).json
    assert rows(engine, db.deck_impressions_table) == before
    assert service._trade_cards  # Hiding a stale read is not historical deletion.


def test_local_roster_change_during_read_projection_is_caught_after_serialization(prepared, monkeypatch):
    _, engine, _, _, _ = prepared[0]
    handled, job = adopt(prepared, monkeypatch)
    assert handled
    original = server._project_trade_dispositions
    def race(*a, **k):
        result = original(*a, **k)
        with engine.begin() as conn:
            conn.execute(update(db.league_members_table).where(
                db.league_members_table.c.league_id == LEAGUE).values(roster_data='["changed"]'))
        return result
    monkeypatch.setattr(server, "_project_trade_dispositions", race)
    view = server._trade_job_public_view(copy.deepcopy(job))
    assert view["status"] == "error" and not view["cards"]


@pytest.mark.parametrize("bad", [None, [], {"scope": None}, {"scope": []}])
def test_malformed_adopted_job_guard_fails_closed(prepared, monkeypatch, bad):
    handled, job = adopt(prepared, monkeypatch)
    assert handled
    job["prepared_guard"] = bad
    assert not server._prepared_job_matches(job)
    assert not server._trade_job_public_view(copy.deepcopy(job))["cards"]


def test_missing_guard_source_is_cache_miss_with_no_partial_exposure_or_artifact_loss(prepared, monkeypatch):
    _, engine, _, service, _ = prepared[0]
    before = rows(engine, db.prepared_trade_inventories_table)
    monkeypatch.setattr(server, "_sleeper_cache", None)
    handled, job = adopt(prepared, monkeypatch)
    assert not handled and not job["cards"] and not service._trade_cards
    assert not rows(engine, db.deck_impressions_table)
    after = rows(engine, db.prepared_trade_inventories_table)
    assert len(before) == len(after) == 1
    assert before[0]["payload_sha256"] == after[0]["payload_sha256"]
    assert after[0]["adoption_token"] is None


def test_market_change_after_first_prefix_revokes_all_instead_of_leaving_stale_cards(prepared, monkeypatch):
    _, engine, _, service, _ = prepared[0]
    original, commits = store.ensure_adoption_evidence, []
    def after_commit(*a, **k):
        result = original(*a, **k)
        commits.append(len(k["rows"]))
        if len(commits) == 2:
            # First30 were public; full admission receipt intentionally uses
            # the captured request pool, while read guard uses current globals.
            server.g_universal_by_format["1qb_ppr"]["seed"]["g"] += 1.
        return result
    monkeypatch.setattr(store, "ensure_adoption_evidence", after_commit)
    handled, job = adopt(prepared, monkeypatch)
    assert handled and commits[0] == 30 and len(commits) == 2
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert not job["cards"] and not service._trade_cards
    assert rows(engine, db.deck_impressions_table)  # Preserve committed history.


def test_restored_committed_card_swipe_uses_server_terms_and_lane_weight(prepared, monkeypatch):
    client, engine, session, service, _ = prepared[0]
    handled, job = adopt(prepared, monkeypatch)
    assert handled
    public = job["cards"][0]
    original = service._trade_cards[public["trade_id"]]
    service._trade_cards.clear()
    calls = []
    monkeypatch.setattr(session["service"], "record_trade_signal", lambda **kw: calls.append(kw))
    response = client.post("/api/trades/swipe", headers={"X-Session-Token": TOKEN},
        json={"trade_id": public["trade_id"], "impression_id": public["impression_id"],
              "decision": "pass", "give_player_ids": ["forged"], "receive_player_ids": ["forged2"]})
    assert response.status_code == 200, response.json
    restored = service._trade_cards[public["trade_id"]]
    assert restored.give_player_ids == original.give_player_ids
    assert restored.receive_player_ids == original.receive_player_ids
    assert restored.owner_evaluation.snapshot_json == original.owner_evaluation.snapshot_json
    assert calls[0]["fit_mult"] == server._bakeoff.elo_freeze_mult(
        ts.fit_congruence_mult(original.lane_shift, "pass"))


@pytest.mark.parametrize("failure", ["invalid_decision", "invalid_evidence"])
def test_failed_restore_action_cannot_publish_or_use_client_fallback(prepared, monkeypatch, failure):
    client, engine, session, service, _ = prepared[0]
    handled, job = adopt(prepared, monkeypatch)
    assert handled
    public = job["cards"][0]
    service._trade_cards.clear()
    if failure == "invalid_evidence":
        original_load = server.load_deck_impression
        def bad_evidence(iid):
            row = copy.deepcopy(original_load(iid))
            features = row["features_json"]
            if isinstance(features, str):
                features = json.loads(features)
            features["prepared_runtime"]["runtime"]["give_player_ids"] = ["forged"]
            row["features_json"] = features
            return row
        monkeypatch.setattr(server, "load_deck_impression", bad_evidence)
    monkeypatch.setattr(server, "_reconstruct_swipe_card", lambda *a: pytest.fail("client fallback"))
    response = client.post("/api/trades/swipe", headers={"X-Session-Token": TOKEN}, json={
        "trade_id": public["trade_id"], "impression_id": public["impression_id"],
        "decision": "invalid" if failure == "invalid_decision" else "pass",
        "give_player_ids": ["forged"], "receive_player_ids": ["forged2"]})
    assert response.status_code == 400
    assert not service._trade_cards and not rows(engine, db.trade_decisions_table)


def test_pending_rechecks_read_guard_after_serialization(prepared, monkeypatch):
    client = prepared[0][0]
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["cards"]
    original = server.trade_card_to_dict
    def serialize(*a, **kw):
        result = original(*a, **kw)
        ts._cfg["prepared_trade_inventory_enabled"] = 0.
        return result
    monkeypatch.setattr(server, "trade_card_to_dict", serialize)
    response = client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200 and response.json == []


def test_job_guard_cannot_extend_original_card_expiry():
    now = datetime.now(timezone.utc)
    cached = {"expires_at": (now + timedelta(hours=24)).isoformat(),
              "payload": {"inventory": {"cards": []}}}
    assert runtime._guard_expiry(cached) == now + timedelta(hours=24)
    cached["payload"]["inventory"]["cards"] = [
        {"runtime": {"expires_at": (now + timedelta(minutes=2)).isoformat()}},
        {"runtime": {"expires_at": (now + timedelta(days=7)).isoformat()}}]
    assert runtime._guard_expiry(cached) == now + timedelta(minutes=2)


def test_unattended_replenishment_cannot_adopt_as_an_interactive_request(prepared, monkeypatch):
    session = prepared[0][2]
    monkeypatch.setattr(runtime, "try_adopt", lambda *a, **k: pytest.fail("background adoption"))
    generated = []
    def generate(job_id, *a, **k):
        generated.append(job_id)
        server._finish_trade_job(job_id)
    monkeypatch.setattr(server, "_run_trade_job", generate)
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=ME, league_id=LEAGUE,
        scoring_format="1qb_ppr", fairness_threshold=.5, source="replenish",
        synchronous=True, session_context=session)
    assert generated == [job_id]


def replace_with_empty(prepared):
    scope = prepared[2]
    previous = store.peek_inventory(scope)
    payload = copy.deepcopy(previous["payload"])
    payload["inventory"] = PreparedEvidenceCapture(user_id=ME, league_id=LEAGUE,
        job_id=payload["generation_job_id"]).finish([], [])
    sweep = store.create_sweep(uuid.uuid4().hex, [{"scope": scope.as_dict(),
        "participants": previous["participants"], "binding": {"fairness": .5}}],
        started=user_data_lifecycle.snapshot())
    claim = store.claim_target(sweep)
    now = datetime.now(timezone.utc)
    store.save_inventory(claim, payload=payload, dependency_receipt=previous["dependency_receipt"],
        model_identity=runtime.model_identity(server), participants=previous["participants"],
        created_at=now, expires_at=now + timedelta(hours=24))


def test_valid_empty_inventory_is_completed_without_generation_or_exposure(prepared, monkeypatch):
    replace_with_empty(prepared)
    monkeypatch.setattr(server, "_run_trade_job", lambda *a, **k: pytest.fail("regenerated known empty"))
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["status"] == "complete" and not job["cards"]
    assert job["prepared_inventory_id"] and job["prepared_guard"]
    assert not rows(prepared[0][1], db.deck_impressions_table)


@pytest.mark.parametrize("empty", [False, True])
def test_claim_window_market_swap_cannot_be_blessed_by_late_guard_capture(prepared, monkeypatch, empty):
    if empty:
        replace_with_empty(prepared)
    original = store.claim_adoption
    def race(*a, **k):
        claim = original(*a, **k)
        server.g_universal_by_format["1qb_ppr"]["seed"]["g"] += 1.
        return claim
    monkeypatch.setattr(store, "claim_adoption", race)
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["status"] == "error" and job["error"] == "inputs_changed"
    assert not job["cards"] and not prepared[0][3]._trade_cards
    assert not rows(prepared[0][1], db.deck_impressions_table)


def test_pure_later_writer_failure_keeps_only_previously_durable_current_prefix(prepared, monkeypatch):
    real_save, count = store.ensure_adoption_evidence, []
    def fail_later(*a, **k):
        count.append(1)
        if len(count) == 2:
            raise RuntimeError("synthetic second batch outage")
        return real_save(*a, **k)
    monkeypatch.setattr(store, "ensure_adoption_evidence", fail_later)
    handled, job = adopt(prepared, monkeypatch)
    assert handled and job["status"] == "error" and job["error"] == "prepared_adoption_incomplete"
    assert len(job["cards"]) == len(prepared[0][3]._trade_cards) == 30
    assert len(server._trade_job_public_view(copy.deepcopy(job))["cards"]) == 30
    assert len(rows(prepared[0][1], db.deck_impressions_table)) == 30
