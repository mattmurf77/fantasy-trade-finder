"""One Home control (D-276, docs/plans/home-return-unify/scope.md).

`nav.home_return_unified` is client-only and takes effect only together with
`nav.home_return` (D-275). These pins hold the repo's flag rules, as
test_nav_continuity_flags.py does for D-275: registered with a False code
default, shipped true in config/features.json with its comment, mirrored in
the three named fixtures, not env-forced (FTF_FLAGS), and the client's
compiled default agrees with config (a first paint that disagrees with the
fetched map would flip the Home control on the second paint).
"""
import json
from pathlib import Path

import backend.feature_flags as ff

REPO = Path(__file__).resolve().parents[2]
FLAG = "nav.home_return_unified"


def test_registered_with_false_code_default():
    assert FLAG in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS[FLAG] is False


def test_shipped_true_in_config_and_fixtures():
    config = json.loads((REPO / "config/features.json").read_text())
    assert config[FLAG] is True
    assert "_comment_nav_home_return_unified" in config
    # Only meaningful together with nav.home_return, which ships on too.
    assert config["nav.home_return"] is True
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[FLAG] is True, name
        assert fixture["nav.home_return"] is True, name


def test_not_env_forced():
    # Never added to the FTF_FLAGS env override (render.yaml is where a
    # deploy would set it): config/features.json is the one shipped value.
    assert FLAG not in (REPO / "render.yaml").read_text()


def test_client_compiled_default_matches_config():
    src = (REPO / "mobile/src/state/useFeatureFlags.ts").read_text()
    assert f"  '{FLAG}': true,\n" in src
