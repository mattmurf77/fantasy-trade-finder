"""Bake-off arm D — the landability challenger.

Spec: docs/plans/landability-challenger/PRD.md (§5 A4 names the tests below).
Evidence: docs/reviews/2026-08-19-armb-audit-consolidated.md.

The arm asks a different question of the same engine:

    show trades two sides could both take — even on consensus, dual-surplus
    on boarded pairs — and stop ranking the most lopsided star deal first.

It is a **config overlay**, not a code branch and not a new generator, which
buys two properties this file exists to prove:

**1. Arm B does not move.** The live serving engine must be byte-identical
whether or not the challenger exists. That is the load-bearing invariant of
the whole design, and it is proved rather than asserted: `GOLDEN_B_*` below
were captured at `CHALLENGER_BASE_SHA` — `origin/main` immediately before the
three new knobs were added — so today's live-defaults output must equal output
produced by code that had never heard of them. If a knob's default turns out
not to be a true no-op, that is what fails.

**2. Arm A does not move either.** The challenger was briefed as "the new arm
A" and the PRD rejects that outright (N1): `MODEL_A_PROFILE` is a pinned
reconstruction of the pre-G6 engine, and overwriting it makes every bake-off
comparison unfalsifiable. Arm A is untouched here — the only edit to
`test_bakeoff_arm_a_golden.py` is five new names in `_PINNED_KNOBS`, and its
captured deck is byte-for-byte what it was.

Capture procedure for the arm-B goldens, re-run only if the fixture changes::

    git worktree add /tmp/ftf-base <CHALLENGER_BASE_SHA>
    cp backend/tests/test_bakeoff_challenger.py /tmp/ftf-base/backend/tests/
    (cd /tmp/ftf-base && python3 -m backend.tests.test_bakeoff_challenger)

At the base SHA the challenger knobs and `model_challenger` do not exist; both
imports are guarded for exactly that run.
"""

import json

import pytest

import backend.bakeoff_runner as bo
import backend.feature_flags as ff
import backend.trade_service as ts
from backend.bakeoff_profiles import MODEL_A_PROFILE
from backend.trade_service import League, LeagueMember, TradeService

try:                       # absent at the base SHA — capture mode only
    from backend.bakeoff_profiles import (MODEL_CHALLENGER_PROFILE,
                                          model_challenger)
    _CHALLENGER_PRESENT = "consensus_both_ways" in ts._DEFAULT_CFG
except ImportError:                                   # pragma: no cover
    MODEL_CHALLENGER_PROFILE, model_challenger = {}, None
    _CHALLENGER_PRESENT = False

#: The `origin/main` commit the arm-B goldens were captured at — the last
#: commit before `user_elo_shrink` / `consensus_both_ways` /
#: `consensus_fairness_floor` entered `trade_service._DEFAULT_CFG`.
CHALLENGER_BASE_SHA = "50e0451"

#: The three NEW `_DEFAULT_CFG` keys and their live-identity defaults. The
#: other six profile entries are pre-existing knobs whose live defaults the
#: challenger does not touch.
NEW_KNOBS = {
    "user_elo_shrink":          1.0,
    "consensus_both_ways":      0.0,
    "consensus_fairness_floor": 0.0,
}


# ───────────────────────────────────────────────────────────────────────────
# Fixture — every input a literal, so these comparisons isolate GENERATION
# logic and are immune to board-computation drift. That is what lets the
# arm-B golden be captured at a different commit and still mean something.
# ───────────────────────────────────────────────────────────────────────────

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


#: The user's roster. `hub` is elite-band (>= 1700 in `_tier_mult_v2`), the
#: rest ladder down so 1-for-1s land at a spread of fairness ratios.
_USER = {"hub": ("WR", 1700.0), "uw": ("WR", 1600.0), "uq": ("QB", 1560.0),
         "ur1": ("RB", 1500.0), "ur2": ("RB", 1470.0), "ut": ("TE", 1400.0)}

