"""Receipts — the grading substrate (docs/plans/receipts/LLD.md §7, T-1…T-10).

Every test here names what it PROVES, because the whole feature is a claim
about honesty and an unproved honesty claim is worse than no claim.

  T-1  module isolation — `receipts_service` pulls in no engine module, and
       nothing in the engine imports it (PLAN §7.3, NG-1).
  T-2  the honesty theorem AS ACTUALLY TRUE — uniform additive drift cancels
       exactly for equal-cardinality shapes; the disclosed residual for a 2x1
       is pinned WITH ITS SIGN (`−d`), plus an explicit directional win.
       This is the matrix's only sign-sensitive test: a flipped sign would
       have rendered every win as a loss (HLD D-1).
  T-3  anchor independence — perturbing `features_json` values changes no
       grade. Valuation comes from `player_value_history`, never the card
       (HLD D-2).
  T-4  pick rules — picks are delta 0; the frozen weights drive coverage and
       pick-share only; DEPLOY-INVARIANCE: repricing `GENERIC_PICK_SEEDS`
       changes no grade under a fixed `GRADER_VERSION` (HLD D-7).
  T-5  anti-survivorship — a player who cratered out of the pool is imputed
       to the floor and RETAINED, flagged; an unresolved-at-serve player is
       weighted at the serve-date floor in the coverage denominator (HLD D-8).
  T-6  snapshot matching — serve anchor is nearest-≤ (a nearer POST-serve
       snapshot is never used), window is ±tol, the retry window holds a row
       out of the table, and the deadline turns it terminal.
  T-7  idempotency — a second run inserts zero; a partial-insert crash
       re-runs to completion without duplicates (LLD §5.1).
  T-8  regrade — bumping `GRADER_VERSION` adds rows, retains the old ones,
       and reads pin the max (HLD D-3).
  T-9  route contracts — viewer scoping, ghost exclusion at BOTH layers,
       dedup-by-earliest, min-n gating, the all-windows payload, flag-off
       404s, `n == len(rows used)`, and the Wilson triple 3/5 →
       [0.231, 0.882].
  T-10 append-only — no UPDATE/DELETE path exists for `receipts_` tables.

Harness: isolated in-memory SQLite (`backend/tests/CLAUDE.md` pattern 1) plus
the Flask client + injected session (pattern 2). No network, no dev DB.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

REPO = Path(__file__).resolve().parents[2]

from backend import database as db_module              # noqa: E402
from backend import feature_flags as ff                # noqa: E402
from backend import receipts_service as rs             # noqa: E402
from backend.database import metadata                  # noqa: E402

LEAGUE = "L-receipts"
VIEWER = "U-viewer"
OTHER = "U-other"
FMT = "1qb_ppr"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        with eng.begin() as conn:
            conn.execute(db_module.leagues_table.insert().values(
                sleeper_league_id=LEAGUE, user_id=VIEWER, name="Receipts League",
                default_scoring=FMT))
            for key, val, desc in db_module._MODEL_CONFIG_DEFAULTS:
                conn.execute(db_module.model_config_table.insert().values(
                    key=key, value=float(val), description=desc))
        yield eng


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch):
    """Both flags ON for the suite; the flag-OFF contracts are asserted
    explicitly in T-9 rather than left as the ambient state."""
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS, **{
        "receipts.grading": True, "receipts.screen": True}))
    yield
    ff._flags_cache = None


def _impression(*, impression_id=None, user_id=VIEWER, league_id=LEAGUE,
                served_days_ago=30, give=("p1",), receive=("p2",),
                is_ghost=None, features=None, assets_json="__default__",
                trade_hash=None, shape_bucket=None, model_arm="current",
                basis="consensus") -> str:
    iid = impression_id or uuid.uuid4().hex
    served = (datetime.now(timezone.utc)
              - timedelta(days=served_days_ago)).replace(hour=12)
    feats = {"basis": basis, "shape": shape_bucket or
             f"{len(give)}x{len(receive)}", "give_value": 1234.0,
             "receive_value": 4321.0, "user_value_basis": "personal"}
    if features:
        feats.update(features)
    payload = (json.dumps({"give": list(give), "receive": list(receive)})
               if assets_json == "__default__" else assets_json)
    with db_module.engine.begin() as conn:
        conn.execute(db_module.deck_impressions_table.insert().values(
            impression_id=iid, user_id=user_id, league_id=league_id,
            deck_job_id="job-1", card_index=0,
            trade_hash=trade_hash or f"h-{iid[:8]}",
            features_json=json.dumps(feats), propensity=1.0,
            shape_bucket=shape_bucket or f"{len(give)}x{len(receive)}",
            archetype="value", served_at=served.isoformat(),
            is_ghost=is_ghost, assets_json=payload, model_arm=model_arm,
            policy_version="pol-1"))
    return iid


def _snapshot(player_id: str, date: str, value: float, fmt: str = FMT) -> None:
    """Idempotent: tests layer overlapping pools freely, and `uq_value_snapshot`
    is what production relies on to make the daily job re-runnable."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    with db_module.engine.begin() as conn:
        conn.execute(sqlite_insert(db_module.player_value_history_table).values(
            player_id=player_id, scoring_format=fmt,
            consensus_elo=1500.0, consensus_value=float(value),
            snapshot_date=date).on_conflict_do_nothing(
                index_elements=["player_id", "scoring_format",
                                "snapshot_date"]))


def _pool(dates: list[str], values: dict, fmt: str = FMT,
          floor_player: str | None = "pool_floor",
          floor_value: float = 10.0) -> None:
    """Write a consensus pool across dates. `values` is {player: value} or
    {player: {date: value}}. A cheap `pool_floor` player anchors MIN() so the
    imputation floor is a real number rather than an artifact of the test."""
    for d in dates:
        for pid, v in values.items():
            val = v[d] if isinstance(v, dict) else v
            if val is None:
                continue
            _snapshot(pid, d, val, fmt)
        if floor_player:
            _snapshot(floor_player, d, floor_value, fmt)


def _grades(**filters) -> list[dict]:
    return db_module.load_receipts_grades(**filters)


def _grade_for(iid: str, window: int) -> dict | None:
    rows = [r for r in _grades() if r["impression_id"] == iid
            and r["window_days"] == window]
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# T-1 — module isolation. Proves PLAN §7.3 / NG-1.
# ---------------------------------------------------------------------------

ENGINE_MODULES = ("trade_service", "trade_optimizer", "trade_gen_v2",
                  "trade_gen_fit", "bakeoff_runner", "bakeoff_profiles",
                  "server", "suggestion_telemetry", "trade_breaker")


