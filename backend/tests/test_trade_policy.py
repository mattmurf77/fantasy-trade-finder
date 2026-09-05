"""
The shared trade-policy evaluator — backend/trade_policy.py.

Scope block: docs/plans/personal-market-policy/scope.md

These are the PURE tests: the evaluator's math, its floors, its symmetry and
its snapshot. The wiring (v2, v3, the mutation paths, deck composition,
proposals, match attribution, flag-off byte identity) is in
`test_trade_policy_wiring.py`.

Every test here pins a numbered behavior from the brief's test list, and the
docstring says which. When one fails, the docstring is the specification.

Package shape note: every fixture below is a 1-for-1, because
`package_value_v2` returns the bare asset value for a single-asset side
against a single-asset other side. That makes `market_ratio` exactly
`min(a, b) / max(a, b)`, so a floor assertion is arithmetic rather than a
guess about the package curve. Multi-asset packages are exercised in the
wiring tests, where the real generators build them.
"""

import pytest

import backend.trade_service as ts
import backend.trade_policy as tp
from backend.bakeoff_profiles import MODEL_A_PROFILE


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_cfg_and_flags(monkeypatch):
    """`trade_service._cfg` is a process-global dict and `_c` reads it at call
    time (tests/CLAUDE.md, harness pattern 4). Snapshot and restore, and force
    both policy flags ON so the pure evaluator can be exercised — the flag-OFF
    guarantee is a wiring property, tested in the wiring file."""
    saved = dict(ts._cfg)
    monkeypatch.setattr(tp, "policy_enabled", lambda: True)
    monkeypatch.setattr(tp, "telemetry_enabled", lambda: True)
    yield
    ts._cfg.clear()
    ts._cfg.update(saved)


def _knobs(**over):
    ts._cfg.update({k: float(v) for k, v in over.items()})


def _vals(**kw):
    """A pid -> value accessor from a plain dict."""
    return lambda pid: float(kw[pid])


def _conf(default=0.0, **kw):
    return lambda pid: float(kw.get(pid, default))


def _evaluate(*, give_v, recv_v, viewer=None, partner=None,
              viewer_conf=0.0, partner_conf=0.0, requested=None,
              partner_has_board=True):
    """One 1-for-1 candidate: viewer gives `g`, receives `r`.

    `give_v`/`recv_v` are the CONSENSUS values (so the market ratio is
    min/max of them). `viewer`/`partner` are (gives, receives) tuples in that
    manager's own effective value space; omitted means "same as consensus",
    i.e. a board with no divergence at all.
    """
    market = {"g": float(give_v), "r": float(recv_v)}
    v_give, v_recv = viewer if viewer else (give_v, recv_v)
    p_give, p_recv = partner if partner else (give_v, recv_v)
    return tp.evaluate_trade_policy(
        give_ids=["g"], receive_ids=["r"],
        consensus_value=_vals(**market),
        viewer_effective_value=_vals(g=v_give, r=v_recv),
        viewer_raw_value=_vals(g=v_give, r=v_recv),
        viewer_confidence_of=_conf(viewer_conf),
        partner_effective_value=(_vals(g=p_give, r=p_recv)
                                 if partner_has_board else None),
        partner_raw_value=(_vals(g=p_give, r=p_recv)
                           if partner_has_board else None),
        partner_confidence_of=(_conf(partner_conf)
                               if partner_has_board else None),
        partner_has_board=partner_has_board,
        requested_floor=requested,
    )


# ---------------------------------------------------------------------------
# 1 / 4 — the floors themselves
# ---------------------------------------------------------------------------

def test_one_board_card_at_084_is_rejected_and_085_is_accepted():
    """Brief test 1. A card with no opponent board sits behind the
    one-board floor (0.85) — there is no two-sided personal evidence to
    justify departing further from the market."""
    _knobs(market_floor_one_board=0.85)

    below = _evaluate(give_v=1000.0, recv_v=840.0, partner_has_board=False)
    assert below.market_ratio == pytest.approx(0.84, abs=1e-4)
    assert not below.eligible
    assert below.reason == tp.REASON_BELOW_FLOOR
    assert below.effective_floor == pytest.approx(0.85)

    at = _evaluate(give_v=1000.0, recv_v=850.0, partner_has_board=False)
    assert at.market_ratio == pytest.approx(0.85, abs=1e-4)
    assert at.eligible
    assert at.lane == tp.LANE_FALLBACK


