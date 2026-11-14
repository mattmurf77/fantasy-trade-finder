"""Max PF moves: the most likely pick if you miss, derived at read time (D-263;
contract §3.4, §3.5, §3.7, §10).

The served block shows the single most likely pick and its chance in place
of the decimal average (`pick_if_miss`, which stays in the payload). It is
derived in `maxpf_moves.compose` from distributions the saved run already
holds; nothing saved, no setting and no hash changes. Same fixture forecast
as test_maxpf_moves / test_maxpf_moves_read. No network.

- test_basis_is_conditional_on_a_miss: renormalised over the non-playoff
  slots; on the fixture it is the argmax of the simulation's own
  `conditional_pick_probabilities` with that probability. Sabotage: drop the
  renormalisation (probability is the unconditional share).
- test_ties_go_to_the_earlier_pick (exact and float-noise ties). Sabotage:
  `>=` in the argmax.
- test_missing_distribution_gives_none.
- test_compose_attaches_to_baseline_rows_and_combined: every row's and
  entry's `now` is the baseline's, `after` comes from the item's saved
  `after_pick_probabilities`, labels via `pick_slots.slot_suffix`.
  Sabotage: derive `after` from the baseline distribution.
- test_missing_data_omits_the_item_only: an older row / entry without
  `after_pick_probabilities`, or with `pick_if_miss.after` null, has no
  `most_likely_pick`; its siblings keep theirs; `no_miss` has none.
  Sabotage: fall back to the "now" pick when "after" is missing.
- test_saved_data_is_not_mutated_and_not_saved: compose leaves the saved run
  byte-identical and `compute` writes no `most_likely_pick`.
- test_settings_and_hash_unchanged: settings keys and the current hash are
  the v1.1 ones. Sabotage: add a key to SETTINGS_KEYS.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from backend import pick_slots
from backend.league_projections import maxpf_moves
from backend.tests.test_maxpf_moves import _block, _result
from backend.tests.test_maxpf_moves_read import compose, saved_run


def _viewer(saved):
    return next(t for t in saved["teams"] if t["roster_id"] == saved["viewer_roster_id"])


def _expected(picks, round_=1):
    total = sum(picks)
    best = max(range(len(picks)), key=lambda k: (picks[k], -k))
    return {"slot": best + 1, "label": pick_slots.slot_suffix(round_, best + 1), "probability": picks[best] / total}


# ── the derivation ──────────────────────────────────────────────────────

def test_basis_is_conditional_on_a_miss():
    out = maxpf_moves.most_likely_pick([0.1, 0.3, 0.2], 1)
    assert out["slot"] == 2 and out["label"] == "1.02"
    assert out["probability"] == pytest.approx(0.5)  # 0.3 / 0.6, not 0.3
    assert maxpf_moves.most_likely_pick([0.0, 0.0, 0.05], 2) == {"slot": 3, "label": "2.03", "probability": 1.0}
    team = _viewer(_result())
    conditional = team["conditional_pick_probabilities"]
    assert conditional is not None and len(team["pick_probabilities"]) == len(conditional)
    ml = maxpf_moves.most_likely_pick(team["pick_probabilities"], 1)
    best = max(range(len(conditional)), key=lambda k: (conditional[k], -k))
    assert ml["slot"] == best + 1 and ml["probability"] == pytest.approx(conditional[best], abs=1e-12)


def test_ties_go_to_the_earlier_pick():
    assert maxpf_moves.most_likely_pick([0.1, 0.3, 0.3, 0.3], 1)["slot"] == 2
    assert maxpf_moves.most_likely_pick([0.25, 0.25, 0.25, 0.25], 1)["slot"] == 1
    noisy = [0.1, 0.3, 0.3 + 1e-15]
    assert maxpf_moves.most_likely_pick(noisy, 1)["slot"] == 2


def test_missing_distribution_gives_none():
    for picks in (None, [], [0.0, 0.0], "x"):
        assert maxpf_moves.most_likely_pick(picks, 1) is None


# ── the read ────────────────────────────────────────────────────────────

def test_compose_attaches_to_baseline_rows_and_combined():
    saved = saved_run()
    raw = saved["max_pf_moves"]
    out = compose(saved)
    assert out["state"] in ("ready", "no_moves") and out["rows"] and len(out["combined"]) == 2
    now = _expected(_viewer(saved)["pick_probabilities"])
    assert out["baseline"]["most_likely_pick"] == now
    for served, item in list(zip(out["rows"], raw["rows"])) + list(zip(out["combined"], raw["combined"])):
        ml = served["most_likely_pick"]
        assert ml["now"] == now
        assert ml["after"] == _expected(item["after_pick_probabilities"])
        assert ml["after"]["label"] == pick_slots.slot_suffix(1, ml["after"]["slot"])
        assert 0 < ml["after"]["probability"] <= 1
        assert served["pick_if_miss"] == item["pick_if_miss"]  # the average stays in the payload
    assert "after_pick_probabilities" not in json.dumps(out)


def test_missing_data_omits_the_item_only():
    saved = saved_run()
    raw = saved["max_pf_moves"]
    del raw["rows"][0]["after_pick_probabilities"]
    raw["rows"][1]["pick_if_miss"] = {**raw["rows"][1]["pick_if_miss"], "after": None}
    del raw["combined"][0]["after_pick_probabilities"]
    out = compose(saved, price=lambda dist: None)
    assert "most_likely_pick" not in out["rows"][0] and "most_likely_pick" not in out["rows"][1]
    assert all("most_likely_pick" in r for r in out["rows"][2:])
    assert "most_likely_pick" not in out["combined"][0] and "most_likely_pick" in out["combined"][1]
    assert "most_likely_pick" in out["baseline"]
    teams = deepcopy(saved["teams"])
    for t in teams:
        if t["roster_id"] == saved["viewer_roster_id"]:
            t["conditional_expected_pick"] = None
    no_miss = compose({**saved, "teams": teams})
    assert no_miss["state"] == "no_miss" and "most_likely_pick" not in no_miss["baseline"]


def test_saved_data_is_not_mutated_and_not_saved():
    saved = saved_run()
    before = json.dumps(saved, sort_keys=True)
    compose(saved)
    assert json.dumps(saved, sort_keys=True) == before
    assert "most_likely_pick" not in json.dumps(_block())


def test_settings_and_hash_unchanged():
    assert set(maxpf_moves.SETTINGS_KEYS) == {"simulations_per_candidate", "candidates", "min_drop_points",
                                              "min_pick_change", "min_top3_change", "time_budget_seconds",
                                              "combined_sizes"}
    current = maxpf_moves.settings()
    assert maxpf_moves.settings_hash(current) == "6c64a9efa1ac4591bc63a4b0089a4e06da46c2c07a24f4f7b475106c79af4c8c"  # origin/main 11f774fb
    assert _block()["settings_hash"] == maxpf_moves.settings_hash(_block()["settings"])
