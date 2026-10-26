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
    server._deck_live_stamped.clear()


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
    a.run["upgrade_misses"] = 1
    assert server._deck_pack_commit(job_id, a)
    b.run["deliveries"] = first + [[59, "2026-10-27T00:09:59+00:00"], [74, "2026-10-27T00:01:14+00:00"]]
    b.run.update(retired=True, retired_at="2026-10-27T01:00:00+00:00")
    assert server._deck_pack_commit(job_id, b)             # a CAS miss, merged, retried
    run, _cards = unpack(pack_of(engine, job_id))          # the checksum holds
    assert run["deliveries"] == first + [[59, "2026-10-27T00:00:59+00:00"],
                                         [74, "2026-10-27T00:01:14+00:00"],
                                         [89, "2026-10-27T00:01:29+00:00"]]
    assert (run["upgrade_misses"], run["retired"], run["retired_at"]) == (
        1, True, "2026-10-27T01:00:00+00:00")


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

def fail_withdrawal_inserts(monkeypatch):
    """The withdrawal insert raises inside its transaction."""
    def boom(conn, rows_):
        if rows_:
            raise RuntimeError("injected: the transaction fails")
        return 0
    monkeypatch.setattr(db_module, "_insert_withdrawals", boom)


def boundaries(engine, job_id):
    row = pack_of(engine, job_id)
    return [d[0] for d in unpack(row)[0]["deliveries"]] if row is not None else None


def test_p3_5_a_header_update_and_its_withdrawal_land_together(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    own_all_but(engine, 40)
    real = db_module._insert_withdrawals
    fail_withdrawal_inserts(monkeypatch)
    status(client, job_id, 30)                             # boundary 59 and card 40's drop
    assert withdrawals(engine) == {} and boundaries(engine, job_id) == [29]
    monkeypatch.setattr(db_module, "_insert_withdrawals", real)
    status(client, job_id, 60)                             # the next delivery carries both
    assert withdrawals(engine)[40]["served_before"] == 0
    assert boundaries(engine, job_id) == [29, 59, 89]


def test_p3_5_the_pack_insert_and_its_withdrawal_land_together(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    own_all_but(engine, 5)
    real = db_module._insert_withdrawals
    fail_withdrawal_inserts(monkeypatch)
    status(client, job_id, 0)
    assert withdrawals(engine) == {} and pack_of(engine, job_id) is None
    monkeypatch.setattr(db_module, "_insert_withdrawals", real)
    status(client, job_id, 30)                             # the next delivery carries both
    assert withdrawals(engine)[5]["served_before"] == 0 and boundaries(engine, job_id) == [29, 59]


def test_p3_5_stage_1_rows_and_their_withdrawal_land_together(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, store=False)
    own_all_but(engine, 5)
    real = db_module._insert_withdrawals
    fail_withdrawal_inserts(monkeypatch)
    status(client, job_id, 0)
    assert withdrawals(engine) == {} and rows(engine) == []
    monkeypatch.setattr(db_module, "_insert_withdrawals", real)
    status(client, job_id, 30)                             # the next delivery carries both
    assert withdrawals(engine)[5]["served_before"] == 0
    assert sorted(i for (g, i), r in by_index(engine).items() if not g and r["delivered_at"]) == [
        i for i in range(60) if i != 5]


def test_p3_5_a_live_stamp_and_its_withdrawal_land_together(deferred, prepared_ok, monkeypatch):
    client, engine, _ = deferred
    job_id, _ids = live_deck(120)
    own_all_but(engine, 7)
    real = db_module._insert_withdrawals
    fail_withdrawal_inserts(monkeypatch)
    status(client, job_id, 0)
    assert withdrawals(engine) == {} and stamped(engine, job_id) == {}
    monkeypatch.setattr(db_module, "_insert_withdrawals", real)
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
    cards, run = server._deck_pack_input(ev)
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
