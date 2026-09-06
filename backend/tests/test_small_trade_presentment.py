"""Small-trade-packages T1–T8: bounded presentation, actual worker and spine.

Generators and per-card valuation supply deterministic fixtures; real bakeoff
drafting, final policy composition, publication and writers remain exercised.
"""
from collections import Counter
from dataclasses import replace
import copy
import json
import inspect
import time
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import database as db, server, trade_policy as tp, trade_service as ts
from backend import bakeoff_runner as bo
from backend import small_trade_presentment as sp
from backend.tests.support import bakeoff_harness as H
from backend.tests.test_bakeoff_serving import _bakeoff_patches, _stub_arms, _card
from backend.tests.test_trade_disposition_replay import replay
from backend.tests.test_decline_reasons import harness, mem_engine, LEAGUE, ME, TOKEN, _post
from backend.tests.test_session_init_sleeper_calls import (
    harness as init_harness, _init, USER_ID, NON_SLEEPER_LEAGUE,
)


@pytest.fixture(autouse=True)
def isolate_config():
    before = dict(ts._cfg)
    yield
    ts._cfg.clear()
    ts._cfg.update(before)


def six_cards():
    cards = [
        _card(["qb1", "rb1", "wr2"], ["rb2", "wr1", "ra3"]),
        _card(["te1"], ["rb2", "wr1", "ra3", "ra4"]),
        _card(["qb1", "te1"], ["rb2", "wr1", "ra4"]),
        _card(["qb1"], ["ra4"]),
        _card(["rb1"], ["rb2", "ra3"]),
        _card(["wr2"], ["wr1"]),
    ]
    for index, card in enumerate(cards):
        card.trade_id = f"small-{index}"
        card.lane = "value"
    return cards


def verdict(card, lane=tp.LANE_CORE):
    board = tp.BoardValuation.consensus_only()
    return tp.PolicyResult(
        eligible=True, reason=None, lane=lane, basis="fixture", market_ratio=1,
        market_gives=1000, market_receives=1000, requested_floor=.75,
        policy_floor=.65, effective_floor=.75, viewer=board, partner=board,
        personal_opportunity=.1, harmonic_effective_surplus=.1,
        trade_confidence=1, policy_variant=tp.POLICY_V1,
        valuation={"assets": {"give": [{"id": p} for p in card.give_player_ids],
                               "receive": [{"id": p} for p in card.receive_player_ids]}},
    )


def worker(cards=None, *, mode=1, signal=True, telemetry=False, extra=(), grouped=False,
           scoring_format="1qb_ppr"):
    cards = cards if cards is not None else six_cards()
    ts._cfg["simple_player_presentment"] = mode
    order = ["baseline", "current", "gen_v2"]
    pool = H._POOL + [("ra3", "Receiver Three", "WR", "AAA", 25, 1550),
                      ("ra4", "Receiver Four", "WR", "BBB", 26, 1600)]
    patches = [
        patch.object(server._trade_policy, "policy_enabled", lambda: True),
        patch.object(server._trade_policy, "telemetry_enabled", lambda: True),
        patch.object(server, "_evaluate_card_policy", lambda card, *a, **kw: verdict(card)),
        patch.object(server, "_deck_signal_v2_enabled", lambda: signal),
        patch.object(server, "_suggestion_telemetry_enabled", lambda: telemetry),
        patch.object(bo, "draft_order_for", lambda parts, lid, wk=None:
                     [p for arm in order for p in parts if p == arm or p.startswith(arm + "_")]),
    ]
    patches += _bakeoff_patches(enabled=True, interleaved=True, composed=grouped,
                                bakeoff_include_baseline=1, bakeoff_include_challenger=0)
    patches += _stub_arms(cards[0::3], cards[1::3], cards[2::3])
    # The harness constructs its league BEFORE entering extra_patches.
    with patch.object(H, "_POOL", pool), \
            patch.object(H, "SEED", {row[0]: row[-1] for row in pool}), \
            patch.object(H, "OPP_ROSTER", ["rb2", "wr1", "ra3", "ra4"]):
        kwargs = {"scoring_format": scoring_format} if scoring_format != "1qb_ppr" else {}
        return H.run_capture(extra_patches=patches + list(extra), seed_like=False, **kwargs)


def shapes(rows):
    return [(len(row["give"]), len(row["receive"])) for row in rows]


