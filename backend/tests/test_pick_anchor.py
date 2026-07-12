"""Pick-anchor wizard (POST /api/anchor/save) + pick-gap equivalence.

The anchor wizard pins a player's Elo from a pick-denominated value
statement ("worth 2 firsts"). Covers:

  (a) anchor→Elo mapping: single-pick anchors pin to the generic pick's
      seed; multi-first anchors are VALUE multiples of the base first
      (Mid 1st) mapped back through value_to_elo; no_value pins below
      the lowest band.
  (b) the route: 200 + override written + persistence called; 400 on a
      bad anchor key; 404 on an unknown player.
  (c) tier assignment falls out of the pinned Elo (band walk); with the
      pick-value tier ladder (2026-07-11) the bands are position-uniform,
      so every anchor lands in the tier that carries its name.
  (d) _pick_gap_equivalent: nearest-pick selection + firsts unit +
      the negligible / too-big cutoffs.
  (e) candidate ordering (#112): the wizard queue's source —
      get_rankings(position=None) — serves players value-descending, so
      the highest-value unanchored player is always asked first and depth
      players only surface once the top of the board is anchored.
  (f) per-user pick-value scale (#111, re-derived for the #117 8-tier
      ladder): "top-tier asset = N firsts" re-spaces the multi-first
      anchors (power curve, γ = log 4 / log N), leaves single-pick
      anchors + no_value untouched, persists per user + format, and is
      byte-identical to the plain m × base mapping at the default N = 4
      (the recalibrated consensus top asset sits at the 4-firsts rung).
"""
import json
import math
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
import backend.trade_service as ts
from backend.database import load_anchor_scale, save_anchor_scale, metadata
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
    # 2 firsts ≈ Elo 1789 → firsts_2 (floor 1788) — the anchor lands
    # in the tier that carries its name.
    assert d["tier"] == "firsts_2"
    assert d["value"] == pytest.approx(2 * _mid_first_value(), rel=1e-3)
    save_overrides.assert_called_once()


def test_anchor_value_and_tier_are_position_uniform(harness):
    client, service, token, _ = harness
    rb = _post(client, token, {"player_id": "rb1", "anchor": "1_second"}).get_json()
    qb = _post(client, token, {"player_id": "qb1", "anchor": "1_second"}).get_json()
    # Same anchor → same Elo/value regardless of position…
    assert rb["elo"] == qb["elo"] == 1460
    assert rb["value"] == qb["value"]
    # …and, with the position-uniform pick-value ladder, the same tier —
    # the one that carries the anchor's name ("worth a 2nd" → second).
    assert rb["tier"] == "second"
    assert qb["tier"] == "second"


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


# ---------------------------------------------------------------------------
# (e) candidate ordering (#112) — the wizard queue's source contract
# ---------------------------------------------------------------------------

def test_wizard_candidate_source_is_value_descending():
    """The wizard asks remaining[0] of get_rankings(None): top value first,
    depth only after the board's top players are anchored/answered."""
    pool = [
        Player(id="depth1", name="Depth Guy",  position="RB", team="AAA", age=27),
        Player(id="elite1", name="Elite Guy",  position="WR", team="BBB", age=24),
        Player(id="mid1",   name="Middle Guy", position="QB", team="CCC", age=25),
    ]
    seeds = {"elite1": 1800.0, "mid1": 1500.0, "depth1": 1300.0}
    service = RankingService(players=pool, seed_ratings=seeds)

    ranked = service.get_rankings(position=None).rankings
    elos = [rp.elo for rp in ranked]
    assert elos == sorted(elos, reverse=True)
    assert [rp.player.id for rp in ranked] == ["elite1", "mid1", "depth1"]

    # Anchoring reshuffles the board but the serve order stays descending:
    # with elite1 answered, the next-highest-value player is up, and the
    # depth player still comes last.
    service.apply_anchor("elite1", 1789.0)
    ranked2 = service.get_rankings(position=None).rankings
    elos2 = [rp.elo for rp in ranked2]
    assert elos2 == sorted(elos2, reverse=True)
    remaining = [rp.player.id for rp in ranked2 if rp.player.id != "elite1"]
    assert remaining == ["mid1", "depth1"]


# ---------------------------------------------------------------------------
# (f) per-user pick-value scale (#111)
# ---------------------------------------------------------------------------

def test_default_scale_is_byte_identical_for_every_anchor_key():
    for key in server.VALID_ANCHORS:
        assert server._anchor_target_elo(key) == server._anchor_target_elo(
            key, top_tier_firsts=server.ANCHOR_TOP_TIER_FIRSTS_DEFAULT)
    # And the default constant really is the plain math (m × base first) —
    # N = 4 since the #117 ladder re-derivation (γ = log 4 / log 4 = 1).
    assert server.ANCHOR_TOP_TIER_FIRSTS_DEFAULT == 4.0
    assert server._anchor_target_elo("3_firsts") == pytest.approx(
        ts.value_to_elo(3 * _mid_first_value()))