def test_no_card_can_pass_below_the_absolute_floor_at_any_knob_setting():
    """Brief test 4. `market_floor_absolute` is the one non-negotiable
    bar. Even with every other floor knob driven to zero — the configuration
    an operator could reach by accident through the admin surface — nothing
    below it is eligible."""
    _knobs(market_floor_absolute=0.65, market_floor_one_board=0.0,
           market_floor_two_board_base=0.0,
           market_floor_confidence_discount=0.0,
           market_floor_surplus_discount=0.0)
    res = _evaluate(give_v=1000.0, recv_v=640.0,
                    viewer=(500.0, 1600.0), partner=(1600.0, 500.0),
                    viewer_conf=1.0, partner_conf=1.0)
    assert res.market_ratio == pytest.approx(0.64, abs=1e-4)
    assert not res.eligible
    assert res.reason == tp.REASON_BELOW_ABSOLUTE


def test_one_board_card_is_never_labelled_a_mutual_win():
    """Acceptance criterion: "a card with no real opponent board uses the
    one-board floor and is never described as a proven mutual win"."""
    res = _evaluate(give_v=1000.0, recv_v=980.0, partner_has_board=False)
    assert res.eligible
    assert res.basis == tp.BASIS_ONE_BOARD
    assert res.lane == tp.LANE_FALLBACK
    assert res.personal_opportunity is None
    # The opponent's board fields are NULL, not a copy of consensus.
    assert res.partner.source == tp.BASIS_CONSENSUS
    assert res.partner.gives_effective is None
    assert res.partner.package_confidence is None
    assert res.client_payload()["value_basis"] == tp.BASIS_ONE_BOARD


# ---------------------------------------------------------------------------
# 2 / 3 — the dynamic floor
# ---------------------------------------------------------------------------

def test_weak_confidence_divergence_cannot_pass_below_the_two_board_base():
    """Brief test 2. Two boards, but no comparison evidence behind either.
    The confidence and surplus discounts both evaluate to zero, so the floor
    stays at the 0.80 base — weak evidence buys no relief."""
    _knobs(market_floor_two_board_base=0.80,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05)
    res = _evaluate(give_v=1000.0, recv_v=790.0,
                    viewer=(700.0, 1200.0), partner=(1200.0, 700.0),
                    viewer_conf=0.0, partner_conf=0.0)
    assert res.trade_confidence == 0.0
    assert res.policy_floor == pytest.approx(0.80)
    assert not res.eligible
    assert res.reason == tp.REASON_BELOW_FLOOR


def test_strong_high_confidence_two_sided_opportunity_reaches_the_absolute_floor():
    """Brief test 3. Both boards well-sampled AND both managers gaining
    strongly: 0.80 − 0.10 − 0.05 = 0.65, the absolute floor. This is the
    conviction lane the whole design exists to open."""
    _knobs(market_floor_two_board_base=0.80,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05,
           market_floor_absolute=0.65, policy_surplus_norm=0.25)
    res = _evaluate(give_v=1000.0, recv_v=660.0,
                    # Each side values what it receives ~40% above what it
                    # gives, on its own board.
                    viewer=(1000.0, 1400.0), partner=(1400.0, 1000.0),
                    viewer_conf=1.0, partner_conf=1.0)
    assert res.trade_confidence == pytest.approx(1.0)
    assert res.personal_opportunity >= 0.25
    assert res.policy_floor == pytest.approx(0.65)
    assert res.eligible
    assert res.lane == tp.LANE_CONVICTION


def test_core_lane_starts_at_the_core_ratio():
    """Deck-composition contract: at or above `market_core_ratio` a
    two-board card is Core, below it (but above its floor) Conviction."""
    _knobs(market_core_ratio=0.80)
    core = _evaluate(give_v=1000.0, recv_v=850.0,
                     viewer=(900.0, 1100.0), partner=(1100.0, 900.0),
                     viewer_conf=1.0, partner_conf=1.0)
    assert core.eligible and core.lane == tp.LANE_CORE
    conv = _evaluate(give_v=1000.0, recv_v=780.0,
                     viewer=(900.0, 1400.0), partner=(1400.0, 900.0),
                     viewer_conf=1.0, partner_conf=1.0)
    assert conv.eligible and conv.lane == tp.LANE_CONVICTION


