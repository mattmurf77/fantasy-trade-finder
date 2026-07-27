"""F6 (flag deck.value_model) — learned acceptance heads × V-vector.

docs/plans/tiktok-discovery/prds/F6-value-model.md · models-research §2
(Algo 101 value function) + §1 (Monolith log-odds calibration).

SHIPS DARK. `deck.value_model` stays false until an F8 replay win with
adequate ESS on real data. Both TRAINING (the nightly refit inside
/api/cron/daily-tick) and SERVING (the base-ordering swap in
server._order_deck) are gated on the flag, so dark means truly inert:
zero reads, zero writes, zero model files. The only flag-independent
entry points are operator-explicit: the CLI (`python3 -m
backend.value_model --refit`) — needed to train the first model for the
F8 replay gate BEFORE the flag ever flips — and the F8 scorer
registration in backend/eval/scorers.py, which grades whatever model the
operator has persisted.

Two calibrated heads, plain-Python logistic regression (no sklearn/numpy
— checked: requirements.txt has neither; data volume makes full-batch GD
trivial):

    P(like | user, card)          — viewed → like/pass labels
    P(propose | user, card, like) — liked  → proposed labels

Features come from the SAME frozen features_json the F1 spine logs
(via backend.eval.data.card_dict at train time and card_features() at
serve time — identical key names, so no training/serving skew), plus:
  - F5 taste-match scores (prefMatch_long/short cosine of the user's live
    taste vector against the card's frozen taste_attrs),
  - per-(user, partner) smoothed historical like rate ("partner history"),
  - served position as a TRAIN-TIME debiasing feature only (YouTube
    shallow-tower pattern): at predict time it is pinned to its training
    mean, so the scorer NEVER reads card_index — the F8 honesty rule.

Calibration: Platt scaling fit on a held-out TIME slice (the last
calib_frac of training rows by served_at). Negatives are NOT downsampled
at this scale; if a future caller ever does, `neg_sample_rate` < 1 stored
on a head applies the Monolith log-odds correction
(logit += ln(rate)) at predict time so probabilities stay honest.

The V-vector — strategy, not learning (PRD §2): hand-set values read
LIVE from model_config at scoring time (changeable without retraining):

    rank_score = P(like)·V_like + P(like)·P(propose|like)·V_propose
    V_like     = model_config value_model_v_like     (default 1.0)
    V_propose  = model_config value_model_v_propose  (default 6.0)

Scope of authority — BASE ORDERING ONLY. server._order_deck swaps its
base key (composite_score) for rank_score when the flag is on, a trained
model exists, and the user has ≥1 deck-outcome row. Every gate upstream
(surplus/fairness/junk/untouchables) and every presentation layer on top
(Thompson draw, F3 fatigue, F5 taste multipliers, diversity penalty +
caps, likes-you pinning, F7 wildcard slot) is untouched — a bad trade
can never be boosted into a deck, and deck_impressions.base_score keeps
logging the composite so F8's `base_score` counterfactual stays honest.

Persistence: append-only JSON-lines at data/value_model/models.jsonl
(env VALUE_MODEL_DIR) — the F8 eval_runs pragmatism verbatim: no schema
migration, greppable, single-writer cron, schema_version on every record
for a later lift into SQL. Latest parseable record = the served model.
Nightly refit is idempotent per UTC date (an existing record for today
⇒ skip).
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.environ.get(
    "VALUE_MODEL_DIR", os.path.join(_REPO_ROOT, "data", "value_model"))
MODELS_FILE = "models.jsonl"

# Hand-set V-vector defaults (PRD: start 6:1, mirroring the Elo K ratios
# like=8 vs accept=20+propose weighting; rules live OUTSIDE the model).
V_LIKE_DEFAULT = 1.0
V_PROPOSE_DEFAULT = 6.0


def _cfg(key: str, default: float) -> float:
    """model_config key via trade_service's live config dict (the
    taste_service._cfg pattern — inline defaults, so a missing key can
    never break scoring or the refit; keys documented in
    docs/config-reference.md §F6)."""
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get(key, default))
    except Exception:
        return float(default)


def models_path() -> str:
    # Env re-read at call time so tests can point at a tmp dir (F8 idiom).
    base = os.environ.get("VALUE_MODEL_DIR", MODELS_DIR)
    return os.path.join(base, MODELS_FILE)


# ---------------------------------------------------------------------------
# Feature extraction — ONE canonical function over a features_json-shaped
# dict, shared by training (eval.data.card_dict) and serving (card_features).
# ---------------------------------------------------------------------------

_POSITIONS = ("QB", "RB", "WR", "TE", "PICK")

# Injected (computed, not frozen) keys — reserved names so they can never
# collide with features_json fields.
K_PREF_LONG = "_pref_long"
K_PREF_SHORT = "_pref_short"
K_PARTNER_RATE = "_partner_rate"
K_POSITION = "_position"       # served-position fraction; TRAIN-TIME ONLY


def _num(v, default=0.0) -> float:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        if math.isfinite(f):
            return f
    return float(default)


def _clip(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def extract_features(f: dict) -> dict[str, float]:
    """features_json-shaped dict → sparse {feature_name: value}.

    Deliberately NEVER reads `card_index`, `final_score`, or `propensity`
    (F8 honesty rule) — served position enters only via the injected
    K_POSITION key, which serving pins to the training mean.
    """
    x: dict[str, float] = {"bias": 1.0}

    give_v = _num(f.get("give_value"))
    recv_v = _num(f.get("receive_value"))
    x["surplus_margin"] = _clip(_num(f.get("surplus_margin")) / 100.0, -5.0, 5.0)
    x["fairness"] = _clip(_num(f.get("fairness_score")), 0.0, 2.0)
    x["value_delta"] = _clip((recv_v - give_v) / 1000.0, -3.0, 3.0)
    x["value_total"] = _clip((recv_v + give_v) / 2000.0, 0.0, 8.0)
    x["ranked_frac"] = _clip(_num(f.get("ranked_player_count")) / 100.0, 0.0, 1.0)

    shape = f.get("shape") or f.get("shape_bucket")
    if shape:
        x[f"shape:{shape}"] = 1.0
    lane = f.get("lane") or f.get("archetype")
    if lane:
        x[f"lane:{lane}"] = 1.0
    basis = f.get("basis")
    if basis:
        x[f"basis:{basis}"] = 1.0
    for pos in {p for p in (f.get("give_positions") or []) if p in _POSITIONS}:
        x[f"give:{pos}"] = 1.0
    for pos in {p for p in (f.get("receive_positions") or []) if p in _POSITIONS}:
        x[f"recv:{pos}"] = 1.0
    if f.get("involves_pick"):
        x["pick"] = 1.0
    if f.get("likes_you"):
        x["likes_you"] = 1.0
    if f.get("relaxed"):
        x["relaxed"] = 1.0
    if f.get("user_value_basis") == "personal":
        x["basis_personal"] = 1.0

    # Injected features (0.0 when absent — the no-signal anchor).
    x["pref_long"] = _clip(_num(f.get(K_PREF_LONG)), -1.0, 1.0)
    x["pref_short"] = _clip(_num(f.get(K_PREF_SHORT)), -1.0, 1.0)
    x["partner_rate"] = _clip(_num(f.get(K_PARTNER_RATE)), 0.0, 1.0)
    x["position"] = _clip(_num(f.get(K_POSITION)), 0.0, 1.0)
    return x


def card_features(card, players_dict: dict, seed_map: dict, *,
                  ranked_player_count=None) -> dict:
    """Serve-time features_json-shaped dict for a LIVE card, using the
    exact key names server._log_deck_signal_impressions freezes — the
    training/serving-skew guard. Cheap getattr reads only."""
    give = [str(p) for p in (getattr(card, "give_player_ids", None) or [])]
    recv = [str(p) for p in (getattr(card, "receive_player_ids", None) or [])]

    def _positions(pids):
        return [getattr(players_dict.get(p), "position", None) or "?" for p in pids]

    give_pos = _positions(give)
    recv_pos = _positions(recv)
    f = {
        "shape": f"{len(give)}x{len(recv)}",
        "basis": getattr(card, "basis", "divergence"),
        "likes_you": bool(getattr(card, "likes_you", False)),
        "lane": getattr(card, "lane", None),
        "give_positions": give_pos,
        "receive_positions": recv_pos,
        "give_value": getattr(card, "give_value", None),
        "receive_value": getattr(card, "receive_value", None),
        "involves_pick": ("PICK" in give_pos) or ("PICK" in recv_pos),
        "partner_user_id": getattr(card, "target_user_id", None),
        "surplus_margin": getattr(card, "mismatch_score", None),
        "fairness_score": getattr(card, "fairness_score", None),
        "relaxed": bool(getattr(card, "relaxed", False)),
    }
    if ranked_player_count is not None:
        f["ranked_player_count"] = ranked_player_count
        f["user_value_basis"] = ("personal" if ranked_player_count > 0
                                 else "consensus")
    try:
        from . import taste_service as _taste
        f["taste_attrs"] = _taste.card_taste_attrs(
            card, players_dict or {}, seed_map or {})
    except Exception:
        pass
    return f


def _taste_attrs_of(f: dict) -> list[str]:
    """The card's taste-attribute keys from a frozen/serve-time features
    dict: the stamped taste_attrs when present, else the F5 fallback
    derivation from frozen fields."""
    try:
        from . import taste_service as _taste
        return _taste.attrs_from_features(f if isinstance(f, dict) else {})
    except Exception:
        return []


class _TasteCache:
    """Per-run cache of (short, long) taste vectors by user — one DB read
    per user per training run / deck / eval pass. Any failure degrades to
    empty vectors (prefMatch 0.0), never an exception."""

    def __init__(self):
        self._by_user: dict[str, tuple[dict, dict]] = {}

    def pref_match(self, user_id, attrs: list[str]) -> tuple[float, float]:
        if not user_id or not attrs:
            return 0.0, 0.0
        uid = str(user_id)
        if uid not in self._by_user:
            try:
                from . import taste_service as _taste
                self._by_user[uid] = _taste.load_taste_vectors(uid)
            except Exception:
                self._by_user[uid] = ({}, {})
        short, long_ = self._by_user[uid]
        try:
            from . import taste_service as _taste
            return (_taste._pref_match(long_, attrs),
                    _taste._pref_match(short, attrs))
        except Exception:
            return 0.0, 0.0


# ---------------------------------------------------------------------------
# Plain-Python logistic regression (full-batch GD + L2) and Platt scaling
# ---------------------------------------------------------------------------

def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


# The dense/numeric feature group — everything else is a one-hot. Grouped
# L2: numerics get the light value_model_l2, one-hots the much stronger
# value_model_l2_cat. Rationale (validated on the F8 synthetic fixtures,
# where it recovers ~the oracle AUC that uniform L2 misses): at this data
# volume high-cardinality one-hots overfit label noise and pollute the
# ranking, while personalized categorical taste already reaches the model
# through the F5 prefMatch numerics — the one-hots only need to carry
# strong GLOBAL categorical effects, which survive a 0.5 penalty.
NUMERIC_FEATURES = frozenset({
    "bias", "surplus_margin", "fairness", "value_delta", "value_total",
    "ranked_frac", "pref_long", "pref_short", "partner_rate", "position",
})


class LogisticHead:
    """Sparse-dict logistic regression. Deterministic (no shuffling, no
    random init), grouped L2 (bias exempt). Small data ⇒ full-batch
    gradient descent is exact enough and dependency-free."""

    def __init__(self, weights: dict[str, float] | None = None,
                 platt_a: float = 1.0, platt_b: float = 0.0,
                 neg_sample_rate: float = 1.0):
        self.weights = dict(weights or {})
        self.platt_a = float(platt_a)
        self.platt_b = float(platt_b)
        # Monolith log-odds correction: when negatives were downsampled at
        # rate r < 1, serving logit += ln(r). We never downsample today
        # (rate 1.0 ⇒ ln = 0), but the correction is wired so a future
        # sampler cannot silently break calibration.
        self.neg_sample_rate = float(neg_sample_rate)

    # -- training ----------------------------------------------------------
    def fit(self, rows: list[tuple[dict, float]], *,
            l2: float = 0.01, l2_cat: float = 0.5,
            lr: float = 1.0, epochs: int = 800) -> None:
        if not rows:
            raise ValueError("no training rows")
        vocab: set[str] = set()
        for x, _y in rows:
            vocab.update(x)
        w = {k: 0.0 for k in sorted(vocab)}
        n = len(rows)
        for _ in range(int(epochs)):
            grad = {k: 0.0 for k in w}
            for x, y in rows:
                z = sum(w[k] * v for k, v in x.items() if k in w)
                err = _sigmoid(z) - y
                for k, v in x.items():
                    if k in w:
                        grad[k] += err * v
            for k in w:
                g = grad[k] / n
                if k != "bias":
                    g += (l2 if k in NUMERIC_FEATURES else l2_cat) * w[k]
                w[k] -= lr * g
        self.weights = w

    def fit_platt(self, rows: list[tuple[dict, float]], *,
                  lr: float = 0.2, epochs: int = 400) -> None:
        """Platt scaling on a HELD-OUT slice: 1-D logistic over the raw
        (corrected) logit. Skipped (identity) when the slice lacks both
        classes — a one-class slice cannot calibrate anything."""
        ys = {y for _x, y in rows}
        if len(rows) < 10 or ys != {0.0, 1.0}:
            self.platt_a, self.platt_b = 1.0, 0.0
            return
        a, b = 1.0, 0.0
        n = len(rows)
        logits = [self._raw_logit(x) for x, _y in rows]
        for _ in range(int(epochs)):
            ga = gb = 0.0
            for z, (_x, y) in zip(logits, rows):
                err = _sigmoid(a * z + b) - y
                ga += err * z
                gb += err
            a -= lr * ga / n
            b -= lr * gb / n
        self.platt_a, self.platt_b = a, b

    # -- inference ---------------------------------------------------------
    def _raw_logit(self, x: dict[str, float]) -> float:
        z = sum(self.weights.get(k, 0.0) * v for k, v in x.items())
        if self.neg_sample_rate < 1.0:
            z += math.log(self.neg_sample_rate)
        return z

    def predict_proba(self, x: dict[str, float]) -> float:
        return _sigmoid(self.platt_a * self._raw_logit(x) + self.platt_b)

    # -- (de)serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {"weights": self.weights, "platt_a": self.platt_a,
                "platt_b": self.platt_b,
                "neg_sample_rate": self.neg_sample_rate}

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticHead":
        return cls(weights=d.get("weights") or {},
                   platt_a=d.get("platt_a", 1.0),
                   platt_b=d.get("platt_b", 0.0),
                   neg_sample_rate=d.get("neg_sample_rate", 1.0))


# ---------------------------------------------------------------------------
# The two-head model
# ---------------------------------------------------------------------------

def _partner_key(user_id, partner) -> str:
    return f"{user_id}|{partner}"


class ValueModel:
    """like_head + propose_head + the injected-feature lookup tables.

    propose_head may be a constant (Laplace-smoothed P(propose|like)) when
    liked rows are too scarce to fit — the PRD's small-data mitigation."""

    def __init__(self, *, like_head: LogisticHead,
                 propose_head: LogisticHead | None,
                 propose_constant: float,
                 partner_rates: dict[str, float],
                 global_like_rate: float,
                 position_mean: float,
                 trained_at: str,
                 train_date: str,
                 meta: dict | None = None):
        self.like_head = like_head
        self.propose_head = propose_head
        self.propose_constant = float(propose_constant)
        self.partner_rates = dict(partner_rates)
        self.global_like_rate = float(global_like_rate)
        self.position_mean = float(position_mean)
        self.trained_at = trained_at
        self.train_date = train_date
        self.meta = dict(meta or {})
        self._taste = _TasteCache()

    # -- feature injection ---------------------------------------------------
    def _inject(self, f: dict, user_id, *, position=None) -> dict:
        """Return a copy of the features dict with the computed features
        injected. `position` None (serving/eval) ⇒ the training mean —
        the shallow-tower drop; the model never reads card_index."""
        g = dict(f)
        pl, ps = self._taste.pref_match(user_id, _taste_attrs_of(f))
        g[K_PREF_LONG] = pl
        g[K_PREF_SHORT] = ps
        partner = f.get("partner_user_id")
        g[K_PARTNER_RATE] = self.partner_rates.get(
            _partner_key(user_id, partner), self.global_like_rate)
        g[K_POSITION] = self.position_mean if position is None else position
        return g

    # -- heads ---------------------------------------------------------------
    def p_like(self, f: dict, user_id) -> float:
        return self.like_head.predict_proba(
            extract_features(self._inject(f, user_id)))

    def p_propose_given_like(self, f: dict, user_id) -> float:
        if self.propose_head is None:
            return self.propose_constant
        return self.propose_head.predict_proba(
            extract_features(self._inject(f, user_id)))

    # -- the V-vector (strategy layer — live model_config reads) -------------
    def rank_score(self, f: dict, user_id) -> float:
        v_like = _cfg("value_model_v_like", V_LIKE_DEFAULT)
        v_prop = _cfg("value_model_v_propose", V_PROPOSE_DEFAULT)
        pl = self.p_like(f, user_id)
        return pl * v_like + pl * self.p_propose_given_like(f, user_id) * v_prop

    # -- card-dict entry points (F8 scorer: user_id rides the card dict) -----
    def rank_score_from_card(self, card: dict) -> float:
        return self.rank_score(card, card.get("user_id"))

    def p_like_from_card(self, card: dict) -> float:
        return self.p_like(card, card.get("user_id"))

    # -- (de)serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "like_head": self.like_head.to_dict(),
            "propose_head": (self.propose_head.to_dict()
                             if self.propose_head else None),
            "propose_constant": self.propose_constant,
            "partner_rates": self.partner_rates,
            "global_like_rate": self.global_like_rate,
            "position_mean": self.position_mean,
            "trained_at": self.trained_at,
            "train_date": self.train_date,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValueModel":
        ph = d.get("propose_head")
        return cls(
            like_head=LogisticHead.from_dict(d.get("like_head") or {}),
            propose_head=LogisticHead.from_dict(ph) if ph else None,
            propose_constant=d.get("propose_constant", 0.0),
            partner_rates=d.get("partner_rates") or {},
            global_like_rate=d.get("global_like_rate", 0.0),
            position_mean=d.get("position_mean", 0.0),
            trained_at=d.get("trained_at", ""),
            train_date=d.get("train_date", ""),
            meta=d.get("meta") or {},
        )


