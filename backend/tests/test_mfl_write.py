"""Unit tests for backend/mfl_write.py — the "Send in MFL" adapter.

Pure/offline: every HTTP call goes through an injected `_opener`; nothing here
touches the network (the live import surface is unverified by design — see the
TODO(live-verify) markers in the module and the operator checklist in
docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md).
"""
import io
import urllib.error
import urllib.parse

import pytest

from backend import mfl_write as mw


# ---------------------------------------------------------------------------
# Injected-opener helpers
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(body: str, seen: list):
    def op(req, timeout=None):
        seen.append(req)
        return _Resp(body)
    return op


def _http_error_opener(code: int, body: bytes = b""):
    def op(req, timeout=None):
        raise urllib.error.HTTPError("url", code, "err", None, io.BytesIO(body))
    return op


def _req(**over):
    base = dict(league_id="62846", offered_to="0005",
                will_give_up=["13130"], will_receive=["14085"])
    base.update(over)
    return mw.ProposeTradeRequest(**base)


# ---------------------------------------------------------------------------
# Asset-id construction
# ---------------------------------------------------------------------------

def test_encode_current_year_pick_zero_based_padded():
    # MFL docs: "DP_02_05 … 3rd round, 6th pick" — zero-based, two-digit.
    assert mw.encode_current_year_pick(2, 5) == "DP_02_05"
    assert mw.encode_current_year_pick(0, 0) == "DP_00_00"
    with pytest.raises(mw.MflWriteError):
        mw.encode_current_year_pick(-1, 0)


def test_encode_future_pick_franchise_padding():
    # MFL docs: "FP_0005_2018_2" — 4-digit original-owner franchise, year, round.
    assert mw.encode_future_pick("5", 2027, 1) == "FP_0005_2027_1"
    assert mw.encode_future_pick("0012", 2028, 3) == "FP_0012_2028_3"
    with pytest.raises(mw.MflWriteError):
        mw.encode_future_pick("not-a-team", 2027, 1)
    with pytest.raises(mw.MflWriteError):
        mw.encode_future_pick("0005", 2027, 0)   # rounds are 1-based


def test_asset_id_validation():
    assert mw.is_valid_asset_id("13130")            # player
    assert mw.is_valid_asset_id("DP_02_05")         # current-year pick
    assert mw.is_valid_asset_id("FP_0005_2027_1")   # future pick
    assert not mw.is_valid_asset_id("BB_10.50")     # blind bid — not built
    assert not mw.is_valid_asset_id("FP_5_2027_1")  # unpadded franchise
    assert not mw.is_valid_asset_id("")
    # pick-only discriminator (route's give_pick_assets/receive_pick_assets)
    assert mw.is_pick_asset_id("DP_02_05") and mw.is_pick_asset_id("FP_0005_2027_1")
    assert not mw.is_pick_asset_id("13130")


def test_normalize_franchise_id():
    assert mw.normalize_franchise_id("5") == "0005"
    assert mw.normalize_franchise_id("0005") == "0005"
    assert mw.normalize_franchise_id("f0012") == "0012"
    with pytest.raises(mw.MflWriteError):
        mw.normalize_franchise_id("team five")


# ---------------------------------------------------------------------------
# build_import_params — the exact wire params
# ---------------------------------------------------------------------------

def test_build_params_happy_path_players_and_both_pick_types():
    req = _req(will_give_up=["13130", "DP_02_05"],
               will_receive=["14085", "FP_0012_2027_1"],
               comments="from FTF", expires=1_800_000_000)
    p = mw.build_import_params(req)
    assert p["TYPE"] == "tradeProposal"
    assert p["L"] == "62846"
    assert p["OFFEREDTO"] == "0005"
    assert p["WILL_GIVE_UP"] == "13130,DP_02_05"
    assert p["WILL_RECEIVE"] == "14085,FP_0012_2027_1"
    assert p["EXPIRES"] == "1800000000"
    assert p["COMMENTS"] == "from FTF"
    assert p["JSON"] == "1"


def test_build_params_default_expires_is_seven_days_out():
    p = mw.build_import_params(_req(), now=1_000_000)
    assert p["EXPIRES"] == str(1_000_000 + mw.DEFAULT_EXPIRES_SECONDS)


def test_build_params_normalizes_bare_franchise_id():
    assert mw.build_import_params(_req(offered_to="5"))["OFFEREDTO"] == "0005"


def test_build_params_refuses_bad_input():
    with pytest.raises(mw.MflWriteError) as e:
        mw.build_import_params(_req(league_id="not-numeric"))
    assert e.value.kind == "input"
    with pytest.raises(mw.MflWriteError):
        mw.build_import_params(_req(will_give_up=[], will_receive=[]))
    with pytest.raises(mw.MflWriteError):
        mw.build_import_params(_req(will_give_up=["BB_10.50"]))  # unsupported asset


