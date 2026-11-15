"""Fairness window (flag trade.fairness_window_v2) — docs/plans/fairness-window/spec.md.

Pins:
  * registration: default False in code, false in config and the three fixtures;
  * one source of truth: FAIR_DEFAULT is 0.75 and every signature default is it;
  * flag OFF: the default is 0.75 without reading model_config, the flags payload has
    no new key, and /api/trades/generate builds the same deck as an explicit 0.75;
  * flag ON: the knob (0.55-0.75, anything else 0.75) is the default and is served;
    explicit and pinned thresholds are untouched;
  * cache keys: a deck built at one threshold can never answer the other;
  * the replay tool (backend/eval/fairness_window_replay.py) on a synthetic fixture,
    and its pre-registered decision rule.
"""
import inspect
import json
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import insert

from backend import database as db, fairness_window as fw, feature_flags as ff, server, trade_service as ts
from backend import prepared_trade_runtime as prt
from backend.eval import fairness_window_replay as replay
from backend.tests.test_min_version_gate import client, mem_engine  # noqa: F401 — fixtures
from backend.tests.test_owner_generator_routes import (  # noqa: F401 — fixtures
    harness, owner_harness, worker, LEAGUE, TOKEN)

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def flag():
    saved = ff._flags_cache

    def _set(on: bool):
        ff._flags_cache = {**(saved or ff.flags_dict()), fw.FLAG: on}
    yield _set
    ff._flags_cache = saved


def _knob(engine, value):
    with engine.begin() as conn:
        conn.execute(insert(db.model_config_table).values(key=fw.KNOB, value=value, description="test"))


# ── registration and the one constant ──────────────────────────────────────

def test_flag_registered_default_off_everywhere():
    assert ff.DEFAULT_FLAGS[fw.FLAG] is False
    assert json.loads((REPO / "config/features.json").read_text())[fw.FLAG] is False
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[fw.FLAG] is False, name
    assert next(v for k, v, _ in db._MODEL_CONFIG_DEFAULTS if k == fw.KNOB) == 0.75


def test_every_signature_default_is_the_single_constant():
    assert fw.FAIR_DEFAULT == 0.75
    for fn in (ts.TradeService._generate_trades_impl, ts.TradeService._generate_for_pair,
               server._kickoff_trade_job):
        assert inspect.signature(fn).parameters["fairness_threshold"].default == 0.75, fn


@pytest.mark.parametrize("raw,served", [
    (0.75, 0.75), (0.70, 0.70), (0.65, 0.65), (0.60, 0.60), (0.55, 0.55),
    (0.5, 0.75), (0.549, 0.75), (0.76, 0.75), (1.0, 0.75), (float("nan"), 0.75),
    (float("inf"), 0.75), ("x", 0.75), (None, 0.75), (True, 0.75)])
def test_knob_validation(raw, served):
    assert fw.configured_fair_threshold({fw.KNOB: raw}) == served
    assert fw.configured_fair_threshold({}) == 0.75


def test_flag_off_never_reads_config(flag):
    flag(False)
    with patch.object(db, "get_config", side_effect=AssertionError("read while off")):
        assert fw.default_fair_threshold() == 0.75
        assert fw.payload_fields() == {}


def test_flag_on_config_read_error_serves_default(flag):
    flag(True)
    with patch.object(db, "get_config", side_effect=RuntimeError("db down")):
        assert fw.default_fair_threshold() == 0.75


# ── GET /api/feature-flags ──────────────────────────────────────────────────

def test_flags_payload_off_has_no_key(client, mem_engine, flag):  # noqa: F811
    flag(False)
    _knob(mem_engine, 0.65)
    assert "fairness_on_threshold" not in client.get("/api/feature-flags").get_json()


@pytest.mark.parametrize("knob,served", [(None, 0.75), (0.65, 0.65), (0.4, 0.75)])
def test_flags_payload_on_serves_the_knob(client, mem_engine, flag, knob, served):  # noqa: F811
    flag(True)
    if knob is not None:
        _knob(mem_engine, knob)
    assert client.get("/api/feature-flags").get_json()["fairness_on_threshold"] == served


# ── /api/trades/generate: the resolved threshold and the deck ──────────────

