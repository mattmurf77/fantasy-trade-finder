"""S0 / R10 — a failed Sleeper traded_picks read is "ownership unknown", never `[]`.

Before: `_fetch_sleeper_traded_picks` failed soft to `[]`. The owned-pick
REPLACE-sync wrote that as "every traded pick is back with its original team"
(a data-loss bug on main), and a pick-bearing send encoded as if nothing had
moved. Now the fetcher returns None on any failure and every caller treats
None as an error (head-eng ruling, 2026-10-23):

  • the owned-pick sync skips and keeps the stored picks (5xx, timeout, open
    circuit — direct and through session init); a successful `[]` still syncs
  • `/api/trades/propose` (and the overhaul send, which calls the same
    `_sleeper_propose_core`) refuses a pick-bearing send with the route's
    existing 502 `sleeper_write_failed` shape, before any GraphQL call
  • `/api/trades/validate` returns the existing "nothing checked" outcome
  • a send without picks is unaffected (the fetch is never made)

`_fetch_sleeper_drafts` keeps its documented D-089 fail-soft `[]` — untouched.
No network: the shipped cassette seam, a fake unguarded getter, mocks.
"""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.server as server
import backend.sleeper_http as sh
from backend.database import metadata
from backend.tests import test_roster_refresh_state as refresh
from backend.tests import test_sleeper_write_route as propose_t
from backend.tests import test_trade_send_validate as validate_t

LID = "1338231586314780672"
ROSTERS = [{"roster_id": 1, "owner_id": "u1", "players": ["p1"]},
           {"roster_id": 2, "owner_id": "u2", "players": ["p2"]}]
META = {"league_id": LID, "season": "2026", "total_rosters": 2,
        "settings": {"draft_rounds": 1}}
TRADED_URL = f"https://api.sleeper.app/v1/league/{LID}/traded_picks"


@pytest.fixture(autouse=True)
def _circuit():
    sh.reset()
    yield
    sh.reset()


