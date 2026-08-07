"""draft-extensions W2 — FTF-native mock draft engine + the calibration GATE.

Spec: ``docs/plans/draft-extensions/plan.md`` §5 · ``lld.md`` §2.3/§3.3/§4.2/§7 ·
``docs/plans/rookie-draft/mock-draft-plan.md`` §4-9.

  T-W2-01  flag off => every mock route 404s; no other route moves
  T-W2-02  snake vs linear turn order; the ownership overlay, incl. back-to-back
  T-W2-03  reach cap: exactly <= mock_max_reach_slots early, and never earlier
  T-W2-04  BPA persona: `jets` never deviates > 1 slot over 500 seeded draws
  T-W2-04b the W2b mixture: the reach branch is geometric in `reach_decay`,
           truncated by the candidate window, and persona-independent
  T-W2-05  determinism: same rng_seed => byte-identical draft; seeds differ
  T-W2-06  need-severity table: the §6.3 examples verbatim
  T-W2-07  persona precedence declared > inferred > not_sure
  T-W2-08  per-team need decrements after that team's pick (no RB triple-tap)
  T-W2-09  not_your_turn / player_unavailable
  T-W2-10  D7 in the mock pool: unvalued present, last, drafted only at the end
  T-W2-11  resume from the row => identical state; abandon => a fresh mock
  T-W2-12  not_rookie_draft; class-not-loaded typed-empty; NO draft object OK
  T-W2-13  ZERO platform egress after creation (fixture-seam counters)
  T-W2-14  CPU basis is consensus: a divergent user board changes nothing
  T-W2-15  ONE consensus definition: the pool IS _undrafted(basis=consensus)
  T-W2-16  THE CALIBRATION GATE — fit on rounds 1-2, hold out 3-4, both bars,
           then `mfl-complete` with NO refit. Re-run in W2b against the
           two-parameter mixture, and again in W2c against a re-derived
           consensus snapshot with the model and the gate FROZEN; still
           records a FAILURE (both mean bars; both KS bars pass).
  T-W2-17  corpus shape check before any corpus is used for calibration

T-W2-18 is a mobile Jest test and belongs to W2b.

Run: ``python3 -m pytest backend/tests/test_mock_draft.py``
"""

from __future__ import annotations

import ast
import collections
import csv
import json
import math
import pathlib
import random
import statistics

import pytest

import backend.draft_board_service as dbs
import backend.mock_draft_service as mds
from backend.data_loader import seed_elo_for_value

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
MODULE_PATH = pathlib.Path(mds.__file__)

LAKEVIEW_LEAGUE = "1312076055586050048"
LAKEVIEW_DRAFT = "1312076055594430464"

STANDARD_LINEUP = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX"]
SUPERFLEX_LINEUP = STANDARD_LINEUP + ["SUPER_FLEX"]


# ---------------------------------------------------------------------------
# Synthetic harness — a tiny, fully-controlled league
# ---------------------------------------------------------------------------

def make_ctx(*, players, rosters=None, lineup=None, season=2026,
             rostered=(), usernames=None) -> mds.MockContext:
    """`players` is [(player_id, position, elo|None)] in the order we want the
    consensus to rank them. `None` elo = the D7 unvalued tail."""
    rows, elo = {}, {}
    for pid, pos, value in players:
        rows[pid] = {"full_name": f"P{pid}", "position": pos, "team": "ARI",
                     "rookie_year": str(season), "search_rank": int(pid[1:])
                     if pid[1:].isdigit() else 999}
        if value is not None:
            elo[pid] = float(value)
    return mds.MockContext(
        league_id="L1", season=season, consensus_elo=elo,
        rookie_ids=frozenset(rows), player_rows=rows,
        rostered_ids=frozenset(rostered), rosters=rosters or {},
        lineup_slots=lineup or STANDARD_LINEUP,
        usernames=usernames or {},
    )


def linear_players(n: int, positions=("WR", "RB", "TE", "QB")) -> list[tuple]:
    """n players, strictly descending consensus value, positions cycling."""
    return [(f"p{i}", positions[i % len(positions)], 2000.0 - i)
            for i in range(1, n + 1)]


def make_state(ctx, *, owners, user, rounds=2, draft_type=mds.TYPE_LINEAR,
               ownership=None, personas=None, seed=7, bpa_prob=None,
               decay=None, reach=None):
    settings = mds.build_settings(
        ctx, owners=owners, user_owner_id=user, rounds=rounds,
        draft_type=draft_type, order=list(owners),
        order_source=mds.ORDER_SOURCE_ASSIGNED, ownership=ownership,
        personas=personas, rng=random.Random(seed))
    if bpa_prob is not None:
        settings["noise"]["bpa_prob"] = bpa_prob
    if decay is not None:
        settings["noise"]["reach_decay"] = decay
    if reach is not None:
        settings["noise"]["max_reach"] = reach
    return mds.new_state(ctx, settings, seed)


def run(state, ctx):
    return mds.advance_cpu(state, ctx, allow_unvalidated_model=True)


# ---------------------------------------------------------------------------
# T-W2-02 — turn order
# ---------------------------------------------------------------------------

def test_w2_02_linear_repeats_the_slot_order_every_round():
    slots = mds.pick_slots(rounds=3, teams=4, draft_type=mds.TYPE_LINEAR)
    assert [s["slot"] for s in slots] == [1, 2, 3, 4] * 3
    assert [s["pick_no"] for s in slots] == list(range(1, 13))


def test_w2_02_snake_reverses_even_rounds():
    slots = mds.pick_slots(rounds=3, teams=4, draft_type=mds.TYPE_SNAKE)
    assert [s["slot"] for s in slots] == [1, 2, 3, 4, 4, 3, 2, 1, 1, 2, 3, 4]


def test_w2_02_ownership_overlay_puts_the_right_roster_on_the_clock():
    ctx = make_ctx(players=linear_players(20))
    owners = ["a", "b", "c", "d"]
    state = make_state(ctx, owners=owners, user="zz", rounds=2,
                       ownership={2: "a", 3: "a"})
    run(state, ctx)
    by_pick = {p["pick_no"]: p["roster_id"] for p in state["picks"]}
    # a owns 1 (its slot), plus 2 and 3 by trade — three on the clock in a row.
    assert [by_pick[i] for i in (1, 2, 3, 4)] == ["a", "a", "a", "d"]


def test_w2_02_snake_numbering_never_changes_ownership():
    """The plan's execution-lens finding: the toggle moves slot NUMBERING
    only. Team `c` owns exactly one pick per round either way."""
    ctx = make_ctx(players=linear_players(20))
    owners = ["a", "b", "c", "d"]
    counts = []
    for draft_type in (mds.TYPE_LINEAR, mds.TYPE_SNAKE):
        state = make_state(ctx, owners=owners, user="zz", rounds=2,
                           draft_type=draft_type)
        run(state, ctx)
        counts.append(sum(1 for p in state["picks"] if p["roster_id"] == "c"))
    assert counts == [2, 2]


# ---------------------------------------------------------------------------
# T-W2-03 / T-W2-04 — the scoring function
# ---------------------------------------------------------------------------

def _candidates(positions):
    return [{"player_id": f"p{i}", "position": pos}
            for i, pos in enumerate(positions, start=1)]


#: "Noise off" under the W2b mixture: every pick takes the strict board pick,
#: so the NEED term is isolated and the §6.1 examples stay assertable verbatim.
NEED_ONLY = {"bpa_prob": 1.0, "reach_decay": mds.MOCK_REACH_DECAY_DEFAULT}