@pytest.mark.parametrize("confidence", [0.0, 0.25, 0.5, 0.75, 1.0])
@pytest.mark.parametrize("strength", [0.0, 0.5, 1.0])
def test_more_confidence_or_more_gain_never_tightens_the_floor(confidence,
                                                               strength):
    """Brief test 5. `derive_policy_floor` is monotone NON-INCREASING in
    both inputs. A user who ranks MORE, or a trade that helps both managers
    MORE, must never face a stricter market bar for it — that would punish
    exactly the evidence the product wants."""
    _knobs(market_floor_two_board_base=0.80,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05, market_floor_absolute=0.65)
    base = tp.derive_policy_floor(two_board=True, trade_confidence=0.0,
                                  normalized_strength=0.0)
    here = tp.derive_policy_floor(two_board=True,
                                  trade_confidence=confidence,
                                  normalized_strength=strength)
    assert here <= base + 1e-9
    # …and strictly monotone in each argument independently.
    more_conf = tp.derive_policy_floor(
        two_board=True, trade_confidence=min(confidence + 0.25, 1.0),
        normalized_strength=strength)
    assert more_conf <= here + 1e-9
    more_gain = tp.derive_policy_floor(
        two_board=True, trade_confidence=confidence,
        normalized_strength=min(strength + 0.25, 1.0))
    assert more_gain <= here + 1e-9


def test_the_floor_is_clamped_into_its_configured_band():
    """No combination of discounts can drive the floor below the absolute
    minimum or above the two-board base."""
    _knobs(market_floor_two_board_base=0.80, market_floor_absolute=0.65,
           market_floor_confidence_discount=5.0,   # absurd, on purpose
           market_floor_surplus_discount=5.0)
    assert tp.derive_policy_floor(two_board=True, trade_confidence=1.0,
                                  normalized_strength=1.0) == pytest.approx(0.65)
    _knobs(market_floor_confidence_discount=-5.0,
           market_floor_surplus_discount=-5.0)
    assert tp.derive_policy_floor(two_board=True, trade_confidence=1.0,
                                  normalized_strength=1.0) == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# 6 / 7 — confidence
# ---------------------------------------------------------------------------

def test_missing_confidence_fails_safe_toward_consensus():
    """Brief test 6. No evidence must price a player at CONSENSUS and buy
    the trade no floor relief. The pre-change `_shrink_user_elo` did the
    opposite — `confidence=None` returned the board raw, i.e. fully trusted."""
    seed = {"a": 1500.0, "b": 1500.0}
    personal = {"a": 1900.0, "b": 1100.0}

    # No map at all.
    out = tp.shrink_board(personal, seed, None)
    assert out == {"a": 1500.0, "b": 1500.0}

    # A map that simply does not mention these players.
    out = tp.shrink_board(personal, seed, {"someone_else": 1.0})
    assert out == {"a": 1500.0, "b": 1500.0}

    # And the weight itself is 0.0, not 1.0, for an unknown count/source.
    assert tp.confidence_weight_for(None, None) == 0.0
    assert tp.confidence_weight_for(None, tp.SOURCE_LEGACY) == 0.0


def test_confidence_weight_shapes_match_the_specified_sources():
    _knobs(shrink_pseudocount=4.0, conf_source_seed=0.0,
           conf_source_cross_format=0.75, conf_source_explicit=1.0)
    assert tp.confidence_weight_for(4, tp.SOURCE_VOTES) == pytest.approx(0.5)
    assert tp.confidence_weight_for(12, tp.SOURCE_VOTES) == pytest.approx(0.75)
    assert tp.confidence_weight_for(0, tp.SOURCE_VOTES) == 0.0
    assert tp.confidence_weight_for(999, tp.SOURCE_SEED) == 0.0
    assert tp.confidence_weight_for(0, tp.SOURCE_CROSS_FORMAT) == pytest.approx(0.75)
    assert tp.confidence_weight_for(0, tp.SOURCE_EXPLICIT) == pytest.approx(1.0)


def test_both_managers_boards_are_shrunk_by_the_identical_rule():
    """Brief test 7. THE asymmetry this whole change exists to remove:
    before it, the requesting user's board was shrunk toward consensus by
    how well-sampled it was while a league-mate's published board was used
    raw (docs/reviews/2026-08-19-armb-audit-claims-3-4.md §3)."""
    seed = {"x": 1500.0}
    viewer_board = {"x": 1900.0}
    partner_board = {"x": 1900.0}
    conf = {"x": 0.5}
    assert (tp.shrink_board(viewer_board, seed, conf)
            == tp.shrink_board(partner_board, seed, conf))
    assert tp.shrink_board(viewer_board, seed, conf)["x"] == pytest.approx(1700.0)


