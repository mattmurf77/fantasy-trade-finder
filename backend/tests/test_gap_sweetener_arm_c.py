"""2026-08-21 gap auto-sweetener — bake-off arm C (`trade_gen_v2`).

The v1 sweetener (`backend/tests/test_gap_sweetener.py`) hooked the v2
divergence generator, the consensus generator and the v3 optimizer, and
deliberately deferred arm C. Arm C still INHERITED the companion change —
the trade-wide package benchmark, which WIDENS absolute consensus gaps —
through `_consensus_packages` at card-build time, so it got the widener
without the closer: its measured share of cards over one late 1st (1539)
sat at 13.6% / 10.5% on the two fixtures while every other served arm read
0–5.3%.

Arm C is not a fourth copy of the same hook, and these tests pin the three
things that make it different (docs/plans/package-benchmark-sweetener/
scope-arm-c.md §0):

  * §0a **placement** — the sweetener runs inside `_pair_survivors` and
    REBUILDS the `_Candidate`, not at the card-build call to
    `_consensus_packages`. Ten derived fields (dedup keys, MESO variants,
    the rationale, `classify_package_shape`'s `len(ids) == 1`
    "consolidation" label, `card.health`, the fairness/mismatch/composite
    scores and the Stage 6/7 exposure+tier ranking) are computed from the
    candidate, so a late sweetener would leave every one of them
    describing the unsweetened trade — arm C's larger analogue of the v3
    stale-`fit_premium` defect;
  * §0b **pools** — arm C prunes in two layers. The SEMANTIC layer
    (`user_assets` = on both boards and not untouchable; `extras_all` =
    divergence-positive and not not-interested) is the equalizer universe
    and is inviolable. The BUDGET layer (`[:gen2_give_pool]`,
    `[:gen2_recv_extra_pool]`) is enumeration cost only, and the sweetener
    deliberately reaches past it;
  * §0c **fairness** — `close_value_gap` is called with
    `fairness_threshold=0.0` because its built-in ratio gate is the
    v2/v3 `_consensus_packages` notion; arm C's real gate is the
    `consolidated_value` band, re-earned in `extra_ok_fn`.

All fixtures are literals (golden hygiene); flags/_cfg snapshot-restored.
"""

import math
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_gen_v2 import (
    consolidated_value,
    generate_league_suggestions,
)
from backend.trade_optimizer import _consensus_packages
from backend.trade_service import League, LeagueMember, elo_to_value

GAP_LINE = 1539.0


@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _elo_for_value(value: float) -> float:
    """Inverse of elo_to_value at the default curve (k=0.005, ref 1500)."""
    return 1500.0 + math.log(value / 1000.0) / 0.005


# Lineup-feasible filler: 1 QB, 2 RB, 2 WR, 1 TE. At 200 these sit under
# the #141 absolute floor (asset_floor_abs 450), so they can never be
# chosen as an equalizer and never muddy the selection.
_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{k}": pos for k, pos in _BASE_POS.items()}


# ── fixture ────────────────────────────────────────────────────────────────
#
# The organic card is the 1-for-1 G -> R:
#   consensus  G 10000, R 11600  -> displayed gap 1687 (> 1539), and the
#              consolidated band ratio is 0.862 (>= 1 - gen2_band = 0.85),
#              so the card PASSES every arm-C gate and is emitted with a
#              gap the ratio gate cannot see. That is the whole defect.
#   user board R 13000 (the divergence claim), G 10000
#   opp  board G 11500 (why they say yes),    R 11000
#
# X1 (3000) is the intended equalizer: it clears the #141 filler floor and
# closes the displayed gap 1600 -> 86 at band ratio 0.937.
#
# X2 (2600) is the decoy, and it is deliberately CHEAPER than X1 so
# `close_value_gap`'s cheapest-first ordering reaches it FIRST. It is well
# above `asset_floor_abs` and would close the gap on value alone — but
# #141 measures the headliner on max(user board, opponent board), so the
# floor is 0.25 x 11500 = 2875, and X2 misses it. Any wiring that does not
# re-earn arm C's own `filler_ok` picks X2 and these tests fail.
_VALUES = {
    "seed": {"G": 10000.0, "R": 11600.0, "X1": 3000.0, "X2": 2600.0},
    "user": {"G": 10000.0, "R": 13000.0, "X1": 3000.0, "X2": 2600.0},
    "opp":  {"G": 11500.0, "R": 11000.0, "X1": 3000.0, "X2": 2600.0},
}


