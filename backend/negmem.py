"""negmem.py — negative-results memory (flag `trade.negmem`, default OFF).

M1: per-(league, partner, reason-family) soft down-weight built from reasoned
rejections; M2: the acceptance_stats feed for trade_gen_v2.acceptance_prior.
Derive-on-read, zero tables (NG6). LEAF: imports database (+ sqlalchemy.text
for the dual-dialect fetch) only — never server, trade_service, any engine
module, and never sleeper_roster. Engines `import negmem` and call attributes
(T1) — the map moves exclusively as an argument (D-3). Identity: M1 evidence
partner ids are ALREADY canonical league ids (features_json.partner_user_id ==
card.target_user_id == LeagueMember.user_id, ADR-012) — no mapping. M2's
account-side ids get an identity-default `owner_alias` and a counted drop
(DE-5). PRD/HLD: docs/plans/negative-results-memory/. Admission is the ONE
closed list (R1): the fetch-SQL + Python-predicate pair below are the only
implementation — builder, readout, and RFPS all go through
_admit_events() / load_admitted_events().

Spec: docs/plans/negative-results-memory/LLD.md (FINAL). Section references in
this file point at that document.

**No module-global map, ever** (T1). The only module-level mutable state is the
60s allowlist cache (§4.1), which holds a set of league-id strings.

This module holds **zero knob default literals** (DE-3): every tuning value
arrives as a `build_map` argument. `negmem_readout(knobs=None)` is the one
exception path and it reads the SEEDED model_config table, never a copy.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

from sqlalchemy import text

from . import database as _db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants (§2) — semantics, not tuning. Tuning lives in model_config.
# ---------------------------------------------------------------------------

NEGMEM_VER = 1                      # stamp schema version; bump on any change
                                    # to admission, decay, or netting semantics
NEGMEM_CLEAN_EPOCH_DAY = "2026-08-20"        # R1(e); subsumes D-091 (ends 08-19)
NEGMEM_ADMITTED_FAMILIES = ("value", "fit")  # R2 — closed set
NEGMEM_HORIZON_HALFLIVES = 4.0               # HLD §3.1 read horizon
NEGMEM_M2_LOOKBACK_DAYS = 180                # PRD R5 M2 window; INDEPENDENT of
                                             # halflife_days, applied in the
                                             # Python fold (§5.4), not in SQL
NEGMEM_BUILD_BUDGET_MS = 250.0               # S6 absolute ceiling (HLD §3.1)
NEGMEM_DEGRADE_MS = 2.0 * NEGMEM_BUILD_BUDGET_MS   # slow-but-valid ⇒ degraded

_DECISION_ACTIONS = frozenset({"like", "pass", "not_interested", "propose"})
_REJECTION_ACTIONS = frozenset({"pass", "not_interested"})
_EMPTY_ALIAS: Mapping[str, str] = MappingProxyType({})   # identity `owner_alias`
                                                         # default (DE-5)

# Git-deployable allowlist source (DE-7) — module-level so tests can patch it
# to a tmp path, exactly the `experiments._ALLOWLIST_FILE` idiom.
ALLOWLIST_FILE = os.path.join(
    os.path.dirname(__file__), "..", "config", "negmem_leagues.json")
ALLOWLIST_ENV = "FTF_NEGMEM_LEAGUES"
_ALLOWLIST_TTL_S = 60.0

# Namespace-local clock indirection so tests can script wall time without
# patching the global `time` module and without `sleep` (§10 N-19).
_perf_counter = time.perf_counter


def _now_utc() -> datetime:
    """The ONE clock read of a build (§4.3 determinism argument, point 4)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# §4.1 — league allowlist + the None seam
# ---------------------------------------------------------------------------

_allowlist_lock = threading.Lock()
_allowlist_cache: tuple[float, frozenset[str]] | None = None


def _read_allowlist_uncached() -> frozenset[str]:
    out: set[str] = {
        s.strip() for s in os.environ.get(ALLOWLIST_ENV, "").split(",")
        if s.strip()
    }
    try:
        with open(ALLOWLIST_FILE) as fh:
            parsed = json.load(fh)
        if isinstance(parsed, list):
            out |= {str(x) for x in parsed}
        else:
            log.warning("negmem allowlist %s is not a JSON array — ignored",
                        ALLOWLIST_FILE)
    except FileNotFoundError:
        pass          # file optional — env alone is a valid configuration
    except Exception as err:
        log.warning("negmem allowlist %s unreadable (%s) — treating as EMPTY; "
                    "flag-on with an empty allowlist is inert by construction",
                    ALLOWLIST_FILE, err)
    return frozenset(out)


def load_negmem_league_allowlist() -> frozenset[str]:
    """The raw allowlist (env FTF_NEGMEM_LEAGUES ∪ config/negmem_leagues.json).

    60s cache (the `experiments._load_cache` idiom). Missing/empty/unparseable
    ⇒ empty set ⇒ `build_map` returns None for every league. Exposed so the
    readout pack's allowlist-scoped denominators use the SAME loader as the
    build — a partial rollout can never read as build failures (§7.2).
    """
    global _allowlist_cache
    # Deliberately time.monotonic(), NOT the module's _perf_counter seam: the
    # build-timing tests script that seam, and the allowlist cache must not
    # consume from their sequence.
    now = time.monotonic()
    with _allowlist_lock:
        cached = _allowlist_cache
        if cached is not None and (now - cached[0]) < _ALLOWLIST_TTL_S:
            return cached[1]
    fresh = _read_allowlist_uncached()
    with _allowlist_lock:
        _allowlist_cache = (now, fresh)
    return fresh