def test_t1_importing_receipts_service_pulls_no_engine_module():
    """A fresh interpreter importing ONLY receipts_service must not drag in a
    generation module. Run in a child process because this suite's other
    tests (and pytest collection) import the engine for their own reasons —
    asserting on `sys.modules` in-process would prove nothing."""
    code = (
        "import sys; import backend.receipts_service;"
        "bad=[m for m in sys.modules if m.startswith('backend.') and "
        f"any(k in m for k in {ENGINE_MODULES!r})];"
        "print(sorted(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", (
        f"receipts_service imported engine modules: {out.stdout.strip()}. "
        "The grader must stay a leaf — an engine import is the first step "
        "toward grading our own code instead of the market.")


def test_t1_no_engine_module_imports_receipts():
    """The other direction, and the one NG-1 actually protects: nothing in
    the generation path may read `receipts_*`. If an engine module ever
    imports this one, feedback-into-scoring has happened by accident."""
    offenders = []
    for name in ("trade_service", "trade_optimizer", "trade_gen_v2",
                 "trade_gen_fit", "bakeoff_runner", "trade_breaker"):
        path = REPO / "backend" / f"{name}.py"
        if not path.exists():
            continue
        text = path.read_text()
        if "receipts_service" in text or "receipts_grades" in text:
            offenders.append(name)
    assert offenders == [], (
        f"engine module(s) reference receipts: {offenders}. Nothing in "
        "generation or ordering may read grades (PLAN NG-1) — that is the "
        "Goodhart line, and it is supposed to be crossed by a PRD, not a "
        "drive-by import.")


def test_t1_assets_are_never_reconstructed_from_trade_hash(engine):
    """Forbidden operation 3, proved behaviourally.

    `trade_hash` is a sha256 of the asset sets — it cannot be inverted. A
    pre-telemetry impression HAS a hash and has no `assets_json`, so the only
    way to grade it would be to invent an asset set at grade time: a NEW
    prediction, minted after the outcome was known, which is precisely what
    preregistration forbids. Such a row must never be graded, under any
    window, ever."""
    serve_date, window = _days_ago(30), 28
    _pool([serve_date, rs._shift(serve_date, window)],
          {"p1": 1000.0, "p2": 1200.0})
    pre = _impression(served_days_ago=30, assets_json=None,
                      trade_hash="deadbeefdeadbeef")
    # A gradeable neighbour, so the run does REAL work. Without it the
    # cohort is empty, the run short-circuits, and this test would pass for
    # the wrong reason — it would be asserting that nothing happened at all.
    neighbour = _impression(served_days_ago=30, give=("p1",), receive=("p2",))
    rs.run_grading(trigger="cron")
    assert _grade_for(neighbour, window) is not None, "the run did no work"
    assert _grade_for(pre, window) is None, (
        "a pre-telemetry row was graded — the only route to that is "
        "reconstructing its assets, which mints a prediction after the fact.")
    assert all(r["impression_id"] != pre for r in _grades()), (
        f"a pre-telemetry row produced a grade row at some window: {pre}")


def test_t1_the_grader_reads_trade_hash_only_as_a_dedup_key():
    """The static half: `trade_hash` never appears on a line that derives or
    handles an asset set. It is a card-identity key for read-time dedup and a
    denormalized column, and nothing else."""
    src = (REPO / "backend" / "receipts_service.py").read_text()
    derivation = ("assets_json", "json.loads", "\"give\"", "\"receive\"",
                  "give_ids", "recv_ids")
    for i, line in enumerate(src.splitlines(), 1):
        if "trade_hash" not in line:
            continue
        hits = [d for d in derivation if d in line]
        assert not hits, (
            f"receipts_service.py:{i} derives assets from trade_hash "
            f"({hits}): {line.strip()}")


# ---------------------------------------------------------------------------
# T-2 — the honesty theorem, as actually true. Proves HLD D-1 — no more.
# ---------------------------------------------------------------------------

def _grade_synthetic(give: dict, receive: dict, window: int = 28) -> dict:
    """Grade one synthetic package. `give`/`receive` are
    {player: (serve_value, window_value)}."""
    serve_date = _days_ago(window + 2)
    window_date = rs._shift(serve_date, window)
    for pid, (v0, _v1) in {**give, **receive}.items():
        _snapshot(pid, serve_date, v0)
    for pid, (_v0, v1) in {**give, **receive}.items():
        _snapshot(pid, window_date, v1)
    _snapshot("pool_floor", serve_date, 10.0)
    _snapshot("pool_floor", window_date, 10.0)
    iid = _impression(served_days_ago=window + 2, give=tuple(give),
                      receive=tuple(receive))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row is not None and row["status"] == "graded", row
    return row


def test_t2_additive_drift_cancels_exactly_for_equal_cardinality(engine):
    """Uniform ADDITIVE drift `d` on a 1x1 → edge EXACTLY 0.

    This is the only part of the drift claim that is exact, and it is exact
    only because the cardinalities match. Stating more than this is the
    overclaim round 2 caught."""
    d = 120.0
    row = _grade_synthetic(give={"g1": (1000.0, 1000.0 + d)},
                           receive={"r1": (900.0, 900.0 + d)})
    assert row["edge"] == 0.0, (
        f"additive drift did not cancel on a 1x1: edge={row['edge']}. The "
        "give side IS the market control; if it stops cancelling, every "
        "number this feature publishes is measuring the market.")


def test_t2_additive_drift_residual_on_a_2x1_is_negative_d(engine):
    """The DISCLOSED residual, pinned WITH ITS SIGN.

    Taxonomy §2.1: the left side is what the deck's user GIVES. So a `2x1`
    gives two assets and receives one, `n_receive − n_given = −1`, and
    uniform additive drift `d` yields `edge = −d` — NOT `+d`.

    Round 3's only new blocker was this sign. It matters more than its size:
    T-2 is the matrix's one sign-sensitive test, so a mis-pin here would have
    shipped every win rendered as a loss and every loss as a win."""
    d = 75.0
    row = _grade_synthetic(
        give={"g1": (800.0, 800.0 + d), "g2": (700.0, 700.0 + d)},
        receive={"r1": (1500.0, 1500.0 + d)})
    assert row["edge"] == pytest.approx(-d), (
        f"2x1 additive-drift residual is {row['edge']}, expected {-d}. A "
        "flipped sign renders every win as a loss.")


def test_t2_a_directional_win_is_positive(engine):
    """The explicit directional case: the RECEIVE side gains `d`, the give
    side is flat → `edge = +d`, a win. Pairs with the residual test above so
    the sign convention is pinned in both directions rather than by
    example."""
    d = 200.0
    row = _grade_synthetic(give={"g1": (1000.0, 1000.0)},
                           receive={"r1": (1000.0, 1000.0 + d)})
    assert row["edge"] == pytest.approx(d)
    assert row["edge_pct"] == pytest.approx(d / 1000.0)


def test_t2_multiplicative_drift_is_near_zero_on_a_balanced_package(engine):
    """Uniform MULTIPLICATIVE drift `m` yields `edge = m · (serve-time
    imbalance)` — ≈0 for the near-balanced packages a fairness gate admits,
    and NOT exactly 0. Pinned as the proportional statement it is."""
    m = 1.10
    give_v, recv_v = 1000.0, 1020.0
    row = _grade_synthetic(give={"g1": (give_v, give_v * m)},
                           receive={"r1": (recv_v, recv_v * m)})
    assert row["edge"] == pytest.approx((m - 1.0) * (recv_v - give_v), abs=1e-6)
    assert abs(row["edge_pct"]) < 0.01


def test_t2_edge_pct_is_null_below_the_junk_midpoint(engine):
    """Junk-for-junk guard: a package whose serve-time midpoint is under
    `EDGE_PCT_MIN_MIDPOINT` records its edge but NULLs `edge_pct`. A ±40
    swing on a 60-value package is not a 67% call, and letting it into the
    median would let two waiver-wire scraps outvote a real trade."""
    row = _grade_synthetic(give={"g1": (60.0, 20.0)},
                           receive={"r1": (55.0, 60.0)})
    assert row["edge"] is not None
    assert row["edge_pct"] is None


# ---------------------------------------------------------------------------
# T-3 — anchor independence. Proves HLD D-2.
# ---------------------------------------------------------------------------

def test_t3_perturbing_features_json_values_changes_no_grade(engine):
    """Forbidden operation 2: reading the card's own frozen values.

    `features_json.give_value/receive_value` may be the USER'S PERSONAL board
    (`user_value_basis='personal'`, server.py:4159) and are engine units.
    Comparing them to later consensus would manufacture movement out of a
    basis mismatch. Two impressions, identical assets and dates, wildly
    different frozen values → byte-identical grades."""
    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    _pool([serve_date], {"p1": 1000.0, "p2": 1100.0})
    _pool([window_date], {"p1": 1050.0, "p2": 1300.0})

    a = _impression(served_days_ago=30, give=("p1",), receive=("p2",),
                    features={"give_value": 1.0, "receive_value": 2.0})
    b = _impression(served_days_ago=30, give=("p1",), receive=("p2",),
                    features={"give_value": 99999.0, "receive_value": 3.0})
    rs.run_grading(trigger="cron")

    ga, gb = _grade_for(a, window), _grade_for(b, window)
    fields = ("give_serve_value", "receive_serve_value", "give_delta",
              "receive_delta", "edge", "edge_pct", "coverage_give",
              "coverage_receive", "status")
    assert [ga[f] for f in fields] == [gb[f] for f in fields], (
        "frozen card values leaked into the grade — the prediction is the "
        "ASSET SET, not what the engine thought it was worth.")
    assert ga["edge"] == pytest.approx(200.0 - 50.0)


# ---------------------------------------------------------------------------
# T-4 — pick rules + deploy invariance. Proves HLD D-7.
# ---------------------------------------------------------------------------

def test_t4_picks_contribute_zero_delta_and_are_flagged(engine):
    """A pick never moves a grade. Its price is a static code seed, so
    "movement" in it would be our own commit history."""
    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    _pool([serve_date], {"p1": 1000.0, "p2": 1000.0, "p3": 1000.0})
    _pool([window_date], {"p1": 1000.0, "p2": 1400.0, "p3": 1000.0})

    iid = _impression(served_days_ago=30,
                      give=("p1", "p3"),
                      receive=("p2", "generic_pick_3_mid"))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row["status"] == "graded"
    assert row["has_picks"] == 1
    # Only p2 moved; the pick contributes nothing on either endpoint.
    assert row["edge"] == pytest.approx(400.0)
    detail = json.loads(row["assets_detail_json"])
    pick = [d for d in detail if d["is_pick"]][0]
    assert pick["cv0"] is None and pick["cv1"] is None


def test_t4_pick_majority_side_is_ungradeable(engine):
    """A side that is mostly picks has no measurable movement to grade, so it
    is excluded and DISCLOSED rather than quietly graded as flat — a flat
    grade would be a fabricated 'we were exactly right'."""
    serve_date, window = _days_ago(30), 28
    _pool([serve_date, rs._shift(serve_date, window)], {"cheap": 50.0})
    iid = _impression(served_days_ago=30, give=("cheap",),
                      receive=("generic_pick_1_mid", "cheap"))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row["status"] == "ungradeable"
    assert row["reason"] == "pick_majority"


def test_t4_pick_weights_are_frozen_value_units(engine):
    """The weights are the value-space image of the Mid rungs at the shipped
    elo_value_* defaults — recomputed here from first principles so a silent
    edit to the literals fails loudly."""
    import math
    expected = {1: 1650, 2: 1400, 3: 1320, 4: 1240}
    for rnd, elo in expected.items():
        assert rs.RECEIPTS_PICK_WEIGHTS[rnd] == pytest.approx(
            1000.0 * math.exp(0.0050 * (elo - 1500)), abs=0.1)


def test_t4_round_five_pick_clamps_to_the_round_four_weight():
    """The owned-pick regex admits any round. Without the clamp a round-5
    pick would raise KeyError inside the grader, the row would be skipped,
    and it would be re-queued FOREVER — a silent permanent backlog."""
    assert rs.pick_weight(5) == rs.RECEIPTS_PICK_WEIGHTS[4]
    assert rs.pick_weight(9) == rs.RECEIPTS_PICK_WEIGHTS[4]
    assert rs.pick_round(f"{LEAGUE}_2027_5_3", LEAGUE) == 5


def test_t4_repricing_generic_pick_seeds_changes_no_grade(engine):
    """DEPLOY INVARIANCE — the reason the weights are frozen at all.

    `GENERIC_PICK_SEEDS` are Elo units and are repriced by commits (D-084 cut
    round 2 on 2026-08-19). If the grader read them live, that single commit
    would have flipped existing impressions between `graded` and
    `pick_majority` under one `grader_version` — grades changing because we
    shipped, not because the market moved. Reprice them 3x here: the grade
    must be byte-identical."""
    from backend import pick_values

    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    _pool([serve_date], {"p1": 1000.0, "p2": 1000.0})
    _pool([window_date], {"p1": 900.0, "p2": 1200.0})
    iid = _impression(served_days_ago=30, give=("p1",),
                      receive=("p2", "generic_pick_4_mid"))
    rs.run_grading(trigger="cron")
    before = dict(_grade_for(iid, window))
    # Non-vacuous baseline: if the grader read live seeds, the round-4 pick
    # would weigh ~1240 ELO units against a 1000-value player and this row
    # would be `pick_majority` on BOTH sides of the comparison, making a
    # field-by-field equality check pass while proving nothing.
    assert before["status"] == "graded", before

    tripled = {k: v * 3 for k, v in pick_values.GENERIC_PICK_SEEDS.items()}
    with patch.object(pick_values, "GENERIC_PICK_SEEDS", tripled):
        iid2 = _impression(served_days_ago=30, give=("p1",),
                           receive=("p2", "generic_pick_4_mid"))
        rs.run_grading(trigger="cron")
        after = dict(_grade_for(iid2, window))

    assert after["status"] == "graded", (
        f"repricing the seeds turned a graded row into {after['status']}/"
        f"{after['reason']} — the grader is reading live seeds and is "
        "therefore grading our deploys, not the market.")
    for field in ("status", "reason", "edge", "edge_pct", "coverage_give",
                  "coverage_receive", "give_delta", "receive_delta"):
        assert before[field] == after[field], (
            f"{field} moved when GENERIC_PICK_SEEDS was repriced — the "
            "grader is reading live seeds and therefore grading deploys.")


def test_t4_pick_weights_survive_the_seed_table_disappearing():
    """The bluntest statement of the same rule: the frozen weights do not
    depend on `GENERIC_PICK_SEEDS` existing at all. Empty the seed table and
    the weights are unchanged — anything that reads it live raises here."""
    from backend import pick_values
    with patch.object(pick_values, "GENERIC_PICK_SEEDS", {}):
        assert rs.pick_weight(1) == 2117.0
        assert rs.pick_weight(4) == 272.5


# ---------------------------------------------------------------------------
# T-5 — anti-survivorship. Proves HLD D-8 + the §4.3 weight convention.
# ---------------------------------------------------------------------------

def test_t5_a_player_who_leaves_the_pool_is_floor_imputed_not_dropped(engine):
    """The single most important test in this file.

    A cratered player falls OUT of the consensus pool. Marking that row
    ungradeable would delete our worst outcomes — survivorship bias that
    flatters the engine, and it flatters it precisely where the engine was
    most wrong. He is imputed to the pool floor, the loss is retained, and
    the imputation is flagged and counted."""
    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    _pool([serve_date], {"bust": 900.0, "keeper": 1000.0})
    _pool([window_date], {"keeper": 1000.0})          # `bust` is GONE

    iid = _impression(served_days_ago=30, give=("keeper",), receive=("bust",))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)

    assert row["status"] == "graded", (
        "a bust made the row ungradeable — that is survivorship bias, and it "
        "deletes exactly the outcomes this feature exists to publish.")
    assert row["imputed_count"] == 1
    assert row["edge"] == pytest.approx(10.0 - 900.0)   # floor − serve value
    assert row["edge"] < 0, "the bust must render as the LOSS it was"
    detail = json.loads(row["assets_detail_json"])
    assert [d["imputed_floor"] for d in detail if d["id"] == "bust"] == [True]