@pytest.mark.parametrize("signal", [False, True])
@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("scoring_format", ["1qb_ppr", "sf_tep"])
def test_t1_actual_worker_moves_same_arm_cards_16_to_7(signal, grouped, scoring_format):
    capture, job, _engine = worker(signal=signal, grouped=grouped, scoring_format=scoring_format)
    assert job["status"] == "complete", job.get("error")
    assert shapes(job["cards"]) == [(1, 1), (1, 2), (1, 1), (3, 3), (1, 4), (2, 3)]
    assert sum(sum(shape) for shape in shapes(job["cards"])[:3]) == 7
    if signal:
        rows = capture["impressions"]
        assert [row["model_arm"] for row in rows] == ["baseline", "current", "gen_v2"] * 2
        assert [row["arm_rank"] for row in rows] == [1, 1, 1, 0, 0, 0]
        assert [row["group_rank"] for row in rows] == ([1, 1, 1, 0, 0, 0] if grouped else [None] * 6)


def helper(cards, *, players=None, results=None, **kwargs):
    if players is None:
        players = {pid: SimpleNamespace(position="WR") for card in cards
                   for pid in card.give_player_ids + card.receive_player_ids}
    context = dict(players=players, league_id=H.LEAGUE,
                   owned_pick_parser=server._parse_owned_pick_id,
                   player_positions=server.VALID_POSITIONS, is_pick_asset=ts.is_pick_asset,
                   policy_results=results if results is not None else {id(c): verdict(c) for c in cards},
                   bakeoff_expected=False, bakeoff_run=None, grouped=False)
    context.update(kwargs)
    return sp.present(cards, **context)


@pytest.mark.parametrize("value", [0, None, False, True, "1", "1.0", -1, 2, 1.001,
                                  float("inf"), float("nan"), {}, [], 10**400])
def test_t5_unsupported_mode_is_off_without_coercion(value):
    assert sp.mode(value) == (0, None)


@pytest.mark.parametrize("value", [1, 1.0])
def test_t5_exact_numeric_one_enables(value):
    assert sp.mode(value) == (1, "simple-player-v1")


def test_t2_absolute_windows_classes_stability_and_occurrence_multiset():
    cards = [copy.deepcopy(six_cards()[i % 6]) for i in range(17)]
    for index, card in enumerate(cards):
        card.trade_id = str(index)
        card.lane = None if index % 2 else "value"
        card.basis = "consensus" if index % 4 else "divergence"
    cards[7].wildcard = True  # hole must not compact either six-slot window
    results = {id(c): verdict(c, tp.LANE_FALLBACK if i % 5 == 0 else tp.LANE_CORE)
               for i, c in enumerate(cards)}
    before = copy.deepcopy([vars(c) for c in cards])
    after, records = helper(cards, results=results)
    assert Counter(map(id, cards)) == Counter(map(id, after))
    assert [vars(c) for c in cards] == before
    assert after[7] is cards[7]
    for index, (card, record) in enumerate(zip(after, records)):
        original = record["original_index"]
        assert card is cards[original]
        assert abs(index - original) <= 5
        assert index // 6 == original // 6
        assert (card.lane, card.basis, results[id(card)].lane) == (
            cards[index].lane, cards[index].basis, results[id(cards[index])].lane)
    again, _ = helper(after, results=results)
    assert list(map(id, again)) == list(map(id, after))
    # A repeated object is an occurrence, not a dictionary key to collapse.
    duplicates = [cards[0], cards[0], cards[1], cards[1]]
    kept, records = helper(duplicates)
    assert Counter(map(id, kept)) == Counter(map(id, duplicates))
    assert sorted(r["original_index"] for r in records) == [0, 1, 2, 3]


@pytest.mark.parametrize("marker", ["likes_you", "standing_offer_reason", "wildcard", "fatigue_retest", "retest"])
def test_t3_special_exact_slot_is_locked(marker):
    cards = six_cards()
    setattr(cards[0], marker, True)
    after, records = helper(cards)
    assert after[0] is cards[0] and records[0]["original_index"] == 0


def test_t3_picks_do_not_penalize_mixed_packages_or_break_player_ties():
    owned = db.make_pick_id(H.LEAGUE, 2027, 1, "roster_1")
    generic = "generic_pick_1_early"
    cards = [_card(["g1", "g2"], ["r1", "r2"]),
             _card(["g1", owned, generic], ["r1"]),
             _card(["g2"], ["r2"]),
             _card([generic], ["r2"])]
    players = {pid: SimpleNamespace(position="WR") for pid in ("g1", "g2", "r1", "r2")}
    after, records = helper(cards, players=players)
    assert after == [cards[3], cards[1], cards[2], cards[0]]
    assert records[0]["give_player_count"] == 0
    assert records[1]["give_player_count"] == 1


