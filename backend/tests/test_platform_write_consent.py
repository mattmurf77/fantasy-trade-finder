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
# Each hash covers EVERY field of the version's consent block (R28.26 2a):
# title, body, checkbox_label, this_move, button_label and links. Re-pinned
# once, 11-01, when `links` moved inside each version (nothing had shipped).
PINNED = {
    ("sleeper", V1, "en-US"): "c9a41eaa22b7767fc82ad436190f69ebb18bd902f595f1e9c8a9bb9bbab7773d",
    ("sleeper", V2, "en-US"): "498e6f994ba1dbee75d0881da9d67e8746d230f7d157a50960aff0b8e497cc3a",
    # DRAFT (legal R28.27): pinned too, so a draft is also never edited in place.
    ("mfl", copy.MFL_ROSTER_MOVES_V1, "en-US"):
        "6fec0497b341ec37f190cbd600c227a2a8b5d244cb898a4adec27c3fd2b4b015",
    ("mfl", copy.MFL_ROSTER_MOVES_V2, "en-US"):
        "4e16f4f632959f1a350220eecd308f60f0e8275d323121f2239da94d74dc53e6",
    ("espn", copy.ESPN_ROSTER_MOVES_V1, "en-US"):
        "7478aebb94333d22dd556b90d6c432b350f3796a24008ec8e7c43ecc8ea0b97e",
    ("espn", copy.ESPN_ROSTER_MOVES_V2, "en-US"):
        "b61dcee3345528c3b2866d685a7d8154701bb92edd4fcb40a8258c2110e9de72",
}
BLOCK_FIELDS = {"title", "body", "checkbox_label", "this_move", "button_label", "links"}


def test_texts_are_pinned_by_hash():
    assert set(copy.CONSENT_TEXTS) == set(PINNED)
    for key, digest in PINNED.items():
        assert _hash(copy.CONSENT_TEXTS[key]) == digest, key


def test_the_hash_covers_every_field_the_block_shows():
    """Every field the served block carries (besides copy_version / locale,
    which are the key, and reason, which is per request) lives in the hashed
    per-version text, so editing ANY of them in place breaks the pin."""
    for key, text in copy.CONSENT_TEXTS.items():
        assert set(text) == BLOCK_FIELDS, key
    block = copy.consent_block("sleeper", reason="first")
    assert set(block) - {"copy_version", "locale", "reason"} == BLOCK_FIELDS
    text = copy.CONSENT_TEXTS[("sleeper", V1, "en-US")]
    assert {f: (list(block[f]) if f in ("body", "links") else block[f]) for f in BLOCK_FIELDS} \
        == {f: (list(text[f]) if f in ("body", "links") else text[f]) for f in BLOCK_FIELDS}


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
        "links": ({"label": "Terms", "url": "https://fantasy-trade-finder.onrender.com/terms"},
                  {"label": "Privacy", "url": "https://fantasy-trade-finder.onrender.com/privacy"}),
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
def test_an_unverified_session_with_the_victims_id_is_refused(h, enforce):
    """head-eng's security check (contract §2): a username-only sign-in yields
    the victim's user_id in an UNVERIFIED session. It must neither forge a
    withdrawal into the append-only record (or fire the event) nor read
    whether the victim consented, whatever the write-gate flag says."""
    if enforce:
        h.flags.add("auth.enforce_verified_writes")
    grant = _grant(h)                                        # the victim's real grant
    h.sess["verified"] = False                               # the squatter's session, same id
    for r in (_delete(h), _get(h)):
        assert r.status_code == 403
        body = _err(r)
        assert body["error"] == "verification_required"
        assert "valid" not in body and "until" not in body   # nothing about the grant leaks
    assert [c for c in h.consents() if c["kind"] == "withdrawal"] == []
    assert h.events_named("fa_move_consent_withdrawn") == []
    assert _active(h, h.now)["consent_id"] == grant["consent_id"]
    h.sess["verified"] = True                                # the real, verified owner can
    assert _get(h).get_json()["valid"] is True
    assert _delete(h).status_code == 200


def test_no_session_is_401(h):
    for method in (h.client.get, h.client.delete):
        assert method("/api/platform-write-consent?platform=sleeper").status_code == 401


def test_the_consent_route_checks_both_denials():
    """Structural twin (sabotage: drop either denial)."""
    src = inspect.getsource(server.platform_write_consent_route)
    assert "_verified_write_denial(sess)" in src and "_verified_read_denial(sess)" in src


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


# ---------------------------------------------------------------------------
# Per-platform versions (legal R28.27 item 3): MFL and ESPN, DRAFT
# ---------------------------------------------------------------------------

MFL_V1, MFL_V2 = copy.MFL_ROSTER_MOVES_V1, copy.MFL_ROSTER_MOVES_V2
ESPN_V1, ESPN_V2 = copy.ESPN_ROSTER_MOVES_V1, copy.ESPN_ROSTER_MOVES_V2
DRAFTS = {("mfl", MFL_V1), ("mfl", MFL_V2), ("espn", ESPN_V1), ("espn", ESPN_V2)}