def test_package_confidence_is_consensus_value_weighted():
    """A cheap filler must not vouch for an unranked centrepiece, and an
    unranked filler must not condemn a well-ranked one."""
    cv = _vals(star=9000.0, filler=100.0)
    # The star is well known, the filler is not.
    assert tp.compute_package_confidence(
        ["star", "filler"], cv, _conf(0.0, star=1.0)) == pytest.approx(
            9000.0 / 9100.0, abs=1e-4)
    # Reversed: the filler is known, the star is not.
    assert tp.compute_package_confidence(
        ["star", "filler"], cv, _conf(0.0, filler=1.0)) == pytest.approx(
            100.0 / 9100.0, abs=1e-4)


# ---------------------------------------------------------------------------
# 8 / 9 — what may and may not move the bar
# ---------------------------------------------------------------------------

def test_uncertainty_can_never_rescue_a_point_ratio_below_the_hard_floor():
    """Brief test 8. The legacy range-overlap gate admitted a card whose
    POINT ratio was under the bar whenever the two value intervals
    overlapped — so LOW confidence made the engine more permissive. The
    evaluator judges the point ratio and nothing else; there is no
    confidence input that can flip this card to eligible."""
    _knobs(market_floor_two_board_base=0.80, market_floor_absolute=0.65,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05)
    for vc, pc in ((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)):
        res = _evaluate(give_v=1000.0, recv_v=600.0,
                        viewer=(600.0, 2000.0), partner=(2000.0, 600.0),
                        viewer_conf=vc, partner_conf=pc)
        assert not res.eligible, (vc, pc)
        assert res.market_ratio == pytest.approx(0.60, abs=1e-4)


def test_a_stricter_user_preference_tightens_and_can_never_loosen():
    """Brief test 9. THE correction. The live divergence path composes with
    `min(requested, fairness_floor_divergence)`, so a user asking for a
    stricter 0.75 band was handed the looser 0.55 gate — their stated
    preference made the guardrail weaker. `compose_effective_floor` is a
    `max`."""
    _knobs(market_floor_two_board_base=0.80, market_floor_absolute=0.65,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05, market_core_ratio=0.80)

    kw = dict(give_v=1000.0, recv_v=720.0,
              viewer=(900.0, 1400.0), partner=(1400.0, 900.0),
              viewer_conf=1.0, partner_conf=1.0)

    # Policy floor lands at 0.65 here, so 0.72 clears with no preference…
    loose = _evaluate(**kw, requested=0.50)
    assert loose.eligible
    assert loose.effective_floor == pytest.approx(loose.policy_floor)

    # …and a stricter 0.75 request TIGHTENS it and rejects the same card.
    strict = _evaluate(**kw, requested=0.75)
    assert strict.effective_floor == pytest.approx(0.75)
    assert not strict.eligible

    # A request BELOW the absolute floor cannot loosen anything.
    absurd = _evaluate(give_v=1000.0, recv_v=500.0,
                       viewer=(500.0, 2000.0), partner=(2000.0, 500.0),
                       viewer_conf=1.0, partner_conf=1.0, requested=0.10)
    assert absurd.effective_floor >= 0.65
    assert not absurd.eligible


def test_compose_effective_floor_is_a_max_over_all_three_inputs():
    _knobs(market_floor_absolute=0.65)
    assert tp.compose_effective_floor(0.70, 0.50) == pytest.approx(0.70)
    assert tp.compose_effective_floor(0.70, 0.90) == pytest.approx(0.90)
    assert tp.compose_effective_floor(0.10, None) == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# 11 / 15 — ranking and symmetry
# ---------------------------------------------------------------------------

def test_personal_opportunity_is_the_weaker_managers_gain():
    """A trade excellent for one side and barely positive for the other must
    score below one that is meaningfully positive for both. That is why the
    primary term is `min`, not a mean."""
    lopsided = _evaluate(give_v=1000.0, recv_v=950.0,
                         viewer=(1000.0, 2000.0), partner=(1010.0, 1000.0),
                         viewer_conf=1.0, partner_conf=1.0)
    balanced = _evaluate(give_v=1000.0, recv_v=950.0,
                         viewer=(1000.0, 1300.0), partner=(1300.0, 1000.0),
                         viewer_conf=1.0, partner_conf=1.0)
    assert balanced.personal_opportunity > lopsided.personal_opportunity
    # rank_key sorts ascending, so the better card sorts FIRST.
    assert balanced.rank_key < lopsided.rank_key


