"""The deletion scrub (legal R28.20 (ii), R28.22; scope:
docs/plans/trade-time-to-suggestion/scope-deletion-scrub.md), stage 1: the job
written in the deletion's transaction, its lease, retry, grace pass, model
step and alert; deck_impressions, deck_candidate_sets, user_taste,
standing_offers and trade_matches. Synthetic ids only."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, insert, select

from backend import accounts, database as db, deletion_scrub as scrub
from backend.eval import evidence_pack

DEL = "deleted-person"
AID = "deleted-account"
ALIAS = accounts.account_user_id(AID)
VIEWER = "viewer-person"
OTHER = "other-person"
LEAGUE = "league-scrub"
EARLY = "2026-01-01T00:00:00+00:00"
LATE = "2999-01-01T00:00:00+00:00"        # past any job's cutoff


def features_for(partner, **extra):
    return {"shape": "1x1", "basis": "divergence", "partner_user_id": partner,
            "give_value": 10.0, "receive_value": 11.0, "fairness_score": 0.9,
            "surplus_margin": 42.0, "taste_attrs": [f"partner:{partner}", "recvpos:RB"], **extra}


RICH = dict(
    likes_you=True, standing_offer=True, standing_offer_reason="x",
    negmem={"m": 1.0, "ver": 3, "exempt": True},
    fit={"you": 60.0, "them": 70.0, "aggregate": 130.0, "bucket": "both_win", "boards": "both",
         "ver": 1, "lenses": {"you": {"board": 1.0}, "them": {"board": 2.0}}},
    fit_diag={"you": 60.0, "them": 70.0, "bucket": "both_win", "ver": 1},
    breaker={"ver": 1, "objections": ["their untouchable"]}, breaker_shadow=None,
    roster_evaluation={"teams": {VIEWER: {"outlook": "contend"}, DEL: {"outlook": "explicit"}},
                       "mutual_benefit": {"partner_preference_source": "observed"}},
    owner_request={"input": {"user_id": VIEWER,
                             "members": [{"id": DEL, "elo": {"p1": 1500}, "board_updated_at": "t",
                                          "username": "n"}],
                             "opponent_sources": {DEL: {"p1": "board"}},
                             "manager_preferences": {VIEWER: {"targets": []}, DEL: {"targets": ["p1"]}},
                             "opponent_outlooks": {DEL: "rebuild", OTHER: "contend"},
                             "inferred_outlooks": {DEL: "rebuild", VIEWER: "contend"}}},
)
VALUATION = {
    "basis": "divergence", "market": {"viewer_gives": 10, "viewer_receives": 11},
    "viewer_board": {"n": 3}, "partner_board": {"n": 4}, "mutual": {"trade_confidence": 0.5},
    "policy": {"model_arm": "a", "policy_floor": 1.0, "effective_floor": 2.0},
    "assets": [{"id": "p1", "market": 5.0, "viewer_raw_value": 1.0, "partner_raw_value": 2.0,
                "partner_effective_value": 2.5, "partner_confidence": 0.4}],
}


def impression(conn, iid, partner, *, served_at=EARLY, features=None, valuation=None):
    conn.execute(insert(db.deck_impressions_table).values(
        impression_id=iid, user_id=VIEWER, league_id=LEAGUE, deck_job_id="deck-1",
        card_index=int(iid.rsplit("-", 1)[-1]) if iid[-1].isdigit() else 0,
        trade_hash="h" + iid, propensity=1.0, base_score=150.0, final_score=160.0,
        served_at=served_at, source_like_impression_id="like-1",
        features_json=json.dumps(features or features_for(partner)),
        valuation_json=json.dumps(valuation) if valuation is not None else None))


MEMBERS = [{"trade_hash": "aa" * 8, "partner": DEL, "give": ["p1"], "receive": ["p2"],
            "base_score": 1.5, "in_deck": True},
           {"trade_hash": "bb" * 8, "partner": OTHER, "give": ["p3"], "receive": ["p4"],
            "base_score": 2.5, "in_deck": False}]


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    packed = evidence_pack.pack_candidates({"candidate_set_id": "cs-2"}, MEMBERS)
    with engine.begin() as conn:
        conn.execute(insert(db.accounts_table).values(
            account_id=AID, sleeper_user_id=DEL, created_at=EARLY))
        for uid in (DEL, VIEWER, OTHER):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid))
            conn.execute(insert(db.league_members_table).values(league_id=LEAGUE, user_id=uid))
        conn.execute(insert(db.leagues_table).values(sleeper_league_id=LEAGUE, user_id=VIEWER))
        impression(conn, "c-del-0", DEL, features=features_for(DEL, **RICH), valuation=VALUATION)
        impression(conn, "c-del-1", DEL)                              # uniformity: a plain card
        impression(conn, "c-other-2", OTHER, valuation=VALUATION)
        impression(conn, "c-late-3", DEL, served_at=LATE)
        conn.execute(insert(db.deck_candidate_sets_table).values(
            candidate_set_id="cs-1", deck_job_id="deck-1", user_id=VIEWER, league_id=LEAGUE,
            size=2, set_hash=evidence_pack.candidate_set_hash(MEMBERS),
            candidates_json=json.dumps(MEMBERS), created_at=EARLY))
        conn.execute(insert(db.deck_candidate_sets_table).values(
            candidate_set_id="cs-2", deck_job_id="deck-1", user_id=VIEWER, league_id=LEAGUE,
            size=2, set_hash=evidence_pack.candidate_set_hash(MEMBERS), candidates_json="[]",
            candidates_packed=packed.candidates_packed, cand_pack_version=packed.cand_pack_version,
            created_at=EARLY))
        for attr, w in ((f"partner:{DEL}", 1.0), (f"partner:{ALIAS}", 2.0), (f"partner:{OTHER}", 5.0)):
            conn.execute(insert(db.user_taste_table).values(
                user_id=VIEWER, attr=attr, w_short=w, w_long=w * 10, updated_at=EARLY))
        conn.execute(insert(db.standing_offers_table).values(
            user_id=VIEWER, league_id=LEAGUE, player_id="p1", round=1,
            team_user_ids=json.dumps([DEL, OTHER])))
        conn.execute(insert(db.trade_matches_table).values(
            league_id=LEAGUE, user_a_id=VIEWER, user_b_id=DEL, user_a_give="[]",
            user_a_receive="[]", match_valuation_json=json.dumps(VALUATION)))
    yield engine
    engine.dispose()


def read(engine, table, **where):
    with engine.connect() as conn:
        q = select(table)
        for k, v in where.items():
            q = q.where(table.c[k] == v)
        return [dict(r) for r in conn.execute(q).mappings()]


def card(engine, iid):
    (row,) = read(engine, db.deck_impressions_table, impression_id=iid)
    return row, json.loads(row["features_json"])


def job(engine):
    (row,) = read(engine, db.deletion_scrub_jobs_table)
    return row


def delete_and_scrub(engine):
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    return token


# ── The job ─────────────────────────────────────────────────────────────────

def test_the_deletion_writes_one_job_with_a_random_token_the_ids_and_the_leagues(engine):
    counts = accounts.delete_user_data(DEL)
    row = job(engine)
    assert counts["deletion_scrub_jobs_enqueued"] == 1
    assert row["token"].startswith("redacted:") and len(row["token"]) == len("redacted:") + 32
    assert DEL not in row["token"] and AID not in row["token"]
    assert set(json.loads(row["partner_ids_json"])) >= {DEL, ALIAS}
    # Captured before league_members lost the person's row (it's gone now).
    assert json.loads(row["league_ids_json"]) == [LEAGUE]
    assert read(engine, db.league_members_table, user_id=DEL) == []
    assert (row["db_version"], row["db_done_at"], row["model_done_at"]) == (0, None, None)


def test_a_rolled_back_deletion_leaves_no_job_and_no_side_table_change(engine):
    def fail(conn, cursor, statement, *a):
        if statement.lstrip().upper().startswith("DELETE FROM USERS"):
            raise RuntimeError("synthetic failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(Exception):
            accounts.delete_user_data(DEL)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert read(engine, db.deletion_scrub_jobs_table) == []
    assert {r["attr"] for r in read(engine, db.user_taste_table)} == {
        f"partner:{DEL}", f"partner:{ALIAS}", f"partner:{OTHER}"}


def test_each_token_is_new(engine):
    assert scrub.new_token() != scrub.new_token()


# ── The small stores, in the deletion transaction ───────────────────────────

def test_taste_for_the_person_takes_the_token_and_two_aliases_merge(engine):
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    rows = {r["attr"]: r for r in read(engine, db.user_taste_table, user_id=VIEWER)}
    assert set(rows) == {f"partner:{token}", f"partner:{OTHER}"}
    assert (rows[f"partner:{token}"]["w_short"], rows[f"partner:{token}"]["w_long"]) == (3.0, 30.0)
    assert rows[f"partner:{OTHER}"]["w_short"] == 5.0


def test_standing_offer_team_lists_take_the_token(engine):
    accounts.delete_user_data(DEL)
    (offer,) = read(engine, db.standing_offers_table)
    assert json.loads(offer["team_user_ids"]) == [job(engine)["token"], OTHER]


def test_the_match_valuation_goes_with_either_side(engine):
    with engine.begin() as conn:
        conn.execute(insert(db.trade_matches_table).values(
            league_id=LEAGUE, user_a_id=DEL, user_b_id=OTHER, user_a_give="[]",
            user_a_receive="[]", match_valuation_json="{}"))
        conn.execute(insert(db.trade_matches_table).values(
            league_id=LEAGUE, user_a_id=VIEWER, user_b_id=OTHER, user_a_give="[]",
            user_a_receive="[]", match_valuation_json="{}"))
    accounts.delete_user_data(DEL)
    got = {(r["user_a_id"], r["user_b_id"]): r["match_valuation_json"]
           for r in read(engine, db.trade_matches_table)}
    assert got == {(VIEWER, accounts.DELETED_USER_PLACEHOLDER): None,
                   (accounts.DELETED_USER_PLACEHOLDER, OTHER): None,
                   (VIEWER, OTHER): "{}"}


# ── deck_impressions ────────────────────────────────────────────────────────

def test_a_redacted_card_takes_the_token_and_loses_the_partners_fields(engine):
    token = delete_and_scrub(engine)
    row, f = card(engine, "c-del-0")
    assert f["partner_user_id"] == token
    assert f["taste_attrs"] == [f"partner:{token}", "recvpos:RB"]
    for key in ("likes_you", "standing_offer", "standing_offer_reason", "breaker", "breaker_shadow"):
        assert key not in f, key                                  # removed, never False (G-a1)
    assert f["surplus_margin"] is None
    assert f["negmem"] == {"m": 1.0, "ver": 3}
    assert f["fit"] == {"you": 60.0, "boards": "both", "ver": 1, "lenses": {"you": {"board": 1.0}}}
    assert f["fit_diag"] == {"you": 60.0, "ver": 1}
    assert f["roster_evaluation"] == {"teams": {VIEWER: {"outlook": "contend"}}}
    inputs = f["owner_request"]["input"]
    assert inputs["members"] == [{"id": token, "username": "n"}]
    assert inputs["opponent_sources"] == {} and inputs["manager_preferences"] == {VIEWER: {"targets": []}}
    assert inputs["opponent_outlooks"] == {OTHER: "contend"}
    assert inputs["inferred_outlooks"] == {VIEWER: "contend"}
    # Kept: consensus, the viewer's own, the platform's.
    assert (f["give_value"], f["receive_value"], f["fairness_score"], f["basis"]) == (
        10.0, 11.0, 0.9, "divergence")
    assert (row["base_score"], row["final_score"], row["source_like_impression_id"]) == (None, None, None)
    assert row["propensity"] == 1.0 and row["trade_hash"] == "hc-del-0"     # (viii): hashes stay
    v = json.loads(row["valuation_json"])
    assert v == {"basis": "divergence", "market": {"viewer_gives": 10, "viewer_receives": 11},
                 "viewer_board": {"n": 3}, "policy": {"model_arm": "a"},
                 "assets": [{"id": "p1", "market": 5.0, "viewer_raw_value": 1.0}]}
    assert DEL not in row["features_json"] and ALIAS not in row["features_json"]


def test_every_redacted_card_loses_the_same_fields(engine):
    """R28.22 b2: a plain card of the same partner is scrubbed the same way,
    so a field's absence on one card can't reveal what the other held."""
    token = delete_and_scrub(engine)
    row, f = card(engine, "c-del-1")
    assert f["partner_user_id"] == token and f["surplus_margin"] is None
    assert (row["base_score"], row["final_score"], row["source_like_impression_id"]) == (None, None, None)


def test_another_partners_card_and_a_later_deck_are_untouched(engine):
    with engine.connect() as conn:
        before = {r["impression_id"]: dict(r) for r in conn.execute(
            select(db.deck_impressions_table)).mappings()}
    delete_and_scrub(engine)
    for iid in ("c-other-2", "c-late-3"):
        assert card(engine, iid)[0] == before[iid], iid


def test_redact_features_is_idempotent_and_leaves_a_card_without_the_id_alone():
    once = scrub.redact_features(features_for(DEL, **RICH), {DEL}, "redacted:t")
    assert scrub.redact_features(once, {DEL}, "redacted:t") == once
    plain = features_for(OTHER)
    assert scrub.redact_features(plain, {DEL}, "redacted:t") == plain


def test_another_partners_card_loses_the_persons_owner_inputs_too():
    """The owner request rides on every card of its run with every member's
    outlook: on another partner's card the person's account fields go too
    (and their id is the token), while that card's own fields stay."""
    other = features_for(OTHER, **RICH)
    out = scrub.redact_features(other, {DEL}, "redacted:t")
    inputs = out["owner_request"]["input"]
    assert inputs["members"] == [{"id": "redacted:t", "username": "n"}]
    assert inputs["opponent_sources"] == {}
    assert inputs["manager_preferences"] == {VIEWER: {"targets": []}}
    assert inputs["opponent_outlooks"] == {OTHER: "contend"}
    assert inputs["inferred_outlooks"] == {VIEWER: "contend"}
    assert out["likes_you"] is True and out["surplus_margin"] == 42.0      # not a redacted card
    assert out["roster_evaluation"]["mutual_benefit"] == RICH["roster_evaluation"]["mutual_benefit"]


