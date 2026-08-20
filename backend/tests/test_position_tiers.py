"""#366 — position-relative tier bands + the RB Handcuff tag.

Scope block: docs/feedback/items/366-tier-ladder/scope.md

THE ONE TEST THAT MATTERS MOST IS THE FLAG-OFF ONE.
`analyze_roster_strengths` does not only feed the Team Review depth beat — it
produces `position_needs` / `position_surplus`, which trade_gen_v2 (:930, :980)
and trade_service (:3413, :3440, :4096, :4172, :4259) consume on every deck.
Changing the bins changes every deck for every user. So the contract this file
exists to hold is: with `trade.position_tiers` OFF, this function returns a dict
byte-identical to the one it returned before #366 — same keys, same nesting,
same counts — and with `trade.rb_handcuff` OFF, no `depth_chart_*` attribute is
read at all.
"""
from dataclasses import dataclass

import pytest

from backend import trade_service as ts
from backend.trade_service import analyze_roster_strengths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class _P:
    id: str
    position: str
    search_rank: int = 100
    name: str = "X"
    pick_value: float | None = None
    depth_chart_position: str | None = None
    depth_chart_order: int | None = None


CORE = ("QB", "RB", "WR", "TE")


def _pool(n_per_pos: int = 80) -> dict:
    """A pool deep enough to clear `_POS_TIER_MIN_POOL` at every position.

    `search_rank` is interleaved across positions so no two players share one,
    and player `f"{pos}{i}"` lands at positional rank `i` (1-based) by
    construction — every band assertion below reads directly off the id.
    """
    players: dict[str, _P] = {}
    for slot, pos in enumerate(CORE):
        for i in range(1, n_per_pos + 1):
            pid = f"{pos}{i}"
            players[pid] = _P(pid, pos, search_rank=(i - 1) * len(CORE) + slot + 1)
    return players


def _flags(*on: str):
    """Patch the flag lookup `analyze_roster_strengths` performs at call time.

    The function imports `is_enabled` from `.feature_flags` INSIDE its body, so
    patching the module attribute is what takes effect (the `test_pick_horizon`
    idiom). Patching a name bound at import time would silently do nothing —
    which would make every assertion here vacuous.
    """
    def _apply(monkeypatch):
        monkeypatch.setattr("backend.feature_flags.is_enabled",
                            lambda k: k in on)
    return _apply


@pytest.fixture
def off(monkeypatch):
    _flags()(monkeypatch)


@pytest.fixture
def tiers_on(monkeypatch):
    _flags("trade.position_tiers")(monkeypatch)


@pytest.fixture
def handcuff_on(monkeypatch):
    _flags("trade.rb_handcuff")(monkeypatch)


@pytest.fixture
def both_on(monkeypatch):
    _flags("trade.position_tiers", "trade.rb_handcuff")(monkeypatch)


# ---------------------------------------------------------------------------
# 1. Flag OFF — byte-identity with pre-#366
# ---------------------------------------------------------------------------

def test_flag_off_profile_is_byte_identical_to_legacy(off):
    """The frozen pre-#366 shape, written out in full rather than derived.

    A literal is the point: a computed expectation would drift with the code it
    is meant to pin. These counts follow the ABSOLUTE cuts — elite >= 4000,
    starter >= 1500, bench >= 500 on `dynasty_value`, i.e. overall search_rank
    <= 73 / <= 151 / <= 238.
    """
    players = {
        "q1": _P("q1", "QB", 5),     # value ~9512  -> elite
        "r1": _P("r1", "RB", 100),   # value ~2851  -> starter
        "w1": _P("w1", "WR", 200),   # value  ~806  -> bench
        "t1": _P("t1", "TE", 400),   # value   ~65  -> uncounted
    }
    assert analyze_roster_strengths(["q1", "r1", "w1", "t1"], players) == {
        "tier_depth": {
            "QB": {"elite": 1, "starter": 0, "bench": 0},
            "RB": {"elite": 0, "starter": 1, "bench": 0},
            "WR": {"elite": 0, "starter": 0, "bench": 1},
            "TE": {"elite": 0, "starter": 0, "bench": 0},
        },
        "position_needs":   ["RB", "WR", "TE"],
        "position_surplus": [],
    }


