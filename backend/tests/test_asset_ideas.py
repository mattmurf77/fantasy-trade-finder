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


# ── #403 W2 — swap_positions (lateral-only predicate replacement) ─────────
#
# `swap_positions` REPLACES the #198 same-position predicate for the LATERAL
# group only; `upgrade` and `downgrade` are byte-identical under every value
# of the field, and absent/None/[] is byte-identical to today. Invalid tokens
# are a 400 at the route, never a silent drop.

def test_swap_positions_absent_is_identical():
    """Absent, None and [] all reproduce today's behavior exactly — asserted
    against the SAME expected shapes the pre-#403 tests pin, not fresh
    snapshots."""
    base = _give_ideas()
    assert _give_ideas(swap_positions=None) == base
    assert _give_ideas(swap_positions=[]) == base
    # The pre-#403 expected shapes still hold on the equal objects.
    assert [i["receive_player_ids"] for i in base["lateral"]] == [["L"]]
    assert [i["receive_player_ids"] for i in base["upgrade"]] == [["U"]]
    # Receive direction, same three-way identity.
    rbase = _recv_ideas()
    assert _recv_ideas(swap_positions=None) == rbase
    assert _recv_ideas(swap_positions=[]) == rbase
    assert [i["give_player_ids"] for i in rbase["lateral"]] == [["G_lat"]]


def test_swap_positions_present_changes_lateral():
    """RB pin + swap_positions=["WR"]: the in-band WR (WL) fills lateral and
    the pin's OWN position is excluded unless selected (replacement, not a
    filter). Selecting both returns both."""
    svc, elos = _cross_pos_service()
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    wr_only = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    assert [i["receive_player_ids"] for i in wr_only["lateral"]] == [["WL"]]
    both = svc.generate_asset_ideas(**kw, swap_positions=["RB", "WR"])
    got = {tuple(i["receive_player_ids"]) for i in both["lateral"]}
    assert got == {("L",), ("WL",)}
    # Selecting only the pin's own position ≡ the #198 default.
    rb_only = svc.generate_asset_ideas(**kw, swap_positions=["RB"])
    assert rb_only == svc.generate_asset_ideas(**kw)


def test_swap_positions_constrains_all_groups():
    """#402 rev-3 §2 (supersedes PRD R-11 / the W2 lateral-only rule),
    forked by QA-B F1 — ON A REV-3-SHAPED REQUEST (lateral_scope present)
    the position set constrains EVERY group's incoming headline piece.
    WR-only on the RB pin: the higher-value WR (XW) IS now the upgrade,
    the in-band WR (WL) the lateral, and the all-RB-headlined downgrade
    combos go honestly empty. Selecting both positions returns both
    upgrades; never-cross-contaminates: the band WR stays lateral-only
    and the above-band WR upgrade-only."""
    svc, elos = _cross_pos_service()
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos),
              lateral_scope="band")     # rev-3 request shape (QA-B F1)
    base = svc.generate_asset_ideas(**kw)
    wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    assert [i["receive_player_ids"] for i in wr["upgrade"]] == [["XW"]]
    assert [i["receive_player_ids"] for i in wr["lateral"]] == [["WL"]]
    assert wr["downgrade"] == []          # D1/D2 headliners are RB
    # Never-cross-contaminates: the filter is applied per group — the
    # band WR never leaks into upgrade, the above-band WR never into
    # lateral, and no RB survives anywhere under a WR-only selection.
    for group, ideas in wr.items():
        for idea in ideas:
            assert "WL" not in idea["receive_player_ids"] or group == "lateral"
            assert "XW" not in idea["receive_player_ids"] or group == "upgrade"
            for pid in idea["receive_player_ids"]:
                assert svc._players[pid].position == "WR"
    # Selecting both positions returns both upgrades alongside the base RB.
    both = svc.generate_asset_ideas(**kw, swap_positions=["RB", "WR"])
    up_heads = {i["receive_player_ids"][0] for i in both["upgrade"]}
    assert up_heads == {"U", "XW"}
    # Selecting only the pin's own position reproduces the base groups
    # (this fixture's downgrade headliners are all RB already).
    rb_only = svc.generate_asset_ideas(**kw, swap_positions=["RB"])
    assert rb_only == base


def test_old_shape_swap_positions_filters_lateral_only():
    """QA-B F1 (reviewer B finding 1, THE field-client blocker) — the
    shipped v1.16.9 client sends swap_positions WITHOUT lateral_scope from
    a picker whose UI promised Same-value-only. On that request shape the
    set filters the LATERAL group only: upgrade and downgrade are
    byte-identical to the unfiltered pinned shapes (U stays the upgrade,
    the RB-headlined downgrades stay), while the lateral group swaps to
    the selected position — exactly the v1.16.9 deploy's behavior.

    SABOTAGE (compat fork removed — _head_ok collapsed to _pos_ok /
    _swap_all_groups hardcoded True): upgrade becomes [["XW"]] and
    downgrade empties → RED."""
    svc, elos = _cross_pos_service()
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    base = svc.generate_asset_ideas(**kw)          # no swap, no scope
    old = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    # Lateral filters (that IS v1.16.9 behavior)…
    assert [i["receive_player_ids"] for i in old["lateral"]] == [["WL"]]
    # …upgrade/downgrade keep the pre-rev-3 pinned shapes byte-identical.
    assert old["upgrade"] == base["upgrade"]
    assert [i["receive_player_ids"] for i in base["upgrade"]] == [["U"]]
    assert old["downgrade"] == base["downgrade"]
    assert base["downgrade"]        # non-vacuous: RB-headlined combos exist
    # Receive-direction mirror of the same wire case.
    relos = {**RECV_ELO, "WU": 1650.0, "WLat": 1690.0}
    rplayers = {pid: _Player(pid) for pid in RECV_ELO}
    rplayers["WU"] = _Player("WU", position="WR")
    rplayers["WLat"] = _Player("WLat", position="WR")
    owner = LeagueMember(user_id="opp2", username="Owner",
                         roster=["T", "E"], elo_ratings={})
    rsvc = TradeService(players=rplayers)
    rsvc.add_league(League(league_id="L1", name="T", platform="demo",
                           members=[owner]))
    rkw = dict(user_id="user",
               user_roster=["G_up", "G2", "G_lat", "G_down", "WU", "WLat"],
               league_id="L1", seed_elo=dict(relos), asset_id="T",
               direction="receive", fairness_threshold=0.50,
               raw_user_elo=dict(relos))
    rbase = rsvc.generate_asset_ideas(**rkw)
    rold = rsvc.generate_asset_ideas(**rkw, swap_positions=["WR"])
    assert [i["give_player_ids"] for i in rold["lateral"]] == [["WLat"]]
    assert rold["upgrade"] == rbase["upgrade"]
    assert rold["downgrade"] == rbase["downgrade"]
    assert rbase["upgrade"] and rbase["downgrade"]     # non-vacuous


