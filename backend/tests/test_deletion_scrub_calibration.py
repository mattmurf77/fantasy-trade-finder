"""The deletion scrub on other users' Calibration sessions, built through the
real producers (#562 QA P1-1, P1-2, P2-4): blind_grading.start_session and
build_session (a stub value-core engine stands in for pipeline.run, with
ranking.card_reasons' real templates) and add_fit_arms (fit_engine.generate
stubbed, so the provenance is what add_fit_arms writes). A built session keeps
no partner ids in its source; the scrub finds the person's cards by
grading_cards.partner_user_id, and older cards (the column NULL) by their deck
row or a name. World adapted from release-lead's QA harness (qa562).

Runs on SQLite, and on Postgres too when FTF_TEST_PG_URL names a scratch
database (it's dropped and recreated per test): the scan's SQL prefilter
behaves differently there (LIKE is case-sensitive), which SQLite can't show
(#562 re-QA P2-B)."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, insert, select, text, update

from backend import accounts, blind_grading as bg, database as db, deletion_scrub as scrub
from backend.value_core.types import (CoreDiagnostics, DeckEntry, FairTrade, PipelineResult,
                                      ScoredTrade, Scores)

NOW = datetime.now(timezone.utc) - timedelta(hours=2)      # sessions built before the deletion
SERVED = (NOW - timedelta(days=1)).isoformat()
VALUE_DATE = (NOW - timedelta(days=1)).date().isoformat()
SERVER = bg.ServerInputs(lineup_slots=None, max_players=None, standings={}, completed_weeks=0)
POS = ("QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE")
DEL, DEL_USER, DEL_DISPLAY = "u3", "kim", "Kim K."
ROSTER = {u: [f"p{8 * i + k}" for k in range(1, 9)] for i, u in enumerate(("u1", "u2", "u3", "u4"))}
PICK = "L1_2027_1_3"
PLACEHOLDER = accounts.DELETED_USER_PLACEHOLDER


PG = os.environ.get("FTF_TEST_PG_URL")


@pytest.fixture(params=["sqlite", "postgres"])
def eng(request, monkeypatch, tmp_path):
    if request.param == "postgres":
        if not PG:
            pytest.skip("FTF_TEST_PG_URL not set")
        engine = create_engine(PG)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    else:
        engine = create_engine(f"sqlite:///{tmp_path}/c.db", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    from backend.eval import redaction
    monkeypatch.setattr(redaction, "redact_model_store", lambda tokens: 0)
    yield engine
    engine.dispose()


def member(league, uid, username, display):
    return {"league_id": league, "user_id": uid, "username": username, "display_name": display,
            "roster_data": json.dumps(ROSTER[uid])}


def seed(engine):
    players = [p for r in ROSTER.values() for p in r]
    with engine.begin() as conn:
        for lg, owner in (("L1", "u1"), ("L2", "u2"), ("L3", "u1"), ("L4", "u1")):
            conn.execute(insert(db.leagues_table).values(
                sleeper_league_id=lg, user_id=owner, name=f"League {lg}", platform="sleeper",
                default_scoring="1qb_ppr"))
        conn.execute(insert(db.league_members_table), [
            member("L1", "u1", "me", "Me"), member("L1", "u2", "jared", "Jared"),
            member("L1", DEL, DEL_USER, DEL_DISPLAY),
            member("L1", "u4", "kimfan", "kim"),        # a display name = the person's username
            member("L2", "u2", "jared", "Jared"), member("L2", "u1", "me", "Me"),
            member("L2", DEL, DEL_USER, DEL_DISPLAY),    # they leave L2 before deleting
            member("L3", "u1", "me", "Me"), member("L3", DEL, DEL_USER, "OldKim"),   # renamed later
            member("L4", "u1", "me", "Me"), member("L4", DEL, None, None)])          # no names
        for uid, un, dn in (("u1", "me", "Me"), ("u2", "jared", "Jared"),
                            (DEL, DEL_USER, DEL_DISPLAY), ("u4", "kimfan", "kim")):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid, username=un, display_name=dn))
        conn.execute(insert(db.players_table), [
            {"player_id": p, "full_name": f"Player {p[1:]}", "position": POS[i % 8],
             "team": "KC", "age": 22 + i % 9, "search_rank": i + 1} for i, p in enumerate(players)])
        conn.execute(insert(db.player_value_history_table), [
            {"player_id": p, "scoring_format": "1qb_ppr", "consensus_elo": 1900.0 - 10 * i,
             "snapshot_date": VALUE_DATE} for i, p in enumerate(players)])
        # Their own 2027 1st, traded to u2: the real label says "(from Kim K.)".
        conn.execute(insert(db.draft_picks_table).values(
            pick_id=PICK, league_id="L1", season=2027, round=1, owner_user_id="u2",
            owner_username="jared", original_user_id=DEL, original_username=DEL_DISPLAY,
            is_traded=1, pick_value=60.0, pool_value=2117.0, platform="sleeper", source=None))


def deck(conn, viewer, league, job, rows):
    for idx, (partner, give, receive) in enumerate(rows):
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id=f"{job}-{idx}", user_id=viewer, league_id=league, deck_job_id=job,
            card_index=idx, propensity=1.0, served_at=SERVED, model_arm="current",
            assets_json=json.dumps({"give": list(give), "receive": list(receive)}),
            features_json=json.dumps({"partner_user_id": partner, "basis": "value"})))


def reasons_for(partner):
    # ranking.card_reasons' templates: the partner's window, and a throw-in
    # valued on THEIR board.
    return (("Fair on value", "Fits their rebuild", "Throw-in: they rank Player 20 at 1.4× market")
            if partner == DEL else ("Fair on value",))


def stub_engine(rows):
    def run(snapshot, request, core_cfg, rank_cfg, **kw):
        return PipelineResult([DeckEntry(i, ScoredTrade(FairTrade(p, tuple(g), tuple(r), 1.0, 1.0, 1.0,
                                                                 0.0, None, False, (0, 0)),
                                                       Scores(.5, .5, .5, .5), {}), .5, reasons_for(p))
                               for i, (p, g, r) in enumerate(rows)], CoreDiagnostics(), 5)
    return run


def trades(viewer, partners, n_per=6, give_off=0):
    return [(partner, (ROSTER[viewer][(k + give_off) % 8],), (ROSTER[partner][(k + k // 8) % 8],))
            for partner in partners for k in range(n_per)]


def build(viewer, league, vc, seed_=5):
    sid = bg.start_session(user_id=viewer, league_user_id=viewer, league_id=league, now=NOW,
                           seed=seed_)["session"]["session_id"]
    bg.build_session(session_id=sid, server=SERVER, engine=stub_engine(vc), now=NOW)
    row = db.load_grading_session(sid)
    assert row["status"] == "open", row["error_json"]
    return sid


def fold_fit(sid, extra, monkeypatch):
    from backend import fit_engine as fe
    ft = lambda t: fe.FitTrade(t[0], tuple(t[1]), tuple(t[2]), 0.21, 0.37, 0.21)  # noqa: E731
    monkeypatch.setattr(fe, "generate", lambda snap, req, scorer: ([ft(t) for t in extra], {}))
    monkeypatch.setattr(fe, "assemble", lambda trades_, snap, size=fe.DECK_SIZE: list(trades_))
    assert bg.add_fit_arms(session_id=sid, server=SERVER, ros_points={}, now=NOW)["status"] == "added"


def cards(engine, sid):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(db.grading_cards_table).where(
            db.grading_cards_table.c.session_id == sid)).mappings()]


def world(eng, monkeypatch):
    """u1's session in L1 (current, value core and fit arms; u3, u2, u4 as
    partners, and the traded pick), u2's in L2 (a league u3 left), u1's in L3
    (u3 renamed after it was built) and L4 (u3 with no names), and u2's still
    building in L1."""
    seed(eng)
    with eng.begin() as conn:
        deck(conn, "u1", "L1", "J1", trades("u1", ("u2", DEL, "u4"), 7))
        deck(conn, "u2", "L1", "J2", trades("u2", ("u1", DEL), 10))
        deck(conn, "u2", "L2", "J3", trades("u2", ("u1", DEL), 10))
        deck(conn, "u1", "L3", "J4", trades("u1", (DEL,), 20))
        deck(conn, "u1", "L4", "J5", trades("u1", (DEL,), 20))
    vc1 = trades("u1", ("u2", DEL, "u4"), 7, give_off=3)
    vc1.insert(0, ("u2", (ROSTER["u1"][7],), (PICK,)))
    s = {"L1": build("u1", "L1", vc1)}
    fold_fit(s["L1"], trades("u1", (DEL, "u2"), 3, give_off=5), monkeypatch)
    for c in db.load_grading_cards(s["L1"])[:5]:
        bg.answer_card(user_id="u1", card_id=c["card_id"], body={"grade": 4})
    s["L2"] = build("u2", "L2", trades("u2", ("u1", DEL), 10, give_off=1))
    s["L3"] = build("u1", "L3", trades("u1", (DEL,), 20, give_off=1))
    s["L4"] = build("u1", "L4", trades("u1", (DEL,), 20, give_off=1))
    s["building"] = bg.start_session(user_id="u2", league_user_id="u2", league_id="L1", now=NOW,
                                     seed=9)["session"]["session_id"]
    with eng.begin() as conn:                        # platform syncs before the deletion
        m = db.league_members_table
        conn.execute(delete(m).where(m.c.league_id == "L2", m.c.user_id == DEL))
        conn.execute(update(m).where(m.c.league_id == "L3", m.c.user_id == DEL).values(display_name="NewKim"))
    return s


def delete_and_scrub(eng):
    accounts.delete_user_data(DEL)
    with eng.connect() as conn:
        job = dict(conn.execute(select(db.deletion_scrub_jobs_table)).mappings().one())
    deleted = datetime.fromisoformat(job["deleted_at"])
    assert scrub.run_pending(deleted + timedelta(minutes=1)) == 1
    return job["token"]


def theirs(card):
    return any(a["id"] in ROSTER[DEL] for a in json.loads(card["trade_json"])["receive"])


def assert_redacted(card, token):
    trade, arms = json.loads(card["trade_json"]), json.loads(card["arms_json"])
    assert trade["partner_name"] == PLACEHOLDER and card["partner_user_id"] == token, trade
    for arm, prov in arms.items():
        assert "gain_partner" not in prov and "reasons" not in prov, (arm, prov)


def test_the_build_stores_each_cards_partner(eng, monkeypatch):
    s = world(eng, monkeypatch)
    by_partner = {c["partner_user_id"] for c in cards(eng, s["L1"])}
    assert by_partner == {"u2", DEL, "u4"}
    fit = [c for c in cards(eng, s["L1"]) if "fit_a" in json.loads(c["arms_json"])]
    assert fit and all(c["partner_user_id"] in ("u2", DEL) for c in fit)


def test_every_card_of_the_person_is_redacted_by_its_stored_partner(eng, monkeypatch):
    """By partner_user_id, so a renamed person (L3: "OldKim" on the cards,
    "NewKim" captured), a league they left (L2), and a person with no names
    (L4: their raw id as the name) are all found. Their arms lose the partner's
    fields; grades stay; u4, whose display name is their username, keeps every
    card; their traded pick's label takes the placeholder on u2's card."""
    s = world(eng, monkeypatch)
    grades = {c["card_id"]: c["grade"] for c in cards(eng, s["L1"])}
    token = delete_and_scrub(eng)
    for league in ("L1", "L2", "L3", "L4"):
        mine = [c for c in cards(eng, s[league]) if theirs(c)]
        assert mine, league
        for c in mine:
            assert_redacted(c, token)
        for c in cards(eng, s[league]):
            blob = json.dumps(c)
            for needle in (f'"{DEL}"', DEL_DISPLAY, "OldKim", "NewKim", "gain_partner\": 0.37"):
                assert needle not in blob, (league, needle, blob[:200])
    l1 = cards(eng, s["L1"])
    assert {c["card_id"]: c["grade"] for c in l1} == grades
    u4 = [c for c in l1 if c["partner_user_id"] == "u4"]
    assert u4 and {json.loads(c["trade_json"])["partner_name"] for c in u4} == {"kim"}
    picks = [a["name"] for c in l1 for a in json.loads(c["trade_json"])["receive"] if a["id"] == PICK]
    assert picks == [f"2027 1st (from {PLACEHOLDER})"]
    with eng.connect() as conn:
        source = conn.execute(select(db.grading_sessions_table.c.source_json).where(
            db.grading_sessions_table.c.session_id == s["building"])).scalar()
    assert token in source and f'"{DEL}"' not in source


def legacy(eng, sids):
    """Cards built before grading_cards.partner_user_id existed."""
    with eng.begin() as conn:
        conn.execute(update(db.grading_cards_table).where(
            db.grading_cards_table.c.session_id.in_(sids)).values(partner_user_id=None))


def test_older_cards_are_traced_by_deck_row_raw_id_or_a_name_no_one_else_uses(eng, monkeypatch):
    """Older cards (the column NULL): a current-arm card by its deck row (in
    L3 only that finds it: the card says "OldKim", "NewKim" was captured), the
    L4 cards by the raw id shown as the name, and value-core / fit cards in L1
    by "Kim K.". "kim" (their username) is also u4's display name in L1, so it
    is never matched there: u4's cards keep it (QA P3)."""
    s = world(eng, monkeypatch)
    legacy(eng, [s["L1"], s["L3"], s["L4"]])
    token = delete_and_scrub(eng)
    current = [c for c in cards(eng, s["L3"]) if theirs(c) and "current" in json.loads(c["arms_json"])]
    assert current
    for c in current:
        assert_redacted(c, token)
    for league in ("L1", "L4"):
        for c in cards(eng, s[league]):
            if theirs(c):
                assert_redacted(c, token)
    u4 = [c for c in cards(eng, s["L1"]) if any(a["id"] in ROSTER["u4"]
                                                for a in json.loads(c["trade_json"])["receive"])]
    assert u4 and {json.loads(c["trade_json"])["partner_name"] for c in u4} == {"kim"}
    assert all(c["partner_user_id"] is None for c in u4)


