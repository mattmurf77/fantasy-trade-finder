"""#320 — additive `tier` per pick row on GET /api/league/picks.

D-320-1 (operator 2026-08-16, supersedes #263's "picks stay numeric"): pick
rows on calculator surfaces carry the pick-value ladder rung their
`pool_value` sits in, so the client can badge them through the same
TierBadge/TIER_LABEL machinery it uses for players — never a client-side
derivation from the display value.

⚠️  **D-147 (2026-08-21) MOVED THE VALUE THIS FILE BADGES.** Closing Q-026,
the route now serves `_priced_pick_value` — the engine's own three-step
waterfall (own slot → round curve → stored ladder) under the same D-090
resolution a trade card charges — instead of the stored `draft_picks.
pool_value`. Every literal below is re-derived from the pricing functions
against the checked-in DP snapshot (`conftest.py` pins
`FTF_DP_PICK_VALUES_FILE`); no tolerance was widened and nothing is asserted
against "whatever the helper returned".

The rule is UNCHANGED — a badge reflects the value it is served (D-320-2) —
and so are the BANDS: `tier_config.json` and its five client mirrors
(docs/cross-client-invariants.md, G-051) are byte-identical, as is the
inverse (`value_to_elo`, D-088). What changed is the price, and therefore
the badge. The headline the operator asked for is
`test_slotted_first_badges_above_a_slotted_twelfth`: a 2026 1.01 and a 2026
1.12 used to be one number and one badge; they are now 4867.1/`firsts_2` and
820.8/`second`.

Every tier assertion pins a LITERAL rung, because the three named sabotages
all produce a "tier" that a tautological tier-equals-whatever-the-helper-
returns test would wave through. All three were re-verified against the
PRICED values at the D-147 rewrite:

  S1 "wrong scale": passing the value straight to `tier_for_elo` without any
     inversion (the #263 bug) reads the 1859.5 round-curve 1st as Elo 1859.5
     → 'firsts_2', and every cheaper rung → None.
  S1b "wrong INVERSE" (D-088): inverting with `seed_elo_for_value` instead of
     `value_to_elo` reads a value-scale number as a DynastyProcess 0-10000
     consensus value, inflating everything cheaper than a mid-1st — the
     current-year 2nd reads 'second' instead of 'third', the 3rd 'third'
     instead of 'fourth', the 4th 'third' instead of 'waivers'.
  S2 "platform-only tiers": skipping tier for `source: 'user'` rows fails the
     asserted-pick case.
  S3 (new, D-147) "left on the ladder": serving `p["pool_value"]` verbatim —
     the pre-D-147 code — puts every 2026 first back at 2117.0/'first_1',
     which `test_slotted_first_badges_above_a_slotted_twelfth` and every
     round-curve literal reject.

Isolation mirrors test_power_rankings.py's route tests: Flask test client,
injected session, patched load_draft_picks, no network/DB.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend.pick_values import (GENERIC_PICK_SEEDS, market_pick_slot_value,
                                 pick_pool_value, priced_pool_value)
from backend.trade_service import value_to_elo

LEAGUE = "league_picks_tier_test"
TOKEN = "sess-picks-tier-test"
FMT = "1qb_ppr"

# ── The prices this file pins, all re-derived from the pricing functions ───
# Step 2 (round curve) is what an unslotted read serves; the `client` fixture
# patches `is_enabled` to False, so `picks.slot_labels` is off, so
# `_league_slot_order` returns None and NOTHING resolves a slot. That is also
# the honest production answer for every future season (#273) and every
# league whose order we cannot resolve.
#
#   pick        stored ladder      priced (round curve)      badge
#   2026 1st         2117.0   →              1859.5   first_1  (unmoved)
#   2026 2nd          606.5   →               434.0   second  → third
#   2026 3rd          406.6   →               262.3   third   → fourth
#   2026 4th          272.5   →               233.9   fourth  → waivers
#   2027 2nd          515.6   →               389.7   third    (unmoved)
#   2027 3rd          345.6   →               254.5   third   → fourth
#   2029 1st         2117.0   →              1263.0   first_1 → second
_CURVE_2026_1 = 1859.5
_CURVE_2026_2 = 434.0
_CURVE_2026_3 = 262.3
_CURVE_2026_4 = 233.9
_CURVE_2027_2 = 389.7
_CURVE_2027_3 = 254.5
_CURVE_2029_1 = 1263.0

# Step 1 (the pick's OWN slot), 2026 round 1, 12-team linear board. The
# ruling's headline: one round, a 5.9x spread, two different badges.
_SLOT_2026_101 = 4867.1
_SLOT_2026_112 = 820.8

PICK_ROWS = [
    {"pick_id": f"{LEAGUE}_2026_1_1", "league_id": LEAGUE, "season": 2026,
     "round": 1, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice", "original_roster_id": "r1",
     "pool_value": pick_pool_value(1, 0)},
    {"pick_id": f"{LEAGUE}_2027_2_1", "league_id": LEAGUE, "season": 2027,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice", "original_roster_id": "r1",
     "pool_value": pick_pool_value(2, 1)},
    {"pick_id": f"{LEAGUE}_2026_3_1", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob", "original_roster_id": "r1",
     "pool_value": pick_pool_value(3, 0)},
    # Far-out 1st. On the ladder D-079 made this flat with a current-year
    # 1st; the market curve decays it (see the far-out test).
    {"pick_id": f"{LEAGUE}_2029_1_1", "league_id": LEAGUE, "season": 2029,
     "round": 1, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob", "original_roster_id": "r1",
     "pool_value": pick_pool_value(1, 3)},
    # A 2027 3rd — the band it lands in must still be REACHABLE from
    # somewhere, so "everything collapsed downward" fails here.
    {"pick_id": f"{LEAGUE}_2027_3_1", "league_id": LEAGUE, "season": 2027,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob", "original_roster_id": "r1",
     "pool_value": pick_pool_value(3, 1)},
    # A leaguemate-ASSERTED pick (W3 M-C `source: 'user'`) — prices, so it
    # tiers exactly like a platform row (sabotage S2 trap).
    {"pick_id": f"{LEAGUE}_2026_2_9", "league_id": LEAGUE, "season": 2026,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice", "source": "user",
     "original_roster_id": "r9", "pool_value": pick_pool_value(2, 0)},
    {"pick_id": f"{LEAGUE}_2026_4_2", "league_id": LEAGUE, "season": 2026,
     "round": 4, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob", "original_roster_id": "r2",
     "pool_value": pick_pool_value(4, 0)},
    # NULL pool_value (pre-pool_value-column row). D-147: this no longer
    # implies "no price" — the market can price a row the sync never did,
    # and the engine already does. See its own test.
    {"pick_id": f"{LEAGUE}_2026_4_1", "league_id": LEAGUE, "season": 2026,
     "round": 4, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob", "original_roster_id": "r1",
     "pool_value": None},
]

# A 12-team linear board — roster rN holds slot N in every round.
SLOT_ORDER = {"schema": 1, "season": 2026, "teams": 12, "type": "linear",
              "slots": {f"r{i}": i for i in range(1, 13)}}


def _mk_sess(user_id="u_a", fmt=FMT):
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
    """Flags OFF — no slot resolves, so every row rides the ROUND CURVE."""
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


@pytest.fixture()
def slotted_client():
    """`picks.slot_labels` ON with a resolvable 12-team order — the state
    that makes step 1 of the waterfall reachable through the route."""
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._slot_order_lock:
        server._slot_order_cache.clear()
    with patch.object(server, "is_enabled",
                      lambda k: k == "picks.slot_labels"), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_draft_slot_order", lambda lid: SLOT_ORDER), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw:
                      [dict(p) for p in PICK_ROWS]
                      if league_id == LEAGUE else []):
        try:
            yield c
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._slot_order_lock:
                server._slot_order_cache.clear()


def _install_sess(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _get(c, path):
    r = c.get(path, headers={"X-Session-Token": TOKEN})
    return r.status_code, json.loads(r.data)


def _picks_by_id(body):
    return {p["pick_id"]: p for p in body["all_picks"]}


def _fetch(c):
    _install_sess(_mk_sess())
    code, body = _get(c, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    return _picks_by_id(body)


# ═══════════════════════════════════════════════════════════════════════════
# D-147 — the route serves the ENGINE's price, and badges follow it
# ═══════════════════════════════════════════════════════════════════════════

def test_served_value_is_the_engine_price_not_the_stored_ladder(client):
    """Q-026's closure, asserted as a NUMBER before any badge is read.

    Sabotage S3 (`{**p}` leaving the stored column on the wire — literally
    the pre-D-147 line) fails every assertion here."""
    rows = _fetch(client)
    served = {pid: r["pool_value"] for pid, r in rows.items()}
    assert served[f"{LEAGUE}_2026_1_1"] == _CURVE_2026_1
    assert served[f"{LEAGUE}_2026_2_9"] == _CURVE_2026_2
    assert served[f"{LEAGUE}_2026_3_1"] == _CURVE_2026_3
    assert served[f"{LEAGUE}_2026_4_2"] == _CURVE_2026_4
    assert served[f"{LEAGUE}_2027_2_1"] == _CURVE_2027_2
    assert served[f"{LEAGUE}_2029_1_1"] == _CURVE_2029_1
    # …and none of them is the stored rung it used to be.
    for pid, stored_rung in [(f"{LEAGUE}_2026_1_1", 2117.0),
                             (f"{LEAGUE}_2026_2_9", 606.5),
                             (f"{LEAGUE}_2026_3_1", 406.6),
                             (f"{LEAGUE}_2026_4_2", 272.5)]:
        assert served[pid] != stored_rung, pid


def test_the_route_agrees_with_priced_pool_value_row_for_row(client):
    """The route is not allowed to have its OWN pricing opinion: every served
    number must be exactly what `pick_values.priced_pool_value` returns for
    the same row. This is the invariant the literals above are instances of —
    both are asserted, so neither a drifted literal nor a drifted route can
    pass alone."""
    rows = _fetch(client)
    for p in PICK_ROWS:
        expected = priced_pool_value(dict(p), scoring_format=FMT, slot=None)
        served = rows[p["pick_id"]]["pool_value"]
        assert served == (round(expected, 1) if expected > 0 else None), \
            p["pick_id"]


def test_slotted_first_badges_above_a_slotted_twelfth(slotted_client):
    """THE OPERATOR'S HEADLINE (Q-026 ruling, D-147 §2).

    Same round, same season, same stored rung (2117.0) — and now a 5.9x
    price spread and two different badges, on the list screen, matching what
    a trade card charges. Under the pre-D-147 code both rows read 2117.0 and
    both badged 'first_1'."""
    _install_sess(_mk_sess())
    code, body = _get(slotted_client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    rows = _picks_by_id(body)
    first = rows[f"{LEAGUE}_2026_1_1"]      # roster r1 → slot 1
    assert first["pool_value"] == _SLOT_2026_101
    assert first["tier"] == "firsts_2"
    assert first["label"] == "2026 1.01"     # price and label, one resolution
    # The 1.12 of the same round, via the asserted round-2 row's roster? No —
    # use the round-1 row's own slot, and pin the twelfth from the pricing
    # function so the spread is stated as a fact about the curve.
    assert market_pick_slot_value(2026, 1, 12, FMT) == _SLOT_2026_112
    assert server.RankingService.tier_for_elo(
        value_to_elo(_SLOT_2026_112), None, FMT) == "second"
    assert first["pool_value"] / _SLOT_2026_112 > 5.0


def test_slot_resolution_moves_price_and_label_together(slotted_client):
    """The 2026 2nd asserted to roster r9 prices at 2.09 and is LABELLED
    2.09. One `slot_for` result drives both, so the list can never say
    "2026 2.09" while charging for a generic second."""
    _install_sess(_mk_sess())
    code, body = _get(slotted_client, f"/api/league/picks?league_id={LEAGUE}")
    assert code == 200
    row = _picks_by_id(body)[f"{LEAGUE}_2026_2_9"]
    assert row["label"] == "2026 2.09"
    assert row["pool_value"] == market_pick_slot_value(2026, 2, 9, FMT)
    # …and a FUTURE season keeps its generic label AND its round-curve price,
    # because #273 refuses to invent next year's order.
    future = _picks_by_id(body)[f"{LEAGUE}_2027_2_1"]
    assert future["label"] == "2027 2nd"
    assert future["pool_value"] == _CURVE_2027_2


def test_pick_rows_carry_literal_tier_rungs(client):
    rows = _fetch(client)
    # Sabotage S1 "wrong scale" turns these into 'firsts_2' / None / None;
    # S1b "wrong inverse" reads them one band too rich.
    assert rows[f"{LEAGUE}_2026_1_1"]["tier"] == "first_1"
    assert rows[f"{LEAGUE}_2026_3_1"]["tier"] == "fourth"     # S1b: 'third'
    assert rows[f"{LEAGUE}_2027_3_1"]["tier"] == "fourth"     # S1b: 'third'
    assert rows[f"{LEAGUE}_2027_2_1"]["tier"] == "third"      # S1b: 'second'
    assert rows[f"{LEAGUE}_2026_4_2"]["tier"] == "waivers"    # S1b: 'third'


def test_far_out_pick_tier_is_the_discounted_band(client):
    """D-320-2's RULE is unchanged — the badge reflects TODAY's value, not
    the pick's name.

    D-147 changed the VALUE it reflects, and reversed D-079's most visible
    consequence at this surface: a 2029 1st is no longer FLAT with a
    current-year 1st. Flat firsts are a property of the stored LADDER, which
    is now only step 3 of the waterfall; DP's curve decays a first across
    seasons, so 2117.0 → 1263.0 and the honest badge is 'second'.

    A round that moves differently is asserted alongside it, so "someone
    flattened every season" fails here rather than shipping."""
    rows = _fetch(client)
    row = rows[f"{LEAGUE}_2029_1_1"]
    assert row["round"] == 1
    assert row["pool_value"] == _CURVE_2029_1
    assert row["tier"] == "second"
    # …and it matches the canonical walk over the inverted value map (the S1
    # "wrong scale" trap: unscaled, 1263.0 would read as Elo 1263 → 'fourth').
    assert row["tier"] == server.RankingService.tier_for_elo(
        value_to_elo(float(row["pool_value"])), None, FMT)
    # The far-out 1st is now worth strictly LESS than a current-year 1st…
    assert float(row["pool_value"]) < float(
        rows[f"{LEAGUE}_2026_1_1"]["pool_value"])
    # …while the STORED column both rows came from still holds them equal,
    # which is precisely what makes this a pricing change and not a data one.
    assert pick_pool_value(1, 3) == pick_pool_value(1, 0)
    # …and a future 2nd is still worth strictly less than a current one.
    assert float(rows[f"{LEAGUE}_2027_2_1"]["pool_value"]) < float(
        rows[f"{LEAGUE}_2026_2_9"]["pool_value"])


