"""The deletion scrub, stage 2: packs through the codec (legal R28.22, models-lead
addendum G: G-a1 to G-a3), and the cached writer state that must not undo or
leak around a scrub. Harness: test_deletion_scrub's engine and seed."""
import json

from sqlalchemy import insert, select, update

from backend import accounts, database as db, deletion_scrub as scrub
from backend.eval import evidence_pack
from backend.tests.test_deletion_scrub import (  # noqa: F401  (fixture)
    DEL, EARLY, LEAGUE, OTHER, VIEWER, engine, job, read)
from backend.tests.test_trade_page_store import p1, spawned  # noqa: F401  (fixtures)
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import deferred  # noqa: F401  (fixture)

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


# ── The page store ──────────────────────────────────────────────────────────

def page_card(partner, i, **extra):
    return {"trade_id": f"t{i}", "league_id": LEAGUE, "target_user_id": partner,
            "target_username": "name", "give": [{"id": "g"}], "receive": [{"id": "r"}],
            "decision": None, "impression_id": f"deck-page:{i}", "mismatch_score": 9.0,
            "composite_score": 150.0, "narrative": "n", **extra}


def insert_page(engine, league=LEAGUE, user=VIEWER, deck="deck-page"):
    from backend.tests.test_deletion_scrub import RICH, features_for
    rich = dict(likes_you=True, standing_offer_reason="x", reasons=["they rank r at 2x"],
                rationale={"counterparty": {"timeline": "declared"}}, fit={"them": 70.0},
                breaker={"objections": ["o"]},
                match_context={"opponent_outlook": {"source": "declared", "value": "rebuild"},
                               "user_needs": ["QB"]})
    pages = {"v": 1, "opponents_total": 2,
             "cards": [page_card(DEL, 0, **rich), page_card(OTHER, 1)]}
    evidence = {"v": 1, "served_at": EARLY, "league_id": league,
                "rows": [{"impression_id": "deck-page:0", "card_index": 0, "trade_hash": "h0",
                          "base_score": 150.0, "final_score": 160.0,
                          "source_like_impression_id": "l",
                          "features_json": json.dumps(features_for(DEL, **RICH)),
                          "valuation_json": json.dumps({"partner_board": {}, "market": {}})},
                         {"impression_id": "deck-page:1", "card_index": 1, "trade_hash": "h1",
                          "base_score": 1.0, "features_json": json.dumps(features_for(OTHER))}],
                "candidate_set": {"candidates_json": json.dumps(
                    [{"trade_hash": "h0", "partner": DEL, "base_score": 1.0}])},
                "trade_impressions": [{"target_user_id": DEL}, {"target_user_id": OTHER}],
                "run_meta": {"filter_inputs": {"qb_te": {DEL: ["q"], OTHER: ["q2"]},
                                               "protected": ["h0", "h1"]}}}
    with engine.begin() as conn:
        conn.execute(insert(db.trade_page_store_table).values(
            user_id=user, league_id=league, scoring_format="1qb_ppr", request_scope="organic",
            roster_fp="r", values_snapshot_id="v", engine_version="e", config_signature="c",
            experiment_digest="d", deck_job_id=deck, built_at=EARLY,
            expires_at="2999-01-01T00:00:00+00:00", card_count=2, pages_blob=pages,
            evidence_blob=evidence, stored_bytes=1, state="ready"))
    return pages


def test_a_page_rows_cards_and_evidence_are_redacted(engine):
    pages = insert_page(engine)
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    (row,) = read(engine, db.trade_page_store_table)
    c0, c1 = row["pages_blob"]["cards"]
    assert c1 == pages["cards"][1]                               # another partner's card
    assert (c0["target_user_id"], c0["target_username"]) == (token, accounts.DELETED_USER_PLACEHOLDER)
    for key in ("likes_you", "standing_offer_reason", "reasons", "rationale", "fit", "breaker"):
        assert key not in c0, key
    assert (c0["mismatch_score"], c0["composite_score"]) == (None, None)
    assert c0["match_context"] == {"user_needs": ["QB"]}
    ev = row["evidence_blob"]
    r0 = ev["rows"][0]
    assert json.loads(r0["features_json"])["partner_user_id"] == token
    assert (r0["base_score"], r0["final_score"], r0["source_like_impression_id"]) == (None, None, None)
    assert json.loads(r0["valuation_json"]) == {"market": {}}
    assert ev["rows"][1]["features_json"] == json.dumps(
        __import__("backend.tests.test_deletion_scrub", fromlist=["x"]).features_for(OTHER))
    assert json.loads(ev["candidate_set"]["candidates_json"]) == [
        {"trade_hash": "h0", "partner": token, "base_score": None}]
    assert ev["trade_impressions"] == [{"target_user_id": None}, {"target_user_id": OTHER}]
    assert ev["run_meta"]["filter_inputs"] == {"qb_te": {OTHER: ["q2"]}, "protected": ["h1"]}
    assert DEL not in json.dumps(row["pages_blob"]) + json.dumps(ev)
    assert row["stored_bytes"] == (len(db.CompressedJSON.encode(row["pages_blob"]))
                                   + len(db.CompressedJSON.encode(ev)))



