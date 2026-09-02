"""Consensus roster-fit SORT KEY — `consensus_fit_weight`
(docs/plans/consensus-fit-sort-key/scope.md; R7 of
docs/reviews/2026-08-22-trade-model-restrictiveness.html).

`_generate_consensus_for_pair` serves 84.5% of production cards and emits the
first `max_cards` combos that clear its gates IN POOL ORDER — so the pool sort
is the ranking, and until this knob that sort was pure `seed_value`. Both
sides are priced by the same consensus functional, so the partner's gain is
the exact negative of the user's and the only modelled reason a counterparty
would accept is roster fit, which was not in the sort at all. The knob blends
it in: `seed_value * (1 + w * fit_norm)`, fit = marginal-value asymmetry
(worth in the partner's lineup minus worth in ours), normalised to [-1, 1].

Three claims, three proofs:

1. **Knob 0 is byte-identical to origin/main** (`ce3f443c`, the tree this
   branch forked from). `_GOLDEN_MAIN_JSON` is the consensus generator's
   output on the engine-quality deck fixture, captured on that tree — code
   that had never heard of the knob — in EMITTED order, because order is the
   whole point of a sort key.
2. **Knob > 0 reorders toward fit.** A mirror fixture (user 6 WR + 1 RB,
   partner 1 WR + 6 RB, partner has NO board, identical consensus prices
   per rung) whose value-only sort leads with the partner's lone high QB;
   at w = 0.5 the first card is the WR-out / RB-in mirror swap.
3. **It reorders, it does not open the fairness floor.** Every emitted card,
   at every w, still clears `rv - gv >= user_gain_epsilon`.

Capture procedure for the golden (re-run only if the fixture changes)::

    git archive origin/main | tar -x -C <scratch>/main_tree
    cp backend/tests/test_consensus_fit_sort_key.py <scratch>/main_tree/backend/tests/
    (cd <scratch>/main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_consensus_fit_sort_key)

Sabotage recipes (each proven red then green on 2026-09-02; clear
`backend/**/__pycache__` after restoring — G-060):
  * replace the blended lambda in `_fit_sort_key` with `seed_value`
    → test_knob_half_leads_with_the_mirror_swap red;
  * drop the `_pos(p) in shed_positions` primary key from the give sort
    → test_knob0_is_byte_identical_to_origin_main red;
  * stamp `consensus_fit` unconditionally (remove the `if _w_fit > 0`)
    → test_knob0_never_stamps red.
"""

import json

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService

from backend.tests.test_engine_quality_golden import (
    _deck_fixture as _eq_fixture,
)

KNOB = "consensus_fit_weight"


