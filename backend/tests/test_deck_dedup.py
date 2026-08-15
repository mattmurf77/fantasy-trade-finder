"""P0-5 near-duplicate deck dedup — metric, greedy pass, and the _order_deck
seam (LLD §4.6, test T-5; PRD R9 + metric M4).

House convention: sabotage-proven. Every test names the change to production
code that must turn it red. The review reads the sabotage list, not the green
run.

What P0-5 must never lose:

  1. **Determinism.** Same candidate set ⇒ same drops, forever. The pass is
     the one layer that REMOVES cards, and the propensity contract (HLD §2.3)
     only tolerates it because it is deterministic-from-frozen-features and
     contributes nothing to the logged propensity.
  2. **Pre-capture.** A dropped card is never logged as an impression. Replay
     reorders only logged cards, so drops are invisible to it by construction.
  3. **Always measured, conditionally dropped** (PRD M4). Drops are
     pre-capture, so a counter is the ONLY thing that can see them — the
     baseline has to accumulate while `deck.dedup` is still off.
  4. **likes_you immunity** and the `_DECK_MIN_CARDS` floor.

Metric under test (LLD §4.6, DECIDED): near-dup iff same `partner_user_id`
AND same centerpiece (`_fatigue_centerpiece`) AND
`jaccard(give ∪ receive) >= dedup_overlap_tau`.
"""

import json
import uuid
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.relevance.config as rel_config
import backend.server as server
from backend.database import deck_job_stats_table, metadata
from backend.relevance.dedup import (
    DEFAULT_TAU,
    DedupCard,
    dedup_cards,
    is_near_dup,
    jaccard,
    near_dup_pairs,
)
from backend.trade_service import TradeCard


LEAGUE = "league_dedup"
ME     = "user_me"
OPP    = "user_opp"
OPP2   = "user_opp2"

# Seed values pick the centerpiece: highest consensus value wins, ties broken
# by player id. STAR/STAR2 dominate; the fillers are interchangeable noise.
SEED_MAP = {
    "STAR":  3000.0,
    "STAR2": 2900.0,
    **{f"f{i}": 1200.0 for i in range(1, 20)},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_card(give, recv, composite, *, likes_you=False, target=OPP):
    return TradeCard(
        trade_id           = f"t_{uuid.uuid4().hex[:8]}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = target,
        target_username    = "opp",
        give_player_ids    = list(give),
        receive_player_ids = list(recv),
        mismatch_score     = 1.0,
        fairness_score     = 0.9,
        composite_score    = composite,
        likes_you          = likes_you,
    )


def _dedup_env(*, on: bool, tau: float = DEFAULT_TAU):
    """Dedup flag + tau pinned; every OTHER ordering layer pinned off.

    Tau is pinned by patching the D10 resolver rather than seeding
    model_config, so these tests never touch a database and never inherit the
    developer's local `dedup_overlap_tau` row.
    """
    stack = ExitStack()
    stack.enter_context(patch.object(server, "_deck_dedup_enabled", lambda: on))
    stack.enter_context(patch.object(
        rel_config, "resolve",
        lambda key, default, **kw: tau if key == "dedup_overlap_tau" else default))
    for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                   "_deck_diversity_enabled", "_deck_fatigue_enabled"):
        stack.enter_context(patch.object(server, helper, lambda: False))
    return stack


def _order(cards, *, stats=None, capture=None, job_id="job-A", **kw):
    return server._order_deck(
        cards, user_id=ME, league_id=LEAGUE, job_id=job_id,
        seed_map=SEED_MAP, capture=capture, dedup_stats=stats, **kw)


def _ids(cards):
    return [c.trade_id for c in cards]


def _view(ident, *, assets, partner=OPP, center="STAR", key=0.0,
          protected=False):
    """A DedupCard with a `key` attached via ref, for pure-module tests."""
    return DedupCard(ident=ident, partner_user_id=partner, centerpiece=center,
                     assets=frozenset(assets), protected=protected, ref=key)


# ---------------------------------------------------------------------------
# The metric itself (pure module — no Flask, no DB)
# ---------------------------------------------------------------------------

