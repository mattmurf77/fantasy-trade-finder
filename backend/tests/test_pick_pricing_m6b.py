"""Market pick pricing — built as rookie-draft M6b, made UNCONDITIONAL by the
operator ruling of 2026-08-21 (D-144).

Operator decision O2 (plan.md, *Operator decisions — 2026-08-06*) reversed
hld KD-9 / lld §4.7's "display-only" position and put DynastyProcess's market
curve into the trade engine behind a #214-style per-user toggle
(`pick_pricing_mode`) and a default-OFF flag (`trade.slot_pricing`).

**The 2026-08-21 ruling removed both**, verbatim: *"Market slots should be
default and not an opt-in or even an option to flip. Aligned that future picks
stay default for now."* So every assertion below that used to read "the flag
is the gate" now reads "there is no gate".

    'market_slots'  THE PRICE. Every owned pick, every user, no exceptions.
    'tier_ladder'   the legacy ladder, reachable ONLY by an explicit
                    `pick_pricing_override` from a harness or a test.

WHAT THIS FILE PINS, in priority order:

  T-M6B-01  the ladder axis still works and still reads NO DP data — the
            fetcher is patched to explode if `tier_ladder` touches it.
  T-M6B-02  THE INVERTED GATE TEST: no flag is read, no session is read, and
            `users.pick_pricing_mode` is never queried, whatever it stores.
  T-M6B-03  the stored `draft_picks.pool_value` column is never written —
            pricing is applied at READ time only (it is league-shared).
  T-M6B-04  GENERIC_PICK_SEEDS / the tier ladder are unchanged in BOTH modes
            (tier bands are absolute Elo mirrored across five clients).
  T-M6B-05  **ROUND-LEVEL, NOT PER-SLOT** — a 2026 1.01 and a 2026 1.12 get
            the SAME price. This is the honest scorecard for what the ruling
            did and did not buy; true-slot pricing is the unbuilt half of
            Q-023 and this test fails loudly if someone ships it silently.
  plus      the slot-mapping basis, format awareness, the DP-horizon
            extrapolation, fail-soft to the ladder, the thread-local
            contextmanager, the cap-after-pricing rule, and the retired route.
"""

from __future__ import annotations

import pathlib

import pytest

import backend.data_loader as data_loader
import backend.database as db
import backend.feature_flags as ff
import backend.pick_values as pv
import backend.server as srv
import backend.trade_service as ts

PICK_CSV = pathlib.Path(__file__).resolve().parent / "fixtures" / "dp_values_picks_2026-08-06.csv"
USER = "m6b_user"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    saved = ff._flags_cache
    monkeypatch.setenv("FTF_DP_PICK_VALUES_FILE", str(PICK_CSV))
    data_loader.reset_pick_values_cache()
    ff._flags_cache = {**ff.DEFAULT_FLAGS}          # everything OFF by default
    yield
    ff._flags_cache = saved
    data_loader.reset_pick_values_cache()


def _flag_on():
    """RETIRED helper, deliberately kept as a NO-OP marker.

    Every call site below used to need `trade.slot_pricing` on. D-144 removed
    the gate, so this sets the flag purely to prove the tests do not depend on
    it: each assertion holds with the flag in the state this leaves it in AND
    with the all-off default the autouse fixture installs. The pairing is
    checked directly by `test_m6b_02_the_flag_is_no_longer_read`.
    """
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.slot_pricing": True}


def _row(season, rnd, pool_value=None, pick_id=None):
    return {"pick_id": pick_id or f"L_{season}_{rnd}_1", "season": season,
            "round": rnd, "pool_value": pool_value, "owner_user_id": "o1"}


# ═══════════════════════════════════════════════════════════════════════════
# T-M6B-01 / T-M6B-04 — byte-identity, and the ladder is untouched in BOTH
# ═══════════════════════════════════════════════════════════════════════════

# The exact shipped ladder, spelled out rather than compared to itself, so a
# future edit to pick_values.py has to change this literal on purpose.
# Round 2 was deliberately repriced on 2026-08-19 (D-084) — 1520/1460/1400
# → 1470/1400/1370 — together with tier_config.json's `second.min`. Rounds 1,
# 3 and 4 have never moved. This literal is the tripwire: changing it is how
# you declare a repricing was intended.
SHIPPED_SEEDS = {
    (1, "Early"): 1720, (1, "Mid"): 1650, (1, "Late"): 1580,
    (2, "Early"): 1470, (2, "Mid"): 1400, (2, "Late"): 1370,
    (3, "Early"): 1360, (3, "Mid"): 1320, (3, "Late"): 1280,
    (4, "Early"): 1260, (4, "Mid"): 1240, (4, "Late"): 1220,
}


