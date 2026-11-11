"""Offer-learnings WS2b — the user's own Sleeper trade offers, read privately.

Scope block: docs/plans/offer-learnings/scope-sleeper-offer-read.md
Shape of Sleeper's answer: docs/plans/offer-learnings/sleeper-offers-read.md

No network. Every Sleeper answer is the synthetic fixture
`fixtures/sleeper/offer-read/league_transactions_filtered.json` (statuses
proposed / complete / rejected / cancelled, `metadata.rejecter_id`,
`settings.is_counter` / `expires_at`, user-id creators, synthetic ids),
served through an injected `_opener` or a patched `league_transactions_filtered`
call. Covers:

  * the client: one GraphQL read, trades only, no status filter, no
    `player_map`; auth and error classification as Send in Sleeper;
  * every status transition of an offer sent through the app, from the
    fixture: declined, withdrawn, lapsed, still sent, accepted, countered
    (counter declined / pending / accepted / countered back), and a counter
    outside the link window left unlinked;
  * counter linking by roster pair and time, one counter per offer;
  * consented import (sent and received, marked by source; three-team and
    other managers' trades skipped) and nothing imported without consent;
  * idempotence, final statuses never moved, per-user rows;
  * consent: grant, repeat, terms version, revoke deletes imports in the
    same transaction and keeps the app's rows, revoke with the flag off,
    verification, account-deletion coverage (parametrized elsewhere);
  * the server seams: flag off makes no call and spawns nothing; the
    throttle; a failed or unauthorised read changes nothing, backs off and
    logs once; the Find a Trade kick; the daily-tick step;
  * nothing stored carries the token, `metadata`, `settings` or a user id
    from the read.
"""
import io
import json
import logging
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db
import backend.server as server
import backend.sleeper_offer_read as sor
import backend.sleeper_write as sw
import backend.trade_outcomes as to
from backend.database import metadata

pytestmark = pytest.mark.usefixtures("no_real_network")

FIX = Path(__file__).resolve().parent / "fixtures/sleeper/offer-read"
ANSWER = json.loads((FIX / "league_transactions_filtered.json").read_text())
TXS = ANSWER["data"]["league_transactions_filtered"]
ROSTERS = json.loads((FIX / "rosters.json").read_text())
LEAGUE = "990000000000000007"
USER = "synthetic-account-1"
ME, THEM = "700000000000000001", "700000000000000002"
NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
TOKEN_SECRET = "synthetic.jwt.never-stored"


def tid(n):
    return f"14000000000000000{n:02d}"


APP_SENT = {1: "declined", 2: "withdrawn", 3: "lapsed", 4: "sent", 5: "accepted",
            6: "countered", 8: "countered", 10: "countered", 16: "declined", 18: "countered"}


@pytest.fixture(autouse=True)
def _reset():
    sor.reset_throttle()
    yield
    sor.reset_throttle()


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    yield eng
    eng.dispose()


def _send(n, user=USER):
    to.record_sent(user_id=user, league_id=LEAGUE, transaction_id=tid(n), my_roster_id=1,
                   their_roster_id=2, give_asset_ids=["x"], receive_asset_ids=["y"])


def _rows(user=None):
    t = db.trade_offer_outcomes_table
    with db.engine.connect() as conn:
        q = select(t).order_by(t.c.id)
        if user:
            q = q.where(t.c.user_id == user)
        return [dict(r._mapping) for r in conn.execute(q)]


def _by_tx(user=USER):
    return {r["provider_transaction_id"]: r for r in _rows(user)}


def _apply(import_on=False, txs=TXS, user=USER, now=NOW):
    return sor.apply_read(user_id=user, league_id=LEAGUE, txs=txs, my_roster_id=1,
                          me={ME}, import_on=import_on, now=now)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_read_is_one_trades_only_graphql_call_without_player_map():
    sent = []

    def opener(request, timeout=15):
        sent.append(request)
        return _Resp(json.dumps(ANSWER).encode())

    out = sw.league_trade_offers(TOKEN_SECRET, LEAGUE, _opener=opener)
    assert out == TXS and len(sent) == 1
    req = sent[0]
    body = json.loads(req.data)
    assert req.full_url == sw.SLEEPER_GRAPHQL_URL
    assert req.get_header("X-sleeper-graphql-op") == "league_transactions_filtered"
    assert req.get_header("Authorization") == TOKEN_SECRET          # raw, as propose
    assert body["operationName"] == "league_transactions_filtered"
    assert body["variables"] == {"league_id": LEAGUE, "type_filters": ["trade"], "limit": 200}
    q = body["query"]
    assert "status_filters" not in q and "player_map" not in q
    assert "roster_id_filters" not in q and "leg_filters" not in q
    for field in ("transaction_id", "status", "created", "status_updated", "creator",
                  "roster_ids", "consenter_ids", "adds", "drops", "draft_picks",
                  "waiver_budget", "metadata", "settings"):
        assert f"\n          {field}\n" in q, field


