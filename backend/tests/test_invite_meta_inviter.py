"""Referral loop FR-11 — `GET /api/league/invite-meta` names the inviter from `t`.

Spec: docs/plans/referral-loop/prd.md @ 91f1cc29 FR-11 / AC-11 and §8.3;
the event grant's C1 naming (`invite_status`, never `token_status`).

The route stays public, read-only and degrade-never-fail. What is pinned:

  * `t` absent → `invite_status` and `inviter_display_name` are null and the
    referrals table is never read;
  * a well-formed `t` resolves through the join landing's own helpers to one
    of valid | expired | unknown | league_mismatch;
  * the display name is returned ONLY for `valid` — never for an expired,
    mismatched or unknown id — and no username, user id or other row field
    ever reaches the response;
  * a malformed `t` is `unknown` with no DB read; a failed lookup degrades;
  * `league_name` keeps its Sleeper-public-API-only rule (test_invite_links
    T8–T11 keep the rest of the contract).

Every test runs against a throwaway SQLite file and never reaches Sleeper.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend.database import leagues_table, metadata, referrals_table, users_table

LEAGUE = "990000000000000001"
LEAGUE_NAME = "Lakeview Dynasty"
ESPN_LEAGUE = "424242"
REFERRER = "u_referrer_1"
REFERRER_USERNAME = "mattref"
REFERRER_NAME = "Matt R"
NAMELESS_REFERRER = "u_referrer_2"
T_VALID = "AbCdEf123456"
T_EXPIRED = "ExPiReD12345"
T_MISMATCH = "MiSmAtCh1234"
T_UNKNOWN = "UnKnOwN12345"
T_ESPN = "EsPnLeAgUe12"
T_NAMELESS = "NoNaMe123456"
KEYS = {"league_id", "league_name", "platform",
        "inviter_display_name", "invite_status"}


@pytest.fixture(autouse=True)
def engine(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'meta.db'}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(
        server, "_fetch_sleeper_league_meta",
        lambda lid: {"name": LEAGUE_NAME} if lid == LEAGUE else None)
    server.app.config["TESTING"] = True
    now = datetime.now(timezone.utc)
    with eng.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=REFERRER, username=REFERRER_USERNAME,
            display_name=REFERRER_NAME))
        conn.execute(insert(users_table).values(
            sleeper_user_id=NAMELESS_REFERRER, username="nonameuser",
            display_name=None))
        conn.execute(insert(leagues_table).values(
            sleeper_league_id=ESPN_LEAGUE, user_id=REFERRER,
            name="Private ESPN League", season="2026", total_rosters=12,
            platform="espn"))
        for tok, referrer, league, age in (
                (T_VALID, REFERRER, LEAGUE, 1),
                (T_EXPIRED, REFERRER, LEAGUE, 31),
                (T_MISMATCH, REFERRER, "555555", 1),
                (T_ESPN, REFERRER, ESPN_LEAGUE, 1),
                (T_NAMELESS, NAMELESS_REFERRER, LEAGUE, 1)):
            conn.execute(insert(referrals_table).values(
                referrer_user_id=referrer, league_id=league,
                invite_token=tok, status="pending",
                created_at=(now - timedelta(days=age)).isoformat()))
    return eng


def _meta(query):
    r = server.app.test_client().get("/api/league/invite-meta?" + query)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert set(body) == KEYS          # nothing else from the row, ever
    return body, r.get_data(as_text=True)


def _no_db_read(monkeypatch):
    def _boom(_t):
        raise AssertionError("referrals must not be read")
    monkeypatch.setattr(db_module, "get_referral_by_invite_token", _boom)


def test_without_t_both_fields_are_null_and_no_lookup(monkeypatch):
    _no_db_read(monkeypatch)
    body, _ = _meta(f"league_id={LEAGUE}")
    assert body["invite_status"] is None
    assert body["inviter_display_name"] is None
    assert body["league_name"] == LEAGUE_NAME


def test_empty_t_reads_as_absent(monkeypatch):
    _no_db_read(monkeypatch)
    body, _ = _meta(f"league_id={LEAGUE}&t=")
    assert body["invite_status"] is None and body["inviter_display_name"] is None


def test_valid_t_names_the_inviter():
    body, _ = _meta(f"league_id={LEAGUE}&t={T_VALID}")
    assert body == {"league_id": LEAGUE, "league_name": LEAGUE_NAME,
                    "platform": "sleeper",
                    "inviter_display_name": REFERRER_NAME,
                    "invite_status": "valid"}


@pytest.mark.parametrize("tok,league,status", [
    (T_EXPIRED, LEAGUE, "expired"),
    (T_MISMATCH, LEAGUE, "league_mismatch"),
    (T_VALID, "555555", "league_mismatch"),     # a valid id in another league's path
    (T_UNKNOWN, LEAGUE, "unknown"),
])
def test_only_a_valid_id_ever_names_anyone(tok, league, status):
    body, text = _meta(f"league_id={league}&t={tok}")
    assert body["invite_status"] == status
    assert body["inviter_display_name"] is None
    assert REFERRER_NAME not in text


@pytest.mark.parametrize("raw", ["short", "has%20space", "bad!chars12",
                                 "a" * 65, "AbCdEf123456%0A",
                                 "AbCdEf123456~x1y2z3"])
def test_malformed_t_is_unknown_without_a_db_read(monkeypatch, raw):
    _no_db_read(monkeypatch)
    body, _ = _meta(f"league_id={LEAGUE}&t={raw}")
    assert body["invite_status"] == "unknown"
    assert body["inviter_display_name"] is None


def test_no_username_user_id_or_token_leaks():
    """The referrer's username and user id never reach the response; the only
    name is users.display_name, and only for a valid id."""
    for tok in (T_VALID, T_EXPIRED, T_MISMATCH, T_UNKNOWN, T_NAMELESS):
        _, text = _meta(f"league_id={LEAGUE}&t={tok}")
        assert REFERRER_USERNAME not in text
        assert "nonameuser" not in text
        assert REFERRER not in text and NAMELESS_REFERRER not in text
        assert "token" not in text


def test_valid_id_without_a_display_name_is_null_not_a_username():
    body, _ = _meta(f"league_id={LEAGUE}&t={T_NAMELESS}")
    assert body["invite_status"] == "valid"
    assert body["inviter_display_name"] is None


def test_league_name_rule_is_unchanged_by_a_valid_id():
    """An imported ESPN league's name lives only in our DB: a valid `t` names
    the inviter but never unlocks the league name (D-10 not taken)."""
    body, text = _meta(f"league_id={ESPN_LEAGUE}&t={T_ESPN}")
    assert body["invite_status"] == "valid"
    assert body["inviter_display_name"] == REFERRER_NAME
    assert body["league_name"] is None and body["platform"] is None
    assert "Private ESPN League" not in text


def test_lookup_failure_degrades_to_unknown(monkeypatch):
    def _boom(_t):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_module, "get_referral_by_invite_token", _boom)
    body, _ = _meta(f"league_id={LEAGUE}&t={T_VALID}")
    assert body["invite_status"] == "unknown"
    assert body["inviter_display_name"] is None
    assert body["league_name"] == LEAGUE_NAME


def test_status_helper_failure_degrades_to_unknown(monkeypatch):
    def _boom(_r, _l):
        raise TypeError("bad row")
    monkeypatch.setattr(server, "_invite_status", _boom)
    body, _ = _meta(f"league_id={LEAGUE}&t={T_VALID}")
    assert body["invite_status"] == "unknown"
    assert body["inviter_display_name"] is None


def test_league_id_still_required_with_t():
    r = server.app.test_client().get(f"/api/league/invite-meta?t={T_VALID}")
    assert r.status_code == 400
    assert r.get_json()["error"] == "missing_league_id"


def test_still_public_and_read_only(engine):
    """No session header; the route writes nothing (no open is recorded —
    that is the join path's FR-8 job, not this banner lookup's)."""
    from sqlalchemy import select
    before = [dict(r._mapping) for r in engine.connect().execute(
        select(referrals_table).order_by(referrals_table.c.id))]
    _meta(f"league_id={LEAGUE}&t={T_VALID}")
    after = [dict(r._mapping) for r in engine.connect().execute(
        select(referrals_table).order_by(referrals_table.c.id))]
    assert before == after
