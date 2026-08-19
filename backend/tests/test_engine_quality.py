"""Engine quality — 2026-08-18 field wave (docs/plans/engine-quality/scope.md).

Two defects diagnosed from the live corpus (563 impressions / 8h):

  A. **Picks are free fairness.** Draft picks carry ZERO board divergence by
     construction (every board is primed with the same bridged Elo — see the
     pick_swap_ok docstring), so a pick adds nothing to the mutual-gain story,
     yet it RAISES the consensus fairness term whenever it closes the
     give/receive value gap. Nothing penalises package size, so a pick was a
     pure composite gain at zero cost: 63% of live cards involved one.
  B. **One player floods the deck.** `mismatch` is largest for whichever asset
     diverges most between the two boards, so that asset generates many
     distinct high-scoring packages and exact-key dedup keeps all of them.
     Colston Loveland appeared in 18 of 18 cards of one deck.

Five knobs, each with a kill value that restores prior behaviour. Every knob
gets a behaviour test AND a kill-value test here; the cross-knob byte-identity
proof against origin/main lives in test_engine_quality_golden.py.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    board_divergence,
    elo_to_value,
    rank_fairness,
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


# ───────────────────────────────────────────────────────────────────────────
# Shared fixture shapes
# ───────────────────────────────────────────────────────────────────────────

class _Player:
    def __init__(self, pid, position="WR", team="TST", age=24):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = age
        self.ktc_value = None


class _Pick(_Player):
    """Owned-pick pseudo-player, shaped like server._owned_pick_assets'."""

    def __init__(self, pid, pick_value=60.0):
        super().__init__(pid, position="PICK", team="PICK", age=0)
        self.pick_value = pick_value


# A full legal lineup per side (QB1/RB2/WR2/TE1) so v3 feasibility is never
# the thing under test.
_FILL = {"q": "QB", "r1": "RB", "r2": "RB", "w1": "WR", "w2": "WR", "t": "TE"}


def _bodies(prefix):
    return {f"{prefix}{k}": pos for k, pos in _FILL.items()}


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _find(cards, give, recv):
    g, r = sorted(give), sorted(recv)
    for c in cards:
        if (sorted(c.give_player_ids), sorted(c.receive_player_ids)) == (g, r):
            return c
    return None


# ───────────────────────────────────────────────────────────────────────────
# C1 — divergence-gated ranking fairness (Defect A)
# ───────────────────────────────────────────────────────────────────────────

def _vals(mapping):
    """(user_val, opp_val) accessors from a {pid: (user_elo, opp_elo)} map."""
    return (lambda p: elo_to_value(mapping[p][0]),
            lambda p: elo_to_value(mapping[p][1]))


def test_board_divergence_is_zero_for_identically_priced_assets():
    """The premise of the whole change: a pick prices identically on every
    board, so its divergence is exactly 0 — no rounding slack."""
    boards = {"PK": (1400.0, 1400.0), "WR": (1500.0, 1700.0)}
    uv, ov = _vals(boards)
    assert board_divergence("PK", uv, ov) == 0.0
    assert board_divergence("WR", uv, ov) > 0.1
    # a divergence-free player is treated exactly like a pick — the rule is
    # about information, not about asset type
    boards["FLAT"] = (1500.0, 1500.0)
    assert board_divergence("FLAT", uv, ov) == 0.0


def test_rank_fairness_is_invariant_to_adding_a_zero_divergence_asset():
    """THE property behind C1. Adding a zero-divergence asset to either side
    leaves the RANKING fairness term bit-for-bit unchanged — for any base
    package, fair or not — while the full-package fairness (still the gate,
    still what the card stamps) moves as it always did."""
    boards = {
        "G1": (1500.0, 1700.0),      # user gives; opp values him more
        "R1": (1700.0, 1500.0),      # user receives; user values him more
        "PK": (1400.0, 1400.0),      # zero divergence by construction
    }
    seed = {"G1": 1600.0, "R1": 1680.0, "PK": 1400.0}
    sv = lambda p: elo_to_value(seed[p])
    uv, ov = _vals(boards)

    def full_fairness(g, r):
        gv = ts.package_value_v2([sv(p) for p in g],
                                 max(sv(p) for p in g + r),
                                 n_other=len(r), other_values=[sv(p) for p in r])
        rv = ts.package_value_v2([sv(p) for p in r],
                                 max(sv(p) for p in g + r),
                                 n_other=len(g), other_values=[sv(p) for p in g])
        return min(gv, rv) / max(gv, rv)

    base_full = full_fairness(["G1"], ["R1"])
    padded_full = full_fairness(["G1", "PK"], ["R1"])
    # fixture validity: the pick really does move the full-package fairness —
    # that movement is exactly the free score C1 takes away
    assert padded_full != pytest.approx(base_full), (
        "fixture no longer reproduces the defect: the pick does not move "
        "full-package fairness")

    base_rank = rank_fairness(base_full, ["G1"], ["R1"], sv, uv, ov)
    padded_rank = rank_fairness(padded_full, ["G1", "PK"], ["R1"], sv, uv, ov)
    assert padded_rank == base_rank, (
        f"a zero-divergence asset moved the ranking fairness term: "
        f"{base_rank} -> {padded_rank}")
    # and symmetrically on the receive side
    recv_padded_full = full_fairness(["G1"], ["R1", "PK"])
    recv_padded_rank = rank_fairness(recv_padded_full, ["G1"], ["R1", "PK"],
                                     sv, uv, ov)
    assert recv_padded_rank == base_rank