#: The partner's roster. He has NO rankings, which is what routes him to
#: `_generate_consensus_for_pair` — the path that is 84.5% of served cards and
#: the only place `consensus_both_ways` and `consensus_fairness_floor` live.
#: Values are chosen so that against the user's roster the emitted 1-for-1s
#: span the interesting bands: pairs above 0.75, pairs between 0.50 and 0.75
#: (what the floor removes), and pairs in BOTH directions.
_OPP = {"o_hi": ("WR", 1665.0), "o_mid": ("RB", 1585.0),
        "o_low": ("TE", 1520.0), "o_dep": ("WR", 1430.0)}

_FAIRNESS = 0.50          # the loose client toggle the floor has to override


def _fixture():
    players, seed = {}, {}
    for pid, (pos, elo) in {**_USER, **_OPP}.items():
        players[pid] = _Player(pid, pos)
        seed[pid] = elo
    opp = LeagueMember(user_id="opp", username="opp", roster=list(_OPP),
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, seed, opp


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _reset_cfg(**cfg):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)


def _consensus(cfg=None, *, overlay=False, threshold=_FAIRNESS):
    """The consensus generator, uncapped and with `presentment_ok_fn=None`.

    Called directly rather than through a deck because the deck-assembly caps
    (`deck_max_per_target`, the headliner caps, diversity) cut most of this
    path before it can be served — measured through a deck alone, the two
    consensus knobs would look inert while being perfectly alive.
    """
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    _reset_cfg(**(cfg or {}))
    svc, seed, opp = _fixture()
    user_roster = list(_USER)
    elos = dict(seed)

    def _sv(pid):
        return ts.elo_to_value(seed.get(pid, 1500.0))

    prof = ts.analyze_roster_strengths
    kw = dict(
        user_id="user", opponent=opp, league_id="L1", seed_value=_sv,
        shrunk_user_elo=elos, user_roster=user_roster, max_cards=200,
        fairness_threshold=threshold,
        user_profile=prof(user_roster, svc._players, "1qb_ppr"),
        opp_profile=prof(opp.roster, svc._players, "1qb_ppr"),
        acquire_positions=[], trade_away_positions=[],
        pinned_give_players=None, raw_user_elo=dict(elos),
        presentment_ok_fn=None)
    if overlay:
        with model_challenger():
            cards = svc._generate_consensus_for_pair(**kw)
    else:
        cards = svc._generate_consensus_for_pair(**kw)
    return sorted([sorted(c.give_player_ids), sorted(c.receive_player_ids),
                   c.fairness_score, c.composite_score,
                   c.give_value, c.receive_value] for c in cards)