class _Player:
    def __init__(self, pid, position, age=25, team="TST"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = age
        self.ktc_value = None
        self.pick_value = None
        self.years_experience = 3
        self.search_rank = 50


class _Pick(_Player):
    def __init__(self, pid, pick_value=60.0):
        super().__init__(pid, position="PICK", team="PICK", age=0)
        self.pick_value = pick_value


@pytest.fixture(autouse=True)
def _isolate():
    old_flags, old_cfg = ff._flags_cache, dict(ts._cfg)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _setup(w: float | None):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update({"trade_engine.v2": True})
    ff._flags_cache = cache
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    # The knob does not exist on the capture tree; only set it when asked
    # for a non-default value so the same file runs on both trees.
    if w:
        ts._cfg[KNOB] = float(w)


def _consensus(svc, *, user_roster, seed, opp, fairness, w, user_elo=None,
               profiles=True, scoring_format="1qb_ppr"):
    """The consensus generator called directly and uncapped (the deck caps
    would otherwise hide most of this path), rows in EMITTED order."""
    def _sv(pid):
        return ts.elo_to_value(seed.get(pid, 1500.0))

    prof = ts.analyze_roster_strengths
    elos = dict(user_elo or seed)
    return svc._generate_consensus_for_pair(
        user_id="user", opponent=opp, league_id="L1", seed_value=_sv,
        shrunk_user_elo=elos, user_roster=user_roster, max_cards=200,
        fairness_threshold=fairness,
        user_profile=(prof(user_roster, svc._players, scoring_format)
                      if profiles else {}),
        opp_profile=(prof(opp.roster, svc._players, scoring_format)
                     if profiles else {}),
        acquire_positions=[], trade_away_positions=[],
        pinned_give_players=None, raw_user_elo=dict(elos),
        presentment_ok_fn=None, scoring_format=scoring_format)


def _rows(cards):
    return [[list(c.give_player_ids), list(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.give_value, c.receive_value] for c in cards]


# ── 1. golden: engine-quality fixture, knob 0, vs origin/main @ ce3f443c ───

def _eq_consensus(w=None):
    _setup(w)
    svc, user_elo, user_roster, seed = _eq_fixture()
    out = []
    for opp in svc._leagues["L1"].members:
        out.extend(_consensus(svc, user_roster=user_roster, seed=seed,
                              opp=opp, fairness=0.6, w=w, user_elo=user_elo))
    return out


_GOLDEN_MAIN_JSON = """\
[["PKu"],["star1"],"opp1",0.356,0.741,1349.9,1822.1],
[["uq"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["ur1"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["ur2"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["uw1"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["uw2"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["ut"],["PKo1"],"opp1",0.228,0.76,1000.0,1316.5],
[["uq"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1q"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1r1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1r2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1w1"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1w2"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur1"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["ur2"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw1"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["uw2"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["ut"],["o1t"],"opp1",0.3,1.0,1000.0,1000.0],
[["uq","ur1"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uq","ur2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uq","uw1"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uq","uw2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uq","ut"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur1","ur2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur1","uw1"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur1","uw2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur1","ut"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur2","uw1"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur2","uw2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["ur2","ut"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uw1","uw2"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uw1","ut"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["uw2","ut"],["star1"],"opp1",0.445,0.927,1689.0,1822.1],
[["PKu"],["star2"],"opp2",0.356,0.741,1349.9,1822.1],
[["uq"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["ur1"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["ur2"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["uw1"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["uw2"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["ut"],["PKo2"],"opp2",0.228,0.76,1000.0,1316.5],
[["uq"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2q"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2r1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2r2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2w1"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2w2"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur1"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["ur2"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw1"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["uw2"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["ut"],["o2t"],"opp2",0.3,1.0,1000.0,1000.0],
[["uq","ur1"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uq","ur2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uq","uw1"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uq","uw2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uq","ut"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur1","ur2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur1","uw1"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur1","uw2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur1","ut"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur2","uw1"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur2","uw2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["ur2","ut"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uw1","uw2"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uw1","ut"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["uw2","ut"],["star2"],"opp2",0.445,0.927,1689.0,1822.1],
[["PKu"],["star3"],"opp3",0.356,0.741,1349.9,1822.1],
[["uq"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["ur1"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["ur2"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["uw1"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["uw2"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["ut"],["PKo3"],"opp3",0.228,0.76,1000.0,1316.5],
[["uq"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3q"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3r1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3r2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3w1"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3w2"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur1"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["ur2"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw1"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["uw2"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["ut"],["o3t"],"opp3",0.3,1.0,1000.0,1000.0],
[["uq","ur1"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uq","ur2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uq","uw1"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uq","uw2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uq","ut"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur1","ur2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur1","uw1"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur1","uw2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur1","ut"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur2","uw1"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur2","uw2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["ur2","ut"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uw1","uw2"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uw1","ut"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
[["uw2","ut"],["star3"],"opp3",0.445,0.927,1689.0,1822.1],
"""

GOLDEN_MAIN = [json.loads(line) for line in
               _GOLDEN_MAIN_JSON.strip().rstrip(",").split(",\n")]


def test_knob0_is_byte_identical_to_origin_main():
    assert _rows(_eq_consensus()) == GOLDEN_MAIN
    assert _rows(_eq_consensus(w=0.0)) == GOLDEN_MAIN


def test_knob0_never_stamps():
    """The knob-0 card object carries no fit stamp at all — the attribute
    stays at its dataclass default, so nothing downstream can tell the knob
    exists."""
    assert all(c.consensus_fit is None for c in _eq_consensus())
    assert all(c.consensus_fit is not None for c in _eq_consensus(w=0.5))


def test_the_engine_quality_fixture_is_fit_symmetric():
    """Measured, not assumed: every lineup on this fixture is the mirror of
    the other side's (three WR, two RB, one QB/TE each, bodies all 1500), so
    the marginal-value asymmetry is 0 for every asset and w cannot move it.
    The golden above therefore proves identity, not sensitivity — which is
    why the mirror golden below exists."""
    assert _rows(_eq_consensus(w=1.0)) == GOLDEN_MAIN


# ── 2. mirror fixture: the swap value-only sorting cannot lead with ───────

_LADDER = [1650.0, 1620.0, 1590.0, 1560.0, 1530.0, 1500.0]


def _mirror():
    """User 6 WR (ladder) + 1 RB; partner 6 RB (same ladder) + 1 WR; each
    side one QB and one TE. The partner's QB is the single most valuable
    asset on the table and the user already starts a QB, so a value-only
    sort leads the receive pool with it. The partner has NO board."""
    players, seed = {}, {}

    def add(pid, pos, elo):
        players[pid] = _Player(pid, pos)
        seed[pid] = elo

    user_roster, opp_roster = [], []
    for i, e in enumerate(_LADDER, 1):
        add(f"uWR{i}", "WR", e); user_roster.append(f"uWR{i}")
        add(f"oRB{i}", "RB", e); opp_roster.append(f"oRB{i}")
    add("uRB1", "RB", 1600.0); user_roster.append("uRB1")
    add("oWR1", "WR", 1600.0); opp_roster.append("oWR1")
    add("uQB", "QB", 1550.0); user_roster.append("uQB")
    add("uTE", "TE", 1500.0); user_roster.append("uTE")
    add("oQB", "QB", 1700.0); opp_roster.append("oQB")
    add("oTE", "TE", 1500.0); opp_roster.append("oTE")

    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="mirror", platform="demo",
                          members=[opp]))
    return svc, seed, user_roster, opp