def test_rank_fairness_falls_back_when_a_side_has_no_signal():
    """"Buy a player with a pick" must not lose the whole fairness term: when
    stripping empties a side there is nothing to price the core on, so the
    real full-package fairness stands."""
    boards = {"PK": (1400.0, 1400.0), "R1": (1700.0, 1500.0)}
    seed = {"PK": 1600.0, "R1": 1620.0}
    sv = lambda p: elo_to_value(seed[p])
    uv, ov = _vals(boards)
    assert rank_fairness(0.812, ["PK"], ["R1"], sv, uv, ov) == 0.812


def test_rank_fairness_kill_value_returns_full_fairness_untouched():
    """Kill value: rank_div_min_frac = 0 ⇒ the ranking fairness IS the
    full-package fairness, byte-identical to pre-C1."""
    boards = {"G1": (1500.0, 1700.0), "R1": (1700.0, 1500.0),
              "PK": (1400.0, 1400.0)}
    seed = {"G1": 1600.0, "R1": 1680.0, "PK": 1400.0}
    sv = lambda p: elo_to_value(seed[p])
    uv, ov = _vals(boards)
    ts._cfg["rank_div_min_frac"] = 0.0
    for g, r in ((["G1"], ["R1"]), (["G1", "PK"], ["R1"]),
                 (["G1"], ["R1", "PK"])):
        assert rank_fairness(0.6371, g, r, sv, uv, ov) == 0.6371


# ── engine-level property (the brief's explicit ask) ───────────────────────

def _pick_fixture(*, opp_seed=1620.0, pick_seed=1250.0):
    """One divergent pair (uA <-> oB) plus a pick the user could throw in.

    Consensus seeds are set so the BARE 1-for-1 is already fair (ratio ~0.9)
    and the pick's only possible contribution is to shave the remaining gap —
    the operator's "the pick is pure fine-tuning on a trade that was already
    fair" shape. Every filler prices identically on both boards, so the
    divergent pair is the whole signal core.
    """
    pos = {"uA": "WR", "oB": "WR", **_bodies("u"), **_bodies("o")}
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    players["PKu"] = _Pick("PKu")
    user_roster = ["uA"] + list(_bodies("u")) + ["PKu"]
    opp_roster = ["oB"] + list(_bodies("o"))
    seed = {pid: 1250.0 for pid in pos}
    seed.update({"uA": 1600.0, "oB": opp_seed, "PKu": pick_seed})
    user_elo, opp_elo = dict(seed), dict(seed)
    user_elo["uA"], opp_elo["uA"] = 1480.0, 1720.0
    user_elo["oB"], opp_elo["oB"] = opp_seed + 120.0, opp_seed - 120.0
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings=opp_elo, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, user_elo, user_roster, seed


# The junk-filler floor, the Elo-gap guard and the per-side surplus minimum
# are all orthogonal to what C1 changes, and each of them independently vetoes
# the two shapes this test has to compare. Pinning them open is the same
# fixture technique test_pick_swap_gate.py uses for the #189 relaxed stage.
_ORTHOGONAL_GATES_OPEN = {
    "trade_elo_gap_max": 0.0,
    "filler_min_frac": 0.0,
    "min_side_surplus": 0.0,
    "min_side_surplus_marginal": 0.0,
    # C4's headliner cap is off here too: the two cards this fixture compares
    # are the same trade with and without a pick, so they share a centerpiece
    # by construction and the cap would remove one of them. C4 has its own
    # fixture below. C4b's give-side cap is off for the same reason — the two
    # cards give the SAME side, so they share a give headliner by construction.
    "deck_headliner_cap": 0.0,
    "deck_give_headliner_cap": 0.0,
}


def _pick_deck(**cfg):
    _set_flags(**{"trade_engine.v2": True})
    ts._cfg.clear()                       # tests call this twice per case
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(_ORTHOGONAL_GATES_OPEN)
    ts._cfg.update(cfg)
    svc, ue, ur, seed = _pick_fixture()
    return svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                               league_id="L1", seed_elo=seed,
                               fairness_threshold=0.6, max_per_opponent=400)


