"""#214/#215 — stud-tax retune ('market' shapes) + stud_tax_mode toggle.

Pins the three #214 market-mode shape changes in package_value_v2
(tuning-proposal.md §1–3):
  1. crown credit phases out as the naive gap widens (skew_phaseout);
  2. crown credit per elite asset (≥ crown_elite_value) on EITHER side,
     count-independent (crown_rate_market per piece);
  3. depth discount benchmarks the package's OWN best asset, total capped
     at package_discount_cap × naive sum;
and the #215 mode plumbing: 'market' (default) | 'heavy' (pre-#214 legacy
math, byte-identical) | 'off' (naive sums), end-to-end through
POST /api/trade/evaluate, the GET/PUT /api/settings/stud-tax route, and
TradeService.generate_trades' per-user mode resolution.

The legacy heavy-path pins live in test_crown_asset.py /
test_fairness_gate_golden.py (fixtures there pin mode='heavy').
"""

from dataclasses import dataclass

import pytest

import backend.feature_flags as ff
import backend.server as srv
import backend.trade_service as ts
from backend.trade_service import package_value_v2

USER = "stm_user"


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.crown_asset": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _market(vals, other=None):
    with ts.stud_tax_override("market"):
        return package_value_v2(vals, max(vals + (other or [])),
                                n_other=len(other) if other else None,
                                other_values=other)


# ── Shape 1 — crown phase-out at high naive skew ─────────────────────────

def test_crown_full_strength_on_even_trade():
    # 7000 elite vs a 7000-sum package: skew 0 → full crown_rate_market.
    v = _market([7000.0], other=[4000.0, 3000.0])
    assert v == pytest.approx(7000.0 * (1 + 0.08), rel=1e-6)


def test_crown_phases_to_zero_at_skew_phaseout():
    # |naive skew| = |7000 − 12000| / 7000 = 71.4% ≥ skew_phaseout (0.5)
    # → no crown at all, even for a clearly elite single asset.
    v = _market([7000.0], other=[8000.0, 4000.0])
    assert v == pytest.approx(7000.0, rel=1e-6)


def test_crown_scales_linearly_between():
    # skew 25% → phase factor 1 − 0.25/0.5 = 0.5 → half the full credit.
    v = _market([8000.0], other=[6000.0, 4000.0])
    assert v == pytest.approx(8000.0 * (1 + 0.08 * 0.5), rel=1e-6)


def test_crown_monotone_decreasing_in_skew():
    creds = []
    for other_sum in ([7000.0], [6500.0], [6000.0], [5500.0]):
        creds.append(_market([7000.0], other=other_sum) - 7000.0)
    assert creds == sorted(creds, reverse=True)
    assert creds[0] > creds[-1] >= 0


# ── Shape 2 — elite credit for BOTH sides, count-independent ─────────────

def test_multi_piece_side_with_elite_earns_credit():
    # Two-piece side holding an elite (6500 ≥ crown_elite_value 6000) earns
    # the per-piece credit — impossible under the legacy outnumbered-side
    # rule (len(values) >= n_other never crowned).
    vals = [6500.0, 3000.0]
    with_credit = _market(vals, other=[9000.0])
    ts._cfg["crown_rate_market"] = 0.0
    without = _market(vals, other=[9000.0])
    assert with_credit > without


def test_sub_elite_pieces_earn_nothing():
    # 5999.9 < crown_elite_value → no credit at any skew.
    v = _market([5999.0], other=[5999.0])
    assert v == pytest.approx(5999.0, rel=1e-6)


def test_credit_is_per_elite_piece():
    # Both pieces elite → both earn; sum of credits = rate × Σ elite values
    # × phase (skew 0 here → phase 1). Asserted as the DELTA over the
    # crown-free value so the pin is independent of the depth benchmark
    # (which the 2026-08-21 cross-package fix deliberately changed for
    # this shape — the side no longer holds the trade's best asset).
    v = _market([6500.0, 6500.0], other=[13000.0])
    ts._cfg["crown_rate_market"] = 0.0
    base = _market([6500.0, 6500.0], other=[13000.0])
    assert v - base == pytest.approx(13000.0 * 0.08, rel=1e-4)