def test_a_page_cards_roster_evaluation_is_redacted_as_on_a_deck_row():
    """With trade.roster_protection on, a page card carries the card's
    roster_evaluation (server._card_to_dict): every team's entry, keyed by
    user id, and the partner's side, mutual_benefit (#559 QA)."""
    token = "redacted:" + "a" * 32
    roster = {"teams": {VIEWER: {"outlook": "contend"}, DEL: {"outlook": "rebuild"},
                        OTHER: {"outlook": "rebuild"}},
              "mutual_benefit": {"them": 4.0}, "verdict": "ok"}
    theirs = scrub.redact_page_card(page_card(DEL, 0, roster_evaluation=roster), {DEL}, token)
    assert theirs["roster_evaluation"] == {
        "teams": {VIEWER: {"outlook": "contend"}, OTHER: {"outlook": "rebuild"}}, "verdict": "ok"}
    # Another partner's card that lists the person's team keeps its own read.
    other = scrub.redact_page_card(page_card(OTHER, 1, roster_evaluation=roster), {DEL}, token)
    assert other["roster_evaluation"] == {
        "teams": {VIEWER: {"outlook": "contend"}, OTHER: {"outlook": "rebuild"}},
        "mutual_benefit": {"them": 4.0}, "verdict": "ok"}
    assert DEL not in json.dumps(theirs) + json.dumps(other)

def test_a_page_row_in_a_league_the_person_left_is_found_by_the_scan(engine):
    insert_page(engine, league="league-left", user=OTHER, deck="deck-left-page")
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    (row,) = read(engine, db.trade_page_store_table)
    assert row["pages_blob"]["cards"][0]["target_user_id"] == job(engine)["token"]


# ── J4: a redacted card never serves, in any I-1 mode ───────────────────────

TOKEN_CARD = {"trade_id": "t0", "target_user_id": "redacted:" + "0" * 32, "impression_id": "d:0"}
PLAIN_CARD = {"trade_id": "t1", "target_user_id": OTHER, "impression_id": "d:1"}


def test_the_serve_rules_drop_a_redacted_card_in_every_mode(monkeypatch):
    """models-lead addendum J4: at prod's trade_i1_mode 1, S0's check serves
    every card, so the drop sits ahead of it in _roster_serve_rules, which
    /generate, /status (legacy and paged) and the page-store serve share."""
    import backend.server as server
    monkeypatch.setattr(server, "_roster_serve_check",
                        lambda cards, *a, **k: (list(cards), None, False))   # lenient: all serve
    monkeypatch.setattr(server, "_gate_miss_test", lambda league_id: None)
    for mode in (0, 1, 2):
        monkeypatch.setattr(server, "_trade_i1_mode", lambda m=mode: m)
        cards, block, _ = server._roster_serve_rules([TOKEN_CARD, PLAIN_CARD], LEAGUE, VIEWER, "d")
        assert (cards, block) == ([PLAIN_CARD], None), mode


def test_a_redacted_card_is_withdrawn_as_partner_deleted_and_counted_apart():
    import backend.server as server
    assert server._withdrawal_reasons([TOKEN_CARD, PLAIN_CARD], [{"impression_id": "d:2"}]) == {
        "d:0": "partner_deleted", "d:1": "i1_dropped", "d:2": "disposition_cut"}


def test_at_mode_1_a_stored_page_never_serves_its_redacted_card(p1, spawned, monkeypatch):
    """The J4 scenario end to end: the scrub has rewritten a stored deck's
    card (its target is the token). At trade_i1_mode 1, page 1 serves every
    other card, and the redacted one leaves as a never-delivered withdrawal,
    reason partner_deleted."""
    import backend.server as server
    from backend.tests.test_trade_page_store import generate, run_job, stored
    client, engine, _ = p1
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_i1_mode", 1.0)
    run_job()
    row = stored()
    cards = row["pages_blob"]["cards"]
    token = "redacted:" + "1" * 32
    redacted = cards[0]["impression_id"]
    # The scrub's own rewrite of the card (its target is the person's id).
    rewritten = [scrub.redact_page_card(cards[0], {cards[0]["target_user_id"]}, token)] + cards[1:]
    with engine.begin() as conn:
        conn.execute(update(db.trade_page_store_table).values(
            pages_blob={**row["pages_blob"], "cards": rewritten}))
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page"
    assert redacted not in [c["impression_id"] for c in body["cards"]]
    assert {c["impression_id"] for c in body["cards"]} == {c["impression_id"] for c in cards[1:]}
    rows = read(engine, db.deck_card_withdrawals_table)
    assert [(r["reason"], r["served_before"]) for r in rows] == [("partner_deleted", 0)]


