"""Roster setup Step 2 as one-page tier placement — the `scope:'roster'` save.

Spec: docs/plans/roster-first-trade-setup/scope-tier-rank.md §1.1, §1.6, §1.8,
§2.3 and §6 ("Unit tests (backend pytest)", tests 1-8). D-232.

`POST /api/tiers/save` with `scope:'roster'` routes to the merged-band writer
(`RankingService.apply_tiers_subset`) with the POSTED ids (plus cleared) as
the scope, reads the scope UNGATED, never marks the position complete, and
tags the server `tier_save` event `via:'roster_setup'`. What this pins:

  1. Only posted ids change Elo (whole-board diff).
  2. A single player moved up into a populated `first_1` lands at the band
     FLOOR (1580), not the ceiling the unscoped writer gives a lone pid.
  3. Incumbents of the target band keep byte-identical overrides.
  4. The scope is honoured with `ranks.rookie_subset` AND
     `trades.roster_tier_rank` both off (§1.8: a gated server would fall
     through to `apply_tiers`).
  5. No `tiers_saved` completeness mark.
  6. `tier_save` carries `via:'roster_setup'`.
  7. Posted ids are `explicit` in the next owner context's `user_sources`.
  8. THE POINT OF THE CHANGE: an owner-v1 card giving X for an at-market
     return is eligible before; after X is moved up two tiers through this
     route it is `viewer_no_benefit`. The same move as a reorder (the old
     step) is a permutation of the roster's own Elos and leaves it eligible.

Sabotages (each proven RED, then reverted — see the TEST_LEDGER entry):
  S1 roster scope routed to `apply_tiers`            → test 2
  S2 persist guard `if pid in scope_pids` removed    → tests 1, 3
  S3 roster branch gated on a flag                   → test 4
  S4 roster save writes `save_tiers_position`        → test 5
  S5 `roster_setup` dropped from the via whitelist   → test 6
  S6 roster scope_pids = the rookie set              → tests 1, 2, 7, 8
  test 8's in-test control: the reorder path         → stays eligible
  S7  anchors always clamped to the floor            → test 9
  S8  scoped slots filled in reverse submitted order → test 10
  S9  route passes empty_band_edge=False             → tests 11, 12
  S10 empty-band rule treats every mover as "up"     → test 12
  S11 `pid in pool_ids` filter dropped               → test 13
  S12 empty_band_edge defaults to True               → test 14

Tests 9-14 pin placement: a lone down-mover at the lower band's ceiling,
several movers in submitted order (exact values), the empty-band edge rule
(`empty_band_edge`, roster scope only: up ⇒ floor, down ⇒ ceiling), ids
not at the position / not in the pool ignored, and the rookie lane's lone
pid still at the ceiling.

Harness: test_fair_packages.py's (Flask client, a real in-memory session over
a real RankingService, isolated in-memory SQLite, `record_event` mocked) and
test_owner_trade_block.py's `_owner_generation_context` call.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend import trade_gen_owner as owner
from backend.database import (
    get_tiers_saved, load_tier_overrides, metadata, users_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

ME = "user_roster_me"
OPP = "user_roster_opp"
LEAGUE = "league_roster_tiers"
TOKEN = "test-token-roster-tiers"
FMT = "1qb_ppr"

# All RB, one age, so the outlook lean and the lineup proxy cancel on a
# same-market 1-for-1 and owner utility is the personal gain alone.
SEED = {
    "x":  1500.0,   # mine — second (1370-1575); the player the user lifts
    "z":  1530.0,   # mine — second; the reorder partner
    "y":  1500.0,   # theirs — second; X's at-market return
    "i1": 1700.0,   # theirs — first_1 (1580-1785) incumbent
    "i2": 1650.0,   # theirs — first_1 incumbent
    "f1": 1450.0,   # free — second
}
MY_ROSTER = ["x", "z"]
THEIR_ROSTER = ["y", "i1", "i2"]
# The viewer already valued Y above market (a pin inside `second`), and the
# opponent values X above Y — so X-for-Y is mutually beneficial before.
VIEWER_PRIOR_PINS = {"y": 1560.0, "i1": 1700.0}
OPP_BOARD = {**SEED, "x": 1560.0, "y": 1500.0}


def _players():
    return [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in SEED]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=ME, created_at="2026-11-11T00:00:00+00:00"))

    players = _players()
    service = RankingService(players=players, seed_ratings=dict(SEED))
    service._scoring_format = FMT
    stamp = datetime(2026, 11, 1, tzinfo=timezone.utc).isoformat()
    for pid, elo in VIEWER_PRIOR_PINS.items():
        service._pin(pid, elo, stamp)
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(league_id=LEAGUE, name="Roster Tiers", platform="sleeper",
                    members=[LeagueMember(user_id=ME, username="me",
                                          roster=list(MY_ROSTER), elo_ratings={}),
                             LeagueMember(user_id=OPP, username="opp",
                                          roster=list(THEIR_ROSTER), elo_ratings={})])
    trade_svc.add_league(league)
    sess = {"verified": True, "user_id": ME, "league": league, "players": players,
            "user_roster": list(MY_ROSTER), "services": {FMT: service},
            "service": service, "trade_svcs": {FMT: trade_svc}, "trade_svc": trade_svc,
            "active_format": FMT, "last_active": 0.0}

    server.app.config["TESTING"] = True
    client = server.app.test_client()
    old_flags, old_cfg = ff._flags_cache, dict(ts._cfg)
    # Both relevant flags OFF: the roster scope must not depend on either.
    ff._flags_cache = {**ff.DEFAULT_FLAGS}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    events = []
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event",
                      MagicMock(side_effect=lambda uid, name, **kw: events.append((name, kw)))):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, sess, service, league, events
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            ff._flags_cache = old_flags
            ts._cfg.clear()
            ts._cfg.update(old_cfg)


def _save(client, tiers, position="RB", **extra):
    body = {"position": position, "tiers": tiers,
            "scope": "roster", "via": "roster_setup", **extra}
    r = client.post("/api/tiers/save", data=json.dumps(body),
                    content_type="application/json",
                    headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200, r.data
    return r.get_json()


def _board(service):
    return {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}


def _context(sess, service, league):
    return server._owner_generation_context(
        sess=sess, service=service, league=league,
        players={p.id: p for p in sess["players"]}, seed_map=dict(SEED),
        user_elo=_board(service), user_roster=list(sess["user_roster"]),
        scoring_format=FMT, fairness_threshold=.5,
        captured_rankings={OPP: {"elo_ratings": dict(OPP_BOARD),
                                 "confidence_sources": {p: "explicit" for p in OPP_BOARD}}},
        pinned_give_players=None, pinned_receive_players=None,
        opponent_user_id=None, trade_intent=None)


def _evaluate_x_for_y(sess, service, league):
    card = ts.TradeCard("c", LEAGUE, ME, OPP, "opp", ["x"], ["y"], 0, 0, 0)
    proof = owner.evaluate_owner_trade(card, **_context(sess, service, league))
    return proof.as_dict()


# ───────────────────────────── 1-3: the merged-band write ─────────────────────────────

def test_1_roster_save_changes_elo_only_for_posted_ids(harness):
    """Whole-board diff: the posted id moves, every other player's Elo is
    unchanged to the float."""
    client, _, service, _, _ = harness
    before = _board(service)
    _save(client, {"first_1": ["x"]})
    after = _board(service)
    changed = {pid for pid in before if after[pid] != before[pid]}
    assert changed == {"x"}


def test_2_single_player_moved_up_lands_at_the_band_floor(harness):
    """first_1 already holds i1/i2, so the merged-band rule puts a promoted X
    at the bottom of the tier (1580). The unscoped writer would pin a lone
    pid at the ceiling (1785) — two firsts' worth, above every incumbent."""
    client, _, service, _, _ = harness
    _save(client, {"first_1": ["x"]})
    assert service._elo_overrides["x"] == pytest.approx(1580.0)
    assert _board(service)["x"] == pytest.approx(1580.0)
    assert load_tier_overrides(ME, FMT)["x"] == pytest.approx(1580.0)


