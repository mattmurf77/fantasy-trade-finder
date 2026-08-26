"""Unit layer for `backend/negmem.py` — negative-results memory (flag
`trade.negmem`, default OFF).

Spec: docs/plans/negative-results-memory/LLD.md (FINAL) — §10's N-plan. This
file carries the tests that need NO engine seam (the seam/golden tests N-7..
N-13, N-17..N-20, N-25, N-27 and the call-site halves of N-15/N-21 belong to
the seam wave, which owns trade_service.py / trade_gen_*.py / server.py /
bakeoff_runner.py / the knob + flag registrations).

Covered here:

  N-1  admission closed-list matrix          (§5.2 — R1(a)-(e) as executed checks)
  N-2  undo-replay table                     (§5.2 — one net disposition per impression)
  N-3  decay + shrinkage worked examples     (§4.3/§4.4, incl. the five OQ-4b
                                              threshold assertions and the sat_k sweep)
  N-4  combine rule is MIN, never product    (§4.4 / DE-1)
  N-5  effective_mult invariants             (§4.6 / C2 — total function, purity)
  N-6  netting order + clamp bounds          (§4.5 / DE-2) and the §5.3
                                              retraction/revive/NULL-created_at rules
  N-14 determinism, as-of, immutability      (C5 + H-4)
  N-15 M2 E-B parity + the lookback window   (C4 — feed x acceptance_prior)
  N-16 M2 feed guard + zero-response keys    (§5.4)
  N-19 degraded + failure taxonomy (builder half)   (§8.1)
  N-21 identity hygiene + unmapped drop      (R9 / DE-5)
  N-22 horizon + epoch day-prefix boundaries (§4.7/§5.1 — asserted on FETCHED ROW COUNT)
  N-23 SQL dialect portability               (banned-token scan + real execution)
  N-24 leaf import contract                  (D-2 / T1)
  N-26 readout format                        (§7.1)

Every knob value is a LITERAL in this file (trap-7): the module holds no
defaults, and a test that read them from model_config would move whenever the
seed rows moved.
"""

from __future__ import annotations

import ast
import json
import math
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from backend import database as db
from backend import negmem
from backend.database import (
    deck_impressions_table,
    deck_outcomes_table,
    league_members_table,
    metadata,
    trade_decisions_table,
    trade_matches_table,
    trade_pass_reasons_table,
)

REPO = Path(__file__).resolve().parents[2]

# --- pinned knobs (literals — never read from model_config here) -----------
K_HALFLIFE = 45.0
K_MIN_EVIDENCE = 3.0
K_SAT_K = 3.0
K_LIKE_NET = 1.0
K_FLOOR = 0.6
K_ACCEPT_STRENGTH = 10.0
K_ACCEPT_P0 = 0.5

BUILD_KNOBS = dict(
    halflife_days=K_HALFLIFE,
    min_evidence=K_MIN_EVIDENCE,
    sat_k=K_SAT_K,
    like_net=K_LIKE_NET,
    floor_b=K_FLOOR,
    accept_prior_strength=K_ACCEPT_STRENGTH,
)

READOUT_KNOBS = {
    "negmem_strength": 1.0,
    "negmem_floor": K_FLOOR,
    "negmem_min_evidence": K_MIN_EVIDENCE,
    "negmem_halflife_days": K_HALFLIFE,
    "negmem_sat_k": K_SAT_K,
    "negmem_like_net": K_LIKE_NET,
    "gen2_accept_prior_strength": K_ACCEPT_STRENGTH,
    "gen2_accept_global_prior": K_ACCEPT_P0,
}

# --- world coordinates ------------------------------------------------------
LEAGUE = "L1"
OTHER_LEAGUE = "L_other"
USER = "U"
AS_OF = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
AS_OF_ISO = AS_OF.isoformat()
# 12 canonical league_members ids (ADR-012 single-valued owner ids).
MEMBERS = ["U", "X", "Y", "Z", "W", "Q",
           "M07", "M08", "M09", "M10", "M11", "M12"]
# The DE-5 case: a response recorded under an account-side co-owner id that is
# NOT a league_members row.
CO_OWNER_ACCT = "acct_co_owner"


# ---------------------------------------------------------------------------
# Fixture plumbing
# ---------------------------------------------------------------------------

def _iso(days_before_as_of: float) -> str:
    return (AS_OF - timedelta(days=days_before_as_of)).isoformat()


