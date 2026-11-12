"""Bilateral revision 5 (owner-v2-bilateral-5): revision 2 plus the win-now season signal.

Spec: docs/plans/win-now-season-signal/lld.md §3 (revision 5), §4 (proof fields),
§10 invariants I2-I9; build-plan.md WI-2; PRD §1, §2, §5, §7, acceptance criteria 2-9, 13, 14.

World: the WI-1 fixture league (`fixtures/season-signal/league-12.json`, public NFL
players, synthetic owners and picks) with DynastyProcess 1QB values as consensus, seeded
noisy boards (the viewer and four league-mates), and the real capture over the
committed Sleeper projections (`test_season_points.captured_snapshot`) viewed at capture
time. Boards and people are synthetic: these test engine behaviour, not acceptance.
No network, no database.

Covered (each proven red against the named sabotage, then green on revert):
- I2  test_without_usable_evidence_revision_5_is_revision_2 (absent and unavailable
      evidence). Sabotage: let `_lineup` use season assets when state != "usable".
- I3  test_not_sure_viewer_with_usable_evidence_is_revision_2. Sabotage: add
      "not_sure" to the scored outlooks.
- I4  test_rebuilding_and_tanking_viewers_keep_inventory_and_terms. Sabotage: score
      a rebuilder's lineup in points.
- I5  test_equal_value_equal_age_starter_beats_backup_for_all_in. Sabotage: read the
      label table with `starts_for` always true.
- I6  test_non_starter_plan_lean_equals_a_picks. Sabotage: give non-starters 0.0.
- I7  test_conflict_penalty_never_changes_the_inventory. Sabotage: apply the penalty
      before `utility` is computed.
- I8  test_pinned_search_records_no_conflict. Sabotage: drop the pin precondition.
- I9  test_shared_cards_keep_revision_2_terms_floor_and_fairness. Sabotage: price a
      package with RATE x ppg.
- test_operators_card_is_flagged_kept_and_below_its_twin. Sabotage: skip the penalty
  for `personal_board`.
- test_target_list_card_is_flagged_not_demoted. Sabotage: demote every flagged card.
- test_each_declared_kind_comes_from_its_own_input_flagged_not_demoted (target,
  trade_block, position, trade_away). Sabotages: file a trade-block match under
  "position"; name the incoming asset for "trade_block"; demote "trade_block".
- test_declared_kind_precedence. Sabotage: check acquire positions before the trade block.
- test_candidate_seats_for_starters_and_for_future_value. Sabotage: leave `_pool` untouched.
- test_stage_2_off_partners_plan_and_lineup_are_revision_2s. Sabotage: read the label
  table for partners unconditionally.
- test_other_revisions_unchanged_with_the_new_knobs_present (revision 1/2 goldens of
  test_bilateral_revision_4, the dark keys dropped from search config). Sabotage: leave
  a season key in `search.config` when revision 5 is not selected.
- test_proof_carries_plan_fit_and_lineup_gain_separately. Sabotage: store only `team_plan`.
- Amended 2026-11-11 (operator direction: Rebuilding / Tanking are season-scored in the
  shed direction, order only):
  - I4 (restated) test_rebuilding_and_tanking_viewers_keep_inventory_and_terms: same
    inventory and terms, the order differs. Sabotage: let the shed term qualify a card
    (add it to `team_plan_gain` and `utility` in `_owner`).
  - test_no_gate_changes_for_rebuilding_and_tanking: every candidate's verdict and reason
    equal revision 2's, Tanking's two hard rules among them. Same sabotage.
  - test_tanking_and_rebuilding_shed_lineup_points_in_the_first_30. Sabotages: sign not
    reversed; equal weights (Rebuilding at 1.0).
  - test_a_point_shed_by_tanking_weighs_what_a_point_gained_weighs_for_all_in.
    Sabotage: a different scale (RATE / 2).
  - test_shed_scored_viewer_proof. Sabotage: record `season_direction` "add".
  - test_inferred_rebuilding_roster_is_scored_and_never_flagged. Sabotage: drop the
    `declared` precondition of `plan_conflict`.
- Stage 2, two win-now teams (Part B): test_stage_2_win_now_pair_trade_on_a_ranking_
  discrepancy, test_stage_2_win_now_pair_trade_on_complementary_needs (what the code
  as built does; no sabotage: they describe, they do not guard a change).
- test_all_in_headline_direction_on_the_fixture (planner's headline, stated tolerance).
- Also: selector composition and defaults, presentment version, revalidation, stage 2 runs.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import random
import statistics

import pytest

from backend import bakeoff_runner as bo, database as db, deck_quality, feature_flags as ff
from backend import season_value as sv, trade_service as ts
from backend import trade_bilateral_presentment as presentment
from backend import trade_gen_bilateral as r1
from backend import trade_gen_bilateral_candidate as r2
from backend import trade_gen_bilateral_r4 as r4
from backend import trade_gen_bilateral_season as r5
from backend.league_projections.core import VERSION as MODEL_VERSION
from backend.ranking_service import Player
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, captured_snapshot, load_league, load_pool

KEY = "owner_bilateral_revision_5_enabled"
LEAGUE, POOL = load_league(), load_pool()
SLOTS = LEAGUE["slots"]
OPPONENT_OUTLOOKS = ["contender", "rebuilder", "not_sure", "championship", "jets"]
BY_NAME = {POOL[pid]["full_name"]: pid for team in LEAGUE["teams"] for pid in team["players"]}
ADAMS = BY_NAME["Davante Adams"]


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


@lru_cache(maxsize=None)
def _evidence():
    return sv.build_evidence(captured_snapshot(), as_of=CAPTURED_AT, league_id=LEAGUE_ID, slots=SLOTS,
                             platform="sleeper", run_id="run-1", model_version=MODEL_VERSION, current=True)


def evidence():
    return deepcopy(_evidence())


def world(outlook, *, neutral_board=False, seed=0):
    """Generator kwargs for the fixture league; the viewer ("me") holds Davante Adams."""
    rng = random.Random(seed)
    players, values = {}, {}
    for team in LEAGUE["teams"]:
        for pid in team["players"]:
            row = POOL[pid]
            age = row["age"] or (22 if (row.get("years_exp") or 0) == 0 else None)
            players[pid] = Player(pid, row["full_name"], row["position"], row.get("team") or "FA", age,
                                  depth_chart_order=row.get("depth_chart_order"))
            values[pid] = float(row["dp_value_1qb"])
        for pid, value in team["picks"].items():
            players[pid] = Player(pid, pid, "PICK", "PICK", None)
            values[pid] = float(value)
    ids = sorted(values)
    seed_elo = {p: ts.value_to_elo(v) for p, v in values.items()}

    def board(noise):
        return {p: ts.value_to_elo(max(30., values[p] * rng.lognormvariate(0, noise))) for p in ids}

    user_elo = board(.3)
    members, outlooks = [], {}
    for index, team in enumerate(LEAGUE["teams"][1:]):
        ranked = index < 4
        members.append(ts.LeagueMember(team["owner_id"], team["owner_id"], team["players"] + list(team["picks"]),
                                       board(.25) if ranked else {}, ranked))
        outlooks[team["owner_id"]] = OPPONENT_OUTLOOKS[index % 5]
    viewer = LEAGUE["teams"][0]
    prefs = {uid: {"starter_slots": list(SLOTS), "lineup_source": "observed"}
             for uid in ["me", *(m.user_id for m in members)]}
    return dict(players=players, league=ts.League(LEAGUE_ID, "Fixture", "sleeper", members),
                user_id="me", user_roster=viewer["players"] + list(viewer["picks"]), seed_elo=seed_elo,
                user_elo=dict(seed_elo) if neutral_board else user_elo, outlook=outlook,
                manager_preferences=prefs, opponent_outlooks=outlooks, fairness_threshold=.75)


@lru_cache(maxsize=None)
def deck(revision, outlook, season="usable", demotion=None, matching=None):
    """(cards, report) for one generation; cached per arguments (several seconds each)."""
    args = world(outlook)
    config = {k: v for k, v in (("season_conflict_demotion", demotion), ("season_partner_matching", matching))
              if v is not None}
    if revision == 2:
        return r2.generate_bilateral_trades(**args)
    ev = {"usable": _evidence(), "unavailable": sv.unavailable("stale"), "absent": None}[season]
    return r5.generate_bilateral_trades(**args, season_evidence=ev, config=config)


def ident(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def terms(card):
    return ident(card), card.give_value, card.receive_value, card.fairness_score


def proof(card):
    return card.owner_evaluation.as_dict()


@lru_cache(maxsize=None)
def probe(outlook="championship", matching=0.0):
    return r5._Search(**world(outlook), season_evidence=_evidence(),
                      config={"season_partner_matching": matching})


def delta(card, search=None):
    """The viewer's season lineup change, points a week, measured with an All-in probe."""
    search = search or probe()
    me = search.teams["me"]
    before = search._season_total(me["roster"], me)[0]
    after = search._season_total((me["roster"] - set(card.give_player_ids)) | set(card.receive_player_ids), me)[0]
    return after - before


