"""DEC-2 (a) prototype: golden round trip for backend/eval/evidence_pack.py.

Spec: docs/plans/org-bringup/leads/models-lead-launch.md §DEC-2 "Confirmation"
§1 and §4; C7 (ii) is the bar: every registered scorer's output and replay's
estimates are bit-identical between the full and the packed form.

Decks: real trade jobs (bakeoff_harness), a 1,200-card deck through the real
impression writer, the F8 synthetic log (multi-deck, with outcomes), and
hand-built edge cards (duplicate positions with no taste_attrs, shape absent
with shape_bucket present, None values, absent keys, gapped card_index).
"""

import json
import random
import struct
import zlib
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import patch

import pytest

import backend.value_model as vm
from backend.eval import evidence_pack as ep
from backend.eval.data import LoggedCard, LoggedDeck, card_dict, load_decks
from backend.eval.replay import evaluate
from backend.eval.scorers import get_scorer, registered_names
from backend.eval.synth import build_synthetic_db
from backend.taste_service import attrs_from_features
from backend.tests.support import evidence_pack_decks as D

LOGGED = ("impression_id", "deck_job_id", "user_id", "league_id", "card_index",
          "trade_hash", "propensity", "base_score", "final_score", "archetype",
          "shape_bucket", "served_at")
INJECTED = {vm.K_PREF_LONG, vm.K_PREF_SHORT, vm.K_PARTNER_RATE, vm.K_POSITION}
FIXED_NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _stub_pref_match(self, user_id, attrs):
    """Fixed taste prefs: any change to the attribute list moves the value."""
    if not user_id or not attrs:
        return 0.0, 0.0
    h = sha256("|".join(attrs).encode()).digest()
    return h[0] / 127.5 - 1.0, h[1] / 127.5 - 1.0


@pytest.fixture(autouse=True)
def _fixed_taste():
    with patch.object(vm._TasteCache, "pref_match", _stub_pref_match):
        yield


def _edge_cards():
    shared = {"user_id": "user_me", "league_id": "league_edge", "deck_job_id": "job-edge",
              "served_at": "2026-10-20T00:00:00+00:00", "candidate_set_id": None,
              "candidate_set_size": None, "ranked_player_count": 12,
              "user_value_basis": "personal", "last_board_update_at": None,
              "impression_id": "dropped-by-the-pack", "need_fit": 0.4}
    return [
        {**shared, "card_index": 30, "trade_hash": "00ff00ff00ff00ff", "shape": "2x1",
         "shape_bucket": "2x1", "lane": "value", "archetype": "value", "basis": "consensus",
         "give_positions": ["WR", "WR"], "receive_positions": ["RB"],
         "give_value": 4000.0, "receive_value": 2100.5, "surplus_margin": 12.5,
         "fairness_score": 0.91, "likes_you": False, "relaxed": False, "involves_pick": False,
         "partner_user_id": "user_opp", "propensity": 1.25, "base_score": 0.5,
         "final_score": 0.625, "model_arm": "current", "arm_rank": 0},
        {**shared, "card_index": 31, "trade_hash": None, "shape_bucket": "2x1",
         "lane": None, "archetype": "value", "basis": "divergence",
         "give_positions": ["QB", "TE"], "receive_positions": ["WR"],
         "give_value": 4500, "receive_value": None, "fairness_score": None,
         "likes_you": False, "involves_pick": False, "partner_user_id": "user_opp2",
         "taste_attrs": None, "propensity": 1.0, "base_score": 0.4, "final_score": 0.4},
        {**shared, "card_index": 33, "trade_hash": "0123456789abcdef", "shape": "4x0",
         "shape_bucket": "4x0", "lane": "window", "archetype": "window",
         "give_positions": ["PICK", "?", "RB", "RB"], "receive_positions": [],
         "give_value": 9000.0, "receive_value": 0.0, "surplus_margin": -3.0,
         "fairness_score": -0.0, "likes_you": True, "involves_pick": True,
         "partner_user_id": None, "taste_attrs": [], "propensity": 0.75,
         "base_score": 0.2, "model_arm": None, "arm_rank": None},
        {**shared, "card_index": 40, "trade_hash": "fedcba9876543210", "shape": "1x1",
         "shape_bucket": "1x1", "lane": "outlook", "archetype": "outlook",
         "give_positions": ["RB"], "receive_positions": ["WR"],
         "give_value": 1234.5, "receive_value": 1300.25, "surplus_margin": 1e-9,
         "fairness_score": 0.5, "likes_you": False, "relaxed": True, "involves_pick": False,
         "partner_user_id": "user_opp", "propensity": 1.5, "base_score": 0.1,
         "final_score": 0.15, "taste_attrs": ["arch:outlook", "givepos:RB", "recvpos:WR"],
         "group_key": "current_value", "group_rank": 40000, "lane_slot": "value",
         "fairness_threshold": 0.8, "centerpiece_id": "rb7", "policy_version": "v3/bo:current"},
    ]


