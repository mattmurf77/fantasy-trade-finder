"""Roster-first setup (flag `trades.roster_setup`, 2026-11-10) — taxonomy.

Spec: docs/plans/roster-first-trade-setup/analytics.md §2-§3; addendum
docs/business/analytics/2026-11-10-roster-setup-events.md. Registered in the
SAME commit as the mobile emitters, because the ingest allowlist is
default-deny behind a 200: an unregistered name is counted and dropped, and
an unregistered prop is stripped while the response still reports
dropped == 0. Same shape as test_analytics_taxonomy_home_hub.py.

2026-11-11: `roster_setup_tiers_saved` (flag `trades.roster_tier_rank`,
docs/plans/roster-first-trade-setup/scope-tier-rank.md §1.7/§4) joins as an
INTENT event, and `roster_setup_skipped.stage` widens with `tiers` (a value,
not a prop, so the prop rows below are unchanged for it).

Two of the seven are NON_INTENT on purpose (INTENT is derived by subtraction):
  * roster_setup_shown   — an impression the user did not ask for on the
                           first-pass entry;
  * roster_setup_skipped — a dismissal/terminator (quickset_abandoned class).
"""

_PROPS: dict[str, set[str]] = {
    "roster_setup_shown": {"league_id", "entry", "roster_size", "pick_count",
                           "prefilled_count"},
    "roster_setup_toggles_done": {"league_id", "entry", "move_count", "keep_count",
                                  "open_count", "pick_move_count", "pick_keep_count",
                                  "changed_count", "duration_ms"},
    "roster_setup_rank_saved": {"league_id", "position", "players_ranked",
                                "players_total"},
    "roster_setup_completed": {"league_id", "entry", "ranked_positions", "changed",
                               "duration_ms"},
    "roster_setup_skipped": {"league_id", "entry", "stage"},
    "roster_setup_prompt_tapped": {"league_id", "surface", "new_asset_count"},
    "roster_setup_tiers_saved": {"league_id", "entry", "moved_count",
                                 "moved_up_count", "moved_down_count",
                                 "players_total", "positions_saved", "duration_ms"},
}

_NON_INTENT = {"roster_setup_shown", "roster_setup_skipped"}


def test_roster_setup_names_are_allowlisted_client_events():
    import backend.analytics_taxonomy as tax
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax.SERVER_FIRED_EVENTS)
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)


def test_roster_setup_prop_rows_are_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    import backend.analytics_taxonomy as tax
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name


def test_roster_setup_carries_no_device_platform_prop():
    import backend.analytics_taxonomy as tax
    for name in _PROPS:
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name


def test_roster_setup_intent_split():
    import backend.analytics_queries as q
    for name in _PROPS:
        if name in _NON_INTENT:
            assert name in q.NON_INTENT_EVENTS, name
            assert name not in q.INTENT_EVENTS, name
        else:
            assert name not in q.NON_INTENT_EVENTS, name


def test_roster_setup_reuses_prompt_shown_without_a_new_prop():
    """The return card's impression widens prompt_shown's `surface` enum
    (`roster_setup_card`); it adds no prop and no event."""
    import backend.analytics_taxonomy as tax
    assert tax.CLIENT_EVENT_PROPS["prompt_shown"] == frozenset({"surface"})


def test_roster_setup_tiers_saved_is_intent():
    """The tier page's save is a deliberate board write: INTENT, so it must be
    absent from NON_INTENT_EVENTS and present in INTENT_EVENTS."""
    import backend.analytics_queries as q
    assert "roster_setup_tiers_saved" not in q.NON_INTENT_EVENTS
    assert "roster_setup_tiers_saved" in q.INTENT_EVENTS


def test_roster_setup_skipped_stage_enum_documents_tiers():
    """`stage` is a closed enum documented beside the prop rows; the tier
    page's skip sends stage:'tiers'."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "analytics_taxonomy.py").read_text()
    assert "stage   ∈ toggles | rank | tiers" in src
