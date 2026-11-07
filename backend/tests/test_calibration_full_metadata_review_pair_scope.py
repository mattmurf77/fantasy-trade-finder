"""Independent synthetic review regressions, copied with reviewer authorization."""
from copy import deepcopy
import json
import pytest
from backend import calibration_provider_capture as provider
from backend.tests.test_calibration_provider_parsers import espn_raw,xwalk
from backend.tests.test_calibration_round_adapter_execution import captured
from backend.tests.test_owner_generator_routes import harness,owner_harness
from backend.tests.test_owner_only_routes import exclusive,large_exclusive
from backend.outlook_calibration_adapter import VERSIONS

def key(c):return c.target_user_id,tuple(c.give_player_ids),tuple(c.receive_player_ids)

@pytest.mark.parametrize('version',VERSIONS)
def test_pair_mask_keeps_inventory_budget_and_supported_order(captured,version,monkeypatch):
 from backend import calibration_fixed_lineup as fixed,deck_quality,trade_bilateral_presentment as presentment
 boundaries=[];quality_calls=[];present_calls=[]
 old_validate=fixed.validate_legs;old_quality=deck_quality.filter_deck;old_present=presentment.present
 def validate(cards,*a,**kw):
  boundaries.append([key(c) for c in cards]);return old_validate(cards,*a,**kw)
 def quality(cards,**kw):
  quality_calls.append(True);return old_quality(cards,**kw)
 def present(cards,**kw):
  present_calls.append(kw);return old_present(cards,**kw)
 monkeypatch.setattr(fixed,'validate_legs',validate);monkeypatch.setattr(deck_quality,'filter_deck',quality);monkeypatch.setattr(presentment,'present',present)
 baseline,initial=captured.run_arm(version)
 assert baseline
 target=baseline[0].target_user_id
 captured.source['fixed_lineup']={'unsupported_teams':{target:{'reason':'provider_cross_domain_eligibility','holdings':{'dual':{'original':['WR','DB']}}}}}
 result,diag=captured.run_arm(version)
 assert diag['native_count']==initial['native_count']
 assert {k:v for k,v in diag['generator'].items() if k!='elapsed_seconds'}=={k:v for k,v in initial['generator'].items() if k!='elapsed_seconds'}
 assert diag['unsupported_participant_count']==1 and diag['unsupported_pair_cards']>0
 assert all(c.target_user_id!=target for c in result)
 # Pair eligibility preserves native relative order. Normal downstream repeat
 # deferral is recomputed on supported cards; final old-deck subsequence is not required.
 assert boundaries[1]==[row for row in boundaries[0] if row[0]!=target]
 assert len(quality_calls)==2 and present_calls==[{'generator_version':version}]*2
 assert {key(c) for c in result}=={key(c) for c in baseline if c.target_user_id!=target}


def test_espn_offense_only_preserves_original_native_eligibility_evidence(xwalk):
 raw=espn_raw();entry=raw['teams'][0]['roster']['entries'][0]['playerPoolEntry']['player']
 entry['eligibleSlots']+=[14,15];original=list(entry['eligibleSlots'])
 snap=provider.parse_espn(raw,league_id='123',user_id='me',team_id=1,xwalk=xwalk)
 def lists(value):
  if isinstance(value,list):
   yield value
   for v in value:yield from lists(v)
  if isinstance(value,dict):
   for v in value.values():yield from lists(v)
 assert original in list(lists(snap.provenance)),'Original native defensive eligibility discarded without effective-slot proof'
 assert not snap.provenance.get('unsupported_native_eligibility')


def test_espn_configured_defense_retains_cross_domain_marker(xwalk):
 raw=espn_raw();raw['settings']['rosterSettings']['lineupSlotCounts']['14']=1
 entry=raw['teams'][0]['roster']['entries'][0]['playerPoolEntry']['player'];entry['eligibleSlots']+=[14,15]
 snap=provider.parse_espn(raw,league_id='123',user_id='me',team_id=1,xwalk=xwalk)
 marker=snap.provenance['unsupported_native_eligibility']['a']
 assert marker['native_eligible_slots']==entry['eligibleSlots'] and marker['extra_fixed_slots']==[14]
 assert 'a' not in snap.fixed_metadata
