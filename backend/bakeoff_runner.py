"""
bakeoff_runner.py — three-model bake-off runner (Phase 3).

Spec: docs/plans/three-model-bakeoff/PLAN.md §3, §3.4, §4, §5.
Scope block: docs/plans/three-model-bakeoff/scope-phase3.md.

One trade job fans out into a generation per ROSTERED arm, the resulting
ranked lists are composed into GROUPS, the groups are merged by team-draft
interleaving, and every served card carries the arm and the group that
produced it.

    A `baseline` — the live engine inside `bakeoff_profiles.model_a()` (the
                   pinned MODEL_A_PROFILE + the arm-A R4 bypass, both
                   golden-tested by Phase 2). **Not in the default roster**
                   (operator decision 2026-08-18) — see `arm_roster()`.
    B `current`  — the live engine at live defaults. No override.
    C `gen_v2`   — backend/trade_gen_v2.py, called directly.

Deck composition (operator decision 2026-08-18; scope block
docs/plans/three-model-bakeoff/scope-composition.md)
-----------------------------------------------------------------------
A 30-card deck built from three groups of ten, each group split five value /
five outlook:

    group 1   arm `current`, basis `divergence`   5 value / 5 outlook
    group 2   arm `current`, basis `consensus`    5 value / 5 outlook
    group 3   arm `gen_v2`   (divergence by nature)  5 value / 5 outlook

"consensus vs divergence" is the existing `TradeCard.basis`; "value vs
outlook" is the existing `TradeCard.lane`, whose engine label for the outlook
lane is `window`. No new taxonomy.

The three GROUPS — not the two arms — are the interleaving participants. A
round robin over arms would hand arm `current` twenty consecutive slots and
push arm `gen_v2` to the deck's tail, reintroducing exactly the position
confound team-draft exists to remove (acceptance falls ~27% across a session
from position alone).

Under-fill is DATA, never a silent backfill. `window` is only ~25% of live
supply, so no group can find five outlook cards reliably, and arm gen_v2 has
never served so its lane mix was unmeasured. Whether an arm can produce
outlook-basis divergence ideas at all is one of the more interesting things
this test can reveal, and a quiet backfill from the value lane would hide it
completely. Every (group, lane) shortfall is recorded on
`bakeoff_runs.groups_json`; `bakeoff_fill_policy` chooses whether the residual
slots are backfilled with a flagged CROSS-LANE substitute (1) or not (0,
default).

D-086 (2026-08-19) separates a second question from that one: a slot the
outlook lane cannot fill is not automatically a slot the GROUP cannot fill.
`bakeoff_lane_reallocate` (default ON) lets each lane spill into slots the
other lane provably could not use, drawing only from its OWN bucket — so
every served card still sits in a slot matching its own label and `lane_slot`
keeps meaning what it says. `short` is computed against the nominal 5/5 ask
BEFORE reallocation and is untouched, `realloc` records the spill explicitly,
so the under-fill finding survives intact while the deck stops paying for it.
Measured on 18 live runs: 13.8 cards/deck before, 16.0 after.

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
import threading
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

#: Every arm that EXISTS. Not every arm that runs — see `arm_roster()`, which
#: is what the fan-out and the draft actually iterate. Order here is the
#: canonical listing order, not the generation order (see GENERATION_ORDER)
#: and not the served order (the rotation is shuffled per deck).
ARMS: tuple[str, ...] = (ARM_BASELINE, ARM_CURRENT, ARM_GEN_V2)

#: Arms that run the v1/v3 engine and therefore produce BOTH bases —
#: `divergence` for opponents with real rankings, `consensus` for the
#: never-ranked fallback path. Each contributes two groups. Arm `gen_v2` is
#: divergence-only by construction (backend/trade_gen_v2.py stamps
#: basis="divergence" on everything it emits), so it contributes one.
ENGINE_ARMS: tuple[str, ...] = (ARM_BASELINE, ARM_CURRENT)

# ---------------------------------------------------------------------------
# Lanes — the "value vs outlook" axis, on the field that already carries it
# ---------------------------------------------------------------------------

#: `TradeCard.lane` values. The engine calls the outlook lane `window`
#: (trade_service.classify_lane); the operator calls it "outlook". Same axis,
#: one label — no parallel taxonomy is introduced.
LANE_VALUE   = "value"
LANE_OUTLOOK = "window"

#: The third bucket: `lane` is absent. It is NOT a synonym for "value".
#: `classify_lane` returns None precisely when the user has no window
#: DIRECTION (outlook None or `not_sure`) or the flag `trade.lanes` is off —
#: i.e. when the outlook axis is undefined for that deck, not when the card is
#: value-shaped. 132 of 3,163 recent live cards (all consensus-basis) land
#: here. Binning them as value would inflate the value lane with cards nobody
#: classified and make the value/outlook comparison depend on how many users
#: happened to declare a window; dropping them would empty the deck for a
#: `not_sure` user. So they get their own bucket, fill NEITHER lane quota,
#: and are eligible only as flagged residual fill.
LANE_NONE = "(none)"

#: Quota slots a served card can occupy, stamped on
#: `deck_impressions.lane_slot`. `fill` = a residual slot the card's own lane
#: did not earn (only reachable under bakeoff_fill_policy = 1).
SLOT_VALUE   = "value"
SLOT_OUTLOOK = "outlook"
SLOT_FILL    = "fill"

#: #172 trade-intent modes. Anything else the client sends is not an intent.
INTENT_MODES: frozenset[str] = frozenset(
    {"consolidate", "tier_up", "tier_down"})

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

    `bakeoff_serve_interleaved` is back to 0.0 = DARK (operator, 2026-08-19).

    Interleaved serving was lit on 2026-08-18 and MEASURABLY SHRANK THE DECK.
    Arm C forfeits everything it generates — the 05:33 run recorded
    `gen_v2: cards=0, forfeits=9` against `current: cards=40` — and the
    outlook lane fills 0 of its 5 slots per group. Because the fill policy is
    leave-short by design (D-078), arm C's 10 slots and the empty outlook
    lanes simply vanish: the operator received a 10-card deck from a 40-card
    arm-B pool. Arm C has never served a single card, so going dark gives up
    nothing that was reaching users.

    Dark = all arms still generate and log (the forfeit data is what diagnoses
    arm C), only arm B is served, and the normal presentation stack runs
    untouched. Re-light with 1.0 once arm C stops forfeiting AND the outlook
    lane fills — both are visible in `bakeoff_runs.groups_json`."""
    return bakeoff_enabled() and _cfg("bakeoff_serve_interleaved", 0.0) >= 1.0


