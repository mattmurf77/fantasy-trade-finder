"""Unit tests for backend/power_rankings.compute_power_rankings (#142/#144)
plus route-level acceptance tests for #14 (picks group, updated_at,
superflex seed selection, rank-chip endpoint).

Covers both value bases (consensus / personal-with-consensus-fallback),
out-of-pool zero-value handling, deterministic ordering, and the #144
roster grouping contract (position groups, value-desc within group).

Route tests mirror the isolation pattern of test_league_prefs_authz.py:
Flask test client, injected sessions, patched loaders, no network/DB.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db
import backend.experiments as ex
import backend.server as server
from backend.database import metadata
from backend.pick_values import pick_pool_value, priced_pool_value
from backend.power_rankings import (
    LINEUP_SLOT_ELIGIBILITY,
    align_starter_slots,
    compute_power_rankings,
    optimal_starter_slots,
    optimal_starters,
)
from backend.server import _aggregate_pick_label, _pick_gap_equivalent
from backend.trade_service import elo_to_value


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str = "FA"
    age: int = 25


PLAYERS = {p.id: p for p in [
    _P("qb1", "Alpha QB",  "QB"),
    _P("qb2", "Beta QB",   "QB"),
    _P("rb1", "Alpha RB",  "RB"),
    _P("rb2", "Beta RB",   "RB"),
    _P("wr1", "Alpha WR",  "WR"),
    _P("te1", "Alpha TE",  "TE"),
    _P("k1",  "Some K",    "K"),   # out of the value pool
]}

SEED = {
    "qb1": 1800.0,
    "qb2": 1500.0,
    "rb1": 1700.0,
    "rb2": 1400.0,
    "wr1": 1600.0,
    "te1": 1450.0,
    # k1 deliberately absent — no consensus value
}

MEMBERS = [
    {"user_id": "u_a", "username": "alice", "display_name": "Alice",
     "player_ids": ["qb1", "rb1", "k1"]},
    {"user_id": "u_b", "username": "bob", "display_name": "Bob",
     "player_ids": ["qb2", "rb2", "wr1", "te1"]},
]


def _team(teams, user_id):
    return next(t for t in teams if t["user_id"] == user_id)


def test_consensus_totals_and_rank_order():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1800) + elo_to_value(1700) + 0.0, 1)
    exp_b = round(sum(elo_to_value(SEED[p]) for p in ("qb2", "rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # Alice's two studs outweigh Bob's four mid assets on this seed.
    assert exp_a > exp_b
    assert [t["user_id"] for t in teams] == ["u_a", "u_b"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_out_of_pool_player_contributes_zero():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    k_row = next(r for r in a["roster"] if r["player_id"] == "k1")
    assert k_row["value"] == 0.0
    # ...but the player still appears in the roster listing with metadata.
    assert k_row["name"] == "Some K"
    assert k_row["position"] == "K"


def test_personal_basis_overrides_with_consensus_fallback():
    # The caller tanks qb1 and pumps qb2; everyone else unranked → seed.
    board = {"qb1": 1400.0, "qb2": 1900.0}
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, board_elo=board)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1400) + elo_to_value(1700), 1)   # qb1 by board, rb1 by seed
    exp_b = round(elo_to_value(1900)                            # qb2 by board
                  + sum(elo_to_value(SEED[p]) for p in ("rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # The board flip inverts the league order vs the consensus basis.
    assert [t["user_id"] for t in teams] == ["u_b", "u_a"]
    assert _team(teams, "u_b")["rank"] == 1


def test_tie_breaks_deterministically_by_user_id():
    members = [
        {"user_id": "u_z", "username": "zed", "player_ids": ["qb1"]},
        {"user_id": "u_a", "username": "ann", "player_ids": ["qb1"]},
    ]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert [t["user_id"] for t in teams] == ["u_a", "u_z"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_roster_grouped_by_position_value_desc_within_group():
    members = [{
        "user_id": "u_b", "username": "bob",
        # Deliberately shuffled input order, two QBs to test in-group sort.
        "player_ids": ["te1", "qb2", "wr1", "qb1", "k1", "rb2", "rb1"],
    }]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    roster = teams[0]["roster"]
    assert [r["player_id"] for r in roster] == [
        "qb1", "qb2",        # QB group, value desc
        "rb1", "rb2",        # RB group, value desc
        "wr1",               # WR
        "te1",               # TE
        "k1",                # non-core positions trail
    ]


def test_position_summary_counts_and_values():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    assert a["positions"]["QB"]["count"] == 1
    assert a["positions"]["RB"]["count"] == 1
    assert a["positions"]["WR"] == {"count": 0, "value": 0.0}
    assert abs(a["positions"]["QB"]["value"] - round(elo_to_value(1800), 1)) < 0.2
    # K is not a core position — excluded from the summary, counted in total.
    assert "K" not in a["positions"]


# ---------------------------------------------------------------------------
# #183 — roster ids with no player metadata (IDP / team-DST ids outside the
# pool) are hidden from the roster listing; totals unchanged.
# ---------------------------------------------------------------------------

def test_unknown_roster_ids_hidden_from_roster():
    members = [{
        "user_id": "u_a", "username": "alice", "display_name": "Alice",
        # "4987" = an IDP-style Sleeper id, "SEA" = a team DST id — neither
        # has metadata in the pool. k1 has metadata but no value.
        "player_ids": ["qb1", "rb1", "k1", "4987", "SEA"],
    }]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    roster_ids = [r["player_id"] for r in teams[0]["roster"]]
    assert "4987" not in roster_ids
    assert "SEA" not in roster_ids
    # Known-position players stay, even out of the value pool (K).
    assert roster_ids == ["qb1", "rb1", "k1"]


def test_unknown_roster_ids_do_not_move_totals():
    with_idp = [{
        "user_id": "u_a", "username": "alice",
        "player_ids": ["qb1", "rb1", "k1", "4987", "SEA"],
    }]
    without_idp = [{
        "user_id": "u_a", "username": "alice",
        "player_ids": ["qb1", "rb1", "k1"],
    }]
    a = compute_power_rankings(with_idp, SEED, PLAYERS)[0]
    b = compute_power_rankings(without_idp, SEED, PLAYERS)[0]
    assert a["total_value"] == b["total_value"]
    assert a["positions_value"] == b["positions_value"]
    assert a["positions"] == b["positions"]


def test_member_without_valid_user_id_skipped():
    members = MEMBERS + [{"user_id": "", "username": "ghost", "player_ids": ["qb1"]}]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert {t["user_id"] for t in teams} == {"u_a", "u_b"}


# ---------------------------------------------------------------------------
# #14 FR1 — picks group + total decomposition (unit level)
# ---------------------------------------------------------------------------

def test_picks_group_totals_and_decomposition():
    picks = {"u_a": [{"label": "2026 1st", "value": 55.0},
                     {"label": "2027 2nd (from bob)", "value": 20.4}]}
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, picks_by_owner=picks)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    assert a["picks"]["count"] == 2
    assert a["picks"]["value"] == 75.4
    assert a["picks"]["items"] == [
        {"label": "2026 1st", "value": 55.0},
        {"label": "2027 2nd (from bob)", "value": 20.4},
    ]
    # total_value = positions_value + picks.value, exactly decomposable.
    assert a["total_value"] == round(a["positions_value"] + 75.4, 1)
    # No picks → empty group, total unchanged (players-only).
    assert b["picks"] == {"count": 0, "value": 0.0, "items": []}
    assert b["total_value"] == b["positions_value"]


def test_no_picks_arg_yields_empty_group_and_players_only_totals():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    for t in teams:
        assert t["picks"] == {"count": 0, "value": 0.0, "items": []}
        assert t["total_value"] == t["positions_value"]


# ---------------------------------------------------------------------------
# #14 acceptance (b) — personal basis with ZERO user rankings == consensus
# ---------------------------------------------------------------------------

def test_personal_basis_zero_board_equals_consensus_exactly():
    consensus = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    personal_empty = compute_power_rankings(MEMBERS, SEED, PLAYERS, board_elo={})
    assert personal_empty == consensus


# ---------------------------------------------------------------------------
# League Analyzer replication (2026-07-26) — DERIVED value-optimal starters
# (optimal_starters + the per-team `starters` field). Starters/bench are a
# function of dynasty value + the league's slot template only — no per-week
# lineup data.
# ---------------------------------------------------------------------------

def _row(pid, pos, value):
    return {"player_id": pid, "position": pos, "value": value}


def test_optimal_starters_fills_dedicated_slots_by_value():
    roster = [_row("qb_hi", "QB", 900), _row("qb_lo", "QB", 300),
              _row("rb_hi", "RB", 800), _row("rb_mid", "RB", 500),
              _row("rb_lo", "RB", 100), _row("wr_hi", "WR", 700)]
    starters = optimal_starters(roster, ["QB", "RB", "RB", "WR"])
    assert starters == ["qb_hi", "rb_hi", "rb_mid", "wr_hi"]


def test_optimal_starters_superflex_takes_second_qb():
    # SUPER_FLEX prefers the QB when he outvalues every remaining RB/WR/TE.
    roster = [_row("qb1", "QB", 900), _row("qb2", "QB", 850),
              _row("rb1", "RB", 800), _row("rb2", "RB", 400),
              _row("wr1", "WR", 700), _row("te1", "TE", 200)]
    starters = optimal_starters(
        roster, ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"])
    # Dedicated: qb1, rb1, wr1, te1. FLEX (RB/WR/TE) → rb2. SUPER_FLEX → qb2.
    assert set(starters) == {"qb1", "rb1", "wr1", "te1", "rb2", "qb2"}


def test_optimal_starters_flex_narrowest_first():
    # One elite WR left for two flex slots: the narrower REC_FLEX must not be
    # starved by SUPER_FLEX taking the WR first.
    roster = [_row("qb1", "QB", 900), _row("qb2", "QB", 850),
              _row("wr1", "WR", 800), _row("te1", "TE", 100)]
    starters = optimal_starters(roster, ["QB", "SUPER_FLEX", "REC_FLEX"])
    # QB→qb1; REC_FLEX (narrower, filled first) → wr1; SUPER_FLEX → qb2.
    assert set(starters) == {"qb1", "wr1", "qb2"}


def test_optimal_starters_unfillable_slots_left_empty():
    roster = [_row("rb1", "RB", 500)]
    starters = optimal_starters(roster, ["QB", "RB", "RB", "TE", "FLEX"])
    # Only one RB exists — every other slot stays empty, never padded.
    assert starters == ["rb1"]


def test_optimal_starters_ignores_out_of_pool_positions():
    roster = [_row("rb1", "RB", 500), _row("k1", "K", 0)]
    # K/DEF/IDP slots aren't in the eligibility map → contribute nothing.
    starters = optimal_starters(roster, ["RB", "FLEX"])
    assert starters == ["rb1"]


def test_compute_derives_starters_from_lineup_slots():
    slots = ["QB", "RB", "FLEX"]
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, lineup_slots=slots)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")
    assert a["starters"] == ["qb1", "rb1"]            # no third pool player
    assert set(b["starters"]) == {"qb2", "rb2", "wr1"}  # FLEX → wr1 over te1


def test_compute_without_lineup_slots_keeps_starters_none():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    assert all(t["starters"] is None for t in teams)


# ---------------------------------------------------------------------------
# #238 — optimal_starter_slots: same greedy fill as optimal_starters, but
# keeps WHICH slot each starter landed in (template order, unfillable slots
# carry player None). Additive sibling — optimal_starters is unchanged.
# ---------------------------------------------------------------------------

def _layout_ids(layout):
    return [(e["slot"], e["player"]["player_id"] if e["player"] else None)
            for e in layout]


def test_starter_slots_template_order_and_dedicated_fill():
    roster = [_row("qb_hi", "QB", 900), _row("rb_hi", "RB", 800),
              _row("rb_mid", "RB", 500), _row("wr_hi", "WR", 700)]
    layout = optimal_starter_slots(roster, ["QB", "RB", "RB", "WR", "FLEX"])
    assert _layout_ids(layout) == [
        ("QB", "qb_hi"), ("RB", "rb_hi"), ("RB", "rb_mid"),
        ("WR", "wr_hi"), ("FLEX", None)]


def test_starter_slots_flex_and_superflex_eligibility():
    # FLEX (RB/WR/TE) takes the best remaining non-QB; SUPER_FLEX takes the
    # second QB — a QB must never land in plain FLEX.
    roster = [_row("qb1", "QB", 900), _row("qb2", "QB", 850),
              _row("rb1", "RB", 800), _row("rb2", "RB", 400),
              _row("wr1", "WR", 700), _row("te1", "TE", 200)]
    layout = optimal_starter_slots(
        roster, ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"])
    assert _layout_ids(layout) == [
        ("QB", "qb1"), ("RB", "rb1"), ("WR", "wr1"), ("TE", "te1"),
        ("FLEX", "rb2"), ("SUPER_FLEX", "qb2")]


def test_starter_slots_narrowest_flex_fills_first_output_stays_template_order():
    # REC_FLEX (narrower) claims the elite WR even though SUPER_FLEX comes
    # first in the template; output rows keep the template's order.
    roster = [_row("qb1", "QB", 900), _row("qb2", "QB", 850),
              _row("wr1", "WR", 800), _row("te1", "TE", 100)]
    layout = optimal_starter_slots(roster, ["QB", "SUPER_FLEX", "REC_FLEX"])
    assert _layout_ids(layout) == [
        ("QB", "qb1"), ("SUPER_FLEX", "qb2"), ("REC_FLEX", "wr1")]


def test_starter_slots_ignore_out_of_pool_slots_and_agree_with_starters():
    roster = [_row("qb1", "QB", 900), _row("rb1", "RB", 500),
              _row("wr1", "WR", 450), _row("k1", "K", 0)]
    slots = ["QB", "RB", "K", "BN", "FLEX"]
    layout = optimal_starter_slots(roster, slots)
    # K/BN aren't lineup slots the value pool can fill — no rows for them.
    assert [e["slot"] for e in layout] == ["QB", "RB", "FLEX"]
    assert (sorted(e["player"]["player_id"] for e in layout if e["player"])
            == sorted(optimal_starters(roster, slots)))


# ---------------------------------------------------------------------------
# #395 — align_starter_slots: pairwise-align two optimal_starter_slots
# outputs so a value-identical lineup change displays the minimum honest set
# of changed rows. Pure display transform — totals, starter sets, and slot
# eligibility are invariant; scan order is pinned (before side first, (i, j)
# ascending, restart on apply) so conforming implementations agree byte-fully.
# ---------------------------------------------------------------------------

# The #395 repro shape (PRD §1): Daniels (QB 9000) canonically owns the QB
# slot, Maye (QB 6000) the SUPER_FLEX; the user reads it the other way.
_395_TEMPLATE = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
_395_ROSTER = [
    _row("daniels", "QB", 9000), _row("maye", "QB", 6000),
    _row("rb_a", "RB", 2000), _row("rb_b", "RB", 1900),
    _row("wr_a", "WR", 3600), _row("wr_b", "WR", 3400),
    _row("wr_c", "WR", 3000),                    # FLEX starter both sides
    _row("te_top", "TE", 3200),                  # dedicated TE both sides
    _row("fannin", "TE", 2800),                  # benched until Daniels leaves
]


def _changed(before, after):
    """Indices whose player_id differs between the two aligned sides."""
    def pid(e):
        return e["player"]["player_id"] if e["player"] else None
    return [k for k, (b, a) in enumerate(zip(before, after))
            if pid(b) != pid(a)]


def test_align_starter_slots_superflex_cascade():
    before = optimal_starter_slots(_395_ROSTER, _395_TEMPLATE)
    after = optimal_starter_slots(
        [r for r in _395_ROSTER if r["player_id"] != "daniels"], _395_TEMPLATE)
    # Unaligned, the canonical fills cascade: QB daniels→maye AND SF
    # maye→fannin — the phantom two-row display the user reported.
    assert len(_changed(before, after)) == 2
    assert before[0]["player"]["player_id"] == "daniels"

    a_before, a_after = align_starter_slots(before, after)
    # Aligned before matches the user's mental model: Maye at QB, Daniels
    # at SUPER_FLEX — so exactly ONE row changes: SF, Daniels → Fannin.
    assert a_before[0]["slot"] == "QB"
    assert a_before[0]["player"]["player_id"] == "maye"
    assert a_before[7]["slot"] == "SUPER_FLEX"
    assert a_before[7]["player"]["player_id"] == "daniels"
    assert _changed(a_before, a_after) == [7]
    assert a_after[7]["player"]["player_id"] == "fannin"


def test_align_starter_slots_wr_flex_cascade():
    roster = [_row("wr_hi", "WR", 900), _row("wr_mid", "WR", 800),
              _row("wr_low", "WR", 700), _row("wr_bench", "WR", 600)]
    tmpl = ["WR", "WR", "FLEX"]
    before = optimal_starter_slots(roster, tmpl)
    after = optimal_starter_slots(
        [r for r in roster if r["player_id"] != "wr_hi"], tmpl)
    # Unaligned every row shifts up one — three changed rows.
    assert len(_changed(before, after)) == 3
    a_before, a_after = align_starter_slots(before, after)
    # Aligned: the two WR rows are byte-equal before/after; the single
    # changed row is the FLEX (departing wr_hi → backfilling wr_bench).
    changed = _changed(a_before, a_after)
    assert changed == [2] and a_before[2]["slot"] == "FLEX"
    assert a_before[2]["player"]["player_id"] == "wr_hi"
    assert a_after[2]["player"]["player_id"] == "wr_bench"
    for k in (0, 1):
        assert a_before[k] == a_after[k]


def test_align_preserves_totals_and_eligibility():
    def check_invariants(before, after, a_before, a_after):
        for orig, aligned in ((before, a_before), (after, a_after)):
            def total(rows):
                return sum(e["player"]["value"] for e in rows if e["player"])

            def ids(rows):
                return {e["player"]["player_id"] for e in rows if e["player"]}
            # Alignment does no arithmetic — totals byte-equal, sets equal.
            assert total(aligned) == total(orig)
            assert ids(aligned) == ids(orig)
            assert [e["slot"] for e in aligned] == [e["slot"] for e in orig]
            for e in aligned:
                if e["player"] is not None:
                    assert (e["player"]["position"]
                            in LINEUP_SLOT_ELIGIBILITY[e["slot"]])

    # Scenario A: the #395 shape. Scenario B: duplicate FLEX + SUPER_FLEX
    # slots with a multi-asset trade.
    dup_tmpl = ["QB", "RB", "WR", "TE", "FLEX", "FLEX",
                "SUPER_FLEX", "SUPER_FLEX"]
    dup_roster = _395_ROSTER + [_row("rb_c", "RB", 1500)]
    scenarios = [
        (optimal_starter_slots(_395_ROSTER, _395_TEMPLATE),
         optimal_starter_slots(
             [r for r in _395_ROSTER if r["player_id"] != "daniels"],
             _395_TEMPLATE)),
        (optimal_starter_slots(dup_roster, dup_tmpl),
         optimal_starter_slots(
             [r for r in dup_roster
              if r["player_id"] not in ("daniels", "wr_a")], dup_tmpl)),
    ]
    for before, after in scenarios:
        b_snap = [dict(e) for e in before]
        a_snap = [dict(e) for e in after]
        a_before, a_after = align_starter_slots(before, after)
        check_invariants(before, after, a_before, a_after)
        # Inputs not mutated; repeated calls byte-identical (pinned order).
        assert before == b_snap and after == a_snap
        assert align_starter_slots(before, after) == (a_before, a_after)

    # Pinned mixed-flex fixture (PRD test 3, mandatory): the ONLY
    # match-improving swaps are eligibility-invalid — before-side
    # teQ → WRRB_FLEX (TE ∉ {RB,WR}); after-side rbR → REC_FLEX
    # (RB ∉ {WR,TE}) — so a correct implementation applies nothing and
    # both changed rows stand.
    mixed_before = [{"slot": "WRRB_FLEX", "player": _row("wrP", "WR", 500)},
                    {"slot": "REC_FLEX", "player": _row("teQ", "TE", 400)}]
    mixed_after = [{"slot": "WRRB_FLEX", "player": _row("rbR", "RB", 450)},
                   {"slot": "REC_FLEX", "player": _row("wrP", "WR", 500)}]
    a_before, a_after = align_starter_slots(mixed_before, mixed_after)
    check_invariants(mixed_before, mixed_after, a_before, a_after)
    assert a_before == mixed_before and a_after == mixed_after
    assert _changed(a_before, a_after) == [0, 1]


def test_align_forced_change_is_noop():
    # Trade the ONLY QB; the template has a second TE slot the roster cannot
    # fill (before TE2 = None). The genuine forced change must survive
    # exactly: the only zero-or-better swap is the INVALID net-0 QB ↔ TE2
    # (+1 at QB, −1 at the vacated TE2), so alignment applies nothing.
    roster = [_row("daniels", "QB", 9000), _row("te_top", "TE", 3200)]
    tmpl = ["QB", "TE", "TE"]
    before = optimal_starter_slots(roster, tmpl)
    after = optimal_starter_slots(
        [r for r in roster if r["player_id"] != "daniels"], tmpl)
    assert before[1]["player"]["player_id"] == "te_top"
    assert before[2]["player"] is None                  # unfillable TE2
    a_before, a_after = align_starter_slots(before, after)
    assert a_before == before and a_after == after      # no-op
    assert _changed(a_before, a_after) == [0]           # exactly {QB}
    assert a_before[0]["player"]["player_id"] == "daniels"
    assert a_after[0]["player"] is None


def test_derived_starters_follow_personal_basis_values():
    # On the caller's board rb2 outvalues rb1 — the optimal lineup must flip
    # with the basis, because starters are a function of the ranked values.
    members = [{"user_id": "u_a", "username": "alice",
                "player_ids": ["rb1", "rb2"]}]
    slots = ["RB"]
    consensus = compute_power_rankings(members, SEED, PLAYERS,
                                       lineup_slots=slots)
    personal = compute_power_rankings(members, SEED, PLAYERS,
                                      board_elo={"rb2": 1900.0},
                                      lineup_slots=slots)
    assert consensus[0]["starters"] == ["rb1"]
    assert personal[0]["starters"] == ["rb2"]


def test_bench_reranking_flips_league_order():
    # The client's Bench view re-ranks the league from (roster − starters)
    # values. Alice: one stud starter, empty bench. Bob: weaker starter but a
    # deep bench. All-ranking says Alice; bench-ranking must say Bob. This
    # pins the payload contract the client math depends on (per-player roster
    # values + the starters split).
    members = [
        {"user_id": "u_a", "username": "alice", "player_ids": ["qb1"]},
        {"user_id": "u_b", "username": "bob",
         "player_ids": ["qb2", "rb1", "rb2", "wr1", "te1"]},
    ]
    teams = compute_power_rankings(members, SEED, PLAYERS,
                                   lineup_slots=["QB"])

    def subset_total(t, bench):
        s = set(t["starters"])
        return sum(r["value"] for r in t["roster"]
                   if (r["player_id"] not in s) == bench)

    a, b = _team(teams, "u_a"), _team(teams, "u_b")
    assert a["starters"] == ["qb1"] and b["starters"] == ["qb2"]
    # Starters view: Alice's qb1 beats Bob's qb2.
    assert subset_total(a, bench=False) > subset_total(b, bench=False)
    # Bench view: Alice has nothing, Bob's bench dominates → order flips.
    assert subset_total(a, bench=True) == 0.0
    assert subset_total(b, bench=True) > subset_total(a, bench=True)
    bench_order = sorted(teams, key=lambda t: -subset_total(t, bench=True))
    assert [t["user_id"] for t in bench_order] == ["u_b", "u_a"]


# ---------------------------------------------------------------------------
# Route-level acceptance tests (#14) — /api/league/power-rankings +
# /api/league/rank-chip
# ---------------------------------------------------------------------------

LEAGUE = "league_pr_test"
TOKEN  = "sess-pr-test"

SEED_SF = {  # superflex pool seed — QBs pumped relative to 1QB
    "qb1": 1950.0,
    "qb2": 1700.0,
    "rb1": 1700.0,
    "rb2": 1400.0,
    "wr1": 1600.0,
    "te1": 1450.0,
}

# Owned-pick fixture rows: the load_draft_picks shape the /api/league/picks
# route consumes, pool_value written the way sync writes it (pick_pool_value
# with years_out = season - current season; current season 2026 here).
#
# ⚠️  D-148 (2026-08-21, closes Q-026) — the STORED value below is no longer
# what the route SERVES. `_power_picks_by_owner` now prices each row through
# `_priced_pick_value`, the same own-slot → round-curve → stored-ladder
# waterfall the trade engine charges, so Power Rankings and a trade card can
# no longer disagree about a pick. `_priced` is the expectation helper for
# that; every literal in this file is re-derived through it against the DP
# snapshot `conftest.py` pins, and the stored column survives as step 3.
#
# These fixtures resolve NO slot (`is_enabled` is patched False, so
# `picks.slot_labels` is off and `_league_slot_order` returns None), which is
# the round-curve branch. Per-slot pricing through a league surface is
# covered in test_league_picks_tier.py's `slotted_client`.
PICK_ROWS = [
    {"pick_id": f"{LEAGUE}_2026_1_1", "league_id": LEAGUE, "season": 2026,
     "round": 1, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(1, 0)},
    {"pick_id": f"{LEAGUE}_2027_2_2", "league_id": LEAGUE, "season": 2027,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 1, "original_username": "bob",
     "pool_value": pick_pool_value(2, 1)},
    {"pick_id": f"{LEAGUE}_2026_3_2", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(3, 0)},
]


def _priced(season: int, rnd: int, years_out: int, fmt: str = "1qb_ppr") -> float:
    """What a league surface SERVES for a pick, re-derived from the pricing
    function rather than pinned as a bare number: `priced_pool_value` over a
    row the sync wrote, with no slot resolved (these fixtures run flags-off).

    Round-curve results under the pinned DP snapshot, for orientation —
    2026 1st 1859.5 · 2026 2nd 434.0 · 2026 3rd 262.3 · 2027 2nd 389.7 —
    against stored rungs of 2117.0 / 606.5 / 406.6 / 515.6."""
    return priced_pool_value(
        {"season": season, "round": rnd,
         "pool_value": pick_pool_value(rnd, years_out, fmt)},
        scoring_format=fmt, slot=None)


class _EmptyBoardSvc:
    """Ranking service stub: a caller who has ranked zero players."""
    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[])


def _h(token=TOKEN):
    return {"X-Session-Token": token}


def _mk_sess(user_id="u_a", fmt="1qb_ppr", svc=None):
    """Minimal session satisfying _require_initialized_session."""
    return {"verified": True,
        "user_id":       user_id,
        "active_format": fmt,
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE, platform=None,
                                         members=[]),
        "players":       list(PLAYERS.values()),
        "trade_svc":     object(),
        "trade_svcs":    {fmt: object()},
        "services":      {fmt: svc} if svc is not None else {},
        "service":       svc,
        "user_roster":   [],
    }


def _fake_pool(fmt):
    return (list(PLAYERS.values()), SEED_SF if fmt == "sf_tep" else dict(SEED))


def _members_rows(league_id):
    if league_id == LEAGUE:
        return [dict(m) for m in MEMBERS]
    return []


def _pick_rows(league_id):
    return [dict(p) for p in PICK_ROWS] if league_id == LEAGUE else []


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    server._rank_chip_cache.clear()
    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_league_members", _members_rows), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw: _pick_rows(league_id)), \
         patch.object(server, "_get_universal_pool", _fake_pool):
        try:
            yield c
        finally:
            server._rank_chip_cache.clear()
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _install_sess(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _get(c, path):
    r = c.get(path, headers=_h())
    return r.status_code, json.loads(r.data)


# (a) team totals reconcile with elo_to_value over the same rosters ---------

def test_route_totals_reconcile_with_elo_to_value(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")

    exp_players = round(elo_to_value(SEED["qb1"]) + elo_to_value(SEED["rb1"])
                        + 0.0, 1)                       # k1 out of pool → 0
    exp_picks = round(_priced(2026, 1, 0) + _priced(2027, 2, 1), 1)
    assert abs(a["positions_value"] - exp_players) < 0.2
    assert abs(a["picks"]["value"] - exp_picks) < 0.2
    assert abs(a["total_value"] - (exp_players + exp_picks)) < 0.3


# (b) personal basis, zero rankings → identical to consensus ----------------

def test_route_personal_zero_board_matches_consensus(client):
    _install_sess(_mk_sess(svc=_EmptyBoardSvc()))
    with patch.object(server, "_verified_read_denial", lambda s: None):
        code_p, body_p = _get(
            client, f"/api/league/power-rankings?league_id={LEAGUE}&basis=personal")
    code_c, body_c = _get(
        client, f"/api/league/power-rankings?league_id={LEAGUE}&basis=consensus")
    assert code_p == code_c == 200
    assert body_p["basis"] == "personal"
    assert body_p["teams"] == body_c["teams"]


# (c) superflex league uses the sf seed pool --------------------------------

def test_route_superflex_uses_sf_seed(client):
    _install_sess(_mk_sess(fmt="sf_tep"))
    pool_spy = MagicMock(side_effect=_fake_pool)
    with patch.object(server, "_get_universal_pool", pool_spy):
        code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert body["scoring_format"] == "sf_tep"
    pool_spy.assert_called_once_with("sf_tep")
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    exp_qb_sf = round(elo_to_value(SEED_SF["qb1"]), 1)
    assert abs(a["positions"]["QB"]["value"] - exp_qb_sf) < 0.2
    assert a["positions"]["QB"]["value"] > round(elo_to_value(SEED["qb1"]), 1)


# (d) picks group == sum(priced_pool_value) == /api/league/picks data -------

def test_route_picks_group_matches_priced_pool_value_and_picks_route(client):
    """D-148 (Q-026) — THE CROSS-SURFACE AGREEMENT TEST.

    The second half was already here and already passed before D-148, because
    both surfaces read the same stored column. Its teeth are new: the two now
    have to agree on a number NEITHER of them stores, produced by the same
    waterfall the engine charges. The first half pins that number literally,
    so "they agree because both regressed to the ladder" fails."""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")

    assert a["picks"]["count"] == 2
    assert a["picks"]["value"] == round(_priced(2026, 1, 0)
                                        + _priced(2027, 2, 1), 1) == 2249.2
    assert b["picks"]["value"] == round(_priced(2026, 3, 0), 1) == 262.3
    # …and NOT the stored ladder, which is what this surface used to serve.
    assert a["picks"]["value"] != round(
        pick_pool_value(1, 0) + pick_pool_value(2, 1), 1)
    labels = [i["label"] for i in a["picks"]["items"]]
    assert labels == ["2026 1st", "2027 2nd (from bob)"]

    # Cross-check against /api/league/picks for the same fixture: same rows,
    # same waterfall, same slot resolution ⇒ the same number per team.
    code2, picks_body = _get(client, f"/api/league/picks?league_id={LEAGUE}")
    assert code2 == 200
    for team in (a, b):
        rows = [p for p in picks_body["all_picks"]
                if p["owner_user_id"] == team["user_id"]]
        assert team["picks"]["count"] == len(rows)
        assert team["picks"]["value"] == round(
            sum(p["pool_value"] for p in rows), 1)
        assert sorted(i["label"] for i in team["picks"]["items"]) == \
               sorted(p["label"] for p in rows)


# (e) updated_at present + parseable ----------------------------------------

def test_route_updated_at_present_and_parseable(client):
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    ts = datetime.fromisoformat(body["updated_at"])
    assert ts.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - ts).total_seconds()) < 60


# (g) derived starters in the route payload (2026-07-26) --------------------

def test_route_starters_unavailable_without_slot_template(client):
    # LEAGUE is a non-Sleeper id → _sleeper_lineup_slots yields None → every
    # team's starters is None and the control-gating flag is false.
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert body["starters_available"] is False
    assert all(t["starters"] is None for t in body["teams"])


def test_route_starters_available_with_slot_template(client):
    _install_sess(_mk_sess())
    with patch.object(server, "_sleeper_lineup_slots",
                      lambda lid: ["QB", "RB", "FLEX"]):
        code, body = _get(client,
                          f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert body["starters_available"] is True
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")
    assert a["starters"] == ["qb1", "rb1"]
    assert set(b["starters"]) == {"qb2", "rb2", "wr1"}
    # Starters are always a subset of the serialized roster.
    for t in body["teams"]:
        roster_ids = {r["player_id"] for r in t["roster"]}
        assert set(t["starters"]) <= roster_ids


def test_sleeper_lineup_slots_filters_to_relevant_slots():
    meta = {"roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX",
                                 "SUPER_FLEX", "K", "DEF", "IDP_FLEX",
                                 "BN", "BN", "IR", "TAXI"]}
    server._FA_LEAGUE_META_CACHE.pop("123456789", None)
    with patch.object(server, "_fetch_sleeper_league_meta", lambda lid: meta):
        try:
            slots = server._sleeper_lineup_slots("123456789")
        finally:
            server._FA_LEAGUE_META_CACHE.pop("123456789", None)
    assert slots == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
    # Non-Sleeper ids never fetch and never yield a template.
    assert server._sleeper_lineup_slots("espn:12345") is None
    assert server._sleeper_lineup_slots("league_demo") is None


# (f) rank-chip route --------------------------------------------------------

def test_rank_chip_consistent_with_full_payload(client):
    _install_sess(_mk_sess(user_id="u_b"))
    code, full = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    you = next(t for t in full["teams"] if t["is_you"])

    code2, chip = _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    assert code2 == 200
    assert chip["rank"] == you["rank"]
    assert chip["team_count"] == len(full["teams"])
    assert chip["basis"] == "consensus"
    assert datetime.fromisoformat(chip["updated_at"]).tzinfo is not None


def test_rank_chip_cached_between_calls(client):
    _install_sess(_mk_sess())
    _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    with patch.object(server, "_power_ranking_inputs",
                      MagicMock(side_effect=AssertionError("cache miss"))):
        code, chip = _get(client, f"/api/league/rank-chip?league_id={LEAGUE}")
    assert code == 200
    assert chip["rank"] == 1


def test_rank_chip_demo_league_via_session_fallback(client):
    sess = _mk_sess(user_id="u_demo")
    sess["league"] = SimpleNamespace(
        league_id="league_demo", platform=None,
        members=[SimpleNamespace(user_id="u_mate", username="mate",
                                 roster=["qb2", "rb2"])])
    sess["user_roster"] = ["qb1", "rb1"]
    _install_sess(sess)
    code, chip = _get(client, "/api/league/rank-chip?league_id=league_demo")
    assert code == 200
    assert chip["team_count"] == 2
    assert chip["rank"] == 1          # qb1+rb1 outvalues qb2+rb2 on this seed
    assert chip["basis"] == "consensus"


def test_rank_chip_espn_league_no_picks(client):
    espn_league = "espn:12345"
    espn_members = [
        {"user_id": "u_a", "username": "alice", "display_name": "Alice",
         "player_ids": ["qb1", "rb1"]},
        {"user_id": "espn:12345.t2", "username": "Team 2",
         "display_name": "Team 2", "player_ids": ["qb2", "rb2", "wr1"]},
    ]
    _install_sess(_mk_sess())
    with patch.object(server, "load_league_members",
                      lambda lid: espn_members if lid == espn_league else []):
        code, chip = _get(client, f"/api/league/rank-chip?league_id={espn_league}")
    assert code == 200
    assert chip["team_count"] == 2
    assert chip["rank"] in (1, 2)

    # ESPN leagues carry no draft_picks rows — full payload shows the empty
    # picks group rather than erroring. #306/D-306-2: the group's
    # `value_label` is an honest "≈0 firsts", never a missing key.
    with patch.object(server, "load_league_members",
                      lambda lid: espn_members if lid == espn_league else []):
        code2, full = _get(client,
                           f"/api/league/power-rankings?league_id={espn_league}")
    assert code2 == 200
    for t in full["teams"]:
        assert t["picks"] == {"count": 0, "value": 0.0, "items": [],
                              "value_label": "≈0 firsts"}


# ── #277/#278 — additive per-player `tier` on roster rows ───────────────────
# Tier labels app-wide: each roster row carries the pick-value ladder tier
# walked off the SAME raw Elo (board first, seed fallback) its `value` was
# priced from. Never derived from the transformed `value`; absent entirely
# when no tier_fn is injected (pure additive — old callers byte-identical).


def test_tier_fn_stamps_tier_from_priced_elo():
    def tier_fn(elo, pos):
        return f"t:{int(elo)}:{pos}"

    board = {"qb1": 1400.0}   # caller tanks qb1 → board elo must win
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS,
                                   board_elo=board, tier_fn=tier_fn)
    rows = {r["player_id"]: r for r in _team(teams, "u_a")["roster"]}
    assert rows["qb1"]["tier"] == "t:1400:QB"     # board elo, not seed 1800
    assert rows["rb1"]["tier"] == "t:1700:RB"     # consensus-seed fallback
    assert rows["k1"]["tier"] is None             # unpriceable → honest null


def test_no_tier_fn_omits_key_entirely():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    assert all("tier" not in r for t in teams for r in t["roster"])


def test_route_roster_rows_carry_canonical_tier(client):
    # Route-level: `tier` equals the canonical RankingService band-walk over
    # the RAW consensus seed (consensus basis, 1qb_ppr session).
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    rows = {r["player_id"]: r for r in a["roster"]}
    assert rows["qb1"]["tier"] == server.RankingService.tier_for_elo(
        SEED["qb1"], "QB", "1qb_ppr")
    assert rows["rb1"]["tier"] == server.RankingService.tier_for_elo(
        SEED["rb1"], "RB", "1qb_ppr")
    assert rows["k1"]["tier"] is None             # out of pool → no tier


# ---------------------------------------------------------------------------
# #279 → #306 — aggregate pick-equivalent labels on TEAM/POSITIONAL
# aggregates. Shipped 2026-08-09 behind the operator-only
# `aggregate_tier_labels` experiment (docs/feedback/items/
# 279-aggregate-tier-labels/status.md); GRADUATED 2026-08-16 (#306,
# D-306-1): the route no longer consults the experiment and every caller
# gets the labels. The experiment-engine test below is kept as an ENGINE
# test (targeting semantics of an is_tester_allowlist 0/10000 experiment —
# the row may still exist in prod until the operator runs stop → decide);
# the ROUTE tests pin the graduated, ungated contract, including under a
# still-running experiment with a non-targeted caller — the exact state
# that used to withhold the keys (re-gate sabotage trap).
# ---------------------------------------------------------------------------

def _mk_aggregate_experiment(engine):
    """Seed a running `aggregate_tier_labels` experiment on the exact shape
    the operator would launch in prod: layer 'ranking', account unit,
    is_tester_allowlist targeting, 0bp control / 10000bp treatment."""
    with engine.begin() as c:
        c.execute(insert(db.experiments_table).values(
            key="aggregate_tier_labels", version=1, layer="ranking",
            status="running", unit_type="account",
            bucket_start=0, bucket_end=10000,
            targeting_json=json.dumps({"is_tester_allowlist": True}),
            variants_json=json.dumps([
                {"name": "control", "weight_bp": 0},
                {"name": "treatment", "weight_bp": 10000},
            ]),
            primary_metric="wat", guardrails_json="[]",
            exposure_surface="league_summary", scope_json="{}",
            created_at="2026-08-09T00:00:00+00:00"))


@pytest.fixture()
def exp_engine():
    """Isolated in-memory experiments DB — patches db.engine/ro_engine
    (shared module object, so backend.experiments sees the same patch)."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        db._seed_experiment_layers()
        ex.invalidate_cache()
        yield eng
    ex.invalidate_cache()


