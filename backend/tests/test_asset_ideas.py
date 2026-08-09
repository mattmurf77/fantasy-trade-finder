"""#172/#189 follow-up — asset-centric Upgrade / Lateral / Downgrade ideas
(flag trade.asset_ideas).

TradeService.generate_asset_ideas: for ONE pinned asset, sweep counterparty
rosters and group candidate deals around the pin's CONSENSUS value:

  upgrade   — counterpart above the ±asset_ideas_lateral_band band; straight
              1-for-1 when it passes the gates, else pin + own-roster
              sweetener (give dir) / package of lesser own assets (receive dir)
  lateral   — 1-for-1 within the band
  downgrade — 2-3 lesser pieces packaged back (give dir) / pin + owner
              sweetener(s) for a single better own asset (receive dir)

#198 — semantics are POSITION-CENTRIC for player pins: Upgrade and Lateral
counterparts must play the pin's position (never relaxed); Downgrade stays
value-based but orders same-position headliners first. PICK pins keep pure
value bands.

Gates are the consensus-basis reuse set (package_value_v2, fairness ratio,
#108 user-gain, #141 filler, consolidation raw-loss). A group that would be
EMPTY refills from the widened #189 band, labeled relaxed=True +
relaxed_reason="fairness_band". Groups are capped (asset_ideas_group_cap)
and ordered by |difference|; output is deterministic.

Route: POST /api/trades/asset-ideas — 404 when the flag is off.

Elo→value refresher (defaults): value = 1000 * exp(0.005 * (elo - 1500)).
"""
import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)   # all off — crown premium too
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        # #214/#215 — these tests were authored against (and pin) the
        # PRE-#214 engine math, which is now the reachable 'heavy'
        # stud-tax mode ('market' is the retuned default). Pinning the
        # mode here keeps them as the heavy-path byte-identity guard;
        # market-mode shapes are covered by test_stud_tax_modes.py.
        with ts.stud_tax_override("heavy"):
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
        self.years_experience = 3
        self.search_rank = search_rank
        self.pick_value = None


# ── Give-direction fixture ────────────────────────────────────────────────
# Pin P (elo 1560, v≈1349.9; band ±10% → [1214.9, 1484.8]).
# Opponent assets: U 1700 (v≈2718, upgrade), L 1570 (v≈1419, lateral),
#   L2 1550 (v≈1284 — in band but BELOW the pin → #108 excludes it),
#   D1 1520 (v≈1105) + D2 1500 (v=1000) — downgrade pieces.
# User roster: P + sweetener S1 1610 (v≈1732 — makes the 2-for-1 upgrade
# pass fairness AND the consolidation raw-loss cap).
GIVE_ELO = {"P": 1560.0, "S1": 1610.0, "U": 1700.0, "L": 1570.0,
            "L2": 1550.0, "D1": 1520.0, "D2": 1500.0}


def _give_service():
    players = {pid: _Player(pid) for pid in GIVE_ELO}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L", "L2", "D1", "D2"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc


def _give_ideas(svc=None, **kw):
    svc = svc or _give_service()
    kw.setdefault("fairness_threshold", 0.50)
    return svc.generate_asset_ideas(
        user_id="user",
        user_roster=["P", "S1"],
        league_id="L1",
        seed_elo=dict(GIVE_ELO),
        asset_id="P",
        direction="give",
        raw_user_elo=dict(GIVE_ELO),
        **kw,
    )


def test_give_direction_grouping_bands():
    groups = _give_ideas()
    # Upgrade: U comes back; the straight 1-for-1 can't pass fairness, so
    # the sweetened 2-for-1 (P + S1) is the emitted variant.
    assert len(groups["upgrade"]) == 1
    up = groups["upgrade"][0]
    assert up["receive_player_ids"] == ["U"]
    assert sorted(up["give_player_ids"]) == ["P", "S1"]
    assert up["counterparty_user_id"] == "opp"
    assert up["difference"] == round(up["receive_value"] - up["give_value"], 1)
    # Lateral: exactly the in-band 1-for-1 that clears #108 (L, not L2).
    assert [i["receive_player_ids"] for i in groups["lateral"]] == [["L"]]
    assert groups["lateral"][0]["give_player_ids"] == ["P"]
    assert groups["lateral"][0]["difference"] > 0
    # Downgrade: P out, 2-piece package back.
    assert len(groups["downgrade"]) == 1
    down = groups["downgrade"][0]
    assert down["give_player_ids"] == ["P"]
    assert sorted(down["receive_player_ids"]) == ["D1", "D2"]
    # No idea is labeled relaxed at the 0.50 wide net.
    for g in groups.values():
        for idea in g:
            assert "relaxed" not in idea


