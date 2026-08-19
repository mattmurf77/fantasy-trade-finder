"""Tier-bounded voting — a pin confines a player to a tier, it no longer freezes him.

Operator design call, 2026-08-18: "for deliberately placed players in tiers, the
voting can just rerank a player within his current set tier. So some adjustment
is expected, but nothing massive across a tier."

Supersedes the Phase 0 model (freeze + full release on a newer swipe;
docs/plans/three-model-bakeoff/scope-phase0.md). `pin_tier_bounded` reads the
pinned Elo as a TIER LABEL (`tier_for_elo`) and clamps every subsequent rating
update to that tier's band (`tier_bands_for` / `backend/tier_config.json`).
Nothing is written anywhere — the band is derived at compute time from the
pinned value the board already stores — so every pre-existing pin is covered
with no migration.

The audited case is the spine of this file: Davante Adams, pinned at 1565.2777
(2nd of 19 in "worth a 2nd", band [1370, 1575]), down-voted 17 times. Under the
freeze his Elo moved zero and his effective trade value ROSE 12.5%. Under
tier-bounding those votes must drive him materially DOWN and must never leave
[1370, 1575].

Everything here is offline — an in-memory RankingService, no DB, no network.
"""
import json
from pathlib import Path

import pytest

from backend import ranking_service as rs
from backend import trade_service as ts
from backend.ranking_service import Player, RankingService, SwipeDecision

GOLDEN = Path(__file__).parent / "fixtures" / "pin_tier_bounded_golden.json"

# The audited board's real numbers (1qb_ppr, 2026-08-18).
CONSENSUS_ELO = 1526.0
PIN_ELO = 1565.2777777777778     # 2nd of 19 in "worth a 2nd"
CONSENSUS_VALUE = 1138.8283833246219

# "worth a 2nd" in every (format, position) cell of tier_config.json.
# D-084 (2026-08-19): the `second` floor tracks the Late 2nd pick seed,
# which moved 1400 → 1370. `second.max` is unchanged at 1575.
SECOND_LO, SECOND_HI = 1370.0, 1575.0
FIRST_1_LO = 1580.0              # the next band up starts here (1576-1579 is a gap)

# The Phase 0 shipped defaults — the behaviour this change replaces, and the
# configuration the golden was captured under on pristine origin/main.
PHASE0 = {"pin_tier_bounded": 0.0,
          "pin_exclude_comparisons": 1.0,
          "pin_unpin_on_newer_swipe": 1.0,
          "pin_legacy_at_epoch": 0.0}
# Today's shipped defaults, read live so a future default change surfaces here.
SHIPPED = {k: rs._DEFAULT_CFG[k] for k in PHASE0}


@pytest.fixture(autouse=True)
def restore_cfg():
    """Every test mutates rs._cfg; put it back so ordering cannot matter."""
    before = dict(rs._cfg)
    yield
    rs._cfg.clear()
    rs._cfg.update(before)


def cfg(**overrides):
    """Start from the shipped defaults, then apply this test's overrides."""
    rs._cfg.update(SHIPPED)
    rs._cfg.update(overrides)


# ═══════════════════════════════════════════════════════════════════════════
# Fixture — one board covering every band case at once
# ═══════════════════════════════════════════════════════════════════════════

