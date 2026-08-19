"""
bakeoff_runner.py — three-model bake-off runner (Phase 3).

Spec: docs/plans/three-model-bakeoff/PLAN.md §3, §3.4, §4, §5.
Scope block: docs/plans/three-model-bakeoff/scope-phase3.md.

One trade job fans out into three generations, the three ranked lists are
merged by team-draft interleaving, and every served card carries the arm that
produced it.

    A `baseline` — the live engine inside `bakeoff_profiles.model_a()` (the
                   pinned MODEL_A_PROFILE + the arm-A R4 bypass, both
                   golden-tested by Phase 2).
    B `current`  — the live engine at live defaults. No override.
    C `gen_v2`   — backend/trade_gen_v2.py, called directly.

Arm C is invoked REGARDLESS of the `trade_gen.v2` flag. That flag gates the
*normal serving path* — whether `_generate_trades_impl` routes the whole deck
through the v2 pipeline instead of the v1/v3 engine. The bake-off does not
route; it calls the module as a third generator and attributes its output
separately, so `trade_gen.v2` stays FALSE for the entire bake-off and arms A/B
keep running the engine they are supposed to be.

Everything here is behind `trade.bakeoff`, default OFF. Flag off ⇒ this module
is never imported by the generation path and every deck is byte-identical.

Measurement hygiene (PLAN.md §3.4)
----------------------------------
Channel 1 — arms teaching the shared board. `elo_freeze_mult()` zeroes the
trade-swipe K factors (`trade_k_like` / `trade_k_pass`) for the duration of the
run, severing the arm → board → arm loop. Ranking votes (`elo_k`) are
deliberately untouched.

The threshold a card was generated under is captured too — see
`effective_fairness_threshold()`. `fairness_threshold` arrives per-request from
the client and was previously persisted NOWHERE
(docs/reviews/2026-08-18-trade-logic-archaeology.md), so a per-arm comparison
spanning sessions with different client settings would have compared arms AND
thresholds at once, with nothing in the data to separate them.

Channel 2 — post-generation reordering. `bypass_rerankers()` is the single
predicate the serving path consults. When interleaved serving is on, EVERY
layer that reorders after generation is bypassed for that deck (F2 Thompson,
A6 diversity + per-target cap, F3 fatigue multipliers, F5 taste, F6 value
model, F7 wildcard insert, F9 first-session shaping), so the deck order the
user sees is exactly the interleaver's output. See scope-phase3.md §4 for why
bypass was chosen over per-arm pre-interleave application.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Callable

from .bakeoff_profiles import model_a
from .feature_flags import is_enabled

log = logging.getLogger(__name__)

ARM_BASELINE = "baseline"
ARM_CURRENT  = "current"
ARM_GEN_V2   = "gen_v2"

#: Canonical arm names. Order here is the DRAFT rotation's base ordering, not
#: the generation order (see GENERATION_ORDER) and not the served order (the
#: rotation is shuffled per deck).
ARMS: tuple[str, ...] = (ARM_BASELINE, ARM_CURRENT, ARM_GEN_V2)

#: Arm B runs FIRST so the user's progress bar and the streaming card
#: snapshots track the arm that is served in dark mode (Phase 4) and that the
#: deck falls back to if the interleave yields nothing. Arms A and C run with
#: progress streaming suppressed — publishing arm-A cards mid-job would show
#: the user un-interleaved, un-attributed baseline cards.
GENERATION_ORDER: tuple[str, ...] = (ARM_CURRENT, ARM_BASELINE, ARM_GEN_V2)

#: The single arm served in Phase-4 dark validation.
DARK_SERVED_ARM = ARM_CURRENT


# ---------------------------------------------------------------------------
# Flag + knobs
# ---------------------------------------------------------------------------

def bakeoff_enabled() -> bool:
    """`trade.bakeoff` — the one switch. OFF (default) ⇒ no fan-out, no
    interleave, no attribution columns stamped, no bakeoff_runs row, and the
    swipe K factors are untouched."""
    return is_enabled("trade.bakeoff")


def _cfg(key: str, default: float) -> float:
    """model_config value via trade_service's live dict (same pattern as
    server._deck_cfg). Defaults inline so a missing key never breaks a job."""
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get(key, default))
    except Exception:
        return float(default)


def serve_interleaved() -> bool:
    """Phase 5 (interleaved serving) vs Phase 4 (dark validation).

    `bakeoff_serve_interleaved` defaults to 0.0 = DARK: all three arms
    generate and log, only arm B is served, and the normal presentation stack
    runs untouched — zero user-visible risk. The operator flips the knob to
    1.0 (config only, no deploy) to light interleaved serving."""
    return bakeoff_enabled() and _cfg("bakeoff_serve_interleaved", 0.0) >= 1.0


def deck_limit() -> int | None:
    """`bakeoff_deck_limit` — max cards in an interleaved deck. 0 (default) =
    uncapped: the draft drains every arm. The knob is the lever PLAN.md §8
    calls for if 3× supply proves too much deck."""
    n = int(_cfg("bakeoff_deck_limit", 0.0))
    return n if n > 0 else None


def elo_freeze_mult(fit_mult: float) -> float:
    """§3.4 Channel 1 — zero the trade-swipe K factors while the bake-off runs.

    Applied at the K multiplier both swipe paths already share (the in-memory
    `RankingService.record_trade_signal(fit_mult=…)` and the `swipe_decisions`
    row's stored `k_factor`), so the live board and the DB replay agree.
    Flag off ⇒ returns `fit_mult` unchanged."""
    return 0.0 if bakeoff_enabled() else fit_mult


def bakeoff_active(league_id: str, pinned_give, pinned_receive,
                   opponent_user_id) -> bool:
    """Per-deck gate. ORGANIC guided decks only — a pinned ("what can I get
    for X?") or opponent-scoped deck is explicit user intent, and arm C
    ignores half of that targeting, so interleaving there would degrade the
    deck AND compare arms on unequal briefs. Same restriction the ghost
    holdout uses, for the same reason."""
    return (
        bakeoff_enabled()
        and league_id != "league_demo"
        and not pinned_give and not pinned_receive and not opponent_user_id
    )


def bypass_rerankers(league_id: str, pinned_give, pinned_receive,
                     opponent_user_id) -> bool:
    """§3.4 Channel 2 — True when this deck's order belongs to the interleaver
    and no post-generation layer may touch it.

    Deliberately False in dark mode: Phase 4 serves arm B through the NORMAL
    presentation stack, so dark validation measures cost and plumbing without
    changing what any user sees."""
    return serve_interleaved() and bakeoff_active(
        league_id, pinned_give, pinned_receive, opponent_user_id)


def policy_version_for_arm(base_policy_version: str | None, arm: str | None) -> str | None:
    """Encode the arm into `deck_impressions.policy_version` (PLAN.md §5).
    `model_arm` carries the same value denormalized, so queries never parse
    this string — it exists so an impression row is self-describing even when
    read through the pre-bake-off policy_version lens."""
    if not arm:
        return base_policy_version
    return f"{base_policy_version or 'unknown'}/bo:{arm}"


# ---------------------------------------------------------------------------
# Configuration capture (PLAN.md §6 "which configuration produced this card")
# ---------------------------------------------------------------------------

def snapshot_config() -> dict:
    """The effective `trade_service` config ON THIS THREAD, i.e. including any
    active `_cfg_override` overlay. Called inside each arm's own context, so
    arm A's snapshot reflects MODEL_A_PROFILE and arms B/C reflect live values.

    `model_config` has no `updated_at`, so a knob's change date is unknowable
    after the fact. Snapshotting per run sidesteps that for the bake-off
    specifically: every card is traceable to the configuration that produced
    it, whatever anyone later does to the table."""
    from .trade_service import _DEFAULT_CFG, _c
    return {k: _c(k) for k in _DEFAULT_CFG}


def effective_fairness_threshold(card, requested: float | None,
                                 config: dict | None) -> float | None:
    """The consensus fairness bar this card ACTUALLY had to clear.

    The requested value (the client's fairness toggle: 0.75 on / 0.50 off) is
    not the whole story — the engine composes it with two knobs, and both
    compositions are card-dependent, which is why this is recorded per CARD
    rather than per job:

      * a **relaxed** card (#189 stage 1, reachable on an organic deck via the
        user's acquire / trade-away position preferences) was generated after
        the band widened to `min(requested, relaxed_fairness_threshold)`;
      * a **divergence** card is gated at `min(…, fairness_floor_divergence)`
        — both members have real boards, so the consensus check is only an
        extreme-case veto (`trade_service._DEFAULT_CFG` comment, 2026-07-17);
      * a **consensus** card keeps the full bar (consensus IS the board there).

    Returns None for arm `gen_v2`: `trade_gen_v2.generate_league_suggestions`
    takes no `fairness_threshold` at all — its admission bar is the `gen2_*`
    dual-board ε stack. NULL there is the honest answer, not missing data, and
    it is itself the fact a reader needs: an arm-C card was never subject to
    the client's fairness toggle.
    """
    if requested is None:
        return None
    thr = float(requested)
    cfg = config or {}
    if getattr(card, "relaxed", False):
        thr = min(thr, float(cfg.get("relaxed_fairness_threshold", thr)))
    if getattr(card, "basis", "divergence") == "divergence":
        thr = min(thr, float(cfg.get("fairness_floor_divergence", thr)))
    return thr


# ---------------------------------------------------------------------------
# Card identity
# ---------------------------------------------------------------------------

def card_key(card) -> tuple:
    """"Same trade" identity for the draft: the asset sets plus the partner.
    Deliberately the same components as server._deck_trade_hash (which hashes
    them), defined locally so the runner does not import the server."""
    give = tuple(sorted(getattr(card, "give_player_ids", None) or []))
    recv = tuple(sorted(getattr(card, "receive_player_ids", None) or []))
    return (give, recv, getattr(card, "target_user_id", None))


# ---------------------------------------------------------------------------
# Arm order — seeded per deck
# ---------------------------------------------------------------------------

def iso_week_of(now: datetime | None = None) -> str:
    """ISO year-week, e.g. '2026-W34'."""
    d = now or datetime.now(timezone.utc)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def arm_order_for(league_id: str, iso_week: str | None = None) -> list[str]:
    """Randomised draft rotation, seeded on league_id + ISO week (PLAN.md §4
    step 2): stable for a league across a week — so a re-run of the same job
    reproduces the same deck — and rotated between weeks, so no arm is
    permanently stuck in slot 3. hashlib, not hash(): Python salts str hashes
    per process."""
    week = iso_week or iso_week_of()
    seed = int(hashlib.sha256(f"{league_id}|{week}".encode()).hexdigest()[:16], 16)
    order = list(ARMS)
    random.Random(seed).shuffle(order)
    return order


# ---------------------------------------------------------------------------
# Team-draft interleaving (PLAN.md §4)
# ---------------------------------------------------------------------------

@dataclass
class DraftResult:
    deck: list = field(default_factory=list)
    #: id(card) → (arm, arm_rank) — arm_rank is the card's 0-based rank in
    #: its OWN arm's ranked list, never its deck position.
    attribution: dict = field(default_factory=dict)
    #: id(card) → [other arms whose full list also contains this trade]
    also_proposed_by: dict = field(default_factory=dict)
    #: arm → number of rotation slots the arm could not fill
    forfeits: dict = field(default_factory=dict)


def team_draft(arm_lists: dict[str, list], arm_order: list[str],
               limit: int | None = None) -> DraftResult:
    """Team-draft interleave of per-arm ranked lists.

    Algorithm, exactly:

      1. Each arm keeps a cursor into its own ranked list, starting at 0.
      2. Rotate through `arm_order`. On its turn an arm advances its cursor
         past any card whose `card_key` is already in the deck (another arm
         proposed the same trade and picked it first), then contributes the
         card at its cursor and advances by one.
      3. The card is credited to the arm that picked it, at its rank within
         that arm's own list. Credit is FIRST-PICKER: agreement never
         double-counts a card.
      4. An arm whose cursor has run past the end of its list forfeits its
         slot to the next arm in the rotation, and the forfeit is counted.
      5. Stop when the deck reaches `limit`, or when a full rotation
         contributes nothing (every arm exhausted).

    Agreement is then computed by a full membership scan over every arm's
    complete list — so `also_proposed_by` records every arm that proposed a
    served trade, including arms whose cursor never reached it.
    """
    order = [a for a in arm_order if a in arm_lists]
    cursors = {arm: 0 for arm in order}
    forfeits = {arm: 0 for arm in order}
    taken: set = set()
    res = DraftResult(forfeits=forfeits)

    total = sum(len(arm_lists[a]) for a in order)
    cap = total if limit is None else min(limit, total)

    while len(res.deck) < cap:
        progressed = False
        for arm in order:
            if len(res.deck) >= cap:
                break
            lst = arm_lists[arm]
            i = cursors[arm]
            while i < len(lst) and card_key(lst[i]) in taken:
                i += 1
            cursors[arm] = i
            if i >= len(lst):
                forfeits[arm] += 1
                continue
            card = lst[i]
            res.deck.append(card)
            res.attribution[id(card)] = (arm, i)
            taken.add(card_key(card))
            cursors[arm] = i + 1
            progressed = True
        if not progressed:
            break

    # Agreement — full membership scan, independent of how far each cursor got.
    members: dict[tuple, set] = defaultdict(set)
    for arm in order:
        for c in arm_lists[arm]:
            members[card_key(c)].add(arm)
    for card in res.deck:
        credited, _rank = res.attribution[id(card)]
        others = sorted(members[card_key(card)] - {credited})
        if others:
            res.also_proposed_by[id(card)] = others

    return res


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------

@dataclass
class ArmResult:
    arm: str
    cards: list
    gen_ms: int
    error: str | None = None
    #: The `fairness_threshold` this arm was INVOKED with. None for `gen_v2`,
    #: which takes no such argument. Captured per arm rather than per job
    #: because arm A runs under MODEL_A_PROFILE and could in principle diverge
    #: — recorded, never assumed to match.
    fairness_threshold: float | None = None
    #: The effective trade_service config INSIDE this arm's context.
    config: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.cards


@dataclass
class BakeoffRun:
    run_id: str
    arm_order: list[str]
    arms: dict[str, ArmResult]
    draft: DraftResult
    served_arm: str | None      # None ⇒ interleaved serving
    total_ms: int

    @property
    def deck(self) -> list:
        """The interleaved deck. In dark mode this is still computed and
        logged — it is just not what gets served."""
        return self.draft.deck

    def served_deck(self) -> list:
        """What the job should actually serve."""
        if self.served_arm is None:
            return list(self.draft.deck)
        return list(self.arms[self.served_arm].cards)

    def attribution_for(self, card) -> tuple[str, int] | None:
        """(arm, arm_rank) for a card, or None when it came from outside the
        bake-off (a likes-you injection, say). In dark mode the served cards
        are arm B's own objects, so the draft attribution still resolves them
        — unless the draft credited that trade to another arm first, in which
        case the served copy falls back to (served_arm, its own rank)."""
        hit = self.draft.attribution.get(id(card))
        if hit is not None:
            return hit
        if self.served_arm is not None:
            try:
                rank = self.arms[self.served_arm].cards.index(card)
            except ValueError:
                return None
            return (self.served_arm, rank)
        return None

    def also_proposed_by(self, card) -> list[str]:
        return list(self.draft.also_proposed_by.get(id(card), ()))

    def fairness_threshold_for(self, card) -> float | None:
        """The consensus fairness bar this served card actually cleared,
        resolved against the config ITS OWN arm ran under."""
        hit = self.attribution_for(card)
        if hit is None:
            return None
        arm = self.arms.get(hit[0])
        if arm is None:
            return None
        return effective_fairness_threshold(
            card, arm.fairness_threshold, arm.config)

    def config_record(self) -> dict:
        """`{"base": <arm current's effective config>, "arm_delta": {arm: {...}}}`.

        Stored whole rather than fingerprinted because `model_config` has no
        `updated_at`: a hash would tell a later reader that the configuration
        changed without telling them what it changed to, which is the same
        archaeology problem one step removed. ~5 KB base + a handful of delta
        keys per run — arm A's delta is essentially MODEL_A_PROFILE, arm C's is
        empty. Deliberately NOT a config-versioning system: one snapshot per
        run, no history, no dedup."""
        base = dict(self.arms[ARM_CURRENT].config or {})
        delta = {}
        for arm, r in self.arms.items():
            if arm == ARM_CURRENT:
                continue
            delta[arm] = {k: v for k, v in (r.config or {}).items()
                          if base.get(k) != v}
        return {"base": base, "arm_delta": delta}

    def run_row(self, *, job_id: str, user_id: str, league_id: str) -> dict:
        """The `bakeoff_runs` row (PLAN.md §5)."""
        arms_summary = {
            arm: {
                "cards":    len(r.cards),
                "gen_ms":   r.gen_ms,
                "empty":    r.empty,
                "forfeits": self.draft.forfeits.get(arm, 0),
                "served":   len([c for c in self.draft.deck
                                 if self.draft.attribution.get(id(c), (None,))[0] == arm]),
                "error":    r.error,
                # The threshold this arm was INVOKED with (null for gen_v2,
                # which takes none). Per arm, not per job: arm A runs under
                # MODEL_A_PROFILE, so agreement is recorded, never assumed.
                "fairness_threshold": r.fairness_threshold,
            }
            for arm, r in self.arms.items()
        }
        agree: dict[str, int] = defaultdict(int)
        for card in self.draft.deck:
            credited, _ = self.draft.attribution[id(card)]
            for other in self.draft.also_proposed_by.get(id(card), ()):
                agree["+".join(sorted((credited, other)))] += 1
        return {
            "run_id":      self.run_id,
            "deck_job_id": job_id,
            "user_id":     user_id,
            "league_id":   league_id,
            "arm_order":   json.dumps(self.arm_order),
            "served_arm":  self.served_arm,
            "deck_size":   len(self.draft.deck),
            "total_ms":    self.total_ms,
            "arms_json":   json.dumps(arms_summary),
            "agreement_json": json.dumps(dict(agree)),
            "config_json": json.dumps(self.config_record()),
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }


def gen_v2_cards(trade_service, kwargs: dict) -> list:
    """Arm C — `trade_gen_v2.generate_league_suggestions` called DIRECTLY.

    Invoked regardless of the `trade_gen.v2` flag. That flag decides whether
    `TradeService._generate_trades_impl` ROUTES the whole deck through the v2
    pipeline instead of the v1/v3 engine; it is a serving-path switch, not a
    module guard. The bake-off does not route — it calls the module as a
    third generator and attributes its output separately — so `trade_gen.v2`
    stays FALSE for the whole bake-off and arms A/B keep running the engine
    they are meant to be.

    Mirrors the kwargs `_generate_trades_impl` passes on its v2 branch,
    including the stud-tax pin `generate_trades` applies for arms A/B (arm C
    bypasses that wrapper, so the pin is re-applied here or arm C would price
    packages differently for a reason that has nothing to do with the model).
    """
    from .trade_gen_v2 import generate_league_suggestions
    from .trade_service import (pinned_stud_tax_mode, stud_tax_mode_for_user,
                                stud_tax_override)

    league = trade_service._leagues.get(kwargs["league_id"])
    if league is None:
        return []
    past_keys = set(getattr(trade_service, "_past_decision_keys", None) or set())
    past_keys |= set(kwargs.get("exclusion_keys") or set())
    mode = pinned_stud_tax_mode() or stud_tax_mode_for_user(kwargs.get("user_id"))
    with stud_tax_override(mode):
        cards, _report = generate_league_suggestions(
            players              = trade_service._players,
            league               = league,
            user_id              = kwargs["user_id"],
            user_elo             = kwargs["user_elo"],
            user_roster          = kwargs["user_roster"],
            seed_elo             = kwargs["seed_elo"],
            confidence           = kwargs.get("confidence"),
            # Operator decision 2026-08-16 — no engine truncation, same as
            # the flag-on serving path.
            max_per_opponent     = None,
            scoring_format       = kwargs.get("scoring_format", "1qb_ppr"),
            untouchable_ids      = kwargs.get("untouchable_ids"),
            target_ids           = kwargs.get("target_ids"),
            not_interested_ids   = kwargs.get("not_interested_ids"),
            opponent_user_id     = kwargs.get("opponent_user_id"),
            opponent_outlooks    = kwargs.get("opponent_outlooks"),
            opponent_pick_shares = kwargs.get("opponent_pick_shares"),
            past_decision_keys   = past_keys,
            on_opponent_done     = kwargs.get("on_opponent_done"),
        )
    return list(cards or [])


def restore_order(fixed: list, after: list) -> list:
    """§3.4 Channel 2 — put a bake-off deck back in the interleaver's order
    after a layer that RE-SORTS it.

    `server._inject_likes_you_cards` returns the deck re-sorted by
    composite_score; on a bake-off deck that would silently destroy the
    team-draft position balance. Cards the injector ADDED keep the top of the
    deck (that is what likes-you means, and it shifts every arm by the same
    constant, so the position control survives); every card already in
    `fixed` returns to its interleaved index. Cards the layer dropped stay
    dropped."""
    pos = {id(c): i for i, c in enumerate(fixed)}
    added = [c for c in after if id(c) not in pos]
    kept = sorted((c for c in after if id(c) in pos), key=lambda c: pos[id(c)])
    return added + kept


def run_bakeoff(
    *,
    generate: Callable[..., list],
    gen_v2: Callable[..., list],
    league_id: str,
    fairness_threshold: float | None = None,
    iso_week: str | None = None,
    interleave: bool | None = None,
    limit: int | None = None,
) -> BakeoffRun:
    """Run all three arms SEQUENTIALLY on this thread and interleave them.

    Sequential is deliberate (PLAN.md §3.1): the config seam is a
    `threading.local()`, so sibling threads would each need their own context
    and the discipline is easy to break; the enumeration is CPU-bound anyway.

    `generate(**overrides)` runs the normal engine — the caller binds the job's
    kwargs and merges any overrides. It is called TWICE: once inside arm A's
    context, once plain. `gen_v2(**overrides)` calls trade_gen_v2 directly.

    An arm that raises is recorded with `error` and an empty list; it then
    forfeits every slot. An arm producing nothing is DATA (§3.2), never an
    exception — arm C under-producing is an expected, measured outcome.
    """
    order = arm_order_for(league_id, iso_week)
    if interleave is None:
        interleave = serve_interleaved()
    if limit is None:
        limit = deck_limit()

    arms: dict[str, ArmResult] = {}
    t_all = time.monotonic()
    for arm in GENERATION_ORDER:
        # Only arm B streams progress: the user's progress bar tracks one
        # sweep, and publishing arm-A/C snapshots would surface
        # un-interleaved, un-attributed cards mid-job.
        quiet = {} if arm == ARM_CURRENT else {"on_opponent_done": None}
        t0 = time.monotonic()
        err = None
        cfg_seen: dict = {}
        try:
            if arm == ARM_BASELINE:
                # `model_a()` applies the pinned config profile AND the R4
                # bypass together — Phase 2 makes it the only supported entry
                # point, because applying one without the other produces a
                # silently wrong arm A.
                with model_a():
                    # Snapshot INSIDE the context — outside it the overlay is
                    # gone and arm A would be recorded as if it ran on live
                    # defaults, which is the exact confusion this exists to
                    # prevent.
                    cfg_seen = snapshot_config()
                    cards = list(generate(**quiet) or [])
            elif arm == ARM_CURRENT:
                cfg_seen = snapshot_config()
                cards = list(generate(**quiet) or [])
            else:
                cfg_seen = snapshot_config()
                cards = list(gen_v2(**quiet) or [])
        except Exception as e:                        # never fail the job
            log.warning("bake-off arm %s failed (recorded, not fatal): %s", arm, e)
            cards, err = [], repr(e)
        arms[arm] = ArmResult(
            arm=arm, cards=cards,
            gen_ms=int((time.monotonic() - t0) * 1000),
            error=err,
            # gen_v2 takes no fairness_threshold — recording None is the
            # honest answer and is itself the fact a reader needs.
            fairness_threshold=(None if arm == ARM_GEN_V2
                                else fairness_threshold),
            config=cfg_seen or snapshot_config(),
        )

    draft = team_draft({a: arms[a].cards for a in ARMS}, order, limit=limit)
    run = BakeoffRun(
        run_id=uuid.uuid4().hex,
        arm_order=order,
        arms=arms,
        draft=draft,
        served_arm=None if interleave else DARK_SERVED_ARM,
        total_ms=int((time.monotonic() - t_all) * 1000),
    )
    log.info(
        "bake-off run %s league=%s order=%s serve=%s arms=%s total_ms=%d",
        run.run_id, league_id, "/".join(order),
        run.served_arm or "interleaved",
        {a: (len(r.cards), r.gen_ms) for a, r in arms.items()}, run.total_ms,
    )
    return run
