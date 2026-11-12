"""A league-mate's assumed outlook from the saved playoff forecast
(flag trade.partner_outlook_projection; docs/plans/league-projections/partner-outlook-scope.md).

The operator, 2026-11-12: "Assumed team outlooks should use our projections for
non app users. For example paulsmenis is shown as 'looks contending' when he
has almost no chance to make the playoffs". Covers:

- the two bands: 3% and exactly 45% are `rebuilder`, 46% is `contender`, on
  the unrounded probability; never Tanking or All-in for an assumed outlook;
- precedence per league-mate: a saved outlook always wins, then the projection
  read, then the roster read; the viewer is not touched;
- usability is `recommendation.unusable_reason` (current, complete, current
  model): stale, incomplete, old model, no run, refresh failed, a pending run,
  an unsupported policy, a non-Sleeper or non-numeric league all keep the
  roster read for everyone with no error; a read failure keeps it and logs one
  line;
- the roster→owner mapping goes through `sleeper_roster.owns_roster`: a
  co-owner is an alias of the primary owner; a member with no roster, two
  rosters, or a roster with no probability keeps the roster read;
- one forecast read per job, none per league-mate; a request's read rides the
  preload into the worker;
- the engine's partner input, the fit block's "Them" tag and Team Review's
  partner groups agree for the same undeclared team; the tag carries
  wire `source: "roster"` (installed builds keep it) with the projection read's text; the request evidence and
  the proof record the source;
- caching: the read is in the trade request signature, so a deck, stored page
  or prepared inventory built under other reads is not served as current;
- flag off: byte-identical (preload, context, request hash, cards, fit
  context, Team Review rows);
- rules-first: page = gated full solve with projection-based partner outlooks
  in the context.
"""
import copy
import json
import logging
import math

import pytest

from backend import database as db, feature_flags as ff, partner_outlook as po, server
from backend import team_review, trade_gen_owner as owner, trade_narrative as tn, trade_service as ts
from backend.league_projections import batch, recommendation
from backend.league_projections.core import VERSION
from backend.tests.test_fair_packages import harness, LEAGUE, ME, OPP, OPP2, SEED, TOKEN  # noqa: F401
from backend.tests.test_league_projection_outlook import review, saved, seed, seed_runs  # noqa: F401
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401
from backend.tests.test_owner_trade_block import ME_BOARD, OPP_BOARD
from backend.tests.test_owner_generator_routes import assign, owner_harness, worker  # noqa: F401

ABOVE = lambda value: math.nextafter(value, 1)  # noqa: E731
FLAGS = ("trade.partner_outlook_projection", "league.projections")
SESSION_READS = po.session_reads
INDEX = {"league_id": LEAGUE, "rosters": [[1, ME, []], [2, OPP, []], [3, OPP2, []]]}


@pytest.fixture(autouse=True)
def fresh_parse_cache():
    po._PARSED.clear()
    yield
    po._PARSED.clear()


def forecast(**probabilities):
    """A usable forecast keyed by roster id (as `read_forecast` returns it)."""
    return {"captured_at": "2026-11-10T15:00:00+00:00",
            "probabilities": {str(k): v for k, v in probabilities.items()}}


def flags_on(on=True):
    for key in FLAGS:
        ff._flags_cache[key] = on


def counting_reader(monkeypatch, value):
    calls = []

    def read(user_id, league_id, *, platform="sleeper"):
        calls.append((user_id, league_id))
        return copy.deepcopy(value)
    monkeypatch.setattr(po, "read_forecast", read)
    return calls


# ── The bands ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("probability,outlook", [
    (.03, "rebuilder"), (0, "rebuilder"), (.45, "rebuilder"), (ABOVE(.45), "contender"),
    (.46, "contender"), (.99, "contender"), (1, "contender"),
    (None, None), (float("nan"), None), (1.2, None), (True, None)])
def test_two_bands_cut_at_45_percent_unrounded(probability, outlook):
    """Sabotage `cut at >= 45%` (`< REBUILDING_MAX`): exactly 45% reads contender."""
    assert po.assumed_from_probability(probability) == outlook