def _is_mirror(card) -> bool:
    return (len(card.give_player_ids) == 1
            and len(card.receive_player_ids) == 1
            and card.give_player_ids[0].startswith("uWR")
            and card.receive_player_ids[0].startswith("oRB"))


def _mirror_cards(w, *, profiles):
    _setup(w)
    svc, seed, user_roster, opp = _mirror()
    return _consensus(svc, user_roster=user_roster, seed=seed, opp=opp,
                      fairness=0.75, w=w, profiles=profiles)


def _mirror_rows(w=None):
    """Both profile modes, concatenated — the emitted order is the claim."""
    return (_rows(_mirror_cards(w, profiles=False))
            + _rows(_mirror_cards(w, profiles=True)))


# Captured on origin/main @ ce3f443c with the procedure in the docstring.
_GOLDEN_MIRROR_JSON = """\
[["uWR1"],["oQB"],"opp",0.374,0.779,2117.0,2718.3],
[["uWR1"],["oRB1"],"opp",0.375,1.0,2117.0,2117.0],
[["uWR2"],["oRB1"],"opp",0.323,0.861,1822.1,2117.0],
[["uRB1"],["oRB1"],"opp",0.292,0.779,1648.7,2117.0],
[["uWR2"],["oRB2"],"opp",0.375,1.0,1822.1,1822.1],
[["uRB1"],["oRB2"],"opp",0.339,0.905,1648.7,1822.1],
[["uWR3"],["oRB2"],"opp",0.323,0.861,1568.3,1822.1],
[["uRB1"],["oWR1"],"opp",0.375,1.0,1648.7,1648.7],
[["uWR3"],["oWR1"],"opp",0.357,0.951,1568.3,1648.7],
[["uWR4"],["oWR1"],"opp",0.307,0.819,1349.9,1648.7],
[["uQB"],["oWR1"],"opp",0.292,0.779,1284.0,1648.7],
[["uWR3"],["oRB3"],"opp",0.375,1.0,1568.3,1568.3],
[["uWR4"],["oRB3"],"opp",0.323,0.861,1349.9,1568.3],
[["uQB"],["oRB3"],"opp",0.307,0.819,1284.0,1568.3],
[["uWR4"],["oRB4"],"opp",0.3,1.0,1349.9,1349.9],
[["uQB"],["oRB4"],"opp",0.285,0.951,1284.0,1349.9],
[["uWR5"],["oRB4"],"opp",0.258,0.861,1161.8,1349.9],
[["uWR5"],["oRB5"],"opp",0.3,1.0,1161.8,1161.8],
[["uWR6"],["oRB5"],"opp",0.258,0.861,1000.0,1161.8],
[["uTE"],["oRB5"],"opp",0.258,0.861,1000.0,1161.8],
[["uWR6"],["oRB6"],"opp",0.3,1.0,1000.0,1000.0],
[["uTE"],["oRB6"],"opp",0.3,1.0,1000.0,1000.0],
[["uWR6"],["oTE"],"opp",0.3,1.0,1000.0,1000.0],
[["uTE"],["oTE"],"opp",0.3,1.0,1000.0,1000.0],
[["uWR2","uQB"],["oQB"],"opp",0.471,0.981,2667.1,2718.3],
[["uWR2","uWR5"],["oQB"],"opp",0.449,0.936,2544.4,2718.3],
[["uWR2","uWR6"],["oQB"],"opp",0.422,0.878,2387.9,2718.3],
[["uWR2","uTE"],["oQB"],"opp",0.422,0.878,2387.9,2718.3],
[["uRB1","uWR4"],["oQB"],"opp",0.449,0.935,2540.6,2718.3],
[["uRB1","uQB"],["oQB"],"opp",0.437,0.91,2473.0,2718.3],
[["uRB1","uWR5"],["oQB"],"opp",0.415,0.865,2350.4,2718.3],
[["uRB1","uWR6"],["oQB"],"opp",0.387,0.807,2193.8,2718.3],
[["uRB1","uTE"],["oQB"],"opp",0.387,0.807,2193.8,2718.3],
[["uWR3","uWR4"],["oQB"],"opp",0.433,0.902,2452.8,2718.3],
[["uWR3","uQB"],["oQB"],"opp",0.421,0.877,2385.2,2718.3],
[["uWR3","uWR5"],["oQB"],"opp",0.4,0.832,2262.5,2718.3],
[["uWR3","uWR6"],["oQB"],"opp",0.372,0.775,2106.0,2718.3],
[["uWR3","uTE"],["oQB"],"opp",0.372,0.775,2106.0,2718.3],
[["uWR4","uQB"],["oQB"],"opp",0.38,0.792,2153.8,2718.3],
[["uWR4","uWR6"],["oRB1"],"opp",0.354,0.944,1999.0,2117.0],
[["uWR4","uTE"],["oRB1"],"opp",0.354,0.944,1999.0,2117.0],
[["uQB","uWR5"],["oRB1"],"opp",0.371,0.99,2094.8,2117.0],
[["uQB","uWR6"],["oRB1"],"opp",0.341,0.91,1926.0,2117.0],
[["uQB","uTE"],["oRB1"],"opp",0.341,0.91,1926.0,2117.0],
[["uWR5","uWR6"],["oRB1"],"opp",0.318,0.847,1793.5,2117.0],
[["uWR5","uTE"],["oRB1"],"opp",0.318,0.847,1793.5,2117.0],
[["uWR6","uTE"],["oRB1"],"opp",0.288,0.767,1624.7,2117.0],
[["uWR6","uTE"],["oRB2"],"opp",0.348,0.927,1689.0,1822.1],
[["uWR1"],["oRB1"],"opp",0.375,1.0,2117.0,2117.0],
[["uWR2"],["oRB1"],"opp",0.323,0.861,1822.1,2117.0],
[["uRB1"],["oRB1"],"opp",0.292,0.779,1648.7,2117.0],
[["uWR2"],["oRB2"],"opp",0.375,1.0,1822.1,1822.1],
[["uWR3"],["oRB2"],"opp",0.323,0.861,1568.3,1822.1],
[["uRB1"],["oRB2"],"opp",0.339,0.905,1648.7,1822.1],
[["uWR3"],["oRB3"],"opp",0.375,1.0,1568.3,1568.3],
[["uWR4"],["oRB3"],"opp",0.323,0.861,1349.9,1568.3],
[["uQB"],["oRB3"],"opp",0.307,0.819,1284.0,1568.3],
[["uWR4"],["oRB4"],"opp",0.3,1.0,1349.9,1349.9],
[["uWR5"],["oRB4"],"opp",0.258,0.861,1161.8,1349.9],
[["uQB"],["oRB4"],"opp",0.285,0.951,1284.0,1349.9],
[["uWR5"],["oRB5"],"opp",0.3,1.0,1161.8,1161.8],
[["uWR6"],["oRB5"],"opp",0.258,0.861,1000.0,1161.8],
[["uTE"],["oRB5"],"opp",0.258,0.861,1000.0,1161.8],
[["uWR6"],["oRB6"],"opp",0.3,1.0,1000.0,1000.0],
[["uTE"],["oRB6"],"opp",0.3,1.0,1000.0,1000.0],
[["uWR4","uWR6"],["oRB1"],"opp",0.354,0.944,1999.0,2117.0],
[["uWR4","uTE"],["oRB1"],"opp",0.354,0.944,1999.0,2117.0],
[["uWR5","uWR6"],["oRB1"],"opp",0.318,0.847,1793.5,2117.0],
[["uWR5","uQB"],["oRB1"],"opp",0.371,0.99,2094.8,2117.0],
[["uWR5","uTE"],["oRB1"],"opp",0.318,0.847,1793.5,2117.0],
[["uWR6","uQB"],["oRB1"],"opp",0.341,0.91,1926.0,2117.0],
[["uWR6","uTE"],["oRB1"],"opp",0.288,0.767,1624.7,2117.0],
[["uQB","uTE"],["oRB1"],"opp",0.341,0.91,1926.0,2117.0],
[["uWR6","uTE"],["oRB2"],"opp",0.348,0.927,1689.0,1822.1],
"""

