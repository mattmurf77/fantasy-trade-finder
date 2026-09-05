"""D-160 (#346/#381, supersedes FB-161) — Quick Set saves HOLD unselected players.

The #161 demote rule (`demoted_pids` on /api/tiers/save pinned passed-over
players to RankingService.DEMOTED_ELO, below every band) is removed on the
operator's #381 ruling: a save mutates ONLY the assigned and cleared pids.
Old binaries (v1.10.0–v1.16.x) still send `demoted_pids`; the route accepts
and silently ignores it like any unknown body key — no pin, no error, no
response change. `cleared_pids` keeps its consensus-restore meaning, and the
old "demote wins over clear" precedence dies with the demote: a legacy
revisit-deselect (pid in both keys) now restores consensus. Explicit demotion
survives via the FA (`waivers`) rung, revisit-deselect, and TiersScreen.

Filename kept for history (this file pinned the #161 contract until
2026-08-24). Test matrix T-1…T-7 from
docs/feedback/items/346-quickset-tier-drop/prd.md §6a — every case asserts a
held tier VALUE, and each is red under its named sabotage (for
T-1/T-3/T-5/T-6, "old code" — re-adding the parse + pin loops — is the
sabotage).

Route harness follows test_trends_history_writers.py (isolated SQLite engine
patched into backend.database, Flask test client, flags forced off except
where a test opts in) but with a REAL RankingService, because the assertions
are about override values, not route wiring.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata, users_table, players_table
from backend.ranking_service import Player, RankingService
from backend.trade_service import League

FMT = "1qb_ppr"
POS = "WR"
USER = "user_quickset_hold"
TOKEN = "quickset-hold-token"
SEASON = server._CURRENT_SEASON  # league_demo scopes to the process default

# Seeds place each player squarely inside a known band
# (backend/tier_config.json, 1qb_ppr — bands are position-uniform):
#   firsts_4plus 1927–1972 · first_1 1580–1785 · second 1370–1575 ·
#   waivers 1150–1215.  nabers mirrors the #381 repro; jamo the #161 case.
_POOL = [
    ("nabers", 1950.0),   # firsts_4plus — the passed-over player
    ("w1",     1760.0),
    ("w2",     1740.0),
    ("w3",     1720.0),
    ("jamo",   1650.0),   # first_1 consensus
    ("mid",    1450.0),   # second
    ("rk1",    1500.0),   # rookies (players-table rows below) — T-5
    ("rk2",    1480.0),
]
ROOKIES = ("rk1", "rk2")


def _svc():
    players = [Player(id=pid, name=pid.upper(), position=POS, team="AAA", age=24)
               for pid, _ in _POOL]
    svc = RankingService(players=players,
                         seed_ratings={pid: elo for pid, elo in _POOL})
    svc._scoring_format = FMT
    return svc


def _tier_of(svc, pid):
    elo = svc._compute_elo(svc._pool(POS))[pid]
    return RankingService.tier_for_elo(elo, POS, FMT)


def _elo_of(svc, pid):
    return svc._compute_elo(svc._pool(POS))[pid]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=USER, created_at="2026-08-24T00:00:00+00:00"))
        for pid in ROOKIES:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Rookie {pid}", position=POS,
                team="AAA", years_exp=0, rookie_year=str(SEASON)))
        for pid, _ in _POOL:
            if pid not in ROOKIES:
                conn.execute(players_table.insert().values(
                    player_id=pid, full_name=f"Vet {pid}", position=POS,
                    team="AAA", years_exp=5, rookie_year="2021"))

    svc = _svc()
    sess = {"verified": True,
        "user_id": USER,
        "active_format": FMT,
        "last_active": 0.0,
        "service": svc,
        # league_demo: skips the member_rankings publish and scopes the
        # rookie season to the process default — neither is under test here.
        "league": League(league_id="league_demo", name="QS",
                         platform="sleeper", members=[]),
        "user_roster": [],
        "players": svc._pool(POS),
        "trade_svc": MagicMock(),
    }

    flags: set[str] = set()          # tests opt in (T-5 adds rookie_subset)
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "touch_user_activity", MagicMock()):
        server._invalidate_rookie_ids_memo()
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, svc, flags
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            server._invalidate_rookie_ids_memo()


def _save(client, body, expect=200):
    r = client.post("/api/tiers/save", json=body,
                    headers={"X-Session-Token": TOKEN})
    assert r.status_code == expect, r.data
    return json.loads(r.data)


# ─── T-1 — the Nabers repro, route level ────────────────────────────────────

def test_passed_over_player_holds_tier(harness):
    """The exact old-binary payload: 3 other WRs saved into firsts_4plus,
    nabers named in demoted_pids. He must hold his tier, byte-unchanged."""
    client, svc, _ = harness
    assert _tier_of(svc, "nabers") == "firsts_4plus"
    elo_before = _elo_of(svc, "nabers")

    _save(client, {"position": POS,
                   "tiers": {"firsts_4plus": ["w1", "w2", "w3"]},
                   "demoted_pids": ["nabers"]})

    assert _elo_of(svc, "nabers") == elo_before          # byte-unchanged
    assert _tier_of(svc, "nabers") == "firsts_4plus"
    assert "nabers" not in svc._elo_overrides
    # …while the three selected really did land in the saved band.
    for pid in ("w1", "w2", "w3"):
        assert 1927 <= svc._elo_overrides[pid] <= 1972
        assert _tier_of(svc, pid) == "firsts_4plus"


# ─── T-2 — the legacy key is ignored, silently ──────────────────────────────

def test_demoted_pids_key_is_ignored(harness):
    """An old-binary request naming a pid with an existing override: 200 ok,
    override byte-unchanged, and the response key set is identical to the
    same request without the key (no echo, no warning)."""
    client, svc, _ = harness
    svc._elo_overrides["mid"] = 1500.0

    with_key = _save(client, {"position": POS,
                              "tiers": {"firsts_4plus": ["w1"]},
                              "demoted_pids": ["mid"]})
    assert with_key["ok"] is True
    assert svc._elo_overrides["mid"] == 1500.0           # byte-unchanged

    without_key = _save(client, {"position": POS,
                                 "tiers": {"firsts_4plus": ["w1"]}})
    assert set(with_key) == set(without_key)


# ─── T-3 — clear restores consensus, even from a legacy both-keys request ───

def test_clear_restores_consensus_even_with_legacy_demote_key(harness):
    """Old binaries send a revisit-deselect pid in BOTH cleared_pids and
    demoted_pids (the #161 demote-beats-clear case). Under D-160 the clear
    wins: override deleted, consensus tier restored."""
    client, svc, _ = harness
    _save(client, {"position": POS, "tiers": {"second": ["jamo", "w1"]}})
    assert _tier_of(svc, "jamo") == "second"

    _save(client, {"position": POS, "tiers": {"second": ["w1"]},
                   "cleared_pids": ["jamo"], "demoted_pids": ["jamo"]})
    assert "jamo" not in svc._elo_overrides
    assert _tier_of(svc, "jamo") == "first_1"            # consensus, not FA


# ─── T-4 — the explicit-demote affordance (FA rung) survives ────────────────

def test_fa_rung_save_pins_waivers_band(harness):
    """Selecting a player on the walk's `waivers` rung is THE explicit
    demote gesture — it must keep pinning into the FA band (1150–1215)."""
    client, svc, _ = harness
    _save(client, {"position": POS, "tiers": {"waivers": ["mid"]}})
    assert 1150 <= svc._elo_overrides["mid"] <= 1215
    assert _tier_of(svc, "mid") == "waivers"


# ─── T-5 — the scoped (rookie) lane holds too ───────────────────────────────

def test_scoped_save_holds_passed_over_rookie(harness):
    """Rookie-scoped route save with a legacy demoted_pids covering a visible
    unselected rookie AND an unshown vet: the rookie keeps his prior
    value/tier, the vet's override is byte-unchanged."""
    client, svc, flags = harness
    flags.add("ranks.rookie_subset")
    svc._elo_overrides.update({"rk2": 1480.0, "w1": 1760.0})

    _save(client, {"position": POS, "tiers": {"second": ["rk1"]},
                   "scope": "rookie", "via": "rookie_quickset",
                   "demoted_pids": ["rk2", "w1"]})

    assert svc._elo_overrides["rk2"] == 1480.0           # visible rookie: held
    assert _tier_of(svc, "rk2") == "second"
    assert svc._elo_overrides["w1"] == 1760.0            # unshown vet: untouched
    # …and the assigned rookie was written through the subset lane.
    assert "rk1" in svc._elo_overrides


# ─── T-6 — the emptiness guard is reverted ──────────────────────────────────

def test_empty_save_still_400s(harness):
    """Nothing assigned, nothing cleared → 400, with and without a legacy
    demoted_pids list. A demote-only body no longer counts as 'something to
    do' — it used to 200 while silently pinning players."""
    client, _, _ = harness
    _save(client, {"position": POS, "tiers": {}}, expect=400)
    _save(client, {"position": POS, "tiers": {},
                   "demoted_pids": ["nabers"]}, expect=400)


# ─── T-7 — the parameter cannot silently return ─────────────────────────────

def test_apply_tiers_signature_has_no_demote_param():
    """Red under 'parameter restored but pin loop left out', which T-1/T-5
    would miss: the kwarg itself must TypeError."""
    svc = _svc()
    with pytest.raises(TypeError):
        svc.apply_tiers(POS, {"first_1": ["w1"]}, FMT, demoted_pids=["jamo"])
    with pytest.raises(TypeError):
        svc.apply_tiers_subset(POS, {"first_1": ["rk1"]},
                               scope_pids={"rk1", "rk2"},
                               scoring_format=FMT, demoted_pids=["rk2"])
