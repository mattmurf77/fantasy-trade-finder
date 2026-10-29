"""C10: readable ESPN/MFL trade-send failures, and an outcome-unknown code so a
timeout never turns into a double send.

head-eng's pre-launch triage, C10. Covered here:

  * A provider rejection's raw body (HTML or JSON) goes to a WARNING log line,
    masked and truncated, and never into the response: `detail` == `message`
    == plain copy, and the codes stay `espn_write_failed` /
    `mfl_write_failed` (502), so the client branches don't change.
  * A write that may have reached the provider with no definitive answer (a
    read timeout or reset after the send, a 5xx, an unreadable 2xx) is 502
    `espn_outcome_unknown` / `mfl_outcome_unknown` with "check before sending
    again" copy. A failure before the send (DNS, connect refused) keeps the
    ordinary failure. The rules live in backend/write_outcome.py.
  * POST /api/trades/respond-mfl shares the MFL adapter and gets the same
    treatment, with its own "this response … nothing changed" copy.
  * Team overhaul: an outcome-unknown core result is an `outcome_unknown`
    attempt (reservation held), with the copy in `error.message`; a rejection
    is `send_failed` with the plain copy.

No network: the real adapters run with an injected `_opener`, or the
adapter is a mock. Copy: marketing's final lines, addendum 10 items 8a–8h
(`docs/plans/org-bringup/leads/marketing-lead-copy.md` §6, 2026-10-28), pinned
word for word below with straight apostrophes.
"""
import errno
import http.client
import io
import json
import logging
import socket
import urllib.error

import pytest

import backend.espn_write as espn_write
import backend.mfl_write as mfl_write
import backend.server as server
from backend import overhaul_store as store
from backend.tests import test_espn_propose_route as espn_t
from backend.tests import test_i2_espn_ownership as i2_espn
from backend.tests import test_i2_mfl_ownership as i2_mfl
from backend.tests import test_mfl_propose_route as mfl_t
from backend.tests import test_mfl_trade_lifecycle as mfl_life_t
from backend.tests import test_overhaul_api as ovh_t

# Addendum 10, word for word, straight apostrophes.
ESPN_REJECTED = "ESPN didn't accept this trade, so nothing was sent. You can still propose it on ESPN."  # 8a
MFL_REJECTED = "MFL didn't accept this trade, so nothing was sent. You can still propose it on MFL."     # 8b
ESPN_NOT_SENT = "Couldn't reach ESPN right now, so nothing was sent. Try again in a moment."            # 8c
MFL_NOT_SENT = "Couldn't reach MFL right now, so nothing was sent. Try again in a moment."              # 8d
ESPN_UNKNOWN = ("Couldn't confirm whether this trade reached ESPN. "
                "Check your league's pending trades on ESPN before you send it again.")              # 8e
MFL_UNKNOWN = ("Couldn't confirm whether this trade reached MFL. "
               "Check your league's pending trades on MFL before you send it again.")                # 8f
RESPOND_REJECTED = "MFL didn't accept your response, so nothing changed. Check the trade on MFL."      # 8g
RESPOND_UNKNOWN = ("Couldn't confirm whether your response reached MFL. "
                   "Check the trade on MFL before you respond again.")                               # 8h
ESPN_AUTH_EXPIRED = "Your ESPN sign-in has expired. Connect ESPN again to send."                       # optional line

MARKER = "C10RAWPROVIDERMARKER"
SWID_ECHO = "{AAAA1111-0000-0000-0000-000000000001}"
COOKIE_SECRET = "AEBs2SecretValue%2Bc10"
RAW_HTML = ("<!DOCTYPE html>\n<html><head><title>Error</title></head><body>\n"
            f"<h1>{MARKER}</h1><p>member {SWID_ECHO} espn_s2={COOKIE_SECRET}</p>\n"
            + "<p>" + "stack frame at handler " * 40 + "</p></body></html>")
RAW_JSON = json.dumps({
    "messages": [f"{MARKER} TRAN_INVALID_TRADE_TEAM_COUNT"],
    "details": [{"type": "TRAN_INVALID_TRADE_TEAM_COUNT",
                 "metaData": {"memberId": SWID_ECHO},
                 "message": "pad " * 150}]})

