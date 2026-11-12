"""Win-now season signal, WI-5: worker wiring, flag, admin route, payload.

docs/plans/win-now-season-signal/lld.md §6 (worker), §5.2 (season_block), §8 (the
admin route's rows), §10 (I1, I15, I16); build-plan.md § WI-5 (the sabotage table).

The saved forecast is faked at its two read seams (`league_projections.batch.view`,
`store.get`), and `season_value.build_evidence` (WI-1's own tests pin it) returns a
synthetic evidence object over this harness's players, so these tests pin the
wiring: when the read happens, what is recorded, what reaches which generator, and
what the card carries. No network, no production DB.
"""
import copy
import json
import logging
import re
import time

import pytest

from backend import bakeoff_runner as bo, database as db, feature_flags as ff, season_value
from backend import server, trade_service as ts
from backend import trade_bilateral_presentment as presentment
from backend import trade_gen_bilateral_season as r5
from backend.league_projections import batch as lp_batch, store as lp_store
from backend.league_projections.core import VERSION as MODEL_VERSION
from backend.tests.test_owner_generator_routes import (  # noqa: F401
    harness, owner_harness, context_for, rows, worker, ME, LEAGUE)
from backend.tests.test_fair_packages import OPP, OPP2, SEED

FLAG = "trade.season_signal"
KNOBS = ("owner_bilateral_revision_5_enabled", "season_conflict_demotion", "season_partner_matching",
         "season_shed_weight_tanking", "season_shed_weight_rebuilding", "season_viewer_label_fit",
         "season_sell_bonus_tanking", "season_sell_bonus_rebuilding")
SLOTS = ["RB", "RB", "FLEX"]
# Projected points a week: the viewer's a1/a2 start, b1/b2 would start for the viewer.
PPG = {"a1": 14.0, "a2": 9.0, "a3": 3.0, "b1": 16.0, "b2": 15.0, "b3": 8.0, "b4": 7.5,
       "b5": 2.0, "c1": 12.0, "c2": 11.0}


def evidence(ppg=None, *, digest="digest-1", as_of="2026-11-11T18:00:00+00:00", unprojected=()):
    ppg = PPG if ppg is None else ppg
    return {"schema": season_value.EVIDENCE_SCHEMA, "state": "usable", "reason": None,
            "source": "league_projections", "run_id": "run-1", "model_version": MODEL_VERSION,
            "captured_at": "2026-11-10T14:30:00+00:00", "season": 2026, "weeks": [11, 12, 13, 14],
            "slots": list(SLOTS), "players": {pid: {"ppg": v, "games": 4} for pid, v in sorted(ppg.items())},
            "unprojected": sorted(unprojected), "free_agent_level": {p: 0.0 for p in season_value.POSITIONS},
            "rules_version": season_value.RULES_VERSION, "digest": digest, "as_of": as_of}


class Forecast:
    """The two read seams of a saved forecast, counted."""

    def __init__(self, monkeypatch, built=None, *, state="current", model=MODEL_VERSION, error=None):
        self.views = self.reads = self.builds = 0
        self.built, self.state, self.model, self.error = built, state, model, error
        monkeypatch.setattr(lp_batch, "view", self.view)
        monkeypatch.setattr(lp_store, "get", self.get)
        monkeypatch.setattr(season_value, "build_evidence", self.build)

    def view(self, user_id, league_id):
        self.views += 1
        if self.error:
            raise self.error
        return {"state": self.state, "run": {"run_id": "run-1", "created_at": "2026-11-10T14:30:00+00:00",
                                             "result_json": json.dumps({"model_version": self.model})}}

    def get(self, run_id, user_id, league_id):
        self.reads += 1
        return {"snapshot_json": json.dumps({"slots": SLOTS})}

    def build(self, snapshot, **kwargs):
        self.builds += 1
        self.kwargs = kwargs
        return copy.deepcopy(self.built if self.built is not None else evidence())


