"""D1 free-agent moves: the `move` capability on GET /api/league/free-agents
(contract §1, scope §B1/§B6/§B7, AC-42).

`_fa_move_capability` is exercised directly per platform, flag state and
connection state, and once through the real route. Harness and fixture:
test_fa_move_route.py (in-memory DB, stubbed public reads, no network).
"""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
import backend.sleeper_write as sleeper_write
from backend import fa_move_copy as copy
from backend.ranking_service import Player
from backend.tests.test_fa_move_route import (  # noqa: F401  (h is a fixture)
    ADD, DROP, KEEP, LEAGUE, MFL_LEAGUE, SLEEPER_UID, THEIRS, TOKEN, USER, V1, V2,
    _jwt, _rosters, _seed_move, add_league, h,
)

CONTRACT_COPY_KEYS = {
    "header_add", "header_claim", "cta_add", "cta_add_drop", "cta_claim", "cta_claim_drop",
    "cta_claim_no_bid", "cta_claim_drop_no_bid", "league_line", "finality", "waiver_line",
    "waiver_line_no_drop", "bid_line", "window_line", "turn_off", "do_in_platform",
    "open_platform", "handoff_footer", "connect_line", "verify_line", "other_account_line",
    "not_sent_line", "unknown_title", "unknown_body", "unavailable_line", "still_sending",
}


def cap(h, league_id=LEAGUE, live=None):
    return server._fa_move_capability(h.sess, league_id,
                                      _rosters() if live is None else live)


# ---------------------------------------------------------------------------
# mode per platform and flag
# ---------------------------------------------------------------------------

def test_sleeper_flag_off_is_handoff(h):
    h.flags.discard("sleeper.send_add_drop")
    move, rows = cap(h)
    assert move["mode"] == "handoff" and move["league_platform"] == "sleeper"
    assert move["claims"] is False


def test_sleeper_flag_on_but_shapes_not_captured_is_handoff(h, monkeypatch):
    monkeypatch.setattr(sleeper_write, "FA_MOVE_SHAPES_CAPTURED", False)
    move, _ = cap(h)
    assert move["mode"] == "handoff"


def test_sleeper_flag_on_and_captured_is_submit(h):
    move, rows = cap(h)
    assert move == {**move, "mode": "submit", "claims": False, "league_platform": "sleeper",
                    "connect": "ok", "consent_until": None}
    assert rows == {}


@pytest.mark.parametrize("platform", ["mfl", "espn", "fleaflicker"])
def test_linked_platforms_are_unsupported(h, platform):
    add_league(h.engine, MFL_LEAGUE, platform)
    move, rows = cap(h, MFL_LEAGUE)
    assert move["mode"] == "unsupported" and move["claims"] is False
    assert move["league_platform"] == (platform if platform != "fleaflicker" else None)
    assert move["copy"] == {} and rows == {}


def test_local_league_is_unsupported(h):
    move, _ = cap(h, "league_demo")
    assert move["mode"] == "unsupported" and move["league_platform"] is None


def test_ftf_flags_env_beats_the_file(h, monkeypatch):
    """B2: the durable prod flip is FTF_FLAGS, which beats config/features.json."""
    monkeypatch.setattr(server, "is_enabled", feature_flags.is_enabled)
    real_load = feature_flags._load_from_json
    try:
        assert json.loads(open(feature_flags._CONFIG_PATH).read())["sleeper.send_add_drop"] is False
        monkeypatch.setenv("FTF_FLAGS", json.dumps({"sleeper.send_add_drop": True}))
        feature_flags.reload()
        assert cap(h)[0]["mode"] == "submit"
        monkeypatch.setattr(feature_flags, "_load_from_json",
                            lambda path: {"sleeper.send_add_drop": True})
        monkeypatch.setenv("FTF_FLAGS", json.dumps({"sleeper.send_add_drop": False}))
        feature_flags.reload()
        assert cap(h)[0]["mode"] == "handoff"
    finally:
        monkeypatch.delenv("FTF_FLAGS", raising=False)
        monkeypatch.setattr(feature_flags, "_load_from_json", real_load)
        feature_flags.reload()


