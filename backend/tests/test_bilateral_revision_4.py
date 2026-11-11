"""Revision 4 (owner-v2-bilateral-4) on constructed leagues.

Synthetic boards and people: these test ordering behaviour, not acceptance.
Each rule has a world where it changes the order against revision 2 and one
where it must not. Spec: docs/plans/offer-learnings/plan.md §3 WS1.
"""

from dataclasses import asdict
import hashlib
import json

import pytest

from backend import bakeoff_runner as bo, feature_flags as ff, trade_service as ts
from backend import trade_bilateral_presentment as presentment
from backend import trade_gen_bilateral_candidate as r2
from backend import trade_gen_bilateral_r4 as r4
from backend.tests.test_bilateral_contracts import favorable, packages, world

KEY = "owner_bilateral_revision_4_enabled"


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def premium_world(outlook):
    """The viewer can ask for the partner's pick or a player; the pick leads in r2."""
    return world(other=("pk", "pl"), positions={"pk": "PICK"},
                 viewer={"give": 800., "pk": 3000., "pl": 1300.},
                 partner={"give": 1300., "pk": 400., "pl": 800.},
                 opponent_outlooks={"partner": outlook})


def tie_world(viewer_pick):
    """Pays-picks and asks-picks offers, contender partner (no premium)."""
    return world(own=("give", "vpk"), other=("tgt", "ppk"), positions={"vpk": "PICK", "ppk": "PICK"},
                 viewer={"give": 800., "vpk": 800., "tgt": 1300., "ppk": viewer_pick},
                 partner={"give": 1300., "vpk": 1300., "tgt": 800., "ppk": 800.},
                 opponent_outlooks={"partner": "contender"})


def best_asset_world(outlook, position, partner_like):
    return world(own=("g1", "g2"), other=("star", "mid"), positions={"g1": position, "g2": position},
                 market={"g1": 650., "g2": 600., "star": 1150., "mid": 640.},
                 viewer={"g1": 500., "g2": 450., "star": 2000., "mid": 800.},
                 partner={"g1": partner_like, "g2": partner_like - 50, "star": 1000., "mid": 500.},
                 opponent_outlooks={"partner": outlook})