@pytest.mark.parametrize("answer,raises", [
    (urllib.error.HTTPError(sw.SLEEPER_GRAPHQL_URL, 401, "u", {}, io.BytesIO(b"")), sw.SleeperAuthError),
    ({"errors": [{"message": "Unauthorized"}]}, sw.SleeperAuthError),
    ({"errors": [{"message": "Something broke"}]}, sw.SleeperWriteError),
    ({"data": {"league_transactions_filtered": None}}, sw.SleeperWriteError),
])
def test_read_classifies_failures_like_send_in_sleeper(answer, raises):
    def opener(request, timeout=15):
        if isinstance(answer, Exception):
            raise answer
        return _Resp(json.dumps(answer).encode())

    with pytest.raises(raises):
        sw.league_trade_offers(TOKEN_SECRET, LEAGUE, _opener=opener)


def test_read_refuses_a_non_numeric_league_before_any_call():
    with pytest.raises(sw.SleeperWriteError):
        sw.league_trade_offers(TOKEN_SECRET, "league_demo", _opener=MagicMock(side_effect=AssertionError))


# ---------------------------------------------------------------------------
# Status transitions of offers sent through the app
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", sorted(APP_SENT.items()))
def test_each_app_sent_offer_moves_to_what_sleeper_shows(engine, n, expected):
    _send(n)
    _apply()
    r = _by_tx()[tid(n)]
    assert r["status"] == expected
    tx = next(t for t in TXS if t["transaction_id"] == tid(n))
    if expected != "sent":
        assert r["status_at"] == sor._iso(tx["status_updated"])
    if expected == "accepted":
        assert r["resolved_transaction_id"] == tid(n)


@pytest.mark.parametrize("n,counter,counter_status", [
    (6, 7, "declined"), (8, 9, "pending"), (10, 11, "accepted"), (18, 19, "countered")])
def test_a_countered_offer_carries_its_counter(engine, n, counter, counter_status):
    _send(n)
    _apply()
    r = _by_tx()[tid(n)]
    assert (r["status"], r["counter_transaction_id"], r["counter_status"]) == \
        ("countered", tid(counter), counter_status)


def test_counter_terms_are_from_the_users_side(engine):
    _send(6)
    _apply()
    terms = json.loads(_by_tx()[tid(6)]["counter_terms_json"])
    assert terms == {"give_asset_ids": ["p105", "p106", f"{LEAGUE}_2027_1_1"],
                     "receive_asset_ids": ["p205"], "give_faab": 5}


def test_a_counter_outside_the_window_is_not_linked(engine):
    _send(16)
    _apply()
    r = _by_tx()[tid(16)]
    assert (r["status"], r["counter_transaction_id"]) == ("declined", None)


def test_pending_offer_is_untouched_but_checked(engine):
    _send(4)
    _apply()
    r = _by_tx()[tid(4)]
    assert (r["status"], r["status_at"], r["checked_at"]) == ("sent", None, NOW.isoformat())


@pytest.mark.parametrize("final", ["accepted", "declined", "withdrawn", "lapsed"])
def test_a_final_status_is_never_moved(engine, final):
    _send(4)
    row = _by_tx()[tid(4)]
    db.update_trade_offer_outcome(row["id"], {"status": final})
    flipped = [dict(t, status="rejected", metadata={"rejecter_id": THEM})
               if t["transaction_id"] == tid(4) else t for t in TXS]
    _apply(txs=flipped)
    assert _by_tx()[tid(4)]["status"] == final


def test_completed_different_terms_yields_to_the_private_answer(engine):
    _send(10)
    row = _by_tx()[tid(10)]
    db.update_trade_offer_outcome(row["id"], {"status": "completed_different_terms"})
    _apply()
    r = _by_tx()[tid(10)]
    assert (r["status"], r["counter_status"]) == ("countered", "accepted")