def test_t5_unresolved_at_serve_is_weighted_at_the_floor_in_the_denominator(engine):
    """The round-2 B-B3 fix. A player with NO serve snapshot cannot be
    valued, but he must still occupy space in the coverage denominator at the
    serve-date floor — otherwise a package where one of three players
    resolved would report coverage 1.0 and sail through the coverage gate
    claiming to be a full measurement."""
    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    _pool([serve_date], {"known_a": 1000.0, "known_b": 1000.0})
    _pool([window_date], {"known_a": 1000.0, "known_b": 1100.0})

    iid = _impression(served_days_ago=30, give=("known_a", "ghost_player"),
                      receive=("known_b",))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row["status"] == "graded"
    assert row["coverage_give"] < 1.0, (
        "an unresolved player vanished from the denominator — coverage then "
        "overstates how much of the package was actually measured.")
    assert row["coverage_give"] == pytest.approx(1000.0 / (1000.0 + 10.0))
    assert row["coverage_receive"] == pytest.approx(1.0)


def test_t5_low_coverage_rows_are_excluded_from_the_user_surface(engine):
    """Coverage is compared on `min(give, receive)`: a package measured well
    on one side and barely on the other is not a swap measurement."""
    assert rs._coverage_ok({"coverage_give": 0.9, "coverage_receive": 0.2}, 0.5) is False
    assert rs._coverage_ok({"coverage_give": 0.6, "coverage_receive": 0.55}, 0.5) is True
    assert rs._coverage_ok({"coverage_give": None, "coverage_receive": 1.0}, 0.5) is False


