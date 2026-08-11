"""Unit tests for backend/espn_write.py — the "Send in ESPN" adapter.

Pure/offline: the HTTP call is injected via `_opener`, so nothing here touches
the network or ESPN. These assert PAYLOAD CONSTRUCTION against the 2026-08-11
football live capture (docs/plans/espn-send-live-capture-2026-08-11.md) and
error mapping only — they deliberately CANNOT prove a server-side POST is
authorized by cookies alone (the flag-graduation unknown).

Covers:
  1. TRADE_PROPOSAL envelope per the capture (constants, teamId = proposer,
     epoch-ms expiration ≈ +48h, comment omitted when empty).
  2. items[] — direction (give = me→them, receive = them→me) + ALL seven
     captured fields (fromLineupSlotId from the roster map with bench-20
     fallback, toLineupSlotId -1, isKeeper, overallPickNumber).
  3. Input guards (numeric league_id, self-team, empty trade).
  4. Sleeper→ESPN id resolution (invert crosswalk + fail-loud on a miss).
  5. League-read helpers (current_scoring_period, extract_lineup_slots).
  6. Write headers (x-fantasy-*, origin/referer) + cookie normalization.
  7. HTTP result + error mapping (success, 401/403→auth, network→network).
  8. Cancel body (executionType CANCEL, empty items, relatedTransactionId).
"""

import io
import json
import urllib.error

import pytest

import backend.espn_write as ew
from backend.espn_write import (
    EspnTradeProposalRequest,
    EspnWriteAuthError,
    EspnWriteError,
    build_trade_proposal_body,
    current_scoring_period,
    extract_lineup_slots,
    invert_espn_crosswalk,
    resolve_espn_player_ids,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, text, status=200):
        self._b = text.encode("utf-8")
        self.status = status
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _opener_returning(payload_obj, status=200):
    def _opener(request, timeout=None):
        return _FakeResp(json.dumps(payload_obj), status=status)
    return _opener


def _opener_http_error(code):
    def _opener(request, timeout=None):
        raise urllib.error.HTTPError(
            "https://lm-api-writes.fantasy.espn.com/x", code, "err", {}, io.BytesIO(b"{}"))
    return _opener


def _items_by_pid(body):
    return {it["playerId"]: (it["fromTeamId"], it["toTeamId"]) for it in body["items"]}


_REQ = EspnTradeProposalRequest(
    league_id="123456", season=2026, my_team_id=5, their_team_id=12,
    member_swid="{ABC-123}", give_espn_player_ids=[4608810],
    receive_espn_player_ids=[4697815], scoring_period_id=0,
)

#: proposedDate from live capture #1 — the epoch-ms expiration math pins to it.
_NOW_MS = 1786476250306


# ---------------------------------------------------------------------------
# 1. envelope (capture-exact)
# ---------------------------------------------------------------------------

def test_envelope_shape_matches_capture():
    body = build_trade_proposal_body(_REQ, now_ms=_NOW_MS)
    assert body["type"] == "TRADE_PROPOSAL"
    assert body["executionType"] == "EXECUTE"
    assert body["teamId"] == 5                     # the PROPOSING team
    assert body["memberId"] == "{ABC-123}"         # braces preserved
    assert body["scoringPeriodId"] == 0            # offseason value, not a week
    assert body["isLeagueManager"] is False
    assert body["isActingAsTeamOwner"] is False
    assert body["bidAmount"] == 0
    assert body["rating"] == 0
    assert "comment" not in body                   # not observed in the capture


def test_expiration_is_epoch_ms_48h_default():
    # Capture: expirationDate − proposedDate = 172,799,897 ms ≈ 48h. The
    # scaffold's ISO ".000Z" string was WRONG — this pins the epoch-ms fix.
    body = build_trade_proposal_body(_REQ, now_ms=_NOW_MS)
    assert isinstance(body["expirationDate"], int)
    assert body["expirationDate"] == _NOW_MS + 48 * 3600 * 1000


def test_explicit_expiration_ms_passthrough():
    req = EspnTradeProposalRequest(
        league_id="1", season=2026, my_team_id=1, their_team_id=2,
        member_swid="{X}", give_espn_player_ids=[1], receive_espn_player_ids=[2],
        expiration_ms=1786649050203,
    )
    assert build_trade_proposal_body(req)["expirationDate"] == 1786649050203


def test_comment_included_only_when_set():
    req = EspnTradeProposalRequest(
        league_id="1", season=2026, my_team_id=1, their_team_id=2,
        member_swid="{X}", give_espn_player_ids=[1], receive_espn_player_ids=[2],
        comment="via FTF",
    )
    assert build_trade_proposal_body(req)["comment"] == "via FTF"


