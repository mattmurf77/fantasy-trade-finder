"""Team overhaul — pure domain rules (backend/overhaul_service.py).

Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §8 minimum list.
Covers: E01 pool violation dropped incl. sweetener; E02 unused eligible
asset allowed; E03 pick-only give (all-in) and pick-only receive (rebuild);
E04/E05 recovery identity across two firsts + every state; E07 give overlap
is not independent; E08 same give set -> one package, tie explicit; E09
regrouping yields distinct diversity keys; E10 incoming collision rejected;
E11 shortfall reason under 4 packages; E12 position preference is soft;
E15 union capacity arithmetic + every-single-passes/union-fails fixture;
D4 tier duplicate counterparty; attempt state machine; ownership reconcile.
No Flask, no DB.
"""
from types import SimpleNamespace

import pytest

from backend import overhaul_service as svc

POOL = ["A", "B", "C", "D", "E"]


def _offer(oid, give, recv, cp, *, decision="like", availability="fresh", score=0.9, is_recovery=False):
    return {"offer_id": oid, "give_ids": list(give), "receive_ids": list(recv), "counterparty_user_id": cp,
            "decision": decision, "availability": availability, "score": score, "is_recovery": is_recovery}


def _card(give, recv, cp="o1"):
    return SimpleNamespace(give_player_ids=list(give), receive_player_ids=list(recv), target_user_id=cp)


def _is_pick(a):
    return str(a).startswith("L1_") or svc.is_generic_pick(a)


FOUR = [_offer("o_a", ["A"], ["X1"], "o1"), _offer("o_b", ["B"], ["X2"], "o2"),
        _offer("o_c", ["C"], ["X3"], "o3"), _offer("o_d", ["D"], ["X4"], "o4")]


# ── E01 / E02 ───────────────────────────────────────────────────────────────

def test_e01_pool_violation_dropped_including_sweetener():
    """A card whose give set escapes the pool is dropped and counted, even
    when the escape is a single sweetener riding alongside pool assets.
    SABOTAGE: make card_passes_pool check `set(give) & pool` instead of `<=`.
    """
    cards = [_card(["A"], ["X1"]), _card(["A", "F"], ["X1"]), _card(["F"], ["X1"]),
             _card(["A"], ["generic_pick_1_early"]), _card([], ["X1"]), _card(["A"], ["X1"], cp="me")]
    kept, rejected = svc.filter_cards(cards, pool=POOL, seller_user_id="me")
    assert [c.give_player_ids for c in kept] == [["A"]]
    assert rejected == 5


def test_e02_unused_eligible_asset_is_allowed_and_reported():
    roadmaps, shortfall = svc.assemble_roadmaps(FOUR, pool=POOL, target_package_count=4)
    assert shortfall is None and len(roadmaps) == 1
    assert roadmaps[0]["summary"]["unused_eligible_ids"] == ["E"]
    assert sorted(roadmaps[0]["summary"]["outgoing_ids"]) == ["A", "B", "C", "D"]


# ── E03 ─────────────────────────────────────────────────────────────────────

def test_e03_pick_only_give_and_pick_only_receive():
    pool = ["P1", "L1_2027_1_3", "L1_2028_2_3"]
    meta = {"L1_2027_1_3": {"round": 1, "season": 2027}, "L1_2028_2_3": {"round": 2, "season": 2028}}
    subsets = svc.enumerate_subsets(pool, values={"P1": 900, "L1_2027_1_3": 800, "L1_2028_2_3": 300},
                                    outlook="push_all_in", is_pick=_is_pick,
                                    pick_budget={"max_picks": 2, "max_round": 2, "seasons": [2027, 2028]},
                                    pick_meta=meta)
    assert ("L1_2027_1_3", "L1_2028_2_3") in subsets          # pick-only package exists
    # Budget: round cap excludes the 2028 2nd when max_round is 1.
    tight = svc.enumerate_subsets(pool, values={}, outlook="push_all_in", is_pick=_is_pick,
                                  pick_budget={"max_picks": 2, "max_round": 1, "seasons": None}, pick_meta=meta)
    assert all("L1_2028_2_3" not in s for s in tight)
    # Rebuild `picks` return: receive side must carry a pick; `mixed` never filters.
    assert svc.receive_side_allowed(["L1_2027_1_5"], outlook="blow_it_up", rebuild_return="picks", is_pick=_is_pick)
    assert not svc.receive_side_allowed(["X9"], outlook="blow_it_up", rebuild_return="picks", is_pick=_is_pick)
    assert svc.receive_side_allowed(["X9"], outlook="blow_it_up", rebuild_return="mixed", is_pick=_is_pick)


