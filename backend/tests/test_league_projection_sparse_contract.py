from decimal import Decimal
import pytest
from backend.league_projections.scoring import normalize, OFFENSE, CONTRACT
from backend.league_projections.core import score, Unavailable
from backend.season_forecasts import normalize_scoring_for_slots


def row(stats, **updates):
    stats = {'gp': 1, **stats}
    for key, reception in [('pts_std', 0), ('pts_half_ppr', .5), ('pts_ppr', 1)]:
        co = {k: Decimal(v) for k, v in OFFENSE.items()}; co['rec'] = Decimal(str(reception))
        stats[key] = str(sum((co[k] * Decimal(str(stats[k])) for k in co if k in stats), Decimal(0)).quantize(Decimal('.01')))
    return {'company': 'rotowire', 'category': 'proj', 'stats': stats, **updates}


def decode(raw, required=OFFENSE, positions=('QB',), policy=CONTRACT):
    return normalize(raw, set(required), set(OFFENSE) | {'idp_sack', 'fgm_50p'}, policy=policy, positions=positions)


@pytest.mark.parametrize('position,stats', [('QB', {'pass_yd': 250, 'pass_td': 2, 'pass_int': 1}),
    ('RB', {'rush_yd': 80, 'rush_td': .5, 'rec': 3, 'rec_yd': 20}),
    ('WR', {'rec': 6, 'rec_yd': 85, 'rec_td': .5, 'pass_yd': 4}), ('TE', {'rec': 4, 'rec_yd': 40})])
def test_mixed_offense_custom_scoring_preserves_direct_and_declares_omissions(position, stats):
    result = decode(row(stats), positions=(position,))
    assert result['missing_keys'] == []
    coefficients = {k: v for k, v in OFFENSE.items()}; coefficients['rec'] = '.5'
    expected = sum((Decimal(v) * Decimal(str(stats.get(k, 0))) for k, v in coefficients.items()), Decimal(0))
    assert score(result['stats'], coefficients, result['supported_keys']) == expected
    for key in coefficients:
        assert result['stat_provenance'][key]['basis'] == ('direct' if key in stats else 'model_assumed')
    assert len(result['aggregate_identity']) == 3


def test_whole_missing_or_wrong_source_or_unreconciled_forecast_never_becomes_zero():
    cases = [row({}), row({'pass_yd': 200}, company='other'), row({'pass_yd': 200}, category='actual')]
    missing_total = row({'pass_yd': 200}); del missing_total['stats']['pts_ppr']; cases.append(missing_total)
    wrong_total = row({'pass_yd': 200}); wrong_total['stats']['pts_ppr'] = 50; cases.append(wrong_total)
    for raw in cases:
        with pytest.raises(Unavailable): decode(raw)


def test_missing_rare_idp_kicker_and_nonlinear_fields_stay_unknown():
    required = {'pass_yd', 'idp_blk_kick', 'fgm_50p', 'bonus_pass_yd_300', 'st_ff'}
    result = decode(row({'pass_yd': 200}), required)
    assert set(result['missing_keys']) == required - {'pass_yd'}
    assert all(result['stat_provenance'][k]['value'] is None for k in result['missing_keys'])
    with pytest.raises(Unavailable): score(result['stats'], {k: 1 for k in required}, result['supported_keys'])


def test_strict_policy_keeps_omissions_unknown_and_kicker_derivation_explicit():
    assert 'rec' in decode(row({'pass_yd': 200}), policy='strict_supplied_v1')['missing_keys']
    result = decode(row({'fga': 2.5, 'fgm': 2, 'fgm_50p': .3}), {'fgmiss', 'fgm_50p', 'idp_int'}, positions=('K',))
    assert result['stats'] == {'fgm_50p': '0.3', 'fgmiss': '0.5'}
    assert result['stat_provenance']['fgmiss']['basis'] == 'derived'
    assert result['missing_keys'] == ['idp_int']


def test_inactive_slot_registry_is_finite_and_preserves_rare_player_events():
    scoring = {'rec': 1, 'fgm_50p': 5, 'pts_allow_0': 10, 'st_ff': 1, 'idp_int': 3, 'fum_rec_td': 6, 'unknown_def_bonus': 2}
    active = normalize_scoring_for_slots(scoring, ['QB', 'RB', 'WR', 'TE', 'FLEX'])
    assert set(active) == {'rec', 'st_ff', 'idp_int', 'fum_rec_td', 'unknown_def_bonus'}
    assert 'fgm_50p' in normalize_scoring_for_slots(scoring, ['K'])


@pytest.mark.parametrize('stats', [{'gp': True, 'pass_yd': 0}, {'pass_att': None}, {'pass_att': float('nan')}])
def test_invalid_population_evidence_is_rejected(stats):
    raw = {'company':'rotowire','category':'proj','stats':{'gp':1,'pts_std':0,'pts_half_ppr':0,'pts_ppr':0,**stats}}
    with pytest.raises(Unavailable): decode(raw)


@pytest.mark.parametrize('primary,positions,expected,basis', [('TE',['TE'],4,'derived'), ('WR',['WR','TE'],0,'inapplicable'), ('TE',['TE','WR'],4,'derived')])
def test_position_bonus_uses_primary_position_not_dual_eligibility(primary,positions,expected,basis):
    result=normalize(row({'rec':4,'rec_yd':40}), {'bonus_rec_te'}, {'bonus_rec_te'}, policy=CONTRACT,positions=positions,primary_position=primary)
    assert Decimal(result['stats']['bonus_rec_te']) == expected
    assert result['stat_provenance']['bonus_rec_te']['basis'] == basis
    missing=normalize(row({'rec':4,'rec_yd':40}), {'bonus_rec_te'}, {'bonus_rec_te'}, policy=CONTRACT,positions=positions)
    assert missing['missing_keys']==['bonus_rec_te']


def test_supplied_position_bonus_cannot_contradict_native_primary_semantics():
    with pytest.raises(Unavailable, match='inconsistent_position_bonus'):
        normalize(row({'rec':4,'rec_yd':40,'bonus_rec_te':4}), {'bonus_rec_te'}, {'bonus_rec_te'}, policy=CONTRACT,positions=['WR','TE'],primary_position='WR')


def test_advertised_missing_event_is_incomplete_but_unknown_bonus_unsupported():
    result=decode(row({'pass_yd':200}), {'idp_sack','unknown_bonus'})
    with pytest.raises(Unavailable) as missing:
        score(result['stats'], {'idp_sack':1}, result['supported_keys'])
    assert missing.value.state=='incomplete_projections' and missing.value.reason=='missing_scoring_stat'
    with pytest.raises(Unavailable) as unknown:
        score(result['stats'], {'unknown_bonus':1}, result['supported_keys'])
    assert unknown.value.reason=='unsupported_scoring'


@pytest.mark.parametrize('primary,eligible,bonus',[('FB',['RB'],'bonus_rec_rb'),('DB',['WR'],'bonus_rec_wr'),('FB',['RB'],'bonus_rec_te'),('DB',['WR'],'bonus_rec_te')])
def test_known_native_primary_does_not_inherit_fantasy_eligibility_premium(primary,eligible,bonus):
    result=normalize(row({'rec':3,'rec_yd':30}),{bonus},{bonus},policy=CONTRACT,positions=eligible,primary_position=primary)
    assert result['stats'][bonus]=='0'
    assert result['stat_provenance'][bonus]['basis']=='inapplicable'
