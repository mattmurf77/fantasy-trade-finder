"""D-161 — the round-1 YoY floor: future firsts never price below the
current class's first, under `market_slots`.

WHY THIS EXISTS. D-079 (2026-08-19) is an operator ruling — *"firsts should
hold similar value YOY. Other picks can degrade the longer away they are"* —
and it shipped as `pick_year_decay_r1 = 1.0` on the tier ladder. Two days
later D-144/D-146 made `market_slots` the only price an owned pick can get,
and the market curve carries DynastyProcess's OWN year discount inside DP's
published window. The ruling therefore stopped reaching the SERVED price:
measured on prod 2026-08-24, a 2027 1st priced 1,751 and a 2028 1st 1,459
against a current-year mid of 2,184.6. A tester found it (MangoPatti, via the
operator: A.J. Brown + depth asked for Isaiah Likely + three future firsts).
Operator re-ruling, 2026-08-24: *"The ideal solution is the D-079 ruling."*

Spec: docs/plans/pick-yoy-floor/plan.md §2-§3.

WHAT IS PINNED HERE, in the order the plan lists it:

  1. default 1.0 — a future r1 prices at the current class's r1, both formats
  2. knob 0 — byte-identical to the raw market curve, AND no second market
     lookup happens at all (the short-circuit, not just the number)
  3. fraction 0.85 — `max(market, 0.85 × current mid)`, and >1 clamps to 1
  4. rounds 2-4 unmoved at every knob setting ("other picks can degrade")
  5. step 1 (a resolved per-slot price) and `tier_ladder` unmoved
  6. no market price ⇒ the stored ladder, no floor, no exception
  7. the injector seam (`server._priced_pick_value`, slot None) — end to end
  8. the anchor season is read out of DP's own map, slotted seasons first

EVERY TEST OWNS ITS MARKET DATA. `data_loader.load_pick_slot_values` is
monkeypatched with a hand-built label→Elo map, so nothing here touches the
network, the 24 h TTL cache, or the checked-in DP snapshot — and the "current
season" the floor anchors on is whatever the fixture says it is, because
`pick_values.market_anchor_season` reads it out of that same map. Every
expectation is DERIVED from the map (via `market_pick_pool_value` /
`elo_to_value`), never a bare literal, so a re-tune of the value scale moves
the fixture and the expectation together.

D-056 sabotage ledger — every test below was proven RED on its named
sabotage and green again on restore from a byte copy (`cp` snapshot, NOT
`git checkout --`: this branch is uncommitted), with
`find backend -name __pycache__ -exec rm -rf {} +` after each restore
(G-060: a same-second, same-size restore keeps the stale `.pyc` and the test
stays red for the wrong reason). One sabotage per test, the exact edited line
quoted; all in `backend/pick_values.py` unless noted:

  S1  test_default_floor_lifts_a_future_first_to_the_current_class
      _r1_yoy_floored:  `return max(market, round(rate * current, 1))`
                     -> `return market`
      (the clamp computes the floor and then throws it away)

  S2  test_knob_zero_is_byte_identical_to_the_raw_market
      _r1_yoy_floored:  `if rate <= 0.0:`  ->  `if rate < 0.0:`
      (0 stops being the disable value. NOTE the returned NUMBER is unchanged
      — `max(market, 0.0)` is `market` — so only this test's loader-call
      assertion catches it. That assertion is the whole reason it exists.)

  S3  test_a_fraction_dials_the_floor_and_above_one_clamps
      _r1_yoy_floored:  `round(rate * current, 1)`  ->  `round(current, 1)`
      (the knob stops being a fraction and becomes a boolean)

  S4  test_rounds_two_to_four_are_unmoved_at_every_setting
      _r1_yoy_floored:  `if round_ != 1:`  ->  `if round_ > 4:`
      (the floor spreads onto the rounds the ruling said may degrade)

  S5  test_step_one_slot_price_and_tier_ladder_are_unmoved
      priced_pool_value, the step-1 branch:
          `            return exact`
       -> `            return _r1_yoy_floored(exact, row.get("season"), row.get("round"), scoring_format)`
      (the clamp moves off the round curve and onto a real published slot)

  S6  test_no_market_price_is_never_an_error_and_never_floored
      _r1_yoy_floored:  `if current is None:`  ->  `if current is False:`
      (the unresolvable floor side stops being guarded — TypeError)

  S7  test_the_injector_seam_prices_a_future_first_at_the_current_class
      priced_pool_value, the step-2 return:
          `    return _r1_yoy_floored(market, row.get("season"), row.get("round"),`
          `                           scoring_format)`
       -> `    return market`
      (the clamp exists but is not wired into the waterfall)

  S8  test_the_anchor_season_comes_from_dps_own_map
      market_anchor_season:  `pool = slotted or published`
                          -> `pool = published`
      (a stale rung-only past season becomes "now" and every future pick
       floors against the wrong year)
"""
from __future__ import annotations

