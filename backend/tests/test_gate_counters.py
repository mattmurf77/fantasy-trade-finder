"""P0-6 gate counters — T-29 (LLD §4.2, PRD R5).

`trade_service._consider` is the v2 deck engine's gate cascade: nine early
returns between "this pair of packages exists" and "this card is offered".
Nobody could previously say WHERE candidates died, so "the engine found you
nothing" was unanalyzable. B4 bumps a counter at each early return and folds
the result into `deck_job_stats.decided_by`.

**Two engines, one vocabulary.** The LLD anchors B4 on `_consider`, but
`config/features.json` ships `trade_engine.v3: true`, so the deck production
actually serves comes from `trade_optimizer.generate_pair_trades_v3` — the same
cascade, exactly enumerated, plus a `shape` filter and the 3.2
lineup-feasibility hard gate. Both are instrumented with the same counter
names (a funnel that only populates on the dark engine is a wall of zeros), and
the v3 section at the bottom pins that.

The whole feature is one sentence of risk: **counting must not become
deciding.** So this file proves two different things, and both matter:

  1. The counters ride the REAL gate booleans. Every per-gate test here
     neutralizes the actual production gate (patching the real helper, or
     moving the real config knob) and asserts the counter follows AND the
     verdict follows. A counter computed from a re-derived condition — the
     obvious way this drifts over time — passes nothing here.
  2. A counters-only diff changes no verdict. Same fixtures, run with and
     without a counters dict, must produce identical cards.

Plus the conservation identity, which is the structural half of (1):

     gate_considered == gate_passed + Σ gate_<name>

Every path out of `_consider` is either an offer or exactly one counted kill,
so a future early return added WITHOUT a counter breaks this arithmetic even
if nobody remembers to add a test for it.

Fixture style mirrors test_engine_gates_config.py: tiny deterministic
leagues, flags and `_cfg` snapshot-restored per test.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.database import deck_job_stats_table, metadata
from backend.trade_service import League, LeagueMember, TradeService


# The kill counters `_consider` can emit, in cascade order. Named here rather
# than derived so that renaming one in production without updating the admin
# report is caught by a test instead of by an empty dashboard panel.
GATES = (
    "gate_pinned_give",
    "gate_pinned_receive",
    "gate_positional",
    "gate_elo_gap",
    "gate_user_gain",
    "gate_pick_swap",
    "gate_junk_filler",
    "gate_mutual_gain",
    "gate_fairness",
    # v3-only (trade_optimizer). The optimizer enumerates exactly instead of
    # heuristically and adds two gates the v2 cascade has no equivalent of.
    "gate_shape",
    "gate_lineup_feasibility",
)


@pytest.fixture(autouse=True)
def _isolate():
    of, oc = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear(); ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = of
        ts._cfg.clear(); ts._cfg.update(oc)


class _P:
    def __init__(s, i, pos="RB", team="T"):
        s.id, s.name, s.position, s.team = i, i, pos, team
        s.age, s.ktc_value = 24, None


def _flags(**kw):
    c = dict(ff.DEFAULT_FLAGS); c.update(kw); ff._flags_cache = c


def _m(uid, roster, elo):
    return LeagueMember(user_id=uid, username=uid, roster=roster,
                        elo_ratings=elo, has_rankings=True)


def _svc(ids, opps, positions=None):
    positions = positions or {}
    players = {i: _P(i, positions.get(i, "RB")) for i in ids}
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo",
                        members=opps))
    return s


def _gen(svc, ue, ur, seed, counters=None, **kw):
    return svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                               league_id="L1", seed_elo=seed,
                               gate_counters=counters, **kw)


def _kills(counters):
    return {k: v for k, v in counters.items() if k in GATES}


def _conserves(counters):
    """considered == passed + every counted kill."""
    return (counters.get("gate_considered", 0)
            == counters.get("gate_passed", 0) + sum(_kills(counters).values()))


# ── fixtures ────────────────────────────────────────────────────────────────

# The proven divergence league from test_engine_gates_config: every Gi<->Rj is
# a two-sided win, so with default config a healthy number of cards clear all
# nine gates and the counters have something to be right about.
_USER_ELO = {"g1": 1500, "g2": 1500, "g3": 1500,
             "r1": 1720, "r2": 1640, "r3": 1580}
_OPP_ELO  = {"g1": 1720, "g2": 1640, "g3": 1580,
             "r1": 1500, "r2": 1500, "r3": 1500}
_IDS = list(_USER_ELO)


def _divergence_league(positions=None):
    seed = {pid: 1500.0 for pid in _IDS}
    opp = _m("opp", ["r1", "r2", "r3"], dict(_OPP_ELO))
    return (_svc(_IDS, [opp], positions), dict(_USER_ELO),
            ["g1", "g2", "g3"], seed)


# v3 enforces post-trade lineup legality, so its fixture needs REAL rosters:
# a legal starting lineup on both sides plus the tradeable extras that carry
# the divergence. (The v2 fixture above is all-RB and would be killed 100% by
# v3's 3.2 gate — which is itself worth knowing about the two engines.)
_V3_POS = {"QB1": "QB", "RB1": "RB", "RB2": "RB", "WR1": "WR", "WR2": "WR",
           "TE1": "TE", "g1": "RB", "g2": "RB",
           "oQB": "QB", "oRB1": "RB", "oRB2": "RB", "oWR1": "WR",
           "oWR2": "WR", "oTE": "TE", "r1": "WR", "r2": "WR"}
_V3_MINE   = ["QB1", "RB1", "RB2", "WR1", "WR2", "TE1", "g1", "g2"]
_V3_THEIRS = ["oQB", "oRB1", "oRB2", "oWR1", "oWR2", "oTE", "r1", "r2"]


def _v3_league():
    ue = {k: 1500 for k in _V3_POS}; ue["r1"], ue["r2"] = 1720, 1640
    oe = {k: 1500 for k in _V3_POS}; oe["g1"], oe["g2"] = 1720, 1640
    seed = {k: 1500.0 for k in _V3_POS}
    svc = _svc(list(_V3_POS), [_m("opp", _V3_THEIRS, oe)], _V3_POS)
    return svc, ue, list(_V3_MINE), seed


def _one_for_one_league(gap=200, positions=None):
    """User gives G, wants R; user Elo gap = `gap`. Exactly one combo, so a
    per-gate counter is an exact integer, not a range."""
    ue = {"G": 1500, "R": 1500 + gap}
    oe = {"G": 1500 + gap, "R": 1500}
    seed = {"G": 1500.0, "R": 1500.0}
    svc = _svc(["G", "R"], [_m("opp", ["R"], dict(oe))], positions)
    return svc, ue, ["G"], seed


# ---------------------------------------------------------------------------
# The invariant that makes the rest trustworthy
# ---------------------------------------------------------------------------

def test_counters_conserve_every_candidate():
    """Every `_consider` call leaves through exactly one exit, and every exit
    is counted.

    SABOTAGE: add an early return to `_consider` without a `_kill()` — e.g.
    a new roster-legality gate — and `considered` exceeds passed + kills, so
    the gate-kill funnel silently under-reports the new gate forever.
    """
    _flags(**{"trade_engine.v2": True})
    svc, ue, ur, seed = _divergence_league()
    ctr: dict = {}
    cards = _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10)

    assert ctr["gate_considered"] == 30      # 9 1x1 + 9 2x1 + 9 1x2 + 3 3x2
    assert ctr["gate_passed"] > 0            # the fixture must exercise both
    assert sum(_kills(ctr).values()) > 0     # halves of the identity
    assert _conserves(ctr), ctr
    assert cards, "fixture regression: the divergence league must yield cards"


def test_counters_are_a_pure_out_param():
    """The headline P0-6 risk: counting that changes deciding.

    SABOTAGE: move any `_kill()` call ACROSS its `return` (so it short-
    circuits), or make `_kill` mutate anything the cascade reads ⇒ the two
    runs diverge in cards, order, or composite.
    """
    _flags(**{"trade_engine.v2": True})

    def run(counters):
        svc, ue, ur, seed = _v3_league()
        cards = _gen(svc, ue, ur, seed, counters=counters, max_per_opponent=10)
        return [(tuple(c.give_player_ids), tuple(c.receive_player_ids),
                 round(c.composite_score, 9)) for c in cards]

    assert run(None) == run({}), "counters changed the served deck"


def test_counters_default_to_none_without_a_dict():
    """A caller that passes nothing still generates — the private dict path.

    SABOTAGE: drop the `gate_counters or {}` fallback in
    `_generate_for_pair_v2` ⇒ every non-instrumented caller (the demo league,
    asset ideas, every existing test) raises TypeError on the first gate.
    """
    _flags(**{"trade_engine.v2": True})
    svc, ue, ur, seed = _divergence_league()
    assert _gen(svc, ue, ur, seed, max_per_opponent=10)


# ---------------------------------------------------------------------------
# Per-gate attribution — each one neutralizes the REAL gate
# ---------------------------------------------------------------------------

def test_positional_filter_counter():
    """acquire_positions the opponent cannot satisfy kills everything at the
    positional gate, and nothing downstream ever runs.

    SABOTAGE: attribute this to `elo_gap` (an off-by-one in the cascade) ⇒
    the funnel blames the wrong gate and an operator tunes the wrong knob.

    Note the count is 90, not 30: expressing a position preference makes this
    a TARGETED job, so #189's relaxed pass re-runs generation twice more when
    the normal pass comes up empty. Counters accumulate across the retries —
    that is the honest number (the engine really did consider 90 candidates
    for this job), and it is why the funnel is read as a ratio, not a raw
    per-job count.
    """
    _flags(**{"trade_engine.v2": True})
    svc, ue, ur, seed = _divergence_league()
    ctr: dict = {}
    cards = _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10,
                 acquire_positions=["QB"])          # every player is an RB
    assert cards == []
    assert ctr["gate_positional"] == ctr["gate_considered"] == 90
    assert ctr.get("gate_passed", 0) == 0
    assert _conserves(ctr)


def test_elo_gap_counter_follows_the_real_cap():
    """The one knife-edge fixture from TC-ENG-003, now counted: gap 200
    passes under cap 250 and dies under cap 150.

    SABOTAGE: compute the counter from a hardcoded gap instead of calling
    `_gap_ok` ⇒ the two runs report the same number even though the verdicts
    differ.
    """
    _flags(**{"trade_engine.v2": True})

    def run(cap):
        ts._cfg["trade_elo_gap_max"] = cap
        svc, ue, ur, seed = _one_for_one_league(gap=200)
        ctr: dict = {}
        cards = _gen(svc, ue, ur, seed, counters=ctr,
                     fairness_threshold=0.5, max_per_opponent=5)
        return cards, ctr

    passed_cards, passed_ctr = run(250.0)
    killed_cards, killed_ctr = run(150.0)

    assert passed_cards and passed_ctr.get("gate_elo_gap", 0) == 0
    assert killed_cards == [] and killed_ctr["gate_elo_gap"] == 1
    assert _conserves(passed_ctr) and _conserves(killed_ctr)


def test_user_gain_counter_follows_the_real_108_gate():
    """#108: a 1-for-1 that sends a player the user ranks ABOVE what they get
    back. Neutralizing the real gate must zero the counter AND admit the card.

    SABOTAGE: count `user_gain` from a locally recomputed Elo comparison ⇒
    patching `fit_premium_1for1` leaves the counter at 1 even though the
    candidate now flows past it, i.e. the funnel reports a kill that the
    engine did not make.
    """
    _flags(**{"trade_engine.v2": True})
    # User's raw board ranks G (1700) above R (1550) — squarely #108 — and
    # the swap is inside the Elo-gap cap, so #108 is the FIRST thing it hits.
    ue = {"G": 1700, "R": 1550}
    oe = {"G": 1900, "R": 1500}
    seed = {"G": 1500.0, "R": 1500.0}

    def run(patched):
        svc = _svc(["G", "R"], [_m("opp", ["R"], dict(oe))])
        ctr: dict = {}
        if patched:
            with patch.object(ts, "fit_premium_1for1",
                              lambda *a, **k: (True, None)):
                cards = _gen(svc, dict(ue), ["G"], dict(seed), counters=ctr,
                             fairness_threshold=0.5, max_per_opponent=5)
        else:
            cards = _gen(svc, dict(ue), ["G"], dict(seed), counters=ctr,
                         fairness_threshold=0.5, max_per_opponent=5)
        return cards, ctr

    real_cards, real_ctr = run(False)
    open_cards, open_ctr = run(True)

    # Real gate: the single candidate dies AT #108 and never reaches a gate
    # behind it.
    assert real_cards == [] and real_ctr["gate_user_gain"] == 1
    assert real_ctr.get("gate_mutual_gain", 0) == 0
    # Gate neutralized: the counter follows the gate, and the candidate is
    # now killed by the next gate down the cascade instead. (It still isn't
    # a servable trade — the user is giving up value — which is exactly why
    # #108 sits in front of the surplus math.)
    assert open_cards == []
    assert open_ctr.get("gate_user_gain", 0) == 0
    assert open_ctr["gate_mutual_gain"] == 1
    assert _conserves(real_ctr) and _conserves(open_ctr)


def test_pick_swap_counter_follows_the_real_227_gate():
    """#227: a 1-for-1 pick-for-pick swap is churn. Same neutralization proof.

    SABOTAGE: count by re-testing `is_pick_asset` locally instead of by
    `pick_swap_ok`'s verdict ⇒ patching the gate open leaves the counter at 1.
    """
    _flags(**{"trade_engine.v2": True})
    positions = {"G": "PICK", "R": "PICK"}

    def run(patched):
        svc, ue, ur, seed = _one_for_one_league(gap=120, positions=positions)
        ctr: dict = {}
        if patched:
            with patch.object(ts, "pick_swap_ok", lambda *a, **k: True):
                cards = _gen(svc, ue, ur, seed, counters=ctr,
                             fairness_threshold=0.5, max_per_opponent=5)
        else:
            cards = _gen(svc, ue, ur, seed, counters=ctr,
                         fairness_threshold=0.5, max_per_opponent=5)
        return cards, ctr

    real_cards, real_ctr = run(False)
    open_cards, open_ctr = run(True)

    assert real_cards == [] and real_ctr["gate_pick_swap"] == 1
    assert open_ctr.get("gate_pick_swap", 0) == 0
    assert open_cards, "neutralizing #227 must actually admit the pick swap"
    assert _conserves(real_ctr) and _conserves(open_ctr)


def test_junk_filler_counter_follows_the_real_141_gate():
    """#141: a package whose non-headliner pieces are junk on both boards.

    SABOTAGE: patch `filler_ok` open and the counter must go to zero — a
    locally recomputed filler test would keep reporting kills.
    """
    _flags(**{"trade_engine.v2": True})

    def run(patched):
        # Opponent holds one asset; the user's give side pairs a real player
        # with a body both boards agree is worthless. The 1-for-1 g1↔R is
        # clean (single-asset sides skip #141); the 2-for-1 is the padded one.
        ue = {"g1": 1500, "junk": 400, "R": 1700}
        oe = {"g1": 1700, "junk": 400, "R": 1500}
        seed = {"g1": 1500.0, "junk": 400.0, "R": 1500.0}
        svc = _svc(["g1", "junk", "R"], [_m("opp", ["R"], dict(oe))])
        ctr: dict = {}
        if patched:
            with patch.object(ts, "filler_ok", lambda *a, **k: True):
                cards = _gen(svc, ue, ["g1", "junk"], seed, counters=ctr,
                             fairness_threshold=0.3, max_per_opponent=8)
        else:
            cards = _gen(svc, ue, ["g1", "junk"], seed, counters=ctr,
                         fairness_threshold=0.3, max_per_opponent=8)
        shapes = {(tuple(c.give_player_ids), tuple(c.receive_player_ids))
                  for c in cards}
        return ctr, shapes

    padded = (("g1", "junk"), ("R",))
    real_ctr, real_shapes = run(False)
    open_ctr, open_shapes = run(True)

    assert real_ctr["gate_junk_filler"] == 1 and padded not in real_shapes
    assert open_ctr.get("gate_junk_filler", 0) == 0 and padded in open_shapes
    assert _conserves(real_ctr) and _conserves(open_ctr)


def test_mutual_gain_counter_follows_the_real_surplus_floor():
    """Both sides must clear min_side_surplus. Raise it out of reach and the
    entire candidate set must die THERE, not at fairness behind it.

    SABOTAGE: put the `_kill("mutual_gain")` on the fairness branch (or vice
    versa) ⇒ this test and the fairness one below swap counters.
    """
    _flags(**{"trade_engine.v2": True})
    ts._cfg["min_side_surplus"] = 1e9
    svc, ue, ur, seed = _divergence_league()
    ctr: dict = {}
    cards = _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10)

    assert cards == []
    assert ctr["gate_mutual_gain"] == 30
    assert ctr.get("gate_fairness", 0) == 0   # nothing reached fairness
    assert _conserves(ctr)


def test_fairness_counter_follows_the_real_fairness_gate():
    """A lopsided 1-for-1 that clears mutual gain but not the fairness band.

    SABOTAGE: count fairness kills where `_fairness` returns a SCORE rather
    than where it returns None ⇒ every surviving card is also counted as a
    fairness kill and conservation breaks.
    """
    _flags(**{"trade_engine.v2": True})
    # Consensus says R is worth far more than G, so the point ratio is deep
    # under any sane threshold and the uncertainty ranges cannot overlap.
    ue = {"G": 1500, "R": 2400}
    oe = {"G": 2400, "R": 1500}
    seed = {"G": 1200.0, "R": 2600.0}
    svc = _svc(["G", "R"], [_m("opp", ["R"], dict(oe))])
    ts._cfg["trade_elo_gap_max"] = 5000.0     # keep the gap gate out of it
    ctr: dict = {}
    cards = _gen(svc, ue, ["G"], seed, counters=ctr,
                 fairness_threshold=0.99, max_per_opponent=5)

    assert cards == []
    assert ctr["gate_fairness"] == 1
    assert _conserves(ctr)


def test_pinned_counters_split_give_from_receive():
    """The two pinned filters are the first two exits and must not be merged.

    SABOTAGE: reuse one counter name for both ⇒ "we found nothing" for a
    pinned-give job is indistinguishable from a pinned-acquire job.
    """
    _flags(**{"trade_engine.v2": True})

    svc, ue, ur, seed = _divergence_league()
    give_ctr: dict = {}
    _gen(svc, ue, ur, seed, counters=give_ctr, max_per_opponent=10,
         pinned_give_players=["g1"])
    assert give_ctr["gate_pinned_give"] > 0
    assert give_ctr.get("gate_pinned_receive", 0) == 0
    assert _conserves(give_ctr)

    svc, ue, ur, seed = _divergence_league()
    recv_ctr: dict = {}
    _gen(svc, ue, ur, seed, counters=recv_ctr, max_per_opponent=10,
         pinned_receive_players=["r1"])
    assert recv_ctr["gate_pinned_receive"] > 0
    assert recv_ctr.get("gate_pinned_give", 0) == 0
    assert _conserves(recv_ctr)


# ---------------------------------------------------------------------------
# The v3 optimizer — the engine PRODUCTION actually runs
# ---------------------------------------------------------------------------
# config/features.json ships `trade_engine.v3: true`, so the live deck path is
# trade_optimizer.generate_pair_trades_v3, not the `_consider` cascade the LLD
# anchors B4 on. Both are instrumented with the same counter names; these tests
# pin that, because a funnel that only populates on the dark engine is a
# dashboard of zeros.

def test_v3_counters_conserve_and_use_the_same_names():
    """SABOTAGE: rename a gate in one engine and not the other ⇒ the funnel
    reports two different vocabularies depending on which flag is live, and
    the series breaks silently at the flag flip.
    """
    _flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    svc, ue, ur, seed = _v3_league()
    ctr: dict = {}
    cards = _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10)

    assert cards, "fixture regression: v3 must also yield cards here"
    assert ctr["gate_passed"] > 0
    assert _conserves(ctr), ctr
    # v3 enumerates the full give×receive grid, so its own shape gate fires.
    assert ctr["gate_shape"] > 0
    assert set(_kills(ctr)) <= set(GATES)


def test_v3_pinned_give_counts_candidates_not_skips():
    """The pinned-give filter sits on v3's OUTER loop, killing a whole row of
    the (give × receive) grid at a time.

    SABOTAGE: count one kill per skipped give-subset ⇒ conservation breaks and
    the funnel understates the most common targeted-job kill by ~|recv| ×.
    """
    _flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    svc, ue, ur, seed = _v3_league()
    ctr: dict = {}
    _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10,
         pinned_give_players=["g1"])
    assert ctr["gate_pinned_give"] > 0
    assert _conserves(ctr), ctr


def test_v3_lineup_feasibility_has_its_own_counter():
    """v3's 3.2 hard constraint (post-trade lineups must stay legal) is a gate
    v2 does not have, and it must not be folded into a neighbour.

    SABOTAGE: attribute infeasible-lineup kills to `junk_filler` ⇒ an operator
    loosens filler_min_frac trying to fix a roster-legality problem.
    """
    _flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    svc, ue, ur, seed = _v3_league()
    ctr: dict = {}
    with patch("backend.trade_optimizer._feasible_after",
               lambda *a, **k: False):
        cards = _gen(svc, ue, ur, seed, counters=ctr, max_per_opponent=10)
    assert cards == []
    assert ctr["gate_lineup_feasibility"] > 0
    assert ctr.get("gate_passed", 0) == 0
    assert _conserves(ctr)


def test_v3_counters_are_a_pure_out_param():
    """SABOTAGE: same as the v2 case — any `_kill` that short-circuits a
    `continue` changes the deck.
    """
    _flags(**{"trade_engine.v2": True, "trade_engine.v3": True})

    def run(counters):
        svc, ue, ur, seed = _divergence_league()
        cards = _gen(svc, ue, ur, seed, counters=counters, max_per_opponent=10)
        return [(tuple(c.give_player_ids), tuple(c.receive_player_ids),
                 round(c.composite_score, 9)) for c in cards]

    assert run(None) == run({})


# ---------------------------------------------------------------------------
# The out-param → deck_job_stats hop
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _decided_by(eng, job_id):
    with eng.connect() as conn:
        row = conn.execute(
            select(deck_job_stats_table.c.decided_by)
            .where(deck_job_stats_table.c.deck_job_id == job_id)).first()
    return json.loads(row[0]) if row else None


def test_gate_counters_merge_beside_the_dedup_counters(mem_engine):
    """Both P0-5 and P0-6 write `decided_by` for the same job, each knowing
    only its own keys.

    SABOTAGE: make `_record_deck_gate_counters` insert-or-replace instead of
    calling `merge_deck_job_counters` ⇒ the dedup layer's numbers vanish, and
    because dedup drops are pre-capture there is nothing to rebuild them from.
    """
    server._record_deck_dedup_stats("job-g", "u", "L1", {
        "cards": 10, "pairs": 2, "cards_in_pairs": 4, "dropped": 1,
        "restored": 0, "applied": True})
    server._record_deck_gate_counters("job-g", "u", "L1", {
        "gate_considered": 30, "gate_passed": 6, "gate_fairness": 24})

    written = _decided_by(mem_engine, "job-g")
    assert written["deduped_cards_per_job"] == 1      # dedup survived
    assert written["near_dup_pairs"] == 2
    assert written["gate_fairness"] == 24             # …beside the gates
    assert written["gate_considered"] == 30


def test_gate_counter_write_never_breaks_a_deck(mem_engine):
    """Observational writes are best-effort by contract.

    SABOTAGE: drop the try/except ⇒ a counter-table problem 500s a deck that
    was already generated successfully.
    """
    with patch.object(server, "merge_deck_job_counters",
                      side_effect=RuntimeError("db gone")):
        server._record_deck_gate_counters("job-x", "u", "L1",
                                          {"gate_considered": 1})
    server._record_deck_gate_counters("job-y", "u", "L1", {})   # no-op, no row
    assert _decided_by(mem_engine, "job-y") is None
