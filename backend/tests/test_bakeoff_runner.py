"""trade.bakeoff — three-model bake-off runner (Phase 3).

Spec: docs/plans/three-model-bakeoff/PLAN.md §3, §3.4, §4, §5.
Scope block: docs/plans/three-model-bakeoff/scope-phase3.md.

Unit-level contract under test (the serving-path integration lives in
test_bakeoff_serving.py):

  • Fan-out runs all three arms sequentially on this thread and returns three
    separately attributed lists; arm A runs under MODEL_A_PROFILE + the R4
    bypass, arm B plain, arm C via trade_gen_v2 regardless of `trade_gen.v2`.
  • Team-draft: arm rotation seeded on league_id + ISO week (reproducible,
    and rotating across weeks); arms alternate picks; every card is credited
    to its own arm at its rank WITHIN that arm's list.
  • Duplicates go to the FIRST picker and the agreement is recorded.
  • A short or empty arm forfeits its slot and the forfeit is counted — never
    an error, never a silent gap.
  • Arm positions across many decks are balanced (assert the distribution,
    not one draw) — the whole point of team-draft over A/B/C rotation.
  • Flag off ⇒ every predicate is False and the swipe K multiplier is
    untouched.
"""

import statistics
from collections import Counter
from unittest.mock import patch

import pytest

from backend import bakeoff_runner as bo
from backend.bakeoff_profiles import MODEL_A_PROFILE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeCard:
    """Minimal stand-in carrying only what card_key() reads."""

    def __init__(self, give, recv, target="opp"):
        self.give_player_ids = list(give)
        self.receive_player_ids = list(recv)
        self.target_user_id = target

    def __repr__(self):  # pragma: no cover — debugging aid
        return f"<{'+'.join(self.give_player_ids)}→{'+'.join(self.receive_player_ids)}>"


def _cards(n, prefix, target="opp"):
    return [FakeCard([f"{prefix}g{i}"], [f"{prefix}r{i}"], target) for i in range(n)]


def _flag(on: bool):
    return patch.object(bo, "bakeoff_enabled", lambda: on)


def _knobs(**vals):
    return patch.object(bo, "_cfg", lambda key, default: float(vals.get(key, default)))


#: Phase 3's behaviour expressed as knob KILL values — no group composition,
#: no deck cap, arm A back in the roster. The tests below that predate the
#: 2026-08-18 composition decision assert exactly this, which is the point:
#: the kill values must still restore it.
PHASE3_KNOBS = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0,
                "bakeoff_include_baseline": 1.0}


# ---------------------------------------------------------------------------
# Flag off
# ---------------------------------------------------------------------------

def test_flag_off_every_predicate_is_false():
    with _flag(False):
        assert bo.bakeoff_active("league_x", None, None, None) is False
        assert bo.bypass_rerankers("league_x", None, None, None) is False
        assert bo.serve_interleaved() is False
        # §3.4 Channel 1 — the swipe K multiplier is untouched.
        assert bo.elo_freeze_mult(0.7) == 0.7
        assert bo.elo_freeze_mult(1.0) == 1.0


def test_flag_on_freezes_swipe_elo():
    with _flag(True):
        assert bo.elo_freeze_mult(1.0) == 0.0
        assert bo.elo_freeze_mult(0.35) == 0.0


def test_bakeoff_skips_targeted_and_demo_decks():
    with _flag(True):
        assert bo.bakeoff_active("league_x", None, None, None) is True
        assert bo.bakeoff_active("league_demo", None, None, None) is False
        assert bo.bakeoff_active("league_x", ["p1"], None, None) is False
        assert bo.bakeoff_active("league_x", None, ["p1"], None) is False
        assert bo.bakeoff_active("league_x", None, None, "opp") is False


def test_interleaved_is_the_default_serving_mode_inside_the_flag():
    # Operator decision 2026-08-18: arm C serves by default; dark is the revert.
    with _flag(True), _knobs():
        assert bo.serve_interleaved() is True           # Phase 5
        assert bo.bypass_rerankers("l", None, None, None) is True
    with _flag(True), _knobs(bakeoff_serve_interleaved=0.0):
        assert bo.serve_interleaved() is False          # Phase 4 dark, the revert
        assert bo.bypass_rerankers("l", None, None, None) is False