import pytest

import backend.data_loader as data_loader
import backend.pick_values as pv
import backend.server as srv
import backend.trade_service as ts


# ── the market map every test owns ─────────────────────────────────────────
# Shape copied from the real DP file (verified against
# fixtures/dp_values_picks_2026-08-06.csv): the CURRENT class gets a per-SLOT
# grid, every later season gets rungs only. Elos are round numbers chosen so
# the current class outprices both future seasons — which is the whole
# premise, and which `test_the_premise_holds` re-checks rather than assumes.
_ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

#: the CURRENT class, per SLOT — 12-team grid, rounds 1-4, descending
_SLOT_ELOS = {
    1: [1700, 1680, 1665, 1655, 1650, 1645, 1640, 1635, 1625, 1615, 1600, 1560],
    2: [1440, 1435, 1430, 1425, 1420, 1415, 1410, 1405, 1400, 1395, 1390, 1385],
    3: [1400, 1392, 1386, 1380, 1375, 1370, 1365, 1360, 1355, 1350, 1346, 1342],
    4: [1330, 1322, 1316, 1310, 1305, 1300, 1296, 1292, 1288, 1284, 1280, 1276],
}
#: every future season, per ROUND: (anchor+1 "Mid <ord>", anchor+2 "<ord>").
#: Each sits BELOW its round's current-class mid tercile, which is the defect
#: this change exists to clamp in round 1 and to leave alone in rounds 2-4.
_RUNG_ELOS = {1: (1581, 1520), 2: (1370, 1340), 3: (1330, 1300), 4: (1265, 1240)}
_SF_BUMP = 40.0            # superflex prices every pick higher (M6 §2.3)


def _market_map(fmt: str = "1qb_ppr", *, anchor: int = 2026) -> dict[str, float]:
    bump = _SF_BUMP if fmt == "sf_tep" else 0.0
    m: dict[str, float] = {}
    for rnd, elos in _SLOT_ELOS.items():
        for slot, elo in enumerate(elos, start=1):
            m[f"{anchor} Pick {rnd}.{slot:02d}"] = elo + bump
    # +1 season: DP's Early/Mid/Late rungs. +2: the round-generic rung only.
    for rnd, (mid, generic) in _RUNG_ELOS.items():
        m[f"{anchor + 1} Mid {_ORD[rnd]}"] = mid + bump
        m[f"{anchor + 2} {_ORD[rnd]}"] = generic + bump
    return m


def _row(season: int, rnd: int, pool_value: float = 2117.0) -> dict:
    """A `draft_picks` row as `load_draft_picks` returns it."""
    return {"pick_id": f"L_{season}_{rnd}_1", "season": season, "round": rnd,
            "owner_user_id": "u1", "is_traded": 0, "original_username": "",
            "pool_value": pool_value}


@pytest.fixture
def market(monkeypatch):
    """Install the fixture map and count how often the loader is consulted.

    The counter is what pins the knob-0 SHORT-CIRCUIT (plan §2: "0 disables …
    so no extra market lookup happens at 0"). Returns a small handle rather
    than the dict so a test can swap the map mid-test.
    """
    state = {"map": _market_map(), "sf": _market_map("sf_tep"), "calls": 0}

    def _fake(scoring: str = "1qb_ppr") -> dict[str, float]:
        state["calls"] += 1
        return dict(state["sf"] if scoring == "sf_tep" else state["map"])

    monkeypatch.setattr(data_loader, "load_pick_slot_values", _fake)
    return state


@pytest.fixture(autouse=True)
def _isolate_cfg():
    """Every test here reads live config; restore it so a knob override in one
    test cannot leak into the rest of the suite."""
    old = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old)