def test_an_assumed_outlook_is_never_an_extreme():
    """Sabotage `four bands` (`recommendation.classify`): 3% reads jets, 99% championship."""
    grid = [i / 1000 for i in range(1001)] + [ABOVE(.15), ABOVE(.75)]
    assert {po.assumed_from_probability(p) for p in grid} == {"rebuilder", "contender"}


# ── Usability: the saved run, through recommendation.unusable_reason ───────

def partner_result(**changes):
    return saved(.6, **{"teams": [{"roster_id": 1, "playoff_probability": .6},
                                  {"roster_id": 2, "playoff_probability": .03}], **changes})


def test_a_usable_saved_forecast_gives_every_roster_s_probability(client, engine):
    seed(engine, partner_result())
    assert po.read_forecast("account", "123") == {
        "captured_at": "2026-11-10T15:00:00+00:00", "probabilities": {"1": .6, "2": .03}}


@pytest.mark.parametrize("case", ["stale", "incomplete", "old_model", "no_run", "refresh_failed",
                                  "pending", "unsupported", "non_sleeper", "non_numeric"])
def test_an_unusable_forecast_keeps_the_roster_read_for_everyone(client, engine, monkeypatch, case):
    """Sabotage `use a stale forecast` (skip `unusable_reason`): every case reads."""
    league, platform = "123", "sleeper"
    if case == "stale":
        seed(engine, partner_result(), age_days=8)
    elif case == "incomplete":
        seed(engine, partner_result(coverage={"estimate_status": "incomplete"}))
    elif case == "old_model":
        seed(engine, partner_result(model_version="joint-season-scenario-v4"))
    elif case == "refresh_failed":
        seed_runs(engine, partner_result(), ("failed", "provider_error"))
    elif case == "pending":
        seed_runs(engine, partner_result(), ("queued", None))
    elif case == "unsupported":
        seed(engine, partner_result())
        monkeypatch.setattr(batch, "is_enabled", lambda key: key != "league.projections_provider_approved")
    elif case == "non_sleeper":
        seed(engine, partner_result())
        platform = "espn"
    elif case == "non_numeric":
        seed(engine, partner_result())
        league = "league_x"
    assert po.read_forecast("account", league, platform=platform) is None
    rosters = [[1, "viewer", []], [2, "paul", []]]
    assert po.projection_reads(po.read_forecast("account", league, platform=platform), rosters, ["paul"]) == {}


def test_a_read_failure_keeps_the_roster_read_and_logs_one_line(monkeypatch, caplog):
    def broken(*a):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(batch, "view", broken)
    with caplog.at_level(logging.WARNING, logger="backend.partner_outlook"):
        assert po.read_forecast("account", "123") is None
    assert len([r for r in caplog.records if r.name == "backend.partner_outlook"]) == 1


def test_build_and_the_partner_reader_share_one_usability_definition():
    """The viewer's suggestion is unchanged by the extraction (D-230)."""
    for state, result in [("stale", saved()), ("current", saved(coverage={})), ("unsupported_policy", saved()),
                          ("queued", None), ("current", saved(model_version="v4"))]:
        block = recommendation.build(state, result, None, (.15, .75))
        assert block["reason"] == recommendation.unusable_reason(state, result)
    assert recommendation.build("unsupported_policy", saved(), None, (.15, .75))["captured_at"] is None
    assert recommendation.unusable_reason("current", saved()) is None


# ── The mapping ────────────────────────────────────────────────────────────

def test_a_co_owned_roster_maps_to_its_primary_owner_and_its_co_owner_is_an_alias():
    """Sabotage `owner_id only`: the co-owner alias reads nothing."""
    rosters = po.roster_index([{"roster_id": 4, "owner_id": "primary", "co_owners": ["co"]},
                               {"roster_id": 5, "owner_id": "other", "co_owners": None}])
    assert rosters == [[4, "primary", ["co"]], [5, "other", []]]
    reads = po.projection_reads(forecast(**{"4": .03, "5": .9}), rosters, ["primary", "co", "other"])
    assert reads == {"primary": "rebuilder", "co": "rebuilder", "other": "contender"}


def test_an_unmappable_roster_keeps_the_roster_read():
    """Sabotage `first match wins`: the two-roster member gets a read."""
    rosters = [[1, "twice", []], [2, "x", ["twice"]], [3, "nobody_prob", []], [4, "y", []]]
    reads = po.projection_reads(forecast(**{"1": .1, "2": .9, "4": .5}), rosters,
                                ["twice", "nobody_prob", "missing", "y"])
    assert reads == {"y": "contender"}