def test_jaccard_and_boundary_are_exact():
    """3/4 = 0.75 is representable exactly, so the tau boundary is a real
    boundary and not float luck.

    SABOTAGE: `>= tau` weakened to `> tau` in is_near_dup (the classic
    off-by-one T-5 names) ⇒ the sweetener pair stops collapsing.
    """
    a = frozenset({"STAR", "f1", "f2"})
    b = frozenset({"STAR", "f1", "f2", "f3"})
    assert jaccard(a, b) == 0.75
    assert is_near_dup(_view("a", assets=a), _view("b", assets=b), 0.75)
    assert not is_near_dup(_view("a", assets=a), _view("b", assets=b), 0.76)


def test_jaccard_empty_union_is_not_a_duplicate():
    """Two assetless cards are degenerate, not identical.

    SABOTAGE: define the empty union as 1.0 ⇒ every malformed card in a deck
    collapses into one slot on the strength of a data bug.
    """
    assert jaccard(frozenset(), frozenset()) == 0.0
    assert not is_near_dup(_view("a", assets=[]), _view("b", assets=[]), 1.0)


def test_unkeyable_card_never_collapses():
    """A None partner or None centerpiece means "we could not key this card".

    SABOTAGE: drop the None guard ⇒ None == None makes every unkeyable card a
    duplicate of every other unkeyable card, and they lose their deck slots.
    """
    assets = frozenset({"STAR", "f1"})
    no_partner = DedupCard("a", None, "STAR", assets)
    no_center  = DedupCard("b", OPP, None, assets)
    twin       = DedupCard("c", None, "STAR", assets)
    assert not is_near_dup(no_partner, twin, 0.5)
    assert not is_near_dup(no_center, DedupCard("d", OPP, None, assets), 0.5)


def test_near_dup_pairs_counts_every_pair():
    """The M4 numerator counts PAIRS, on the candidate set, before any drop.

    SABOTAGE: report cluster count (or survivor deficit) instead of pairs ⇒
    a 3-card cluster reports 1 or 2 instead of 3 and the baseline is wrong.
    """
    trio = [_view(f"c{i}", assets={"STAR", "f1", "f2"}) for i in range(3)]
    assert near_dup_pairs(trio, tau=0.75) == [(0, 1), (0, 2), (1, 2)]


# ---------------------------------------------------------------------------
# T-5 — the greedy pass through the real _order_deck seam
# ---------------------------------------------------------------------------

def test_sweetener_variant_collapses_and_survivor_is_higher_keyed():
    """Same partner, same centerpiece, one extra filler ⇒ J = 3/4 = 0.75 ⇒
    collapse. The survivor is the higher-BASE-KEY card, per LLD §4.6.

    SABOTAGE: sort `_dedup_views` ascending (or drop the sort entirely and
    trust incoming order) ⇒ the cheap sweetener-laden card survives instead of
    the better one.
    """
    hi  = _mk_card(["STAR"], ["f1", "f2"], composite=9.0)
    lo  = _mk_card(["STAR"], ["f1", "f2", "f3"], composite=1.0)
    others = [_mk_card(["STAR2"], [f"f{i}"], composite=5.0) for i in range(10, 16)]
    stats: dict = {}
    with _dedup_env(on=True):
        # lo first in the incoming list — the pass must not reward that.
        kept = _order([lo, hi] + others, stats=stats)
    assert hi.trade_id in _ids(kept)
    assert lo.trade_id not in _ids(kept)
    assert stats["dropped"] == 1
    assert stats["pairs"] == 1


def test_tau_one_drops_only_byte_identical_asset_sets():
    """tau=1.0 is the soft off-switch AND the strictest possible metric.

    SABOTAGE: clamp tau, or compare with `>` ⇒ either the sweetener pair
    collapses at 1.0 (soft off is broken, no operator undo without a flag
    flip) or the true twins survive.
    """
    a = _mk_card(["STAR"], ["f1", "f2"], composite=9.0)
    b = _mk_card(["STAR"], ["f1", "f2", "f3"], composite=8.0)   # J = 0.75
    twin = _mk_card(["f2", "f1"], ["STAR"], composite=7.0)      # J = 1.0 vs a
    pool = [a, b, twin] + [_mk_card(["STAR2"], [f"f{i}"], 5.0) for i in range(10, 16)]
    with _dedup_env(on=True, tau=1.0):
        kept = _order(pool)
    assert b.trade_id in _ids(kept)       # 0.75 < 1.0 — untouched
    assert twin.trade_id not in _ids(kept)   # identical asset set — collapsed
    assert a.trade_id in _ids(kept)


