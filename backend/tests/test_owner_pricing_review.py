"""Independent review regressions for transitive and unchanged pricing math."""
import random
import pytest
from backend import trade_service as ts,feature_flags as ff
from backend import owner_pricing_execution as ex,owner_evaluation_inputs as inputs
from backend import trade_gen_outlook_evidence as outlook
from backend.tests.test_bilateral_contracts import world
from backend.tests.test_outlook_evidence_candidate import qualified
from backend.tests.test_bilateral_candidate import terms

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
 monkeypatch.setattr(ts,'_cfg',dict(ts._DEFAULT_CFG));monkeypatch.setattr(ff,'_flags_cache',dict(ff.DEFAULT_FLAGS))
 ts._cfg.update(age_pref_mult_u23=1.,age_pref_mult_30plus=1.)

def policy(config=None,crown=True,masks=None):
 return ex.PackagePricingPolicy({**ts._DEFAULT_CFG,**(config or {})},crown,masks or {'a':False,'b':True,'c':False})

@pytest.mark.parametrize('adjusted,frac',[(0,0.25),(1,0.25),(1,0)])
def test_unknown_id_always_refused_by_owned_overpay(adjusted,frac):
 p=policy({'overpay_adjusted':adjusted,'max_overpay_frac':frac})
 with pytest.raises(inputs.UnsupportedOwnerInput,match='uncaptured_pricing_asset'):
  ts.overpay_ok(['not-captured'],['a'],lambda _:1000.,pricing_policy=p)

def test_outlook_companion_overpay_consumes_policy(monkeypatch):
 args=qualified(world(other=('wr','rb'),market={'give':1000,'wr':1100,'rb':100},viewer={'give':800,'wr':1600,'rb':100},partner={'give':1600,'wr':800,'rb':100},positions={'rb':'RB'},outlook='rebuilder'))
 result=ex.capture_owner_pricing(args,model_version=outlook.VERSION);assert result.execution
 original=ts.overpay_ok;calls=[]
 def checked(*a,**kw):
  calls.append(kw.get('pricing_policy'))
  assert kw.get('pricing_policy') is result.execution.pricing_policy
  return original(*a,**kw)
 monkeypatch.setattr(ts,'overpay_ok',checked)
 result.execution.evaluate([terms(args,('give',),('wr','rb'))])
 assert len(calls)>=2

@pytest.mark.parametrize('crown',[False,True])
def test_random_explicit_math_matches_original_live_inputs(monkeypatch,crown):
 rng=random.Random(722);ids=['a','b','c'];masks={'a':False,'b':True,'c':False}
 monkeypatch.setitem(ff._flags_cache,'trade.crown_asset',crown)
 monkeypatch.setattr(ts,'first_round_pick_mask',lambda rows:[masks[x] for x in rows])
 for _ in range(100):
  cfg={**ts._DEFAULT_CFG,'package_adj_gamma_market':rng.uniform(.2,3.),'package_floor_market':rng.random(),'package_floor_cross':rng.random(),'crown_rate_market':rng.random(),'max_overpay_frac':rng.random(),'overpay_adjusted':rng.choice([0.,1.]),'stud_tax_exempt_first_round':rng.choice([0.,1.])}
  p=ex.PackagePricingPolicy(cfg,crown,masks);values={x:rng.uniform(20,12000) for x in ids}
  with ts._cfg_override(cfg),ts.stud_tax_override('market'):
   expected=ts.price_consensus_package(['a','b'],['c'],value_of=values.__getitem__)
   expected_overpay=ts.overpay_ok(['a','b'],['c'],values.__getitem__)
  with ts._cfg_override({'package_floor_market':99.}),ts.stud_tax_override('off'):
   assert ts.price_consensus_package(['a','b'],['c'],value_of=values.__getitem__,pricing_policy=p)==expected
   assert ts.overpay_ok(['a','b'],['c'],values.__getitem__,pricing_policy=p)==expected_overpay

def test_midcall_config_flag_classifier_change_cannot_change_owned_price(monkeypatch):
 p=policy();values={'a':6000.,'b':1000.,'c':6500.}
 expected=ts.price_consensus_package(['a','b'],['c'],value_of=values.__getitem__,pricing_policy=p)
 def change(pid):
  ts._cfg.update(package_floor_market=99.,crown_rate_market=99.);ff._flags_cache['trade.crown_asset']=False
  monkeypatch.setattr(ts,'first_round_pick_mask',lambda _:pytest.fail('live classifier'))
  return values[pid]
 assert ts.price_consensus_package(['a','b'],['c'],value_of=change,pricing_policy=p)==expected

def test_policy_input_maps_detached_and_default_live_caller_unmodified():
 before=dict(ts._cfg);cfg=dict(ts._DEFAULT_CFG);masks={'a':False,'b':True,'c':False};p=ex.PackagePricingPolicy(cfg,True,masks)
 cfg['crown_rate_market']=999.;masks.clear()
 assert p.config['crown_rate_market']!=999. and p.mask(['b'])==[True]
 with pytest.raises(TypeError):p.first_round_by_id['b']=False
 assert ts._cfg==before