def test_user_gain_gate_excludes_below_pin_lateral():
    """L2 sits inside the band but below the pin's value — the #108
    consensus-delta gate (receive − give ≥ ε) keeps it out everywhere."""
    groups = _give_ideas()
    for g in groups.values():
        for idea in g:
            assert "L2" not in idea["receive_player_ids"]


def test_exclusions_respected():
    # not-interested: U never enters the receive pool → no upgrade ideas
    # (the 1-for-1 is hard-gated by fairness, nothing to relax into).
    groups = _give_ideas(not_interested_ids={"U"})
    assert groups["upgrade"] == []
    assert groups["lateral"]            # unrelated groups unaffected
    # untouchable sweetener: never leaves the roster → upgrade dries up.
    groups = _give_ideas(untouchable_ids={"S1"})
    assert groups["upgrade"] == []
    for g in groups.values():
        for idea in g:
            assert "S1" not in idea["give_player_ids"]
    # untouchable PIN in give direction: nothing is ever offered.
    groups = _give_ideas(untouchable_ids={"P"})
    assert groups == {"upgrade": [], "lateral": [], "downgrade": []}


def test_relaxed_refill_labels_only_empty_groups():
    """At a strict 0.75 threshold the sweetened upgrade (fairness ≈0.59)
    falls out of the strict band; the group refills from the widened #189
    band (relaxed_fairness_threshold 0.55) with honest labels. Groups that
    still pass strictly (lateral ≈0.89, downgrade ≈0.87) stay unlabeled."""
    groups = _give_ideas(fairness_threshold=0.75)
    assert len(groups["upgrade"]) == 1
    up = groups["upgrade"][0]
    assert up["relaxed"] is True
    assert up["relaxed_reason"] == "fairness_band"
    assert up["fairness"] < 0.75
    for group in ("lateral", "downgrade"):
        assert groups[group], f"{group} should still pass strictly"
        for idea in groups[group]:
            assert "relaxed" not in idea