@contextmanager
def _memdb():
    """Harness pattern 1 — isolated in-memory DB, module attribute patched."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db, "engine", engine):
        yield engine


@contextmanager
def _allowlist(entries):
    """Point the allowlist loader at an in-test value (60s cache reset both
    ways so neighbouring tests never inherit it)."""
    negmem._reset_allowlist_cache()
    try:
        with patch.object(negmem, "_read_allowlist_uncached",
                          lambda: frozenset(entries)):
            yield
    finally:
        negmem._reset_allowlist_cache()


class _Seeder:
    def __init__(self, engine):
        self.engine = engine
        self._n = 0

    def impression(self, partner, *, served_at, league=LEAGUE, user=USER,
                   is_ghost=None, assets=None, lane="window",
                   user_value_basis="personal", trade_intent=None,
                   features_json=None, shape_bucket="1x1"):
        self._n += 1
        imp = f"imp{self._n:03d}"
        if features_json is None:
            features_json = json.dumps({
                "partner_user_id": partner,
                "lane": lane,
                "user_value_basis": user_value_basis,
            })
        with self.engine.begin() as conn:
            conn.execute(deck_impressions_table.insert().values(
                impression_id=imp, user_id=user, league_id=league,
                deck_job_id="job1", card_index=0, trade_hash=f"h{self._n}",
                features_json=features_json, propensity=1.0,
                served_at=served_at, is_ghost=is_ghost,
                assets_json=(json.dumps(assets) if assets is not None else None),
                shape_bucket=shape_bucket, trade_intent=trade_intent,
            ))
        return imp

    def outcome(self, imp, action, acted_at):
        with self.engine.begin() as conn:
            conn.execute(deck_outcomes_table.insert().values(
                impression_id=imp, action=action, acted_at=acted_at))

    def reason(self, imp, reason, *, key_source="impression", detail=None,
               league=LEAGUE, user=USER, created_at=None):
        created_at = created_at or AS_OF_ISO
        with self.engine.begin() as conn:
            conn.execute(trade_pass_reasons_table.insert().values(
                impression_id=imp, user_id=user, league_id=league,
                key_source=key_source, reason=reason, detail=detail,
                created_at=created_at, updated_at=created_at))

    def decision(self, decision, give, receive, *, created_at,
                 retracted_at=None, league=LEAGUE, user=USER):
        with self.engine.begin() as conn:
            conn.execute(trade_decisions_table.insert().values(
                user_id=user, league_id=league, decision=decision,
                give_player_ids=json.dumps(give),
                receive_player_ids=json.dumps(receive),
                created_at=created_at, retracted_at=retracted_at))

    def match(self, other, decision, decided_at, *, league=LEAGUE, user=USER):
        with self.engine.begin() as conn:
            conn.execute(trade_matches_table.insert().values(
                league_id=league, user_a_id=user, user_b_id=other,
                user_a_give="[]", user_a_receive="[]",
                matched_at=decided_at, status="pending",
                user_a_decision=None, user_b_decision=decision,
                user_a_decided_at=None, user_b_decided_at=decided_at))

    def members(self, ids, league=LEAGUE):
        with self.engine.begin() as conn:
            for uid in ids:
                conn.execute(league_members_table.insert().values(
                    league_id=league, user_id=uid, username=uid,
                    display_name=uid, updated_at=AS_OF_ISO))


# The two retraction asset sets (§5.3 fixture cases).
A_RELIKE = {"give": ["p1"], "receive": ["p2"]}          # case (ii) revive
A_RETRACTED = {"give": ["p3"], "receive": ["p4"]}       # case (i) still retracted
A_PASS = {"give": ["p5"], "receive": ["p6"]}            # case (iii) retracted pass


def _seed_world(engine) -> _Seeder:
    """The shared `_negmem_world` of LLD §10.

    X: 5 admitted `value` passes (crosses min_evidence) — the fixture-power
    partner. Y: 2 admitted `value` passes (sub-threshold). Z: 3 `fit` passes
    + 1 admitted netting like (the revive case). W: 1 like that is still
    retracted (⇒ no cells at all). Q: the whole inadmissible matrix.
    """
    s = _Seeder(engine)
    s.members(MEMBERS)

    # --- X: five admitted value passes; the last carries the case-(iii)
    #     asset set (a retracted pass superseded by a later live pass).
    for i, day in enumerate([10, 8, 6, 4, 2]):
        assets = A_PASS if i == 4 else None
        imp = s.impression("X", served_at=_iso(day + 0.2), assets=assets)
        s.outcome(imp, "viewed", _iso(day))
        s.outcome(imp, "pass", _iso(day))
        s.reason(imp, "value")

    # --- Y: two admitted value passes (stays below min_evidence)
    for day in (9, 3):
        imp = s.impression("Y", served_at=_iso(day + 0.2))
        s.outcome(imp, "viewed", _iso(day))
        s.outcome(imp, "pass", _iso(day))
        s.reason(imp, "value")

    # --- Z: three admitted fit passes + one admitted netting like
    for day in (12, 7, 5):
        imp = s.impression("Z", served_at=_iso(day + 0.2), lane="win_now")
        s.outcome(imp, "viewed", _iso(day))
        s.outcome(imp, "pass", _iso(day))
        s.reason(imp, "fit")
    imp = s.impression("Z", served_at=_iso(1.2), assets=A_RELIKE)
    s.outcome(imp, "viewed", _iso(1))
    s.outcome(imp, "like", _iso(1))

    # --- W: one like whose decision row is STILL retracted ⇒ dropped
    imp = s.impression("W", served_at=_iso(1.2), assets=A_RETRACTED)
    s.outcome(imp, "viewed", _iso(1))
    s.outcome(imp, "like", _iso(1))

    # --- Q: the inadmissible matrix (one row per R1 clause)
    ghost = s.impression("Q", served_at=_iso(5.2), is_ghost=1)
    s.outcome(ghost, "viewed", _iso(5))
    s.outcome(ghost, "pass", _iso(5))
    s.reason(ghost, "value")

    unviewed = s.impression("Q", served_at=_iso(5.2))
    s.outcome(unviewed, "pass", _iso(5))
    s.reason(unviewed, "value")

    other_fam = s.impression("Q", served_at=_iso(5.2))
    s.outcome(other_fam, "viewed", _iso(5))
    s.outcome(other_fam, "pass", _iso(5))
    s.reason(other_fam, "other")

    local_key = s.impression("Q", served_at=_iso(5.2))
    s.outcome(local_key, "viewed", _iso(5))
    s.outcome(local_key, "pass", _iso(5))
    s.reason(local_key, "value", key_source="local")

    undone = s.impression("Q", served_at=_iso(5.2))
    s.outcome(undone, "viewed", _iso(5))
    s.outcome(undone, "pass", _iso(5))
    s.outcome(undone, "undo", _iso(4.9))
    s.reason(undone, "value")

    pre_epoch = s.impression("Q", served_at="2026-08-19T23:59:00+00:00")
    s.outcome(pre_epoch, "viewed", "2026-08-19T23:59:30+00:00")
    s.outcome(pre_epoch, "pass", "2026-08-19T23:59:30+00:00")
    s.reason(pre_epoch, "value")

    # --- trade_decisions: the three retraction histories (§5.3)
    #  (i)  like still retracted
    s.decision("like", A_RETRACTED["give"], A_RETRACTED["receive"],
               created_at=_iso(1), retracted_at=_iso(0.5))
    #  (ii) revive: older retracted like, NEWER live like, identical asset sets
    s.decision("like", A_RELIKE["give"], A_RELIKE["receive"],
               created_at=_iso(20), retracted_at=_iso(19))
    s.decision("like", A_RELIKE["give"], A_RELIKE["receive"],
               created_at=_iso(1), retracted_at=None)
    #  (iii) retracted pass superseded by a later live pass
    s.decision("pass", A_PASS["give"], A_PASS["receive"],
               created_at=_iso(30), retracted_at=_iso(29))
    s.decision("pass", A_PASS["give"], A_PASS["receive"],
               created_at=_iso(2), retracted_at=None)

    # --- trade_matches: X = 2 accepts / 5 responses, plus one co-owner
    #     account-side response that is NOT a league member (DE-5).
    for i, dec in enumerate(["accept", "accept", "decline", "decline", "decline"]):
        s.match("X", dec, _iso(20 + i))
    s.match(CO_OWNER_ACCT, "accept", _iso(15))
    return s


def _build_world(engine, **overrides):
    knobs = dict(BUILD_KNOBS)
    knobs.update(overrides)
    with _allowlist({LEAGUE}):
        return negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO, **knobs)


# ---------------------------------------------------------------------------
# N-1 — the closed admission list, exercised on the predicate in isolation
# ---------------------------------------------------------------------------

def _spine_row(**over) -> dict:
    """One fetched outcome row, keys EXACTLY the _SPINE_SQL select list and
    values as the DB would return them (Text stays str; is_ghost stays int or
    None, never coerced to bool)."""
    row = {
        "impression_id": "i1",
        "served_at": _iso(5.2),
        "features_json": json.dumps({"partner_user_id": "X", "lane": "window",
                                     "user_value_basis": "consensus"}),
        "is_ghost": None,
        "assets_json": None,
        "shape_bucket": "1x1",
        "trade_intent": None,
        "outcome_id": 1,
        "action": "pass",
        "acted_at": _iso(5),
        "reason": "value",
        "detail": None,
        "key_source": "impression",
    }
    row.update(over)
    return row


def _admit(rows, retracted=frozenset()):
    return negmem._admit_events(rows, as_of_dt=AS_OF, retracted_keys=set(retracted))


def test_n1_admission_closed_list_matrix():
    """N-1: each R1 clause excludes exactly its row; the SQL bound + the Python
    predicate together are the closed list."""
    base_id = 0
    # The LEFT JOIN puts the impression-level and reason-level columns on EVERY
    # row of a group; only action/acted_at/outcome_id vary per outcome row. The
    # fixture reproduces that faithfully.
    outcome_level = {"action", "acted_at", "outcome_id"}

    def case(**over):
        nonlocal base_id
        base_id += 1
        imp = f"i{base_id}"
        shared = {k: v for k, v in over.items() if k not in outcome_level}
        rows = [_spine_row(impression_id=imp, outcome_id=base_id * 10,
                           action="viewed", acted_at=_iso(5.1), **shared),
                _spine_row(impression_id=imp, outcome_id=base_id * 10 + 1,
                           **over)]
        return rows

    # (baseline) a fully admissible pass
    ev, net, errs = _admit(case())
    assert len(ev) == 1 and ev[0]["partner"] == "X" and ev[0]["family"] == "value"
    assert net == [] and errs == 0

    # (a) viewed gate — no viewed row at all
    ev, _net, _e = _admit([_spine_row()])
    assert ev == []

    # (a') viewed AFTER the decision still admits (batched side-channel race)
    imp_rows = [_spine_row(impression_id="ilate", outcome_id=1, action="pass",
                           acted_at=_iso(5)),
                _spine_row(impression_id="ilate", outcome_id=2,
                           action="viewed", acted_at=_iso(4.9))]
    ev, _net, _e = _admit(imp_rows)
    assert len(ev) == 1

    # (b) reason clauses: NULL reason, 'other', and key_source='local'
    for over in ({"reason": None, "key_source": None},
                 {"reason": "other"},
                 {"key_source": "local"}):
        ev, _net, _e = _admit(case(**over))
        assert ev == [], over

    # (c) ghost exclusion — is_ghost is an int, never coerced to bool
    ev, _net, _e = _admit(case(is_ghost=1))
    assert ev == []
    ev, _net, _e = _admit(case(is_ghost=0))      # 0 and NULL are both not-ghost
    assert len(ev) == 1

    # (d) retraction leg — the asset key of a currently-retracted pass
    assets = json.dumps({"give": ["p5"], "receive": ["p6"]})
    key = ("pass", frozenset({"p5"}), frozenset({"p6"}))
    ev, _net, _e = _admit(case(assets_json=assets), retracted={key})
    assert ev == []
    ev, _net, _e = _admit(case(assets_json=assets))
    assert len(ev) == 1

    # not_interested rides the same evidence branch as pass
    ev, _net, _e = _admit(case(action="not_interested"))
    assert len(ev) == 1

    # a partnerless card cannot key a partner-keyed prior — counted, skipped
    ev, _net, errs = _admit(case(features_json=json.dumps({"lane": "window"})))
    assert ev == [] and errs == 1

    # `propose` survivors contribute nothing to either list
    ev, net, _e = _admit(case(action="propose", reason=None, key_source=None))
    assert ev == [] and net == []


def test_n1_context_tags_recorded_not_consulted():
    """R11 tags ride on the event; a personal-basis `value` row gets a
    basis_note TAG, never a family change (re-keying would silently merge two
    objection classes under the MIN combine)."""
    shared = dict(trade_intent="tier_up",
                  features_json=json.dumps({"partner_user_id": "X",
                                            "lane": "window",
                                            "user_value_basis": "personal"}))
    rows = [_spine_row(outcome_id=1, action="viewed", acted_at=_iso(5.1),
                       **shared),
            _spine_row(outcome_id=2, **shared)]
    ev, _net, _e = _admit(rows)
    assert ev[0]["family"] == "value"
    assert ev[0]["context_tags"] == {"lane": "window",
                                     "user_value_basis": "personal",
                                     "trade_intent": "tier_up",
                                     "basis_note": "board-fit"}


# ---------------------------------------------------------------------------
# N-2 — per-impression undo replay
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("actions,expect_evidence,expect_netting", [
    (["pass", "undo"], 0, 0),
    (["pass", "undo", "pass"], 1, 0),
    (["like", "undo"], 0, 0),
    (["undo"], 0, 0),                       # stray undo — no-op
    (["pass", "pass", "undo"], 1, 0),       # dup labels are legal
    (["pass", "undo", "pass", "undo"], 0, 0),
    (["pass", "like"], 0, 1),               # last survivor wins
    (["like", "pass"], 1, 0),
    # The two cases that actually SEPARATE "pop the most recent" from "pop the
    # oldest": with a 2-deep stack the surviving disposition differs in KIND.
    (["pass", "like", "undo"], 1, 0),       # pops the like ⇒ evidence survives
    (["like", "pass", "undo"], 0, 1),       # pops the pass ⇒ netting survives
])
def test_n2_undo_replay_table(actions, expect_evidence, expect_netting):
    """N-2: one net disposition per impression; undo pops the MOST RECENT
    surviving decision."""
    rows = [_spine_row(outcome_id=0, action="viewed", acted_at=_iso(9))]
    for i, action in enumerate(actions):
        rows.append(_spine_row(outcome_id=i + 1, action=action,
                               acted_at=_iso(8 - i)))
    ev, net, _e = _admit(rows)
    assert len(ev) == expect_evidence
    assert len(net) == expect_netting


def test_n2_dup_rows_never_double_count():
    """Two `pass` rows on one impression contribute at most ONE evidence unit
    (the replay is impression-keyed)."""
    rows = [_spine_row(outcome_id=0, action="viewed", acted_at=_iso(9)),
            _spine_row(outcome_id=1, action="pass", acted_at=_iso(8)),
            _spine_row(outcome_id=2, action="pass", acted_at=_iso(7))]
    ev, _net, _e = _admit(rows)
    assert len(ev) == 1


def test_n2_acted_after_as_of_is_invisible():
    """R6 as-of reconstruction: an undo landing after as_of is not seen by this
    build (and a later build sees it)."""
    rows = [_spine_row(outcome_id=0, action="viewed", acted_at=_iso(9)),
            _spine_row(outcome_id=1, action="pass", acted_at=_iso(8)),
            _spine_row(outcome_id=2, action="undo", acted_at=_iso(-1))]
    ev, _net, _e = _admit(rows)
    assert len(ev) == 1
    ev, _net, _e = negmem._admit_events(
        rows, as_of_dt=AS_OF + timedelta(days=2), retracted_keys=set())
    assert ev == []


# ---------------------------------------------------------------------------
# N-3 — decay, shrinkage curve, threshold assertions (OQ-4b falsifiable)
# ---------------------------------------------------------------------------

def _ev(day, rid, family="value", partner="X"):
    return {"impression_id": f"e{rid}", "partner": partner, "family": family,
            "ts": AS_OF - timedelta(days=day), "row_id": rid,
            "context_tags": {}}


def _like(day, rid, partner="X"):
    return {"impression_id": f"l{rid}", "partner": partner,
            "ts": AS_OF - timedelta(days=day), "row_id": rid,
            "context_tags": {}}


def _fold(evidence, netting=(), **over):
    kw = dict(halflife_days=K_HALFLIFE, like_net=K_LIKE_NET,
              min_evidence=K_MIN_EVIDENCE, floor_b=K_FLOOR, sat_k=K_SAT_K)
    kw.update(over)
    return negmem._fold_events(list(evidence), list(netting),
                               as_of_dt=AS_OF, **kw)


def test_n3_decay_worked_example():
    """§4.3 worked example, verbatim: H=45, as_of = day 90, rejections at days
    0, 0, 45, 80 ⇒ n_decayed 1.857, n_raw 4."""
    cells, _pm = _fold([_ev(90, 1), _ev(90, 2), _ev(45, 3), _ev(10, 4)])
    cell = cells[("X", "value")]
    assert cell.n_raw == 4
    assert cell.n_decayed == pytest.approx(1.857, abs=5e-4)


def test_n3_clock_skew_exponent_clamped():
    """A row whose timestamp precedes its predecessor must count at weight 1,
    never amplified (§4.3 max(0, Δ) guard)."""
    skewed = [_ev(10, 1), _ev(12, 2)]        # row_id 2 is EARLIER in time
    cells, _pm = _fold(skewed)
    assert cells[("X", "value")].n_decayed <= 2.0
    assert cells[("X", "value")].n_decayed > 1.0


def test_n3_shrinkage_curve_worked_table():
    """§4.4 worked examples at floor_b=0.6, min_evidence=3, sat_k=3."""
    table = {2.9: 1.000, 3.0: 0.900, 5.0: 0.800, 9.0: 0.720}
    for n_decayed, expected in table.items():
        got = negmem._cell_mult(n_decayed, min_evidence=K_MIN_EVIDENCE,
                                floor_b=K_FLOOR, sat_k=K_SAT_K)
        assert got == pytest.approx(expected, abs=1e-6), n_decayed
    # Asymptote: approached, never reached — at every magnitude a real cell can
    # hold. (At absurd magnitudes the 1e-6 cell rounding makes the value
    # indistinguishable from floor_b; that is the ROUNDING, not the curve, and
    # it is why `floored` stays a RESERVED constant rather than being computed
    # from a `mult == floor_b` comparison.)
    for n in (20.0, 50.0, 100.0):
        assert negmem._cell_mult(n, min_evidence=K_MIN_EVIDENCE,
                                 floor_b=K_FLOOR, sat_k=K_SAT_K) > K_FLOOR
    assert negmem._cell_mult(1e9, min_evidence=K_MIN_EVIDENCE,
                             floor_b=K_FLOOR,
                             sat_k=K_SAT_K) == pytest.approx(K_FLOOR, abs=1e-6)


@pytest.mark.parametrize("sat_k,step_mult", [(3.0, 0.900), (7.0, 0.950),
                                             (19.0, 0.980)])
def test_n3_threshold_assertions(sat_k, step_mult):
    """The five restored threshold assertions — what makes the OQ-4b
    resolution falsifiable rather than asserted."""
    def mult(n):
        return negmem._cell_mult(n, min_evidence=K_MIN_EVIDENCE,
                                 floor_b=K_FLOOR, sat_k=sat_k)

    # (1) monotone non-increasing in n_decayed
    xs = [i / 20.0 for i in range(0, 400)]
    values = [mult(x) for x in xs]
    assert all(b <= a + 1e-12 for a, b in zip(values, values[1:]))

    # (2) strictly identity everywhere BELOW min_evidence
    assert all(mult(x) == 1.0 for x in xs if x < K_MIN_EVIDENCE)

    # (3) the first non-identity value occurs exactly AT min_evidence
    assert mult(K_MIN_EVIDENCE) < 1.0
    assert mult(math.nextafter(K_MIN_EVIDENCE, 0.0)) == 1.0

    # (4) mult(min_evidence) == 1 − (1 − floor_b)/(1 + sat_k), exactly
    assert mult(K_MIN_EVIDENCE) == pytest.approx(step_mult, abs=1e-6)
    assert mult(K_MIN_EVIDENCE) == pytest.approx(
        1.0 - (1.0 - K_FLOOR) / (1.0 + sat_k), abs=1e-6)


def test_n3_raising_sat_k_shrinks_the_step():
    """(5) — the §8.4 line-8 operator remedy provably works, at the stated cost
    of flatter mid-range damping."""
    def step(k):
        return 1.0 - negmem._cell_mult(K_MIN_EVIDENCE,
                                       min_evidence=K_MIN_EVIDENCE,
                                       floor_b=K_FLOOR, sat_k=k)

    assert step(3.0) > step(7.0) > step(19.0)
    assert step(3.0) == pytest.approx(0.100, abs=1e-6)
    assert step(7.0) == pytest.approx(0.050, abs=1e-6)
    assert step(19.0) == pytest.approx(0.020, abs=1e-6)
    # the stated trade-off: mid-range damping flattens as k rises
    mid = [negmem._cell_mult(K_MIN_EVIDENCE + 2.0, min_evidence=K_MIN_EVIDENCE,
                             floor_b=K_FLOOR, sat_k=k) for k in (3.0, 7.0, 19.0)]
    # LLD §4.4 prints these to 3 dp (0.945 is 0.945455 rounded).
    assert mid == [pytest.approx(v, abs=1e-3) for v in (0.800, 0.880, 0.945)]


def test_n3_degenerate_knobs_are_sanitized_not_fatal():
    """A fat-fingered admin PUT must not produce ZeroDivisionError or mult > 1
    (§2 entry sanitization)."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine, halflife_days=0.0, min_evidence=0.0,
                          sat_k=0.0, floor_b=1.7)
    assert nm is not None and not nm.degraded
    assert all(0.0 <= c.mult <= 1.0 for c in nm.cells.values())