def _legacy_cards():
    """Rows from before the board-state amendment: no per-run board keys at all."""
    base = {"user_id": "user_old", "league_id": "league_old", "deck_job_id": "job-old",
            "served_at": "2026-07-01T00:00:00+00:00", "propensity": 1.0,
            "shape": "1x1", "shape_bucket": "1x1", "lane": "value", "archetype": "value",
            "give_positions": ["WR"], "receive_positions": ["WR"],
            "give_value": 2000.0, "receive_value": 2050.0}
    return [{**base, "card_index": i, "base_score": 1.0 - i / 10,
             "final_score": 1.0 - i / 10, "trade_hash": f"{i:016x}"} for i in range(5)]


def _with_outcomes(deck, seed):
    rng = random.Random(seed)
    for c in deck.cards:
        c.viewed = c.card_index < 40 or rng.random() < 0.05
        if c.viewed:
            c.liked = rng.random() < 0.3
            c.passed = not c.liked
            c.proposed = c.liked and rng.random() < 0.3
    return deck


@pytest.fixture(scope="module")
def harness():
    return D.harness_decks()


@pytest.fixture(scope="module")
def writer():
    with D.hermetic_values():
        deck, cards = D.writer_deck(1200, seed=3)
    return _with_outcomes(deck, seed=3), cards


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('evpack') / 'synth.db'}"
    build_synthetic_db(url, n_decks=40, cards_per_deck=8, seed=11)
    return [(deck, [card_dict(c) for c in deck.cards]) for deck in load_decks(db_url=url)]


def _all_decks(harness, writer, synth):
    return [d for decks in harness.values() for d in decks] + [writer] + synth


def _round_trip(cards, run=None):
    packed = ep.pack_run(run or {"values_snapshot_id": 7}, cards)
    out_run, out = ep.unpack_run(packed)
    assert out_run == (run or {"values_snapshot_id": 7})
    return out


def _rt_deck(deck, unpacked):
    """What C7 (i)'s reader rebuilds: a LoggedDeck from the unpacked cards only
    (outcomes are not part of the pack, so they are copied over)."""
    cards = []
    for orig, u in zip(deck.cards, unpacked):
        features = {k: v for k, v in u.items()
                    if k not in LOGGED and k not in D.ATTRIBUTION_COLUMNS}
        cards.append(LoggedCard(
            impression_id=f"{u['deck_job_id']}:{u['card_index']}",
            deck_job_id=u["deck_job_id"], user_id=u["user_id"], league_id=u["league_id"],
            card_index=u["card_index"], trade_hash=u.get("trade_hash"),
            propensity=u.get("propensity"), base_score=u.get("base_score"),
            final_score=u.get("final_score"), archetype=u.get("archetype"),
            shape_bucket=u.get("shape_bucket"), served_at=u["served_at"],
            features=features, viewed=orig.viewed, liked=orig.liked, passed=orig.passed,
            proposed=orig.proposed, not_interested=orig.not_interested,
            undone=orig.undone, dwell_ms=orig.dwell_ms))
    return replace(deck, served_at=unpacked[0]["served_at"], cards=cards)