def test_t3_real_position_generic_pseudo_asset_is_a_pick():
    from backend.ranking_service import Player
    generic = "generic_pick_1_early"
    cards = [_card(["g1", "g2"], ["r1"]), _card([generic], ["r1"])]
    players = {p: Player(id=p, name=p, position="WR", team="NFL", age=25)
               for p in ("g1", "g2", "r1")}
    players[generic] = Player(id=generic, name="Early first", position="RB", team="PICK", age=0)
    after, records = helper(cards, players=players)
    assert after == [cards[1], cards[0]]
    assert records[0]["give_player_count"] == 0


@pytest.mark.parametrize("give,receive,players,counts", [
    (["generic_pick_1_early"], ["generic_pick_2_mid"], {}, (0, 0)),
    (["unknown"], ["r"], {"r": "WR"}, (None, 1)),
    (["generic_pick_1_early"], ["r"], {"generic_pick_1_early": "WR", "r": "WR"}, (None, 1)),
    (["not_a_pick"], ["r"], {"not_a_pick": "PICK", "r": "WR"}, (None, 1)),
    (["not_a_position"], ["r"], {"not_a_position": "garbage", "r": "WR"}, (None, 1)),
    ([f"{H.LEAGUE}_2027_1_"], ["r"], {"r": "WR"}, (None, 1)),
    ([], ["r"], {"r": "WR"}, (None, 1)),
])
def test_t3_unknown_conflicting_malformed_and_pure_pick_cards_lock(give, receive, players, counts):
    cards = [_card(give, receive), _card(["g"], ["r"])]
    pool = {pid: SimpleNamespace(position=pos) for pid, pos in players.items()}
    pool["g"] = SimpleNamespace(position="WR")
    after, records = helper(cards, players=pool)
    assert after[0] is cards[0]
    assert (records[0]["give_player_count"], records[0]["receive_player_count"]) == counts


def test_t3_actual_attribution_and_required_group_locks():
    cards = six_cards()
    arms = {"baseline": cards[:3], "current": cards[3:]}
    run = bo.BakeoffRun("fixture", list(arms),
        {name: bo.ArmResult(name, values, 0) for name, values in arms.items()},
        bo.team_draft(arms, list(arms)), None, 0)
    after, _ = helper(cards, bakeoff_expected=True, bakeoff_run=run, grouped=True)
    assert after == cards  # group expected but absent; never guess organic
    after, _ = helper(cards, bakeoff_expected=True, bakeoff_run=None)
    assert after == cards
    run.draft.attribution.pop(id(cards[0]))
    after, _ = helper(cards, bakeoff_expected=True, bakeoff_run=run)
    assert after[0] is cards[0]
    after, _ = helper(cards, results={})
    assert after == cards