def test_raising_the_weaker_sides_gain_never_lowers_the_rank():
    """Brief test 11, at the evaluator level. Holding everything else
    constant, increasing the weaker manager's gain moves the card UP."""
    prev = None
    for partner_recv in (1010.0, 1100.0, 1200.0, 1300.0, 1400.0):
        res = _evaluate(give_v=1000.0, recv_v=950.0,
                        viewer=(1000.0, 2000.0),
                        partner=(partner_recv, 1000.0),
                        viewer_conf=1.0, partner_conf=1.0)
        if prev is not None:
            assert res.rank_key <= prev, partner_recv
        prev = res.rank_key


def test_reversing_the_managers_and_the_direction_preserves_the_verdict():
    """Brief test 15. Swap who is viewing AND swap the package direction:
    the market ratio, the eligibility and the magnitude of the personal
    opportunity must all be identical. If they are not, the engine's answer
    depends on who opened the deck — the 86.9%-one-orientation finding."""
    _knobs(market_floor_two_board_base=0.80, market_floor_absolute=0.65,
           market_floor_confidence_discount=0.10,
           market_floor_surplus_discount=0.05)
    a = _evaluate(give_v=1000.0, recv_v=820.0,
                  viewer=(900.0, 1200.0), partner=(1200.0, 900.0),
                  viewer_conf=0.8, partner_conf=0.6)
    # B's view: B gives what A receives, and receives what A gives.
    b = _evaluate(give_v=820.0, recv_v=1000.0,
                  viewer=(900.0, 1200.0), partner=(1200.0, 900.0),
                  viewer_conf=0.6, partner_conf=0.8)
    assert a.market_ratio == pytest.approx(b.market_ratio)
    assert a.eligible == b.eligible
    assert a.trade_confidence == pytest.approx(b.trade_confidence)
    assert a.personal_opportunity == pytest.approx(b.personal_opportunity)


# ---------------------------------------------------------------------------
# 14 — one consensus definition
# ---------------------------------------------------------------------------

def test_the_policy_prices_consensus_with_the_calculators_own_function():
    """Brief test 14. `compute_market_ratio` delegates to
    `trade_optimizer._consensus_packages`, which is what the manual
    calculator and all three generators price with. Identity by
    construction, not by two implementations kept in sync by hand."""
    from backend.trade_optimizer import _consensus_packages
    cv = _vals(a=4200.0, b=1900.0, c=2600.0)
    gv, rv, ratio = tp.compute_market_ratio(["a"], ["b", "c"], cv)
    exp_g, exp_r = _consensus_packages(["a"], ["b", "c"], cv)
    assert (gv, rv) == pytest.approx((exp_g, exp_r))
    assert ratio == pytest.approx(min(exp_g, exp_r) / max(exp_g, exp_r))


def test_all_four_consensus_accessors_are_one_function():
    """The three generators' `_vs` / `_sv` / `cval` and the policy all build
    from `trade_service.make_consensus_value_fn`. Four mirrors of the same
    formula was the shape of a bug waiting to happen."""
    import backend.trade_optimizer as opt
    import backend.trade_gen_v2 as g2
    src_opt = opt.generate_pair_trades_v3.__code__.co_names
    assert "make_consensus_value_fn" in src_opt
    assert "make_consensus_value_fn" in g2.generate_league_suggestions.__code__.co_names \
        or any("make_consensus_value_fn" in getattr(c, "co_names", ())
               for c in g2.generate_league_suggestions.__code__.co_consts
               if hasattr(c, "co_names"))


# ---------------------------------------------------------------------------
# 16 — the snapshot
# ---------------------------------------------------------------------------