# ---------------------------------------------------------------------------
# Counter linking (pure)
# ---------------------------------------------------------------------------

def _t(n, status, creator, created, updated, rosters=(1, 2), counter=False, rejecter=None):
    return {"transaction_id": tid(n), "type": "trade", "status": status, "creator": creator,
            "created": created, "status_updated": updated, "roster_ids": list(rosters),
            "metadata": {"rejecter_id": rejecter} if rejecter else None,
            "settings": {"is_counter": 1} if counter else None}


def test_one_counter_answers_one_offer_the_one_that_closed_first():
    me = lambda u: u == ME                                         # noqa: E731
    a = _t(1, "rejected", ME, 0, 1_000_000, rejecter=THEM)
    b = _t(2, "rejected", ME, 0, 1_050_000, rejecter=THEM)
    c = _t(3, "proposed", THEM, 1_060_000, 1_060_000, counter=True)
    links = sor.link_counters([a, b, c], me)
    assert {k: v["transaction_id"] for k, v in links.items()} == {tid(1): tid(3)}


@pytest.mark.parametrize("why,counter", [
    ("another roster pair", _t(3, "proposed", THEM, 1_010_000, 1_010_000, rosters=(1, 3), counter=True)),
    ("from the same side", _t(3, "proposed", ME, 1_010_000, 1_010_000, counter=True)),
    ("not flagged a counter", _t(3, "proposed", THEM, 1_010_000, 1_010_000)),
    ("too early", _t(3, "proposed", THEM, 1_000_000 - 61_000, 1_000_000, counter=True)),
    ("too late", _t(3, "proposed", THEM, 1_000_000 + 601_000, 1_601_000, counter=True)),
])
def test_counter_link_needs_pair_side_flag_and_window(why, counter):
    me = lambda u: u == ME                                         # noqa: E731
    offer = _t(1, "rejected", ME, 0, 1_000_000, rejecter=THEM)
    assert sor.link_counters([offer, counter], me) == {}, why


def test_a_pending_offer_has_no_counter():
    me = lambda u: u == ME                                         # noqa: E731
    offer = _t(1, "proposed", ME, 0, 1_000_000)
    counter = _t(3, "proposed", THEM, 1_000_100, 1_000_100, counter=True)
    assert sor.link_counters([offer, counter], me) == {}


# ---------------------------------------------------------------------------
# Consented import
# ---------------------------------------------------------------------------

def test_without_consent_only_the_apps_own_rows_are_written(engine):
    _send(1)
    stats = _apply(import_on=False)
    assert [r["provider_transaction_id"] for r in _rows()] == [tid(1)]
    assert stats["imported"] == 0 and stats["app_updated"] == 1


def test_with_consent_the_users_own_offers_are_imported_marked_by_source(engine):
    _send(1)
    stats = _apply(import_on=True)
    rows = _by_tx()
    assert rows[tid(1)]["source"] == "app"                          # the app's row, not a copy
    imported = {k: v for k, v in rows.items() if v["source"] == "sleeper_import"}
    # Two-team trades involving roster 1, minus the app's own: 2-13, 16-20.
    assert set(imported) == {tid(n) for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20)}
    assert tid(14) not in rows and tid(15) not in rows             # three-team; not mine
    assert stats["skipped_multi_team"] == 1
    l_row, m_row = imported[tid(12)], imported[tid(13)]
    assert (l_row["direction"], l_row["status"], l_row["their_roster_id"]) == ("sent", "declined", 2)
    assert (json.loads(l_row["give_asset_ids"]), json.loads(l_row["receive_asset_ids"])) == (["p111"], ["p211"])
    assert (m_row["direction"], m_row["status"]) == ("received", "sent")
    assert (json.loads(m_row["give_asset_ids"]), json.loads(m_row["receive_asset_ids"])) == (["p112"], ["p212"])
    assert imported[tid(7)]["direction"] == "received" and imported[tid(7)]["status"] == "declined"
    assert json.loads(imported[tid(7)]["extras_json"]) == {"give_faab": 5}
    assert imported[tid(12)]["sent_at"] == sor._iso(next(t for t in TXS if t["transaction_id"] == tid(12))["created"])


def test_apply_is_idempotent(engine):
    _send(6)
    _apply(import_on=True)
    first = _rows()
    later = NOW + timedelta(hours=1)
    stats = _apply(import_on=True, now=later)
    second = _rows()
    assert stats["imported"] == 0
    strip = lambda rows: [{k: v for k, v in r.items() if k != "checked_at"} for r in rows]  # noqa: E731
    assert strip(first) == strip(second)
    assert {r["checked_at"] for r in second} == {later.isoformat()}


