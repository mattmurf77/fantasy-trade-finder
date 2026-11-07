"""Complete calibration roster occupancy without expanding the ranked market.

A known held NFL skill player can occupy a slot even when outside the ranked
pool. Its missing price is NEVER a zero-valued market observation or a usable
starter/replacement. This helper is private to the strict calibration capture.
"""
from .trade_roster import Asset, POSITIONS, UNAVAILABLE


def add_unranked_occupancy(context, metadata):
    """Add only metadata-resolved held assets; return private missing-price facts."""
    facts = {}
    held = {pid for team in context.teams.values() for pid in team.roster}
    for pid in sorted(held - set(context.assets)):
        row = metadata.get(pid) or {}
        positions = row.get('fantasy_positions') or [row.get('position')]
        if (not isinstance(positions, list) or not positions
                or any(p not in POSITIONS for p in positions)
                or (row.get('player_id') is not None and str(row['player_id']) != pid)):
            continue  # Still unresolved: the existing common gate refuses it.
        injury = str(row.get('injury_status') or '').upper()
        available = row.get('active') is True and injury not in UNAVAILABLE
        context.assets[pid] = Asset(pid, frozenset(positions), 0.,
                                    startable=False, available=available)
        facts[pid] = {'positions': sorted(set(positions)),
                      'market_value': None, 'market_state': 'unknown_outside_ranked_pool',
                      'numeric_value_role': 'internal_occupancy_sentinel_only',
                      'generator_candidate': False, 'usable_replacement': False,
                      'availability_basis': 'fresh_provider_active_and_injury_metadata',
                      'available': available}
    return facts


def annotate_coverage(cards, facts, context):
    """Prevent roster diagnostics from presenting partial sums as full prices."""
    if not facts:
        return
    for card in cards:
        held = {p for uid in (context.viewer_id, card.target_user_id)
                for p in context.teams[uid].roster}
        unknown = sorted(held & set(facts))
        if unknown:
            card.roster_evaluation.update(
                value_basis='priced_assets_only_with_unpriced_occupancy',
                unpriced_occupancy_ids=unknown,
                unpriced_assets_are_generator_candidates=False)