# ── G-a2's unpack test (models-lead addendum J2) ─────────────────────────────

def test_g_a2_unpack_equals_the_original_with_items_1_to_5_applied(engine):
    """models-lead addendum J2: unpack(redacted) == unpack(original) with
    E-b2's items 1-5 applied, written out here apart from the scrub's code;
    every other card bit-identical; the codec round-trips a null float."""
    before_run, before = insert_pack(engine)
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    _row, run, cards = stored_pack(engine)

    def items_1_to_5(card):
        if card["partner_user_id"] != DEL:
            return card
        out = {k: v for k, v in card.items() if k != "likes_you"}         # 2: c2 fields removed
        out["partner_user_id"] = token                                    # 1: the token
        out["taste_attrs"] = [f"partner:{token}" if a == f"partner:{DEL}" else a
                              for a in card["taste_attrs"]]
        out.update(base_score=None, final_score=None, surplus_margin=None)  # 5: blended nulled
        return out
    assert cards == [items_1_to_5(c) for c in before]
    for got, was in zip(cards, before):
        if was["partner_user_id"] != DEL:
            assert json.dumps(got, sort_keys=True) == json.dumps(was, sort_keys=True)
    assert cards[0]["base_score"] is None and isinstance(before[0]["base_score"], float)
    inputs = run["filter_inputs"]                                         # 3: holdings, protected
    assert DEL not in inputs["qb_te"] and f"{0:016x}" not in inputs["protected"]
    assert run["redacted_at"]                                             # 4: redacted_at


# ── #559 QA P2: in-memory jobs naming the person are revoked at deletion ───

def test_deletion_revokes_the_live_jobs_that_name_the_person(engine, monkeypatch):
    """The scrub rewrites stored decks only. A job held in this process keeps
    the person's original cards, and at trade_i1_mode 0 or 1 it would serve
    them until it leaves memory, so the delete route revokes it, whether its
    cards are dicts or TradeCard objects. A running job in their league is
    revoked too, with the neutral inputs_changed: its owner is a leaguemate
    (#559 re-QA P2-a). Another league's job is left alone."""
    from types import SimpleNamespace
    import backend.server as server
    monkeypatch.setattr(server, "touch_user_activity", lambda *a, **kw: None)
    monkeypatch.setattr(accounts, "apple_identity_subjects", lambda *a, **kw: set())
    jobs = {
        "names-them": {"key": (VIEWER, LEAGUE, "1qb_ppr"), "status": "complete",
                       "cards": [{"target_user_id": DEL, "trade_id": "t0"},
                                 {"target_user_id": OTHER, "trade_id": "t1"}]},
        "running-there": {"key": (OTHER, LEAGUE, "1qb_ppr"), "status": "running", "cards": []},
        "elsewhere": {"key": (VIEWER, "league-other", "1qb_ppr"), "status": "complete",
                      "cards": [{"target_user_id": OTHER, "trade_id": "t2"}]},
        "card-objects": {"key": (OTHER, "league-other", "1qb_ppr"), "status": "complete",
                         "cards": [SimpleNamespace(target_user_id=OTHER, trade_id="t3"),
                                   SimpleNamespace(target_user_id=DEL, trade_id="t4")]},
    }
    monkeypatch.setattr(server, "_trade_jobs", jobs)
    with server._sessions_lock:
        server._sessions["synthetic-delete-token"] = {"user_id": DEL, "verified": True}
    try:
        response = server.app.test_client().delete(
            "/api/account", headers={"X-Session-Token": "synthetic-delete-token"})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["deleted"]["trade_jobs_revoked"] == 3
    finally:
        with server._sessions_lock:
            server._sessions.pop("synthetic-delete-token", None)
    assert jobs["names-them"]["superseded"] and jobs["names-them"]["cards"] == []
    assert jobs["card-objects"]["superseded"] and jobs["card-objects"]["cards"] == []
    running = jobs["running-there"]
    assert running["superseded"] and (running["status"], running["error"]) == ("error", "inputs_changed")
    assert not jobs["elsewhere"].get("superseded") and jobs["elsewhere"]["cards"]


