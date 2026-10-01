"""Value-core adapter: app objects -> contract -> TradeCard + evidence.

Spec: docs/plans/value-core-engine/lld.md §3 (knobs + clamps), §7 (adapter),
§7.3 (valuation_json schema v1); test list in specs.md §5.3.

Isolated: needs only backend.value_core.types, trade_service and
ranking_service (plus backend.server for the payload test). Covers:
  • core/rank config mapping, clamps and the all-zero-weights rule;
  • tier_values read from tier_config.json bands;
  • build_snapshot: raw market (no age preference), other_players,
    picks, default lineup template;
  • build_request: board shrink, no board, id filtering, pin mode;
  • to_trade_cards / evidence shape, and the client payload through the
    real trade_card_to_dict.
"""
import json

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.ranking_service import Player
from backend.trade_service import LeagueMember, elo_to_value
from backend.value_core import adapter
from backend.value_core.types import (
    DEFAULT_WINDOW, Asset, Board, CoreConfig, CoreDiagnostics, DeckEntry, FairTrade,
    LeagueSnapshot, PipelineResult, RankConfig, Request, RosterRules, Scores, ScoredTrade,
    Team, TeamWindow,
)


@pytest.fixture(autouse=True)
def _isolate_cfg(monkeypatch):
    # The shrink and value curve read trade_service._cfg; pin the knobs the
    # assertions depend on and restore the dict afterwards.
    monkeypatch.setattr(ts, "_cfg", dict(ts._cfg))
    for key in ("elo_value_base", "elo_value_k", "elo_value_ref", "shrink_pseudocount",
                "user_elo_shrink", "placement_tier_clamp"):
        ts._cfg[key] = ts._DEFAULT_CFG[key]


def _player(pid, pos, age=25, name=None):
    return Player(id=pid, name=name or pid.upper(), position=pos, team="AAA", age=age)


def _snapshot_from_app(*, fmt="1qb_ppr", lineup_slots=None, extra_players=()):
    players = {p.id: p for p in [
        _player("v1", "WR", age=21), _player("v2", "RB"), _player("vk", "K"),
        _player("vdl", "DL"), _player("o1", "WR"), _player("o2", "QB"),
        Player(id="pk1", name="2027 1st", position="PICK", team="", age=0, pick_value=2117.0),
        *extra_players]}
    seed = {"v1": 1650.0, "v2": 1600.0, "o1": 1640.0, "o2": 1700.0, "pk1": 1650.0}
    opp = LeagueMember(user_id="opp", username="Opp", roster=["o1", "o2", "pk1"], elo_ratings={})
    return adapter.build_snapshot(
        league_id="L", scoring_format=fmt, viewer_team_id="me", viewer_name="Me",
        viewer_roster=["v1", "v2", "vk", "vdl", "ghost"], opponents=[opp], players=players,
        seed_elo=seed, lineup_slots=lineup_slots, max_players=None, windows={})


def _request(snap, **kw):
    base = dict(snapshot=snap, user_elo=None, seed_elo={}, confidence=None, placements=None,
                untouchable_ids=(), not_interested_ids=(), pinned_give=(),
                pinned_give_mode="any", pinned_receive=(), partner_team_id=None,
                fairness_threshold=None)
    base.update(kw)
    return adapter.build_request(**base)


# ── config ──────────────────────────────────────────────────────────────────

def test_core_config_defaults_and_clamps():
    assert adapter.core_config_from({}) == CoreConfig()
    assert adapter.core_config_from({"vc_band": 5}).band == 0.5
    assert adapter.core_config_from({"vc_band": 0.0}).band == 0.01
    assert adapter.core_config_from({"vc_max_assets_per_side": 3.7}).max_assets_per_side == 4
    assert adapter.core_config_from({"vc_max_per_partner": 5000}).max_per_partner == 1000
    assert adapter.core_config_from({"vc_untouchable_min_ratio": 0.5}).untouchable_min_ratio == 1.0
    assert adapter.core_config_from({"vc_stud_premium": 0.9}).stud_premium == 0.5
    floor = adapter.core_config_from({"asset_floor_abs": 600})
    assert floor.asset_floor_abs == 600.0 and isinstance(floor.asset_floor_abs, float)
    assert adapter.core_config_from({"filler_min_frac": 0.3}).filler_min_frac == 0.3


