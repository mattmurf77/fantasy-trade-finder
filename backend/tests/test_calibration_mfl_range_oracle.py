"""Independent reviewer acceptance cases, copied with permission; synthetic only."""
from itertools import product,combinations
from dataclasses import replace
from types import SimpleNamespace as N
import random
import pytest
from backend.calibration_native_lineup import templates,choose,demands,NativeRules
from backend.trade_roster import Asset,Team,Context
from backend.trade_outlook_utility import evaluate_outlook_utility

def vectors(bounds,total):
 return [n for n in product(*(range(lo,hi+1) for _,lo,hi in bounds)) if sum(n)==total]

def objective(bounds,total,assets):
 scores=[]
 for n in vectors(bounds,total):
  selected=[]
  for (pos,_,_),count in zip(bounds,n):
   candidates=sorted((a.value for a in assets if a.positions==frozenset({pos})),reverse=True)
   selected+=candidates[:count]
  scores.append((len(selected),sum(selected)))
 return max(scores)

def test_200_random_singleton_families_exact_against_enumeration():
 rng=random.Random(721)
 for _ in range(200):
  bounds=tuple((pos,rng.randint(0,1),rng.randint(1,3)) for pos in ('QB','RB','WR','TE'))
  total=rng.randint(max(1,sum(lo for _,lo,_ in bounds)),min(7,sum(hi for _,_,hi in bounds)))
  allcounts=vectors(bounds,total)
  observed=templates(bounds,total)
  assert {tuple(row.count(p) for p,_,_ in bounds) for row in observed}==set(allcounts)
  assets=[Asset(str(i),frozenset({rng.choice(('QB','RB','WR','TE'))}),rng.randint(0,100)) for i in range(rng.randint(0,12))]
  selected=choose(bounds,total,assets)
  values={a.id:a.value for a in assets};positions={a.id:next(iter(a.positions)) for a in assets}
  assert len({p for p in selected if p})==sum(p is not None for p in selected)
  assert all(p is None or positions[p]==s for p,s in zip(selected,selected.slots))
  assert (sum(p is not None for p in selected),sum(values[p] for p in selected if p))==objective(bounds,total,assets)
  actual=demands(bounds,total)
  for k in range(1,5):
   for group in combinations(range(4),k):
    demand=min(sum(counts[i] for i in group) for counts in allcounts)
    key='+'.join(sorted(bounds[i][0] for i in group))
    assert actual.get(key,(None,0))[1]==demand

def test_native_utility_can_switch_into_position_absent_from_first_shape():
 bounds=(('QB',0,1),('WR',1,2))
 rules=NativeRules(('WR','WR'),source='observed',capacity=10,native_bounds=bounds)
 assets={p:Asset(p,frozenset({pos}),v) for p,pos,v in [('w1','WR',10),('w2','WR',9),('q','QB',100)]}
 before=Team('me',('w1','w2'));after=replace(before,roster=('w1','q'))
 ctx=Context('me',{'me':before},assets,rules)
 result=evaluate_outlook_utility(before=before,after=after,assets=assets,rules=rules,explicit_outlook='contender',_assign=ctx._assign)
 assert result['components']['lineup_dynasty_proxy']['before']==19
 assert result['components']['lineup_dynasty_proxy']['after']==110
 result=evaluate_outlook_utility(before=before,after=after,assets=assets,rules=rules,explicit_outlook='contender',_assign=ctx._assign,projections={'w1':3,'w2':2,'q':20},projection_basis='fixture',projection_unit='fantasy_points_per_game',projections_fresh=True)
 assert result['components']['current_production']['before']==5
 assert result['components']['current_production']['after']==23

def test_native_context_capacity_counts_fixed_and_inactive():
 bounds=(('WR',1,1),)
 rules=NativeRules(('WR',),source='observed',capacity=2,native_bounds=bounds)
 assets={p:Asset(p,frozenset({'WR'}),10) for p in ['sell','buy','extra','bench']}
 assets['fixed']=Asset('fixed',frozenset(),0,startable=False,available=False)
 ctx=Context('a',{'a':Team('a',('sell','fixed')),'b':Team('b',('buy','extra','bench'))},assets,rules)
 card=N(target_user_id='b',give_player_ids=['sell'],receive_player_ids=['buy','extra'])
 assert 'cuts_required' in ctx.card(card)['teams']['a']['blockers']
 ctx.teams['a']=replace(ctx.teams['a'],inactive=frozenset({'fixed'}));ctx.cache.clear()
 assert 'cuts_required' not in ctx.card(card)['teams']['a']['blockers']

def test_unreachable_declared_max_does_not_create_usable_backup_value():
 from backend import trade_gen_owner as owner
 assets={p:Asset(p,frozenset({pos}),v) for p,pos,v in [('w1','WR',10),('w2','WR',9),('q','QB',100)]}
 search=N(_lineup_assets=assets,_position=lambda p:next(iter(assets[p].positions)))
 team={'slots':('WR','WR'),'inactive':frozenset(),'native_bounds':(('QB',0,2),('WR',2,2))}
 result=owner._Search._lineup(search,assets,team)
 assert result['QB']==0,'QB cannot occur in any legal shape; not a usable backup'

def test_100_random_exchange_structural_blockers_match_independent_subset_oracle():
 rng=random.Random(962)
 for case in range(100):
  bounds=tuple((pos,0,rng.randint(1,3)) for pos in ('QB','RB','WR','TE'))
  total=rng.randint(1,min(5,sum(hi for _,_,hi in bounds)))
  family=vectors(bounds,total)
  slots=tuple(p for (p,_,_),n in zip(bounds,family[0]) for _ in range(n))
  assets={str(i):Asset(str(i),frozenset({rng.choice(('QB','RB','WR','TE'))}),10+i,startable=i%4!=0,available=i%7!=0) for i in range(16)}
  before=set(str(i) for i in range(8));after=(before-{'1'})|{'9'}
  ctx=Context('a',{'a':Team('a',tuple(sorted(before))),'b':Team('b',tuple(str(i) for i in range(8,16)))},assets,NativeRules(slots,'observed',100,native_bounds=bounds))
  result=ctx.card(N(target_user_id='b',give_player_ids=['1'],receive_player_ids=['9']))['teams']['a']
  expected=[]
  for k in range(1,5):
   for indexes in combinations(range(4),k):
    group={bounds[i][0] for i in indexes};d=min(sum(row[i] for i in indexes) for row in family)
    if not d:continue
    key='+'.join(sorted(group))
    count=lambda ids,quality:sum(bool(assets[p].positions&group) and assets[p].available and (assets[p].startable or not quality) for p in ids)
    for quality,label in [(False,'legal_deficits'),(True,'deficits')]:
     if max(0,d-count(after,quality))>max(0,d-count(before,quality)):expected.append(label+':'+key)
    if count(after,True)<min(d+1,count(before,True)):expected.append('backup_depth:'+key)
  assert result['blockers']==sorted(set(expected))
