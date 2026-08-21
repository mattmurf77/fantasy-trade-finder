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
from backend.pick_values import market_pick_pool_value

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
    # #214 — market-mode crown credit requires a piece at/above
    # crown_elite_value (6000); elite (Elo 1900 → 7389.1) qualifies, and
    # good2 (1780 → 4055.2) keeps the 1-for-2 naive skew inside the
    # skew_phaseout window so the credit is visible.
    _P("elite", "Elite Ace",   "WR", "MIN", 25),
    _P("good2", "Good Deuce",  "RB", "ATL", 23),
]

# Seed Elos chosen so values are clearly ordered: elite > stud >> good2 >
# good > mid > bench.
_SEED = {"stud": 1800.0, "good": 1650.0, "mid": 1500.0, "bench": 1350.0,
         "elite": 1900.0, "good2": 1780.0}


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
    # #214 deliberate update: under the default 'market' mode a 1-for-1
    # side is benchmarked against its OWN best asset, so the lighter side
    # is no longer shrunk — the gap is the raw 4481.7 − 2117.0 = 2364.7
    # (was ~3580 under the legacy math) → nearest generic pick = Mid 1st
    # (was Early 1st).
    assert gap["pick_equivalent"]["pick_id"] == "generic_pick_1_mid"
    assert gap["pick_equivalent"]["label"] == "Mid 1st Round Pick"


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
    """D-148 (2026-08-21, Q-026) — an evener pick is priced by the ENGINE's
    waterfall, not by the stored `draft_picks.pool_value`.

    Both call sites of `_roster_eveners` sit inside `_trade_evaluate_impl`,
    whose `gap` is computed from priced picks. Sizing the candidates against
    the stored ladder meant the sweetener and the hole it was sized to fill
    came off two different price lists — a one-tap "add their 2026 1.01"
    offered as closing a 2117.0 gap the same response charged 4867.1 for.

    The fixture is built so the two answers PROVABLY differ and both are
    in-window, so the assertion cannot pass by accident: the row STORES
    1005.3 (0.9x gap) and the 2028 round-1 market curve prices it at 1263.0.
    Ordering by |Δ| holds either way, so the ranking assertion stays a
    ranking assertion and the value assertion carries the pricing claim."""
    gap = _consensus_gap(["mid"], ["good"])
    stored = round(gap * 0.9, 1)                      # 1005.3 — deliberately stale
    pick = {"pick_id": "L1_2028_1_3", "owner_user_id": CALLER, "season": 2028,
            "round": 1, "pool_value": stored, "is_traded": 0,
            "original_username": None}
    _install_evener_world(monkeypatch, CALLER, gap, picks=[pick],
                          untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    singles = [e for e in d["eveners"] if not e.get("is_package")]
    # |Δ|: ev_close 0 < ev_second 0.05 < pick 0.13 < ev_third 0.20 (capped).
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "L1_2028_1_3"]
    pick_row = singles[2]
    assert pick_row["is_pick"] is True
    assert pick_row["position"] == "PICK"
    assert pick_row["name"] == "2028 1st"
    # THE D-148 ASSERTION: the market curve, re-derived from the pricing
    # function, and NOT the stored column the pre-D-148 line read.
    expected = market_pick_pool_value(2028, 1, "1qb_ppr")
    assert expected == 1263.0
    assert pick_row["value"] == pytest.approx(expected, rel=1e-3)
    assert pick_row["value"] != pytest.approx(stored, rel=1e-3)


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


def test_mode_b_one_sided_eveners_opt_in_for_emptied_give_side(monkeypatch):
    # Deck swap-suggestions (2026-07-27): a 1-for-1 card minus its give asset
    # is a one-sided read. With one_sided_eveners the EMPTY give side gets
    # replacement candidates from the CALLER's roster, sized against the
    # receive side's full package value.
    d0 = _post({"give_player_ids": [], "receive_player_ids": ["good"]}).get_json()
    gap = d0["receive_value"]
    _install_evener_world(monkeypatch, CALLER, gap, untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": [], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
        "one_sided_eveners": True,
    }, _BOARDS, monkeypatch).get_json()
    assert d["gap"] is None                      # still a one-sided read
    singles = [e for e in d["eveners"] if not e.get("is_package")]
    # Same window/cap/order semantics as the two-sided eveners, gap = the
    # non-empty side's value; the caller's untouchables stay excluded.
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "ev_third"]
    assert all(gap * 0.4 <= e["value"] <= gap * 1.5 for e in singles)