# ---------------------------------------------------------------------------
# claims (D5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("version,shape,live,expected", [
    (V1, False, True, False), (V1, True, True, False), (V2, False, True, False),
    (V2, True, False, False), (V2, True, True, True),
])
def test_claims_only_under_d5(h, monkeypatch, version, shape, live, expected):
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", version)
    monkeypatch.setattr(sleeper_write, "FA_CLAIM_SHAPE_CAPTURED", shape)
    if not live:
        h.flags.discard("sleeper.send_add_drop")
    assert cap(h)[0]["claims"] is expected


# ---------------------------------------------------------------------------
# connect (contract §6; ux-lead F3)
# ---------------------------------------------------------------------------

def test_connect_not_linked(h):
    db_module.delete_sleeper_credential(USER, withdrawn_via="disconnect")
    assert cap(h)[0]["connect"] == "not_linked"


def test_connect_other_account(h):
    live = [r for r in _rosters() if r["owner_id"] != USER]
    assert cap(h, live=live)[0]["connect"] == "other_account"


def test_connect_unknown_rosters_never_reads_other_account(h):
    assert server._fa_move_capability(h.sess, LEAGUE, None)[0]["connect"] == "ok"


def test_connect_expired(h):
    db_module.upsert_sleeper_credential(USER, SLEEPER_UID,
                                        sleeper_write.encrypt_token(_jwt(-60)),
                                        (h.now - timedelta(minutes=1)).isoformat())
    assert cap(h)[0]["connect"] == "expired"


def test_connect_unverified(h):
    h.sess["verified"] = False
    assert cap(h)[0]["connect"] == "unverified"


def test_connect_co_owner_is_ok(h):
    live = [{"owner_id": "someone", "co_owners": [USER], "roster_id": 3, "players": [DROP]}]
    assert cap(h, live=live)[0]["connect"] == "ok"


# ---------------------------------------------------------------------------
# consent_until
# ---------------------------------------------------------------------------

def _grant(h, at=None, version=V1, account=SLEEPER_UID):
    return db_module.record_platform_write_grant(
        user_id=USER, platform="sleeper", platform_user_id=account, copy_version=version,
        locale="en-US", consented_at=at or h.now, client_platform=None, app_version=None,
        trigger_attempt_id=None)


def test_consent_until_is_the_open_grants_expiry(h):
    grant = _grant(h)
    assert cap(h)[0]["consent_until"] == grant["expires_at"]
    assert grant["expires_at"] == (h.now + timedelta(days=7)).isoformat()


def test_consent_until_null_after_lapse_bump_or_other_account(h, monkeypatch):
    _grant(h, at=h.now - timedelta(days=7))
    assert cap(h)[0]["consent_until"] is None                     # lapsed
    _grant(h)
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V2)
    assert cap(h)[0]["consent_until"] is None                     # version bump
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V1)
    db_module.upsert_sleeper_credential(USER, "999", sleeper_write.encrypt_token(_jwt()), None)
    assert cap(h)[0]["consent_until"] is None                     # another account


# ---------------------------------------------------------------------------
# copy (contract §7): approved slots always, drafts only in submit
# ---------------------------------------------------------------------------

def test_copy_keys_are_the_contracts():
    assert copy.MOVE_COPY_KEYS == CONTRACT_COPY_KEYS
    assert set(copy._SLEEPER_SLOTS_FINAL) | set(copy._SLEEPER_SLOTS_DRAFT) == CONTRACT_COPY_KEYS
    assert not set(copy._SLEEPER_SLOTS_FINAL) & set(copy._SLEEPER_SLOTS_DRAFT)


def test_handoff_serves_no_draft_copy(h):
    h.flags.discard("sleeper.send_add_drop")
    served = cap(h)[0]["copy"]
    assert served == copy._SLEEPER_SLOTS_FINAL
    assert not set(served) & set(copy._SLEEPER_SLOTS_DRAFT)


