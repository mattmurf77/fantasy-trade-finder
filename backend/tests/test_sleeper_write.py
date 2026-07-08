"""Unit tests for backend/sleeper_write.py — the Sleeper "Send in Sleeper"
adapter. Pure/offline: the HTTP call is injected via `_opener`, so nothing here
touches the network or Sleeper.

Covers:
  1. propose_trade payload encoding — the k_adds/v_adds/k_drops/v_drops roster
     pairing, verified against the 2026-07-02 live capture (runbook §C2).
  2. Input guards (numeric league_id, self-roster, empty trade, bad pick).
  3. Token crypto round-trip (Fernet) + fail-closed when the key is missing.
  4. JWT introspection (claims / exp / is_expired).
  5. HTTP result + error mapping (success, 401→auth, GraphQL errors array).
"""

import io
import json
import time
import urllib.error

import pytest

import backend.sleeper_write as sw
from backend.sleeper_write import (
    ProposeTradeRequest,
    SleeperAuthError,
    SleeperWriteError,
    build_propose_trade_body,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _triples(body):
    """Map player_id -> (v_add_roster, v_drop_roster) from a built body, so we
    can compare the *set* of adds/drops regardless of list ordering."""
    v = body["variables"]
    out = {}
    for pid, va in zip(v["k_adds"], v["v_adds"]):
        out.setdefault(pid, [None, None])[0] = va
    for pid, vd in zip(v["k_drops"], v["v_drops"]):
        out.setdefault(pid, [None, None])[1] = vd
    return {k: tuple(val) for k, val in out.items()}


class _FakeResp:
    def __init__(self, text):
        self._b = text.encode("utf-8")
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _opener_returning(payload_obj):
    def _opener(request, timeout=None):
        return _FakeResp(json.dumps(payload_obj))
    return _opener


def test_request_carries_browser_headers_not_urllib():
    """Cloudflare 1010 bans Python's default urllib signature. The Sleeper call
    must present a real browser User-Agent + origin/referer so the server-side
    request gets through — regression guard for the 1010 block."""
    captured = {}
    token = _fake_jwt({"user_id": "u1"})

    def _capturing_opener(request, timeout=None):
        captured["ua"] = request.get_header("User-agent")
        captured["origin"] = request.get_header("Origin")
        captured["referer"] = request.get_header("Referer")
        captured["auth"] = request.get_header("Authorization")
        return _FakeResp(json.dumps({"data": {"propose_trade": {"transaction_id": "t1", "status": "proposed"}}}))

    sw.propose_trade(
        token,
        ProposeTradeRequest(league_id="999", my_roster_id=1, their_roster_id=2,
                            give_player_ids=["10"], receive_player_ids=["20"]),
        _opener=_capturing_opener,
    )
    assert captured["ua"] and "urllib" not in captured["ua"].lower()
    assert "Mozilla" in captured["ua"]           # real browser signature
    assert captured["origin"] == "https://sleeper.com"
    assert captured["referer"] == "https://sleeper.com/"
    # Sleeper wants the RAW token — NOT `Bearer <token>` (verified vs live API).
    assert captured["auth"] == token
    assert not captured["auth"].lower().startswith("bearer ")


def _opener_http_error(code):
    def _opener(request, timeout=None):
        raise urllib.error.HTTPError(sw.SLEEPER_GRAPHQL_URL, code, "err", {}, io.BytesIO(b"{}"))
    return _opener


def _fake_jwt(claims):
    import base64
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


# ---------------------------------------------------------------------------
# 1. payload encoding
# ---------------------------------------------------------------------------

def test_encoding_one_for_one():
    body = build_propose_trade_body(ProposeTradeRequest(
        league_id="1312140920132497408", my_roster_id=1, their_roster_id=2,
        give_player_ids=["100"], receive_player_ids=["200"],
    ))
    assert body["operationName"] == "propose_trade"
    # received player is added to MY roster (1), dropped from THEIRS (2);
    # given player is the mirror.
    assert _triples(body) == {"200": (1, 2), "100": (2, 1)}


def test_encoding_matches_live_capture():
    # From runbook §C2 (roster 1 = proposer/consenter). Players received by
    # roster 1 vs given to roster 2, reconstructed from the captured v_adds.
    receive = ["4866", "6797", "12506", "12514"]   # v_adds == 1 in capture
    give = ["4892", "6149", "11588", "11599"]       # v_adds == 2 in capture
    body = build_propose_trade_body(ProposeTradeRequest(
        league_id="1312140920132497408", my_roster_id=1, their_roster_id=2,
        give_player_ids=give, receive_player_ids=receive,
    ))
    expected = {p: (1, 2) for p in receive}
    expected.update({p: (2, 1) for p in give})
    assert _triples(body) == expected


def test_query_inlines_league_and_empty_picks():
    body = build_propose_trade_body(ProposeTradeRequest(
        league_id="999", my_roster_id=1, their_roster_id=2,
        give_player_ids=["1"], receive_player_ids=["2"],
    ))
    q = body["query"]
    assert 'propose_trade(league_id: "999"' in q
    assert "draft_picks: []" in q
    assert "waiver_budget: []" in q


def test_picks_encoded_and_validated():
    body = build_propose_trade_body(ProposeTradeRequest(
        league_id="999", my_roster_id=1, their_roster_id=2,
        give_player_ids=[], receive_player_ids=["2"],
        draft_picks=["11,2026,1,1,2"],
    ))
    assert '["11,2026,1,1,2"]' in body["query"]

    with pytest.raises(SleeperWriteError):
        build_propose_trade_body(ProposeTradeRequest(
            league_id="999", my_roster_id=1, their_roster_id=2,
            give_player_ids=[], receive_player_ids=["2"],
            draft_picks=["not,a,valid,pick"],
        ))


# ---------------------------------------------------------------------------
# 2. input guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(league_id="not-numeric", my_roster_id=1, their_roster_id=2,
         give_player_ids=["1"], receive_player_ids=["2"]),
    dict(league_id="1", my_roster_id=1, their_roster_id=1,   # self-trade
         give_player_ids=["1"], receive_player_ids=["2"]),
    dict(league_id="1", my_roster_id=1, their_roster_id=2,   # empty trade
         give_player_ids=[], receive_player_ids=[]),
])
def test_build_guards_reject_bad_input(kwargs):
    with pytest.raises(SleeperWriteError):
        build_propose_trade_body(ProposeTradeRequest(**kwargs))


