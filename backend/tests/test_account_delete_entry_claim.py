"""M11 minimal path (#354, head-eng's ruling 2026-10-24): the claim-only
DELETE /api/account for an UNVERIFIED ESPN/MFL entry session.

An entry id (`entry:espn:…` / `entry:mfl:…`) is deterministic from public
league data, so an unverified session holding one may be someone else's
account. Its "Delete account" therefore removes only what THIS device wrote
for the id (its identity_links row and the user_events it sent) and ends THIS
session. The users row, rankings, and other devices' rows are untouched.
Every other unverified session keeps the 403; verified sessions keep the full
deletion; export stays gated.

Reuses test_account_data_rights' fixture: in-memory SQLite, injected sessions,
mocked flags, no network.
"""
import json

import pytest
from sqlalchemy import insert, select

import backend.database as db_module
import backend.server as server
from backend.database import identity_links_table, user_events_table

from .test_account_data_rights import client, _h, UID  # noqa: F401  (fixture)

MFL_UID = "entry:mfl:61408.f0003"
ESPN_UID = "entry:espn:{3C1E7A52-1D2B-4C5E-9F00-ABCDEF123456}"
THIS_DEVICE = "dev_this-install"
OTHER_DEVICE = "dev_someone-else"
CONFIRM = json.dumps({"confirm": "delete"})


def _entry_session(token, uid):
    with server._sessions_lock:
        server._sessions[token] = {"user_id": uid, "active_format": "1qb_ppr",
                                   "last_active": 0.0}


def _seed(uid):
    """This device and another device both linked to `uid`, each with events,
    plus a users row and a ranking keyed only by the id."""
    db_module.upsert_user(sleeper_user_id=uid)
    db_module.save_ranking_swipes(user_id=uid, ordered_ids=["1", "2"],
                                  scoring_format="1qb_ppr")
    for dev in (THIS_DEVICE, OTHER_DEVICE):
        db_module.link_identity(dev, sleeper_user_id=uid)
    with db_module.engine.begin() as conn:
        for i, dev in enumerate([THIS_DEVICE, THIS_DEVICE, OTHER_DEVICE, None]):
            conn.execute(insert(user_events_table).values(
                user_id=uid, event_type="screen_viewed",
                occurred_at=f"2026-10-24T00:00:0{i}Z", device_id=dev))


def _links(uid):
    with db_module.engine.connect() as conn:
        return sorted(r.device_id for r in conn.execute(
            select(identity_links_table).where(identity_links_table.c.sleeper_user_id == uid)))


def _events(uid):
    with db_module.engine.connect() as conn:
        return sorted((r.device_id or "") for r in conn.execute(
            select(user_events_table).where(user_events_table.c.user_id == uid)))


def _user_exists(uid):
    with db_module.engine.connect() as conn:
        return conn.execute(select(db_module.users_table).where(
            db_module.users_table.c.sleeper_user_id == uid)).first() is not None


def _claim_delete(c, token, body=CONFIRM, device=THIS_DEVICE):
    headers = _h(token)
    if device:
        headers["X-Device-Id"] = device
    return c.delete("/api/account", headers=headers, data=body)


@pytest.mark.parametrize("uid", [MFL_UID, ESPN_UID])
def test_unverified_entry_claim_delete_removes_this_device_and_ends_session(client, uid):
    c, _, _ = client
    token = "sess-entry-claim"
    _entry_session(token, uid)
    _seed(uid)
    before = _events(uid)

    r = _claim_delete(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"ok": True, "deleted": "session_only",
                            "removed": {"identity_links": 1, "user_events": 2, "push_tokens": 0}}

    # This device's link and events are gone, and only those ...
    assert _links(uid) == [OTHER_DEVICE]
    assert _events(uid) == [e for e in before if e != THIS_DEVICE]
    # ... and the session is over.
    with server._sessions_lock:
        assert token not in server._sessions
    assert c.get("/api/session/ping", headers=_h(token)).status_code == 401


def test_claim_delete_leaves_other_devices_and_account_data(client):
    c, _, _ = client
    token = "sess-entry-claim-keep"
    _entry_session(token, MFL_UID)
    _seed(MFL_UID)

    assert _claim_delete(c, token).status_code == 200

    # Another device's link and events for the SAME id survive, as does the
    # server-fired (device-less) event.
    assert OTHER_DEVICE in _links(MFL_UID)
    assert _events(MFL_UID).count(OTHER_DEVICE) == 1
    assert "" in _events(MFL_UID)
    # Nothing keyed only by the id is touched: the users row and the board.
    assert _user_exists(MFL_UID)
    assert db_module.load_swipe_decisions(user_id=MFL_UID, scoring_format="1qb_ppr")