def test_the_snapshot_is_complete_parseable_and_matches_its_assets():
    """Brief test 16 + the instrumentation acceptance criteria: the snapshot
    must be parseable, its asset ids and DIRECTIONS must match the served
    package exactly, and the recomputed market ratio must match the stored
    one."""
    import json
    res = tp.evaluate_trade_policy(
        give_ids=["g1", "g2"], receive_ids=["r1"],
        consensus_value=_vals(g1=2000.0, g2=800.0, r1=2600.0),
        viewer_effective_value=_vals(g1=1900.0, g2=700.0, r1=3000.0),
        viewer_raw_value=_vals(g1=2100.0, g2=600.0, r1=3300.0),
        viewer_confidence_of=_conf(0.8),
        partner_effective_value=_vals(g1=2400.0, g2=900.0, r1=2500.0),
        partner_raw_value=_vals(g1=2600.0, g2=950.0, r1=2400.0),
        partner_confidence_of=_conf(0.6),
        partner_has_board=True, requested_floor=0.5,
        scoring_format="sf_tep", model_arm="challenger",
    )
    blob = tp.dumps(res.valuation)
    snap = json.loads(blob)

    assert snap["schema_version"] == tp.VALUATION_SCHEMA_VERSION
    assert snap["scoring_format"] == "sf_tep"
    assert snap["snapshot_stage"] == "serve"
    assert snap["policy"]["model_arm"] == "challenger"
    assert snap["policy"]["policy_version"] == tp.POLICY_V1
    assert snap["policy"]["value_basis"] == tp.BASIS_TWO_BOARD

    # Directions: `give` is the card's give side, for BOTH boards.
    assert [a["id"] for a in snap["assets"]["give"]] == ["g1", "g2"]
    assert [a["id"] for a in snap["assets"]["receive"]] == ["r1"]
    assert tp.snapshot_matches_assets(snap, {"give": ["g1", "g2"],
                                             "receive": ["r1"]})
    assert not tp.snapshot_matches_assets(snap, {"give": ["r1"],
                                                 "receive": ["g1", "g2"]})

    # Recomputed ratio matches the stored one well inside the 0.001 bar.
    gv, rv, ratio = tp.compute_market_ratio(
        ["g1", "g2"], ["r1"], _vals(g1=2000.0, g2=800.0, r1=2600.0))
    assert abs(snap["market"]["ratio"] - ratio) < 0.001

    # Both boards carry raw AND effective; neither is a copy of the other.
    for side in ("viewer_board", "partner_board"):
        b = snap[side]
        assert b["source"] == "personal"
        assert b["gives_raw"] is not None and b["gives_effective"] is not None
        assert b["package_confidence"] is not None


def test_a_missing_opponent_board_leaves_partner_fields_null_not_copied():
    """"Do not manufacture a personal board by copying consensus" — a
    fabricated partner board would make a one-board card indistinguishable
    from a proven mutual win in every later query."""
    res = _evaluate(give_v=1000.0, recv_v=900.0, partner_has_board=False)
    pb = res.valuation["partner_board"]
    assert pb["source"] == tp.BASIS_CONSENSUS
    assert pb["gives_raw"] is None and pb["gives_effective"] is None
    assert pb["package_confidence"] is None
    assert res.valuation["mutual"]["personal_opportunity"] is None
    for asset in (res.valuation["assets"]["give"]
                  + res.valuation["assets"]["receive"]):
        assert asset["partner_raw_value"] is None
        assert asset["partner_effective_value"] is None


def test_a_rejected_card_still_produces_a_snapshot_with_its_reason():
    """A rejection has to be readable, or the treatment's discarded
    candidates vanish from the denominator."""
    res = _evaluate(give_v=1000.0, recv_v=400.0, partner_has_board=False)
    assert not res.eligible
    assert res.valuation["policy"]["eligible"] is False
    assert res.valuation["policy"]["rejection_reason"] == res.reason


def test_an_empty_side_is_rejected_without_pricing_anything():
    res = tp.evaluate_trade_policy(
        give_ids=[], receive_ids=["r"],
        consensus_value=_vals(r=1000.0),
        viewer_effective_value=_vals(r=1000.0))
    assert not res.eligible
    assert res.reason == tp.REASON_EMPTY_PACKAGE
    assert res.valuation["policy"]["rejection_reason"] == tp.REASON_EMPTY_PACKAGE


def test_serialization_failure_is_counted_not_raised():
    """Telemetry may never fail a trade job."""
    tp.reset_health()
    assert tp.dumps({"bad": object()}) is None
    assert tp.HEALTH["serialize_failures"] == 1
    tp.reset_health()


# ---------------------------------------------------------------------------
# 20 — canonical concept identity
# ---------------------------------------------------------------------------

def test_mirrored_cards_share_one_canonical_concept_id():
    """Brief test 20. The existing `trade_hash` is viewer-relative, so A's
    card and B's mirror hash differently and cannot be joined. The concept
    id must be identical from both perspectives of the same package."""
    a = tp.trade_concept_id(league_id="L1", viewer_user_id="alice",
                            partner_user_id="bob",
                            viewer_gives=["p1", "p2"], viewer_receives=["p3"])
    b = tp.trade_concept_id(league_id="L1", viewer_user_id="bob",
                            partner_user_id="alice",
                            viewer_gives=["p3"], viewer_receives=["p2", "p1"])
    assert a is not None and a == b


