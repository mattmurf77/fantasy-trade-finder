"""Placement tier clamp — a deliberately placed player is priced in HIS tier.

D-085 (2026-08-19). Confidence shrinkage blends a personal Elo toward the
consensus seed with ``w = n/(n + shrink_pseudocount)``, and ``n`` counts
COMPARISONS. A tier save / drag-reorder is not a sample — it is an assertion,
the strongest statement of value the product accepts — and ``w`` cannot see
assertions. So a player the user deliberately placed, but has rarely compared
head-to-head, was priced wherever consensus wanted him and then offered for
assets of that other tier.

The operator's live case is the spine of this file: Davante Adams placed in
the user's `third` band while consensus prices him at value 1138.8 → Elo 1526,
which is `second`. One full tier up.

The fix is the operator's own already-shipped voting rule (``pin_tier_bounded``
— "the voting can just rerank a player within his current set tier ... nothing
massive across a tier") applied one layer further out, to how the engine
PRICES the result: clamp the shrunk Elo to the placed tier's band. Shrinkage
itself is preserved — a player the user never compared still has a default,
not an opinion.

Band numbers are read LIVE from tier_config.json rather than hardcoded. D-084
moved `second`.min 1400 → 1370 and `third`.max 1395 → 1365 while this change
was being written; a hardcoded copy would have gone stale silently and asserted
the wrong thing.

Everything here is offline: an in-memory RankingService, no DB, no network.
"""
import inspect

import pytest

from backend import ranking_service as rs
from backend import trade_service as ts
from backend.ranking_service import Player, RankingService, SwipeDecision

FMT = "1qb_ppr"
_WR_BANDS = RankingService.tier_bands_for("WR", FMT)
THIRD_LO, THIRD_HI = _WR_BANDS["third"]
SECOND_LO, SECOND_HI = _WR_BANDS["second"]
FIRST_1_LO, FIRST_1_HI = _WR_BANDS["first_1"]

# The audited board's real numbers (1qb_ppr, 2026-08-18).
ADAMS_CONSENSUS_ELO = 1526.0                       # value 1138.8 → `second`
ADAMS_PLACED_ELO = (THIRD_LO + THIRD_HI) / 2.0     # mid-`third`, where he was put
# A pin inside the GAP between `second`.max and `first_1`.min (1576-1579).
GAP_PIN = SECOND_HI + 2.0

PIN_KNOBS = ("pin_tier_bounded", "pin_exclude_comparisons",
             "pin_unpin_on_newer_swipe", "pin_legacy_at_epoch")


def test_band_constants_match_the_shipped_config():
    """Guard the guard: these tests only mean something if the bands they read
    are the ones the engine uses, the gap really is a gap, and `second` really
    does sit above `third` (the direction the whole defect depends on)."""
    assert THIRD_LO < THIRD_HI < SECOND_LO < SECOND_HI < FIRST_1_LO < FIRST_1_HI
    assert RankingService.tier_for_elo(GAP_PIN, "WR", FMT) == "second"
    assert GAP_PIN > SECOND_HI                      # genuinely outside the band
    assert RankingService.tier_for_elo(ADAMS_PLACED_ELO, "WR", FMT) == "third"
    assert RankingService.tier_for_elo(ADAMS_CONSENSUS_ELO, "WR", FMT) == "second"


@pytest.fixture(autouse=True)
def restore_cfg():
    """Both modules' live config are process globals; put them back."""
    rs_before, ts_before = dict(rs._cfg), dict(ts._cfg)
    yield
    rs._cfg.clear(); rs._cfg.update(rs_before)
    ts._cfg.clear(); ts._cfg.update(ts_before)


def shipped():
    """Reset the pin knobs to the shipped defaults, read live."""
    rs._cfg.update({k: rs._DEFAULT_CFG[k] for k in PIN_KNOBS})