def test_swid_braces_added_when_bare():
    req = EspnTradeProposalRequest(
        league_id="1", season=2026, my_team_id=1, their_team_id=2,
        member_swid="ABC-123", give_espn_player_ids=[1], receive_espn_player_ids=[2],
    )
    assert build_trade_proposal_body(req)["memberId"] == "{ABC-123}"


# ---------------------------------------------------------------------------
# 2. items[] — direction + all seven captured fields
# ---------------------------------------------------------------------------

def test_item_direction_confirmed_by_capture():
    body = build_trade_proposal_body(_REQ)
    # give (4608810): from me(5) → them(12); receive (4697815): mirrored —
    # exactly the captured proposal's semantics (capture §3). Do not invert.
    assert _items_by_pid(body) == {4608810: (5, 12), 4697815: (12, 5)}


def test_item_carries_all_captured_fields():
    body = build_trade_proposal_body(_REQ)
    for it in body["items"]:
        assert it["type"] == "TRADE"
        assert it["toLineupSlotId"] == -1
        assert it["isKeeper"] is False
        assert it["overallPickNumber"] == 0
        # No roster map supplied → bench fallback (both captures showed 20).
        assert it["fromLineupSlotId"] == 20


def test_item_uses_real_lineup_slot_when_known():
    req = EspnTradeProposalRequest(
        league_id="1", season=2026, my_team_id=5, their_team_id=12,
        member_swid="{X}", give_espn_player_ids=[4608810],
        receive_espn_player_ids=[4697815],
        lineup_slots={4608810: 2, 4697815: 20},
    )
    by_pid = {it["playerId"]: it["fromLineupSlotId"]
              for it in build_trade_proposal_body(req)["items"]}
    assert by_pid == {4608810: 2, 4697815: 20}


def test_multi_player_direction():
    req = EspnTradeProposalRequest(
        league_id="1", season=2026, my_team_id=3, their_team_id=7,
        member_swid="{X}", give_espn_player_ids=[11, 12],
        receive_espn_player_ids=[21], scoring_period_id=0,
    )
    body = build_trade_proposal_body(req)
    assert _items_by_pid(body) == {11: (3, 7), 12: (3, 7), 21: (7, 3)}
    assert all(it["type"] == "TRADE" for it in body["items"])


# ---------------------------------------------------------------------------
# 3. input guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(league_id="not-numeric", season=2026, my_team_id=1, their_team_id=2,
         member_swid="{X}", give_espn_player_ids=[1], receive_espn_player_ids=[2]),
    dict(league_id="1", season=2026, my_team_id=1, their_team_id=1,   # self-team
         member_swid="{X}", give_espn_player_ids=[1], receive_espn_player_ids=[2]),
    dict(league_id="1", season=2026, my_team_id=1, their_team_id=2,   # empty
         member_swid="{X}", give_espn_player_ids=[], receive_espn_player_ids=[]),
])
def test_build_guards_reject_bad_input(kwargs):
    with pytest.raises(EspnWriteError):
        build_trade_proposal_body(EspnTradeProposalRequest(**kwargs))


# ---------------------------------------------------------------------------
# 4. Sleeper → ESPN id resolution (crosswalk inversion CONFIRMED 2026-08-11:
#    DP espn_id IS the write-API playerId — 4/4 live ids matched)
# ---------------------------------------------------------------------------

def test_invert_crosswalk_on_live_verified_ids():
    by_espn_id = {"4697815": "8136", "4608810": "12485",
                  "4431268": "12540", "4431545": "11577"}
    inv = invert_espn_crosswalk(by_espn_id)
    assert inv == {"8136": "4697815", "12485": "4608810",
                   "12540": "4431268", "11577": "4431545"}


def test_resolve_maps_all():
    sleeper_to_espn = {"8136": "4697815", "12485": "4608810"}
    assert resolve_espn_player_ids(["8136", "12485"], sleeper_to_espn) == \
        [4697815, 4608810]


def test_resolve_fails_loud_on_miss():
    with pytest.raises(EspnWriteError) as ei:
        resolve_espn_player_ids(["8136", "9999"], {"8136": "4697815"})
    assert "9999" in str(ei.value)


# ---------------------------------------------------------------------------
# 5. league-read helpers
# ---------------------------------------------------------------------------

def test_current_scoring_period_prefers_top_level():
    assert current_scoring_period({"scoringPeriodId": 3,
                                   "status": {"latestScoringPeriod": 2}}) == 3


def test_current_scoring_period_offseason_zero():
    # The captured league: scoringPeriodId 0 in the offseason — 0 is a real
    # value, never "missing".
    assert current_scoring_period({"scoringPeriodId": 0,
                                   "status": {"latestScoringPeriod": 0}}) == 0


def test_current_scoring_period_falls_back_to_status_then_zero():
    assert current_scoring_period({"status": {"latestScoringPeriod": 7}}) == 7
    assert current_scoring_period({}) == 0
    assert current_scoring_period({"scoringPeriodId": "junk"}) == 0
    assert current_scoring_period(None) == 0


