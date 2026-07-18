"""Tests for backend/mfl_service.py — MFL league linking Phase 1.

Pure/offline: HTTP is injected via `_opener`; league data comes from the
recorded fixture mfl_league_snapshot_2026-07-17.json (bundle of the four
league-scoped exports, trimmed to 3 franchises from live public league 10005)
and the crosswalk from the re-cut DP snapshot fixture.
"""
import io
import json
import os
import urllib.error

import pytest

import backend.mfl_service as mfl
import backend.espn_service as es

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BUNDLE_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")


def _bundle():
    with open(BUNDLE_FIXTURE) as f:
        return json.load(f)


class _FakeResp:
    def __init__(self, text):
        self._b = text.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_by_type(bundle):
    """Dispatch a fetch to the right slice of the fixture bundle by TYPE=."""
    def _opener(request, timeout=None):
        url = request.full_url
        for t in ("league", "rosters", "futureDraftPicks", "players"):
            if f"TYPE={t}" in url:
                return _FakeResp(json.dumps(bundle[t]))
        return _FakeResp("{}")
    return _opener


def _opener_http_error(code):
    def _opener(request, timeout=None):
        raise urllib.error.HTTPError("http://mfl", code, "err", {}, io.BytesIO(b"{}"))
    return _opener


# ── host resolution (the wwwNN gotcha) ──────────────────────────────────────

def test_parse_host_from_url_normal_and_mangled():
    assert mfl.parse_host_from_url(
        "https://www48.myfantasyleague.com/2026/home/10005") == "www48.myfantasyleague.com"
    # MFL's own scheme-mangled homeURL (missing colon)
    assert mfl.parse_host_from_url(
        "https//www48.myfantasyleague.com/2026/home/10005") == "www48.myfantasyleague.com"
    assert mfl.parse_host_from_url("https://sleeper.com/leagues/123") is None


def test_parse_league_id_from_url():
    assert mfl.parse_league_id_from_url(
        "https://www48.myfantasyleague.com/2026/home/10005") == "10005"
    assert mfl.parse_league_id_from_url(
        "https://www47.myfantasyleague.com/2026/options?L=54321") == "54321"
    assert mfl.parse_league_id_from_url("garbage") is None


def test_resolve_host_reads_location():
    def _opener(request, timeout=None):
        # api host 302s to the league's real host; the injected opener returns
        # the Location value directly (see resolve_host's _opener contract).
        return "https://www48.myfantasyleague.com/2026/home/10005"
    assert mfl.resolve_host("10005", 2026, _opener=_opener) == "www48.myfantasyleague.com"


def test_resolve_host_no_redirect_is_not_found():
    def _opener(request, timeout=None):
        return ""      # no league → no host
    with pytest.raises(mfl.MflError) as ei:
        mfl.resolve_host("999999", 2026, _opener=_opener)
    assert ei.value.kind == "not_found"


def test_resolve_host_rejects_non_numeric():
    with pytest.raises(mfl.MflError) as ei:
        mfl.resolve_host("not-a-league", 2026)
    assert ei.value.kind == "input"


# ── fetch error mapping + cookie passthrough ────────────────────────────────

@pytest.mark.parametrize("code,kind", [(401, "auth"), (403, "auth"),
                                       (404, "not_found"), (500, "http")])
def test_fetch_error_mapping(code, kind):
    with pytest.raises(mfl.MflError) as ei:
        mfl.fetch_league_bundle("10005", 2026, "www48.myfantasyleague.com",
                                _opener=_opener_http_error(code))
    assert ei.value.kind == kind


def test_fetch_sends_cookie_and_ua():
    captured = {}

    def _opener(request, timeout=None):
        captured["ua"] = request.get_header("User-agent")
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({}))

    mfl.fetch_league_bundle("10005", 2026, "www48.myfantasyleague.com",
                            cookie="MFL_USER_ID=abc", _opener=_opener)
    assert "FantasyTradeFinder" in captured["ua"]
    assert captured["cookie"] == "MFL_USER_ID=abc"


def test_fetch_bundle_players_degrades_gracefully():
    # players export 500s → best-effort empty, other exports still returned
    bundle = _bundle()

    def _opener(request, timeout=None):
        url = request.full_url
        if "TYPE=players" in url:
            raise urllib.error.HTTPError(url, 500, "err", {}, io.BytesIO(b"{}"))
        for t in ("league", "rosters", "futureDraftPicks"):
            if f"TYPE={t}" in url:
                return _FakeResp(json.dumps(bundle[t]))
        return _FakeResp("{}")

    raw = mfl.fetch_league_bundle("10005", 2026, "www48.myfantasyleague.com", _opener=_opener)
    assert raw["players"] == {}
    assert raw["league"]


# ── parse ───────────────────────────────────────────────────────────────────

def test_parse_bundle_shape():
    parsed = mfl.parse_bundle(_bundle())
    assert parsed["league_id"] == "10005"
    assert parsed["name"].startswith("Masters Copper Dynasty")
    assert parsed["total_teams"] == 3
    assert len(parsed["franchises"]) == 3
    fr = parsed["franchises"][0]
    assert fr["franchise_id"] == "0001"
    assert fr["name"]
    # players carry (mfl_id, flipped "First Last" name, position)
    ids, names, poss = zip(*fr["players"])
    assert all(pid.isdigit() for pid in ids)
    assert any("," not in n for n in names)   # names were flipped
    # future picks stored
    assert len(parsed["future_picks"]) > 0
    assert set(parsed["future_picks"][0]) == {"franchise_id", "year", "round", "original_owner"}


def test_parse_bundle_normalises_single_item_dicts():
    # MFL returns a bare dict (not list) when a collection has one member.
    raw = {
        "league": {"league": {"id": "1", "name": "Solo",
                              "franchises": {"count": "1",
                                             "franchise": {"id": "0001", "name": "Only"}}}},
        "rosters": {"rosters": {"franchise": {"id": "0001",
                                              "player": {"id": "15281", "status": "ROSTER"}}}},
        "players": {"players": {"player": {"id": "15281", "name": "Chase, Ja'Marr",
                                          "position": "WR"}}},
        "futureDraftPicks": {"futureDraftPicks": {"franchise": {
            "id": "0001", "futureDraftPick": {"year": "2027", "round": "1",
                                              "originalPickFor": "0001"}}}},
    }
    parsed = mfl.parse_bundle(raw)
    assert len(parsed["franchises"]) == 1
    assert parsed["franchises"][0]["players"] == [("15281", "Ja'Marr Chase", "WR")]
    assert len(parsed["future_picks"]) == 1


def test_flip_name():
    assert mfl._flip_name("Chase, Ja'Marr") == "Ja'Marr Chase"
    assert mfl._flip_name("Bills, Buffalo") == "Buffalo Bills"
    assert mfl._flip_name("Madonna") == "Madonna"


# ── crosswalk mapping ───────────────────────────────────────────────────────

def test_map_franchises_full_match_rate():
    parsed = mfl.parse_bundle(_bundle())
    xw = es.load_crosswalk(XWALK_FIXTURE)
    out = mfl.map_franchises(parsed, xw)
    r = out["report"]
    # 24 skill players across 3 franchises, all resolve by mfl_id
    assert r["pool_players"] == 24
    assert r["matched_by_id"] == 24
    assert r["matched_by_name"] == 0
    assert r["unmatched"] == []
    assert r["match_rate"] == 1.0
    # team defenses are out of pool, not failures
    assert r["out_of_pool"] == 3
    assert all(sid.isdigit() for ids in out["rosters"].values() for sid in ids)
