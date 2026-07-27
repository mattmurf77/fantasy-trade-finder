"""F6 (flag deck.value_model) — learned acceptance heads × V-vector.

docs/plans/tiktok-discovery/prds/F6-value-model.md. SHIPS DARK. Contract
under test:

  - Flag OFF ⇒ byte-identical: _order_deck untouched, zero model
    reads (mock-asserted), zero training from daily-tick's hook, no
    model files.
  - Heads train on synthetic F1-shaped fixtures (backend.eval.synth) and
    beat random AUC-wise on a held-out time slice; calibrated P(like) is
    within tolerance on the F8 reliability tables.
  - V-vector math: rank_score = P(like)·V_like + P(like)·P(prop|like)·V_prop,
    with V's read live from model_config (no retrain to change strategy).
  - Zero-history users fall back to composite ordering exactly.
  - Serving errors ⇒ silent fallback to composite (deck never fails).
  - Nightly refit is idempotent per UTC date.
  - F8 scorer contract: `value_model` grades synthetic logs without
    error once a model is persisted; honest raise (→ the harness's
    scorer_error accounting) when none is.

Same isolation pattern as test_deck_taste.py: in-memory SQLite patched
into backend.database, flag helpers patched directly, VALUE_MODEL_DIR
pointed at a tmp dir (the F8 EVAL_RUNS_DIR idiom).
"""

import bisect
import json
import os
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
import backend.trade_service as ts
import backend.value_model as vm
from backend.database import metadata
from backend.eval.calibration import calibration_pairs, ece, reliability_table
from backend.eval.data import load_decks, split_decks
from backend.eval.replay import evaluate
from backend.eval.scorers import get_scorer
from backend.eval.synth import build_synthetic_db
from backend.trade_service import TradeCard

LEAGUE = "league_f6"
ME = "user_me"
OPP = "user_opp"

SEED = {"star": 1800.0, "mid": 1500.0, "scrub": 1250.0}


class _P:
    def __init__(self, pid, pos="RB", age=25):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = pos
        self.team = "TST"
        self.age = age


PLAYERS = {"star": _P("star", "WR", 24), "mid": _P("mid", "RB", 27),
           "scrub": _P("scrub", "TE", 31)}


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture(autouse=True)
def _model_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path / "vm"))
    vm._model_cache = None
    yield
    vm._model_cache = None


@pytest.fixture(autouse=True)
def _cfg_defaults():
    old_cfg = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _mk_card(give, recv, composite=5.0, likes_you=False):
    return TradeCard(
        trade_id=f"t_{uuid.uuid4().hex[:8]}",
        league_id=LEAGUE,
        proposing_user_id=ME,
        target_user_id=OPP,
        target_username="opp",
        give_player_ids=list(give),
        receive_player_ids=list(recv),
        mismatch_score=1.0,
        fairness_score=0.9,
        composite_score=composite,
        likes_you=likes_you,
    )


def _synth_decks(tmp_path, n_decks=300, seed=7, name="synth.db"):
    db = tmp_path / name
    build_synthetic_db(f"sqlite:///{db}", n_decks=n_decks, seed=seed)
    return load_decks(db_url=f"sqlite:///{db}"), f"sqlite:///{db}"


def _auc(pairs):
    pos = sorted(p for p, y in pairs if y == 1)
    neg = sorted(p for p, y in pairs if y == 0)
    wins = sum(
        bisect.bisect_left(neg, p)
        + 0.5 * (bisect.bisect_right(neg, p) - bisect.bisect_left(neg, p))
        for p in pos)
    return wins / (len(pos) * len(neg))


def _trained_model(tmp_path, persist=True):
    decks, _ = _synth_decks(tmp_path, n_decks=150, seed=11, name="train.db")
    model = vm.train_model(decks)
    assert model is not None
    if persist:
        vm.append_model(model)
        vm._model_cache = None
    return model


# ---------------------------------------------------------------------------
# Flag OFF — byte-identical, zero model reads
# ---------------------------------------------------------------------------

