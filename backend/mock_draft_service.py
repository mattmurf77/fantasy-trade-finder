"""FTF-native mock draft — engine + calibration (draft-extensions W2a).

Spec: ``docs/plans/draft-extensions/plan.md`` §5 · ``lld.md`` §2.3/§3.3/§4.2 ·
``docs/plans/rookie-draft/mock-draft-plan.md`` §4-9 (adopted), with the plan's
three binding amendments.

A flat module beside ``draft_board_service.py`` (KD-1): pure logic with every
input injected, so the M1 corpora and unit tests drive it with no Flask, no
DB and no network. ``backend/server.py`` owns resolution and persistence.

Three properties this module exists to hold
-------------------------------------------
**Amendment 1 — ONE consensus definition.** The CPU drafters rank candidates
through :func:`draft_board_service._undrafted` with ``basis="consensus"`` and
the caller-injected ``consensus_elo`` — the very map ``server`` builds from
``_get_universal_pool()``. There is deliberately no second ordering in this
file: a second "market consensus" would let the Draft Room's undrafted list
and the mock's bots visibly disagree on one screen. ``basis="my_board"``
re-sorts the *user's* undrafted list only and never reaches a CPU decision.

**Amendment 2 — the noise model is FITTED, and the fit is a GATE.** See
:data:`CPU_MODEL_VALIDATED` and :data:`CALIBRATION_ARTIFACT`. W2a's
single-parameter uniform-jitter model failed the gate on a model-FORM ground;
W2b re-specced it as the two-parameter mixture in :func:`cpu_pick` and re-ran
the same gate unchanged. The re-fit **still FAILS**, on one bar of four
instead of four of four, so :func:`advance_cpu` remains unreachable from the
routes; the engine, its tests and the harness that produced the verdict all
ship so the verdict is reproducible and a further re-spec can be re-gated
without a rebuild.

**INV-10 — deterministic and self-contained.** Same ``rng_seed`` ⇒ a
byte-identical draft; zero platform egress after creation (this module
imports no HTTP client and performs no I/O of any kind).
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from . import draft_board_service as dbs

SCHEMA = 1

# ── Closed vocabularies (mirrors of the I-6 board vocabulary) ─────────────
STATUS_ACTIVE = "active"
STATUS_COMPLETE = "complete"
STATUS_ABANDONED = "abandoned"

TYPE_LINEAR = "linear"
TYPE_SNAKE = "snake"

ORDER_SOURCE_ASSIGNED = "assigned"
ORDER_SOURCE_RANDOMIZED = "randomized"

BY_USER = "user"
BY_CPU = "cpu"

PERSONA_DECLARED = "declared"
PERSONA_INFERRED = "inferred"
PERSONA_DEFAULT = "default"
DEFAULT_OUTLOOK = "not_sure"

#: Reason strings on the typed-empty ``200 {"empty": true}`` contract that
#: ``GET/POST /api/mock-draft`` share with M2. New states ride this field
#: rather than a new member of any closed client enum (plan D10).
REASON_CLASS_NOT_LOADED = "class_not_loaded"
REASON_CPU_MODEL_UNVALIDATED = "cpu_model_unvalidated"

# ── Tunables (``model_config``; see docs/config-reference.md) ─────────────
#: Product cap on how many consensus slots a *need* can pull a player up. NOT
#: a fitted parameter — fitting it alongside the noise is unidentifiable at
#: n = 23 (lld §4.2.3 step 2).
MOCK_MAX_REACH_DEFAULT = 3.0

#: THE two fitted parameters of the W2b mixture (see :func:`cpu_pick`).
#: ``mock_bpa_prob`` = P(this pick is the strict board pick, no idiosyncrasy).
#: ``mock_reach_decay`` = the per-slot survival ratio of the reach branch:
#: reaching one slot further is ``decay`` times as likely. The values below are
#: the W2b fit on ``lakeview-complete`` rounds 1-2 — recorded, but NOT
#: validated: see :data:`CPU_MODEL_VALIDATED`.
MOCK_BPA_PROB_DEFAULT = 0.50
MOCK_REACH_DECAY_DEFAULT = 0.95

_DEFAULT_CFG: dict[str, float] = {
    "mock_max_reach_slots": MOCK_MAX_REACH_DEFAULT,
    "mock_bpa_prob": MOCK_BPA_PROB_DEFAULT,
    "mock_reach_decay": MOCK_REACH_DECAY_DEFAULT,
}

#: Candidate window ``K`` — the deepest a CPU may reach, in consensus slots.
#: A PRODUCT CAP, never a fitted parameter (W2b brief): the mixture's reach
#: branch is truncated BY it rather than fitted TO it. Set once, from the FIT
#: block alone — ``lakeview-complete`` rounds 1-2 reach at most 9 slots, so a
#: window under 10 could not represent the fit data at all — rounded up to 12.
#: Beyond ~a dozen slots a bot's pick stops reading as conviction and starts
#: reading as broken, which is the product half of the same number.
MOCK_CANDIDATE_WINDOW = 12

#: "Worth a 3rd or better" — the `third` tier floor from
#: ``docs/cross-client-invariants.md``. A roster-clogging body below this does
#: not count as filling a slot.
VIABLE_ELO_FLOOR = 1280.0

_POSITIONS = ("QB", "RB", "WR", "TE")

#: Bench target per position (mock-draft-plan §6.3). QB gets one only in a
#: superflex league; TE never does.
_BENCH_TARGET = {"QB": 0, "RB": 1, "WR": 1, "TE": 0}
_BENCH_TARGET_QB_SUPERFLEX = 1

_ROOKIE_MAX_ROUNDS = 8          # mirrors draft_status.ROOKIE_MAX_ROUNDS
DEFAULT_ROUNDS = 4

# ---------------------------------------------------------------------------
# THE CALIBRATION GATE (I-10)
# ---------------------------------------------------------------------------
# `docs/plans/draft-extensions/mock-calibration-2026-08b.md` is a GATE, not a
# report (plan §5, lld §4.2.3).
#
# W2a: the specified single-parameter model — argmin over
# `rank - need_bonus - Uniform(0, jitter)` — failed all FOUR bars. The failure
# was a model-FORM failure: its reachable support is bounded by roughly
# `max_reach + jitter` slots while 21 % of real picks reach 6-9.
#
# W2b (this file): re-specced to the two-parameter mixture in `cpu_pick` and
# re-ran the SAME gate, unchanged. It now passes the Lakeview hold-out on both
# bars and the independent `mfl-complete` corpus on KS — three of four — and
# fails `mfl-complete`'s paired-mean bar. The residual is NOT a model-form
# failure: the two corpora's observed mean |d| differ by 2.7 slots, 2.7x the
# +/-1.0 bar itself, so no corpus-invariant noise model can satisfy both mean
# bars at once. See the artifact §6 before touching anything.
#
# Per the plan's W2 abort criterion the CPU-bot mock therefore stays CUT: the
# routes refuse to generate CPU picks while this stays False, returning the
# typed-empty `200 {"empty": true, "reason": "cpu_model_unvalidated"}` that
# M2's contract already carries. Do NOT flip this to re-enable bots without
# re-running `test_mock_draft.py::test_w2_16_calibration_gate` green against a
# re-specced model — flipping it is the exact "fit on the validation set"
# failure the amendment exists to prevent.
CPU_MODEL_VALIDATED = False
CALIBRATION_ARTIFACT = "docs/plans/draft-extensions/mock-calibration-2026-08b.md"


class MockDraftError(Exception):
    """Base for the engine's typed refusals."""

    code = "mock_draft_error"


