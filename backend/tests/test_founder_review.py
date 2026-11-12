"""Founders' review: label overrides, their engine seam, and the founder-only routes.

docs/plans/founder-review/design.md (§2.1 the rule table, §4 the seam and digest, §5 access).
The pure rules run on synthetic leagues and on the committed fixture league; the routes and
the worker run on the season-signal worker harness (forecast faked at its read seams, an
isolated SQLite engine). No network, no production database.
"""
import copy
import json

import pytest
from sqlalchemy import select

from backend import database as db, feature_flags as ff, founder_review, season_value as sv
from backend import server, trade_gen_bilateral_season as r5, trade_service as ts
from backend.eval.season_replay import fixture_evidence, fixture_world
from backend.tests.test_season_signal_worker import (  # noqa: F401
    FLAG, PPG, Forecast, evidence, harness, owner_harness, revision_5, run_record, stored_league, world)
from backend.tests.test_owner_generator_routes import ME, LEAGUE, rows, worker
from backend.tests.test_fair_packages import TOKEN

LABELS = ("cornerstone", "win_now", "rebuild", "depth")


# ── the rule table (design.md §2.1), on a synthetic league ─────────────────────
#
# Two teams, two RB slots each: the starter line is 10.0 (margin 0.5).
#   kid   20 ppg, 9000, age 22  -> starts, future 5000      -> cornerstone
#   old   20 ppg, 9000, age 29  -> starts, past the cliff   -> win_now
#   x, y  10 ppg (on the line)  -> borderline               -> no label
#   by     5 ppg, 2000, age 22  -> bench, young with value  -> rebuild
#   bo     5 ppg,  100, age 30  -> bench, old and cheap     -> depth
#   gone  no projection         -> no label; pick -> rebuild by rule

RB_PPG = {"kid": 20.0, "old": 20.0, "x": 10.0, "y": 10.0, "by": 5.0, "bo": 5.0}
ROSTERS = {"t1": ["kid", "x", "by", "pick1"], "t2": ["old", "y", "bo", "gone"]}
POSITION = {**dict.fromkeys(["kid", "old", "x", "y", "by", "bo", "gone"], "RB"), "pick1": "PICK"}
MARKET = {"kid": 9000.0, "old": 9000.0, "x": 500.0, "y": 500.0, "by": 2000.0, "bo": 100.0,
          "gone": 3000.0, "pick1": 800.0}
AGE = {"kid": 22, "old": 29, "x": 26, "y": 26, "by": 22, "bo": 30, "gone": 24, "pick1": None}


def rb_evidence(slots=("RB", "RB")):
    return {"state": "usable", "slots": list(slots), "players": {p: {"ppg": v, "games": 4} for p, v in RB_PPG.items()},
            "unprojected": ["gone"], "digest": "d0"}


def rb_profile(ev):
    return sv.league_profile(ev, rosters=ROSTERS, position=POSITION, market=MARKET, age=AGE)


ENGINE = {"kid": "cornerstone", "old": "win_now", "x": None, "y": None, "by": "rebuild", "bo": "depth",
          "gone": None, "pick1": "rebuild"}
# The rule (design.md §2.1, amended 2026-11-12): the override IS the label the engine
# uses, for a starter (kid, old), a bench player (by, bo), a borderline player (x) and an
# unprojected one (gone). Whether he starts, and his future value, never move.
CASES = ("kid", "old", "by", "bo", "x", "gone")


def test_the_synthetic_league_has_every_engine_case():
    prof = rb_profile(rb_evidence())
    assert prof["line"]["RB"] == 10.0
    assert {pid: item["label"] for pid, item in prof["players"].items()} == ENGINE
    assert all("engine_label" not in item for item in prof["players"].values())


@pytest.mark.parametrize("pid", CASES)
@pytest.mark.parametrize("override", LABELS)
def test_any_label_for_any_player(pid, override):
    """Sabotage: D-242's future-axis swap (`overridden_label` keeping the starts axis), or
    the `continue` that skipped overrides for an unprojected player."""
    ev = sv.with_label_overrides(rb_evidence(), [(pid, "all", override)])
    base, prof = rb_profile(rb_evidence())["players"][pid], rb_profile(ev)["players"][pid]
    assert prof["label"] == override
    assert prof["startable"] == base["startable"] and prof["future"] == base["future"]
    if override != ENGINE[pid]:
        assert prof["engine_label"] == ENGINE[pid]
    else:
        assert "engine_label" not in prof