# ── The trade engine's partner input (owner context) ──────────────────────

def owner_context(harness, *, projection=None):
    _, _, sess, svc, league = harness
    kwargs = {} if projection is None else {"partner_projection": projection}
    return server._owner_generation_context(
        sess=sess, service=sess["service"], league=league, players=svc._players,
        seed_map=dict(SEED), user_elo=dict(ME_BOARD), user_roster=list(sess["user_roster"]),
        scoring_format="1qb_ppr", fairness_threshold=.5,
        captured_rankings={OPP: {"elo_ratings": dict(OPP_BOARD),
                                 "confidence_sources": {p: "explicit" for p in OPP_BOARD}}},
        pinned_give_players=None, pinned_receive_players=None, opponent_user_id=None,
        trade_intent=None, **kwargs)


def engine_outlook(context, uid):
    return owner._Search(**context).teams[uid]["outlook"]


@pytest.fixture
def roster_says_contender(monkeypatch):
    monkeypatch.setattr(ts, "infer_team_outlook", lambda *a, **k: ("contender", .5, {}))


@pytest.mark.parametrize("probability,outlook", [(.03, "rebuilder"), (.46, "contender"), (.45, "rebuilder")])
def test_an_undeclared_league_mate_is_assumed_from_their_playoff_chance(
        harness, monkeypatch, probability, outlook):
    """The operator's example: 3% is Rebuilding even though the roster read says
    Contending. Sabotage `use the roster read` (no projection in
    `_apply_partner_outlooks`): 3% and 45% read contender."""
    monkeypatch.setattr(ts, "infer_team_outlook", lambda *a, **k: ("contender", .5, {}))
    flags_on()
    harness[2]["sleeper_roster_index"] = INDEX
    counting_reader(monkeypatch, forecast(**{"1": .9, "2": probability, "3": .9}))
    context = owner_context(harness)
    prefs = context["manager_preferences"]
    assert prefs[OPP]["inferred_outlook"] == outlook and prefs[OPP]["outlook_source"] == "projection"
    assert context["inferred_outlooks"][OPP] == outlook
    assert engine_outlook(context, OPP) == outlook
    assert "outlook_source" not in prefs[ME]                          # the viewer is not touched
    flags_on(False)
    assert engine_outlook(owner_context(harness), OPP) == "contender"  # today's roster read


def test_a_saved_outlook_always_wins_over_the_projection(harness, monkeypatch, roster_says_contender):
    """Sabotage `projection overrides declared`: the engine reads rebuilder."""
    flags_on()
    harness[2]["sleeper_roster_index"] = INDEX
    db.upsert_league_preference(OPP, LEAGUE, "jets")
    counting_reader(monkeypatch, forecast(**{"2": .03}))
    context = owner_context(harness)
    prefs = context["manager_preferences"][OPP]
    assert prefs["outlook_source"] == "declared" and "inferred_outlook" not in prefs
    assert engine_outlook(context, OPP) == "jets"


def test_no_usable_forecast_keeps_the_roster_read_and_records_it(harness, monkeypatch, roster_says_contender):
    flags_on()
    harness[2]["sleeper_roster_index"] = INDEX
    counting_reader(monkeypatch, None)
    context = owner_context(harness)
    assert {u: p.get("outlook_source") for u, p in context["manager_preferences"].items()} == {
        ME: None, OPP: "roster", OPP2: "roster"}
    assert engine_outlook(context, OPP) == "contender"


def test_the_request_evidence_and_the_proof_record_the_source(harness, monkeypatch):
    flags_on()
    harness[2]["sleeper_roster_index"] = INDEX
    counting_reader(monkeypatch, forecast(**{"2": .03}))
    context = owner_context(harness)
    evidence = server._owner_selected_assignment(context, "organic", serve=True)["input"]
    assert evidence["manager_preferences"][OPP]["outlook_source"] == "projection"
    assert evidence["manager_preferences"][OPP2]["outlook_source"] == "roster"
    ts._cfg.update(bakeoff_include_owner=1., bakeoff_serve_owner=1.)
    cards, _ = owner.generate_owner_trades(**context)
    proofs = [c.owner_evaluation.as_dict() for c in cards if c.target_user_id == OPP]
    assert proofs, "fixture must emit a card against OPP"
    assert all(p["counterparty"]["outlook"] == "rebuilder" and p["counterparty"]["outlook_read"] == "projection"
               and p["counterparty"]["outlook_source"] == "inferred" and "outlook_read" not in p["viewer"]
               for p in proofs)


