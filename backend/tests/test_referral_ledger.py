"""Referral loop L7 — the referral ledger's server side.

Spec: docs/plans/referral-loop/prd.md @ 91f1cc29 (FR-6, FR-13–FR-20, FR-23,
§7, §8.1, §8.4, §9), the event grant PR #350 (C1–C9) and engagement-eng's L7
design §2 (D-056 evidence). What is pinned here:

  * the mint, POST /api/invite/token: flag AND knob gating (either off →
    404), the knob read per request (a DB flip lands with no restart),
    auth / demo / unverified, membership, the surface set, the 10-per-day
    rate limit with retry_after_s, the 12-char id, no URL;
  * attribution at a new user's first session (AC-13 … AC-16): credit by
    token for Sleeper / ESPN / MFL invitees, unknown / expired ids, a
    non-member, a group-chat sibling, an existing user, a repeat init; the
    league-match fallback and its tie-breaks; legacy `ref` never credits or
    notifies; the `signup` props on every case;
  * FR-18 (one join row, title != body) and FR-20 (the fanout skips only
    the credited inviter's coalesced row), end to end through
    POST /api/session/init with an inline daemon;
  * referral_attributed: exact props at the writer, NON_INTENT, no token
    key, no invitee id, and the non-touching write (C6);
  * activation (AC-17, AC-19, R-F7): the stage-7 set IS FUNNEL_STAGES[7];
    a first opinion stamps once from each of the three emitters (the swipe
    route, the calculator queue, the reasoned pass); outside 14 days, a
    second opinion, trades_generated and the flag off do nothing; the hook
    never raises and reads nothing when it can't matter; the FR-19 row
    (title != body, no deck promise, meta) merges into an unread join row;
    referral_activated's exact props and C6;

Every test runs against a throwaway SQLite file, never data/trade_finder.db.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert, select, update

import backend.analytics_queries as aq
import backend.analytics_taxonomy as at
import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.referral_ledger as rl
import backend.server as server
from backend.database import (
    league_members_table, metadata, model_config_table, notifications_table,
    referrals_table, user_events_table, users_table,
)

LEAGUE = "990000000000000001"
OTHER_LEAGUE = "990000000000000002"
REFERRER = "u_referrer_1"
REFERRER_USERNAME = "mattref"
TOKEN = "sess-referrer-token"
LEDGER = "growth.referral_ledger"
_REAL_IS_ENABLED = feature_flags.is_enabled     # captured before any patch


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


# ═══════════════════════════════════════════════════════════════════════════
# Attribution — attribute_first_session (§7.4, §7.5, FR-13 … FR-16, FR-18)
# ═══════════════════════════════════════════════════════════════════════════

INVITEE = "u_invitee_1"
PEER = "u_peer_1"
T1 = "AbCdEf123456"
T2 = "ZyXwVu987654"
ESPN_LEAGUE = "77001"
MFL_LEAGUE = "mfl:2026:55001"
ATTRIBUTED_KEYS = {"invite_id", "referral_id", "league_id", "attribution_method",
                   "league_platform", "notified"}


def _iso_ago(days=0, hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def _mint_row(engine, tok, *, referrer=REFERRER, league=LEAGUE, age_days=1,
              opened_days=None, status="pending", referred=None,
              surface="league_home", share=True):
    with engine.begin() as conn:
        return conn.execute(insert(referrals_table).values(
            referrer_user_id=referrer, referred_user_id=referred, league_id=league,
            invite_token=tok, share_token=tok if share else None, status=status,
            surface=surface, created_at=_iso_ago(age_days),
            opened_at=None if opened_days is None else _iso_ago(opened_days),
        )).inserted_primary_key[0]


def _add_user(engine, uid, username, **extra):
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=uid, username=username, display_name=username.title(),
            last_active_at="2026-01-01T00:00:00+00:00", events_count=5, **extra))


def _add_member(engine, league, uid):
    with engine.begin() as conn:
        conn.execute(insert(league_members_table).values(
            league_id=league, user_id=uid, username=uid, display_name=uid,
            roster_data="[]", updated_at="2026-10-24"))


def _platform_league(engine, league, platform, members):
    with engine.begin() as conn:
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id=league, user_id=members[0], name="Imported",
            platform=platform))
    for uid in members:
        _add_member(engine, league, uid)


@pytest.fixture()
def writer(monkeypatch):
    """Spy on the writer every ledger event goes through."""
    captured = []
    real = db_module.record_event

    def _spy(user_id, event_type, **kw):
        captured.append((user_id, event_type, kw))
        return real(user_id, event_type, **kw)
    monkeypatch.setattr(db_module, "record_event", _spy)
    return captured


def _attr(**kw):
    args = dict(is_new_user=True, user_id=INVITEE, league_id=LEAGUE,
                league_platform="sleeper", invite_id=None, invited_by=None,
                new_username="newbie")
    args.update(kw)
    return rl.attribute_first_session(**args)


def _events(engine, name):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(user_events_table).where(user_events_table.c.event_type == name)
            .order_by(user_events_table.c.id))]


def _notifs(engine, uid=REFERRER):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(notifications_table).where(notifications_table.c.user_id == uid)
            .order_by(notifications_table.c.id))]


def _user(engine, uid=REFERRER):
    with engine.connect() as conn:
        row = conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == uid)).fetchone()
    return dict(row._mapping) if row else None


def _captured(captured, name):
    return [(uid, kw) for uid, n, kw in captured if n == name]


# ── AC-13: credit by token ────────────────────────────────────────────────

def test_token_credits_a_sleeper_invitee(env, writer):
    rid = _mint_row(env, T1)
    res = _attr(invite_id=T1, invited_by="someone_else")
    (row,) = _rows(env)
    assert row["id"] == rid
    assert (row["referred_user_id"], row["status"], row["attribution_method"]) == (
        INVITEE, "joined", "token")
    assert row["joined_at"] is not None
    # FR-13 step 5: invited_by is the REFERRER's username, server-derived,
    # never the client's value.
    assert res.invited_by == REFERRER_USERNAME
    assert res.signup_props == {"attribution": "token", "attribution_miss": None}
    assert res.inviter_user_id == REFERRER and res.legacy_notify is False
    ((owner, kw),) = _captured(writer, "referral_attributed")
    assert owner == REFERRER
    assert kw["props"] == {"invite_id": T1, "referral_id": rid, "league_id": LEAGUE,
                           "attribution_method": "token", "league_platform": "sleeper",
                           "notified": True}
    assert kw["platform"] == "server" and kw["touch_user"] is False


@pytest.mark.parametrize("platform,league", [("espn", ESPN_LEAGUE), ("mfl", MFL_LEAGUE)])
def test_token_credits_platform_invitees_in_the_session_league(env, writer, platform, league):
    """ESPN / MFL: the session league is the row's league, so
    resolve_session_input already proved membership."""
    _platform_league(env, league, platform, [REFERRER, INVITEE])
    rid = _mint_row(env, T1, league=league)
    res = _attr(invite_id=T1, league_id=league, league_platform=platform)
    assert res.signup_props["attribution"] == "token"
    ((_, kw),) = _captured(writer, "referral_attributed")
    assert kw["props"]["league_platform"] == platform
    assert kw["props"]["league_id"] == league and kw["props"]["referral_id"] == rid


def test_token_credits_a_member_of_another_league_via_league_members(env, writer):
    """§7.4 step 3: the id's league is not the session's league; the
    league_members snapshot proves membership, and league_platform is the
    id's league's platform, not the session's."""
    _platform_league(env, MFL_LEAGUE, "mfl", [REFERRER, INVITEE])
    _mint_row(env, T1, league=MFL_LEAGUE)
    res = _attr(invite_id=T1, league_id=LEAGUE, league_platform="sleeper")
    assert res.signup_props == {"attribution": "token", "attribution_miss": None}
    ((_, kw),) = _captured(writer, "referral_attributed")
    assert kw["props"]["league_platform"] == "mfl"
    assert kw["props"]["league_id"] == MFL_LEAGUE


