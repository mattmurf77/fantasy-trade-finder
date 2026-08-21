"""
receipts_service.py — Receipts: grading served trade suggestions against
subsequent CONSENSUS value movement (flags `receipts.grading` /
`receipts.screen`, both default OFF).

Plan suite: docs/plans/receipts/ (PLAN → HLD → LLD → PRD). Shared vocabulary:
docs/plans/shared/trade-shape-taxonomy.md.

WHAT THIS MODULE IS. The serve-time `deck_impressions` row is a PREREGISTERED
prediction: `assets_json` names the asset set and its direction, and it was
frozen before any outcome existed. This module marks that prediction to market
at 14 / 28 / 56 days using `player_value_history` — the daily consensus
snapshot table, denormalized at snapshot time (`database.py:1294-1296`) so an
engine repricing can never rewrite recorded history — and appends one
immutable grade row per (impression, window, grader_version).

WHAT IT IS NOT. It answers "did the VALUE move as the suggestion implied?",
never "did the trade EXECUTE?" — that is `suggestion_trade_links` /
`suggestion_telemetry.py`, a different question and a different table family
(HLD §1). Nothing here feeds generation or ordering: no engine module reads
`receipts_*` and this module imports no engine module (PLAN NG-1 / §7.3).

THIS MODULE IS A LEAF. Imports are `database`, `feature_flags`,
`pick_values.parse_generic_pick_id` (import-safe by design — pick_values'
`elo_to_value` dependency is deliberately lazy, `pick_values.py:11-14`) and
stdlib. NOTHING from `trade_service` / `trade_optimizer` / `trade_gen_*` /
`bakeoff_*` / `server` / `suggestion_telemetry` — the same leaf discipline
`suggestion_telemetry.py` states in its own docstring, pinned by
`backend/tests/test_receipts_grading.py` (T-1).

THE METRIC IS SWAP EDGE (HLD D-1):

    edge = (receive-side consensus delta) − (give-side consensus delta)

The give side is the built-in market control. Precisely — and only this
much — uniform MULTIPLICATIVE drift `m` yields `edge = m · (serve-time
imbalance)`, which is ≈0 for the near-balanced packages a fairness gate
admits; uniform ADDITIVE drift `d` yields `edge = d · (n_receive − n_give)`,
exactly 0 for equal-cardinality shapes and `−d` for a 2x1 (give 2, receive 1)
under the taxonomy §2.1 direction convention. Residual shape effects are
DISCLOSED per shape cell, never hidden. A standalone acquire-side percentage
measures the market, not the engine, and is banned copy (PRD §4.4).

FOUR FORBIDDEN OPERATIONS (preregistration enforcement, PRD DR-4). Each has a
named test in `backend/tests/test_receipts_grading.py`:
  1. Import or replay engine code.                                      (T-1)
  2. Read any LIVE value — seeds, `elo_to_value`, or
     `features_json.give_value/receive_value` — for valuation or edge
     arithmetic. `features_json` is read for SLICING ONLY. The sole
     exemption is this module's own frozen `RECEIPTS_PICK_WEIGHTS`, used
     for coverage / pick-share and never for edge.                 (T-3, T-4)
  3. Reconstruct assets from `trade_hash` (it is not invertible).       (T-1)
  4. UPDATE or DELETE a grade row. Corrections are a `grader_version`
     bump plus a regrade, with the old rows retained.               (T-8, T-10)
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import database as db
from .feature_flags import is_enabled
from .pick_values import parse_generic_pick_id

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (LLD §1)
# ---------------------------------------------------------------------------

#: Bump on ANY change to grading semantics (HLD D-3). Reads pin the MAX
#: version present, compared by numeric suffix; superseded rows are retained
#: and the screen footnotes the regrade. Two bumps inside a month is PLAN A-4:
#: stop and re-review the grader design.
GRADER_VERSION = "receipts-1"

#: Mirrors docs/plans/shared/trade-shape-taxonomy.md (HLD D-10). The LLD text
#: was written against 1.0.0; the shared file landed at 1.1.1, whose only
#: additions (§5 objection vocabulary) are explicitly no-impact for Receipts
#: and whose §1–§4 — everything this module reads — are unchanged. The stamp
#: records the version actually in the tree at build time, because a stamp
#: naming a version the repo does not contain is worse provenance than none.
TAXONOMY_VERSION = "1.1.1"

#: Fixed. Additive changes only: one payload always carries all three, so no
#: surface can select the best-looking window (PLAN §3.3).
WINDOWS_DAYS = (14, 28, 56)

#: The headline window, fixed in advance (PRD DR-1).
HEADLINE_WINDOW_DAYS = 28

#: Junk-for-junk guard, VALUE units. Below this serve-time package midpoint
#: `edge_pct` is NULL — the edge is still recorded and the row still counts,
#: but a ±40 swing on a 60-value package is not a 67% call. NULL rows are
#: excluded from the median and DISCLOSED (`disclosure.null_edge_pct`). A
#: constant rather than a knob on purpose: the honesty rules are version-
#: pinned under `grader_version`, not operator-tunable.
EDGE_PCT_MIN_MIDPOINT = 100.0

#: How long an impression×window waits for its window snapshot before the
#: row becomes terminally `ungradeable/missing_snapshot`. Until the deadline
#: the row is simply absent from the grades table — retry-pending is queue-
#: implicit and never persisted (LLD §3 invariants).
RETRY_GRACE_DAYS = 14

#: Pick weights for COVERAGE and PICK-SHARE only — never edge arithmetic.
#: Picks contribute delta 0 (HLD D-7): pick prices are static code seeds
#: repriced by commits (D-084 repriced round 2 on 2026-08-19), so grading them
#: would grade our own deploys.
#:
#: VALUE-unit constants FROZEN here. Populated ONCE at build time from
#: elo_to_value(GENERIC_PICK_SEEDS[(round, "Mid")]) under the shipped
#: elo_value_* defaults (base 1000, k 0.0050, ref 1500) and then hard-coded:
#:     round 1: 1000·exp(0.005·(1650−1500)) = 2117.0
#:     round 2: 1000·exp(0.005·(1400−1500)) =  606.5
#:     round 3: 1000·exp(0.005·(1320−1500)) =  406.6
#:     round 4: 1000·exp(0.005·(1240−1500)) =  272.5
#: Deliberately NOT read live. GENERIC_PICK_SEEDS are ELO units and are
#: deploy-variant; reading them live would flip the same impression between
#: `graded` and `pick_majority` under one grader_version on a repricing day.
#: Owned picks map to their round's Mid rung. Any change to this table bumps
#: GRADER_VERSION.
RECEIPTS_PICK_WEIGHTS: dict[int, float] = {
    1: 2117.0,
    2: 606.5,
    3: 406.6,
    4: 272.5,
}

#: Rounds > 4 clamp to the round-4 weight, mirroring `pick_values.py:284-285`.
#: The owned-pick regex admits any round, and a KeyError here would re-queue
#: the impression forever.
_MAX_PICK_ROUND = 4

#: Status / reason enum — TERMINAL rows only (LLD §5.3).
STATUS_GRADED = "graded"
STATUS_UNGRADEABLE = "ungradeable"
REASONS = (
    "pick_majority",       # a side is mostly picks; picks are delta 0
    "no_serve_snapshot",   # zero graded players on a side — no market control
    "missing_snapshot",    # window endpoint never arrived, retry deadline passed
    "malformed_assets",    # assets_json is not a two-list object
    "format_missing",      # league scoring format unresolvable
)

#: Deploy-free kill switch, checked before the flag (LLD §2.1).
_ENV_KILL = "FTF_RECEIPTS_GRADE"

# Single-flight. One gunicorn worker (`render.yaml:16`), so a module-level
# lock is the whole concurrency story: a second trigger while a run is in
# flight returns started=false rather than queueing (LLD §5.1).
_RUN_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def grading_enabled() -> bool:
    """Env kill switch first, then the flag. Both must allow the run."""
    if os.environ.get(_ENV_KILL, "").strip() == "0":
        return False
    return bool(is_enabled("receipts.grading"))


def screen_enabled() -> bool:
    return bool(is_enabled("receipts.screen"))


def is_running() -> bool:
    """True while a grading run holds the single-flight lock. The cron route
    reads this to answer `started` honestly in its 202 without waiting for the
    daemon thread it is about to spawn."""
    return _RUN_LOCK.locked()


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _shift(date_str: str, days: int) -> str:
    """`'2026-08-16' + 14` → `'2026-08-30'`. All receipts date math is on UTC
    dates; `served_at` is ISO UTC and `snapshot_date` is a UTC `YYYY-MM-DD`,
    so there is no local-time or DST surface anywhere in this module."""
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def _daterange(start: str, end: str) -> list[str]:
    """Inclusive list of UTC dates from `start` to `end` ('' when reversed)."""
    if not start or not end or start > end:
        return []
    out, cur = [], start
    # Bounded so a corrupt `served_at` can never spin: the telemetry era began
    # 2026-08-16, two years of dates is a decade of headroom.
    for _ in range(800):
        out.append(cur)
        if cur >= end:
            break
        cur = _shift(cur, 1)
    return out


def pick_round(asset_id: str, league_id: str) -> int | None:
    """Round number when `asset_id` is a draft pick, else None.

    Two id shapes, both stamped into `assets_json` at serve:
      * generic ladder — `generic_pick_{round}_{tier}`, parsed by
        `pick_values.parse_generic_pick_id` (the one import this module takes
        from the pick ladder, and an import-safe one).
      * owned pick — `{league_id}_{season}_{round}_{orig_roster}`. The regex
        is COPIED here rather than importing `suggestion_telemetry`
        (`:196`), which is a sibling leaf this module must not depend on.
    """
    pid = str(asset_id)
    generic = parse_generic_pick_id(pid)
    if generic is not None:
        return int(generic[0])
    m = re.match(rf"^{re.escape(str(league_id))}_(\d{{4}})_(\d+)_(.+)$", pid)
    if m:
        try:
            return int(m.group(2))
        except (TypeError, ValueError):
            return None
    return None


def pick_weight(round_: int) -> float:
    """Frozen coverage/pick-share weight for a pick round (never an edge
    input). Rounds beyond 4 clamp to the round-4 weight."""
    return RECEIPTS_PICK_WEIGHTS[min(max(int(round_), 1), _MAX_PICK_ROUND)]


def parse_grader_version(version: str) -> int:
    """Numeric suffix of a `grader_version` string. Reads pin the MAX by this
    number, never lexicographically — `receipts-10` must beat `receipts-2`."""
    try:
        return int(str(version).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def max_grader_version(versions: list[str]) -> str | None:
    """Highest grader_version present, by numeric suffix (LLD §2.2)."""
    real = [v for v in versions if v]
    if not real:
        return None
    return max(real, key=parse_grader_version)


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval on a win share — the CENTER-SHIFTED form.

        ( p̂ + z²/2n ± z·√( p̂(1−p̂)/n + z²/4n² ) ) / ( 1 + z²/n )

    The `z²/2n` center shift is material at the single-digit n this feature
    will live at for months; dropping it moves the interval by 0.2–0.4 at
    n ≤ 10, on a feature whose entire pitch is honesty. Pinned in T-9 against
    3 wins of 5 → [0.231, 0.882].
    """
    n = int(n)
    if n <= 0:
        return (0.0, 1.0)
    p = float(wins) / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (float(vals[mid - 1]) + float(vals[mid])) / 2.0