def deck_limit() -> int | None:
    """`bakeoff_deck_limit` — max cards in the served bake-off deck. Default
    30: three groups of ten. 0 = uncapped, which together with
    `bakeoff_group_size` = 0 restores Phase 3's drain-every-arm draft."""
    n = int(_cfg("bakeoff_deck_limit", 30.0))
    return n if n > 0 else None


def arm_roster() -> tuple[str, ...]:
    """The arms that actually RUN — generated, drafted, served.

    Operator decision 2026-08-18: arm `baseline` leaves the served rotation.
    It leaves by CONFIGURATION, not by deletion — `MODEL_A_PROFILE`,
    `model_a()`, the arm-A golden and the knob-inventory guard all stay in the
    tree and keep passing, because they cost nothing while dark and the
    baseline may be wanted later. `bakeoff_include_baseline` = 1 puts arm A
    back (and with it its two groups) with no deploy.

    Skipping arm A is also the cheapest half of the fan-out budget: it was
    measured as the SLOWEST arm (4.19 s of the 7.36 s three-arm fixture run —
    its profile zeroes every gate, so more candidates survive), so a two-arm
    roster roughly halves the job cost Phase 4 was told to watch.
    """
    if _cfg("bakeoff_include_baseline", 0.0) >= 1.0:
        return (ARM_BASELINE, ARM_CURRENT, ARM_GEN_V2)
    return (ARM_CURRENT, ARM_GEN_V2)


def group_size() -> int:
    """`bakeoff_group_size` — cards per group. 0 kills the whole composition
    layer: no groups, no lane quotas, and the draft reverts to Phase 3's plain
    per-ARM team draft."""
    return max(0, int(_cfg("bakeoff_group_size", 10.0)))


def group_value_slots() -> int:
    """`bakeoff_group_value_slots` — value-lane slots per group. The outlook
    slots are the remainder (`group_size() - this`), so the split can never be
    inconsistent with the group size."""
    return max(0, int(_cfg("bakeoff_group_value_slots", 5.0)))


def backfill_residual_slots() -> bool:
    """`bakeoff_fill_policy` — what happens to a lane slot its own lane could
    not fill.

    **Default 0 = leave short.** The divergence groups are expected to
    under-fill their outlook quota routinely (`window` is ~19% of live
    divergence supply) and arm gen_v2's lane mix has never been observed at
    all. "Can this arm produce outlook-basis divergence ideas?" is one of the
    questions the bake-off exists to answer, and a silent value-lane backfill
    would erase the evidence while leaving the deck looking full. So the
    default keeps the hole and records it.

    1 = backfill from the same GROUP's other lane (then its unlabelled
    remainder), every substitute stamped `lane_slot = 'fill'` so no analysis
    can mistake it for a card that earned an outlook slot.

    Orthogonal to `bakeoff_lane_reallocate` (D-086): that runs FIRST and moves
    slots between lanes without moving cards between lanes, so by the time
    this policy sees a residual, both lane buckets are exhausted and a fill
    can only come from the unlabelled `(none)` remainder.
    """
    return _cfg("bakeoff_fill_policy", 0.0) >= 1.0


def lane_reallocate() -> bool:
    """`bakeoff_lane_reallocate` — **default 1 = ON** (D-086, 2026-08-19).

    A lane quota the group's own lane cannot supply leaves SLOTS empty, not
    just that lane's slots. Before D-086 a group holding 7 value cards and 0
    window cards served 5 and dropped 5, and a group holding 10 value / 0
    window served 5 and dropped 5 — measured across 18 live runs that cost
    40 of 288 fillable slots (13.8 cards/deck served against a 16.0 ceiling
    the group partition already allowed).

    ON: after the nominal quota is taken, each lane may extend into slots the
    OTHER lane provably could not fill, drawing only from its OWN bucket. The
    cards keep their true `lane_slot` (`value` / `outlook`) because no card
    ever occupies the other lane's slot — that is what distinguishes this
    from `bakeoff_fill_policy` = 1, where a value card takes an OUTLOOK slot
    and is flagged `fill` precisely so analysis discounts it.

    What D-078 protected is protected still: `short` is computed against the
    nominal ask BEFORE any reallocation, `pool` records the raw lane supply,
    and `groups_json[key].realloc` names the spill card-for-card. "Can this
    arm produce outlook-basis ideas?" is answered by `short` and `pool`, and
    both are untouched. What changes is only that the deck no longer shrinks
    to make the point a column already makes.

    0 restores the pre-D-086 composition byte-for-byte, deploy-free.
    """
    return _cfg("bakeoff_lane_reallocate", 1.0) >= 1.0


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


