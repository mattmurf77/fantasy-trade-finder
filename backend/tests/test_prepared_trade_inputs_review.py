"""Independent active-vs-admission input contract, using isolated real SQL."""
from copy import deepcopy

import pytest
from sqlalchemy import insert, update

from backend import database as db, prepared_trade_runtime as runtime, server
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness,
)


def context(headless):
    _, target = headless
    session = runtime.build_session(server, deepcopy(target))
    scope = runtime.scope_for(target["user_id"], target["league_id"], target["league_user_id"],
                              target["scoring_format"], .5)
    return scope, session, target


@pytest.mark.parametrize("decision_type", ["trade", "disposition"])
def test_only_known_ordinary_feedback_can_change_without_active_input_miss(headless, decision_type):
    scope, session, target = context(headless)
    active_before = runtime.active_dependency_receipt(server, scope, session, target)
    full_before = runtime.dependency_receipt(server, scope, session, target)
    give, receive = target["user_roster"][0], target["opponents"][0]["player_ids"][0]
    session["service"].record_trade_signal(winner_ids=[receive], loser_ids=[give])
    db.save_trade_swipes(scope.user_id, [receive], [give], 8., decision_type=decision_type,
                         scoring_format=scope.scoring_format)
    assert runtime.active_dependency_receipt(server, scope, session, target) == active_before
    full_after = runtime.dependency_receipt(server, scope, session, target)
    assert full_after != full_before
    assert full_after["records"] != full_before["records"]
    assert {"ratings", "dispositions", "presentment_exclusions"}.issubset(full_after)
    assert not {"ratings", "dispositions", "presentment_exclusions"} & active_before.keys()
    assert active_before["version"] != full_before["version"]


@pytest.mark.parametrize("decision_type", ["rank", "", "future_unrecognized_input"])
def test_explicit_and_unknown_swipe_types_remain_persistent_active_inputs(headless, decision_type):
    scope, session, target = context(headless)
    before = runtime.active_dependency_receipt(server, scope, session, target)
    peer = target["opponents"][0]
    with db.engine.begin() as conn:
        conn.execute(insert(db.swipe_decisions_table).values(user_id=peer["user_id"],
            winner_player_id=peer["player_ids"][0], loser_player_id=target["user_roster"][0],
            decision_type=decision_type, k_factor=32., scoring_format=scope.scoring_format))
    assert runtime.active_dependency_receipt(server, scope, session, target)["records"] != before["records"]


@pytest.mark.parametrize("changed", ["partner_board", "partner_outlook", "partner_asset", "own_tiers"])
def test_persisted_explicit_inputs_are_not_relaxed_by_feedback_split(headless, changed):
    scope, session, target = context(headless)
    before = runtime.active_dependency_receipt(server, scope, session, target)
    peer = target["opponents"][0]
    with db.engine.begin() as conn:
        if changed == "partner_board":
            conn.execute(insert(db.member_rankings_table).values(user_id=peer["user_id"],
                league_id=scope.league_id, player_id=peer["player_ids"][0], elo=1701.,
                scoring_format=scope.scoring_format, confidence_source="explicit"))
        elif changed == "partner_outlook":
            conn.execute(insert(db.league_preferences_table).values(user_id=peer["user_id"],
                league_id=scope.league_id, team_outlook="contender"))
        elif changed == "partner_asset":
            conn.execute(insert(db.asset_preferences_table).values(user_id=peer["user_id"],
                league_id=scope.league_id, player_id=peer["player_ids"][0], list_type="untouchable"))
        else:
            conn.execute(update(db.users_table).where(db.users_table.c.sleeper_user_id == scope.user_id)
                .values(tier_overrides='{"1qb_ppr":{"g":1810}}'))
    assert runtime.active_dependency_receipt(server, scope, session, target)["records"] != before["records"]


def test_active_input_reader_does_not_treat_current_history_as_immutable_inputs(headless, monkeypatch):
    scope, session, target = context(headless)
    before = runtime.active_dependency_receipt(server, scope, session, target)
    for name in ("_load_trade_disposition_keys", "_load_presentment_exclusions"):
        monkeypatch.setattr(server, name, lambda *a, **k: pytest.fail("history belongs to current-card projection"))
    assert runtime.active_dependency_receipt(server, scope, session, target) == before
