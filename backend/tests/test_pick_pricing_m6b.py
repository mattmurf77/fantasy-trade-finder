"""rookie-draft M6b — DynastyProcess market slot values IN THE TRADE ENGINE.

Operator decision O2 (plan.md, *Operator decisions — 2026-08-06*) reverses
hld KD-9 / lld §4.7's "display-only" position. This wave adds a #214-style
per-user toggle, `pick_pricing_mode`:

    'tier_ladder'  DEFAULT — today's behaviour, EXACTLY
    'market_slots' the DP per-slot market curve

behind the default-OFF flag `trade.slot_pricing`.

The load-bearing tests here, in priority order:

  T-M6B-01  BYTE-IDENTITY with the flag off — GENERIC_PICK_SEEDS unchanged,
            every stored pool_value returned verbatim, and the DP source is
            NEVER read (the fetcher is patched to explode if touched).
  T-M6B-02  the flag is the ONE gate: a user with 'market_slots' STORED still
            prices at the ladder while the flag is off, and the settings
            route 404s.
  T-M6B-03  the stored `draft_picks.pool_value` column is never written —
            the mode is applied at READ time only (it is league-shared).
  T-M6B-04  GENERIC_PICK_SEEDS / the tier ladder are unchanged in BOTH modes
            (tier bands are absolute Elo mirrored across five clients).
  plus      the slot-mapping basis, format awareness, the DP-horizon
            extrapolation, fail-soft to the ladder, the thread-local
            contextmanager, the cap-after-pricing rule, and the route.
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
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.slot_pricing": True}


def _row(season, rnd, pool_value=None, pick_id=None):
    return {"pick_id": pick_id or f"L_{season}_{rnd}_1", "season": season,
            "round": rnd, "pool_value": pool_value, "owner_user_id": "o1"}


# ═══════════════════════════════════════════════════════════════════════════
# T-M6B-01 / T-M6B-04 — byte-identity, and the ladder is untouched in BOTH
# ═══════════════════════════════════════════════════════════════════════════

# The exact shipped ladder, spelled out rather than compared to itself, so a
# future edit to pick_values.py has to change this literal on purpose.
SHIPPED_SEEDS = {
    (1, "Early"): 1720, (1, "Mid"): 1650, (1, "Late"): 1580,
    (2, "Early"): 1520, (2, "Mid"): 1460, (2, "Late"): 1400,
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


def test_m6b_01_flag_off_prices_at_the_stored_value_and_never_reads_dp(monkeypatch):
    """Flag off ⇒ every price is the stored pool_value, and DynastyProcess's
    values.csv is not fetched, parsed or cached."""
    def _explode(*a, **k):
        raise AssertionError("DP pick values read while trade.slot_pricing is OFF")
    monkeypatch.setattr(data_loader, "_fetch_pick_values_csv", _explode)
    monkeypatch.setattr(db, "get_pick_pricing_mode", lambda uid: "market_slots")

    for season, rnd, stored in ((2026, 1, 2117.0), (2027, 2, 695.9),
                                (2029, 4, 167.4)):
        row = _row(season, rnd, stored)
        mode = ts.pick_pricing_mode_for_user(USER)
        assert mode == "tier_ladder"
        with ts.pick_pricing_override(mode):
            assert pv.priced_pool_value(row, scoring_format="1qb_ppr") == stored


def test_m6b_01b_tier_ladder_mode_is_the_stored_value_verbatim():
    """Even with the flag ON, `tier_ladder` returns the stored float itself —
    no round-trip, no recompute, no DP read."""
    _flag_on()
    for stored in (2117.0, 0.0, 1.234567, 999.9):
        row = _row(2027, 1, stored)
        assert pv.priced_pool_value(row, scoring_format="1qb_ppr",
                                    mode="tier_ladder") == stored


def test_m6b_02_stored_market_mode_cannot_escape_the_flag(monkeypatch):
    """THE gate test. A user row that says 'market_slots' prices at the ladder
    while the flag is off, without the DB even being read."""
    called = []
    monkeypatch.setattr(db, "get_pick_pricing_mode",
                        lambda uid: called.append(uid) or "market_slots")
    assert ts.pick_pricing_mode_for_user(USER) == "tier_ladder"
    assert called == []                       # no DB read at all
    _flag_on()
    assert ts.pick_pricing_mode_for_user(USER) == "market_slots"
    assert called == [USER]


def test_m6b_02b_defaults_are_todays_behaviour():
    """Unlike #214 — which shipped its retuned mode as the DEFAULT — the
    market mode here is opt-in."""
    assert pv.PICK_PRICING_DEFAULT == "tier_ladder"
    assert ts.PICK_PRICING_DEFAULT == "tier_ladder"
    assert db.PICK_PRICING_MODES == pv.PICK_PRICING_MODES == ts.PICK_PRICING_MODES
    assert ts.current_pick_pricing_mode() == "tier_ladder"
    assert ts.pinned_pick_pricing_mode() is None
    assert ff.DEFAULT_FLAGS["trade.slot_pricing"] is False


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
    pick DEFLATES, 2nds hardest (~-40%); the 1.01 inflation exists only for
    the literal 1.01 SLOT, which an unknown-slot owned pick never gets."""
    _flag_on()
    def delta(season, rnd, fmt="1qb_ppr"):
        lad = pv.pick_pool_value(rnd, season - 2026, fmt)
        return (pv.market_pick_pool_value(season, rnd, fmt) - lad) / lad

    assert delta(2026, 1) < -0.10          # a 2026 1st gets CHEAPER, not dearer
    assert delta(2026, 2) < -0.40          # 2nds collapse hardest
    assert delta(2027, 2) < -0.40
    assert delta(2028, 1) < -0.15
    # ... but the literal top slot really is above our Early-1st rung.
    m = data_loader.load_pick_slot_values("1qb_ppr")
    assert m["2026 Pick 1.01"] > pv.GENERIC_PICK_SEEDS[(1, "Early")]


