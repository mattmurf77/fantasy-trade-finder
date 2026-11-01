"""D1 free-agent moves: POST /api/league/free-agents/move (scope §3, contract §3–§5).

Flask test client, an in-memory SQLite DB, a real session, a real Fernet key
and a real stored credential. Sleeper is never called: the public reads
(`_fetch_league_rosters`, `_fa_league_meta`) are stubbed, and the write runs
through the REAL `sleeper_write.fa_move` and its outcome-classified transport
with an injected `_opener` (`Platform` below) that simulates Sleeper: a
complete add, a pending claim, a partial, a refusal, a token rejection, a
connect-phase failure, a post-send timeout or reset, a 5xx, an unreadable 2xx.

The captured shapes don't exist yet, so `build_fa_move_body` and
`read_fa_move_result` are replaced by a test double of a captured op, and
`FA_MOVE_SHAPES_CAPTURED` is forced on. Everything else is the shipped code.
Nothing here makes a live write.
"""
from __future__ import annotations

import base64
import errno
import http.client
import inspect
import io
import json
import socket
import threading
import time
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.server as server
import backend.sleeper_write as sleeper_write
from backend import fa_move_copy as copy
from backend.write_outcome import OUTCOME_UNKNOWN

SLEEPER_UID = "313560442465169408"
USER = SLEEPER_UID                    # the link route binds FTF user == Sleeper user
LEAGUE = "1312140920132497408"
MFL_LEAGUE = "61204"
ADD, DROP, KEEP = "4046", "6794", "1111"
THEIRS = "2222"
OP = "ftf_test_fa_move"
TOKEN = "sess-fa-move"
V1, V2 = copy.SLEEPER_ROSTER_MOVES_V1, copy.SLEEPER_ROSTER_MOVES_V2
NAMES = {ADD: "Aaron Add", DROP: "Drew Drop"}
META = {"name": "Dummy League",
        "roster_positions": ["QB", "RB", "WR", "TE", "BN"],
        "settings": {"reserve_slots": 0, "taxi_slots": 0, "waiver_type": 2,
                     "waiver_budget": 100}}

# The granted props, exactly (scope §1; test_analytics_taxonomy_fa_move_server).
SUCCEEDED_PROPS = {"move_kind", "has_drop", "has_bid", "result", "attempt_id",
                   "league_platform"}


def _rosters(mine=(DROP, KEEP)):
    return [{"owner_id": USER, "roster_id": 3, "players": list(mine),
             "settings": {"waiver_budget_used": 20}},
            {"owner_id": "other", "roster_id": 4, "players": [THEIRS]}]


def _jwt(exp_offset=3600, uid=SLEEPER_UID):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64({'user_id': uid, 'exp': int(time.time()) + exp_offset})}.sig"


# ---------------------------------------------------------------------------
# The simulated platform: an urllib opener (no network)
# ---------------------------------------------------------------------------

class _Resp:
    status = 200

    def __init__(self, body: bytes = b"", read_exc=None):
        self._body, self._exc = body, read_exc

    def read(self):
        if self._exc is not None:
            raise self._exc
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _data(node):
    return json.dumps({"data": {OP: node}}).encode()


