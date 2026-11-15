"""Fairness formula (flag trade.fairness_formula_v2) — docs/plans/fairness-formula/spec.md.

Pins:
  * registration: default False in code, false in config and the three fixtures; the
    four knobs are seeded at today's math;
  * knob validation, and flag OFF never reads the knobs;
  * each arm's side value, ratio and floor on hand-computed numbers;
  * flag OFF: owner, r1, r2 and r4 decks are byte-identical to main (golden digests
    computed on origin/main c8807cdd before this change), with the knobs at every arm's
    values; flag ON with default knobs is byte-identical too;
  * a non-default formula changes a deck, and its proofs still revalidate;
  * the replay tool (backend/eval/fairness_formula_replay.py) on a synthetic fixture,
    and its pre-registered decision rule.
"""
from dataclasses import asdict
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from backend import bakeoff_runner as bo, database as db, feature_flags as ff, trade_service as ts
from backend import fairness_formula as fx
from backend import trade_gen_bilateral_r4 as r4
from backend.data_loader import SEED_VALUE_FLOOR, seed_elo_for_value
from backend.ranking_service import Player
from backend.trade_gen_owner import generate_owner_trades
from backend.tests.test_bilateral_contracts import favorable
from backend.tests.test_bilateral_revision_4 import best_asset_world, premium_world
from backend.tests.test_fairness_window import _synthetic_case
from backend.tests.test_owner_generator_routes import harness, owner_harness, context_for  # noqa: F401
from backend.eval import fairness_formula_replay as replay, fairness_window_replay as window_replay

REPO = Path(__file__).resolve().parents[2]

ARMS = {"A": (0.0, 0.7, 0.0, 1.0), "B": (0.0, 0.7, 0.0, 0.7),
        "C": (0.0, 1.0, 0.0, 1.0), "D": (0.0, 0.7, 1.0, 1.0)}


def knobs(arm):
    return dict(zip(fx.KNOBS, ARMS[arm]))


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def flag(on):
    ff._flags_cache[fx.FLAG] = on


# ── worlds and the digest ──────────────────────────────────────────────────

def synthetic(seed=3, teams=4, players=8, threshold=.75):
    """A league like the replay's synthetic case: enough assets for a real deck."""
    rng = random.Random(seed)
    pos = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "RB"]
    roster, seed_elo, players_ = {}, {}, {}
    for t in range(teams):
        ids = []
        for i in range(players):
            pid = "p%d_%d" % (t, i)
            players_[pid] = Player(pid, pid, pos[i % len(pos)], "TST", rng.randint(21, 31))
            seed_elo[pid] = seed_elo_for_value(float(rng.randint(400, 6000)))
            ids.append(pid)
        pid = "k%d" % t
        players_[pid] = Player(pid, pid, "PICK", "PICK", None)
        seed_elo[pid] = seed_elo_for_value(1800.0)
        ids.append(pid)
        roster["t%d" % t] = ids
    members = [ts.LeagueMember(u, u, roster[u], {}, False) for u in roster if u != "t0"]
    return dict(players=players_, league=ts.League("L", "synthetic", "sleeper", members),
                user_id="t0", user_roster=roster["t0"], user_elo={}, seed_elo=seed_elo,
                scoring_format="1qb_ppr", fairness_threshold=threshold, outlook="contender",
                opponent_outlooks={"t1": "rebuilder", "t2": "contender", "t3": "rebuilder"})


WORLDS = {"favorable": favorable, "premium": lambda: premium_world("rebuilder"),
          "best_asset": lambda: best_asset_world("contender", "WR", 1300.), "synthetic": synthetic}
BASES = {"owner": {}, "r1": {"owner_bilateral_enabled": 1.},
         "r2": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.},
         "r4": {"owner_bilateral_revision_4_enabled": 1.}}


def generate(revision, world, extra=None):
    base = BASES[revision]
    cfg = dict(ts._DEFAULT_CFG, **base)
    fn = generate_owner_trades if revision == "owner" else bo.owner_generator(cfg)
    return fn(**WORLDS[world](), config={**base, **(extra or {})})


def digest(cards, report):
    encoded = [asdict(c) for c in cards]
    for card in encoded:
        for key in ("trade_id", "created_at", "expires_at"):
            card[key] = "variable-occurrence"
    report = report.as_dict()
    report.pop("elapsed_seconds", None)
    return hashlib.sha256(json.dumps([encoded, report], sort_keys=True, default=str).encode()).hexdigest()