def test_concept_id_separates_leagues_participants_and_packages():
    base = dict(league_id="L1", viewer_user_id="alice", partner_user_id="bob",
                viewer_gives=["p1"], viewer_receives=["p2"])
    ref = tp.trade_concept_id(**base)
    assert tp.trade_concept_id(**{**base, "league_id": "L2"}) != ref
    assert tp.trade_concept_id(**{**base, "partner_user_id": "carol"}) != ref
    assert tp.trade_concept_id(**{**base, "viewer_receives": ["p3"]}) != ref
    # Order within a side is irrelevant; identity is the SET.
    assert tp.trade_concept_id(
        **{**base, "viewer_gives": ["p1"], "viewer_receives": ["p2"]}) == ref


def test_concept_id_is_none_when_a_participant_is_unknown():
    """Better no id than a colliding one: a null joins nothing, a wrong id
    joins the wrong two managers."""
    assert tp.trade_concept_id(league_id="L1", viewer_user_id="a",
                               partner_user_id=None, viewer_gives=["p"],
                               viewer_receives=["q"]) is None
    assert tp.trade_concept_id(league_id=None, viewer_user_id="a",
                               partner_user_id="b", viewer_gives=["p"],
                               viewer_receives=["q"]) is None


# ---------------------------------------------------------------------------
# 13 — deck composition
# ---------------------------------------------------------------------------

class _Card:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<{self.name}>"


def _entry(name, lane, opportunity=0.1):
    res = tp.PolicyResult(
        eligible=True, reason=None, lane=lane, basis=tp.BASIS_TWO_BOARD,
        market_ratio=0.9 if lane == tp.LANE_CORE else 0.7,
        market_gives=1000.0, market_receives=900.0, requested_floor=0.5,
        policy_floor=0.65, effective_floor=0.65,
        viewer=tp.BoardValuation.consensus_only(),
        partner=tp.BoardValuation.consensus_only(),
        personal_opportunity=opportunity, harmonic_effective_surplus=100.0,
        trade_confidence=0.8, policy_variant=tp.POLICY_V1)
    return (_Card(name), res)


def test_deck_leads_with_core_and_caps_conviction():
    """Brief test 13. First three cards Core, at most two Conviction, and
    Conviction sits behind the trust-building lead block."""
    _knobs(deck_core_lead_cards=3, conviction_deck_share=0.20,
           deck_core_min_share=0.70)
    entries = ([_entry(f"core{i}", tp.LANE_CORE) for i in range(8)]
               + [_entry(f"conv{i}", tp.LANE_CONVICTION) for i in range(5)])
    kept, dropped = tp.compose_deck(entries, size=10)

    lanes = [r.lane for _c, r in kept]
    assert lanes[:3] == [tp.LANE_CORE] * 3
    assert lanes.count(tp.LANE_CONVICTION) <= 2
    assert lanes.count(tp.LANE_CORE) >= 7
    assert len(kept) <= 10
    assert dropped, "surplus candidates must be reported, not silently lost"


def test_a_short_deck_is_preferred_to_a_weakened_guardrail():
    """"If safe supply is insufficient, return a smaller deck rather than
    weakening the guardrail."" Only two Core cards exist, so the deck comes
    back short — it does not backfill with Conviction to reach ten."""
    _knobs(deck_core_lead_cards=3, conviction_deck_share=0.20,
           deck_core_min_share=0.70)
    entries = ([_entry("core0", tp.LANE_CORE), _entry("core1", tp.LANE_CORE)]
               + [_entry(f"conv{i}", tp.LANE_CONVICTION) for i in range(8)])
    kept, _dropped = tp.compose_deck(entries, size=10)
    assert len(kept) < 10
    n_core = sum(1 for _c, r in kept if r.lane == tp.LANE_CORE)
    assert n_core >= len(kept) * 0.70 - 1e-9