@pytest.fixture
def world(owner_harness, monkeypatch):
    """Owner-only organic decks under revision 2 (today's engine), a Sleeper league
    with RB/RB/FLEX starters, and a saved All-in plan."""
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1., bakeoff_owner_only=1.)
    monkeypatch.setitem(server._FA_LEAGUE_META_CACHE, LEAGUE,
                        (time.time(), {"roster_positions": [*SLOTS, "BN", "BN"]}))
    monkeypatch.setattr(server, "load_league_preference",
                        lambda **kw: {"team_outlook": "championship"})
    ff._flags_cache.update({FLAG: False, "deck.rules_first": False, "trade.fit_first_copy": True})
    return owner_harness


def revision_5():
    ts._cfg["owner_bilateral_revision_5_enabled"] = 1.


def season_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("season-signal:")]


def run_record(engine):
    return json.loads(rows(engine, db.bakeoff_runs_table)[-1]["config_json"])["owner_request"]


def shape(cards):
    """What a client is served, minus per-run ids and clocks."""
    volatile = {"impression_id", "expires_at", "trade_id"}
    return [{k: v for k, v in card.items() if k not in volatile} for card in cards]


def job_logs(caplog):
    return [re.sub(r"\d+(\.\d+)?", "#", r.getMessage()) for r in caplog.records
            if "ms" not in r.getMessage()]


# ── the flag gate (I1) ─────────────────────────────────────────────────────────

def test_flag_off_is_byte_identical_no_read_no_line_no_key(world, monkeypatch, caplog):
    """I1. Sabotage: attach the evidence key when the flag is off."""
    _, engine, *_ = world
    forecast = Forecast(monkeypatch)
    saved = {k: ts._cfg.pop(k) for k in KNOBS}           # the config as it was before revision 5 existed
    with caplog.at_level(logging.INFO):
        before = worker(world, monkeypatch)
    before_logs, before_record = job_logs(caplog), run_record(engine)
    caplog.clear()
    ts._cfg.update(saved)                                 # today: the knobs exist, the flag is off
    with caplog.at_level(logging.INFO):
        after = worker(world, monkeypatch)
    after_record = run_record(engine)
    assert after["cards"] and shape(after["cards"]) == shape(before["cards"])
    assert [sorted(c) for c in after["cards"]] == [sorted(c) for c in before["cards"]]
    assert all("season_block" not in c for c in after["cards"])
    assert job_logs(caplog) == before_logs and not season_lines(caplog)
    assert (forecast.views, forecast.reads, forecast.builds) == (0, 0, 0)
    assert "season_evidence" not in after_record
    assert after_record["request_hash"] == before_record["request_hash"]
    for row in rows(engine, db.deck_impressions_table):
        request = db.load_deck_diagnostics(row["impression_id"], row["user_id"])["owner_request"]
        assert "season_evidence" not in request


# ── one read per job; recorded, not a revision 2 input ─────────────────────────

def test_one_read_per_job_recorded_on_the_request_and_never_a_revision_2_input(world, monkeypatch, caplog):
    """Sabotages: read inside trade_card_to_dict (reads > 1); pass the evidence to
    revision 2 (TypeError: the owner arm forfeits, no revision 2 cards)."""
    client, engine, *_ = world
    ff._flags_cache[FLAG] = True
    forecast = Forecast(monkeypatch)
    with caplog.at_level(logging.INFO):
        job = worker(world, monkeypatch)
    assert job["cards"] and {c["generator_version"] for c in job["cards"]} == {"owner-v2-bilateral-2"}
    assert (forecast.views, forecast.reads, forecast.builds) == (1, 1, 1)
    assert forecast.kwargs["platform"] == "sleeper" and forecast.kwargs["slots"] == SLOTS
    record = run_record(engine)
    assert record["season_evidence"]["digest"] == "digest-1"
    assert record["season_evidence"]["players"] == evidence()["players"]
    assert "season_evidence" not in record["input"]
    # Each impression keeps only its own assets' rows; the digest names the whole map.
    impressions = rows(engine, db.deck_impressions_table)
    assert impressions
    for row in impressions:
        request = db.load_deck_diagnostics(row["impression_id"], row["user_id"])["owner_request"]
        projected = request["season_evidence"]
        assets = set(request["input"]["players"])
        assert projected["digest"] == "digest-1" and assets
        assert set(projected["players"]) == assets & set(PPG)
    # Polling the job serves the stored cards; it never reads the forecast again.
    client.get("/api/trades/status?job_id=owner-route-worker", headers={"X-Session-Token": "test-token-fairpk"})
    assert forecast.reads == 1
    assert season_lines(caplog) == [
        "season-signal: state=usable reason=- weeks=4 viewer_outlook=championship source=declared "
        "scored=false unprojected=0 revision=owner-v2-bilateral-2"]


