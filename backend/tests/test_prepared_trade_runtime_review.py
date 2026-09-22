"""Independent integration checks: real preparation, quiet sync and recovery.

Synthetic provider snapshots and isolated SQL only. No production/provider I/O.
The constructor, prepared capture, dependency receipt and store remain real.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import socket
import threading
import uuid

import pytest
from sqlalchemy import insert, update

from backend import database as db, feature_flags as ff, server, trade_service as ts
from backend import prepared_trade_runtime as runtime, prepared_trade_store as store
from backend import user_data_lifecycle as lifecycle
from backend.tests.test_owner_generator_routes import harness, owner_harness, rows, ME, LEAGUE
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_prepared_trade_runtime import adopt


@pytest.fixture
def headless(large_exclusive, monkeypatch):
    fixture = large_exclusive
    _, engine, session, _, league = fixture
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   prepared_trade_inventory_enabled=1.)
    ff._flags_cache.update({"trade.prepared_inventory": True, "picks.owned_sync": True})
    for name in ("_deck_exploration_enabled", "_likes_you_enabled", "_suggestion_telemetry_enabled",
                 "_deck_fatigue_enabled", "_deck_taste_enabled", "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    monkeypatch.setattr(server, "_deck_first_session_enabled", lambda: True)
    monkeypatch.setattr(server, "_trade_jobs", {})
    pool = {"players": session["players"], "seed": dict(session["service"]._seed)}
    monkeypatch.setattr(server, "g_universal_by_format", {"1qb_ppr": pool})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    raw = {p.id: {"fantasy_positions": [p.position], "injury_status": None} for p in pool["players"]}
    monkeypatch.setattr(server, "_sleeper_cache", raw)
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: raw)
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: 1.)
    monkeypatch.setattr(server, "_FA_LEAGUE_META_CACHE", {})
    def forbidden(*a, **k):
        pytest.fail("preparation unexpectedly fetched, notified or recorded activity")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(server, "_sleeper_get", forbidden)
    monkeypatch.setattr(server, "record_event", forbidden)
    target = {"user_id": ME, "league_user_id": ME, "league_id": LEAGUE,
        "platform": "sleeper", "scoring_format": "1qb_ppr", "scoring_basis": "saved",
        "native_team_key": "1", "user_roster": ["g"],
        "opponents": [{"user_id": m.user_id, "team_id": str(i + 1),
                       "player_ids": list(m.roster), "name": m.username}
                      for i, m in enumerate(league.members) if m.user_id != ME],
        "binding_evidence": {"kind": "sleeper_owner", "owner_id": ME},
        "source": {"league_id": LEAGUE, "platform": "sleeper", "season": 2026,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"name": "Synthetic", "season": "2026", "total_rosters": 5,
                         "settings": {"draft_rounds": 1}, "roster_positions": ["WR"] + ["BN"] * 16},
            "teams": [{"team_id": str(i + 1), "owner_id": m.user_id, "co_owners": [],
                       "player_ids": list(m.roster), "name": m.username, "reserve": [], "taxi": [],
                       "availability_source": "observed"} for i, m in enumerate(league.members)],
            "traded_picks": [], "drafts": [{"season": "2026", "status": "complete"}],
            "future_picks": [], "limitations": [], "fingerprint": "synthetic"}}
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=ME, created_at="2026-01-01",
            tier_overrides=json.dumps({"1qb_ppr": session["service"]._elo_overrides})))
        conn.execute(insert(db.leagues_table).values(sleeper_league_id=LEAGUE, user_id=ME,
            season="2026", platform="sleeper", default_scoring="1qb_ppr",
            roster_data=json.dumps(["g"]), opponent_data=json.dumps(target["opponents"])))
        conn.execute(insert(db.league_members_table), [{"league_id": LEAGUE, "user_id": m.user_id,
            "roster_data": json.dumps(m.roster)} for m in league.members])
    monkeypatch.setattr(runtime, "refresh_target", lambda *a: deepcopy(target))
    return fixture, target


def new_claim(target, *, now=None, lease_seconds=300):
    scope = runtime.scope_for(ME, LEAGUE, ME, "1qb_ppr", .5)
    participants = sorted({ME, *(m["user_id"] for m in target["opponents"])})
    sweep = store.create_sweep(uuid.uuid4().hex, [{"scope": scope.as_dict(),
        "participants": participants, "binding": {"fairness": .5}}],
        started=lifecycle.snapshot(), now=now, coverage={"eligible": 1})
    return scope, sweep, store.claim_target(sweep, now=now, lease_seconds=lease_seconds)


def test_real_headless_prepare_syncs_under_all_participant_leases_and_reuses(headless, monkeypatch):
    fixture, target = headless
    _, engine, session, service, _ = fixture
    scope, sweep, claim = new_claim(target)
    calls = {"sync": 0, "worker": 0}
    original_sync, original_worker = server._sync_sleeper_owned_picks, server._run_trade_job
    def sync(*a, **k):
        calls["sync"] += 1
        assert k["traded_picks"] == [] and k["drafts"] == target["source"]["drafts"]
        assert all(lifecycle._state(uid).readers.get(threading.get_ident()) for uid in claim["participants"])
        return original_sync(*a, **k)
    def worker(*a, **k):
        calls["worker"] += 1
        return original_worker(*a, **k)
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", sync)
    monkeypatch.setattr(server, "_run_trade_job", worker)
    runtime.prepare_target(server, claim)
    cached = store.peek_inventory(scope)
    assert cached and cached["card_count"] >= 64
    assert rows(engine, db.draft_picks_table)  # Actual validated-source ledger sync.
    assert store.sweep_status(sweep)["status"] == "complete"
    before_picks = rows(engine, db.draft_picks_table)
    _, second_sweep, second_claim = new_claim(target)
    runtime.prepare_target(server, second_claim)
    after = store.peek_inventory(scope)
    assert calls == {"sync": 2, "worker": 1}
    assert after["inventory_id"] == cached["inventory_id"]
    assert after["created_at"] == cached["created_at"] and after["expires_at"] == cached["expires_at"]
    assert store.sweep_status(second_sweep)["counts"] == {"reused": 1}
    assert store.sweep_status(second_sweep)["unexpired_artifacts"] == 1
    assert len(rows(engine, db.draft_picks_table)) == len(before_picks)
    assert not server._trade_jobs and not service._trade_cards
    assert session["last_active"] == 0.
    for table in (db.deck_impressions_table, db.trade_impressions_table, db.deck_outcomes_table,
                  db.trade_decisions_table, db.user_events_table, db.bakeoff_runs_table):
        assert rows(engine, table) == []


def test_disabled_pick_sync_cannot_prepare_or_touch_existing_ledger(headless, monkeypatch):
    fixture, target = headless
    _, engine, *_ = fixture
    scope, _, claim = new_claim(target)
    ff._flags_cache["picks.owned_sync"] = False
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", lambda *a, **k: pytest.fail("disabled pick sync"))
    monkeypatch.setattr(server, "_run_trade_job", lambda *a, **k: pytest.fail("unsafe worker"))
    with pytest.raises(ValueError, match="source_pick_sync_disabled"):
        runtime.prepare_target(server, claim)
    assert store.peek_inventory(scope) is None
    assert not rows(engine, db.draft_picks_table)


def test_real_preparation_adopts_equivalent_fresh_session_with_actual_receipt(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, original_service, _ = fixture
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = store.peek_inventory(scope)
    assert cached and cached["card_count"] >= 64
    fresh = runtime.build_session(server, deepcopy(target))
    assert runtime.dependency_receipt(server, scope, fresh, target) == cached["dependency_receipt"]
    context_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((context_fixture, None, scope, None), monkeypatch, "real-receipt-adoption")
    assert handled and job["status"] == "complete", job
    assert len(job["cards"]) == cached["card_count"]
    assert [row["trade_id"] for row in job["cards"]] == [row["runtime"]["trade_id"]
        for row in cached["payload"]["inventory"]["cards"]]
    assert len(rows(engine, db.deck_impressions_table)) == cached["card_count"]
    assert len(fresh["trade_svc"]._trade_cards) == cached["card_count"]
    assert not original_service._trade_cards
    assert not rows(engine, db.trade_decisions_table) and not rows(engine, db.user_events_table)


def test_deleted_original_claim_cannot_sync_or_regenerate(headless, monkeypatch):
    fixture, target = headless
    scope, _, claim = new_claim(target)
    with lifecycle.hold([ME]):
        lifecycle.invalidate([ME])
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", lambda *a, **k: pytest.fail("deleted user sync"))
    monkeypatch.setattr(server, "_run_trade_job", lambda *a, **k: pytest.fail("deleted user worker"))
    with pytest.raises(ValueError, match="account_deleted"):
        runtime.prepare_target(server, claim)
    assert store.peek_inventory(scope) is None
    assert not rows(fixture[1], db.draft_picks_table)


@pytest.mark.parametrize("change", ["board", "source"])
def test_completed_generation_cannot_save_if_actual_inputs_changed(headless, monkeypatch, change):
    fixture, target = headless
    _, engine, session, service, _ = fixture
    scope, _, claim = new_claim(target)
    original = server._run_trade_job
    def worker(*a, **k):
        result = original(*a, **k)
        assert server._trade_jobs[a[0]]["prepared_count"] >= 64
        if change == "board":
            changed = dict(session["service"]._elo_overrides)
            changed["g"] += 100.
            with engine.begin() as conn:
                conn.execute(update(db.users_table).where(db.users_table.c.sleeper_user_id == ME)
                    .values(tier_overrides=json.dumps({"1qb_ppr": changed})))
        else:
            target["source"]["teams"][0]["reserve"] = ["g"]
        return result
    monkeypatch.setattr(server, "_run_trade_job", worker)
    with pytest.raises(ValueError, match="inputs_changed"):
        runtime.prepare_target(server, claim)
    assert store.peek_inventory(scope) is None
    assert not server._trade_jobs and not service._trade_cards
    assert not rows(engine, db.deck_impressions_table)


def test_scheduler_resumes_expired_claim_without_rediscovering_or_resetting_cohort(headless, monkeypatch):
    _, target = headless
    now = datetime.now(timezone.utc)
    _, sweep, abandoned = new_claim(target, now=now, lease_seconds=1)
    monkeypatch.setattr(runtime, "utcnow", lambda: now + timedelta(seconds=2))
    monkeypatch.setattr(runtime, "_active", False)
    monkeypatch.setattr(runtime, "_state", {"status": "idle"})
    monkeypatch.setattr(runtime, "discover", lambda *a: pytest.fail("resume rediscovered cohort"))
    completed = []
    def finish(_server, claim):
        completed.append(claim)
        store.complete_target(claim, status="error", reason="synthetic_stop", now=runtime.utcnow())
    monkeypatch.setattr(runtime, "prepare_target", finish)
    class InlineThread:
        def __init__(self, *, target, **kwargs): self.target = target
        def start(self): self.target()
    monkeypatch.setattr(runtime.threading, "Thread", InlineThread)
    result = runtime.start(server, idempotency_key="resume-test", resume_sweep_id=sweep)
    assert result["status"] == "complete" and len(completed) == 1
    assert completed[0]["target_id"] == abandoned["target_id"]
    assert completed[0]["lease_token"] != abandoned["lease_token"]
    assert store.sweep_status(sweep)["coverage"] == {"eligible": 1}
    assert not runtime._active


def test_scheduler_waits_for_deferred_claim_instead_of_abandoning_sweep(headless, monkeypatch):
    _, target = headless
    now = [datetime.now(timezone.utc)]
    _, sweep, claim = new_claim(target, now=now[0])
    store.complete_target(claim, status="deferred", reason="interactive_work",
                          retry_at=now[0] + timedelta(seconds=10), now=now[0])
    monkeypatch.setattr(runtime, "utcnow", lambda: now[0])
    monkeypatch.setattr(runtime, "_active", False)
    monkeypatch.setattr(runtime, "_state", {"status": "idle"})
    waits, attempts = [], []
    def sleep(seconds):
        waits.append(seconds)
        assert len(waits) <= 3, "scheduler failed to reclaim deferred target"
        now[0] += timedelta(seconds=seconds)
    monkeypatch.setattr(runtime.time, "sleep", sleep)
    def finish(_server, recovered):
        attempts.append(recovered)
        store.complete_target(recovered, status="error", reason="synthetic_stop", now=now[0])
    monkeypatch.setattr(runtime, "prepare_target", finish)
    class InlineThread:
        def __init__(self, *, target, **kwargs): self.target = target
        def start(self): self.target()
    monkeypatch.setattr(runtime.threading, "Thread", InlineThread)
    result = runtime.start(server, idempotency_key="deferred-test", resume_sweep_id=sweep)
    assert result["status"] == "complete" and waits == [5, 5] and len(attempts) == 1