def test_an_unprojected_players_override_joins_the_evidence():
    """Sabotage: keep only projected players in with_label_overrides (the old filter)."""
    ev = sv.with_label_overrides(rb_evidence(), [("gone", "all", "win_now")])
    assert ev["label_overrides"] == {"gone": {"label": "win_now", "scope": "all"}}
    assert ev["digest"] != rb_evidence()["digest"]
    prof = rb_profile(ev)["players"]["gone"]
    assert prof == {"label": "win_now", "future": None, "startable": None, "engine_label": None}


def test_a_pick_is_never_overridden():
    ev = copy.deepcopy(rb_evidence())
    ev["label_overrides"] = {"pick1": {"label": "depth", "scope": "all"}}
    assert rb_profile(ev)["players"]["pick1"]["label"] == "rebuild"


def test_an_override_never_moves_the_line_starters_or_other_players():
    plain = rb_profile(rb_evidence())
    moved = rb_profile(sv.with_label_overrides(rb_evidence(), [("kid", "all", "win_now")]))
    assert {k: moved[k] for k in ("line", "margin", "starters")} == {k: plain[k] for k in ("line", "margin", "starters")}
    assert {p: v for p, v in moved["players"].items() if p != "kid"} == {
        p: v for p, v in plain["players"].items() if p != "kid"}


# ── QB scope (operator ruling 2026-11-12) ──────────────────────────────────────

def qb_evidence(slots):
    return {"state": "usable", "slots": list(slots), "digest": "dq",
            "players": {"qa": {"ppg": 25.0, "games": 4}, "qb": {"ppg": 10.0, "games": 4}}, "unprojected": []}


def qb_profile(ev):
    return sv.league_profile(ev, rosters={"t1": ["qa"], "t2": ["qb"]}, position={"qa": "QB", "qb": "QB"},
                             market={"qa": 9000.0, "qb": 100.0}, age={"qa": 24, "qb": 35})


SINGLE, SUPERFLEX = ("QB",), ("QB", "SUPER_FLEX")


def test_the_superflex_test_is_the_repo_one():
    assert sv.qb_scope(["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"]) == "single_qb"
    assert sv.qb_scope(["QB", "RB", "SUPER_FLEX", "BN"]) == "superflex"
    assert sv.qb_scope(["QB", "QB", "RB"]) == "superflex"
    for slots in (["QB", "RB", "BN"], ["QB", "SUPER_FLEX"], ["QB", "QB"]):
        meta = {"roster_positions": slots, "scoring_settings": {}}
        assert (server._detect_scoring_format_from_meta(meta) == "sf_tep") == sv.is_superflex(slots)
    assert sv.override_scope("QB", SUPERFLEX) == "superflex" and sv.override_scope("RB", SUPERFLEX) == "all"


def test_a_superflex_qb_override_changes_superflex_leagues_only():
    """Sabotage: drop the scope check (in with_label_overrides and league_profile)."""
    rows_ = [("qa", "superflex", "win_now")]
    assert qb_profile(qb_evidence(SINGLE))["players"]["qa"]["label"] == "cornerstone"
    assert qb_profile(qb_evidence(SUPERFLEX))["players"]["qa"]["label"] == "cornerstone"
    sf = sv.with_label_overrides(qb_evidence(SUPERFLEX), rows_)
    assert qb_profile(sf)["players"]["qa"]["label"] == "win_now"
    single = qb_evidence(SINGLE)
    assert sv.with_label_overrides(single, rows_) is single
    assert qb_profile(sv.with_label_overrides(single, rows_))["players"]["qa"]["label"] == "cornerstone"
    # ...and a single-QB override the other way round.
    one = sv.with_label_overrides(qb_evidence(SINGLE), [("qa", "single_qb", "win_now")])
    assert qb_profile(one)["players"]["qa"]["label"] == "win_now"
    two = qb_evidence(SUPERFLEX)
    assert sv.with_label_overrides(two, [("qa", "single_qb", "win_now")]) is two


def test_league_profile_itself_refuses_a_scope_that_is_not_the_players():
    """A QB entry scoped `all`, or an RB entry scoped to a QB format, is ignored."""
    ev = qb_evidence(SUPERFLEX)
    ev["label_overrides"] = {"qa": {"label": "win_now", "scope": "all"}}
    assert qb_profile(ev)["players"]["qa"]["label"] == "cornerstone"
    ev = qb_evidence(SINGLE)
    ev["label_overrides"] = {"qa": {"label": "win_now", "scope": "superflex"}}
    assert qb_profile(ev)["players"]["qa"]["label"] == "cornerstone"
    rb = rb_evidence(("RB", "RB", "SUPER_FLEX"))
    rb["label_overrides"] = {"kid": {"label": "win_now", "scope": "superflex"}}
    assert rb_profile(rb)["players"]["kid"]["label"] == "cornerstone"