class Platform:
    """What Sleeper does with the one write. `calls` records (request, timeout)
    so tests count opener calls; `on_call` runs inside the call (e.g. to read
    the DB while the write is in flight)."""

    BEHAVIOURS = {
        "complete": lambda: _Resp(_data({"status": "complete", "result": "accepted",
                                         "transaction_id": "TX9"})),
        "complete_no_tx": lambda: _Resp(_data({"status": "complete", "result": "accepted"})),
        "pending": lambda: _Resp(_data({"status": "pending", "result": "accepted",
                                        "transaction_id": "TX10"})),
        "partial": lambda: _Resp(_data({"status": "complete", "result": "partial",
                                        "added": [ADD], "dropped": []})),
        "refused": lambda: _Resp(json.dumps(
            {"errors": [{"message": "This player cannot be added right now."}]}).encode()),
        "auth": "http_401",
        "connect_refused": urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")),
        "dns": urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")),
        "no_route": urllib.error.URLError(OSError(errno.EHOSTUNREACH, "No route to host")),
        "read_timeout": TimeoutError("The read operation timed out"),
        "reset": ConnectionResetError(54, "Connection reset by peer"),
        "remote_disconnected": http.client.RemoteDisconnected("closed"),
        "urlerror_timeout": urllib.error.URLError(TimeoutError("timed out")),
        "body_read_timeout": lambda: _Resp(read_exc=TimeoutError("timed out")),
        "http_500": "http_500",
        "http_504": "http_504",
        "http_400": "http_400",
        "http_429": "http_429",
        "non_json_2xx": lambda: _Resp(b"<html>surprise</html>"),
        "no_data_2xx": lambda: _Resp(b'{"ok": true}'),
        "unreadable_node": lambda: _Resp(_data({"weird": 1})),
    }

    def __init__(self):
        self.mode = "complete"
        self.calls: list = []
        self.on_call = None

    def opener(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.on_call is not None:
            self.on_call(request)
        b = self.BEHAVIOURS[self.mode]
        if isinstance(b, str) and b.startswith("http_"):
            code = int(b[5:])
            raise urllib.error.HTTPError(request.full_url, code, "err", {},
                                         io.BytesIO(b"<html>oops</html>"))
        if isinstance(b, BaseException):
            raise b
        return b()


def _fake_build(req):
    return OP, {"operationName": OP,
                "variables": {"add": req.add_player_id, "drop": req.drop_player_id,
                              "roster_id": req.roster_id, "kind": req.move_kind,
                              "bid": req.faab_bid},
                "query": "mutation ftf_test_fa_move { __typename }"}


def _fake_read(req, node):
    if not isinstance(node, dict) or node.get("status") not in ("complete", "pending"):
        raise sleeper_write.SleeperWriteError("unreadable", kind=OUTCOME_UNKNOWN)
    return {"status": node["status"], "result": node["result"],
            "transaction_id": node.get("transaction_id"),
            "added": node.get("added"), "dropped": node.get("dropped"), "raw": node}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class Harness:
    def __init__(self, monkeypatch, engine):
        self.mp = monkeypatch
        self.engine = engine
        self.platform = Platform()
        self.flags = {"sleeper.send_add_drop", "trade.send_in_sleeper"}
        self.rosters = _rosters()
        self.meta = dict(META)
        self.events: list[tuple] = []
        self.stamps: list[tuple] = []
        self.saves: list[tuple] = []
        self.client = server.app.test_client()
        self.sess = {"user_id": USER, "verified": True, "active_format": "1qb_ppr",
                     "last_active": time.time()}
        self.now = datetime.now(timezone.utc)

    # requests -----------------------------------------------------------
    def body(self, **over):
        b = {"league_id": LEAGUE, "add_player_id": ADD, "drop_player_id": DROP,
             "move_kind": "add", "attempt_id": str(uuid.uuid4()),
             "consent": {"copy_version": V1, "locale": "en-US"}}
        b.update(over)
        return {k: v for k, v in b.items() if v is not _ABSENT}

    def post(self, **over):
        return self.client.post("/api/league/free-agents/move",
                                headers={"X-Session-Token": TOKEN,
                                         "Content-Type": "application/json",
                                         "X-Device": "iphone", "X-App-Version": "1.22.0"},
                                data=json.dumps(self.body(**over)))

    # DB views -------------------------------------------------------------
    def rows(self, table):
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(select(table))]

    def moves(self, attempt_id=None):
        return [r for r in self.rows(db_module.platform_write_moves_table)
                if attempt_id is None or r["attempt_id"] == attempt_id]

    def consents(self):
        return self.rows(db_module.platform_write_consents_table)

    def stored_roster(self):
        return json.loads(db_module.load_league_members(LEAGUE)[0]["roster_data"])

    def events_named(self, name):
        return [e for e in self.events if e[1] == name]


_ABSENT = object()


@pytest.fixture()
def h(monkeypatch):
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    # The default pool for an in-memory SQLite DB gives each thread its own
    # connection. Never StaticPool here: the first request of a process starts
    # the `win-now-resume` thread (server._ensure_background_threads), which
    # would then share this test's one connection and race it.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db_module.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    hz = Harness(monkeypatch, engine)

    monkeypatch.setattr(server, "is_enabled", lambda k: k in hz.flags)
    monkeypatch.setattr(sleeper_write, "FA_MOVE_SHAPES_CAPTURED", True)
    monkeypatch.setattr(sleeper_write, "build_fa_move_body", _fake_build)
    monkeypatch.setattr(sleeper_write, "read_fa_move_result", _fake_read)
    real_fa_move = sleeper_write.fa_move
    monkeypatch.setattr(sleeper_write, "fa_move",
                        lambda token, req: real_fa_move(token, req, _opener=hz.platform.opener))
    monkeypatch.setattr(server, "_fetch_league_rosters",
                        lambda lid: json.loads(json.dumps(hz.rosters)) if hz.rosters is not None else None)
    monkeypatch.setattr(server, "_fa_league_meta", lambda lid: hz.meta)
    monkeypatch.setattr(server, "_player_names_by_id",
                        lambda ids: {str(i): NAMES[str(i)] for i in ids if str(i) in NAMES})
    monkeypatch.setattr(server, "record_event",
                        lambda uid, name, **kw: hz.events.append((uid, name, kw)))
    monkeypatch.setattr(server, "touch_user_activity", lambda *a, **k: None)
    monkeypatch.setattr(server._roster_refresh, "stamp",
                        lambda lid: hz.stamps.append((lid, threading.current_thread())))
    real_save = db_module.set_league_member_roster

    def _save(*a, **k):
        hz.saves.append(threading.current_thread())
        return real_save(*a, **k)
    monkeypatch.setattr(db_module, "set_league_member_roster", _save)
    monkeypatch.setattr(server, "_fa_move_now", lambda: hz.now)

    db_module.upsert_sleeper_credential(USER, SLEEPER_UID, sleeper_write.encrypt_token(_jwt()),
                                        (hz.now + timedelta(days=300)).isoformat())
    db_module.upsert_league_members(LEAGUE, [{"user_id": USER, "username": "me",
                                              "player_ids": [DROP, KEEP]},
                                             {"user_id": "other", "username": "them",
                                              "player_ids": [THEIRS]}])
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        server._sessions[TOKEN] = hz.sess
    try:
        yield hz
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        engine.dispose()