# ── bakeoff_runs (legal f's trace, 10-31) ───────────────────────────────────

OWNER_INPUT = {"user_id": VIEWER,
               "members": [{"id": DEL, "elo": {"p1": 1500}, "board_updated_at": "t"},
                           {"id": OTHER, "elo": {"p2": 1400}, "board_updated_at": "u"}],
               "opponent_sources": {DEL: {"p1": "board"}, OTHER: {"p2": "board"}},
               "manager_preferences": {VIEWER: {"t": 1}, DEL: {"t": 2}, OTHER: {"t": 3}},
               "opponent_outlooks": {DEL: "rebuild", OTHER: "contend"},
               "inferred_outlooks": {DEL: "rebuild"}}


def bakeoff_run(conn, run_id, league=LEAGUE, user=VIEWER):
    conn.execute(insert(db.bakeoff_runs_table).values(
        run_id=run_id, deck_job_id="deck-1", user_id=user, league_id=league, arm_order="[]",
        deck_size=1, arms_json="{}", created_at=EARLY,
        config_json=json.dumps({"owner_request": {"input": OWNER_INPUT, "unit": "team_draft"},
                                "per_opponent": {DEL: 1, OTHER: 2}})))


def test_a_bakeoff_runs_frozen_owner_input_loses_the_persons_account_fields(engine):
    """Other users' bakeoff runs keep the owner engine's full frozen input:
    every league member's board, sources, preferences and outlooks."""
    with engine.begin() as conn:
        bakeoff_run(conn, "run-1")
        bakeoff_run(conn, "run-left", league="league-gone", user=OTHER)
    token = delete_and_scrub(engine)
    for run_id in ("run-1", "run-left"):          # the second only through the scan
        (row,) = read(engine, db.bakeoff_runs_table, run_id=run_id)
        config = json.loads(row["config_json"])
        inputs = config["owner_request"]["input"]
        assert inputs["members"] == [{"id": token},
                                     {"id": OTHER, "elo": {"p2": 1400}, "board_updated_at": "u"}]
        assert inputs["opponent_sources"] == {OTHER: {"p2": "board"}}
        assert inputs["manager_preferences"] == {VIEWER: {"t": 1}, OTHER: {"t": 3}}
        assert inputs["opponent_outlooks"] == {OTHER: "contend"} and inputs["inferred_outlooks"] == {}
        assert config["per_opponent"] == {token: 1, OTHER: 2}
        assert DEL not in row["config_json"]