def test_mode_b_one_sided_eveners_from_opponent_for_emptied_receive_side(monkeypatch):
    d0 = _post({"give_player_ids": ["good"], "receive_player_ids": []}).get_json()
    gap = d0["give_value"]
    # Candidates live on the OPPONENT's roster (the receive side's owner).
    _install_evener_world(monkeypatch, OPP, gap, untouchables=["ev_untouch"])
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": [],
        "league_id": "L1", "opponent_user_id": OPP,
        "one_sided_eveners": True,
    }, _BOARDS, monkeypatch).get_json()
    singles = [e for e in d["eveners"] if not e.get("is_package")]
    assert [e["id"] for e in singles] == ["ev_close", "ev_second", "ev_third"]


def test_mode_b_one_sided_eveners_absent_without_param(monkeypatch):
    # Default behavior unchanged: one-sided Mode B reads carry no eveners.
    gap = _post({"give_player_ids": [],
                 "receive_player_ids": ["good"]}).get_json()["receive_value"]
    _install_evener_world(monkeypatch, CALLER, gap)
    d = _post_authed({
        "give_player_ids": [], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert "eveners" not in d


def test_mode_b_evener_players_carry_tier_picks_and_packages_do_not(monkeypatch):
    # #277 — evener PLAYER rows gain an additive `tier`, walked off the RAW
    # seed Elo via the canonical RankingService.tier_for_elo band-walk (the
    # same convention as /api/trade/values' #263 field — never derived from
    # the elo_to_value-transformed `value`). Picks and 2-piece packages
    # carry no tier: a pick's label already reads as a ladder rung, and a
    # package sum has no single tier.
    gap = _consensus_gap(["mid"], ["good"])
    pick = {"pick_id": "L1_2027_1_3", "owner_user_id": CALLER, "season": 2027,
            "round": 1, "pool_value": round(gap * 0.9, 1), "is_traded": 0,
            "original_username": None}
    _install_evener_world(monkeypatch, CALLER, gap, picks=[pick],
                          untouchables=["ev_untouch"])
    # Recover the injected seed the world installed (extended pool).
    seed = srv.g_universal_by_format["1qb_ppr"]["seed"]
    d = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    for e in d["eveners"]:
        if e.get("is_package") or e.get("is_pick"):
            assert "tier" not in e
        else:
            assert e["tier"] == srv.RankingService.tier_for_elo(
                seed[e["id"]], e["position"], "1qb_ppr")


def test_mode_b_one_sided_eveners_param_ignored_on_two_sided_read(monkeypatch):
    # With both sides present the normal gap machinery owns eveners — the
    # param must not change a two-sided response.
    gap = _consensus_gap(["mid"], ["good"])
    _install_evener_world(monkeypatch, CALLER, gap)
    base = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    with_param = _post_authed({
        "give_player_ids": ["mid"], "receive_player_ids": ["good"],
        "league_id": "L1", "opponent_user_id": OPP,
        "one_sided_eveners": True,
    }, _BOARDS, monkeypatch).get_json()
    assert with_param["eveners"] == base["eveners"]


def test_mode_a_one_sided_eveners_param_is_mode_b_only():
    # Rosterless Mode A has no rosters to draw from — the param is inert.
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": [],
               "one_sided_eveners": True}).get_json()
    assert "eveners" not in d


def test_mode_a_evener_is_the_gap_generic_pick():
    # stud vs good — the gap names Mid 1st (see the gap tests above; #214:
    # was Early 1st under the legacy math); the rosterless calculator
    # recommends exactly that pick, calculator-addable.
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]}).get_json()
    pe = d["gap"]["pick_equivalent"]
    assert d["eveners"] == [{
        "id": pe["pick_id"], "name": pe["label"], "position": "PICK",
        "team": None, "value": pe["value"], "is_pick": True,
    }]
    assert d["eveners"][0]["id"] == "generic_pick_1_mid"


