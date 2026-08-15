"""B8 — propensity freeze + the nightly drift check (T-4; LLD §3.6/§4.13,
HLD §2.3/§5.3, PRD R10).

THE CONTRACT (HLD §2.3): every layer that touches serving order must either be
replayable from the logged `features_json`, or contribute its factor to the
logged `propensity`. Its corollary: anything read from a nightly-mutating table
is FROZEN into the serve-time capture, because replay reconstructing table
state at serve time is leakage (D8).

That contract is unenforceable by review — the failure mode is a layer someone
adds in six months and forgets to log. So it is enforced arithmetically:

    final_score  ==  base × propensity × Π(frozen multipliers)      (±1%)

and the nightly `drift_check` pass re-derives it from yesterday's impressions.

The single most important test in this file is
`test_t4_unlogged_multiplier_is_caught`: it adds a real, unlogged ×1.3 reorder
layer — the exact mistake the check exists for — and asserts the check goes
red. If that test can be made to pass with the drift check gutted, B8 bought
nothing.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import deck_impressions_table, metadata
from backend.relevance.passes import drift_check as dc
from backend.relevance.registry import PassContext
from backend.trade_service import TradeCard


LEAGUE = "league_fs2"
ME     = "user_me"
OPP    = "user_opp"
JOB    = "job-fs2"

SEED_MAP = {f"p{i}": 3000.0 - 10 * i for i in range(1, 12)}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture()
def marker_dir(tmp_path, monkeypatch):
    """`untrusted-<date>` lands next to the F8 eval runs; point that at tmp."""
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "eval_runs"))
    return tmp_path / "eval_runs"


def _card(pid_give, pid_recv, composite, *, likes_you=False, target=OPP):
    return TradeCard(
        trade_id           = f"t_{pid_give}_{pid_recv}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = target,
        target_username    = "opp",
        give_player_ids    = [pid_give],
        receive_player_ids = [pid_recv],
        mismatch_score     = 1.0,
        fairness_score     = 0.9,
        composite_score    = composite,
        likes_you          = likes_you,
    )


class _P:
    def __init__(s, i):
        s.id, s.name, s.position, s.team, s.age = i, i, "RB", "T", 24


PLAYERS = {pid: _P(pid) for pid in SEED_MAP}


def _flags(**kw):
    """Patch the deck flag helpers; anything unnamed is OFF."""
    defaults = {
        "_thompson_deck_enabled": False, "_deck_thompson_v2_enabled": False,
        "_deck_diversity_enabled": False, "_deck_fatigue_enabled": False,
        "_deck_taste_enabled": False, "_deck_dedup_enabled": False,
    }
    defaults.update(kw)
    from contextlib import ExitStack
    stack = ExitStack()
    for name, val in defaults.items():
        stack.enter_context(patch.object(server, name, lambda v=val: v))
    return stack


def _serve(cards, *, fatigue=None, taste=None, value_scores=None,
           order_fn=None, job_id=JOB):
    """The `_run_trade_job` sequence, minus the job plumbing: order the deck
    with a live capture, then write the impression rows from that capture."""
    capture: dict = {}
    ordered = (order_fn or server._order_deck)(
        cards, user_id=ME, league_id=LEAGUE, job_id=job_id, seed_map=SEED_MAP,
        capture=capture, fatigue_mult=fatigue, taste_mult=taste,
        value_scores=value_scores, dedup_stats={},
    )
    server._log_deck_signal_impressions(
        user_id=ME, league_id=LEAGUE, job_id=job_id, cards=ordered,
        players_dict=PLAYERS, capture=capture, scoring_format="1qb_ppr",
        seed_map=SEED_MAP,
    )
    return ordered, capture


def _rows(eng, job_id=JOB):
    t = deck_impressions_table
    with eng.connect() as conn:
        rows = list(conn.execute(
            select(t).where(t.c.deck_job_id == job_id)
            .order_by(t.c.card_index)))
    return [(r, json.loads(r.features_json)) for r in rows]


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# The freeze itself (LLD §3.6)
# ---------------------------------------------------------------------------

def test_every_fs2_row_is_stamped(mem_engine):
    """`feature_set` is the predicate the drift check samples on.

    SABOTAGE: stamp it only when a multiplier layer ran ⇒ the plain-ordering
    majority of impressions is never checked, and the tripwire covers the one
    path least likely to break.
    """
    with _flags():
        _serve([_card("p1", "p2", 5.0), _card("p3", "p4", 4.0)])
    for _row, f in _rows(mem_engine):
        assert f["feature_set"] == dc.FEATURE_SET


def test_applied_fatigue_and_taste_are_frozen_exactly(mem_engine):
    """A card that had fatigue and taste applied carries THOSE numbers.

    SABOTAGE: freeze the multiplier map the caller passed in rather than the
    value `_order_deck` actually used ⇒ the fatigue clamp (`min(1.0, m)`) is
    invisible to replay, and a >1.0 fatigue bug would reconstruct perfectly
    while mis-serving in production.
    """
    a, b = _card("p1", "p2", 5.0), _card("p3", "p4", 4.0)
    # 1.4 must be CLAMPED to 1.0 by the fatigue layer — fatigue never boosts.
    fatigue = {id(a): 0.6, id(b): 1.4}
    taste   = {id(a): 1.25, id(b): 0.8}
    with _flags(_thompson_deck_enabled=True):
        _serve([a, b], fatigue=fatigue, taste=taste)

    by_hash = {r.trade_hash: f for r, f in _rows(mem_engine)}
    fa = by_hash[server._deck_trade_hash(["p1"], ["p2"], OPP)]
    fb = by_hash[server._deck_trade_hash(["p3"], ["p4"], OPP)]
    assert fa["fatigue_mult"] == 0.6 and fa["taste_mult"] == 1.25
    assert fb["fatigue_mult"] == 1.0 and fb["taste_mult"] == 0.8


def test_layers_that_did_not_run_leave_no_key(mem_engine):
    """Absent ⇒ neutral. A card served with no presentation layer active
    carries no multiplier keys at all.

    SABOTAGE: write 1.0 placeholders for every layer ⇒ replay can no longer
    distinguish "fatigue ran and found nothing" from "fatigue was off", which
    is precisely the distinction an off-policy estimator needs.
    """
    with _flags():
        _serve([_card("p1", "p2", 5.0)])
    _row, f = _rows(mem_engine)[0]
    for key in dc.FROZEN_MULTIPLIER_KEYS:
        assert key not in f
    assert "base_key" not in f


def test_diversity_penalty_is_frozen_per_card(mem_engine):
    """The diversity layer reads a rolling impression count — a table that
    mutates nightly, so HLD §2.3's corollary applies to it directly.

    SABOTAGE: freeze only the penalized cards ⇒ an un-penalized card is
    indistinguishable from a card the layer never saw, and the day the window
    rolls, replay silently re-derives a different penalty.
    """
    hot, cold = _card("p1", "p2", 5.0), _card("p3", "p4", 4.0)
    with _flags(_deck_diversity_enabled=True), \
         patch.object(server, "load_recent_impression_target_user_counts",
                      lambda *a, **k: {"p2": 99}), \
         patch.object(server, "_deck_cfg",
                      lambda k, d=None: {"diversity_user_cap": 3,
                                         "diversity_penalty": 0.6,
                                         "diversity_window_days": 7,
                                         "deck_max_per_target": 3}.get(k, d)):
        _serve([hot, cold])

    by_hash = {r.trade_hash: f for r, f in _rows(mem_engine)}
    assert by_hash[server._deck_trade_hash(["p1"], ["p2"], OPP)]["diversity_mult"] == 0.6
    assert by_hash[server._deck_trade_hash(["p3"], ["p4"], OPP)]["diversity_mult"] == 1.0


def test_model_base_key_swap_is_frozen(mem_engine):
    """F6 replaces the BASE ordering key, so `base_score` (the composite) is
    no longer what the multipliers multiplied. The applied base is frozen.

    SABOTAGE: drop the `base_key` freeze ⇒ the identity breaks for every card
    on every job the day `deck.value_model` flips on, and the drift check
    cries wolf nightly instead of catching the real thing.
    """
    a = _card("p1", "p2", 5.0)
    with _flags():
        _serve([a, _card("p3", "p4", 4.0)], value_scores={id(a): 42.0})
    by_hash = {r.trade_hash: (r, f) for r, f in _rows(mem_engine)}
    row, f = by_hash[server._deck_trade_hash(["p1"], ["p2"], OPP)]
    assert f["base_key"] == 42.0
    assert row.base_score == 5.0          # the composite is still recorded
    assert row.final_score == 42.0


# ---------------------------------------------------------------------------
# T-4 — propensity integrity
# ---------------------------------------------------------------------------

def _recompute(row, features):
    return dc.expected_final(row.base_score, row.propensity, features)


def test_t4_frozen_values_reproduce_the_served_order(mem_engine):
    """THE REPLAY PROPERTY: with the whole stack live, the served order is
    recomputable from frozen values alone — no table reads, no re-derivation.

    SABOTAGE: apply any multiplier to the ordering key AFTER
    `capture["final_key"]` is taken ⇒ the recomputed ranking stops matching
    `card_index`, which is the same break the nightly check reports.
    """
    cards = [_card(f"p{i}", f"p{i + 1}", 10.0 - i) for i in range(1, 6)]
    fatigue = {id(c): 0.5 + 0.1 * n for n, c in enumerate(cards)}
    taste   = {id(c): 1.3 - 0.1 * n for n, c in enumerate(cards)}
    with _flags(_thompson_deck_enabled=True):
        served, _cap = _serve(cards, fatigue=fatigue, taste=taste)

    rows = _rows(mem_engine)
    assert len(rows) == len(cards)
    # Served order, as logged.
    served_hashes = [r.trade_hash for r, _f in rows]
    # Order recomputed from nothing but the frozen numbers.
    replayed = sorted(rows, key=lambda rf: _recompute(rf[0], rf[1]),
                      reverse=True)
    assert [r.trade_hash for r, _f in replayed] == served_hashes

    # …and the identity itself holds card by card.
    for row, f in rows:
        assert abs(row.final_score - _recompute(row, f)) <= 1e-9
    report = dc.check_drift(day=_today())
    assert report["sampled"] == len(cards) and report["violations"] == 0


def test_t4_unlogged_multiplier_is_caught(mem_engine, marker_dir):
    """THE TRIPWIRE (R4). A new reorder layer applies ×1.3 to one card and
    logs nothing — the mistake this whole mechanism exists to catch.

    SABOTAGE: widen TOLERANCE_FRAC past 30%, drop the violation counting, or
    let the pass swallow its own exception ⇒ an unlogged reorder layer ships,
    every off-policy estimate downstream is silently biased, and no one finds
    out until a model trained on it underperforms in production.
    """
    real_order = server._order_deck

    def rogue_order_deck(cards, **kwargs):
        # A perfectly ordinary-looking "boost the top partner" layer, applied
        # after the capture was taken. It reorders and it changes the key it
        # sorts on — it just never tells the capture.
        ordered = real_order(cards, **kwargs)
        cap = kwargs.get("capture")
        if cap and ordered:
            victim = ordered[-1]
            cap["final_key"][id(victim)] *= 1.3
            ordered = sorted(ordered, key=lambda c: cap["final_key"][id(c)],
                             reverse=True)
        return ordered

    cards = [_card(f"p{i}", f"p{i + 1}", 10.0 - i) for i in range(1, 6)]
    with _flags(_thompson_deck_enabled=True):
        _serve(cards, order_fn=rogue_order_deck)

    report = dc.check_drift(day=_today())
    assert report["sampled"] == len(cards)
    assert report["violations"] == 1, report
    assert report["violation_rate"] > dc.MAX_VIOLATION_RATE
    assert report["untrusted"] is True

    # …and through the pass body: ledger error + the untrusted marker.
    ctx = PassContext(now=datetime.now(timezone.utc) + timedelta(days=1),
                      run_date="x")
    with pytest.raises(RuntimeError, match="propensity drift"):
        dc.run(ctx)
    assert os.path.exists(dc.marker_path(_today()))


# ---------------------------------------------------------------------------
# The pass body
# ---------------------------------------------------------------------------

def test_clean_night_passes_and_writes_no_marker(mem_engine, marker_dir):
    """A trusted night must leave NO marker — the D4 promotion counter treats
    the file's existence as the poison signal.

    SABOTAGE: write the marker unconditionally (or on any violation at all)
    ⇒ every night reads as untrusted and promotion stalls forever.
    """
    cards = [_card(f"p{i}", f"p{i + 1}", 10.0 - i) for i in range(1, 6)]
    with _flags(_thompson_deck_enabled=True, _deck_fatigue_enabled=True):
        _serve(cards, fatigue={id(c): 0.7 for c in cards})

    ctx = PassContext(now=datetime.now(timezone.utc) + timedelta(days=1),
                      run_date="x")
    report = dc.run(ctx)
    assert report["violations"] == 0 and report["untrusted"] is False
    assert not os.path.exists(dc.marker_path(_today()))


def test_violations_under_the_bar_stay_trusted(mem_engine, marker_dir):
    """2% is a bar, not a hair trigger: one bad row in a hundred is noise
    (float paths, a mid-job deploy), not a broken contract.

    SABOTAGE: fail on `violations > 0` ⇒ the pass is red often enough that an
    operator learns to ignore it, which is worse than not having it.
    """
    cards = [_card(f"p{i}", f"p{i + 1}", 100.0 - i) for i in range(1, 11)]
    with _flags():
        _serve(cards)
    # Corrupt ONE row out of 100 by hand (10 served rows ⇒ 10%, so pad the
    # sample with 90 clean synthetic rows first).
    served = datetime.now(timezone.utc).isoformat()
    extra = [{
        "impression_id": f"synthetic-{i}", "user_id": ME, "league_id": LEAGUE,
        "deck_job_id": "job-pad", "card_index": i, "trade_hash": f"h{i}",
        "features_json": json.dumps({"feature_set": dc.FEATURE_SET}),
        "propensity": 1.0, "base_score": 5.0, "final_score": 5.0,
        "archetype": None, "shape_bucket": "1x1", "served_at": served,
    } for i in range(90)]
    db_module.save_deck_impressions(extra)
    with mem_engine.begin() as conn:
        t = deck_impressions_table
        first = conn.execute(select(t.c.impression_id)
                             .where(t.c.deck_job_id == JOB)
                             .order_by(t.c.card_index).limit(1)).scalar()
        conn.execute(t.update().where(t.c.impression_id == first)
                     .values(final_score=999.0))

    report = dc.check_drift(day=_today())
    assert report["sampled"] == 100
    assert report["violations"] == 1
    assert report["violation_rate"] == 0.01 <= dc.MAX_VIOLATION_RATE
    assert report["untrusted"] is False


def test_pre_fs2_rows_are_not_sampled(mem_engine, marker_dir):
    """Rows written before B8 carry no frozen multipliers. Checking them would
    flag the entire back catalogue.

    SABOTAGE: drop the `feature_set` predicate ⇒ the first night after deploy
    reports ~100% drift on rows that were never in scope.
    """
    served = datetime.now(timezone.utc).isoformat()
    db_module.save_deck_impressions([{
        "impression_id": "legacy-1", "user_id": ME, "league_id": LEAGUE,
        "deck_job_id": "job-legacy", "card_index": 0, "trade_hash": "h",
        "features_json": json.dumps({"shape": "1x1"}),   # no feature_set
        "propensity": 0.8, "base_score": 5.0, "final_score": 5.0,  # violates
        "archetype": None, "shape_bucket": "1x1", "served_at": served,
    }])
    report = dc.check_drift(day=_today())
    assert report["sampled"] == 0 and report["skipped_non_fs2"] == 1
    assert report["untrusted"] is False


def test_wildcard_rows_are_not_sampled(mem_engine, marker_dir):
    """F7 wildcards log the exploration DRAW PROBABILITY as `propensity`, not
    an ordering multiplier, and they are slotted in after ordering. The
    identity does not apply to them by construction.

    SABOTAGE: sample them ⇒ every exploration card is a false violation, and
    on a heavy-exploration day the pass marks a perfectly clean night
    untrusted, freezing D4 promotion.
    """
    served = datetime.now(timezone.utc).isoformat()
    db_module.save_deck_impressions([{
        "impression_id": "wild-1", "user_id": ME, "league_id": LEAGUE,
        "deck_job_id": "job-wild", "card_index": 0, "trade_hash": "h",
        "features_json": json.dumps({"feature_set": dc.FEATURE_SET,
                                     "wildcard": True,
                                     "wildcard_pool_size": 20}),
        "propensity": 0.005, "base_score": 5.0, "final_score": 5.0,
        "archetype": None, "shape_bucket": "1x1", "served_at": served,
    }])
    report = dc.check_drift(day=_today())
    assert report["sampled"] == 0 and report["skipped_wildcard"] == 1
    assert report["untrusted"] is False


def test_empty_night_is_ok(mem_engine, marker_dir):
    """No impressions is not a violation.

    SABOTAGE: divide by `sampled` without guarding zero ⇒ the pass raises
    ZeroDivisionError on any quiet night and the ledger reads `error`.
    """
    ctx = PassContext(now=datetime.now(timezone.utc) + timedelta(days=1),
                      run_date="x")
    report = dc.run(ctx)
    assert report["sampled"] == 0 and report["untrusted"] is False
    assert not os.path.exists(dc.marker_path(_today()))


def test_sample_is_capped(mem_engine, marker_dir):
    """≤200 rows per night (LLD §4.13) — this is an audit, not a full scan.

    SABOTAGE: drop the cap ⇒ the 60s budget pass starts reading every
    impression written that day.
    """
    served = datetime.now(timezone.utc).isoformat()
    db_module.save_deck_impressions([{
        "impression_id": f"bulk-{i:04d}", "user_id": ME, "league_id": LEAGUE,
        "deck_job_id": "job-bulk", "card_index": i, "trade_hash": f"h{i}",
        "features_json": json.dumps({"feature_set": dc.FEATURE_SET}),
        "propensity": 1.0, "base_score": 5.0, "final_score": 5.0,
        "archetype": None, "shape_bucket": "1x1", "served_at": served,
    } for i in range(500)])
    assert dc.check_drift(day=_today())["sampled"] == dc.DEFAULT_SAMPLE


def test_marker_contents_name_the_damage(mem_engine, marker_dir):
    """The marker is read months later by the D4 promotion counter and by a
    human asking "what happened that night?".

    SABOTAGE: write an empty sentinel file ⇒ the night is skippable but not
    diagnosable, and nobody can tell a 3% blip from a 100% breakage.
    """
    served = datetime.now(timezone.utc).isoformat()
    db_module.save_deck_impressions([{
        "impression_id": "bad-1", "user_id": ME, "league_id": LEAGUE,
        "deck_job_id": "job-bad", "card_index": 0, "trade_hash": "h",
        "features_json": json.dumps({"feature_set": dc.FEATURE_SET}),
        "propensity": 1.0, "base_score": 5.0, "final_score": 7.0,
        "archetype": None, "shape_bucket": "1x1", "served_at": served,
    }])
    ctx = PassContext(now=datetime.now(timezone.utc) + timedelta(days=1),
                      run_date="x")
    with pytest.raises(RuntimeError):
        dc.run(ctx)
    with open(dc.marker_path(_today())) as fh:
        payload = json.load(fh)
    assert payload["violations"] == 1 and payload["sampled"] == 1
    assert payload["examples"][0]["impression_id"] == "bad-1"


def test_registered_in_the_nightly_registry():
    """A pass that isn't registered never runs.

    SABOTAGE: drop the PassSpec ⇒ the drift check exists, is tested, and is
    dead code in production.
    """
    spec = next((s for s in server.DAILY_TICK_REGISTRY
                 if s.name == "drift_check"), None)
    assert spec is not None and spec.budget_s == 60.0
