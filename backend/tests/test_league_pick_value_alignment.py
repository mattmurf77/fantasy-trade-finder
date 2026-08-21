"""D-147 (2026-08-21) — league surfaces price picks exactly like the engine.

Closes Q-026. Operator ruling: *"I want the league values to reflect the same
pick values."* D-146 had put the per-slot waterfall into the ENGINE only, so
a 2026 1.01 read 2117.0 on Power Rankings and 4867.1 inside a trade card — a
2.3x disagreement about the single most valuable asset a team can hold.

The per-surface VALUES are pinned in each surface's own file
(`test_power_rankings.py`, `test_league_picks_tier.py`, `test_trade_evaluate.
py`). What lives here is what none of those can assert on its own:

  A. THE ONE SEAM — an AST walk proving every pricing call in `server.py`
     goes through `_priced_pick_value`, and that its callers are exactly the
     five known sites. Bidirectional, so both a new site sneaking around the
     seam and a known site quietly dropping out fail.
  B. RESOLVE-ONCE — Power Rankings iterates every roster in one request;
     `_league_slot_order` must be hit once per LEAGUE, not once per pick.
  C. BOARD ↔ ENGINE — the Draft Room's display prices and the engine's per-slot
     prices come off the same DP rows, asserted rather than assumed. Includes
     the one place they DON'T agree, pinned so it cannot drift silently.
  D. THE FLOOR — a legacy NULL `pool_value` and an unreachable DP still land
     on exactly the number these surfaces served before this ship.
"""
import ast
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.data_loader as data_loader
import backend.draft_board_service as dbs
import backend.server as server
from backend.pick_values import (market_pick_slot_value, pick_pool_value,
                                 priced_pool_value)
from backend.trade_service import elo_to_value

REPO = pathlib.Path(__file__).resolve().parents[2]
FMT = "1qb_ppr"
LEAGUE = "league_align_test"


# ═══════════════════════════════════════════════════════════════════════════
# A. The one seam
# ═══════════════════════════════════════════════════════════════════════════

#: The ONLY function in `server.py` permitted to call `priced_pool_value`.
_PRICING_SEAM = "_priced_pick_value"

#: Every function permitted to call the seam. This list IS the answer to
#: "which surfaces price owned picks", so adding to it is a deliberate act:
#:
#:   _roster_eveners      S4 — one-tap sweeteners on /api/trade/evaluate
#:   _trade_evaluate_impl S1 — the manual calculator's owned-pick values
#:   get_league_picks     S1 — GET /api/league/picks values + tier badges
#:   _owned_pick_assets   S3 — the suggestion candidate pool (deck lane)
#:   _power_picks_by_owner S2 — Power Rankings + the ADR-011 history snapshot
_SEAM_CALLERS = {
    "_roster_eveners",
    "_trade_evaluate_impl",
    "get_league_picks",
    "_owned_pick_assets",
    "_power_picks_by_owner",
}


def _callers_of(tree: ast.AST, name: str) -> set[str]:
    """Names of the functions containing a call to `name`. Nested functions
    are attributed to the ENCLOSING top-level function, because that is the
    unit the seam list is written in (`get_league_picks` prices inside a
    local `_serialize` helper)."""
    out: set[str] = set()

    def walk(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, owner or child.name)
            else:
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == name and owner):
                    out.add(owner)
                walk(child, owner)

    walk(tree, None)
    return out


@pytest.fixture(scope="module")
def server_tree():
    return ast.parse((REPO / "backend" / "server.py").read_text())


def test_priced_pool_value_is_called_from_exactly_one_place(server_tree):
    """`priced_pool_value` — the pick_values waterfall — must be reached from
    `_priced_pick_value` and nowhere else in `server.py`.

    Without this, "the same waterfall with the same slot resolution" is six
    copies of one expression that agree today. Sabotage-verified: inlining
    the call at any surface fails here."""
    assert _callers_of(server_tree, "priced_pool_value") == {_PRICING_SEAM}