def test_a_read_failure_serves_todays_deck_and_records_read_failed(world, monkeypatch, caplog):
    """Sabotage: let the exception reach the job."""
    _, engine, *_ = world
    Forecast(monkeypatch)
    today = worker(world, monkeypatch)
    ff._flags_cache[FLAG] = True
    forecast = Forecast(monkeypatch, error=RuntimeError("database is down"))
    with caplog.at_level(logging.INFO):
        job = worker(world, monkeypatch)
    assert forecast.views == 1 and forecast.reads == 0
    assert shape(job["cards"]) == shape(today["cards"]) and job["cards"]
    assert run_record(engine)["season_evidence"] == season_value.unavailable("read_failed")
    assert season_lines(caplog) == [
        "season-signal: state=unavailable reason=read_failed weeks=0 viewer_outlook=championship "
        "source=declared scored=false unprojected=0 revision=owner-v2-bilateral-2"]
    assert "database is down" not in caplog.text


@pytest.mark.parametrize("state,model,reason,reads", [
    ("stale", MODEL_VERSION, "stale", 0), ("current", "projected-lineup-universal-sd-v5", "old_model", 0),
    ("unsupported_policy", MODEL_VERSION, "no_forecast", 0)])
def test_unusable_saved_forecasts_skip_the_snapshot(world, monkeypatch, state, model, reason, reads):
    forecast = Forecast(monkeypatch, state=state, model=model)
    got = server._season_evidence(ME, LEAGUE, "sleeper", SLOTS)
    assert got == season_value.unavailable(reason) and forecast.reads == reads


def test_non_sleeper_league_is_platform_unsupported_without_a_read(world, monkeypatch):
    """Sabotage: call the store first."""
    _, engine, sess, _, league = world
    ff._flags_cache[FLAG] = True
    forecast = Forecast(monkeypatch)
    monkeypatch.setattr(league, "platform", "espn")
    worker(world, monkeypatch)
    assert (forecast.views, forecast.reads, forecast.builds) == (0, 0, 0)
    assert run_record(engine)["season_evidence"] == season_value.unavailable("platform_unsupported")
    assert server._season_evidence(ME, LEAGUE, "mfl", SLOTS)["reason"] == "platform_unsupported"
    assert forecast.views == 0


# ── the viewer completeness rule (PRD §2.5 rule 5) ─────────────────────────────

def _context(world, monkeypatch, built):
    ff._flags_cache[FLAG] = True
    Forecast(monkeypatch, built)
    _, _, sess, svc, league = world
    out = {}
    server._owner_generation_context(
        sess=sess, service=sess["service"], league=league, players=svc._players, seed_map=SEED,
        user_elo=dict(SEED), user_roster=sess["user_roster"], scoring_format="1qb_ppr",
        fairness_threshold=.5, season_out=out)
    return out["evidence"]


def test_an_unprojected_viewer_asset_worth_450_makes_the_lineup_unknown(world, monkeypatch):
    """a1 (value ~1649) is the viewer's and unprojected."""
    ppg = {k: v for k, v in PPG.items() if k != "a1"}
    assert _context(world, monkeypatch, evidence(ppg, unprojected=["a1"])) == \
        season_value.unavailable("viewer_unprojected_asset")


