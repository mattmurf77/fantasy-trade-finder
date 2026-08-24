"""C4 — the v3 package-shape rule is a knob (`v3_shape_max_delta`).

Plan: docs/plans/knockout-refine/plan.md §3 C4 / §5 item (7)+(8).

`trade_optimizer.generate_pair_trades_v3` enumerates give-subsets and
receive-subsets of size 1-3 and then drops any pair whose asset-count
difference exceeds the knob. Until 2026-08-23 that bound was the literal
`1`, which meant the 3-for-1 and 1-for-3 subsets were *built* by the
enumeration and thrown away one line later. The knob replaces the literal;
its default `1` is byte-identical to the old rule, and `2` unlocks the
already-enumerated 3x1 / 1x3 shapes. Nothing else in the optimizer moves —
the subset generator still caps each side at 3, so a 4-a-side package is
unreachable at ANY knob value (test 3).

The knob is read at call time through `trade_service._c`, never bound at
import — D-098 / G-058 cause 3. Section 4 holds both traps that guards:
one mutates the live config map of an ALREADY-IMPORTED trade_service and
requires the verdict to change (and walks the optimizer's AST to prove no
module-level statement snapshots the value); the other drives the knob
through `_cfg_override`, the thread-local overlay that `_c` honours and a
bare `_ts._cfg.get(...)` cannot see. That second one is not decoration:
`_cfg_override` is how the #189 relaxed pass and bake-off arm A's
`MODEL_A_PROFILE` apply knob values, so arm A's pin of this knob to 1.0
would silently no-op under a `_cfg.get` reader the moment prod flips the
row to 2 — and the golden would drift with no test red.

Fixtures
--------
Both pools are pinned to exactly the assets under test (`untouchable_ids`
removes the user's lineup bodies from the give pool, `not_interested_ids`
removes the opponent's from the receive pool), so the shape set the
optimizer can reach is small and fully determined. The sweetener passes
are disabled (`sweetener_max_cards` / `sweetener_gap_threshold` = 0)
because a sweetener ADDS an asset to a side and would change a card's
shape after the rule has already ruled on it.

Sabotage record (2026-08-23; each sabotage applied ALONE, and the file
restored between runs from a byte copy at /tmp/topt.c4v2 — NOT
`git checkout --`, the branch is uncommitted)
-----------------------------------------------------------------------
Baseline: `13 passed`.

1. **Reverted the rule to the literal** (`trade_optimizer.py:541`,
   `... > SHAPE_D:` -> `... > 1:`) -> `8 failed, 5 passed`::

       FAILED test_delta_2_admits_3_for_1              - assert '3x1' in ['2x1']
       FAILED test_delta_2_admits_1_for_3
       FAILED test_knob_accepts_the_float_the_db_stores
       FAILED test_no_side_ever_carries_four_assets[2]
       FAILED test_no_side_ever_carries_four_assets[3]
       FAILED test_no_side_ever_carries_four_assets[5]
       FAILED test_module_object_read_no_import_time_binding
       FAILED test_cfg_override_moves_the_verdict

   The five that stayed green are the ones that PIN today's behaviour
   (`test_delta_1_*`, `test_default_when_key_absent_*`,
   `test_no_side_ever_carries_four_assets[1]`,
   `test_knob_is_declared_in_default_cfg`) — they must survive a revert to
   the literal, because the literal is what the default means.

2. **Bound the knob at import time** (module-level
   `SHAPE_D = int(_c("v3_shape_max_delta"))` at `trade_optimizer.py:77`,
   the in-function read deleted) -> `8 failed, 5 passed`, the SAME eight.

   That identity is the finding, not a redundancy: an import-time binding
   is behaviourally indistinguishable from the literal it replaced, which
   is exactly why G-058 cause 3 goes unnoticed in review. The behavioural
   half of `test_module_object_read_no_import_time_binding` catches it
   without the AST walk; the AST half names the cause instead of leaving
   it to be diagnosed.

3. **Swapped `_c` for the overlay-blind reader** (`SHAPE_D  =
   int(_ts._cfg.get("v3_shape_max_delta", 1))` — the form the plan
   originally specified, before the key landed in `_DEFAULT_CFG`)
   -> `1 failed, 12 passed`::

       FAILED test_cfg_override_moves_the_verdict      - assert '3x1' in ['2x1']

   One test, and it is the whole reason that test exists. Every knob-value
   assertion in this file writes `ts._cfg` directly, so all twelve others
   are blind to the difference — and so is the live engine, until the day
   something applies this knob through `_cfg_override`. Two things do:
   the #189 relaxed pass, and bake-off arm A's `MODEL_A_PROFILE`, which
   pins this knob to 1.0 precisely so the prod flip to 2 cannot leak into
   the pre-wave arm. Under the `_cfg.get` reader that pin is a silent
   no-op and the arm-A golden drifts with nothing red.
"""