def test_group_cap_and_ordering():
    """11 lateral candidates → capped at asset_ideas_group_cap (6), ordered
    by |difference| ascending (closest deals first)."""
    elos = {"P": 1560.0}
    lat_ids = []
    for i in range(11):
        pid = f"LAT{i}"
        lat_ids.append(pid)
        elos[pid] = 1562.0 + 2.0 * i          # all in band, all above the pin
    players = {pid: _Player(pid) for pid in elos}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=lat_ids, elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["P"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    groups = svc.generate_asset_ideas(**kw)
    assert len(groups["lateral"]) == int(ts._DEFAULT_CFG["asset_ideas_group_cap"])
    diffs = [abs(i["difference"]) for i in groups["lateral"]]
    assert diffs == sorted(diffs)
    # Closest candidate leads the group.
    assert groups["lateral"][0]["receive_player_ids"] == ["LAT0"]
    # Determinism: an identical second run returns an identical structure.
    assert svc.generate_asset_ideas(**kw) == groups


def test_give_ideas_deterministic():
    assert _give_ideas() == _give_ideas()


# ── #198 — position-centric semantics ─────────────────────────────────────

def _cross_pos_service():
    """The operator's complaint case: the opponent holds a HIGHER-VALUE WR
    (XW 1705 > U 1700) and an in-band WR (WL 1570) alongside the RB assets.
    Pure value bands would classify both as Upgrade/Lateral for the RB pin."""
    elos = {**GIVE_ELO, "XW": 1705.0, "WL": 1570.0}
    players = {pid: _Player(pid) for pid in GIVE_ELO}
    players["XW"] = _Player("XW", position="WR")
    players["WL"] = _Player("WL", position="WR")
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L", "L2", "D1", "D2", "XW", "WL"],
                       elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, elos


def test_upgrade_and_lateral_are_position_locked():
    """#198 — the pinned RB's Upgrade group returns better RBs only, and the
    Lateral group same-position swaps only; the higher-value WR never
    surfaces as an 'upgrade' (the operator's complaint case)."""
    svc, elos = _cross_pos_service()
    groups = svc.generate_asset_ideas(
        user_id="user", user_roster=["P", "S1"], league_id="L1",
        seed_elo=dict(elos), asset_id="P", direction="give",
        fairness_threshold=0.50, raw_user_elo=dict(elos))
    assert [i["receive_player_ids"] for i in groups["upgrade"]] == [["U"]]
    assert [i["receive_player_ids"] for i in groups["lateral"]] == [["L"]]
    for g in groups.values():
        for idea in g:
            assert "XW" not in idea["receive_player_ids"]
            assert "WL" not in idea["receive_player_ids"]


def test_downgrade_prefers_same_position_headliner():
    """#198 — Downgrade stays value-based (cross-position pieces allowed) but
    combos headlined by the pin's position order first, even when a
    cross-position headliner lands a closer deal."""
    # Pieces (all below the band): DA is the only RB; the WR pair (WA+WB)
    # sums to the CLOSEST deal that still clears the #108 gate, so pure
    # |difference| ordering would lead with the WR-headlined combo.
    elos = {"P": 1560.0, "DA": 1524.0, "WA": 1510.0, "WB": 1508.0}
    players = {
        "P":  _Player("P"),                     # RB pin
        "DA": _Player("DA"),                    # RB
        "WA": _Player("WA", position="WR"),
        "WB": _Player("WB", position="WR"),
    }
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["DA", "WA", "WB"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    groups = svc.generate_asset_ideas(
        user_id="user", user_roster=["P"], league_id="L1",
        seed_elo=dict(elos), asset_id="P", direction="give",
        fairness_threshold=0.50, raw_user_elo=dict(elos))
    down = groups["downgrade"]
    assert down, "expected downgrade packages"
    # The leading combo is headlined by the RB.
    assert down[0]["receive_player_ids"][0] == "DA"
    # Preference did real work: the WR-headlined combo exists with a SMALLER
    # |difference| — pure closeness ordering would have led with it.
    wr_headed = [i for i in down if i["receive_player_ids"][0] == "WA"]
    assert wr_headed
    assert abs(wr_headed[0]["difference"]) < abs(down[0]["difference"])


def test_pick_pin_keeps_value_bands():
    """#198 — a PICK pin has no position to upgrade: groups keep the pure
    value-band semantics (any better asset is an upgrade target)."""
    elos = {"PK": 1560.0, "S1": 1610.0, "U": 1700.0, "L": 1570.0}
    players = {
        "PK": _Player("PK", position="PICK"),
        "S1": _Player("S1"),
        "U":  _Player("U", position="WR"),      # cross-"position" on purpose
        "L":  _Player("L", position="QB"),
    }
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    groups = svc.generate_asset_ideas(
        user_id="user", user_roster=["PK", "S1"], league_id="L1",
        seed_elo=dict(elos), asset_id="PK", direction="give",
        fairness_threshold=0.50, raw_user_elo=dict(elos))
    assert [i["receive_player_ids"] for i in groups["upgrade"]] == [["U"]]
    assert [i["receive_player_ids"] for i in groups["lateral"]] == [["L"]]


# ── Receive-direction fixture ─────────────────────────────────────────────
# Pin T (elo 1700, v≈2718; band → [2446, 2990]) on opp2's roster (which also
# holds extra E 1650, v≈2117). User roster: G_up 1650 (v≈2117, below band —
# upgrade headliner), G2 1500 (v=1000, pairs with G_up), G_lat 1690 (v≈2586,
# in band), G_down 1720 (v≈3004, above band — downgrade give).
RECV_ELO = {"T": 1700.0, "E": 1650.0, "G_up": 1650.0, "G2": 1500.0,
            "G_lat": 1690.0, "G_down": 1720.0}


def _recv_service():
    players = {pid: _Player(pid) for pid in RECV_ELO}
    owner = LeagueMember(user_id="opp2", username="Owner",
                         roster=["T", "E"], elo_ratings={})
    other = LeagueMember(user_id="opp3", username="Other",
                         roster=[], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner, other]))
    return svc


def _recv_ideas(svc=None, **kw):
    svc = svc or _recv_service()
    kw.setdefault("fairness_threshold", 0.50)
    return svc.generate_asset_ideas(
        user_id="user",
        user_roster=["G_up", "G2", "G_lat", "G_down"],
        league_id="L1",
        seed_elo=dict(RECV_ELO),
        asset_id="T",
        direction="receive",
        raw_user_elo=dict(RECV_ELO),
        **kw,
    )


