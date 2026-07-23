"""Tests for the #169 outlook-odds pipeline (backend/outlook/).

Covers each phase in isolation plus the flag-dark endpoint:
  - simulator determinism + sanity (dominant team, symmetric league) and the
    hard invariants (Σ playoff_pct == slots, Σ title_pct == 1, Σ bye == byes)
  - StrengthProvider contract: RosterValueStrength works at completed_weeks==0;
    TrailingScoresStrength requires >= K weeks; both satisfy the Protocol
  - StandardFormat seeding / byes / points_for tiebreak
  - GET /api/league/outlook payload shape, flag-dark 404, preseason beta==true
  - an offline (skipped) backtest scaffold against captured data

No test hits the network: Phase 1 is bypassed with crafted LeagueState objects
and the endpoint patches build_league_state.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

import backend.server as server
from backend.outlook.league_state import (
    LeagueState, TeamState, compute_num_byes,
)
from backend.outlook.playoff_format import StandardFormat, get_playoff_format
from backend.outlook.serialize import StandardSerializer
from backend.outlook.simulator import simulate, stable_hash
from backend.outlook.strength import (
    BlendedStrength, RosterValueStrength, StrengthContext, StrengthProvider,
    TeamStrength, TrailingScoresStrength, resolve_strength_source,
    starting_lineup_value,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round_robin(roster_ids: list[int], weeks: int) -> dict[int, list[tuple[int, int]]]:
    """Circle-method round-robin, cycled to fill `weeks` weeks."""
    ids = list(roster_ids)
    if len(ids) % 2:
        ids.append(-1)  # bye placeholder
    n = len(ids)
    rounds = []
    arr = ids[:]
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if a != -1 and b != -1:
                pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    schedule = {}
    for w in range(1, weeks + 1):
        schedule[w] = rounds[(w - 1) % len(rounds)]
    return schedule


def _state(n_teams=8, weeks=13, playoff_slots=6, completed_weeks=0,
           weekly_scores=None, wins=None, points_for=None) -> LeagueState:
    rids = list(range(1, n_teams + 1))
    teams = []
    for rid in rids:
        teams.append(TeamState(
            roster_id=rid,
            user_id=f"u{rid}",
            username=f"user{rid}",
            display_name=f"Team {rid}",
            wins=(wins or {}).get(rid, 0),
            points_for=(points_for or {}).get(rid, 0.0),
            player_ids=[],
        ))
    return LeagueState(
        league_id="LG-TEST",
        platform="sleeper",
        regular_season_weeks=weeks,
        playoff_slots=playoff_slots,
        num_byes=compute_num_byes(playoff_slots),
        roster_slots=[],
        teams=teams,
        schedule=_round_robin(rids, weeks),
        completed_weeks=completed_weeks,
        weekly_scores=weekly_scores or {},
    )


def _flat_strengths(rids, mu=110.0, sigma=25.0):
    return {rid: TeamStrength(rid, mu, sigma) for rid in rids}


# ---------------------------------------------------------------------------
# Phase 3 — simulator determinism + sanity + invariants
# ---------------------------------------------------------------------------

def test_simulator_is_deterministic_for_same_seed():
    st = _state()
    strengths = _flat_strengths([t.roster_id for t in st.teams])
    fmt = StandardFormat(st.playoff_slots, st.num_byes)
    a = simulate(st, strengths, fmt, n_sims=1500, config_seed=7)
    b = simulate(st, strengths, fmt, n_sims=1500, config_seed=7)
    assert a.titles == b.titles
    assert a.made_playoffs == b.made_playoffs
    assert a.seed == b.seed


def test_simulator_changes_with_seed():
    st = _state()
    strengths = _flat_strengths([t.roster_id for t in st.teams])
    fmt = StandardFormat(st.playoff_slots, st.num_byes)
    a = simulate(st, strengths, fmt, n_sims=1500, config_seed=1)
    b = simulate(st, strengths, fmt, n_sims=1500, config_seed=2)
    assert a.seed != b.seed


def test_invariants_playoffs_titles_byes_sum():
    st = _state(n_teams=10, playoff_slots=6)
    strengths = _flat_strengths([t.roster_id for t in st.teams])
    fmt = StandardFormat(st.playoff_slots, st.num_byes)
    n = 2000
    res = simulate(st, strengths, fmt, n_sims=n, config_seed=0)
    assert sum(res.made_playoffs.values()) == n * st.playoff_slots
    assert sum(res.titles.values()) == n
    assert sum(res.byes.values()) == n * st.num_byes
    # per-team pcts sum to the slot/title/bye counts
    assert abs(sum(res.playoff_pct(r) for r in range(1, 11)) - st.playoff_slots) < 1e-9
    assert abs(sum(res.title_pct(r) for r in range(1, 11)) - 1.0) < 1e-9


def test_dominant_team_wins_most_titles():
    st = _state(n_teams=8, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = _flat_strengths(rids, mu=100.0, sigma=20.0)
    strengths[1] = TeamStrength(1, mu=170.0, sigma=20.0)  # juggernaut
    fmt = StandardFormat(st.playoff_slots, st.num_byes)
    res = simulate(st, strengths, fmt, n_sims=3000, config_seed=3)
    assert res.title_pct(1) > 0.5
    assert res.playoff_pct(1) > 0.95
    for other in rids[1:]:
        assert res.title_pct(other) < res.title_pct(1)


def test_symmetric_league_is_roughly_uniform():
    st = _state(n_teams=8, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = _flat_strengths(rids, mu=110.0, sigma=25.0)
    fmt = StandardFormat(st.playoff_slots, st.num_byes)
    res = simulate(st, strengths, fmt, n_sims=4000, config_seed=11)
    expected = 1.0 / len(rids)
    for rid in rids:
        assert abs(res.title_pct(rid) - expected) < 0.06  # ~0.125 each


def test_stable_hash_is_process_stable():
    # builtin hash() is salted; ours must be fixed.
    assert stable_hash("LG-TEST") == stable_hash("LG-TEST")
    assert isinstance(stable_hash("x"), int)


# ---------------------------------------------------------------------------
# Phase 2 — strength providers
# ---------------------------------------------------------------------------

def test_roster_value_strength_works_at_preseason():
    st = _state(n_teams=4, completed_weeks=0)
    # give team 1 the strongest roster
    for i, t in enumerate(st.teams):
        t.player_ids = [f"p{t.roster_id}a", f"p{t.roster_id}b"]
    player_value = {
        "p1a": 9000, "p1b": 8000,
        "p2a": 5000, "p2b": 4000,
        "p3a": 3000, "p3b": 2500,
        "p4a": 2000, "p4b": 1500,
    }
    player_pos = {k: ("QB" if k.endswith("a") else "RB") for k in player_value}
    st.roster_slots = ["QB", "RB"]
    ctx = StrengthContext(player_value, player_pos, cfg={})
    out = RosterValueStrength().estimate(st, ctx)
    assert set(out) == {1, 2, 3, 4}
    assert out[1].mu > out[2].mu > out[3].mu > out[4].mu
    assert all(s.sigma > 0 for s in out.values())


def test_trailing_scores_requires_k_weeks():
    prov = TrailingScoresStrength()
    # 2 completed weeks, K default 3 → error
    st = _state(n_teams=4, completed_weeks=2,
                weekly_scores={r: [100.0, 110.0] for r in range(1, 5)})
    with pytest.raises(ValueError):
        prov.estimate(st, StrengthContext({}, {}, cfg={}))
    # 3 weeks → ok
    st3 = _state(n_teams=4, completed_weeks=3,
                 weekly_scores={r: [100.0, 110.0, 90.0] for r in range(1, 5)})
    out = prov.estimate(st3, StrengthContext({}, {}, cfg={}))
    assert set(out) == {1, 2, 3, 4}
    assert all(s.mu == pytest.approx(100.0) for s in out.values())


def test_providers_satisfy_protocol():
    assert isinstance(RosterValueStrength(), StrengthProvider)
    assert isinstance(TrailingScoresStrength(), StrengthProvider)
    assert isinstance(BlendedStrength(), StrengthProvider)


def test_auto_source_selection():
    cfg = {"outlook_trailing_min_weeks": 3.0}
    assert resolve_strength_source("auto", _state(completed_weeks=0), cfg) == "roster_value"
    assert resolve_strength_source("auto", _state(completed_weeks=2), cfg) == "blended"
    assert resolve_strength_source("auto", _state(completed_weeks=5), cfg) == "trailing_scores"
    # explicit override passes through untouched
    assert resolve_strength_source("own_model", _state(), cfg) == "own_model"


def test_starting_lineup_value_respects_slots_and_flex():
    pv = {"qb1": 9000, "qb2": 3000, "rb1": 5000, "rb2": 4000, "wr1": 6000}
    pp = {"qb1": "QB", "qb2": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR"}
    # 1 QB, 1 RB, 1 FLEX(RB/WR/TE) → qb1 + rb1 + best-remaining(wr1) = 20000
    val = starting_lineup_value(list(pv), pv, pp, ["QB", "RB", "FLEX"])
    assert val == pytest.approx(9000 + 5000 + 6000)


# ---------------------------------------------------------------------------
# Phase 4 — format seeding / byes / tiebreak
# ---------------------------------------------------------------------------

def test_seeding_by_record_then_points_for():
    fmt = StandardFormat(playoff_slots=4, num_byes=0)
    # (roster_id, win_credit, points_for, division)
    standings = [
        (1, 8.0, 1200.0, None),
        (2, 8.0, 1300.0, None),   # ties team 1 on record, wins on PF
        (3, 9.0, 1000.0, None),   # best record
        (4, 5.0, 1500.0, None),
    ]
    order = fmt.seed(standings)
    assert order[:3] == [3, 2, 1]   # 3 (record), then 2 > 1 on PF tiebreak


def test_byes_go_to_top_seeds():
    st = _state(n_teams=8, playoff_slots=6)
    assert st.num_byes == 2
    # dominant top-2 by strength should collect the bulk of byes
    rids = [t.roster_id for t in st.teams]
    strengths = _flat_strengths(rids, mu=100.0, sigma=15.0)
    strengths[1] = TeamStrength(1, 160.0, 15.0)
    strengths[2] = TeamStrength(2, 155.0, 15.0)
    res = simulate(st, strengths, StandardFormat(6, 2), n_sims=2000, config_seed=5)
    assert res.bye_pct(1) > 0.7
    assert res.bye_pct(2) > 0.7


def test_champion_is_a_playoff_team():
    fmt = get_playoff_format("standard", 6, 2)
    order = [10, 20, 30, 40, 50, 60, 70, 80]
    champ = fmt.champion(order, sample=lambda rid: 100.0 - rid)  # seed 10 always wins
    assert champ == 10


# ---------------------------------------------------------------------------
# Phase 5 — serializer shape
# ---------------------------------------------------------------------------

def test_serializer_shape_and_preseason_beta():
    st = _state(n_teams=6, completed_weeks=0)
    rids = [t.roster_id for t in st.teams]
    strengths = _flat_strengths(rids)
    res = simulate(st, strengths, StandardFormat(st.playoff_slots, st.num_byes),
                   n_sims=500, config_seed=0)
    payload = StandardSerializer().serialize(
        st, res, strengths, strength_source="roster_value",
        basis="consensus", you_user_id="u1")
    assert payload["league_id"] == "LG-TEST"
    assert payload["meta"]["is_preseason"] is True
    assert payload["meta"]["beta"] is True
    assert payload["meta"]["strength_source"] == "roster_value"
    assert len(payload["teams"]) == 6
    t0 = payload["teams"][0]
    for key in ("roster_id", "user_id", "is_you", "wins", "points_for",
                "strength", "odds"):
        assert key in t0
    for key in ("playoff_pct", "bye_pct", "title_pct", "projected_wins",
                "projected_seed"):
        assert key in t0["odds"]
    assert any(t["is_you"] for t in payload["teams"])
    # sorted by playoff_pct desc
    pcts = [t["odds"]["playoff_pct"] for t in payload["teams"]]
    assert pcts == sorted(pcts, reverse=True)


# ---------------------------------------------------------------------------
# Endpoint — flag gating + payload shape
# ---------------------------------------------------------------------------

USER = "313560442465169408"
TOKEN = "outlook-sess-tok"


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


def test_endpoint_404_when_flag_off(client):
    with patch.object(server, "is_enabled", lambda k: False):
        r = client.get("/api/league/outlook?league_id=LG-TEST", headers=_headers())
    assert r.status_code == 404


def test_endpoint_payload_when_flag_on(client):
    import backend.outlook as outlook_pkg
    st = _state(n_teams=6, completed_weeks=0)
    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"), \
         patch.object(outlook_pkg, "build_league_state", lambda *a, **k: st), \
         patch.object(server, "_get_universal_pool", lambda fmt: ([], {})):
        r = client.get("/api/league/outlook?league_id=LG-TEST", headers=_headers())
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["league_id"] == "LG-TEST"
    assert body["basis"] == "consensus"
    assert body["meta"]["beta"] is True
    assert len(body["teams"]) == 6
    # invariants hold end-to-end
    assert abs(sum(t["odds"]["title_pct"] for t in body["teams"]) - 1.0) < 0.02


def test_endpoint_redraft_501(client):
    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"):
        r = client.get("/api/league/outlook?league_id=LG&basis=redraft",
                       headers=_headers())
    assert r.status_code == 501


def test_endpoint_bad_basis_400(client):
    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"):
        r = client.get("/api/league/outlook?league_id=LG&basis=bogus",
                       headers=_headers())
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Offline backtest scaffold — NOT CI-gated. Skipped unless a captured-data
# fixture path is provided via FTF_OUTLOOK_BACKTEST env. Never fetches live.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("FTF_OUTLOOK_BACKTEST"),
    reason="offline backtest — set FTF_OUTLOOK_BACKTEST=/path/to/captured_2025.json",
)
def test_backtest_against_captured_season():
    """Scaffold: score simulated preseason odds against realized 2025 outcomes.

    Expected fixture shape (list of leagues), stubbed here — the operator drops
    captured data in and tunes the roster-value→points calibration knobs:
        [{"state": <LeagueState-as-dict>,
          "player_value": {...}, "player_pos": {...},
          "actual_champion_roster_id": 3,
          "actual_playoff_roster_ids": [1,3,4,5,7,9]}]
    """
    path = os.environ["FTF_OUTLOOK_BACKTEST"]
    with open(path) as f:
        leagues = json.load(f)
    from backend.outlook.pipeline import run_outlook  # noqa: F401
    briers = []
    for lg in leagues:
        # Reconstruct a LeagueState from the captured dict.
        raw = lg["state"]
        teams = [TeamState(**t) for t in raw["teams"]]
        st = LeagueState(
            league_id=raw["league_id"], platform=raw.get("platform", "sleeper"),
            regular_season_weeks=raw["regular_season_weeks"],
            playoff_slots=raw["playoff_slots"],
            num_byes=raw.get("num_byes", compute_num_byes(raw["playoff_slots"])),
            roster_slots=raw.get("roster_slots", []),
            teams=teams,
            schedule={int(k): [tuple(p) for p in v]
                      for k, v in raw.get("schedule", {}).items()},
            completed_weeks=raw.get("completed_weeks", 0),
            weekly_scores=raw.get("weekly_scores", {}),
        )
        payload = run_outlook(
            st, player_value=lg["player_value"], player_pos=lg["player_pos"],
            model_cfg={}, basis="consensus")
        champ_true = lg["actual_champion_roster_id"]
        for team in payload["teams"]:
            y = 1.0 if team["roster_id"] == champ_true else 0.0
            briers.append((team["odds"]["title_pct"] - y) ** 2)
    assert briers, "no leagues scored"
    mean_brier = sum(briers) / len(briers)
    # A useful model should beat a naive uniform prior; recorded for tuning.
    print(f"outlook backtest mean Brier (title): {mean_brier:.4f}")
