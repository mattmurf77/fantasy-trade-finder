"""F5 (flag deck.taste_vectors) — trade-taste vectors.

docs/plans/tiktok-discovery/prds/F5-taste-vectors.md (incl. the 2026-07-26
board-derived-prior amendment). Per-user decayed attribute-preference
vectors over engineered card attributes — the Monolith long/short interest
split without embeddings. Elo learns *who* the user values; this module
learns *what kinds of trades* they take.

Three responsibilities, all flag-gated by the caller (backend/server.py):

  1. UPDATE — `update_taste_from_outcome` rides every F1 deck_outcomes
     write:  w[a] ← w[a]·exp(−Δt/τ) + r(action)  for both τ_short (21d)
     and τ_long (180d), on the attribute keys FROZEN into the impression's
     features_json at serve time (no label-time re-derivation → no
     training/serving skew). Rows are lazily created and GC'd when both
     decayed weights fall below taste_epsilon. Never throws.

  2. BOARD PRIOR — `compute_board_prior`/`refresh_board_prior`: the user's
     board is taste signal before a single swipe. Per ranked player,
     delta = user_value − consensus_value (elo_to_value over both boards —
     no re-derived valuation math), aggregated per player attribute,
     shrunk by per-attribute ranked count n/(n+taste_prior_shrink) and
     scaled so a strong full-board divergence ≈ the weight of
     ~taste_prior_scale likes. Stored as separate "prior:"-prefixed rows
     (rewritten wholesale on board saves) so swipe-learned weights
     accumulate on top and dominate with volume.

  3. SERVE — `taste_multipliers`: bounded multiplicative re-rank at
     generation,  final = base × (1 + η_l·prefMatch_long)
     × (1 + η_s·prefMatch_short)  clamped to [taste_clamp_lo,
     taste_clamp_hi], prefMatch = normalized cosine of the decayed vector
     against the card's attribute set. Zero-history user (no board, no
     swipes) ⇒ returns None so the ordering path is byte-identical to
     flag-off. Applied by server._order_deck AFTER every generation gate —
     taste reorders gate-passing candidates only; untouchables,
     not-interested, outlook filters and the surplus/fairness gates stay
     authoritative upstream and are never touched here. Composes
     multiplicatively with F3's fatigue discount (order immaterial).

Attribute space (~30–50 live keys per user; full list in the F5 build
report and docs/config-reference.md):
  shape:{G}x{R}            package shape bucket ("1x1" … "3x3")
  arch:{lane}              archetype label (today's lanes: window | value)
  window:aligned|off       window alignment, derived from the lane signal
  cpos:{POS}               centerpiece position (highest-consensus asset)
  givepos:{POS} / recvpos:{POS}    positions changing hands, per side
  giveband:{tier} / recvband:{tier}  per-asset mean value tier
                           (low <1800 | mid | high | elite ≥6000)
  giveage:{band} / recvage:{band}    age bands (u23|23-26|27-29|30plus)
  pick:none|mid|premium    pick involvement (premium = a 1st)
  partner:{user_id}        counterparty manager
POS ∈ {QB, RB, WR, TE, PICK}.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone

from .database import (
    load_deck_impression,
    load_user_taste,
    replace_user_taste_prior,
    replace_user_taste_rows,
)

log = logging.getLogger(__name__)

PRIOR_PREFIX = "prior:"

# Rewards mirror the Elo K ratios (PRD §2 / research §8). `accept`/`decline`
# are match-disposition semantics — deck_outcomes' action enum doesn't carry
# them today, so no server path emits them through this map yet (explicit
# handoff in the F5 build report); they're declared so the wiring is a
# one-liner when dispositions gain an impression join.
# Every key MUST be a member of database.DECK_OUTCOME_ACTIONS — enforced by
# test_taste_rewards_keys_are_legal_actions. This is not pedantry: the dict
# previously carried "accept" and "decline", which are NOT legal actions (the
# real labels are "accepted"/"declined") and which no writer could ever
# produce, so those rewards were dead while looking authoritative. P0-3 added
# the four disposition labels; they deliberately score 0.0 here because taste
# rewards for them are a separate, later PR — but a future author who
# hand-adds "accept" back would silently get nothing. The test makes that
# mistake fail loudly instead.
TASTE_REWARDS: dict[str, float] = {
    "like":            1.0,
    "propose":         6.0,
    "pass":           -0.5,
    "not_interested": -4.0,
    "viewed":          0.0,   # participates only via the long-dwell bonus
    "undo":            0.0,   # appends alongside the original outcome; no taste signal
}

_POSITIONS = ("QB", "RB", "WR", "TE", "PICK")


def _cfg(key: str, default: float) -> float:
    """model_config key via trade_service's live config dict (the
    server._deck_cfg pattern). Defaults inline so a missing key never
    breaks an outcome write or deck generation. Keys are declared in
    trade_service._DEFAULT_CFG and documented in docs/config-reference.md."""
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get(key, default))
    except Exception:
        return float(default)


# ---------------------------------------------------------------------------
# Attribute derivation
# ---------------------------------------------------------------------------

def _value_tier(per_asset_value) -> str | None:
    """Coarse per-asset value tier. Deliberately coarser than F1's 500-wide
    features_json bands: four tiers generalize across the sparse per-user
    event volume where 500-wide buckets would fragment it."""
    if not isinstance(per_asset_value, (int, float)):
        return None
    v = float(per_asset_value)
    if v >= 6000:
        return "elite"
    if v >= 3500:
        return "high"
    if v >= 1800:
        return "mid"
    return "low"


def _age_band(age) -> str | None:
    if not isinstance(age, (int, float)) or age <= 0:
        return None
    a = float(age)
    if a < 23:
        return "u23"
    if a < 27:
        return "23-26"
    if a < 30:
        return "27-29"
    return "30plus"


def _is_pick(player) -> bool:
    """Pick pseudo-asset detection covering both families: owned picks
    (position "PICK") and the universal pool's generic picks (team "PICK",
    id "generic_pick_*", real position for trio mixing)."""
    if player is None:
        return False
    if getattr(player, "position", None) == "PICK":
        return True
    if getattr(player, "team", None) == "PICK":
        return True
    pid = str(getattr(player, "id", "") or "")
    return pid.startswith("generic_pick_")


def _pick_tier(player) -> str:
    """premium = a 1st (generic_pick_1_* / "… 1st …" owned-pick label),
    mid = everything else. Coarse by design — round is the only reliably
    derivable slot signal."""
    pid = str(getattr(player, "id", "") or "")
    name = str(getattr(player, "name", "") or "")
    if pid.startswith("generic_pick_1_") or "1st" in name:
        return "premium"
    return "mid"


def _asset_pos(player) -> str | None:
    if _is_pick(player):
        return "PICK"
    pos = getattr(player, "position", None)
    return pos if pos in _POSITIONS else None


def card_taste_attrs(card, players_dict: dict, seed_map: dict) -> list[str]:
    """The card's taste-attribute keys, computed at generation from
    attributes the pipeline already carries (no new heavy computation).
    Frozen into features_json["taste_attrs"] by the F1 impression writer
    while the flag is on, so outcome-time updates never re-derive them."""
    give = [str(p) for p in (getattr(card, "give_player_ids", None) or [])]
    recv = [str(p) for p in (getattr(card, "receive_player_ids", None) or [])]
    attrs: set[str] = set()

    attrs.add(f"shape:{len(give)}x{len(recv)}")

    lane = getattr(card, "lane", None)
    if lane:
        attrs.add(f"arch:{lane}")
        # Window alignment reuses the lane signal: "window" is by
        # construction a move aligned with the user's declared/inferred
        # window; "value" is window-neutral (classify_lane docstring).
        attrs.add("window:aligned" if lane == "window" else "window:off")

    pids = give + recv
    if pids:
        # Same centerpiece definition as F3 (highest-consensus asset,
        # deterministic id tie-break) — the two layers must agree.
        center = max(pids, key=lambda p: (float((seed_map or {}).get(p, 1500.0)), p))
        cpos = _asset_pos(players_dict.get(center))
        if cpos:
            attrs.add(f"cpos:{cpos}")

    pick_tier: str | None = None
    for side, pos_prefix, age_prefix in (
        (give, "givepos", "giveage"),
        (recv, "recvpos", "recvage"),
    ):
        for pid in side:
            p = players_dict.get(pid)
            pos = _asset_pos(p)
            if pos is None:
                continue
            attrs.add(f"{pos_prefix}:{pos}")
            if pos == "PICK":
                tier = _pick_tier(p)
                if tier == "premium" or pick_tier == "premium":
                    pick_tier = "premium"
                else:
                    pick_tier = "mid"
            else:
                band = _age_band(getattr(p, "age", None))
                if band:
                    attrs.add(f"{age_prefix}:{band}")
    attrs.add(f"pick:{pick_tier or 'none'}")

    gv = getattr(card, "give_value", None)
    rv = getattr(card, "receive_value", None)
    if isinstance(gv, (int, float)) and give:
        tier = _value_tier(float(gv) / len(give))
        if tier:
            attrs.add(f"giveband:{tier}")
    if isinstance(rv, (int, float)) and recv:
        tier = _value_tier(float(rv) / len(recv))
        if tier:
            attrs.add(f"recvband:{tier}")

    target = getattr(card, "target_user_id", None)
    if target:
        attrs.add(f"partner:{target}")

    return sorted(attrs)


def attrs_from_features(features: dict) -> list[str]:
    """Attribute keys for an outcome update, from the impression's FROZEN
    features_json. Prefers the serve-time "taste_attrs" list (stamped while
    the flag is on — zero skew). Fallback for impressions frozen before the
    flag flipped: re-derive the subset computable from F1's frozen fields
    alone (no age/centerpiece keys — those need player objects; a pick's
    tier degrades to "mid")."""
    if not isinstance(features, dict):
        return []
    ta = features.get("taste_attrs")
    if isinstance(ta, list) and ta:
        return sorted({str(a) for a in ta if a})

    attrs: set[str] = set()
    shape = features.get("shape")
    if shape:
        attrs.add(f"shape:{shape}")
    lane = features.get("lane")
    if lane:
        attrs.add(f"arch:{lane}")
        attrs.add("window:aligned" if lane == "window" else "window:off")
    give_pos = [p for p in (features.get("give_positions") or []) if p in _POSITIONS]
    recv_pos = [p for p in (features.get("receive_positions") or []) if p in _POSITIONS]
    for pos in give_pos:
        attrs.add(f"givepos:{pos}")
    for pos in recv_pos:
        attrs.add(f"recvpos:{pos}")
    gv = features.get("give_value")
    if isinstance(gv, (int, float)) and give_pos:
        tier = _value_tier(float(gv) / len(give_pos))
        if tier:
            attrs.add(f"giveband:{tier}")
    rv = features.get("receive_value")
    if isinstance(rv, (int, float)) and recv_pos:
        tier = _value_tier(float(rv) / len(recv_pos))
        if tier:
            attrs.add(f"recvband:{tier}")
    attrs.add("pick:mid" if features.get("involves_pick") else "pick:none")
    partner = features.get("partner_user_id")
    if partner:
        attrs.add(f"partner:{partner}")
    return sorted(attrs)


# ---------------------------------------------------------------------------
# Decay + synchronous updates
# ---------------------------------------------------------------------------

def _age_days(iso_ts, now: datetime) -> float:
    """Fractional days since an ISO timestamp; 0.0 when unparseable or in
    the future (a clock skew must never AMPLIFY a weight)."""
    if not iso_ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(iso_ts))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def _decay(w: float, dt_days: float, tau_days: float) -> float:
    return float(w) * math.exp(-max(0.0, dt_days) / max(1e-9, tau_days))


def _reward_for(action: str, dwell_ms=None) -> float:
    reward = float(TASTE_REWARDS.get(action, 0.0))
    if (isinstance(dwell_ms, (int, float)) and not isinstance(dwell_ms, bool)
            and float(dwell_ms) >= _cfg("taste_dwell_ms", 8000.0)):
        # Long-dwell bonus — hesitation is interest, whatever the verdict:
        # a long-considered pass (−0.5 + 0.3) is less negative than a flick.
        reward += _cfg("taste_dwell_bonus", 0.3)
    return reward


def update_taste_from_outcome(impression_id: str, action: str, dwell_ms=None) -> None:
    """Synchronous taste update riding an F1 outcome write (the minute-level
    Monolith sync miniaturized to one SQL transaction at FTF QPS).

    Never throws — the caller is the never-throwing _save_deck_outcome_safe
    and this hook must not weaken that contract. Zero-reward actions
    (viewed without a long dwell, undo, unknown) write nothing; unknown
    impression ids write nothing. Prior rows are never touched here."""
    try:
        reward = _reward_for(action, dwell_ms)
        if reward == 0.0:
            return
        imp = load_deck_impression(impression_id)
        if not imp:
            return
        try:
            features = json.loads(imp.get("features_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            features = {}
        attrs = attrs_from_features(features)
        if not attrs:
            return

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        tau_s = _cfg("taste_tau_short_days", 21.0)
        tau_l = _cfg("taste_tau_long_days", 180.0)
        eps   = _cfg("taste_epsilon", 0.05)

        wanted = set(attrs)
        existing = {r["attr"]: r for r in load_user_taste(imp["user_id"])
                    if r["attr"] in wanted}
        upserts: dict[str, tuple] = {}
        deletes: list[str] = []
        for a in attrs:
            row = existing.get(a)
            if row:
                dt = _age_days(row["updated_at"], now)
                w_s = _decay(row["w_short"], dt, tau_s) + reward
                w_l = _decay(row["w_long"], dt, tau_l) + reward
            else:
                w_s = w_l = reward
            if abs(w_s) < eps and abs(w_l) < eps:
                if row:
                    deletes.append(a)     # GC on update (admission/expiry)
                continue
            upserts[a] = (w_s, w_l, now_iso)
        replace_user_taste_rows(imp["user_id"], upserts, deletes)
    except Exception as e:
        log.warning("taste update failed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# Reads (decayed, prior-merged, GC on read)
# ---------------------------------------------------------------------------

def load_taste_vectors(user_id: str) -> tuple[dict, dict]:
    """(short, long) decayed weight dicts for one user, at read time.

    - Learned rows decay lazily from updated_at (no cron mutates state);
      rows whose BOTH decayed weights fell below ε are GC'd here (read-side
      expiry — the write side GC's on update).
    - "prior:" rows fold their mass into the LONG vector under the base
      attr (the prior is a long-interest warm start). They are not
      time-decayed: board saves rewrite them wholesale, so their staleness
      is bounded by board activity, and swipe-learned mass accumulates on
      top of them either way.
    Empty dicts ⇒ zero-history user ⇒ the serving layer stays out entirely."""
    now = datetime.now(timezone.utc)
    tau_s = _cfg("taste_tau_short_days", 21.0)
    tau_l = _cfg("taste_tau_long_days", 180.0)
    eps   = _cfg("taste_epsilon", 0.05)

    short: dict[str, float] = {}
    long_: dict[str, float] = {}
    gc: list[str] = []
    for r in load_user_taste(user_id):
        attr = r["attr"]
        if attr.startswith(PRIOR_PREFIX):
            base = attr[len(PRIOR_PREFIX):]
            v = float(r["w_long"])
            if abs(v) >= eps:
                long_[base] = long_.get(base, 0.0) + v
            continue
        dt  = _age_days(r["updated_at"], now)
        w_s = _decay(r["w_short"], dt, tau_s)
        w_l = _decay(r["w_long"], dt, tau_l)
        if abs(w_s) < eps and abs(w_l) < eps:
            gc.append(attr)
            continue
        short[attr] = short.get(attr, 0.0) + w_s
        long_[attr] = long_.get(attr, 0.0) + w_l
    if gc:
        try:
            replace_user_taste_rows(user_id, {}, gc)
        except Exception as e:
            log.warning("taste read-side GC failed (non-fatal): %s", e)
    return short, long_


def _pref_match(weights: dict, attrs: list[str]) -> float:
    """Normalized cosine of the taste vector against the card's binary
    attribute indicator: Σ w[a∈card] / (‖w‖ · √|card attrs|) ∈ [−1, 1].
    0.0 whenever either side is empty — the no-signal anchor."""
    if not weights or not attrs:
        return 0.0
    num = sum(weights.get(a, 0.0) for a in attrs)
    if num == 0.0:
        return 0.0
    w_norm = math.sqrt(sum(v * v for v in weights.values()))
    if w_norm <= 0.0:
        return 0.0
    return num / (w_norm * math.sqrt(len(attrs)))


def taste_multipliers(
    cards: list,
    *,
    user_id: str,
    players_dict: dict,
    seed_map: dict,
) -> dict | None:
    """{id(card): clamped multiplier} for a generated deck, or None when
    the user has no taste signal at all (no board prior, no swipe-learned
    rows) — the zero-history contract: the caller then skips the layer and
    ordering is byte-identical to flag-off. Any read failure degrades to
    None — generation never breaks."""
    if not cards:
        return None
    try:
        short, long_ = load_taste_vectors(user_id)
    except Exception as e:
        log.warning("taste vector read failed (soft-off): %s", e)
        return None
    if not short and not long_:
        return None

    eta_l = _cfg("taste_eta_long", 0.2)
    eta_s = _cfg("taste_eta_short", 0.3)
    lo    = _cfg("taste_clamp_lo", 0.7)
    hi    = max(lo, _cfg("taste_clamp_hi", 1.4))

    out: dict[int, float] = {}
    for c in cards:
        attrs = card_taste_attrs(c, players_dict or {}, seed_map or {})
        m = ((1.0 + eta_l * _pref_match(long_, attrs))
             * (1.0 + eta_s * _pref_match(short, attrs)))
        out[id(c)] = min(hi, max(lo, m))
    return out


# ---------------------------------------------------------------------------
# Board-derived prior (PRD amendment 2026-07-26)
# ---------------------------------------------------------------------------

def player_prior_attrs(player, consensus_value) -> list[str]:
    """The attribute keys a ranked player's board-vs-consensus delta feeds.
    Receive-oriented on purpose: valuing an attribute above consensus means
    wanting to ACQUIRE it, so the prior lands on the keys a card earns for
    offering it (recvpos/cpos/recvage/recvband/pick) rather than splitting
    ambiguously across both sides."""
    attrs: list[str] = []
    pos = _asset_pos(player)
    if pos:
        attrs.append(f"recvpos:{pos}")
        attrs.append(f"cpos:{pos}")
    if pos == "PICK":
        attrs.append(f"pick:{_pick_tier(player)}")
    else:
        band = _age_band(getattr(player, "age", None))
        if band:
            attrs.append(f"recvage:{band}")
    tier = _value_tier(consensus_value)
    if tier:
        attrs.append(f"recvband:{tier}")
    return attrs


def compute_board_prior(entries) -> dict:
    """Aggregate systematic board-vs-consensus deltas into per-attribute
    prior mass.

    entries: iterable of (player, user_elo, seed_elo) for players the user
    has actually priced away from consensus (the caller filters — an
    untouched player sits exactly at seed and carries no signal).

    Per player: rel_delta = clamp((user_value − consensus_value) /
    consensus_value, ±1) via trade_service.elo_to_value on BOTH Elos (the
    engine's own valuation map — nothing re-derived). Per attribute:
    prior[a] = taste_prior_scale · n/(n+taste_prior_shrink)
               · clamp(mean_rel_delta / taste_prior_ref_delta, ±1)
    so a full board diverging ≥ taste_prior_ref_delta on an attribute
    approaches taste_prior_scale ≈ the weight of that many likes — a warm
    start swipe volume overtakes, not a ceiling. Sub-ε attrs are dropped."""
    from .trade_service import elo_to_value

    acc: dict[str, list] = {}   # attr -> [delta_sum, n]
    for player, user_elo, seed_elo in entries:
        try:
            cv = float(elo_to_value(float(seed_elo)))
            uv = float(elo_to_value(float(user_elo)))
        except Exception:
            continue
        if cv <= 0:
            continue
        rel = max(-1.0, min(1.0, (uv - cv) / cv))
        for a in player_prior_attrs(player, cv):
            slot = acc.setdefault(a, [0.0, 0])
            slot[0] += rel
            slot[1] += 1

    scale    = _cfg("taste_prior_scale", 10.0)
    shrink_n = max(0.0, _cfg("taste_prior_shrink", 20.0))
    ref      = max(1e-6, _cfg("taste_prior_ref_delta", 0.25))
    eps      = _cfg("taste_epsilon", 0.05)

    prior: dict[str, float] = {}
    for a, (delta_sum, n) in acc.items():
        if n <= 0:
            continue
        mean = delta_sum / n
        val = scale * (n / (n + shrink_n)) * max(-1.0, min(1.0, mean / ref))
        if abs(val) >= eps:
            prior[a] = val
    return prior


def refresh_board_prior(user_id: str, entries) -> dict:
    """Compute + persist the board prior in one call (board-save hook).
    Rewrites the "prior:" block wholesale — including clearing it when the
    board stopped diverging. Returns the stored prior (for tests/inspection)."""
    prior = compute_board_prior(entries)
    replace_user_taste_prior(
        user_id, prior, datetime.now(timezone.utc).isoformat())
    return prior