# Computed on origin/main c8807cdd (before this change existed) with the same worlds,
# configs and digest. ("r1", "synthetic") and ("r2", "synthetic") are left out: on main
# itself those decks depend on PYTHONHASHSEED (seed 10 gives other digests), so they are
# pinned in-process instead
# (test_flag_off_matches_the_unconfigured_deck_in_process).
GOLDEN = {
    ("owner", "favorable"): "dc22adea2f2dac8056723a13af9fb0b501d7bd2f955be4ccdfde03352faa215e",
    ("owner", "premium"): "20c7105175a6354aaa008478190619c334f61c6fd86e315b88e78f9a05601f77",
    ("owner", "best_asset"): "e39d3518259b2ec282945fd0fc6970ab71ab863b4c4a296cee53343a586aefda",
    ("owner", "synthetic"): "8fa3a0c5519216391735fe491a10966fcb51443fdce3525d4e1001fb41b11aa4",
    ("r1", "favorable"): "75df37aebfa5c5ae3919cebb406376d7d1cc81e64f9f33cbbb04f3f0ae4f1b06",
    ("r1", "premium"): "13ccb66a8b8a08cc2e5aeccc3d658d4daf9a011c1ce859cd092844f52446ef05",
    ("r1", "best_asset"): "fc96d2f791a10a59cfd9d4169b1241821847599b1d51bcc976d9d3e86021560a",
    ("r2", "favorable"): "f595c2d8bed111f0a5ec13f8591cb84506992158070789e5159d7c13860e41c7",
    ("r2", "premium"): "3c6faf66ab6eddcba50e36aa6d4a4c3f2c3e3a3efa6cf40e4ce9b355a002f89f",
    ("r2", "best_asset"): "3c0f2e29ebaa1577a03c925dbb9f0d64278e1d31fc4767142d696823963ff511",
    ("r4", "favorable"): "cf8e11bd1becf9a4d96e561d77109af6ba3fa069086d2e19dcec37d0e82c0280",
    ("r4", "premium"): "7f9f82bb993efd9d1b1e06b7f527b82b3ede3c47ea9fab2203b05c48a65d9603",
    ("r4", "best_asset"): "b4c435d6b062a8d8281e4ec6661668daa758e2998e27a9a235965a59fd1975a7",
    ("r4", "synthetic"): "56df8597783085f23070b1e00f4c5f51a90719127b73799194124ccf553b202d",
}


# ── registration ───────────────────────────────────────────────────────────

def test_flag_registered_default_off_everywhere():
    assert ff.DEFAULT_FLAGS[fx.FLAG] is False
    assert json.loads((REPO / "config/features.json").read_text())[fx.FLAG] is False
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[fx.FLAG] is False, name
    seeds = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    assert {k: seeds[k] for k in fx.KNOBS} == fx.DEFAULTS == {
        "fairness_formula_package_math": 1.0, "fairness_formula_exponent": 1.0,
        "fairness_formula_raw": 0.0, "fairness_formula_threshold_power": 1.0}


@pytest.mark.parametrize("key,raw,served", [
    (fx.EXPONENT, 0.7, 0.7), (fx.EXPONENT, 1.0, 1.0), (fx.EXPONENT, 0.0, 1.0), (fx.EXPONENT, 1.2, 1.0),
    (fx.EXPONENT, -0.5, 1.0), (fx.EXPONENT, float("nan"), 1.0), (fx.EXPONENT, "x", 1.0),
    (fx.EXPONENT, True, 1.0), (fx.THRESHOLD_POWER, 0.7, 0.7), (fx.THRESHOLD_POWER, float("inf"), 1.0),
    (fx.PACKAGE, 0.0, 0.0), (fx.PACKAGE, 0.5, 1.0), (fx.PACKAGE, None, 1.0),
    (fx.RAW, 1.0, 1.0), (fx.RAW, 2.0, 0.0), (fx.RAW, False, 0.0)])
def test_knob_validation(key, raw, served):
    assert fx.configured({key: raw})[key] == served
    assert fx.configured({}) == fx.DEFAULTS


def test_flag_off_never_reads_the_knobs():
    flag(False)
    with patch.object(fx, "configured", side_effect=AssertionError("read while off")):
        for arm in ARMS:
            assert fx.active(knobs(arm)) is None