def test_adding_a_pick_to_a_fair_package_does_not_raise_composite():
    """Defect A, pinned. The bare 1-for-1 is already fair (0.905); throwing in
    a pick shaves the gap to 0.967 and — before C1 — bought a strictly higher
    composite for an asset that carries no mutual-gain information at all.
    """
    killed = _pick_deck(rank_div_min_frac=0.0)
    k_bare = _find(killed, ["uA"], ["oB"])
    k_pad = _find(killed, ["PKu", "uA"], ["oB"])
    assert k_bare is not None and k_pad is not None
    # fixture validity: at the kill value the defect is live
    assert k_pad.composite_score > k_bare.composite_score, (
        "fixture no longer reproduces Defect A — the pick does not buy "
        f"composite at the kill value ({k_pad.composite_score} vs "
        f"{k_bare.composite_score})")

    on = _pick_deck()
    bare = _find(on, ["uA"], ["oB"])
    pad = _find(on, ["PKu", "uA"], ["oB"])
    assert bare is not None and pad is not None
    assert pad.composite_score <= bare.composite_score, (
        f"adding a pick to a fair package still raises composite: "
        f"{bare.composite_score} -> {pad.composite_score}")
    # the card still REPORTS the real full-package fairness — C1 changes the
    # ranking term, never the gate or what the user is shown
    assert pad.fairness_score == k_pad.fairness_score
    assert bare.fairness_score == k_bare.fairness_score


def test_bare_deal_outranks_its_padded_sibling_on_the_tie():
    """C1 makes a package and its zero-divergence-padded sibling score
    identically. The pre-existing v2 tie-break was `_tb` descending — the
    LATER-enumerated candidate — and 1-for-1s are enumerated first, so the
    bare deal lost every tie it now makes. On a tie, fewer pieces wins."""
    on = _pick_deck()
    bare = _find(on, ["uA"], ["oB"])
    pad = _find(on, ["PKu", "uA"], ["oB"])
    assert bare.composite_score == pad.composite_score, (
        "expected the C1 tie this test exists to break")
    assert on.index(bare) < on.index(pad), (
        "the padded sibling outranked the bare deal on an exact tie")


# ───────────────────────────────────────────────────────────────────────────
# C2 — prefer the minimal package among near-equivalents (_emit_best)
# ───────────────────────────────────────────────────────────────────────────