# ---------------------------------------------------------------------------
# Training pipeline (labels per the F2 cascade rule: only VIEWED cards have
# honest labels; undone dispositions are retracted)
# ---------------------------------------------------------------------------

# Guardrail minimums — below these the refit declines to persist a model
# (serving then falls back to composite, by design).
MIN_LIKE_ROWS = 30
MIN_LIKE_POS = 5
# Below these the propose head degrades to the smoothed constant.
MIN_PROPOSE_ROWS = 20
MIN_PROPOSE_POS = 3

_POSITION_NORM = 10.0   # card_index / this, clipped to [0,1] — train-only


def build_training_rows(decks) -> tuple[list[dict], list[dict]]:
    """LoggedDecks → (like_rows, propose_rows), each row =
    {"f": features_json-shaped dict, "y": 0/1, "user_id", "served_at",
     "position": card_index/_POSITION_NORM}.

    like head:    viewed ∧ ¬undone ∧ (liked ∨ passed), y = liked.
    propose head: viewed ∧ ¬undone ∧ liked,            y = proposed.
    """
    like_rows: list[dict] = []
    propose_rows: list[dict] = []
    for deck in decks:
        for c in deck.cards:
            if not c.viewed or c.undone or c.features is None:
                continue
            row = {
                "f": c.features,
                "user_id": c.user_id,
                "partner": (c.features or {}).get("partner_user_id"),
                "served_at": c.served_at,
                "position": _clip(c.card_index / _POSITION_NORM, 0.0, 1.0),
            }
            if c.liked or c.passed:
                like_rows.append({**row, "y": 1.0 if c.liked else 0.0})
            if c.liked:
                propose_rows.append({**row, "y": 1.0 if c.proposed else 0.0})
    like_rows.sort(key=lambda r: r["served_at"])
    propose_rows.sort(key=lambda r: r["served_at"])
    return like_rows, propose_rows