def _deck(cfg=None, *, overlay=False):
    """A full `generate_trades` sweep — the arm-B byte-identity surface that
    covers dedup, deck caps and the v2 orchestration, not just the generator."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    _reset_cfg(**(cfg or {}))
    svc, seed, _opp = _fixture()
    user_roster = list(_USER)

    def _run():
        return svc.generate_trades(
            user_id="user", user_elo=dict(seed), user_roster=user_roster,
            league_id="L1", seed_elo=dict(seed),
            fairness_threshold=_FAIRNESS, max_per_opponent=20,
            confidence={"hub": 0, "uw": 3, "uq": 40},
            outlook="contender", is_dynasty=True, exclusion_keys=set())

    if overlay:
        with model_challenger():
            cards = _run()
    else:
        cards = _run()
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.composite_score, c.fairness_score] for c in cards]


# ── arm-B goldens, captured at CHALLENGER_BASE_SHA ─────────────────────────

_GOLDEN_B_DECK_JSON = """\
[["ut","uw"],["o_hi"],0.359,0.957],
[["uq","ur2"],["o_hi"],0.355,0.946],
[["ur2","ut"],["o_mid"],0.353,0.94],
[["uq"],["o_mid"],0.331,0.883],
[["ur1"],["o_low"],0.271,0.905],
[["ur2"],["o_low"],0.234,0.779],
"""

_GOLDEN_B_CONS_JSON = """\
[["uq"],["o_hi"],0.592,0.222,1349.9,2281.9],
[["uq"],["o_mid"],0.883,0.331,1349.9,1529.6],
[["uq","ur2"],["o_hi"],0.946,0.355,2158.5,2281.9],
[["uq","ut"],["o_hi"],0.831,0.312,1896.4,2281.9],
[["ur1"],["o_low"],0.905,0.271,1000.0,1105.2],
[["ur1"],["o_mid"],0.654,0.245,1000.0,1529.6],
[["ur1","ur2"],["o_hi"],0.807,0.303,1842.1,2281.9],
[["ur1","ut"],["o_hi"],0.686,0.257,1566.3,2281.9],
[["ur2"],["o_low"],0.779,0.234,860.7,1105.2],
[["ur2"],["o_mid"],0.563,0.211,860.7,1529.6],
[["ur2","ut"],["o_hi"],0.63,0.236,1438.0,2281.9],
[["ur2","ut"],["o_mid"],0.94,0.353,1438.0,1529.6],
[["ut"],["o_dep"],0.861,0.142,606.5,704.7],
[["ut"],["o_low"],0.549,0.165,606.5,1105.2],
[["ut","uw"],["o_hi"],0.957,0.359,2183.7,2281.9],
[["uw"],["o_hi"],0.723,0.271,1648.7,2281.9],
"""


def _rows(blob):
    blob = blob.strip().rstrip(",")
    return [json.loads(line) for line in blob.split(",\n")] if blob else []


GOLDEN_B_DECK = _rows(_GOLDEN_B_DECK_JSON)
GOLDEN_B_CONS = _rows(_GOLDEN_B_CONS_JSON)


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


_B_REMEDY = (
    "Arm B — the LIVE serving engine, what users actually see — moved. This "
    "is the load-bearing invariant of the whole challenger design: the arm "
    "is an OVERLAY, so with the overlay unentered nothing may change. Either "
    "a new knob's default is not a true no-op, or challenger code runs "
    "outside `model_challenger()`. Fix the knob. Do NOT re-capture this "
    f"golden — it was taken at {CHALLENGER_BASE_SHA}, by code that had never "
    "heard of the knobs, and re-capturing destroys the only proof there is.")


# ───────────────────────────────────────────────────────────────────────────
# The invariant: arm B is byte-identical with the overlay off
# ───────────────────────────────────────────────────────────────────────────

def test_arm_b_deck_is_byte_identical_to_the_pre_challenger_engine():
    assert _deck() == GOLDEN_B_DECK, _B_REMEDY


def test_arm_b_consensus_generator_is_byte_identical():
    """The surface that matters most: 84.5% of served cards take this path,
    and all three new knobs are reachable from it."""
    assert _consensus() == GOLDEN_B_CONS, _B_REMEDY


def test_new_knob_defaults_are_the_live_identity():
    """PRD N2. A default edited to a challenger value would ship the arm to
    every live user without anyone entering the overlay."""
    for key, val in NEW_KNOBS.items():
        assert ts._DEFAULT_CFG[key] == val, key


def test_every_new_knob_is_inert_at_its_default():
    """Per-knob no-op proof, independent of the goldens. Setting a knob
    EXPLICITLY to the value `_DEFAULT_CFG` already carries must reproduce arm
    B — this catches a knob that is inert only because some other guard
    happens to skip its code path."""
    deck_b, cons_b = _deck(), _consensus()
    for key, val in NEW_KNOBS.items():
        assert _deck({key: val}) == deck_b, f"{key} (deck)"
        assert _consensus({key: val}) == cons_b, f"{key} (consensus)"


# ───────────────────────────────────────────────────────────────────────────
# A4.1 / A4.3 — the two profiles are independent
# ───────────────────────────────────────────────────────────────────────────

def test_the_two_profiles_do_not_collide():
    """Arm A reconstructs the PAST; arm D proposes a FUTURE. They may share a
    value only by coincidence, and exactly one such coincidence is expected:
    both zero `need_gate_min_value`, arm A because R5 postdates its reference
    SHA and arm D because R5 kills landable trades."""
    shared = set(MODEL_A_PROFILE) & set(MODEL_CHALLENGER_PROFILE)
    assert shared == {"need_gate_min_value"}, (
        "the challenger profile overlaps arm A's beyond the one expected "
        f"coincidence: {sorted(shared)}. Arm A is a pinned constant (D-075); "
        "a shared knob means one of the two is drifting toward the other.")
    assert MODEL_A_PROFILE["need_gate_min_value"] == 0.0
    assert MODEL_CHALLENGER_PROFILE["need_gate_min_value"] == 0.0
    # …and the new keys are NOT in arm A's profile. Their defaults ARE the
    # pre-wave engine, so pinning a kill value would CHANGE arm A rather than
    # preserve it (PRD N1, scope-phase2.md § Excluded).
    for key in NEW_KNOBS:
        assert key not in MODEL_A_PROFILE, key


def test_model_a_still_sees_the_live_identity_for_the_new_knobs():
    """Arm A must be unaware the challenger exists. If it ever read a
    challenger value it would skip shrinkage and emit both directions —
    behaviour the pre-wave engine never had, silently rewriting the baseline
    every comparison is measured against."""
    from backend.bakeoff_profiles import model_a
    _reset_cfg()
    with model_a():
        for key, val in NEW_KNOBS.items():
            assert ts._c(key) == val, key


def test_model_challenger_does_not_bypass_r4():
    """A4.2. Arm A bypasses the windowless awaiting/matched exclusion because
    R4 postdates its reference SHA and has no kill knob. The challenger has no
    such excuse — and re-serving a trade the user already has pending is not a
    more landable trade."""
    assert ts.r4_bypassed() is False
    with model_challenger():
        assert ts.r4_bypassed() is False
    assert ts.r4_bypassed() is False


def test_the_overlay_is_thread_local_and_leaves_nothing_behind():
    import threading
    seen = {}
    started, release = threading.Event(), threading.Event()

    def _sibling():
        started.set()
        release.wait(5)
        seen["both_ways"] = ts._c("consensus_both_ways")

    t = threading.Thread(target=_sibling)
    t.start()
    started.wait(5)
    _reset_cfg()
    with model_challenger():
        assert ts._c("consensus_both_ways") == 1.0
        release.set()
        t.join(5)
    assert seen["both_ways"] == 0.0, \
        "the overlay leaked into a concurrent trade job"
    assert ts._c("consensus_both_ways") == 0.0
    assert getattr(ts._cfg_local, "map", None) in (None, {})


# ───────────────────────────────────────────────────────────────────────────
# A4.5 — shrink-neither (`user_elo_shrink`)
# ───────────────────────────────────────────────────────────────────────────

def test_shrink_at_zero_comparisons_is_seed_live_and_raw_under_the_overlay():
    """The PRD's named case. At n = 0 the live blend has w = 0, so the user's
    own number is replaced wholesale by consensus — while the PARTNER's board
    is used raw. That asymmetry is the boarded-pair one-sidedness (86.9%)."""
    user_elo = {"a": 1800.0, "b": 1200.0}
    seed = {"a": 1500.0, "b": 1500.0}
    counts = {"a": 0, "b": 0}

    _reset_cfg()
    assert ts._shrink_user_elo(user_elo, seed, counts) == seed

    _reset_cfg()
    with model_challenger():
        assert ts._shrink_user_elo(user_elo, seed, counts) == user_elo


def test_shrink_off_is_not_the_same_as_a_zero_pseudocount():
    """PRD §4 calls this out explicitly: `shrink_pseudocount = 0` is NOT a
    substitute, because w = n/(n+0) is undefined at n = 0. The knob exists
    because the obvious alternative crashes on the exact case it must handle."""
    _reset_cfg(shrink_pseudocount=0.0)
    with pytest.raises(ZeroDivisionError):
        ts._shrink_user_elo({"a": 1800.0}, {"a": 1500.0}, {"a": 0})
    _reset_cfg()
    with model_challenger():
        assert ts._shrink_user_elo({"a": 1800.0}, {"a": 1500.0},
                                   {"a": 0}) == {"a": 1800.0}


def test_a_well_sampled_player_is_unmoved_by_the_knob():
    """Non-vacuity from the other side: at a high comparison count the live
    blend already sits near the raw board, so the knob's effect must be
    concentrated on thinly-sampled players — which is what makes it a
    correction rather than a global rescale."""
    user_elo, seed = {"a": 1800.0}, {"a": 1500.0}
    _reset_cfg()
    heavy = ts._shrink_user_elo(user_elo, seed, {"a": 10_000})["a"]
    thin = ts._shrink_user_elo(user_elo, seed, {"a": 0})["a"]
    assert heavy == pytest.approx(1800.0, abs=1.0)
    assert thin == 1500.0


# ───────────────────────────────────────────────────────────────────────────
# A4.6 — consensus both-ways and the floor
# ───────────────────────────────────────────────────────────────────────────

def _user_pays(rows):
    """Cards where the user gives more consensus value than they receive —
    the direction the live `rv >= gv` sign test makes unrepresentable."""
    return [r for r in rows if r[5] < r[4]]        # receive_value < give_value


def test_live_never_emits_a_card_the_user_pays_for():
    """The viewer-wins identity, stated as a test so the challenger's change
    to it is legible. 0 of N, not merely a tilt."""
    rows = _consensus()
    assert rows, "the fixture generates no consensus cards"
    assert _user_pays(rows) == []


def test_both_ways_emits_the_user_pays_direction():
    """A4.6 / PRD G3. With the overlay on, the same even trade can surface in
    the direction where the PARTNER is the one who gains."""
    rows = _consensus(overlay=True)
    paying = _user_pays(rows)
    assert paying, "both-ways emitted nothing the user pays for"
    # Every one of them is still FAIR — that is what makes it a trade rather
    # than a fleece in the other direction.
    for r in paying:
        assert r[2] >= 0.75, r
    # …and the new direction is genuinely new supply, not a relabelling: every
    # one-way card that still clears the floor is still there. (Cards below
    # 0.75 are gone, but that is the FLOOR's doing, not the direction's — the
    # two knobs travel together precisely so that trade is explicit.)
    both = {(tuple(r[0]), tuple(r[1])) for r in rows}
    kept = {(tuple(r[0]), tuple(r[1])) for r in _consensus() if r[2] >= 0.75}
    assert kept and kept <= both
    # The user-pays cards are all NEW keys, never re-labelled old ones.
    assert {(tuple(r[0]), tuple(r[1])) for r in paying}.isdisjoint(kept)


def test_the_floor_only_ever_tightens():
    """`max(requested, floor)`. A client that asks for MORE than 0.75 must
    still get what it asked for — the floor is a bar, not an override."""
    strict = _consensus(overlay=True, threshold=0.90)
    assert strict, "nothing survives at 0.90"
    for r in strict:
        assert r[2] >= 0.90, r


def test_the_floor_kills_the_cards_between_the_client_toggle_and_075():
    """The knob in isolation: at the live 0.50 toggle the engine serves cards
    the challenger's floor removes, and everything it removes is sub-floor.
    Opening both directions at 0.50 without this is a 2:1 user-pays flood."""
    loose = _consensus()
    floored = _consensus({"consensus_fairness_floor": 0.75})
    dropped = [r for r in loose if r not in floored]
    assert dropped, "the fixture generates no cards between 0.50 and 0.75"
    assert all(r[2] < 0.75 for r in dropped)
    assert all(r[2] >= 0.75 for r in floored)
    assert all(r in loose for r in floored), "the floor only ever subtracts"


def test_one_for_two_exists_only_under_both_ways():
    """PRD G3 / A2. Production holds 6,635 `1x1` and 459 `2x1` packages and
    exactly ZERO `1x2`: partner-favourable consolidation is unrepresentable,
    not merely rare, because every such shape dies on the sign test."""
    def shapes(rows):
        return {(len(r[0]), len(r[1])) for r in rows}

    live = shapes(_consensus())
    assert (1, 2) not in live
    assert (2, 1) in live, "the fixture no longer exercises consolidation"
    assert (1, 2) in shapes(_consensus(overlay=True))


def test_a_sub_floor_two_for_one_stays_dead_under_the_overlay():
    """The PRD's done-when for A2: a 0.40-fairness 2:1 is still dead even if
    the client sent 0.50. Both-ways opens the DIRECTION, never the bar."""
    rows = _consensus(overlay=True, threshold=0.50)
    assert rows
    assert all(r[2] >= 0.75 for r in rows), \
        "both-ways let a card through below the floor"


# ───────────────────────────────────────────────────────────────────────────
# A3 — the compressed tier ladder
# ───────────────────────────────────────────────────────────────────────────

def _consensus_composite(elo_map, pids, fairness):
    """The consensus composite, spelled exactly as `_generate_consensus_for_
    pair` spells it: fairness x tier_mult x consensus_score_scale."""
    svc, _seed, _opp = _fixture()
    return (fairness * svc._tier_mult_v2(elo_map, pids)
            * ts._c("consensus_score_scale"))


def test_the_challenger_ladder_lets_fairness_beat_the_biggest_name():
    """A3's done-when. Live spans 4.57x (0.35 -> 1.60) against fairness's
    2.00x, so the biggest name wins regardless of balance: an elite card at
    fairness 0.70 outranks a perfectly even solid one. The challenger ladder
    spans 1.44x and the even card leads."""
    elos = {"elite": 1750.0, "solid": 1500.0}

    def pair():
        return (_consensus_composite(elos, ["elite"], 0.70),
                _consensus_composite(elos, ["solid"], 1.00))

    _reset_cfg()
    elite_live, solid_live = pair()
    assert elite_live > solid_live, \
        "the fixture no longer reproduces the live tier-over-fairness bias"

    _reset_cfg()
    with model_challenger():
        elite_new, solid_new = pair()
    assert solid_new > elite_new, \
        "the compressed ladder still lets the biggest name outrank balance"


def test_the_ladder_compresses_rather_than_rescales():
    """A uniform rescale would leave every ranking identical and the fix
    inert. The span must actually shrink, and below the fairness span so tier
    can break ties without overruling them."""
    live = [MODEL_A_PROFILE.get(k, ts._DEFAULT_CFG[k]) for k in
            ("tier_mult_elite", "tier_mult_bench")]
    live_span = ts._DEFAULT_CFG["tier_mult_elite"] / \
        ts._DEFAULT_CFG["tier_mult_bench"]
    new_span = (MODEL_CHALLENGER_PROFILE["tier_mult_elite"]
                / MODEL_CHALLENGER_PROFILE["tier_mult_bench"])
    assert live_span == pytest.approx(4.571, abs=0.01)
    assert new_span == pytest.approx(1.4375, abs=0.001)
    # Fairness at the challenger's 0.75 floor spans 1/0.75 = 1.33x. Tier must
    # sit near it, not four times it.
    assert new_span < live_span
    assert MODEL_CHALLENGER_PROFILE["tier_mult_solid"] == 1.0, \
        "solid must stay the pivot or the whole ladder shifts, not compresses"
    assert live  # the read above is what pins arm A's ladder as untouched


# ───────────────────────────────────────────────────────────────────────────
# A4.4 / A4.8 — fan-out and roster
# ───────────────────────────────────────────────────────────────────────────

class _FanCard:
    def __init__(self, tag):
        self.give_player_ids = [f"g{tag}"]
        self.receive_player_ids = [f"r{tag}"]
        self.target_user_id = "opp"
        self.basis = "divergence"
        self.lane = "value"


def _fanout(**knobs):
    """Drive `run_bakeoff` with stub generators, recording the thread-local
    overlay each arm's generator actually saw."""
    from unittest.mock import patch
    seen = []

    def generate(**_ov):
        overlay = dict(getattr(ts._cfg_local, "map", None) or {})
        seen.append((overlay, ts.r4_bypassed()))
        return [_FanCard(len(seen))]

    def gen_v2(**_ov):
        seen.append((dict(getattr(ts._cfg_local, "map", None) or {}),
                     ts.r4_bypassed()))
        return [_FanCard("c")]

    cfg = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0, **knobs}
    with patch.object(bo, "_cfg", lambda k, d: float(cfg.get(k, d))), \
            patch.object(bo, "draft_order_for",
                         lambda parts, lid, wk=None: list(parts)):
        run = bo.run_bakeoff(generate=generate, gen_v2=gen_v2,
                             league_id="l", interleave=False, limit=None)
    return run, seen