def test_receive_direction_mirrors_grouping():
    groups = _recv_ideas()
    # Every idea's counterparty is the pin's OWNER, and the pin is always
    # on the receive side (ideas are what the user GIVES).
    for g in groups.values():
        for idea in g:
            assert idea["counterparty_user_id"] == "opp2"
            assert "T" in idea["receive_player_ids"]
    # Upgrade: tier up INTO the pin — a package of lesser own assets
    # (the G_up + G2 pair lands closer than the bare 1-for-1).
    assert len(groups["upgrade"]) == 1
    up = groups["upgrade"][0]
    assert up["receive_player_ids"] == ["T"]
    assert sorted(up["give_player_ids"]) == ["G2", "G_up"]
    assert up["difference"] > 0
    # Lateral: the in-band own asset swaps straight across.
    assert [i["give_player_ids"] for i in groups["lateral"]] == [["G_lat"]]
    # Downgrade: single better own asset out, pin + owner sweetener back.
    assert len(groups["downgrade"]) == 1
    down = groups["downgrade"][0]
    assert down["give_player_ids"] == ["G_down"]
    assert sorted(down["receive_player_ids"]) == ["E", "T"]


def test_receive_direction_exclusions():
    # A not-interested PIN is never proposed at all.
    groups = _recv_ideas(not_interested_ids={"T"})
    assert groups == {"upgrade": [], "lateral": [], "downgrade": []}
    # A not-interested owner sweetener never pads the downgrade return.
    groups = _recv_ideas(not_interested_ids={"E"})
    assert groups["downgrade"] == []
    # Untouchable own assets never appear on the give side.
    groups = _recv_ideas(untouchable_ids={"G_lat"})
    assert groups["lateral"] == []
    for g in groups.values():
        for idea in g:
            assert "G_lat" not in idea["give_player_ids"]


def test_receive_ideas_deterministic():
    assert _recv_ideas() == _recv_ideas()


def test_receive_direction_position_locked():
    """#198 mirror — acquiring an RB pin: the tier-up headliner and the
    lateral swap must be the user's own RBs; equally-valued WRs never
    headline either group (the second tier-up piece may be any position)."""
    elos = {**RECV_ELO, "WU": 1650.0, "WLat": 1690.0}
    players = {pid: _Player(pid) for pid in RECV_ELO}
    players["WU"] = _Player("WU", position="WR")     # value-twin of G_up
    players["WLat"] = _Player("WLat", position="WR")  # value-twin of G_lat
    owner = LeagueMember(user_id="opp2", username="Owner",
                         roster=["T", "E"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner]))
    groups = svc.generate_asset_ideas(
        user_id="user",
        user_roster=["G_up", "G2", "G_lat", "G_down", "WU", "WLat"],
        league_id="L1", seed_elo=dict(elos), asset_id="T",
        direction="receive", fairness_threshold=0.50,
        raw_user_elo=dict(elos))
    for idea in groups["upgrade"]:
        assert idea["give_player_ids"][0] not in ("WU", "WLat")
    assert [i["give_player_ids"] for i in groups["lateral"]] == [["G_lat"]]


# ── #250 — Specific-Team scope (opponent_user_id) ─────────────────────────

def _two_opponent_service():
    """The give fixture's opponent plus a SECOND league-mate holding a
    value-twin roster — unscoped sweeps return ideas from both."""
    players = {pid: _Player(pid) for pid in GIVE_ELO}
    for pid in ("U9", "L9", "D19", "D29"):
        players[pid] = _Player(pid)
    elos = {**GIVE_ELO, "U9": 1700.0, "L9": 1570.0,
            "D19": 1520.0, "D29": 1500.0}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L", "L2", "D1", "D2"], elo_ratings={})
    opp9 = LeagueMember(user_id="opp9", username="OtherTeam",
                        roster=["U9", "L9", "D19", "D29"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp, opp9]))
    return svc, elos


