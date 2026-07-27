"""F8 — calibration module: reliability tables + ECE on hand-computed
fixtures, plus the inclusion rules for probability-emitting scorers."""

import pytest

from backend.eval.calibration import (
    calibration_pairs,
    ece,
    reliability_table,
    render_markdown,
)
from backend.tests.test_eval_replay import _card, _deck, _iso


# ---------------------------------------------------------------------------
# Hand-computed reliability table
# ---------------------------------------------------------------------------

def test_reliability_table_hand_computed():
    # decile 1 [0.0,0.1): preds 0.05,0.05,0.05 → mean 0.05, observed 1/3
    # decile 6 [0.5,0.6): pred 0.55           → mean 0.55, observed 1
    # decile 10 [0.9,1.0]: preds 0.95,0.95,1.0 → mean ≈0.9667, observed 2/3
    pairs = [
        (0.05, 0), (0.05, 0), (0.05, 1),
        (0.55, 1),
        (0.95, 1), (0.95, 0), (1.0, 1),
    ]
    rows = reliability_table(pairs)
    assert len(rows) == 10

    r0 = rows[0]
    assert (r0.n, r0.mean_predicted) == (3, pytest.approx(0.05))
    assert r0.observed_rate == pytest.approx(1 / 3)
    assert r0.gap == pytest.approx(1 / 3 - 0.05)

    r5 = rows[5]
    assert (r5.n, r5.mean_predicted, r5.observed_rate) == (1, 0.55, 1.0)
    assert r5.gap == pytest.approx(0.45)

    r9 = rows[9]                       # p=1.0 lands in the last bin
    assert r9.n == 3
    assert r9.mean_predicted == pytest.approx((0.95 + 0.95 + 1.0) / 3)
    assert r9.observed_rate == pytest.approx(2 / 3)

    # Empty bins are kept, explicitly empty
    for i in (1, 2, 3, 4, 6, 7, 8):
        assert rows[i].n == 0 and rows[i].observed_rate is None

    # ECE = Σ (n/N)·|gap|, N=7
    expected_ece = (
        3 / 7 * abs(1 / 3 - 0.05)
        + 1 / 7 * 0.45
        + 3 / 7 * abs(2 / 3 - (0.95 + 0.95 + 1.0) / 3)
    )
    assert ece(rows) == pytest.approx(expected_ece)


def test_perfectly_calibrated_ece_zero():
    pairs = [(0.25, 1), (0.25, 0), (0.25, 0), (0.25, 0),
             (0.75, 1), (0.75, 1), (0.75, 1), (0.75, 0)]
    rows = reliability_table(pairs)
    assert ece(rows) == pytest.approx(0.0)


def test_non_probability_prediction_raises():
    with pytest.raises(ValueError):
        reliability_table([(1.2, 1)])
    with pytest.raises(ValueError):
        reliability_table([(-0.1, 0)])
    with pytest.raises(ValueError):
        reliability_table([(float("nan"), 0)])


def test_ece_empty_is_none():
    assert ece(reliability_table([])) is None


def test_render_markdown_shape():
    text = render_markdown(reliability_table([(0.05, 0), (0.95, 1)]))
    assert text.count("|") > 20
    assert "ECE:" in text


# ---------------------------------------------------------------------------
# calibration_pairs — inclusion mirrors replay
# ---------------------------------------------------------------------------

class ProbaScorer:
    name = "proba_stub"
    def score(self, card):
        return float(card.get("base_score") or 0.0)
    def predict_proba(self, card):
        return 0.25 if card.get("card_index", 0) < 2 else 0.05


def test_calibration_pairs_inclusion_and_labels():
    served = _iso(1)
    cards = [
        _card("jc", 0, viewed=True, liked=True, served_at=served),
        _card("jc", 1, viewed=True, served_at=served),
        _card("jc", 2, viewed=False, served_at=served),               # never_viewed
        _card("jc", 3, viewed=True, undone=True, served_at=served),   # undo_reversed
        _card("jc", 4, viewed=True, propensity=0.0, served_at=served),# null_propensity
        _card("jc", 5, viewed=True, features=None, served_at=served), # bad_features
    ]
    pairs, excluded = calibration_pairs(ProbaScorer(), [_deck("jc", cards)])
    assert pairs == [(0.25, 1.0), (0.25, 0.0)]
    assert excluded == {"null_propensity": 1, "never_viewed": 1,
                        "undo_reversed": 1, "bad_features": 1,
                        "scorer_error": 0}


def test_calibration_requires_predict_proba():
    from backend.eval.scorers import get_scorer
    with pytest.raises(ValueError, match="predict_proba"):
        calibration_pairs(get_scorer("production"), [])