def _queued_threshold(client, monkeypatch, **body):
    """POST /generate without running the worker; return the job's threshold."""
    monkeypatch.setattr(server.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None))
    resp = client.post("/api/trades/generate", json={"league_id": LEAGUE, **body},
                       headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200, resp.json
    job = server._trade_jobs.pop(resp.json["job_id"])
    for k, v in list(server._trade_jobs_by_key.items()):
        if v == job["job_id"]:
            server._trade_jobs_by_key.pop(k)
    return job["fairness_threshold"]


@pytest.mark.parametrize("on,knob,body,expected", [
    (False, None, {}, 0.75),
    (False, 0.65, {}, 0.75),                                   # off: knob ignored
    (True, None, {}, 0.75),
    (True, 0.65, {}, 0.65),
    (True, 0.65, {"fairness_threshold": 0.8}, 0.8),            # explicit untouched
    (True, 0.65, {"fairness_threshold": 0.5}, 0.5),
    (False, None, {"fairness_threshold": 0.75}, 0.75),
])
def test_generate_resolves_the_default(owner_harness, monkeypatch, flag, on, knob, body, expected):  # noqa: F811
    client, engine, *_ = owner_harness
    flag(on)
    if knob is not None:
        _knob(engine, knob)
    assert _queued_threshold(client, monkeypatch, **body) == expected


def test_generate_pinned_default_stays_050(owner_harness, monkeypatch, flag):  # noqa: F811
    client, engine, *_ = owner_harness
    flag(True)
    _knob(engine, 0.65)
    assert _queued_threshold(client, monkeypatch, pinned_give_players=["a1"]) == 0.5


def _deck(job):
    return [(c.get("target_user_id"), tuple(c.get("give_player_ids") or ()),
             tuple(c.get("receive_player_ids") or ()), c.get("fairness_score")) for c in job["cards"]]


def _run_at(owner_harness, monkeypatch, threshold):  # noqa: F811
    orig = server._run_trade_job

    def at(job_id, token, league_id, _fair, *a, **k):
        return orig(job_id, token, league_id, threshold, *a, **k)
    monkeypatch.setattr(server, "_run_trade_job", at)
    job = worker(owner_harness, monkeypatch)
    monkeypatch.setattr(server, "_run_trade_job", orig)
    return _deck(job)


def test_flag_off_deck_is_byte_identical_to_explicit_075(owner_harness, monkeypatch, flag):  # noqa: F811
    client, engine, *_ = owner_harness
    flag(False)
    _knob(engine, 0.55)
    resolved = _queued_threshold(client, monkeypatch)
    assert resolved == 0.75
    random.seed(1)
    via_default = _run_at(owner_harness, monkeypatch, resolved)
    random.seed(1)
    explicit = _run_at(owner_harness, monkeypatch, 0.75)
    assert via_default and via_default == explicit


# ── cache keys ──────────────────────────────────────────────────────────────

def test_cache_keys_separate_thresholds():
    assert server._trade_page_scope(0.75) != server._trade_page_scope(0.65)
    assert server._trade_page_scope(0.65) == "organic:f=0.65"
    a = prt.scope_for("u", "l", "lu", "1qb_ppr", 0.75)
    b = prt.scope_for("u", "l", "lu", "1qb_ppr", 0.65)
    assert a != b and a == prt.scope_for("u", "l", "lu", "1qb_ppr", 0.75)


def test_fresh_job_at_075_cannot_answer_065(monkeypatch):
    for name in ("_trade_job_revoked",):
        monkeypatch.setattr(server, name, lambda *a: False)
    for name in ("_prepared_job_matches", "_trade_owner_model_matches"):
        monkeypatch.setattr(server, name, lambda *a: True)
    monkeypatch.setattr(server, "_trade_presentation_matches", lambda *a: True)
    monkeypatch.setattr(server, "_trade_safety_signature", lambda *a: [])
    import time
    job = {"status": "complete", "finished_at": time.monotonic(), "fairness_threshold": 0.75,
           "outlook_value": None, "key": ("u", "l", "1qb_ppr"), "safety_policy": []}
    assert server._trade_job_is_fresh(job, 0.75, None, presentation_capture=object()) is not False
    assert server._trade_job_is_fresh(job, 0.65, None, presentation_capture=object()) is False


# ── the replay tool on a synthetic fixture ─────────────────────────────────

def _synthetic_case(seed=3, teams=4, players=8):
    rng = random.Random(seed)
    pos = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "RB"]
    case = {"lineage": "lin%d" % seed, "format": "1qb", "viewer": "t0", "partner": "t1", "teams": {}}
    for t in range(teams):
        assets = [{"id": "p%d_%d" % (t, i), "pos": pos[i % len(pos)], "age": rng.randint(21, 31),
                   "value": float(rng.randint(400, 6000)), "token": "p%d_%d" % (t, i)} for i in range(players)]
        assets.append({"id": "k%d" % t, "pos": "PICK", "age": None, "value": 1800.0, "token": "P:2027:1"})
        case["teams"]["t%d" % t] = {"outlook": ["contender", "rebuilder"][t % 2], "assets": assets}
    return case


