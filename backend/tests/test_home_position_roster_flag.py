"""Home position tile body tap (D-269, docs/plans/position-tile-tap/scope.md).

The flag is client-only. These pins hold the repo's flag rules: registered
with a False code default, shipped true in config/features.json, mirrored in
the three named fixtures, and not an env-forced (FTF_FLAGS) key. The
`home_tile_tapped` prop row (with `split`) is pinned by
test_analytics_taxonomy_home_hub.py.
"""
import json
from pathlib import Path

import backend.feature_flags as ff

REPO = Path(__file__).resolve().parents[2]
FLAG = "nav.home_position_roster"


def test_registered_with_false_code_default():
    assert FLAG in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS[FLAG] is False


def test_shipped_true_in_config_and_fixtures():
    assert json.loads((REPO / "config/features.json").read_text())[FLAG] is True
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[FLAG] is True, name


def test_close_via_home_back_is_documented_in_the_taxonomy():
    import backend.analytics_taxonomy as tax
    text = (REPO / "backend/analytics_taxonomy.py").read_text()
    assert "home_back" in text and "home_tile" in text and "position_roster" in text
    assert tax.CLIENT_EVENT_PROPS["league_team_closed"] == frozenset({"via", "dwell_ms", "rank"})
    assert tax.CLIENT_EVENT_PROPS["league_team_opened"] == frozenset(
        {"via", "rank", "basis", "subset", "filter_count"})