# ---------------------------------------------------------------------------
# N-4 — DE-1 combine rule: MIN, never product
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value_n,fit_n,expected_min,product", [
    # (n_decayed chosen to land on the DE-1 fixture table's mults)
    (5.0, None, 0.800, 0.800),      # value-only evidence — identical, no cost
    (3.0, 3.0, 0.900, 0.810),       # two barely-admitted objections
    (9.0, 3.0, 0.720, 0.648),       # one strong + one weak
])
def test_n4_combine_rule_min(value_n, fit_n, expected_min, product):
    """N-4: partner_mult is the MIN across a partner's family cells. The house
    precedent is F3 fatigue ("never a product — one impression must not be
    triple-counted")."""
    cells = {}
    for family, n in (("value", value_n), ("fit", fit_n)):
        if n is None:
            continue
        cells[("P", family)] = negmem.NegmemCell(
            n_raw=1, n_decayed=n, likes_net=0.0,
            mult=negmem._cell_mult(n, min_evidence=K_MIN_EVIDENCE,
                                   floor_b=K_FLOOR, sat_k=K_SAT_K),
            floored=False)
    mults = [c.mult for c in cells.values()]
    assert min(mults) == pytest.approx(expected_min, abs=1e-6)
    prod = 1.0
    for m in mults:
        prod *= m
    assert prod == pytest.approx(product, abs=1e-6)
    if len(mults) > 1:
        assert min(mults) > prod        # the regression the MIN rule prevents


def test_n4_partner_mult_is_min_on_a_real_build():
    """The same rule, end-to-end through the fold: a partner with evidence in
    two families collapses by MIN, not product."""
    cells, partner_mult = _fold([_ev(0.0, i) for i in range(1, 6)] +
                                [_ev(0.0, 10 + i, family="fit") for i in range(4)])
    assert cells[("X", "value")].mult < 1.0
    assert cells[("X", "fit")].mult < 1.0
    assert partner_mult["X"] == pytest.approx(
        min(cells[("X", "value")].mult, cells[("X", "fit")].mult), abs=1e-9)
    assert partner_mult["X"] > cells[("X", "value")].mult * cells[("X", "fit")].mult


# ---------------------------------------------------------------------------
# N-5 — effective_mult: total function, C2 invariants, purity
# ---------------------------------------------------------------------------