def build_service(scoring_format: str = "1qb_ppr"):
    """A board with one pinned player per interesting position in a band.

    adams     — pinned mid-band ABOVE consensus, down-voted 17x (the audit case)
    edge_hi   — pinned exactly at the band CEILING, then voted UP
    edge_lo   — pinned exactly at the band FLOOR, then voted DOWN
    boundary  — pinned exactly ON a band boundary (first_1's floor, 1580)
    gapped    — pinned in the GAP between two bands (1577 > second.max 1575)
    unranked  — pinned BELOW every band (DEMOTED_ELO, #161), and voted on
    rb_pin    — pinned, non-WR, to exercise the per-position band lookup
    free      — never pinned (control)
    quiet     — never pinned, never compared (pure-consensus control)

    Kept byte-identical to the capture script that produced the golden.
    """
    players = [
        Player(id="adams",    name="Pinned Vet",    position="WR", team="LAR", age=33),
        Player(id="edge_hi",  name="Band Ceiling",  position="WR", team="KC",  age=27),
        Player(id="edge_lo",  name="Band Floor",    position="WR", team="MIA", age=28),
        Player(id="boundary", name="On Boundary",   position="WR", team="CIN", age=25),
        Player(id="gapped",   name="In The Gap",    position="WR", team="PHI", age=26),
        Player(id="unranked", name="Passed Over",   position="WR", team="NYJ", age=31),
        Player(id="rb_pin",   name="Pinned Back",   position="RB", team="DAL", age=24),
        Player(id="free",     name="Free Agent",    position="WR", team="NYG", age=24),
        Player(id="quiet",    name="Quiet Player",  position="WR", team="SF",  age=25),
    ]
    seed = {
        "adams": CONSENSUS_ELO, "edge_hi": 1480.0, "edge_lo": 1470.0,
        "boundary": 1600.0, "gapped": 1560.0, "unranked": 1210.0,
        "rb_pin": 1650.0, "free": 1500.0, "quiet": 1450.0,
    }
    svc = RankingService(players, seed_ratings=seed)
    svc._scoring_format = scoring_format
    svc._elo_overrides = {
        "adams":    PIN_ELO,
        "edge_hi":  SECOND_HI,          # 1575.0 — ceiling of "worth a 2nd"
        "edge_lo":  SECOND_LO,          # 1370.0 — floor of "worth a 2nd"
        "boundary": FIRST_1_LO,         # 1580.0 — exactly a band boundary
        "gapped":   1577.0,             # between second.max and first_1.min
        "unranked": RankingService.DEMOTED_ELO,   # 1100.0 — below every band
        "rb_pin":   1700.0,             # mid "worth a 1st", RB row
    }

    pairs = [("free", "adams", f"2026-08-17T10:{i:02d}:00+00:00") for i in range(17)]
    pairs.append(("adams", "free", "2026-08-17T10:30:00+00:00"))
    # edge_hi keeps winning — he is already at his tier's ceiling.
    pairs += [("edge_hi", "free", f"2026-08-17T11:{i:02d}:00+00:00") for i in range(6)]
    # edge_lo keeps losing — he is already at his tier's floor.
    pairs += [("free", "edge_lo", f"2026-08-17T12:{i:02d}:00+00:00") for i in range(6)]
    # boundary loses a few: he must hold his boundary Elo exactly.
    pairs += [("free", "boundary", f"2026-08-17T13:{i:02d}:00+00:00") for i in range(4)]
    # gapped loses: his band was widened to contain the pin, so he can fall.
    pairs += [("free", "gapped", f"2026-08-17T14:{i:02d}:00+00:00") for i in range(4)]
    # unranked wins repeatedly: no band, so nothing may move him.
    pairs += [("unranked", "free", f"2026-08-17T15:{i:02d}:00+00:00") for i in range(5)]
    # rb_pin loses to a WR (cross-position pool) — bands are per position.
    pairs += [("free", "rb_pin", f"2026-08-17T16:{i:02d}:00+00:00") for i in range(3)]
    pairs.append(("free", "quiet", "2026-08-17T17:00:00+00:00"))

    svc._swipes = [SwipeDecision(winner_id=w, loser_id=l, timestamp=t)
                   for w, l, t in pairs]
    svc._version = len(svc._swipes)
    return svc, seed


def snapshot(svc, seed):
    """Every number this change can move — matches the golden's shape."""
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


def elo_of(svc, pid="adams"):
    return svc._compute_elo(list(svc._players.values()))[pid]


