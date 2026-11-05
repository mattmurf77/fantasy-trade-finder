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


"""Referral loop v1 — taxonomy registration: the SERVER rows (D-1).

Grant: analytics-lead, PR #350
(docs/business/analytics/2026-10-15-referral-loop-events.md), conditions
C1-C9. This section is that addendum's §Verification items 1-6 for the four
server names: `invite_landing_opened` and `invite_landing_cta` (D-1, the join
landing) and `referral_attributed` and `referral_activated` (L7, the ledger:
backend/referral_ledger.py), plus item 5's C5 half (the activation set IS
stage 7 of FUNNEL_STAGES).

PR #364 (build/referral-binary) creates this same file with the CLIENT rows
(`_CLIENT_PROPS`; items 1-4 and 7). When the two meet, keep both: this
section adds only `_SERVER_PROPS` / `_SERVER_OPTIONAL`, the `_srv_*` helpers
and the `test_server_*` tests, and touches no client name.

Server-fired names have no CLIENT_EVENT_PROPS row, so each emitter's props
are CAPTURED AT THE WRITER and compared `==` to the granted set (item 2).
One spy, on both writer names: the landing calls `server.record_event`, the
ledger calls `database.record_event` (the same function, bound twice), so
each event is captured exactly once.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

import backend.analytics_queries as aq
import backend.analytics_taxonomy as at
import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.referral_ledger as rl
import backend.server as server
from backend.database import (
    metadata, referrals_table, user_events_table, users_table,
)

# ---------------------------------------------------------------------------
# The server rows, with realistic values: a human iPhone GET of a minted
# link (`t` present, valid). Keys equal the granted set exactly; the keys in
# _SERVER_OPTIONAL are the ones that drop out when there is no `t`.
# ---------------------------------------------------------------------------

_SRV_INVITE_ID = "Ab3dEf6hIj9k"         # 12 URL-safe chars, the minted shape (§7.1)
_SRV_LEAGUE_ID = "123456789012345678"   # an 18-digit Sleeper id
_SRV_REFERRER = "u_srv_referrer"
_SRV_PRIOR = "2026-01-01T00:00:00+00:00"
_SRV_INVITEE = "u_srv_invitee"          # L7: a new user arriving through the link
_SRV_REFERRAL_ID = 1                    # the fixture's one referrals row
_SRV_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
               "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
               "Mobile/15E148 Safari/604.1")

_SERVER_PROPS: dict[str, dict] = {
    "invite_landing_opened": {"invite_id": _SRV_INVITE_ID,
                              "league_id": _SRV_LEAGUE_ID,
                              "invite_status": "valid", "device_class": "ios"},
    "invite_landing_cta":    {"invite_id": _SRV_INVITE_ID,
                              "league_id": _SRV_LEAGUE_ID,
                              "cta": "ios_install", "device_class": "ios"},
    # L7: the invitee's first session credits the link (§7.4), then their
    # first trade opinion activates it (FR-17). No invitee id (C2).
    "referral_attributed":   {"invite_id": _SRV_INVITE_ID,
                              "referral_id": _SRV_REFERRAL_ID,
                              "league_id": _SRV_LEAGUE_ID,
                              "attribution_method": "token",
                              "league_platform": "sleeper", "notified": True},
    "referral_activated":    {"invite_id": _SRV_INVITE_ID,
                              "referral_id": _SRV_REFERRAL_ID,
                              "league_id": _SRV_LEAGUE_ID,
                              "days_to_activate": 0, "notified": True},
}
_SERVER_OPTIONAL: dict[str, set] = {
    "invite_landing_opened": {"invite_id"},   # invite_status stays, as null
    "invite_landing_cta":    {"invite_id"},
    "referral_attributed":   set(),           # every key, every time
    "referral_activated":    set(),
}


@pytest.fixture()
def srv(monkeypatch):
    """Throwaway DB, both D-1 flags on, the beta URL set, no Sleeper egress,
    and a spy on the writer (both of its names)."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    flags = {"growth.join_landing", "growth.referral_ledger"}
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)
    monkeypatch.setattr(feature_flags, "is_enabled", lambda k: k in flags)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"name": "Lakeview Dynasty"})
    monkeypatch.setenv("IOS_INSTALL_URL", "https://testflight.apple.com/join/AbCdEfGh")
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=_SRV_REFERRER, username="srvref",
            display_name="Srv Ref", last_active_at=_SRV_PRIOR, events_count=5))
        conn.execute(insert(referrals_table).values(
            referrer_user_id=_SRV_REFERRER, league_id=_SRV_LEAGUE_ID,
            invite_token=_SRV_INVITE_ID, share_token=_SRV_INVITE_ID, status="pending",
            created_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()))
    captured = []
    real = server.record_event

    def _spy(user_id, event_type, **kw):
        captured.append((user_id, event_type, kw))
        return real(user_id, event_type, **kw)
    monkeypatch.setattr(server, "record_event", _spy)
    monkeypatch.setattr(db_module, "record_event", _spy)   # the ledger's writer
    server.app.config["TESTING"] = True
    return engine, captured


