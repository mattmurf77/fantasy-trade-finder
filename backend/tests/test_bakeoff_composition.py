"""trade.bakeoff — three-group deck composition (operator decision 2026-08-18).

Spec: docs/plans/three-model-bakeoff/scope-composition.md.

A 30-card deck built from three groups of ten, each split five value / five
outlook:

    group 1   arm `current`, basis `divergence`
    group 2   arm `current`, basis `consensus`
    group 3   arm `gen_v2`   (divergence by nature)

Contract under test:

  • Groups are derived from the arm ROSTER, and arm `baseline` is absent from
    the default roster — by configuration, with Phase 2's profile, golden and
    knob-inventory guard all still live (asserted here, not just next door).
  • Each group's quota is honoured: 5 value + 5 outlook, from that arm's cards
    at that basis, in the arm's own rank order.
  • The three GROUPS interleave — not the two arms. Asserted as a
    DISTRIBUTION over many decks, because a single draw proves nothing about
    position balance and position is the confound the whole design exists to
    remove.
  • Under-fill is recorded per (group, lane) and never silently backfilled.
  • An absent `lane` is its own bucket: never counted as value, never as
    outlook, and never allowed to empty a deck.
  • The knob kill values restore Phase 3 exactly.
"""

import statistics
from collections import Counter
from unittest.mock import patch

import pytest

from backend import bakeoff_runner as bo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class Card:
    """Minimal stand-in carrying what composition reads: identity, basis, lane."""

    _n = 0

    def __init__(self, basis="divergence", lane="value", target="opp", tag=None):
        Card._n += 1
        tag = tag or f"c{Card._n}"
        self.give_player_ids = [f"g_{tag}"]
        self.receive_player_ids = [f"r_{tag}"]
        self.target_user_id = target
        self.basis = basis
        self.lane = lane

    def __repr__(self):                      # pragma: no cover — debugging aid
        return f"<{self.basis[:4]}/{self.lane}:{self.give_player_ids[0]}>"


def _cards(spec):
    """spec = [(basis, lane, count), ...] → one flat arm-ranked list."""
    out = []
    for basis, lane, n in spec:
        out.extend(Card(basis, lane) for _ in range(n))
    return out


def _knobs(**vals):
    return patch.object(bo, "_cfg", lambda key, default: float(vals.get(key, default)))


def _order(fixed):
    return patch.object(bo, "draft_order_for",
                        lambda parts, lid, wk=None: [p for p in fixed if p in parts])


G1, G2, G3 = "current_divergence", "current_consensus", "gen_v2"


# ---------------------------------------------------------------------------
# Roster + group derivation
# ---------------------------------------------------------------------------

def test_default_roster_drops_arm_baseline_from_serving():
    with _knobs():
        assert bo.arm_roster() == ("current", "gen_v2")
        assert bo.ARM_BASELINE not in bo.arm_roster()


def test_arm_baseline_is_restored_by_a_knob_not_a_deploy():
    with _knobs(bakeoff_include_baseline=1.0):
        assert bo.arm_roster() == ("baseline", "current", "gen_v2")


def test_arm_a_leaves_serving_but_phase_2_stays_intact():
    """The operator's constraint: arm A is removed from the SERVED rotation by
    configuration, not by deleting Phase 2's work. The profile, its entry
    point and its knob inventory must all still be importable and correct —
    they cost nothing dark and the baseline may be wanted back."""
    from backend import bakeoff_profiles as bp
    import backend.trade_service as ts

    assert bp.MODEL_A_PROFILE and bp.MODEL_A_REFERENCE_SHA
    assert callable(bp.model_a)
    # Every pinned knob still exists — the guard the golden test enforces.
    assert set(bp.MODEL_A_PROFILE) <= set(ts._DEFAULT_CFG)
    # …and the entry point still applies the profile AND the R4 bypass.
    with bp.model_a():
        assert ts.r4_bypassed() is True
        assert ts._c("max_overpay_frac") == 0.0
    assert ts.r4_bypassed() is False