@pytest.mark.parametrize("signal", [False, True])
@pytest.mark.parametrize("telemetry", [False, True])
def test_t4_t6_held_worker_pass_remaps_duplicate_occurrences_before_freeze(signal, telemetry):
    cards = six_cards()
    cards.extend([copy.deepcopy(cards[3]), cards[3]])
    real_project = server._project_trade_dispositions
    real_present = sp.present
    observed = []

    def project(values, *args, **kwargs):
        # This actual boundary is after first evaluated publication but before
        # legacy/F1 writes. Simulate an exact pass arriving while held here.
        observed.append(copy.deepcopy(server._trade_jobs[H.JOB_ID]["cards"]))
        assert shapes(observed[-1]) == [(1, 1), (1, 1), (1, 2), (2, 3),
                                        (3, 3), (1, 4), (1, 1), (1, 1)]
        assert not server._trade_jobs[H.JOB_ID]["final_checks_pending"]
        db.save_trade_decision(H.ME, H.LEAGUE, "arrived-while-held",
                               cards[0].give_player_ids, cards[0].receive_player_ids, "pass")
        return real_project(values, *args, **kwargs)

    with patch.object(sp, "present", wraps=real_present) as presentation_call:
        capture, job, engine = worker(cards, signal=signal, telemetry=telemetry, extra=[
            patch.object(bo, "bakeoff_enabled", lambda: False),
            patch.object(ts.TradeService, "generate_trades", lambda *a, **kw: cards),
            patch.object(server, "_order_deck", lambda values, *a, **kw: values),
            patch.object(server, "_project_trade_dispositions", project),
        ])
    assert job["status"] == "complete", job.get("error")
    assert len(observed) == 1 and presentation_call.call_count == 1
    assert shapes(job["cards"]) == [(1, 1), (1, 1), (1, 2), (2, 3), (1, 4), (1, 1), (1, 1)]
    if signal:
        rows = capture["impressions"]
        records = [json.loads(row["features_json"])["presentation"] for row in rows]
        assert [r["original_index"] for r in records] == [3, 5, 4, 2, 1, 6, 7]
        assert [r["final_index"] for r in records] == [r["card_index"] for r in rows] == list(range(7))
        assert all(r["version"] == sp.VERSION and r["window_size"] == 6 for r in records)
        assert all(row["model_arm"] is None for row in rows)  # actual organic, no fake arm
        assert all(row["policy_version"].endswith("/pp:simple-player-v1") for row in rows)
        assert all(row["policy_variant"] == tp.POLICY_V1 for row in rows)
    else:
        assert capture["impressions"] == []
    with engine.connect() as conn:
        candidate_rows = conn.execute(select(db.deck_candidate_sets_table)).all()
        frozen = conn.execute(select(db.deck_impressions_table)).all()
        legacy = conn.execute(select(db.trade_impressions_table).order_by(
            db.trade_impressions_table.c.position_in_deck)).mappings().all()
    assert [r["position_in_deck"] for r in legacy] == list(range(7))
    assert [(len(json.loads(r["give_player_ids"])), len(json.loads(r["receive_player_ids"])))
            for r in legacy] == shapes(job["cards"])
    assert bool(candidate_rows) is (signal and telemetry)
    # A later serve-time pass cannot rewrite any frozen occurrence index.
    with patch.object(db, "engine", engine):
        db.save_trade_decision(H.ME, H.LEAGUE, "later-pass",
                               cards[2].give_player_ids, cards[2].receive_player_ids, "pass")
        survivors = real_project(job["cards"], H.ME, H.LEAGUE)
    assert len(survivors) == 6
    with engine.connect() as conn:
        assert conn.execute(select(db.deck_impressions_table)).all() == frozen


@pytest.mark.parametrize("initial", [0, 1])
def test_t5_worker_mode_and_base_version_are_captured_before_hot_flip(initial):
    current_version = ["captured-base"]

    def evaluate(card, *args, **kwargs):
        ts._cfg["simple_player_presentment"] = 1 - initial
        current_version[0] = "changed-after-capture"
        return verdict(card)

    capture, job, _ = worker(mode=initial, telemetry=True, extra=[
        patch.object(server._sugg_tel, "serving_policy_version", lambda: current_version[0]),
        patch.object(server, "_evaluate_card_policy", evaluate),
    ])
    expected = ([3, 4, 5, 0, 1, 2] if initial else list(range(6)))
    assert shapes(job["cards"]) == [shapes_for_card(six_cards()[i]) for i in expected]
    for row in capture["impressions"]:
        assert row["policy_version"].startswith("captured-base/")
        assert ("/pp:simple-player-v1/bo:" in row["policy_version"]) is bool(initial)
        assert ("presentation" in json.loads(row["features_json"])) is bool(initial)


def shapes_for_card(card):
    return len(card.give_player_ids), len(card.receive_player_ids)


@pytest.mark.parametrize("status", ["complete", "running"])
@pytest.mark.parametrize("old,new", [(None, 0), (None, 1), (0, 0), (0, 1), (1, 0), (1, 1)])
def test_t5_generate_completed_and_running_cache_mode_boundaries(replay, monkeypatch, status, old, new):
    client, _svc, _engine, job, _siblings = replay
    job["status"] = status
    if old is not None:
        job["presentation_capture"] = (*sp.mode(old), "old-base")
    ts._cfg["simple_player_presentment"] = new
    before = copy.deepcopy(job)
    calls = []

    def kickoff(**kwargs):
        calls.append(kwargs)
        fresh = dict(job, job_id="new-presentation-job", presentation_capture=kwargs["presentation_capture"])
        monkeypatch.setitem(server._trade_jobs, fresh["job_id"], fresh)
        return fresh["job_id"]

    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)
    response = _post(client, {"league_id": LEAGUE, "fairness_threshold": .75},
                     path="/api/trades/generate")
    assert response.status_code == 200, response.get_json()
    changed = (old or 0) != new
    assert len(calls) == int(changed)
    assert response.get_json()["job_id"] == ("new-presentation-job" if changed else job["job_id"])
    if changed:
        assert calls[0]["presentation_capture"][:2] == sp.mode(new)
    assert job == before
    # An explicit old-ID poll remains old order even after the flag flips.
    polled = client.get(f"/api/trades/status?job_id={job['job_id']}", headers={"X-Session-Token": TOKEN})
    assert polled.status_code == 200 and polled.get_json()["cards"] == before["cards"]