def effective_value(svc, seed, pid="adams"):
    """What the trade engine actually prices this player at."""
    counts = svc.comparison_counts()
    shrunk = ts._shrink_user_elo(svc._compute_elo(list(svc._players.values())),
                                 seed, counts)
    return ts.elo_to_value(shrunk[pid])


# ═══════════════════════════════════════════════════════════════════════════
# Kill-value byte identity
# ═══════════════════════════════════════════════════════════════════════════

def test_kill_value_is_byte_identical_to_the_captured_golden():
    """The one non-negotiable.

    `fixtures/pin_tier_bounded_golden.json` was CAPTURED by running this exact
    fixture against **pristine origin/main** (commit e8ae476) before a line of
    production code changed — so this compares against real recorded output,
    not against the new code's own opinion of what the old code did.

    PHASE0 is main's shipped configuration: tier-bounding off, F2 on. Setting
    those two knobs is the complete revert path.

    RE-CAPTURED 2026-08-19 (D-084), and re-captured the honest way. The
    fixture pins `edge_lo` to the `second` FLOOR, which moved 1400 → 1370, so
    the golden's input changed and the old recording could not stand. It was
    NOT regenerated from this branch's code. It was regenerated by running
    this same fixture against a pristine `origin/main` worktree (93ac695)
    with only `SECOND_LO` overridden — and the harness was first proved sound
    by re-capturing at 1400 and confirming it reproduced the previous golden
    byte-for-byte. So this still compares against real recorded old-code
    output.

    Seven numbers moved, all mechanically forced by the one changed input:
    `elo.edge_lo` (he is frozen ON his pin), plus small ripples in `free` and
    `quiet` — `free` is edge_lo's opponent in six comparisons, so shifting
    edge_lo's rating shifts free's expected scores, and `quiet` shares the
    pool. Nothing else in the fixture moved.
    """
    golden = json.loads(GOLDEN.read_text())
    cfg(**PHASE0)
    svc, seed = build_service()
    assert snapshot(svc, seed) == golden


def test_the_golden_itself_records_the_frozen_behaviour():
    """Guard the premise. If the golden ever stops showing a FROZEN pin, the
    fixture has drifted and the identity test above is measuring nothing."""
    golden = json.loads(GOLDEN.read_text())
    # Every pinned player sat exactly on his pin, no matter how he was voted.
    assert golden["elo"]["adams"] == round(PIN_ELO, 1)
    assert golden["elo"]["edge_hi"] == SECOND_HI
    assert golden["elo"]["edge_lo"] == SECOND_LO
    assert golden["elo"]["boundary"] == FIRST_1_LO
    assert golden["elo"]["gapped"] == 1577.0
    assert golden["elo"]["unranked"] == RankingService.DEMOTED_ELO
    # And none of them accrued any confidence, because no vote moved them.
    assert all(golden["counts"][pid] == 0 for pid in
               ("adams", "edge_hi", "edge_lo", "boundary", "gapped", "unranked"))
    # The unpinned control DID move, so the fixture really is exercising votes.
    assert golden["elo"]["free"] != round(1500.0, 1)


def test_the_kill_value_alone_restores_the_freeze():
    """Only `pin_tier_bounded` needs flipping to stop the new behaviour; the
    other knobs keep their shipped values."""
    cfg(pin_tier_bounded=0.0)
    svc, _ = build_service()
    elo = svc._compute_elo(list(svc._players.values()))
    assert elo["adams"] == pytest.approx(PIN_ELO)
    assert elo["edge_lo"] == pytest.approx(SECOND_LO)


# ═══════════════════════════════════════════════════════════════════════════
# The Adams scenario
# ═══════════════════════════════════════════════════════════════════════════

def test_adams_17_downvotes_move_him_down_inside_his_tier():
    """THE scenario. 17 down-votes on a player pinned at 1565.3 in
    "worth a 2nd" [1370, 1575] must move him materially DOWN and must never
    leave the band."""
    cfg()
    svc, _ = build_service()
    moved = elo_of(svc)
    assert moved < PIN_ELO - 50            # materially down, not a rounding blip
    assert SECOND_LO <= moved <= SECOND_HI