def _srv_get(path, ua=_SRV_IPHONE, method="GET"):
    return server.app.test_client().open(
        path, method=method, headers={"User-Agent": "" if ua is None else ua})


def _srv_drive(with_t=True):
    """One human GET of the landing and one of /go/ios."""
    q = f"?t={_SRV_INVITE_ID}" if with_t else ""
    _srv_get(f"/app/league/join/{_SRV_LEAGUE_ID}{q}")
    _srv_get(f"/app/league/join/{_SRV_LEAGUE_ID}/go/ios{q}")


def _srv_drive_ledger():
    """L7: the invitee's first session through the link, then their first
    trade opinion (the writers the session-init daemon and the stage-7
    emitters call)."""
    rl.attribute_first_session(
        is_new_user=True, user_id=_SRV_INVITEE, league_id=_SRV_LEAGUE_ID,
        league_platform="sleeper", invite_id=_SRV_INVITE_ID, invited_by=None,
        new_username="srvnew")
    rl.maybe_activate_referral(_SRV_INVITEE, "trade_proposed")


def _srv_rows(engine):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(user_events_table))]


# ---------------------------------------------------------------------------
# (1) membership
# ---------------------------------------------------------------------------

def test_server_names_are_server_fired_only():
    for name in _SERVER_PROPS:
        assert name in at.SERVER_FIRED_EVENTS, name
        assert name not in at.ALLOWED_CLIENT_EVENTS, name
        assert name not in at.CLIENT_EVENT_PROPS, name
        assert name in at._SERVER_AUTHORITATIVE, name


# ---------------------------------------------------------------------------
# (2) + (3) exact props at the writer, no `token` key, no device platform
# ---------------------------------------------------------------------------

def test_server_props_captured_at_the_writer_are_exact(srv):
    _, captured = srv
    _srv_drive(with_t=True)
    _srv_drive_ledger()
    assert [name for _, name, _ in captured] == list(_SERVER_PROPS)
    for _, name, kw in captured:
        assert kw["props"] == _SERVER_PROPS[name], name
        assert kw["platform"] == "server" and kw["touch_user"] is False, name


def test_server_props_without_t_drop_only_the_optional_keys(srv):
    _, captured = srv
    _srv_drive(with_t=False)
    for _, name, kw in captured:
        assert set(kw["props"]) == set(_SERVER_PROPS[name]) - _SERVER_OPTIONAL[name]
    opened = [kw["props"] for _, name, kw in captured if name == "invite_landing_opened"]
    assert opened == [{"league_id": _SRV_LEAGUE_ID, "invite_status": None,
                       "device_class": "ios"}]


def test_server_rows_carry_no_token_key(srv):
    engine, _ = srv
    _srv_drive(with_t=True)
    _srv_drive(with_t=False)
    _srv_drive_ledger()
    for name, props in _SERVER_PROPS.items():
        assert not any("token" in k for k in props), name
    for row in _srv_rows(engine):
        assert not any("token" in k for k in json.loads(row["props"]))


def test_server_rows_add_no_device_platform_prop(srv):
    """The device platform is the `platform` COLUMN ('server'), never a prop;
    the device bucket is `device_class`."""
    engine, _ = srv
    _srv_drive(with_t=True)
    _srv_drive_ledger()
    for name, props in _SERVER_PROPS.items():
        assert "platform" not in props, name
    rows = _srv_rows(engine)
    assert len(rows) == len(_SERVER_PROPS)
    for row in rows:
        assert "platform" not in json.loads(row["props"])
        assert row["platform"] == "server"


# ---------------------------------------------------------------------------
# (4) the intent split
# ---------------------------------------------------------------------------

def test_server_names_are_non_intent():
    for name in _SERVER_PROPS:
        assert name in aq.NON_INTENT_EVENTS, name
        assert name not in aq.INTENT_EVENTS, name


# ---------------------------------------------------------------------------
# (5) the non-touching write (C6)
# ---------------------------------------------------------------------------

def test_server_writes_never_move_the_owners_users_row(srv):
    engine, _ = srv

    def _user():
        with engine.connect() as conn:
            return dict(conn.execute(select(users_table).where(
                users_table.c.sleeper_user_id == _SRV_REFERRER)).fetchone()._mapping)
    before = _user()
    _srv_drive(with_t=True)
    _srv_get(f"/app/league/join/{_SRV_LEAGUE_ID}?ref=srvref")   # ref-resolved owner
    rows = _srv_rows(engine)
    assert {r["user_id"] for r in rows} == {_SRV_REFERRER} and len(rows) == 3
    assert _user() == before
    assert (before["last_active_at"], before["events_count"]) == (_SRV_PRIOR, 5)