@pytest.mark.parametrize("old,new", [(None, 0), (None, 1), (0, 1), (1, 0), (1, 1)])
@pytest.mark.parametrize("status", ["complete", "running"])
def test_t5_session_init_pregen_cache_mode_boundaries(init_harness, monkeypatch, old, new, status):
    client, _ = init_harness
    ts._cfg["simple_player_presentment"] = new
    key = server._trade_job_key(USER_ID, NON_SLEEPER_LEAGUE, "1qb_ppr")
    job = dict(job_id="presentation-pregen", status=status, finished_at=time.monotonic())
    if old is not None:
        job["presentation_capture"] = (*sp.mode(old), "old-base")
    monkeypatch.setitem(server._trade_jobs, job["job_id"], job)
    monkeypatch.setitem(server._trade_jobs_by_key, key, job["job_id"])
    assert _init(client, NON_SLEEPER_LEAGUE).status_code == 200
    kickoff = server._kickoff_trade_job
    changed = (old or 0) != new
    assert kickoff.call_count == int(changed)
    if changed:
        assert kickoff.call_args.kwargs["presentation_capture"][:2] == sp.mode(new)


@pytest.mark.parametrize("old,new", [(None, 0), (None, 1), (0, 1), (1, 0), (1, 1)])
def test_t5_replenish_cache_mode_boundaries(replay, monkeypatch, old, new):
    _client, _svc, _engine, job, _siblings = replay
    if old is not None:
        job["presentation_capture"] = (*sp.mode(old), "old-base")
    ts._cfg["simple_player_presentment"] = new
    calls = []

    def kickoff(**kwargs):
        calls.append(kwargs)
        fresh = dict(job, job_id="presentation-replenish", presentation_capture=kwargs["presentation_capture"])
        monkeypatch.setitem(server._trade_jobs, fresh["job_id"], fresh)
        return fresh["job_id"]

    monkeypatch.setattr(server, "get_league_scoring", lambda _: "1qb_ppr")
    monkeypatch.setattr(server, "_find_live_session_token", lambda *args: TOKEN)
    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)
    assert server._replenish_deck_for(ME, LEAGUE) == (3, 0)
    assert len(calls) == int((old or 0) != new)
    if calls:
        assert calls[0]["presentation_capture"][:2] == sp.mode(new)


@pytest.mark.parametrize("exempt", [False, True])
def test_t5_actual_kickoff_passes_one_capture_to_held_worker(replay, monkeypatch, exempt):
    _client, _svc, _engine, old_job, _siblings = replay
    captured, calls = (1, sp.VERSION, "request-base"), []

    def worker_spy(*args, **kwargs):
        calls.append((kwargs["presentation_capture"], kwargs["presentation_exempt"]))

    monkeypatch.setattr(server, "_run_trade_job", worker_spy)
    ts._cfg["simple_player_presentment"] = 0  # changed after caller's decision
    jid = server._kickoff_trade_job(sess_token=TOKEN, user_id=ME, league_id=LEAGUE,
        scoring_format="1qb_ppr", synchronous=True, presentation_capture=captured,
        presentation_exempt=exempt)
    try:
        assert calls == [(captured, exempt)]
        assert server._trade_jobs[jid]["presentation_capture"] == captured
        assert server._trade_jobs_by_key[old_job["key"]] == (old_job["job_id"] if exempt else jid)
    finally:
        server._trade_jobs.pop(jid, None)