def test_token_non_member_is_a_miss(env, writer):
    _platform_league(env, MFL_LEAGUE, "mfl", [REFERRER])          # invitee absent
    _mint_row(env, T1, league=MFL_LEAGUE)
    res = _attr(invite_id=T1, league_id=LEAGUE)
    assert res.signup_props == {"attribution": "none", "attribution_miss": "not_member"}
    assert _rows(env)[0]["referred_user_id"] is None
    assert _captured(writer, "referral_attributed") == [] and _notifs(env) == []


@pytest.mark.parametrize("setup,miss", [
    ("unknown", "unknown"), ("expired", "expired"), ("deleted_referrer", "unknown"),
])
def test_token_misses(env, writer, setup, miss):
    if setup == "expired":
        _mint_row(env, T1, age_days=31)
    elif setup == "deleted_referrer":
        _mint_row(env, T1, share=False)          # FR-23 NULLs share_token
    res = _attr(invite_id=T1)
    assert res.signup_props == {"attribution": "none", "attribution_miss": miss}
    assert res.invited_by is None and res.inviter_user_id is None
    assert all(r["referred_user_id"] is None for r in _rows(env))
    assert _captured(writer, "referral_attributed") == [] and _notifs(env) == []


def test_miss_with_legacy_ref_reports_legacy_ref(env):
    res = _attr(invite_id=T1, invited_by="whoever")
    assert res.signup_props == {"attribution": "legacy_ref", "attribution_miss": "unknown"}
    assert res.invited_by == "whoever"          # stored unverified (FR-15)