def add_league(engine, league_id, platform):
    with engine.begin() as conn:
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id=league_id, user_id=USER, name=platform, platform=platform))


def _err(r):
    body = r.get_json()
    assert body["detail"] == body["message"] and body["message"], body
    return body


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------

def test_add_drop_with_consent_completes(h):
    r = h.post()
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    attempt = h.platform.calls and json.loads(h.platform.calls[0][0].data)["variables"]
    assert body["status"] == "complete" and body["move_kind"] == "add"
    assert body["result"] == "accepted" and body["league_platform"] == "sleeper"
    assert body["platform_transaction_id"] == "TX9"
    assert body["title"] and body["lines"] == ["Aaron Add added, Drew Drop dropped in Dummy League."]
    assert set(body) == {"status", "move_kind", "result", "league_platform", "attempt_id",
                         "title", "lines", "platform_transaction_id"}
    # One write; the roster id is the server's, never the client's.
    assert len(h.platform.calls) == 1
    assert attempt == {"add": ADD, "drop": DROP, "roster_id": 3, "kind": "add", "bid": None}
    req = h.platform.calls[0][0]
    assert req.get_header("Authorization") and req.get_header("X-sleeper-graphql-op") == OP
    # Records: one grant, then the move's two rows.
    (grant,) = h.consents()
    assert grant["kind"] == "grant" and grant["copy_version"] == V1
    assert grant["platform"] == "sleeper" and grant["platform_user_id"] == SLEEPER_UID
    assert grant["league_scope"] == "all_linked" and grant["locale"] == "en-US"
    assert grant["client_platform"] == "iphone" and grant["app_version"] == "1.22.0"
    assert grant["trigger_attempt_id"] == body["attempt_id"]
    sent, result = sorted(h.moves(body["attempt_id"]), key=lambda m: m["phase"] != "sent")
    assert sent["phase"] == "sent" and sent["consent_id"] == grant["consent_id"]
    assert json.loads(sent["add_player_ids"]) == [ADD]
    assert json.loads(sent["drop_player_ids"]) == [DROP]
    assert result["phase"] == "result" and result["result"] == "accepted"
    assert result["status"] == "complete" and result["platform_transaction_id"] == "TX9"
    assert json.loads(result["response_json"]) == body and result["response_status"] == 200


def test_add_without_drop_into_open_slot(h):
    h.platform.mode = "complete_no_tx"
    r = h.post(drop_player_id=_ABSENT)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert "platform_transaction_id" not in body
    assert body["lines"] == ["Aaron Add added in Dummy League."]
    assert h.stored_roster() == [DROP, KEEP, ADD]


def test_partial_is_stated_exactly(h):
    h.platform.mode = "partial"
    body = h.post().get_json()
    assert body["result"] == "partial" and body["title"] == "Partly done"
    assert body["lines"] == ["Aaron Add added in Dummy League.", "Drew Drop was not dropped."]
    # The roster follows what the platform reported: A on, B still there.
    assert h.stored_roster() == [DROP, KEEP, ADD]


def test_write_succeeded_event_exact_props(h):
    body = h.post().get_json()
    (ev,) = h.events_named("fa_move_write_succeeded")
    uid, _, kw = ev
    assert uid == USER and kw["league_id"] == LEAGUE
    assert set(kw["props"]) == SUCCEEDED_PROPS and "platform" not in kw["props"]
    assert kw["props"] == {"move_kind": "add", "has_drop": True, "has_bid": False,
                           "result": "accepted", "attempt_id": body["attempt_id"],
                           "league_platform": "sleeper"}
    (rec,) = h.events_named("fa_move_consent_recorded")
    assert rec[2]["props"] == {"surface": None, "copy_version": V1, "league_platform": "sleeper"}