class NotYourTurn(MockDraftError):
    code = "not_your_turn"


class PlayerUnavailable(MockDraftError):
    code = "player_unavailable"


class CalibrationGateClosed(MockDraftError):
    """CPU generation attempted while :data:`CPU_MODEL_VALIDATED` is False."""

    code = REASON_CPU_MODEL_UNVALIDATED


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _c(key: str, overrides: Mapping[str, float] | None = None) -> float:
    """A ``model_config`` value with the module default as the floor.

    Deliberately NOT seeded into ``_MODEL_CONFIG_DEFAULTS``: these two keys
    belong to a feature whose gate is closed, so the code default is the
    single source until an operator inserts a row. ``overrides`` is how a
    persisted mock replays at ITS OWN fitted noise (lld §3.3: the noise
    parameters are snapshotted into the row) even if the live config moved.
    """
    if overrides is not None and key in overrides:
        return float(overrides[key])
    try:                                        # pragma: no cover - DB optional
        from .database import get_config
        live = get_config() or {}
    except Exception:
        live = {}
    value = live.get(key)
    return float(value) if value is not None else _DEFAULT_CFG[key]


def noise_params(overrides: Mapping[str, float] | None = None) -> dict[str, float]:
    """``{bpa_prob, reach_decay, max_reach}`` — snapshotted into a new row."""
    return {
        "bpa_prob": _c("mock_bpa_prob", overrides),
        "reach_decay": _c("mock_reach_decay", overrides),
        "max_reach": _c("mock_max_reach_slots", overrides),
    }