def test_give_direction_scoped_to_opponent():
    """#250 — with opponent_user_id set, every idea's counterparty is that
    member and no other team's players appear on the receive side."""
    svc, elos = _two_opponent_service()
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    # Sanity: unscoped sweep sees both teams.
    unscoped = svc.generate_asset_ideas(**kw)
    parties = {i["counterparty_user_id"]
               for g in unscoped.values() for i in g}
    assert parties == {"opp", "opp9"}
    # Scoped sweep: only the targeted team, only its players coming back.
    scoped = svc.generate_asset_ideas(**kw, opponent_user_id="opp9")
    ideas = [i for g in scoped.values() for i in g]
    assert ideas, "scoped sweep should still find ideas on the target team"
    opp9_roster = {"U9", "L9", "D19", "D29"}
    for idea in ideas:
        assert idea["counterparty_user_id"] == "opp9"
        assert set(idea["receive_player_ids"]) <= opp9_roster


def test_receive_direction_scope_mismatch_returns_empty():
    """#250 — acquiring a pin owned by someone OTHER than the scoped
    opponent yields no ideas (never off-team acquire options); a matching
    scope returns the normal groups."""
    svc = _recv_service()          # pin T is owned by opp2
    empty = {"upgrade": [], "lateral": [], "downgrade": []}
    assert _recv_ideas(svc, opponent_user_id="opp3") == empty
    assert _recv_ideas(_recv_service(), opponent_user_id="opp2") == _recv_ideas()


def test_unknown_asset_or_direction_returns_empty():
    svc = _give_service()
    empty = {"upgrade": [], "lateral": [], "downgrade": []}
    assert svc.generate_asset_ideas(
        user_id="user", user_roster=["P", "S1"], league_id="L1",
        seed_elo=dict(GIVE_ELO), asset_id="nope", direction="give") == empty
    assert svc.generate_asset_ideas(
        user_id="user", user_roster=["P", "S1"], league_id="L1",
        seed_elo=dict(GIVE_ELO), asset_id="P", direction="sideways") == empty
    # Give-direction pin must actually be on the user's roster.
    assert svc.generate_asset_ideas(
        user_id="user", user_roster=["S1"], league_id="L1",
        seed_elo=dict(GIVE_ELO), asset_id="P", direction="give") == empty


# ── Route: POST /api/trades/asset-ideas ──────────────────────────────────

TOKEN = "sess-asset-ideas-tok"


class _FakeRankSet(SimpleNamespace):
    pass


class _FakeService:
    def __init__(self, elo_map):
        self._seed = dict(elo_map)
        self._rank_rows = [
            SimpleNamespace(player=SimpleNamespace(id=pid), elo=e)
            for pid, e in elo_map.items()
        ]

    def get_rankings(self, position=None):
        return _FakeRankSet(rankings=self._rank_rows)


@pytest.fixture()
def route_client():
    import backend.server as server
    svc = _give_service()
    players = list(svc._players.values())
    sess = {
        "user_id":       "user",
        "league":        svc._leagues["L1"],
        "players":       players,
        "user_roster":   ["P", "S1"],
        "service":       _FakeService(GIVE_ELO),
        "trade_svc":     svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        with patch.object(server, "_verified_write_denial", lambda s: None):
            yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _post(c, body):
    return c.post("/api/trades/asset-ideas", json=body,
                  headers={"X-Session-Token": TOKEN})


def test_route_404_when_flag_off(route_client):
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)          # trade.asset_ideas off
    r = _post(route_client, {"asset_id": "P"})
    assert r.status_code == 404


def test_route_groups_shape(route_client):
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    r = _post(route_client, {"asset_id": "P", "direction": "give"})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["direction"] == "give"
    assert data["basis"] == "consensus"
    assert data["asset"]["id"] == "P"
    groups = data["groups"]
    assert set(groups) == {"upgrade", "lateral", "downgrade"}
    up = groups["upgrade"][0]
    # Serialized rows carry hydrated player dicts alongside the id lists.
    assert [p["id"] for p in up["receive"]] == up["receive_player_ids"] == ["U"]
    assert {p["id"] for p in up["give"]} == set(up["give_player_ids"]) == {"P", "S1"}
    assert up["counterparty_username"] == "OppTeam"
    assert isinstance(up["difference"], float)


