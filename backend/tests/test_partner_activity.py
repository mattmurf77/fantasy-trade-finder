"""Revision 4's partner-activity rule (WS7, flag trade.partner_activity).

Synthetic leagues: these test ordering behaviour, not acceptance. Spec:
docs/plans/offer-learnings/plan.md §3 WS7; scope-partner-activity.md.
"""

from dataclasses import asdict
import copy
import hashlib
import json

import pytest

from backend import bakeoff_runner as bo, feature_flags as ff, server, trade_service as ts
from backend import trade_bilateral_presentment as presentment
from backend import trade_gen_bilateral_r4 as r4
from backend.tests.test_bilateral_contracts import Player, favorable, packages
from backend.tests.test_bilateral_revision_4 import best_asset_world, premium_world, tie_world
from backend.tests.test_owner_generator_routes import harness, owner_harness, context_for  # noqa: F401

KEY = "owner_bilateral_revision_4_enabled"
FLAG = "trade.partner_activity"


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def league_world(lead=1340., quiet_give=1300.):
    """Two partners, one comparable offer each; the offer to `quiet` leads in WS1.

    By default the offer to quiet leads by a margin inside the demotion, so a
    demoted quiet offer falls behind active's and an undemoted one leads.
    `lead` / `quiet_give` widen the margin on the viewer's / quiet's side.
    """
    ids = ("give", "qa", "ab")
    market = dict.fromkeys(ids, 1000.)
    players = {pid: Player(pid, pid, "WR", "TST", 26) for pid in ids}
    viewer = {"give": 800., "qa": lead, "ab": 1300.}
    partner = {"give": 1300., "qa": 800., "ab": 800.}
    boards = {"quiet": {**partner, "give": quiet_give}, "active": partner}
    members = [ts.LeagueMember(uid, uid.title(), [pid], {p: ts.value_to_elo(v) for p, v in boards[uid].items()},
                               True, confidence_sources=dict.fromkeys(partner, "explicit"))
               for uid, pid in (("quiet", "qa"), ("active", "ab"))]
    return dict(players=players,
                league=ts.League("synthetic_activity", "Synthetic", "sleeper", members),
                user_id="viewer", user_roster=["give"],
                seed_elo={pid: ts.value_to_elo(v) for pid, v in market.items()},
                user_elo={pid: ts.value_to_elo(v) for pid, v in viewer.items()},
                user_sources=dict.fromkeys(viewer, "explicit"),
                opponent_sources={uid: dict.fromkeys(partner, "explicit") for uid in ("quiet", "active")},
                outlook="not_sure", opponent_outlooks={"quiet": "contender", "active": "contender"},
                fairness_threshold=.75, scoring_format="1qb_ppr")


def targets(cards):
    return [c.target_user_id for c in cards]


def proof(cards, target):
    return next(c.owner_evaluation.as_dict() for c in cards if c.target_user_id == target)


def run(counts, **kwargs):
    args = league_world(**kwargs)
    before, _ = r4.generate_bilateral_trades(**args)
    after, report = r4.generate_bilateral_trades(**args, partner_activity=counts)
    return before, after, report.as_dict()


# ── The rule on constructed leagues ───────────────────────────────────────

def test_a_clear_non_trader_is_demoted_not_removed():
    before, after, report = run({"viewer": 4, "quiet": 0, "active": 4})
    assert targets(before) == ["quiet", "active"]
    assert targets(after) == ["active", "quiet"]
    assert packages(after) == packages(before)
    rule = proof(after, "quiet")["revision_4"]["partner_activity"]
    assert rule["fired"] and rule["counterparty_trades"] == 0 and rule["league_median"] == 4
    assert rule["threshold"] == pytest.approx(4 / 3) and rule["managers_with_profile"] == 3
    assert rule["demotion"] == r4.PARTNER_ACTIVITY_DEMOTION
    assert not proof(after, "active")["revision_4"]["partner_activity"]["fired"]
    old, new = proof(before, "quiet"), proof(after, "quiet")
    for side in ("viewer", "counterparty"):
        assert new[side]["support"]["score"] == pytest.approx(
            old[side]["support"]["score"] - r4.PARTNER_ACTIVITY_DEMOTION)
        assert new[side]["support"]["revision_4_adjustments"]["partner_activity_demotion"] == pytest.approx(
            -r4.PARTNER_ACTIVITY_DEMOTION)
    assert report["revision_4"]["partner_activity_demoted"] == 1
    assert report["revision_4"]["partner_activity"]["flagged_managers"] == 1