def test_two_consenting_managers_each_hold_their_own_row(engine):
    _apply(import_on=True)
    them_view = sor.apply_read(user_id="synthetic-account-2", league_id=LEAGUE, txs=TXS,
                               my_roster_id=2, me={THEM}, import_on=True, now=NOW)
    assert them_view["imported"] > 0
    mine, theirs = _by_tx(USER)[tid(12)], _by_tx("synthetic-account-2")[tid(12)]
    assert (mine["direction"], theirs["direction"]) == ("sent", "received")
    assert (mine["their_roster_id"], theirs["their_roster_id"]) == (2, 1)


def test_nothing_stored_carries_the_token_metadata_settings_or_a_user_id(engine):
    _send(6)
    _apply(import_on=True)
    dump = json.dumps(_rows(), default=str)
    for secret in (TOKEN_SECRET, ME, THEM, "700000000000000003", "rejecter", "is_counter",
                   "expires_at", "metadata", "settings"):
        assert secret not in dump, secret


# ---------------------------------------------------------------------------
# Consent: the route
# ---------------------------------------------------------------------------

def _flags(*on):
    return lambda k: k in on


@pytest.fixture()
def client(engine, monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    server.app.config["TESTING"] = True
    token = "offer-read-sess"
    with server._sessions_lock:
        server._sessions[token] = {"user_id": USER, "verified": True, "last_active": 0.0}
    monkeypatch.setattr(server, "is_enabled", _flags("trade.sleeper_offer_import"))
    try:
        yield server.app.test_client(), {"X-Session-Token": token, "Content-Type": "application/json"}
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


def _link(expired=False):
    exp = int(time.time()) + (-10 if expired else 365 * 86400)   # Sleeper's are 365-day
    import base64
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    jwt = f"{b64({'alg': 'HS256'})}.{b64({'user_id': ME, 'exp': exp})}.sig"
    db.upsert_sleeper_credential(USER, ME, sw.encrypt_token(jwt), None)
    return jwt


def _consents():
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(db.offer_import_consents_table).order_by(db.offer_import_consents_table.c.id))]


def test_consent_routes_404_with_the_flag_off_except_withdrawal(client, monkeypatch):
    c, h = client
    monkeypatch.setattr(server, "is_enabled", _flags())
    assert c.get("/api/sleeper/offer-import", headers=h).status_code == 404
    assert c.post("/api/sleeper/offer-import", headers=h, json={}).status_code == 404
    r = c.delete("/api/sleeper/offer-import", headers=h)
    assert r.status_code == 200 and r.get_json()["consented"] is False


def test_grant_is_append_only_versioned_and_needs_a_link(client):
    c, h = client
    assert c.post("/api/sleeper/offer-import", headers=h,
                  json={"terms_version": sor.TERMS_VERSION}).get_json()["error"] == "sleeper_not_linked"
    _link()
    r = c.post("/api/sleeper/offer-import", headers=h, json={"terms_version": "old"})
    assert r.status_code == 409 and r.get_json()["error"] == "terms_changed"
    assert _consents() == []
    for _ in range(2):
        r = c.post("/api/sleeper/offer-import", headers=h, json={"terms_version": sor.TERMS_VERSION})
        assert r.status_code == 200 and r.get_json()["consented"] is True
    rows = _consents()
    assert [(x["kind"], x["terms_version"], x["via"]) for x in rows] == \
        [("grant", sor.TERMS_VERSION, "settings")]
    assert rows[0]["recorded_at"]
    body = c.get("/api/sleeper/offer-import", headers=h).get_json()
    assert body == {"consented": True, "linked": True, "terms_version": sor.TERMS_VERSION,
                    "label": sor.SWITCH_LABEL, "terms_line": sor.TERMS_LINE}


def test_a_grant_at_an_older_terms_version_is_not_consent(client, monkeypatch):
    _link()
    db.record_offer_import_grant(USER, "offer-import-draft-0", NOW.isoformat())
    assert sor.consented(USER) is False


