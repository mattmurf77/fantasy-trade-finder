"""ADR-025 stage 2: packed deck evidence (S8), flag trade.packed_evidence.

Spec: docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6-§9;
models-lead R2.4 addendum §2-§3 and R4.2 (U1-U8).

Harness: test_deferred_evidence's `deferred` (p1's real worker and routes,
flag on, evidence writes inline).
"""
import collections
import json

import pytest
from pathlib import Path

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.feature_flags import DEFAULT_FLAGS, FLAG_KEYS
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, run_job, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import (  # noqa: F401  (fixture)
    HEADERS, LEAGUE, UID, by_index, deferred, deferred_deck, outcomes, rows, threaded)
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


# ── Item 1 (S8): the packed deck-evidence writer; item 3 (R4.2): full row on view ──

from backend.eval import evidence_pack  # noqa: E402
from backend.tests.test_deferred_evidence import archive_id  # noqa: E402

PACKS = db_module.deck_evidence_packs_table
REAL_START = server._start_deck_evidence_thread            # before any fixture inlines it


def pack_of(engine, job_id):
    with engine.connect() as conn:
        row = conn.execute(PACKS.select().where(PACKS.c.run_id == job_id)).mappings().first()
    return dict(row) if row is not None else None


def unpack(row):
    return evidence_pack.unpack_run(evidence_pack.PackedRun(
        row["pack_version"], row["header_json"], bytes(row["cards_blob"]), row["checksum"],
        row["card_count"]))


def packed_deck(n, **kw):
    return deferred_deck(n, packed=True, **kw)


def view(job_id, index, action="viewed"):
    """An outcome posted with the card's contract id (the swipe/view routes' writer)."""
    server._save_deck_outcome_safe(contract.card_impression_id(job_id, index), action,
                                   acting_user_id=UID)


def restart():
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    server._deck_withdrawn_cache.clear()
    server._deck_pack_states.clear()
    server._deck_live_stamped.clear()
    server._deck_held.clear()                              # U4: a new process held none of them
    server._deck_evicted_at.clear()
    server._deck_f5_dropped.clear()


def test_s8_the_first_delivery_writes_the_first_30_the_ghosts_and_one_pack_of_every_card(deferred):
    client, engine, _ = deferred
    job_id, served, ghosts, ev, _ = packed_deck(120, ghost_every=9)
    status(client, job_id, 0)
    written = rows(engine)
    full = sorted(r["card_index"] for r in written if not r["is_ghost"])
    assert full == list(range(30))                         # C4; the rest is packed (R4.2)
    assert {r["evidence_tier"] for r in written if not r["is_ghost"]} == {"first30"}
    assert {r["evidence_tier"] for r in written if r["is_ghost"]} == {"ghost"}
    row = pack_of(engine, job_id)
    run, cards = unpack(row)
    assert row["card_count"] == len(served) == 120 and [c["card_index"] for c in cards] == list(range(120))
    assert row["served_at"] == written[0]["served_at"]     # the first delivery (F2)
    assert run["deliveries"] == [[29, row["served_at"]]] and run["page_store"] == 1
    assert run["retired"] is False and run["upgrade_misses"] == {"restart_split": 0, "evicted_split": 0, "other": 0}
    job = server._trade_jobs[job_id]
    assert (run["values_snapshot_id"], run["config_ref"]) == (job["values_snapshot_id"],
                                                              job["request_signature"])
    assert run["built_at"] < row["served_at"]
    [cand] = rows(engine, db_module.deck_candidate_sets_table)
    assert cand["candidates_json"] == "" and cand["candidates_packed"] is not None
    _r, members = evidence_pack.unpack_candidates(evidence_pack.PackedCandidates(
        cand["cand_pack_version"], bytes(cand["candidates_packed"])))
    assert len(members) == cand["size"] and evidence_pack.candidate_set_hash(members) == cand["set_hash"]


def test_s8_a_later_delivery_rewrites_only_header_and_checksum(deferred):
    from sqlalchemy import event
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    before = pack_of(engine, job_id)
    seen = []
    listen = lambda conn, cursor_, statement, params, *a: seen.append((statement, params))
    event.listen(engine, "before_cursor_execute", listen)
    try:
        status(client, job_id, 30)
    finally:
        event.remove(engine, "before_cursor_execute", listen)
    updates = [st for st, _p in seen if st.lstrip().upper().startswith("UPDATE DECK_EVIDENCE_PACKS")]
    assert len(updates) == 1 and "cards_blob" not in updates[0]
    assert "header_json" in updates[0] and "checksum" in updates[0]
    after = pack_of(engine, job_id)
    assert bytes(after["cards_blob"]) == bytes(before["cards_blob"])
    run, _cards = unpack(after)                            # the checksum holds
    assert [d[0] for d in run["deliveries"]] == [29, 59]
    assert not [r for r in rows(engine) if not r["is_ghost"] and r["card_index"] >= 30]


def test_s8_the_incremental_checksum_equals_pack_runs():
    """models-eng's condition 1: the v1 checksum's prefix is fixed at build."""
    cards = [{"card_index": i, "trade_hash": f"{i:016x}", "base_score": i / 7, "shape": "1x1",
              "user_id": "u", "league_id": "l", "deck_job_id": "d", "served_at": "t"} for i in range(50)]
    first = evidence_pack.pack_run({"deliveries": [[9, "a"]], "retired": False}, cards, card_count=50)
    _run, unpacked = evidence_pack.unpack_run(first)
    state = server._PackState("u", json.loads(first.header_json), unpacked)
    assert state.render() == (first.header_json, first.checksum)
    state.run["deliveries"].append([29, "b"])
    state.run.update(retired=True, retired_at="c")
    again = evidence_pack.pack_run(state.run, cards, card_count=50)
    assert state.render() == (again.header_json, again.checksum)
    assert again.cards_blob == first.cards_blob


def test_r42_a_first_view_upgrades_a_packed_card_to_a_viewed_row(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 30)
    view(job_id, 45)
    got = by_index(engine)[(0, 45)]
    features = json.loads(got["features_json"])
    assert got["evidence_tier"] == "viewed" and "give_value_band" in features   # the wide row
    assert got["delivered_at"] == unpack(pack_of(engine, job_id))[0]["deliveries"][1][1]
    assert got["assets_json"] and got["served_at"] == pack_of(engine, job_id)["served_at"]
    view(job_id, 45, "like")
    assert [o["action"] for o in outcomes(engine)] == ["viewed", "like"]
    assert len([r for r in rows(engine) if r["card_index"] == 45]) == 1


def test_r42_after_a_restart_a_stored_card_upgrades_from_the_blob(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 30)
    restart()
    view(job_id, 50)
    got = by_index(engine)[(0, 50)]
    assert got["evidence_tier"] == "viewed" and got["assets_json"]
    assert "give_value_band" in json.loads(got["features_json"])
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {"restart_split": 0, "evicted_split": 0, "other": 0}
    assert [o["impression_id"] for o in outcomes(engine)] == [contract.card_impression_id(job_id, 50)]


def test_s8_an_upgrade_past_the_recorded_deliveries_writes_no_delivery(deferred, monkeypatch, caplog):
    """models-eng's review of #416: page 2's header update was lost (the
    process died). The outcome on its card 45, after the restart, upgrades
    the card but never writes a delivery for it (that would hide the loss and
    bias e(k)'s tail; eval excludes the deck as incomplete_deck); it logs."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    real = db_module.update_deck_evidence_pack_header
    monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", lambda *a: True)   # lost
    status(client, job_id, 30)
    restart()
    monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", real)
    with caplog.at_level("WARNING"):
        view(job_id, 45)
    assert [d[0] for d in unpack(pack_of(engine, job_id))[0]["deliveries"]] == [29]
    assert by_index(engine)[(0, 45)]["evidence_tier"] == "viewed" and outcomes(engine)
    assert any(f"upgrade past last_delivered job={job_id} index=45 last=29" in r.getMessage()
               for r in caplog.records)


def test_s8_the_shutdown_drain_flushes_pending_pack_updates(deferred, threaded, monkeypatch):
    """models-eng's condition 4: Render's SIGTERM drain. An update still in
    flight lands before the drain returns."""
    import time as _time
    client, engine = deferred[0], threaded
    monkeypatch.setattr(server, "_start_deck_evidence_thread", REAL_START)   # tracked threads
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    server._deck_evidence_drain(5)
    real = server._deck_pack_flush_header
    monkeypatch.setattr(server, "_deck_pack_flush_header",
                        lambda ev, **kw: (_time.sleep(0.5), real(ev, **kw))[1])
    status(client, job_id, 30)
    assert [d[0] for d in unpack(pack_of(engine, job_id))[0]["deliveries"]] == [29]
    assert server._deck_evidence_drain(5) == 0
    assert [d[0] for d in unpack(pack_of(engine, job_id))[0]["deliveries"]] == [29, 59]


def test_s8_a_never_delivered_withdrawal_is_packed_never_a_row_never_upgraded(deferred):
    """models-eng's condition 2: cards_blob holds W0 cards; eval removes them."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    own_all_but(engine, 40)
    status(client, job_id, 30)                             # card 40 withdrawn, never delivered
    assert withdrawals(engine)[40]["served_before"] == 0
    _run, cards = unpack(pack_of(engine, job_id))
    assert 40 in {c["card_index"] for c in cards}
    view(job_id, 40)
    assert (0, 40) not in by_index(engine) and outcomes(engine) == []


def test_s8_a_failed_first_write_still_packs_a_card_withdrawn_at_that_serve(deferred, monkeypatch):
    """#420 QA P2: the first attempt's rows are fixed on `ev`. plan() drops a
    never-delivered withdrawn card's row at the first write; if that write's
    rows transaction fails, the retry must pack the same N cards, or pack_run
    refuses (card_count N-1) at every later delivery and the deck never packs."""
    from sqlalchemy.exc import OperationalError
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    own_all_but(engine, 5)                                 # card 5 I-1-dropped at the first serve
    real, calls = db_module.save_deck_evidence, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("INSERT INTO deck_impressions", {}, Exception("database is locked"))
        return real(*args, **kwargs)

    monkeypatch.setattr(db_module, "save_deck_evidence", flaky)
    status(client, job_id, 0)                              # the first write fails
    assert pack_of(engine, job_id) is None
    status(client, job_id, 30)                             # the next delivery retries it
    _run, cards = unpack(pack_of(engine, job_id))
    assert len(cards) == 120 and 5 in {c["card_index"] for c in cards}


def test_s8_an_archive_deck_writes_every_card_and_a_view_raises_it_to_viewed(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, job_id=archive_id(True))
    status(client, job_id, 0)
    tiers_ = {r["card_index"]: r["evidence_tier"] for r in rows(engine) if not r["is_ghost"]}
    assert set(tiers_) == set(range(120)) and pack_of(engine, job_id) is not None
    assert {tiers_[i] for i in range(30)} == {"first30"} and {tiers_[i] for i in range(30, 120)} == {"archive"}
    status(client, job_id, 60)
    view(job_id, 70)
    assert by_index(engine)[(0, 70)]["evidence_tier"] == "viewed"
    assert by_index(engine)[(0, 70)]["delivered_at"] is not None