def test_submit_serves_every_slot(h):
    assert set(cap(h)[0]["copy"]) == CONTRACT_COPY_KEYS


def test_approved_slots_verbatim():
    final = copy._SLEEPER_SLOTS_FINAL
    assert final["connect_line"] == "Connect your Sleeper sign-in to make moves from here."   # G2
    assert final["finality"] == "Final on Sleeper. Fleeced can't undo it."                    # G7
    assert final["do_in_platform"] == "Do it in Sleeper instead"                              # G20
    assert final["unknown_title"] == "Check before resending"                                 # 8i
    # G8, R15.1 :766, in the contract §7 forms.
    assert final["waiver_line"] == ("This places a waiver claim for {add} (dropping {drop} "
                                    "if it clears). Sleeper processes it on its waiver schedule.")
    assert final["waiver_line_no_drop"] == ("This places a waiver claim for {add}. "
                                            "Sleeper processes it on its waiver schedule.")
    assert final["bid_line"] == "Bid: {bid}"
    assert final["cta_claim_no_bid"] == "Claim {add}"
    assert final["cta_claim_drop_no_bid"] == "Claim {add}, drop {drop}"
    # A no-drop / no-bid form never names the missing half.
    for key in ("waiver_line_no_drop", "cta_claim_no_bid"):
        assert "{drop}" not in final[key]
    for key in ("waiver_line", "waiver_line_no_drop", "cta_claim_no_bid", "cta_claim_drop_no_bid"):
        assert "{bid}" not in final[key]


def test_templates_never_write_their_own_dollar_sign():
    """Contract §7: the client fills `{bid}` WITH its "$" ("$7")."""
    for key, text in {**copy._SLEEPER_SLOTS_FINAL, **copy._SLEEPER_SLOTS_DRAFT}.items():
        assert "${" not in text, key
    assert copy._SLEEPER_SLOTS_FINAL["bid_line"] == "Bid: {bid}"
    assert copy._SLEEPER_SLOTS_FINAL["cta_claim"] == "Claim {add} for {bid}"


# marketing-lead addendum 17 §B (2026-11-01), word for word. "Keep" rows are
# pinned by test_approved_slots_verbatim and the route tests.
FINAL_SLOTS_CHANGED = {
    "window_line": "Roster moves: on until {date}",
    "verify_line": "Verify your Sleeper sign-in to make moves from here.",
    "not_sent_line": "Couldn't reach Sleeper right now, so nothing was sent.",
    "unknown_body": ("Couldn't confirm whether this move reached Sleeper. Check your roster and "
                     "claims in Sleeper before you make it again."),
    "unavailable_line": ("Moves from Fleeced aren't available right now. You can still make this "
                         "move in Sleeper."),
}
FINAL_SLOTS_KEPT = {
    "header_add": "Add {name}", "header_claim": "Claim {name}", "cta_add": "Add {add}",
    "cta_add_drop": "Add {add}, drop {drop}", "cta_claim": "Claim {add} for {bid}",
    "cta_claim_drop": "Claim {add} for {bid}, drop {drop}", "league_line": "In {league}",
    "turn_off": "Turn off", "open_platform": "Open in Sleeper to claim",
    "handoff_footer": "You'll finish this move in Sleeper.",
    "other_account_line": ("The Sleeper account you connected isn't in {league}. Connect the "
                           "one that owns your team."),
    "still_sending": "Still sending to Sleeper…",
}
UNCONFIRMED = ("Couldn't confirm whether this move reached Sleeper. Check your roster and claims "
               "in Sleeper before you make it again.")