def test_import_url_uses_league_host():
    url = mw.import_url("www76.myfantasyleague.com", 2026,
                        {"TYPE": "tradeProposal", "L": "62846"})
    assert url.startswith("https://www76.myfantasyleague.com/2026/import?")
    with pytest.raises(mw.MflWriteError):
        mw.import_url("evil.example.com", 2026, {})


# ---------------------------------------------------------------------------
# Response parsing — both documented conventions, refuse ambiguity
# ---------------------------------------------------------------------------

def test_parse_response_xml_ok():
    assert mw._parse_import_response(
        '<?xml version="1.0"?><status>OK</status>')["status"] == "OK"


def test_parse_response_json_ok():
    assert mw._parse_import_response('{"status": "OK"}')["status"] == "OK"


def test_parse_response_xml_error_raises():
    with pytest.raises(mw.MflWriteError) as e:
        mw._parse_import_response("<error>Invalid franchise</error>")
    assert not isinstance(e.value, mw.MflWriteAuthError)
    assert "Invalid franchise" in (e.value.detail or "")


def test_parse_response_auth_flavored_error_raises_auth():
    with pytest.raises(mw.MflWriteAuthError):
        mw._parse_import_response("<error>You must be logged in</error>")
    with pytest.raises(mw.MflWriteAuthError):
        mw._parse_import_response('{"error": "bad cookie"}')


def test_parse_response_ambiguous_body_never_reports_success():
    for body in ("", "<html>surprise</html>", '{"status": "PENDING?"}'):
        with pytest.raises(mw.MflWriteError):
            mw._parse_import_response(body)


# ---------------------------------------------------------------------------
# propose_trade — full request issue through an injected opener
# ---------------------------------------------------------------------------

def test_propose_trade_happy_path_request_shape():
    seen: list = []
    out = mw.propose_trade("MFL_USER_ID=abc123", "www76.myfantasyleague.com",
                           2026, _req(), _opener=_opener("<status>OK</status>", seen))
    assert out["status"] == "OK"
    assert len(seen) == 1
    r = seen[0]
    # league host, not the api. host — the wwwNN gotcha applies to writes too
    assert r.full_url.startswith("https://www76.myfantasyleague.com/2026/import?")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.full_url).query))
    assert q["TYPE"] == "tradeProposal" and q["L"] == "62846"
    assert q["OFFEREDTO"] == "0005"
    assert q["WILL_GIVE_UP"] == "13130" and q["WILL_RECEIVE"] == "14085"
    # cookie + identifying UA ride as headers, never in the URL
    assert r.get_header("Cookie") == "MFL_USER_ID=abc123"
    assert r.get_header("User-agent")
    assert "MFL_USER_ID" not in r.full_url


def test_propose_trade_no_cookie_is_auth_error():
    with pytest.raises(mw.MflWriteAuthError):
        mw.propose_trade("", "www76.myfantasyleague.com", 2026, _req(),
                         _opener=_opener("<status>OK</status>", []))


def test_propose_trade_http_401_403_map_to_auth():
    for code in (401, 403):
        with pytest.raises(mw.MflWriteAuthError):
            mw.propose_trade("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026,
                             _req(), _opener=_http_error_opener(code))


def test_propose_trade_429_is_network_kind():
    with pytest.raises(mw.MflWriteError) as e:
        mw.propose_trade("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026,
                         _req(), _opener=_http_error_opener(429))
    assert e.value.kind == "network"


def test_propose_trade_transport_failure_is_network_kind():
    def op(req, timeout=None):
        raise urllib.error.URLError("no route to host")
    with pytest.raises(mw.MflWriteError) as e:
        mw.propose_trade("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026,
                         _req(), _opener=op)
    assert e.value.kind == "network"


# ---------------------------------------------------------------------------
# respond_trade (tradeResponse) — stub-level coverage
# ---------------------------------------------------------------------------

def test_respond_trade_request_shape():
    seen: list = []
    out = mw.respond_trade("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026,
                           "62846", "42", "revoke",
                           _opener=_opener('{"status":"OK"}', seen))
    assert out["status"] == "OK"
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(seen[0].full_url).query))
    assert q["TYPE"] == "tradeResponse" and q["TRADE_ID"] == "42"
    assert q["RESPONSE"] == "revoke"


def test_respond_trade_validates_input():
    for bad in ({"response": "counter"}, {"trade_id": ""}, {"league_id": "abc"}):
        kw = dict(league_id="62846", trade_id="42", response="reject")
        kw.update(bad)
        with pytest.raises(mw.MflWriteError):
            mw.respond_trade("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026,
                             kw["league_id"], kw["trade_id"], kw["response"],
                             _opener=_opener('{"status":"OK"}', []))