REAL_ESPN_PROPOSE = espn_write.propose_trade
REAL_MFL_PROPOSE = mfl_write.propose_trade


# ---------------------------------------------------------------------------
# Injected openers (urllib's shapes, no network)
# ---------------------------------------------------------------------------

class _Resp:
    status = 200

    def __init__(self, body=b"", read_exc=None):
        self._body, self._exc = body, read_exc

    def read(self):
        if self._exc is not None:
            raise self._exc
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _raises(make_exc):
    def op(request, timeout=None):
        raise make_exc()
    return op


def _http_error(code, body=""):
    def op(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, code, "err", {},
                                     io.BytesIO(body.encode("utf-8")))
    return op


def _returns(body=b"", read_exc=None):
    def op(request, timeout=None):
        return _Resp(body, read_exc)
    return op


# The two sides of the line backend/write_outcome.py draws.
NOT_SENT = {
    "dns": _raises(lambda: urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))),
    "refused": _raises(lambda: urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))),
    "no_route": _raises(lambda: urllib.error.URLError(OSError(errno.EHOSTUNREACH, "No route to host"))),
    "bad_url": _raises(lambda: urllib.error.URLError("unknown url type: x")),
}
AFTER_SEND = {
    "read_timeout": _raises(lambda: TimeoutError("The read operation timed out")),
    "socket_timeout": _raises(lambda: socket.timeout("timed out")),
    "reset": _raises(lambda: ConnectionResetError(54, "Connection reset by peer")),
    "remote_disconnected": _raises(
        lambda: http.client.RemoteDisconnected("Remote end closed connection without response")),
    "bad_status_line": _raises(lambda: http.client.BadStatusLine("")),
    "body_read_timeout": _returns(read_exc=TimeoutError("The read operation timed out")),
    "incomplete_read": _returns(read_exc=http.client.IncompleteRead(b"{\"id\":")),
    # Conservative: urllib can't say whether a wrapped timeout/reset was the
    # connect or the request write.
    "urlerror_timeout": _raises(lambda: urllib.error.URLError(TimeoutError("timed out"))),
    "urlerror_reset": _raises(lambda: urllib.error.URLError(ConnectionResetError(54, "reset"))),
    "http_500": _http_error(500, "<html>oops</html>"),
    "http_502": _http_error(502, "<html>Bad Gateway</html>"),
    "http_503": _http_error(503, ""),
    "http_504": _http_error(504, "<html>Gateway Timeout</html>"),
}


# ---------------------------------------------------------------------------
# Adapters: kind classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(NOT_SENT))
def test_espn_adapter_failure_before_send_is_network(case):
    with pytest.raises(espn_write.EspnWriteError) as ei:
        REAL_ESPN_PROPOSE("s2", "{S}", espn_t_req(), _opener=NOT_SENT[case])
    assert ei.value.kind == "network"


@pytest.mark.parametrize("case", sorted(AFTER_SEND))
def test_espn_adapter_failure_after_send_is_outcome_unknown(case):
    with pytest.raises(espn_write.EspnWriteError) as ei:
        REAL_ESPN_PROPOSE("s2", "{S}", espn_t_req(), _opener=AFTER_SEND[case])
    assert ei.value.kind == "outcome_unknown"


@pytest.mark.parametrize("opener", [_returns(b"<html>not json</html>"), _returns(b"\xff\xfe\x00")],
                         ids=["non_json_2xx", "non_utf8_2xx"])
def test_espn_adapter_unreadable_2xx_is_outcome_unknown(opener):
    with pytest.raises(espn_write.EspnWriteError) as ei:
        REAL_ESPN_PROPOSE("s2", "{S}", espn_t_req(), _opener=opener)
    assert ei.value.kind == "outcome_unknown"


@pytest.mark.parametrize("code", [400, 409, 422])
def test_espn_adapter_4xx_is_a_rejection(code):
    with pytest.raises(espn_write.EspnWriteError) as ei:
        REAL_ESPN_PROPOSE("s2", "{S}", espn_t_req(), _opener=_http_error(code, RAW_JSON))
    assert ei.value.kind == "error"
    assert MARKER in ei.value.detail          # the adapter keeps it, for the log


