"""Referral loop v1 — taxonomy registration (2026-10-23).

Grant: analytics-lead, PR #350
(docs/business/analytics/2026-10-15-referral-loop-events.md), conditions
C1-C9. This file is the addendum's §Verification list. It lands in the
CLIENT emitters' commit (C7) and pins the client rows; the four server names
(invite_landing_opened, invite_landing_cta, referral_attributed,
referral_activated) are added to `_SERVER_PROPS` below, with their own
tests, in the server emitters' commit (D-1).

The three silent failures this guards, all behind a 200:

  * an UNREGISTERED NAME is counted-and-dropped (`dropped_unknown_type`);
  * a registered name with an UNREGISTERED PROP lands hollowed out:
    `analytics_ingest._scrub_props` pops the key, `dropped` stays 0;
  * a key containing "token" is dropped by ingest's PII denylist
    (`analytics_ingest._PROP_KEY_DENYLIST`) whatever the registry says,
    which is why the id travels as `invite_id`, never `*token*` (C1, C3).

And one for the report layer: INTENT is derived by SUBTRACTION
(`analytics_queries.INTENT_EVENTS`), so the split below is hand-written on
purpose; flipping a name in the module fails here instead of quietly moving
DAU.
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
# The client rows, with realistic values. KEY SETS are asserted EQUAL to
# CLIENT_EVENT_PROPS, so a row narrowed later fails here rather than
# hollowing out production rows. Every optional prop is present, so each
# payload exercises its row completely.
# ---------------------------------------------------------------------------

_INVITE_ID = "Ab3dEf6hIj9k"          # 12 URL-safe chars, the minted shape (§7.1)
_LEAGUE_ID = "123456789012345678"    # an 18-digit Sleeper id (G-036 exempt)

_CLIENT_PROPS: dict[str, dict] = {
    # Widened: + invite_id (only when the mint succeeded), + mint_outcome.
    "invite_shared":        {"league_id": _LEAGUE_ID, "surface": "trades_banner",
                             "not_joined": None, "total_mates": None,
                             "platform": "sleeper", "invite_id": _INVITE_ID,
                             "mint_outcome": "ok"},
    # Keys unchanged by #350 (`surface` gains `web_invite`, a value).
    "invite_cta_tapped":    {"surface": "league_home", "not_joined": 3,
                             "total_mates": 11, "platform": "espn"},
    "invite_cta_shown":     {"surface": "matches_empty", "not_joined": 3,
                             "total_mates": 11, "platform": "mfl"},
    # Widened: + invite_id (the well-formed `t` as received).
    "invite_link_opened":   {"league_id": _LEAGUE_ID, "has_ref": False,
                             "format": "path", "auth_state": "signed_out",
                             "invite_id": _INVITE_ID},
    "invite_league_pinned": {"league_id": _LEAGUE_ID, "source": "picker_autopin",
                             "ms_since_open": 4200, "invite_id": _INVITE_ID},
    "invite_pin_failed":    {"league_id": _LEAGUE_ID, "reason": "not_member",
                             "invite_id": _INVITE_ID},
    # New.
    "share_link_opened":    {"kind": "trade", "has_ref": True,
                             "auth_state": "authed_non_member"},
}

# Server rows land with D-1 (SERVER_FIRED_EVENTS has no prop registry: each
# emitter's keys are captured at the writer and compared `==` to these).
_SERVER_PROPS: dict[str, dict] = {}

# The deliberate classification (§Verification item 4). Server names join
# _NON_INTENT with D-1; `signup` is already INTENT and is unchanged.
_NON_INTENT = {"invite_cta_shown"}
_INTENT = {"signup", "invite_cta_tapped", "invite_shared",
           "invite_link_opened", "invite_league_pinned", "invite_pin_failed",
           "share_link_opened"}

_SERVER_NAMES = {"invite_landing_opened", "invite_landing_cta",
                 "referral_attributed", "referral_activated"}

assert not (_NON_INTENT & _INTENT)


# ---------------------------------------------------------------------------
# (1) membership
# ---------------------------------------------------------------------------

def test_referral_client_names_are_allowlisted_and_client_only():
    import backend.analytics_taxonomy as tax
    assert set(_CLIENT_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    # Client-fired: none may ever be server-authoritative (the import-time
    # disjointness assert would take the app down at boot).
    assert not (set(_CLIENT_PROPS) & tax._SERVER_AUTHORITATIVE)
    assert "share_link_opened" not in tax.SERVER_FIRED_EVENTS


def test_referral_server_names_are_never_client_submittable():
    """The four server names are server-authoritative (C7): whatever D-1
    does to SERVER_FIRED_EVENTS, none of them may be client-allowlisted."""
    import backend.analytics_taxonomy as tax
    assert not (_SERVER_NAMES & tax.ALLOWED_CLIENT_EVENTS)


# ---------------------------------------------------------------------------
# (2) + (3) exact prop rows, no `token` key, no device platform
# ---------------------------------------------------------------------------

def test_referral_client_prop_rows_are_exact():
    """EQUAL, not <=: an extra key is an unspecced prop and a missing key is
    silently stripped at ingest."""
    import backend.analytics_taxonomy as tax
    for name, props in _CLIENT_PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name


def test_referral_rows_carry_no_token_key():
    """C1 / C3: ingest drops any key containing "token" behind a 200, and the
    id must never read as a credential."""
    import backend.analytics_taxonomy as tax
    for name in _CLIENT_PROPS:
        assert not [k for k in tax.CLIENT_EVENT_PROPS[name]
                    if "token" in k.lower()], name
    for name, props in _SERVER_PROPS.items():
        assert not [k for k in props if "token" in k.lower()], name
    # The registry's key and ingest's denylist agree on why.
    assert "token" in ingest._PROP_KEY_DENYLIST


def test_referral_rows_add_no_device_platform_prop():
    """Device platform is a user_events COLUMN (the NULL-`platform`
    incident). The invite rows' existing `platform` is the LEAGUE platform
    and keeps that meaning; nothing new adds one."""
    import backend.analytics_taxonomy as tax
    assert "platform" not in tax.CLIENT_EVENT_PROPS["share_link_opened"]
    for name in ("invite_link_opened", "invite_league_pinned",
                 "invite_pin_failed"):
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name


# ---------------------------------------------------------------------------
# (4) the intent split
# ---------------------------------------------------------------------------

def test_referral_intent_split():
    """`share_link_opened` is INTENT, overruling the P18 draft: its twin
    `invite_link_opened` is INTENT and twins land on the same side."""
    import backend.analytics_queries as q
    for name in _NON_INTENT:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name
    for name in _INTENT:
        assert name in q.INTENT_EVENTS, name
        assert name not in q.NON_INTENT_EVENTS, name


# ---------------------------------------------------------------------------
# (7) ingest round-trip through POST /api/events (the 384 harness)
# ---------------------------------------------------------------------------

USER = "taxonomy_referral_test"
TOKEN = "tax-referral-token"
DEVICE = "dev_referral01"


def _envelope(i, event_type, props, screen="Trades"):
    return {
        "event_id": f"evtref-{i:04d}",
        "event_type": event_type,
        "client_ts": "2026-10-23T12:00:00Z",
        "screen": screen,
        "props": props,
        "session_id": "sess-ref-0001",
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
    """`seq` and `ts_suspect` are stamped by the server after the strip."""
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


def test_referral_client_events_land_with_every_prop(harness):
    """NAME and PROP survival in one pass, by value. `dropped == 0` alone is
    not evidence (an unknown type still counts in `accepted`), so the health
    counter and the stored rows are read back too."""
    client, engine = harness
    before = dict(ingest._health)
    body = _post(client, [
        _envelope(i, name, props)
        for i, (name, props) in enumerate(_CLIENT_PROPS.items())
    ]).get_json()

    assert body["accepted"] == len(_CLIENT_PROPS)
    assert body["dropped"] == 0
    assert ingest._health["dropped_unknown_type"] == \
        before["dropped_unknown_type"]

    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == set(_CLIENT_PROPS)
    for name, props in _CLIENT_PROPS.items():
        # Equality by value: the id survives the PII scrubber, and the
        # 18-digit league id is not "[scrubbed]" (G-036).
        assert _client_props(by_type[name]) == props, name


def test_referral_unregistered_sibling_is_still_dropped(harness):
    """Control: the pipeline really is default-deny, so `dropped == 0` above
    is evidence and not a tautology."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, "share_link_viewed", {"kind": "trade"}),
    ]).get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    assert _rows(engine) == []
