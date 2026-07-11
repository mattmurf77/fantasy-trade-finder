"""Account-auth P1 — verified sessions via Sleeper-JWT proof.

Covers (docs/plans/account-auth-plan-2026-07-11.md §2c/§2d/§3-P1):

  1. The oracle probe (`sleeper_write.verify_token_live`) — success /
     token-rejected / transport-failure classification, offline via _opener.
  2. POST /api/sleeper/link as the verification step — claim mismatch,
     dead token, inconclusive oracle, and the happy path that stamps
     sess["verified"] + persists users.verified_via='sleeper'.
  3. The write-gate matrix on a representative gated route
     (/api/ranking-method): grace allow+log, verified-controller deny,
     enforcement deny, verified allow, GET pass-through.
  4. First-verified-controller-wins across two live sessions.
  5. POST /api/account/reset-rankings (verified-only squatter remedy).
  6. /api/session/init's additive `verification` response field.

Same isolation pattern as test_sleeper_write_route.py: Flask test client,
in-memory SQLite, injected sessions, no network (oracle + Sleeper reads
mocked).
"""
import base64
import io
import json
import time
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.accounts as accounts
import backend.database as db_module
import backend.server as server
import backend.sleeper_write as sw
from backend.database import metadata

UID = "313560442465169408"          # session user AND token claim (must match)
OTHER_UID = "999999999999999999"    # a mismatching claim


def _fake_jwt(claims):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


def _token(user_id=UID, exp_offset=3600):
    return _fake_jwt({"user_id": user_id, "exp": int(time.time()) + exp_offset})


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# 1. verify_token_live — the oracle probe (pure, offline)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, obj):
        self._b = json.dumps(obj).encode("utf-8")
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_probe_success_on_200():
    captured = {}
    def opener(request, timeout=None):
        captured["auth"] = request.get_header("Authorization")
        captured["op"] = request.get_header("X-sleeper-graphql-op")
        return _FakeResp({"data": {"__typename": "RootQueryType"}})
    out = sw.verify_token_live("tok.abc.sig", _opener=opener)
    assert isinstance(out, dict)
    # raw token, no Bearer prefix — same auth surface as propose_trade
    assert captured["auth"] == "tok.abc.sig"
    assert captured["op"] == "ftf_token_probe"


def test_probe_forged_token_raises_auth_error():
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(
            sw.SLEEPER_GRAPHQL_URL, 401, "unauthorized", {},
            io.BytesIO(b'{"error":"Your token is invalid."}'))
    with pytest.raises(sw.SleeperAuthError):
        sw.verify_token_live("forged", _opener=opener)


def test_probe_transport_failure_is_not_auth_error():
    """Network trouble must classify as INCONCLUSIVE (SleeperWriteError,
    kind='network') — callers stay unverified but must not treat the token
    as forged."""
    def opener(request, timeout=None):
        raise urllib.error.URLError("dns down")
    with pytest.raises(sw.SleeperWriteError) as ei:
        sw.verify_token_live("tok", _opener=opener)
    assert not isinstance(ei.value, sw.SleeperAuthError)
    assert ei.value.kind == "network"


# ---------------------------------------------------------------------------
# Route fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-verif-tok"
    sess = {"user_id": UID, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on = {"trade.send_in_sleeper"}
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags_on), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, flags_on
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _sess(token):
    with server._sessions_lock:
        return server._sessions[token]


# ---------------------------------------------------------------------------
# 2. POST /api/sleeper/link — verification proof path
# ---------------------------------------------------------------------------