def test_an_older_card_in_a_league_they_left_is_found_by_the_scan(eng, monkeypatch):
    """L2 isn't a captured league (they left it), so only the fallback scan
    reaches it: an older card naming them "Kim K." is redacted."""
    s = world(eng, monkeypatch)
    legacy(eng, [s["L2"]])
    with eng.connect() as conn:
        captured = scrub.capture_leagues(conn, [DEL])
    assert "L2" not in captured
    token = delete_and_scrub(eng)
    mine = [c for c in cards(eng, s["L2"]) if theirs(c)]
    assert mine and all(json.loads(c["trade_json"])["partner_name"] == PLACEHOLDER for c in mine)
    assert all(c["partner_user_id"] == token for c in mine)


def test_a_session_after_the_cutoff_or_their_own_is_left_alone(eng, monkeypatch):
    """Sessions created after the job's cutoff (deleted_at + the grace), and a
    session owned by a deleted id (a re-signup within the grace), are never
    scrubbed."""
    s = world(eng, monkeypatch)
    accounts.delete_user_data(DEL)
    with eng.connect() as conn:
        job = dict(conn.execute(select(db.deletion_scrub_jobs_table)).mappings().one())
    deleted = datetime.fromisoformat(job["deleted_at"])
    late = (deleted + scrub.IN_FLIGHT_GRACE + timedelta(minutes=1)).isoformat()
    source = json.dumps({"seat": DEL, "current": {"cards": []}})
    with eng.begin() as conn:
        gs, gc = db.grading_sessions_table, db.grading_cards_table
        conn.execute(insert(gs).values(session_id="after", user_id="u1", league_id="L1",
                                       status="open", seed="1", created_at=late, counts_json="{}",
                                       source_json="{}"))
        conn.execute(insert(gc).values(card_id="after-1", session_id="after", user_id="u1", position=1,
                                       partner_user_id=DEL, arms_json=json.dumps({"value_core": {"reasons": ["r"]}}),
                                       trade_json=json.dumps({"partner_name": DEL_DISPLAY,
                                                              "give": [], "receive": []})))
        conn.execute(insert(gs).values(session_id="own", user_id=DEL, league_id="L1",
                                       status="building", seed="1", created_at=deleted.isoformat(),
                                       counts_json="{}", source_json=source))
    assert scrub.run_pending(deleted + timedelta(minutes=1)) == 1
    (after,) = cards(eng, "after")
    assert json.loads(after["trade_json"])["partner_name"] == DEL_DISPLAY and after["partner_user_id"] == DEL
    with eng.connect() as conn:
        own = conn.execute(select(db.grading_sessions_table.c.source_json).where(
            db.grading_sessions_table.c.session_id == "own")).scalar()
    assert own == source
    assert s                                          # the world's own sessions were scrubbed meanwhile