def _map_with(partner_mult: dict, *, degraded=False) -> negmem.NegmemMap:
    return negmem.NegmemMap(
        user_id=USER, league_id=LEAGUE, as_of=AS_OF_ISO, ver=negmem.NEGMEM_VER,
        cells=MappingProxyType({}), partner_mult=MappingProxyType(partner_mult),
        acceptance_stats=MappingProxyType({}), degraded=degraded, build_ms=1.0,
        parse_errors=0, dropped_unmapped_partner_ids=0)


def test_n5_effective_mult_invariants():
    """C2 across the §4.6 behaviour table: eff ∈ [floor, 1]; sink-never-rise;
    strength 0 ⇒ exactly 1.0; NaN / negative / floor>1 all safe.

    Note on the two clamps, because it changes what a sabotage can prove: with
    the `s <= 0` short-circuit in place the UPPER `min(1.0, ·)` is unreachable
    (mult ≤ 1 and s > 0 make the term ≤ 1), so removing it alone cannot move
    any output. It is defence in depth for a future edit that drops the
    short-circuit — and THAT pair is the sabotage this test goes red against.
    The LOWER `max(floor, ·)` is reachable at strength > 1 and is asserted
    directly below.
    """
    for mult in [0.0, 0.2, 0.6, 0.8, 0.9, 1.0]:
        nm = _map_with({"P": mult})
        for strength in [-1.0, -0.001, 0.0, 0.25, 1.0, 2.0, 3.0]:
            for floor in [0.4, 0.6, 1.0, 1.2]:
                eff = negmem.effective_mult(nm, "P", strength=strength,
                                            floor=floor)
                assert eff <= 1.0                      # sink-never-rise
                assert eff >= min(max(floor, 0.0), 1.0) - 1e-12
                if strength <= 0.0:
                    assert eff == 1.0                  # exactly, no float artifact


def test_n5_effective_mult_total_function_table():
    nm = _map_with({"P": 0.8})
    assert negmem.effective_mult(nm, "P", strength=0.5, floor=K_FLOOR) == 0.9
    assert negmem.effective_mult(nm, "P", strength=1.0, floor=K_FLOOR) == 0.8
    assert negmem.effective_mult(nm, "P", strength=2.0, floor=K_FLOOR) == 0.6
    # the LOWER clamp is the reachable one: an operator over-crank cannot push
    # eff past the floor.
    hard = _map_with({"P": 0.0})
    assert negmem.effective_mult(hard, "P", strength=3.0, floor=0.4) == 0.4
    assert negmem.effective_mult(nm, "P", strength=float("nan"),
                                 floor=K_FLOOR) == 1.0
    assert negmem.effective_mult(nm, "P", strength=1.0, floor=1.5) == 1.0
    assert negmem.effective_mult(nm, "unknown", strength=1.0,
                                 floor=K_FLOOR) == 1.0
    assert negmem.effective_mult(None, "P", strength=1.0, floor=K_FLOOR) == 1.0
    assert negmem.effective_mult(_map_with({"P": 0.5}, degraded=True), "P",
                                 strength=1.0, floor=K_FLOOR) == 1.0


def test_n5_effective_mult_is_pure():
    """D-10: no config access, no I/O. Poison the module's DB handle — the
    function must not notice."""
    class _Poison:
        def __getattr__(self, name):
            raise AssertionError(f"effective_mult touched the DB ({name})")

    nm = _map_with({"P": 0.7})
    with patch.object(db, "engine", _Poison()):
        assert negmem.effective_mult(nm, "P", strength=1.0,
                                     floor=K_FLOOR) == 0.7


def test_n5_stamp_payload_shape():
    """§3.3: keys are the families that DROVE partner_mult (mult < 1.0), ev is
    their n_decayed to 2 dp, ver on every variant."""
    cells = {
        ("P", "value"): negmem.NegmemCell(3, 4.25, 0.0, 0.85, False),
        ("P", "fit"): negmem.NegmemCell(1, 1.0, 0.0, 1.0, False),
    }
    nm = negmem.NegmemMap(
        user_id=USER, league_id=LEAGUE, as_of=AS_OF_ISO, ver=negmem.NEGMEM_VER,
        cells=MappingProxyType(cells), partner_mult=MappingProxyType({"P": 0.85}),
        acceptance_stats=MappingProxyType({}), degraded=False, build_ms=1.0,
        parse_errors=0, dropped_unmapped_partner_ids=0)
    stamp = negmem.stamp_payload(nm, "P", 0.85123)
    assert stamp == {"m": 0.8512, "keys": ["value"], "ev": {"value": 4.25},
                     "ver": 1}


# ---------------------------------------------------------------------------
# N-6 — netting bounds, the retraction fold, revive, NULL created_at
# ---------------------------------------------------------------------------

def test_n6_netting_worked_example():
    """§4.5 worked example verbatim: passes day 0, 0, 10; like day 20;
    as_of day 30 ⇒ 1.137 (1.994 without the like). The like also touches the
    (P, fit) cell, which records likes_net only."""
    cells, _pm = _fold([_ev(30, 1), _ev(30, 2), _ev(20, 3)], [_like(10, 9)])
    assert cells[("X", "value")].n_decayed == pytest.approx(1.137, abs=1e-3)
    assert cells[("X", "value")].likes_net == pytest.approx(0.857, abs=1e-3)
    assert cells[("X", "fit")].n_raw == 0
    assert cells[("X", "fit")].n_decayed == 0.0
    assert cells[("X", "fit")].likes_net == pytest.approx(0.857, abs=1e-3)
    no_like, _pm = _fold([_ev(30, 1), _ev(30, 2), _ev(20, 3)])
    assert no_like[("X", "value")].n_decayed == pytest.approx(1.994, abs=1e-3)


def test_n6_like_before_evidence_banks_nothing():
    """Bound (iii): a like that PRECEDES any evidence nets nothing and cannot
    bank credit against future rejections (the per-step clamp)."""
    early_like, _pm = _fold([_ev(5, 1)], [_like(20, 9)])
    no_like, _pm = _fold([_ev(5, 1)])
    assert early_like[("X", "value")].n_decayed == pytest.approx(
        no_like[("X", "value")].n_decayed, abs=1e-9)


def test_n6_one_like_erases_at_most_like_net():
    """Bound (ii): one like erases at most `like_net` decayed units per cell —
    it cannot reset a 5-evidence cell."""
    same_day = [_ev(0.0, i) for i in range(1, 6)]
    with_like, _pm = _fold(same_day, [_like(0.0, 99)])
    without, _pm = _fold(same_day)
    delta = without[("X", "value")].n_decayed - with_like[("X", "value")].n_decayed
    assert delta == pytest.approx(K_LIKE_NET, abs=1e-6)
    assert with_like[("X", "value")].n_decayed >= 3.9


def test_n6_cells_never_go_negative():
    """Bound (i): five likes against one evidence unit clamp at 0.0, and a
    zero cell is identity."""
    cells, _pm = _fold([_ev(10, 1)],
                       [_like(9 - i, 50 + i) for i in range(5)])
    cell = cells[("X", "value")]
    assert cell.n_decayed == 0.0
    assert cell.mult == 1.0
    assert cell.likes_net > 0.0        # transparency figure still recorded


def test_n6_fold_clamp_not_end_clamp():
    """The clamp is per-step, in the as-of domain — an end-clamp would let an
    early like bank credit. Pinned as a direct comparison of the two regimes."""
    evidence = [_ev(5, 1), _ev(4, 2), _ev(3, 3)]
    netting = [_like(20, 9)]        # long BEFORE any evidence
    folded, _pm = _fold(evidence, netting)
    gross, _pm = _fold(evidence)
    assert folded[("X", "value")].n_decayed == pytest.approx(
        gross[("X", "value")].n_decayed, abs=1e-9)
    # ... and the pre-clamp transparency figure is NOT the cancelled mass
    assert folded[("X", "value")].likes_net > 0.0


def test_n6_retracted_keys_latest_row_rule():
    """§5.3: the group's latest row decides. Case (i) stays retracted; case
    (ii) — the documented revive path — must NOT be in retracted_keys."""
    rows = [
        {"id": 1, "decision": "like", "give_player_ids": '["p3"]',
         "receive_player_ids": '["p4"]', "created_at": _iso(1),
         "retracted_at": _iso(0.5)},
        {"id": 2, "decision": "like", "give_player_ids": '["p1"]',
         "receive_player_ids": '["p2"]', "created_at": _iso(20),
         "retracted_at": _iso(19)},
        {"id": 3, "decision": "like", "give_player_ids": '["p1"]',
         "receive_player_ids": '["p2"]', "created_at": _iso(1),
         "retracted_at": None},
        {"id": 4, "decision": "pass", "give_player_ids": '["p5"]',
         "receive_player_ids": '["p6"]', "created_at": _iso(30),
         "retracted_at": _iso(29)},
        {"id": 5, "decision": "pass", "give_player_ids": '["p5"]',
         "receive_player_ids": '["p6"]', "created_at": _iso(2),
         "retracted_at": None},
    ]
    keys = negmem._retracted_keys(rows)
    assert ("like", frozenset({"p3"}), frozenset({"p4"})) in keys
    assert ("like", frozenset({"p1"}), frozenset({"p2"})) not in keys
    assert ("pass", frozenset({"p5"}), frozenset({"p6"})) not in keys


def test_n6_retraction_id_coercion_both_sides():
    """Player ids are strings in the impression writer and may be INTS in older
    decision rows; frozenset({1}) != frozenset({"1"}) would silently disable
    the whole leg."""
    rows = [{"id": 1, "decision": "like", "give_player_ids": "[1]",
             "receive_player_ids": "[2]", "created_at": _iso(1),
             "retracted_at": _iso(0.5)}]
    keys = negmem._retracted_keys(rows)
    imp_key, ok = negmem._asset_key(
        json.dumps({"give": ["1"], "receive": ["2"]}), "like")
    assert ok and imp_key in keys