def test_rank_config_zero_weights_equalize():
    zero = adapter.rank_config_from({"vc_w_value": 0, "vc_w_outlook": 0, "vc_w_rank": 0})
    assert (zero.w_value, zero.w_outlook, zero.w_rank) == (1.0, 1.0, 1.0)
    neg = adapter.rank_config_from({"vc_w_value": -2})
    assert (neg.w_value, neg.w_outlook, neg.w_rank) == (0.0, 1.0, 1.0)
    assert adapter.rank_config_from({}) == RankConfig()
    assert adapter.rank_config_from({"vc_player_cap": 99}).player_cap == 30
    assert adapter.rank_config_from({"vc_repeat_penalty": 2}).repeat_penalty == 1.0
    assert adapter.standings_weight_from({}) == 0.30
    assert adapter.standings_weight_from({"vc_standings_weight": 4}) == 1.0


def test_tier_values():
    assert adapter.tier_values("1qb_ppr") == pytest.approx((elo_to_value(1580), elo_to_value(1927)))
    assert adapter.tier_values("sf_tep") == pytest.approx((elo_to_value(1580), elo_to_value(1927)))


# ── build_snapshot ──────────────────────────────────────────────────────────

def test_build_snapshot_raw_market_no_age_pref():
    snap = _snapshot_from_app()
    v1 = snap.assets["v1"]
    assert v1.age == 21.0 and v1.kind == "player" and v1.name == "V1"
    assert v1.market == pytest.approx(elo_to_value(1650))
    assert v1.market == pytest.approx(2117.0, abs=0.1)        # not x1.10 for youth
    assert list(snap.teams) == ["me", "opp"]                   # viewer inserted first
    assert snap.teams["me"].window == DEFAULT_WINDOW
    assert snap.first_round_value == pytest.approx(elo_to_value(1580))


def test_build_snapshot_other_players():
    snap = _snapshot_from_app()
    me = snap.teams["me"]
    assert me.asset_ids == ("v1", "v2")
    assert me.other_players == 3                               # K, DL, and an unknown id
    assert "vk" not in snap.assets and "vdl" not in snap.assets


def test_build_snapshot_picks():
    snap = _snapshot_from_app()
    pk = snap.assets["pk1"]
    assert (pk.kind, pk.position, pk.age) == ("pick", "PICK", None)
    assert pk.market == pytest.approx(elo_to_value(1650))
    assert snap.teams["opp"].asset_ids == ("o1", "o2", "pk1")


def test_build_snapshot_default_sf_lineup():
    snap = _snapshot_from_app(fmt="sf_tep")
    assert snap.rules == RosterRules(adapter.DEFAULT_LINEUP + ("SUPER_FLEX",), None)
    assert _snapshot_from_app().rules.lineup_slots == adapter.DEFAULT_LINEUP
    assert _snapshot_from_app(lineup_slots=["QB", "BN"]).rules.lineup_slots == ("QB", "BN")


def test_build_snapshot_duplicate_asset_keeps_first_owner(caplog):
    players = {"x": _player("x", "WR")}
    opp = LeagueMember(user_id="opp", username="Opp", roster=["x"], elo_ratings={})
    with caplog.at_level("WARNING"):
        snap = adapter.build_snapshot(
            league_id="L", scoring_format="1qb_ppr", viewer_team_id="me", viewer_name="Me",
            viewer_roster=["x"], opponents=[opp], players=players, seed_elo={"x": 1600.0},
            lineup_slots=None, max_players=12, windows={"opp": TeamWindow("rebuilder", -0.2, "declared", None, 0.0)})
    assert snap.teams["me"].asset_ids == ("x",) and snap.teams["opp"].asset_ids == ()
    assert snap.teams["opp"].window.window == "rebuilder"
    assert any("keeping the first" in r.getMessage() for r in caplog.records)