class _IdeaPlayer:
    def __init__(self, pid, position="RB"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = 25
        self.years_experience = 3
        self.search_rank = 50
        self.pick_value = None


def _upgrade_ideas(pin_elo, counterpart_elo, sweetener_elo, **cfg):
    """One pin, one counterpart just above the lateral band (so the Upgrade
    branch runs), one own-roster sweetener. _emit_best then chooses between
    [pin] -> [counterpart] and [pin, sweetener] -> [counterpart]."""
    elos = {"P": float(pin_elo), "S": float(sweetener_elo),
            "U": float(counterpart_elo)}
    players = {pid: _IdeaPlayer(pid) for pid in elos}
    opp = LeagueMember(user_id="opp", username="Opp", roster=["U"],
                       elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    _set_flags(**{"trade.asset_ideas": True})
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    # asset-ideas fixtures across this suite pin the pre-#214 'heavy' math
    with ts.stud_tax_override("heavy"):
        return svc.generate_asset_ideas(
            league_id="L1", user_id="user", asset_id="P", direction="give",
            user_roster=["P", "S"], seed_elo=dict(elos), raw_user_elo={},
            fairness_threshold=0.75)["upgrade"]


def test_minimal_package_wins_among_near_equivalent_gaps():
    """The bare 1-for-1 is already fair (0.789) and hands the user MORE
    consensus value than the sweetened version — but "closest to even" alone
    preferred the sweetened deal, so the sweetener bought the slot for free."""
    killed = _upgrade_ideas(1700, 1721, 1440, min_package_band=0.0)
    assert [i["give_player_ids"] for i in killed] == [["P", "S"]], (
        "fixture no longer reproduces the defect at the kill value")

    on = _upgrade_ideas(1700, 1721, 1440)
    assert [i["give_player_ids"] for i in on] == [["P"]], (
        "the sweetened variant still wins a near-equivalent gap")
    # and it is still a fair, strict-band deal — not a relaxed fallback
    assert on[0]["fairness"] >= 0.75
    assert on[0].get("relaxed") is None


def test_needed_sweetener_still_wins_outside_the_band():
    """The band is a tolerance, not a ban: when the bare deal's gap is
    genuinely further from even than the band allows, the sweetened variant
    still wins — otherwise the pin could never tier up at all."""
    on = _upgrade_ideas(1700, 1730, 1440)
    assert [i["give_player_ids"] for i in on] == [["P", "S"]]


def test_min_package_band_kill_value_restores_closest_gap_wins():
    """Kill value: min_package_band = 0 ⇒ the rank key is the original
    (relaxed, |difference|, give, receive) tuple, byte-identical to pre-C2."""
    for counterpart in (1721, 1725, 1730):
        killed = _upgrade_ideas(1700, counterpart, 1440, min_package_band=0.0)
        # closest-to-even wins regardless of piece count — the pre-C2 rule
        assert [i["give_player_ids"] for i in killed] == [["P", "S"]]


# ───────────────────────────────────────────────────────────────────────────
# C3 — widened pick_swap_ok: matched pick pairs are stripped, not ignored
# ───────────────────────────────────────────────────────────────────────────

_C3_SEEDS = {
    # two same-round picks a year apart in name but the same price — the
    # "random 1st swap" shape the tester filed
    "PK_A": 900.0, "PK_B": 890.0,
    # a second matched pair
    "PK_C": 400.0, "PK_D": 396.0,
    # consolidation partners: two lesser picks for one clearly better one
    "PK_LO1": 420.0, "PK_LO2": 400.0, "PK_HI": 900.0,
    "W1": 1500.0, "W2": 1400.0,
}


def _c3_players():
    players = {pid: _Pick(pid) for pid in _C3_SEEDS if pid.startswith("PK")}
    players["W1"] = _Player("W1", "WR")
    players["W2"] = _Player("W2", "RB")
    return players


def _c3_sv(pid):
    return _C3_SEEDS[pid]


def test_matched_pick_pair_inside_a_package_no_longer_rides_along_free():
    """The gate now judges the trade's REAL content. A matched 1st-for-1st
    contributes nothing in either direction, so it is stripped before the
    ruling — and when stripping empties a side, the pick swap WAS the trade."""
    players = _c3_players()
    ok = lambda g, r: ts.pick_swap_ok(g, r, players, _c3_sv)

    # give a player AND a matched pick, get only that pick back: once the
    # matched pair is stripped the user is shipping W1 for nothing
    assert not ok(["PK_A", "W1"], ["PK_B"])
    # both sides pure picks, pairwise matched — churn wearing a package
    assert not ok(["PK_A", "PK_C"], ["PK_B", "PK_D"])
    # strip one matched pair and the remainder is the banned 1-for-1 shape
    assert not ok(["PK_A", "PK_C"], ["PK_B", "PK_LO1"])

    # real content on both sides survives the strip
    assert ok(["PK_A", "W1"], ["PK_B", "W2"])
    assert ok(["PK_A", "W1"], ["W2"])


def test_c3_preserves_the_documented_legitimate_pick_shapes():
    """The narrow gate's documented exemptions still hold — C3 must not turn
    into a blanket ban on picks."""
    players = _c3_players()
    ok = lambda g, r: ts.pick_swap_ok(g, r, players, _c3_sv)

    # sweetener / headline compensation: only one side holds picks, so
    # nothing pairs and nothing strips
    assert ok(["W1"], ["PK_A", "W2"])
    assert ok(["PK_A", "W1"], ["W2"])
    assert ok(["PK_A"], ["W1"])
    assert ok(["W1"], ["PK_A"])
    # CONSOLIDATION: 2 lesser picks for 1 better. Pairing is best-against-
    # best, so PK_HI faces PK_LO1 — outside the match band — nothing strips
    # and the shape survives, exactly as documented.
    assert ok(["PK_LO1", "PK_LO2"], ["PK_HI"])
    # players only — untouched
    assert ok(["W1"], ["W2"])
    # the original 1-for-1 ban is intact
    assert not ok(["PK_A"], ["PK_B"])


def test_strip_pairs_best_against_best():
    """Deterministic pairing, and the reason consolidation survives."""
    players = _c3_players()
    g, r = ts.strip_matched_pick_pairs(
        ["PK_LO1", "PK_LO2"], ["PK_HI"], players, _c3_sv, 0.85)
    assert (g, r) == (["PK_LO1", "PK_LO2"], ["PK_HI"])
    g, r = ts.strip_matched_pick_pairs(
        ["PK_A", "PK_C", "W1"], ["PK_B", "W2"], players, _c3_sv, 0.85)
    assert (g, r) == (["PK_C", "W1"], ["W2"])


def test_pick_pair_strip_kill_value_restores_the_narrow_gate():
    """Kill value: pick_pair_strip_frac = 0 ⇒ only the literal 1-for-1
    both-sides-pick shape is banned, byte-identical to pre-C3. A caller that
    passes no seed_value gets the same narrow behaviour at any knob value."""
    players = _c3_players()
    ts._cfg["pick_pair_strip_frac"] = 0.0
    assert ts.pick_swap_ok(["PK_A", "W1"], ["PK_B"], players, _c3_sv)
    assert ts.pick_swap_ok(["PK_A", "PK_C"], ["PK_B", "PK_D"], players, _c3_sv)
    assert not ts.pick_swap_ok(["PK_A"], ["PK_B"], players, _c3_sv)

    ts._cfg["pick_pair_strip_frac"] = 0.85
    # no seed_value (e.g. the dark trade_gen.v2 caller) ⇒ pre-C3 behaviour
    assert ts.pick_swap_ok(["PK_A", "W1"], ["PK_B"], players)
    assert not ts.pick_swap_ok(["PK_A"], ["PK_B"], players)


def _wiring_fixture():
    """Two boarded sides with one divergent pair and a pick each, so every
    generator actually reaches the pick gate."""
    pos = {"uA": "WR", "oB": "WR", **_bodies("u"), **_bodies("o")}
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    players["PKu"] = _Pick("PKu")
    players["PKo"] = _Pick("PKo")
    seed = {pid: 1400.0 for pid in pos}
    seed.update({"uA": 1600.0, "oB": 1620.0, "PKu": 1450.0, "PKo": 1450.0})
    user_elo, opp_elo = dict(seed), dict(seed)
    user_elo["uA"], opp_elo["uA"] = 1480.0, 1720.0
    user_elo["oB"], opp_elo["oB"] = 1740.0, 1500.0
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=["oB"] + list(_bodies("o")) + ["PKo"],
                       elo_ratings=opp_elo, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, user_elo, ["uA"] + list(_bodies("u")) + ["PKu"], seed


@pytest.mark.parametrize("v3", [False, True])
def test_pick_gate_receives_the_consensus_value_fn_on_every_path(monkeypatch, v3):
    """C3 is inert without a seed_value — prove the v1 generators actually
    thread one in, on both the v2 pair path and the v3 optimizer."""
    seen = []

    def _spy(give_ids, recv_ids, players, seed_value=None):
        seen.append(seed_value)
        return True

    monkeypatch.setattr(ts, "pick_swap_ok", _spy)
    import backend.trade_optimizer as topt
    monkeypatch.setattr(topt, "pick_swap_ok", _spy)

    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3})
    ts._cfg.update(_ORTHOGONAL_GATES_OPEN)
    svc, ue, ur, seed = _wiring_fixture()
    svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                        league_id="L1", seed_elo=seed,
                        fairness_threshold=0.6, max_per_opponent=20)
    assert seen, "the pick gate was never reached — fixture is inert"
    assert all(callable(sv) for sv in seen), (
        "a generator still calls pick_swap_ok without a consensus value fn, "
        "so C3 silently degrades to the pre-C3 narrow gate there")


