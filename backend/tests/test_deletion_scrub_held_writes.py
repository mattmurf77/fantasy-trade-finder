"""Legal R28.26 #10 (MUST): no write after a deletion re-creates the person's id.

While a deletion's scrub job row lives, a write that would store one of its
ids as a trade's partner stores the token, or NULL where the deletion itself
NULLs that column (database.live_deletion_token). That covers a card a client
still holds from before the deletion:
  • the lookup itself (the 5 s cache, cleared by the delete route);
  • routes: a held FB-46 swipe, a calculator queue, a bad-trade flag;
  • a confirmed proposal's row, the taste update, trade_impressions;
  • every pass re-runs the side-table scrub, so a write that raced the
    deletion's commit is caught (and the taste merge is idempotent);
  • the in-process deleted-id set is pruned once its window closes.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select

import backend.database as db_module
import backend.server as server
import backend.tests.test_calc_trade_queue as tcq
from backend import accounts, database as db, deletion_scrub as scrub, taste_service
from backend.tests.test_deletion_scrub import (  # noqa: F401  (fixture)
    DEL, EARLY, LEAGUE, OTHER, VIEWER, engine, job, read)

TOKEN = "redacted:" + "a" * 32


def _job_row(conn, ids, token=TOKEN):
    conn.execute(insert(db.deletion_scrub_jobs_table).values(
        job_id="b" * 32, token=token, partner_ids_json=json.dumps(list(ids)),
        league_ids_json=json.dumps([LEAGUE]),
        deleted_at=datetime.now(timezone.utc).isoformat()))
    db.clear_deletion_tokens_cache()


@pytest.fixture(autouse=True)
def _fresh_cache():
    db.clear_deletion_tokens_cache()
    yield
    db.clear_deletion_tokens_cache()


# ── The lookup ──────────────────────────────────────────────────────────────

def test_a_deletion_maps_its_ids_to_its_token_while_the_job_lives(engine):
    assert db.live_deletion_token(DEL) is None
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    db.clear_deletion_tokens_cache()           # the delete route does this
    assert db.live_deletion_token(DEL) == token
    assert db.live_deletion_token(OTHER) is None
    with engine.begin() as conn:               # the job finishes: no mapping
        conn.execute(db.deletion_scrub_jobs_table.delete())
    db.clear_deletion_tokens_cache()
    assert db.live_deletion_token(DEL) is None


def test_the_lookup_is_cached_and_never_raises(engine, monkeypatch):
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    assert db.live_deletion_token(DEL) == TOKEN
    with engine.begin() as conn:
        conn.execute(db.deletion_scrub_jobs_table.delete())
    assert db.live_deletion_token(DEL) == TOKEN       # within the 5 s cache
    db.clear_deletion_tokens_cache()

    class Broken:
        def connect(self):
            raise RuntimeError(f"db down for {DEL}")
    monkeypatch.setattr(db, "engine", Broken())
    # A failed read keeps the last map it had (never raises, never forgets a
    # live deletion on a blip), and logs no id.
    assert db.live_deletion_token(DEL) == TOKEN


# ── Held cards on the routes ────────────────────────────────────────────────

@pytest.fixture()
def routes(monkeypatch):
    yield from tcq._harness_ctx(caller_in_members=False)


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json",
                       headers={"X-Session-Token": tcq.TOKEN})


def _event_props(name):
    return [c.kwargs.get("props") or {} for c in server.record_event.call_args_list
            if len(c.args) > 1 and c.args[1] == name]


def test_a_held_swipe_on_a_deleted_partners_card_writes_the_token(routes):
    client, engine, *_ = routes
    with engine.begin() as conn:
        _job_row(conn, [tcq.OPP])
    res = _post(client, "/api/trades/swipe", {
        "trade_id": "held0001", "decision": "like", "league_id": tcq.LEAGUE,
        "give_player_ids": ["g1"], "receive_player_ids": ["r1"],
        "target_user_id": tcq.OPP, "target_username": "opp"})
    assert res.status_code == 200, res.get_data(as_text=True)
    (props,) = _event_props("trade_proposed")
    assert props["target"] == TOKEN
    assert tcq.OPP not in json.dumps([c.kwargs for c in server.record_event.call_args_list])


def test_a_held_swipe_with_no_deletion_keeps_the_partner(routes):
    client, *_ = routes
    assert _post(client, "/api/trades/swipe", {
        "trade_id": "held0002", "decision": "like", "league_id": tcq.LEAGUE,
        "give_player_ids": ["g1"], "receive_player_ids": ["r1"],
        "target_user_id": tcq.OPP, "target_username": "opp"}).status_code == 200
    (props,) = _event_props("trade_proposed")
    assert props["target"] == tcq.OPP


def test_a_calculator_queue_to_a_deleted_partner_writes_the_token(routes):
    client, engine, *_ = routes
    with engine.begin() as conn:
        _job_row(conn, [tcq.OPP])
    assert tcq._queue(client).get_json()["queued"] is True
    (props,) = _event_props("trade_proposed")
    assert props["target"] == TOKEN


def test_a_flag_on_a_deleted_partners_card_stores_no_id_or_name(routes):
    client, engine, *_ = routes
    with engine.begin() as conn:
        _job_row(conn, [tcq.OPP])
    res = _post(client, "/api/trades/flag", {
        "league_id": tcq.LEAGUE, "give_player_ids": ["g1"], "receive_player_ids": ["r1"],
        "target_user_id": tcq.OPP, "target_username": "opp", "reason": "other"})
    assert res.status_code < 300, res.get_data(as_text=True)
    with engine.connect() as conn:
        (row,) = conn.execute(select(db.bad_trade_flags_table)).mappings().all()
    assert row["target_user_id"] is None and row["target_username"] is None


# ── Proposals, taste, trade_impressions ─────────────────────────────────────

def test_a_confirmed_proposal_to_a_deleted_partner_keeps_no_id_or_valuation(engine, monkeypatch):
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    saved = []
    monkeypatch.setattr(server._trade_policy, "telemetry_enabled", lambda: True)
    monkeypatch.setattr(server, "save_trade_proposal",
                        lambda row: (saved.append(row), (1, True))[1])
    server._record_trade_proposal(
        sess={"league": None}, provider="sleeper", user_id=VIEWER, league_id=LEAGUE,
        target_user_id=DEL, give_asset_ids=["g1"], receive_asset_ids=["r1"],
        impression_id=None, proposal_event_id="pe-1")
    (row,) = saved
    assert row["target_user_id"] is None and row["valuation_json"] is None


def test_the_taste_update_keys_a_deleted_partner_by_token(engine):
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    assert taste_service._redact_partner_attrs(
        [f"partner:{DEL}", f"partner:{OTHER}", "pos:QB"]) == sorted(
        [f"partner:{TOKEN}", f"partner:{OTHER}", "pos:QB"])


def test_an_outcome_on_a_held_card_updates_taste_under_the_token(engine):
    """The live path: an outcome on the person's card (its impression still
    names them, before the scrub's pass) writes `partner:<token>`, never
    touching or re-creating `partner:<id>`."""
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    before = {r["attr"]: r["w_short"] for r in read(engine, db.user_taste_table)}
    taste_service.update_taste_from_outcome("c-del-0", "like")
    after = {r["attr"]: r["w_short"] for r in read(engine, db.user_taste_table)}
    assert f"partner:{TOKEN}" in after
    assert after[f"partner:{DEL}"] == before[f"partner:{DEL}"]


def test_trade_impressions_store_no_deleted_partner(engine):
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    db.log_trade_impressions(VIEWER, LEAGUE, [
        {"target_user_id": DEL, "give_player_ids": ["g"], "receive_player_ids": ["r"]},
        {"target_user_id": OTHER, "give_player_ids": ["g"], "receive_player_ids": ["r"]}])
    with engine.connect() as conn:
        targets = conn.execute(select(db.trade_impressions_table.c.target_user_id)
                               .order_by(db.trade_impressions_table.c.position_in_deck)).scalars().all()
    assert targets == [None, OTHER]


# ── Every pass repairs the side tables ──────────────────────────────────────

def test_a_write_that_raced_the_deletion_is_repaired_by_the_next_pass(engine):
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    with engine.begin() as conn:           # written as if racing the commit
        conn.execute(insert(db.user_taste_table).values(
            user_id=VIEWER, attr=f"partner:{DEL}", w_short=3.0, w_long=30.0, updated_at=EARLY))
        conn.execute(insert(db.bad_trade_flags_table).values(
            user_id=VIEWER, league_id=LEAGUE, target_user_id=DEL, target_username="Del",
            give_player_ids="[]", receive_player_ids="[]", dedupe_key="k1", created_at=EARLY))
        conn.execute(insert(db.trade_impressions_table).values(
            user_id=VIEWER, league_id=LEAGUE, target_user_id=DEL, give_player_ids="[]",
            receive_player_ids="[]", position_in_deck=0, shown_at=EARLY))
    scrub.run_pending()
    taste = {r["attr"]: r for r in read(engine, db.user_taste_table)}
    assert f"partner:{DEL}" not in taste
    # the deletion's own merge (1 + 2, aliases) plus the raced row (3)
    assert taste[f"partner:{token}"]["w_short"] == pytest.approx(6.0)
    (flag,) = read(engine, db.bad_trade_flags_table)
    assert flag["target_user_id"] is None and flag["target_username"] is None
    assert [r["target_user_id"] for r in read(engine, db.trade_impressions_table)] == [None]


# ── The in-process deleted-id set is pruned ─────────────────────────────────

def test_the_deleted_id_set_is_pruned_after_its_window_with_a_last_purge():
    class Card:
        def __init__(self, target):
            self.target_user_id = target

    store = {"t1": Card(DEL), "t2": Card(OTHER)}
    svc = type("Svc", (), {"_trade_cards": store})()
    now = datetime.now(timezone.utc)
    with patch.object(server, "trade_service", svc), \
         patch.dict(server._deleted_partner_ids, {DEL: now - timedelta(seconds=1),
                                                 "still-open": now + timedelta(hours=1)},
                    clear=True):
        assert server._prune_deleted_partner_ids(now) == 1
        assert set(server._deleted_partner_ids) == {"still-open"}
        assert set(store) == {"t2"}           # the late-written card went too


def test_a_held_upgrade_row_takes_a_live_deletions_token_before_the_pack_is_redacted(engine, monkeypatch):
    """The audit's cursor-order gap: an upgrade written while the pack still
    names the person gets the live deletion's token."""
    from backend.tests.test_deletion_scrub import features_for
    row = {"impression_id": "d:0", "features_json": json.dumps(features_for(DEL))}
    monkeypatch.setattr(server, "_deck_pack_card", lambda state, index: {"partner_user_id": DEL})
    assert server._redacted_held_row(dict(row), None, 0) == row          # no deletion: untouched
    with engine.begin() as conn:
        _job_row(conn, [DEL])
    out = server._redacted_held_row(dict(row), None, 0)
    assert json.loads(out["features_json"])["partner_user_id"] == TOKEN
    assert DEL not in json.dumps(out)
