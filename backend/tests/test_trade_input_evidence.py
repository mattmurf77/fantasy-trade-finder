"""Private age provenance is collected, never consumed by the trade model."""
import copy
import json
import socket
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from backend import server, trade_service as ts, database as db
from backend import trade_input_evidence as evidence
from backend import trade_gen_bilateral_candidate as candidate
from backend.ranking_service import Player
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, context_for, post, rows, worker)
from backend.tests.test_players_refresh import m0, OLD_PAYLOAD, NEW_PAYLOAD


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("age evidence must not fetch provider data")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(server, "_sleeper_get", forbidden)


def player(pid="p", age=25, **kwargs):
    return Player(id=pid, name=pid, position="WR", team="T", age=age, **kwargs)


def bound(players, ages=None):
    collector = evidence.PoolInputEvidence()
    for pid, p in players.items():
        collector.record(p, raw={"age": p.age if ages is None else ages.get(pid)})
    return collector


def test_named_red_control_pool_keeps_genuine_25_distinct_from_fallback_25(monkeypatch):
    raw = {
        "known": {"full_name": "Known Player", "position": "WR", "age": 25},
        "missing": {"full_name": "Missing Player", "position": "WR", "age": None},
    }
    monkeypatch.setattr(server, "g_universal_by_format", {})
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: raw)
    monkeypatch.setattr(server, "load_players", lambda **kwargs: [])
    monkeypatch.setattr(server, "_load_dp_maps", lambda formats: None)
    values = {"known player": 1000., "missing player": 1000.}
    monkeypatch.setattr(server, "dp_values_by_format", {f: values for f in ("1qb_ppr", "sf_tep")})
    monkeypatch.setattr(server, "dp_elo_by_format", {})
    monkeypatch.setattr(server, "dp_pos_by_format", {})
    monkeypatch.setattr(server, "_rebind_legacy_pool_aliases", lambda: None)
    server._build_universal_pools_locked()
    pool = server.g_universal_by_format["1qb_ppr"]
    players = {p.id: p for p in pool["players"]}
    assert players["known"].age == players["missing"].age == 25
    assert "input_evidence" in pool, "age provenance was discarded during pool construction"
    rows = pool["input_evidence"].capture(players).as_dict(players)["age"]
    assert rows["known"]["age"] == 25
    assert rows["known"]["state"] == "observed"
    assert rows["missing"]["age"] is None
    assert rows["missing"]["state"] == "imputed"


@pytest.mark.parametrize("raw,db_age,expected,source,state", [
    (25, 31, 31, "players_db", "observed"),
    (25, 0, 25, "sleeper_cache", "observed"),
    (25, False, 25, "sleeper_cache", "observed"),
    (25, None, 25, "sleeper_cache", "observed"),
    ("25", None, 25, "sleeper_cache", "observed"),
    (25., None, 25, "sleeper_cache", "observed"),
    (None, None, None, "default", "imputed"),
    (0, None, None, "default", "imputed"),
    (False, None, None, "default", "imputed"),
    (True, None, None, "sleeper_cache", "invalid"),
    (-1, None, None, "sleeper_cache", "invalid"),
    (25.5, None, None, "sleeper_cache", "invalid"),
    ("bad", None, None, "sleeper_cache", "invalid"),
    ("25.0", None, None, "sleeper_cache", "invalid"),
    (float("inf"), None, None, "sleeper_cache", "invalid"),
    (float("nan"), None, None, "sleeper_cache", "invalid"),
    (25, True, None, "players_db", "invalid"),
    (25, float("inf"), None, "players_db", "invalid"),
    (25, float("nan"), None, "players_db", "invalid"),
    (25, "bad", None, "players_db", "invalid"),
    (25, -1, None, "players_db", "invalid"),
    (25, 10 ** 400, None, "players_db", "invalid"),
])
def test_selected_source_is_validated_without_changing_priority(raw, db_age, expected, source, state):
    row = evidence.age_row({"age": raw}, {"age": db_age})
    assert (row["age"], row["source"], row["state"]) == (expected, source, state)
    assert (row["imputed"] is True) == (state == "imputed")
    json.dumps(row, allow_nan=False)


