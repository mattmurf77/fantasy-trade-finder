"""FB-191 — cross-format board derivation (read-time auto-sync).

Rules pinned here (flag `rankings.cross_format_derive`; see the #191 block
in backend/server.py above _derive_board_from_format):

  1. Explicit-over-derived — derivation fires only when the member has NO
     member_rankings rows in the requested format; real rows always win.
  2. Read-time — nothing is materialized; the derived board is recomputed
     from the source format's current snapshot on every read.
  3. Value-mapped — per position, the source rank ORDER is preserved and
     magnitudes are re-dealt from the target format's consensus seed curve
     (the #124 tiers/copy math), never label/Elo-copied.
  4. Labeled — Mode B responses carry additive *_derived markers so UIs can
     mark derived boards (the #192 R* badge).
"""

from dataclasses import dataclass

import pytest

import backend.database as db
import backend.server as srv

CALLER = "caller_uid"
OPP = "opp_uid"


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str | None = None
    age: int | None = None


_POOL_PLAYERS = [
    _P("stud",  "Stud Man",   "WR", "CIN", 26),
    _P("good",  "Good Guy",   "RB", "DET", 24),
    _P("mid",   "Mid Player", "TE", "SF",  27),
    _P("bench", "Bench Body", "RB", "NYJ", 28),
]
_SEED = {"stud": 1800.0, "good": 1650.0, "mid": 1500.0, "bench": 1350.0}


@pytest.fixture(autouse=True)
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr",
        {"players": _POOL_PLAYERS, "seed": dict(_SEED)},
    )
    # Flag on for these tests regardless of the deployment config.
    monkeypatch.setattr(
        srv, "is_enabled",
        lambda k: k == "rankings.cross_format_derive",
    )
    yield


def _post_authed(body, boards_by_fmt, monkeypatch, token="derive-sess"):
    """POST /api/trade/evaluate Mode B with per-format mocked boards."""
    monkeypatch.setattr(
        db, "load_member_rankings",
        lambda league_id, exclude_user_id="", scoring_format="1qb_ppr":
            boards_by_fmt.get(scoring_format, {}),
    )
    with srv._sessions_lock:
        srv._sessions[token] = {"user_id": CALLER, "active_format": "1qb_ppr",
                                "last_active": 0.0}
    try:
        with srv.app.test_client() as c:
            return c.post("/api/trade/evaluate", json=body,
                          headers={"X-Session-Token": token})
    finally:
        with srv._sessions_lock:
            srv._sessions.pop(token, None)


_MODE_B_BODY = {
    "give_player_ids": ["stud"], "receive_player_ids": ["good"],
    "league_id": "L1", "opponent_user_id": OPP,
}


# ── The derivation helper itself (rule 3) ─────────────────────────────────

def test_derive_preserves_source_order_with_target_magnitudes():
    # Opponent's SF board flips the two RBs: bench > good.
    src = {"bench": 1800.0, "good": 1500.0}
    derived = srv._derive_board_from_format(src, "1qb_ppr")
    # Target RB seeds {good: 1650, bench: 1350} dealt best-first to the
    # SOURCE order → bench takes 1650, good takes 1350. Order is the
    # user's; magnitudes are this format's consensus.
    assert derived["bench"] == 1650.0
    assert derived["good"] == 1350.0


def test_derive_is_per_position_and_skips_unknown_pids():
    src = {"stud": 1200.0, "good": 1900.0, "ghost": 1700.0}
    derived = srv._derive_board_from_format(src, "1qb_ppr")
    # Single-member position groups map to their own seed (no cross-
    # position mixing — same shape as apply_value_map / tiers copy).
    assert derived["stud"] == _SEED["stud"]
    assert derived["good"] == _SEED["good"]
    assert "ghost" not in derived


# ── Mode B wiring (rules 1, 2, 4) ─────────────────────────────────────────

def test_opponent_ranked_only_in_other_format_is_derived_not_unranked(monkeypatch):
    boards = {
        "1qb_ppr": {CALLER: {"username": "me",
                             "elo_ratings": {"stud": 1500.0, "good": 1800.0}}},
        "sf_tep":  {OPP: {"username": "jon",
                          "elo_ratings": {"stud": 1800.0, "good": 1500.0}}},
    }
    r = _post_authed(_MODE_B_BODY, boards, monkeypatch)
    assert r.status_code == 200
    d = r.get_json()
    # The operator's case: the partner HAS ranked — never "consensus".
    assert d["basis"] == "divergence"
    assert d["opponent_has_rankings"] is True
    assert d["opponent_username"] == "jon"
    # Rule 4 — the derived board is labeled, additively.
    assert d["opponent_board_derived"] is True
    assert d["opponent_board_derived_from"] == "sf_tep"
    assert d["your_board_derived"] is False