def test_route_ideas_carry_value_verdict(route_client):
    """#216 — every serialized idea carries the pick-denominated verdict
    (favors + gap) in the same shape evaluate / deck cards use, so the
    featured-trade window's TradeValueBar renders from it directly."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    r = _post(route_client, {"asset_id": "P", "direction": "give"})
    assert r.status_code == 200, r.get_json()
    groups = r.get_json()["groups"]
    ideas = [i for g in groups.values() for i in g]
    assert ideas
    for idea in ideas:
        assert idea["favors"] in ("give", "receive", "even")
        gap = idea["gap"]
        assert gap["value"] == round(
            abs(idea["receive_value"] - idea["give_value"]), 1)
        assert isinstance(gap["firsts"], float)
        # favors agrees with the package values (even ⇔ fairness ≥ 0.95).
        if idea["fairness"] >= 0.95:
            assert idea["favors"] == "even"
        elif idea["receive_value"] > idea["give_value"]:
            assert idea["favors"] == "receive"
        else:
            assert idea["favors"] == "give"


def test_route_passes_opponent_scope(route_client):
    """#250 — body opponent_user_id threads through to the sweep: scoping
    the give fixture (single opponent 'opp') to a different user id yields
    empty groups; scoping to 'opp' matches the unscoped read."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    r = _post(route_client, {"asset_id": "P", "direction": "give",
                             "opponent_user_id": "someone_else"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["groups"] == {
        "upgrade": [], "lateral": [], "downgrade": []}
    r_scoped = _post(route_client, {"asset_id": "P", "direction": "give",
                                    "opponent_user_id": "opp"})
    r_plain = _post(route_client, {"asset_id": "P", "direction": "give"})
    assert r_scoped.get_json()["groups"] == r_plain.get_json()["groups"]


def test_route_validation(route_client):
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    assert _post(route_client, {}).status_code == 400
    assert _post(route_client,
                 {"asset_id": "P", "direction": "sideways"}).status_code == 400
    assert _post(route_client, {"asset_id": "zzz"}).status_code == 404


# ── #286 — balanced mix under the PRODUCTION-DEFAULT stud-tax mode ────────
#
# Every test above runs under the module's autouse `_isolate` fixture, which
# deliberately PINS stud_tax_override("heavy") — the pre-#214 legacy math
# these tests were authored against. Production defaults to 'market' mode
# (stud_tax_mode_for_user), and the two modes price multi-piece packages
# very differently: 'market' benchmarks a package's depth-discount against
# its OWN best asset (not a trade-wide max) and only grants a crown premium
# when a received single asset clears crown_elite_value (an ultra-elite
# absolute threshold, ~6000). The upshot: a lone sweetener is a blunt
# instrument — under 'market' math there is often a real gv window between
# "still underpaying" (fails the fairness floor) and "now overpaying"
# (fails the never-relaxed #108 gain gate at trade_service.py `_eval`) that
# no single available roster piece lands inside, even though the pin has
# genuine upgrade/tier-up candidates. The Downgrade branch already searches
# 2-3-piece combinations (`combinations(down, r)` for r in (2, 3)), so it
# reliably finds a passing package; the give-direction Upgrade branch and
# the receive-direction Tier-UP branch tried only ONE extra piece at a
# time, so they silently emptied out — the operator's "alt trade options
# are only trade down ideas" report. The fix widens both Upgrade branches
# to also search 2-sweetener combinations (bounded to the top _POOL, same
# breadth Downgrade already gets). These tests reproduce a pin whose
# candidate opponent asset is priced far enough above the pin that closing
# the fairness gap needs more than any single roster piece provides, but a
# pair of them clears it — asserting the returned mix is genuinely
# balanced (all three classes populated) rather than skewed to Downgrade.
def _v_for_elo(elo: float) -> float:
    return 1000.0 * math.exp(0.005 * (elo - 1500.0))


def _elo_for_value(value: float) -> float:
    return 1500.0 + math.log(value / 1000.0) / 0.005


