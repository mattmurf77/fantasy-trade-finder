"""419 T6: both real builders restore the same D-067 policy from DB rows.

The existing session-init harness isolates provider data and runs its own
background writes inline. No copies of the production window predicate.
"""
import json

import pytest
from sqlalchemy import insert

from backend import database as db, server
from backend.tests.test_session_init_sleeper_calls import (
    harness as init_harness, _init, USER_ID, NON_SLEEPER_LEAGUE,
)
from backend.tests.test_trade_interest_disposition import Clock


@pytest.mark.parametrize("builder", ["interactive", "replenish"])
@pytest.mark.parametrize("action,at,days,amnesty,expected", [
    ("pass", "2026-08-28T12:00:00Z", 14, 0, True),  # day 8
    ("pass", "2026-08-23T12:00:00Z", 14, 0, True),  # day 13
    ("pass", "2026-08-28T00:00:00Z", 8.5, 0, True),  # exact fractional boundary
    ("pass", "2026-08-27T23:59:59Z", 8.5, 0, False),
    ("pass", "2026-08-16T12:00:00Z", 30, 1787005800, False),
    ("pass", "2026-08-16T12:00:00Z", 30, 0, True),
    ("like", "2026-08-29T12:00:00Z", 14, 0, True),
    ("like", "2026-08-29T11:59:59Z", 14, 0, False),
    ("pass", "not-a-date", 14, 1787005800, True),
    ("pass", "2026-08-28T00:00:00-12:00", 8, 0, True),  # UTC boundary
])
def test_419_builders_restore_same_real_db_window(init_harness, monkeypatch,
        builder, action, at, days, amnesty, expected):
    client, _calls = init_harness
    monkeypatch.setattr(db, "datetime", Clock)
    monkeypatch.setattr(server, "datetime", Clock)
    cfg = {"pass_cooldown_days": days, "pass_cooldown_start_epoch": amnesty}
    original = server._deck_cfg
    monkeypatch.setattr(server, "_deck_cfg", lambda key, default: cfg.get(key, original(key, default)))
    with db.engine.begin() as conn:
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=USER_ID, league_id=NON_SLEEPER_LEAGUE, trade_id="restore_419",
            give_player_ids=json.dumps(["p1"]), receive_player_ids=json.dumps(["p2"]),
            decision=action, created_at=at))
    if builder == "interactive":
        response = _init(client, NON_SLEEPER_LEAGUE)
        assert response.status_code == 200, response.get_json()
        token = "budget-verified-token"
    else:
        token = server._build_replenish_session(USER_ID, NON_SLEEPER_LEAGUE)
        assert token is not None
    try:
        services = server._sessions[token]["trade_svcs"].values()
        exact = (frozenset(["p1"]), frozenset(["p2"]))
        assert services
        for service in services:
            assert (exact in service._past_decision_keys) is expected
            assert (exact in service._dismissed_decision_keys) is (expected and action == "pass")
    finally:
        if builder == "replenish":
            server._sessions.pop(token, None)


def test_419_both_builders_call_shared_production_restoration():
    import inspect
    for builder in (server.session_init, server._build_replenish_session):
        source = inspect.getsource(builder)
        assert "_load_trade_disposition_keys(" in source
        assert "since_days=7" not in source
