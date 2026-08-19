"""Kill-value byte-identity proof for the 2026-08-18 engine-quality wave.

Each of the five knobs (C1 `rank_div_min_frac`, C2 `min_package_band`,
C3 `pick_pair_strip_frac`, C4 `deck_headliner_cap`, C5
`mismatch_confidence_damp`) claims that its disable value restores the prior
behaviour exactly. The per-knob no-op tests in test_engine_quality.py prove
each new branch is inert at its kill value; this file proves the CLAIM, by
comparing real generator output with all five knobs killed against goldens
captured by running these same fixtures on the pre-wave code
(origin/main @ 90fb19a).

Capture procedure (re-run if the fixtures ever change):

    git worktree add /tmp/ftf-main origin/main
    cp backend/tests/test_engine_quality_golden.py /tmp/ftf-main/backend/tests/
    (cd /tmp/ftf-main && python3 -m backend.tests.test_engine_quality_golden)

The `__main__` block below prints the two goldens as literals. On pre-wave
code the five knobs simply do not exist, so the run needs no configuration —
what it prints IS the prior behaviour.

The fixtures deliberately exercise every path the wave touches: draft picks
on both sides (C1/C3), multi-asset packages (C1/C2), one asset headlining
cards against several counterparties (C4), comparison counts (C5), and the
pinned asset-ideas ranker (C2).
"""

import json

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService

_KILL_ALL = {
    "rank_div_min_frac": 0.0,
    "min_package_band": 0.0,
    "pick_pair_strip_frac": 0.0,
    "deck_headliner_cap": 0.0,
    "mismatch_confidence_damp": 0.0,
}

_FILL = {"q": "QB", "r1": "RB", "r2": "RB", "w1": "WR", "w2": "WR", "t": "TE"}


class _Player:
    def __init__(self, pid, position="WR", team="TST", age=24):
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


def _bodies(prefix):
    return {f"{prefix}{k}": pos for k, pos in _FILL.items()}


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _reset_cfg(**cfg):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)


# ── deck fixture ───────────────────────────────────────────────────────────

def _deck_fixture():
    """A `hub` the whole league wants (headlines cards against all three
    counterparties), a divergent star per opponent, a pick on each side, and
    a full legal lineup everywhere."""
    pos = dict(_bodies("u"))
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    seed = {pid: 1500.0 for pid in pos}
    user_elo = {pid: 1500.0 for pid in pos}
    players["hub"] = _Player("hub", "WR")
    seed["hub"], user_elo["hub"] = 1700.0, 1600.0
    players["PKu"] = _Pick("PKu")
    seed["PKu"], user_elo["PKu"] = 1560.0, 1560.0
    members = []
    for n in (1, 2, 3):
        star, opp_bodies, pk = f"star{n}", _bodies(f"o{n}"), f"PKo{n}"
        for pid, p in opp_bodies.items():
            players[pid] = _Player(pid, p)
            seed[pid] = user_elo[pid] = 1500.0
        players[star] = _Player(star, "WR")
        seed[star], user_elo[star] = 1620.0, 1750.0
        players[pk] = _Pick(pk)
        seed[pk] = user_elo[pk] = 1555.0
        opp_elo = {pid: 1500.0 for pid in list(opp_bodies) + list(pos)}
        opp_elo.update({"hub": 1800.0, star: 1560.0, "PKu": 1560.0,
                        pk: 1555.0})
        members.append(LeagueMember(
            user_id=f"opp{n}", username=f"opp{n}",
            roster=[star, pk] + list(opp_bodies), elo_ratings=opp_elo,
            has_rankings=True))
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=members))
    return svc, user_elo, ["hub", "PKu"] + list(pos), seed


_CONFIDENCE = {"hub": 2, "star1": 1, "star2": 30, "star3": 300}


def _deck(**cfg):
    _set_flags(**{"trade_engine.v2": True})
    _reset_cfg(**cfg)
    svc, ue, ur, seed = _deck_fixture()
    cards = svc.generate_trades(
        user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
        seed_elo=seed, fairness_threshold=0.6, max_per_opponent=10,
        confidence=dict(_CONFIDENCE))
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.mismatch_score] for c in cards]


# ── asset-ideas fixture (the _emit_best ranker C2 touches) ─────────────────