# ---------------------------------------------------------------------------
# Order of checks (§B3): every pre-write refusal, with detail == message and
# NO opener call
# ---------------------------------------------------------------------------

def _no_write(h):
    assert h.platform.calls == []
    assert [m for m in h.moves() if m["phase"] == "sent"] == []


def test_flag_off_is_404_before_the_session(h):
    h.flags.discard("sleeper.send_add_drop")
    r = h.client.post("/api/league/free-agents/move", data="{}")   # no session at all
    assert r.status_code == 404 and _err(r)["error"] == "feature_disabled"
    _no_write(h)


def test_test_mode_fails_closed(h, monkeypatch):
    monkeypatch.setattr(server, "_TEST_MODE", True)
    assert h.post().status_code == 599
    _no_write(h)


def test_shapes_not_captured_is_the_handoff_404(h, monkeypatch):
    """Flag on but no captured shapes: the capability says `handoff`, so the
    route answers 404 `feature_disabled` (state 1, the hand-off)."""
    monkeypatch.setattr(sleeper_write, "FA_MOVE_SHAPES_CAPTURED", False)
    r = h.post()
    assert r.status_code == 404 and _err(r)["error"] == "feature_disabled"
    _no_write(h)
    assert h.consents() == []


def test_adapter_never_sends_until_captured(monkeypatch):
    """Defense in depth: even called directly, the real adapter refuses before
    building or sending while the shapes aren't captured."""
    monkeypatch.setattr(sleeper_write, "FA_MOVE_SHAPES_CAPTURED", False)
    platform = Platform()
    req = sleeper_write.FaMoveRequest(LEAGUE, 3, ADD, DROP, "add")
    with pytest.raises(sleeper_write.SleeperWriteError) as ei:
        sleeper_write.fa_move("tok", req, _opener=platform.opener)
    assert ei.value.kind == "config" and platform.calls == []
    with pytest.raises(sleeper_write.SleeperWriteError):
        sleeper_write.build_fa_move_body(req)


@pytest.mark.parametrize("setup,status,code", [
    ("unverified", 403, "verification_required"),
    ("missing_attempt", 400, "bad_request"),
    ("bad_attempt", 400, "bad_request"),
    ("bad_kind", 400, "bad_request"),
    ("drop_is_add", 400, "bad_request"),
    ("mfl_league", 404, "feature_disabled"),
    ("no_credential", 409, "sleeper_not_linked"),
    ("expired_token", 409, "sleeper_expired"),
    ("no_consent", 409, "consent_required"),
    ("stale_copy_version", 409, "consent_required"),
    ("unknown_locale", 409, "consent_required"),
    ("rosters_read_failed", 502, "sleeper_write_failed"),
    ("other_account", 409, "sleeper_not_linked"),
    ("already_mine", 422, "player_unavailable"),
    ("taken", 422, "player_unavailable"),
    ("drop_gone", 422, "asset_not_owned"),
    ("roster_full", 422, "roster_full_drop_required"),
    ("claim_d5_unmet", 422, "waiver_claim_unsupported"),
    ("add_but_on_waivers_claims_off", 422, "waiver_claim_unsupported"),
    ("add_but_on_waivers_claims_on", 409, "move_kind_changed"),
    ("over_budget", 422, "waiver_bid_over_budget"),
])
def test_pre_write_refusals_never_call_the_platform(h, monkeypatch, setup, status, code):
    over = {}
    if setup == "unverified":
        h.sess["verified"] = False
    elif setup == "missing_attempt":
        over["attempt_id"] = _ABSENT
    elif setup == "bad_attempt":
        over["attempt_id"] = "not-a-uuid"
    elif setup == "bad_kind":
        over["move_kind"] = "trade"
    elif setup == "drop_is_add":
        over["drop_player_id"] = ADD
    elif setup == "mfl_league":
        add_league(h.engine, MFL_LEAGUE, "mfl")
        over["league_id"] = MFL_LEAGUE
    elif setup == "no_credential":
        db_module.delete_sleeper_credential(USER, withdrawn_via="disconnect")
    elif setup == "expired_token":
        db_module.upsert_sleeper_credential(USER, SLEEPER_UID,
                                            sleeper_write.encrypt_token(_jwt(-60)), None)
    elif setup == "no_consent":
        over["consent"] = _ABSENT
    elif setup == "stale_copy_version":
        over["consent"] = {"copy_version": "sleeper-roster-moves-v0", "locale": "en-US"}
    elif setup == "unknown_locale":
        over["consent"] = {"copy_version": V1, "locale": "fr-FR"}
    elif setup == "rosters_read_failed":
        h.rosters = None
    elif setup == "other_account":
        h.rosters = [r for r in h.rosters if r["owner_id"] != USER]
    elif setup == "already_mine":
        over["add_player_id"] = KEEP
    elif setup == "taken":
        over["add_player_id"] = THEIRS
    elif setup == "drop_gone":
        over["drop_player_id"] = "5555"
    elif setup == "roster_full":
        h.meta = {**META, "roster_positions": ["QB", "BN"]}
        over["drop_player_id"] = _ABSENT
    elif setup == "claim_d5_unmet":
        over["move_kind"] = "claim"
    elif setup.startswith("add_but_on_waivers"):
        monkeypatch.setattr(server, "_fa_move_actual_kind", lambda lid, pid: "claim")
        if setup.endswith("claims_on"):
            monkeypatch.setattr(server, "_fa_move_claims_enabled", lambda p: True)
    elif setup == "over_budget":
        monkeypatch.setattr(server, "_fa_move_claims_enabled", lambda p: True)
        over.update(move_kind="claim", faab_bid=81)          # 100 budget − 20 used = 80
    r = h.post(**over)
    assert r.status_code == status, r.get_json()
    body = _err(r)
    assert body["error"] == code
    _no_write(h)
    if code == "consent_required":
        assert body["consent"] == copy.consent_block("sleeper", reason="first")
        assert body["consent"]["copy_version"] == V1
        assert [c for c in h.consents() if c["kind"] == "grant"] == []
    if setup == "rosters_read_failed":
        assert body["kind"] == "roster_read"
    if setup == "other_account":
        assert "isn't in Dummy League" in body["message"]
    if setup == "over_budget":
        assert body["remaining"] == 80
    if setup == "expired_token":
        assert db_module.get_sleeper_credential(USER) is None
    if code not in ("sleeper_write_failed",):
        assert "kind" not in body