def test_s8_a_superseded_or_capped_deck_is_retired_once(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    assert server._retire_deck_evidence() == 0             # current, fresh: not yet
    key = server._trade_jobs[job_id]["key"]
    server._trade_jobs_by_key[key] = "a-newer-deck"        # superseded for its key
    assert server._retire_deck_evidence() == 1
    run, _ = unpack(pack_of(engine, job_id))
    assert run["retired"] is True and run["retired_at"] >= pack_of(engine, job_id)["served_at"]
    assert server._retire_deck_evidence() == 0             # once
    other, *_ = packed_deck(60, job_id="deck-capped")
    status(client, other, 0)
    monkeypatch.setattr(server, "_DECK_DISPLAY_CAP_S", 0)  # the 24 h display cap
    assert server._retire_deck_evidence() == 1
    assert unpack(pack_of(engine, other))[0]["retired"] is True


def test_s8_flag_off_and_stage_1_write_no_pack_and_json_candidates(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60)                         # the store on, packed evidence off
    status(client, job_id, 0)
    assert rows(engine, PACKS) == []
    assert {r["candidates_packed"] for r in rows(engine, db_module.deck_candidate_sets_table)} == {None}
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False,
                                             "trade.packed_evidence": True})
    run_job(force_fresh=True)                              # the store off: rows at build
    assert rows(engine, PACKS) == []


