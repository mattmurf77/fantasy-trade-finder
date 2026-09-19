"""Hot-path work stays bounded without stale flags or changed owner decisions."""
from collections import defaultdict
from unittest.mock import patch

import pytest

from backend import feature_flags as flags, trade_gen_owner as owner
from backend.tests.test_trade_gen_owner import world


def test_flag_reads_follow_reload_and_do_not_copy_or_scan_registry(monkeypatch):
    cache = dict(flags.DEFAULT_FLAGS)
    monkeypatch.setattr(flags, '_flags_cache', cache)
    with patch.object(flags, '_key_to_attr', side_effect=AssertionError('registry scan')), \
         patch.object(flags, 'flags_dict', side_effect=AssertionError('flag-map copy')):
        assert flags.FLAGS.trade_math_qb_tax is False
        monkeypatch.setattr(flags, '_compute_flags', lambda: {**cache, 'trade_math.qb_tax': True})
        flags.reload()
        assert flags.FLAGS.trade_math_qb_tax is True
        assert flags.FLAGS['trade_math.qb_tax'] is True
        assert flags.is_enabled('unknown') is False
    detached = flags.flags_dict()
    detached['trade_math.qb_tax'] = False
    assert flags.FLAGS.trade_math_qb_tax is True
    with pytest.raises(AttributeError):
        flags.FLAGS.missing_flag


def test_flags_initialize_lazily_and_support_declared_extension(monkeypatch):
    monkeypatch.setattr(flags, '_flags_cache', None)
    monkeypatch.setattr(flags, '_compute_flags', lambda: {'test.added_flag': True})
    monkeypatch.setattr(flags, 'DEFAULT_FLAGS', {**flags.DEFAULT_FLAGS, 'test.added_flag': False})
    assert flags.FLAGS.test_added_flag is True


def uncached_lineup(self, roster, team):
    """Pre-optimization lineup calculation, independent of prepared facts."""
    from backend.trade_roster import Asset, ELIGIBILITY, UNAVAILABLE, assign
    usable = []
    for pid in roster:
        player = self.players.get(pid)
        pos = 'PICK' if self.ts.is_pick_asset(player) else getattr(player, 'position', None)
        if pos in owner._POSITIONS and pid in self.market and pid not in team['inactive']:
            status = str(getattr(player, 'injury_status', '') or '').upper()
            if status not in UNAVAILABLE:
                usable.append(Asset(pid, frozenset([pos]), self.market[pid]
                    * self.ts.age_now_mult(pos, getattr(player, 'age', None))))
    selected = {pid for pid in assign(team['slots'], usable) if pid}
    result, bench = dict.fromkeys(owner._POSITIONS, 0.0), defaultdict(list)
    for asset in usable:
        pos = self.players[asset.id].position
        if asset.id in selected:
            result[pos] += asset.value
        else:
            bench[pos].append(asset.value)
    for pos, values in bench.items():
        if any(pos in ELIGIBILITY[s] for s in team['slots']):
            result[pos] += .15 * max(values)
    return result


@pytest.mark.parametrize('slots', [None, ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPER_FLEX']])
def test_prepared_player_facts_preserve_complete_search_and_fresh_inputs(monkeypatch, slots):
    ids = [f'{side}{i}' for side in ('g', 'r') for i in range(8)]
    spec = {pid: (['QB', 'RB', 'WR', 'TE'][i % 4], 23 + i % 9, 300 + (i % 7) * 350)
            for i, pid in enumerate(ids)}
    prefs = {uid: {'starter_slots': slots, 'inactive_ids': [ids[6 if uid == 'me' else 14]]}
             for uid in ('me', 'opp')}
    kwargs = world(spec, ids[:8], ids[8:], manager_preferences=prefs,
        viewer={p: v * (.85 if p.startswith('g') else 1.15) for p, (_, _, v) in spec.items()},
        opponent={p: v * (1.15 if p.startswith('g') else .85) for p, (_, _, v) in spec.items()})
    def run():
        cards, report = owner.generate_owner_trades(**kwargs)
        return [c.owner_evaluation.as_dict() for c in cards], report.as_dict()
    for status in (None, 'OUT', 'Questionable'):
        kwargs['players']['g0'].injury_status = status
        optimized = run()
        with monkeypatch.context() as m:
            m.setattr(owner._Search, '_lineup', uncached_lineup)
            reference = run()
        assert optimized == reference