def _reset_allowlist_cache() -> None:
    """Test seam: drop the 60s cache (never called in production)."""
    global _allowlist_cache
    with _allowlist_lock:
        _allowlist_cache = None


def negmem_league_allowed(league_id: str) -> bool:
    """PRD §8.2 league scoping: True iff league_id ∈ (file ∪ env) allowlist, or
    the allowlist contains "*". Global rollout is the one-line diff `["*"]`."""
    allow = load_negmem_league_allowlist()
    if not allow:
        return False
    return "*" in allow or str(league_id) in allow


# ---------------------------------------------------------------------------
# §3 — data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NegmemCell:
    """One (partner, reason-family) evidence cell (§3.1). No nullable fields."""

    n_raw: int          # admitted rejection events in the horizon (pre-decay, pre-net)
    n_decayed: float    # decayed, like-netted evidence mass at as_of; ≥ 0.0; rounded 1e-9
    likes_net: float    # READOUT-ONLY, PRE-CLAMP: Σ like_net·0.5^((as_of−t_like)/H)
                        # over the cell's admitted likes. NOT a term in n_decayed's
                        # arithmetic — the fold's per-step clamp (§4.5) means the mass
                        # a like actually cancelled can be LESS. Never invert one
                        # from the other.
    mult: float         # base multiplier (§4.4); ∈ (floor_b, 1.0]; rounded 1e-6
    floored: bool       # RESERVED — always False under the §4.4 asymptotic curve.
                        # Carried so a future curve change has a stamped field
                        # already in the schema. Never delete as dead code.


@dataclass(frozen=True)
class NegmemMap:
    """One job's negative-results memory (§3.2). Structurally immutable: the
    three dict fields are MappingProxyType-wrapped at construction, so a seam
    cannot "fix up" a shared map in place (H-4)."""

    user_id: str
    league_id: str
    as_of: str                                   # ISO UTC, build time or caller's as_of
    ver: int                                     # = NEGMEM_VER
    cells: Mapping[tuple[str, str], NegmemCell]  # (partner_league_id, family)
    partner_mult: Mapping[str, float]            # DE-1 MIN collapse; absent ⇒ 1.0
    acceptance_stats: Mapping[str, tuple[int, int]]   # M2: partner → (accepts, responses)
                                                 # tuple order follows CODE
                                                 # (trade_gen_v2.py acceptance_prior
                                                 # unpacks `accepts, responses`) — §9 delta a
    degraded: bool                               # build exception OR build_ms > NEGMEM_DEGRADE_MS
    build_ms: float
    parse_errors: int                            # skipped rows (§8.1)
    dropped_unmapped_partner_ids: int            # §5.4 tripwire. 0 on a degraded map and
                                                 # 0 when the M2 feed guard short-circuits —
                                                 # "no count taken", NOT "no drops".

    def m2_feed(self) -> Mapping[str, tuple[int, int]]:
        """{} when degraded, else acceptance_stats (the read-only proxy) — the
        ONE degraded-⇒-{} rule (HLD §3.5); both gen_v2 call sites go through
        this, never the field. Drop-in safe: `acceptance_prior` only does
        truthiness, `in`, and `[]` on it — all supported by MappingProxyType —
        and it never mutates or copies it."""
        if self.degraded:
            return _EMPTY_M2
        return self.acceptance_stats


_EMPTY_M2: Mapping[str, tuple[int, int]] = MappingProxyType({})
_EMPTY_CELLS: Mapping[tuple[str, str], NegmemCell] = MappingProxyType({})
_EMPTY_MULT: Mapping[str, float] = MappingProxyType({})


# ---------------------------------------------------------------------------
# §5.1/§5.3/§5.4 — the SQL half of the ONE admission pair (DE-4)
#
# Dialect rule (analytics_queries.py header is the binding precedent): no
# json_extract/->>/::jsonb, no strftime/date_trunc/julianday, no SQL date
# arithmetic. Day bucket = substr(col,1,10) compared against a 'YYYY-MM-DD'
# bind. JSON is parsed in Python. No ORDER BY (ordering is Python's job — SQL
# sorts differ in NULL/collation corners across engines for zero benefit).
# ---------------------------------------------------------------------------

_SPINE_SQL = """
SELECT di.impression_id,
       di.served_at,
       di.features_json,
       di.is_ghost,
       di.assets_json,
       di.shape_bucket,
       di.trade_intent,
       o.id       AS outcome_id,
       o.action,
       o.acted_at,
       r.reason,
       r.detail,
       r.key_source
FROM deck_impressions di
JOIN deck_outcomes o        ON o.impression_id = di.impression_id
LEFT JOIN trade_pass_reasons r ON r.impression_id = di.impression_id
WHERE di.user_id = :uid
  AND di.league_id = :lid
  AND substr(di.served_at, 1, 10) >= :horizon_day
"""

