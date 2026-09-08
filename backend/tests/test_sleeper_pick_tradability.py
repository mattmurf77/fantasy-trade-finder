"""#428 — a spent current-season pick must never reach Sleeper's propose.

Operator report (2026-09-08, v1.17.2 build 154, TradesHome): "Draft pick
trading on sleeper still doesn't work." The 2026 rookie draft had run on
2026-08-26; the league's grid still carried 2026 rows (a flaked `/drafts`
read re-populates them — investigation §3.1); Sleeper's `traded_picks` still
listed the season, so the #413 holder check passed; Sleeper answered
"These draft picks cannot be traded." (prd.md §2).

Two things are pinned here:

  1. The ONE tradability predicate — `draft_status.sleeper_pick_window` /
     `sleeper_pick_tradable` — sits beside `pick_horizon` (the window rule it
     reuses, #355 / D-089) rather than in test_pick_horizon.py so the #428
     guard has one home.
  2. `POST /api/trades/validate`'s Sleeper branch reports a spent pick as the
     blocking advisory `pick_untradable` (the advisory mirror of the propose
     route's 422 `sleeper_pick_untradable`, tested in
     test_sleeper_write_route.py). The client fixture is the #180 file's own —
     imported, not copied, so the two files cannot drift on the Sleeper stubs.
"""
import json
from unittest.mock import MagicMock, patch

import backend.server as server
from backend import draft_status as ds

# Re-exported so pytest discovers the fixture in this module's namespace.
from backend.tests.test_trade_send_validate import (   # noqa: F401
    client, _validate, _codes, LEAGUE, GRID, TRADED, MY_2027_2ND, META,
)

# Production fixture shape (prd.md §5): FFV3 on 2026-09-08.
DRAFTS_DONE = [{"draft_id": "d1", "season": "2026", "status": "complete",
                "type": "linear", "last_picked": 1787707582674,
                "settings": {"rounds": 4}}]
DRAFTS_PRE = [{"draft_id": "d1", "season": "2026", "status": "pre_draft",
               "type": "linear", "settings": {"rounds": 4}}]
TRADED_2026 = [{"season": "2026", "round": 4, "roster_id": 11, "owner_id": 1,
                "previous_owner_id": 11}]
TRADED_2026_2028 = TRADED_2026 + [
    {"season": "2028", "round": 1, "roster_id": 3, "owner_id": 1,
     "previous_owner_id": 3}]
CACHED_DRAFTED = ds.DraftStatus(ds.DRAFTED, ds.HIGH, ds.SRC_SLEEPER)
# A first-season dynasty league after its startup draft (rounds >= 15 —
# `_is_rookie_shaped` is False). G-428 QA round 1 (A F-1 / B F-2): the class
# is consumed all the same, so the send window must start the following class.
STARTUP_DONE = [{"draft_id": "s1", "season": "2026", "status": "complete",
                 "type": "snake", "last_picked": 1787707582674,
                 "settings": {"rounds": 25}}]


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------

class TestSleeperPickWindow:

    def test_completed_draft_seasons_reads_only_complete_current_or_later(self):
        drafts = DRAFTS_DONE + [
            {"draft_id": "d0", "season": "2025", "status": "complete",
             "settings": {"rounds": 4}},                       # last year — irrelevant
            {"draft_id": "d2", "season": "2027", "status": "pre_draft",
             "settings": {"rounds": 4}},                       # not complete
            {"draft_id": "s2", "season": "2027", "status": "complete",
             "settings": {"rounds": 25}},                      # startup-shaped — still counts
        ]
        assert ds.completed_draft_seasons(drafts, 2026) == {2026, 2027}

    def test_completed_draft_seasons_is_shape_blind(self):
        """G-428 QA round 1 (A F-1 / B F-2): a completed STARTUP draft consumes
        the current class too — the pre-#428 sync excluded any `complete`
        current-season draft regardless of shape, and so must this."""
        assert ds.completed_draft_seasons(STARTUP_DONE, 2026) == {2026}
        # Shape-less entries (no `settings`) count as well, as they always did.
        assert ds.completed_draft_seasons(
            [{"season": "2026", "status": "complete"}], 2026) == {2026}

    def test_sleeper_pick_window_post_startup_starts_next_class(self):
        assert ds.sleeper_pick_window(2026, STARTUP_DONE, TRADED_2026) == (2027, 2029)
        assert ds.sleeper_pick_tradable(2026, ds.sleeper_pick_window(2026, STARTUP_DONE)) is False

    def test_sleeper_pick_window_post_draft_is_next_three_classes(self):
        """Spent-season rows in traded_picks must NOT widen the window back
        onto the spent class — observed seasons only widen forward."""
        assert ds.sleeper_pick_window(2026, DRAFTS_DONE, TRADED_2026_2028) == (2027, 2029)

    def test_sleeper_pick_window_pre_draft_anchors_current(self):
        assert ds.sleeper_pick_window(2026, DRAFTS_PRE, TRADED_2026) == (2026, 2028)

    def test_sleeper_pick_window_flake_with_cached_drafted_excludes_current(self):
        """D-189 — `/drafts` flaked ([]) but the #207 cached verdict is a
        positive `drafted`: corroborated unknown excludes the current season."""
        assert ds.sleeper_pick_window(2026, [], TRADED_2026,
                                      cached_verdict=CACHED_DRAFTED) == (2027, 2029)

    def test_sleeper_pick_window_flake_without_verdict_abstains(self):
        """The D-089 fail-safe survives uncorroborated: a flake with no
        verdict (or a non-positive one) excludes nothing."""
        assert ds.sleeper_pick_window(2026, [], TRADED_2026) == (2026, 2028)
        for v in (ds.DraftStatus(ds.UNKNOWN, ds.LOW), ds.DraftStatus(ds.NOT_DRAFTED, ds.HIGH)):
            assert ds.sleeper_pick_window(2026, [], TRADED_2026, cached_verdict=v) == (2026, 2028)

    def test_cached_verdict_never_overrides_a_live_drafts_read(self):
        """Live `/drafts` wins whenever it answers — a stale cached `drafted`
        cannot hide picks a pre_draft read says still exist."""
        assert ds.sleeper_pick_window(2026, DRAFTS_PRE, (),
                                      cached_verdict=CACHED_DRAFTED) == (2026, 2028)

    def test_sleeper_pick_window_unknown_season_is_none(self):
        assert ds.sleeper_pick_window(None, DRAFTS_DONE) is None
        assert ds.sleeper_pick_window("", DRAFTS_DONE) is None

    def test_sleeper_pick_tradable(self):
        win = (2027, 2029)
        assert ds.sleeper_pick_tradable(2026, win) is False
        assert ds.sleeper_pick_tradable("2027", win) is True
        assert ds.sleeper_pick_tradable(2029, win) is True
        assert ds.sleeper_pick_tradable(2030, win) is False
        # None window = abstain: never blocks.
        assert ds.sleeper_pick_tradable(2026, None) is True
        # Garbage season abstains too (the grid lookup already proved the row).
        assert ds.sleeper_pick_tradable("x", win) is True