def _league(extra_user_assets=None, untouchable=None, not_interested=None):
    """Arm C needs a BOARDED opponent (has_rankings + elo_ratings) — the
    divergence claim is meaningless without two real boards.

    ``extra_user_assets`` = {pid: (seed, user, opp, position)} appended to
    the user's roster; used to push X1 out of the `[:gen2_give_pool]`
    budget slice without removing it from `user_assets`.
    """
    extra_user_assets = extra_user_assets or {}
    seed, uboard, oboard = (dict(_VALUES["seed"]), dict(_VALUES["user"]),
                            dict(_VALUES["opp"]))
    spec = {pid: "WR" for pid in seed}
    for pid, (sv, uv, ov, pos) in extra_user_assets.items():
        seed[pid], uboard[pid], oboard[pid], spec[pid] = sv, uv, ov, pos
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        seed[pid] = uboard[pid] = oboard[pid] = 200.0

    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = (["G", "X1", "X2"] + list(extra_user_assets)
                   + list(_bodies("u")))
    opp_roster = ["R"] + list(_bodies("o"))

    to_elo = lambda d: {p: _elo_for_value(v) for p, v in d.items()}  # noqa: E731
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings=to_elo(oboard), has_rankings=True)
    league = League(league_id="L1", name="T", platform="demo", members=[opp])
    return dict(
        players=players, league=league, user_id="user",
        user_elo=to_elo(uboard), user_roster=user_roster,
        seed_elo=to_elo(seed), scoring_format="1qb_ppr",
        untouchable_ids=set(untouchable or ()),
        not_interested_ids=set(not_interested or ()),
    )


def _cards(**over):
    kw = _league(**over)
    cards, report = generate_league_suggestions(**kw)
    return cards, report, kw


def _g_for_r(cards):
    """The organic G -> R card family (receive side is exactly R)."""
    return [c for c in cards if c.receive_player_ids == ["R"]]


# ── 1. the headline contract ───────────────────────────────────────────────

def test_arm_c_gap_card_is_sweetened_at_default():
    cards, report, _ = _cards()
    fam = _g_for_r(cards)
    assert fam, "fixture no longer yields the G->R arm-C card"
    sweet = [c for c in fam if c.gap_sweetener]
    assert sweet, "arm C big-gap card was not sweetened"
    c = sweet[0]
    assert c.gap_sweetener["side"] == "give"
    assert c.gap_sweetener["player_id"] == "X1", "not the smallest sufficient"
    assert c.gap_sweetener["player_id"] in c.give_player_ids
    assert c.gap_sweetener["gap_before"] > GAP_LINE
    assert c.gap_sweetener["gap_after"] <= GAP_LINE
    assert abs(c.give_value - c.receive_value) <= GAP_LINE
    assert report.gap_sweetened >= 1


def test_arm_c_decoy_equalizer_is_never_chosen():
    """X2 is on both boards, untouched, and CHEAPER than X1 — so
    cheapest-first ordering offers it to the gate stack first. It must be
    rejected by arm C's own #141 filler floor (0.25 x 11500 = 2875) and
    the search must continue to X1 rather than stopping at the first
    arithmetically-sufficient asset."""
    cards, report, _ = _cards()
    sweet = [c for c in cards if c.gap_sweetener]
    # asserted positively so this cannot pass vacuously on a tree where
    # nothing sweetens at all
    assert sweet, "nothing was sweetened — the decoy check would be vacuous"
    assert report.gap_sweetened >= 1
    for c in sweet:
        assert c.gap_sweetener["player_id"] != "X2"
        assert "X2" not in c.give_player_ids


# ── 2. the deploy-free kill value (arm A's pin) ────────────────────────────

def test_arm_c_sabotage_disable_brings_the_gap_card_back():
    """THE sabotage check: knob at 0 => the exact gap card reappears,
    unsweetened, carrying its full gap."""
    ts._cfg["sweetener_gap_threshold"] = 0.0
    cards, report, _ = _cards()
    fam = _g_for_r(cards)
    assert fam, "fixture no longer yields the G->R arm-C card"
    assert all(c.gap_sweetener is None for c in cards)
    assert report.gap_sweetened == 0
    assert [c for c in fam
            if abs(c.give_value - c.receive_value) > GAP_LINE], \
        "expected the unsweetened gap card to reappear"