def test_adams_downvotes_lower_his_trade_value_instead_of_raising_it():
    """The inversion, inverted. Before this change 17 down-votes raised his
    effective trade value 12.5%; now they must lower it below consensus."""
    cfg()
    svc, seed = build_service()
    assert effective_value(svc, seed) < CONSENSUS_VALUE

    cfg(**PHASE0)
    frozen, seed = build_service()
    # Phase 0 removed the +12.5% by zeroing his confidence, so he prices at
    # exactly consensus — correct, but it discards the user's votes entirely.
    assert effective_value(frozen, seed) == pytest.approx(CONSENSUS_VALUE)


def _value_sweep(winner: str, loser: str, counts=(0, 1, 2, 5, 17, 40)):
    """Effective value of `adams` after n identical comparisons."""
    out = []
    for n in counts:
        svc, seed = build_service()
        svc._swipes = [SwipeDecision(winner, loser,
                                     f"2026-08-17T10:{i:02d}:00+00:00")
                       for i in range(n)]
        svc._version = n
        out.append(effective_value(svc, seed))
    return out


def test_more_downvotes_never_raise_value_once_the_board_has_weight():
    """The audit's finding was that value rose MONOTONICALLY with every extra
    down-vote. From the second vote on it must now fall, every time, and end
    up below consensus."""
    cfg()
    values = _value_sweep("free", "adams")
    assert values[1:] == sorted(values[1:], reverse=True)
    assert values[1] > values[-1]
    assert values[-1] < CONSENSUS_VALUE


def test_the_very_first_vote_raises_value_a_documented_residual():
    """Honest disclosure, pinned so it cannot change silently.

    n=0 means the shrinkage weight is 0 and the player prices at exactly the
    consensus seed — the tier placement counts for nothing. The first vote that
    MOVES him makes the board carry weight (w = 1/(1+n0) = 0.2), and this
    board says he is worth a 2nd, i.e. more than consensus. So value ticks up
    once before falling.

    This is the shrinkage model working as designed, not the audited
    inversion: it is a one-step effect of the pin gaining weight, it is small,
    and every subsequent down-vote reverses it (test above). The audited
    defect was unbounded and direction-blind; this is neither."""
    cfg()
    values = _value_sweep("free", "adams", counts=(0, 1))
    assert values[0] == pytest.approx(CONSENSUS_VALUE)
    assert values[1] > values[0]
    assert values[1] < CONSENSUS_VALUE * 1.03


def test_downvotes_never_price_above_upvotes_at_the_same_vote_count():
    """Direction-awareness — the property the audit found missing. Holding the
    number of comparisons fixed, voting a player DOWN must never value him at
    or above voting him UP."""
    cfg()
    down = _value_sweep("free", "adams", counts=(1, 2, 5, 17))
    up = _value_sweep("adams", "free", counts=(1, 2, 5, 17))
    assert all(d < u for d, u in zip(down, up))


def test_a_pinned_player_with_no_votes_is_untouched():
    """The clamp must never move a player on its own — only votes move him."""
    cfg()
    svc, seed = build_service()
    svc._swipes = []
    svc._version = 0
    elo = svc._compute_elo(list(svc._players.values()))
    for pid, pin in svc._elo_overrides.items():
        assert elo[pid] == pytest.approx(pin)
    assert effective_value(svc, seed) == pytest.approx(CONSENSUS_VALUE)


# ═══════════════════════════════════════════════════════════════════════════
# The band edges
# ═══════════════════════════════════════════════════════════════════════════

def test_votes_cannot_push_a_player_above_his_tier_ceiling():
    cfg()
    svc, _ = build_service()
    assert elo_of(svc, "edge_hi") == pytest.approx(SECOND_HI)