def test_w2_03_reach_cap_is_exact_and_never_exceeded():
    """The bonus is at most `need_weight x severity x max_reach` = 3.0 rank
    slots, so a needed player at rank r wins exactly while `r - 3 < 1`.

    r == 4 is the boundary and it LOSES: the scores tie at 1.0 and ties go to
    the better consensus rank (mock-draft-plan §6.1). So the cap is honoured
    from both sides — reached at 3 slots, never at 4.

    The NEED cap is a product cap and W2b did not touch it: the re-spec
    replaced the noise term only, so this test is unchanged apart from the
    spelling of "noise off"."""
    needs = {"RB": 1.0, "WR": 0.0}
    for rank, expected in ((2, "p2"), (3, "p3"), (4, "p1"), (5, "p1")):
        positions = ["WR"] * 8
        positions[rank - 1] = "RB"
        chosen = mds.cpu_pick(_candidates(positions), "championship", needs,
                              random.Random(0), max_reach=3.0, **NEED_ONLY)
        assert chosen == expected, f"needed RB at rank {rank} -> {chosen}"


def test_w2_03_persona_scales_the_reach_with_no_second_code_path():
    """The same board under three personas: only the weight changed."""
    board = _candidates(["WR", "WR", "RB", "WR", "WR", "WR", "WR", "WR"])
    needs = {"RB": 1.0, "WR": 0.0}
    picks = {p: mds.cpu_pick(board, p, needs, random.Random(0),
                             max_reach=3.0, **NEED_ONLY)
             for p in ("championship", "contender", "rebuilder", "jets")}
    assert picks["championship"] == "p3"        # 3 - 3.00 = 0.0 < 1
    assert picks["contender"] == "p3"           # 3 - 2.25 = 0.75 < 1
    assert picks["rebuilder"] == "p1"           # 3 - 0.75 = 2.25 > 1
    assert picks["jets"] == "p1"                # 3 - 0.30 = 2.70 > 1


def test_w2_04_jets_persona_is_bpa_within_one_slot_over_500_draws():
    """The persona knob governs the NEED reach, and `jets` gets none of it.

    W2b amendment, stated rather than hidden: under the mixture the
    idiosyncrasy branch is persona-INDEPENDENT (see the test below), because
    neither calibration corpus carries persona labels and there is therefore no
    evidence to condition it on. So this asserts what the persona knob actually
    owns — the need term — with the reach branch off. `jets` never deviates."""
    board = _candidates(["WR", "RB", "TE", "QB", "WR", "RB", "TE", "QB"])
    needs = {pos: 1.0 for pos in ("QB", "RB", "WR", "TE")}
    ranks = []
    for seed in range(500):
        chosen = mds.cpu_pick(board, "jets", needs, random.Random(seed),
                              max_reach=3.0, **NEED_ONLY)
        ranks.append(int(chosen[1:]))
    assert max(ranks) <= 2, f"jets deviated {max(ranks) - 1} slots from BPA"


# ---------------------------------------------------------------------------
# T-W2-04b — the W2b mixture's two branches, asserted separately
# ---------------------------------------------------------------------------

def _reach_draws(*, bpa_prob, decay, n=6000, outlook=mds.DEFAULT_OUTLOOK,
                 width=20):
    """`n` seeded picks off a flat, need-free board -> the reach depths."""
    board = _candidates(["WR"] * width)
    needs = {pos: 0.0 for pos in ("QB", "RB", "WR", "TE")}
    return [int(mds.cpu_pick(board, outlook, needs, random.Random(seed),
                             max_reach=3.0, bpa_prob=bpa_prob,
                             reach_decay=decay)[1:]) - 1
            for seed in range(n)]


def test_w2_04b_bpa_prob_is_exactly_the_mass_on_the_board_pick():
    """`bpa_prob = 1` is strict BPA; `bpa_prob = 0` never short-circuits."""
    assert set(_reach_draws(bpa_prob=1.0, decay=0.9, n=500)) == {0}
    reaching = _reach_draws(bpa_prob=0.0, decay=0.9, n=2000)
    assert max(reaching) > 5, "the reach branch never leaves the board pick"


def test_w2_04b_the_reach_branch_is_geometric_in_reach_decay():
    """The Gumbel-max identity, verified rather than asserted in prose.

    An argmin over `rank - Gumbel(0, beta)` is a softmax over `-rank`, so the
    reach depth is geometric with per-slot ratio `reach_decay`. Checked as the
    ratio of successive frequencies over the head of the distribution, where
    the window truncation has not yet bitten.
    """
    for decay in (0.5, 0.7):
        draws = _reach_draws(bpa_prob=0.0, decay=decay, n=20000)
        hist = collections.Counter(draws)
        for d in range(4):
            ratio = hist[d + 1] / hist[d]
            assert abs(ratio - decay) < 0.06, (
                f"decay={decay}: P({d+1})/P({d}) = {ratio:.3f}")


def test_w2_04b_the_candidate_window_truncates_the_tail_and_is_not_fitted():
    """`K` is a product cap applied by the ENGINE, not by the scoring function:
    no CPU pick can land beyond it at ANY parameter, including the degenerate
    flat branch on a board 6x wider than the window."""
    window = mds.candidate_window(mds.MOCK_MAX_REACH_DEFAULT)
    assert window == mds.MOCK_CANDIDATE_WINDOW
    # Unwindowed, the flat branch reaches far past K — so the cap is real work.
    assert max(_reach_draws(bpa_prob=0.0, decay=0.999, n=2000, width=72)) > window

    ctx = make_ctx(players=linear_players(80))
    state = make_state(ctx, owners=["a", "b"], user="zz", rounds=8,
                       bpa_prob=0.0, decay=0.999)
    run(state, ctx)
    assert max(mds.reach_series([p["player_id"] for p in state["picks"]],
                                mds.consensus_pool(ctx))) < window


def test_w2_04b_the_reach_branch_is_persona_independent():
    """Stated explicitly so nobody later reads persona-scaled idiosyncrasy into
    the model: with needs zeroed, every persona draws the same reach law."""
    by_persona = {outlook: _reach_draws(bpa_prob=0.0, decay=0.9, n=1500,
                                        outlook=outlook)
                  for outlook in ("championship", "rebuilder", "jets")}
    assert len(set(tuple(v) for v in by_persona.values())) == 1


# ---------------------------------------------------------------------------
# T-W2-06 — need severity (mock-draft-plan §6.3, verbatim)
# ---------------------------------------------------------------------------

def test_w2_06_slot_targets_read_the_league_template():
    one_qb = mds.slot_targets(STANDARD_LINEUP)
    assert one_qb["QB"] == (1, 0)          # 1QB league: no QB bench target
    assert one_qb["RB"] == (2, 1)
    assert one_qb["WR"] == (3, 1)
    assert one_qb["TE"] == (1, 0)          # TE never gets a bench target
    superflex = mds.slot_targets(SUPERFLEX_LINEUP)
    assert superflex["QB"] == (1, 1)       # B(QB) = 1 iff superflex
    # FLEX is excluded from S (v1, O-M5) — it is not a dedicated slot.
    assert one_qb["RB"][0] == 2


def test_w2_06_severity_examples_verbatim():
    targets = mds.slot_targets(STANDARD_LINEUP)
    assert mds.severity({"RB": 0}, targets, "RB") == 1.0          # (2+1-0)/3
    assert mds.severity({"RB": 2}, targets, "RB") == pytest.approx(1 / 3)
    assert mds.severity({"QB": 1}, targets, "QB") == 0.0          # 1QB with a QB
    assert mds.severity({"RB": 9}, targets, "RB") == 0.0          # clamped at 0


def test_w2_06_viable_floor_ignores_roster_clogging_depth():
    ctx = make_ctx(players=[("p1", "RB", 1900.0), ("p2", "RB", 1200.0)])
    counts = mds.positional_needs(["p1", "p2"], STANDARD_LINEUP,
                                  ctx.consensus_elo, ctx.player_rows)
    assert counts["RB"] == 1, "a sub-1280 body must not count as viable"