def _partner_rate_table(rows: list[dict]) -> tuple[dict[str, float], float]:
    """Laplace-smoothed per-(user, partner) like rate from FIT rows only
    (the calibration slice never leaks into its own features)."""
    n_pos = sum(r["y"] for r in rows)
    global_rate = (n_pos + 1.0) / (len(rows) + 2.0)
    acc: dict[str, list] = {}
    for r in rows:
        if not r.get("partner"):
            continue
        k = _partner_key(r["user_id"], r["partner"])
        slot = acc.setdefault(k, [0.0, 0])
        slot[0] += r["y"]
        slot[1] += 1
    return ({k: (pos + 1.0) / (n + 2.0) for k, (pos, n) in acc.items()},
            global_rate)


def _vectorize(rows: list[dict], model: "ValueModel") -> list[tuple[dict, float]]:
    return [
        (extract_features(model._inject(
            r["f"], r["user_id"], position=r["position"])), r["y"])
        for r in rows
    ]


def train_model(decks, *, now: datetime | None = None) -> ValueModel | None:
    """Fit both heads on all supplied decks (callers pass history ≤ now —
    the nightly refit passes everything; the time discipline for EVAL is
    F8's job, not this function's). Returns None when the like head lacks
    MIN_LIKE_ROWS/MIN_LIKE_POS — no model is better than a fake one."""
    now = now or datetime.now(timezone.utc)
    like_rows, propose_rows = build_training_rows(decks)
    n_like_pos = int(sum(r["y"] for r in like_rows))
    if len(like_rows) < MIN_LIKE_ROWS or n_like_pos < MIN_LIKE_POS:
        log.info("value model: insufficient labels (%d like rows, %d pos) — "
                 "not training", len(like_rows), n_like_pos)
        return None

    calib_frac = _clip(_cfg("value_model_calib_frac", 0.2), 0.05, 0.5)
    l2 = max(0.0, _cfg("value_model_l2", 0.01))
    l2_cat = max(0.0, _cfg("value_model_l2_cat", 0.5))
    split = max(1, int(len(like_rows) * (1.0 - calib_frac)))
    fit_rows, cal_rows = like_rows[:split], like_rows[split:]

    partner_rates, global_rate = _partner_rate_table(fit_rows)
    position_mean = (sum(r["position"] for r in fit_rows) / len(fit_rows))

    model = ValueModel(
        like_head=LogisticHead(),
        propose_head=None,
        propose_constant=0.0,
        partner_rates=partner_rates,
        global_like_rate=global_rate,
        position_mean=position_mean,
        trained_at=now.isoformat(),
        train_date=now.date().isoformat(),
    )

    model.like_head.fit(_vectorize(fit_rows, model), l2=l2, l2_cat=l2_cat)
    model.like_head.fit_platt(_vectorize(cal_rows, model))

    n_prop_pos = int(sum(r["y"] for r in propose_rows))
    model.propose_constant = (n_prop_pos + 1.0) / (len(propose_rows) + 2.0)
    if len(propose_rows) >= MIN_PROPOSE_ROWS and n_prop_pos >= MIN_PROPOSE_POS:
        psplit = max(1, int(len(propose_rows) * (1.0 - calib_frac)))
        p_fit, p_cal = propose_rows[:psplit], propose_rows[psplit:]
        head = LogisticHead()
        head.fit(_vectorize(p_fit, model), l2=l2, l2_cat=l2_cat)
        head.fit_platt(_vectorize(p_cal, model))
        model.propose_head = head

    model.meta = {
        "n_like_rows": len(like_rows), "n_like_pos": n_like_pos,
        "n_propose_rows": len(propose_rows), "n_propose_pos": n_prop_pos,
        "n_calibration_rows": len(cal_rows),
        "calib_frac": calib_frac, "l2": l2, "l2_cat": l2_cat,
        "propose_head": "lr" if model.propose_head else "constant",
    }
    return model