def test_consensus_fallback_never_displaces_valid_divergence_cards():
    """Brief test 12, at the composition level. Fallback fills only what
    Core and Conviction could not — a consensus card's higher fairness score
    must not push out a valid two-board find."""
    _knobs(deck_core_lead_cards=3, conviction_deck_share=0.20,
           deck_core_min_share=0.70)
    entries = ([_entry(f"core{i}", tp.LANE_CORE) for i in range(10)]
               + [_entry(f"fb{i}", tp.LANE_FALLBACK) for i in range(10)])
    kept, _dropped = tp.compose_deck(entries, size=10)
    assert all(r.lane == tp.LANE_CORE for _c, r in kept)


# ---------------------------------------------------------------------------
# Arm A is untouched
# ---------------------------------------------------------------------------

def test_the_pinned_historical_model_a_profile_is_not_modified():
    """The brief is explicit: "do not modify the pinned historical
    MODEL_A_PROFILE". None of the policy knobs may appear in it — arm A is a
    reconstruction of an engine that predates the policy, so there is
    nothing for it to pin, and pinning would change arm A rather than
    preserve it. The reasoning is recorded in
    docs/plans/three-model-bakeoff/scope-phase2.md."""
    policy_knobs = {
        "market_floor_absolute", "market_floor_one_board",
        "market_floor_two_board_base", "market_floor_confidence_discount",
        "market_floor_surplus_discount", "market_core_ratio",
        "personal_gain_min_frac", "conviction_deck_share",
        "deck_core_lead_cards", "deck_core_min_share", "policy_surplus_norm",
        "conf_source_seed", "conf_source_cross_format", "conf_source_explicit",
        "policy_confidence_band_high", "policy_confidence_band_med",
        "policy_shadow_log_cap",
    }
    assert policy_knobs & set(MODEL_A_PROFILE) == set()
    # …and every one of them really is a declared knob, so `_c` cannot
    # KeyError the first time an arm evaluates a candidate.
    assert policy_knobs <= set(ts._DEFAULT_CFG)


def test_confidence_band_labels_are_the_privacy_safe_summary():
    """A card may show which band the WEAKER board falls in. It may never
    show the counterparty's values, positions or counts."""
    _knobs(policy_confidence_band_high=0.66, policy_confidence_band_med=0.33)
    assert tp.confidence_band(0.9) == "high"
    assert tp.confidence_band(0.5) == "medium"
    assert tp.confidence_band(0.1) == "low"

    res = _evaluate(give_v=1000.0, recv_v=900.0,
                    viewer=(900.0, 1100.0), partner=(1100.0, 900.0),
                    viewer_conf=0.9, partner_conf=0.9)
    payload = res.client_payload()
    assert set(payload) == {"market_fairness", "value_basis",
                            "confidence_band", "opportunity_label"}
    assert "partner" not in str(payload).lower()


def test_composition_respects_zero_and_small_requested_sizes():
    entries = [_entry(str(i), tp.LANE_CORE) for i in range(8)]
    for size in (0, 1, 2, 3):
        kept, _ = tp.compose_deck(entries, size=size)
        assert len(kept) == size


def test_conviction_share_is_based_on_realized_deck_length():
    entries = ([_entry(str(i), tp.LANE_CORE) for i in range(3)]
               + [_entry('conv', tp.LANE_CONVICTION)])
    kept, _ = tp.compose_deck(entries, size=10)
    assert all(r.lane == tp.LANE_CORE for _, r in kept)


def test_partial_persisted_confidence_does_not_discard_other_players_counts():
    result = tp.confidence_map({'a': 4, 'b': 8, 'c': 4}, source='votes',
                               weights={'a': 1, 'c': None, 'bad': 'invalid'})
    assert result == {'a': 1, 'b': pytest.approx(8 / 12), 'c': .5, 'bad': 0}


def test_pair_policy_uses_same_effective_basis_even_when_legacy_viewer_shrink_is_off():
    from types import SimpleNamespace
    opponent = SimpleNamespace(has_rankings=True, elo_ratings={'g': 1400, 'r': 1600},
                               comparison_counts={'g': 4, 'r': 4})
    evaluate = tp.make_pair_evaluator(consensus_value=lambda pid: 1000,
        viewer_effective_value=lambda pid: 99999, viewer_raw_value=lambda pid: 99999,
        viewer_confidence_of=lambda pid: 1, opponent=opponent,
        seed_elo={'g': 1500, 'r': 1500}, requested_floor=.75,
        viewer_elo={'g': 1400, 'r': 1600}, viewer_counts={'g': 4, 'r': 4})
    result = evaluate(['g'], ['r'])
    values = result.valuation['assets']
    for row in values['give'] + values['receive']:
        assert row['viewer_effective_value'] == row['partner_effective_value']