def test_different_partner_never_collapses():
    """Byte-identical packages against DIFFERENT managers are two real trades.

    SABOTAGE: drop the partner_user_id clause ⇒ the user only ever sees one of
    the twelve managers who could give them that player.
    """
    a = _mk_card(["STAR"], ["f1", "f2"], composite=9.0, target=OPP)
    b = _mk_card(["STAR"], ["f1", "f2"], composite=8.0, target=OPP2)
    pool = [a, b] + [_mk_card(["STAR2"], [f"f{i}"], 5.0) for i in range(10, 16)]
    stats: dict = {}
    with _dedup_env(on=True):
        kept = _order(pool, stats=stats)
    assert {a.trade_id, b.trade_id} <= set(_ids(kept))
    assert stats["pairs"] == 0


def test_different_centerpiece_never_collapses():
    """Same partner, 0.75 overlap, but the packages are BUILT AROUND different
    players — different trade ideas that happen to share filler.

    SABOTAGE: drop the centerpiece clause ⇒ the control pair below proves the
    overlap alone would have collapsed them, so the user loses one of two
    genuinely distinct stars.
    """
    fillers = ["f1", "f2", "f3", "f4", "f5", "f6"]
    a = _mk_card(["STAR"],  list(fillers), composite=9.0)    # J vs b = 6/8 = 0.75
    b = _mk_card(["STAR2"], list(fillers), composite=8.0)
    pool = [a, b] + [_mk_card(["f19"], [f"f{i}"], 5.0) for i in range(10, 16)]
    with _dedup_env(on=True):
        kept = _order(pool)
    assert {a.trade_id, b.trade_id} <= set(_ids(kept))

    # Control: same overlap, SAME centerpiece ⇒ it does collapse. Without this
    # the test above would also pass if dedup were disabled outright.
    c = _mk_card(["STAR"], fillers + ["f7"], composite=9.0)
    d = _mk_card(["STAR"], fillers + ["f8"], composite=8.0)   # J = 7/9 ≈ 0.78
    pool2 = [c, d] + [_mk_card(["f19"], [f"f{i}"], 5.0) for i in range(10, 16)]
    with _dedup_env(on=True):
        kept2 = _order(pool2)
    assert d.trade_id not in _ids(kept2)


def test_likes_you_card_is_immune():
    """A likes_you card is a live counterparty signal — it outranks tidiness.

    SABOTAGE: drop the `protected` check in dedup_cards ⇒ the lower-keyed
    likes_you card is collapsed away and the mutual match never surfaces.
    """
    hi = _mk_card(["STAR"], ["f1", "f2"], composite=9.0)
    likes = _mk_card(["STAR"], ["f1", "f2", "f3"], composite=1.0, likes_you=True)
    pool = [hi, likes] + [_mk_card(["STAR2"], [f"f{i}"], 5.0) for i in range(10, 16)]
    stats: dict = {}
    with _dedup_env(on=True):
        kept = _order(pool, stats=stats)
    assert likes.trade_id in _ids(kept)
    assert hi.trade_id in _ids(kept)
    assert stats["dropped"] == 0
    assert stats["pairs"] == 1        # still MEASURED as a near-dup pair


def test_min_cards_restore_fires():
    """Dedup must never thin a deck below _DECK_MIN_CARDS — the best-dropped
    cards come back, mirroring `_cap_per_target`.

    SABOTAGE: remove the restore loop ⇒ a duplicate-heavy candidate set serves
    a 2-card deck. Six near-identical cards + one other would otherwise leave 2.
    """
    assert server._DECK_MIN_CARDS == 5
    dupes = [_mk_card(["STAR"], ["f1", "f2"], composite=9.0 - i) for i in range(6)]
    other = _mk_card(["STAR2"], ["f9"], composite=1.0)
    stats: dict = {}
    with _dedup_env(on=True):
        kept = _order(dupes + [other], stats=stats)
    assert len(kept) == server._DECK_MIN_CARDS
    assert stats["restored"] == 3
    assert stats["dropped"] == 2
    # Restores go by base key: the three best dropped cards come back.
    assert _ids(kept) == _ids(dupes[:4]) + [other.trade_id]