def test_claim_delete_reads_the_device_id_from_the_body_too(client):
    c, _, _ = client
    token = "sess-entry-claim-body"
    _entry_session(token, ESPN_UID)
    _seed(ESPN_UID)

    r = _claim_delete(c, token, body=json.dumps({"confirm": "delete", "device_id": THIS_DEVICE}),
                      device=None)
    assert r.status_code == 200
    assert r.get_json()["removed"] == {"identity_links": 1, "user_events": 2, "push_tokens": 0}
    assert _links(ESPN_UID) == [OTHER_DEVICE]


def test_claim_delete_without_a_device_id_only_ends_the_session(client):
    c, _, _ = client
    token = "sess-entry-claim-nodev"
    _entry_session(token, MFL_UID)
    _seed(MFL_UID)
    before = _events(MFL_UID)

    r = _claim_delete(c, token, device=None)
    assert r.status_code == 200
    assert r.get_json()["removed"] == {"identity_links": None, "user_events": None, "push_tokens": 0}
    assert _links(MFL_UID) == sorted([THIS_DEVICE, OTHER_DEVICE])
    assert _events(MFL_UID) == before
    assert c.get("/api/session/ping", headers=_h(token)).status_code == 401


def test_claim_delete_is_all_or_nothing(client, monkeypatch):
    """legal's condition (R27.2): the two deletes share one transaction, and
    the session ends only after it commits. Point the SECOND delete
    (user_events) at a table that doesn't exist: the first delete
    (identity_links) must roll back, the call fails, and the session lives."""
    from sqlalchemy import Column, MetaData, Table, Text
    c, _, _ = client
    token = "sess-entry-claim-atomic"
    _entry_session(token, MFL_UID)
    _seed(MFL_UID)
    links_before, events_before = _links(MFL_UID), _events(MFL_UID)

    missing = Table("user_events_missing_for_test", MetaData(),
                    Column("user_id", Text), Column("device_id", Text))
    monkeypatch.setattr(db_module, "user_events_table", missing)
    r = _claim_delete(c, token)
    monkeypatch.undo()

    assert r.status_code == 500, r.get_data(as_text=True)
    assert r.get_json() == {"error": "deletion_failed"}
    assert _links(MFL_UID) == links_before      # the first delete rolled back
    assert _events(MFL_UID) == events_before
    with server._sessions_lock:
        assert token in server._sessions        # not signed out
    assert c.get("/api/session/ping", headers=_h(token)).status_code == 200


@pytest.mark.parametrize("body", [None, "{}", json.dumps({"confirm": "yes"})])
def test_claim_delete_requires_the_confirmation(client, body):
    c, _, _ = client
    token = "sess-entry-claim-noconfirm"
    _entry_session(token, MFL_UID)
    _seed(MFL_UID)
    before = _events(MFL_UID)
    try:
        r = _claim_delete(c, token, body=body)
        assert r.status_code == 400
        assert r.get_json()["error"] == "confirmation_required"
        # Nothing happened: rows intact, session still live.
        assert _links(MFL_UID) == sorted([THIS_DEVICE, OTHER_DEVICE])
        assert _events(MFL_UID) == before
        assert c.get("/api/session/ping", headers=_h(token)).status_code == 200
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


def test_unverified_sleeper_username_session_still_403(client):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    server._sessions[token]["verified"] = False
    r = c.delete("/api/account", headers={**_h(token), "X-Device-Id": THIS_DEVICE}, data=CONFIRM)
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"
    assert _user_exists(UID)


def test_verified_session_keeps_the_full_deletion(client):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    db_module.link_identity(THIS_DEVICE, sleeper_user_id=UID)
    db_module.link_identity(OTHER_DEVICE, sleeper_user_id=UID)
    r = c.delete("/api/account", headers={**_h(token), "X-Device-Id": THIS_DEVICE})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert isinstance(body["deleted"], dict)
    assert body["deleted"]["users_deleted"] == 1
    assert body["deleted"]["identity_links_deleted"] == 2
    assert not _user_exists(UID)


def test_verified_entry_session_takes_the_full_deletion_not_the_claim_path(client):
    """A future proven entry (M11-R1) is verified: the full matrix applies."""
    c, _, _ = client
    token = "sess-entry-verified"
    with server._sessions_lock:
        server._sessions[token] = {"user_id": MFL_UID, "verified": True,
                                   "active_format": "1qb_ppr", "last_active": 0.0}
    _seed(MFL_UID)
    try:
        r = c.delete("/api/account", headers={**_h(token), "X-Device-Id": THIS_DEVICE})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert isinstance(r.get_json()["deleted"], dict)
        assert not _user_exists(MFL_UID)
        assert _links(MFL_UID) == []
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


