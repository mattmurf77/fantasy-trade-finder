"""Unit tests for backend/power_rankings.compute_power_rankings (#142/#144)
plus route-level acceptance tests for #14 (picks group, updated_at,
superflex seed selection, rank-chip endpoint).

Covers both value bases (consensus / personal-with-consensus-fallback),
out-of-pool zero-value handling, deterministic ordering, and the #144
roster grouping contract (position groups, value-desc within group).

Route tests mirror the isolation pattern of test_league_prefs_authz.py:
Flask test client, injected sessions, patched loaders, no network/DB.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend.pick_values import pick_pool_value
from backend.power_rankings import compute_power_rankings
from backend.trade_service import elo_to_value


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str = "FA"
    age: int = 25


PLAYERS = {p.id: p for p in [
    _P("qb1", "Alpha QB",  "QB"),
    _P("qb2", "Beta QB",   "QB"),
    _P("rb1", "Alpha RB",  "RB"),
    _P("rb2", "Beta RB",   "RB"),
    _P("wr1", "Alpha WR",  "WR"),
    _P("te1", "Alpha TE",  "TE"),
    _P("k1",  "Some K",    "K"),   # out of the value pool
]}

SEED = {
    "qb1": 1800.0,
    "qb2": 1500.0,
    "rb1": 1700.0,
    "rb2": 1400.0,
    "wr1": 1600.0,
    "te1": 1450.0,
    # k1 deliberately absent — no consensus value
}

MEMBERS = [
    {"user_id": "u_a", "username": "alice", "display_name": "Alice",
     "player_ids": ["qb1", "rb1", "k1"]},
    {"user_id": "u_b", "username": "bob", "display_name": "Bob",
     "player_ids": ["qb2", "rb2", "wr1", "te1"]},
]


def _team(teams, user_id):
    return next(t for t in teams if t["user_id"] == user_id)


def test_consensus_totals_and_rank_order():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1800) + elo_to_value(1700) + 0.0, 1)
    exp_b = round(sum(elo_to_value(SEED[p]) for p in ("qb2", "rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # Alice's two studs outweigh Bob's four mid assets on this seed.
    assert exp_a > exp_b
    assert [t["user_id"] for t in teams] == ["u_a", "u_b"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_out_of_pool_player_contributes_zero():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    k_row = next(r for r in a["roster"] if r["player_id"] == "k1")
    assert k_row["value"] == 0.0
    # ...but the player still appears in the roster listing with metadata.
    assert k_row["name"] == "Some K"
    assert k_row["position"] == "K"


def test_personal_basis_overrides_with_consensus_fallback():
    # The caller tanks qb1 and pumps qb2; everyone else unranked → seed.
    board = {"qb1": 1400.0, "qb2": 1900.0}
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, board_elo=board)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1400) + elo_to_value(1700), 1)   # qb1 by board, rb1 by seed
    exp_b = round(elo_to_value(1900)                            # qb2 by board
                  + sum(elo_to_value(SEED[p]) for p in ("rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # The board flip inverts the league order vs the consensus basis.
    assert [t["user_id"] for t in teams] == ["u_b", "u_a"]
    assert _team(teams, "u_b")["rank"] == 1


def test_tie_breaks_deterministically_by_user_id():
    members = [
        {"user_id": "u_z", "username": "zed", "player_ids": ["qb1"]},
        {"user_id": "u_a", "username": "ann", "player_ids": ["qb1"]},
    ]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert [t["user_id"] for t in teams] == ["u_a", "u_z"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_roster_grouped_by_position_value_desc_within_group():
    members = [{
        "user_id": "u_b", "username": "bob",
        # Deliberately shuffled input order, two QBs to test in-group sort.
        "player_ids": ["te1", "qb2", "wr1", "qb1", "k1", "rb2", "rb1"],
    }]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    roster = teams[0]["roster"]
    assert [r["player_id"] for r in roster] == [
        "qb1", "qb2",        # QB group, value desc
        "rb1", "rb2",        # RB group, value desc
        "wr1",               # WR
        "te1",               # TE
        "k1",                # non-core positions trail
    ]


def test_position_summary_counts_and_values():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    assert a["positions"]["QB"]["count"] == 1
    assert a["positions"]["RB"]["count"] == 1
    assert a["positions"]["WR"] == {"count": 0, "value": 0.0}
    assert abs(a["positions"]["QB"]["value"] - round(elo_to_value(1800), 1)) < 0.2
    # K is not a core position — excluded from the summary, counted in total.
    assert "K" not in a["positions"]


# ---------------------------------------------------------------------------
# #183 — roster ids with no player metadata (IDP / team-DST ids outside the
# pool) are hidden from the roster listing; totals unchanged.
# ---------------------------------------------------------------------------

def test_unknown_roster_ids_hidden_from_roster():
    members = [{
        "user_id": "u_a", "username": "alice", "display_name": "Alice",
        # "4987" = an IDP-style Sleeper id, "SEA" = a team DST id — neither
        # has metadata in the pool. k1 has metadata but no value.
        "player_ids": ["qb1", "rb1", "k1", "4987", "SEA"],
    }]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    roster_ids = [r["player_id"] for r in teams[0]["roster"]]
    assert "4987" not in roster_ids
    assert "SEA" not in roster_ids
    # Known-position players stay, even out of the value pool (K).
    assert roster_ids == ["qb1", "rb1", "k1"]


def test_unknown_roster_ids_do_not_move_totals():
    with_idp = [{
        "user_id": "u_a", "username": "alice",
        "player_ids": ["qb1", "rb1", "k1", "4987", "SEA"],
    }]
    without_idp = [{
        "user_id": "u_a", "username": "alice",
        "player_ids": ["qb1", "rb1", "k1"],
    }]
    a = compute_power_rankings(with_idp, SEED, PLAYERS)[0]
    b = compute_power_rankings(without_idp, SEED, PLAYERS)[0]
    assert a["total_value"] == b["total_value"]
    assert a["positions_value"] == b["positions_value"]
    assert a["positions"] == b["positions"]


def test_member_without_valid_user_id_skipped():
    members = MEMBERS + [{"user_id": "", "username": "ghost", "player_ids": ["qb1"]}]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert {t["user_id"] for t in teams} == {"u_a", "u_b"}


# ---------------------------------------------------------------------------
# #14 FR1 — picks group + total decomposition (unit level)
# ---------------------------------------------------------------------------

def test_picks_group_totals_and_decomposition():
    picks = {"u_a": [{"label": "2026 1st", "value": 55.0},
                     {"label": "2027 2nd (from bob)", "value": 20.4}]}
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, picks_by_owner=picks)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    assert a["picks"]["count"] == 2
    assert a["picks"]["value"] == 75.4
    assert a["picks"]["items"] == [
        {"label": "2026 1st", "value": 55.0},
        {"label": "2027 2nd (from bob)", "value": 20.4},
    ]
    # total_value = positions_value + picks.value, exactly decomposable.
    assert a["total_value"] == round(a["positions_value"] + 75.4, 1)
    # No picks → empty group, total unchanged (players-only).
    assert b["picks"] == {"count": 0, "value": 0.0, "items": []}
    assert b["total_value"] == b["positions_value"]


def test_no_picks_arg_yields_empty_group_and_players_only_totals():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    for t in teams:
        assert t["picks"] == {"count": 0, "value": 0.0, "items": []}
        assert t["total_value"] == t["positions_value"]


# ---------------------------------------------------------------------------
# #14 acceptance (b) — personal basis with ZERO user rankings == consensus
# ---------------------------------------------------------------------------

def test_personal_basis_zero_board_equals_consensus_exactly():
    consensus = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    personal_empty = compute_power_rankings(MEMBERS, SEED, PLAYERS, board_elo={})
    assert personal_empty == consensus


# ---------------------------------------------------------------------------
# Route-level acceptance tests (#14) — /api/league/power-rankings +
# /api/league/rank-chip
# ---------------------------------------------------------------------------

LEAGUE = "league_pr_test"
TOKEN  = "sess-pr-test"

SEED_SF = {  # superflex pool seed — QBs pumped relative to 1QB
    "qb1": 1950.0,
    "qb2": 1700.0,
    "rb1": 1700.0,
    "rb2": 1400.0,
    "wr1": 1600.0,
    "te1": 1450.0,
}

# Owned-pick fixture rows: the load_draft_picks shape the /api/league/picks
# route consumes, pool_value written the way sync writes it (pick_pool_value
# with years_out = season - current season; current season 2026 here).
PICK_ROWS = [
    {"pick_id": f"{LEAGUE}_2026_1_1", "league_id": LEAGUE, "season": 2026,
     "round": 1, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(1, 0)},
    {"pick_id": f"{LEAGUE}_2027_2_2", "league_id": LEAGUE, "season": 2027,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 1, "original_username": "bob",
     "pool_value": pick_pool_value(2, 1)},
    {"pick_id": f"{LEAGUE}_2026_3_2", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(3, 0)},
]


class _EmptyBoardSvc:
    """Ranking service stub: a caller who has ranked zero players."""
    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[])


def _h(token=TOKEN):
    return {"X-Session-Token": token}


def _mk_sess(user_id="u_a", fmt="1qb_ppr", svc=None):
    """Minimal session satisfying _require_initialized_session."""
    return {
        "user_id":       user_id,
        "active_format": fmt,
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE, platform=None,
                                         members=[]),
        "players":       list(PLAYERS.values()),
        "trade_svc":     object(),
        "trade_svcs":    {fmt: object()},
        "services":      {fmt: svc} if svc is not None else {},
        "service":       svc,
        "user_roster":   [],
    }


def _fake_pool(fmt):
    return (list(PLAYERS.values()), SEED_SF if fmt == "sf_tep" else dict(SEED))


def _members_rows(league_id):
    if league_id == LEAGUE:
        return [dict(m) for m in MEMBERS]
    return []


def _pick_rows(league_id):
    return [dict(p) for p in PICK_ROWS] if league_id == LEAGUE else []


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    server._rank_chip_cache.clear()
    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_league_members", _members_rows), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw: _pick_rows(league_id)), \
         patch.object(server, "_get_universal_pool", _fake_pool):
        try:
            yield c
        finally:
            server._rank_chip_cache.clear()
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _install_sess(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _get(c, path):
    r = c.get(path, headers=_h())
    return r.status_code, json.loads(r.data)


# (a) team totals reconcile with elo_to_value over the same rosters ---------

def test_route_totals_reconcile_with_elo_to_value(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")

    exp_players = round(elo_to_value(SEED["qb1"]) + elo_to_value(SEED["rb1"])
                        + 0.0, 1)                       # k1 out of pool → 0
    exp_picks = round(pick_pool_value(1, 0) + pick_pool_value(2, 1), 1)
    assert abs(a["positions_value"] - exp_players) < 0.2
    assert abs(a["picks"]["value"] - exp_picks) < 0.2
    assert abs(a["total_value"] - (exp_players + exp_picks)) < 0.3


# (b) personal basis, zero rankings → identical to consensus ----------------

def test_route_personal_zero_board_matches_consensus(client):
    _install_sess(_mk_sess(svc=_EmptyBoardSvc()))
    with patch.object(server, "_verified_read_denial", lambda s: None):
        code_p, body_p = _get(
            client, f"/api/league/power-rankings?league_id={LEAGUE}&basis=personal")
    code_c, body_c = _get(
        client, f"/api/league/power-rankings?league_id={LEAGUE}&basis=consensus")
    assert code_p == code_c == 200
    assert body_p["basis"] == "personal"
    assert body_p["teams"] == body_c["teams"]


# (c) superflex league uses the sf seed pool --------------------------------

def test_route_superflex_uses_sf_seed(client):
    _install_sess(_mk_sess(fmt="sf_tep"))
    pool_spy = MagicMock(side_effect=_fake_pool)
    with patch.object(server, "_get_universal_pool", pool_spy):
        code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert body["scoring_format"] == "sf_tep"
    pool_spy.assert_called_once_with("sf_tep")
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    exp_qb_sf = round(elo_to_value(SEED_SF["qb1"]), 1)
    assert abs(a["positions"]["QB"]["value"] - exp_qb_sf) < 0.2
    assert a["positions"]["QB"]["value"] > round(elo_to_value(SEED["qb1"]), 1)


# (d) picks group == sum(pick_pool_value) == /api/league/picks data ---------

def test_route_picks_group_matches_pick_pool_value_and_picks_route(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")

    assert a["picks"]["count"] == 2
    assert a["picks"]["value"] == round(
        pick_pool_value(1, 0) + pick_pool_value(2, 1), 1)
    assert b["picks"]["value"] == round(pick_pool_value(3, 0), 1)
    labels = [i["label"] for i in a["picks"]["items"]]
    assert labels == ["2026 1st", "2027 2nd (from bob)"]

    # Cross-check against /api/league/picks for the same fixture.
    code2, picks_body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code2 == 200
    for team in (a, b):
        rows = [p for p in picks_body["all_picks"]
                if p["owner_user_id"] == team["user_id"]]
        assert team["picks"]["count"] == len(rows)
        assert team["picks"]["value"] == round(
            sum(p["pool_value"] for p in rows), 1)
        assert sorted(i["label"] for i in team["picks"]["items"]) == \
               sorted(p["label"] for p in rows)


# (e) updated_at present + parseable ----------------------------------------

def test_route_updated_at_present_and_parseable(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    ts = datetime.fromisoformat(body["updated_at"])
    assert ts.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - ts).total_seconds()) < 60


# (f) rank-chip route --------------------------------------------------------

def test_rank_chip_consistent_with_full_payload(client):
    _install_sess(_mk_sess(user_id="u_b"))
    code, full = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    you = next(t for t in full["teams"] if t["is_you"])

    code2, chip = _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    assert code2 == 200
    assert chip["rank"] == you["rank"]
    assert chip["team_count"] == len(full["teams"])
    assert chip["basis"] == "consensus"
    assert datetime.fromisoformat(chip["updated_at"]).tzinfo is not None


def test_rank_chip_cached_between_calls(client):
    _install_sess(_mk_sess())
    _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    with patch.object(server, "_power_ranking_inputs",
                      MagicMock(side_effect=AssertionError("cache miss"))):
        code, chip = _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    assert code == 200
    assert chip["rank"] == 1


def test_rank_chip_demo_league_via_session_fallback(client):
    sess = _mk_sess(user_id="u_demo")
    sess["league"] = SimpleNamespace(
        league_id="league_demo", platform=None,
        members=[SimpleNamespace(user_id="u_mate", username="mate",
                                 roster=["qb2", "rb2"])])
    sess["user_roster"] = ["qb1", "rb1"]
    _install_sess(sess)
    code, chip = _get(client, "/api/league/rank-chip?league_id=league_demo")
    assert code == 200
    assert chip["team_count"] == 2
    assert chip["rank"] == 1          # qb1+rb1 outvalues qb2+rb2 on this seed
    assert chip["basis"] == "consensus"


def test_rank_chip_espn_league_no_picks(client):
    espn_league = "espn:12345"
    espn_members = [
        {"user_id": "u_a", "username": "alice", "display_name": "Alice",
         "player_ids": ["qb1", "rb1"]},
        {"user_id": "espn:12345.t2", "username": "Team 2",
         "display_name": "Team 2", "player_ids": ["qb2", "rb2", "wr1"]},
    ]
    _install_sess(_mk_sess())
    with patch.object(server, "load_league_members",
                      lambda lid: espn_members if lid == espn_league else []):
        code, chip = _get(client, f"/api/league/rank-chip?league_id={espn_league}")
    assert code == 200
    assert chip["team_count"] == 2
    assert chip["rank"] in (1, 2)

    # ESPN leagues carry no draft_picks rows — full payload shows the empty
    # picks group rather than erroring.
    with patch.object(server, "load_league_members",
                      lambda lid: espn_members if lid == espn_league else []):
        code2, full = _get(client,
                           f"/api/league/power-rankings?league_id={espn_league}")
    assert code2 == 200
    for t in full["teams"]:
        assert t["picks"] == {"count": 0, "value": 0.0, "items": []}