@pytest.mark.parametrize("timestamp,expected", [
    ("2026-09-22T10:00:00Z", "2026-09-22T10:00:00+00:00"),
    ("2026-09-22T06:00:00-04:00", "2026-09-22T10:00:00+00:00"),
    ("2026-09-22T10:00:00", None), ("bad", None), (None, None), (123, None),
])
def test_only_available_timezone_bearing_source_observation_is_recorded(timestamp, expected):
    row = evidence.age_row({"age": 20}, {"age": 25, "last_synced": timestamp})
    assert row["observed_at"] == expected
    assert row["observation_basis"] == ("players.last_synced" if expected else None)
    raw = evidence.age_row({"age": 25, "updated_at": timestamp}, {"last_synced": timestamp})
    assert raw["observed_at"] is None


@pytest.mark.parametrize("age", [25, None, 0, False, True, -1, 25.5])
def test_direct_legacy_build_return_values_and_public_players_do_not_change(monkeypatch, age):
    monkeypatch.setattr(server, "load_players", lambda **k: pytest.fail("extra DB read"))
    inputs = dict(sleeper_cache={"p": {"full_name": "P", "position": "WR", "age": age}},
                  dp_vals={"p": 1000.}, all_db_players=[])
    before_players, before_seeds = server.build_universal_pool(**inputs)
    collector = evidence.PoolInputEvidence()
    after_players, after_seeds = server.build_universal_pool(**inputs, input_evidence=collector)
    assert [asdict(p) for p in before_players] == [asdict(p) for p in after_players]
    assert before_seeds == after_seeds
    assert [server.player_to_dict(p) for p in before_players] == [server.player_to_dict(p) for p in after_players]
    assert not any(hasattr(p, "input_evidence") for p in after_players)


@pytest.mark.parametrize("age", [float("inf"), float("nan"), "bad"])
def test_unsuccessful_legacy_age_conversion_is_not_repaired(age):
    args = dict(sleeper_cache={"p": {"full_name": "P", "position": "WR", "age": age}},
                dp_vals={"p": 1000.}, all_db_players=[])
    for extra in ({}, {"input_evidence": evidence.PoolInputEvidence()}):
        with pytest.raises((ValueError, OverflowError)):
            server.build_universal_pool(**args, **extra)


@pytest.mark.parametrize("field,value", [("age", 26), ("age", True), ("position", "QB"),
    ("team", "PICK"), ("pick_value", 50.), ("id", "other")])
def test_relevant_mutation_cannot_inherit_bound_age(field, value):
    p = player(age=1 if value is True else 25)
    players = {"p": p}
    captured = bound(players).capture(players)
    setattr(p, field, value)
    assert captured.as_dict(players)["age"]["p"]["age"] is None


def test_equal_replacements_mixed_maps_and_wrong_ids_remain_unknown():
    original, other = player(), player("other", 23)
    collector = bound({"p": original, "other": other})
    incoming = {"p": replace(original), "other": other, "foreign": player("foreign")}
    result = collector.capture(incoming).as_dict(incoming)["age"]
    assert result["p"]["reason"] == "pool_player_mismatch"
    assert result["foreign"]["reason"] == "pool_evidence_missing"
    assert result["other"]["age"] == 23
    bad_key = {"wrong": original}
    assert collector.capture(bad_key).as_dict(bad_key)["age"]["wrong"]["age"] is None


@pytest.mark.parametrize("p", [replace(player(), position="PICK"), replace(player(), team="PICK")])
def test_generic_and_injected_picks_are_not_human_age_evidence(p):
    for collector in (bound({"p": p}), evidence.PoolInputEvidence()):
        row = collector.capture({"p": p}).as_dict({"p": p})["age"]["p"]
        assert row["state"] == "not_applicable" and row["age"] is None and row["imputed"] is None


def test_raw_and_enriched_mutation_cannot_rewrite_a_collected_row():
    raw, enriched = {"age": 20}, {"age": 25, "last_synced": "2026-09-22T10:00:00Z"}
    p, collector = player(), evidence.PoolInputEvidence()
    collector.record(p, raw=raw, enriched=enriched)
    raw["age"], enriched["age"] = 35, 40
    assert collector.capture({"p": p}).as_dict({"p": p})["age"]["p"]["age"] == 25