def test_n6_null_created_at_never_wins_the_group():
    """DIRECT call of the fold (the row can never arrive from the DB: the fetch
    bounds on substr(created_at,1,10) and substr(NULL,…) is NULL in both
    dialects, so an end-to-end fixture would assert vacuously). The ("", id)
    tie-break is DEFENSIVE ONLY."""
    rows = [
        {"id": 1, "decision": "like", "give_player_ids": '["p9"]',
         "receive_player_ids": '["pA"]', "created_at": None,
         "retracted_at": _iso(0.1)},                       # NULL ⇒ oldest
        {"id": 2, "decision": "like", "give_player_ids": '["p9"]',
         "receive_player_ids": '["pA"]', "created_at": _iso(5),
         "retracted_at": None},
    ]
    assert negmem._retracted_keys(rows) == set()
    # reversed insert order must not change the winner
    assert negmem._retracted_keys(list(reversed(rows))) == set()


def test_n6_retraction_end_to_end_through_the_world():
    """The seeded world's three histories: W's still-retracted like is dropped
    (no cells at all), Z's revived like IS admitted, X's superseded pass is
    admitted."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
        evidence, netting, _errs = negmem.load_admitted_events(
            USER, LEAGUE, as_of=AS_OF_ISO, horizon_floor_day="2026-08-20")
    assert not any(k[0] == "W" for k in nm.cells)          # (i) dropped
    assert [n["partner"] for n in netting] == ["Z"]        # (ii) revived
    assert nm.cells[("X", "value")].n_raw == 5             # (iii) admitted
    assert nm.cells[("Z", "fit")].likes_net > 0.0


def test_n6_revive_lowers_the_cell_vs_retracted_only():
    """The revived like must actually net: Z's fit cell is strictly lower than
    it would be if the like had been dropped."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
        # simulate the sabotage's world: no netting like at all
        evidence, netting, _e = negmem.load_admitted_events(
            USER, LEAGUE, as_of=AS_OF_ISO, horizon_floor_day="2026-08-20")
    no_net, _pm = negmem._fold_events(
        evidence, [], as_of_dt=AS_OF, halflife_days=K_HALFLIFE,
        like_net=K_LIKE_NET, min_evidence=K_MIN_EVIDENCE, floor_b=K_FLOOR,
        sat_k=K_SAT_K)
    assert nm.cells[("Z", "fit")].n_decayed < no_net[("Z", "fit")].n_decayed


# ---------------------------------------------------------------------------
# N-14 — determinism, as-of reproducibility, H-4 immutability
# ---------------------------------------------------------------------------

def _snapshot(nm):
    return (sorted((k, c.n_raw, c.n_decayed, c.mult, c.likes_net)
                   for k, c in nm.cells.items()),
            sorted(nm.partner_mult.items()),
            sorted(nm.acceptance_stats.items()))


def test_n14_determinism_same_as_of():
    """Two builds at one as_of are bit-identical, AND the cell holds the value
    the as_of DOMAIN implies — the literal is what catches a `now()` leaking
    into the fold (a build clock would age the evidence differently)."""
    with _memdb() as engine:
        _seed_world(engine)
        first = _build_world(engine)
        second = _build_world(engine)
    assert _snapshot(first) == _snapshot(second)
    # X: passes 10/8/6/4/2 days before as_of, H=45 (hand-checked against §4.3's
    # fold), pinned as a literal — a clock read inside the fold moves it.
    assert first.cells[("X", "value")].n_decayed == pytest.approx(
        4.562939925, abs=1e-9)


def test_n14_insert_order_independence():
    """No dict/set iteration influences any sum: a permuted seed order yields
    a bit-identical fold."""
    with _memdb() as engine:
        _seed_world(engine)
        forward = _build_world(engine)
        evidence, netting, _e = negmem.load_admitted_events(
            USER, LEAGUE, as_of=AS_OF_ISO, horizon_floor_day="2026-08-20")
    shuffled, _pm = negmem._fold_events(
        list(reversed(evidence)), list(reversed(netting)), as_of_dt=AS_OF,
        halflife_days=K_HALFLIFE, like_net=K_LIKE_NET,
        min_evidence=K_MIN_EVIDENCE, floor_b=K_FLOOR, sat_k=K_SAT_K)
    for key, cell in shuffled.items():
        assert cell == forward.cells[key]


def test_n14_historical_as_of_is_reproducible():
    """R6: a build at a historical as_of sees only rows acted on at or before
    it — netting events included, in the as-of domain."""
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            early = negmem.build_map(
                USER, LEAGUE, as_of=(AS_OF - timedelta(days=5)).isoformat(),
                **BUILD_KNOBS)
            late = negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO,
                                    **BUILD_KNOBS)
    assert early.cells[("X", "value")].n_raw == 3      # days 10, 8, 6 only
    assert late.cells[("X", "value")].n_raw == 5
    assert ("Z", "fit") in early.cells                 # 3 fit passes, no like yet
    assert early.cells[("Z", "fit")].likes_net == 0.0
    assert late.cells[("Z", "fit")].likes_net > 0.0


def test_n14_map_is_structurally_immutable():
    """H-4: a seam cannot 'fix up' a shared map in place."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
    with pytest.raises(TypeError):
        nm.partner_mult["X"] = 0.5
    with pytest.raises(TypeError):
        nm.cells[("X", "value")] = None
    with pytest.raises(TypeError):
        nm.acceptance_stats["X"] = (1, 1)
    with pytest.raises(Exception):
        nm.degraded = True              # frozen dataclass


def test_n14_rounding_discipline():
    """C5: n_decayed at 1e-9, cell mult at 1e-6, stamp m at 1e-4."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
    for cell in nm.cells.values():
        assert cell.n_decayed == round(cell.n_decayed, 9)
        assert cell.mult == round(cell.mult, 6)
    eff = negmem.effective_mult(nm, "X", strength=1.0, floor=K_FLOOR)
    stamp = negmem.stamp_payload(nm, "X", eff)
    assert stamp["m"] == round(stamp["m"], 4)
    assert stamp["ver"] == negmem.NEGMEM_VER


def test_n14_no_module_global_map():
    """T1: the map moves exclusively as an argument — nothing on the module
    holds one."""
    with _memdb() as engine:
        _seed_world(engine)
        _build_world(engine)
    globals_holding_maps = [
        name for name, value in vars(negmem).items()
        if isinstance(value, negmem.NegmemMap)
    ]
    assert globals_holding_maps == []


# ---------------------------------------------------------------------------
# N-15 / N-16 — M2: E-B parity, the lookback window, the feed guard
# ---------------------------------------------------------------------------

def _eb(accepts, responses, m=K_ACCEPT_STRENGTH, p0=K_ACCEPT_P0):
    """The ratified memo §2f math, reproduced (never modified)."""
    return (accepts + m * p0) / (responses + m)


def test_n15_m2_parity_against_acceptance_prior():
    """C4: feed × the ratified acceptance_prior reproduces memo §2f exactly.
    The tuple order is (accepts, responses) — the CODE wins over HLD §2.1
    (§9 delta a); flipping it changes the number."""
    from backend import trade_gen_v2
    from backend import trade_service

    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)

    assert nm.acceptance_stats["X"] == (2, 5)
    saved = dict(trade_service._cfg)
    try:
        trade_service._cfg["gen2_accept_prior_strength"] = K_ACCEPT_STRENGTH
        trade_service._cfg["gen2_accept_global_prior"] = K_ACCEPT_P0
        feed = nm.m2_feed()
        assert trade_gen_v2.acceptance_prior("X", feed) == pytest.approx(
            _eb(2, 5), abs=1e-12)
        # the tuple-flip sabotage would land here:
        assert _eb(2, 5) != pytest.approx(_eb(5, 2), abs=1e-9)
        # C4 empty case: {} ⇒ uniform p0 (the guard lives in the FEED, never
        # in the ratified math)
        assert trade_gen_v2.acceptance_prior("X", {}) == K_ACCEPT_P0
        assert trade_gen_v2.acceptance_prior("nobody", feed) == K_ACCEPT_P0
    finally:
        trade_service._cfg.clear()
        trade_service._cfg.update(saved)


def test_n15_m2_empty_table_parity():
    """Empty tables ⇒ zero rows ⇒ {} on both engines (no aggregate SQL, so no
    SQLite-SUM-returns-NULL divergence to reconcile)."""
    from backend import trade_gen_v2
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        with _allowlist({LEAGUE}):
            nm = negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO, **BUILD_KNOBS)
    assert dict(nm.acceptance_stats) == {}
    assert dict(nm.m2_feed()) == {}
    assert trade_gen_v2.acceptance_prior("X", nm.m2_feed()) == pytest.approx(
        trade_gen_v2.acceptance_prior("X", None), abs=1e-12)


def test_n15_m2_lookback_window_is_pinned_to_the_constant():
    """PRD R5's 180-day window, read from negmem.NEGMEM_M2_LOOKBACK_DAYS rather
    than a literal, so the spec and the code cannot drift apart silently
    (§9 delta f — the window moved layers, not size)."""
    # The constant IS the PRD R5 window — pinned here so moving it is a
    # deliberate spec change, not a silent one (§9 delta f moved the LAYER the
    # window is applied at, never its size).
    assert negmem.NEGMEM_M2_LOOKBACK_DAYS == 180, "PRD R5 window"
    inside = negmem.NEGMEM_M2_LOOKBACK_DAYS - 1
    outside = negmem.NEGMEM_M2_LOOKBACK_DAYS + 1
    boundary = negmem.NEGMEM_M2_LOOKBACK_DAYS
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        s.match("X", "accept", _iso(inside))
        s.match("Y", "accept", _iso(outside))
        s.match("Z", "accept", _iso(boundary))
        nm = _build_world(engine)
    assert nm.acceptance_stats["X"] == (1, 1)
    assert "Y" not in nm.acceptance_stats
    assert nm.acceptance_stats["Z"] == (1, 1)      # the boundary row counts