def test_demotion_moves_order_only_never_terms_or_eligibility():
    before, after, _ = run({"viewer": 4, "quiet": 0, "active": 4})
    old = {c.target_user_id: c.owner_evaluation.as_dict() for c in before}
    new = {c.target_user_id: c.owner_evaluation.as_dict() for c in after}
    for target in old:
        for field in ("market", "eligible", "reason", "term_efficiency", "direction"):
            assert new[target][field] == old[target][field]
        for side in ("viewer", "counterparty"):
            for field in ("market_gain_fraction", "utility", "team_plan_gain", "intent", "benefits"):
                assert new[target][side][field] == old[target][side][field]


@pytest.mark.parametrize("counts", [{"viewer": 4, "quiet": 3, "active": 4},
                                    {"viewer": 2, "quiet": 2, "active": 2}],
                         ids=["active_league", "flat_league"])
def test_a_league_where_everyone_trades_changes_nothing(counts):
    before, after, report = run(counts)
    assert targets(after) == targets(before)
    for target in ("quiet", "active"):
        old, new = proof(before, target), proof(after, target)
        assert new["bilateral"] == old["bilateral"]
        rule = new["revision_4"]["partner_activity"]
        assert not rule["fired"] and rule["reason_not_applied"] == "every_manager_active"
    assert report["revision_4"]["partner_activity"]["applies"] is False


@pytest.mark.parametrize("counts,reason", [
    ({"quiet": 0}, "league_history_thin"),                      # 1 of 3 managers profiled
    ({}, "league_history_thin"),
    ({"viewer": 1, "quiet": 0, "active": 1}, "league_median_below_minimum"),
], ids=["one_profile", "none", "low_median"])
def test_a_league_with_thin_history_changes_nothing(counts, reason):
    before, after, _ = run(counts)
    assert targets(after) == targets(before)
    rule = proof(after, "quiet")["revision_4"]["partner_activity"]
    assert not rule["fired"] and rule["reason_not_applied"] == reason and rule["threshold"] is None
    assert proof(after, "quiet")["bilateral"] == proof(before, "quiet")["bilateral"]


def test_a_manager_with_no_profile_is_never_flagged():
    before, after, _ = run({"viewer": 6, "active": 6})        # 2 of 3 profiled; quiet has none
    assert targets(after) == targets(before)
    rule = proof(after, "quiet")["revision_4"]["partner_activity"]
    assert not rule["fired"] and rule["counterparty_trades"] is None
    assert rule["counterparty_has_profile"] is False


def test_demotion_is_not_larger_than_the_best_asset_rule_and_clears_the_comparable_set():
    assert r4.PARTNER_ACTIVITY_DEMOTION <= r4.BEST_ASSET_DEMOTION
    assert r4.PARTNER_ACTIVITY_DEMOTION > r4.incumbent._QUALITY_TOLERANCE


def test_a_clearly_better_offer_to_a_non_trader_keeps_its_lead():
    # Quiet's offer leads on both sides by more than the demotion: order unchanged.
    before, after, _ = run({"viewer": 4, "quiet": 0, "active": 4}, lead=3000., quiet_give=4000.)
    gap = (proof(before, "quiet")["bilateral"]["weaker_support"]
           - proof(before, "active")["bilateral"]["weaker_support"])
    assert gap > r4.PARTNER_ACTIVITY_DEMOTION
    assert proof(after, "quiet")["revision_4"]["partner_activity"]["fired"]
    assert targets(after) == targets(before) == ["quiet", "active"]