@pytest.mark.parametrize("source", ["raw", "enriched"])
def test_named_red_control_pool_age_and_evidence_use_same_source_read(monkeypatch, source):
    raw = {"full_name": "P", "position": "WR", "age": 25}
    enriched = {"player_id": "p", "age": 25, "last_synced": "2026-09-22T10:00:00Z"}
    original_player = server.Player
    def mutate_after_construction(*args, **kwargs):
        result = original_player(*args, **kwargs)
        if result.id == "p":
            raw["age"] = enriched["age"] = 40
            enriched["last_synced"] = "2026-09-23T10:00:00Z"
        return result
    monkeypatch.setattr(server, "Player", mutate_after_construction)
    collector = evidence.PoolInputEvidence()
    built, _ = server.build_universal_pool(
        sleeper_cache={"p": raw}, dp_vals={"p": 1000.},
        all_db_players=[enriched] if source == "enriched" else [], input_evidence=collector)
    p = next(p for p in built if p.id == "p")
    row = collector.capture({"p": p}).as_dict({"p": p})["age"]["p"]
    assert p.age == 25 and row["age"] == p.age
    assert row["source"] == ("players_db" if source == "enriched" else "sleeper_cache")
    assert row["observed_at"] == ("2026-09-22T10:00:00+00:00" if source == "enriched" else None)


def test_named_red_control_selection_cannot_rebind_checked_age_to_mutated_player(monkeypatch):
    p = player()
    collector = bound({"p": p})
    original_row = evidence._BoundAge.row
    changed = []
    def mutate_after_check(self, pid, selected):
        row = original_row(self, pid, selected)
        if selected is p and not changed:
            changed.append(True)
            p.age = 26
        return row
    monkeypatch.setattr(evidence._BoundAge, "row", mutate_after_check)
    captured = evidence.detached_context({"players": {"p": p}}, collector)
    row = evidence.request_evidence(captured)["age"]["p"]
    assert changed and p.age == 26
    assert row["age"] is None or row["age"] == captured["players"]["p"].age


@pytest.mark.parametrize("initially_matches_pool", [False, True])
def test_named_red_control_copy_cannot_retarget_selected_pool_incarnation(initially_matches_pool):
    original = player()
    foreign = replace(original)
    values = {"players": {"p": original if initially_matches_pool else foreign}}
    class SwapDuringCopy:
        def __deepcopy__(self, memo):
            values["players"]["p"] = foreign if initially_matches_pool else original
            return None
    values["interleaving"] = SwapDuringCopy()
    captured = evidence.detached_context(values, bound({"p": original}))
    row = evidence.request_evidence(captured)["age"]["p"]
    assert (row["state"] == "observed") is initially_matches_pool
    assert row["age"] == (25 if initially_matches_pool else None)
    assert captured["players"]["p"] is not values["players"]["p"]


@pytest.fixture
def revised(owner_harness, monkeypatch):
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1., bakeoff_owner_only=1.)
    players = owner_harness[3]._players
    monkeypatch.setattr(server, "g_universal_by_format", {"1qb_ppr": {
        "players": list(players.values()), "seed": {}, "input_evidence": bound(players)}})
    return owner_harness


def test_named_red_control_revision_detaches_player_instances(revised):
    context = context_for(revised)
    original = revised[3]._players["a1"]
    captured_age = original.age
    original.age += 1
    assert context["players"]["a1"].age == captured_age
    assert context["players"]["a1"] is not original
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    assert assignment["input_evidence"]["age"]["a1"]["age"] == captured_age


def test_named_red_control_revision_captures_search_rank_and_pick_value(revised):
    original = revised[3]._players["a1"]
    original.search_rank, original.pick_value = 7, 123.5
    context = context_for(revised)
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    attrs = assignment["input"]["players"]["a1"]
    assert attrs["search_rank"] == 7 and attrs["pick_value"] == 123.5
    rebuilt = Player(id="a1", name="a1", **attrs)
    assert rebuilt.search_rank == 7 and rebuilt.pick_value == 123.5


def test_context_evidence_never_enters_generator_kwargs_and_is_collection_only(revised):
    context = context_for(revised)
    assert type(context) is evidence.OwnerInputContext
    assert "input_evidence" not in context
    with_evidence, _ = candidate.generate_bilateral_trades(**context)
    without, _ = candidate.generate_bilateral_trades(**dict(context))
    assert [c.owner_evaluation.as_dict() for c in with_evidence] == [c.owner_evaluation.as_dict() for c in without]
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    assert assignment["input_evidence"]["used_in_model"] is False
    assert "input_evidence" not in assignment["input"]