def effective_trade_intent(requested: str | None) -> str | None:
    """The #172 intent lens the deck was ACTUALLY generated under.

    Same rule Phase 3 established for `fairness_threshold` and the same reason
    for it: *record the gate a row passed, never the gate that was requested*.
    The requested value and the effective value genuinely diverge here, in
    three ways, none hypothetical:

      * `trade_service._generate_trades_impl` resolves
        `_intent = trade_intent if FLAGS.trades_intent_modes else None`
        — with `trades.intent_modes` off, a client that sent
        `consolidate` was served an unfiltered deck;
      * the route (`server.py`) already narrows anything outside
        `INTENT_MODES` to None, so a stale or misspelled client value is not
        an intent;
      * `_filter_by_trade_intent` is a POST-GENERATION filter, so the
        recorded value describes the served set, not a generator setting.

    The operator kept the user-facing trade settings visible for the bake-off
    (testers are briefed verbally instead), so a tester CAN change the intent
    chip mid-test. Without this the resulting shift in each group's basis/lane
    mix would be invisible in the data — the exact class of silently-invalid
    result the fairness-threshold capture was added to prevent.
    """
    if not requested or requested not in INTENT_MODES:
        return None
    return requested if is_enabled("trades.intent_modes") else None


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
# Groups — (arm, basis) composition units
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Group:
    """One composition unit: an arm's cards narrowed to one `basis`.

    The group — not the arm — is the interleaving participant and the quota
    holder, so `key` is what `deck_impressions.group_key` records.
    """
    key: str
    arm: str
    #: None = accept every basis. Used for arm `gen_v2`, which emits nothing
    #: but `divergence`, so narrowing it would be a no-op that invited the
    #: reader to think a consensus gen_v2 group exists.
    basis: str | None = None


def basis_of(card) -> str:
    """`TradeCard.basis`, defaulted the way the engine defaults it."""
    return getattr(card, "basis", None) or "divergence"


def lane_of(card) -> str:
    """`TradeCard.lane` bucketed into exactly three values. Anything that is
    not the engine's `value` or `window` label — including None — is
    `LANE_NONE`, never silently folded into a lane that has a quota."""
    lane = getattr(card, "lane", None)
    return lane if lane in (LANE_VALUE, LANE_OUTLOOK) else LANE_NONE


def groups_for(roster: tuple[str, ...] | list[str] | None = None) -> list[Group]:
    """Derive the group list from the arm roster.

    Derived rather than hard-coded so the roster knob genuinely controls the
    deck: a two-arm roster yields the operator's three groups, and flipping
    `bakeoff_include_baseline` back on yields five (arm A gains the same
    divergence/consensus pair arm B has) without a second knob to keep in
    sync. `bakeoff_deck_limit` still caps the total.
    """
    out: list[Group] = []
    for arm in (roster if roster is not None else arm_roster()):
        if arm in ENGINE_ARMS:
            out.append(Group(f"{arm}_divergence", arm, "divergence"))
            out.append(Group(f"{arm}_consensus",  arm, "consensus"))
        else:
            out.append(Group(arm, arm, None))
    return out


@dataclass
class GroupResult:
    """One group's composed list plus the whole of its quota accounting.

    `short` is the first-class output here, not an error path: it is the
    per-(group, lane) under-fill the operator asked to be recorded rather than
    papered over.
    """
    group: Group
    cards: list = field(default_factory=list)
    #: id(card) -> SLOT_VALUE | SLOT_OUTLOOK | SLOT_FILL
    slots: dict = field(default_factory=dict)
    #: id(card) -> rank within THIS group's composed list
    ranks: dict = field(default_factory=dict)
    #: {"size": n, "value": n, "outlook": n} — what was asked for
    quota: dict = field(default_factory=dict)
    #: {"value": n, "outlook": n, "fill": n} — what was found. Under
    #: `bakeoff_lane_reallocate` (D-086) a lane's count can EXCEED its quota:
    #: it absorbed slots the other lane could not fill, from its own bucket.
    #: The excess is `realloc`, so the two are never guesswork.
    filled: dict = field(default_factory=dict)
    #: {"value": n, "outlook": n} — the UNDER-FILL, per lane, against the
    #: NOMINAL quota and computed BEFORE reallocation. The point. D-086 does
    #: not touch this number: a group that found no outlook card still reads
    #: `{"outlook": 5}` here whether or not the value lane used those slots.
    short: dict = field(default_factory=dict)
    #: {"value": n, "outlook": n} — slots each lane absorbed from the other
    #: lane's unfillable quota (D-086), drawn from its OWN bucket. All-zero
    #: when both lanes met their quota or `bakeoff_lane_reallocate` is 0.
    realloc: dict = field(default_factory=dict)
    #: {"value": n, "window": n, "(none)": n} — supply the group could draw on
    pool: dict = field(default_factory=dict)
    #: False when NO card in the pool carried a lane label, i.e. the outlook
    #: axis is undefined for this deck (user has no window direction, or
    #: `trade.lanes` is off). The split is then inert — see compose_group.
    lane_split_active: bool = True

    def summary(self) -> dict:
        return {
            "arm":               self.group.arm,
            "basis":             self.group.basis,
            "quota":             dict(self.quota),
            "filled":            dict(self.filled),
            "short":             dict(self.short),
            "realloc":           dict(self.realloc),
            "pool":              dict(self.pool),
            "composed":          len(self.cards),
            "lane_split_active": self.lane_split_active,
        }