def test_mfl_and_espn_have_their_own_versions_marked_draft():
    assert copy.DRAFT_CONSENT_VERSIONS == {v for _, v in DRAFTS}
    for platform, version in DRAFTS:
        assert version.startswith(f"{platform}-roster-moves-v")
        text = copy.CONSENT_TEXTS[(platform, version, "en-US")]
        joined = " ".join([text["title"], *text["body"], text["checkbox_label"]])
        label = copy.PLATFORM_LABEL[platform]
        assert "Sleeper" not in joined and label in text["title"]   # written per platform
        unofficial = [b for b in text["body"] if "unofficial" in b]
        # MFL documents its import API: no unofficial-connection bullet. ESPN keeps it.
        assert unofficial == ([] if platform == "mfl" else
                              ["This uses an unofficial ESPN connection, so it could stop "
                               "working at any time."])
    assert copy.CONSENT_TEXTS[("mfl", MFL_V1, "en-US")]["body"] == [
        "Fleeced will add and drop players in your MFL leagues for you, using the MFL sign-in "
        "you connected.",
        "Moves are final on MFL. Fleeced can't undo them, and a player you drop can be picked "
        "up by another team.",
        "Your OK lasts 7 days. You'll still confirm every move. Turn it off any time in "
        "Settings › Leagues › Stop roster moves."]
    assert copy.CONSENT_TEXTS[("espn", ESPN_V2, "en-US")]["checkbox_label"] == (
        "I authorize Fleeced to add and drop players and place waiver claims in my ESPN "
        "leagues for the next 7 days.")
    assert copy.WITHDRAWAL_NOTICES[("mfl", MFL_V2)] == (
        "Roster moves in MFL are off. Fleeced won't add or drop players or place waiver claims "
        "there until you agree again. Moves already made stay in MFL.")
    assert copy.PLATFORM_SLOTS_DRAFT["espn"]["finality"] == "Final on ESPN. Fleeced can't undo it."
    assert "${" not in json.dumps(copy.PLATFORM_SLOTS_DRAFT)


def _draft_strings():
    """Every DRAFT string, less any that a final text shares word for word
    (the window bullet, "Make the move", "Bid: {bid}")."""
    out = set()
    for platform, version in DRAFTS:
        text = copy.CONSENT_TEXTS[(platform, version, "en-US")]
        out |= {text["title"], *text["body"], text["checkbox_label"],
                copy.WITHDRAWAL_NOTICES[(platform, version)]}
    for slots in copy.PLATFORM_SLOTS_DRAFT.values():
        out |= set(slots.values())
    final = set()
    for (platform, version, _), text in copy.CONSENT_TEXTS.items():
        if version not in copy.DRAFT_CONSENT_VERSIONS:
            final |= {text["title"], *text["body"], text["checkbox_label"], text["this_move"],
                      text["button_label"]}
    final |= set(copy._SLEEPER_SLOTS_FINAL.values())
    assert len(out - final) >= 20                              # not vacuous
    return out - final


def _strings(obj):
    """Every string value in a decoded JSON body, recursively."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def test_draft_texts_are_never_served(h, monkeypatch):
    """Nothing DRAFT reaches a client: not the consent GET or DELETE for MFL /
    ESPN, not the capability on an MFL / ESPN league, and not even when
    CURRENT_CONSENT_VERSION points at a draft by mistake."""
    from backend.tests.test_fa_move_route import MFL_LEAGUE, add_league
    served = set()
    for platform in ("mfl", "espn", "sleeper"):
        served |= set(_strings(_get(h, platform).get_json()))
        served |= set(_strings(_delete(h, platform).get_json()))
    for platform, lid in (("mfl", MFL_LEAGUE), ("espn", "61205")):
        add_league(h.engine, lid, platform)
        served |= set(_strings(server._fa_move_capability(h.sess, lid, None)))
    for platform, version in DRAFTS:
        monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, platform, version)
        assert copy.consent_block(platform) is None
        assert copy.withdrawal_notice(platform) == "Roster moves are off."
        assert not copy.has_consent_text(platform, version, "en-US")
        served |= set(_strings(_get(h, platform).get_json()))
        served |= set(_strings(_delete(h, platform).get_json()))
    assert "Let Fleeced make roster moves in Sleeper?" in served   # the probe sees real text
    assert not served & _draft_strings(), served & _draft_strings()
    # The neutral notice served for a platform without final text is R15.2.6's
    # own first sentence.
    assert WITHDRAWAL_NOTICE.startswith(copy.withdrawal_notice("mfl"))


def test_a_draft_version_is_never_accepted_as_consent(h):
    r = h.post(consent={"copy_version": MFL_V1, "locale": "en-US"})
    assert r.status_code == 409 and _err(r)["error"] == "consent_required"
    assert [c for c in h.consents() if c["kind"] == "grant"] == []


def test_grants_never_cross_platforms(h):
    """R28.27: an MFL (or ESPN) grant never covers Sleeper, and the reverse,
    even for the same account id and an identical version string."""
    for platform in ("mfl", "espn"):
        db_module.record_platform_write_grant(
            user_id=USER, platform=platform, platform_user_id=SLEEPER_UID, copy_version=V1,
            locale="en-US", consented_at=h.now, client_platform=None, app_version=None,
            trigger_attempt_id=None)
    assert _active(h, h.now) is None                          # no Sleeper grant
    r = h.post(consent=_ABSENT)
    assert r.status_code == 409 and _err(r)["error"] == "consent_required"
    sleeper = _grant(h)
    for platform in ("mfl", "espn"):
        got = db_module.active_platform_write_grant(USER, platform, SLEEPER_UID, V1, h.now)
        assert got is not None and got["platform"] == platform
        assert got["consent_id"] != sleeper["consent_id"]
    db_module.withdraw_platform_write_grants(USER, "sleeper", "settings", h.now)
    for platform in ("mfl", "espn"):                          # untouched by Sleeper's withdrawal
        assert db_module.active_platform_write_grant(USER, platform, SLEEPER_UID, V1, h.now)
    assert db_module.active_platform_write_grant(USER, "mfl", SLEEPER_UID, MFL_V1, h.now) is None

