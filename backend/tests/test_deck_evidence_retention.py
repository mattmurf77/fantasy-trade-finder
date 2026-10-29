"""Deck-evidence retention (legal R28.20 (iii), final; models-lead addendum E).

purge_deck_evidence runs one bounded pass per cleanup tick, measured from a
deck's first delivery:
- the cap (`deck_evidence_retention_days`, 365): every store of a deck past it
  goes at once, in one transaction (E-a1): its outcomes (a packed card's by
  contract id, with or without a row; a row's by its impression_id), rows,
  withdrawals, candidate set, bakeoff_runs row and pack; and legacy
  trade_impressions past it;
- the full-row bound (`deck_evidence_full_row_days`, 90): a packed deck's rows
  (full and ghost) go, everything else stays until the cap (E-c1, E-c2); a
  deck with no pack keeps its rows until the cap (E-a3).
Off at a cap of 0 (the default, dark); a bound under 56 days is refused.

Covers: off; both floors; the cap across every store, packed and pack-less,
with outcomes never before their pack and no other deck's touched; the
full-row bound, its chunks and resumable cursor; the bounds measured from the
first delivery; the batch bound; a failing deck or chunk left for the next
tick; trade_impressions; the loop step's knobs; the index and its script.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, insert, select, text, update

import backend.database as db_module
import backend.server as server
from backend.database import (
    bakeoff_runs_table, deck_candidate_sets_table, deck_card_withdrawals_table,
    deck_evidence_packs_table, deck_impressions_table, deck_outcomes_table, metadata,
    trade_impressions_table, trade_page_store_table, trade_pass_reasons_table,
    trade_policy_shadow_table)
from backend.tests.test_eval_pack_reader import _card, _row

NOW = datetime(2028, 3, 1, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "_full_row_cursor", None)
    monkeypatch.setattr(db_module, "_bound_warned", set())
    monkeypatch.setattr(db_module, "_served_index_ready", False)
    monkeypatch.setattr(db_module, "_served_index_checked", 0.0)
    monkeypatch.setattr(db_module, "_served_index_warned", False)
    return engine


def deck(engine, job, days_ago, *, packed=True, n=3, user="u1", league="lg", pack_days=None):
    """A deck first delivered `days_ago` days before NOW: n full rows and a
    ghost row, a withdrawal, a candidate set, a bakeoff_runs row, a policy
    shadow row, a viewed outcome and a pass reason on its first row and
    (packed) a pack, plus a like and a pass reason on a packed card with no
    row (its contract id). A pack-less deck's rows have uuid ids, as pre-flip
    and live-mode rows do."""
    served = iso(days_ago)
    rows = [_row({**_card(job, i, served_at=served, user=user), "league_id": league})
            for i in range(n)]
    rows.append(_row({**_card(job, n, served_at=served, user=user), "league_id": league},
                     ghost=True))
    if not packed:
        for r in rows:
            r["impression_id"] = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(insert(deck_impressions_table), rows)
        conn.execute(insert(deck_card_withdrawals_table).values(
            deck_job_id=job, card_index=n + 1, user_id=user, league_id=league,
            reason="disposition_cut", first_withdrawn_at=served, served_before=0,
            impression_id=f"{job}:{n + 1}"))
        conn.execute(insert(deck_candidate_sets_table).values(
            candidate_set_id=f"cs-{job}", deck_job_id=job, user_id=user, league_id=league,
            size=n, set_hash="h" * 16, candidates_json="[]", created_at=served))
        conn.execute(insert(bakeoff_runs_table).values(
            run_id=f"bo-{job}", deck_job_id=job, user_id=user, league_id=league,
            arm_order="[]", deck_size=n, arms_json="{}", created_at=served))
        conn.execute(insert(trade_policy_shadow_table).values(
            deck_job_id=job, user_id=user, league_id=league, created_at=served))
        conn.execute(insert(deck_outcomes_table).values(
            impression_id=rows[0]["impression_id"], action="viewed", acted_at=served))
        conn.execute(insert(trade_pass_reasons_table).values(
            impression_id=rows[0]["impression_id"], user_id=user, league_id=league,
            reason="value", created_at=served, updated_at=served))
        if packed:
            conn.execute(insert(deck_outcomes_table).values(
                impression_id=f"{job}:{n + 2}", action="like", acted_at=served))
            conn.execute(insert(trade_pass_reasons_table).values(
                impression_id=f"{job}:{n + 2}", user_id=user, league_id=league,
                reason="fit", created_at=served, updated_at=served))
            conn.execute(insert(deck_evidence_packs_table).values(
                run_id=job, user_id=user, league_id=league,
                served_at=served if pack_days is None else iso(pack_days), pack_version=1,
                header_json=json.dumps({"run": {}}), cards_blob=b"x", checksum="c" * 64,
                card_count=n + 3, created_at=served))


def _count(conn, table, where):
    return conn.execute(select(func.count()).select_from(table).where(where)).scalar()


def counts(engine, job):
    """What's left of one deck, in every store."""
    o = deck_outcomes_table.c.impression_id
    r = trade_pass_reasons_table.c.impression_id
    with engine.connect() as conn:
        ids = list(conn.execute(select(deck_impressions_table.c.impression_id).where(
            deck_impressions_table.c.deck_job_id == job)).scalars())
        # A pack-less deck's outcomes are found through its rows: the tests
        # that delete those rows check "out"/"pr" before or through `outcomes`.
        return {
            "imp": len(ids),
            "out": _count(conn, deck_outcomes_table, o.like(f"{job}:%") | o.in_(ids or [""])),
            "pr": _count(conn, trade_pass_reasons_table, r.like(f"{job}:%") | r.in_(ids or [""])),
            "sh": _count(conn, trade_policy_shadow_table,
                         trade_policy_shadow_table.c.deck_job_id == job),
            "wd": _count(conn, deck_card_withdrawals_table,
                         deck_card_withdrawals_table.c.deck_job_id == job),
            "cs": _count(conn, deck_candidate_sets_table,
                         deck_candidate_sets_table.c.deck_job_id == job),
            "bo": _count(conn, bakeoff_runs_table, bakeoff_runs_table.c.deck_job_id == job),
            "pack": _count(conn, deck_evidence_packs_table,
                           deck_evidence_packs_table.c.run_id == job),
        }