def test_n16_m2_feed_guard_short_circuits():
    """§5.4: accept_prior_strength ≤ 0 ⇒ acceptance_stats {} AND both M2
    queries skipped — so dropped_unmapped_partner_ids reads 0 because no count
    was TAKEN, never because there were no drops."""
    with _memdb() as engine:
        _seed_world(engine)
        calls = []
        real_rows = negmem._rows

        def spy(sql, params):
            calls.append(sql)
            return real_rows(sql, params)

        with patch.object(negmem, "_rows", spy):
            nm = _build_world(engine, accept_prior_strength=0.0)
    assert dict(nm.acceptance_stats) == {}
    assert nm.dropped_unmapped_partner_ids == 0
    assert negmem._MATCHES_SQL not in calls
    assert negmem._MEMBERS_SQL not in calls


def test_n16_no_zero_response_keys_ever():
    """A partner with matches but NO decisions is structurally absent — a key
    exists only via `resp + 1`."""
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        s.match("X", None, _iso(3))          # matched, never decided
        nm = _build_world(engine)
    assert "X" not in nm.acceptance_stats
    assert all(r > 0 for (_a, r) in nm.acceptance_stats.values())


def test_n16_requesting_user_is_dropped_before_the_membership_filter():
    """Drop-then-filter order: the requesting user never lands in the feed and
    never inflates the drop counter."""
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        with engine.begin() as conn:
            conn.execute(trade_matches_table.insert().values(
                league_id=LEAGUE, user_a_id=USER, user_b_id="X",
                user_a_give="[]", user_a_receive="[]", matched_at=_iso(3),
                user_a_decision="accept", user_a_decided_at=_iso(3),
                user_b_decision="decline", user_b_decided_at=_iso(3)))
        nm = _build_world(engine)
    assert USER not in nm.acceptance_stats
    assert nm.acceptance_stats["X"] == (0, 1)
    assert nm.dropped_unmapped_partner_ids == 0


# ---------------------------------------------------------------------------
# N-21 — identity hygiene (R9) and the DE-5 accepted limitation
# ---------------------------------------------------------------------------

def test_n21_all_keys_are_canonical_league_members():
    """R9: every cell key and every acceptance_stats key is a canonical league
    member id; account-side ids never appear as keys."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
    assert {p for p, _f in nm.cells} <= set(MEMBERS)
    assert set(nm.acceptance_stats) <= set(MEMBERS)
    assert CO_OWNER_ACCT not in nm.acceptance_stats
    assert all(CO_OWNER_ACCT != p for p, _f in nm.cells)


def test_n21_m1_evidence_path_never_consults_owner_alias():
    """DE-5: the M1 path performs NO lookup at all. A future edit that
    re-introduces an alias hop on the evidence path is caught here — the alias
    is a no-op in production, so only this assertion would notice."""
    class _TripwireAlias(dict):
        def get(self, key, default=None):          # noqa: D102
            raise AssertionError(
                "owner_alias consulted — the M1 evidence path must not alias")

        def __getitem__(self, key):
            raise AssertionError("owner_alias consulted on the M1 path")

    with _memdb() as engine:
        _seed_world(engine)
        # M2 is killed so the ONLY remaining consumer of the alias would be a
        # (forbidden) evidence-path hop.
        nm = _build_world(engine, accept_prior_strength=0.0)
        with _allowlist({LEAGUE}):
            knobs = dict(BUILD_KNOBS)
            knobs["accept_prior_strength"] = 0.0
            nm2 = negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO,
                                   owner_alias=_TripwireAlias(), **knobs)
    assert nm2 is not None and not nm2.degraded
    assert _snapshot(nm) == _snapshot(nm2)


def test_n21_unmapped_m2_key_is_dropped_and_counted():
    """The accepted limitation, made visible: a co-owner account-side response
    is DROPPED (never mis-attributed to X) and the tripwire counter fires."""
    with _memdb() as engine:
        _seed_world(engine)
        nm = _build_world(engine)
    assert nm.acceptance_stats["X"] == (2, 5)      # unchanged by the co-owner row
    assert nm.dropped_unmapped_partner_ids == 1


def test_n21_injected_owner_alias_folds_onto_the_canonical_key():
    """A UNIT assertion about the KWARG'S CONTRACT ONLY. It proves the
    parameter works if ever fed; it must NOT be read as evidence that a
    server-built map exists — v1 ships NO producer (LLD §4.2)."""
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            nm = negmem.build_map(
                USER, LEAGUE, as_of=AS_OF_ISO,
                owner_alias=MappingProxyType({CO_OWNER_ACCT: "X"}),
                **BUILD_KNOBS)
    assert nm.acceptance_stats["X"] == (3, 6)     # the co-owner accept folds in
    assert nm.dropped_unmapped_partner_ids == 0


def test_n21_default_owner_alias_is_identity_and_immutable():
    assert dict(negmem._EMPTY_ALIAS) == {}
    with pytest.raises(TypeError):
        negmem._EMPTY_ALIAS["a"] = "b"


# ---------------------------------------------------------------------------
# N-22 — horizon + epoch bounds, asserted on the FETCHED ROW COUNT
# ---------------------------------------------------------------------------

def test_n22_rolling_horizon_is_applied_in_query():
    """halflife pinned SMALL and as_of set FAR past the epoch, so
    max(CLEAN_EPOCH, as_of − 4H) resolves to the ROLLING floor — at default
    H=45 with a near-epoch as_of the epoch dominates and the horizon arm of the
    max is never exercised, which is how a broken horizon would pass unnoticed.

    The assertion is on the ROW COUNT the SQL returns: "never loaded" is the
    claim, and a Python-side filter would produce identical cells while loading
    everything.
    """
    as_of = datetime(2027, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    floor_day = negmem._horizon_floor_day(as_of, 2.0)
    assert floor_day == "2027-05-24" > negmem.NEGMEM_CLEAN_EPOCH_DAY
    floor_dt = datetime.fromisoformat(floor_day + "T00:00:00+00:00")

    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        for served, tag in ((floor_dt - timedelta(days=1), "before"),
                            (floor_dt + timedelta(hours=1), "on"),
                            (floor_dt + timedelta(days=3), "inside")):
            imp = s.impression("X", served_at=served.isoformat())
            s.outcome(imp, "viewed", served.isoformat())
            s.outcome(imp, "pass", served.isoformat())
            s.reason(imp, "value")
        fetched = negmem._fetch_spine(USER, LEAGUE, floor_day)
    # 2 admitted impressions × 2 outcome rows each = 4 rows; the "before" row
    # is NEVER LOADED.
    assert len(fetched) == 4
    assert {r["impression_id"] for r in fetched} == {"imp002", "imp003"}


def test_n22_clean_epoch_day_prefix_boundary():
    """The day-prefix bound admits the WHOLE boundary day and excludes D-091
    structurally — no separate NOT-BETWEEN clause to get wrong."""
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        keep = s.impression("X", served_at="2026-08-20T00:00:00+00:00")
        drop = s.impression("X", served_at="2026-08-19T23:59:00+00:00")
        for imp in (keep, drop):
            s.outcome(imp, "viewed", "2026-08-20T01:00:00+00:00")
            s.outcome(imp, "pass", "2026-08-20T01:00:00+00:00")
            s.reason(imp, "value")
        fetched = negmem._fetch_spine(USER, LEAGUE,
                                      negmem.NEGMEM_CLEAN_EPOCH_DAY)
    assert {r["impression_id"] for r in fetched} == {keep}


def test_n22_horizon_floor_is_the_max_of_epoch_and_rolling():
    near = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert negmem._horizon_floor_day(near, 45.0) == negmem.NEGMEM_CLEAN_EPOCH_DAY
    far = datetime(2028, 1, 1, tzinfo=timezone.utc)
    assert negmem._horizon_floor_day(far, 45.0) > negmem.NEGMEM_CLEAN_EPOCH_DAY


# ---------------------------------------------------------------------------
# N-23 — SQL dialect portability (banned tokens + real execution)
# ---------------------------------------------------------------------------

_MODULE_SQL = {
    "_SPINE_SQL": negmem._SPINE_SQL,
    "_RETRACTED_SQL": negmem._RETRACTED_SQL,
    "_MATCHES_SQL": negmem._MATCHES_SQL,
    "_MEMBERS_SQL": negmem._MEMBERS_SQL,
}

_BANNED_TOKENS = ("json_extract", "->>", "::jsonb", "strftime", "date_trunc",
                  "percentile_cont", "julianday")

#: The SHIPPED readout-pack files (LLD §7.2/§7.3). They are held to the same
#: DE-4 rule as the module's own SQL: an operator runs these against SQLite
#: locally and Postgres in prod, and a dialect-split token in one of them
#: fails at the worst possible moment — mid-incident, at the keyboard.
_PACK_SQL_FILES = ("negmem-stamp-rate.sql", "negmem-gr4-joint.sql")


def _executable_sql(text_: str) -> str:
    """Strip `--` comments — the banned-token rule governs the SQL that RUNS.

    Both pack files document their Postgres-only variant in a comment (the
    `bakeoff_readout.sql` convention), and those comments legitimately contain
    `::jsonb` / `->>` / `PERCENTILE_CONT`. Scanning raw file text would ban
    the documentation instead of the code; scanning the executable half is the
    rule as written ("SQLite form is normative", §7.2).
    """
    return "\n".join(line.split("--", 1)[0] for line in text_.splitlines())


@pytest.mark.parametrize("name", sorted(_MODULE_SQL))
def test_n23_banned_token_scan(name):
    """(1) The DE-4 dialect rule made mechanical. `text()` is an opaque string
    to SQLAlchemy — it compiles any SQLite-only syntax without complaint, so a
    postgres-dialect compile could never fail. This scan can."""
    lowered = _MODULE_SQL[name].lower()
    for token in _BANNED_TOKENS:
        assert token not in lowered, f"{name} uses banned token {token!r}"


@pytest.mark.parametrize("fname", _PACK_SQL_FILES)
def test_n23_pack_files_ship_and_obey_the_same_dialect_rule(fname):
    """(1b) The same scan over the SHIPPED pack files — the coverage the
    module-only scan was missing.

    Also asserts each file still ships and still carries its two runner
    contracts: the `{allowlist}` substitution point (the allowlist-scoped
    denominator is the whole point — an unscoped one reads a partial rollout
    as build failures) and the `:flag_on_day` bind (pre-flag rows carry no
    stamp by construction; including them manufactures a false alarm).

    Sabotage: paste `json_extract(i.features_json, '$.negmem.m')` into either
    file's executable SQL, or drop the `{allowlist}` clause.
    """
    path = REPO / "scripts" / fname
    assert path.exists(), f"the readout pack lost {fname}"
    body = _executable_sql(path.read_text())
    lowered = body.lower()
    for token in _BANNED_TOKENS:
        assert token not in lowered, f"{fname} uses banned token {token!r}"
    assert "{allowlist}" in body, f"{fname} lost its allowlist scoping"
    assert ":flag_on_day" in body, f"{fname} lost its flag-era bind"


@pytest.mark.parametrize("fname", _PACK_SQL_FILES)
def test_n23_pack_files_execute_against_sqlite(fname):
    """(2b) Execution half for the pack, mirroring the module's: substitute a
    real allowlist, bind a real day, run it against the seeded in-memory DB.
    A syntax error or a column renamed out from under the pack fails loudly
    here instead of in the operator's hands."""
    from sqlalchemy import text as sa_text

    # Comments are stripped BEFORE binding, not merely before scanning:
    # SQLAlchemy's text() harvests `:name` binds out of comment text too, and
    # both files name their binds in prose.
    body = _executable_sql((REPO / "scripts" / fname).read_text()).replace(
        "{allowlist}", "'" + LEAGUE + "'")
    with _memdb() as engine:
        _seed_world(engine)
        with engine.connect() as conn:
            result = conn.execute(sa_text(body),
                                  {"flag_on_day": negmem.NEGMEM_CLEAN_EPOCH_DAY})
            assert result.keys(), f"{fname} selected no columns"
            assert result.fetchall() is not None