# ═══════════════════════════════════════════════════════════════════════════
# Fixture — one board covering every placement case at once
# ═══════════════════════════════════════════════════════════════════════════

def build_service():
    """A board whose pins exercise each branch of the clamp.

    adams     — placed in `third`, consensus sits a full tier UP (`second`).
                THE case. Never compared, so w = 0 and the blend is pure
                consensus.
    cheap     — placed in `first_1`, consensus a tier DOWN (`second`). The
                clamp must lift, not only lower.
    agree     — placed in `second` with consensus in `second`. Inside the band
                from both directions; the clamp must never touch him.
    demoted   — placed BELOW every band (#161 DEMOTED_ELO). No band exists,
                so nothing is clamped.
    gapped    — placed in the GAP above `second`.max. The band is widened to
                contain the pin.
    rb_pin    — placed, non-WR, to exercise the per-position band lookup.
    quiet     — never placed, never compared (control at n = 0).
    f0..f11   — never placed, seeded mid-`third`; the DISTINCT opponents a
                comparison count is built from (`comparison_counts` counts
                unique opponents, so one rival voted 30 times is n = 1).
    """
    mid_second = (SECOND_LO + SECOND_HI) / 2.0
    mid_first_1 = (FIRST_1_LO + FIRST_1_HI) / 2.0
    players = [
        Player(id="adams",   name="Placed Vet",    position="WR", team="LAR", age=33),
        Player(id="cheap",   name="Placed High",   position="WR", team="KC",  age=25),
        Player(id="agree",   name="Placed Agreed", position="WR", team="MIA", age=27),
        Player(id="demoted", name="Passed Over",   position="WR", team="NYJ", age=31),
        Player(id="gapped",  name="In The Gap",    position="WR", team="PHI", age=26),
        Player(id="rb_pin",  name="Placed Back",   position="RB", team="DAL", age=24),
        Player(id="quiet",   name="Never Placed",  position="WR", team="NYG", age=24),
    ] + [Player(id=f"f{i}", name=f"Filler {i}", position="WR", team="SF", age=26)
         for i in range(12)]
    seed = {
        "adams":   ADAMS_CONSENSUS_ELO,
        "cheap":   mid_second,        # `second` — a tier BELOW his placement
        "agree":   mid_second,        # `second` — the same tier as his placement
        "demoted": mid_second,        # consensus likes him; the user did not
        "gapped":  mid_second,
        "rb_pin":  1900.0,            # consensus two tiers above `first_1`
        "quiet":   mid_second,
    }
    seed.update({f"f{i}": ADAMS_PLACED_ELO for i in range(12)})
    svc = RankingService(players, seed_ratings=seed)
    svc._scoring_format = FMT
    for pid, elo in (
        ("adams",   ADAMS_PLACED_ELO),
        ("cheap",   mid_first_1),
        ("agree",   mid_second),
        ("demoted", RankingService.DEMOTED_ELO),    # 1100.0 — below every band
        ("gapped",  GAP_PIN),                       # second.max < pin < first_1.min
        ("rb_pin",  mid_first_1),                   # mid `first_1`, RB row
    ):
        svc._pin(pid, elo, at="2026-08-18T09:00:00+00:00")

    # `agree` is well compared — one win and one loss against each of the 12
    # fillers. Every other placed player is barely touched, which is exactly
    # the shape that makes the defect bite.
    pairs = []
    for i in range(12):
        pairs.append((f"f{i}", "agree", f"2026-08-18T10:{i:02d}:00+00:00"))
        pairs.append(("agree", f"f{i}", f"2026-08-18T11:{i:02d}:00+00:00"))
    svc._swipes = [SwipeDecision(winner_id=w, loser_id=l, timestamp=t)
                   for w, l, t in pairs]
    svc._version = len(svc._swipes)
    return svc, seed


def priced(svc, seed, placements=None):
    """The engine's personal Elo map after shrinkage (+ the clamp)."""
    raw = svc._compute_elo(list(svc._players.values()))
    return ts._shrink_user_elo(raw, seed, svc.comparison_counts(), placements)


