"""#355 — draft picks must never be offered for a class the league lacks.

Operator report (2026-08-19, BUG, TradesHome, v1.15.0): "2029 picks showing on
sleeper league without 2029 picks available".

The ground truth these tests encode was read off the live Sleeper API on
2026-08-19 for every league present in prod:

    league 1312140920132497408  2026 draft `pre_draft`  traded picks 2026/27/28
    league 1312583962966650880  2026 draft `complete`   traded picks incl. 2029

so the window is not `current_season + N` — it is three consecutive rookie
classes anchored to the first class that has NOT been drafted, and it rolls
forward the moment a draft completes.
"""

import pytest

import backend.database as db
from backend import draft_status as ds
from backend.database import sync_draft_picks


# ---------------------------------------------------------------------------
# The pure helper
# ---------------------------------------------------------------------------

class TestPickHorizon:

    def test_predraft_league_stops_one_class_short_of_the_old_window(self):
        """THE regression. 2026 undrafted ⇒ 2026-2028, and 2029 is phantom."""
        assert ds.pick_horizon(2026) == (2026, 2028)

    def test_postdraft_league_rolls_forward_and_2029_is_real(self):
        """2026 drafted ⇒ the anchor moves, so 2029 becomes legitimate."""
        assert ds.pick_horizon(2026, exclude_seasons={2026}) == (2027, 2029)

    def test_window_is_always_three_classes_wide(self):
        for cur in (2024, 2026, 2030):
            for exclude in ((), {2024, 2026, 2030}):
                first, last = ds.pick_horizon(cur, exclude_seasons=exclude)
                assert last - first + 1 == ds.PICK_HORIZON_CLASSES

    def test_platform_reported_season_widens_the_window(self):
        """A traded pick the platform reports is existence proof."""
        assert ds.pick_horizon(2026, observed_seasons=[2026, 2029]) == (2026, 2029)

    def test_widening_is_bounded_so_a_bad_feed_cannot_reopen_the_defect(self):
        first, last = ds.pick_horizon(2026, observed_seasons=[2099])
        assert (first, last) == (2026, 2028)
        assert last <= 2026 + ds.PICK_HORIZON_MAX_CLASSES - 1

    def test_observed_seasons_never_narrow_the_window(self):
        assert ds.pick_horizon(2026, observed_seasons=[2026]) == (2026, 2028)

    def test_garbage_observed_seasons_are_ignored_not_fatal(self):
        assert ds.pick_horizon(2026, observed_seasons=[None, "x", {}, 2027]) \
            == (2026, 2028)

    def test_unknown_horizon_degrades_to_the_narrowest_plausible_window(self):
        """A flaked drafts read gives no exclusions ⇒ pre-draft reading.

        Deliberately NOT "allow nothing" (would empty ~55% of served cards on
        one flaky HTTP read) and NOT the old default (that is the defect).
        """
        assert ds.pick_horizon(2026, exclude_seasons=()) == (2026, 2028)

    def test_consecutive_completed_classes_keep_walking_the_anchor(self):
        assert ds.pick_horizon(2026, exclude_seasons={2026, 2027}) == (2028, 2030)


# ---------------------------------------------------------------------------
# The grid builder
# ---------------------------------------------------------------------------

ROSTERS = [1, 2]
RID_TO_USER = {"1": "u1", "2": "u2"}
NAMES = {"u1": "Alice", "u2": "Bob"}


_LEAGUE = "L355"


@pytest.fixture
def _clean_league():
    yield _LEAGUE
    db.replace_draft_picks(_LEAGUE, [])       # tear down synthetic rows


def _sync(monkeypatch, flag_on=True, **kw):
    monkeypatch.setattr("backend.feature_flags.is_enabled",
                        lambda key: flag_on if key == "picks.league_horizon"
                        else False)
    params = dict(
        league_id=_LEAGUE, roster_ids=ROSTERS, traded_picks=[],
        roster_id_to_user=RID_TO_USER, user_id_to_name=NAMES,
        current_season=2026, rounds=1, seasons_ahead=3, league_size=2,
    )
    params.update(kw)
    return sync_draft_picks(**params)


def _seasons(rows):
    return sorted({int(r["season"]) for r in rows})


@pytest.mark.usefixtures("_clean_league")
class TestSyncGridHorizon:

    def test_predraft_grid_no_longer_invents_the_fourth_class(self, monkeypatch):
        """The operator's exact case: 2029 must not be generated."""
        rows = _sync(monkeypatch)
        assert _seasons(rows) == [2026, 2027, 2028]
        assert 2029 not in _seasons(rows)

    def test_postdraft_grid_keeps_2029_because_it_is_real(self, monkeypatch):
        rows = _sync(monkeypatch, exclude_seasons=(2026,))
        assert _seasons(rows) == [2027, 2028, 2029]

    def test_kill_switch_restores_the_historical_window(self, monkeypatch):
        """OFF ⇒ byte-identical to the shipped behavior, phantom included."""
        rows = _sync(monkeypatch, flag_on=False)
        assert _seasons(rows) == [2026, 2027, 2028, 2029]

    def test_a_reported_far_pick_pulls_its_whole_class_into_the_grid(self, monkeypatch):
        """Sleeper proving 2029 exists must give EVERY team its 2029 pick,
        not just the one row the traded-picks feed happened to mention."""
        traded = [{"season": 2029, "round": 1, "roster_id": 1, "owner_id": 2}]
        rows = _sync(monkeypatch, traded_picks=traded)
        assert 2029 in _seasons(rows)
        assert len([r for r in rows if int(r["season"]) == 2029]) == len(ROSTERS)

    def test_every_generated_season_lies_inside_the_derived_horizon(self, monkeypatch):
        rows = _sync(monkeypatch, rounds=3)
        first, last = ds.pick_horizon(2026)
        assert all(first <= int(r["season"]) <= last for r in rows)

    def test_grid_never_widens_past_the_legacy_ceiling(self, monkeypatch):
        """Safety: the fix may only ever REMOVE classes, never add one."""
        for exclude in ((), (2026,)):
            rows = _sync(monkeypatch, exclude_seasons=exclude)
            assert max(_seasons(rows)) <= 2026 + 3

    def test_empty_rosters_still_short_circuits(self, monkeypatch):
        """#220 clobber guard must survive the horizon change."""
        assert _sync(monkeypatch, roster_ids=[]) == []