def test_aggregate_labels_assignment_is_operator_only(exp_engine, monkeypatch):
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_a")
    _mk_aggregate_experiment(exp_engine)
    ex.invalidate_cache()
    # Allowlisted account unit → always treatment (0bp control makes it
    # certain); a non-listed unit is excluded by TARGETING, not bucketing.
    assert ex.variant_for("u_a", "aggregate_tier_labels") == "treatment"
    assert ex.variant_for("u_b", "aggregate_tier_labels") is None
    assert ex.variant_for("someone_else", "aggregate_tier_labels") is None


def test_positional_value_labels_ungated(client, exp_engine, monkeypatch):
    """#306 graduation (D-306-1), re-gate sabotage trap: a caller who is NOT
    on the tester allowlist, reading while the `aggregate_tier_labels`
    experiment is still RUNNING — the exact state in which #279 withheld the
    keys — gets `value_label` on every team's every core position, plus
    `total_value_label`, all in the `≈N firsts` format. Wrapping the
    emission back in a `variant_for(...) == "treatment"` check fails this
    on the missing keys."""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_a")   # u_b is NOT listed
    _mk_aggregate_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_b"))
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")

    # #285 math carried through graduation unchanged: the team TOTAL label
    # is positions_value's firsts PLUS the literal pick count (u_a owns a
    # 2026 1st + a 2027 2nd → 1.0 + 1/3.5 firsts; u_b owns only a 2026 3rd
    # → 0 firsts), never `total_value` (dollar-priced picks, double count).
    assert a["total_value_label"] == _aggregate_pick_label(
        a["positions_value"], 1.0 + 1 / 3.5)
    assert b["total_value_label"] == _aggregate_pick_label(
        b["positions_value"], 0.0)
    for team in body["teams"]:
        for pos, pv in team["positions"].items():
            # Positional subtotals stay position-scoped — no pick
            # contribution — and every label is a real `≈N firsts` string.
            assert pv["value_label"] == _aggregate_pick_label(pv["value"])
            assert pv["value_label"].startswith("≈")
            assert pv["value_label"].endswith(" firsts")


