"""The next move (offer-learnings WS5): one revision of a sent offer, or none.

Synthetic boards only. Every eligibility claim is the engine evaluator's own
(`bakeoff_runner.owner_evaluator`), for each engine revision it can select.
"""

from copy import deepcopy
import json
import re
from pathlib import Path

import pytest

from backend import bakeoff_runner as bo, feature_flags as ff, trade_next_move as nm, trade_service as ts
from backend.tests.test_bilateral_contracts import world
from backend.tests.test_outlook_evidence_candidate import qualified

REPO = Path(__file__).resolve().parents[2]
LEAGUE = "synthetic_bilateral"
ARMS = {
    "owner-v1": {},
    "bilateral-1": {"owner_bilateral_enabled": 1.},
    "bilateral-2": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.},
    "bilateral-3": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
                    "owner_outlook_evidence_enabled": 1.},
}
# At the engine's package pricing a 1000-for-1150 offer gains the other
# manager ~15% of the trade from `mid`, ~18% from `mid2`, ~40% from `big`
# and nothing from `small` (a filler costs them a roster spot).
MARKET = {"give": 1000., "target": 1150., "small": 60., "mid": 300., "mid2": 340., "big": 600.}
VIEWER = {"give": 800., "target": 1400., "small": 50., "mid": 250., "mid2": 290., "big": 500.}
PARTNER = {"give": 1350., "target": 900., "small": 70., "mid": 380., "mid2": 400., "big": 700.}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", {**ff.DEFAULT_FLAGS, nm.FLAG: True})
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def context(arm="owner-v1", own=("give", "small", "mid", "mid2", "big"), other=("target",),
            market=MARKET, viewer=VIEWER, partner=PARTNER, **extra):
    args = world(own=own, other=other, market=market, viewer=viewer, partner=partner,
                 config=dict(ARMS[arm]), **extra)
    return qualified(args) if arm == "bilateral-3" else args


def offer(give=("give",), receive=("target",)):
    return ts.TradeCard("", LEAGUE, "viewer", "partner", "Partner", list(give), list(receive), 0, 0, 0)


def evaluate(ctx, give, receive):
    return bo.owner_evaluator(ctx["config"])([offer(give, receive)], **ctx)[0]


@pytest.mark.parametrize("arm", ARMS)
def test_revision_is_one_valid_bounded_change_that_keeps_the_core(arm):
    ctx = context(arm)
    move = nm.propose_revision(offer(), ctx)
    assert isinstance(move, nm.NextMove)
    card, proof = move.card, move.proof
    # Proven by the evaluator in force, bound to the card it returns.
    assert proof.eligible and proof.matches(card)
    assert proof.model_identity == (bo.owner_arm(ctx["config"]), bo.owner_version(ctx["config"]))
    again = evaluate(ctx, card.give_player_ids, card.receive_player_ids)
    assert again.eligible and again.as_dict()["market"] == proof.as_dict()["market"]
    # One change, the core kept on both sides.
    assert move.core == {"give": "give", "receive": "target"}
    assert move.change == {"kind": "add_to_give", "asset_id": "mid"}
    assert card.give_player_ids == ["give", "mid"] and card.receive_player_ids == ["target"]
    # Bounded: the step is the other manager's market gain at evaluator pricing.
    base = evaluate(context(arm), ["give"], ["target"]).as_dict()["market"]
    terms = proof.as_dict()["market"]
    step = (terms["give"] - terms["receive"]) - (base["give"] - base["receive"])
    assert move.trade_market_value == pytest.approx(max(base["give"], base["receive"]))
    assert move.step_value == pytest.approx(step)
    assert nm.STEP_MIN <= move.step_fraction <= nm.STEP_MAX


def test_smallest_in_band_step_wins_and_only_one_is_returned():
    # `mid2` is also in band; the smaller concession is the one offered.
    assert evaluate(context(), ["give", "mid2"], ["target"]).eligible
    move = nm.propose_revision(offer(), context())
    assert move.change["asset_id"] == "mid"
    without_mid = nm.propose_revision(offer(), context(own=("give", "small", "mid2", "big")))
    assert without_mid.change["asset_id"] == "mid2"
    assert without_mid.step_fraction > move.step_fraction


def test_no_revision_when_every_valid_change_is_out_of_band():
    ctx = context(own=("give", "small", "big"))
    # Both additions are valid trades; neither is a bounded step.
    assert evaluate(ctx, ["give", "small"], ["target"]).eligible
    assert evaluate(ctx, ["give", "big"], ["target"]).eligible
    assert nm.propose_revision(offer(), ctx) is None


def test_no_revision_when_the_offer_can_no_longer_be_priced():
    # The offered asset has left the viewer's roster.
    assert nm.propose_revision(offer(), context(own=("small", "mid", "mid2", "big"))) is None


