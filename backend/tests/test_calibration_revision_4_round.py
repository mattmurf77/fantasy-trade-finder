"""The revision-4 Calibration round (outlook-v2-v4-1) beside outlook-v2-v3-1.

docs/plans/offer-learnings/plan.md §3 WS1b and scope-revision-4-round.md. Stub arms
test orchestration, as test_outlook_calibration_service.py does; the adapter's
real-engine run of revision 4 on one capture is test_calibration_revision_4.py's.
"""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import blind_grading as bg, database as db, feature_flags as ff, outlook_calibration as oc, server
from backend import outlook_calibration_adapter as adapter
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401

R4 = oc.R4_ROUND_ID
V2, V3, V4 = "owner-v2-bilateral-2", "owner-v2-bilateral-3", "owner-v2-bilateral-4"
TOKEN = "synthetic-revision-4-round-token"
AUTH = {"X-Session-Token": TOKEN}
CRON = {"X-Cron-Secret": "synthetic-cron-secret"}


@pytest.fixture
def flags(monkeypatch):
    cache = {**ff.DEFAULT_FLAGS, "grading.blind": True, "grading.outlook_round": True}
    monkeypatch.setattr(ff, "_flags_cache", cache)
    monkeypatch.setattr(oc, "kick_worker", lambda: None)
    monkeypatch.setattr(adapter, "is_current", lambda *a, **k: True)
    return cache


@pytest.fixture
def client(engine, flags, monkeypatch):  # noqa: F811
    monkeypatch.setattr(server, "_CRON_SECRET", "synthetic-cron-secret")
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="league", user_id="account"))
    sess = {"user_id": "account", "league_user_id": "seat", "verified": True, "last_active": 0.,
            "league": SimpleNamespace(league_id="league", platform="sleeper"), "players": [],
            "trade_svc": object()}
    server._sessions[TOKEN] = sess
    server.app.config["TESTING"] = True
    yield server.app.test_client()
    server._sessions.pop(TOKEN, None)


class Proof:
    def __init__(self, version):
        self.model_identity = ("owner", version)

    def matches(self, card):
        return True

    def as_dict(self):
        return {"model_version": self.model_identity[1]}


def frozen_factory():
    """v2 = r0..r11; v3 = r0..r2 + r40..r48; v4 = r0..r2 + r60..r68 (12 each, 3 shared)."""
    calls = []
    assets = {i: {"name": i, "position": "WR", "nfl_team": "X", "age": 26, "value": 1000}
              for i in ["g"] + [f"r{i}" for i in range(100)]}
    catalog = bg.Catalog(assets=assets, partner_names={"partner": "Partner"},
                         holdings={"seat": frozenset({"g"}), "partner": frozenset(assets) - {"g"}})
    ids = {V2: list(range(12)), V3: [0, 1, 2, *range(40, 49)], V4: [0, 1, 2, *range(60, 69)]}

    def run(version, *, check_current=None):
        calls.append(version)
        rows = [SimpleNamespace(target_user_id="partner", give_player_ids=("g",),
                                receive_player_ids=(f"r{i}",), owner_evaluation=Proof(version))
                for i in ids[version]]
        return rows, {"native_count": len(rows), "final_count": len(rows)}
    return SimpleNamespace(source={}, catalog=catalog, run_arm=run), calls


def build(user="account", round_id=oc.ROUND_ID):
    frozen, calls = frozen_factory()
    kwargs = {"round_id": round_id} if round_id != oc.ROUND_ID else {}
    sid = oc.start_session(user_id=user, league_user_id="seat", league_id="league", seed=91,
                           **kwargs)["session"]["session_id"]
    oc.build_session(session_id=sid, capture=lambda **scope: frozen)
    return sid, calls


def expose(sid):
    with db.engine.begin() as conn:
        conn.execute(db.grading_sessions_table.update().where(
            db.grading_sessions_table.c.session_id == sid).values(first_exposed_at="2026-11-10T00:00:00+00:00"))


def answer_all(sid, user="account", grade=4):
    for c in db.load_grading_cards(sid):
        db.answer_grading_card(c["card_id"], user, grade=grade, skipped=False, tags_json="[]",
                               now="2026-11-10T00:00:01+00:00")