def _priced(row, fmt="1qb_ppr", slot=None):
    with ts.pick_pricing_override("market_slots"):
        return pv.priced_pool_value(row, scoring_format=fmt, slot=slot)


# ═══════════════════════════════════════════════════════════════════════════
# 0. the premise
# ═══════════════════════════════════════════════════════════════════════════

def test_the_premise_holds(market):
    """Without the floor the market curve DISCOUNTS a future first — that is
    the defect, and if the fixture ever stopped showing it every assertion
    below would pass vacuously."""
    mid = pv.market_pick_pool_value(2026, 1, "1qb_ppr")
    assert mid is not None
    assert pv.market_pick_pool_value(2027, 1, "1qb_ppr") < mid
    assert pv.market_pick_pool_value(2028, 1, "1qb_ppr") < mid
    assert pv.market_r1_yoy_floor() == 1.0          # the shipped default


# ═══════════════════════════════════════════════════════════════════════════
# 1. default 1.0 — the ruling
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fmt", ["1qb_ppr", "sf_tep"])
@pytest.mark.parametrize("season", [2027, 2028, 2031])
def test_default_floor_lifts_a_future_first_to_the_current_class(
        market, fmt, season):
    """A future 1st prices at the CURRENT class's 1st. Both formats, inside
    DP's published window (2027, 2028) and out past its horizon (2031, which
    rides `market_pick_pool_value`'s own extrapolation before the clamp)."""
    mid = pv.market_pick_pool_value(2026, 1, fmt)
    raw = pv.market_pick_pool_value(season, 1, fmt)
    assert raw < mid, "fixture no longer discounts the future — see premise"
    assert _priced(_row(season, 1), fmt) == mid


def test_the_floor_is_a_floor_not_a_peg(market):
    """`max`, never `min`: a future first the market prices ABOVE the current
    class keeps its market price. Nothing in the ruling caps a first."""
    market["map"]["2027 Mid 1st"] = 1740.0          # above every 2026 slot
    mid = pv.market_pick_pool_value(2026, 1, "1qb_ppr")
    raw = pv.market_pick_pool_value(2027, 1, "1qb_ppr")
    assert raw > mid
    assert _priced(_row(2027, 1), "1qb_ppr") == raw


def test_the_current_class_itself_is_never_floored(market):
    """`season > anchor` is STRICT. The current class prices at its own round
    curve — flooring it against itself would be a no-op today and a silent
    self-reference the moment the basis changes."""
    assert (_priced(_row(2026, 1), "1qb_ppr")
            == pv.market_pick_pool_value(2026, 1, "1qb_ppr"))


# ═══════════════════════════════════════════════════════════════════════════
# 2. knob 0 — the deploy-free revert
# ═══════════════════════════════════════════════════════════════════════════