def outcomes(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(deck_outcomes_table)).scalar()


GONE = {"imp": 0, "out": 0, "pr": 0, "sh": 0, "wd": 0, "cs": 0, "bo": 0, "pack": 0}
WHOLE = {"imp": 4, "out": 2, "pr": 2, "sh": 1, "wd": 1, "cs": 1, "bo": 1, "pack": 1}
WHOLE_PACKLESS = {**WHOLE, "out": 1, "pr": 1, "pack": 0}
ROWS_GONE = {**WHOLE, "imp": 0}   # the pack keeps its outcomes (contract ids) and the rest


def purge(**kw):
    return db_module.purge_deck_evidence(now=NOW, **{"days": 365, "full_row_days": 90, **kw})


@pytest.mark.parametrize("days", [0, 0.0, None])
def test_off_deletes_nothing_full_rows_included(db, days):
    deck(db, "old", 400)
    deck(db, "mid", 120)
    assert purge(days=days) == {}
    assert counts(db, "old") == counts(db, "mid") == WHOLE


def test_a_cap_under_the_floor_is_refused_and_logged(db, caplog):
    deck(db, "old", 400)
    with caplog.at_level("WARNING"):
        assert purge(days=30) == {}
    assert counts(db, "old") == WHOLE
    assert any("deck_evidence_retention_days 30 days is under the 56-day floor"
               in r.getMessage() for r in caplog.records)