def test_a_client_sent_platform_is_ignored(h):
    """AC-43: the platform comes from the league row."""
    r = h.post(platform="mfl", league_platform="espn")
    assert r.status_code == 200 and r.get_json()["league_platform"] == "sleeper"
    add_league(h.engine, MFL_LEAGUE, "mfl")
    r = h.post(league_id=MFL_LEAGUE, platform="sleeper")
    assert r.status_code == 404 and len(h.platform.calls) == 1


_ORDER = [
    "_verified_write_denial(",                 # 3
    "_fa_move_parse_body(",                    # 4
    "_fa_move_league_platform(",               # 5
    "_fa_move_live(",                          # 6
    "platform_write_move_rows(",               # 7  attempt_id
    "_fa_move_blocks(",                        # 7b double-move block
    "get_sleeper_credential(",                 # 8
    "_fa_move_consent_step(",                  # 9
    "_fetch_league_rosters(",                  # 10
    "_fa_move_claims_enabled(",                # 11
    "_fa_move_preflight_over_budget(",         # budget, immediately before the write
    "record_platform_write_move(",             # 12 the sent row
    "_sleeper_write.fa_move(",                 # 12 the write
    "set_league_member_roster(",               # K-F5 save, after the result row
    "_fa_move_stamp_async(",                   # K-F5 stamp, last
]


def test_order_of_checks_in_source():
    """Structural twin of the behavioural matrix above (sabotage: move the
    write above consent): each step's first call appears in §B3 order."""
    src = inspect.getsource(server._fa_move_core)
    positions = [src.find(marker) for marker in _ORDER]
    assert -1 not in positions, dict(zip(_ORDER, positions))
    assert positions == sorted(positions), dict(zip(_ORDER, positions))
    # The consent step (and its grant commit) precedes the only write call.
    assert src.count("_sleeper_write.fa_move(") == 1


# ---------------------------------------------------------------------------
# Consent is committed before the write
# ---------------------------------------------------------------------------

def test_grant_and_sent_row_exist_when_the_platform_is_called_and_survive_a_refusal(h):
    seen = {}

    def _inspect(request):
        seen["grants"] = [c for c in h.consents() if c["kind"] == "grant"]
        seen["sent"] = [m for m in h.moves() if m["phase"] == "sent"]
    h.platform.on_call = _inspect
    h.platform.mode = "refused"
    r = h.post()
    assert r.status_code == 502
    assert len(seen["grants"]) == 1 and len(seen["sent"]) == 1
    # The grant stands after the platform refused; the move row records it.
    assert len([c for c in h.consents() if c["kind"] == "grant"]) == 1
    (result,) = [m for m in h.moves() if m["phase"] == "result"]
    assert result["result"] == "rejected" and result["error_code"] == "sleeper_write_failed"


def test_inside_the_window_no_consent_is_needed(h):
    assert h.post().status_code == 200
    h.rosters = _rosters(mine=(KEEP, ADD))
    r = h.post(add_player_id="7777", drop_player_id=ADD, consent=_ABSENT)
    assert r.status_code == 200, r.get_json()
    assert len([c for c in h.consents() if c["kind"] == "grant"]) == 1