# ── build_request ───────────────────────────────────────────────────────────

def test_build_request_shrink():
    snap = _snapshot_from_app()
    req = _request(snap, user_elo={"v2": 1700.0, "not_in_league": 1800.0},
                   seed_elo={"v2": 1600.0}, confidence={"v2": 4})
    assert req.viewer_team_id == "me"
    assert req.board.values["v2"] == pytest.approx(elo_to_value(1650))
    assert req.board.comparisons["v2"] == 4
    assert "not_in_league" not in req.board.values


def test_build_request_no_board():
    snap = _snapshot_from_app()
    assert _request(snap, user_elo={}).board is None
    assert _request(snap, user_elo=None).board is None


def test_build_request_filters_ids():
    snap = _snapshot_from_app()
    req = _request(snap, untouchable_ids={"v1", "zzz"}, not_interested_ids=["o1", "nope"],
                   pinned_give=["v2", "gone"], pinned_give_mode="bogus",
                   pinned_receive=["o2", "x"], partner_team_id="opp", fairness_threshold=0.9)
    assert req.untouchable_ids == frozenset({"v1"})
    assert req.not_interested_ids == frozenset({"o1"})
    assert req.pinned_give_ids == frozenset({"v2"})
    assert req.pinned_receive_ids == frozenset({"o2"})
    assert req.pinned_give_mode == "any"
    assert _request(snap, pinned_give_mode="all").pinned_give_mode == "all"
    assert (req.partner_team_id, req.fairness_threshold) == ("opp", 0.9)


# ── cards + evidence ────────────────────────────────────────────────────────

def _hand_snapshot():
    assets = {a.id: a for a in [
        Asset("a1", "player", "WR", "Alpha", 24.0, 3000.0),
        Asset("a2", "player", "RB", "Bravo", 27.0, 1500.0),
        Asset("b1", "player", "WR", "Charlie", 25.0, 3150.0),
        Asset("b2", "pick", "PICK", "2027 1st", None, 1600.0),
    ]}
    win = TeamWindow("contender", 0.21, "inferred", 0.33, 0.1125)
    teams = {"me": Team("me", "Me", ("a1", "a2"), 1, win),
             "opp": Team("opp", "Opp", ("b1", "b2"), 0, TeamWindow("rebuilder", -0.3, "declared", -1.0, 0.1125))}
    return LeagueSnapshot("L", "1qb_ppr", assets, teams, RosterRules(adapter.DEFAULT_LINEUP, None),
                          1492.0, 8457.0)


def _entry(pos, give, receive, gm, rm, priority, effective):
    trade = FairTrade("opp", give, receive, gm, rm, rm / gm, 0.0, None, False, (0, 1))
    detail = {"value": {"delta_ln": 0.05}, "outlook": {"scale": 1000.0}, "rank": {"has_board": True}}
    scored = ScoredTrade(trade, Scores(0.6, 0.7, 0.55, priority), detail)
    return DeckEntry(pos, scored, effective, ("Fair on value", "Fits their rebuild"))


def _result():
    return PipelineResult([_entry(0, ("a1",), ("b1",), 3000.0, 3150.0, 0.6123456, 0.6123456),
                           _entry(1, ("a2",), ("b2",), 1500.0, 1600.0, 0.5, 0.35)],
                          CoreDiagnostics(partners=1, fair=2), 5)


def _hand_request():
    return Request("me", board=Board({"a1": 3300.0}, {"a1": 9}))


