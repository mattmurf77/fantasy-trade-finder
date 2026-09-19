"""Board-override pins — F1 (comparison exclusion) + F2 (unpin on newer vote).

Phase 0 of docs/plans/three-model-bakeoff/PLAN.md, fixing the defect diagnosed
in docs/reviews/2026-08-18-valuation-age-audit.md §3.4 / §5.1:

  * `_compute_elo` seeds an override-pinned player from the override and skips
    every rating update, so their Elo cannot move from voting.
  * `trade_service._shrink_user_elo` blends personal Elo toward the consensus
    seed with w = n/(n + shrink_pseudocount), where n is the COMPARISON COUNT
    — direction-blind.

Composed, they invert intent: the audited board had Davante Adams pinned at
Elo 1565.3, ABOVE the 1526.0 consensus. Seventeen down-votes moved his Elo by
exactly zero but raised n, which raised w, which dragged his effective trade
value UP 12.5%. Voting a player down made the engine want him more.

The fixture below reproduces those exact numbers (consensus 1138.83, pinned
board value 1385.95) so the assertions are about real arithmetic, not a toy.

Everything here is offline: an in-memory RankingService for the ranking math
and in-memory SQLite for the persistence round-trip.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
from backend.database import (
    PIN_STAMPS_KEY, PRE_ROOKIE_SCOPE_KEY, metadata, users_table,
    load_tier_override_stamps, load_tier_overrides, save_tier_overrides,
    take_tier_override_snapshot, restore_tier_overrides_from_snapshot,
)
from backend import ranking_service as rs
from backend import trade_service as ts
from backend.ranking_service import Player, RankingService, SwipeDecision

GOLDEN = Path(__file__).parent / "fixtures" / "override_pin_golden.json"

# The audited board's real numbers.
CONSENSUS_ELO = 1526.0          # Adams's consensus seed, 1qb_ppr, 2026-08-18
PIN_ELO = 1565.2777777777778    # his tier placement: 2nd of 19 in "worth a 2nd"
CONSENSUS_VALUE = 1138.8283833246219

KILL = {"pin_exclude_comparisons": 0.0,
        "pin_unpin_on_newer_swipe": 0.0,
        "pin_legacy_at_epoch": 0.0,
        "pin_tier_bounded": 0.0}
# Phase 0's shipped configuration. TIER-BOUNDED VOTING (2026-08-18) superseded
# it hours later — `pin_tier_bounded` now defaults ON and F2 defaults OFF — but
# Phase 0 remains reachable by knob and is the documented revert path, so this
# module states that configuration explicitly instead of reading today's
# defaults. Today's defaults are covered by test_pin_tier_bounded.py.
DEFAULTS = {"pin_exclude_comparisons": 1.0,
            "pin_unpin_on_newer_swipe": 1.0,
            "pin_legacy_at_epoch": 0.0,
            "pin_tier_bounded": 0.0}


@pytest.fixture(autouse=True)
def restore_cfg():
    """Every test mutates rs._cfg; put it back so ordering cannot matter."""
    before = dict(rs._cfg)
    yield
    rs._cfg.clear()
    rs._cfg.update(before)


def cfg(**overrides):
    """Start from the Phase 0 configuration, then apply this test's overrides."""
    rs._cfg.update(DEFAULTS)
    rs._cfg.update(overrides)


# ═══════════════════════════════════════════════════════════════════════════
# Fixture — the Adams scenario
# ═══════════════════════════════════════════════════════════════════════════