# ── I2, I3, I4: no change where the season signal does not apply ──────────────

@pytest.mark.parametrize("season", ["absent", "unavailable"])
def test_without_usable_evidence_revision_5_is_revision_2(season):
    base, _ = deck(2, "championship")
    cards, report = deck(5, "championship", season)
    assert [terms(c) for c in cards] == [terms(c) for c in base]
    assert all(proof(c)["generator_version"] == r5.VERSION for c in cards)
    signal = proof(cards[0])["season_signal"]
    assert signal == {"evidence": {"state": "absent", "reason": None}} if season == "absent" else \
        signal == {"evidence": {"state": "unavailable", "reason": "stale"}}
    assert report.as_dict()["starter_evidence"] == "dynasty_proxy_only_no_projected_points"


def test_not_sure_viewer_with_usable_evidence_is_revision_2():
    base, _ = deck(2, "not_sure")
    cards, report = deck(5, "not_sure")
    assert [terms(c) for c in cards] == [terms(c) for c in base]
    for old, new in zip(base, cards):
        old, new = proof(old), proof(new)
        assert new["bilateral"] == old["bilateral"]
        assert new["season_signal"]["viewer"]["scored"] is False
        assert new["season_signal"]["conflict"]["fired"] is False
    assert report.as_dict()["season_signal"]["viewer_scored"] is False


