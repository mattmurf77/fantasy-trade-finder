"""Prepared R4 must honor the same kill switch as actual Bilateral2 generation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from backend import database as db, feature_flags as ff, server
from backend import prepared_trade_runtime as runtime, prepared_trade_store_v2 as store
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness, new_claim,
)
from backend.tests.test_prepared_trade_runtime import adopt
from backend.tests.test_owner_generator_routes import rows


def _empty_history(monkeypatch, *, passes=()):
    history = SimpleNamespace(discovery_keys=lambda *a, **k: (set(), set(passes)),
                              likes=lambda **k: [])
    monkeypatch.setattr(server, "load_trade_interest_history", lambda *a, **k: history)
    monkeypatch.setattr(server, "load_trade_card_source_likes", lambda *a, **k: {})


@pytest.mark.parametrize("kind", ["awaiting", "matched"])
def test_r4_off_preserves_prepared_packages_without_consulting_disabled_history(monkeypatch, kind):
    monkeypatch.setattr(ff, "_flags_cache", {**(ff._flags_cache or {}), "trade.presentment_rules": False})
    assert not server.FLAGS.trade_presentment_rules
    _empty_history(monkeypatch)
    cards = [{"trade_id": "kept", "give": [{"id": "a"}], "receive": [{"id": "b"}]}]

    def forbidden(*a, **k):
        raise AssertionError("disabled R4 history was read")

    monkeypatch.setattr(server, "load_awaiting_trades", forbidden if kind == "awaiting" else lambda *a: [])
    monkeypatch.setattr(server, "load_matches_for_exclusion", forbidden if kind == "matched" else lambda *a: [])
    assert server._project_trade_dispositions(cards, "owner", "league", prepared=True) == cards


@pytest.mark.parametrize("guard", ["exact_pass", "resolved_source_interest"])
def test_r4_off_does_not_disable_independent_pass_or_source_like_safety(monkeypatch, guard):
    monkeypatch.setattr(ff, "_flags_cache", {**(ff._flags_cache or {}), "trade.presentment_rules": False})
    package = (frozenset({"a"}), frozenset({"b"}))
    _empty_history(monkeypatch, passes=[package] if guard == "exact_pass" else [])
    monkeypatch.setattr(server, "load_awaiting_trades", lambda *a: [])
    monkeypatch.setattr(server, "load_matches_for_exclusion", lambda *a: [])
    cards = [{"trade_id": "blocked", "give": [{"id": "a"}], "receive": [{"id": "b"}],
              "target_user_id": "peer", "likes_you": guard == "resolved_source_interest"}]
    assert server._project_trade_dispositions(cards, "owner", "league", prepared=True) == []


@pytest.mark.parametrize("kind", ["old_awaiting", "pending_match"])
def test_actual_flag_off_bilateral_inventory_remains_adoptable_with_r4_only_history(headless, monkeypatch, kind):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    monkeypatch.setattr(ff, "_flags_cache", {**(ff._flags_cache or {}), "trade.presentment_rules": False})
    scope, _, initial_claim = new_claim(target)
    runtime.prepare_target(server, initial_claim)
    original = store.peek_inventory(scope).read_admission(0, 1)[0]
    give, receive = original["give_player_ids"], original["receive_player_ids"]
    if kind == "pending_match":
        db.create_trade_match(scope.league_id, scope.user_id, original["target_user_id"], give, receive)
    else:
        db.save_trade_decision(user_id=scope.user_id, league_id=scope.league_id,
            trade_id="old-awaiting-compatibility", give_player_ids=give,
            receive_player_ids=receive, decision="like")
        with engine.begin() as conn:
            conn.execute(update(db.trade_decisions_table).where(
                db.trade_decisions_table.c.trade_id == "old-awaiting-compatibility")
                .values(created_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat()))
    key = (frozenset(give), frozenset(receive))
    assert key in server._load_presentment_exclusions(scope.user_id, scope.league_id)
    assert key not in server._load_trade_disposition_keys(scope.user_id, scope.league_id)[0]
    # Fresh real generation with the history already present must still emit
    # this package when R4 is OFF. Capture/adoption may not silently turn it ON.
    _, _, next_claim = new_claim(target)
    runtime.prepare_target(server, next_claim)
    reader = store.peek_inventory(scope)
    header = reader.header
    entries = reader.read_admission(0, header["card_count"])
    expected = [entry for entry in entries if (frozenset(entry["give_player_ids"]),
        frozenset(entry["receive_player_ids"])) == key]
    assert expected
    fresh = runtime.build_session(server, deepcopy(target))
    assert runtime.dependency_receipt(server, scope, fresh, target) == header["dependency_receipt"]
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "r4-off-compatibility")
    assert handled and job["status"] == "complete", job
    visible = server._trade_job_public_view(deepcopy(job))["cards"]
    assert {entry["trade_id"] for entry in expected}.issubset(card["trade_id"] for card in visible)
    assert len(rows(engine, db.deck_impressions_table)) == header["card_count"]