def test_a_full_row_bound_under_the_floor_is_refused_and_the_cap_still_runs(db, caplog):
    deck(db, "old", 400)
    deck(db, "mid", 120)
    with caplog.at_level("WARNING"):
        purge(full_row_days=30)
    assert counts(db, "old") == GONE and counts(db, "mid") == WHOLE
    assert any("deck_evidence_full_row_days 30 days is under the 56-day floor"
               in r.getMessage() for r in caplog.records)


def test_the_cap_takes_every_store_of_a_deck_at_once(db):
    """E-a1: outcomes of every kind and pass reasons (on a packed card with no
    row included), rows, withdrawals, candidate set, bakeoff_runs row, policy
    shadow rows, pack; for a pack-less deck the per-card ones go through its
    rows (checked by table totals, as its rows are gone)."""
    deck(db, "packed", 400)
    deck(db, "rows-only", 380, packed=False)
    deck(db, "recent", 30)
    got = purge()
    assert counts(db, "packed") == counts(db, "rows-only") == GONE
    assert counts(db, "recent") == WHOLE
    assert got == {"deck_outcomes": 3, "trade_pass_reasons": 3, "deck_impressions": 8,
                   "deck_card_withdrawals": 2, "deck_candidate_sets": 2, "bakeoff_runs": 2,
                   "trade_policy_shadow": 2, "deck_evidence_packs": 1, "decks": 2}
    with db.connect() as conn:              # only the recent deck's per-card rows are left
        assert conn.execute(select(func.count()).select_from(deck_outcomes_table)).scalar() == 2
        assert conn.execute(select(func.count()).select_from(
            trade_pass_reasons_table)).scalar() == 2


def test_no_other_decks_outcomes_go(db):
    """The contract-id range is exact: deck d1's never reaches d10's."""
    deck(db, "d1", 400)
    deck(db, "d10", 30)
    purge()
    assert counts(db, "d1") == GONE and counts(db, "d10") == WHOLE


def test_a_big_packs_outcomes_all_go(db):
    """Every card's contract id, in bounded IN lists (a pack can hold
    thousands of cards)."""
    deck(db, "big", 400)
    with db.begin() as conn:
        conn.execute(update(deck_evidence_packs_table).values(card_count=1200))
        conn.execute(insert(deck_outcomes_table), [
            {"impression_id": f"big:{k}", "action": "pass", "acted_at": iso(400)}
            for k in (499, 500, 1001, 1199)])
    assert purge()["deck_outcomes"] == 6 and counts(db, "big") == GONE
    assert counts(db, "big") == GONE


def test_full_rows_of_a_packed_deck_go_at_90_days_and_the_rest_stays(db):
    """E-c1, E-c2: rows (ghost included) go, and the pack keeps every card;
    its outcomes never go before it (E-a1). A pack-less deck keeps its rows
    until the cap (E-a3)."""
    deck(db, "packed", 120)
    deck(db, "rows-only", 120, packed=False)
    deck(db, "recent", 30)
    before = outcomes(db)
    got = purge()
    assert counts(db, "packed") == ROWS_GONE
    assert counts(db, "rows-only") == WHOLE_PACKLESS
    assert counts(db, "recent") == WHOLE
    assert got == {"full_rows": 4}
    with db.connect() as conn:            # the viewed outcome outlives its row, with the pack
        assert conn.execute(select(func.count()).select_from(deck_outcomes_table)).scalar() \
            == before


def test_the_bounds_are_the_first_delivery(db):
    """A deck exactly at a bound stays; one a day past it goes."""
    deck(db, "cap-at", 365)
    deck(db, "cap-past", 366)
    deck(db, "rows-at", 90)
    deck(db, "rows-past", 91)
    purge(days=365.5, full_row_days=90.5)
    assert counts(db, "cap-at") == ROWS_GONE and counts(db, "cap-past") == GONE
    assert counts(db, "rows-at") == WHOLE and counts(db, "rows-past") == ROWS_GONE


