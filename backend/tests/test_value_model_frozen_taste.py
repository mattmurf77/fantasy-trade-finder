"""R4.1: value_model's fits and evals read the serve-time taste matches frozen
on each card (taste_pref_long / taste_pref_short), never live taste state, and
a fit takes an explicit as_of (models-lead-launch §Reviews-4 R4.1).

  (i)   a re-fit at the same as_of is bit-identical after the clock moves, new
        outcomes arrive, a board prior is rewritten and taste rows are GC'd:
        the coefficients, value_model's calibration table and every
        registered scorer's replay estimates;
  (ii)  mutating taste rows after serve changes no eval score, and no fit or
        eval path reads taste state at all;
  (iii) parity: the frozen values equal what taste_multipliers used, through
        backend/tests/support/taste_parity.py (trades-eng's writer test uses
        the same helper);
  (iv)  the packed/full golden with the two fields is in test_evidence_pack.py.
Live serving (serving_scores) is the one path that still reads taste.
"""

import json
import math
import struct
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select, update

import backend.database as db_module
import backend.taste_service as taste_service
import backend.value_model as vm
from backend.database import (
    deck_impressions_table, deck_outcomes_table, metadata, replace_user_taste_prior,
    replace_user_taste_rows, user_taste_table,
)
from backend.eval.calibration import calibration_pairs, reliability_table
from backend.eval.data import card_dict, load_decks
from backend.eval.replay import evaluate
from backend.eval.scorers import get_scorer, registered_names
from backend.eval.synth import build_synthetic_db
from backend.ranking_service import Player
from backend.tests.support import taste_parity
from backend.trade_service import TradeCard

USERS = [f"user{u}" for u in range(6)]     # build_synthetic_db's users
ME = "user_me"


def _clock(at: datetime):
    """taste_service's datetime with now() pinned to `at`."""
    class _Pinned(datetime):
        @classmethod
        def now(cls, tz=None):
            return at
    return _Pinned


@contextmanager
def _taste_reads():
    """Records every live taste read (load_taste_vectors) made inside."""
    calls, real = [], taste_service.load_taste_vectors
    with patch.object(taste_service, "load_taste_vectors",
                      lambda uid: calls.append(uid) or real(uid)):
        yield calls


def _bits(xs):
    return [struct.pack("<d", float(x)).hex() for x in xs]


# ---------------------------------------------------------------------------
# A served corpus with frozen taste matches, and live taste state beside it
# ---------------------------------------------------------------------------

def _freeze_serve_time_prefs(url):
    """The writer's job, done here: every card's taste_attrs and, for 4 decks
    in 5, the prefMatch pair the taste layer computed at serve (the 5th ran
    without the layer: the pair is absent)."""
    eng = create_engine(url)
    imp = deck_impressions_table
    vectors = {}
    with eng.begin() as conn:
        for r in conn.execute(select(imp.c.impression_id, imp.c.user_id,
                                     imp.c.deck_job_id, imp.c.features_json)).fetchall():
            f = json.loads(r.features_json)
            f["taste_attrs"] = taste_service.attrs_from_features(f)
            if int(r.deck_job_id[-4:]) % 5:
                if r.user_id not in vectors:
                    vectors[r.user_id] = taste_service.load_taste_vectors(r.user_id)
                short, long_ = vectors[r.user_id]
                f[vm.K_TASTE_PREF_LONG] = taste_service._pref_match(long_, f["taste_attrs"])
                f[vm.K_TASTE_PREF_SHORT] = taste_service._pref_match(short, f["taste_attrs"])
            conn.execute(update(imp).where(imp.c.impression_id == r.impression_id)
                         .values(features_json=json.dumps(f)))
    eng.dispose()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    taste = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(taste)
    monkeypatch.setattr(db_module, "engine", taste)
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path / "vm"))
    monkeypatch.setattr(vm, "_model_cache", None)
    as_of = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=1)
    learned_at = (as_of - timedelta(days=2)).isoformat()
    with taste.begin() as conn:
        conn.execute(insert(user_taste_table), [
            *({"user_id": u, "attr": f"prior:{a}", "w_short": 0.0, "w_long": w + i / 10,
               "updated_at": learned_at}
              for i, u in enumerate(USERS)
              for a, w in (("partner:opp1", 1.5), ("shape:2x1", -0.8), ("arch:window", 0.6))),
            *({"user_id": u, "attr": a, "w_short": ws, "w_long": wl, "updated_at": learned_at}
              for u in USERS
              for a, ws, wl in (("recvpos:WR", 1.2, 0.9), ("partner:opp2", -1.0, -0.4))),
        ])
    url = f"sqlite:///{tmp_path / 'decks.db'}"
    build_synthetic_db(url, n_decks=80, seed=29, days_span=20)
    _freeze_serve_time_prefs(url)
    return {"url": url, "as_of": as_of}


