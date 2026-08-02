"""#232 follow-on — paste-first rankings import (flag `ranks.import`).

Covers the four contract layers:
  1. Parser tolerance (backend/rankings_import.py extract_name/parse):
     "rank. name", bare names, TSV/CSV rows with the name in any column,
     space-separated rows with trailing POS/TEAM codes, ignored headers
     and numbers-only lines.
  2. Match tiers: exact / suffix-normalized ("Kenneth Walker" → III) /
     initial form ("K. Walker") / ambiguous (≤3 candidates, seed-ordered) /
     unmatched.
  3. Apply semantics via POST /api/rankings/import-apply: the imported ids
     land at the top of the board in imported order and unlisted players
     keep their relative (consensus) order below — asserted both on the
     composed apply_reorder call and end-to-end on a real RankingService.
  4. Route auth/flag: 404 while `ranks.import` is off, 401 without a
     session, 400 on empty input.

Isolation pattern mirrors test_rankings_submit_authz.py: Flask test
client, in-memory SQLite, injected sessions, no network.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.ranking_service import Player, RankingService
from backend.rankings_import import (
    extract_name,
    match_rank_list,
    normalize_player_name,
    parse_rank_lines,
)

# ---------------------------------------------------------------------------
# Fixtures — a small universal pool with the interesting name shapes
# ---------------------------------------------------------------------------

def _p(pid, name, pos="WR", team="FA"):
    return Player(id=pid, name=name, position=pos, team=team, age=25)


POOL = [
    _p("p_allen",    "Josh Allen",          "QB", "BUF"),
    _p("p_chase",    "Ja'Marr Chase",       "WR", "CIN"),
    _p("p_walker",   "Kenneth Walker III",  "RB", "SEA"),
    _p("p_mhj",      "Marvin Harrison Jr.", "WR", "ARI"),
    _p("p_stroud",   "C.J. Stroud",         "QB", "HOU"),
    _p("p_lamb",     "CeeDee Lamb",         "WR", "DAL"),
    # Ambiguity pair: two pool players normalizing to the same name.
    _p("p_lj_qb",    "Lamar Jackson",       "QB", "BAL"),
    _p("p_lj_wr",    "Lamar Jackson",       "WR", "FA"),
]
SEED = {"p_lj_qb": 1900.0, "p_lj_wr": 1200.0, "p_allen": 1950.0,
        "p_chase": 1940.0, "p_walker": 1700.0, "p_mhj": 1800.0,
        "p_stroud": 1750.0, "p_lamb": 1930.0}


# ---------------------------------------------------------------------------
# 1. Parser tolerance
# ---------------------------------------------------------------------------

def test_extract_rank_dot_name():
    assert extract_name("1. Josh Allen") == "Josh Allen"
    assert extract_name("12) Ja'Marr Chase") == "Ja'Marr Chase"


def test_extract_bare_name():
    assert extract_name("Josh Allen") == "Josh Allen"


def test_extract_tsv_row_name_in_middle_column():
    assert extract_name("1\tJosh Allen\tQB\tBUF") == "Josh Allen"
    # POS code in an earlier column is skipped — name in ANY column.
    assert extract_name("1\tQB\tJosh Allen\tBUF") == "Josh Allen"


def test_extract_csv_row():
    assert extract_name("2,CeeDee Lamb,WR,DAL") == "CeeDee Lamb"


def test_extract_space_separated_row_drops_trailing_codes():
    assert extract_name("12 Josh Allen QB BUF") == "Josh Allen"


def test_headers_and_numbers_only_lines_ignored():
    assert extract_name("Rank,Player,Pos,Team") is None
    assert extract_name("Rank\tName\tValue") is None
    assert extract_name("123") is None
    assert extract_name("") is None
    assert extract_name("   ") is None


def test_parse_rank_lines_keeps_only_player_rows():
    lines = ["Rank,Player,Pos", "1. Josh Allen", "", "2,CeeDee Lamb,WR", "99"]
    parsed = parse_rank_lines(lines)
    assert [name for _line, name in parsed] == ["Josh Allen", "CeeDee Lamb"]


def test_normalize_strips_suffix_and_punctuation():
    assert normalize_player_name("Marvin Harrison Jr.") == "marvin harrison"
    assert normalize_player_name("Kenneth Walker III") == "kenneth walker"
    assert normalize_player_name("C.J. Stroud") == "cj stroud"


# ---------------------------------------------------------------------------
# 2. Match tiers
# ---------------------------------------------------------------------------

def _match_one(line):
    rows = match_rank_list([line], POOL, SEED)
    assert len(rows) == 1
    return rows[0]


def test_match_exact():
    row = _match_one("Josh Allen")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_allen"


def test_match_suffix_form_auto_accepts():
    # Pasted without the III — normalization makes it an exact match.
    row = _match_one("Kenneth Walker")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_walker"


def test_match_jr_suffix():
    row = _match_one("Marvin Harrison")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_mhj"


def test_match_initial_form():
    row = _match_one("K. Walker")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_walker"


def test_match_ambiguous_two_candidates_seed_ordered():
    row = _match_one("Lamar Jackson")
    assert row["status"] == "ambiguous"
    assert row["player"] is None
    ids = [c["id"] for c in row["candidates"]]
    assert ids == ["p_lj_qb", "p_lj_wr"]  # seed-desc: QB first
    assert len(ids) <= 3


def test_match_unmatched():
    row = _match_one("Zzz Qqq")
    assert row["status"] == "unmatched"
    assert row["player"] is None
    assert row["candidates"] == []


def test_match_full_paste_counts():
    text = [
        "Rank\tPlayer\tPos",
        "1\tJosh Allen\tQB",
        "2. CeeDee Lamb",
        "Lamar Jackson",
        "Nobody Realname",
    ]
    rows = match_rank_list(text, POOL, SEED)
    statuses = [r["status"] for r in rows]
    assert statuses == ["matched", "matched", "ambiguous", "unmatched"]


# ---------------------------------------------------------------------------
# 3a. Apply semantics — real RankingService end-to-end
# ---------------------------------------------------------------------------

def test_apply_reorder_full_board_permutation_semantics():
    """Imported order lands on top; unlisted players keep their relative
    consensus order below the imported block."""
    players = [_p(f"x{i}", f"Player Num{i}") for i in range(6)]
    seed = {f"x{i}": 1800.0 - i * 50 for i in range(6)}  # consensus x0..x5
    svc = RankingService(players, seed_ratings=seed)

    imported = ["x4", "x1"]  # user's pasted order
    current = [rp.player.id for rp in svc.get_rankings(None).rankings]
    assert current == ["x0", "x1", "x2", "x3", "x4", "x5"]
    full = imported + [pid for pid in current if pid not in set(imported)]
    svc.apply_reorder(position=None, ordered_ids=full)

    after = [rp.player.id for rp in svc.get_rankings(None).rankings]
    assert after == ["x4", "x1", "x0", "x2", "x3", "x5"]
    # Pure permutation: the Elo multiset is unchanged (value curve intact).
    elos_after = sorted(rp.elo for rp in svc.get_rankings(None).rankings)
    assert elos_after == sorted(seed.values())


# ---------------------------------------------------------------------------
# 3b/4. Routes — flag, auth, composition
# ---------------------------------------------------------------------------

TOKEN = "sess-import-1"
USER = "555555555555555555"
LEAGUE = "league_import_test"


def _h(token=TOKEN):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


class _FakeService:
    """get_rankings in a fixed current order + apply_reorder capture."""

    def __init__(self, ordered_ids):
        self._ordered = list(ordered_ids)
        self._elo_overrides = {}
        self.applied = None

    def get_rankings(self, position=None):
        rankings = [
            SimpleNamespace(player=SimpleNamespace(id=pid), elo=1500.0 - i)
            for i, pid in enumerate(self._ordered)
        ]
        return SimpleNamespace(rankings=rankings)

    def apply_reorder(self, position, ordered_ids):
        assert position is None
        self.applied = list(ordered_ids)
        self._ordered = list(ordered_ids)


def _mk_sess(svc):
    return {
        "user_id":       USER,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [],
        "service":       svc,
        "services":      {"1qb_ppr": svc},
        "trade_svc":     object(),
        "trade_svcs":    {"1qb_ppr": object()},
    }


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    svc = _FakeService(["a", "b", "c", "d", "e"])

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled",
                      lambda k: k == "ranks.import"), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "_get_universal_pool",
                      lambda fmt: (POOL, SEED)), \
         patch.object(server, "_refresh_taste_board_prior", MagicMock()), \
         patch.object(server, "_record_trends_snapshot", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = _mk_sess(svc)
        try:
            yield c, svc
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def test_import_match_route(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"names": ["1. Josh Allen", "Lamar Jackson",
                                          "Nobody Realname", "Rank,Player"]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["scoring_format"] == "1qb_ppr"
    assert body["counts"] == {"matched": 1, "ambiguous": 1, "unmatched": 1}
    assert [row["status"] for row in body["rows"]] == \
        ["matched", "ambiguous", "unmatched"]


def test_import_match_accepts_raw_text(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"text": "1. Josh Allen\n2. CeeDee Lamb\n"}))
    assert r.status_code == 200
    assert r.get_json()["counts"]["matched"] == 2


def test_import_match_requires_input(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"names": []}))
    assert r.status_code == 400


def test_import_match_requires_session(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match",
               headers={"Content-Type": "application/json"},
               data=json.dumps({"names": ["Josh Allen"]}))
    assert r.status_code == 401


def test_import_routes_404_when_flag_off(client):
    c, _svc = client
    with patch.object(server, "is_enabled", lambda k: False):
        r1 = c.post("/api/rankings/import-match", headers=_h(),
                    data=json.dumps({"names": ["Josh Allen"]}))
        r2 = c.post("/api/rankings/import-apply", headers=_h(),
                    data=json.dumps({"ordered_player_ids": ["a", "b"]}))
    assert r1.status_code == 404
    assert r2.status_code == 404


def test_import_apply_composes_full_board_order(client):
    """Imported ids first (imported order, deduped, pool-filtered), then the
    remaining board in its current order."""
    c, svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids":
                                ["d", "b", "d", "not_in_pool"]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["imported_count"] == 2
    assert body["board_count"] == 5
    assert svc.applied == ["d", "b", "a", "c", "e"]


def test_import_apply_publishes_member_rankings(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids": ["c", "a"]}))
    assert r.status_code == 200
    stored = db_module.load_member_rankings(
        league_id=LEAGUE, exclude_user_id="", scoring_format="1qb_ppr")
    assert USER in stored


def test_import_apply_rejects_unknown_ids_only(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids": ["zzz"]}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_matching_players"


def test_import_apply_requires_session(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply",
               headers={"Content-Type": "application/json"},
               data=json.dumps({"ordered_player_ids": ["a", "b"]}))
    assert r.status_code == 401