FINAL_MESSAGES = {   # (key, fmt) → the Sleeper text
    ("feature_disabled", ()): ("Moves from Fleeced aren't available right now, so nothing was "
                               "sent. You can still make this move in Sleeper."),
    ("unconfigured", ()): ("Moves from Fleeced aren't available right now, so nothing was sent. "
                           "You can still make this move in Sleeper."),
    ("bad_request", ()): "Nothing was sent. Close this and start the move again.",
    ("verification_required", ()): ("Nothing was sent. Verify your Sleeper sign-in to make "
                                    "moves from here."),
    ("expired", ()): ("Your Sleeper sign-in has expired, so nothing was sent. Sign in again to "
                      "make moves from here."),
    ("consent_required", ()): "Nothing was sent. Agree to roster moves to make this move.",
    ("roster_full_drop_required", ()): ("Your roster is full, so nothing was sent. Pick a player "
                                        "to drop."),
    ("asset_not_owned", (("drop", "B"),)): ("B is no longer on your roster, so nothing was sent. "
                                            "Pick another player to drop."),
    ("player_unavailable", (("add", "A"),)): "A is no longer a free agent, so nothing was sent.",
    ("waiver_bid_over_budget", (("remaining", 80),)): (
        "Your bid is more than the $80 you have left, so nothing was sent. Lower it to make "
        "the claim."),
    ("move_kind_changed", (("add", "A"),)): ("A's waiver status changed, so nothing was sent. "
                                             "The button now shows the right move."),
    ("waiver_claim_unsupported", (("add", "A"),)): (
        "A is on waivers, and waiver claims can't be made from here right now, so nothing was "
        "sent. Claim in Sleeper instead."),
    ("write_failed", ()): ("Sleeper didn't accept this move, so nothing changed. You can still "
                           "try it in Sleeper."),
    ("outcome_unknown", ()): UNCONFIRMED,
    ("internal_error", ()): UNCONFIRMED,
    ("move_in_progress", (("add", "A"),)): ("A recent move for A isn't confirmed yet. Check your "
                                            "roster in Sleeper before you make it again."),
    ("move_in_progress_pending_claim", (("add", "A"),)): (
        "A claim for A is already pending in Sleeper. Check your claims there before you make "
        "another."),
}


def test_marketing_final_part_b_verbatim():
    final = copy._SLEEPER_SLOTS_FINAL
    for key, text in {**FINAL_SLOTS_CHANGED, **FINAL_SLOTS_KEPT}.items():
        assert final[key] == text, key
    assert copy._SLEEPER_SLOTS_DRAFT == {}                   # nothing left awaiting words
    for (key, fmt), text in FINAL_MESSAGES.items():
        assert copy.message(key, "sleeper", **dict(fmt)) == text, key
    assert copy.row_line("unconfirmed", "sleeper") == (
        "A recent move for this player isn't confirmed. Check Sleeper before you make it again.")
    assert copy.row_line("pending_claim", "sleeper") == (
        "A claim for this player is already pending in Sleeper.")
    # One "$" in what the user sees: the server fills {remaining} with it,
    # the client fills {bid} with its own.
    assert copy.message("waiver_bid_over_budget", "sleeper", remaining=80).count("$") == 1


def test_handoff_now_serves_every_final_slot(h):
    h.flags.discard("sleeper.send_add_drop")
    assert set(cap(h)[0]["copy"]) == CONTRACT_COPY_KEYS


def test_no_we_our_or_try_again_where_the_outcome_is_unknown_or_in_progress():
    """State 12 and the double-move block: never "we" / "our", never "try
    again" (G16, the 8e frame)."""
    import re
    texts = [copy._SLEEPER_SLOTS_FINAL["unknown_title"], copy._SLEEPER_SLOTS_FINAL["unknown_body"],
             copy.UNKNOWN_TITLE, copy.row_line("unconfirmed", "sleeper"),
             copy.row_line("pending_claim", "sleeper")]
    texts += [copy.message(k, "sleeper", add="A") for k in (
        "outcome_unknown", "internal_error", "move_in_progress", "move_in_progress_pending_claim")]
    for text in texts:
        assert not re.search(r"\b(we|our|us)\b|try again", text, re.IGNORECASE), text