def test_the_seam_serves_exactly_the_known_surfaces(server_tree):
    """Bidirectional. A NEW pricing surface that forgets to be listed fails
    the first half; a listed surface that quietly stops pricing (regressing
    to `p["pool_value"]`, the pre-D-147 line) fails the second."""
    found = _callers_of(server_tree, _PRICING_SEAM)
    assert not found - _SEAM_CALLERS, f"unlisted pricing surface: {found - _SEAM_CALLERS}"
    assert not _SEAM_CALLERS - found, f"surface stopped pricing: {_SEAM_CALLERS - found}"


def test_no_league_surface_reads_the_stored_column_as_a_price(server_tree):
    """The specific regression D-147 fixes, refused structurally.

    `_power_picks_by_owner` and `get_league_picks` may still MENTION
    `pool_value` — the first re-derives a legacy NULL into a row copy, the
    second serializes the key — but neither may take it as the value it
    serves. Asserted as "the priced call happens", plus the behavioural pins
    in each surface's own file; the AST cannot tell a read from a write, so
    this is deliberately the weaker half of a two-part guarantee and says so
    rather than pretending otherwise."""
    for fn in ("_power_picks_by_owner", "get_league_picks", "_roster_eveners"):
        assert fn in _callers_of(server_tree, _PRICING_SEAM)


# ═══════════════════════════════════════════════════════════════════════════
# B. Resolve once per league, not once per pick
# ═══════════════════════════════════════════════════════════════════════════

def _rows(n_rosters=12, rounds=(1, 2, 3, 4), season=2026):
    out = []
    for rnd in rounds:
        for r in range(1, n_rosters + 1):
            out.append({"pick_id": f"{LEAGUE}_{season}_{rnd}_{r}",
                        "league_id": LEAGUE, "season": season, "round": rnd,
                        "owner_user_id": f"u{r}", "owner_username": f"m{r}",
                        "is_traded": 0, "original_username": f"m{r}",
                        "original_roster_id": f"r{r}",
                        "pool_value": pick_pool_value(rnd, season - 2026, FMT)})
    return out


ORDER_12 = {"schema": 1, "season": 2026, "teams": 12, "type": "linear",
            "slots": {f"r{i}": i for i in range(1, 13)}}


def test_power_rankings_resolves_the_draft_order_once_per_league(monkeypatch):
    """48 picks across 12 rosters, ONE `_league_slot_order` call.

    The 60s cache would hide a per-pick lookup in production; this counts the
    calls directly so the discipline is enforced rather than trusted. The
    waterfall itself is read-time and per pick — that part is cheap (an
    in-process dict); the DB-backed order lookup is what must not be."""
    calls = []
    real = server._league_slot_order

    def counting(league_id):
        calls.append(league_id)
        return ORDER_12

    monkeypatch.setattr(server, "_league_slot_order", counting)
    monkeypatch.setattr(server, "load_draft_picks", lambda **k: _rows())
    out = server._power_picks_by_owner(LEAGUE, FMT)
    assert calls == [LEAGUE], f"resolved {len(calls)} times for 48 picks"
    assert sum(len(v) for v in out.values()) == 48
    assert real is not counting            # the spy replaced the real thing


def test_power_rankings_prices_each_slot_at_its_own_market_value(monkeypatch):
    """The ruling, at the Power Rankings surface: a 1.01 and a 1.12 that
    STORE the identical rung now serve a 5.9x spread and the same numbers a
    trade card charges."""
    monkeypatch.setattr(server, "_league_slot_order", lambda lid: ORDER_12)
    monkeypatch.setattr(server, "load_draft_picks", lambda **k: _rows(rounds=(1,)))
    out = server._power_picks_by_owner(LEAGUE, FMT)
    first = out["u1"][0]
    twelfth = out["u12"][0]
    assert first["label"] == "2026 1.01" and twelfth["label"] == "2026 1.12"
    assert first["value"] == 4867.1 == market_pick_slot_value(2026, 1, 1, FMT)
    assert twelfth["value"] == 820.8 == market_pick_slot_value(2026, 1, 12, FMT)
    # …and both STORED the same number, which is what makes the spread a
    # pricing change rather than a data one.
    assert pick_pool_value(1, 0, FMT) == 2117.0
    assert first["value"] / twelfth["value"] > 5.0