def test_rb_overrides_hold_in_both_formats():
    for slots in (("RB", "RB"), ("RB", "RB", "QB", "SUPER_FLEX")):
        ev = sv.with_label_overrides(rb_evidence(slots), [("kid", "all", "win_now")])
        assert rb_profile(ev)["players"]["kid"]["label"] == "win_now"


# ── byte-identical without overrides; the digest (design.md §4) ────────────────

@pytest.fixture(scope="module")
def fixture_ev():
    return fixture_evidence()


def _fixture_profile(ev):
    search = r5._Search(**fixture_world("championship"), season_evidence=ev)
    return search._profile


def test_no_override_rows_is_the_same_object_and_the_same_profile(fixture_ev):
    """Sabotage: always attach `label_overrides` (even empty) and re-digest."""
    assert sv.with_label_overrides(fixture_ev, []) is fixture_ev
    assert sv.with_label_overrides(fixture_ev, None) is fixture_ev
    elsewhere = [("not-in-this-league", "all", "win_now")]
    assert sv.with_label_overrides(fixture_ev, elsewhere) is fixture_ev
    before = json.dumps(_fixture_profile(fixture_ev), sort_keys=True)
    after = json.dumps(_fixture_profile(sv.with_label_overrides(fixture_ev, elsewhere)), sort_keys=True)
    assert before == after
    stale = sv.unavailable("stale")
    assert sv.with_label_overrides(stale, [("x", "all", "win_now")]) is stale


def test_the_digest_moves_with_an_override_that_can_matter(fixture_ev):
    unprojected = fixture_ev["unprojected"][0]
    assert sv.with_label_overrides(fixture_ev, [(unprojected, "all", "win_now")])["digest"] != fixture_ev["digest"]
    projected = sorted(fixture_ev["players"])[0]
    one = sv.with_label_overrides(fixture_ev, [(projected, "all", "win_now")])
    two = sv.with_label_overrides(fixture_ev, [(projected, "all", "cornerstone")])
    assert len({fixture_ev["digest"], one["digest"], two["digest"]}) == 3
    assert one["as_of"] == fixture_ev["as_of"] and one["label_overrides"] == {
        projected: {"label": "win_now", "scope": "all"}}
    again = sv.with_label_overrides(fixture_ev, [(projected, "all", "win_now"), ("elsewhere", "all", "depth")])
    assert again["digest"] == one["digest"]


def test_the_request_hash_follows_the_override_digest(world):
    from backend.tests.test_owner_generator_routes import context_for
    ctx = context_for(world)
    base = evidence()
    moved = sv.with_label_overrides(base, [("b1", "all", "cornerstone")])
    other_format = sv.with_label_overrides(base, [("b1", "superflex", "cornerstone")])
    hashes = [server._owner_selected_assignment(ctx, "organic", serve=True, season_evidence=e)["request_hash"]
              for e in (base, moved, other_format)]
    assert hashes[0] != hashes[1] and hashes[0] == hashes[2]


# ── overrides reach every consumer identically (design.md §4) ──────────────────

def test_overrides_reach_plan_fit_and_the_conflict_rule(fixture_ev):
    """A viewer bench player the engine calls depth becomes a rebuild piece: the
    Rebuilding mirror table and the conflict rule read it."""
    plain = r5._Search(**fixture_world("rebuilder"), season_evidence=fixture_ev)
    me = plain.teams[plain.user_id]
    depth = sorted((p for p in me["roster"] if plain._label(p) == "depth" and plain.market.get(p, 0) > 0),
                   key=lambda p: -plain.market[p])[0]
    win_now = min((p for team in plain.teams.values() for p in team["roster"] if plain._label(p) == "win_now"),
                  key=lambda p: (plain._profile["players"][p]["future"], p))
    ev = sv.with_label_overrides(fixture_ev, [(depth, "all", "rebuild")])
    moved = r5._Search(**fixture_world("rebuilder"), season_evidence=ev)
    assert moved._label(depth) == "rebuild" and plain._label(depth) == "depth"
    team = {**me, "outlook": "rebuilder"}
    assert plain._mirror_fit(team, depth) != moved._mirror_fit(team, depth)
    kwargs = dict(plan="rebuilder", declared=True, usable_evidence=True, receive=[win_now], give=[depth])
    assert sv.plan_conflict(profile=plain._profile, market=plain.market, **kwargs) is False
    assert sv.plan_conflict(profile=moved._profile, market=moved.market, **kwargs) == "label"