# ---------------------------------------------------------------------------
# Arm order
# ---------------------------------------------------------------------------

def test_arm_order_is_seed_reproducible_and_a_permutation():
    a = bo.arm_order_for("league_42", "2026-W34")
    b = bo.arm_order_for("league_42", "2026-W34")
    assert a == b
    assert sorted(a) == sorted(bo.ARMS)


def test_arm_order_rotates_across_weeks_and_leagues():
    weeks = {tuple(bo.arm_order_for("league_42", f"2026-W{w:02d}"))
             for w in range(1, 30)}
    assert len(weeks) > 1, "arm order must not be constant across weeks"
    leagues = {tuple(bo.arm_order_for(f"league_{i}", "2026-W34"))
               for i in range(50)}
    assert len(leagues) > 1


def test_arm_order_is_uniform_over_many_decks():
    """Every arm must land in every rotation slot at a comparable rate — a
    permanently-slot-3 arm is exactly the position confound team-draft exists
    to remove."""
    slots = {arm: Counter() for arm in bo.ARMS}
    for i in range(600):
        for pos, arm in enumerate(bo.arm_order_for(f"league_{i}", "2026-W34")):
            slots[arm][pos] += 1
    for arm in bo.ARMS:
        for pos in range(3):
            assert 130 <= slots[arm][pos] <= 270, (arm, pos, slots[arm])


# ---------------------------------------------------------------------------
# Team draft
# ---------------------------------------------------------------------------

def test_team_draft_alternates_and_credits_own_rank():
    a, b, c = _cards(3, "a"), _cards(3, "b"), _cards(3, "c")
    res = bo.team_draft({"baseline": a, "current": b, "gen_v2": c},
                        ["current", "gen_v2", "baseline"])
    assert res.deck == [b[0], c[0], a[0], b[1], c[1], a[1], b[2], c[2], a[2]]
    for i, card in enumerate(res.deck):
        arm, rank = res.attribution[id(card)]
        assert rank == i // 3          # rank WITHIN its own arm's list
    assert [res.attribution[id(x)][0] for x in res.deck[:3]] == \
        ["current", "gen_v2", "baseline"]
    assert res.forfeits == {"baseline": 0, "current": 0, "gen_v2": 0}


def test_team_draft_is_reproducible_for_the_same_seed():
    lists = {"baseline": _cards(4, "a"), "current": _cards(4, "b"),
             "gen_v2": _cards(4, "c")}
    keys = lambda r: [bo.card_key(c) for c in r.deck]
    o1 = bo.arm_order_for("league_9", "2026-W20")
    o2 = bo.arm_order_for("league_9", "2026-W20")
    assert keys(bo.team_draft(lists, o1)) == keys(bo.team_draft(lists, o2))


def test_duplicate_goes_to_first_picker_and_is_recorded():
    shared = (["s_give"], ["s_recv"])
    a = [FakeCard(*shared), FakeCard(["a1"], ["a2"])]
    b = [FakeCard(*shared), FakeCard(["b1"], ["b2"])]
    c = [FakeCard(["c1"], ["c2"])]
    res = bo.team_draft({"baseline": a, "current": b, "gen_v2": c},
                        ["current", "baseline", "gen_v2"])

    # `current` drafts first, so the shared trade is credited to it exactly
    # once — the deck never carries the same trade twice.
    assert [bo.card_key(x) for x in res.deck].count(
        (("s_give",), ("s_recv",), "opp")) == 1
    winner = next(x for x in res.deck if bo.card_key(x)[0] == ("s_give",))
    assert res.attribution[id(winner)] == ("current", 0)
    # …and the agreement is recorded, not discarded.
    assert res.also_proposed_by[id(winner)] == ["baseline"]
    # `baseline`'s own second card still gets in, at ITS rank (1).
    a1 = next(x for x in res.deck if x.give_player_ids == ["a1"])
    assert res.attribution[id(a1)] == ("baseline", 1)