def test_mode_a_eveners_empty_when_gap_beyond_pick_ladder():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["bench"]}).get_json()
    assert d["gap"]["pick_equivalent"] is None
    assert d["eveners"] == []          # present but honestly empty


def test_mode_a_eveners_absent_when_even_or_one_sided():
    even = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]}).get_json()
    assert "eveners" not in even
    one = _post({"give_player_ids": ["stud"], "receive_player_ids": []}).get_json()
    assert "eveners" not in one


# ── Itemized value adjustments (`adjustments`) — DynastyDealer 2026-07-26 ──
# Transparency-only decomposition of the displayed side totals: per side,
# naive_totals + Σ row amounts == the displayed package value (0.1 rounding).
# Only the two adjustments the evaluate path actually applies can appear:
# package_depth (gamma weighting, always on) and consolidation (crown flag,
# outnumbered side only). Displayed totals must be byte-identical to before.


def _side_rows(d, side):
    return {r["key"]: r for r in d.get("adjustments", {}).get(side, [])}


def test_adjustments_1for1_no_rows_under_market_default():
    # #214 deliberate update (was test_adjustments_1for1_depth_on_weaker_
    # side_only): under the default 'market' mode each side benchmarks its
    # OWN best asset, so a 1-for-1 has no depth discount on either side —
    # and with neither piece at crown_elite_value, no consolidation either.
    # No adjustments moved a value → the key is absent entirely.
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]}).get_json()
    assert "adjustments" not in d
    assert d["give_value"] == pytest.approx(4481.7, abs=0.11)
    assert d["receive_value"] == pytest.approx(2117.0, abs=0.11)


def test_adjustments_1for1_depth_on_weaker_side_only_heavy_mode():
    # The pre-#214 legacy behavior, preserved verbatim as the reachable
    # 'heavy' mode: the weaker 1-for-1 side is shaved against the trade's
    # best asset.
    import backend.trade_service as ts
    with ts.stud_tax_override("heavy"):
        d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]}).get_json()
    # stud IS the trade's best asset → contributes 100%, no rows on give.
    assert d["adjustments"]["give"] == []
    give_naive = d["naive_totals"]["give"]
    assert give_naive == pytest.approx(d["give_value"], abs=0.11)
    # good sits below v_max → depth weighting shaves it; no consolidation
    # (equal counts).
    rows = _side_rows(d, "receive")
    assert set(rows) == {"package_depth"}
    depth = rows["package_depth"]
    assert depth["amount"] < 0
    assert depth["label"] == "Package depth"
    assert depth["why"]
    assert (d["naive_totals"]["receive"] + depth["amount"]
            == pytest.approx(d["receive_value"], abs=0.15))


def test_adjustments_2for1_depth_and_consolidation():
    # #214 deliberate update: under 'market' the crown credit needs an
    # elite piece (value ≥ crown_elite_value 6000) and a naive gap inside
    # the skew_phaseout window — good+mid → stud (4481.7) no longer earns
    # it. good2+good (6172.2) → elite (7389.1) does: skew 19.7% → phase
    # 0.61 → credit ≈ +358 on the receive side; the give side is
    # depth-discounted against its OWN best (good shaved vs good2, ≈ −176).
    d = _post({"give_player_ids": ["good2", "good"],
               "receive_player_ids": ["elite"]}).get_json()
    grows = _side_rows(d, "give")
    assert "package_depth" in grows and grows["package_depth"]["amount"] < 0
    assert "consolidation" not in grows          # no elite piece on give
    rrows = _side_rows(d, "receive")
    assert "consolidation" in rrows and rrows["consolidation"]["amount"] > 0
    assert "package_depth" not in rrows          # single asset → own best
    # Attribution identity per side: naive + Σamounts == displayed value.
    for side, total in (("give", d["give_value"]), ("receive", d["receive_value"])):
        amounts = sum(r["amount"] for r in d["adjustments"][side])
        assert (d["naive_totals"][side] + amounts
                == pytest.approx(total, abs=0.15))


def test_adjustments_equal_counts_never_show_consolidation():
    d = _post({"give_player_ids": ["stud", "mid"],
               "receive_player_ids": ["good", "bench"]}).get_json()
    for side in ("give", "receive"):
        assert "consolidation" not in _side_rows(d, side)


