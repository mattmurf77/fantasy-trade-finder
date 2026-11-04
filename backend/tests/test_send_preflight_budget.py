"""Send pre-flight budget (release-lead QA P1-A on #527, 2026-10-28).

The iOS client most likely gives up on a request after ~60 s idle, and the
propose routes send no bytes until the provider write ends. MFL's pre-flight
alone can reach ~60 s (crosswalk + host + two I-2 reads). Invariant: a
provider write never starts so late that it can finish after the client gave
up. `_mfl_propose_core` / `_espn_propose_core` read `server._send_clock` at
entry and, immediately before the write, skip it once more than
`_SEND_PREFLIGHT_BUDGET_S` has passed, answering their existing "nothing was
sent" read-failure 502 (`mfl_unavailable` / `espn_unavailable`, I-2's R3
copy) instead.

No network and no real time: the clock is injected and advanced by the mocked
pre-flight read, and the write adapter is a mock.
"""
import itertools
import logging
from unittest.mock import MagicMock

import pytest

import backend.espn_service as espn_service
import backend.espn_write as espn_write
import backend.mfl_service as mfl_service
import backend.mfl_write as mfl_write
import backend.server as server
from backend import overhaul_store as store
from backend.tests import test_espn_propose_route as espn_t
from backend.tests import test_i2_mfl_ownership as i2_mfl
from backend.tests import test_mfl_propose_route as mfl_t
from backend.tests import test_overhaul_api as ovh_t

BUDGET = server._SEND_PREFLIGHT_BUDGET_S
IOS_IDLE_TIMEOUT_S = 60

# I-2 / platforms-pm R3 copy (backend/ownership_copy.py), word for word, curly ’.
MFL_R3 = "Couldn’t confirm rosters with MFL right now, so nothing was sent. Try again in a moment."
ESPN_R3 = "Couldn’t confirm rosters with ESPN right now, so nothing was sent. Try again in a moment."


def test_a_write_started_inside_the_budget_ends_before_the_ios_timeout():
    assert BUDGET + mfl_write._HTTP_TIMEOUT + mfl_write._REQUEST_SPACING_SECONDS < IOS_IDLE_TIMEOUT_S
    assert BUDGET + espn_write._HTTP_TIMEOUT < IOS_IDLE_TIMEOUT_S


@pytest.fixture()
def clock(monkeypatch):
    """A fake `_send_clock`; `clock[0] += s` is `s` seconds passing."""
    now = [1000.0]
    monkeypatch.setattr(server, "_send_clock", lambda: now[0])
    return now


def _slow(now, seconds, result):
    def read(*a, **kw):
        now[0] += seconds
        return result
    return read


def _budget_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "trade_finder" and r.levelno == logging.WARNING
            and "send budget" in r.getMessage()]


# ---------------------------------------------------------------------------
# POST /api/trades/propose-mfl
# ---------------------------------------------------------------------------

@pytest.fixture()
def mfl_client(monkeypatch):
    yield from mfl_t.client.__wrapped__(monkeypatch)


def _post_mfl(mfl_client, monkeypatch, clock, preflight_s):
    c, token = mfl_client
    # The fixture's live rosters read is the slow pre-flight step.
    mfl_service.fetch_rosters.side_effect = _slow(clock, preflight_s, mfl_t._ROSTERS_EXPORT)
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    monkeypatch.setattr(mfl_write, "propose_trade", fake)
    return c.post("/api/trades/propose-mfl", headers=mfl_t._h(token),
                  data=mfl_t._propose_body()), fake