def test_n23_every_statement_executes_with_the_expected_columns():
    """(2) Execution against the in-memory engine with real binds — a syntax
    error or a renamed column fails loudly."""
    from sqlalchemy import text as sa_text

    expected = {
        "_SPINE_SQL": {"impression_id", "served_at", "features_json", "is_ghost",
                       "assets_json", "shape_bucket", "trade_intent",
                       "outcome_id", "action", "acted_at", "reason", "detail",
                       "key_source"},
        "_RETRACTED_SQL": {"id", "decision", "give_player_ids",
                           "receive_player_ids", "retracted_at", "created_at"},
        "_MATCHES_SQL": {"user_a_id", "user_a_decision", "user_a_decided_at",
                         "user_b_id", "user_b_decision", "user_b_decided_at",
                         "matched_at"},
        "_MEMBERS_SQL": {"user_id"},
    }
    params = {
        "_SPINE_SQL": {"uid": USER, "lid": LEAGUE, "horizon_day": "2026-08-20"},
        "_RETRACTED_SQL": {"uid": USER, "lid": LEAGUE,
                           "horizon_day": "2026-08-20"},
        "_MATCHES_SQL": {"lid": LEAGUE},
        "_MEMBERS_SQL": {"lid": LEAGUE},
    }
    with _memdb() as engine:
        _seed_world(engine)
        with engine.connect() as conn:
            for name, sql in _MODULE_SQL.items():
                result = conn.execute(sa_text(sql), params[name])
                assert set(result.keys()) == expected[name], name
                assert result.fetchall() is not None


def test_n23_postgres_dialect_compile_smoke():
    """Kept as a CHEAP smoke check and explicitly NON-LOAD-BEARING: text() is
    opaque to the compiler, so this can never catch a dialect error. The
    banned-token scan above is the real gate."""
    from sqlalchemy import text as sa_text
    from sqlalchemy.dialects import postgresql

    for sql in _MODULE_SQL.values():
        assert str(sa_text(sql).compile(dialect=postgresql.dialect()))


# ---------------------------------------------------------------------------
# N-24 — leaf import contract
# ---------------------------------------------------------------------------

def test_n24_leaf_import_contract():
    """D-2/T1: negmem imports stdlib + sqlalchemy + `database` only. NOT
    sleeper_roster (DE-5), NOT server/trade_service/any engine module."""
    source = (REPO / "backend" / "negmem.py").read_text()
    tree = ast.parse(source)
    absolute: set[str] = set()
    relative: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # `from . import x`
                if node.module:
                    relative.add(node.module.split(".")[0])
                relative |= {alias.name for alias in node.names}
            elif node.module:
                absolute.add(node.module.split(".")[0])

    allowed_absolute = {
        # stdlib
        "__future__", "json", "logging", "os", "threading", "time",
        "collections", "dataclasses", "datetime", "types", "typing",
        # the SQL driver — required for the dual-dialect text() fetch
        "sqlalchemy",
    }
    assert absolute <= allowed_absolute, absolute - allowed_absolute
    assert relative == {"database"}, relative
    banned = {"sleeper_roster", "server", "trade_service", "trade_gen_v2",
              "trade_gen_fit", "trade_optimizer", "bakeoff_runner",
              "bakeoff_profiles", "suggestion_telemetry", "experiments"}
    assert not (banned & (absolute | relative)), banned & (absolute | relative)


def test_n24_module_holds_no_knob_default_literals():
    """DE-3: negmem holds ZERO knob defaults — every tuning value arrives as a
    build_map argument. The one config read is the readout's seeded-table
    convenience, which raises rather than substituting a literal."""
    source = (REPO / "backend" / "negmem.py").read_text()
    tree = ast.parse(source)
    module_level_names = {
        target.id
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    # No module-level binding may shadow a model_config knob name.
    knob_names = {"negmem_strength", "negmem_floor", "negmem_min_evidence",
                  "negmem_halflife_days", "negmem_sat_k", "negmem_like_net"}
    assert module_level_names & knob_names == set()
    # ...and build_map's knobs are all REQUIRED keyword-only args (no default).
    build_map = next(n for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name == "build_map")
    required_kwonly = {
        arg.arg for arg, default in zip(build_map.args.kwonlyargs,
                                        build_map.args.kw_defaults)
        if default is None
    }
    assert {"halflife_days", "min_evidence", "sat_k", "like_net", "floor_b",
            "accept_prior_strength"} <= required_kwonly


# ---------------------------------------------------------------------------
# N-19 (builder half) — degraded map + failure taxonomy
# ---------------------------------------------------------------------------

def test_n19_build_exception_degrades_and_never_raises():
    with _memdb() as engine:
        _seed_world(engine)
        def boom(*_a, **_k):
            raise RuntimeError("DB down")
        with patch.object(negmem, "_fetch_spine", boom):
            nm = _build_world(engine)
    assert nm is not None and nm.degraded
    assert dict(nm.cells) == {} and dict(nm.acceptance_stats) == {}
    assert dict(nm.m2_feed()) == {}
    assert nm.dropped_unmapped_partner_ids == 0
    assert negmem.effective_mult(nm, "X", strength=1.0, floor=K_FLOOR) == 1.0


def test_n19_slow_but_valid_build_is_discarded():
    """build_ms > NEGMEM_DEGRADE_MS ⇒ degraded — DISCARDED by design, not just
    stamped. Driven by scripting the module's own clock seam (never `sleep`:
    build_ms is wall-clock around the reads + fold, so the clock IS the only
    input to degrade)."""
    ticks = iter([0.0, (negmem.NEGMEM_DEGRADE_MS / 1000.0) + 0.1])
    with _memdb() as engine:
        _seed_world(engine)
        with patch.object(negmem, "_perf_counter", lambda: next(ticks)):
            nm = _build_world(engine)
    assert nm.degraded
    assert nm.build_ms > negmem.NEGMEM_DEGRADE_MS
    assert dict(nm.cells) == {}
    assert dict(nm.m2_feed()) == {}
    assert negmem.effective_mult(nm, "X", strength=1.0, floor=K_FLOOR) == 1.0


def test_n19_keyboard_interrupt_propagates():
    """`except Exception` does not catch BaseException — never swallow
    interpreter shutdown."""
    with _memdb() as engine:
        _seed_world(engine)
        def interrupt(*_a, **_k):
            raise KeyboardInterrupt
        with patch.object(negmem, "_fetch_spine", interrupt):
            with pytest.raises(KeyboardInterrupt):
                _build_world(engine)


def test_n19_corrupt_row_increments_parse_errors_but_keeps_the_map():
    """A single corrupt features_json must not zero a league's memory."""
    with _memdb() as engine:
        s = _seed_world(engine)
        bad = s.impression("X", served_at=_iso(3.2), features_json="{not json")
        s.outcome(bad, "viewed", _iso(3))
        s.outcome(bad, "pass", _iso(3))
        s.reason(bad, "value")
        nm = _build_world(engine)
    assert not nm.degraded
    assert nm.parse_errors == 1
    assert nm.cells[("X", "value")].n_raw == 5      # the healthy five survive


def test_n19_not_allowlisted_returns_none():
    """§8.1: the None seam is indistinguishable from flag-off downstream."""
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist(set()):
            assert negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO,
                                    **BUILD_KNOBS) is None
        with _allowlist({"some_other_league"}):
            assert negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO,
                                    **BUILD_KNOBS) is None
        with _allowlist({"*"}):
            assert negmem.build_map(USER, LEAGUE, as_of=AS_OF_ISO,
                                    **BUILD_KNOBS) is not None