def test_never_the_false_sleeper_line():
    """Scope state 1: the neutral fallback is never "Sleeper doesn't allow
    apps to submit claims"; nor may the server say so."""
    every = " ".join(list(copy._SLEEPER_SLOTS_FINAL.values())
                     + list(copy._SLEEPER_SLOTS_DRAFT.values()))
    assert "doesn't allow" not in every and "allow apps" not in every


# ---------------------------------------------------------------------------
# Per-row override: the double-move block (§B6(b))
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("result,status,kind,reason", [
    (None, None, "add", "unconfirmed"),
    ("unknown", None, "add", "unconfirmed"),
    ("accepted", "pending", "claim", "pending_claim"),
])
def test_blocked_row_is_handed_off_with_a_line(h, result, status, kind, reason):
    _seed_move(h, result=result, status=status, minutes_ago=2, kind=kind)
    _, rows = cap(h)
    assert rows == {ADD: {"move_mode": "handoff",
                          "move_line": copy.row_line(reason, "sleeper")}}
    if reason == "pending_claim":
        assert "already pending" in rows[ADD]["move_line"]
    else:
        assert "isn't confirmed" in rows[ADD]["move_line"]


def test_block_lifts_from_the_row_at_15_minutes(h):
    _seed_move(h, result="unknown", minutes_ago=15)
    assert cap(h)[1] == {}


# ---------------------------------------------------------------------------
# Through the route
# ---------------------------------------------------------------------------

POOL = [Player(id=pid, name=pid, position="RB", team="FA", age=25)
        for pid in (ADD, "7777", DROP, KEEP, THEIRS)]


class _FakeService:
    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[])


def fa_get(h, monkeypatch, league_id=LEAGUE):
    from backend.trade_service import League, LeagueMember
    h.sess.update(
        league=League(league_id=LEAGUE, name="Dummy League", platform="sleeper",
                      members=[LeagueMember(user_id="other", username="them",
                                            roster=[THEIRS], elo_ratings={})]),
        players=list(POOL), user_roster=[DROP, KEEP], service=_FakeService(),
        trade_svc=object())
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (POOL, {p.id: 1500.0 for p in POOL}))
    monkeypatch.setattr(server, "_verified_read_denial", lambda s: None)
    monkeypatch.setattr(server, "_sleeper_get", lambda url, timeout=15: _rosters())
    return h.client.get(f"/api/league/free-agents?league_id={league_id}",
                        headers={"X-Session-Token": TOKEN})


def test_route_carries_the_capability_and_row_fields(h, monkeypatch):
    _seed_move(h, result="unknown", minutes_ago=1, add="7777")
    r = fa_get(h, monkeypatch)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["move"]["mode"] == "submit" and body["move"]["connect"] == "ok"
    rows = {row["player_id"]: row for row in body["free_agents"]}
    assert set(rows) == {ADD, "7777"}
    assert all("move_kind" in row and row["move_kind"] is None for row in rows.values())
    assert "move_mode" not in rows[ADD]
    assert rows["7777"]["move_mode"] == "handoff" and rows["7777"]["move_line"]
    # The #179 claim-sheet context is untouched.
    assert body["roster_capacity"]["open_slots"] == 3


def test_route_flag_off_says_handoff(h, monkeypatch):
    h.flags.discard("sleeper.send_add_drop")
    body = fa_get(h, monkeypatch).get_json()
    assert body["move"]["mode"] == "handoff"
    assert not set(body["move"]["copy"]) & set(copy._SLEEPER_SLOTS_DRAFT)


def test_route_omits_move_when_the_capability_fails(h, monkeypatch):
    """An absent `move` is legacy behaviour (contract §1): the FA read never
    fails because of the capability."""
    def _boom(*a):
        raise RuntimeError("db down")
    monkeypatch.setattr(server, "_fa_move_capability", _boom)
    r = fa_get(h, monkeypatch)
    assert r.status_code == 200
    body = r.get_json()
    assert "move" not in body
    assert all("move_kind" not in row for row in body["free_agents"])
