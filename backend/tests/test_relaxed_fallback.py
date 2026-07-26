"""#189 — targeted jobs (acquire / trade-away / pinned players) should always
present offers when anything defensible exists.

When a targeted v2 job yields ZERO cards under the normal gates,
TradeService._relaxed_targeted_pass reruns generation with staged, labeled
relaxation:

  stage 1 "fairness_band"                — fairness threshold widened to
                                           relaxed_fairness_threshold
  stage 2 "fairness_band+surplus_floor"  — plus both-sides surplus minimums
                                           dropped to relaxed_surplus_floor

Cards from a relaxed pass carry relaxed=True + relaxed_reason (additive —
clients label them). NEVER relaxed: #108 user-gain gates, untouchables,
past-decision dedup. Normal jobs / non-empty targeted jobs are byte-identical.
"""
import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


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


def _svc_consensus_gap():
    """User pins away G; the unranked opponent's only return R is priced so
    the package ratio lands BETWEEN relaxed_fairness_threshold (0.55) and the
    caller's 0.75 — zero cards normally, stage-1 rescue under relaxation.
    (G seed 1540, R seed 1590: gv≈999, rv≈1568 → ratio≈0.64; the user still
    comes out ahead so the never-relaxed #108 epsilon gate passes.)"""
    players = {"G": _Player("G", "RB"), "R": _Player("R", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={}, has_rankings=False)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen(svc, **kw):
    kw.setdefault("fairness_threshold", 0.75)
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1540.0, "R": 1590.0},
        user_roster=["G"],
        league_id="L1",
        seed_elo={"G": 1540.0, "R": 1590.0},
        **kw,
    )


def test_empty_targeted_job_returns_relaxed_cards():
    svc = _svc_consensus_gap()
    # Normal (non-targeted) job: zero cards, NO relaxed fallback.
    assert _gen(svc) == []
    # Targeted (pinned give): the relaxed pass rescues ≥1 labeled card.
    cards = _gen(_svc_consensus_gap(), pinned_give_players=["G"])
    assert cards, "targeted empty sweep must fall back to a relaxed pass"
    for c in cards:
        assert c.relaxed is True
        assert c.relaxed_reason == "fairness_band"
        assert "G" in c.give_player_ids


def test_nontargeted_empty_job_stays_empty():
    # No pins, no position prefs ⇒ no fallback even when the sweep is empty.
    assert _gen(_svc_consensus_gap()) == []


def test_targeted_job_with_normal_cards_is_untouched(monkeypatch):
    """A targeted job that yields cards normally must never invoke the
    relaxed pass — results byte-identical to the plain v2 output."""
    svc = _svc_consensus_gap()
    calls = []
    orig = TradeService._relaxed_targeted_pass
    monkeypatch.setattr(TradeService, "_relaxed_targeted_pass",
                        lambda self, kw: calls.append(1) or orig(self, kw))
    cards = _gen(svc, pinned_give_players=["G"], fairness_threshold=0.55)
    assert cards and all(not c.relaxed for c in cards)
    assert calls == []


def test_stage_order_and_reason_stamping(monkeypatch):
    """The defined relaxation order: stage 1 widens fairness only; stage 2
    additionally floors the surplus minimums. First non-empty stage wins."""
    svc = _svc_consensus_gap()
    seen = []

    def _fake_v2(self, **kw):
        # Record the effective knobs each stage ran with.
        seen.append({
            "thr": kw["fairness_threshold"],
            "floor_div": ts._c("fairness_floor_divergence"),
            "min_side": ts._c("min_side_surplus"),
            "cb": kw["on_opponent_done"],
        })
        if len(seen) < 2:
            return []                       # stage 1 comes up empty
        return [TradeCard(trade_id="t1", league_id="L1",
                          proposing_user_id="user", target_user_id="opp",
                          target_username="opp", give_player_ids=["G"],
                          receive_player_ids=["R"], mismatch_score=0.0,
                          fairness_score=0.6, composite_score=0.5)]

    monkeypatch.setattr(TradeService, "_generate_trades_v2", _fake_v2)
    cards = svc._relaxed_targeted_pass({
        "fairness_threshold": 0.75, "on_opponent_done": object(),
    })
    assert [s["thr"] for s in seen] == [0.55, 0.55]
    assert seen[0]["floor_div"] == 0.55
    assert seen[0]["min_side"] == ts._DEFAULT_CFG["min_side_surplus"]  # stage 1: surplus intact
    assert seen[1]["min_side"] == 0.0                                  # stage 2: floored
    assert all(s["cb"] is None for s in seen)                          # no re-streaming
    assert cards[0].relaxed and cards[0].relaxed_reason == "fairness_band+surplus_floor"
    # Overrides never leak past the pass (thread-local context exited).
    assert ts._c("min_side_surplus") == ts._DEFAULT_CFG["min_side_surplus"]
    assert ts._c("fairness_floor_divergence") == ts._DEFAULT_CFG["fairness_floor_divergence"]


def test_relaxed_never_widens_beyond_callers_looser_threshold(monkeypatch):
    """A caller already below relaxed_fairness_threshold keeps their own
    (looser) bar — relaxation never TIGHTENS."""
    svc = _svc_consensus_gap()
    seen = []
    monkeypatch.setattr(TradeService, "_generate_trades_v2",
                        lambda self, **kw: seen.append(kw["fairness_threshold"]) or [])
    svc._relaxed_targeted_pass({"fairness_threshold": 0.50,
                                "on_opponent_done": None})
    assert seen == [0.50, 0.50]


def test_user_gain_epsilon_never_relaxed():
    """#108 safety: a pinned-give sweep where every return LOSES user value
    stays empty even after both relaxed stages (consensus path enforces
    receive − give ≥ user_gain_epsilon on the user's board)."""
    players = {"G": _Player("G", "RB"), "R": _Player("R", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    cards = svc.generate_trades(
        user_id="user",
        user_elo={"G": 1700.0, "R": 1450.0},     # user's G far above the only return
        user_roster=["G"],
        league_id="L1",
        seed_elo={"G": 1700.0, "R": 1450.0},
        fairness_threshold=0.75,
        pinned_give_players=["G"],
    )
    assert cards == []


def test_untouchables_never_relaxed():
    """Untouchables hold through both relaxed stages: with the only viable
    give blocked, a targeted sweep stays empty rather than offering it."""
    svc = _svc_consensus_gap()
    cards = _gen(svc, pinned_give_players=["G"], untouchable_ids={"G"})
    assert cards == []


def test_relaxed_card_serializes_additive_fields():
    import backend.server as srv
    card = TradeCard(trade_id="t", league_id="L", proposing_user_id="u",
                     target_user_id="o", target_username="o",
                     give_player_ids=["G"], receive_player_ids=["R"],
                     mismatch_score=0.0, fairness_score=0.6,
                     composite_score=0.5, relaxed=True,
                     relaxed_reason="fairness_band")
    d = srv.trade_card_to_dict(card, {})
    assert d["relaxed"] is True
    assert d["relaxed_reason"] == "fairness_band"
    # Ordinary cards stay byte-identical — no relaxed keys at all.
    card2 = TradeCard(trade_id="t2", league_id="L", proposing_user_id="u",
                      target_user_id="o", target_username="o",
                      give_player_ids=["G"], receive_player_ids=["R"],
                      mismatch_score=0.0, fairness_score=0.6,
                      composite_score=0.5)
    d2 = srv.trade_card_to_dict(card2, {})
    assert "relaxed" not in d2 and "relaxed_reason" not in d2