@pytest.mark.parametrize("outlook", ["rebuilder", "jets"])
def test_rebuilding_and_tanking_viewers_keep_inventory_and_terms(outlook):
    """I4 as amended 2026-11-11: same inventory and terms as revision 2; the order differs."""
    base, _ = deck(2, outlook)
    cards, _ = deck(5, outlook)
    assert sorted(terms(c) for c in cards) == sorted(terms(c) for c in base)
    flagged = [c for c in cards if proof(c)["season_signal"]["conflict"]["fired"]]
    assert flagged, "the mirror rule fires somewhere on the fixture"
    for card in flagged:
        conflict = proof(card)["season_signal"]["conflict"]
        assert conflict["plan"] == outlook and conflict["threshold"] == sv.CONFLICT_ADD[outlook]
        assert conflict["trigger"] in ("points", "label")
    # Penalty 0: the same inventory again, and the shed term alone reorders it.
    still, _ = deck(5, outlook, demotion=0.0)
    assert sorted(terms(c) for c in still) == sorted(terms(c) for c in base)
    assert [terms(c) for c in still] != [terms(c) for c in base]


def _candidates(outlook, args, per_member=120):
    """Revision 2's own candidate stream (eligible or not) for the first four partners."""
    search = r2._Search(**args)
    out = []
    with ts._cfg_override(search.config), ts.stud_tax_override("market"):
        for member in search.members[:4]:
            stream = search.candidates(member)
            for _ in range(per_member):
                card = next(stream, None)
                if card is None:
                    break
                search.evaluate(card)
                out.append(card)
    return out


@pytest.mark.parametrize("outlook", ["rebuilder", "jets"])
def test_no_gate_changes_for_rebuilding_and_tanking(outlook):
    """Every candidate gets revision 2's verdict and reason under revision 5, eligible or
    rejected; Tanking's hard rules (own next-year pick, RB without a long-term case) still
    reject what they rejected."""
    args = world(outlook)
    me = args["manager_preferences"]["me"]
    picks = sorted(p for p in args["user_roster"] if args["players"][p].position == "PICK")
    me["own_next_draft_pick_ids"] = picks[:2]
    cards = _candidates(outlook, args)
    old = r2.evaluate_bilateral_trades(cards, **args)
    new = r5.evaluate_bilateral_trades(cards, **args, season_evidence=_evidence())
    verdicts = [(o.eligible, o.reason) for o in old]
    assert verdicts == [(n.eligible, n.reason) for n in new]
    reasons = {reason for _, reason in verdicts}
    assert sum(e for e, _ in verdicts) > 20 and len(reasons) > 3, reasons
    if outlook == "jets":
        assert {"tanking_own_next_draft_pick", "tanking_rb_without_long_term_exception"} <= reasons


def _first_30_points(cards):
    return statistics.mean(delta(c) for c in cards[:30])


def test_tanking_and_rebuilding_shed_lineup_points_in_the_first_30():
    """With usable evidence the first 30 of a Tanking or Rebuilding deck shed more lineup
    points a week than revision 2's; for the same Rebuilding viewer the move at its own
    weight (0.5) is smaller than at Tanking's (1.0). Measured at build (fixture): Tanking
    -2.09 -> -2.83, Rebuilding -1.95 -> -2.95 (at weight 1.0: -3.22)."""
    moves = {}
    for outlook in ("jets", "rebuilder"):
        base, _ = deck(2, outlook)
        cards, _ = deck(5, outlook)
        moves[outlook] = _first_30_points(cards) - _first_30_points(base)
        assert moves[outlook] <= -.5, (outlook, moves[outlook])
        assert sum(delta(c) <= -.5 for c in cards[:30]) > sum(delta(c) <= -.5 for c in base[:30])
    full, _ = r5.generate_bilateral_trades(**world("rebuilder"), season_evidence=_evidence(),
                                           config={"season_shed_weight_rebuilding": 1.0})
    base, _ = deck(2, "rebuilder")
    assert moves["rebuilder"] > _first_30_points(full) - _first_30_points(base) + .1


def test_a_point_shed_by_tanking_weighs_what_a_point_gained_weighs_for_all_in():
    """lineup_gain of a Tanking viewer is exactly minus the All-in viewer's for the same
    card (RATE x points / gross market, clipped), Rebuilding's is half of that, and it is
    positive when the trade sheds points."""
    allin = probe()
    me = allin.teams["me"]
    for outlook, weight in (("jets", 1.0), ("rebuilder", .5)):
        cards, _ = deck(5, outlook)
        signs = set()
        for card in cards[:300]:
            give, receive = tuple(card.give_player_ids), tuple(card.receive_player_ids)
            gross = sum(allin.market[p] for p in give + receive)
            gained = r1._clip(allin._owner(me, give, receive)["need_utility"] * 4)
            assert gained == pytest.approx(r1._clip(r5.RATE * delta(card) / gross), abs=1e-12)
            shed = proof(card)["season_signal"]["components"]["lineup_gain"]
            assert shed == pytest.approx(r1._clip(-weight * r5.RATE * delta(card) / gross), abs=1e-12)
            if weight == 1.0:
                assert shed == pytest.approx(-gained, abs=1e-12)
            signs.add((delta(card) < 0, shed > 0))
        assert (True, True) in signs and (False, True) not in signs


