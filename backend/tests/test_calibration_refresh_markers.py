"""#406 ↔ #370 pin (models-lead condition 2(a)): eval's Calibration-refresh
exclusion and the receipts queue's skip must name the same deck_source.

eval.data excludes a deck whose cards carry deck_source CALIBRATION_REFRESH_SOURCE;
database._CALIBRATION_REFRESH_MARKERS is the receipts queue's LIKE match on the
features_json dump, in both JSON spellings. A rename on either side alone would
silently let refresh decks back into one of them."""
from backend import database
from backend.eval import data as eval_data


def test_every_receipts_marker_names_evals_refresh_source():
    source = eval_data.CALIBRATION_REFRESH_SOURCE
    assert source == "grading_refresh"
    assert len(database._CALIBRATION_REFRESH_MARKERS) == 2
    for marker in database._CALIBRATION_REFRESH_MARKERS:
        assert f'"{source}"' in marker and '"deck_source"' in marker


def test_both_json_spellings_are_matched():
    source = eval_data.CALIBRATION_REFRESH_SOURCE
    assert set(database._CALIBRATION_REFRESH_MARKERS) == {
        f'"deck_source": "{source}"', f'"deck_source":"{source}"'}