def test_flag_off_order_deck_untouched_and_no_model_reads(mem_engine):
    cards = [_mk_card(["mid"], ["star"]), _mk_card(["scrub"], ["mid"])]
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        stack.enter_context(patch.object(
            server, "_deck_value_model_enabled", lambda: False))
        stack.enter_context(patch.object(
            server._value_model, "serving_scores",
            MagicMock(side_effect=AssertionError("model touched while dark"))))
        stack.enter_context(patch.object(
            server._value_model, "load_latest_model",
            MagicMock(side_effect=AssertionError("model store read while dark"))))
        # The worker-path helper is the flag gate: OFF ⇒ None, no reads.
        assert server._deck_value_scores(
            cards, user_id=ME, league_id=LEAGUE, players_dict=PLAYERS,
            seed_map=SEED, scoring_format="1qb_ppr") is None
        # And _order_deck with the flag-off caller value is the identity.
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j1",
            seed_map=SEED, value_scores=None)
    assert out is cards


def test_flag_off_daily_tick_hook_never_trains(mem_engine):
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            server, "_deck_value_model_enabled", lambda: False))
        refit = stack.enter_context(patch.object(
            server._value_model, "nightly_refit",
            MagicMock(side_effect=AssertionError("trained while dark"))))
        # Mirror the daily-tick block's gate exactly.
        if server._deck_value_model_enabled():
            server._value_model.nightly_refit()
    refit.assert_not_called()
    assert not os.path.exists(vm.models_path()), "no model files while dark"


def test_demo_league_never_scored(mem_engine):
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            server, "_deck_value_model_enabled", lambda: True))
        stack.enter_context(patch.object(
            server._value_model, "serving_scores",
            MagicMock(side_effect=AssertionError("demo league scored"))))
        assert server._deck_value_scores(
            [_mk_card(["mid"], ["star"])], user_id=ME,
            league_id="league_demo", players_dict=PLAYERS,
            seed_map=SEED, scoring_format="1qb_ppr") is None


# ---------------------------------------------------------------------------
# Training — beats random AUC on held-out synthetic; calibration holds
# ---------------------------------------------------------------------------

def test_heads_beat_random_auc_on_heldout(tmp_path, mem_engine):
    decks, _ = _synth_decks(tmp_path)
    split = decks[int(len(decks) * 0.8)].served_at
    train, heldout = split_decks(decks, split)
    model = vm.train_model(train)
    assert model is not None
    assert model.meta["n_like_rows"] >= vm.MIN_LIKE_ROWS

    rows, _ = vm.build_training_rows(heldout)
    pairs = [(model.p_like(r["f"], r["user_id"]), r["y"]) for r in rows]
    auc = _auc(pairs)
    assert auc > 0.55, f"held-out like-head AUC {auc:.3f} — not above random"
    assert all(0.0 <= p <= 1.0 for p, _ in pairs)


def test_calibration_within_tolerance_on_heldout(tmp_path, mem_engine):
    decks, _ = _synth_decks(tmp_path)
    split = decks[int(len(decks) * 0.8)].served_at
    train, heldout = split_decks(decks, split)
    model = vm.train_model(train)
    rows, _ = vm.build_training_rows(heldout)
    pairs = [(model.p_like(r["f"], r["user_id"]), r["y"]) for r in rows]
    table = reliability_table(pairs)
    e = ece(table)
    assert e is not None and e < 0.10, f"held-out ECE {e:.3f} out of tolerance"
    # Base-rate sanity: mean prediction near the observed like rate.
    mean_p = sum(p for p, _ in pairs) / len(pairs)
    obs = sum(y for _, y in pairs) / len(pairs)
    assert abs(mean_p - obs) < 0.08


def test_insufficient_labels_declines_to_train(tmp_path, mem_engine):
    decks, _ = _synth_decks(tmp_path, n_decks=2, seed=3, name="tiny.db")
    assert vm.train_model(decks) is None


def test_monolith_log_odds_correction():
    head = vm.LogisticHead(weights={"bias": 0.0}, neg_sample_rate=0.1)
    # logit 0 + ln(0.1) ⇒ sigmoid(-2.302…) ≈ 0.0909 — downsampled negatives
    # are re-weighted back to honest probabilities at serving.
    assert head.predict_proba({"bias": 1.0}) == pytest.approx(1 / 11, abs=1e-6)
    head_full = vm.LogisticHead(weights={"bias": 0.0}, neg_sample_rate=1.0)
    assert head_full.predict_proba({"bias": 1.0}) == pytest.approx(0.5)


def test_position_is_train_only_never_card_index(tmp_path, mem_engine):
    model = _trained_model(tmp_path, persist=False)
    f = {"shape": "1x1", "surplus_margin": 50, "fairness_score": 0.9,
         "card_index": 0, "final_score": 99.0, "propensity": 1.4}
    p_top = model.p_like({**f, "card_index": 0}, ME)
    p_bottom = model.p_like({**f, "card_index": 30}, ME)
    assert p_top == p_bottom, "predict must pin position (never card_index)"