# ---------------------------------------------------------------------------
# Persistence — append-only JSONL, latest record wins (F8 eval_runs idiom)
# ---------------------------------------------------------------------------

def append_model(model: ValueModel) -> str:
    path = models_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": uuid.uuid4().hex,
        "train_date": model.train_date,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "model": model.to_dict(),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def _load_records() -> list[dict]:
    path = models_path()
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # torn write — skip, never crash a deck
    return records


# Serve-time cache: (path, mtime, size) → ValueModel, so a deck generation
# costs one os.stat, not a JSON parse.
_model_cache: tuple[tuple, ValueModel | None] | None = None


def load_latest_model(*, use_cache: bool = True) -> ValueModel | None:
    """The most recent parseable persisted model, or None. Never raises."""
    global _model_cache
    try:
        path = models_path()
        try:
            st = os.stat(path)
            cache_key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            cache_key = (path, None, None)
        if use_cache and _model_cache is not None and _model_cache[0] == cache_key:
            return _model_cache[1]
        model = None
        for rec in reversed(_load_records()):
            if isinstance(rec.get("model"), dict):
                try:
                    model = ValueModel.from_dict(rec["model"])
                    break
                except Exception:
                    continue
        _model_cache = (cache_key, model)
        return model
    except Exception as e:
        log.warning("value model load failed (soft-off): %s", e)
        return None


