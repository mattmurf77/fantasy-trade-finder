"""Arm A of the three-model bake-off IS the pre-wave engine — proof.

`docs/plans/three-model-bakeoff/PLAN.md` §1: arm A ("baseline") is not a code
branch. The original trade-generation logic was modified **in place** by the
2026-08-16 G6 presentment wave and the 2026-08-18 engine-quality wave, so
"original" survives only as `bakeoff_profiles.MODEL_A_PROFILE` (nine knob
kill-values) plus the R4 thread-local bypass (R4 has no knob). If that set is
not pinned and golden-tested it drifts silently, and the whole bake-off
becomes unfalsifiable with no visible symptom.

Reference SHA: **92c31d5** — `20b40db^` on `--first-parent main`, i.e. the
last commit before the G6 wave. `MODEL_A_REFERENCE_SHA` carries it in code.

**Why this fixture pins its own board.** A lot legitimately changed between
92c31d5 and today that alters generation *inputs*: Phase 0's pin fix
(`pin_exclude_comparisons`, `pin_unpin_on_newer_swipe`), tier-bounded voting,
premium import. A naive end-to-end golden would differ for reasons unrelated
to the two waves and be worse than useless. So every input here is a
**literal**: the player table, `seed_elo` (the consensus board), `user_elo`
(the user's board), each opponent's `elo_ratings`, the confidence counts, the
roster, the outlook, the fairness threshold. Nothing is computed from the DB,
from `ranking_service`, or from a fixture file. The comparison therefore
isolates **generation logic** and is immune to board-computation drift by
construction.

Capture procedure (re-run only if the fixture changes — and re-read the
scope block first, because a changed fixture invalidates the pin):

    git worktree add /tmp/ftf-prewave 92c31d5
    cp backend/tests/test_bakeoff_arm_a_golden.py /tmp/ftf-prewave/backend/tests/
    (cd /tmp/ftf-prewave && python3 -m backend.tests.test_bakeoff_arm_a_golden)

At 92c31d5 neither wave's knobs exist and `generate_trades` has no
`exclusion_keys` parameter, so the capture run needs no configuration and
passes no G6 kwargs: what it prints IS the prior behaviour. The
`bakeoff_profiles` import is guarded for exactly that run.
"""

import json

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService

try:                       # absent at the reference SHA — capture mode only
    from backend.bakeoff_profiles import (MODEL_A_PROFILE,
                                          MODEL_A_REFERENCE_SHA, model_a)
except ImportError:                                   # pragma: no cover
    MODEL_A_PROFILE, MODEL_A_REFERENCE_SHA, model_a = {}, "92c31d5", None


# ── literal asset table ────────────────────────────────────────────────────
# (position, consensus/seed elo, the USER's elo). Divergence between the two
# boards is what the engine trades on, so both are pinned.

_USER_ASSETS = {
    # id        pos      seed     user
    "hub":     ("WR",   1700.0,  1600.0),   # headliner: many cards (C4/R1)
    "uw1":     ("WR",   1600.0,  1600.0),
    "uw2":     ("WR",   1500.0,  1500.0),
    "uq":      ("QB",   1500.0,  1500.0),
    "ur1":     ("RB",   1500.0,  1500.0),
    "ur2":     ("RB",   1500.0,  1500.0),
    "ut":      ("TE",   1500.0,  1500.0),
    "PKu":     ("PICK", 1560.0,  1560.0),
    "PKus":    ("PICK", 1300.0,  1300.0),   # small pick (R3/C3 fodder)
}

# Three opponents. `star` diverges hard in the USER's favour (the engine's
# raison d'etre); `lowN` is a body the user overrates and consensus does not
# (R5 fodder — a received starter who upgrades nothing); the picks give R3
# and C3 something to bite on.
_OPP_ASSETS = {
    1: {"star1": ("WR",   1620.0, 1750.0), "low1": ("WR",   1450.0, 1800.0),
        "PKo1":  ("PICK", 1555.0, 1555.0), "PKs1": ("PICK", 1330.0, 1330.0)},
    2: {"star2": ("WR",   1620.0, 1750.0), "low2": ("WR",   1450.0, 1800.0),
        "PKo2":  ("PICK", 1555.0, 1555.0), "PKs2": ("PICK", 1330.0, 1330.0)},
    3: {"star3": ("WR",   1620.0, 1750.0), "low3": ("WR",   1450.0, 1800.0),
        "PKo3":  ("PICK", 1555.0, 1555.0), "PKs3": ("PICK", 1330.0, 1330.0)},
}

# Filler bodies every roster needs to field a legal lineup, at parity on both
# boards so they carry no divergence of their own.
_FILL = {"q": "QB", "r1": "RB", "r2": "RB", "w1": "WR", "w2": "WR", "t": "TE"}

# Each opponent's own board, for the assets where it matters. Everything not
# listed sits at 1500 (see _fixture). star: their own board underrates him —
# that is the trade. hub: they covet him. low: they are happy to move him.
_OPP_BOARD = {
    "star": 1560.0, "low": 1400.0, "hub": 1800.0,
    "uw1": 1700.0, "uw2": 1700.0,
}

# C5 (mismatch_confidence_damp) reads comparison counts: a huge apparent
# divergence resting on a barely-ranked player is damped. Spread the counts.
_CONFIDENCE = {"hub": 2, "star1": 1, "star2": 30, "star3": 300,
               "low1": 1, "low2": 30, "low3": 300}