# ── deck_candidate_sets ─────────────────────────────────────────────────────

def test_candidate_members_take_the_token_through_the_codec_and_json(engine):
    token = delete_and_scrub(engine)
    want = [{**MEMBERS[0], "partner": token, "base_score": None}, MEMBERS[1]]
    (legacy,) = read(engine, db.deck_candidate_sets_table, candidate_set_id="cs-1")
    assert json.loads(legacy["candidates_json"]) == want
    (packed,) = read(engine, db.deck_candidate_sets_table, candidate_set_id="cs-2")
    run, members = evidence_pack.unpack_candidates(evidence_pack.PackedCandidates(
        packed["cand_pack_version"], packed["candidates_packed"]))
    assert run == {"candidate_set_id": "cs-2"} and members == want
    # The other member is bit-identical, and set_hash covers trade_hashes only.
    assert json.dumps(members[1]) == json.dumps(MEMBERS[1])
    assert packed["set_hash"] == evidence_pack.candidate_set_hash(want)


# ── A league the person left before deleting (head-eng, 10-31) ──────────────

LEFT = "league-they-left"


def seed_left_league(engine):
    """Decks in a league the person left before deleting: no membership, no
    import, no roster history and no own deck name them there, so the league
    pass can't find it."""
    with engine.begin() as conn:
        conn.execute(insert(db.league_members_table).values(league_id=LEFT, user_id=OTHER))
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id="left-0", user_id=OTHER, league_id=LEFT, deck_job_id="deck-left",
            card_index=0, trade_hash="hl", propensity=1.0, base_score=1.0, final_score=1.0,
            served_at=EARLY, features_json=json.dumps(features_for(DEL, likes_you=True))))
        conn.execute(insert(db.deck_candidate_sets_table).values(
            candidate_set_id="cs-left", deck_job_id="deck-left", user_id=OTHER, league_id=LEFT,
            size=2, set_hash=evidence_pack.candidate_set_hash(MEMBERS),
            candidates_json=json.dumps(MEMBERS), created_at=EARLY))