def test_knob_zero_is_byte_identical_to_the_raw_market(market):
    """0 = pure market. Two claims, and the second is the one a value-only
    assertion cannot make: at 0 the clamp returns BEFORE the anchor lookup,
    so the disabled path costs exactly one market load — the same as the
    pre-D-161 waterfall — rather than three."""
    ts._cfg["market_r1_yoy_floor"] = 0.0
    assert pv.market_r1_yoy_floor() == 0.0

    for season in (2026, 2027, 2028, 2031):
        expected = pv.market_pick_pool_value(season, 1, "1qb_ppr")
        market["calls"] = 0
        assert _priced(_row(season, 1), "1qb_ppr") == expected
        assert market["calls"] == 1, (
            f"{season}: knob 0 took {market['calls']} market loads, not 1 — "
            "the short-circuit is gone")

    # …and at the default a floored pick really does take the extra two
    # (the anchor read + the current-class price), so the count above is
    # measuring something that can move.
    ts._cfg["market_r1_yoy_floor"] = 1.0
    market["calls"] = 0
    _priced(_row(2027, 1), "1qb_ppr")
    assert market["calls"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# 3. fractions
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rate", [0.85, 0.5])
@pytest.mark.parametrize("season", [2027, 2028])
def test_a_fraction_dials_the_floor_and_above_one_clamps(market, rate, season):
    """A fraction is a dialled YoY discount: `max(market, rate × mid)`.
    0.85 lifts both future seasons in this fixture; 0.5 sits below the market
    for both, so the market price stands untouched — the same expression
    covering both directions."""
    ts._cfg["market_r1_yoy_floor"] = rate
    mid = pv.market_pick_pool_value(2026, 1, "1qb_ppr")
    raw = pv.market_pick_pool_value(season, 1, "1qb_ppr")
    expected = max(raw, round(rate * mid, 1))
    assert _priced(_row(season, 1), "1qb_ppr") == expected
    assert (expected > raw) is (rate == 0.85), (
        "the fixture no longer exercises both sides of the max()")


def test_a_rate_above_one_clamps_to_one(market):
    """Mirrors `year_decay`'s clamp, for the mirror reason: above 1 a FUTURE
    first would outprice a CURRENT one and re-open the year arbitrage D-079
    closed, pointing the other way."""
    ts._cfg["market_r1_yoy_floor"] = 2.0
    assert pv.market_r1_yoy_floor() == 1.0
    assert (_priced(_row(2027, 1), "1qb_ppr")
            == pv.market_pick_pool_value(2026, 1, "1qb_ppr"))
    ts._cfg["market_r1_yoy_floor"] = -1.0
    assert pv.market_r1_yoy_floor() == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 4. rounds 2-4 — "other picks can degrade"
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rate", [0.0, 0.85, 1.0])
@pytest.mark.parametrize("season", [2027, 2028])
@pytest.mark.parametrize("rnd", [2, 3, 4])
def test_rounds_two_to_four_are_unmoved_at_every_setting(
        market, rate, season, rnd):
    """The other half of the same operator ruling. A round-2 clamp would
    overturn it, so the floor must be inert for rounds 2-4 at every knob
    setting — including the ones that move round 1."""
    ts._cfg["market_r1_yoy_floor"] = rate
    expected = pv.market_pick_pool_value(season, rnd, "1qb_ppr")
    assert expected is not None
    assert _priced(_row(season, rnd), "1qb_ppr") == expected
    assert expected < pv.market_pick_pool_value(2026, rnd, "1qb_ppr"), (
        "rounds 2-4 must still be DISCOUNTED — if the fixture stopped "
        "discounting them this test could not tell a floor from no floor")


# ═══════════════════════════════════════════════════════════════════════════
# 5. step 1 and the ladder mode
# ═══════════════════════════════════════════════════════════════════════════

def test_step_one_slot_price_and_tier_ladder_are_unmoved(market):
    """Two untouched paths, both at the default knob.

    STEP 1 — a resolved per-slot price is a real published price for a real
    ordered pick and is returned verbatim, even for a future season and even
    when it sits far below the floor. In production DP publishes future slots
    for nobody (#273 refuses a future slot anyway), so this is a structural
    guarantee rather than a live case: the fixture hands 2027 a slot row on
    purpose, precisely to prove the clamp lives at step 2 only.

    TIER_LADDER — the harness/test axis returns the stored value before any
    DP read; the floor cannot reach it, and it is flat in round 1 already."""
    market["map"]["2027 Pick 1.11"] = 1400.0        # far below the 2026 mid
    exact = pv.market_pick_slot_value(2027, 1, 11, "1qb_ppr")
    mid = pv.market_pick_pool_value(2026, 1, "1qb_ppr")
    assert exact is not None and exact < mid
    assert _priced(_row(2027, 1), "1qb_ppr", slot=11) == exact

    # the current class's own slots, likewise verbatim
    slot6 = pv.market_pick_slot_value(2026, 1, 6, "1qb_ppr")
    assert _priced(_row(2026, 1), "1qb_ppr", slot=6) == slot6

    with ts.pick_pricing_override("tier_ladder"):
        assert pv.priced_pool_value(_row(2027, 1, 2117.0),
                                    scoring_format="1qb_ppr") == 2117.0
        assert pv.priced_pool_value(_row(2028, 1, 2117.0),
                                    scoring_format="1qb_ppr",
                                    slot=11) == 2117.0


# ═══════════════════════════════════════════════════════════════════════════
# 6. the fallback chain — the floor must never turn a fallback into an error
# ═══════════════════════════════════════════════════════════════════════════

def test_no_market_price_is_never_an_error_and_never_floored(market):
    """Three shapes of "no price", all of which existed before D-161 and none
    of which the floor may change:

      (a) DP unreachable — `load_pick_slot_values` fail-softs to `{}`;
      (b) a season DP neither publishes nor extrapolates to (a PAST season);
      (c) the FUTURE side resolves but the CURRENT-class side does not, so
          there is no floor to apply. Plan §2: "floor only applies when the
          current-season side resolves (None ⇒ no floor)". This is the shape
          that reaches the clamp with an unresolvable anchor price, which is
          why an unguarded floor would raise here rather than misprice.
    """
    # (b) past season, live map
    assert pv.market_pick_pool_value(2019, 1, "1qb_ppr") is None
    assert _priced(_row(2019, 1, 1234.5), "1qb_ppr") == 1234.5

    # (c) 2026 is slotted in round 2 only, so it is still the anchor, but it
    #     has no round-1 price at all; 2027's rung still resolves.
    market["map"] = {k: v for k, v in market["map"].items()
                     if not k.startswith("2026 Pick 1.")}
    assert pv.market_anchor_season("1qb_ppr") == 2026
    assert pv.market_pick_pool_value(2026, 1, "1qb_ppr") is None
    raw27 = pv.market_pick_pool_value(2027, 1, "1qb_ppr")
    assert raw27 is not None
    assert _priced(_row(2027, 1, 777.0), "1qb_ppr") == raw27

    # (a) DP unreachable
    market["map"], market["sf"] = {}, {}
    assert pv.market_anchor_season("1qb_ppr") is None
    assert _priced(_row(2027, 1, 777.0), "1qb_ppr") == 777.0
    assert _priced(_row(2027, 1, None), "1qb_ppr") == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 7. the injector seam, end to end
# ═══════════════════════════════════════════════════════════════════════════

def test_the_injector_seam_prices_a_future_first_at_the_current_class(market):
    """`server._priced_pick_value` is THE pricing call every owned-pick site
    routes through (`_owned_pick_assets` → `_inject_owned_picks`, the league
    surfaces, `/api/trade/evaluate`). `slot_order=None` is what every league
    with an unresolved order gets, and what `pick_slots.slot_for` returns for
    a future season regardless — so this is the real production shape of the
    MangoPatti card's three future firsts."""
    mid = pv.market_pick_pool_value(2026, 1, "1qb_ppr")
    for season in (2027, 2028):
        priced = srv._priced_pick_value(_row(season, 1), None, "1qb_ppr")
        assert priced == mid
        assert priced > pv.market_pick_pool_value(season, 1, "1qb_ppr")
    # rounds 2-4 ride the same seam and are still discounted through it
    assert (srv._priced_pick_value(_row(2028, 2), None, "1qb_ppr")
            == pv.market_pick_pool_value(2028, 2, "1qb_ppr"))


# ═══════════════════════════════════════════════════════════════════════════
# 8. the clock
# ═══════════════════════════════════════════════════════════════════════════

def test_the_anchor_season_comes_from_dps_own_map(market):
    """"Now" is read out of the same map the price comes from — no new clock,
    no `server._CURRENT_SEASON` import (which `database.py` could not follow),
    and no `min(draft_picks.season)` (which #228 empties post-draft).

    DP publishes a per-SLOT grid only for the class that has an order, so the
    earliest SLOTTED season is DP's own statement of the current class. A
    rung-only season that sorts earlier — a stale past rung DP has not
    dropped — must NOT win, or every future pick would floor against the
    wrong year."""
    assert pv.market_anchor_season("1qb_ppr") == 2026
    assert pv.market_anchor_season("sf_tep") == 2026

    market["map"]["2025 1st"] = 1600.0              # stale rung-only season
    assert pv.market_anchor_season("1qb_ppr") == 2026
    assert (_priced(_row(2027, 1), "1qb_ppr")
            == pv.market_pick_pool_value(2026, 1, "1qb_ppr"))

    # no slot grid at all (a post-draft window, or a thin fixture): the
    # earliest published season is the same answer by a weaker route
    market["map"] = {k: v for k, v in market["map"].items()
                     if " Pick " not in k and not k.startswith("2025 ")}
    assert pv.market_anchor_season("1qb_ppr") == 2027

    # a map with no parseable season is None, exactly where
    # `market_pick_pool_value` also has nothing to say
    market["map"] = {"Josh Allen": 1858.9}
    assert pv.market_anchor_season("1qb_ppr") is None