def test_revoke_deletes_imports_in_the_same_transaction_and_keeps_the_apps_rows(client):
    c, h = client
    _link()
    c.post("/api/sleeper/offer-import", headers=h, json={"terms_version": sor.TERMS_VERSION})
    _send(1)
    _apply(import_on=True)
    other = "synthetic-account-2"
    sor.apply_read(user_id=other, league_id=LEAGUE, txs=TXS, my_roster_id=2, me={THEM},
                   import_on=True, now=NOW)
    n_imported = sum(r["source"] == "sleeper_import" for r in _rows(USER))
    r = c.delete("/api/sleeper/offer-import", headers=h)
    assert r.get_json() == {"consented": False, "deleted": n_imported,
                            "notice": sor.WITHDRAWN_NOTICE}
    assert [x["provider_transaction_id"] for x in _rows(USER)] == [tid(1)]
    assert _rows(other)                                             # another user's untouched
    assert [x["kind"] for x in _consents()] == ["grant", "withdrawal"]
    assert c.delete("/api/sleeper/offer-import", headers=h).get_json()["deleted"] == 0
    assert [x["kind"] for x in _consents()] == ["grant", "withdrawal"]


def test_revoke_is_atomic(client, monkeypatch):
    _link()
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    _apply(import_on=True)
    before_rows, before_consents = _rows(), _consents()
    real_delete = db.delete

    def broken(table):
        if table is db.trade_offer_outcomes_table:
            raise RuntimeError("synthetic failure inside the transaction")
        return real_delete(table)

    monkeypatch.setattr(db, "delete", broken)
    with pytest.raises(RuntimeError):
        db.withdraw_offer_import_consent(USER, sor.TERMS_VERSION, NOW.isoformat())
    assert _rows() == before_rows and _consents() == before_consents


@pytest.mark.parametrize("method", ["get", "post", "delete"])
def test_consent_routes_need_a_verified_session(client, method):
    c, h = client
    with server._sessions_lock:
        server._sessions[h["X-Session-Token"]]["verified"] = False
    r = getattr(c, method)("/api/sleeper/offer-import", headers=h, json={})
    assert r.status_code == 403 and r.get_json()["error"] == "verification_required"


# ---------------------------------------------------------------------------
# The server seams: when a read happens, and what a failure does
# ---------------------------------------------------------------------------

@pytest.fixture()
def wired(client, monkeypatch):
    """A linked, CONSENTING user with one open app-sent offer; the private call
    and the public rosters read are mocks."""
    _link()
    _send(1)
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    call = MagicMock(return_value=TXS)
    monkeypatch.setattr(server._sleeper_write, "league_trade_offers", call)
    monkeypatch.setattr(server, "_fetch_league_rosters", MagicMock(return_value=ROSTERS))
    return call


def test_flag_off_makes_no_call(wired, monkeypatch):
    monkeypatch.setattr(server, "is_enabled", _flags())
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "off"
    wired.assert_not_called()
    assert _by_tx()[tid(1)]["status"] == "sent"


def test_a_read_moves_the_offer_and_then_is_not_due_for_thirty_minutes(wired, monkeypatch):
    _send(4)                       # still pending at Sleeper: keeps a reason to read
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "read"
    wired.assert_called_once()
    assert wired.call_args[0][1] == LEAGUE
    assert _by_tx()[tid(1)]["status"] == "declined"
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "not_due"
    assert wired.call_count == 1
    clock = time.time() + sor.READ_MIN_INTERVAL_S + 1
    monkeypatch.setattr(server.time, "time", lambda: clock)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "read"
    assert wired.call_count == 2


def test_no_reason_to_read_makes_no_call(client, monkeypatch):
    # No app-sent offer Sleeper may still move, and the switch is off.
    _link()
    call = MagicMock(side_effect=AssertionError("read without a reason"))
    monkeypatch.setattr(server._sleeper_write, "league_trade_offers", call)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "nothing_to_read"
    _send(5)
    _apply()                                   # accepted: final, no longer a reason
    assert _by_tx()[tid(5)]["status"] == "accepted"
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "nothing_to_read"