def test_arm_c_kill_value_is_a_byte_identical_no_op():
    """Stronger than the sabotage half: at threshold 0 EVERY card must be
    identical to the pre-sweetener deck, field for field — not merely
    unsweetened. This is what makes the knob a real rollback lever."""
    def deck(thr):
        ts._cfg["sweetener_gap_threshold"] = thr
        cards, _, _ = _cards()
        return [(c.give_player_ids, c.receive_player_ids, c.give_value,
                 c.receive_value, c.fairness_score, c.mismatch_score,
                 c.composite_score, c.tier, c.health, c.rationale,
                 c.gap_sweetener) for c in cards]

    off = deck(0.0)
    # A negative threshold is the same disabled branch; a huge one can
    # never fire because no gap exceeds it. Both must equal the off deck.
    assert deck(-1.0) == off
    assert deck(10 ** 9) == off
    # ...and the disabled deck must still be the PRE-SWEETENER deck, not
    # merely self-consistent: the organic 1-for-1, at its original prices
    # and its original 0.862 band ratio, gap intact and above the line.
    # Pinned as literals so any drift in the disabled path is caught here
    # rather than silently rebaselined.
    assert len(off) == 1
    give, recv, gv, rv, fairness = off[0][:5]
    assert (give, recv) == (["G"], ["R"])
    assert (gv, rv) == (10000.0, 11600.0)
    assert fairness == 0.862
    assert abs(gv - rv) == 1600.0 > GAP_LINE
    assert off[0][-1] is None


# ── 3. §0a — the annotation-coherence regression ───────────────────────────

def test_arm_c_sweetened_card_annotations_describe_the_sweetened_trade():
    """The §0a defect, pinned. Every derived field on a sweetened card
    must be recomputed from the sweetened ids. Sweetening at the
    card-build `_consensus_packages` call (the textually obvious spot)
    fails every assertion below."""
    cards, _, kw = _cards()
    sweet = [c for c in _g_for_r(cards) if c.gap_sweetener]
    assert sweet
    c = sweet[0]
    cval = {p: elo_to_value(e) for p, e in kw["seed_elo"].items()}
    uval = _VALUES["user"]
    oval = _VALUES["opp"]

    # give side really carries the equalizer
    assert set(c.give_player_ids) == {"G", "X1"}

    # displayed values ARE the sweetened package values
    gv, rv = _consensus_packages(c.give_player_ids, c.receive_player_ids,
                                 lambda p: cval[p])
    assert c.give_value == round(gv, 1)
    assert c.receive_value == round(rv, 1)

    # fairness_score is the sweetened consolidated band ratio, NOT the
    # organic 1-for-1 ratio of 0.862
    gc = consolidated_value([cval[p] for p in c.give_player_ids])
    rc = consolidated_value([cval[p] for p in c.receive_player_ids])
    assert c.fairness_score == round(min(gc, rc) / max(gc, rc), 3)
    assert c.fairness_score > 0.87, "still showing the pre-sweetener ratio"

    # health's own-board gains are the sweetened ones
    ug = (consolidated_value([uval[p] for p in c.receive_player_ids])
          - consolidated_value([uval[p] for p in c.give_player_ids]))
    og = (consolidated_value([oval[p] for p in c.give_player_ids])
          - consolidated_value([oval[p] for p in c.receive_player_ids]))
    assert c.health["ir_margin_user"] == round(ug - ts._cfg["gen2_epsilon"], 1)
    assert c.health["ir_margin_opp"] == round(og - ts._cfg["gen2_epsilon"], 1)
    assert c.health["fairness_ratio"] == c.fairness_score

    # the rationale's give side lists BOTH positions — this is the
    # `classify_package_shape` / `_timeline_fit` surface, whose
    # "consolidation" label is literally `len(ids) == 1`
    why = c.rationale["counterparty"]["why_yes"]
    assert c.rationale["user"]["own_board_gain"] == round(ug, 1)
    assert c.rationale["counterparty"]["own_board_gain"] == round(og, 1)
    assert isinstance(why["timeline_fit"], (str, type(None)))


