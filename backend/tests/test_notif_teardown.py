"""Teardown 05-01 + 05-04 — notification timezone sync, consent defaults,
winback honesty, and the first_match/new_match dedup.

Covers:
  1. `notif.tz_sync` — register-device adopts a valid non-ET X-User-TZ
     header while the stored tz is still the default; never overwrites an
     explicit non-default value; rejects invalid tz; dark = no-op.
  2. Quiet-hours math actually consumes a non-ET tz (_next_8am_utc /
     _local_hour_in_quiet_window + a full _send_typed_push queue check).
  3. `notif.reengagement_default_off` — reengagement serves 0 with no
     stored pref; stored prefs always win; bucket gate honors it.
  4. `notif.honest_winbacks` — winback_dormant sends nothing for a dormant
     user with zero unread matches, truthful copy otherwise, and stops for
     life after 3 consecutive unanswered winbacks. Legacy copy when dark.
  5. 05-04c (unflagged) — one push per match: first-ever match →
     `first_match` only; later matches → `new_match` only.

Isolation pattern mirrors test_verified_sessions.py.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
from backend.database import metadata

UID = "313560442465169408"
LA = "America/Los_Angeles"


def _h(token, tz=None):
    h = {"X-Session-Token": token, "Content-Type": "application/json"}
    if tz:
        h["X-User-TZ"] = tz
    return h


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-notif-tok"
    sess = {"user_id": UID, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on: set = set()
    flag_fn = lambda k: k in flags_on   # noqa: E731
    # server.py binds is_enabled at import; database.py lazy-imports it from
    # feature_flags at call time — patch both to the same switchable set.
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", flag_fn), \
         patch.object(feature_flags, "is_enabled", flag_fn), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, flags_on
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _register_device(c, token, tz):
    return c.post("/api/notifications/register-device",
                  headers=_h(token, tz=tz),
                  data=json.dumps({"device_token": "ExponentPushToken[x1]",
                                   "platform": "ios"}))


# ---------------------------------------------------------------------------
# 1. notif.tz_sync
# ---------------------------------------------------------------------------

def test_tz_sync_dark_is_noop(client):
    c, token, _ = client
    assert _register_device(c, token, LA).status_code == 200
    assert db_module.get_notification_prefs(UID)["tz"] == "America/New_York"


def test_tz_sync_adopts_device_tz_when_default(client):
    c, token, flags_on = client
    flags_on.add("notif.tz_sync")
    assert _register_device(c, token, LA).status_code == 200
    assert db_module.get_notification_prefs(UID)["tz"] == LA


def test_tz_sync_rejects_invalid_tz(client):
    c, token, flags_on = client
    flags_on.add("notif.tz_sync")
    assert _register_device(c, token, "Not/AZone").status_code == 200
    assert db_module.get_notification_prefs(UID)["tz"] == "America/New_York"


def test_tz_sync_never_overwrites_explicit_non_default(client):
    c, token, flags_on = client
    flags_on.add("notif.tz_sync")
    db_module.upsert_notification_prefs(UID, tz="Europe/London")
    assert _register_device(c, token, LA).status_code == 200
    assert db_module.get_notification_prefs(UID)["tz"] == "Europe/London"


# ---------------------------------------------------------------------------
# 2. Quiet-hours math in a non-ET tz
# ---------------------------------------------------------------------------

def _tz_with_local_hour(target_hour: int) -> str:
    """An IANA Etc/GMT zone whose current local hour == target_hour."""
    delta = (target_hour - datetime.now(timezone.utc).hour) % 24
    # Etc/GMT-N == UTC+N (sign is inverted by POSIX convention).
    return f"Etc/GMT-{delta}" if delta <= 14 else f"Etc/GMT+{24 - delta}"


def test_next_8am_utc_respects_non_et_tz():
    out = datetime.fromisoformat(server._next_8am_utc(LA))
    local = out.astimezone(ZoneInfo(LA))
    assert (local.hour, local.minute) == (8, 0)
    # And it is genuinely a different instant from the ET default's 8am.
    et = datetime.fromisoformat(server._next_8am_utc("America/New_York"))
    assert out != et


def test_local_hour_quiet_window_uses_given_tz():
    assert server._local_hour_in_quiet_window(_tz_with_local_hour(23)) is True
    assert server._local_hour_in_quiet_window(_tz_with_local_hour(12)) is False


def test_send_typed_push_queues_during_non_et_quiet_hours(client):
    """End-to-end: a stored non-ET tz whose local time is 23:00 sends the
    push to the quiet-hours queue instead of Expo."""
    c, token, _ = client
    quiet_tz = _tz_with_local_hour(23)
    db_module.upsert_notification_prefs(UID, tz=quiet_tz)

    with patch.object(server, "load_device_tokens_for_users",
                      MagicMock(return_value=[{"device_token":
                                               "ExponentPushToken[x1]"}])), \
         patch.object(server, "_send_expo_push", MagicMock()) as expo, \
         patch.object(server, "queue_notification", MagicMock()) as q:
        server._send_typed_push(UID, "new_match", title="t", body="b",
                                data={}, dedup_key="m1")
    expo.assert_not_called()
    q.assert_called_once()
    deliver_after = q.call_args.kwargs["deliver_after"]
    local = datetime.fromisoformat(deliver_after).astimezone(ZoneInfo(quiet_tz))
    assert (local.hour, local.minute) == (8, 0)   # next 8am in THAT tz


# ---------------------------------------------------------------------------
# 3. notif.reengagement_default_off
# ---------------------------------------------------------------------------

def test_reengagement_defaults_on_while_dark(client):
    assert db_module.get_notification_prefs(UID)["reengagement"] == 1


def test_reengagement_defaults_off_with_flag(client):
    _, _, flags_on = client
    flags_on.add("notif.reengagement_default_off")
    assert db_module.get_notification_prefs(UID)["reengagement"] == 0


def test_reengagement_stored_pref_wins_over_flag_default(client):
    _, _, flags_on = client
    flags_on.add("notif.reengagement_default_off")
    db_module.upsert_notification_prefs(UID, reengagement=1)   # explicit opt-in
    assert db_module.get_notification_prefs(UID)["reengagement"] == 1


def test_reengagement_bucket_gate_skips_push_under_flag_default(client):
    _, _, flags_on = client
    flags_on.add("notif.reengagement_default_off")
    with patch.object(server, "load_device_tokens_for_users",
                      MagicMock(return_value=[{"device_token":
                                               "ExponentPushToken[x1]"}])), \
         patch.object(server, "_send_expo_push", MagicMock()) as expo:
        server._send_typed_push(UID, "winback_dormant", title="t", body="b")
    expo.assert_not_called()


# ---------------------------------------------------------------------------
# 4. notif.honest_winbacks — daily-tick winback_dormant
# ---------------------------------------------------------------------------

def _dormant_user(days_inactive=40):
    now = datetime.now(timezone.utc)
    return [{
        "sleeper_user_id":  UID,
        "username":         "dormant",
        "display_name":     "Dormant",
        "signup_at":        (now - timedelta(days=120)).isoformat(),
        "last_active_at":   (now - timedelta(days=days_inactive)).isoformat(),
        "last_rank_at":     None,
        "unlocked_formats": ["1qb_ppr"],
    }]


def _run_daily_tick(c, unread):
    with patch.object(server, "load_all_signed_up_users",
                      MagicMock(return_value=_dormant_user())), \
         patch.object(server, "load_unread_match_count",
                      MagicMock(return_value=unread)), \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        r = c.post("/api/cron/daily-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200
    return push, r.get_json()


def test_winback_dormant_dark_keeps_legacy_copy(client):
    c, _, _ = client
    push, body = _run_daily_tick(c, unread=0)
    calls = [k for k in push.call_args_list if k.args[1] == "winback_dormant"]
    assert len(calls) == 1
    assert calls[0].kwargs["body"] == \
        "New trade matches are waiting when you're ready."
    assert body["winback_dormant"] == 1


def test_honest_winback_silent_when_nothing_waiting(client):
    c, _, flags_on = client
    flags_on.add("notif.honest_winbacks")
    push, body = _run_daily_tick(c, unread=0)
    assert not [k for k in push.call_args_list
                if k.args[1] == "winback_dormant"]
    assert body["winback_dormant"] == 0


def test_honest_winback_truthful_copy_with_count(client):
    c, _, flags_on = client
    flags_on.add("notif.honest_winbacks")
    push, body = _run_daily_tick(c, unread=2)
    calls = [k for k in push.call_args_list if k.args[1] == "winback_dormant"]
    assert len(calls) == 1
    assert "2 unreviewed trade matches" in calls[0].kwargs["body"]
    assert calls[0].kwargs["data"] == {"unread_count": 2}
    assert body["winback_dormant"] == 1


def test_honest_winback_lifetime_stop_after_three_unanswered(client):
    c, _, flags_on = client
    flags_on.add("notif.honest_winbacks")
    for _ in range(3):     # 3 winbacks sent, all after last_active (40d ago)
        db_module.log_notification_send(UID, "winback_dormant")
    push, body = _run_daily_tick(c, unread=5)   # even with matches waiting
    assert not [k for k in push.call_args_list
                if k.args[1] == "winback_dormant"]
    assert body["winback_dormant"] == 0


def test_honest_winback_resumes_after_user_returns(client):
    """Two unanswered winbacks (< the stop threshold) keep nudges eligible;
    the count is 'consecutive since last session' because it only counts
    log rows newer than last_active_at."""
    c, _, flags_on = client
    flags_on.add("notif.honest_winbacks")
    for _ in range(2):
        db_module.log_notification_send(UID, "winback_dormant")
    push, body = _run_daily_tick(c, unread=1)
    assert len([k for k in push.call_args_list
                if k.args[1] == "winback_dormant"]) == 1
    assert body["winback_dormant"] == 1


# ---------------------------------------------------------------------------
# 5. 05-04c — one push per match (first_match vs new_match)
# ---------------------------------------------------------------------------

def test_match_push_kind_first_then_new(client):
    assert server._match_push_kind(UID) == "first_match"
    db_module.log_notification_send(UID, "first_match", dedup_key="lifetime")
    assert server._match_push_kind(UID) == "new_match"


def test_exactly_one_push_per_match_event(client):
    """Simulate the swipe-path sequence for two consecutive matches: the
    first delivers only first_match, the second only new_match."""
    db_module.upsert_notification_prefs(UID, quiet_hours_enabled=0)
    sent_kinds = []

    def _deliver(match_id):
        kind = server._match_push_kind(UID)
        if kind == "first_match":
            server._send_typed_push(UID, "first_match", title="first",
                                    body="b", data={}, dedup_key="lifetime")
        else:
            server._send_typed_push(UID, "new_match", title="new", body="b",
                                    data={}, dedup_key=str(match_id))
        sent_kinds.append(kind)

    with patch.object(server, "load_device_tokens_for_users",
                      MagicMock(return_value=[{"device_token":
                                               "ExponentPushToken[x1]"}])), \
         patch.object(server, "_send_expo_push", MagicMock()) as expo:
        _deliver(1)
        _deliver(2)

    assert sent_kinds == ["first_match", "new_match"]
    assert expo.call_count == 2          # one push per match, not two each
