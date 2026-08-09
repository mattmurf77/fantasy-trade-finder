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


def test_fetch_passes_encoded_cookies_byte_identical_for_private():
    # An already-percent-encoded espn_s2 (browser paste) must NOT be
    # re-encoded — double-encoding breaks auth just like the decoded form.
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({"id": 1}))

    es.fetch_league("1", 2026, espn_s2=s2, swid=swid, _opener=_capturing_opener)
    assert captured["cookie"] == f"espn_s2={s2}; SWID={swid}"


def test_fetch_reencodes_decoded_native_store_cookies():
    # 2026-08-09 field failure: the iOS native cookie store surfaces espn_s2
    # percent-DECODED; ESPN only accepts the encoded wire form. fetch_league
    # must canonicalize before building the Cookie header.
    s2_decoded = "AEB/vS0me+decoded=value"
    swid = "{ABCD-1234}"
    captured = {}

    def _capturing_opener(request, timeout=None):
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({"id": 1}))

    es.fetch_league(
        "1", 2026, espn_s2=s2_decoded, swid=swid, _opener=_capturing_opener
    )
    assert captured["cookie"] == "espn_s2=AEB%2FvS0me%2Bdecoded%3Dvalue; SWID={ABCD-1234}"


# ---------------------------------------------------------------------------
# 1b. cookie canonicalizers (2026-08-09 — decoded-capture field failure)
# ---------------------------------------------------------------------------

def test_canonical_espn_s2_encoded_form_passes_byte_identical():
    # A realistic browser-jar shape: long, %XX escapes present. Must be
    # returned unchanged — never double-encoded.
    v = "AEBx%2Fabc%2Bdef%3D%3D" + "Qw9" * 100
    assert es.canonical_espn_s2(v) == v


def test_canonical_espn_s2_decoded_form_is_reencoded():
    import urllib.parse

    decoded = "AEBx/abc+def==" + "Qw9" * 100
    out = es.canonical_espn_s2(decoded)
    assert "%2F" in out and "%2B" in out and "%3D" in out
    # Round-trip: the encoded output decodes back to the original value.
    assert urllib.parse.unquote(out) == decoded


def test_canonical_espn_s2_plain_and_empty_values_are_stable():
    # Pure-alphanumeric values are the same in both forms — identity.
    assert es.canonical_espn_s2("ABCdef123") == "ABCdef123"
    assert es.canonical_espn_s2("  ABCdef123  ") == "ABCdef123"
    assert es.canonical_espn_s2("") == ""


def test_canonical_swid_braced_passes_and_bare_gains_braces():
    assert es.canonical_swid("{ABCD-1234-EF}") == "{ABCD-1234-EF}"
    assert es.canonical_swid("ABCD-1234-EF") == "{ABCD-1234-EF}"
    # Half-braced paste still normalizes to one brace pair.
    assert es.canonical_swid("{ABCD-1234-EF") == "{ABCD-1234-EF}"
    assert es.canonical_swid("") == ""


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
# 1b. fetch_fan_leagues / _parse_fan_leagues — league-picker fan-profile call
# (2026-08-09, feedback: "fetch all their ESPN leagues and let them pick").
# UNVERIFIED SHAPE — see espn_service.fetch_fan_leagues docstring +
# docs/integrations/espn.md §1.7. These fixtures pin the best-known
# community shape and the defensive-parse contract, not ESPN's real payload.
# ---------------------------------------------------------------------------

FAN_PAYLOAD = {
    "preferences": [
        {
            "metaData": {
                "entry": {
                    "abbrev": "ffl",
                    "entryMetadata": {"teamName": "The Dynasty Dominators"},
                    "groups": [
                        {"groupId": "987654321", "groupName": "Recorded Shape Dynasty",
                         "seasonId": 2026},
                        {"groupId": "111222333", "groupName": "Old League",
                         "seasonId": 2024},
                    ],
                }
            }
        },
        # A different game (ESPN fantasy baseball) — must be filtered out.
        {
            "metaData": {
                "entry": {
                    "abbrev": "flb",
                    "groups": [{"groupId": "555", "groupName": "Baseball League",
                               "seasonId": 2026}],
                }
            }
        },
    ]
}