def test_without_the_switch_an_app_sent_offer_is_read_and_nothing_is_imported(client, monkeypatch):
    # Operator, 2026-11-11: trades sent from the app are followed without the
    # Settings switch (web/terms.html §6). The switch adds the other offers.
    _link()
    _send(1)
    call = MagicMock(return_value=TXS)
    monkeypatch.setattr(server._sleeper_write, "league_trade_offers", call)
    monkeypatch.setattr(server, "_fetch_league_rosters", MagicMock(return_value=ROSTERS))
    assert not sor.consented(USER)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "read"
    call.assert_called_once()
    rows = _rows()
    assert [r["provider_transaction_id"] for r in rows] == [tid(1)]      # the app's row only
    assert rows[0]["status"] == "declined" and rows[0]["source"] == "app"
    # Its offer is final now, so there is nothing left to read for.
    clock = time.time() + sor.READ_MIN_INTERVAL_S + 1
    monkeypatch.setattr(server.time, "time", lambda: clock)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "nothing_to_read"
    assert call.call_count == 1
    # The switch on: the same read now also keeps the user's other offers.
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "read"
    assert any(r["source"] == "sleeper_import" for r in _rows())


def test_no_credential_makes_no_call(engine, monkeypatch):
    monkeypatch.setattr(server, "is_enabled", _flags("trade.sleeper_offer_import"))
    _send(1)
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    call = MagicMock(side_effect=AssertionError)
    monkeypatch.setattr(server._sleeper_write, "league_trade_offers", call)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "no_credential"


@pytest.mark.parametrize("error,auth", [
    (sw.SleeperAuthError("Sleeper rejected the token (HTTP 401)", detail="Unauthorized"), True),
    (sw.SleeperWriteError("Sleeper returned HTTP 500", detail="oops"), False),
])
def test_a_failed_read_changes_nothing_backs_off_and_logs_once(wired, caplog, error, auth):
    wired.side_effect = error
    before_rows, before_cred = _rows(), db.get_sleeper_credential(USER)
    with caplog.at_level(logging.WARNING, logger="backend.sleeper_offer_read"):
        assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "failed"
        # Past the ordinary interval, still inside the back-off: no call, no log.
        later = time.time() + sor.READ_MIN_INTERVAL_S + 1
        with patch.object(server.time, "time", lambda: later):
            assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "not_due"
    assert wired.call_count == 1
    assert _rows() == before_rows
    assert db.get_sleeper_credential(USER) == before_cred           # never dropped
    failures = [r for r in caplog.records if "sleeper offers read failed" in r.getMessage()]
    assert len(failures) == 1 and ("(auth)" in failures[0].getMessage()) == auth
    assert TOKEN_SECRET not in caplog.text
    after = time.time() + (sor.AUTH_BACKOFF_S if auth else sor.ERROR_BACKOFF_S) + 1
    with patch.object(server.time, "time", lambda: after):
        wired.side_effect = None
        assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "read"


def test_an_auth_failure_backs_off_every_league_of_the_user(wired):
    wired.side_effect = sw.SleeperAuthError("no", detail="Unauthorized")
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "failed"
    other = "990000000000000008"
    to.record_sent(user_id=USER, league_id=other, transaction_id="1500000000000000001",
                   my_roster_id=1, their_roster_id=2, give_asset_ids=["x"], receive_asset_ids=["y"])
    assert server._sleeper_offers_sync(USER, other, trigger="t") == "not_due"
    assert wired.call_count == 1


def test_an_expired_token_is_not_sent(client, monkeypatch):
    _link(expired=True)
    _send(1)
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    call = MagicMock(return_value=TXS)
    monkeypatch.setattr(server._sleeper_write, "league_trade_offers", call)
    monkeypatch.setattr(server, "_fetch_league_rosters", MagicMock(return_value=ROSTERS))
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "failed"
    call.assert_not_called()
    assert db.get_sleeper_credential(USER) is not None


def test_a_failed_rosters_read_makes_no_private_call(wired, monkeypatch):
    monkeypatch.setattr(server, "_fetch_league_rosters", MagicMock(return_value=None))
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "failed"
    wired.assert_not_called()


def test_a_linked_platform_league_is_never_read(wired, monkeypatch):
    monkeypatch.setattr(server, "is_linked_platform_league", lambda lid: True)
    assert server._sleeper_offers_sync(USER, LEAGUE, trigger="t") == "not_sleeper"
    wired.assert_not_called()


@pytest.mark.parametrize("flag_on", [True, False])
def test_find_a_trade_kicks_one_background_read_only_when_on(monkeypatch, flag_on):
    spawned = MagicMock()
    monkeypatch.setattr(server, "_sleeper_offers_spawn", spawned)
    monkeypatch.setattr(server, "is_enabled",
                        _flags("trade.sleeper_offer_import") if flag_on else _flags())
    server._sleeper_offers_kick(USER, LEAGUE)
    if flag_on:
        spawned.assert_called_once_with(server._sleeper_offers_sync, USER, LEAGUE,
                                        trigger="find_a_trade")
    else:
        spawned.assert_not_called()