def _fit(world):
    decks = load_decks(db_url=world["url"], until=world["as_of"].isoformat())
    return decks, vm.train_model(decks, as_of=world["as_of"])


def _readout(decks, model):
    """Every registered scorer's replay estimates, and value_model's
    calibration table, with `model` as the persisted model."""
    with patch.object(vm, "load_latest_model",
                      lambda: vm.ValueModel.from_dict(model.to_dict())):
        runs = {name: repr(evaluate(get_scorer(name, seed=4), decks, bootstrap=100, seed=6))
                for name in registered_names()}
        pairs, _excluded = calibration_pairs(get_scorer("value_model"), decks)
    table = [(r.n, r.mean_predicted, r.observed_rate) for r in reliability_table(pairs)]
    return runs, table


def _mutate_taste_state(world, monkeypatch) -> datetime:
    """After the fit: the clock moves 40 days, a deck served after as_of gets
    outcomes (and the taste updates they cause), every board prior is
    rewritten, and a decayed learned row is GC'd by a live read."""
    later = world["as_of"] + timedelta(days=40)
    replace_user_taste_rows("user0", {"givepos:RB": (0.06, 0.06,
                                                     (later - timedelta(days=400)).isoformat())})
    eng = create_engine(world["url"])
    with eng.begin() as conn:
        conn.execute(insert(deck_impressions_table).values(
            impression_id="late-0", user_id="user1", league_id="league_synth",
            deck_job_id="late", card_index=0, features_json=json.dumps(
                {"shape": "2x1", "partner_user_id": "opp1", vm.K_TASTE_PREF_LONG: 0.9}),
            propensity=1.0, base_score=1.0, final_score=1.0, shape_bucket="2x1",
            served_at=(world["as_of"] + timedelta(hours=1)).isoformat()))
        conn.execute(insert(deck_outcomes_table), [
            {"impression_id": "late-0", "action": a, "acted_at": later.isoformat()}
            for a in ("viewed", "like")])
    eng.dispose()
    for u in USERS:
        replace_user_taste_rows(u, {"recvpos:WR": (3.0, 2.5, later.isoformat()),
                                    "arch:value": (2.0, 1.0, later.isoformat())})
        replace_user_taste_prior(u, {"partner:opp3": 2.0, "shape:1x1": -1.5},
                                 later.isoformat())
    monkeypatch.setattr(taste_service, "datetime", _clock(later))
    taste_service.load_taste_vectors("user0")      # a live read GCs the decayed row
    with db_module.engine.connect() as conn:
        assert not conn.execute(select(user_taste_table.c.attr).where(
            user_taste_table.c.attr == "givepos:RB")).fetchall()
    return later


# ---------------------------------------------------------------------------
# (i) and (ii)
# ---------------------------------------------------------------------------

def test_i_refit_at_the_same_as_of_is_bit_identical(world, monkeypatch):
    with _taste_reads() as reads:
        decks_1, model_1 = _fit(world)
        readout_1 = _readout(decks_1, model_1)
    assert reads == []
    assert model_1.like_head.weights.get("pref_long", 0.0) != 0.0     # the frozen prefs matter
    live_before = taste_service.load_taste_vectors("user1")

    _mutate_taste_state(world, monkeypatch)
    assert taste_service.load_taste_vectors("user1") != live_before     # live state moved
    assert len(load_decks(db_url=world["url"])) == len(decks_1) + 1     # new evidence exists

    with _taste_reads() as reads:
        decks_2, model_2 = _fit(world)
        readout_2 = _readout(decks_2, model_2)
    assert reads == []
    assert model_2.to_dict() == model_1.to_dict()
    assert readout_2 == readout_1


def test_ii_taste_mutated_after_serve_changes_no_eval_score(world, monkeypatch):
    decks, model = _fit(world)

    def scores():
        with patch.object(vm, "load_latest_model",
                          lambda: vm.ValueModel.from_dict(model.to_dict())):
            scorer = get_scorer("value_model")
            return _bits(scorer.score(card_dict(c)) for d in decks for c in d.cards)

    before = scores()
    _mutate_taste_state(world, monkeypatch)
    with _taste_reads() as reads:
        after = scores()
    assert reads == [] and after == before


# ---------------------------------------------------------------------------
# (iii) parity with taste_multipliers, and live serving
# ---------------------------------------------------------------------------