def build_service(stamped: str | None = None):
    """The audited board in miniature.

    p_pinned  — pinned ABOVE consensus, then voted DOWN 17× (the Adams case)
    p_pinned2 — pinned; only ever compared against p_pinned, so every one of
                those comparisons is INERT (both sides pinned → no-op on both)
    p_free    — never pinned, compared normally (control)
    p_quiet   — never pinned, never compared (pure-consensus control)

    `stamped` — ISO write time for the two pins. None leaves them LEGACY
    (the shape of all 2,739 pins live in prod today).

    Kept byte-identical to the capture script that produced the golden.
    """
    players = [
        Player(id="p_pinned",  name="Pinned Vet",   position="WR", team="LAR", age=33),
        Player(id="p_pinned2", name="Pinned Two",   position="WR", team="KC",  age=27),
        Player(id="p_free",    name="Free Agent",   position="WR", team="NYG", age=24),
        Player(id="p_quiet",   name="Quiet Player", position="WR", team="SF",  age=25),
    ]
    seed = {"p_pinned": CONSENSUS_ELO, "p_pinned2": 1480.0,
            "p_free": 1500.0, "p_quiet": 1450.0}
    svc = RankingService(players, seed_ratings=seed)
    svc._elo_overrides = {"p_pinned": PIN_ELO, "p_pinned2": 1341.3333333333333}
    if stamped:
        svc._elo_override_at = {"p_pinned": stamped, "p_pinned2": stamped}

    pairs = [("p_free", "p_pinned", f"2026-08-17T10:{i:02d}:00+00:00")
             for i in range(17)]
    pairs.append(("p_pinned", "p_free", "2026-08-17T10:30:00+00:00"))
    pairs += [("p_pinned", "p_pinned2", f"2026-08-17T11:{i:02d}:00+00:00")
              for i in range(6)]
    pairs.append(("p_free", "p_quiet", "2026-08-17T12:00:00+00:00"))

    svc._swipes = [SwipeDecision(winner_id=w, loser_id=l, timestamp=t)
                   for w, l, t in pairs]
    svc._version = len(svc._swipes)
    return svc, seed


def snapshot(svc, seed):
    """Every number the two fixes can move — matches the golden's shape."""
    rankset = svc.get_rankings(position=None)
    counts = svc.comparison_counts()
    raw_elo = svc._compute_elo(list(svc._players.values()))
    shrunk = ts._shrink_user_elo(raw_elo, seed, counts)
    return {
        "elo": {r.player.id: r.elo for r in rankset.rankings},
        "counts": dict(sorted(counts.items())),
        "shrunk": {k: round(v, 6) for k, v in sorted(shrunk.items())},
        "unc": {pid: round(ts._value_uncertainty(pid, counts), 6)
                for pid in sorted(raw_elo)},
        "value": {k: round(ts.elo_to_value(v), 6) for k, v in sorted(shrunk.items())},
    }


def effective_value(svc, seed, pid="p_pinned"):
    """What the trade engine actually prices this player at."""
    counts = svc.comparison_counts()
    shrunk = ts._shrink_user_elo(svc._compute_elo(list(svc._players.values())),
                                 seed, counts)
    return ts.elo_to_value(shrunk[pid])


# ═══════════════════════════════════════════════════════════════════════════
# Kill-value byte identity
# ═══════════════════════════════════════════════════════════════════════════

def test_kill_values_are_byte_identical_to_the_captured_golden():
    """The one non-negotiable: both knobs at 0.0 reproduce pre-fix output.

    `fixtures/override_pin_golden.json` was CAPTURED by running this exact
    fixture against origin/main before a line of it changed — so this is a
    comparison against real recorded output, not against the new code's own
    opinion of what the old code did.
    """
    golden = json.loads(GOLDEN.read_text())
    cfg(**KILL)
    svc, seed = build_service()
    assert snapshot(svc, seed) == golden


def test_kill_values_hold_for_stamped_pins_too():
    """Stamping a pin must not change anything while the knobs are dead —
    otherwise the kill switch would not be a true revert for boards saved
    after this ships."""
    golden = json.loads(GOLDEN.read_text())
    cfg(**KILL)
    svc, seed = build_service(stamped="2026-08-01T00:00:00+00:00")
    assert snapshot(svc, seed) == golden