def test_route_labels_identical_with_and_without_experiment(client, exp_engine, monkeypatch):
    """Graduated code consults the experiment NOWHERE: the payload for a
    non-targeted caller under a running experiment is byte-identical —
    labels INCLUDED — to the same request with no experiment row at all.
    (Pre-graduation this test asserted byte-identical absence; the invariant
    survived the flip, only the shared contract changed.)"""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_a")   # u_b is NOT listed
    _mk_aggregate_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_b"))
    code_running, body_running = _get(
        client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code_running == 200
    assert all("total_value_label" in t for t in body_running["teams"])

    # Baseline: identical request, fresh empty experiments DB (no row at
    # all) — proves the payload is byte-identical either way.
    eng2 = create_engine("sqlite:///:memory:",
                         connect_args={"check_same_thread": False})
    metadata.create_all(eng2)
    with patch.object(db, "engine", eng2), patch.object(db, "ro_engine", eng2):
        db._seed_experiment_layers()
        ex.invalidate_cache()
        _install_sess(_mk_sess(user_id="u_b"))
        code_base, body_base = _get(
            client, f"/api/league/power-rankings?league_id={LEAGUE}")
    ex.invalidate_cache()
    assert code_base == 200
    # `updated_at` is a fresh compute timestamp each call — compare
    # everything else byte-for-byte.
    body_running.pop("updated_at", None)
    body_base.pop("updated_at", None)
    assert body_running == body_base


# #306 D-306-2 — `picks.value_label` fixture where the literal-count label
# and a (wrong) dollar-space conversion of `picks.value` provably DIFFER:
# two current-season 2nds → literal 2/3.5 firsts → "≈0.5 firsts", while
# their summed dollar pool_value converts to "≈1 firsts". (The module-level
# PICK_ROWS fixture collides on this distinction — 1st+2nd lands on
# "≈1.5 firsts" both ways — so it cannot catch the dollar-space sabotage.)
_PICKS_306 = [
    {"pick_id": f"{LEAGUE}_2026_2_1", "league_id": LEAGUE, "season": 2026,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(2, 0)},
    {"pick_id": f"{LEAGUE}_2026_2_2", "league_id": LEAGUE, "season": 2026,
     "round": 2, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 1, "original_username": "bob",
     "pool_value": pick_pool_value(2, 0)},
    # D-084 (2026-08-19): u_a also holds 3rds. They are what keeps the
    # dollar-space sabotage trap below sharp — the literal scale prices a
    # 3rd at exactly 0, the dollar scale at 262.3, so the two answers
    # diverge. Before D-084 two 2nds alone were enough to split them; the
    # round-2 deflation moved the engine's 2nd:1st ratio to 0.287, which is
    # within 0.001 of the #285 literal weight of 1/3.5 = 0.286, so two 2nds
    # now agree in BOTH scales and no longer trap anything.
    #
    # D-148 (2026-08-21) WIDENED THE GAP THIS FIXTURE HAS TO CROSS. The
    # market curve deflates a current-year 2nd (606.5 → 434.0) and 3rd
    # (406.6 → 262.3) while the "firsts" denominator stays the ladder's Mid
    # 1st, so ONE 3rd no longer separates the scales: 2 seconds + 1 third is
    # 1130.3 dollars ⇒ "≈0.5 firsts", the same answer the literal count
    # gives. Re-derived to THREE thirds — 1654.9 dollars ⇒ "≈1 firsts"
    # against the literal "≈0.5 firsts" — which restores the divergence the
    # trap is made of. Two thirds would not: 1392.6 still rounds to ≈0.5.
    {"pick_id": f"{LEAGUE}_2026_3_1", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(3, 0)},
    {"pick_id": f"{LEAGUE}_2026_3_3", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(3, 0)},
    {"pick_id": f"{LEAGUE}_2026_3_4", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_a", "owner_username": "alice",
     "is_traded": 0, "original_username": "alice",
     "pool_value": pick_pool_value(3, 0)},
    {"pick_id": f"{LEAGUE}_2026_3_2", "league_id": LEAGUE, "season": 2026,
     "round": 3, "owner_user_id": "u_b", "owner_username": "bob",
     "is_traded": 0, "original_username": "bob",
     "pool_value": pick_pool_value(3, 0)},
]


def test_picks_value_label_literal_count(client):
    """#306 D-306-2: each team's `picks.value_label` is the #285 literal
    pick count expressed alone (1st = 1.0, 2nd = 1/3.5, 3rd+ = 0; value
    base 0.0) — never a conversion of the dollar-priced `picks.value`.
    Dollar-space sabotage trap: computing the label from `picks.value`
    yields "≈1 firsts" for u_a here, not the literal "≈0.5 firsts" — the
    divergence is carried by his three 3rds, which the literal scale prices
    at 0 apiece and the dollar scale at 262.3 apiece (see the fixture note
    on _PICKS_306, re-derived at D-148)."""
    with patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw:
                      [dict(p) for p in _PICKS_306]
                      if league_id == LEAGUE else []):
        _install_sess(_mk_sess())
        code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")

    assert a["picks"]["value_label"] == "≈0.5 firsts"          # 2/3.5 → 0.57
    assert a["picks"]["value_label"] == _aggregate_pick_label(0.0, 2 / 3.5)
    # The trap has teeth: the dollar-space conversion provably disagrees.
    assert _aggregate_pick_label(a["picks"]["value"]) == "≈1 firsts"
    assert a["picks"]["value_label"] != _aggregate_pick_label(a["picks"]["value"])

    # A 3rd-round-only holding honestly labels zero (never a missing key —
    # the client's count>0 gate decides whether the segment renders).
    assert b["picks"]["value_label"] == "≈0 firsts"

    # And the dollar-priced `picks.value` is the PRICED sum (D-148), not the
    # stored ladder — pinned literally so a regression to either the ladder
    # or a different fixture shape fails here rather than silently.
    assert a["picks"]["value"] == round(
        2 * _priced(2026, 2, 0) + 3 * _priced(2026, 3, 0), 1) == 1654.9
    assert a["picks"]["value"] != round(
        2 * pick_pool_value(2, 0) + 3 * pick_pool_value(3, 0), 1)


