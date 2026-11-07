"""Real owner generation with provider facts isolated from network and accounts."""
import copy
from datetime import datetime, timedelta, timezone

import pytest

from backend import outlook_calibration_adapter as adapter, server, session_input
from backend.tests.test_owner_generator_routes import harness, owner_harness, ME, LEAGUE


@pytest.fixture
def captured(owner_harness, monkeypatch):
    _, engine, sess, _, league = owner_harness
    from backend import database as db
    with engine.begin() as conn:
        conn.execute(db.users_table.insert(), [{"sleeper_user_id": uid,
            "created_at": "2026-11-01T00:00:00+00:00", "verified_via": "sleeper"}
            for uid in sorted({ME, *(m.user_id for m in league.members)})])
    raw_rosters = [{"owner_id": ME, "players": list(sess["user_roster"])}] + [
        {"owner_id": m.user_id, "players": list(m.roster)} for m in league.members]
    def resolve(_sess, _body, _fetch, raw):
        raw.update(rosters=copy.deepcopy(raw_rosters), meta={"roster_positions": ["RB", "BN", "BN", "BN", "BN"]})
        return dict(platform="sleeper", league_user_id=ME,
                    user_player_ids=list(sess["user_roster"]),
                    opponent_rosters=[dict(user_id=m.user_id, username=m.username,
                                           player_ids=list(m.roster)) for m in league.members if m.user_id != ME])
    monkeypatch.setattr(session_input, "resolve_session_input", resolve)
    monkeypatch.setattr(server, "_extension_ranking_services", lambda *a, **k: {"1qb_ppr": sess["service"]})
    monkeypatch.setattr(server, "_get_universal_pool", lambda fmt: (sess["players"], sess["service"]._seed))
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: 0)
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {p.id: {"fantasy_positions": [p.position]} for p in sess["players"]})
    monkeypatch.setattr(server, "_league_slot_order", lambda lid: {})
    monkeypatch.setattr(adapter, "_input_identity", lambda *a: "same")
    from backend import feature_flags as ff, trade_service as ts
    ff._flags_cache.update({"trade.picks_in_pool": False, "deck.quality_filters": False})
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   owner_outlook_evidence_enabled=0.)
    return adapter.capture(user_id=ME, league_user_id=ME, league_id=LEAGUE)


def test_real_paired_models_use_same_snapshot_and_never_change_selector(captured):
    from backend import trade_service as ts
    before = copy.deepcopy(captured.source)
    outputs = [captured.run_arm(version) for version in adapter.VERSIONS]
    assert outputs[0][0] and outputs[1][0]
    for version, (cards, diag) in zip(adapter.VERSIONS, outputs):
        assert diag["native_count"] >= diag["final_count"] == len(cards)
        assert all(c.owner_evaluation.model_identity[1] == version for c in cards)
        assert all(c.roster_evaluation["eligible"] for c in cards)
    assert ts._cfg["owner_outlook_evidence_enabled"] == 0
    assert captured.source == before
    assert captured.source["input"]["user_id"] == ME
    assert ME in captured.source["registered_participants"]
    assert captured.source["registered_participant_revisions"][ME] == "2026-11-01T00:00:00+00:00"