def test_s8_a_real_job_admitted_with_the_flag_on_is_packed(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.packed_evidence": True})
    job_id = run_job()
    assert server._trade_jobs[job_id]["evidence"].packed
    status(client, job_id, 0)
    row = pack_of(engine, job_id)
    assert row is not None and row["card_count"] == len(server._trade_jobs[job_id]["cards"])


def test_s8_the_pack_round_trips_through_the_eval_reader_to_the_full_rows(deferred):
    """The golden: a packed deck (the first 30 as rows, the rest packed) and
    the same deck with every card a full row read back through
    eval.data.load_decks to the same cards on every contract key, the same
    delivered positions (U1) and the same e(k) inputs."""
    from sqlalchemy import create_engine, insert
    from backend.eval.data import card_dict, load_decks
    client, engine, _ = deferred
    job_id, served, ghosts, ev, _ = packed_deck(120, ghost_every=9)
    status(client, job_id, 0)
    status(client, job_id, 30)
    with ev.lock:                                          # the build-time snapshots still held
        held = [server._unpack_row(packed) for _iid, (_i, packed) in ev.rows.items()]
    full = create_engine("sqlite:///:memory:")
    db_module.metadata.create_all(full)
    first = rows(engine)
    served_at = pack_of(engine, job_id)["served_at"]
    with ev.lock:                                          # retired: final for eval v5 too
        ev.pack.run.update(retired=True, retired_at=served_at)
        ev.pack_dirty = True
    server._deck_pack_flush_header(ev)
    with full.begin() as conn:
        conn.execute(insert(db_module.deck_impressions_table), first + [
            {**{c.name: r.get(c.name) for c in db_module.deck_impressions_table.columns},
             "served_at": served_at, "evidence_tier": "archive"} for r in held])
        conn.execute(insert(PACKS), [pack_of(engine, job_id)])

    attribution = server._PACK_ATTRIBUTION_COLUMNS

    def read(eng):
        """card_dict plus a full row's attribution columns (a packed card
        carries them in the pack), restricted to the contract keys and the id."""
        on_rows = {r["impression_id"]: r for r in rows(eng)}
        [deck] = load_decks(engine=eng)
        out = []
        for c in deck.cards:
            d = card_dict(c)
            if c.impression_id in on_rows and not c.is_ghost:
                d.update({k: on_rows[c.impression_id][k] for k in attribution})
            out.append((c.card_index, c.is_ghost, c.delivered,
                        {k: v for k, v in d.items() if k in evidence_pack.CONTRACT_KEYS
                         or k == "impression_id"}))
        return out

    packed_read, full_read = read(engine), read(full)
    assert len(packed_read) == len(full_read) == 120 + len(ghosts)
    assert packed_read == full_read
    assert [i for i, ghost, delivered, _ in packed_read if delivered and not ghost] == list(range(60))


# ── R6.2's condition: the prepared payload readers key on candidates_packed ──

def candidate_row(n=40):
    from backend import prepared_trade_payload as v1
    members = [{"trade_hash": v1._trade_hash([f"g{i}"], [f"r{i}"], "opp"), "partner": "opp",
                "give": [f"g{i}"], "receive": [f"r{i}"], "base_score": i / 3, "in_deck": i % 2 == 0}
               for i in range(n)]
    row = {"candidate_set_id": "cs", "deck_job_id": "job", "user_id": "u", "league_id": "l",
           "size": n, "set_hash": evidence_pack.candidate_set_hash(members),
           "candidates_json": json.dumps(members), "created_at": "2026-10-26T00:00:00+00:00"}
    return row, members


def test_a_packed_candidate_row_reads_as_its_members_in_both_payload_versions():
    from backend import prepared_trade_payload as v1, prepared_trade_payload_v2 as v2
    row, members = candidate_row()
    packed = server._pack_candidate_set(row)
    assert packed["candidates_json"] == "" and packed["candidates_packed"]
    scope = {"user_id": "u", "league_id": "l", "job_id": "job"}
    assert v1._candidate(packed, **scope) == v1._candidate(row, **scope) == members
    assert v2._candidate(packed, "u", "l", "job") == v2._candidate(row, "u", "l", "job")


def test_a_corrupt_candidate_pack_is_refused_never_read_as_empty():
    import pytest
    from backend import prepared_trade_payload as v1, prepared_trade_payload_v2 as v2
    row, _members = candidate_row()
    packed = server._pack_candidate_set(row)
    broken = {**packed, "candidates_packed": packed["candidates_packed"][:-3] + b"xyz"}
    with pytest.raises(ValueError, match="candidate_pack_integrity"):
        v1._candidate(broken, user_id="u", league_id="l", job_id="job")
    with pytest.raises(ValueError, match="candidate_pack_integrity"):
        v2._candidate(broken, "u", "l", "job")
    big = {**packed, "candidates_packed": b"\0" * (v2.MAX_CANDIDATE_BYTES + 1)}
    with pytest.raises(ValueError, match="candidate_pack_bytes"):
        v2._candidate(big, "u", "l", "job")


# ── R4.2 U8: full rows per served deck, re-measured on the real owner path ──

from backend.tests.test_deferred_evidence import owner_deck  # noqa: E402
from backend.tests.test_owner_batch_publication import sized_exclusive  # noqa: E402,F401  (fixture)
from backend.tests.test_owner_generator_routes import harness, owner_harness, worker  # noqa: E402,F401
from backend.tests.test_owner_only_routes import exclusive  # noqa: E402,F401  (fixture)


@pytest.mark.parametrize("sized_exclusive", [2354], indirect=True)   # B15's measured production deck
def test_u8_full_rows_per_served_deck_with_packing(sized_exclusive, monkeypatch):
    """Stage 1 wrote a full row for every card at the first delivery; packed,
    the first 30 (and the viewed ones later), the rest in one pack row."""
    fixture, count = sized_exclusive
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    real_init = server._DeckEvidence.__init__

    def packed_init(self, *a, **k):
        real_init(self, *a, **k)
        self.packed = True

    monkeypatch.setattr(server._DeckEvidence, "__init__", packed_init)
    original = server._ghost_holdout_active

    def telemetry_on(*args):                               # the worker helper turns it off
        monkeypatch.setattr(server, "_suggestion_telemetry_enabled", lambda: True)
        return original(*args)

    monkeypatch.setattr(server, "_ghost_holdout_active", telemetry_on)
    job, ev, engine = owner_deck(fixture, monkeypatch, deferred_mode=True)
    with ev.lock:
        stage1_bytes = sum(len(json.dumps(server._unpack_row(p))) for _, p in ev.rows.values())
    server._deck_evidence_delivered(ev, job["cards"][:30])
    written = [r for r in rows(engine) if not r["is_ghost"]]
    row_bytes = sum(len(json.dumps({k: v for k, v in r.items()})) for r in written)
    pack = pack_of(engine, job["job_id"])
    [cand] = rows(engine, db_module.deck_candidate_sets_table)
    _r, members = evidence_pack.unpack_candidates(evidence_pack.PackedCandidates(
        cand["cand_pack_version"], bytes(cand["candidates_packed"])))
    print(f"\n[U8] owner deck cards={count}: full rows written {len(written)} "
          f"({row_bytes / 1024:.0f} KiB), against stage 1's {count} ({stage1_bytes / 2**20:.1f} MiB raw); "
          f"pack cards_blob {len(pack['cards_blob']) / 1024:.1f} KiB + header {len(pack['header_json'])} B; "
          f"candidate set {len(members)} members packed {len(cand['candidates_packed']) / 1024:.1f} KiB "
          f"vs JSON {len(json.dumps(members)) / 1024:.1f} KiB")
    assert len(written) == 30 and pack["card_count"] == count


# ── #417 (eval v5) contract §6/§8 alignment ─────────────────────────────────

def test_served_before_is_written_as_exactly_0_or_1(deferred):
    """v5 reads any served_before other than 0 as 1."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, store=False)
    status(client, job_id, 0)
    own_all_but(engine, 3, 40)
    status(client, job_id, 0)
    status(client, job_id, 30)
    values = [r["served_before"] for r in rows(engine, db_module.deck_card_withdrawals_table)]
    assert sorted(values) == [0, 1] and {type(v) for v in values} == {int}


def test_a_stored_path_withdrawal_of_a_delivered_unseen_card_was_served_before(deferred):
    """models-eng's blocking find on #416: card 45 was delivered (page 2) but
    never viewed, so it has no row, only its place in the pack's deliveries.
    Withdrawn after a restart (the stored path), it was served before."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 30)
    restart()
    own_all_but(engine, 45)
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    assert (0, 45) not in by_index(engine)
    assert withdrawals(engine)[45]["served_before"] == 1


def test_interleaved_header_updates_from_two_instances_lose_nothing(deferred):
    """models-eng's review: a deploy overlap, two instances updating one pack.
    Each appends a different intermediate boundary, one also a duplicate index
    with a later time; one counts a miss, the other retires the deck. After
    the CAS retry the stored run holds the union (the earlier time for the
    duplicate), the miss, and the retirement."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    first = unpack(pack_of(engine, job_id))[0]["deliveries"]
    restart()
    a = server._deck_pack_state(job_id, UID)               # instance A
    server._deck_pack_states.clear()
    b = server._deck_pack_state(job_id, UID)               # instance B, the same stored header
    assert a is not b and a.checksum == b.checksum
    a.run["deliveries"] = first + [[59, "2026-10-27T00:00:59+00:00"], [89, "2026-10-27T00:01:29+00:00"]]
    a.run["upgrade_miss_cards"] = {"91": "restart_split"}
    a.run["upgrade_misses"] = server._upgrade_miss_tally(a.run["upgrade_miss_cards"])
    assert server._deck_pack_commit(job_id, a)
    b.run["deliveries"] = first + [[59, "2026-10-27T00:09:59+00:00"], [74, "2026-10-27T00:01:14+00:00"]]
    b.run.update(retired=True, retired_at="2026-10-27T01:00:00+00:00",
                 upgrade_miss_cards={"95": "evicted_split", "96": "evicted_split"})
    b.run["upgrade_misses"] = server._upgrade_miss_tally(b.run["upgrade_miss_cards"])
    assert server._deck_pack_commit(job_id, b)             # a CAS miss, merged, retried
    run, _cards = unpack(pack_of(engine, job_id))          # the checksum holds
    assert run["deliveries"] == first + [[59, "2026-10-27T00:00:59+00:00"],
                                         [74, "2026-10-27T00:01:14+00:00"],
                                         [89, "2026-10-27T00:01:29+00:00"]]
    assert run["upgrade_miss_cards"] == {"91": "restart_split", "95": "evicted_split",
                                         "96": "evicted_split"}      # the union
    assert (run["upgrade_misses"], run["retired"], run["retired_at"]) == (    # the map's tally
        {"restart_split": 1, "evicted_split": 2, "other": 0}, True, "2026-10-27T01:00:00+00:00")


def test_a_replenished_decks_pack_carries_its_deck_source(deferred, monkeypatch):
    """§6: eval reads deck_source off the run metadata."""
    from backend.tests.test_trade_page_store import generate
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.packed_evidence": True})
    assert server._replenish_deck_for(UID, LEAGUE) is not None
    [job] = [j for j in server._trade_jobs.values() if j.get("source") == "replenish"]
    assert job["evidence"].packed
    generate(client)                                       # the tap that opens it
    run, _cards = unpack(pack_of(engine, job["job_id"]))
    assert run["deck_source"] == "replenish" and run["page_store"] == 0


def test_v5_reads_the_packed_deck_like_its_full_rows_with_withdrawals_and_in_flight(deferred):
    """Under eval v5 (#417): the packed form and the full-row form give the
    same cards, delivered positions and displayed positions, with a W0
    withdrawal (removed) and a served-before one (kept); a non-retired pack in
    its window reads as in_flight, and as final once retired."""
    from sqlalchemy import create_engine, insert
    from backend.eval import data as eval_data
    from backend.eval.data import card_dict, load_decks
    if not hasattr(eval_data, "PAGE_STORE_MARKER"):
        pytest.skip("eval v5 (#417) isn't merged here")
    client, engine, _ = deferred
    job_id, served, ghosts, ev, _ = packed_deck(120, ghost_every=9)
    status(client, job_id, 0)
    own_all_but(engine, 3, 40)
    status(client, job_id, 0)                              # card 3: served before, withdrawn
    status(client, job_id, 30)                             # card 40: never delivered (W0)
    with ev.lock:
        held = [server._unpack_row(packed) for _iid, (_i, packed) in ev.rows.items()]
    full = create_engine("sqlite:///:memory:")
    db_module.metadata.create_all(full)
    served_at = pack_of(engine, job_id)["served_at"]
    with full.begin() as conn:
        conn.execute(insert(db_module.deck_impressions_table), rows(engine) + [
            {**{c.name: r.get(c.name) for c in db_module.deck_impressions_table.columns},
             "served_at": served_at, "evidence_tier": "archive"} for r in held])
        conn.execute(insert(PACKS), [pack_of(engine, job_id)])
        conn.execute(insert(db_module.deck_card_withdrawals_table),
                     rows(engine, db_module.deck_card_withdrawals_table))
    attribution = server._PACK_ATTRIBUTION_COLUMNS

    def read(eng, as_of=None):
        on_rows = {r["impression_id"]: r for r in rows(eng)}
        [deck] = load_decks(engine=eng, as_of=as_of)
        out = []
        for c in deck.cards:
            d = card_dict(c)
            if c.impression_id in on_rows and not c.is_ghost:
                d.update({k: on_rows[c.impression_id][k] for k in attribution})
            out.append((c.card_index, c.is_ghost, c.delivered, c.position,
                        {k: v for k, v in d.items() if k in evidence_pack.CONTRACT_KEYS
                         or k == "impression_id"}))
        return deck, out

    with ev.lock:                                          # retire it, as the cleanup loop does
        ev.pack.run.update(retired=True, retired_at=served_at)
        ev.pack_dirty = True
    server._deck_pack_flush_header(ev)
    retired = pack_of(engine, job_id)
    with full.begin() as conn:                             # the full-row form: the same header
        conn.execute(PACKS.update().where(PACKS.c.run_id == job_id).values(
            header_json=retired["header_json"], checksum=retired["checksum"]))
    (pdeck, packed_read), (fdeck, full_read) = read(engine), read(full)
    assert pdeck.exclusion is None and fdeck.exclusion is None
    assert packed_read == full_read
    w = {r["served_before"]: r["card_index"] for r in rows(engine, db_module.deck_card_withdrawals_table)}
    kept = [i for i, ghost, *_ in packed_read if not ghost]
    assert w[0] not in kept and w[1] in kept and pdeck.withdrawn_removed == fdeck.withdrawn_removed == 1
    assert [i for i, ghost, delivered, *_ in packed_read if delivered and not ghost] == [
        i for i in range(60) if i != w[0]]
    positions = [p for _i, ghost, _d, p, _c in packed_read if not ghost]
    assert positions == list(range(len(positions)))       # displayed positions, the W0 gap closed
    # A non-retired pack inside its window is in_flight (as of now).
    with ev.lock:
        ev.pack.run["retired"] = False
        ev.pack.run.pop("retired_at")
        ev.pack_dirty = True
    server._deck_pack_flush_header(ev)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    deck, _ = read(engine, as_of=now)
    assert deck.exclusion == "in_flight"


# ── #417 cross-check P2-1: live-mode page-scoped decks stamp delivered_at ───

def live_deck(n, *, kind="value_core", ghost_every=0):
    """A live-mode page-scoped deck as the value core or prepared adoption
    leaves it: admitted organic (a page_scope), switched to live
    (_deck_evidence_live), its rows written at build by the real logger (uuid
    ids, tier NULL, the page_store marker) and its cards published; the value
    core's first pages are stored (prepared adoption stores none)."""
    from backend.tests.test_deferred_evidence import public, synthetic_cards
    job_id = run_job()
    server._deck_evidence_live(job_id)
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
        assert job["evidence_mode"] == "live" and job["page_scope"]
        job["append_only"] = True
        if kind == "value_core":
            job["value_core"] = {"served": n}
        else:
            job["prepared_inventory_id"] = "inventory-1"
    with db_module.engine.begin() as conn:                 # the completion's page row goes
        conn.execute(db_module.trade_page_store_table.delete().where(
            db_module.trade_page_store_table.c.deck_job_id == job_id))
    cards, players = synthetic_cards(n + (n // ghost_every if ghost_every else 0))
    ghosts = [(pos, c) for pos, c in enumerate(cards)
              if ghost_every and pos % (ghost_every + 1) == ghost_every]
    ghost_ids = {id(c) for _, c in ghosts}
    served = [c for c in cards if id(c) not in ghost_ids]
    imp = server._log_deck_signal_impressions(
        user_id=UID, league_id=LEAGUE, job_id=job_id, cards=served, players_dict=players,
        capture=None, scoring_format="1qb_ppr", ghost_cards=ghosts, candidate_pool=[],
        policy_version="pv-test")
    with server._trade_jobs_lock:
        job.update(cards=[public(c, imp[id(c)]) for c in served])
    if kind == "value_core":
        assert server._store_trade_page(job_id)
    return job_id, [imp[id(c)] for c in served]


def stamped(engine, job_id):
    return {r["card_index"]: r["delivered_at"] for r in rows(engine)
            if r["deck_job_id"] == job_id and not r["is_ghost"] and r["delivered_at"]}


@pytest.fixture()
def prepared_ok(monkeypatch):
    monkeypatch.setattr(server, "_prepared_job_matches", lambda job: True)


@pytest.mark.parametrize("kind", ["value_core", "prepared"])
def test_p2_1_a_live_page_scoped_deck_stamps_exactly_the_pages_it_sends(deferred, prepared_ok, kind):
    client, engine, _ = deferred
    job_id, _ids = live_deck(120, kind=kind)
    written = [r for r in rows(engine) if r["deck_job_id"] == job_id]
    assert len(written) == 120 and {r["evidence_tier"] for r in written} == {None}
    assert {json.loads(r["features_json"]).get("page_store") for r in written} == {1}
    assert stamped(engine, job_id) == {}
    status(client, job_id, 0)
    assert sorted(stamped(engine, job_id)) == list(range(30))
    if kind == "prepared":
        status(client, job_id, 30)
        assert sorted(stamped(engine, job_id)) == list(range(60))
        return
    # The value core's stored pages: in process, then after its job left.
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    assert sorted(stamped(engine, job_id)) == list(range(60))
    restart()
    client.get(f"/api/trades/status?deck={job_id}&cursor=60", headers=HEADERS)
    assert sorted(stamped(engine, job_id)) == list(range(90))
    assert {r["evidence_tier"] for r in rows(engine)} == {None}   # the stamp only


def test_p2_1_a_page_with_an_i1_drop_stamps_every_card_but_the_dropped_one(deferred, prepared_ok):
    """models-eng's rule (a): by impression_id, never by index range. The
    drop is a never-delivered withdrawal (W0): recorded, its row unstamped."""
    client, engine, _ = deferred
    job_id, ids = live_deck(120)
    own_all_but(engine, 7)
    status(client, job_id, 0)
    assert sorted(stamped(engine, job_id)) == [i for i in range(30) if i != 7]
    got = withdrawals(engine)
    assert set(got) == {7} and got[7]["served_before"] == 0 and got[7]["impression_id"] == ids[7]


@pytest.mark.parametrize("kind", ["value_core", "prepared"])
def test_p2_1_a_live_deck_drop_under_mode_2_is_recorded_and_stays_out(deferred, prepared_ok, kind):
    """models-eng: a value-core deck under trade_i1_mode 2 records its I-1
    drops (served_before right both ways) and never serves them again, in
    process (its stored pages; prepared adoption's job pages) and after a
    restart (the value core's stored pages)."""
    client, engine, _ = deferred
    assert server._trade_i1_mode() == 2
    job_id, ids = live_deck(120, kind=kind)
    status(client, job_id, 0)
    own_all_but(engine, 4, 40)
    status(client, job_id, 0)                              # card 4: delivered, then withdrawn
    status(client, job_id, 30)                             # card 40: never delivered (W0)
    got = withdrawals(engine)
    assert (got[4]["served_before"], got[40]["served_before"]) == (1, 0)
    own_all_but(engine)                                    # the rosters move back
    again = deck_ids(status(client, job_id, 0).get_json()) + deck_ids(status(client, job_id, 30).get_json())
    assert len(again) == 58 and not {ids[4], ids[40]} & set(again)
    if kind == "prepared":                                 # no stored pages to serve after a restart
        return
    restart()
    page = client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS).get_json()
    assert len(page["cards"]) == 29 and ids[40] not in deck_ids(page)
    assert stamped(engine, job_id).get(40) is None


def test_p2_1_the_stamp_is_the_response_time_not_the_write_time(deferred, prepared_ok, monkeypatch):
    """models-eng's rule (b): a delayed write still stamps the response time."""
    import time as _time
    from datetime import datetime, timezone
    client, engine, _ = deferred
    job_id, _ids = live_deck(60)
    queued = []
    monkeypatch.setattr(server, "_start_deck_evidence_thread",
                        lambda *, target, args: queued.append((target, args)))
    before = datetime.now(timezone.utc).isoformat()
    status(client, job_id, 0)
    after = datetime.now(timezone.utc).isoformat()
    _time.sleep(0.05)
    assert queued and stamped(engine, job_id) == {}
    for target, args in queued:                            # the write runs later
        target(*args)
    times = set(stamped(engine, job_id).values())
    assert len(times) == 1 and before <= next(iter(times)) <= after


def test_p2_1_the_first_delivery_wins_and_ghosts_stay_null(deferred, prepared_ok):
    """models-eng's rule (c)."""
    import time as _time
    client, engine, _ = deferred
    job_id, _ids = live_deck(60, ghost_every=9)
    status(client, job_id, 0)
    first = stamped(engine, job_id)
    assert sorted(first) == list(range(30))
    _time.sleep(0.01)
    server._deck_live_stamped.clear()                      # another process serves it again
    status(client, job_id, 0)
    assert stamped(engine, job_id) == first
    ghost_ids = [r["impression_id"] for r in rows(engine) if r["is_ghost"]]
    assert ghost_ids
    db_module.stamp_live_deliveries(job_id, UID, LEAGUE, ghost_ids, "2026-10-27T00:00:00+00:00")
    assert all(r["delivered_at"] is None for r in rows(engine) if r["is_ghost"])


def test_the_live_stamp_reports_a_deck_with_no_evidence(deferred, prepared_ok):
    """A delivery of a deck with no row at all (and so, on this path, no pack)
    says so; one with rows, or one delivering nothing, doesn't."""
    client, engine, _ = deferred
    job_id, _ids = live_deck(60)
    status(client, job_id, 0)
    sent = [r["impression_id"] for r in rows(engine) if not r["is_ghost"]][:3]
    at = "2026-10-27T00:00:00+00:00"
    assert db_module.stamp_live_deliveries(job_id, UID, LEAGUE, sent, at) is True
    assert db_module.stamp_live_deliveries("no-such-deck", UID, LEAGUE, ["no-such-deck:0"], at) is False
    assert db_module.stamp_live_deliveries("no-such-deck", UID, LEAGUE, [], at) is True


@pytest.mark.parametrize("has_rows", [True, False])
def test_a_live_stamp_on_a_deck_with_no_evidence_is_logged(monkeypatch, caplog, has_rows):
    """The count for the read: an ERROR line per such delivery, with the
    card count and no user id."""
    monkeypatch.setattr(db_module, "stamp_live_deliveries", lambda *a, **k: has_rows)
    with caplog.at_level("ERROR"):
        server._deck_live_stamp("deck-x", "u-secret", "lg", {"deck-x:0", "deck-x:1"}, {},
                                "2026-10-27T00:00:00+00:00")
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    if has_rows:
        assert not errors
    else:
        assert errors == ["deck-evidence deck-x: 2 delivered cards of a deck with no evidence "
                          "(no rows, no pack); eval can't see them"]
        assert "u-secret" not in errors[0]


def test_p2_1_v5_reads_a_live_decks_delivered_positions_from_its_stamps(deferred, prepared_ok):
    """Under eval v5 (#417): the delivered positions are the pages sent, the
    W0 card removed."""
    from backend.eval import data as eval_data
    from backend.eval.data import load_decks
    if not hasattr(eval_data, "PAGE_STORE_MARKER"):
        pytest.skip("eval v5 (#417) isn't merged here")
    client, engine, _ = deferred
    job_id, _ids = live_deck(120)
    own_all_but(engine, 40)
    status(client, job_id, 0)
    status(client, job_id, 30)
    [deck] = load_decks(engine=engine)
    assert deck.exclusion is None and deck.withdrawn_removed == 1
    assert [c.card_index for c in deck.cards if c.delivered and not c.is_ghost] == [
        i for i in range(60) if i != 40]


# ── #417 cross-check P3-5: a serve's withdrawals land with its delivery ─────

class fail_after:
    """Raise right after a statement starting with `prefix` runs, inside its
    transaction and before its commit (an after_cursor_execute hook)."""

    def __init__(self, engine, prefix):
        self.engine, self.prefix = engine, prefix

    def _hook(self, conn, cursor, statement, *_args):
        if " ".join(statement.split()).upper().startswith(self.prefix):
            raise RuntimeError(f"injected: the transaction fails after {self.prefix}")

    def __enter__(self):
        from sqlalchemy import event
        event.listen(self.engine, "after_cursor_execute", self._hook)

    def __exit__(self, *_exc):
        from sqlalchemy import event
        event.remove(self.engine, "after_cursor_execute", self._hook)


# Each path's delivery-evidence statement. Failing the transaction right after
# it, or right after the withdrawals' insert, must leave neither (#416 QA P3:
# both directions, so a withdrawal written in its own transaction before or
# after the delivery's goes red).
DELIVERY_STATEMENT = {"header": "UPDATE DECK_EVIDENCE_PACKS", "pack": "INSERT INTO DECK_EVIDENCE_PACKS",
                      "rows": "INSERT INTO DECK_IMPRESSIONS", "live": "UPDATE DECK_IMPRESSIONS"}
SIDES = ["after_withdrawals", "after_delivery"]


def failing(engine, path, side):
    return fail_after(engine, "INSERT INTO DECK_CARD_WITHDRAWALS" if side == "after_withdrawals"
                      else DELIVERY_STATEMENT[path])


def boundaries(engine, job_id):
    row = pack_of(engine, job_id)
    return [d[0] for d in unpack(row)[0]["deliveries"]] if row is not None else None


@pytest.mark.parametrize("side", SIDES)
def test_p3_5_a_header_update_and_its_withdrawal_land_together(deferred, side):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    own_all_but(engine, 40)
    with failing(engine, "header", side):
        status(client, job_id, 30)                         # boundary 59 and card 40's drop
    assert withdrawals(engine) == {} and boundaries(engine, job_id) == [29]
    status(client, job_id, 60)                             # the next delivery carries both
    assert withdrawals(engine)[40]["served_before"] == 0
    assert boundaries(engine, job_id) == [29, 59, 89]


@pytest.mark.parametrize("side", SIDES)
def test_p3_5_the_pack_insert_and_its_withdrawal_land_together(deferred, side):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    own_all_but(engine, 5)
    with failing(engine, "pack", side):
        status(client, job_id, 0)
    assert withdrawals(engine) == {} and pack_of(engine, job_id) is None
    status(client, job_id, 30)                             # the next delivery carries both
    assert withdrawals(engine)[5]["served_before"] == 0 and boundaries(engine, job_id) == [29, 59]


@pytest.mark.parametrize("side", SIDES)
def test_p3_5_stage_1_rows_and_their_withdrawal_land_together(deferred, side):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, store=False)
    own_all_but(engine, 5)
    with failing(engine, "rows", side):
        status(client, job_id, 0)
    assert withdrawals(engine) == {} and rows(engine) == []
    status(client, job_id, 30)                             # the next delivery carries both
    assert withdrawals(engine)[5]["served_before"] == 0
    assert sorted(i for (g, i), r in by_index(engine).items() if not g and r["delivered_at"]) == [
        i for i in range(60) if i != 5]


@pytest.mark.parametrize("side", SIDES)
def test_p3_5_a_live_stamp_and_its_withdrawal_land_together(deferred, prepared_ok, side):
    client, engine, _ = deferred
    job_id, _ids = live_deck(120)
    own_all_but(engine, 7)
    with failing(engine, "live", side):
        status(client, job_id, 0)
    assert withdrawals(engine) == {} and stamped(engine, job_id) == {}
    status(client, job_id, 0)                              # the next serve records both
    assert set(withdrawals(engine)) == {7}
    assert sorted(stamped(engine, job_id)) == [i for i in range(30) if i != 7]


def test_p3_5_withdrawals_before_any_delivery_are_written_alone(deferred):
    """A serve whose every card I-1 drops delivers nothing: its withdrawals
    have no delivery evidence to ride, so they are written on their own."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    own_all_but(engine, *range(30))
    assert status(client, job_id, 0).get_json()["cards"] == []
    got = withdrawals(engine)
    assert sorted(got) == list(range(30)) and {r["served_before"] for r in got.values()} == {0}
    assert pack_of(engine, job_id) is None


# ── #416 QA follow-ups (release-lead, 2026-10-26) ───────────────────────────

class _StopLoop(BaseException):
    """Ends _cleanup_loop from its sleep (not an Exception: the loop must not catch it)."""


def test_a_retirement_db_error_never_stops_the_cleanup_loop(deferred, monkeypatch, caplog):
    """P2: an OperationalError on the retirement CAS is logged; the loop keeps
    running, evicts on that tick and the next, and retires the deck on the
    next tick (the failed retirement is undone in memory, so it retries)."""
    import time as real_time
    from sqlalchemy.exc import OperationalError
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    with server._trade_jobs_lock:                          # superseded: due, and not evicted
        server._trade_jobs_by_key[server._trade_jobs[job_id]["key"]] = "a-newer-job"
    real_cas = db_module.update_deck_evidence_pack_header

    def locked(*_a, **_k):
        raise OperationalError("UPDATE deck_evidence_packs", {}, Exception("database is locked"))

    def stale(jid):                                        # a finished job past retention
        with server._trade_jobs_lock:
            server._trade_jobs[jid] = {"job_id": jid, "key": ("u", jid, "f"), "status": "complete",
                                       "finished_at": real_time.monotonic() - server._JOB_RETENTION - 60}

    ticks = []

    class FakeTime:
        def __getattr__(self, name):
            return getattr(real_time, name)

        def sleep(self, _seconds):
            ticks.append(1)
            if len(ticks) == 1:
                monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", locked)
                stale("stale-1")
            elif len(ticks) == 2:
                assert "stale-1" not in server._trade_jobs   # evicted on the failing tick
                assert unpack(pack_of(engine, job_id))[0]["retired"] is False
                monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", real_cas)
                stale("stale-2")
            else:
                raise _StopLoop

    monkeypatch.setattr(server, "time", FakeTime())
    with pytest.raises(_StopLoop):
        server._cleanup_loop()
    assert len(ticks) == 3 and "stale-2" not in server._trade_jobs
    run = unpack(pack_of(engine, job_id))[0]
    assert run["retired"] is True and run["retired_at"]
    assert any("retirement failed" in r.getMessage() for r in caplog.records)


def test_two_instances_first_writes_keep_both_boundaries(deferred):
    """P3 (deploy overlap at the first write): both instances insert the pack
    (insert-or-ignore). The loser adopts the stored pack (its cards stand, the
    checksum stays valid even though its own cards differ) and merges its
    boundary and its withdrawal in through the header CAS."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(80, store=False)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.served_at = "2026-10-27T00:00:00+00:00"
        source = server._deck_pack_input(ev)
    cards, run = server._deck_pack_cards(ev, source)
    a, b = server._DeckEvidence(job_id, UID), server._DeckEvidence(job_id, UID)
    for x, at, delivered in ((a, "2026-10-27T00:00:00+00:00", [[29, "2026-10-27T00:00:00+00:00"]]),
                             (b, "2026-10-27T00:00:05+00:00", [[59, "2026-10-27T00:00:05+00:00"]])):
        x.served_at, x.league_id, x.deliveries, x.packed = at, LEAGUE, delivered, True
    b_cards = [{**c, "served_at": b.served_at} for c in cards]   # its own first delivery
    w = {"deck_job_id": job_id, "card_index": 70, "user_id": UID, "league_id": LEAGUE,
         "reason": "i1_dropped", "first_withdrawn_at": b.served_at,
         "impression_id": contract.card_impression_id(job_id, 70), "served_before": 0}
    assert server._deck_pack_first_write(a, cards, {**run, "deliveries": a.deliveries})
    assert server._deck_pack_first_write(b, b_cards, {**run, "deliveries": b.deliveries},
                                         withdrawals=[w])
    stored_run, stored_cards = unpack(pack_of(engine, job_id))          # the checksum holds
    assert stored_run["deliveries"] == [[29, "2026-10-27T00:00:00+00:00"],
                                        [59, "2026-10-27T00:00:05+00:00"]]
    assert {c["served_at"] for c in stored_cards} == {a.served_at}      # the first writer's cards
    assert set(withdrawals(engine)) == {70}
    assert b.pack.checksum == pack_of(engine, job_id)["checksum"]       # later updates CAS on it


def deliveries_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]["deliveries"]


def test_pages_delivered_out_of_order_each_keep_their_boundary(deferred):
    """P3 (concurrent pages): page 3 finishes before page 2. Page 2's boundary
    is added below the last one (the union), so its cards read its own time
    instead of collapsing into page 3's."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 60)
    status(client, job_id, 30)
    delivered = deliveries_of(engine, job_id)
    assert [d[0] for d in delivered] == [29, 59, 89]
    assert delivered[1][1] >= delivered[2][1]              # page 2 went out after page 3
    state =server._trade_jobs[job_id]["evidence"].pack
    assert state.delivered_at(40) == delivered[1][1] and state.delivered_at(70) == delivered[2][1]


def test_a_first_send_inside_a_delivered_stretch_adds_no_boundary(deferred):
    """A card sent for the first time where its neighbours were delivered
    earlier (as if a disposition had hidden it at that page's serve): no
    boundary, so its neighbours keep their earlier time."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 30)
    before = deliveries_of(engine, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    card45 = server._trade_jobs[job_id]["cards"][45]
    with ev.lock:
        ev.delivered.discard(card45["impression_id"])
    server._deck_evidence_delivered(ev, [card45], league_id=LEAGUE)
    assert ev.deliveries == before and deliveries_of(engine, job_id) == before


def test_stored_path_writes_landing_out_of_order_keep_both_boundaries(deferred, monkeypatch):
    """After the job left: pages 2 and 3 are requested in order, their writes
    land in reverse. Each keeps its request's time; a later re-serve of page 2
    (its top card now dropped) adds nothing."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    restart()
    queued = []
    monkeypatch.setattr(server, "_start_deck_evidence_thread",
                        lambda *, target, args: queued.append((target, args)))
    for cursor in (30, 60):
        client.get(f"/api/trades/status?deck={job_id}&cursor={cursor}", headers=HEADERS)
    for target, args in reversed(queued):
        target(*args)
    delivered = deliveries_of(engine, job_id)
    assert [d[0] for d in delivered] == [29, 59, 89] and delivered[1][1] < delivered[2][1]
    queued.clear()
    own_all_but(engine, 59)
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    for target, args in queued:
        target(*args)
    assert deliveries_of(engine, job_id) == delivered


def test_the_first_write_builds_the_pack_cards_outside_the_deck_lock(deferred, monkeypatch):
    """P3 (lock hold): building every card's pack dict under ev.lock held a
    next-page serve ~40 ms at 2,354 cards. Only the rows' snapshot is taken
    under it; a W0 card is still packed (its row is snapshotted before plan()
    drops it)."""
    client, engine, _ = deferred
    job_id, _served, _ghosts, ev, _players = packed_deck(120)
    own_all_but(engine, 7)
    real = server._pack_card
    held = []
    monkeypatch.setattr(server, "_pack_card",
                        lambda row, at: (held.append(ev.lock.locked()), real(row, at))[1])
    status(client, job_id, 0)
    assert len(held) == 120 and not any(held)
    _run, cards = unpack(pack_of(engine, job_id))
    assert [c["card_index"] for c in cards] == list(range(120)) and 7 in withdrawals(engine)


# ── models-lead addendum A, U4: the counted residual (R2, R5) ───────────────

NO_MISSES = {"restart_split": 0, "evicted_split": 0, "other": 0}


def eval_cards(eng, as_of=None):
    """Eval v5's view of the one deck in `eng`, as the goldens compare it:
    per card its index, ghost flag, delivery, displayed position, outcome
    flags and contract-key dict, a full row's attribution columns merged in
    (eval reads them off the row's columns; a packed card carries them in the
    pack). Impression ids are left out: they differ by storage form."""
    from backend.eval.data import card_dict, load_decks
    on_rows = {r["impression_id"]: r for r in rows(eng)}
    [deck] = load_decks(engine=eng, as_of=as_of)
    out = []
    for c in deck.cards:
        d = card_dict(c)
        if c.impression_id in on_rows and not c.is_ghost:
            d.update({k: on_rows[c.impression_id][k] for k in server._PACK_ATTRIBUTION_COLUMNS})
        out.append((c.card_index, c.is_ghost, c.delivered, c.position, c.viewed, c.liked, c.passed,
                    {k: v for k, v in d.items() if k in evidence_pack.CONTRACT_KEYS}))
    return deck, out


def copy_db(engine, drop_impressions=()):
    """A second in-memory database holding `engine`'s rows, less the
    deck_impressions rows named."""
    from sqlalchemy import create_engine, insert
    other = create_engine("sqlite:///:memory:")
    db_module.metadata.create_all(other)
    with other.begin() as conn:
        for table in db_module.metadata.sorted_tables:
            got = [r for r in rows(engine, table)
                   if not (table is db_module.deck_impressions_table
                           and r["impression_id"] in drop_impressions)]
            if got:
                conn.execute(insert(table), got)
    return other


def cleanup_ticks(monkeypatch, n):
    """Run the real _cleanup_loop for n ticks (its sleep returns at once)."""
    import time as real_time
    ticks = []

    class FakeTime:
        def __getattr__(self, name):
            return getattr(real_time, name)

        def sleep(self, _seconds):
            ticks.append(1)
            if len(ticks) > n:
                raise _StopLoop

    monkeypatch.setattr(server, "time", FakeTime())
    with pytest.raises(_StopLoop):
        server._cleanup_loop()
    monkeypatch.setattr(server, "time", real_time)


def evict(monkeypatch, job_id):
    """The cleanup loop evicts the deck's job (finished past _JOB_RETENTION),
    in this process: no restart."""
    import time as real_time
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["finished_at"] = real_time.monotonic() - server._JOB_RETENTION - 60
    cleanup_ticks(monkeypatch, 1)
    assert job_id not in server._trade_jobs


def an_old_instance_delivers(job_id, last, at):
    """A deploy overlap: the old instance, still serving, records a page
    boundary on the deck's pack after this (new) process started."""
    state = server._load_pack_state(job_id, UID)
    state.run["deliveries"] = server._merge_deliveries(state.run["deliveries"], [[last, at]])
    assert server._deck_pack_commit(job_id, state)
    server._deck_pack_states.clear()


@pytest.mark.parametrize("how, cause", [
    ("restart", "restart_split"), ("deploy_overlap", "restart_split"), ("re_fork", "restart_split"),
    ("eviction", "other"), ("eviction_named", "evicted_split"), ("held_here", "other")])
def test_u4_a_card_past_the_stored_pages_missing_its_snapshot_is_a_cause_coded_miss(
        deferred, monkeypatch, caplog, how, cause):
    """U4-R2/R5, causes by provenance (#428 QA (d)). A card past the stored
    90 is viewed with no snapshot left; its row comes from the packed card
    (the U2 id joins the outcome) and the miss is counted by cause:
    - restart, a deploy overlap (the old instance delivered page 4 after this
      process started) and a re-fork (a fresh worker): this process never
      held the deck, so restart_split;
    - an eviction here: evicted_split with _EVICTED_SPLIT_NAMED on (its
      default since models-lead's addendum C), other with it off;
    - a deck this process built and still holds: other (a defect), at error."""
    from datetime import datetime, timezone
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    if how != "deploy_overlap":
        status(client, job_id, 90)                         # the live job's page past the stored 90
    if how in ("restart", "re_fork"):
        restart()                                          # a new process (or worker): no jobs, no ledgers
    elif how == "deploy_overlap":
        restart()
        an_old_instance_delivers(job_id, 119, datetime.now(timezone.utc).isoformat())
    elif how.startswith("eviction"):
        monkeypatch.setattr(server, "_EVICTED_SPLIT_NAMED", how == "eviction_named")
        evict(monkeypatch, job_id)
    else:                                                  # held here: its snapshot is lost in process
        ev = server._trade_jobs[job_id]["evidence"]
        with ev.lock:
            ev.rows.pop(contract.card_impression_id(job_id, 95))
    with caplog.at_level("WARNING"):
        view(job_id, 95)
    got = by_index(engine)[(0, 95)]
    assert got["evidence_tier"] == "viewed" and got["assets_json"] is None
    run, cards = unpack(pack_of(engine, job_id))
    features = json.loads(got["features_json"])       # the packed card less the row's columns
    assert set(features) == set(cards[95]) - set(server._PACK_LOGGED_COLUMNS) - set(
        server._PACK_ATTRIBUTION_COLUMNS) - {"served_at"} | {"page_store"}
    assert contract.FROZEN_INPUT_KEYS & set(cards[95]) <= set(features)
    assert run["upgrade_misses"] == {**NO_MISSES, cause: 1}
    assert features["give_value"] == cards[95]["give_value"]
    assert [o["impression_id"] for o in outcomes(engine)] == [contract.card_impression_id(job_id, 95)]
    [line] = [r for r in caplog.records if "upgrade miss cause=" in r.getMessage()]
    assert f"cause={cause} job={job_id} index=95 stored=90" in line.getMessage()
    assert line.levelname == ("ERROR" if cause == "other" else "WARNING")


def test_u4_the_classification_hook():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server, "_deck_held", {"held": None, "gone": None})
        mp.setattr(server, "_deck_evicted_at", {"gone": "2026-10-27T02:00:00+00:00"})
        cause = server._upgrade_miss_cause
        assert cause("elsewhere", 95, 90, True) == "restart_split"     # another process built it
        assert cause("elsewhere", 95, 90, False) == "other"            # no recorded delivery
        assert cause("elsewhere", 89, 90, True) == "other"             # within the stored pages
        assert cause("elsewhere", 60, 60, True) == "restart_split"     # the deck's own count
        assert cause("held", 95, 90, True) == "other"                  # built here, still here
        assert cause("gone", 95, 90, True) == "evicted_split"          # evicted: named by default
        mp.setattr(server, "_EVICTED_SPLIT_NAMED", False)
        assert cause("gone", 95, 90, True) == "other"                  # off: other
        mp.setattr(server, "_EVICTED_SPLIT_NAMED", True)
        assert cause("gone", 95, 90, True) == "evicted_split"
        assert cause("gone", 95, 90, False) == "other"
        assert cause("gone", 89, 90, True) == "other"


def pages_stored(monkeypatch, pages):
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_pages_stored", float(pages))
    assert server._trade_pages_stored() * server._trade_page_size() == 30 * pages


def test_u4_a_deck_that_stored_fewer_cards_splits_at_its_own_count(deferred, monkeypatch):
    """#428 QA (c): the knob was 2 pages when the deck was built, so it stored
    60 cards. Card 70, delivered past them and viewed after a restart, is a
    restart_split (a constant 90 would have called it other)."""
    client, engine, _ = deferred
    pages_stored(monkeypatch, 2)
    job_id, *_ = packed_deck(120)
    for cursor in (0, 30, 60):
        status(client, job_id, cursor)
    assert unpack(pack_of(engine, job_id))[0]["stored_count"] == 60
    restart()
    view(job_id, 70)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_u4_the_stored_count_order(monkeypatch):
    """The deck's job (or page row) first, then its pack, then 0: no record
    that a store wrote (#434 QA P2-1). The explicit counts come before the
    fallback, page_store 0 included (#434 QA P3-2), and the knobs are never
    read: raising or lowering them changes nothing."""
    assert server._deck_stored_count(75, {"stored_count": 90}) == 75
    assert server._deck_stored_count(None, {"stored_count": 90}) == 90
    assert server._deck_stored_count(60, {"page_store": 0}) == 60
    assert server._deck_stored_count(None, {"stored_count": 60, "page_store": 0}) == 60
    for pages in (2, 4):
        pages_stored(monkeypatch, pages)
        assert server._deck_stored_count(None, {"page_store": 1}) == 0
        assert server._deck_stored_count(None, {"page_store": 0}) == 0
        assert server._deck_stored_count(None, {}) == 0


def test_u4_a_deck_this_process_builds_is_noted_held(deferred, monkeypatch):
    """The provenance ledger's source: the kickoff notes each flag-on deck it
    admits, so a miss on it in this process is never a restart_split. A
    flag-off job carries no evidence and isn't noted."""
    job_id = run_job()
    assert server._trade_jobs[job_id]["evidence_mode"] == "deferred" and job_id in server._deck_held
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    off = run_job(force_fresh=True)
    assert off != job_id and off not in server._deck_held


def _web_start_command(render_yaml: str) -> list[str]:
    """The web service's startCommand in `render_yaml`, as shell words. Plain
    text, no PyYAML (not a CI dependency): the service's block runs from its
    "- type: web" line to the next "- type:" line, and the command is either
    on its own line or a folded/literal block (`>`, `|`) indented below it.
    Everything from a " #" on is dropped: a YAML comment, or a shell one."""
    lines = render_yaml.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().startswith("- type:")]
    [web_at] = [i for i in starts if lines[i].split(":", 1)[1].strip() == "web"]
    block = lines[web_at:min([i for i in starts if i > web_at], default=len(lines))]
    [at] = [i for i, line in enumerate(block) if line.strip().startswith("startCommand:")]
    value = block[at].split(":", 1)[1]
    if value.strip()[:1] in (">", "|"):
        indent = len(block[at]) - len(block[at].lstrip())
        body = []
        for line in block[at + 1:]:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
        value = " ".join(body)
    value = (" " + value).split(" #", 1)[0].strip()
    if value[:1] in "\"'" and value[-1:] == value[:1]:
        value = value[1:-1]
    return value.split()


def _gunicorn_workers(words: list[str]) -> list[str]:
    """Every workers value the command gives gunicorn, in order (it uses the
    last): --workers N, --workers=N, -w N, -wN."""
    values = []
    for i, word in enumerate(words):
        if word in ("--workers", "-w"):
            values.append(words[i + 1] if i + 1 < len(words) else "")
        elif word.startswith("--workers="):
            values.append(word.split("=", 1)[1])
        elif word.startswith("-w") and len(word) > 2:
            values.append(word[2:])
    return values


_WEB = "services:\n  - type: web\n    name: x\n"
_CRON = "  - type: cron\n    startCommand: gunicorn run:app --workers 9\n"


@pytest.mark.parametrize("command, workers", [
    ("    startCommand: gunicorn run:app --workers 1 --threads 4\n", ["1"]),
    ("    startCommand: gunicorn run:app -w 1\n", ["1"]),
    ("    startCommand: gunicorn run:app --workers=1\n", ["1"]),
    ("    startCommand: gunicorn run:app -w1\n", ["1"]),
    ("    startCommand: >\n      gunicorn run:app\n      --workers 1 --threads 4\n", ["1"]),
    ("    startCommand: \"gunicorn run:app --workers 1\"\n", ["1"]),
    ("    startCommand: gunicorn run:app --timeout 120  # --workers 1\n", []),
    ("    startCommand: gunicorn run:app --workers 1 -w 2\n", ["1", "2"]),
    ("    startCommand: gunicorn run:app --workers 1 --workers=2\n", ["1", "2"]),
    ("    startCommand: gunicorn run:app -w 2\n", ["2"]),
    ("    startCommand: gunicorn run:app --threads 4\n", []),
])
def test_u4_the_workers_pin_reads_every_form(command, workers):
    """#433 QA P3: the pin's parser. A trailing comment never counts, every
    repeat is seen (gunicorn takes the last), and each spelling is read,
    including a folded block. Only the web service's command is read."""
    assert _gunicorn_workers(_web_start_command(_WEB + command + _CRON)) == workers


def test_u4_restart_splits_assume_one_worker_per_instance():
    """models-eng: "this process never held the deck" means a restart only
    with one gunicorn worker per instance. The command line's workers win over
    GUNICORN_CMD_ARGS and WEB_CONCURRENCY (Render sets the latter from the
    CPUs: 2 on a 2-CPU plan), so this explicit value is the only reliable pin.
    --preload is fine (#428 QA: Render preloads by default through
    GUNICORN_CMD_ARGS): the master's import leaves the ledgers empty, pinned
    below."""
    words = _web_start_command((REPO / "render.yaml").read_text())
    message = ("restart_split's provenance rule assumes one worker per instance: add a "
               "cross_worker cause to _upgrade_miss_cause (models-eng's reader is cause-generic) "
               "before raising --workers")
    assert _gunicorn_workers(words) == ["1"], message


def test_u4_importing_the_server_leaves_the_deck_ledgers_empty(tmp_path):
    """#428 QA: the preload hazard. Under --preload the gunicorn master imports
    the app and forks its worker, which inherits the master's _deck_held and
    _deck_evicted_at. A deck noted there would never read as a restart's.
    Observable only in a fresh interpreter (this one imported the server). It
    imports run, gunicorn's target (run:app), so a boot-time step there is
    covered too (#433 QA P3), with the boot sync's one network call, Sleeper's
    ADP, stubbed out."""
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items()
           if k not in ("FTF_TEST_MODE", "FTF_SLEEPER_RECORD", "DATABASE_URL")}
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'scratch.db'}"
    # A players cache, as prod's build bakes one (#436 QA): without it the boot
    # sync stops at "sync deferred" and its sync branch never runs here.
    env["FTF_PLAYERS_CACHE_FILE"] = str(
        REPO / "backend/tests/fixtures/draft/players-bulk/players/nfl.json")
    child = subprocess.run(
        [sys.executable, "-c", "import backend.server as s; "
         "s._fetch_sleeper_adp = lambda: {}; import run; "
         "print(len(s._deck_held), len(s._deck_evicted_at))"],
        capture_output=True, text=True, cwd=REPO, env=env, timeout=180)
    assert child.returncode == 0, child.stderr[-2000:]
    assert child.stdout.strip().splitlines()[-1] == "0 0"