# ═══════════════════════════════════════════════════════════════════════════
# C. The Draft Room board and the engine name the same DP rows
# ═══════════════════════════════════════════════════════════════════════════

def test_board_and_engine_agree_on_every_slot_of_a_twelve_team_board():
    """The board serves DP's SEED-ELO number (`_annotate_slot_values`); the
    engine serves the same row through `elo_to_value` (`market_pick_slot_
    value`). Different scales, one row — asserted for every published slot
    rather than assumed from the fact that both call `pick_slot_label`."""
    prices = data_loader.load_pick_slot_values(FMT)
    assert prices, "the pinned DP snapshot must be loaded (conftest)"
    checked = 0
    for rnd in range(1, 6):
        for slot in range(1, 13):
            board = prices.get(data_loader.pick_slot_label(2026, rnd, slot))
            engine = market_pick_slot_value(2026, rnd, slot, FMT)
            if board is None:
                assert engine is None, f"engine priced {rnd}.{slot:02d}, board did not"
                continue
            assert engine == round(elo_to_value(board), 1), f"{rnd}.{slot:02d}"
            checked += 1
    assert checked >= 48, f"only {checked} slots compared — snapshot too thin"


def test_non_twelve_team_boards_disagree_and_that_is_pinned_not_fixed():
    """⚠️  A NAMED DIVERGENCE, NOT A PASSING GRADE — see the scope block's
    disposition table and Q-027.

    DP publishes ONE 12-team curve. The Draft Room maps a smaller league onto
    it by percentile within the round (`_basis_slot`, plan O3), so a 10-team
    league's last first is priced as the 1.12. `market_pick_slot_value` does
    NOT: it has no league size to map with, so it looks up "2026 Pick 1.10"
    literally. The engine and every surface D-147 aligned therefore price a
    small league's late firsts ABOVE what its own board displays.

    Fixing it means threading league size into `priced_pool_value`, which
    reprices the ENGINE in every non-12-team league — outside this ship's
    ruling. So it is pinned here instead: this test failing means somebody
    changed one of the two mappings, and the operator's open question about
    which one is right needs answering before it ships."""
    assert dbs._basis_slot(10, 10) == 12          # board: last of 10 → the 1.12
    assert dbs._basis_slot(1, 10) == 1            # …ends are anchored
    assert dbs._basis_slot(7, 12) == 7            # 12-team is the identity
    board_price = data_loader.load_pick_slot_values(FMT)[
        data_loader.pick_slot_label(2026, 1, dbs._basis_slot(10, 10))]
    engine_price = market_pick_slot_value(2026, 1, 10, FMT)
    assert engine_price == round(elo_to_value(
        data_loader.load_pick_slot_values(FMT)[
            data_loader.pick_slot_label(2026, 1, 10)]), 1)
    assert engine_price != round(elo_to_value(board_price), 1)
    # The size of the disagreement, so a change to either mapping is visible.
    assert engine_price == 1069.8                 # priced as the 1.10
    assert round(elo_to_value(board_price), 1) == 820.8   # displayed as the 1.12

    # A 14-team league is the other half of the same gap: DP publishes no
    # 1.13/1.14, so those two picks fall off step 1 onto the ROUND curve
    # while their 12 leaguemates get per-slot prices.
    assert market_pick_slot_value(2026, 1, 13, FMT) is None
    assert market_pick_slot_value(2026, 1, 14, FMT) is None


# ═══════════════════════════════════════════════════════════════════════════
# D. The floor: what happens when the market has nothing to say
# ═══════════════════════════════════════════════════════════════════════════

def test_legacy_null_pool_value_keeps_its_ladder_floor_under_the_waterfall(monkeypatch):
    """INV-5's NULL branch survives D-147 rather than collapsing to zero.

    `_power_picks_by_owner` re-derives a pre-`pool_value`-column row from the
    ladder BEFORE running the waterfall, so that number is the row's step 3.
    With DP unreachable, every step above it is empty and the surface serves
    exactly what it served before this ship — which is the whole point of
    keeping the stored ladder as the floor."""
    rows = _rows(n_rosters=1, rounds=(4,))
    rows[0]["pool_value"] = None
    monkeypatch.setattr(server, "_league_slot_order", lambda lid: None)
    monkeypatch.setattr(server, "load_draft_picks", lambda **k: [dict(rows[0])])
    with patch.object(data_loader, "load_pick_slot_values", lambda *a, **k: {}):
        out = server._power_picks_by_owner(LEAGUE, FMT)
    assert out["u1"][0]["value"] == round(pick_pool_value(4, 0, FMT), 1) == 272.5