def test_adjustments_absent_when_none_apply():
    # Symmetric 1-for-1: both sides ARE the trade max → zero depth, equal
    # counts → zero crown → the field is omitted entirely.
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]}).get_json()
    assert "adjustments" not in d and "naive_totals" not in d


def test_adjustments_do_not_change_displayed_totals():
    # Pure transparency: totals must match an independent recomputation of
    # the pre-existing math (_consensus_packages) exactly.
    from backend.trade_optimizer import _consensus_packages
    e2v = srv._trade_service_mod.elo_to_value
    gv, rv = _consensus_packages(
        ["good", "mid"], ["stud"], lambda p: e2v(_SEED[p]))
    d = _post({"give_player_ids": ["good", "mid"],
               "receive_player_ids": ["stud"]}).get_json()
    assert d["give_value"] == round(gv, 1)
    assert d["receive_value"] == round(rv, 1)


def test_adjustments_mode_b_match_consensus_itemization(monkeypatch):
    # Mode B carries the same consensus-based itemization (the "Consensus"
    # row both cards display) — board-priced totals are not itemized.
    a = _post({"give_player_ids": ["good", "mid"],
               "receive_player_ids": ["stud"]}).get_json()
    b = _post_authed({
        "give_player_ids": ["good", "mid"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert b["adjustments"] == a["adjustments"]
    assert b["naive_totals"] == a["naive_totals"]


# ── Starter impact (`starter_impact`) — DTF teardown 2026-07-27 ──────────
# Mode B only: optimal-lineup value before vs after the trade, per side,
# via power_rankings.optimal_starters over the league's slot template.
# Omitted without a template (non-Sleeper league / meta miss) and in Mode A.


_SI_EXTRA = [
    (_P("wr_low",  "Low Wideout", "WR", "TB", 24), 1400.0),
    (_P("te_stud", "Elite Tight", "TE", "LV", 26), 1800.0),
]


def _install_starter_world(monkeypatch, *, slots=("RB", "WR"),
                           caller_roster=("good", "bench", "wr_low"),
                           opp_roster=("stud", "mid")):
    """Slot template + both rosters; pool extended with wr_low/mid2."""
    players = _POOL_PLAYERS + [p for p, _ in _SI_EXTRA]
    seed = dict(_SEED)
    seed.update({p.id: elo for p, elo in _SI_EXTRA})
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr", {"players": players, "seed": seed})
    # #311 — _starter_impact resolves the template via _league_lineup_slots
    # (platform branch); patch the new seam directly.
    monkeypatch.setattr(srv, "_league_lineup_slots",
                        lambda league_id: list(slots) if slots else None)
    monkeypatch.setattr(srv, "load_league_members", lambda league_id: [
        {"user_id": CALLER, "player_ids": list(caller_roster)},
        {"user_id": OPP,    "player_ids": list(opp_roster)},
    ])
    monkeypatch.setattr(
        srv, "load_draft_picks", lambda *a, **k: [])
    monkeypatch.setattr(
        srv, "load_asset_preferences",
        lambda user_id=None, league_id=None: {"untouchables": [], "targets": [],
                                              "not_interested": []},
    )
    return seed


def test_starter_impact_before_after_lineup_math(monkeypatch):
    # Slots RB+WR. Caller [good RB, bench RB, wr_low WR] gives good,
    # receives stud WR: lineup good+wr_low → bench+stud. Opponent
    # [stud WR, mid TE] flips stud → good: WR slot empties, RB slot fills.
    seed = _install_starter_world(monkeypatch)
    e2v = srv._trade_service_mod.elo_to_value
    v = lambda pid: e2v(seed[pid])
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    si = d["starter_impact"]
    you_before = v("good") + v("wr_low")
    you_after = v("bench") + v("stud")
    assert si["your_delta"] == pytest.approx(you_after - you_before, abs=0.15)
    # Opponent: before = stud alone (no RB to fill); after = good alone
    # (no WR left) — mid is a TE, outside the RB/WR template.
    assert si["their_delta"] == pytest.approx(v("good") - v("stud"), abs=0.15)
    assert si["your_delta"] > 0 > si["their_delta"]
    assert si["note"] == "You likely gain immediate lineup value."


def test_starter_impact_bench_depth_and_future_value_notes(monkeypatch):
    _install_starter_world(monkeypatch)
    # bench (RB, never starts here) for mid (TE, can't start in RB/WR):
    # neither lineup slot moves for the caller → bench-depth note.
    d = _post_authed({
        "give_player_ids": ["bench"], "receive_player_ids": ["mid"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    si = d["starter_impact"]
    assert si["your_delta"] == 0
    assert si["note"] == ("This mostly trades bench depth — your starting "
                          "lineup barely moves.")
    # give the RB starter for a pricier TE: receive_value > give_value (more
    # raw value in) but the TE can't start in an RB/WR template, so the RB
    # slot drops good → bench = lineup strength lost.
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["te_stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert d["receive_value"] > d["give_value"]
    si = d["starter_impact"]
    assert si["your_delta"] < 0
    assert si["note"] == ("You gain future value but lose immediate lineup "
                          "strength.")


def test_starter_impact_omitted_without_slot_template(monkeypatch):
    _install_starter_world(monkeypatch, slots=None)
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    assert "starter_impact" not in d


def test_starter_impact_omitted_in_mode_a():
    d = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"]}).get_json()
    assert "starter_impact" not in d


# ── Starter impact `slots` (#238) — per-slot before/after breakdown ──────
# Additive on the same Mode B payload: one row per lineup slot in the
# league's template order, before/after = the player the value-optimal fill
# assigns there ({player_id, name, position, value} or null), delta = the
# slot's value move. Summary fields (your_delta/their_delta/note) unchanged.


def test_starter_impact_slots_breakdown(monkeypatch):
    seed = _install_starter_world(monkeypatch)
    e2v = srv._trade_service_mod.elo_to_value
    v = lambda pid: e2v(seed[pid])
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    si = d["starter_impact"]
    assert {"your_delta", "their_delta", "note"} <= set(si)   # summary intact
    slots = si["slots"]
    assert [s["slot"] for s in slots] == ["RB", "WR"]
    rb, wr = slots
    # RB: starter good leaves, bench backfills.
    assert rb["before"]["player_id"] == "good"
    assert rb["before"]["name"] == "Good Guy"
    assert rb["before"]["position"] == "RB"
    assert rb["after"]["player_id"] == "bench"
    assert rb["delta"] == pytest.approx(v("bench") - v("good"), abs=0.15)
    # WR: incoming stud outvalues wr_low.
    assert wr["before"]["player_id"] == "wr_low"
    assert wr["after"]["player_id"] == "stud"
    assert wr["delta"] == pytest.approx(v("stud") - v("wr_low"), abs=0.15)
    # Per-slot deltas reconcile with the summary delta.
    assert sum(s["delta"] for s in slots) == pytest.approx(
        si["your_delta"], abs=0.3)


def test_starter_impact_slots_numbered_labels_and_null_after(monkeypatch):
    # Two RB slots → labels RB1/RB2; the trade empties RB2 (after = null).
    seed = _install_starter_world(monkeypatch, slots=("RB", "RB", "WR"))
    e2v = srv._trade_service_mod.elo_to_value
    v = lambda pid: e2v(seed[pid])
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    slots = d["starter_impact"]["slots"]
    assert [s["slot"] for s in slots] == ["RB1", "RB2", "WR"]
    rb2 = slots[1]
    assert rb2["before"]["player_id"] == "bench" and rb2["after"] is None
    assert rb2["delta"] == pytest.approx(-v("bench"), abs=0.15)


# ── Starter impact `slots[].tier`/`rank` (#169, flag trade.position_impact) ──
# Additive on the #238 slot rows: `tier` (RankingService.tier_for_elo over
# the RAW seed Elo, the same call #277's evener rows make) and `rank` (this
# player's 1-based positional rank within the universal pool). Both bound
# behind the SAME internal `tier_of` param, so they appear together or not
# at all. Flag off → byte-identical to pre-#169 (no new keys).


def test_starter_impact_slots_tier_and_rank_when_flag_on(monkeypatch):
    monkeypatch.setattr(srv, "is_enabled", lambda k: k == "trade.position_impact")
    seed = _install_starter_world(monkeypatch)
    fmt = "1qb_ppr"
    tier = lambda pid, pos: srv.RankingService.tier_for_elo(seed[pid], pos, fmt)
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    slots = d["starter_impact"]["slots"]
    rb, wr = slots
    # Pool RBs by seed elo desc: good2 (1780) > good (1650) > bench (1350).
    assert rb["before"]["player_id"] == "good" and rb["before"]["rank"] == 2
    assert rb["after"]["player_id"] == "bench" and rb["after"]["rank"] == 3
    assert rb["before"]["tier"] == tier("good", "RB")
    assert rb["after"]["tier"] == tier("bench", "RB")
    # Pool WRs by seed elo desc: elite (1900) > stud (1800) > wr_low (1400).
    assert wr["before"]["player_id"] == "wr_low" and wr["before"]["rank"] == 3
    assert wr["after"]["player_id"] == "stud" and wr["after"]["rank"] == 2
    assert wr["before"]["tier"] == tier("wr_low", "WR")
    assert wr["after"]["tier"] == tier("stud", "WR")


def test_starter_impact_slots_tier_and_rank_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr(srv, "is_enabled", lambda k: False)
    _install_starter_world(monkeypatch)
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    slots = d["starter_impact"]["slots"]
    for s in slots:
        for side in ("before", "after"):
            entry = s[side]
            if entry is not None:
                assert set(entry) == {"player_id", "name", "position", "value"}


def test_starter_impact_slots_rank_ties_broken_by_player_id(monkeypatch):
    # Two RBs at the identical seed elo — the ranker must break the tie
    # deterministically (lower player_id sorts first) rather than raising
    # or ordering arbitrarily.
    monkeypatch.setattr(srv, "is_enabled", lambda k: k == "trade.position_impact")
    players = _POOL_PLAYERS + [
        _P("rb_tie_a", "Tie A", "RB", "LAR", 25),
        _P("rb_tie_b", "Tie B", "RB", "SEA", 25),
    ]
    seed = dict(_SEED, rb_tie_a=1700.0, rb_tie_b=1700.0)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr", {"players": players, "seed": seed})
    monkeypatch.setattr(srv, "_league_lineup_slots", lambda league_id: ["RB"])
    monkeypatch.setattr(srv, "load_league_members", lambda league_id: [
        {"user_id": CALLER, "player_ids": ["rb_tie_a"]},
        {"user_id": OPP,    "player_ids": ["rb_tie_b"]},
    ])
    monkeypatch.setattr(srv, "load_draft_picks", lambda *a, **k: [])
    monkeypatch.setattr(
        srv, "load_asset_preferences",
        lambda user_id=None, league_id=None: {"untouchables": [], "targets": [],
                                              "not_interested": []},
    )
    d = _post_authed({
        "give_player_ids": ["rb_tie_a"], "receive_player_ids": ["rb_tie_b"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    rb = d["starter_impact"]["slots"][0]
    # good2 (1780) still outranks both ties at 1700; between the tied pair,
    # the lower id (rb_tie_a) sorts first.
    assert rb["before"]["player_id"] == "rb_tie_a" and rb["before"]["rank"] == 2
    assert rb["after"]["player_id"] == "rb_tie_b" and rb["after"]["rank"] == 3


def test_starter_impact_slots_null_after_carries_no_tier_or_rank(monkeypatch):
    # Flag on, but the slot's `after` is null (unfillable) — no crash, and
    # there's simply no entry to attach tier/rank to.
    monkeypatch.setattr(srv, "is_enabled", lambda k: k == "trade.position_impact")
    _install_starter_world(monkeypatch, slots=("RB", "RB", "WR"))
    d = _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": "L1", "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()
    rb2 = d["starter_impact"]["slots"][1]
    assert rb2["before"]["player_id"] == "bench"
    assert rb2["before"]["tier"] is not None
    assert rb2["before"]["rank"] is not None
    assert rb2["after"] is None


def test_values_endpoint_shape_and_etag():
    with srv.app.test_client() as c:
        r = c.get("/api/trade/values?scoring_format=1qb_ppr")
        assert r.status_code == 200
        d = r.get_json()
        rows = d["players"]
        # value-desc (#214: pool gained 'elite' 7389.1 > 'stud' 4481.7 >
        # 'good2' 4055.2 > 'good')
        assert [p["id"] for p in rows[:4]] == ["elite", "stud", "good2", "good"]
        # B3 follow-up (2026-08-18): `is_pick` is additive — pick identity is
        # now explicit on the wire. Pinned in test_trade_values_is_pick.py.
        assert set(rows[0]) == {"id", "name", "position", "team", "age", "value",
                                "tier", "is_pick"}
        # #263 — tier is walked off the RAW seed Elo (not the transformed
        # `value`), via the same RankingService.tier_for_elo the extension/
        # anchor wizard use.
        by_id = {p["id"]: p["tier"] for p in rows}
        assert by_id["elite"] == srv.RankingService.tier_for_elo(_SEED["elite"], "WR", "1qb_ppr")
        assert by_id["bench"] == srv.RankingService.tier_for_elo(_SEED["bench"], "RB", "1qb_ppr")
        etag = r.headers["ETag"]
        r2 = c.get("/api/trade/values?scoring_format=1qb_ppr",
                   headers={"If-None-Match": etag})
        assert r2.status_code == 304


# ── #311 — platform-aware template resolution (_league_lineup_slots) ─────
# ESPN/MFL/Fleaflicker leagues have NO roster_positions equivalent, so the
# helper serves the app's one standard template (_MOCK_DEFAULT_LINEUP, plus
# SUPER_FLEX for sf_tep) keyed off the leagues.platform column — never off
# id shape (platform league ids are numeric too). Sleeper resolution and
# the no-row/demo omission are byte-identical to pre-#311.

from unittest.mock import MagicMock  # noqa: E402

_311_QBS = [
    (_P("qb_one", "First Signal",  "QB", "BUF", 27), 1850.0),
    (_P("qb_two", "Second Signal", "QB", "WAS", 23), 1820.0),
]

_STANDARD_1QB_LABELS = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX"]


def _install_league_row(monkeypatch, league_id, *, platform,
                        default_scoring=None):
    """Isolated in-memory DB, one leagues row (or none when platform is
    None) — _league_lineup_slots reads it live, nothing is monkeypatched
    over the helper itself."""
    from sqlalchemy import create_engine, insert as _insert
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    if platform is not None or default_scoring is not None:
        with eng.begin() as conn:
            conn.execute(_insert(db.leagues_table).values(
                sleeper_league_id=str(league_id), user_id=CALLER,
                platform=platform, default_scoring=default_scoring))
    monkeypatch.setattr(db, "engine", eng)
    return eng


def _install_platform_world(monkeypatch, league_id, *, platform,
                            default_scoring=None, seed_row=True,
                            caller_roster=("good", "bench", "wr_low",
                                           "qb_one", "qb_two"),
                            opp_roster=("stud", "mid")):
    """Full Mode B world where the template comes from the REAL
    _league_lineup_slots over a seeded leagues row. Returns (seed,
    sleeper_fetch_mock)."""
    _install_league_row(monkeypatch, league_id,
                        platform=platform if seed_row else None,
                        default_scoring=default_scoring if seed_row else None)
    players = (_POOL_PLAYERS + [p for p, _ in _SI_EXTRA]
               + [p for p, _ in _311_QBS])
    seed = dict(_SEED)
    seed.update({p.id: elo for p, elo in _SI_EXTRA})
    seed.update({p.id: elo for p, elo in _311_QBS})
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr", {"players": players, "seed": seed})
    monkeypatch.setattr(srv, "load_league_members", lambda league_id: [
        {"user_id": CALLER, "player_ids": list(caller_roster)},
        {"user_id": OPP,    "player_ids": list(opp_roster)},
    ])
    monkeypatch.setattr(srv, "load_draft_picks", lambda *a, **k: [])
    monkeypatch.setattr(
        srv, "load_asset_preferences",
        lambda user_id=None, league_id=None: {"untouchables": [], "targets": [],
                                              "not_interested": []},
    )
    # Any Sleeper meta fetch in these tests is either mocked (test 4) or a
    # BUG (tests 1-3, 6) — never let one reach the network.
    fetch_mock = MagicMock(return_value={})
    monkeypatch.setattr(srv, "_fetch_sleeper_league_meta", fetch_mock)
    monkeypatch.setattr(srv, "_FA_LEAGUE_META_CACHE", {})
    return seed, fetch_mock


def _evaluate_platform(monkeypatch, league_id):
    return _post_authed({
        "give_player_ids": ["good"], "receive_player_ids": ["stud"],
        "league_id": str(league_id), "opponent_user_id": OPP,
    }, _BOARDS, monkeypatch).get_json()


def test_espn_league_gets_standard_1qb_template(monkeypatch):
    # Numeric PK + platform='espn' + NULL scoring → standard 1QB template.
    _install_platform_world(monkeypatch, "777001", platform="espn")
    d = _evaluate_platform(monkeypatch, "777001")
    si = d.get("starter_impact")
    assert si is not None, "starter_impact must appear for ESPN leagues (#311)"
    assert [s["slot"] for s in si["slots"]] == _STANDARD_1QB_LABELS


def test_espn_sf_tep_league_appends_super_flex_and_seats_second_qb(monkeypatch):
    _install_platform_world(monkeypatch, "777002", platform="espn",
                            default_scoring="sf_tep")
    d = _evaluate_platform(monkeypatch, "777002")
    si = d["starter_impact"]
    labels = [s["slot"] for s in si["slots"]]
    assert labels == _STANDARD_1QB_LABELS + ["SUPER_FLEX"]
    sf = si["slots"][-1]
    # qb_one takes the QB slot; the SECOND QB lands in SUPER_FLEX.
    assert sf["before"] is not None
    assert sf["before"]["player_id"] == "qb_two"
    assert sf["before"]["position"] == "QB"


def test_mfl_league_gets_standard_1qb_template(monkeypatch):
    # The branch is platform-tuple wide, not ESPN-only.
    _install_platform_world(monkeypatch, "777003", platform="mfl")
    d = _evaluate_platform(monkeypatch, "777003")
    si = d.get("starter_impact")
    assert si is not None, "starter_impact must appear for MFL leagues (#311)"
    assert [s["slot"] for s in si["slots"]] == _STANDARD_1QB_LABELS


def test_fleaflicker_league_gets_standard_1qb_template(monkeypatch):
    # Operator scope call #1 (plan #311): fleaflicker included.
    _install_platform_world(monkeypatch, "777005", platform="fleaflicker")
    d = _evaluate_platform(monkeypatch, "777005")
    assert d.get("starter_impact") is not None


def test_sleeper_league_template_still_meta_derived(monkeypatch):
    # platform NULL + digit id → the existing Sleeper path, byte-identical:
    # meta roster_positions filtered to LINEUP_SLOT_ELIGIBILITY, NOT the
    # standard template.
    _, fetch_mock = _install_platform_world(monkeypatch, "888001",
                                            platform=None, seed_row=False)
    _install_league_row(monkeypatch, "888001", platform=None,
                        default_scoring="1qb_ppr")  # row with NULL platform
    fetch_mock.return_value = {"roster_positions": [
        "QB", "RB", "RB", "WR", "BN", "K", "IDP_FLEX", "FLEX"]}
    got = srv._league_lineup_slots("888001")
    assert got == ["QB", "RB", "RB", "WR", "FLEX"]
    assert got == srv._sleeper_lineup_slots("888001")
    assert fetch_mock.called


def test_no_leagues_row_still_omits_starter_impact(monkeypatch):
    # league_demo has no leagues row → template None → field omitted, as
    # before. Never serve the standard template for an unknown league.
    _install_platform_world(monkeypatch, "league_demo", platform=None,
                            seed_row=False)
    d = _evaluate_platform(monkeypatch, "league_demo")
    assert "starter_impact" not in d
    assert srv._league_lineup_slots("league_demo") is None


def test_numeric_espn_id_never_fetches_sleeper_meta(monkeypatch):
    # The platform branch must run BEFORE any digit-shaped Sleeper probe.
    _, fetch_mock = _install_platform_world(monkeypatch, "777004",
                                            platform="espn")
    slots = srv._league_lineup_slots("777004")
    assert slots == list(srv._MOCK_DEFAULT_LINEUP)
    assert not fetch_mock.called