def test_agreement_is_found_even_past_an_arms_cursor():
    """The scan is over each arm's FULL list, so agreement is recorded even
    when the losing arm's cursor never reached the duplicate."""
    dup = (["x"], ["y"])
    a = [FakeCard(["a1"], ["a2"])] * 0 + [FakeCard(*dup)]
    b = [FakeCard(["b%d" % i], ["b%d" % i]) for i in range(5)] + [FakeCard(*dup)]
    res = bo.team_draft({"baseline": a, "current": b, "gen_v2": []},
                        ["baseline", "current", "gen_v2"], limit=3)
    winner = next(x for x in res.deck if bo.card_key(x) == (("x",), ("y",), "opp"))
    assert res.attribution[id(winner)][0] == "baseline"
    assert res.also_proposed_by[id(winner)] == ["current"]


def test_short_arm_forfeits_and_the_forfeit_is_counted():
    a, b, c = _cards(4, "a"), _cards(4, "b"), _cards(1, "c")
    res = bo.team_draft({"baseline": a, "current": b, "gen_v2": c},
                        ["baseline", "current", "gen_v2"])
    assert len(res.deck) == 9
    # Rounds 2 and 3; round 4 fills the deck before gen_v2's turn comes round,
    # and a full deck is not a forfeit.
    assert res.forfeits["gen_v2"] == 2
    assert res.forfeits["baseline"] == 0 and res.forfeits["current"] == 0
    assert sum(1 for x in res.deck
               if res.attribution[id(x)][0] == "gen_v2") == 1


def test_empty_arm_is_data_not_an_error():
    a, b = _cards(2, "a"), _cards(2, "b")
    res = bo.team_draft({"baseline": a, "current": b, "gen_v2": []},
                        ["baseline", "current", "gen_v2"])
    assert len(res.deck) == 4
    assert res.forfeits["gen_v2"] == 1
    assert all(res.attribution[id(x)][0] != "gen_v2" for x in res.deck)


def test_deck_limit_truncates_the_draft():
    lists = {"baseline": _cards(5, "a"), "current": _cards(5, "b"),
             "gen_v2": _cards(5, "c")}
    res = bo.team_draft(lists, ["baseline", "current", "gen_v2"], limit=4)
    assert len(res.deck) == 4


def test_team_draft_balances_arm_positions_across_many_decks():
    """The measurement guarantee: across many decks no arm systematically
    occupies better deck positions. Assert the distribution of mean served
    position per arm, not a single draw."""
    positions = {arm: [] for arm in bo.ARMS}
    for i in range(400):
        lists = {"baseline": _cards(6, "a"), "current": _cards(6, "b"),
                 "gen_v2": _cards(6, "c")}
        order = bo.arm_order_for(f"league_{i}", "2026-W34")
        res = bo.team_draft(lists, order)
        for pos, card in enumerate(res.deck):
            positions[res.attribution[id(card)][0]].append(pos)
    means = {arm: statistics.mean(v) for arm, v in positions.items()}
    assert max(means.values()) - min(means.values()) < 0.25, means
    # Every arm reaches slot 0 a comparable share of the time.
    firsts = Counter()
    for i in range(400):
        firsts[bo.arm_order_for(f"league_{i}", "2026-W34")[0]] += 1
    assert min(firsts.values()) > 90, firsts


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------

def _run(*, a_cards, b_cards, c_cards, interleave, order=None, seen=None,
         thr=None):
    """Drive run_bakeoff with stub generators. `generate` is called twice —
    once inside arm A's context, once plain — and distinguishes the two by
    reading the thread-local config overlay the runner entered."""
    from backend.trade_service import _cfg_local, r4_bypassed

    calls = seen if seen is not None else []

    def generate(**ov):
        overlay = getattr(_cfg_local, "map", None) or {}
        is_arm_a = overlay.get("max_overpay_frac") == 0.0 and \
            all(overlay.get(k) == v for k, v in MODEL_A_PROFILE.items())
        calls.append(("arm_a" if is_arm_a else "arm_b",
                      r4_bypassed(), dict(ov)))
        return list(a_cards if is_arm_a else b_cards)

    def gen_v2(**ov):
        from backend.trade_service import r4_bypassed
        calls.append(("arm_c", r4_bypassed(), dict(ov)))
        return list(c_cards)

    fixed = list(order or bo.ARMS)
    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in fixed if p in parts]), \
            _knobs(**PHASE3_KNOBS):
        return bo.run_bakeoff(generate=generate, gen_v2=gen_v2,
                              league_id="league_x", interleave=interleave,
                              fairness_threshold=thr, limit=None,
                              roster=bo.ARMS), calls