def test_asserted_user_source_pick_carries_tier_too(client):
    """Sabotage S2 "platform-only tiers": a `source: 'user'` row prices, so
    it tiers — skipping it fails here. (The provenance MARKER is a separate,
    flag-gated concern; the tier is not.)"""
    assert _fetch(client)[f"{LEAGUE}_2026_2_9"]["tier"] == "third"


def test_stored_null_now_prices_from_the_market_like_the_engine_does(client):
    """D-147 re-anchored the null contract, deliberately.

    A NULL `pool_value` used to mean "no price, no badge". It never meant
    that to anyone else: `_power_picks_by_owner` re-derives a price from a
    NULL, and `priced_pool_value` prices the row off the market regardless of
    what the sync stored. Serving null HERE while the engine charged for the
    same row is exactly the disagreement Q-026 closed, so the row now prices
    — at the identical number its non-null twin gets, since the stored column
    is only step 3."""
    rows = _fetch(client)
    null_row = rows[f"{LEAGUE}_2026_4_1"]      # stored NULL
    twin = rows[f"{LEAGUE}_2026_4_2"]          # same season+round, stored 272.5
    assert null_row["pool_value"] == _CURVE_2026_4 == twin["pool_value"]
    assert null_row["tier"] == twin["tier"] == "waivers"


