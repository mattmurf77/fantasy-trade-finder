"""#320 — additive `tier` per pick row on GET /api/league/picks.

D-320-1 (operator 2026-08-16, supersedes #263's "picks stay numeric"): pick
rows on calculator surfaces carry the pick-value ladder rung their
DISCOUNTED `pool_value` sits in, so the client can badge them through the
same TierBadge/TIER_LABEL machinery it uses for players — never a
client-side derivation from the display value.

Every tier assertion below pins a LITERAL rung, because the two named
sabotages both produce a "tier" that a tautological
tier-equals-whatever-the-helper-returns test would wave through:

  S1 "wrong scale": passing `pool_value` straight to `tier_for_elo` without
     `seed_elo_for_value` (the exact #263 scale-confusion bug) reads a
     2117-value 1st as Elo 2117 → 'firsts_4plus', and a 406-value 3rd as
     Elo 406 → None. Both literal assertions fail.
  S2 "platform-only tiers": skipping tier for `source: 'user'` rows fails
     the asserted-pick case.

Isolation mirrors test_power_rankings.py's route tests: Flask test client,
injected session, patched load_draft_picks, no network/DB.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend.data_loader import seed_elo_for_value
from backend.pick_values import pick_pool_value

LEAGUE = "league_picks_tier_test"
TOKEN = "sess-picks-tier-test"

# The load_draft_picks row shape the route consumes; pool_value written the
# way sync writes it (pick_pool_value with years_out = season - current
# season; current season 2026 here). Expected rungs verified against the
# canonical band walk at authoring time (1qb_ppr bands, position-uniform):
#   2026 1st  → pool 2117.0 → Elo 1635.5 → 'first_1'
#   2027 2nd  → pool  515.6 → Elo 1413.3 → 'second'   (D-084: was 695.9)
#   2026 3rd  → pool  406.6 → Elo 1383.5 → 'second'   (!! see below)
#   2027 3rd  → pool  345.6 → Elo 1364.6 → 'third'
#
# ⚠️  D-084 (2026-08-19) MOVED ONE BADGE, AND IT IS THE ONE ODD-LOOKING
# CONSEQUENCE OF THE ROUND-2 RECALIBRATION. The `second` floor dropped
# 1400 → 1370 with the Late 2nd seed. A CURRENT-YEAR 3rd prices at Elo
# 1383.5 on the consensus seed map, which used to sit 16.5 points BELOW the
# old floor and now sits 13.5 points ABOVE the new one — so a 2026 3rd-round
# pick badges "2nd". Every other rung is unmoved: all four round-2 rungs
# still badge 'second', and 2027+ 3rds and every 4th still badge 'third'.
#
# This is NOT a banding bug. It is the pre-existing round-3 OVERPRICE
# becoming visible: docs/reviews/2026-08-19-ktc-pick-value-comparison.md
# measures a mid-3rd at ~67 ranks too dear, and shows the cause is
# `seed_elo_for_value` compressing ranks 200-300 into 32 Elo points — which
# no pick-seed edit can fix (Q-019, and the reason D-084 deliberately left
# rounds 3-4 alone). The badge is honest about what our engine currently
# believes a current-year 3rd is worth. Fixing it means opening the seed
# map. Both rungs are pinned below so neither can drift unnoticed.
#   2029 1st  → pool 1300.1 → Elo 1551.7 → 'second'  (D-320-2: the badge is
#                the discounted price, not the pick's name)
PICK_ROWS = [
    {"pick_id": f"{LEAGUE}_2026_1_1", "league_id": LEAGUE, "season": 2026,
     "round": 1, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(1, 0)},
    {"pick_id": f"{LEAGUE}_2027_2_1", "league_id": LEAGUE, "season": 2027,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(2, 1)},
    {"pick_id": f"{LEAGUE}_2026_3_1", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(3, 0)},
    # Far-out 1st, heavily discounted — nominal round 1, badge 'second'.
    {"pick_id": f"{LEAGUE}_2029_1_1", "league_id": LEAGUE, "season": 2029,
     "round": 1, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(1, 3)},
    # A 2027 3rd — still 'third' after D-084, so the band is provably still
    # reachable and "everything collapsed upward" fails here.
    {"pick_id": f"{LEAGUE}_2027_3_1", "league_id": LEAGUE, "season": 2027,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(3, 1)},
    # A leaguemate-ASSERTED pick (W3 M-C `source: 'user'`) — prices, so it
    # tiers exactly like a platform row (sabotage S2 trap).
    {"pick_id": f"{LEAGUE}_2026_2_9", "league_id": LEAGUE, "season": 2026,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice", "source": "user",
     "pool_value": pick_pool_value(2, 0)},
    # NULL pool_value (pre-pool_value-column row) — no price, no tier.
    {"pick_id": f"{LEAGUE}_2026_4_1", "league_id": LEAGUE, "season": 2026,
     "round": 4, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": None},
]


def _mk_sess(user_id="u_a", fmt="1qb_ppr"):
    """Minimal session satisfying _require_initialized_session."""
    return {
        "user_id":       user_id,
        "active_format": fmt,
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE, platform=None,
                                         members=[]),
        "players":       [],
        "trade_svc":     object(),
        "trade_svcs":    {fmt: object()},
        "services":      {},
        "service":       None,
        "user_roster":   [],
    }


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw:
                      [dict(p) for p in PICK_ROWS]
                      if league_id == LEAGUE else []):
        try:
            yield c
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _install_sess(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _get(c, path):
    r = c.get(path, headers={"X-Session-Token": TOKEN})
    return r.status_code, json.loads(r.data)


def _picks_by_id(body):
    return {p["pick_id"]: p for p in body["all_picks"]}


def test_pick_rows_carry_literal_tier_rungs(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    rows = _picks_by_id(body)
    # Sabotage S1 "wrong scale" turns these into 'firsts_4plus' / None /
    # None respectively — the literal rungs are the trap.
    assert rows[f"{LEAGUE}_2026_1_1"]["tier"] == "first_1"
    assert rows[f"{LEAGUE}_2027_2_1"]["tier"] == "second"
    # D-084: a CURRENT-year 3rd now clears the lowered `second` floor
    # (Elo 1383.5 >= 1370). Deliberate and explained in the header note.
    assert rows[f"{LEAGUE}_2026_3_1"]["tier"] == "second"
    # ...while a 2027 3rd still bands as 'third', so the band is reachable.
    assert rows[f"{LEAGUE}_2027_3_1"]["tier"] == "third"


def test_far_out_pick_tier_is_the_discounted_band(client):
    """D-320-2's RULE is unchanged — the badge reflects TODAY's value, not
    the pick's name. D-079 changed the VALUE it reflects: a 2029 1st no
    longer decays (2117.0, not 1300.1), so the honest badge is now 'first_1'
    rather than 'second'. The operator reported the old badge's cause
    directly ("2029 1st values are the issue"), so this test now pins the
    fix. The S1 "wrong scale" trap is preserved by the canonical-walk
    assertion below: unscaled, 2117.0 would read as Elo 2117 and mis-band.

    A round that still decays is asserted alongside it, so "someone flattened
    every round" fails here rather than shipping."""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    rows = _picks_by_id(body)
    row = rows[f"{LEAGUE}_2029_1_1"]
    assert row["round"] == 1
    assert row["tier"] == "first_1"
    # ...and it matches the canonical walk over the inverted value map.
    assert row["tier"] == server.RankingService.tier_for_elo(
        seed_elo_for_value(float(row["pool_value"])), None, "1qb_ppr")
    # A far-out 1st is now worth exactly a current-year 1st...
    assert float(row["pool_value"]) == float(
        rows[f"{LEAGUE}_2026_1_1"]["pool_value"])
    # ...while a future 2nd is still worth strictly less than a current one.
    assert float(rows[f"{LEAGUE}_2027_2_1"]["pool_value"]) < float(
        rows[f"{LEAGUE}_2026_2_9"]["pool_value"])


