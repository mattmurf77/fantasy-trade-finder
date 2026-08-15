"""P0-4 (B6) — nightly flag aggregation → bounded class demotion (D11).

docs/plans/trade-relevance-engine/lld.md §4.6, hld.md D11, PRD R8.

WHAT THIS IS. Once a night, count how often each *card class* was actually
looked at and how often it was explicitly flagged "not interested", shrink the
raw rate toward the global rate (empirical Bayes), and turn that into a
`demotion` multiplier in `deck_class_stats`. Serving multiplies a card's
ordering key by its class's multiplier. **That is the entire blast radius: a
reorder of cards the engine already admitted.**

FIVE PROPERTIES THAT MUST NEVER BE LOST
---------------------------------------
1. **Never a gate** (D11). The multiplier is clamped to
   [`class_demotion_floor` (0.5), 1.0]. The worst class in the product still
   appears in decks; it just sorts lower. A human reads the operator report
   and decides whether any class deserves a real, hand-authored gate in
   `_consider`. Gates stay editorial.
2. **No evidence ⇒ no penalty.** A class with fewer than
   `class_demotion_min_views` (200) exposures in the window gets demotion
   EXACTLY 1.0. "3 flags on 40 exposures" is noise, and noise must not demote
   an archetype product-wide. The row is still written, so the operator report
   can show the class and its n.
3. **The join key.** `bad_trade_flags` carries neither `impression_id` nor
   `trade_hash` (`database.py:917`), so it CANNOT be the numerator. Attribution
   rides the impression-keyed `not_interested` `deck_outcomes` row that the
   flag route writes beside the flag (`server.py:10777`).
4. **Fail-soft by data layout.** Rows are written for `stat_date = today` and
   consumers read `MAX(stat_date)`. A pass that dies writes nothing, so
   yesterday's rows stay live. There is no partial-state to repair.
5. **Bounded work.** The group-by keys on `receive_value_band`, which lives
   inside `features_json` with no SQL column, so the grouping is a Python-side
   JSON parse. It is therefore chunked (keyset pagination, `CHUNK_ROWS` at a
   time) and hard-capped at `MAX_WINDOW_IMPRESSIONS`. See the ceiling note
   below — truncation is safe *because* `impression_id` is a uuid4 hex.

THE ROW CEILING (PRD R8 pre-build check 2)
------------------------------------------
The 60s pass budget is a hope, not a design. At 10× today's volume a 30-day
window is a large scan, so this pass refuses to become unbounded:

  * `CHUNK_ROWS` (2000) impressions per SQL page, keyset-paginated on
    `impression_id` — no OFFSET, no held cursor, no long transaction.
  * `MAX_WINDOW_IMPRESSIONS` (500_000) is the hard stop. Beyond it the pass
    stops reading and reports `truncated: True` in its result and the log.
  * Truncation is UNBIASED and CONSERVATIVE: `impression_id` is a uuid4 hex,
    so ordering by it is ordering by noise — the prefix read is a uniform
    random sample of the window. Rates are therefore unaffected in
    expectation; only n shrinks, which pushes classes *below* the
    `class_demotion_min_views` gate and toward 1.0. A truncated run under-
    demotes. It never over-demotes.

No Flask imports (D12).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from ..batch import batch_write
from ..config import resolve

__all__ = [
    "run_pass", "aggregate", "demotion_for", "class_key",
    "UNKNOWN", "WINDOW_DAYS", "RETENTION_DAYS", "CHUNK_ROWS",
    "MAX_WINDOW_IMPRESSIONS", "EB_PRIOR_STRENGTH",
    "DEFAULT_FLOOR", "DEFAULT_MIN_VIEWS",
]

log = logging.getLogger(__name__)

PASS_NAME = "flag_aggregation"

WINDOW_DAYS    = 30      # trailing exposure window
RETENTION_DAYS = 30      # stat_date history kept for the operator report
CHUNK_ROWS     = 2000    # impressions per keyset page
MAX_WINDOW_IMPRESSIONS = 500_000     # hard ceiling; see module docstring

# EB prior strength: `(flags + k·ρ) / (views + k)` (LLD §4.6). k=50 means a
# class needs ~50 exposures before its own data outweighs the global rate —
# deliberately below `class_demotion_min_views` so that by the time a class is
# eligible to be demoted at all, the shrinkage has already stopped dominating.
EB_PRIOR_STRENGTH = 50.0

DEFAULT_FLOOR     = 0.5      # model_config `class_demotion_floor`
DEFAULT_MIN_VIEWS = 200.0    # model_config `class_demotion_min_views`

# `deck_class_stats.archetype` / `.value_band` are NOT NULL, but an impression
# may legitimately carry neither (no lane, no receive_value). One sentinel,
# used identically by this pass and by the serving lookup, so a NULL-archetype
# card is a real class rather than a silently dropped one.
UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------

def demotion_for(flags: int, views: int, rho: float, *,
                 floor: float, min_views: float,
                 k: float = EB_PRIOR_STRENGTH) -> tuple[float, float | None]:
    """(demotion, shrunk_rate) for one class. Pure; no I/O.

    Returns demotion 1.0 in every no-evidence case:
      * `views < min_views` — property 2, the noise floor;
      * `rho <= 0` — NOBODY flagged anything in the window, so there is no
        signal to normalize against. Without this branch `rho/shrunk` is 0/0
        and every class on the platform would clamp to the floor. That is the
        single most destructive bug this function can have.
      * `shrunk <= 0` — same division hazard from the other side.

    Otherwise `clamp(rho / shrunk, floor, 1.0)`: a class flagged at exactly the
    global rate rides 1.0; a class flagged at 2× the global rate lands near
    0.5; the clamp keeps it in the deck either way.
    """
    floor = min(1.0, max(0.0, float(floor)))
    if views <= 0:
        return 1.0, None
    shrunk = (float(flags) + k * float(rho)) / (float(views) + k)
    if views < min_views:
        # Below the evidence bar. The shrunk rate is still reported (the
        # operator report shows it beside n), but the multiplier is exactly
        # 1.0 — not "nearly 1.0", not "clamped to 1.0".
        return 1.0, shrunk
    if rho <= 0 or shrunk <= 0:
        return 1.0, shrunk
    return min(1.0, max(floor, float(rho) / shrunk)), shrunk


def class_key(archetype, shape_bucket, value_band) -> tuple[str, str, str]:
    """The ONE (archetype, shape_bucket, value_band) normalization.

    Both writers of this key — this pass and `server._deck_class_key` — call
    it. A second normalization would drift and the serving lookup would miss
    every class with a NULL component.
    """
    return (
        str(archetype) if archetype else UNKNOWN,
        str(shape_bucket) if shape_bucket else UNKNOWN,
        str(value_band) if value_band else UNKNOWN,
    )


# ---------------------------------------------------------------------------
# The chunked scan
# ---------------------------------------------------------------------------

# Exposures = impressions with a `viewed` outcome (served ≠ viewed), on the
# deck surface, in the trailing window. Flags = the impression-keyed
# `not_interested` outcome on the SAME impression, so `flags <= exposures`
# holds by construction and a "rate" is a rate.
#
# Surface: `deck_impressions` has no `surface` column yet — it arrives with
# B11/P1-3 — and today every row in the table is written by
# `server._log_deck_signal_impressions` from a deck-generation job, so the
# whole table IS the deck surface. B11 adds `AND i.surface = 'deck'` here.
#
# Dialect notes: `substr(...,1,10)` compares date PREFIXES against YYYY-MM-DD
# binds (the analytics_queries house rule — never a 'Z' instant against
# stored '+00:00' text), and works on SQLite and Postgres alike. The GROUP BY
# lists every bare column; `features_json` rides `MAX()` because each group is
# exactly one `deck_impressions` row (impression_id is that table's PK), so
# MAX is an identity here and we avoid grouping on a Text blob.
_SCAN_SQL = text("""
    SELECT i.impression_id        AS impression_id,
           i.archetype            AS archetype,
           i.shape_bucket         AS shape_bucket,
           MAX(i.features_json)   AS features_json,
           MAX(CASE WHEN o.action = 'viewed'         THEN 1 ELSE 0 END) AS viewed,
           MAX(CASE WHEN o.action = 'not_interested' THEN 1 ELSE 0 END) AS flagged
      FROM deck_impressions i
      JOIN deck_outcomes    o ON o.impression_id = i.impression_id
     WHERE substr(i.served_at, 1, 10) >= :since_day
       AND i.impression_id > :cursor
       AND o.action IN ('viewed', 'not_interested')
     GROUP BY i.impression_id, i.archetype, i.shape_bucket
     ORDER BY i.impression_id
     LIMIT :chunk