def test_link_claim_mismatch_denied_and_nothing_stored(client):
    c, token, _ = client
    with patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(return_value={"raw": {}})) as probe:
        r = c.post("/api/sleeper/link", headers=_h(token),
                   data=json.dumps({"token": _token(user_id=OTHER_UID)}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "token_user_mismatch"
    probe.assert_not_called()                     # denied before the oracle
    assert not _sess(token).get("verified")
    assert c.get("/api/sleeper/link", headers=_h(token)).get_json()["connected"] is False


def test_link_dead_token_denied_by_oracle(client):
    """Forged/dead token: the claim matches but Sleeper (the signature
    oracle) rejects it → 403 token_rejected, nothing stored, unverified."""
    c, token, _ = client
    with patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(side_effect=sw.SleeperAuthError("dead", detail="401"))):
        r = c.post("/api/sleeper/link", headers=_h(token),
                   data=json.dumps({"token": _token()}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "token_rejected"
    assert not _sess(token).get("verified")
    assert c.get("/api/sleeper/link", headers=_h(token)).get_json()["connected"] is False


def test_link_oracle_inconclusive_links_but_unverified(client):
    """Transport failure during the probe: best-effort per plan §2c — the
    link stores (Send-in-Sleeper keeps working) but verification is NOT
    granted."""
    c, token, _ = client
    with patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(side_effect=sw.SleeperWriteError("net", kind="network"))):
        r = c.post("/api/sleeper/link", headers=_h(token),
                   data=json.dumps({"token": _token()}))
    assert r.status_code == 200
    body = r.get_json()
    assert body["connected"] is True and body["verified"] is False
    assert not _sess(token).get("verified")
    assert accounts.get_user_verified_via(UID) is None


def test_link_success_verifies_session_and_persists_marker(client):
    c, token, _ = client
    with patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(return_value={"raw": {}})):
        r = c.post("/api/sleeper/link", headers=_h(token),
                   data=json.dumps({"token": _token()}))
    assert r.status_code == 200
    body = r.get_json()
    assert body["connected"] is True and body["verified"] is True
    assert _sess(token).get("verified") is True
    # persisted controller marker — platform-neutral source string
    assert accounts.get_user_verified_via(UID) == "sleeper"


# ---------------------------------------------------------------------------
# 3. Write-gate matrix (representative gated route: /api/ranking-method)
# ---------------------------------------------------------------------------

def _post_method(c, token):
    return c.post("/api/ranking-method", headers=_h(token),
                  data=json.dumps({"method": "trio"}))


def test_gate_grace_allows_and_logs_unverified_write(client, caplog):
    c, token, _ = client
    with caplog.at_level("INFO", logger="trade_finder"):
        r = _post_method(c, token)
    assert r.status_code == 200
    line = [m for m in caplog.messages if m.startswith("AUTH-GRACE")]
    assert line and f"user_id={UID}" in line[0] \
        and "path=/api/ranking-method" in line[0]


def test_gate_denies_unverified_when_controller_exists(client):
    """First-verified-controller-wins: once ANY controller verified this
    user_id, an unverified session's writes 403 — even in grace."""
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    accounts.mark_user_verified(UID, "sleeper")
    r = _post_method(c, token)
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_gate_denies_unverified_under_enforcement(client):
    c, token, flags_on = client
    flags_on.add("auth.enforce_verified_writes")
    r = _post_method(c, token)
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_gate_allows_verified_session_even_under_enforcement(client):
    c, token, flags_on = client
    flags_on.add("auth.enforce_verified_writes")
    db_module.upsert_user(sleeper_user_id=UID)
    accounts.mark_user_verified(UID, "sleeper")
    _sess(token)["verified"] = True
    r = _post_method(c, token)
    assert r.status_code == 200


def test_gate_get_passes_through_on_mixed_method_route(client):
    """GETs on gated GET+POST routes pass the WRITE gate untouched. With no
    verified controller the READ gate allows them too, even under
    enforcement — enforcement is a write-only concept. (The controller-
    exists read denial is covered in test_verified_reads.py.)"""
    c, token, flags_on = client
    flags_on.add("auth.enforce_verified_writes")
    r = c.get("/api/anchor/scale", headers=_h(token))
    assert r.status_code == 200


def test_first_verified_wins_across_live_sessions(client):
    """Squatter scenario end-to-end: session B (squatter) can write during
    grace; the owner verifies on session A; B's next write 403s with no
    restart or session expiry."""
    c, token_a, _ = client
    token_b = "sess-squatter-tok"
    with server._sessions_lock:
        server._sessions[token_b] = {"user_id": UID, "active_format": "1qb_ppr",
                                     "last_active": 0.0}
    try:
        assert _post_method(c, token_b).status_code == 200      # grace
        with patch.object(server._sleeper_write, "verify_token_live",
                          MagicMock(return_value={"raw": {}})):
            r = c.post("/api/sleeper/link", headers=_h(token_a),
                       data=json.dumps({"token": _token()}))
        assert r.get_json()["verified"] is True
        r = _post_method(c, token_b)                            # immediately
        assert r.status_code == 403
        assert r.get_json()["error"] == "verification_required"
        assert _post_method(c, token_a).status_code == 200      # owner writes
    finally:
        with server._sessions_lock:
            server._sessions.pop(token_b, None)


# ---------------------------------------------------------------------------
# 5. POST /api/account/reset-rankings — verified-only squatter remedy
# ---------------------------------------------------------------------------

class _StubService:
    def __init__(self):
        self.reset_calls = []
        self._elo_overrides = {"123": 1600.0}
    def reset(self, position=None):
        self.reset_calls.append(position)
        return {"reset": True, "position": position}


def test_reset_rankings_requires_verified(client):
    c, token, _ = client
    r = c.post("/api/account/reset-rankings", headers=_h(token), data="{}")
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_reset_rankings_wipes_persisted_and_in_memory(client):
    c, token, _ = client
    # Squatter-authored artifacts under this user_id
    db_module.upsert_user(sleeper_user_id=UID)
    db_module.save_ranking_swipes(
        user_id=UID,
        ordered_ids=["1", "2"],       # → one pairwise swipe row
        scoring_format="1qb_ppr",
    )
    db_module.save_tier_overrides(UID, {"1": 1700.0}, scoring_format="1qb_ppr")
    db_module.save_tiers_position(UID, "RB", scoring_format="1qb_ppr")
    db_module.set_ranking_method(UID, "trio")
    assert db_module.load_swipe_decisions(user_id=UID, scoring_format="1qb_ppr")

    stub = _StubService()
    sess = _sess(token)
    sess["verified"] = True
    sess["services"] = {"1qb_ppr": stub}

    r = c.post("/api/account/reset-rankings", headers=_h(token), data="{}")
    assert r.status_code == 200, r.get_data(as_text=True)
    counts = r.get_json()["counts"]
    assert counts["swipe_decisions_deleted"] == 1
    assert counts["user_rows_cleared"] == 1

    assert db_module.load_swipe_decisions(user_id=UID, scoring_format="1qb_ppr") == []
    assert db_module.load_tier_overrides(UID, scoring_format="1qb_ppr") == {}
    assert db_module.get_tiers_saved(UID, scoring_format="1qb_ppr") == []
    assert db_module.get_ranking_method(UID) is None
    assert stub.reset_calls == [None] and stub._elo_overrides == {}


# ---------------------------------------------------------------------------
# 6. /api/session/init — additive `verification` response field
# ---------------------------------------------------------------------------

@pytest.fixture()
def init_client(monkeypatch, client):
    """Layer the minimum session_init world on top of `client`: a tiny
    universal pool, no Sleeper network, no background daemons."""
    c, token, flags_on = client
    from backend.ranking_service import Player

    pool = [
        Player("qb_1", "QB One", "QB", "AAA", 25, 3),
        Player("rb_1", "RB One", "RB", "BBB", 24, 2),
        Player("wr_1", "WR One", "WR", "CCC", 23, 1),
    ]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep":  {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", lambda lid: None)

    # Don't run session_init's fire-and-forget daemon (bg DB writes) — the
    # patched engine is torn down when the test ends. SELECTIVE: only the
    # bg-writes thread is inerted; ThreadPoolExecutor's session-init-rank
    # workers construct threading.Thread too and must actually run or
    # fut.result() deadlocks.
    real_thread = server.threading.Thread

    class _SelectiveThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _SelectiveThread)
    return c, token, flags_on