def test_overrides_reach_the_card_and_the_request_record(world, monkeypatch):
    """A revision 5 deck: the proof's asset labels (what season_block prints) and the
    recorded evidence carry the override; the request hash moves."""
    _, engine, *_ = world
    revision_5()
    ff._flags_cache[FLAG] = True
    Forecast(monkeypatch)
    plain = worker(world, monkeypatch)
    plain_hash = run_record(engine)["request_hash"]
    seen = len(rows(engine, db.deck_impressions_table))
    with engine.begin() as conn:
        conn.execute(db.founder_label_overrides_table.insert().values(
            player_id="b1", scope="all", label="cornerstone", set_by=ME, set_at="2026-11-11T00:00:00+00:00"))
    job = worker(world, monkeypatch)
    record = run_record(engine)
    assert record["request_hash"] != plain_hash
    assert record["season_evidence"]["label_overrides"] == {"b1": {"label": "cornerstone", "scope": "all"}}
    proofs = [json.loads(r["valuation_json"]) for r in rows(engine, db.deck_impressions_table)[seen:]]
    labelled = [a for p in proofs if "season_signal" in p for a in p["season_signal"].get("assets", ())
                if a["id"] == "b1"]
    assert labelled and {a["label"] for a in labelled} == {"cornerstone"}
    tags = [t for c in job["cards"] for t in (c.get("season_block") or {}).get("labels", ()) if t["id"] == "b1"]
    assert tags and all(t["label"] == "cornerstone" for t in tags)
    assert plain["cards"]


# ── the founder routes ─────────────────────────────────────────────────────────

@pytest.fixture
def founder(stored_league, monkeypatch):
    ff._flags_cache["founder.review"] = True
    monkeypatch.setenv("FOUNDER_ACCOUNTS", f"someone-else, {ME}")
    return stored_league


def H(**extra):
    return {"X-Session-Token": TOKEN, **extra}


def stored(engine):
    return sorted((r["player_id"], r["scope"], r["label"]) for r in rows(engine, db.founder_label_overrides_table))


def _engine():
    return db.engine


def test_the_capability_answers_a_founder_only(founder):
    assert founder.get("/api/founder/capability", headers=H()).json == {"founder_review": True}


@pytest.mark.parametrize("case", ["flag_off", "env_unset", "env_blank", "not_listed", "unverified",
                                  "demo", "no_token", "device_id", "body_identity"])
def test_access_is_refused_404_with_no_state_change(founder, monkeypatch, case):
    """Sabotage: drop the verified check, or read the allow-list against X-Device-Id."""
    sess = server._sessions[TOKEN]
    headers = H()
    if case == "flag_off":
        ff._flags_cache["founder.review"] = False
    elif case == "env_unset":
        monkeypatch.delenv("FOUNDER_ACCOUNTS")
    elif case == "env_blank":
        monkeypatch.setenv("FOUNDER_ACCOUNTS", " , ")
    elif case == "not_listed":
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "someone-else")
    elif case == "unverified":
        monkeypatch.setitem(sess, "verified", False)
    elif case == "demo":
        monkeypatch.setitem(sess, "user_id", "demo_user_1")
        monkeypatch.setitem(sess, "is_demo", True)
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "demo_user_1")
    elif case == "no_token":
        headers = {}
    elif case in ("device_id", "body_identity"):
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "the-founder")
        headers = H(**{"X-Device-Id": "the-founder", "X-User-Id": "the-founder"})
    body = {"league_id": LEAGUE, "set": {"b1": "cornerstone"},
            **({"user_id": "the-founder", "account_id": "the-founder"} if case == "body_identity" else {})}
    assert founder.get("/api/founder/capability", headers=headers).status_code == 404
    assert founder.get(f"/api/founder/labels?league_id={LEAGUE}", headers=headers).status_code == 404
    response = founder.post("/api/founder/labels", json=body, headers=headers)
    assert response.status_code == 404 and response.json == {"error": "not_found"}
    assert stored(_engine()) == []


