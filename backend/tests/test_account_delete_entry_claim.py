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
