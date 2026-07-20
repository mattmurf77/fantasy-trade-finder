"""POST/DELETE /api/test-users — synthetic stage-user spawner for onboarding
QA (backend/test_users.py + routes in server.py).

Covers:
  (a) allowlist-only gate: the flag is NOT consulted server-side (it gates
      only the client Settings row, shipped per-device via the experiment
      overlay) — flag off still spawns for allowlisted callers
  (b) caller not on the tester allowlist → 404 (no existence signal)
  (c) allowlisted device + flag on → spawn returns token + a session that is
      initialized-session-shaped and NOT marked is_demo
  (d) stage seeding: fresh/activated leave no boards; board_owner persists a
      WR quickset board in users.tier_overrides/tiers_saved with
      ranking_method='quickset'; converted adds verified_at/verified_via
      stamps (+ verified session); power has boards for all four positions
  (e) client_state per stage (exact dicts the mobile client adopts)
  (f) the minted session drives a real route (/api/tiers/save works)
  (g) DELETE refuses non-qa_ ids (400); qa_ delete removes users +
      swipe_decisions rows and evicts the live session
  (h) session-user allowlist path (no device header) also opens the gate

Harness pattern follows test_events_api.py: isolated in-memory SQLite with
db.engine patched, server.is_enabled patched, sessions cleaned up per test.
The allowlist reader (experiments.load_tester_allowlist) is env-driven, so
tests point FTF_TESTER_ALLOWLIST at a fake device and _ALLOWLIST_FILE at a
nonexistent path.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.experiments as ex
import backend.server as server
from backend.database import metadata, swipe_decisions_table, users_table

DEVICE = "qa-op-device-1"


def _flags_on(key):
    """testing.stage_users on; everything else off (incl. write enforcement)."""
    return key == "testing.stage_users"


@pytest.fixture()
def harness(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", f"device:{DEVICE}")
    monkeypatch.setattr(ex, "_ALLOWLIST_FILE", "/nonexistent/allow.json")

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    spawned_tokens: list[str] = []
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", _flags_on):
        try:
            yield client, engine, spawned_tokens
        finally:
            with server._sessions_lock:
                for t in spawned_tokens:
                    server._sessions.pop(t, None)


def _spawn(client, stage, device_id=DEVICE, token=None):
    h = {"Content-Type": "application/json"}
    if device_id is not None:
        h["X-Device-Id"] = device_id
    if token:
        h["X-Session-Token"] = token
    return client.post("/api/test-users", headers=h,
                       data=json.dumps({"stage": stage}))


def _spawn_ok(harness, stage):
    client, _, tokens = harness
    r = _spawn(client, stage)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    tokens.append(body["session_token"])
    return body


def _user_row(engine, user_id):
    with engine.begin() as conn:
        row = conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == user_id)).mappings().first()
    return row


# ── (a)/(b) gates ──────────────────────────────────────────────────────────

def test_flag_off_hides_routes(harness):
    client, _, _ = harness
    # Allowlist-only gate: flag off must NOT block an allowlisted caller.
    with patch.object(server, "is_enabled", lambda k: False):
        assert _spawn(client, "fresh").status_code == 200
        assert client.delete("/api/test-users/qa_dead",
                             headers={"X-Device-Id": DEVICE}).status_code != 404


def test_not_allowlisted_404(harness):
    client, _, _ = harness
    assert _spawn(client, "fresh", device_id="stranger-device").status_code == 404
    assert _spawn(client, "fresh", device_id=None).status_code == 404
    assert client.delete("/api/test-users/qa_dead",
                         headers={"X-Device-Id": "stranger-device"}).status_code == 404


def test_session_user_allowlist_path(harness, monkeypatch):
    """No device header, but the session's user_id is allowlisted → allowed."""
    client, _, tokens = harness
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "matt_user_id")
    with server._sessions_lock:
        server._sessions["tu-op-token"] = {"user_id": "matt_user_id",
                                           "last_active": 0.0}
    tokens.append("tu-op-token")
    r = _spawn(client, "fresh", device_id=None, token="tu-op-token")
    assert r.status_code == 200
    tokens.append(r.get_json()["session_token"])


def test_invalid_stage_400(harness):
    client, _, _ = harness
    r = _spawn(client, "whale")
    assert r.status_code == 400
    assert "stages" in r.get_json()


# ── (c) session shape ──────────────────────────────────────────────────────

def test_spawn_fresh_session_shape(harness):
    body = _spawn_ok(harness, "fresh")
    assert body["user_id"].startswith("qa_")
    assert body["username"].startswith("qa_fresh_")
    assert body["league_id"] == "league_demo"
    assert body["league_name"] == "The Demo League"
    assert body["stage"] == "fresh"
    assert body["client_state"] == {}

    with server._sessions_lock:
        sess = server._sessions[body["session_token"]]
    # Initialized-session shape (league + players + trade services), and
    # indistinguishable from a real signed-in session: NO is_demo key.
    for key in ("league", "players", "user_roster", "services", "service",
                "trade_svcs", "trade_svc", "active_format", "display_name"):
        assert key in sess, key
    assert "is_demo" not in sess
    assert sess["user_id"] == body["user_id"]

    # users row persisted (unlike demo sessions); no boards, no verification
    row = _user_row(harness[1], body["user_id"])
    assert row is not None and row["username"] == body["username"]
    assert row["ranking_method"] is None
    assert row["verified_at"] is None


# ── (d)/(e) stage seeding + client_state ───────────────────────────────────