# ---------------------------------------------------------------------------
# Injection surface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MockContext:
    """Everything the engine knows; nothing it can look up itself.

    Mirrors :class:`draft_board_service.BoardRequest`'s stance — the caller
    resolves the league, the pool and the rosters, so this module stays free
    of Flask, the DB and the network (INV-10's egress half is structural).
    """

    league_id: str
    season: int
    #: THE consensus map — ``server._get_universal_pool(fmt)[1]`` (amendment 1).
    consensus_elo: Mapping[str, float]
    #: ``load_rookie_player_ids(season)`` — THE rookie predicate (I-2).
    rookie_ids: frozenset[str]
    #: Player rows in ``draft_board_service`` shape, keyed by player id.
    player_rows: Mapping[str, Mapping[str, Any]]
    #: Rostered player ids league-wide, subtracted from the pool (D7).
    rostered_ids: frozenset[str] = frozenset()
    #: Pre-draft roster player ids per owner — the severity input.
    rosters: Mapping[str, Sequence[str]] = field(default_factory=dict)
    #: The league's ``roster_positions`` template.
    lineup_slots: Sequence[str] = ()
    #: Display names per owner id.
    usernames: Mapping[str, str] = field(default_factory=dict)
    scoring_format: str = "1qb_ppr"

    def fetchers(self) -> "dbs.PlatformFetchers":
        """A fetcher shim over the injected maps — no upstream is bound, so a
        stray platform read raises instead of going live."""
        return dbs.PlatformFetchers(
            rookie_ids_fn=lambda season: set(self.rookie_ids),
            players_fn=lambda ids: {p: self.player_rows[p]
                                    for p in ids if p in self.player_rows},
        )


# ---------------------------------------------------------------------------
# The consensus pool — ONE definition (amendment 1)
# ---------------------------------------------------------------------------

def consensus_pool(ctx: MockContext) -> list[dict]:
    """The mock's draftable pool, in consensus order.

    This is ``draft_board_service._undrafted(..., basis="consensus")`` itself,
    not a re-implementation: the room's undrafted list and the bots' board are
    the same list by construction (T-W2-15). Unvalued rookies are present and
    sort last (D7); a CPU team reaches them only once the valued pool is gone.

    Computed ONCE per mock and then consumed by removal. That is exactly
    equivalent to recomputing per pick — the sort key is per-row, so deleting
    rows never reorders the survivors — and it is what makes a 60-pick CPU
    tail free.
    """
    rows, class_loaded = dbs._undrafted(
        int(ctx.season), set(), set(ctx.rostered_ids),
        dbs.BASIS_CONSENSUS, None, ctx.consensus_elo, ctx.fetchers())
    return rows if class_loaded else []


def class_loaded(ctx: MockContext) -> bool:
    """False ⇒ the caller owes a typed-empty ``class_not_loaded`` (M2)."""
    return bool(ctx.rookie_ids)