def test_a_job_done_at_stage_2_runs_again(eng, monkeypatch):
    """A job whose DB pass ran at SCRUB_VERSION 2 is due again under stage 3,
    so a deletion before stage 3 deployed still gets Calibration scrubbed."""
    s = world(eng, monkeypatch)
    accounts.delete_user_data(DEL)
    with eng.begin() as conn:
        t = db.deletion_scrub_jobs_table
        row = dict(conn.execute(select(t)).mappings().one())
        deleted = datetime.fromisoformat(row["deleted_at"])
        conn.execute(update(t).values(db_version=2, db_done_at=(deleted + timedelta(hours=7)).isoformat(),
                                      model_done_at=(deleted + timedelta(hours=7)).isoformat()))
        row = dict(conn.execute(select(t)).mappings().one())
    assert scrub.SCRUB_VERSION >= 3 and scrub._db_due(row, deleted + timedelta(hours=8))
    assert scrub.run_pending(deleted + timedelta(hours=8)) == 1
    assert all(json.loads(c["trade_json"])["partner_name"] == PLACEHOLDER
               for c in cards(eng, s["L1"]) if theirs(c))


def left_league(eng, monkeypatch, *, legacy_cards=True, boot_before_leaving=False):
    """L5: u1 and u3, where u3 went by "KimFive" (a name of theirs nowhere
    else) and left before deleting, so nothing about them was captured there.
    u1's built session has current-arm cards (traceable only by their deck
    row) and value-core cards. u5 joins L2 with display name "kim" (u3's
    username) and has older cards in u2's L2 session."""
    s = world(eng, monkeypatch)
    with eng.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id="L5", user_id="u1", name="League L5", platform="sleeper",
            default_scoring="1qb_ppr"))
        conn.execute(insert(db.league_members_table), [
            member("L5", "u1", "me", "Me"), member("L5", DEL, "kimfive", "KimFive")])
        deck(conn, "u1", "L5", "J6", trades("u1", (DEL,), 20))
    s["L5"] = build("u1", "L5", trades("u1", (DEL,), 20, give_off=1))
    # u2's sessions in L5 that failed and are still building: start_session's
    # building source, which lists u3 (fail_grading_session keeps it).
    building = json.dumps({"version": bg.VERSION, "seat": "u2", "scoring_format": "1qb_ppr",
                           "current": {"cards": [{"partner_id": DEL, "give": [ROSTER["u1"][0]],
                                                  "receive": [ROSTER[DEL][0]], "provenance": {}}]}},
                          sort_keys=True)
    with eng.begin() as conn:
        gs = db.grading_sessions_table
        for sid in ("L5-failed", "L5-building"):
            conn.execute(insert(gs).values(session_id=sid, user_id="u2", league_id="L5",
                                           status="building", seed="1", created_at=NOW.isoformat(),
                                           counts_json="{}", source_json=building))
    assert db.fail_grading_session("L5-failed", json.dumps({"code": "value_core_failed"}))
    s["L5-failed"] = "L5-failed"
    if boot_before_leaving:          # a deploy's boot backfill while they're still in L5
        legacy(eng, [s["L1"], s["L3"], s["L5"]])
        assert db.backfill_grading_card_partners()
    with eng.begin() as conn:
        m = db.league_members_table
        conn.execute(delete(m).where(m.c.league_id == "L5", m.c.user_id == DEL))
        conn.execute(insert(m).values(member("L2", "u4", "kimfan2", "kim")))
        gc = db.grading_cards_table
        conn.execute(insert(gc).values(
            card_id="u5-old", session_id=s["L2"], user_id="u2", position=999,
            arms_json=json.dumps({"value_core": {"deck_position": 1, "reasons": ["Fair on value"]}}),
            trade_json=json.dumps({"partner_name": "kim", "give": [], "receive": []})))
    s["L5-building"] = "L5-building"
    if legacy_cards:
        legacy(eng, [s["L5"]])
    return s


