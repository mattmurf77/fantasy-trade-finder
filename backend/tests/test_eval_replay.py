"""F8 — offline eval harness: replay/IPS evaluator.

Covers (PRD acceptance criteria):
  • Self-consistency: replaying the logged policy reproduces the observed
    like-rate — exactly under deterministic serving (p=1), within the
    bootstrap CI under Thompson noise.
  • A deliberately broken scorer (random order) grades measurably worse
    than the production baseline.
  • ESS + CI reported on every run; tiny samples labeled UNRELIABLE.
  • Exclusion accounting adds up (null propensity / never-viewed /
    undo-reversed / bad features / scorer error) — nothing silently dropped.
  • Time-ordered protocol: fit() sees only pre-split impressions; a
    fit-capable scorer without eval_start is refused.
  • Loader outcome reduction; CLI end-to-end (synth db → report + records);
    nightly run_all idempotency.

Harness: in-memory SQLite patched into backend.database (the
test_deck_signal_v2.py idiom) for loader/CLI paths; direct
LoggedDeck/LoggedCard construction for pure-estimator paths.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
from backend.database import deck_impressions_table, deck_outcomes_table, metadata

from backend.eval.data import LoggedCard, LoggedDeck, load_decks, split_decks
from backend.eval.replay import (
    EXCLUSION_REASONS,
    evaluate,
    self_check,
    render_report,
    verdict,
)
from backend.eval.scorers import get_scorer
from backend.eval.synth import build_synthetic_db
from backend.eval import nightly


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


_FEATURES_DEFAULT = object()   # sentinel: features=None must mean "unparseable"


def _card(job, pos, *, viewed=True, liked=False, proposed=False, undone=False,
          propensity=1.0, base=None, final=None, features=_FEATURES_DEFAULT,
          served_at=None) -> LoggedCard:
    base = base if base is not None else (10.0 - pos)
    return LoggedCard(
        impression_id=f"{job}_c{pos}", deck_job_id=job, user_id="u1",
        league_id="lg", card_index=pos, trade_hash=None,
        propensity=propensity, base_score=base,
        final_score=(final if final is not None else base),
        archetype=None, shape_bucket="1x1",
        served_at=served_at or _iso(1),
        features=({"shape": "1x1"} if features is _FEATURES_DEFAULT else features),
        viewed=viewed, liked=liked, proposed=proposed, undone=undone,
    )


def _deck(job, cards, served_at=None) -> LoggedDeck:
    served = served_at or (cards[0].served_at if cards else _iso(1))
    return LoggedDeck(deck_job_id=job, user_id="u1", league_id="lg",
                      served_at=served, cards=cards)


def _uniform_decks(n_decks=12, n_cards=8, likes_top=2, viewed_upto=6,
                   propensity=1.0):
    """Likes concentrated at the top of a position-decaying view window —
    the shape a healthy log has."""
    decks = []
    for d in range(n_decks):
        served = _iso(10 - d * 0.5)
        cards = [
            _card(f"j{d}", p, viewed=(p < viewed_upto), liked=(p < likes_top),
                  propensity=propensity, served_at=served)
            for p in range(n_cards)
        ]
        decks.append(_deck(f"j{d}", cards, served_at=served))
    return decks


# ---------------------------------------------------------------------------
# Self-consistency
# ---------------------------------------------------------------------------

def test_self_check_exact_under_deterministic_serving():
    decks = _uniform_decks(propensity=1.0)
    ok, run = self_check(decks, ess_min=10, bootstrap=400, seed=3)
    assert ok
    m = run.metrics["like"]
    # p=1 everywhere + identical ranks ⇒ every weight is exactly 1 ⇒ SNIPS
    # (and IPS) collapse to the observed rate.
    assert m.snips == pytest.approx(m.observed)
    assert m.ips == pytest.approx(m.observed)
    assert m.ci_low <= m.observed <= m.ci_high
    assert m.ess == pytest.approx(m.n)


def test_self_check_within_ci_under_thompson_noise(tmp_path):
    db = tmp_path / "noise.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=50, seed=11,
                       thompson_noise=True)
    decks = load_decks(db_url=f"sqlite:///{db}")
    ok, run = self_check(decks, ess_min=50, bootstrap=500, seed=1)
    assert ok, (
        f"self-check failed: observed={run.metrics['like'].observed} "
        f"ci=[{run.metrics['like'].ci_low}, {run.metrics['like'].ci_high}]")


# ---------------------------------------------------------------------------
# Random must grade worse than production
# ---------------------------------------------------------------------------

def test_random_scorer_grades_worse_than_production(tmp_path):
    db = tmp_path / "grade.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=80, seed=5,
                       thompson_noise=False)
    decks = load_decks(db_url=f"sqlite:///{db}")
    production = evaluate(get_scorer("production"), decks,
                          ess_min=50, bootstrap=300, seed=2)
    rand = evaluate(get_scorer("random", seed=9), decks,
                    ess_min=50, bootstrap=300, seed=2)
    p_like = production.metrics["like"]
    r_like = rand.metrics["like"]
    assert p_like.snips is not None and r_like.snips is not None
    # Measurably worse: likes live at the top of a decaying view curve, so a
    # random shuffle sheds counterfactual exposure on exactly the liked cards.
    assert r_like.snips < p_like.snips - 0.01
    assert verdict(rand, production, "like") in ("LOSS", "FLAT")
    # ESS/CI must be reported on every run.
    for m in (p_like, r_like):
        assert m.ess > 0 and m.ci_low is not None and m.ci_high is not None


# ---------------------------------------------------------------------------
# ESS gate
# ---------------------------------------------------------------------------

def test_tiny_sample_labeled_unreliable():
    decks = _uniform_decks(n_decks=2)
    baseline = evaluate(get_scorer("production"), decks,
                        ess_min=100, bootstrap=100, seed=0)
    assert baseline.unreliable
    assert verdict(baseline, baseline, "like") == "UNRELIABLE"
    # The numbers are still reported — the label refuses, nothing is hidden.
    assert baseline.metrics["like"].snips is not None
    assert baseline.metrics["like"].ess < 100


def test_ess_gate_respects_threshold():
    decks = _uniform_decks(n_decks=12)   # 72 viewed impressions
    run = evaluate(get_scorer("production"), decks, ess_min=10,
                   bootstrap=50, seed=0)
    assert not run.unreliable
    run2 = evaluate(get_scorer("production"), decks, ess_min=1000,
                    bootstrap=50, seed=0)
    assert run2.unreliable


# ---------------------------------------------------------------------------
# Exclusion accounting
# ---------------------------------------------------------------------------

def test_exclusion_accounting_adds_up():
    served = _iso(2)
    cards = [
        _card("jx", 0, viewed=True, liked=True, served_at=served),
        _card("jx", 1, viewed=True, propensity=0.0, served_at=served),      # null_propensity
        _card("jx", 2, viewed=False, served_at=served),                     # never_viewed
        _card("jx", 3, viewed=True, undone=True, served_at=served),         # undo_reversed
        _card("jx", 4, viewed=True, features=None, served_at=served),       # bad_features
        _card("jx", 5, viewed=True, served_at=served),
    ]
    decks = [_deck("jx", cards, served_at=served)] + _uniform_decks(n_decks=3)
    run = evaluate(get_scorer("production"), decks, ess_min=1,
                   bootstrap=0, seed=0)
    assert run.excluded["null_propensity"] == 1
    assert run.excluded["never_viewed"] == 1 + 3 * 2   # +2 unviewed per uniform deck
    assert run.excluded["undo_reversed"] == 1
    assert run.excluded["bad_features"] == 1
    assert run.excluded["scorer_error"] == 0
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert set(run.excluded) == set(EXCLUSION_REASONS)


def test_scorer_error_excludes_whole_deck():
    class Exploder:
        name = "exploder"
        def score(self, card):
            raise RuntimeError("boom")
    decks = _uniform_decks(n_decks=4)
    run = evaluate(Exploder(), decks, ess_min=1, bootstrap=0, seed=0)
    assert run.n_included == 0
    assert run.excluded["scorer_error"] == run.n_total
    assert run.n_total == sum(run.excluded.values())


# ---------------------------------------------------------------------------
# Time-ordered protocol
# ---------------------------------------------------------------------------

class FitRecorder:
    name = "fit_recorder"
    def __init__(self):
        self.fit_rows = None
    def fit(self, rows):
        self.fit_rows = rows
    def score(self, card):
        return float(card.get("base_score") or 0.0)


def test_fit_sees_only_pre_split_and_eval_only_post_split():
    old = _uniform_decks(n_decks=4)
    for i, d in enumerate(old):
        d.served_at = f"2026-07-0{i + 1}T00:00:00+00:00"
        for c in d.cards:
            c.served_at = d.served_at
    new = _uniform_decks(n_decks=3)
    for i, d in enumerate(new):
        d.deck_job_id = f"new{i}"
        d.served_at = f"2026-07-2{i}T00:00:00+00:00"
        for c in d.cards:
            c.served_at = d.served_at
    split = "2026-07-10"
    scorer = FitRecorder()
    run = evaluate(scorer, old + new, eval_start=split, ess_min=1,
                   bootstrap=0, seed=0)
    # fit() got exactly the pre-split impressions
    assert scorer.fit_rows is not None
    assert len(scorer.fit_rows) == sum(len(d.cards) for d in old)
    assert all(r["card"]["served_at"] < split for r in scorer.fit_rows)
    # evaluation window is strictly post-split
    assert run.n_total == sum(len(d.cards) for d in new)
    assert run.eval_start == split


def test_fit_capable_scorer_refused_without_eval_start():
    with pytest.raises(ValueError, match="eval-start|eval_start"):
        evaluate(FitRecorder(), _uniform_decks(n_decks=2))


def test_split_decks_requires_eval_start():
    with pytest.raises(ValueError):
        split_decks(_uniform_decks(n_decks=2), "")


# ---------------------------------------------------------------------------
# Loader — outcome reduction on the F1 tables
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def test_load_decks_reduces_outcomes(mem_engine):
    served = _iso(1)
    with mem_engine.begin() as conn:
        for pos, imp in enumerate(("i0", "i1", "i2")):
            conn.execute(insert(deck_impressions_table).values(
                impression_id=imp, user_id="u1", league_id="lg",
                deck_job_id="j1", card_index=pos,
                features_json=json.dumps({"shape": "1x1"}),
                propensity=1.0, base_score=2.0, final_score=2.0,
                shape_bucket="1x1", served_at=served,
            ))
        for imp, action, dwell in (
            ("i0", "viewed", 500), ("i0", "like", 4000),
            ("i1", "viewed", 600), ("i1", "pass", 900), ("i1", "undo", None),
        ):
            conn.execute(insert(deck_outcomes_table).values(
                impression_id=imp, action=action, dwell_ms=dwell,
                acted_at=served))
    decks = load_decks(engine=mem_engine)
    assert len(decks) == 1
    c0, c1, c2 = decks[0].cards
    assert c0.viewed and c0.liked and not c0.undone and c0.dwell_ms == 4000
    assert c1.viewed and c1.passed and c1.undone
    assert not c2.viewed and not c2.liked and c2.dwell_ms is None


def test_load_decks_time_and_scope_filters(mem_engine):
    with mem_engine.begin() as conn:
        for job, user, served in (("ja", "u1", "2026-07-01T00:00:00+00:00"),
                                  ("jb", "u1", "2026-07-20T00:00:00+00:00"),
                                  ("jc", "u2", "2026-07-21T00:00:00+00:00")):
            conn.execute(insert(deck_impressions_table).values(
                impression_id=f"{job}_i", user_id=user, league_id="lg",
                deck_job_id=job, card_index=0, features_json="{}",
                propensity=1.0, shape_bucket="1x1", served_at=served))
    assert [d.deck_job_id for d in
            load_decks(engine=mem_engine, since="2026-07-10")] == ["jb", "jc"]
    assert [d.deck_job_id for d in
            load_decks(engine=mem_engine, user_id="u1")] == ["ja", "jb"]


# ---------------------------------------------------------------------------
# CLI end-to-end + persistence + nightly
# ---------------------------------------------------------------------------

def test_cli_end_to_end(tmp_path, capsys, monkeypatch):
    from backend.eval.replay import main
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "runs"))
    db = tmp_path / "cli.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=40, seed=13)

    assert main(["--db", str(db), "--self-check", "--ess-min", "50",
                 "--bootstrap", "300"]) == 0
    out = capsys.readouterr().out
    assert "SELF-CHECK PASS" in out

    assert main(["--db", str(db), "--scorer", "base_score",
                 "--scorer", "random", "--ess-min", "50",
                 "--bootstrap", "200"]) == 0
    out = capsys.readouterr().out
    assert "| scorer | metric |" in out          # markdown report table
    assert "Exclusion accounting" in out
    assert "runs.jsonl" in out

    from backend.eval.persistence import load_runs
    records = load_runs()
    assert {r["scorer"] for r in records} == {"production", "base_score", "random"}
    for r in records:
        assert r["n_total"] == r["n_included"] + sum(r["excluded"].values())
        assert "like" in r["metrics"] and "verdict" in r["metrics"]["like"]


def test_nightly_run_all_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "runs"))
    db = tmp_path / "nightly.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=30, seed=17, days_span=10)

    first = nightly.run_all(window_days=30, db_url=f"sqlite:///{db}",
                            ess_min=50, bootstrap=100, seed=1)
    assert first["ran"] >= 2          # base_score + random at minimum
    assert first["errors"] == 0
    assert "| scorer | metric |" in first["report"]

    second = nightly.run_all(window_days=30, db_url=f"sqlite:///{db}",
                             ess_min=50, bootstrap=100, seed=1)
    assert second["ran"] == 0
    assert second["skipped"] == first["ran"]


def test_render_report_flags_accounting_and_ess(capsys):
    decks = _uniform_decks(n_decks=3)
    run = evaluate(get_scorer("production"), decks, ess_min=100,
                   bootstrap=50, seed=0)
    text = render_report([run], run)
    assert "UNRELIABLE" in text
    assert "tilt_clipped" in text
    assert "ESS gate: 100" in text