def test_w2_06_one_qb_league_never_reaches_for_a_qb():
    """Emergent from the template, not special-cased: S+B == 1 and the team
    has a viable QB, so severity is 0 and the QB gets no bonus at all."""
    targets = mds.slot_targets(STANDARD_LINEUP)
    assert mds.severity({"QB": 1}, targets, "QB") == 0.0
    assert mds.severity({"QB": 1}, mds.slot_targets(SUPERFLEX_LINEUP), "QB") == 0.5


# ---------------------------------------------------------------------------
# T-W2-07 — persona precedence
# ---------------------------------------------------------------------------

def test_w2_07_persona_precedence_declared_beats_inferred_beats_default():
    ctx = make_ctx(players=linear_players(8))
    settings = mds.build_settings(
        ctx, owners=["a", "b", "c"], user_owner_id="a",
        personas={"a": {"outlook": "championship", "source": mds.PERSONA_DECLARED},
                  "b": {"outlook": "rebuilder", "source": mds.PERSONA_INFERRED}},
        rng=random.Random(1))
    personas = settings["personas"]
    assert personas["a"] == {"outlook": "championship", "source": "declared"}
    assert personas["b"] == {"outlook": "rebuilder", "source": "inferred"}
    assert personas["c"] == {"outlook": "not_sure", "source": "default"}


def test_w2_07_need_weight_is_the_shipped_outlook_alpha_map():
    from backend.trade_service import outlook_alpha
    for outlook in ("championship", "contender", "not_sure", "rebuilder",
                    "jets", None, "nonsense"):
        assert mds.need_weight(outlook) == outlook_alpha(outlook)


def test_w2_07_inference_never_yields_an_extreme_label():
    """`infer_team_outlook`'s stated design: the extremes stay reserved for
    self-declaration, so no inferred persona can ever be a 1.0/0.1 drafter."""
    from backend.trade_service import infer_team_outlook
    src = pathlib.Path(infer_team_outlook.__code__.co_filename).read_text()
    body = src[src.index("def infer_team_outlook"):]
    body = body[:body.index("\ndef build_match_context")]
    returned = {n.value for n in ast.walk(ast.parse(body.replace("\n", "\n", 1)
                                                    if False else body))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "championship" not in returned and "jets" not in returned


# ---------------------------------------------------------------------------
# T-W2-08 — needs decrement as a team drafts
# ---------------------------------------------------------------------------

def test_w2_08_a_team_does_not_triple_tap_one_position():
    """Team `a` starts with zero viable RBs (severity 1.0) and owns picks 1-3.
    After one RB its severity drops to 2/3, after two to 1/3 — so with the
    board stacked RB-first it still cannot take three."""
    players = [("p1", "WR", 2000.0), ("p2", "RB", 1990.0), ("p3", "RB", 1980.0),
               ("p4", "RB", 1970.0), ("p5", "WR", 1960.0), ("p6", "WR", 1950.0),
               ("p7", "TE", 1940.0), ("p8", "QB", 1930.0)]
    ctx = make_ctx(players=players, rosters={"a": [], "b": [], "c": [], "d": []})
    state = make_state(ctx, owners=["a", "b", "c", "d"], user="zz", rounds=1,
                       ownership={2: "a", 3: "a"},
                       personas={"a": {"outlook": "championship",
                                       "source": "declared"}},
                       bpa_prob=1.0)
    run(state, ctx)
    a_positions = [ctx.player_rows[p["player_id"]]["position"]
                   for p in state["picks"] if p["roster_id"] == "a"]
    assert a_positions.count("RB") <= 2, a_positions


# ---------------------------------------------------------------------------
# T-W2-05 — determinism
# ---------------------------------------------------------------------------

def test_w2_05_same_seed_is_byte_identical():
    ctx = make_ctx(players=linear_players(40))
    owners = ["a", "b", "c", "d"]
    runs = []
    for _ in range(2):
        state = make_state(ctx, owners=owners, user="zz", rounds=4, seed=99)
        run(state, ctx)
        runs.append(mds.dumps(state)[1])
    assert runs[0] == runs[1]


def test_w2_05_different_seeds_differ():
    ctx = make_ctx(players=linear_players(40))
    owners = ["a", "b", "c", "d"]
    bodies = set()
    for seed in range(12):
        state = make_state(ctx, owners=owners, user="zz", rounds=4, seed=seed,
                           bpa_prob=0.0)
        run(state, ctx)
        bodies.add(mds.dumps(state)[1])
    assert len(bodies) > 1, "seeds must produce statistically different drafts"


def test_w2_05_per_pick_rng_is_a_function_of_seed_and_pick_only():
    """Resume replays identically because the stream never depends on call
    order — the property that makes a backgrounded app safe."""
    state = {"rng_seed": 4242}
    assert [mds._pick_rng(state, n).random() for n in (1, 2, 3)] == \
           [mds._pick_rng(state, n).random() for n in (3, 2, 1)][::-1]


# ---------------------------------------------------------------------------
# T-W2-09 / T-W2-10 — user picks and the D7 tail
# ---------------------------------------------------------------------------

def test_w2_09_not_your_turn_and_player_unavailable():
    ctx = make_ctx(players=linear_players(20))
    state = make_state(ctx, owners=["a", "b", "c", "d"], user="b", rounds=2)
    run(state, ctx)
    assert mds.next_pick(state)["is_user"] is True
    taken = {p["player_id"] for p in state["picks"]}
    with pytest.raises(mds.PlayerUnavailable):
        mds.apply_user_pick(state, ctx, sorted(taken)[0])
    with pytest.raises(mds.PlayerUnavailable):
        mds.apply_user_pick(state, ctx, "not-a-player")
    free = next(r["player_id"] for r in mds._available(ctx, state))
    mds.apply_user_pick(state, ctx, free)
    # It is now a CPU's turn again (advance_cpu ran) or the draft is done.
    slot = mds.next_pick(state)
    assert slot is None or slot["is_user"] is True


def test_w2_09_already_rostered_players_are_unavailable():
    ctx = make_ctx(players=linear_players(12), rostered=("p1",))
    state = make_state(ctx, owners=["a", "b"], user="a", rounds=1)
    available = {r["player_id"] for r in mds._available(ctx, state)}
    assert "p1" not in available


def test_w2_09_a_completed_mock_refuses_another_pick():
    ctx = make_ctx(players=linear_players(12))
    state = make_state(ctx, owners=["a", "b"], user="zz", rounds=1)
    run(state, ctx)
    assert state["status"] == mds.STATUS_COMPLETE
    with pytest.raises(mds.NotYourTurn):
        mds.apply_user_pick(state, ctx, "p9")


def test_w2_10_unvalued_rookies_are_present_last_and_drafted_only_at_the_end():
    players = [("p1", "WR", 2000.0), ("p2", "RB", 1990.0),
               ("p3", "TE", None), ("p4", "QB", None)]
    ctx = make_ctx(players=players)
    pool = mds.consensus_pool(ctx)
    assert [r["player_id"] for r in pool] == ["p1", "p2", "p3", "p4"]
    assert [r["valued"] for r in pool] == [True, True, False, False]
    state = make_state(ctx, owners=["a", "b"], user="zz", rounds=2, bpa_prob=1.0)
    run(state, ctx)
    order = [p["player_id"] for p in state["picks"]]
    assert order[:2] == ["p1", "p2"], "the valued pool must exhaust first"


# ---------------------------------------------------------------------------
# T-W2-14 / T-W2-15 — ONE consensus definition (amendment 1)
# ---------------------------------------------------------------------------

def test_w2_15_the_mock_pool_is_undrafted_basis_consensus_element_for_element():
    ctx = make_ctx(players=linear_players(30))
    expected, loaded = dbs._undrafted(2026, set(), set(), dbs.BASIS_CONSENSUS,
                                      None, ctx.consensus_elo, ctx.fetchers())
    assert loaded
    assert mds.consensus_pool(ctx) == expected


def test_w2_15_removal_equals_recomputation():
    """Consuming the pool by removal is exactly recomputing it per pick — the
    sort key is per-row, so deletions never reorder the survivors."""
    ctx = make_ctx(players=linear_players(30))
    state = make_state(ctx, owners=["a", "b", "c"], user="zz", rounds=3)
    run(state, ctx)
    taken = {p["player_id"] for p in state["picks"]}
    recomputed, _ = dbs._undrafted(2026, taken, set(), dbs.BASIS_CONSENSUS,
                                   None, ctx.consensus_elo, ctx.fetchers())
    assert mds._available(ctx, state) == recomputed


def test_w2_14_a_wildly_divergent_user_board_changes_no_cpu_pick():
    ctx = make_ctx(players=linear_players(30))
    owners = ["a", "b", "c"]
    baseline = make_state(ctx, owners=owners, user="zz", rounds=3, seed=5)
    run(baseline, ctx)

    inverted = {f"p{i}": float(i) for i in range(1, 31)}     # exactly backwards
    other = make_state(ctx, owners=owners, user="zz", rounds=3, seed=5)
    run(other, ctx)
    assert mds.dumps(baseline)[1] == mds.dumps(other)[1]

    # …and the payload's own undrafted list DOES flip under basis=my_board,
    # proving the board was live and simply never reached a CPU decision.
    consensus = mds.state_payload(baseline, ctx)["undrafted"]
    my_board = mds.state_payload(baseline, ctx, basis=dbs.BASIS_MY_BOARD,
                                 board_elo=inverted)["undrafted"]
    assert [r["player_id"] for r in consensus] != [r["player_id"] for r in my_board]


def test_w2_14_the_service_declares_no_second_consensus():
    """VFF-style: the module must not build its own ordering. The only sort of
    the candidate pool anywhere in this file is inside `_reranked`, which
    preserves the order `_undrafted` produced."""
    tree = ast.parse(MODULE_PATH.read_text())
    sorts = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and ((isinstance(n.func, ast.Name) and n.func.id == "sorted")
                  or (isinstance(n.func, ast.Attribute) and n.func.attr == "sort"))]
    assert sorts == [], "a second consensus ordering appeared in mock_draft_service"