import ast
import inspect
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
import backend.trade_optimizer as topt
from backend.trade_optimizer import generate_pair_trades_v3
from backend.trade_service import LeagueMember, elo_to_value


# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None


#: A lineup-feasible base for either side: 1 QB, 2 RB, 2 WR, 1 TE.
_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix: str) -> dict[str, str]:
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    """All flags off except trade_engine.v2, pristine `_cfg`, both
    sweetener passes disabled. Restored afterwards."""
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    cache = dict(ff.DEFAULT_FLAGS)
    cache["trade_engine.v2"] = True
    ff._flags_cache = cache
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg["sweetener_max_cards"] = 0        # a sweetener changes shape
    ts._cfg["sweetener_gap_threshold"] = 0    # so does the gap sweetener
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _fixture(*, n_user_extra: int, n_opp_extra: int):
    """Rosters = lineup bodies + N tradeable WRs per side. Only the extras
    reach the pools (bodies are untouchable / not-interested)."""
    pos = {**_bodies("u"), **_bodies("o")}
    for i in range(1, n_user_extra + 1):
        pos[f"uX{i}"] = "WR"
    for i in range(1, n_opp_extra + 1):
        pos[f"oX{i}"] = "WR"
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in pos.items()}
    user_roster = list(_bodies("u")) + [f"uX{i}" for i in range(1, n_user_extra + 1)]
    opp_roster = list(_bodies("o")) + [f"oX{i}" for i in range(1, n_opp_extra + 1)]
    return pos, players, user_roster, opp_roster


def _shapes(pos, players, user_roster, opp_roster, user_elo, opp_elo, seed_elo,
            delta) -> list[str]:
    """Run one pair generation at `v3_shape_max_delta = delta`; return the
    distinct `GxR` shapes of the cards it emits."""
    ts._cfg["v3_shape_max_delta"] = delta
    cards = generate_pair_trades_v3(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value={p: elo_to_value(e) for p, e in user_elo.items()},
        user_roster=user_roster,
        opponent=LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                              elo_ratings=opp_elo, has_rankings=True),
        league_id="L1",
        seed_elo=seed_elo,
        confidence=None,
        max_cards=20,
        fairness_threshold=0.75,
        scoring_format="1qb_ppr",
        players=players,
        untouchable_ids=set(_bodies("u")),
        not_interested_ids=set(_bodies("o")),
    )
    return sorted({f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
                   for c in cards})


def _consolidation_fixture(n_mids: int = 3):
    """User sheds `n_mids` mid WRs the OPPONENT rates highly for one stud
    the USER rates highly — the 3-for-1 consolidation shape. Numbers found
    by grid search (/tmp probe, 2026-08-23): at the default knob this pair
    yields only the 2-for-1 sub-package; at 2 the full 3-for-1 clears every
    gate (surplus both sides, waiver cost, filler floor, Elo gap, fairness).
    """
    pos, players, user_roster, opp_roster = _fixture(
        n_user_extra=n_mids, n_opp_extra=1)
    mids = [f"uX{i}" for i in range(1, n_mids + 1)]
    stud = "oX1"
    user_elo = {p: 1500.0 for p in pos}
    user_elo.update({p: 1300.0 for p in mids})      # user is low on the mids
    user_elo[stud] = 1530.0                         # and high on the stud
    opp_elo = {p: 1500.0 for p in pos}
    opp_elo.update({p: 1520.0 for p in mids})       # opponent is the mirror
    opp_elo[stud] = 1480.0
    seed_elo = {p: 1500.0 for p in pos}
    seed_elo.update({p: 1400.0 for p in mids})
    seed_elo[stud] = 1600.0
    return pos, players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