# ── One read per job ───────────────────────────────────────────────────────

def test_one_forecast_read_per_job_and_the_engine_gets_the_reads(owner_harness, monkeypatch):
    """Sabotage `read per league-mate` (`_apply_partner_outlooks` re-reads for
    each member): the engine gets roster reads / more than one read."""
    flags_on()
    owner_harness[2]["sleeper_roster_index"] = INDEX
    calls = counting_reader(monkeypatch, forecast(**{"1": .9, "2": .03, "3": .46}))
    assign(monkeypatch, "owner_v1")
    seen = []
    original = owner.generate_owner_trades

    def generate(**kwargs):
        seen.append({u: p.get("inferred_outlook") for u, p in kwargs["manager_preferences"].items()})
        return original(**kwargs)
    monkeypatch.setattr(owner, "generate_owner_trades", generate)
    worker(owner_harness, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP)
    assert calls == [(ME, LEAGUE)]
    assert seen and all(s[OPP] == "rebuilder" and s[OPP2] == "contender" for s in seen)


def test_the_request_thread_s_read_rides_the_preload_into_the_worker(owner_harness, monkeypatch):
    flags_on()
    _, _, sess, _, league = owner_harness
    sess["sleeper_roster_index"] = INDEX
    calls = counting_reader(monkeypatch, forecast(**{"2": .03}))
    preload = server._trade_job_preferences(ME, LEAGUE, sess, league)
    assert preload["partner_projection"]["reads"] == {OPP: "rebuilder"} and len(calls) == 1
    monkeypatch.setattr(po, "read_forecast", lambda *a, **k: pytest.fail("the worker read again"))
    assign(monkeypatch, "owner_v1")
    seen = []
    original = owner.generate_owner_trades

    def generate(**kwargs):
        seen.append(kwargs["manager_preferences"][OPP].get("inferred_outlook"))
        return original(**kwargs)
    monkeypatch.setattr(owner, "generate_owner_trades", generate)
    original_run = server._run_trade_job
    monkeypatch.setattr(server, "_run_trade_job",
                        lambda *a, **k: original_run(*a, **{**k, "prefs_preload": preload}))
    worker(owner_harness, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP)
    assert seen and set(seen) == {"rebuilder"}


# ── Every consumer agrees ─────────────────────────────────────────────────

def test_engine_and_fit_block_agree_for_the_same_team(harness, monkeypatch, roster_says_contender):
    """Sabotage `leave the fit block on the roster read`
    (`_fit_league_context` skipping `inferred_outlooks`): the tag says contending."""
    flags_on()
    ff._flags_cache["trade.fit_first_copy"] = True
    harness[2]["sleeper_roster_index"] = INDEX
    counting_reader(monkeypatch, forecast(**{"2": .03, "3": .46}))
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (list(harness[3]._players.values()), dict(SEED)))
    context = owner_context(harness)
    fit = server._fit_league_context(context, None)
    for uid, outlook in ((OPP, "rebuilder"), (OPP2, "contender")):
        assert engine_outlook(context, uid) == fit.reads[uid] == outlook
        assert fit.sources[uid] == "projection"
    assert ME not in fit.sources


