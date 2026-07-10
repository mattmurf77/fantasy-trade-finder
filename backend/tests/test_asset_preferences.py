"""Backlog #2 — asset preference lists (untouchables + targets).

Pins (docs/plans/competitor-top20/02-asset-preference-lists.md):
  1. Untouchables never appear on a generated card's give side (v2 divergence
     path + consensus fallback).
  2. A target on the receive side lifts the card's composite (so it ranks
     higher), capped by pos_multiplier_cap, and never rescues a non-mutual-gain
     trade (applied after the surplus gates).
  3. Flag-off / no-ids ⇒ output byte-identical (the engine params default None).
  4. set_asset_preference: single membership per player, 'none' removes,
     bad list_type rejected.

Flags/_cfg snapshot-restored per test.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
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


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _svc():
    # Clean 1-for-1 divergence: user gives G (undervalues), receives R (covets);
    # opponent mirrors. Both rostered so the card is reachable.
    players = {pid: _Player(pid) for pid in ("G", "R", "G2")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500, "G2": 1500},
                       has_rankings=True)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen(svc, **kw):
    kw.setdefault("fairness_threshold", 0.05)
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1500, "R": 1700, "G2": 1500},
        user_roster=["G", "G2"],
        league_id="L1",
        seed_elo={"G": 1540, "R": 1500, "G2": 1540},
        **kw,
    )


# ───────────────────────── untouchables ─────────────────────────

def test_untouchable_never_on_give_side():
    _set_flags(**{"trade_engine.v2": True})
    base = _gen(_svc())
    assert any("G" in c.give_player_ids for c in base), "fixture should give G at baseline"
    # Mark G untouchable ⇒ no card may give G away.
    guarded = _gen(_svc(), untouchable_ids={"G"})
    assert all("G" not in c.give_player_ids for c in guarded)


def test_unmarking_restores_give_side():
    """Feedback #95 end-to-end: mark → the player is never offered; unmark →
    the player is offered again. Mirrors _run_trade_job's wiring
    (load_asset_preferences → untouchable_ids)."""
    import backend.database as db
    db.metadata.create_all(db.engine)
    _set_flags(**{"trade_engine.v2": True})
    uid, lid = "u_ap_e2e", "L_ap_e2e"
    db.set_asset_preference(uid, lid, "G", None)   # clean slate

    try:
        db.set_asset_preference(uid, lid, "G", "untouchable")
        ids = set(db.load_asset_preferences(uid, lid)["untouchables"])
        assert ids == {"G"}
        guarded = _gen(_svc(), untouchable_ids=ids or None)
        assert all("G" not in c.give_player_ids for c in guarded)

        db.set_asset_preference(uid, lid, "G", None)   # unmark
        ids = set(db.load_asset_preferences(uid, lid)["untouchables"])
        assert ids == set()
        restored = _gen(_svc(), untouchable_ids=ids or None)
        assert any("G" in c.give_player_ids for c in restored)
    finally:
        db.set_asset_preference(uid, lid, "G", None)   # cleanup


def test_untouchable_blocks_consensus_give():
    # Opponent has NO rankings ⇒ consensus fallback path.
    _set_flags(**{"trade_engine.v2": True})
    players = {pid: _Player(pid, position=("WR" if pid == "R" else "RB"))
               for pid in ("G", "R")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={}, has_rankings=False)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    cards = s.generate_trades(
        user_id="user", user_elo={"G": 1600}, user_roster=["G"],
        league_id="L1", seed_elo={"G": 1500, "R": 1500},
        fairness_threshold=0.05, untouchable_ids={"G"},
    )
    assert all("G" not in c.give_player_ids for c in cards)


# ───────────────────────── targets ─────────────────────────

def test_target_lifts_composite():
    _set_flags(**{"trade_engine.v2": True})
    base = _gen(_svc())
    card = next(c for c in base if c.receive_player_ids == ["R"])
    boosted = _gen(_svc(), target_ids={"R"})
    bcard = next(c for c in boosted if c.receive_player_ids == ["R"])
    assert bcard.composite_score > card.composite_score


def test_target_bonus_capped():
    _set_flags(**{"trade_engine.v2": True})
    ts._cfg["target_acquire_bonus"] = 5.0     # absurd bonus
    ts._cfg["pos_multiplier_cap"] = 2.0
    base = _gen(_svc())
    card = next(c for c in base if c.receive_player_ids == ["R"])
    boosted = _gen(_svc(), target_ids={"R"})
    bcard = next(c for c in boosted if c.receive_player_ids == ["R"])
    # Even with a 5x per-target bonus, the multiplier is capped at 2.0.
    assert bcard.composite_score <= card.composite_score * 2.0 + 1e-9


# ───────────────────────── flag-off identity ─────────────────────────

def test_no_ids_is_identical():
    _set_flags(**{"trade_engine.v2": True})
    a = _gen(_svc())
    b = _gen(_svc(), untouchable_ids=None, target_ids=None)
    assert [(c.give_player_ids, c.receive_player_ids, c.composite_score) for c in a] == \
           [(c.give_player_ids, c.receive_player_ids, c.composite_score) for c in b]


# ───────────────────────── persistence ─────────────────────────

def test_set_asset_preference_single_membership_and_validation():
    import backend.database as db
    db.metadata.create_all(db.engine)
    uid, lid = "u_ap_test", "L_ap"
    # clean slate
    for pid in ("p1", "p2"):
        db.set_asset_preference(uid, lid, pid, None)

    db.set_asset_preference(uid, lid, "p1", "untouchable")
    db.set_asset_preference(uid, lid, "p2", "target")
    assert db.load_asset_preferences(uid, lid) == {
        "untouchables": ["p1"], "targets": ["p2"]}

    # Moving p1 to target removes it from untouchables (single membership).
    db.set_asset_preference(uid, lid, "p1", "target")
    got = db.load_asset_preferences(uid, lid)
    assert got["untouchables"] == [] and set(got["targets"]) == {"p1", "p2"}

    # 'none' removes.
    db.set_asset_preference(uid, lid, "p1", None)
    assert "p1" not in db.load_asset_preferences(uid, lid)["targets"]

    with pytest.raises(ValueError):
        db.set_asset_preference(uid, lid, "p2", "bogus")

    # cleanup
    db.set_asset_preference(uid, lid, "p2", None)