GOLDEN_MIRROR = [json.loads(line) for line in
                 _GOLDEN_MIRROR_JSON.strip().rstrip(",").split(",\n")
                 if line]                       # empty only in capture mode


def test_mirror_knob0_is_byte_identical_to_origin_main():
    assert _mirror_rows() == GOLDEN_MIRROR
    assert _mirror_rows(w=0.0) == GOLDEN_MIRROR


def test_the_mirror_golden_is_not_vacuous():
    """The knob must actually move THIS fixture, or the identity above would
    hold at every w and prove nothing about the default."""
    assert _mirror_rows(w=0.5) != GOLDEN_MIRROR


def test_knob0_leads_with_the_lone_qb_not_the_mirror_swap():
    """Profile-silent (no acquire/shed positions, empty profiles — the
    sort is the ONLY ranking): the value sort leads with uWR1 -> oQB, the
    partner's one QB into a roster that already starts one."""
    cards = _mirror_cards(0.0, profiles=False)
    assert cards, "fixture emits nothing"
    first = cards[0]
    assert (first.give_player_ids, first.receive_player_ids) == \
        (["uWR1"], ["oQB"]), (first.give_player_ids, first.receive_player_ids)
    assert not _is_mirror(first)


def test_knob_half_leads_with_the_mirror_swap():
    cards = _mirror_cards(0.5, profiles=False)
    first = cards[0]
    assert _is_mirror(first), (first.give_player_ids, first.receive_player_ids)
    assert (first.give_player_ids, first.receive_player_ids) == \
        (["uWR1"], ["oRB1"])
    # The stamp says so too: +1.0 = both assets at their pool's max fit.
    assert first.consensus_fit == 1.0