@pytest.mark.parametrize("outlook", ["rebuilder", "jets"])
def test_shed_scored_viewer_proof(outlook):
    """The viewer's season facts as for a win-now viewer, the direction, the components and
    the support moved by the team-plan weight times the re-scored team plan."""
    cards, report = deck(5, outlook)
    assert report.as_dict()["season_signal"]["viewer_scored"] is True
    assert report.as_dict()["starter_evidence"] == "projected_points_viewer"
    for card in cards[:200]:
        data = proof(card)
        signal = data["season_signal"]
        viewer = signal["viewer"]
        assert viewer["scored"] is True and viewer["season_direction"] == "shed"
        assert viewer["delta_pts_week"] == pytest.approx(delta(card), abs=.01)
        assert {"lineup_before", "lineup_after", "incoming_starters", "outgoing_starters",
                "dynasty_cost_pct"} <= set(viewer)
        parts = signal["components"]
        combined = min(1, max(0, .5 + .5 * max(-1, min(1, parts["plan_fit"] + parts["lineup_gain"]))))
        assert parts["team_plan"] == pytest.approx(combined, abs=1e-12)
        support = data["viewer"]["support"]
        assert support["components"]["team_plan"] == parts["team_plan"]
        adjustments = support["season_adjustments"]
        assert support["score"] == pytest.approx(min(1, max(0, support["season_unadjusted_score"]
                                                            + sum(adjustments.values()))), abs=1e-12)
        assert all(a["plan_lean"] is None for a in signal["assets"])  # the label table is not read
        assert data["viewer"]["team_plan_gain"] == pytest.approx(  # the gates' figure: revision 2's
            r1._clip(parts["plan_fit"] + r1._clip(data["viewer"]["need_utility"] * 4)), abs=1e-12)


def test_inferred_rebuilding_roster_is_scored_and_never_flagged():
    args = world("rebuilder")
    args["outlook"] = None
    args["inferred_outlooks"] = {"me": "rebuilder"}
    base, _ = r2.generate_bilateral_trades(**args)
    cards, _ = r5.generate_bilateral_trades(**args, season_evidence=_evidence())
    assert sorted(terms(c) for c in cards) == sorted(terms(c) for c in base)
    assert [terms(c) for c in cards] != [terms(c) for c in base]
    for card in cards:
        signal = proof(card)["season_signal"]
        assert signal["viewer"]["outlook_source"] == "inferred" and signal["viewer"]["season_direction"] == "shed"
        assert signal["conflict"]["fired"] is False


# ── I5, I6: plan fit from the label table ────────────────────────────────────

def _two_rbs(outlook):
    """Two RBs of equal value and age on a partner: one projects as a starter, one as a backup."""
    args = world(outlook)
    partner = args["league"].members[0]
    ev = evidence()
    for pid, ppg in (("rb_starter", 13.0), ("rb_backup", 4.0)):
        args["players"][pid] = Player(pid, pid, "RB", "TST", 25)
        args["seed_elo"][pid] = args["user_elo"][pid] = ts.value_to_elo(1150.)
        partner.roster.append(pid)
        ev["players"][pid] = {"ppg": ppg, "games": 13}
    return args, ev


def test_equal_value_equal_age_starter_beats_backup_for_all_in():
    args, ev = _two_rbs("championship")
    old, new = r2._Search(**args), r5._Search(**args, season_evidence=ev)
    me_old, me_new = old.teams["me"], new.teams["me"]
    assert old._plan_asset(me_old, "rb_starter") == old._plan_asset(me_old, "rb_backup")  # today: a tie
    assert new.starts_for(me_new, "rb_starter") and not new.starts_for(me_new, "rb_backup")
    assert new._plan_asset(me_new, "rb_starter") > new._plan_asset(me_new, "rb_backup")
    assert new._plan_asset(me_new, "rb_backup") == pytest.approx(-.5)  # a pick's fit, All-in
    contender = r5._Search(**_two_rbs("contender")[0], season_evidence=ev)
    team = contender.teams["me"]
    assert contender._plan_asset(team, "rb_starter") == pytest.approx(.6 * new._plan_asset(me_new, "rb_starter"))


def test_non_starter_plan_lean_equals_a_picks():
    search = probe()
    me = search.teams["me"]
    pick = next(p for p in sorted(me["roster"]) if search._position(p) == "PICK")
    benched = [p for p in sorted(search.market) if p in search._season_ppg and not search.starts_for(me, p)]
    assert len(benched) > 50
    assert {search._plan_asset(me, p) for p in benched} == {search._plan_asset(me, pick)} == {-.5}


# ── I7, I8, I9: the penalty is order only; terms are revision 2's ─────────────

def test_conflict_penalty_never_changes_the_inventory():
    demoted, _ = deck(5, "championship")
    kept, _ = deck(5, "championship", demotion=0.0)
    assert sorted(terms(c) for c in demoted) == sorted(terms(c) for c in kept)
    flagged = [c for c in demoted if proof(c)["season_signal"]["conflict"]["fired"]]
    assert flagged and all(proof(c)["season_signal"]["conflict"]["demotion"] == .10 for c in flagged
                           if proof(c)["season_signal"]["conflict"]["kind"] == "board")
    for card in flagged:
        data = proof(card)
        assert data["viewer"]["utility"] == pytest.approx(data["viewer"]["support"]["season_unadjusted_score"] - .35)