@pytest.mark.parametrize("mode", ["tier_ladder", "market_slots"])
def test_m6b_04_generic_ladder_byte_unchanged_in_every_mode(mode):
    """Tier bands are ABSOLUTE Elo mirrored across five clients
    (docs/cross-client-invariants.md). The 12 generic rungs are RANKABLE POOL
    assets whose seeds anchor those bands — repricing them would repaint tier
    colours everywhere for a PER-USER setting. They must not move in either
    mode."""
    _flag_on()
    with ts.pick_pricing_override(mode):
        assert pv.GENERIC_PICK_SEEDS == SHIPPED_SEEDS
        assert pv.GENERIC_PICK_SEEDS[(1, "Mid")] == 1650      # the base first
        assert srv.GENERIC_PICK_SEEDS is pv.GENERIC_PICK_SEEDS


def test_m6b_01_the_ladder_axis_prices_at_the_stored_value_and_never_reads_dp(monkeypatch):
    """The `tier_ladder` pin returns the stored pool_value and does not fetch,
    parse or cache DynastyProcess's values.csv.

    Production cannot reach this pin any more — it is the harness/test axis —
    but it stays load-bearing twice over: the bake-off arms price both curves
    in one process, and "no DP read" is what proves the market path really is
    the thing doing the repricing rather than something upstream."""
    def _explode(*a, **k):
        raise AssertionError("DP pick values read under the tier_ladder pin")
    monkeypatch.setattr(data_loader, "_fetch_pick_values_csv", _explode)
    data_loader.reset_pick_values_cache()

    for season, rnd, stored in ((2026, 1, 2117.0), (2027, 2, 695.9),
                                (2029, 4, 167.4)):
        row = _row(season, rnd, stored)
        with ts.pick_pricing_override("tier_ladder"):
            assert pv.priced_pool_value(row, scoring_format="1qb_ppr") == stored


def test_m6b_01b_tier_ladder_mode_is_the_stored_value_verbatim():
    """`tier_ladder` returns the stored float itself — no round-trip, no
    recompute, no DP read."""
    for stored in (2117.0, 0.0, 1.234567, 999.9):
        row = _row(2027, 1, stored)
        assert pv.priced_pool_value(row, scoring_format="1qb_ppr",
                                    mode="tier_ladder") == stored


def test_m6b_02_the_flag_is_no_longer_read(monkeypatch):
    """THE INVERTED GATE TEST (D-144).

    Before: `trade.slot_pricing` off ⇒ ladder for everyone, DB unread.
    Now: there is no gate. The resolver returns `market_slots` with the flag
    off, with the flag on, and with `is_enabled` rigged to explode — which is
    the strongest available proof that the flag is not consulted at all."""
    def _explode(key):
        raise AssertionError(f"feature flag {key!r} read by pick pricing")
    monkeypatch.setattr(ff, "is_enabled", _explode)

    ff._flags_cache = {**ff.DEFAULT_FLAGS}                      # flag off
    assert ts.pick_pricing_mode_for_user(USER) == "market_slots"
    _flag_on()                                                  # flag on
    assert ts.pick_pricing_mode_for_user(USER) == "market_slots"


def test_m6b_02_the_stored_column_is_no_longer_read(monkeypatch):
    """`users.pick_pricing_mode` is DEAD DATA. A row that still says
    'tier_ladder' — every row does, it was the old default — must not drag its
    owner back onto the ladder, and the column must not even be queried."""
    called = []
    monkeypatch.setattr(db, "get_pick_pricing_mode",
                        lambda uid: called.append(uid) or "tier_ladder")
    assert ts.pick_pricing_mode_for_user(USER) == "market_slots"
    assert ts.pick_pricing_mode_for_user(None) == "market_slots"
    assert ts.pick_pricing_mode_for_user("") == "market_slots"
    assert called == []                       # not one DB read