def _fixed_model(cards):
    partners = sorted({str(c.get("partner_user_id")) for c in cards})
    return vm.ValueModel(
        like_head=vm.LogisticHead(), propose_head=None, propose_constant=0.1,
        partner_rates={f"{c.get('user_id')}|{p}": (i + 1) / (len(partners) + 2)
                       for c in cards[:1] for i, p in enumerate(partners)},
        global_like_rate=0.2, position_mean=0.3, trained_at="fixed", train_date="fixed")


def _bits(xs):
    return [struct.pack("<d", float(x)).hex() for x in xs]


def assert_golden(orig, rt, model):
    """(a) and (b) per card, (c) per scorer over the deck, then (d) per card."""
    assert len(orig) == len(rt)
    fixed = _fixed_model(orig)
    for o, u in zip(orig, rt):
        assert (vm.extract_features(fixed._inject(u, u.get("user_id")))
                == vm.extract_features(fixed._inject(o, o.get("user_id"))))  # (a)
        assert attrs_from_features(u) == attrs_from_features(o)            # (b)
        u_bare = {k: v for k, v in u.items() if k != "taste_attrs"}
        o_bare = {k: v for k, v in o.items() if k != "taste_attrs"}
        assert attrs_from_features(u_bare) == attrs_from_features(o_bare)
    for name in registered_names():                                         # (c)
        with patch.object(vm, "load_latest_model", lambda: model):
            s_o, s_u = get_scorer(name, seed=5), get_scorer(name, seed=5)
            assert _bits(s_o.score(c) for c in orig) == _bits(s_u.score(c) for c in rt), name
    for o, u in zip(orig, rt):
        proj = {k: v for k, v in o.items() if k in ep.CONTRACT_KEYS}
        assert u == proj                                                    # (d)
        assert json.dumps(u, sort_keys=True) == json.dumps(proj, sort_keys=True)


@pytest.fixture(scope="module")
def trained(harness, writer, synth):
    decks = [d for d, _ in _all_decks(harness, writer, synth)]
    with patch.object(vm._TasteCache, "pref_match", _stub_pref_match):
        model = vm.train_model(decks, now=FIXED_NOW)
    assert model is not None and model.propose_head is not None
    return model


# ---------------------------------------------------------------------------
# Golden
# ---------------------------------------------------------------------------

def test_harness_decks_round_trip_exactly(harness, trained):
    seen = set()
    for name, decks in harness.items():
        assert decks, name
        for deck, cards in decks:
            seen.update(k for c in cards for k in c)
            assert_golden(cards, _round_trip(cards), trained)
    assert {"taste_attrs", "model_arm", "group_key", "centerpiece_id",
            "candidate_set_id"} <= seen


def test_writer_deck_round_trips_exactly(writer, trained):
    _deck, cards = writer
    assert len(cards) == 1200 and any(len(c["give_positions"]) != len(set(c["give_positions"]))
                                      for c in cards)
    assert_golden(cards, _round_trip(cards), trained)


def test_edge_and_legacy_cards_round_trip_exactly(trained):
    for cards in (_edge_cards(), _legacy_cards()):
        rt = _round_trip(cards)
        assert_golden(cards, rt, trained)
    rt = _round_trip(_edge_cards())
    assert rt[0]["give_positions"] == ["WR", "WR"] and "taste_attrs" not in rt[0]
    assert "shape" not in rt[1] and rt[1]["shape_bucket"] == "2x1"
    assert rt[1]["trade_hash"] is None and "surplus_margin" not in rt[1]
    assert type(rt[1]["give_value"]) is int and rt[2]["taste_attrs"] == []
    assert struct.pack("<d", rt[2]["fairness_score"]) == struct.pack("<d", -0.0)
    assert "impression_id" not in rt[0] and "need_fit" not in rt[0]
    assert [c["card_index"] for c in rt] == [30, 31, 33, 40]