# ---------------------------------------------------------------------------
# POST /api/trades/validate — Sleeper branch
# ---------------------------------------------------------------------------

SPENT_2026_4TH = f"{LEAGUE}_2026_4_11"
GRID_WITH_SPENT = GRID + [
    {"pick_id": SPENT_2026_4TH, "season": 2026, "round": 4, "original_roster_id": "11"},
]


def _with_pick_truth(grid, traded, drafts):
    # The #180 META carries no `season` (the window abstains without one), so
    # the league meta is re-patched here with FFV3's 2026.
    return [patch.object(server, "_fetch_sleeper_league_meta",
                         lambda lid: {**json.loads(json.dumps(META)), "season": "2026"}),
            patch.object(server, "load_draft_picks",
                         lambda lid, *a, **k: json.loads(json.dumps(grid))),
            patch.object(server, "_fetch_sleeper_traded_picks",
                         lambda lid: json.loads(json.dumps(traded))),
            patch.object(server, "_fetch_sleeper_drafts",
                         lambda lid: json.loads(json.dumps(drafts)))]


def test_spent_current_season_pick_flags_pick_untradable(client):
    """V-7 — the #428 repro on the pre-flight: roster 11's 2026 4th, held by
    me per traded_picks, in a league whose 2026 draft is complete → blocking
    `pick_untradable`, with the season window in the copy."""
    c, token = client
    patches = _with_pick_truth(GRID_WITH_SPENT, TRADED + TRADED_2026, DRAFTS_DONE)
    for p in patches:
        p.start()
    try:
        r = _validate(c, token, give_player_ids=[SPENT_2026_4TH])
    finally:
        for p in reversed(patches):
            p.stop()
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _codes(r) == ["pick_untradable"]
    w = r.get_json()["warnings"][0]
    assert w["severity"] == "blocking"
    assert "1 draft pick " in w["message"]
    assert "2026" in w["message"] and "2027–2029" in w["message"]


def test_in_window_pick_has_no_untradable_warning(client):
    """V-8 — my 2027 2nd under the same completed 2026 draft stays clean."""
    c, token = client
    patches = _with_pick_truth(GRID_WITH_SPENT, TRADED + TRADED_2026, DRAFTS_DONE)
    for p in patches:
        p.start()
    try:
        r = _validate(c, token, give_player_ids=[MY_2027_2ND])
    finally:
        for p in reversed(patches):
            p.stop()
    assert r.get_json()["warnings"] == []


def test_validate_drafts_flake_without_verdict_does_not_flag(client):
    """V-9 — `/drafts` → [] and no cached verdict: the window abstains on
    the spent class (D-089 fail-safe); Sleeper stays the final authority."""
    c, token = client
    patches = _with_pick_truth(GRID_WITH_SPENT, TRADED + TRADED_2026, [])
    for p in patches:
        p.start()
    try:
        r = _validate(c, token, give_player_ids=[SPENT_2026_4TH])
    finally:
        for p in reversed(patches):
            p.stop()
    assert r.get_json()["warnings"] == []


def test_pick_free_validate_makes_no_drafts_fetch(client):
    """V-10 — R-4/R-12 of #413 stand: a pick-free trade never reads `/drafts`."""
    c, token = client
    drafts_mock = MagicMock(return_value=DRAFTS_DONE)
    with patch.object(server, "_fetch_sleeper_drafts", drafts_mock):
        r = _validate(c, token)
    assert r.get_json()["warnings"] == []
    drafts_mock.assert_not_called()
