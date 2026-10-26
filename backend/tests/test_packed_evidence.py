"""ADR-025 stage 2: packed deck evidence (S8), flag trade.packed_evidence.

Spec: docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6-§9;
models-lead R2.4 addendum §2-§3 and R4.2 (U1-U8).

Harness: test_deferred_evidence's `deferred` (p1's real worker and routes,
flag on, evidence writes inline).
"""
import json
from pathlib import Path

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.feature_flags import DEFAULT_FLAGS, FLAG_KEYS
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, run_job, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import (  # noqa: F401  (fixture)
    HEADERS, LEAGUE, UID, by_index, deferred, deferred_deck, outcomes, rows)
from backend.database import league_members_table
from sqlalchemy import update
from backend.tests.test_trade_page_store import generate  # noqa: E402
from backend.eval import contract

REPO = Path(__file__).resolve().parents[2]


# ── Item 6: the flag ────────────────────────────────────────────────────────

def test_the_packed_evidence_flag_is_registered_and_off():
    """The 3-touch mirror (FLAG_KEYS, config/features.json, the release
    fixture). It ships off; it goes on before trade.first_page_store (R2.4 §3)."""
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads((REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert "trade.packed_evidence" in FLAG_KEYS and DEFAULT_FLAGS["trade.packed_evidence"] is False
    assert features["trade.packed_evidence"] is False
    assert release["trade.packed_evidence"] == features["trade.packed_evidence"]


# ── Item 4: the page_store marker ───────────────────────────────────────────

def marker(row):
    return json.loads(row["features_json"]).get("page_store")


def test_every_row_of_a_page_scoped_deck_carries_the_page_store_marker(deferred):
    """R2.4 addendum §3: full rows and narrow ghosts alike, so a paged deck is
    never read as a legacy one."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60, ghost_every=9)
    assert server._trade_jobs[job_id]["page_scope"]
    status(client, job_id, 0)
    written = rows(engine)
    assert {r["is_ghost"] for r in written} == {0, 1}
    assert {marker(r) for r in written} == {1}


def test_a_real_page_scoped_job_marks_its_rows_and_a_flag_off_job_does_not(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id = run_job()
    status(client, job_id, 0)
    assert rows(engine) and {marker(r) for r in rows(engine)} == {1}
    with engine.begin() as conn:
        conn.execute(db_module.deck_impressions_table.delete())
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    off = run_job(force_fresh=True)                        # flag off: rows at build, no page_scope
    assert "page_scope" not in server._trade_jobs[off]
    assert rows(engine)
    assert all("page_store" not in json.loads(r["features_json"]) for r in rows(engine))


# ── Item 2 (R4.2 U2): the deterministic impression id ───────────────────────

def is_uuid_hex(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def test_every_non_ghost_row_has_the_contract_id_and_ghosts_keep_a_uuid(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60, ghost_every=9)
    status(client, job_id, 0)
    written = rows(engine)
    assert {r["impression_id"] for r in written if not r["is_ghost"]} == {
        contract.card_impression_id(job_id, r["card_index"]) for r in written if not r["is_ghost"]}
    assert all(is_uuid_hex(r["impression_id"]) for r in written if r["is_ghost"])


def test_the_page_payload_carries_the_contract_id_and_an_outcome_with_it_lands(deferred):
    """The client echoes the id untouched (mobile api/trades.ts); it passes the
    outcome routes' 1-64-character check and their ownership read."""
    client, engine, _ = deferred
    job_id = run_job()
    built = [c["impression_id"] for c in server._trade_jobs[job_id]["cards"]]
    assert built == [contract.card_impression_id(job_id, i) for i in range(len(built))]
    for body in (generate(client, page=1).get_json(), status(client, job_id, 0).get_json()):
        sent = [c["impression_id"] for c in body["cards"]]   # S0's I-1 may drop some (gaps)
        assert sent and set(sent) <= set(built) and sent == sorted(sent, key=built.index)
    iid = body["cards"][0]["impression_id"]
    assert 1 <= len(iid) <= 64
    server._save_deck_outcome_safe(iid, "like", acting_user_id=UID)
    assert [o["impression_id"] for o in outcomes(engine)] == [iid]


def test_rows_written_at_build_keep_uuid_ids(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    run_job()
    assert rows(engine) and all(is_uuid_hex(r["impression_id"]) for r in rows(engine))


# ── Item 5: C-b withdrawals (deck_card_withdrawals) and the sticky drop ──────

def withdrawals(engine):
    return {r["card_index"]: r for r in rows(engine, db_module.deck_card_withdrawals_table)}


def own_all_but(engine, *card_indexes):
    """The viewer owns every synthetic card's give asset but these."""
    with engine.begin() as conn:
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps(
                         ["g2"] + [f"mine{i}" for i in range(400) if i not in card_indexes])))


def deck_ids(body):
    return [c["impression_id"] for c in body["cards"]]


def test_served_before_is_recorded_both_ways_and_the_drop_is_sticky(deferred):
    """Card 3 was delivered on page 1, then withdrawn (served_before 1); card
    40 is withdrawn before it was ever sent (served_before 0). Neither is
    served again once its roster moves back."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, store=False)
    first = status(client, job_id, 0).get_json()
    assert contract.card_impression_id(job_id, 3) in deck_ids(first)
    own_all_but(engine, 3, 40)
    status(client, job_id, 0)                              # a repeat poll: card 3 withdrawn
    status(client, job_id, 30)                             # the next page: card 40 withdrawn
    got = withdrawals(engine)
    assert set(got) == {3, 40}
    assert (got[3]["served_before"], got[40]["served_before"]) == (1, 0)
    assert {(r["reason"], r["user_id"], r["league_id"]) for r in got.values()} == {("i1_dropped", UID, LEAGUE)}
    assert got[40]["impression_id"] == contract.card_impression_id(job_id, 40)
    own_all_but(engine)                                    # the rosters move back
    again = deck_ids(status(client, job_id, 0).get_json()) + deck_ids(status(client, job_id, 30).get_json())
    assert not {contract.card_impression_id(job_id, i) for i in (3, 40)} & set(again)
    assert len(again) == 58
    written = by_index(engine)
    assert written.get((0, 40), {}).get("delivered_at") is None   # W0: never a delivered row
    assert written[(0, 3)]["delivered_at"] is not None     # delivered before: keeps its row


def test_the_first_withdrawal_wins():
    rows_ = [{"deck_job_id": "d", "card_index": 7, "user_id": "u", "league_id": "l",
              "reason": "i1_dropped", "first_withdrawn_at": at, "served_before": served,
              "impression_id": "d:7"} for at, served in (("2026-10-26T00:00:00+00:00", 0),
                                                         ("2026-10-26T01:00:00+00:00", 1))]
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    db_module.metadata.create_all(engine)
    real, db_module.engine = db_module.engine, engine
    try:
        assert db_module.record_deck_withdrawals(rows_[:1]) == 1
        assert db_module.record_deck_withdrawals(rows_) == 0
        [kept] = db_module.load_deck_withdrawals("d")
        assert (kept["first_withdrawn_at"], kept["served_before"]) == ("2026-10-26T00:00:00+00:00", 0)
    finally:
        db_module.engine = real


def test_repeat_polls_record_a_withdrawal_once(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, store=False)
    own_all_but(engine, 5)
    for _ in range(3):
        status(client, job_id, 0)
    assert list(withdrawals(engine)) == [5]


def test_the_sticky_drop_holds_across_a_restart(deferred):
    """Withdrawn on a stored page; after the job leaves the process (and the
    process cache is gone) the table keeps it from returning."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120)
    own_all_but(engine, 4)
    page = client.get(f"/api/trades/status?deck={job_id}&cursor=0", headers=HEADERS).get_json()
    assert contract.card_impression_id(job_id, 4) not in deck_ids(page)
    assert list(withdrawals(engine)) == [4]
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    server._deck_withdrawn_cache.clear()
    own_all_but(engine)                                    # its roster moved back
    again = client.get(f"/api/trades/status?deck={job_id}&cursor=0", headers=HEADERS).get_json()
    assert again["cards"] and contract.card_impression_id(job_id, 4) not in deck_ids(again)
    assert len(again["cards"]) == 29


def test_a_w0_card_never_gets_a_delivered_row(deferred, monkeypatch):
    """models-eng's one conflict: a never-delivered withdrawal (W0) whose row
    has a delivered_at. Card 15 has an undelivered first30 row (10-card
    pages), is withdrawn on page 2, and is never sent after."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_trade_page_size", lambda: 10)
    job_id, *_ = deferred_deck(120)
    status(client, job_id, 0)
    assert by_index(engine)[(0, 15)]["delivered_at"] is None
    own_all_but(engine, 15)
    status(client, job_id, 10)
    own_all_but(engine)
    status(client, job_id, 10)
    assert withdrawals(engine)[15]["served_before"] == 0
    assert by_index(engine)[(0, 15)]["delivered_at"] is None


def test_the_flag_off_path_records_no_withdrawal(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    job_id = run_job()
    cards = server._trade_jobs[job_id]["cards"]
    assert cards
    with engine.begin() as conn:                           # the viewer owns nothing
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))
    body = client.get(f"/api/trades/status?job_id={job_id}", headers=HEADERS).get_json()
    assert len(body["cards"]) < len(cards)                 # I-1 dropped some
    assert rows(engine, db_module.deck_card_withdrawals_table) == []


def test_withdrawals_are_covered_by_account_deletion_and_export():
    """C7 (v): test_account_deletion_coverage runs over every table listed."""
    from backend import accounts
    assert "deck_card_withdrawals" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert ("deck_card_withdrawals", "deck_card_withdrawals_table", "user_id", ()) in accounts._EXPORT_TABLES