# ---------------------------------------------------------------------------
# T-6 — snapshot matching. Proves LLD §4.2 / §4.3 step 4.
# ---------------------------------------------------------------------------

def test_t6_serve_anchor_never_uses_a_post_serve_snapshot(engine):
    """Nearest-≤, not nearest.

    Put a snapshot 1 day AFTER the serve date and another 3 days BEFORE. The
    later one is nearer — and using it would let information that did not
    exist at serve time into the baseline, which is look-ahead bias dressed
    up as tolerance. The grader must take the earlier one."""
    serve_date, window = _days_ago(30), 28
    before, after = rs._shift(serve_date, -3), rs._shift(serve_date, 1)
    window_date = rs._shift(serve_date, window)
    _pool([before], {"p1": 1000.0, "p2": 1000.0})
    _pool([after], {"p1": 5000.0, "p2": 5000.0})
    _pool([window_date], {"p1": 1000.0, "p2": 1200.0})

    iid = _impression(served_days_ago=30, give=("p1",), receive=("p2",))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row["serve_snap_date"] == before, (
        f"serve anchored to {row['serve_snap_date']} — a POST-serve snapshot "
        "is look-ahead bias, however near it is.")
    assert row["give_serve_value"] == pytest.approx(1000.0)


def test_t6_window_endpoint_matches_within_tolerance(engine):
    """The window endpoint resolves nearest within ±tol, and the date
    actually used is RECORDED so the admin `effective_window` block can show
    that a nominal 14-day window really spans 11–20 days."""
    serve_date, window = _days_ago(30), 28
    window_date = rs._shift(serve_date, window)
    near = rs._shift(window_date, 2)
    _pool([serve_date], {"p1": 1000.0, "p2": 1000.0})
    _pool([near], {"p1": 1000.0, "p2": 1300.0})

    iid = _impression(served_days_ago=30, give=("p1",), receive=("p2",))
    rs.run_grading(trigger="cron")
    row = _grade_for(iid, window)
    assert row["window_snap_date"] == near
    assert row["edge"] == pytest.approx(300.0)