def _knob(cfg: dict, key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return float(default)


# ---------------------------------------------------------------------------
# Snapshot anchoring (LLD §4.2)
# ---------------------------------------------------------------------------

def _serve_anchor_dates(date_str: str, tol: int) -> list[str]:
    """Candidate SERVE-endpoint dates, nearest first, strictly on-or-BEFORE
    the serve date. No post-serve information may ever enter the baseline —
    this is the `latest_value_snapshot_date` nearest-≤ idiom
    (`database.py:10883`) spelled out for a memoized lookup."""
    return [_shift(date_str, -k) for k in range(0, max(0, tol) + 1)]


def _window_anchor_dates(date_str: str, tol: int) -> list[str]:
    """Candidate WINDOW-endpoint dates, nearest first, within ±tol. Ties
    resolve to the EARLIER date so the choice is deterministic across runs
    and dialects."""
    out = [date_str]
    for k in range(1, max(0, tol) + 1):
        out.append(_shift(date_str, -k))
        out.append(_shift(date_str, k))
    return out


def _first_present(dates: list[str], available: set[str]) -> str | None:
    for d in dates:
        if d in available:
            return d
    return None


def resolvable_serve_dates(snapshot_dates: set[str], window_days: int,
                           tol: int, today: str,
                           min_serve_date: str) -> list[str]:
    """Serve dates whose `window_days` endpoint produces a TERMINAL row today.

    Two ways to qualify, and the union is exactly "not retry-pending":
      * the window endpoint resolves — some snapshot lies within ±tol of it;
      * the retry deadline has passed (`today ≥ window_date + 14`), so the row
        is terminally `ungradeable/missing_snapshot`.

    Folding this into the queue predicate (LLD §4.1) is what lets the batch
    cap bound TERMINAL rows: a head-of-queue block of unresolvable rows can
    never starve a run.
    """
    latest_serve = _shift(today, -int(window_days))
    out = []
    for s in _daterange(min_serve_date, latest_serve):
        wd = _shift(s, int(window_days))
        if _first_present(_window_anchor_dates(wd, tol), snapshot_dates):
            out.append(s)
        elif today >= _shift(wd, RETRY_GRACE_DAYS):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# The grader (LLD §4.3) — a pure function of its inputs
# ---------------------------------------------------------------------------

class _SideResult:
    __slots__ = ("serve_sum", "window_sum", "coverage", "pick_share",
                 "detail", "graded_n", "imputed_n", "has_picks", "denom")

    def __init__(self, serve_sum, window_sum, coverage, pick_share, detail,
                 graded_n, imputed_n, has_picks, denom):
        self.serve_sum = serve_sum
        self.window_sum = window_sum
        self.coverage = coverage
        self.pick_share = pick_share
        self.detail = detail
        self.graded_n = graded_n
        self.imputed_n = imputed_n
        self.has_picks = has_picks
        self.denom = denom


class GradeContext:
    """Everything `grade_one` needs, prefetched once per run (LLD §4.2)."""

    def __init__(self, scoring_format: str, snapshots: dict,
                 snapshot_dates: set[str], floors: dict, tol: int,
                 pick_share_max: float, today: str):
        self.scoring_format = scoring_format
        self.snapshots = snapshots            # {(player_id, date): value}
        self.snapshot_dates = snapshot_dates  # dates present for this format
        self.floors = floors                  # {date: MIN(consensus_value)}
        self.tol = int(tol)
        self.pick_share_max = float(pick_share_max)
        self.today = today

    def value_at(self, player_id: str, date: str) -> float | None:
        return self.snapshots.get((str(player_id), date))

    def floor_at(self, date: str | None) -> float:
        """Consensus pool floor on a date; 0.0 when the date has no rows.

        0.0 rather than an exception on purpose: with no format history at
        all, every player is unresolved and the row terminates at
        `no_serve_snapshot` (or at `pick_majority` first, if it is a
        pick-heavy package) — which is the ordering LLD §4.3 prescribes.
        """
        if not date:
            return 0.0
        return float(self.floors.get(date, 0.0))


def _ungradeable(imp: dict, window_days: int, reason: str, ctx: GradeContext,
                 *, serve_snap: str | None = None,
                 window_snap: str | None = None) -> dict:
    return _grade_row(imp, window_days, ctx, STATUS_UNGRADEABLE, reason,
                      serve_snap=serve_snap, window_snap=window_snap)


def _grade_row(imp: dict, window_days: int, ctx: GradeContext, status: str,
               reason: str | None, *, serve_snap=None, window_snap=None,
               give: "_SideResult | None" = None,
               recv: "_SideResult | None" = None) -> dict:
    """Assemble a grade row. Slice keys are COPIED from the impression — never
    re-derived — so a per-cell read is one GROUP BY and no read-time
    recomputation can drift from what was frozen at serve."""
    features = {}
    if imp.get("features_json"):
        try:
            parsed = json.loads(imp["features_json"])
            if isinstance(parsed, dict):
                features = parsed
        except (TypeError, ValueError):
            features = {}

    row = {
        "impression_id":    str(imp["impression_id"]),
        "window_days":      int(window_days),
        "grader_version":   GRADER_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "status":           status,
        "reason":           reason,
        "serve_snap_date":  serve_snap,
        "window_snap_date": window_snap,
        "give_serve_value":    None, "receive_serve_value": None,
        "give_delta":          None, "receive_delta":       None,
        "edge":                None, "edge_pct":            None,
        "baseline_edge":       None,   # RESERVED — shuffle baseline follow-on
        "coverage_give":    None, "coverage_receive": None,
        "has_picks":        None,
        "imputed_count":    None,
        "assets_detail_json": None,
        "league_id":        str(imp["league_id"]),
        "user_id":          str(imp["user_id"]),
        "scoring_format":   ctx.scoring_format,
        "served_at":        str(imp["served_at"]),
        "trade_hash":       imp.get("trade_hash"),
        "is_ghost":         imp.get("is_ghost"),
        "shape_bucket":     imp.get("shape_bucket"),
        "archetype":        imp.get("archetype"),
        # `basis` is a features_json SLICE key (taxonomy §2.2). Reading
        # features_json for slicing is allowed and reading it for valuation
        # is not — the two frozen VALUES beside it may be personal-basis
        # (`user_value_basis`, server.py:4159) and are never touched.
        "basis":            features.get("basis"),
        "model_arm":        imp.get("model_arm"),
        "policy_version":   imp.get("policy_version"),
        "graded_at":        _now_iso(),
    }
    if give is not None and recv is not None:
        detail = give.detail + recv.detail
        row.update({
            "give_serve_value":    round(give.serve_sum, 4),
            "receive_serve_value": round(recv.serve_sum, 4),
            "coverage_give":       round(give.coverage, 6),
            "coverage_receive":    round(recv.coverage, 6),
            "has_picks":           1 if (give.has_picks or recv.has_picks) else 0,
            "imputed_count":       give.imputed_n + recv.imputed_n,
            "assets_detail_json":  json.dumps(detail, separators=(",", ":")),
        })
    return row


def _side(asset_ids: list, league_id: str, ctx: GradeContext, side_name: str,
          serve_date: str, floor_serve_date: str | None) -> _SideResult:
    """Serve-endpoint half of one side: consensus sums, coverage, pick share.

    Weight convention (LLD §4.3, the round-2 B-B3 fix). Weights exist ONLY to
    make coverage and pick-share computable; they never touch edge:
        graded player     → its own serve consensus value (cv0)
        unresolved player → the format's serve-date pool FLOOR, flagged and
                            direction-neutral (its absence must not silently
                            shrink the denominator, which would let a
                            one-player-resolved package report coverage 1.0)
        pick              → RECEIPTS_PICK_WEIGHTS[round], frozen
    """
    serve_sum = 0.0
    denom = 0.0
    pick_weight_sum = 0.0
    graded_n = 0
    has_picks = False
    detail: list[dict] = []
    floor_serve = ctx.floor_at(floor_serve_date)

    for raw in asset_ids:
        aid = str(raw)
        rnd = pick_round(aid, league_id)
        if rnd is not None:
            has_picks = True
            w = pick_weight(rnd)
            pick_weight_sum += w
            denom += w
            detail.append({"id": aid, "side": side_name, "is_pick": True,
                           "cv0": None, "cv1": None, "imputed_floor": False})
            continue
        snap = _first_present(_serve_anchor_dates(serve_date, ctx.tol),
                              ctx.snapshot_dates)
        cv0 = ctx.value_at(aid, snap) if snap else None
        if cv0 is None:
            denom += floor_serve
            detail.append({"id": aid, "side": side_name, "is_pick": False,
                           "cv0": None, "cv1": None, "imputed_floor": False})
            continue
        serve_sum += cv0
        denom += cv0
        graded_n += 1
        detail.append({"id": aid, "side": side_name, "is_pick": False,
                       "cv0": round(cv0, 4), "cv1": None,
                       "imputed_floor": False})

    coverage = (serve_sum / denom) if denom > 0 else 0.0
    pick_share = (pick_weight_sum / denom) if denom > 0 else 0.0
    return _SideResult(serve_sum, 0.0, coverage, pick_share, detail,
                       graded_n, 0, has_picks, denom)


def _resolve_window(side: _SideResult, ctx: GradeContext,
                    window_snap_date: str) -> None:
    """Window-endpoint half: fill cv1 for every graded asset, imputing the
    pool floor for a player who was present at serve and is GONE at the
    window date (HLD D-8).

    That imputation is the anti-survivorship rule and it is not optional: a
    cratered player falls out of the snapshot pool, so marking him
    ungradeable would delete our WORST outcomes and flatter the engine. The
    imputation is flagged per asset and counted on the row.
    """
    window_sum = 0.0
    imputed = 0
    floor = ctx.floor_at(window_snap_date)
    for item in side.detail:
        if item["is_pick"] or item["cv0"] is None:
            continue
        cv1 = ctx.value_at(item["id"], window_snap_date)
        if cv1 is None:
            cv1 = floor
            item["imputed_floor"] = True
            imputed += 1
        item["cv1"] = round(float(cv1), 4)
        window_sum += float(cv1)
    side.window_sum = window_sum
    side.imputed_n = imputed


def grade_one(imp: dict, window_days: int, ctx: GradeContext) -> dict | None:
    """Grade one impression at one window. Pure: same inputs, same row.

    Returns a TERMINAL row, or None when the impression×window is still
    retry-pending (window endpoint not yet resolvable and the 14-day deadline
    has not passed). Retry-pending is never persisted — the queue is defined
    by the absence of a row, which is what makes the job idempotent.
    """
    serve_date = str(imp.get("served_at") or "")[:10]
    if len(serve_date) != 10 or serve_date[4] != "-":
        return _ungradeable(imp, window_days, "malformed_assets", ctx)

    # ── Terminal check 1: the assets bundle must be a two-list object ──
    try:
        assets = json.loads(imp.get("assets_json") or "")
    except (TypeError, ValueError):
        return _ungradeable(imp, window_days, "malformed_assets", ctx)
    if not isinstance(assets, dict):
        return _ungradeable(imp, window_days, "malformed_assets", ctx)
    give_ids = assets.get("give")
    recv_ids = assets.get("receive")
    if (not isinstance(give_ids, list) or not isinstance(recv_ids, list)
            or not give_ids or not recv_ids):
        # A 1x0 shouldn't exist; if one is seen it is malformed, not graded.
        return _ungradeable(imp, window_days, "malformed_assets", ctx)

    league_id = str(imp["league_id"])
    window_date = _shift(serve_date, int(window_days))

    # Format-wide serve anchor. Used for the unresolved-player floor weight,
    # and recorded on the row as the serve endpoint actually used. Falls back
    # past the tolerance for the FLOOR only (round-3 fold): no format history
    # at or before the serve date at all leaves it None, and the row then
    # terminates below with no players resolved.
    serve_snap = _first_present(_serve_anchor_dates(serve_date, ctx.tol),
                                ctx.snapshot_dates)
    floor_serve_date = serve_snap
    if floor_serve_date is None:
        earlier = [d for d in ctx.snapshot_dates if d <= serve_date]
        floor_serve_date = max(earlier) if earlier else None

    give = _side(give_ids, league_id, ctx, "give", serve_date, floor_serve_date)
    recv = _side(recv_ids, league_id, ctx, "receive", serve_date, floor_serve_date)

    # ── Terminal check 2: pick-majority ──
    # Picks are delta 0, so a side that is mostly picks has no measurable
    # movement to grade. Ordered BEFORE the snapshot checks deliberately:
    # a pick-heavy package is ungradeable for a reason that has nothing to do
    # with snapshot supply, and mislabelling it would corrupt the supply-
    # health read (`disclosure.excluded`).
    if (give.pick_share > ctx.pick_share_max
            or recv.pick_share > ctx.pick_share_max):
        return _ungradeable(imp, window_days, "pick_majority", ctx,
                            serve_snap=serve_snap)

    # ── Terminal check 3: zero graded players on EITHER side ──
    # Never grade one-sided. A one-empty-side grade would delete D-1's market
    # control and halve `edge_pct`'s midpoint — two silent distortions in one.
    if give.graded_n == 0 or recv.graded_n == 0:
        return _ungradeable(imp, window_days, "no_serve_snapshot", ctx,
                            serve_snap=serve_snap)

    # ── Terminal check 4: the window endpoint ──
    window_snap = _first_present(_window_anchor_dates(window_date, ctx.tol),
                                 ctx.snapshot_dates)
    if window_snap is None:
        if ctx.today < _shift(window_date, RETRY_GRACE_DAYS):
            return None                      # retry-pending: no row, requeue
        return _ungradeable(imp, window_days, "missing_snapshot", ctx,
                            serve_snap=serve_snap)

    _resolve_window(give, ctx, window_snap)
    _resolve_window(recv, ctx, window_snap)

    give_delta = give.window_sum - give.serve_sum
    recv_delta = recv.window_sum - recv.serve_sum
    edge = recv_delta - give_delta
    midpoint = (give.serve_sum + recv.serve_sum) / 2.0
    edge_pct = (edge / midpoint) if midpoint >= EDGE_PCT_MIN_MIDPOINT else None

    row = _grade_row(imp, window_days, ctx, STATUS_GRADED, None,
                     serve_snap=serve_snap, window_snap=window_snap,
                     give=give, recv=recv)
    row.update({
        "give_delta":    round(give_delta, 4),
        "receive_delta": round(recv_delta, 4),
        "edge":          round(edge, 4),
        "edge_pct":      (round(edge_pct, 6) if edge_pct is not None else None),
    })
    return row


# ---------------------------------------------------------------------------
# The run (LLD §4.1, §5.1)
# ---------------------------------------------------------------------------

def _serve_date_sets(cfg: dict, today: str,
                     min_serve_date: str) -> tuple[dict, dict]:
    """Per-format snapshot dates, and per-window resolvable serve dates.

    The queue predicate takes the UNION across formats (a superset — both
    formats are written by the same daily job, so they diverge only on a
    partial write). A candidate whose own format has not resolved yet is
    skipped in-loop without consuming the batch cap.
    """
    tol = int(_knob(cfg, "receipts_snap_tolerance_days", 3.0))
    fmt_dates = {fmt: set(db.load_value_snapshot_dates(fmt))
                 for fmt in db.SCORING_FORMATS}
    per_window: dict[int, list[str]] = {}
    for w in WINDOWS_DAYS:
        union: set[str] = set()
        for dates in fmt_dates.values():
            union |= set(resolvable_serve_dates(dates, w, tol, today,
                                                min_serve_date))
        per_window[w] = sorted(union)
    return fmt_dates, per_window


def remaining_resolvable(cfg: dict | None = None) -> int:
    """Eligible-and-resolvable-NOW work, retry-pending excluded. Computed
    before the daemon thread starts so every cron 202 carries an honest
    backlog figure (LLD §2.1)."""
    cfg = cfg if cfg is not None else db.get_config()
    today = _utc_today()
    min_serve = db.receipts_min_served_date()
    if not min_serve:
        return 0
    _, per_window = _serve_date_sets(cfg, today, min_serve)
    return sum(db.count_receipts_queue(w, GRADER_VERSION, per_window[w])
               for w in WINDOWS_DAYS)


def run_grading(trigger: str = "cron", batch: int | None = None) -> dict:
    """One grading run. Idempotent, single-flight, bounded by the batch cap.

    Writes a `kind='start'` ledger row at begin and a `kind='end'` row at
    completion; a crash or a Render free-instance spin-down mid-run leaves the
    start row unmatched, which IS the kill marker. Completed inserts stand
    (unique-keyed), the rest re-queue on the next trigger.
    """
    if not grading_enabled():
        return {"ok": True, "skipped": "flag", "graded": 0, "ungradeable": 0}

    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": "in_flight", "graded": 0,
                "ungradeable": 0}
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    cfg = db.get_config()
    batch_cap = int(batch) if batch else int(_knob(cfg, "receipts_grade_batch",
                                                   500.0))
    batch_cap = max(1, min(5000, batch_cap))
    db.insert_receipts_grade_run({
        "run_id": run_id, "kind": "start", "run_at": _now_iso(),
        "trigger": trigger, "batch_cap": batch_cap,
        "grader_version": GRADER_VERSION,
    })

    graded = ungradeable = errors = 0
    reason_counts: dict[str, int] = {}
    try:
        graded, ungradeable, errors, reason_counts = _drain(cfg, batch_cap)
    except Exception as e:                                  # pragma: no cover
        log.warning("receipts: run %s failed: %s", run_id, e)
        errors += 1
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        terminal = graded + ungradeable
        try:
            left = remaining_resolvable(cfg)
        except Exception:                                   # pragma: no cover
            left = None
        db.insert_receipts_grade_run({
            "run_id": run_id, "kind": "end", "run_at": _now_iso(),
            "trigger": trigger, "duration_ms": duration_ms,
            "graded": graded, "ungradeable": ungradeable,
            "reason_counts_json": json.dumps(reason_counts,
                                             separators=(",", ":")),
            "batch_cap": batch_cap,
            "cap_hit": 1 if terminal >= batch_cap else 0,
            "remaining_resolvable": left,
            "grader_version": GRADER_VERSION,
        })
        _RUN_LOCK.release()

    _emit_run_event(graded, ungradeable, terminal >= batch_cap, duration_ms,
                    trigger)
    return {"ok": True, "graded": graded, "ungradeable": ungradeable,
            "errors": errors, "cap_hit": terminal >= batch_cap,
            "duration_ms": duration_ms, "reason_counts": reason_counts,
            "remaining_resolvable": left, "run_id": run_id}