def test_the_golden_itself_records_the_defect():
    """Guard the premise. If the golden ever stops showing the inversion, the
    fixture has drifted and every assertion below is measuring nothing."""
    golden = json.loads(GOLDEN.read_text())
    assert golden["elo"]["p_pinned"] == round(PIN_ELO, 1)          # never moved
    assert golden["counts"]["p_pinned"] == 2                        # but n rose
    assert golden["value"]["p_pinned"] > CONSENSUS_VALUE            # → worth MORE


# ═══════════════════════════════════════════════════════════════════════════
# F1 — the Adams inversion
# ═══════════════════════════════════════════════════════════════════════════

def test_adams_downvotes_no_longer_raise_his_trade_value():
    """THE regression test. 17 down-votes on a pinned player must not make the
    engine value him more than it did before the user voted at all."""
    cfg(**KILL)
    before, seed = build_service()
    before._swipes = []                      # the board as it was pre-session
    before._version = 0
    baseline = effective_value(before, seed)

    cfg()                                    # shipped defaults
    after, seed = build_service()            # + the 17 down-votes
    assert effective_value(after, seed) <= baseline + 1e-9


def test_pinned_player_prices_at_exactly_consensus():
    """A still-pinned player carries no vote signal, so shrinkage must put him
    on the consensus seed — n=0, w=0, no divergence invented."""
    cfg()
    svc, seed = build_service()
    assert svc.comparison_counts()["p_pinned"] == 0
    assert effective_value(svc, seed) == pytest.approx(CONSENSUS_VALUE)


def test_kill_switch_restores_the_inversion():
    """Proves the knob is load-bearing, not decorative."""
    cfg(**KILL)
    svc, seed = build_service()
    assert effective_value(svc, seed) > CONSENSUS_VALUE


def test_more_downvotes_never_raise_value_monotonicity():
    """The audit's core claim was monotone: every extra vote pushed value
    further toward the pin. Sweep the vote count and assert it cannot rise."""
    cfg()
    values = []
    for n in (0, 1, 5, 17):
        svc, seed = build_service()
        svc._swipes = [SwipeDecision("p_free", "p_pinned",
                                     f"2026-08-17T10:{i:02d}:00+00:00")
                       for i in range(n)]
        svc._version = n
        values.append(effective_value(svc, seed))
    assert values == sorted(values, reverse=True) or len(set(values)) == 1


def test_inert_comparison_both_sides_pinned_counts_for_neither():
    """67.8% of all recorded comparisons have BOTH players pinned, so the Elo
    update is a no-op on both sides. Those must not accrue confidence either —
    that is the whole mechanism by which inert swipes moved value."""
    cfg()
    svc, seed = build_service()
    svc._swipes = [SwipeDecision("p_pinned", "p_pinned2",
                                 f"2026-08-17T11:{i:02d}:00+00:00")
                   for i in range(6)]
    svc._version = 6
    counts = svc.comparison_counts()
    assert counts["p_pinned"] == 0
    assert counts["p_pinned2"] == 0
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] == pytest.approx(PIN_ELO)
    assert elo["p_pinned2"] == pytest.approx(1341.3333333333333)


def test_unpinned_players_counts_are_untouched():
    """F1 is scoped to pins. A normal player's confidence must not move, or
    the fix would silently reprice the whole board."""
    cfg()
    svc, _ = build_service()
    cfg(**KILL)
    before = build_service()[0].comparison_counts()
    cfg()
    after = svc.comparison_counts()
    assert after["p_free"] == before["p_free"]
    assert after["p_quiet"] == before["p_quiet"]


def test_uncertainty_shares_the_excluded_map():
    """Documented consequence (comparison_counts docstring): a pinned player is
    valued at consensus, and this codebase gives any consensus-valued player
    maximum uncertainty. Pinning that down so a future change to `confidence`
    plumbing cannot silently split the two consumers."""
    cfg()
    svc, _ = build_service()
    counts = svc.comparison_counts()
    assert ts._value_uncertainty("p_pinned", counts) == pytest.approx(
        ts._c("range_base"))                            # == the n=0 half-width