def test_t6_retry_pending_writes_no_row_then_goes_terminal(engine):
    """Two halves of one rule.

    (a) A window whose snapshot has not arrived writes NO row — retry-pending
        is queue-implicit, never persisted, which is what keeps the queue's
        "absence means work" definition true.
    (b) Once the 14-day deadline passes it becomes terminally
        `missing_snapshot` rather than waiting forever.
    """
    serve_date, window = _days_ago(30), 28
    _pool([serve_date], {"p1": 1000.0, "p2": 1000.0})   # window date absent
    iid = _impression(served_days_ago=30, give=("p1",), receive=("p2",))

    rs.run_grading(trigger="cron")
    assert _grade_for(iid, window) is None, (
        "a retry-pending row was persisted — the queue is defined by the "
        "ABSENCE of a row, so writing one here permanently hides the work.")

    # Same impression, now well past the deadline.
    old = _impression(served_days_ago=window + rs.RETRY_GRACE_DAYS + 3,
                      give=("p1",), receive=("p2",))
    old_serve = _days_ago(window + rs.RETRY_GRACE_DAYS + 3)
    _pool([old_serve], {"p1": 1000.0, "p2": 1000.0})
    rs.run_grading(trigger="cron")
    row = _grade_for(old, window)
    assert row is not None and row["reason"] == "missing_snapshot"


def test_t6_retry_pending_rows_do_not_starve_the_batch_cap(engine):
    """Skip-and-fill, on the case that can actually produce it.

    The queue predicate takes the UNION of resolvable serve dates across both
    scoring formats (a superset — the two are written by one daily job and
    diverge only on a partial write). So a `sf_tep` impression can be SELECTED
    because `1qb_ppr` resolved that date, and then turn out to be retry-pending
    for its own format. Served earlier, it sorts to the head of the queue.

    Both impressions here are inside the 14-day window only (served 20 and 18
    days ago), so the 28/56 windows have not elapsed and cannot muddy the cap.
    With `batch=1`, a run that let the retry-pending head consume the cap would
    report a full batch while making zero progress — indefinitely, silently."""
    window = 14
    with db_module.engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id="L-sftep", user_id=VIEWER, name="SF league",
            default_scoring="sf_tep"))

    stale_serve = _days_ago(20)                      # head of the queue
    good_serve = _days_ago(18)
    # 1qb_ppr resolves BOTH window endpoints, so both serve dates enter the
    # union the queue predicate is built from.
    _pool([stale_serve, rs._shift(stale_serve, window),
           good_serve, rs._shift(good_serve, window)],
          {"p1": 1000.0, "p2": 1100.0})
    # sf_tep has the serve endpoint only — its window endpoint has not
    # arrived and is still well inside the 14-day retry grace.
    _pool([stale_serve], {"s1": 900.0, "s2": 900.0}, fmt="sf_tep")

    stale = _impression(served_days_ago=20, league_id="L-sftep",
                        give=("s1",), receive=("s2",))
    good = _impression(served_days_ago=18, give=("p1",), receive=("p2",))

    rs.run_grading(trigger="cron", batch=1)

    assert _grade_for(stale, window) is None, (
        "a retry-pending row was persisted instead of skipped")
    assert _grade_for(good, window) is not None, (
        "a retry-pending head-of-queue row consumed the batch cap — a "
        "backlog of them would stall grading indefinitely.")


# ---------------------------------------------------------------------------
# T-7 — idempotency. Proves LLD §5.1.
# ---------------------------------------------------------------------------

def _seed_gradeable(n: int = 3, window: int = 28) -> list[str]:
    serve_date = _days_ago(30)
    window_date = rs._shift(serve_date, window)
    ids = []
    for i in range(n):
        _pool([serve_date], {f"a{i}": 1000.0, f"b{i}": 1000.0})
        _pool([window_date], {f"a{i}": 1000.0, f"b{i}": 1100.0 + i})
        ids.append(_impression(served_days_ago=30, give=(f"a{i}",),
                               receive=(f"b{i}",)))
    return ids


def test_t7_a_second_run_inserts_nothing(engine):
    """The job runs daily and can double-fire (cron + daily-tick guard on the
    same day). A second run over the same work must be a no-op, not a
    duplicate — duplicates would silently double a card's vote in every
    aggregate."""
    _seed_gradeable(3)
    first = rs.run_grading(trigger="cron")
    count_after_first = len(_grades())
    second = rs.run_grading(trigger="daily_tick")
    assert first["graded"] > 0
    assert second["graded"] == 0 and second["ungradeable"] == 0
    assert len(_grades()) == count_after_first


def test_t7_a_partial_insert_crash_resumes_without_duplicates(engine):
    """Crash simulation: a run dies after writing part of a batch (a Render
    free-instance spin-down mid-run is exactly this). Completed inserts
    stand, the rest re-queue, and the re-run produces no duplicate — the
    unique constraint plus insert-or-ignore is the whole mechanism."""
    ids = _seed_gradeable(4)
    real_insert = db_module.insert_receipts_grades

    def _half(rows):
        return real_insert(rows[:2])          # the crash: half the batch lands

    with patch.object(db_module, "insert_receipts_grades", _half):
        rs.run_grading(trigger="cron")
    partial = len(_grades())
    assert 0 < partial < len(ids) * len(rs.WINDOWS_DAYS)

    rs.run_grading(trigger="cron")
    rows = _grades()
    keys = [(r["impression_id"], r["window_days"], r["grader_version"])
            for r in rows]
    assert len(keys) == len(set(keys)), "the crash re-run duplicated rows"
    assert len(rows) > partial


def test_t7_the_run_ledger_records_a_start_end_pair(engine):
    """The ledger is the only observability a job with no UI has. Two rows
    per run sharing a `run_id`; a killed run shows up as an UNMATCHED start,
    which is the entire point of splitting them."""
    _seed_gradeable(1)
    rs.run_grading(trigger="cron")
    ledger = db_module.load_receipts_grade_runs()
    kinds = {}
    for row in ledger:
        kinds.setdefault(row["run_id"], set()).add(row["kind"])
    assert any(v == {"start", "end"} for v in kinds.values())
    end = [r for r in ledger if r["kind"] == "end"][0]
    assert end["trigger"] == "cron"
    assert end["grader_version"] == rs.GRADER_VERSION
    assert end["duration_ms"] is not None


def test_t7_flag_off_writes_absolutely_nothing(engine, monkeypatch):
    """Rollback has to be real. Flag off ⇒ no grade rows AND no ledger rows —
    a ledger row alone would still be a write on a dark feature."""
    _seed_gradeable(2)
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    out = rs.run_grading(trigger="cron")
    assert out["skipped"] == "flag"
    assert _grades() == []
    assert db_module.load_receipts_grade_runs() == []