def test_votes_cannot_push_a_player_below_his_tier_floor():
    cfg()
    svc, _ = build_service()
    assert elo_of(svc, "edge_lo") == pytest.approx(SECOND_LO)


def test_a_player_pinned_exactly_on_a_band_boundary_holds_that_boundary():
    """1580.0 is `first_1`'s floor. Down-votes may not take him to 1579."""
    cfg()
    svc, _ = build_service()
    assert elo_of(svc, "boundary") == pytest.approx(FIRST_1_LO)


def test_a_clamped_player_can_still_move_back_toward_the_middle():
    """The clamp is a wall, not glue: a floor-pinned player who then WINS must
    climb back into the band."""
    cfg()
    svc, _ = build_service()
    svc._swipes = [SwipeDecision("edge_lo", "free",
                                 f"2026-08-18T09:{i:02d}:00+00:00")
                   for i in range(5)]
    svc._version = 99
    moved = elo_of(svc, "edge_lo")
    assert SECOND_LO < moved <= SECOND_HI


def test_a_pin_in_a_band_gap_keeps_its_own_value_as_the_ceiling():
    """`tier_config.json` has gaps (1576-1579 sits between `second`.max 1575
    and `first_1`.min 1580). `tier_for_elo(1577)` says `second`, whose max is
    BELOW the pin, so the band is widened to [1370, 1577]: he can fall through
    the tier but the clamp can never drag him down on its own."""
    cfg()
    svc, _ = build_service()
    moved = elo_of(svc, "gapped")
    assert SECOND_LO <= moved < 1577.0        # four losses moved him down
    up, _ = build_service()
    up._swipes = [SwipeDecision("gapped", "free", "2026-08-18T09:00:00+00:00")]
    up._version = 1
    assert elo_of(up, "gapped") == pytest.approx(1577.0)   # capped at his pin


def test_a_pin_above_the_top_band_can_fall_but_not_rise():
    """`apply_reorder` permutes raw seed Elos, which need not sit inside a
    band; the top band's max is finite. Widening to max(hi, pin) keeps a
    zero-vote player still and stops the clamp inventing an increase."""
    cfg()
    svc, _ = build_service()
    svc._elo_overrides["adams"] = 2100.0       # above firsts_4plus.max (1972)
    svc._swipes = [SwipeDecision("adams", "free", "2026-08-18T09:00:00+00:00")]
    svc._version = 1
    assert elo_of(svc) == pytest.approx(2100.0)

    down, _ = build_service()
    down._elo_overrides["adams"] = 2100.0
    down._swipes = [SwipeDecision("free", "adams", "2026-08-18T09:00:00+00:00")]
    down._version = 1
    assert 1927.0 <= elo_of(down) < 2100.0


# ═══════════════════════════════════════════════════════════════════════════
# Pins with no tier (below the lowest band)
# ═══════════════════════════════════════════════════════════════════════════

def test_a_pin_below_every_band_stays_frozen():
    """`tier_for_elo` returns None below 1150 — where #161's DEMOTED_ELO and
    the anchor wizard's "no value" answer put people. Those are deliberate
    'unranked, pending placement' markers, so a stray comparison must not drag
    one back onto the board. Frozen, not crashed, and not floated free."""
    cfg()
    svc, _ = build_service()
    assert elo_of(svc, "unranked") == pytest.approx(RankingService.DEMOTED_ELO)
    assert svc.comparison_counts()["unranked"] == 0


def test_an_unranked_pin_does_not_break_the_rest_of_the_board():
    """Regression guard: the None-tier branch is a `continue`, not an
    exception, so the players around him still compute."""
    cfg()
    svc, _ = build_service()
    elo = svc._compute_elo(list(svc._players.values()))
    assert len(elo) == len(svc._players)
    assert elo["free"] != 1500.0