# ═══════════════════════════════════════════════════════════════════════════
# F2 — a newer vote unpins
# ═══════════════════════════════════════════════════════════════════════════

def test_newer_swipe_releases_the_pin():
    """Pin written 2026-08-01, voted on 2026-08-17 ⇒ released. The pin stays
    the STARTING rating and the newer down-votes apply on top, so the Elo must
    fall below both the pin and consensus."""
    cfg()
    svc, seed = build_service(stamped="2026-08-01T00:00:00+00:00")
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] < PIN_ELO
    assert elo["p_pinned"] < CONSENSUS_ELO
    assert effective_value(svc, seed) < CONSENSUS_VALUE


def test_older_swipe_does_not_release_the_pin():
    """A pin written AFTER the votes is the user's newest word — it wins."""
    cfg()
    svc, _ = build_service(stamped="2026-08-18T00:00:00+00:00")
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] == pytest.approx(PIN_ELO)
    assert svc.comparison_counts()["p_pinned"] == 0


def test_released_player_only_replays_post_pin_swipes():
    """The pin summarises everything said before it. Swipes that predate it
    were already superseded and must not be resurrected."""
    cfg()
    # Pinned at 10:20 — AFTER all 17 down-votes (10:00–10:16) and before the
    # single up-vote at 10:30. Only the up-vote and the 6 wins over p_pinned2
    # survive the cut, so he can only RISE.
    early, _ = build_service(stamped="2026-08-17T10:20:00+00:00")
    # Pinned 2026-08-01 — every one of the 17 down-votes is newer, so they all
    # apply and he falls hard.
    late, _ = build_service(stamped="2026-08-01T00:00:00+00:00")
    e_early = early._compute_elo(list(early._players.values()))["p_pinned"]
    e_late = late._compute_elo(list(late._players.values()))["p_pinned"]
    assert e_late < PIN_ELO < e_early, (
        "the pin's own timestamp must decide which swipes replay")


def test_released_player_regains_confidence_from_post_release_votes_only():
    """Once released the player evolves again, so his votes count again — but
    only the ones that actually moved him."""
    cfg()
    # Pin both at 10:20. p_pinned's only post-pin opponents are p_free (10:30)
    # and p_pinned2 (11:xx) → 2. p_pinned2's sole opponent is p_pinned, and
    # those 6 comparisons are all post-pin → 1 unique opponent.
    svc, _ = build_service(stamped="2026-08-17T10:20:00+00:00")
    counts = svc.comparison_counts()
    assert counts["p_pinned"] == 2
    assert counts["p_pinned2"] == 1
    # The 17 pre-pin down-votes are excluded — under the kill switch p_pinned
    # would score 2 for a different reason (p_free + p_pinned2 across ALL of
    # history), so assert the frozen case too, where the split is unambiguous.
    frozen, _ = build_service(stamped="2026-08-18T00:00:00+00:00")
    assert frozen.comparison_counts()["p_pinned"] == 0


def test_unpin_kill_switch_freezes_pins_again():
    cfg(pin_unpin_on_newer_swipe=0.0)
    svc, _ = build_service(stamped="2026-08-01T00:00:00+00:00")
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] == pytest.approx(PIN_ELO)


def test_trade_swipes_cannot_release_a_pin():
    """Design decision: only a deliberate RANKING comparison unpins. A trade
    like/pass is an indirect, low-K signal about a whole package."""
    cfg()
    svc, _ = build_service(stamped="2026-08-01T00:00:00+00:00")
    svc._swipes = []                                   # no ranking swipes
    svc._trade_swipes = [(SwipeDecision("p_free", "p_pinned",
                                        "2026-08-17T10:00:00+00:00"), 8.0)]
    svc._version = 1
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] == pytest.approx(PIN_ELO)


