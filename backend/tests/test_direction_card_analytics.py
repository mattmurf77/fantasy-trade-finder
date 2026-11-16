"""Improve pages and the Home playoff card: analytics registration (spec
docs/plans/league-projections/direction-pages/spec.md §9; D-265, D-270).
Harness mirrors test_playoff_targets_analytics.py.

The ingest allowlist is default-deny behind a 200, so the names and props are
registered in the same commit as the app's emitters.

- test_names_are_allowlisted_with_exact_props. Sabotage: register
  direction_card_shown without `pick_shown`.
- test_only_the_impression_is_non_intent. Sabotage: leave
  direction_card_shown out of NON_INTENT_EVENTS.
- test_home_tile_tapped_gains_via_and_the_new_tiles: `via` on the prop row,
  the three new tile values documented.
- test_events_land_with_every_prop: POST /api/events accepts the two new
  events and the sheet tap with their props intact.
"""
import inspect
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.analytics_queries as q
import backend.analytics_taxonomy as tax
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

_PROPS = {
    "direction_card_shown": {"band": "middle", "primary": "playoffs", "shown": "none", "sheet": True,
                             "pick_shown": True},
    "direction_page_opened": {"page": "draft_pick", "source": "sheet", "state": "ready"},
}
_TAP = {"tile": "improve_pick", "via": "sheet"}


def test_names_are_allowlisted_with_exact_props():
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name
        assert not {"platform", "player_id", "name", "player_name"} & tax.CLIENT_EVENT_PROPS[name]


def test_only_the_impression_is_non_intent():
    assert "direction_card_shown" in q.NON_INTENT_EVENTS and "direction_card_shown" not in q.INTENT_EVENTS
    assert "direction_page_opened" not in q.NON_INTENT_EVENTS
    # The card's taps keep home_tile_tapped's existing class.
    assert "home_tile_tapped" in q.NON_INTENT_EVENTS


def test_home_tile_tapped_gains_via_and_the_new_tiles():
    assert tax.CLIENT_EVENT_PROPS["home_tile_tapped"] == frozenset({"tile", "position", "band", "split", "via"})
    source = inspect.getsource(tax)
    for tile in ("playoff_options", "improve_playoffs | improve_pick"):
        assert tile in source, tile
    # The list bodies' events keep their shapes on the pages (only the screen changes).
    assert tax.CLIENT_EVENT_PROPS["maxpf_moves_viewed"] == frozenset({"state", "n_moves", "band", "n_listed", "any_pass"})
    assert tax.CLIENT_EVENT_PROPS["playoff_targets_viewed"] == frozenset(
        {"state", "n_listed", "any_pass", "n_sellers", "band"})
    assert tax.CLIENT_EVENT_PROPS["finder_target_pinned"] == frozenset({"side", "source"})


USER, TOKEN, DEVICE = "taxonomy_direction_test", "tax-direction-token", "dev_direct1"


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled", lambda k: k == "analytics.ingest"):
        with server._sessions_lock:
            server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with ingest._rate_lock:
                ingest._events_rate.clear()


def test_events_land_with_every_prop(harness):
    client, engine = harness
    sent = [("direction_card_shown", _PROPS["direction_card_shown"], "Home"),
            ("direction_page_opened", _PROPS["direction_page_opened"], "ImproveDraftPick"),
            ("home_tile_tapped", _TAP, "LeagueRankings")]
    events = [{"event_id": f"evtdc-{i:04d}", "event_type": name, "client_ts": "2026-11-15T12:00:00Z",
               "screen": screen, "props": props, "session_id": "sess-dc-0001", "seq": i + 1}
              for i, (name, props, screen) in enumerate(sent)]
    body = client.post("/api/events", headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
                       data=json.dumps({"events": events})).get_json()
    assert body["accepted"] == len(sent) and body["dropped"] == 0
    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table).order_by(user_events_table.c.id)).fetchall()
    by_type = {r._mapping["event_type"]: r._mapping for r in rows}
    for name, props, screen in sent:
        landed = {k: v for k, v in json.loads(by_type[name]["props"]).items() if k not in {"seq", "ts_suspect"}}
        assert landed == props, name
        assert by_type[name]["screen"] == screen, name