def test_swap_positions_receive_direction_mirror():
    """#402 rev-3 §2 mirror (rev-3 request shape, QA-B F1) — in the
    receive direction the position set constrains the user's variable
    GIVE piece in all three groups (the incoming pin is fixed): WR-only
    makes WU the tier-up headliner and WLat the lateral swap, and empties
    the RB-given downgrade."""
    elos = {**RECV_ELO, "WU": 1650.0, "WLat": 1690.0}
    players = {pid: _Player(pid) for pid in RECV_ELO}
    players["WU"] = _Player("WU", position="WR")
    players["WLat"] = _Player("WLat", position="WR")
    owner = LeagueMember(user_id="opp2", username="Owner",
                         roster=["T", "E"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner]))
    kw = dict(user_id="user",
              user_roster=["G_up", "G2", "G_lat", "G_down", "WU", "WLat"],
              league_id="L1", seed_elo=dict(elos), asset_id="T",
              direction="receive", fairness_threshold=0.50,
              raw_user_elo=dict(elos),
              lateral_scope="band")     # rev-3 request shape (QA-B F1)
    groups = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    assert [i["give_player_ids"] for i in groups["lateral"]] == [["WLat"]]
    # The tier-up headliner is now the selected-position own asset; the
    # RB value-twin (G_up) no longer headlines.
    assert groups["upgrade"]
    for idea in groups["upgrade"]:
        assert idea["give_player_ids"][0] == "WU"
    # The only above-band own asset (G_down) is RB → honest empty.
    assert groups["downgrade"] == []
    # Selecting the pin's own position reproduces the unfiltered groups
    # (this fixture's downgrade give is RB already).
    base = svc.generate_asset_ideas(**kw)
    assert svc.generate_asset_ideas(**kw, swap_positions=["RB"]) == base


def test_relaxed_refill_never_widens_positions():
    """The #189 refill widens the FAIRNESS band only, never the position
    set: at a strict 0.75 threshold the upgrade group refills relaxed —
    and with only the pin's own position selected it is still RB-only
    (the WR upgrade XW stays out; rev-3 §2 makes the set the constraint,
    the refill honors it)."""
    svc, elos = _cross_pos_service()
    groups = svc.generate_asset_ideas(
        user_id="user", user_roster=["P", "S1"], league_id="L1",
        seed_elo=dict(elos), asset_id="P", direction="give",
        fairness_threshold=0.75, raw_user_elo=dict(elos),
        swap_positions=["RB"],
        lateral_scope="band")     # rev-3 request shape (QA-B F1)
    assert [i["receive_player_ids"] for i in groups["upgrade"]] == [["U"]]
    assert groups["upgrade"][0]["relaxed"] is True
    for idea in groups["upgrade"]:
        assert "XW" not in idea["receive_player_ids"]


def test_avoided_position_beats_swap_selection():
    """#360 × #403 — an avoided position wins structurally (excluded at
    pool-build), producing an honest empty lateral, never a silent
    override."""
    svc, elos = _cross_pos_service()
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    with_wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    assert [i["receive_player_ids"] for i in with_wr["lateral"]] == [["WL"]]
    avoided = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                       avoid_positions=["WR"])
    assert avoided["lateral"] == []
    for g in avoided.values():
        for idea in g:
            assert "WL" not in idea["receive_player_ids"]
            assert "XW" not in idea["receive_player_ids"]