def order(cards):
    return [(tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in cards]


def both(args):
    return r2.generate_bilateral_trades(**args)[0], r4.generate_bilateral_trades(**args)


def proofs(cards):
    return {key: c.owner_evaluation.as_dict() for key, c in zip(order(cards), cards)}


# ── R4: owned-pick premium ────────────────────────────────────────────────

@pytest.mark.parametrize("outlook,rate", [("rebuilder", .20), ("jets", .20), ("tanking", .20)])
def test_premium_for_pick_wanting_partner_moves_their_pick_below_a_player(outlook, rate):
    before, (after, _) = both(premium_world(outlook))
    assert order(before)[0] == (("give",), ("pk",))
    assert order(after) == [(("give",), ("pl",)), (("give",), ("pk",))]
    applied = proofs(after)[(("give",), ("pk",))]["revision_4"]["pick_premium"]
    assert applied["applied"] and applied["rate"] == rate and applied["pick_ids"] == ["pk"]
    assert applied["counterparty_outlook"] == ("rebuilder" if outlook == "rebuilder" else "jets")
    assert applied["outlook_source"] == "declared" and applied["support_delta"] < 0


@pytest.mark.parametrize("outlook", ["contender", "championship", "all_in", "mystery_value"])
def test_no_premium_for_contender_or_unrecognised_outlook(outlook):
    before, (after, _) = both(premium_world(outlook))
    assert order(after) == order(before)
    for old, new in zip(before, after):
        old, new = old.owner_evaluation.as_dict(), new.owner_evaluation.as_dict()
        assert new["revision_4"]["pick_premium"]["rate"] == 0
        assert not new["revision_4"]["pick_premium"]["applied"]
        assert new["bilateral"] == old["bilateral"]


def test_not_sure_premium_is_half_the_top_rate():
    after, _ = r4.generate_bilateral_trades(**premium_world("not_sure"))
    applied = proofs(after)[(("give",), ("pk",))]["revision_4"]["pick_premium"]
    assert applied["rate"] == .10 and applied["applied"]


def test_viewer_own_picks_are_never_marked_up():
    after, _ = r4.generate_bilateral_trades(**tie_world(1300.))
    data = proofs(after)[(("vpk",), ("tgt",))]
    assert data["revision_4"]["pick_premium"]["pick_ids"] == []
    assert data["revision_4"]["pick_premium"]["premium_value"] == 0
    assert data["viewer"]["support"]["revision_4_adjustments"]["pick_premium"] == 0


@pytest.mark.parametrize("args", [premium_world("rebuilder"), premium_world("contender"), tie_world(1300.),
                                  best_asset_world("contender", "WR", 1300.),
                                  best_asset_world("rebuilder", "PICK", 1600.), favorable()],
                         ids=["premium", "contender", "tie", "best_asset", "exception", "favorable"])
def test_rules_never_change_inventory_terms_floor_or_eligibility(args):
    before, (after, _) = both(args)
    assert packages(after) == packages(before)
    old, new = proofs(before), proofs(after)
    for key in old:
        for field in ("market", "eligible", "reason", "term_efficiency", "direction"):
            assert new[key][field] == old[key][field]
        for side in ("viewer", "counterparty"):
            for field in ("market_gain_fraction", "utility", "team_plan_gain", "intent", "benefits"):
                assert new[key][side][field] == old[key][side][field]
            assert new[key][side]["support"]["revision_2_score"] == old[key][side]["support"]["score"]


# ── R1: pay-picks tie-breaker ─────────────────────────────────────────────

def test_tie_breaker_prefers_paying_picks_inside_the_tolerance():
    before, (after, report) = both(tie_world(1300.))
    pays, asks = (("vpk",), ("tgt",)), (("give",), ("ppk",))
    assert order(before).index(asks) < order(before).index(pays)
    assert order(after).index(pays) < order(after).index(asks)
    assert report.as_dict()["revision_4"]["pay_picks_tie_breaks"] == 1
    old, new = proofs(before), proofs(after)
    assert new[pays]["bilateral"] == old[pays]["bilateral"]  # Order moved, not scores.
    assert new[pays]["revision_4"]["pick_direction"] == "pays_picks"
    assert new[asks]["revision_4"]["pick_direction"] == "asks_picks"


def test_tie_breaker_has_no_effect_beyond_the_tolerance():
    before, (after, report) = both(tie_world(1320.))
    data = proofs(after)
    gap = (data[(("give",), ("ppk",))]["bilateral"]["weaker_support"]
           - data[(("vpk",), ("tgt",))]["bilateral"]["weaker_support"])
    assert gap > r4.incumbent._QUALITY_TOLERANCE
    assert order(after) == order(before)
    assert report.as_dict()["revision_4"]["pay_picks_tie_breaks"] == 0


# ── R5: best-asset rule ───────────────────────────────────────────────────

def test_several_for_their_best_asset_is_demoted_not_deleted():
    before, (after, report) = both(best_asset_world("contender", "WR", 1300.))
    ask = (("g1", "g2"), ("star",))
    assert order(before).index(ask) < order(before).index((("g1",), ("mid",)))
    assert order(after).index(ask) == len(after) - 1
    rule = proofs(after)[ask]["revision_4"]["best_asset_rule"]
    assert rule["fired"] and rule["demotion"] == r4.BEST_ASSET_DEMOTION and rule["exception"] is None
    assert rule["best_asset_ids"] == ["star"]
    assert report.as_dict()["revision_4"]["best_asset_demoted"] == 1
    old, new = proofs(before)[ask], proofs(after)[ask]
    assert new["bilateral"]["weaker_support"] == pytest.approx(
        old["bilateral"]["weaker_support"] - r4.BEST_ASSET_DEMOTION)


def test_picks_for_their_best_player_to_a_rebuilder_is_not_demoted():
    before, (after, report) = both(best_asset_world("rebuilder", "PICK", 1600.))
    ask = (("g1", "g2"), ("star",))
    assert order(after) == order(before)
    rule = proofs(after)[ask]["revision_4"]["best_asset_rule"]
    assert rule["consolidation_ask"] and not rule["fired"] and rule["demotion"] == 0
    assert rule["exception"] == "picks_to_rebuilding_or_tanking_team"
    assert proofs(after)[ask]["bilateral"] == proofs(before)[ask]["bilateral"]
    assert report.as_dict()["revision_4"]["best_asset_excepted"] == 1


def test_picks_for_best_player_to_a_contender_is_demoted():
    after, _ = r4.generate_bilateral_trades(**best_asset_world("contender", "PICK", 1600.))
    assert proofs(after)[(("g1", "g2"), ("star",))]["revision_4"]["best_asset_rule"]["fired"]


# ── R6: size, and the proof contract ──────────────────────────────────────

def test_organic_offers_stay_at_most_three_assets():
    args = world(own=("a", "b", "c"), other=("x", "y", "z"),
                 market={"a": 900., "b": 500., "c": 400., "x": 1000., "y": 600., "z": 300.},
                 viewer={"a": 700., "b": 400., "c": 300., "x": 1500., "y": 900., "z": 500.},
                 partner={"a": 1200., "b": 700., "c": 600., "x": 800., "y": 450., "z": 200.})
    cards, _ = r4.generate_bilateral_trades(**args)
    assert cards
    assert {(len(c.give_player_ids), len(c.receive_player_ids)) for c in cards} <= {(1, 1), (1, 2), (2, 1)}
    wide = ts.TradeCard("x", args["league"].league_id, "viewer", "partner", "Partner",
                        ["a", "b"], ["x", "y"], 0, 0, 0)
    assert r4.evaluate_bilateral_trade(wide, **args).reason == "organic_shape"


def test_revalidation_reproduces_every_frozen_proof():
    args = best_asset_world("contender", "WR", 1300.)
    cards, report = r4.generate_bilateral_trades(**args)
    assert report.as_dict()["generator_version"] == r4.VERSION
    for card, final in zip(cards, r4.evaluate_bilateral_trades(cards, **args)):
        assert final.eligible and final.matches(card)
        assert final.as_dict() == card.owner_evaluation.as_dict()
        assert final.model_identity == ("owner_v2_bilateral", "owner-v2-bilateral-4")


def test_presentment_reads_revision_4_proofs():
    cards, _ = r4.generate_bilateral_trades(**tie_world(1300.))
    _, diagnostics = presentment.present(cards, generator_version=r4.VERSION)
    assert diagnostics["eligible_count"] == len(cards)
    _, other = presentment.present(cards)  # The revision 2 default reads none of them.
    assert other["eligible_count"] == 0


# ── Selector composition and selector-off goldens ─────────────────────────

@pytest.mark.parametrize("cfg,expected", [
    ({}, "owner-v1"),
    ({KEY: 1.}, "owner-v1"),
    ({"owner_bilateral_enabled": 1., KEY: 1.}, "owner-v2-bilateral-1"),
    ({"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.}, "owner-v2-bilateral-2"),
    ({"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1., KEY: 1.}, "owner-v2-bilateral-4"),
    ({"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1., KEY: 1.,
      "owner_outlook_evidence_enabled": 1.}, "owner-v2-bilateral-4"),
    ({"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
      "owner_outlook_evidence_enabled": 1.}, "owner-v2-bilateral-3"),
] + [({"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
       "owner_outlook_evidence_enabled": v3, KEY: value},
      "owner-v2-bilateral-3" if v3 else "owner-v2-bilateral-2")
     for value in (0., .5, 2., -1., True + 1) for v3 in (0., 1.)])
def test_selector_composition(cfg, expected):
    assert bo.owner_version(cfg) == expected
    assert (bo.owner_generator(cfg).__module__.endswith("trade_gen_bilateral_r4")
            == (expected == "owner-v2-bilateral-4"))
    assert (bo.owner_evaluator(cfg).__module__.endswith("trade_gen_bilateral_r4")
            == (expected == "owner-v2-bilateral-4"))
    assert bo.owner_outlook_evidence_enabled(cfg) == (expected == "owner-v2-bilateral-3")


def test_selector_defaults_dark():
    from backend import database as db
    assert ts._DEFAULT_CFG[KEY] == 0
    assert next(v for k, v, _ in db._MODEL_CONFIG_DEFAULTS if k == KEY) == 0
    assert bo.owner_version() != r4.VERSION


def _digest(cards, report):
    encoded = [asdict(c) for c in cards]
    for card in encoded:
        for key in ("trade_id", "created_at", "expires_at"):
            card[key] = "variable-occurrence"
    report = report.as_dict()
    report.pop("elapsed_seconds", None)
    return hashlib.sha256(json.dumps([encoded, report], sort_keys=True, default=str).encode()).hexdigest()


# Computed from origin/main 6017d64b (before revision 4 existed) with the same
# worlds, configs and digest. A selector value other than exactly 1 must keep
# revisions 1 and 2 byte-identical, generator report included.
_GOLDEN = {
    ("r1", "favorable"): "75df37aebfa5c5ae3919cebb406376d7d1cc81e64f9f33cbbb04f3f0ae4f1b06",
    ("r1", "premium"): "13ccb66a8b8a08cc2e5aeccc3d658d4daf9a011c1ce859cd092844f52446ef05",
    ("r1", "best_asset"): "fc96d2f791a10a59cfd9d4169b1241821847599b1d51bcc976d9d3e86021560a",
    ("r2", "favorable"): "f595c2d8bed111f0a5ec13f8591cb84506992158070789e5159d7c13860e41c7",
    ("r2", "premium"): "3c6faf66ab6eddcba50e36aa6d4a4c3f2c3e3a3efa6cf40e4ce9b355a002f89f",
    ("r2", "best_asset"): "3c0f2e29ebaa1577a03c925dbb9f0d64278e1d31fc4767142d696823963ff511",
}
_BASES = {"r1": {"owner_bilateral_enabled": 1.},
          "r2": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.}}
_WORLDS = {"favorable": favorable, "premium": lambda: premium_world("rebuilder"),
           "best_asset": lambda: best_asset_world("contender", "WR", 1300.)}


@pytest.mark.parametrize("extra", [{}, {KEY: 0.}, {KEY: 2.}, {KEY: .5}, {KEY: -1.}],
                         ids=["absent", "zero", "two", "half", "negative"])
@pytest.mark.parametrize("revision,name", sorted(_GOLDEN))
def test_selector_off_is_byte_identical_to_main(revision, name, extra):
    base = _BASES[revision]
    cfg = dict(ts._DEFAULT_CFG, **base, **extra)
    cards, report = bo.owner_generator(cfg)(**_WORLDS[name](), config={**base, **extra})
    assert _digest(cards, report) == _GOLDEN[revision, name]
