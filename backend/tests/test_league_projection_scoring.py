from decimal import Decimal
import pytest
from backend.league_projections.core import score, split_points, semantic_facts, Unavailable
from backend.league_projections.provider import LINEAR_PROJECTED_EVENTS


def test_decimal_custom_idp_and_negative_scoring_preserves_small_components():
    assert score({'pass_yd':'.1','idp_tkl':'2','fum_lost':'1'},
                 {'pass_yd':'.04','idp_tkl':'.5','fum_lost':'-2'},
                 {'pass_yd','idp_tkl','fum_lost'}) == Decimal('-0.996')
    assert split_points(-2, -35) == Decimal('-2.35')
    assert split_points(0, -5) == Decimal('-.05')
    with pytest.raises(Unavailable): split_points(-2, 35)


def test_unknown_expected_event_and_nonlinear_bonus_never_become_zero():
    with pytest.raises(Unavailable, match='missing_scoring_stat'):
        score({}, {'idp_blk_kick':3}, {'idp_blk_kick'})
    assert 'bonus_pass_yd_300' not in LINEAR_PROJECTED_EVENTS
    with pytest.raises(Unavailable, match='unsupported_scoring'):
        score({'bonus_pass_yd_300':1}, {'bonus_pass_yd_300':4}, LINEAR_PROJECTED_EVENTS)


def test_semantic_reuse_keeps_kickoff_and_provider_revision():
    a={'captured_at':'old','input':{'captured_at':'old','kickoff_at':'game1','source_updated_at':'revision1','stats':{'rec':2}},'source_hash':'derived1'}
    b={'captured_at':'new','input':{'captured_at':'new','kickoff_at':'game1','source_updated_at':'revision1','stats':{'rec':2}},'source_hash':'derived2'}
    assert semantic_facts(a)==semantic_facts(b)
    b['input']['source_updated_at']='revision2'
    assert semantic_facts(a)!=semantic_facts(b)