def _operator_world(**prefs):
    """PRD §7: All-in, the viewer gives Davante Adams (a starter) for a 23-year-old backup RB
    the viewer's board rates 15% above market; the twin gives an equal, benched WR instead."""
    args = world("championship", neutral_board=True)
    partner = args["league"].members[0]
    ev = evidence()
    players = args["players"]
    players["rb_kid"] = Player("rb_kid", "rb_kid", "RB", "TST", 23)
    players["wr_twin"] = Player("wr_twin", "wr_twin", "WR", "TST", players[ADAMS].age)
    args["seed_elo"]["rb_kid"] = args["user_elo"]["rb_kid"] = ts.value_to_elo(1150.)
    args["seed_elo"]["wr_twin"] = args["user_elo"]["wr_twin"] = args["seed_elo"][ADAMS]
    if prefs.get("lift", True):
        args["user_elo"]["rb_kid"] = ts.value_to_elo(1150. * 1.15)
    partner.roster.append("rb_kid")
    if ADAMS in partner.elo_ratings:  # the partner sees the twin exactly as Adams
        partner.elo_ratings["wr_twin"] = partner.elo_ratings[ADAMS]
    args["user_roster"].append("wr_twin")
    args["manager_preferences"]["me"].update(prefs.get("me", {}))
    ev["players"]["rb_kid"] = {"ppg": 4.0, "games": 13}
    ev["players"]["wr_twin"] = {"ppg": 3.0, "games": 13}
    cards = [ts.TradeCard("", LEAGUE_ID, "me", partner.user_id, partner.username, [give], ["rb_kid"], 0, 0, 0)
             for give in (ADAMS, "wr_twin")]
    return args, ev, cards


def test_operators_card_is_flagged_kept_and_below_its_twin():
    args, ev, (card, twin) = _operator_world()
    before = r2.evaluate_bilateral_trades([card, twin], **args)
    after = r5.evaluate_bilateral_trades([card, twin], **args, season_evidence=ev)
    assert all(p.eligible for p in before + after)
    old, new = [p.as_dict() for p in before], [p.as_dict() for p in after]
    for o, n in zip(old, new):
        assert n["market"] == o["market"] and n["viewer"]["intent"]["path"] == "personal_board"
    assert old[0]["bilateral"]["weaker_support"] == pytest.approx(old[1]["bilateral"]["weaker_support"])
    signal = new[0]["season_signal"]
    assert signal["viewer"]["delta_pts_week"] <= -.5 and signal["viewer"]["outgoing_starters"] == [ADAMS]
    assert signal["conflict"] == {"fired": True, "plan": "championship", "kind": "board", "named": "rb_kid",
                                  "trigger": "points", "threshold": .5, "demotion": .10}
    assert new[0]["viewer"]["support"]["score"] == pytest.approx(
        new[0]["viewer"]["support"]["season_unadjusted_score"] - .10)
    labels = {a["id"]: a["label"] for a in signal["assets"]}
    assert labels == {ADAMS: "win_now", "rb_kid": "rebuild"}
    assert new[1]["season_signal"]["conflict"]["fired"] is False
    assert new[0]["bilateral"]["weaker_support"] < new[1]["bilateral"]["weaker_support"]
    # Ranked together: the conflict card sits below its twin.
    for proof_, c in zip(after, (card, twin)):
        c.owner_evaluation, c.give_value, c.receive_value, c.fairness_score = (
            proof_, proof_.as_dict()["market"]["give"], proof_.as_dict()["market"]["receive"],
            proof_.as_dict()["market"]["ratio"])
    assert [c.give_player_ids[0] for c in r5._rank([card, twin])] == ["wr_twin", ADAMS]


def test_target_list_card_is_flagged_not_demoted():
    args, ev, (card, _) = _operator_world(lift=False, me={"targets": ["rb_kid"]})
    assert r2.evaluate_bilateral_trade(card, **args).eligible
    data = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev).as_dict()
    assert data["eligible"] and data["viewer"]["intent"]["path"] == "declared_intent"
    assert data["season_signal"]["conflict"] == {"fired": True, "plan": "championship", "kind": "target",
                                                 "named": "rb_kid", "trigger": "points", "threshold": .5,
                                                 "demotion": 0.0}
    assert "season_adjustments" not in data["viewer"]["support"]


# Each declared preference on the operator's card (Adams, a WR, out; rb_kid, an RB, in).
DECLARED = {"target": ({"targets": ["rb_kid"]}, "rb_kid"),
            "trade_block": ({"trade_block": [ADAMS]}, ADAMS),
            "position": ({"acquire_positions": ["RB"]}, "rb_kid"),
            "trade_away": ({"trade_away_positions": ["WR"]}, ADAMS)}


@pytest.mark.parametrize("kind", sorted(DECLARED))
def test_each_declared_kind_comes_from_its_own_input_flagged_not_demoted(kind):
    """The kind names what the viewer declared; `named` is the asset the declaration is
    about; a declared conflict of any kind is flagged and never demoted."""
    prefs, named = DECLARED[kind]
    args, ev, (card, _) = _operator_world(lift=False, me=prefs)
    data = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev).as_dict()
    assert data["eligible"] and data["viewer"]["intent"]["path"] == "declared_intent"
    assert data["season_signal"]["conflict"] == {"fired": True, "plan": "championship", "kind": kind,
                                                 "named": named, "trigger": "points", "threshold": .5,
                                                 "demotion": 0.0}
    assert "season_adjustments" not in data["viewer"]["support"]
    assert kind not in r5.DEMOTED_KINDS and r5.DEMOTED_KINDS == {"board"}


@pytest.mark.parametrize("kinds, expected", [
    (("target", "trade_block", "position", "trade_away"), "target"),
    (("trade_block", "position", "trade_away"), "trade_block"),
    (("position", "trade_away"), "position"),
])
def test_declared_kind_precedence(kinds, expected):
    """Several declarations match: target, then trade block, then position, then trade-away."""
    prefs = {k: v for kind in kinds for k, v in DECLARED[kind][0].items()}
    args, ev, (card, _) = _operator_world(lift=False, me=prefs)
    conflict = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev).as_dict()["season_signal"]["conflict"]
    assert (conflict["kind"], conflict["named"]) == (expected, DECLARED[expected][1])