def test_deck_at_or_below_floor_is_measured_but_never_thinned():
    """A 5-card deck of pure duplicates keeps all 5 — and never enters the
    drop/restore churn to get there.

    SABOTAGE: drop the `len(cards) <= min_cards` guard ⇒ the pass drops four
    cards and the restore loop hands them straight back, so the SURVIVORS look
    right while `restored` jumps to 4. Asserting restored == 0 is what makes
    this test able to fail at all.
    """
    dupes = [_mk_card(["STAR"], ["f1", "f2"], composite=9.0 - i) for i in range(5)]
    stats: dict = {}
    with _dedup_env(on=True):
        kept = _order(dupes, stats=stats)
    assert _ids(kept) == _ids(dupes)
    assert stats["dropped"] == 0
    assert stats["restored"] == 0
    assert stats["pairs"] == 10        # measured anyway: C(5,2)


# ---------------------------------------------------------------------------
# M4 — always compute, conditionally drop
# ---------------------------------------------------------------------------

def test_flag_off_drops_nothing_but_still_measures():
    """THE M4 baseline requirement. Drops are pre-capture, so `deck_impressions`
    can never reconstruct the near-dup rate — only this counter can, and it has
    to accumulate for ≥7d BEFORE `deck.dedup` flips.

    SABOTAGE: gate the measurement on the flag (the obvious "don't do work we
    don't need" refactor) ⇒ pairs/cards_in_pairs read 0 with the flag off and
    the pre-ship baseline is a flat line of zeroes.
    """
    a = _mk_card(["STAR"], ["f1", "f2"], composite=9.0)
    b = _mk_card(["STAR"], ["f1", "f2", "f3"], composite=8.0)
    pool = [a, b] + [_mk_card(["STAR2"], [f"f{i}"], 5.0) for i in range(10, 16)]
    stats: dict = {}
    with _dedup_env(on=False):
        kept = _order(pool, stats=stats)
    assert _ids(kept) == _ids(pool)          # nothing dropped, order untouched
    assert stats["dropped"] == 0
    assert stats["applied"] is False
    assert stats["pairs"] == 1               # …but it WAS measured
    assert stats["cards_in_pairs"] == 2
    assert stats["cards"] == len(pool)


def test_counter_mapping_names_the_prd_key():
    """PRD M4 mandates the counter name `deduped_cards_per_job`.

    SABOTAGE: rename the key ⇒ the admin relevance report's dedup series goes
    silently empty (a dict lookup, not an error).
    """
    counters = server._dedup_counters(
        {"cards": 12, "pairs": 3, "cards_in_pairs": 5, "dropped": 2,
         "restored": 1, "applied": True})
    assert counters["deduped_cards_per_job"] == 2
    assert counters["near_dup_pairs"] == 3
    assert counters["near_dup_cards"] == 5
    assert counters["deck_cards"] == 12
    assert counters["dedup_applied"] == 1


# ---------------------------------------------------------------------------
# T-5 — determinism, and the pre-capture placement
# ---------------------------------------------------------------------------

def test_identical_drops_across_100_runs():
    """Same candidate set ⇒ identical drops, 100 times. This is the clause the
    propensity contract leans on: dedup is deterministic-from-frozen-features,
    so it owes the logged propensity nothing.

    Every card carries the SAME composite, so the drop set is decided purely
    by the `ident` tie-break — and Thompson is left ON with a different job_id
    each run, which is what makes this a PLACEMENT test too: the per-job Beta
    draws differ every iteration, so a dedup pass that ran on the post-draw
    key instead of the base key would wobble immediately.

    SABOTAGE: tie-break on id(card) instead of the trade hash; iterate a set;
    move the dedup call below the Thompson block ⇒ the drop set wobbles.
    """
    pool = [_mk_card(["STAR"], ["f1", "f2"], composite=5.0) for _ in range(4)]
    pool += [_mk_card(["STAR"], ["f1", "f2", f"f{i}"], composite=5.0)
             for i in range(3, 6)]
    pool += [_mk_card(["STAR2"], [f"f{i}"], composite=5.0) for i in range(10, 16)]
    baseline = None
    for run in range(100):
        stats: dict = {}
        with _dedup_env(on=True):
            with patch.object(server, "_thompson_deck_enabled", lambda: True), \
                 patch.object(server, "load_trade_decision_shape_counts",
                              lambda *a, **k: {}):
                kept = _order(pool, stats=stats, job_id=f"job-{run}")
        signature = tuple(stats["dropped_idents"])
        if baseline is None:
            baseline = signature
        assert signature == baseline, f"run {run} diverged"
        assert len(kept) == len(pool) - stats["dropped"]
    assert baseline is not None and len(baseline) > 0   # drops actually happened