# ---------------------------------------------------------------------------
# T-W2-11 — resume
# ---------------------------------------------------------------------------

def test_w2_11_resume_from_the_row_is_identical():
    ctx = make_ctx(players=linear_players(40))
    state = make_state(ctx, owners=["a", "b", "c", "d"], user="b", rounds=4,
                       seed=31)
    run(state, ctx)
    settings_json, picks_json = mds.dumps(state)
    rehydrated = mds.loads({"id": 1, "user_id": "b", "league_id": "L1",
                            "season": 2026, "status": state["status"],
                            "settings": settings_json, "picks": picks_json,
                            "rng_seed": 31})
    assert mds.next_pick(rehydrated) == mds.next_pick(state)

    free = next(r["player_id"] for r in mds._available(ctx, state))
    mds.apply_user_pick(state, ctx, free)
    mds.apply_user_pick(rehydrated, ctx, free)
    assert mds.dumps(state)[1] == mds.dumps(rehydrated)[1]


def test_w2_11_the_row_snapshots_its_own_noise_parameters():
    """A resumed mock replays at ITS fitted noise even if model_config moved."""
    ctx = make_ctx(players=linear_players(10))
    settings = mds.build_settings(ctx, owners=["a"], user_owner_id="a",
                                  config_overrides={"mock_bpa_prob": 0.25,
                                                    "mock_reach_decay": 0.75,
                                                    "mock_max_reach_slots": 4.0},
                                  rng=random.Random(0))
    assert settings["noise"] == {"bpa_prob": 0.25, "reach_decay": 0.75,
                                 "max_reach": 4.0}


# ---------------------------------------------------------------------------
# T-W2-13 — zero platform egress (structural)
# ---------------------------------------------------------------------------

_EGRESS_MODULES = {"urllib", "urllib.request", "http", "http.client", "socket",
                   "requests", "ssl"}
_EGRESS_SIBLINGS = {"sleeper_write", "mfl_service", "espn_service",
                    "fleaflicker_service"}


def test_w2_13_the_engine_imports_nothing_that_can_reach_a_platform():
    tree = ast.parse(MODULE_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {a.name for a in node.names}
    assert not (imported & _EGRESS_MODULES), imported & _EGRESS_MODULES
    assert not (imported & _EGRESS_SIBLINGS), imported & _EGRESS_SIBLINGS


def test_w2_13_no_fetcher_the_engine_builds_can_reach_upstream():
    """`MockContext.fetchers()` binds no `sleeper_get` and no `mfl_opener`, so
    a stray platform read raises instead of going live (the T-M1-01 stance)."""
    ctx = make_ctx(players=linear_players(4))
    f = ctx.fetchers()
    assert f.sleeper_get is None and f.mfl_opener is None
    with pytest.raises(RuntimeError):
        f.drafts("whatever")


def test_w2_13_a_full_mock_runs_with_the_test_mode_counters_untouched():
    from backend import test_support
    import backend.server as server

    before = dict(test_support.counters)
    saved_mode = server._TEST_MODE
    server._TEST_MODE = True
    try:
        ctx = make_ctx(players=linear_players(40))
        state = make_state(ctx, owners=["a", "b", "c", "d"], user="b", rounds=4)
        run(state, ctx)
        free = next(r["player_id"] for r in mds._available(ctx, state))
        mds.apply_user_pick(state, ctx, free)
        mds.state_payload(state, ctx)
    finally:
        server._TEST_MODE = saved_mode
    assert test_support.counters == before, "the mock caused platform egress"


# ---------------------------------------------------------------------------
# T-W2-12 — create-path states
# ---------------------------------------------------------------------------

def test_w2_12_class_not_loaded_is_typed_empty():
    ctx = make_ctx(players=[])
    assert mds.class_loaded(ctx) is False
    assert mds.empty_payload(mds.REASON_CLASS_NOT_LOADED) == {
        "schema": 1, "empty": True, "reason": "class_not_loaded"}


def test_w2_12_rounds_are_clamped_to_the_rookie_ceiling():
    ctx = make_ctx(players=linear_players(4))
    settings = mds.build_settings(ctx, owners=["a"], user_owner_id="a",
                                  rounds=99, rng=random.Random(0))
    assert settings["rounds"] == mds._ROOKIE_MAX_ROUNDS


def test_w2_12_no_draft_object_yields_a_randomized_and_labelled_order():
    """O-M7: a league with no platform draft is the PRIMARY mock case. The
    order is randomized and SAID to be randomized — never an invented one."""
    ctx = make_ctx(players=linear_players(4))
    settings = mds.build_settings(ctx, owners=["a", "b", "c", "d"],
                                  user_owner_id="a", rng=random.Random(3))
    assert settings["order_source"] == mds.ORDER_SOURCE_RANDOMIZED
    assert sorted(settings["order"]) == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# The abort criterion, expressed in code
# ---------------------------------------------------------------------------

def test_the_calibration_gate_blocks_cpu_generation_from_the_routes():
    ctx = make_ctx(players=linear_players(10))
    state = make_state(ctx, owners=["a", "b"], user="a", rounds=1)
    with pytest.raises(mds.CalibrationGateClosed):
        mds.advance_cpu(state, ctx)             # the routes' call — no opt-in


def test_the_artifact_the_gate_points_at_exists_and_states_a_verdict():
    repo = pathlib.Path(__file__).resolve().parents[2]
    artifact = repo / mds.CALIBRATION_ARTIFACT
    assert artifact.exists(), f"the I-10 gate artifact is missing: {artifact}"
    text = artifact.read_text()
    assert "VERDICT" in text
    for token in ("mock_bpa_prob", "mock_reach_decay", "Wasserstein", "KS",
                  "lakeview-complete", "mfl-complete"):
        assert token in text, f"the artifact never states {token}"


# ===========================================================================
# T-W2-01 — the route shims
#
# Everything above drives the engine directly. These drive Flask, because
# three things belong to the SHIM and cannot be asserted at the service
# layer: the `draft.mock` gate, session/league resolution, and the abort
# criterion's typed-empty answer.
# ===========================================================================

import backend.feature_flags as ff                             # noqa: E402
import backend.server as server                                # noqa: E402
from backend.ranking_service import Player, RankingService     # noqa: E402
from backend.trade_service import League, LeagueMember         # noqa: E402

ROUTE = "/api/mock-draft"
ROUTE_TOKEN = "test-token-w2-01"
OPERATOR = "313560442465169408"


def _pin_flags(**overrides) -> dict:
    """The repo's flag-pinning idiom (there is no conftest.py)."""
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, **overrides}
    return saved