def test_the_fanout_enters_the_overlay_only_on_the_challenger_call():
    """A4.4. The arm IS the overlay, so an overlay that leaks into arm B's
    call would make the two arms the same model while reporting them as
    different — the one failure mode that would not show up as an error."""
    run, seen = _fanout()
    assert set(run.arms) == {"current", "challenger", "gen_v2"}
    entered = [ov for ov, _r4 in seen if ov]
    assert len(entered) == 1, \
        f"expected exactly one arm inside an overlay, saw {len(entered)}"
    assert entered[0] == MODEL_CHALLENGER_PROFILE
    # No arm bypasses R4 on the default roster (arm A is off it).
    assert all(r4 is False for _ov, r4 in seen)
    # …and the overlay is gone once the run returns.
    assert getattr(ts._cfg_local, "map", None) in (None, {})


def test_the_challenger_config_is_snapshotted_inside_its_own_overlay():
    """Taken outside the context, arm D would be recorded as if it had run on
    live defaults — and `config_json` is the only record of what produced each
    card, since `model_config` has no `updated_at`."""
    run, _seen = _fanout()
    cfg = run.arms["challenger"].config
    assert cfg, "the challenger's config was not captured"
    for key, val in MODEL_CHALLENGER_PROFILE.items():
        assert cfg[key] == val, key
    delta = run.config_record()["arm_delta"]["challenger"]
    assert delta and set(delta) <= set(MODEL_CHALLENGER_PROFILE)
    assert run.config_record()["arm_delta"]["gen_v2"] == {}


