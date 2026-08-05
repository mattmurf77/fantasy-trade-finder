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
        for t in ("league", "rosters", "futureDraftPicks", "players", "rules"):
            if f"TYPE={t}" in url and t in bundle:
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


# ── draftResults (#207 — MFL's authoritative draft-completion signal) ───────

def test_fetch_draft_results_requests_the_right_export():
    captured = {}
    payload = {"draftResults": {"draftUnit": {"unit": "LEAGUE", "draftPick": [
        {"round": "01", "pick": "01", "franchise": "0007",
         "player": "17472", "timestamp": "1785589226"},
    ]}}}

    def _opener(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResp(json.dumps(payload))

    got = mfl.fetch_draft_results("10005", 2026, "www48.myfantasyleague.com",
                                  _opener=_opener)
    assert "TYPE=draftResults" in captured["url"]
    assert "L=10005" in captured["url"] and "JSON=1" in captured["url"]
    assert got == payload


@pytest.mark.parametrize("code", [401, 404, 500])
def test_fetch_draft_results_degrades_to_empty(code):
    """Best-effort: this runs on a background refresh, never a request path."""
    assert mfl.fetch_draft_results("10005", 2026, "www48.myfantasyleague.com",
                                   _opener=_opener_http_error(code)) == {}


def test_fetch_draft_results_rejects_a_non_numeric_league_id():
    assert mfl.fetch_draft_results("abc", 2026, "www48.myfantasyleague.com",
                                   _opener=_opener_http_error(500)) == {}


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


# ── #210 — MFL display strings arrive with HTML entities / messy whitespace ─

def test_clean_text_unescapes_entities_and_normalises_whitespace():
    assert mfl._clean_text("&#201;ire Rebels") == "Éire Rebels"        # numeric
    assert mfl._clean_text("Fish &amp; Chips") == "Fish & Chips"            # named
    assert mfl._clean_text("&amp;#201;ire Rebels") == "Éire Rebels"    # double-escaped
    assert mfl._clean_text("  Two  Spaces\t Team \n") == "Two Spaces Team"
    assert mfl._clean_text(None) == ""
    assert mfl._clean_text("Plain Name") == "Plain Name"


def test_parse_bundle_cleans_entity_laden_names():
    # The operator's Dependables case: MFL serving '&#201;ire Rebels'.
    raw = {
        "league": {"league": {
            "id": "62846", "name": "The Dependables &amp; Friends",
            "franchises": {"count": "2", "franchise": [
                {"id": "0001", "name": "&#201;ire  Rebels"},
                {"id": "0002", "name": "Smash &amp; Grab"},
            ]},
        }},
        "rosters": {"rosters": {"franchise": [
            {"id": "0001", "player": {"id": "15281", "status": "ROSTER"}},
            {"id": "0002"},
        ]}},
        "players": {"players": {"player": {
            "id": "15281", "name": "O&#8217;Connell, Kirby", "position": "QB"}}},
    }
    parsed = mfl.parse_bundle(raw)
    assert parsed["name"] == "The Dependables & Friends"
    assert parsed["franchises"][0]["name"] == "Éire Rebels"
    assert parsed["franchises"][1]["name"] == "Smash & Grab"
    # player names get the same cleanup before the flip
    assert parsed["franchises"][0]["players"] == [
        ("15281", "Kirby O’Connell", "QB")]


# ── scoring-format detection (#201) ─────────────────────────────────────────

def _scoring_raw(qb_limit=None, te_pts=None, wr_pts=None):
    """Build a minimal raw bundle carrying an MFL-shaped league (starting
    lineup config) + rules (scoring) export. te/wr points are the MFL points
    strings for the per-reception event 'CC' (e.g. '1.5*'); the TE rule uses
    MFL's {"$t": …} text-node wrapping and a list, the WR rule the bare-value
    single-dict form — both shapes appear in live exports."""
    league = {"id": "10005", "name": "Detect Me"}
    if qb_limit is not None:
        league["starters"] = {
            "count": "10",
            "position": [{"name": "QB", "limit": qb_limit},
                         {"name": "RB", "limit": "2-4"},
                         {"name": "WR", "limit": "3-5"}],
        }
    raw = {"league": {"league": league}}
    prs = []
    if te_pts is not None:
        prs.append({"positions": "TE",
                    "rule": [{"points": {"$t": te_pts},
                              "event": {"$t": "CC"},
                              "range": {"$t": "0-100"}}]})
    if wr_pts is not None:
        prs.append({"positions": "WR|RB",
                    "rule": {"points": wr_pts, "event": "CC",
                             "range": "0-100"}})
    if prs:
        raw["rules"] = {"rules": {"positionRules": prs}}
    return raw


def test_detect_sf_tep_league():
    # The operator's Dependables case: superflex QB slot + TE reception premium.
    raw = _scoring_raw(qb_limit="1-2", te_pts="1.5*", wr_pts="1*")
    assert mfl.detect_scoring_format(raw) == "sf_tep"


def test_detect_plain_1qb_ppr_league():
    raw = _scoring_raw(qb_limit="1", te_pts="1*", wr_pts="1*")
    assert mfl.detect_scoring_format(raw) == "1qb_ppr"


def test_detect_superflex_without_tep_collapses_to_sf_tep():
    # Mirror of the Sleeper convention: SF alone is enough for the sf_tep
    # bucket (QB scarcity dominates), even with flat reception scoring.
    raw = _scoring_raw(qb_limit="2", te_pts="1*", wr_pts="1*")
    assert mfl.detect_scoring_format(raw) == "sf_tep"


def test_detect_tep_without_superflex_collapses_to_sf_tep():
    raw = _scoring_raw(qb_limit="1", te_pts="1.5*", wr_pts="1*")
    assert mfl.detect_scoring_format(raw) == "sf_tep"


def test_detect_degrades_without_rules_export():
    # rules fetch failed / trimmed → TEP undetectable, lineup signal only.
    assert mfl.detect_scoring_format(_scoring_raw(qb_limit="1-2")) == "sf_tep"
    assert mfl.detect_scoring_format(_scoring_raw(qb_limit="1")) == "1qb_ppr"


def test_detect_defaults_1qb_on_empty_bundle():
    # Old trimmed fixtures carry no starters config at all.
    assert mfl.detect_scoring_format(_bundle()) == "1qb_ppr"
    assert mfl.detect_scoring_format({}) == "1qb_ppr"


def test_fetch_bundle_includes_rules_and_degrades_on_rules_error():
    bundle = _bundle()

    def _opener(request, timeout=None):
        url = request.full_url
        if "TYPE=rules" in url:
            raise urllib.error.HTTPError(url, 500, "err", {}, io.BytesIO(b"{}"))
        for t in ("league", "rosters", "futureDraftPicks", "players"):
            if f"TYPE={t}" in url:
                return _FakeResp(json.dumps(bundle[t]))
        return _FakeResp("{}")

    raw = mfl.fetch_league_bundle("10005", 2026, "www48.myfantasyleague.com",
                                  _opener=_opener)
    assert raw["rules"] == {}          # best-effort, never a hard error
    assert raw["league"]


def test_fetch_scoring_inputs_league_and_rules_only():
    fetched = []
    payload = _scoring_raw(qb_limit="1-2", te_pts="1.5*", wr_pts="1*")

    def _opener(request, timeout=None):
        url = request.full_url
        for t in ("league", "rules"):
            if f"TYPE={t}" in url:
                fetched.append(t)
                return _FakeResp(json.dumps(payload[t]))
        raise AssertionError(f"unexpected fetch: {url}")

    raw = mfl.fetch_scoring_inputs("10005", 2026, "www48.myfantasyleague.com",
                                   _opener=_opener)
    assert fetched == ["league", "rules"]
    assert mfl.detect_scoring_format(raw) == "sf_tep"


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