def test_presentment_cannot_move_a_demoted_offer_back_up():
    _, after, _ = run({"viewer": 4, "quiet": 0, "active": 4})
    presented, diagnostics = presentment.present(after, generator_version=r4.VERSION)
    assert diagnostics["eligible_count"] == len(after)
    assert targets(presented) == ["active", "quiet"]


def test_revalidation_reproduces_every_frozen_proof():
    args = {**league_world(), "partner_activity": {"viewer": 4, "quiet": 0, "active": 4}}
    cards, _ = r4.generate_bilateral_trades(**args)
    for card, final in zip(cards, r4.evaluate_bilateral_trades(cards, **args)):
        assert final.eligible and final.matches(card)
        assert final.as_dict() == card.owner_evaluation.as_dict()


# ── Evidence: rules version and report ───────────────────────────────────

def test_rules_version_separates_graded_evidence():
    before, after, report = run({"viewer": 4, "quiet": 0, "active": 4})
    assert r4.RULES_VERSION_PARTNER_ACTIVITY != r4.RULES_VERSION == "offer-learnings-1"
    assert {proof(before, t)["revision_4"]["rules_version"] for t in ("quiet", "active")} == {r4.RULES_VERSION}
    assert "partner_activity" not in proof(before, "quiet")["revision_4"]
    assert {proof(after, t)["revision_4"]["rules_version"] for t in ("quiet", "active")} == {
        r4.RULES_VERSION_PARTNER_ACTIVITY}
    assert report["revision_4"]["rules_version"] == r4.RULES_VERSION_PARTNER_ACTIVITY
    summary = report["revision_4"]["partner_activity"]
    assert summary["league_median"] == 4 and summary["managers"] == 3
    assert "quiet" not in json.dumps(summary)   # Aggregates only, no manager ids.


def _digest(cards, report):
    encoded = [asdict(c) for c in cards]
    for card in encoded:
        for key in ("trade_id", "created_at", "expires_at"):
            card[key] = "variable-occurrence"
    report = report.as_dict()
    report.pop("elapsed_seconds", None)
    return hashlib.sha256(json.dumps([encoded, report], sort_keys=True, default=str).encode()).hexdigest()


# Computed with WS1's trade_gen_bilateral_r4.py (feat/offer-learnings 78a4aae0)
# on the same worlds and digest: with no partner_activity input revision 4's
# cards, proofs and report are WS1's bytes.
_WS1_GOLDEN = {
    "favorable": "baacb6dcfc0fd2f216a6e01a691208eceb2a3b03a29898cfecbefd409ec6ba96",
    "premium": "cfd2a736d577fb731d6a9c28d19da932c1a7620e6b2ab2d62f98c4088dd9cee0",
    "tie": "ee7a802c2a346e226d0bc6e8f76dfd6b3043c683610cd7e2d4a35ac51613543a",
    "best_asset": "634f3d68cafb9ac854ba24079238293a61f824014ccea454a221e1dd241769aa",
    "league": "6659885930c65a3882a8ed2249c64959b4ca3cc795165add0013fa10d983554f",
}
_WORLDS = {"favorable": favorable, "premium": lambda: premium_world("rebuilder"),
           "tie": lambda: tie_world(1300.), "best_asset": lambda: best_asset_world("contender", "WR", 1300.),
           "league": league_world}


@pytest.mark.parametrize("name", sorted(_WS1_GOLDEN))
def test_without_the_input_revision_4_is_byte_identical_to_ws1(name):
    cfg = {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1., KEY: 1.}
    cards, report = bo.owner_generator(cfg)(**_WORLDS[name](), config=cfg)
    assert _digest(cards, report) == _WS1_GOLDEN[name]


# ── Privacy: the public card ─────────────────────────────────────────────