def test_the_page_lists_every_rostered_player_with_what_to_judge_by(founder):
    body = founder.get(f"/api/founder/labels?league_id={LEAGUE}", headers=H()).json
    assert body["schema"] == founder_review.SCHEMA
    assert body["bands"] == ["cornerstone", "win_now", "rebuild", "depth", "none"]
    assert body["labels"] == list(LABELS) and body["qb_scope"] == "single_qb"
    assert body["evidence"]["state"] == "usable" and body["line"]["RB"] == 7.5
    by_id = {r["id"]: r for r in body["players"]}
    assert set(by_id) == {"a1", "a2", "a3", "b1", "b2", "b3", "b4", "b5", "c1", "c2"}
    b1 = by_id["b1"]
    assert {k: b1[k] for k in ("name", "position", "team", "age", "ppg", "line", "label", "engine_label",
                               "override", "startable", "movable_to", "why_unlabelled")} == {
        "name": "B1", "position": "RB", "team": "AAA", "age": 25, "ppg": 16.0, "line": 7.5,
        "label": "win_now", "engine_label": "win_now", "override": None, "startable": True,
        "movable_to": list(LABELS), "why_unlabelled": None}
    assert b1["value"] > 0
    assert by_id["b4"]["label"] is None and by_id["b4"]["why_unlabelled"] == "borderline"
    # Any label for any player (amended 2026-11-12): build 187 enables its chips from this.
    assert all(r["movable_to"] == list(LABELS) for r in body["players"])
    assert by_id["a3"]["label"] == "depth"
    assert body["summary"]["positions"]["RB"] == {"moved": 0, "corrections": []}
    for private in (ME, "user_opp", LEAGUE):
        assert f'"{private}"' not in json.dumps(body["summary"])


def test_set_clear_and_idempotent(founder):
    """Sabotage: rewrite set_at on an unchanged label."""
    engine = _engine()
    post = lambda body: founder.post("/api/founder/labels", json={"league_id": LEAGUE, **body}, headers=H())
    first = post({"set": {"b1": "cornerstone", "a3": "rebuild"}})
    assert first.status_code == 200 and first.json["set"] == 2 and first.json["overrides_total"] == 2
    assert stored(engine) == [("a3", "all", "rebuild"), ("b1", "all", "cornerstone")]
    stamp = {r["player_id"]: (r["set_at"], r["set_by"]) for r in rows(engine, db.founder_label_overrides_table)}
    assert stamp["b1"][1] == ME
    again = post({"set": {"b1": "cornerstone", "a3": "rebuild"}})
    assert again.json["set"] == 0 and again.json["cleared"] == 0
    assert {r["player_id"]: (r["set_at"], r["set_by"]) for r in rows(engine, db.founder_label_overrides_table)} == stamp
    page = founder.get(f"/api/founder/labels?league_id={LEAGUE}", headers=H()).json
    by_id = {r["id"]: r for r in page["players"]}
    assert (by_id["b1"]["label"], by_id["b1"]["engine_label"], by_id["b1"]["override"]) == (
        "cornerstone", "win_now", "cornerstone")
    assert (by_id["a3"]["label"], by_id["a3"]["engine_label"]) == ("rebuild", "depth")
    assert page["summary"]["positions"]["RB"] == {"moved": 2, "corrections": [
        {"from": "depth", "to": "rebuild", "count": 1}, {"from": "win_now", "to": "cornerstone", "count": 1}]}
    assert page["summary"]["overrides_total"] == 2 and page["summary"]["overrides_here"] == 2
    cleared = post({"clear": ["b1"], "set": {"a3": "depth"}})
    assert cleared.json == {"set": 1, "cleared": 1, "overrides_total": 1}
    assert stored(engine) == [("a3", "all", "depth")]
    assert post({"clear": ["b1"]}).json["cleared"] == 0


@pytest.mark.parametrize("body,code", [
    ({"set": {"b1": "superstar"}}, "unknown_label"),
    ({"set": {"b1": None}}, "unknown_label"),
    ({"set": {"nobody": "win_now"}}, "unknown_player"),
    ({"clear": ["nobody"]}, "unknown_player"),
    ({"set": {"b1": "win_now"}, "clear": ["b1"]}, "set_and_clear_overlap"),
    ({"set": ["b1"]}, "set_must_be_an_object_and_clear_a_list"),
])
def test_writes_are_validated_against_the_vocabulary_and_the_pool(founder, body, code):
    """Sabotage: accept any label string."""
    response = founder.post("/api/founder/labels", json={"league_id": LEAGUE, **body}, headers=H())
    assert response.status_code == 400 and response.json["error"] == code
    assert stored(_engine()) == []


