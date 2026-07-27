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


# ── Eveners (`eveners`) — DynastyGM teardown 2026-07-26 ──────────────────
# One-tap balance assets for the WINNING side. Mode B draws from that side's
# real roster + owned picks in a 0.4×–1.5× window around gap.value (closest
# first, cap 3, + at most one 2-piece combo); Mode A falls back to the single
# generic pick the gap already names. Untouchables are never recommended.


def _evener_pool(gap, e2v_inv):
    """Extra pool players at controlled values relative to the gap."""
    mk = lambda pid, mult: (_P(pid, pid.upper(), "WR", "KC", 25), e2v_inv(gap * mult))
    return [
        mk("ev_close",   1.0),    # |Δ| = 0        → rank 1
        mk("ev_second",  0.95),   # |Δ| = 0.05·gap → rank 2
        mk("ev_third",   0.8),    # |Δ| = 0.20·gap → rank 3 (unless pick beats it)
        mk("ev_fourth",  0.5),    # in window but beyond the cap
        mk("ev_low",     0.3),    # below window — excluded
        mk("ev_high",    1.6),    # above window — excluded
        mk("ev_untouch", 0.99),   # would rank 2nd but is untouchable
    ]


def _install_evener_world(monkeypatch, roster_owner, gap, *, picks=None,
                          untouchables=()):
    """Extend the pool with evener candidates owned by `roster_owner` and
    mock the Mode B roster/pick/pref loaders."""
    v2e = srv._trade_service_mod.value_to_elo
    extra = _evener_pool(gap, v2e)
    players = _POOL_PLAYERS + [p for p, _ in extra]
    seed = dict(_SEED)
    seed.update({p.id: elo for p, elo in extra})
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr", {"players": players, "seed": seed})
    monkeypatch.setattr(srv, "load_league_members", lambda league_id: [
        {"user_id": roster_owner, "player_ids": [p.id for p, _ in extra]},
    ])
    monkeypatch.setattr(
        srv, "load_draft_picks",
        lambda league_id=None, owner_user_id=None, **k: [
            p for p in (picks or [])
            if owner_user_id is None or p["owner_user_id"] == owner_user_id],
    )
    monkeypatch.setattr(
        srv, "load_asset_preferences",
        lambda user_id=None, league_id=None: {"untouchables": list(untouchables),
                                              "targets": [], "not_interested": []},
    )


def _consensus_gap(give_ids, recv_ids):
    """The gap the route will compute for this trade (Mode A read)."""
    d = _post({"give_player_ids": give_ids, "receive_player_ids": recv_ids}).get_json()
    return d["gap"]["value"]


_BOARDS = {
    CALLER: {"username": "me",  "elo_ratings": {}},
    OPP:    {"username": "opp", "elo_ratings": {}},
}


def test_mode_b_eveners_from_callers_roster_when_caller_wins(monkeypatch):
    # give=mid < receive=good → the CALLER receives more (wins) → add_to='give'
    # → eveners come from the CALLER's roster; their untouchables are skipped.
    gap = _consensus_gap(["mid"], ["good"])
    _install_evener_world(monkeypatch, CALLER, gap, untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert d["gap"]["add_to"] == "give"
    evs = d["eveners"]
    singles = [e for e in evs if not e.get("is_package")]
    # Window + cap + closest-first: ev_close, ev_second, ev_third; ev_fourth
    # capped out, ev_low/ev_high outside the window, ev_untouch excluded.
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "ev_third"]
    assert all(gap * 0.4 <= e["value"] <= gap * 1.5 for e in singles)
    assert singles[0]["position"] == "WR" and singles[0]["is_pick"] is False
    # Stretch: one 2-piece combo from sub-gap assets — pieces too small to
    # matter alone can pair up. Best in-window pair by closeness is
    # ev_third+ev_low (1.1×gap); the 0.95+0.8-style sums overflow the window.
    pkgs = [e for e in evs if e.get("is_package")]
    assert len(pkgs) == 1
    assert sorted(pkgs[0]["ids"]) == ["ev_low", "ev_third"]
    assert pkgs[0]["value"] == pytest.approx(gap * 1.1, rel=0.01)
    assert pkgs[0]["position"] == "PKG"


def test_mode_b_eveners_include_owned_picks(monkeypatch):
    gap = _consensus_gap(["mid"], ["good"])
    pick = {"pick_id": "L1_2027_1_3", "owner_user_id": CALLER, "season": 2027,
            "round": 1, "pool_value": round(gap * 0.9, 1), "is_traded": 0,
            "original_username": None}
    _install_evener_world(monkeypatch, CALLER, gap, picks=[pick],
                          untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    singles = [e for e in d["eveners"] if not e.get("is_package")]
    # |Δ|: ev_close 0 < ev_second 0.05 < pick 0.10 < ev_third 0.20 (capped).
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "L1_2027_1_3"]
    pick_row = singles[2]
    assert pick_row["is_pick"] is True
    assert pick_row["position"] == "PICK"
    assert pick_row["name"] == "2027 1st"
    assert pick_row["value"] == pytest.approx(gap * 0.9, rel=0.01)


def test_mode_b_eveners_from_opponents_roster_when_opponent_wins(monkeypatch):
    # give=good > receive=mid → the OPPONENT receives more → add_to='receive'
    # → eveners come from the OPPONENT's roster (their untouchables skipped).
    gap = _consensus_gap(["good"], ["mid"])
    _install_evener_world(monkeypatch, OPP, gap, untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["mid"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert d["gap"]["add_to"] == "receive"
    singles = [e for e in d["eveners"] if not e.get("is_package")]
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "ev_third"]


def test_mode_b_eveners_absent_on_even_trade(monkeypatch):
    _install_evener_world(monkeypatch, CALLER, 1000.0)
    d = _post_authed({
        "give_player_ids": ["stud"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert d["favors"] == "even"
    assert "eveners" not in d


def test_mode_b_eveners_exclude_players_already_in_trade(monkeypatch):
    gap = _consensus_gap(["mid"], ["good"])
    _install_evener_world(monkeypatch, CALLER, gap)
    d = _post_authed({
        # ev_close rides along in the give side → it can't be recommended.
        "give_player_ids": ["mid", "ev_close"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    if d.get("gap") and d["gap"]["add_to"]:
        assert all(e["id"] != "ev_close" for e in d.get("eveners", []))


def test_mode_a_evener_is_the_gap_generic_pick():
    # stud vs good — the gap names Early 1st (see the gap tests above); the
    # rosterless calculator recommends exactly that pick, calculator-addable.
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]}).get_json()
    pe = d["gap"]["pick_equivalent"]
    assert d["eveners"] == [{
        "id": pe["pick_id"], "name": pe["label"], "position": "PICK",
        "team": None, "value": pe["value"], "is_pick": True,
    }]
    assert d["eveners"][0]["id"] == "generic_pick_1_early"


def test_mode_a_eveners_empty_when_gap_beyond_pick_ladder():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["bench"]}).get_json()
    assert d["gap"]["pick_equivalent"] is None
    assert d["eveners"] == []          # present but honestly empty


def test_mode_a_eveners_absent_when_even_or_one_sided():
    even = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]}).get_json()
    assert "eveners" not in even
    one = _post({"give_player_ids": ["stud"], "receive_player_ids": []}).get_json()
    assert "eveners" not in one


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