def test_t7_env_kill_switch_stops_the_grader_without_a_flag_write(engine,
                                                                 monkeypatch):
    """`FTF_RECEIPTS_GRADE=0` is the deploy-free lever that does not need a
    flag edit — the one an operator reaches for at 2am."""
    _seed_gradeable(1)
    monkeypatch.setenv("FTF_RECEIPTS_GRADE", "0")
    assert rs.grading_enabled() is False
    assert rs.run_grading(trigger="cron")["skipped"] == "flag"
    assert _grades() == []


# ---------------------------------------------------------------------------
# T-8 — regrade. Proves HLD D-3.
# ---------------------------------------------------------------------------

def test_t8_bumping_grader_version_adds_rows_and_retains_the_old_ones(engine):
    """Corrections without goalpost-moving.

    A wrong grade is never edited. The version bumps, the whole cohort is
    regraded, the old rows STAY (that is the audit trail), and reads pin the
    max version. Without retention, "we corrected it" is indistinguishable
    from "we rewrote history"."""
    ids = _seed_gradeable(2)
    rs.run_grading(trigger="cron")
    v1_rows = _grades(grader_version="receipts-1")
    assert v1_rows

    with patch.object(rs, "GRADER_VERSION", "receipts-2"):
        rs.run_grading(trigger="cron")
        v2_rows = _grades(grader_version="receipts-2")

    assert v2_rows, "the version bump regraded nothing"
    assert len(_grades(grader_version="receipts-1")) == len(v1_rows), (
        "superseded rows were removed — that destroys the audit trail the "
        "append-only design exists to keep.")
    versions = db_module.load_receipts_grader_versions()
    assert rs.max_grader_version(versions) == "receipts-2"


def test_t8_max_grader_version_orders_by_numeric_suffix_not_lexically():
    """`receipts-10` beats `receipts-2`. Lexicographic ordering would pin
    reads to a STALE version the moment the tenth correction ships, and it
    would do so silently."""
    assert rs.max_grader_version(
        ["receipts-2", "receipts-10", "receipts-9"]) == "receipts-10"
    assert rs.parse_grader_version("receipts-10") == 10


# ---------------------------------------------------------------------------
# T-9 — route contracts. Proves LLD §2.2 / §2.3.
# ---------------------------------------------------------------------------

def test_t9_wilson_interval_matches_the_pinned_triple():
    """3 wins of 5 → [0.231, 0.882], the centre-shifted form.

    Round 2 caught the shift dropped. At n ≤ 10 — where this feature lives
    for months — that error is 0.2–0.4 wide, on a trust feature."""
    low, high = rs.wilson_interval(3, 5)
    assert round(low, 3) == 0.231
    assert round(high, 3) == 0.882


def test_t9_ghost_rows_are_excluded_at_the_QUEUE_layer(engine):
    """Operator ruling 2026-08-21, layer one: an `is_ghost=1` impression
    never enters the grading queue at all. Not filtered later — never
    graded."""
    serve_date, window = _days_ago(30), 28
    _pool([serve_date, rs._shift(serve_date, window)],
          {"p1": 1000.0, "p2": 1200.0})
    ghost = _impression(served_days_ago=30, give=("p1",), receive=("p2",),
                        is_ghost=1)
    served = _impression(served_days_ago=30, give=("p1",), receive=("p2",),
                         is_ghost=0)
    rs.run_grading(trigger="cron")
    assert _grade_for(ghost, window) is None, (
        "a ghost row was graded — the operator ruled ghosts out entirely.")
    assert _grade_for(served, window) is not None


def test_t9_ghost_rows_are_excluded_at_the_ROUTE_layer_too(engine):
    """Layer two, defence in depth. Even if a ghost grade somehow existed —
    an older grader version, a hand-inserted row — the read filters it."""
    with db_module.engine.begin() as conn:
        conn.execute(db_module.receipts_grades_table.insert().values(
            impression_id="ghost-1", window_days=28,
            grader_version=rs.GRADER_VERSION, status="graded", edge=500.0,
            edge_pct=0.5, coverage_give=1.0, coverage_receive=1.0,
            league_id=LEAGUE, user_id=VIEWER, served_at="2026-08-16T00:00:00",
            trade_hash="gh", is_ghost=1, graded_at="2026-08-20T00:00:00"))
    payload = rs.league_receipts(VIEWER, LEAGUE)
    assert all(r["impression_id"] != "ghost-1" for r in payload["rows"])


def test_t9_payload_carries_all_three_windows_always(engine):
    """Anti-cherry-pick BY CONSTRUCTION. There is no per-window endpoint, so
    no surface — this one or a later one — can request only the flattering
    window. A window with no data says `pending`; it is never omitted."""
    _seed_gradeable(1)
    rs.run_grading(trigger="cron")
    payload = rs.league_receipts(VIEWER, LEAGUE)
    assert [w["window_days"] for w in payload["windows"]] == [14, 28, 56]
    assert payload["headline_window_days"] == 28
    assert set(payload["maturity"]["graded_n"]) == {"14", "28", "56"}


def test_t9_headline_is_gated_until_min_n(engine):
    """Sub-min-n leagues get the maturity state and NO number. A win share
    computed on n=3 is not a track record, and publishing one would be the
    first debunkable claim."""
    _seed_gradeable(3)
    rs.run_grading(trigger="cron")
    payload = rs.league_receipts(VIEWER, LEAGUE)
    w28 = [w for w in payload["windows"] if w["window_days"] == 28][0]
    assert w28["status"] == "insufficient"
    assert "win_share" not in w28, (
        "a win share leaked out below min-n — the gate is the whole "
        "small-n discipline.")
    assert payload["maturity"]["mature"]["28"] is False
    assert payload["maturity"]["tracked_n"] == 3


def test_t9_n_equals_the_rows_the_stats_were_computed_over(engine,
                                                           monkeypatch):
    """The round-2 B-B5 fix: `n` is the POST-dedup, POST-coverage count, and
    every displayed statistic is computed over exactly those rows. An `n`
    that describes a different set than the number beside it is the quiet
    way a trust feature starts lying."""
    ids = _seed_gradeable(12)
    rs.run_grading(trigger="cron")
    payload = rs.league_receipts(VIEWER, LEAGUE)
    w28 = [w for w in payload["windows"] if w["window_days"] == 28][0]
    assert w28["status"] == "ready"
    graded_28 = [r for r in _grades(window_days=28) if r["status"] == "graded"
                 and rs._coverage_ok(r, 0.5)]
    assert w28["n"] == len(graded_28) == payload["maturity"]["graded_n"]["28"]
    # win_share must be recomputable from exactly that row set.
    wins = sum(1 for r in graded_28 if (r["edge"] or 0) > 0)
    assert w28["win_share"] == pytest.approx(round(wins / w28["n"], 4))