def test_swap_positions_ignored_for_pick_pin():
    """A PICK pin has pos_constrained False — pure value bands already —
    so swap_positions changes nothing."""
    elos = {"PK": 1560.0, "S1": 1610.0, "U": 1700.0, "L": 1570.0}
    players = {
        "PK": _Player("PK", position="PICK"),
        "S1": _Player("S1"),
        "U":  _Player("U", position="WR"),
        "L":  _Player("L", position="QB"),
    }
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["PK", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="PK", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    assert (svc.generate_asset_ideas(**kw, swap_positions=["WR"])
            == svc.generate_asset_ideas(**kw))


def test_swap_positions_filters_downgrade_headliner():
    """#402 rev-3 §2 (rev-3 request shape, QA-B F1) — the downgrade filter
    binds on the package's HEADLINE piece (top value), not every piece: a
    WR-headlined combo survives a WR-only selection even with an RB
    filler, and RB-headlined combos are dropped. On the OLD request shape
    (no lateral_scope) the same selection leaves downgrade untouched."""
    elos = {"P": 1560.0, "D1": 1520.0, "WD": 1510.0, "D2": 1500.0}
    players = {pid: _Player(pid) for pid in elos}
    players["WD"] = _Player("WD", position="WR")
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["D1", "WD", "D2"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["P"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    base = svc.generate_asset_ideas(**kw)
    base_heads = {i["receive_player_ids"][0] for i in base["downgrade"]}
    assert "D1" in base_heads          # absent = any-position headliners
    wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                  lateral_scope="band")
    assert wr["downgrade"]
    for idea in wr["downgrade"]:
        assert idea["receive_player_ids"][0] == "WD"
        # RB fillers behind a WR headliner are allowed — only the
        # headline piece is constrained.
    assert any("D2" in i["receive_player_ids"] for i in wr["downgrade"])
    # QA-B F1 — old shape: the selection never touches downgrade.
    old = svc.generate_asset_ideas(**kw, swap_positions=["WR"])
    assert old["downgrade"] == base["downgrade"]


# ── #402 rev-3 §3 — lateral_scope ("band" | "tier") ──────────────────────
#
# "tier" replaces the ±band + #108 gates + fairness floor for the LATERAL
# group only: the pool is every counterpart on the pin's rung of the
# 8-tier ladder (tier_for_elo). Default "band" is byte-identical to today
# for every caller; upgrade/downgrade keep band math under either scope.

def test_lateral_scope_default_is_band_identity():
    """Omitted and explicit "band" are byte-identical, both directions."""
    base = _give_ideas()
    assert _give_ideas(lateral_scope="band") == base
    rbase = _recv_ideas()
    assert _recv_ideas(lateral_scope="band") == rbase


def test_tier_scope_returns_tier_mates_band_excluded():
    """GIVE fixture, pin P elo 1560 → tier 'second' (elo 1370–1575).
    D1 1520 (v≈1105) and D2 1500 (v=1000) are tier-mates OUTSIDE the ±10%
    value band [1214.9, 1484.8]; L2 1550 is in band but #108-gated. Under
    "tier" all of them join lateral ungated and unlabeled; U (first_1,
    a different rung) never does; upgrade and downgrade are byte-identical
    to band scope (tier never relaxes them — the sabotage case)."""
    band = _give_ideas()
    assert [i["receive_player_ids"] for i in band["lateral"]] == [["L"]]
    tier = _give_ideas(lateral_scope="tier")
    got = {i["receive_player_ids"][0] for i in tier["lateral"]}
    assert got == {"L", "L2", "D1", "D2"}
    for idea in tier["lateral"]:
        assert "relaxed" not in idea          # membership, not fairness
        assert idea["give_player_ids"] == ["P"]
    assert tier["upgrade"] == band["upgrade"]
    assert tier["downgrade"] == band["downgrade"]
    # Determinism holds under tier scope too.
    assert _give_ideas(lateral_scope="tier") == tier


def test_tier_scope_receive_mirror_and_groups_unchanged():
    """RECV fixture, pin T 1700 → 'first_1' (1580–1785). G_up 1650 and
    G_down 1720 are tier-mates that band scope classes as upgrade /
    downgrade; under "tier" they ALSO appear as laterals (group-scoped
    dedupe) while upgrade and downgrade stay byte-identical."""
    band = _recv_ideas()
    tier = _recv_ideas(lateral_scope="tier")
    got = {i["give_player_ids"][0] for i in tier["lateral"]}
    assert got == {"G_up", "G_lat", "G_down"}
    for idea in tier["lateral"]:
        assert "relaxed" not in idea
        assert idea["receive_player_ids"] == ["T"]
    assert tier["upgrade"] == band["upgrade"]
    assert tier["downgrade"] == band["downgrade"]


def test_tier_scope_respects_caps_exclusions_and_avoids():
    """Tier scope changes MEMBERSHIP only — the group cap, |difference|
    ordering, not-interested exclusion and #360 avoided positions all
    still bind on the lateral group."""
    elos = {"P": 1560.0}
    ids = []
    for i in range(11):                    # 11 tier-mates ('second' rung),
        pid = f"TM{i}"                     # most outside the ±10% band
        ids.append(pid)
        elos[pid] = 1380.0 + 18.0 * i
    players = {pid: _Player(pid) for pid in elos}
    players["TM0"] = _Player("TM0", position="WR")
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=ids, elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["P"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos),
              lateral_scope="tier")
    groups = svc.generate_asset_ideas(**kw)
    # Cap + ordering (band scope would return only the in-band few).
    assert len(groups["lateral"]) == int(ts._DEFAULT_CFG["asset_ideas_group_cap"])
    diffs = [abs(i["difference"]) for i in groups["lateral"]]
    assert diffs == sorted(diffs)
    # The WR tier-mate is position-locked out by the #198 default (empty
    # selection = the pin's own position), and #360 avoid still wins.
    for idea in groups["lateral"]:
        assert "TM0" not in idea["receive_player_ids"]
    ni = svc.generate_asset_ideas(**{**kw, "not_interested_ids": {"TM10"}})
    for idea in ni["lateral"]:
        assert "TM10" not in idea["receive_player_ids"]
    avoided = svc.generate_asset_ideas(**{**kw, "avoid_positions": ["RB"]})
    assert avoided["lateral"] == []


# ── #402 rev-3 QA-B F2 — D-067 dismiss cooldown on the asset-ideas sweep ─
#
# A package dismissed via /api/trades/swipe (decision='pass', a full
# Elo-moving decision with a 14-day server-side cooldown) must NOT be
# re-served by the next asset-ideas fetch — D-067's own rule: "the cooldown
# binds every live service immediately". Only DISMISSES exclude: a like is
# a queued proposal. The windowing (14d expiry, amnesty) is applied at load
# and pinned by test_pass_cooldown.py; here the contract is the consult.


def _give_service_with(past=None, dismissed=None):
    players = {pid: _Player(pid) for pid in GIVE_ELO}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L", "L2", "D1", "D2"], elo_ratings={})
    svc = TradeService(players=players, past_decision_keys=past or set(),
                       dismissed_keys=dismissed)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc


def test_dismissed_package_excluded_from_asset_ideas():
    """QA-B F2 — a live dismiss cooldown on (P → L) removes exactly that
    idea from the sweep, under BOTH lateral scopes (correctness rule, not
    a tier feature); every other idea is untouched.

    SABOTAGE (cooldown consult removed — the _dismissed guard deleted from
    _emit/_emit_best/the combo loop): L is re-served → RED."""
    key = (frozenset({"P"}), frozenset({"L"}))
    base_band = _give_ideas()
    base_tier = _give_ideas(lateral_scope="tier")
    svc = _give_service_with(past={key}, dismissed={key})
    band = _give_ideas(svc=svc)
    assert band["lateral"] == []                    # L was the only band lateral
    assert band["upgrade"] == base_band["upgrade"]
    assert band["downgrade"] == base_band["downgrade"]
    tier = _give_ideas(svc=_give_service_with(past={key}, dismissed={key}),
                       lateral_scope="tier")
    got = {i["receive_player_ids"][0] for i in tier["lateral"]}
    assert got == {"L2", "D1", "D2"}                # tier-mates minus the dismiss
    assert tier["upgrade"] == base_tier["upgrade"]
    assert tier["downgrade"] == base_tier["downgrade"]
    # A dismissed multi-piece package excludes by SET identity too.
    dkey = (frozenset({"P"}), frozenset({"D1", "D2"}))
    down = _give_ideas(svc=_give_service_with(past={dkey}, dismissed={dkey}))
    assert down["downgrade"] == []
    assert down["lateral"] == base_band["lateral"]


def test_dismissed_package_excluded_receive_direction():
    """QA-B F2 parity — the receive-direction sweep consults the same keys
    (user orientation: give = what the user sends), band and tier."""
    key = (frozenset({"G_lat"}), frozenset({"T"}))
    players = {pid: _Player(pid) for pid in RECV_ELO}
    owner = LeagueMember(user_id="opp2", username="Owner",
                         roster=["T", "E"], elo_ratings={})
    svc = TradeService(players=players, past_decision_keys={key},
                       dismissed_keys={key})
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner]))
    for scope in (None, "band", "tier"):
        kw = {} if scope is None else {"lateral_scope": scope}
        base = _recv_ideas(**kw)
        got = _recv_ideas(svc=svc, **kw)
        assert all(i["give_player_ids"] != ["G_lat"] for i in got["lateral"])
        assert got["upgrade"] == base["upgrade"]
        assert got["downgrade"] == base["downgrade"]
        svc = TradeService(players=players, past_decision_keys={key},
                           dismissed_keys={key})
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[owner]))