def _split_fixture():
    """The exact mirror of `_consolidation_fixture` with the two managers'
    roles swapped: the user ships one stud for three mids (1-for-3)."""
    pos, players, user_roster, opp_roster = _fixture(
        n_user_extra=1, n_opp_extra=3)
    mids = [f"oX{i}" for i in (1, 2, 3)]
    stud = "uX1"
    user_elo = {p: 1500.0 for p in pos}
    user_elo.update({p: 1520.0 for p in mids})
    user_elo[stud] = 1480.0
    opp_elo = {p: 1500.0 for p in pos}
    opp_elo.update({p: 1300.0 for p in mids})
    opp_elo[stud] = 1530.0
    seed_elo = {p: 1500.0 for p in pos}
    seed_elo.update({p: 1400.0 for p in mids})
    seed_elo[stud] = 1600.0
    return pos, players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


# ---------------------------------------------------------------------------
# 1. Default (1) is the historical rule — 3x1 and 1x3 are rejected
# ---------------------------------------------------------------------------

def test_delta_1_rejects_3_for_1():
    shapes = _shapes(*_consolidation_fixture(), delta=1)
    assert shapes, "fixture must produce SOME card at the default knob"
    assert "3x1" not in shapes
    assert shapes == ["2x1"], shapes


def test_delta_1_rejects_1_for_3():
    shapes = _shapes(*_split_fixture(), delta=1)
    assert shapes, "fixture must produce SOME card at the default knob"
    assert "1x3" not in shapes
    assert shapes == ["1x2"], shapes


def test_default_when_key_absent_is_the_historical_rule():
    """A DB with no `v3_shape_max_delta` row (every deploy before the flip)
    must behave exactly as the literal `1` did — the inline default is what
    makes the code change byte-identical on merge."""
    ts._cfg.pop("v3_shape_max_delta", None)
    args = _consolidation_fixture()
    ts._cfg.pop("v3_shape_max_delta", None)
    cards_shapes = _shapes(*args, delta=1)          # writes the key
    ts._cfg.pop("v3_shape_max_delta", None)         # ...and take it away
    pos, players, ur, orr, ue, oe, se = args
    absent = generate_pair_trades_v3(
        user_id="user", shrunk_user_elo=ue,
        user_value={p: elo_to_value(e) for p, e in ue.items()},
        user_roster=ur,
        opponent=LeagueMember(user_id="opp", username="opp", roster=orr,
                              elo_ratings=oe, has_rankings=True),
        league_id="L1", seed_elo=se, confidence=None, max_cards=20,
        fairness_threshold=0.75, scoring_format="1qb_ppr", players=players,
        untouchable_ids=set(_bodies("u")),
        not_interested_ids=set(_bodies("o")))
    assert "v3_shape_max_delta" not in ts._cfg
    assert sorted({f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
                   for c in absent}) == cards_shapes


# ---------------------------------------------------------------------------
# 2. Delta 2 admits both directions
# ---------------------------------------------------------------------------

def test_delta_2_admits_3_for_1():
    shapes = _shapes(*_consolidation_fixture(), delta=2)
    assert "3x1" in shapes, shapes


def test_delta_2_admits_1_for_3():
    shapes = _shapes(*_split_fixture(), delta=2)
    assert "1x3" in shapes, shapes


def test_knob_accepts_the_float_the_db_stores():
    """`model_config.value` is a REAL column, so the live map hands the
    optimizer `2.0`, not `2`. The `int(...)` coercion is load-bearing."""
    shapes = _shapes(*_consolidation_fixture(), delta=2.0)
    assert "3x1" in shapes, shapes


# ---------------------------------------------------------------------------
# 3. The subset generator still caps each side at 3, at ANY knob value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("delta", [1, 2, 3, 5])
def test_no_side_ever_carries_four_assets(delta):
    """C4 moves the SHAPE bound only. `give_subsets`/`recv_subsets` are
    still built over sizes (1, 2, 3), so raising the knob past 2 buys
    nothing and a 4-a-side package stays unreachable — the enumeration
    cost of this change is bounded by construction, not by the knob."""
    pos, players, ur, orr, ue, oe, se = _consolidation_fixture(n_mids=4)
    ts._cfg["v3_shape_max_delta"] = delta
    cards = generate_pair_trades_v3(
        user_id="user", shrunk_user_elo=ue,
        user_value={p: elo_to_value(e) for p, e in ue.items()},
        user_roster=ur,
        opponent=LeagueMember(user_id="opp", username="opp", roster=orr,
                              elo_ratings=oe, has_rankings=True),
        league_id="L1", seed_elo=se, confidence=None, max_cards=20,
        fairness_threshold=0.75, scoring_format="1qb_ppr", players=players,
        untouchable_ids=set(_bodies("u")),
        not_interested_ids=set(_bodies("o")))
    assert cards, "fixture must stay alive at every knob value"
    assert len(ur) - len(_bodies("u")) == 4, "4 tradeable assets are in the pool"
    for c in cards:
        assert len(c.give_player_ids) <= 3, c.give_player_ids
        assert len(c.receive_player_ids) <= 3, c.receive_player_ids
    if delta >= 2:
        assert any(len(c.give_player_ids) == 3 for c in cards), \
            "delta >= 2 must actually reach the 3-asset give side"


