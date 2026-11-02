"""The deletion scrub, stage 3 (legal R28.22 f's trace, c3 #7 and #13; scope
§0.2): the person's names captured at deletion; the narrative on a redacted
page card; value_core's blended scores; other users' Calibration cards; overdue
diagnostics; the boot migration for the names column. Harness:
test_deletion_scrub's engine and seed."""
import json
import logging
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
    """Their names, and their trade matches, read before the deletion puts the
    placeholder on their side."""
    name_people(engine)
    mt = db.trade_matches_table
    with engine.connect() as conn:
        mine = sorted(conn.execute(select(mt.c.id).where(
            (mt.c.user_a_id == DEL) | (mt.c.user_b_id == DEL))).scalars())
    accounts.delete_user_data(DEL)
    assert json.loads(job(engine)["partner_names_json"]) == {
        "leagues": {LEAGUE: ["Del Name", "deluser"]}, "usernames": ["deluser"], "match_ids": mine}


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
        for sid, days, who in (("old-del", 40, DEL), ("past-del", 20, DEL), ("new-del", 10, DEL),
                               ("old-other", 40, OTHER)):
            conn.execute(insert(db.deck_diagnostic_snapshots_table).values(
                snapshot_id=sid, user_id=VIEWER, deck_job_id="deck-1",
                created_at=(now - timedelta(days=days)).isoformat(),
                payload_json=json.dumps({"card": {"partner": who}})))
    accounts.delete_user_data(DEL)
    scrub.run_pending()
    assert sorted(r["snapshot_id"] for r in read(engine, db.deck_diagnostic_snapshots_table)) == [
        "new-del", "old-other"]          # past the 14-day retention goes; the purge takes the newer one


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
    """A match / disposition notification names its partner in its title and
    metadata: by username (unique, matched anywhere); by display name (the
    second liker's copy, #562 QA P2-2), matched only for a recipient who shared
    a league with the person, since a display name could be someone else's; or
    by a raw id when they had neither. That name, and any "@<id>", take the
    placeholder, and any id in the metadata the token."""
    name_people(engine)
    with engine.begin() as conn:
        u = db.users_table
        conn.execute(update(u).where(u.c.sleeper_user_id == DEL).values(username="renée"))
        notification(conn, "Trade match with @deluser", {"partner_username": "deluser", "match_id": 1})
        notification(conn, "@deluser accepted your trade", {"partner_username": "deluser"})
        notification(conn, "Trade match with @otheruser", {"partner_username": "otheruser"})
        notification(conn, "Trade match with @Del Name", {"partner_username": "Del Name"})  # a leaguemate's copy
        notification(conn, "Counter offer", {"partner_user_id": DEL})
        notification(conn, f"Trade match with @{DEL}", {"partner_username": DEL})       # no names at all
        notification(conn, "Trade match with @renée", {"partner_username": "renée"},
                     user="faraway")      # stored as \u escapes; no match, so only that term finds it
        notification(conn, "Trade match with @Del Name", {"partner_username": "Del Name"},
                     user="stranger")                                                   # shares no league
        notification(conn, f"@{DEL} countered your offer", {"partner_user_id": DEL})   # the id, no name
        # Match notifications: the match row says who the partner is (re-QA P3).
        mt = db.trade_matches_table
        conn.execute(update(db.league_members_table).where(
            db.league_members_table.c.user_id == OTHER).values(display_name="deluser"))
        conn.execute(insert(mt), [
            {"id": 7, "league_id": LEAGUE, "user_a_id": VIEWER, "user_b_id": OTHER,
             "user_a_give": "[]", "user_a_receive": "[]", "status": "pending"},
            {"id": 8, "league_id": "league-left", "user_a_id": "stranger", "user_b_id": DEL,
             "user_a_give": "[]", "user_a_receive": "[]", "status": "pending"}])
        notification(conn, "Trade match with @deluser", {"partner_username": "deluser", "match_id": 7})
        notification(conn, "Trade match with @Del Name", {"partner_username": "Del Name", "match_id": 8},
                     user="stranger")
        # A name never captured (or since changed) on one of their matches; and
        # one of their matches named on a notification to someone not on it.
        conn.execute(insert(mt).values(id=9, league_id="league-left", user_a_id=DEL, user_b_id=VIEWER,
                                       user_a_give="[]", user_a_receive="[]", status="pending"))
        notification(conn, "Trade match with @KimFive", {"partner_username": "KimFive", "match_id": 9})
        notification(conn, "Trade match with @KimFive", {"partner_username": "KimFive", "match_id": 9},
                     user="stranger")
    accounts.delete_user_data(DEL)
    token = job(engine)["token"]
    scrub.run_pending()
    rows = {r["id"]: r for r in read(engine, db.notifications_table)}
    got = [(r["title"], json.loads(r["metadata_json"])) for _id, r in sorted(rows.items())]
    assert got == [
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER, "match_id": 1}),
        (f"@{PLACEHOLDER} accepted your trade", {"partner_username": PLACEHOLDER}),
        ("Trade match with @otheruser", {"partner_username": "otheruser"}),
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER}),
        ("Counter offer", {"partner_user_id": token}),
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER}),
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER}),
        ("Trade match with @Del Name", {"partner_username": "Del Name"}),
        (f"@{PLACEHOLDER} countered your offer", {"partner_user_id": token}),
        ("Trade match with @deluser", {"partner_username": "deluser", "match_id": 7}),   # OTHER's
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER, "match_id": 8}),
        (f"Trade match with @{PLACEHOLDER}", {"partner_username": PLACEHOLDER, "match_id": 9}),
        ("Trade match with @KimFive", {"partner_username": "KimFive", "match_id": 9}),   # not a side
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



