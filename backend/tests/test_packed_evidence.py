"""ADR-025 stage 2: packed deck evidence (S8), flag trade.packed_evidence.

Spec: docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6-§9;
models-lead R2.4 addendum §2-§3 and R4.2 (U1-U8).

Harness: test_deferred_evidence's `deferred` (p1's real worker and routes,
flag on, evidence writes inline).
"""
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
    assert run["retired"] is False and run["upgrade_misses"] == 0
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
    assert unpack(pack_of(engine, job_id))[0]["upgrade_misses"] == 0
    assert [o["impression_id"] for o in outcomes(engine)] == [contract.card_impression_id(job_id, 50)]


def test_r42_a_card_past_the_stored_ones_viewed_after_a_restart_is_a_counted_miss(deferred):
    """models-lead (b): delivered past the stored 90 before a deploy, viewed
    from the device after it. Its row comes from the packed card itself."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)                             # the live job's page past the stored 90
    restart()
    view(job_id, 95)
    got = by_index(engine)[(0, 95)]
    assert got["evidence_tier"] == "viewed" and got["assets_json"] is None
    assert set(json.loads(got["features_json"])) <= contract.FROZEN_INPUT_KEYS | {"page_store"}
    run, cards = unpack(pack_of(engine, job_id))
    assert run["upgrade_misses"] == 1
    assert json.loads(got["features_json"])["give_value"] == cards[95]["give_value"]
    assert [o["impression_id"] for o in outcomes(engine)] == [contract.card_impression_id(job_id, 95)]


def test_s8_a_delivery_lost_to_a_crash_is_recorded_before_its_outcome(deferred, monkeypatch):
    """models-eng's condition 4: page 2's header update never landed (the
    process died); after the restart, the outcome on one of its cards writes
    the delivery first."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    real = db_module.update_deck_evidence_pack_header
    monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", lambda *a: True)   # lost
    status(client, job_id, 30)
    assert [d[0] for d in unpack(pack_of(engine, job_id))[0]["deliveries"]] == [29]
    restart()
    monkeypatch.setattr(db_module, "update_deck_evidence_pack_header", real)
    view(job_id, 45)
    deliveries = unpack(pack_of(engine, job_id))[0]["deliveries"]
    assert deliveries[-1][0] >= 45
    assert by_index(engine)[(0, 45)]["evidence_tier"] == "viewed" and outcomes(engine)


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
                        lambda ev: (_time.sleep(0.5), real(ev))[1])
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
