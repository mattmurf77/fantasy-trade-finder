"""Pick-anchor wizard (POST /api/anchor/save) + pick-gap equivalence.

The anchor wizard pins a player's Elo from a pick-denominated value
statement ("worth 2 firsts"). Covers:

  (a) anchor→Elo mapping: single-pick anchors pin to the generic pick's
      seed; multi-first anchors are VALUE multiples of the base first
      (Mid 1st) mapped back through value_to_elo; no_value pins below
      the lowest band.
  (b) the route: 200 + override written + persistence called; 400 on a
      bad anchor key; 404 on an unknown player.
  (c) tier assignment falls out of the pinned Elo (band walk), and is
      position-aware even though the anchor VALUE is position-uniform.
  (d) _pick_gap_equivalent: nearest-pick selection + firsts unit +
      the negligible / too-big cutoffs.
"""
import json
import math
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
import backend.trade_service as ts
from backend.ranking_service import Player, RankingService

ME = "user_anchor_test"


def _mid_first_value() -> float:
    return ts.elo_to_value(server.GENERIC_PICK_SEEDS[(1, "Mid")])


# ---------------------------------------------------------------------------
# (a) anchor → target Elo mapping
# ---------------------------------------------------------------------------

def test_single_pick_anchors_pin_to_generic_pick_seeds():
    assert server._anchor_target_elo("1_first") == 1650
    assert server._anchor_target_elo("1_second") == 1460
    assert server._anchor_target_elo("1_third") == 1320
    assert server._anchor_target_elo("1_fourth") == 1240


def test_multi_first_anchors_are_value_multiples_of_the_base_first():
    for key, mult in (("2_firsts", 2), ("3_firsts", 3), ("4_firsts", 4)):
        elo = server._anchor_target_elo(key)
        assert elo is not None
        # Round-trip: the pinned Elo's value == mult × value(Mid 1st).
        assert ts.elo_to_value(elo) == pytest.approx(
            mult * _mid_first_value(), rel=1e-6)
    # Monotone: more firsts → higher Elo, and all above the single 1st.
    assert (server._anchor_target_elo("4_firsts")
            > server._anchor_target_elo("3_firsts")
            > server._anchor_target_elo("2_firsts")
            > server._anchor_target_elo("1_first"))


def test_no_value_pins_below_the_lowest_band():
    elo = server._anchor_target_elo("no_value")
    assert elo == server.ANCHOR_NO_VALUE_ELO
    assert RankingService.tier_for_elo(elo, "RB", "1qb_ppr") is None


def test_unknown_anchor_maps_to_none():
    assert server._anchor_target_elo("5_firsts") is None


def test_value_to_elo_inverts_elo_to_value():
    for elo in (1220.0, 1460.0, 1650.0, 1790.0):
        assert ts.value_to_elo(ts.elo_to_value(elo)) == pytest.approx(elo)


# ---------------------------------------------------------------------------
# (b)+(c) the route
# ---------------------------------------------------------------------------

@pytest.fixture()
def harness():
    """Injected initialized session with a real RankingService pool."""
    pool = [
        Player(id="rb1", name="Runner Back", position="RB", team="AAA", age=24),
        Player(id="qb1", name="Quarter Back", position="QB", team="BBB", age=26),
    ]
    service = RankingService(players=pool)

    token = "test-token-anchor"
    sess = {
        "user_id":       ME,
        "league":        None,          # no league → member_rankings publish skipped
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svc":     MagicMock(),
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()
    save_overrides = MagicMock()

    with patch.object(server, "save_tier_overrides", save_overrides):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, service, token, save_overrides
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _post(client, token, body):
    return client.post(
        "/api/anchor/save",
        headers={"X-Session-Token": token, "Content-Type": "application/json"},
        data=json.dumps(body),
    )


def test_anchor_save_pins_override_and_reports_tier(harness):
    client, service, token, save_overrides = harness
    r = _post(client, token, {"player_id": "rb1", "anchor": "2_firsts"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["anchor"] == "2_firsts"
    # Override written with the mapped Elo.
    assert service._elo_overrides["rb1"] == pytest.approx(d["elo"], abs=0.1)
    # 2 firsts ≈ Elo 1789 → elite for an RB in 1qb (elite floor 1600).
    assert d["tier"] == "elite"
    assert d["value"] == pytest.approx(2 * _mid_first_value(), rel=1e-3)
    save_overrides.assert_called_once()


def test_anchor_value_is_position_uniform_but_tier_is_band_aware(harness):
    client, service, token, _ = harness
    rb = _post(client, token, {"player_id": "rb1", "anchor": "1_second"}).get_json()
    qb = _post(client, token, {"player_id": "qb1", "anchor": "1_second"}).get_json()
    # Same anchor → same Elo/value regardless of position…
    assert rb["elo"] == qb["elo"] == 1460
    assert rb["value"] == qb["value"]
    # …but tier falls out of each position's band walk (1qb compresses QB:
    # a mid-2nd Elo is a top-5 1QB QB but only a starter-grade RB).
    assert rb["tier"] == "starter"
    assert qb["tier"] == "elite"


def test_anchor_save_rejects_bad_anchor_and_unknown_player(harness):
    client, _, token, _ = harness
    r = _post(client, token, {"player_id": "rb1", "anchor": "worth_a_lot"})
    assert r.status_code == 400
    assert "valid_anchors" in r.get_json()

    r = _post(client, token, {"player_id": "ghost", "anchor": "1_first"})
    assert r.status_code == 404

    r = _post(client, token, {"anchor": "1_first"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# (d) pick-gap equivalence
# ---------------------------------------------------------------------------

def test_gap_equivalent_finds_nearest_generic_pick():
    mid_2nd = ts.elo_to_value(server.GENERIC_PICK_SEEDS[(2, "Mid")])
    out = server._pick_gap_equivalent(mid_2nd * 1.02)
    assert out["pick_equivalent"]["pick_id"] == "generic_pick_2_mid"
    assert out["pick_equivalent"]["label"] == "Mid 2nd Round Pick"
    assert out["firsts"] == pytest.approx(mid_2nd * 1.02 / _mid_first_value(),
                                          abs=0.01)


def test_gap_equivalent_negligible_and_oversized_gaps_have_no_pick():
    min_pick = min(ts.elo_to_value(s) for s in server.GENERIC_PICK_SEEDS.values())
    max_pick = max(ts.elo_to_value(s) for s in server.GENERIC_PICK_SEEDS.values())
    assert server._pick_gap_equivalent(min_pick * 0.4)["pick_equivalent"] is None
    big = server._pick_gap_equivalent(max_pick * 2)
    assert big["pick_equivalent"] is None
    assert big["firsts"] > 1.5   # client falls back to the firsts unit