@pytest.fixture()
def flag_off():
    saved = _pin_flags()
    try:
        yield
    finally:
        ff._flags_cache = saved


@pytest.fixture()
def flag_on():
    saved = _pin_flags(**{"draft.room": True, "draft.mock": True})
    try:
        yield
    finally:
        ff._flags_cache = saved


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


@pytest.fixture()
def session(monkeypatch):
    pool = [Player(id="p1", name="Rookie One", position="WR", team="ARI", age=22)]
    service = RankingService(players=pool)
    league = League(league_id=LAKEVIEW_LEAGUE, name="Lakeview", platform="sleeper",
                    members=[LeagueMember(user_id=OPERATOR, username="op",
                                          roster=[], elo_ratings={})])
    sess = {"user_id": OPERATOR, "league": league, "players": pool,
            "services": {"1qb_ppr": service}, "service": service,
            "trade_svc": object(), "active_format": "1qb_ppr", "last_active": 0.0}
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (pool, {"p1": 1500.0}))
    monkeypatch.setattr(server, "_rookie_player_ids", lambda season: {"p1"})
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "sleeper", "season": 2026})
    monkeypatch.setattr(server, "_sleeper_lineup_slots", lambda lid: STANDARD_LINEUP)
    monkeypatch.setattr(dbs, "database_players",
                        lambda ids: {"p1": {"full_name": "Rookie One",
                                            "position": "WR", "team": "ARI",
                                            "rookie_year": "2026",
                                            "search_rank": 1}})
    with server._sessions_lock:
        server._sessions[ROUTE_TOKEN] = sess
    try:
        yield sess
    finally:
        with server._sessions_lock:
            server._sessions.pop(ROUTE_TOKEN, None)


def _post(client, path=ROUTE, **body):
    return client.post(path, json=body, headers={"X-Session-Token": ROUTE_TOKEN})


def test_w2_01_flag_off_404s_every_mock_route(client, flag_off, session):
    for call in (lambda: client.get(ROUTE, headers={"X-Session-Token": ROUTE_TOKEN}),
                 lambda: _post(client, league_id=LAKEVIEW_LEAGUE),
                 lambda: _post(client, ROUTE + "/pick", mock_id=1, player_id="p1"),
                 lambda: _post(client, ROUTE + "/abandon", mock_id=1)):
        resp = call()
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "feature_disabled"}


def test_w2_01_the_gate_precedes_any_session_work(client, flag_off):
    """No token at all still gets the 404 — an unauthenticated probe learns
    nothing about the session or the league."""
    resp = client.post(ROUTE, json={})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "feature_disabled"}


def test_w2_01_flag_off_changes_no_other_route(client):
    """D10: a neighbouring unflagged route answers byte-identically with
    `draft.mock` off and on."""
    saved = ff._flags_cache
    try:
        _pin_flags()
        off = client.get("/api/tier-config")
        off_body = off.get_data()
        _pin_flags(**{"draft.mock": True, "draft.room": True})
        on = client.get("/api/tier-config")
        assert (on.status_code, on.get_data()) == (off.status_code, off_body)
    finally:
        ff._flags_cache = saved


def test_w2_01_flag_on_without_a_session_is_401(client, flag_on):
    assert client.post(ROUTE, json={"league_id": LAKEVIEW_LEAGUE}).status_code == 401


def test_w2_01_unknown_league_is_404(client, flag_on, session, monkeypatch):
    monkeypatch.setattr(server, "get_league_draft_context", lambda lid: None)
    resp = _post(client, league_id="9999999999")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "league_not_found"}


def test_w2_01_bad_basis_is_400(client, flag_on, session):
    resp = client.get(f"{ROUTE}?league_id={LAKEVIEW_LEAGUE}&basis=vibes",
                      headers={"X-Session-Token": ROUTE_TOKEN})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad_basis"}


def test_w2_12_route_rejects_a_startup_shaped_round_count(client, flag_on, session):
    resp = _post(client, league_id=LAKEVIEW_LEAGUE, rounds=28)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "not_rookie_draft"}


def test_w2_12_route_serves_the_typed_empty_when_the_class_is_not_loaded(
        client, flag_on, session, monkeypatch):
    monkeypatch.setattr(server, "_rookie_player_ids", lambda season: set())
    resp = _post(client, league_id=LAKEVIEW_LEAGUE)
    assert resp.status_code == 200
    assert resp.get_json() == {"schema": 1, "empty": True,
                               "reason": "class_not_loaded"}


def test_the_abort_criterion_is_enforced_at_the_route(client, flag_on, session):
    """W2's abort criterion, end to end: even with the flag ON, creating a mock
    answers the typed-empty rather than serving unvalidated bots. The reason
    rides the EXISTING typed-empty contract, so no closed client enum moves."""
    assert mds.CPU_MODEL_VALIDATED is False
    resp = _post(client, league_id=LAKEVIEW_LEAGUE)
    assert resp.status_code == 200
    assert resp.get_json() == {"schema": 1, "empty": True,
                               "reason": "cpu_model_unvalidated"}


def test_get_with_no_mock_is_a_typed_empty_not_a_404(client, flag_on, session):
    resp = client.get(f"{ROUTE}?league_id={LAKEVIEW_LEAGUE}",
                      headers={"X-Session-Token": ROUTE_TOKEN})
    assert resp.status_code == 200
    assert resp.get_json()["empty"] is True


def test_pick_and_abandon_reject_a_mock_that_is_not_the_callers(
        client, flag_on, session):
    assert _post(client, ROUTE + "/pick", mock_id=999999,
                 player_id="p1").status_code == 404
    assert _post(client, ROUTE + "/abandon", mock_id=999999).status_code == 404


# ---------------------------------------------------------------------------
# T-W2-11 (persistence half) — the store round-trips and enforces one active
# ---------------------------------------------------------------------------

def test_w2_11_only_one_active_mock_survives_per_user_and_league():
    from backend.database import (create_mock_draft, load_current_mock_draft,
                                  load_mock_draft, update_mock_draft)
    user, league = "u-w2-11", "L-w2-11"
    first = create_mock_draft(user, league, 2026, '{"rounds": 4}', "[]", 11)
    second = create_mock_draft(user, league, 2026, '{"rounds": 4}', "[]", 12)
    assert load_mock_draft(first)["status"] == "abandoned"
    current = load_current_mock_draft(user, league)
    assert current["id"] == second and current["status"] == "active"

    assert update_mock_draft(second, user, picks_json='[{"pick_no": 1}]',
                             status="complete") is True
    assert json.loads(load_mock_draft(second)["picks"]) == [{"pick_no": 1}]
    # Owner-scoped: another user cannot touch or read the row.
    assert update_mock_draft(second, "someone-else", status="active") is False
    assert load_mock_draft(second, "someone-else") is None
    # A completed mock is what GET falls back to for the recap.
    assert load_current_mock_draft(user, league)["id"] == second