def test_u4_the_restart_split_path_replays_the_same_upgraded_or_left_packed(deferred, monkeypatch):
    """U4-R5: the upgraded-vs-packed identity, on the restart path itself.
    Cards past the stored 90 are viewed after a restart (restart_split rows
    from the pack), with a stored card upgraded from the blob beside them.
    Eval reads the deck the same with those rows as with them left packed:
    every card dict, outcome and position, the exposure curve, and every
    registered scorer's replay (estimates and IPS weights)."""
    import backend.eval.replay as replay_mod
    import backend.value_model as vm
    from backend.eval.replay import evaluate, exposure_curve
    from backend.eval.scorers import get_scorer, registered_names
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    for cursor in (0, 30, 60, 90):
        status(client, job_id, cursor)
    restart()                                              # a new process: never held the deck
    for index, action in ((50, "like"), (91, "like"), (95, "pass"), (99, "viewed"), (104, "like")):
        view(job_id, index, action)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 4}
    misses = [contract.card_impression_id(job_id, i) for i in (91, 95, 99, 104)]
    assert {r["impression_id"] for r in rows(engine) if r["card_index"] >= 90} == set(misses)
    upgraded, left_packed = engine, copy_db(engine, drop_impressions=misses)
    from datetime import datetime, timedelta
    as_of = (datetime.fromisoformat(pack_of(engine, job_id)["served_at"])
             + timedelta(hours=26)).isoformat()                 # past v5's 25 h in-flight window

    (deck_u, cards_u), (deck_p, cards_p) = eval_cards(upgraded, as_of), eval_cards(left_packed, as_of)
    assert deck_u.exclusion is None and deck_p.exclusion is None
    assert cards_u == cards_p
    assert [c[0] for c in cards_u if any(c[4:7])] == [50, 91, 95, 99, 104]
    assert exposure_curve([deck_u]) == exposure_curve([deck_p])
    model = vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.4, "value_delta": 0.8, "pref_long": 1.1,
                                           "pref_short": -0.6, "partner_rate": 0.9}),
        propose_head=None, propose_constant=0.2, partner_rates={}, global_like_rate=0.3,
        position_mean=0.4, trained_at="t", train_date="t")
    monkeypatch.setattr(vm, "load_latest_model", lambda: model)
    real = replay_mod._estimate
    for name in registered_names():
        out = []
        for deck in (deck_u, deck_p):
            weights = []
            monkeypatch.setattr(replay_mod, "_estimate",
                                lambda *a, w=weights: w.append(list(a[1])) or real(*a))
            run = evaluate(get_scorer(name, seed=3), [deck], ess_min=1, bootstrap=50, seed=2)
            out.append((repr(run), weights))
        assert out[0] == out[1], name