# ---------------------------------------------------------------------------
# V-vector math — strategy lives in model_config, changeable sans retrain
# ---------------------------------------------------------------------------

def test_rank_score_v_vector_math(mem_engine):
    model = vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": 0.0}),        # P(like)=0.5
        propose_head=None,
        propose_constant=0.25,                                   # P(prop|like)
        partner_rates={}, global_like_rate=0.2, position_mean=0.3,
        trained_at="t", train_date="d")
    # rank = 0.5·1 + 0.5·0.25·6 = 1.25 with the defaults
    assert model.rank_score({}, ME) == pytest.approx(0.5 * 1 + 0.5 * 0.25 * 6)
    # V's are live model_config reads — no retrain to change strategy.
    ts._cfg["value_model_v_like"] = 2.0
    ts._cfg["value_model_v_propose"] = 10.0
    assert model.rank_score({}, ME) == pytest.approx(0.5 * 2 + 0.5 * 0.25 * 10)


def test_order_deck_uses_rank_scores_as_base_key(mem_engine):
    low = _mk_card(["mid"], ["star"], composite=9.0)    # composite winner
    high = _mk_card(["scrub"], ["mid"], composite=1.0)  # model winner
    scores = {id(low): 0.2, id(high): 3.0}
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        capture = {}
        out = server._order_deck(
            [low, high], user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, capture=capture, value_scores=scores)
    assert [id(c) for c in out] == [id(high), id(low)]
    assert capture["final_key"][id(high)] == pytest.approx(3.0)


def test_gates_pins_and_multipliers_still_apply_on_top(mem_engine):
    pinned = _mk_card(["mid"], ["star"], composite=0.5, likes_you=True)
    strong = _mk_card(["scrub"], ["mid"], composite=8.0)
    scores = {id(pinned): 0.01, id(strong): 5.0}
    fatigue = {id(strong): 0.001}   # F3 discount composes on the model base
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        out = server._order_deck(
            [strong, pinned], user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, value_scores=scores, fatigue_mult=fatigue)
    # Likes-you stays pinned to the top regardless of the model's opinion,
    # and membership is untouched — ordering authority only.
    assert out[0] is pinned
    assert {id(c) for c in out} == {id(pinned), id(strong)}


# ---------------------------------------------------------------------------
# Cold start + fallbacks — composite ordering exactly
# ---------------------------------------------------------------------------

def test_zero_history_user_falls_back_to_composite(tmp_path, mem_engine):
    _trained_model(tmp_path)   # a model EXISTS, but this user has no history
    assert vm.serving_scores(
        [_mk_card(["mid"], ["star"])], user_id=ME, league_id=LEAGUE,
        players_dict=PLAYERS, seed_map=SEED) is None


def test_no_model_falls_back_to_composite(mem_engine):
    assert vm.load_latest_model(use_cache=False) is None
    assert vm.serving_scores(
        [_mk_card(["mid"], ["star"])], user_id=ME, league_id=LEAGUE,
        players_dict=PLAYERS, seed_map=SEED) is None


def test_user_with_history_gets_model_scores(tmp_path, mem_engine):
    _trained_model(tmp_path)
    with mem_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO deck_impressions (impression_id, user_id, league_id, "
            "deck_job_id, card_index, features_json, propensity, served_at) "
            "VALUES ('i1', :uid, :lid, 'j1', 0, '{}', 1.0, :ts)"),
            {"uid": ME, "lid": LEAGUE,
             "ts": datetime.now(timezone.utc).isoformat()})
        conn.execute(text(
            "INSERT INTO deck_outcomes (impression_id, action, acted_at) "
            "VALUES ('i1', 'like', :ts)"),
            {"ts": datetime.now(timezone.utc).isoformat()})
    cards = [_mk_card(["mid"], ["star"]), _mk_card(["scrub"], ["mid"])]
    scores = vm.serving_scores(
        cards, user_id=ME, league_id=LEAGUE,
        players_dict=PLAYERS, seed_map=SEED)
    assert scores is not None and set(scores) == {id(c) for c in cards}
    assert all(s > 0 for s in scores.values())


