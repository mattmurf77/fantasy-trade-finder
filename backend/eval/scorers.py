"""F8 — registered-scorer registry.

A Scorer turns one card dict (backend.eval.data.card_dict — frozen
features_json merged with logged fields) into a float; higher = ranked
earlier. The registry is how the CLI, the nightly job, and future waves
(F6's learned model) name scorers.

Contract (the stub interface F6 implements):

    class MyScorer:
        name = "my_scorer"
        def score(self, card: dict) -> float: ...
        # optional — probability-emitting scorers (calibration.py consumes):
        # def predict_proba(self, card: dict) -> float   # P(like | card) in [0,1]
        # optional — trainable scorers (harness enforces the time split):
        # def fit(self, train_rows: list[dict]) -> None
        #     train_rows = [{"card": {...}, "viewed": bool, "liked": bool,
        #                    "proposed": bool, "dwell_ms": int|None}, ...]
        #     ONLY pre-eval_start impressions are ever passed here.

Register with @register or register_factory(name, callable). Factories
return a FRESH instance per run so fit() state never leaks across runs.

Honesty rule: candidate scorers must not read the logged-policy keys
(contract.LOGGED_POLICY_KEYS: `card_index`, `position`, `propensity`,
`base_score`, `final_score`) from the card dict. Those encode the logged
policy and would let a "candidate" trivially copy production. The
baselines below are the sanctioned exceptions, each reading only what
contract.PERMITTED_LOGGED grants it (`logged`: `position`).
"""

from __future__ import annotations

import random as _random_mod

_REGISTRY: dict[str, callable] = {}


def register_factory(name: str, factory) -> None:
    if name in _REGISTRY:
        raise ValueError(f"scorer {name!r} already registered")
    _REGISTRY[name] = factory


def register(cls):
    """Class decorator: registers cls under cls.name, instantiated fresh
    per get_scorer() call."""
    register_factory(cls.name, cls)
    return cls


def get_scorer(name: str, seed: int | None = None, config: dict | None = None):
    """A fresh scorer. `config` is a pinned model_config record
    (value_model.pin_config): a scorer that reads configuration
    (`takes_config = True`) takes it as its constructor argument and reads
    nothing live; a scorer that reads none ignores it. Omitted, a configured
    scorer pins the live values itself. Either way the scorer's `config` is
    what an EvalRun records (models-lead R5.2 (a))."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown scorer {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None
    scorer = (factory(config=config)
              if config is not None and getattr(factory, "takes_config", False) else factory())
    if seed is not None and hasattr(scorer, "reseed"):
        scorer.reseed(seed)
    return scorer


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------

@register
class LoggedOrderScorer:
    """The logged policy itself: reproduces the exact displayed order
    (score = -position, the loader's displayed position: withdrawals and
    serve-time display moves included, models-lead F2). This is the
    --self-check scorer — replaying it must reproduce observed rates within CI."""
    name = "logged"

    def score(self, card: dict) -> float:
        return -float(card.get("position", 0))


@register
class ProductionScorer:
    """Production-ordering baseline reconstructed from logs: final_score is
    the post-multiplier ordering key _order_deck actually sorted by, so
    ranking by it reproduces the production policy (including presentation
    multipliers) up to the logged Thompson draw."""
    name = "production"

    def score(self, card: dict) -> float:
        v = card.get("final_score")
        if v is None:
            v = card.get("base_score") or 0.0
        return float(v)


@register
class BaseScoreScorer:
    """Pre-presentation composite (base_score): 'what if we served the raw
    engine order with no presentation layer' — the first real counterfactual
    candidate."""
    name = "base_score"

    def score(self, card: dict) -> float:
        return float(card.get("base_score") or 0.0)


@register
class RandomOrderScorer:
    """Deliberately broken canary: uniform-random order, seeded for
    reproducibility. Must grade measurably worse than production on any
    healthy log (PRD acceptance criterion) — if it ever grades level, the
    harness or the log is broken."""
    name = "random"

    def __init__(self, seed: int = 0):
        self._rng = _random_mod.Random(seed)

    def reseed(self, seed: int) -> None:
        self._rng = _random_mod.Random(seed)

    def score(self, card: dict) -> float:
        return self._rng.random()


@register
class ValueModelScorer:
    """F6 — learned acceptance heads × V-vector (backend/value_model.py,
    flag deck.value_model — dark). Loads the LATEST persisted nightly
    model, so the nightly job automatically grades the production-trained
    artifact vs the production baseline; the F8-replay-win verdict on this
    scorer is the PRD's graduation gate for flipping the flag.

    Honest candidate: features come from the frozen features_json only —
    card_index / final_score / propensity are never read (served position
    is a train-time debias feature pinned to its training mean at
    predict). predict_proba emits the calibrated P(like) for the
    reliability tables.

    Until a model has been trained (`python3 -m backend.value_model
    --refit`, or the flag-gated nightly refit once deck.value_model is
    on), every score()/predict_proba() call raises — the harness then
    excludes each deck under its printed `scorer_error` accounting, which
    is the honest signal: there is no model to grade, and falling back to
    any proxy score would grade a fake.

    Its V-vector is a pinned model_config record (`config`, R5.2 (a)):
    passed in to replay a recorded run, else pinned from live model_config
    once, here. Every score uses it; nothing reads model_config live."""
    name = "value_model"
    takes_config = True

    def __init__(self, config: dict | None = None):
        from backend.value_model import SCORE_CONFIG, load_latest_model, pin_config
        self.config = config if config is not None else pin_config(SCORE_CONFIG)
        self._model = load_latest_model()

    def _require_model(self):
        if self._model is None:
            raise RuntimeError(
                "no persisted value model (data/value_model/models.jsonl) — "
                "train one with `python3 -m backend.value_model --refit`")
        return self._model

    def score(self, card: dict) -> float:
        return float(self._require_model().rank_score_from_card(
            card, v_values=self.config["values"]))

    def predict_proba(self, card: dict) -> float:
        return float(self._require_model().p_like_from_card(card))