def test_expired_dismiss_cooldown_returns():
    """Two-sided bar: the exclusion is the WINDOWED set loaded per D-067
    (14d cut at session build — the window math itself is pinned by
    test_pass_cooldown.py). An expired dismiss never enters
    dismissed_keys, so the idea returns — the cooldown must expire, not
    become permanent."""
    expired = _give_service_with(past=set(), dismissed=set())
    assert _give_ideas(svc=expired) == _give_ideas()
    assert (_give_ideas(svc=_give_service_with(), lateral_scope="tier")
            == _give_ideas(lateral_scope="tier"))


def test_past_decision_keys_do_not_exclude_asset_ideas():
    """The mixed `_past_decision_keys` set the DECK consults never excludes
    on this sweep — the pre-F2 pin, still true after D-178.

    NOT a claim that a like cannot exclude here: D-178 (#418) says it does,
    but through the explicit `exclusion_keys` kwarg (the deck's windowless
    R4 #336 set, built per request by
    `server._load_presentment_exclusions`), never through this mixed set of
    every past disposition. The route tests at the bottom of this file pin
    that half.

    SABOTAGE (consult widened to _past_decision_keys): the liked idea
    vanishes → RED."""
    key = (frozenset({"P"}), frozenset({"L"}))
    liked = _give_service_with(past={key})          # like ⇒ mixed set only
    for scope_kw in ({}, {"lateral_scope": "band"}, {"lateral_scope": "tier"}):
        assert (_give_ideas(svc=_give_service_with(past={key}), **scope_kw)
                == _give_ideas(**scope_kw))
    assert [i["receive_player_ids"]
            for i in _give_ideas(svc=liked)["lateral"]] == [["L"]]


def test_swap_positions_composes_with_tier_scope():
    """Both request fields together: a WR-only selection under tier scope
    returns the WR tier-mates (in-band and out), and the upgrade group
    matches the WR-filtered BAND-scope upgrade — tier touches lateral
    only, the filter touches all groups."""
    svc, elos = _cross_pos_service()
    elos = dict(elos, WX=1400.0)               # WR tier-mate, v≈606 —
    svc._players["WX"] = _Player("WX", position="WR")   # far below band
    svc._leagues["L1"].members[0].roster.append("WX")
    kw = dict(user_id="user", user_roster=["P", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    band_wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                       lateral_scope="band")   # rev-3 shape
    assert [i["receive_player_ids"] for i in band_wr["lateral"]] == [["WL"]]
    tier_wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                       lateral_scope="tier")
    got = {i["receive_player_ids"][0] for i in tier_wr["lateral"]}
    assert got == {"WL", "WX"}
    assert tier_wr["upgrade"] == band_wr["upgrade"]
    assert tier_wr["downgrade"] == band_wr["downgrade"]


