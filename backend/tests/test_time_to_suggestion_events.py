"""Time to trade suggestion (#339 §4.6, AC-L1) — taxonomy registration.

Contract: docs/business/analytics/2026-10-20-time-to-suggestion-events.md
(addendum v2 @ 255dd832, analytics-lead ruling 30). Each emitter's name and
props are registered in the SAME commit as the emitter, because the ingest
allowlist is default-deny behind a 200: an unregistered name is counted and
dropped, an unregistered prop is stripped, and the response still reports
dropped == 0.

Rows are asserted EQUAL (==), not <=: an extra key is unspecced and a
missing one is stripped.

  * R1 `find_trades_tapped` / `calc_find_a_trade_tapped` — WIDENED with
    `search_id`; both stay INTENT (a tap is a user action).
"""
import backend.analytics_queries as q
import backend.analytics_taxonomy as tax


R1_ROWS: dict[str, frozenset[str]] = {
    "find_trades_tapped": frozenset({"source", "mode", "search_id"}),
    "calc_find_a_trade_tapped": frozenset(
        {"path", "give_count", "receive_count", "has_partner", "search_id"}),
}


def test_r1_names_are_allowlisted_client_events():
    assert set(R1_ROWS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(R1_ROWS) & tax._SERVER_AUTHORITATIVE)


def test_r1_prop_rows_are_exact():
    for name, props in R1_ROWS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == props, name


def test_r1_stays_intent():
    for name in R1_ROWS:
        assert name not in q.NON_INTENT_EVENTS, name
        assert name in q.INTENT_EVENTS, name


def test_r1_carries_no_device_platform_prop():
    for name in R1_ROWS:
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name