def test_group_chat_second_joiner_gets_a_sibling_row(env, writer):
    """§7.6: one link, many joiners. The minted row holds the first; the
    second gets a sibling with the parent's share_token and its own
    never-emitted invite_token."""
    parent = _mint_row(env, T1, surface="trades_banner")
    _attr(invite_id=T1, user_id="u_first")
    res = _attr(invite_id=T1, user_id=INVITEE)
    rows = _rows(env)
    assert len(rows) == 2
    sib = rows[1]
    assert sib["share_token"] == T1 and sib["invite_token"].startswith(T1 + "~")
    assert len(sib["invite_token"]) == len(T1) + 7
    assert not server.INVITE_ID_RE.fullmatch(sib["invite_token"])
    assert (sib["referrer_user_id"], sib["league_id"], sib["status"],
            sib["attribution_method"], sib["surface"], sib["created_at"]) == (
        REFERRER, LEAGUE, "joined", "token", "trades_banner", rows[0]["created_at"])
    assert sib["referred_user_id"] == INVITEE
    assert res.signup_props == {"attribution": "token", "attribution_miss": None}
    second = _captured(writer, "referral_attributed")[1][1]["props"]
    assert second["invite_id"] == T1 and second["referral_id"] == sib["id"] != parent
    assert sib["invite_token"] not in json.dumps(_events(env, "referral_attributed"),
                                                 default=str)


def test_existing_user_is_never_credited(env, writer):
    _mint_row(env, T1)
    res = _attr(invite_id=T1, is_new_user=False, invited_by="x")
    assert res == rl.FirstSession("x", None, None, False)
    assert _rows(env)[0]["referred_user_id"] is None
    assert writer == [] and _notifs(env) == []


def test_repeat_first_session_is_idempotent(env, writer):
    """A second 'first' init (the users INSERT failed after the credit)
    credits and notifies nothing again, but reports the credit."""
    _mint_row(env, T1)
    first = _attr(invite_id=T1)
    again = _attr(invite_id=T1)
    assert again == first
    assert len(_rows(env)) == 1
    assert len(_captured(writer, "referral_attributed")) == 1 and len(_notifs(env)) == 1


def test_a_referred_user_is_credited_at_most_once(env):
    _add_user(env, "u_ref2", "reftwo")
    _mint_row(env, T1)
    _mint_row(env, T2, referrer="u_ref2")
    _attr(invite_id=T1)
    _attr(invite_id=T2)
    credited = [r for r in _rows(env) if r["referred_user_id"] == INVITEE]
    assert len(credited) == 1 and credited[0]["share_token"] == T1


def test_flag_off_is_todays_behaviour(env, monkeypatch, writer):
    _set_flags(monkeypatch)
    _mint_row(env, T1, opened_days=1)
    res = _attr(invite_id=T1, invited_by="legacy")
    assert res == rl.FirstSession("legacy", None, None, True)
    assert _rows(env)[0]["referred_user_id"] is None
    assert writer == [] and _notifs(env) == []


def test_attribution_never_raises(env, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_module, "get_referral_for_referred", _boom)
    res = _attr(invite_id=T1, invited_by="legacy")
    assert res == rl.FirstSession("legacy", None, None, False)


def test_referrer_users_row_never_moves(env):
    """C6: the inviter did nothing; their last_active_at / events_count stay."""
    before = _user(env)
    _mint_row(env, T1)
    _attr(invite_id=T1)
    assert _events(env, "referral_attributed")
    after = _user(env)
    assert (after["last_active_at"], after["events_count"]) == (
        before["last_active_at"], before["events_count"]) == (
        "2026-01-01T00:00:00+00:00", 5)


# ── AC-14: league-match fallback ──────────────────────────────────────────

def test_league_match_takes_the_most_recent_open(env, writer):
    _add_user(env, "u_ref2", "reftwo")
    _mint_row(env, T1, opened_days=3)
    newer = _mint_row(env, T2, referrer="u_ref2", opened_days=1)
    res = _attr()
    assert res.signup_props == {"attribution": "league_match", "attribution_miss": None}
    row = next(r for r in _rows(env) if r["id"] == newer)
    assert (row["referred_user_id"], row["status"], row["attribution_method"]) == (
        INVITEE, "joined", "league_match")
    assert res.invited_by == "reftwo" and res.inviter_user_id == "u_ref2"
    ((owner, kw),) = _captured(writer, "referral_attributed")
    assert owner == "u_ref2" and kw["props"]["attribution_method"] == "league_match"
    assert kw["props"]["invite_id"] == T2


def test_league_match_legacy_ref_breaks_the_tie(env):
    _add_user(env, "u_ref2", "RefTwo")
    older = _mint_row(env, T1, referrer="u_ref2", opened_days=5)
    _mint_row(env, T2, opened_days=1)
    res = _attr(invited_by="reftwo")       # case-insensitive, like today
    credited = next(r for r in _rows(env) if r["referred_user_id"] == INVITEE)
    assert credited["id"] == older and res.inviter_user_id == "u_ref2"
    assert res.signup_props["attribution"] == "league_match"