def test_flag_off_adds_no_keys_anywhere(off):
    """Not just "the values are right" — the KEY SET is frozen too, at both
    levels. An extra key is a payload change and a client-parse risk."""
    players = _pool()
    profile = analyze_roster_strengths(list(players)[:40], players)
    assert set(profile) == {"tier_depth", "position_needs", "position_surplus"}
    for pos, bins in profile["tier_depth"].items():
        assert set(bins) == {"elite", "starter", "bench"}, pos


def test_flag_off_bins_follow_the_absolute_cuts_exactly(off):
    """The engine-facing invariant, checked against `_bin_player` itself rather
    than against a second copy of the thresholds."""
    players = _pool()
    roster = list(players)
    profile = analyze_roster_strengths(roster, players)
    expected = {pos: {"elite": 0, "starter": 0, "bench": 0} for pos in CORE}
    for pid in roster:
        p = players[pid]
        b = ts._bin_player(ts.dynasty_value(p))
        if b:
            expected[p.position][b] += 1
    assert profile["tier_depth"] == expected


def test_flag_off_never_touches_the_depth_chart(off):
    """`trade.rb_handcuff` OFF must mean the attribute is never READ, not merely
    that the result is discarded. A player that detonates on access proves it."""
    class _Landmine:
        """Not a dataclass — a plain object, so the exploding attributes stay
        read-only properties instead of being overwritten by a generated
        __init__. `getattr(obj, name, default)` swallows AttributeError, so
        these raise RuntimeError: only a genuine non-read passes."""
        id = "r1"
        position = "RB"
        search_rank = 30
        name = "X"
        pick_value = None

        @property
        def depth_chart_order(self):          # pragma: no cover - must not run
            raise RuntimeError("depth_chart_order was read with the flag OFF")

        @property
        def depth_chart_position(self):       # pragma: no cover - must not run
            raise RuntimeError("depth_chart_position was read with the flag OFF")

    players = {"r1": _Landmine()}
    profile = analyze_roster_strengths(["r1"], players)
    assert "handcuff_rb" not in profile


# ---------------------------------------------------------------------------
# 2. Position-relative bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pos,elite_cut,starter_cut,repl_cut", [
    ("QB", 6, 18, 32),
    ("TE", 6, 18, 32),
    ("RB", 12, 36, 60),
    ("WR", 12, 36, 60),
])
def test_relative_band_boundaries(tiers_on, pos, elite_cut, starter_cut, repl_cut):
    """Every boundary, from both sides. Off-by-one here silently re-labels a
    whole tier of players, which is the failure the report is about."""
    players = _pool()

    def bin_of(rank: int) -> str | None:
        prof = analyze_roster_strengths([f"{pos}{rank}"], players)
        bins = prof["tier_depth"][pos]
        for name in ("elite", "starter", "bench"):
            if bins[name] == 1:
                return name
        return None

    assert bin_of(elite_cut) == "elite"
    assert bin_of(elite_cut + 1) == "starter"
    assert bin_of(starter_cut) == "starter"
    assert bin_of(starter_cut + 1) == "bench"
    assert bin_of(repl_cut) == "bench"
    assert bin_of(repl_cut + 1) is None


def test_relative_bands_make_elite_mean_one_thing(tiers_on):
    """THE REPORTED DEFECT, as an assertion.

    On the live pool the absolute cuts admit 33 elite RBs, 33 elite WRs, 17
    elite QBs and 7 elite TEs — one word, four meanings. Under positional
    bands, "elite" admits the same share of each position's starting demand
    everywhere: 6 at the one-starter positions, 12 at the two-starter ones.
    """
    players = _pool()
    profile = analyze_roster_strengths(list(players), players)
    elite = {pos: profile["tier_depth"][pos]["elite"] for pos in CORE}
    assert elite == {"QB": 6, "TE": 6, "RB": 12, "WR": 12}


def test_superflex_widens_qb_and_nothing_else(tiers_on):
    """Superflex starts two QBs, so QB scarcity should match RB/WR scarcity —
    and only QB should move."""
    players = _pool()
    roster = list(players)
    one_qb = analyze_roster_strengths(roster, players, "1qb_ppr")["tier_depth"]
    sf = analyze_roster_strengths(roster, players, "sf_tep")["tier_depth"]
    assert one_qb["QB"]["elite"] == 6
    assert sf["QB"]["elite"] == 12
    for pos in ("RB", "WR", "TE"):
        assert sf[pos] == one_qb[pos], pos