def _reranked(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Re-number ``rank`` 1..n over a subsequence, preserving order."""
    out = []
    for i, row in enumerate(rows, start=1):
        entry = dict(row)
        entry["rank"] = i
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Positional need (mock-draft-plan §6.3)
# ---------------------------------------------------------------------------

def positional_needs(roster_rows: Sequence[Mapping[str, Any]] | Sequence[str],
                     lineup_slots: Sequence[str],
                     consensus_elo: Mapping[str, float] | None = None,
                     player_rows: Mapping[str, Mapping[str, Any]] | None = None,
                     ) -> dict[str, float]:
    """``{pos: viable_count}`` — the severity inputs for one team.

    ``roster_rows`` may be player ids (with ``consensus_elo``/``player_rows``
    supplied) or pre-resolved ``{"player_id", "position", "value"}`` rows.
    A player counts as *viable* at his position only at or above
    :data:`VIABLE_ELO_FLOOR` — roster-clogging depth does not fill a slot.

    Returns counts, not severities: the count is what mutates as a team
    drafts, and :func:`severity` is the cheap arithmetic on top.
    """
    counts = {pos: 0 for pos in _POSITIONS}
    for row in roster_rows or ():
        if isinstance(row, Mapping):
            pid = str(row.get("player_id") or "")
            position = str(row.get("position") or "").upper()
            value = row.get("value")
        else:
            pid = str(row)
            meta = (player_rows or {}).get(pid) or {}
            position = str(meta.get("position") or "").upper()
            value = None
        if value is None and consensus_elo is not None:
            value = consensus_elo.get(pid)
        if position in counts and value is not None and float(value) >= VIABLE_ELO_FLOOR:
            counts[position] += 1
    return counts


def slot_targets(lineup_slots: Sequence[str]) -> dict[str, tuple[int, int]]:
    """``{pos: (S, B)}`` — dedicated starter slots and the bench target.

    Flex slots are excluded from ``S`` (v1 simplification, O-M5): only slots
    whose eligibility set is exactly one position count, which is what
    ``power_rankings.LINEUP_SLOT_ELIGIBILITY`` calls a dedicated slot.
    ``B(QB)`` is 1 only when the template carries a superflex slot, so a 1QB
    league's CPU never reaches for a QB — emergent, not special-cased.
    """
    from .power_rankings import LINEUP_SLOT_ELIGIBILITY
    dedicated = {pos: 0 for pos in _POSITIONS}
    superflex = False
    for slot in lineup_slots or ():
        eligible = LINEUP_SLOT_ELIGIBILITY.get(slot)
        if eligible is None:
            continue
        if len(eligible) == 1 and eligible[0] in dedicated:
            dedicated[eligible[0]] += 1
        elif "QB" in eligible:
            superflex = True
    bench = dict(_BENCH_TARGET)
    if superflex:
        bench["QB"] = _BENCH_TARGET_QB_SUPERFLEX
    return {pos: (dedicated[pos], bench[pos]) for pos in _POSITIONS}


def severity(viable: Mapping[str, int], targets: Mapping[str, tuple[int, int]],
             pos: str) -> float:
    """``clamp01((S + B - viable) / (S + B))`` — 1.0 = nothing viable there."""
    s, b = targets.get(pos, (0, 0))
    denom = s + b
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, (denom - int(viable.get(pos, 0))) / float(denom)))


def need_weight(outlook: str | None) -> float:
    """``trade_service.outlook_alpha`` — the existing map, reused verbatim.

    This single knob is what makes contenders needs-drafters and rebuilders
    BPA-drafters; it is already operator-tunable and already documented.
    """
    from .trade_service import outlook_alpha
    return float(outlook_alpha(outlook))


# ---------------------------------------------------------------------------
# The scoring function (mock-draft-plan §6.1)
# ---------------------------------------------------------------------------

def _gumbel(rng: random.Random, scale: float) -> float:
    """A standard Gumbel(0, ``scale``) draw."""
    u = min(max(rng.random(), 1e-12), 1.0 - 1e-12)
    return -float(scale) * math.log(-math.log(u))


def _decay_to_scale(decay: float) -> float:
    """``beta`` such that the reach branch decays by ``decay`` per slot.

    ``P(reach = d) ∝ exp(-d / beta)``, so ``decay = exp(-1/beta)`` and
    ``beta = -1 / ln(decay)``. ``decay <= 0`` ⇒ 0 ⇒ the branch is inert.
    """
    decay = float(decay)
    if decay <= 0.0:
        return 0.0
    decay = min(decay, 0.999)              # 1.0 = flat over the window
    return -1.0 / math.log(decay)


def cpu_pick(candidates_ranked: Sequence[Mapping[str, Any]],
             persona_outlook: str | None,
             needs_for_team: Mapping[str, float],
             rng: random.Random,
             *,
             max_reach: float = MOCK_MAX_REACH_DEFAULT,
             bpa_prob: float = MOCK_BPA_PROB_DEFAULT,
             reach_decay: float = MOCK_REACH_DECAY_DEFAULT) -> str:
    """One CPU pick — ``argmin(rank - need_bonus - reach_noise)``.

    ``candidates_ranked`` is the head of the consensus pool, 1-based by list
    position. ``needs_for_team`` is ``{pos: severity}``. Ties resolve to the
    better consensus rank because the scan keeps the first strict minimum.

    **The need term** is unchanged from W2a and is not part of the noise model:
    ``need_bonus <= need_weight * 1.0 * max_reach``, so a championship team with
    a desperate need reaches at most ``max_reach`` slots and a `jets` team takes
    the board pick. One scoring function, persona = parameters.

    **The noise term is the W2b re-spec** (build-w2b.md). W2a drew
    ``Uniform(0, jitter)`` per candidate; its reachable support was bounded by
    ``max_reach + jitter`` ≈ 6 slots, which cannot produce the observed shape —
    ~44 % of real picks are exactly the board pick, yet 21 % reach 6-9 slots.
    That is a MIXTURE, so the model is one:

    * with probability ``bpa_prob`` the CPU takes the strict board pick — every
      candidate's noise is 0, so the argmin is exactly ``rank - need_bonus``;
    * otherwise each candidate draws an i.i.d. ``Gumbel(0, beta)``.

    Gumbel is chosen over log-normal/negative-binomial for one structural
    reason, not for fit convenience: by the Gumbel-max identity, an argmin over
    ``rank - G`` with ``G ~ Gumbel(0, beta)`` is *exactly* a softmax over
    ``-rank``, i.e. the reach depth is **geometric** with per-slot ratio
    ``exp(-1/beta) = reach_decay`` — the heavy-tailed discrete law the evidence
    asks for, obtained without leaving the shipped per-candidate additive-noise
    code shape and without a second ordering of the pool (amendment 1).

    The two parameters are ``bpa_prob`` and ``reach_decay``. The candidate
    window ``K`` (:data:`MOCK_CANDIDATE_WINDOW`) truncates the geometric tail
    and is deliberately NOT fitted.
    """
    if not candidates_ranked:
        raise PlayerUnavailable("no candidates")
    weight = need_weight(persona_outlook)
    scale = _decay_to_scale(reach_decay)
    # ONE Bernoulli per pick, drawn first so the branch (and therefore the
    # whole stream) is a pure function of the seed.
    reaching = scale > 0.0 and rng.random() >= float(bpa_prob)
    best_id: str | None = None
    best_score: float | None = None
    for rank, row in enumerate(candidates_ranked, start=1):
        pos = str(row.get("position") or "").upper()
        bonus = weight * float(needs_for_team.get(pos, 0.0)) * float(max_reach)
        noise = _gumbel(rng, scale) if reaching else 0.0
        score = rank - bonus - noise
        if best_score is None or score < best_score:
            best_id, best_score = str(row.get("player_id")), score
    return str(best_id)


def candidate_window(max_reach: float) -> int:
    """``K`` — the scan width, and the product cap on a CPU reach.

    :data:`MOCK_CANDIDATE_WINDOW`, floored so the *need* term can always reach
    its own ``max_reach`` cap even if the window is retuned downwards.
    """
    return max(MOCK_CANDIDATE_WINDOW, int(math.ceil(float(max_reach))) + 1)


# ---------------------------------------------------------------------------
# Turn order
# ---------------------------------------------------------------------------

def pick_slots(rounds: int, teams: int, draft_type: str) -> list[dict]:
    """``[{pick_no, round, slot}]`` for the whole draft.

    ``snake`` reverses even rounds. Note the execution-lens finding the plan
    records: snake vs linear changes slot NUMBERING only, never ownership.
    """
    out: list[dict] = []
    pick_no = 0
    for round_no in range(1, int(rounds) + 1):
        slots = range(1, int(teams) + 1)
        if draft_type == TYPE_SNAKE and round_no % 2 == 0:
            slots = range(int(teams), 0, -1)
        for slot in slots:
            pick_no += 1
            out.append({"pick_no": pick_no, "round": round_no, "slot": slot})
    return out


def owner_of(pick_no: int, settings: Mapping[str, Any]) -> str | None:
    """Who is on the clock at ``pick_no``.

    The ownership overlay (traded picks) wins over the slot order, so a team
    can be on the clock twice in a row. Ownership is snapshotted at creation
    so a mid-mock ``draft_picks`` resync cannot shift picks under the user.
    """
    ownership = settings.get("ownership") or {}
    owner = ownership.get(str(pick_no)) or ownership.get(pick_no)
    if owner:
        return str(owner)
    order = settings.get("order") or []
    for slot_row in settings.get("slots") or []:
        if int(slot_row["pick_no"]) == int(pick_no):
            idx = int(slot_row["slot"]) - 1
            if 0 <= idx < len(order):
                return str(order[idx])
            return None
    return None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def build_settings(ctx: MockContext,
                   *,
                   owners: Sequence[str],
                   user_owner_id: str,
                   rounds: int | None = None,
                   draft_type: str | None = None,
                   order: Sequence[str] | None = None,
                   order_source: str = ORDER_SOURCE_RANDOMIZED,
                   ownership: Mapping[Any, str] | None = None,
                   personas: Mapping[str, Mapping[str, str]] | None = None,
                   rng: random.Random | None = None,
                   config_overrides: Mapping[str, float] | None = None,
                   ) -> dict:
    """The ``settings`` JSON for a new mock (lld §3.3).

    ``order`` absent ⇒ a seeded shuffle labelled ``order_source:"randomized"``
    — never an invented "real" order (KD-6). ``rounds`` is clamped to
    ``1..ROOKIE_MAX_ROUNDS``. The fitted noise parameters are snapshotted so a
    resumed mock replays identically even if ``model_config`` is retuned.
    """
    owners = [str(o) for o in owners]
    teams = len(owners)
    rounds = int(rounds or DEFAULT_ROUNDS)
    rounds = max(1, min(_ROOKIE_MAX_ROUNDS, rounds))
    draft_type = draft_type if draft_type in (TYPE_LINEAR, TYPE_SNAKE) else TYPE_LINEAR

    if order:
        resolved_order = [str(o) for o in order]
        resolved_source = order_source
    else:
        resolved_order = list(owners)
        (rng or random.Random(0)).shuffle(resolved_order)
        resolved_source = ORDER_SOURCE_RANDOMIZED

    resolved_personas = {
        str(o): dict(((personas or {}).get(str(o))
                      or {"outlook": DEFAULT_OUTLOOK, "source": PERSONA_DEFAULT}))
        for o in owners
    }
    return {
        "rounds": rounds,
        "type": draft_type,
        "teams": teams,
        "order": resolved_order,
        "order_source": resolved_source,
        "slots": pick_slots(rounds, teams, draft_type),
        "ownership": {str(k): str(v) for k, v in (ownership or {}).items()},
        "personas": resolved_personas,
        "user_owner_id": str(user_owner_id),
        "lineup_slots": list(ctx.lineup_slots),
        "scoring_format": ctx.scoring_format,
        "noise": noise_params(config_overrides),
    }


def new_state(ctx: MockContext, settings: Mapping[str, Any], rng_seed: int,
              *, mock_id: int | None = None, user_id: str = "") -> dict:
    """A fresh, unpersisted mock. ``advance_cpu`` is the caller's next step."""
    return {
        "id": mock_id,
        "user_id": str(user_id),
        "league_id": str(ctx.league_id),
        "season": int(ctx.season),
        "status": STATUS_ACTIVE,
        "settings": dict(settings),
        "picks": [],
        "rng_seed": int(rng_seed),
    }


def total_picks(settings: Mapping[str, Any]) -> int:
    return len(settings.get("slots") or [])


def next_pick(state: Mapping[str, Any]) -> dict | None:
    """The slot on the clock, or ``None`` when the draft is done."""
    made = len(state.get("picks") or [])
    slots = state["settings"].get("slots") or []
    if made >= len(slots):
        return None
    slot = dict(slots[made])
    owner = owner_of(slot["pick_no"], state["settings"])
    slot["roster_id"] = owner
    slot["is_user"] = owner is not None and owner == state["settings"].get("user_owner_id")
    return slot


def _pick_rng(state: Mapping[str, Any], pick_no: int) -> random.Random:
    """Per-pick RNG (lld §3.3). Resume replays identically because the seed
    is a pure function of ``(rng_seed, pick_no)`` — never of call order."""
    return random.Random(int(state["rng_seed"]) * 10_007 + int(pick_no))


def _available(ctx: MockContext, state: Mapping[str, Any],
               pool: Sequence[Mapping[str, Any]] | None = None) -> list[dict]:
    """The consensus pool minus everything taken in THIS mock."""
    taken = {str(p["player_id"]) for p in (state.get("picks") or [])}
    rows = pool if pool is not None else consensus_pool(ctx)
    return _reranked([r for r in rows if str(r["player_id"]) not in taken])


def _team_viable(ctx: MockContext, state: Mapping[str, Any],
                 owner_id: str) -> dict[str, int]:
    """Viable counts for ``owner_id``, including what it drafted in the mock.

    Recomputed from the persisted picks rather than carried in memory, so a
    resumed mock and a continuous one see the same needs (T-W2-11).
    """
    counts = positional_needs(ctx.rosters.get(owner_id) or (), ctx.lineup_slots,
                              ctx.consensus_elo, ctx.player_rows)
    for pick in state.get("picks") or ():
        if str(pick.get("roster_id")) != str(owner_id):
            continue
        row = ctx.player_rows.get(str(pick["player_id"])) or {}
        pos = str(row.get("position") or "").upper()
        if pos in counts:
            counts[pos] += 1
    return counts


def _severities(ctx: MockContext, state: Mapping[str, Any],
                owner_id: str) -> dict[str, float]:
    targets = slot_targets(state["settings"].get("lineup_slots")
                           or ctx.lineup_slots)
    viable = _team_viable(ctx, state, owner_id)
    return {pos: severity(viable, targets, pos) for pos in _POSITIONS}


def advance_cpu(state: dict, ctx: MockContext,
                pool: Sequence[Mapping[str, Any]] | None = None,
                *, allow_unvalidated_model: bool = False) -> dict:
    """Run CPU picks until the user is on the clock, or the draft completes.

    Raises :class:`CalibrationGateClosed` while :data:`CPU_MODEL_VALIDATED` is
    False unless the caller explicitly opts in — the routes never do, the
    calibration harness and the engine tests do. That is the plan's W2 abort
    criterion expressed in code rather than only in prose.
    """
    if not CPU_MODEL_VALIDATED and not allow_unvalidated_model:
        raise CalibrationGateClosed(CALIBRATION_ARTIFACT)

    noise = state["settings"].get("noise") or noise_params()
    max_reach = float(noise.get("max_reach", MOCK_MAX_REACH_DEFAULT))
    bpa_prob = float(noise.get("bpa_prob", MOCK_BPA_PROB_DEFAULT))
    reach_decay = float(noise.get("reach_decay", MOCK_REACH_DECAY_DEFAULT))
    window = candidate_window(max_reach)
    rows = pool if pool is not None else consensus_pool(ctx)

    while True:
        slot = next_pick(state)
        if slot is None:
            state["status"] = STATUS_COMPLETE
            return state
        if slot["is_user"]:
            return state
        available = _available(ctx, state, rows)
        if not available:
            state["status"] = STATUS_COMPLETE
            return state
        owner = slot["roster_id"]
        persona = (state["settings"].get("personas") or {}).get(
            str(owner), {"outlook": DEFAULT_OUTLOOK})
        player_id = cpu_pick(available[:window], persona.get("outlook"),
                             _severities(ctx, state, str(owner)),
                             _pick_rng(state, slot["pick_no"]),
                             max_reach=max_reach, bpa_prob=bpa_prob,
                             reach_decay=reach_decay)
        _append(state, slot, player_id, BY_CPU)


def apply_user_pick(state: dict, ctx: MockContext, player_id: str,
                    pool: Sequence[Mapping[str, Any]] | None = None) -> dict:
    """Validate the turn + eligibility, append the pick, advance the CPUs."""
    slot = next_pick(state)
    if slot is None or not slot["is_user"]:
        raise NotYourTurn(str(slot["pick_no"]) if slot else "complete")
    available = {str(r["player_id"]) for r in _available(ctx, state, pool)}
    if str(player_id) not in available:
        raise PlayerUnavailable(str(player_id))
    _append(state, slot, str(player_id), BY_USER)
    if next_pick(state) is None:
        state["status"] = STATUS_COMPLETE
        return state
    return advance_cpu(state, ctx, pool, allow_unvalidated_model=True)


def _append(state: dict, slot: Mapping[str, Any], player_id: str, by: str) -> None:
    state.setdefault("picks", []).append({
        "pick_no": int(slot["pick_no"]),
        "round": int(slot["round"]),
        "slot": int(slot["slot"]),
        "roster_id": slot["roster_id"],
        "player_id": str(player_id),
        "by": by,
    })
    if len(state["picks"]) >= total_picks(state["settings"]):
        state["status"] = STATUS_COMPLETE


# ---------------------------------------------------------------------------
# Payload (the I-6 vocabulary, verbatim)
# ---------------------------------------------------------------------------

def state_payload(state: Mapping[str, Any], ctx: MockContext,
                  *, basis: str = dbs.BASIS_CONSENSUS,
                  board_elo: Mapping[str, float] | None = None,
                  notice_code: str | None = None) -> dict:
    """``GET/POST /api/mock-draft``'s body — same entry shapes as the board.

    ``basis="my_board"`` re-sorts the USER's undrafted list only. It never
    touched a CPU decision: those were made against the consensus pool at
    pick time and are already recorded (amendment 1, T-W2-14).
    """
    settings = state["settings"]
    taken = {str(p["player_id"]) for p in (state.get("picks") or [])}
    if basis == dbs.BASIS_MY_BOARD:
        rows, _ = dbs._undrafted(int(ctx.season), taken, set(ctx.rostered_ids),
                                 dbs.BASIS_MY_BOARD, board_elo,
                                 ctx.consensus_elo, ctx.fetchers())
        undrafted = rows
    else:
        undrafted = _available(ctx, state)

    user_owner = str(settings.get("user_owner_id") or "")
    slot = next_pick(state)
    order = []
    for row in settings.get("slots") or ():
        owner = owner_of(row["pick_no"], settings)
        order.append({
            "slot": row["slot"],
            "round": row["round"],
            "pick_no": row["pick_no"],
            "owner_user_id": owner,
            "owner_username": ctx.usernames.get(str(owner)) if owner else None,
            "original_user_id": owner,
            "original_username": ctx.usernames.get(str(owner)) if owner else None,
            "is_traded": bool((settings.get("ownership") or {}).get(str(row["pick_no"]))),
        })

    picks = []
    for pick in state.get("picks") or ():
        row = ctx.player_rows.get(str(pick["player_id"])) or {}
        picks.append({
            "round": pick["round"],
            "pick_no": pick["pick_no"],
            "slot": pick["slot"],
            "player_id": pick["player_id"],
            "name": row.get("full_name") or row.get("name") or "",
            "position": str(row.get("position") or "").upper(),
            "team": row.get("team") or None,
            "picked_by_user_id": pick["roster_id"],
            "picked_at": None,
            "by": pick["by"],
        })

    return {
        "schema": SCHEMA,
        "mock_id": state.get("id"),
        "status": state.get("status"),
        "league_id": str(ctx.league_id),
        "season": int(ctx.season),
        "on_the_clock": slot,
        "order": order,
        "picks": picks,
        "undrafted": undrafted,
        "undrafted_basis": basis,
        "my_picks": [p for p in picks if str(p["picked_by_user_id"]) == user_owner],
        "settings_echo": {
            "rounds": settings.get("rounds"),
            "type": settings.get("type"),
            "teams": settings.get("teams"),
            "order_source": settings.get("order_source"),
            "personas": settings.get("personas"),
            "noise": settings.get("noise"),
        },
        "notice": dbs._notice(notice_code),
    }


def empty_payload(reason: str) -> dict:
    """M2's typed-empty contract — the only place a new state may appear
    without touching a closed client enum (plan D10)."""
    return {"schema": SCHEMA, "empty": True, "reason": reason}


# ---------------------------------------------------------------------------
# Persistence helpers (JSON columns ↔ state dict)
# ---------------------------------------------------------------------------

def dumps(state: Mapping[str, Any]) -> tuple[str, str]:
    """``(settings_json, picks_json)`` — sort_keys so a resumed row is
    byte-comparable against a continuous one (T-W2-11)."""
    return (json.dumps(state["settings"], sort_keys=True),
            json.dumps(state.get("picks") or [], sort_keys=True))


def loads(row: Mapping[str, Any]) -> dict:
    """Rehydrate a ``mock_drafts`` row into an engine state."""
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "league_id": row.get("league_id"),
        "season": int(row.get("season") or 0),
        "status": row.get("status") or STATUS_ACTIVE,
        "settings": json.loads(row.get("settings") or "{}"),
        "picks": json.loads(row.get("picks") or "[]"),
        "rng_seed": int(row.get("rng_seed") or 0),
    }


