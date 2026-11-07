"""V3 evidence semantics; synthetic fixtures are not forecast validation."""
from copy import deepcopy
import json

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend import trade_gen_bilateral_candidate as previous
from backend import trade_gen_outlook_evidence as candidate
from backend import trade_bilateral_presentment as presentment
from backend.trade_input_evidence import PoolInputEvidence, detached_context, request_evidence
from backend.tests.test_bilateral_contracts import favorable, world, packages
from backend.tests.test_bilateral_candidate import terms


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def qualified(args, *, missing=()):
    collector = PoolInputEvidence()
    for pid, player in args["players"].items():
        collector.record(player, raw={"age": None if pid in missing else player.age})
    args = detached_context(args, collector)
    args["input_evidence"] = request_evidence(args)
    args["input_evidence"].update(schema_version=candidate.INPUT_VERSION, used_in_model=True)
    return args


def proof(args, give=("give",), receive=("target",)):
    return candidate.evaluate_bilateral_trade(terms(args, give, receive), **args)


@pytest.mark.parametrize("position,boundary", [("QB",27), ("WR",25), ("TE",25), ("RB",24)])
@pytest.mark.parametrize("outlook", ["jets", "rebuilder", "contender", "championship"])
def test_birthdays_cannot_create_age_only_fit_or_eligibility(position, boundary, outlook):
    snapshots = []
    for age in (boundary-1/365, boundary, boundary+1/365, boundary+1):
        args = qualified(favorable(positions={"give":position,"target":position},
            ages={"give":age,"target":23}, outlook=outlook,
            opponent_outlooks={"partner":outlook}))
        cards, _ = candidate.generate_bilateral_trades(**args)
        assert cards
        snapshots.append((packages(cards), [(c.give_player_ids,c.receive_player_ids) for c in cards],
            proof(args).as_dict()["bilateral"]))
        search = candidate._Search(**args)
        assert search._plan_asset(search.teams["viewer"], "give") == 0
    assert all(snapshot == snapshots[0] for snapshot in snapshots)


@pytest.mark.parametrize("age", [None,0,True,False,-1,float("inf"),float("nan"),"bad"])
def test_invalid_or_missing_age_never_becomes_genuine25(age):
    args = favorable(ages={"give":25})
    args = qualified(args)
    args["input_evidence"]["age"]["give"]["age"] = age
    data = proof(args).as_dict()
    assert data["viewer"]["window_evidence"]["assets"]["give"]["age"]["age"] is None
    assert "give" in data["viewer"]["team_plan_evidence"]["missing_age_ids"]


def test_observed25_imputed25_and_absent_provenance_remain_distinct():
    args = favorable(ages={"give":25,"target":25}, outlook="rebuilder")
    known = proof(qualified(args)).as_dict()
    missing = proof(qualified(args, missing={"give"})).as_dict()
    absent = proof(args).as_dict()
    assert known["input_evidence"]["age"]["give"]["age"] == 25
    assert missing["input_evidence"]["age"]["give"]["age"] is None
    assert absent["input_evidence"]["age"]["give"]["age"] is None
    assert known["bilateral"] == missing["bilateral"] == absent["bilateral"]
    assert args["players"]["give"].age == 25  # Shared public pool unchanged.


def test_personal_elite_rb_does_not_manufacture_longevity():
    outputs = []
    for age in (22,32):
        args = qualified(favorable(positions={"target":"RB"}, ages={"target":age}, outlook="jets"))
        args["user_elo"]["target"] = ts.value_to_elo(100000)
        data = proof(args).as_dict()
        evidence = data["viewer"]["window_evidence"]["assets"]["target"]
        assert evidence["production_fit"] == "unknown" and evidence["age_used_as_fit_score"] is False
        assert data["viewer"]["decomposition"]["player_window_fit"] is None
        outputs.append((data["bilateral"], evidence["age_at_window"]))
    assert outputs[0][0] == outputs[1][0]
    assert outputs[0][1] == [24,26] and outputs[1][1] == [34,36]


def test_qb_production_and_job_quality_cannot_be_fabricated_by_metadata():
    args = qualified(favorable(positions={"give":"QB","target":"QB"}, ages={"give":29,"target":24}))
    args["players"]["give"].years_experience=10
    args["players"]["give"].depth_chart_order=1
    args["input_evidence"]["qb_quality"]={"give":"proven","target":"fragile"}
    before = proof(args).as_dict()
    args["players"]["give"].years_experience=3
    after = proof(args).as_dict()
    for data in (before,after):
        assert data["viewer"]["window_evidence"]["assets"]["give"]["qb_quality_class"] == "unknown"
        assert data["viewer"]["starter_evidence"]["projected_starter_delta"] is None
    assert before["bilateral"] == after["bilateral"]