def _drain(cfg: dict, batch_cap: int) -> tuple[int, int, int, dict]:
    """Pull candidates window by window until `batch_cap` TERMINAL rows are
    written or the resolvable queue is empty."""
    today = _utc_today()
    min_serve = db.receipts_min_served_date()
    graded = ungradeable = errors = 0
    reason_counts: dict[str, int] = {}
    if not min_serve:
        return 0, 0, 0, reason_counts

    fmt_dates, per_window = _serve_date_sets(cfg, today, min_serve)
    tol = int(_knob(cfg, "receipts_snap_tolerance_days", 3.0))
    pick_share_max = _knob(cfg, "receipts_pick_share_max", 0.5)

    for window_days in WINDOWS_DAYS:
        serve_dates = per_window[window_days]
        if not serve_dates:
            continue
        seen: set[str] = set()
        while graded + ungradeable < batch_cap:
            need = batch_cap - (graded + ungradeable)
            # Stream PAST the LIMIT: skipped (still retry-pending for their
            # own format) rows stay queued, so the fetch window has to grow
            # past them or the loop would re-read the same head forever.
            candidates = db.load_receipts_queue(
                window_days, GRADER_VERSION, serve_dates, need + len(seen))
            fresh = [c for c in candidates
                     if str(c["impression_id"]) not in seen]
            if not fresh:
                break
            rows, skipped, errs = _grade_batch(fresh[:need + len(seen)],
                                               window_days, fmt_dates, tol,
                                               pick_share_max, today, need)
            errors += errs
            seen.update(skipped)
            for r in rows:
                seen.add(r["impression_id"])
            if rows:
                db.insert_receipts_grades(rows)
                for r in rows:
                    if r["status"] == STATUS_GRADED:
                        graded += 1
                    else:
                        ungradeable += 1
                        reason_counts[r["reason"]] = (
                            reason_counts.get(r["reason"], 0) + 1)
            elif not skipped:
                break
    return graded, ungradeable, errors, reason_counts


