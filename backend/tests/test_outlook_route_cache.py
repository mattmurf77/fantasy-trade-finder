"""#169 outlook odds — route-level concerns: the Sleeper fan-out cache, the
flag registration (dark), and the payload contract the mobile layer binds to.

Split from `test_outlook_odds.py` on purpose: that file owns the ENGINE
(simulator / strength / format / calibration). This one owns the surface —
`server.py`'s route, `_outlook_sleeper_fetch()`, the `outlook.odds` flag
touches, and the wire contract.

Nothing here hits the network: `server._sleeper_get` is patched with a
counting fake, which doubles as the instrumentation probe — every upstream
call MUST go through that chokepoint (it is where `_api_obs.observe_call`
fires), so a cache hit is observable as a call that never happened.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
from unittest.mock import patch

import pytest

import backend.api_observability as api_obs
import backend.server as server
from backend.feature_flags import DEFAULT_FLAGS, FLAG_KEYS

REPO = pathlib.Path(__file__).resolve().parents[2]

LEAGUE_ID = "1234567890"
USER = "313560442465169408"
TOKEN = "outlook-cache-sess-tok"

# 4-week regular season (playoff_week_start=5). Weeks 1-2 are played, weeks
# 3-4 are pairings-only — so week 1 is SETTLED (a later week has scored),
# week 2 is the live week, weeks 3-4 are future schedule.
_PLAYED_WEEKS = (1, 2)
_REGULAR_WEEKS = 4


def _fake_sleeper(season: str = "2026", calls: list[str] | None = None,
                  playoff_seed_type: int | None = None):
    """A stand-in for `_sleeper_get` that records every URL it is asked for.

    `playoff_seed_type`, when given, is included in the league-meta
    `settings` blob — real Sleeper leagues carry this field (BUG-3); omitted
    by default to also cover leagues where it's absent."""
    log = calls if calls is not None else []

    def fake(url: str, timeout: int = 15):
        log.append(url)
        path = url.split("/v1/", 1)[1]
        if path == f"league/{LEAGUE_ID}":
            settings = {"playoff_week_start": _REGULAR_WEEKS + 1,
                       "playoff_teams": 4}
            if playoff_seed_type is not None:
                settings["playoff_seed_type"] = playoff_seed_type
            return {
                "season": season,
                "settings": settings,
                "roster_positions": ["QB", "RB", "BN"],
            }
        if path == f"league/{LEAGUE_ID}/rosters":
            return [
                {"roster_id": rid, "owner_id": f"u{rid}",
                 "players": [f"p{rid}"], "starters": [f"p{rid}"],
                 "settings": {"wins": 1, "losses": 1, "ties": 0, "fpts": 200}}
                for rid in range(1, 5)
            ]
        if path == f"league/{LEAGUE_ID}/users":
            return [{"user_id": f"u{rid}", "display_name": f"user{rid}",
                     "metadata": {"team_name": f"Team {rid}"}}
                    for rid in range(1, 5)]
        m = re.match(rf"league/{LEAGUE_ID}/matchups/(\d+)$", path)
        if m:
            week = int(m.group(1))
            pts = 100.0 if week in _PLAYED_WEEKS else 0.0
            return [{"roster_id": rid, "matchup_id": (rid + 1) // 2,
                     "points": pts}
                    for rid in range(1, 5)]
        raise AssertionError(f"unexpected Sleeper URL in test: {url}")

    return fake, log


def _matchup_calls(log: list[str]) -> list[int]:
    """Weeks actually fetched upstream, in order."""
    return [int(m.group(1))
            for m in (re.search(r"/matchups/(\d+)$", u) for u in log) if m]


def _load(fetch) -> None:
    from backend.outlook.pipeline import build_league_state
    build_league_state(LEAGUE_ID, platform="sleeper", fetch=fetch)


@pytest.fixture(autouse=True)
def _clean_cache():
    server._outlook_cache_clear()
    yield
    server._outlook_cache_clear()


# ---------------------------------------------------------------------------
# Fan-out cache
# ---------------------------------------------------------------------------

def test_completed_weeks_are_never_refetched():
    """The whole point: a settled week is fetched ONCE, ever. Two full loads
    must produce exactly one upstream call per week."""
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        fetch = server._outlook_sleeper_fetch()
        _load(fetch)
        first = _matchup_calls(log)
        _load(fetch)
        second = _matchup_calls(log)[len(first):]
    assert first == [1, 2, 3, 4]
    assert second == []                      # everything served from cache
    assert server._OUTLOOK_CACHE_STATS["settled_hits"] >= 1
    assert server._OUTLOOK_CACHE_STATS["upstream"] == _REGULAR_WEEKS