def test_a_failed_or_building_session_in_a_league_they_left_takes_the_token(eng, monkeypatch):
    """#562 re-QA P2-A: a session that failed (or was retired) while building
    keeps its building source, partner ids and all; the scan's session pass
    took only building ones."""
    s = left_league(eng, monkeypatch)
    token = delete_and_scrub(eng)
    with eng.connect() as conn:
        gs = db.grading_sessions_table
        for sid in (s["L5-failed"], s["L5-building"]):
            source = conn.execute(select(gs.c.source_json).where(gs.c.session_id == sid)).scalar()
            assert token in source and f'"{DEL}"' not in source, sid


def test_older_current_arm_cards_in_a_league_with_no_captured_name_are_traced(eng, monkeypatch):
    """#562 re-QA P2-B: in L5 nothing names them in a way the SQL could
    match, so only the deck row finds the current-arm cards; the scan must
    look at every older card, on Postgres too. In L2, "kim" is u5's display
    name, so u5's older card keeps it (the left-league collision guard)."""
    s = left_league(eng, monkeypatch)
    token = delete_and_scrub(eng)
    current = [c for c in cards(eng, s["L5"]) if "current" in json.loads(c["arms_json"])]
    assert current
    for c in current:
        assert_redacted(c, token)
    (u5,) = [c for c in cards(eng, s["L2"]) if c["card_id"] == "u5-old"]
    assert json.loads(u5["trade_json"])["partner_name"] == "kim" and u5["partner_user_id"] is None