def _grade_batch(candidates: list[dict], window_days: int, fmt_dates: dict,
                 tol: int, pick_share_max: float, today: str,
                 need: int) -> tuple[list[dict], set[str], int]:
    """Grade a candidate slice with ONE snapshot prefetch per format."""
    scoring = db.load_league_scoring_map([c["league_id"] for c in candidates])
    by_format: dict[str, list[dict]] = {}
    rows: list[dict] = []
    skipped: set[str] = set()
    errors = 0

    for c in candidates:
        fmt = scoring.get(str(c["league_id"]))
        if fmt is None:
            # Unknown league — the format is unresolvable, so the row can
            # never be graded. Terminal, not retry-pending.
            ctx = GradeContext(None, {}, set(), {}, tol, pick_share_max, today)
            rows.append(_ungradeable(c, window_days, "format_missing", ctx))
            continue
        by_format.setdefault(fmt, []).append(c)

    for fmt, group in by_format.items():
        dates = fmt_dates.get(fmt, set())
        player_ids, endpoint_dates = set(), set()
        for c in group:
            serve_date = str(c.get("served_at") or "")[:10]
            if len(serve_date) != 10:
                continue
            window_date = _shift(serve_date, window_days)
            endpoint_dates.update(_serve_anchor_dates(serve_date, tol))
            endpoint_dates.update(_window_anchor_dates(window_date, tol))
            try:
                assets = json.loads(c.get("assets_json") or "")
            except (TypeError, ValueError):
                continue
            if not isinstance(assets, dict):
                continue
            for side in ("give", "receive"):
                for a in (assets.get(side) or []):
                    if pick_round(str(a), str(c["league_id"])) is None:
                        player_ids.add(str(a))
        wanted = sorted(d for d in endpoint_dates if d in dates)
        snapshots = db.load_value_snapshots_for(
            fmt, sorted(player_ids), wanted[0], wanted[-1]) if wanted else {}
        floors = db.load_value_snapshot_floors(fmt, wanted)
        ctx = GradeContext(fmt, snapshots, dates, floors, tol, pick_share_max,
                           today)
        for c in group:
            if len(rows) >= need:
                break
            try:
                row = grade_one(c, window_days, ctx)
            except Exception as e:
                # One bad row logs and continues; it stays queued and the run
                # ledger counts the error (LLD §5.2).
                log.warning("receipts: grading %s w=%s failed: %s",
                            c.get("impression_id"), window_days, e)
                skipped.add(str(c["impression_id"]))
                errors += 1
                continue
            if row is None:
                skipped.add(str(c["impression_id"]))   # retry-pending
                continue
            rows.append(row)
    return rows, skipped, errors


