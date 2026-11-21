"""Home's next move: analytics (docs/plans/home-next-move/scope.md §1, D-278).
Harness: test_direction_card_analytics.py's.

No new event and no new prop. The tap is `home_tile_tapped {tile:
'next_move'}` (a new value in the documented closed `tile` vocabulary), and
the hand-off that follows is the list row's own `finder_target_pinned`
(side give / source maxpf_moves for a sell, side receive / source
playoff_targets for a buy), logged with screen Home.

- test_tile_is_documented_and_props_unchanged. Sabotage: drop the
  `next_move` line from the taxonomy's tile vocabulary.
- test_the_tap_and_the_hand_off_land: POST /api/events accepts the three
  events with their props and screen intact.
"""
import inspect
import json

from sqlalchemy import select

import backend.analytics_queries as q
import backend.analytics_taxonomy as tax
from backend.database import user_events_table
from backend.tests.test_direction_card_analytics import DEVICE, harness  # noqa: F401  (fixture)


def test_tile_is_documented_and_props_unchanged():
    source = inspect.getsource(tax)
    assert "#   next_move " in source and "league.next_move" in source
    assert tax.CLIENT_EVENT_PROPS["home_tile_tapped"] == frozenset({"tile", "position", "band", "split", "via"})
    assert tax.CLIENT_EVENT_PROPS["finder_target_pinned"] == frozenset({"side", "source"})
    assert "home_tile_tapped" in q.NON_INTENT_EVENTS


def test_the_tap_and_the_hand_off_land(harness):  # noqa: F811
    client, engine = harness
    sent = [("home_tile_tapped", {"tile": "next_move"}),
            ("finder_target_pinned", {"side": "give", "source": "maxpf_moves"}),
            ("finder_target_pinned", {"side": "receive", "source": "playoff_targets"})]
    events = [{"event_id": f"evtnm-{i:04d}", "event_type": name, "client_ts": "2026-11-21T12:00:00Z",
               "screen": "Home", "props": props, "session_id": "sess-nm-0001", "seq": i + 1}
              for i, (name, props) in enumerate(sent)]
    body = client.post("/api/events", headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
                       data=json.dumps({"events": events})).get_json()
    assert body["accepted"] == len(sent) and body["dropped"] == 0
    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table).order_by(user_events_table.c.id)).fetchall()
    landed = [({k: v for k, v in json.loads(r._mapping["props"]).items() if k not in {"seq", "ts_suspect"}},
               r._mapping["screen"]) for r in rows]
    assert landed == [(props, "Home") for _, props in sent]
