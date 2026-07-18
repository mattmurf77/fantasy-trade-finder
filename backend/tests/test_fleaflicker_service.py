"""Tests for backend/fleaflicker_service.py — Fleaflicker linking Phase 1.

Pure/offline: HTTP injected via `_opener`; data from the recorded fixture
fleaflicker_league_snapshot_2026-07-17.json (standings + rosters, trimmed to 3
teams from live public league 312861) and the re-cut DP crosswalk snapshot.
"""
import io
import json
import os
import urllib.error

import pytest

import backend.fleaflicker_service as fl
import backend.espn_service as es

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BUNDLE_FIXTURE = os.path.join(FIXTURES, "fleaflicker_league_snapshot_2026-07-17.json")
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


def _opener_for(bundle):
    def _opener(request, timeout=None):
        url = request.full_url
        if "FetchLeagueStandings" in url:
            return _FakeResp(json.dumps(bundle["standings"]))
        if "FetchLeagueRosters" in url:
            return _FakeResp(json.dumps(bundle["rosters"]))
        return _FakeResp("{}")
    return _opener


def _opener_http_error(code):
    def _opener(request, timeout=None):
        raise urllib.error.HTTPError("http://flea", code, "err", {}, io.BytesIO(b"{}"))
    return _opener


# ── fetch ───────────────────────────────────────────────────────────────────

def test_fetch_requests_sportradar_external_ids():
    captured = {}

    def _opener(request, timeout=None):
        url = request.full_url
        if "FetchLeagueRosters" in url:
            captured["rosters_url"] = url
        b = _bundle()
        if "FetchLeagueStandings" in url:
            return _FakeResp(json.dumps(b["standings"]))
        return _FakeResp(json.dumps(b["rosters"]))

    fl.fetch_league_bundle("312861", _opener=_opener)
    assert "external_id_type=SPORTRADAR" in captured["rosters_url"]
    assert "sport=NFL" in captured["rosters_url"]


@pytest.mark.parametrize("code,kind", [(401, "auth"), (403, "auth"),
                                       (404, "not_found"), (500, "http")])
def test_fetch_error_mapping(code, kind):
    with pytest.raises(fl.FleaflickerError) as ei:
        fl.fetch_league_bundle("312861", _opener=_opener_http_error(code))
    assert ei.value.kind == kind


def test_fetch_rejects_non_numeric():
    with pytest.raises(fl.FleaflickerError) as ei:
        fl.fetch_league_bundle("not-a-league")
    assert ei.value.kind == "input"


def test_in_band_error_becomes_not_found():
    def _opener(request, timeout=None):
        return _FakeResp(json.dumps({"error": {"message": "no such league"}}))
    with pytest.raises(fl.FleaflickerError) as ei:
        fl.fetch_league_bundle("312861", _opener=_opener)
    assert ei.value.kind == "not_found"


# ── discovery by email ──────────────────────────────────────────────────────

def test_fetch_user_leagues_shape():
    def _opener(request, timeout=None):
        assert "email=me%40example.com" in request.full_url
        return _FakeResp(json.dumps({"leagues": [
            {"id": 312861, "name": "Avid Auctioneers Alliance", "size": 12}]}))
    out = fl.fetch_user_leagues("me@example.com", _opener=_opener)
    assert out == [{"league_id": "312861", "name": "Avid Auctioneers Alliance", "size": 12}]


def test_fetch_user_leagues_bad_email():
    with pytest.raises(fl.FleaflickerError) as ei:
        fl.fetch_user_leagues("not-an-email")
    assert ei.value.kind == "input"


# ── parse + crosswalk ───────────────────────────────────────────────────────

def test_parse_bundle_shape():
    parsed = fl.parse_bundle(_bundle())
    assert parsed["league_id"] == "312861"
    assert parsed["name"] == "Avid Auctioneers Alliance"
    assert parsed["total_teams"] == 12          # league.size, not the 3 trimmed teams
    assert len(parsed["teams"]) == 3
    t = parsed["teams"][0]
    assert t["team_id"].isdigit()
    # players carry (sportradar_id, nameFull, position)
    srids, names, poss = zip(*t["players"])
    assert any("-" in s for s in srids if s)    # sportradar uuids


def test_map_teams_full_match_rate():
    parsed = fl.parse_bundle(_bundle())
    xw = es.load_crosswalk(XWALK_FIXTURE)
    out = fl.map_teams(parsed, xw)
    r = out["report"]
    # 24 skill players across 3 teams resolve by sportradar_id
    assert r["pool_players"] == 24
    assert r["matched_by_id"] == 24
    assert r["matched_by_name"] == 0
    assert r["unmatched"] == []
    assert r["match_rate"] == 1.0
    # the synthetic kicker is out of pool, not a failure
    assert r["out_of_pool"] == 1
    assert all(sid.isdigit() for ids in out["rosters"].values() for sid in ids)
