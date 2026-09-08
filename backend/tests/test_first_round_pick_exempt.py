"""#427 — first-round picks are exempt from the stud tax.

PRD: docs/feedback/items/427-first-round-picks-stud-tax-exempt/prd.md (R-5).
Report (mattmurf77, 1.17.2): *"First round picks should not be devalued. Two
firsts straight up for a player in the 2-1sts tier should be even. Other draft
picks should still be subject to the tax."*

Rule under test: inside `package_value_v2` / `_package_value_market` (and
gen-v2's `consolidated_value`) an asset flagged exempt contributes its FACE
value; the taxable subset keeps today's depth formula and per-side cap;
benchmark selection and the crown credit are unchanged over ALL values. The
mask is built from asset IDS at every call site by `first_round_pick_mask`
(generic `generic_pick_1_*` rungs + owned `{league}_{season}_1_{orig}` ids).
Knob `stud_tax_exempt_first_round` ≤ 0 restores today's math byte-for-byte.

Literal values (elo_to_value, k 0.005 / ref 1500 / base 1000):
  Mid 1st 1650 → 2117.0 · Early 1st 1720 → 3004.2 · Late 1st 1580 → 1491.8
  Mid 2nd 1400 → 606.5 · `firsts_2` floor 1788 → 4220.7 · `second` 1538.6 → 1213.1
"""

import csv
import pathlib
from dataclasses import dataclass

import pytest

import backend.feature_flags as ff
import backend.server as srv
import backend.trade_service as ts
from backend.trade_gen_v2 import consolidated_value
from backend.trade_optimizer import _consensus_packages, _fairness_v3
from backend.trade_service import package_value_v2

M1, E1, L1, M2 = 2117.0, 3004.2, 1491.8, 606.5
P_F2 = 4220.7     # player at the `firsts_2` band floor (Elo 1788)
P_2ND = 1213.1    # player in the `second` tier (Elo 1538.6)
KNOB = "stud_tax_exempt_first_round"

# id → consensus value, in the `_consensus_packages(seed_value)` convention.
_VALS = {
    "generic_pick_1_mid": M1, "generic_pick_1_early": E1,
    "generic_pick_1_late": L1, "generic_pick_2_mid": M2,
    "L_2027_1_3": M1, "L_2028_1_7": M1,          # owned-pick id shape
    "wr_2117": M1, "p_f2": P_F2, "p_2nd": P_2ND,
    "p_4234": 4234.0, "p_4496": 4496.0, "p_2723": 2723.5,
}
_sv = _VALS.__getitem__


def _mask(ids):
    fn = getattr(ts, "first_round_pick_mask", None)
    assert fn is not None, "trade_service.first_round_pick_mask is missing"
    return fn(ids)


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


def _pair(give_ids, recv_ids, mode="market"):
    """(give_pkg, receive_pkg, ratio) through the calculator's own path."""
    with ts.stud_tax_override(mode):
        gv, rv = _consensus_packages(give_ids, recv_ids, _sv)
    return gv, rv, round(min(gv, rv) / max(gv, rv), 3)


# ── R-4 knob ───────────────────────────────────────────────────────────────

def test_knob_default_is_on():
    assert ts._DEFAULT_CFG[KNOB] == 1.0


# ── a. the report: two Mid 1sts vs a `firsts_2`-floor player → even ───────

def test_a_two_firsts_vs_firsts_2_floor_player_is_even():
    gv, rv, ratio = _pair(["generic_pick_1_mid", "generic_pick_1_mid"], ["p_f2"])
    assert (gv, rv) == (4234.0, 4220.7)        # today: 3492.8 / 4220.7
    assert ratio == 0.997 and ratio >= 0.95


# ── b/c. seconds and players are still taxed (unchanged numbers) ──────────

def test_b_two_seconds_still_taxed():
    gv, rv, ratio = _pair(["generic_pick_2_mid", "generic_pick_2_mid"], ["p_2nd"])
    # 2 × 606.5·(0.40 + 0.60·√(606.5/1213.1)) = 999.8 (the PRD's "999.9"
    # rounded each piece first); pinned to today's actual — unchanged.
    assert (gv, rv) == (999.8, 1213.1)
    assert ratio == 0.824 and ratio < 0.95