@pytest.mark.parametrize("full_row_days", [0, 365, 400])
def test_rows_follow_the_cap_without_a_shorter_full_row_bound(db, full_row_days):
    deck(db, "mid", 120)
    assert purge(full_row_days=full_row_days) == {}
    assert counts(db, "mid") == WHOLE


def test_a_pack_less_scan_never_takes_a_deck_whose_pack_is_inside_the_cap(db):
    """A deck is found past the cap through its pack only: a row older than
    its pack's first delivery never takes the deck."""
    deck(db, "odd", 400, pack_days=200)
    purge(full_row_days=0)
    assert counts(db, "odd") == WHOLE


def test_one_bounded_batch_per_call(db):
    for k in range(3):
        deck(db, f"d{k}", 400 + k, packed=k != 1)
    assert purge(batch_decks=2)["decks"] == 2
    left = [j for j in ("d0", "d1", "d2") if counts(db, j)["imp"]]
    assert len(left) == 1
    assert purge(batch_decks=2)["decks"] == 1
    assert purge(batch_decks=2) == {}


def test_a_deck_whose_delete_fails_is_left_whole_for_the_next_tick(db, monkeypatch, caplog):
    """Each deck is its own transaction: one failing never takes another with
    it, and never leaves a deck half deleted."""
    deck(db, "bad", 400)
    deck(db, "good", 410)
    real_begin = db.begin
    state = {"n": 0}

    class Boom:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *exc):
            return False

    def begin():
        state["n"] += 1
        return Boom() if state["n"] == 1 else real_begin()
    monkeypatch.setattr(db, "begin", begin)
    with caplog.at_level("WARNING"):
        got = purge(full_row_days=0)
    assert got["decks"] == 1 and got["deck_impressions"] == 4   # only the deck that went
    assert sorted([counts(db, "bad"), counts(db, "good")], key=lambda c: c["imp"]) == [GONE, WHOLE]
    assert any("not deleted; retried next tick" in r.getMessage() for r in caplog.records)


def test_full_rows_go_in_bounded_chunks_resuming_where_the_last_call_stopped(db, monkeypatch):
    monkeypatch.setattr(db_module, "_FULL_ROW_PRUNE_PACKS", 2)
    for k in range(5):
        deck(db, f"p{k}", 200 - k)            # p0 is the oldest
    assert purge(full_row_chunks=1) == {"full_rows": 8}
    assert [counts(db, f"p{k}")["imp"] for k in range(5)] == [0, 0, 4, 4, 4]
    assert purge(full_row_chunks=1) == {"full_rows": 8}
    assert purge(full_row_chunks=1) == {"full_rows": 4}
    assert all(counts(db, f"p{k}") == ROWS_GONE for k in range(5))
    assert purge(full_row_chunks=1) == {}
    deck(db, "p5", 100)                         # crosses the bound later: still found
    assert purge(full_row_chunks=1) == {"full_rows": 4}


def test_a_failed_full_row_chunk_keeps_the_cursor(db, monkeypatch, caplog):
    deck(db, "p0", 120)
    monkeypatch.setattr(db_module, "_delete_old_trade_impressions", lambda *a: 0)
    monkeypatch.setattr(db_module, "_delete_old_page_store", lambda *a: 0)
    real_begin = db.begin
    state = {"fail": True}

    def begin():
        if state.pop("fail", False):
            raise RuntimeError("db down")
        return real_begin()
    monkeypatch.setattr(db, "begin", begin)
    with caplog.at_level("WARNING"):
        assert purge() == {}
    assert db_module._full_row_cursor is None and counts(db, "p0") == WHOLE
    assert any("full rows not deleted; retried next tick" in r.getMessage()
               for r in caplog.records)
    assert purge() == {"full_rows": 4}