def test_picks_value_label_present_with_default_fixture(client):
    """The module fixture path too (u_a: 1st + 2nd → 1.0 + 1/3.5 → ≈1.5;
    u_b: a lone 3rd → ≈0) — no experiment, plain client, ungated."""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")
    assert a["picks"]["value_label"] == _aggregate_pick_label(0.0, 1.0 + 1 / 3.5)
    assert b["picks"]["value_label"] == "≈0 firsts"


def test_aggregate_pick_label_reuses_pick_gap_equivalent_firsts():
    """Conversion correctness: the aggregate label's number IS
    _pick_gap_equivalent's `firsts` (the SAME generic-Mid-1st denomination
    already shown as "a Late 2nd" on trade cards), rounded to the nearest
    half-first and phrased — never a second, independently-computed scale."""
    for value in (0.0, 60.0, 250.0, 4200.7, 14820.0):
        firsts = _pick_gap_equivalent(value)["firsts"]
        half = round(firsts * 2) / 2
        assert _aggregate_pick_label(value) == f"≈{half:g} firsts"
    # Monotonic: a bigger aggregate never yields a smaller label value.
    assert _pick_gap_equivalent(14820.0)["firsts"] > _pick_gap_equivalent(250.0)["firsts"]


# ---------------------------------------------------------------------------
# #285 — operator bug on the aggregate_tier_labels experiment: "Draft picks
# should be summed into the league/team values. Keep it simple. 1sts equal
# firsts, 3-4 2nds equal a 1st. No other picks included." Covers
# _pick_firsts_equivalent's pick-sum correctness in isolation, the
# _aggregate_pick_label(value, pick_firsts) wiring, and the route-level
# label math end to end (positions_value + literal pick count, never
# total_value — see docs/feedback/items/285-pick-sums/status.md).
# ---------------------------------------------------------------------------