@pytest.mark.parametrize("case", sorted(NOT_SENT))
def test_mfl_adapter_failure_before_send_is_network(case):
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026, mfl_req(),
                         _opener=NOT_SENT[case])
    assert ei.value.kind == "network"


@pytest.mark.parametrize("case", sorted(AFTER_SEND))
def test_mfl_adapter_failure_after_send_is_outcome_unknown(case):
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026, mfl_req(),
                         _opener=AFTER_SEND[case])
    assert ei.value.kind == "outcome_unknown"


@pytest.mark.parametrize("body", [b"", b"<html>surprise</html>", b'{"status": "PENDING?"}'],
                         ids=["empty", "html", "json_unknown_status"])
def test_mfl_adapter_unreadable_200_is_outcome_unknown(body):
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", "www76.myfantasyleague.com", 2026, mfl_req(),
                         _opener=_returns(body))
    assert ei.value.kind == "outcome_unknown"


def test_mfl_adapter_error_body_and_4xx_and_429_stay_ordinary():
    host = "www76.myfantasyleague.com"
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", host, 2026, mfl_req(),
                         _opener=_returns(f"<error>{MARKER} Invalid asset</error>".encode()))
    assert ei.value.kind == "error"
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", host, 2026, mfl_req(), _opener=_http_error(400, RAW_HTML))
    assert ei.value.kind == "error"
    with pytest.raises(mfl_write.MflWriteError) as ei:
        REAL_MFL_PROPOSE("MFL_USER_ID=x", host, 2026, mfl_req(), _opener=_http_error(429))
    assert ei.value.kind == "network"         # a throttle is a definite "not processed"


def espn_t_req():
    return espn_write.EspnTradeProposalRequest(
        league_id=espn_t.LEAGUE, season=2026, my_team_id=espn_t.MY_TEAM,
        their_team_id=espn_t.THEIR_TEAM, member_swid=espn_t.MY_SWID,
        give_espn_player_ids=[espn_t.ESPN_GIVE], receive_espn_player_ids=[espn_t.ESPN_RECV])


def mfl_req():
    return mfl_write.ProposeTradeRequest(league_id=mfl_t.LEAGUE, offered_to=mfl_t.THEIR_FID,
                                         will_give_up=[mfl_t.MFL_GIVE],
                                         will_receive=[mfl_t.MFL_RECV])


# ---------------------------------------------------------------------------
# Routes: POST /api/trades/propose-espn and /propose-mfl
# ---------------------------------------------------------------------------

@pytest.fixture()
def espn_client(monkeypatch):
    yield from espn_t.client.__wrapped__(monkeypatch)


@pytest.fixture()
def mfl_client(monkeypatch):
    yield from mfl_t.client.__wrapped__(monkeypatch)


def _post_espn(client, monkeypatch, opener):
    c, token = client
    monkeypatch.setattr(espn_write, "propose_trade",
                        lambda s2, swid, req: REAL_ESPN_PROPOSE(s2, swid, req, _opener=opener))
    return c.post("/api/trades/propose-espn", headers=espn_t._h(token), data=espn_t._propose_body())


def _post_mfl(client, monkeypatch, opener):
    c, token = client
    monkeypatch.setattr(mfl_write, "propose_trade",
                        lambda cookie, host, year, req: REAL_MFL_PROPOSE(cookie, host, year, req,
                                                                        _opener=opener))
    return c.post("/api/trades/propose-mfl", headers=mfl_t._h(token), data=mfl_t._propose_body())


def _warning_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "trade_finder" and r.levelno == logging.WARNING]


def _assert_logged_masked_and_truncated(caplog, prefix):
    lines = [m for m in _warning_lines(caplog) if m.startswith(prefix)]
    assert len(lines) == 1, _warning_lines(caplog)
    line = lines[0]
    assert MARKER in line                      # the raw body reached the log...
    assert "…[+" in line                       # ...truncated...
    assert SWID_ECHO not in line and SWID_ECHO.strip("{}") not in line   # ...masked
    assert COOKIE_SECRET not in line
    assert "\n" not in line
    return line