def test_the_kill_knob_restores_the_pre_challenger_roster():
    """A4.8. One value, no deploy — and it gives back the extra full
    `generate_trades` per organic job, which is the arm's whole cost."""
    run, seen = _fanout(bakeoff_include_challenger=0.0)
    assert set(run.arms) == {"current", "gen_v2"}
    assert all(not ov for ov, _r4 in seen), \
        "an overlay was entered with the challenger off the roster"


def test_dropping_arm_c_leaves_a_clean_head_to_head():
    run, _seen = _fanout(bakeoff_include_gen_v2=0.0)
    assert set(run.arms) == {"current", "challenger"}


# ───────────────────────────────────────────────────────────────────────────
# A4.7 — knob inventory
# ───────────────────────────────────────────────────────────────────────────

def test_every_new_knob_is_pinned_in_the_arm_a_inventory():
    """The guard that stops arm A rotting is a literal name list in
    `test_bakeoff_arm_a_golden.py`. A new knob absent from it fails that test;
    a new knob absent from `_DEFAULT_CFG` fails this one. Both directions
    matter — the point is that no knob exists without a written arm-A
    decision."""
    from backend.tests.test_bakeoff_arm_a_golden import _PINNED_KNOBS
    for key in ("user_elo_shrink", "consensus_both_ways",
                "consensus_fairness_floor", "bakeoff_include_challenger",
                "bakeoff_include_gen_v2"):
        assert key in ts._DEFAULT_CFG, key
        assert key in _PINNED_KNOBS, (
            f"{key} is not pinned in the arm-A knob inventory")


def test_the_profile_only_names_knobs_that_exist():
    unknown = sorted(set(MODEL_CHALLENGER_PROFILE) - set(ts._DEFAULT_CFG))
    assert not unknown, (
        f"MODEL_CHALLENGER_PROFILE names knobs that no longer exist: "
        f"{unknown}. A renamed knob makes the arm silently stop applying "
        "whatever replaced it.")


if __name__ == "__main__":            # capture mode — see the module docstring
    def _block(label, rows):
        print(f'{label} = """\\')
        for row in rows:
            print(json.dumps(row, separators=(",", ":")) + ",")
        print('"""')
        print()

    _block("_GOLDEN_B_DECK_JSON", _deck())
    _block("_GOLDEN_B_CONS_JSON", _consensus())
