"""Local owner-proof decoding preserves standard encoding and detached semantics."""
import json, math, random, struct
from copy import deepcopy
from dataclasses import replace
import pytest
from backend import trade_gen_owner as owner



def decode(proof):
    return proof.as_dict()


def local_proof(data):
    return proof('{}')._with_data(data)


def proof(raw):
    return owner.OwnerDecisionContext(False, 'test', 'L', 'U', 'O', (), (), raw)


def same(left, right):
    assert type(left) is type(right)
    if isinstance(left, float):
        assert struct.pack('!d', left) == struct.pack('!d', right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for k in left: same(left[k], right[k])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a,b in zip(left,right): same(a,b)
    else:
        assert left == right


@pytest.mark.parametrize('value', [-(2**63)-1, 2**64, 10**100, -(10**100), 2**53+1,
    -0., 5e-324, 1.7976931348623157e308, '\ud800', '\udc00', '😀', 'e\u0301', 'a\x00b',
    'prefix:123456789012345678901,suffix', {'nested': [2**64]}])
def test_local_values_preserve_stdlib_types_bits_and_unicode(value):
    local = local_proof({'value': value})
    same(decode(local), json.loads(local.snapshot_json))


def test_random_finite_float_roundtrips():
    rng = random.Random(20261106)
    values = [struct.unpack('!d', rng.getrandbits(64).to_bytes(8, 'big'))[0] for _ in range(10000)]
    values = [v for v in values if math.isfinite(v)]
    local = local_proof({'values': values})
    same(decode(local), json.loads(local.snapshot_json))


@pytest.mark.parametrize('raw', ['NaN', 'Infinity', '-Infinity', '1e309', str(2**64),
    '{"x":}', '{"x":1,}', '{"x":1,"x":2}', '"\\ud800"', '[1,]'])
def test_manual_snapshots_retain_success_or_exact_failure(raw):
    local = proof(raw)
    try:
        expected = json.loads(raw)
    except Exception as exc:
        with pytest.raises(type(exc), match=str(exc).replace('(', r'\(').replace(')',r'\)')):
            decode(local)
    else:
        same(decode(local), expected)


def test_detached_deepcopy_replace_and_marker_binding():
    local = local_proof({'nested': {'value': [1, 2]}})
    detached = decode(local)
    detached['nested']['value'].append(9)
    assert decode(local) == {'nested': {'value': [1, 2]}}
    copied = deepcopy(local)
    decoded_copy = decode(copied)
    decoded_copy['nested']['value'].append(7)
    assert decode(copied) == decode(local) == {'nested': {'value': [1, 2]}}
    changed = replace(local, snapshot_json='NaN')
    assert not hasattr(changed, '_local_json')
    assert math.isnan(decode(changed))
    if hasattr(local, '_local_json'):
        object.__setattr__(changed, '_local_json', local._local_json)
    assert math.isnan(decode(changed))  # A stale legitimate marker does not bind this string.
    for hostile in (True, {'raw': 'NaN', 'fast': True}, object()):
        object.__setattr__(changed, '_local_json', hostile)
        assert math.isnan(decode(changed))


def test_local_encoder_rejects_nonfinite_before_a_marker_exists():
    for value in (float('nan'), float('inf'), -float('inf')):
        with pytest.raises(ValueError): owner._dump({'value': value})


@pytest.mark.parametrize('value', [-(2**63)-1, 2**64, 10**100, -0., 5e-324, '😀', '\ud800', None, True])
def test_root_primitives_preserve_standard_decoder(value):
    local = local_proof(value)
    same(decode(local), json.loads(local.snapshot_json))
    if isinstance(value, int) and len(str(abs(value))) >= 19 and hasattr(local, '_local_json'):
        assert not local._local_json.fast


def test_explicit_reencoding_keeps_standard_bytes_and_drops_old_scalar_caches():
    data = {'generator': 'old', 'generator_version': 'v1', 'selection': {'coverage': 'partial'}}
    local = local_proof(data)
    assert local.snapshot_json == owner._dump(data)
    assert local.model_identity == ('old', 'v1')
    assert local.selection_coverage == 'partial'
    data['generator'] = 'new'
    data['selection']['coverage'] = 'full'
    changed = local._with_data(data)
    assert changed.model_identity == ('new', 'v1')
    assert changed.selection_coverage == 'full'
    assert local.model_identity == ('old', 'v1')
    raw_replace = replace(local, snapshot_json=owner._dump(data))
    assert not hasattr(raw_replace, '_local_json')
    assert raw_replace.model_identity == ('new', 'v1')
    assert raw_replace.selection_coverage == 'full'
    with pytest.raises(TypeError):
        local._with_data(data, snapshot_json='NaN')
    assert local.model_identity == ('old', 'v1')


def test_missing_optional_decoder_preserves_marked_and_unmarked_reads(monkeypatch):
    marked = local_proof({'value': 1})
    monkeypatch.setattr(owner, '_fast_json', None)
    assert decode(marked) == {'value': 1}
    new = local_proof({'value': 2**100})
    assert not hasattr(new, '_local_json')
    assert decode(new) == {'value': 2**100}


def test_optional_import_failure_in_a_fresh_module():
    import subprocess, sys
    code = """
import builtins
original = builtins.__import__
def without_orjson(name, *args, **kwargs):
    if name == 'orjson':
        raise ModuleNotFoundError('test missing optional decoder')
    return original(name, *args, **kwargs)
builtins.__import__ = without_orjson
from backend import trade_gen_owner as owner
assert owner._fast_json is None
proof = owner.OwnerDecisionContext(False, 'test', 'L', 'U', 'O', (), (), '{}')._with_data({'n': 2**100})
assert proof.as_dict() == {'n': 2**100}
assert not hasattr(proof, '_local_json')
"""
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)


@pytest.mark.skipif(owner._fast_json is None, reason='optional decoder not installed')
def test_actual_fast_path_and_rejection_fallback(monkeypatch):
    from types import SimpleNamespace
    real = owner._fast_json
    calls = []
    def tracked(raw):
        calls.append(raw)
        return real.loads(raw)
    monkeypatch.setattr(owner, '_fast_json', SimpleNamespace(loads=tracked, JSONDecodeError=real.JSONDecodeError))
    local = local_proof({'value': .746, 'nested': [1, 2]})
    assert local._local_json.raw is local.snapshot_json
    assert local._local_json.fast
    assert decode(local) == {'value': .746, 'nested': [1, 2]}
    assert calls == [local.snapshot_json]
    unsafe = local_proof({'value': 2**100})
    assert not unsafe._local_json.fast
    assert decode(unsafe) == {'value': 2**100}
    assert len(calls) == 1
    unicode_proof = local_proof({'value': '\ud800'})
    assert decode(unicode_proof) == {'value': '\ud800'}
    assert len(calls) == 2  # Fast decoder rejects; standard decoder preserves it.
    def failed(raw):
        raise real.JSONDecodeError('injected decode rejection', raw, 0)
    monkeypatch.setattr(owner, '_fast_json', SimpleNamespace(loads=failed, JSONDecodeError=real.JSONDecodeError))
    assert decode(local) == {'value': .746, 'nested': [1, 2]}