def test_a_partner_who_left_a_league_is_still_scrubbed_from_its_decks(engine):
    seed_left_league(engine)
    accounts.delete_user_data(DEL)
    assert LEFT not in json.loads(job(engine)["league_ids_json"])      # the league pass misses it
    token = job(engine)["token"]
    assert scrub.run_pending() == 1
    row, f = card(engine, "left-0")
    assert f["partner_user_id"] == token and "likes_you" not in f and row["base_score"] is None
    (cs,) = read(engine, db.deck_candidate_sets_table, candidate_set_id="cs-left")
    assert json.loads(cs["candidates_json"])[0]["partner"] == token
    assert job(engine)["scan_json"] is None


def test_the_scan_is_bounded_per_run_and_resumes_from_its_cursor(engine, monkeypatch):
    seed_left_league(engine)
    monkeypatch.setattr(scrub, "_SCAN_BATCH", 1)
    monkeypatch.setattr(scrub, "_SCAN_PAGES_PER_RUN", 2)
    accounts.delete_user_data(DEL)
    runs = 0
    while not scrub.run_pending():
        runs += 1
        state = json.loads(job(engine)["scan_json"])
        # Kept (at a cursor, or at the start of the next store), lease released.
        assert state["version"] == scrub.SCRUB_VERSION and "after" in state
        assert job(engine)["claimed_until"] is None
        assert runs < 20
    # 5 impressions + 3 candidate sets, one row a page, two pages a run (and
    # an empty page closes each store).
    assert runs >= 3
    assert card(engine, "left-0")[1]["partner_user_id"] == job(engine)["token"]
    assert job(engine)["scan_json"] is None


