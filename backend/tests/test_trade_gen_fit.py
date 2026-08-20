"""Bake-off arm `fit` — PR-F1 knockout-scope tests.

Spec: docs/plans/fit-challenger/LLD.md §1.6 (the K-chain) + §6.1 (the
knockout rows of the test plan); PRD.md §3 (knockouts, operator-CLOSED).

Scope note: PR-F1 ships the knockout chain only — the enumerator/scorer are
NotImplementedError stubs until PR-F2 — so every test here drives `_kill`
directly through a hand-built `_PairCtx`. Kill-count assertions therefore
read the chain's return code (the enumerator closure that increments
`report.killed[code]` on that code is PR-F2's); the full-pipeline versions
of the mode/sabotage tests are owed by the PR-F2/PR-F3 rows of LLD §6.1.

Fixture idiom (HANDOVER trap 7): every input is a literal — players, Elos,
rosters — so these tests isolate the knockout logic from board-computation
drift. Values below are `elo_to_value` at the live constants (base 1000,
ref 1500, k 0.005), quoted in comments where a gate margin matters.
"""

import pytest

import backend.trade_gen_fit as tgf
import backend.trade_optimizer as topt
import backend.trade_service as ts


# ───────────────────────────── fixture ─────────────────────────────────────

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


#: pid → (position, seed Elo). User side is a full startable roster with one
#: body of slack at QB/RB/WR/TE; the opponent sits EXACTLY at starter need
#: at RB (2 bodies) so taking one is a clean K3 kill.
_SPEC = {
    # user roster
    "uq":    ("QB", 1700.0), "uq2": ("QB", 1560.0),
    "ur1":   ("RB", 1600.0), "ur2": ("RB", 1500.0), "ur3": ("RB", 1430.0),
    "uw1":   ("WR", 1650.0),               # value 2117.0 — the elite headliner
    "uw2":   ("WR", 1550.0),               # value 1284.0
    "uw3":   ("WR", 1450.0),               # value 778.8
    "ut":    ("TE", 1400.0), "ut2": ("TE", 1350.0),
    "ujunk": ("RB", 1250.0),               # value 286.5 < asset_floor_abs (450)
    "upk1":  ("PICK", 1520.0),             # 2026 1st — value 1105.2
    "upk2":  ("PICK", 1450.0),             # 2027 late 2nd — value 778.8
    "upk3":  ("PICK", 1440.0),             # 2027 late 2nd — value 741.2
    "upk4":  ("PICK", 1390.0),             # K6 fixture pick — value 577.0
    # opponent roster
    "oq":    ("QB", 1680.0),
    "or1":   ("RB", 1580.0), "or2": ("RB", 1480.0),
    "ow1":   ("WR", 1660.0),               # value 2225.5
    "ow2":   ("WR", 1460.0),               # value 818.7
    "ow3":   ("WR", 1440.0),               # value 741.2
    "ot":    ("TE", 1420.0),
    "opk1":  ("PICK", 1515.0),             # 2027 1st — value 1077.9 (≈ upk1)
}

_PLAYERS = {pid: _Player(pid, pos) for pid, (pos, _e) in _SPEC.items()}
_SEED = {pid: elo for pid, (_p, elo) in _SPEC.items()}

_USER_ROSTER = ["uq", "uq2", "ur1", "ur2", "ur3", "uw1", "uw2", "uw3",
                "ut", "ut2", "upk1", "upk2", "upk3"]
_OPP_ROSTER = ["oq", "or1", "or2", "ow1", "ow2", "ow3", "ot", "opk1"]


def _cval(pid: str) -> float:
    return ts.elo_to_value(_SEED[pid])