def test_the_backfill_gives_older_cards_their_partner(eng, monkeypatch):
    """At boot, before any deletion: a current-arm card takes its deck row's
    partner, any other the one member shown by its partner_name; ambiguous or
    unknown stays NULL. Then every one of the person's cards in L5, value
    core included, is redacted by id."""
    s = left_league(eng, monkeypatch, legacy_cards=False, boot_before_leaving=True)

    def pick_only(c):
        return all(a["position"] == "PICK" for a in json.loads(c["trade_json"])["receive"])
    l1 = cards(eng, s["L1"])
    assert all(c["partner_user_id"] is not None for c in l1 if not pick_only(c))
    assert [c["partner_user_id"] for c in l1 if pick_only(c)] == [None]   # no roster evidence
    assert {c["partner_user_id"] for c in l1} - {None} == {"u2", DEL, "u4"}
    l5 = cards(eng, s["L5"])
    assert l5 and all(c["partner_user_id"] == DEL for c in l5)   # deck row, or "KimFive" while live
    l3_old = [c for c in cards(eng, s["L3"]) if "current" not in json.loads(c["arms_json"])]
    assert l3_old and all(c["partner_user_id"] is None for c in l3_old)   # "OldKim": nobody now
    db.backfill_grading_card_partners()                                   # u5's card, added since
    assert db.backfill_grading_card_partners() == 0                       # idempotent
    token = delete_and_scrub(eng)
    for c in cards(eng, s["L5"]):
        assert_redacted(c, token)