def test_scale_respaces_multi_first_anchors_only():
    top_tier_elo = server._anchor_target_elo("4_firsts")  # default top-tier pin
    for n in (2.0, 3.0):
        key = f"{int(n)}_firsts"
        # The user's own "top-tier = N firsts" answer lands exactly where
        # the default math pins a top-tier asset (the 4-firsts rung).
        assert server._anchor_target_elo(key, top_tier_firsts=n) == \
            pytest.approx(top_tier_elo)
        # Single-pick anchors + no_value are consensus assets — untouched.
        for fixed in ("1_first", "1_second", "1_third", "1_fourth", "no_value"):
            assert server._anchor_target_elo(fixed, top_tier_firsts=n) == \
                server._anchor_target_elo(fixed)
        # Ladder stays monotone: 4 > 3 > 2 firsts > the actual Mid 1st.
        ladder = [server._anchor_target_elo(k, top_tier_firsts=n)
                  for k in ("4_firsts", "3_firsts", "2_firsts", "1_first")]
        assert ladder == sorted(ladder, reverse=True)


def test_anchor_scale_persistence_roundtrip():
    """save/load_anchor_scale: per-format isolation + unset → None."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        with eng.begin() as conn:
            conn.execute(db_module.users_table.insert().values(
                sleeper_user_id=ME, username="anchor_tester"))
        assert load_anchor_scale(ME, scoring_format="1qb_ppr") is None
        save_anchor_scale(ME, 3.0, scoring_format="1qb_ppr")
        assert load_anchor_scale(ME, scoring_format="1qb_ppr") == 3.0
        assert load_anchor_scale(ME, scoring_format="sf_tep") is None
        save_anchor_scale(ME, 4.0, scoring_format="sf_tep")
        assert load_anchor_scale(ME, scoring_format="1qb_ppr") == 3.0
        assert load_anchor_scale(ME, scoring_format="sf_tep") == 4.0


def test_anchor_save_route_applies_user_scale(harness):
    client, service, token, _ = harness
    with patch.object(server, "load_anchor_scale", return_value=3.0):
        d = _post(client, token, {"player_id": "rb1", "anchor": "3_firsts"}).get_json()
    # Under "top-tier = 3 firsts", a 3-firsts answer pins to the default
    # top-tier Elo (what 4_firsts maps to at the default scale).
    assert d["elo"] == pytest.approx(server._anchor_target_elo("4_firsts"), abs=0.1)
    assert d["top_tier_firsts"] == 3.0
    assert service._elo_overrides["rb1"] == pytest.approx(d["elo"], abs=0.1)


def test_anchor_save_route_default_scale_unchanged(harness):
    client, _, token, _ = harness
    with patch.object(server, "load_anchor_scale", return_value=None):
        d = _post(client, token, {"player_id": "rb1", "anchor": "2_firsts"}).get_json()
    assert d["elo"] == pytest.approx(
        ts.value_to_elo(2 * _mid_first_value()), abs=0.1)
    assert d["top_tier_firsts"] == 4.0


def test_anchor_scale_route_get_post_and_validation(harness):
    client, _, token, _ = harness
    saved = {}

    def _fake_save(user_id, n, scoring_format):
        saved[scoring_format] = n

    with patch.object(server, "load_anchor_scale",
                      side_effect=lambda uid, scoring_format: saved.get(scoring_format)), \
         patch.object(server, "save_anchor_scale", side_effect=_fake_save):
        # GET before any save → default (N = 4 since the #117 re-derivation)
        r = client.get("/api/anchor/scale", headers={"X-Session-Token": token})
        assert r.status_code == 200
        assert r.get_json()["top_tier_firsts"] == 4.0

        # POST a valid scale, GET reflects it
        r = client.post("/api/anchor/scale",
                        headers={"X-Session-Token": token,
                                 "Content-Type": "application/json"},
                        data=json.dumps({"top_tier_firsts": 3}))
        assert r.status_code == 200 and r.get_json()["top_tier_firsts"] == 3.0
        r = client.get("/api/anchor/scale", headers={"X-Session-Token": token})
        assert r.get_json()["top_tier_firsts"] == 3.0

        # Invalid values → 400, nothing saved
        for bad in (1, 5, "lots", None):
            r = client.post("/api/anchor/scale",
                            headers={"X-Session-Token": token,
                                     "Content-Type": "application/json"},
                            data=json.dumps({"top_tier_firsts": bad}))
            assert r.status_code == 400
        assert saved == {"1qb_ppr": 3.0}