# ── E04 / E05 recovery identity ─────────────────────────────────────────────

def _row(pick_id, season, rnd, orig_user, orig_roster, owner, owner_name=None):
    return {"pick_id": pick_id, "season": season, "round": rnd, "original_user_id": orig_user,
            "original_roster_id": orig_roster, "owner_user_id": owner, "owner_username": owner_name}


def test_e04_two_firsts_resolve_to_my_original_roster_only():
    """I hold someone else's 2027 first and they hold mine: recovery names MY
    original pick and its holder, never the first I already own.
    SABOTAGE: match on owner_user_id instead of original_user_id.
    """
    rows = [_row("L1_2027_1_3", 2027, 1, "me", "3", "them", "Them"),   # mine, held by them
            _row("L1_2027_1_7", 2027, 1, "them", "7", "me", "Me")]     # theirs, held by me
    rec = svc.recovery_requirement(outlook="blow_it_up", season=2026, picks=rows, my_user_id="me", my_roster_id=3)
    assert rec["applicable"] and rec["season"] == 2027
    assert rec["state"] == "missing_with_known_holder"
    assert rec["pick_id"] == "L1_2027_1_3" and rec["holder_user_id"] == "them" and rec["holder_username"] == "Them"
    assert rec["draft_order_rule"] == "unknown" and rec["resolved"] is False


def test_e05_recovery_states():
    mine = [_row("L1_2027_1_3", 2027, 1, "me", "3", "me")]
    assert svc.recovery_requirement(outlook="blow_it_up", season=2026, picks=mine, my_user_id="me")["state"] == "owned"
    assert svc.recovery_requirement(outlook="blow_it_up", season=2026, picks=[], my_user_id="me")["state"] == "unknown"
    only_2026 = [_row("L1_2026_1_3", 2026, 1, "me", "3", "me")]
    assert svc.recovery_requirement(outlook="blow_it_up", season=2026, picks=only_2026, my_user_id="me")["state"] == "not_yet_available"
    assert svc.recovery_requirement(outlook="blow_it_up", season=2026, picks=mine, my_user_id="me",
                                    picks_supported=False)["state"] == "unsupported"
    # Not applicable for push_all_in, but the identity is still reported.
    rec = svc.recovery_requirement(outlook="push_all_in", season=2026, picks=mine, my_user_id="me")
    assert rec["applicable"] is False and rec["state"] == "owned"


# ── E07 / E08 / E09 / E10 / E11 ─────────────────────────────────────────────

def test_e07_give_overlap_is_not_independent():
    offers = [_offer("ab", ["A", "B"], ["X1"], "o1"), _offer("a", ["A"], ["X2"], "o2"),
              _offer("c", ["C"], ["X3"], "o3"), _offer("d", ["D"], ["X4"], "o4")]
    roadmaps, shortfall = svc.assemble_roadmaps(offers, pool=POOL, target_package_count=4)
    # A+B and A cannot coexist, so only three give-disjoint packages exist.
    assert roadmaps == [] and shortfall["reason"] == "overlapping_sells"
    # prepare-send says the same thing about a hand-picked overlap.
    packages = [{"package_id": "p1", "give_ids": ["A", "B"], "tiers": [{"tier": 1, "offer_ids": ["ab"]}]},
                {"package_id": "p2", "give_ids": ["A"], "tiers": [{"tier": 1, "offer_ids": ["a"]}]}]
    receipt = svc.validate_prepare(selected=["ab", "a"], packages=packages, offers_by_id={o["offer_id"]: o for o in offers},
                                   my_roster_ids=POOL, my_pick_ids=[], pool=POOL, rosters={"o1": ["X1"], "o2": ["X2"]},
                                   reserved_asset_ids=[], capacity=None, recovery=None, package_states={},
                                   checked_at="t", is_pick=_is_pick)
    assert not receipt["ok"] and "give_overlap" in {b["code"] for b in receipt["blockers"]}