@pytest.mark.parametrize("code,body", [(400, RAW_HTML), (409, RAW_JSON)], ids=["html", "json"])
def test_espn_rejection_raw_body_goes_to_log_only(espn_client, monkeypatch, caplog, code, body):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r = _post_espn(espn_client, monkeypatch, _http_error(code, body))
    assert r.status_code == 502
    payload = r.get_json()
    assert payload == {"error": "espn_write_failed", "kind": "error",
                       "detail": ESPN_REJECTED, "message": ESPN_REJECTED}
    assert MARKER not in r.get_data(as_text=True)
    _assert_logged_masked_and_truncated(caplog, "espn propose write-failed [error]")


@pytest.mark.parametrize("raw", [RAW_HTML, f"<error>{MARKER} Trades are disabled {'x' * 400}</error>"],
                         ids=["http_400_html", "error_body_200"])
def test_mfl_rejection_raw_body_goes_to_log_only(mfl_client, monkeypatch, caplog, raw):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    opener = _http_error(400, raw) if raw is RAW_HTML else _returns(raw.encode())
    r = _post_mfl(mfl_client, monkeypatch, opener)
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_write_failed", "kind": "error",
                            "detail": MFL_REJECTED, "message": MFL_REJECTED}
    assert MARKER not in r.get_data(as_text=True)
    line = [m for m in _warning_lines(caplog) if m.startswith("mfl propose write-failed")][0]
    assert MARKER in line and len(line) < 500


@pytest.mark.parametrize("case", ["read_timeout", "reset", "http_504", "incomplete_read"])
def test_espn_timeout_after_send_is_outcome_unknown(espn_client, monkeypatch, case):
    r = _post_espn(espn_client, monkeypatch, AFTER_SEND[case])
    assert r.status_code == 502
    assert r.get_json() == {"error": "espn_outcome_unknown", "kind": "outcome_unknown",
                            "detail": ESPN_UNKNOWN, "message": ESPN_UNKNOWN}


@pytest.mark.parametrize("case", ["dns", "refused"])
def test_espn_connect_failure_before_send_is_an_ordinary_failure(espn_client, monkeypatch, case):
    r = _post_espn(espn_client, monkeypatch, NOT_SENT[case])
    assert r.status_code == 502
    assert r.get_json() == {"error": "espn_write_failed", "kind": "network",
                            "detail": ESPN_NOT_SENT, "message": ESPN_NOT_SENT}


@pytest.mark.parametrize("case", ["read_timeout", "remote_disconnected", "http_502"])
def test_mfl_timeout_after_send_is_outcome_unknown(mfl_client, monkeypatch, case):
    r = _post_mfl(mfl_client, monkeypatch, AFTER_SEND[case])
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_outcome_unknown", "kind": "outcome_unknown",
                            "detail": MFL_UNKNOWN, "message": MFL_UNKNOWN}


@pytest.mark.parametrize("case", ["dns", "refused"])
def test_mfl_connect_failure_before_send_is_an_ordinary_failure(mfl_client, monkeypatch, case):
    r = _post_mfl(mfl_client, monkeypatch, NOT_SENT[case])
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_write_failed", "kind": "network",
                            "detail": MFL_NOT_SENT, "message": MFL_NOT_SENT}


def test_mfl_429_throttle_gets_the_not_sent_line(mfl_client, monkeypatch):
    """MFL's 429 carries kind `network` (a throttle is processed by nothing),
    so it reads 8d, "try again in a moment", not 8b."""
    r = _post_mfl(mfl_client, monkeypatch, _http_error(429, "<html>slow down</html>"))
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_write_failed", "kind": "network",
                            "detail": MFL_NOT_SENT, "message": MFL_NOT_SENT}


def test_outcome_unknown_fires_no_trade_sent(espn_client, monkeypatch):
    """Unknown is not a confirmed send: no `trade_sent`, no proposal record."""
    r = _post_espn(espn_client, monkeypatch, AFTER_SEND["read_timeout"])
    assert r.get_json()["error"] == "espn_outcome_unknown"
    assert espn_t._trade_sent_rows() == []


