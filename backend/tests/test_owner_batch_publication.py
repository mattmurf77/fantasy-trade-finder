"""Real worker/logger/SQLite publication boundaries for cumulative clients."""
import copy
import math
import time

import pytest

from backend import database as db, server, trade_service as ts
from backend.ranking_service import Player, RankingService
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, rows, worker, ME, LEAGUE, TOKEN,
)
from backend.tests.test_owner_only_routes import exclusive, large_exclusive


@pytest.fixture
def sized_exclusive(exclusive, monkeypatch, request):
    """Real safe 1-for-1 construction, at most 16 returns per opponent."""
    count = request.param
    _, _, sess, service, league = exclusive
    rosters = {f"partner-{n}": [f"return-{i}" for i in range(n * 16, min(count, (n + 1) * 16))]
               for n in range((count + 15) // 16)}
    ids = ["give", *(p for roster in rosters.values() for p in roster)]
    players = [Player(id=p, name=p, position="WR", team="AAA", age=26) for p in ids]
    low, high = 1500 + math.log(.8) / .005, 1500 + math.log(1.2) / .005
    ranking = RankingService(players=players)
    ranking._seed = dict.fromkeys(ids, 1500.)
    ranking._elo_overrides.update({p: low if p == "give" else high for p in ids})
    monkeypatch.setattr(ranking, "placement_bands", lambda: {p: (1200, 1900) for p in ids})
    league.members = [ts.LeagueMember(user_id=ME, username="me", roster=["give"], elo_ratings={}),
        *(ts.LeagueMember(user_id=uid, username=uid, roster=roster, elo_ratings={})
          for uid, roster in rosters.items())]
    sess.update(players=players, user_roster=["give"], service=ranking, services={"1qb_ppr": ranking})
    service._players = {p.id: p for p in players}
    boards = {uid: {"elo_ratings": {p: low if p in roster else high for p in ids},
                    "confidence_sources": dict.fromkeys(ids, "explicit"), "username": uid}
              for uid, roster in rosters.items()}
    monkeypatch.setattr(server, "load_member_rankings", lambda *a, **k: boards)
    monkeypatch.setattr(server, "load_league_preferences_bulk", lambda *a: {
        uid: {"team_outlook": "not_sure"} for uid in [ME, *rosters]})
    monkeypatch.setattr(server, "_infer_user_outlook", lambda *a, **k: ("not_sure", None))
    return exclusive, count


def observe_batches(monkeypatch, engine, after_publish=None):
    original = server._log_deck_signal_impressions
    observed = {"snapshots": [], "cards": [], "batches": []}

    def log(**kwargs):
        assert kwargs["initial_publication_batch_size"] == 30
        assert kwargs["publication_batch_size"] == 100
        assert kwargs["structured_features"] is True
        observed["cards"] = list(kwargs["cards"])
        publish = kwargs["on_batch_committed"]

        def committed(batch, identities):
            job = server._trade_jobs["owner-route-worker"]
            previous = len(job["cards"])
            assert job["status"] == "running"
            persisted = {r["impression_id"]: r for r in rows(engine, db.deck_impressions_table)}
            # Each offered identity and global ordinal is durable before the
            # callback has an opportunity to put that offer into the API.
            for offset, card in enumerate(batch, previous):
                record = persisted[identities[id(card)]]
                assert record["card_index"] == offset
                assert record["valuation_json"]
                assert not getattr(card, "owner_published", False)
            publish(batch, identities)
            assert len(job["cards"]) == previous + len(batch)
            assert job["final_checks_pending"] is False
            assert all(getattr(c, "owner_published", False) for c in batch)
            observed["snapshots"].append(copy.deepcopy(job["cards"]))
            observed["batches"].append(len(batch))
            if after_publish:
                after_publish(job, batch)

        return original(**{**kwargs, "on_batch_committed": committed})

    monkeypatch.setattr(server, "_log_deck_signal_impressions", log)
    return observed


@pytest.mark.parametrize("bilateral", [False, True])
def test_first_30_are_durable_running_and_full_inventory_keeps_order(large_exclusive, monkeypatch, bilateral):
    client, engine, _, _, _ = large_exclusive
    ts._cfg["owner_bilateral_enabled"] = float(bilateral)
    responses = []

    def read_status(job, batch):
        response = client.get("/api/trades/status?job_id=owner-route-worker",
                              headers={"X-Session-Token": TOKEN})
        assert response.status_code == 200
        assert response.json["status"] == "running"
        assert [c["impression_id"] for c in response.json["cards"]] == [
            c["impression_id"] for c in job["cards"]]
        responses.append(response.json)

    observed = observe_batches(monkeypatch, engine, read_status)
    job = worker(large_exclusive, monkeypatch)
    assert observed["batches"] == [30, 34]
    assert len(job["cards"]) == 64
    assert [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in observed["cards"]]
    assert job["cards"][:30] == observed["snapshots"][0]
    assert observed["snapshots"][-1] == job["cards"]
    assert len({c["impression_id"] for c in job["cards"]}) == 64
    assert len(responses[0]["cards"]) == 30
    assert responses[0]["cards"] == job["cards"][:30]
    assert not rows(engine, db.trade_decisions_table)
    assert not rows(engine, db.deck_outcomes_table)


@pytest.mark.parametrize("sized_exclusive", [0, 1, 19, 30, 160], indirect=True)
def test_empty_short_and_multi_page_inventory_completes_without_cap(sized_exclusive, monkeypatch):
    fixture, count = sized_exclusive
    _, engine, *_ = fixture
    observed = observe_batches(monkeypatch, engine)
    job = worker(fixture, monkeypatch)
    assert len(job["cards"]) == count
    assert observed["batches"] == ([30, 100, 30] if count == 160 else [count] if count else [])
    assert [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in observed["cards"]]
    persisted = rows(engine, db.deck_impressions_table)
    assert sorted(r["card_index"] for r in persisted) == list(range(count))
    assert {r["impression_id"] for r in persisted} == {c["impression_id"] for c in job["cards"]}
    assert job["final_checks_pending"] is False


def test_null_impression_result_fails_closed(owner_harness, monkeypatch):
    monkeypatch.setattr(server, "_log_deck_signal_impressions", lambda **kwargs: None)
    job = worker(owner_harness, monkeypatch, expected_error="owner_impression_unavailable")
    assert job["cards"] == []
    assert job["final_checks_pending"] is False


@pytest.mark.parametrize("fail_batch,expected", [(1, 0), (2, 30)])
@pytest.mark.parametrize("targeted", [False, True])
def test_failed_write_exposes_only_previous_committed_prefix(large_exclusive, monkeypatch, fail_batch, expected, targeted):
    _, engine, _, _, _ = large_exclusive
    observed = observe_batches(monkeypatch, engine)
    original = server.save_deck_impressions
    writes = []

    def save(batch):
        writes.append(len(batch))
        if len(writes) == fail_batch:
            raise RuntimeError("injected database failure")
        return original(batch)

    monkeypatch.setattr(server, "save_deck_impressions", save)
    job = worker(large_exclusive, monkeypatch, give=["g"] if targeted else [],
                 expected_error="owner_impression_unavailable")
    assert len(job["cards"]) == expected
    assert len(rows(engine, db.deck_impressions_table)) == expected
    assert sum(bool(getattr(c, "owner_published", False)) for c in observed["cards"]) == expected
    assert not rows(engine, db.trade_decisions_table)
    assert not rows(engine, db.deck_outcomes_table)
    if expected:
        assert job["cards"] == observed["snapshots"][0]
    if targeted:
        assert rows(engine, db.bakeoff_runs_table)[0]["deck_size"] == expected


@pytest.mark.parametrize("revoke,expected_error", [
    ("inputs", "inputs_changed"), ("timeout", "generation_timeout"),
    ("supersede", "superseded"), ("model", "owner_model_changed"),
    ("significance", "significance_policy_changed"),
])
def test_revocation_after_first_batch_never_writes_or_publishes_tail(
        large_exclusive, monkeypatch, revoke, expected_error):
    _, engine, _, _, _ = large_exclusive
    completed_events = []
    monkeypatch.setattr(server, "record_event", lambda *args, **kwargs: completed_events.append(args))
    finished_at = []

    def stop(job, batch):
        if revoke == "inputs":
            server._invalidate_trade_jobs(user_id=ME, league_id=LEAGUE)
        elif revoke == "timeout":
            with server._trade_jobs_lock:
                job.update(status="error", error="generation_timeout", finished_at=time.monotonic())
        elif revoke == "supersede":
            with server._trade_jobs_lock:
                server._revoke_trade_job_locked(job, "superseded")
        elif revoke == "model":
            ts._cfg["owner_bilateral_enabled"] = 1.
        else:
            ts._cfg["significance_mode"] = 2.
        if job["status"] == "error":
            finished_at.append(job["finished_at"])

    observed = observe_batches(monkeypatch, engine, stop)
    job = worker(large_exclusive, monkeypatch, expected_error=expected_error)
    assert observed["batches"] == [30]
    assert len(rows(engine, db.deck_impressions_table)) == 30
    assert sum(bool(getattr(c, "owner_published", False)) for c in observed["cards"]) == 30
    if finished_at:
        assert job["finished_at"] == finished_at[0]
    assert not any(len(args) > 1 and args[1] == "trades_generated" for args in completed_events)
    assert len(job["cards"]) == (30 if revoke == "timeout" else 0)


def test_revocation_between_commit_and_callback_prevents_publication(large_exclusive, monkeypatch):
    _, engine, _, service, _ = large_exclusive
    original = server.save_deck_impressions

    def save(batch):
        result = original(batch)
        # A real invalidation wins even in the narrow post-commit interval.
        server._invalidate_trade_jobs(user_id=ME, league_id=LEAGUE)
        return result

    monkeypatch.setattr(server, "save_deck_impressions", save)
    # Revocation's truthful terminal state is allowed to leave the checks flag
    # pending; the generic worker fixture expects it cleared, so run directly.
    job_id = "between-commit"
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "cards": [], "opponents_done": 0,
           "opponents_total": 4, "error": None, "fairness_threshold": .5}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    server._run_trade_job(job_id, TOKEN, LEAGUE, .5, [], [])
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert job["cards"] == []
    assert len(rows(engine, db.deck_impressions_table)) == 30
    assert not any(getattr(c, "owner_published", False) for c in service._trade_cards.values())


def test_an_explicit_first_batch_action_joins_durable_identity_while_job_runs(large_exclusive, monkeypatch):
    client, engine, _, _, _ = large_exclusive
    acted = []

    def act(job, batch):
        if acted:
            return
        card = job["cards"][0]
        assert not rows(engine, db.trade_decisions_table)
        response = client.post("/api/trades/swipe", headers={"X-Session-Token": TOKEN}, json={
            "trade_id": card["trade_id"], "league_id": LEAGUE,
            "decision": "pass", "target_user_id": card["target_user_id"],
            "give_player_ids": [p["id"] for p in card["give"]],
            "receive_player_ids": [p["id"] for p in card["receive"]],
            "impression_id": card["impression_id"], "dwell_ms": 800,
        })
        assert response.status_code == 200, response.json
        assert job["status"] == "running"
        acted.append(card)

    observe_batches(monkeypatch, engine, act)
    job = worker(large_exclusive, monkeypatch)
    assert len(job["cards"]) == 64
    assert len(rows(engine, db.trade_decisions_table)) == 1
    outcomes = rows(engine, db.deck_outcomes_table)
    assert len(outcomes) == 1
    assert outcomes[0]["action"] == "pass"
    assert outcomes[0]["impression_id"] == acted[0]["impression_id"]
    assert acted[0] == job["cards"][0]