def test_n19_allowlist_sources_union_and_star():
    assert negmem.negmem_league_allowed(LEAGUE) in (True, False)  # no raise
    with _allowlist({"*"}):
        assert negmem.negmem_league_allowed("anything")
    with _allowlist({LEAGUE}):
        assert negmem.negmem_league_allowed(LEAGUE)
        assert not negmem.negmem_league_allowed(OTHER_LEAGUE)
    with _allowlist(set()):
        assert not negmem.negmem_league_allowed(LEAGUE)


def test_n19_unparseable_allowlist_file_is_empty_not_fatal(tmp_path):
    bad = tmp_path / "negmem_leagues.json"
    bad.write_text("{not json")
    negmem._reset_allowlist_cache()
    try:
        with patch.object(negmem, "ALLOWLIST_FILE", str(bad)):
            assert negmem.load_negmem_league_allowlist() == frozenset()
    finally:
        negmem._reset_allowlist_cache()


# ---------------------------------------------------------------------------
# N-26 — readout format (§7.1)
# ---------------------------------------------------------------------------

def test_n26_readout_format():
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            out = negmem.negmem_readout(USER, LEAGUE, AS_OF_ISO,
                                        knobs=dict(READOUT_KNOBS))
    assert set(out) == {
        "user_id", "league_id", "as_of", "ver", "allowlisted", "degraded",
        "build_ms", "parse_errors", "knobs", "cells", "partner_likes",
        "partner_mult", "acceptance_stats", "m2",
        "dropped_unmapped_partner_ids"}
    assert out["allowlisted"] is True
    assert out["degraded"] is False and out["parse_errors"] == 0
    assert out["ver"] == negmem.NEGMEM_VER
    assert set(out["knobs"]) == set(READOUT_KNOBS)
    assert out["m2"] == "live"
    assert out["dropped_unmapped_partner_ids"] == 1
    assert out["acceptance_stats"]["X"] == [2, 5]

    cells = {(c["partner_league_id"], c["family"]): c for c in out["cells"]}
    # EVERY cell is reported, identity ones included (the RFPS numerator rule
    # and the readout both need sub-threshold state).
    assert ("Y", "value") in cells and cells[("Y", "value")]["below_min_evidence"]
    x_value = cells[("X", "value")]
    assert x_value["n_raw"] == 5 and not x_value["below_min_evidence"]
    assert x_value["mult"] < 1.0
    # `floored` is RESERVED and always false in v1 — a true here means the
    # curve changed.
    assert all(c["floored"] is False for c in out["cells"])
    # R11 context tags: annotated, NULL expected, never an error.
    assert x_value["context_tag_counts"]["trade_intent"] == {None: 5}
    assert x_value["context_tag_counts"]["user_value_basis"] == {"personal": 5}
    # partner_likes is COUNTED from the admitted netting list, not inverted
    # from the map's decayed likes_net mass.
    assert out["partner_likes"] == {"Z": 1}
    assert cells[("Z", "fit")]["likes_net"] > 0.0
    assert out["partner_mult"]["X"] == x_value["mult"]


def test_n26_readout_bypasses_the_allowlist_and_reports_it_as_data():
    """A readout that returned None for a not-yet-allowlisted league would be a
    tautology — "why no stamps in league X" must be answerable."""
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist(set()):
            out = negmem.negmem_readout(USER, LEAGUE, AS_OF_ISO,
                                        knobs=dict(READOUT_KNOBS))
    assert out["allowlisted"] is False
    assert out["cells"], "the builder must still run with the check bypassed"


def test_n26_readout_m2_killed_annotation():
    """Under a killed M2 the counter's 0 means 'not counted', so the readout
    says so explicitly."""
    knobs = dict(READOUT_KNOBS, gen2_accept_prior_strength=0.0)
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            out = negmem.negmem_readout(USER, LEAGUE, AS_OF_ISO, knobs=knobs)
    assert out["m2"] == "killed (gen2_accept_prior_strength <= 0)"
    assert out["acceptance_stats"] == {}
    assert out["dropped_unmapped_partner_ids"] == 0


def test_n26_readout_missing_seed_rows_is_loud():
    """Operator tool — loud is correct; negmem holds no default literals."""
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            with pytest.raises(KeyError) as err:
                negmem.negmem_readout(USER, LEAGUE, AS_OF_ISO,
                                      knobs={"negmem_floor": 0.6})
    assert "run init_db" in str(err.value)


# ---------------------------------------------------------------------------
# Operator scripts (§7.1 entry point, §7.4 RFPS artifact) — self-tests
# ---------------------------------------------------------------------------

def test_readout_script_prints_the_readout_dict(capsys):
    from backend.scripts import negmem_readout as script
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            with patch.object(db, "get_config", lambda: dict(READOUT_KNOBS)):
                code = script.main(["--user", USER, "--league", LEAGUE,
                                    "--as-of", AS_OF_ISO])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["league_id"] == LEAGUE and printed["m2"] == "live"
    assert printed["dropped_unmapped_partner_ids"] == 1


def test_readout_script_is_loud_about_missing_seed_rows(capsys):
    from backend.scripts import negmem_readout as script
    with _memdb() as engine:
        _seed_world(engine)
        with _allowlist({LEAGUE}):
            with patch.object(db, "get_config", lambda: {"negmem_floor": 0.6}):
                code = script.main(["--user", USER, "--league", LEAGUE])
    assert code == 3
    assert "run init_db" in capsys.readouterr().err


def test_rfps_artifact_shape_and_numerator_rule():
    """§7.4: the frozen-cohort artifact. The cohort includes reason-LESS
    rejections (relaxed for MEMBERSHIP only) and the numerator keys on the HARD
    min_evidence threshold at served_at."""
    from backend.scripts import negmem_rfps as script
    with _memdb() as engine:
        s = _seed_world(engine)
        # a reason-less rejection toward X, served AFTER X crossed the gate
        bare = s.impression("X", served_at=_iso(1.2))
        s.outcome(bare, "viewed", _iso(1))
        s.outcome(bare, "pass", _iso(1))
        with _allowlist({LEAGUE}):
            with patch.object(db, "get_config", lambda: dict(READOUT_KNOBS)):
                artifact = script.build_artifact(
                    [LEAGUE], (AS_OF - timedelta(days=30)).date().isoformat(),
                    AS_OF.date().isoformat())

    assert set(artifact) >= {"generated_at", "pre_registered", "window",
                             "leagues", "knobs_frozen", "id_mapping",
                             "owner_alias", "owner_alias_source",
                             "dropped_unmapped_partner_ids", "admission_ver",
                             "cohort", "baseline_rfps", "n",
                             "family_switch_rate"}
    assert artifact["pre_registered"] is True
    assert artifact["admission_ver"] == negmem.NEGMEM_VER
    assert artifact["owner_alias"] == {}
    assert set(artifact["knobs_frozen"]) == {
        "negmem_min_evidence", "negmem_halflife_days", "negmem_sat_k",
        "negmem_like_net"}
    by_imp = {c["impression_id"]: c for c in artifact["cohort"]}
    # the reason-less row IS in the cohort ...
    assert bare in by_imp and by_imp[bare]["reason_carrying"] is False
    # ... and its numerator fires off ANY admitted (partner, *) cell
    assert by_imp[bare]["numerator"] is True
    # X's own reason-carrying rejections are in too, keyed on their family
    reasoned = [c for c in artifact["cohort"]
                if c["partner_league_id"] == "X" and c["reason_carrying"]]
    assert reasoned and all(c["reason_family"] == "value" for c in reasoned)
    # the FIRST rejection toward X cannot be in the numerator — no evidence had
    # accumulated at its served_at.
    first = min(reasoned, key=lambda c: c["served_at"])
    assert first["numerator"] is False
    assert 0.0 <= artifact["baseline_rfps"] <= 1.0
    assert artifact["n"] == len(artifact["cohort"])


def test_n26_readout_worked_example_row():
    """The readout's example and §4.5's core-logic example are ONE set of
    numbers: passes day 0/0/10, like day 20, as_of day 30, H=45 ⇒
    n_decayed 1.14, likes_net 0.86."""
    with _memdb() as engine:
        s = _Seeder(engine)
        s.members(MEMBERS)
        for day in (30, 30, 20):
            imp = s.impression("X", served_at=_iso(day + 0.2))
            s.outcome(imp, "viewed", _iso(day))
            s.outcome(imp, "pass", _iso(day))
            s.reason(imp, "value")
        imp = s.impression("X", served_at=_iso(10.2))
        s.outcome(imp, "viewed", _iso(10))
        s.outcome(imp, "like", _iso(10))
        with _allowlist({LEAGUE}):
            out = negmem.negmem_readout(USER, LEAGUE, AS_OF_ISO,
                                        knobs=dict(READOUT_KNOBS))
    row = next(c for c in out["cells"]
               if (c["partner_league_id"], c["family"]) == ("X", "value"))
    assert row["n_raw"] == 3
    assert row["n_decayed"] == 1.14
    assert row["likes_net"] == 0.86
    assert row["mult"] == 1.0 and row["below_min_evidence"] is True
