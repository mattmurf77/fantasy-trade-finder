"""Offline latency experiments: exact cache inputs and lossless structured evidence.

These exercise research tools only; no live worker behavior is changed.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.research_trade_compute import (
    compact_structured_rows, intern_features, load_inputs, package_cache, storage_sample,
)
from backend import deck_diagnostics as dd


def test_compute_refuses_preimported_database(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "backend.database", None)
    with pytest.raises(RuntimeError, match="fresh process"):
        load_inputs(tmp_path / "no-input", tmp_path / "no-config", tmp_path / "isolated.sqlite3")


def test_package_cache_real_market_math_and_exemptions(tmp_path):
    # Fresh interpreter and explicit SQLite protect the main suite's globals.
    script = r'''
import socket
def no_network(*args, **kwargs):
    raise RuntimeError('Offline pricing test forbids network')
socket.socket.connect = socket.socket.connect_ex = socket.create_connection = no_network
from types import SimpleNamespace
from scripts.research_trade_compute import package_cache
from backend import trade_service as ts, feature_flags as ff
ff._flags_cache = {**ff.DEFAULT_FLAGS, 'trade.crown_asset': True}
class Search:
    def _package(self, give, receive, values):
        return ts.price_consensus_package(list(give), list(receive), value_of=values.__getitem__)
Search.ts = ts
original = Search._package
values = {'a': 6351., 'b': 2117., 'c': 0.05, 'generic_pick_1_mid': 2117., 'zero': 0.}
shapes = [(['a'], ['b', 'generic_pick_1_mid']),
          (['a', 'c'], ['generic_pick_1_mid', 'b']),
              (['b', 'c'], ['a']), (['zero'], ['b'])]
for mode in ('market', 'heavy', 'off'):
    for exemption in (0., 1.):
        for trade_wide in (0., 1.):
            with ts.stud_tax_override(mode), ts._cfg_override({
                **ts._DEFAULT_CFG, 'stud_tax_exempt_first_round': exemption,
                'package_bench_trade_wide': trade_wide, 'skew_phaseout': 0.31,
                'crown_rate_market': 0.27, 'package_floor_cross': 0.32}):
                with package_cache(SimpleNamespace(_Search=Search)):
                    search = Search()
                    for give, receive in shapes:
                        assert search._package(give, receive, values) == original(search, give, receive, values)
                        assert search._package(receive, give, values) == original(search, receive, give, values)
print('96 directional pricing comparisons passed')
'''
    run = subprocess.run([sys.executable, "-c", script],
                         cwd=Path(__file__).resolve().parents[2],
                         env={"PATH": os.defpath, "DATABASE_URL": "sqlite:///" + str(tmp_path / "isolated.sqlite3")},
                         capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert "96 directional pricing comparisons passed" in run.stdout


def test_package_cache_preserves_full_ordered_context_and_pick_masks():
    calls = []

    class Search:
        ts = SimpleNamespace(first_round_pick_mask=lambda ids: [p.startswith("pick_") for p in ids],
                             current_stud_tax_mode=lambda: "market")

        def _package(self, give, receive, values):
            calls.append((tuple(give), tuple(receive)))
            a, b = sum(values[p] for p in give), sum(values[p] for p in receive)
            return min(a, b) / max(a, b), a, b

    original = Search._package
    owner = SimpleNamespace(_Search=Search)
    values = {"a": 100., "b": 60., "c": 40., "pick_1": 100., "d": 61.}
    with package_cache(owner) as counts:
        search = Search()
        assert search._package(["a"], ["b", "c"], values) == (1., 100., 100.)
        assert search._package(["b", "c"], ["a"], values) == (1., 100., 100.)
        search._package(["a"], ["b", "c"], values)
        assert len(calls) == 1
        # Reordered float additions, a changed counterparty and first-round
        # exemption each require fresh evaluation; additive caches are unsafe.
        search._package(["a"], ["c", "b"], values)
        search._package(["a"], ["d", "c"], values)
        search._package(["pick_1"], ["b", "c"], values)
        assert len(calls) == 4
        Search()._package(["a"], ["b", "c"], values)
        assert len(calls) == 5  # a separate captured request has a fresh cache
        assert counts == {"hits": 2, "misses": 5}
    assert Search._package is original


def test_package_cache_reverse_retains_side_values():
    class Search:
        ts = SimpleNamespace(first_round_pick_mask=lambda ids: [False] * len(ids),
                             current_stud_tax_mode=lambda: "market")

        def _package(self, give, receive, values):
            return .5, 100., 200.

    with package_cache(SimpleNamespace(_Search=Search)):
        search = Search()
        values = {"a": 100., "b": 200.}
        assert search._package(["a"], ["b"], values) == (.5, 100., 200.)
        assert search._package(["b"], ["a"], values) == (.5, 200., 100.)


def fixture_rows(count=6):
    shared = {f"setting_{i}": i / 7 for i in range(200)}
    return [{"user_id": "u", "deck_job_id": "j", "served_at": "2026-09-21T00:00:00Z",
             "valuation_json": json.dumps({"value": i + .01}), "impression_id": str(i),
             "features_json": json.dumps({"owner_request": {"config": shared, "asset": str(i)},
                                          "owner_generation": {"config": shared, "count": count},
                                          "give_value": i + .01})} for i in range(count)]


def test_structured_compaction_exact_bytes_snapshots_no_mutation():
    original = fixture_rows()
    structured = intern_features(original)
    before = copy.deepcopy(structured)
    expected_rows, expected_snapshots = dd.compact_rows(original)
    actual_rows, actual_snapshots = compact_structured_rows(structured)
    assert actual_rows == expected_rows
    assert actual_snapshots == expected_snapshots
    assert structured == before
    assert structured[0]["features_json"]["owner_generation"] is structured[1]["features_json"]["owner_generation"]


def test_structured_scope_and_existing_reference_contract():
    raw = fixture_rows(2)
    raw += [{**row, "user_id": "other"} for row in fixture_rows(2)]
    structured = intern_features(raw)
    compact, snapshots = compact_structured_rows(structured)
    by_scope = {}
    for node in snapshots:
        by_scope.setdefault(node["user_id"], set()).add(node["snapshot_id"])
    assert not by_scope["u"].intersection(by_scope["other"])
    repeated, extra = compact_structured_rows(intern_features(compact))
    assert repeated == compact
    assert extra == []


def test_storage_comparison_checks_all_expanded_values():
    structured = intern_features(fixture_rows(7))
    baseline = storage_sample(structured, page_size=3)
    candidate = storage_sample(structured, experiment=True, page_size=3)
    for field in ("compacted_sha256", "snapshot_writes_sha256", "inline_bytes", "unique_snapshot_bytes"):
        assert baseline[field] == candidate[field]
    assert baseline["expanded_parity"] and candidate["expanded_parity"]
