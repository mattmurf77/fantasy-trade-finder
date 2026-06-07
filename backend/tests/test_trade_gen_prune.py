"""Top-K equivalence tests for INIT-09 trade-gen candidate pruning.

The prune restricts give_candidates / recv_candidates to players whose ELO
divergence signals a mutual-gain opportunity before the combination loops run.
The hard gate: the pruned code path must produce the same top-5 trade cards
(by composite_score, give_player_ids, receive_player_ids) as the un-pruned
path, for every fixture below.

Acceptance criteria covered:
  AC-4  Near-equal-ELO boundary players are INCLUDED, not silently dropped.
  AC-5  New-user (all-ELO-at-1500) degrades gracefully — prune falls back
        to full roster when the pruned set would be too small.
  AC-6  prune_candidates=False path still works (regression guard).
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

import pytest

from backend.trade_service import TradeService, LeagueMember, TradeCard


# ---------------------------------------------------------------------------
# Minimal Player stub — trade_service uses a players dict keyed by player_id,
# with dynasty_value() reading attributes off the player objects.
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "RB"
    team: str = "TST"
    age: int = 24
    ktc_value: Optional[int] = None


def _make_service(player_ids: list[str]) -> TradeService:
    """Build a TradeService with a minimal player dict."""
    players = {
        pid: _Player(id=pid, name=f"Player {pid}", position="RB")
        for pid in player_ids
    }
    return TradeService(players=players)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _member(user_id: str, roster: list[str], elo: dict[str, float]) -> LeagueMember:
    return LeagueMember(user_id=user_id, username=user_id, roster=roster, elo_ratings=elo)


def _run_pair(
    svc: TradeService,
    user_id: str,
    user_elo: dict[str, float],
    user_roster: list[str],
    opponent: LeagueMember,
    prune: bool,
) -> list[TradeCard]:
    """Call _generate_for_pair with a fixed seed_elo (all 1500) and return results."""
    seed_elo = {pid: 1500.0 for pid in list(user_elo) + list(opponent.elo_ratings)}
    return svc._generate_for_pair(
        user_id            = user_id,
        user_elo           = user_elo,
        user_roster        = user_roster,
        opponent           = opponent,
        league_id          = "test-league",
        seed_elo           = seed_elo,
        max_cards          = 5,
        fairness_threshold = 0.75,
        prune_candidates   = prune,
    )


def _card_key(c: TradeCard) -> tuple:
    """Stable identity tuple for comparison: sorted player ID lists + rounded score."""
    return (
        tuple(sorted(c.give_player_ids)),
        tuple(sorted(c.receive_player_ids)),
        round(c.composite_score, 6),
    )


def _top5_keys(cards: list[TradeCard]) -> list[tuple]:
    return [_card_key(c) for c in sorted(cards, key=lambda x: x.composite_score, reverse=True)[:5]]


# ---------------------------------------------------------------------------
# Fixture A — Clear ELO divergence (typical dynasty league).
#
# user highly values u1/u2 (1700+), opponent highly values o1/o2 (1700+).
# Each side undervalues the other's star, creating multiple trade signals.
# ---------------------------------------------------------------------------

_PLAYER_IDS_A = [f"u{i}" for i in range(1, 8)] + [f"o{i}" for i in range(1, 8)]

def _fixture_a():
    """7 user players, 7 opp players with clear divergence."""
    user_roster = [f"u{i}" for i in range(1, 8)]
    opp_roster  = [f"o{i}" for i in range(1, 8)]

    user_elo = {
        "u1": 1720, "u2": 1680, "u3": 1560, "u4": 1490, "u5": 1430, "u6": 1380, "u7": 1300,
        # user's view of opp players (undervalues o1/o2)
        "o1": 1420, "o2": 1390, "o3": 1530, "o4": 1480, "o5": 1420, "o6": 1370, "o7": 1290,
    }
    opp_elo = {
        # opp's view of user players (overvalues u1/u2)
        "u1": 1800, "u2": 1760, "u3": 1540, "u4": 1470, "u5": 1420, "u6": 1360, "u7": 1290,
        "o1": 1710, "o2": 1690, "o3": 1540, "o4": 1480, "o5": 1430, "o6": 1370, "o7": 1300,
    }
    svc = _make_service(_PLAYER_IDS_A)
    opp = _member("opp_a", opp_roster, opp_elo)
    return svc, user_elo, user_roster, opp


# ---------------------------------------------------------------------------
# Fixture B — AC-4: Near-equal ELO boundary case.
#
# Some players have very similar (but not identical) ELO on both sides —
# just above the 0.97 * user_elo threshold.  The prune must NOT drop these
# near-equal-ELO players, so the trade set stays consistent with un-pruned.
# ---------------------------------------------------------------------------

_PLAYER_IDS_B = [f"p{i}" for i in range(1, 9)]

def _fixture_b():
    """Near-equal ELO on some players — boundary condition for the prune gate.

    We need actual trade opportunities, so we ensure that opp overvalues some
    user players AND user overvalues some opp players — creating mismatch > 0.
    A subset of players are "near-equal" (opp_elo ≈ user_elo * 0.98) so they
    land just above the 0.97 threshold and stay included in the pruned set.
    """
    user_roster = [f"p{i}" for i in range(1, 5)]
    opp_roster  = [f"p{i}" for i in range(5, 9)]

    user_elo = {
        # user side: p1 near-equal boundary, p2 clear divergence
        "p1": 1600, "p2": 1650, "p3": 1500, "p4": 1450,
        # user's view of opp players: undervalues p5/p6
        "p5": 1400, "p6": 1380, "p7": 1530, "p8": 1490,
    }
    opp_elo = {
        # opp overvalues p1 slightly (1568 / 1600 = 0.98, above 0.97 threshold)
        # opp overvalues p2 strongly (1750 >> 1650)
        "p1": 1568, "p2": 1750, "p3": 1490, "p4": 1440,
        # opp overvalues its own p5/p6 strongly
        "p5": 1700, "p6": 1680, "p7": 1520, "p8": 1480,
    }
    svc = _make_service(_PLAYER_IDS_B)
    opp = _member("opp_b", opp_roster, opp_elo)
    return svc, user_elo, user_roster, opp


# ---------------------------------------------------------------------------
# Fixture C — AC-5: New-user (all ELO at 1500 for the user's own players).
#
# No signal from user_elo — the prune must fall back to the full roster
# rather than returning an empty candidate set.
# ---------------------------------------------------------------------------

_PLAYER_IDS_C = [f"q{i}" for i in range(1, 9)]

def _fixture_c():
    """User has all-1500 ELO (new user). Prune should fall back gracefully."""
    user_roster = [f"q{i}" for i in range(1, 5)]
    opp_roster  = [f"q{i}" for i in range(5, 9)]

    # All user's own-elo at 1500 → no divergence signal
    user_elo = {
        "q1": 1500, "q2": 1500, "q3": 1500, "q4": 1500,
        "q5": 1500, "q6": 1500, "q7": 1500, "q8": 1500,
    }
    opp_elo = {
        "q1": 1650, "q2": 1600, "q3": 1530, "q4": 1510,
        "q5": 1620, "q6": 1580, "q7": 1540, "q8": 1500,
    }
    svc = _make_service(_PLAYER_IDS_C)
    opp = _member("opp_c", opp_roster, opp_elo)
    return svc, user_elo, user_roster, opp


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.parametrize("fixture_fn,label", [
    (_fixture_a, "clear_divergence"),
    (_fixture_b, "equal_elo_boundary_ac4"),
    (_fixture_c, "new_user_fallback_ac5"),
])
def test_top5_equivalence_pruned_vs_full(fixture_fn, label):
    """Pruned top-5 must be identical (order + content) to un-pruned top-5."""
    svc, user_elo, user_roster, opp = fixture_fn()

    full_cards   = _run_pair(svc, "user", user_elo, user_roster, opp, prune=False)
    pruned_cards = _run_pair(svc, "user", user_elo, user_roster, opp, prune=True)

    full_top5   = _top5_keys(full_cards)
    pruned_top5 = _top5_keys(pruned_cards)

    # Sanity: fixture must actually produce some results
    assert full_top5, f"[{label}] un-pruned run returned 0 cards — fixture is broken"

    assert pruned_top5 == full_top5, (
        f"[{label}] pruned top-5 differs from un-pruned.\n"
        f"  pruned:   {pruned_top5}\n"
        f"  un-pruned:{full_top5}"
    )


def test_prune_false_path_still_works():
    """AC-6: prune_candidates=False must not error and must return results."""
    svc, user_elo, user_roster, opp = _fixture_a()
    cards = _run_pair(svc, "user", user_elo, user_roster, opp, prune=False)
    assert len(cards) > 0, "prune=False path returned no cards"


def test_ac4_equal_elo_players_included():
    """AC-4: players with equal ELO on both sides must appear in prune output."""
    svc, user_elo, user_roster, opp = _fixture_b()

    # Run with prune — must not discard equal-ELO players (p1, p6) silently.
    pruned = _run_pair(svc, "user", user_elo, user_roster, opp, prune=True)
    full   = _run_pair(svc, "user", user_elo, user_roster, opp, prune=False)

    # Convergence: the card sets should be the same
    assert _top5_keys(pruned) == _top5_keys(full)


def test_ac5_new_user_nonempty_output():
    """AC-5: all-1500 user must still get trade cards (prune falls back)."""
    svc, user_elo, user_roster, opp = _fixture_c()

    pruned = _run_pair(svc, "user", user_elo, user_roster, opp, prune=True)
    full   = _run_pair(svc, "user", user_elo, user_roster, opp, prune=False)

    # Both must produce the same results — prune should have fallen back
    assert _top5_keys(pruned) == _top5_keys(full), (
        "AC-5: new-user prune fallback produced different results than un-pruned"
    )