def test_replay_estimates_and_value_model_fit_are_bit_identical(harness, writer, synth,
                                                                 trained):
    decks = _all_decks(harness, writer, synth)
    orig = [d for d, _ in decks]
    rt = [_rt_deck(d, _round_trip(cards)) for d, cards in decks]
    refit = vm.train_model(rt, now=FIXED_NOW)
    assert refit.to_dict() == trained.to_dict()
    for name in registered_names():
        with patch.object(vm, "load_latest_model", lambda: trained):
            run_o = evaluate(get_scorer(name, seed=5), orig, bootstrap=200, seed=1)
            run_u = evaluate(get_scorer(name, seed=5), rt, bootstrap=200, seed=1)
        assert run_o.n_included > 0 and repr(run_o) == repr(run_u), name


def test_contract_covers_every_key_the_scorers_read(writer, trained):
    class Recorder(dict):
        read: set = set()

        def get(self, k, default=None):
            Recorder.read.add(k)
            return super().get(k, default)

        def __getitem__(self, k):
            Recorder.read.add(k)
            return super().__getitem__(k)

    _deck, cards = writer
    variants = [cards[0], *_edge_cards()]
    for c in variants:
        for card in (Recorder(c), Recorder({k: v for k, v in c.items() if k != "taste_attrs"})):
            vm.extract_features(card)
            attrs_from_features(card)
            trained._inject(card, card.get("user_id"))
            trained.rank_score_from_card(card)
            for name in ("logged", "production", "base_score", "random"):
                get_scorer(name).score(card)
    assert {"shape_bucket", "archetype", "partner_user_id", "taste_attrs"} <= Recorder.read
    assert Recorder.read - INJECTED <= ep.CONTRACT_KEYS


# ---------------------------------------------------------------------------
# Integrity and refusals
# ---------------------------------------------------------------------------

def test_a_flipped_byte_anywhere_is_refused(writer):
    _deck, cards = writer
    packed = ep.pack_run({}, cards[:200])
    blob = bytearray(packed.blob)
    blob[len(blob) // 2] ^= 0x01
    with pytest.raises(ep.PackIntegrityError):
        ep.unpack_run(replace(packed, blob=bytes(blob)))
    # Flips that still decode: one taste_attrs token on the last card, one
    # partner id in the header dictionary, the checksum itself.
    raw = bytearray(zlib.decompress(packed.blob))
    raw[-1] ^= 0x01
    header = packed.header_json.replace('"user_01"', '"user_99"')
    assert header != packed.header_json
    for bad in (replace(packed, blob=zlib.compress(bytes(raw))),
                replace(packed, header_json=header),
                replace(packed, checksum="0" * 64)):
        with pytest.raises(ep.PackIntegrityError, match="checksum mismatch"):
            ep.unpack_run(bad)


def test_unknown_pack_version_is_refused():
    packed = ep.pack_run({}, _legacy_cards())
    head = json.loads(packed.header_json)
    head["pack_version"] = ep.PACK_VERSION + 1
    with pytest.raises(ep.PackIntegrityError, match="unknown pack_version"):
        ep.unpack_run(replace(packed, header_json=json.dumps(head)))


@pytest.mark.parametrize("mutate, message", [
    (lambda cs: cs[1].update(served_at="2026-07-02T00:00:00+00:00"), "not constant"),
    (lambda cs: cs[1].pop("user_id"), "not constant"),
    (lambda cs: cs[1].update(is_ghost=1), "ghost"),
    (lambda cs: cs[1].update(taste_attrs=["b", "a"]), "sorted list"),
    (lambda cs: cs[1].update(trade_hash="ABCDEF0123456789"), "lowercase hex"),
    (lambda cs: cs[1].update(give_value=True), "cannot pack bool"),
    (lambda cs: cs[1].update(card_index=0), "strictly increasing"),
])
def test_cards_that_cannot_pack_exactly_are_refused(mutate, message):
    cards = _legacy_cards()
    mutate(cards)
    with pytest.raises(ValueError, match=message):
        ep.pack_run({}, cards)