def test_dp_unreachable_degrades_every_surface_to_the_stored_ladder(monkeypatch):
    """The safety net, stated once. `load_pick_slot_values` fail-softs to
    `{}` on any fetch or parse failure, so both market steps return None and
    every aligned surface serves the stored column — today's price, not a
    wrong number and not an error."""
    rows = _rows(rounds=(1, 2))
    monkeypatch.setattr(server, "_league_slot_order", lambda lid: ORDER_12)
    monkeypatch.setattr(server, "load_draft_picks", lambda **k: rows)
    with patch.object(data_loader, "load_pick_slot_values", lambda *a, **k: {}):
        out = server._power_picks_by_owner(LEAGUE, FMT)
    for owner, items in out.items():
        for item in items:
            rnd = item["round"]
            assert item["value"] == round(pick_pool_value(rnd, 0, FMT), 1)
    # …and with DP present the SAME fixture prices differently, so the test
    # above cannot pass because nothing was ever priced.
    live = server._power_picks_by_owner(LEAGUE, FMT)
    assert live["u1"][0]["value"] != out["u1"][0]["value"]


def test_priced_pick_value_is_a_pure_read_and_never_mutates_the_row():
    """The stored column is written by a league-wide sync and shared by every
    user of the league; pricing is read-time in every mode (D-146). A helper
    that quietly stamped its answer back onto the row would make one user's
    request change another's price."""
    row = {"season": 2026, "round": 1, "original_roster_id": "r1",
           "pool_value": pick_pool_value(1, 0, FMT)}
    before = dict(row)
    v = server._priced_pick_value(row, ORDER_12, FMT)
    assert row == before
    assert v == market_pick_slot_value(2026, 1, 1, FMT)
    # …and it is exactly `priced_pool_value` with the slot D-090 resolves.
    assert v == priced_pool_value(row, scoring_format=FMT, slot=1)


def test_future_seasons_ride_the_round_curve_by_data_not_by_a_branch():
    """The operator's "future picks stay default for now", still falling out
    of the data: DP publishes per-slot rows only for the current class, and
    `slot_for` refuses a future season anyway (#273). Two independent
    refusals, so removing either one alone does not start pricing 2027 slots."""
    assert market_pick_slot_value(2027, 1, 1, FMT) is None      # DP has no row
    import backend.pick_slots as pick_slots
    assert pick_slots.slot_for(ORDER_12, 2027, 1, "r1") is None  # #273 refuses
    row = {"season": 2027, "round": 1, "original_roster_id": "r1",
           "pool_value": pick_pool_value(1, 1, FMT)}
    assert server._priced_pick_value(row, ORDER_12, FMT) == 1504.6


# ═══════════════════════════════════════════════════════════════════════════
# The ADR-011 boundary, asserted as a property of the writer
# ═══════════════════════════════════════════════════════════════════════════

def test_history_snapshot_reads_the_same_priced_picks_as_power_rankings(monkeypatch):
    """ADR-011 — `roster_history` takes its pick values from
    `_power_picks_by_owner`, so `team_value` / `team_value_picks` move with
    this ship. That is a time-series BOUNDARY (recorded in the scope block
    and TEST_LEDGER), and it is correct going forward precisely BECAUSE the
    snapshot has no pricing opinion of its own: it is handed the dict.

    Asserted by signature rather than by a full snapshot run — the contract
    that matters is "the writer does not re-price", and a second pricing path
    is what would break it."""
    src = (REPO / "backend" / "roster_history.py").read_text()
    assert "priced_pool_value" not in src
    assert "_priced_pick_value" not in src
    assert "picks_by_owner" in src, "the snapshot must be HANDED its prices"
    tree = ast.parse(src)
    assert not _callers_of(tree, "pick_pool_value"), \
        "roster_history must not price picks itself"