def test_flag_on_default_knobs_is_today():
    flag(True)
    assert fx.active({}) is None and fx.active(dict(fx.DEFAULTS)) is None
    assert fx.active(knobs("A")) == knobs("A")


def test_override_pins_regardless_of_flag_and_restores():
    flag(False)
    with fx.override(knobs("C")):
        assert fx.active({}) == knobs("C")
        with fx.override(None):
            flag(True)
            assert fx.active(knobs("A")) is None
        assert fx.active({}) == knobs("C")
    assert fx.active(knobs("A")) == knobs("A")      # flag on, nothing pinned


# ── each arm's side value, ratio and floor (hand-computed) ─────────────────

def test_side_values_by_hand():
    # give one 1000 asset, receive 600 + 400.
    a, c = knobs("A"), knobs("C")
    assert fx.side_value(c, [600.0, 400.0]) == pytest.approx(1000.0)                  # C: plain sum
    assert fx.side_value(a, [1000.0]) == pytest.approx(125.8925, abs=1e-4)            # 10 ** 2.1
    assert fx.side_value(a, [600.0, 400.0]) == pytest.approx(88.0452 + 66.2891, abs=1e-3)
    ratio = fx.side_value(a, [1000.0]) / fx.side_value(a, [600.0, 400.0])
    assert ratio == pytest.approx(0.8157, abs=1e-4)                                   # A and B
    d = knobs("D")                                                                    # D: raw values
    assert fx.side_value(d, [9.9e9], raw_values=[1000.0]) == pytest.approx(125.8925, abs=1e-4)
    assert fx.side_value(a, [1000.0], raw_values=[9.9e9]) == pytest.approx(125.8925, abs=1e-4)


def test_raw_value_removes_only_the_seed_constant():
    assert SEED_VALUE_FLOOR == pytest.approx(223.13, abs=0.01)
    prime = Player("x", "x", "WR", "TST", 26)
    # DP 5000 -> app value 223.13 + 4122.43; raw keeps 4122.43.
    assert ts.elo_to_value(seed_elo_for_value(5000.0)) == pytest.approx(4345.565, abs=0.01)
    assert fx.raw_value(ts, seed_elo_for_value(5000.0), prime) == pytest.approx(4122.435, abs=0.01)
    # The age preference still applies (to the raw value).
    young = Player("y", "y", "WR", "TST", 21)
    ts._cfg.update(age_pref_mult_u23=1.10)
    assert fx.raw_value(ts, seed_elo_for_value(5000.0), young) == pytest.approx(4122.435 + 412.24, abs=0.02)


def test_floors_by_hand():
    assert fx.floor(knobs("A"), .75, .65) == .75
    assert fx.floor(knobs("B"), .75, .65) == pytest.approx(0.8176, abs=1e-4)          # 0.75 ** 0.7
    assert fx.floor(knobs("A"), .50, .65) == .65                                       # absolute floor holds
    assert fx.floor(knobs("B"), .50, .65) == .65                                       # .5 ** .7 = .616


# ── the generators: flag off is main, byte for byte ────────────────────────

@pytest.mark.parametrize("extra", [None] + [knobs(a) for a in ARMS], ids=["absent"] + list(ARMS))
@pytest.mark.parametrize("revision,world", sorted(GOLDEN))
def test_flag_off_decks_are_byte_identical_to_main(revision, world, extra):
    flag(False)
    assert digest(*generate(revision, world, extra)) == GOLDEN[revision, world]


@pytest.mark.parametrize("revision", list(BASES))
def test_flag_off_matches_the_unconfigured_deck_in_process(revision):
    """Hash-seed independent: in one process, any knobs with the flag off, and default
    knobs with it on, give the deck of a config with no knobs at all."""
    flag(False)
    plain = digest(*generate(revision, "synthetic"))
    for arm in ARMS:
        assert digest(*generate(revision, "synthetic", knobs(arm))) == plain
    flag(True)
    assert digest(*generate(revision, "synthetic", dict(fx.DEFAULTS))) == plain
    assert digest(*generate(revision, "synthetic", knobs("C"))) != plain


@pytest.mark.parametrize("extra", [None, dict(fx.DEFAULTS)], ids=["absent", "defaults"])
@pytest.mark.parametrize("revision,world", sorted(GOLDEN))
def test_flag_on_default_knobs_are_byte_identical_to_main(revision, world, extra):
    flag(True)
    assert digest(*generate(revision, world, extra)) == GOLDEN[revision, world]