def test_p2_1_a4_a_live_deck_replays_like_the_same_deck_stored_as_a_pack(deferred, prepared_ok,
                                                                        monkeypatch):
    """models-lead B2 (a4), the storage-form identity: a value-core
    page-scoped deck's stamped live rows replay under eval v5 exactly as the
    same deck stored as a pack with the same deliveries: card dicts,
    delivered and dense displayed positions (a W0 withdrawal removed), the
    exposure curve, and every registered scorer's replay. Only the impression
    ids differ (uuid rows vs the contract id), so the comparison maps them."""
    from sqlalchemy import create_engine, insert
    from backend.eval import data as eval_data
    if not hasattr(eval_data, "PAGE_STORE_MARKER"):
        pytest.skip("eval v5 (#417) isn't merged here")
    import backend.eval.replay as replay_mod
    import backend.value_model as vm
    from backend.eval.replay import evaluate, exposure_curve
    from backend.eval.scorers import get_scorer, registered_names
    client, engine, _ = deferred
    job_id, ids = live_deck(120)
    own_all_but(engine, 40)                                # W0 on page 2
    status(client, job_id, 0)
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    for index, action in ((0, "like"), (3, "pass"), (10, "viewed"), (31, "like"), (45, "pass")):
        server._save_deck_outcome_safe(ids[index], action, acting_user_id=UID)
    live_rows = sorted((r for r in rows(engine) if r["deck_job_id"] == job_id),
                       key=lambda r: r["card_index"])
    assert sorted(r["card_index"] for r in live_rows if r["delivered_at"]) == [
        i for i in range(60) if i != 40]
    to_contract = {r["impression_id"]: contract.card_impression_id(job_id, r["card_index"])
                   for r in live_rows}
    served_at = live_rows[0]["served_at"]
    deliveries = [[29, live_rows[0]["delivered_at"]], [59, live_rows[30]["delivered_at"]]]

    # The same deck, stored as S8 stores a pack: full first-30 rows, every card packed.
    cards = [server._pack_card(r, served_at) for r in live_rows]
    run = {"values_snapshot_id": "vsn", "config_ref": "cfg", "built_at": served_at,
           "deliveries": deliveries, "page_store": 1, "retired": True,
           "retired_at": deliveries[-1][1],
           "upgrade_misses": {"restart_split": 0, "other": 0}}
    packed = evidence_pack.pack_run(run, cards, card_count=len(cards))
    stored = create_engine("sqlite:///:memory:")
    db_module.metadata.create_all(stored)
    with stored.begin() as conn:
        conn.execute(insert(db_module.deck_impressions_table), [
            {**r, "impression_id": to_contract[r["impression_id"]], "evidence_tier": "first30"}
            for r in live_rows if r["card_index"] < 30])
        conn.execute(insert(PACKS), [{
            "run_id": job_id, "user_id": UID, "league_id": LEAGUE, "served_at": served_at,
            "pack_version": packed.pack_version, "header_json": packed.header_json,
            "cards_blob": packed.cards_blob, "checksum": packed.checksum,
            "card_count": packed.card_count, "created_at": served_at}])
        conn.execute(insert(db_module.deck_card_withdrawals_table), [
            {**{k: v for k, v in w.items() if k != "id"},
             "impression_id": to_contract[w["impression_id"]]}
            for w in rows(engine, db_module.deck_card_withdrawals_table)])
        conn.execute(insert(db_module.deck_outcomes_table), [
            {**{k: v for k, v in o.items() if k != "id"},
             "impression_id": to_contract[o["impression_id"]]}
            for o in outcomes(engine)])

    (deck_live, live_read), (deck_pack, pack_read) = eval_cards(engine), eval_cards(stored)
    assert deck_live.exclusion is None and deck_pack.exclusion is None
    assert live_read == pack_read
    kept = [c for c in live_read if not c[1]]
    assert 40 not in [c[0] for c in kept] and deck_live.withdrawn_removed == 1
    assert [c[0] for c in kept if c[2]] == [i for i in range(60) if i != 40]
    assert [c[3] for c in kept] == list(range(len(kept)))      # dense displayed positions
    assert exposure_curve([deck_live]) == exposure_curve([deck_pack])
    model = vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.4, "value_delta": 0.8, "pref_long": 1.1,
                                           "pref_short": -0.6, "partner_rate": 0.9}),
        propose_head=None, propose_constant=0.2, partner_rates={}, global_like_rate=0.3,
        position_mean=0.4, trained_at="t", train_date="t")
    monkeypatch.setattr(vm, "load_latest_model", lambda: model)
    real = replay_mod._estimate
    import dataclasses
    for name in registered_names():
        out, misses = [], []
        for deck in (deck_live, deck_pack):
            weights = []
            monkeypatch.setattr(replay_mod, "_estimate",
                                lambda *a, w=weights: w.append(list(a[1])) or real(*a))
            evaluated = evaluate(get_scorer(name, seed=3), [deck], ess_min=1, bootstrap=50, seed=2)
            misses.append(evaluated.upgrade_misses)
            # Upgrade misses are a pack's own count (#425): compared apart, below.
            out.append((repr(dataclasses.replace(evaluated, upgrade_misses={})), weights))
        assert out[0] == out[1], name
        assert misses[0] == {} and misses[1] and set(misses[1].values()) == {0}, (name, misses)


