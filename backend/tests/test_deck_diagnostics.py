"""Storage incident: lossless scoped dedup, atomic writes, expiry and privacy.

Regression: repeating full request/generation evidence on hundreds of cards
must not multiply shared payload storage. Core features/valuations stay intact.
"""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError

from backend import database as db
from backend.deck_diagnostics import compact_rows, expand_features, REFERENCE_KEY


def rows(n=12, user='u', job='j', days=0):
    stamp = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    shared = {f'config_{k}': k / 13 for k in range(350)}
    return [dict(impression_id=f'{user}-{job}-{i}', user_id=user, league_id='l',
                 deck_job_id=job, card_index=i, propensity=1., served_at=stamp,
                 valuation_json=json.dumps({'give': [str(i)], 'value': 12.3}),
                 features_json=json.dumps({'partner_user_id': 'other',
                     'taste_attrs': ['RB'], 'give_value': 200.,
                     'owner_request': {'input': {'config': shared, 'assets': [str(i)]}},
                     'owner_generation': {'config': shared, 'emitted': n},
                     'roster_evaluation': {'result': 'pass', 'rosters': shared},
                     'owner_experiment': None})) for i in range(n)]


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine('sqlite:///:memory:')
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, 'engine', eng)
    yield eng
    eng.dispose()


def test_roundtrip_and_payload_budget():
    original = rows(100)
    before = copy.deepcopy(original)
    compact, snapshots = compact_rows(original)
    mapping = {s['snapshot_id']: s['payload_json'] for s in snapshots}
    for old, new in zip(original, compact):
        assert expand_features(json.loads(new['features_json']), mapping) == json.loads(old['features_json'])
        assert new['valuation_json'] == old['valuation_json']
        assert {k:v for k,v in new.items() if k != 'features_json'} == {k:v for k,v in old.items() if k != 'features_json'}
    assert original == before  # no mutation of live caller evidence
    stored = sum(len(r['features_json']) for r in compact) + sum(len(s['payload_json']) for s in snapshots)
    assert stored < .15 * sum(len(r['features_json']) for r in original)
    assert len(snapshots) < 110  # repeated subtrees don't become per-card nodes


def test_scope_and_idempotence():
    compact, snapshots = compact_rows(rows() + rows(user='v') + rows(job='k'))
    by_scope = {}
    for s in snapshots:
        by_scope.setdefault((s['user_id'],s['deck_job_id']), set()).add(s['snapshot_id'])
    assert len(by_scope) == 3
    assert not (by_scope['u','j'] & by_scope['v','j'])
    assert not (by_scope['u','j'] & by_scope['u','k'])
    again, extra = compact_rows(compact)
    assert again == compact and extra == []


def test_legacy_null_and_corrupt_features_unchanged():
    for value in ('{}', 'null', '[1,2]', 'bad-json', None):
        original = rows(1)
        original[0]['features_json'] = value
        compact, snapshots = compact_rows(original)
        assert compact == original and snapshots == []


def test_atomic_write_and_owner_read(engine):
    original = rows()
    db.save_deck_impressions(original)
    assert db.load_deck_diagnostics('u-j-0', 'u') == json.loads(original[0]['features_json'])
    assert db.load_deck_diagnostics('u-j-0', 'v') is None
    with engine.connect() as c:
        before = c.scalar(select(func.count()).select_from(db.deck_diagnostic_snapshots_table))
    bad = rows(job='fail')
    bad[1]['impression_id'] = bad[0]['impression_id']
    with pytest.raises(IntegrityError):
        db.save_deck_impressions(bad)
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.deck_impressions_table)) == len(original)
        assert c.scalar(select(func.count()).select_from(db.deck_diagnostic_snapshots_table)) == before


def test_retention_only_debug_nodes_and_batch_bound(engine):
    old = rows(job='old', days=20)
    fresh = rows(job='fresh')
    db.save_deck_impressions(old + fresh)
    db.save_deck_outcome('u-old-0', 'viewed', acting_user_id='u')
    assert db.purge_deck_diagnostics(days=0) == 0
    assert db.purge_deck_diagnostics(days=14, batch_size=1) == 1
    while db.purge_deck_diagnostics(days=14):
        pass
    assert db.load_deck_diagnostics('u-fresh-0','u') == json.loads(fresh[0]['features_json'])
    expired = db.load_deck_diagnostics('u-old-0','u')
    assert expired['owner_request']['diagnostic_status'] == 'expired_or_missing'
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 24
        assert c.scalar(select(func.count()).select_from(db.deck_outcomes_table)) == 1
        assert c.scalar(select(db.deck_impressions_table.c.valuation_json).where(
            db.deck_impressions_table.c.impression_id == 'u-old-0')) == old[0]['valuation_json']