def test_fanout_produces_three_attributed_lists():
    a, b, c = _cards(2, "a"), _cards(2, "b"), _cards(2, "c")
    run, calls = _run(a_cards=a, b_cards=b, c_cards=c, interleave=True)

    assert set(run.arms) == set(bo.ARMS)
    assert [bo.card_key(x) for x in run.arms["baseline"].cards] == \
        [bo.card_key(x) for x in a]
    assert [bo.card_key(x) for x in run.arms["current"].cards] == \
        [bo.card_key(x) for x in b]
    assert [bo.card_key(x) for x in run.arms["gen_v2"].cards] == \
        [bo.card_key(x) for x in c]
    assert len(run.deck) == 6
    for card in run.deck:
        arm, rank = run.attribution_for(card)
        assert arm in bo.ARMS and rank >= 0


def test_arm_a_runs_under_the_pinned_profile_and_the_r4_bypass():
    run, calls = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                      c_cards=_cards(1, "c"), interleave=True)
    by_arm = {name: (r4, ov) for name, r4, ov in calls}
    assert by_arm["arm_a"][0] is True, "arm A must run inside model_a()'s R4 bypass"
    assert by_arm["arm_b"][0] is False, "arm B must not"
    assert by_arm["arm_c"][0] is False, "arm C must not"
    # …and the overlay is gone once the run returns.
    from backend.trade_service import _cfg_local
    assert getattr(_cfg_local, "map", None) in (None, {})


def test_only_arm_b_streams_progress():
    """Arms A and C run with on_opponent_done suppressed — publishing their
    cards mid-job would surface un-interleaved, un-attributed suggestions."""
    _run_res, calls = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                           c_cards=_cards(1, "c"), interleave=True)
    by_arm = {name: ov for name, _r4, ov in calls}
    assert by_arm["arm_b"] == {}
    assert by_arm["arm_a"] == {"on_opponent_done": None}
    assert by_arm["arm_c"] == {"on_opponent_done": None}


def test_arms_run_sequentially_in_generation_order():
    _run_res, calls = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                           c_cards=_cards(1, "c"), interleave=True)
    assert [name for name, _r4, _ov in calls] == ["arm_b", "arm_a", "arm_c"]


def test_a_raising_arm_is_recorded_not_fatal():
    def generate(**ov):
        return _cards(2, "b")

    def gen_v2(**ov):
        raise RuntimeError("divergence pipeline blew up")

    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: list(parts)), \
            _knobs(**PHASE3_KNOBS):
        run = bo.run_bakeoff(generate=generate, gen_v2=gen_v2,
                             league_id="l", interleave=True, limit=None,
                             roster=bo.ARMS)
    assert run.arms["gen_v2"].error is not None
    assert run.arms["gen_v2"].cards == []
    assert run.deck, "the surviving arms still produce a deck"
    row = run.run_row(job_id="j", user_id="u", league_id="l")
    import json
    assert json.loads(row["arms_json"])["gen_v2"]["empty"] is True


def test_dark_mode_logs_three_arms_but_serves_only_arm_b():
    a, b, c = _cards(3, "a"), _cards(3, "b"), _cards(3, "c")
    run, calls = _run(a_cards=a, b_cards=b, c_cards=c, interleave=False)

    assert len(calls) == 3, "all three arms still generate in dark mode"
    assert run.served_arm == "current"
    served = run.served_deck()
    assert [bo.card_key(x) for x in served] == [bo.card_key(x) for x in b]
    # Attribution still resolves for the served cards…
    for i, card in enumerate(served):
        assert run.attribution_for(card) == ("current", i)
    # …and the interleaved deck is still computed and logged.
    assert len(run.deck) == 9
    import json
    row = run.run_row(job_id="j", user_id="u", league_id="league_x")
    assert row["served_arm"] == "current"
    arms = json.loads(row["arms_json"])
    assert {k: v["cards"] for k, v in arms.items()} == \
        {"baseline": 3, "current": 3, "gen_v2": 3}