def test_c_two_players_still_taxed():
    gv, rv, ratio = _pair(["wr_2117", "wr_2117"], ["p_4234"])
    assert (gv, rv) == (3489.9, 4234.0)
    assert ratio == 0.824 and ratio < 0.95


# ── d. mixed package: first at face, WR cross-benchmarked, cap inert ──────

def test_d_first_plus_wr_taxes_only_the_wr():
    gv, rv, ratio = _pair(["generic_pick_1_mid", "wr_2117"], ["p_4234"])
    # 2117.0 (face) + 2117·(0.40 + 0.60·√(2117/4234)) = 2117.0 + 1745.0;
    # cap on the taxable subset only: 0.65·2117 = 1376 < 1745 → inert.
    assert (gv, rv) == (3862.0, 4234.0)        # today: 3489.9
    assert ratio == 0.912 and ratio < 0.95


# ── e/f. any first rung; first + second ───────────────────────────────────

def test_e_early_and_late_first_both_exempt():
    gv, rv, ratio = _pair(["generic_pick_1_early", "generic_pick_1_late"], ["p_4496"])
    assert (gv, rv) == (4496.0, 4496.0)        # today ratio 0.842
    assert ratio == 1.0


def test_f_first_plus_second_discounts_only_the_second():
    gv, rv, ratio = _pair(["generic_pick_1_mid", "generic_pick_2_mid"], ["p_2723"])
    # 2117.0 face + 606.5·(0.40 + 0.60·√(606.5/2723.5)) = 414.3 → 2531.3
    assert (gv, rv) == (2531.3, 2723.5)        # today ratio 0.874
    assert ratio == 0.929


# ── g/h. identity and symmetry ────────────────────────────────────────────

def test_g_one_for_one_first_is_identity():
    gv, rv, ratio = _pair(["generic_pick_1_mid"], ["generic_pick_1_mid"])
    assert (gv, rv) == (M1, M1) and ratio == 1.0


def test_h_stud_on_the_give_side_is_symmetric():
    gv, rv, ratio = _pair(["p_4234"], ["generic_pick_1_mid", "generic_pick_1_mid"])
    assert (gv, rv) == (4234.0, 4234.0)        # today: rv 3489.9 → 0.824
    assert ratio == 1.0


# ── i. owned-pick id shape {league}_{season}_{round}_{orig} ───────────────

def test_i_owned_first_round_pick_ids_are_exempt():
    gv, rv, ratio = _pair(["L_2027_1_3", "L_2028_1_7"], ["p_f2"])
    assert (gv, rv) == (4234.0, 4220.7) and ratio == 0.997


# ── j. knob ≤ 0 ⇒ byte-identical to today ────────────────────────────────

def test_j_knob_off_restores_todays_numbers():
    ts._cfg[KNOB] = 0.0
    gv, rv, ratio = _pair(["generic_pick_1_mid", "generic_pick_1_mid"], ["p_f2"])
    assert (gv, rv) == (3492.8, 4220.7) and ratio == 0.828


@pytest.mark.parametrize("mode", ["market", "heavy", "off"])
@pytest.mark.parametrize("vals,other", [
    ([M1, M1], [P_F2]), ([M1, 900.0, 450.0], [6500.0]),
    ([E1, L1, M2], [4496.0]), ([7000.0, M1], [3000.0, 3000.0, 2000.0]),
    ([M1], [M1]), ([M1, M2, 400.0, 300.0, 250.0], [9000.0]),
])
def test_j_knob_off_mask_is_ignored_byte_for_byte(mode, vals, other):
    """At the kill value an all-True mask must not move a single bit on any
    mode / shape / crown configuration — the deploy-free rollback lever."""
    ts._cfg[KNOB] = 0.0
    v_max = max(vals + other)
    with ts.stud_tax_override(mode):
        for kw in ({}, {"n_other": len(other), "other_values": other}):
            plain = package_value_v2(vals, v_max, **kw)
            masked = package_value_v2(vals, v_max, exempt=[True] * len(vals), **kw)
            assert masked == plain