def test_team_review_partner_groups_use_the_same_assumed_outlook(review, monkeypatch):
    """Sabotage `leave Team Review on the roster read`: u_b is missing from the
    rebuilding partners."""
    from backend.tests import test_power_rankings as pr
    get, flags, _ = review
    flags.update(FLAGS)
    with server._sessions_lock:
        server._sessions[pr.TOKEN]["sleeper_roster_index"] = {
            "league_id": pr.LEAGUE, "rosters": [[1, "u_a", []], [2, "u_b", []]]}
    rows = {}

    def partners(probability):
        counting_reader(monkeypatch, forecast(**{"1": .9, "2": probability}))
        response = server.app.test_client().get(
            f"/api/league/team-review?league_id={pr.LEAGUE}", headers=pr._h())
        return response.json["partners"]["opposed_window"]
    monkeypatch.setattr(server._trade_service_mod, "infer_team_outlook", lambda *a, **k: ("contender", .5, {}))
    get()                                                       # the fixture's saved-outlook guard
    rows["low"] = partners(.03)
    rows["high"] = partners(.46)
    # u_a declared contender, so the beat lists rebuilding league-mates.
    assert rows["low"] == [{**rows["low"][0], "user_id": "u_b", "inferred_outlook": "rebuilder",
                            "outlook_source": "projection"}]
    assert rows["high"] == []
    flags.discard("trade.partner_outlook_projection")
    off = partners(.03)
    assert off == [] and all("outlook_source" not in r for r in off)


def test_team_review_public_read_never_shows_a_saved_outlook():
    assert po.public("b", declared={"b": "jets"}, projection={"b": "rebuilder"}, roster="contender") == (
        "contender", "roster")
    assert po.public("b", declared={}, projection={"b": "rebuilder"}, roster="contender") == (
        "rebuilder", "projection")
    assert po.assumed("b", declared={"b": "jets"}, projection={"b": "rebuilder"}) == ("jets", "declared")


# ── The fit block tag ──────────────────────────────────────────────────────

def test_the_them_tag_follows_the_projection_read_and_installed_builds_keep_it(monkeypatch):
    """The projection read sets the tag; its wire `source` is `roster`, the
    only assumed-outlook source installed builds keep. Sabotage `wire source
    projection`: the tag reads `projection` and build 186 drops it."""
    from backend.tests import test_fit_block_v3 as fb
    from backend import trade_gen_bilateral_candidate as rev2
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(ff, "_flags_cache", {**ff.DEFAULT_FLAGS, "trade.fit_first_copy": True})
    kwargs, context, seed_map = fb.owner_league()
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (list(kwargs["players"].values()), dict(seed_map)))
    cards, _ = rev2.generate_bilateral_trades(**kwargs)
    roster_ctx = server._fit_league_context(context, None)
    context["manager_preferences"]["A"] = {"outlook_source": "projection"}
    projected_ctx = server._fit_league_context(context, None)
    tags = []
    for card in cards:
        if card.target_user_id != "A":
            continue
        proof = card.owner_evaluation.as_dict()
        before = tn.fit_block(proof, card, kwargs["players"], roster_ctx)
        after = tn.fit_block(proof, card, kwargs["players"], projected_ctx)
        if after:
            them = next(t for t in after["teams"] if t["side"] == "them")
            tags.append(them["tag"])
            old = next(t for t in before["teams"] if t["side"] == "them")
            assert {**them, "tag": None} == {**old, "tag": None}
            assert old["tag"] == them["tag"]   # this fixture's roster read agrees
    assert tags and all(t == {"code": "rebuilder", "source": "roster", "text": "Looks rebuilding"}
                        for t in tags)
    assert tn.FIT_TAGS["projection"] == tn.FIT_TAGS["roster"]
    assert tn.FIT_TAG_WIRE_SOURCE == {"projection": "roster"}


# ── Caching ────────────────────────────────────────────────────────────────

def test_a_changed_assumed_outlook_changes_the_request_signature(harness, monkeypatch):
    """A cached job, stored first page or prepared inventory is matched on the
    request signature (`_trade_job_is_fresh`, `_trade_require_current_page`,
    the prepared dependency receipt's `preferences`). Sabotage `keep the read
    out of the preload`: the signatures match and the old deck is served."""
    flags_on()
    _, _, sess, _, league = harness
    sess["sleeper_roster_index"] = INDEX
    counting_reader(monkeypatch, forecast(**{"2": .46}))
    before = server._trade_request_signature(server._trade_job_preferences(ME, LEAGUE, sess, league))
    counting_reader(monkeypatch, forecast(**{"2": .03}))
    after = server._trade_request_signature(server._trade_job_preferences(ME, LEAGUE, sess, league))
    counting_reader(monkeypatch, None)                 # the forecast went stale
    stale = server._trade_request_signature(server._trade_job_preferences(ME, LEAGUE, sess, league))
    assert len({before, after, stale}) == 3
    job = {"status": "complete", "request_signature": before, "fairness_threshold": .5,
           "finished_at": __import__("time").monotonic(), "outlook_value": None,
           "safety_policy": server._trade_safety_signature(), "key": (ME, LEAGUE, "1qb_ppr")}
    monkeypatch.setattr(server, "_trade_fingerprints_match", lambda *a, **k: True)
    assert server._trade_job_is_fresh(job, .5, None, request_signature=before)
    assert not server._trade_job_is_fresh(job, .5, None, request_signature=after)