# ── Lease, retry, grace, logs ───────────────────────────────────────────────

def test_two_runners_never_claim_one_job(engine):
    accounts.delete_user_data(DEL)
    now = datetime.now(timezone.utc)
    stale = job(engine)                      # both runners read the row before either claims
    assert scrub._take(stale, now) is not None and scrub._take(stale, now) is None
    assert scrub._claim_one(now, set()) is None                             # held
    assert scrub._claim_one(now + scrub.LEASE + timedelta(seconds=1), set()) is not None


def test_a_failed_pass_records_the_class_only_and_is_retried(engine, monkeypatch, caplog):
    accounts.delete_user_data(DEL)

    def boom(job):
        raise ValueError(f"synthetic, quoting {DEL}")
    monkeypatch.setattr(scrub, "_STORES", (("boom", boom),))
    caplog.set_level(logging.INFO, logger="trade_finder")
    assert scrub.run_pending() == 0
    row = job(engine)
    assert (row["last_error"], row["claimed_until"], row["db_version"]) == ("ValueError", None, 0)
    monkeypatch.undo()
    monkeypatch.setattr(db, "engine", engine)
    assert scrub.run_pending() == 1 and job(engine)["db_version"] == scrub.SCRUB_VERSION
    assert not any(DEL in r.getMessage() or ALIAS in r.getMessage() for r in caplog.records)


def test_the_grace_pass_scrubs_a_row_an_in_flight_deck_wrote_later(engine):
    token = delete_and_scrub(engine)
    deleted = datetime.fromisoformat(job(engine)["deleted_at"])
    with engine.begin() as conn:                    # its first delivery, after the deletion
        impression(conn, "c-late-write-9", DEL, served_at=(deleted + timedelta(hours=1)).isoformat())
    assert scrub.run_pending(deleted + timedelta(hours=2)) == 0            # not due yet
    assert scrub.run_pending(deleted + scrub.IN_FLIGHT_GRACE) == 1
    assert card(engine, "c-late-write-9")[1]["partner_user_id"] == token
    assert scrub.run_pending(deleted + scrub.IN_FLIGHT_GRACE + timedelta(hours=1)) == 0


# ── The daily-tick step ─────────────────────────────────────────────────────

def test_the_step_runs_right_before_the_refit():
    import backend.server as server
    keys = [s.key for s in server._daily_tick_steps()]
    assert keys.index("deletion_scrub") == keys.index("value_model_refit") - 1


def test_the_tick_redacts_the_model_store_once_the_db_pass_is_current(engine, monkeypatch):
    from backend.eval import redaction
    calls = []
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: calls.append(tokens) or 2)
    token = delete_and_scrub(engine)
    outcome, detail = scrub.tick(datetime.now(timezone.utc))
    assert outcome == "ok" and detail["model_changed"] == 2
    assert calls == [{pid: token for pid in json.loads(job(engine)["partner_ids_json"])}]
    assert job(engine)["model_done_at"] is not None
    scrub.tick(datetime.now(timezone.utc))
    assert len(calls) == 1                          # done once


def test_a_model_store_raise_keeps_the_job_for_the_next_tick(engine, monkeypatch):
    from backend.eval import redaction

    def busy(tokens):
        raise RuntimeError("the store kept changing")
    monkeypatch.setattr(redaction, "redact_model_store", busy)
    delete_and_scrub(engine)
    outcome, detail = scrub.tick(datetime.now(timezone.utc))
    assert (outcome, detail["model_error"]) == ("error", "RuntimeError")
    row = job(engine)
    assert (row["model_done_at"], row["last_error"]) == (None, "RuntimeError")


def test_a_finished_job_is_deleted_only_once_every_stage_is_built(engine, monkeypatch):
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    delete_and_scrub(engine)
    deleted = datetime.fromisoformat(job(engine)["deleted_at"])
    scrub.tick(deleted + timedelta(hours=1))
    assert job(engine)["model_done_at"] is not None          # kept: the grace pass hasn't run
    monkeypatch.setattr(scrub, "COMPLETE", False)
    later = deleted + scrub.IN_FLIGHT_GRACE
    scrub.tick(later)
    assert job(engine)["db_done_at"] >= later.isoformat()    # kept: a stage still unbuilt
    monkeypatch.setattr(scrub, "COMPLETE", True)
    assert scrub.tick(later)[1]["finished"] == 1
    assert read(engine, db.deletion_scrub_jobs_table) == []