@pytest.mark.parametrize("exemption", ["give", "receive", "ignored_receive", "opponent", "demo", "ghost", "shadow", "dark", "failure"])
def test_t3_t7_actual_worker_exemptions_have_no_presentation(exemption):
    real_worker = server._run_trade_job

    def scoped(*args, **kwargs):
        bound = inspect.signature(real_worker).bind(*args, **kwargs)
        if exemption in ("give", "receive", "opponent"):
            key, value = {"give": ("pinned_give", ["qb1"]),
                          "receive": ("pinned_receive", ["rb2"]),
                          "opponent": ("opponent_user_id", H.OPP)}[exemption]
            bound.arguments[key] = value
        elif exemption == "ignored_receive":
            bound.arguments["presentation_exempt"] = True
        return real_worker(*bound.args, **bound.kwargs)

    def run(mode):
        extra = [patch.object(server, "_run_trade_job", scoped)]
        if exemption == "ghost":
            extra += [patch.object(server, "_ghost_holdout_active", lambda *a: True)]
        elif exemption == "shadow":
            extra += [patch.object(server._trade_policy, "policy_enabled", lambda: False),
                      patch.object(server.FLAGS, "trade_mutual_benefit_v1", False)]
        elif exemption == "dark":
            extra += _bakeoff_patches(enabled=True, interleaved=False)
        elif exemption == "failure":
            extra += [patch.object(server, "_evaluate_deck_policy", side_effect=RuntimeError("fixture policy failure"))]
        league = "league_demo" if exemption == "demo" else H.LEAGUE
        with patch.object(H, "LEAGUE", league), patch.object(sp, "present", wraps=sp.present) as invoked:
            capture, job, _ = worker(mode=mode, extra=extra)
        assert not invoked.called
        assert job["status"] == "complete", job.get("error")
        assert all("presentation" not in json.loads(r["features_json"]) for r in capture["impressions"])
        return capture

    off, enabled = run(0), run(1)
    # Only private on-job bookkeeping is new; off/exempt public and frozen
    # outputs retain their unmodified baseline contract.
    assert off["cards"] == enabled["cards"]
    assert off["impressions"] == enabled["impressions"]


def test_t6_locked_unknown_unattributed_first_row_keeps_uniform_provenance():
    cards = six_cards()
    cards[0].give_player_ids = ["unknown-asset"]
    actual_run = bo.run_bakeoff

    def no_first_credit(*args, **kwargs):
        run = actual_run(*args, **kwargs)
        run.draft.attribution.pop(id(cards[0]), None)
        return run

    capture, job, _ = worker(cards, extra=[patch.object(bo, "run_bakeoff", no_first_credit)])
    assert job["status"] == "complete", job.get("error")
    rows = capture["impressions"]
    first = json.loads(rows[0]["features_json"])["presentation"]
    assert first["give_player_count"] is None and first["original_index"] == first["final_index"] == 0
    assert rows[0]["model_arm"] is None
    assert rows[0]["policy_version"].endswith("/pp:simple-player-v1")
    assert all("/pp:simple-player-v1" in row["policy_version"] for row in rows)
    assert [row["model_arm"] for row in rows[1:]] == ["current", "gen_v2", "baseline", "current", "gen_v2"]


@pytest.mark.parametrize("status", ["complete", "running"])
@pytest.mark.parametrize("mode", [0, 1])
@pytest.mark.parametrize("supplied", [False, True])
def test_t3_raw_receive_exemption_survives_targeting_off_route(replay, monkeypatch, status, mode, supplied):
    client, _svc, _engine, job, _siblings = replay
    job.update(status=status, presentation_capture=(*sp.mode(mode), "matched-base"))
    ts._cfg["simple_player_presentment"] = mode
    actual_flag, calls = server.is_enabled, []
    monkeypatch.setattr(server, "is_enabled", lambda key: False if key == "trade.finder_targeting" else actual_flag(key))

    def kickoff(**kwargs):
        calls.append(kwargs)
        fresh = dict(job, job_id="explicit-uninterpreted-search")
        monkeypatch.setitem(server._trade_jobs, fresh["job_id"], fresh)
        return fresh["job_id"]

    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)
    body = {"league_id": LEAGUE, "pinned_receive_players": ["r1"] if supplied else []}
    response = _post(client, body, path="/api/trades/generate")
    assert response.status_code == 200
    bypass = bool(mode and supplied)
    assert len(calls) == int(bypass)
    assert response.get_json()["job_id"] == ("explicit-uninterpreted-search" if bypass else job["job_id"])
    assert server._trade_jobs_by_key[job["key"]] == job["job_id"]
    if bypass:
        assert calls[0]["presentation_exempt"] is True
        assert calls[0]["pinned_receive"] is None  # generation still ignores unsupported targeting
        assert calls[0]["fairness_threshold"] == .75  # no new pin/fairness semantics