def test_e08_same_give_set_is_one_package_and_ties_are_explicit():
    offers = FOUR + [_offer("o_a2", ["A"], ["X9"], "o9", score=0.8)]
    roadmaps, _ = svc.assemble_roadmaps(offers, pool=POOL, target_package_count=4)
    pkg = next(p for p in roadmaps[0]["packages"] if p["give_ids"] == ["A"])
    # Initial state: one alternative per tier, server rank order (best first).
    assert pkg["tiers"] == [{"tier": 1, "offer_ids": ["o_a"]}, {"tier": 2, "offer_ids": ["o_a2"]}]
    # A tie is a deliberate user action and is accepted when counterparties differ.
    by_id = {o["offer_id"]: o for o in offers}
    tied = svc.validate_priorities(pkg, [{"tier": 1, "offer_ids": ["o_a", "o_a2"]}], by_id)
    assert tied == [{"tier": 1, "offer_ids": ["o_a", "o_a2"]}]
    assert svc.races(["o_a", "o_a2", "o_b"], roadmaps[0]["packages"]) == [{"package_id": pkg["package_id"], "offer_ids": ["o_a", "o_a2"]}]


def test_e09_regrouping_produces_materially_distinct_roadmaps():
    offers = FOUR + [_offer("o_ab", ["A", "B"], ["X7"], "o7"), _offer("o_e", ["E"], ["X5"], "o5")]
    roadmaps, shortfall = svc.assemble_roadmaps(offers, pool=POOL, target_package_count=4)
    assert shortfall is None and 2 <= len(roadmaps) <= svc.OVERHAUL_MAX_ROADMAPS
    keys = [r["summary"]["diversity_key"] for r in roadmaps]
    assert len(keys) == len(set(keys))
    assert any("A,B" in k for k in keys) and any("A|" in k or k.startswith("A|") for k in keys)
    assert [r["rank"] for r in roadmaps] == list(range(1, len(roadmaps) + 1))


def test_e10_incoming_collision_rejected():
    offers = [_offer("o_a", ["A"], ["X1"], "o1"), _offer("o_b", ["B"], ["X1"], "o1"),
              _offer("o_c", ["C"], ["X3"], "o3"), _offer("o_d", ["D"], ["X4"], "o4")]
    roadmaps, shortfall = svc.assemble_roadmaps(offers, pool=POOL, target_package_count=4)
    assert roadmaps == [] and shortfall["reason"] == "competing_incoming"
    # And the receipt names it when a user hand-picks the collision.
    packages = [{"package_id": "p1", "give_ids": ["A"], "tiers": [{"tier": 1, "offer_ids": ["o_a"]}]},
                {"package_id": "p2", "give_ids": ["B"], "tiers": [{"tier": 1, "offer_ids": ["o_b"]}]}]
    receipt = svc.validate_prepare(selected=["o_a", "o_b"], packages=packages, offers_by_id={o["offer_id"]: o for o in offers},
                                   my_roster_ids=POOL, my_pick_ids=[], pool=POOL, rosters={"o1": ["X1"]},
                                   reserved_asset_ids=[], capacity=None, recovery=None, package_states={},
                                   checked_at="t", is_pick=_is_pick)
    assert "receive_overlap" in {b["code"] for b in receipt["blockers"]}


def test_e11_shortfall_reason_under_four_packages():
    assert svc.assemble_roadmaps([], pool=POOL)[1]["reason"] == "insufficient_likes"
    two = FOUR[:2]
    assert svc.assemble_roadmaps(two, pool=POOL)[1]["reason"] == "insufficient_likes"
    passed = [dict(o, decision="pass") for o in FOUR]
    assert svc.assemble_roadmaps(passed, pool=POOL)[1]["reason"] == "insufficient_likes"
    stale = [dict(o, availability="stale") for o in FOUR]
    assert svc.assemble_roadmaps(stale, pool=POOL)[1]["reason"] == "stale_ownership"
    # Liked offers outside the pool never pad a roadmap (invariant 10).
    outside = FOUR + [_offer("o_f", ["F"], ["X6"], "o6")]
    roadmaps, _ = svc.assemble_roadmaps(outside, pool=POOL, target_package_count=5)
    assert all("F" not in p["give_ids"] for r in roadmaps for p in r["packages"])