def test_t9_reserves_dedup_to_the_earliest_serve(engine):
    """A deck regeneration can re-serve an identical card. Counting it twice
    would let one call carry two votes in every aggregate."""
    serve_date, window = _days_ago(30), 28
    _pool([serve_date, rs._shift(serve_date, window)],
          {"p1": 1000.0, "p2": 1200.0})
    early = _impression(served_days_ago=32, give=("p1",), receive=("p2",),
                        trade_hash="same-card")
    _pool([_days_ago(32), rs._shift(_days_ago(32), window)],
          {"p1": 1000.0, "p2": 1200.0})
    _impression(served_days_ago=30, give=("p1",), receive=("p2",),
                trade_hash="same-card")
    rs.run_grading(trigger="cron")

    payload = rs.league_receipts(VIEWER, LEAGUE)
    hashes = [r["impression_id"] for r in payload["rows"]]
    assert len(hashes) == 1 and hashes[0] == early, (
        "a re-served card counted twice — one suggestion, one vote.")
    assert payload["disclosure"]["deduped_reserves"] == 1


def test_t9_viewer_scoping_hides_other_users_rows(engine):
    """Cross-user receipts are unreachable (PLAN NG-3): other managers' decks
    are private, and at n≈5 leagues an aggregate is reverse-engineerable."""
    serve_date, window = _days_ago(30), 28
    _pool([serve_date, rs._shift(serve_date, window)],
          {"p1": 1000.0, "p2": 1200.0})
    mine = _impression(served_days_ago=30, user_id=VIEWER)
    theirs = _impression(served_days_ago=30, user_id=OTHER)
    rs.run_grading(trigger="cron")
    ids = {r["impression_id"] for r in rs.league_receipts(VIEWER, LEAGUE)["rows"]}
    assert mine in ids and theirs not in ids


def test_t9_best_and_worst_call_are_both_present_or_both_absent(engine):
    """Best-call is never shown without worst-call (PRD §4.4). Both are
    max/min `edge_pct` over the SAME displayed rows, so the selection is
    symmetric by construction rather than by editorial restraint."""
    _seed_gradeable(12)
    rs.run_grading(trigger="cron")
    payload = rs.league_receipts(VIEWER, LEAGUE)
    best = payload["best_call_impression_id"]
    worst = payload["worst_call_impression_id"]
    assert (best is None) == (worst is None)
    assert best is not None and worst is not None


def test_t9_disclosure_reports_exclusions_and_methodology(engine):
    """Selection disclosure is STRUCTURAL: gradeable share and the exclusion
    breakdown ride in the payload beside the numbers, not in a footnote
    someone can forget to render."""
    _seed_gradeable(2)
    rs.run_grading(trigger="cron")
    d = rs.league_receipts(VIEWER, LEAGUE)["disclosure"]
    for key in ("gradeable_share", "ties", "null_edge_pct", "excluded",
                "methodology", "pre_telemetry"):
        assert key in d
    assert "consensus" in d["methodology"]
    assert "accuracy" not in d["methodology"].lower(), (
        "banned phrasing: this measures agreement with market consensus, "
        "not accuracy (PRD §4.2).")


def test_t9_pre_telemetry_rows_are_disclosed_not_graded(engine):
    """Pre-telemetry impressions (`assets_json IS NULL`) are permanently
    ungradeable — `trade_hash` is not invertible. They are COUNTED and
    disclosed rather than silently dropped from the denominator."""
    _impression(served_days_ago=200, assets_json=None)
    payload = rs.league_receipts(VIEWER, LEAGUE)
    assert payload["disclosure"]["pre_telemetry"] == 1
    assert payload["maturity"]["tracked_n"] == 0


def test_t9_admin_cells_carry_n_and_an_interval(engine):
    """No bare percentages anywhere. Every admin cell ships `n` and a Wilson
    interval; a point estimate alone at single-digit n is a claim the data
    cannot support."""
    _seed_gradeable(4)
    rs.run_grading(trigger="cron")
    out = rs.admin_metrics(window=28)
    assert out["cells"]
    for cell in out["cells"]:
        assert cell["n"] >= 0
        assert "wilson_low" in cell and "wilson_high" in cell
        assert "gradeable_share" in cell and "flag_low_share" in cell
    assert out["grader_version"] == rs.GRADER_VERSION
    assert out["taxonomy_version"] == rs.TAXONOMY_VERSION


def test_t9_effective_window_reports_the_real_span(engine):
    """A nominal 14-day window really spans ~11–20 days once both anchors
    resolve. The operator reads the number knowing that, or the number is
    quietly mislabelled."""
    serve_date, window = _days_ago(30), 28
    _pool([rs._shift(serve_date, -2)], {"p1": 1000.0, "p2": 1000.0})
    _pool([rs._shift(serve_date, window + 2)], {"p1": 1000.0, "p2": 1100.0})
    _impression(served_days_ago=30, give=("p1",), receive=("p2",))
    rs.run_grading(trigger="cron")
    eff = rs.admin_metrics(window=28)["effective_window"]
    assert eff["28"]["n"] >= 1
    assert eff["28"]["min"] == 32                # 28 + 2 (window) + 2 (serve)


# --- route-level contracts (Flask client) ----------------------------------

@pytest.fixture()
def client(engine, monkeypatch):
    from backend import server
    server.app.config["TESTING"] = True
    token = "tok-receipts"
    with server._sessions_lock:
        server._sessions[token] = {"verified": True, "user_id": VIEWER, "last_active": 0.0,
                                   "initialized": True}
    try:
        yield server.app.test_client(), token, server
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


def test_t9_user_route_404s_while_the_screen_flag_is_dark(client, monkeypatch):
    """Flag off ⇒ 404 `feature_disabled`, which is what lets the client HIDE
    the entry point rather than show an error dialog (PRD FR-5)."""
    c, token, server = client
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(server, "is_enabled", lambda k: False)
    res = c.get(f"/api/league/{LEAGUE}/receipts",
                headers={"X-Session-Token": token})
    assert res.status_code == 404
    assert res.get_json()["error"] == "feature_disabled"


