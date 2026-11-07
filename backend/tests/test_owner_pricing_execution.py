"""Consumed pricing values, full independent evaluation and explicit limits."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
import threading

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend import trade_gen_owner as owner, trade_gen_bilateral as bilateral
from backend import trade_gen_bilateral_candidate as candidate, trade_gen_outlook_evidence as outlook
from backend import owner_pricing_execution as execution
from backend import owner_evaluation_inputs as inputs
from backend.tests.test_bilateral_generation_freeze import CASES, arguments, external_cards
from backend.tests.test_bilateral_candidate import companion_world
from backend.tests.test_trade_gen_owner import favorable


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, '_flags_cache', dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, '_cfg', dict(ts._DEFAULT_CFG))


def capture(args, module=candidate):
    result = execution.capture_owner_pricing(args, model_version=module.VERSION)
    assert result.execution is not None, (result.reason, result.path)
    return result.execution


def generated_value(result):
    cards, report = result
    rows = [dict(vars(card)) for card in cards]
    for row in rows:
        for key in ('trade_id', 'created_at', 'expires_at'):
            row.pop(key, None)
    data = report.as_dict()
    data.pop('elapsed_seconds', None)
    return json.loads(json.dumps([rows, data], default=lambda value: asdict(value) if is_dataclass(value) else value,
                                allow_nan=False))


@pytest.mark.parametrize('module', [bilateral, candidate, outlook])
@pytest.mark.parametrize('case', [case for case in CASES if case != 'invalid_floor'])
def test_all_native_outputs_and_fresh_final_proofs_match(module, case):
    args = arguments(case)
    captured = capture(args, module)
    assert generated_value(captured.generate()) == generated_value(module.generate_bilateral_trades(**deepcopy(args)))
    cards = external_cards(args)
    assert [asdict(p) for p in captured.evaluate(cards)] == [asdict(p) for p in module.evaluate_bilateral_trades(cards, **args)]


def test_original_owner_full_outputs_and_final_proofs_match():
    args = favorable()
    captured = capture(args, owner)
    result = captured.generate()
    assert generated_value(result) == generated_value(owner.generate_owner_trades(**deepcopy(args)))
    assert [asdict(p) for p in captured.evaluate(result[0])] == [asdict(p) for p in owner.evaluate_owner_trades(result[0], **args)]


def test_pricing_policy_is_owned_and_fingerprint_binds_effective_masks(monkeypatch):
    args = companion_world()
    first = capture(args)
    observed = first.pricing_policy.observation()
    observed['config']['crown_rate_market'] = 999
    observed['first_round_by_id'].clear()
    assert first.pricing_policy.config['crown_rate_market'] != 999
    assert first.pricing_policy.first_round_by_id
    with pytest.raises(TypeError):
        first.pricing_policy.config['crown_rate_market'] = 999
    monkeypatch.setattr(ts, 'first_round_pick_mask', lambda ids: [True for _ in ids])
    second = capture(args)
    assert first.envelope.fingerprint == second.envelope.fingerprint
    assert first.fingerprint != second.fingerprint
    assert first.pricing_policy.mask(['give', 'give']) == [False, False]
    with pytest.raises(inputs.UnsupportedOwnerInput, match='uncaptured_pricing_asset'):
        first.pricing_policy.mask(['unknown'])


@pytest.mark.parametrize('mutation', ['config', 'crown', 'mask', 'players', 'boards'])
def test_generation_and_final_use_owned_inputs_after_source_changes(monkeypatch, mutation):
    args = companion_world()
    captured = capture(args)
    cards, report = captured.generate()
    expected = [asdict(p) for p in captured.evaluate(cards)]
    if mutation == 'config':
        ts._cfg.update(elo_value_base=4321., package_floor_market=.1, market_floor_absolute=.99)
        args['config'] = {'owner_total_budget': 1}
    elif mutation == 'crown':
        monkeypatch.setitem(ff._flags_cache, 'trade.crown_asset', not captured.pricing_policy.crown_asset)
    elif mutation == 'mask':
        monkeypatch.setattr(ts, 'first_round_pick_mask', lambda ids: pytest.fail('live pick classifier read'))
    elif mutation == 'players':
        args['players']['give'].age = 40
        args['players']['give'].injury_status = 'OUT'
    else:
        args['user_elo'].clear()
        args['league'].members[0].elo_ratings.clear()
    assert [asdict(p) for p in captured.evaluate(cards)] == expected
    assert generated_value(captured.generate()) == generated_value((cards, report))


def test_explicit_pricing_never_reads_live_config_flag_mode_or_pick_mask(monkeypatch):
    captured = capture(companion_world())
    policy = captured.pricing_policy
    values = {'give': 6500., 'extra': 2500., 'target': 8000.}
    expected = ts.price_consensus_package(['give', 'extra'], ['target'], value_of=values.__getitem__, pricing_policy=policy)
    overpay = ts.overpay_ok(['give', 'extra'], ['target'], values.__getitem__, pricing_policy=policy)
    def forbidden(*args, **kwargs):
        pytest.fail('live pricing dependency read')
    monkeypatch.setattr(ts, '_c', forbidden)
    monkeypatch.setattr(ts, 'FLAGS', object())
    monkeypatch.setattr(ts, 'current_stud_tax_mode', forbidden)
    monkeypatch.setattr(ts, 'first_round_pick_mask', forbidden)
    assert ts.price_consensus_package(['give', 'extra'], ['target'], value_of=values.__getitem__, pricing_policy=policy) == expected
    assert ts.overpay_ok(['give', 'extra'], ['target'], values.__getitem__, pricing_policy=policy) == overpay


def test_default_pricing_still_reads_live_policy():
    args = companion_world()
    captured = capture(args)
    values = {'give': 6500., 'extra': 2500., 'target': 8000.}
    bound = lambda: ts.price_consensus_package(['give', 'extra'], ['target'], value_of=values.__getitem__, pricing_policy=captured.pricing_policy)
    expected = bound()
    with ts._cfg_override({'package_floor_market': .01, 'package_floor_cross': .01, 'package_discount_cap': .99}), ts.stud_tax_override('off'):
        assert bound() == expected
        assert ts.price_consensus_package(['give', 'extra'], ['target'], value_of=values.__getitem__) != expected


def test_constructor_precedence_and_unsupported_internal_policy(monkeypatch):
    args = companion_world()
    ts._cfg['owner_pool_size'] = 7
    with ts._cfg_override({'owner_pool_size': 9, 'elo_value_base': 1337.}):
        captured = capture(args)
    assert captured.pricing_policy.config['owner_pool_size'] == 7
    assert captured.pricing_policy.config['elo_value_base'] == 1337.
    args['config'] = {'owner_pool_size': 11}
    assert capture(args).pricing_policy.config['owner_pool_size'] == 11
    args['_pricing_policy'] = captured.pricing_policy
    assert execution.capture_owner_pricing(args, model_version=candidate.VERSION).reason == 'unknown_context_key'
    with pytest.raises(ValueError, match='pricing config mismatch'):
        candidate.generate_bilateral_trades(**companion_world(), _pricing_policy=captured.pricing_policy)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), 10**1000, 'not numeric'])
def test_malformed_config_is_explicitly_unsupported(value):
    args = companion_world()
    args['config'] = {'owner_total_budget': value}
    result = execution.capture_owner_pricing(args, model_version=candidate.VERSION)
    assert result.execution is None and result.reason


@pytest.mark.parametrize('value', [123, 'invalid', [('owner_pool_size', 9)], []])
def test_non_mapping_config_returns_explicit_unsupported(value):
    args = companion_world()
    args['config'] = value
    result = execution.capture_owner_pricing(args, model_version=candidate.VERSION)
    assert result.execution is None and result.reason == 'unsupported_pricing_config'


def test_overlays_are_nested_thread_local_and_restored_after_exception(monkeypatch):
    args = companion_world()
    first = capture(args)
    args['config'] = {'elo_value_base': 1234.}
    second = capture(args)
    before = ts._c('elo_value_base')
    barrier = threading.Barrier(2)
    original = candidate.generate_bilateral_trades
    def inspect(**kwargs):
        barrier.wait(timeout=5)
        assert ts._c('elo_value_base') == kwargs['_pricing_policy'].config['elo_value_base']
        return original(**kwargs)
    monkeypatch.setattr(candidate, 'generate_bilateral_trades', inspect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(item.generate) for item in (first, second)]
        assert all(f.result()[0] for f in results)
    assert ts._c('elo_value_base') == before
    def nested_failure(**kwargs):
        with ts._cfg_override({'elo_value_base': 9876.}):
            raise RuntimeError('test failure')
    monkeypatch.setattr(candidate, 'generate_bilateral_trades', nested_failure)
    with ts._cfg_override({'elo_value_base': 5432.}):
        with pytest.raises(RuntimeError, match='test failure'):
            first.generate()
        assert ts._c('elo_value_base') == 5432.
    assert ts._c('elo_value_base') == before


def test_final_evaluation_is_fresh_and_rejects_changed_offer(monkeypatch):
    captured = capture(companion_world())
    cards, _ = captured.generate()
    count = []
    init = candidate._Search.__init__
    def observe(self, **kwargs):
        count.append(kwargs['_pricing_policy'])
        init(self, **kwargs)
    monkeypatch.setattr(candidate._Search, '__init__', observe)
    good = captured.evaluate(cards)
    cards[0].give_player_ids = ['unknown']
    bad = captured.evaluate(cards)
    assert len(count) == 2 and all(policy is captured.pricing_policy for policy in count)
    assert good[0].eligible and not bad[0].eligible


def test_mutation_during_real_generation_and_final_keeps_same_pricing_policy(monkeypatch):
    args = companion_world()
    captured = capture(args)
    baseline = captured.generate()
    expected_final = [asdict(p) for p in captured.evaluate(baseline[0])]
    original = ts.price_consensus_package
    observed = []
    def mutate(*args_, **kwargs):
        observed.append(kwargs.get('pricing_policy'))
        ts._cfg.update(elo_value_base=7654., crown_rate_market=33., package_floor_market=.01)
        ff._flags_cache['trade.crown_asset'] = not captured.pricing_policy.crown_asset
        args['user_elo'].clear()
        args['players']['give'].injury_status = 'OUT'
        return original(*args_, **kwargs)
    monkeypatch.setattr(ts, 'price_consensus_package', mutate)
    generated = captured.generate()
    during_generation = len(observed)
    assert generated_value(generated) == generated_value(baseline)
    assert [asdict(p) for p in captured.evaluate(generated[0])] == expected_final
    assert 0 < during_generation < len(observed)
    assert all(policy is captured.pricing_policy for policy in observed)