def test_replacement_is_an_alias_of_bench_not_a_fourth_bin(tiers_on):
    """`replacement` must equal `bench`, and `bench` must survive. Dropping
    `bench` would break every client older than this commit; making
    `replacement` a genuinely different count would break the partition."""
    players = _pool()
    profile = analyze_roster_strengths(list(players), players)
    for pos, bins in profile["tier_depth"].items():
        assert "bench" in bins, pos
        assert bins["replacement"] == bins["bench"], pos


def test_relative_and_absolute_actually_disagree(monkeypatch):
    """A guard that cannot tell the two paths apart proves nothing.

    This pins that the flag genuinely re-bins a real roster — without it, every
    band assertion above could be passing against the legacy path and nobody
    would know. Both calls use the SAME pool and the SAME roster; only the flag
    moves.
    """
    players = _pool()
    roster = [f"WR{i}" for i in range(1, 41)]

    _flags()(monkeypatch)
    absolute = analyze_roster_strengths(roster, players)["tier_depth"]["WR"]

    _flags("trade.position_tiers")(monkeypatch)
    relative = analyze_roster_strengths(roster, players)["tier_depth"]["WR"]

    assert {k: relative[k] for k in ("elite", "starter", "bench")} != absolute, (
        "the position_tiers flag produced the same bins as the legacy cuts — "
        "either the flag is not being read or the fixture cannot distinguish "
        "the two paths, and every band assertion in this file is vacuous"
    )


def test_unranked_players_sort_last(tiers_on):
    """No `search_rank` means unranked, not rank 1. A player who sorted first on
    missing data would be crowned elite by an absence."""
    players = _pool()
    players["ghost"] = _P("ghost", "WR", search_rank=None)  # type: ignore[arg-type]
    profile = analyze_roster_strengths(["ghost"], players)
    assert profile["tier_depth"]["WR"] == {
        "elite": 0, "starter": 0, "bench": 0, "replacement": 0}


# ---------------------------------------------------------------------------
# 3. The small-pool guard and `tier_basis`
# ---------------------------------------------------------------------------

def test_thin_pool_falls_back_to_absolute_cuts(tiers_on):
    """Positional rank over four players would crown all four. Below
    `_POS_TIER_MIN_POOL` the legacy cuts run instead — and say so."""
    players = {
        "q1": _P("q1", "QB", 5),
        "r1": _P("r1", "RB", 100),
        "w1": _P("w1", "WR", 200),
        "t1": _P("t1", "TE", 400),
    }
    profile = analyze_roster_strengths(list(players), players)
    assert profile["tier_basis"] == {p: "absolute" for p in CORE}
    assert profile["tier_depth"]["QB"]["elite"] == 1
    assert profile["tier_depth"]["RB"]["starter"] == 1
    assert profile["tier_depth"]["WR"]["bench"] == 1


def test_deep_pool_reports_position_relative(tiers_on):
    players = _pool()
    profile = analyze_roster_strengths(list(players)[:10], players)
    assert profile["tier_basis"] == {p: "position_relative" for p in CORE}


def test_tier_basis_is_per_position(tiers_on):
    """A pool deep at WR and thin everywhere else must band WR relatively and
    the rest absolutely — the guard is per position, not per call."""
    players = {f"WR{i}": _P(f"WR{i}", "WR", search_rank=i)
               for i in range(1, 81)}
    players["q1"] = _P("q1", "QB", 5)
    profile = analyze_roster_strengths(list(players), players)
    assert profile["tier_basis"]["WR"] == "position_relative"
    assert profile["tier_basis"]["QB"] == "absolute"
    # The QB was banded by the absolute cut, so he is still elite.
    assert profile["tier_depth"]["QB"]["elite"] == 1


def test_tier_basis_absent_when_flag_off(off):
    players = _pool()
    assert "tier_basis" not in analyze_roster_strengths(list(players)[:5], players)


def test_positional_rank_map_is_memoised(tiers_on):
    """Same pool object in, same map object out — the memo is what keeps the
    engine's 13-calls-per-deck loop from rebuilding a 2.7k-player map 13 times."""
    players = _pool()
    first = ts._positional_rank_map(players)
    assert ts._positional_rank_map(players) is first


# ---------------------------------------------------------------------------
# 4. Handcuff
# ---------------------------------------------------------------------------

