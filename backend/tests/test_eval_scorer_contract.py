"""C7 (iii): the scorer-input contract (backend/eval/contract.py).

Narrow evidence rows keep a frozen compact block instead of features_json,
so replay stays valid only if no registered scorer reads a key the narrow
row lacks. Covered here:

  - Contract: every registered scorer, scoring a card wrapped in a
    key-recording dict, reads only COMPACT ∪ INJECTED ∪ IDENTITY ∪ its
    PERMITTED_LOGGED columns.
  - Guards: COMPACT_KEYS is exactly what value_model.extract_features
    reads; INJECTED_* is exactly what ValueModel._inject reads and writes;
    card_dict's logged columns are all classified; every registered scorer
    has a PERMITTED_LOGGED entry.
  - Equivalence: a card carrying only the frozen block (FROZEN_INPUT_KEYS)
    scores identically to one carrying the full features_json, for every
    scorer; the 14 COMPACT_KEYS alone do not, for value_model.

How value_model is instrumented: a real model is fitted in-test with the
module's own train_model() on synthetic LoggedDecks (in-memory SQLite
patched into backend.database for the taste reads, VALUE_MODEL_DIR on a
tmp dir), persisted with append_model(), and graded through the registered
`value_model` scorer end to end. One seam: _inject's `g = dict(f)` copies
the whole card, and a copy is a pass-through, not a read. The builtin
`dict` inside backend.value_model is swapped for `_see_through_copy`,
which copies a recorder into a recorder sharing the same log, so
extract_features' reads on the copy are recorded too. A future change to
another copy idiom (`{**f}`) would record every key and fail loudly,
which is the safe direction.
"""

import random
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.value_model as vm
from backend.database import metadata, user_taste_table
from backend.eval import contract as C
from backend.eval import scorers
from backend.eval.data import LoggedCard, LoggedDeck, card_dict

USER = "u_contract"
ITERATED = "<iterated the whole card>"


class KeyRecorder(dict):
    """A card dict that records every key read through [], get(), `in`
    and iteration. Iteration records ITERATED, which no contract permits:
    a scorer that walks the whole card depends on keys a narrow row lacks.
    copy() returns a recorder sharing the same log."""

    def __init__(self, data, reads=None):
        super().__init__(dict.items(data))   # unbound: never records
        self.reads = set() if reads is None else reads

    def __getitem__(self, key):
        self.reads.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.reads.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        self.reads.add(key)
        return super().__contains__(key)

    def __iter__(self):
        self.reads.add(ITERATED)
        return super().__iter__()

    def keys(self):
        self.reads.add(ITERATED)
        return super().keys()

    def items(self):
        self.reads.add(ITERATED)
        return super().items()

    def values(self):
        self.reads.add(ITERATED)
        return super().values()

    def copy(self):
        return KeyRecorder(self, self.reads)


class _BuiltinDictChecks(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, dict)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, dict)