def test_settled_week_survives_ttl_expiry_but_live_and_future_weeks_do_not():
    """Expire every TTL entry: the settled week (no TTL) still must not be
    refetched, while the live + future weeks are."""
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        fetch = server._outlook_sleeper_fetch()
        _load(fetch)
        base = len(_matchup_calls(log))
        with server._outlook_cache_lock:
            for k, (_ts, rows) in list(server._OUTLOOK_WEEK_LIVE.items()):
                server._OUTLOOK_WEEK_LIVE[k] = (time.time() - 10_000, rows)
        _load(fetch)
        after = _matchup_calls(log)[base:]
    assert 1 not in after, "settled week 1 must never be refetched"
    assert sorted(after) == [2, 3, 4]


def test_live_week_expires_before_future_weeks():
    """Tiering: at ~16 min only the live week (15 min TTL) is stale; the
    unplayed weeks ride the 1 h schedule TTL."""
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        fetch = server._outlook_sleeper_fetch()
        _load(fetch)
        base = len(_matchup_calls(log))
        with server._outlook_cache_lock:
            for k, (_ts, rows) in list(server._OUTLOOK_WEEK_LIVE.items()):
                server._OUTLOOK_WEEK_LIVE[k] = (time.time() - 1_000, rows)
        _load(fetch)
        after = _matchup_calls(log)[base:]
    assert after == [2], "only the in-progress week should refresh at 16 min"


def test_cache_is_scoped_by_season():
    """A new season must never be served last season's scores."""
    fake_a, log = _fake_sleeper(season="2026")
    with patch.object(server, "_sleeper_get", fake_a):
        _load(server._outlook_sleeper_fetch())
        base = len(_matchup_calls(log))
    fake_b, _ = _fake_sleeper(season="2027", calls=log)
    with patch.object(server, "_sleeper_get", fake_b):
        _load(server._outlook_sleeper_fetch())
    assert _matchup_calls(log)[base:] == [1, 2, 3, 4]


