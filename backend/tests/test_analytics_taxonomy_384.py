"""#384 merged calculator + finder — taxonomy registration (2026-08-22).

Addendum: docs/business/analytics/2026-08-22-384-calc-finder-addendum.md.
Origin: docs/feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md
§Analytics, which found the W4 guided tour firing three names the backend
allowlist had never heard of — counted and dropped behind a 200.

Two silent failure modes, one per registry, both asserted here:

  * an UNREGISTERED NAME is accepted-and-dropped (`dropped_unknown_type`);
    the client sees a 200 and the row never exists;
  * a REGISTERED NAME with an unregistered PROP lands hollowed out —
    `analytics_ingest._scrub_props` pops the key while the response still
    reports dropped == 0.

And one silent failure mode for the report layer: `INTENT_EVENTS` is derived
by SUBTRACTION (`analytics_queries.py`), so taxonomy growth is
intent-BY-DEFAULT. A passive name registered without its NON_INTENT row
step-changes DAU/WAU on ship day, permanently, with no error anywhere. The
`_NON_INTENT` / `_INTENT` split below is the deliberate classification — it
is a hand-written expectation on purpose, so flipping a name in the module
fails here instead of quietly moving the north star.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

# ---------------------------------------------------------------------------
# The batch, with its exact prop rows and its deliberate classification.
# ---------------------------------------------------------------------------
# Values are the props the emitters send; the KEY SET is asserted equal to
# CLIENT_EVENT_PROPS, so a row narrowed later fails here rather than
# hollowing out production rows.

_PROPS: dict[str, dict] = {
    # Calculator tour (screen 'TradeCalculator') — live emitters in
    # mobile/src/utils/calcTour.ts.
    "calc_tour_started":            {"source": "show_me_around"},
    "calc_tour_ended":              {"reason": "finished", "beats_shown": 9},
    "calc_tour_beat_missing":       {"beat": "n17"},
    # Calculator interactions.
    "calc_mode_switched":           {"mode": "league"},
    "calc_asset_added":             {"side": "receive"},
    "calc_cleared":                 {"mode": "live"},
    # W6-B (D-153): `path` replaced `include_players`. The toggle it named is
    # gone — the canvas is always the anchor — so the prop now reports which
    # fork the tap actually took (`fair` = canvas anchored, `model` = empty).
    "calc_find_a_trade_tapped":     {"path": "fair",
                                     "give_count": 2, "receive_count": 1,
                                     "has_partner": False},
    # Deck (screen 'Trades').
    "deck_back_to_calculator":      {"pin_count": 3},
    "deck_unpin_retry":             {"pin_count": 1},
    "deck_search_all_tapped":       {},
    "trade_pass_overlay_opened":    {},
    "trade_pass_overlay_dismissed": {"banked": True},
    # Pre-existing live emitter, never registered until now
    # (mobile/src/state/useInterruptCoordinator.ts:170/183).
    "prompt_deferred":              {"surface": "quickset_prompt",
                                     "blocked_by": "tour"},
}

# NON_INTENT: mount counters, terminators, exposures, dismissals and system
# refusals. One line each — the argument, not the restatement.
_NON_INTENT = {
    # the tour auto-starts on landing: a MOUNT counter for a primary surface
    "calc_tour_started",
    # a TERMINATOR, always preceded by its own start
    "calc_tour_ended",
    # a SCRIPT DEFECT diagnostic — nothing the user did or was shown
    "calc_tour_beat_missing",
    # an EXPOSURE of the capture surface; the decision is trade_pass_layer*
    "trade_pass_overlay_opened",
    # a DISMISSAL, the apple_banner_dismissed class
    "trade_pass_overlay_dismissed",
    # a SYSTEM REFUSAL, the exact peer of guide_step_suppressed
    "prompt_deferred",
}

# INTENT: real user decisions, deliberately absent from NON_INTENT_EVENTS.
_INTENT = {
    # a configuration change, the league_basis_changed peer
    "calc_mode_switched",
    # the calculator's core gesture, the finder_target_pinned peer
    "calc_asset_added",
    # a deliberate destructive action (its undo calc_clear_undone is INTENT)
    "calc_cleared",
    # the hand-off tap — the conversion moment of the whole #384 merge
    "calc_find_a_trade_tapped",
    # a return to editing, the trade_edit_in_calculator_tapped peer
    "deck_back_to_calculator",
    # a retry after an empty deck, the suppression_undo_tapped peer
    "deck_unpin_retry",
    # W6-B: a deliberate widening off an exhausted FAIR deck — the same class
    # as deck_unpin_retry, and reachable only from a deck the user asked for
    "deck_search_all_tapped",
}

assert _NON_INTENT | _INTENT == set(_PROPS), "classify every #384 name"
assert not (_NON_INTENT & _INTENT)


# ---------------------------------------------------------------------------
# (1) + (2) registration and prop rows
# ---------------------------------------------------------------------------

def test_384_names_are_allowlisted():
    """An unregistered name is counted-and-dropped behind a 200 — the exact
    state calc_tour_started/_ended/_beat_missing shipped in."""
    import backend.analytics_taxonomy as tax
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    # Client-fired: none of them may ever become server-authoritative (the
    # import-time disjointness assert would take the app down at boot).
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)


def test_384_prop_rows_are_exact():
    """Asserted EQUAL, not <=: an extra key is an unspecced prop and a
    missing key is silently stripped at ingest."""
    import backend.analytics_taxonomy as tax
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name
    # The one deliberately empty row — the card is already identified by
    # trade_card_viewed and the trade_pass_layer* rows.
    assert tax.CLIENT_EVENT_PROPS["trade_pass_overlay_opened"] == frozenset()


def test_384_carries_no_device_platform_prop():
    """Device platform is a user_events COLUMN derived server-side (the
    NULL-`platform` incident). The decline-reason family is the one
    operator-approved exception and this batch does not inherit it."""
    import backend.analytics_taxonomy as tax
    for name in _PROPS:
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name


def test_384_mints_no_duplicate_of_a_shipped_event():
    """The merge adds surfaces, not second sources of truth for shipped
    interactions (#208/#248/#293). The deck's own `find_trades_tapped` and
    the inline `trade_pass_layer*` pair keep their meanings unchanged."""
    import backend.analytics_taxonomy as tax
    for shipped in ("find_trades_tapped", "trade_pass_layer1",
                    "trade_pass_layer2", "prompt_shown"):
        assert shipped in tax.ALLOWED_CLIENT_EVENTS
    assert tax.CLIENT_EVENT_PROPS["find_trades_tapped"] == frozenset(
        {"source", "mode"})
    # `prompt_deferred` is the twin of `prompt_shown`, not a replacement.
    assert tax.CLIENT_EVENT_PROPS["prompt_shown"] == frozenset({"surface"})


# ---------------------------------------------------------------------------
# (3) intent classification — the DAU seam
# ---------------------------------------------------------------------------

def test_384_every_name_is_classified():
    """INTENT is a deny-list, so every name is classified by construction —
    what this pins is that the classification is the INTENDED one."""
    import backend.analytics_queries as q
    for name in _NON_INTENT:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name
    for name in _INTENT:
        assert name in q.INTENT_EVENTS, name
        assert name not in q.NON_INTENT_EVENTS, name


def test_384_tour_start_cannot_mint_a_user_day():
    """The load-bearing one. The tour AUTO-starts on landing on the
    calculator (calcTour.startCalcTour, source='auto'), so if
    calc_tour_started ever reads as intent, DAU/WAU becomes approximately
    calculator-visit count from ship day and every retention and churn
    series breaks at that seam — silently, and with a 200 on every request.
    """
    import backend.analytics_queries as q
    assert "calc_tour_started" in q.NON_INTENT_EVENTS
    # …and the WAT north star is untouched by this batch.
    assert not (set(_PROPS) & q.WAT_EVENTS)


def test_384_prompt_deferred_matches_its_granted_twin():
    """`prompt_shown` (granted) is already NON_INTENT; its refusal half must
    not land on the other side of the line."""
    import backend.analytics_queries as q
    assert "prompt_shown" in q.NON_INTENT_EVENTS
    assert "prompt_deferred" in q.NON_INTENT_EVENTS
    # The system-refusal peer it is modelled on.
    assert "guide_step_suppressed" in q.NON_INTENT_EVENTS


# ---------------------------------------------------------------------------
# (4) ingest — the names actually survive POST /api/events
# ---------------------------------------------------------------------------
# Harness mirrors test_events_api.py: the pipeline writes via
# db.ingest_engine, so BOTH engines are patched to the same in-memory DB, and
# `analytics_ingest.is_enabled` is patched because the pipeline imports the
# name directly.

USER = "taxonomy_384_test"
TOKEN = "tax-384-token"
DEVICE = "dev_384abc"


def _envelope(i, event_type, props, screen="TradeCalculator"):
    return {
        "event_id": f"evt384-{i:04d}",
        "event_type": event_type,
        "client_ts": "2026-08-22T12:00:00Z",
        "screen": screen,
        "props": props,
        "session_id": "sess-384-0001",
        "seq": i + 1,
    }


def _post(client, events):
    return client.post(
        "/api/events",
        headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
        data=json.dumps({"events": events}),
    )


def _rows(engine):
    with engine.begin() as conn:
        return conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()


def _client_props(row):
    """`seq` and `ts_suspect` are stamped by the server AFTER the strip and
    never pass through CLIENT_EVENT_PROPS."""
    return {k: v for k, v in json.loads(row["props"]).items()
            if k not in {"seq", "ts_suspect"}}


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled",
                      lambda k: k == "analytics.ingest"):
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


def test_384_prompt_deferred_is_no_longer_dropped(harness):
    """The regression that motivated the whole registration.

    `useInterruptCoordinator.ts` has fired `prompt_deferred` since the prompt
    arbiter shipped and ingest bumped `dropped_unknown_type` on every one of
    them — a success-shaped 200 with no row. This asserts the drop is gone,
    by counting the health counter rather than trusting `accepted` (an
    unknown type still counts in `accepted`, so `accepted` proves nothing).
    """
    client, engine = harness
    before = dict(ingest._health)
    body = _post(client, [
        _envelope(0, "prompt_deferred", _PROPS["prompt_deferred"],
                  screen="TradeCalculator"),
    ]).get_json()

    assert body["accepted"] == 1 and body["dropped"] == 0
    assert ingest._health["dropped_unknown_type"] == \
        before["dropped_unknown_type"]

    rows = _rows(engine)
    assert len(rows) == 1
    assert rows[0]._mapping["event_type"] == "prompt_deferred"
    # `blocked_by: 'tour'` is the value the #384 tour hold produces — the
    # one this event exists to make readable.
    assert _client_props(rows[0]._mapping) == {"surface": "quickset_prompt",
                                               "blocked_by": "tour"}


def test_384_unregistered_sibling_is_still_dropped(harness):
    """Control for the test above: the pipeline really is default-deny, so
    `dropped == 0` on a registered name is evidence and not a tautology."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, "calc_tour_paused", {"beat": "n12"}),
    ]).get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    assert _rows(engine) == []