def test_league_match_after_a_token_miss_keeps_the_miss(env):
    _mint_row(env, T2, opened_days=1)
    res = _attr(invite_id=T1)              # unknown id, then the fallback
    assert res.signup_props == {"attribution": "league_match",
                                "attribution_miss": "unknown"}


@pytest.mark.parametrize("kw", [
    {"opened_days": 15},                    # opened > 14 d ago
    {"opened_days": None},                  # never opened
    {"opened_days": 1, "age_days": 31},     # minted > 30 d ago
    {"opened_days": 1, "status": "joined", "referred": "u_x"},
    {"opened_days": 1, "referrer": INVITEE},
    {"opened_days": 1, "league": OTHER_LEAGUE},
    {"opened_days": 1, "share": False},     # not a minted row
])
def test_league_match_never_takes(env, writer, kw):
    _mint_row(env, T2, **kw)
    res = _attr()
    assert res.signup_props == {"attribution": "none", "attribution_miss": None}
    assert _captured(writer, "referral_attributed") == []


# ── AC-15: legacy ref never credits or notifies ───────────────────────────

def test_legacy_ref_alone_credits_and_notifies_no_one(env, writer):
    res = _attr(invited_by=REFERRER_USERNAME)
    assert res == rl.FirstSession(
        REFERRER_USERNAME, {"attribution": "legacy_ref", "attribution_miss": None},
        None, False)
    assert _rows(env) == [] and writer == [] and _notifs(env) == []


# ── FR-18: the join row ───────────────────────────────────────────────────

def test_join_row_title_differs_from_body(env):
    rid = _mint_row(env, T1)
    _attr(invite_id=T1, new_username="newbie")
    (n,) = _notifs(env)
    assert n["type"] == "referral_joined"
    assert n["title"] == "@newbie joined Fleeced via your invite"
    assert n["body"] == ("Once they rank, trades with them can use their board, "
                         "not just consensus.")
    assert n["title"] != n["body"]
    assert json.loads(n["metadata_json"]) == {
        "new_user_id": INVITEE, "new_username": "newbie", "league_id": LEAGUE,
        "referral_id": rid}


def test_notified_false_when_the_row_fails(env, monkeypatch, writer):
    def _boom(**kw):
        raise RuntimeError("inbox down")
    monkeypatch.setattr(db_module, "create_notification", _boom)
    _mint_row(env, T1)
    res = _attr(invite_id=T1)
    assert res.signup_props["attribution"] == "token"
    assert _captured(writer, "referral_attributed")[0][1]["props"]["notified"] is False


# ── #350 registration (C7): referral_attributed ───────────────────────────
# Shaped like test_analytics_taxonomy_referral_loop.py's _SERVER_PROPS (L1
# created that file after this branch's base); these move there on rebase.

def test_referral_attributed_is_registered_server_fired_non_intent():
    name = "referral_attributed"
    assert name in at.SERVER_FIRED_EVENTS and name not in at.ALLOWED_CLIENT_EVENTS
    assert name not in at.CLIENT_EVENT_PROPS
    assert name in aq.NON_INTENT_EVENTS and name not in aq.INTENT_EVENTS
    assert "signup" in aq.INTENT_EVENTS                       # class unchanged


def test_referral_attributed_props_are_exactly_the_grant(env, writer):
    _mint_row(env, T1)
    _attr(invite_id=T1)
    ((_, kw),) = _captured(writer, "referral_attributed")
    assert set(kw["props"]) == ATTRIBUTED_KEYS
    assert not any("token" in k for k in kw["props"])          # C1
    assert "referred_user_id" not in kw["props"]               # C2
    assert INVITEE not in json.dumps(kw["props"])              # C2: no invitee id
    assert "platform" not in kw["props"]                       # the column says 'server'
    (row,) = _events(env, "referral_attributed")
    assert row["platform"] == "server" and row["user_id"] == REFERRER


# ═══════════════════════════════════════════════════════════════════════════
# End to end: POST /api/session/init with an inline daemon (G1 call line,
# FR-13 step 5 on the INSERT, FR-15, FR-16, FR-18, FR-20)
# ═══════════════════════════════════════════════════════════════════════════
# Modelled on test_session_init_sleeper_calls.py's harness. LEAGUE is a
# Sleeper league of three: the invitee (new, initializing), the REFERRER and
# a PEER, both existing users already in league_members.

INVITEE_TOKEN = "sess-invitee-token"


