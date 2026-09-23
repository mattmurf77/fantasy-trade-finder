"""Actual matched-like continuation and admission-input race controls."""
from copy import deepcopy

from sqlalchemy import insert, update

from backend import database as db, prepared_trade_runtime as runtime, server
from backend import prepared_trade_store_v2 as store
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness, new_claim,
)
from backend.tests.test_prepared_trade_runtime import adopt
from backend.tests.test_owner_generator_routes import rows, TOKEN


def test_real_first_prefix_like_creating_match_keeps_unrelated_stream(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = store.peek_inventory(scope).header
    fresh = runtime.build_session(server, deepcopy(target))
    fresh.update(verified=True, last_active=0.)
    monkeypatch.setitem(server._sessions, TOKEN, fresh)
    monkeypatch.setattr(server, "record_event", lambda *a, **k: None)
    notifications = []
    monkeypatch.setattr(server, "create_notification", lambda *a, **k: notifications.append(k))
    commit = store.ensure_adoption_evidence
    attempts, acted = [], []

    def publish(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 2:
            job = server._trade_jobs["matched-first-action"]
            assert len(job["cards"]) == 30
            public = deepcopy(job["cards"][0])
            card = fresh["trade_svc"]._trade_cards[public["trade_id"]]
            proof = card.owner_evaluation.snapshot_json
            # This is a new real mirror decision after admission, not a
            # fixture-preseeded row hidden by the original source receipt.
            db.save_trade_decision(user_id=card.target_user_id, league_id=scope.league_id,
                trade_id="synthetic-counterparty-original", give_player_ids=card.receive_player_ids,
                receive_player_ids=card.give_player_ids, decision="like")
            response = client.post("/api/trades/swipe", headers={"X-Session-Token": TOKEN},
                json={"trade_id": card.trade_id, "impression_id": public["impression_id"], "decision": "like"})
            assert response.status_code == 200, response.json
            matches = rows(engine, db.trade_matches_table)
            assert len(matches) == 1 and matches[0]["status"] == "pending"
            assert card.owner_evaluation.snapshot_json == proof
            acted.append(card.trade_id)
        return commit(*args, **kwargs)

    monkeypatch.setattr(store, "ensure_adoption_evidence", publish)
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "matched-first-action")
    assert acted and notifications
    assert handled and job["status"] == "complete", job
    assert len(job["cards"]) > 30
    assert len(rows(engine, db.deck_impressions_table)) == cached["card_count"]
    visible = server._trade_job_public_view(deepcopy(job))["cards"]
    assert visible and acted[0] not in {card["trade_id"] for card in visible}
    assert store.peek_inventory(scope) is not None


def test_explicit_partner_edit_between_active_snapshot_and_full_admission_is_not_blessed(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = store.peek_inventory(scope).header
    fresh = runtime.build_session(server, deepcopy(target))
    capture = runtime.active_dependency_receipt
    changed = []

    def capture_then_change(*args, **kwargs):
        result = capture(*args, **kwargs)
        if not changed:
            peer = target["opponents"][0]
            with engine.begin() as conn:
                conn.execute(insert(db.member_rankings_table).values(user_id=peer["user_id"],
                    league_id=scope.league_id, player_id=peer["player_ids"][0], elo=1817.,
                    scoring_format=scope.scoring_format, confidence_source="explicit"))
            changed.append(True)
        return result

    monkeypatch.setattr(runtime, "active_dependency_receipt", capture_then_change)
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "admission-input-race")
    assert changed and not handled
    assert not job["cards"] and not fresh["trade_svc"]._trade_cards
    assert not rows(engine, db.deck_impressions_table)
    assert store.peek_inventory(scope).header == cached


def test_roster_write_during_admission_index_cannot_become_new_read_baseline(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    from backend import prepared_trade_runtime_v2 as paged_runtime
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    fresh = runtime.build_session(server, deepcopy(target))
    original_open = paged_runtime.open_attested_inventory
    changed = []

    def open_while_roster_changes(*args, **kwargs):
        original_check = kwargs["disposition_check"]

        def check_then_change(cards):
            accepted = original_check(cards)
            assert accepted is True
            if not changed:
                with engine.begin() as conn:
                    result = conn.execute(update(db.league_members_table).where(
                        db.league_members_table.c.league_id == scope.league_id,
                        db.league_members_table.c.user_id == target["opponents"][0]["user_id"])
                        .values(roster_data="[]"))
                    assert result.rowcount == 1
                changed.append(True)
            return accepted

        return original_open(*args, **{**kwargs, "disposition_check": check_then_change})

    monkeypatch.setattr(paged_runtime, "open_attested_inventory", open_while_roster_changes)
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "admission-roster-race")
    assert changed and handled
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert not job["cards"] and not fresh["trade_svc"]._trade_cards
    assert not rows(engine, db.deck_impressions_table)