_IDEA_ELOS = {"P": 1700.0, "S": 1440.0, "S2": 1400.0, "U": 1721.0,
              "U2": 1730.0}


def _ideas(**cfg):
    players = {pid: _Player(pid, "RB") for pid in _IDEA_ELOS}
    opp = LeagueMember(user_id="opp", username="Opp", roster=["U", "U2"],
                       elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    _set_flags(**{"trade.asset_ideas": True})
    _reset_cfg(**cfg)
    with ts.stud_tax_override("heavy"):
        groups = svc.generate_asset_ideas(
            league_id="L1", user_id="user", asset_id="P", direction="give",
            user_roster=["P", "S", "S2"], seed_elo=dict(_IDEA_ELOS),
            raw_user_elo={}, fairness_threshold=0.75)
    return {g: [[i["give_player_ids"], i["receive_player_ids"],
                 i["difference"], i["fairness"]] for i in ideas]
            for g, ideas in groups.items()}


# ── goldens, captured on origin/main @ 90fb19a ─────────────────────────────

_GOLDEN_DECK_JSON = """\
[["hub"],["o2t","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o2w2","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o2w1","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o2r2","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o2r1","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o2q","star2"],"opp2",1.595,0.99,1683.8],
[["hub"],["o3t","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["o3w2","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["o3w1","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["o3r2","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["o3r1","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["o3q","star3"],"opp3",1.595,0.99,1840.5],
[["hub"],["PKo2","star2"],"opp2",1.544,0.883,1747.8],
[["hub"],["PKo3","star3"],"opp3",1.544,0.883,1859.1],
[["hub"],["star3"],"opp3",1.442,0.67,1692.5],
[["hub"],["star2"],"opp2",1.395,0.67,1437.0],
[["PKu","uq","ur2"],["o3r2","star3"],"opp3",0.932,0.84,708.5],
[["PKu","uq","ur1"],["o3r2","star3"],"opp3",0.932,0.84,708.5],
[["PKu","uq","ur2"],["o2r2","star2"],"opp2",0.889,0.84,650.5],
[["PKu","uq","ur1"],["o2r2","star2"],"opp2",0.889,0.84,650.5],
[["hub"],["PKo1","star1"],"opp1",0.848,0.883,885.7],
[["hub"],["o1t","star1"],"opp1",0.64,0.99,460.1],
[["hub"],["o1w2","star1"],"opp1",0.64,0.99,460.1],
[["hub"],["o1w1","star1"],"opp1",0.64,0.99,460.1],
[["hub"],["o1r2","star1"],"opp1",0.64,0.99,460.1],
[["hub"],["o1r1","star1"],"opp1",0.64,0.99,460.1],
[["hub"],["o1q","star1"],"opp1",0.64,0.99,460.1],
"""

_GOLDEN_IDEAS_JSON = """{"upgrade":[[["P","S"],["U"],450.0,0.851],[["P","S"],["U2"],722.8,0.771]],"lateral":[],"downgrade":[]}"""

GOLDEN_DECK = [json.loads(line) for line in
               _GOLDEN_DECK_JSON.strip().rstrip(",").split(",\n")]
GOLDEN_IDEAS = json.loads(_GOLDEN_IDEAS_JSON)


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def test_all_knobs_killed_reproduces_pre_wave_deck():
    """Every knob at its kill value ⇒ the generated deck is byte-identical to
    the same fixture on origin/main."""
    assert _deck(**_KILL_ALL) == GOLDEN_DECK


def test_all_knobs_killed_reproduces_pre_wave_asset_ideas():
    assert _ideas(**_KILL_ALL) == GOLDEN_IDEAS


def test_the_goldens_are_not_vacuous():
    """A golden that matches the LIVE defaults too would prove nothing — the
    wave has to actually change something on these fixtures."""
    assert _deck() != GOLDEN_DECK
    assert _ideas() != GOLDEN_IDEAS


if __name__ == "__main__":       # capture mode — see the module docstring
    print("_GOLDEN_DECK_JSON = \"\"\"\\")
    for row in _deck():
        print(json.dumps(row, separators=(",", ":")) + ",")
    print("\"\"\"")
    print()
    print("_GOLDEN_IDEAS_JSON = \"\"\"" +
          json.dumps(_ideas(), separators=(",", ":")) + "\"\"\"")