def test_swap_positions_composes_with_tier_scope_receive_direction():
    """QA-B F4 (reviewer B's named gap) — the receive-direction mirror of
    the compose case: WR-only + tier scope makes the lateral group the
    user's WR tier-mates of the pin (in-band WLat AND below-band WX, both
    'first_1' like T), while upgrade matches the WR-filtered band-scope
    upgrade — tier touches lateral membership only, the filter touches
    all groups (rev-3 request shape in both calls)."""
    elos = {**RECV_ELO, "WU": 1650.0, "WLat": 1690.0, "WX": 1600.0}
    players = {pid: _Player(pid) for pid in RECV_ELO}
    players["WU"] = _Player("WU", position="WR")
    players["WLat"] = _Player("WLat", position="WR")
    players["WX"] = _Player("WX", position="WR")   # 'first_1' tier-mate,
    owner = LeagueMember(user_id="opp2", username="Owner",   # below band
                         roster=["T", "E"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[owner]))
    kw = dict(user_id="user",
              user_roster=["G_up", "G2", "G_lat", "G_down",
                           "WU", "WLat", "WX"],
              league_id="L1", seed_elo=dict(elos), asset_id="T",
              direction="receive", fairness_threshold=0.50,
              raw_user_elo=dict(elos))
    band_wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                       lateral_scope="band")
    assert [i["give_player_ids"] for i in band_wr["lateral"]] == [["WLat"]]
    tier_wr = svc.generate_asset_ideas(**kw, swap_positions=["WR"],
                                       lateral_scope="tier")
    got = {i["give_player_ids"][0] for i in tier_wr["lateral"]}
    # WU (1650) sits on 'first_1' too: under band+swap it is the upgrade
    # headliner ONLY; under tier it is honestly BOTH (group-scoped dedupe).
    assert got == {"WLat", "WX", "WU"}
    for idea in tier_wr["lateral"]:
        assert "relaxed" not in idea
        assert idea["receive_player_ids"] == ["T"]
    assert tier_wr["upgrade"] == band_wr["upgrade"]
    assert tier_wr["downgrade"] == band_wr["downgrade"]


def test_pick_pin_under_tier_scope():
    """QA-B F4 (reviewer B's named gap) — a PICK pin under tier scope:
    pos_constrained is False (pure value semantics, #198), so the lateral
    group is every tier-mate of the pin's rung REGARDLESS of position —
    including one far outside the ±band that band scope excluded — and
    the bands resolve via tier_bands_for's RB fallback (identical across
    positions by design). Upgrade/downgrade keep band math."""
    elos = {"PK": 1560.0, "S1": 1610.0, "U": 1700.0, "L": 1570.0,
            "D": 1400.0}
    players = {
        "PK": _Player("PK", position="PICK"),
        "S1": _Player("S1"),
        "U":  _Player("U", position="WR"),      # 'first_1' — different rung
        "L":  _Player("L", position="QB"),      # 'second', in band
        "D":  _Player("D", position="TE"),      # 'second', far BELOW band
    }
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["U", "L", "D"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["PK", "S1"], league_id="L1",
              seed_elo=dict(elos), asset_id="PK", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    band = svc.generate_asset_ideas(**kw)
    assert [i["receive_player_ids"] for i in band["lateral"]] == [["L"]]
    tier = svc.generate_asset_ideas(**kw, lateral_scope="tier")
    got = {i["receive_player_ids"][0] for i in tier["lateral"]}
    assert got == {"L", "D"}                    # cross-position tier-mates
    for idea in tier["lateral"]:
        assert "relaxed" not in idea
    assert tier["upgrade"] == band["upgrade"]   # rung 'first_1' ⇒ never lateral
    assert [i["receive_player_ids"] for i in tier["upgrade"]] == [["U"]]


def test_seed_missing_asset_has_no_tier():
    """QA-B F3 (reviewer B plausible 7) — an asset with NO real seed has
    NO tier: _tier_of returns None instead of bucketing the 1500.0
    placeholder onto the 'second' rung, so tier scope never surfaces
    default-priced assets the band + #108 gates used to hide. The same
    asset stays band-eligible exactly as today (band math prices the
    default).

    SABOTAGE (guard removed — _tier_of falls back to 1500.0): M buckets
    'second' and appears as a tier-mate of the 'second'-rung pin → RED."""
    # Pin at elo 1490 (v≈951, band [856, 1046]) — the seed-missing M
    # prices at the 1000.0 default: inside the band, above the pin (#108
    # passes), and 1500.0 would bucket 'second' exactly like the pin.
    elos = {"P": 1490.0, "L": 1495.0}           # M deliberately ABSENT
    players = {pid: _Player(pid) for pid in ("P", "L", "M")}
    opp = LeagueMember(user_id="opp", username="OppTeam",
                       roster=["L", "M"], elo_ratings={})
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    kw = dict(user_id="user", user_roster=["P"], league_id="L1",
              seed_elo=dict(elos), asset_id="P", direction="give",
              fairness_threshold=0.50, raw_user_elo=dict(elos))
    band = svc.generate_asset_ideas(**kw)
    assert any(i["receive_player_ids"] == ["M"] for i in band["lateral"]), \
        "seed-missing must stay band-eligible exactly as today"
    tier = svc.generate_asset_ideas(**kw, lateral_scope="tier")
    for group in tier.values():
        for idea in group:
            assert "M" not in idea["receive_player_ids"], \
                "a seed-missing asset has no rung — it never tier-matches"
    # The seeded tier-mate still matches — the guard is surgical.
    assert any(i["receive_player_ids"] == ["L"] for i in tier["lateral"])


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

    def record_trade_signal(self, **kw):
        """The Elo half of a ✓ (`/api/trades/queue`). Irrelevant to what this
        file pins — the D-178 tests below need the DECISION ROW that route
        writes, not the board move — so it is a no-op here."""
        return None


@pytest.fixture()
def route_db():
    """D-178 (#418) — the route now READS the database: it builds the deck's
    awaiting-like exclusion set per request. An isolated in-memory DB keeps
    that hermetic (and stops every route test below from touching the real
    `data/trade_finder.db`)."""
    from sqlalchemy import create_engine

    import backend.database as db_module
    from backend.database import metadata

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


@pytest.fixture()
def route_client(route_db):
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


# ── #403 W2 — route validation for swap_positions ─────────────────────────

def test_route_swap_positions_omitted_null_empty_identical(route_client):
    """Absent, null and [] produce byte-identical 200 responses (R-11)."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client, {"asset_id": "P", "direction": "give"})
    as_null = _post(route_client, {"asset_id": "P", "direction": "give",
                                   "swap_positions": None})
    as_empty = _post(route_client, {"asset_id": "P", "direction": "give",
                                    "swap_positions": []})
    assert plain.status_code == as_null.status_code == as_empty.status_code == 200
    assert plain.get_json() == as_null.get_json() == as_empty.get_json()


def test_route_threads_swap_positions(route_client):
    """The field reaches the generator, on BOTH request shapes (QA-B F1).

    OLD shape — swap_positions WITHOUT lateral_scope: the exact v1.16.9
    wire case (the fielded inline strip sends the selection on the one
    fetch feeding all three mode groups, but its picker UI promised
    Same-value-only). On the all-RB give fixture a WR selection empties
    the LATERAL group while upgrade/downgrade stay byte-identical to the
    plain response — deploying rev-3 must not silently change Tier
    up/down for a v1.16.9 user holding a selection.

    NEW shape — lateral_scope present: rev-3 §2, the set constrains every
    group's headline piece; WR empties ALL THREE groups (honest empties).

    Selecting the pin's own position reproduces the plain response under
    either shape."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client,
                  {"asset_id": "P", "direction": "give"}).get_json()
    assert plain["groups"]["upgrade"] and plain["groups"]["downgrade"]
    # OLD shape (v1.16.9 wire case): lateral filters, the rest is pinned.
    wr_old = _post(route_client, {"asset_id": "P", "direction": "give",
                                  "swap_positions": ["WR"]})
    assert wr_old.status_code == 200, wr_old.get_json()
    old_groups = wr_old.get_json()["groups"]
    assert old_groups["lateral"] == []
    assert old_groups["upgrade"] == plain["groups"]["upgrade"]
    assert old_groups["downgrade"] == plain["groups"]["downgrade"]
    # NEW shape (rev-3 signature): the set constrains every group.
    wr_new = _post(route_client, {"asset_id": "P", "direction": "give",
                                  "swap_positions": ["WR"],
                                  "lateral_scope": "band"})
    assert wr_new.status_code == 200, wr_new.get_json()
    assert wr_new.get_json()["groups"] == {
        "upgrade": [], "lateral": [], "downgrade": []}
    # Own-position selection ≡ plain, under either shape.
    rb = _post(route_client, {"asset_id": "P", "direction": "give",
                              "swap_positions": ["RB"]})
    assert rb.get_json()["groups"] == plain["groups"]
    rb_new = _post(route_client, {"asset_id": "P", "direction": "give",
                                  "swap_positions": ["RB"],
                                  "lateral_scope": "band"})
    assert rb_new.get_json()["groups"] == plain["groups"]
    # Normalization: strip+upper and first-seen dedupe.
    messy = _post(route_client, {"asset_id": "P", "direction": "give",
                                 "swap_positions": [" rb ", "RB", "rb"]})
    assert messy.status_code == 200
    assert messy.get_json()["groups"] == plain["groups"]