def _emit_run_event(graded: int, ungradeable: int, cap_hit: bool,
                    duration_ms: int, trigger: str) -> None:
    """Server-fired `receipts_grade_run` (PRD DR-9). Best-effort: analytics
    must never break the job."""
    try:
        db.record_event(
            "system:receipts", "receipts_grade_run",
            props={"graded": graded, "ungradeable": ungradeable,
                   "cap_hit": bool(cap_hit), "duration_ms": duration_ms,
                   "trigger": trigger},
        )
    except Exception as e:                                  # pragma: no cover
        log.warning("receipts: run event failed (continuing): %s", e)


# ---------------------------------------------------------------------------
# Read side — user surface (LLD §2.2)
# ---------------------------------------------------------------------------

METHODOLOGY_LINE = (
    "Graded against market consensus at serve time; picks held constant; "
    "predictions locked when shown."
)


def _dedup_earliest(rows: list[dict]) -> tuple[list[dict], int]:
    """Collapse re-serves of the same card, keeping the EARLIEST serve.

    A deck regeneration can re-serve an identical trade; counting it twice
    would let one call carry two votes. Key is `(league_id, trade_hash)`,
    matching the card identity `_deck_trade_hash` mints at serve.
    """
    best: dict[tuple, dict] = {}
    dropped = 0
    for r in rows:
        key = (r.get("league_id"), r.get("trade_hash") or r.get("impression_id"))
        prev = best.get(key)
        if prev is None:
            best[key] = r
        elif str(r.get("served_at")) < str(prev.get("served_at")):
            best[key] = r
            dropped += 1
        else:
            dropped += 1
    return list(best.values()), dropped


