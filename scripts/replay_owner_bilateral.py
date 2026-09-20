"""Offline old/new constructor comparison from a private frozen owner request.

No server import, provider access, production connection, or acceptance claims.
Usage: python -m scripts.replay_owner_bilateral --snapshot PRIVATE.json
       --config LIVE_READBACK.json --output NEW_DIRECTORY
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.environ['DATABASE_URL'] = 'sqlite:///' + str((args.output / 'isolated.sqlite3').resolve())

    def no_network(*_args, **_kwargs):
        raise RuntimeError('Offline replay forbids network')
    socket.socket.connect = no_network
    from backend import trade_service as ts, trade_gen_owner as old, trade_gen_bilateral as new
    from backend import feature_flags as ff, database as db
    from backend.ranking_service import Player
    db.metadata.create_all(db.engine)
    capture = json.loads(args.config.read_text())
    cfg = {r['key']: r['value'] for r in capture['config']}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    ff._flags_cache = capture['flags']['flags']
    raw = json.loads(args.snapshot.read_text())['owner_request']
    k = copy.deepcopy(raw['input'])
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop('players').items()}
    sources = k.get('opponent_sources') or {}
    members = [ts.LeagueMember(m['id'], m['id'], m['roster'], m['elo'], bool(m['elo']),
        confidence_sources=sources.get(m['id'], {})) for m in k.pop('members')]
    # No route/significance/pick-ledger reconstruction is claimed. This compares
    # the constructors on the same frozen asset universe, not live serving.
    k.update(players=players, league=ts.League('frozen-replay', 'Private replay', 'espn', members), config=cfg)
    for field in ('past_decision_keys', 'exclusion_keys'):
        k[field] = {(frozenset(a), frozenset(b)) for a, b in k[field]}
    result = {'snapshot_sha256': hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        'captured_at': raw.get('captured_at'), 'configuration_checked_at': capture['checked_at'],
        'limitations': ['Frozen reconstructed input, not fresh live rosters',
            'No route/legality/significance gates or complete pick-ledger replay',
            'No acceptance labels; support scores are not probabilities'], 'arms': {}}
    for arm, generator in [('owner_v1', old.generate_owner_trades), ('owner_v2_bilateral', new.generate_bilateral_trades)]:
        start = time.perf_counter()
        cards, report = generator(**k)
        rows = []
        for c in cards:
            d = c.owner_evaluation.as_dict()
            rows.append({'give': c.give_player_ids, 'receive': c.receive_player_ids,
                'partner': c.target_user_id, 'proof': d})
        (args.output / (arm + '.private.json')).write_text(json.dumps(rows))
        heads = Counter(max(c.give_player_ids, key=lambda p: k['seed_elo'][p]) for c in cards[:50])
        result['arms'][arm] = {'cards': len(cards), 'seconds': round(time.perf_counter() - start, 3),
            'shape': dict(Counter(f'{len(c.give_player_ids)}x{len(c.receive_player_ids)}' for c in cards)),
            'top50_distinct_sent_heads': len(heads), 'top50_max_sent_head_count': max(heads.values(), default=0),
            'evaluated': report.as_dict()['evaluated'], 'rejections': report.as_dict()['rejections']}
        print(json.dumps({arm: result['arms'][arm]}), flush=True)
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
