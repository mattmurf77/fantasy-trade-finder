"""Exact finite native position ranges, opted into only by calibration capture.

Single native positions and separate offense/defense totals are required. A range
family is a union of legal templates, never one guessed FLEX formation.
"""
from dataclasses import dataclass
from functools import lru_cache
from itertools import product, combinations
import math
from .trade_roster import Rules, assign

POLICY = 'native_position_range_family_v1'
OFFENSE = frozenset({'QB','RB','WR','TE'})
DEFENSE = frozenset({'DT','DE','LB','CB','S'})

@dataclass(frozen=True)
class NativeRules(Rules):
    native_bounds: tuple = ()

class Assignment(list):
    def __init__(self, ids, slots):
        super().__init__(ids)
        self.slots = tuple(slots)

@lru_cache(maxsize=128)
def templates(bounds, total):
    if not bounds or not isinstance(total,int) or isinstance(total,bool) or not 1 <= total <= 32:
        raise ValueError('invalid_native_lineup')
    positions = [p for p,_,_ in bounds]
    if len(set(positions)) != len(positions) or len(positions)>9:
        raise ValueError('invalid_native_lineup')
    if any(type(lo) is not int or type(hi) is not int or not 0<=lo<=hi<=32 for _,lo,hi in bounds):
        raise ValueError('invalid_native_lineup')
    # Bound work before taking the Cartesian product; unsupported is explicit.
    if math.prod(hi-lo+1 for _,lo,hi in bounds)>100000:
        raise ValueError('native_lineup_family_too_large')
    rows=[]
    for counts in product(*(range(lo,hi+1) for _,lo,hi in bounds)):
        if sum(counts)==total:
            rows.append(tuple(p for (p,_,_),n in zip(bounds,counts) for _ in range(n)))
            if len(rows)>256:raise ValueError('native_lineup_family_too_large')
    if not rows:raise ValueError('infeasible_native_lineup')
    return tuple(rows)

def choose(bounds,total,assets):
    """Maximum unique occupancy, then dynasty proxy; deterministic family ties."""
    assets=sorted(assets,key=lambda a:a.id)
    allowed={p for p,_,hi in bounds if hi}
    if any(len(a.positions & allowed)>1 for a in assets):
        raise ValueError('native_multi_position_unsupported')
    values={a.id:max(0,a.value) for a in assets}
    best=None; bestkey=None
    for slots in templates(tuple(bounds),total):
        ids=assign(slots,assets)
        key=(sum(p is not None for p in ids),sum(values[p] for p in ids if p))
        if bestkey is None or key>bestkey:
            best,bestkey=Assignment(ids,slots),key
    return best

def demands(bounds,total):
    """Exact subset demands for singleton position capacities and total N."""
    positions=[p for p,_,hi in bounds if hi]
    result={}
    for size in range(1,len(positions)+1):
        for group in combinations(positions,size):
            wanted=set(group)
            demand=max(sum(lo for p,lo,_ in bounds if p in wanted),
                       total-sum(hi for p,_,hi in bounds if p not in wanted))
            if demand>0:result['+'.join(sorted(group))]=(wanted,demand)
    return result


def max_positions(bounds,total):
    family=templates(tuple(bounds),total)
    return {p:max(row.count(p) for row in family) for p,_,_ in bounds}