def latest_train_dates() -> set[str]:
    return {r.get("train_date") for r in _load_records() if r.get("train_date")}


# ---------------------------------------------------------------------------
# Nightly refit (daily-tick hook — flag-gated at the call site AND here)
# ---------------------------------------------------------------------------

def nightly_refit(*, engine=None, db_url: str | None = None,
                  now: datetime | None = None,
                  force: bool = False) -> dict:
    """Fit on ALL history ≤ now and append the model. Idempotent per UTC
    date (existing record for today ⇒ skip, so daily-tick retries are
    free — the F10/F8 convention). Never raises: the caller is a cron
    tick that must not fail. `force` is the CLI's re-train override."""
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    try:
        if not force and today in latest_train_dates():
            return {"status": "skipped", "reason": "already trained today",
                    "train_date": today}
        from backend.eval.data import load_decks
        decks = load_decks(engine=engine, db_url=db_url,
                           until=now.isoformat())
        model = train_model(decks, now=now)
        if model is None:
            return {"status": "skipped", "reason": "insufficient labels",
                    "train_date": today}
        path = append_model(model)
        return {"status": "trained", "train_date": today, "path": path,
                **model.meta}
    except Exception as e:
        log.warning("value model nightly refit failed (non-fatal): %s", e)
        return {"status": "error", "error": str(e), "train_date": today}