def _rb(pid: str, order, dcp="RB", rank=50) -> _P:
    return _P(pid, "RB", search_rank=rank,
              depth_chart_position=dcp, depth_chart_order=order)


def test_handcuff_counts_the_rb2(handcuff_on):
    players = {
        "starter": _rb("starter", 1),
        "hc":      _rb("hc", 2),
        "third":   _rb("third", 3),
    }
    assert analyze_roster_strengths(list(players), players)["handcuff_rb"] == 1


@pytest.mark.parametrize("pid,order,dcp,position", [
    ("order1",   1,    "RB", "RB"),     # the starter is not his own handcuff
    ("order3",   3,    "RB", "RB"),     # third string is not the RB2
    ("null",     None, "RB", "RB"),     # off the depth chart entirely
    ("blank",    2,    None, "RB"),     # no depth-chart position
    ("mismatch", 2,    "WR", "RB"),     # order 2 at a DIFFERENT chart position
    ("notrb",    2,    "RB", "WR"),     # a WR can never be a handcuff
])
def test_handcuff_rejects_everything_that_is_not_an_rb2(
        handcuff_on, pid, order, dcp, position):
    p = _P(pid, position, search_rank=50,
           depth_chart_position=dcp, depth_chart_order=order)
    players = {pid: p}
    assert analyze_roster_strengths([pid], players)["handcuff_rb"] == 0


def test_handcuff_absent_when_flag_off(off):
    players = {"hc": _rb("hc", 2)}
    assert "handcuff_rb" not in analyze_roster_strengths(["hc"], players)


def test_handcuff_zero_is_present_not_absent(handcuff_on):
    """"We looked and you have none" and "we did not look" are different
    claims. Zero must be PRESENT so the card can say the first one."""
    players = {"starter": _rb("starter", 1)}
    profile = analyze_roster_strengths(["starter"], players)
    assert profile["handcuff_rb"] == 0
    assert "handcuff_rb" in profile


def test_handcuff_never_enters_tier_depth(handcuff_on):
    """`tier_depth[pos]` is a disjoint partition. The handcuff overlay must not
    add a key to it or inflate a count — an RB2 is ALSO elite/starter/bench, so
    counting him twice would make the bins stop summing to the roster."""
    players = {"hc": _rb("hc", 2)}
    profile = analyze_roster_strengths(["hc"], players)
    assert set(profile["tier_depth"]["RB"]) == {"elite", "starter", "bench"}
    assert sum(profile["tier_depth"]["RB"].values()) == 1


def test_handcuff_and_tiers_are_independent(monkeypatch):
    """Two kill switches, four states, no coupling: the tier flag must not
    summon `handcuff_rb`, and the handcuff flag must not summon `tier_basis`."""
    players = _pool()
    players["hc"] = _rb("hc", 2)
    roster = list(players)

    _flags()(monkeypatch)
    p = analyze_roster_strengths(roster, players)
    assert "handcuff_rb" not in p
    assert "tier_basis" not in p

    _flags("trade.position_tiers")(monkeypatch)
    p = analyze_roster_strengths(roster, players)
    assert "tier_basis" in p
    assert "handcuff_rb" not in p

    _flags("trade.rb_handcuff")(monkeypatch)
    p = analyze_roster_strengths(roster, players)
    assert "tier_basis" not in p
    assert p["handcuff_rb"] == 1

    _flags("trade.position_tiers", "trade.rb_handcuff")(monkeypatch)
    p = analyze_roster_strengths(roster, players)
    assert "tier_basis" in p
    assert p["handcuff_rb"] == 1


def test_needs_and_surplus_never_read_the_handcuff(both_on):
    """The engine consumes needs/surplus. The handcuff overlay must be inert to
    them, or a purely cosmetic label would reshape decks."""
    players = _pool()
    roster = [f"RB{i}" for i in range(1, 5)]
    baseline = analyze_roster_strengths(roster, players)
    for pid in roster:
        players[pid].depth_chart_position = "RB"
        players[pid].depth_chart_order = 2
    after = analyze_roster_strengths(roster, players)
    assert after["handcuff_rb"] == 4
    assert after["position_needs"] == baseline["position_needs"]
    assert after["position_surplus"] == baseline["position_surplus"]
    assert after["tier_depth"] == baseline["tier_depth"]