# ---------------------------------------------------------------------------
# Calibration harness (I-10 — the GATE, lld §4.2.3)
# ---------------------------------------------------------------------------
# The observable and the simulator live here rather than in the test file so
# the number in the artifact and the number the engine produces cannot drift:
# `simulate_reaches` drives the SHIPPED `cpu_pick`. The statistics (KS,
# Wasserstein, the grid search) live in `backend/tests/test_mock_draft.py`.

def reach_series(drafted_ids: Sequence[str],
                 pool_order: Sequence[str]) -> list[int]:
    """The empirical reach ``d_i`` for one recorded draft.

    ``d_i`` = how many better-valued AVAILABLE players the pick passed over —
    i.e. the player's 1-based consensus rank in the pool *as it stood at that
    pick*, minus 1. ``d_i > 0`` is a reach; ``d_i == 0`` is best-player-
    available.

    **Deviation from lld §4.2.3, deliberate and recorded in the artifact.**
    The LLD writes ``d_i = consensus_rank_at_pick - i`` *and* says the rank is
    taken over the pool with drafted players removed. Those two clauses
    contradict each other: over a remaining pool the BPA pick always ranks 1,
    so ``rank - i`` would read ``1 - i`` and a pure-BPA draft would score a
    huge "fall". Read the other way (a rank frozen over the pre-draft pool)
    the observable is non-stationary — measured on `lakeview-complete` it runs
    mean |d| 2.67 in rounds 1-2 against 5.79 in rounds 3-4, which no
    single-parameter model can bridge inside the ±1.0 hold-out bar *by
    construction*. The remaining-pool reading is stationary on the same corpus
    (2.54 vs 2.47), so it is the one that can actually falsify a noise model,
    which is the whole point of the amendment.

    Picks of players outside ``pool_order`` are skipped; the ranking and the
    sequence are then restricted to the same sub-universe, which leaves ``d``
    self-consistent.
    """
    available = list(pool_order)
    index = {pid: i for i, pid in enumerate(available)}
    out: list[int] = []
    for pid in drafted_ids:
        pid = str(pid)
        if pid not in index:
            continue
        position = available.index(pid)
        out.append(position)
        available.pop(position)
        index = {p: i for i, p in enumerate(available)}
    return out