# ---------------------------------------------------------------------------
# 3. token crypto
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    assert sw.token_encryption_available() is True
    ct = sw.encrypt_token("secret-jwt-value")
    assert ct != "secret-jwt-value"          # actually encrypted
    assert sw.decrypt_token(ct) == "secret-jwt-value"


def test_crypto_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("SLEEPER_TOKEN_KEY", raising=False)
    assert sw.token_encryption_available() is False
    with pytest.raises(SleeperWriteError) as ei:
        sw.encrypt_token("x")
    assert ei.value.kind == "config"


# ---------------------------------------------------------------------------
# 4. JWT introspection
# ---------------------------------------------------------------------------

def test_token_claims_and_expiry():
    exp = int(time.time()) + 3600
    jwt = _fake_jwt({"user_id": "313560442465169408", "exp": exp})
    assert sw.token_sleeper_user_id(jwt) == "313560442465169408"
    assert sw.token_expiry(jwt) == exp
    assert sw.is_expired(jwt) is False


def test_is_expired_true_for_past_token():
    jwt = _fake_jwt({"user_id": "1", "exp": int(time.time()) - 10})
    assert sw.is_expired(jwt) is True


def test_token_claims_garbage_is_empty():
    assert sw.token_claims("not-a-jwt") == {}
    assert sw.token_expiry("not-a-jwt") is None


# ---------------------------------------------------------------------------
# 5. HTTP result + error mapping
# ---------------------------------------------------------------------------

_REQ = ProposeTradeRequest(
    league_id="1312140920132497408", my_roster_id=1, their_roster_id=2,
    give_player_ids=["100"], receive_player_ids=["200"],
)


def test_propose_success_parses_transaction():
    opener = _opener_returning({"data": {"propose_trade": {
        "transaction_id": "1378625554508423168", "status": "proposed"}}})
    out = sw.propose_trade("tok", _REQ, _opener=opener)
    assert out["transaction_id"] == "1378625554508423168"
    assert out["status"] == "proposed"


def test_propose_401_raises_auth():
    with pytest.raises(SleeperAuthError):
        sw.propose_trade("tok", _REQ, _opener=_opener_http_error(401))


def test_propose_graphql_auth_error_raises_auth():
    opener = _opener_returning({"errors": [{"message": "invalid auth token"}]})
    with pytest.raises(SleeperAuthError):
        sw.propose_trade("tok", _REQ, _opener=opener)


def test_propose_graphql_generic_error_raises_write():
    opener = _opener_returning({"errors": [{"message": "roster is locked"}]})
    with pytest.raises(SleeperWriteError) as ei:
        sw.propose_trade("tok", _REQ, _opener=opener)
    assert not isinstance(ei.value, SleeperAuthError)


def test_propose_empty_token_raises_auth():
    with pytest.raises(SleeperAuthError):
        sw.propose_trade("", _REQ)