# ---------------------------------------------------------------------------
# Serving — the base-ordering scores for server._order_deck
# ---------------------------------------------------------------------------

def user_has_outcome_history(user_id: str, *, engine=None) -> bool:
    """≥1 deck_outcomes row joined to this user's impressions — the
    cold-start gate: a user the model has never observed gets the
    composite ordering exactly (PRD acceptance criterion)."""
    from sqlalchemy import select
    from .database import deck_impressions_table, deck_outcomes_table
    if engine is None:
        import backend.database as db_module
        engine = db_module.engine
    q = (
        select(deck_outcomes_table.c.id)
        .select_from(deck_outcomes_table.join(
            deck_impressions_table,
            deck_outcomes_table.c.impression_id
            == deck_impressions_table.c.impression_id))
        .where(deck_impressions_table.c.user_id == str(user_id))
        .limit(1)
    )
    with engine.connect() as conn:
        return conn.execute(q).first() is not None


def serving_scores(cards, *, user_id: str, league_id: str,
                   players_dict: dict, seed_map: dict,
                   scoring_format: str | None = None) -> dict | None:
    """{id(card): rank_score} for a generated deck, or None whenever the
    model must stay out: no persisted model, zero-history user, or any
    error (logged, soft-off — a scoring failure can NEVER fail a deck;
    the server call site try/excepts again, belt and braces).

    NOTE the caller contract: the flag check lives in server.py
    (_deck_value_scores) so this module stays import-safe for the CLI and
    the F8 scorer while the feature ships dark."""
    try:
        if not cards:
            return None
        model = load_latest_model()
        if model is None:
            return None
        if not user_has_outcome_history(user_id):
            return None
        ranked_count = None
        if scoring_format:
            try:
                from .database import load_board_state
                ranked_count, _ = load_board_state(
                    user_id, league_id, scoring_format)
            except Exception:
                ranked_count = None
        out: dict[int, float] = {}
        for c in cards:
            f = card_features(c, players_dict or {}, seed_map or {},
                              ranked_player_count=ranked_count)
            out[id(c)] = float(model.rank_score(f, user_id))
        return out
    except Exception as e:
        log.warning("value model serving failed (soft-off): %s", e)
        return None


# ---------------------------------------------------------------------------
# Operator CLI — the flag-independent trainer the graduation path needs
# (a model must exist BEFORE the flag flips, so the F8 replay can grade it)
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="python3 -m backend.value_model",
        description="F6 value-model operator tool (train/inspect).")
    ap.add_argument("--refit", action="store_true",
                    help="train on all history and append to models.jsonl")
    ap.add_argument("--force", action="store_true",
                    help="retrain even if a model exists for today")
    ap.add_argument("--db", help="SQLite path (or SQLAlchemy URL); "
                                 "default = backend.database engine")
    args = ap.parse_args(argv)

    db_url = None
    if args.db:
        db_url = args.db if "://" in args.db else f"sqlite:///{args.db}"

    if args.refit:
        stats = nightly_refit(db_url=db_url, force=args.force)
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0 if stats.get("status") in ("trained", "skipped") else 1

    model = load_latest_model(use_cache=False)
    if model is None:
        print("no persisted value model (train with --refit)")
        return 1
    print(json.dumps({"train_date": model.train_date,
                      "trained_at": model.trained_at, **model.meta},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