def test_espn_auth_rejection_body_is_not_returned(espn_client, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r = _post_espn(espn_client, monkeypatch, _http_error(401, RAW_HTML))
    assert r.status_code == 409 and r.get_json()["error"] == "espn_auth_expired"
    assert MARKER not in r.get_data(as_text=True)
    assert r.get_json()["detail"] == r.get_json()["message"] == ESPN_AUTH_EXPIRED
    _assert_logged_masked_and_truncated(caplog, "espn propose auth-rejected")


def test_mfl_auth_rejection_body_is_not_returned(mfl_client, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r = _post_mfl(mfl_client, monkeypatch, _http_error(403, RAW_HTML))
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_auth_expired"
    assert MARKER not in r.get_data(as_text=True)
    assert r.get_json()["detail"] == r.get_json()["message"]
    _assert_logged_masked_and_truncated(caplog, "mfl propose auth-rejected")


# ---------------------------------------------------------------------------
# The copy: pinned word for word, swept for banned words, chosen by kind
# ---------------------------------------------------------------------------

# Every C10 copy constant in backend/server.py, with the outcome it speaks for.
C10_CONSTANTS = {
    "_SEND_REJECTED_COPY": "rejected",
    "_SEND_NOT_SENT_COPY": "not_sent",
    "_SEND_OUTCOME_UNKNOWN_COPY": "unknown",
    "_RESPOND_REJECTED_COPY": "rejected",
    "_RESPOND_OUTCOME_UNKNOWN_COPY": "unknown",
    "_ESPN_WRITE_AUTH_EXPIRED_COPY": "auth",
}


@pytest.mark.parametrize("const,platform,expected", [
    ("_SEND_REJECTED_COPY", "ESPN", ESPN_REJECTED),
    ("_SEND_REJECTED_COPY", "MFL", MFL_REJECTED),
    ("_SEND_NOT_SENT_COPY", "ESPN", ESPN_NOT_SENT),
    ("_SEND_NOT_SENT_COPY", "MFL", MFL_NOT_SENT),
    ("_SEND_OUTCOME_UNKNOWN_COPY", "ESPN", ESPN_UNKNOWN),
    ("_SEND_OUTCOME_UNKNOWN_COPY", "MFL", MFL_UNKNOWN),
    ("_RESPOND_REJECTED_COPY", "MFL", RESPOND_REJECTED),
    ("_RESPOND_OUTCOME_UNKNOWN_COPY", "MFL", RESPOND_UNKNOWN),
    ("_ESPN_WRITE_AUTH_EXPIRED_COPY", "ESPN", ESPN_AUTH_EXPIRED),
], ids=["8a", "8b", "8c", "8d", "8e", "8f", "8g", "8h", "auth"])
def test_copy_is_addendum_10_word_for_word(const, platform, expected):
    assert getattr(server, const).format(platform=platform) == expected
    assert "\u2019" not in expected and "\u2018" not in expected      # straight apostrophes only


@pytest.mark.parametrize("const", sorted(C10_CONSTANTS))
def test_copy_never_says_failed_error_or_nothing_sent_when_unknown(const):
    text = getattr(server, const)
    low = text.lower()
    assert "fail" not in low and "error" not in low, text
    assert "\u2019" not in text and "\u2018" not in text, text
    if C10_CONSTANTS[const] == "unknown":
        assert "nothing was sent" not in low and "nothing changed" not in low, text


def test_every_c10_copy_constant_is_swept():
    """A new `_SEND_*_COPY` / `_RESPOND_*_COPY` constant joins the sweep."""
    found = {n for n in vars(server) if n.endswith("_COPY")
             and (n.startswith("_SEND_") or n.startswith("_RESPOND_"))}
    assert found <= set(C10_CONSTANTS), found - set(C10_CONSTANTS)


@pytest.mark.parametrize("prefix,platform,rejected,not_sent,unknown", [
    ("espn", "ESPN", ESPN_REJECTED, ESPN_NOT_SENT, ESPN_UNKNOWN),
    ("mfl", "MFL", MFL_REJECTED, MFL_NOT_SENT, MFL_UNKNOWN),
], ids=["espn", "mfl"])
def test_line_is_chosen_by_kind_and_both_not_sent_kinds_keep_write_failed(
        prefix, platform, rejected, not_sent, unknown):
    for kind, line in (("network", not_sent), ("error", rejected), ("input", rejected)):
        payload, status = server._send_write_failed(prefix, platform, kind)
        assert status == 502
        assert payload == {"error": f"{prefix}_write_failed", "kind": kind,
                           "detail": line, "message": line}
    payload, status = server._send_write_failed(prefix, platform, "outcome_unknown")
    assert (status, payload["error"], payload["detail"]) == (502, f"{prefix}_outcome_unknown", unknown)


# ---------------------------------------------------------------------------
# POST /api/trades/respond-mfl: the same adapter, the same rule
# ---------------------------------------------------------------------------

RAW_MFL_ERROR = (f"<error>{MARKER} Trades are disabled for member {SWID_ECHO} "
                 f"MFL_USER_ID={COOKIE_SECRET} {'x ' * 250}</error>")
REAL_MFL_RESPOND = mfl_write.respond_trade


@pytest.fixture()
def respond_client(monkeypatch):
    yield from mfl_life_t.client.__wrapped__(monkeypatch)


def _post_respond(client, monkeypatch, opener):
    c, token = client
    monkeypatch.setattr(
        mfl_write, "respond_trade",
        lambda cookie, host, year, league_id, trade_id, response, comments=None:
            REAL_MFL_RESPOND(cookie, host, year, league_id, trade_id, response,
                             comments=comments, _opener=opener))
    return c.post("/api/trades/respond-mfl", headers=mfl_life_t._h(token),
                  data=mfl_life_t._respond_body())


@pytest.mark.parametrize("opener", [_http_error(400, RAW_HTML), _returns(RAW_MFL_ERROR.encode())],
                         ids=["http_400_html", "error_body_200"])
def test_respond_mfl_rejection_raw_body_goes_to_log_only(respond_client, monkeypatch, caplog, opener):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r = _post_respond(respond_client, monkeypatch, opener)
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_write_failed", "kind": "error",
                            "detail": RESPOND_REJECTED, "message": RESPOND_REJECTED}
    assert MARKER not in r.get_data(as_text=True)
    _assert_logged_masked_and_truncated(caplog, "mfl respond write-failed [error]")


@pytest.mark.parametrize("case", ["read_timeout", "reset", "http_504"])
def test_respond_mfl_timeout_after_send_is_outcome_unknown(respond_client, monkeypatch, case):
    r = _post_respond(respond_client, monkeypatch, AFTER_SEND[case])
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_outcome_unknown", "kind": "outcome_unknown",
                            "detail": RESPOND_UNKNOWN, "message": RESPOND_UNKNOWN}