@pytest.mark.parametrize("copy_context", [dict, lambda c: c.copy(), lambda c: {**c}, copy.deepcopy])
def test_copy_loss_is_unknown_not_inferred_from_age_25(revised, copy_context):
    original = context_for(revised)
    copied = copy_context(original)
    assignment = server._owner_selected_assignment(copied, "fair_packages", serve=True)
    assert all(row["age"] is None for row in assignment["input_evidence"]["age"].values())
    assert any(row["age"] is not None for row in
               server._owner_selected_assignment(original, "fair_packages", serve=True)["input_evidence"]["age"].values())


def test_missing_legacy_pool_and_mutated_player_before_assignment_fail_closed(revised, monkeypatch):
    context = context_for(revised)
    first = next(iter(context["players"]))
    context["players"][first] = replace(context["players"][first])
    assert server._owner_selected_assignment(context, "fair_packages", serve=True)["input_evidence"]["age"][first]["age"] is None
    monkeypatch.setattr(server, "g_universal_by_format", {})
    legacy = server._owner_selected_assignment(context_for(revised), "fair_packages", serve=True)
    assert all(row["age"] is None and row["imputed"] is None for row in legacy["input_evidence"]["age"].values())


def test_assignment_is_detached_and_per_offer_rows_do_not_expand(revised):
    context = context_for(revised)
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    cards, _ = candidate.generate_bilateral_trades(**context)
    assert cards
    card = cards[0]
    subset = server._owner_request_snapshot(assignment, card)
    assets = set(card.give_player_ids + card.receive_player_ids)
    assert set(subset["input_evidence"]["age"]) == assets
    assert len(assignment["input_evidence"]["age"]) > len(assets)
    assert subset["request_hash"] == assignment["request_hash"]
    first = next(iter(assets))
    subset["input_evidence"]["age"][first]["age"] = 99
    assert assignment["input_evidence"]["age"][first]["age"] != 99
    context["players"][first].age = 77
    assert assignment["input_evidence"]["age"][first]["age"] != 77
    for pid, attrs in assignment["input"]["players"].items():
        rebuilt = Player(id=pid, name=pid, **attrs)
        assert rebuilt.age == attrs["age"]


def test_dark_context_and_hash_ignore_the_private_channel(revised):
    ts._cfg["owner_bilateral_revision_enabled"] = 0.
    context = context_for(revised)
    assert type(context) is dict and not hasattr(context, "_input_evidence")
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    assert "input_evidence" not in assignment
    assert "search_rank" not in assignment["input"]["players"]["a1"]
    assert "pick_value" not in assignment["input"]["players"]["a1"]
    assert context["players"]["a1"] is revised[3]._players["a1"]
    injected = evidence.OwnerInputContext(context, bound(context["players"]).capture(context["players"]))
    assert assignment["request_hash"] == server._owner_selected_assignment(injected, "fair_packages", serve=True)["request_hash"]
    context["config"].pop("owner_bilateral_revision_enabled")
    assert assignment["request_hash"] == server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]


def test_age_provenance_changes_revision_hash_without_changing_public_age(revised):
    context = context_for(revised)
    first = server._owner_selected_assignment(context, "fair_packages", serve=True)
    same_ages = {pid: p.age for pid, p in context["players"].items()}
    imputed = bound(context["players"], {})
    changed = evidence.OwnerInputContext(context, imputed.capture(context["players"]))
    second = server._owner_selected_assignment(changed, "fair_packages", serve=True)
    assert first["request_hash"] != second["request_hash"]
    assert first["input"]["players"] == second["input"]["players"]
    assert same_ages == {pid: p.age for pid, p in context["players"].items()}


def test_revision_capture_adds_no_database_queries(revised):
    engine = revised[1]
    queries = []
    def trace(conn, cursor, statement, parameters, context, executemany):
        queries.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", trace)
    try:
        ts._cfg["owner_bilateral_revision_enabled"] = 0.
        context_for(revised)
        dark = list(queries)
        queries.clear()
        ts._cfg["owner_bilateral_revision_enabled"] = 1.
        context = context_for(revised)
        server._owner_selected_assignment(context, "fair_packages", serve=True)
        assert queries == dark
    finally:
        event.remove(engine, "before_cursor_execute", trace)