def slot_world(slots, *, depth=False, outlook="rebuilder", position="WR"):
    own=("give","qb1","bench","wr") if depth else ("give","qb1","wr")
    ids=own+("target",)
    args=world(own=own, market={p:850 if p=="target" else 1000 for p in ids},
        viewer={p:1300 if p=="target" else 800 for p in ids},
        partner={p:800 if p=="target" else 1300 for p in ids},
        positions={"give":"QB","qb1":"QB","bench":"QB","wr":"WR","target":position},
        outlook=outlook, scoring_format="1qb_ppr", manager_preferences={
            uid:{"starter_slots":slots,"lineup_source":"observed"} for uid in ("viewer","partner")})
    return qualified(args)


def test_actual_superflex_slots_and_real_nonqb_replacement_are_recorded():
    one = proof(slot_world(["QB","WR"])).as_dict()["viewer"]
    sf = proof(slot_world(["QB","SUPER_FLEX","WR"])).as_dict()["viewer"]
    depth = proof(slot_world(["QB","SUPER_FLEX","WR"],depth=True)).as_dict()["viewer"]
    assert one["qb_roster_context"]["before"]["qb_eligible_slots"] == 1
    assert sf["qb_roster_context"]["before"]["qb_eligible_slots"] == 2
    assert sf["qb_roster_context"]["after"]["nfl_starting_jobs"] == "unknown"
    assert depth["qb_roster_context"]["after"]["eligible_roster_qb_ids"] == ["bench","qb1"]
    assert sf["need_utility"] < depth["need_utility"]
    # SUPER_FLEX can legally hold a WR; no mandatory QB2 veto.
    args=slot_world(["QB","SUPER_FLEX"])
    assert any(row["slot"]=="SUPER_FLEX" and row["position"]=="WR"
        for row in proof(args).as_dict()["viewer"]["qb_roster_context"]["after"]["assignment"])


@pytest.mark.parametrize("outlook", ["jets","rebuilder"])
def test_rebuild_rb_hole_is_not_positive_current_starter_incentive(outlook):
    args=qualified(favorable(positions={"give":"PICK","target":"RB"}, outlook=outlook,
        manager_preferences={"viewer":{"starter_slots":["RB"],"lineup_source":"observed"}}))
    data=proof(args).as_dict()["viewer"]
    assert data["need_utility"] == 0
    assert data["decomposition"]["roster_proxy_applicability"] == "bounded_downside_only"
    assert "dynasty_roster_fit_proxy" not in data["benefits"]


@pytest.mark.parametrize("outlook", ["jets","rebuilder"])
def test_rb_to_pick_capital_survives_without_age_story(outlook):
    snapshots=[]
    for age in (22,32):
        args=qualified(favorable(positions={"give":"RB","target":"PICK"},
            ages={"give":age},outlook=outlook))
        decision=proof(args)
        assert decision.eligible
        data=decision.as_dict()["viewer"]
        assert "future_pick_capital" in data["benefits"]
        assert data["decomposition"]["future_capital_direction"] > 0
        snapshots.append(data["support"])
    assert snapshots[0] == snapshots[1]


def test_no_second_age_multiplier_and_explicit_outlook_overrides_inference():
    args=qualified(favorable(ages={"give":22,"target":34},outlook="rebuilder",
        inferred_outlooks={"viewer":"championship"}, opponent_outlooks={"partner":"jets"}))
    search=candidate._Search(**args)
    assert all(asset.value == search.market[pid] for pid,asset in search._lineup_assets.items())
    assert search.teams["viewer"]["outlook"]=="rebuilder"
    assert search.teams["partner"]["outlook"]=="jets"


def test_unknown_outlook_not_inferred_from_unbound_imputed_age():
    args=favorable(outlook=None,opponent_outlooks={})
    for age in (19,25,38):
        for player in args["players"].values(): player.age=age
        search=candidate._Search(**args)
        assert all(team["outlook"]=="not_sure" for team in search.teams.values())


def test_generation_evaluation_and_presentment_bind_v3_and_do_not_mutate_inputs():
    args=qualified(favorable())
    before=deepcopy(args)
    cards,report=candidate.generate_bilateral_trades(**args)
    assert cards and report.as_dict()["generator_version"]==candidate.VERSION
    for card,decision in zip(cards,candidate.evaluate_bilateral_trades(cards,**args)):
        assert decision.as_dict()==card.owner_evaluation.as_dict()
        assert decision.matches(card) and decision.eligible
    proof_bytes=[c.owner_evaluation.snapshot_json for c in cards]
    presented,diagnostics=presentment.present(cards,generator_version=candidate.VERSION)
    assert diagnostics["version"]=="bilateral-survivors-4"
    assert diagnostics["eligible_count"]==len(cards)
    assert [c.owner_evaluation.snapshot_json for c in presented]==proof_bytes
    assert args==before
    # Old presentment rejects rather than relabels new proofs.
    assert presentment.present(cards)[1]["eligible_count"]==0
    assert not previous.term_evidence_valid(cards[0].owner_evaluation.as_dict(),
        user_id="viewer",target_user_id="partner")