def test_legacy_trade_impressions_go_at_the_cap(db):
    with db.begin() as conn:
        conn.execute(insert(trade_impressions_table), [
            {"user_id": "u1", "league_id": "lg", "give_player_ids": "[]",
             "receive_player_ids": "[]", "shown_at": iso(d)} for d in (500, 400, 366, 30)])
    assert purge() == {"trade_impressions": 3}
    with db.connect() as conn:
        assert list(conn.execute(select(trade_impressions_table.c.shown_at)).scalars()) \
            == [iso(30)]


@pytest.mark.parametrize("step,name", [("_delete_old_trade_impressions", "trade_impressions"),
                                       ("_delete_old_page_store", "trade_page_store")])
def test_a_failed_side_step_never_stops_the_others(db, monkeypatch, caplog, step, name):
    deck(db, "p0", 120)

    def boom(*a):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_module, step, boom)
    with caplog.at_level("WARNING"):
        assert purge() == {"full_rows": 4}
    assert any(f"{name} not deleted; retried next tick" in r.getMessage()
               for r in caplog.records)


def test_page_store_rows_past_the_cap_go_whatever_the_stores_flag(db, monkeypatch):
    """A backstop: the store's own eviction runs only while it's on."""
    monkeypatch.setattr(server, "_trade_page_store_enabled", lambda: False)
    t = trade_page_store_table
    with db.begin() as conn:
        conn.execute(insert(t), [
            {"user_id": "u1", "league_id": "lg", "scoring_format": "sf", "request_scope": scope,
             "roster_fp": "rfp", "values_snapshot_id": "vsn", "engine_version": "e",
             "config_signature": "c", "experiment_digest": "x", "deck_job_id": f"j{d}",
             "built_at": iso(d), "expires_at": iso(d - 7), "card_count": 1,
             "pages_blob": {"cards": []}, "stored_bytes": 1, "state": "ready"}
            for scope, d in (("organic:f=0.50", 366), ("organic:f=0.75", 364))])
    assert purge() == {"trade_page_store": 1}
    with db.connect() as conn:
        assert list(conn.execute(select(t.c.deck_job_id)).scalars()) == ["j364"]


def test_the_loop_step_reads_both_knobs(monkeypatch):
    seen = {}
    monkeypatch.setattr(db_module, "purge_deck_evidence",
                        lambda **kw: seen.update(kw) or {"decks": 1})
    monkeypatch.setitem(server._trade_service_mod._cfg, "deck_evidence_retention_days", 365.0)
    monkeypatch.setitem(server._trade_service_mod._cfg, "deck_evidence_full_row_days", 80.0)
    assert server._prune_deck_evidence() == {"decks": 1}
    assert seen == {"days": 365.0, "full_row_days": 80.0}


def test_the_loop_step_defaults_match_model_config(monkeypatch):
    """Dark (cap 0) until head-eng turns it on; full rows at 90 once it is."""
    seen = {}
    monkeypatch.setattr(db_module, "purge_deck_evidence", lambda **kw: seen.update(kw) or {})
    for key in ("deck_evidence_retention_days", "deck_evidence_full_row_days"):
        monkeypatch.delitem(server._trade_service_mod._cfg, key, raising=False)
    server._prune_deck_evidence()
    defaults = {k: v for k, v, _d in db_module._MODEL_CONFIG_DEFAULTS}
    assert seen == {"days": defaults["deck_evidence_retention_days"],
                    "full_row_days": defaults["deck_evidence_full_row_days"]}
    assert seen == {"days": 0.0, "full_row_days": 90.0}
    assert "deck_evidence_keep_until_epoch" not in defaults


def test_the_loop_step_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(db_module, "purge_deck_evidence",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("db")))
    with caplog.at_level("ERROR"):
        assert server._prune_deck_evidence() == {}
    assert any("deck-evidence retention failed" in r.getMessage() for r in caplog.records)


def test_the_cleanup_loop_runs_the_step():
    import inspect
    assert "_prune_deck_evidence()" in inspect.getsource(server._cleanup_loop)