def test_released_player_does_absorb_newer_trade_swipes():
    """...but once a ranking swipe HAS released him, he is simply un-pinned,
    and every newer signal applies."""
    cfg()
    svc, _ = build_service(stamped="2026-08-01T00:00:00+00:00")
    with_trade = svc._compute_elo(list(svc._players.values()))["p_pinned"]
    svc2, _ = build_service(stamped="2026-08-01T00:00:00+00:00")
    svc2._trade_swipes = [(SwipeDecision("p_free", "p_pinned",
                                         "2026-08-17T13:00:00+00:00"), 8.0)]
    svc2._version += 1
    assert svc2._compute_elo(list(svc2._players.values()))["p_pinned"] < with_trade


# ═══════════════════════════════════════════════════════════════════════════
# F2 — legacy (timestamp-less) overrides
# ═══════════════════════════════════════════════════════════════════════════

def test_legacy_override_is_permanent_by_default():
    """2,739 pins live in prod carry no write time. The default must not touch
    a single one of them: F2 is inert until the user re-tiers."""
    cfg()
    svc, _ = build_service(stamped=None)
    assert svc._elo_override_at == {}
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] == pytest.approx(PIN_ELO)


def test_legacy_override_releases_when_the_epoch_policy_is_on():
    """The operator's opt-in: treat an unstamped pin as written at the epoch,
    so ANY recorded swipe — including historical ones — releases it."""
    cfg(pin_legacy_at_epoch=1.0)
    svc, seed = build_service(stamped=None)
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["p_pinned"] < CONSENSUS_ELO
    assert effective_value(svc, seed) < CONSENSUS_VALUE


def test_legacy_epoch_policy_needs_the_unpin_knob():
    """A sub-policy of F2 — it must not act on its own when F2 is killed."""
    cfg(pin_unpin_on_newer_swipe=0.0, pin_legacy_at_epoch=1.0)
    svc, _ = build_service(stamped=None)
    assert svc._compute_elo(list(svc._players.values()))["p_pinned"] == pytest.approx(PIN_ELO)


def test_unparseable_stamp_is_treated_as_legacy():
    """Garbage in the blob must fail closed (stay pinned), never open."""
    cfg()
    svc, _ = build_service()
    svc._elo_override_at = {"p_pinned": "not-a-date"}
    assert svc._compute_elo(list(svc._players.values()))["p_pinned"] == pytest.approx(PIN_ELO)


def test_mixed_stamp_formats_compare_correctly():
    """`SwipeDecision.timestamp` and `swipe_decisions.created_at` are both
    written by `datetime.now(timezone.utc).isoformat()`, but a naive or
    Z-suffixed stamp must still compare rather than silently fail closed."""
    cfg()
    for stamp in ("2026-08-01T00:00:00Z", "2026-08-01T00:00:00"):
        svc, _ = build_service(stamped=stamp)
        assert svc._compute_elo(list(svc._players.values()))["p_pinned"] < PIN_ELO


# ═══════════════════════════════════════════════════════════════════════════
# Stamping — every override write must record when
# ═══════════════════════════════════════════════════════════════════════════

def _fresh_service():
    players = [Player(id=f"p{i}", name=f"P{i}", position="WR", team="SF", age=25)
               for i in range(5)]
    return RankingService(players,
                          seed_ratings={f"p{i}": 1500.0 - 10 * i for i in range(5)})


def test_apply_tiers_stamps_every_pin_it_writes():
    svc = _fresh_service()
    svc.apply_tiers("WR", {"firsts_2": ["p0", "p1"], "second": ["p2"]})
    assert set(svc._elo_override_at) == set(svc._elo_overrides)
    assert all(rs._parse_ts(v) for v in svc._elo_override_at.values())


def test_apply_tiers_shares_one_stamp_per_save():
    """A single save is one instant — otherwise pins written microseconds
    apart would release each other inconsistently."""
    svc = _fresh_service()
    svc.apply_tiers("WR", {"firsts_2": ["p0", "p1", "p2"]})
    assert len(set(svc._elo_override_at.values())) == 1