def test_actual_route_projects_private_rows_and_keeps_full_run_capture(revised):
    client, engine, *_ = revised
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    public = json.dumps(response.json)
    assert "input_evidence" not in public and "used_in_model" not in public
    full = json.loads(rows(engine, db.bakeoff_runs_table)[0]["config_json"])
    assert full["input_evidence"]["used_in_model"] is False
    for impression in rows(engine, db.deck_impressions_table):
        snapshot = db.load_deck_diagnostics(impression["impression_id"], impression["user_id"])["owner_experiment"]
        proof = json.loads(impression["valuation_json"])
        exact = {asset["id"] for asset in proof["assets"]}
        assert set(snapshot["input_evidence"]["age"]) == exact
        assert snapshot["request_hash"] == full["request_hash"]
        assert "input_evidence" not in proof


def test_actual_organic_worker_keeps_input_evidence_private(revised, monkeypatch):
    job = worker(revised, monkeypatch)
    assert job["cards"]
    assert "input_evidence" not in json.dumps(job["cards"])
    records = rows(revised[1], db.deck_impressions_table)
    assert records
    snapshots = [db.load_deck_diagnostics(r["impression_id"], r["user_id"])["owner_request"] for r in records]
    assert all("input_evidence" in snapshot for snapshot in snapshots)
    assert all(snapshot["input_evidence"]["used_in_model"] is False for snapshot in snapshots)


def test_complete_input_tree_detaches_nested_selections_preferences_and_owned_pick(revised, monkeypatch):
    _, _, sess, service, league = revised
    pick = Player(id="owned-pick", name="Pick", position="PICK", team="PICK", age=0,
                  search_rank=8, pick_value=92.25)
    players = {**service._players, pick.id: pick}
    prefs = {"team_outlook": "contender", "targets": ["a1"], "nested": {"items": ["old"]}}
    give = ["a1"]
    context = server._owner_generation_context(
        sess=sess, service=sess["service"], league=league, players=players,
        seed_map={pid: 1500. for pid in players}, user_elo={}, user_roster=list(players),
        scoring_format="1qb_ppr", fairness_threshold=.5, captured_rankings={},
        captured_preferences={}, viewer_preferences=prefs, pinned_give_players=give)
    prefs["targets"].append("new")
    prefs["nested"]["items"].append("new")
    give.append("a2")
    pick.search_rank, pick.pick_value = 99, 1.
    assert context["pinned_give_players"] == ["a1"]
    assert context["manager_preferences"][sess["user_id"]]["targets"] == ["a1"]
    assert context["manager_preferences"][sess["user_id"]]["nested"]["items"] == ["old"]
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    captured = assignment["input"]["players"][pick.id]
    assert captured["search_rank"] == 8 and captured["pick_value"] == 92.25
    assert assignment["input_evidence"]["age"][pick.id]["state"] == "not_applicable"
    replay = Player(id=pick.id, name="Pick", **captured)
    assert replay.search_rank == 8 and replay.pick_value == 92.25


def test_preclone_identity_check_is_not_replaced_by_equal_attribute_matching():
    original = player()
    collector = bound({"p": original})
    values = {"players": {"p": replace(original)}, "nested": {"values": [1]}}
    cloned = evidence.detached_context(values, collector)
    assert evidence.request_evidence(cloned)["age"]["p"]["age"] is None
    assert cloned["players"]["p"] is not values["players"]["p"]
    assert cloned["nested"] is not values["nested"]


def test_mutation_during_copy_cannot_rebind_stale_age():
    class MutatingPlayer(Player):
        def __deepcopy__(self, memo):
            return replace(self, age=self.age + 1)
    original = MutatingPlayer(id="p", name="P", position="WR", team="T", age=25)
    cloned = evidence.detached_context({"players": {"p": original}}, bound({"p": original}))
    row = evidence.request_evidence(cloned)["age"]["p"]
    assert row["age"] is None and row["reason"] == "player_changed_during_capture"


def test_named_red_control_assignment_member_board_is_detached(revised):
    context = context_for(revised)
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    before = json.dumps(assignment, sort_keys=True)
    for member in context["league"].members:
        member.elo_ratings["synthetic-new-row"] = 1777.
    assert json.dumps(assignment, sort_keys=True) == before