# ── E12 / E15 / D4 ──────────────────────────────────────────────────────────

def test_e12_position_preference_is_soft():
    settings = svc.merge_settings(svc.default_settings(), {"preferred_positions": ["wr"]}, owned_ids=POOL)
    assert settings["preferred_positions"] == ["WR"]
    # Assembly never consults preferred positions: RB-returning offers still assemble.
    roadmaps, shortfall = svc.assemble_roadmaps(FOUR, pool=POOL, target_package_count=4)
    assert shortfall is None and len(roadmaps[0]["packages"]) == 4


def test_e15_union_capacity_every_single_passes_but_union_fails():
    """Roster 20/22: each package nets +1 (21 <= 22 alone) but four together
    reach 24 > 22. SABOTAGE: sum only the max single package net gain."""
    alts = [[(["A"], ["X1", "Y1"])], [(["B"], ["X2", "Y2"])], [(["C"], ["X3", "Y3"])], [(["D"], ["X4", "Y4"])]]
    for pkg in alts:
        assert svc.union_capacity_worst_case(20, [pkg], is_pick=_is_pick) == 21
    assert svc.union_capacity_worst_case(20, alts, is_pick=_is_pick) == 24
    # Picks cost no slot: one player out, one player + one pick in nets 0, not +1.
    assert svc.union_capacity_worst_case(20, [[(["A"], ["X1", "L1_2027_1_3"])]], is_pick=_is_pick) == 20
    assert svc.union_capacity_worst_case(20, [[(["L1_2027_1_3"], ["X1"])]], is_pick=_is_pick) == 21
    offers = [_offer("o_a", ["A"], ["X1", "Y1"], "o1"), _offer("o_b", ["B"], ["X2", "Y2"], "o2"),
              _offer("o_c", ["C"], ["X3", "Y3"], "o3"), _offer("o_d", ["D"], ["X4", "Y4"], "o4")]
    packages = [{"package_id": f"p{o['offer_id']}", "give_ids": o["give_ids"],
                 "tiers": [{"tier": 1, "offer_ids": [o["offer_id"]]}]} for o in offers]
    roster = [f"R{i}" for i in range(16)] + ["A", "B", "C", "D"]
    rosters = {o["counterparty_user_id"]: o["receive_ids"] for o in offers}
    receipt = svc.validate_prepare(selected=[o["offer_id"] for o in offers], packages=packages,
                                   offers_by_id={o["offer_id"]: o for o in offers}, my_roster_ids=roster,
                                   my_pick_ids=[], pool=POOL, rosters=rosters, reserved_asset_ids=[], capacity=22,
                                   recovery=None, package_states={}, checked_at="t", is_pick=_is_pick)
    assert [b["code"] for b in receipt["blockers"]] == ["capacity_exceeded"]
    single = svc.validate_prepare(selected=["o_a"], packages=packages, offers_by_id={o["offer_id"]: o for o in offers},
                                  my_roster_ids=roster, my_pick_ids=[], pool=POOL, rosters=rosters,
                                  reserved_asset_ids=[], capacity=22, recovery=None, package_states={},
                                  checked_at="t", is_pick=_is_pick)
    assert single["ok"]
    unknown = svc.validate_prepare(selected=["o_a"], packages=packages, offers_by_id={o["offer_id"]: o for o in offers},
                                   my_roster_ids=roster, my_pick_ids=[], pool=POOL, rosters=rosters,
                                   reserved_asset_ids=[], capacity=None, recovery=None, package_states={},
                                   checked_at="t", is_pick=_is_pick)
    assert unknown["ok"] and unknown["unknowns"] == ["capacity_unknown"]