def test_pick_firsts_equivalent_counts_1sts_and_2nds_ignores_3rds_plus():
    items = [
        {"round": 1, "value": 999.0}, {"round": 1, "value": 1.0},
        {"round": 2, "value": 999.0},
        {"round": 3, "value": 999.0},
        {"round": 4, "value": 999.0},
    ]
    # 2 firsts (1.0 each) + 1 second (1/3.5) — dollar `value` plays no part;
    # 3rd/4th round picks contribute exactly nothing regardless of value.
    assert server._pick_firsts_equivalent(items) == pytest.approx(2.0 + 1 / 3.5)


def test_pick_firsts_equivalent_empty_and_unrecognized_round():
    assert server._pick_firsts_equivalent([]) == 0.0
    # Missing/None `round` (e.g. a pre-#285 caller's item shape) contributes
    # nothing, same as round >= 3 — never raises.
    assert server._pick_firsts_equivalent([{"value": 5.0}]) == 0.0
    assert server._pick_firsts_equivalent([{"round": None, "value": 5.0}]) == 0.0


def test_aggregate_pick_label_pick_firsts_defaults_to_zero_backward_compatible():
    # Every pre-#285 call site omits `pick_firsts` — must be byte-identical.
    for value in (0.0, 250.0, 4200.7):
        assert _aggregate_pick_label(value) == _aggregate_pick_label(value, 0.0)


