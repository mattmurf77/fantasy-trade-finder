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
  * R2 `trade_first_card_shown` / R2b `trade_first_card_failed` — new,
    NON_INTENT (a system outcome echoing the R1 tap).
  * `deck_buffer_empty` — new (ruling 30), NON_INTENT (an AC-L4 outcome).
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


# The addendum's exact R1 `source` values (+ team_review, granted Q-A). The
# registry holds prop NAMES, not values, so the values live in the row's
# comment; this keeps that list complete (mobile utils/firstCardEvent.ts
# R1Source is pinned against the same list by check-trade-first-card-events).
R1_SOURCES = (
    "deck_error_retry", "prefs_changed_strip", "deck_summary_unpin",
    "deck_search_all", "calculator", "league_offer", "league_target",
    "usage_trends", "deep_link", "end_card_adjust", "team_review",
)


def test_r1_source_values_are_listed_on_the_row():
    import inspect
    src = inspect.getsource(tax)
    start = src.index("# Time to trade suggestion (R1;")
    end = src.index('"find_trades_tapped":   frozenset(', start)
    comment = src[start:end]
    missing = [v for v in R1_SOURCES if v not in comment]
    assert not missing, missing
    assert "team_review" in comment and "AC-L1" in comment


R2_ROWS: dict[str, frozenset[str]] = {
    "trade_first_card_shown": frozenset({
        "search_id", "ms_from_tap", "entry_point", "search_type",
        "launch_state", "network_type", "serve_source", "freshness_state",
        "job_id", "card_index"}),
    "trade_first_card_failed": frozenset({
        "search_id", "ms_from_tap", "reason", "entry_point", "search_type",
        "launch_state", "network_type", "serve_source"}),
    "deck_buffer_empty": frozenset({
        "search_id", "deck_id", "cards_seen", "ms_since_first_card",
        "network_type"}),
}


def test_r2_names_are_allowlisted_client_events():
    assert set(R2_ROWS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(R2_ROWS) & tax._SERVER_AUTHORITATIVE)


def test_r2_prop_rows_are_exact():
    for name, props in R2_ROWS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == props, name


def test_r2_names_are_non_intent():
    for name in R2_ROWS:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name


def test_r2_carries_no_pii_or_platform_prop():
    for name in R2_ROWS:
        props = tax.CLIENT_EVENT_PROPS[name]
        assert "platform" not in props, name
        assert not ({"player_id", "player_ids", "league_id", "name"} & props), name
