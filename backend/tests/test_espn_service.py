"""Tests for backend/espn_service.py — the ESPN league-linking spike (#101).

Pure/offline: HTTP is injected via `_opener` (same pattern as
test_sleeper_write.py); league + crosswalk data come from recorded fixtures:

  fixtures/espn_league_snapshot_2026-07-11.json  — shape-accurate ESPN v3
      mTeam+mRoster+mSettings payload with REAL espn player IDs (the public
      test leagues espn-api used were purged by ESPN, so the shape was
      recorded from the documented v3 format instead of a live league).
  fixtures/dp_playerids_snapshot_2026-07-11.csv  — trimmed DynastyProcess
      db_playerids crosswalk (skill positions, rows with a sleeper/espn id).

Covers: fetch error mapping + cookie passthrough, payload parsing, crosswalk
loading, and the roster → Sleeper player_id mapping with its match-rate report.
"""

import io
import json
import os
import urllib.error

import pytest

import backend.espn_service as es

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LEAGUE_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, text):
        self._b = text.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_returning(payload_obj):
    def _opener(request, timeout=None):
        return _FakeResp(json.dumps(payload_obj))
    return _opener


def _opener_http_error(code):
    def _opener(request, timeout=None):
        raise urllib.error.HTTPError(es.ESPN_READS_BASE, code, "err", {}, io.BytesIO(b"{}"))
    return _opener


def _load_fixture():
    with open(LEAGUE_FIXTURE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. fetch — headers, cookies, error mapping
# ---------------------------------------------------------------------------

def test_fetch_sends_browser_headers_and_no_cookie_for_public():
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["ua"] = request.get_header("User-agent")
        captured["cookie"] = request.get_header("Cookie")
        captured["url"] = request.full_url
        return _FakeResp(json.dumps({"id": 1}))

    es.fetch_league("987654321", 2026, _opener=_capturing_opener)
    assert "Mozilla" in captured["ua"] and "urllib" not in captured["ua"].lower()
    assert captured["cookie"] is None
    assert "seasons/2026/segments/0/leagues/987654321" in captured["url"]
    assert "view=mRoster" in captured["url"]


def test_fetch_passes_cookies_verbatim_for_private():
    # espn_s2 is URL-encoded as captured — it must NOT be re-encoded.
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({"id": 1}))

    es.fetch_league("1", 2026, espn_s2=s2, swid=swid, _opener=_capturing_opener)
    assert captured["cookie"] == f"espn_s2={s2}; SWID={swid}"


@pytest.mark.parametrize("code,exc,kind", [
    (401, es.EspnAuthError, "auth"),
    (403, es.EspnAuthError, "auth"),
    (404, es.EspnError, "not_found"),
    (500, es.EspnError, "http"),
])
def test_fetch_error_mapping(code, exc, kind):
    with pytest.raises(exc) as ei:
        es.fetch_league("1", 2026, _opener=_opener_http_error(code))
    assert ei.value.kind == kind


def test_fetch_rejects_non_numeric_league_id():
    with pytest.raises(es.EspnError) as ei:
        es.fetch_league("not-a-league", 2026)
    assert ei.value.kind == "input"


def test_fetch_non_json_raises_parse():
    def _opener(request, timeout=None):
        return _FakeResp("<html>maintenance</html>")
    with pytest.raises(es.EspnError) as ei:
        es.fetch_league("1", 2026, _opener=_opener)
    assert ei.value.kind == "parse"


# ---------------------------------------------------------------------------
# 2. parse_league — fixture shape
# ---------------------------------------------------------------------------

def test_parse_league_fixture():
    league = es.parse_league(_load_fixture())
    assert league["league_id"] == "987654321"
    assert league["name"] == "Recorded Shape Dynasty"
    assert league["season"] == 2026
    assert league["total_teams"] == 3
    assert len(league["teams"]) == 3

    t1 = league["teams"][0]
    assert t1.team_id == 1
    assert t1.name == "Chalk Dusters"
    assert t1.owner_display == "owner1"
    # 8 skill players + 1 K + 1 D/ST
    assert len(t1.players) == 10
    positions = {p.position for p in t1.players}
    assert positions == {"QB", "RB", "WR", "TE", "K", "DST"}