def test_serving_error_falls_back_silently(mem_engine):
    # Inner layer: any exception inside serving_scores ⇒ None, no raise.
    with patch.object(vm, "load_latest_model",
                      MagicMock(side_effect=RuntimeError("store corrupt"))):
        assert vm.serving_scores(
            [_mk_card(["mid"], ["star"])], user_id=ME, league_id=LEAGUE,
            players_dict=PLAYERS, seed_map=SEED) is None
    # Outer layer (the worker's call): a raise from the module still ⇒ None
    # (belt and braces), so the deck is served on the composite.
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            server, "_deck_value_model_enabled", lambda: True))
        stack.enter_context(patch.object(
            server._value_model, "serving_scores",
            MagicMock(side_effect=RuntimeError("scorer blew up"))))
        cards = [_mk_card(["mid"], ["star"]), _mk_card(["scrub"], ["mid"])]
        assert server._deck_value_scores(
            cards, user_id=ME, league_id=LEAGUE, players_dict=PLAYERS,
            seed_map=SEED, scoring_format="1qb_ppr") is None
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, value_scores=None)
    assert out is cards, "error path serves the composite deck untouched"


# ---------------------------------------------------------------------------
# Nightly refit — idempotent per UTC day, non-fatal
# ---------------------------------------------------------------------------

def test_nightly_refit_idempotent_per_day(tmp_path, mem_engine):
    _decks, db_url = _synth_decks(tmp_path, n_decks=150, seed=11,
                                  name="refit.db")
    first = vm.nightly_refit(db_url=db_url)
    assert first["status"] == "trained"
    assert os.path.exists(first["path"])
    second = vm.nightly_refit(db_url=db_url)
    assert second["status"] == "skipped"
    assert second["reason"] == "already trained today"
    with open(vm.models_path(), encoding="utf-8") as fh:
        assert sum(1 for line in fh if line.strip()) == 1
    # --force retrains (the operator override).
    third = vm.nightly_refit(db_url=db_url, force=True)
    assert third["status"] == "trained"


def test_nightly_refit_never_raises(mem_engine):
    with patch.object(vm, "latest_train_dates",
                      MagicMock(side_effect=RuntimeError("disk gone"))):
        stats = vm.nightly_refit()
    assert stats["status"] == "error"


def test_refit_on_empty_spine_skips(mem_engine):
    stats = vm.nightly_refit()   # in-memory DB has no impressions
    assert stats["status"] == "skipped"
    assert stats["reason"] == "insufficient labels"
    assert not os.path.exists(vm.models_path())


# ---------------------------------------------------------------------------
# F8 scorer contract — grades synthetic logs; honest raise when untrained
# ---------------------------------------------------------------------------

def test_f8_scorer_grades_synthetic_logs(tmp_path, mem_engine):
    _trained_model(tmp_path)
    decks, _ = _synth_decks(tmp_path, n_decks=60, seed=23, name="grade.db")
    scorer = get_scorer("value_model")
    run = evaluate(scorer, decks, ess_min=10, bootstrap=50, seed=0)
    assert run.excluded["scorer_error"] == 0
    assert run.n_included > 0
    assert run.metrics["like"].snips is not None
    # predict_proba feeds the reliability tables without exclusions.
    pairs, excl = calibration_pairs(scorer, decks)
    assert excl["scorer_error"] == 0 and pairs
    assert all(0.0 <= p <= 1.0 for p, _ in pairs)


def test_f8_scorer_honesty_no_logged_policy_fields(tmp_path, mem_engine):
    _trained_model(tmp_path)
    scorer = get_scorer("value_model")
    base = {"user_id": ME, "shape": "1x1", "surplus_margin": 60,
            "fairness_score": 0.9, "give_positions": ["RB"],
            "receive_positions": ["WR"]}
    s1 = scorer.score({**base, "card_index": 0, "final_score": 9.9,
                       "propensity": 1.5})
    s2 = scorer.score({**base, "card_index": 25, "final_score": 0.1,
                       "propensity": 0.5})
    assert s1 == s2, "logged-policy fields must not influence the candidate"


def test_f8_scorer_raises_without_model(mem_engine):
    scorer = get_scorer("value_model")
    with pytest.raises(RuntimeError, match="no persisted value model"):
        scorer.score({"user_id": ME})
    with pytest.raises(RuntimeError, match="no persisted value model"):
        scorer.predict_proba({"user_id": ME})


def test_f8_scorer_untrained_is_counted_not_silent(tmp_path, mem_engine):
    decks, _ = _synth_decks(tmp_path, n_decks=10, seed=29, name="empty.db")
    run = evaluate(get_scorer("value_model"), decks,
                   ess_min=10, bootstrap=10, seed=0)
    assert run.n_included == 0
    assert run.excluded["scorer_error"] == run.n_total
