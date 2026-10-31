"""The deletion scrub, stage 3 (legal R28.22 f's trace, c3 #7 and #13; scope
§0.2): the person's names captured at deletion; the narrative on a redacted
page card; value_core's blended scores; other users' Calibration cards; overdue
diagnostics; the boot migration for the names column. Harness:
test_deletion_scrub's engine and seed."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, insert, inspect as sa_inspect, select, text, update

from backend import accounts, database as db, deletion_scrub as scrub
from backend.tests.test_deletion_scrub import (  # noqa: F401  (fixture)
    DEL, EARLY, LEAGUE, OTHER, VIEWER, engine, job, read)

PLACEHOLDER = accounts.DELETED_USER_PLACEHOLDER


def name_people(engine):
    with engine.begin() as conn:
        m = db.league_members_table
        conn.execute(update(m).where(m.c.user_id == DEL).values(display_name="Del Name",
                                                                  username="deluser"))
        conn.execute(update(m).where(m.c.user_id == OTHER).values(display_name="Other Name"))


def test_the_persons_names_per_league_are_captured_at_deletion(engine):
    name_people(engine)
    accounts.delete_user_data(DEL)
    assert json.loads(job(engine)["partner_names_json"]) == {
        "leagues": {LEAGUE: ["Del Name", "deluser"]}, "usernames": ["deluser"]}


def test_a_redacted_page_card_loses_its_narrative():
    card = {"target_user_id": DEL, "target_username": "n", "narrative": "They're rebuilding."}
    assert "narrative" not in scrub.redact_page_card(card, {DEL}, "redacted:t")
    other = {"target_user_id": OTHER, "narrative": "Fair on value."}
    assert scrub.redact_page_card(other, {DEL}, "redacted:t") == other


def test_value_cores_blended_scores_go_and_value_and_rank_stay():
    """outlook = (viewer + partner) / 2 with the viewer's side kept, and
    priority and effective are built from it: each solves back the partner's
    outlook (scope §1.3)."""
    evidence = {"scores": {"value": 0.6, "outlook": 0.7, "rank": 0.5, "priority": 0.62},
                "effective": 0.61, "detail": {"outlook": {"viewer": {"score": 0.8},
                                                          "partner": {"score": 0.6}}},
                "windows": {"viewer": "contender", "partner": "rebuilder"}}
    assert scrub.redact_valuation(evidence) == {
        "scores": {"value": 0.6, "rank": 0.5}, "detail": {"outlook": {"viewer": {"score": 0.8}}},
        "windows": {"viewer": "contender"}}


# ── Calibration ─────────────────────────────────────────────────────────────

def session(conn, session_id, league, cards):
    source = {"version": 1, "seat": VIEWER, "current": {"cards": [
        {"partner_id": DEL, "give": ["a"], "receive": ["b"], "provenance": {"impression_id": "i0"}},
        {"partner_id": OTHER, "give": ["c"], "receive": ["d"], "provenance": {}}]}}
    conn.execute(insert(db.grading_sessions_table).values(
        session_id=session_id, user_id=VIEWER, league_id=league, status="completed",
        seed="1", created_at=EARLY, counts_json="{}", source_json=json.dumps(source)))
    for pos, (name, give, receive) in enumerate(cards, 1):
        conn.execute(insert(db.grading_cards_table).values(
            card_id=f"{session_id}-{pos}", session_id=session_id, user_id=VIEWER, position=pos,
            arms_json=json.dumps({"current": {"partner": DEL}} if give == "a" else {"value_core": {}}),
            trade_json=json.dumps({"partner_name": name, "give": [{"id": give}],
                                   "receive": [{"id": receive}]}), grade=5))


def names_on_cards(engine, session_id):
    with engine.connect() as conn:
        rows = conn.execute(select(db.grading_cards_table.c.card_id, db.grading_cards_table.c.trade_json)
                            .where(db.grading_cards_table.c.session_id == session_id)
                            .order_by(db.grading_cards_table.c.position)).all()
    return [json.loads(t)["partner_name"] for _id, t in rows]


def test_other_users_calibration_cards_naming_the_person_take_the_placeholder(engine):
    name_people(engine)
    with engine.begin() as conn:
        session(conn, "s1", LEAGUE, [("Del Name", "a", "b"),        # the current arm, by provenance
                                     ("Del Name", "e", "f"),        # a value-core card, by name
                                     ("Other Name", "c", "d")])     # another partner's
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    assert names_on_cards(engine, "s1") == [PLACEHOLDER, PLACEHOLDER, "Other Name"]
    (row,) = read(engine, db.grading_sessions_table, session_id="s1")
    assert DEL not in row["source_json"] and job(engine)["token"] in row["source_json"]
    (card,) = read(engine, db.grading_cards_table, card_id="s1-1")
    assert DEL not in card["arms_json"] and card["grade"] == 5          # grades are kept


def test_a_session_in_a_league_the_person_left_is_found_by_its_source(engine):
    """The fallback scan finds the session. The current arm's provenance
    finds their card, and since the source shows they were a partner there,
    a value-core card naming them by any of their names goes too."""
    name_people(engine)
    with engine.begin() as conn:
        session(conn, "s-left", "league-left", [("Del Name", "a", "b"), ("Del Name", "e", "f"),
                                                ("Other Name", "c", "d")])
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    assert names_on_cards(engine, "s-left") == [PLACEHOLDER, PLACEHOLDER, "Other Name"]


# ── Diagnostics ─────────────────────────────────────────────────────────────

def test_an_overdue_diagnostic_naming_the_person_is_deleted(engine):
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for sid, days, who in (("old-del", 40, DEL), ("new-del", 10, DEL), ("old-other", 40, OTHER)):
            conn.execute(insert(db.deck_diagnostic_snapshots_table).values(
                snapshot_id=sid, user_id=VIEWER, deck_job_id="deck-1",
                created_at=(now - timedelta(days=days)).isoformat(),
                payload_json=json.dumps({"card": {"partner": who}})))
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    assert sorted(r["snapshot_id"] for r in read(engine, db.deck_diagnostic_snapshots_table)) == [
        "new-del", "old-other"]          # the 14-day purge takes the newer one within 30 days


# ── The lifecycle, complete ─────────────────────────────────────────────────

def test_a_job_is_deleted_once_its_grace_pass_and_the_model_store_are_done(engine, monkeypatch):
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    accounts.delete_user_data(DEL)
    deleted = datetime.fromisoformat(job(engine)["deleted_at"])
    scrub.run_pending(deleted)
    assert scrub.tick(deleted + timedelta(hours=1))[1]["finished"] == 0   # the grace pass is due
    assert scrub.tick(deleted + scrub.IN_FLIGHT_GRACE)[1]["finished"] == 1
    assert read(engine, db.deletion_scrub_jobs_table) == []


def test_boot_adds_the_names_column_to_an_existing_jobs_table(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'scrub.db'}"
    eng = create_engine(url)
    db.metadata.create_all(eng)
    with eng.begin() as conn:                    # stage 1's table, without the column
        conn.execute(text("DROP TABLE deletion_scrub_jobs"))
        conn.execute(text("CREATE TABLE deletion_scrub_jobs (job_id VARCHAR PRIMARY KEY, "
                          "token VARCHAR NOT NULL, partner_ids_json TEXT NOT NULL, "
                          "league_ids_json TEXT NOT NULL, deleted_at VARCHAR NOT NULL, "
                          "db_version INTEGER NOT NULL DEFAULT 0, db_done_at VARCHAR, "
                          "model_done_at VARCHAR, attempts INTEGER NOT NULL DEFAULT 0, "
                          "claimed_until VARCHAR, last_error VARCHAR, scan_json TEXT)"))
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    db.init_db()
    assert "partner_names_json" in {c["name"] for c in sa_inspect(eng).get_columns("deletion_scrub_jobs")}
    eng.dispose()


# ── J2: E-b2 item 5, identical in every store ──────────

def test_item_5_applies_identically_in_rows_packs_and_the_page_store():
    """models-lead addendum J2 (G-a1's uniformity): on a redacted card the
    blended scores go the same way wherever the card is stored: base_score,
    final_score and surplus_margin null; fit.aggregate removed; value_core's
    outlook, priority and effective removed."""
    from backend.tests.test_deletion_scrub import features_for
    token, ids = "redacted:t", {DEL}
    valuation = {"scores": {"value": 0.6, "outlook": 0.7, "rank": 0.5, "priority": 0.62},
                 "effective": 0.61, "market": {"give": 1.0}}
    features = features_for(DEL, fit={"you": 60.0, "them": 70.0, "aggregate": 130.0})
    row = {"base_score": 150.0, "final_score": 160.0, "source_like_impression_id": None,
           "features_json": json.dumps(features), "valuation_json": json.dumps(valuation)}

    def item_5_holds(r):
        f = json.loads(r["features_json"])
        v = json.loads(r["valuation_json"])
        assert (r["base_score"], r["final_score"], f["surplus_margin"]) == (None, None, None)
        assert "aggregate" not in f["fit"] and f["fit"]["you"] == 60.0
        assert v["scores"] == {"value": 0.6, "rank": 0.5} and "effective" not in v
    item_5_holds(scrub.redact_row(row, ids, token))                       # deck_impressions
    blob = scrub.redact_evidence_blob({"rows": [{**row, "impression_id": "d:0", "trade_hash": "h"}]},
                                      ids, token)
    item_5_holds(blob["rows"][0])                                         # the page store's evidence
    packed = scrub.redact_packed_card({"partner_user_id": DEL, "base_score": 150.0,
                                       "final_score": 160.0, "surplus_margin": 42.0}, ids, token)
    assert (packed["base_score"], packed["final_score"], packed["surplus_margin"]) == (None, None, None)
    page = scrub.redact_page_card({"target_user_id": DEL, "composite_score": 150.0,
                                   "mismatch_score": 42.0, "fit": {"aggregate": 130.0}}, ids, token)
    assert (page["composite_score"], page["mismatch_score"]) == (None, None) and "fit" not in page


def notification(conn, title, meta, user=VIEWER):
    conn.execute(insert(db.notifications_table).values(
        user_id=user, type="trade_match", title=title, body="CeeDee Lamb for Tyreek Hill",
        metadata_json=json.dumps(meta), created_at=EARLY))


def test_notifications_naming_the_person_take_the_placeholder_and_the_token(engine):
    """A match / disposition notification names its partner by username
    (unique) in its title and metadata: it takes the placeholder there, and
    any id in its metadata the token. A display name is never matched: it
    could be someone else's username."""
    name_people(engine)
    with engine.begin() as conn:
        notification(conn, "Trade match with @deluser", {"partner_username": "deluser", "match_id": 1})
        notification(conn, "@deluser accepted your trade", {"partner_username": "deluser"})
        notification(conn, "Trade match with @otheruser", {"partner_username": "otheruser"})
        notification(conn, "Trade match with @Del Name", {"partner_username": "Del Name"})  # another person
        notification(conn, "Counter offer", {"partner_user_id": DEL})
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    rows = {r["id"]: r for r in read(engine, db.notifications_table)}
    got = [(r["title"], json.loads(r["metadata_json"])) for _id, r in sorted(rows.items())]
    assert got == [
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER, "match_id": 1}),
        (f"@{PLACEHOLDER} accepted your trade", {"partner_username": PLACEHOLDER}),
        ("Trade match with @otheruser", {"partner_username": "otheruser"}),
        ("Trade match with @Del Name", {"partner_username": "Del Name"}),
        ("Counter offer", {"partner_user_id": token}),
    ]


def test_other_users_events_naming_the_person_take_the_token(engine):
    with engine.begin() as conn:
        for props in ({"partner_user_id": DEL, "surface": "deck"}, {"partner_user_id": OTHER}):
            conn.execute(insert(db.user_events_table).values(
                user_id=VIEWER, event_type="trade_matched", occurred_at=EARLY, props=json.dumps(props)))
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    props = [json.loads(r["props"]) for r in read(engine, db.user_events_table)]
    assert props == [{"partner_user_id": token, "surface": "deck"}, {"partner_user_id": OTHER}]
