"""Manual Trade Calculator endpoints (docs/plans/manual-trade-calculator-plan.md).

Pins the open consensus seam: POST /api/trade/evaluate and
GET /api/trade/values run over an injected universal pool, reuse the
engine's elo_to_value transform, drop unknown ids gracefully, and gate
fairness with the point ratio when confidence is absent.
"""

from dataclasses import dataclass

import pytest

import backend.server as srv
import backend.database as db

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
    _P("stud",  "Stud Man",    "WR", "CIN", 26),
    _P("good",  "Good Guy",    "RB", "DET", 24),
    _P("mid",   "Mid Player",  "TE", "SF",  27),
    _P("bench", "Bench Body",  "RB", "NYJ", 28),
]

# Seed Elos chosen so values are clearly ordered: stud >> good > mid > bench.
_SEED = {"stud": 1800.0, "good": 1650.0, "mid": 1500.0, "bench": 1350.0}


@pytest.fixture(autouse=True)
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr",
        {"players": _POOL_PLAYERS, "seed": dict(_SEED)},
    )
    yield


def _post(body):
    with srv.app.test_client() as c:
        return c.post("/api/trade/evaluate", json=body)


def test_symmetric_trade_is_even():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]})
    assert r.status_code == 200
    d = r.get_json()
    assert d["verdict"] == "even" and d["favors"] == "even"
    assert d["point_ratio"] == 1.0
    assert d["give_value"] == d["receive_value"] > 0


def test_lopsided_trade_is_unfair_and_reports_favored_side():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["bench"]})
    d = r.get_json()
    assert d["verdict"] == "unfair"
    assert d["fairness"] is None            # gate failed (no confidence → point gate)
    assert d["favors"] == "give"            # give side carries the value
    assert d["give_value"] > d["receive_value"]


def test_values_match_engine_transform():
    r = _post({"give_player_ids": ["mid"], "receive_player_ids": ["good"]})
    d = r.get_json()
    by_id = {p["player_id"]: p["value"] for p in d["per_player"]}
    e2v = srv._trade_service_mod.elo_to_value
    assert by_id["mid"] == round(e2v(_SEED["mid"]), 1)
    assert by_id["good"] == round(e2v(_SEED["good"]), 1)


def test_unknown_ids_dropped_and_reported():
    r = _post({"give_player_ids": ["stud", "ghost"], "receive_player_ids": ["good"]})
    d = r.get_json()
    assert d["dropped_player_ids"] == ["ghost"]
    assert {p["player_id"] for p in d["per_player"]} == {"stud", "good"}


def test_one_sided_package_values_without_verdict():
    r = _post({"give_player_ids": ["stud", "good"], "receive_player_ids": []})
    d = r.get_json()
    assert d["give_value"] > 0 and d["receive_value"] == 0
    assert d["verdict"] is None and d["fairness"] is None


def test_empty_request_rejected():
    assert _post({"give_player_ids": [], "receive_player_ids": []}).status_code == 400


def test_unknown_format_falls_back_to_default():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"],
               "scoring_format": "bogus"})
    assert r.get_json()["scoring_format"] == "1qb_ppr"


# ── Pick-denominated gap (`gap`) ─────────────────────────────────────────

def test_gap_names_nearest_pick_and_lighter_side():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]})
    d = r.get_json()
    gap = d["gap"]
    assert gap is not None
    assert gap["value"] == pytest.approx(
        abs(d["give_value"] - d["receive_value"]), abs=0.11)
    assert gap["add_to"] == "receive"          # receive side is lighter
    assert gap["firsts"] > 0
    # 1800-vs-1650 seeds with package shrink on the lighter side ≈ a
    # ~3580-value gap → nearest generic pick = Early 1st.
    assert gap["pick_equivalent"]["pick_id"] == "generic_pick_1_early"
    assert gap["pick_equivalent"]["label"] == "Early 1st Round Pick"


def test_gap_zero_on_symmetric_trade():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]}).get_json()
    gap = d["gap"]
    assert gap["value"] == 0 and gap["add_to"] is None
    assert gap["firsts"] == 0 and gap["pick_equivalent"] is None


def test_gap_beyond_pick_ladder_reports_firsts_only():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["bench"]}).get_json()
    gap = d["gap"]
    assert gap["pick_equivalent"] is None      # bigger than any single pick
    assert gap["firsts"] > 1.5
    assert gap["add_to"] == "receive"


def test_gap_absent_when_one_sided():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": []}).get_json()
    assert d["gap"] is None


# ── Mode B — in-league, both owners' boards ──────────────────────────────

def _post_authed(body, boards, monkeypatch, token="calc-sess"):
    """POST /api/trade/evaluate with an injected session + mocked member
    rankings (no DB). `boards` mirrors load_member_rankings' shape."""
    monkeypatch.setattr(db, "load_member_rankings", lambda *a, **k: boards)
    monkeypatch.setattr(srv, "touch_user_activity", lambda *a, **k: None, raising=False)
    with srv._sessions_lock:
        srv._sessions[token] = {"user_id": CALLER, "active_format": "1qb_ppr", "last_active": 0.0}
    try:
        with srv.app.test_client() as c:
            return c.post("/api/trade/evaluate", json=body,
                          headers={"X-Session-Token": token})
    finally:
        with srv._sessions_lock:
            srv._sessions.pop(token, None)


def test_mode_b_divergence_mutual_gain(monkeypatch):
    # Caller loves `good`; opponent loves `stud`. Trading stud→good makes each
    # side richer BY ITS OWN BOARD → mutual gain, basis=divergence.
    boards = {
        CALLER: {"username": "me",  "elo_ratings": {"stud": 1500.0, "good": 1800.0}},
        OPP:    {"username": "opp", "elo_ratings": {"stud": 1800.0, "good": 1500.0}},
    }
    r = _post_authed({
        "give_player_ids": ["stud"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, boards, monkeypatch)
    assert r.status_code == 200
    d = r.get_json()
    assert d["basis"] == "divergence"
    assert d["opponent_has_rankings"] is True
    assert d["opponent_username"] == "opp"
    assert d["your_value_delta"] > 0 and d["their_value_delta"] > 0
    assert d["mutual_gain"] is True


def test_mode_b_consensus_fallback_when_opponent_unranked(monkeypatch):
    boards = {CALLER: {"username": "me", "elo_ratings": {"stud": 1600.0}}}  # opp absent
    r = _post_authed({
        "give_player_ids": ["stud"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, boards, monkeypatch)
    assert r.status_code == 200
    d = r.get_json()
    assert d["basis"] == "consensus"
    assert d["opponent_has_rankings"] is False
    # consensus fields still present
    assert d["give_value"] > 0 and d["receive_value"] > 0


def test_mode_b_requires_session():
    with srv.app.test_client() as c:
        r = c.post("/api/trade/evaluate", json={
            "give_player_ids": ["stud"], "receive_player_ids": ["good"],
            "league_id": "L1", "opponent_user_id": OPP,
        })
    assert r.status_code == 401


def test_values_endpoint_shape_and_etag():
    with srv.app.test_client() as c:
        r = c.get("/api/trade/values?scoring_format=1qb_ppr")
        assert r.status_code == 200
        d = r.get_json()
        rows = d["players"]
        assert [p["id"] for p in rows[:2]] == ["stud", "good"]   # value-desc
        assert set(rows[0]) == {"id", "name", "position", "team", "age", "value"}
        etag = r.headers["ETag"]
        r2 = c.get("/api/trade/values?scoring_format=1qb_ppr",
                   headers={"If-None-Match": etag})
        assert r2.status_code == 304
