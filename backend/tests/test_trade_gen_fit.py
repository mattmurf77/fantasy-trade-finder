"""Bake-off arm `fit` — PR-F1 knockout-scope tests.

Spec: docs/plans/fit-challenger/LLD.md §1.6 (the K-chain) + §6.1 (the
knockout rows of the test plan); PRD.md §3 (knockouts, operator-CLOSED).

Scope note: the PR-F1 half (top of file) drives `_kill` directly through a
hand-built `_PairCtx` and reads the chain's return code; the PR-F2 half
(below the "full pipeline" banner) covers the enumerator, the dual scorer,
card construction, the M3 `fit_diag` stamp, and the full-pipeline versions
of the r5-mode and binding-sabotage tests PR-F1's scope note owed. The
§1.9 post-score filter rows (untouchable/prefs/C4) are PR-F3's.

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
    # 2026-08-23 — this test states its packages in RAW consensus sums
    # (the numbers in the comments below), so it is pinned to R1's raw
    # body. Knockout-refine C2 lit `overpay_adjusted` by default, which
    # prices both sides with package_value_v2: the 3-for-1 fixture goes
    # 12.1% -> 35.9% and R1 takes it, changing K-chain ATTRIBUTION
    # rather than anything this test is about. C2's own verdicts live in
    # test_knockout_refine.py (docs/plans/knockout-refine/plan.md §3).
    ts._cfg["overpay_adjusted"] = 0.0
    # PRD §12.6 (operator, 2026-08-20): every 1–3 × 1–3 shape is legal —
    # the original list's 2-2/3-3 omission was unintended (LLD §8 R-b flag).
    assert tgf._LEGAL_SHAPES == frozenset(
        {(1, 1), (2, 1), (1, 2), (2, 2), (3, 1), (1, 3), (3, 2), (2, 3),
         (3, 3)})
    for shape in tgf._LEGAL_SHAPES:
        assert tgf._k1_shape_ok(*shape), shape
    for shape in ((4, 1), (1, 4), (4, 4), (3, 0), (0, 3), (0, 0)):
        assert not tgf._k1_shape_ok(*shape), shape
    # Chain guard: an oversized side dies at K1 before any predicate runs…
    assert tgf._kill(["uw3", "ur3", "ut2", "uw2"], ["ow1"], _ctx()) == "K1"
    # …a 2-2 (newly legal per §12.6) gets PAST K1 into the real chain…
    assert tgf._kill(["ur2", "ut2"], ["or2", "ot"], _ctx()) != "K1"
    # …and the 3-for-1 (gone from live v3's |n−m| ≤ 1) survives the whole
    # chain when startable and gate-clean.
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
    # 2026-08-23 — this test states its packages in RAW consensus sums
    # (the numbers in the comments below), so it is pinned to R1's raw
    # body. Knockout-refine C2 lit `overpay_adjusted` by default, which
    # prices both sides with package_value_v2: the 3-for-1 fixture goes
    # 12.1% -> 35.9% and R1 takes it, changing K-chain ATTRIBUTION
    # rather than anything this test is about. C2's own verdicts live in
    # test_knockout_refine.py (docs/plans/knockout-refine/plan.md §3).
    ts._cfg["overpay_adjusted"] = 0.0
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
    # 2026-08-23 — this test states its packages in RAW consensus sums
    # (the numbers in the comments below), so it is pinned to R1's raw
    # body. Knockout-refine C2 lit `overpay_adjusted` by default, which
    # prices both sides with package_value_v2: the 3-for-1 fixture goes
    # 12.1% -> 35.9% and R1 takes it, changing K-chain ATTRIBUTION
    # rather than anything this test is about. C2's own verdicts live in
    # test_knockout_refine.py (docs/plans/knockout-refine/plan.md §3).
    ts._cfg["overpay_adjusted"] = 0.0
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
    # 2026-08-23 — this test states its packages in RAW consensus sums
    # (the numbers in the comments below), so it is pinned to R1's raw
    # body. Knockout-refine C2 lit `overpay_adjusted` by default, which
    # prices both sides with package_value_v2: the 3-for-1 fixture goes
    # 12.1% -> 35.9% and R1 takes it, changing K-chain ATTRIBUTION
    # rather than anything this test is about. C2's own verdicts live in
    # test_knockout_refine.py (docs/plans/knockout-refine/plan.md §3).
    ts._cfg["overpay_adjusted"] = 0.0
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


# ═══════════════════════════ PR-F2 — full pipeline ═════════════════════════
# Enumerator + dual scorer + M3 stamp (LLD §1.3–§1.8, §1.10–§1.11; §6.1
# scorer rows + the full-pipeline r5-mode / binding-sabotage tests owed by
# the PR-F1 scope note above). Same literal-fixture idiom.

import backend.bakeoff_runner as bo
from unittest.mock import patch


#: Raw viewer board for the boarded tests — diverges HARD from seed on or1
#: (1620 vs seed 1580 → value 1822.1 vs 1491.8); everything else falls back
#: to Elo 1500 through the accessor.
_USER_BOARD = {"or1": 1620.0}

#: Raw opponent board that MIRRORS seed on the two assets it rates — so the
#: partner's board lens agrees with consensus and a viewer-favored candidate
#: keeps them < 50 on every lens.
_OPP_BOARD = {"ur2": 1500.0, "or1": 1580.0}


def _league(opp_board=None, opp_roster=None):
    """Two-member league over the literal fixture. The opponent is boarded
    iff `opp_board` is a non-empty dict (the trade_gen_v2.py:925 test)."""
    return ts.League(
        league_id="Lfit", name="Fit League", platform="demo",
        members=[
            ts.LeagueMember(user_id="user", username="You",
                            roster=list(_USER_ROSTER), elo_ratings={},
                            has_rankings=False),
            ts.LeagueMember(user_id="opp", username="Opp",
                            roster=list(opp_roster or _OPP_ROSTER),
                            elo_ratings=dict(opp_board or {}),
                            has_rankings=bool(opp_board)),
        ])


def _gen(user_elo=None, league=None, **kw):
    kwargs = dict(players=_PLAYERS, league=league or _league(),
                  user_id="user", user_elo=dict(user_elo or {}),
                  user_roster=list(_USER_ROSTER), seed_elo=dict(_SEED),
                  scoring_format="1qb_ppr")
    kwargs.update(kw)
    return tgf.generate_league_suggestions(**kwargs)


def _find(cards, give, recv):
    hits = [c for c in cards if c.give_player_ids == give
            and c.receive_player_ids == recv]
    return hits[0] if hits else None


# ───────────── the volume unlock — negative surplus scores, not killed ─────

def test_negative_surplus_scores_not_killed():
    # Boarded pair. give ur2 (1000.0) for or1 (1491.8): the viewer receives
    # MORE consensus value, so live arm B kills it on rv ≥ gv / dual
    # surplus. Fit keeps it and prices the partner's side honestly (<50).
    # C4 off: with the §12.6 shapes (2-2/3-3) enumerated, headliner
    # crowding would drop this exact 1x1 from the FINAL list — the
    # mechanism under test is the kill chain, not deck composition.
    with ts._cfg_override({"deck_headliner_cap": 0.0}):
        cards, report = _gen(user_elo=_USER_BOARD,
                             league=_league(opp_board=_OPP_BOARD))
    assert report.boarded_opponents == 1
    card = _find(cards, ["ur2"], ["or1"])
    assert card is not None, "viewer-favored candidate must survive the chain"
    assert card.receive_value > card.give_value          # the arm-B kill shape
    fit = card.fit
    assert fit["boards"] == "both" and card.basis == "divergence"
    assert fit["them"] is not None and fit["them"] < 50
    # Consensus lens: them pays 491.8 → 50 − 50·tanh(491.8/400) ≈ 7.9.
    assert fit["lenses"]["them"]["consensus"] < 50
    # And the generator-level diagnostics populated (pre-F4 set, R-j).
    assert report.median_aggregate is not None
    assert report.one_sided_pct is not None


# ───────────── unranked partner — them side is L3 only ─────────────────────

def test_unranked_partner_l3_only():
    cards, _report = _gen(user_elo=_USER_BOARD)      # opp has no board
    assert cards
    for card in cards:
        lens_them = card.fit["lenses"]["them"]
        assert lens_them["board"] is None
        assert lens_them["vs_consensus"] is None
        assert lens_them["consensus"] is not None
        # them-score IS the consensus lens (1.0 · L3 combine).
        assert card.fit["them"] == lens_them["consensus"]
        assert card.fit["boards"] == "viewer"
        assert card.basis == "consensus"


# ───────────── unranked PAIR — the C7c aggregate-100 plateau ───────────────

def test_unranked_pair_aggregate_mirror():
    cards, _report = _gen(user_elo={})               # neither side boarded
    assert cards
    # §12.6: the plateau is EQUAL-COUNT shapes (1-1, 2-2, 3-3) — the
    # waiver-slot cost is symmetric when both sides move the same number of
    # bodies, so both teams see the same mirrored consensus surplus.
    equal = [c for c in cards
             if len(c.give_player_ids) == len(c.receive_player_ids)]
    assert len(equal) >= 2
    assert any(len(c.give_player_ids) == 1 for c in equal)
    for c in cards:
        assert c.fit["boards"] == "none"
        assert c.basis == "consensus"
    # Balanced shapes mirror exactly: both sides are the same consensus
    # surplus with opposite sign, so aggregate == 100 (composite_score is
    # round(aggregate, 4)).
    for c in equal:
        assert abs(c.composite_score - 100.0) < 1e-6
    # Unbalanced shapes pay the waiver-slot cost on the receiving-more side
    # → strictly below the plateau, so the plateau is the deck's prefix.
    for c in cards[len(equal):]:
        assert c.composite_score < 100.0
    assert cards[:len(equal)] == equal
    # Within the plateau the consensus-fairness ratio decides order (C7c)…
    fairs = [c.fairness_score for c in equal]
    assert fairs == sorted(fairs, reverse=True)
    # …and equal-fairness ties fall to the deterministic tie-break.
    for a, b in zip(equal, equal[1:]):
        if a.fairness_score == b.fairness_score:
            ka = (a.target_user_id, tuple(sorted(a.give_player_ids)),
                  tuple(sorted(a.receive_player_ids)))
            kb = (b.target_user_id, tuple(sorted(b.give_player_ids)),
                  tuple(sorted(b.receive_player_ids)))
            assert ka < kb


# ───────────── scorer curve — computed values, never hand-rounded ──────────

def test_fit_score_curve_pinned():
    # LLD §1.7 computed table (HLD F-5: NOT PLAN-v2's rounded 88.4/11.6).
    expected = {
        0.0:     50.0,
        200.0:   73.105857863,
        -200.0:  26.894142137,
        400.0:   88.079707797,
        -400.0:  11.920292202,
        800.0:   98.201379003,
        -800.0:  1.798620996,
        1200.0:  99.752737684,
        -1200.0: 0.247262315,
    }
    for s, exp in expected.items():
        assert abs(tgf._score(s) - exp) < 1e-6, s
    # Clamp at the rails.
    assert tgf._score(1e6) == 100.0
    assert tgf._score(-1e6) == 0.0
    # fit_score_even moves the midpoint; fit_score_scale rescales the curve.
    with ts._cfg_override({"fit_score_even": 60.0}):
        assert abs(tgf._score(0.0) - 60.0) < 1e-9
    with ts._cfg_override({"fit_score_scale": 200.0}):
        assert abs(tgf._score(200.0) - 88.079707797) < 1e-6


# ───────────── T3 — lens provenance is the RAW board ───────────────────────

def test_fit_lens_provenance_raw(monkeypatch):
    # Fixture where raw and shrunk diverge: the viewer's board rates or1 at
    # 1620 (value 1822.1) vs seed 1580 (1491.8). A confidence-0 shrink
    # would collapse the board onto seed — so raw ≠ shrunk observably.
    def _boom(*_a, **_kw):
        raise AssertionError("fit must never call _shrink_user_elo (T3)")
    monkeypatch.setattr(ts, "_shrink_user_elo", _boom)

    # PR-F3 activated the §1.9 post-filters; the C4 centerpiece cap is
    # orthogonal to lens provenance and would drop this test's hand-computed
    # package (or1 headlines many higher-aggregate cards), so it is disarmed
    # for the generation call only. The sentinel stays armed throughout.
    with ts._cfg_override({"deck_headliner_cap": 0.0}):
        cards, _report = _gen(user_elo=_USER_BOARD)  # sentinel armed
    card = _find(cards, ["ur2"], ["or1"])
    assert card is not None

    # Hand-computed L1 from the RAW board accessor (Elo-1500 fallback).
    def raw_uval(pid):
        return ts.elo_to_value(_USER_BOARD.get(pid, 1500.0))
    exp_l1 = round(tgf._score(tgf._surplus(["or1"], ["ur2"], raw_uval)), 1)
    assert card.fit["lenses"]["you"]["board"] == exp_l1
    # And it is NOT the shrunk-to-seed (= consensus) score — the lens read
    # the board, not the shrinkage output.
    assert exp_l1 != card.fit["lenses"]["you"]["consensus"]


# ───────────── pool discipline ─────────────────────────────────────────────

def _pool_world():
    """30-asset rosters with startable cores; boards built so the three
    sub-pools are DISJOINT and the union (24 ids) exceeds fit_pool_cap."""
    players, seed = {}, {}
    user_roster, opp_roster = [], []
    core = [("qA", "QB"), ("qB", "QB"), ("rA", "RB"), ("rB", "RB"),
            ("rC", "RB"), ("tA", "TE"), ("tB", "TE")]
    for side, roster in (("u", user_roster), ("o", opp_roster)):
        for stem, pos in core:
            pid = side + stem
            players[pid] = _Player(pid, pos)
            seed[pid] = 1500.0
            roster.append(pid)
        for i in range(23):
            pid = f"{side}w{i:02d}"
            players[pid] = _Player(pid, "WR")
            seed[pid] = 1500.0 + 2.0 * i
            roster.append(pid)
    # Viewer board: big |board − seed| on uw05..uw12; opp's view of the
    # user's assets diverges on uw13..uw20 (→ |board − opp_board| there).
    uboard = {f"uw{i:02d}": seed[f"uw{i:02d}"] + 150.0 for i in range(5, 13)}
    oboard = {f"uw{i:02d}": seed[f"uw{i:02d}"] - 150.0 for i in range(13, 21)}
    oboard.update({f"ow{i:02d}": seed[f"ow{i:02d}"] + 150.0
                   for i in range(5, 13)})
    return players, seed, user_roster, opp_roster, uboard, oboard


def test_pool_cap_respected():
    players, seed, user_roster, opp_roster, uboard, oboard = _pool_world()

    def cv(pid):
        return ts.elo_to_value(seed[pid])

    def bv(pid):
        return ts.elo_to_value(uboard.get(pid, 1500.0))

    def ov(pid):
        return ts.elo_to_value(oboard.get(pid, 1500.0))

    # Direct pool check: union = 8 consensus ∪ 8 div-seed ∪ 8 div-opp
    # (disjoint by construction) = 24 unique ids → hard-capped to 15.
    pool = tgf._build_pool(roster=user_roster, players=players, cval=cv,
                           board_val=bv, opp_board_val=ov)
    assert len(pool) == 15
    assert len(set(pool)) == 15 and set(pool) <= set(user_roster)
    # Unboarded: only the consensus sub-pool exists (no picks here).
    pool_dark = tgf._build_pool(roster=user_roster, players=players, cval=cv)
    assert len(pool_dark) == 8

    # Full pipeline under a tight budget: the pair hard-stops at 500.
    league = ts.League(
        league_id="Lpool", name="Pool", platform="demo",
        members=[
            ts.LeagueMember(user_id="user", username="You",
                            roster=user_roster, elo_ratings={},
                            has_rankings=False),
            ts.LeagueMember(user_id="opp", username="Opp",
                            roster=opp_roster, elo_ratings=dict(oboard),
                            has_rankings=True),
        ])
    with ts._cfg_override({"fit_max_packages_per_pair": 500.0}):
        _cards, report = tgf.generate_league_suggestions(
            players=players, league=league, user_id="user",
            user_elo=dict(uboard), user_roster=user_roster,
            seed_elo=dict(seed), scoring_format="1qb_ppr")
    assert report.enumerated == 500          # hard stop AT the budget
    assert report.capped_pairs == 1
    assert report.scored > 0                 # phase 1 survivors existed


# ───────────── K7 knob — full-pipeline version (owed by PR-F1) ─────────────

def test_fit_r5_mode_full_pipeline():
    # give ur2 (RB 1000.0) for ow2 (WR 818.7) under a contender window:
    # lateral, non-upgrade (WR incumbent uw2 1284.0), non-hole primary
    # receive over the floor — the live R5 kill, reached through the whole
    # pipeline this time (PR-F1 proved it at the _kill level only).
    # C4 off in BOTH runs (crowding isolation, §12.6 shapes); the knob
    # under test is fit_r5_mode alone.
    with ts._cfg_override({"deck_headliner_cap": 0.0}):
        cards1, rep1 = _gen(outlook="contender")
    assert rep1.killed["K7"] >= 1
    assert _find(cards1, ["ur2"], ["ow2"]) is None
    with ts._cfg_override({"fit_r5_mode": 0.0, "deck_headliner_cap": 0.0}):
        cards0, rep0 = _gen(outlook="contender")
    assert rep0.killed["K7"] == 0
    assert rep0.r5_fail_scored >= 1
    assert len(cards0) > len(cards1)                 # the unlock is real
    tagged = _find(cards0, ["ur2"], ["ow2"])
    assert tagged is not None and tagged.fit["r5_fail"] is True
    # No score change in v1 (LLD §8 R-d): every candidate present in both
    # runs carries an identical fit payload.
    def key(c):
        return (tuple(c.give_player_ids), tuple(c.receive_player_ids))
    f1 = {key(c): c.fit for c in cards1}
    f0 = {key(c): c.fit for c in cards0}
    common = set(f1) & set(f0)
    assert common
    for k in common:
        assert f1[k] == f0[k]


# ───────────── T1 — binding sabotage, full-pipeline version ────────────────

def test_fit_gate_binding_sabotage_full_pipeline(monkeypatch):
    cards, rep = _gen()
    assert cards and rep.scored > 0
    # Rebind the MODULE attribute — had fit bound the predicate by value at
    # import, this would be a perfect no-op and the asserts below would
    # fail the build. Monkeypatch auto-restores.
    monkeypatch.setattr(ts, "overpay_ok", lambda *a, **kw: False)
    cards2, rep2 = _gen()
    assert cards2 == []
    assert rep2.scored == 0 and rep2.emitted == 0
    # Every K1/K2 survivor died at K4 — nothing leaked past the rebind.
    assert rep2.killed["K4"] == (rep2.enumerated - rep2.killed["K1"]
                                 - rep2.killed["K2"])
    assert rep2.killed["K4"] > 0


# ───────────── §1.10 — card field construction ─────────────────────────────

def test_mismatch_and_fairness_fields():
    # C4 off — same isolation as test_negative_surplus_scores_not_killed.
    with ts._cfg_override({"deck_headliner_cap": 0.0}):
        cards, _report = _gen(user_elo=_USER_BOARD,
                              league=_league(opp_board=_OPP_BOARD))
    card = _find(cards, ["ur2"], ["or1"])
    assert card is not None
    fit = card.fit
    # mismatch = harmonic mean of the two 0–100 team scores (F-4 ruling).
    assert card.mismatch_score == round(
        ts._harmonic_mean(fit["you"], fit["them"]), 1)
    # fairness = the live consensus ratio from _consensus_packages.
    gv, rv = topt._consensus_packages(["ur2"], ["or1"], _cval)
    assert card.fairness_score == min(gv, rv) / max(gv, rv)
    assert card.give_value == round(gv, 1)
    assert card.receive_value == round(rv, 1)
    # composite = round(aggregate, 4), 0–200 (payload values are 1-dp).
    assert abs(card.composite_score - (fit["you"] + fit["them"])) <= 0.11
    assert card.basis == "divergence"                    # both boarded
    assert fit["ver"] == tgf.SCORER_VERSION
    # need_fit is STAMPED for telemetry (never multiplied): the helper's
    # own output for this package, verbatim.
    exp_nf = ts.need_fit_score(
        ts.analyze_roster_strengths(_USER_ROSTER, _PLAYERS, "1qb_ppr"),
        ts.analyze_roster_strengths(_OPP_ROSTER, _PLAYERS, "1qb_ppr"),
        ["ur2"], ["or1"], _PLAYERS, "1qb_ppr")
    assert card.need_fit == exp_nf


# ───────────── M3 — fit_diag stamp is inert ────────────────────────────────

class _StubCard:
    """Minimal bake-off card for runner-level fixtures (the FakeCard
    idiom from test_bakeoff_runner.py)."""
    def __init__(self, give, recv, target="opp"):
        self.give_player_ids = list(give)
        self.receive_player_ids = list(recv)
        self.target_user_id = target


def _stub_run():
    """Deterministic run_bakeoff over stub arms (challenger-test idiom)."""
    def generate(**_ov):
        return [_StubCard([f"bg{i}"], [f"br{i}"]) for i in range(3)]

    def gen_v2(**_ov):
        return [_StubCard([f"cg{i}"], [f"cr{i}"]) for i in range(2)]

    knobs = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0,
             "bakeoff_include_baseline": 1.0}
    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: list(parts)), \
            patch.object(bo, "_cfg",
                         lambda key, default: float(knobs.get(key, default))):
        return bo.run_bakeoff(generate=generate, gen_v2=gen_v2,
                              league_id="Lstamp", interleave=True,
                              limit=None, roster=bo.ARMS)


def test_fit_diag_inert():
    league = ts.League(
        league_id="Lstamp", name="Stamp", platform="demo",
        members=[ts.LeagueMember(user_id="opp", username="Opp",
                                 roster=["x1"], elo_ratings={},
                                 has_rankings=False)])
    run = _stub_run()
    baseline_deck = [(tuple(c.give_player_ids), tuple(c.receive_player_ids))
                     for c in run.served_deck()]
    all_cards = [c for arm in run.arms.values() for c in arm.cards]
    assert all_cards
    before = [dict(vars(c)) for c in all_cards]

    tgf.stamp_fit_diag({a: r.cards for a, r in run.arms.items()},
                       players={}, league=league, user_elo={}, seed_elo={})

    for card in all_cards:
        diag = card.fit_diag
        assert set(diag) == {"you", "them", "bucket", "ver", "lenses"}
        assert diag["ver"] == tgf.SCORER_VERSION
        # Blank world: every asset prices at Elo-1500 fallback → even trade.
        assert diag["you"] == 50.0 and diag["them"] == 50.0
        assert diag["bucket"] == "both_ok"
        assert diag["lenses"]["you"]["board"] is None    # unboarded viewer
    # Attribute-only: nothing else on any card changed.
    for card, snap in zip(all_cards, before):
        after = dict(vars(card))
        after.pop("fit_diag")
        assert after == snap
    # THE contract: delete the stamp from every card → served outcome
    # byte-identical (the stamp fed nothing the serving path reads).
    for card in all_cards:
        delattr(card, "fit_diag")
    assert [(tuple(c.give_player_ids), tuple(c.receive_player_ids))
            for c in run.served_deck()] == baseline_deck
    # And a fresh unstamped run drafts the same deck.
    run2 = _stub_run()
    assert [(tuple(c.give_player_ids), tuple(c.receive_player_ids))
            for c in run2.served_deck()] == baseline_deck


def test_fit_diag_unscorable_cards_get_none():
    league = ts.League(
        league_id="Lstamp", name="Stamp", platform="demo",
        members=[ts.LeagueMember(user_id="opp", username="Opp",
                                 roster=["x1"], elo_ratings={},
                                 has_rankings=False)])
    ghost = _StubCard(["g"], ["r"], target="nobody")     # unknown partner
    empty = _StubCard([], ["r"])                         # empty give side
    ok = _StubCard(["g"], ["r"])
    tgf.stamp_fit_diag({"current": [ghost, empty, ok]},
                       players={}, league=league, user_elo={}, seed_elo={})
    assert ghost.fit_diag is None
    assert empty.fit_diag is None
    assert isinstance(ok.fit_diag, dict)
    # Fit's own cards reuse the fit payload verbatim (identical numbers).
    own = _StubCard(["g"], ["r"])
    own.fit = {"you": 61.0, "them": 55.5, "aggregate": 116.5,
               "bucket": "both_ok", "boards": "both",
               "ver": tgf.SCORER_VERSION, "r5_fail": False,
               "lenses": {"you": {"board": 61.0, "vs_consensus": None,
                                  "consensus": 61.0},
                          "them": {"board": None, "vs_consensus": None,
                                   "consensus": 55.5}}}
    tgf.stamp_fit_diag({"fit": [own]}, players={}, league=league,
                       user_elo={}, seed_elo={})
    assert own.fit_diag == {"you": 61.0, "them": 55.5, "bucket": "both_ok",
                            "ver": tgf.SCORER_VERSION,
                            "lenses": own.fit["lenses"]}


# ═══════════════════════════ PR-F3 — §1.9 post-score filters ═══════════════
# Filters run per-viewer AFTER scoring — a preference hides a card, it never
# shrinks the search (LLD §1.9; PRD §6.4 rules R4 post-score too). Same
# literal fixture; every test compares against an unfiltered control run.

import sys


def test_untouchable_enumerated_then_filtered():
    # Untouchable = the viewer's best asset (uw1, seed 1650).
    control, rep_c = _gen()
    filtered, rep_f = _gen(untouchable_ids={"uw1"})
    # The preference never shrank the search: the K-chain saw the identical
    # candidate stream, untouchable or not.
    assert rep_f.enumerated == rep_c.enumerated
    assert rep_f.scored == rep_c.scored
    # uw1 entered ≥1 scored candidate (it is in the control output)…
    assert any("uw1" in c.give_player_ids for c in control)
    # …and the F4 filter hid every one of them from the viewer.
    assert rep_f.post_filtered["untouchable"] >= 1
    assert all("uw1" not in c.give_player_ids for c in filtered)


def test_prefs_filter_not_kill():
    # Not-interested = the partner's best asset (ow1, seed 1660) — the
    # receive-side mirror of the untouchable test.
    control, rep_c = _gen()
    filtered, rep_f = _gen(not_interested_ids={"ow1"})
    assert rep_f.enumerated == rep_c.enumerated
    assert rep_f.scored == rep_c.scored
    assert any("ow1" in c.receive_player_ids for c in control)
    assert rep_f.post_filtered["not_interested"] >= 1
    assert all("ow1" not in c.receive_player_ids for c in filtered)


def test_position_pins_filter():
    control, rep_c = _gen()
    # Acquire pin: every surviving card's receive side carries ≥1 non-pick
    # player at a pinned position; pick-only receive sides do not satisfy it.
    cards_a, rep_a = _gen(acquire_positions=["RB"])
    assert rep_a.enumerated == rep_c.enumerated          # filter, not kill
    assert rep_a.post_filtered["position_prefs"] >= 1
    for c in cards_a:
        assert any(_PLAYERS[p].position == "RB"
                   and not ts.is_pick_asset(_PLAYERS[p])
                   for p in c.receive_player_ids)
    # Trade-away pin: the give-side mirror.
    cards_t, rep_t = _gen(trade_away_positions=["WR"])
    assert rep_t.post_filtered["position_prefs"] >= 1
    for c in cards_t:
        assert any(_PLAYERS[p].position == "WR"
                   and not ts.is_pick_asset(_PLAYERS[p])
                   for p in c.give_player_ids)


def test_r4_swiped_post_filtered():
    # Take a real surviving package, then replay the job with its key in
    # past_decision_keys (the G6 R4 / already-swiped shape:
    # (frozenset(give), frozenset(recv))).
    control, rep_c = _gen()
    assert control
    victim = control[0]
    key = (frozenset(victim.give_player_ids),
           frozenset(victim.receive_player_ids))
    filtered, rep_f = _gen(past_decision_keys={key})
    # Post-score by operator ruling (PRD §6.4): fit's `enumerated` includes
    # the swiped candidate — unlike gen_v2, which skips it while enumerating.
    assert rep_f.enumerated == rep_c.enumerated
    assert rep_f.post_filtered["r4_swiped"] >= 1
    assert all((frozenset(c.give_player_ids),
                frozenset(c.receive_player_ids)) != key for c in filtered)


def test_min_them_and_min_aggregate_floors():
    # C4 off throughout: the §12.6 equal swaps otherwise crowd the
    # one-sided tail out of the capped list; the knobs under test are the
    # two floors alone.
    _off = {"deck_headliner_cap": 0.0}
    # Defaults 0 = off: the one-sided volume the arm exists to keep.
    with ts._cfg_override(_off):
        control, rep_c = _gen()
    assert rep_c.post_filtered["min_them"] == 0
    assert rep_c.post_filtered["min_aggregate"] == 0
    assert any(c.fit["them"] < 40.0 for c in control)    # one-sided supply
    # Floors on (presentment knobs, applied FIRST so later counters
    # describe the visible universe — LLD §8 R-i).
    with ts._cfg_override({"fit_min_them": 40.0, **_off}):
        cards_t, rep_t = _gen()
    assert rep_t.post_filtered["min_them"] >= 1
    assert all(c.fit["them"] >= 40.0 for c in cards_t)
    with ts._cfg_override({"fit_min_aggregate": 100.0, **_off}):
        cards_a, rep_a = _gen()
    assert rep_a.post_filtered["min_aggregate"] >= 1
    assert all(c.fit["aggregate"] >= 100.0 for c in cards_a)


def test_c4_centerpiece_cap_replicates_live():
    # Default deck_headliner_cap = 2: at most two surviving cards share a
    # centerpiece (ts.deck_centerpiece — max seed over BOTH sides, id
    # tie-break), keep-first in rank order.
    cards, rep = _gen()
    assert rep.post_filtered["c4_centerpiece"] >= 1
    heads: dict = {}
    for c in cards:
        head = ts.deck_centerpiece(c.give_player_ids, c.receive_player_ids,
                                   _SEED)
        heads[head] = heads.get(head, 0) + 1
    assert heads and max(heads.values()) <= 2
    # cap 0 ⇒ the C4 stage is a no-op (live inertness rule).
    with ts._cfg_override({"deck_headliner_cap": 0.0}):
        cards0, rep0 = _gen()
    assert rep0.post_filtered["c4_centerpiece"] == 0
    assert len(cards0) > len(cards)


def test_max_per_opponent_module_contract():
    # None (the adapter's value, §8 R-g) = full ranked list; an int caps
    # per target in rank order. No post_filtered counter — the pinned key
    # set does not name it, and the adapter can never reach it.
    full, _rep = _gen()
    capped, rep_c = _gen(max_per_opponent=3)
    per: dict = {}
    for c in capped:
        per[c.target_user_id] = per.get(c.target_user_id, 0) + 1
    assert per and max(per.values()) <= 3
    assert capped == full[:len(capped)] or len(capped) < len(full)
    assert set(rep_c.post_filtered) == set(_rep.post_filtered)


# ───────────── organic isolation — the grep + sys.modules proof ────────────

def test_organic_never_imports_fit():
    import inspect

    # Source-level: the organic generator never IMPORTS or calls this
    # module — and neither does gen_v2 (the other organic-path generator).
    # Comments are stripped first: the fit knob block in _DEFAULT_CFG
    # legitimately NAMES the module while documenting that arm A never
    # imports it.
    def _code(mod) -> str:
        return "\n".join(line.split("#", 1)[0]
                         for line in inspect.getsource(mod).splitlines())

    assert "trade_gen_fit" not in _code(ts)
    import backend.trade_gen_v2 as tgv2
    assert "trade_gen_fit" not in _code(tgv2)

    # Runtime-level: drop the module from sys.modules, run an ORGANIC
    # generate (flag `trade.bakeoff` never enters trade_service — the
    # organic path is generate_trades itself), and prove nothing re-imported
    # it. Restore the registry afterwards for the rest of the suite.
    saved = sys.modules.pop("backend.trade_gen_fit", None)
    try:
        svc = ts.TradeService(players=_PLAYERS)
        svc.add_league(_league())
        cards = svc.generate_trades(
            user_id="user", user_elo={}, user_roster=list(_USER_ROSTER),
            league_id="Lfit", seed_elo=dict(_SEED),
            fairness_threshold=0.5, max_per_opponent=10)
        assert isinstance(cards, list)
        assert "backend.trade_gen_fit" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["backend.trade_gen_fit"] = saved


# ───────────── arms_json['fit'] — the diagnostics schema through the runner ─

class _SvcStub:
    """The two attributes gen_fit_cards reads from the service."""
    def __init__(self, players, league):
        self._players = players
        self._leagues = {league.league_id: league}
        self._past_decision_keys: set = set()


#: Every §1.2 FitReport key + the three S7 post-generation counters the
#: adapter adds — the arms_json['fit'].diagnostics contract.
_FIT_DIAG_KEYS = {
    "opponents", "boarded_opponents", "enumerated", "scored", "killed",
    "r5_fail_scored", "capped_pairs", "post_filtered", "emitted",
    "one_sided_pct", "both_high_pct", "mixed_pct", "you_tilt_pct",
    "median_aggregate", "top_q_pick_share", "top_q_junk_share", "ms",
    "S7_intent_filter", "S7_headliner_cap", "S7_served_to_deck",
}


def test_arms_json_fit_diagnostics_schema():
    import json as _json

    svc = _SvcStub(_PLAYERS, _league(opp_board=_OPP_BOARD))
    kwargs = dict(league_id="Lfit", user_id="user",
                  user_elo=dict(_USER_BOARD),
                  user_roster=list(_USER_ROSTER), seed_elo=dict(_SEED),
                  scoring_format="1qb_ppr")

    # Adapter-level: the drained dict carries the full schema.
    cards = bo.gen_fit_cards(svc, dict(kwargs))
    assert cards
    diag = bo.last_fit_diagnostics()
    assert set(diag) == _FIT_DIAG_KEYS
    assert set(diag["killed"]) == {"K0", "K1", "K2", "K3", "K4", "K5",
                                   "K6", "K7", "junk"}
    assert diag["S7_served_to_deck"] == len(cards)
    # …and the drain drained (the leak guard).
    assert bo.last_fit_diagnostics() == {}

    # Runner-level: the same dict lands on arms_json['fit'].diagnostics.
    knobs = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0}
    with patch.object(bo, "_cfg",
                      lambda k, d: float(knobs.get(k, d))):
        run = bo.run_bakeoff(
            generate=lambda **ov: [],
            gen_v2=lambda **ov: [],
            gen_fit=lambda **ov: bo.gen_fit_cards(svc, {**kwargs, **ov}),
            league_id="Lfit", iso_week="2026-W34", interleave=True,
            roster=(bo.ARM_CURRENT, bo.ARM_FIT))
    row = run.run_row(job_id="j", user_id="user", league_id="Lfit")
    arms = _json.loads(row["arms_json"])
    assert arms["fit"]["cards"] == len(cards)
    assert set(arms["fit"]["diagnostics"]) == _FIT_DIAG_KEYS
    assert arms["fit"]["fairness_threshold"] is None     # HLD F-7 posture