def simulate_reaches(pool_rows: Sequence[Mapping[str, Any]],
                     owners_by_pick: Sequence[str],
                     personas: Mapping[str, str],
                     viable_by_owner: Mapping[str, Mapping[str, int]],
                     targets: Mapping[str, tuple[int, int]],
                     *, bpa_prob: float, reach_decay: float, max_reach: float,
                     seed: int) -> list[int]:
    """One seeded replay of a recorded draft through the SHIPPED
    :func:`cpu_pick`, returning the simulated reach series.

    Same observable as :func:`reach_series`, same pool, same turn order — the
    only thing that changes is who chooses. That is what makes the two
    distributions comparable.
    """
    rng_root = random.Random(seed)
    available = list(pool_rows)             # read-only: never mutated in place
    viable = {o: dict(v) for o, v in viable_by_owner.items()}
    window = candidate_window(max_reach)
    out: list[int] = []
    for pick_no, owner in enumerate(owners_by_pick, start=1):
        if not available:
            break
        owner = str(owner)
        needs = {pos: severity(viable.get(owner, {}), targets, pos)
                 for pos in _POSITIONS}
        rng = random.Random(rng_root.randrange(2 ** 31) * 10_007 + pick_no)
        head = available[:window]
        chosen = cpu_pick(head, personas.get(owner, DEFAULT_OUTLOOK),
                          needs, rng, max_reach=max_reach, bpa_prob=bpa_prob,
                          reach_decay=reach_decay)
        # The pick is always inside the window, so the scan is O(K), not O(n).
        position = next(i for i, r in enumerate(head)
                        if str(r["player_id"]) == chosen)
        out.append(position)
        pos = str(available[position].get("position") or "").upper()
        if owner in viable and pos in viable[owner]:
            viable[owner][pos] += 1
        available.pop(position)
    return out
