"""The deletion scrub, stage 2: packs through the codec (legal R28.22, models-lead
addendum G: G-a1 to G-a3), and the cached writer state that must not undo or
leak around a scrub. Harness: test_deletion_scrub's engine and seed."""
import json

from sqlalchemy import insert, select

from backend import accounts, database as db, deletion_scrub as scrub
from backend.eval import evidence_pack
from backend.tests.test_deletion_scrub import (  # noqa: F401  (fixture)
    DEL, EARLY, LEAGUE, OTHER, VIEWER, engine, job, read)

SHARED = {"user_id": VIEWER, "league_id": LEAGUE, "deck_job_id": "deck-pack",
          "served_at": EARLY, "candidate_set_id": None, "candidate_set_size": None,
          "ranked_player_count": 12, "user_value_basis": "personal",
          "last_board_update_at": None}


def packed_cards():
    def card(i, partner, **extra):
        return {**SHARED, "card_index": i, "trade_hash": f"{i:016x}", "shape": "1x1",
                "shape_bucket": "1x1", "lane": "value", "archetype": "value",
                "basis": "divergence", "give_positions": ["WR"], "receive_positions": ["RB"],
                "give_value": 100.0 + i, "receive_value": 101.0 + i, "surplus_margin": 7.5,
                "fairness_score": 0.9, "likes_you": False, "relaxed": False,
                "involves_pick": False, "partner_user_id": partner, "propensity": 1.25,
                "base_score": 150.0 + i, "final_score": 160.0 + i, "model_arm": "current",
                "arm_rank": i, "taste_attrs": [f"partner:{partner}", "recvpos:RB"], **extra}
    return [card(0, DEL, likes_you=True), card(1, OTHER), card(2, DEL), card(3, OTHER)]


RUN = {"values_snapshot_id": 7, "deliveries": [[3, "2026-01-01T00:05:00+00:00"]],
       "filter_inputs": {"v": 1, "filter_ran": True, "viewer_team": VIEWER,
                         "qb_te": {VIEWER: ["q0"], DEL: ["q1"], OTHER: ["q2"]},
                         "protected": [f"{0:016x}", f"{1:016x}"]}}


def insert_pack(engine, run_id="deck-pack", league=LEAGUE, user=VIEWER, run=None, cards=None):
    cards = cards or [{**c, "deck_job_id": run_id, "league_id": league, "user_id": user}
                      for c in packed_cards()]
    packed = evidence_pack.pack_run(run or RUN, cards, card_count=4)
    with engine.begin() as conn:
        conn.execute(insert(db.deck_evidence_packs_table).values(
            run_id=run_id, user_id=user, league_id=league, served_at=EARLY,
            pack_version=packed.pack_version, header_json=packed.header_json,
            cards_blob=packed.cards_blob, checksum=packed.checksum, card_count=4,
            created_at=EARLY))
    return evidence_pack.unpack_run(packed)


def stored_pack(engine, run_id="deck-pack"):
    (row,) = read(engine, db.deck_evidence_packs_table, run_id=run_id)
    run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
        row["pack_version"], row["header_json"], bytes(row["cards_blob"]), row["checksum"],
        row["card_count"]))
    return row, run, cards


def test_a_pack_is_rewritten_through_the_codec_with_exactly_the_four_changes(engine):
    before_run, before = insert_pack(engine)
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    assert scrub.run_pending() == 1
    row, run, cards = stored_pack(engine)            # unpack_run checks the checksum
    assert (row["card_count"], row["pack_version"]) == (4, evidence_pack.PACK_VERSION)
    # Non-redacted cards: bit for bit (G-a2).
    for i in (1, 3):
        assert json.dumps(cards[i], sort_keys=True) == json.dumps(before[i], sort_keys=True)
    # Redacted cards: the token, likes_you removed (never False), scores null.
    for i in (0, 2):
        want = {**before[i], "partner_user_id": token, "surplus_margin": None,
                "base_score": None, "final_score": None,
                "taste_attrs": [f"partner:{token}", "recvpos:RB"]}
        want.pop("likes_you")
        assert cards[i] == want
    # The run: the holdings and the protected hash of the person's card go,
    # redacted_at is added, and nothing else moves.
    inputs = run["filter_inputs"]
    assert inputs["qb_te"] == {VIEWER: ["q0"], OTHER: ["q2"]}
    assert inputs["protected"] == [f"{1:016x}"]
    assert run["redacted_at"] >= job(engine)["deleted_at"]
    assert {k: v for k, v in run.items() if k not in ("filter_inputs", "redacted_at")} == {
        k: v for k, v in before_run.items() if k != "filter_inputs"}
    assert DEL not in row["header_json"]


def test_eval_reads_the_other_cards_unchanged(engine):
    """G-a2's replay identity, through eval's own reader: every non-redacted
    card load_decks builds from the pack is the same before and after."""
    from backend.eval import data as eval_data
    insert_pack(engine)

    def cards_by_index():
        (deck,) = [d for d in eval_data.load_decks(engine=engine) if d.deck_job_id == "deck-pack"]
        return {c.card_index: c for c in deck.cards}
    before = cards_by_index()
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    after = cards_by_index()
    assert set(after) == set(before)
    for i in (1, 3):
        assert repr(after[i]) == repr(before[i])
    for i in (0, 2):
        assert repr(after[i]) != repr(before[i])