@pytest.fixture()
def picks_db(monkeypatch, tmp_path):
    """In-memory DB holding one TRADED pick (roster 1's 2027 1st, now u2's)."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "_SLEEPER_FIXTURES_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_SLEEPER_RECORD", False)
    with engine.begin() as conn:
        conn.execute(insert(db_module.draft_picks_table).values(
            pick_id=f"{LID}_2027_1_1", league_id=LID, season=2027, round=1,
            owner_user_id="u2", original_roster_id="1", original_user_id="u1",
            is_traded=1, platform="sleeper"))

    def put(rel, doc):
        path = tmp_path / f"{rel}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))

    put(f"league/{LID}/drafts", [])
    yield put


def _picks():
    t = db_module.draft_picks_table
    with db_module.engine.connect() as conn:
        rows = conn.execute(select(t.c.pick_id, t.c.owner_user_id, t.c.is_traded)
                            .where(t.c.league_id == LID).order_by(t.c.pick_id)).all()
    return [tuple(r) for r in rows]


def _sync():
    return server._sync_sleeper_owned_picks(
        LID, {"u1": "A", "u2": "B"}, "1qb_ppr", rosters=ROSTERS, meta=META)


# ---------------------------------------------------------------------------
# The fetcher
# ---------------------------------------------------------------------------

def test_fetcher_none_on_failure_and_list_on_success(picks_db):
    put = picks_db
    put(f"league/{LID}/traded_picks", {"__http_error__": 502})
    assert server._fetch_sleeper_traded_picks(LID) is None
    put(f"league/{LID}/traded_picks", {"not": "a list"})
    assert server._fetch_sleeper_traded_picks(LID) is None
    put(f"league/{LID}/traded_picks", [])
    assert server._fetch_sleeper_traded_picks(LID) == []
    assert server._fetch_sleeper_traded_picks("mfl:synthetic:1") is None


def test_drafts_fetcher_keeps_its_fail_soft_empty_list(picks_db):
    put = picks_db
    put(f"league/{LID}/drafts", {"__http_error__": 502})
    assert server._fetch_sleeper_drafts(LID) == []          # D-089, untouched


# ---------------------------------------------------------------------------
# A failure keeps the existing picks
# ---------------------------------------------------------------------------

def _fail_5xx(put, monkeypatch):
    put(f"league/{LID}/traded_picks", {"__http_error__": 503})


def _fail_timeout(put, monkeypatch):
    real = server._sleeper_get_unguarded

    def fake(url, timeout=15):
        if url == TRADED_URL:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return real(url, timeout)

    monkeypatch.setattr(server, "_sleeper_get_unguarded", fake)


def _fail_circuit_open(put, monkeypatch):
    put(f"league/{LID}/traded_picks", [])          # would succeed if it were read
    sh.record_429("60")


@pytest.mark.parametrize("fail", [_fail_5xx, _fail_timeout, _fail_circuit_open],
                         ids=["5xx", "timeout", "circuit_open"])
def test_owned_pick_sync_failure_keeps_existing_picks(picks_db, monkeypatch, fail):
    before = _picks()
    fail(picks_db, monkeypatch)
    assert _sync() is None
    assert _picks() == before == [(f"{LID}_2027_1_1", "u2", 1)]


def test_successful_empty_traded_picks_still_replace_syncs(picks_db):
    picks_db(f"league/{LID}/traded_picks", [])
    assert _sync() is not None
    # A real answer of "nothing traded": the pick is back with its original team.
    assert (f"{LID}_2027_1_1", "u1", 0) in _picks()


def test_session_init_traded_picks_5xx_keeps_picks_and_marks_stale(refresh_harness):
    client, put = refresh_harness
    t = db_module.draft_picks_table
    with db_module.engine.begin() as conn:
        conn.execute(insert(t).values(
            pick_id=f"{refresh.LEAGUE_ID}_2027_1_1", league_id=refresh.LEAGUE_ID,
            season=2027, round=1, owner_user_id=refresh.OPP_ID, original_roster_id="1",
            original_user_id=refresh.USER_ID, is_traded=1, platform="sleeper"))
    put(f"league/{refresh.LEAGUE_ID}/traded_picks", {"__http_error__": 503})
    assert refresh._init(client).status_code == 200            # never blocks the init
    with db_module.engine.connect() as conn:
        rows = conn.execute(select(t.c.pick_id, t.c.owner_user_id)
                            .where(t.c.league_id == refresh.LEAGUE_ID)).all()
    assert [tuple(r) for r in rows] == [(f"{refresh.LEAGUE_ID}_2027_1_1", refresh.OPP_ID)]
    state = db_module.get_league_roster_state(refresh.LEAGUE_ID)
    assert (state["status"], state["last_error_code"]) == ("stale", "picks_unavailable")


@pytest.fixture()
def refresh_harness(monkeypatch, tmp_path):
    yield from refresh.harness.__wrapped__(monkeypatch, tmp_path)


# ---------------------------------------------------------------------------
# Sends refuse; validate reports nothing checked
# ---------------------------------------------------------------------------

@pytest.fixture()
def propose_client(monkeypatch):
    yield from propose_t.client.__wrapped__(monkeypatch)


def test_propose_with_picks_and_failed_fetch_refuses_before_graphql(propose_client):
    r, fake, _grid, traded = propose_t._propose(propose_client, propose_t.T3_BODY, traded=None)
    assert r.status_code == 502, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "sleeper_write_failed" and body["kind"] == "network"
    assert body["detail"] == body["message"] and "nothing was sent" in body["message"]
    traded.assert_called_once()
    fake.assert_not_called()                                    # no GraphQL propose


def test_propose_without_picks_is_unaffected(propose_client):
    r, fake, _grid, traded = propose_t._propose(
        propose_client, {"give_player_ids": ["100"], "receive_player_ids": ["200"]},
        traded=None)
    assert r.status_code == 200, r.get_data(as_text=True)
    traded.assert_not_called()                                  # the fetch never happens
    fake.assert_called_once()


@pytest.fixture()
def validate_client():
    yield from validate_t.client.__wrapped__()


def test_validate_with_picks_and_failed_fetch_reports_nothing_checked(validate_client):
    c, token = validate_client
    with patch.object(server, "_fetch_sleeper_traded_picks", lambda lid: None):
        r = validate_t._validate(c, token, give_player_ids=[validate_t.MY_2027_2ND])
    assert r.status_code == 200, r.get_data(as_text=True)
    # Never a false "pick_moved" from an empty overlay: the existing
    # unreachable outcome. The send itself is refused by propose (above).
    assert r.get_json() == {"ok": True, "checked": False, "warnings": []}


def test_validate_without_picks_is_unaffected(validate_client):
    c, token = validate_client
    traded = MagicMock(return_value=None)
    with patch.object(server, "_fetch_sleeper_traded_picks", traded):
        r = validate_t._validate(c, token)
    assert r.get_json()["checked"] is True
    traded.assert_not_called()