# ── models-lead B4 (C): disposition cuts are withdrawals too ────────────────

def pass_elsewhere(engine, *card_indexes, give=None, receive=None):
    """The user passed on these cards' exact packages on another surface
    (a trade_decisions pass): the serve's disposition projection cuts them."""
    from datetime import datetime, timezone
    from sqlalchemy import insert
    with engine.begin() as conn:
        for i in card_indexes:
            conn.execute(insert(db_module.trade_decisions_table).values(
                user_id=UID, league_id=LEAGUE, trade_id=f"elsewhere-{i}",
                give_player_ids=json.dumps(give or [f"mine{i}"]),
                receive_player_ids=json.dumps(receive or [f"theirs{i}"]),
                decision="pass", created_at=datetime.now(timezone.utc).isoformat()))


def undo_passes(engine):
    from sqlalchemy import delete
    with engine.begin() as conn:
        conn.execute(delete(db_module.trade_decisions_table))


@pytest.mark.parametrize("kind", ["packed", "packed_job_view", "live", "live_prepared"])
def test_b4_a_cut_never_delivered_is_recorded_w0_and_stays_out(deferred, prepared_ok, kind):
    """Through both serve hooks: the stored pages (packed, live value core)
    and the job view (an unstored packed deck, prepared adoption)."""
    client, engine, _ = deferred
    if kind.startswith("packed"):
        job_id, *_ = packed_deck(120, store=kind == "packed")
        cut_id = contract.card_impression_id(job_id, 40)
    else:
        job_id, ids = live_deck(120, kind="prepared" if kind == "live_prepared" else "value_core")
        cut_id = ids[40]
    status(client, job_id, 0)
    pass_elsewhere(engine, 40)
    page = deck_ids(status(client, job_id, 30).get_json())
    assert cut_id not in page and len(page) == 29
    got = withdrawals(engine)
    assert set(got) == {40}
    assert (got[40]["reason"], got[40]["served_before"], got[40]["impression_id"]) == (
        "disposition_cut", 0, cut_id)
    undo_passes(engine)                                    # sticky, whatever the pass does now
    assert cut_id not in deck_ids(status(client, job_id, 30).get_json())
    if kind == "live":
        assert 40 not in stamped(engine, job_id)