_OUTLOOK = "contender"          # R5 only binds on contender/championship
_FAIRNESS = 0.6


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
    def __init__(self, pid):
        super().__init__(pid, position="PICK", team="PICK", age=0)
        self.pick_value = 60.0


def _mk(pid, pos):
    return _Pick(pid) if pos == "PICK" else _Player(pid, pos)


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _reset_cfg(**cfg):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)


def _fixture():
    """Build the league. Every value is a literal from the tables above."""
    players, seed, user_elo = {}, {}, {}

    for pid, (pos, s, u) in _USER_ASSETS.items():
        players[pid] = _mk(pid, pos)
        seed[pid], user_elo[pid] = s, u
    for k, pos in _FILL.items():
        pid = f"u{k}"
        if pid not in players:
            players[pid] = _mk(pid, pos)
            seed[pid] = user_elo[pid] = 1500.0
    user_roster = list(_USER_ASSETS) + [f"u{k}" for k in _FILL
                                        if f"u{k}" not in _USER_ASSETS]

    members = []
    for n, assets in _OPP_ASSETS.items():
        roster = []
        for pid, (pos, s, u) in assets.items():
            players[pid] = _mk(pid, pos)
            seed[pid], user_elo[pid] = s, u
            roster.append(pid)
        for k, pos in _FILL.items():
            pid = f"o{n}{k}"
            players[pid] = _mk(pid, pos)
            seed[pid] = user_elo[pid] = 1500.0
            roster.append(pid)
        opp_elo = {pid: 1500.0 for pid in players}
        for pid in players:
            for prefix, val in _OPP_BOARD.items():
                if pid == prefix or pid == f"{prefix}{n}":
                    opp_elo[pid] = val
        members.append(LeagueMember(
            user_id=f"opp{n}", username=f"opp{n}", roster=roster,
            elo_ratings=opp_elo, has_rankings=True))

    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=members))
    return svc, user_elo, user_roster, seed


def _shape(cards):
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.mismatch_score] for c in cards]


def _generate(svc, user_elo, user_roster, seed, *, exclusion_keys=None):
    """The ONE generation call. Only pre-reference-SHA kwargs are passed
    unconditionally, so this same file runs at 92c31d5."""
    kw = {}
    if exclusion_keys is not None:          # G6-era kwarg — capture omits it
        kw["exclusion_keys"] = exclusion_keys
    return svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed, fairness_threshold=_FAIRNESS,
        max_per_opponent=10, confidence=dict(_CONFIDENCE),
        outlook=_OUTLOOK, is_dynasty=True, **kw)


def _deck(cfg=None, *, presentment=False, exclusion_keys=None, arm_a=False):
    _set_flags(**{"trade_engine.v2": True,
                  "trade.presentment_rules": bool(presentment)})
    _reset_cfg(**(cfg or {}))
    svc, ue, ur, seed = _fixture()
    if arm_a:
        with model_a():
            cards = _generate(svc, ue, ur, seed, exclusion_keys=exclusion_keys)
    else:
        cards = _generate(svc, ue, ur, seed, exclusion_keys=exclusion_keys)
    return svc, _shape(cards)


# ── second generation surface: the pinned asset-ideas ranker ───────────────
# C2 (`min_package_band`) lives ONLY in `_emit_best`, which the deck path
# never reaches — so a deck-only golden would carry a knob in the profile
# that nothing here proves. Same literal-board discipline as above.

_IDEA_ELOS = {"P": 1700.0, "S": 1440.0, "S2": 1400.0,
              "U": 1721.0, "U2": 1730.0}