def test_extract_lineup_slots():
    raw = {"teams": [
        {"roster": {"entries": [
            {"lineupSlotId": 2,
             "playerPoolEntry": {"player": {"id": 4608810}}},
            {"lineupSlotId": 20,
             "playerPoolEntry": {"player": {"id": 4697815}}},
            {"playerPoolEntry": {"player": {}}},          # malformed — skipped
        ]}},
        {"roster": {"entries": [
            {"lineupSlotId": 0,
             "playerPoolEntry": {"player": {"id": 4431268}}},
        ]}},
    ]}
    assert extract_lineup_slots(raw) == {4608810: 2, 4697815: 20, 4431268: 0}
    assert extract_lineup_slots({}) == {}
    assert extract_lineup_slots(None) == {}


# ---------------------------------------------------------------------------
# 6. headers + cookie normalization
# ---------------------------------------------------------------------------

def test_request_carries_fantasy_headers_and_cookies():
    captured = {}

    def _capturing_opener(request, timeout=None):
        for h in ("X-fantasy-platform", "X-fantasy-source", "Origin", "Referer", "Cookie"):
            captured[h] = request.get_header(h)
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResp(json.dumps({"id": "t1", "status": "PENDING"}))

    ew.propose_trade("s2value", "{SWID-1}", _REQ, _opener=_capturing_opener)
    assert captured["X-fantasy-platform"] == "espn-fantasy-web"
    assert captured["X-fantasy-source"] == "kona"
    assert captured["Origin"] == "https://fantasy.espn.com"
    assert captured["Referer"] == "https://fantasy.espn.com/"
    assert "espn_s2=" in captured["Cookie"]
    assert "SWID={SWID-1}" in captured["Cookie"]
    assert captured["url"] == (
        "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
        "segments/0/leagues/123456/transactions/")
    assert isinstance(captured["body"]["expirationDate"], int)   # epoch ms on the wire


def test_decoded_espn_s2_gets_reencoded_in_cookie():
    # A base64-ish (decoded) espn_s2 must be percent-encoded on the wire —
    # the 2026-08-09 field-failure lesson (espn_service.canonical_espn_s2).
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({"id": "t1"}))

    ew.propose_trade("AEB+cd/ef=", "{S}", _REQ, _opener=_capturing_opener)
    assert "%2B" in captured["cookie"] or "%2F" in captured["cookie"] \
        or "%3D" in captured["cookie"]


# ---------------------------------------------------------------------------
# 7. HTTP result + error mapping
# ---------------------------------------------------------------------------

def test_propose_success_parses_id_and_status():
    out = ew.propose_trade("s2", "{S}", _REQ,
                           _opener=_opener_returning({"id": "9988", "status": "PENDING"}))
    assert out["transaction_id"] == "9988"
    assert out["status"] == "PENDING"


@pytest.mark.parametrize("code", [401, 403])
def test_propose_401_403_raise_clean_auth_error(code):
    # The flag-graduation unknown (cookies-alone auth) MUST surface as a
    # structured EspnWriteAuthError, never a crash.
    with pytest.raises(EspnWriteAuthError):
        ew.propose_trade("s2", "{S}", _REQ, _opener=_opener_http_error(code))


def test_propose_500_raises_write_not_auth():
    with pytest.raises(EspnWriteError) as ei:
        ew.propose_trade("s2", "{S}", _REQ, _opener=_opener_http_error(500))
    assert not isinstance(ei.value, EspnWriteAuthError)


def test_missing_cookies_raises_auth():
    with pytest.raises(EspnWriteAuthError):
        ew.propose_trade("", "", _REQ)


def test_network_error_maps_to_network_kind():
    def _opener(request, timeout=None):
        raise urllib.error.URLError("boom")
    with pytest.raises(EspnWriteError) as ei:
        ew.propose_trade("s2", "{S}", _REQ, _opener=_opener)
    assert ei.value.kind == "network"


# ---------------------------------------------------------------------------
# 8. cancel (revoke) — capture confirms proposals are cancelable
# ---------------------------------------------------------------------------

def test_cancel_body_shape():
    body = ew.build_cancel_body(_REQ, related_transaction_id="777")
    assert body["executionType"] == "CANCEL"
    assert body["items"] == []
    assert body["relatedTransactionId"] == "777"
    assert body["type"] == "TRADE_PROPOSAL"
    assert body["teamId"] == 5
    assert body["bidAmount"] == 0 and body["rating"] == 0


def test_cancel_posts_same_endpoint():
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResp(json.dumps({"id": "777", "status": "CANCELED"}))

    ew.cancel_trade("s2", "{S}", _REQ, "777", _opener=_capturing_opener)
    assert captured["url"].endswith("/leagues/123456/transactions/")