def test_asserted_user_source_pick_carries_tier_too(client):
    """Sabotage S2 "platform-only tiers": a `source: 'user'` row prices, so
    it tiers — skipping it fails here. (The provenance MARKER is a separate,
    flag-gated concern; the tier is not.)"""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    assert _picks_by_id(body)[f"{LEAGUE}_2026_2_9"]["tier"] == "second"


def test_null_pool_value_yields_null_tier_not_a_guess(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    row = _picks_by_id(body)[f"{LEAGUE}_2026_4_1"]
    assert row["pool_value"] is None
    assert row["tier"] is None


def test_my_picks_rows_carry_tier_and_demo_league_unchanged(client):
    _install_sess(_mk_sess(user_id="u_a"))
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    # my_picks is a filtered view of the SAME serialized rows.
    assert {p["pick_id"] for p in body["my_picks"]} == {
        f"{LEAGUE}_2026_1_1", f"{LEAGUE}_2027_2_1", f"{LEAGUE}_2026_2_9"}
    assert all("tier" in p for p in body["my_picks"])
    # Demo early-return path: no rows, no tier work, shape unchanged.
    code, demo = _get(client, "/api/league/picks?league_id=league_demo")
    assert code == 200
    assert demo == {"my_picks": [], "all_picks": [],
                    "picks_supported": True}
