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
     any inversion (the exact #263 scale-confusion bug) reads a 2117-value
     1st as Elo 2117 → 'firsts_4plus', and a 406-value 3rd as Elo 406 →
     None. Both literal assertions fail.
  S1b "wrong INVERSE" (D-088, the defect this file's pins now trap):
     inverting with `seed_elo_for_value` instead of `value_to_elo`. That
     reads a value-scale number as a DynastyProcess 0-10000 consensus
     value, inflating every rung cheaper than a mid-1st — Mid 3rd 1320 →
     1383.5, Mid 4th 1240 → 1339.3 — so a current-year 3rd badges 'second'
     and a current-year 4th badges 'third'. Both are pinned literally, and
     `test_current_year_rungs_badge_their_own_round` pins the underlying
     identity so no future inverse can drift back.
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
from backend.pick_values import GENERIC_PICK_SEEDS, pick_pool_value
from backend.trade_service import value_to_elo

LEAGUE = "league_picks_tier_test"
TOKEN = "sess-picks-tier-test"

# The load_draft_picks row shape the route consumes; pool_value written the
# way sync writes it (pick_pool_value with years_out = season - current
# season; current season 2026 here). Expected rungs verified against the
# canonical band walk at authoring time (1qb_ppr bands, position-uniform):
#   2026 1st  → pool 2117.0 → Elo 1650.0 → 'first_1'
#   2027 2nd  → pool  515.6 → Elo 1367.5 → 'third'    (D-088: was 'second')
#   2026 3rd  → pool  406.6 → Elo 1320.0 → 'third'    (D-088: was 'second')
#   2027 3rd  → pool  345.6 → Elo 1287.5 → 'third'
#   2026 4th  → pool  272.5 → Elo 1240.0 → 'fourth'   (D-088: was 'third')
#
# ⚠️  D-088 (2026-08-19) CORRECTED THE INVERSE AND MOVED 600 OF 1104 LIVE
# PICK BADGES. The Elo column above USED to read 1635.5 / 1413.3 / 1383.5 /
# 1364.6 / 1339.3, because #320 inverted `pool_value` with
# `seed_elo_for_value` (which inverts DynastyProcess's raw 0-10000 scale)
# rather than `value_to_elo` (the true inverse of the `elo_to_value` units
# `pool_value` is stored in — see database.py's column comment). The two
# maps agree only at Elo 1548.0, so every rung below a mid-1st was inflated,
# growing with cheapness: +63.4 Elo at the Mid 3rd, +99.3 at the Mid 4th,
# +109.5 at the Late 4th.
#
# That inflation — NOT the D-084 band move, and NOT the seed map's genuine
# rank compression — is why a current-year 3rd badged "2nd" once the
# `second` floor dropped to 1370: the inflated 1383.5 cleared it. The pick's
# real price is Elo 1320, 45 points inside `third`.
#
# The fix restores an identity that tier_config.json's own `_calibration`
# already asserts ("third floor = Late 3rd seed 1280"): a CURRENT-YEAR pick
# of round R badges exactly where GENERIC_PICK_SEEDS[(R, "Mid")] sits.
# `test_current_year_rungs_badge_their_own_round` pins that for all four
# rounds, so a future edit cannot silently swap the inverse back.
# Rationale + measurement: docs/reviews/2026-08-19-pick-badge-scale.md.
#   2029 1st  → pool 2117.0 → Elo 1650.0 → 'first_1' (D-079: firsts are flat)
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
    # A CURRENT-YEAR 4th — the second rung D-088 moved (was 'third', which
    # claimed a 4th this year was worth a 3rd-round pick). Elo 1240.
    {"pick_id": f"{LEAGUE}_2026_4_2", "league_id": LEAGUE, "season": 2026,
     "round": 4, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(4, 0)},
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
    # D-088: the current-year 3rd bands where its OWN rung sits (Elo 1320,
    # 45 points inside `third`). Sabotage S1b puts this back at 'second'.
    assert rows[f"{LEAGUE}_2026_3_1"]["tier"] == "third"
    # ...and a 2027 3rd, discounted a year, is still 'third' too.
    assert rows[f"{LEAGUE}_2027_3_1"]["tier"] == "third"
    # A discounted 2027 2nd is worth LESS than a late 2026 2nd (Elo 1367.5
    # vs the 1370 `second` floor), so it honestly reads 'third' — D-320-2's
    # rule, applied with the correct inverse. Under S1b this reads 'second'.
    assert rows[f"{LEAGUE}_2027_2_1"]["tier"] == "third"


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
        value_to_elo(float(row["pool_value"])), None, "1qb_ppr")
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


def test_current_year_rungs_badge_their_own_round(client):
    """D-088 — THE INVARIANT, not a literal restatement of it.

    `tier_config.json`'s `_calibration` defines each band's floor AS a rung
    of `GENERIC_PICK_SEEDS` ("third floor = Late 3rd seed 1280"), which is
    only coherent if the seeds live on the tier-band Elo scale. So a
    CURRENT-year pick — `years_out == 0`, no decay applied — must badge
    exactly where its own Mid rung sits. Any inverse other than
    `value_to_elo` breaks this for at least one round:

      * `seed_elo_for_value` (the #320 defect) → r3 'second', r4 'third'
      * no inversion at all (the #263 defect) → r1 'firsts_4plus', r3 None

    Asserted through the ROUTE, so it covers the serializer and not just the
    helper, and asserted for all four rounds so a single-round patch cannot
    satisfy it."""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    rows = _picks_by_id(body)
    served = {1: f"{LEAGUE}_2026_1_1", 3: f"{LEAGUE}_2026_3_1",
              4: f"{LEAGUE}_2026_4_2"}
    for rnd, pick_id in served.items():
        seed_tier = server.RankingService.tier_for_elo(
            GENERIC_PICK_SEEDS[(rnd, "Mid")], None, "1qb_ppr")
        assert rows[pick_id]["tier"] == seed_tier, (
            f"round {rnd}: badge {rows[pick_id]['tier']!r} != its own rung "
            f"{seed_tier!r} (Elo {GENERIC_PICK_SEEDS[(rnd, 'Mid')]})")
    # …and the round-2 rung too, via the current-year asserted pick row.
    assert rows[f"{LEAGUE}_2026_2_9"]["tier"] == (
        server.RankingService.tier_for_elo(
            GENERIC_PICK_SEEDS[(2, "Mid")], None, "1qb_ppr"))
    # The identity underneath, stated directly: value_to_elo is the EXACT
    # inverse of the elo_to_value units pick_pool_value returns.
    for rnd in (1, 2, 3, 4):
        assert abs(value_to_elo(pick_pool_value(rnd, 0))
                   - GENERIC_PICK_SEEDS[(rnd, "Mid")]) < 0.05
    # Named literals, so "all four collapsed to one tier" fails here.
    assert rows[f"{LEAGUE}_2026_1_1"]["tier"] == "first_1"
    assert rows[f"{LEAGUE}_2026_2_9"]["tier"] == "second"
    assert rows[f"{LEAGUE}_2026_3_1"]["tier"] == "third"
    assert rows[f"{LEAGUE}_2026_4_2"]["tier"] == "fourth"


def test_deep_far_out_pick_tiers_null_rather_than_flattering_it(client):
    """A pick priced BELOW the `waivers` floor (1150) gets no badge at all
    — the documented null-tier contract, same as an unpriced row — never a
    fabricated `third`. Under the #320 inverse a 2029 4th read Elo 1330.7
    and badged 'third'; its real price is Elo 1142.5, below every band.

    This is the one case where the fix removes a badge rather than lowering
    it, so it is pinned explicitly."""
    from backend.pick_values import pick_pool_value as _ppv
    deep = {"pick_id": f"{LEAGUE}_2029_4_1", "league_id": LEAGUE,
            "season": 2029, "round": 4, "owner_user_id": "u_b",
            "owner_username": "bob", "is_traded": 0,
            "original_username": "bob", "pool_value": _ppv(4, 3)}
    with patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw: [dict(deep)]):
        _install_sess(_mk_sess())
        code, body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    row = _picks_by_id(body)[f"{LEAGUE}_2029_4_1"]
    assert row["pool_value"] is not None
    assert value_to_elo(float(row["pool_value"])) < 1150.0
    assert row["tier"] is None