def test_both_formats_rebuild_atomically_without_rebinding_old_players(m0, monkeypatch):
    server._invalidate_player_pipeline(copy.deepcopy(OLD_PAYLOAD))
    old = dict(server.g_universal_by_format)
    assert set(old) == {"1qb_ppr", "sf_tep"}
    before = {}
    for fmt, pool in old.items():
        players = {p.id: p for p in pool["players"]}
        before[fmt] = pool["input_evidence"].capture(players)
        assert before[fmt].as_dict(players)["age"]["p1"]["age"] == 23
    assert old["1qb_ppr"]["input_evidence"] is not old["sf_tep"]["input_evidence"]
    build = server.build_universal_pool
    def observe(*args, **kwargs):
        assert all(server.g_universal_by_format[fmt] is entry for fmt, entry in old.items())
        return build(*args, **kwargs)
    monkeypatch.setattr(server, "build_universal_pool", observe)
    payload = copy.deepcopy(NEW_PAYLOAD)
    payload["p1"]["age"] = 31
    server._invalidate_player_pipeline(payload)
    for fmt, current in server.g_universal_by_format.items():
        old_players = {p.id: p for p in old[fmt]["players"]}
        new_players = {p.id: p for p in current["players"]}
        assert current is not old[fmt]
        assert new_players["p1"] is not old_players["p1"]
        row = current["input_evidence"].capture(new_players).as_dict(new_players)["age"]["p1"]
        assert row["age"] == 31 and row["source"] == "players_db" and row["observed_at"]
        assert before[fmt].as_dict(old_players)["age"]["p1"]["age"] == 23
        mismatch = current["input_evidence"].capture(old_players).as_dict(old_players)["age"]["p1"]
        assert mismatch["age"] is None and mismatch["reason"] == "pool_player_mismatch"


def test_cross_format_equal_players_cannot_borrow_provenance(m0):
    server._invalidate_player_pipeline(copy.deepcopy(OLD_PAYLOAD))
    first, second = (server.g_universal_by_format[fmt] for fmt in ("1qb_ppr", "sf_tep"))
    players = {p.id: p for p in second["players"]}
    row = first["input_evidence"].capture(players).as_dict(players)["age"]["p1"]
    assert row["age"] is None and row["reason"] == "pool_player_mismatch"


def test_unsuccessful_refresh_keeps_previous_pool_and_evidence(m0, monkeypatch):
    server._invalidate_player_pipeline(copy.deepcopy(OLD_PAYLOAD))
    old = dict(server.g_universal_by_format)
    generation = server.pool_generation()
    monkeypatch.setattr(server, "_load_dp_maps", lambda formats: None)
    server._invalidate_player_pipeline(copy.deepcopy(NEW_PAYLOAD))
    assert server.pool_generation() == generation
    assert all(server.g_universal_by_format[fmt] is entry for fmt, entry in old.items())


def test_partial_refresh_preserves_other_formats_own_incarnation(m0, monkeypatch):
    server._invalidate_player_pipeline(copy.deepcopy(OLD_PAYLOAD))
    old = dict(server.g_universal_by_format)
    load = server._load_dp_maps
    monkeypatch.setattr(server, "_load_dp_maps", lambda formats: load(["sf_tep"]))
    server._invalidate_player_pipeline(copy.deepcopy(NEW_PAYLOAD))
    assert server.g_universal_by_format["1qb_ppr"] is old["1qb_ppr"]
    assert server.g_universal_by_format["sf_tep"] is not old["sf_tep"]


def test_checkpoint_default_off_assignment_hash_golden():
    # Independently generated by the untouched assignment at HEAD 6c53caf9.
    p = Player(id="p", name="P", position="WR", team="T", age=25, search_rank=7)
    context = dict(players={"p": p}, league=SimpleNamespace(members=[]), user_id="viewer",
        user_roster=["p"], user_elo={"p": 1500.}, seed_elo={"p": 1500.},
        scoring_format="1qb_ppr", fairness_threshold=.5, manager_preferences={},
        config={"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 0.})
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True)
    assert assignment["request_hash"] == "fc7cf9bafc7fef42577fffe323d57164f77af4efdbe19eea9303f33923459407"
    assert "input_evidence" not in assignment