# ═══════════════════════════════════════════════════════════════════════════
# Thread-local plumbing (the matrix/deck harnesses depend on it)
# ═══════════════════════════════════════════════════════════════════════════

def test_override_pins_nests_and_restores():
    _flag_on()
    assert ts.pinned_pick_pricing_mode() is None
    with ts.pick_pricing_override("market_slots"):
        assert ts.current_pick_pricing_mode() == "market_slots"
        assert ts.pinned_pick_pricing_mode() == "market_slots"
        with ts.pick_pricing_override("tier_ladder"):
            assert ts.current_pick_pricing_mode() == "tier_ladder"
        assert ts.current_pick_pricing_mode() == "market_slots"
    assert ts.pinned_pick_pricing_mode() is None
    assert ts.current_pick_pricing_mode() == "tier_ladder"


def test_override_rejects_garbage_and_none():
    with ts.pick_pricing_override("nonsense"):
        assert ts.current_pick_pricing_mode() == "tier_ladder"
    with ts.pick_pricing_override(None):
        assert ts.current_pick_pricing_mode() == "tier_ladder"


def test_mode_for_user_is_db_failure_safe(monkeypatch):
    _flag_on()
    def _boom(uid):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "get_pick_pricing_mode", _boom)
    assert ts.pick_pricing_mode_for_user(USER) == "tier_ladder"
    assert ts.pick_pricing_mode_for_user(None) == "tier_ladder"


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
    store = {}
    monkeypatch.setattr(db, "get_pick_pricing_mode",
                        lambda uid: store.get(uid, "tier_ladder"))
    monkeypatch.setattr(db, "set_pick_pricing_mode",
                        lambda uid, mode: store.__setitem__(uid, mode))
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


def test_m6b_02c_route_404s_while_the_flag_is_dark(monkeypatch):
    assert _settings_call(monkeypatch, "GET").status_code == 404
    assert _settings_call(monkeypatch, "PUT",
                          {"mode": "market_slots"}).status_code == 404


def test_route_get_defaults_to_tier_ladder(monkeypatch):
    _flag_on()
    r = _settings_call(monkeypatch, "GET")
    assert r.status_code == 200 and r.get_json() == {"mode": "tier_ladder"}


def test_route_put_validates_and_persists(monkeypatch):
    _flag_on()
    assert _settings_call(monkeypatch, "PUT", {"mode": "market"}).status_code == 400
    ok = _settings_call(monkeypatch, "PUT", {"mode": "market_slots"})
    assert ok.status_code == 200
    assert ok.get_json() == {"ok": True, "mode": "market_slots"}


def test_route_requires_a_session():
    _flag_on()
    with srv.app.test_client() as c:
        assert c.get("/api/settings/pick-pricing").status_code == 401


def test_db_accessors_round_trip_and_reject_bad_modes():
    db.init_db()
    uid = "m6b_db_user"
    assert db.get_pick_pricing_mode(uid) == "tier_ladder"
    db.set_pick_pricing_mode(uid, "market_slots")
    assert db.get_pick_pricing_mode(uid) == "market_slots"
    db.set_pick_pricing_mode(uid, "tier_ladder")
    assert db.get_pick_pricing_mode(uid) == "tier_ladder"
    with pytest.raises(ValueError):
        db.set_pick_pricing_mode(uid, "market")