def test_m6b_02b_the_default_is_the_market():
    """The ruling, as constants. `market_slots` is the default in every module
    that names one, so an unpinned thread — a cron job, a background deck
    worker, a direct `priced_pool_value` call — prices at the market."""
    assert pv.PICK_PRICING_DEFAULT == "market_slots"
    assert ts.PICK_PRICING_DEFAULT == "market_slots"
    assert db.PICK_PRICING_MODES == pv.PICK_PRICING_MODES == ts.PICK_PRICING_MODES
    assert ts.current_pick_pricing_mode() == "market_slots"
    assert ts.pinned_pick_pricing_mode() is None
    # The flag key is KEPT (clients in the field still receive it) but is
    # never read. Its value is documentation, not behaviour.
    assert "trade.slot_pricing" in ff.FLAG_KEYS


def test_m6b_03_read_time_only_never_writes_the_shared_column():
    """`draft_picks.pool_value` is written by a league-wide sync path and
    SHARED by every user of the league. A per-user mode that rewrote it would
    silently reprice the user's leaguemates."""
    _flag_on()
    row = _row(2027, 2, 695.9)
    before = dict(row)
    with ts.pick_pricing_override("market_slots"):
        priced = pv.priced_pool_value(row, scoring_format="1qb_ppr")
    assert row == before                       # the row object is untouched
    assert row["pool_value"] == 695.9
    assert priced != 695.9                     # and the read DID reprice


# ═══════════════════════════════════════════════════════════════════════════
# The market curve itself
# ═══════════════════════════════════════════════════════════════════════════

def test_market_current_season_uses_the_mid_tercile_basis():
    """UNKNOWN_SLOT_BASIS = mid tercile (slots 5–8 of a 12-team round), in
    VALUE space. Pinned as an explicit computation so a change to the basis
    has to be a deliberate edit."""
    _flag_on()
    assert pv.UNKNOWN_SLOT_BASIS == "mid_tercile"
    assert pv._basis_slots(1) == [5, 6, 7, 8]
    m = data_loader.load_pick_slot_values("1qb_ppr")
    expected = sum(ts.elo_to_value(m[f"2026 Pick 1.{s:02d}"]) for s in (5, 6, 7, 8)) / 4
    assert pv.market_pick_pool_value(2026, 1, "1qb_ppr") == round(expected, 1)


def test_market_future_season_uses_dps_own_mid_rung():
    _flag_on()
    m = data_loader.load_pick_slot_values("1qb_ppr")
    assert pv.market_pick_pool_value(2027, 1, "1qb_ppr") == round(
        ts.elo_to_value(m["2027 Mid 1st"]), 1)
    # 2028 publishes only the round-generic rung
    assert "2028 Mid 1st" not in m and "2028 1st" in m
    assert pv.market_pick_pool_value(2028, 1, "1qb_ppr") == round(
        ts.elo_to_value(m["2028 1st"]), 1)


def test_market_beyond_dp_horizon_extrapolates_with_the_shipped_discount():
    """DP publishes through 2028. 2029+ rides the round's `year_decay` off the
    deepest published season, in value space — the same clock
    `pick_pool_value` uses, so the two curves do not diverge in the tail.

    D-079 made that clock per-round, and the tail follows it: a round-1 tail
    is FLAT (decay 1.0), a round-2 tail still decays. Pinning both is what
    stops the market path from quietly keeping a rate the ladder abandoned.
    """
    _flag_on()
    m = data_loader.load_pick_slot_values("1qb_ppr")
    base = ts.elo_to_value(m["2028 1st"])          # unrounded, as the code uses
    assert pv.market_pick_pool_value(2028, 1, "1qb_ppr") == round(base, 1)
    assert pv.market_pick_pool_value(2029, 1, "1qb_ppr") == round(
        base * pv.year_decay(1), 1)
    assert pv.market_pick_pool_value(2031, 1, "1qb_ppr") == round(
        base * pv.year_decay(1) ** 3, 1)
    # round 1 is flat by default, so the tail is literally the horizon price
    assert pv.market_pick_pool_value(2031, 1, "1qb_ppr") == round(base, 1)

    base2 = ts.elo_to_value(m["2028 2nd"])
    assert pv.market_pick_pool_value(2031, 2, "1qb_ppr") == round(
        base2 * pv.YEAR_DISCOUNT ** 3, 1)
    assert pv.market_pick_pool_value(2031, 2, "1qb_ppr") < round(base2, 1)