@pytest.fixture()
def init_env(env, monkeypatch):
    from unittest.mock import MagicMock

    import backend.sleeper_trades_service as trades_service
    import backend.suggestion_telemetry as sugg_tel
    import backend.trade_block_service as tb_service
    from backend.ranking_service import Player

    rosters = [{"roster_id": i + 1, "owner_id": uid, "co_owners": None,
                "players": [f"p{i + 1}"], "starters": [f"p{i + 1}"]}
               for i, uid in enumerate((INVITEE, REFERRER, PEER))]
    meta = {"league_id": LEAGUE, "name": "Lakeview Dynasty", "season": "2026",
            "total_rosters": 3, "roster_positions": ["QB", "RB", "WR", "TE", "BN"],
            "scoring_settings": {"rec": 1.0}, "settings": {"draft_rounds": 3}}
    users = [{"user_id": INVITEE, "username": "newbie", "display_name": "newbie"},
             {"user_id": REFERRER, "username": REFERRER_USERNAME},
             {"user_id": PEER, "username": "peer"}]

    def _fake_sleeper_get(url, timeout=15):
        tail = url.split("/v1/league/")[-1]
        if tail == LEAGUE:
            return dict(meta)
        if tail == f"{LEAGUE}/users":
            return [dict(u) for u in users]
        if tail == f"{LEAGUE}/rosters":
            return [dict(r) for r in rosters]
        return []

    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper_get)
    monkeypatch.setattr(tb_service, "_fetch_rosters",
                        lambda league_id, *, _opener=None, timeout=15: [dict(r) for r in rosters])
    monkeypatch.setattr(tb_service, "fetch_league_players",
                        lambda league_id, *, _opener=None, timeout=15: [])
    monkeypatch.setattr(trades_service, "fetch_week_transactions",
                        lambda lid, week, *, _opener=None, timeout=15: [])
    monkeypatch.setattr(sugg_tel, "fetch_league_roster_map",
                        lambda league_id, *, _opener=None, timeout=15:
                        {str(r["roster_id"]): r["owner_id"] for r in rosters})
    monkeypatch.setattr(server, "_refresh_league_draft_status",
                        lambda league_id, force=False: None)
    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2, 3)]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep":  {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    pushes = []
    monkeypatch.setattr(server, "_send_typed_push",
                        lambda uid, kind, **kw: pushes.append((uid, kind)))

    real_thread = server.threading.Thread

    class _InlineBgThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineBgThread)
    _add_user(env, PEER, "peer")
    for uid in (REFERRER, PEER):
        _add_member(env, LEAGUE, uid)
    monkeypatch.setitem(server._sessions, INVITEE_TOKEN,
                        {"user_id": INVITEE, "verified": True})
    return pushes


def _init(**extra):
    r = _client().post("/api/session/init", headers={"X-Session-Token": INVITEE_TOKEN},
                       json={**extra, "user_id": INVITEE, "league_id": LEAGUE})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r


def _signup_props(engine):
    (row,) = _events(engine, "signup")
    return json.loads(row["props"]) if row["props"] else None


def test_e2e_token_credit(env, init_env):
    _mint_row(env, T1)
    _init(invite_id=T1, invited_by="spoofed_name")
    # FR-13 step 5: the referrer's username lands on the INSERT.
    assert _user(env, INVITEE)["invited_by"] == REFERRER_USERNAME
    # FR-16 on the signup row.
    assert _signup_props(env) == {"attribution": "token", "attribution_miss": None}
    (row,) = _rows(env)
    assert row["referred_user_id"] == INVITEE and row["status"] == "joined"
    # FR-18 + FR-20 (AC-18, AC-20): exactly ONE bell row for the inviter
    # about this join, title != body; the peer's coalesced row is unchanged.
    (n,) = _notifs(env, REFERRER)
    assert n["type"] == "referral_joined" and n["title"] != n["body"]
    assert "Fantasy Trade Finder" not in n["title"]
    (peer_row,) = _notifs(env, PEER)
    assert peer_row["type"] == "league_member_joined"
    # The inviter's per-pair push is kept (FR-20 skips the inbox row only).
    assert (REFERRER, "league_member_joined") in init_env
    assert (PEER, "league_member_joined") in init_env
    assert len(_events(env, "referral_attributed")) == 1


def test_e2e_repeat_init_is_idempotent(env, init_env):
    _mint_row(env, T1)
    _init(invite_id=T1)
    _init(invite_id=T1)                      # now an existing user: app_open
    assert len(_rows(env)) == 1 and len(_notifs(env, REFERRER)) == 1
    assert len(_events(env, "referral_attributed")) == 1
    (app_open,) = _events(env, "app_open")
    assert app_open["props"] is None


def test_e2e_league_match(env, init_env):
    _mint_row(env, T1, opened_days=2)
    _init()
    assert _signup_props(env) == {"attribution": "league_match", "attribution_miss": None}
    assert _user(env, INVITEE)["invited_by"] == REFERRER_USERNAME
    assert [n["type"] for n in _notifs(env, REFERRER)] == ["referral_joined"]


def test_e2e_legacy_ref_alone_notifies_no_one(env, init_env):
    """AC-15 with the flag ON: no ledger row and no bell row for the named
    user; invited_by is still stored, unverified."""
    _init(invited_by=REFERRER_USERNAME)
    assert _rows(env) == []
    assert _user(env, INVITEE)["invited_by"] == REFERRER_USERNAME
    assert _signup_props(env) == {"attribution": "legacy_ref", "attribution_miss": None}
    assert [n["type"] for n in _notifs(env, REFERRER)] == ["league_member_joined"]