# ───────────────────────────────────────────────────────────────────────────
# C4 — headliner diversity at deck assembly (Defect B)
# ───────────────────────────────────────────────────────────────────────────

def _flood_fixture():
    """Reproduces Defect B: ONE asset anchors package after package, and with
    exact-key dedup as the only filter every one of them survives.

    `hub` is the flood source — the user's own highest-consensus asset, which
    all three opponents value above consensus. He therefore headlines a give
    side against EVERY counterparty and is the centerpiece of every card he
    appears in, so the flooding spans the whole deck rather than one pair's
    enumeration. That is the case a per-opponent cap would miss and a
    deck-assembly cap catches: uncapped he owns 21 of 36 cards across three
    counterparties, and a per-opponent cap of 2 would still leave six.
    """
    pos = dict(_bodies("u"))
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    seed = {pid: 1500.0 for pid in pos}
    user_elo = {pid: 1500.0 for pid in pos}
    players["hub"] = _Player("hub", "WR")
    seed["hub"] = 1700.0                     # highest consensus ⇒ centerpiece
    user_elo["hub"] = 1600.0                 # the user is lukewarm …
    members = []
    for n in (1, 2, 3):
        star, opp_bodies = f"star{n}", _bodies(f"o{n}")
        for pid, p in opp_bodies.items():
            players[pid] = _Player(pid, p)
            seed[pid] = 1500.0
            user_elo[pid] = 1500.0
        players[star] = _Player(star, "WR")
        seed[star] = 1620.0
        user_elo[star] = 1750.0
        opp_elo = {pid: 1500.0 for pid in list(opp_bodies) + list(pos)}
        opp_elo["hub"] = 1800.0              # … every opponent is not
        opp_elo[star] = 1560.0
        members.append(LeagueMember(
            user_id=f"opp{n}", username=f"opp{n}",
            roster=[star] + list(opp_bodies), elo_ratings=opp_elo,
            has_rankings=True))
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=members))
    return svc, user_elo, ["hub"] + list(pos), seed


def _flood_deck(**cfg):
    _set_flags(**{"trade_engine.v2": True})
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    # C4b off unless a case asks for it: every card in this fixture gives
    # `hub`, so the give-side cap would bind first and the C4 cases below
    # could not tell which cap trimmed the deck. C4b has its own fixture.
    ts._cfg["deck_give_headliner_cap"] = 0.0
    ts._cfg.update(cfg)
    svc, ue, ur, seed = _flood_fixture()
    return svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                               league_id="L1", seed_elo=seed,
                               fairness_threshold=0.6, max_per_opponent=12)


def _headliner_counts(cards, seed):
    counts = {}
    for c in cards:
        head = ts.deck_centerpiece(c.give_player_ids, c.receive_player_ids,
                                   seed)
        counts[head] = counts.get(head, 0) + 1
    return counts


def test_headliner_cap_bounds_a_flooded_deck():
    """Defect B, pinned. Uncapped, one asset owns most of the deck; capped, no
    centerpiece exceeds deck_headliner_cap."""
    _, _, _, seed = _flood_fixture()

    uncapped = _flood_deck(deck_headliner_cap=0.0)
    before = _headliner_counts(uncapped, seed)
    worst_before = max(before.values())
    assert worst_before > 2, (
        "fixture no longer floods — Defect B repro is invalid "
        f"(worst headliner appears {worst_before}x in {len(uncapped)} cards)")

    capped = _flood_deck()
    after = _headliner_counts(capped, seed)
    assert max(after.values()) <= 2, (
        f"a centerpiece still exceeds the cap: {after}")
    # the cap trims, it does not empty the deck, and it only ever REMOVES —
    # every surviving card was already in the uncapped deck
    assert capped, "the cap emptied the deck"
    assert [c.composite_score for c in capped] == sorted(
        (c.composite_score for c in capped), reverse=True)
    _key = lambda c: (tuple(c.give_player_ids), tuple(c.receive_player_ids))
    assert {_key(c) for c in capped} <= {_key(c) for c in uncapped}
    # and it keeps each headliner's BEST cards (applied after the sort)
    for head, n in after.items():
        best = [c.composite_score for c in uncapped
                if ts.deck_centerpiece(c.give_player_ids,
                                       c.receive_player_ids, seed) == head]
        kept = [c.composite_score for c in capped
                if ts.deck_centerpiece(c.give_player_ids,
                                       c.receive_player_ids, seed) == head]
        assert kept == sorted(best, reverse=True)[:n]


