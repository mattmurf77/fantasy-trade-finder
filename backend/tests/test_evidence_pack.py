"""ADR-025 C1 / C7: golden round trip for backend/eval/evidence_pack.py, and
the C7 (ii) golden end to end through the DB and backend.eval.data.load_decks.

Spec: docs/plans/org-bringup/leads/models-lead-launch.md §DEC-2 "Confirmation"
§1 and §4, and §Reviews-2 R2.2; C7 (ii) is the bar: every registered scorer's
output and replay's estimates are bit-identical between the full and the
packed form.

Decks: real trade jobs (bakeoff_harness), a 1,200-card deck through the real
impression writer, the F8 synthetic log (multi-deck, with outcomes), and
hand-built edge cards (duplicate positions with no taste_attrs, shape absent
with shape_bucket present, None values, absent keys, gapped card_index).
"""

import json
import math
import random
import struct
import zlib
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import patch

import pytest
from sqlalchemy import insert

import backend.value_model as vm
from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval import contract as C
from backend.eval import evidence_pack as ep
from backend.eval.data import LoggedCard, LoggedDeck, card_dict, load_decks
from backend.eval.replay import evaluate
from backend.eval.scorers import get_scorer, registered_names
from backend.eval.synth import build_synthetic_db
from backend.taste_service import attrs_from_features
from backend.tests.support import evidence_pack_decks as D
from backend.tests.test_eval_pack_reader import insert_pack, make_engine

LOGGED = ("impression_id", "deck_job_id", "user_id", "league_id", "card_index",
          "trade_hash", "propensity", "base_score", "final_score", "archetype",
          "shape_bucket", "served_at")
INJECTED = {vm.K_PREF_LONG, vm.K_PREF_SHORT, vm.K_PARTNER_RATE, vm.K_POSITION}
FIXED_NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _no_live_taste(self, user_id, attrs):
    raise AssertionError("a fit or eval read live taste state (R4.1)")


@pytest.fixture(autouse=True)
def _fixed_taste():
    """Fits and evals read the frozen taste_pref_*; a live read fails here."""
    with patch.object(vm._TasteCache, "pref_match", _no_live_taste):
        yield


def _frozen_prefs(trade_hash: str) -> dict:
    """R4.1: the taste matches the writer freezes per card, as exact float8s
    (derived from the trade hash, so a card keeps its pair across forms)."""
    h = sha256(trade_hash.encode()).digest()
    return {vm.K_TASTE_PREF_LONG: int.from_bytes(h[:8], "little") / 2**63 - 1.0,
            vm.K_TASTE_PREF_SHORT: int.from_bytes(h[8:16], "little") / 2**64 - 0.5}


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
         "final_score": 0.625, "model_arm": "current", "arm_rank": 0,
         "taste_pref_long": -0.0, "taste_pref_short": 5e-324},
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
         "taste_pref_long": 0.6180339887498949, "taste_pref_short": -0.25,
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
    """The 1,200-card writer deck, with the R4.1 frozen taste matches on
    every card (the real writer stamps them once trades-eng ships it)."""
    with D.hermetic_values():
        deck, cards = D.writer_deck(1200, seed=3)
    for c, d in zip(deck.cards, cards):
        prefs = _frozen_prefs(d["trade_hash"])
        c.features.update(prefs)
        d.update(prefs)
    return _with_outcomes(deck, seed=3), cards


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('evpack') / 'synth.db'}"
    build_synthetic_db(url, n_decks=40, cards_per_deck=8, seed=11)
    return [(deck, [card_dict(c) for c in deck.cards]) for deck in load_decks(db_url=url)]


def _all_decks(harness, writer, synth):
    return [d for decks in harness.values() for d in decks] + [writer] + synth


def _count(cards):
    """card_count = the last card_index + 1 (these card lists end the deck)."""
    return cards[-1]["card_index"] + 1 if cards else 0


def _run(cards):
    """Run metadata with the whole deck delivered in one page (R4.2 U1)."""
    n = _count(cards)
    return {"values_snapshot_id": 7,
            "deliveries": [[n - 1, "2026-10-20T00:05:00+00:00"]] if n else []}