def test_credit_count_independent_on_equal_counts():
    # 1-for-1 of two elites: BOTH sides earn (legacy: neither did). Ratio
    # of the sides is preserved (both scale by the same 1+rate at skew≈0).
    a = _market([7000.0], other=[7000.0])
    assert a == pytest.approx(7000.0 * 1.08, rel=1e-6)


# ── Shape 3 — own-best-asset benchmark + total-discount cap ──────────────

def test_single_asset_side_never_depth_discounted():
    # Legacy shaved a lone asset sitting below the trade-wide v_max; market
    # benchmarks the package's OWN best → a single asset is always whole.
    ts._cfg["crown_rate_market"] = 0.0   # isolate the depth shape
    v = _market([3000.0], other=[9000.0])
    assert v == pytest.approx(3000.0, rel=1e-6)


def test_depth_benchmarks_own_best_at_kill_value():
    # 2026-08-21 amendment: the original #214 own-max benchmark survives
    # only at package_bench_trade_wide ≤ 0 (arm A's pin). At the kill
    # value the pre-fix shape must hold byte-for-byte.
    ts._cfg["crown_rate_market"] = 0.0
    ts._cfg["package_bench_trade_wide"] = 0.0
    vals = [4000.0, 2000.0]
    # Same package, wildly different other side → identical depth math.
    assert _market(vals, other=[9000.0]) == _market(vals, other=[4500.0])
    # Exact shape: floor + (1−floor)·(v/own_max)^γ with own_max = 4000.
    floor, gamma = 0.70, 0.5
    expected = 4000.0 + 2000.0 * (floor + (1 - floor) * (2000.0 / 4000.0) ** gamma)
    assert _market(vals, other=[9000.0]) == pytest.approx(expected, abs=0.1)


def test_depth_benchmarks_trade_best_at_default():
    # …and at the live default the benchmark IS the trade's best asset:
    # the same package prices LOWER against a 9000 stud than against a
    # 4500 headliner (docs/reviews/2026-08-21-market-curve-comparison.md
    # §3b — the four-quarters-buy-a-dollar fix). Full shape pins live in
    # test_package_benchmark.py.
    ts._cfg["crown_rate_market"] = 0.0
    vals = [4000.0, 2000.0]
    assert _market(vals, other=[9000.0]) < _market(vals, other=[4500.0])


def test_total_discount_capped():
    ts._cfg["crown_rate_market"] = 0.0
    ts._cfg["package_floor_market"] = 0.0   # brutal per-piece discounting…
    ts._cfg["package_adj_gamma_market"] = 8.0
    vals = [1000.0, 900.0, 900.0, 900.0, 900.0]
    naive = sum(vals)                        # 4600
    # Uncapped contributions: 1000 + 4 × 900·(0.9)^8 ≈ 2549.7 — a −45%
    # side discount, past the 35% cap…
    uncapped = 1000.0 + 4 * 900.0 * (900.0 / 1000.0) ** 8
    assert uncapped < naive * (1 - 0.35)
    v = _market(vals, other=[9000.0])
    # …so the SIDE total floors at (1 − package_discount_cap)·naive.
    assert v == pytest.approx(naive * (1 - 0.35), rel=1e-6)


# ── Modes ────────────────────────────────────────────────────────────────

def test_default_mode_is_market():
    assert ts.current_stud_tax_mode() == "market"
    assert ts.STUD_TAX_DEFAULT == "market"


def test_off_mode_returns_naive_sums():
    with ts.stud_tax_override("off"):
        assert package_value_v2([4000.0, 2000.0], 9000.0, n_other=1,
                                other_values=[9000.0]) == 6000.0
        assert package_value_v2([9000.0], 9000.0, n_other=2,
                                other_values=[4000.0, 2000.0]) == 9000.0