def test_fetch_fan_leagues_happy_path_parses_and_sorts_newest_first():
    captured = {}

    def _opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps(FAN_PAYLOAD))

    out = es.fetch_fan_leagues("AEBencoded%2Fvalue", "{ABCD-1234}", _opener=_opener)
    assert "fan.api.espn.com/apis/v2/fans/" in captured["url"]
    assert captured["cookie"] == "espn_s2=AEBencoded%2Fvalue; SWID={ABCD-1234}"
    assert [lg["league_id"] for lg in out] == ["987654321", "111222333"]
    assert out[0]["season"] == 2026 and out[1]["season"] == 2024   # newest first
    assert out[0]["league_name"] == "Recorded Shape Dynasty"
    assert out[0]["team_name"] == "The Dynasty Dominators"
    # The baseball ("flb") group must not leak into the football list.
    assert "555" not in [lg["league_id"] for lg in out]


def test_fetch_fan_leagues_reencodes_decoded_native_store_cookies():
    # Same normalizer choke point as fetch_league — a native-store (decoded)
    # espn_s2 must be re-encoded before it reaches the Cookie header.
    captured = {}

    def _opener(request, timeout=None):
        captured["cookie"] = request.get_header("Cookie")
        return _FakeResp(json.dumps({"preferences": []}))

    es.fetch_fan_leagues("AEB+decoded/value=", "ABCD-1234", _opener=_opener)
    assert captured["cookie"] == "espn_s2=AEB%2Bdecoded%2Fvalue%3D; SWID={ABCD-1234}"


@pytest.mark.parametrize("code", [401, 403, 404])
def test_fetch_fan_leagues_auth_failure_mapping(code):
    with pytest.raises(es.EspnAuthError):
        es.fetch_fan_leagues("s2value", "{SWID}", _opener=_opener_http_error(code))


def test_fetch_fan_leagues_non_json_raises_parse():
    def _opener(request, timeout=None):
        return _FakeResp("<html>maintenance</html>")
    with pytest.raises(es.EspnError) as ei:
        es.fetch_fan_leagues("s2value", "{SWID}", _opener=_opener)
    assert ei.value.kind == "parse"


def test_fetch_fan_leagues_requires_both_cookies():
    with pytest.raises(es.EspnError) as ei:
        es.fetch_fan_leagues("", "{SWID}")
    assert ei.value.kind == "input"
    with pytest.raises(es.EspnError) as ei:
        es.fetch_fan_leagues("s2value", "")
    assert ei.value.kind == "input"


def test_parse_fan_leagues_empty_account_returns_empty_list():
    assert es._parse_fan_leagues({"preferences": []}) == []
    assert es._parse_fan_leagues({}) == []


@pytest.mark.parametrize("bad_shape", [
    None, [], "not a dict",
    {"preferences": "not a list"},
    {"preferences": [{"metaData": "not a dict"}]},
    {"preferences": [{"metaData": {"entry": {"abbrev": "ffl", "groups": "nope"}}}]},
    {"preferences": [{"metaData": {"entry": {"abbrev": "ffl",
                                              "groups": [{"groupId": "not-numeric"}]}}}]},
])
def test_parse_fan_leagues_shape_drift_never_raises(bad_shape):
    # The defensive-parse contract: whatever ESPN's real shape turns out to
    # be, a mismatch degrades to an empty/partial list, never an exception.
    assert es._parse_fan_leagues(bad_shape) == []


def test_parse_fan_leagues_entry_without_abbrev_is_kept():
    # Missing `abbrev` entirely (vs. a non-"ffl" value) is kept rather than
    # dropped — better a possibly-mislabeled row surfaces than a real league
    # silently vanishes.
    data = {"preferences": [{"metaData": {"entry": {
        "groups": [{"groupId": "42", "groupName": "No Abbrev League", "seasonId": 2025}],
    }}}]}
    out = es._parse_fan_leagues(data)
    assert [lg["league_id"] for lg in out] == ["42"]


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
