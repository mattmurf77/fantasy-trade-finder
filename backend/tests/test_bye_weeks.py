"""Tests for backend/outlook/bye_weeks.py — nflverse schedule -> bye-week
derivation (feedback #169, evaluated bye-week multiplier).

Offline only: the committed fixture `fixtures/nflverse_games_2022_2026.csv`
(a season-filtered slice of the real nflverse/nfldata `games.csv`, captured
2026-08-09) stands in for the live fetch. HTTP is injected via `_opener`,
same pattern as `espn_service.fetch_crosswalk` / `test_espn_service.py`.
"""

from __future__ import annotations

import io
import os
import urllib.error

import pytest

import backend.outlook.bye_weeks as bw

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "nflverse_games_2022_2026.csv"
)


@pytest.fixture(autouse=True)
def _clean_cache():
    bw.reset_cache()
    yield
    bw.reset_cache()


class _FakeResp:
    def __init__(self, text: str):
        self._b = text.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_returning(text: str, calls: list | None = None):
    def _opener(request, timeout=None):
        if calls is not None:
            calls.append(1)
        return _FakeResp(text)
    return _opener


def _opener_raising(exc: Exception):
    def _opener(request, timeout=None):
        raise exc
    return _opener


def _read_fixture() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# derive_byes — the pure derivation
# ---------------------------------------------------------------------------

def test_known_2025_bye_philadelphia_week_9():
    """Ground truth: the Eagles' actual 2025 bye was week 9 (independently
    verifiable against the real NFL schedule) — the load-bearing assertion
    that the derivation logic (present-in-neither-home-nor-away => bye) is
    correct, not just internally consistent."""
    byes = bw.derive_byes(_read_fixture())
    assert byes["2025"]["PHI"] == 9


def test_known_2025_bye_rams_week_8_via_la_alias():
    """The Rams play as nflverse "LA" but Sleeper's player.team field (and
    therefore player_team maps fed into bye_multiplier) uses "LAR" — the
    alias must resolve both directions to the same team."""
    byes = bw.derive_byes(_read_fixture())
    assert byes["2025"]["LAR"] == 8
    assert "LA" not in byes["2025"]  # normalized away, not left as a dupe key


def test_every_team_has_exactly_one_bye_per_season():
    byes = bw.derive_byes(_read_fixture())
    for season, by_team in byes.items():
        assert len(by_team) == 32, f"{season}: expected 32 teams, got {len(by_team)}"
        for team, week in by_team.items():
            assert 1 <= week <= 18, f"{season} {team}: implausible bye week {week}"


def test_derive_byes_ignores_non_regular_season_games():
    # A postseason game where a team that never appears in REG shows up must
    # not suppress that team's derived bye (POST rows are simply skipped).
    csv_text = (
        "season,game_type,week,home_team,away_team\n"
        "2030,REG,1,AAA,BBB\n"
        "2030,REG,2,AAA,CCC\n"
        "2030,POST,19,BBB,CCC\n"
    )
    byes = bw.derive_byes(csv_text)
    # AAA plays every week -> no bye. BBB misses week 2 -> bye week 2.
    # CCC misses week 1 -> bye week 1.
    assert byes["2030"] == {"BBB": 2, "CCC": 1}


def test_team_alias_normalizes_la_to_lar():
    csv_text = (
        "season,game_type,week,home_team,away_team\n"
        "2030,REG,1,LA,BBB\n"
        "2030,REG,2,CCC,BBB\n"
    )
    byes = bw.derive_byes(csv_text)
    assert byes["2030"]["LAR"] == 2  # LA didn't play week 2 -> bye, keyed as LAR
    assert byes["2030"]["CCC"] == 1


# ---------------------------------------------------------------------------
# load_snapshot / cache / fallback
# ---------------------------------------------------------------------------

def test_load_snapshot_matches_derive_byes_on_same_fixture():
    assert bw.load_snapshot() == bw.derive_byes(_read_fixture())


def test_get_byes_fetch_success_is_cached_until_ttl():
    calls: list = []
    text = _read_fixture()
    result1 = bw.get_byes(_opener=_opener_returning(text, calls))
    result2 = bw.get_byes(_opener=_opener_returning(text, calls))
    assert result1 == result2
    assert len(calls) == 1, "second call within TTL must reuse the cache, not re-fetch"


def test_get_byes_fetch_failure_falls_back_to_snapshot():
    result = bw.get_byes(_opener=_opener_raising(urllib.error.URLError("boom")))
    assert result == bw.load_snapshot()


def test_get_byes_keeps_last_good_copy_on_later_failure():
    text = _read_fixture()
    good = bw.get_byes(_opener=_opener_returning(text))
    # Force a re-fetch attempt (TTL bypass) that fails; the in-memory copy
    # from the successful call must survive.
    bw._cache_fetched_at = 0.0  # noqa: SLF001 — test-only TTL bypass
    again = bw.get_byes(_opener=_opener_raising(urllib.error.URLError("boom")))
    assert again == good


def test_team_bye_week_convenience_accessor():
    text = _read_fixture()
    assert bw.team_bye_week("2025", "PHI", _opener=_opener_returning(text)) == 9
    assert bw.team_bye_week("2025", "LA", _opener=_opener_returning(text)) == 8
    assert bw.team_bye_week("2099", "PHI", _opener=_opener_returning(text)) is None


def test_fetch_byes_raises_on_network_failure():
    with pytest.raises(urllib.error.URLError):
        bw.fetch_byes(_opener=_opener_raising(urllib.error.URLError("boom")))