def tier(elo, position="WR"):
    return RankingService.tier_for_elo(elo, position, FMT)


# ═══════════════════════════════════════════════════════════════════════════
# The defect, and the fix
# ═══════════════════════════════════════════════════════════════════════════

def test_unclamped_prices_a_placed_player_a_full_tier_up():
    """The defect, stated as a test: without the clamp the engine prices the
    operator's third-tier Adams in `second` — the tier he was NOT placed in."""
    shipped()
    svc, seed = build_service()
    before = priced(svc, seed)["adams"]
    assert tier(ADAMS_PLACED_ELO) == "third"
    assert before == pytest.approx(ADAMS_CONSENSUS_ELO)   # n = 0 ⇒ pure consensus
    assert tier(before) == "second"


def test_clamp_keeps_a_placed_player_inside_his_placed_tier():
    shipped()
    svc, seed = build_service()
    after = priced(svc, seed, svc.placement_bands())["adams"]
    assert tier(after) == "third"
    assert THIRD_LO <= after <= THIRD_HI
    # Consensus still pulls him to the TOP of the tier the user chose — the
    # clamp bounds the disagreement, it does not erase it.
    assert after == pytest.approx(THIRD_HI)


def test_clamp_lifts_as_well_as_lowers():
    """A player placed ABOVE consensus is held up into his band, not only
    pulled down out of one. The rule is a band, not a ceiling."""
    shipped()
    svc, seed = build_service()
    bands = svc.placement_bands()
    before, after = priced(svc, seed)["cheap"], priced(svc, seed, bands)["cheap"]
    assert tier(before) == "second"
    assert tier(after) == "first_1"
    assert after == pytest.approx(FIRST_1_LO)


def test_consensus_still_moves_him_inside_the_band():
    """The operator's rule: "some adjustment is expected, but nothing massive
    across a tier". Sweeping consensus across `third` must move the priced
    value across `third` — and stop at its edges."""
    shipped()
    svc, _ = build_service()
    bands = svc.placement_bands()
    raw = svc._compute_elo(list(svc._players.values()))
    counts = svc.comparison_counts()
    seen = []
    for consensus in (THIRD_LO - 100, THIRD_LO + 10, ADAMS_PLACED_ELO,
                      THIRD_HI - 5, ADAMS_CONSENSUS_ELO, 1900.0):
        seen.append(ts._shrink_user_elo({"adams": raw["adams"]},
                                        {"adams": consensus},
                                        counts, bands)["adams"])
    assert seen == sorted(seen)                    # monotone in consensus
    assert min(seen) == pytest.approx(THIRD_LO)    # floored, not below
    assert max(seen) == pytest.approx(THIRD_HI)    # capped, not above
    assert len(set(seen)) > 1                      # genuinely re-priced inside
    assert all(THIRD_LO <= v <= THIRD_HI for v in seen)


def test_clamp_is_inert_when_user_and_consensus_agree_on_the_tier():
    """The clamp bites only where shrinkage carried a placement OUT of its
    band. When the user's placement and consensus name the same tier, both
    endpoints of the blend are inside the band, so the blend is too — at any
    confidence, including a heavily-voted board."""
    shipped()
    svc, seed = build_service()
    assert svc.comparison_counts()["agree"] == 12      # 12 distinct opponents
    assert tier(seed["agree"]) == "second"
    assert (priced(svc, seed)["agree"]
            == pytest.approx(priced(svc, seed, svc.placement_bands())["agree"]))