def test_e2e_unattributed_no_ref(env, init_env):
    _init(invite_id="not a valid id!")       # malformed → ignored (§8.4)
    assert _signup_props(env) == {"attribution": "none", "attribution_miss": None}
    assert _user(env, INVITEE)["invited_by"] is None


def test_e2e_flag_off_is_byte_identical_to_today(env, init_env, monkeypatch):
    _set_flags(monkeypatch)
    _mint_row(env, T1, opened_days=1)
    _init(invite_id=T1, invited_by=REFERRER_USERNAME)
    assert _rows(env)[0]["referred_user_id"] is None
    assert _user(env, INVITEE)["invited_by"] == REFERRER_USERNAME
    assert _signup_props(env) is None
    # Today's legacy row (title = body) plus today's coalesced row.
    types = sorted(n["type"] for n in _notifs(env, REFERRER))
    assert types == ["league_member_joined", "referral_joined"]
    legacy = next(n for n in _notifs(env, REFERRER) if n["type"] == "referral_joined")
    assert legacy["title"] == legacy["body"] == (
        "@newbie joined Fantasy Trade Finder via your invite.")
    assert _events(env, "referral_attributed") == []


# ═══════════════════════════════════════════════════════════════════════════
# Activation — maybe_activate_referral (FR-17, FR-19, R-F7; AC-17, AC-19)
# ═══════════════════════════════════════════════════════════════════════════

ACTIVATED_KEYS = {"invite_id", "referral_id", "league_id", "days_to_activate", "notified"}


def _joined_row(engine, *, tok=T1, referrer=REFERRER, referred=INVITEE,
                league=LEAGUE, joined_days=2, status="joined"):
    with engine.begin() as conn:
        return conn.execute(insert(referrals_table).values(
            referrer_user_id=referrer, referred_user_id=referred, league_id=league,
            invite_token=tok, share_token=tok, status=status, surface="league_home",
            created_at=_iso_ago(joined_days + 1), joined_at=_iso_ago(joined_days, hours=1),
            attribution_method="token",
        )).inserted_primary_key[0]


def _set_read(engine, notif_id, *, read=True, dismissed=False):
    with engine.begin() as conn:
        conn.execute(update(notifications_table)
                     .where(notifications_table.c.id == notif_id)
                     .values(is_read=1 if read else 0,
                             dismissed_at=_iso_ago() if dismissed else None))


def test_stage7_set_is_read_from_funnel_stages():
    """C5 / R3: the qualifying set IS stage 7 of FUNNEL_STAGES."""
    (stage7,) = [events for n, _name, events in aq.FUNNEL_STAGES if n == 7]
    assert rl.STAGE7_EVENTS == frozenset(stage7)
    assert rl.STAGE7_EVENTS == {"trade_proposed", "match_swiped"}     # today
    (stage6,) = [events for n, _name, events in aq.FUNNEL_STAGES if n == 6]
    assert not rl.STAGE7_EVENTS & set(stage6)                         # trades_generated


@pytest.mark.parametrize("event", ["trade_proposed", "match_swiped"])
def test_first_opinion_activates_once(env, writer, event):
    rid = _joined_row(env, joined_days=2)
    _add_user(env, INVITEE, "newbie")
    rl.maybe_activate_referral(INVITEE, event)
    (row,) = _rows(env)
    assert (row["status"], row["qualifying_event"]) == ("activated", event)
    assert row["activated_at"] is not None
    ((owner, kw),) = _captured(writer, "referral_activated")
    assert owner == REFERRER
    assert kw["props"] == {"invite_id": T1, "referral_id": rid, "league_id": LEAGUE,
                           "days_to_activate": 2, "notified": True}
    assert kw["platform"] == "server" and kw["touch_user"] is False
    # A second opinion is a no-op.
    rl.maybe_activate_referral(INVITEE, "match_swiped")
    assert len(_captured(writer, "referral_activated")) == 1
    assert _rows(env)[0]["qualifying_event"] == event
    assert len(_notifs(env)) == 1


def test_outside_fourteen_days_does_nothing(env, writer):
    _joined_row(env, joined_days=15)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert _rows(env)[0]["status"] == "joined"
    assert writer == [] and _notifs(env) == []


def test_day_fourteen_still_activates(env, writer):
    with env.begin() as conn:
        conn.execute(insert(referrals_table).values(
            referrer_user_id=REFERRER, referred_user_id=INVITEE, league_id=LEAGUE,
            invite_token=T1, share_token=T1, status="joined",
            created_at=_iso_ago(20), joined_at=_iso_ago(13, hours=23)))
    rl.maybe_activate_referral(INVITEE, "match_swiped")
    assert _captured(writer, "referral_activated")[0][1]["props"]["days_to_activate"] == 13