def test_unfinished_past_24h_is_counted_at_error_without_ids(engine, monkeypatch, caplog):
    from backend.eval import redaction

    def busy(tokens):                         # the model store keeps the job unfinished
        raise RuntimeError("the store kept changing")
    monkeypatch.setattr(redaction, "redact_model_store", busy)
    accounts.delete_user_data(DEL)
    deleted = datetime.fromisoformat(job(engine)["deleted_at"])
    caplog.set_level(logging.INFO, logger="trade_finder")
    outcome, detail = scrub.tick(deleted + timedelta(hours=30))
    assert detail["unfinished_24h"] == 1
    alerts = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.getMessage() for r in alerts] == ["[scrub] unfinished jobs=1 oldest_h=30"]
    assert not any(DEL in r.getMessage() or ALIAS in r.getMessage() for r in caplog.records)


def test_the_tick_never_raises_an_errors_text(engine, monkeypatch):
    monkeypatch.setattr(scrub, "_db_pass", lambda now: (_ for _ in ()).throw(
        RuntimeError(f"quoting {DEL}")))
    assert scrub.tick(datetime.now(timezone.utc)) == ("error", {"error": "RuntimeError"})


def test_the_route_kicks_the_scrub_off_the_request_and_tests_never_start_the_thread(
        engine, monkeypatch):
    """kick() starts the DB phase on a daemon thread; the suite disables it
    (conftest), since a thread would outlive a test's engine."""
    import threading
    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self.name))
    scrub.kick()
    assert started == []                                   # disabled in the suite
    monkeypatch.setenv("FTF_DISABLE_DELETION_SCRUB_KICK", "0")
    scrub.kick()
    assert started == ["deletion-scrub"]


# ── #557 QA: the lease, one job per claim, poison rows, a version bump ─────

def test_a_run_that_outlasted_its_lease_writes_nothing(engine):
    """#557 QA P2: another runner took the job over (this run's lease ran
    out); every write of the stale run is a CAS on its lease, so it writes
    no scan cursor, no done mark, nothing."""
    accounts.delete_user_data(DEL)
    now = datetime.now(timezone.utc)
    held = scrub._claim_one(now, set())
    with engine.begin() as conn:             # the other runner's lease
        conn.execute(db.deletion_scrub_jobs_table.update().values(claimed_until="9999-01-01"))
    assert scrub._run_db(held, now) is False
    row = job(engine)
    assert (row["claimed_until"], row["scan_json"], row["db_version"], row["db_done_at"]) == (
        "9999-01-01", None, 0, None)


def test_each_claim_takes_one_job(engine):
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="second-person"))
    accounts.delete_user_data(DEL)
    accounts.delete_user_data("second-person")
    now = datetime.now(timezone.utc)
    first = scrub._claim_one(now, set())
    held = [r for r in read(engine, db.deletion_scrub_jobs_table) if r["claimed_until"]]
    assert [r["job_id"] for r in held] == [first["job_id"]]                 # the other waits
    assert scrub.run_pending(now + scrub.LEASE + timedelta(seconds=1)) == 2


def test_a_poison_row_is_counted_and_the_pass_retried_later(engine, monkeypatch):
    """#557 QA P3: a row whose redaction raises doesn't stop the others; the
    pass isn't done, and it runs again after the backoff, not every tick."""
    real = scrub.redact_features

    def poison(features, ids, token):
        if features.get("receive_value") == 101.0:
            raise ValueError("synthetic poison")
        return real(features, ids, token)
    with engine.begin() as conn:
        from backend.tests.test_deletion_scrub import impression as _imp  # noqa: F401
        impression(conn, "c-poison-5", DEL, features=features_for(DEL, receive_value=101.0))
    monkeypatch.setattr(scrub, "redact_features", poison)
    accounts.delete_user_data(DEL)
    now = datetime.now(timezone.utc)
    assert scrub.run_pending(now) == 0
    row = job(engine)
    assert (row["last_error"], row["db_version"], row["scan_json"]) == ("row_failures", 0, None)
    assert row["claimed_until"] > (now + timedelta(minutes=30)).isoformat()   # the backoff
    assert card(engine, "c-del-1")[1]["partner_user_id"] == row["token"]     # the rest done


def test_a_version_bump_runs_the_model_store_again(engine, monkeypatch):
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    delete_and_scrub(engine)
    scrub.tick(datetime.now(timezone.utc))
    assert job(engine)["model_done_at"] is not None
    monkeypatch.setattr(scrub, "SCRUB_VERSION", scrub.SCRUB_VERSION + 1)
    scrub.run_pending()
    assert job(engine)["model_done_at"] is None


# ── #557 QA P1s ─────────────────────────────────────────────────────────────