@pytest.mark.parametrize("swap,status,err,value", [
    (["K"],           400, "invalid_position", "K"),
    (["PICK"],        400, "invalid_position", "PICK"),      # rejected on
                                                             # purpose — see
                                                             # the route
    (["QB", "FLEX"],  400, "invalid_position", "FLEX"),
    ([1],             400, "invalid_position", "1"),
    ([None],          400, "invalid_position", "None"),
    ("RB",            400, "swap_positions must be an array", None),
    (True,            400, "swap_positions must be an array", None),
    ({"pos": "RB"},   400, "swap_positions must be an array", None),
    ([" rb "],        200, None, None),      # must-succeed leg (R-12)
])
def test_invalid_position_is_400(route_client, swap, status, err, value):
    """R-12 — invalid positions are a named 400, never a silent empty;
    " rb " normalizes to RB and succeeds."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    r = _post(route_client, {"asset_id": "P", "direction": "give",
                             "swap_positions": swap})
    assert r.status_code == status, r.get_json()
    if err is not None:
        body = r.get_json()
        assert body["error"] == err
        if value is not None:
            assert body["value"] == value


# ── #402 rev-3 §3 — route: lateral_scope ─────────────────────────────────

def test_route_lateral_scope_default_is_band(route_client):
    """Omitted and explicit "band" produce byte-identical 200 responses —
    every existing caller (the single-pin panel included) is untouched."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client, {"asset_id": "P", "direction": "give"})
    band = _post(route_client, {"asset_id": "P", "direction": "give",
                                "lateral_scope": "band"})
    assert plain.status_code == band.status_code == 200
    assert plain.get_json() == band.get_json()