def test_the_scan_keeps_the_cutoff_and_the_owner(eng, monkeypatch):
    """In a league they had left (the scan's side): a session created after
    the cutoff, and a session owned by a deleted id (a re-signup within the
    grace), are never scrubbed."""
    s = left_league(eng, monkeypatch)
    accounts.delete_user_data(DEL)
    with eng.connect() as conn:
        job = dict(conn.execute(select(db.deletion_scrub_jobs_table)).mappings().one())
    deleted = datetime.fromisoformat(job["deleted_at"])
    late = (deleted + scrub.IN_FLIGHT_GRACE + timedelta(minutes=1)).isoformat()
    pick = json.dumps({"partner_name": "Me", "give": [],
                       "receive": [{"id": "x", "name": f"2027 1st (from {DEL_DISPLAY})"}]})
    with eng.begin() as conn:
        gs, gc = db.grading_sessions_table, db.grading_cards_table
        for sid, owner, created in (("late-L5", "u1", late), ("own-L5", DEL, deleted.isoformat())):
            conn.execute(insert(gs).values(session_id=sid, user_id=owner, league_id="L5", status="open",
                                           seed="1", created_at=created, counts_json="{}", source_json="{}"))
            conn.execute(insert(gc).values(card_id=f"{sid}-1", session_id=sid, user_id=owner, position=1,
                                           partner_user_id=DEL if owner != DEL else "u1",
                                           arms_json=json.dumps({"value_core": {"reasons": ["r"]}}),
                                           trade_json=pick))
    assert scrub.run_pending(deleted + timedelta(minutes=1)) == 1
    for sid in ("late-L5", "own-L5"):
        (c,) = cards(eng, sid)
        assert c["trade_json"] == pick and json.loads(c["arms_json"]) == {"value_core": {"reasons": ["r"]}}, sid
    assert s


def test_the_backfill_uses_the_deck_row_and_skips_an_ambiguous_name(eng, monkeypatch):
    """L3's older current-arm cards say "OldKim", which nobody shows now: only
    their deck row gives the partner. A card naming "Twin", which two L1
    members show, stays NULL rather than guessing."""
    s = world(eng, monkeypatch)
    legacy(eng, [s["L3"]])
    with eng.begin() as conn:
        conn.execute(insert(db.league_members_table), [
            {"league_id": "L1", "user_id": uid, "username": None, "display_name": "Twin",
             "roster_data": json.dumps(["p77"])} for uid in ("u7", "u8")])
        conn.execute(insert(db.grading_cards_table).values(
            card_id="twin", session_id=s["L1"], user_id="u1", position=998,
            arms_json=json.dumps({"value_core": {"deck_position": 1, "reasons": []}}),
            trade_json=json.dumps({"partner_name": "Twin", "give": [],
                                   "receive": [{"id": "p77", "position": "WR"}]})))
    db.backfill_grading_card_partners()
    l3 = cards(eng, s["L3"])
    current = [c for c in l3 if "current" in json.loads(c["arms_json"])]
    assert current and all(c["partner_user_id"] == DEL for c in current)
    assert all(c["partner_user_id"] is None for c in l3 if c not in current)
    (twin,) = [c for c in cards(eng, s["L1"]) if c["card_id"] == "twin"]
    assert twin["partner_user_id"] is None


# ── The boot backfill, hardened (#562 delta QA): it runs from _migrate_db, so
# during a Render build too, against prod while the old instance serves ────

def older(eng, monkeypatch):
    s = world(eng, monkeypatch)
    legacy(eng, [s["L1"], s["L3"], s["L4"]])
    return s


def all_cards(eng):
    with eng.connect() as conn:
        return {r["card_id"]: dict(r) for r in conn.execute(select(db.grading_cards_table)).mappings()}