def test_server_ledger_writes_never_move_the_owners_users_row(srv):
    """C6 for the L7 rows: owned by the referrer, caused by the invitee."""
    engine, _ = srv
    with engine.connect() as conn:
        before = dict(conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == _SRV_REFERRER)).fetchone()._mapping)
    _srv_drive_ledger()
    rows = _srv_rows(engine)
    assert [r["event_type"] for r in rows] == ["referral_attributed", "referral_activated"]
    assert {r["user_id"] for r in rows} == {_SRV_REFERRER}
    with engine.connect() as conn:
        after = dict(conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == _SRV_REFERRER)).fetchone()._mapping)
    assert after == before


def test_server_ledger_rows_carry_no_invitee_id(srv):
    """C2: the referrer's rows never name the referred user; join through
    referral_id to the ledger instead."""
    engine, _ = srv
    _srv_drive_ledger()
    for name in ("referral_attributed", "referral_activated"):
        assert "referred_user_id" not in _SERVER_PROPS[name], name
    for row in _srv_rows(engine):
        assert _SRV_INVITEE not in row["props"]


def test_server_activation_set_is_funnel_stage_7():
    """Item 5's C5 half: referral_activated's qualifying set is read from
    stage 7 of FUNNEL_STAGES (today trade_proposed | match_swiped), never a
    hand list, and never includes stage 6's trades_generated."""
    (stage7,) = [ev for n, _name, ev in aq.FUNNEL_STAGES if n == 7]
    (stage6,) = [ev for n, _name, ev in aq.FUNNEL_STAGES if n == 6]
    assert rl.STAGE7_EVENTS == frozenset(stage7)
    assert rl.STAGE7_EVENTS == {"trade_proposed", "match_swiped"}
    assert not rl.STAGE7_EVENTS & set(stage6)


def test_signup_keeps_its_class():
    """FR-16 widens signup's props only; the event stays INTENT (stage 2)."""
    assert "signup" in at.SERVER_FIRED_EVENTS
    assert "signup" in aq.INTENT_EVENTS and "signup" not in aq.NON_INTENT_EVENTS


# ---------------------------------------------------------------------------
# (6) the bot filter (C4), on both events
# ---------------------------------------------------------------------------

_SRV_PREVIEW_SAMPLES = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_1) AppleWebKit/601.2.4 "
    "(KHTML, like Gecko) Version/9.0.1 Safari/601.2.4 facebookexternalhit/1.1 "
    "Facebot Twitterbot/1.0",                                    # iMessage
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "WhatsApp/2.23.20.0 A",
    "TelegramBot (like TwitterBot)",
    "Mozilla/5.0 (Applebot/0.1; +http://www.apple.com/go/applebot)",
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient)",
    "Mozilla/5.0 (compatible; SkypeUriPreview Preview/0.5)",
    "",                                                          # empty UA
]


def test_server_bot_filter_lists_the_contracted_agents():
    tokens = {t.lower() for t in server.PREVIEW_UA_TOKENS}
    for need in ("facebookexternalhit", "twitterbot", "slackbot", "discordbot",
                 "whatsapp", "telegrambot", "applebot", "linkedinbot",
                 "bot", "crawler", "spider", "preview"):
        assert need in tokens, need


def test_server_bot_filter_fires_nothing_and_bumps_nothing(srv):
    """Each listed agent, each generic pattern and the empty UA: no event
    on either route and no open_count bump; HEAD records nothing either."""
    engine, captured = srv
    agents = _SRV_PREVIEW_SAMPLES + [
        f"Mozilla/5.0 (compatible; Some{tok.title()}/1.0)" for tok in server.PREVIEW_UA_TOKENS]
    for ua in agents:
        _srv_get(f"/app/league/join/{_SRV_LEAGUE_ID}?t={_SRV_INVITE_ID}", ua=ua)
        _srv_get(f"/app/league/join/{_SRV_LEAGUE_ID}/go/ios?t={_SRV_INVITE_ID}", ua=ua)
    for path in (f"/app/league/join/{_SRV_LEAGUE_ID}?t={_SRV_INVITE_ID}",
                 f"/app/league/join/{_SRV_LEAGUE_ID}/go/ios?t={_SRV_INVITE_ID}",
                 f"/app/league/join/{_SRV_LEAGUE_ID}/go/web?t={_SRV_INVITE_ID}"):
        _srv_get(path, method="HEAD")
    assert captured == [] and _srv_rows(engine) == []
    with engine.connect() as conn:
        row = conn.execute(select(referrals_table)).fetchone()._mapping
    assert row["open_count"] == 0 and row["opened_at"] is None


def test_server_rows_store_no_user_agent_or_ip(srv):
    engine, _ = srv
    _srv_drive(with_t=True)
    with engine.connect() as conn:
        ref_row = dict(conn.execute(select(referrals_table)).fetchone()._mapping)
    stored = [json.dumps(r, default=str) for r in _srv_rows(engine)] + [
        json.dumps(ref_row, default=str)]
    for blob in stored:
        for leak in ("Mozilla", "iPhone OS", "Safari", "127.0.0.1"):
            assert leak not in blob, leak