def _ctx(user_roster=None, opp_roster=None, outlook=None, bypass=False):
    """Build the LLD §1.6 per-pair namespace from literal rosters. Both
    teams unboarded (uval/oval None) — the K-chain reads consensus only,
    except the junk accessors, which honestly degrade to cval."""
    user_roster = list(user_roster or _USER_ROSTER)
    opp_roster = list(opp_roster or _OPP_ROSTER)
    pos_vals: dict = {}
    for pid in user_roster:                # players only, QB/RB/WR/TE only —
        p = _PLAYERS[pid]                  # the ts.need_gate_ok shape
        if ts.is_pick_asset(p):
            continue
        if p.position in ("QB", "RB", "WR", "TE"):
            pos_vals.setdefault(p.position, []).append((pid, _cval(pid)))
    return tgf._PairCtx(
        players=_PLAYERS,
        cval=_cval,
        uval=None,
        oval=None,
        user_counts=topt._pos_counts(user_roster, _PLAYERS),
        opp_counts=topt._pos_counts(opp_roster, _PLAYERS),
        user_pos_values=pos_vals,
        user_profile=ts.analyze_roster_strengths(
            user_roster, _PLAYERS, "1qb_ppr"),
        outlook=outlook,
        scoring_format="1qb_ppr",
        bypass_need_gate=bypass,
        viewer_boarded=False,
        partner_boarded=False,
    )


@pytest.fixture(autouse=True)
def _pinned_defaults():
    """Every gate reads live knobs through ts._c — pin them to defaults so
    another module's leftover _cfg mutation cannot move a verdict."""
    saved = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    yield
    ts._cfg.clear()
    ts._cfg.update(saved)


# ───────────────────────────── K1 — shapes ─────────────────────────────────

