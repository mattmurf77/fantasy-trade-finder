"""#207 — per-league rookie-draft detection matrix.

Every row of the plan's detection matrix, plus the three cases a naive
"just read `drafts[].status`" implementation gets wrong:

  1. `pre_draft` + a full rookie class on rosters  → DRAFTED (rosters veto)
  2. an EMPTY drafts list                          → UNKNOWN, not NOT_DRAFTED
  3. `complete` on a startup-shaped (20+ round)    → says nothing about the
     draft                                            rookie draft

...and the fail-safe: anything short of a positive `drafted` keeps
current-year picks visible.

Pure unit tests — the module takes already-fetched payloads by design, so no
network, no DB, no Flask.
"""
import pytest

from backend import draft_status as ds


# ── helpers ────────────────────────────────────────────────────────────────

def _draft(status="pre_draft", season=2026, rounds=4, last_picked=None):
    return {"draft_id": "d1", "status": status, "season": str(season),
            "type": "linear", "last_picked": last_picked,
            "settings": {"rounds": rounds, "teams": 12, "player_type": 0}}


def _mfl(made, total, franchise_count=12):
    picks = []
    for i in range(total):
        picks.append({"round": f"{i // franchise_count + 1:02d}",
                      "pick": f"{i % franchise_count + 1:02d}",
                      "franchise": f"{i % franchise_count + 1:04d}",
                      "player": "17472" if i < made else "",
                      "timestamp": "1785589226" if i < made else ""})
    return {"draftResults": {"draftUnit": {"unit": "LEAGUE",
                                           "draftPick": picks}}}


_FULL_CLASS = ds.rosters_verdict(rookies_rostered=57, teams_with_rookie=12,
                                 league_size=12)
_NO_ROOKIES = ds.rosters_verdict(rookies_rostered=0, teams_with_rookie=0,
                                 league_size=12)


# ── rookie row test ────────────────────────────────────────────────────────

def test_rookie_year_is_the_primary_class_test():
    assert ds.is_rookie_row("2026", 0, "ARI", 2026) is True
    assert ds.is_rookie_row("2025", 1, "TEN", 2026) is False
    # years_exp is NOT a class field — a 2023 UDFA can read years_exp == 1.
    assert ds.is_rookie_row("2023", 1, "BUF", 2026) is False


def test_rookie_year_falls_back_to_years_exp_plus_team():
    assert ds.is_rookie_row(None, 0, "SF", 2026) is True
    # Teamless prospect (pre-NFL-draft window) is not a rostered rookie.
    assert ds.is_rookie_row(None, 0, None, 2026) is False
    assert ds.is_rookie_row(None, 2, "SF", 2026) is False
    # Sleeper's bogus "0" rookie_year falls through to the proxy.
    assert ds.is_rookie_row("0", 0, "SF", 2026) is True


# ── rosters heuristic thresholds ───────────────────────────────────────────

def test_rosters_heuristic_at_the_exact_boundary():
    """Exactly N rookies across exactly ceil(N/2) teams clears the bar."""
    v = ds.rosters_verdict(rookies_rostered=12, teams_with_rookie=6,
                           league_size=12)
    assert (v.status, v.confidence) == (ds.DRAFTED, ds.MEDIUM)


def test_rosters_heuristic_one_under_each_threshold_abstains():
    assert ds.rosters_verdict(11, 6, 12).status == ds.UNKNOWN     # count short
    assert ds.rosters_verdict(12, 5, 12).status == ds.UNKNOWN     # spread short


def test_rosters_heuristic_odd_league_size_uses_ceiling():
    # N=11 → ceil(11/2) = 6 teams required.
    assert ds.rosters_verdict(11, 6, 11).status == ds.DRAFTED
    assert ds.rosters_verdict(11, 5, 11).status == ds.UNKNOWN


def test_rosters_heuristic_zero_rookies_is_not_drafted_medium():
    v = ds.rosters_verdict(0, 0, 12)
    assert (v.status, v.confidence) == (ds.NOT_DRAFTED, ds.MEDIUM)


def test_rosters_heuristic_abstains_when_player_table_is_stale():
    """Zero *classifiable* rookies but a big unknown-id tail means our player
    snapshot is stale, not that the league has no rookies."""
    assert ds.rosters_verdict(0, 0, 12, unclassifiable=30).status == ds.UNKNOWN


def test_rosters_heuristic_never_exceeds_medium():
    assert ds.rosters_verdict(200, 12, 12).confidence == ds.MEDIUM


# ── Sleeper signal ordering ────────────────────────────────────────────────

