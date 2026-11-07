"""Calibration-only proof that disjoint non-traded slots cannot change.

Kicker/defense assets have no market or offensive replacement value. They remain
in the common capacity count. The normal roster engine and serving are unchanged.
"""
from dataclasses import replace

from .blind_grading import GradingError
from .trade_roster import Asset, ELIGIBILITY, POSITIONS, UNAVAILABLE

FIXED_ELIGIBILITY = {
    **{p:frozenset({p}) for p in ('DT','DE','CB','S')},
    'K': frozenset({'K'}), 'DEF': frozenset({'DEF'}),
    'DL': frozenset({'DL'}), 'LB': frozenset({'LB'}), 'DB': frozenset({'DB'}),
    'IDP_FLEX': frozenset({'DL', 'LB', 'DB'}),
}
FIXED_POSITIONS = frozenset().union(*FIXED_ELIGIBILITY.values())
POLICY = 'unchanged_disjoint_holdings_v1'


def _matching(slots, candidates):
    """Exact cardinality matching, independent of prices and offensive slots."""
    owners = {}
    def place(index, seen):
        for pid in sorted(candidates):
            if pid in seen or not candidates[pid] & FIXED_ELIGIBILITY[slots[index]]:
                continue
            seen.add(pid)
            if pid not in owners or place(owners[pid], seen):
                owners[pid] = index
                return True
        return False
    for index in range(len(slots)):
        place(index, set())
    assigned = {index: pid for pid, index in owners.items()}
    return [{'slot': slot, 'player_id': assigned.get(index)} for index, slot in enumerate(slots)]


def prepare(context, metadata, *, fixed_bounds=()):
    """Project only a proved-disjoint fixed block; leave unknown assets unresolved."""
    original = tuple(context.rules.slots)
    if not original:
        raise GradingError('lineup_unavailable', 409)
    if any(slot not in ELIGIBILITY and slot not in FIXED_ELIGIBILITY for slot in original):
        raise GradingError('provider_lineup_unsupported', 409)
    offensive = tuple(slot for slot in original if slot in ELIGIBILITY)
    if not offensive:
        raise GradingError('provider_lineup_unsupported', 409)
    fixed_slots = tuple(slot for slot in original if slot in FIXED_ELIGIBILITY)
    facts = {}
    held = {pid for team in context.teams.values() for pid in team.roster}
    for pid in sorted(held):
        if pid in context.assets and context.assets[pid].is_pick:
            continue
        row = metadata.get(pid) or {}
        positions = row.get('fantasy_positions') or [row.get('position')]
        if not isinstance(positions, list) or not positions or any(not isinstance(p, str) for p in positions):
            continue
        positions = frozenset(positions)
        if positions & POSITIONS and not positions <= POSITIONS:
            raise GradingError('provider_cross_domain_eligibility', 409)
        if not positions <= FIXED_POSITIONS or not positions:
            continue
        if row.get('player_id') is not None and str(row['player_id']) != pid:
            continue
        existing = context.assets.get(pid)
        if existing and existing.positions & POSITIONS:
            raise GradingError('provider_cross_domain_eligibility', 409)
        injury = str(row.get('injury_status') or '').upper()
        known = isinstance(row.get('active'), bool)
        available = row.get('active') is True and injury not in UNAVAILABLE
        # Empty eligibility prevents any offensive lineup/depth use. Keep the
        # asset in the full roster so active capacity still includes it.
        context.assets[pid] = Asset(pid, frozenset(), 0., startable=False, available=False)
        facts[pid] = {'positions': sorted(positions), 'market_value': None,
            'market_state': 'unpriced_fixed_holding', 'generator_candidate': False,
            'usable_replacement': False, 'available': available,
            'availability_known': known, 'numeric_value_role': 'capacity_sentinel_only'}
    teams, assigned_owner = {}, set()
    for uid, team in context.teams.items():
        fixed = sorted(set(team.roster) & facts.keys())
        if assigned_owner & set(fixed):
            raise GradingError('provider_roster_identity_ambiguous', 409)
        assigned_owner.update(fixed)
        eligible = {pid: frozenset(facts[pid]['positions']) for pid in fixed
                    if pid not in team.inactive and facts[pid]['available']}
        family = (fixed_slots,)
        if fixed_bounds:
            from .calibration_native_lineup import templates
            family = templates(tuple(fixed_bounds), len(fixed_slots))
        assignments = [_matching(template, eligible) for template in family]
        best = max(assignments, key=lambda rows:sum(row['player_id'] is not None for row in rows))
        teams[uid] = {'fixed_ids': fixed, 'active_count': sum(pid not in team.inactive for pid in fixed),
            'known_available_assignment': best,
            'unknown_availability_ids': [pid for pid in fixed if not facts[pid]['availability_known']],
            'basis': 'unchanged_holdings_and_eligibility_not_full_lineup_fit'}
    context.rules = replace(context.rules, slots=offensive)
    return {'policy': POLICY, 'native_fixed_bounds':list(fixed_bounds),
            'native_offensive_bounds':list(getattr(context.rules, 'native_bounds', ())), 'original_slots': list(original), 'fixed_slots': list(fixed_slots),
            'offensive_slots': list(offensive), 'assets': facts, 'teams': teams}


def validate_legs(cards, fixed, context=None):
    """Never silently remove a fixed holding from a proposed exchange."""
    fixed_ids = set(fixed.get('assets') or {})
    for card in cards:
        if fixed_ids & set(card.give_player_ids + card.receive_player_ids):
            raise GradingError('comparison_fixed_asset_exchange', 409)
        if context is not None:
            for pid in card.give_player_ids + card.receive_player_ids:
                asset = context.assets.get(pid)
                if asset is None or (not asset.is_pick and
                        (not asset.positions or not asset.positions <= POSITIONS)):
                    raise GradingError('comparison_nonoffensive_exchange', 409)
        # Calibration does not construct cut plans. A future caller must prove
        # fixed holdings remain intact before enabling any such extension.
        if getattr(card, 'cuts', None) or getattr(card, 'cut_plan', None):
            raise GradingError('comparison_cut_plan_unsupported', 409)


def annotate(cards, fixed, viewer_id):
    if not fixed.get('fixed_slots') and not fixed.get('assets'):
        return
    for card in cards:
        card.roster_evaluation['fixed_lineup'] = {
            'policy': POLICY, 'original_slots': fixed['original_slots'],
            **({'native_family_policy':'native_position_range_family_v1',
                'native_fixed_bounds':fixed['native_fixed_bounds'],
                'native_offensive_bounds':fixed['native_offensive_bounds'],
                'slots_role':'representative_templates_not_complete_native_rules'}
               if fixed.get('native_fixed_bounds') or fixed.get('native_offensive_bounds') else {}),
            'fixed_slots': fixed['fixed_slots'], 'offensive_slots': fixed['offensive_slots'],
            'teams': {uid: fixed['teams'][uid] for uid in (viewer_id, card.target_user_id)},
            'legality_basis': 'offensive_checks_plus_unchanged_disjoint_block',
            'fixed_market_values': 'unknown_not_zero'}