BILATERAL = {"generator": "owner_v2_bilateral", "market": {"give": 1.0},
             "construction": {"partner": DEL},       # an id in a kept field
             "viewer": {"support": {"score": 0.6}},
             "counterparty": {"support": {"score": 0.7}},
             "bilateral": {"weaker_support": 0.6, "total_support": 1.3, "preference_fulfillment": 0.2},
             "term_efficiency": {"useful_companions": [{"asset_id": "p", "recipient": DEL,
                                                        "benefits": ["personal_preference"]}],
                                 "comparisons": [{"asset_id": "p", "recipient": DEL}]},
             "assets": [{"id": "p", "market": 5.0, "viewer_preference": {"tier": 1},
                         "counterparty_preference": {"tier": 2, "source": "explicit"}}]}


def test_the_bilateral_valuation_loses_the_partners_fields_and_the_id(engine):
    """#557 QA P1-1: owner_v2_bilateral's valuation keeps the raw id in
    term_efficiency's recipients, the partner's preference per asset, and
    bilateral scores that sum or min both sides (the viewer's kept, so they
    solve back)."""
    with engine.begin() as conn:
        impression(conn, "c-bilateral-6", DEL, valuation=BILATERAL)
    token = delete_and_scrub(engine)
    row, _f = card(engine, "c-bilateral-6")
    v = json.loads(row["valuation_json"])
    assert v == {"generator": "owner_v2_bilateral", "market": {"give": 1.0},
                 "construction": {"partner": token},
                 "viewer": {"support": {"score": 0.6}},
                 "assets": [{"id": "p", "market": 5.0, "viewer_preference": {"tier": 1}}]}
    assert DEL not in row["valuation_json"]


def test_an_owner_selected_runs_top_level_input_and_its_arms_are_scrubbed(engine):
    """#557 QA P1-2 and P1-3: owner-selected runs (fair packages, asset ideas)
    keep the frozen input at the top level of config_json; every run's arms,
    agreement and groups name members by id, and an owner arm's pools are the
    person's preference-ordered assets."""
    with engine.begin() as conn:
        conn.execute(insert(db.bakeoff_runs_table).values(
            run_id="run-owner", deck_job_id="deck-1", user_id=VIEWER, league_id=LEAGUE,
            arm_order="[]", deck_size=1, created_at=EARLY,
            config_json=json.dumps({"input": OWNER_INPUT, "unit": "owner_only"}),
            arms_json=json.dumps({"owner": {"diagnostics": {
                "per_opponent": {DEL: {"evaluated": 3}, OTHER: {"evaluated": 2}},
                "pools": {DEL: {"give": ["a"], "receive": ["b"]}, OTHER: {"give": ["c"]}}}}}),
            agreement_json=json.dumps({"by_partner": {DEL: 1}}),
            groups_json=json.dumps([{"partner": DEL}])))
    token = delete_and_scrub(engine)
    (row,) = read(engine, db.bakeoff_runs_table, run_id="run-owner")
    inputs = json.loads(row["config_json"])["input"]
    assert inputs["members"][0] == {"id": token}
    assert inputs["manager_preferences"] == {VIEWER: {"t": 1}, OTHER: {"t": 3}}
    assert inputs["opponent_outlooks"] == {OTHER: "contend"}
    diag = json.loads(row["arms_json"])["owner"]["diagnostics"]
    assert diag["pools"] == {OTHER: {"give": ["c"]}}
    assert diag["per_opponent"] == {token: {"evaluated": 3}, OTHER: {"evaluated": 2}}
    assert json.loads(row["agreement_json"]) == {"by_partner": {token: 1}}
    assert json.loads(row["groups_json"]) == [{"partner": token}]
    assert not any(DEL in (row[c] or "") for c in ("config_json", "arms_json", "agreement_json",
                                                   "groups_json"))


def test_the_cleanup_step_kick_and_its_thread_log_the_class_only(engine, monkeypatch, caplog):
    """#557 QA P3: the cleanup loop's step, the route's start and the kicked
    thread each catch a raise and log its class, never its text (a DB error
    quotes its parameters)."""
    import threading
    import backend.server as server
    caplog.set_level(logging.INFO, logger="trade_finder")
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"quoting {DEL}"))  # noqa: E731
    monkeypatch.setattr(scrub, "run_pending", boom)
    server._cleanup_deletion_scrub()                      # the cleanup loop's step
    monkeypatch.setenv("FTF_DISABLE_DELETION_SCRUB_KICK", "0")
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    scrub.kick()                                          # the kicked thread's catch
    monkeypatch.setattr(scrub, "kick", boom)
    server._kick_deletion_scrub()                         # the route's catch
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert messages == ["deletion scrub pass failed: RuntimeError",
                        "[scrub] kicked pass failed: RuntimeError",
                        "deletion scrub start failed: RuntimeError"]
    assert not any(DEL in r.getMessage() for r in caplog.records)


# ── #557 re-QA notes ────────────────────────────────────────────────────────