def test_d4_tier_duplicate_counterparty_rejected():
    offers = [_offer("o_a", ["A"], ["X1"], "o1"), _offer("o_a2", ["A"], ["X2"], "o1")]
    by_id = {o["offer_id"]: o for o in offers}
    pkg = {"package_id": "p1", "give_ids": ["A"], "tiers": [{"tier": 1, "offer_ids": ["o_a"]}, {"tier": 2, "offer_ids": ["o_a2"]}]}
    with pytest.raises(svc.ValidationError) as exc:
        svc.validate_priorities(pkg, [{"tier": 1, "offer_ids": ["o_a", "o_a2"]}], by_id)
    assert exc.value.code == "tier_duplicate_counterparty"
    # Separate tiers with the same counterparty are fine; gaps and omissions are not.
    assert svc.validate_priorities(pkg, [{"tier": 1, "offer_ids": ["o_a2"]}, {"tier": 2, "offer_ids": ["o_a"]}], by_id)
    for bad in ([{"tier": 2, "offer_ids": ["o_a"]}], [{"tier": 1, "offer_ids": ["o_a"]}],
                [{"tier": 1, "offer_ids": ["o_a", "zz"]}]):
        with pytest.raises(svc.ValidationError):
            svc.validate_priorities(pkg, bad, by_id)


# ── prepare-send blockers, state machine, reconcile ─────────────────────────

def test_prepare_blockers_for_ownership_pool_reservation_and_pending_package():
    offers = FOUR + [_offer("o_pass", ["E"], ["X5"], "o5", decision="pass")]
    by_id = {o["offer_id"]: o for o in offers}
    packages = [{"package_id": f"p{o['offer_id']}", "give_ids": o["give_ids"],
                 "tiers": [{"tier": 1, "offer_ids": [o["offer_id"]]}]} for o in offers]
    receipt = svc.validate_prepare(selected=["o_a", "o_b", "o_c", "o_d", "o_pass"], packages=packages, offers_by_id=by_id,
                                   my_roster_ids=["B", "C", "D", "E"], my_pick_ids=[], pool=["A", "B", "D", "E"],
                                   rosters={"o1": ["X1"], "o2": [], "o3": ["X3"], "o4": ["X4"], "o5": ["X5"]},
                                   reserved_asset_ids=["D"], capacity=None,
                                   recovery={"applicable": True, "state": "missing_with_known_holder"},
                                   package_states={"po_b": "pending"}, checked_at="t", is_pick=_is_pick)
    codes = {(b["code"], b.get("offer_id")) for b in receipt["blockers"]}
    assert ("asset_not_owned", "o_a") in codes
    assert ("pool_violation", "o_c") in codes
    assert ("asset_reserved", "o_d") in codes
    assert ("asset_reserved", "o_b") in codes                      # pending package holds later sends (D5)
    assert ("counterparty_asset_not_owned", "o_b") in codes
    assert ("offer_not_liked", "o_pass") in codes
    assert [w["code"] for w in receipt["warnings"]] == ["recovery_unresolved"]   # advisory, never blocking


def test_attempt_state_machine_never_regresses_terminal_states():
    assert svc.can_transition("queued", "sending") and svc.can_transition("sending", "proposed")
    assert svc.can_transition("proposed", "accepted") and svc.can_transition("outcome_unknown", "declined")
    for terminal in ("accepted", "declined", "expired", "withdrawn", "invalidated", "resolved_elsewhere", "send_failed"):
        assert not svc.can_transition(terminal, "proposed")
        assert not svc.can_transition(terminal, "queued")
    assert set(svc.ATTEMPT_STATES) >= svc.LIVE_ATTEMPT_STATES | svc.USER_REPORTABLE_STATES


def test_reconcile_attempt_from_ownership():
    offer = {"give_ids": ["A"], "receive_ids": ["X1"]}
    assert svc.reconcile_attempt(offer, my_assets=["B", "X1"]) == "accepted"
    assert svc.reconcile_attempt(offer, my_assets=["B"]) == "resolved_elsewhere"
    assert svc.reconcile_attempt(offer, my_assets=["A", "B"]) is None
    assert svc.reconcile_attempt(offer, my_assets=["A", "X1"]) is None   # both sides present: unchanged