def test_3_target_band_incumbents_keep_byte_identical_overrides(harness):
    """No respread: i1's existing override and i2's absence of one survive."""
    client, _, service, _, _ = harness
    _save(client, {"first_1": ["x"]})
    assert service._elo_overrides["i1"] == 1700.0
    assert "i2" not in service._elo_overrides
    assert service._elo_overrides["y"] == 1560.0


# ───────────────────────────── 4-6: route semantics ─────────────────────────────

def test_4_roster_scope_is_read_with_both_flags_off(harness):
    """§1.8: the server reads scope:'roster' UNGATED. The fixture runs with
    DEFAULT_FLAGS, where both flags are False; the subset writer must be the
    one called, never apply_tiers."""
    client, _, service, _, _ = harness
    assert ff.is_enabled("ranks.rookie_subset") is False
    assert ff.is_enabled("trades.roster_tier_rank") is False
    with patch.object(service, "apply_tiers",
                      MagicMock(side_effect=AssertionError("unscoped writer"))) as plain, \
         patch.object(service, "apply_tiers_subset",
                      wraps=service.apply_tiers_subset) as subset:
        _save(client, {"first_1": ["x"]}, cleared_pids=["f1"])
    plain.assert_not_called()
    assert subset.call_count == 1
    assert subset.call_args.kwargs["scope_pids"] == {"x", "f1"}