def test_non_matchup_reads_stay_live():
    """Standings (rosters) and users are deliberately NOT cached — a stale
    standing is a wrong answer, not a slow one."""
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        fetch = server._outlook_sleeper_fetch()
        _load(fetch)
        _load(fetch)
    assert log.count(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters") == 2
    assert log.count(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users") == 2


def test_every_upstream_fetch_flows_through_the_instrumented_chokepoint():
    """Cache misses must go through `_sleeper_get` (where
    `_api_obs.observe_call` fires) and classify as `league.matchups`, so the
    cache's effect is visible in apihealth as api_call events that stop
    happening. Cache hits fire nothing."""
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        fetch = server._outlook_sleeper_fetch()
        _load(fetch)
        misses = len(log)
        _load(fetch)
        hits_added = len(log) - misses
    assert misses == 3 + _REGULAR_WEEKS      # meta + rosters + users + weeks
    assert hits_added == 3                   # only the deliberately-live reads
    for url in log:
        if "/matchups/" in url:
            cls, lid = api_obs.sleeper_endpoint_class(url)
            assert cls == "league.matchups"
            assert lid == LEAGUE_ID


# ---------------------------------------------------------------------------
# BUG-3 — `_outlook_sleeper_fetch`'s `captured` side-channel for
# `playoff_seed_type` (backend/outlook/playoff_format.py owns modeling it;
# this closure is the only place that can observe the raw Sleeper setting
# without a second network call or editing league_state.py).
# ---------------------------------------------------------------------------

def test_outlook_sleeper_fetch_captures_playoff_seed_type_when_present():
    fake, _log = _fake_sleeper(playoff_seed_type=0)
    with patch.object(server, "_sleeper_get", fake):
        captured: dict = {}
        _load(server._outlook_sleeper_fetch(captured))
    assert captured["playoff_seed_type"] == 0


def test_outlook_sleeper_fetch_captured_is_none_when_absent():
    fake, _log = _fake_sleeper()  # no playoff_seed_type in league settings
    with patch.object(server, "_sleeper_get", fake):
        captured: dict = {}
        _load(server._outlook_sleeper_fetch(captured))
    assert captured["playoff_seed_type"] is None


def test_outlook_sleeper_fetch_without_captured_arg_does_not_crash():
    """Default (no `captured` dict passed) must behave exactly as before —
    this is a purely additive, opt-in parameter."""
    fake, _log = _fake_sleeper(playoff_seed_type=1)
    with patch.object(server, "_sleeper_get", fake):
        _load(server._outlook_sleeper_fetch())  # no captured=... at all


# ---------------------------------------------------------------------------
# Flag registration — `outlook.odds` is a full 4-touch flag, DARK everywhere
# ---------------------------------------------------------------------------

def test_flag_is_registered_and_defaults_off_everywhere():
    assert "outlook.odds" in FLAG_KEYS
    assert DEFAULT_FLAGS["outlook.odds"] is False
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads(
        (REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert features["outlook.odds"] is False
    assert release["outlook.odds"] is False, "release fixture must mirror dark"
    all_on = json.loads(
        (REPO / "backend/tests/fixtures/flags/all-on.json").read_text())
    assert "outlook.odds" not in all_on, (
        "the flag-sweep fixture must not light an uncalibrated surface")


def test_mobile_never_defaults_the_flag_on():
    body = (REPO / "mobile/src/state/useFeatureFlags.ts").read_text()
    defaults = body.split("LAUNCHED_FLAG_DEFAULTS", 1)[1].split("}", 1)[0]
    assert "outlook.odds" not in defaults


# ---------------------------------------------------------------------------
# Endpoint — ships off (real flag resolution, nothing patched)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    sess = {
        "user_id": USER,
        "active_format": "1qb_ppr",
        "last_active": 0.0,
        "league": None,
        "players": [],
        "trade_svc": object(),
    }
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _headers():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def test_ships_off_route_is_unreachable_and_makes_no_sleeper_call(client):
    """The ships-off gate: with the REAL flag map (nothing patched) the route
    is unreachable and the fan-out never runs — zero behavior change."""
    assert server.is_enabled("outlook.odds") is False
    fake, log = _fake_sleeper()
    with patch.object(server, "_sleeper_get", fake):
        r = client.get(f"/api/league/outlook?league_id={LEAGUE_ID}",
                       headers=_headers())
    assert r.status_code == 404
    assert r.get_json() == {"error": "not_found"}
    assert log == []


# ---------------------------------------------------------------------------
# Wire contract — what mobile/src/api/league.ts binds to
# ---------------------------------------------------------------------------

def _payload(client) -> dict:
    fake, _log = _fake_sleeper()
    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"), \
         patch.object(server, "_sleeper_get", fake), \
         patch.object(server, "_get_universal_pool", lambda fmt: ([], {})):
        r = client.get(f"/api/league/outlook?league_id={LEAGUE_ID}",
                       headers=_headers())
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def test_route_threads_playoff_seed_type_from_sleeper_settings_into_run_outlook(client):
    """End-to-end BUG-3 wiring: the raw `settings.playoff_seed_type` the fake
    Sleeper league carries must reach `run_outlook` (and therefore
    `get_playoff_format`) — this is the route-level counterpart to the
    `playoff_format.py` unit/fixture tests in test_outlook_playoff_seed_type.py."""
    import backend.outlook as outlook_pkg
    fake, _log = _fake_sleeper(playoff_seed_type=0)
    calls: list = []
    real_run_outlook = outlook_pkg.run_outlook

    def spy(*a, **k):
        calls.append(k.get("playoff_seed_type"))
        return real_run_outlook(*a, **k)

    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"), \
         patch.object(server, "_sleeper_get", fake), \
         patch.object(server, "_get_universal_pool", lambda fmt: ([], {})), \
         patch.object(outlook_pkg, "run_outlook", spy):
        r = client.get(f"/api/league/outlook?league_id={LEAGUE_ID}",
                       headers=_headers())
    assert r.status_code == 200, r.get_data(as_text=True)
    assert calls == [0]


def test_payload_shape_is_the_documented_contract(client):
    body = _payload(client)
    assert set(body) == {"league_id", "platform", "basis", "scoring_format",
                         "meta", "teams"}
    assert set(body["meta"]) == {
        "strength_source", "completed_weeks", "regular_season_weeks",
        "playoff_slots", "byes", "sims", "seed", "is_preseason", "beta"}
    team = body["teams"][0]
    assert set(team) == {
        "roster_id", "user_id", "username", "display_name", "is_you",
        "wins", "losses", "ties", "points_for", "strength", "odds"}
    assert set(team["strength"]) == {"mu", "sigma"}
    assert set(team["odds"]) == {"playoff_pct", "bye_pct", "title_pct",
                                 "projected_wins", "projected_seed"}
    # Percentages are 0..1 fractions (the mobile layer multiplies by 100).
    for t in body["teams"]:
        for k in ("playoff_pct", "bye_pct", "title_pct"):
            assert 0.0 <= t["odds"][k] <= 1.0
    # Pre-sorted playoff_pct desc — mobile renders in payload order.
    pcts = [t["odds"]["playoff_pct"] for t in body["teams"]]
    assert pcts == sorted(pcts, reverse=True)


def test_preseason_flag_tracks_completed_weeks(client):
    """The LLD's preseason rule is `completed_weeks == 0` ⇒ is_preseason. Weeks
    1-2 are played in the fake league, so the label must not fire here. (The
    in-season value of `meta.beta` is the engine's call — see status.md
    §Productionization; the mobile ribbon composes whatever it is sent.)"""
    body = _payload(client)
    assert body["meta"]["completed_weeks"] == len(_PLAYED_WEEKS)
    assert body["meta"]["is_preseason"] is False


def test_mobile_types_match_the_payload_field_for_field(client):
    """The odds layer was typed in July against this payload; the screen has
    been rebuilt several times since. Pin the two together."""
    src = (REPO / "mobile/src/api/league.ts").read_text()

    def ts_fields(interface: str) -> set[str]:
        """Top-level field names of a TS interface (nested object literals are
        the wire's nested objects, not extra fields)."""
        block = src.split(f"export interface {interface} {{", 1)[1]
        depth, out = 0, set()
        for line in block.splitlines():
            if depth == 0:
                m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\??\s*:", line.strip())
                if m:
                    out.add(m.group(1))
            depth += line.count("{") - line.count("}")
            if depth < 0:
                break
        return out

    body = _payload(client)
    assert ts_fields("LeagueOutlookResponse") == set(body)
    assert ts_fields("OutlookMeta") == set(body["meta"])
    assert ts_fields("OutlookTeam") == set(body["teams"][0])


def test_mobile_captions_cover_every_implemented_strength_source():
    """LLD preseason rule: the layer always shows a source caption. Every
    provider the backend can actually SELECT must have a friendly caption; the
    registered stubs are allowed to fall through to the generic one."""
    from backend.outlook.strength import STRENGTH_PROVIDERS, _StubStrength
    screen = (REPO / "mobile/src/screens/LeagueSummaryScreen.tsx").read_text()
    captions = screen.split("STRENGTH_SOURCE_CAPTION", 1)[1].split("}", 1)[0]
    for key, factory in STRENGTH_PROVIDERS.items():
        if issubclass(factory, _StubStrength):
            continue
        assert f"{key}:" in captions, f"no mobile caption for {key!r}"


def test_mobile_ribbon_composes_the_lld_preseason_label():
    """"Projected · preseason · beta" is composed from meta.is_preseason /
    meta.beta — the load-bearing honesty label, on BOTH sides."""
    screen = (REPO / "mobile/src/screens/LeagueSummaryScreen.tsx").read_text()
    ribbon = screen.split("function betaRibbonLabel", 1)[1].split("\n}", 1)[0]
    assert "'Projected'" in ribbon
    assert "meta.is_preseason" in ribbon and "'preseason'" in ribbon
    assert "meta.beta" in ribbon and "'beta'" in ribbon
    assert "league-summary.odds.beta-ribbon" in screen
    assert "league-summary.odds.source" in screen


def test_nullable_wire_fields_are_typed_nullable_in_mobile():
    """`scoring_format` and `strength.{mu,sigma}` are `| None` on the wire
    (serialize.py); the TS must admit null or a real payload can violate its
    own types at runtime."""
    src = (REPO / "mobile/src/api/league.ts").read_text()
    block = src.split("export interface LeagueOutlookResponse {", 1)[1]
    line = next(l for l in block.splitlines() if "scoring_format" in l)
    assert "null" in line, "scoring_format is null when the format is unset"
    team = src.split("export interface OutlookTeam {", 1)[1]
    strength = next(l for l in team.splitlines() if l.strip().startswith("strength"))
    assert "null" in strength, "strength.mu/sigma are null when a team has no estimate"