def test_mfl_preflight_past_the_budget_sends_nothing(mfl_client, monkeypatch, clock, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r, fake = _post_mfl(mfl_client, monkeypatch, clock, BUDGET + 0.01)
    assert r.status_code == 502
    assert r.get_json() == {"error": "mfl_unavailable", "kind": "network",
                            "detail": MFL_R3, "message": MFL_R3}
    fake.assert_not_called()                      # the write never started
    assert mfl_t._trade_sent_rows() == []
    assert _budget_lines(caplog) == [
        f"mfl propose: pre-flight took {BUDGET:.1f}s, past the {BUDGET}s send budget; nothing sent"]


def test_mfl_preflight_inside_the_budget_writes(mfl_client, monkeypatch, clock, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r, fake = _post_mfl(mfl_client, monkeypatch, clock, BUDGET - 0.01)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "proposed"
    fake.assert_called_once()
    assert _budget_lines(caplog) == []


# ---------------------------------------------------------------------------
# POST /api/trades/propose-espn
# ---------------------------------------------------------------------------

@pytest.fixture()
def espn_client(monkeypatch):
    yield from espn_t.client.__wrapped__(monkeypatch)


def _post_espn(espn_client, monkeypatch, clock, preflight_s):
    c, token = espn_client
    # The fixture's live league read is the slow pre-flight step.
    espn_service.fetch_league.side_effect = _slow(clock, preflight_s, espn_t.RAW_LEAGUE)
    fake = MagicMock(return_value={"transaction_id": "tx", "status": "PENDING", "raw": {}})
    monkeypatch.setattr(espn_write, "propose_trade", fake)
    return c.post("/api/trades/propose-espn", headers=espn_t._h(token),
                  data=espn_t._propose_body()), fake


def test_espn_preflight_past_the_budget_sends_nothing(espn_client, monkeypatch, clock, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r, fake = _post_espn(espn_client, monkeypatch, clock, BUDGET + 0.01)
    assert r.status_code == 502
    assert r.get_json() == {"error": "espn_unavailable", "kind": "network",
                            "detail": ESPN_R3, "message": ESPN_R3}
    fake.assert_not_called()
    assert espn_t._trade_sent_rows() == []
    assert _budget_lines(caplog) == [
        f"espn propose: pre-flight took {BUDGET:.1f}s, past the {BUDGET}s send budget; nothing sent"]


def test_espn_preflight_inside_the_budget_writes(espn_client, monkeypatch, clock, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    r, fake = _post_espn(espn_client, monkeypatch, clock, BUDGET - 0.01)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "proposed"
    fake.assert_called_once()
    assert _budget_lines(caplog) == []


# ---------------------------------------------------------------------------
# Team overhaul: send_core → the REAL _mfl_propose_core, one budget per offer
# ---------------------------------------------------------------------------

@pytest.fixture()
def mfl_overhaul(monkeypatch):
    yield from i2_mfl.overhaul.__wrapped__(monkeypatch)


def test_overhaul_offer_past_the_budget_is_send_failed_not_unknown(mfl_overhaul, monkeypatch):
    """Nothing was sent, so each refused offer is `send_failed` with the R3
    copy and its reservation is released; never `outcome_unknown`."""
    c, world, live, fake, mfl_id = mfl_overhaul
    fid_of = {ovh_t.USER: "0001", **{i2_mfl._syn(f): f for f in i2_mfl.CP.values()}}
    live["rosters"] = {"rosters": {"franchise": [
        {"id": fid_of[owner], "player": [{"id": mfl_id[p]} for p in roster]}
        for owner, roster in world.rosters.items()]}}
    ticks = itertools.count(0, BUDGET + 1)        # every clock read is 31 s later
    monkeypatch.setattr(server, "_send_clock", lambda: next(ticks))
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "budget-mfl"})
    assert r.status_code == 200, r.get_json()
    attempts = r.get_json()["attempts"]
    assert [a["state"] for a in attempts] == ["send_failed"] * 5
    assert {a["error"]["code"] for a in attempts} == {"mfl_unavailable"}
    assert {a["error"]["message"] for a in attempts} == {MFL_R3}
    assert store.active_reservations(i2_mfl.LEAGUE, ovh_t.USER) == []
    fake.assert_not_called()