def test_pinned_search_records_no_conflict():
    args, ev, (card, _) = _operator_world()
    for pins in ({"opponent_user_id": card.target_user_id}, {"pinned_give_players": [ADAMS]},
                 {"pinned_receive_players": ["rb_kid"]}):
        data = r5.evaluate_bilateral_trade(card, **args, **pins, season_evidence=ev).as_dict()
        assert data["eligible"], pins
        assert data["season_signal"]["conflict"]["fired"] is False, pins
        assert "season_adjustments" not in data["viewer"]["support"]


def test_conflict_needs_a_saved_plan():
    args, ev, (card, _) = _operator_world()
    args["outlook"] = None
    args["inferred_outlooks"] = {"me": "championship"}
    data = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev).as_dict()
    assert data["viewer"]["outlook_source"] == "inferred" and data["season_signal"]["viewer"]["scored"]
    assert data["season_signal"]["conflict"]["fired"] is False


def test_shared_cards_keep_revision_2_terms_floor_and_fairness():
    base, _ = deck(2, "championship")
    cards, _ = deck(5, "championship")
    old = {ident(c): c for c in base}
    shared = [c for c in cards if ident(c) in old]
    assert len(shared) > 1000
    for card in shared:
        before, after = proof(old[ident(card)]), proof(card)
        assert after["market"] == before["market"]
        assert terms(card) == terms(old[ident(card)])
        for side in ("viewer", "counterparty"):
            assert after[side]["market_gain_fraction"] == before[side]["market_gain_fraction"]
            assert (after[side]["support"]["components"]["market_acceptability"]
                    == before[side]["support"]["components"]["market_acceptability"])


# ── candidate seats, stage 2 ─────────────────────────────────────────────────

def test_candidate_seats_for_starters_and_for_future_value():
    args = world("championship", neutral_board=True)
    old, new = r2._Search(**args), r5._Search(**args, season_evidence=_evidence())
    me = new.teams["me"]
    held = new._season_total(me["roster"], me)[1]
    future = min((p for p in me["roster"] if p in new.market and p not in held),
                 key=lambda p: (-new.market[p], p))
    for member in new.members:
        team = new.teams[member.user_id]
        receive_old, receive_new = old._pool(old.teams[member.user_id], old.teams["me"]), new._pool(team, me)
        assert len(receive_new) == len(receive_old) == new.pool_size
        starters = sorted((p for p in team["roster"] if p in new.market and new.starts_for(me, p)),
                          key=lambda p: (-new.season_gain(me, p), p))
        # The two best starters for the viewer always hold a seat (the board is neutral on them).
        assert set(starters[:2]) <= set(receive_new), member.user_id
        give_new = new._pool(me, team)
        assert len(give_new) == new.pool_size and future in give_new, member.user_id


def test_stage_2_off_partners_plan_and_lineup_are_revision_2s():
    args = world("championship")
    old, new = r2._Search(**args), r5._Search(**args, season_evidence=_evidence())
    for uid, team in new.teams.items():
        if uid == "me":
            continue
        assert team["lineup_before"] == old.teams[uid]["lineup_before"], uid
        for pid in sorted(new.market):
            assert new._plan_asset(team, pid) == old._plan_asset(old.teams[uid], pid), (uid, pid)
    on = probe(matching=1.0)
    changed = {uid for uid, team in on.teams.items() if uid != "me" and any(
        on._plan_asset(team, p) != old._plan_asset(old.teams[uid], p) for p in sorted(on.market))}
    assert changed == {uid for uid, o in args["opponent_outlooks"].items() if o != "not_sure"}


def test_stage_2_generates():
    cards, report = deck(5, "championship", matching=1.0)
    base, _ = deck(5, "championship")
    assert cards and report.as_dict()["season_signal"]["partner_matching"] is True
    assert {terms(c) for c in cards} != {terms(c) for c in base}


_STAGE_2 = {"season_partner_matching": 1.0}


def _card(args, partner, give, receive):
    member = next(m for m in args["league"].members if m.user_id == partner)
    return ts.TradeCard("", LEAGUE_ID, "me", partner, member.username, list(give), list(receive), 0, 0, 0)


@pytest.mark.parametrize("partner, wanted, offered", [
    ("u00", "Terry McLaurin", "Kenyon Sadiq"),          # a Contending partner
    ("u03", "Tucker Kraft", "2027_r1_t01"),             # an All-in partner
])
def test_stage_2_win_now_pair_trade_on_a_ranking_discrepancy(partner, wanted, offered):
    """Two win-now teams, stage 2 on: when the partner's own board rates the player the
    viewer wants well below market (60%), the card is eligible for both. With the
    partner's board at market the same card is not (the partner gains nothing): the
    discrepancy is what makes it. Measured at build; Travis Etienne for the same pick
    stays ineligible either way (counterparty_no_benefit)."""
    verdicts = []
    for share in (.6, 1.0):
        args = world("championship", neutral_board=True)
        member = next(m for m in args["league"].members if m.user_id == partner)
        assert args["opponent_outlooks"][partner] in r5.SCORED_OUTLOOKS and member.has_rankings
        member.elo_ratings.update({k: args["seed_elo"][k] for k in member.elo_ratings})
        x = BY_NAME[wanted]
        give = BY_NAME.get(offered, offered)
        member.elo_ratings[x] = ts.value_to_elo(ts.elo_to_value(args["seed_elo"][x]) * share)
        search = r5._Search(**args, season_evidence=_evidence(), config=_STAGE_2)
        assert search.starts_for(search.teams["me"], x)                    # he starts for the viewer
        data = r5.evaluate_bilateral_trade(_card(args, partner, [give], [x]), **args,
                                           season_evidence=_evidence(), config=_STAGE_2).as_dict()
        verdicts.append((data["eligible"], data["reason"]))
        if share < 1:
            assert data["counterparty"]["season"]["delta_pts_week"] < 0     # the partner gives a starter
    assert verdicts == [(True, "eligible"), (False, "counterparty_no_benefit")]