def _stuck_pair(engine, now):
    """Two deletions, both unfinished and held by another runner (as a poison
    row leaves a job unfinished for good): one 31 days old, one 29."""
    accounts.delete_user_data(DEL)
    t = db.deletion_scrub_jobs_table
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="second-person"))
    accounts.delete_user_data("second-person")
    with engine.begin() as conn:
        rows = conn.execute(select(t.c.job_id).order_by(t.c.job_id)).scalars().all()
        old, young = sorted(rows)
        conn.execute(update(t).where(t.c.job_id == old).values(
            deleted_at=(now - timedelta(days=31)).isoformat(), last_error="row_failures",
            claimed_until="9999-01-01"))
        conn.execute(update(t).where(t.c.job_id == young).values(
            deleted_at=(now - timedelta(days=29)).isoformat(), last_error="row_failures",
            claimed_until="9999-01-01"))
    return old, young


def test_a_job_unfinished_after_30_days_is_kept_escalated_and_alerted_daily(engine, caplog, monkeypatch):
    """Legal R28.26 #8 (R28.20 (ix)): a job is never dropped unfinished, because
    its row is the only way to find a poison row that still names the person.
    Past 30 days it's kept, stamped `escalated_at` once, and every tick logs it
    at ERROR by its own job id, age, where it stands and its error class, never
    the person's ids. A younger unfinished job isn't escalated."""
    now = datetime.now(timezone.utc)
    old, young = _stuck_pair(engine, now)
    t = db.deletion_scrub_jobs_table
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    caplog.set_level(logging.ERROR, logger="trade_finder")
    _, detail = scrub.tick(now)                   # the daily tick's step
    assert detail["escalated"] == 1
    with engine.connect() as conn:
        rows = {r.job_id: r for r in conn.execute(select(t)).all()}
    assert set(rows) == {old, young}              # nothing deleted
    assert rows[old].escalated_at == now.isoformat()
    assert rows[young].escalated_at is None
    lines = [r.getMessage() for r in caplog.records if "escalated" in r.getMessage()]
    assert lines == [f"[scrub] escalated job={old[:8]} days=31 stuck_at=db_pass last_error=row_failures"]
    assert DEL not in caplog.text and "second-person" not in caplog.text
    assert "abandoned" not in caplog.text

    # The next day: alerted again, the first stamp kept.
    caplog.clear()
    _, detail = scrub.tick(now + timedelta(days=1))
    assert detail["escalated"] == 1
    with engine.connect() as conn:
        assert conn.execute(select(t.c.escalated_at).where(t.c.job_id == old)).scalar() == now.isoformat()
    assert [r.getMessage() for r in caplog.records if "escalated" in r.getMessage()] == [
        f"[scrub] escalated job={old[:8]} days=32 stuck_at=db_pass last_error=row_failures"]


def test_an_escalated_job_still_finishes_once_the_row_is_fixed(engine, monkeypatch):
    """The escalated row is still worked: once eng fixes the poison row (here,
    the lease another runner held is released), the next pass completes it and
    _finish deletes it as any finished job."""
    now = datetime.now(timezone.utc)
    old, young = _stuck_pair(engine, now)
    t = db.deletion_scrub_jobs_table
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    scrub.tick(now)
    with engine.begin() as conn:
        conn.execute(update(t).where(t.c.job_id == old).values(claimed_until=None, last_error=None))
    scrub.run_pending()                           # the pass completes; the job finishes
    scrub.tick(now)
    with engine.connect() as conn:
        assert conn.execute(select(t.c.job_id)).scalars().all() == [young]