def test_market_is_scoring_format_aware():
    """M6 §2.3: superflex prices every pick higher (a 2026 1.01 is Elo 1864.3
    in sf_tep vs 1816.5 in 1qb_ppr), so the pricing path must be format-aware
    or SF users get 1QB pick prices."""
    _flag_on()
    for season, rnd in ((2026, 1), (2027, 1), (2028, 2)):
        sf = pv.market_pick_pool_value(season, rnd, "sf_tep")
        one = pv.market_pick_pool_value(season, rnd, "1qb_ppr")
        assert sf > one, (season, rnd, sf, one)


def test_market_past_season_and_missing_source_fall_back_to_the_ladder(monkeypatch):
    """No market price ⇒ the stored ladder value stands. Never 0, never
    None, never an invented number."""
    _flag_on()
    assert pv.market_pick_pool_value(2019, 1, "1qb_ppr") is None
    row = _row(2019, 1, 1234.5)
    with ts.pick_pricing_override("market_slots"):
        assert pv.priced_pool_value(row, scoring_format="1qb_ppr") == 1234.5

    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda *a, **k: {})
    assert pv.market_pick_pool_value(2027, 1, "1qb_ppr") is None
    row2 = _row(2027, 1, 777.0)
    with ts.pick_pricing_override("market_slots"):
        assert pv.priced_pool_value(row2, scoring_format="1qb_ppr") == 777.0


def test_market_deep_rounds_clamp_and_junk_input_is_none():
    _flag_on()
    assert (pv.market_pick_pool_value(2026, 9, "1qb_ppr")
            == pv.market_pick_pool_value(2026, 5, "1qb_ppr"))
    assert pv.market_pick_pool_value(None, 1, "1qb_ppr") is None
    assert pv.market_pick_pool_value("nope", 1, "1qb_ppr") is None


def test_the_measured_reshaping_direction_is_deflation_not_inflation():
    """The plan's premise ('DP's curve is much steeper, so adoption inflates
    pick values') is WRONG for owned picks and is pinned as wrong here, so a
    later wave cannot quietly re-adopt it. In 1QB every representative owned
    pick DEFLATES; the 1.01 inflation exists only for the literal 1.01 SLOT,
    which an unknown-slot owned pick never gets.

    THIS TEST IS THE HONEST SCORECARD FOR D-084, and its numbers were moved
    on purpose (2026-08-19). Before the round-2 recalibration a 2026 2nd
    priced from DynastyProcess's real market slots was **more than 40 %**
    cheaper than our ladder's price for it, and 2nds collapsed hardest of any
    round. Deflating the round-2 seeds closed most of that: the 2026 gap is
    now **-0.284** and the 2027 gap **-0.244**.

    THE REMAINING GAP IS INTENTIONAL, NOT UNFINISHED WORK. Option B in
    docs/reviews/2026-08-19-ktc-pick-value-comparison.md — pushing every rung
    to its market-median rank — was measured and rejected: it breaks
    test_tier_occupancy.py in three places and buckets the Mid 3rd seed as
    `second`. DynastyProcess's pick curve is also the most convex and most
    near-zero-anchored of the four sources surveyed, so full convergence on
    it was never the target; it is one vote, not the goal. Closing to ~28 %
    is the deliberate stopping point.

    NOTE THE RANKING FLIPPED. 2nds are no longer the biggest outlier — a
    2026 3rd now deflates hardest of the round-2/3 pair (-0.355 vs -0.284).
    That is the residue the memo predicted and explicitly declined to chase
    here: rounds 3-4 diverge because `seed_elo_for_value` compresses ranks
    ~200-300 into 32 Elo points, which no seed edit can fix (Q-019)."""
    _flag_on()
    def delta(season, rnd, fmt="1qb_ppr"):
        lad = pv.pick_pool_value(rnd, season - 2026, fmt)
        return (pv.market_pick_pool_value(season, rnd, fmt) - lad) / lad

    assert delta(2026, 1) < -0.10          # a 2026 1st gets CHEAPER, not dearer
    # Round 2, post-D-084: pinned to the VALUE, not to a loose bound, so that
    # any future drift in either direction has to be acknowledged here.
    assert delta(2026, 2) == pytest.approx(-0.284, abs=0.01)
    assert delta(2027, 2) == pytest.approx(-0.244, abs=0.01)
    # Still deflation everywhere, and still nowhere near parity with DP.
    assert delta(2026, 2) < -0.20
    assert delta(2027, 2) < -0.20
    assert delta(2028, 1) < -0.15
    # The round-3 residue D-084 deliberately did not chase (Q-019).
    assert delta(2026, 3) < delta(2026, 2)
    # ... but the literal top slot really is above our Early-1st rung.
    m = data_loader.load_pick_slot_values("1qb_ppr")
    assert m["2026 Pick 1.01"] > pv.GENERIC_PICK_SEEDS[(1, "Early")]