def test_aggregate_pick_label_adds_pick_firsts_before_rounding():
    base_firsts = _pick_gap_equivalent(250.0)["firsts"]
    combined = round((base_firsts + 1.2857142857142856) * 2) / 2
    assert _aggregate_pick_label(250.0, 1.2857142857142856) == f"≈{combined:g} firsts"


def test_power_picks_by_owner_carries_round_for_pick_sum_math(client):
    # Source of truth for #285: _power_picks_by_owner already loads the
    # draft-capital rows the picks group renders from — round rides along
    # as an additive field (compute_power_rankings still serializes only
    # label/value, so the general payload is unaffected — see the byte-
    # identical test above and the byte-identical assertion below).
    picks = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    assert [i["round"] for i in picks["u_a"]] == [1, 2]
    assert [i["round"] for i in picks["u_b"]] == [3]


def test_route_total_label_sums_owned_picks_1sts_and_2nds_ignores_3rd(
        client, exp_engine, monkeypatch):
    """End-to-end #285: the allowlisted caller's team TOTAL label folds in
    owned picks via the operator's literal count, sourced from the SAME
    draft-capital data the picks group already renders (PICK_ROWS: u_a
    owns a 2026 1st + a 2027 2nd; u_b owns only a 2026 3rd)."""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_a")
    _mk_aggregate_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_a"))
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    a = next(t for t in body["teams"] if t["user_id"] == "u_a")
    b = next(t for t in body["teams"] if t["user_id"] == "u_b")

    a_firsts = _pick_gap_equivalent(a["positions_value"])["firsts"] + 1.0 + 1 / 3.5
    a_half = round(a_firsts * 2) / 2
    assert a["total_value_label"] == f"≈{a_half:g} firsts"

    # u_b's lone owned pick is a 3rd — the label is identical to having no
    # picks at all, even though `positions_value`/`total_value` differ.
    assert b["total_value_label"] == _aggregate_pick_label(b["positions_value"])
    assert b["total_value_label"] == _aggregate_pick_label(b["positions_value"], 0.0)

    # `total_value` itself is untouched by #285 — still positions + the
    # DOLLAR-priced picks.value (unrelated to the label's literal count).
    assert a["total_value"] == round(a["positions_value"] + a["picks"]["value"], 1)
    assert b["total_value"] == round(b["positions_value"] + b["picks"]["value"], 1)


