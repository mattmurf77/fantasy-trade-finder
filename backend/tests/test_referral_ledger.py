"""Referral loop L7 — the referral ledger's server side.

Spec: docs/plans/referral-loop/prd.md @ 91f1cc29 (FR-6, FR-13–FR-20, FR-23,
§7, §8.1, §8.4, §9), the event grant PR #350 (C1–C9) and engagement-eng's L7
design §2 (D-056 evidence). What is pinned here:

  * the mint, POST /api/invite/token: flag AND knob gating (either off →
    404), the knob read per request (a DB flip lands with no restart),
    auth / demo / unverified, membership, the surface set, the 10-per-day
    rate limit with retry_after_s, the 12-char id, no URL;

Every test runs against a throwaway SQLite file, never data/trade_finder.db.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert, select, update

import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.referral_ledger as rl
import backend.server as server
from backend.database import (
    league_members_table, metadata, model_config_table, referrals_table,
    users_table,
)

LEAGUE = "990000000000000001"
OTHER_LEAGUE = "990000000000000002"
REFERRER = "u_referrer_1"
REFERRER_USERNAME = "mattref"
TOKEN = "sess-referrer-token"
LEDGER = "growth.referral_ledger"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """A throwaway DB, the ledger flag ON (tests turn it off explicitly), no
    Sleeper egress, and one verified referrer session in LEAGUE."""
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    _set_flags(monkeypatch, LEDGER)
    server.app.config["TESTING"] = True
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=REFERRER, username=REFERRER_USERNAME,
            display_name="Matt R", last_active_at="2026-01-01T00:00:00+00:00",
            events_count=5))
    _session(monkeypatch, TOKEN, REFERRER, league=LEAGUE)
    return engine


def _set_flags(monkeypatch, *enabled):
    on = set(enabled)
    monkeypatch.setattr(server, "is_enabled", lambda k: k in on)
    monkeypatch.setattr(feature_flags, "is_enabled", lambda k: k in on)


def _session(monkeypatch, token, user_id, *, league, verified=True, **extra):
    sess = {"user_id": user_id, "verified": verified, "active_format": "1qb_ppr",
            "league": SimpleNamespace(league_id=league), **extra}
    monkeypatch.setitem(server._sessions, token, sess)
    return sess


def _client():
    return server.app.test_client()


def _mint(token=TOKEN, **body):
    payload = {"league_id": LEAGUE, "surface": "league_home", **body}
    return _client().post("/api/invite/token", json=payload,
                          headers={"X-Session-Token": token} if token else {})


def _rows(engine, table=referrals_table):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(table).order_by(table.c.id))]


def _set_knob(engine, value):
    with engine.begin() as conn:
        n = conn.execute(update(model_config_table)
                         .where(model_config_table.c.key == "referral_mint_enabled")
                         .values(value=value)).rowcount
        if not n:
            conn.execute(insert(model_config_table).values(
                key="referral_mint_enabled", value=value, description="test"))


# ═══════════════════════════════════════════════════════════════════════════
# The mint — POST /api/invite/token (§8.1, FR-1 server half, FR-6)
# ═══════════════════════════════════════════════════════════════════════════

def test_mint_201_shape_and_row(env):
    r = _mint()
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert set(body) == {"invite_id", "league_id", "expires_at"}   # never a URL
    assert len(body["invite_id"]) == 12
    assert server.INVITE_ID_RE.fullmatch(body["invite_id"])
    assert body["league_id"] == LEAGUE
    (row,) = _rows(env)
    assert row["invite_token"] == row["share_token"] == body["invite_id"]
    assert (row["referrer_user_id"], row["league_id"], row["status"], row["surface"]) == (
        REFERRER, LEAGUE, "pending", "league_home")
    assert row["referred_user_id"] is None and row["attribution_method"] is None
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires - datetime.fromisoformat(row["created_at"]) == timedelta(days=30)
    assert "http" not in r.get_data(as_text=True) and "/app/" not in r.get_data(as_text=True)


def test_mint_ids_are_unique(env):
    ids = {_mint().get_json()["invite_id"] for _ in range(5)}
    assert len(ids) == 5


@pytest.mark.parametrize("flags,knob", [((), 1.0), ((LEDGER,), 0.0), ((), 0.0),
                                        ((LEDGER,), 2.0)])
def test_mint_gated_on_flag_and_knob(env, monkeypatch, flags, knob):
    _set_flags(monkeypatch, *flags)
    _set_knob(env, knob)
    r = _mint()
    assert r.status_code == 404 and r.get_json() == {"error": "not_found"}
    assert _rows(env) == []


def test_mint_gate_is_checked_before_auth(env, monkeypatch):
    """A dark route answers every caller the same 404, even with no session."""
    _set_flags(monkeypatch)
    assert _mint(token=None).status_code == 404
    _set_knob(env, 0.0)
    _set_flags(monkeypatch, LEDGER)
    assert _mint(token="no-such-session").status_code == 404


def test_knob_is_read_per_request_no_restart(env):
    """A DB flip (scripts/set_knob.py --local writes exactly this) lands on
    the very next request: no reload_config, no restart."""
    _set_knob(env, 0.0)
    assert _mint().status_code == 404
    _set_knob(env, 1.0)
    assert _mint().status_code == 201
    _set_knob(env, 0.0)
    assert _mint().status_code == 404
    assert len(_rows(env)) == 1


def test_knob_is_seeded_on(env):
    assert ("referral_mint_enabled", 1.0) in [
        row[:2] for row in db_module._MODEL_CONFIG_DEFAULTS]
    assert server._referral_mint_enabled() is True       # empty table → default


def test_mint_requires_a_session():
    r = _mint(token="no-such-session")
    assert r.status_code == 401 and r.get_json()["error"] == "session_expired"


@pytest.mark.parametrize("extra", [{"verified": False}, {"is_demo": True}])
def test_mint_refuses_unverified_and_demo(env, monkeypatch, extra):
    _session(monkeypatch, "t2", "u_other", league=LEAGUE, **extra)
    r = _mint(token="t2")
    assert r.status_code == 403 and r.get_json()["error"] == "verification_required"
    assert _rows(env) == []


def test_mint_refuses_a_demo_user_id(env, monkeypatch):
    _session(monkeypatch, "t3", "demo_user_7", league=LEAGUE)
    assert _mint(token="t3").get_json()["error"] == "verification_required"


@pytest.mark.parametrize("body,err", [
    ({"league_id": None}, "missing_league_id"),
    ({"league_id": "  "}, "missing_league_id"),
    ({"league_id": 123}, "missing_league_id"),
    ({"surface": "invite_card"}, "invalid_surface"),      # a retired name
    ({"surface": None}, "invalid_surface"),
    ({"surface": "LEAGUE_HOME"}, "invalid_surface"),
])
def test_mint_validates_the_body(env, body, err):
    r = _mint(**body)
    assert r.status_code == 400 and r.get_json()["error"] == err
    assert _rows(env) == []


@pytest.mark.parametrize("surface", sorted(rl.INVITE_SURFACES))
def test_mint_accepts_every_surface(env, surface):
    assert _mint(surface=surface).status_code == 201
    assert _rows(env)[-1]["surface"] == surface


def test_surface_set_is_the_prd_set():
    assert rl.INVITE_SURFACES == {"league_home", "matches_empty", "trades_banner",
                                  "members_overlay", "notif_empty", "web_invite"}


def test_mint_membership_other_league_via_league_members(env):
    """Not the session's league: the league_members snapshot decides."""
    r = _mint(league_id=OTHER_LEAGUE)
    assert r.status_code == 403 and r.get_json()["error"] == "not_member"
    with env.begin() as conn:
        conn.execute(insert(league_members_table).values(
            league_id=OTHER_LEAGUE, user_id=REFERRER, username="m",
            display_name="m", roster_data="[]", updated_at="2026-10-24"))
    assert _mint(league_id=OTHER_LEAGUE).status_code == 201