def test_init_db_runs_the_backfill(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'boot.db'}"
    engine = create_engine(url)
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    calls = []
    monkeypatch.setattr(db, "backfill_grading_card_partners", lambda: calls.append(1) or 0)
    db.init_db()
    assert calls == [1]
    engine.dispose()


def test_the_backfill_writes_only_the_partner_in_chunks_with_one_deck_lookup_each(eng, monkeypatch, caplog):
    """Chunks of _BACKFILL_CHUNK, each its own transaction with one batched
    deck-row lookup; only partner_user_id changes (grades, tags, positions
    kept); the log carries counts, never an id or a name."""
    import logging
    from sqlalchemy import event
    s = older(eng, monkeypatch)
    for c in db.load_grading_cards(s["L1"])[:3]:
        bg.answer_card(user_id="u1", card_id=c["card_id"], body={"grade": 2, "tags": []})
    before = all_cards(eng)
    pending = sum(1 for c in before.values() if c["partner_user_id"] is None)
    monkeypatch.setattr(db, "_BACKFILL_CHUNK", 7)
    lookups = []
    event.listen(eng, "before_cursor_execute",
                 lambda conn, cur, stmt, *a: lookups.append(1) if "FROM deck_impressions" in stmt else None)
    caplog.set_level(logging.INFO, logger=db.log.name)
    filled = db.backfill_grading_card_partners()
    chunks = -(-pending // 7)
    assert 0 < filled <= pending and len(lookups) <= chunks
    after = all_cards(eng)
    assert sum(1 for c in after.values() if c["partner_user_id"] is not None) - \
        sum(1 for c in before.values() if c["partner_user_id"] is not None) == filled
    for cid, row in before.items():
        assert {k: v for k, v in after[cid].items() if k != "partner_user_id"} == \
            {k: v for k, v in row.items() if k != "partner_user_id"}, cid
    text_ = caplog.text
    for needle in ("u1", "u2", DEL, "u4", DEL_DISPLAY, "Jared", "kimfan"):
        assert needle not in text_, needle
    assert f"grading_cards partner backfill: {filled} cards, 0 chunks failed" in text_


def test_the_backfill_counts_only_what_committed_and_never_raises(eng, monkeypatch):
    """A chunk that fails (here its commit) is rolled back, not counted, and
    skipped; the others land. A failure before any chunk returns 0. It never
    raises (it runs at boot)."""
    from sqlalchemy import event
    older(eng, monkeypatch)
    monkeypatch.setattr(db, "_BACKFILL_CHUNK", 5)
    commits = []

    def fail_first_commit(conn):          # commit 1 is the pending read; 2 the first chunk
        commits.append(1)
        if len(commits) == 2:
            raise RuntimeError("commit failed")
    event.listen(eng, "commit", fail_first_commit)
    before = sum(1 for c in all_cards(eng).values() if c["partner_user_id"] is None)
    filled = db.backfill_grading_card_partners()
    event.remove(eng, "commit", fail_first_commit)
    after = sum(1 for c in all_cards(eng).values() if c["partner_user_id"] is None)
    assert filled == before - after and filled > 0
    assert db.backfill_grading_card_partners() > 0          # the skipped chunk, next boot

    class Broken:
        dialect = eng.dialect

        def connect(self):
            raise RuntimeError("no database")
    monkeypatch.setattr(db, "engine", Broken())
    assert db.backfill_grading_card_partners() == 0


def test_on_postgres_each_chunk_sets_its_lock_and_statement_timeouts(eng, monkeypatch):
    from sqlalchemy import event
    if eng.dialect.name != "postgresql":
        pytest.skip("Postgres only: SET LOCAL")
    older(eng, monkeypatch)
    monkeypatch.setattr(db, "_BACKFILL_CHUNK", 10)
    seen = []
    event.listen(eng, "before_cursor_execute", lambda conn, cur, stmt, *a: seen.append(stmt))
    db.backfill_grading_card_partners()
    locks = [x for x in seen if x.startswith("SET LOCAL lock_timeout")]
    stmts = [x for x in seen if x.startswith("SET LOCAL statement_timeout")]
    updates = [x for x in seen if x.startswith("UPDATE grading_cards")]
    assert locks and len(locks) == len(stmts) and updates


def test_a_name_fill_needs_the_cards_players_on_that_members_roster(eng, monkeypatch):
    """After a rename, "Jared" can name someone else: u2's older card stays
    NULL when the member now shown as "Jared" (u9) doesn't hold the players it
    received from u2, rather than being filled with u9."""
    s = world(eng, monkeypatch)
    legacy(eng, [s["L1"]])
    with eng.begin() as conn:
        m = db.league_members_table
        conn.execute(update(m).where(m.c.league_id == "L1", m.c.user_id == "u2").values(display_name="J2"))
        conn.execute(insert(m).values(league_id="L1", user_id="u9", username="nine", display_name="Jared",
                                      roster_data=json.dumps(["p99"])))
    db.backfill_grading_card_partners()
    jared = [c for c in cards(eng, s["L1"]) if json.loads(c["trade_json"])["partner_name"] == "Jared"
             and "current" not in json.loads(c["arms_json"])]
    assert jared and all(c["partner_user_id"] is None for c in jared)


def test_an_older_current_arm_card_whose_name_matches_nothing_is_scanned_on_sqlite(eng, monkeypatch):
    """The P2-B case visible on SQLite too: in L6, a league they left, they went
    by "Zed", which shares no text with any name captured, so only the scan's
    NULL-partner term brings the card to its deck-row trace."""
    s = world(eng, monkeypatch)
    with eng.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id="L6", user_id="u1", name="League L6", platform="sleeper",
            default_scoring="1qb_ppr"))
        conn.execute(insert(db.league_members_table), [
            member("L6", "u1", "me", "Me"), member("L6", DEL, "zzz", "Zed")])
        deck(conn, "u1", "L6", "J7", trades("u1", (DEL,), 20))
    s["L6"] = build("u1", "L6", trades("u1", (DEL,), 20, give_off=1))
    legacy(eng, [s["L6"]])
    with eng.begin() as conn:
        m = db.league_members_table
        conn.execute(delete(m).where(m.c.league_id == "L6", m.c.user_id == DEL))
    token = delete_and_scrub(eng)
    current = [c for c in cards(eng, s["L6"]) if "current" in json.loads(c["arms_json"])]
    assert current
    for c in current:
        assert_redacted(c, token)