@pytest.mark.parametrize("mode", ["market", "heavy", "off"])
def test_no_mask_and_all_false_mask_are_byte_identical(mode):
    vals, other = [M1, 900.0, 450.0], [6500.0]
    with ts.stud_tax_override(mode):
        plain = package_value_v2(vals, 6500.0, n_other=1, other_values=other)
        assert package_value_v2(vals, 6500.0, n_other=1, other_values=other,
                                exempt=None) == plain
        assert package_value_v2(vals, 6500.0, n_other=1, other_values=other,
                                exempt=[False] * 3) == plain


def test_cap_applies_to_the_taxable_subset_only():
    """A first at face plus a brutally discounted taxable subset: the side's
    floor is X + 0.65·ΣT, not 0.65·(X + ΣT)."""
    ts._cfg["crown_rate_market"] = 0.0
    ts._cfg["package_floor_market"] = 0.0
    ts._cfg["package_floor_cross"] = 0.0
    ts._cfg["package_adj_gamma_market"] = 8.0
    vals = [M1, 900.0, 900.0, 900.0]
    exempt = [True, False, False, False]
    with ts.stud_tax_override("market"):
        v = package_value_v2(vals, 9000.0, n_other=1, other_values=[9000.0],
                             exempt=exempt)
    assert v == pytest.approx(M1 + 0.65 * 2700.0, abs=0.1)


# ── k. mask guard — no player id is ever a first ──────────────────────────

_FIXTURE = (pathlib.Path(__file__).parent / "fixtures"
            / "dp_playerids_snapshot_2026-07-11.csv")


def test_k_mask_true_only_for_round_one_pick_ids():
    assert _mask(["generic_pick_1_early", "generic_pick_1_mid",
                  "generic_pick_1_late"]) == [True, True, True]
    assert _mask(["L_2027_1_3", "123456789_2028_1_12"]) == [True, True]
    assert _mask(["generic_pick_2_mid", "generic_pick_3_early",
                  "L_2027_2_3", "L_2027_4_3"]) == [False] * 4
    # malformed / non-pick shapes never match
    assert _mask(["generic_pick_1", "generic_pick_1_gold", "L_27_1_3",
                  "L_2027_x_3", "L_2027_1", "", None, 4046]) == [False] * 8
    assert _mask([]) == []


def test_k_no_player_id_in_the_snapshot_is_masked():
    with _FIXTURE.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 3000
    ids = [r[col] for r in rows for col in ("sleeper_id", "espn_id", "mfl_id")
           if r[col]]
    assert not any(_mask(ids)), [i for i, m in zip(ids, _mask(ids)) if m]


# ── l. the calculator's itemised "Package depth" row ──────────────────────

def test_l_adjustments_have_no_depth_row_for_two_firsts():
    with ts.stud_tax_override("market"):
        rows, naive = srv._evaluate_adjustments(
            ["generic_pick_1_mid", "generic_pick_1_mid"], ["p_f2"], _sv)
    assert naive == {"give": 4234.0, "receive": 4220.7}
    assert [r["key"] for r in rows["give"]] == []      # today: depth −741.2
    assert rows["receive"] == []


def test_l_adjustments_still_show_depth_on_the_wr_in_a_mixed_package():
    with ts.stud_tax_override("market"):
        rows, _ = srv._evaluate_adjustments(
            ["generic_pick_1_mid", "wr_2117"], ["p_4234"], _sv)
    depth = [r for r in rows["give"] if r["key"] == "package_depth"]
    assert len(depth) == 1 and depth[0]["amount"] == -372.0   # 3862.0 − 4234.0


# ── m. gen-v2's own curve ─────────────────────────────────────────────────

def test_m_consolidated_value_exempts_firsts():
    # A first that is NOT the side's best asset still counts at face.
    assert consolidated_value([3000.0, M1], exempt=[False, True]) == \
        pytest.approx(3000.0 + M1)                       # today ≈ 4385.0
    # [1st, WR]: only the WR rides the curve (v_best stays the side's max).
    wr = 1000.0
    curve = wr * (0.15 + 0.85 * (wr / M1) ** 1.5)
    assert consolidated_value([M1, wr], exempt=[True, False]) == \
        pytest.approx(M1 + curve)
    assert consolidated_value([M1, M1], exempt=[True, True]) == pytest.approx(4234.0)