def test_b4_a_cut_after_delivery_was_served_before_and_is_distinct_from_i1(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    pass_elsewhere(engine, 5)                              # card 5 was delivered on page 1
    own_all_but(engine, 7)
    status(client, job_id, 0)
    got = withdrawals(engine)
    assert {i: (r["reason"], r["served_before"]) for i, r in got.items()} == {
        5: ("disposition_cut", 1), 7: ("i1_dropped", 1)}


def test_b4_a_stored_page_cut_after_a_restart_is_recorded(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    restart()
    pass_elsewhere(engine, 3, 40)                          # 3 delivered before, 40 never
    client.get(f"/api/trades/status?deck={job_id}&cursor=0", headers=HEADERS)
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    got = withdrawals(engine)
    assert {i: (r["reason"], r["served_before"]) for i, r in got.items()} == {
        3: ("disposition_cut", 1), 40: ("disposition_cut", 0)}


@pytest.mark.parametrize("side", SIDES)
def test_b4_a_cut_lands_with_its_delivery(deferred, side):
    """The cut rides the delivery's transaction, as I-1's withdrawals do."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    pass_elsewhere(engine, 40)
    with failing(engine, "header", side):
        status(client, job_id, 30)
    assert withdrawals(engine) == {} and boundaries(engine, job_id) == [29]
    status(client, job_id, 60)
    assert withdrawals(engine)[40]["reason"] == "disposition_cut"
    assert boundaries(engine, job_id) == [29, 59, 89]


def test_b4_the_flag_off_path_records_no_cut(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    job_id = run_job()
    cards = server._trade_jobs[job_id]["cards"]
    first = cards[0]
    pass_elsewhere(engine, 0, give=[p["id"] for p in first["give"]],
                   receive=[p["id"] for p in first["receive"]])
    body = client.get(f"/api/trades/status?job_id={job_id}", headers=HEADERS).get_json()
    assert first["trade_id"] not in {c["trade_id"] for c in body["cards"]}   # cut, as today
    assert rows(engine, db_module.deck_card_withdrawals_table) == []


@pytest.mark.parametrize("kind", ["packed", "live"])
def test_b4_v5_removes_a_never_delivered_cut_like_an_i1_withdrawal(deferred, prepared_ok, kind):
    """models-lead B4: eval v5 removes a cut never delivered (served_before 0)
    exactly as it removes I-1's: gone from the deck, the displayed positions
    dense, counted in withdrawn_removed."""
    from datetime import datetime, timedelta, timezone
    from backend.eval.data import load_decks
    client, engine, _ = deferred
    job_id = packed_deck(120)[0] if kind == "packed" else live_deck(120)[0]
    status(client, job_id, 0)
    pass_elsewhere(engine, 40)
    status(client, job_id, 30)
    as_of = (datetime.now(timezone.utc) + timedelta(hours=26)).isoformat()   # packs settled
    [deck] = load_decks(engine=engine, as_of=as_of)
    assert deck.exclusion is None and deck.withdrawn_removed == 1
    kept = [c for c in deck.cards if not c.is_ghost]
    assert 40 not in [c.card_index for c in kept]
    assert [c.position for c in kept] == list(range(len(kept)))
    assert [c.card_index for c in kept if c.delivered] == [i for i in range(60) if i != 40]


@pytest.mark.parametrize("side", SIDES)
def test_b4_a_live_decks_cut_lands_with_its_stamp(deferred, prepared_ok, side):
    """#428 QA (a): on the live path the cut rides the delivered_at stamp's
    transaction, both directions; the next serve records both."""
    client, engine, _ = deferred
    job_id, ids = live_deck(120)
    pass_elsewhere(engine, 7)
    with failing(engine, "live", side):
        status(client, job_id, 0)
    assert withdrawals(engine) == {} and stamped(engine, job_id) == {}
    status(client, job_id, 0)
    got = withdrawals(engine)
    assert {i: (r["reason"], r["served_before"]) for i, r in got.items()} == {7: ("disposition_cut", 0)}
    assert sorted(stamped(engine, job_id)) == [i for i in range(30) if i != 7]


@pytest.mark.parametrize("side", SIDES)
def test_b4_a_stored_path_cut_after_a_restart_lands_with_its_delivery(deferred, side):
    """#428 QA (a): after a restart (the stored path) the cut rides the
    page's header CAS, both directions; the next serve records both."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    restart()
    pass_elsewhere(engine, 40)
    with failing(engine, "header", side):
        client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    assert withdrawals(engine) == {} and boundaries(engine, job_id) == [29]
    client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS)
    got = withdrawals(engine)
    assert {i: (r["reason"], r["served_before"]) for i, r in got.items()} == {40: ("disposition_cut", 0)}
    assert boundaries(engine, job_id) == [29, 59]


@pytest.mark.parametrize("kind", ["stored_pages", "job_view", "live_job_view"])
def test_b4_a_page_whose_every_card_is_cut(deferred, prepared_ok, kind):
    """#428 QA (b), the three `or cut` hooks (the stored page, the job view,
    the live job view): every card on page 2 was acted on elsewhere. The page
    returns no cards, records all 30 cuts (never delivered: W0), and is not
    the deck's end: page 3 follows."""
    client, engine, _ = deferred
    if kind == "live_job_view":
        job_id, ids = live_deck(120, kind="prepared")
    else:
        job_id, *_ = packed_deck(120, store=kind == "stored_pages")
        ids = [contract.card_impression_id(job_id, i) for i in range(120)]
    status(client, job_id, 0)
    pass_elsewhere(engine, *range(30, 60))
    body = client.get(f"/api/trades/status?deck={job_id}&cursor=30", headers=HEADERS).get_json()
    assert body["cards"] == [] and body["status"] == "complete" and body["cursor"] >= 60
    assert not {"pool_exhausted", "rebased"} & set(body)
    got = withdrawals(engine)
    assert sorted(got) == list(range(30, 60))
    assert {(r["reason"], r["served_before"]) for r in got.values()} == {("disposition_cut", 0)}
    nxt = client.get(f"/api/trades/status?deck={job_id}&cursor={body['cursor']}", headers=HEADERS)
    assert deck_ids(nxt.get_json()) == ids[60:90]


# ── Fix-before-flip (#428 QA, release-lead) ─────────────────────────────────

def test_flip_a_replenished_decks_miss_after_a_restart_is_a_restart_split(deferred):
    """Item 4: a weekly-replenishment deck is packed but never page-stored
    (no page_scope: page_store 0, no stored_count). None of its cards has a
    stored snapshot, so a miss after a restart is restart_split at any index,
    never other because the knobs (90) say card 40 should have been stored."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, store=False, source="replenish")
    status(client, job_id, 0)
    status(client, job_id, 30)
    assert server._trade_jobs[job_id]["source"] == "replenish"
    assert not server._trade_jobs[job_id].get("page_scope")
    run = unpack(pack_of(engine, job_id))[0]
    assert (run["page_store"], "stored_count" in run) == (0, False)
    restart()
    view(job_id, 40)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_flip_a_pack_written_before_its_page_store_gets_the_stored_count(deferred):
    """Item 4's ordering: a page delivered while the job ran makes
    _deck_evidence_job_done write the pack (server.py, the worker: job_done,
    then _store_trade_page), before the store sets ev.stored_count. The store
    then records stored_count in the pack's header."""
    import time as _time
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False)
    assert deck_ids(status(client, job_id, 0).get_json())       # delivered while it runs
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="complete", finished_at=_time.monotonic())
    server._deck_evidence_job_done(job_id)                     # the first write
    assert "stored_count" not in unpack(pack_of(engine, job_id))[0]
    assert server._store_trade_page(job_id)                    # then the store
    run = unpack(pack_of(engine, job_id))[0]
    assert run["stored_count"] == 90 and [d[0] for d in run["deliveries"]] == [29]