def test_groups_are_derived_from_the_roster():
    assert [g.key for g in bo.groups_for(("current", "gen_v2"))] == [G1, G2, G3]
    assert [(g.arm, g.basis) for g in bo.groups_for(("current", "gen_v2"))] == [
        ("current", "divergence"), ("current", "consensus"), ("gen_v2", None)]
    # Arm A back in ⇒ it gains the same divergence/consensus pair, no second knob.
    assert [g.key for g in bo.groups_for(bo.ARMS)] == [
        "baseline_divergence", "baseline_consensus", G1, G2, G3]


# ---------------------------------------------------------------------------
# Quotas
# ---------------------------------------------------------------------------

def test_group_takes_five_value_and_five_outlook_from_its_own_basis():
    arm = _cards([("divergence", "value", 8), ("divergence", "window", 8),
                  ("consensus", "value", 8), ("consensus", "window", 8)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    assert len(res.cards) == 10
    assert res.filled == {"value": 5, "outlook": 5, "fill": 0}
    assert res.short == {"value": 0, "outlook": 0}
    assert all(c.basis == "divergence" for c in res.cards), \
        "a group must never take a card from the other basis"
    assert Counter(c.lane for c in res.cards) == {"value": 5, "window": 5}


def test_group_keeps_the_arms_own_rank_order_within_each_lane():
    arm = _cards([("divergence", "value", 5), ("divergence", "window", 5)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    served_value = [c for c in res.cards if c.lane == "value"]
    assert served_value == [c for c in arm if c.lane == "value"], \
        "composition must not re-sort the generator's own ranking"


def test_group_alternates_lanes_so_neither_owns_the_front_half():
    arm = _cards([("divergence", "value", 5), ("divergence", "window", 5)])
    for leads in (False, True):
        res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                               size=10, value_slots=5, backfill=False,
                               outlook_leads=leads)
        lanes = [c.lane for c in res.cards]
        assert lanes[0] == ("window" if leads else "value")
        # Strict alternation ⇒ each lane holds exactly half of the front half.
        assert Counter(lanes[:5]) == {"value": 2 if leads else 3,
                                      "window": 3 if leads else 2}


def test_which_lane_leads_is_seeded_and_not_constant():
    """A constant leading lane would put the value lane in every group's slot
    0 in every deck — a within-group position bias on the exact axis the
    quota compares."""
    leads = [bo.outlook_leads_for(G1, f"league_{i}", "2026-W34")
             for i in range(200)]
    assert 60 < sum(leads) < 140, Counter(leads)
    # …and reproducible for a given league+week.
    assert (bo.outlook_leads_for(G1, "league_9", "2026-W34")
            == bo.outlook_leads_for(G1, "league_9", "2026-W34"))


def test_quota_knobs_move_the_split():
    arm = _cards([("divergence", "value", 9), ("divergence", "window", 9)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=6, value_slots=2, backfill=False)
    assert res.quota == {"size": 6, "value": 2, "outlook": 4}
    assert res.filled == {"value": 2, "outlook": 4, "fill": 0}


# ---------------------------------------------------------------------------
# Under-fill — the finding, not the failure
# ---------------------------------------------------------------------------

def test_outlook_shortfall_is_recorded_and_not_backfilled():
    """The expected case: `window` is ~25% of live supply, so a group
    routinely cannot find five outlook cards. It must SAY so — a silent
    cross-lane substitution would hide whether the arm can produce
    outlook-basis ideas at all.

    `reallocate=False` is the pre-D-086 composition: the slots the outlook
    lane could not fill are simply dropped."""
    arm = _cards([("divergence", "value", 20), ("divergence", "window", 2)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False,
                           reallocate=False)
    assert res.filled == {"value": 5, "outlook": 2, "fill": 0}
    assert res.short == {"value": 0, "outlook": 3}
    assert res.realloc == {"value": 0, "outlook": 0}
    assert len(res.cards) == 7, "the group serves short rather than backfilling"
    assert Counter(c.lane for c in res.cards)["value"] == 5, \
        "the value lane must not overflow into outlook slots"
    assert res.pool == {"value": 20, "window": 2, "(none)": 0}


def test_lane_reallocation_fills_the_group_without_softening_the_shortfall():
    """D-086 — the same group, with reallocation ON (the default).

    The three slots the outlook lane could not fill go to the value lane,
    which has its own cards to spare. The deck stops shrinking; `short` still
    reads {"outlook": 3} because it is measured against the NOMINAL 5/5 ask,
    and `realloc` names the spill so nothing is inferred."""
    arm = _cards([("divergence", "value", 20), ("divergence", "window", 2)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    assert len(res.cards) == 10, "reallocation fills the group"
    assert res.filled == {"value": 8, "outlook": 2, "fill": 0}
    assert res.short == {"value": 0, "outlook": 3}, \
        "the under-fill finding survives reallocation untouched"
    assert res.realloc == {"value": 3, "outlook": 0}
    assert res.pool == {"value": 20, "window": 2, "(none)": 0}
    # The distinction from bakeoff_fill_policy = 1: no card takes the OTHER
    # lane's slot, so every lane_slot stamp is still literally true.
    assert not [c for c in res.cards if res.slots[id(c)] == bo.SLOT_FILL]
    for c in res.cards:
        want = bo.SLOT_VALUE if c.lane == "value" else bo.SLOT_OUTLOOK
        assert res.slots[id(c)] == want


def test_lane_reallocation_is_a_no_op_when_both_lanes_meet_their_quota():
    """The rich case must be byte-identical to pre-D-086: reallocation only
    ever consumes slots a lane could not fill."""
    arm = _cards([("divergence", "value", 20), ("divergence", "window", 20)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.filled == {"value": 5, "outlook": 5, "fill": 0}
    assert res.short == {"value": 0, "outlook": 0}
    assert res.realloc == {"value": 0, "outlook": 0}


def test_lane_reallocation_runs_in_both_directions():
    """A value shortfall is reallocated to the outlook lane too — the rule is
    "slots follow supply", not "the value lane wins"."""
    arm = _cards([("divergence", "value", 2), ("divergence", "window", 20)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.filled == {"value": 2, "outlook": 8, "fill": 0}
    assert res.short == {"value": 3, "outlook": 0}
    assert res.realloc == {"value": 0, "outlook": 3}


def test_lane_reallocation_cannot_invent_supply():
    """A group that is genuinely short of CARDS still serves short — the
    D-086 ceiling is the group's own pool, never more."""
    arm = _cards([("divergence", "value", 3), ("divergence", "window", 1)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=False)
    assert len(res.cards) == 4
    assert res.filled == {"value": 3, "outlook": 1, "fill": 0}
    assert res.short == {"value": 2, "outlook": 4}
    assert res.realloc == {"value": 0, "outlook": 0}


def test_empty_group_is_data_not_an_error():
    res = bo.compose_group(bo.Group(G3, "gen_v2", None), [],
                           size=10, value_slots=5, backfill=False)
    assert res.cards == []
    assert res.short == {"value": 5, "outlook": 5}
    assert res.pool == {"value": 0, "window": 0, "(none)": 0}


def test_backfill_policy_fills_residual_slots_and_flags_every_substitute():
    """bakeoff_fill_policy = 1 substitutes ACROSS lanes: a value card takes an
    outlook slot and is flagged so no analysis mistakes it for a card that
    earned one. Asserted with reallocation off, which is when the cross-lane
    substitution is actually reachable."""
    arm = _cards([("divergence", "value", 20), ("divergence", "window", 2)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=True,
                           reallocate=False)
    assert len(res.cards) == 10
    assert res.filled == {"value": 5, "outlook": 2, "fill": 3}
    # The shortfall is STILL recorded — the backfill hides nothing.
    assert res.short == {"value": 0, "outlook": 3}
    fills = [c for c in res.cards if res.slots[id(c)] == bo.SLOT_FILL]
    assert len(fills) == 3
    assert all(c.lane == "value" for c in fills), \
        "a fill came from the group's own other lane"


def test_reallocation_leaves_backfill_only_the_unlabelled_remainder():
    """The two policies compose without double-counting: reallocation drains
    both lane buckets first, so a `fill` under D-086 can only be a card that
    carried no lane at all — exactly the bucket that has no quota to earn."""
    arm = _cards([("divergence", "value", 6), ("divergence", "window", 1),
                  ("divergence", None, 8)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=True)
    assert res.filled == {"value": 6, "outlook": 1, "fill": 3}
    assert res.short == {"value": 0, "outlook": 4}
    assert res.realloc == {"value": 1, "outlook": 0}
    fills = [c for c in res.cards if res.slots[id(c)] == bo.SLOT_FILL]
    assert all(c.lane is None for c in fills), \
        "both lane buckets were already exhausted by reallocation"


def test_backfill_never_crosses_the_groups_basis():
    arm = _cards([("divergence", "value", 6), ("consensus", "value", 50),
                  ("consensus", "window", 50)])
    res = bo.compose_group(bo.Group(G1, "current", "divergence"), arm,
                           size=10, value_slots=5, backfill=True)
    assert all(c.basis == "divergence" for c in res.cards)
    # Only one leftover divergence card exists, so the group still runs short.
    assert len(res.cards) == 6
    assert res.short == {"value": 0, "outlook": 5}


# ---------------------------------------------------------------------------
# The absent-lane rule
# ---------------------------------------------------------------------------

def test_absent_lane_is_its_own_bucket_and_fills_neither_quota():
    """`lane=None` means the outlook axis is undefined for the user, not that
    the card is value-shaped. Counting it as value would inflate the value
    lane with cards nobody classified."""
    arm = _cards([("consensus", "value", 3), ("consensus", None, 40)])
    res = bo.compose_group(bo.Group(G2, "current", "consensus"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.pool == {"value": 3, "window": 0, "(none)": 40}
    assert res.filled == {"value": 3, "outlook": 0, "fill": 0}
    assert res.short == {"value": 2, "outlook": 5}
    assert all(c.lane == "value" for c in res.cards), \
        "an unlabelled card must never be served as if it filled a lane quota"


def test_absent_lane_cards_are_reachable_only_as_flagged_fill():
    arm = _cards([("consensus", "value", 3), ("consensus", None, 40)])
    res = bo.compose_group(bo.Group(G2, "current", "consensus"), arm,
                           size=10, value_slots=5, backfill=True)
    assert len(res.cards) == 10
    fills = [c for c in res.cards if res.slots[id(c)] == bo.SLOT_FILL]
    assert len(fills) == 7 and all(c.lane is None for c in fills)


def test_a_wholly_unlabelled_pool_turns_the_split_off_instead_of_emptying_the_deck():
    """Every card is unlabelled when the user has no window direction
    (`not_sure` / None outlook) or `trade.lanes` is off. Quota'ing on an axis
    that does not exist would serve an EMPTY deck to those users under the
    leave-short default — a measurement artefact AND real user harm. The split
    goes inert for that group instead, and the row says so."""
    arm = _cards([("consensus", None, 30)])
    res = bo.compose_group(bo.Group(G2, "current", "consensus"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.lane_split_active is False
    assert len(res.cards) == 10, "top-N by arm rank, not an empty group"
    assert res.cards == arm[:10]
    assert all(res.slots[id(c)] == bo.SLOT_FILL for c in res.cards), \
        "no card may claim to have filled a lane quota when there is no axis"
    assert res.short == {"value": 5, "outlook": 5}


def test_one_labelled_card_is_enough_to_keep_the_split_honest():
    arm = _cards([("consensus", "window", 1), ("consensus", None, 30)])
    res = bo.compose_group(bo.Group(G2, "current", "consensus"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.lane_split_active is True
    assert res.filled == {"value": 0, "outlook": 1, "fill": 0}
    assert res.short == {"value": 5, "outlook": 4}


# ---------------------------------------------------------------------------
# The three-group interleave
# ---------------------------------------------------------------------------

def _compose(arm_lists, league="league_x", week="2026-W34", **knobs):
    with _knobs(**knobs):
        return bo.compose_deck(arm_lists, league_id=league, iso_week=week,
                               roster=bo.arm_roster(), limit=bo.deck_limit())


def test_three_groups_are_the_interleaving_participants():
    cur = _cards([("divergence", "value", 20), ("divergence", "window", 20),
                  ("consensus", "value", 20), ("consensus", "window", 20)])
    v2 = _cards([("divergence", "value", 20), ("divergence", "window", 20)])
    groups, order, draft = _compose({"current": cur, "gen_v2": v2})

    assert sorted(order) == sorted([G1, G2, G3])
    assert len(draft.deck) == 30, "three groups of ten"
    seq = [draft.group_attribution[id(c)][0] for c in draft.deck]
    # Strict rotation ⇒ no group ever holds two consecutive slots.
    assert all(a != b for a, b in zip(seq, seq[1:]))
    assert Counter(seq) == {G1: 10, G2: 10, G3: 10}


def test_grouping_by_arm_would_bury_arm_c_and_the_group_draft_does_not():
    """The failure this design exists to prevent, measured. Arm `current`
    holds two of the three groups; hand the deck out per ARM and its twenty
    cards land ahead of arm `gen_v2`'s ten, which then sit in the deck's tail
    — reintroducing the position confound (acceptance falls ~27% across a
    session from position alone) with no visible symptom."""
    cur = _cards([("divergence", "value", 15), ("divergence", "window", 15),
                  ("consensus", "value", 15), ("consensus", "window", 15)])
    v2 = _cards([("divergence", "value", 15), ("divergence", "window", 15)])
    groups, _order, draft = _compose({"current": cur, "gen_v2": v2})

    # Naive alternative: each group composed the same way, then concatenated
    # arm by arm.
    by_arm_deck = (groups[G1].cards + groups[G2].cards + groups[G3].cards)
    by_arm_pos = statistics.mean(
        i for i, c in enumerate(by_arm_deck) if c in groups[G3].cards)
    assert by_arm_pos == pytest.approx(24.5),         "per-arm concatenation puts arm C's whole group in the deck's tail"

    by_group_pos = statistics.mean(
        i for i, c in enumerate(draft.deck)
        if draft.attribution[id(c)][0] == "gen_v2")
    # Interleaved, arm C sits at the deck's centre of mass like everyone else.
    assert by_group_pos == pytest.approx(14.5, abs=1.0)


def test_group_positions_are_balanced_across_many_decks():
    """The measurement guarantee, asserted as a DISTRIBUTION: across many
    decks no group systematically occupies better deck positions. A single
    draw cannot show this — the rotation is seeded per deck, so any one deck
    has a first-mover."""
    positions = {G1: [], G2: [], G3: []}
    firsts = Counter()
    for i in range(300):
        cur = _cards([("divergence", "value", 8), ("divergence", "window", 8),
                      ("consensus", "value", 8), ("consensus", "window", 8)])
        v2 = _cards([("divergence", "value", 8), ("divergence", "window", 8)])
        with _knobs():
            groups, order, draft = bo.compose_deck(
                {"current": cur, "gen_v2": v2}, league_id=f"league_{i}",
                iso_week="2026-W34", roster=bo.arm_roster(),
                limit=bo.deck_limit())
        firsts[order[0]] += 1
        for pos, card in enumerate(draft.deck):
            positions[draft.group_attribution[id(card)][0]].append(pos)

    means = {g: statistics.mean(v) for g, v in positions.items()}
    assert max(means.values()) - min(means.values()) < 0.35, means
    assert min(firsts.values()) > 60, firsts


def test_lane_positions_are_balanced_across_many_decks():
    """Same guarantee one level down: neither LANE may systematically sit
    ahead of the other, or a value-vs-outlook comparison measures position."""
    by_lane = {"value": [], "window": []}
    for i in range(300):
        cur = _cards([("divergence", "value", 8), ("divergence", "window", 8),
                      ("consensus", "value", 8), ("consensus", "window", 8)])
        v2 = _cards([("divergence", "value", 8), ("divergence", "window", 8)])
        with _knobs():
            _g, _o, draft = bo.compose_deck(
                {"current": cur, "gen_v2": v2}, league_id=f"league_{i}",
                iso_week="2026-W34", roster=bo.arm_roster(),
                limit=bo.deck_limit())
        for pos, card in enumerate(draft.deck):
            by_lane[card.lane].append(pos)
    means = {k: statistics.mean(v) for k, v in by_lane.items()}
    assert abs(means["value"] - means["window"]) < 0.6, means


def test_interleave_credits_arm_rank_from_the_arms_own_full_list():
    """`group_rank` is position inside the group; `arm_rank` stays the
    generator's own ranking. They answer different questions, so both are
    recorded and neither is derived from the other."""
    cur = _cards([("divergence", "value", 3), ("divergence", "window", 3)])
    v2 = _cards([("divergence", "value", 3)])
    with _order([G1, G2, G3]):
        _g, _o, draft = _compose({"current": cur, "gen_v2": v2})
    for card in draft.deck:
        arm, arm_rank = draft.attribution[id(card)]
        gkey, grank, slot = draft.group_attribution[id(card)]
        src = cur if arm == "current" else v2
        assert src[arm_rank] is card, "arm_rank must index the arm's own list"
        assert slot in (bo.SLOT_VALUE, bo.SLOT_OUTLOOK, bo.SLOT_FILL)
        assert gkey in (G1, G2, G3) and grank >= 0


def test_a_trade_two_arms_both_found_is_served_once_and_credited_to_the_first():
    shared = ("divergence", "value")
    dup_cur = Card(*shared, tag="dup")
    dup_v2 = Card(*shared, tag="dup")          # same give/receive/target ⇒ same key
    cur = [dup_cur] + _cards([("divergence", "value", 4),
                              ("divergence", "window", 5)])
    v2 = [dup_v2] + _cards([("divergence", "value", 4),
                            ("divergence", "window", 5)])
    with _order([G1, G2, G3]):
        _g, _o, draft = _compose({"current": cur, "gen_v2": v2})

    keys = [bo.card_key(c) for c in draft.deck]
    assert keys.count(bo.card_key(dup_cur)) == 1
    winner = next(c for c in draft.deck if bo.card_key(c) == bo.card_key(dup_cur))
    assert draft.attribution[id(winner)][0] == "current"       # G1 drafts first
    assert draft.also_proposed_by[id(winner)] == ["gen_v2"], \
        "agreement is per ARM — the signal worth having"


def test_deck_limit_caps_the_composed_deck():
    cur = _cards([("divergence", "value", 20), ("divergence", "window", 20),
                  ("consensus", "value", 20), ("consensus", "window", 20)])
    v2 = _cards([("divergence", "value", 20), ("divergence", "window", 20)])
    _g, _o, draft = _compose({"current": cur, "gen_v2": v2},
                             bakeoff_deck_limit=12.0)
    assert len(draft.deck) == 12


# ---------------------------------------------------------------------------
# Kill values restore Phase 3
# ---------------------------------------------------------------------------

def test_group_size_zero_kills_composition_entirely():
    with _knobs(bakeoff_group_size=0.0):
        groups, order, draft = bo.compose_deck(
            {"current": _cards([("divergence", "value", 3)])},
            league_id="l", iso_week="2026-W34")
    assert groups == {} and order == [] and draft.deck == []


def test_phase3_kill_values_restore_the_uncapped_three_arm_draft():
    a = _cards([("divergence", "value", 4)])
    b = _cards([("divergence", "value", 4)])
    c = _cards([("divergence", "value", 4)])

    def generate(**ov):
        from backend.trade_service import _cfg_local
        overlay = getattr(_cfg_local, "map", None) or {}
        return list(a if overlay.get("max_overpay_frac") == 0.0 else b)

    with _knobs(bakeoff_group_size=0.0, bakeoff_deck_limit=0.0,
                bakeoff_include_baseline=1.0), _order(list(bo.ARMS)):
        run = bo.run_bakeoff(generate=generate, gen_v2=lambda **ov: list(c),
                             league_id="l", iso_week="2026-W34", interleave=True)

    assert set(run.arms) == set(bo.ARMS), "arm A generates again"
    assert run.groups == {}
    assert len(run.deck) == 12, "uncapped: the draft drains every arm"
    assert [run.attribution_for(x)[0] for x in run.deck[:3]] == list(bo.ARMS)
    assert run.group_for(run.deck[0]) is None


# ---------------------------------------------------------------------------
# run_bakeoff end to end + the bakeoff_runs row
# ---------------------------------------------------------------------------

def _run(cur, v2, **knobs):
    with _knobs(**knobs), _order([G1, G2, G3]):
        return bo.run_bakeoff(
            generate=lambda **ov: list(cur), gen_v2=lambda **ov: list(v2),
            league_id="league_x", iso_week="2026-W34", interleave=True)


def test_lane_reallocation_is_wired_to_its_knob_end_to_end():
    """The D-086 revert lever must be real: `bakeoff_lane_reallocate` = 0 has
    to reach `compose_group` through `compose_deck`, not just exist."""
    import json
    cur = _cards([("divergence", "value", 20), ("divergence", "window", 2),
                  ("consensus", "value", 20), ("consensus", "window", 20)])
    v2 = _cards([("divergence", "value", 20)])

    on = json.loads(_run(cur, v2).run_row(job_id="j", user_id="u",
                                          league_id="l")["groups_json"])
    off = json.loads(_run(cur, v2, bakeoff_lane_reallocate=0.0)
                     .run_row(job_id="j", user_id="u",
                              league_id="l")["groups_json"])

    assert on[G1]["filled"]["value"] == 8 and on[G3]["composed"] == 10
    assert off[G1]["filled"]["value"] == 5 and off[G3]["composed"] == 5
    # The finding the deck size used to carry is on the record either way.
    assert on[G1]["short"] == off[G1]["short"] == {"value": 0, "outlook": 3}
    assert on[G3]["short"] == off[G3]["short"] == {"value": 0, "outlook": 5}
    assert off[G1]["realloc"] == {"value": 0, "outlook": 0}


def test_measured_prod_shape_reaches_the_group_size():
    """Regression on the actual 2026-08-19 defect (D-086).

    The two 10:33 runs recorded pools of value 7 / window 0 (group 1),
    value 10 / window 0 (group 2) and value 13 / window 3 (group 3) and served
    an 18-card deck: every group's outlook quota went unfilled AND the value
    cards that could have taken those slots were dropped. Same pools, D-086
    on: 27 cards, the ceiling this supply allows against a 30-card target."""
    cur = (_cards([("divergence", "value", 7)])
           + _cards([("consensus", "value", 10)]))
    v2 = _cards([("divergence", "value", 13), ("divergence", "window", 3)])
    import json
    row = _run(cur, v2).run_row(job_id="j", user_id="u", league_id="l")
    groups = json.loads(row["groups_json"])

    assert [groups[k]["composed"] for k in (G1, G2, G3)] == [7, 10, 10]
    assert row["deck_size"] == 27
    # Group 1 could not reach ten — it had seven cards. That is supply, and it
    # is still reported as such.
    assert groups[G1]["short"] == {"value": 0, "outlook": 5}
    assert groups[G1]["realloc"] == {"value": 2, "outlook": 0}


def test_default_run_generates_only_the_rostered_arms():
    seen = []

    def generate(**ov):
        seen.append("engine")
        return _cards([("divergence", "value", 5)])

    with _knobs(), _order([G1, G2, G3]):
        run = bo.run_bakeoff(generate=generate,
                             gen_v2=lambda **ov: _cards([("divergence", "value", 5)]),
                             league_id="l", iso_week="2026-W34", interleave=True)
    assert set(run.arms) == {"current", "gen_v2"}
    assert len(seen) == 1, "the engine must not be run for an unrostered arm A"
    assert bo.ARM_BASELINE not in run.arms


def test_run_row_records_the_per_group_under_fill():
    import json
    cur = _cards([("divergence", "value", 20), ("divergence", "window", 2),
                  ("consensus", "value", 20), ("consensus", "window", 20)])
    v2 = _cards([("divergence", "value", 20)])
    run = _run(cur, v2)
    row = run.run_row(job_id="j", user_id="u", league_id="l")
    groups = json.loads(row["groups_json"])

    assert set(groups) == {G1, G2, G3}
    assert groups[G1]["short"] == {"value": 0, "outlook": 3}
    assert groups[G1]["filled"] == {"value": 8, "outlook": 2, "fill": 0}
    assert groups[G1]["realloc"] == {"value": 3, "outlook": 0}
    assert groups[G1]["pool"] == {"value": 20, "window": 2, "(none)": 0}
    assert groups[G2]["short"] == {"value": 0, "outlook": 0}
    # Arm C produced no outlook cards at all — the shortfall is recorded in
    # full even though the value lane went on to use the slots (D-086).
    assert groups[G3]["short"] == {"value": 0, "outlook": 5}
    assert groups[G3]["realloc"] == {"value": 5, "outlook": 0}
    assert groups[G3]["composed"] == 10 and groups[G3]["served"] == 10
    assert groups[G3]["arm"] == "gen_v2" and groups[G3]["basis"] is None
    assert row["deck_size"] == 10 + 10 + 10


def test_run_row_group_summary_is_empty_when_composition_is_killed():
    import json
    run = _run(_cards([("divergence", "value", 3)]),
               _cards([("divergence", "value", 3)]),
               bakeoff_group_size=0.0)
    assert json.loads(
        run.run_row(job_id="j", user_id="u", league_id="l")["groups_json"]) == {}


# ---------------------------------------------------------------------------
# Measured under-fill on the operator's live distribution
# ---------------------------------------------------------------------------

def test_measured_under_fill_across_realistic_divergence_supply():
    """Not a knob check — a measurement, pinned so a future change to the
    quota or the lane rule shows up as a number rather than a vibe.

    The lane RATIO is the live 2026-08-18 one (divergence: 798 value / 193
    window / 0 unlabelled ⇒ 19.5% window; consensus: 1455 / 585 / 132 ⇒ 26.8%
    window). Per-deck SUPPLY is not knowable from those totals, so it is
    swept: a divergence group needs roughly 5 / 0.195 ≈ 26 surviving cards
    before it can expect to fill five outlook slots, and every arm that
    produces fewer serves short.

    The point of the numbers is the asymmetry they show. The consensus group
    fills both lanes from a much smaller pool; the divergence groups need
    ~1.4× the supply to do the same, so under-fill on groups 1 and 3 is the
    normal case rather than the exception — which is exactly why the default
    policy records the hole instead of topping it up from the value lane.
    """
    def _supply(n, value_frac, none_frac=0.0, basis="divergence", seed=0):
        import random as _r
        n_none = int(round(n * none_frac))
        n_val = int(round((n - n_none) * value_frac))
        pool = _cards([(basis, "value", n_val),
                       (basis, "window", n - n_none - n_val),
                       (basis, None, n_none)])
        _r.Random(seed).shuffle(pool)
        return pool

    div_short, con_short = {}, {}
    for n in (10, 20, 30, 40, 60):
        d, c = [], []
        for i in range(60):
            gd = bo.compose_group(
                bo.Group(G1, "current", "divergence"),
                _supply(n, 0.805, 0.0, "divergence", seed=i),
                size=10, value_slots=5, backfill=False)
            gc = bo.compose_group(
                bo.Group(G2, "current", "consensus"),
                _supply(n, 0.732, 0.061, "consensus", seed=i),
                size=10, value_slots=5, backfill=False)
            d.append(gd.short["outlook"])
            c.append(gc.short["outlook"])
        div_short[n] = statistics.mean(d)
        con_short[n] = statistics.mean(c)

    # The measured curve (outlook slots left empty, out of 5):
    #     supply      10    20    30    40    60
    #     divergence   3     1     0     0     0
    #     consensus    3     0     0     0     0
    assert [div_short[n] for n in (10, 20, 30, 40, 60)] == [3, 1, 0, 0, 0]
    assert [con_short[n] for n in (10, 20, 30, 40, 60)] == [3, 0, 0, 0, 0]
    # A thin arm misses 3 of its 5 outlook slots — the shortfall the run row
    # records rather than papering over.
    assert div_short[10] == 3
    # Consensus clears its outlook quota at 20 surviving cards; divergence
    # still cannot, and needs ~30. That gap is why groups 1 and 3 are the
    # ones expected to serve short.
    assert con_short[20] == 0.0 and div_short[20] > 0.0
    # Monotone in supply — more cards can only help.
    assert all(div_short[a] >= div_short[b]
               for a, b in zip((10, 20, 30, 40), (20, 30, 40, 60)))


def test_unlabelled_consensus_share_never_leaks_into_a_lane_quota():
    """4.2% of live consensus cards carry no lane (132 of 3,163). None of them
    may be served as if it filled a value or outlook slot."""
    arm = _cards([("consensus", "value", 40), ("consensus", "window", 16),
                  ("consensus", None, 4)])
    res = bo.compose_group(bo.Group(G2, "current", "consensus"), arm,
                           size=10, value_slots=5, backfill=False)
    assert res.pool["(none)"] == 4
    assert res.filled == {"value": 5, "outlook": 5, "fill": 0}
    assert all(c.lane is not None for c in res.cards)