# ===========================================================================
# T-W2-16 / T-W2-17 — THE CALIBRATION GATE (I-10, lld §4.2.3)
# ===========================================================================
# The engine's simulator (`mds.simulate_reaches` -> the SHIPPED `cpu_pick`)
# supplies the model side; everything below is the statistics and the corpus
# plumbing. `FIT_BLOCK` is fitted, `HOLDOUT_BLOCK` is only ever validated —
# separating them is the entire point of amendment 2.

# The W2b grid, declared over each parameter's NATURAL domain rather than a
# hand-picked interval — that is what makes "the optimum is interior" mean
# something. `bpa_prob` is a probability; `reach_decay` is a survival ratio in
# (0, 1), with 0.95/0.99 appended because the interesting region of a geometric
# ratio compresses against 1.
BPA_GRID = [round(0.1 * k, 2) for k in range(0, 10)]         # [0.00 … 0.90]
DECAY_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
FIXED_MAX_REACH = 3.0                                        # a product cap, not fitted
FIT_SIMS = 1000         # per grid point (lld §4.2.3 step 2)
VALIDATE_SIMS = 1000
KS_ALPHA = 0.05
MEAN_BAR = 1.0


def _wasserstein1(a, b) -> float:
    """1-D Wasserstein distance between two empirical samples."""
    a, b = sorted(a), sorted(b)
    grid = sorted(set(a) | set(b))
    total = 0.0
    for lo, hi in zip(grid, grid[1:]):
        fa = sum(1 for x in a if x <= lo) / len(a)
        fb = sum(1 for x in b if x <= lo) / len(b)
        total += abs(fa - fb) * (hi - lo)
    return total