def test_sleeper_complete_with_last_picked_is_drafted_high():
    v = ds.sleeper_verdict([_draft("complete", last_picked=1777947157960)],
                           2026, _FULL_CLASS)
    assert (v.status, v.confidence, v.source) == (ds.DRAFTED, ds.HIGH,
                                                  ds.SRC_SLEEPER)


def test_sleeper_complete_with_zero_picks_made_is_not_trusted():
    """A commissioner flipping an empty draft to `complete` must not hide
    picks — `last_picked` is the corroborator."""
    v = ds.sleeper_verdict([_draft("complete", last_picked=None)], 2026,
                           _NO_ROOKIES)
    assert v.status == ds.NOT_DRAFTED
    assert v.source == ds.SRC_ROSTERS


def test_sleeper_pre_draft_with_empty_rosters_is_not_drafted_high():
    v = ds.sleeper_verdict([_draft("pre_draft")], 2026, _NO_ROOKIES)
    assert (v.status, v.confidence, v.source) == (ds.NOT_DRAFTED, ds.HIGH,
                                                  ds.SRC_SLEEPER)


def test_sleeper_pre_draft_but_full_rookie_class_rosters_win():
    """CONFLICT CASE 1 — off-platform / imported draft. A status-only rule
    returns NOT_DRAFTED here and is wrong."""
    v = ds.sleeper_verdict([_draft("pre_draft")], 2026, _FULL_CLASS)
    assert (v.status, v.confidence, v.source) == (ds.DRAFTED, ds.MEDIUM,
                                                  ds.SRC_ROSTERS)
    assert v.evidence["veto"] == "rosters_show_rookie_class"


def test_sleeper_drafting_status_also_yields_to_the_roster_veto():
    v = ds.sleeper_verdict([_draft("drafting")], 2026, _FULL_CLASS)
    assert v.status == ds.DRAFTED
    v2 = ds.sleeper_verdict([_draft("drafting")], 2026, _NO_ROOKIES)
    assert v2.status == ds.NOT_DRAFTED


def test_sleeper_complete_with_no_rookies_rostered_is_downgraded():
    """Platform still wins, but the combination is near-impossible — flag it
    as an anomaly and drop to medium."""
    v = ds.sleeper_verdict([_draft("complete", last_picked=1)], 2026,
                           _NO_ROOKIES)
    assert (v.status, v.confidence) == (ds.DRAFTED, ds.MEDIUM)
    assert v.evidence["anomaly"] == "no_rookies_rostered"


def test_sleeper_empty_drafts_list_is_ambiguous_not_not_drafted():
    """CONFLICT CASE 2 — `[]` means 'flake OR no draft object'. A status-only
    rule reads it as 'no complete draft ⇒ not drafted'."""
    assert ds.sleeper_verdict([], 2026, None).status == ds.UNKNOWN
    assert ds.sleeper_verdict(None, 2026, None).status == ds.UNKNOWN
    # ...and it hands off to the heuristic when rosters ARE available.
    v = ds.sleeper_verdict([], 2026, _FULL_CLASS)
    assert (v.status, v.source) == (ds.DRAFTED, ds.SRC_ROSTERS)


def test_sleeper_startup_shaped_complete_draft_does_not_settle_rookie_picks():
    """CONFLICT CASE 3 — a 28-round startup completing says nothing about a
    pending rookie draft. A status-only rule hides the picks."""
    startup = _draft("complete", rounds=28, last_picked=1)
    assert ds.sleeper_verdict([startup], 2026, _NO_ROOKIES).status == ds.NOT_DRAFTED
    assert ds.sleeper_verdict([startup], 2026, _FULL_CLASS).status == ds.DRAFTED
    assert ds.sleeper_verdict([startup], 2026, None).status == ds.UNKNOWN


def test_sleeper_ignores_other_seasons_and_iterates_all_entries():
    drafts = [_draft("complete", season=2025, last_picked=1),
              _draft("pre_draft", season=2026)]
    assert ds.sleeper_verdict(drafts, 2026, _NO_ROOKIES).status == ds.NOT_DRAFTED
    # Season coercion: Sleeper serves season as a STRING on both objects.
    assert ds.sleeper_verdict(drafts, "2026", _NO_ROOKIES).status == ds.NOT_DRAFTED


def test_sleeper_no_current_season_draft_falls_back():
    drafts = [_draft("complete", season=2025, last_picked=1)]
    assert ds.sleeper_verdict(drafts, 2026, None).status == ds.UNKNOWN
    assert ds.sleeper_verdict(drafts, 2026, _NO_ROOKIES).status == ds.NOT_DRAFTED


def test_sleeper_missing_rounds_is_treated_as_possibly_rookie():
    d = _draft("complete", last_picked=1)
    d["settings"] = {}
    assert ds.sleeper_verdict([d], 2026, _FULL_CLASS).status == ds.DRAFTED