def test_pack_less_decks_wait_for_the_index_and_packed_ones_never_do(db, monkeypatch, caplog):
    """The index is built off the boot path: until it exists the pack-less scan
    would read the whole table, so those decks wait (logged once)."""
    monkeypatch.setattr(db_module, "_served_index_ready", False)
    monkeypatch.setattr(db_module, "_served_index_warned", False)
    with db.begin() as conn:
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    deck(db, "packed", 400)
    deck(db, "rows-only", 380, packed=False)
    with caplog.at_level("WARNING"):
        purge()
        purge()
    assert counts(db, "packed") == GONE and counts(db, "rows-only") == WHOLE_PACKLESS
    assert sum("wait for ix_deck_impressions_served" in r.getMessage()
               for r in caplog.records) == 1
    with db.begin() as conn:
        conn.execute(text("CREATE INDEX ix_deck_impressions_served ON deck_impressions (served_at)"))
    purge()
    assert counts(db, "rows-only") == GONE


def test_the_index_is_declared_and_never_built_at_boot(tmp_path, monkeypatch):
    """A fresh DB gets it from the declaration; init_db never builds it on an
    existing table (prod: a plain CREATE INDEX there blocks writes for a full
    scan and can outlast the boot timeout)."""
    assert "ix_deck_impressions_served" in {ix.name for ix in deck_impressions_table.indexes}
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    deck_impressions_table.create(engine)                 # the table as it is today ...
    with engine.begin() as conn:                          # ... from before the index
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.init_db()
    with engine.connect() as conn:
        got = [r[1] for r in conn.execute(text("PRAGMA index_list('deck_impressions')"))]
    assert "ix_deck_impressions_served" not in got