def _ks_two_sample(a, b) -> tuple[float, float]:
    """`(D, p)` — the two-sample Kolmogorov-Smirnov statistic and its
    asymptotic p-value. No SciPy in this repo, so the standard
    Q_KS series is inlined."""
    a, b = sorted(a), sorted(b)
    n1, n2 = len(a), len(b)
    grid = sorted(set(a) | set(b))
    d = max(abs(sum(1 for x in a if x <= t) / n1 - sum(1 for x in b if x <= t) / n2)
            for t in grid)
    en = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d
    p = 2.0 * sum((-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
                  for k in range(1, 101))
    return d, max(0.0, min(1.0, p))


# ── corpus plumbing ──────────────────────────────────────────────────────

def _fixture_pool() -> dict:
    return json.loads((FIXTURES / "player_pool_2026.json").read_text())["players"]


def _rookie_universe() -> dict:
    """The 2026 prospect class — `rookie_universe_2026.json` (W2c).

    W2a/W2b ranked the corpora against `player_pool_2026.json`, which is a
    *UI-seeder* cut: top-N per POSITION across all players by `value_1qb`, so
    it keeps 56 of these 290 prospects and floors their deep tail at repeated
    DP values. A rookie draft's late picks were therefore measured against a
    censored board whose tail order was a `search_rank` tiebreak. This fixture
    is the whole prospect class; the VALUES come from the live snapshot below.
    """
    return json.loads((FIXTURES / "rookie_universe_2026.json").read_text())["players"]


def _mfl_to_sleeper() -> dict[str, str]:
    out: dict[str, str] = {}
    with open(FIXTURES / "dp_playerids_snapshot_2026-07-11.csv") as fh:
        for row in csv.DictReader(fh):
            mfl, sleeper = (row.get("mfl_id") or "").strip(), (row.get("sleeper_id") or "").strip()
            if mfl and sleeper:
                out.setdefault(mfl, sleeper)
    return out


_BLENDED_CACHE: dict[str, dict[str, float]] = {}


def _blended_values(fmt: str) -> dict[str, float]:
    """{normalised name: consensus value} for `fmt`, from the LIVE snapshot.

    The W2c correction. Inputs are `ktc_blend_pipeline_2026-07-17.json` — the
    untrimmed 2026-07-17 DynastyProcess `values-players.csv` (633 players per
    format) plus the 441 matched KeepTradeCut rows — and the arithmetic is the
    SHIPPED `data_loader._apply_consensus_blend` at the shipped default weight,
    so this is the same consensus `_get_universal_pool` serves the product, not
    a second opinion. `_blend_config` is pinned rather than read from
    `model_config` so the gate cannot move when an operator retunes the blend.
    """
    if fmt not in _BLENDED_CACHE:
        import backend.data_loader as dl
        pipe = json.loads((FIXTURES / "ktc_blend_pipeline_2026-07-17.json").read_text())
        value_map = {k: float(v) for k, v in pipe["dp"][fmt].items()}
        elo_map = {k: round(seed_elo_for_value(v), 1) for k, v in value_map.items()}
        ktc, cfg = dl._ktc_consensus, dl._blend_config
        dl._ktc_consensus = lambda: pipe["ktc"]
        dl._blend_config = lambda: (dl.KTC_BLEND_WEIGHT_DEFAULT, dl.TEP_TE_UPLIFT_DEFAULT)
        try:
            _elo, blended = dl._apply_consensus_blend(
                fmt, elo_map, value_map, dict(pipe["dp_pos"]))
        finally:
            dl._ktc_consensus, dl._blend_config = ktc, cfg
        _BLENDED_CACHE[fmt] = blended
    return _BLENDED_CACHE[fmt]


def _rookie_ctx(fmt: str, *, pre_rostered=frozenset(),
                lineup=STANDARD_LINEUP) -> mds.MockContext:
    """A `MockContext` whose consensus is the live-shaped snapshot (W2c).

    Membership is the full prospect class RESTRICTED TO THE PLAYERS THE
    CONSENSUS VALUES — the name join is `normalise_name(full_name) in values`,
    which is `server.build_universal_pool`'s join verbatim. A prospect the
    consensus prices at nothing carries no opinion to reach past, so his rank
    inside the unvalued block would be alphabetical order rather than a
    reach; `reach_report` counts every such pick as `skipped` and the artifact
    reports the count.

    Values run through the SHIPPED `_apply_consensus_blend` +
    `seed_elo_for_value`, and the ordering through the SHIPPED `_undrafted`,
    so the calibration ranks players exactly the way the product does.
    """
    from backend.data_loader import normalise_name, DP_TO_SLEEPER_NAME
    values = _blended_values(fmt)
    rows, elo = {}, {}
    for pid, row in _rookie_universe().items():
        name = normalise_name(row.get("full_name") or "")
        value = values.get(DP_TO_SLEEPER_NAME.get(name, name))
        if not value or value <= 0:
            continue
        rows[pid] = {"full_name": row.get("full_name"), "position": row.get("position"),
                     "team": row.get("team"), "rookie_year": "2026",
                     "search_rank": row.get("search_rank")}
        elo[pid] = seed_elo_for_value(value)
    return mds.MockContext(
        league_id="calibration", season=2026, consensus_elo=elo,
        rookie_ids=frozenset(rows), player_rows=rows,
        rostered_ids=frozenset(pre_rostered), lineup_slots=lineup)


def _lakeview_corpus():
    """`(ctx, pool, drafted_ids, owners_by_pick, viable0, targets)`."""
    root = FIXTURES / "draft" / "lakeview-complete"
    picks = json.loads((root / "draft" / LAKEVIEW_DRAFT / "picks.json").read_text())
    rosters = json.loads((root / "league" / LAKEVIEW_LEAGUE / "rosters.json").read_text())
    league = json.loads((root / "league" / f"{LAKEVIEW_LEAGUE}.json").read_text())
    lineup = league["roster_positions"]

    drafted = [str(p["player_id"]) for p in picks]
    drafted_set = set(drafted)
    rostered = {str(x) for r in rosters for x in (r.get("players") or [])}
    pre_rostered = rostered - drafted_set

    ctx = _rookie_ctx("sf_tep", pre_rostered=pre_rostered, lineup=lineup)
    pool = mds.consensus_pool(ctx)
    owners = [str(p["roster_id"]) for p in
              sorted(picks, key=lambda p: int(p["pick_no"]))]
    positions = {pid: {"position": row.get("position")}
                 for pid, row in _fixture_pool().items()}
    viable0 = {
        str(r["roster_id"]): mds.positional_needs(
            [str(p) for p in (r.get("players") or []) if str(p) not in drafted_set],
            lineup, ctx.consensus_elo, positions)
        for r in rosters
    }
    return ctx, pool, drafted, owners, viable0, mds.slot_targets(lineup)


def _mfl_corpus(name: str):
    from backend.tests.support.draft_replay import mfl_corpus
    raw = mfl_corpus(name)
    unit = raw["draftResults"]["draftUnit"]
    units = unit if isinstance(unit, list) else [unit]
    made = []
    for u in units:
        rows = u["draftPick"]
        rows = rows if isinstance(rows, list) else [rows]
        made += [r for r in rows if str(r.get("player", "")).strip()]
    made.sort(key=lambda r: (int(r["round"]), int(r["pick"])))
    xwalk = _mfl_to_sleeper()
    ctx = _rookie_ctx("1qb_ppr")
    pool = mds.consensus_pool(ctx)
    drafted = [xwalk.get(str(r["player"])) for r in made]
    drafted = [d for d in drafted if d]
    owners = [str(r["franchise"]) for r in made]
    rounds = sorted({int(r["round"]) for r in made})
    return ctx, pool, drafted, owners, rounds


# ── T-W2-17 — shape check BEFORE any corpus is used ──────────────────────

def test_w2_17_corpus_shape_is_checked_before_calibration_use():
    from backend.draft_status import ROOKIE_MAX_ROUNDS, STARTUP_MIN_ROUNDS
    from backend.tests.support.draft_replay import mfl_corpus

    for name in ("mfl-complete", "mfl-partial"):
        raw = mfl_corpus(name)
        unit = raw["draftResults"]["draftUnit"]
        units = unit if isinstance(unit, list) else [unit]
        assert len(units) == 1, f"{name} is multi-unit"
        rows = units[0]["draftPick"]
        rounds = max(int(r["round"]) for r in rows)
        assert rounds <= ROOKIE_MAX_ROUNDS, f"{name} is startup-shaped"

    # `mfl-multi-unit` is EXCLUDED. The LLD calls it "startup-shaped"; by the
    # round-count discriminator it is not (5 rounds, well under
    # STARTUP_MIN_ROUNDS). The real disqualifier is that it is a two-unit
    # conference-split draft, so "the pool as it stood at that pick" is not
    # well defined across units — two drafts interleave in one grid.
    raw = mfl_corpus("mfl-multi-unit")
    units = raw["draftResults"]["draftUnit"]
    assert isinstance(units, list) and len(units) == 2
    assert max(int(r["round"]) for u in units for r in u["draftPick"]) < STARTUP_MIN_ROUNDS


def test_w2_17_lakeview_is_a_four_round_rookie_draft():
    from backend.draft_status import ROOKIE_MAX_ROUNDS
    _ctx, _pool, drafted, owners, _v, _t = _lakeview_corpus()
    assert len(drafted) == 48 and len(owners) == 48
    assert 48 // len(set(owners)) <= ROOKIE_MAX_ROUNDS


# ── T-W2-16 — the gate itself ────────────────────────────────────────────

def _fit_and_validate():
    """Run the lld §4.2.3 procedure end to end. Returns the report dict."""
    ctx, pool, drafted, owners, viable0, targets = _lakeview_corpus()
    pool_ids = [r["player_id"] for r in pool]
    report = mds.reach_report(drafted, pool)
    observed = report["series"]

    # Restrict the turn order to the retained sub-universe so the simulated
    # sequence and the observed one index the same picks.
    kept = [i for i, pid in enumerate(drafted) if pid in set(pool_ids)]
    owners_kept = [owners[i] for i in kept]
    n = len(observed)
    cut = sum(1 for i in kept if i < 24)          # rounds 1-2 of the retained picks

    fit_obs, hold_obs = observed[:cut], observed[cut:]
    personas = {o: mds.DEFAULT_OUTLOOK for o in set(owners_kept)}

    def sim(params, sims, count, owners_slice, viable_seed):
        bpa, decay = params
        out = []
        for seed in range(sims):
            out += mds.simulate_reaches(pool, owners_slice, personas, viable_seed,
                                        targets, bpa_prob=bpa, reach_decay=decay,
                                        max_reach=FIXED_MAX_REACH, seed=seed)[:count]
        return out

    grid = {}
    for bpa in BPA_GRID:
        for decay in DECAY_GRID:
            sample = sim((bpa, decay), FIT_SIMS, cut, owners_kept[:cut], viable0)
            grid[(bpa, decay)] = _wasserstein1([abs(x) for x in sample],
                                               [abs(x) for x in fit_obs])
    fitted = min(grid, key=grid.get)

    hold_sim = sim(fitted, VALIDATE_SIMS, n - cut, owners_kept, viable0)
    hold_d, hold_p = _ks_two_sample([abs(x) for x in hold_sim],
                                    [abs(x) for x in hold_obs])
    hold_delta = abs(statistics.mean(abs(x) for x in hold_sim)
                     - statistics.mean(abs(x) for x in hold_obs))

    # Independent corpus, NO refit.
    mctx, mpool, mdrafted, mowners, _rounds = _mfl_corpus("mfl-complete")
    mpool_ids = [r["player_id"] for r in mpool]
    mreport = mds.reach_report(mdrafted, mpool)
    mobs = mreport["series"]
    mkept = [mowners[i] for i, pid in enumerate(mdrafted) if pid in set(mpool_ids)]
    mviable = {o: {p: 0 for p in ("QB", "RB", "WR", "TE")} for o in set(mkept)}
    msim = []
    for seed in range(VALIDATE_SIMS):
        msim += mds.simulate_reaches(mpool, mkept, {o: mds.DEFAULT_OUTLOOK for o in mkept},
                                     mviable, mds.slot_targets(STANDARD_LINEUP),
                                     bpa_prob=fitted[0], reach_decay=fitted[1],
                                     max_reach=FIXED_MAX_REACH, seed=seed)
    mfl_d, mfl_p = _ks_two_sample([abs(x) for x in msim], [abs(x) for x in mobs])
    mfl_delta = abs(statistics.mean(abs(x) for x in msim)
                    - statistics.mean(abs(x) for x in mobs))

    return {
        "n": n, "fit_n": cut, "hold_n": n - cut,
        "observed": observed,
        "pool_n": len(pool), "mfl_pool_n": len(mpool),
        "skipped": report["skipped"], "tied": report["tied"],
        "mfl_skipped": mreport["skipped"], "mfl_tied": mreport["tied"],
        "fit_mean": statistics.mean(abs(x) for x in fit_obs),
        "hold_mean": statistics.mean(abs(x) for x in hold_obs),
        "grid": {f"{b}/{d}": w for (b, d), w in grid.items()},
        "grid_best_w1": grid[fitted], "grid_worst_w1": max(grid.values()),
        "fitted_bpa_prob": fitted[0], "fitted_reach_decay": fitted[1],
        "fitted_is_interior": (fitted[0] not in (BPA_GRID[0], BPA_GRID[-1])
                               and fitted[1] not in (DECAY_GRID[0], DECAY_GRID[-1])),
        "hold_sim_mean": statistics.mean(abs(x) for x in hold_sim),
        "hold_ks_d": hold_d, "hold_ks_p": hold_p, "hold_delta": hold_delta,
        "hold_pass": hold_p >= KS_ALPHA and hold_delta <= MEAN_BAR,
        "mfl_n": len(mobs),
        "mfl_obs_mean": statistics.mean(abs(x) for x in mobs),
        "mfl_sim_mean": statistics.mean(abs(x) for x in msim),
        "mfl_ks_d": mfl_d, "mfl_ks_p": mfl_p, "mfl_delta": mfl_delta,
        "mfl_pass": mfl_p >= KS_ALPHA and mfl_delta <= MEAN_BAR,
    }


def test_w2_16_calibration_gate():
    """THE GATE. It pins the recorded verdict, in both directions.

    While the verdict is FAILED this asserts the failure is still real — if a
    future change made the model pass, this test goes red and forces someone
    to re-publish the artifact and flip `CPU_MODEL_VALIDATED` deliberately
    rather than by accident. Once the verdict is PASSED it asserts both bars
    on both corpora. Either way the gate is never silently satisfied.
    """
    report = _fit_and_validate()
    passed = report["hold_pass"] and report["mfl_pass"]
    assert passed is mds.CPU_MODEL_VALIDATED, (
        "the calibration verdict moved — re-run the harness, re-publish "
        f"{mds.CALIBRATION_ARTIFACT}, and change CPU_MODEL_VALIDATED "
        f"deliberately. Report: {json.dumps(report, default=float)}")


def test_w2_16_the_w2a_model_form_could_not_have_passed():
    """W2a's verdict, kept falsifiable after its model was deleted.

    The single-parameter model's reachable support was bounded by roughly
    `max_reach + jitter` slots: a candidate at rank r could only win when
    `r - bonus - jitter < 1`, with jitter capped by the top of its grid (3.00).
    Picks beyond that bound have probability EXACTLY ZERO under it, so no value
    of that parameter reproduced the shape. This is why W2b re-specced the
    FAMILY rather than re-tuning — if the observed tail ever thins to nothing,
    this test goes red and the history needs re-deriving.

    **The fraction was re-derived in W2c** and the threshold with it. On the
    W2b snapshot the corpus put 15 %+ of picks past the bound; on the corrected
    snapshot (artifact 08c §2) it is 11 % — 5 of 45 — because the corrected
    consensus moves several mid-round picks up the board. The structural
    argument is unchanged and does not turn on the exact fraction: a model that
    assigns zero probability to 1 pick in 9 cannot be the data-generating one.
    """
    ctx, pool, drafted, _owners, _v, _t = _lakeview_corpus()
    observed = mds.reach_series(drafted, pool)
    beyond = [d for d in observed if d > FIXED_MAX_REACH + 3.00]
    assert len(beyond) / len(observed) > 0.05, (
        "the observed tail moved — re-derive the structural argument")


def test_w2_16_the_mean_bars_became_jointly_satisfiable_under_the_corrected_snapshot():
    """W2c's headline finding, pinned the way W2a's and W2b's were.

    W2b's residual failure rested on an arithmetic claim: the Lakeview hold-out
    and `mfl-complete` disagreed by 2.71 slots — more than twice the ±1.0 bar —
    so the two mean bars asked for simulated means in DISJOINT intervals and no
    corpus-invariant model could satisfy both. The corrected snapshot dissolves
    that claim: the same two blocks now disagree by ~1.65 slots, so the windows
    OVERLAP and a jointly-satisfying simulated mean exists.

    That is why W2c's verdict is still FAILED but for a different reason (both
    mean bars, not one): the failure is now that the FIT block disagrees with
    the blocks it is validated against — see the drift test below. If this test
    ever goes red the 08c artifact's §6 argument has to be re-derived.
    """
    _c1, pool, drafted, _o, _v, _t = _lakeview_corpus()
    lakeview = mds.reach_series(drafted, pool)
    ids = [r["player_id"] for r in pool]
    cut = sum(1 for i, pid in enumerate(drafted) if pid in set(ids) and i < 24)
    hold = statistics.mean(lakeview[cut:])
    _c2, mpool, mdrafted, _mo, _r = _mfl_corpus("mfl-complete")
    mfl = statistics.mean(mds.reach_series(mdrafted, mpool))
    spread = abs(mfl - hold)
    assert spread < 2 * MEAN_BAR, (
        f"the two validation blocks disagree by {spread:.2f} slots again — the "
        "mean bars are back to being jointly UNSATISFIABLE, which is a "
        "different verdict from the one 08c records")
    lo, hi = max(hold, mfl) - MEAN_BAR, min(hold, mfl) + MEAN_BAR
    assert lo <= hi, "the jointly-satisfying window is empty"


def test_w2_16_the_observable_drifts_with_draft_depth():
    """The fit/hold-out split is only meaningful if the observable does not
    drift between blocks — otherwise the ±1.0 hold-out bar is unreachable by
    ANY model fitted on the fit block, and the gate tests the split.

    **This is the W2c finding, and it is a FAILURE being pinned, not a property
    being asserted.** Under W2b's trimmed snapshot the drift measured ~0.3
    slots — but only because a 50-player universe censored every deep reach at
    9 slots. The corrected snapshot uncensors them and the same split drifts
    ~2.0: `d` is a RANK distance, so as a draft descends into the flat part of
    the value curve the same disagreement costs many more slots. Rounds 1-2 sit
    on the steep part, which is exactly the block the procedure fits.

    The remaining-pool reading of the LLD's `d_i` is still the better of the
    two readings (see `reach_report`'s docstring) — the static-rank reading
    drifts harder still, and that comparison is what this test keeps alive.
    """
    ctx, pool, drafted, _o, _v, _t = _lakeview_corpus()
    ids = [r["player_id"] for r in pool]
    observed = mds.reach_series(drafted, pool)
    cut = sum(1 for i, pid in enumerate(drafted) if pid in set(ids) and i < 24)
    drift = abs(statistics.mean(observed[:cut]) - statistics.mean(observed[cut:]))
    assert drift > MEAN_BAR, (
        f"the observable now drifts only {drift:.2f} slots across the split — "
        "08c's diagnosis of the mean-bar failure needs re-deriving")

    static_rank = {pid: i + 1 for i, pid in enumerate(ids)}
    kept = [pid for pid in drafted if pid in static_rank]
    alt = [abs(static_rank[pid] - (i + 1)) for i, pid in enumerate(kept)]
    alt_drift = abs(statistics.mean(alt[:cut]) - statistics.mean(alt[cut:]))
    assert alt_drift > drift, (
        "the two readings of the LLD's d_i no longer differ in stationarity — "
        "re-derive the choice recorded in reach_report's docstring")


def test_w2_16_the_mean_bar_is_tighter_than_the_statistic_it_tests():
    """The other half of the W2c diagnosis: at these sample sizes the ±1.0 bar
    is smaller than the STANDARD ERROR of the mean it bounds, because the
    corrected snapshot's `|d|` is heavy-tailed (one pick at 29.5 on a 22-pick
    block; one at 51.5 on a 28-pick corpus).

    A perfectly-specified model would therefore fail the mean bar a large share
    of the time on sampling noise alone. Recorded so the operator can see that
    "more corpora" is not a nice-to-have but the precondition for the bar to
    mean anything.
    """
    _c1, pool, drafted, _o, _v, _t = _lakeview_corpus()
    observed = mds.reach_series(drafted, pool)
    ids = [r["player_id"] for r in pool]
    cut = sum(1 for i, pid in enumerate(drafted) if pid in set(ids) and i < 24)
    hold = observed[cut:]
    _c2, mpool, mdrafted, _mo, _r = _mfl_corpus("mfl-complete")
    mfl = mds.reach_series(mdrafted, mpool)
    for name, block in (("lakeview hold-out", hold), ("mfl-complete", mfl)):
        se = statistics.stdev(block) / math.sqrt(len(block))
        assert se > MEAN_BAR, (
            f"{name}'s mean is now estimated to +/-{se:.2f}, inside the "
            f"+/-{MEAN_BAR} bar — the bar has become estimable and 08c §6's "
            "power argument needs re-deriving")