# ---------------------------------------------------------------------------
# Outcome classification (write_outcome.py) and the codes that follow
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["read_timeout", "reset", "remote_disconnected",
                                  "urlerror_timeout", "body_read_timeout", "http_500",
                                  "http_504", "non_json_2xx", "no_data_2xx",
                                  "unreadable_node"])
def test_after_send_failure_is_outcome_unknown_and_never_retried(h, mode):
    h.platform.mode = mode
    r = h.post()
    assert r.status_code == 502
    body = _err(r)
    assert body["error"] == "sleeper_outcome_unknown"
    assert body["title"] == "Check before resending" and "kind" not in body
    assert len(h.platform.calls) == 1                     # never retried
    (result,) = [m for m in h.moves() if m["phase"] == "result"]
    assert result["result"] == "unknown"
    assert h.stored_roster() == [DROP, KEEP] and h.stamps == []
    assert h.events_named("fa_move_write_succeeded") == []


@pytest.mark.parametrize("mode", ["connect_refused", "dns", "no_route", "http_429"])
def test_connect_phase_failure_is_not_sent(h, mode):
    h.platform.mode = mode
    r = h.post()
    assert r.status_code == 502
    body = _err(r)
    assert body["error"] == "sleeper_write_failed" and body["kind"] == "network"
    assert "nothing was sent" in body["message"]
    (result,) = [m for m in h.moves() if m["phase"] == "result"]
    assert result["result"] == "error"
    # Not sent, so not blocked: the same named CTA (a new attempt) may send.
    h.platform.mode = "complete"
    assert h.post(consent=_ABSENT).status_code == 200


@pytest.mark.parametrize("mode", ["refused", "http_400"])
def test_platform_refusal_is_write_failed_without_kind(h, mode):
    h.platform.mode = mode
    r = h.post()
    body = _err(r)
    assert r.status_code == 502 and body["error"] == "sleeper_write_failed"
    assert "kind" not in body                                # 10f, not state 11
    assert "This player cannot be added" not in body["message"]   # Sleeper's text is logged only
    assert h.stored_roster() == [DROP, KEEP]


def test_token_rejected_drops_credential_and_withdraws(h):
    h.platform.mode = "auth"
    r = h.post()
    assert r.status_code == 409 and _err(r)["error"] == "sleeper_rejected"
    assert db_module.get_sleeper_credential(USER) is None
    withdrawals = [c for c in h.consents() if c["kind"] == "withdrawal"]
    assert [w["withdrawn_via"] for w in withdrawals] == ["credential_rejected"]
    (ev,) = h.events_named("fa_move_consent_withdrawn")
    assert ev[2]["props"] == {"via": "credential_rejected", "league_platform": "sleeper"}
    assert ev[2]["touch_user"] is False                      # a system withdrawal (F2)


def test_config_failure_is_unconfigured(h, monkeypatch):
    def _boom(req):
        raise sleeper_write.SleeperWriteError("no shape", kind="config")
    monkeypatch.setattr(sleeper_write, "build_fa_move_body", _boom)
    r = h.post()
    assert r.status_code == 503 and _err(r)["error"] == "sleeper_unconfigured"
    assert h.platform.calls == []


def test_unexpected_error_before_the_sent_row_is_internal_error(h, monkeypatch):
    def _boom(*a):
        raise RuntimeError("bug")
    monkeypatch.setattr(server, "_fa_move_blocks", _boom)
    r = h.post()
    assert r.status_code == 500
    body = _err(r)
    assert body["error"] == "internal_error" and body["title"] == "Check before resending"
    _no_write(h)


# ---------------------------------------------------------------------------
# Idempotency (§B6)
# ---------------------------------------------------------------------------

def test_same_attempt_id_writes_once_and_replays_the_answer(h):
    attempt = str(uuid.uuid4())
    first = h.post(attempt_id=attempt)
    second = h.post(attempt_id=attempt)
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()
    assert len(h.platform.calls) == 1
    assert len(h.moves(attempt)) == 2


def test_same_attempt_id_replays_an_error_too(h):
    attempt = str(uuid.uuid4())
    h.platform.mode = "read_timeout"
    first = h.post(attempt_id=attempt)
    h.platform.mode = "complete"
    second = h.post(attempt_id=attempt)
    assert first.get_json() == second.get_json() and second.status_code == 502
    assert len(h.platform.calls) == 1