def test_frozen_snapshot_survives_elapsed_time_but_not_input_changes(captured, monkeypatch):
    args = dict(user_id=ME, league_user_id=ME, league_id=LEAGUE)
    assert adapter.is_current(captured.source, **args)
    monkeypatch.setattr(adapter, "_input_identity", lambda *a: "changed")
    assert not adapter.is_current(captured.source, **args)
    monkeypatch.setattr(adapter, "_input_identity", lambda *a: "same")
    old = {**captured.source, "captured_at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()}
    assert adapter.is_current(old, **args)
    assert not adapter.is_current(captured.source, **{**args, "league_user_id": "other"})


def test_unknown_version_refuses_without_generation(captured):
    with pytest.raises(ValueError, match="unsupported"):
        captured.run_arm("future")


def test_capture_rejects_changes_between_input_reads(captured, monkeypatch):
    values = iter(("before", "after"))
    monkeypatch.setattr(adapter, "_input_identity", lambda *a: next(values))
    with pytest.raises(adapter.GradingError) as error:
        adapter.capture(user_id=ME, league_user_id=ME, league_id=LEAGUE)
    assert error.value.code == "inputs_changed_during_capture"


def test_coowner_uses_personal_preferences_but_actual_roster_seat(captured, monkeypatch):
    reads = []
    def prefs(*, user_id, league_id):
        reads.append(user_id)
        return {"team_outlook": "rebuilding"} if user_id == "coowner" else {}
    monkeypatch.setattr(server, "load_league_preference", prefs)
    result = adapter.capture(user_id="coowner", league_user_id=None, league_id=LEAGUE)
    assert reads == ["coowner"]
    assert result.source["account_user_id"] == "coowner"
    assert result.source["league_user_id"] == ME
    assert result.owner_context["user_id"] == ME
    assert result.owner_context["manager_preferences"][ME]["team_outlook"] == "rebuilding"
    assert "coowner" not in result.owner_context["manager_preferences"]
    assert result.roster_context.viewer_id == ME
    with pytest.raises(adapter.GradingError) as error:
        adapter.capture(user_id="coowner", league_user_id="wrong", league_id=LEAGUE)
    assert error.value.code == "league_seat_changed"


def test_frozen_suppression_cannot_consume_live_retest(captured, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("live read/write after capture")
    monkeypatch.setattr(server, "load_deck_suppressions", forbidden)
    monkeypatch.setattr(server, "load_deck_pass_after", forbidden)
    monkeypatch.setattr(server, "mark_deck_suppression_retested", forbidden)
    monkeypatch.setattr(server, "resuppress_deck_suppression", forbidden)
    captured.source["suppression"] = {"rows": [], "passed_at": {}, "band": .1,
        "window_days": 30, "now": datetime.now(timezone.utc).isoformat()}
    assert captured.run_arm(adapter.VERSIONS[0])[0]
    with pytest.raises(ValueError, match="private mutation sink"):
        server._apply_deck_suppression([], user_id=ME, league_id=LEAGUE,
            seed_map={}, frozen_state=captured.source["suppression"])


def test_capture_reacquires_pool_replaced_after_warm_before_fingerprint(captured, monkeypatch):
    """An unchanged new fingerprint must never authenticate the warm-up pool."""
    old_players, old_seed = server._get_universal_pool("1qb_ppr")
    new_players, new_seed = copy.deepcopy(old_players), dict(old_seed)
    pid = new_players[0].id
    new_players[0].age = 31
    new_seed[pid] = float(new_seed[pid]) + 37
    state = {"current": (old_players, old_seed), "reads": [], "checks": 0}

    def get_pool(fmt):
        current = state["current"]
        state["reads"].append(current[1][pid])
        return current

    def identity(*args):
        state["checks"] += 1
        if state["checks"] == 1:
            state["current"] = (new_players, new_seed)
        return "new-pool-identity"

    monkeypatch.setattr(server, "_get_universal_pool", get_pool)
    monkeypatch.setattr(adapter, "_input_identity", identity)
    result = adapter.capture(user_id=ME, league_user_id=ME, league_id=LEAGUE)

    assert state["reads"] == [old_seed[pid], new_seed[pid]]
    assert result.owner_context["seed_elo"][pid] == new_seed[pid]
    assert result.owner_context["players"][pid].age == 31
    assert result.source["input_identity"] == "new-pool-identity"
    assert state["checks"] == 2


def test_provider_cache_warming_is_not_a_semantic_change(captured, monkeypatch):
    args = dict(user_id=ME, league_user_id=ME, league_id=LEAGUE)
    at = datetime.fromisoformat(captured.source['captured_at']).timestamp()
    monkeypatch.setattr(server, '_FA_LEAGUE_META_CACHE', {})
    assert adapter.is_current(captured.source, **args)
    server._FA_LEAGUE_META_CACHE[LEAGUE] = (at + 1, captured.source['provider_rules'])
    assert adapter.is_current(captured.source, **args)
    server._FA_LEAGUE_META_CACHE[LEAGUE] = (at - 1, {'roster_positions': ['QB']})
    assert adapter.is_current(captured.source, **args)
    server._FA_LEAGUE_META_CACHE[LEAGUE] = (at + 1, {'roster_positions': ['QB']})
    assert not adapter.is_current(captured.source, **args)


def test_cold_missing_pool_is_unavailable_not_a_stale_exercise(captured, monkeypatch):
    monkeypatch.setattr(server, 'g_universal_by_format', {})
    monkeypatch.setattr(server, '_get_universal_pool', lambda fmt: ([], {}))
    with pytest.raises(adapter.GradingError) as error:
        adapter.is_current(captured.source, user_id=ME, league_user_id=ME, league_id=LEAGUE)
    assert error.value.code == 'comparison_inputs_unavailable'


def test_capture_refuses_participant_identity_change_even_with_same_model_inputs(captured, monkeypatch):
    from backend import database as db
    calls = []
    def identity(*args):
        if not calls:
            with db.engine.begin() as conn:
                conn.execute(db.users_table.update().where(db.users_table.c.sleeper_user_id == ME)
                             .values(created_at='2026-11-06T00:00:00+00:00'))
        calls.append(True)
        return 'same'
    monkeypatch.setattr(adapter, '_input_identity', identity)
    with pytest.raises(adapter.GradingError) as error:
        adapter.capture(user_id=ME, league_user_id=ME, league_id=LEAGUE)
    assert error.value.code == 'inputs_changed_during_capture'