def current_round_rows():
    gs, gc = db.grading_sessions_table, db.grading_cards_table
    with db.engine.connect() as conn:
        sessions = [dict(r) for r in conn.execute(select(gs).where(gs.c.round_id == oc.ROUND_ID)
                                                  .order_by(gs.c.session_id)).mappings()]
        ids = [s["session_id"] for s in sessions]
        cards = [dict(r) for r in conn.execute(select(gc).where(gc.c.session_id.in_(ids))
                                               .order_by(gc.c.card_id)).mappings()]
    return sessions, cards


def round_ids():
    gs = db.grading_sessions_table
    with db.engine.connect() as conn:
        return sorted(r for r in conn.execute(select(gs.c.round_id)).scalars())


# -- what the round compares ---------------------------------------------------------------

def test_round_compares_revision_2_with_revision_4_on_one_capture_blind(engine, flags):  # noqa: F811
    flags["grading.revision4_round"] = True
    flags["grading.revision4_arm"] = True  # superseded: must add nothing to the round's deck
    sid, calls = build(round_id=R4)
    row, cards = db.load_grading_session(sid), db.load_grading_cards(sid)
    assert sorted(calls) == sorted([V2, V4])  # never revision 3, never a third run
    source, counts = json.loads(row["source_json"]), json.loads(row["counts_json"])
    assert row["round_id"] == R4 and row["status"] == "open"
    assert source["version"] == R4 and source["model_versions"] == {"current": V2, "value_core": V4}
    assert "extra_arms" not in source
    assert set(counts["arms"]) == {V2, V4}
    assert counts["arms"][V2]["selected"] == counts["arms"][V4]["selected"] == 12
    assert counts["shared"] == 3 and counts["total"] == len(cards) == 21
    for c in cards:
        arms = json.loads(c["arms_json"])
        assert set(arms) <= {"current", "value_core"}
        assert {a["model_version"] for a in arms.values()} <= {V2, V4}
        assert "bilateral" not in c["trade_json"] and "value_core" not in c["trade_json"]


def test_session_and_card_payloads_stay_blind(client, flags):
    flags["grading.revision4_round"] = True
    sid, _ = build(round_id=R4)
    current = client.get(f"/api/grading/sessions/current?league_id=league&round_id={R4}", headers=AUTH)
    nxt = client.get(f"/api/grading/sessions/{sid}/next", headers=AUTH)
    assert current.status_code == 200 and nxt.status_code == 200
    for body in (current.json, nxt.json):
        text = json.dumps(body)
        assert "bilateral" not in text and R4 not in text and "arms" not in text


# -- the route sequence the installed app calls --------------------------------------------
# Offer order with no round_id (default_round): a current deck part-way through first; then
# the revision-4 deck until it is completed; then the current round's deck again.

CURRENT = "/api/grading/sessions/current?league_id=league"


def grade_through(client, sid, grade):
    """CalibrationScreen: next -> answer each card until done. Returns the last session_status."""
    status = None
    while True:
        nxt = client.get(f"/api/grading/sessions/{sid}/next", headers=AUTH)
        assert nxt.status_code == 200, nxt.json
        if nxt.json["done"]:
            return status
        status = client.post(f"/api/grading/cards/{nxt.json['card']['card_id']}", json={"grade": grade},
                             headers=AUTH).json["session_status"]


def start_and_build(client, round_id):
    """Start (202 building), the worker builds, GET current shows it open. Returns its id."""
    start = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
    assert start.status_code == 202 and start.json["session"]["status"] == "building"
    sid = start.json["session"]["session_id"]
    assert db.load_grading_session(sid)["round_id"] == round_id
    assert client.get(CURRENT, headers=AUTH).json["session"]["session_id"] == sid
    frozen, calls = frozen_factory()
    assert oc.drain_queue(capture=lambda **k: frozen,
                          **({"round_id": round_id} if round_id != oc.ROUND_ID else {}))["processed"] == 1
    assert sorted(calls) == sorted([V2, V4] if round_id == R4 else [V2, V3])
    opened = client.get(CURRENT, headers=AUTH).json["session"]
    assert opened["session_id"] == sid and opened["status"] == "open"
    assert opened["progress"] == {"answered": 0, "total": 21}
    return sid