def test_respond_mfl_refused_connection_is_an_ordinary_failure(respond_client, monkeypatch):
    """Addendum 10 has no not-sent line for a response, so 8g covers it too."""
    r = _post_respond(respond_client, monkeypatch, NOT_SENT["refused"])
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_write_failed", "kind": "network",
                            "detail": RESPOND_REJECTED, "message": RESPOND_REJECTED}


def test_respond_mfl_auth_rejection_body_is_not_returned(respond_client, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r = _post_respond(respond_client, monkeypatch, _http_error(401, RAW_HTML))
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_auth_expired"
    assert MARKER not in r.get_data(as_text=True)
    assert r.get_json()["detail"] == r.get_json()["message"]
    _assert_logged_masked_and_truncated(caplog, "mfl respond auth-rejected")


# ---------------------------------------------------------------------------
# Team overhaul: send_core → the REAL propose cores
# ---------------------------------------------------------------------------

@pytest.fixture()
def espn_overhaul(monkeypatch):
    yield from i2_espn.overhaul.__wrapped__(monkeypatch)


@pytest.fixture()
def mfl_overhaul(monkeypatch):
    yield from i2_mfl.overhaul.__wrapped__(monkeypatch)


def _send_batch(c, world, key):
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": key})
    assert r.status_code == 200, r.get_json()
    give_of = {p["package_id"]: p["give_ids"][0] for p in rm["packages"]}
    by_give = {}
    for a in r.get_json()["attempts"]:
        by_give.setdefault(give_of[a["package_id"]], []).append(a)
    return oid, r, by_give


def test_overhaul_espn_outcome_unknown_is_live_and_readable(espn_overhaul):
    """A's tie times out after the send → `outcome_unknown` with the copy and
    the reservation held. B is rejected with a raw body → `send_failed` with
    the plain copy. C and D go through."""
    c, world, live, fake, espn_id = espn_overhaul
    tid_of = {ovh_t.USER: 1, **{i2_espn._syn(t): t for t in i2_espn.TEAM_OF.values()}}
    live["raw"] = {"id": int(i2_espn.LEAGUE), "scoringPeriodId": 0, "settings": {"size": 6},
                   "members": [], "teams": [
                       {"id": tid_of[owner], "name": f"Team {tid_of[owner]}",
                        "roster": {"entries": [{"lineupSlotId": 20, "playerPoolEntry": {
                            "player": {"id": espn_id[p], "fullName": p}}} for p in roster]}}
                       for owner, roster in world.rosters.items()]}
    give_name = {v: k for k, v in espn_id.items()}

    def provider(s2, swid, req):
        give = give_name[req.give_espn_player_ids[0]]
        opener = {"A": AFTER_SEND["read_timeout"], "B": _http_error(400, RAW_HTML)}.get(give)
        if opener is None:
            return {"transaction_id": f"tx-{give}", "status": "PENDING", "raw": {}}
        return REAL_ESPN_PROPOSE(s2, swid, req, _opener=opener)

    fake.side_effect = provider
    oid, r, by_give = _send_batch(c, world, "c10-espn")
    assert MARKER not in r.get_data(as_text=True)
    assert [a["state"] for a in by_give["A"]] == ["outcome_unknown", "outcome_unknown"]
    assert [a["state_source"] for a in by_give["A"]] == ["server", "server"]
    for a in by_give["A"]:
        assert a["error"] == {"code": "espn_outcome_unknown", "message": ESPN_UNKNOWN}
    assert [a["state"] for a in by_give["B"]] == ["send_failed"]
    assert by_give["B"][0]["error"] == {"code": "espn_write_failed", "message": ESPN_REJECTED}
    assert [a["state"] for a in by_give["C"] + by_give["D"]] == ["proposed", "proposed"]
    held = {row["asset_id"] for row in store.active_reservations(i2_espn.LEAGUE, ovh_t.USER)}
    assert "A" in held and "B" not in held       # unknown holds, a rejection releases
    # The overhaul view surfaces the same readable error.
    view = c.get(f"/api/overhauls/{oid}", headers=ovh_t._h()).get_json()
    unknown = [a for a in view["attempts"] if a["state"] == "outcome_unknown"]
    assert len(unknown) == 2 and all(a["error"]["message"] == ESPN_UNKNOWN for a in unknown)


def test_overhaul_mfl_outcome_unknown_is_live_and_readable(mfl_overhaul, monkeypatch):
    c, world, live, fake, mfl_id = mfl_overhaul
    fid_of = {ovh_t.USER: "0001", **{i2_mfl._syn(f): f for f in i2_mfl.CP.values()}}
    live["rosters"] = {"rosters": {"franchise": [
        {"id": fid_of[owner], "player": [{"id": mfl_id[p]} for p in roster]}
        for owner, roster in world.rosters.items()]}}
    fake.side_effect = lambda cookie, host, year, req: REAL_MFL_PROPOSE(
        cookie, host, year, req, _opener=AFTER_SEND["reset"])
    oid, r, by_give = _send_batch(c, world, "c10-mfl")
    attempts = r.get_json()["attempts"]
    assert [a["state"] for a in attempts] == ["outcome_unknown"] * 5
    assert {json.dumps(a["error"], sort_keys=True) for a in attempts} == {
        json.dumps({"code": "mfl_outcome_unknown", "message": MFL_UNKNOWN}, sort_keys=True)}
    held = {row["asset_id"] for row in store.active_reservations(i2_mfl.LEAGUE, ovh_t.USER)}
    assert {"A", "B", "C", "D"} <= held