def test_a_run_whose_lease_was_taken_before_its_done_write_writes_nothing(engine, monkeypatch):
    """#557 re-QA QA7: the lease is lost after the run's last renew; the done
    write is a CAS on it too, so it marks nothing done."""
    accounts.delete_user_data(DEL)
    now = datetime.now(timezone.utc)
    held = scrub._claim_one(now, set())
    monkeypatch.setattr(scrub._Lease, "renew", lambda self: None)   # the run never notices
    with engine.begin() as conn:
        conn.execute(db.deletion_scrub_jobs_table.update().values(claimed_until="9999-01-01"))
    assert scrub._run_db(held, now) is False
    row = job(engine)
    assert (row["db_version"], row["db_done_at"], row["claimed_until"]) == (0, None, "9999-01-01")


def test_a_permanent_poison_row_counts_once_per_pass_and_never_blocks_the_model_store(
        engine, monkeypatch, caplog):
    from backend.eval import redaction
    calls = []
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: calls.append(tokens) or 0)
    real = scrub.redact_features

    def poison(features, ids, token):
        if features.get("receive_value") == 101.0:
            raise ValueError("synthetic poison")
        return real(features, ids, token)
    with engine.begin() as conn:
        impression(conn, "c-poison-5", DEL, features=features_for(DEL, receive_value=101.0))
    monkeypatch.setattr(scrub, "redact_features", poison)
    accounts.delete_user_data(DEL)
    caplog.set_level(logging.INFO, logger="trade_finder")
    now = datetime.now(timezone.utc)
    scrub.run_pending(now)
    # One poison row, hit by the league pass and by the scan: 2 failed
    # redactions, counted once each.
    assert any("had 2 failed row redactions" in r.getMessage() for r in caplog.records)
    assert job(engine)["last_error"] == "row_failures"
    scrub.tick(now)
    assert len(calls) == 1 and job(engine)["model_done_at"] is not None


def test_bakeoff_batches_by_count_and_by_bytes_each_renewing_the_lease(engine, monkeypatch):
    """#557 re-QA P2-2: a page of megabyte bakeoff rows is read in batches
    capped by bytes as well as rows, and every batch renews the lease."""
    with engine.begin() as conn:
        for run_id, size in (("r1", 10), ("r2", 10), ("r3", 100), ("r4", 10)):
            conn.execute(insert(db.bakeoff_runs_table).values(
                run_id=run_id, deck_job_id="d", user_id=VIEWER, league_id=LEAGUE, arm_order="[]",
                deck_size=1, arms_json="{}", created_at=EARLY,
                config_json=json.dumps({"partner": DEL, "pad": "x" * size})))
    # ~52 bytes a small row, ~142 the big one: two small rows fit, the big
    # one is a batch of its own.
    monkeypatch.setattr(scrub, "_BAKEOFF_BATCH_BYTES", 120)
    with engine.connect() as conn:
        assert scrub._bakeoff_batches(conn, ["r1", "r2", "r3", "r4"]) == [["r1", "r2"], ["r3"], ["r4"]]
    renewed = []

    class Lease:
        def renew(self):
            renewed.append(1)
    n = scrub._redact_bakeoff_runs(["r1", "r2", "r3", "r4"],
                                   {"ids": [DEL], "token": "redacted:t", "lease": Lease(), "job_id": "j"})
    assert n == 4 and len(renewed) == 3



def test_bakeoff_batches_count_stored_bytes_not_characters(engine, monkeypatch):
    """The byte cap reads octet_length, the stored size (#557 re-QA notes).
    Two rows of three-byte characters: about 40 characters but 100 bytes each,
    so each is a batch of its own under a 120-byte cap, where length() would
    count characters and put them together. Needs SQLite 3.43 or later
    (living-memory/DEPENDENCIES.md)."""
    with engine.begin() as conn:
        for run_id in ("m1", "m2"):
            conn.execute(insert(db.bakeoff_runs_table).values(
                run_id=run_id, deck_job_id="d", user_id=VIEWER, league_id=LEAGUE, arm_order="[]",
                deck_size=1, arms_json="{}", created_at=EARLY,
                config_json=json.dumps({"pad": "\u20ac" * 30}, ensure_ascii=False)))
    monkeypatch.setattr(scrub, "_BAKEOFF_BATCH_BYTES", 120)
    with engine.connect() as conn:
        assert scrub._bakeoff_batches(conn, ["m1", "m2"]) == [["m1"], ["m2"]]

def test_every_impressions_batch_renews_the_lease(engine, monkeypatch):
    """#557 re-QA P3: the rows are redacted in batches, each renewing the
    job's lease, so a long league pass can't outlast it."""
    monkeypatch.setattr(scrub, "_BATCH", 1)
    renewed = []

    class Lease:
        def renew(self):
            renewed.append(1)
    ids = ["c-del-0", "c-del-1", "c-other-2"]
    scrub._redact_impressions(ids, {"ids": [DEL], "token": "redacted:t", "lease": Lease(),
                                    "job_id": "j"})
    assert len(renewed) == len(ids)