def test_in_progress_user_finishes_the_current_deck_first(client, flags):
    flags["grading.revision4_round"] = True
    first, _ = build()
    expose(first)  # the user opened it earlier
    current = client.get(CURRENT, headers=AUTH)
    assert current.json["session"]["session_id"] == first
    assert client.post("/api/grading/sessions", json={"league_id": "league"},
                       headers=AUTH).json["session"]["session_id"] == first
    assert grade_through(client, first, 4) == "completed"
    results = client.get(f"/api/grading/sessions/{first}/results", headers=AUTH)
    assert results.json["round_id"] == oc.ROUND_ID and results.json["model_versions"]["value_core"] == V3
    # Done -> handleDone re-reads GET current: no revision-4 deck yet, so Start.
    assert client.get(CURRENT, headers=AUTH).json == {"session": None}
    second = start_and_build(client, R4)
    assert grade_through(client, second, 5) == "completed"
    results = client.get(f"/api/grading/sessions/{second}/results", headers=AUTH).json
    assert results["round_id"] == R4 and results["model_versions"] == {"current": V2, "value_core": V4}
    assert results["arm_labels"] == {"current": "Today's engine", "value_core": "New engine"}
    assert results["arms"]["current"]["n"] == results["arms"]["value_core"]["n"] == 12
    # Both done: Start shows the revision-4 results; the first round's results are unchanged.
    assert client.get(CURRENT, headers=AUTH).json == {"session": None}
    again = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
    assert again.status_code == 200 and again.json["session"]["session_id"] == second
    assert client.get(f"/api/grading/sessions/{first}/results", headers=AUTH).json["arms"]["current"]["mean"] == 4


def test_never_started_user_gets_revision_4_first_then_the_current_deck(client, flags):
    flags["grading.revision4_round"] = True
    assert client.get(CURRENT, headers=AUTH).json == {"session": None}
    second = start_and_build(client, R4)
    assert grade_through(client, second, 5) == "completed"
    assert client.get(f"/api/grading/sessions/{second}/results", headers=AUTH).json["round_id"] == R4
    # Done -> GET current: the current round now, still nothing built, so Start builds it.
    assert client.get(CURRENT, headers=AUTH).json == {"session": None}
    first = start_and_build(client, oc.ROUND_ID)
    assert grade_through(client, first, 3) == "completed"
    results = client.get(f"/api/grading/sessions/{first}/results", headers=AUTH).json
    assert results["round_id"] == oc.ROUND_ID and results["model_versions"]["value_core"] == V3
    # Both done: Start returns the revision-4 results, no third deck.
    again = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
    assert again.status_code == 200 and again.json["session"]["session_id"] == second
    assert round_ids() == [oc.ROUND_ID, R4]


@pytest.mark.parametrize("stale", [False, True])
def test_an_unstarted_current_deck_is_skipped_then_offered_again_unchanged(client, flags, monkeypatch, stale):
    first, _ = build()  # pre-generated, never opened
    before = current_round_rows()
    flags["grading.revision4_round"] = True
    assert client.get(CURRENT, headers=AUTH).json == {"session": None}  # revision-4 round, none yet
    second = start_and_build(client, R4)
    assert current_round_rows() == before  # skipped, not retired or rebuilt
    assert grade_through(client, second, 5) == "completed"
    assert current_round_rows() == before
    # Revision 4 done: the same current-round deck is offered again (Resume 0 of 21).
    current = client.get(CURRENT, headers=AUTH).json["session"]
    assert current["session_id"] == first and current["status"] == "open"
    assert current["progress"] == {"answered": 0, "total": 21}
    assert current_round_rows() == before
    if stale:
        # The current round's own rule, unchanged: an unexposed deck whose inputs changed is
        # retired on Start and rebuilt, exactly as it would be without the new round.
        monkeypatch.setattr(adapter, "is_current", lambda *a, **k: False)
        start = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
        assert start.status_code == 202 and start.json["session"]["session_id"] != first
        assert json.loads(db.load_grading_session(first)["error_json"]) == {"code": "comparison_stale"}
    else:
        start = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
        assert start.status_code == 200 and start.json["session"]["session_id"] == first
        assert current_round_rows() == before