def test_activated_client_only(harness):
    body = _spawn_ok(harness, "activated")
    assert body["client_state"] == {
        "firstSwipeDone": True, "totalSwipes": 5, "sessionCount": 1}
    row = _user_row(harness[1], body["user_id"])
    assert row["tier_overrides"] is None      # nothing extra server-side
    assert row["verified_at"] is None


def test_board_owner_persists_wr_quickset(harness):
    body = _spawn_ok(harness, "board_owner")
    cs = body["client_state"]
    assert cs["quicksetCompletedPositions"] == ["WR"]
    assert cs["quicksetPromptShows"] == 1
    assert cs["guideSeen"] == {k: True for k in
                               ("s0.1", "s0.2", "s1.1", "s2.1", "s2.2",
                                "s2.3", "s3.1", "s4.1")}

    row = _user_row(harness[1], body["user_id"])
    assert row["ranking_method"] == "quickset"
    assert json.loads(row["tiers_saved"])["1qb_ppr"] == ["WR"]
    overrides = json.loads(row["tier_overrides"])["1qb_ppr"]
    assert len(overrides) == 10                       # full demo WR pool
    assert all(pid.startswith("wr_") for pid in overrides)
    # Tier shape: exactly 2 players in the firsts_2 band (floor 1788)
    assert sum(1 for elo in overrides.values() if elo >= 1788) == 2
    assert row["verified_at"] is None                 # not converted yet

    # The live session's service carries the same overrides (no replay needed)
    with server._sessions_lock:
        sess = server._sessions[body["session_token"]]
    assert set(sess["services"]["1qb_ppr"]._elo_overrides) == set(overrides)


def test_converted_has_verification_stamps(harness):
    body = _spawn_ok(harness, "converted")
    cs = body["client_state"]
    assert cs["applePromptShownFor"] == {"like": True, "quickset_save": True}
    assert cs["celebrationsShown"] == {"first_like": True,
                                       "first_quickset_save": True}
    assert cs["guideSeen"]["s6.1"] is True and cs["guideSeen"]["s6.2"] is True
    assert cs["quicksetCompletedPositions"] == ["WR"]

    row = _user_row(harness[1], body["user_id"])
    assert row["verified_at"] is not None
    assert row["verified_via"] == "apple"
    assert json.loads(row["tiers_saved"])["1qb_ppr"] == ["WR"]
    # Session marked verified so the P2.5 read gate doesn't lock the user out
    with server._sessions_lock:
        sess = server._sessions[body["session_token"]]
    assert sess.get("verified") is True and sess.get("verified_via") == "apple"
    # Honest response: deep account flows are not simulated
    assert any("no accounts row" in n for n in body["notes"])


def test_power_has_all_four_boards(harness):
    body = _spawn_ok(harness, "power")
    cs = body["client_state"]
    assert cs["quicksetCompletedPositions"] == ["QB", "RB", "WR", "TE"]
    assert cs["guideTourCompleted"] is True
    assert cs["guideSeen"]["s8.1"] is True

    row = _user_row(harness[1], body["user_id"])
    assert set(json.loads(row["tiers_saved"])["1qb_ppr"]) == {"QB", "RB", "WR", "TE"}
    overrides = json.loads(row["tier_overrides"])["1qb_ppr"]
    prefixes = {pid.split("_")[0] for pid in overrides}
    assert prefixes == {"qb", "rb", "wr", "te"}
    assert row["verified_via"] == "apple"


# ── (f) the minted session drives real routes ──────────────────────────────

def test_session_works_for_tiers_save(harness):
    client, engine, _ = harness
    body = _spawn_ok(harness, "fresh")
    r = client.post("/api/tiers/save",
                    headers={"X-Session-Token": body["session_token"],
                             "Content-Type": "application/json"},
                    data=json.dumps({"position": "QB",
                                     "tiers": {"first_1": ["qb_1", "qb_3"]}}))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["saved"] == ["QB"]
    row = _user_row(engine, body["user_id"])
    assert json.loads(row["tiers_saved"])["1qb_ppr"] == ["QB"]


# ── (g) deletion ───────────────────────────────────────────────────────────

def test_delete_refuses_non_qa(harness):
    client, _, _ = harness
    r = client.delete("/api/test-users/real_sleeper_123",
                      headers={"X-Device-Id": DEVICE})
    assert r.status_code == 400
    assert r.get_json()["error"] == "not_a_test_user"


def test_delete_removes_rows_and_evicts_session(harness):
    client, engine, _ = harness
    body = _spawn_ok(harness, "board_owner")
    uid, token = body["user_id"], body["session_token"]

    # Simulate live usage having written a swipe row for this user
    with engine.begin() as conn:
        conn.execute(insert(swipe_decisions_table).values(
            user_id=uid, winner_player_id="wr_1", loser_player_id="wr_2",
            decision_type="rank", k_factor=32.0))

    r = client.delete(f"/api/test-users/{uid}",
                      headers={"X-Device-Id": DEVICE})
    assert r.status_code == 200
    deleted = r.get_json()["deleted"]
    assert deleted["users"] == 1
    assert deleted["swipe_decisions"] == 1
    assert deleted["sessions_evicted"] == 1

    assert _user_row(engine, uid) is None
    with engine.begin() as conn:
        assert conn.execute(select(swipe_decisions_table).where(
            swipe_decisions_table.c.user_id == uid)).first() is None
    with server._sessions_lock:
        assert token not in server._sessions