def test_explicit_selection_untouchables_price_and_owned_pick_protection():
    args=qualified(favorable(outlook="jets",positions={"give":"PICK"},
        manager_preferences={"viewer":{"own_next_draft_pick_ids":["give"]}}))
    assert proof(args).reason=="tanking_own_next_draft_pick"
    args["pinned_give_players"]=["give"]
    assert proof(args).eligible
    args=qualified(favorable(manager_preferences={"partner":{"untouchables":["target"]}},
        positions={"give":"RB","target":"QB"},pinned_receive_players=["target"]))
    assert proof(args).reason=="untouchable_return"
    args=qualified(favorable())
    args["seed_elo"]["target"]=ts.value_to_elo(100000)
    assert proof(args).reason=="market_floor"


@pytest.mark.parametrize('outlook',['jets','rebuilder'])
@pytest.mark.parametrize('age',[22,29,32])
def test_rebuild_focal_rb_needs_acquisition_thesis_not_market_or_sell_desire(outlook,age):
    args=qualified(world(viewer={},partner={},positions={'target':'RB'},
        ages={'target':age},market={'give':1000,'target':1100},outlook=outlook,
        manager_preferences={'viewer':{'trade_away_positions':['WR']}}))
    assert proof(args).reason=='rebuild_rb_acquisition_thesis_missing'
    for change in ('pin','target','acquire','preference'):
        desired=deepcopy(args)
        if change=='pin': desired['pinned_receive_players']=['target']
        if change=='target': desired['manager_preferences']['viewer']['targets']=['target']
        if change=='acquire': desired['manager_preferences']['viewer']['acquire_positions']=['RB']
        if change=='preference':
            desired['user_elo']['target']=ts.value_to_elo(1600)
            desired['user_sources']['target']='explicit'
        decision=proof(desired)
        assert decision.eligible, (change,decision.reason)
        assert decision.as_dict()['viewer']['rb_acquisition_evidence']['meaning']=='manager_desire_not_longevity'


def test_spending_pick_alone_cannot_claim_contender_production_or_capital_gain():
    args=qualified(world(positions={'give':'PICK'},outlook='contender',viewer={},partner={}))
    data=proof(args).as_dict()['viewer']
    assert 'future_pick_capital' not in data['benefits']
    assert data['decomposition']['future_capital_direction']==0
    assert data['decomposition']['player_window_fit'] is None


def test_roster_assignment_cache_is_bounded_and_same_input_has_no_duplicate_solve(monkeypatch):
    args=slot_world(['QB','SUPER_FLEX','WR'])
    real=candidate.assign
    calls=[]
    def observed(slots,assets):
        calls.append(tuple(sorted(a.id for a in assets)))
        return real(slots,assets)
    monkeypatch.setattr(candidate,'assign',observed)
    search=candidate._Search(**args)
    team=search.teams['viewer']
    before=len(calls)
    search._lineup(team['roster'],team)
    search._coverage(team,team['roster'])
    assert len(calls)==before
    for n in range(300): search._lineup(team['roster']|{f'unknown{n}'},team)
    assert len(search._roster_cache)==256


def test_companion_price_boundary_cannot_bypass_rebuild_acquisition_thesis():
    for rb_price in (999,1000):
        args=qualified(world(other=('wr','rb'), market={'give':1400,'wr':1000,'rb':rb_price},
            viewer={},partner={'give':2600,'wr':500,'rb':500},
            positions={'give':'WR','wr':'WR','rb':'RB'}, ages={'give':26,'wr':26,'rb':32},
            outlook='rebuilder',opponent_outlooks={'partner':'contender'}))
        assert candidate.generate_bilateral_trades(**args)[0] == []
        # The known desired WR is a valid independent thesis only when it is
        # the headliner and the RB is genuinely required price consideration.
        args['user_elo']['wr']=ts.value_to_elo(1600)
        args['user_sources']['wr']='explicit'
        decision=proof(args,receive=('wr','rb'))
        assert decision.eligible == (rb_price < 1000)
        if decision.eligible:
            assert decision.as_dict()['viewer']['rb_acquisition_evidence']['companion_theses']['rb'] == 'required_price_companion_to_independent_focal_thesis'


def test_unrequested_unnecessary_rb_cannot_ride_a_desired_headliner():
    args=qualified(world(other=('wr','rb'),market={'give':1000,'wr':1100,'rb':100},
        viewer={'give':800,'wr':1600,'rb':100},partner={'give':1600,'wr':800,'rb':100},
        positions={'rb':'RB'},outlook='rebuilder'))
    assert proof(args,receive=('wr','rb')).reason=='rebuild_rb_companion_thesis_missing'


def test_existing_shared_age_price_policy_is_preserved_and_separate_from_fit():
    ts._cfg.update(age_pref_mult_u23=1.1,age_pref_mult_30plus=.9)
    args=qualified(favorable(positions={'give':'RB','target':'RB'},ages={'give':22,'target':32},
        outlook='rebuilder'))
    search=candidate._Search(**args)
    market=ts.make_consensus_value_fn(args['seed_elo'],args['players'])
    assert search.market['give']==market('give')
    assert search.market['target']==market('target')
    assert search.market['give']>search.market['target']
    assert search._lineup_assets['give'].value==search.market['give']
    assert search._lineup_assets['target'].value==search.market['target']
    assert search._plan_asset(search.teams['viewer'],'give')==search._plan_asset(search.teams['viewer'],'target')==0