def test_the_clamp_stops_biting_as_confidence_rises():
    """Shrinkage is preserved, so the clamp's job shrinks as the user supplies
    real evidence: the displacement it applies falls monotonically with n and
    reaches exactly zero once the blend lands back inside the band on its own.
    The clamp is a floor under the placement, not a replacement for voting."""
    shipped()
    raw, seed = {"adams": ADAMS_PLACED_ELO}, {"adams": ADAMS_CONSENSUS_ELO}
    bands = {"adams": (THIRD_LO, THIRD_HI)}
    bites = []
    for n in range(0, 201):
        counts = {"adams": n}
        loose = ts._shrink_user_elo(raw, seed, counts)["adams"]
        tight = ts._shrink_user_elo(raw, seed, counts, bands)["adams"]
        assert THIRD_LO <= tight <= THIRD_HI
        bites.append(round(loose - tight, 9))
    assert bites == sorted(bites, reverse=True)        # monotonically smaller
    assert bites[0] > 0                                # n = 0: the full defect
    assert bites[-1] == 0                              # well-voted: inert


def test_re_placing_a_player_moves_where_he_is_priced():
    """The correction path for a MIS-placement: put him in a different tier and
    the priced value follows, because the band is derived from the placement at
    compute time and nothing is persisted separately."""
    shipped()
    svc, seed = build_service()
    assert tier(priced(svc, seed, svc.placement_bands())["adams"]) == "third"
    svc._pin("adams", (SECOND_LO + SECOND_HI) / 2.0, at="2026-08-19T09:00:00+00:00")
    svc._version += 1
    assert tier(priced(svc, seed, svc.placement_bands())["adams"]) == "second"


def test_clamp_is_a_band_not_a_freeze_at_the_placed_value():
    """A clamp, not `w = 1`. The engine does not price the user's pin back at
    him: consensus still carries him across his own tier, up to its ceiling."""
    shipped()
    svc, seed = build_service()
    after = priced(svc, seed, svc.placement_bands())["adams"]
    assert after != pytest.approx(ADAMS_PLACED_ELO)
    assert after > ADAMS_PLACED_ELO


# ═══════════════════════════════════════════════════════════════════════════
# Blast radius — who the clamp must NOT touch
# ═══════════════════════════════════════════════════════════════════════════

def test_unplaced_players_are_never_clamped():
    """Clamping an unplaced player would freeze the board at consensus."""
    shipped()
    svc, seed = build_service()
    bands = svc.placement_bands()
    assert "quiet" not in bands
    assert (priced(svc, seed)["quiet"]
            == pytest.approx(priced(svc, seed, bands)["quiet"]))


def test_a_placement_below_the_lowest_band_is_not_clamped():
    """#161 demotion / anchor "no value" (1100) sit below every band, so
    `tier_for_elo` returns None and there is nothing to clamp to. They are
    "unranked, pending placement" markers, not tier placements — pricing a
    player into a sub-1150 non-band would be an assertion the user never
    made. Same population `_pin_bounds` leaves frozen."""
    shipped()
    svc, seed = build_service()
    bands = svc.placement_bands()
    assert tier(RankingService.DEMOTED_ELO) is None
    assert "demoted" not in bands
    assert (priced(svc, seed)["demoted"]
            == pytest.approx(priced(svc, seed, bands)["demoted"]))


def test_gap_placement_band_is_widened_to_contain_the_pin():
    """tier_config.json has gaps between bands. A player placed there keeps his
    own value as the bound, so the clamp can never move him further from his
    placement than the band already does."""
    shipped()
    svc, _ = build_service()
    assert svc.placement_bands()["gapped"] == (SECOND_LO, GAP_PIN)


def test_bands_are_looked_up_per_position():
    shipped()
    svc, seed = build_service()
    bands = svc.placement_bands()
    assert bands["rb_pin"] == (FIRST_1_LO, FIRST_1_HI)
    assert tier(priced(svc, seed, bands)["rb_pin"], "RB") == "first_1"