def test_reconcile_attempt_never_terminalizes_on_picks_without_a_live_read():
    """Finding 1: the pick table lags the platform. A pick-only un-arrived
    receive side is `accepted` only when a live holder read confirms it and
    otherwise leaves the attempt alone; a player that did not arrive is still
    live evidence of `resolved_elsewhere`.
    SABOTAGE: ignore `is_pick` / `live_pick_holder` in reconcile_attempt."""
    pick = "L1_2027_1_2"
    offer = {"give_ids": ["A"], "receive_ids": [pick]}
    assert svc.reconcile_attempt(offer, my_assets=["B"], is_pick=_is_pick) is None
    assert svc.reconcile_attempt(offer, my_assets=["B"], is_pick=_is_pick, live_pick_holder=lambda a: False) is None
    assert svc.reconcile_attempt(offer, my_assets=["B"], is_pick=_is_pick, live_pick_holder=lambda a: True) == "accepted"
    assert svc.reconcile_attempt(offer, my_assets=["B", pick], is_pick=_is_pick) == "accepted"
    mixed = {"give_ids": ["A"], "receive_ids": ["X1", pick]}
    assert svc.reconcile_attempt(mixed, my_assets=["B", "X1"], is_pick=_is_pick) is None
    assert svc.reconcile_attempt(mixed, my_assets=["B"], is_pick=_is_pick, live_pick_holder=lambda a: True) == "resolved_elsewhere"
    # Without an is_pick predicate the legacy player-only rule holds.
    assert svc.reconcile_attempt(offer, my_assets=["B"]) == "resolved_elsewhere"


def test_stuck_live_attempts_sweep_and_transitions_are_legal():
    """Finding 2: sending -> outcome_unknown and queued -> stale after 5 min."""
    assert svc.stuck_outcome("sending", svc.LIVE_STUCK_AFTER_S) == "outcome_unknown"
    assert svc.stuck_outcome("queued", svc.LIVE_STUCK_AFTER_S + 1) == "stale"
    assert svc.stuck_outcome("sending", svc.LIVE_STUCK_AFTER_S - 1) is None
    assert svc.stuck_outcome("proposed", 10_000) is None
    assert svc.can_transition("sending", "outcome_unknown") and svc.can_transition("queued", "stale")


def test_pick_budget_defaults_missing_bounds():
    """Finding 6: a partial pick_budget defaults max_round=3, seasons=[]."""
    out = svc.merge_settings(svc.default_settings(), {"pick_budget": {"max_picks": 2}}, owned_ids=POOL)
    assert out["pick_budget"] == {"max_picks": 2, "max_round": 3, "seasons": []}
    out = svc.merge_settings(svc.default_settings(), {"pick_budget": {"max_round": 1, "seasons": [2027]}}, owned_ids=POOL)
    assert out["pick_budget"] == {"max_picks": None, "max_round": 1, "seasons": [2027]}
    assert svc.merge_settings(svc.default_settings(), {"pick_budget": None}, owned_ids=POOL)["pick_budget"] is None


def test_settings_validation_and_stale_rule():
    with pytest.raises(svc.ValidationError) as exc:
        svc.merge_settings(svc.default_settings(), {"eligible_asset_ids": ["Z"]}, owned_ids=POOL)
    assert exc.value.code == "asset_not_owned"
    with pytest.raises(svc.ValidationError) as exc:
        svc.merge_settings(svc.default_settings(), {"eligible_asset_ids": ["generic_pick_1_early"]}, owned_ids=POOL)
    assert exc.value.code == "generic_pick_not_allowed"
    with pytest.raises(svc.ValidationError):
        svc.merge_settings(svc.default_settings(), {"outlook": "balanced"}, owned_ids=POOL)
    before = svc.merge_settings(svc.default_settings(), {"outlook": "blow_it_up", "eligible_asset_ids": ["A", "B"]}, owned_ids=POOL)
    same = svc.merge_settings(before, {"preferred_positions": ["RB"]}, owned_ids=POOL)
    assert not svc.settings_invalidate_offers(before, same)
    assert svc.settings_invalidate_offers(before, svc.merge_settings(before, {"eligible_asset_ids": ["A"]}, owned_ids=POOL))
    assert svc.settings_invalidate_offers(before, svc.merge_settings(before, {"outlook": "push_all_in"}, owned_ids=POOL))


