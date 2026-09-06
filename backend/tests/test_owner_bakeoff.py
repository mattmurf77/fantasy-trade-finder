"""Owner construction arm joins the trial without changing existing generators."""

from types import SimpleNamespace

import pytest

from backend import bakeoff_runner as bo
from backend import trade_service as ts


def _card(tag):
    return SimpleNamespace(give_player_ids=[tag + "g"],
                           receive_player_ids=[tag + "r"],
                           target_user_id="partner", basis="divergence",
                           lane="value")


class _Report:
    def diagnostics(self):
        return {"generator_version": "owner-v1", "enumerated": 12}


@pytest.fixture
def config(monkeypatch):
    values = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0}
    monkeypatch.setattr(bo, "_cfg", lambda key, default: values.get(key, default))
    return values


def _run(**kwargs):
    return bo.run_bakeoff(generate=lambda **_: [_card("current")],
                         gen_v2=lambda **_: [_card("v2")],
                         league_id="league", iso_week="2026-W36",
                         interleave=True, fairness_threshold=.85, **kwargs)


def test_owner_disabled_leaves_default_control_roster_and_calls_unchanged(config):
    assert bo.arm_roster() == (bo.ARM_CURRENT, bo.ARM_CHALLENGER, bo.ARM_GEN_V2)
    assert not bo.serve_owner()
    before = _run()

    def must_not_run(**_):
        pytest.fail("disabled owner generator must not run")

    after = _run(gen_owner=must_not_run)
    assert list(before.arms) == list(after.arms)
    assert [(before.draft.attribution[id(c)], bo.card_key(c))
            for c in before.draft.deck] == [
        (after.draft.attribution[id(c)], bo.card_key(c)) for c in after.draft.deck]


@pytest.mark.parametrize("group_size", [0.0, 10.0])
def test_included_owner_is_logged_but_not_served_until_separately_enabled(config, group_size):
    config.update(bakeoff_include_owner=1.0, bakeoff_group_size=group_size)
    owner = _card("owner")
    run = _run(gen_owner=lambda **_: ([owner], _Report()))
    assert run.arms[bo.ARM_OWNER].cards == [owner]
    assert run.arms[bo.ARM_OWNER].diagnostics["enumerated"] == 12
    assert run.arms[bo.ARM_OWNER].fairness_threshold == .85
    assert all(arm != bo.ARM_OWNER for arm, _ in run.draft.attribution.values())
    config["bakeoff_serve_owner"] = 1.0
    live = _run(gen_owner=lambda **_: ([owner], _Report()))
    assert owner in live.draft.deck
    assert live.draft.attribution[id(owner)][0] == bo.ARM_OWNER


def test_serving_bit_without_inclusion_never_runs_or_serves_owner(config):
    config["bakeoff_serve_owner"] = 1.0
    assert bo.ARM_OWNER not in bo.arm_roster()
    run = _run(gen_owner=lambda **_: pytest.fail("include is off"))
    assert bo.ARM_OWNER not in run.arms


@pytest.mark.parametrize("group_size", [0.0, 10.0])
@pytest.mark.parametrize("initial", [False, True])
def test_owner_serving_is_frozen_before_generators_run(config, group_size, initial):
    config.update(bakeoff_include_owner=1.0, bakeoff_group_size=group_size,
                  bakeoff_serve_owner=float(initial))
    owner = _card("owner")

    def generate_owner(**_):
        config["bakeoff_serve_owner"] = float(not initial)
        return [owner], _Report()

    run = _run(gen_owner=generate_owner)
    assert (owner in run.draft.deck) is initial


@pytest.mark.parametrize("group_size", [0.0, 10.0])
@pytest.mark.parametrize("captured", [False, True])
def test_worker_captured_owner_permission_wins_over_later_config(config, group_size, captured):
    config.update(bakeoff_include_owner=1.0, bakeoff_group_size=group_size,
                  bakeoff_serve_owner=float(not captured))
    owner = _card("owner")
    run = _run(gen_owner=lambda **_: ([owner], _Report()), owner_serving=captured)
    assert (owner in run.draft.deck) is captured


def test_owner_failure_is_explicit_and_not_misattributed_to_control(config):
    config.update(bakeoff_include_owner=1.0, bakeoff_serve_owner=1.0)
    run = _run()
    assert "no gen_owner" in run.arms[bo.ARM_OWNER].error
    assert run.arms[bo.ARM_OWNER].cards == []
    assert run.arms[bo.ARM_CURRENT].error is None
    assert all(arm != bo.ARM_OWNER for arm, _ in run.draft.attribution.values())


def test_owner_config_cannot_modify_historical_profiles(config):
    from backend.bakeoff_profiles import MODEL_A_PROFILE, MODEL_CHALLENGER_PROFILE
    for key in ("bakeoff_include_owner", "bakeoff_serve_owner", "owner_pool_size",
                "owner_pair_budget", "owner_total_budget"):
        assert key not in MODEL_A_PROFILE
        assert key not in MODEL_CHALLENGER_PROFILE
    assert ts._DEFAULT_CFG["bakeoff_include_owner"] == 0
    assert ts._DEFAULT_CFG["bakeoff_serve_owner"] == 0


def test_owner_fairness_telemetry_never_uses_legacy_divergence_discount():
    card = _card("owner")
    card.relaxed = True
    card.owner_evaluation = SimpleNamespace(effective_floor=.9)
    assert bo.effective_fairness_threshold(card, .9, {
        "fairness_floor_divergence": .55, "relaxed_fairness_threshold": .55}) == .9


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), True, -.1, 1.1])
def test_invalid_owner_fairness_evidence_is_not_relabelled_as_legacy(invalid):
    card = _card("owner")
    card.owner_evaluation = SimpleNamespace(effective_floor=invalid)
    assert bo.effective_fairness_threshold(card, .75, {}) is None