def test_a_failed_current_deck_moves_on_to_revision_4_which_fails_the_same_way(client, flags):
    from backend.tests.test_outlook_calibration_persistence import session
    row = session("failed-first", status="failed")
    row["error_json"] = json.dumps({"code": "provider_lineup_unsupported"})
    db.insert_grading_session(row, [])
    before = current_round_rows()
    flags["grading.revision4_round"] = True
    start = client.post("/api/grading/sessions", json={"league_id": "league"}, headers=AUTH)
    assert start.status_code == 202
    second = start.json["session"]["session_id"]
    assert db.load_grading_session(second)["round_id"] == R4

    def unsupported(**scope):
        raise bg.GradingError("provider_lineup_unsupported", 409)
    oc.drain_queue(capture=unsupported, round_id=R4)
    shown = client.get(CURRENT, headers=AUTH).json["session"]
    assert shown["session_id"] == second and shown["status"] == "failed"
    assert shown["error"] == {"code": "provider_lineup_unsupported"}
    assert current_round_rows() == before


def test_explicit_round_ids_address_each_round_and_unknown_is_refused(client, flags):
    flags["grading.revision4_round"] = True
    first, _ = build()
    second, _ = build(round_id=R4)
    by_round = lambda rid: client.get(f"/api/grading/sessions/current?league_id=league&round_id={rid}",  # noqa: E731
                                      headers=AUTH)
    assert by_round(oc.ROUND_ID).json["session"]["session_id"] == first
    assert by_round(R4).json["session"]["session_id"] == second
    assert by_round("outlook-v9").status_code == 400 and by_round("outlook-v9").json["error"] == "invalid_round"
    post = client.post("/api/grading/sessions", json={"league_id": "league", "round_id": R4}, headers=AUTH)
    assert post.status_code == 200 and post.json["session"]["session_id"] == second
    bad = client.post("/api/grading/sessions", json={"league_id": "league", "round_id": "x"}, headers=AUTH)
    assert bad.status_code == 400 and bad.json["error"] == "invalid_round"


# -- two rounds, one pair, no crosstalk ---------------------------------------------------

def test_both_rounds_open_for_one_pair_without_touching_each_other(client, flags):
    flags["grading.revision4_round"] = True
    first, _ = build()
    expose(first)
    one = db.load_grading_cards(first)[0]
    db.answer_grading_card(one["card_id"], "account", grade=2, skipped=False, tags_json="[]",
                           now="2026-11-10T00:00:01+00:00")
    before = current_round_rows()
    second, _ = build(round_id=R4)
    assert db.load_grading_session(first)["status"] == db.load_grading_session(second)["status"] == "open"
    for card in db.load_grading_cards(second):
        r = client.post(f"/api/grading/cards/{card['card_id']}", json={"grade": 5}, headers=AUTH)
        assert r.status_code == 200 and r.json["session_id"] == second
    assert db.load_grading_session(second)["status"] == "completed"
    assert current_round_rows() == before  # the first round's session and cards, byte for byte
    assert client.get(f"/api/grading/sessions/{first}/results", headers=AUTH).json["error"] == "session_incomplete"
    first_report = oc.report(include_open=True)
    second_report = oc.report(include_open=True, round_id=R4)
    assert first_report["round_id"] == oc.ROUND_ID and second_report["round_id"] == R4
    assert first_report["partial"]["sessions"] == 1 and first_report["completed"]["sessions"] == 0
    assert first_report["partial"]["answered_observations"] == 1
    assert second_report["completed"]["sessions"] == 1 and "partial" in second_report
    assert second_report["model_versions"] == {"current": V2, "value_core": V4}
    assert set(second_report["completed"]["arms"]) == {V2, V4}
    assert second_report["completed"]["arms"][V4]["mean"] == 5
    assert second_report["completed"]["answered_observations"] == 21