def test_dark_mode_attributes_a_served_card_another_arm_drafted_first():
    """In dark mode arm B's whole list is served, including trades the draft
    credited to another arm. Those served copies are attributed to the arm
    that actually produced them (`current`) at their own rank — never left
    unattributed."""
    dup = (["x"], ["y"])
    a = [FakeCard(*dup)]
    b = [FakeCard(["b0"], ["b0r"]), FakeCard(*dup)]
    run, _calls = _run(a_cards=a, b_cards=b, c_cards=[], interleave=False,
                       order=["baseline", "current", "gen_v2"])
    served = run.served_deck()
    assert run.attribution_for(served[0]) == ("current", 0)
    assert run.attribution_for(served[1]) == ("current", 1)


def test_run_row_carries_the_plan_s5_fields():
    import json
    a, b, c = _cards(4, "a"), _cards(4, "b"), _cards(1, "c")
    run, _ = _run(a_cards=a, b_cards=b, c_cards=c, interleave=True,
                  order=["baseline", "current", "gen_v2"])
    row = run.run_row(job_id="job1", user_id="u1", league_id="league_x")
    assert row["deck_job_id"] == "job1"
    assert json.loads(row["arm_order"]) == ["baseline", "current", "gen_v2"]
    assert row["served_arm"] is None            # interleaved
    assert row["deck_size"] == 9
    arms = json.loads(row["arms_json"])
    assert arms["gen_v2"]["cards"] == 1
    assert arms["gen_v2"]["forfeits"] == 2
    assert arms["gen_v2"]["empty"] is False
    assert arms["baseline"]["empty"] is False
    for arm in bo.ARMS:
        assert arms[arm]["gen_ms"] >= 0


def test_run_row_records_pairwise_agreement():
    import json
    dup = (["x"], ["y"])
    a = [FakeCard(*dup), FakeCard(["a1"], ["a1r"])]
    b = [FakeCard(*dup), FakeCard(["b1"], ["b1r"])]
    run, _ = _run(a_cards=a, b_cards=b, c_cards=[], interleave=True,
                  order=["baseline", "current", "gen_v2"])
    agree = json.loads(run.run_row(job_id="j", user_id="u",
                                   league_id="l")["agreement_json"])
    assert agree == {"baseline+current": 1}


# ---------------------------------------------------------------------------
# restore_order (§3.4 Channel 2 helper)
# ---------------------------------------------------------------------------

def test_restore_order_pins_injections_and_restores_the_interleave():
    fixed = _cards(4, "f")
    injected = FakeCard(["ly"], ["ly2"])
    resorted = [fixed[3], injected, fixed[0], fixed[2]]      # layer re-sorted
    out = bo.restore_order(fixed, resorted)
    assert out == [injected, fixed[0], fixed[2], fixed[3]]


def test_restore_order_keeps_drops_dropped():
    fixed = _cards(3, "f")
    out = bo.restore_order(fixed, [fixed[2], fixed[0]])
    assert out == [fixed[0], fixed[2]]


# ---------------------------------------------------------------------------
# fairness_threshold + config capture
# (docs/reviews/2026-08-18-trade-logic-archaeology.md — persisted nowhere
#  before this, so an arm comparison across client settings compared arms AND
#  thresholds at once)
# ---------------------------------------------------------------------------

class _ThrCard(FakeCard):
    def __init__(self, basis="divergence", relaxed=False, tag="x"):
        super().__init__([f"g{tag}"], [f"r{tag}"])
        self.basis = basis
        self.relaxed = relaxed


_THR_CFG = {"fairness_floor_divergence": 0.55,
            "relaxed_fairness_threshold": 0.55}


def test_effective_threshold_consensus_card_keeps_the_full_bar():
    # Consensus IS the board there, so the client's toggle applies in full.
    assert bo.effective_fairness_threshold(
        _ThrCard(basis="consensus"), 0.75, _THR_CFG) == 0.75