def test_value_uncertainty_ignores_placements():
    """Deliberate (D-085): the half-width feeds a GATE (range-overlap
    fairness), and gates price the real package. A placement bounds where the
    point estimate may sit; it does not claim precision inside the band. Pinned
    so a later change to `_value_uncertainty` is a decision, not a drive-by."""
    shipped()
    svc, _ = build_service()
    counts = svc.comparison_counts()
    assert "placements" not in inspect.signature(ts._value_uncertainty).parameters
    assert counts["adams"] == counts["quiet"] == 0
    assert (ts._value_uncertainty("adams", counts)        # placed
            == ts._value_uncertainty("quiet", counts))    # unplaced


# ═══════════════════════════════════════════════════════════════════════════
# Kill switch
# ═══════════════════════════════════════════════════════════════════════════

def test_knob_at_zero_is_byte_identical():
    """`placement_tier_clamp` = 0 restores the pre-D-085 blend for the WHOLE
    board, even with a fully populated placements map."""
    shipped()
    svc, seed = build_service()
    bands = svc.placement_bands()
    assert bands                                   # the map is not empty
    ts._cfg["placement_tier_clamp"] = 0.0
    assert priced(svc, seed, bands) == priced(svc, seed, None)


def test_default_is_on():
    assert ts._DEFAULT_CFG["placement_tier_clamp"] == 1.0


def test_arm_a_disables_the_clamp():
    """The bake-off is live. Arm A is the pre-wave engine, so it must pin this
    knob at its kill value or the arm silently drifts."""
    from backend.bakeoff_profiles import MODEL_A_PROFILE
    assert MODEL_A_PROFILE["placement_tier_clamp"] == 0.0


def test_no_confidence_map_means_no_shrinkage_and_no_clamp():
    """`confidence=None` is "no information at all" — the pre-existing
    early-out. A placement map must not smuggle a clamp past it, because the
    unshrunk personal Elo IS the user's own number already."""
    shipped()
    svc, seed = build_service()
    raw = svc._compute_elo(list(svc._players.values()))
    assert ts._shrink_user_elo(raw, seed, None, svc.placement_bands()) == raw


# ═══════════════════════════════════════════════════════════════════════════
# placement_bands() itself
# ═══════════════════════════════════════════════════════════════════════════

def test_placement_bands_agrees_with_tier_bounded_voting():
    """One definition of "the tier the user placed him in", shared by the
    voting clamp and the pricing clamp."""
    shipped()
    svc, _ = build_service()
    assert svc.placement_bands() == svc._pin_bounds(set(svc._players), {})


def test_placement_bands_is_independent_of_pin_tier_bounded():
    """`pin_tier_bounded` governs how VOTES move a placement; the pricing clamp
    is a different question. With voting-bounding off a placement is a total
    freeze, which is exactly when the blend drags hardest."""
    shipped()
    rs._cfg["pin_tier_bounded"] = 0.0
    svc, seed = build_service()
    assert svc._pin_bounds(set(svc._players), {}) == {}     # voting frozen
    bands = svc.placement_bands()
    assert bands["adams"] == (THIRD_LO, THIRD_HI)           # pricing still bounded
    assert tier(priced(svc, seed, bands)["adams"]) == "third"


def test_placement_bands_drops_a_released_pin():
    """F2 (`pin_unpin_on_newer_swipe`) release means the placement is GONE, so
    there is nothing left to honour. Off by default; this is the interaction
    rule, not the normal path."""
    shipped()
    rs._cfg["pin_unpin_on_newer_swipe"] = 1.0
    svc, _ = build_service()
    assert "adams" in svc.placement_bands()
    svc._swipes.append(SwipeDecision(winner_id="f0", loser_id="adams",
                                     timestamp="2026-08-19T09:00:00+00:00"))
    svc._version = len(svc._swipes)
    assert "adams" not in svc.placement_bands()


def test_placement_bands_is_empty_for_a_swipe_only_board():
    shipped()
    svc, _ = build_service()
    svc._elo_overrides = {}
    svc._elo_override_at = {}
    assert svc.placement_bands() == {}