def view_swallowed(job_id, index, action="viewed"):
    """An outcome whose upgrade fails: the route logs it and goes on."""
    view(job_id, index, action)


def rows_of(engine, job_id, index):
    return [r for r in rows(engine) if r["deck_job_id"] == job_id and r["card_index"] == index]


@pytest.mark.parametrize("path", ["stored", "live"])
def test_flip_a_miss_whose_header_commit_raises_counts_once_after_the_retry(deferred, path):
    """Item 1: the header UPDATE fails on card 95's first outcome. Its
    increment is taken back, so the next outcome counts it once: one row and
    a count of 1, after a restart (restart_split) and in process (a held
    deck whose snapshot is gone: other)."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)
    if path == "stored":
        restart()
        cause = "restart_split"
    else:
        ev = server._trade_jobs[job_id]["evidence"]
        with ev.lock:
            ev.rows.pop(contract.card_impression_id(job_id, 95))
        cause = "other"
    with fail_after(engine, "UPDATE DECK_EVIDENCE_PACKS"):
        view_swallowed(job_id, 95)
    assert rows_of(engine, job_id, 95) == []
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == NO_MISSES
    view(job_id, 95)                                           # the retry
    assert len(rows_of(engine, job_id, 95)) == 1
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, cause: 1}


def test_flip_a_miss_whose_row_save_raises_counts_once_after_the_retry(deferred):
    """Item 1's sibling: the count commits, then the row's insert fails. The
    retry writes the row and doesn't count again."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)
    restart()
    with fail_after(engine, "INSERT INTO DECK_IMPRESSIONS"):
        view_swallowed(job_id, 95)
    assert rows_of(engine, job_id, 95) == []
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}
    view(job_id, 95)
    assert len(rows_of(engine, job_id, 95)) == 1
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_flip_ledger_adds_at_the_cap_are_thread_safe(monkeypatch):
    """Item 2: kickoffs add to _deck_held concurrently; at the cap the FIFO
    trim raced (KeyError, or the dict changing size). Under the leaf lock no
    add raises and the ledger never passes the cap (addendum C: the memory
    guard; its warning is silenced here, every add trims a young entry)."""
    import sys
    import threading
    monkeypatch.setattr(server, "_DECK_LEDGER_GUARD", 8)
    monkeypatch.setattr(server.log, "warning", lambda *a, **k: None)
    ledger, errors = collections.OrderedDict(), []

    def hammer(t):
        try:
            for i in range(20000):
                server._ledger_add(ledger, f"{t}-{i}")
        except Exception as exc:                           # noqa: BLE001 (the race's symptom)
            errors.append(repr(exc))

    switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=hammer, args=(t,)) for t in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(switch)
    assert errors == [] and len(ledger) <= 8


def test_flip_a_past_stored_card_with_no_recorded_delivery_is_other(deferred):
    """Item 3: only page 1's delivery is recorded (a later update was lost).
    Card 95, past the stored pages, viewed after a restart, has no recorded
    delivery, so it is no named cause: other."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    restart()
    view(job_id, 95)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "other": 1}


def test_flip_eviction_is_checked_before_holding():
    """Item 5 (a): a deck this process built and then evicted is in both
    ledgers: with evicted_split named it reads evicted_split, never other (a
    held check first) nor restart_split (a not-held check first, as for a
    deck the held ledger's cap trimmed)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server, "_deck_held", {"built_and_evicted": None})
        mp.setattr(server, "_deck_evicted_at", {"built_and_evicted": "t", "trimmed": "t"})
        mp.setattr(server, "_EVICTED_SPLIT_NAMED", True)
        assert server._upgrade_miss_cause("built_and_evicted", 95, 90, True) == "evicted_split"
        assert server._upgrade_miss_cause("trimmed", 95, 90, True) == "evicted_split"


def test_flip_the_stored_path_counts_against_the_page_rows_card_count(deferred):
    """Item 5 (b): the page row says 90 cards were stored; the pack's run is
    made to say 100. After a restart card 95 is past the row's 90: the stored
    path passes the row's card_count, so restart_split (the run's 100 would
    read other)."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)
    state = server._load_pack_state(job_id, UID)
    state.run["stored_count"] = 100
    assert server._deck_pack_commit(job_id, state)
    restart()
    view(job_id, 95)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_flip_the_live_path_counts_against_the_jobs_stored_count(deferred):
    """Item 5 (c): in process the job's ev.stored_count (90) is passed, not the
    run's (made 100). The deck is taken off the held ledger so the count
    decides: card 95 is past 90, restart_split (the run's 100 would read
    other)."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)
    ev = server._trade_jobs[job_id]["evidence"]
    assert ev.stored_count == 90
    with server._deck_evidence_write_lock:
        ev.pack.run["stored_count"] = 100
        assert server._deck_pack_commit(job_id, ev.pack)
    server._deck_held.clear()
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 95))
    view(job_id, 95)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


# ── #434 QA: a store that doesn't write records stored count 0 ──────────────

def delivered_before_completion(client, job_id):
    """Pages 1 and 2 delivered while the job ran; then the worker's job_done
    writes the pack (no stored_count yet), as before its store."""
    import time as _time
    for cursor in (0, 30):
        assert deck_ids(status(client, job_id, cursor).get_json())
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="complete", finished_at=_time.monotonic())
    server._deck_evidence_job_done(job_id)
    assert "stored_count" not in unpack(pack_of(engine_of(), job_id))[0]


def engine_of():
    return db_module.engine


def store_fails(job_id, how):
    """The store writes no page row: (a) the save raises, (b) the supersede
    guard refuses it (a newer deck's row holds the key), (c) the deck isn't
    page-eligible (a failed experiment-digest read) or its job was revoked."""
    import time as _time
    from backend.tests.test_trade_page_store import _row
    with pytest.MonkeyPatch.context() as mp:
        if how == "raises":
            def boom(row):
                raise RuntimeError("injected: the page store's write fails")
            mp.setattr(db_module, "save_trade_page", boom)
        elif how == "refused":
            assert db_module.save_trade_page(_row(_time.time() + 3600, "a-newer-deck"))
        elif how == "ineligible":
            with server._trade_jobs_lock:
                server._trade_jobs[job_id]["experiment_digest"] = None
        else:
            with server._trade_jobs_lock:
                server._revoke_trade_job_locked(server._trade_jobs[job_id], "inputs_changed")
        assert server._store_trade_page(job_id) is False


@pytest.mark.parametrize("how, pack_first", [
    ("raises", True), ("raises", False), ("refused", True), ("refused", False),
    ("ineligible", True), ("ineligible", False), ("revoked", True)])
def test_store_count_zero_when_the_store_writes_no_row(deferred, how, pack_first):
    """#434 QA P2-1 (a)-(c): the deck is page-scoped (page_store 1) but its
    store wrote no row, so no card has a stored snapshot. Its stored count is
    recorded as 0, in the pack's header whether the pack came before the
    store (pages delivered while the job ran) or after (the first delivery),
    and card 40 (delivered on page 2, under 90, packed: past the first 30's
    full rows) missed after a restart is a restart_split, not other."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=not pack_first, store=False)
    if pack_first:
        delivered_before_completion(client, job_id)
    store_fails(job_id, how)
    if not pack_first:
        for cursor in (0, 30):                             # the first delivery writes the pack
            status(client, job_id, cursor)
    run = unpack(pack_of(engine, job_id))[0]
    assert (run["page_store"], run["stored_count"]) == (1, 0)
    assert db_module.load_trade_page_for_job(UID, job_id) is None
    restart()
    view(job_id, 40)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_store_count_zero_when_the_process_died_before_its_store(deferred):
    """#434 QA P2-1, the read side: the pack's first write happened (a page
    delivered while the job ran) and the process died before its store ran:
    no row, no stored_count anywhere. No record that a store wrote reads as
    0, so a delivered card under 90 (40) is a restart_split."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False)
    delivered_before_completion(client, job_id)
    restart()                                              # no _store_trade_page
    view(job_id, 40)
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_store_count_a_late_store_keeps_a_count_the_pack_already_has(deferred):
    """#434 QA P3-2: the late store only fills a missing stored_count; a pack
    that already has one (77, here) keeps it when the store lands."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False)
    delivered_before_completion(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with server._deck_evidence_write_lock:
        ev.pack.run["stored_count"] = 77
        assert server._deck_pack_commit(job_id, ev.pack)
    assert server._store_trade_page(job_id)
    assert unpack(pack_of(engine, job_id))[0]["stored_count"] == 77
