"""Age-preference consensus value multiplier (docs/plans/age-pref-value/scope.md,
evidence docs/business/analytics/2026-08-29-trade-disposition-review.md).

Covers `trade_service.age_pref_value`: band boundaries at the taste_service
cut points (u23 = age<23, 30plus = age>=30), the boost cap (`age_pref_boost_cap`
bounds INCREASES only, <=0 disables), exact identity at the 1.0 kill values
(the arm-A pin relies on byte-identical accessors), pass-through for picks /
missing age, and the MODEL_A_PROFILE pin itself.
"""

from types import SimpleNamespace

from backend import trade_service as ts
from backend.bakeoff_profiles import MODEL_A_PROFILE
from backend.trade_service import _cfg_override, age_pref_value


def _p(age):
    return SimpleNamespace(age=age)


KNOBS = {"age_pref_mult_u23": 1.10,
         "age_pref_mult_30plus": 0.90,
         "age_pref_boost_cap": 500.0}


def test_u23_boosted():
    with _cfg_override(KNOBS):
        assert age_pref_value(1000.0, _p(22)) == 1000.0 * 1.10


def test_boost_cap_engages_on_large_values():
    # 8000 * 1.10 = 8800 would be a +800 boost; the cap holds it to +500.
    with _cfg_override(KNOBS):
        assert age_pref_value(8000.0, _p(22)) == 8500.0


def test_boost_cap_nonpositive_disables():
    with _cfg_override({**KNOBS, "age_pref_boost_cap": 0.0}):
        assert age_pref_value(8000.0, _p(22)) == 8000.0 * 1.10


def test_30plus_discounted_and_never_capped():
    # The cap bounds increases only — a discount passes through untouched
    # even when the cap is far smaller than the decrease.
    with _cfg_override({**KNOBS, "age_pref_boost_cap": 10.0}):
        assert age_pref_value(8000.0, _p(33)) == 8000.0 * 0.90


def test_band_boundaries():
    with _cfg_override(KNOBS):
        assert age_pref_value(1000.0, _p(22)) == 1100.0   # u23
        assert age_pref_value(1000.0, _p(23)) == 1000.0   # 23–26 untouched
        assert age_pref_value(1000.0, _p(29)) == 1000.0   # 27–29 untouched
        assert age_pref_value(1000.0, _p(30)) == 900.0    # 30plus


def test_future_boost_on_30plus_band_is_capped_too():
    # "A maximum value increase" is band-agnostic: if the 30plus mult is
    # ever tuned above 1.0, its increase rides the same cap.
    with _cfg_override({**KNOBS, "age_pref_mult_30plus": 1.50,
                        "age_pref_boost_cap": 100.0}):
        assert age_pref_value(1000.0, _p(31)) == 1100.0


def test_kill_values_are_exact_identity():
    v = 1234.5678901
    with _cfg_override({"age_pref_mult_u23": 1.0,
                        "age_pref_mult_30plus": 1.0,
                        "age_pref_boost_cap": 500.0}):
        assert age_pref_value(v, _p(21)) == v
        assert age_pref_value(v, _p(35)) == v


def test_missing_age_and_picks_pass_through():
    with _cfg_override(KNOBS):
        assert age_pref_value(1000.0, None) == 1000.0
        assert age_pref_value(1000.0, _p(None)) == 1000.0
        assert age_pref_value(1000.0, _p(0)) == 1000.0
        # Owned-pick pseudo-players carry no age attribute at all.
        assert age_pref_value(1000.0, SimpleNamespace(position="PICK")) == 1000.0


def test_model_a_profile_pins_the_identity():
    assert MODEL_A_PROFILE["age_pref_mult_u23"] == 1.0
    assert MODEL_A_PROFILE["age_pref_mult_30plus"] == 1.0
    # The cap is deliberately absent — unread while both mults are 1.0.
    assert "age_pref_boost_cap" not in MODEL_A_PROFILE
    with _cfg_override(MODEL_A_PROFILE):
        v = 4263.9
        assert age_pref_value(v, _p(21)) == v
        assert age_pref_value(v, _p(35)) == v


def test_defaults_registered_in_both_stores():
    # Five-registration discipline: _DEFAULT_CFG and the DB seed list must
    # carry the same defaults (config-reference documents them; the arm-A
    # golden pins the knob inventory).
    from backend.database import _MODEL_CONFIG_DEFAULTS
    seeded = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    for key in KNOBS:
        assert key in ts._DEFAULT_CFG, key
        assert key in seeded, key
        assert ts._DEFAULT_CFG[key] == seeded[key], key