# ---------------------------------------------------------------------------
# #300 — `medians`: the league median positional value + its pick-equivalent
# label, for the single-position median divider on the League rankings list
# (docs/feedback/items/300-league-rankings-trade-candidates/
# operator-answers-2026-08-12.md — the frozen design).
#
# The field exists because the client can compute the median VALUE but cannot
# LABEL it. Every test below therefore asserts LABEL CONTENT, not key presence:
# a test that only checked `"medians" in body` would pass on a build that
# labelled the mean, the max, or nothing at all.
# ---------------------------------------------------------------------------

def _label_of(value: float) -> str:
    """The expected label, recomputed from `_pick_gap_equivalent` rather than
    by calling `_aggregate_pick_label` — so these tests pin the LABEL STRING,
    not merely 'whatever that helper returns'."""
    half = round(_pick_gap_equivalent(max(value, 0.0))["firsts"] * 2) / 2
    return f"≈{half:g} firsts"


def _teams_with_qb(*values: float) -> list[dict]:
    """`teams`-shaped rows carrying only what `_position_medians` reads."""
    return [{"user_id": f"u_{i}",
             "positions": {"QB": {"count": 1, "value": v},
                           "RB": {"count": 0, "value": 0.0},
                           "WR": {"count": 0, "value": 0.0},
                           "TE": {"count": 0, "value": 0.0}}}
            for i, v in enumerate(values)]