# ── Flag off: byte-identical ───────────────────────────────────────────────

def test_flag_off_is_byte_identical(harness, monkeypatch):
    """Sabotage `stamp the source with the flag off`: preferences, hash and cards move."""
    _, _, sess, _, league = harness
    sess["sleeper_roster_index"] = INDEX
    ts._cfg.update(bakeoff_include_owner=1., bakeoff_serve_owner=1.)

    def run():
        context = owner_context(harness)
        cards, _ = owner.generate_owner_trades(**context)
        return {"preload": server._trade_job_preferences(ME, LEAGUE, sess, league),
                "prefs": copy.deepcopy(context["manager_preferences"]),
                "inferred": dict(context["inferred_outlooks"]),
                "hash": server._owner_selected_assignment(context, "organic", serve=True)["request_hash"],
                "cards": [(c.target_user_id, c.give_player_ids, c.receive_player_ids,
                           c.owner_evaluation.snapshot_json) for c in cards]}
    monkeypatch.setattr(po, "read_forecast", lambda *a, **k: pytest.fail("flag off read the forecast"))
    off = run()
    monkeypatch.setattr(po, "session_reads", lambda *a, **k: pytest.fail("flag off mapped the forecast"))
    never = run()
    assert off == never and off["cards"]
    assert "partner_projection" not in off["preload"]
    assert all("outlook_source" not in p for p in off["prefs"].values())
    # Sensitivity: the same world with the flag on moves the inputs and the hash.
    monkeypatch.setattr(po, "session_reads", SESSION_READS)
    flags_on()
    counting_reader(monkeypatch, forecast(**{"2": .03}))
    on = run()
    assert on["hash"] != off["hash"] and on["prefs"][OPP]["inferred_outlook"] == "rebuilder"



# ── Rules-first decks ──────────────────────────────────────────────────────

def test_rules_first_page_equals_gated_full_solve_with_projection_partner_outlooks():
    from backend import trade_fast_deck as fast, trade_gen_bilateral_candidate as candidate
    from backend.eval import served_deck_replay as replay, synthetic_league
    from backend.tests.test_rules_first_deck import identities
    context = synthetic_league.build(teams=12, seed=7)
    # Half the league never saved an outlook: they get a projection read
    # opposite to their roster read, through the production resolver.
    undeclared = [m.user_id for m in context["league"].members][::2]
    declared = {u: o for u, o in context["opponent_outlooks"].items() if u not in undeclared}
    prefs = {u: {"team_outlook": declared.get(u)} for u in [m.user_id for m in context["league"].members]}
    with ts._cfg_override({}):
        roster_reads = {m.user_id: ts.infer_team_outlook(list(m.roster), context["players"], num_teams=12)[0]
                        for m in context["league"].members}
    reads = {u: ("rebuilder" if roster_reads[u] != "rebuilder" else "contender") for u in undeclared}
    sess = {"user_id": "me"}
    server._apply_partner_outlooks(prefs, "me", sess, context["league"], {"reads": reads})
    context.update(opponent_outlooks=declared, manager_preferences=prefs,
                   inferred_outlooks={u: p["inferred_outlook"] for u, p in prefs.items() if "inferred_outlook" in p})
    assert context["inferred_outlooks"] == reads
    request = replay.Request(context, replay.DEFAULT_SLOTS)
    built, _, info = fast.serve(candidate.generate_bilateral_trades, context, request.rules())
    gated, _ = fast.gated_full(candidate.generate_bilateral_trades, context, request.rules())
    assert info["path"] == "page"
    assert identities(built) == identities(gated)
    assert identities(request.served(built)[0]) == identities(request.served(gated)[0])
    s = candidate._Search(**context)
    assert all(s.teams[u]["outlook"] == reads[u] for u in undeclared)