def test_a_pass_that_straddles_the_grace_is_not_the_grace_pass(engine, monkeypatch):
    """#562 QA P2-3: a resumable pass that started before IN_FLIGHT_GRACE and
    ended after it counted as the grace pass, so a deck row written in flight
    after its store's scan was never scrubbed and the job was deleted. The
    pass's start is its db_done_at now: the grace pass still runs."""
    from backend.eval import redaction
    from backend.tests.test_deletion_scrub import features_for
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    monkeypatch.setattr(scrub, "_SCAN_BATCH", 1)
    monkeypatch.setattr(scrub, "_SCAN_PAGES_PER_RUN", 2)
    with engine.begin() as conn:
        conn.execute(insert(db.user_events_table), [
            {"user_id": VIEWER, "event_type": "x", "occurred_at": EARLY, "props": json.dumps({"i": i})}
            for i in range(200)])                        # a long last scan
    accounts.delete_user_data(DEL)
    deleted = datetime.fromisoformat(job(engine)["deleted_at"])
    start = t = deleted + timedelta(minutes=1)
    wrote = False
    while not scrub.run_pending(t):
        state = json.loads(job(engine)["scan_json"] or "null")
        if not wrote and state and state["scan"] >= 2:   # deck_impressions' scan is behind it
            with engine.begin() as conn:
                conn.execute(insert(db.deck_impressions_table).values(
                    impression_id="late-9", user_id=VIEWER, league_id=LEAGUE, deck_job_id="deck-9",
                    card_index=9, trade_hash="hlate", propensity=1.0,
                    served_at=(deleted + timedelta(minutes=5)).isoformat(),
                    features_json=json.dumps(features_for(DEL))))
            wrote = True
        t += timedelta(minutes=5)
    assert wrote and t > deleted + scrub.IN_FLIGHT_GRACE           # it ended past the grace
    row = job(engine)
    assert datetime.fromisoformat(row["db_done_at"]) == start      # its start, not its end
    assert scrub._db_due(row, t) and scrub._finish(t) == 0
    grace_start = t
    while not scrub.run_pending(t):                                # the grace pass, resumed
        t += timedelta(minutes=5)
    assert datetime.fromisoformat(job(engine)["db_done_at"]) == grace_start
    (late,) = [r for r in read(engine, db.deck_impressions_table) if r["impression_id"] == "late-9"]
    assert DEL not in late["features_json"]
    scrub.tick(t + timedelta(minutes=1))
    assert read(engine, db.deletion_scrub_jobs_table) == []


def test_stuck_at_reads_only_this_versions_cursor():
    from types import SimpleNamespace
    row = lambda scan_json: SimpleNamespace(scan_json=scan_json, db_version=0, db_done_at=None)  # noqa: E731
    now = json.dumps({"version": scrub.SCRUB_VERSION, "scan": 0})
    old = json.dumps({"version": scrub.SCRUB_VERSION - 1, "scan": 0})
    assert scrub._stuck_at(row(now)) == scrub._SCANS[0][0] + "_scan"
    assert scrub._stuck_at(row(old)) == "db_pass"


def test_a_person_with_many_matches_is_scanned_without_a_term_per_match(engine):
    """#562 delta QA P3: the scan ORed two SQL terms per captured match id, so
    600+ ids broke SQLite's expression limit and the job never finished. It now
    reads the counterparties' notifications instead."""
    mt = db.trade_matches_table
    with engine.begin() as conn:
        conn.execute(insert(mt), [
            {"id": 1000 + i, "league_id": LEAGUE, "user_a_id": DEL, "user_b_id": f"cp{i}",
             "user_a_give": "[]", "user_a_receive": "[]", "status": "pending"} for i in range(1500)])
        # One counterparty per match, and one past the first 500 match ids, so
        # every batch of the counterparty lookup is needed (#562 final QA P3-2).
        notification(conn, "Trade match with @Someone", {"partner_username": "Someone", "match_id": 2200},
                     user="cp1200")
        notification(conn, "Trade match with @Someone", {"partner_username": "Someone", "match_id": 2200},
                     user="cp1201")                                # not a side of match 2200
    accounts.delete_user_data(DEL)
    assert scrub.run_pending() == 1
    rows = sorted(read(engine, db.notifications_table), key=lambda r: r["id"])
    assert [r["title"] for r in rows] == [f"Trade match with @{PLACEHOLDER}", "Trade match with @Someone"]