def test_effective_threshold_divergence_card_rides_the_floor():
    # Both members have real boards; the consensus check is an extreme-case
    # veto only. Recording 0.75 here would be a lie about what the card cleared.
    assert bo.effective_fairness_threshold(
        _ThrCard(basis="divergence"), 0.75, _THR_CFG) == 0.55


def test_effective_threshold_never_tightens_below_the_request():
    assert bo.effective_fairness_threshold(
        _ThrCard(basis="divergence"), 0.50, _THR_CFG) == 0.50
    assert bo.effective_fairness_threshold(
        _ThrCard(basis="consensus"), 0.50, _THR_CFG) == 0.50


def test_effective_threshold_relaxed_card_records_the_widened_band():
    # #189 stage 1 — reachable on an ORGANIC deck through the user's
    # acquire / trade-away position preferences, so this is not hypothetical.
    assert bo.effective_fairness_threshold(
        _ThrCard(basis="consensus", relaxed=True), 0.75, _THR_CFG) == 0.55


def test_effective_threshold_is_null_for_arm_c():
    # trade_gen_v2 takes no fairness_threshold at all — its bar is the gen2_*
    # stack. NULL is the fact, not a gap.
    assert bo.effective_fairness_threshold(
        _ThrCard(), None, _THR_CFG) is None


def test_run_records_the_threshold_per_arm_and_null_for_gen_v2():
    import json
    run, _ = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                  c_cards=_cards(1, "c"), interleave=True,
                  order=["baseline", "current", "gen_v2"], thr=0.75)
    assert run.arms["baseline"].fairness_threshold == 0.75
    assert run.arms["current"].fairness_threshold == 0.75
    assert run.arms["gen_v2"].fairness_threshold is None
    arms = json.loads(run.run_row(job_id="j", user_id="u",
                                  league_id="l")["arms_json"])
    assert arms["baseline"]["fairness_threshold"] == 0.75
    assert arms["gen_v2"]["fairness_threshold"] is None


def test_per_card_threshold_resolves_against_its_own_arm():
    a = [_ThrCard(basis="divergence", tag="a")]
    b = [_ThrCard(basis="consensus",  tag="b")]
    c = [_ThrCard(basis="divergence", tag="c")]
    run, _ = _run(a_cards=a, b_cards=b, c_cards=c, interleave=True,
                  order=["baseline", "current", "gen_v2"], thr=0.75)
    assert run.fairness_threshold_for(a[0]) == 0.55   # divergence floor
    assert run.fairness_threshold_for(b[0]) == 0.75   # consensus, full bar
    assert run.fairness_threshold_for(c[0]) is None   # arm C takes none


def test_arm_a_config_snapshot_is_taken_inside_the_profile():
    """The snapshot must happen INSIDE model_a() — outside it the overlay is
    gone and arm A would be recorded as if it ran on live defaults."""
    from backend.bakeoff_profiles import MODEL_A_PROFILE
    run, _ = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                  c_cards=[], interleave=True)
    a_cfg = run.arms["baseline"].config
    assert a_cfg, "arm A config was not captured"
    for key, val in MODEL_A_PROFILE.items():
        assert a_cfg[key] == val, key


def test_config_record_is_base_plus_arm_deltas():
    import json
    from backend.bakeoff_profiles import MODEL_A_PROFILE
    run, _ = _run(a_cards=_cards(1, "a"), b_cards=_cards(1, "b"),
                  c_cards=_cards(1, "c"), interleave=True)
    rec = run.config_record()
    assert rec["base"], "base config (arm `current`) missing"
    assert "fairness_floor_divergence" in rec["base"]
    # Arm C runs on live defaults, so it has nothing to say.
    assert rec["arm_delta"]["gen_v2"] == {}
    # Arm A's delta is exactly the profile keys whose values actually differ
    # from live — never a key the profile does not set.
    a_delta = rec["arm_delta"]["baseline"]
    assert a_delta, "arm A must differ from live defaults"
    assert set(a_delta) <= set(MODEL_A_PROFILE)
    for key, val in a_delta.items():
        assert val == MODEL_A_PROFILE[key]
    # And it survives the JSON round-trip the row actually stores.
    row = run.run_row(job_id="j", user_id="u", league_id="l")
    assert json.loads(row["config_json"])["arm_delta"]["baseline"] == a_delta