def test_parse_league_owner_falls_back_to_owners_list():
    league = es.parse_league({
        "id": 5, "seasonId": 2026, "settings": {"name": "x", "size": 1},
        "members": [],
        "teams": [{"id": 1, "location": "Old", "nickname": "Shape",
                    "owners": ["{X}"], "roster": {"entries": []}}],
    })
    t = league["teams"][0]
    assert t.name == "Old Shape"
    assert t.owner_swid == "{X}"


# ---------------------------------------------------------------------------
# 3. crosswalk
# ---------------------------------------------------------------------------

def test_load_crosswalk_fixture():
    xw = es.load_crosswalk(XWALK_FIXTURE)
    # trimmed snapshot: thousands of skill players carry both ids
    assert len(xw.by_espn_id) > 2000
    # spot-check: Ja'Marr Chase — espn 4362628 ↔ sleeper 7564
    assert xw.by_espn_id.get("4362628") == "7564"
    assert xw.by_name_pos.get(("jamarr chase", "WR")) == "7564"


def test_crosswalk_skips_rows_without_sleeper_id(tmp_path):
    p = tmp_path / "xw.csv"
    p.write_text(
        "name,merge_name,position,team,sleeper_id,espn_id\n"
        "A Player,a player,RB,FA,,111\n"          # no sleeper id → unusable
        "B Player,b player,WR,FA,42,NA\n"         # name-only row
        "C Player,c player,QB,FA,43,222\n"
    )
    xw = es.load_crosswalk(str(p))
    assert "111" not in xw.by_espn_id
    assert xw.by_espn_id == {"222": "43"}
    assert xw.by_name_pos[("b player", "WR")] == "42"


# ---------------------------------------------------------------------------
# 4. roster mapping + match-rate report
# ---------------------------------------------------------------------------

def test_map_rosters_full_fixture_match_rate():
    league = es.parse_league(_load_fixture())
    xw = es.load_crosswalk(XWALK_FIXTURE)
    out = es.map_rosters(league["teams"], xw)
    r = out["report"]

    # 24 skill players across 3 teams; every one carries a real espn_id
    # present in the snapshot → 100% match, all by id.
    assert r["pool_players"] == 24
    assert r["matched_by_id"] == 24
    assert r["matched_by_name"] == 0
    assert r["unmatched"] == []
    assert r["match_rate"] == 1.0
    # K + D/ST are out of pool, not failures
    assert r["out_of_pool"] == 2

    # every team got sleeper ids for its 8 skill players
    assert {tid: len(ids) for tid, ids in out["rosters"].items()} == {1: 8, 2: 8, 3: 8}
    # mapped ids are Sleeper-style numeric strings
    assert all(sid.isdigit() for ids in out["rosters"].values() for sid in ids)


def test_map_rosters_name_fallback_and_unmatched():
    teams = [es.EspnTeam(
        team_id=1, name="T", owner_swid="{X}", owner_display="x",
        players=[
            es.EspnPlayer(espn_id="999999999", name="Ja'Marr Chase", position="WR"),
            es.EspnPlayer(espn_id="888888888", name="Totally Unknown", position="RB"),
        ],
    )]
    xw = es.load_crosswalk(XWALK_FIXTURE)
    out = es.map_rosters(teams, xw)
    r = out["report"]
    # bogus espn_id but the name+pos fallback recovers Chase
    assert r["matched_by_name"] == 1
    assert out["rosters"][1] == ["7564"]
    assert [u["name"] for u in r["unmatched"]] == ["Totally Unknown"]
    assert r["match_rate"] == 0.5


def test_map_rosters_empty_pool_zero_rate():
    teams = [es.EspnTeam(team_id=1, name="T", owner_swid="", owner_display="",
                          players=[es.EspnPlayer("15683", "Justin Tucker", "K")])]
    xw = es.Crosswalk(by_espn_id={}, by_name_pos={})
    out = es.map_rosters(teams, xw)
    assert out["report"]["match_rate"] == 0.0
    assert out["report"]["out_of_pool"] == 1
    assert out["rosters"] == {1: []}