def test_5_roster_save_does_not_mark_the_position_complete(harness):
    client, _, _, _, _ = harness
    assert get_tiers_saved(ME, scoring_format=FMT) == []
    out = _save(client, {"first_1": ["x"]})
    assert out["saved"] == [] and out["all_done"] is False
    assert get_tiers_saved(ME, scoring_format=FMT) == []


def test_6_tier_save_event_carries_via_roster_setup(harness):
    client, _, _, _, events = harness
    _save(client, {"first_1": ["x"]})
    tier_saves = [kw for name, kw in events if name == "tier_save"]
    assert len(tier_saves) == 1
    assert tier_saves[0]["props"]["via"] == "roster_setup"
    assert tier_saves[0]["props"]["position"] == "RB"
    assert "quickset_completed" not in [n for n, _ in events]


# ───────────────────────────── 7-8: what the engine reads ─────────────────────────────

def test_7_posted_ids_are_explicit_in_the_next_owner_context(harness):
    client, sess, service, league, _ = harness
    assert _context(sess, service, league)["user_sources"]["x"] == "consensus"
    _save(client, {"first_1": ["x"]})
    sources = _context(sess, service, league)["user_sources"]
    assert sources["x"] == "explicit"
    assert sources["z"] == "consensus"          # not posted, not touched


def test_8_moving_x_up_two_tiers_makes_an_at_market_give_viewer_no_benefit(harness):
    """The endowment correction (§1.6.2). X-for-Y is at market (both seed
    1500), the viewer values Y above market and the opponent values X above
    Y, so the card is eligible. Lifting X second → firsts_2 through the
    roster save prices X far above Y on the viewer's board: the same card is
    now rejected as viewer_no_benefit, while the market floor still passes."""
    client, sess, service, league, _ = harness
    before = _evaluate_x_for_y(sess, service, league)
    assert before["eligible"] is True, before.get("reason")
    assert before["market"]["ratio"] == pytest.approx(1.0)

    _save(client, {"firsts_2": ["x"]})
    assert 1788 <= _board(service)["x"] <= 1864        # in firsts_2

    after = _evaluate_x_for_y(sess, service, league)
    assert after["eligible"] is False
    assert after["reason"] == "viewer_no_benefit"
    assert after["viewer"]["personal_gain_fraction"] < 0