def test_heavy_mode_is_pre_214_math_byte_identical():
    vals, v_max = [4000.0, 2000.0], 9000.0
    gamma = 1.5
    expected = round(sum(v * (0.15 + 0.85 * (v / v_max) ** gamma) for v in vals), 1)
    with ts.stud_tax_override("heavy"):
        assert package_value_v2(vals, v_max) == expected
        # crown: outnumbered side only, share/elite scaling — legacy formula.
        crowned = package_value_v2([5000.0], 5000.0, n_other=3)
        assert crowned == pytest.approx(5000.0 * (1 + 0.12 * 5000.0 / 6000.0),
                                        rel=1e-6)


def test_override_restores_previous_mode():
    with ts.stud_tax_override("heavy"):
        assert ts.current_stud_tax_mode() == "heavy"
        with ts.stud_tax_override("off"):
            assert ts.current_stud_tax_mode() == "off"
        assert ts.current_stud_tax_mode() == "heavy"
    assert ts.current_stud_tax_mode() == "market"
    assert ts.pinned_stud_tax_mode() is None


# ── End-to-end — /api/trade/evaluate under all three modes ───────────────

@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str | None = None
    age: int | None = None


_POOL = [
    _P("elite", "Elite Ace", "WR", "MIN", 25),
    _P("p1",    "Piece One", "RB", "DET", 24),
    _P("p2",    "Piece Two", "WR", "ATL", 23),
]
# elite 1900 → 7389.1; p1 1780 → 4055.2; p2 1650 → 2117.0 (elo_to_value).
_SEED = {"elite": 1900.0, "p1": 1780.0, "p2": 1650.0}
_BODY = {"give_player_ids": ["elite"], "receive_player_ids": ["p1", "p2"]}


@pytest.fixture()
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr",
        {"players": _POOL, "seed": dict(_SEED)},
    )
    yield


def _post_as_user(body, monkeypatch, mode_in_db, token="stm-sess"):
    """POST with an injected session; the user's stored stud_tax_mode is
    monkeypatched at the DB seam (get_stud_tax_mode)."""
    import backend.database as db
    monkeypatch.setattr(db, "get_stud_tax_mode",
                        lambda uid: mode_in_db if uid == USER else "market")
    with srv._sessions_lock:
        srv._sessions[token] = {"verified": True, "user_id": USER, "active_format": "1qb_ppr",
                                "last_active": 0.0}
    try:
        with srv.app.test_client() as c:
            return c.post("/api/trade/evaluate", json=body,
                          headers={"X-Session-Token": token}).get_json()
    finally:
        with srv._sessions_lock:
            srv._sessions.pop(token, None)


def test_evaluate_anonymous_defaults_to_market(_pool):
    with srv.app.test_client() as c:
        d = c.post("/api/trade/evaluate", json=_BODY).get_json()
    assert d["stud_tax_mode"] == "market"
    # Market shapes visible: elite (7389.1 ≥ 6000, skew 19.7% < 50%) earns
    # a consolidation row; the package is depth-shaved vs its own best.
    rows = {r["key"] for r in d["adjustments"]["give"]}
    assert rows == {"consolidation"}
    rrows = {r["key"] for r in d["adjustments"]["receive"]}
    assert rrows == {"package_depth"}


def test_evaluate_respects_stored_heavy_mode(_pool, monkeypatch):
    d = _post_as_user(_BODY, monkeypatch, "heavy")
    assert d["stud_tax_mode"] == "heavy"
    m = _post_as_user(_BODY, monkeypatch, "market")
    # Heavy shaves the package against the trade-wide best (elite) — a much
    # deeper cut than market's own-best benchmark.
    heavy_recv, market_recv = d["receive_value"], m["receive_value"]
    assert heavy_recv < market_recv
    # And heavy's give side carries the legacy single-crown premium.
    grows = {r["key"]: r for r in d["adjustments"]["give"]}
    assert grows["consolidation"]["amount"] > 0