def test_headliner_cap_constrains_the_final_served_set_not_one_pairing():
    """The cap must bind on the DECK, not on one opponent's enumeration:
    `hub` headlines cards against all three counterparties, so a per-opponent
    cap of 2 would still serve six hub cards."""
    _, _, _, seed = _flood_fixture()
    uncapped = _flood_deck(deck_headliner_cap=0.0)
    hub_opponents = {c.target_user_id for c in uncapped
                     if ts.deck_centerpiece(c.give_player_ids,
                                            c.receive_player_ids,
                                            seed) == "hub"}
    assert len(hub_opponents) > 1, (
        "fixture no longer floods ACROSS opponents — a per-opponent cap "
        "would be indistinguishable here")
    capped = _flood_deck()
    assert _headliner_counts(capped, seed).get("hub", 0) <= 2


def test_deck_headliner_cap_kill_value_leaves_every_card():
    """Kill value: deck_headliner_cap = 0 ⇒ no card is dropped and the order
    is the plain composite sort, byte-identical to pre-C4."""
    uncapped = _flood_deck(deck_headliner_cap=0.0)
    keys = [(tuple(c.give_player_ids), tuple(c.receive_player_ids))
            for c in uncapped]
    assert len(keys) == len(uncapped)
    assert [c.composite_score for c in uncapped] == sorted(
        (c.composite_score for c in uncapped), reverse=True)
    # and the cap really was the only thing removing cards
    assert len(uncapped) > len(_flood_deck())


def test_deck_centerpiece_is_the_impression_metric_definition():
    """The cap ranks on the SAME definition deck_impressions.centerpiece_id
    is written with — server._fatigue_centerpiece delegates here, so the two
    cannot drift."""
    import backend.server as server
    seed = {"a": 1500.0, "b": 1700.0, "c": 1700.0}
    give, recv = ["a"], ["b", "c"]
    assert ts.deck_centerpiece(give, recv, seed) == "c"     # id tie-break
    assert server._fatigue_centerpiece(give, recv, seed) == \
        ts.deck_centerpiece(give, recv, seed)
    assert ts.deck_centerpiece([], [], seed) is None


# ───────────────────────────────────────────────────────────────────────────
# C4b — GIVE-side headliner cap (2026-08-19,
#       docs/plans/deck-give-headliner-cap/scope.md)
#
# The measured defect C4 could not see. `deck_centerpiece` maxes over give AND
# receive and defaults unknown assets to 1500, so on a "give one player, get
# one draft pick" card the PICK is the centerpiece — and every such card offers
# a DIFFERENT pick slot, so every card gets a unique centerpiece and a cap of 2
# never fires. Live deck 2740a7fc: 22 cards, 20 distinct centerpieces, C4 kills
# 0, and three players supplied 17 of the 22 GIVE sides (6 / 6 / 5).
# ───────────────────────────────────────────────────────────────────────────

def _c4b_players():
    """Two players + a family of owned-pick pseudo-assets, all distinct ids."""
    players = {"adams": _Player("adams", "WR"), "mayfield": _Player("mayfield", "QB")}
    for n in range(1, 8):
        players[f"L_2028_1_{n}"] = _Pick(f"L_2028_1_{n}", pick_value=60.0)
    return players


def _c4b_seed():
    """D-079 pricing, in miniature: every 1st sits ABOVE the player being sent,
    which is what hands the centerpiece to the pick."""
    seed = {"adams": 1600.0, "mayfield": 1580.0}
    seed.update({f"L_2028_1_{n}": 1650.0 + n for n in range(1, 8)})
    return seed


def _c4b_cards():
    """Six 'give one player for one pick' cards — the live shape, best-first."""
    cards = []
    for i, n in enumerate(range(1, 7)):
        cards.append(ts.TradeCard(
            trade_id=f"t{n}", league_id="L1", proposing_user_id="u1",
            target_user_id="u2", target_username="opp",
            give_player_ids=["adams"], receive_player_ids=[f"L_2028_1_{n}"],
            mismatch_score=50.0, fairness_score=0.9,
            composite_score=100.0 - i))
    return cards


def _c4b_svc(**cfg):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    svc = TradeService(players=_c4b_players())
    svc._job_seed_elo = _c4b_seed()
    return svc