@pytest.mark.parametrize("event", ["trades_generated", "trio_swipe", "signup",
                                   "ranking_complete_first_time", "match_viewed"])
def test_non_stage7_events_never_activate(env, writer, event):
    """Including a replenish deck: trades_generated never activates, whoever
    (or whatever cron) fired it."""
    _joined_row(env)
    rl.maybe_activate_referral(INVITEE, event)
    assert _rows(env)[0]["status"] == "joined" and writer == []


def test_flag_off_does_nothing(env, monkeypatch, writer):
    _set_flags(monkeypatch)
    _joined_row(env)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert _rows(env)[0]["status"] == "joined" and writer == []


def test_short_circuits_before_any_read(env, monkeypatch):
    """Cheap: a non-stage-7 name or the flag off never reads the DB."""
    calls = []
    monkeypatch.setattr(db_module, "get_referral_for_referred",
                        lambda *a, **k: calls.append(a) or None)
    rl.maybe_activate_referral(INVITEE, "trades_generated")
    _set_flags(monkeypatch)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert calls == []
    _set_flags(monkeypatch, LEDGER)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert calls == [(INVITEE,)]                     # one read when it can matter


def test_non_referred_and_already_activated_users_are_no_ops(env, writer):
    rl.maybe_activate_referral("u_nobody", "trade_proposed")
    _joined_row(env, status="activated")
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert writer == [] and _notifs(env) == []


def test_activation_never_raises(env, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_module, "get_referral_for_referred", _boom)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")         # no exception


def test_activation_never_moves_the_referrer(env):
    """C6 for referral_activated."""
    _joined_row(env)
    before = _user(env)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert _events(env, "referral_activated")
    after = _user(env)
    assert (after["last_active_at"], after["events_count"]) == (
        before["last_active_at"], before["events_count"])


# ── FR-19 + R-F7: the activation row ──────────────────────────────────────

ACT_TITLE = "@newbie weighed in on their first trade"
ACT_BODY = "When they like a trade with you, it can show up with a \"They're interested\" tag."


def _credit_then_join_row(env):
    """A real FR-18 join row via attribution; returns its notification id."""
    _mint_row(env, T1)
    _add_user(env, INVITEE, "newbie")
    _attr(invite_id=T1)
    (n,) = _notifs(env)
    return n["id"]


def test_activation_row_posts_separately_once_the_join_row_is_read(env):
    join_id = _credit_then_join_row(env)
    _set_read(env, join_id)
    rl.maybe_activate_referral(INVITEE, "match_swiped")
    rows = _notifs(env)
    assert [n["type"] for n in rows] == ["referral_joined", "referral_activated"]
    act = rows[1]
    assert (act["title"], act["body"]) == (ACT_TITLE, ACT_BODY)
    assert act["title"] != act["body"]
    assert "deck" not in act["body"].lower()
    meta = json.loads(act["metadata_json"])
    assert meta["new_username"] == "newbie" and meta["league_id"] == LEAGUE
    assert meta["new_user_id"] == INVITEE


def test_rf7_merges_into_an_unread_join_row(env, writer):
    """ux-lead R-F7: one person, one row, with the activation title."""
    join_id = _credit_then_join_row(env)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    (row,) = _notifs(env)
    assert row["id"] == join_id
    assert (row["type"], row["title"], row["body"], row["is_read"]) == (
        "referral_activated", ACT_TITLE, ACT_BODY, 0)
    meta = json.loads(row["metadata_json"])
    assert meta["new_username"] == "newbie" and meta["league_id"] == LEAGUE
    assert _captured(writer, "referral_activated")[0][1]["props"]["notified"] is True


def test_rf7_never_merges_into_a_dismissed_join_row(env):
    join_id = _credit_then_join_row(env)
    _set_read(env, join_id, read=False, dismissed=True)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert [n["type"] for n in _notifs(env)] == ["referral_joined", "referral_activated"]


def test_activation_row_failure_reports_notified_false(env, monkeypatch, writer):
    _joined_row(env)

    def _boom(**kw):
        raise RuntimeError("inbox down")
    monkeypatch.setattr(db_module, "create_notification", _boom)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    assert _rows(env)[0]["status"] == "activated"
    assert _captured(writer, "referral_activated")[0][1]["props"]["notified"] is False


# ── #350 registration (C7): referral_activated ────────────────────────────

def test_referral_activated_is_registered_server_fired_non_intent():
    name = "referral_activated"
    assert name in at.SERVER_FIRED_EVENTS and name not in at.ALLOWED_CLIENT_EVENTS
    assert name not in at.CLIENT_EVENT_PROPS
    assert name in aq.NON_INTENT_EVENTS and name not in aq.INTENT_EVENTS