# ═══════════════════════════════════════════════════════════════════════════
# pin_exclude_comparisons under tier-bounding
# ═══════════════════════════════════════════════════════════════════════════

def test_votes_that_moved_a_pinned_player_now_count_as_confidence():
    """The narrowing. Under the freeze every vote on a pin was inert and F1
    discarded them all (n=0, priced at consensus). Under tier-bounding those
    votes MOVE him, so they are real evidence and must count."""
    cfg()
    svc, _ = build_service()
    assert svc.comparison_counts()["adams"] > 0

    cfg(**PHASE0)
    frozen, _ = build_service()
    assert frozen.comparison_counts()["adams"] == 0


def test_votes_swallowed_by_the_clamp_do_not_count_as_confidence():
    """The residue F1 still excludes: a player at his band edge with the vote
    pushing him further out. Nothing moved, so it is not evidence — counting it
    would raise confidence in a number the user was trying to lower, which is
    the original inversion one tier down."""
    cfg()
    svc, _ = build_service()
    counts = svc.comparison_counts()
    assert counts["edge_hi"] == 0        # 6 wins, all absorbed by the ceiling
    assert counts["edge_lo"] == 0        # 6 losses, all absorbed by the floor
    assert counts["boundary"] == 0


def test_a_partly_clamped_vote_still_counts():
    """A vote that moves him *some* of the way to the edge did change his
    rating, so it is evidence."""
    cfg()
    svc, _ = build_service()
    svc._swipes = [SwipeDecision("free", "adams", "2026-08-17T10:00:00+00:00")]
    svc._version = 1
    assert svc.comparison_counts()["adams"] == 1
    assert elo_of(svc) < PIN_ELO


def test_killing_pin_exclude_comparisons_restores_raw_counts():
    """The knob is still load-bearing: at 0.0 every comparison counts again,
    including the ones the clamp swallowed."""
    cfg(pin_exclude_comparisons=0.0)
    svc, _ = build_service()
    counts = svc.comparison_counts()
    assert counts["edge_hi"] == 1        # 6 comparisons, 1 unique opponent
    assert counts["edge_lo"] == 1
    assert counts["unranked"] == 1


def test_uncertainty_shares_the_same_map():
    """`_value_uncertainty` reads the same confidence map, so a clamped-at-the-
    edge player keeps maximum uncertainty rather than false precision."""
    cfg()
    svc, _ = build_service()
    counts = svc.comparison_counts()
    assert ts._value_uncertainty("edge_hi", counts) == pytest.approx(
        ts._value_uncertainty("quiet_unknown_pid", {}))


def test_unpinned_players_counts_are_untouched():
    """The recount only ever touches pinned pids."""
    cfg()
    svc, _ = build_service()
    bounded = svc.comparison_counts()
    cfg(pin_exclude_comparisons=0.0)
    raw, _ = build_service()
    assert bounded["free"] == raw.comparison_counts()["free"]
    assert bounded["quiet"] == raw.comparison_counts()["quiet"]


# ═══════════════════════════════════════════════════════════════════════════
# Scoring formats
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fmt", ["1qb_ppr", "sf_tep"])
def test_both_scoring_formats_bound_the_same_way(fmt):
    """`tier_config.json` ships identical bands in both formats by design
    (pick value is position- and format-uniform), so the outcome must match."""
    cfg()
    svc, _ = build_service(scoring_format=fmt)
    assert elo_of(svc) == pytest.approx(elo_of(build_service("1qb_ppr")[0]))
    assert SECOND_LO <= elo_of(svc) <= SECOND_HI