def test_clearing_a_pid_drops_its_stamp():
    """A stale stamp on a cleared pid would re-stamp the next pin the user
    creates for that player, silently backdating it."""
    svc = _fresh_service()
    svc.apply_tiers("WR", {"firsts_2": ["p0", "p1"]})
    svc.apply_tiers("WR", {"firsts_2": ["p1"]}, cleared_pids=["p0"])
    assert "p0" not in svc._elo_overrides
    assert "p0" not in svc._elo_override_at


@pytest.mark.parametrize("mutate", [
    lambda s: s.apply_reorder("WR", ["p3", "p1", "p0", "p2", "p4"]),
    lambda s: s.apply_value_map("WR", ["p3", "p1", "p0", "p2", "p4"]),
    lambda s: s.apply_anchor("p2", 1600.0),
    lambda s: s.apply_tiers("WR", {"firsts_2": ["p0"]}),
    lambda s: s.apply_tiers_subset("WR", {"firsts_2": ["p0"]}, scope_pids={"p0"}),
])
def test_every_override_mutator_stamps(mutate):
    """Structural guard. An unstamped write is a pin nothing can ever release,
    which is exactly the bug F2 exists to remove."""
    svc = _fresh_service()
    mutate(svc)
    assert svc._elo_overrides, "mutator wrote no override — fixture drifted"
    assert set(svc._elo_override_at) == set(svc._elo_overrides)


def test_replay_from_db_carries_the_persisted_timestamp():
    """SwipeDecision defaults `timestamp` to NOW. Replaying without the stored
    created_at would make every historical swipe look newer than every pin, so
    a server restart would silently unpin whole boards."""
    svc = _fresh_service()
    svc.replay_from_db([{
        "winner_player_id": "p0", "loser_player_id": "p1",
        "decision_type": "rank", "k_factor": 32.0,
        "created_at": "2026-01-02T03:04:05+00:00",
    }])
    assert svc._swipes[0].timestamp == "2026-01-02T03:04:05+00:00"


def test_replay_survives_a_null_created_at():
    """Legacy rows can carry a NULL created_at; those must not crash, and must
    fail closed (no stamp ⇒ never releases a pin)."""
    cfg()
    svc = _fresh_service()
    svc.replay_from_db([{
        "winner_player_id": "p0", "loser_player_id": "p1",
        "decision_type": "rank", "k_factor": 32.0, "created_at": None,
    }])
    svc._pin("p1", 1400.0, at="2026-01-01T00:00:00+00:00")
    assert svc._compute_elo(list(svc._players.values()))["p1"] == pytest.approx(1400.0)


# ═══════════════════════════════════════════════════════════════════════════
# Persistence — stamps round-trip as a sibling key
# ═══════════════════════════════════════════════════════════════════════════

UID = "u_pin"


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-18T00:00:00+00:00"))
    return engine


def test_stamps_round_trip(db):
    save_tier_overrides(UID, {"a": 1500.0, "b": 1400.0},
                        scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00",
                                "b": "2026-08-18T02:00:00+00:00"})
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1500.0, "b": 1400.0}
    assert load_tier_override_stamps(UID, "1qb_ppr") == {
        "a": "2026-08-18T01:00:00+00:00", "b": "2026-08-18T02:00:00+00:00"}


def test_override_value_shape_is_unchanged(db):
    """The per-format map stays `{pid: elo}`. Anything else would break
    `load_tier_overrides`' float cast and every existing reader of the column."""
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00"})
    with db.begin() as conn:
        raw = conn.execute(users_table.select()).fetchone().tier_overrides
    assert json.loads(raw)["1qb_ppr"] == {"a": 1500.0}


def test_legacy_blob_without_stamps_loads_empty(db):
    """Exactly what prod holds today: overrides, no stamps, no crash."""
    with db.begin() as conn:
        conn.execute(users_table.update().values(
            tier_overrides=json.dumps({"1qb_ppr": {"a": 1500.0}})))
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1500.0}
    assert load_tier_override_stamps(UID, "1qb_ppr") == {}