def _coverage_ok(row: dict, coverage_min: float) -> bool:
    """The user-surface coverage filter: `min(give, receive) ≥ knob`. Compared
    on the MINIMUM because a package graded on one well-covered side and one
    barely-covered side is not a swap measurement."""
    cg = row.get("coverage_give")
    cr = row.get("coverage_receive")
    if cg is None or cr is None:
        return False
    return min(float(cg), float(cr)) >= coverage_min


def league_receipts(user_id: str, league_id: str,
                    name_lookup=None) -> dict:
    """The viewer's own graded track record in one league — ONE payload
    carrying ALL THREE windows, which is what makes cherry-picking a window
    structurally impossible rather than merely discouraged.

    Viewer-scoped by WHERE clause; ghost rows are filtered again here as
    defense in depth even though the queue predicate means none can exist
    (operator ruling 2026-08-21). `name_lookup` resolves display names at
    read time and is DISPLAY-ONLY — no name ever enters the math.
    """
    cfg = db.get_config()
    min_n = int(_knob(cfg, "receipts_min_n", 10.0))
    coverage_min = _knob(cfg, "receipts_coverage_min", 0.5)

    version = max_grader_version(db.load_receipts_grader_versions())
    all_rows = db.load_receipts_grades(user_id=user_id, league_id=league_id,
                                       grader_version=version) if version else []
    all_rows = [r for r in all_rows if not r.get("is_ghost")]

    cohort = db.receipts_impression_cohort(user_id, league_id)
    scoring = db.load_league_scoring_map([league_id]).get(str(league_id))

    # Group by impression, then dedup by card identity ONCE — so every window
    # is computed over the same card set and the three windows can never
    # disagree about which trades they describe.
    by_impression: dict[str, dict] = {}
    for r in all_rows:
        by_impression.setdefault(str(r["impression_id"]), {})[
            int(r["window_days"])] = r
    spine = []
    for imp_id, windows in by_impression.items():
        any_row = next(iter(windows.values()))
        spine.append({"impression_id": imp_id,
                      "league_id": any_row.get("league_id"),
                      "trade_hash": any_row.get("trade_hash"),
                      "served_at": any_row.get("served_at"),
                      "shape_bucket": any_row.get("shape_bucket"),
                      "windows": windows})
    spine, deduped = _dedup_earliest(spine)
    spine.sort(key=lambda s: str(s.get("served_at") or ""), reverse=True)

    excluded = {"low_coverage": 0, "pick_majority": 0, "missing_snapshot": 0,
                "no_serve_snapshot": 0, "malformed_assets": 0,
                "format_missing": 0}
    windows_out = []
    displayed: dict[int, list[dict]] = {}
    graded_n: dict[str, int] = {}
    ties = 0
    null_edge_pct = 0
    touched = 0

    for w in WINDOWS_DAYS:
        rows = []
        for s in spine:
            r = s["windows"].get(w)
            if r is None:
                continue
            touched += 1
            if r["status"] != STATUS_GRADED:
                reason = r.get("reason")
                if reason in excluded:
                    excluded[reason] += 1
                continue
            if not _coverage_ok(r, coverage_min):
                excluded["low_coverage"] += 1
                continue
            rows.append(r)
        displayed[w] = rows
        graded_n[str(w)] = len(rows)
        # n IS the displayed row count — post-dedup, post-coverage — and every
        # statistic below is computed over exactly these rows (LLD §2.2).
        n = len(rows)
        if n == 0:
            windows_out.append({"window_days": w, "n": 0, "status": "pending"})
            continue
        wins = sum(1 for r in rows if (r.get("edge") or 0.0) > 0)
        if w == HEADLINE_WINDOW_DAYS:
            ties = sum(1 for r in rows if (r.get("edge") or 0.0) == 0)
            null_edge_pct = sum(1 for r in rows if r.get("edge_pct") is None)
        if n < min_n:
            windows_out.append({"window_days": w, "n": n,
                                "status": "insufficient"})
            continue
        windows_out.append({
            "window_days": w, "n": n, "status": "ready",
            "win_share": round(wins / n, 4),
            "median_edge_pct": _median([r.get("edge_pct") for r in rows]),
        })

    head_rows = displayed.get(HEADLINE_WINDOW_DAYS, [])
    ranked = sorted((r for r in head_rows if r.get("edge_pct") is not None),
                    key=lambda r: float(r["edge_pct"]))
    # Best call and worst call are max / min `edge_pct` at the headline window
    # among the DISPLAYED rows — symmetric by construction. Neither is ever
    # shown without the other (PRD §4.4).
    best_call = ranked[-1]["impression_id"] if ranked else None
    worst_call = ranked[0]["impression_id"] if ranked else None

    total_graded = sum(len(v) for v in displayed.values())
    gradeable_share = round(total_graded / touched, 4) if touched else None

    return {
        "league_id": str(league_id),
        "scoring_format": scoring,
        "grader_version": version,
        "maturity": {
            "tracked_n": cohort["tracked"],
            "first_tracked_at": cohort["first_tracked_at"],
            "graded_n": graded_n,
            "min_n": min_n,
            "mature": {str(w): graded_n.get(str(w), 0) >= min_n
                       for w in WINDOWS_DAYS},
        },
        "windows": windows_out,
        "headline_window_days": HEADLINE_WINDOW_DAYS,
        "best_call_impression_id": best_call,
        "worst_call_impression_id": worst_call,
        "rows": [_render_row(s, name_lookup) for s in spine],
        "disclosure": {
            "gradeable_share": gradeable_share,
            "ties": ties,
            "null_edge_pct": null_edge_pct,
            "deduped_reserves": deduped,
            "pre_telemetry": cohort["pre_telemetry"],
            "excluded": excluded,
            "methodology": METHODOLOGY_LINE,
        },
    }