def test_public_card_dict_is_unchanged_except_order():
    before, after, _ = run({"viewer": 4, "quiet": 0, "active": 4})
    players = league_world()["players"]
    def public(cards):
        out, ranks = [], []
        for card in cards:
            d = server.trade_card_to_dict(card, players)
            d.pop("trade_id"), d.pop("expires_at")
            # The constructor's rank encodings: a function of position only.
            ranks.append((d.pop("composite_score"), d.pop("mismatch_score")))
            out.append(json.dumps(d, sort_keys=True))
        return out, ranks
    assert targets(before) != targets(after)
    (old, old_ranks), (new, new_ranks) = public(before), public(after)
    assert sorted(old) == sorted(new) and old_ranks == new_ranks
    served = json.dumps([server.trade_card_to_dict(c, players) for c in after])
    for private in ("partner_activity", "counterparty_trades", "league_median", "revision_4"):
        assert private not in served


# ── The worker: context, flag and request hash ───────────────────────────

def _revision_4():
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    ts._cfg[KEY] = 1.


def test_flag_off_context_and_request_hash_carry_nothing(owner_harness, monkeypatch):
    _revision_4()
    calls = []
    monkeypatch.setattr(server, "load_manager_trade_counts", lambda lid: calls.append(lid) or {})
    context = context_for(owner_harness)
    assert "partner_activity" not in context and calls == []
    original = server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]
    ff._flags_cache[FLAG] = True
    on = context_for(owner_harness)
    assert on["partner_activity"] == {} and len(calls) == 1
    assert server._owner_selected_assignment(on, "fair_packages", serve=True)["request_hash"] != original
    del on["partner_activity"]   # The key is the only difference the flag makes.
    assert server._owner_selected_assignment(on, "fair_packages", serve=True)["request_hash"] == original


@pytest.mark.parametrize("cfg", [
    {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.},                  # revision 2
    {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
     "owner_outlook_evidence_enabled": 1.},                                                   # revision 3
    {"owner_bilateral_enabled": 1., KEY: 1.},                                                 # bilateral-1
    {KEY: 1.},                                                                                # owner-v1
], ids=["r2", "r3", "r1", "v1"])
def test_flag_on_without_revision_4_reads_nothing(owner_harness, monkeypatch, cfg):
    ts._cfg.update(cfg)
    ff._flags_cache[FLAG] = True
    calls = []
    monkeypatch.setattr(server, "load_manager_trade_counts", lambda lid: calls.append(lid) or {"x": 1})
    context = context_for(owner_harness)
    assert "partner_activity" not in context and calls == []
    cards, _ = bo.owner_generator(context["config"])(**context)    # No unexpected kwarg anywhere.
    assert server._owner_cards_valid(cards, context) == cards or not cards


def test_flag_on_revision_4_reads_once_and_validates(owner_harness, monkeypatch):
    _revision_4()
    ff._flags_cache[FLAG] = True
    _, _, sess, _, league = owner_harness
    calls = []
    counts = {m.user_id: 0 for m in league.members}
    monkeypatch.setattr(server, "load_manager_trade_counts", lambda lid: calls.append(lid) or dict(counts))
    context = context_for(owner_harness)
    assert calls == [league.league_id]
    cards, report = bo.owner_generator(context["config"])(**copy.deepcopy(context))
    assert cards and report.as_dict()["revision_4"]["rules_version"] == r4.RULES_VERSION_PARTNER_ACTIVITY
    assert server._owner_cards_valid(cards, context)


def test_trade_counts_come_from_the_stored_public_profiles(owner_harness):
    from backend import database as db
    db.replace_manager_profiles("pa-league", [
        {"league_id": "pa-league", "owner_id": owner, "roster_id": rid, "profile_version": 1,
         "computed_at": "2026-11-10T00:00:00+00:00", "n_trades": n, "last_trade_at": None,
         "n_waiver_bids": 0, "n_free_agent_adds": 0, "profile": "{}"}
        for rid, (owner, n) in enumerate((("u1", 0), ("u2", 5), ("u3", 2)), start=1)])
    assert db.load_manager_trade_counts("pa-league") == {"u1": 0, "u2": 5, "u3": 2}
    assert db.load_manager_trade_counts("other-league") == {}