def test_mint_rate_limit_ten_per_league_per_utc_day(env):
    for _ in range(rl.MINT_DAILY_CAP):
        assert _mint().status_code == 201
    r = _mint()
    assert r.status_code == 429
    body = r.get_json()
    assert body["error"] == "rate_limited"
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert 0 < body["retry_after_s"] <= int((midnight - now).total_seconds()) + 1
    assert len(_rows(env)) == rl.MINT_DAILY_CAP
    # Per league: another league the referrer is in still mints.
    with env.begin() as conn:
        conn.execute(insert(league_members_table).values(
            league_id=OTHER_LEAGUE, user_id=REFERRER, username="m",
            display_name="m", roster_data="[]", updated_at="2026-10-24"))
    assert _mint(league_id=OTHER_LEAGUE).status_code == 201


def test_mint_rate_limit_resets_the_next_utc_day(env):
    """Yesterday's ten don't count today (AC-6)."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0).isoformat()
    with env.begin() as conn:
        for i in range(rl.MINT_DAILY_CAP):
            tok = f"yesterday{i:03d}"
            conn.execute(insert(referrals_table).values(
                referrer_user_id=REFERRER, league_id=LEAGUE, invite_token=tok,
                share_token=tok, status="pending", created_at=yesterday))
    assert _mint().status_code == 201


def test_mint_rate_limit_ignores_sibling_rows(env):
    """Group-chat siblings are joins, not mints (invite_token != share_token)."""
    now = datetime.now(timezone.utc).isoformat()
    with env.begin() as conn:
        for i in range(rl.MINT_DAILY_CAP):
            conn.execute(insert(referrals_table).values(
                referrer_user_id=REFERRER, referred_user_id=f"u_sib_{i}",
                league_id=LEAGUE, invite_token=f"parent123456~s{i:05d}",
                share_token="parent123456", status="joined", created_at=now))
    assert _mint().status_code == 201