@pytest.fixture(scope="module")
def eng():
    import socket
    saved = socket.socket.connect, socket.create_connection
    try:
        yield replay.load_engine(under_pytest=True)
    finally:
        socket.socket.connect, socket.create_connection = saved


def test_replay_finds_a_real_trade_that_is_in_the_deck(eng):
    case = _synthetic_case()
    probe = replay.replay_case(dict(case, real_give=[], real_receive=[]), eng, thresholds=(0.65,))
    assert probe["0.65"]["n_cards"] > 0
    kwargs, meta = replay._inputs(case, eng)
    cards, _ = eng[1].generate_bilateral_trades(fairness_threshold=0.65, **kwargs)
    target = next(c for c in cards if c.target_user_id == "t1")
    rank = cards.index(target) + 1
    case["real_give"] = [{"token": meta[p][1], "value": meta[p][2]} for p in target.give_player_ids]
    case["real_receive"] = [{"token": meta[p][1], "value": meta[p][2]} for p in target.receive_player_ids]
    out = replay.replay_case(case, eng)
    assert set(out) == {"0.75", "0.70", "0.65", "0.60", "0.55"}
    assert out["0.65"]["exact_rank"] == rank and out["0.65"]["close_rank"] <= rank
    # The engine clamps to market_floor_absolute (0.65): 0.60 and 0.55 are 0.65.
    assert out["0.60"]["deck"] == out["0.55"]["deck"] == out["0.65"]["deck"]
    for v in out.values():
        assert v["first30_under"] <= v["first30_n"] <= replay.FIRST_PAGE


def test_close_rule():
    case = {"partner": "t1", "real_give": [{"token": "a", "value": 60.0}],
            "real_receive": [{"token": "b", "value": 40.0}, {"token": "c", "value": 10.0}]}
    meta = {"A": ("t0", "a", 60.0), "B": ("t1", "b", 40.0), "C": ("t1", "c", 10.0), "D": ("t1", "d", 45.0)}
    card = lambda g, r, who="t1": SimpleNamespace(target_user_id=who, give_player_ids=g, receive_player_ids=r)
    assert replay.match_card(case, meta, card(["A"], ["B", "C"])) == (True, True)
    assert replay.match_card(case, meta, card(["A"], ["B"])) == (True, False)       # 100/110
    assert replay.match_card(case, meta, card(["A"], ["D"])) == (False, False)      # 60/155
    assert replay.match_card(case, meta, card(["A"], ["B", "C"], who="t2")) == (False, False)


def _rows(gain_at, n=60):
    rows = []
    for i in range(n):
        by = {}
        for thr in replay.CANDIDATES:
            hit = (i % 3 == 0) or (thr <= gain_at and i % 3 == 1)
            by["%.2f" % thr] = {"n_cards": 10, "secs": 1.0, "close_rank": 1 if hit else None,
                                "exact_rank": None, "first30_n": 10, "first30_under": 0, "deck": []}
        rows.append({"lineage": "L%d" % (i % 30), "by_threshold": by})
    return rows


def test_decision_rule_adopts_tightest_of_equal_winners():
    res = replay.summarise(_rows(gain_at=0.70), draws=200)
    assert res["selection"]["adopted"] == 0.70          # 0.70..0.55 tie; tighter wins
    assert res["selection"]["passed"] == [0.70, 0.65, 0.60, 0.55]


def test_decision_rule_keeps_075_when_nothing_gains():
    res = replay.summarise(_rows(gain_at=0.0), draws=200)
    assert res["selection"]["adopted"] == 0.75 and res["selection"]["passed"] == []


def test_decision_rule_refuses_a_slow_winner():
    rows = _rows(gain_at=0.65)
    for r in rows:
        r["by_threshold"]["0.65"]["secs"] = r["by_threshold"]["0.60"]["secs"] = \
            r["by_threshold"]["0.55"]["secs"] = 1.2
    assert replay.summarise(rows, draws=200)["selection"]["adopted"] == 0.75


def test_replay_tool_never_imports_the_server_module():
    import re
    src = (REPO / "backend/eval/fairness_window_replay.py").read_text()
    imports = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    assert imports and not any("server" in l for l in imports)