def test_pure_pass_is_stable_when_base_keys_tie():
    """Equal base keys must still order deterministically — the caller sorts on
    (-key, ident), so the pass never depends on dict or list arrival order.

    SABOTAGE: drop `ident` from the sort key ⇒ Python's stable sort silently
    preserves incoming order, which across processes is generator order.
    """
    assets = frozenset({"STAR", "f1", "f2"})
    forward  = [_view("zzz", assets=assets), _view("aaa", assets=assets)]
    backward = list(reversed(forward))
    forward.sort(key=lambda v: (-0.0, v.ident))
    backward.sort(key=lambda v: (-0.0, v.ident))
    kept_f, _ = dedup_cards(forward, tau=0.75)
    kept_b, _ = dedup_cards(backward, tau=0.75)
    assert [c.ident for c in kept_f] == [c.ident for c in kept_b] == ["aaa"]


def test_dropped_cards_never_reach_the_capture_map():
    """Pre-capture placement, asserted directly: whatever `capture` holds is
    what gets written to deck_impressions, so a dropped card appearing there
    would put an unserved card into the replay corpus.

    SABOTAGE: move the dedup call below the Thompson block (or stop pruning
    `key` after a drop) ⇒ the dropped card shows up in capture["final_key"]
    and offline replay starts scoring a card no human ever saw.
    """
    hi = _mk_card(["STAR"], ["f1", "f2"], composite=9.0)
    lo = _mk_card(["STAR"], ["f1", "f2", "f3"], composite=1.0)
    pool = [hi, lo] + [_mk_card(["STAR2"], [f"f{i}"], 5.0) for i in range(10, 16)]
    capture: dict = {}
    with _dedup_env(on=True):
        # Thompson v1 on so `capture` is actually populated.
        with patch.object(server, "_thompson_deck_enabled", lambda: True), \
             patch.object(server, "load_trade_decision_shape_counts",
                          lambda *a, **k: {}):
            kept = _order(pool, capture=capture)
    assert lo.trade_id not in _ids(kept)
    assert id(lo) not in capture["propensity"]
    assert id(lo) not in capture["final_key"]
    assert set(capture["final_key"]) == {id(c) for c in kept}


# ---------------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------------

def test_dedup_failure_serves_the_deck_untouched():
    """Dedup is tidiness; a deck is the product. Any exception must degrade to
    the generated candidate list.

    SABOTAGE: remove the try/except in `_apply_deck_dedup` ⇒ a bad seed_map or
    a resolver blip turns into a failed deck for the user.
    """
    pool = [_mk_card(["STAR"], ["f1", "f2"], composite=9.0 - i) for i in range(6)]
    with _dedup_env(on=True):
        with patch.object(server, "_dedup_views",
                          side_effect=RuntimeError("boom")):
            kept = _order(pool)
    assert _ids(kept) == _ids(pool)


@pytest.mark.parametrize("flag_on", [True, False])
def test_empty_and_single_card_decks_are_safe(flag_on):
    """Guards the two shapes that break naive pair loops.

    SABOTAGE: index into cards[0] unconditionally, or divide by len(cards) for
    a rate ⇒ ZeroDivisionError / IndexError on an empty deck.
    """
    stats: dict = {}
    with _dedup_env(on=flag_on):
        assert _order([], stats=stats) == []
        one = [_mk_card(["STAR"], ["f1"], composite=1.0)]
        assert _order(one, stats=stats) == one
    assert stats["pairs"] == 0