# ---------------------------------------------------------------------------
# 4. D-098 / G-058 cause 3 — module-object read, no import-time binding
# ---------------------------------------------------------------------------

def test_module_object_read_no_import_time_binding():
    """The trap test. `backend.trade_optimizer` is already imported (it is
    imported at the top of this file and by every other test in the run).
    Writing the knob into `trade_service`'s LIVE config map — which is what
    `reload_config()` and `PUT /api/admin/config/<key>` both do — must
    change the optimizer's verdict with no reimport. A value bound into the
    optimizer's namespace at import time measures a perfect no-op."""
    args = _consolidation_fixture()

    ts._cfg["v3_shape_max_delta"] = 1
    before = _shapes(*args, delta=1)
    assert "3x1" not in before, before

    # The only thing that changes between the two calls: one dict write on
    # an already-imported module. No importlib.reload, no re-entry.
    ts._cfg["v3_shape_max_delta"] = 2
    after = _shapes(*args, delta=2)
    assert "3x1" in after, after

    # Structural half: no module-level statement in trade_optimizer.py may
    # mention the key. Every read has to sit inside a function body, so it
    # re-reads on every call.
    tree = ast.parse(inspect.getsource(topt))
    for node in tree.body:                       # module level only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Expr)):
            continue                              # bodies + the docstring
        assert "v3_shape_max_delta" not in ast.dump(node), (
            "v3_shape_max_delta is bound at module level in "
            "trade_optimizer.py — that freezes it at import (D-098)")

    # ...and it IS read inside the generator, on every call.
    src = inspect.getsource(generate_pair_trades_v3)
    assert "v3_shape_max_delta" in src

def test_cfg_override_moves_the_verdict():
    """The overlay trap. `_cfg_override` is a THREAD-LOCAL that `_c` reads
    before the live map; `_ts._cfg.get(...)` never consults it. Both the
    #189 relaxed pass and the bake-off arm profiles (including arm A's pin
    of this very knob) are applied that way, so a reader that misses the
    overlay turns those into silent no-ops.

    Sabotaging the read back to `int(_ts._cfg.get("v3_shape_max_delta", 1))`
    fails THIS test and nothing else in the file — which is precisely why it
    is here."""
    args = _consolidation_fixture()
    ts._cfg["v3_shape_max_delta"] = 1

    with ts._cfg_override({"v3_shape_max_delta": 2.0}):
        # NOTE: no `delta=` — the overlay is the only thing setting it.
        pos, players, ur, orr, ue, oe, se = args
        cards = generate_pair_trades_v3(
            user_id="user", shrunk_user_elo=ue,
            user_value={p: elo_to_value(e) for p, e in ue.items()},
            user_roster=ur,
            opponent=LeagueMember(user_id="opp", username="opp", roster=orr,
                                  elo_ratings=oe, has_rankings=True),
            league_id="L1", seed_elo=se, confidence=None, max_cards=20,
            fairness_threshold=0.75, scoring_format="1qb_ppr", players=players,
            untouchable_ids=set(_bodies("u")),
            not_interested_ids=set(_bodies("o")))
        shapes = sorted({f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}"
                         for c in cards})

    assert ts._cfg["v3_shape_max_delta"] == 1, "the overlay must not leak"
    assert "3x1" in shapes, shapes


def test_knob_is_declared_in_default_cfg():
    """`_c` raises `KeyError` for a key absent from `_DEFAULT_CFG`, so the
    declaration is load-bearing, not documentation. It is also what
    `test_bakeoff_arm_a_golden.test_no_generation_knob_was_added_without_an_arm_a_decision`
    keys off to force an arm-A disposition for every new generation knob."""
    assert "v3_shape_max_delta" in ts._DEFAULT_CFG
    assert ts._DEFAULT_CFG["v3_shape_max_delta"] == 1.0