def test_profile_driven_mirror_already_leads_with_the_swap_at_knob0():
    """With the real `analyze_roster_strengths` profiles the need filter
    already restricts the receive pool to RB and the shed key already
    fronts WR, so the value sort leads with the swap at w = 0 too — the
    sort key matters WITHIN a need position, not across the filter. Stated
    rather than hidden: on this fixture the profile does the work."""
    c0 = _mirror_cards(0.0, profiles=True)
    c5 = _mirror_cards(0.5, profiles=True)
    assert _is_mirror(c0[0]), (c0[0].give_player_ids, c0[0].receive_player_ids)
    assert _is_mirror(c5[0])


@pytest.mark.parametrize("w", [0.0, 0.25, 0.5, 1.0])
@pytest.mark.parametrize("profiles", [False, True])
def test_sign_test_still_holds_on_every_card(w, profiles):
    """Reorders only: the user still wins on consensus on every card."""
    cards = _mirror_cards(w, profiles=profiles)
    assert cards
    eps = ts._c("user_gain_epsilon")
    for c in cards:
        assert c.receive_value - c.give_value >= eps - 1e-6, \
            (c.give_player_ids, c.receive_player_ids, c.give_value,
             c.receive_value)


def test_knob_half_set_of_cards_is_the_same_as_knob0_uncapped():
    """Uncapped, the knob cannot add or remove a card — the gate stack is
    untouched — so the two runs emit the same SET in a different ORDER."""
    def key(c):
        return (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
    c0 = _mirror_cards(0.0, profiles=False)
    c5 = _mirror_cards(0.5, profiles=False)
    assert {key(c) for c in c0} == {key(c) for c in c5}
    assert [key(c) for c in c0] != [key(c) for c in c5]


# ── 3. picks are neutral; fit_norm guard; seed parity ─────────────────────

def test_picks_keep_their_relative_order():
    """Picks have no lineup slot and get fit 0, so a pool of picks sorts by
    value alone at every w — their order among themselves never moves."""
    players, seed = {}, {}
    for i, e in enumerate((1600.0, 1560.0, 1520.0, 1480.0), 1):
        players[f"PK{i}"] = _Pick(f"PK{i}")
        seed[f"PK{i}"] = e
    for pid, e in (("uw", 1500.0), ("ow", 1500.0)):
        players[pid] = _Player(pid, "WR")
        seed[pid] = e
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=["PK1", "PK3", "ow"], elo_ratings={},
                       has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    seen = []
    for w in (0.0, 1.0):
        _setup(w)
        cards = _consensus(svc, user_roster=["PK2", "PK4", "uw"], seed=seed,
                           opp=opp, fairness=0.5, w=w, profiles=False)
        recv_order = []
        for c in cards:
            for p in c.receive_player_ids:
                if p not in recv_order:
                    recv_order.append(p)
        seen.append(recv_order)
        if w > 0:
            for c in cards:
                if all(p.startswith("PK") for p in
                       c.give_player_ids + c.receive_player_ids):
                    assert c.consensus_fit == 0.0
    assert seen[0] == seen[1]


def test_all_zero_fit_pool_is_guarded():
    """A pool whose every asset has fit 0 (all picks) must not divide by
    zero and must sort exactly as at w = 0."""
    players, seed = {}, {}
    for i, e in enumerate((1600.0, 1550.0, 1500.0), 1):
        players[f"PK{i}"] = _Pick(f"PK{i}")
        seed[f"PK{i}"] = e
    opp = LeagueMember(user_id="opp", username="opp", roster=["PK1", "PK2"],
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    out = []
    for w in (0.0, 1.0):
        _setup(w)
        out.append(_rows(_consensus(svc, user_roster=["PK3"], seed=seed,
                                    opp=opp, fairness=0.5, w=w,
                                    profiles=False)))
    assert out[0] == out[1]


def test_knob_is_read_at_call_time_through_the_overlay():
    """`_cfg_override` (arm A's pin, the #189 relaxed pass) must reach the
    read: a process-global 0.5 overlaid with 0.0 is the knob-0 deck."""
    _setup(0.5)
    svc, seed, user_roster, opp = _mirror()
    with ts._cfg_override({KNOB: 0.0}):
        cards = _consensus(svc, user_roster=user_roster, seed=seed, opp=opp,
                           fairness=0.75, w=0.5, profiles=False)
    assert not _is_mirror(cards[0])
    assert all(c.consensus_fit is None for c in cards)


def test_arm_a_pins_the_identity_and_the_challenger_inherits():
    from backend.bakeoff_profiles import (MODEL_A_PROFILE,
                                          MODEL_CHALLENGER_PROFILE)
    assert MODEL_A_PROFILE[KNOB] == 0.0
    assert KNOB not in MODEL_CHALLENGER_PROFILE


def test_default_registered_in_both_stores():
    """`PUT /api/admin/config/<key>` refuses keys without a seeded row, so
    the DB seed list must carry the knob at the same default."""
    from backend.database import _MODEL_CONFIG_DEFAULTS
    seeded = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    assert KNOB in ts._DEFAULT_CFG
    assert KNOB in seeded
    assert ts._DEFAULT_CFG[KNOB] == seeded[KNOB] == 0.0


# ── 4. D-159 junk guard on the harness fixtures ───────────────────────────

def _harness():
    """The measurement harness (docs/plans/consensus-fit-sort-key/) is a
    plain script, not a package; import it by path."""
    import importlib.util
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", "docs", "plans",
                        "consensus-fit-sort-key", "measure_consensus_fit.py")
    spec = importlib.util.spec_from_file_location("measure_consensus_fit",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("league", ["12t_1qb@u0", "12t_1qb@u8", "mirror@b"])
def test_junk_guard_on_harness_fixtures(league, monkeypatch):
    """D-159 guardrail: the sub-450 body share of emitted consensus cards at
    w = 0.5 may not exceed the w = 0 share by more than 2pp, and the deck
    must not shrink. Clock frozen for the test only (G-065) — the v2 pair
    generator's 1 s deadline is otherwise a hidden input."""
    h = _harness()
    monkeypatch.setattr(ts.time, "monotonic", lambda: h.FROZEN_CLOCK)
    h.live_flags(**{"trade_engine.v2": True, "trade_engine.v3": True,
                    "trade.bakeoff": False})
    L = dict(h.LEAGUES)[league]()
    h.reset_cfg(**{KNOB: 0.0})
    base = h.gen(L)
    h.reset_cfg(**{KNOB: 0.5})
    half = h.gen(L)
    s0, s5 = h.stats(base, L), h.stats(half, L, baseline=base)
    assert s0["consensus_cards"] > 0
    assert s5["consensus_cards"] >= s0["consensus_cards"], (s0, s5)
    assert s5["sub450_share"] <= s0["sub450_share"] + 0.02, (s0, s5)


if __name__ == "__main__":       # capture mode — see the module docstring
    print("_GOLDEN_MAIN_JSON = \"\"\"\\")
    for row in _rows(_eq_consensus()):
        print(json.dumps(row, separators=(",", ":")) + ",")
    print("\"\"\"")
    print()
    print("_GOLDEN_MIRROR_JSON = \"\"\"\\")
    for row in _mirror_rows():
        print(json.dumps(row, separators=(",", ":")) + ",")
    print("\"\"\"")