def test_export_for_an_unverified_entry_session_still_403(client):
    c, _, flags_on = client
    flags_on.add("account.data_export")
    token = "sess-entry-export"
    _entry_session(token, ESPN_UID)
    try:
        r = c.get("/api/account/export", headers={**_h(token), "X-Device-Id": THIS_DEVICE})
        assert r.status_code == 403
        assert r.get_json()["error"] == "verification_required"
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


# ── Advisory (head-eng 2026-10-24): the device the MINT recorded wins ──────
# `/api/entry/platform` stores the minting request's device id on the session
# (sess["device_id"]); the claim-only delete then ignores whatever id its own
# request carries, so it can't be pointed at another device's rows. Sessions
# minted before that change have no device_id and fall back to the request's
# body / X-Device-Id.

def test_minted_device_id_wins_over_the_request_ids(client):
    c, _, _ = client
    token = "sess-entry-claim-minted"
    _entry_session(token, MFL_UID)
    server._sessions[token]["device_id"] = THIS_DEVICE
    _seed(MFL_UID)
    before = _events(MFL_UID)

    r = _claim_delete(c, token, device=OTHER_DEVICE,
                      body=json.dumps({"confirm": "delete", "device_id": OTHER_DEVICE}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["removed"] == {"identity_links": 1, "user_events": 2, "push_tokens": 0}
    # The minted device's rows are gone; the device the request named is untouched.
    assert _links(MFL_UID) == [OTHER_DEVICE]
    assert _events(MFL_UID) == [e for e in before if e != THIS_DEVICE]


def test_legacy_session_without_a_minted_device_falls_back_to_the_request(client):
    c, _, _ = client
    token = "sess-entry-claim-legacy"
    _entry_session(token, ESPN_UID)          # no device_id: minted before the change
    _seed(ESPN_UID)

    r = _claim_delete(c, token, device=None,
                      body=json.dumps({"confirm": "delete", "device_id": OTHER_DEVICE}))
    assert r.status_code == 200
    assert r.get_json()["removed"]["identity_links"] == 1
    assert _links(ESPN_UID) == [THIS_DEVICE]


# The real mint, on test_entry_platform_route's no-network fixtures.
from .test_entry_platform_route import (  # noqa: E402
    ENTRY_FLAGS, MFL_FIXTURE, MFL_LEAGUE, _fake_extension_builder,
)


@pytest.fixture()
def mint_client():
    import copy
    from unittest.mock import patch
    from sqlalchemy import create_engine
    import backend.mfl_service as mfl
    from backend.database import metadata

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    with open(MFL_FIXTURE) as f:
        bundle = json.load(f)
    with server._sessions_lock:
        before = set(server._sessions)
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in ENTRY_FLAGS), \
         patch.object(mfl, "resolve_host", lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "fetch_league_bundle", lambda *a, **kw: copy.deepcopy(bundle)), \
         patch.object(server, "_extension_build_session", _fake_extension_builder), \
         patch.object(server, "_link_device_identity", lambda **kw: None):
        try:
            yield server.app.test_client()
        finally:
            with server._sessions_lock:
                for t in set(server._sessions) - before:
                    server._sessions.pop(t, None)


def _mint(c, device=None):
    headers = {"Content-Type": "application/json"}
    if device:
        headers["X-Device-Id"] = device
    r = c.post("/api/entry/platform", headers=headers, data=json.dumps(
        {"platform": "mfl", "mfl_league_id": MFL_LEAGUE, "year": 2026, "franchise_id": "0001"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def test_the_mint_records_its_device_id_on_the_session(mint_client):
    body = _mint(mint_client, device=THIS_DEVICE)
    with server._sessions_lock:
        assert server._sessions[body["session_token"]]["device_id"] == THIS_DEVICE
    bare = _mint(mint_client)
    with server._sessions_lock:
        assert "device_id" not in server._sessions[bare["session_token"]]


def test_minted_session_claim_delete_ignores_a_different_request_id(mint_client):
    body = _mint(mint_client, device=THIS_DEVICE)
    uid, token = body["user_id"], body["session_token"]
    _seed(uid)

    r = mint_client.delete("/api/account", data=CONFIRM, headers={
        **_h(token), "X-Device-Id": OTHER_DEVICE})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["deleted"] == "session_only"
    assert _links(uid) == [OTHER_DEVICE]