def test_export_and_delete_include_scoped_snapshots(engine):
    from backend import accounts
    db.upsert_user(sleeper_user_id='u')
    db.upsert_user(sleeper_user_id='v')
    db.save_deck_impressions(rows() + rows(user='v'))
    exported = accounts.export_user_data('u')['tables']
    snaps = exported['deck_diagnostic_snapshots']
    assert snaps and all(s['user_id'] == 'u' for s in snaps)
    mapping = {s['snapshot_id']:s['payload_json'] for s in snaps}
    assert expand_features(json.loads(exported['deck_impressions'][0]['features_json']), mapping)['owner_request']['input']['assets'] == ['0']
    accounts.delete_user_data('u')
    with engine.connect() as c:
        users = set(c.execute(select(db.deck_diagnostic_snapshots_table.c.user_id)).scalars())
        assert users == {'v'}


def test_maintenance_preserves_core_and_is_resumable(engine):
    from scripts.compact_deck_diagnostics import compact_batch
    original = rows()
    with engine.begin() as c:
        c.execute(db.deck_impressions_table.insert(), original)
    with engine.begin() as c:
        batch = [dict(r._mapping) for r in c.execute(select(db.deck_impressions_table))]
        assert compact_batch(c, batch)[0] == len(original)
    with engine.begin() as c:
        batch = [dict(r._mapping) for r in c.execute(select(db.deck_impressions_table))]
        assert compact_batch(c, batch) == (0, 0)
    for old in original:
        assert db.load_deck_diagnostics(old['impression_id'], 'u') == json.loads(old['features_json'])
    with engine.connect() as c:
        for new in c.execute(select(db.deck_impressions_table)).mappings():
            old = next(r for r in original if r['impression_id'] == new['impression_id'])
            for k in old:
                if k != 'features_json':
                    assert old[k] == new[k]


def test_roundtrip_across_insert_pages_and_mixed_packing(engine):
    original = rows(215)
    # Last page changes repetition counts, but an already-stored raw hash
    # must keep expanding to the same value even if its packed form differs.
    for i, row in enumerate(original):
        f = json.loads(row['features_json'])
        f['owner_generation']['rare'] = ({'x': 'y' * 1100} if i % 100 == 0 else None)
        row['features_json'] = json.dumps(f)
    db.save_deck_impressions(original)
    for index in (0, 1, 99, 100, 101, 199, 200, 214):
        old = original[index]
        assert db.load_deck_diagnostics(old['impression_id'], 'u') == json.loads(old['features_json'])
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 215


def test_postgres_maintenance_uses_one_bounded_update(monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.dialects import postgresql
    from scripts.compact_deck_diagnostics import compact_batch
    calls = []
    class Connection:
        dialect = postgresql.dialect()
        def execute(self, statement):
            sql = str(statement.compile(dialect=self.dialect))
            calls.append(sql)
            return SimpleNamespace(rowcount=12)
    monkeypatch.setattr(db, '_save_deck_diagnostic_snapshots', lambda *args: None)
    assert compact_batch(Connection(), rows())[0] == 12
    assert len(calls) == 1
    assert 'FROM (VALUES' in calls[0]


def test_snapshot_insert_uses_bounded_multivalues():
    """ON CONFLICT executemany otherwise makes one WAN round trip per node."""
    from sqlalchemy.dialects import postgresql
    statements = []
    class Connection:
        dialect = postgresql.dialect()
        def execute(self, statement, *parameters):
            assert not parameters, 'executemany reintroduces per-node round trips'
            statements.append(statement.compile(dialect=self.dialect))
    snapshots = [dict(snapshot_id=str(i), user_id='u', deck_job_id='j',
                      created_at='2026-09-15T00:00:00+00:00', payload_json='{}')
                 for i in range(215)]
    db._save_deck_diagnostic_snapshots(Connection(), snapshots)
    assert [len(s.params) for s in statements] == [500, 500, 75]
    assert all('ON CONFLICT (snapshot_id) DO NOTHING' in str(s) for s in statements)
