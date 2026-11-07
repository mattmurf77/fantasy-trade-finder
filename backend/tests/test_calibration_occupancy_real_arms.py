from dataclasses import replace
import pytest
from backend.calibration_roster_coverage import add_unranked_occupancy
from backend.outlook_calibration_adapter import VERSIONS
from backend.tests.test_calibration_round_adapter_execution import captured
from backend.tests.test_owner_generator_routes import harness, owner_harness
from backend.tests.test_owner_only_routes import exclusive, large_exclusive

@pytest.mark.parametrize('version', VERSIONS)
def test_real_engines_keep_unpriced_holdings_out_of_legs_and_proofs_qualified(captured,version):
    metadata={}
    for uid,team in list(captured.roster_context.teams.items()):
        pid='unpriced-'+uid
        metadata[pid]={'position':'WR','fantasy_positions':['WR'],'active':True}
        captured.roster_context.teams[uid]=replace(team,roster=team.roster+(pid,))
        if uid==captured.owner_context['user_id']:
            captured.owner_context['user_roster'].append(pid)
        for member in captured.owner_context['league'].members:
            if member.user_id==uid: member.roster.append(pid)
    blocked, before=captured.run_arm(version)
    assert before['native_count']>0 and before['roster_count']==0 and not blocked
    facts=add_unranked_occupancy(captured.roster_context,metadata)
    captured.source['unpriced_occupancy']=facts
    cards,after=captured.run_arm(version)
    assert after['native_count']==before['native_count']
    assert cards and after['roster_count']>0
    assert not set(facts)&set(captured.owner_context['players'])
    for card in cards:
        assert not set(facts)&set(card.give_player_ids+card.receive_player_ids)
        assert card.owner_evaluation.matches(card)
        assert card.owner_evaluation.model_identity[1]==version
        assert card.roster_evaluation['value_basis']=='priced_assets_only_with_unpriced_occupancy'
        assert card.roster_evaluation['unpriced_assets_are_generator_candidates'] is False