def _ideas(cfg=None, *, arm_a=False):
    players = {pid: _Player(pid, "RB") for pid in _IDEA_ELOS}
    opp = LeagueMember(user_id="opp", username="Opp", roster=["U", "U2"],
                       elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    _set_flags(**{"trade.asset_ideas": True})
    _reset_cfg(**(cfg or {}))

    def _run():
        with ts.stud_tax_override("heavy"):
            return svc.generate_asset_ideas(
                league_id="L1", user_id="user", asset_id="P",
                direction="give", user_roster=["P", "S", "S2"],
                seed_elo=dict(_IDEA_ELOS), raw_user_elo={},
                fairness_threshold=0.75)

    groups = _run_as_arm_a(_run) if arm_a else _run()
    return {g: [[i["give_player_ids"], i["receive_player_ids"],
                 i["difference"], i["fairness"]] for i in ideas]
            for g, ideas in groups.items()}


def _run_as_arm_a(fn):
    with model_a():
        return fn()


# ── golden, captured at 92c31d5 ────────────────────────────────────────────

_GOLDEN_JSON = """\
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
[["ur2","ut","uw2"],["PKo2","star2"],"opp2",1.588,0.974,1559.5],
[["ur1","ut","uw2"],["PKo2","star2"],"opp2",1.588,0.974,1559.5],
[["ur1","ur2","uw2"],["PKo2","star2"],"opp2",1.588,0.974,1559.5],
[["uq","ut","uw2"],["PKo2","star2"],"opp2",1.588,0.974,1559.5],
[["ur2","ut","uw2"],["PKo3","star3"],"opp3",1.588,0.974,1685.2],
[["ur1","ut","uw2"],["PKo3","star3"],"opp3",1.588,0.974,1685.2],
[["ur1","ur2","uw2"],["PKo3","star3"],"opp3",1.588,0.974,1685.2],
[["uq","ut","uw2"],["PKo3","star3"],"opp3",1.588,0.974,1685.2],
[["PKus","ut","uw2"],["PKo1","star1"],"opp1",1.019,0.755,1261.7],
[["PKus","ur2","uw2"],["PKo1","star1"],"opp1",1.019,0.755,1261.7],
[["PKus","ur1","uw2"],["PKo1","star1"],"opp1",1.019,0.755,1261.7],
[["PKus","uq","uw2"],["PKo1","star1"],"opp1",1.019,0.755,1261.7],
[["PKus","ut","uw2"],["low1","star1"],"opp1",1.006,0.922,1131.3],
[["PKus","ur2","uw2"],["low1","star1"],"opp1",1.006,0.922,1131.3],
[["PKus","ur1","uw2"],["low1","star1"],"opp1",1.006,0.922,1131.3],
[["PKus","uq","uw2"],["low1","star1"],"opp1",1.006,0.922,1131.3],
[["PKus","uw2"],["star1"],"opp1",0.893,0.727,1063.8],
[["PKus","ut","uw2"],["o1t","star1"],"opp1",0.876,0.847,957.1],
"""

_GOLDEN_IDEAS_JSON = """{"upgrade":[[["P","S"],["U"],450.0,0.851],[["P","S"],["U2"],722.8,0.771]],"lateral":[],"downgrade":[]}"""

GOLDEN = [json.loads(line) for line in
          _GOLDEN_JSON.strip().rstrip(",").split(",\n")]
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


def _drift_report(actual, expected):
    """Name the drift. A bare `assert a == b` on 30 rows of floats tells
    whoever broke this nothing about WHAT moved."""
    lines = [f"arm A no longer reproduces {MODEL_A_REFERENCE_SHA}: "
             f"{len(expected)} golden cards vs {len(actual)} produced."]
    a_keys = {(tuple(r[0]), tuple(r[1]), r[2]): r for r in actual}
    e_keys = {(tuple(r[0]), tuple(r[1]), r[2]): r for r in expected}
    for k in sorted(e_keys.keys() - a_keys.keys()):
        lines.append(f"  MISSING (golden had it, arm A dropped it): {k}")
    for k in sorted(a_keys.keys() - e_keys.keys()):
        lines.append(f"  EXTRA (arm A invented it): {k}")
    for k in sorted(e_keys.keys() & a_keys.keys()):
        if e_keys[k] != a_keys[k]:
            lines.append(f"  SCORES MOVED {k}: golden {e_keys[k][3:]} "
                         f"-> arm A {a_keys[k][3:]}")
    if actual != expected and len(lines) == 1:
        lines.append("  ORDER CHANGED (same cards, different deck order).")
    lines.append("Either a new generation knob needs a kill value in "
                 "MODEL_A_PROFILE, or an existing knob's disable value "
                 "stopped being a true no-op. Fix the profile — do not "
                 "re-capture the golden to make this pass.")
    return "\n".join(lines)


# ── the golden ─────────────────────────────────────────────────────────────

def test_arm_a_reproduces_the_pre_wave_deck():
    """MODEL_A_PROFILE + the R4 bypass, with the G6 flag ON (as it is in
    production), reproduces 92c31d5 exactly."""
    _, rows = _deck(presentment=True, exclusion_keys=set(), arm_a=True)
    assert rows == GOLDEN, _drift_report(rows, GOLDEN)


def test_arm_a_reproduces_the_pre_wave_asset_ideas():
    """The second generation surface. C2 (`min_package_band`) is reachable
    only here, so without this the profile would carry a knob that no golden
    in this file proves."""
    assert _ideas(arm_a=True) == GOLDEN_IDEAS


def test_arm_a_is_flag_independent():
    """The profile alone must carry arm A: flipping trade.presentment_rules
    off must not change arm A's deck. If it does, some part of the G6 wave is
    reachable only through the flag and needs a bypass of its own."""
    _, on = _deck(presentment=True, exclusion_keys=set(), arm_a=True)
    _, off = _deck(presentment=False, arm_a=True)
    assert on == off == GOLDEN


# ── non-vacuity: the golden must not be a tautology ────────────────────────

def test_current_defaults_differ_from_the_golden():
    """Arm B (live defaults) on the SAME fixture must NOT match the golden.
    Without this the golden could quietly become a no-op — a profile that
    disables nothing would still 'pass'."""
    svc, rows = _deck(presentment=True, exclusion_keys=set())
    assert rows != GOLDEN
    assert len(rows) < len(GOLDEN)      # the waves are net-subtractive here
    assert _ideas() != GOLDEN_IDEAS


def test_every_pinned_rule_actually_bites_on_this_fixture():
    """Per-rule non-vacuity. `rows != GOLDEN` could be satisfied by ONE knob;
    then a second knob could silently stop working and nothing would fail.
    Each G6 rule must record kills, and each engine-quality knob must move
    the deck on its own."""
    svc, _ = _deck(presentment=True, exclusion_keys=set())
    kills = svc.presentment_kill_counts()
    for rule in ("R1", "R2", "R3", "R5"):
        assert kills[rule] > 0, f"fixture no longer exercises G6 {rule}"

    # Engine-quality knobs: kill them ONE at a time off the live defaults.
    # Each must move its own surface by itself — C1/C4/C5 the deck, C2 the
    # asset-ideas ranker (the only place `_emit_best` runs).
    _, arm_b = _deck(presentment=True, exclusion_keys=set())
    for knob in ("rank_div_min_frac", "deck_headliner_cap",
                 "deck_give_headliner_cap", "mismatch_confidence_damp"):
        _, one_off = _deck({knob: 0.0}, presentment=True, exclusion_keys=set())
        assert one_off != arm_b, f"fixture no longer exercises {knob}"
    assert _ideas({"min_package_band": 0.0}) != _ideas(), \
        "fixture no longer exercises min_package_band"


def test_pick_pair_strip_kill_value_is_load_bearing():
    """C3 (`pick_pair_strip_frac`) is the one profile entry this fixture's
    DECK cannot exercise: matched pick pairs only kill when stripping empties
    a side, and no such shape survives the other gates on this league. Rather
    than contort the fixture into an unrealistic one, assert C3 at its own
    gate — the profile's kill value must still change `pick_swap_ok`'s
    verdict. (Byte-identity of that kill value is separately pinned by
    test_engine_quality_golden.py.)"""
    players = {"PKa": _Pick("PKa"), "PKb": _Pick("PKb"), "X": _Player("X")}
    values = {"PKa": 1000.0, "PKb": 980.0, "X": 900.0}   # PKa/PKb matched
    give, recv = ["PKa", "X"], ["PKb"]

    _reset_cfg(**MODEL_A_PROFILE)
    assert ts.pick_swap_ok(give, recv, players, values.get) is True
    _reset_cfg()
    assert ts.pick_swap_ok(give, recv, players, values.get) is False


# ── R4: the rule with no knob ──────────────────────────────────────────────

def test_r4_bypass_restores_a_card_the_flag_would_exclude():
    """R4 (#336 windowless awaiting/matched exclusion) has no kill knob, so
    arm A needs the thread-local bypass. Feed the engine an exclusion key for
    a card the golden contains: arm A must keep it. Arm B's R4-respect half
    uses a victim from arm B's OWN current deck — since the 2026-08-21
    package-benchmark fix, arm B no longer emits GOLDEN[0]'s shape on this
    fixture (the cross-benchmarked receive side prices out of band), so a
    golden victim would never reach R4 there."""
    victim = GOLDEN[0]
    key = {(frozenset(victim[0]), frozenset(victim[1]))}

    _, arm_b_full = _deck(presentment=True, exclusion_keys=set())
    assert arm_b_full, "fixture yields no arm-B deck at live defaults"
    b_victim = arm_b_full[0]
    b_key = {(frozenset(b_victim[0]), frozenset(b_victim[1]))}
    svc_b, arm_b = _deck(presentment=True, exclusion_keys=b_key)
    assert [r[:2] for r in arm_b].count(b_victim[:2]) == 0
    assert svc_b.presentment_kill_counts()["R4"] == 1

    svc_a, arm_a = _deck(presentment=True, exclusion_keys=key, arm_a=True)
    assert arm_a == GOLDEN
    assert svc_a.presentment_kill_counts()["R4"] == 0


def test_r4_bypass_is_thread_local():
    """Same discipline as _cfg_override: an arm-A generation on one thread
    must not disable R4 for a concurrent job on another."""
    import threading
    seen = {}
    started, release = threading.Event(), threading.Event()

    def _sibling():
        started.set()
        release.wait(5)
        seen["sibling"] = ts.r4_bypassed()

    t = threading.Thread(target=_sibling)
    t.start()
    started.wait(5)
    with model_a():
        assert ts.r4_bypassed() is True
        release.set()
        t.join(5)
    assert seen["sibling"] is False
    assert ts.r4_bypassed() is False


# ── drift alarm: a new knob must not slip past the profile ─────────────────

#: Every key in `trade_service._DEFAULT_CFG` as of 2026-08-18 (plus later
#: additions, each DECIDED below and in scope-phase2.md's exclusion table —
#: 2026-08-20 added `infer_w_net_firsts` / `infer_net_firsts_cap`, D-110:
#: excluded from MODEL_A_PROFILE because they cannot reach generation at all.
#: The term they weight is gated on BOTH `trade.outlook_net_firsts` AND a
#: caller supplying `first_round_ledger`, and the only caller that does is
#: GET /api/league/team-review — trade_gen_v2, the mock draft and the outlook
#: seed all still pass four positional arguments. Pinning a kill value would
#: imply the knobs matter to a deck; they provably do not.
#: 2026-08-20 added the eight `infer_composite_*` knobs, D-140: excluded for
#: the SAME reason, one report later. They weight `infer_team_outlook`'s
#: composite vector, which is gated on BOTH `trade.outlook_composite` AND a
#: caller supplying an APPLIED `starter_signal` — and starter value can only
#: be summed off a league-wide power-rankings call, which no generation path
#: makes. trade_gen_v2, the mock draft and the outlook seed still pass four
#: positional arguments, so with the flag lit they score the LEGACY vector
#: (INV-372b, pinned by test_window_composite.py). Excluded rather than
#: pinned: a kill value would assert these reach a deck.)
#: 2026-08-21 added the 25 `breaker_*` knobs (counterparty breaker,
#: docs/plans/counterparty-breaker/LLD.md §4): excluded from MODEL_A_PROFILE
#: because they are EVALUATION-layer, not generation. `backend/trade_breaker.py`
#: is imported by no generator and no ranker; it runs after the deck-mutation
#: stack completes and mutates only a new card attribute, so no arm can observe
#: one. Dispositions in scope-phase2.md. `waiver_slot_cost`, which the breaker
#: reuses, is an existing engine knob and was already pinned below.)
#: 2026-08-22 added the six `negmem_*` knobs (negative-results memory,
#: docs/plans/negative-results-memory/LLD.md §3.4). `negmem_strength` is
#: INCLUDED in MODEL_A_PROFILE at 0.0 — negmem post-dates the reference SHA and
#: its seam multiplies `composite_score` inside generation, so 0.0 (the
#: documented byte-identical M1 disable) is what preserves the pre-wave engine;
#: the golden was re-run with the pin in place and did NOT need re-capturing.
#: 2026-08-22 added `fair_packages_cap` (#384 W6-B, POST /api/trades/fair-packages).
#: EXCLUDED from MODEL_A_PROFILE: it caps a SURFACE, not a generator. No arm
#: reaches `TradeService.generate_fair_packages` — the bake-off deck comes from
#: `generate_trades` / `trade_gen_v2` / `generate_pair_trades_v3`, none of which
#: calls it — so a kill value would falsely assert the knob reaches an arm-A deck.
#: Same rule as `asset_ideas_group_cap`, its sibling one line up.
#: 2026-08-22 added two full-sweep knobs (docs/plans/full-sweep/plan.md).
#: `exploration_base_per_opp` (§3.3) is EXCLUDED from MODEL_A_PROFILE, but NOT
#: for the "runs after generation" reason its `exploration_*` siblings get —
#: that reason is FALSE here and saying it would be worse than saying nothing.
#: Its first read sets `gen_kwargs["max_per_opponent"]`, which IS splatted into
#: every arm's generate call, so it does reach generators. It is excluded
#: because an arm pin is structurally UNREACHABLE: both reads happen on the job
#: thread in `server._run_trade_job`, OUTSIDE every arm's `_cfg_override`
#: context, so the value is a job-level constant shared identically by all
#: arms and no profile entry could ever change it. Its default 5.0 is the
#: pre-knob hardcoded `server._EXPLORATION_BASE_PER_OPP`, so arm A is unmoved.
#: `full_sweep_budget_s` (§3.5) is EXCLUDED too: it is a job-level wall-clock
#: safety rail, read ONLY inside `if FLAGS.trade_full_sweep` in the two
#: opponent loops, so with the flag dark it is never evaluated at all and it
#: shapes no gate, score or package. A kill value would assert arm A's deck
#: depends on how long the sweep ran, which is exactly what it must not.
#: The other five (`negmem_floor`, `negmem_min_evidence`, `negmem_halflife_days`,
#: `negmem_sat_k`, `negmem_like_net`) are EXCLUDED: at strength 0.0
#: `negmem.effective_mult` returns exactly 1.0 before any of them is consulted —
#: they shape the map, not the gate — so pinning a kill value would falsely
#: assert they reach an arm-A deck. Dispositions in scope-phase2.md. This is the
#: guard the plan's §8 risk row ("arm A drifts and stops being original")
#: actually needs: the golden only catches a new knob if that knob happens to
#: move THIS fixture, whereas this catches it the moment it is declared.
#: `age_pref_mult_u23` / `age_pref_mult_30plus` (2026-08-29, age-preference
#: consensus multiplier — docs/plans/age-pref-value/scope.md): generation
#: logic post-dating the reference SHA, so both are PINNED at the identity
#: value 1.0 in MODEL_A_PROFILE — `age_pref_value` short-circuits at exactly
#: 1.0, the consensus accessors are byte-identical, and the golden stands
#: un-recaptured. `age_pref_boost_cap` is EXCLUDED from the profile: it is
#: never read while both mults are 1.0 (the `package_floor_cross` rule).
#: Disposition in docs/plans/three-model-bakeoff/scope-phase2.md.
_PINNED_KNOBS = frozenset("""
age_pref_mult_u23 age_pref_mult_30plus age_pref_boost_cap
aggression_weight asset_floor_abs asset_ideas_group_cap
bakeoff_deck_limit bakeoff_serve_interleaved bakeoff_group_size
bakeoff_group_value_slots bakeoff_fill_policy bakeoff_include_baseline
bakeoff_include_challenger bakeoff_include_gen_v2 bakeoff_include_fit
bakeoff_lane_reallocate bakeoff_serve_fit
asset_ideas_lateral_band audition_like_rate_frac audition_min_views
audition_retire_days bench_credit_qb bench_credit_qb_sf bench_credit_rate
bench_credit_rb bench_credit_te bench_credit_te_tep bench_credit_wr
block_boost_weight boost_moderate boost_strong
breaker_board_div_min breaker_board_min_divergent
breaker_budget_checkpoint_frac breaker_crunch_scale
breaker_degraded_share_max breaker_floor_fit_duplicate
breaker_floor_fit_new_weakness breaker_floor_fit_outlook
breaker_floor_other_player_keep breaker_floor_roster_crunch
breaker_floor_value_giving breaker_floor_value_giving_consensus
breaker_max_repeat_frac breaker_min_severity breaker_ms_budget
breaker_narrate_fit_duplicate breaker_narrate_fit_new_weakness
breaker_narrate_fit_outlook breaker_narrate_other_player_keep
breaker_narrate_roster_crunch breaker_narrate_value_giving
breaker_outlook_haircut_legacy breaker_outlook_narrate_margin
breaker_shadow_run breaker_value_scale
consensus_both_ways
consensus_fairness_floor consensus_score_scale
consolidation_raw_loss_frac crown_elite_value crown_rate crown_rate_market
crown_share_floor cycle_edge_min_gain cycle_max_results cycle_min_net
deck_give_headliner_cap deck_headliner_cap deck_max_per_target
diversity_penalty diversity_user_cap
diversity_window_days elo_value_base elo_value_k elo_value_ref
exploration_base_per_opp exploration_min_deck exploration_overgen
exploration_rate
exploration_slot_position fairness_floor_divergence fairness_weight fatigue_a
fatigue_arch_a fatigue_b fatigue_decline_suppress_days
fatigue_decline_value_band fatigue_floor fatigue_lookback_days
fatigue_retest_mult fatigue_session_demotion fatigue_session_hours fatigue_w1
fatigue_w2 filler_min_frac first_session_deck_max first_session_deck_min
first_session_max_side_assets first_session_max_total_assets
first_session_min_fairness first_session_min_margin first_session_min_seed_elo
first_session_top_k fit_consensus_weight fit_divergence_weight
fit_expand_from fit_junk_floor fit_k_defying_mult fit_k_explained_mult
fit_max_packages_per_pair fit_min_aggregate fit_min_them fit_pool_cap
fit_pool_consensus fit_pool_div_opp fit_pool_div_seed fit_premium_max_loss
fit_r5_mode fit_score_even fit_score_scale fit_w_board fit_w_cons fit_w_div
full_sweep_budget_s
fair_packages_cap
fuzzy_match_tau
gen2_accept_global_prior gen2_accept_prior_strength gen2_band
gen2_centerpiece_top_k gen2_consol_floor gen2_consol_gamma gen2_dedup_jaccard
gen2_epsilon gen2_exposure_cap gen2_exposure_floor gen2_featured_count
gen2_give_pool gen2_meso_band gen2_meso_max_variants gen2_min_divergence
gen2_recv_extra_pool gen2_youth_age ghost_holdout_one_in infer_contender_cut
infer_composite_playoff_cap infer_composite_playoff_center
infer_composite_starter_cap infer_composite_w_pick infer_composite_w_playoff
infer_composite_w_starter infer_composite_w_vet infer_composite_w_youth
infer_net_firsts_cap infer_rebuilder_cut infer_w_net_firsts
infer_w_pick_share infer_w_vet_share infer_w_youth_share
jets_age ktc_fallback_rank ktc_k ktc_max lane_shift_frac
likes_you_gate_level likes_you_min_user_delta likes_you_min_user_gain
max_candidates max_overpay_frac max_overpay_min_value
max_value_ratio min_mismatch_score min_package_band min_side_surplus
min_side_surplus_marginal mismatch_confidence_damp mismatch_weight
mutual_gain_cap need_fit_weight need_gate_min_value need_gate_upgrade_margin
negmem_floor negmem_halflife_days negmem_like_net negmem_min_evidence
negmem_sat_k negmem_strength
neutral outlook_alpha_championship outlook_alpha_contender outlook_alpha_jets
outlook_alpha_not_sure outlook_alpha_rebuilder outlook_dir_age_gap_mult
outlook_dir_age_tolerance outlook_dir_boost outlook_dir_contend_weight
outlook_dir_penalty outlook_dir_rescue_frac package_adj_gamma
package_adj_gamma_market package_bench_trade_wide package_discount_cap
package_floor_cross package_floor_market
package_weight_1 package_weight_2 package_weight_3 package_weight_4
package_weight_5 pass_cooldown_days pass_cooldown_start_epoch penalty_heavy
penalty_mod penalty_soft pick_gap_frac pick_gap_min_value pick_pair_strip_frac
pick_year_decay_r1 pick_year_decay_r2 pick_year_decay_r3 pick_year_decay_r4
placement_tier_clamp
pos_acquire_bonus pos_conflict_penalty pos_multiplier_cap pos_net_cap
pos_tradeaway_bonus qb_tax_rate range_base rank_div_min_frac
relaxed_fairness_threshold relaxed_surplus_floor replenish_weekday
roster_clogger_penalty roster_clogger_threshold roster_spot_penalty
shrink_pseudocount skew_phaseout star_tax_elite_multiplier
star_tax_per_tier_gap suggestion_match_lookback_days
suggestion_match_min_overlap sweetener_band sweetener_gap_threshold
sweetener_max_cards
target_acquire_bonus taste_clamp_hi taste_clamp_lo taste_dwell_bonus
taste_dwell_ms taste_epsilon taste_eta_long taste_eta_short
taste_prior_ref_delta taste_prior_scale taste_prior_shrink taste_tau_long_days
taste_tau_short_days thompson_decay_gamma thompson_prior_base_rate
tier_mult_bench tier_mult_depth tier_mult_elite tier_mult_solid
tier_mult_starter trade_elo_gap_max user_elo_shrink user_gain_epsilon
v3_diversity_max_overlap
v3_pool_size vet_age waiver_baseline_value waiver_slot_cost youth_age
""".split()) | {
    # ── knockout refine, 2026-08-23 ────────────────────────────────────────
    # docs/plans/knockout-refine/plan.md §3. Four knobs, four dispositions.
    # A `.split()` blob cannot carry a per-key reason, so these are declared
    # here instead — the disposition is the point, not the membership.
    #
    # All four are read by `_c()` (C4 through the `trade_service` module
    # object, D-098) DURING generation, on the arm's own thread, INSIDE the
    # `_cfg_override` context `model_a()` opens. Unlike `exploration_base_per_opp`
    # they are therefore structurally arm-pinnable, so "excluded" below never
    # means "unreachable" — it means the read never happens under arm A.

    # C1. Read inside `need_gate_ok`, but only AFTER
    # `if _c("need_gate_min_value") <= 0: return True`. MODEL_A_PROFILE pins
    # `need_gate_min_value` at 0.0, so R5 returns True on its first line and
    # this knob is never consulted on an arm-A thread. EXCLUDED, by the
    # precedent already recorded for `need_gate_upgrade_margin`: "Companion
    # knobs are deliberately absent — their predicates return early at the
    # kill value above and never read them."
    "need_gate_dual_rescue",

    # C2. Read inside `overpay_ok`, after
    # `if _c("max_overpay_frac") <= 0: return True`. MODEL_A_PROFILE pins
    # `max_overpay_frac` at 0.0. EXCLUDED, same precedent, same sentence —
    # this is the exact companion relationship `max_overpay_min_value` has.
    "overpay_adjusted",

    # C3. Read inside `pos_net_ok`, after
    # `if _c("pos_net_cap") <= 0: return True`, AND behind a second guard
    # (`opp_ctx is None`) that no arm can satisfy without the member-loop
    # binding. MODEL_A_PROFILE pins `pos_net_cap` at 0.0. EXCLUDED, same
    # precedent.
    "pos_net_starter_relief",

    # C4. The ONLY one of the four with no sibling kill knob in front of it:
    # `trade_optimizer` reads it unconditionally in the v3 enumeration, on
    # every arm's thread, inside the overlay. It is NOT a post-reference-SHA
    # rule — `abs(len(give_ids) - len(recv_ids)) > 1` is present verbatim at
    # 92c31d5 (trade_optimizer.py:507) — so arm A's correct value is the
    # knob's identity value 1.0, not a kill value.
    #
    # DECISION: **pin at 1.0 in MODEL_A_PROFILE.** This is the one place the
    # D-095 exclusion rule ("their defaults ARE the pre-wave engine, so a pin
    # would change arm A rather than preserve it") must NOT be applied. That
    # rule is safe only while the LIVE row keeps sitting at the pre-wave
    # value, and here it demonstrably will not: the post-merge consolidation
    # bundle flips the prod `model_config` row to 2 (plan §1). `reload_config()`
    # writes that into `_cfg`, and `_cfg_override` shadows only keys the
    # profile names — so an unpinned arm A would silently start enumerating
    # 3-for-1 shapes the pre-wave engine could not build, with no test red.
    # Pinning the identity value costs nothing today (it equals the default,
    # so the golden stands un-recaptured) and is exactly the move
    # `package_bench_trade_wide` made for the same reason one wave earlier.
    #
    # The profile edit itself lives in backend/bakeoff_profiles.py, which is
    # The pin landed in bakeoff_profiles.py in the same tree (C4, D-159).
    "v3_shape_max_delta",

    # ── pick YoY floor, 2026-08-24 ─────────────────────────────────────────
    # docs/plans/pick-yoy-floor/plan.md §2 (D-161). One knob, one disposition,
    # written in the corrected style: WHERE the knob is read, relative to the
    # arm overlays.
    #
    # WHERE IT IS READ: `pick_values.market_r1_yoy_floor()` → `_c`, called
    # from `pick_values._r1_yoy_floored`, called from `priced_pool_value`
    # step 2. On the generation path the only route in is
    # `server._priced_pick_value` (server.py:10909) ← `_owned_pick_assets`
    # (server.py:10962, the `_priced[...]` loop at :11019) ←
    # `_inject_owned_picks` (server.py:11063).
    #
    # RELATIVE TO THE ARM OVERLAYS: `_inject_owned_picks` is called ONCE per
    # job, at server.py:5690, on the `_run_trade_job` thread — and
    # `_bakeoff.run_bakeoff` is not reached until server.py:5824. Every pick
    # is therefore priced, and this knob read, ~130 lines BEFORE the first
    # arm's `_cfg_override` is entered; the prices are then frozen into
    # `players_dict` / `seed_map` and the four arms all score the same
    # numbers. An arm pin is structurally UNREACHABLE, exactly as it is for
    # `exploration_base_per_opp` above — and for the same reason, which is
    # why that entry's wording is reused rather than a new one invented.
    #
    # ARM A DOES NOT PIN A PICK-PRICING MODE EITHER. `MODEL_A_PROFILE`
    # (bakeoff_profiles.py:68-116) names no pick key, and neither
    # `bakeoff_profiles.py` nor `bakeoff_runner.py` mentions
    # `pick_pricing_override` at all — so arm A prices picks on
    # `market_slots`, the process default resolved at server.py:11097-11099,
    # exactly like arms B/C/D. It does NOT ride `tier_ladder`, and the
    # tempting "arm A predates market_slots so pin the identity 0.0" is
    # therefore wrong twice over: the pin could not be honoured (see above),
    # and it would be describing a mode arm A does not run in.
    #
    # DECISION: **EXCLUDED from MODEL_A_PROFILE.** This is the same class as
    # its four `pick_year_decay_r*` siblings, whose recorded reason —
    # "they price an ASSET rather than decide which package to build from
    # priced assets" (docs/config-reference.md, D-079 § Not a generation
    # knob) — applies verbatim; the unreachability above is the second,
    # independent reason. The golden stands un-recaptured, and not merely
    # because it was re-run: the fixture's PICK assets are literal `_Pick`
    # objects carrying a hardcoded `pick_value = 60.0` (line 121). They are
    # not `draft_picks` rows, `_owned_pick_assets` is never called, and
    # `priced_pool_value` is never entered — so no season, no round, and
    # nothing for a market floor to clamp.
    "market_r1_yoy_floor",

    # ── consensus roster-fit sort key, 2026-09-02 ──────────────────────────
    # docs/plans/consensus-fit-sort-key/scope.md. One knob, one disposition.
    #
    # WHERE IT IS READ: `_generate_consensus_for_pair` → `_c` at CALL time,
    # on the arm's own thread, INSIDE the `_cfg_override` context `model_a()`
    # opens — so an arm pin is honoured, unlike `exploration_base_per_opp`.
    # It re-sorts the two candidate pools, and on this path the pool sort IS
    # the ranking (the emit loops take pool order), so it changes WHICH
    # consensus cards exist, not just their order — generation logic.
    #
    # DECISION: **PINNED at 0.0 in MODEL_A_PROFILE — the identity value.**
    # Its default is the pre-change engine, which is the D-095 shape ("a pin
    # would change arm A rather than preserve it") — but that rule is safe
    # only while the LIVE row keeps sitting at the pre-wave value, and this
    # knob ships expressly to be flipped live (the recommended value is in
    # docs/plans/consensus-fit-sort-key/results.md). Unpinned, arm A would
    # silently start emitting fit-sorted consensus decks the pre-wave engine
    # never built, with no golden drift. That is exactly the C4
    # `v3_shape_max_delta` situation one screen up, and it takes the same
    # remedy. At 0.0 the sort-key factory returns `seed_value` itself, so the
    # pin equals the default, the pools are byte-identical, and the golden
    # stands un-recaptured. The golden is NOT what proves the pin, though:
    # this fixture is fit-symmetric (QA showed it passes identically with the
    # pin removed and the live row at 0.5), so
    # `test_consensus_fit_pin_is_load_bearing` below asserts the pin on the
    # mirror fixture, which the knob does move — the same shape as
    # `test_pick_pair_strip_kill_value_is_load_bearing`.
    "consensus_fit_weight",
}


def test_consensus_fit_pin_is_load_bearing():
    """`consensus_fit_weight` is the one MODEL_A_PROFILE entry this file's
    deck fixture cannot exercise (fit-symmetric: every lineup mirrors the
    other side's, so the marginal-value asymmetry is 0 everywhere). Assert
    the pin on a fixture that DOES move — the consensus-fit mirror — with the
    live row at 0.5: arm A's output must equal its knob-0 output, and with
    the pin temporarily removed from the overlay it must NOT, so the pin is
    proven load-bearing rather than assumed."""
    from backend.tests.test_consensus_fit_sort_key import (
        _consensus, _mirror, _setup, KNOB)
    from backend.trade_service import _cfg_override, r4_bypass

    def run(live, overlay):
        _setup(live)                       # process-global row := live
        svc, seed, roster, opp = _mirror()
        with _cfg_override(overlay), r4_bypass():   # == model_a()'s shape
            cards = _consensus(svc, user_roster=roster, seed=seed, opp=opp,
                               fairness=0.75, w=live, profiles=False)
        return [(c.give_player_ids, c.receive_player_ids) for c in cards]

    pinned = dict(MODEL_A_PROFILE)
    unpinned = {k: v for k, v in MODEL_A_PROFILE.items() if k != KNOB}
    assert KNOB in pinned and pinned[KNOB] == 0.0
    # Arm A is unmoved by the live row...
    assert run(0.5, pinned) == run(0.0, pinned)
    # ...and only because of the pin: the same overlay minus this one key
    # follows the live row (non-vacuity — the fixture really moves).
    assert run(0.5, unpinned) != run(0.0, unpinned)
    assert run(0.0, unpinned) == run(0.0, pinned)


def test_no_generation_knob_was_added_without_an_arm_a_decision():
    added = sorted(set(ts._DEFAULT_CFG) - _PINNED_KNOBS)
    removed = sorted(_PINNED_KNOBS - set(ts._DEFAULT_CFG))
    assert not added and not removed, (
        f"trade_service._DEFAULT_CFG drifted: added={added} removed={removed}."
        "\nA new knob is a new way for arm A to stop being the pre-wave "
        "engine. Decide, in docs/plans/three-model-bakeoff/scope-phase2.md:"
        "\n  (D-095 precedent: the five landability-challenger knobs are "
        "EXCLUDED — their defaults ARE the pre-wave engine, so pinning a "
        "kill value would change arm A rather than preserve it.)"
        "\n  • generation logic that post-dates "
        f"{MODEL_A_REFERENCE_SHA} -> add its kill value to MODEL_A_PROFILE "
        "and re-capture the golden;"
        "\n  • anything else -> record why it is excluded."
        "\nThen add the key to _PINNED_KNOBS here.")


def test_model_a_profile_only_names_real_knobs():
    unknown = sorted(set(MODEL_A_PROFILE) - set(ts._DEFAULT_CFG))
    assert not unknown, (
        f"MODEL_A_PROFILE names knobs that no longer exist: {unknown}. "
        "A renamed or deleted knob makes arm A silently stop disabling "
        "whatever replaced it.")


if __name__ == "__main__":            # capture mode — see the module docstring
    _, rows = _deck()
    print('_GOLDEN_JSON = """\\')
    for row in rows:
        print(json.dumps(row, separators=(",", ":")) + ",")
    print('"""')
    print()
    print('_GOLDEN_IDEAS_JSON = """'
          + json.dumps(_ideas(), separators=(",", ":")) + '"""')