def compose_group(group: Group, arm_cards: list, *, size: int,
                  value_slots: int, backfill: bool,
                  reallocate: bool = True,
                  outlook_leads: bool = False) -> GroupResult:
    """Narrow one arm's ranked list to a group and fill that group's quota.

    Steps, exactly:

      1. Filter to the group's `basis`, preserving the ARM's own rank order —
         the generator's opinion is never re-sorted here.
      2. Bucket by lane into value / outlook(`window`) / `(none)`.
      3. Take the top `value_slots` of the value bucket and the top
         `size - value_slots` of the outlook bucket. Whatever a lane could not
         supply is recorded in `short` — always, and always against this
         nominal ask, whatever steps 4 and 5 then do with the empty slots.
      4. `reallocate` (bakeoff_lane_reallocate = 1, the default; D-086): a
         lane that met its quota extends into the slots the other lane could
         not fill, drawing only from its OWN bucket, and the extension is
         recorded in `realloc`. No card changes lane, so every card still
         takes a slot its own label earned — the difference from step 5,
         where it does not.
      5. `backfill` (bakeoff_fill_policy = 1) only: refill whatever residual
         survives step 4 from the group's leftovers in arm-rank order, each
         stamped `SLOT_FILL`. With reallocation on, both lane buckets are
         already drained, so a fill can only be an `(none)`-bucket card. The
         group's own arm and basis still hold, so a fill is a lane
         substitution and nothing more.
      6. Order the quota'd cards by ALTERNATING lanes (`outlook_leads` picks
         which lane takes slot 0, seeded per deck+group by the caller) so
         neither lane systematically occupies the better half of the group's
         positions. Each lane keeps its internal arm-rank order. Fills append
         after, which is honest — they are the residue — and they are flagged.

    An empty group is data, exactly like an empty arm: it forfeits its draft
    slots and the shortfall is on the record.
    """
    res = GroupResult(group=group)
    pool = [c for c in arm_cards
            if group.basis is None or basis_of(c) == group.basis]

    buckets: dict[str, list] = {LANE_VALUE: [], LANE_OUTLOOK: [], LANE_NONE: []}
    for c in pool:
        buckets[lane_of(c)].append(c)
    res.pool = {k: len(v) for k, v in buckets.items()}

    outlook_slots = max(0, size - value_slots)
    res.quota = {"size": size, "value": value_slots, "outlook": outlook_slots}

    # The lane axis is undefined for this deck when nothing in the pool
    # carries a label. Quota'ing on an axis that does not exist would serve
    # an EMPTY group under the leave-short default — a real user harm for
    # every `not_sure`-outlook user, and a measurement artefact rather than a
    # model property. Fall back to top-N by arm rank and say so.
    res.lane_split_active = bool(buckets[LANE_VALUE] or buckets[LANE_OUTLOOK])
    if not res.lane_split_active:
        res.cards = list(pool[:size])
        res.slots = {id(c): SLOT_FILL for c in res.cards}
        res.filled = {"value": 0, "outlook": 0, "fill": len(res.cards)}
        res.short = {"value": value_slots, "outlook": outlook_slots}
        res.realloc = {"value": 0, "outlook": 0}
        res.ranks = {id(c): i for i, c in enumerate(res.cards)}
        return res

    take_v = buckets[LANE_VALUE][:value_slots]
    take_o = buckets[LANE_OUTLOOK][:outlook_slots]
    #: Against the NOMINAL ask, before reallocation — D-086 must not be able
    #: to soften this number, because it is the whole reason the column exists.
    res.short = {"value":   value_slots - len(take_v),
                 "outlook": outlook_slots - len(take_o)}

    # D-086 — lane REALLOCATION. Slots exist only because one lane's bucket
    # ran dry, so at most one lane can have a tail to spill into them and the
    # order of the two extensions below cannot change the outcome.
    res.realloc = {"value": 0, "outlook": 0}
    if reallocate:
        spare = max(0, size - len(take_v) - len(take_o))
        if spare > 0:
            extra_v = buckets[LANE_VALUE][value_slots:value_slots + spare]
            extra_o = buckets[LANE_OUTLOOK][
                outlook_slots:outlook_slots + spare - len(extra_v)]
            take_v = take_v + extra_v
            take_o = take_o + extra_o
            res.realloc = {"value": len(extra_v), "outlook": len(extra_o)}

    fills: list = []
    if backfill:
        residual = max(0, size - len(take_v) - len(take_o))
        if residual > 0:
            taken = {id(c) for c in take_v} | {id(c) for c in take_o}
            fills = [c for c in pool if id(c) not in taken][:residual]

    # Alternate the two lanes so neither owns the group's front half.
    first, second = ((take_o, take_v) if outlook_leads else (take_v, take_o))
    ordered: list = []
    for i in range(max(len(first), len(second))):
        if i < len(first):
            ordered.append(first[i])
        if i < len(second):
            ordered.append(second[i])
    ordered.extend(fills)

    slot_of = {id(c): SLOT_VALUE for c in take_v}
    slot_of.update({id(c): SLOT_OUTLOOK for c in take_o})
    slot_of.update({id(c): SLOT_FILL for c in fills})

    res.cards = ordered
    res.slots = slot_of
    res.ranks = {id(c): i for i, c in enumerate(ordered)}
    res.filled = {"value": len(take_v), "outlook": len(take_o),
                  "fill": len(fills)}
    return res


# ---------------------------------------------------------------------------
# Draft order — seeded per deck
# ---------------------------------------------------------------------------

def iso_week_of(now: datetime | None = None) -> str:
    """ISO year-week, e.g. '2026-W34'."""
    d = now or datetime.now(timezone.utc)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _seed_for(*parts: str) -> int:
    """sha256 over the joined parts. hashlib, not hash(): Python salts str
    hashes per process, so hash() would reshuffle every deploy."""
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:16], 16)


def draft_order_for(participants, league_id: str,
                    iso_week: str | None = None) -> list[str]:
    """Randomised draft rotation over whatever the participants are — arms in
    Phase 3's uncomposed fallback, GROUPS once composition is on (PLAN.md §4
    step 2, unchanged seed).

    Seeded on league_id + ISO week: stable for a league across a week, so a
    re-run of the same job reproduces the same deck, and rotated between
    weeks, so nothing is permanently stuck in the last slot.
    """
    order = list(participants)
    random.Random(_seed_for(league_id, iso_week or iso_week_of())).shuffle(order)
    return order


