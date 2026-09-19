"""Taxonomy registration for `swipe_guard_blocked` (deck double-fire guards).

Tracking plan: docs/business/analytics/2026-08-18-swipe-guard-blocked.md
Origin: docs/reviews/2026-08-18-bug-sweep/ticket.md §B4 · D-068 · G-049

The registry is DEFAULT-DENY BEHIND A 200 — analytics_ingest counts and drops
an unknown event type, and strips an unregistered prop, with a success-shaped
response and a plausible-looking empty dashboard (G-031). These tests are the
pin: the name is allowlisted, the prop row is exactly the addendum's table,
nothing that identifies a person is in it, and the two deliberate omissions
(FUNNEL_CRITICAL, SERVER_FIRED_EVENTS) stay omissions rather than drifting in.

Follows the registration-test pattern of test_decline_reasons.py §"Analytics
registration"; no harness needed — these assert on imported registries only.
"""

import pytest

from backend.analytics_taxonomy import (
    ALLOWED_CLIENT_EVENTS,
    CLIENT_EVENT_PROPS,
    FUNNEL_CRITICAL,
    SERVER_FIRED_EVENTS,
)

EVENT = "swipe_guard_blocked"

# Transcribed from the addendum's props table. Held here rather than derived,
# so a widened frozenset fails HERE instead of silently changing what ingest
# accepts.
_SPEC_PROPS = frozenset({
    "guard",            # swipe_undo | decline_reasons — which early-return
    "decision",         # like | pass — what the user was reaching for
    "trade_id",         # the card (server-minted)
    "impression_id",    # the serve, or the literal 'none'
    "blocked_n",        # consecutive blocks on this (card, guard)
    "ms_since_render",  # card render → block, ms
})


def test_event_is_registered_client_side():
    assert EVENT in ALLOWED_CLIENT_EVENTS
    assert EVENT in CLIENT_EVENT_PROPS


def test_event_is_not_server_fired():
    """The server never learns that a tap was swallowed — that IS the
    finding. A collision would also trip the import-time disjointness assert
    and take the app down at boot."""
    assert EVENT not in SERVER_FIRED_EVENTS


def test_props_are_exactly_the_addendum():
    assert CLIENT_EVENT_PROPS[EVENT] == _SPEC_PROPS


@pytest.mark.parametrize("prop", ["guard", "decision", "trade_id", "blocked_n"])
def test_diagnosis_minimum_is_present(prop):
    """Which guard fired and on which card is the least a diagnosis needs;
    `decision` and `blocked_n` are what separate a benign double-fire from a
    user trapped on a card."""
    assert prop in CLIENT_EVENT_PROPS[EVENT]


@pytest.mark.parametrize("prop", [
    "platform", "player_id", "player_name", "user_id", "username",
    "league_id", "text", "free_text", "partner_id", "email",
])
def test_no_pii_and_no_device_platform_prop(prop):
    """Device platform is a `user_events` COLUMN derived server-side at
    ingest (the NULL-`platform` incident); the trade_pass_layer* pair is the
    one operator-approved exception and this event does not inherit it.
    Nothing else here may identify a person — `league_id` rides the envelope
    column as always."""
    assert prop not in CLIENT_EVENT_PROPS[EVENT]


def test_not_funnel_critical():
    """FUNNEL_CRITICAL is the SDK's drop-LAST policy under queue overflow,
    hand-mirrored into mobile/src/api/events.ts. A trapped user is the one
    most likely to overflow the queue, so admitting this event would let
    their guard rows evict signin_* and experiment_exposed — the inverse of
    the intended priority. It is also the change that would desync the
    mirror."""
    assert EVENT not in FUNNEL_CRITICAL


def test_intent_by_design_no_dau_seam():
    """Deliberately NOT in analytics_queries.NON_INTENT_EVENTS: INTENT is
    derived by subtraction, and admitting this name cannot step-change
    DAU/WAU because every emission is preceded on the same card, in the same
    session, by `trade_card_viewed` — which is itself INTENT and fires on
    every card reaching the top of the deck. Pinned as a pair: if
    trade_card_viewed ever becomes non-intent, that argument dies and this
    decision must be revisited (addendum § Registry decisions)."""
    from backend.analytics_queries import NON_INTENT_EVENTS

    assert "trade_card_viewed" not in NON_INTENT_EVENTS
    assert EVENT not in NON_INTENT_EVENTS