# ── 4. §0b — pool containment, the round-2 lesson ──────────────────────────

def test_arm_c_equalizer_never_uses_an_untouchable():
    """SEMANTIC layer: untouchables are excluded from `user_assets`, so
    they can never be an equalizer even though X1 would otherwise be the
    perfect one. The card must ship unsweetened rather than cheat."""
    cards, report, _ = _cards(untouchable={"X1"})
    for c in cards:
        assert "X1" not in c.give_player_ids
        if c.gap_sweetener:
            assert c.gap_sweetener["player_id"] != "X1"
    assert report.gap_sweetened == 0, \
        "no other asset can close this gap; it must stay unsweetened"
    assert [c for c in _g_for_r(cards)
            if abs(c.give_value - c.receive_value) > GAP_LINE]


def test_arm_c_equalizer_never_uses_an_off_board_asset():
    """SEMANTIC layer: `user_assets` requires the pid be ranked on BOTH
    boards. An asset the opponent has never ranked is not tradeable
    currency for this engine and must not appear via the sweetener."""
    kw = _league()
    # Y is perfectly sized to close the gap, but the opponent has no
    # opinion on it — drop it from the opponent's board only.
    kw["players"]["Y"] = _Player(id="Y", name="Y", position="WR")
    kw["user_roster"] = kw["user_roster"] + ["Y"]
    kw["user_elo"]["Y"] = _elo_for_value(3000.0)
    kw["seed_elo"]["Y"] = _elo_for_value(3000.0)
    kw["untouchable_ids"] = {"X1"}          # force the sweetener to look
    cards, report = generate_league_suggestions(**kw)
    for c in cards:
        assert "Y" not in c.give_player_ids
    assert report.gap_sweetened == 0


def test_arm_c_equalizer_reaches_past_the_budget_slice():
    """BUDGET layer, the §0b decision. `[:gen2_give_pool]` is enumeration
    cost, not a rule — documented as bounding SEARCH BREADTH, never output
    length. Here X1 is pushed out of the top-10 give pool by ten decoys the
    opponent over-values, so the pre-decision wiring (give_candidates=
    give_pool) finds nothing. The equalizer must still be reachable,
    because nothing SEMANTIC excludes it."""
    # `give_pool` ranks `user_assets` by (oval - uval) and keeps the top
    # gen2_give_pool = 10. G sits at +1500 and X1 at 0, so nine decoys at
    # +700 land BETWEEN them: the slice fills up as [G, d0..d8] and X1 is
    # evicted at rank 11. G must stay IN — evicting it too would delete
    # the organic card and the test would pass vacuously.
    #
    # The decoys can only evict, never substitute: at seed 300 they are
    # far too small to close a 1600 gap, and at max(board) 1000 they are
    # under the #141 floor of 2875 anyway.
    decoys = {f"d{i}": (300.0, 300.0, 1000.0, "WR") for i in range(9)}
    cards, report, _ = _cards(extra_user_assets=decoys)
    assert ts._cfg["gen2_give_pool"] == 10.0, "slice size assumption moved"
    assert _g_for_r(cards), "decoys deleted the organic card — test is vacuous"
    sweet = [c for c in _g_for_r(cards) if c.gap_sweetener]
    assert sweet, "equalizer outside the budget slice was not reachable"
    assert sweet[0].gap_sweetener["player_id"] == "X1"
    assert report.gap_sweetened >= 1


# ── 5. arm C's own gate stack is re-earned ─────────────────────────────────

def test_arm_c_sweetened_combo_respects_past_decisions():
    """A sweetened combo is a DIFFERENT trade, so the past-decision ban
    has to be re-tested against ITS key — the enumeration only ever saw
    the unsweetened shape. With the sweetened key banned the card must
    fall back to unsweetened, not vanish and not ship banned."""
    kw = _league()
    kw["past_decision_keys"] = {(frozenset({"G", "X1"}), frozenset({"R"}))}
    cards, report = generate_league_suggestions(**kw)
    for c in cards:
        assert set(c.give_player_ids) != {"G", "X1"}, \
            "shipped a combo the user already rejected"
    assert report.gap_sweetened == 0
    assert _g_for_r(cards), "the organic card must survive unsweetened"