def _delete_through_the_route(server, monkeypatch, sessions=()):
    monkeypatch.setattr(server, "touch_user_activity", lambda *a, **kw: None)
    monkeypatch.setattr(accounts, "apple_identity_subjects", lambda *a, **kw: set())
    tokens = {"synthetic-delete-token": {"user_id": DEL, "verified": True},
              **{f"synthetic-viewer-{i}": sess for i, sess in enumerate(sessions)}}
    with server._sessions_lock:
        server._sessions.update(tokens)
    try:
        response = server.app.test_client().delete(
            "/api/account", headers={"X-Session-Token": "synthetic-delete-token"})
        assert response.status_code == 200, response.get_json()
        return response.get_json()["deleted"]
    finally:
        with server._sessions_lock:
            for token in tokens:
                server._sessions.pop(token, None)


def test_deletion_purges_every_sessions_trade_cards_naming_the_person(engine, monkeypatch):
    """A session's TradeService card store, shared with its trade jobs, keeps
    the cards it generated, and GET /api/trades serves them with no expiry
    (#559 re-QA P2-b). Deletion removes the person's cards from every
    session's services, every format's, and keeps everyone else's."""
    from types import SimpleNamespace
    import backend.server as server

    def store(*partners):
        return SimpleNamespace(_trade_cards={
            f"{p}-{i}": SimpleNamespace(trade_id=f"{p}-{i}", target_user_id=p)
            for i, p in enumerate(partners)})
    a, b, c = store(DEL, OTHER, DEL), store(DEL), store(OTHER)
    sessions = [{"user_id": VIEWER, "trade_svc": a, "trade_svcs": {"1qb_ppr": a, "sf_tep": b}},
                {"user_id": OTHER, "trade_svc": c}]
    deleted = _delete_through_the_route(server, monkeypatch, sessions)
    assert deleted["trade_cards_purged"] == 3
    assert [card.target_user_id for card in a._trade_cards.values()] == [OTHER]
    assert b._trade_cards == {} and len(c._trade_cards) == 1
    assert DEL in server._deleted_partner_ids


def test_get_trades_never_serves_a_card_written_after_the_purge(engine, monkeypatch):
    """A job still running at the deletion writes its cards straight into the
    session's store, after the purge; GET /api/trades filters them on the
    deleted ids (#559 re-QA P2-b)."""
    from unittest.mock import MagicMock
    import backend.server as server
    from backend.trade_service import TradeCard
    _delete_through_the_route(server, monkeypatch)

    def card(partner, i):
        return TradeCard(trade_id=f"late-{i}", league_id=LEAGUE, proposing_user_id=VIEWER,
                         target_user_id=partner, target_username="name",
                         give_player_ids=[f"g{i}"], receive_player_ids=[f"r{i}"],
                         mismatch_score=1.0, fairness_score=0.9, composite_score=0.5)
    service = MagicMock()
    service.get_pending_trades.return_value = [card(DEL, 0), card(OTHER, 1)]
    session = {"user_id": VIEWER, "verified": True, "active_format": "1qb_ppr",
               "league": MagicMock(), "players": [], "trade_svc": service}
    monkeypatch.setattr(server, "_get_session", lambda _token: session)
    monkeypatch.setattr(server, "_project_trade_dispositions", lambda cards, *a, **kw: cards)
    response = server.app.test_client().get(f"/api/trades?league_id={LEAGUE}",
                                            headers={"X-Session-Token": "viewer-token"})
    assert response.status_code == 200, response.get_json()
    assert [c["target_user_id"] for c in response.get_json()] == [OTHER]


# ── #559 QA1: the in-process upgrade reloads the scrubbed pack ─────────────

def test_an_in_process_upgrade_after_the_scrub_writes_the_redacted_row(deferred, monkeypatch):
    """A packed deck still held in this process: its partner deletes their
    account and the scrub rewrites the pack. A first view of a card past the
    first 30 then writes its full row from the job's build-time snapshot,
    after reloading the pack, so it carries the token, never the person's id
    or their fields (without the reload it wrote the original row back)."""
    from backend.tests.test_i1_serve_filter import OPP as PARTNER
    from backend.tests.test_packed_evidence import by_index, packed_deck, status, view
    client, engine, _ = deferred
    monkeypatch.setenv("FTF_DISABLE_DELETION_SCRUB_KICK", "1")
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 30)                 # the pack, delivered past 30
    accounts.delete_user_data(PARTNER)
    scrub.run_pending()
    token = job(engine)["token"]
    view(job_id, 45)                           # the job is still in this process
    row = by_index(engine)[(0, 45)]
    features = json.loads(row["features_json"])
    assert row["evidence_tier"] == "viewed"
    assert features["partner_user_id"] == token and "likes_you" not in features
    assert (row["base_score"], row["final_score"]) == (None, None)
    assert PARTNER not in row["features_json"]
