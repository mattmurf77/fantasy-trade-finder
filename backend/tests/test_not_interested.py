"""#163 — "not interested in this player" flag.

Third asset_prefs list (`not_interested`, FB-95 pattern): players the engine
must never offer TO the user — a receive-side hard exclusion across every
generation path (v2 divergence, v3 optimizer incl. sweeteners, consensus
fallback, likes-you injection). The give side is untouched: the user can
still trade a not-interested player away.
"""
import pytest

import backend.database as db
import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


class _Player:
    def __init__(self, pid, position="RB", age=25, search_rank=50):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = age
        self.search_rank = search_rank
        self.pick_value = None


# ── storage round-trip ─────────────────────────────────────────────────────

def test_prefs_round_trip_and_single_membership():
    db.metadata.create_all(db.engine)
    uid, lid = "u_ni_rt", "L_ni_rt"
    try:
        lists = db.set_asset_preference(uid, lid, "P1", "not_interested")
        assert lists["not_interested"] == ["P1"]
        assert lists["untouchables"] == [] and lists["targets"] == []
        # single membership: moving to another list clears the old tag
        lists = db.set_asset_preference(uid, lid, "P1", "target")
        assert lists["not_interested"] == [] and lists["targets"] == ["P1"]
        # and back
        lists = db.set_asset_preference(uid, lid, "P1", "not_interested")
        assert lists["not_interested"] == ["P1"] and lists["targets"] == []
        # 'none' removes
        lists = db.set_asset_preference(uid, lid, "P1", None)
        assert lists["not_interested"] == []
        assert db.load_asset_preferences(uid, lid)["not_interested"] == []
    finally:
        db.set_asset_preference(uid, lid, "P1", None)


def test_unknown_list_type_still_rejected():
    with pytest.raises(ValueError):
        db.set_asset_preference("u", "L", "P1", "blocklist")


# ── engine: divergence path (v2 + v3) ──────────────────────────────────────

# Position-complete rosters so the v3 lineup-feasibility hard gate (3.2)
# doesn't veto every combo. Divergence: user covets R, opponent covets G.
_U_ROSTER = [("uq", "QB"), ("G", "RB"), ("ur2", "RB"),
             ("uw1", "WR"), ("uw2", "WR"), ("ute", "TE")]
_O_ROSTER = [("oq", "QB"), ("R", "RB"), ("or2", "RB"),
             ("ow1", "WR"), ("ow2", "WR"), ("ote", "TE")]
_ALL = _U_ROSTER + _O_ROSTER


def _divergence_svc():
    players = {pid: _Player(pid, pos) for pid, pos in _ALL}
    opp_elo = {pid: 1500 for pid, _ in _ALL}
    opp_elo["G"] = 1700               # opponent covets the user's G
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=[pid for pid, _ in _O_ROSTER],
                       elo_ratings=opp_elo, has_rankings=True)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen_divergence(svc, **kw):
    kw.setdefault("fairness_threshold", 0.05)
    user_elo = {pid: 1500 for pid, _ in _ALL}
    user_elo["R"] = 1700              # user covets the opponent's R
    return svc.generate_trades(
        user_id="user",
        user_elo=user_elo,
        user_roster=[pid for pid, _ in _U_ROSTER],
        league_id="L1",
        seed_elo={pid: (1540 if pid in ("G", "R") else 1500) for pid, _ in _ALL},
        **kw,
    )


@pytest.mark.parametrize("v3", [False, True])
def test_not_interested_never_on_receive_side_divergence(v3):
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True,
                       "trade_engine.v3": v3}
    # Baseline: R is offered to the user.
    base = _gen_divergence(_divergence_svc())
    assert any("R" in c.receive_player_ids for c in base), \
        "fixture should offer R at baseline"
    # Tagged not_interested ⇒ R never appears on the receive side.
    guarded = _gen_divergence(_divergence_svc(), not_interested_ids={"R"})
    assert all("R" not in c.receive_player_ids for c in guarded)


def test_give_side_untouched_by_not_interested():
    """The user can still trade AWAY a not-interested player."""
    cards = _gen_divergence(_divergence_svc(), not_interested_ids={"G"})
    assert any("G" in c.give_player_ids for c in cards)


# ── engine: consensus fallback path ────────────────────────────────────────

def _consensus_svc():
    players = {"G": _Player("G", "RB"), "R": _Player("R", "WR"),
               "R2": _Player("R2", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R", "R2"],
                       elo_ratings={}, has_rankings=False)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen_consensus(svc, **kw):
    kw.setdefault("fairness_threshold", 0.55)
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1540, "R": 1590, "R2": 1585},
        user_roster=["G"],
        league_id="L1",
        seed_elo={"G": 1540, "R": 1590, "R2": 1585},
        **kw,
    )


def test_not_interested_excluded_on_consensus_path():
    base = _gen_consensus(_consensus_svc())
    assert any("R" in c.receive_player_ids for c in base)
    guarded = _gen_consensus(_consensus_svc(), not_interested_ids={"R"})
    assert guarded, "other returns must still surface"
    assert all("R" not in c.receive_player_ids for c in guarded)


def test_not_interested_beats_target_readd_consensus():
    """Exclusion wins over the target re-add loop (single membership makes
    the overlap impossible via the route; the engine is safe regardless)."""
    guarded = _gen_consensus(_consensus_svc(), not_interested_ids={"R"},
                             target_ids={"R"})
    assert all("R" not in c.receive_player_ids for c in guarded)


# ── likes-you injection ────────────────────────────────────────────────────

def test_likes_you_injection_respects_not_interested(monkeypatch):
    import backend.server as srv
    players = {"A": _Player("A"), "B": _Player("B")}
    svc = TradeService(players=players)
    opp = LeagueMember(user_id="opp", username="opp", roster=["B"],
                       elo_ratings={}, has_rankings=False)
    league = League(league_id="L1", name="T", platform="demo", members=[opp])
    like = {"user_id": "opp", "give_player_ids": ["B"],
            "receive_player_ids": ["A"]}
    monkeypatch.setattr(srv, "load_recent_league_likes",
                        lambda **kw: [like])

    base = srv._inject_likes_you_cards(
        cards=[], trade_service=svc, user_id="user", league_id="L1",
        league=league, user_roster=["A"], seed_map={"A": 1500.0, "B": 1500.0})
    assert any("B" in c.receive_player_ids for c in base)

    guarded = srv._inject_likes_you_cards(
        cards=[], trade_service=svc, user_id="user", league_id="L1",
        league=league, user_roster=["A"], seed_map={"A": 1500.0, "B": 1500.0},
        not_interested_ids={"B"})
    assert guarded == []


# ── route contract ─────────────────────────────────────────────────────────

def test_route_accepts_not_interested_list_type():
    """ASSET_PREF_LISTS drives the route's validation — the enum must carry
    the new value (and the GET shape the new key)."""
    from backend.database import ASSET_PREF_LISTS
    assert "not_interested" in ASSET_PREF_LISTS
    db.metadata.create_all(db.engine)
    out = db.load_asset_preferences("u_ni_shape", "L_ni_shape")
    assert out == {"untouchables": [], "targets": [], "not_interested": []}
