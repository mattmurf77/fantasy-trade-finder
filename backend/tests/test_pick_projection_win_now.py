"""Projected slot value reaches Win-Now through the same pricing path.

Win-Now prices next-season picks itself (`win_now_service.build_context`), so
it was the one consumer outside `server._priced_pick_value`. It now passes the
league's projection (`server._league_pick_projection`, via
`win_now_service._pick_projection`) to `pick_values.priced_pool_value`.
Fixtures are `test_win_now_service`'s own (frozen Sleeper world, flags off).
"""
import pytest

from backend import pick_values
from backend import win_now_service as service
from backend.tests.test_win_now_service import context_inputs, isolated_state  # noqa: F401

PICK = {"season": "2027", "round": 1, "original_roster_id": "1", "owner_user_id": "u1",
        "pick_id": "owned:first", "pool_value": 2117.0}


@pytest.fixture
def one_pick(monkeypatch):
    from backend import database as db
    monkeypatch.setattr(db, "load_draft_picks", lambda *_, **__: [dict(PICK)])


def test_build_context_prices_with_the_league_projection(context_inputs, one_pick, monkeypatch):
    """Sabotage: drop `projection=` in build_context → the sentinel never arrives."""
    actor, bundle, params, fetch, _ = context_inputs
    sentinel = object()
    seen = []
    monkeypatch.setattr(service, "_pick_projection", lambda lid: sentinel)
    monkeypatch.setattr(pick_values, "priced_pool_value",
                        lambda row, **kw: seen.append(kw.get("projection")) or 1234.0)
    context = service.build_context(actor, bundle, params, fetch)
    assert seen == [sentinel]
    assert next(a for a in service.public_assets(context) if a["id"] == "owned:first")


def test_flag_off_passes_no_projection_and_never_imports_the_server(context_inputs, one_pick,
                                                                     monkeypatch):
    actor, bundle, params, fetch, _ = context_inputs
    seen = []
    monkeypatch.setattr(pick_values, "priced_pool_value",
                        lambda row, **kw: seen.append(kw.get("projection", "absent")) or 1234.0)
    service.build_context(actor, bundle, params, fetch)       # is_enabled → False here
    assert seen == [None]
    assert service._pick_projection(bundle["league"]["league_id"]) is None