def test_to_trade_cards_shape():
    snap, req = _hand_snapshot(), _hand_request()
    cards, ev = adapter.to_trade_cards(_result(), snap, req, league_id="L", proposing_user_id="acct_me",
                                       core_cfg=CoreConfig(), rank_cfg=RankConfig())
    assert len(cards) == 2 and set(ev) == {id(c) for c in cards}
    c0, c1 = cards
    assert c0.trade_id.startswith("vc_") and c1.trade_id.startswith("vc_") and c0.trade_id != c1.trade_id
    assert c0.basis == "consensus" and c0.preserve_server_order is True
    assert c0.composite_score == pytest.approx(0.612346)
    assert (c0.give_value, c0.receive_value) == (3000.0, 3150.0)
    assert c0.fairness_score == pytest.approx(round(3000 / 3150, 4))
    assert c0.mismatch_score == 0.55
    assert (c0.target_user_id, c0.target_username, c0.proposing_user_id) == ("opp", "Opp", "acct_me")
    assert (c0.give_player_ids, c0.receive_player_ids) == (["a1"], ["b1"])
    assert c0.reasons == ["Fair on value", "Fits their rebuild"]
    assert c0.lane is None and c0.narrative is None and c0.match_context is None
    assert ev[id(c1)]["deck_position"] == 1


def test_evidence_schema_v1():
    snap, req = _hand_snapshot(), _hand_request()
    entry = _result().entries[0]
    doc = adapter.evidence(entry, snap, req, CoreConfig(), RankConfig(), budget_exhausted=True)
    assert set(doc) == {"schema_version", "generator", "generator_version", "deck_position",
                        "weights", "scores", "effective", "market", "core", "windows",
                        "detail", "assets"}
    assert json.loads(json.dumps(doc, sort_keys=True)) == doc
    assert (doc["schema_version"], doc["generator"], doc["generator_version"]) == (1, "value_core", "value-core-1")
    assert doc["core"]["ratio_floor"] == pytest.approx(1 / 1.2, abs=1e-4)   # default band 0.20
    assert doc["core"]["ratio_ceiling"] == pytest.approx(1.2)
    assert doc["core"]["budget_exhausted"] is True and doc["core"]["drops_needed"] == [0, 1]
    assert doc["weights"] == {"value": 1.0, "outlook": 1.0, "rank": 1.0,
                              "repeat_penalty": 0.15, "player_cap": 3}
    assert doc["windows"]["viewer"]["window"] == "contender"
    assert doc["windows"]["partner"] == {"window": "rebuilder", "score": -0.3, "source": "declared",
                                         "pf_index": -1.0, "standings_weight": 0.1125}
    assert doc["detail"] == entry.scored.detail
    assert doc["assets"] == [
        {"id": "a1", "side": "give", "market": 3000.0, "personal": 3300.0, "n": 9},
        {"id": "b1", "side": "receive", "market": 3150.0, "personal": None, "n": None}]
    # The client's fairness preference only tightens the band.
    tight = adapter.evidence(entry, snap, Request("me", fairness_threshold=0.97), CoreConfig(),
                             RankConfig(), budget_exhausted=False)
    assert tight["core"]["band"] == pytest.approx(0.03)
    assert tight["core"]["ratio_floor"] == pytest.approx(1 / 1.03, abs=1e-4)
    assert adapter.evidence(entry, snap, Request("me"), CoreConfig(), RankConfig(),
                            budget_exhausted=False)["assets"][0]["personal"] is None


def test_payload_via_trade_card_to_dict(monkeypatch):
    import backend.server as server
    snap, req = _hand_snapshot(), _hand_request()
    cards, _ev = adapter.to_trade_cards(_result(), snap, req, league_id="L", proposing_user_id="me",
                                        core_cfg=CoreConfig(), rank_cfg=RankConfig())
    players = {"a1": _player("a1", "WR"), "b1": _player("b1", "WR")}
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade_math.human_explanations": False})
    off = server.trade_card_to_dict(cards[0], players)
    assert off["preserve_server_order"] is True and off["basis"] == "consensus"
    assert "favors" in off and "gap" in off
    assert "lane" not in off and "narrative" not in off and "reasons" not in off
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade_math.human_explanations": True})
    on = server.trade_card_to_dict(cards[0], players)
    assert on["reasons"] == ["Fair on value", "Fits their rebuild"]