def test_a_pack_in_a_league_the_person_left_is_found_by_the_scan(engine):
    with engine.begin() as conn:
        conn.execute(insert(db.league_members_table).values(league_id="league-left", user_id=OTHER))
    insert_pack(engine, run_id="deck-left", league="league-left", user=OTHER)
    accounts.delete_user_data(DEL)
    assert "league-left" not in json.loads(job(engine)["league_ids_json"])
    scrub.run_pending()
    _row, _run, cards = stored_pack(engine, "deck-left")
    assert cards[0]["partner_user_id"] == job(engine)["token"]


def test_redacting_a_pack_twice_changes_nothing(engine):
    insert_pack(engine)
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    (row,) = read(engine, db.deck_evidence_packs_table, run_id="deck-pack")
    ids = json.loads(job(engine)["partner_ids_json"])
    assert scrub.redact_pack(row, ids, job(engine)["token"], "2027-01-01T00:00:00+00:00") is None


def test_a_pack_that_names_nobody_deleted_is_untouched(engine):
    cards = [{**c, "partner_user_id": OTHER, "taste_attrs": ["recvpos:RB"]} for c in packed_cards()]
    run = {**RUN, "filter_inputs": {**RUN["filter_inputs"], "qb_te": {VIEWER: ["q0"]}}}
    insert_pack(engine, cards=cards, run=run)
    (before,) = read(engine, db.deck_evidence_packs_table, run_id="deck-pack")
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    (after,) = read(engine, db.deck_evidence_packs_table, run_id="deck-pack")
    assert after == before


def test_a_concurrent_header_update_makes_the_scrub_redo_on_the_new_row(engine, monkeypatch):
    """The scrub's write is a CAS on the checksum it read: a live writer's
    header update in between makes it re-read and redo, keeping that update."""
    insert_pack(engine)
    accounts.delete_user_data(DEL)
    real = scrub.redact_pack
    raced = []

    def racing(row, ids, token, now):
        if not raced:                         # a delivery lands between the read and the write
            raced.append(1)
            run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
                row["pack_version"], row["header_json"], bytes(row["cards_blob"]),
                row["checksum"], row["card_count"]))
            moved = evidence_pack.pack_run({**run, "retired": True}, cards, card_count=4)
            db.update_deck_evidence_pack_header("deck-pack", moved.header_json, moved.checksum,
                                                row["checksum"])
        return real(row, ids, token, now)
    monkeypatch.setattr(scrub, "redact_pack", racing)
    scrub.run_pending()
    _row, run, cards = stored_pack(engine)
    assert run["retired"] is True and cards[0]["partner_user_id"] == job(engine)["token"]


# ── The cached writer state (server._fresh_pack_state) ──────────────────────

def test_a_writers_header_update_after_a_scrub_keeps_the_scrub(engine):
    """head-eng's ruling 2: a state cached before the scrub, committing a new
    delivery after it, must neither write the old partner dictionary back nor
    leave a checksum over the old cards."""
    import backend.server as server
    insert_pack(engine)
    state = server._load_pack_state("deck-pack", VIEWER)        # a live writer's cache
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    state.header["run"]["retired"] = True                       # its pending change
    assert server._deck_pack_commit("deck-pack", state) is True
    row, run, cards = stored_pack(engine)                       # unpacks: the checksum holds
    assert run["retired"] is True and "redacted_at" in run
    assert cards[0]["partner_user_id"] == job(engine)["token"] and DEL not in row["header_json"]
    assert run["filter_inputs"]["qb_te"] == {VIEWER: ["q0"], OTHER: ["q2"]}


def test_a_stale_cached_state_reloads_once_and_a_plain_update_doesnt_reload(engine):
    import backend.server as server
    insert_pack(engine)
    state = server._load_pack_state("deck-pack", VIEWER)
    server._deck_pack_card(state, 0)                            # builds its index of the old cards
    # Another instance's plain header update: only the run changes.
    other = server._load_pack_state("deck-pack", VIEWER)
    other.header["run"]["retired"] = True
    assert server._deck_pack_commit("deck-pack", other)
    assert server._fresh_pack_state(state, "deck-pack") is False
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    assert server._fresh_pack_state(state, "deck-pack") is True
    assert server._deck_pack_card(state, 0)["partner_user_id"] == job(engine)["token"]
    assert state.run["redacted_at"] and state.run["retired"] is True
    assert server._fresh_pack_state(state, "deck-pack") is False


def test_a_held_rows_upgrade_after_a_scrub_takes_the_packs_token(engine):
    """An upgrade from the deck's build-time snapshot (the job in process, or
    the page store's blob) after the scrub: the pack's card names the token,
    so the row is redacted the same way; a card of another partner isn't."""
    import backend.server as server
    from backend.tests.test_deletion_scrub import RICH, features_for
    insert_pack(engine)
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    state = server._load_pack_state("deck-pack", VIEWER)
    token = job(engine)["token"]
    held = {"impression_id": "deck-pack:0", "base_score": 150.0, "final_score": 160.0,
            "source_like_impression_id": "like-1",
            "features_json": json.dumps(features_for(DEL, **RICH)),
            "valuation_json": json.dumps({"partner_board": {"n": 1}, "market": {"r": 1}})}
    row = server._redacted_held_row(held, state, 0)
    f = json.loads(row["features_json"])
    assert f["partner_user_id"] == token and "likes_you" not in f and f["surplus_margin"] is None
    assert (row["base_score"], row["final_score"], row["source_like_impression_id"]) == (None, None, None)
    assert json.loads(row["valuation_json"]) == {"market": {"r": 1}}
    other = {**held, "impression_id": "deck-pack:1", "features_json": json.dumps(features_for(OTHER))}
    assert server._redacted_held_row(other, state, 1) == other
