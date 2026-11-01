"""D1 roster-move consent (contract §2; consent.md §4.2–§4.4 / §8.1; legal R15.2,
R15.3, R15.8): the server-authored texts, the rolling 7 × 24 h window, the
append-only records, withdrawals from every path, and GET/DELETE
/api/platform-write-consent. Harness: test_fa_move_route.py (in-memory DB,
no network).
"""
from __future__ import annotations

import hashlib
import inspect
import json
from datetime import timedelta

import pytest
from sqlalchemy import event

import backend.database as db_module
import backend.server as server
import backend.sleeper_write as sleeper_write
from backend import accounts
from backend import fa_move_copy as copy
from backend.tests.test_fa_move_route import (  # noqa: F401  (h is a fixture)
    _ABSENT, ADD, DROP, KEEP, LEAGUE, SLEEPER_UID, THEIRS, TOKEN, USER, V1, V2, _err, _jwt,
    _rosters, h,
)

WITHDRAWAL_NOTICE = ("Roster moves are off. Fleeced won't add or drop players until you agree "
                     "again. Moves already made stay in Sleeper.")                # R15.2.6


def _hash(text: dict) -> str:
    return hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The texts: legal-final, verbatim, pinned by hash (the old S22)
# ---------------------------------------------------------------------------

# A version is never edited in place: changed wording is a NEW copy_version
# (and a new row here). If one of these fails, revert the text, don't re-pin.
PINNED = {
    ("sleeper", V1, "en-US"): "f4e500eb1528c6ce425dbdd8a2ce4757fc2b5e7a12a263157b5961024c283527",
    ("sleeper", V2, "en-US"): "38e5e2064bc84de07202bc57649d49bc668c554901be90316a6e6fb1fc2395ee",
}


def test_texts_are_pinned_by_hash():
    assert set(copy.CONSENT_TEXTS) == set(PINNED)
    for key, digest in PINNED.items():
        assert _hash(copy.CONSENT_TEXTS[key]) == digest, key


def test_v1_is_r15_8_verbatim():
    v1 = copy.CONSENT_TEXTS[("sleeper", V1, "en-US")]
    assert v1 == {
        "title": "Let Fleeced make roster moves in Sleeper?",
        "body": [
            "Fleeced will add and drop players in your Sleeper leagues for you, using the "
            "Sleeper sign-in you connected.",
            "Moves are final on Sleeper. Fleeced can't undo them, and a player you drop can be "
            "picked up by another team.",
            "This uses an unofficial Sleeper connection, so it could stop working at any time.",
            "Your OK lasts 7 days. You'll still confirm every move. Turn it off any time in "
            "Settings › Leagues › Stop roster moves.",
        ],
        "checkbox_label": "I authorize Fleeced to add and drop players in my Sleeper leagues "
                          "for the next 7 days.",
        "this_move": "This move: {cta} in {league}.",
        "button_label": "Make the move",
    }


def test_v2_differs_from_v1_exactly_where_r15_8_says():
    v1 = copy.CONSENT_TEXTS[("sleeper", V1, "en-US")]
    v2 = copy.CONSENT_TEXTS[("sleeper", V2, "en-US")]
    assert v2["body"][0] == ("Fleeced will add and drop players, and place waiver claims, in "
                             "your Sleeper leagues for you, using the Sleeper sign-in you "
                             "connected.")
    assert v2["body"][1] == ("Moves are final on Sleeper and Fleeced can't undo them. A player "
                             "you drop can be picked up by another team. A waiver claim runs on "
                             "Sleeper's schedule and spends any bid you set.")
    # No cancel sentence until platforms-pm verifies cancelling (capture Q7b).
    assert "cancel" not in " ".join(v2["body"]).lower()
    assert v2["checkbox_label"] == ("I authorize Fleeced to add and drop players and place "
                                    "waiver claims in my Sleeper leagues for the next 7 days.")
    assert v2["body"][2:] == v1["body"][2:]
    assert {k: v2[k] for k in ("title", "this_move", "button_label")} == \
           {k: v1[k] for k in ("title", "this_move", "button_label")}