def test_route_lateral_scope_tier_threads_through(route_client):
    """"tier" reaches the generator: the give fixture's 'second'-rung
    tier-mates (L, L2, D1, D2 — two of them outside the ±10% band, one
    #108-gated under band scope) fill lateral; upgrade and downgrade are
    byte-identical to the band response."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client,
                  {"asset_id": "P", "direction": "give"}).get_json()
    r = _post(route_client, {"asset_id": "P", "direction": "give",
                             "lateral_scope": "tier"})
    assert r.status_code == 200, r.get_json()
    groups = r.get_json()["groups"]
    assert ({i["receive_player_ids"][0] for i in groups["lateral"]}
            == {"L", "L2", "D1", "D2"})
    assert groups["upgrade"] == plain["groups"]["upgrade"]
    assert groups["downgrade"] == plain["groups"]["downgrade"]
    for idea in groups["lateral"]:
        assert "relaxed" not in idea
        assert idea["favors"] in ("give", "receive", "even")   # verdict prices it


def test_route_excludes_dismissed_packages(route_client):
    """QA-B F2 route-level — a dismiss bound to the live service (the
    swipe route's in-memory D-067 update / the session_init load) removes
    the package from the very next asset-ideas response, both scopes;
    everything else unchanged."""
    import backend.server as server
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client,
                  {"asset_id": "P", "direction": "give"}).get_json()
    assert [i["receive_player_ids"]
            for i in plain["groups"]["lateral"]] == [["L"]]
    with server._sessions_lock:
        svc = server._sessions[TOKEN]["trade_svc"]
    svc._dismissed_decision_keys.add((frozenset({"P"}), frozenset({"L"})))
    try:
        after = _post(route_client,
                      {"asset_id": "P", "direction": "give"}).get_json()
        assert after["groups"]["lateral"] == []
        assert after["groups"]["upgrade"] == plain["groups"]["upgrade"]
        assert after["groups"]["downgrade"] == plain["groups"]["downgrade"]
        tier = _post(route_client, {"asset_id": "P", "direction": "give",
                                    "lateral_scope": "tier"}).get_json()
        assert ({i["receive_player_ids"][0]
                 for i in tier["groups"]["lateral"]} == {"L2", "D1", "D2"})
    finally:
        svc._dismissed_decision_keys.clear()


def test_route_composes_swap_and_tier(route_client):
    """Both request fields together thread through: own-position selection
    + tier scope returns the four RB tier-mates; a WR-only selection under
    tier scope is an honest all-empty on this all-RB fixture."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    rb = _post(route_client, {"asset_id": "P", "direction": "give",
                              "swap_positions": ["RB"],
                              "lateral_scope": "tier"})
    assert rb.status_code == 200, rb.get_json()
    assert ({i["receive_player_ids"][0] for i in rb.get_json()["groups"]["lateral"]}
            == {"L", "L2", "D1", "D2"})
    wr = _post(route_client, {"asset_id": "P", "direction": "give",
                              "swap_positions": ["WR"],
                              "lateral_scope": "tier"})
    assert wr.get_json()["groups"] == {
        "upgrade": [], "lateral": [], "downgrade": []}