def test_picks_are_refused_and_a_write_needs_a_league_and_a_forecast(founder, monkeypatch):
    known = {"p1": "PICK", "q": "QB"}
    with pytest.raises(founder_review.InvalidRequest) as err:
        founder_review.parse_write({"set": {"p1": "rebuild"}}, known=known, stored=set(), slots=["QB"])
    assert err.value.code == "unknown_player" and err.value.ids == ["p1"]
    assert founder.post("/api/founder/labels", json={"set": {}}, headers=H()).status_code == 400
    Forecast(monkeypatch, state="stale")
    response = founder.post("/api/founder/labels", json={"league_id": LEAGUE, "set": {"b1": "win_now"}}, headers=H())
    assert response.status_code == 409 and response.json["reason"] == "stale"
    page = founder.get(f"/api/founder/labels?league_id={LEAGUE}", headers=H()).json
    assert page["players"] == [] and page["evidence"]["reason"] == "stale"
    assert stored(_engine()) == []


def test_a_qb_write_takes_the_leagues_qb_format():
    known = {"q": "QB", "r": "RB"}
    to_set, to_clear = founder_review.parse_write(
        {"set": {"q": "win_now", "r": "depth"}, "clear": ["gone"]}, known=known,
        stored={("gone", "superflex"), ("gone", "single_qb")}, slots=["QB", "SUPER_FLEX", "RB"])
    assert to_set == {("q", "superflex"): "win_now", ("r", "all"): "depth"}
    assert to_clear == [("gone", "superflex")]
    to_set, _ = founder_review.parse_write({"set": {"q": "win_now"}}, known=known, stored=set(), slots=["QB", "RB"])
    assert to_set == {("q", "single_qb"): "win_now"}


def test_the_admin_route_reads_the_same_label(founder):
    founder.post("/api/founder/labels", json={"league_id": LEAGUE, "set": {"b1": "cornerstone"}}, headers=H())
    admin = founder.get(f"/api/admin/season-signal/labels?user_id={ME}&league_id={LEAGUE}",
                        headers={"X-Cron-Secret": "s3cret"}).json
    page = founder.get(f"/api/founder/labels?league_id={LEAGUE}", headers=H()).json
    admin_labels = {p["id"]: p["label"] for p in admin["players"]}
    assert admin_labels["b1"] == "cornerstone"
    assert admin_labels == {r["id"]: r["label"] for r in page["players"]}


def test_any_label_for_a_starter_a_bench_borderline_and_unprojected_player(founder, monkeypatch):
    """Amended 2026-11-12 (the operator: "remove the controls limiting which label I can
    assign"). Starter b1 (win_now) -> depth, bench a3 (depth) -> cornerstone, borderline
    b4 -> win_now, unprojected c2 -> rebuild: stored, read back, honoured by the label the
    engine uses (the page and the admin route both read the profile), summary counts add
    up; moving each back to the engine's label (a clear) restores the engine's labels.
    Sabotages: the old future-axis swap; the projected-only filter in with_label_overrides;
    `why_unlabelled` from the effective label; the summary's None -> "none"."""
    Forecast(monkeypatch, built=evidence({k: v for k, v in PPG.items() if k != "c2"}, unprojected=["c2"]))
    engine = _engine()
    url = f"/api/founder/labels?league_id={LEAGUE}"
    before = {r["id"]: r for r in founder.get(url, headers=H()).json["players"]}
    assert (before["b1"]["label"], before["b1"]["startable"]) == ("win_now", True)
    assert (before["a3"]["label"], before["a3"]["startable"]) == ("depth", False)
    assert (before["b4"]["label"], before["b4"]["why_unlabelled"]) == (None, "borderline")
    assert (before["c2"]["label"], before["c2"]["why_unlabelled"], before["c2"]["ppg"]) == (None, "unprojected", None)
    calls = {"b1": "depth", "a3": "cornerstone", "b4": "win_now", "c2": "rebuild"}
    response = founder.post("/api/founder/labels", json={"league_id": LEAGUE, "set": calls}, headers=H())
    assert response.status_code == 200 and response.json["set"] == 4
    assert stored(engine) == sorted((pid, "all", label) for pid, label in calls.items())
    page = founder.get(url, headers=H()).json
    after = {r["id"]: r for r in page["players"]}
    for pid, label in calls.items():
        row = after[pid]
        assert (row["label"], row["override"], row["engine_label"]) == (label, label, before[pid]["label"])
        assert row["startable"] == before[pid]["startable"] and row["future"] == before[pid]["future"]
        assert row["why_unlabelled"] == before[pid]["why_unlabelled"]   # still why the ENGINE has none
    assert {pid: r["label"] for pid, r in after.items() if pid not in calls} == {
        pid: r["label"] for pid, r in before.items() if pid not in calls}
    moved = {pos: v["moved"] for pos, v in page["summary"]["positions"].items()}
    assert sum(moved.values()) == 4 and page["summary"]["overrides_here"] == 4
    for pos, block in page["summary"]["positions"].items():
        assert sum(c["count"] for c in block["corrections"]) == block["moved"]
        assert all(c["from"] in founder_review.BANDS and c["to"] in founder_review.BANDS
                   for c in block["corrections"])
    pairs = {(c["from"], c["to"]) for block in page["summary"]["positions"].values() for c in block["corrections"]}
    assert {("win_now", "depth"), ("depth", "cornerstone"), ("none", "win_now"), ("none", "rebuild")} == pairs
    admin = founder.get(f"/api/admin/season-signal/labels?user_id={ME}&league_id={LEAGUE}",
                        headers={"X-Cron-Secret": "s3cret"}).json
    assert {p["id"]: p["label"] for p in admin["players"]} == {pid: r["label"] for pid, r in after.items()}
    # Back to the engine's label (for b4 / c2: no label) = clear: the engine's labels return.
    cleared = founder.post("/api/founder/labels", json={"league_id": LEAGUE, "clear": sorted(calls)}, headers=H())
    assert cleared.json == {"set": 0, "cleared": 4, "overrides_total": 0}
    page = founder.get(url, headers=H()).json
    assert {r["id"]: (r["label"], r["engine_label"], r["override"]) for r in page["players"]} == {
        pid: (r["label"], r["engine_label"], None) for pid, r in before.items()}
    assert all(v["moved"] == 0 for v in page["summary"]["positions"].values())