def test_centerpiece_cap_is_blind_to_the_measured_flood():
    """The root cause, pinned. Six cards that all ask for the same player are
    six DISTINCT centerpieces, so C4 at its default of 2 removes nothing."""
    seed = _c4b_seed()
    heads = {ts.deck_centerpiece(c.give_player_ids, c.receive_player_ids, seed)
             for c in _c4b_cards()}
    assert len(heads) == 6, "fixture no longer reproduces the unique-key flood"
    assert all(h.startswith("L_2028_1_") for h in heads), \
        "the PICK must win the centerpiece — that is the defect"

    svc = _c4b_svc(deck_give_headliner_cap=0.0)
    assert len(svc._dedup_and_sort(_c4b_cards())) == 6, \
        "C4 alone should not trim this deck (that is why C4b exists)"


def test_give_headliner_cap_bounds_the_flood_c4_cannot():
    """C4b at its default keeps the best `cap` cards per give headliner and
    drops the rest."""
    svc = _c4b_svc()
    kept = svc._dedup_and_sort(_c4b_cards())
    assert len(kept) == 3
    assert [c.trade_id for c in kept] == ["t1", "t2", "t3"], \
        "the cap must keep each headliner's BEST cards (applied after the sort)"
    assert [c.composite_score for c in kept] == sorted(
        (c.composite_score for c in kept), reverse=True)


def test_give_headliner_cap_is_per_headliner_not_per_deck():
    """A second give-side player gets its own allowance — the cap bounds
    repetition, it does not bound deck size."""
    cards = _c4b_cards()
    for i, n in enumerate(range(1, 5)):
        cards.append(ts.TradeCard(
            trade_id=f"m{n}", league_id="L1", proposing_user_id="u1",
            target_user_id="u3", target_username="opp3",
            give_player_ids=["mayfield"], receive_player_ids=[f"L_2028_1_{n}"],
            mismatch_score=50.0, fairness_score=0.9,
            composite_score=50.0 - i))
    kept = _c4b_svc()._dedup_and_sort(cards)
    counts = {}
    for c in kept:
        counts[c.give_player_ids[0]] = counts.get(c.give_player_ids[0], 0) + 1
    assert counts == {"adams": 3, "mayfield": 3}


def test_give_headliner_cap_leaves_short_and_never_backfills():
    """Leave-short, like compose_group's lane quotas: the dropped slots stay
    empty. Backfilling would put the same headliner straight back."""
    kept = _c4b_svc()._dedup_and_sort(_c4b_cards())
    assert len(kept) == 3, "6 cards in, 3 out — the deck is allowed to shrink"
    assert {c.trade_id for c in kept} <= {f"t{n}" for n in range(1, 7)}, \
        "the cap only ever REMOVES; it must not invent or reorder cards"


def test_give_headliner_cap_kill_value_leaves_every_card():
    """Kill value: 0 ⇒ every card survives in plain composite order,
    byte-identical to pre-C4b."""
    cards = _c4b_cards()
    kept = _c4b_svc(deck_give_headliner_cap=0.0)._dedup_and_sort(cards)
    assert [c.trade_id for c in kept] == [c.trade_id for c in cards]


def test_give_headliner_cap_is_inert_without_a_seed_map():
    """No consensus values ⇒ every asset ties at 1500 and 'headliner' would
    degenerate to 'largest player id'. Same inertness rule as C4."""
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    svc = TradeService(players=_c4b_players())
    svc._job_seed_elo = {}
    assert len(svc._dedup_and_sort(_c4b_cards())) == 6


def test_give_headliner_prefers_the_player_over_the_pick():
    """The definition that fixes the root cause: on a mixed give side the
    PLAYER headlines even though D-079 prices the pick higher."""
    seed = _c4b_seed()
    players = _c4b_players()
    assert seed["L_2028_1_1"] > seed["adams"]          # the pick is worth more
    assert ts.deck_give_headliner(["adams", "L_2028_1_1"], seed, players) == "adams"
    # all-pick give side: the pick may headline, there is nothing else
    assert ts.deck_give_headliner(["L_2028_1_1", "L_2028_1_2"], seed,
                                  players) == "L_2028_1_2"
    # no players map ⇒ plain highest-Elo, id tie-break
    assert ts.deck_give_headliner(["adams", "L_2028_1_1"], seed, None) == "L_2028_1_1"
    assert ts.deck_give_headliner([], seed, players) is None


def test_give_headliner_ignores_the_receive_side():
    """The whole point: what the user is ASKED TO SEND, never what comes back.
    A monster on the receive side must not become the key."""
    seed = dict(_c4b_seed())
    seed["monster"] = 2000.0
    assert ts.deck_give_headliner(["adams"], seed, _c4b_players()) == "adams"
    assert ts.deck_centerpiece(["adams"], ["monster"], seed) == "monster"


def test_deck_centerpiece_definition_is_untouched_by_c4b():
    """C4b must NOT re-key `deck_centerpiece`: that is the shared definition
    behind deck_impressions.centerpiece_id AND the decline-time fatigue key,
    so changing it would silently re-key fatigue matching against every row
    already written."""
    import backend.server as server
    seed = {"a": 1500.0, "b": 1700.0}
    give, recv = ["a"], ["b"]
    assert ts.deck_centerpiece(give, recv, seed) == "b"
    assert server._fatigue_centerpiece(give, recv, seed) == "b"
    assert ts.deck_give_headliner(give, seed, None) == "a"