# ═══════════════════════════════════════════════════════════════════════════
# T-M6B-05 — what the ruling did NOT buy: the price is ROUND-level
# ═══════════════════════════════════════════════════════════════════════════

def test_m6b_05_a_101_and_a_112_price_identically(monkeypatch):
    """**THE SCORECARD TEST. Read it before quoting a 1.01 number anywhere.**

    Q-023 is about pricing a pick at its TRUE SLOT — a 1.01 above a 1.12. That
    is NOT what shipped. `market_slots` prices at the round's mid-tercile
    basis, so two 2026 firsts are the same number whatever slot D-090 resolved
    for them. The engine sees no 1.01/1.12 spread at all.

    The gap is large and the direction is counter-intuitive, so both are
    pinned: DP's own slot curve says the 1.01 is worth ~2.6x the round price
    and the 1.12 about 0.44x, and the shipped round price sits BELOW today's
    flat ladder rung. "Adopting the market" made firsts CHEAPER, not dearer.

    If true-slot pricing is ever built, this test fails — which is the point.
    Update it deliberately; do not relax it."""
    slots = data_loader.load_pick_slot_values("1qb_ppr")
    round_price = pv.market_pick_pool_value(2026, 1, "1qb_ppr")

    # Two owned 2026 firsts. Nothing in a `draft_picks` row carries a slot,
    # and `priced_pool_value` takes none, so they cannot differ.
    a = pv.priced_pool_value(_row(2026, 1, 2117.0, "the_101"),
                             scoring_format="1qb_ppr")
    b = pv.priced_pool_value(_row(2026, 1, 2117.0, "the_112"),
                             scoring_format="1qb_ppr")
    assert a == b == round_price

    v101 = ts.elo_to_value(slots["2026 Pick 1.01"])
    v112 = ts.elo_to_value(slots["2026 Pick 1.12"])
    assert v101 / v112 > 5.0                       # the spread DP publishes…
    assert a == b                                  # …and the spread we charge
    assert v101 > round_price * 2.5                # what a 1.01 is NOT charged
    assert v112 < round_price * 0.5                # what a 1.12 is NOT charged
    # And the headline direction, against the flat ladder rung it replaces.
    assert round_price < pv.pick_pool_value(1, 0)


def test_m6b_05b_the_badge_follows_the_served_value(monkeypatch):
    """D-320-2: a pick's tier badge reflects the value it is SERVED at, not
    its name. So the badge move is a consequence of the repricing, not a
    second decision — and it moves exactly as far as the value does.

    Walked over the same inverse the clients use, so a badge computed here
    matches what `/api/league/picks` would compute from the same number."""
    tier_for = srv.RankingService.tier_for_elo
    v2e = ts.value_to_elo

    ladder_1st = pv.pick_pool_value(1, 0)                       # 2117.0
    market_1st = pv.market_pick_pool_value(2026, 1, "1qb_ppr")  # 1859.5
    assert market_1st < ladder_1st

    # Both still band as firsts here — the round price did not fall through a
    # band edge — which is the honest, unexciting answer for the ROUND-level
    # curve. The 38/48 badge churn Q-023 measured belongs to TRUE-SLOT
    # pricing; asserting it against this build would be false.
    for value in (ladder_1st, market_1st):
        assert tier_for(v2e(value), None, "1qb_ppr") is not None

    # Where the badge DOES move: the per-slot curve, if it were ever served.
    slots = data_loader.load_pick_slot_values("1qb_ppr")
    band_101 = tier_for(v2e(ts.elo_to_value(slots["2026 Pick 1.01"])),
                        None, "1qb_ppr")
    band_112 = tier_for(v2e(ts.elo_to_value(slots["2026 Pick 1.12"])),
                        None, "1qb_ppr")
    band_now = tier_for(v2e(market_1st), None, "1qb_ppr")
    assert band_101 != band_112                 # slots would badge apart…
    assert band_now == tier_for(v2e(market_1st), None, "1qb_ppr")   # …we do not