def _render_row(spine_row: dict, name_lookup=None) -> dict:
    """One trade, both sides, every window — the ONLY row format there is.

    A loss renders through exactly this shape, with exactly these fields, as a
    win does. There is no "highlight" variant to reach for later.
    """
    windows = spine_row["windows"]
    any_row = next(iter(windows.values()))
    detail = []
    if any_row.get("assets_detail_json"):
        try:
            detail = json.loads(any_row["assets_detail_json"]) or []
        except (TypeError, ValueError):
            detail = []

    def _assets(side: str) -> list[dict]:
        out = []
        for a in detail:
            if a.get("side") != side:
                continue
            name = None
            if name_lookup is not None and not a.get("is_pick"):
                try:
                    name = name_lookup(a["id"])
                except Exception:
                    name = None
            out.append({"id": a["id"], "name": name,
                        "is_pick": bool(a.get("is_pick"))})
        return out

    per_window = {}
    for w in WINDOWS_DAYS:
        r = windows.get(w)
        if r is None or r["status"] != STATUS_GRADED:
            per_window[str(w)] = None
            continue
        per_window[str(w)] = {
            "give_delta": r.get("give_delta"),
            "receive_delta": r.get("receive_delta"),
            "edge": r.get("edge"),
            "edge_pct": r.get("edge_pct"),
            "imputed": bool(r.get("imputed_count")),
        }

    return {
        "impression_id": spine_row["impression_id"],
        "served_at": spine_row.get("served_at"),
        "shape_bucket": spine_row.get("shape_bucket"),
        "give": {"assets": _assets("give"),
                 "serve_value": any_row.get("give_serve_value")},
        "receive": {"assets": _assets("receive"),
                    "serve_value": any_row.get("receive_serve_value")},
        "windows": per_window,
        "has_picks": bool(any_row.get("has_picks")),
        "coverage": {"give": any_row.get("coverage_give"),
                     "receive": any_row.get("coverage_receive")},
    }


