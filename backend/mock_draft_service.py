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
the same gate unchanged; W2c left the model and the gate FROZEN and re-derived
the calibration CONSENSUS instead; W2d took the operator's pre-registered
decision to re-balance the fit/hold-out SPLIT for draft depth and to add a
third validation corpus, with the model still frozen; W2e took the operator's
PRODUCT decision on how deep and how often a bot may reach and replaced the
single global cap with the round-tiered policy below, **without re-fitting or
re-gating**. The last recorded verdict is **STILL A FAILURE**, but the ship
decision no longer follows from it: :data:`CPU_MODEL_VALIDATED` was flipped
True by operator override once W2e made the reach policy a product rule, so
:func:`advance_cpu` **is** reachable from the routes and `draft.mock` is ON.
``test_w2_16_calibration_gate`` pins the statistical verdict independently, so
a change that makes the model pass turns the suite red and forces a deliberate
artifact re-publish rather than a silent one. The engine, its tests and the
harness that produced the verdict all ship so the verdict is reproducible and
the next attempt can be re-gated without a rebuild.

**INV-10 — deterministic and self-contained.** Same ``rng_seed`` ⇒ a
byte-identical draft; zero platform egress after creation (this module
imports no HTTP client and performs no I/O of any kind at runtime). The one
qualifier (#323): :func:`state_payload` labels picks through
:meth:`ranking_service.RankingService.tier_for_elo` — a pure classmethod
over the checked-in ``tier_config.json``, which ``ranking_service`` loads
once at module import (a module the server already imports at boot). The
per-pick band walk is in-memory; nothing here gains I/O or egress.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from . import draft_board_service as dbs
# #323 — the ONE canonical tier walk (stdlib-only module, config read at
# import; INV-10 note above). Never wire `board_elo` into it: a pick's tier
# is consensus-denominated, stable across basis toggles (PRD §2).
from .ranking_service import RankingService

SCHEMA = 1

# ── Closed vocabularies (mirrors of the I-6 board vocabulary) ─────────────
STATUS_ACTIVE = "active"
STATUS_COMPLETE = "complete"
STATUS_ABANDONED = "abandoned"

TYPE_LINEAR = "linear"
TYPE_SNAKE = "snake"

ORDER_SOURCE_ASSIGNED = "assigned"
ORDER_SOURCE_RANDOMIZED = "randomized"

#: #328 — provenance of the traded-pick ownership overlay, snapshotted into
#: ``settings`` at create like everything else. Closed server-side; clients
#: type it open + nullable (``null`` = a row persisted before the label
#: existed — *unknown*, never "none").
OWNERSHIP_SOURCE_PLATFORM = "platform"   # platform-stated ownership (Sleeper board / MFL store), covering every slot of this mock
OWNERSHIP_SOURCE_USER = "user"           # the ESPN manual assignment grid (user-asserted), covering every slot of this mock
OWNERSHIP_SOURCE_PARTIAL = "partial"     # ownership data applied, but NOT covering every slot (rounds beyond grid/store depth, contested/orphaned exclusions, identity-dropped rows); uncovered slots use slot order
OWNERSHIP_SOURCE_NONE = "none"           # no ownership data applied; every team drafts its own slot

BY_USER = "user"
BY_CPU = "cpu"

#: #305 — the two draft modes. A create-time-immutable ``settings`` key (no
#: schema change; the blob absorbs it). The ONE engine lever is ``next_pick``
#: (INV-7): in manual mode every owned slot is ``is_user``.
MODE_CPU = "cpu"
MODE_MANUAL = "manual"

PERSONA_DECLARED = "declared"
PERSONA_INFERRED = "inferred"
PERSONA_DEFAULT = "default"
DEFAULT_OUTLOOK = "not_sure"

#: Reason strings on the typed-empty ``200 {"empty": true}`` contract that
#: ``GET/POST /api/mock-draft`` share with M2. New states ride this field
#: rather than a new member of any closed client enum (plan D10).
REASON_CLASS_NOT_LOADED = "class_not_loaded"
REASON_CPU_MODEL_UNVALIDATED = "cpu_model_unvalidated"
REASON_NO_ACTIVE_MOCK = "no_active_mock"
#: W2d/G-extra. ``teams`` was ``len(owners)`` with no floor, so a 2-team league
#: got a 2-team "mock" whose every round is a coin flip between two rosters.
REASON_LEAGUE_TOO_SMALL = "league_too_small"
#: #295/#296/#305 — the session user could not be placed in the resolved
#: draft. Fourth and LAST ladder rung (least actionable); also the code of the
#: :class:`UserNotInDraft` raise from :func:`build_settings`, which the create
#: route maps to the byte-identical typed-empty, so a born-broken mock can be
#: refused but never persisted (INV-6) and clients see one vocabulary.
REASON_USER_NOT_IN_DRAFT = "user_not_in_draft"

#: The smallest league a mock says anything about. Below this the CPU field is
#: too thin for a reach to mean anything — with 3 opponents the pool barely
#: moves between your picks, so the exercise stops being a draft simulation.
MOCK_MIN_TEAMS = 4

# ── Tunables (``model_config``; see docs/config-reference.md) ─────────────
#: Product cap on how many consensus slots a *need* can pull a player up. NOT
#: a fitted parameter — fitting it alongside the noise is unidentifiable at
#: n = 23 (lld §4.2.3 step 2).
#:
#: **W2e narrowed its role.** It scales the NEED term and nothing else. It is no
#: longer any part of the support bound on a reach — that is the round-tiered
#: :func:`round_reach_cap` — and the round cap dominates it, since the need term
#: is scored over the already-truncated candidate set.
MOCK_MAX_REACH_DEFAULT = 3.0

#: THE two fitted parameters of the W2b mixture (see :func:`cpu_pick`).
#: ``mock_bpa_prob`` = P(this pick is the strict board pick, no idiosyncrasy).
#: ``mock_reach_decay`` = the per-slot survival ratio of the reach branch:
#: reaching one slot further is ``decay`` times as likely. The values below are
#: the **W2d** fit on ``lakeview-complete``'s interleaved FIT block (W2c, on the
#: same corrected snapshot but the round-based split, was 0.20 / 0.70; W2b, on
#: the trimmed snapshot, 0.50 / 0.95) — recorded, but NOT validated: see
#: :data:`CPU_MODEL_VALIDATED`.
#:
#: **W2e did NOT re-fit them.** W2e installed the operator's round-tiered reach
#: policy below and stopped there, deliberately: re-fitting and re-gating is a
#: separate, later decision. So these two remain the values fitted under the OLD
#: global support bound, and a re-fit is owed before they mean anything. Nothing
#: ships on them meanwhile — :data:`CPU_MODEL_VALIDATED` is ``False`` and the
#: routes refuse to generate CPU picks at all.
MOCK_BPA_PROB_DEFAULT = 0.10
MOCK_REACH_DECAY_DEFAULT = 0.70

_DEFAULT_CFG: dict[str, float] = {
    "mock_max_reach_slots": MOCK_MAX_REACH_DEFAULT,
    "mock_bpa_prob": MOCK_BPA_PROB_DEFAULT,
    "mock_reach_decay": MOCK_REACH_DECAY_DEFAULT,
}

# ── THE ROUND-TIERED REACH POLICY (W2e) ──────────────────────────────────
# The operator's product rule, verbatim:
#
#   "For the first round, I expect no more than reaching 3 picks (and no more
#    than 3 times a round). For the second round 5 picks (and only 2 times a
#    round). For the third and fourth 15 picks (limit of 5 times a round)."
#
# This is PRODUCT POLICY — "how deep, and how often, may a bot deviate from the
# board before it reads as broken" — decided on its own terms by the operator
# and only THEN re-gated (artifact 08d §8 option A). It is deliberately not a
# fitted parameter and deliberately not a ``model_config`` row: a support bound
# an operator could retune from the DB would silently invalidate the calibration
# verdict the gate records. Changing either table is a product decision that
# requires a re-gate. Documented in ``docs/config-reference.md``.
#
# W2e semantics, stated once (artifact 08e §2 argues each one):
#  * A **reach** is a pick whose 0-based position in the remaining consensus
#    pool is >= 1 — i.e. the pick passed over at least one better-valued
#    available player. A pick at best-player-available is never a reach.
#  * The **cap** truncates the candidate set for that round, so the reach
#    branch is a geometric law truncated at the round's cap rather than at the
#    old global window. A CPU can NEVER reach further than its round's cap.
#  * The **budget** is per round and shared across every CPU team in the league
#    (not per team). Once a round has spent it, every remaining CPU pick in that
#    round is strict best-available — the need term included, because "strict
#    best available" is what the rule says. It is consumed in pick order, so it
#    is a pure function of the seeded RNG and replay stays exact.
#  * The USER's picks neither consume the budget nor are constrained by it: the
#    policy describes how the bots draft, and a human reaching in round 1 should
#    not force the field to BPA for the rest of it.

#: Round -> the deepest a CPU may reach in that round, in consensus slots.
MOCK_REACH_CAP_BY_ROUND: dict[int, int] = {1: 3, 2: 5}
#: Rounds 3, 4 and every later round.
MOCK_REACH_CAP_LATE = 15

#: Round -> how many reaching picks that round allows, LEAGUE-WIDE.
MOCK_REACH_BUDGET_BY_ROUND: dict[int, int] = {1: 3, 2: 2}
#: Rounds 3, 4 and every later round.
MOCK_REACH_BUDGET_LATE = 5


def round_reach_cap(round_no: int) -> int:
    """The deepest reach allowed in ``round_no`` (product policy, W2e)."""
    return MOCK_REACH_CAP_BY_ROUND.get(int(round_no), MOCK_REACH_CAP_LATE)


def round_reach_budget(round_no: int) -> int:
    """How many reaching picks ``round_no`` allows, league-wide (W2e)."""
    return MOCK_REACH_BUDGET_BY_ROUND.get(int(round_no), MOCK_REACH_BUDGET_LATE)


#: Candidate window ``K`` — a PERFORMANCE bound, and nothing else since W2e.
#:
#: It is the width of the head of the pool :func:`cpu_pick` scans, so the scan
#: is O(K) rather than O(pool). Until W2e it was ALSO the support bound on a
#: reach, and W2d's finding was that at ``K = 12`` it was the BINDING one: every
#: simulated ``d`` was bounded at 11.5 while 7 of 102 validation picks reached
#: 13 to 51.5 slots, probability exactly zero. W2e replaces it in that role with
#: the round-tiered cap above, which is a stated product rule rather than a
#: constant nobody chose deliberately.
#:
#: It is therefore set WIDE ENOUGH THAT IT NEVER BINDS: the deepest round cap is
#: :data:`MOCK_REACH_CAP_LATE` = 15, which needs 16 candidates, and 24 leaves 8
#: slots of headroom so the round tier is always the constraint that bites.
#: Pinned by ``test_w2_04b_the_candidate_window_is_never_the_binding_constraint``,
#: which asserts the slack at EVERY round the engine can draft.
MOCK_CANDIDATE_WINDOW = 24

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
# `docs/plans/draft-extensions/mock-calibration-2026-08d.md` is a GATE, not a
# report (plan §5, lld §4.2.3).
#
# W2a: the specified single-parameter model — argmin over
# `rank - need_bonus - Uniform(0, jitter)` — failed all FOUR bars. The failure
# was a model-FORM failure: its reachable support is bounded by roughly
# `max_reach + jitter` slots while 21 % of real picks reach 6-9.
#
# W2b: re-specced to the two-parameter mixture in `cpu_pick` and re-ran the
# SAME gate, unchanged. Three of four bars passed; `mfl-complete`'s paired-mean
# bar failed, and the recorded cause was the CONSENSUS SNAPSHOT — a trimmed
# fixture whose deep tail was floored at repeated DP values, so `d` there was
# measuring a `search_rank` tiebreak rather than a reach.
#
# W2c: the model, both bars, alpha, the split and the corpora were all
# UNCHANGED; what changed was the snapshot the observable is measured against —
# the full 2026 prospect class priced by the live, KTC-blended DynastyProcess
# snapshot through the shipped blend — plus an explicit average-rank rule for
# the ties that remain (`_block_rank`). Verdict: still FAILED, on BOTH
# paired-mean bars while both KS bars passed, and the recorded cause was the
# SPLIT: the observable drifted 2.017 slots between the fit block (rounds 1-2)
# and the hold-out (rounds 3-4) before any model, because `d` is a rank
# distance over a value curve that flattens in the tail.
#
# W2d (this file): the operator's decision, PRE-REGISTERED in build-w2d.md §1
# and committed before the harness moved. Two changes, both to the gate and
# both recorded in advance: (1) the split is now an alternating INTERLEAVE over
# the retained picks, so the fit and hold-out blocks see the same draft depth
# (23.61 vs 23.64 mean pick position, against 12.17 vs 35.59 before) — pinned
# as a precondition by T-W2-19 so it can never silently re-skew; (2) the corpus
# `mfl-partial` joins as a THIRD independent validation block with both bars and
# no refit, taking the gate from four bars to six. The model family, both bars,
# alpha, the +/-1.0 constant, the tie rule and `d_i` are FROZEN; only the two
# parameters were re-fitted.
#
# Verdict: still FAILED. All THREE KS bars pass (p = 0.317 / 0.546 / 0.108);
# all three paired-mean bars fail (1.648 / 3.605 / 2.026). The re-balance did
# what it was meant to — the depth drift is gone and the observable's residual
# 1.44-slot block difference is ~1.1 SE of sampling noise — and it exposed the
# next layer: `MOCK_CANDIDATE_WINDOW` bounded every simulated `d` at 11.5, while
# 7 of the 102 validation picks reached 13 to 51.5 slots. Those out-of-support
# picks carried 1.34 / 4.04 / 1.24 slots of the three blocks' observed means,
# i.e. they WERE the gap. `K` is a PRODUCT CAP and deliberately not fitted, so
# W2d did not touch it and asked the operator to decide it.
#
# W2e (this file): the operator decided `K` on product grounds, as artifact 08d
# §8 option A asked. The single global cap is REPLACED as the support bound by
# the ROUND-TIERED REACH POLICY above — reach at most 3 / 5 / 15 slots in rounds
# 1 / 2 / 3+, at most 3 / 2 / 5 times per round league-wide — and
# `MOCK_CANDIDATE_WINDOW` is demoted to a pure performance bound, widened 12 ->
# 24 so it never binds the distribution at any round.
#
# **W2e installed the policy and STOPPED THERE, deliberately.** It did NOT
# re-fit the two parameters and did NOT re-run the gate; that is a separate,
# later decision (build-w2e.md §1). Two consequences to hold in mind:
#
#   * 08d's verdict TABLE still records the last run of the gate, but its §6
#     diagnosis — "the residual is the candidate window's support bound" — is
#     the finding W2e's policy ACTS ON, so the numbers beside it are no longer
#     reproducible against this engine. A re-gate is owed before any of them
#     is quoted again.
#   * `MOCK_BPA_PROB_DEFAULT` / `MOCK_REACH_DECAY_DEFAULT` were fitted under the
#     OLD support and are left untouched for the same reason.
#
# Neither matters for what ships: the verdict is still FAILED, so this stays
# False and the routes still refuse.
#
# ── OPERATOR OVERRIDE, 2026-08-06 ────────────────────────────────────────────
# Flipped True by explicit operator instruction ("Flip the mock draft build
# on"), NOT by the statistical gate passing. Both facts are true and must stay
# visible together:
#
#   * The six-bar gate in `mock-calibration-2026-08d.md` FAILED its paired-mean
#     bars (all three KS bars passed). The measurements are unchanged and the
#     artifact is not re-published — nothing was fitted to make this flip.
#   * The operator subsequently specified CPU reach behaviour directly as a
#     product rule (W2e: per-round reach caps + per-round frequency budget,
#     R1 3/3 · R2 5/2 · R3+ 15/5) and declined further validation. That rule,
#     not the mean bar, is now the accepted definition of "bots draft
#     plausibly".
#
# So this constant no longer means "the model matched the corpora". It means
# "the operator accepted the shipped reach policy". `test_w2_16_calibration_gate`
# still records the statistical verdict independently — see its docstring.
# Revert by setting this back to False; nothing else needs to change.
CPU_MODEL_VALIDATED = True
CALIBRATION_ARTIFACT = "docs/plans/draft-extensions/mock-calibration-2026-08d.md"


class MockDraftError(Exception):
    """Base for the engine's typed refusals."""

    code = "mock_draft_error"


class NotYourTurn(MockDraftError):
    code = "not_your_turn"


class PlayerUnavailable(MockDraftError):
    code = "player_unavailable"


class UserNotInDraft(MockDraftError):
    """#295/#296/#305 — the resolved order does not contain the user.

    Raised by :func:`build_settings` before any slot table or persisted row
    exists: at this depth a missing user signals a contract violation between
    the resolution layer and the engine (an assigned platform order can omit a
    user who IS in ``owners`` — e.g. a co-owner id), not a league condition.
    The create route maps it to ``empty_payload(REASON_USER_NOT_IN_DRAFT)``,
    byte-identical to the refusal ladder's rung.
    """

    code = REASON_USER_NOT_IN_DRAFT


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


def start_refusal(ctx: MockContext, owners: Sequence[str],
                  *, user_owner_id: str | None = None) -> str | None:
    """The reason a mock cannot start right now, or ``None`` — **interface G2**.

    ONE ordering of the refusals, so the capability probe a client renders a
    disabled button from and the create route it eventually POSTs to can never
    disagree. The order is the SHIPPED route's, preserved deliberately:
    ``class_not_loaded`` outranks ``cpu_model_unvalidated`` because it is the
    transient, seasonal, self-resolving state and is the more useful thing to
    say when both hold. The last two rungs are the least actionable, in that
    order: ``league_too_small``, then ``user_not_in_draft`` (#295/#296/#305).

    ``user_owner_id`` is keyword-only and ``None``-defaulted: ``None`` means a
    legacy positional caller and SKIPS the fourth rung, so every existing call
    site answers the old ladder byte-identically. The empty string is NOT
    ``None`` — a session with ``user_id == ""`` refuses (the phantom-owner
    tripwire, T-295-09). The rung is mode-blind.
    """
    if not class_loaded(ctx):
        return REASON_CLASS_NOT_LOADED
    if not CPU_MODEL_VALIDATED:
        return REASON_CPU_MODEL_UNVALIDATED
    if len({str(o) for o in owners or ()}) < MOCK_MIN_TEAMS:
        return REASON_LEAGUE_TOO_SMALL
    if (user_owner_id is not None
            and str(user_owner_id) not in {str(o) for o in owners or ()}):
        return REASON_USER_NOT_IN_DRAFT
    return None


def capability(ctx: MockContext, owners: Sequence[str],
               *, draft_type: str | None = None,
               order_source: str | None = None,
               user_owner_id: str | None = None) -> dict:
    """**Interface G2** — what a client needs to render the mock entry point
    WITHOUT POSTing a create first.

    Before this, ``cpu_model_unvalidated`` and ``class_not_loaded`` were only
    discoverable by starting a mock and reading the typed-empty back, so the
    only honest UI was an enabled button that failed. This rides
    ``GET /api/mock-draft`` — no new route, no new closed enum: ``reason``
    carries the same strings the typed-empty already uses.

    ``draft_type`` / ``order_source`` are what the create route WOULD resolve
    from the league's real draft, so a setup sheet can prefill its
    linear/snake toggle and disclose a randomized order before the user
    commits — the same disclosure the created mock echoes back.
    """
    reason = start_refusal(ctx, owners, user_owner_id=user_owner_id)
    return {
        "can_start": reason is None,
        "reason": reason,
        "teams": len({str(o) for o in owners or ()}),
        "min_teams": MOCK_MIN_TEAMS,
        "rounds_default": DEFAULT_ROUNDS,
        "rounds_max": _ROOKIE_MAX_ROUNDS,
        "type": draft_type if draft_type in (TYPE_LINEAR, TYPE_SNAKE) else None,
        "order_source": (order_source
                         if order_source in (ORDER_SOURCE_ASSIGNED,
                                             ORDER_SOURCE_RANDOMIZED) else None),
    }


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


# ── The run (#290) ────────────────────────────────────────────────────────
#
# A "run" is an engine-internal cluster of candidates the consensus prices as
# effectively interchangeable. It is NOT the 8-tier ladder and never touches
# `tier_config.json` or the cross-client tier enum — see
# `docs/cross-client-invariants.md`'s quarantine paragraph and #279.

#: How many times the LOCAL median gap a value drop must be before it counts as
#: a run boundary. Dimensionless on purpose (D-9): an absolute Elo threshold
#: behaves differently at the head of the board than in the tail, which is the
#: flattening this module already records at :231.
#:
#: 2.5 is not a taste call. On the pinned 2026 consensus board it yields a
#: MEDIAN RUN OF 5 players on BOTH scoring formats — the operator's "tight
#: groups of 4-5" as an emergent property of the value curve rather than an
#: imposed clamp. At 2.0 the first run collapses to a single player and round 1
#: is forced. Measurements: docs/feedback/items/290-mock-draft-engine/status.md
MOCK_RUN_GAP_MULTIPLE = 2.5

#: Width, in GAPS, of the window the median is taken over. Odd so the window is
#: symmetric about the gap under test where it can be.
MOCK_RUN_MEDIAN_WINDOW = 9

#: Rounds 3+ may cross this many run boundaries (D-6's "softer penalty in
#: rounds 3+"). Rounds 1-2 cross none — a hard wall. Expressed in the same
#: units as the thing it softens (candidate-set width), so `cpu_pick`'s scoring
#: function stays byte-identical and the Gumbel-max identity survives.
MOCK_RUN_CROSS_ALLOWANCE_LATE = 1

#: The FLOOR on :func:`run_offset`'s return, in candidate slots.
#:
#: Load-bearing, and the reason is a measured near-miss. A boundary at index 0
#: means "the head is alone in its run", which without this floor truncates the
#: candidate set to a single row and makes the pick deterministic. On `sf_tep`
#: the top of the 2026 board is exactly that shape, so `MOCK_RUN_MIN_OFFSET = 0`
#: forces pick 1.01 in 100% of superflex mocks and collapses round-1 variety —
#: a parameter that looked fine on `1qb_ppr` and was catastrophic on the other
#: board. At 1 the head always has at least one rival, so a wall can tighten the
#: field to a pair but can never remove the draw. Pinned by T-290-14, which is
#: seedless and structural precisely so it cannot be tuned away by a lucky seed.
MOCK_RUN_MIN_OFFSET = 1

#: The share of today's reach rate a bot with ZERO positional need keeps (D-5:
#: "need DOMINATES reaching, but idiosyncrasy survives"). At 0.25 and the fitted
#: `mock_bpa_prob = 0.10`, a satisfied roster reaches 22.5% of the time against
#: a desperate roster's unchanged 90%. Zero here would make most August bots
#: pure BPA and the board chalky, which D-5 explicitly rejects.
MOCK_IDIOSYNCRASY_FLOOR = 0.25


def run_boundaries(candidates_ranked: Sequence[Mapping[str, Any]],
                   *,
                   multiple: float = MOCK_RUN_GAP_MULTIPLE,
                   window: int = MOCK_RUN_MEDIAN_WINDOW) -> list[int]:
    """Indices ``i`` such that a run boundary sits between rows ``i``/``i+1``.

    The raw gap rule, with **no** :data:`MOCK_RUN_MIN_OFFSET` floor applied —
    that floor is a safety device on the CANDIDATE SET, not part of the
    partition. Keeping the two separable is what lets R-2's "median run of 4-5"
    be measured against the rule the operator asked for rather than against the
    floor, which would report every singleton run as a pair.

    A single forward walk; no ``sorted``, no ``.sort`` (amendment 1).
    """
    n = len(candidates_ranked)
    if n <= 1:
        return []

    # Two parallel lists over the n-1 adjacent pairs. `frontier` marks the
    # valued -> unvalued edge, which is a boundary regardless of magnitude
    # because there is no gap to measure across it.
    gaps: list[float | None] = []
    frontier: list[bool] = []
    for i in range(n - 1):
        a = candidates_ranked[i].get("value")
        b = candidates_ranked[i + 1].get("value")
        if a is None:
            # Inside the unvalued block: the consensus holds no opinion, so
            # there is nothing to wall off (`reach_report`, :1181-1191).
            gaps.append(None)
            frontier.append(False)
        elif b is None:
            gaps.append(None)
            frontier.append(True)
        else:
            # The pool is value-descending, so a negative gap is impossible;
            # the clamp keeps a future reordering from poisoning the median.
            gaps.append(max(0.0, float(a) - float(b)))
            frontier.append(False)

    out: list[int] = []
    for i, g in enumerate(gaps):
        if g is None:
            if frontier[i]:
                out.append(i)
            continue
        lo = max(0, i - window // 2)
        hi = min(len(gaps), lo + window)
        lo = max(0, hi - window)          # re-clip so the window keeps its
                                          # full width near the list's end
        win = [x for x in gaps[lo:hi] if x is not None]
        med = statistics.median(win) if win else 0.0
        # `med > 0.0` excludes a flat block: an exact tie carries no opinion,
        # so a consensus-tied run is never cut into singletons.
        if med > 0.0 and g >= float(multiple) * med:
            out.append(i)
    return out


def run_offset(candidates_ranked: Sequence[Mapping[str, Any]],
               *,
               allow_cross: int = 0,
               multiple: float = MOCK_RUN_GAP_MULTIPLE,
               window: int = MOCK_RUN_MEDIAN_WINDOW) -> int:
    """The 0-based distance from the head of ``candidates_ranked`` to the last
    row a CPU may consider without passing more than ``allow_cross`` run
    boundaries.

    Pure. No RNG, no I/O, no ordering — a single forward walk over the list
    ``_undrafted`` already produced, modelled on :func:`_block_rank` (:1127),
    which is why amendment 1's no-``sorted`` rule needs no waiver here.

    Returns a value in ``[0, len(candidates_ranked) - 1]``, floored at
    :data:`MOCK_RUN_MIN_OFFSET` wherever the list is wide enough to allow it,
    and suitable to pass straight into ``min()`` against :func:`round_reach_cap`.

    A boundary sits between rows ``i`` and ``i+1`` when the value drop there is
    at least ``multiple`` times the MEDIAN gap in a ``window``-wide local
    neighbourhood. Adaptive rather than a fixed Elo threshold (D-9): the same
    absolute drop means something different at the head of the board than in
    the tail.
    """
    n = len(candidates_ranked)
    if n <= 1:
        return 0

    limit = n - 1
    crossed = 0
    for i in run_boundaries(candidates_ranked, multiple=multiple, window=window):
        if crossed >= int(allow_cross):
            limit = i
            break
        crossed += 1

    # The floor is applied LAST and clamped to the list, so it can widen a
    # single-candidate wall to a pair but can never point past the end.
    return max(0, min(n - 1, max(int(MOCK_RUN_MIN_OFFSET), limit)))


def need_pressure(severities: Mapping[str, float],
                  targets: Mapping[str, tuple[int, int]]) -> float:
    """How much of this team's STARTING+BENCH need is unfilled, in ``[0, 1]``.

    The denominator-weighted share of unmet slots:

        sum_p severity[p] * (S_p + B_p)  /  sum_p (S_p + B_p)

    **Why not ``max(severities.values())``.** :func:`slot_targets` gives TE
    ``(S, B) = (1, 0)`` on a standard lineup, so a team with no 1280+ TE scores
    ``severity["TE"] == 1.0`` and ``max`` returns 1.0 — which makes
    :func:`effective_bpa_prob` return ``bpa_prob``, i.e. TODAY'S BEHAVIOUR, for
    the large majority of real rosters. Measured on a roster full at QB/RB/WR
    with no viable TE: ``max`` = 1.000 (P(reach) 0.900, unchanged), ``mean`` =
    0.250, denominator-weighted = **0.111** (P(reach) 0.300).

    **Why not ``mean``.** A team missing its whole WR corps and a team missing
    one TE both score 0.25 under ``mean``. Denominator weighting scores them
    0.44 and 0.11, which is the honest ordering.

    Pure; consumes no RNG.
    """
    den = sum(sum(targets.get(p, (0, 0))) for p in _POSITIONS)
    if den <= 0:
        return 0.0
    num = sum(float(severities.get(p, 0.0)) * sum(targets.get(p, (0, 0)))
              for p in _POSITIONS)
    return max(0.0, min(1.0, num / den))


def effective_bpa_prob(bpa_prob: float,
                       needs_for_team: Mapping[str, float],
                       pressure: float | None = None) -> float:
    """P(this pick is the strict board pick), tilted by how needy the team is.

    ``bpa_prob`` is the FITTED mixture weight and stays the value at MAXIMAL
    need: a team with a desperate hole reaches exactly as often as the fit says.
    As need falls the reach branch is damped toward — but never to —
    best-available, which is D-5's ruling ("need DOMINATES reaching, but
    idiosyncrasy survives"):

        tilt          = floor + (1 - floor) * pressure
        bpa_effective = 1 - (1 - bpa_prob) * tilt

    pressure == 1 -> bpa_effective == bpa_prob      (today's behaviour)
    pressure == 0 -> bpa_effective == 1 - (1 - bpa_prob) * floor

    Pure; consumes no RNG. It changes the mixture WEIGHT and nothing about the
    noise FAMILY, so the Gumbel-max identity and the geometric reach law hold
    unchanged conditional on reaching (T-W2-04b).

    ``pressure`` is optional in the signature and MANDATORY in production. The
    default exists so the shipped single-position unit tests keep working
    unchanged — on a uniform board ``max`` and the weighted share coincide.
    Both engine call sites pass it from :func:`need_pressure`, and T-290-16
    asserts by AST that they do.
    """
    if pressure is None:
        # Callers that hold no lineup template (the existing unit tests) fall
        # back to the worst single hole. Production callers ALWAYS pass
        # `pressure` from `need_pressure`.
        values = [float(v) for v in (needs_for_team or {}).values()]
        pressure = max(values) if values else 0.0
    sev = max(0.0, min(1.0, float(pressure)))
    tilt = MOCK_IDIOSYNCRASY_FLOOR + (1.0 - MOCK_IDIOSYNCRASY_FLOOR) * sev
    return 1.0 - (1.0 - float(bpa_prob)) * tilt


def cpu_pick(candidates_ranked: Sequence[Mapping[str, Any]],
             persona_outlook: str | None,
             needs_for_team: Mapping[str, float],
             rng: random.Random,
             *,
             max_reach: float = MOCK_MAX_REACH_DEFAULT,
             bpa_prob: float = MOCK_BPA_PROB_DEFAULT,
             reach_decay: float = MOCK_REACH_DECAY_DEFAULT,
             reach_cap: int | None = None,
             need_pressure_value: float | None = None) -> str:
    """One CPU pick — ``argmin(rank - need_bonus - reach_noise)``.

    ``candidates_ranked`` is the head of the consensus pool, 1-based by list
    position. ``needs_for_team`` is ``{pos: severity}``. Ties resolve to the
    better consensus rank because the scan keeps the first strict minimum.

    **The need term** is unchanged from W2a and is not part of the noise model:
    ``need_bonus <= need_weight * 1.0 * max_reach``, so a championship team with
    a desperate need reaches at most ``max_reach`` slots and a `jets` team takes
    the board pick. One scoring function, persona = parameters.

    **Need is also conditional on the mixture WEIGHT since #290 (D-5).**
    ``bpa_prob`` is now the value at MAXIMAL need — a desperate roster reaches
    exactly as often as the fit says — and :func:`effective_bpa_prob` damps the
    reach branch toward best-available as need falls, never to it.
    ``need_pressure_value`` is the denominator-weighted share of unfilled slots
    from :func:`need_pressure`; a caller that omits it falls back to the worst
    single hole, which is the same number on the single-position boards the
    noise-law tests use. The scoring loop below is byte-identical either way:
    only the Bernoulli's threshold moves.

    **The per-position severity term is untouched.** ``need_pressure``
    aggregates only for the mixture weight — how *often* a bot reaches. The
    ``bonus = weight * severity[pos] * max_reach`` term below, which decides
    *what* it reaches for, still reads the raw per-position severity.

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

    The two parameters are ``bpa_prob`` and ``reach_decay``. **``reach_cap``
    (W2e) truncates the geometric tail** and is deliberately NOT fitted: it is
    the caller's round-tiered product cap (:func:`round_reach_cap`), passed in
    per pick because it depends on the round. ``reach_cap=0`` collapses the
    candidate set to the board pick, which is how the round's spent frequency
    budget expresses "strict best available" — the need term included, since it
    too is scored over the truncated set. ``None`` leaves the scan untruncated,
    which is what the unit tests of the noise law itself use.
    """
    if not candidates_ranked:
        raise PlayerUnavailable("no candidates")
    if reach_cap is not None:
        candidates_ranked = candidates_ranked[:max(0, int(reach_cap)) + 1]
    weight = need_weight(persona_outlook)
    scale = _decay_to_scale(reach_decay)
    # D-5 — the mixture weight is need-conditional. `bpa_prob` keeps its name,
    # its default and its meaning in the signature; it is now the value at
    # MAXIMAL need, and a satisfied roster is damped toward best-available.
    # Consumes no RNG, and is evaluated BEFORE the draw, so the Bernoulli stays
    # the first draw of the pick and INV-10 holds.
    bpa_eff = effective_bpa_prob(bpa_prob, needs_for_team, need_pressure_value)
    # ONE Bernoulli per pick, drawn first so the branch (and therefore the
    # whole stream) is a pure function of the seed.
    reaching = scale > 0.0 and rng.random() >= float(bpa_eff)
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
    """``K`` — the scan width. A PERFORMANCE bound only since W2e.

    :data:`MOCK_CANDIDATE_WINDOW`, floored so the *need* term can always reach
    its own ``max_reach`` cap even if the window is retuned downwards. The
    binding cap on a reach is :func:`round_reach_cap`, not this.
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
                   ownership_source: str = OWNERSHIP_SOURCE_NONE,
                   mode: str = MODE_CPU,
                   ownership: Mapping[Any, str] | None = None,
                   traded_slots: Mapping[Any, str] | None = None,
                   personas: Mapping[str, Mapping[str, str]] | None = None,
                   rng: random.Random | None = None,
                   config_overrides: Mapping[str, float] | None = None,
                   ) -> dict:
    """The ``settings`` JSON for a new mock (lld §3.3).

    ``order`` absent ⇒ a seeded shuffle labelled ``order_source:"randomized"``
    — never an invented "real" order (KD-6). ``rounds`` is clamped to
    ``1..ROOKIE_MAX_ROUNDS``. The fitted noise parameters are snapshotted so a
    resumed mock replays identically even if ``model_config`` is retuned.

    **Two ways to state traded picks (W2d/G1), because the two callers hold
    different keys.** ``ownership`` is the persisted shape — ``{pick_no:
    user_id}`` — and is what a test or a replayed row supplies. ``traded_slots``
    is the PLATFORM shape — ``{(round, slot): user_id}`` — because that is all
    Sleeper's ``traded_picks`` export and MFL's grid actually state; the overall
    pick number depends on this mock's own ``rounds``/``teams``/``type``, which
    only this function knows. ``traded_slots`` is translated through the slot
    table built just above, and an explicit ``ownership`` entry wins over it.

    **Three #295/#296/#305 rules (INV-4/INV-6):**

    * ``teams == len(resolved_order)`` — ``owners`` never sizes the draft; its
      residual roles are the shuffle pool, the persona keying and the refusal
      ladder's count.
    * An explicit ``order`` shorter than ``MOCK_MIN_TEAMS`` is *not an order*:
      fall back to the seeded shuffle of ``owners``, label it ``randomized``,
      and drop ``traded_slots`` with it.
    * :class:`UserNotInDraft` is raised when the resolved order lacks
      ``user_owner_id`` — before any slot table or persisted row exists.

    **Fail-soft roster contract:** an order entry absent from ``ctx.rosters``
    simply has no pre-draft roster to exclude and no severity input — its CPU
    picks come from the shared pool with flat needs. That is the contract, not
    a bug: the session cannot supply a roster for a member it does not know.
    Every such entry still gets a persona row (the ``owners ∪ resolved_order``
    union below), so ``settings`` stays the complete record of the mock.
    """
    owners = [str(o) for o in owners]
    rounds = int(rounds or DEFAULT_ROUNDS)
    rounds = max(1, min(_ROOKIE_MAX_ROUNDS, rounds))
    draft_type = draft_type if draft_type in (TYPE_LINEAR, TYPE_SNAKE) else TYPE_LINEAR

    if order is not None and len(order) < MOCK_MIN_TEAMS:
        # §14-2: a degenerate platform order below the mock's own floor is not
        # an order (server precedent: "a partial slot map is not an order").
        # Fall back to the labelled shuffle, and drop the overlay with it: a
        # traded pick is meaningless without the slots it trades between.
        # #328 — the label degrades at the SAME point the overlay is dropped
        # (the honest-fallback rule); no other degrade point exists in the
        # engine, all others live in the server resolvers.
        order = None
        traded_slots = None
        ownership_source = OWNERSHIP_SOURCE_NONE

    if order:
        resolved_order = [str(o) for o in order]
        resolved_source = order_source
    else:
        resolved_order = list(owners)
        (rng or random.Random(0)).shuffle(resolved_order)
        resolved_source = ORDER_SOURCE_RANDOMIZED

    teams = len(resolved_order)                                  # INV-4
    if str(user_owner_id) not in resolved_order:                 # INV-6
        raise UserNotInDraft(str(user_owner_id))

    resolved_personas = {
        str(o): dict(((personas or {}).get(str(o))
                      or {"outlook": DEFAULT_OUTLOOK, "source": PERSONA_DEFAULT}))
        for o in dict.fromkeys([*owners, *resolved_order])
    }
    slots = pick_slots(rounds, teams, draft_type)
    resolved_ownership: dict[str, str] = {}
    if traded_slots:
        by_slot = {(int(row["round"]), int(row["slot"])): row["pick_no"]
                   for row in slots}
        for key, new_owner in traded_slots.items():
            pick_no = by_slot.get((int(key[0]), int(key[1])))
            if pick_no is not None and new_owner:
                resolved_ownership[str(pick_no)] = str(new_owner)
    resolved_ownership.update({str(k): str(v) for k, v in (ownership or {}).items()})
    return {
        "rounds": rounds,
        "type": draft_type,
        "teams": teams,
        "order": resolved_order,
        "order_source": resolved_source,
        # #328 — closed-vocabulary coercion, the `mode` idiom below. Describes
        # create-time provenance of the ownership overlay; the explicit
        # `ownership` parameter (persisted/replay shape) never affects it.
        "ownership_source": (ownership_source
                             if ownership_source in (OWNERSHIP_SOURCE_PLATFORM,
                                                     OWNERSHIP_SOURCE_USER,
                                                     OWNERSHIP_SOURCE_PARTIAL,
                                                     OWNERSHIP_SOURCE_NONE)
                             else OWNERSHIP_SOURCE_NONE),
        # #305 — create-time-immutable. Engine-side coercion keeps this
        # function total (the `draft_type` idiom above); the route already
        # 400'd real garbage as `bad_mode`.
        "mode": mode if mode in (MODE_CPU, MODE_MANUAL) else MODE_CPU,
        "slots": slots,
        "ownership": resolved_ownership,
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
    """The slot on the clock, or ``None`` when the draft is done.

    THE one mode lever (INV-7): in ``manual`` mode every owned slot is
    ``is_user``, so ``advance_cpu`` stops at pick 1 on create and returns
    immediately after every ``/pick``. No other site may read ``mode`` for a
    turn decision. The read-time default keeps pre-mode persisted rows
    byte-identical (T-305-05).
    """
    made = len(state.get("picks") or [])
    slots = state["settings"].get("slots") or []
    if made >= len(slots):
        return None
    slot = dict(slots[made])
    owner = owner_of(slot["pick_no"], state["settings"])
    slot["roster_id"] = owner
    mode = state["settings"].get("mode", MODE_CPU)
    slot["is_user"] = owner is not None and (
        mode == MODE_MANUAL or owner == state["settings"].get("user_owner_id"))
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


def _severity_targets(ctx: MockContext,
                      state: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    """``{pos: (S, B)}`` for this mock's lineup template.

    Split out of :func:`_severities` because :func:`aggregate_severity` needs
    the DENOMINATORS, not just the per-position severities — see its docstring
    for why a ``max()`` over the severities alone is inert (D-5).
    """
    return slot_targets(state["settings"].get("lineup_slots")
                        or ctx.lineup_slots)


def _severities(ctx: MockContext, state: Mapping[str, Any],
                owner_id: str) -> dict[str, float]:
    targets = _severity_targets(ctx, state)
    viable = _team_viable(ctx, state, owner_id)
    return {pos: severity(viable, targets, pos) for pos in _POSITIONS}


def reaches_spent(state: Mapping[str, Any],
                  pool_rows: Sequence[Mapping[str, Any]],
                  round_no: int) -> int:
    """How much of ``round_no``'s frequency budget the recorded CPU picks used.

    Re-derived from the persisted picks rather than carried in memory, for the
    same reason ``_team_viable`` is (T-W2-11): a mock resumed from its row must
    see the same budget state as one that never stopped, or the seeded replay
    stops being exact. The remaining pool at pick *j* is the frozen pre-draft
    pool minus picks ``0..j-1``, so every pick's depth is reconstructible from
    the row alone.

    USER picks are skipped: the budget governs the bots (W2e semantics).
    """
    remaining = [str(r["player_id"]) for r in pool_rows]
    index = {pid: i for i, pid in enumerate(remaining)}
    spent = 0
    for pick in state.get("picks") or ():
        position = index.get(str(pick["player_id"]))
        if position is None:
            continue
        if (position > 0 and pick.get("by") == BY_CPU
                and int(pick.get("round") or 0) == int(round_no)):
            spent += 1
        remaining.pop(position)
        index = {pid: i for i, pid in enumerate(remaining)}
    return spent


def advance_cpu(state: dict, ctx: MockContext,
                pool: Sequence[Mapping[str, Any]] | None = None,
                *, allow_unvalidated_model: bool = False) -> dict:
    """Run CPU picks until the user is on the clock, or the draft completes.

    Raises :class:`CalibrationGateClosed` while :data:`CPU_MODEL_VALIDATED` is
    False unless the caller explicitly opts in — the routes never do, the
    calibration harness and the engine tests do. That is the plan's W2 abort
    criterion expressed in code rather than only in prose.

    **W2e — the round-tiered reach policy is enforced here**, because it is the
    engine that knows the round and the league-wide history; :func:`cpu_pick`
    only knows the cap it is handed. The round's budget is re-derived from the
    row on entry (and reset when the loop crosses a round boundary), so a
    resumed mock and a continuous one spend it identically.
    """
    if not CPU_MODEL_VALIDATED and not allow_unvalidated_model:
        raise CalibrationGateClosed(CALIBRATION_ARTIFACT)

    noise = state["settings"].get("noise") or noise_params()
    max_reach = float(noise.get("max_reach", MOCK_MAX_REACH_DEFAULT))
    bpa_prob = float(noise.get("bpa_prob", MOCK_BPA_PROB_DEFAULT))
    reach_decay = float(noise.get("reach_decay", MOCK_REACH_DECAY_DEFAULT))
    window = candidate_window(max_reach)
    rows = pool if pool is not None else consensus_pool(ctx)
    # Per-mock, not per-pick: the lineup template cannot change mid-draft.
    targets = _severity_targets(ctx, state)
    round_no: int | None = None
    spent = 0

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
        if round_no != int(slot["round"]):
            round_no = int(slot["round"])
            spent = reaches_spent(state, rows, round_no)
        owner = slot["roster_id"]
        persona = (state["settings"].get("personas") or {}).get(
            str(owner), {"outlook": DEFAULT_OUTLOOK})
        # Budget spent => strict best-available for the rest of the round.
        cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
        head = available[:window]
        if cap > 0:
            # #290 — the run can only TIGHTEN the operator's W2e cap, never
            # loosen it. `cap == 0` is the spent-budget case and already means
            # strict best-available, so the run rule is skipped rather than
            # min()'d — that keeps "strict best available" verbatim.
            cap = min(cap, run_offset(
                head,
                allow_cross=0 if round_no <= 2 else MOCK_RUN_CROSS_ALLOWANCE_LATE))
        sev = _severities(ctx, state, str(owner))
        player_id = cpu_pick(head, persona.get("outlook"), sev,
                             _pick_rng(state, slot["pick_no"]),
                             max_reach=max_reach, bpa_prob=bpa_prob,
                             reach_decay=reach_decay, reach_cap=cap,
                             need_pressure_value=need_pressure(sev, targets))
        if str(available[0]["player_id"]) != str(player_id):
            spent += 1                      # this pick was a reach
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
    # ONE pre-draft pool read, reused for the undrafted list AND for the
    # consensus ranks below, so the two cannot disagree about the ordering.
    pool = consensus_pool(ctx)
    if basis == dbs.BASIS_MY_BOARD:
        rows, _ = dbs._undrafted(int(ctx.season), taken, set(ctx.rostered_ids),
                                 dbs.BASIS_MY_BOARD, board_elo,
                                 ctx.consensus_elo, ctx.fetchers())
        undrafted = rows
    else:
        undrafted = _available(ctx, state, pool)

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

    # **Interface G3** — the recap's "+3 / -1 vs consensus" column.
    # `rank` here is the player's 1-based position in the PRE-DRAFT consensus
    # pool, frozen for the whole mock, so a pick's delta does not move as later
    # picks come off the board. Everything the column needs travels on the pick
    # itself; the client never has to hold the full class ordering.
    pre_draft = {str(r["player_id"]): r for r in pool}
    picks = []
    for pick in state.get("picks") or ():
        row = ctx.player_rows.get(str(pick["player_id"])) or {}
        seed = pre_draft.get(str(pick["player_id"])) or {}
        rank = seed.get("rank")
        position = str(row.get("position") or "").upper()
        picks.append({
            "round": pick["round"],
            "pick_no": pick["pick_no"],
            "slot": pick["slot"],
            "player_id": pick["player_id"],
            "name": row.get("full_name") or row.get("name") or "",
            "position": position,
            "team": row.get("team") or None,
            "picked_by_user_id": pick["roster_id"],
            "picked_at": None,
            "by": pick["by"],
            # null when the consensus does not price him (D7's `valued:false`
            # rows sort last but still rank) or when he fell outside the
            # board's undrafted cap. A null rank means "no delta to show",
            # never zero.
            "consensus_rank": rank,
            # Signed in the ADP convention: POSITIVE = went LATER than the
            # consensus said, i.e. value; NEGATIVE = a reach. `+3` reads "the
            # consensus had him 3 slots earlier than where he actually went".
            "consensus_delta": (int(rank) - int(pick["pick_no"])
                                if rank is not None else None),
            "valued": bool(seed.get("valued")) if seed else False,
            # #323 — the pick-value tier ladder rung, server-computed via the
            # canonical band walk (the #263/#277/#278 rule: clients render
            # tiers, never derive them). CONSENSUS-denominated always — never
            # `board_elo`, so the chip cannot flip on a basis toggle (PRD §2
            # basis-independence). None when the player has no consensus Elo
            # (the `valued: false` rows) or sits below the waivers floor —
            # None means "show no tier", never a fabricated one.
            "tier": RankingService.tier_for_elo(
                ctx.consensus_elo.get(str(pick["player_id"])),
                position, ctx.scoring_format),
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
            # #328 — `.get` IS the back-compat story: rows persisted before
            # the label echo `null` (the #305 pre-mode read-time convention).
            "ownership_source": settings.get("ownership_source"),
            "personas": settings.get("personas"),
            "noise": settings.get("noise"),
            # G3 — the denominator for "12th of 79 on the consensus board".
            "consensus_pool_size": len(pool),
            # #305 — ALWAYS present, the only source of mode truth. Pre-mode
            # rows echo the effective value; clients must never infer mode
            # from `by`, pick cadence, or `on_the_clock` (HLD §4.4).
            "mode": settings.get("mode", MODE_CPU),
            # #295/#296/#305 — the caller's team id in this draft: the join
            # key for "my team". In manual mode every pick is `by: "user"`
            # while `picked_by_user_id` walks the order, so keying "my team"
            # off `by` is wrong in exactly the mode that needs it.
            "user_owner_id": user_owner or None,
        },
        "notice": dbs._notice(notice_code),
    }


def empty_payload(reason: str, capability_info: Mapping[str, Any] | None = None) -> dict:
    """M2's typed-empty contract — the only place a new state may appear
    without touching a closed client enum (plan D10).

    ``capability_info`` (W2d/G2) rides along so a client that reads
    ``no_active_mock`` learns in the SAME response whether starting one is even
    possible, instead of having to POST a create to find out.
    """
    out: dict[str, Any] = {"schema": SCHEMA, "empty": True, "reason": reason}
    if capability_info is not None:
        out["capability"] = dict(capability_info)
    return out


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

def _block_rank(rows: Sequence[Mapping[str, Any]], index: int) -> tuple[float, bool]:
    """``(d, was_tied)`` for the row at ``index`` — the AVERAGE 0-based rank of
    the consensus-tied block it belongs to (W2c).

    The pool is already in consensus order, so a tied block is the maximal run
    of neighbours carrying the same ``value``; no ordering happens here
    (amendment 1's no-``sorted`` rule). Inside such a block the shipped
    ``_undrafted`` tiebreak (``search_rank`` then name) decides who is "first",
    which is not an opinion the consensus holds — so charging a drafter the
    full depth of a block he could not have been told apart is measuring the
    tiebreak. Averaging the block is the symmetric alternative: it is applied
    identically to the OBSERVED series here and to the SIMULATED series in
    :func:`simulate_reaches`, keeps every pick (nothing is dropped), and is a
    no-op the moment the values separate.
    """
    value = rows[index].get("value")
    lo = hi = int(index)
    while lo > 0 and rows[lo - 1].get("value") == value:
        lo -= 1
    while hi + 1 < len(rows) and rows[hi + 1].get("value") == value:
        hi += 1
    return (lo + hi) / 2.0, hi > lo


def reach_report(drafted_ids: Sequence[str],
                 pool_rows: Sequence[Mapping[str, Any]]) -> dict:
    """``{series, skipped, tied}`` — the empirical reach for one recorded draft.

    ``d_i`` = how many better-valued AVAILABLE players the pick passed over —
    i.e. the player's 1-based consensus rank in the pool *as it stood at that
    pick*, minus 1, averaged over any consensus-tied block (:func:`_block_rank`).
    ``d_i > 0`` is a reach; ``d_i == 0`` is best-player-available.

    **Deviation from lld §4.2.3, deliberate and recorded in the artifact.**
    The LLD writes ``d_i = consensus_rank_at_pick - i`` *and* says the rank is
    taken over the pool with drafted players removed. Those two clauses
    contradict each other: over a remaining pool the BPA pick always ranks 1,
    so ``rank - i`` would read ``1 - i`` and a pure-BPA draft would score a
    huge "fall". Read the other way (a rank frozen over the pre-draft pool) it
    is that same construction that makes the reading useless: a pure-BPA draft
    scores a large fall no matter what the drafter did, so it cannot falsify a
    noise model — which is the whole point of the amendment. Both readings'
    drift across the split is re-measured by
    ``test_w2_19_the_rebalanced_split_removes_the_depth_drift``, which also
    carries the W2d correction: the static-rank reading drifts far harder than
    this one under the round-based split (3.56 vs 2.02) but slightly LESS under
    W2d's depth-balanced split (1.16 vs 1.44), because most of its excess drift
    WAS the depth term the re-balance removes.

    Picks of players outside ``pool_rows`` are skipped and COUNTED (``skipped``)
    rather than silently dropped: a rookie the consensus does not value carries
    no opinion to reach past, so his ``d`` would be alphabetical order. The
    ranking and the sequence are then restricted to the same sub-universe,
    which leaves ``d`` self-consistent.
    """
    available = [dict(r) for r in pool_rows]
    index = {str(r["player_id"]): i for i, r in enumerate(available)}
    out: list[float] = []
    skipped = tied = 0
    for pid in drafted_ids:
        pid = str(pid)
        if pid not in index:
            skipped += 1
            continue
        position = index[pid]
        d, was_tied = _block_rank(available, position)
        out.append(d)
        tied += int(was_tied)
        available.pop(position)
        index = {str(r["player_id"]): i for i, r in enumerate(available)}
    return {"series": out, "skipped": skipped, "tied": tied}


def reach_series(drafted_ids: Sequence[str],
                 pool_rows: Sequence[Mapping[str, Any]]) -> list[float]:
    """:func:`reach_report`'s series alone."""
    return reach_report(drafted_ids, pool_rows)["series"]


def simulate_reaches(pool_rows: Sequence[Mapping[str, Any]],
                     owners_by_pick: Sequence[str],
                     personas: Mapping[str, str],
                     viable_by_owner: Mapping[str, Mapping[str, int]],
                     targets: Mapping[str, tuple[int, int]],
                     *, bpa_prob: float, reach_decay: float, max_reach: float,
                     seed: int,
                     rounds_by_pick: Sequence[int]) -> list[float]:
    """One seeded replay of a recorded draft through the SHIPPED
    :func:`cpu_pick`, returning the simulated reach series.

    Same observable as :func:`reach_series`, same pool, same turn order — the
    only thing that changes is who chooses. That is what makes the two
    distributions comparable.

    ``rounds_by_pick`` is the recorded ROUND of each pick in the sequence, and
    it is required rather than derived (W2e): the sequence is restricted to the
    picks the consensus prices, so the round is not ``i // teams`` and only the
    corpus knows it. The round-tiered cap and the league-wide frequency budget
    are applied exactly as :func:`advance_cpu` applies them — one forward pass,
    budget consumed in pick order — so the simulator and the product cannot
    diverge on the policy any more than they can on the noise law.
    """
    rng_root = random.Random(seed)
    available = list(pool_rows)             # read-only: never mutated in place
    viable = {o: dict(v) for o, v in viable_by_owner.items()}
    window = candidate_window(max_reach)
    round_no: int | None = None
    spent = 0
    out: list[float] = []
    for pick_no, (owner, pick_round) in enumerate(
            zip(owners_by_pick, rounds_by_pick), start=1):
        if not available:
            break
        owner = str(owner)
        if round_no != int(pick_round):
            round_no, spent = int(pick_round), 0
        needs = {pos: severity(viable.get(owner, {}), targets, pos)
                 for pos in _POSITIONS}
        rng = random.Random(rng_root.randrange(2 ** 31) * 10_007 + pick_no)
        head = available[:window]
        cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
        if cap > 0:
            # #290 R-6 / G-6 — composed IDENTICALLY to `advance_cpu`. Applying
            # the run rule in the product but not here would silently invalidate
            # the calibration harness, which exists to prove the simulator and
            # the product cannot diverge on the policy (:1226-1229).
            cap = min(cap, run_offset(
                head,
                allow_cross=0 if round_no <= 2 else MOCK_RUN_CROSS_ALLOWANCE_LATE))
        chosen = cpu_pick(head, personas.get(owner, DEFAULT_OUTLOOK),
                          needs, rng, max_reach=max_reach, bpa_prob=bpa_prob,
                          reach_decay=reach_decay, reach_cap=cap,
                          need_pressure_value=need_pressure(needs, targets))
        # The pick is always inside the window, so the scan is O(K), not O(n).
        position = next(i for i, r in enumerate(head)
                        if str(r["player_id"]) == chosen)
        if position > 0:
            spent += 1                      # this pick was a reach
        # Tied blocks are averaged exactly as on the observed side (W2c). The
        # block is read over `available`, not `head`, because a block can
        # straddle the window edge — and the observed series reads the whole
        # remaining pool too.
        out.append(_block_rank(available, position)[0])
        pos = str(available[position].get("position") or "").upper()
        if owner in viable and pos in viable[owner]:
            viable[owner][pos] += 1
        available.pop(position)
    return out