def test_the_server_shows_v1_while_claims_are_refused():
    assert copy.CURRENT_CONSENT_VERSION == {"sleeper": V1}
    assert copy.consent_block("sleeper")["copy_version"] == V1
    assert copy.consent_block("mfl") is None and copy.consent_block("espn") is None


def test_withdrawal_notice_and_settings_lines_verbatim():
    assert copy.withdrawal_notice("sleeper") == WITHDRAWAL_NOTICE
    assert copy.STATUS_LINE == "Roster moves: on until {date}"
    assert copy.STOP_LABEL == "Stop roster moves"


# ---------------------------------------------------------------------------
# Validity (consent.md §4.2)
# ---------------------------------------------------------------------------

def _grant(h, at=None, version=V1, account=SLEEPER_UID):
    return db_module.record_platform_write_grant(
        user_id=USER, platform="sleeper", platform_user_id=account, copy_version=version,
        locale="en-US", consented_at=at or h.now, client_platform="iphone",
        app_version="1.22.0", trigger_attempt_id="a1")


def _active(h, at, account=SLEEPER_UID, version=V1):
    return db_module.active_platform_write_grant(USER, "sleeper", account, version, at)


def test_window_is_rolling_7_days_from_the_server_tick(h):
    g = _grant(h)
    assert _active(h, h.now + timedelta(days=7) - timedelta(minutes=1))["consent_id"] == g["consent_id"]
    assert _active(h, h.now + timedelta(days=7)) is None


def test_moves_never_extend_the_window(h):
    assert h.post().status_code == 200                      # the grant's own move
    (grant,) = [c for c in h.consents() if c["kind"] == "grant"]
    h.now = h.now + timedelta(days=6)
    h.rosters = _rosters(mine=(KEEP, ADD))
    assert h.post(add_player_id="7777", drop_player_id=ADD, consent=_ABSENT).status_code == 200
    h.now = h.now + timedelta(days=1)                       # 7 d after the tick
    h.rosters = _rosters(mine=(KEEP, "7777"))
    r = h.post(add_player_id="7778", drop_player_id="7777", consent=_ABSENT)
    assert r.status_code == 409 and _err(r)["error"] == "consent_required"
    assert [c for c in h.consents() if c["kind"] == "grant"] == [grant]


def test_bound_to_the_platform_account(h):
    _grant(h, account="other-sleeper-account")
    assert _active(h, h.now) is None
    assert _active(h, h.now, account="other-sleeper-account") is not None
    # Through the route: the stored credential is SLEEPER_UID's.
    r = h.post(consent=_ABSENT)
    assert r.status_code == 409 and _err(r)["error"] == "consent_required"


def test_a_version_bump_invalidates_every_older_grant(h, monkeypatch):
    _grant(h)
    assert _active(h, h.now) is not None
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V2)
    assert server._fa_move_grant(USER, "sleeper", SLEEPER_UID, h.now) is None
    r = h.post(consent=_ABSENT)
    body = _err(r)
    assert r.status_code == 409 and body["consent"]["copy_version"] == V2


def test_the_latest_grant_decides(h):
    _grant(h, at=h.now - timedelta(days=1))
    _grant(h, at=h.now - timedelta(hours=1), version=V2)    # latest, but not current
    assert _active(h, h.now) is None


# ---------------------------------------------------------------------------
# Append-only (R15.3): no UPDATE or DELETE of either table, ever
# ---------------------------------------------------------------------------

@pytest.fixture()
def statements(h):
    seen: list[str] = []

    def _record(conn, cursor, statement, params, context, executemany):
        seen.append(" ".join(statement.split()).lower())
    event.listen(h.engine, "before_cursor_execute", _record)
    yield seen
    event.remove(h.engine, "before_cursor_execute", _record)


def _mutations(seen):
    return [s for s in seen if ("platform_write_consents" in s or "platform_write_moves" in s)
            and (s.startswith("update") or s.startswith("delete"))]