def test_league_mates_unprojected_assets_never_count(world, monkeypatch):
    """Sabotage: apply the rule to any roster in the league (b1 is OPP's)."""
    ppg = {k: v for k, v in PPG.items() if k not in ("b1", "c1")}
    assert season_value.usable(_context(world, monkeypatch, evidence(ppg, unprojected=["b1", "c1"])))


def test_an_injured_or_cheap_unprojected_viewer_player_is_allowed(world, monkeypatch):
    _, _, _, svc, _ = world
    monkeypatch.setattr(svc._players["a1"], "injury_status", "IR", raising=False)
    ppg = {k: v for k, v in PPG.items() if k not in ("a1", "a3")}   # a3 is worth ~368, under 450
    assert season_value.usable(_context(world, monkeypatch, evidence(ppg, unprojected=["a1", "a3"])))


# ── the request hash (I15) and the dark knobs ──────────────────────────────────

@pytest.mark.parametrize("revision", [2, 3, 4])
def test_revisions_2_to_4_hash_as_before_with_the_season_knobs_present(world, revision):
    """Sabotage: keep the knobs in the canonical config (drop the pop)."""
    ts._cfg.update(owner_outlook_evidence_enabled=float(revision == 3),
                   owner_bilateral_revision_4_enabled=float(revision == 4))
    context = context_for(world)                        # (a detached context: never deep-copied)
    for key in KNOBS:
        context["config"].pop(key, None)
    expected = server._owner_selected_assignment(context, "organic", serve=True)["request_hash"]
    for values in ((0., .10, 0., 1., .5, 0., 0., 0.), (2., 0., 1., .3, .9, 1., .05, .03)):
        context["config"].update(dict(zip(KNOBS, values)))
        assert server._owner_selected_assignment(context, "organic", serve=True)["request_hash"] == expected
    assert bo.owner_version(context["config"]) == {2: "owner-v2-bilateral-2", 3: "owner-v2-bilateral-3",
                                                   4: "owner-v2-bilateral-4"}[revision]


def test_revision_5_knobs_are_part_of_its_request(world):
    revision_5()
    context = context_for(world)
    first = server._owner_selected_assignment(context, "organic", serve=True)["request_hash"]
    context["config"]["season_conflict_demotion"] = 0.
    assert server._owner_selected_assignment(context, "organic", serve=True)["request_hash"] != first


def test_viewer_label_fit_off_keeps_revision_5_hashes_on_is_a_new_unit(world):
    """`season_viewer_label_fit` (amended 2026-11-12): any value but exactly 1 hashes as a
    revision 5 request built before the knob existed; 1 (the default) is a new unit.
    Sabotage: drop the knob-off pop from `_owner_selected_assignment`."""
    revision_5()
    context = context_for(world)
    context["config"].pop("season_viewer_label_fit", None)          # before the knob existed
    before = server._owner_selected_assignment(context, "organic", serve=True)["request_hash"]
    for off in (0., .5, 2.):
        context["config"]["season_viewer_label_fit"] = off
        assert server._owner_selected_assignment(context, "organic", serve=True)["request_hash"] == before
    context["config"]["season_viewer_label_fit"] = 1.
    assert server._owner_selected_assignment(context, "organic", serve=True)["request_hash"] != before


@pytest.mark.parametrize("key", ["season_sell_bonus_tanking", "season_sell_bonus_rebuilding"])
def test_sell_bonus_off_keeps_revision_5_hashes_on_is_a_new_unit(world, key):
    """The sell bonus (amended 2026-11-12): any value <= 0 hashes as a revision 5 request
    built before the knob existed; a positive value is a new unit, each value its own.
    Sabotage: drop the bonus-off pop from `_owner_selected_assignment`."""
    revision_5()
    context = context_for(world)
    for other in ("season_sell_bonus_tanking", "season_sell_bonus_rebuilding"):
        context["config"].pop(other, None)                      # before the knobs existed
    before = server._owner_selected_assignment(context, "organic", serve=True)["request_hash"]
    for off in (0., -.05):
        context["config"][key] = off
        assert server._owner_selected_assignment(context, "organic", serve=True)["request_hash"] == before
    hashes = set()
    for on in (.03, .05):
        context["config"][key] = on
        hashes.add(server._owner_selected_assignment(context, "organic", serve=True)["request_hash"])
    assert before not in hashes and len(hashes) == 2