def test_t9_cron_route_is_a_202_and_no_ops_while_dark(client, monkeypatch):
    """202 always — the grading loop must never run inline on the single
    gunicorn worker, so the route hands work to a daemon thread and answers
    immediately. Flag off returns 200 `skipped` and writes nothing.

    `run_grading` is stubbed here deliberately: this test is about the ROUTE
    contract, and letting a real daemon thread outlive the in-memory-engine
    patch would write to the dev DB (which the suite never touches)."""
    c, _token, server = client
    calls = []
    monkeypatch.setattr(rs, "run_grading",
                        lambda **kw: calls.append(kw) or {"ok": True})

    res = c.post("/api/cron/receipts-grade")
    assert res.status_code == 202
    body = res.get_json()
    assert body["ok"] is True and "remaining_resolvable" in body
    assert body["started"] is True

    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    res = c.post("/api/cron/receipts-grade")
    assert res.status_code == 200
    assert res.get_json()["skipped"] == "flag"
    assert _grades() == []


def test_t9_cron_route_rejects_a_nonsense_batch(client):
    c, _token, _server = client
    res = c.post("/api/cron/receipts-grade?batch=banana")
    assert res.status_code == 400


def test_t9_daily_tick_payload_is_byte_identical_while_grading_is_dark(
        client, monkeypatch):
    """The daily-tick guard must be INVISIBLE while dark.

    The tick's response payload is a contract other tests pin
    (test_deck_replenishment.py). Adding a `receipts_grade_started: false` key
    to every flag-off tick would be a payload change shipped by a dark
    feature — the exact thing the `_run_weekly_replenishment` convention
    exists to prevent. The counter appears only once grading is ON."""
    from backend import server
    c, _token, _server = client
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(server, "load_all_signed_up_users", lambda: [])
    res = c.post("/api/cron/daily-tick", headers={"X-Cron-Secret": "x"})
    assert res.status_code == 200
    assert "receipts_grade_started" not in res.get_json()


def test_t9_admin_route_404s_while_grading_is_dark(client, monkeypatch):
    c, _token, server = client
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    res = c.get("/api/admin/receipts/metrics")
    assert res.status_code == 404
    assert res.get_json()["error"] == "feature_disabled"


# ---------------------------------------------------------------------------
# T-10 — append-only. Proves HLD D-3 mechanically.
# ---------------------------------------------------------------------------

RECEIPTS_TABLES = ("receipts_grades", "receipts_grade_runs")


def test_t10_no_update_or_delete_path_exists_for_receipts_tables():
    """Forbidden operation 4, enforced by grep rather than by intention.

    "We can't move the goalposts" has to be MECHANICAL. If an UPDATE or
    DELETE against a receipts table ever compiles, the append-only claim is
    marketing. Both the service and the database helpers are scanned."""
    offenders = []
    for name in ("receipts_service.py", "database.py"):
        for i, line in enumerate((REPO / "backend" / name).read_text()
                                 .splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for table in RECEIPTS_TABLES:
                token = f"{table}_table"
                if token in line and (".update(" in line or ".delete(" in line):
                    offenders.append(f"{name}:{i}: {stripped}")
            if ("receipts" in line.lower()
                    and ("UPDATE receipts" in line or "DELETE FROM receipts" in line)):
                offenders.append(f"{name}:{i}: {stripped}")
    assert offenders == [], (
        "an UPDATE/DELETE path against a receipts table exists:\n"
        + "\n".join(offenders)
        + "\nCorrections are a grader_version bump plus a regrade, with the "
          "old rows retained. Editing a grade destroys the audit trail that "
          "makes the preregistration claim checkable.")


def test_t10_regrading_never_mutates_an_existing_row(engine):
    """The behavioural half of T-10: run, snapshot every row, regrade under a
    new version, and assert the ORIGINAL rows are byte-identical."""
    _seed_gradeable(2)
    rs.run_grading(trigger="cron")
    before = {(r["impression_id"], r["window_days"]): dict(r)
              for r in _grades(grader_version="receipts-1")}
    with patch.object(rs, "GRADER_VERSION", "receipts-2"):
        rs.run_grading(trigger="cron")
    after = {(r["impression_id"], r["window_days"]): dict(r)
             for r in _grades(grader_version="receipts-1")}
    assert before == after, "a regrade mutated the superseded rows"


# ---------------------------------------------------------------------------
# Registration guards — the five-registration rule for every knob
# ---------------------------------------------------------------------------

RECEIPTS_KNOBS = ("receipts_grade_batch", "receipts_min_n",
                  "receipts_coverage_min", "receipts_pick_share_max",
                  "receipts_snap_tolerance_days")


def test_every_receipts_knob_is_seeded_in_model_config_defaults():
    """Without a `_MODEL_CONFIG_DEFAULTS` row, `set_config` raises KeyError
    and `PUT /api/admin/config/<key>` 404s — which would make the knob half
    of the rollback ladder theater."""
    seeded = {k: v for k, v, _d in db_module._MODEL_CONFIG_DEFAULTS}
    for key in RECEIPTS_KNOBS:
        assert key in seeded, f"missing _MODEL_CONFIG_DEFAULTS row: {key}"


def test_receipts_knobs_are_absent_from_the_generation_config():
    """These are OFFLINE grading knobs. Arm A — and every other arm — must be
    unable to observe them, which is why they are deliberately NOT in
    `trade_service._DEFAULT_CFG` and therefore not in `_PINNED_KNOBS`. Their
    arm-A disposition sentences live in
    docs/plans/three-model-bakeoff/scope-phase2.md."""
    from backend import trade_service as ts
    for key in RECEIPTS_KNOBS:
        assert key not in ts._DEFAULT_CFG, (
            f"{key} entered the generation config — an offline grading knob "
            "in _DEFAULT_CFG becomes a new way for arm A to drift.")


def test_receipts_flags_are_registered_and_default_false():
    """Code defaults stay dark (registry False) so a missing features.json
    key never lights anything. SHIP STATE (operator Q-1..Q-4 rulings,
    2026-08-22): receipts.grading is LIT in features.json so the nightly
    grader accrues; receipts.screen stays dark until the operator's
    TestFlight pass. Both files must mirror each other exactly."""
    for key in ("receipts.grading", "receipts.screen"):
        assert key in ff.FLAG_KEYS
        assert ff.DEFAULT_FLAGS[key] is False
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads(
        (REPO / "backend/tests/fixtures/flags/release.json").read_text())
    for key, expected in (("receipts.grading", True), ("receipts.screen", False)):
        assert features[key] is expected, key
        assert release[key] is expected, key
def test_receipts_grade_run_is_server_fired_and_non_intent():
    """Analytics classification, asserted rather than assumed: the event is
    server-authoritative (never client-forgeable) and NON_INTENT (a cron tick
    must not mint a user-day)."""
    from backend import analytics_queries as aq
    from backend import analytics_taxonomy as at
    assert "receipts_grade_run" in at.SERVER_FIRED_EVENTS
    assert "receipts_grade_run" not in at.ALLOWED_CLIENT_EVENTS
    assert "receipts_grade_run" in aq.NON_INTENT_EVENTS