def test_stamps_are_pruned_to_live_overrides(db):
    save_tier_overrides(UID, {"a": 1500.0, "b": 1400.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00",
                                "b": "2026-08-18T02:00:00+00:00"})
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00"})
    assert load_tier_override_stamps(UID, "1qb_ppr") == {
        "a": "2026-08-18T01:00:00+00:00"}


def test_omitting_stamps_preserves_the_stored_ones(db):
    """A caller that has not been updated must not silently strip stamps."""
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00"})
    save_tier_overrides(UID, {"a": 1600.0}, scoring_format="1qb_ppr")
    assert load_tier_override_stamps(UID, "1qb_ppr") == {
        "a": "2026-08-18T01:00:00+00:00"}


def test_formats_keep_separate_stamp_maps(db):
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00"})
    save_tier_overrides(UID, {"b": 1400.0}, scoring_format="sf_tep",
                        stamps={"b": "2026-08-18T02:00:00+00:00"})
    assert load_tier_override_stamps(UID, "1qb_ppr") == {"a": "2026-08-18T01:00:00+00:00"}
    assert load_tier_override_stamps(UID, "sf_tep") == {"b": "2026-08-18T02:00:00+00:00"}
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1500.0}


def test_stamps_coexist_with_the_rookie_scope_snapshot(db):
    """Both live as sibling keys in the same column; `_parse_extra_keys` is the
    only thing keeping either alive across a save (see T-M2-01)."""
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00"})
    assert take_tier_override_snapshot(UID) is True
    save_tier_overrides(UID, {"a": 1500.0, "b": 1400.0}, scoring_format="sf_tep",
                        stamps={"a": "2026-08-18T03:00:00+00:00"})
    with db.begin() as conn:
        blob = json.loads(conn.execute(users_table.select()).fetchone().tier_overrides)
    assert PRE_ROOKIE_SCOPE_KEY in blob
    assert blob[PIN_STAMPS_KEY]["1qb_ppr"] == {"a": "2026-08-18T01:00:00+00:00"}


def test_snapshot_restore_clears_stamps(db):
    """The snapshot predates F2 and holds no write times; the restored pins
    must come back LEGACY rather than inherit stamps for pins just discarded."""
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr")
    take_tier_override_snapshot(UID)
    save_tier_overrides(UID, {"a": 1500.0, "b": 1400.0}, scoring_format="1qb_ppr",
                        stamps={"a": "2026-08-18T01:00:00+00:00",
                                "b": "2026-08-18T02:00:00+00:00"})
    restore_tier_overrides_from_snapshot(UID, scoring_format="1qb_ppr")
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1500.0}
    assert load_tier_override_stamps(UID, "1qb_ppr") == {}


def test_full_cycle_pin_then_vote_then_unpin(db):
    """End to end on the real seam: tier-save writes a stamped pin, it persists,
    a later swipe releases it on the rebuilt service."""
    cfg()
    svc = _fresh_service()
    svc.apply_tiers("WR", {"firsts_2": ["p0", "p1"]})
    save_tier_overrides(UID, svc._elo_overrides, scoring_format="1qb_ppr",
                        stamps=svc._elo_override_at)

    rebuilt = _fresh_service()
    rebuilt._elo_overrides = load_tier_overrides(UID, "1qb_ppr")
    rebuilt._elo_override_at = load_tier_override_stamps(UID, "1qb_ppr")
    pinned = rebuilt._elo_overrides["p0"]

    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    rebuilt.replay_from_db([{
        "winner_player_id": "p2", "loser_player_id": "p0",
        "decision_type": "rank", "k_factor": 32.0, "created_at": later,
    }])
    assert rebuilt._compute_elo(list(rebuilt._players.values()))["p0"] < pinned