def test_unpriceable_row_still_serves_null_rather_than_a_fake_zero(client):
    """The null contract that SURVIVES: when every step of the waterfall is
    empty — DP unreachable (`load_pick_slot_values` fail-softs to `{}`) and
    no stored value — there is nothing honest to say, so `pool_value` is
    null and the badge is null. Never 0.0, which would render as "this pick
    is worthless" on every client."""
    row = {"pick_id": f"{LEAGUE}_2026_4_1", "league_id": LEAGUE,
           "season": 2026, "round": 4, "owner_user_id": "u_b",
           "owner_username": "bob", "is_traded": 0, "original_username": "bob",
           "pool_value": None}
    with patch("backend.data_loader.load_pick_slot_values", lambda *a, **k: {}), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw: [dict(row)]):
        served = _fetch(client)[f"{LEAGUE}_2026_4_1"]
    assert served["pool_value"] is None
    assert served["tier"] is None


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


def test_the_d088_inverse_identity_is_still_the_one_this_route_uses(client):
    """D-088 — THE INVARIANT, restated where D-147 left it.

    `tier_config.json`'s `_calibration` defines each band's floor AS a rung of
    `GENERIC_PICK_SEEDS` ("third floor = Late 3rd seed 1280"), which is only
    coherent if the seeds live on the tier-band Elo scale. The identity that
    pins it — `value_to_elo(pick_pool_value(R, 0)) == GENERIC_PICK_SEEDS[(R,
    'Mid')]` — is a property of the LADDER, and D-147 did not touch it: the
    ladder is still step 3, and `value_to_elo` is still the exact inverse of
    the units every step of the waterfall returns.

    What D-147 changed is which number goes IN. So this asserts both halves,
    separately, because only the pair excludes both defects:

      1. the ladder identity itself, for all four rounds; and
      2. the route badging the SERVED value through that same inverse.

    Any inverse other than `value_to_elo` breaks at least one round:
      * `seed_elo_for_value` (the #320 defect) → the 2026 2nd reads 'second'
        instead of 'third' and the 2026 4th 'third' instead of 'waivers'
      * no inversion at all (the #263 defect) → the 2026 1st reads 'firsts_2'
        and everything cheaper reads None
    """
    # (1) the ladder identity — unchanged by D-147.
    for rnd in (1, 2, 3, 4):
        assert abs(value_to_elo(pick_pool_value(rnd, 0))
                   - GENERIC_PICK_SEEDS[(rnd, "Mid")]) < 0.05
    # (2) the route walks the SERVED value through that inverse, every row.
    rows = _fetch(client)
    for pid, row in rows.items():
        v = row["pool_value"]
        expected = (None if v is None else server.RankingService.tier_for_elo(
            value_to_elo(float(v)), None, FMT))
        assert row["tier"] == expected, pid
    # Named literals, so "all four collapsed to one tier" fails here.
    assert rows[f"{LEAGUE}_2026_1_1"]["tier"] == "first_1"
    assert rows[f"{LEAGUE}_2026_2_9"]["tier"] == "third"
    assert rows[f"{LEAGUE}_2026_3_1"]["tier"] == "fourth"
    assert rows[f"{LEAGUE}_2026_4_2"]["tier"] == "waivers"


def test_deep_far_out_pick_tiers_null_rather_than_flattering_it(client):
    """A pick priced BELOW the `waivers` floor (Elo 1150) gets no badge at
    all — the documented null-tier contract — never a fabricated `fourth`.

    Re-derived for D-147: the 2029 4th that used to sit below the floor now
    prices at 195.2 (Elo 1173.3) and honestly badges 'waivers', so the case
    is pinned one year deeper, at a 2030 4th (166.0 → Elo 1140.8). The
    PRICE is still served — only the badge is withheld."""
    deep = {"pick_id": f"{LEAGUE}_2030_4_1", "league_id": LEAGUE,
            "season": 2030, "round": 4, "owner_user_id": "u_b",
            "owner_username": "bob", "is_traded": 0,
            "original_username": "bob", "pool_value": pick_pool_value(4, 4)}
    with patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw: [dict(deep)]):
        row = _fetch(client)[f"{LEAGUE}_2030_4_1"]
    assert row["pool_value"] == 166.0
    assert value_to_elo(float(row["pool_value"])) < 1150.0
    assert row["tier"] is None