""")


def _receive_value_band(features_json) -> str | None:
    """`receive_value_band` out of the frozen features blob.

    Chosen over the give band (LLD §4.6) to match the flagger's receive side:
    a user flags "this is a bad trade" about what they are being offered.
    Malformed/absent JSON ⇒ None ⇒ the `unknown` class, never an exception —
    one bad row must not kill the night's aggregation.
    """
    if not features_json:
        return None
    try:
        feats = json.loads(features_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(feats, dict):
        return None
    band = feats.get("receive_value_band")
    return str(band) if band else None


def aggregate(*, since_day: str, engine=None,
              chunk_rows: int = CHUNK_ROWS,
              max_rows: int = MAX_WINDOW_IMPRESSIONS) -> dict:
    """Scan the window in keyset-paginated chunks; return raw class counts.

    Returns {"counts": {(arch, shape, band): [views, flags]},
             "views": int, "flags": int, "scanned": int,
             "flags_unviewed": int, "truncated": bool}.

    Pure counting — no shrinkage, no clamping, no writes. `engine` defaults to
    the product engine, resolved through the module object so tests can patch
    `backend.database.engine` the way the rest of the suite does.
    """
    if engine is None:
        from ... import database as db     # noqa: F401 — late import (D12)
        engine = db.engine

    counts: dict[tuple[str, str, str], list[int]] = {}
    cursor = ""
    scanned = 0
    total_views = 0
    total_flags = 0
    flags_unviewed = 0
    truncated = False

    while True:
        remaining = max_rows - scanned
        if remaining <= 0:
            truncated = True
            break
        limit = min(chunk_rows, remaining)
        # One short read per chunk — never one long-lived cursor. The pass
        # shares the SQLite file with the request path (HLD §2.2).
        with engine.connect() as conn:
            rows = conn.execute(_SCAN_SQL, {
                "since_day": since_day, "cursor": cursor, "chunk": limit,
            }).fetchall()
        if not rows:
            break
        for r in rows:
            cursor = r.impression_id
            scanned += 1
            flagged = bool(r.flagged)
            if not r.viewed:
                # Flagged but never fronted for ≥500ms. Not an exposure, so
                # not a denominator — and counting it as a numerator would
                # make "rate" exceed 1. Reported as an honesty counter.
                if flagged:
                    flags_unviewed += 1
                continue
            key = class_key(r.archetype, r.shape_bucket,
                            _receive_value_band(r.features_json))
            slot = counts.get(key)
            if slot is None:
                slot = counts[key] = [0, 0]
            slot[0] += 1
            total_views += 1
            if flagged:
                slot[1] += 1
                total_flags += 1
        if len(rows) < limit:
            break

    return {"counts": counts, "views": total_views, "flags": total_flags,
            "scanned": scanned, "flags_unviewed": flags_unviewed,
            "truncated": truncated}


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------

def _prune(engine, cutoff_day: str) -> int:
    """Drop `deck_class_stats` rows older than the retention horizon."""
    from ... import database as db
    stmt = db.deck_class_stats_table.delete().where(
        db.deck_class_stats_table.c.stat_date < cutoff_day)
    with engine.begin() as conn:
        return int(conn.execute(stmt).rowcount or 0)


def run_pass(ctx) -> dict:
    """`registry.PassSpec.fn` entry point. One `stat_date` worth of rows.

    Writes EVERY class it saw, not just the demoted ones: the operator report
    needs the un-demoted classes and their n to judge whether a demotion is
    real, and a missing class reads as 1.0 at serve time anyway.
    """
    from ... import database as db

    now: datetime = getattr(ctx, "now", None) or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stat_date = now.strftime("%Y-%m-%d")
    since_day = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

    floor     = resolve("class_demotion_floor", DEFAULT_FLOOR)
    min_views = resolve("class_demotion_min_views", DEFAULT_MIN_VIEWS)

    agg = aggregate(since_day=since_day, engine=db.engine)
    counts  = agg["counts"]
    rho     = (agg["flags"] / agg["views"]) if agg["views"] else 0.0
    computed_at = now.isoformat()

    rows: list[dict] = []
    demoted = 0
    for (arch, shape, band), (views, flags) in sorted(counts.items()):
        demotion, shrunk = demotion_for(flags, views, rho,
                                        floor=floor, min_views=min_views)
        if demotion < 1.0:
            demoted += 1
        rows.append({
            "archetype":        arch,
            "shape_bucket":     shape,
            "value_band":       band,
            "exposures":        views,
            "flags":            flags,
            "flag_rate_shrunk": shrunk,
            "demotion":         demotion,
            "computed_at":      computed_at,
            "stat_date":        stat_date,
        })

    written = 0
    if rows:
        # Upsert, not insert: a same-day re-run (double-POST, stale-claim
        # recovery, same-day retry) must overwrite today's rows, never
        # duplicate-key its way to an error or leave half a day behind.
        written = batch_write(
            db.deck_class_stats_table, rows, mode="upsert",
            upsert_keys=("archetype", "shape_bucket", "value_band", "stat_date"),
        )

    pruned = 0
    try:
        cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        pruned = _prune(db.engine, cutoff)
    except Exception as e:      # retention is hygiene, not correctness
        log.warning("%s: prune failed (continuing): %s", PASS_NAME, e)

    result = {
        "items":          len(rows),
        "written":        written,
        "classes":        len(rows),
        "demoted":        demoted,
        "exposures":      agg["views"],
        "flags":          agg["flags"],
        "flags_unviewed": agg["flags_unviewed"],
        "global_rate":    rho,
        "scanned":        agg["scanned"],
        "truncated":      agg["truncated"],
        "pruned":         pruned,
        "stat_date":      stat_date,
    }
    log.info("%s: %s", PASS_NAME, result)
    if agg["truncated"]:
        log.warning("%s: hit the %d-impression window ceiling — rates are a "
                    "uniform sample (uuid4 ordering), n is understated, so "
                    "demotion is conservative", PASS_NAME, MAX_WINDOW_IMPRESSIONS)
    return result