# ═══════════════════════════════════════════════════════════════════════════
# Thread-local plumbing (the matrix/deck harnesses depend on it)
# ═══════════════════════════════════════════════════════════════════════════

def test_override_pins_nests_and_restores():
    assert ts.pinned_pick_pricing_mode() is None
    with ts.pick_pricing_override("market_slots"):
        assert ts.current_pick_pricing_mode() == "market_slots"
        assert ts.pinned_pick_pricing_mode() == "market_slots"
        with ts.pick_pricing_override("tier_ladder"):
            assert ts.current_pick_pricing_mode() == "tier_ladder"
        assert ts.current_pick_pricing_mode() == "market_slots"
    assert ts.pinned_pick_pricing_mode() is None
    # UNPINNED now lands on the market, not the ladder — the D-144 flip.
    assert ts.current_pick_pricing_mode() == "market_slots"


def test_override_rejects_garbage_and_none():
    """An unrecognised pin falls back to the DEFAULT, which is now the market.
    Note what this means: a typo'd mode string can no longer silently restore
    the old ladder — it fails safe toward the shipped price instead."""
    with ts.pick_pricing_override("nonsense"):
        assert ts.current_pick_pricing_mode() == "market_slots"
    with ts.pick_pricing_override(None):
        assert ts.current_pick_pricing_mode() == "market_slots"


def test_mode_for_user_cannot_fail(monkeypatch):
    """It used to be DB-failure-safe by catching. Now it is safe by not
    touching the DB at all: a `get_pick_pricing_mode` that raises on sight
    proves the call never happens."""
    def _boom(uid):
        raise AssertionError("users.pick_pricing_mode read after D-144")
    monkeypatch.setattr(db, "get_pick_pricing_mode", _boom)
    assert ts.pick_pricing_mode_for_user(USER) == "market_slots"
    assert ts.pick_pricing_mode_for_user(None) == "market_slots"


# ═══════════════════════════════════════════════════════════════════════════
# _owned_pick_assets — the engine read site
# ═══════════════════════════════════════════════════════════════════════════

_ROWS = [
    _row(2026, 1, 2117.0, "L_2026_1"), _row(2026, 2, 818.7, "L_2026_2"),
    _row(2027, 1, 1799.5, "L_2027_1"), _row(2027, 2, 695.9, "L_2027_2"),
    _row(2029, 4, 167.4, "L_2029_4"), _row(2030, 3, 212.2, "L_2030_3"),
]


def _assets(monkeypatch, mode, cap=6):
    monkeypatch.setattr(srv, "load_draft_picks", lambda **k: [dict(r) for r in _ROWS])
    monkeypatch.setattr(srv, "_picks_pool_cap", lambda: cap)
    with ts.pick_pricing_override(mode):
        out = srv._owned_pick_assets("L", "1qb_ppr")
    return {a.id: ts.elo_to_value(1200.0 + 6.0 * a.pick_value)
            for a in out.get("o1", [])}


def test_owned_pick_assets_ladder_reproduces_the_stored_value(monkeypatch):
    priced = _assets(monkeypatch, "tier_ladder")
    for r in _ROWS:
        assert priced[r["pick_id"]] == pytest.approx(r["pool_value"], rel=1e-3)


def test_owned_pick_assets_market_reprices_every_row(monkeypatch):
    _flag_on()
    priced = _assets(monkeypatch, "market_slots")
    for r in _ROWS:
        expected = pv.market_pick_pool_value(r["season"], r["round"], "1qb_ppr")
        assert priced[r["pick_id"]] == pytest.approx(expected, rel=1e-3)


def test_owned_pick_assets_caps_after_pricing_not_before(monkeypatch):
    """`market_slots` re-shapes the curve, so the top-N by stored value is not
    the top-N by market value. Capping on the stale order would inject a
    different set than the one the engine then prices. A real inversion in the
    fixture: the ladder says a 2030 3rd (212.2) beats a 2029 4th (167.4), the
    market says the opposite — deep future picks are the one place the market
    is DEARER than our uniformly-discounted ladder."""
    _flag_on()
    assert 167.4 < 212.2                     # ladder order
    assert (pv.market_pick_pool_value(2029, 4, "1qb_ppr")
            > pv.market_pick_pool_value(2030, 3, "1qb_ppr"))   # market order
    kept = list(_assets(monkeypatch, "market_slots", cap=5))
    assert "L_2029_4" in kept and "L_2030_3" not in kept