def test_8b_the_same_move_as_a_reorder_leaves_the_card_eligible(harness):
    """Control for test 8 (its named sabotage): the old step's reorder of the
    roster's RBs (X first) is a permutation of the roster's own Elos — X can
    only take Z's 1530, still below the viewer's 1560 on Y — so the
    at-market give stays eligible. Only an absolute placement corrects it."""
    client, sess, service, league, _ = harness
    r = client.post("/api/rankings/reorder",
                    data=json.dumps({"position": "RB", "ordered_ids": ["x", "z"]}),
                    content_type="application/json",
                    headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200, r.data
    assert _board(service)["x"] == pytest.approx(1530.0)
    after = _evaluate_x_for_y(sess, service, league)
    assert after["eligible"] is True, after.get("reason")


# ──────────────── 9-13: placement pins (review fixes, 2026-11-11) ────────────────
# RB bands (1qb_ppr): firsts_4plus 1927-1972 · firsts_2 1788-1864 ·
# first_1 1580-1785 · second 1370-1575 · third 1280-1365.

def test_9_single_player_moved_down_lands_at_the_ceiling_of_the_lower_band(harness):
    """i2 (1650, first_1) → second, which holds x/z/y/f1: a demoted player
    anchors at the TOP of the merge, i.e. the band ceiling."""
    client, _, service, _, _ = harness
    _save(client, {"second": ["i2"]})
    assert service._elo_overrides["i2"] == 1575.0


def test_10_several_moved_into_one_tier_keep_submitted_order(harness):
    """z, f1, x up into first_1 (incumbents i1 1700, i2 1650). Merged list
    [i1, i2, z, f1, x] spread 1785→1580 over five slots; the three posted ids
    take slots 2-4 in SUBMITTED order. Exact values pinned on purpose."""
    client, _, service, _, _ = harness
    _save(client, {"first_1": ["z", "f1", "x"]})
    o = service._elo_overrides
    assert (o["z"], o["f1"], o["x"]) == (1682.5, 1631.25, 1580.0)
    assert o["i1"] == 1700.0 and "i2" not in o


def test_11_up_move_into_a_band_empty_at_the_position_lands_at_the_floor(harness):
    """Fix 3: no RB in firsts_4plus. A lone up-mover gets the floor (1927),
    not the ceiling (1972); two up-movers stack from the floor upward in
    submitted order: [EDGE, x, f1] → x 1949.5, f1 1927."""
    client, _, service, _, _ = harness
    _save(client, {"firsts_4plus": ["x"]})
    assert service._elo_overrides["x"] == 1927.0
    _save(client, {"firsts_2": ["z", "f1"]})
    assert (service._elo_overrides["z"], service._elo_overrides["f1"]) == (1826.0, 1788.0)


def test_12_down_move_into_a_band_empty_at_the_position_lands_at_the_ceiling(harness):
    """No RB in third. A lone down-mover gets the ceiling (1365); two stack
    from the ceiling downward in submitted order: [i2, i1, EDGE] → 1365, 1322.5."""
    client, _, service, _, _ = harness
    _save(client, {"third": ["i1"]})
    assert service._elo_overrides["i1"] == 1365.0
    _save(client, {"fourth": ["i2", "y"]})
    assert (service._elo_overrides["i2"], service._elo_overrides["y"]) == (1275.0, 1247.5)


def test_13_ids_not_at_the_position_or_not_in_the_pool_are_ignored(harness):
    """A WR save naming an RB writes nothing; an RB save naming an unknown id
    writes only the real RB."""
    client, _, service, _, _ = harness
    before_o, before_b = dict(service._elo_overrides), _board(service)
    _save(client, {"first_1": ["x"]}, position="WR")
    assert service._elo_overrides == before_o and _board(service) == before_b
    _save(client, {"first_1": ["ghost", "x"]})
    assert set(service._elo_overrides) - set(before_o) == {"x"}
    assert "ghost" not in load_tier_overrides(ME, FMT)
    assert {p for p in before_b if _board(service)[p] != before_b[p]} == {"x"}


def test_14_rookie_path_lone_player_in_an_empty_band_still_gets_the_ceiling(harness):
    """Every non-roster caller of apply_tiers_subset is unchanged: without
    `empty_band_edge` a lone scoped pid in an empty band is pinned at hi."""
    _, _, service, _, _ = harness
    service.apply_tiers_subset(position="RB", tiers={"firsts_4plus": ["x"]},
                               scope_pids={"x"}, scoring_format=FMT)
    assert service._elo_overrides["x"] == 1972.0