def test_admin_report_per_round(client, flags):
    flags["grading.revision4_round"] = True
    build(round_id=R4)
    one = client.get(f"/api/admin/grading/report?round_id={oc.ROUND_ID}&include_open=1", headers=CRON)
    two = client.get(f"/api/admin/grading/report?round_id={R4}&include_open=1", headers=CRON)
    assert one.status_code == two.status_code == 200
    assert one.json["round_id"] == oc.ROUND_ID and two.json["round_id"] == R4
    assert one.json["inventory_totals"]["total"] == 0 and two.json["inventory_totals"]["total"] == 21
    assert two.json["model_versions"]["value_core"] == V4
    # Readable after rollback, like every Calibration report.
    flags["grading.revision4_round"] = False
    assert client.get(f"/api/admin/grading/report?round_id={R4}", headers=CRON).status_code == 200
    assert client.get(f"/api/admin/grading/report?round_id={R4}").status_code == 401


# -- pre-generation never touches the current round ----------------------------------------

def test_pregenerating_the_new_round_leaves_current_decks_byte_identical(client, flags):
    done, _ = build("account")
    expose(done)
    answer_all(done)
    started, _ = build("account-1")
    expose(started)
    first = db.load_grading_cards(started)[0]
    db.answer_grading_card(first["card_id"], "account-1", grade=3, skipped=False, tags_json='["overpay"]',
                           now="2026-11-10T00:00:02+00:00")
    assert db.load_grading_session(done)["status"] == "completed"
    assert db.load_grading_session(started)["status"] == "open"
    before = current_round_rows()
    flags["grading.revision4_round"] = True
    queued = client.post("/api/admin/grading/pregenerate", json={"round_id": R4, "offset": 0, "limit": 100},
                         headers=CRON)
    assert queued.status_code == 202, queued.json
    assert queued.json["round_id"] == R4 and queued.json["batch_status_counts"] == {"building": 2}
    assert queued.json["next_offset"] is None
    frozen, _ = frozen_factory()
    assert oc.drain_queue(capture=lambda **k: frozen, round_id=R4)["processed"] == 2
    gs = db.grading_sessions_table
    with db.engine.connect() as conn:
        new = conn.execute(select(gs.c.user_id, gs.c.status).where(gs.c.round_id == R4)).all()
    assert sorted(new) == [("account", "open"), ("account-1", "open")]
    assert current_round_rows() == before
    # Re-running the command resumes, never rebuilds.
    again = client.post("/api/admin/grading/pregenerate", json={"round_id": R4}, headers=CRON)
    assert again.json["batch_status_counts"] == {"open": 2}
    assert current_round_rows() == before


def test_turning_the_round_on_never_retires_an_unexposed_current_deck(engine, flags):  # noqa: F811
    # WS1's additive arm would retire this deck (built without revision 4) on its next
    # start. With the round on, the arm is superseded and inert: the deck is resumed.
    sid, _ = build()
    before = current_round_rows()
    flags["grading.revision4_arm"] = True
    flags["grading.revision4_round"] = True
    again = oc.start_session(user_id="account", league_user_id="seat", league_id="league")
    assert again["resumed"] and again["session"]["session_id"] == sid
    assert current_round_rows() == before
    assert not oc.revision4_enabled()


# -- off is today's behaviour --------------------------------------------------------------