def test_generate_route_calls_the_kick():
    import inspect
    src = inspect.getsource(server.generate_trades)
    assert "_sleeper_offers_kick(g_user_id, league_id)" in src


def test_daily_step_is_skipped_when_off(wired, monkeypatch):
    monkeypatch.setattr(server, "is_enabled", _flags())
    assert server._daily_tick_sleeper_offers(NOW) == ("skipped", "flag off")
    wired.assert_not_called()


def test_daily_step_reads_open_app_offers_and_consenting_users_leagues(wired, monkeypatch):
    # An app-sent offer in LEAGUE inside the watch window (sent "now" by the
    # recorder's clock), and a consenting user whose current league is another.
    monkeypatch.setattr(to, "_now", lambda: NOW)
    with db.engine.begin() as conn:
        conn.execute(db.trade_offer_outcomes_table.update().values(sent_at=NOW.isoformat()))
    db.record_offer_import_grant(USER, sor.TERMS_VERSION, NOW.isoformat())
    other = "990000000000000009"
    with db.engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id=other, user_id=ME,
                                                      updated_at=NOW.isoformat()))
        conn.execute(db.league_members_table.insert().values(league_id=other, user_id=ME))
    outcome, stats = server._daily_tick_sleeper_offers(NOW)
    assert outcome == "ok" and stats == {"read": 2}
    assert sorted(c[0][1] for c in wired.call_args_list) == sorted([LEAGUE, other])
    # A second tick the same day: LEAGUE's offer is now final (declined), so
    # it is no longer a target; the consenting user's league is not due.
    assert server._daily_tick_sleeper_offers(NOW)[1] == {"not_due": 1}
    assert wired.call_count == 2


def test_flag_defaults_off_in_code_and_ships_on():
    """On from 2026-11-10, once the operator approved the Terms wording. New
    code still ships dark: the code default is off and the config turns it on."""
    from backend import feature_flags as ff
    repo = Path(__file__).resolve().parents[2]
    assert sor.FLAG in ff.FLAG_KEYS and ff.DEFAULT_FLAGS[sor.FLAG] is False
    for path in ("config/features.json", "backend/tests/fixtures/flags/release.json",
                 "backend/tests/fixtures/flags/onboarding-v2.json",
                 "backend/tests/fixtures/flags/profiles-on.json"):
        assert json.loads((repo / path).read_text())[sor.FLAG] is True, path


def test_the_published_terms_carry_the_wording_the_switch_stands_on():
    """Consent is recorded against TERMS_VERSION; the page must say what the
    switch does, in the words the switch itself uses for its name."""
    repo = Path(__file__).resolve().parents[2]
    terms = (repo / "web/terms.html").read_text()
    privacy = (repo / "web/privacy.html").read_text()
    assert "draft" not in sor.TERMS_VERSION
    for page in (terms, privacy):
        assert '"Use my Sleeper trade offers"' in page
        assert "never your messages or chats" in page
    assert sor.SWITCH_LABEL.startswith("Use my Sleeper trade offers")
    assert "we delete the offers we imported" in terms


def test_consent_and_imports_are_deleted_with_the_account():
    from backend import accounts
    assert "offer_import_consents" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert "trade_offer_outcomes" in accounts._ADDITIONAL_PRIVATE_TABLES


# ---------------------------------------------------------------------------
# Shapes seen on the live private read (2026-11-10, docs/plans/offer-learnings/
# sleeper-offers-read.md): picks arrive as "orig,season,round,from,to" strings
# and FAAB as an "n,n,n" string.
# ---------------------------------------------------------------------------

def test_live_shapes_string_picks_parse_and_string_faab_marks_the_offer():
    tx = {"adds": {"p1": 1}, "drops": {"p2": 1},
          "draft_picks": ["3,2027,1,1,2", "5,2026,2,2,1"], "waiver_budget": ["1,2,25"]}
    give, receive, extras = sor.side_assets(tx, 1, "L1")
    assert db.make_pick_id("L1", 2027, 1, "3") in give
    assert db.make_pick_id("L1", 2026, 2, "5") in receive
    assert "p2" in give and "p1" in receive
    # The string's field order is not established: the offer is only marked,
    # and any extras keep it out of revised-offer cards.
    assert extras == {"unparsed_faab": 1}