# ── downstream consumers when a label disagrees with `startable` (2026-11-12) ──
#
# On the fixture league: every rostered QB/RB/WR/TE gets a label that disagrees with
# whether he starts (a starter -> rebuild / depth, a bench player -> cornerstone /
# win_now), borderline players and unprojected players get labels too. Each consumer
# must read the founder's label without raising, and nothing about who starts moves.

def _adversarial(ev, world_kwargs):
    plain = r5._Search(**world_kwargs, season_evidence=ev)
    calls = []
    for i, (pid, info) in enumerate(sorted(plain._profile["players"].items())):
        if plain._position(pid) not in sv.POSITIONS:
            continue
        pick = (("rebuild", "depth") if info["startable"] is True else
                ("cornerstone", "win_now") if info["startable"] is False else LABELS)[i % (2 if info["startable"] is not None else 4)]
        calls.append((pid, sv.override_scope(plain._position(pid), ev["slots"]), pick))
    return plain, dict((pid, label) for pid, _, label in calls), sv.with_label_overrides(ev, calls)


@pytest.mark.parametrize("outlook", ["championship", "rebuilder", "jets"])
def test_consumers_read_a_label_that_disagrees_with_startable(fixture_ev, outlook):
    """`_season_lean` (win-now team), `_mirror_parts` / `_shed_plan_asset` (the label fit),
    `_older_producer` / `_sell_share` (the sell bonus), `plan_conflict`. Sabotage: make
    `SeasonLayer._label` (what they all read) return the engine's label (`engine_label`)."""
    world_kwargs = fixture_world(outlook)
    plain, calls, ev = _adversarial(fixture_ev, world_kwargs)
    moved = r5._Search(**world_kwargs, season_evidence=ev)
    unprojected = [p for p in calls if p not in moved._season_ppg]
    disagree = [p for p in calls if p in moved._season_ppg and plain._profile["players"][p]["startable"] is not None]
    assert unprojected and disagree
    for pid, label in calls.items():
        info, base = moved._profile["players"][pid], plain._profile["players"][pid]
        assert info["label"] == label
        assert (info["startable"], info["future"]) == (base["startable"], base["future"])
    me = moved.teams[moved.user_id]
    team = {**me, "outlook": outlook if outlook != "championship" else "rebuilder"}
    for pid in calls:
        assert moved.starts_for(me, pid) == plain.starts_for(me, pid)   # who starts never moves
        lean = moved._season_lean(me, pid)
        if pid not in moved._season_ppg:
            assert lean is None             # unprojected: today's age rule, the label claims nothing
        elif not moved.starts_for(me, pid):
            assert lean == r5.LEAN_BENCH
        else:
            assert lean == (r5.LEAN_STARTS_LABELLED if calls[pid] in ("win_now", "cornerstone") else r5.LEAN_STARTS)
        fit, how = moved._mirror_parts(team, pid)
        if how not in ("board", "pick"):
            expected_how = {"rebuild": "rebuild", "win_now": "win_now", "depth": None,
                            "cornerstone": "cornerstone_young" if sv.young(moved._position(pid),
                                                                          moved.players[pid].age)
                            else "cornerstone_old"}[calls[pid]]
            assert how == expected_how and (fit is None) == (expected_how is None)
        assert moved._older_producer(team, pid) == (how in r5.NEVER_MILDER)
    give = sorted(p for p in me["roster"] if p in calls)[:2]
    receive = [p for p in unprojected if p not in me["roster"]][:1] or unprojected[:1]
    share = moved._sell_share(team, give, receive)
    assert -1.0 <= share <= 1.0
    # plan_conflict: an unprojected incoming player's future counts as his market value.
    players, top = moved._profile["players"], receive[0]
    expect = (calls[top] == "win_now" and any(calls[p] in ("rebuild", "cornerstone") for p in give)
              and moved.market[top] < sum(players[p]["future"] if players[p]["future"] is not None
                                          else moved.market[p] for p in give))
    got = sv.plan_conflict(plan="rebuilder", declared=True, usable_evidence=True,
                           receive=receive, give=give, profile=moved._profile, market=moved.market)
    assert got == ("label" if expect else False)