def test_explicit_rankings_win_over_derivation(monkeypatch):
    boards = {
        "1qb_ppr": {
            CALLER: {"username": "me",  "elo_ratings": {"stud": 1500.0}},
            OPP:    {"username": "jon", "elo_ratings": {"stud": 1800.0, "good": 1500.0}},
        },
        # A conflicting sf_tep board that must be IGNORED (rule 1).
        "sf_tep": {OPP: {"username": "jon",
                         "elo_ratings": {"stud": 1000.0, "good": 1990.0}}},
    }
    d = _post_authed(_MODE_B_BODY, boards, monkeypatch).get_json()
    assert d["basis"] == "divergence"
    assert d["opponent_board_derived"] is False
    assert d["opponent_board_derived_from"] is None
    # Deltas come from the explicit 1qb board: they receive stud (their
    # 1800) and give good (their 1500) → positive their_delta.
    assert d["their_value_delta"] > 0


def test_caller_board_derives_too(monkeypatch):
    boards = {
        "1qb_ppr": {OPP: {"username": "jon",
                          "elo_ratings": {"stud": 1800.0, "good": 1500.0}}},
        "sf_tep":  {CALLER: {"username": "me",
                             "elo_ratings": {"stud": 1500.0, "good": 1800.0}}},
    }
    d = _post_authed(_MODE_B_BODY, boards, monkeypatch).get_json()
    assert d["your_board_derived"] is True
    assert d["your_board_derived_from"] == "sf_tep"
    assert d["opponent_board_derived"] is False


def test_never_ranked_anywhere_stays_consensus(monkeypatch):
    boards = {"1qb_ppr": {CALLER: {"username": "me",
                                   "elo_ratings": {"stud": 1600.0}}}}
    d = _post_authed(_MODE_B_BODY, boards, monkeypatch).get_json()
    assert d["basis"] == "consensus"
    assert d["opponent_has_rankings"] is False
    assert d["opponent_board_derived"] is False


def test_flag_off_keeps_consensus_fallback(monkeypatch):
    monkeypatch.setattr(srv, "is_enabled", lambda k: False)
    boards = {
        "1qb_ppr": {CALLER: {"username": "me", "elo_ratings": {"stud": 1600.0}}},
        "sf_tep":  {OPP: {"username": "jon", "elo_ratings": {"stud": 1800.0}}},
    }
    d = _post_authed(_MODE_B_BODY, boards, monkeypatch).get_json()
    assert d["basis"] == "consensus"
    assert d["opponent_has_rankings"] is False
    assert d["opponent_board_derived"] is False


# ── Coverage's per-format detail (#191/#192 client contract) ──────────────

def test_coverage_reports_ranked_formats(monkeypatch, tmp_path):
    """get_ranking_coverage lists each member's ranked formats (NULL rows
    count as the default format) while has_rankings stays format-blind."""
    from sqlalchemy import create_engine, insert
    eng = create_engine(f"sqlite:///{tmp_path}/cov.db")
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    with eng.begin() as conn:
        conn.execute(insert(db.league_members_table), [
            {"league_id": "L1", "user_id": "u_sf",   "username": "sf_only"},
            {"league_id": "L1", "user_id": "u_both", "username": "both"},
            {"league_id": "L1", "user_id": "u_none", "username": "never"},
            {"league_id": "L1", "user_id": "u_null", "username": "legacy"},
        ])
        conn.execute(insert(db.member_rankings_table), [
            {"user_id": "u_sf",   "league_id": "L1", "player_id": "p1",
             "elo": 1600.0, "scoring_format": "sf_tep",  "updated_at": "t"},
            {"user_id": "u_both", "league_id": "L1", "player_id": "p1",
             "elo": 1600.0, "scoring_format": "sf_tep",  "updated_at": "t"},
            {"user_id": "u_both", "league_id": "L1", "player_id": "p1",
             "elo": 1500.0, "scoring_format": "1qb_ppr", "updated_at": "t"},
            {"user_id": "u_null", "league_id": "L1", "player_id": "p1",
             "elo": 1500.0, "scoring_format": None,      "updated_at": "t"},
        ])
    cov = db.get_ranking_coverage("L1", exclude_user_id="me")
    by_id = {m["user_id"]: m for m in cov["members"]}
    assert by_id["u_sf"]["ranked_formats"] == ["sf_tep"]
    assert by_id["u_sf"]["has_rankings"] is True
    assert by_id["u_both"]["ranked_formats"] == ["1qb_ppr", "sf_tep"]
    assert by_id["u_none"]["ranked_formats"] == []
    assert by_id["u_none"]["has_rankings"] is False
    assert by_id["u_null"]["ranked_formats"] == ["1qb_ppr"]  # legacy NULL