def _pack(cards, run=None):
    return ep.pack_run(run if run is not None else _run(cards), cards,
                       card_count=_count(cards))


def _round_trip(cards, run=None):
    run = run if run is not None else _run(cards)
    out_run, out = ep.unpack_run(_pack(cards, run))
    assert out_run == run
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
    model = vm.train_model(decks, as_of=FIXED_NOW)
    assert model is not None and model.propose_head is not None
    assert model.like_head.weights.get("pref_long", 0.0) != 0.0   # the frozen prefs score
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
    assert _bits([rt[0]["taste_pref_long"], rt[0]["taste_pref_short"]]) == \
        _bits([-0.0, 5e-324])                                   # R4.1 fields, exact
    assert "taste_pref_long" not in rt[1] and rt[3]["taste_pref_short"] == -0.25


def test_replay_estimates_and_value_model_fit_are_bit_identical(harness, writer, synth,
                                                                 trained):
    decks = _all_decks(harness, writer, synth)
    orig = [d for d, _ in decks]
    rt = [_rt_deck(d, _round_trip(cards)) for d, cards in decks]
    refit = vm.train_model(rt, as_of=FIXED_NOW)
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


def test_codec_carries_every_key_the_contract_names():
    """C7 (iii) <-> the codec: every key backend/eval/contract.py lets a
    scorer read (the frozen inputs, the identity keys, every PERMITTED_LOGGED
    column) and every logged-policy column replay reads (propensity) is
    carried by the pack. impression_id alone is synthesized by the reader.
    A contract key the codec doesn't carry fails here."""
    required = (C.FROZEN_INPUT_KEYS | C.IDENTITY_KEYS | C.LOGGED_POLICY_KEYS
                | frozenset().union(*C.PERMITTED_LOGGED.values()))
    missing = required - {"impression_id"} - ep.CONTRACT_KEYS
    assert not missing, sorted(missing)


# ---------------------------------------------------------------------------
# Integrity and refusals
# ---------------------------------------------------------------------------

RUN = {"values_snapshot_id": "vsn1:9f2c", "built_at": "2026-10-24T01:02:03+00:00",
       "config_ref": 41, "deliveries": [[49, "2026-10-24T01:10:00+00:00"],
                                        [99, "2026-10-24T01:30:00+00:00"]]}


def _with_header(packed, edit):
    head = json.loads(packed.header_json)
    edit(head)
    return replace(packed, header_json=json.dumps(head, sort_keys=True, separators=(",", ":")),
                   card_count=head["card_count"])


def _flip_last_raw_byte(packed):
    """One taste_attrs token on the last card: still decodes, different card."""
    raw = bytearray(zlib.decompress(packed.cards_blob))
    raw[-1] ^= 0x01
    return replace(packed, cards_blob=zlib.compress(bytes(raw)))


@pytest.mark.parametrize("tamper", [
    lambda p: _with_header(p, lambda h: h["run"].update(values_snapshot_id="vsn1:9f2d")),
    lambda p: _with_header(p, lambda h: h["run"].update(built_at="2026-10-24T01:02:04+00:00")),
    lambda p: _with_header(p, lambda h: h["run"]["deliveries"][1].__setitem__(0, 149)),
    lambda p: _with_header(p, lambda h: h["run"]["deliveries"].pop()),
    lambda p: _with_header(p, lambda h: h["dicts"]["basis"][0][0].__setitem__(0, "x")),
    lambda p: _with_header(p, lambda h: h["dicts"]["basis"].append([["unused"]])),
    lambda p: _with_header(p, lambda h: h["shared"].update(user_id="user_99")),
    lambda p: _with_header(p, lambda h: h.update(card_count=h["card_count"] + 1)),
    _flip_last_raw_byte,
    lambda p: replace(p, checksum="0" * 64),
], ids=["run_snapshot_id", "run_built_at", "run_delivery_boundary", "run_delivery_dropped",
        "dictionary_entry", "unused_dictionary_entry", "shared_field", "card_count", "card",
        "checksum"])