def outlook_leads_for(group_key: str, league_id: str,
                      iso_week: str | None = None) -> bool:
    """Which lane takes slot 0 inside a group, seeded per deck AND per group.

    Without this the leading lane would be a constant, and the value lane
    would occupy every group's slot 0 in every deck — a within-group position
    bias on the exact axis the quota exists to compare.
    """
    return random.Random(
        _seed_for(league_id, iso_week or iso_week_of(), group_key)
    ).random() < 0.5


def arm_order_for(league_id: str, iso_week: str | None = None) -> list[str]:
    """Phase-3 compatibility shim: the draft rotation over ALL arms."""
    return draft_order_for(ARMS, league_id, iso_week)


# ---------------------------------------------------------------------------
# Team-draft interleaving (PLAN.md §4)
# ---------------------------------------------------------------------------

@dataclass
class DraftResult:
    deck: list = field(default_factory=list)
    #: id(card) → (arm, arm_rank) — arm_rank is the card's 0-based rank in
    #: its OWN arm's FULL ranked list, never its deck position and never its
    #: position inside a group. It is what separates "this model ranks badly"
    #: from "this card sat low in the deck".
    attribution: dict = field(default_factory=dict)
    #: id(card) → (group_key, group_rank, lane_slot) — which group's quota the
    #: card filled, its rank inside that group's composed list, and which
    #: quota slot it took. Empty in the uncomposed (Phase 3) path.
    group_attribution: dict = field(default_factory=dict)
    #: id(card) → [other arms whose full list also contains this trade]
    also_proposed_by: dict = field(default_factory=dict)
    #: participant → number of rotation slots it could not fill. Participants
    #: are ARMS in the uncomposed path and GROUPS once composition is on.
    forfeits: dict = field(default_factory=dict)


def _draft_core(lists: dict[str, list], order: list[str],
                limit: int | None) -> tuple[list, dict, dict]:
    """The team-draft loop itself, over whatever the participants are.

    Returns (deck, credit, forfeits) where credit maps id(card) → (participant,
    rank-within-that-participant's-list).

      1. Each participant keeps a cursor into its own ranked list, from 0.
      2. Rotate through `order`. On its turn a participant advances its cursor
         past any card whose `card_key` is already in the deck (something else
         proposed the same trade and picked it first), then contributes the
         card at its cursor and advances by one.
      3. Credit is FIRST-PICKER: agreement never double-counts a card.
      4. A participant whose cursor has run past the end of its list forfeits
         its slot to the next in rotation, and the forfeit is COUNTED.
      5. Stop at `limit`, or when a full rotation contributes nothing.
    """
    order = [p for p in order if p in lists]
    cursors = {p: 0 for p in order}
    forfeits = {p: 0 for p in order}
    taken: set = set()
    deck: list = []
    credit: dict = {}

    total = sum(len(lists[p]) for p in order)
    cap = total if limit is None else min(limit, total)

    while len(deck) < cap:
        progressed = False
        for p in order:
            if len(deck) >= cap:
                break
            lst = lists[p]
            i = cursors[p]
            while i < len(lst) and card_key(lst[i]) in taken:
                i += 1
            cursors[p] = i
            if i >= len(lst):
                forfeits[p] += 1
                continue
            card = lst[i]
            deck.append(card)
            credit[id(card)] = (p, i)
            taken.add(card_key(card))
            cursors[p] = i + 1
            progressed = True
        if not progressed:
            break
    return deck, credit, forfeits


def _agreement(deck: list, credited_arm: dict,
               arm_lists: dict[str, list]) -> dict:
    """Which OTHER arms also proposed each served trade.

    A full membership scan over every arm's COMPLETE list, so agreement is
    recorded even for an arm whose cursor never reached the duplicate — and it
    is per ARM, not per group, because "did arm B and arm C independently find
    this trade" is the question worth asking (groups 1 and 2 are the same arm
    on disjoint bases and can never collide with each other).
    """
    members: dict[tuple, set] = defaultdict(set)
    for arm, lst in arm_lists.items():
        for c in lst:
            members[card_key(c)].add(arm)
    out: dict = {}
    for card in deck:
        others = sorted(members[card_key(card)] - {credited_arm[id(card)]})
        if others:
            out[id(card)] = others
    return out


def team_draft(arm_lists: dict[str, list], arm_order: list[str],
               limit: int | None = None) -> DraftResult:
    """Team-draft interleave of per-ARM ranked lists — Phase 3's draft, kept
    as the behaviour `bakeoff_group_size = 0` falls back to."""
    deck, credit, forfeits = _draft_core(arm_lists, arm_order, limit)
    res = DraftResult(deck=deck, attribution=credit, forfeits=forfeits)
    res.also_proposed_by = _agreement(
        deck, {k: v[0] for k, v in credit.items()}, arm_lists)
    return res