@pytest.mark.parametrize("scope", [
    "TIER", "Band", "", "both", "bands", 5, True, ["tier"], {"scope": "tier"},
])
def test_route_invalid_lateral_scope_is_400(route_client, scope):
    """Invalid lateral_scope values are a named 400 (rev-3 §3), never a
    silent band default — a silently-defaulted scope looks exactly like a
    toggle that did nothing. Domain is exactly {"band", "tier"}."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    r = _post(route_client, {"asset_id": "P", "direction": "give",
                             "lateral_scope": scope})
    assert r.status_code == 400, r.get_json()
    assert r.get_json()["error"] == "invalid_lateral_scope"


def test_route_lateral_scope_null_is_band(route_client):
    """JSON null = omitted (the shop client never sends null, but the
    contract mirrors swap_positions' null handling)."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.asset_ideas": True}
    plain = _post(route_client, {"asset_id": "P", "direction": "give"})
    as_null = _post(route_client, {"asset_id": "P", "direction": "give",
                                   "lateral_scope": None})
    assert as_null.status_code == 200
    assert plain.get_json() == as_null.get_json()


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

    # 2026-08-21 — the cross-package benchmark fix post-dates this fixture
    # (its literal values were sized against own-max market math; under the
    # trade-wide benchmark the P+pair package prices below the fairness
    # floor by design). Pinned to the kill value so this stays the #286
    # paired-sweetener mechanics guard; the new benchmark's own shapes are
    # pinned in test_package_benchmark.py.
    ts._cfg["package_bench_trade_wide"] = 0.0
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

    # 2026-08-21 — same kill-value pin as the give-direction test above;
    # see the comment there.
    ts._cfg["package_bench_trade_wide"] = 0.0
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


# ── D-178 (#418) — a sent offer is a LIKE, so it stops being offered ──────
#
# Operator ruling, verbatim: *"needs a backend follow up. This should be
# treated the same as any other 'liked' trade."* The shop's ✓ ("Send this
# offer") writes a real `decision="like"` row through POST /api/trades/queue,
# and the model deck has always refused to re-offer a package the caller has
# an un-retracted awaiting like on (G6 R4 #336 — NO time window). This route
# consulted only the D-067 dismiss cooldown, so a SENT idea came back on the
# next window open looking new while a DISMISSED one stayed gone.
#
# Fixture honesty: every like here is written by the shipped ✓ route and
# every retraction by the shipped POST /api/trades/awaiting/dismiss (#318).
# `load_awaiting_trades` recovers the counterparty from the `league_members`
# roster snapshot `session_init` persists, so these tests persist it too —
# without it a like is invisible to the exclusion set, in tests and in prod
# alike.

_ROUTE_FLAGS = {
    "trade.asset_ideas":       True,
    "calc.merged_layout":      True,   # the ✓ route's own gate
    "trade.presentment_rules": True,   # R4's one switch (true in prod)
}


def _lit_route_flags(**over):
    ff._flags_cache = {**ff.DEFAULT_FLAGS, **_ROUTE_FLAGS, **over}


def _seed_route_members():
    """The membership snapshot session_init writes (upsert_league_members).
    `league.members` is caller-excluded by app convention (FB-409), but the
    persisted snapshot is not — it carries every owner, which is how the
    counterparty of a like is recovered."""
    from backend.database import upsert_league_members
    upsert_league_members("L1", [
        {"user_id": "user", "username": "Me",
         "player_ids": ["P", "S1"]},
        {"user_id": "opp", "username": "OppTeam",
         "player_ids": ["U", "L", "L2", "D1", "D2"]},
    ])


def _send(client, idea):
    """The shop's ✓ — POST /api/trades/queue, the route that turns 'Send this
    offer' into a decision='like' row."""
    return client.post(
        "/api/trades/queue",
        json={"league_id":          "L1",
              "opponent_user_id":   idea["counterparty_user_id"],
              "give_player_ids":    idea["give_player_ids"],
              "receive_player_ids": idea["receive_player_ids"]},
        headers={"X-Session-Token": TOKEN})


def test_route_excludes_a_sent_offer(route_client):
    """(a) The ruling. Send the lateral idea (P → L); the next fetch has no
    lateral at all and the other two groups are untouched — band scope and
    tier scope alike, because the exclusion is a correctness rule, not a
    tier feature.

    SABOTAGE (the route stops loading/passing `exclusion_keys`): L is
    re-served → RED."""
    _lit_route_flags()
    _seed_route_members()
    before = _post(route_client,
                   {"asset_id": "P", "direction": "give"}).get_json()
    assert [i["receive_player_ids"]
            for i in before["groups"]["lateral"]] == [["L"]]

    res = _send(route_client, before["groups"]["lateral"][0])
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["queued"] is True

    after = _post(route_client,
                  {"asset_id": "P", "direction": "give"}).get_json()
    assert after["groups"]["lateral"] == []
    assert after["groups"]["upgrade"] == before["groups"]["upgrade"]
    assert after["groups"]["downgrade"] == before["groups"]["downgrade"]

    tier = _post(route_client, {"asset_id": "P", "direction": "give",
                                "lateral_scope": "tier"}).get_json()
    assert ({i["receive_player_ids"][0] for i in tier["groups"]["lateral"]}
            == {"L2", "D1", "D2"})


def test_route_returns_a_retracted_like(route_client):
    """(b) Q-G6-2 / #318, inherited: `load_awaiting_trades` already drops
    retracted likes, so retracting the Awaiting tile brings the idea back.
    Nothing about retraction is re-implemented on this route.

    SABOTAGE (a bespoke 'sent' memory instead of the shared loader): the
    idea stays gone → RED."""
    _lit_route_flags()
    _seed_route_members()
    before = _post(route_client,
                   {"asset_id": "P", "direction": "give"}).get_json()
    idea = before["groups"]["lateral"][0]
    assert _send(route_client, idea).status_code == 200
    assert _post(route_client, {"asset_id": "P", "direction": "give"}
                 ).get_json()["groups"]["lateral"] == []

    res = route_client.post(
        "/api/trades/awaiting/dismiss",
        json={"league_id":  "L1",
              "my_give":    idea["give_player_ids"],
              "my_receive": idea["receive_player_ids"],
              "partner_id": idea["counterparty_user_id"]},
        headers={"X-Session-Token": TOKEN})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["dismissed_likes"] >= 1

    assert _post(route_client,
                 {"asset_id": "P", "direction": "give"}).get_json() == before


def test_route_dismiss_behaviour_is_unchanged(route_client):
    """(c) D-067 regression bar: the dismiss cooldown still excludes on its
    own — with NO like row and NO exclusion set — and still binds through
    the live service the swipe route mutates in memory. D-178 widened the
    predicate; it must not have replaced it."""
    _lit_route_flags()
    _seed_route_members()
    import backend.server as server
    plain = _post(route_client,
                  {"asset_id": "P", "direction": "give"}).get_json()
    with server._sessions_lock:
        svc = server._sessions[TOKEN]["trade_svc"]
    svc._dismissed_decision_keys.add((frozenset({"P"}), frozenset({"L"})))
    try:
        after = _post(route_client,
                      {"asset_id": "P", "direction": "give"}).get_json()
        assert after["groups"]["lateral"] == []
        assert after["groups"]["upgrade"] == plain["groups"]["upgrade"]
        assert after["groups"]["downgrade"] == plain["groups"]["downgrade"]
    finally:
        svc._dismissed_decision_keys.clear()


def test_route_group_cap_refills_after_an_exclusion(route_client):
    """(d) The filter runs at EMISSION, inside `asset_ideas_group_cap`, so a
    sent offer costs its own slot and no more: a 2-deep group stays 2 deep by
    promoting the next-best idea.

    SABOTAGE (filter applied to the response groups instead of at emission):
    the capped group comes back one short → RED."""
    _lit_route_flags()
    _seed_route_members()
    ts._cfg["asset_ideas_group_cap"] = 2.0
    full = _post(route_client, {"asset_id": "P", "direction": "give",
                                "lateral_scope": "tier"}).get_json()
    lateral = full["groups"]["lateral"]
    assert len(lateral) == 2, lateral
    uncapped = ["L", "L2", "D1", "D2"]

    assert _send(route_client, lateral[0]).status_code == 200
    after = _post(route_client, {"asset_id": "P", "direction": "give",
                                 "lateral_scope": "tier"}).get_json()
    got = [i["receive_player_ids"][0] for i in after["groups"]["lateral"]]
    assert len(got) == 2, "the cap must REFILL, not shrink"
    assert lateral[0]["receive_player_ids"][0] not in got
    assert set(got) <= set(uncapped)


def test_route_serves_unfiltered_when_the_load_breaks(route_client):
    """(e) Non-fatal posture, inherited from `_load_presentment_exclusions`:
    a raising loader logs and yields an empty set, so the groups answer
    unfiltered instead of 500-ing.

    SABOTAGE (the load hoisted out of the loader's try/except): 500 → RED."""
    _lit_route_flags()
    _seed_route_members()
    import backend.server as server
    before = _post(route_client,
                   {"asset_id": "P", "direction": "give"}).get_json()
    assert _send(route_client, before["groups"]["lateral"][0]).status_code == 200

    def _boom(_user_id):
        raise RuntimeError("awaiting load exploded")

    with patch.object(server, "load_awaiting_trades", _boom):
        res = _post(route_client, {"asset_id": "P", "direction": "give"})
    assert res.status_code == 200
    assert res.get_json() == before


def test_route_flag_off_is_byte_identical(route_client):
    """`trade.presentment_rules` stays R4's ONE switch: with it off this
    route builds no set and re-serves the sent package, exactly as it did
    before D-178."""
    _lit_route_flags()
    _seed_route_members()
    before = _post(route_client,
                   {"asset_id": "P", "direction": "give"}).get_json()
    assert _send(route_client, before["groups"]["lateral"][0]).status_code == 200
    _lit_route_flags(**{"trade.presentment_rules": False})
    assert _post(route_client,
                 {"asset_id": "P", "direction": "give"}).get_json() == before