def _init_body(user_id=UID):
    return json.dumps({
        "user_id": user_id,
        "league_id": "league_x",
        "league_name": "Test League",
        "user_player_ids": ["qb_1"],
        "opponent_rosters": [
            {"user_id": "opp_1", "username": "Opp", "player_ids": ["rb_1"]},
        ],
    })


def test_session_init_reports_unverified_by_default(init_client):
    c, token, _ = init_client
    r = c.post("/api/session/init", headers=_h(token), data=_init_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    v = r.get_json()["verification"]
    assert v == {"session_verified": False, "user_verified": False,
                 "verified_via": None, "enforced": False}


def test_session_init_verified_carryover_and_controller_flag(init_client):
    c, token, _ = init_client
    # Session verified earlier (link proof) + persisted controller marker.
    _sess(token)["verified"] = True
    db_module.upsert_user(sleeper_user_id=UID)
    accounts.mark_user_verified(UID, "sleeper")

    r = c.post("/api/session/init", headers=_h(token), data=_init_body())
    v = r.get_json()["verification"]
    assert v["session_verified"] is True          # survives same-user re-init
    assert v["user_verified"] is True and v["verified_via"] == "sleeper"

    # Re-pointing the SAME token at a different user_id drops verified.
    r = c.post("/api/session/init", headers=_h(token),
               data=_init_body(user_id=OTHER_UID))
    v = r.get_json()["verification"]
    assert v["session_verified"] is False
    assert v["user_verified"] is False


def test_session_init_reports_enforcement(init_client):
    c, token, flags_on = init_client
    flags_on.add("auth.enforce_verified_writes")
    r = c.post("/api/session/init", headers=_h(token), data=_init_body())
    assert r.get_json()["verification"]["enforced"] is True