# ---------------------------------------------------------------------------
# Read side — internal per-cell readout (LLD §2.3)
# ---------------------------------------------------------------------------

#: Cells whose gradeable share falls below this are FLAGGED in the readout —
#: a selection-effect warning attached to the number, not a filter applied
#: behind it (PLAN §3.6).
LOW_SHARE_FLAG = 0.70


def admin_metrics(*, window: int | None = None,
                  shape_bucket: str | None = None,
                  basis: str | None = None,
                  model_arm: str | None = None,
                  league_id: str | None = None,
                  dedup: bool = True) -> dict:
    """Per-taxonomy-cell accuracy with honest intervals.

    Admin cells do NOT apply the user-surface coverage filter — they carry
    every graded row and report `gradeable_share` / `flag_low_share` instead.
    The `n == rows used` invariant still holds, per surface, over that
    surface's own row set.
    """
    version = max_grader_version(db.load_receipts_grader_versions())
    rows = db.load_receipts_grades(
        grader_version=version, window_days=window, shape_bucket=shape_bucket,
        basis=basis, model_arm=model_arm, league_id=league_id) if version else []
    rows = [r for r in rows if not r.get("is_ghost")]

    if dedup:
        spine, _ = _dedup_earliest(_dedup_keys(rows))
        rows = [s["row"] for s in spine]

    cells: dict[tuple, dict] = {}
    for r in rows:
        key = (int(r["window_days"]), r.get("shape_bucket"), r.get("basis"),
               r.get("model_arm"))
        cell = cells.setdefault(key, {"graded": [], "touched": 0})
        cell["touched"] += 1
        if r["status"] == STATUS_GRADED:
            cell["graded"].append(r)

    out = []
    for (w, shape, bas, arm), cell in sorted(
            cells.items(), key=lambda kv: (kv[0][0], str(kv[0][1]),
                                           str(kv[0][2]), str(kv[0][3]))):
        graded = cell["graded"]
        n = len(graded)
        wins = sum(1 for r in graded if (r.get("edge") or 0.0) > 0)
        low, high = wilson_interval(wins, n) if n else (None, None)
        share = round(n / cell["touched"], 4) if cell["touched"] else None
        out.append({
            "window_days": w, "shape_bucket": shape, "basis": bas,
            "model_arm": arm, "n": n,
            "win_share": round(wins / n, 4) if n else None,
            "wilson_low": round(low, 4) if low is not None else None,
            "wilson_high": round(high, 4) if high is not None else None,
            "median_edge_pct": _median([r.get("edge_pct") for r in graded]),
            "ties": sum(1 for r in graded if (r.get("edge") or 0.0) == 0),
            "gradeable_share": share,
            "flag_low_share": bool(share is not None and share < LOW_SHARE_FLAG),
        })

    return {
        "grader_version": version,
        "taxonomy_version": TAXONOMY_VERSION,
        "dedup": bool(dedup),
        "cells": out,
        "effective_window": _effective_window(rows),
        "runs": db.load_receipts_grade_runs(limit=10),
        "note": (None if dedup else
                 "dedup=0 — re-serves of one card are included; rows within a "
                 "card identity are correlated and n overstates independence."),
    }


def _dedup_keys(rows: list[dict]) -> list[dict]:
    """Wrap grade rows for `_dedup_earliest`, keyed per WINDOW so deduping
    never collapses the three windows of one card into one row."""
    return [{"league_id": (r.get("league_id"), int(r["window_days"])),
             "trade_hash": r.get("trade_hash") or r.get("impression_id"),
             "served_at": r.get("served_at"), "row": r} for r in rows]


def _effective_window(rows: list[dict]) -> dict:
    """Distribution of `window_snap_date − serve_snap_date`.

    A nominal 14-day window really spans roughly 11–20 days once the anchors
    land (serve resolves nearest-≤ up to 3 days earlier, window resolves ±3),
    and the operator should read the number knowing that.
    """
    spans: dict[int, list[int]] = {}
    for r in rows:
        s, e = r.get("serve_snap_date"), r.get("window_snap_date")
        if not s or not e:
            continue
        try:
            days = (datetime.strptime(e, "%Y-%m-%d")
                    - datetime.strptime(s, "%Y-%m-%d")).days
        except ValueError:
            continue
        spans.setdefault(int(r["window_days"]), []).append(days)
    return {str(w): {"n": len(v), "min": min(v), "max": max(v),
                     "median": _median([float(x) for x in v])}
            for w, v in sorted(spans.items()) if v}