def test_the_script_builds_it_on_an_existing_table_and_check_writes_nothing(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts/create_evidence_retention_index.py"
    spec = importlib.util.spec_from_file_location("create_evidence_retention_index", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    deck_impressions_table.create(engine)                 # the table as it is today ...
    with engine.begin() as conn:                          # ... from before the index
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    monkeypatch.setattr(db_module, "engine", engine)
    assert script.main(["--check"]) == 0 and script.state(engine) == "missing"
    assert script.main([]) == 0 and script.state(engine) == "valid"
    assert script.build(engine) == "valid"                # idempotent


# ── #523 QA P1-1: account rights reach outcomes whose rows the prune deleted ──

@pytest.mark.parametrize("pruned", [False, True])
def test_export_and_deletion_reach_a_packed_decks_outcomes_after_its_rows_go(db, pruned):
    """The full-row bound deletes a packed deck's rows and keeps its outcomes
    by contract id. The viewer's export still carries every one of them, and
    deleting the account removes them and unlinks the executed-trade links
    (accounts, through deck_pack_contract_ids), so none is kept forever."""
    import backend.accounts as accounts
    from backend.database import suggestion_trade_links_table as links
    deck(db, "mine", 120)                      # outcomes: a viewed (row) and a like (row-less)
    deck(db, "theirs", 120, user="u2")
    with db.begin() as conn:
        conn.execute(insert(links).values(transaction_id="t1", league_id="lg", was_recommended=1,
                                          matched_impression_id="mine:5",
                                          computed_at=iso(0)))
    if pruned:
        assert purge()["full_rows"] == 8
        assert counts(db, "mine") == ROWS_GONE
    o = deck_outcomes_table.c.impression_id
    exported = accounts.export_user_data("u1")["tables"]["deck_outcomes"]
    assert sorted(r["impression_id"] for r in exported) == ["mine:0", "mine:5"]
    accounts._delete_user_data("u1")
    with db.connect() as conn:
        left = sorted(conn.execute(select(o)).scalars())
        link = conn.execute(select(links.c.matched_impression_id)).scalar()
    assert left == ["theirs:0", "theirs:5"] and link is None


def test_deck_pack_contract_ids_lists_every_card_of_the_users_packs(db):
    deck(db, "a", 120)
    deck(db, "b", 120, packed=False)
    deck(db, "c", 120, user="u2")
    with db.connect() as conn:
        got = db_module.deck_pack_contract_ids(conn, {"u1"})
    assert got == [f"a:{k}" for k in range(6)]          # card_count = n + 3


# ── #523 QA P2/P3s ────────────────────────────────────────────────────────────

def test_exact_contract_ids_never_reach_a_deck_whose_id_extends_this_ones(db):
    """Deck "abc"'s card 1 is "abc:1", which is also deck "abc:1"'s prefix: a
    LIKE or a string range would take "abc:1:0" too. Exact ids never do."""
    deck(db, "abc", 400)
    deck(db, "abc:1", 30)
    deck(db, "abcd", 30)
    o, r = deck_outcomes_table.c.impression_id, trade_pass_reasons_table.c.impression_id

    def left(col, table):
        with db.connect() as conn:
            return sorted(conn.execute(select(col).select_from(table)).scalars())
    purge(full_row_days=0)
    assert left(o, deck_outcomes_table) == left(r, trade_pass_reasons_table) == [
        "abc:1:0", "abc:1:5", "abcd:0", "abcd:5"]


@pytest.mark.parametrize("packed", [True, False])
def test_the_cap_is_the_first_delivery_not_the_last(db, packed):
    """A deck first delivered 400 days ago and served again 30 days ago goes
    at the 365-day cap: the clock is its first delivery."""
    deck(db, "old", 400, packed=packed)
    with db.begin() as conn:
        conn.execute(deck_impressions_table.update()
                     .where(deck_impressions_table.c.deck_job_id == "old")
                     .values(delivered_at=iso(30)))
    purge(full_row_days=0)
    assert counts(db, "old") == GONE


def test_legacy_trade_impressions_go_by_an_id_bound_in_batches(db):
    """Only past the cap, and among the oldest `limit` ids; a table smaller
    than the batch is read whole."""
    with db.begin() as conn:
        conn.execute(insert(trade_impressions_table), [
            {"user_id": "u1", "league_id": "lg", "give_player_ids": "[]",
             "receive_player_ids": "[]", "shown_at": iso(d)} for d in (500, 450, 400, 30, 380)])
    assert db_module._delete_old_trade_impressions(iso(365), 2) == 2    # ids 1, 2
    assert db_module._delete_old_trade_impressions(iso(365), 2) == 1    # id 3 (4 is recent)
    assert db_module._delete_old_trade_impressions(iso(365), 100) == 1  # id 5 (380 days)
    with db.connect() as conn:
        assert list(conn.execute(select(trade_impressions_table.c.shown_at)).scalars()) == [iso(30)]
    assert db_module._delete_old_trade_impressions(iso(365), 100) == 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 1e9, 30.0])
def test_a_refused_bound_is_logged_once_and_never_raises(db, caplog, bad):
    deck(db, "old", 400)
    with caplog.at_level("WARNING"):
        for _ in range(3):
            assert purge(days=bad) == {}
            purge(full_row_days=bad)                      # the cap still runs
    assert counts(db, "old") == GONE
    refusals = [r.getMessage() for r in caplog.records if "nothing deleted under it" in r.getMessage()]
    assert len(refusals) == 2                             # once per knob, not every tick
    assert all(r.levelname == "WARNING" for r in caplog.records)


def test_a_dropped_index_is_noticed_at_the_next_check(db, monkeypatch, caplog):
    """A seen index is checked again after _SERVED_INDEX_RECHECK_S: dropped,
    the pack-less scan stops (and says so)."""
    assert db_module._deck_impressions_served_index_ready() is True
    with db.begin() as conn:
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    assert db_module._deck_impressions_served_index_ready() is True        # cached within the hour
    monkeypatch.setattr(db_module, "_served_index_checked", -db_module._SERVED_INDEX_RECHECK_S)
    with caplog.at_level("WARNING"):
        assert db_module._deck_impressions_served_index_ready() is False
    assert any("wait for ix_deck_impressions_served" in r.getMessage() for r in caplog.records)
