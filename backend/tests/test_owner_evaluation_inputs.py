"""Offline observation only: exact inputs, explicit gaps, no reuse authority."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
import inspect
import math
import struct

import pytest

from backend import feature_flags as ff, ranking_service as ranking, trade_service as ts
from backend import trade_gen_owner as owner, trade_gen_bilateral as incumbent
from backend import trade_gen_bilateral_candidate as candidate, trade_gen_outlook_evidence as outlook
from backend import owner_evaluation_inputs as inputs
from backend.trade_input_evidence import PoolInputEvidence, detached_context, request_evidence
from backend.tests.test_bilateral_generation_freeze import CASES, arguments, generated_value, external_cards
from backend.tests.test_bilateral_candidate import companion_world
from backend.tests.test_owner_generator_routes import harness, owner_harness, context_for


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, '_cfg', dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(ranking, '_cfg', dict(ranking._DEFAULT_CFG))
    monkeypatch.setattr(ff, '_flags_cache', dict(ff.DEFAULT_FLAGS))


def capture(context, *, module=candidate, ambient=None):
    result = inputs.capture_owner_inputs(context, model_version=module.VERSION,
        ambient=inputs.observe_ambient_inputs() if ambient is None else ambient)
    assert result.reason is None, (result.reason, result.path)
    return result.envelope


def test_schema_covers_constructor_and_preserves_full_records_and_detached_reads():
    expected = set(inspect.signature(owner._Search.__init__).parameters) - {'self'}
    assert inputs.CONTEXT_KEYS == expected | {'input_evidence'}
    args = companion_world()
    player = args['players']['give']
    player.search_rank, player.pick_value, player.birth_date = 123, 12.5, '2000-01-01'
    args['league'].members[0].board_updated_at = '2026-01-01T00:00:00Z'
    envelope = capture(args)
    reconstructed = envelope.evaluator_kwargs()
    assert reconstructed == args
    assert reconstructed['players']['give'] is not player
    assert reconstructed['league'].members[0] is not args['league'].members[0]
    player.search_rank = 999
    args['user_elo']['give'] += 40
    reconstructed['players']['give'].birth_date = 'changed'
    reconstructed['league'].members[0].roster.append('changed')
    assert envelope.evaluator_kwargs()['players']['give'].search_rank == 123
    assert envelope.evaluator_kwargs()['players']['give'].birth_date == '2000-01-01'
    assert 'changed' not in envelope.evaluator_kwargs()['league'].members[0].roster
    with pytest.raises(FrozenInstanceError):
        envelope.fingerprint = 'changed'
    assert 'user_elo' not in repr(envelope)
    assert envelope.unbound_dependencies and not hasattr(envelope, 'authorize_reuse')


@pytest.mark.parametrize('value', [0, False, True, -0., 5e-324, 10**100, 'e\u0301', '\ud800'])
def test_numeric_types_bits_and_unicode_are_preserved(value):
    args = companion_world()
    args['manager_preferences'] = {'viewer': {'test_value': value}}
    result = capture(args).evaluator_kwargs()['manager_preferences']['viewer']['test_value']
    assert type(result) is type(value)
    if type(value) is float:
        assert struct.pack('!d', result) == struct.pack('!d', value)
    else:
        assert result == value


def test_ordered_pins_and_map_iteration_are_bound_but_set_membership_is_canonical():
    args = companion_world()
    args['pinned_give_players'] = ['give', 'extra']
    first = capture(args)
    args['pinned_give_players'].reverse()
    assert capture(args).fingerprint != first.fingerprint
    args['user_elo'] = dict(reversed(list(args['user_elo'].items())))
    changed = capture(args)
    assert list(changed.evaluator_kwargs()['user_elo']) == list(args['user_elo'])
    assert changed.fingerprint != first.fingerprint
    args['past_decision_keys'] = {(frozenset(['give', 'extra']), frozenset(['target']))}
    before = capture(args)
    args['past_decision_keys'] = {(frozenset(['extra', 'give']), frozenset(['target']))}
    assert capture(args).fingerprint == before.fingerprint
    assert capture(args).evaluator_kwargs()['past_decision_keys'] == args['past_decision_keys']


@pytest.mark.parametrize('mutation', [
    lambda a: a['user_elo'].__setitem__('unrelated', 1600.),
    lambda a: a['seed_elo'].__setitem__('unrelated', 1700.),
    lambda a: a['league'].members[0].elo_ratings.__setitem__('target', 1501.),
    lambda a: a['league'].members[0].roster.append('new_hold'),
    lambda a: setattr(a['players']['give'], 'injury_status', 'OUT'),
    lambda a: setattr(a['players']['give'], 'search_rank', 99),
    lambda a: setattr(a['players']['give'], 'pick_value', 42.),
    lambda a: a.__setitem__('scoring_format', 'sf_ppr'),
    lambda a: a.__setitem__('user_sources', {'give': 'seed'}),
    lambda a: a.__setitem__('manager_preferences', {'viewer': {'inactive_ids': ['give']}}),
    lambda a: a.__setitem__('exclusion_keys', {(frozenset(['give']), frozenset(['target']))}),
    lambda a: a.__setitem__('config', {'market_floor_absolute': .71}),
])
def test_declared_context_dependencies_change_binding(mutation):
    args = companion_world()
    before = capture(args)
    mutation(args)
    assert capture(args).fingerprint != before.fingerprint


def test_ambient_observation_is_detached_and_effective_config_flags_tables_are_bound(monkeypatch):
    args = companion_world()
    baseline = capture(args)
    observed = inputs.observe_ambient_inputs()
    observed['static_data']['tier_config'].clear()
    observed['feature_flags'].clear()
    assert ranking.TIER_CONFIG and ff._flags_cache
    with ts._cfg_override({'market_floor_absolute': .701}):
        changed = capture(args)
        assert changed.ambient_observation()['effective_trade_config']['market_floor_absolute'] == .701
        assert changed.fingerprint != baseline.fingerprint
    monkeypatch.setitem(ff._flags_cache, 'trade.crown_asset', not ff._flags_cache['trade.crown_asset'])
    assert capture(args).fingerprint != baseline.fingerprint
    flags_changed = capture(args)
    monkeypatch.setattr(ranking, 'ORDERED_TIERS', list(reversed(ranking.ORDERED_TIERS)))
    assert capture(args).fingerprint != flags_changed.fingerprint
    result = baseline.ambient_observation()
    result['effective_trade_config'].clear()
    assert baseline.ambient_observation()['effective_trade_config']


def test_source_sidecar_is_observed_without_rebinding_player_identity():
    args = companion_world()
    pool = PoolInputEvidence()
    for player in args['players'].values():
        pool.record(player, raw={'age': player.age})
    context = detached_context(args, pool)
    before = request_evidence(context)
    envelope = capture(context)
    assert envelope.provenance_observation() == {'kind': 'observation_not_rebound', 'rows': before}
    restored = envelope.evaluator_kwargs()
    assert type(restored) is dict and not hasattr(restored, '_input_evidence')
    assert request_evidence(restored)['age']['give']['state'] == 'unknown'
    assert before['age']['give']['state'] == 'observed'
    # Explicit consumed V3 evidence remains evaluator input, with normal bytes.
    restored['input_evidence'] = {**before, 'schema_version': outlook.INPUT_VERSION, 'used_in_model': True}
    assert capture(restored, module=outlook).evaluator_kwargs()['input_evidence'] == restored['input_evidence']


@pytest.mark.parametrize('value,reason', [
    (math.nan, 'nonfinite_number'), (math.inf, 'nonfinite_number'),
    (object(), 'unsupported_type'), (b'bytes', 'unsupported_type')])
def test_unsupported_values_are_explicit_without_lossy_encoding(value, reason):
    args = companion_world()
    args['manager_preferences'] = {'viewer': {'bad': value}}
    result = inputs.capture_owner_inputs(args, model_version=candidate.VERSION, ambient=inputs.observe_ambient_inputs())
    assert result.envelope is None and result.reason == reason and result.path


def test_cycles_callbacks_unknown_schema_and_missing_ambient_are_rejected():
    class Hostile(dict):
        def items(self):
            pytest.fail('custom serialization callback executed')
    args = companion_world()
    args['config'] = Hostile(x=1)
    ambient = inputs.observe_ambient_inputs()
    result = inputs.capture_owner_inputs(args, model_version=candidate.VERSION, ambient=ambient)
    assert result.reason == 'unsupported_type'
    cyclic = {}; cyclic['self'] = cyclic
    args['config'] = cyclic
    assert inputs.capture_owner_inputs(args, model_version=candidate.VERSION, ambient=ambient).reason == 'cyclic_input'
    args['config'] = {}
    args['future_uninventoried_input'] = 1
    assert inputs.capture_owner_inputs(args, model_version=candidate.VERSION, ambient=ambient).reason == 'unknown_context_key'
    del args['future_uninventoried_input']
    del ambient['feature_flags']
    assert inputs.capture_owner_inputs(args, model_version=candidate.VERSION, ambient=ambient).reason == 'missing_ambient_dependency'
    args['players']['give'].new_runtime_attribute = 1
    assert inputs.capture_owner_inputs(args, model_version=candidate.VERSION,
        ambient=inputs.observe_ambient_inputs()).reason == 'record_attribute_schema'


@pytest.mark.parametrize('module', [incumbent, candidate, outlook])
@pytest.mark.parametrize('case', [case for case in CASES if case != 'invalid_floor'])
def test_full_stable_input_generation_and_final_proofs_match(module, case):
    args = arguments(case)
    envelope = capture(args, module=module)
    restored = envelope.evaluator_kwargs()
    assert generated_value(module, args, dynamic=True) == generated_value(module, restored, dynamic=True)
    original = module.evaluate_bilateral_trades(external_cards(args), **deepcopy(args))
    reconstructed = module.evaluate_bilateral_trades(external_cards(restored), **restored)
    assert [asdict(p) for p in original] == [asdict(p) for p in reconstructed]
    assert envelope.fingerprint == capture(args, module=module).fingerprint


@pytest.mark.parametrize('module', [incumbent, candidate, outlook])
def test_unsupported_nonfinite_request_leaves_existing_evaluator_available(module):
    args = arguments('invalid_floor')
    result = inputs.capture_owner_inputs(args, model_version=module.VERSION, ambient=inputs.observe_ambient_inputs())
    assert result.envelope is None and result.reason == 'nonfinite_number'
    # Unsupported observation is not a route policy or changed rejection path.
    assert module.generate_bilateral_trades(**args)[0] == []
    assert all(not proof.eligible for proof in module.evaluate_bilateral_trades(external_cards(args), **args))


def test_actual_revision_adapter_context_preserves_owner_math_not_provider_binding(owner_harness):
    from backend import server
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    args = context_for(owner_harness)
    envelope = capture(args)
    restored = envelope.evaluator_kwargs()
    original = candidate.generate_bilateral_trades(**args)[0]
    reproduced = candidate.generate_bilateral_trades(**restored)[0]
    assert original and [c.owner_evaluation.snapshot_json for c in original] == [c.owner_evaluation.snapshot_json for c in reproduced]
    original = server._owner_cards_valid(original, args)
    reproduced = server._owner_cards_valid(reproduced, restored)
    assert [c.owner_evaluation.snapshot_json for c in original] == [c.owner_evaluation.snapshot_json for c in reproduced]
    assert type(restored) is dict and not hasattr(restored, '_input_evidence')


def test_original_owner_generator_preserves_full_output():
    from backend.tests.test_trade_gen_owner import favorable
    args = favorable()
    restored = capture(args, module=owner).evaluator_kwargs()
    def value(context):
        cards, report = owner.generate_owner_trades(**context)
        rows = [asdict(card) for card in cards]
        for row in rows:
            for key in ('trade_id', 'created_at', 'expires_at'):
                row.pop(key, None)
        result = report.as_dict()
        result.pop('elapsed_seconds', None)
        return rows, result
    assert value(args) == value(restored)


def test_ambient_unknown_proxy_and_closure_return_explicit_reasons(monkeypatch):
    monkeypatch.setattr(ts, 'FLAGS', object())
    with pytest.raises(inputs.UnsupportedOwnerInput) as caught:
        inputs.observe_ambient_inputs()
    assert caught.value.reason == 'unsupported_flag_proxy'
    monkeypatch.setattr(ts, 'FLAGS', ff.FLAGS)
    rate = .75
    curves = {**ts._AGE_NOW_CURVE, 'RB': lambda age: rate}
    monkeypatch.setattr(ts, '_AGE_NOW_CURVE', curves)
    with pytest.raises(inputs.UnsupportedOwnerInput) as caught:
        inputs.observe_ambient_inputs()
    assert caught.value.reason == 'unsupported_ambient_callable'


@pytest.mark.parametrize('group,key', [
    ('effective_trade_config', 'market_floor_absolute'),
    ('raw_owner_limits', 'owner_pool_size'), ('feature_flags', 'trade.crown_asset'),
    ('source_files', 'trade_gen_owner.py'), ('static_data', 'roster_eligibility'),
    ('runtime', 'string_hash_observation')])
def test_ambient_groups_cannot_hide_missing_declared_dependencies(group, key):
    ambient = inputs.observe_ambient_inputs()
    del ambient[group][key]
    result = inputs.capture_owner_inputs(companion_world(), model_version=candidate.VERSION, ambient=ambient)
    assert result.envelope is None and result.reason == 'missing_ambient_dependency'


def test_missing_flag_cache_keys_bind_actual_false_not_default(monkeypatch):
    monkeypatch.setattr(ff, '_flags_cache', {})
    observed = inputs.observe_ambient_inputs()
    assert observed['feature_flags'] and not any(observed['feature_flags'].values())


def test_ambient_model_constant_inventory_cannot_be_empty():
    observed = inputs.observe_ambient_inputs()
    observed['static_data']['model_constants'][owner.__name__].clear()
    result = inputs.capture_owner_inputs(companion_world(), model_version=candidate.VERSION, ambient=observed)
    assert result.reason == 'missing_ambient_dependency'


def test_provenance_internal_callbacks_are_rejected_before_execution():
    from backend.trade_input_evidence import CapturedInputEvidence, OwnerInputContext
    class HostileRow:
        def row(self, *_):
            pytest.fail('provenance callback executed')
    args = companion_world()
    context = OwnerInputContext(args, CapturedInputEvidence({'give': HostileRow()}))
    result = inputs.capture_owner_inputs(context, model_version=candidate.VERSION,
                                        ambient=inputs.observe_ambient_inputs())
    assert result.envelope is None and result.reason == 'unsupported_provenance_binding'


@pytest.mark.parametrize('container', [lambda n: n, lambda n: {n}])
def test_oversized_native_integer_returns_structured_unsupported(container):
    import sys
    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip('runtime has no integer-to-JSON digit limit')
    args = companion_world()
    args['manager_preferences'] = {'viewer': {'oversized': container(10 ** (limit + 1))}}
    result = inputs.capture_owner_inputs(args, model_version=candidate.VERSION,
                                        ambient=inputs.observe_ambient_inputs())
    assert result.envelope is None and result.reason == 'input_encoding_limit'