def group_draft(group_results: dict[str, GroupResult], group_order: list[str],
                arm_lists: dict[str, list],
                limit: int | None = None) -> DraftResult:
    """Team-draft interleave of per-GROUP composed lists.

    The GROUPS are the participants. Drafting by arm instead would give arm
    `current` two consecutive picks per rotation — twenty of the deck's thirty
    cards, all ahead of arm `gen_v2`'s tail — which is precisely the
    deck-position confound team-draft exists to remove.

    `arm_rank` still comes from the arm's FULL ranked list (via `arm_lists`),
    not from the group's composed list: the two answer different questions and
    both are recorded.
    """
    lists = {key: gr.cards for key, gr in group_results.items()}
    deck, credit, forfeits = _draft_core(lists, group_order, limit)

    arm_index = {arm: {id(c): i for i, c in enumerate(lst)}
                 for arm, lst in arm_lists.items()}
    attribution: dict = {}
    group_attribution: dict = {}
    for card in deck:
        gkey, _pos_in_group = credit[id(card)]
        gr = group_results[gkey]
        attribution[id(card)] = (
            gr.group.arm,
            arm_index.get(gr.group.arm, {}).get(id(card), gr.ranks[id(card)]))
        group_attribution[id(card)] = (
            gkey, gr.ranks[id(card)], gr.slots.get(id(card)))

    res = DraftResult(deck=deck, attribution=attribution,
                      group_attribution=group_attribution, forfeits=forfeits)
    res.also_proposed_by = _agreement(
        deck, {k: v[0] for k, v in attribution.items()}, arm_lists)
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
    #: The #172 intent lens this arm's cards were actually filtered under —
    #: the EFFECTIVE value (see effective_trade_intent), not the request.
    #: Per arm for the same reason as the threshold: recorded, never assumed
    #: to match across arms.
    trade_intent: str | None = None
    #: The effective trade_service config INSIDE this arm's context.
    config: dict = field(default_factory=dict)
    #: Per-stage attrition for the arms that expose it. Arm `gen_v2` fills
    #: this from `GenerationReport.kill_counts()` plus the two
    #: post-generation filters `gen_v2_cards` applies itself; the engine
    #: arms leave it empty (their kill accounting lives on TradeService's
    #: own `presentment_kill_counts`). `{}` is "this arm reports no
    #: stages", never "this arm killed nothing".
    diagnostics: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.cards


@dataclass
class BakeoffRun:
    run_id: str
    #: The DRAFT rotation actually used — group keys once composition is on,
    #: arm names in the `bakeoff_group_size = 0` fallback. Kept under this
    #: name because it is what `bakeoff_runs.arm_order` has always stored.
    arm_order: list[str]
    arms: dict[str, ArmResult]
    draft: DraftResult
    served_arm: str | None      # None ⇒ interleaved serving
    total_ms: int
    #: group_key → GroupResult. Empty when composition is killed.
    groups: dict = field(default_factory=dict)

    @property
    def deck(self) -> list:
        """The interleaved deck. In dark mode this is still computed and
        logged — it is just not what gets served."""
        return self.draft.deck

    def served_deck(self) -> list:
        """What the job should actually serve."""
        if self.served_arm is None:
            return list(self.draft.deck)
        served = self.arms.get(self.served_arm)
        return list(served.cards) if served is not None else list(self.draft.deck)

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

    def group_for(self, card) -> tuple[str, int, str | None] | None:
        """(group_key, group_rank, lane_slot) for a served card, or None when
        no group produced the deck this card was served in.

        None in DARK mode even for a card the composition also picked: dark
        validation serves arm B's own list in arm B's own order, so that card
        did not fill anyone's quota and its `group_rank` would describe a deck
        nobody saw. The composition is still computed and its accounting still
        written to `bakeoff_runs.groups_json` — measuring the per-(group, lane)
        under-fill before Phase 5 lights interleaved serving is precisely what
        dark validation is for.

        Also None for a likes-you injection (no arm, no group produced it) and
        for a run with `bakeoff_group_size = 0`."""
        if self.served_arm is not None:
            return None
        return self.draft.group_attribution.get(id(card))

    def trade_intent_for(self, card) -> str | None:
        """The effective #172 intent the card's OWN arm was filtered under."""
        hit = self.attribution_for(card)
        if hit is None:
            return None
        arm = self.arms.get(hit[0])
        return arm.trade_intent if arm is not None else None

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

    def forfeits_for_arm(self, arm: str) -> int:
        """Rotation slots this ARM could not fill, summed over its groups.

        The draft's participants are GROUPS once composition is on, and a
        group key is only equal to its arm name for single-group arms —
        arm `current` contributes `current_divergence` + `current_consensus`,
        so the old `forfeits[arm]` lookup missed on every engine arm and
        recorded a flat 0 for all of them. That made arm C's non-zero count
        look like a property of arm C rather than of the key spelling. Falls
        back to the direct lookup for the `bakeoff_group_size = 0` path,
        where the participants really are arms.
        """
        if self.groups:
            return sum(n for key, n in self.draft.forfeits.items()
                       if (self.groups[key].group.arm if key in self.groups
                           else key) == arm)
        return self.draft.forfeits.get(arm, 0)

    def config_record(self) -> dict:
        """`{"base": <arm current's effective config>, "arm_delta": {arm: {...}}}`.

        Stored whole rather than fingerprinted because `model_config` has no
        `updated_at`: a hash would tell a later reader that the configuration
        changed without telling them what it changed to, which is the same
        archaeology problem one step removed. ~5 KB base + a handful of delta
        keys per run — arm A's delta is essentially MODEL_A_PROFILE, arm C's is
        empty. Deliberately NOT a config-versioning system: one snapshot per
        run, no history, no dedup."""
        cur = self.arms.get(ARM_CURRENT)
        base = dict((cur.config if cur is not None else None) or {})
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
                "forfeits": self.forfeits_for_arm(arm),
                "served":   len([c for c in self.draft.deck
                                 if self.draft.attribution.get(id(c), (None,))[0] == arm]),
                "error":    r.error,
                # The threshold this arm was INVOKED with (null for gen_v2,
                # which takes none). Per arm, not per job: arm A runs under
                # MODEL_A_PROFILE, so agreement is recorded, never assumed.
                "fairness_threshold": r.fairness_threshold,
                # The EFFECTIVE #172 intent lens (null = unfiltered). Same
                # record-the-gate-that-applied rule as the threshold above.
                "trade_intent": r.trade_intent,
                # Per-stage attrition, for the arms that report it (arm C
                # today). `{}` = this arm reports no stages. This is what
                # turns "cards: 0, forfeits: 9" from a counter into a
                # diagnosis — see `bakeoff_runner.last_gen_v2_diagnostics`.
                "diagnostics": r.diagnostics or {},
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
            # Per-group quota accounting: what each group asked for, what it
            # found, and — the point of recording it at all — what it could
            # NOT find, per lane. `{}` when composition is killed.
            "groups_json": json.dumps({
                key: {**gr.summary(),
                      "served": len([
                          c for c in self.draft.deck
                          if (self.draft.group_attribution.get(id(c))
                              or (None,))[0] == key])}
                for key, gr in self.groups.items()}),
            "agreement_json": json.dumps(dict(agree)),
            "config_json": json.dumps(self.config_record()),
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }


#: Arm C's per-stage attrition, handed from `gen_v2_cards` to `run_bakeoff`.
#: A thread-local rather than a return value because `gen_v2` reaches the
#: fan-out as an opaque `Callable[..., list]` bound by the caller — widening
#: that contract would touch every arm. Thread-local (not module-global) for
#: the same reason the config seam is: concurrent jobs share this module.
#: Same shape as the `presentment_kill_counts()` precedent — a flat dict of
#: counters, read once immediately after the call that wrote it.
_gen2_diag = threading.local()


def last_gen_v2_diagnostics() -> dict:
    """Per-stage kill counts from the most recent `gen_v2_cards` call ON
    THIS THREAD, then CLEARED. Draining is deliberate: a stale read would
    attribute one job's attrition to another, and `{}` (arm C did not run,
    or raised before generating) is the honest answer for that."""
    diag = getattr(_gen2_diag, "value", None) or {}
    _gen2_diag.value = {}
    return dict(diag)


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
    packages differently for a reason that has nothing to do with the model),
    and the two POST-generation steps that branch applies to the cards it
    returns:

      * **the #172 intent filter.** `_generate_trades_impl`'s v2 branch runs
        `_filter_by_trade_intent` on gen-v2's output before returning it;
        calling `generate_league_suggestions` directly skipped it, so a tester
        who set an intent chip would have had groups 1 and 2 filtered and
        group 3 not — the head-to-head comparing two different briefs.
      * **the lane label.** `classify_lane` runs late in
        `_generate_trades_impl`, AFTER the v2 branch returns, so no gen-v2
        card has ever carried a `lane`. Left alone, group 3's outlook quota
        would under-fill 100% of the time for a plumbing reason and the result
        would read as "arm C cannot produce outlook ideas" — a false finding
        of exactly the kind this deck composition exists to test for. The
        label is a pure post-hoc classification of give/receive against the
        user's resolved window on CONSENSUS values; it touches no gate and no
        score, and applying the same labeller to every arm is what makes the
        lane comparison a comparison of generators.

    Both are presentation-side treatment, not model behaviour: arms A/B get
    them, so arm C gets them, and the bake-off compares generation.
    """
    from .trade_gen_v2 import generate_league_suggestions
    from .trade_service import (_c, _filter_by_trade_intent, cap_give_headliners,
                                classify_lane, elo_to_value,
                                pinned_stud_tax_mode, signed_lane_shift,
                                stud_tax_mode_for_user, stud_tax_override)
    from .feature_flags import FLAGS

    # Cleared on ENTRY as well as drained on read: a run that returns early
    # below must not leave a previous job's counters visible to the fan-out.
    _gen2_diag.value = {}

    league = trade_service._leagues.get(kwargs["league_id"])
    if league is None:
        _gen2_diag.value = {"S0_no_league": 1}
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
    cards = list(cards or [])

    # Per-stage attrition (see `last_gen_v2_diagnostics`). The generator's
    # own stages come from the report it already builds and previously
    # threw away here; the two POST-generation filters below are counted
    # in the same dict because they kill arm-C cards too — a batch the
    # engine emitted and the intent lens then wiped is indistinguishable
    # from a batch the engine never produced, in `arms_json`'s card count.
    # `getattr` rather than a direct call: the report is whatever
    # `generate_league_suggestions` returned as its second element, and
    # tests substitute a plain dict for it. Diagnostics are telemetry —
    # a stub that cannot report stages degrades to "no stages reported",
    # it never breaks the arm.
    _kc = getattr(_report, "kill_counts", None)
    diag = dict(_kc()) if callable(_kc) else {}

    seed_elo = kwargs.get("seed_elo") or {}
    scoring_format = kwargs.get("scoring_format", "1qb_ppr")
    _n_before = len(cards)
    cards = _filter_by_trade_intent(
        cards, effective_trade_intent(kwargs.get("trade_intent")),
        seed_elo, trade_service._players, scoring_format)
    diag["S7_intent_filter"] = _n_before - len(cards)

    # C4b give-side headliner cap — the third post-generation step arms A/B get
    # and arm C would otherwise miss. `_dedup_and_sort` applies it on the v1/v3
    # path and `_generate_trades_impl`'s v2 branch applies it on the flag-on
    # serving path; calling `generate_league_suggestions` directly skips both,
    # so without this line group 3 would be the only group allowed to flood one
    # give-side headliner and the bake-off would compare arms under different
    # deck-assembly rules. Arm A disables it through MODEL_A_PROFILE, which is
    # a deliberate arm difference, not an accidental one.
    _n_before = len(cards)
    cards = cap_give_headliners(cards, seed_elo, trade_service._players,
                                int(_c("deck_give_headliner_cap")))
    diag["S7_headliner_cap"] = _n_before - len(cards)
    diag["S7_served_to_deck"] = len(cards)
    _gen2_diag.value = diag

    # `_vs` — the consensus (seed) value function `_generate_trades_impl`
    # builds for exactly this call. Lanes describe the trade's shape against
    # the shared board, never either member's private one.
    _vs_cache: dict = {}

    def _vs(pid: str) -> float:
        v = _vs_cache.get(pid)
        if v is None:
            v = elo_to_value(seed_elo.get(pid, 1500.0))
            _vs_cache[pid] = v
        return v

    outlook = kwargs.get("outlook")
    for c in cards:
        # Unconditional, matching the v1/v3 path: `lane_shift` has no flag
        # (its kill switch is fit_k_explained_mult = 1.0) and the swipe site
        # cannot recompute it.
        c.lane_shift = signed_lane_shift(
            c.give_player_ids, c.receive_player_ids,
            trade_service._players, outlook, _vs)
        if FLAGS.trade_lanes:
            c.lane = classify_lane(
                c.give_player_ids, c.receive_player_ids,
                trade_service._players, outlook, _vs)
    return cards


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


def compose_deck(arm_lists: dict[str, list], *, league_id: str,
                 iso_week: str | None = None,
                 roster: tuple[str, ...] | list[str] | None = None,
                 limit: int | None = None,
                 ) -> tuple[dict[str, GroupResult], list[str], DraftResult]:
    """Build the groups, compose each one's quota, and interleave the GROUPS.

    Returns (groups, group_order, draft). `bakeoff_group_size = 0` is the kill
    value: no groups at all, and the caller falls back to Phase 3's per-arm
    team draft.
    """
    size = group_size()
    if size <= 0:
        return {}, [], DraftResult()

    value_slots = min(group_value_slots(), size)
    backfill = backfill_residual_slots()
    reallocate = lane_reallocate()
    groups: dict[str, GroupResult] = {}
    for grp in groups_for(roster):
        groups[grp.key] = compose_group(
            grp, arm_lists.get(grp.arm, []),
            size=size, value_slots=value_slots, backfill=backfill,
            reallocate=reallocate,
            outlook_leads=outlook_leads_for(grp.key, league_id, iso_week))
    order = draft_order_for(list(groups), league_id, iso_week)
    return groups, order, group_draft(groups, order, arm_lists, limit=limit)


def run_bakeoff(
    *,
    generate: Callable[..., list],
    gen_v2: Callable[..., list],
    league_id: str,
    fairness_threshold: float | None = None,
    trade_intent: str | None = None,
    iso_week: str | None = None,
    interleave: bool | None = None,
    limit: int | None = None,
    roster: tuple[str, ...] | list[str] | None = None,
) -> BakeoffRun:
    """Run every ROSTERED arm SEQUENTIALLY on this thread, compose the groups
    and interleave them.

    Sequential is deliberate (PLAN.md §3.1): the config seam is a
    `threading.local()`, so sibling threads would each need their own context
    and the discipline is easy to break; the enumeration is CPU-bound anyway.

    `generate(**overrides)` runs the normal engine — the caller binds the job's
    kwargs and merges any overrides. It is called once per rostered engine arm:
    inside arm A's context when arm A is rostered, and once plain for arm B.
    `gen_v2(**overrides)` calls trade_gen_v2 directly.

    An arm that raises is recorded with `error` and an empty list; it then
    forfeits every slot. An arm producing nothing is DATA (§3.2), never an
    exception — arm C under-producing is an expected, measured outcome, and so
    is a group that cannot fill a lane quota.
    """
    if roster is None:
        roster = arm_roster()
    roster = tuple(roster)
    if interleave is None:
        interleave = serve_interleaved()
    if limit is None:
        limit = deck_limit()
    intent = effective_trade_intent(trade_intent)

    arms: dict[str, ArmResult] = {}
    t_all = time.monotonic()
    for arm in (a for a in GENERATION_ORDER if a in roster):
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
        # Drained here, immediately after the call that wrote it, and only
        # for arm C — `gen_v2_cards` is the only writer. An arm that raised
        # leaves `{}`, which is the honest reading: no stage completed.
        diag = last_gen_v2_diagnostics() if arm == ARM_GEN_V2 else {}
        arms[arm] = ArmResult(
            arm=arm, cards=cards,
            gen_ms=int((time.monotonic() - t0) * 1000),
            error=err,
            diagnostics=diag,
            # gen_v2 takes no fairness_threshold — recording None is the
            # honest answer and is itself the fact a reader needs.
            fairness_threshold=(None if arm == ARM_GEN_V2
                                else fairness_threshold),
            trade_intent=intent,
            config=cfg_seen or snapshot_config(),
        )

    arm_lists = {a: arms[a].cards for a in roster}
    groups, group_order, draft = compose_deck(
        arm_lists, league_id=league_id, iso_week=iso_week, roster=roster,
        limit=limit)
    if not groups:
        # bakeoff_group_size = 0 — Phase 3's plain per-ARM team draft.
        group_order = draft_order_for(roster, league_id, iso_week)
        draft = team_draft(arm_lists, group_order, limit=limit)

    run = BakeoffRun(
        run_id=uuid.uuid4().hex,
        arm_order=group_order,
        arms=arms,
        draft=draft,
        served_arm=None if interleave else DARK_SERVED_ARM,
        total_ms=int((time.monotonic() - t_all) * 1000),
        groups=groups,
    )
    log.info(
        "bake-off run %s league=%s roster=%s order=%s serve=%s arms=%s "
        "short=%s total_ms=%d",
        run.run_id, league_id, "/".join(roster), "/".join(group_order),
        run.served_arm or "interleaved",
        {a: (len(r.cards), r.gen_ms) for a, r in arms.items()},
        {k: gr.short for k, gr in groups.items()}, run.total_ms,
    )
    return run