AT = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@pytest.fixture()
def parity_deck(monkeypatch):
    """A live deck for ME, with learned (decaying) and prior taste rows, on a
    pinned taste clock so two reads see one state."""
    taste = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(taste)
    monkeypatch.setattr(db_module, "engine", taste)
    monkeypatch.setattr(taste_service, "datetime", _clock(AT))
    with taste.begin() as conn:
        conn.execute(insert(user_taste_table), [
            {"user_id": ME, "attr": a, "w_short": ws, "w_long": wl,
             "updated_at": (AT - timedelta(days=d)).isoformat()}
            for a, ws, wl, d in (("recvpos:WR", 1.4, 0.7, 3), ("arch:value", -0.6, 0.5, 9),
                                 ("partner:opp1", 0.9, 1.1, 1), ("prior:cpos:QB", 0.0, 0.8, 0))])
    players = {pid: Player(id=pid, name=pid, position=pos, team="T", age=age)
               for pid, pos, age in (("qb1", "QB", 27), ("rb1", "RB", 23), ("wr1", "WR", 25),
                                     ("wr2", "WR", 30), ("te1", "TE", 24))}
    seed = {"qb1": 1700.0, "rb1": 1650.0, "wr1": 1600.0, "wr2": 1450.0, "te1": 1500.0}
    cards = []
    for i, (give, recv, partner, lane) in enumerate((
            (["rb1"], ["wr1"], "opp1", "value"), (["qb1"], ["wr1", "te1"], "opp2", "window"),
            (["wr2"], ["rb1"], "opp1", None), (["te1", "wr2"], ["qb1"], "opp3", "value"))):
        card = TradeCard(trade_id=f"t{i}", league_id="lg", proposing_user_id=ME,
                         target_user_id=partner, target_username="opp",
                         give_player_ids=give, receive_player_ids=recv,
                         mismatch_score=10.0, fairness_score=0.9, composite_score=1.0 - i / 10)
        card.lane = lane
        cards.append(card)
    return cards, players, seed


def test_iii_frozen_prefs_match_what_taste_multipliers_used(parity_deck):
    cards, players, seed = parity_deck
    kw = {"user_id": ME, "players_dict": players, "seed_map": seed}
    mults = taste_service.taste_multipliers(cards, **kw)
    assert mults is not None and len(set(mults.values())) > 1
    ref = taste_parity.serve_time_prefs(cards, **kw)
    frozen = {id(c): {vm.K_TASTE_PREF_LONG: ref[id(c)][0], vm.K_TASTE_PREF_SHORT: ref[id(c)][1]}
              for c in cards}
    taste_parity.assert_frozen_prefs_match_multipliers(cards, frozen, mults, **kw)

    c0 = id(cards[0])
    pl, ps = ref[c0]
    assert pl != ps
    for bad in ({vm.K_TASTE_PREF_LONG: ps, vm.K_TASTE_PREF_SHORT: pl},           # swapped
                {vm.K_TASTE_PREF_LONG: math.nextafter(pl, math.inf),
                 vm.K_TASTE_PREF_SHORT: ps},                                     # 1 ulp off
                {}):                                                             # not frozen
        with pytest.raises(AssertionError):
            taste_parity.assert_frozen_prefs_match_multipliers(
                cards, {**frozen, c0: bad}, mults, **kw)


def test_iii_no_taste_signal_means_the_prefs_are_absent(parity_deck):
    cards, players, seed = parity_deck
    kw = {"user_id": "nobody", "players_dict": players, "seed_map": seed}
    assert taste_service.taste_multipliers(cards, **kw) is None
    taste_parity.assert_frozen_prefs_match_multipliers(
        cards, {id(c): {} for c in cards}, None, **kw)
    with pytest.raises(AssertionError):
        taste_parity.assert_frozen_prefs_match_multipliers(
            cards, {id(c): {vm.K_TASTE_PREF_LONG: 0.0, vm.K_TASTE_PREF_SHORT: 0.0}
                    for c in cards}, None, **kw)


def test_live_serving_alone_reads_taste(parity_deck, monkeypatch):
    cards, players, seed = parity_deck
    model = vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.3, "pref_long": 1.2, "pref_short": -0.7}),
        propose_head=None, propose_constant=0.2, partner_rates={}, global_like_rate=0.3,
        position_mean=0.4, trained_at="t", train_date="t")
    monkeypatch.setattr(vm, "load_latest_model", lambda: model)
    monkeypatch.setattr(vm, "user_has_outcome_history", lambda uid: True)
    with _taste_reads() as reads:
        scores = vm.serving_scores(cards, user_id=ME, league_id="lg",
                                   players_dict=players, seed_map=seed)
    assert reads == [ME]
    ref = taste_parity.serve_time_prefs(cards, user_id=ME, players_dict=players, seed_map=seed)
    for c in cards:
        f = {**vm.card_features(c, players, seed), vm.K_TASTE_PREF_LONG: ref[id(c)][0],
             vm.K_TASTE_PREF_SHORT: ref[id(c)][1]}
        assert scores[id(c)] == model.rank_score(f, ME)