def test_owned_pick_assets_never_injects_a_zero_or_negative_price(monkeypatch):
    _flag_on()
    monkeypatch.setattr(srv, "load_draft_picks",
                        lambda **k: [_row(2019, 1, None, "L_stale")])
    with ts.pick_pricing_override("market_slots"):
        assert srv._owned_pick_assets("L", "1qb_ppr") == {}


# ═══════════════════════════════════════════════════════════════════════════
# Settings route + storage
# ═══════════════════════════════════════════════════════════════════════════

def _settings_call(monkeypatch, method, body=None, token="m6b-set"):
    # Both accessors raise: the retired route must touch NEITHER, on either
    # verb. (They still exist, and still round-trip — see the db test below —
    # because the column is kept as dead data, not dropped.)
    def _boom(*a, **k):
        raise AssertionError("retired route touched users.pick_pricing_mode")
    monkeypatch.setattr(db, "get_pick_pricing_mode", _boom)
    monkeypatch.setattr(db, "set_pick_pricing_mode", _boom)
    with srv._sessions_lock:
        srv._sessions[token] = {"user_id": USER, "active_format": "1qb_ppr",
                                "last_active": 0.0}
    try:
        with srv.app.test_client() as c:
            if method == "GET":
                return c.get("/api/settings/pick-pricing",
                             headers={"X-Session-Token": token})
            return c.put("/api/settings/pick-pricing", json=body,
                         headers={"X-Session-Token": token})
    finally:
        with srv._sessions_lock:
            srv._sessions.pop(token, None)


def test_route_get_serves_the_fixed_state_for_old_clients(monkeypatch):
    """Build 12x clients still GET this on Settings open. They must receive the
    TRUE fixed state — not the dead stored column, and not a 404 (which the
    shipped client reads as "flag dark, hide the control", i.e. a lie now)."""
    for flags in ({**ff.DEFAULT_FLAGS},
                  {**ff.DEFAULT_FLAGS, "trade.slot_pricing": True}):
        ff._flags_cache = flags
        r = _settings_call(monkeypatch, "GET")
        assert r.status_code == 200
        assert r.get_json() == {"mode": "market_slots", "retired": True}


def test_route_put_is_410_gone_whatever_the_body(monkeypatch):
    """410, not 404 and not 400: the resource existed and was withdrawn. A
    once-valid mode, a once-invalid mode and no body at all all get the same
    answer — there is nothing left to validate against."""
    for body in ({"mode": "market_slots"}, {"mode": "tier_ladder"},
                 {"mode": "market"}, {}, None):
        r = _settings_call(monkeypatch, "PUT", body)
        assert r.status_code == 410, body
        payload = r.get_json()
        assert payload["error"] == "gone"
        assert payload["mode"] == "market_slots"
        assert "no longer configurable" in payload["message"]


def test_route_still_requires_a_session_on_both_verbs():
    """Unchanged auth posture — the retirement did not make the route public."""
    with srv.app.test_client() as c:
        assert c.get("/api/settings/pick-pricing").status_code == 401
        assert c.put("/api/settings/pick-pricing",
                     json={"mode": "market_slots"}).status_code == 401


def test_db_accessors_survive_as_dead_data():
    """`users.pick_pricing_mode` is never dropped (additive-schema rule) and
    its accessors still work. Nothing in production calls them; this pins that
    the column's removal was NOT part of the retirement, so a restore of the
    per-user axis would not need a migration."""
    db.init_db()
    uid = "m6b_db_user"
    assert db.get_pick_pricing_mode(uid) == "tier_ladder"
    db.set_pick_pricing_mode(uid, "market_slots")
    assert db.get_pick_pricing_mode(uid) == "market_slots"
    db.set_pick_pricing_mode(uid, "tier_ladder")
    assert db.get_pick_pricing_mode(uid) == "tier_ladder"
    with pytest.raises(ValueError):
        db.set_pick_pricing_mode(uid, "market")
    # ...and none of it reaches pricing.
    assert ts.pick_pricing_mode_for_user(uid) == "market_slots"