def test_both_generation_paths_apply_the_give_cap():
    """Bake-off consistency. The v1/v3 engine applies C4b in `_dedup_and_sort`;
    the `trade_gen.v2` branch of `_generate_trades_impl` returns BEFORE that
    call, and `bakeoff_runner.gen_v2_cards` (arm C) bypasses the method
    entirely. All three must call the one helper, or the bake-off compares
    arms under different deck-assembly rules."""
    import inspect
    import backend.bakeoff_runner as br
    impl = inspect.getsource(ts.TradeService._generate_trades_impl)
    v2_branch = impl.split("if FLAGS.trade_gen_v2:", 1)[1].split("return cards", 1)[0]
    assert "cap_give_headliners" in v2_branch, \
        "the trade_gen.v2 serving branch lost its give-side cap"
    assert "cap_give_headliners" in inspect.getsource(
        ts.TradeService._dedup_and_sort)
    assert "cap_give_headliners" in inspect.getsource(br.gen_v2_cards), \
        "arm C would flood one give headliner while arms A/B could not"


def test_arm_a_disables_the_give_cap():
    """Arm A is the pre-wave engine, so a knob that post-dates the reference
    sha must be pinned to its kill value in MODEL_A_PROFILE."""
    from backend.bakeoff_profiles import MODEL_A_PROFILE
    assert MODEL_A_PROFILE["deck_give_headliner_cap"] == 0.0


# ───────────────────────────────────────────────────────────────────────────
# C5 — confidence damping of the ranking mismatch term
# ───────────────────────────────────────────────────────────────────────────

def test_mismatch_damp_shrinks_with_thin_comparison_counts():
    """_value_uncertainty already knew a thinly-compared player's value is a
    guess; it just never reached the RANKING. unc = range_base/sqrt(1+n), so
    the damp is strongest at n=0 and approaches 1 as n grows."""
    seed = {"A": 1000.0, "B": 1000.0}
    sv = lambda p: seed[p]
    ids = ["A", "B"]
    never = ts.mismatch_damp(ids, sv, {"A": 0, "B": 0})
    thin = ts.mismatch_damp(ids, sv, {"A": 3, "B": 3})
    heavy = ts.mismatch_damp(ids, sv, {"A": 200, "B": 200})
    assert 0.0 < never < thin < heavy < 1.0
    # exact shape at n=0: 1 − damp × range_base
    assert never == pytest.approx(1.0 - ts._c("range_base"))
    # value-weighted: a thin player carrying most of the package's value
    # damps the package more than a thin bench piece does
    seed["A"] = 5000.0
    thin_star = ts.mismatch_damp(ids, sv, {"A": 0, "B": 200})
    thin_bench = ts.mismatch_damp(ids, sv, {"A": 200, "B": 0})
    assert thin_star < thin_bench


def test_mismatch_damp_kill_value_and_no_confidence_are_both_no_ops():
    """Kill value: mismatch_confidence_damp = 0 ⇒ 1.0. And confidence=None
    (no comparison counts available at all) is a no-op at ANY knob value —
    no information is not the same as low confidence."""
    seed = {"A": 1000.0}
    sv = lambda p: seed[p]
    assert ts.mismatch_damp(["A"], sv, None) == 1.0
    ts._cfg["mismatch_confidence_damp"] = 0.0
    assert ts.mismatch_damp(["A"], sv, {"A": 0}) == 1.0


def _damp_deck(confidence, **cfg):
    _set_flags(**{"trade_engine.v2": True})
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(_ORTHOGONAL_GATES_OPEN)
    ts._cfg.update(cfg)
    svc, ue, ur, seed = _pick_fixture()
    return svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                               league_id="L1", seed_elo=seed,
                               fairness_threshold=0.6, max_per_opponent=400,
                               confidence=confidence)


def test_thinly_compared_divergence_is_discounted_in_the_ranking():
    """Same fixture, same confidence, damp on vs off: the card built on a
    barely-ranked pair loses composite. The surplus GATES are untouched — the
    card still surfaces, it just stops outranking well-sampled disagreement.
    """
    thin = {"uA": 1, "oB": 1}
    undamped = _find(_damp_deck(thin, mismatch_confidence_damp=0.0),
                     ["uA"], ["oB"])
    damped = _find(_damp_deck(thin), ["uA"], ["oB"])
    assert undamped is not None and damped is not None, (
        "damping must not gate a card out — it only reorders")
    assert damped.composite_score < undamped.composite_score

    # a well-sampled pair keeps far more of its mismatch
    heavy = {"uA": 400, "oB": 400}
    heavy_damped = _find(_damp_deck(heavy), ["uA"], ["oB"])
    heavy_undamped = _find(_damp_deck(heavy, mismatch_confidence_damp=0.0),
                           ["uA"], ["oB"])
    thin_loss = undamped.composite_score - damped.composite_score
    heavy_loss = heavy_undamped.composite_score - heavy_damped.composite_score
    assert heavy_loss < thin_loss, (
        f"thin package lost {thin_loss}, well-sampled lost {heavy_loss} — "
        "damping is not tracking comparison count")