def test_the_hash_follows_the_evidence_digest_never_as_of(world):
    """I15. Sabotage: hash the full evidence including as_of."""
    context = context_for(world)
    off = server._owner_selected_assignment(context, "organic", serve=True)
    one = server._owner_selected_assignment(context, "organic", serve=True, season_evidence=evidence())
    later = server._owner_selected_assignment(context, "organic", serve=True,
                                              season_evidence=evidence(as_of="2026-11-12T09:00:00+00:00"))
    other = server._owner_selected_assignment(context, "organic", serve=True,
                                              season_evidence=evidence(digest="digest-2"))
    failed = server._owner_selected_assignment(context, "organic", serve=True,
                                               season_evidence=season_value.unavailable("read_failed"))
    assert "season_evidence" not in off
    assert one["request_hash"] == later["request_hash"]
    assert len({off["request_hash"], one["request_hash"], other["request_hash"], failed["request_hash"]}) == 4
    assert one["season_evidence"] == evidence() and later["season_evidence"]["as_of"] == "2026-11-12T09:00:00+00:00"


# ── revision 5 served: presentment, season_block, rules-first ─────────────────

def test_revision_5_cards_present_and_carry_the_season_block(world, monkeypatch):
    """Sabotage: keep the literal version tuple at the presentment call (revision 5
    proofs read under revision 2's version)."""
    _, engine, *_ = world
    revision_5()
    ff._flags_cache[FLAG] = True
    Forecast(monkeypatch)
    versions = []
    original = presentment.present

    def present(cards, **kwargs):
        versions.append(kwargs.get("generator_version"))
        return original(cards, **kwargs)
    monkeypatch.setattr(presentment, "present", present)
    job = worker(world, monkeypatch)
    assert versions == ["owner-v2-bilateral-5"]
    assert job["cards"] and {c["generator_version"] for c in job["cards"]} == {"owner-v2-bilateral-5"}
    blocks = [c["season_block"] for c in job["cards"] if "season_block" in c]
    assert blocks and all(b["v"] == "season-1" and b for b in blocks)
    assert all(c.get("season_block") != {} and c.get("season_block", 1) is not None for c in job["cards"])
    proofs = [json.loads(r["valuation_json"]) for r in rows(engine, db.deck_impressions_table)]
    assert all(p["season_signal"]["evidence"]["digest"] == "digest-1" for p in proofs)


def test_no_season_block_on_revision_2_cards_or_with_the_flag_off(world, monkeypatch):
    ff._flags_cache[FLAG] = True
    Forecast(monkeypatch)
    assert all("season_block" not in c for c in worker(world, monkeypatch)["cards"])
    revision_5()
    ff._flags_cache[FLAG] = False
    job = worker(world, monkeypatch)
    assert job["cards"] and {c["generator_version"] for c in job["cards"]} == {"owner-v2-bilateral-5"}
    assert all("season_block" not in c for c in job["cards"])


def test_revision_5_with_unusable_evidence_carries_no_season_block(world, monkeypatch):
    revision_5()
    ff._flags_cache[FLAG] = True
    Forecast(monkeypatch, season_value.unavailable("stale"))
    job = worker(world, monkeypatch)
    assert job["cards"] and all("season_block" not in c for c in job["cards"])