def test_sleeper_tolerates_junk_entries():
    assert ds.sleeper_verdict(["nope", None, {}], 2026, None).status == ds.UNKNOWN


# ── MFL signal ─────────────────────────────────────────────────────────────

def test_mfl_full_grid_is_drafted_high():
    v = ds.mfl_verdict(_mfl(made=48, total=48), 12, _FULL_CLASS)
    assert (v.status, v.confidence, v.source) == (ds.DRAFTED, ds.HIGH,
                                                  ds.SRC_MFL)
    assert v.evidence["made"] == v.evidence["total"] == 48


def test_mfl_partial_grid_is_not_drafted():
    """Unmade picks still exist as assets — in progress counts as NOT done."""
    v = ds.mfl_verdict(_mfl(made=20, total=48), 12, None)
    assert (v.status, v.confidence) == (ds.NOT_DRAFTED, ds.HIGH)


def test_mfl_empty_grid_is_not_drafted():
    v = ds.mfl_verdict(_mfl(made=0, total=60), 12, None)
    assert (v.status, v.confidence) == (ds.NOT_DRAFTED, ds.HIGH)


def test_mfl_startup_sized_grid_falls_back_to_the_heuristic():
    # 264 picks / 12 franchises = 22 rounds ⇒ startup, not a rookie draft.
    assert ds.mfl_verdict(_mfl(264, 264), 12, _NO_ROOKIES).status == ds.NOT_DRAFTED
    assert ds.mfl_verdict(_mfl(264, 264), 12, None).status == ds.UNKNOWN


def test_mfl_aggregates_across_draft_units():
    """A league drafting by division serves draftUnit as a LIST."""
    unit_a = _mfl(24, 24, 6)["draftResults"]["draftUnit"]
    unit_b = _mfl(0, 24, 6)["draftResults"]["draftUnit"]
    payload = {"draftResults": {"draftUnit": [unit_a, unit_b]}}
    v = ds.mfl_verdict(payload, 12, None)
    assert v.evidence == {"made": 24, "total": 48, "rounds": 4.0,
                          "league_size": 12}
    assert v.status == ds.NOT_DRAFTED


def test_mfl_export_unavailable_falls_back():
    assert ds.mfl_verdict(None, 12, None).status == ds.UNKNOWN
    assert ds.mfl_verdict(None, 12, _FULL_CLASS).status == ds.DRAFTED
    assert ds.mfl_verdict({}, 12, None).status == ds.UNKNOWN


def test_mfl_empty_pre_populated_grid_yields_to_the_roster_veto():
    v = ds.mfl_verdict(_mfl(0, 48), 12, _FULL_CLASS)
    assert (v.status, v.source) == (ds.DRAFTED, ds.SRC_ROSTERS)


# ── platform dispatch ──────────────────────────────────────────────────────

def test_detect_dispatches_by_platform():
    complete = [_draft("complete", last_picked=1)]
    assert ds.detect("sleeper", 2026, 12, sleeper_drafts=complete).status == ds.DRAFTED
    assert ds.detect("mfl", 2026, 12, mfl_draft_results=_mfl(48, 48)).status == ds.DRAFTED
    # Sleeper payload on an MFL league must not leak across.
    assert ds.detect("mfl", 2026, 12, sleeper_drafts=complete).status == ds.UNKNOWN


def test_detect_espn_and_fleaflicker_are_heuristic_only():
    complete = [_draft("complete", last_picked=1)]
    for plat in ("espn", "fleaflicker"):
        assert ds.detect(plat, 2026, 12, sleeper_drafts=complete).status == ds.UNKNOWN
        assert ds.detect(plat, 2026, 12, rosters=_FULL_CLASS).status == ds.DRAFTED
        assert ds.detect(plat, 2026, 12, rosters=_NO_ROOKIES).status == ds.NOT_DRAFTED


def test_detect_defaults_null_platform_to_sleeper():
    complete = [_draft("complete", last_picked=1)]
    assert ds.detect(None, 2026, 12, sleeper_drafts=complete).status == ds.DRAFTED


# ── the fail-safe ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [ds.UNKNOWN, ds.NOT_DRAFTED])
def test_fail_safe_keeps_current_year_picks_visible(status):
    assert ds.current_year_picks_visible(
        ds.DraftStatus(status, ds.LOW, ds.SRC_NONE)) is True


def test_fail_safe_covers_a_missing_verdict_entirely():
    assert ds.current_year_picks_visible(None) is True


def test_only_a_positive_drafted_verdict_hides_current_year_picks():
    assert ds.current_year_picks_visible(
        ds.DraftStatus(ds.DRAFTED, ds.MEDIUM, ds.SRC_ROSTERS)) is False