def test_in_flight_duplicate_is_move_in_progress(h):
    attempt = str(uuid.uuid4())
    db_module.record_platform_write_move({
        "attempt_id": attempt, "phase": "sent", "user_id": USER, "platform": "sleeper",
        "league_id": LEAGUE, "add_player_ids": json.dumps([ADD]),
        "sent_at": h.now.isoformat()})
    r = h.post(attempt_id=attempt)
    assert r.status_code == 409 and _err(r)["error"] == "move_in_progress"
    assert h.platform.calls == []


def test_a_concurrent_duplicate_loses_the_sent_row_race(h, monkeypatch):
    """Two requests with one attempt_id that both pass step 7: the unique
    (attempt_id, phase) constraint lets one write; the other never sends."""
    real = db_module.record_platform_write_move
    attempt = str(uuid.uuid4())

    def _racing(row):
        if row["phase"] == "sent":
            real({**row})                      # the twin request got there first
        return real(row)
    monkeypatch.setattr(db_module, "record_platform_write_move", _racing)
    r = h.post(attempt_id=attempt)
    assert r.status_code == 409 and _err(r)["error"] == "move_in_progress"
    assert h.platform.calls == []


def test_another_users_attempt_id_is_refused(h):
    attempt = str(uuid.uuid4())
    db_module.record_platform_write_move({
        "attempt_id": attempt, "phase": "sent", "user_id": "someone-else",
        "platform": "sleeper", "league_id": LEAGUE, "sent_at": h.now.isoformat()})
    r = h.post(attempt_id=attempt)
    assert r.status_code == 400 and _err(r)["error"] == "bad_request"
    assert h.platform.calls == []


# ---------------------------------------------------------------------------
# The double-move block (§B6, ux-lead F1)
# ---------------------------------------------------------------------------

def _seed_move(h, *, result=None, status=None, minutes_ago=1, add=ADD, kind="add"):
    attempt = str(uuid.uuid4())
    sent_at = (h.now - timedelta(minutes=minutes_ago)).isoformat()
    base = {"attempt_id": attempt, "user_id": USER, "platform": "sleeper",
            "league_id": LEAGUE, "move_kind": kind, "add_player_ids": json.dumps([add]),
            "drop_player_ids": "[]", "sent_at": sent_at}
    db_module.record_platform_write_move({**base, "phase": "sent"})
    if result:
        db_module.record_platform_write_move({**base, "phase": "result", "result": result,
                                              "status": status, "response_status": 200,
                                              "response_json": "{}"})
    return attempt


@pytest.mark.parametrize("result", [None, "unknown"])
def test_recent_unconfirmed_move_blocks_a_new_attempt(h, result):
    _seed_move(h, result=result, minutes_ago=14)
    r = h.post()
    assert r.status_code == 409
    body = _err(r)
    assert body["error"] == "move_in_progress" and "Aaron Add" in body["message"]
    assert h.platform.calls == []


@pytest.mark.parametrize("result", [None, "unknown"])
def test_the_block_lifts_at_15_minutes(h, result):
    _seed_move(h, result=result, minutes_ago=15)
    assert h.post().status_code == 200
    assert len(h.platform.calls) == 1


@pytest.mark.parametrize("result,status", [("rejected", None), ("error", None),
                                           ("accepted", "complete")])
def test_a_recorded_result_lifts_the_block(h, result, status):
    _seed_move(h, result=result, status=status, minutes_ago=1)
    assert h.post().status_code == 200


def test_a_pending_claim_blocks_until_24h(h, monkeypatch):
    monkeypatch.setattr(server, "_fa_move_claims_enabled", lambda p: True)
    monkeypatch.setattr(sleeper_write, "FA_CLAIM_SHAPE_CAPTURED", True)
    _seed_move(h, result="accepted", status="pending", minutes_ago=23 * 60, kind="claim")
    r = h.post(move_kind="claim", faab_bid=5, consent={"copy_version": V1, "locale": "en-US"})
    assert r.status_code == 409 and "already pending" in _err(r)["message"]
    assert h.platform.calls == []
    h.now = h.now + timedelta(hours=1)
    h.platform.mode = "pending"
    assert h.post(move_kind="claim", faab_bid=5).status_code == 200


def test_the_block_is_per_player(h):
    _seed_move(h, result="unknown", minutes_ago=1, add="8888")
    assert h.post().status_code == 200


# ---------------------------------------------------------------------------
# Claims (R15.8 D5) and move_kind (D10)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("version,captured", [(V1, False), (V1, True), (V2, False)])
def test_a_claim_is_refused_until_v2_and_the_shape(h, monkeypatch, version, captured):
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", version)
    monkeypatch.setattr(sleeper_write, "FA_CLAIM_SHAPE_CAPTURED", captured)
    r = h.post(move_kind="claim", faab_bid=5, consent={"copy_version": version, "locale": "en-US"})
    assert r.status_code == 422 and _err(r)["error"] == "waiver_claim_unsupported"
    assert h.platform.calls == []