def test_384_every_name_lands_with_every_prop(harness):
    """NAME survival and PROP survival in one pass, driven off `_PROPS`
    (whose key sets are pinned equal to CLIENT_EVENT_PROPS above), so a
    later narrowing fails here instead of hollowing out live rows."""
    client, engine = harness
    screens = {"deck_back_to_calculator": "Trades",
               "deck_unpin_retry": "Trades",
               "deck_search_all_tapped": "Trades",
               "trade_pass_overlay_opened": "Trades",
               "trade_pass_overlay_dismissed": "Trades"}
    body = _post(client, [
        _envelope(i, name, props, screens.get(name, "TradeCalculator"))
        for i, (name, props) in enumerate(_PROPS.items())
    ]).get_json()

    assert body["accepted"] + body["deduped"] + len(body["rejected"]) == \
        len(_PROPS)
    # dropped == 0 proves NAME survival; accepted alone would not.
    assert body["accepted"] == len(_PROPS) and body["dropped"] == 0

    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == set(_PROPS)
    for name, props in _PROPS.items():
        stored = _client_props(by_type[name])
        for k, v in props.items():
            assert k in stored, f"{name}.{k} was STRIPPED at ingest"
            assert stored[k] == v, f"{name}.{k} changed value"


def test_384_calculator_screen_rides_the_envelope(harness):
    """`screen` is an envelope COLUMN, not a prop — the calculator events
    must not start carrying a screen prop to compensate."""
    client, engine = harness
    _post(client, [
        _envelope(0, "calc_asset_added", {"side": "give"}),
    ])
    row = _rows(engine)[0]._mapping
    assert row["screen"] == "TradeCalculator"
    assert "screen" not in _client_props(row)