def test_every_path_is_append_only(h, statements):
    assert h.post().status_code == 200                                     # grant + move
    h.platform.mode = "read_timeout"
    h.post(add_player_id="7777", drop_player_id=KEEP)                     # unknown outcome
    assert h.client.delete("/api/platform-write-consent?platform=sleeper",
                           headers={"X-Session-Token": TOKEN}).status_code == 200
    _grant(h)
    assert h.client.delete("/api/sleeper/link",
                           headers={"X-Session-Token": TOKEN}).status_code == 200
    assert _mutations(statements) == []
    # Each tick appended a grant (both moves carried consent); Settings ended
    # both open grants with one row each, and disconnect ended the third.
    kinds = [c["kind"] for c in h.consents()]
    assert kinds.count("grant") == 3 and kinds.count("withdrawal") == 3


def test_no_token_in_any_record(h):
    raw = _jwt()
    db_module.upsert_sleeper_credential(USER, SLEEPER_UID, sleeper_write.encrypt_token(raw), None)
    cipher = db_module.get_sleeper_credential(USER)["token_encrypted"]
    assert h.post().status_code == 200
    dump = json.dumps(h.consents() + h.moves(), default=str)
    assert raw not in dump and cipher not in dump and raw.split(".")[1] not in dump


# ---------------------------------------------------------------------------
# GET / DELETE /api/platform-write-consent (contract §2)
# ---------------------------------------------------------------------------

def _get(h, platform="sleeper"):
    q = "" if platform is None else f"?platform={platform}"
    return h.client.get(f"/api/platform-write-consent{q}", headers={"X-Session-Token": TOKEN})


def _delete(h, platform="sleeper"):
    return h.client.delete(f"/api/platform-write-consent?platform={platform}",
                           headers={"X-Session-Token": TOKEN})


def test_routes_never_follow_the_kill_switch(h):
    """Contract §2: GET always answers and DELETE always works, so a user can
    withdraw while moves are switched off (sabotage: re-add the flag gate)."""
    _grant(h)
    h.flags.clear()                                          # every flag off
    r = _get(h)
    assert r.status_code == 200 and r.get_json()["valid"] is True
    r = _delete(h)
    assert r.status_code == 200 and r.get_json()["notice"] == WITHDRAWAL_NOTICE
    assert [c["withdrawn_via"] for c in h.consents() if c["kind"] == "withdrawal"] == ["settings"]
    body = _get(h).get_json()
    assert body["valid"] is False and body["status_line"] is None and body["stop_label"] is None
    assert body["consent"]["copy_version"] == V1             # the block is still there
    # The move route does follow it.
    assert h.post().status_code == 404


@pytest.mark.parametrize("platform", [None, "", "fleaflicker", "Sleeper", "local"])
def test_platform_is_validated(h, platform):
    r = _get(h, platform)
    assert r.status_code == 400 and _err(r)["error"] == "bad_request"


def test_get_without_a_grant(h):
    body = _get(h).get_json()
    assert body == {"platform": "sleeper", "valid": False, "until": None,
                    "consent": copy.consent_block("sleeper", reason="first"),
                    "status_line": None, "stop_label": None}
    assert body["consent"]["copy_version"] == V1 and body["consent"]["locale"] == "en-US"
    assert set(body["consent"]) == {"copy_version", "locale", "title", "body",
                                    "checkbox_label", "this_move", "button_label",
                                    "links", "reason"}


def test_consent_links_are_terms_and_privacy():
    """Contract §2 `links`: legal v1's "Terms · Privacy" row, the app's pages."""
    assert copy.consent_block("sleeper")["links"] == [
        {"label": "Terms", "url": "https://fantasy-trade-finder.onrender.com/terms"},
        {"label": "Privacy", "url": "https://fantasy-trade-finder.onrender.com/privacy"}]
    assert "reason" not in copy.consent_block("sleeper")


def _reason(h):
    return _get(h).get_json()["consent"].get("reason")