def test_claims_need_v2_even_with_the_shape(h, monkeypatch):
    """AC-33: enabling claims while the current version is v1 fails."""
    monkeypatch.setattr(sleeper_write, "FA_CLAIM_SHAPE_CAPTURED", True)
    assert copy.CURRENT_CONSENT_VERSION["sleeper"] == V1
    assert server._fa_move_claims_enabled("sleeper") is False


def test_a_claim_goes_through_with_v2_and_the_shape_and_is_pending(h, monkeypatch):
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "sleeper", V2)
    monkeypatch.setattr(sleeper_write, "FA_CLAIM_SHAPE_CAPTURED", True)
    h.platform.mode = "pending"
    r = h.post(move_kind="claim", faab_bid=7, consent={"copy_version": V2, "locale": "en-US"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["status"] == "pending" and body["move_kind"] == "claim"
    assert body["title"] == "Claim submitted"
    assert not any("added" in line.lower() for line in body["lines"])     # never "added"
    assert json.loads(h.platform.calls[0][0].data)["variables"]["bid"] == 7
    # Pending: no roster write, no stamp (§B10).
    assert h.saves == [] and h.stamps == [] and h.stored_roster() == [DROP, KEEP]
    ev = h.events_named("fa_move_write_succeeded")[0][2]["props"]
    assert ev["move_kind"] == "claim" and ev["has_bid"] is True


def test_a_bid_on_an_add_is_never_sent(h):
    r = h.post(faab_bid=9)
    assert r.status_code == 200
    assert json.loads(h.platform.calls[0][0].data)["variables"]["bid"] is None


# ---------------------------------------------------------------------------
# Preflight budget and the 76 s worst case (contract §5)
# ---------------------------------------------------------------------------

def test_worst_case_is_a_pinned_sum():
    assert server.FA_MOVE_SERVER_WORST_CASE_S == 76
    assert server._FA_MOVE_PREFLIGHT_BUDGET_S == 30
    write_path = sum(sleeper_write.FA_MOVE_WRITE_TIMEOUTS_S)
    assert write_path <= 46 == server._FA_MOVE_WRITE_PATH_MAX_S
    assert server._FA_MOVE_PREFLIGHT_BUDGET_S + write_path <= server.FA_MOVE_SERVER_WORST_CASE_S
    # The client's timeout is derived from it: (76 + 15) × 1000.
    assert (server.FA_MOVE_SERVER_WORST_CASE_S + 15) * 1000 == 91_000


def test_the_write_uses_only_the_pinned_timeouts(h):
    assert h.post().status_code == 200
    assert len(h.platform.calls) <= len(sleeper_write.FA_MOVE_WRITE_TIMEOUTS_S)
    assert [t for _, t in h.platform.calls] == list(
        sleeper_write.FA_MOVE_WRITE_TIMEOUTS_S[:len(h.platform.calls)])


@pytest.mark.parametrize("elapsed,sends", [(30.0, True), (30.5, False)])
def test_preflight_budget_is_checked_before_the_write(h, monkeypatch, elapsed, sends):
    clock = {"t": 1000.0}
    monkeypatch.setattr(server, "_fa_move_clock", lambda: clock["t"])
    real = server._fetch_league_rosters

    def _slow(lid):
        clock["t"] += elapsed                  # a slow pre-write read
        return real(lid)
    monkeypatch.setattr(server, "_fetch_league_rosters", _slow)
    r = h.post()
    if sends:
        assert r.status_code == 200 and len(h.platform.calls) == 1
    else:
        assert r.status_code == 502
        body = _err(r)
        assert body["error"] == "sleeper_write_failed" and body["kind"] == "roster_read"
        _no_write(h)


# ---------------------------------------------------------------------------
# K-F5 (§B10): roster saved before answering; stamp off the request thread
# ---------------------------------------------------------------------------

def test_complete_saves_the_roster_on_the_request_thread_then_stamps_off_it(h):
    me = threading.current_thread()
    r = h.post()
    assert r.status_code == 200
    # Saved on the request thread, i.e. before the response existed.
    assert h.saves == [me]
    assert h.stored_roster() == [KEEP, ADD]           # B off, A on
    for t in threading.enumerate():
        if t.name == "fa-move-stamp":
            t.join(5)
    assert len(h.stamps) == 1
    lid, thread = h.stamps[0]
    assert lid == LEAGUE and thread is not me         # sabotage: call it inline


@pytest.mark.parametrize("mode", ["pending", "refused", "read_timeout", "connect_refused",
                                  "auth"])
def test_no_roster_write_unless_complete(h, mode):
    h.platform.mode = mode
    h.post()
    assert h.saves == [] and h.stamps == []
    assert h.stored_roster() == [DROP, KEEP]
