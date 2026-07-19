"""Deck-eval 2026-07-17 — consensus consolidation raw-delta sanity gate.

The onboarding deck eval flagged a card class where a consensus-lopsided
2-for-1 consolidation scores near-perfect fairness: user gives Jayden
Daniels (6424) + Rome Odunze (2940), receives Jalen Hurts (6616) alone —
raw consensus Δ −2748 for the user, fairness 0.99. Mechanism:

  * package_adj_gamma (1.5) depth discount: Odunze contributes only
    2940 · (0.15 + 0.85·(2940/6616)^1.5) ≈ 1181 — a 60% haircut on a
    genuinely valuable asset (the #141 junk-filler gates don't fire
    because he clears both the relative and absolute filler floors).
  * trade.crown_asset premium: Hurts, the lone asset on the smaller
    side, gains the full +12% (value ≥ crown_elite_value) → 7410.
  * Net adjusted delta +41 → the #108 user-gain gate passes and
    fairness lands at 0.995, OUTRANKING the clean 1-for-1
    Daniels → Hurts (0.935) — the insult card headlines the deck.

Fix: on a user-give-side consolidation (more assets given than
received) the RAW consensus loss must stay within
consolidation_raw_loss_frac (0.15) of the raw give total. Each repro
asserts the card is dark by default and pins the pre-fix leak by
disabling the gate (frac = 0) and watching the same card surface.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    value_to_elo,
)


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


class _Player:
    def __init__(self, pid, position):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = 24
        self.ktc_value = None


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _find(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    for c in cards:
        if (tuple(sorted(c.give_player_ids)),
                tuple(sorted(c.receive_player_ids))) == (g, r):
            return c
    return None


# ───────────────────────────────────────────────────────────────────────────
# Repro fixture: Daniels + Odunze → Hurts on the consensus path
# ───────────────────────────────────────────────────────────────────────────
# Consensus values from the flagged eval card (fairness 0.994, raw Δ −2748):
# DANIELS 6424 (QB), ODUNZE 2940 (WR), HURTS 6616 (QB). Opponent has no
# rankings → consensus-basis cards. trade.crown_asset must be ON (as in
# prod): without the crown premium the #108 adjusted-delta gate already
# blocks the card (rv 6616 < gv 7369).

_VALUES = {"DANIELS": 6424.0, "ODUNZE": 2940.0, "HURTS": 6616.0}
_POSITIONS = {"DANIELS": "QB", "ODUNZE": "WR", "HURTS": "QB"}


def _consensus_run(values, positions, user_roster, opp_roster,
                   fairness_threshold=0.75):
    _set_flags(**{"trade_engine.v2": True, "trade.crown_asset": True})
    seed = {pid: value_to_elo(v) for pid, v in values.items()}
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings={}, has_rankings=False)
    players = {pid: _Player(pid, pos) for pid, pos in positions.items()}
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc.generate_trades(user_id="user", user_elo=dict(seed),
                               user_roster=user_roster, league_id="L1",
                               seed_elo=seed,
                               fairness_threshold=fairness_threshold,
                               max_per_opponent=5)


def test_lopsided_consolidation_is_dark():
    """The flagged 2-for-1 (raw loss 29% of the give side) must be gated;
    disabling the gate resurrects it, pinning the pre-fix leak."""
    cards = _consensus_run(_VALUES, _POSITIONS,
                           ["DANIELS", "ODUNZE"], ["HURTS"])
    assert _find(cards, ["DANIELS", "ODUNZE"], ["HURTS"]) is None, (
        "consensus-lopsided consolidation leaked through the raw-delta gate")

    ts._cfg["consolidation_raw_loss_frac"] = 0.0     # gate off → old behavior
    cards = _consensus_run(_VALUES, _POSITIONS,
                           ["DANIELS", "ODUNZE"], ["HURTS"])
    assert _find(cards, ["DANIELS", "ODUNZE"], ["HURTS"]) is not None, (
        "fixture no longer reproduces the deck-eval leak — repro invalid")


def test_prefix_leak_headlined_over_clean_1for1():
    """Documents WHY this class auto-flagged: with the gate off, the
    insult 2-for-1 scores near-perfect fairness and outranks the clean
    Daniels → Hurts 1-for-1 that would otherwise headline."""
    ts._cfg["consolidation_raw_loss_frac"] = 0.0
    cards = _consensus_run(_VALUES, _POSITIONS,
                           ["DANIELS", "ODUNZE"], ["HURTS"])
    bad = _find(cards, ["DANIELS", "ODUNZE"], ["HURTS"])
    clean = _find(cards, ["DANIELS"], ["HURTS"])
    assert bad is not None and clean is not None
    assert bad.fairness_score > 0.99
    assert bad.composite_score > clean.composite_score


def test_clean_1for1_still_surfaces():
    """Positive control: the fair Daniels → Hurts 1-for-1 (raw Δ +192)
    is untouched by the consolidation gate."""
    cards = _consensus_run(_VALUES, _POSITIONS,
                           ["DANIELS", "ODUNZE"], ["HURTS"])
    assert _find(cards, ["DANIELS"], ["HURTS"]) is not None


def test_sane_consolidation_still_surfaces():
    """Positive control: a genuine consolidation paying a normal premium
    (give 5500 + 1400 = 6900 raw for a 6000 stud → 13% raw loss, inside
    the 15% cap; filler clears the #141 floors; adjusted fairness ≈ 0.78)
    surfaces normally."""
    values = {"HEAD": 5500.0, "FILLER": 1400.0, "STUD": 6000.0}
    positions = {"HEAD": "QB", "FILLER": "WR", "STUD": "QB"}
    cards = _consensus_run(values, positions, ["HEAD", "FILLER"], ["STUD"])
    assert _find(cards, ["HEAD", "FILLER"], ["STUD"]) is not None, (
        "sane consolidation (13% raw loss) was wrongly gated")