def test_referral_activated_props_are_exactly_the_grant(env, writer):
    _joined_row(env)
    rl.maybe_activate_referral(INVITEE, "trade_proposed")
    ((_, kw),) = _captured(writer, "referral_activated")
    assert set(kw["props"]) == ACTIVATED_KEYS
    assert not any("token" in k for k in kw["props"])
    assert INVITEE not in json.dumps(kw["props"])
    assert isinstance(kw["props"]["days_to_activate"], int)
    (row,) = _events(env, "referral_activated")
    assert row["platform"] == "server" and row["user_id"] == REFERRER


# ── AC-17: each of the three stage-7 emitters stamps once (G2) ────────────

def _real_flags_plus_ledger(monkeypatch):
    """The emitter routes read real flags; only the ledger is forced on."""
    monkeypatch.setattr(server, "is_enabled", _REAL_IS_ENABLED)
    monkeypatch.setattr(feature_flags, "is_enabled",
                        lambda k: k == LEDGER or _REAL_IS_ENABLED(k))


def test_swipe_route_like_and_pass_activate(env, monkeypatch):
    from unittest.mock import MagicMock

    from backend.ranking_service import Player, RankingService
    from backend.trade_service import League, LeagueMember, TradeService
    _real_flags_plus_ledger(monkeypatch)
    players = [Player(id=p, name=p.upper(), position="RB", team="AAA", age=25)
               for p in ("g1", "r1")]
    service = RankingService(players=players)
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(league_id=LEAGUE, name="L", platform="sleeper", members=[
        LeagueMember(user_id=INVITEE, username="me", roster=[], elo_ratings={}),
        LeagueMember(user_id=REFERRER, username="ref", roster=[], elo_ratings={})])
    monkeypatch.setitem(server._sessions, "swipe-tok", {
        "verified": True, "user_id": INVITEE, "league": league, "players": players,
        "services": {"1qb_ppr": service}, "service": service,
        "trade_svcs": {"1qb_ppr": trade_svc}, "trade_svc": trade_svc,
        "active_format": "1qb_ppr", "last_active": 0.0})
    monkeypatch.setattr(server, "save_trade_swipes", MagicMock())
    monkeypatch.setattr(server, "create_notification", MagicMock())
    _joined_row(env)
    for i, decision in enumerate(("pass", "like")):
        r = _client().post("/api/trades/swipe", headers={"X-Session-Token": "swipe-tok"},
                           json={"trade_id": f"stale{i}", "decision": decision,
                                 "league_id": LEAGUE, "give_player_ids": ["g1"],
                                 "receive_player_ids": ["r1"], "target_user_id": REFERRER,
                                 "target_username": "ref"})
        assert r.status_code == 200, r.get_data(as_text=True)
    (row,) = _rows(env)
    assert (row["status"], row["qualifying_event"]) == ("activated", "match_swiped")
    assert len(_events(env, "referral_activated")) == 1


def test_calculator_queue_activates(env, monkeypatch):
    from backend.tests import test_calc_trade_queue as cq
    gen = cq._harness_ctx(caller_in_members=False)
    client, engine, *_ = next(gen)
    try:
        _real_flags_plus_ledger(monkeypatch)
        _joined_row(engine, referred=cq.ME, league=cq.LEAGUE, referrer=cq.OPP)
        r = cq._queue(client)
        assert r.status_code == 200, r.get_data(as_text=True)
        (row,) = _rows(engine)
        assert (row["status"], row["qualifying_event"]) == ("activated", "trade_proposed")
        assert len(_events(engine, "referral_activated")) == 1
    finally:
        gen.close()


def test_reasoned_pass_activates(env, monkeypatch):
    _joined_row(env)
    card = SimpleNamespace(league_id=LEAGUE, trade_id="t1", give_player_ids=["g1"],
                           receive_player_ids=["r1"], target_user_id=REFERRER)
    with server.app.test_request_context():
        server._apply_reasoned_pass({"user_id": INVITEE}, card, {})
        server._apply_reasoned_pass({"user_id": INVITEE}, card, {})
    (row,) = _rows(env)
    assert (row["status"], row["qualifying_event"]) == ("activated", "match_swiped")
    assert len(_events(env, "referral_activated")) == 1


def test_emitter_call_lines_sit_after_each_stage7_emitter():
    """G2 structure: exactly three call lines, each right after a stage-7
    record_event, and nowhere near the Elo writers."""
    import inspect
    src = inspect.getsource(server)
    assert src.count("_referral_ledger.maybe_activate_referral(") == 3
    for fn, emitted in ((server.swipe_trade, '"trade_proposed" if decision'),
                        (server.queue_trade_for_opponent, '"trade_proposed",'),
                        (server._apply_reasoned_pass, '"match_swiped", league_id')):
        body = inspect.getsource(fn)
        assert body.count("maybe_activate_referral(") == 1, fn.__name__
        call = body.index("maybe_activate_referral(")
        assert call > body.index(emitted), fn.__name__          # after the emit
        if "save_trade_swipes(" in body:                         # after the Elo write
            assert call > body.index("save_trade_swipes("), fn.__name__