def test_reason_first_lapsed_version_withdrawn(h, monkeypatch):
    assert _reason(h) == "first"
    _grant(h, at=h.now - timedelta(days=8))
    assert _reason(h) == "lapsed"
    _grant(h)
    assert _reason(h) is None                                 # valid: nothing to ask
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V2)
    assert _reason(h) == "version"
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V1)
    assert _delete(h).status_code == 200
    assert _reason(h) == "withdrawn"
    _grant(h, account="another-account")                      # not this credential's
    assert _reason(h) == "withdrawn"


def test_reason_absent_without_a_credential(h):
    db_module.delete_sleeper_credential(USER, withdrawn_via="disconnect")
    assert "reason" not in _get(h).get_json()["consent"]


def test_reason_rides_the_409_too(h):
    _grant(h, at=h.now - timedelta(days=8))
    r = h.post(consent=_ABSENT)
    assert r.status_code == 409 and _err(r)["consent"]["reason"] == "lapsed"


def test_get_with_an_open_grant(h, monkeypatch):
    from datetime import datetime, timezone
    h.now = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)   # Nov 1, 8 pm in Los Angeles
    g = _grant(h)
    body = _get(h).get_json()
    assert body["valid"] is True and body["until"] == g["expires_at"]
    # Expires Nov 9 03:00 UTC = Nov 8 in US Pacific: never later than the user's date.
    assert body["status_line"] == "Roster moves: on until Nov 8"
    assert body["stop_label"] == "Stop roster moves"


def test_get_needs_the_credential(h):
    _grant(h)
    db_module.delete_sleeper_credential(USER, withdrawn_via="disconnect")
    assert _get(h).get_json()["valid"] is False


@pytest.mark.parametrize("platform", ["mfl", "espn"])
def test_get_other_platforms_have_no_text_yet(h, platform):
    body = _get(h, platform).get_json()
    assert body == {"platform": platform, "valid": False, "until": None, "consent": None,
                    "status_line": None, "stop_label": None}


def test_delete_withdraws_once_and_is_idempotent(h):
    _grant(h)
    first, second = _delete(h), _delete(h)
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json() == {
        "platform": "sleeper", "valid": False, "notice": WITHDRAWAL_NOTICE}
    withdrawals = [c for c in h.consents() if c["kind"] == "withdrawal"]
    assert [w["withdrawn_via"] for w in withdrawals] == ["settings"]
    assert withdrawals[0]["refers_to"] == [c for c in h.consents() if c["kind"] == "grant"][0]["consent_id"]
    (ev,) = h.events_named("fa_move_consent_withdrawn")
    assert ev[2]["props"] == {"via": "settings", "league_platform": "sleeper"}
    assert _get(h).get_json()["valid"] is False
    r = h.post(consent=_ABSENT)                              # the next move asks again
    assert r.status_code == 409 and _err(r)["error"] == "consent_required"


@pytest.mark.parametrize("enforce", [False, True])
def test_delete_needs_a_session_only(h, enforce):
    """Contract §2 / R15.2.6: withdrawal is as easy as consent, so an
    UNVERIFIED session can stop roster moves (whatever the write-gate flag)."""
    if enforce:
        h.flags.add("auth.enforce_verified_writes")
    _grant(h)
    h.sess["verified"] = False
    r = _delete(h)
    assert r.status_code == 200 and r.get_json()["notice"] == WITHDRAWAL_NOTICE
    assert [c["withdrawn_via"] for c in h.consents() if c["kind"] == "withdrawal"] == ["settings"]
    assert _get(h).status_code == 200                        # GET too


def test_no_session_is_401(h):
    for method in (h.client.get, h.client.delete):
        assert method("/api/platform-write-consent?platform=sleeper").status_code == 401


def test_no_unverified_write_gate_on_the_consent_route():
    """Structural twin (sabotage: put `@_gate_unverified_write` or a
    `_verified_write_denial` check back on it)."""
    view = server.app.view_functions["platform_write_consent_route"]
    assert not hasattr(view, "__wrapped__")                  # no decorator wrapped it
    src = inspect.getsource(server.platform_write_consent_route)
    for check in ("_verified_write_denial(", "_gate_unverified_write\n", '"verified"'):
        assert check not in src, check