def test_flag_off_is_todays_behaviour(client, flags, monkeypatch):
    first, _ = build()
    answer_all(first)
    looked = []
    real = db.load_open_grading_session
    monkeypatch.setattr(db, "load_open_grading_session",
                        lambda *a, **k: looked.append(k.get("statuses")) or real(*a, **k))
    assert oc.default_round(user_id="account", league_id="league", requested="anything") is None
    assert looked == []  # no extra read with the flag off
    current = client.get("/api/grading/sessions/current?league_id=league", headers=AUTH)
    assert current.status_code == 200 and current.json == {"session": None}
    for body in ({"league_id": "league"}, {"league_id": "league", "round_id": R4}):
        start = client.post("/api/grading/sessions", json=body, headers=AUTH)
        assert start.status_code == 200 and start.json["session"]["session_id"] == first
        assert start.json["session"]["status"] == "completed"
    explicit = client.get(f"/api/grading/sessions/current?league_id=league&round_id={R4}", headers=AUTH)
    assert explicit.status_code == 200 and explicit.json == {"session": None}
    refused = client.post("/api/admin/grading/pregenerate", json={"round_id": R4}, headers=CRON)
    assert refused.status_code == 400 and refused.json == {"error": "invalid_round"}
    with pytest.raises(bg.GradingError) as err:
        oc.pregenerate(round_id=R4)
    assert err.value.code == "round_disabled"
    assert round_ids() == [oc.ROUND_ID]
    assert oc._build_rounds() == [oc.ROUND_ID]


def test_rollback_pauses_unopened_revision_4_decks_and_keeps_visible_ones(client, flags):
    flags["grading.revision4_round"] = True
    unopened, _ = build("account", round_id=R4)
    visible, _ = build("account-1", round_id=R4)
    expose(visible)
    flags["grading.revision4_round"] = False
    paused = client.get(f"/api/grading/sessions/{unopened}/next", headers=AUTH)
    assert paused.status_code == 409 and paused.json["error"] == "round_paused"
    assert db.load_grading_session(unopened)["first_exposed_at"] is None
    server._sessions[TOKEN]["user_id"] = "account-1"
    card = client.get(f"/api/grading/sessions/{visible}/next", headers=AUTH)
    assert card.status_code == 200 and not card.json["done"]
    saved = client.post(f"/api/grading/cards/{card.json['card']['card_id']}", json={"grade": 5}, headers=AUTH)
    assert saved.status_code == 200


# -- worker, leases, deletion --------------------------------------------------------------

def test_worker_drains_each_enabled_round_under_its_own_lease(engine, flags, monkeypatch):  # noqa: F811
    drained, launched = [], []
    monkeypatch.setattr(oc, "drain_queue", lambda **k: drained.append(k) or {"processed": 0})
    monkeypatch.setattr(oc, "_launch_worker_locked", lambda: launched.append(True))
    oc._worker_main()
    assert drained == [{}]
    flags["grading.revision4_round"] = True
    oc._worker_main()
    assert drained == [{}, {}, {"round_id": R4}]
    flags["grading.outlook_round"] = False
    oc._worker_main()
    assert drained[-1] == {"round_id": R4} and len(drained) == 4
    assert launched == []


def test_a_foreign_current_round_lease_does_not_block_the_new_round(engine, flags):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    flags["grading.revision4_round"] = True
    with db.engine.begin() as conn:
        conn.execute(db.grading_build_leases_table.insert().values(
            lease_key=oc.ROUND_ID, token="other-process",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))
    sid = oc.start_session(user_id="account", league_user_id="seat", league_id="league",
                           round_id=R4)["session"]["session_id"]
    frozen, _ = frozen_factory()
    assert oc.drain_queue(capture=lambda **k: frozen) == {"busy": True}
    assert oc.drain_queue(capture=lambda **k: frozen, round_id=R4)["processed"] == 1
    assert db.load_grading_session(sid)["status"] == "open"


def test_participant_deletion_discards_the_revision_4_snapshot(engine, flags):  # noqa: F811
    from backend import deletion_scrub as scrub
    flags["grading.revision4_round"] = True
    sid, _ = build(round_id=R4)
    row = db.load_grading_session(sid)
    source = json.loads(row["source_json"])
    source["snapshot"]["members"] = {"partner": {"private_board": {"WR": 1900}}}
    with engine.begin() as conn:
        conn.execute(db.grading_sessions_table.update().where(db.grading_sessions_table.c.session_id == sid)
                     .values(source_json=json.dumps(source)))
        scrub._redact_grading_source(conn, {**row, "source_json": json.dumps(source)},
                                     SimpleNamespace(ids={"partner"}, token="deleted-token"))
    after = json.loads(db.load_grading_session(sid)["source_json"])
    assert after["replay_invalidated"] == "participant_deleted"
    assert "snapshot" not in after and "proofs" not in after