def test_m_consolidated_value_knob_off_and_no_mask_are_identical():
    vals = [3000.0, M1, 400.0]
    plain = consolidated_value(vals)
    assert consolidated_value(vals, exempt=None) == plain
    assert consolidated_value(vals, exempt=[False] * 3) == plain
    ts._cfg[KNOB] = 0.0
    assert consolidated_value(vals, exempt=[False, True, False]) == plain


# ── n. heavy mode: depth exemption applies, crown premium untouched ───────

def test_n_heavy_mode_exempts_depth_but_keeps_the_crown_premium():
    gv, rv, ratio = _pair(["generic_pick_1_mid", "generic_pick_1_mid"],
                          ["p_f2"], mode="heavy")
    assert (gv, rv) == (4234.0, 4577.0)        # today: 1913.5 / 4577.0
    assert ratio == 0.925


# ── R-7 untouched: `off` mode and the market crown credit ─────────────────

def test_off_mode_unchanged():
    gv, rv, ratio = _pair(["generic_pick_1_mid", "generic_pick_1_mid"],
                          ["p_f2"], mode="off")
    assert (gv, rv) == (4234.0, 4220.7) and ratio == 0.997


def test_crown_credit_still_paid_on_elite_other_side():
    # Three firsts vs a 6351 stud: the stud keeps its ≥ 6000 crown credit
    # (reconciliation ruling b) — the picks are at face, the credit is not
    # the pick tax.
    vals = {"generic_pick_1_mid": M1, "stud": 6351.0}
    with ts.stud_tax_override("market"):
        gv, rv = _consensus_packages(["generic_pick_1_mid"] * 3, ["stud"],
                                     vals.__getitem__)
    assert gv == 6351.0
    assert rv > 6351.0


# ── end-to-end — POST /api/trade/evaluate ─────────────────────────────────

@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str | None = None
    age: int | None = None


_POOL = [
    _P("generic_pick_1_mid", "2027 Mid 1st", "RB", "PICK"),
    _P("p_f2", "Floor Guy", "WR", "MIN", 25),
    _P("wr_2117", "Mid Wideout", "WR", "ATL", 24),
    _P("p_4234", "Two Firsts Guy", "WR", "DET", 24),
]
_SEED = {"generic_pick_1_mid": 1650.0, "p_f2": 1788.0,
         "wr_2117": 1650.0, "p_4234": 1788.6}


@pytest.fixture()
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(srv.g_universal_by_format, "1qb_ppr",
                        {"players": _POOL, "seed": dict(_SEED)})
    yield


def _evaluate(body):
    with srv.app.test_client() as c:
        return c.post("/api/trade/evaluate", json=body).get_json()


def test_evaluate_report_case_is_even(_pool):
    d = _evaluate({"give_player_ids": ["generic_pick_1_mid", "generic_pick_1_mid"],
                   "receive_player_ids": ["p_f2"]})
    assert d["stud_tax_mode"] == "market"
    assert (d["give_value"], d["receive_value"]) == (4234.0, 4220.7)
    assert d["point_ratio"] >= 0.95
    assert d["verdict"] == "even" and d["favors"] == "even"
    give_rows = (d.get("adjustments") or {}).get("give", [])
    assert not any(r["key"] == "package_depth" for r in give_rows)


def test_evaluate_mixed_package_is_fair_not_even(_pool):
    d = _evaluate({"give_player_ids": ["generic_pick_1_mid", "wr_2117"],
                   "receive_player_ids": ["p_4234"]})
    assert d["give_value"] == 3862.0
    assert d["verdict"] == "fair" and d["favors"] == "receive"
    assert [r["key"] for r in d["adjustments"]["give"]] == ["package_depth"]


def test_fairness_v3_point_ratio_uses_the_mask():
    with ts.stud_tax_override("market"):
        fairness, point_ratio, gv, rv = _fairness_v3(
            ["generic_pick_1_mid", "generic_pick_1_mid"], ["p_f2"], _sv, None, 0.75)
    assert (gv, rv) == (4234.0, 4220.7) and point_ratio == 0.997
