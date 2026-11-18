"""Home return control + navigation continuity fixes (D-275,
docs/plans/nav-continuity/scope.md).

Both flags are client-only. These pins hold the repo's flag rules: registered
with a False code default, shipped true in config/features.json, mirrored in
the three named fixtures, not env-forced (FTF_FLAGS), and the client's
compiled default agrees with config (a first paint that disagrees with the
fetched map flips the feature on the second paint).
"""
import json
from pathlib import Path

import pytest

import backend.feature_flags as ff

REPO = Path(__file__).resolve().parents[2]
FLAGS = ("nav.home_return", "nav.continuity")


@pytest.mark.parametrize("flag", FLAGS)
def test_registered_with_false_code_default(flag):
    assert flag in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS[flag] is False


@pytest.mark.parametrize("flag", FLAGS)
def test_shipped_true_in_config_and_fixtures(flag):
    config = json.loads((REPO / "config/features.json").read_text())
    assert config[flag] is True
    assert f"_comment_{flag.replace('.', '_')}" in config
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[flag] is True, name


@pytest.mark.parametrize("flag", FLAGS)
def test_not_env_forced(flag):
    # Never added to the FTF_FLAGS env override (render.yaml is where a
    # deploy would set it): config/features.json is the one shipped value.
    assert flag not in (REPO / "render.yaml").read_text()


@pytest.mark.parametrize("flag", FLAGS)
def test_client_compiled_default_matches_config(flag):
    src = (REPO / "mobile/src/state/useFeatureFlags.ts").read_text()
    assert f"  '{flag}': true,\n" in src