def test_every_backfill_transaction_sets_both_timeouts(eng, monkeypatch):
    """Seen on SQLite too (CI runs SQLite): with Postgres assumed, the first
    read and every chunk issue SET LOCAL lock_timeout and statement_timeout."""
    older(eng, monkeypatch)
    monkeypatch.setattr(db, "_BACKFILL_CHUNK", 10)
    issued = []
    monkeypatch.setattr(db, "_ddl_is_postgres", lambda: True)
    monkeypatch.setattr(db, "_execute_ddl", lambda conn, sql: issued.append(sql))
    begins = []
    real_begin = db.engine.begin
    monkeypatch.setattr(db.engine, "begin", lambda: begins.append(1) or real_begin())
    db.backfill_grading_card_partners()
    assert begins and issued == [f"SET LOCAL lock_timeout = '{db._DDL_LOCK_TIMEOUT}'",
                                 f"SET LOCAL statement_timeout = '{db._DDL_STATEMENT_TIMEOUT}'"] * len(begins)


def test_the_backfill_never_fills_the_sessions_own_user_and_skips_a_bad_receive(eng, monkeypatch, caplog):
    """(c) The viewer, renamed "Jared" and now holding the players the card
    received from u2 (the trade went through), is never the partner. A card
    whose receive is not a list (never written by neutral_trade) is left alone
    without sinking its chunk."""
    import logging
    s = world(eng, monkeypatch)
    legacy(eng, [s["L1"]])
    jared = [c for c in cards(eng, s["L1"]) if json.loads(c["trade_json"])["partner_name"] == "Jared"
             and "current" not in json.loads(c["arms_json"])]
    received = sorted({a["id"] for c in jared for a in json.loads(c["trade_json"])["receive"]
                       if a["position"] != "PICK"})
    with eng.begin() as conn:
        m = db.league_members_table
        conn.execute(update(m).where(m.c.league_id == "L1", m.c.user_id == "u2").values(display_name="J2"))
        conn.execute(update(m).where(m.c.league_id == "L1", m.c.user_id == "u1").values(
            display_name="Jared", roster_data=json.dumps(ROSTER["u1"] + received)))
        conn.execute(insert(db.grading_cards_table).values(
            card_id="scalar", session_id=s["L1"], user_id="u1", position=997,
            arms_json=json.dumps({"value_core": {}}),
            trade_json=json.dumps({"partner_name": "Me", "give": [], "receive": 5})))
    caplog.set_level(logging.INFO, logger=db.log.name)
    filled = db.backfill_grading_card_partners()
    by_id = {c["card_id"]: c for c in cards(eng, s["L1"])}
    assert all(by_id[c["card_id"]]["partner_user_id"] is None for c in jared)
    assert by_id["scalar"]["partner_user_id"] is None
    assert filled and f"{filled} cards, 0 chunks failed" in caplog.text