def test_give_direction_balanced_mix_under_market_mode():
    """#286 — direction='give', production-default 'market' stud-tax mode.
    The pin (P, v≈1000) has a same-position upgrade target (C, v=3000) far
    outside the lateral band; no single sweetener in the user's roster
    lands gv inside the [fairness floor, epsilon ceiling] window, but a
    pair of them does. Lateral (L) and Downgrade (D1/D2) candidates exist
    too — the returned mix must not collapse to Downgrade-only."""
    elos = {
        "P":  _elo_for_value(1000.0),   # the pin
        "C":  _elo_for_value(3000.0),   # opponent's upgrade target
        "L":  _elo_for_value(1050.0),   # opponent's in-band lateral swap
        "D1": _elo_for_value(700.0),    # opponent's downgrade pieces
        "D2": _elo_for_value(650.0),
    }
    sweeteners = [f"S{i}" for i in range(1, 5)]
    for s in sweeteners:
        # Each alone (P + one) undershoots the fairness floor against C;
        # each individually clears the #141 filler floor (asset_floor_abs).
        elos[s] = _elo_for_value(470.0)

    players = {pid: _Player(pid) for pid in elos}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["C", "L", "D1", "D2"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))

    with ts.stud_tax_override("market"):
        groups = svc.generate_asset_ideas(
            user_id="user",
            user_roster=["P"] + sweeteners,
            league_id="L1",
            seed_elo=elos,
            asset_id="P",
            direction="give",
            raw_user_elo=elos,
            fairness_threshold=0.50,
        )

    assert groups["upgrade"], "upgrade group must not be empty when a passing combo exists"
    assert groups["lateral"], "lateral group must not be empty"
    assert groups["downgrade"], "downgrade group must not be empty"
    up = groups["upgrade"][0]
    assert up["receive_player_ids"] == ["C"]
    # The winning package needed TWO sweeteners — a single one never clears
    # the window (see test_give_direction_upgrade_needs_paired_sweetener).
    assert len(up["give_player_ids"]) == 3
    assert "P" in up["give_player_ids"]


def test_give_direction_upgrade_needs_paired_sweetener():
    """Same fixture as above, isolating the single-sweetener search: no
    ONE available sweetener clears the window alone (regression guard for
    the #286 fix — proves the paired search is load-bearing, not a no-op)."""
    elos = {
        "P": _elo_for_value(1000.0),
        "C": _elo_for_value(3000.0),
    }
    for i in range(1, 5):
        elos[f"S{i}"] = _elo_for_value(470.0)
    players = {pid: _Player(pid) for pid in elos}
    opp = LeagueMember(user_id="opp", username="OppTeam", roster=["C"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))

    with ts.stud_tax_override("market"):
        for s in ("S1", "S2", "S3", "S4"):
            groups = svc.generate_asset_ideas(
                user_id="user", user_roster=["P", s], league_id="L1",
                seed_elo=elos, asset_id="P", direction="give",
                raw_user_elo=elos, fairness_threshold=0.50,
            )
            assert groups["upgrade"] == [], (
                f"single sweetener {s} should NOT alone clear the window")


def test_receive_direction_balanced_mix_under_market_mode():
    """#286 mirror — direction='receive'. The pin (PIN, v=3000) is owned by
    an opponent; the user's tier-up headliner (G, v≈1000) needs a paired
    sweetener to close the gap, same as the give-direction case. Lateral
    (LAT) and tier-down (GD + owner extras) candidates exist too."""
    elos = {
        "PIN": _elo_for_value(3000.0),
        "G":   _elo_for_value(1000.0),   # user's tier-up headliner
        "LAT": _elo_for_value(2950.0),   # user's in-band lateral asset
        "GD":  _elo_for_value(3600.0),   # user's tier-down asset
        "E1":  _elo_for_value(950.0),    # owner's tier-down sweeteners
        "E2":  _elo_for_value(900.0),
    }
    sweeteners = [f"S{i}" for i in range(1, 5)]
    for s in sweeteners:
        elos[s] = _elo_for_value(470.0)

    players = {pid: _Player(pid) for pid in elos}
    owner = LeagueMember(user_id="opp", username="OppTeam",
                         roster=["PIN", "E1", "E2"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner]))

    with ts.stud_tax_override("market"):
        groups = svc.generate_asset_ideas(
            user_id="user",
            user_roster=["G", "LAT", "GD"] + sweeteners,
            league_id="L1",
            seed_elo=elos,
            asset_id="PIN",
            direction="receive",
            raw_user_elo=elos,
            fairness_threshold=0.50,
        )

    assert groups["upgrade"], "upgrade group must not be empty when a passing combo exists"
    assert groups["lateral"], "lateral group must not be empty"
    assert groups["downgrade"], "downgrade group must not be empty"
    up = groups["upgrade"][0]
    assert up["receive_player_ids"] == ["PIN"]
    assert len(up["give_player_ids"]) == 3
    assert "G" in up["give_player_ids"]