def test_rules_first_takes_the_full_solve_for_revision_5_until_the_join(world, monkeypatch, caplog):
    from backend import trade_fast_deck
    revision_5()
    ff._flags_cache.update({FLAG: True, "deck.rules_first": True})
    Forecast(monkeypatch)
    with caplog.at_level(logging.INFO):
        job = worker(world, monkeypatch)
    assert job["cards"]
    line = ("rules-first: not built, generator backend.trade_gen_bilateral_season has no "
            "rules-first construction (full solve)")
    # WI-8 adds revision 5 to the rules-first set; until then it takes today's full solve.
    assert (line in caplog.text) == (not trade_fast_deck.supported(r5.generate_bilateral_trades))


# ── the admin label-review route ───────────────────────────────────────────────

@pytest.fixture
def stored_league(world, monkeypatch):
    client, engine, sess, svc, league = world
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id=LEAGUE, user_id=ME, platform="sleeper"))
        for member in league.members:
            conn.execute(db.league_members_table.insert().values(
                league_id=LEAGUE, user_id=member.user_id, username=member.username,
                roster_data=json.dumps(list(member.roster))))
    monkeypatch.setattr(server, "_get_universal_pool", lambda fmt: (list(svc._players.values()), dict(SEED)))
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cret")
    Forecast(monkeypatch)
    return client


def test_admin_label_route_refuses_without_the_cron_secret(stored_league):
    """Sabotage: drop _require_cron_auth()."""
    url = f"/api/admin/season-signal/labels?user_id={ME}&league_id={LEAGUE}"
    assert stored_league.get(url).status_code == 401
    assert stored_league.get(url, headers={"X-Cron-Secret": "wrong"}).status_code == 401


def test_admin_label_rows_are_the_review_shape_without_user_ids(stored_league):
    from backend.eval.season_label_review import SCHEMA, label_counts
    headers = {"X-Cron-Secret": "s3cret"}
    response = stored_league.get(f"/api/admin/season-signal/labels?user_id={ME}&league_id={LEAGUE}",
                                 headers=headers)
    assert response.status_code == 200
    body = response.json
    assert body["schema"] == SCHEMA and body["label_rules_version"] == r5.LABEL_RULES_VERSION
    assert body["evidence"]["state"] == "usable" and body["league_key"].startswith("league-")
    assert {p["id"] for p in body["players"]} == set(SEED)
    assert set(body["players"][0]) == {"id", "name", "position", "age", "ppg", "line", "value",
                                       "future", "startable", "label"}
    assert {p["id"] for p in body["own"]} == {"a1", "a2", "a3"}
    assert set(body["own"][0]) == {"id", "name", "position", "ppg", "starts_for_you"}
    assert sum(label_counts(body).values()) == len(SEED)
    served = json.dumps(body)
    for private in (ME, OPP, OPP2, LEAGUE, "me", "opp", "Fair Packages League"):
        assert f'"{private}"' not in served
    assert stored_league.get(f"/api/admin/season-signal/labels?user_id=stranger&league_id={LEAGUE}",
                             headers=headers).status_code == 404
    assert stored_league.get("/api/admin/season-signal/labels?user_id=x", headers=headers).status_code == 400


def test_admin_label_rows_say_why_when_there_is_no_usable_forecast(stored_league, monkeypatch):
    Forecast(monkeypatch, state="stale")
    body = stored_league.get(f"/api/admin/season-signal/labels?user_id={ME}&league_id={LEAGUE}",
                             headers={"X-Cron-Secret": "s3cret"}).json
    assert body["evidence"]["reason"] == "stale" and body["players"] == [] and body["own"] == []


# ── I16 ────────────────────────────────────────────────────────────────────────

def test_the_pipeline_version_and_engine_modules_cover_the_season_signal():
    """I16 (with test_deck_pipeline_digest). Sabotage: forget the bump."""
    assert server.DECK_PIPELINE_VERSION >= 25 and 25 in server.DECK_PIPELINE_PINS
    assert {"season_value.py", "league_projections/season_points.py"} <= set(server._ENGINE_CODE_MODULES)
    assert {"_season_evidence", "_season_viewer_complete"} <= set(server.DECK_PIPELINE_FUNCTIONS)