_RETRACTED_SQL = """
SELECT id, decision, give_player_ids, receive_player_ids, retracted_at, created_at
FROM trade_decisions
WHERE user_id = :uid AND league_id = :lid
  AND decision IN ('pass', 'like')
  AND substr(created_at, 1, 10) >= :horizon_day
"""

_MATCHES_SQL = """
SELECT user_a_id, user_a_decision, user_a_decided_at,
       user_b_id, user_b_decision, user_b_decided_at,
       matched_at
FROM trade_matches
WHERE league_id = :lid
"""

_MEMBERS_SQL = """
SELECT user_id FROM league_members WHERE league_id = :lid
"""


def _rows(sql: str, params: dict) -> list[dict]:
    """One short-lived connection per statement (§5.6 — no long transaction:
    consistency-within-job comes from building once per job, not from snapshot
    isolation)."""
    with _db.engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _fetch_spine(user_id: str, league_id: str, horizon_day: str) -> list[dict]:
    """The spine fetch (§5.1). Named so the horizon/epoch test can assert on the
    FETCHED ROW COUNT — "never loaded" is the claim, and a Python-side filter
    would produce identical cells while loading everything (§10 N-22)."""
    return _rows(_SPINE_SQL, {"uid": user_id, "lid": league_id,
                              "horizon_day": horizon_day})