def test_medians_odd_count_is_the_middle_team_not_the_mean():
    # mean = 4000.0, median = 2000.0 — deliberately far enough apart that the
    # half-first rounding cannot collapse the two labels together.
    teams = _teams_with_qb(1000.0, 2000.0, 9000.0)
    med = server._position_medians(teams)
    assert med["QB"]["value"] == 2000.0
    assert med["QB"]["value_label"] == _label_of(2000.0) == "≈1 firsts"
    assert med["QB"]["value_label"] != _label_of(4000.0)      # not the mean
    assert med["QB"]["value_label"] != _label_of(9000.0)      # not the max


def test_medians_even_count_averages_the_two_middle_values():
    """Recorded convention: the textbook median (mean of the two middle
    values), NOT the lower-middle team — so an even league leaves no team
    sitting on the line and an odd one leaves exactly one, which is what the
    frozen design's 'At median' case depends on."""
    teams = _teams_with_qb(1000.0, 2000.0, 9000.0, 10000.0)
    med = server._position_medians(teams)
    assert med["QB"]["value"] == 5500.0                       # (2000+9000)/2
    assert med["QB"]["value_label"] == _label_of(5500.0) == "≈2.5 firsts"
    assert med["QB"]["value"] != 2000.0                       # not lower-middle
    assert med["QB"]["value_label"] != _label_of(2000.0)


def test_medians_cover_exactly_the_four_core_positions():
    med = server._position_medians(_teams_with_qb(1000.0, 2000.0, 9000.0))
    assert set(med) == {"QB", "RB", "WR", "TE"}
    for pos in ("RB", "WR", "TE"):
        # No holdings anywhere → a real 0.0 median with a real label, never
        # a missing key the client has to branch on.
        assert med[pos] == {"value": 0.0, "value_label": _label_of(0.0)}


def test_medians_empty_teams_is_empty_dict():
    """No list ⇒ no divider. Never a fabricated 0.0 across four positions."""
    assert server._position_medians([]) == {}


def test_route_serves_medians_unflagged_with_correct_labels(client):
    """De-gating proof, part 1: the `client` fixture pins every feature flag
    OFF and runs with no experiment at all — `medians` and its LABELS are
    still served, and the labels match the payload's own team values."""
    _install_sess(_mk_sess())
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert set(body["medians"]) == {"QB", "RB", "WR", "TE"}
    for pos in ("QB", "RB", "WR", "TE"):
        vals = sorted(t["positions"][pos]["value"] for t in body["teams"])
        mid = len(vals) // 2
        expected = round(vals[mid] if len(vals) % 2
                         else (vals[mid - 1] + vals[mid]) / 2.0, 1)
        assert body["medians"][pos]["value"] == expected
        assert body["medians"][pos]["value_label"] == _label_of(expected)
    # ...and post-graduation (#306/D-306-1) the per-team labels ride along
    # ungated too — medians led, the team keys followed.
    assert all("value_label" in pv
               for t in body["teams"] for pv in t["positions"].values())


def test_route_medians_label_ungated_for_non_allowlisted_caller(
        client, exp_engine, monkeypatch):
    """De-gating proof, part 2: with the `aggregate_tier_labels` experiment
    RUNNING and the caller NOT targeted, `medians[P].value_label` is a real
    label. Historically this pinned the divider's deliberate gate bypass;
    post-graduation (#306/D-306-1) the per-team labels are ungated too, so
    both assertions now point the same direction."""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_a")   # u_b is NOT listed
    _mk_aggregate_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_b"))
    code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    assert all("value_label" in pv
               for t in body["teams"] for pv in t["positions"].values())
    for pos in ("QB", "RB", "WR", "TE"):
        vals = sorted(t["positions"][pos]["value"] for t in body["teams"])
        mid = len(vals) // 2
        expected = round(vals[mid] if len(vals) % 2
                         else (vals[mid - 1] + vals[mid]) / 2.0, 1)
        assert body["medians"][pos]["value_label"] == _label_of(expected)


# The caller-inclusion league: three teams, the CALLER holding the only
# high-value QB and a third team holding none. QB values sort to
# [0.0, 1000.0, 4481.7], so the median WITH the caller is 1000.0 ("≈0.5
# firsts") and the median WITHOUT them would be 500.0 ("≈0 firsts") — the two
# populations disagree in both the value AND the label.
_MEMBERS_3 = [
    {"user_id": "u_a", "username": "alice", "display_name": "Alice",
     "player_ids": ["qb1"]},                     # 1800 elo → 4481.7
    {"user_id": "u_b", "username": "bob", "display_name": "Bob",
     "player_ids": ["qb2"]},                     # 1500 elo → 1000.0
    {"user_id": "u_c", "username": "cy", "display_name": "Cy",
     "player_ids": ["rb2"]},                     # no QB → 0.0
]


def test_route_medians_population_includes_the_calling_team(client):
    """Recorded decision: the median is taken over EVERY team in the payload,
    the caller included — the frozen design keeps the caller's own team in the
    list as the anchor, so the line must be drawn across that same list."""
    with patch.object(server, "load_league_members",
                      lambda lid: [dict(m) for m in _MEMBERS_3]
                      if lid == LEAGUE else []):
        _install_sess(_mk_sess(user_id="u_a"))
        code, body = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
    assert code == 200
    caller = next(t for t in body["teams"] if t["is_you"])
    others = sorted(t["positions"]["QB"]["value"]
                    for t in body["teams"] if not t["is_you"])
    assert caller["positions"]["QB"]["value"] == round(elo_to_value(1800), 1)

    with_caller = 1000.0                                   # middle of three
    without_caller = round((others[0] + others[1]) / 2.0, 1)   # 500.0
    assert with_caller != without_caller
    assert body["medians"]["QB"]["value"] == with_caller
    assert body["medians"]["QB"]["value_label"] == _label_of(with_caller)
    assert body["medians"]["QB"]["value_label"] != _label_of(without_caller)


def test_route_medians_are_basis_aware(client):
    """The medians are computed over the SAME `teams` the request priced, so a
    personal-basis read gets personal-basis medians for free."""
    class _Board:
        def get_rankings(self, position=None):
            return SimpleNamespace(rankings=[
                SimpleNamespace(player=SimpleNamespace(id="qb2"), elo=1900.0)])

    with patch.object(server, "load_league_members",
                      lambda lid: [dict(m) for m in _MEMBERS_3]
                      if lid == LEAGUE else []), \
         patch.object(server, "_verified_read_denial", lambda sess: None):
        _install_sess(_mk_sess(user_id="u_a"))
        _, consensus = _get(client, f"/api/league/power-rankings?league_id={LEAGUE}")
        _install_sess(_mk_sess(user_id="u_a", svc=_Board()))
        code, personal = _get(
            client, f"/api/league/power-rankings?league_id={LEAGUE}&basis=personal")
    assert code == 200
    # The board pumps qb2 1500 → 1900, which lifts it PAST qb1 — so the QB
    # values re-sort to [0.0, 4481.7, 7389.1] and the median team changes
    # from Bob to Alice. The label moves with the median.
    assert consensus["medians"]["QB"]["value"] == 1000.0
    assert personal["medians"]["QB"]["value"] == round(elo_to_value(1800.0), 1)
    assert personal["medians"]["QB"]["value_label"] == _label_of(
        round(elo_to_value(1800.0), 1))
    assert (personal["medians"]["QB"]["value_label"]
            != consensus["medians"]["QB"]["value_label"])