def test_stage_2_win_now_pair_trade_on_complementary_needs():
    """Two win-now teams, stage 2 on, positional needs that complement: the viewer's QB is
    out and the All-in partner has a spare QB on its bench; the viewer has a spare RB the
    partner would start. Each gains lineup points at a different position, and the card is
    eligible with stage 2 on (and off). The fixture league has no such 1-for-1 between
    win-now teams as dealt (two FLEX slots absorb every surplus but QB), so the viewer's QB
    injury and the spare RB are constructed."""
    args = world("championship", neutral_board=True)
    ev = evidence()
    args["manager_preferences"]["me"]["inactive_ids"] = [BY_NAME["Joe Burrow"]]
    args["players"]["rb_spare"] = Player("rb_spare", "rb_spare", "RB", "TST", 26)
    args["seed_elo"]["rb_spare"] = args["user_elo"]["rb_spare"] = ts.value_to_elo(700.)
    ev["players"]["rb_spare"] = {"ppg": 10.0, "games": 13}
    args["user_roster"].append("rb_spare")
    assert args["opponent_outlooks"]["u08"] == "championship"
    card = _card(args, "u08", ["rb_spare"], [BY_NAME["Jared Goff"]])
    for config in (_STAGE_2, {}):
        data = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev, config=config).as_dict()
        assert data["eligible"], (config, data["reason"])
        assert data["season_signal"]["viewer"]["delta_pts_week"] >= .5
        assert data["season_signal"]["viewer"]["incoming_starters"] == [BY_NAME["Jared Goff"]]
    on = r5.evaluate_bilateral_trade(card, **args, season_evidence=ev, config=_STAGE_2).as_dict()
    partner = on["counterparty"]["season"]
    assert partner["delta_pts_week"] >= .5 and partner["incoming_starters"] == ["rb_spare"]
    assert partner["outgoing_starters"] == []                               # Goff sat on their bench


# ── proof fields (lld §4) ─────────────────────────────────────────────────────

def test_proof_carries_plan_fit_and_lineup_gain_separately():
    cards, report = deck(5, "championship")
    search = probe()
    me = search.teams["me"]
    profile = search._profile["players"]
    assert report.as_dict()["starter_evidence"] == "projected_points_viewer"
    for card in cards[:200]:
        data = proof(card)
        signal = data["season_signal"]
        assert signal["rules_version"] == sv.RULES_VERSION and signal["label_rules_version"] == sv.LABEL_RULES_VERSION
        assert signal["evidence"]["digest"] == _evidence()["digest"] and signal["evidence"]["weeks"] == list(range(1, 15))
        parts = signal["components"]
        assert -1 <= parts["plan_fit"] <= 1 and -1 <= parts["lineup_gain"] <= 1
        combined = min(1, max(0, .5 + .5 * max(-1, min(1, parts["plan_fit"] + parts["lineup_gain"]))))
        assert parts["team_plan"] == pytest.approx(combined, abs=1e-9)
        assert parts["team_plan"] == data["viewer"]["support"]["components"]["team_plan"]
        viewer = signal["viewer"]
        assert viewer["scored"] and viewer["delta_pts_week"] == pytest.approx(delta(card), abs=.01)
        assert data["viewer"]["starter_evidence"]["projected_starter_delta"] == viewer["delta_pts_week"]
        assert data["viewer"]["lineup_proxy"] == "season_points_per_game_v1"
        assert data["counterparty"]["lineup_proxy"] == "market_usable_depth_v1"
        for asset in signal["assets"]:
            pid = asset["id"]
            assert asset["label"] == profile[pid]["label"]  # the label the table read
            if asset["ppg"] is None:  # unprojected or a pick: no claim
                assert asset["starts_for_viewer"] is None and asset["gain_for_viewer"] is None
                continue
            table = (r5.LEAN_BENCH if not asset["starts_for_viewer"] else
                     r5.LEAN_STARTS_LABELLED if asset["label"] in ("win_now", "cornerstone") else r5.LEAN_STARTS)
            assert asset["plan_lean"] == table
            assert asset["gain_for_viewer"] == search.season_gain(me, pid)


def test_revalidation_reproduces_every_frozen_proof():
    cards, _ = deck(5, "championship")
    sample = cards[:40]
    finals = r5.evaluate_bilateral_trades(sample, **world("championship"), season_evidence=_evidence())
    for card, final in zip(sample, finals):
        assert final.eligible and final.matches(card)
        assert final.as_dict() == proof(card)
        assert final.model_identity == ("owner_v2_bilateral", "owner-v2-bilateral-5")


def test_presentment_reads_revision_5_proofs():
    cards, _ = deck(5, "championship")
    sample = cards[:60]
    _, diagnostics = presentment.present(sample, generator_version=r5.VERSION)
    assert diagnostics["eligible_count"] == len(sample)


# ── the planner's headline direction (validation §2), stated tolerance ──────────

