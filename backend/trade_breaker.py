"""trade_breaker.py — counterparty-breaker evaluation layer (v1: stamp + narrate).

Spec: docs/plans/counterparty-breaker/{PLAN,HLD,LLD}.md.

Predicts the counterparty's most likely decline reason for every SERVED card,
in the shipped trade_pass_reasons layer-2 vocabulary (database.py:5579-5583)
plus the one registered extension `roster_crunch` (producer=breaker).

BOUNDARIES (all test-enforced):
  * evaluation only — never reorders, filters, or mutates any existing card
    field; the ONLY writes are the new attributes card.breaker /
    card.breaker_shadow (test_breaker_inert, test_breaker_zero_ordering_effect)
  * raw boards only — member.elo_ratings / the job's raw viewer map; this
    module must never import or call _shrink_user_elo (T3)
  * one production caller: the server.py post-mutation-stack seam. Never
    imported by trade_service, any generator, or bakeoff_runner (D-11 grep
    guard). Never imports trade_gen_fit (their-lens read via card.fit_diag).
  * no DB writes, no HTTP, no LLM, no RNG, no wall clock in any verdict
    (NFR-4; `ms` is diagnostics, never an input).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

from . import trade_service as ts        # T1 — MODULE import
from . import trade_optimizer as topt    # T1 — same discipline
from . import trade_narrative            # hesitation_line + TMPL version

logger = logging.getLogger(__name__)

#: Pinned evaluator version — stamped into every breaker/breaker_shadow
#: payload AND hardcoded as a literal in the server rung-5 handler
#: (test_rung5_marker_version_pinned keeps the two equal). Bump on ANY change
#: to predicates, severity math, floors semantics, evidence shapes, the
#: tie-break priority order, or the format envelope. Calibration readouts
#: filter on this alone (HLD §5.5).
BREAKER_VERSION = "brk-1"

#: The v1 objection classes, in pass order (LLD §3.4). Closed set = the 9
#: coded PASS_REASON_LAYER2 codes minus other_text, restricted to the 6
#: evaluated in v1, plus the registered extension. producer=breaker for all
#: seven taxonomy rows this plan contributes; emitting a producer=negmem code
#: (shape_aversion) is a defect (test_breaker_vocabulary_closure).
PASS_1_CLASSES = ("fit_outlook", "fit_duplicate", "value_giving",
                  "other_player_keep")
PASS_2_CLASSES = ("fit_new_weakness", "roster_crunch")     # feasibility tier
ALL_CLASSES = PASS_1_CLASSES + PASS_2_CLASSES

#: M-6 — argmax tie-break priority when two classes clear their floors at
#: equal (3-dp-rounded) severity: earlier in this tuple wins. A module
#: CONSTANT pinned under BREAKER_VERSION, never a knob — an unpinned
#: dict-order tie-break is a determinism bug waiting for a Python bump.
TIEBREAK_PRIORITY = ("fit_new_weakness", "fit_outlook", "other_player_keep",
                     "fit_duplicate", "roster_crunch", "value_giving")

#: Classes whose evidence is public-observable and therefore ever
#: narration-ELIGIBLE (HLD D-6 whitelist). other_player_keep is permanently
#: dark in v1; value_giving is eligible on the consensus basis ONLY
#: (board-basis value_giving is narration-ineligible outright, D-7).
NARRATABLE_CLASSES = frozenset({"fit_outlook", "fit_new_weakness",
                                "fit_duplicate", "value_giving",
                                "roster_crunch"})

#: Depth-based classes gated by the format envelope (LLD §3.7).
ENVELOPE_CLASSES = frozenset({"fit_new_weakness", "fit_duplicate",
                              "roster_crunch"})

#: LLD §2.4 — the CLOSED evidence-key enum per code. `hesitation_line` may
#: read only these keys and the vocabulary-closure test checks evidence keys
#: too, not just codes: an unlisted key is how a private-state leak sneaks
#: past the whitelist.
EVIDENCE_KEYS: dict[str, frozenset] = {
    "fit_outlook":       frozenset({"outlook", "lean", "asset", "age", "pos"}),
    "fit_new_weakness":  frozenset({"pos", "before", "after", "need", "asset",
                                    "tier_basis"}),
    "fit_duplicate":     frozenset({"pos", "bench_n", "value_share", "asset",
                                    "tier_basis"}),
    "value_giving":      frozenset({"basis", "margin", "n_give", "n_recv"}),
    "other_player_keep": frozenset({"asset", "list"}),
    "roster_crunch":     frozenset({"extra", "slot_cost", "pileup"}),
}

#: The closed breaker-owned knob list, read ONCE per stamp_breaker call into a
#: frozen per-job snapshot (LLD §3.0 — M-5). Enumerated to match the 25 §4
#: registrations exactly; the knob-inventory guard pins those two lists equal.
#: The SNAPSHOT key set is the union of this list and _SHARED_ENGINE_KNOB_KEYS
#: below.
#:
#: The values here are the LLD §4 defaults, used ONLY as the fallback when a
#: key is not (yet) five-registered in trade_service._DEFAULT_CFG — `ts._c`
#: KeyErrors on an unregistered key. Once registered, `ts._c` is authoritative
#: and these are dead weight, which is the point: the module never depends on
#: registration order, and its tests stay hermetic.
_BREAKER_KNOB_DEFAULTS: dict[str, float] = {
    "breaker_ms_budget":                    250.0,
    "breaker_budget_checkpoint_frac":       0.6,
    "breaker_degraded_share_max":           0.05,
    "breaker_min_severity":                 0.60,
    "breaker_max_repeat_frac":              0.34,
    "breaker_shadow_run":                   1.0,
    "breaker_outlook_haircut_legacy":       0.70,
    "breaker_outlook_narrate_margin":       0.06,
    "breaker_board_div_min":                25.0,
    "breaker_board_min_divergent":          10.0,
    "breaker_value_scale":                  400.0,
    "breaker_crunch_scale":                 850.0,
    "breaker_floor_fit_outlook":            0.35,
    "breaker_floor_fit_new_weakness":       0.30,
    "breaker_floor_fit_duplicate":          0.30,
    "breaker_floor_value_giving":           0.30,
    "breaker_floor_value_giving_consensus": 0.75,
    "breaker_floor_other_player_keep":      0.50,
    "breaker_floor_roster_crunch":          0.40,
    "breaker_narrate_fit_outlook":          0.0,
    "breaker_narrate_fit_new_weakness":     0.0,
    "breaker_narrate_fit_duplicate":        0.0,
    "breaker_narrate_value_giving":         0.0,
    "breaker_narrate_other_player_keep":    0.0,
    "breaker_narrate_roster_crunch":        0.0,
}

_BREAKER_KNOB_KEYS: tuple[str, ...] = tuple(_BREAKER_KNOB_DEFAULTS)

#: Engine-owned knobs the breaker also reads (LLD §3.4 waiver adjustment,
#: §3.5 roster_crunch). ALREADY five-registered as engine keys — they need NO
#: new registration and are not counted in §4's 25 — but they MUST be in the
#: frozen snapshot: reading them live via ts._c mid-job would reintroduce the
#: §3.0 hot-flip hazard, and leaving them out of `cfg` is a KeyError.
_SHARED_ENGINE_KNOB_KEYS: tuple[str, ...] = ("waiver_slot_cost",)

_SHARED_ENGINE_KNOB_DEFAULTS: dict[str, float] = {"waiver_slot_cost": 425.0}

#: The positions `_POS_TIER_CUTS` / `_STARTER_NEED` model. Everything else
#: (K/DEF/IDP) is invisible to slot and depth math — LLD §3.7 item 4.
_CORE_POS = ("QB", "RB", "WR", "TE")

#: LLD §3.3 severity constants — version-pinned semantics, deliberately NOT
#: knobs (M-6). Mirrors of trade_narrative._opponent_frame's ±0.05 band.
_LEAN_DEADBAND = 0.05
_LEAN_FULL_PUSH = 0.35

_WIN_NOW_OUTLOOKS = ("contender", "championship")
_REBUILD_OUTLOOKS = ("rebuilder", "jets")


# ---------------------------------------------------------------------------
# Diagnostics + the per-job holder (LLD §1.1 — FitReport precedent, no DB)
# ---------------------------------------------------------------------------

@dataclass
class BreakerReport:
    """Per-job diagnostics. Rides job diagnostics only — never persisted."""
    cards_seen: int = 0
    stamped: int = 0
    degraded_by_rung: dict = field(default_factory=lambda: {
        0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
    narrated: int = 0
    suppressed_by_reason: dict = field(default_factory=dict)
    class_fires: dict = field(default_factory=dict)   # top.code histogram
    predicate_errors: int = 0                         # E-14 containment counter
    format_gapped_decks: int = 0                      # 0/1 — ≥1 gapped class
    partner_ctx_built: int = 0
    partner_ctx_failed: int = 0
    ms_total: float = 0.0
    ms_p50_card: float = 0.0
    ms_p95_card: float = 0.0
    pass2_ran: bool = False                           # False ⇒ rung-2 fired


@dataclass
class BreakerJob:
    """The LLD §3.0 per-job holder — stamp_breaker's return value. Carries the
    frozen knob snapshot AND the report; compose_narration receives it and
    updates the report in place. Ephemeral (job diagnostics only, no DB)."""
    cfg: dict
    report: BreakerReport


@dataclass
class _CardView:
    """LLD §3.1 — give/receive swapped as a VIEW at evaluation time, never as
    data. Partner seat: they send `give_ids`, they receive `recv_ids`."""
    give_ids: list
    recv_ids: list


@dataclass
class PartnerContext:
    """One counterparty's present-state snapshot. Built lazily, once per
    target_user_id per stamp_breaker call, ONLY for partners appearing in the
    served deck."""
    user_id: str
    username: str
    roster: list
    counts: dict
    profile: dict
    outlook: str
    outlook_src: str
    outlook_declared: str | None
    outlook_inferred: str
    outlook_score: float
    board: dict | None
    board_auth: str
    prefs: dict
    format_gap: list
    prefs_available: bool = True
    envelope_ok: bool = True
    identity_src: str = "owner_id"
    degraded: str | None = None


# ---------------------------------------------------------------------------
# Knob snapshot (LLD §3.0)
# ---------------------------------------------------------------------------

def _knob_snapshot() -> dict:
    """One job, one knob-state. Every key of the union list resolved ONCE via
    the module-level `ts._c` (T1 discipline — a monkeypatched knob moves the
    NEXT call's verdicts), falling back to the LLD §4 default while a key is
    still awaiting its five-registration."""
    cfg: dict = {}
    for key in _BREAKER_KNOB_KEYS + _SHARED_ENGINE_KNOB_KEYS:
        fallback = _BREAKER_KNOB_DEFAULTS.get(
            key, _SHARED_ENGINE_KNOB_DEFAULTS.get(key, 0.0))
        try:
            cfg[key] = float(ts._c(key))
        except Exception:
            cfg[key] = float(fallback)
    return cfg


def _marker(reason: str) -> dict:
    """The minimal marker — exactly three keys, constructible anywhere."""
    return {"ver": BREAKER_VERSION, "degraded": reason, "objections": None}


def _sev(x: float) -> float:
    return round(min(1.0, max(0.0, float(x))), 3)


def _entry(code: str, severity, evidence: dict, skipped: str | None = None) -> dict:
    out = {"code": code, "severity": severity, "evidence": evidence}
    if skipped is not None:
        out["skipped"] = skipped
    return out


def _skip(code: str, reason: str) -> dict:
    return _entry(code, None, {}, skipped=reason)


# ---------------------------------------------------------------------------
# Evaluation context — value accessors + the format envelope
# ---------------------------------------------------------------------------

class _EvalCtx:
    """Everything the per-class predicates read besides (view, pctx). Built
    once per stamp_breaker call, inside the LLD §3.0 stud-tax pin."""

    def __init__(self, *, cfg, players, seed_elo, scoring_format, league):
        self.cfg = cfg
        self.players = players
        self.seed_elo = seed_elo
        self.scoring_format = scoring_format
        self.league = league
        self._cv: dict = {}
        self._ovals: dict = {}
        self.league_envelope_ok = _league_in_envelope(league, scoring_format)

    def cval(self, pid: str) -> float:
        v = self._cv.get(pid)
        if v is None:
            v = ts.elo_to_value(self.seed_elo.get(pid, 1500.0))
            self._cv[pid] = v
        return v

    def val_for(self, pctx: PartnerContext):
        """LLD §3.4: `oval` on an authentic board, else consensus optics."""
        if pctx.board_auth != "board" or not pctx.board:
            return self.cval
        fn = self._ovals.get(pctx.user_id)
        if fn is None:
            cache: dict = {}
            board = pctx.board

            def fn(pid: str, _b=board, _c=cache) -> float:
                v = _c.get(pid)
                if v is None:
                    v = ts.elo_to_value(_b.get(pid, 1500.0))
                    _c[pid] = v
                return v
            self._ovals[pctx.user_id] = fn
        return fn

    def is_zero_priced_player(self, pid: str) -> bool:
        """G-026: a PLAYER asset the value space cannot price. Build-time
        resolution of LLD §3.7 item 4 — an IDP/K asset carries a position
        outside `_POS_TIER_CUTS` and no seed Elo, so it prices at the 1500
        default (or at nothing) while occupying a roster slot."""
        p = self.players.get(pid)
        if p is None or ts.is_pick_asset(p):
            return False
        pos = getattr(p, "position", None)
        if pos in _CORE_POS:
            return False
        return pid not in self.seed_elo or self.cval(pid) <= 0.0


def _league_in_envelope(league, scoring_format: str) -> bool:
    """LLD §3.7 items 1–3 — the league-level half of the format envelope."""
    platform = str(getattr(league, "platform", "") or "").lower()
    if platform != "sleeper":
        return False
    members = list(getattr(league, "members", None) or ())
    if len(members) + 1 != 12:
        return False
    fmt = str(scoring_format or "")
    return fmt == "1qb_ppr" or fmt.startswith("sf")


def _num_teams(league) -> int:
    """Q-1: `league.members` excludes the viewer (server.py:362-431), so the
    league size is the member count plus one."""
    return len(list(getattr(league, "members", None) or ())) + 1


def _tier_basis(profile: dict, pos: str | None) -> str:
    """LLD §2.4 enum ("positional"|"absolute"). The engine's own reporting key
    spells the relative mode "position_relative" (trade_service.py:2311) and
    is ABSENT entirely when `trade.position_tiers` is off — both normalize
    here so a fallback row stays distinguishable in data."""
    basis = (profile or {}).get("tier_basis") or {}
    return "positional" if basis.get(pos) == "position_relative" else "absolute"


def _net_player_bodies(view: _CardView, players: dict) -> int:
    """Net PLAYER bodies the partner absorbs (recv − give), picks excluded
    (ts.is_pick_asset takes the player OBJECT, not the pid — Sleeper picks
    occupy no roster slot). The ONE computation behind both value_giving's
    waiver-slot adjustment and roster_crunch's `extra` (LLD §3.4/§3.5):
    shared so the two can never diverge."""
    recv = sum(1 for p in view.recv_ids if not ts.is_pick_asset(players.get(p)))
    give = sum(1 for p in view.give_ids if not ts.is_pick_asset(players.get(p)))
    return recv - give


# ---------------------------------------------------------------------------
# PartnerContext construction (LLD §2.2 / §3.2 / §3.7)
# ---------------------------------------------------------------------------

def _bulk_prefs(user_ids: list, league_id: str) -> tuple[dict, bool]:
    """The §2.2 bulk asset-prefs read. A DB failure (or a build where the
    reader has not landed) degrades the FIELD, not the rung: prefs absence is
    a legitimate common state and marking it "degraded" would swamp the rung
    metrics."""
    try:
        from . import database as db
        reader = getattr(db, "load_asset_preferences_bulk", None)
        if reader is None:
            return {}, False
        return dict(reader(list(user_ids), league_id) or {}), True
    except Exception as err:                                # pragma: no cover
        logger.warning("breaker: bulk asset-prefs read failed: %s", err)
        return {}, False


def _bulk_league_prefs(user_ids: list, league_id: str) -> dict:
    """The §2.2 bulk league-preferences read (declared team_outlook)."""
    try:
        from . import database as db
        reader = getattr(db, "load_league_preferences_bulk", None)
        if reader is None:
            return {}
        return dict(reader(list(user_ids), league_id) or {})
    except Exception as err:                                # pragma: no cover
        logger.warning("breaker: bulk league-prefs read failed: %s", err)
        return {}


def _untouchables(prefs: dict) -> set:
    """`ASSET_PREF_LISTS` spells the list `untouchable` (database.py:8657);
    the LLD prose says "untouchables". Accept both, emit the enum value."""
    if not isinstance(prefs, dict):
        return set()
    return set(prefs.get("untouchable") or prefs.get("untouchables") or ())


def _board_auth(board: dict | None, seed_elo: dict, cfg: dict) -> str:
    """F-3 heuristic: a board that never disagrees with the seed is a clone,
    not a valuation — one pass over the board dict, deterministic."""
    if not board:
        return "consensus"
    div_min = cfg["breaker_board_div_min"]
    divergent = 0
    for pid, elo in board.items():
        base = seed_elo.get(pid)
        if base is None:
            continue
        if abs(float(elo) - float(base)) >= div_min:
            divergent += 1
    return ("board" if divergent >= cfg["breaker_board_min_divergent"]
            else "board_suspect")


def _resolve_outlook(roster, players, pick_share, num_teams, declared):
    """LLD §3.2 — mirrored from trade_service.py:4948-4956, verbatim shape."""
    inferred, score, signals = ts.infer_team_outlook(
        list(roster or ()), players, pick_share, num_teams)
    outlook = declared or inferred
    if declared:
        src = "declared"
    elif ((signals.get("starters") or {}).get("applied")
          if isinstance(signals, dict) else False):
        src = "composite"
    else:
        src = "legacy"
    return outlook, src, inferred, float(score)


def _roster_format_gap(roster, ctx: _EvalCtx) -> list:
    """LLD §3.7 — the ENVELOPE_CLASSES gapped for this league/roster."""
    ok = ctx.league_envelope_ok
    if ok:
        # Item 4 — the G-026 corruption test, one pass over the roster.
        for pid in roster or ():
            if ctx.is_zero_priced_player(pid):
                ok = False
                break
    if ok:
        return []
    return [c for c in ALL_CLASSES if c in ENVELOPE_CLASSES]


def _build_context(*, user_id, username, roster, board_raw, has_rankings,
                   declared, pick_share, prefs, prefs_available, ctx) -> PartnerContext:
    roster = list(roster or ())
    profile = ts.analyze_roster_strengths(roster, ctx.players, ctx.scoring_format)
    counts = topt._pos_counts(roster, ctx.players)
    board = dict(board_raw) if (has_rankings and board_raw) else None
    outlook, src, inferred, score = _resolve_outlook(
        roster, ctx.players, pick_share, _num_teams(ctx.league), declared)
    gap = _roster_format_gap(roster, ctx)
    return PartnerContext(
        user_id=user_id, username=username, roster=roster, counts=counts,
        profile=profile, outlook=outlook, outlook_src=src,
        outlook_declared=declared, outlook_inferred=inferred,
        outlook_score=round(score, 3),
        board=board, board_auth=_board_auth(board, ctx.seed_elo, ctx.cfg),
        prefs=prefs or {}, format_gap=gap, prefs_available=prefs_available,
        envelope_ok=not gap,
    )


# ---------------------------------------------------------------------------
# Per-class predicates (LLD §3.3 – §3.5). Each returns ONE objection entry —
# always. Absence is impossible; only zero/skip are representable (M4).
# ---------------------------------------------------------------------------

def _obj_fit_outlook(view: _CardView, pctx: PartnerContext, ctx: _EvalCtx) -> dict:
    leans = []
    asset, age, pos, best_v = None, None, None, -1.0
    for pid in view.recv_ids:
        p = ctx.players.get(pid)
        if p is None:
            continue
        p_pos = getattr(p, "position", None)
        leans.append(ts._now_lean(p_pos, getattr(p, "age", None)))
        if ts.is_pick_asset(p):
            continue
        v = ctx.cval(pid)
        if v > best_v:
            best_v, asset, age, pos = v, pid, getattr(p, "age", None), p_pos
    if not leans:
        # Nothing on the incoming side resolves — no lean is computable.
        return _skip("fit_outlook", "not_applicable")

    # Byte-parallel to trade_narrative._give_side_now_lean (picks IN at the
    # `_now_lean` PICK constant −0.25) — that identity is what makes the
    # coherence test a proof instead of a hope.
    lean = sum(leans) / len(leans)

    o = pctx.outlook
    if o in _REBUILD_OUTLOOKS:
        push = max(0.0, lean - _LEAN_DEADBAND)
    elif o in _WIN_NOW_OUTLOOKS:
        push = max(0.0, -lean - _LEAN_DEADBAND)
    else:
        push = 0.0
    sev = min(1.0, push / _LEAN_FULL_PUSH)
    if pctx.outlook_src == "legacy":
        sev *= ctx.cfg["breaker_outlook_haircut_legacy"]
    # A declared window that disagrees with the inferred one does NOT move
    # severity; narration is what the §3.8 agreement rule blocks.

    evidence = {"outlook": o, "lean": round(lean, 3),
                "asset": asset, "age": age, "pos": pos}
    return _entry("fit_outlook", _sev(sev), evidence)


def _obj_fit_duplicate(view: _CardView, pctx: PartnerContext,
                       ctx: _EvalCtx) -> dict:
    if "fit_duplicate" in pctx.format_gap:
        return _skip("fit_duplicate", "format_gap")
    if not pctx.roster:
        return _skip("fit_duplicate", "not_applicable")

    by_pos: dict = {}
    total = 0.0
    for pid in view.recv_ids:
        p = ctx.players.get(pid)
        if p is None or ts.is_pick_asset(p):
            continue
        p_pos = getattr(p, "position", None)
        if p_pos not in _CORE_POS:
            continue
        v = ctx.cval(pid)
        total += v
        by_pos.setdefault(p_pos, []).append((v, pid))
    if not by_pos:
        return _skip("fit_duplicate", "not_applicable")

    surplus = set((pctx.profile or {}).get("position_surplus") or ())
    tier_depth = (pctx.profile or {}).get("tier_depth") or {}
    best = None
    for p_pos in _CORE_POS:                      # fixed order — determinism
        entries = by_pos.get(p_pos)
        if not entries or p_pos not in surplus:
            continue
        share = (sum(v for v, _ in entries) / total) if total > 0 else 0.0
        bench_n = int((tier_depth.get(p_pos) or {}).get("bench", 0))
        sev = min(1.0, 0.40 + 0.40 * share + 0.20 * min(bench_n, 4) / 4.0)
        entries.sort(key=lambda e: (-e[0], e[1]))
        cand = (sev, p_pos, bench_n, share, entries[0][1])
        if best is None or sev > best[0]:
            best = cand
    if best is None:
        return _entry("fit_duplicate", 0.0,
                      {"pos": None, "bench_n": 0, "value_share": 0.0,
                       "asset": None,
                       "tier_basis": _tier_basis(pctx.profile, None)})
    sev, p_pos, bench_n, share, asset = best
    return _entry("fit_duplicate", _sev(sev),
                  {"pos": p_pos, "bench_n": bench_n,
                   "value_share": round(share, 3), "asset": asset,
                   "tier_basis": _tier_basis(pctx.profile, p_pos)})


def _obj_value_giving(view: _CardView, pctx: PartnerContext,
                      ctx: _EvalCtx) -> dict:
    # G-026 hazard: a zero-priced PLAYER asset makes the partner's give side
    # look free, inflating the margin. In-envelope leagues cannot hit it.
    if not ctx.league_envelope_ok or not pctx.envelope_ok:
        for pid in (*view.give_ids, *view.recv_ids):
            if ctx.is_zero_priced_player(pid):
                return _skip("value_giving", "format_gap")

    val = ctx.val_for(pctx)
    basis = "board" if pctx.board_auth == "board" and pctx.board else "consensus"
    rvals = [val(p) for p in view.recv_ids]
    gvals = [val(p) for p in view.give_ids]
    if not rvals and not gvals:
        return _entry("value_giving", 0.0,
                      {"basis": basis, "margin": 0.0, "n_give": 0, "n_recv": 0})
    v_max = max(rvals + gvals)
    recvd = ts.package_value_v2(rvals, v_max, n_other=len(gvals),
                                other_values=gvals)
    sent = ts.package_value_v2(gvals, v_max, n_other=len(rvals),
                               other_values=rvals)
    extra = _net_player_bodies(view, ctx.players)
    if extra > 0:
        recvd -= ctx.cfg["waiver_slot_cost"] * extra
    margin = recvd - sent
    sev = min(1.0, max(0.0, -margin) / max(ctx.cfg["breaker_value_scale"], 1e-9))
    return _entry("value_giving", _sev(sev),
                  {"basis": basis, "margin": round(margin, 3),
                   "n_give": len(view.give_ids), "n_recv": len(view.recv_ids)})


def _obj_other_player_keep(view: _CardView, pctx: PartnerContext,
                           ctx: _EvalCtx) -> dict:
    if not pctx.prefs_available:
        # Bulk read unavailable — field-level degrade, rung stays 0 (§2.2).
        return _skip("other_player_keep", "not_applicable")
    unt = _untouchables(pctx.prefs)
    hits = [pid for pid in view.give_ids if pid in unt]
    if not hits:
        return _entry("other_player_keep", 0.0, {"asset": None,
                                                 "list": "untouchable"})
    hits.sort(key=lambda pid: (-ctx.cval(pid), pid))
    top_hit = hits[0]
    package = list(view.give_ids) + list(view.recv_ids)
    package.sort(key=lambda pid: (-ctx.cval(pid), pid))
    sev = 0.9 + (0.1 if package and package[0] in hits else 0.0)
    return _entry("other_player_keep", _sev(sev),
                  {"asset": top_hit, "list": "untouchable"})


def _obj_fit_new_weakness(view: _CardView, pctx: PartnerContext,
                          ctx: _EvalCtx) -> dict:
    if "fit_new_weakness" in pctx.format_gap:
        return _skip("fit_new_weakness", "format_gap")
    if not pctx.roster:
        return _skip("fit_new_weakness", "not_applicable")

    out_d = topt._subset_pos_delta(view.give_ids, ctx.players)
    in_d = topt._subset_pos_delta(view.recv_ids, ctx.players)
    if not any(out_d.get(p, 0) > 0 for p in _CORE_POS):
        # Nothing they send touches a modeled lineup slot. A vacated K/DEF/IDP
        # slot is invisible to the slot math ⇒ format_gap, not a clean zero.
        for pid in view.give_ids:
            p = ctx.players.get(pid)
            if p is None or ts.is_pick_asset(p):
                continue
            if getattr(p, "position", None) not in _CORE_POS:
                return _skip("fit_new_weakness", "format_gap")
        return _skip("fit_new_weakness", "not_applicable")

    worst_pos, worst_slack, need_at, before, after = None, 99, 0, 0, 0
    for p_pos in _CORE_POS:
        if p_pos not in pctx.counts:
            continue
        base = pctx.counts[p_pos]
        need = topt._starters_at(p_pos, ctx.scoring_format)
        post = base - out_d.get(p_pos, 0) + in_d.get(p_pos, 0)
        slack = post - need
        if out_d.get(p_pos, 0) > 0 and slack < worst_slack:
            worst_pos, worst_slack, need_at = p_pos, slack, need
            before, after = base, post

    if worst_slack < 0:
        sev = 1.0
    elif worst_slack == 0:
        sev = 0.60
    elif worst_slack == 1:
        sev = 0.30
    else:
        sev = 0.0

    asset, best_v = None, -1.0
    for pid in view.give_ids:
        p = ctx.players.get(pid)
        if p is None or ts.is_pick_asset(p):
            continue
        if getattr(p, "position", None) != worst_pos:
            continue
        v = ctx.cval(pid)
        if v > best_v:
            best_v, asset = v, pid
    return _entry("fit_new_weakness", _sev(sev),
                  {"pos": worst_pos, "before": before, "after": after,
                   "need": need_at, "asset": asset,
                   "tier_basis": _tier_basis(pctx.profile, worst_pos)})


def _obj_roster_crunch(view: _CardView, pctx: PartnerContext,
                       ctx: _EvalCtx) -> dict:
    if "roster_crunch" in pctx.format_gap:
        return _skip("roster_crunch", "format_gap")
    if not pctx.roster:
        return _skip("roster_crunch", "not_applicable")

    extra = _net_player_bodies(view, ctx.players)
    slot_cost = ctx.cfg["waiver_slot_cost"] * max(extra, 0)
    if extra <= 0:
        return _entry("roster_crunch", 0.0,
                      {"extra": extra, "slot_cost": round(slot_cost, 3),
                       "pileup": []})
    tier_depth = (pctx.profile or {}).get("tier_depth") or {}
    incoming = set()
    for pid in view.recv_ids:
        p = ctx.players.get(pid)
        if p is None or ts.is_pick_asset(p):
            continue
        incoming.add(getattr(p, "position", None))
    pileup = [p_pos for p_pos in _CORE_POS
              if p_pos in incoming
              and int((tier_depth.get(p_pos) or {}).get("bench", 0)) >= 3]
    sev = min(1.0, slot_cost / max(ctx.cfg["breaker_crunch_scale"], 1e-9)
              + 0.15 * min(len(pileup), 2))
    return _entry("roster_crunch", _sev(sev),
                  {"extra": extra, "slot_cost": round(slot_cost, 3),
                   "pileup": pileup})


_PREDICATES = {
    "fit_outlook":       _obj_fit_outlook,
    "fit_duplicate":     _obj_fit_duplicate,
    "value_giving":      _obj_value_giving,
    "other_player_keep": _obj_other_player_keep,
    "fit_new_weakness":  _obj_fit_new_weakness,
    "roster_crunch":     _obj_roster_crunch,
}


def _class_floor(code: str, entry: dict, cfg: dict) -> float:
    """The top-selection floor. `value_giving`'s floor is BASIS-dependent —
    the consensus basis is deliberately much higher (D-7 near-tautology)."""
    if code == "value_giving":
        basis = (entry.get("evidence") or {}).get("basis")
        if basis == "consensus":
            return cfg["breaker_floor_value_giving_consensus"]
        return cfg["breaker_floor_value_giving"]
    return cfg[f"breaker_floor_{code}"]


# ---------------------------------------------------------------------------
# stamp_breaker (LLD §1.1 / §3.9)
# ---------------------------------------------------------------------------

def stamp_breaker(cards: list, *, league, players: dict,
                  seed_elo: dict, scoring_format: str, league_id: str,
                  viewer_user_id: str, viewer_roster: list,
                  viewer_elo: dict, viewer_outlook: str | None,
                  declared_outlooks: dict | None = None,
                  pick_shares: dict | None = None) -> BreakerJob:
    """Evaluate every card from the counterparty's seat and set
    `card.breaker` (+ `card.breaker_shadow` when breaker_shadow_run >= 1).

    Attribute-setting only; two deck-wide passes under breaker_ms_budget with
    the LLD §5 degradation ladder. EVERY card leaves this function carrying
    the attribute — scored payload or minimal marker; absence is impossible by
    construction (M4 pattern). RAISES NOTHING: every exception is absorbed
    into rung-4/5 markers internally. Idempotent: a second call overwrites
    card.breaker wholesale. `cards` may be empty (F3 can empty a deck) —
    no-op, zeroed report. Returns the per-job holder (LLD §3.0)."""
    cfg = _knob_snapshot()
    report = BreakerReport()
    job = BreakerJob(cfg=cfg, report=report)
    cards = list(cards or ())
    report.cards_seen = len(cards)
    if not cards:
        return job

    shadow_on = cfg["breaker_shadow_run"] >= 1.0
    budget = cfg["breaker_ms_budget"] / 1000.0

    def _stamp_marker(card, reason, rung):
        card.breaker = _marker(reason)
        if shadow_on:
            card.breaker_shadow = _marker(reason)
        report.degraded_by_rung[rung] = report.degraded_by_rung.get(rung, 0) + 1

    if budget <= 0:
        # Documented disable — evaluation off, every card labeled.
        for card in cards:
            _stamp_marker(card, "budget_exhausted", 3)
        return job

    try:
        _run(cards, job, league=league, players=players, seed_elo=seed_elo,
             scoring_format=scoring_format, league_id=league_id,
             viewer_user_id=viewer_user_id, viewer_roster=viewer_roster,
             viewer_elo=viewer_elo, viewer_outlook=viewer_outlook,
             declared_outlooks=declared_outlooks, pick_shares=pick_shares,
             shadow_on=shadow_on, budget=budget)
    except Exception as err:                                # pragma: no cover
        logger.warning("breaker: deck evaluation failed (non-fatal): %s", err)
        for card in cards:
            if getattr(card, "breaker", None) is None:
                _stamp_marker(card, "exception_card", 4)
    return job


class _Work:
    """Per-card mutable evaluation state — never leaves this module."""

    __slots__ = ("card", "view", "shadow_view", "pctx", "objs", "shadow_objs",
                 "ms", "done")

    def __init__(self, card):
        self.card = card
        self.view = None
        self.shadow_view = None
        self.pctx = None
        self.objs: dict = {}
        self.shadow_objs: dict = {}
        self.ms = 0.0
        self.done = False


def _run(cards, job, *, league, players, seed_elo, scoring_format, league_id,
         viewer_user_id, viewer_roster, viewer_elo, viewer_outlook,
         declared_outlooks, pick_shares, shadow_on, budget) -> None:
    cfg, report = job.cfg, job.report
    t0 = time.monotonic()

    def elapsed():
        return time.monotonic() - t0

    members = {m.user_id: m for m in (getattr(league, "members", None) or ())}
    partner_ids = []
    for card in cards:
        uid = getattr(card, "target_user_id", None)
        if uid is not None and uid not in partner_ids:
            partner_ids.append(uid)
    pref_ids = list(partner_ids)
    if viewer_user_id not in pref_ids:
        pref_ids.append(viewer_user_id)

    bulk_prefs, prefs_ok = _bulk_prefs(pref_ids, league_id)
    bulk_lprefs = (_bulk_league_prefs(pref_ids, league_id)
                   if not declared_outlooks else {})

    # Every breaker valuation runs under an explicit stud-tax pin: the seam
    # leaves the thread-local unset, and a partner's own mode is private state
    # the breaker cannot know (LLD §3.0 hazard 3, M-5).
    with ts.stud_tax_override("market"):
        ctx = _EvalCtx(cfg=cfg, players=players, seed_elo=seed_elo,
                       scoring_format=scoring_format, league=league)
        pctx_cache: dict = {}

        def _partner_context(uid):
            if uid in pctx_cache:
                return pctx_cache[uid]
            member = members.get(uid)
            if member is None:
                raise KeyError(f"partner {uid!r} absent from league.members")
            declared = (declared_outlooks or {}).get(uid)
            if declared is None and not declared_outlooks:
                declared = (bulk_lprefs.get(uid) or {}).get("team_outlook")
            out = _build_context(
                user_id=uid, username=getattr(member, "username", "") or "",
                roster=getattr(member, "roster", None),
                board_raw=getattr(member, "elo_ratings", None),
                has_rankings=bool(getattr(member, "has_rankings", False)),
                declared=declared or None,
                pick_share=float((pick_shares or {}).get(uid, 0.0) or 0.0),
                prefs=bulk_prefs.get(uid) or {}, prefs_available=prefs_ok,
                ctx=ctx)
            pctx_cache[uid] = out
            return out

        viewer_pctx = None
        if shadow_on:
            try:
                viewer_pctx = _build_context(
                    user_id=viewer_user_id, username="", roster=viewer_roster,
                    board_raw=viewer_elo, has_rankings=bool(viewer_elo),
                    declared=viewer_outlook or None,
                    pick_share=float((pick_shares or {}).get(viewer_user_id, 0.0)
                                     or 0.0),
                    prefs=bulk_prefs.get(viewer_user_id) or {},
                    prefs_available=prefs_ok, ctx=ctx)
            except Exception as err:                        # pragma: no cover
                logger.warning("breaker: viewer shadow context failed: %s", err)
                viewer_pctx = None

        work = [_Work(c) for c in cards]

        def _eval_classes(classes, view, pctx, sink):
            for code in classes:
                try:
                    sink[code] = _PREDICATES[code](view, pctx, ctx)
                except Exception as err:
                    # E-14 — per-CLASS containment: the card stays rung 0 with
                    # the other classes scored, and the skip is DURABLE so the
                    # §8 readout can count unattributable crashes from data.
                    logger.warning("breaker: predicate %s raised: %s", code, err)
                    sink[code] = _skip(code, "predicate_error")
                    report.predicate_errors += 1

        # ── PASS 1 ────────────────────────────────────────────────────────
        exhausted_at = None
        for i, w in enumerate(work):
            if exhausted_at is not None:
                break
            c_t0 = time.monotonic()
            card = w.card
            try:
                uid = getattr(card, "target_user_id", None)
                if uid == viewer_user_id:
                    # Not constructible today; guarded anyway (E-7).
                    card.breaker = _marker("self_partner")
                    if shadow_on:
                        card.breaker_shadow = _marker("self_partner")
                    report.degraded_by_rung[4] += 1
                    w.done = True
                    continue
                w.view = _CardView(
                    give_ids=list(getattr(card, "receive_player_ids", None) or ()),
                    recv_ids=list(getattr(card, "give_player_ids", None) or ()))
                w.shadow_view = _CardView(
                    give_ids=list(getattr(card, "give_player_ids", None) or ()),
                    recv_ids=list(getattr(card, "receive_player_ids", None) or ()))
                try:
                    w.pctx = _partner_context(uid)
                    report.partner_ctx_built = len(pctx_cache)
                except Exception as err:
                    logger.warning("breaker: partner context failed (%s): %s",
                                   uid, err)
                    report.partner_ctx_failed += 1
                    card.breaker = _marker("partner_snapshot")
                    if shadow_on:
                        card.breaker_shadow = _marker("partner_snapshot")
                    report.degraded_by_rung[1] += 1
                    w.done = True
                    continue
                _eval_classes(PASS_1_CLASSES, w.view, w.pctx, w.objs)
                if shadow_on and viewer_pctx is not None:
                    _eval_classes(PASS_1_CLASSES, w.shadow_view, viewer_pctx,
                                  w.shadow_objs)
            except Exception as err:
                logger.warning("breaker: card evaluation failed: %s", err)
                card.breaker = _marker("exception_card")
                if shadow_on:
                    card.breaker_shadow = _marker("exception_card")
                report.degraded_by_rung[4] += 1
                w.done = True
            w.ms += (time.monotonic() - c_t0) * 1000.0
            if elapsed() > budget:
                exhausted_at = i + 1

        if exhausted_at is not None:
            for w in work[exhausted_at:]:
                w.card.breaker = _marker("budget_exhausted")
                if shadow_on:
                    w.card.breaker_shadow = _marker("budget_exhausted")
                report.degraded_by_rung[3] += 1
                w.done = True

        live = [w for w in work if not w.done]

        # ── CHECKPOINT + PASS 2 (atomic — M-9) ────────────────────────────
        pass2_skip_reason = None
        if elapsed() > cfg["breaker_budget_checkpoint_frac"] * budget:
            pass2_skip_reason = "budget"          # rung 2 — deck-uniform
        else:
            buffer: dict = {}
            shadow_buffer: dict = {}
            for w in live:
                c_t0 = time.monotonic()
                sink: dict = {}
                shadow_sink: dict = {}
                _eval_classes(PASS_2_CLASSES, w.view, w.pctx, sink)
                if shadow_on and viewer_pctx is not None:
                    _eval_classes(PASS_2_CLASSES, w.shadow_view, viewer_pctx,
                                  shadow_sink)
                buffer[id(w)] = sink
                shadow_buffer[id(w)] = shadow_sink
                w.ms += (time.monotonic() - c_t0) * 1000.0
                if elapsed() > budget:
                    pass2_skip_reason = "budget_exhausted"
                    break
            if pass2_skip_reason is None:
                report.pass2_ran = True
                for w in live:
                    w.objs.update(buffer.get(id(w)) or {})
                    w.shadow_objs.update(shadow_buffer.get(id(w)) or {})

        # ── FINALIZE ──────────────────────────────────────────────────────
        per_card_ms = []
        gapped_deck = False
        for w in live:
            payload = _finalize(w.objs, w.pctx, w.card, cfg,
                                pass2_skip_reason=pass2_skip_reason,
                                ms=w.ms, shadow=False)
            w.card.breaker = payload
            if payload.get("format_gap"):
                gapped_deck = True
            if shadow_on:
                if viewer_pctx is None:
                    w.card.breaker_shadow = _marker("partner_snapshot")
                else:
                    w.card.breaker_shadow = _finalize(
                        w.shadow_objs, viewer_pctx, w.card, cfg,
                        pass2_skip_reason=pass2_skip_reason, ms=w.ms,
                        shadow=True)
            report.stamped += 1
            rung = 2 if pass2_skip_reason else 0
            report.degraded_by_rung[rung] = report.degraded_by_rung.get(rung, 0) + 1
            top = payload.get("top")
            if top:
                report.class_fires[top["code"]] = \
                    report.class_fires.get(top["code"], 0) + 1
            per_card_ms.append(w.ms)

        report.format_gapped_decks = 1 if gapped_deck else 0
        report.ms_total = round((time.monotonic() - t0) * 1000.0, 1)
        if per_card_ms:
            ordered = sorted(per_card_ms)
            report.ms_p50_card = round(ordered[len(ordered) // 2], 1)
            p95 = ordered[min(len(ordered) - 1,
                              int(math.ceil(0.95 * len(ordered))) - 1)]
            report.ms_p95_card = round(p95, 1)


def _finalize(objs: dict, pctx: PartnerContext, card, cfg: dict, *,
              pass2_skip_reason, ms: float, shadow: bool) -> dict:
    """Assemble the §2.1 payload: full objection vector, argmax top, `them`
    passthrough, provenance markers, rounded `ms`."""
    objections = []
    for code in ALL_CLASSES:
        entry = objs.get(code)
        if entry is None:
            entry = _skip(code, pass2_skip_reason or "budget")
        objections.append(entry)

    top = None
    best = None
    for entry in objections:
        sev = entry.get("severity")
        if sev is None or entry.get("skipped"):
            continue
        if sev < _class_floor(entry["code"], entry, cfg):
            continue
        rank = TIEBREAK_PRIORITY.index(entry["code"])
        key = (-sev, rank)
        if best is None or key < best:
            best = key
            top = {"code": entry["code"], "severity": sev,
                   "evidence": entry["evidence"]}

    them = None
    if not shadow:
        fd = getattr(card, "fit_diag", None)
        if isinstance(fd, dict):
            them = fd.get("them")

    format_gap = [e["code"] for e in objections
                  if e.get("skipped") == "format_gap"] or None

    payload = {
        "ver": BREAKER_VERSION,
        "tmpl_ver": None,
        "top": top,
        "objections": objections,
        "them": them,
        "narrated": None,
        "suppressed": None,
        "outlook_src": pctx.outlook_src,
        "outlook_pair": {"declared": pctx.outlook_declared,
                         "inferred": pctx.outlook_inferred,
                         "score": pctx.outlook_score},
        "board_auth": pctx.board_auth,
        "value_mode": "market",
        "identity_src": pctx.identity_src,
        "format_gap": format_gap,
        "degraded": "budget_exhausted" if pass2_skip_reason == "budget_exhausted"
                    else None,
        "skipped": ({"classes": list(PASS_2_CLASSES),
                     "reason": pass2_skip_reason} if pass2_skip_reason else None),
        "ms": round(ms, 1),
    }
    return payload


# ---------------------------------------------------------------------------
# compose_narration (LLD §1.1 / §3.8)
# ---------------------------------------------------------------------------

def _suppress(payload: dict, reason: str, report: BreakerReport) -> None:
    payload["narrated"] = None
    payload["suppressed"] = reason
    report.suppressed_by_reason[reason] = \
        report.suppressed_by_reason.get(reason, 0) + 1


def _outlook_cut(inferred: str) -> float | None:
    try:
        if inferred == "contender":
            return float(ts._c("infer_contender_cut"))
        if inferred == "rebuilder":
            return float(ts._c("infer_rebuilder_cut"))
    except Exception:                                       # pragma: no cover
        return None
    return None


def compose_narration(cards: list, *, players: dict, job: BreakerJob) -> int:
    """Deck-level narration pass (flag trade.breaker_narrative, checked at the
    CALLSITE — this function assumes it is wanted).

    Applies the LLD §3.8 eligibility chain, then deck-level repetition
    suppression, then calls trade_narrative.hesitation_line. Returns the count
    narrated (0 is normal and is the M-1 republish condition). Never touches
    card.narrative, card order, or breaker_shadow (shadow never narrates).
    Idempotent; must run after stamp_breaker in the same job. Per-card
    internal exceptions stamp `suppressed: "template_error"`, never raise."""
    cfg, report = job.cfg, job.report
    cards = list(cards or ())
    if not cards:
        return 0

    partner_card_counts: dict = {}
    for card in cards:
        uid = getattr(card, "target_user_id", None)
        partner_card_counts[uid] = partner_card_counts.get(uid, 0) + 1

    survivors = []                       # (card, payload, code, severity)
    for card in cards:
        payload = getattr(card, "breaker", None)
        if not isinstance(payload, dict) or payload.get("objections") is None:
            continue                     # marker-only card — nothing to narrate
        payload["narrated"] = None
        payload["suppressed"] = None
        payload["tmpl_ver"] = None
        try:
            top = payload.get("top")
            if not top:
                continue
            code = top["code"]
            if cfg.get(f"breaker_narrate_{code}", 0.0) < 1.0:
                _suppress(payload, "class_ineligible", report)
                continue
            if code not in NARRATABLE_CLASSES:
                _suppress(payload, "class_ineligible", report)
                continue
            evidence = top.get("evidence") or {}
            if code == "value_giving" and evidence.get("basis") != "consensus":
                _suppress(payload, "class_ineligible", report)
                continue
            if code in (payload.get("format_gap") or ()):
                _suppress(payload, "format_gap", report)
                continue
            floor = _class_floor(code, {"evidence": evidence}, cfg)
            if top["severity"] < max(floor, cfg["breaker_min_severity"]):
                _suppress(payload, "below_floor", report)
                continue
            if code == "fit_outlook" and not _outlook_narratable(payload, cfg):
                _suppress(payload, "class_ineligible", report)
                continue
            survivors.append((card, payload, code, top["severity"]))
        except Exception as err:                            # pragma: no cover
            logger.warning("breaker: narration eligibility failed: %s", err)
            _suppress(payload, "template_error", report)

    # Repetition suppression (D-7) — per (partner, code), per deck.
    groups: dict = {}
    for idx, item in enumerate(survivors):
        card, _payload, code, _sev_v = item
        groups.setdefault((getattr(card, "target_user_id", None), code),
                          []).append((idx, item))
    winners = set()
    for (uid, _code), members_ in groups.items():
        limit = math.ceil(cfg["breaker_max_repeat_frac"]
                          * partner_card_counts.get(uid, len(members_)))
        if len(members_) <= limit:
            winners.update(idx for idx, _ in members_)
            continue
        best_idx = min(members_, key=lambda m: (-m[1][3], m[0]))[0]
        winners.add(best_idx)
        for idx, (_c, payload, _cd, _s) in members_:
            if idx != best_idx:
                _suppress(payload, "repetition", report)

    narrated = 0
    tmpl_ver = getattr(trade_narrative, "HESITATION_TMPL_VERSION", None)
    for idx, (card, payload, code, _sev_v) in enumerate(survivors):
        if idx not in winners:
            continue
        try:
            sentence = trade_narrative.hesitation_line(payload["top"], players)
        except Exception as err:
            logger.warning("breaker: hesitation_line raised: %s", err)
            _suppress(payload, "template_error", report)
            continue
        if not sentence:
            # A template refusal is honest silence, not a suppression reason.
            continue
        payload["narrated"] = sentence
        payload["tmpl_ver"] = tmpl_ver
        narrated += 1

    report.narrated = narrated
    return narrated


def _outlook_narratable(payload: dict, cfg: dict) -> bool:
    """LLD §3.8 step 6 — D-8 agreement rule + the inferred-window margin. The
    narration bar sits ABOVE the stamp bar."""
    pair = payload.get("outlook_pair") or {}
    declared, inferred = pair.get("declared"), pair.get("inferred")
    if declared and declared != inferred:
        return False
    if payload.get("outlook_src") != "legacy":
        return True
    cut = _outlook_cut(inferred)
    if cut is None:
        return False
    score = pair.get("score")
    if score is None:
        return False
    return abs(float(score) - cut) >= cfg["breaker_outlook_narrate_margin"]