@pytest.mark.parametrize("outlook,matching", [("championship", None), ("rebuilder", None), ("jets", None),
                                              ("contender", 1.0)])
def test_a_whole_deck_with_disagreeing_labels_runs_and_prints_the_founders_labels(fixture_ev, outlook, matching):
    """Revision 5 end to end (label fit, sell bonus, partner matching in stage 2, the card's
    season block) on the adversarial overrides: no exception; every proof's asset label is
    the founder's; the season block prints a label only for a projected asset, and prints
    the founder's. Sabotage: print `engine_label` in `_season_signal`'s assets."""
    from backend import trade_narrative as tn
    world_kwargs = fixture_world(outlook)
    _, calls, ev = _adversarial(fixture_ev, world_kwargs)
    config = {} if matching is None else {r5.MATCHING_KEY: matching}
    cards, _ = r5.generate_bilateral_trades(**world_kwargs, season_evidence=ev, config=config)
    assert cards
    printed = 0
    for card in cards:
        proof = card.owner_evaluation.as_dict()
        for asset in proof["season_signal"]["assets"]:
            if asset["id"] in calls:
                assert asset["label"] == calls[asset["id"]]
        block = tn.season_block(proof, card, world_kwargs["players"])
        for tag in (block or {}).get("labels", ()):
            printed += 1
            assert tag["label"] == calls[tag["id"]] and tag["id"] in ev["players"]
    if outlook != "contender":
        assert printed     # the block was built (season_block swallows errors into None)


# ── pins ───────────────────────────────────────────────────────────────────────

def test_the_pipeline_version_is_pinned_for_the_override_seam():
    """Sabotage: forget the bump."""
    assert server.DECK_PIPELINE_VERSION >= 28 and server.DECK_PIPELINE_PINS[28] == "f9dc5f829bcd9a92"


def test_the_flag_defaults_off_in_code_and_ships_on():
    assert ff.DEFAULT_FLAGS["founder.review"] is False
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for rel in ("config/features.json", "backend/tests/fixtures/flags/release.json",
                "backend/tests/fixtures/flags/onboarding-v2.json", "backend/tests/fixtures/flags/profiles-on.json"):
        # Shipped on: the page is still inert until FOUNDER_ACCOUNTS names an account.
        assert json.loads((root / rel).read_text())["founder.review"] is True, rel


def test_the_vocabulary_is_one_definition():
    assert founder_review.LABELS == sv.OVERRIDE_LABELS == LABELS
    assert founder_review.BANDS == (*LABELS, "none")
    assert sv.OVERRIDE_SCOPES == ("all", "superflex", "single_qb")


def test_account_deletion_keeps_the_judgment_and_drops_who_set_it(founder):
    from backend import accounts
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(db.founder_label_overrides_table.insert().values(
            player_id="b1", scope="all", label="win_now", set_by=ME, set_at="2026-11-11T00:00:00+00:00"))
        conn.execute(db.founder_label_overrides_table.insert().values(
            player_id="b2", scope="all", label="win_now", set_by="kept", set_at="2026-11-11T00:00:00+00:00"))
    accounts.delete_user_data(ME)
    with engine.connect() as conn:
        left = {r.player_id: r.set_by for r in conn.execute(select(db.founder_label_overrides_table))}
    assert left == {"b1": accounts.DELETED_USER_PLACEHOLDER, "b2": "kept"}