def test_tampering_with_anything_a_reader_acts_on_is_refused(writer, tamper):
    """R2.2 (a): the run metadata (deliveries included, R4.2 U1), every
    header field (an unused dictionary entry changes no decoded card, so
    only header coverage catches it) and every card are under the
    checksum."""
    _deck, cards = writer
    packed = ep.pack_run(RUN, cards[:200], card_count=1200)
    assert len(json.loads(packed.header_json)["dicts"]["basis"]) == 2
    assert ep.unpack_run(packed)[0] == RUN
    bad = tamper(packed)
    assert bad != packed
    with pytest.raises(ep.PackIntegrityError, match="checksum mismatch"):
        ep.unpack_run(bad)


def test_a_flipped_byte_anywhere_is_refused(writer):
    _deck, cards = writer
    packed = _pack(cards[:200])
    blob = bytearray(packed.cards_blob)
    blob[len(blob) // 2] ^= 0x01
    with pytest.raises(ep.PackIntegrityError):
        ep.unpack_run(replace(packed, cards_blob=bytes(blob)))


@pytest.mark.parametrize("deliveries", [
    None, "49", [[49]], [[49, None]], [["49", "t"]], [[True, "t"]], [[-1, "t"]],
    [[5, "t"], [5, "t"]], [[9, "t"], [4, "t"]], [[5, "t"], [5000, "t"]],
], ids=["missing", "not_a_list", "short", "no_time", "str_index", "bool_index", "negative",
        "repeated", "decreasing", "past_card_count"])
def test_malformed_deliveries_are_refused(deliveries):
    run = {"values_snapshot_id": 7}
    if deliveries is not None:
        run["deliveries"] = deliveries
    with pytest.raises(ValueError, match="deliveries"):
        ep.pack_run(run, _legacy_cards(), card_count=5)
    assert ep.check_deliveries({"deliveries": [[1, "t"], [4, "u"]]}, 5) == 4
    assert ep.check_deliveries({"deliveries": []}, 5) == -1


def test_row_fields_must_agree_with_the_header():
    packed = _pack(_legacy_cards())
    for bad, field in ((replace(packed, card_count=packed.card_count + 1), "card_count"),
                       (replace(packed, pack_version=0), "pack_version")):
        with pytest.raises(ep.PackIntegrityError, match=field):
            ep.unpack_run(bad)


def test_every_version_up_to_pack_version_has_a_decoder():
    """R2.2 (c): the reader decodes every version 1..PACK_VERSION forever."""
    for version in range(1, ep.PACK_VERSION + 1):
        assert callable(ep.DECODERS.get(version)), version
    packed = _pack(_legacy_cards())
    assert packed.pack_version == ep.PACK_VERSION
    assert json.loads(packed.header_json)["pack_version"] == ep.PACK_VERSION


@pytest.mark.parametrize("version", [0, -1, ep.PACK_VERSION + 1, "1", 1.0, True, None])
def test_unknown_pack_versions_are_refused(version):
    packed = _with_header(_pack(_legacy_cards()), lambda h: h.update(pack_version=version))
    with pytest.raises(ep.PackIntegrityError, match="unknown pack_version"):
        ep.unpack_run(replace(packed, pack_version=version))


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
        ep.pack_run({}, cards, card_count=5)


@pytest.mark.parametrize("card_count", [4, -1, None, 5.0])
def test_a_card_count_below_a_packed_index_is_refused(card_count):
    with pytest.raises(ValueError, match="card_count"):
        ep.pack_run({}, _legacy_cards(), card_count=card_count)


# ---------------------------------------------------------------------------
# C7 (ii) end to end: the same decks written as full rows and packed, both
# read back through backend.eval.data.load_decks
# ---------------------------------------------------------------------------

FIRST_FULL = 30   # C4
LAST_DELIVERED = 99   # the golden decks were delivered in pages of 25 through card 99
# Compared card by card: every key a registered scorer or replay may read,
# impression_id included (a non-ghost card's is card_impression_id, R4.2 U2).
GOLDEN_KEYS = C.FROZEN_INPUT_KEYS | C.IDENTITY_KEYS | C.LOGGED_POLICY_KEYS
_ROW_COLUMNS = ("user_id", "league_id", "card_index", "trade_hash", "propensity",
                "base_score", "final_score", "archetype", "shape_bucket", "served_at")
_ACTIONS = (("viewed", "viewed"), ("liked", "like"), ("passed", "pass"),
            ("proposed", "propose"), ("not_interested", "not_interested"), ("undone", "undo"))


def _has_outcome(card):
    return any(getattr(card, attr) for attr, _ in _ACTIONS)


def _write_db(decks, *, packed, head=FIRST_FULL, nudge=None):
    """A fresh DB holding `decks` = [(tag, LoggedDeck, packable card dicts)]
    as the packing writer leaves a retired deck: every non-ghost card's id is
    card_impression_id(run, index); every deck has a pack row whose run
    metadata records its deliveries (pages of 25 through card 99, or the
    whole deck if shorter); outcomes exist on delivered cards only, posted
    with the card's id; two ghost rows per deck copy cards 0 and n//2 at
    those would-have-been ranks. Deck ids are prefixed by tag (the harness
    configs share one job id).

    (A) packed=False, the C8 archive form: every card is a full row, and the
        pack holds the cards from `head` on (every row wins).
    (B) packed=True: the first `head` cards and the ghosts are rows; so are
        the cards with an outcome at an even index (upgraded on view, R4.2);
        the pack holds every card from `head` on, so an odd-index card with
        an outcome stays packed and its outcomes join by id (U2).
    nudge = (deck_job_id, card_index): that packed card's base_score moves 1 ulp."""
    eng, packs = make_engine()
    with eng.begin() as conn:
        for tag, deck, cards in decks:
            job, n = f"{tag}/{deck.deck_job_id}", len(deck.cards)
            served = deck.cards[0].served_at
            last = min(n - 1, LAST_DELIVERED)
            rows, outcomes, to_pack = [], [], []
            for c, d in zip(deck.cards, cards):
                iid = C.card_impression_id(job, c.card_index)
                row = {k: getattr(c, k) for k in _ROW_COLUMNS}
                row.update(impression_id=iid, deck_job_id=job, is_ghost=0,
                           features_json=json.dumps(c.features),
                           **{k: d[k] for k in D.ATTRIBUTION_COLUMNS if k in d})
                if c.card_index in (0, n // 2):
                    rows.append({**row, "impression_id": f"{c.impression_id}-ghost",
                                 "is_ghost": 1})
                seen = c.card_index <= last and _has_outcome(c)
                if seen:
                    actions = [a for attr, a in _ACTIONS if getattr(c, attr)]
                    outcomes += [{"impression_id": iid, "action": a,
                                  "dwell_ms": c.dwell_ms if i == 0 else None,
                                  "acted_at": served} for i, a in enumerate(actions)]
                if (not packed or c.card_index < head
                        or (seen and c.card_index % 2 == 0)):
                    rows.append(row)
                if c.card_index >= head:
                    p = {**d, "deck_job_id": job}
                    if packed and (job, c.card_index) == nudge:
                        p["base_score"] = math.nextafter(p["base_score"], math.inf)
                    to_pack.append(p)
            conn.execute(insert(deck_impressions_table), rows)
            if outcomes:
                conn.execute(insert(deck_outcomes_table), outcomes)
            run = {"values_snapshot_id": "vsn1:golden", "built_at": served, "config_ref": None,
                   "deliveries": [[b, served] for b in
                                  sorted({min(k, last) for k in range(24, last + 25, 25)})]}
            insert_pack(conn, packs, run_id=job, user_id=deck.user_id,
                        league_id=deck.league_id, served_at=served,
                        packed=ep.pack_run(run, to_pack, card_count=n))
    return eng


def _contract_view(card):
    d = card_dict(card)
    return json.dumps({k: d[k] for k in GOLDEN_KEYS if k in d}, sort_keys=True)


def _outcomes(c):
    return (c.viewed, c.liked, c.passed, c.proposed, c.not_interested, c.undone, c.dwell_ms)


def assert_db_golden(full, packed, model):
    """C7 (ii) over load_decks' output: the decks, the card dicts on every
    contract key, delivery, outcomes, every registered scorer's scores bit
    for bit, replay's estimates by repr, and a value-model refit."""
    assert ([(d.deck_job_id, d.served_at, d.exclusion) for d in full]
            == [(d.deck_job_id, d.served_at, d.exclusion) for d in packed])
    assert all(d.exclusion is None for d in full)
    for a, b in zip(full, packed):
        assert [(c.card_index, c.is_ghost, c.delivered) for c in a.cards] == \
               [(c.card_index, c.is_ghost, c.delivered) for c in b.cards], a.deck_job_id
        for x, y in zip(a.cards, b.cards):
            assert _contract_view(x) == _contract_view(y), (a.deck_job_id, x.card_index)
            assert _outcomes(x) == _outcomes(y), (a.deck_job_id, x.card_index)
    dicts_a = [card_dict(c) for d in full for c in d.cards]
    dicts_b = [card_dict(c) for d in packed for c in d.cards]
    with patch.object(vm, "load_latest_model", lambda: model):
        for name in registered_names():
            s_a, s_b = get_scorer(name, seed=5), get_scorer(name, seed=5)
            assert (_bits(s_a.score(c) for c in dicts_a)
                    == _bits(s_b.score(c) for c in dicts_b)), name
            run_a = evaluate(get_scorer(name, seed=5), full, bootstrap=200, seed=1)
            run_b = evaluate(get_scorer(name, seed=5), packed, bootstrap=200, seed=1)
            assert run_a.n_included > 0 and repr(run_a) == repr(run_b), name
    assert (vm.train_model(full, as_of=FIXED_NOW).to_dict()
            == vm.train_model(packed, as_of=FIXED_NOW).to_dict())


@pytest.fixture(scope="module")
def db_decks(harness, writer, synth):
    out = [(name, d, cs) for name, decks in harness.items() for d, cs in decks]
    out.append(("writer", *writer))
    return out + [("synth", d, cs) for d, cs in synth]


@pytest.mark.parametrize("head, project", [(FIRST_FULL, False), (0, True)])
def test_db_golden_full_rows_vs_packed(db_decks, trained, head, project):
    """head=30 is C4. head=0 packs every non-ghost card (the rows left are
    ghosts and upgraded cards), with the nightly's projected load. (iv): the
    writer deck's cards carry the R4.1 frozen taste matches."""
    full = load_decks(engine=_write_db(db_decks, packed=False), project_features=project)
    packed = load_decks(engine=_write_db(db_decks, packed=True, head=head),
                        project_features=project)
    from_pack = [c for d in packed for c in d.cards if not c.is_ghost and c.features is None]
    assert len(from_pack) >= 1100
    assert sum(c.viewed for c in from_pack) >= 3                   # outcomes joined by id
    assert all(vm.K_TASTE_PREF_LONG in c.features_compact for c in from_pack
               if c.deck_job_id.startswith("writer/"))
    assert sum(not c.delivered for d in packed for c in d.cards) >= 1100
    assert_db_golden(full, packed, trained)


def test_db_golden_detects_a_one_ulp_change(db_decks, trained):
    tag, deck, _cards = next(s for s in db_decks if s[0] == "writer")
    index = next(c.card_index for c in deck.cards
                 if c.card_index >= FIRST_FULL and not _has_outcome(c))
    full = load_decks(engine=_write_db(db_decks, packed=False))
    moved = load_decks(engine=_write_db(db_decks, packed=True,
                                        nudge=(f"{tag}/{deck.deck_job_id}", index)))
    scorer = get_scorer("base_score")
    bits_a = _bits(scorer.score(card_dict(c)) for d in full for c in d.cards)
    bits_b = _bits(scorer.score(card_dict(c)) for d in moved for c in d.cards)
    assert sum(a != b for a, b in zip(bits_a, bits_b)) == 1
    with pytest.raises(AssertionError):
        assert_db_golden(full, moved, trained)
