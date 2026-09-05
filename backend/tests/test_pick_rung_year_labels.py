"""#207 — year-explicit generic pick rungs on /api/rankings + /api/trio.

Option A (docs/feedback/items/207-rookie-draft-detection/plan.md): the 12
Early/Mid/Late rungs keep their stable ids and their pool membership forever;
only the SERVED label and pick_value become year-explicit, per the active
league's cached rookie-draft verdict.

Pins:
  * not_drafted / unknown / never-checked → "2026 Early 1st", value unchanged
  * drafted                               → "2027 Early 1st", value discounted
  * flag off                              → byte-identical to today
  * rung ids, board Elo and rank are never touched
  * real players are never relabelled

Flask test client + in-memory SQLite + an injected fake ranking service — no
network, no universal pool build.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata, leagues_table
from backend.pick_values import GENERIC_PICK_SEEDS, YEAR_DISCOUNT
from backend.ranking_service import Player, RankedPlayer, RankSet, MatchupTrio
from backend.trade_service import League, elo_to_value

UID = "u_207"
LEAGUE_ID = "1312076055586050048"
TOKEN = "sess-207-tok"

_SEED_1_EARLY = GENERIC_PICK_SEEDS[(1, "Early")]
_PV_1_EARLY = round(max(0, (_SEED_1_EARLY - 1200) / 6), 1)


def _pick(rnd=1, tier="Early"):
    seed = GENERIC_PICK_SEEDS[(rnd, tier)]
    return Player(
        id=f"generic_pick_{rnd}_{tier.lower()}",
        name=f"{tier} {'1st' if rnd == 1 else '2nd'} Round Pick",
        position="RB", team="PICK", age=0, years_experience=0,
        pick_value=round(max(0, (seed - 1200) / 6), 1),
        search_rank=10,
    )


def _human():
    return Player(id="4034", name="Christian McCaffrey", position="RB",
                  team="SF", age=29, years_experience=8, search_rank=3)


class _FakeService:
    """Minimal stand-in for RankingService — the relabel runs on the
    serialized dicts, so the ranking math is irrelevant here."""

    def __init__(self, players):
        self._players = players

    def get_rankings(self, position=None):
        return RankSet(
            position=position,
            rankings=[RankedPlayer(p, 1500.0 + i, 1, 0, i + 1)
                      for i, p in enumerate(self._players)],
            interaction_count=0, threshold=10, threshold_met=False,
            version=1, computed_at="2026-08-05T00:00:00Z",
        )

    def get_next_trio(self, position=None, skipped_player_ids=None,
                      scoped=False):
        a, b, c = (self._players + self._players + self._players)[:3]
        return MatchupTrio(a, b, c, reasoning="test")

    def _tier_info(self, position=None):
        return {}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = [_pick(1, "Early"), _pick(2, "Mid"), _human()]
    sess = {"verified": True,
        "user_id": UID,
        "active_format": "1qb_ppr",
        "last_active": 0.0,
        "service": _FakeService(players),
        "league": League(league_id=LEAGUE_ID, name="Lakeview",
                         platform="sleeper", members=[]),
        "user_roster": [],
    }

    flags = {"picks.rank_year_labels"}
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        server._invalidate_draft_context_cache()
        try:
            yield c, flags
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            server._invalidate_draft_context_cache()


def _seed_league(season="2026", status=None, confidence=None):
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.delete())
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ID, user_id=UID, name="Lakeview",
            season=season, total_rosters=12, platform="sleeper",
            draft_status=status, draft_status_confidence=confidence,
            draft_status_checked_at="2026-08-05T00:00:00+00:00",
        ))
    server._invalidate_draft_context_cache()


def _get(c, path):
    r = c.get(path, headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200, r.data
    return json.loads(r.data)


def _by_id(rows):
    return {r["id"]: r for r in rows}


# ── labels ─────────────────────────────────────────────────────────────────

def test_not_drafted_league_shows_current_year_picks(client):
    c, _ = client
    _seed_league(status="not_drafted", confidence="high")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "2026 Early 1st"
    assert rows["generic_pick_2_mid"]["name"] == "2026 Mid 2nd"


def test_drafted_league_rolls_the_rungs_to_next_season(client):
    c, _ = client
    _seed_league(status="drafted", confidence="high")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "2027 Early 1st"
    assert rows["generic_pick_2_mid"]["name"] == "2027 Mid 2nd"


@pytest.mark.parametrize("status", [None, "unknown"])
def test_fail_safe_unknown_status_keeps_the_current_year(client, status):
    """A phantom current-year pick is visible and self-correcting; a silently
    hidden real asset produces no artifact at all."""
    c, _ = client
    _seed_league(status=status, confidence="low")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "2026 Early 1st"
    assert rows["generic_pick_1_early"]["pick_value"] == _PV_1_EARLY


def test_medium_confidence_drafted_still_rolls_the_year(client):
    """Confidence gates nothing on this surface — only the verdict does."""
    c, _ = client
    _seed_league(status="drafted", confidence="medium")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "2027 Early 1st"


def test_league_season_drives_the_year_not_the_wall_clock(client):
    c, _ = client
    _seed_league(season="2027", status="not_drafted")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "2027 Early 1st"


# ── values ─────────────────────────────────────────────────────────────────

def test_not_drafted_value_is_an_exact_no_op(client):
    c, _ = client
    _seed_league(status="not_drafted")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["pick_value"] == _PV_1_EARLY


def test_drafted_value_takes_one_year_of_discount(client):
    c, _ = client
    _seed_league(status="drafted")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    # D-079: the rate is per round, so the 1st rung is now an exact no-op
    # even when the relabel rolls it to next season — the rung's NAME moves,
    # its value does not.
    assert rows["generic_pick_1_early"]["pick_value"] == _PV_1_EARLY
    assert rows["generic_pick_1_early"]["name"] == "2027 Early 1st"
    # The 2nd rung still takes its year of discount, in VALUE space, matching
    # pick_pool_value (and therefore the owned 2027 pick of the same round).
    pv2 = rows["generic_pick_2_mid"]["pick_value"]
    seed_2_mid = GENERIC_PICK_SEEDS[(2, "Mid")]
    assert pv2 < round(max(0, (seed_2_mid - 1200) / 6), 1)
    assert elo_to_value(1200 + 6 * pv2) == pytest.approx(
        elo_to_value(seed_2_mid) * YEAR_DISCOUNT, rel=0.01)


def test_relabel_never_touches_ids_elo_or_rank(client):
    c, _ = client
    _seed_league(status="drafted")
    rows = _get(c, "/api/rankings")["rankings"]
    assert [r["id"] for r in rows] == ["generic_pick_1_early",
                                       "generic_pick_2_mid", "4034"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert [r["elo"] for r in rows] == [1500.0, 1501.0, 1502.0]


def test_real_players_are_untouched(client):
    c, _ = client
    _seed_league(status="drafted")
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["4034"]["name"] == "Christian McCaffrey"
    assert "pick_value" not in rows["4034"]


# ── /api/trio parity ───────────────────────────────────────────────────────

def test_trio_gets_the_same_labels_as_the_board(client):
    c, _ = client
    _seed_league(status="drafted")
    body = _get(c, "/api/trio")
    assert body["player_a"]["name"] == "2027 Early 1st"
    assert body["player_b"]["name"] == "2027 Mid 2nd"
    assert body["player_c"]["name"] == "Christian McCaffrey"


def test_trio_current_year_when_not_drafted(client):
    c, _ = client
    _seed_league(status="not_drafted")
    body = _get(c, "/api/trio")
    assert body["player_a"]["name"] == "2026 Early 1st"


# ── flag off + abstention ──────────────────────────────────────────────────

def test_flag_off_is_byte_identical(client):
    c, flags = client
    _seed_league(status="drafted", confidence="high")
    on = _get(c, "/api/rankings")
    flags.discard("picks.rank_year_labels")
    server._invalidate_draft_context_cache()
    off = _get(c, "/api/rankings")
    assert off != on
    rows = _by_id(off["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "Early 1st Round Pick"
    assert rows["generic_pick_1_early"]["pick_value"] == _PV_1_EARLY
    assert rows["generic_pick_2_mid"]["name"] == "Mid 2nd Round Pick"


def test_flag_off_trio_is_byte_identical(client):
    c, flags = client
    _seed_league(status="drafted", confidence="high")
    flags.discard("picks.rank_year_labels")
    server._invalidate_draft_context_cache()
    body = _get(c, "/api/trio")
    assert body["player_a"]["name"] == "Early 1st Round Pick"
    assert body["player_a"]["pick_value"] == _PV_1_EARLY


def test_no_league_row_abstains(client):
    """A league we have never persisted (or whose row carries no season)
    must not get invented years."""
    c, _ = client
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.delete())
    server._invalidate_draft_context_cache()
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "Early 1st Round Pick"


def test_demo_league_abstains(client):
    c, _ = client
    _seed_league(status="drafted")
    with server._sessions_lock:
        server._sessions[TOKEN]["league"] = League(
            league_id="league_demo", name="Demo", platform="demo", members=[])
    rows = _by_id(_get(c, "/api/rankings")["rankings"])
    assert rows["generic_pick_1_early"]["name"] == "Early 1st Round Pick"


# ── the label helper itself ────────────────────────────────────────────────

def test_year_label_is_not_longer_than_the_label_it_replaces():
    """Mobile name boxes (QuickSet chips, Tiers tiles, Trios two-line
    mini-cards) size off these strings — the year-explicit form must not be
    the longest thing they have ever rendered."""
    from backend.pick_values import generic_pick_label, year_pick_label
    for (rnd, tier) in GENERIC_PICK_SEEDS:
        assert len(year_pick_label(2026, rnd, tier)) < \
            len(generic_pick_label(rnd, tier))