def test_removing_an_asked_for_companion_and_never_the_focal_asset():
    market = {"give": 1000., "target": 900., "t2": 250.}
    ctx = context(own=("give",), other=("target", "t2"), market=market,
                  viewer={"give": 800., "target": 1300., "t2": 200.},
                  partner={"give": 1300., "target": 900., "t2": 325.})
    move = nm.propose_revision(offer(receive=("target", "t2")), ctx)
    assert move.change == {"kind": "remove_from_receive", "asset_id": "t2"}
    assert move.card.receive_player_ids == ["target"] and move.core["receive"] == "target"
    # With market gates opened and the band moved past the companion's step,
    # only removing the focal asset would qualify, and it is never offered.
    assert nm.propose_revision(offer(receive=("target", "t2")), _loose(ctx),
                               step_min=move.step_fraction + .01, step_max=10.) is None


def _loose(ctx):
    """Market gates opened so a focal-only removal is itself a valid trade."""
    loose = deepcopy(ctx)
    loose["fairness_threshold"] = 0.
    loose["config"].update(market_floor_absolute=0., max_overpay_frac=100., max_overpay_min_value=1e9)
    loose["user_elo"]["t2"] = ts.value_to_elo(5000.)
    assert evaluate(loose, ["give"], ["t2"]).eligible
    return loose


def test_a_change_that_fails_the_viewers_own_checks_is_never_offered():
    # The viewer rates `mid` far above market: giving it up fails the
    # engine's viewer checks, and the next-best in-band change takes its place.
    viewer = {**VIEWER, "mid": 3000.}
    ctx = context(viewer=viewer)
    rejected = evaluate(ctx, ["give", "mid"], ["target"])
    assert not rejected.eligible and rejected.reason.startswith("viewer")
    assert nm.propose_revision(offer(), ctx).change["asset_id"] == "mid2"
    only = context(own=("give", "mid"), viewer=viewer)
    assert nm.propose_revision(offer(), only) is None


def test_the_viewers_untouchables_are_never_added():
    market = {"give": 1000., "target": 1400., "mid": 300.}
    ctx = context(own=("give", "mid"), market=market,
                  viewer={"give": 800., "target": 1680., "mid": 250.},
                  partner={"give": 1350., "target": 1120., "mid": 380.},
                  manager_preferences={"viewer": {"untouchables": ["mid"]}})
    # The evaluator alone would accept it (same position, the viewer still
    # receives more), and its step is inside this band.
    assert evaluate(ctx, ["give", "mid"], ["target"]).eligible
    assert nm.propose_revision(offer(), ctx, step_min=.05) is None
    ctx["manager_preferences"] = {}
    assert nm.propose_revision(offer(), ctx, step_min=.05).change["asset_id"] == "mid"


def test_a_sent_offer_is_priced_despite_its_disposition_but_revisions_honour_theirs():
    key = (frozenset(["give"]), frozenset(["target"]))
    ctx = context(past_decision_keys={key})
    assert evaluate(ctx, ["give"], ["target"]).reason == "previous_disposition"
    assert nm.propose_revision(offer(), ctx).change["asset_id"] == "mid"
    passed = {key, (frozenset(["give", "mid"]), frozenset(["target"]))}
    assert nm.propose_revision(offer(), context(past_decision_keys=passed)).change["asset_id"] == "mid2"


def test_a_selection_in_the_context_does_not_carry_over():
    # A context captured for an exact selection (as the calculator routes
    # build one) still judges the revision as an organic card.
    ctx = context(pinned_give_players=["give"], pinned_receive_players=["target"], exact_give=True)
    assert evaluate(ctx, ["give", "mid"], ["target"]).reason == "exact_give_mismatch"
    assert nm.propose_revision(offer(), ctx).change["asset_id"] == "mid"


def test_inputs_are_not_mutated():
    ctx, sent = context(), offer()
    before, sent_before = deepcopy(ctx), deepcopy(sent)
    nm.propose_revision(sent, ctx)
    assert ctx == before and sent == sent_before


def test_flag_off_does_no_work(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    def forbidden(*args, **kwargs):
        raise AssertionError("evaluated with the flag off")
    monkeypatch.setattr(bo, "owner_evaluator", forbidden)
    assert nm.propose_revision(offer(), context()) is None


def test_flag_is_registered_dark_everywhere():
    assert nm.FLAG in ff.FLAG_KEYS and ff.DEFAULT_FLAGS[nm.FLAG] is False
    for path in ("config/features.json", "backend/tests/fixtures/flags/release.json",
                 "backend/tests/fixtures/flags/onboarding-v2.json",
                 "backend/tests/fixtures/flags/profiles-on.json"):
        assert json.loads((REPO / path).read_text())[nm.FLAG] is False, path


def test_no_production_module_reaches_the_generator():
    """Flag off is byte-identical because nothing serves a revision yet:
    no route, no deck wiring, no payload key. Wiring one changes this test."""
    imports = re.compile(r"^\s*(from\s+\S*trade_next_move\s+import|from\s+\S+\s+import\s+[^#\n]*\btrade_next_move\b"
                         r"|import\s+[^#\n]*\btrade_next_move\b)|import_module\([^)]*trade_next_move", re.M)
    users = [p.relative_to(REPO).as_posix() for p in (REPO / "backend").rglob("*.py")
             if "tests" not in p.parts and p.name != "trade_next_move.py"
             and imports.search(p.read_text())]
    assert users == []