def test_evaluate_off_mode_naive_totals_stand(_pool, monkeypatch):
    d = _post_as_user(_BODY, monkeypatch, "off")
    assert d["stud_tax_mode"] == "off"
    assert "adjustments" not in d          # zero rows are omitted entirely
    assert d["give_value"] == pytest.approx(7389.1, abs=0.11)
    assert d["receive_value"] == pytest.approx(4055.2 + 2117.0, abs=0.15)


def test_evaluate_mode_ordering_market_between_off_and_heavy(_pool, monkeypatch):
    off = _post_as_user(_BODY, monkeypatch, "off")["receive_value"]
    mkt = _post_as_user(_BODY, monkeypatch, "market")["receive_value"]
    heavy = _post_as_user(_BODY, monkeypatch, "heavy")["receive_value"]
    assert heavy < mkt < off


# ── Settings route ───────────────────────────────────────────────────────

def _settings_call(monkeypatch, method, body=None, token="stm-set"):
    store = {}
    import backend.database as db
    monkeypatch.setattr(db, "get_stud_tax_mode",
                        lambda uid: store.get(uid, "market"))
    monkeypatch.setattr(db, "set_stud_tax_mode",
                        lambda uid, mode: store.__setitem__(uid, mode))
    with srv._sessions_lock:
        srv._sessions[token] = {"verified": True, "user_id": USER, "active_format": "1qb_ppr",
                                "last_active": 0.0}
    try:
        with srv.app.test_client() as c:
            if method == "GET":
                return c.get("/api/settings/stud-tax",
                             headers={"X-Session-Token": token})
            return c.put("/api/settings/stud-tax", json=body,
                         headers={"X-Session-Token": token})
    finally:
        with srv._sessions_lock:
            srv._sessions.pop(token, None)


def test_settings_get_defaults_market(monkeypatch):
    r = _settings_call(monkeypatch, "GET")
    assert r.status_code == 200 and r.get_json() == {"mode": "market"}


def test_settings_put_validates_and_persists(monkeypatch):
    bad = _settings_call(monkeypatch, "PUT", {"mode": "extra_heavy"})
    assert bad.status_code == 400
    ok = _settings_call(monkeypatch, "PUT", {"mode": "heavy"})
    assert ok.status_code == 200 and ok.get_json() == {"ok": True, "mode": "heavy"}


def test_settings_requires_session():
    with srv.app.test_client() as c:
        r = c.get("/api/settings/stud-tax")
    assert r.status_code == 401


# ── Deck generation resolves the user's mode ─────────────────────────────

def test_generate_trades_pins_user_mode(monkeypatch):
    seen = {}

    svc = ts.TradeService(players={})
    svc.add_league(ts.League(league_id="L1", name="L1", platform="sleeper", members=[]))
    monkeypatch.setattr(ts, "stud_tax_mode_for_user",
                        lambda uid: "off" if uid == USER else "market")
    monkeypatch.setattr(
        ts.TradeService, "_generate_trades_impl",
        lambda self, *a, **k: seen.setdefault("mode", ts.current_stud_tax_mode()) and [] or [])
    svc.generate_trades(USER, {}, [], "L1", {})
    assert seen["mode"] == "off"


def test_generate_trades_respects_existing_pin(monkeypatch):
    seen = {}
    svc = ts.TradeService(players={})
    svc.add_league(ts.League(league_id="L1", name="L1", platform="sleeper", members=[]))
    monkeypatch.setattr(ts, "stud_tax_mode_for_user", lambda uid: "market")
    monkeypatch.setattr(
        ts.TradeService, "_generate_trades_impl",
        lambda self, *a, **k: seen.setdefault("mode", ts.current_stud_tax_mode()) and [] or [])
    with ts.stud_tax_override("heavy"):
        svc.generate_trades(USER, {}, [], "L1", {})
    assert seen["mode"] == "heavy"