def test_recommendations_are_outlook_specific():
    assets = [{"id": "q1", "kind": "player", "position": "QB", "value": 900, "age": 30},
              {"id": "r1", "kind": "player", "position": "RB", "value": 800, "age": 24},
              {"id": "r2", "kind": "player", "position": "RB", "value": 700, "age": 28},
              {"id": "r3", "kind": "player", "position": "RB", "value": 100, "age": 22},
              {"id": "L1_2027_1_3", "kind": "pick", "position": "PICK", "value": 500}]
    blow = svc.recommend_assets([dict(a) for a in assets], outlook="blow_it_up")
    assert {a["id"] for a in blow if a["recommended"]} == {"q1", "r2"}          # aging starters only
    allin = svc.recommend_assets([dict(a) for a in assets], outlook="push_all_in",
                                 pick_budget={"max_round": 1}, pick_meta={"L1_2027_1_3": {"round": 1}})
    assert {a["id"] for a in allin if a["recommended"]} == {"r3", "L1_2027_1_3"}  # bench depth + budget picks
    assert not any(a["recommended"] for a in svc.recommend_assets([dict(a) for a in assets], outlook=None))


def test_reconcile_attempt_refuses_a_non_fresh_roster_source():
    """All-platform sends (2026-09-07): a session-sourced roster is never
    evidence, however conclusive it looks."""
    offer = {"give_ids": ["A"], "receive_ids": ["X1"]}
    assert svc.reconcile_attempt(offer, my_assets=["B", "X1"], roster_fresh=False) is None
    assert svc.reconcile_attempt(offer, my_assets=["B"], roster_fresh=False) is None
    assert svc.reconcile_attempt(offer, my_assets=["B", "X1"], roster_fresh=True) == "accepted"


def test_platform_blockers_and_handoff_mode():
    is_pick = lambda a: a.startswith("L1_")
    packages = [{"package_id": "pk_1", "tiers": [{"tier": 1, "offer_ids": ["o1", "o2"]}]}]
    offers = {"o1": {"give_ids": ["A"], "receive_ids": ["L1_2027_1_2"]}, "o2": {"give_ids": ["B"], "receive_ids": ["X"]}}
    common = dict(selected=["o1", "o2"], packages=packages, offers_by_id=offers, is_pick=is_pick)
    assert svc.handoff_mode("sleeper") == svc.handoff_mode("mfl") == svc.handoff_mode("espn") == "send"
    assert svc.handoff_mode("fleaflicker") == svc.handoff_mode(None) == "copy"
    # Copy platforms: nothing to block, whatever the auth state.
    assert svc.platform_blockers(platform="fleaflicker", auth_state="n/a", picks_sendable=False, **common) == []
    # ESPN: the pick offer is named; the players-only one passes.
    got = svc.platform_blockers(platform="espn", auth_state="linked", picks_sendable=False, **common)
    assert [(b["code"], b["package_id"], b["offer_id"]) for b in got] == [("pick_unsupported_on_platform", "pk_1", "o1")]
    # MFL carries picks; an unlinked user gets exactly one reconnect blocker naming the platform.
    got = svc.platform_blockers(platform="mfl", auth_state="unlinked", picks_sendable=True, **common)
    assert [b["code"] for b in got] == ["reconnect_required"] and "MFL" in got[0]["message"]
    assert svc.platform_blockers(platform="mfl", auth_state="linked", picks_sendable=True, **common) == []
    receipt = svc.with_blockers({"ok": True, "blockers": []}, got)
    assert receipt["ok"] is False and receipt["blockers"] == got
    assert svc.with_blockers({"ok": True, "blockers": []}, [])["ok"] is True
    assert {"pick_unsupported_on_platform", "reconnect_required"} <= set(svc.VALIDATION_CODES)