def test_the_clamp_reads_the_services_own_scoring_format(monkeypatch):
    """Plumbing proof: bands are equal today, so widen sf_tep's WR "second"
    band and check only the sf_tep service follows it."""
    cfg()
    wide = {t: dict(b) for t, b in rs.TIER_CONFIG["sf_tep"]["WR"].items()}
    wide["second"] = {"min": 1000, "max": 1575}
    monkeypatch.setitem(rs.TIER_CONFIG["sf_tep"], "WR", wide)

    sf, _ = build_service(scoring_format="sf_tep")
    one_qb, _ = build_service(scoring_format="1qb_ppr")
    # edge_lo is pinned ON the floor and voted down, so the floor is what holds
    # him: move the floor and only the sf_tep service follows.
    assert elo_of(sf, "edge_lo") < SECOND_LO
    assert elo_of(one_qb, "edge_lo") == pytest.approx(SECOND_LO)


def test_per_position_band_lookup(monkeypatch):
    """Bands are per (format, position); the RB pin must read the RB row."""
    cfg()
    narrow = {t: dict(b) for t, b in rs.TIER_CONFIG["1qb_ppr"]["RB"].items()}
    narrow["first_1"] = {"min": 1699, "max": 1785}
    monkeypatch.setitem(rs.TIER_CONFIG["1qb_ppr"], "RB", narrow)

    svc, _ = build_service()
    assert elo_of(svc, "rb_pin") == pytest.approx(1699.0)   # RB floor, not 1580


# ═══════════════════════════════════════════════════════════════════════════
# Interaction with the superseded F2 knobs, and with the memo
# ═══════════════════════════════════════════════════════════════════════════

def test_f2_is_off_by_default():
    """`pin_unpin_on_newer_swipe` and `pin_legacy_at_epoch` are superseded: a
    pin is now a durable band constraint, not something a swipe expires."""
    assert rs._DEFAULT_CFG["pin_unpin_on_newer_swipe"] == 0.0
    assert rs._DEFAULT_CFG["pin_legacy_at_epoch"] == 0.0
    assert rs._DEFAULT_CFG["pin_tier_bounded"] == 1.0


def test_a_released_pin_evolves_unclamped_when_f2_is_turned_back_on():
    """Interaction rule: F2 release means the pin is GONE, so tier-bounding no
    longer applies to him. Only pins still in force are clamped."""
    cfg(pin_unpin_on_newer_swipe=1.0)
    svc, _ = build_service()
    svc._elo_override_at = {pid: "2026-08-01T00:00:00+00:00"
                            for pid in svc._elo_overrides}
    assert elo_of(svc, "edge_lo") < SECOND_LO     # unclamped, below the floor


def test_tier_bounding_still_applies_to_pins_f2_did_not_release():
    """A legacy (unstamped) pin is not released, so the band still governs it
    even with F2 on."""
    cfg(pin_unpin_on_newer_swipe=1.0)
    svc, _ = build_service()          # no stamps written -> all legacy
    assert elo_of(svc, "edge_lo") == pytest.approx(SECOND_LO)


def test_the_knob_is_in_the_memo_key():
    """A live `PUT /api/admin/config` must take effect on a warm session — the
    memo is keyed on `_version`, which a config write does not bump."""
    cfg()
    svc, _ = build_service()
    bounded = elo_of(svc)
    rs._cfg["pin_tier_bounded"] = 0.0
    assert elo_of(svc) == pytest.approx(PIN_ELO)      # no _version bump needed
    rs._cfg["pin_tier_bounded"] = 1.0
    assert elo_of(svc) == pytest.approx(bounded)


def test_comparison_counts_memo_also_tracks_the_knob():
    cfg()
    svc, _ = build_service()
    assert svc.comparison_counts()["edge_hi"] == 0
    rs._cfg["pin_exclude_comparisons"] = 0.0
    assert svc.comparison_counts()["edge_hi"] == 1


def test_a_board_with_no_pins_is_completely_unaffected():
    """Cheapest possible guard on blast radius."""
    cfg()
    svc, seed = build_service()
    svc._elo_overrides = {}
    bounded = snapshot(svc, seed)
    cfg(**PHASE0)
    other, seed = build_service()
    other._elo_overrides = {}
    assert bounded == snapshot(other, seed)