# ---------------------------------------------------------------------------
# Every Sleeper-credential deletion withdraws (consent.md §4.4)
# ---------------------------------------------------------------------------

def test_disconnect_withdraws(h):
    _grant(h)
    r = h.client.delete("/api/sleeper/link", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200 and r.get_json() == {"connected": False}
    (w,) = [c for c in h.consents() if c["kind"] == "withdrawal"]
    assert w["withdrawn_via"] == "disconnect" and w["platform"] == "sleeper"
    (ev,) = h.events_named("fa_move_consent_withdrawn")
    assert ev[2]["props"] == {"via": "disconnect", "league_platform": "sleeper"}
    assert ev[2]["touch_user"] is True                      # the user's own act


def test_disconnect_without_a_grant_records_nothing(h):
    h.client.delete("/api/sleeper/link", headers={"X-Session-Token": TOKEN})
    assert h.consents() == [] and h.events_named("fa_move_consent_withdrawn") == []


def _propose(h):
    return h.client.post("/api/trades/propose", headers={"X-Session-Token": TOKEN,
                                                         "Content-Type": "application/json"},
                         data=json.dumps({"league_id": LEAGUE, "their_roster_id": 4,
                                          "give_player_ids": [DROP],
                                          "receive_player_ids": [THEIRS]}))


def test_trade_send_expiry_withdraws(h):
    _grant(h)
    db_module.upsert_sleeper_credential(USER, SLEEPER_UID,
                                        sleeper_write.encrypt_token(_jwt(-60)), None)
    r = _propose(h)
    assert r.status_code == 409 and r.get_json()["error"] == "sleeper_expired"
    (w,) = [c for c in h.consents() if c["kind"] == "withdrawal"]
    assert w["withdrawn_via"] == "credential_expired"
    (ev,) = h.events_named("fa_move_consent_withdrawn")
    assert ev[2]["touch_user"] is False                     # a system withdrawal (F2)


def test_trade_send_token_rejection_withdraws(h, monkeypatch):
    _grant(h)

    def _rejected(token, req):
        raise sleeper_write.SleeperAuthError("Sleeper rejected the token (HTTP 401)")
    monkeypatch.setattr(server._sleeper_write, "propose_trade", _rejected)
    r = _propose(h)
    assert r.status_code == 409 and r.get_json()["error"] == "sleeper_rejected"
    (w,) = [c for c in h.consents() if c["kind"] == "withdrawal"]
    assert w["withdrawn_via"] == "credential_rejected"
    assert db_module.get_sleeper_credential(USER) is None


def test_move_route_expiry_withdraws(h):
    _grant(h)
    db_module.upsert_sleeper_credential(USER, SLEEPER_UID,
                                        sleeper_write.encrypt_token(_jwt(-60)), None)
    r = h.post(consent=_ABSENT)
    assert r.status_code == 409 and _err(r)["error"] == "sleeper_expired"
    assert [c["withdrawn_via"] for c in h.consents() if c["kind"] == "withdrawal"] == [
        "credential_expired"]


def test_no_unrecorded_credential_deletion_in_server():
    """Every Sleeper-credential deletion goes through `_drop_sleeper_credential`
    (sabotage: call delete_sleeper_credential directly again)."""
    src = open(server.__file__, encoding="utf-8").read()
    assert src.count("delete_sleeper_credential(") == 1
    assert "delete_sleeper_credential(user_id, withdrawn_via=via)" in src


# ---------------------------------------------------------------------------
# Account data: export includes both tables (deletion: test_account_deletion_coverage)
# ---------------------------------------------------------------------------

def test_consent_and_moves_in_export(h):
    assert h.post().status_code == 200
    tables = accounts.export_user_data(USER)["tables"]
    assert len(tables["platform_write_consents"]) == 1
    assert {m["phase"] for m in tables["platform_write_moves"]} == {"sent", "result"}


def test_both_tables_are_private_tables():
    assert {"platform_write_consents", "platform_write_moves"} <= set(
        accounts._ADDITIONAL_PRIVATE_TABLES)