def _fetch_retracted(user_id: str, league_id: str, horizon_day: str) -> list[dict]:
    return _rows(_RETRACTED_SQL, {"uid": user_id, "lid": league_id,
                                  "horizon_day": horizon_day})


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_dt(value) -> datetime | None:
    """ISO-UTC text → aware datetime, or None. Naive input is read as UTC (the
    whole table family is written by datetime.now(timezone.utc).isoformat())."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _asset_key(assets_json, decision: str):
    """impression `assets_json` → (decision, frozenset(give), frozenset(receive)).

    Returns (key, ok). `ok` is False only on a PARSE failure (which the caller
    counts); a NULL column simply yields (None, True) — the retraction leg is
    skipped for that row, which is not an error.

    Both sides are str()-coerced: player ids are strings in the impression
    writer and may be ints in older decision rows, and
    frozenset({1}) != frozenset({"1"}) would silently disable the whole leg.
    """
    if not assets_json:
        return None, True
    try:
        parsed = json.loads(assets_json)
        give = frozenset(str(x) for x in (parsed.get("give") or []))
        recv = frozenset(str(x) for x in (parsed.get("receive") or []))
    except Exception:
        return None, False
    return (decision, give, recv), True


def _retracted_keys(decision_rows) -> set[tuple[str, frozenset, frozenset]]:
    """§5.3 latest-row rule. Group ('pass','like') decision rows by
    (decision, frozenset(give), frozenset(recv)); within a group the row with
    max(created_at) DECIDES, and the key is retracted iff THAT row's
    `retracted_at` is non-NULL.

    The `AND retracted_at IS NOT NULL` filter is deliberately absent from
    _RETRACTED_SQL: the schema documents a revive path ("a later re-like writes
    a fresh row with NULL"), so windowless retracted-only matching would let a
    stale retraction suppress a later live decision over the identical asset
    set forever — and over-dropping a netting LIKE is the ANTI-conservative
    direction (§5.3).

    NULL `created_at` sorts as oldest via ("", id). That branch is DEFENSIVE
    ONLY: substr(NULL,1,10) is NULL in both dialects, so such a row never
    survives the fetch predicate — it can only arrive from a fixture, a
    backfill, or a future writer handing rows straight to this function.
    """
    groups: dict[tuple[str, frozenset, frozenset], tuple[tuple, object]] = {}
    for row in decision_rows:
        decision = row.get("decision")
        if decision not in ("pass", "like"):
            continue
        try:
            give = frozenset(
                str(x) for x in json.loads(row.get("give_player_ids") or "[]"))
            recv = frozenset(
                str(x) for x in json.loads(row.get("receive_player_ids") or "[]"))
        except Exception:
            continue                      # unparseable decision side ⇒ leg skipped
        key = (decision, give, recv)
        sort_key = (str(row.get("created_at") or ""), int(row.get("id") or 0))
        current = groups.get(key)
        if current is None or sort_key > current[0]:
            groups[key] = (sort_key, row.get("retracted_at"))
    return {key for key, (_, retracted_at) in groups.items() if retracted_at}


# ---------------------------------------------------------------------------
# §5.2 — the Python predicate half of the pair (per-impression replay +
#        the closed admission list)
# ---------------------------------------------------------------------------

def _admit_events(rows, *, as_of_dt: datetime, retracted_keys,
                  require_reason: bool = True
                  ) -> tuple[list[dict], list[dict], int]:
    """R1's closed list as executed checks. Takes NO `owner_alias` — the
    evidence path does no identity conversion (DE-5).

    Returns (evidence_events, netting_events, parse_errors).

    `require_reason` is the ONE relaxation, and it exists solely so the RFPS
    cohort (§7.4 step 1) can include reason-LESS rejections without a second
    copy of the replay/ghost/viewed/retraction logic — the LLD requires both
    "reason requirement relaxed for cohort membership" and "the admission
    implementation is still the one shared code path", and this parameter is
    what makes those compatible. The SERVING path never passes it: build_map
    and the readout use the default, so R1's closed list is unchanged for
    everything that feeds a deck. Relaxed events carry `family=None` and are
    ignored by `_fold_events`.
    """
    parse_errors = 0
    by_impression: dict[str, dict] = {}

    for row in rows:
        imp = row.get("impression_id")
        if imp is None:
            parse_errors += 1
            continue
        acted = _parse_dt(row.get("acted_at"))
        if acted is None:
            parse_errors += 1
            continue
        if acted > as_of_dt:               # as-of reconstruction (R6)
            continue
        group = by_impression.get(imp)
        if group is None:
            group = by_impression[imp] = {"meta": row, "outcomes": []}
        group["outcomes"].append((acted, int(row.get("outcome_id") or 0),
                                  row.get("action"), row))

    evidence: list[dict] = []
    netting: list[dict] = []

    for imp, group in by_impression.items():
        meta = group["meta"]
        outcomes = sorted(group["outcomes"], key=lambda t: (t[0], t[1]))

        # --- undo pairing = per-impression replay -------------------------
        stack: list[tuple[datetime, int, str]] = []
        viewed = False
        for acted, oid, action, _row in outcomes:
            if action == "viewed":
                viewed = True
            elif action in _DECISION_ACTIONS:
                stack.append((acted, oid, action))
            elif action == "undo":
                if stack:
                    stack.pop()            # negates the MOST RECENT survivor
                # else: stray undo — no-op (late/duplicate labels are legal)
        if not stack:
            continue                       # no net disposition
        final_ts, final_oid, final = stack[-1]

        # (a) viewed gate — "a viewed row exists with acted_at ≤ as_of", NOT
        #     "viewed precedes the decision" (the batched events side-channel
        #     can land the viewed row after the swipe).
        if not viewed:
            continue
        # (c) ghost exclusion — Integer nullable; `!= 1` treats NULL as
        #     not-ghost, matching pre-telemetry rows.
        is_ghost = meta.get("is_ghost")
        if is_ghost is not None:
            try:
                if int(is_ghost) == 1:
                    continue
            except Exception:
                parse_errors += 1
                continue

        if final in _REJECTION_ACTIONS:
            # (b) reason row required, layer-1 column IS the family
            family = meta.get("reason")
            reason_carrying = (meta.get("key_source") == "impression"
                               and family in NEGMEM_ADMITTED_FAMILIES)
            if not reason_carrying:
                if require_reason:
                    continue
                family = None            # RFPS cohort member, not evidence
            partner, ok = _partner_and_tags(meta)
            if not ok:
                parse_errors += 1
                continue
            if partner is None:
                parse_errors += 1
                continue
            partner_id, tags = partner
            # (d) retraction leg — the replay is the undo half; this is the
            #     trade_decisions half.
            key, parsed_ok = _asset_key(meta.get("assets_json"), "pass")
            if not parsed_ok:
                parse_errors += 1
            elif key is not None and key in retracted_keys:
                continue
            if family == "value" and tags.get("user_value_basis") == "personal":
                tags["basis_note"] = "board-fit"     # a TAG, not a family change
            evidence.append({
                "impression_id": imp,
                "partner": partner_id,
                "family": family,
                "reason_carrying": reason_carrying,
                "ts": final_ts,
                "served_at": meta.get("served_at"),
                "row_id": final_oid,
                "action": final,
                "detail": meta.get("detail"),
                "shape_bucket": meta.get("shape_bucket"),
                "context_tags": tags,
            })
        elif final == "like":
            partner, ok = _partner_and_tags(meta)
            if not ok:
                parse_errors += 1
                continue
            if partner is None:
                parse_errors += 1
                continue
            partner_id, tags = partner
            key, parsed_ok = _asset_key(meta.get("assets_json"), "like")
            if not parsed_ok:
                parse_errors += 1
            elif key is not None and key in retracted_keys:
                continue
            netting.append({
                "impression_id": imp,
                "partner": partner_id,
                "ts": final_ts,
                "served_at": meta.get("served_at"),
                "row_id": final_oid,
                "context_tags": tags,
            })
        # `propose` survivors contribute nothing (PRD §5.3 names likes only).

    evidence.sort(key=lambda e: (e["ts"], e["row_id"], e["impression_id"]))
    netting.sort(key=lambda e: (e["ts"], e["row_id"], e["impression_id"]))
    return evidence, netting, parse_errors


def _partner_and_tags(meta) -> tuple[tuple[str, dict] | None, bool]:
    """features_json → (partner_user_id, context tags), or (None, ok).

    `partner_user_id` is used VERBATIM as the cell key with no alias step
    (DE-5): it is written from card.target_user_id == LeagueMember.user_id, the
    canonical league identity ADR-012 keeps league_members single-valued on.
    Context tags are R11 recorded-not-consulted.
    """
    raw = meta.get("features_json")
    if not raw:
        return None, True                  # partnerless card ⇒ counted, skipped
    try:
        features = json.loads(raw)
    except Exception:
        return None, False
    if not isinstance(features, dict):
        return None, False
    partner = features.get("partner_user_id")
    if partner is None or str(partner) == "":
        return None, True
    tags = {
        "lane": features.get("lane"),
        "user_value_basis": features.get("user_value_basis"),
        "trade_intent": meta.get("trade_intent"),   # COLUMN, not a features key
    }
    return (str(partner), tags), True


def load_admitted_events(user_id: str, league_id: str, *, as_of: str,
                         horizon_floor_day: str
                         ) -> tuple[list[dict], list[dict], int]:
    """R1's closed list, THE one implementation: runs _SPINE_SQL (the plain
    dual-dialect fetch) and _RETRACTED_SQL, then applies the Python predicate.
    Consumed by build_map, negmem_readout, and the RFPS artifact generator —
    nobody re-implements."""
    as_of_dt = _parse_dt(as_of)
    if as_of_dt is None:
        raise ValueError(f"negmem: unparseable as_of {as_of!r}")
    spine = _fetch_spine(user_id, league_id, horizon_floor_day)
    retracted = _retracted_keys(
        _fetch_retracted(user_id, league_id, horizon_floor_day))
    return _admit_events(spine, as_of_dt=as_of_dt, retracted_keys=retracted)


# ---------------------------------------------------------------------------
# §4.3/§4.4/§4.5 — decay, netting, shrinkage curve, combine rule
# ---------------------------------------------------------------------------

def _decay(mass: float, delta_days: float, halflife_days: float) -> float:
    """Exponential half-life decay with the clock-skew guard (§4.3): the
    exponent is clamped at ≥ 0, so a server clock that jumped back between
    writes counts a skewed row at weight 1, never amplified."""
    return mass * (0.5 ** (max(0.0, delta_days) / halflife_days))


def _days_between(earlier: datetime, later: datetime) -> float:
    return (later - earlier).total_seconds() / 86400.0


def _cell_mult(n_decayed: float, *, min_evidence: float, floor_b: float,
               sat_k: float) -> float:
    """§4.4 — identity below the shrinkage threshold (R3), first effect exactly
    AT it, asymptote floor_b, never below it and never above 1.0.

        n_eff = n_decayed − min_evidence + 1
        mult  = 1 − (1 − floor_b) · n_eff / (n_eff + sat_k)

    The threshold step is exactly (1 − floor_b)/(1 + sat_k) — which is why
    negmem_sat_k is the deploy-free flap-size lever (OQ-4b, runbook line 8).
    """
    if n_decayed < min_evidence:
        return 1.0
    n_eff = n_decayed - min_evidence + 1.0
    return round(1.0 - (1.0 - floor_b) * n_eff / (n_eff + sat_k), 6)


def _fold_events(evidence, netting, *, as_of_dt: datetime, halflife_days: float,
                 like_net: float, min_evidence: float, floor_b: float,
                 sat_k: float
                 ) -> tuple[dict[tuple[str, str], NegmemCell], dict[str, float]]:
    """The chronological fold (§4.3) with DECREMENT netting and a clamp-at-zero
    after EVERY step (§4.5 / DE-2), then the §4.4 curve and the DE-1 MIN
    collapse.

    Cells exist for every (partner, family) with ≥1 admitted rejection OR ≥1
    netting like in the horizon — identity cells are kept, because the readout
    and the RFPS numerator rule both need sub-threshold state.
    """
    ev_by_partner_family: dict[tuple[str, str], list[dict]] = {}
    for e in evidence:
        if e.get("family") not in NEGMEM_ADMITTED_FAMILIES:
            continue          # a relaxed RFPS-cohort row is never evidence
        ev_by_partner_family.setdefault((e["partner"], e["family"]), []).append(e)

    likes_by_partner: dict[str, list[dict]] = {}
    for n in netting:
        likes_by_partner.setdefault(n["partner"], []).append(n)

    # A like carries no reason code, so it nets EVERY (P, ✱) cell — which also
    # means a partner with any admitted like gets a cell in every admitted
    # family, even with zero evidence (the cell records likes_net only).
    cell_keys: set[tuple[str, str]] = set(ev_by_partner_family)
    for partner in likes_by_partner:
        for family in NEGMEM_ADMITTED_FAMILIES:
            cell_keys.add((partner, family))

    cells: dict[tuple[str, str], NegmemCell] = {}
    for key in sorted(cell_keys):
        partner, family = key
        ev_rows = ev_by_partner_family.get(key, [])
        like_rows = likes_by_partner.get(partner, [])

        # kind orders evidence (0) before netting (1) at identical timestamps —
        # a same-instant like should net the evidence it accompanies, not miss
        # it; row_id breaks same-instant ties deterministically.
        stream = [(e["ts"], 0, e["row_id"], 1.0) for e in ev_rows]
        stream += [(n["ts"], 1, n["row_id"], -float(like_net)) for n in like_rows]
        stream.sort(key=lambda t: (t[0], t[1], t[2]))

        acc = 0.0
        prev: datetime | None = None
        for ts, _kind, _rid, weight in stream:
            if prev is not None:
                acc = _decay(acc, _days_between(prev, ts), halflife_days)
            acc = max(0.0, acc + weight)
            prev = ts
        n_decayed = 0.0 if prev is None else _decay(
            acc, _days_between(prev, as_of_dt), halflife_days)
        n_decayed = round(n_decayed, 9)

        likes_net = round(float(sum(
            _decay(float(like_net), _days_between(n["ts"], as_of_dt), halflife_days)
            for n in like_rows)), 9)

        cells[key] = NegmemCell(
            n_raw=len(ev_rows),
            n_decayed=n_decayed,
            likes_net=likes_net,
            mult=_cell_mult(n_decayed, min_evidence=min_evidence,
                            floor_b=floor_b, sat_k=sat_k),
            floored=False,        # RESERVED — the curve never lands on floor_b
        )

    # DE-1: MIN across a partner's family cells, never the product. House
    # precedent: F3 fatigue takes the MIN of its keys ("never a product — one
    # impression must not be triple-counted"). Precomputed at build so
    # effective_mult is O(1) per call.
    partner_mult: dict[str, float] = {}
    for (partner, _family), cell in cells.items():
        prior = partner_mult.get(partner)
        partner_mult[partner] = cell.mult if prior is None else min(prior, cell.mult)

    return cells, partner_mult


# ---------------------------------------------------------------------------
# §4.6 — effective_mult: the ONE implementation; PURE; total function
# ---------------------------------------------------------------------------

def effective_mult(nm_map: "NegmemMap | None", partner_league_id: str, *,
                   strength: float, floor: float) -> float:
    """eff = clamp(1 + strength·(mult−1), floor, 1.0) — the HLD D-6 formula.

    PURE (D-10): no config access, no defaults, no I/O. Total function —
    None/degraded map, unknown partner, strength ≤ 0, or NaN strength all
    return exactly 1.0. Sink-never-rise is structural (mult ≤ 1 and the upper
    min()). `degraded` is DATA on the map, so branching on it here is what
    makes "seams treat a degraded map as identity" a one-line invariant.
    """
    if nm_map is None or nm_map.degraded:
        return 1.0
    mult = nm_map.partner_mult.get(partner_league_id, 1.0)
    if mult >= 1.0:
        return 1.0
    s = float(strength)
    if s != s:                                  # NaN strength — kill, not poison
        return 1.0
    if s <= 0.0:
        return 1.0                              # structural short-circuit (D-6)
    f = min(max(float(floor), 0.0), 1.0)        # sanitize a bad knob read
    return round(min(1.0, max(f, 1.0 + s * (mult - 1.0))), 6)


def stamp_payload(nm_map: "NegmemMap", partner_league_id: str,
                  eff: float) -> dict:
    """The consult-time stamp the card carries (B2): {m, keys, ev, ver} (§3.3).

    `keys` = the admitted families whose cells DROVE partner_mult (mult < 1.0),
    sorted; `ev` = {family: round(n_decayed, 2)} for those keys. Partner is
    deliberately not repeated — it is already features.partner_user_id.
    """
    keys = sorted(
        family for (partner, family), cell in nm_map.cells.items()
        if partner == partner_league_id and cell.mult < 1.0
    )
    return {
        "m": round(float(eff), 4),
        "keys": keys,
        "ev": {f: round(nm_map.cells[(partner_league_id, f)].n_decayed, 2)
               for f in keys},
        "ver": NEGMEM_VER,
    }


# ---------------------------------------------------------------------------
# §5.4 — M2 aggregation (fetch + Python fold + feed guard)
# ---------------------------------------------------------------------------

def _acceptance_fold(match_rows, member_ids, *, user_id: str,
                     as_of_dt: datetime, owner_alias: Mapping[str, str]
                     ) -> tuple[dict[str, tuple[int, int]], int]:
    """trade_matches → {partner: (accepts, responses)} + the unmapped-drop count.

    `status` is derived and deliberately NOT used (a 'pending' row where one
    side already declined-first would be missed by status-filtering); per-side
    decisions are the response events. `user_*_dismissed` is inbox-archive only
    and is never read here.

    The fold never emits zero-response keys — structurally, a key exists only
    via `resp + 1`. At n=0 a partner is simply absent and acceptance_prior
    returns exactly p0.
    """
    cutoff = as_of_dt - timedelta(days=NEGMEM_M2_LOOKBACK_DAYS)
    stats: dict[str, tuple[int, int]] = {}
    for row in match_rows:
        matched_at = row.get("matched_at")
        sides = (
            (row.get("user_a_id"), row.get("user_a_decision"),
             row.get("user_a_decided_at")),
            (row.get("user_b_id"), row.get("user_b_decision"),
             row.get("user_b_decided_at")),
        )
        for uid, decision, decided_at in sides:
            if decision not in ("accept", "decline"):
                continue
            ts = _parse_dt(decided_at) or _parse_dt(matched_at)
            if ts is None or ts > as_of_dt:
                continue
            if ts < cutoff:                       # PRD R5 window, §9 delta f
                continue
            if uid is None:
                continue
            key = owner_alias.get(str(uid), str(uid))   # DE-5: identity by default
            accepts, responses = stats.get(key, (0, 0))
            stats[key] = (accepts + (1 if decision == "accept" else 0),
                          responses + 1)

    # Drop the requesting user FIRST, then filter to canonical league members
    # and count every dropped key once (DE-5's visible tripwire).
    stats.pop(str(user_id), None)
    members = {str(m) for m in member_ids}
    dropped = 0
    for key in list(stats):
        if key not in members:
            del stats[key]
            dropped += 1
    return {k: (int(a), int(r)) for k, (a, r) in stats.items()}, dropped


# ---------------------------------------------------------------------------
# §4.7 / §5.6 — the build
# ---------------------------------------------------------------------------

def _horizon_floor_day(as_of_dt: datetime, halflife_days: float) -> str:
    """max(clean epoch, as_of − 4·halflife) as YYYY-MM-DD (§4.7). Day
    granularity is conservative by at most one day of EXTRA rows — never one
    day short, because `>=` on the day prefix admits the whole boundary day."""
    rolling = (as_of_dt - timedelta(
        days=NEGMEM_HORIZON_HALFLIVES * halflife_days)).date().isoformat()
    return max(NEGMEM_CLEAN_EPOCH_DAY, rolling)


def _degraded_map(user_id: str, league_id: str, as_of_iso: str, build_ms: float,
                  parse_errors: int = 0) -> NegmemMap:
    return NegmemMap(
        user_id=str(user_id), league_id=str(league_id), as_of=as_of_iso,
        ver=NEGMEM_VER, cells=_EMPTY_CELLS, partner_mult=_EMPTY_MULT,
        acceptance_stats=_EMPTY_M2, degraded=True, build_ms=build_ms,
        parse_errors=parse_errors, dropped_unmapped_partner_ids=0,
    )


def _build(user_id: str, league_id: str, *, halflife_days: float,
           min_evidence: float, sat_k: float, like_net: float, floor_b: float,
           accept_prior_strength: float, owner_alias: Mapping[str, str],
           as_of: str | None) -> tuple[NegmemMap, dict]:
    """The builder, allowlist-independent. Returns (map, extras); `extras`
    carries the admitted-event lists the readout needs (partner_likes and the
    per-cell context-tag counts are derived from the SAME lists the fold
    consumed, so the two can never disagree about the same as_of).

    NEVER raises except KeyboardInterrupt/SystemExit (BaseException passes
    through `except Exception` untouched).
    """
    t0 = _perf_counter()
    as_of_dt = _parse_dt(as_of) if as_of else _now_utc()
    if as_of_dt is None:
        as_of_dt = _now_utc()
    as_of_iso = as_of_dt.isoformat()

    try:
        # Degenerate knobs sanitized ONCE at entry (§2): a fat-fingered admin
        # PUT must not produce ZeroDivisionError or a mult > 1.
        floor_b = min(max(float(floor_b), 0.0), 1.0)
        halflife_days = max(float(halflife_days), 1e-6)
        min_evidence = max(float(min_evidence), 1e-6)
        sat_k = max(float(sat_k), 1e-6)
        like_net = float(like_net)
        accept_prior_strength = float(accept_prior_strength)

        horizon_day = _horizon_floor_day(as_of_dt, halflife_days)
        evidence, netting, parse_errors = load_admitted_events(
            user_id, league_id, as_of=as_of_iso, horizon_floor_day=horizon_day)
        cells, partner_mult = _fold_events(
            evidence, netting, as_of_dt=as_of_dt, halflife_days=halflife_days,
            like_net=like_net, min_evidence=min_evidence, floor_b=floor_b,
            sat_k=sat_k)

        # Feed guard FIRST (HLD §3.5, NG9): the E-B pseudo-count m IS this
        # knob, and the guard lives in the FEED, never inside the ratified
        # acceptance_prior math. It SHORT-CIRCUITS both M2 queries — so a
        # killed M2 costs two fewer round-trips and the counter below reads 0
        # because no count was TAKEN, not because there were no drops.
        if accept_prior_strength <= 0.0:
            acceptance_stats: dict[str, tuple[int, int]] = {}
            dropped = 0
        else:
            match_rows = _rows(_MATCHES_SQL, {"lid": league_id})
            member_ids = [r.get("user_id")
                          for r in _rows(_MEMBERS_SQL, {"lid": league_id})]
            acceptance_stats, dropped = _acceptance_fold(
                match_rows, member_ids, user_id=user_id, as_of_dt=as_of_dt,
                owner_alias=owner_alias)
    except Exception as err:      # BaseException (KeyboardInterrupt/SystemExit,
                                  # GeneratorExit) deliberately passes through
        build_ms = (_perf_counter() - t0) * 1000.0
        log.warning("negmem build degraded for user=%s league=%s: %s",
                    user_id, league_id, err)
        return _degraded_map(user_id, league_id, as_of_iso, build_ms), {}

    build_ms = (_perf_counter() - t0) * 1000.0
    slow = build_ms > NEGMEM_DEGRADE_MS
    if slow:
        # Slow-but-valid ⇒ DISCARDED by design, not merely stamped.
        log.warning("negmem build_ms=%.1f exceeded %.1f — map degraded "
                    "(user=%s league=%s)", build_ms, NEGMEM_DEGRADE_MS,
                    user_id, league_id)
        return (_degraded_map(user_id, league_id, as_of_iso, build_ms,
                              parse_errors),
                {"evidence": evidence, "netting": netting})

    nm_map = NegmemMap(
        user_id=str(user_id), league_id=str(league_id), as_of=as_of_iso,
        ver=NEGMEM_VER,
        cells=MappingProxyType(dict(cells)),
        partner_mult=MappingProxyType(dict(partner_mult)),
        acceptance_stats=MappingProxyType(dict(acceptance_stats)),
        degraded=False, build_ms=build_ms, parse_errors=parse_errors,
        dropped_unmapped_partner_ids=dropped,
    )
    log.info("negmem build_ms=%.1f cells=%d evidence=%d netting_likes=%d "
             "user=%s league=%s", build_ms, len(cells), len(evidence),
             len(netting), user_id, league_id)
    return nm_map, {"evidence": evidence, "netting": netting}


def build_map(user_id: str, league_id: str, *,
              halflife_days: float, min_evidence: float, sat_k: float,
              like_net: float, floor_b: float,
              accept_prior_strength: float,
              owner_alias: Mapping[str, str] = _EMPTY_ALIAS,
              as_of: str | None = None) -> NegmemMap | None:
    """One bulk read → NegmemMap for this job; None iff league not allowlisted
    (the PRD §8.2 None seam — downstream indistinguishable from flag-off).

    All knobs arrive as arguments — no config access in this module (DE-3).

    `owner_alias` (DE-5) applies to the M2 path ONLY and defaults to IDENTITY.
    v1 ships no producer for a co-owner map: no server-side co-owner source
    exists, so callers pass nothing. M1's evidence path takes no alias at all —
    its partner ids are already canonical league identities.
    """
    if not negmem_league_allowed(league_id):
        return None
    nm_map, _extras = _build(
        user_id, league_id, halflife_days=halflife_days,
        min_evidence=min_evidence, sat_k=sat_k, like_net=like_net,
        floor_b=floor_b, accept_prior_strength=accept_prior_strength,
        owner_alias=owner_alias, as_of=as_of)
    return nm_map


# ---------------------------------------------------------------------------
# §7.1 — the R8 operator readout
# ---------------------------------------------------------------------------

_READOUT_KNOBS = ("negmem_strength", "negmem_floor", "negmem_min_evidence",
                  "negmem_halflife_days", "negmem_sat_k", "negmem_like_net",
                  "gen2_accept_prior_strength", "gen2_accept_global_prior")

_MISSING_SEEDS = "negmem seed rows missing — run init_db"


def negmem_readout(user_id: str, league_id: str, as_of: str | None = None,
                   knobs: dict | None = None,
                   owner_alias: Mapping[str, str] = _EMPTY_ALIAS) -> dict:
    """R8 operator dump (§7.1 format).

    Same builder, allowlist check BYPASSED — the readout must work for a
    not-yet-allowlisted league and reports `allowlisted` as DATA (a readout
    that returns None there is a tautology).

    knobs=None ⇒ read database.get_config() (leaf-legal); a missing knob key
    raises KeyError('negmem seed rows missing — run init_db') — negmem holds no
    default literals (DE-3).
    """
    if knobs is None:
        knobs = _db.get_config()
    resolved: dict[str, float] = {}
    for key in _READOUT_KNOBS:
        if key not in knobs:
            raise KeyError(_MISSING_SEEDS)
        resolved[key] = float(knobs[key])

    nm_map, extras = _build(
        user_id, league_id,
        halflife_days=resolved["negmem_halflife_days"],
        min_evidence=resolved["negmem_min_evidence"],
        sat_k=resolved["negmem_sat_k"],
        like_net=resolved["negmem_like_net"],
        floor_b=resolved["negmem_floor"],
        accept_prior_strength=resolved["gen2_accept_prior_strength"],
        owner_alias=owner_alias, as_of=as_of)

    evidence = extras.get("evidence", [])
    netting = extras.get("netting", [])

    tag_counts: dict[tuple[str, str], dict[str, dict]] = {}
    for e in evidence:
        bucket = tag_counts.setdefault((e["partner"], e["family"]), {})
        for tag in ("lane", "user_value_basis", "trade_intent"):
            per_tag = bucket.setdefault(tag, {})
            value = e["context_tags"].get(tag)
            per_tag[value] = per_tag.get(value, 0) + 1

    min_evidence = resolved["negmem_min_evidence"]
    cells = [
        {
            "partner_league_id": partner,
            "family": family,
            "n_raw": cell.n_raw,
            "n_decayed": round(cell.n_decayed, 2),
            "likes_net": round(cell.likes_net, 2),
            "mult": cell.mult,
            "floored": cell.floored,
            "below_min_evidence": cell.n_decayed < min_evidence,
            "context_tag_counts": tag_counts.get((partner, family), {}),
        }
        for (partner, family), cell in sorted(nm_map.cells.items())
    ]

    partner_likes: dict[str, int] = {}
    for n in netting:
        partner_likes[n["partner"]] = partner_likes.get(n["partner"], 0) + 1

    if nm_map.degraded:
        m2_status = "degraded"
    elif resolved["gen2_accept_prior_strength"] <= 0:
        m2_status = "killed (gen2_accept_prior_strength <= 0)"
    else:
        m2_status = "live"

    return {
        "user_id": str(user_id),
        "league_id": str(league_id),
        "as_of": nm_map.as_of,
        "ver": NEGMEM_VER,
        "allowlisted": negmem_league_allowed(league_id),
        "degraded": nm_map.degraded,
        "build_ms": round(nm_map.build_ms, 1),
        "parse_errors": nm_map.parse_errors,
        "knobs": resolved,
        "cells": cells,
        "partner_likes": partner_likes,
        "partner_mult": dict(nm_map.partner_mult),
        "acceptance_stats": {k: list(v) for k, v in nm_map.acceptance_stats.items()},
        "m2": m2_status,
        "dropped_unmapped_partner_ids": nm_map.dropped_unmapped_partner_ids,
    }