def _served(cards, args):
    rosters = {"me": list(args["user_roster"]), **{m.user_id: list(m.roster) for m in args["league"].members}}
    market = probe().market
    kept, _ = deck_quality.filter_deck(cards, viewer_id="me", market=market.get,
                                       position=lambda p: getattr(args["players"].get(p), "position", None),
                                       rosters=rosters, lineup_slots=SLOTS)
    return kept


def test_all_in_headline_direction_on_the_fixture():
    """All-in viewer, first 30 cards. Tolerance: lineup points added per card rise by at least
    1.0 a week; the share adding a starter rises; the share costing points does not rise;
    the generated inventory stays within 20% and the served stand-in deck keeps at least 95%
    of revision 2's size (PRD acceptance 14). Measured at build: see the WI-2 report."""
    args = world("championship")
    base, _ = deck(2, "championship")
    cards, _ = deck(5, "championship")
    for old, new in ((base, cards), (_served(base, args), _served(cards, args))):
        d_old, d_new = [delta(c) for c in old[:30]], [delta(c) for c in new[:30]]
        assert statistics.mean(d_new) >= statistics.mean(d_old) + 1.0
        assert sum(d > .5 for d in d_new) > sum(d > .5 for d in d_old)
        assert sum(d < -.5 for d in d_new) <= sum(d < -.5 for d in d_old)
    assert abs(len(cards) - len(base)) <= .2 * len(base)
    assert len(_served(cards, args)) >= .95 * len(_served(base, args))


# ── selector, knobs, other revisions ─────────────────────────────────────────

_ON = {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.}


@pytest.mark.parametrize("cfg,expected", [
    ({}, "owner-v1"),
    ({KEY: 1.}, "owner-v1"),
    ({"owner_bilateral_enabled": 1., KEY: 1.}, "owner-v2-bilateral-1"),
    (_ON, "owner-v2-bilateral-2"),
    ({**_ON, KEY: 1.}, "owner-v2-bilateral-5"),
    ({**_ON, KEY: 1., "owner_bilateral_revision_4_enabled": 1.}, "owner-v2-bilateral-5"),
    ({**_ON, KEY: 1., "owner_outlook_evidence_enabled": 1.}, "owner-v2-bilateral-5"),
    ({**_ON, "owner_bilateral_revision_4_enabled": 1.}, "owner-v2-bilateral-4"),
    ({**_ON, "owner_outlook_evidence_enabled": 1.}, "owner-v2-bilateral-3"),
] + [({**_ON, KEY: value, "owner_bilateral_revision_4_enabled": v4},
      "owner-v2-bilateral-4" if v4 else "owner-v2-bilateral-2")
     for value in (0., .5, 2., -1.) for v4 in (0., 1.)])
def test_selector_composition(cfg, expected):
    assert bo.owner_version(cfg) == expected
    assert bo.owner_generator(cfg).__module__.endswith("trade_gen_bilateral_season") == (expected == r5.VERSION)
    assert bo.owner_evaluator(cfg).__module__.endswith("trade_gen_bilateral_season") == (expected == r5.VERSION)
    assert bo.owner_revision_5_enabled(cfg) == (expected == r5.VERSION)
    assert bo.owner_revision_4_enabled(cfg) == (expected == r4.VERSION)
    assert bo.owner_outlook_evidence_enabled(cfg) == (expected == "owner-v2-bilateral-3")
    assert bo.owner_presentment_version(cfg) == (
        expected if expected in ("owner-v2-bilateral-3", r4.VERSION, r5.VERSION) else presentment.GENERATOR_VERSION)


def test_knob_defaults_are_dark():
    defaults = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    for key, value in ((KEY, 0.), ("season_partner_matching", 0.), ("season_conflict_demotion", .10),
                       ("season_shed_weight_tanking", 1.), ("season_shed_weight_rebuilding", .5)):
        assert ts._DEFAULT_CFG[key] == value and defaults[key] == value
    assert bo.owner_version() != r5.VERSION and bo.owner_presentment_version() == presentment.GENERATOR_VERSION


_DARK = ("owner_bilateral_revision_5_enabled", "season_conflict_demotion", "season_partner_matching",
         "season_shed_weight_tanking", "season_shed_weight_rebuilding")


@pytest.mark.parametrize("extra", [{}, {KEY: 0., "season_conflict_demotion": .3, "season_partner_matching": 1.,
                                         "season_shed_weight_tanking": 2., "season_shed_weight_rebuilding": 0.},
                                   {KEY: 2., "season_partner_matching": 1., "season_shed_weight_rebuilding": 1.}],
                         ids=["defaults", "zero", "two"])
def test_other_revisions_unchanged_with_the_new_knobs_present(extra):
    from backend.tests import test_bilateral_revision_4 as golden
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)  # the goldens' own setup
    ts._cfg.update(extra)
    for (revision, name), digest in sorted(golden._GOLDEN.items()):
        base = golden._BASES[revision]
        cfg = dict(ts._cfg, **base, **extra)
        cards, report = bo.owner_generator(cfg)(**golden._WORLDS[name](), config={**base, **extra})
        assert golden._digest(cards, report) == digest, (revision, name)
    for module in (r1, r2, r4):
        search = module._Search(**golden._WORLDS["favorable"](), config=dict(extra))
        assert not set(_DARK) & set(search.config), module.__name__
    selected = r2._Search(**golden._WORLDS["favorable"](), config={KEY: 1.})
    assert set(_DARK) <= set(selected.config)