def _formula_ratio(arm, card, args):
    k = knobs(arm)
    cval = ts.make_consensus_value_fn(args["seed_elo"], args["players"])
    sides = []
    for ids in (card.give_player_ids, card.receive_player_ids):
        raws = [fx.raw_value(ts, args["seed_elo"][p], args["players"][p]) for p in ids]
        sides.append(fx.side_value(k, [cval(p) for p in ids], raws))
    return min(sides) / max(sides)


@pytest.mark.parametrize("arm", list(ARMS))
def test_flag_on_formula_admits_on_its_own_ratio(arm):
    flag(True)
    args = synthetic()
    cards, _ = r4.generate_bilateral_trades(**args, config=knobs(arm))
    today, _ = r4.generate_bilateral_trades(**args)
    assert cards and digest(cards, _) != GOLDEN["r4", "synthetic"]
    assert {(c.target_user_id, tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in cards} != \
        {(c.target_user_id, tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in today}
    bar = fx.floor(knobs(arm), .75, ts._DEFAULT_CFG["market_floor_absolute"])
    for card in cards:
        market = card.owner_evaluation.as_dict()["market"]
        assert card.fairness_score == market["ratio"] == market["formula"]["ratio"] >= bar - 1e-9
        assert card.fairness_score == pytest.approx(_formula_ratio(arm, card, args), rel=1e-9)
        # The shown side values stay today's package values.
        assert (card.give_value, card.receive_value) == (market["give"], market["receive"])
        assert market["formula"]["package_ratio"] == pytest.approx(
            min(card.give_value, card.receive_value) / max(card.give_value, card.receive_value))
    # Proofs revalidate under the same formula.
    for card, final in zip(cards, r4.evaluate_bilateral_trades(cards, **args, config=knobs(arm))):
        assert final.eligible and final.matches(card)


def test_formula_floor_refuses_below_the_bar():
    """Arm B's 0.8176 bar refuses an A card between 0.75 and 0.8176."""
    flag(True)
    args = synthetic()
    a_cards, _ = r4.generate_bilateral_trades(**args, config=knobs("A"))
    b_cards, _ = r4.generate_bilateral_trades(**args, config=knobs("B"))
    between = [c for c in a_cards if c.fairness_score < .8176]
    assert between, "fixture must hold an A card under B's bar"
    b_keys = {(tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in b_cards}
    assert all((tuple(c.give_player_ids), tuple(c.receive_player_ids)) not in b_keys for c in between)
    assert all(c.fairness_score >= .8176 - 1e-9 for c in b_cards)


# ── the request hash ───────────────────────────────────────────────────────

def test_request_hash_ignores_the_knobs_unless_a_formula_is_active(owner_harness):  # noqa: F811
    from backend import server
    context = context_for(owner_harness)
    flag(False)
    for key in fx.KNOBS:
        context["config"].pop(key, None)
    original = server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]
    for extra in (dict(fx.DEFAULTS), knobs("A")):
        context["config"].update(extra)
        assert server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"] == original
    flag(True)
    context["config"].update(fx.DEFAULTS)
    assert server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"] == original
    context["config"].update(knobs("A"))
    assert server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"] != original


# ── the replay tool and its rule ───────────────────────────────────────────

@pytest.fixture(scope="module")
def eng():
    import socket
    saved = socket.socket.connect, socket.create_connection
    try:
        yield replay.load_engine(under_pytest=True)
    finally:
        socket.socket.connect, socket.create_connection = saved


def test_replay_builds_every_arm_and_finds_a_real_trade(eng):
    flag(False)                                   # the replay pins arms itself
    case = _synthetic_case()
    kwargs, meta = window_replay._inputs(case, eng)
    with fx.override(knobs("C")):
        cards, _ = eng[1].generate_bilateral_trades(fairness_threshold=.75, **kwargs)
    target = next(c for c in cards if c.target_user_id == "t1")
    rank = cards.index(target) + 1
    case["real_give"] = [{"token": meta[p][1], "value": meta[p][2]} for p in target.give_player_ids]
    case["real_receive"] = [{"token": meta[p][1], "value": meta[p][2]} for p in target.receive_player_ids]
    out = replay.replay_case(case, eng)
    assert list(out) == ["T", "A", "B", "C", "D"]
    assert out["C"]["exact_rank"] == rank and out["C"]["close_rank"] <= rank
    assert out["C"]["n_cards"] != out["T"]["n_cards"]
    # T is today's deck: the fairness-window tool at 0.75 builds the same first 30.
    assert out["T"]["deck"] == window_replay.replay_case(case, eng, thresholds=(.75,))["0.75"]["deck"]
    for v in out.values():
        assert v["first30_under_today"] <= v["first30_n"] <= replay.FIRST_PAGE
    assert out["T"]["first30_under_today"] == 0
    assert not replay.involves_pick(case) or any(
        a["token"].startswith("P:") for a in case["real_give"] + case["real_receive"])


def test_involves_pick():
    case = {"real_give": [{"token": "123"}], "real_receive": [{"token": "P:2027:1"}]}
    assert replay.involves_pick(case)
    assert not replay.involves_pick({"real_give": [{"token": "1"}], "real_receive": [{"token": "2"}]})


def _rows(winners, n=60, pick_loss=(), slow=()):
    """T hits every third trade; each winner also hits i % 3 == 1. A `pick_loss` arm hits
    nothing on pick trades and every non-pick trade; `slow` arms take 1.2x."""
    rows = []
    for i in range(n):
        pick = i % 2 == 0
        by = {}
        for arm in replay.ARMS:
            if arm in pick_loss:
                hit = not pick
            else:
                hit = i % 3 == 0 or (arm in winners and i % 3 == 1)
            by[arm] = {"n_cards": 10, "secs": 1.2 if arm in slow else 1.0, "close_rank": 1 if hit else None,
                       "exact_rank": None, "first30_n": 10, "first30_under_today": 0, "deck": []}
        rows.append({"lineage": "L%d" % (i % (n // 2)), "pick": pick, "by_arm": by})
    return rows


def test_rule_ties_go_to_the_arm_closest_to_today():
    res = replay.summarise(_rows({"A", "B", "C", "D"}), draws=200)
    assert res["selection"]["passed"] == ["A", "B", "C", "D"]
    assert res["selection"]["adopted"] == "C"
    res = replay.summarise(_rows({"A", "B", "D"}), draws=200)
    assert res["selection"]["adopted"] == "B"


def test_rule_keeps_today_when_nothing_gains():
    res = replay.summarise(_rows(set()), draws=200)
    assert res["selection"] == {"adopted": "T", "passed": [],
                                "reason": "no arm passed; the knobs stay at today's math"}


def test_rule_refuses_a_slow_arm():
    res = replay.summarise(_rows({"A", "D"}, slow={"A"}), draws=200)
    assert res["selection"]["passed"] == ["D"] and res["selection"]["adopted"] == "D"


def test_rule_refuses_an_arm_that_loses_pick_trades():
    rows = _rows({"A"}, n=300, pick_loss={"C"})
    # C gains overall (every non-pick trade) but loses every pick-trade T hit.
    res = replay.summarise(rows, draws=200)
    c = next(r for r in res["table"] if r["arm"] == "C")
    assert c["gain_close_first30_vs_T"]["ci95"][0] > 0 and c["pick"]["gain_vs_T"]["ci95"][1] < 0
    assert res["selection"]["passed"] == ["A"] and res["selection"]["adopted"] == "A"


def test_summary_carries_every_reported_measure():
    res = replay.summarise(_rows({"A"}), draws=50)
    row = next(r for r in res["table"] if r["arm"] == "A")
    for key in ("close_first30", "gain_close_first30_vs_T", "close_anywhere", "exact_first30",
                "first30_share_under_075_today", "median_deck_size", "median_time_ratio_vs_T"):
        assert key in row
    assert row["pick"]["n_trades"] + row["no_pick"]["n_trades"] == res["n_trades"] == 60


def test_replay_tool_never_imports_the_server_module():
    import re
    src = (REPO / "backend/eval/fairness_formula_replay.py").read_text()
    imports = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    assert imports and not any("server" in l for l in imports)


def test_page_first_search_declines_an_active_formula():
    """trade_first_page bounds today's package math; an active formula falls back to the full solve."""
    from backend import trade_first_page as tfp
    flag(True)
    search = r4._GenerationSearch(**synthetic(), config=knobs("C"))
    with pytest.raises(tfp.Unsupported) as err:
        tfp._Bounds(search)
    assert err.value.reason == "fairness_formula"
    flag(False)
    tfp._Bounds(r4._GenerationSearch(**synthetic(), config=knobs("C")))     # today: no refusal