def test_k1_shapes():
    # The operator-CLOSED list, pinned exactly (LLD §8 R-b): equal
    # multi-asset swaps (2-2, 3-3) are NOT legal shapes.
    assert tgf._LEGAL_SHAPES == frozenset(
        {(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (3, 2), (2, 3)})
    for shape in tgf._LEGAL_SHAPES:
        assert tgf._k1_shape_ok(*shape), shape
    for shape in ((4, 1), (1, 4), (4, 4), (3, 0), (0, 3), (0, 0),
                  (2, 2), (3, 3)):
        assert not tgf._k1_shape_ok(*shape), shape
    # Chain guard: a 2-2 swap dies at K1 before any predicate runs…
    assert tgf._kill(["ur2", "ut2"], ["or2", "ot"], _ctx()) == "K1"
    # …while the newly-legal 3-for-1 (gone from live v3's |n−m| ≤ 1)
    # survives the whole chain when startable and gate-clean.
    assert tgf._kill(["uw3", "ur3", "ut2"], ["ow1"], _ctx()) is None


# ───────────────────────────── K2 — live C3 ────────────────────────────────

def test_k2_byte_identical_to_live_c3():
    ctx = _ctx()
    packages = [
        (["upk1"], ["opk1"]),          # 2026 1st vs 2027 1st, near-equal price
        (["upk2", "upk3"], ["opk1"]),  # two late 2nds for a 1st
        (["uw2"], ["or1"]),            # pure player swap — no picks
        (["upk2"], ["ow3"]),           # pick-for-player 1-for-1
    ]
    # Byte-identical: fit's K2 verdict is the live predicate's, cval as
    # seed_value (the C3 strip active exactly as live).
    for g, r in packages:
        live_ok = ts.pick_swap_ok(g, r, _PLAYERS, _cval)
        assert (tgf._kill(g, r, ctx) == "K2") == (not live_ok), (g, r)
    # The cross-year matched pair (values 1105.2 vs 1077.9, ratio 0.975 ≥
    # pick_pair_strip_frac 0.85) strips both sides empty: churn, dead.
    assert tgf._kill(["upk1"], ["opk1"], ctx) == "K2"
    # Consolidation (two late 2nds for a 1st) sits outside the match band:
    # nothing strips, and the candidate survives the full chain.
    assert tgf._kill(["upk2", "upk3"], ["opk1"], ctx) is None


# ───────────────────────────── K3 — both rosters ───────────────────────────

def test_k3_both_rosters_all_paths():
    # Opponent path: taking or1 leaves the opponent 1 RB < need 2
    # (viewer is fine — gains an RB, gives a spare WR).
    assert tgf._kill(["uw2"], ["or1"], _ctx()) == "K3"
    # Mirror — viewer path: with the user's RB room trimmed to exactly
    # starter need, sending ur2 breaks the VIEWER's lineup instead.
    thin = [p for p in _USER_ROSTER if p != "ur3"]
    assert tgf._kill(["ur2"], ["ow2"], _ctx(user_roster=thin)) == "K3"
    # And a startable, gate-clean 3-for-1 passes K3 on both rosters.
    assert tgf._kill(["uw3", "ur3", "ut2"], ["ow1"], _ctx()) is None


def test_k3_runs_last_in_kill_order():
    # Candidate failing BOTH K4 (gap 1830.5 ≥ 500 and 86% ≥ 25%) and K3
    # (viewer WR room at exactly need 2, so giving uw1 leaves 1 < 2).
    thin = ["uq", "uq2", "ur1", "ur2", "ur3", "uw1", "uw2", "ut", "ut2"]
    ctx = _ctx(user_roster=thin)
    # First-failure attribution lands on K4 — K3 never saw the candidate.
    assert tgf._kill(["uw1"], ["ujunk"], ctx) == "K4"
    # Disarm R1 and the SAME candidate re-attributes to K3 — direct proof
    # K3 sits at the END of the chain rather than ahead of the cheap gates.
    with ts._cfg_override({"max_overpay_frac": 0.0}):
        assert tgf._kill(["uw1"], ["ujunk"], ctx) == "K3"


# ───────────────────────── K4 / K5 / K6 — wrapper parity ───────────────────

def test_k4_k5_k6_wrapper_parity():
    ctx = _ctx()
    # K4 — R1 overpay: elite WR (2117.0) for a depth WR (818.7); gap
    # 1298.3 ≥ 500 and 61% ≥ 25%. Fit's verdict is the live predicate's.
    g, r = ["uw1"], ["ow2"]
    assert ts.overpay_ok(g, r, _cval) is False
    assert tgf._kill(g, r, ctx) == "K4"
    # K5 — R2 position net: two RBs out, one WR back (net RB −2 > cap 1).
    # R1 passes first (gap 520.9 but 23.4% < 25%), so attribution is K5's.
    g, r = ["ur2", "ur3"], ["ow1"]
    assert ts.overpay_ok(g, r, _cval) is True
    assert ts.pos_net_ok(g, r, _PLAYERS) is False
    assert tgf._kill(g, r, ctx) == "K5"
    # K6 — R3 pick-is-the-gap: give 2117.0 + pick 577.0 vs 2225.5; gap
    # 468.4 (under R1's 500 floor), heavy side's pick sits inside the
    # [0.8·gap, gap/0.8] band — the pick IS the gap.
    g, r = ["uw1", "upk4"], ["ow1"]
    assert ts.pick_gap_ok(g, r, _cval, _PLAYERS) is False
    assert tgf._kill(g, r, ctx) == "K6"
    # And a candidate every wrapped gate passes end-to-end.
    assert tgf._kill(["uw3", "ur3", "ut2"], ["ow1"], ctx) is None


# ───────────────────────── K7 — fit_r5_mode knob ───────────────────────────

def test_fit_r5_mode_knob():
    ctx = _ctx(outlook="contender")
    # Lateral, non-upgrade, non-hole primary receive over the floor:
    # ow2 (818.7 ≥ need_gate_min_value 500) vs post-give WR incumbent
    # uw2 (1284.0) — a contender kill under live R5.
    g, r = ["uw3"], ["ow2"]
    # Wrapper parity: the live predicate itself refuses this lateral with
    # exactly the arguments the K-chain hands it.
    assert ts.need_gate_ok(
        g, r, seed_value=_cval, players=_PLAYERS,
        user_pos_values=ctx.user_pos_values, outlook="contender",
        position_needs=ctx.user_profile.get("position_needs"),
        position_surplus=ctx.user_profile.get("position_surplus"),
        scoring_format="1qb_ppr") is False
    # Mode 1 (default): killed, attributed K7.
    assert tgf._kill(g, r, ctx) == "K7"
    assert ctx.r5_fail is False
    # Mode 0: the predicate still RUNS; a failure tags instead of killing
    # (no score change in v1 — LLD §8 R-d). Thread-local override, the
    # same seam a live knob write reaches.
    with ts._cfg_override({"fit_r5_mode": 0.0}):
        assert tgf._kill(g, r, ctx) is None
        assert ctx.r5_fail is True
        # Control: an R5-exempt candidate (pick-primary receive) leaves
        # the tag unset — r5_fail marks real predicate failures only.
        assert tgf._kill(["uw2"], ["opk1"], ctx) is None
        assert ctx.r5_fail is False
    # Targeted-job parity: bypass_need_gate skips the predicate entirely.
    ctx_b = _ctx(outlook="contender", bypass=True)
    assert tgf._kill(g, r, ctx_b) is None
    assert ctx_b.r5_fail is False


# ───────────────────────── junk — fit_junk_floor knob ──────────────────────

def test_fit_junk_floor_knob():
    ctx = _ctx(user_roster=_USER_ROSTER + ["ujunk"])
    # 2-asset give side padded with a sub-asset_floor_abs body: ujunk
    # (286.5) under the filler bar max(2117.0 × 0.25, 450) = 529.3.
    g, r = ["uw1", "ujunk"], ["ow1"]
    # Default 0: the junk knockout is ABSENT in this arm (PRD §3 —
    # filler is a score problem, not a kill), so the candidate survives.
    assert tgf._kill(g, r, ctx) is None
    with ts._cfg_override({"fit_junk_floor": 1.0}):
        # Armed: the live filler_ok metric kills, attributed "junk".
        assert tgf._kill(g, r, ctx) == "junk"
        # Parity with the live predicate under the chain's own accessors
        # (unboarded fixture ⇒ both honestly degrade to consensus).
        assert ts.filler_ok(g, r, ctx.uval_or_cval, ctx.oval_or_cval) is False


# ───────────────────────── T1 — gate binding sabotage ──────────────────────

def test_fit_gate_binding_sabotage(monkeypatch):
    ctx = _ctx()
    g, r = ["uw3", "ur3", "ut2"], ["ow1"]
    # Baseline: a full-chain survivor.
    assert tgf._kill(g, r, ctx) is None
    # T1: rebind the MODULE attribute on trade_service — no reload. Had
    # trade_gen_fit imported the predicate by name (by value), this patch
    # would be a perfect no-op, the verdict below would stay None, and
    # this assert would fail the build. Monkeypatch auto-restores.
    monkeypatch.setattr(ts, "overpay_ok", lambda *a, **kw: False)
    assert tgf._kill(g, r, ctx) == "K4"


# ───────────────────────── diagnostics contract ────────────────────────────

def test_diagnostics_keys_complete():
    # Every LLD §1.2 key present on a fresh (zero-work) report — the
    # arms_json contract is "always present, zero/None-valued, never absent".
    rep = tgf.FitReport(league_id="L", user_id="u")
    d = rep.diagnostics()
    assert set(d) == {
        "opponents", "boarded_opponents", "enumerated", "scored", "killed",
        "r5_fail_scored", "capped_pairs", "post_filtered", "emitted",
        "one_sided_pct", "both_high_pct", "mixed_pct", "you_tilt_pct",
        "median_aggregate", "top_q_pick_share", "top_q_junk_share", "ms",
    }
    assert set(d["killed"]) == {"K0", "K1", "K2", "K3", "K4", "K5", "K6",
                                "K7", "junk"}
    assert all(v == 0 for v in d["killed"].values())
    assert set(d["post_filtered"]) == {
        "untouchable", "not_interested", "position_prefs", "r4_swiped",
        "c4_centerpiece", "min_them", "min_aggregate"}
    # The flat dict is a COPY — arms_json consumers cannot mutate the report.
    d["killed"]["K1"] = 99
    assert rep.killed["K1"] == 0
    assert tgf.SCORER_VERSION == "fit-1"