class _see_through_copy(metaclass=_BuiltinDictChecks):
    """Stands in for `dict` inside backend.value_model (see module doc).
    Calls and isinstance checks behave as the builtin's, except that
    copying a KeyRecorder yields a KeyRecorder sharing its log."""

    def __new__(cls, *args, **kwargs):
        if len(args) == 1 and not kwargs and isinstance(args[0], KeyRecorder):
            return KeyRecorder(args[0], args[0].reads)
        return dict(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures: cards shaped like a real features_json, and a fitted model
# ---------------------------------------------------------------------------

def _full_features(rng=None, *, partner="opp1", quality=0.7) -> dict:
    """A wide features_json: every scorer input plus keys no scorer reads."""
    rng = rng or random.Random(0)
    shape = rng.choice(("1x1", "2x1", "1x2"))
    lane = rng.choice(("window", "value"))
    return {
        "shape": shape, "lane": lane, "basis": "divergence",
        "likes_you": rng.random() < 0.2, "relaxed": rng.random() < 0.2,
        "give_positions": ["RB"], "receive_positions": ["WR", "PICK"],
        "give_value": 1000 + 500 * quality, "receive_value": 1050 + 500 * quality,
        "involves_pick": True, "partner_user_id": partner,
        "surplus_margin": 80 * quality, "fairness_score": 0.8 + 0.15 * quality,
        "ranked_player_count": 40, "user_value_basis": "personal",
        "taste_attrs": [f"shape:{shape}", f"arch:{lane}", "recvpos:WR",
                        f"partner:{partner}"],
        # Wide-only keys: dropped by a narrow row, read by no scorer.
        "give_value_band": "1000-1500", "receive_value_band": "1000-1500",
        "last_board_update_at": "2026-10-01T00:00:00+00:00",
        "served_market": {"give": 1, "receive": 2},
    }


def _fallback_features() -> dict:
    """No shape, lane or taste_attrs: drives extract_features onto its
    shape_bucket/archetype fallbacks and _inject onto attrs_from_features'
    derivation from frozen fields."""
    f = _full_features(partner="opp2")
    for k in ("shape", "lane", "taste_attrs"):
        f.pop(k)
    return f


def _card(features=None, compact=None, *, pos=0, job="j_contract",
          served_at="2026-10-10T00:00:00+00:00", **outcome) -> LoggedCard:
    return LoggedCard(
        impression_id=f"{job}_{pos}", deck_job_id=job, user_id=USER,
        league_id="lg", card_index=pos, trade_hash=f"h{pos}",
        propensity=1.0, base_score=2.0 - pos / 10, final_score=2.5 - pos / 10,
        archetype="value", shape_bucket="2x1", served_at=served_at,
        features=features, features_compact=compact, **outcome,
    )


def _contract_cards() -> list[LoggedCard]:
    return [_card(_full_features()), _card(_fallback_features(), pos=1)]


def _training_decks() -> list[LoggedDeck]:
    rng = random.Random(42)
    decks = []
    for d in range(12):
        served = f"2026-10-0{1 + d % 9}T{d:02d}:00:00+00:00"
        cards = []
        for pos in range(8):
            quality = 1.0 - pos / 8 + rng.uniform(-0.1, 0.1)
            partner = f"opp{rng.randrange(4)}"
            f = _full_features(rng, partner=partner, quality=quality)
            if rng.random() < 0.3:
                f.pop("taste_attrs")
            liked = rng.random() < (0.1 + 0.4 * quality
                                    + (0.2 if partner == "opp1" else 0.0))
            cards.append(_card(f, pos=pos, job=f"jt{d}", served_at=served,
                               viewed=True, liked=liked, passed=not liked,
                               proposed=liked and rng.random() < 0.4))
        decks.append(LoggedDeck(deck_job_id=f"jt{d}", user_id=USER,
                                league_id="lg", served_at=served, cards=cards))
    return decks


@pytest.fixture()
def taste_db(monkeypatch):
    """In-memory DB for value_model's taste reads, with a taste vector for
    USER so prefMatch is non-zero."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    now = datetime.now(timezone.utc).isoformat()
    with eng.begin() as conn:
        conn.execute(insert(user_taste_table), [
            {"user_id": USER, "attr": a, "w_short": ws, "w_long": wl,
             "updated_at": now}
            for a, ws, wl in (("partner:opp1", 2.0, 3.0), ("recvpos:WR", 1.0, 0.5),
                              ("shape:2x1", -1.0, -0.5), ("arch:value", 0.8, 1.2))
        ])
    return eng


_FITTED: dict = {}   # fit once per module; each test persists its own copy


@pytest.fixture()
def fitted_model(taste_db, tmp_path, monkeypatch):
    """A value model fitted with the module's own API and persisted where
    the registered `value_model` scorer loads it from."""
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path / "vm"))
    monkeypatch.setattr(vm, "_model_cache", None)
    if "model" not in _FITTED:
        trained = vm.train_model(_training_decks())
        assert trained is not None, "fixture decks too small to train"
        _FITTED["model"] = trained.to_dict()
    model = vm.ValueModel.from_dict(_FITTED["model"])
    vm.append_model(model)
    vm._model_cache = None
    return model


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", scorers.registered_names())
def test_scorer_reads_only_contract_keys(name, fitted_model, monkeypatch):
    monkeypatch.setattr(vm, "dict", _see_through_copy, raising=False)
    scorer = scorers.get_scorer(name, seed=0)
    for card in _contract_cards():
        rec = KeyRecorder(card_dict(card))
        scorer.score(rec)
        if hasattr(scorer, "predict_proba"):
            scorer.predict_proba(rec)
        outside = rec.reads - C.allowed_keys(name)
        assert not outside, (
            f"scorer {name!r} reads {sorted(outside)}, outside the C7 "
            "contract. Add a feature to COMPACT_KEYS (and the compact-block "
            "writer) before a scorer reads it, or grant a logged column in "
            "PERMITTED_LOGGED (backend/eval/contract.py)")


def test_value_model_contract_run_actually_reads_the_card(fitted_model, monkeypatch):
    """Positive control: the instrumented value_model path records the
    extract_features and _inject inputs, so an empty read set can't pass
    the contract test vacuously."""
    monkeypatch.setattr(vm, "dict", _see_through_copy, raising=False)
    rec = KeyRecorder(card_dict(_card(_full_features())))
    scorers.get_scorer("value_model").score(rec)
    assert {"user_id", "partner_user_id", "taste_attrs", "give_value",
            "_pref_long", "_partner_rate"} <= rec.reads


# ---------------------------------------------------------------------------
# Guards: the declared sets track the code
# ---------------------------------------------------------------------------

def test_compact_keys_are_exactly_what_extract_features_reads():
    reads: set = set()
    for card in _contract_cards():
        vm.extract_features(KeyRecorder(card_dict(card), reads))
    card_inputs = reads - C.INJECTED_COMPUTED_KEYS - C.IDENTITY_KEYS
    assert card_inputs == C.COMPACT_KEYS, (
        f"extract_features reads {sorted(card_inputs - C.COMPACT_KEYS)} not "
        f"in COMPACT_KEYS; COMPACT_KEYS lists {sorted(C.COMPACT_KEYS - card_inputs)} "
        "it no longer reads. A new feature joins the compact block first.")


def test_injected_keys_are_exactly_what_inject_reads_and_writes(taste_db, monkeypatch):
    monkeypatch.setattr(vm, "dict", _see_through_copy, raising=False)
    model = vm.ValueModel(
        like_head=vm.LogisticHead(), propose_head=None, propose_constant=0.0,
        partner_rates={}, global_like_rate=0.5, position_mean=0.3,
        trained_at="", train_date="")
    reads: set = set()
    for features in (_full_features(), _fallback_features()):
        out = model._inject(KeyRecorder(features, reads), USER)
        assert set(dict.keys(out)) - set(features) == C.INJECTED_COMPUTED_KEYS
    assert reads - C.COMPACT_KEYS == C.INJECTED_CARD_INPUTS


def test_card_dict_logged_columns_are_all_classified():
    logged = set(card_dict(_card(None)))
    assert logged == C.IDENTITY_KEYS | C.LOGGED_POLICY_KEYS, (
        "card_dict's logged columns changed: classify each one as identity "
        "or logged policy in backend/eval/contract.py")
    assert not C.IDENTITY_KEYS & C.LOGGED_POLICY_KEYS


def test_every_registered_scorer_declares_its_logged_columns():
    names = set(scorers.registered_names())
    missing = names - set(C.PERMITTED_LOGGED)
    stale = set(C.PERMITTED_LOGGED) - names
    assert not missing, (
        f"registered scorers without a PERMITTED_LOGGED entry: {sorted(missing)}")
    assert not stale, f"PERMITTED_LOGGED entries for no scorer: {sorted(stale)}"
    for name, cols in C.PERMITTED_LOGGED.items():
        assert cols <= C.LOGGED_POLICY_KEYS, (name, sorted(cols))


# ---------------------------------------------------------------------------
# Equivalence: the frozen block replays exactly
# ---------------------------------------------------------------------------

def _frozen(features: dict, keys=C.FROZEN_INPUT_KEYS) -> dict:
    return {k: v for k, v in features.items() if k in keys}


@pytest.mark.parametrize("name", scorers.registered_names())
def test_compact_block_scores_like_full_features(name, fitted_model):
    for features in (_full_features(), _fallback_features()):
        full = _card(features)
        narrow = _card(None, _frozen(features))
        s_full = scorers.get_scorer(name, seed=7).score(card_dict(full))
        s_narrow = scorers.get_scorer(name, seed=7).score(card_dict(narrow))
        assert s_narrow == s_full, (name, s_narrow, s_full)


def test_compact_keys_alone_do_not_replay_value_model(fitted_model):
    """Why the frozen block is COMPACT_KEYS ∪ INJECTED_CARD_INPUTS: without
    partner_user_id and taste_attrs, _inject falls back to the global like
    rate and a partner-less taste derivation, and the score moves."""
    features = _full_features()
    full = _card(features)
    narrow = _card(None, _frozen(features, C.COMPACT_KEYS))
    scorer = scorers.get_scorer("value_model")
    assert scorer.score(card_dict(narrow)) != scorer.score(card_dict(full))


def test_card_dict_prefers_features_and_logged_fields_win():
    card = _card({"shape": "1x1", "final_score": 99.0},
                 {"shape": "3x2", "give_value": 5.0})
    d = card_dict(card)
    assert d["shape"] == "1x1" and "give_value" not in d
    assert d["final_score"] == card.final_score       # logged wins collisions
    d2 = card_dict(_card(None, {"shape": "3x2", "card_index": 40}))
    assert d2["shape"] == "3x2" and d2["card_index"] == 0
