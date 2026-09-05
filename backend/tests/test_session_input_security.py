"""Security hardening: init identity, membership and roster authority.

All DBs are scratch; Sleeper responses are injected. Forged client profiles,
rosters, league names and co-owner aliases cannot affect the resolved input.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend import database as db
from backend.session_input import resolve_session_input, SessionInputError


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def upstream(url):
    if url.endswith('/rosters'):
        return [{"owner_id": "owner", "co_owners": ["caller"], "players": ["p1"]},
                {"owner_id": "opponent", "players": ["p2"]}]
    if url.endswith('/users'):
        return [{"user_id": "caller", "username": "Real Caller"},
                {"user_id": "owner", "display_name": "Real Owner"},
                {"user_id": "opponent", "display_name": "Real Opponent"}]
    return {"name": "Real League"}


def test_sleeper_snapshot_overrides_every_untrusted_field(engine):
    result = resolve_session_input({"user_id": "caller", "verified": True}, {
        "user_id": "caller", "league_id": "123", "league_name": "Forged League",
        "display_name": "Forged Caller", "username": "Forged Caller", "avatar": "forged",
        "league_user_id": "opponent", "league_display_name": "Forged Owner",
        "user_player_ids": ["stolen"], "opponent_rosters": [{"user_id": "victim"}],
    }, upstream)
    assert result["league_user_id"] == "owner"
    assert result["league_name"] == "Real League"
    assert result["league_display_name"] == "Real Owner"
    assert result["username"] == "Real Caller"
    assert result["avatar"] is None
    assert result["user_player_ids"] == ["p1"]
    assert result["opponent_rosters"] == [dict(user_id="opponent", username="Real Opponent", player_ids=["p2"])]


@pytest.mark.parametrize("sess, uid, error, status", [
    (None, "victim", "session_expired", 401),
    ({"user_id": "victim"}, "victim", "verification_required", 403),
    ({"user_id": "caller", "verified": True}, "victim", "identity_mismatch", 403),
    ({"user_id": "caller", "verified": True, "is_demo": True}, "caller", "verification_required", 403),
    ({"user_id": "caller", "verified": True}, None, "missing_user_id", 400),
])
def test_identity_rejected_before_any_data_read(engine, sess, uid, error, status):
    with pytest.raises(SessionInputError) as exc:
        resolve_session_input(sess, {"user_id": uid, "league_id": "123"},
                              lambda url: pytest.fail("network reached"))
    assert (exc.value.error, exc.value.status) == (error, status)


def test_sleeper_stranger_cannot_claim_roster(engine):
    with pytest.raises(SessionInputError, match="league_membership_required"):
        resolve_session_input({"user_id": "stranger", "verified": True},
                              {"user_id": "stranger", "league_id": "123", "league_user_id": "owner"}, upstream)


def test_upstream_failure_fails_closed(engine):
    with pytest.raises(SessionInputError) as exc:
        resolve_session_input({"user_id": "caller", "verified": True},
                              {"user_id": "caller", "league_id": "123"}, lambda url: None)
    assert exc.value.status == 503


@pytest.mark.parametrize("platform", ["espn", "mfl", "fleaflicker"])
def test_platform_snapshot_uses_imported_membership_and_rosters(engine, platform):
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="123", user_id="acct_caller", name="Imported", platform=platform))
    db.upsert_league_members("123", [dict(user_id="acct_caller", username="Caller", player_ids=["p1"]),
                                    dict(user_id="platform:other", username="Other", player_ids=["p2"])])
    body = {"user_id": "acct_caller", "league_id": "123", "user_player_ids": ["stolen"]}
    result = resolve_session_input({"user_id": "acct_caller", "verified": True}, body,
                                   lambda url: pytest.fail("Sleeper called for imported league"))
    assert result["platform"] == platform
    assert result["user_player_ids"] == ["p1"]
    assert result["opponent_rosters"][0]["player_ids"] == ["p2"]
    with pytest.raises(SessionInputError, match="league_membership_required"):
        resolve_session_input({"user_id": "stranger", "verified": True},
                              {"user_id": "stranger", "league_id": "123"}, upstream)


def test_verified_account_only_stays_empty(engine):
    result = resolve_session_input({"user_id": "acct_a", "verified": True, "account_only": True},
                                   {"user_id": "acct_a", "league_id": "no_league", "opponent_rosters": [{"user_id": "x"}]}, upstream)
    assert result["platform"] == "none"
    assert result["opponent_rosters"] == result["user_player_ids"] == []


def test_route_rejects_before_pool_or_writes(engine, monkeypatch):
    from backend import server
    monkeypatch.setattr(server, "_get_session", lambda token: {"user_id": "caller", "verified": True})
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: pytest.fail("pool reached"))
    monkeypatch.setattr(server, "_sleeper_get", upstream)
    response = server.app.test_client().post('/api/session/init', json={"user_id": "victim", "league_id": "123"})
    assert response.status_code == 403
    assert response.json["error"] == "identity_mismatch"
