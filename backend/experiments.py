"""experiments.py — the layered A/B + multivariate evaluator (analytics
platform P3, LLD §4.2/§4.3/§6.5). Deterministic, stateless assignment;
persist-on-first-eval as an audit trail; fail-open everywhere.

Public API (the P1 stubs bind to these — keep the signatures stable):
  resolve_for_unit(unit_id, header_attrs=None) -> (experiments, configs)
      the flag endpoint's per-unit snapshot: {key: variant}, {key: client_config}
  variant_for(unit_id, exp_key, header_attrs=None) -> str | None
      server call sites (e.g. the trade_service aggression migration)
  stamp_for_event(user_id, event_type, screen) -> dict | None
      FR-32: {key: variant} for events inside a running experiment's scope
Admin (CRON-gated routes call these): create_experiment, validate_spec,
transition, decide, revise, list_experiments, get_experiment, readout,
preview (design calculator).

Two-stage hash (LLD §4.2 — a single experiment-keyed hash CANNOT give in-layer
exclusivity, so the layer bucket is experiment-INDEPENDENT):
  layer_bucket   = h(salt : unit_id)                    places the unit once/layer
  variant_bucket = h(salt : key : version : unit_id)    the variant split
Ranges are half-open [start, end); the layer salt is per-layer and immutable.

Gated on the `experiments.engine` flag: off → resolve/variant_for return
empty/None, so the product runs exactly as if no experiment existed.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import insert, select, text, update

from . import database as db
from .feature_flags import is_enabled

# ---------------------------------------------------------------------------
# Attribute registry (FR-33b) — name → (source, unit_types it's available for)
# ---------------------------------------------------------------------------
# device-unit experiments (e.g. the onboarding layer, pre-auth) can target only
# header + allowlist attributes — a device pseudo-id has no `users` row.
_HEADER = "header"
_USERS = "users"
_CONFIG = "config"
ATTR_REGISTRY = {
    "platform":            (_HEADER, {"account", "device"}),
    "app_version":         (_HEADER, {"account", "device"}),   # + _gte semver op
    "os_version":          (_HEADER, {"account", "device"}),
    "device_type":         (_HEADER, {"account", "device"}),
    "is_tester_allowlist": (_CONFIG, {"account", "device"}),
    "signup_week":         (_USERS, {"account"}),
    "verified":            (_USERS, {"account"}),
    "invited_by_present":  (_USERS, {"account"}),
    "league_count":        (_USERS, {"account"}),
    "scoring_formats":     (_USERS, {"account"}),
    "ranking_method":      (_USERS, {"account"}),
    "activation_stage":    (_USERS, {"account"}),
    "wat_active_last_28d": (_USERS, {"account"}),
}

# Metric catalog — primary/secondary/guardrail keys must resolve here (FR-34).
METRIC_CATALOG = {
    "activation_rate", "ttfv_p50", "empty_deck_rate", "insult_rate",
    "crash_free_core_loop", "wat", "like_rate", "board_completion_rate",
    "trades_generated_count", "send_success_rate", "match_rate",
}
# The five binding PFO guardrails, auto-attached to every experiment (FR-45).
PFO_GUARDRAILS = ["activation_rate", "ttfv_p50", "empty_deck_rate",
                  "insult_rate", "crash_free_core_loop"]

RESERVED_LAYERS = ("onboarding", "ranking", "trades_ui", "engine", "growth")
_STATUS = ("draft", "running", "paused", "stopped", "decided")
_LEGAL_EDGES = {
    ("draft", "running"),
    ("running", "paused"), ("paused", "running"),
    ("running", "stopped"), ("paused", "stopped"),
    ("stopped", "decided"),
}
_CACHE_TTL_S = 60.0
_UNDERPOWERED_WEEKS = 26
# Git-deployable allowlist source (see _load_cache) — module-level so tests
# can patch it to a tmp path.
_ALLOWLIST_FILE = os.path.join(
    os.path.dirname(__file__), "..", "config", "tester_allowlist.json")


class ExperimentError(ValueError):
    """Validation / state error → the route returns 400/409, never a 500."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Hashing (LLD §4.2)
# ---------------------------------------------------------------------------

def _h(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big") % 10000


def _variant_for_bucket(variants: list[dict], bucket: int) -> str:
    """Cumulative weight_bp lookup over [0, 10000). variants sum to 10000."""
    acc = 0
    for v in variants:
        acc += int(v["weight_bp"])
        if bucket < acc:
            return v["name"]
    return variants[-1]["name"]   # rounding guard (Σ==10000 makes this rare)


def unit_type_of(unit_id: str) -> str:
    return "device" if unit_id.startswith("device:") else "account"


def load_tester_allowlist() -> set[str]:
    """Operator/tester allowlist — union of two sources (FR-33b):
      1. FTF_TESTER_ALLOWLIST env var (comma-separated unit_ids)
      2. config/tester_allowlist.json (JSON array; git-deployable —
         needed because Render does NOT apply render.yaml envVars to a
         dashboard-created service, observed 2026-07-19)
    Unit ids are account ids and/or 'device:<id>' pseudo-ids. Not
    model_config (value column is Float). Consumed by the is_tester_allowlist
    targeting attribute (via _load_cache) and by the QA stage-user spawner
    gate (server.py /api/test-users) so both share one definition."""
    allowlist = {
        s.strip() for s in os.environ.get("FTF_TESTER_ALLOWLIST", "").split(",")
        if s.strip()
    }
    try:
        with open(_ALLOWLIST_FILE) as f:
            parsed = json.load(f)
        if isinstance(parsed, list):
            allowlist |= {str(x) for x in parsed}
    except Exception:
        pass   # file optional — env alone is a valid configuration
    return allowlist


# ---------------------------------------------------------------------------
# Running-experiment cache (60 s TTL, LLD §4.4/FR-38)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict = {"at": 0.0, "running": [], "layers": {}, "scope": {}, "allowlist": set()}


def _load_cache() -> dict:
    now = time.time()
    with _cache_lock:
        if now - _cache["at"] < _CACHE_TTL_S and _cache["at"] > 0:
            return _cache
    try:
        with db.ro_engine.connect() as conn:
            layers = {r[0]: r[1] for r in conn.execute(
                select(db.experiment_layers_table.c.layer,
                       db.experiment_layers_table.c.salt)).fetchall()}
            rows = conn.execute(
                select(db.experiments_table).where(
                    db.experiments_table.c.status == "running")).mappings().all()
        running = [_parse_row(r) for r in rows]
        # is_tester_allowlist (_CONFIG source, FR-33b) — resolved here (60s
        # cache refresh) so _gather_attrs stays query-free on the hot flags
        # path. See load_tester_allowlist for the source-of-truth reader.
        allowlist = load_tester_allowlist()
        # Stamp scope: event_type/screen → [keys] for FR-32 (funnel events
        # always stamped, plus each running experiment's declared scope).
        scope: dict[str, list] = {}
        for e in running:
            sc = e.get("scope") or {}
            for et in sc.get("event_types", []):
                scope.setdefault(("event", et), []).append(e["key"])
            for scr in sc.get("screens", []):
                scope.setdefault(("screen", scr), []).append(e["key"])
        snap = {"at": now, "running": running, "layers": layers, "scope": scope,
                "allowlist": allowlist}
        with _cache_lock:
            _cache.update(snap)
        return snap
    except Exception as e:
        print(f"[experiments] cache load failed (serving stale/empty): {e}")
        with _cache_lock:
            return dict(_cache)


def _parse_row(r) -> dict:
    return {
        "key": r["key"], "version": r["version"], "layer": r["layer"],
        "status": r["status"], "unit_type": r["unit_type"],
        "bucket_start": r["bucket_start"], "bucket_end": r["bucket_end"],
        "targeting": json.loads(r["targeting_json"]) if r["targeting_json"] else {},
        "variants": json.loads(r["variants_json"]) if r["variants_json"] else [],
        "scope": json.loads(r["scope_json"]) if r["scope_json"] else {},
        "exposure_surface": r["exposure_surface"],
        "primary_metric": r["primary_metric"],
    }


def invalidate_cache() -> None:
    with _cache_lock:
        _cache["at"] = 0.0


# ---------------------------------------------------------------------------
# Targeting (LLD §4.3) — predicate over the attribute registry
# ---------------------------------------------------------------------------

def _semver_tuple(v: str):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0,)


def _targeting_match(targeting: dict, attrs: dict) -> bool:
    """AND over predicates. A missing attribute → predicate FALSE (the unit is
    excluded, not defaulted into control). Ops: `<attr>_gte` semver, membership
    (list value), equality (scalar/bool)."""
    for pred, want in (targeting or {}).items():
        if pred.endswith("_gte"):
            attr = pred[:-4]
            have = attrs.get(attr)
            if have is None or _semver_tuple(have) < _semver_tuple(want):
                return False
        else:
            have = attrs.get(pred)
            if have is None:
                return False
            if isinstance(want, list):
                if have not in want:
                    return False
            elif have != want:
                return False
    return True


def _gather_attrs(unit_id: str, header_attrs: dict | None) -> dict:
    """Header attrs (passed by the caller) + users-row attrs for account units.
    Device units get header/allowlist only (no users row)."""
    attrs = dict(header_attrs or {})
    # _CONFIG-sourced allowlist membership — available to BOTH unit types
    # (the registry says so; without this resolution a targeting predicate on
    # is_tester_allowlist matched nobody, since missing attr == excluded).
    attrs["is_tester_allowlist"] = unit_id in (_load_cache().get("allowlist") or set())
    if unit_type_of(unit_id) != "account":
        return attrs
    try:
        with db.ro_engine.connect() as conn:
            row = conn.execute(select(db.users_table).where(
                db.users_table.c.sleeper_user_id == unit_id)).mappings().first()
        if row:
            attrs.setdefault("verified", bool(row.get("verified_at")))
            attrs.setdefault("invited_by_present", bool(row.get("invited_by")))
            attrs.setdefault("ranking_method", row.get("ranking_method"))
            if row.get("signup_at"):
                attrs.setdefault("signup_week", str(row["signup_at"])[:10])
            # activation_stage / wat via hot columns (cheap proxy, no event scan)
            attrs.setdefault("activation_stage",
                             "activated" if row.get("last_rank_at") else "signed_in")
            attrs.setdefault("wat_active_last_28d", bool(row.get("last_trade_proposed_at")))
    except Exception:
        pass
    return attrs


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

def _persist_assignment(unit_id, exp, variant, attrs):
    """INSERT OR IGNORE — audit only; the variant is always re-derivable, and
    concurrent first evals race benignly (same variant, one insert wins)."""
    try:
        with db.engine.begin() as conn:
            stmt = _conflict_ignore(
                db.experiment_assignments_table,
                ["unit_id", "experiment_key", "version"], conn)
            conn.execute(stmt, [{
                "unit_id": unit_id, "experiment_key": exp["key"],
                "version": exp["version"], "variant": variant,
                "assigned_at": _now(),
                "context_json": json.dumps(attrs, default=str)[:2000],
            }])
    except Exception:
        pass   # assignment is audit; a write failure never blocks the variant


def _conflict_ignore(table, cols, conn):
    from sqlalchemy.dialects.sqlite import insert as sq
    from sqlalchemy.dialects.postgresql import insert as pg
    ins = sq if conn.dialect.name == "sqlite" else pg
    return ins(table).on_conflict_do_nothing(index_elements=cols)


def _evaluate(unit_id, utype, attrs, exp):
    if exp["unit_type"] != utype:
        return None
    if not _targeting_match(exp["targeting"], attrs):
        return None
    salt = _load_cache()["layers"].get(exp["layer"])
    if not salt:
        return None
    layer_bucket = _h(f"{salt}:{unit_id}")
    if not (exp["bucket_start"] <= layer_bucket < exp["bucket_end"]):
        return None
    vbucket = _h(f"{salt}:{exp['key']}:{exp['version']}:{unit_id}")
    variant = _variant_for_bucket(exp["variants"], vbucket)
    _persist_assignment(unit_id, exp, variant, attrs)
    return variant


# ---------------------------------------------------------------------------
# Public API (fail-open)
# ---------------------------------------------------------------------------

def resolve_for_unit(unit_id: str, header_attrs: dict | None = None):
    """Per-unit snapshot for the flag endpoint. Returns ({key:variant},
    {key:client_config}). Empty when the engine is off or on any error."""
    try:
        if not unit_id or not is_enabled("experiments.engine"):
            return {}, {}
        utype = unit_type_of(unit_id)
        attrs = _gather_attrs(unit_id, header_attrs)
        experiments: dict[str, str] = {}
        configs: dict[str, dict] = {}
        for exp in _load_cache()["running"]:
            v = _evaluate(unit_id, utype, attrs, exp)
            if v is None:
                continue
            experiments[exp["key"]] = v
            cfg = next((x.get("client_config") for x in exp["variants"]
                        if x["name"] == v and x.get("client_config")), None)
            if cfg:
                configs[exp["key"]] = cfg
        return experiments, configs
    except Exception as e:
        print(f"[experiments] resolve_for_unit failed (default): {e}")
        return {}, {}


def variant_for(unit_id: str, exp_key: str, header_attrs: dict | None = None):
    """Variant for one experiment at a server call site. None = default
    experience (engine off / not running / not targeted / not in bucket)."""
    try:
        if not unit_id or not is_enabled("experiments.engine"):
            return None
        utype = unit_type_of(unit_id)
        attrs = _gather_attrs(unit_id, header_attrs)
        for exp in _load_cache()["running"]:
            if exp["key"] == exp_key:
                return _evaluate(unit_id, utype, attrs, exp)
        return None
    except Exception:
        return None


def variant_overlay(unit_id: str, exp_key: str, header_attrs: dict | None = None):
    """Like variant_for but also returns the variant's model_overlay dict
    (engine-layer experiments merge it over model_config). Returns
    (variant|None, overlay_dict)."""
    try:
        v = variant_for(unit_id, exp_key, header_attrs)
        if v is None:
            return None, {}
        for exp in _load_cache()["running"]:
            if exp["key"] == exp_key:
                overlay = next((x.get("model_overlay") or {} for x in exp["variants"]
                                if x["name"] == v), {})
                return v, overlay
        return v, {}
    except Exception:
        return None, {}


# Funnel events that ALWAYS carry the stamp (program-plan funnel v2).
_FUNNEL_STAMP_EVENTS = frozenset({
    "signup", "signin_succeeded", "league_selected", "trio_swipe",
    "ranking_complete_first_time", "trades_generated", "trade_proposed",
    "match_swiped", "trade_ratified", "calc_trade_evaluated",
})


def stamp_for_event(user_id: str, event_type: str, screen: str | None):
    """FR-32: the {key: variant} snapshot to stamp on an event, when the event
    is a funnel event OR inside a running experiment's declared scope. Returns
    None (no stamp) otherwise. Fail-open."""
    try:
        if not user_id or not is_enabled("experiments.engine"):
            return None
        cache = _load_cache()
        keys = set()
        if event_type in _FUNNEL_STAMP_EVENTS:
            keys.update(e["key"] for e in cache["running"])
        keys.update(cache["scope"].get(("event", event_type), []))
        if screen:
            keys.update(cache["scope"].get(("screen", screen), []))
        if not keys:
            return None
        exps, _ = resolve_for_unit(user_id, None)
        stamp = {k: v for k, v in exps.items() if k in keys}
        return stamp or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Admin: validation, CRUD, status machine (LLD §2.4)
# ---------------------------------------------------------------------------

def _running_and_paused(conn, layer, exclude_key=None):
    rows = conn.execute(select(db.experiments_table).where(
        db.experiments_table.c.layer == layer,
        db.experiments_table.c.status.in_(("running", "paused")))).mappings().all()
    return [r for r in rows if r["key"] != exclude_key]


def validate_spec(spec: dict, *, for_launch: bool = False):
    """Raise ExperimentError with an actionable message on any invalid field.
    Checks: layer, bucket range, weights sum, metric catalog, targeting attrs +
    unit-type compatibility, exposure surface, and (for_launch) in-layer overlap."""
    errs = []
    layer = spec.get("layer")
    if layer not in RESERVED_LAYERS:
        errs.append(f"layer_unknown: {layer!r} not in {RESERVED_LAYERS}")
    unit_type = spec.get("unit_type")
    if unit_type not in ("account", "device"):
        errs.append(f"unit_type_invalid: {unit_type!r}")
    bs, be = spec.get("bucket_start"), spec.get("bucket_end")
    if not (isinstance(bs, int) and isinstance(be, int) and 0 <= bs < be <= 10000):
        errs.append(f"bucket_range_invalid: need 0<=start<end<=10000, got [{bs},{be})")
    variants = spec.get("variants") or []
    if len(variants) < 2:
        errs.append("variants: need at least 2")
    else:
        wsum = sum(int(v.get("weight_bp", 0)) for v in variants)
        if wsum != 10000:
            errs.append(f"weights_not_10000: sum={wsum}")
        if len({v.get("name") for v in variants}) != len(variants):
            errs.append("variants: duplicate variant names")
        # model_overlay must be a dict of numeric scalars — a malformed overlay
        # would break the engine-layer consumer at runtime, so reject it here
        # (defense in depth with the fail-open coercion at the trade call site).
        for v in variants:
            ov = v.get("model_overlay")
            if ov is None:
                continue
            if not isinstance(ov, dict):
                errs.append(f"model_overlay_invalid: {v.get('name')!r} overlay must be an object")
            else:
                for ok, oval in ov.items():
                    if not isinstance(oval, (int, float)) or isinstance(oval, bool):
                        errs.append(f"model_overlay_invalid: {v.get('name')!r}.{ok} must be numeric")
    pm = spec.get("primary_metric")
    if pm not in METRIC_CATALOG:
        errs.append(f"metric_unknown: {pm!r} not in the program-plan catalog")
    for attr in (spec.get("targeting") or {}):
        base = attr[:-4] if attr.endswith("_gte") else attr
        reg = ATTR_REGISTRY.get(base)
        if not reg:
            errs.append(f"attr_unknown: {attr!r}")
        elif unit_type and unit_type not in reg[1]:
            errs.append(f"attr_unit_incompatible: {attr!r} needs a users row "
                        f"(account unit); this experiment is {unit_type}")
    if not spec.get("exposure_surface"):
        errs.append("no_exposure_surface")
    # onboarding layer must use device units (FR-34)
    if layer == "onboarding" and unit_type != "device":
        errs.append("onboarding_layer_requires_device_unit")
    if for_launch:
        try:
            with db.ro_engine.connect() as conn:
                for other in _running_and_paused(conn, layer, spec.get("key")):
                    if bs is not None and be is not None and \
                            bs < other["bucket_end"] and other["bucket_start"] < be:
                        errs.append(
                            f"layer_overlap: buckets [{bs},{be}) collide with "
                            f"{other['key']} v{other['version']} "
                            f"[{other['bucket_start']},{other['bucket_end']})")
        except Exception:
            pass
    if errs:
        raise ExperimentError("; ".join(errs))


def _seed_guardrails(spec):
    g = list(dict.fromkeys(PFO_GUARDRAILS + list(spec.get("guardrails") or [])))
    return g


def create_experiment(spec: dict) -> dict:
    """Create a draft (or the next version of an existing key). Validates,
    stamps server fields, auto-attaches PFO guardrails."""
    validate_spec(spec)
    key = spec["key"]
    with db.engine.begin() as conn:
        prior = conn.execute(select(db.experiments_table.c.version).where(
            db.experiments_table.c.key == key).order_by(
            db.experiments_table.c.version.desc())).first()
        version = (prior[0] + 1) if prior else 1
        conn.execute(insert(db.experiments_table).values(
            key=key, version=version, layer=spec["layer"], status="draft",
            unit_type=spec["unit_type"], hypothesis=spec.get("hypothesis"),
            bucket_start=spec["bucket_start"], bucket_end=spec["bucket_end"],
            targeting_json=json.dumps(spec.get("targeting") or {}),
            variants_json=json.dumps(spec["variants"]),
            primary_metric=spec["primary_metric"],
            guardrails_json=json.dumps(_seed_guardrails(spec)),
            exposure_surface=spec["exposure_surface"],
            scope_json=json.dumps(spec.get("scope") or {}),
            mde=spec.get("mde"), alpha=spec.get("alpha", 0.05),
            power=spec.get("power", 0.80),
            override_underpowered=1 if spec.get("override_underpowered") else 0,
            created_at=_now()))
    invalidate_cache()
    return {"key": key, "version": version, "status": "draft"}


def transition(key: str, version: int, to: str, actor: str = "operator",
               reason: str = "", override_underpowered: bool = False) -> dict:
    """Status-machine transition. Illegal edge → ExperimentError (409).
    Launch (draft→running) re-validates + checks the underpowered gate."""
    with db.engine.begin() as conn:
        row = conn.execute(select(db.experiments_table).where(
            db.experiments_table.c.key == key,
            db.experiments_table.c.version == version)).mappings().first()
        if not row:
            raise ExperimentError("not_found")
        frm = row["status"]
        if (frm, to) not in _LEGAL_EDGES:
            raise ExperimentError(f"illegal_transition: {frm} -> {to}")
        if to == "running":
            spec = {
                "key": key, "layer": row["layer"], "unit_type": row["unit_type"],
                "bucket_start": row["bucket_start"], "bucket_end": row["bucket_end"],
                "variants": json.loads(row["variants_json"] or "[]"),
                "primary_metric": row["primary_metric"],
                "targeting": json.loads(row["targeting_json"] or "{}"),
                "exposure_surface": row["exposure_surface"],
            }
            validate_spec(spec, for_launch=True)
        vals = {"status": to}
        if to == "running" and not row["started_at"]:
            vals["started_at"] = _now()
        if to == "stopped":
            vals["ended_at"] = _now()
        conn.execute(update(db.experiments_table).where(
            db.experiments_table.c.key == key,
            db.experiments_table.c.version == version).values(**vals))
        conn.execute(insert(db.experiment_transitions_table).values(
            experiment_key=key, version=version, from_status=frm, to_status=to,
            actor=actor, reason=reason, at=_now()))
    invalidate_cache()
    return {"key": key, "version": version, "status": to}


def decide(key: str, version: int, decision: str, rationale: str = "",
           actor: str = "operator") -> dict:
    if decision not in ("ship", "revert", "iterate"):
        raise ExperimentError("decision must be ship|revert|iterate")
    with db.engine.begin() as conn:
        row = conn.execute(select(db.experiments_table.c.status).where(
            db.experiments_table.c.key == key,
            db.experiments_table.c.version == version)).first()
        if not row:
            raise ExperimentError("not_found")
        if row[0] != "stopped":
            raise ExperimentError("not_stopped: decide only from stopped")
        conn.execute(update(db.experiments_table).where(
            db.experiments_table.c.key == key,
            db.experiments_table.c.version == version).values(
            status="decided", decision=decision, decision_rationale=rationale,
            decided_at=_now()))
        conn.execute(insert(db.experiment_transitions_table).values(
            experiment_key=key, version=version, from_status="stopped",
            to_status="decided", actor=actor, reason=f"{decision}: {rationale}",
            at=_now()))
    invalidate_cache()
    return {"key": key, "version": version, "status": "decided", "decision": decision}


def revise(key: str, spec: dict) -> dict:
    """Mint a new draft version (edits to a running experiment are forbidden;
    this is the sanctioned path — metrics reset, prior readout archived)."""
    spec = dict(spec, key=key)
    return create_experiment(spec)


def list_experiments() -> list[dict]:
    with db.ro_engine.connect() as conn:
        rows = conn.execute(select(db.experiments_table).order_by(
            db.experiments_table.c.key, db.experiments_table.c.version.desc())
        ).mappings().all()
    return [{"key": r["key"], "version": r["version"], "layer": r["layer"],
             "status": r["status"], "primary_metric": r["primary_metric"],
             "created_at": r["created_at"], "started_at": r["started_at"],
             "decision": r["decision"]} for r in rows]


def get_experiment(key: str, version: int | None = None) -> dict | None:
    with db.ro_engine.connect() as conn:
        q = select(db.experiments_table).where(db.experiments_table.c.key == key)
        if version is not None:
            q = q.where(db.experiments_table.c.version == version)
        else:
            q = q.order_by(db.experiments_table.c.version.desc())
        row = conn.execute(q).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Readout (R9) + design calculator (LLD §4.5 / FR-42–46)
# ---------------------------------------------------------------------------

# metric_key → the event_type(s) that, produced by an exposed unit, count it as
# a "success" for a per-unit PROPORTION readout. (Beta-scale: assignment is the
# exposure proxy until experiment_exposed events flow — dilution is reported.)
_METRIC_EVENTS = {
    "wat": ["trade_proposed", "match_swiped", "calc_trade_evaluated"],
    "activation_rate": ["ranking_complete_first_time"],
    "like_rate": ["trade_proposed"],
    "board_completion_rate": ["ranking_complete_first_time"],
    "match_rate": ["trade_ratified"],
    "insult_rate": ["trade_flagged"],
}


def _variant_success(conn, key, version, metric_key):
    """For each variant: (assigned_n, success_n) where success = an assigned
    unit produced ≥1 of the metric's defining events after assignment."""
    from sqlalchemy import bindparam
    events = _METRIC_EVENTS.get(metric_key)
    rows = conn.execute(select(
        db.experiment_assignments_table.c.variant,
        db.experiment_assignments_table.c.unit_id,
        db.experiment_assignments_table.c.assigned_at).where(
        db.experiment_assignments_table.c.experiment_key == key,
        db.experiment_assignments_table.c.version == version)).mappings().all()
    by_variant: dict[str, dict] = {}
    for r in rows:
        by_variant.setdefault(r["variant"], {"units": {}, "n": 0})
        by_variant[r["variant"]]["units"][r["unit_id"]] = r["assigned_at"]
        by_variant[r["variant"]]["n"] += 1
    if not events:
        return by_variant, None    # non-proportion / dark metric
    # success = unit has a defining event at/after assignment.
    for variant, d in by_variant.items():
        succ = 0
        for unit, assigned_at in d["units"].items():
            q = text(
                "SELECT 1 FROM user_events WHERE user_id = :u "
                "AND event_type IN :ev AND occurred_at >= :a LIMIT 1"
            ).bindparams(bindparam("ev", expanding=True))
            hit = conn.execute(q, {"u": unit, "ev": events, "a": assigned_at}).first()
            succ += 1 if hit else 0
        d["success"] = succ
    return by_variant, events


def readout(key: str, version: int | None = None) -> dict:
    """Decision-grade readout: per-variant primary-metric proportions, the
    two-proportion z vs control, SRM, guardrail deltas, and a verdict withheld
    until horizon / suppressed on SRM red / honest below minimum n."""
    from . import analytics_stats as st
    exp = get_experiment(key, version)
    if not exp:
        raise ExperimentError("not_found")
    if exp["status"] == "draft":
        raise ExperimentError("not_started")
    version = exp["version"]
    variants = json.loads(exp["variants_json"] or "[]")
    weights = [int(v["weight_bp"]) for v in variants]
    names = [v["name"] for v in variants]
    with db.ro_engine.connect() as conn:
        by_variant, events = _variant_success(conn, key, version, exp["primary_metric"])
    arms = [{"variant": n,
             "n": by_variant.get(n, {}).get("n", 0),
             "success": by_variant.get(n, {}).get("success")} for n in names]
    observed = [a["n"] for a in arms]
    srm = st.srm_check(observed, weights) if sum(observed) else {
        "chi2": None, "df": None, "p_value": None, "red": False}

    control = arms[0]
    results = []
    min_n = 20
    for treat in arms[1:]:
        if events and control["n"] and treat["n"] and \
                control["success"] is not None and treat["success"] is not None:
            z = st.two_proportion_z(control["success"], control["n"],
                                    treat["success"], treat["n"],
                                    alpha=st.bonferroni(0.05, max(len(arms) - 1, 1)))
            results.append({"variant": treat["variant"], **z})
        else:
            results.append({"variant": treat["variant"], "error": "insufficient_or_dark"})

    total_n = sum(observed)
    horizon_reached = exp["status"] in ("stopped", "decided")
    below_min = total_n < min_n * len(arms)
    verdict = None
    banner = None
    if srm.get("red"):
        banner = "SRM detected (p<.001) — data-quality issue; verdict suppressed."
    elif below_min:
        banner = (f"n={total_n} across {len(arms)} arms — below the minimum for a "
                  f"trustworthy verdict at beta scale; showing counts only.")
    elif not horizon_reached:
        banner = "Verdict withheld until the experiment reaches its horizon (stopped)."
    else:
        # Primary-metric winner among treatments with p < adjusted alpha.
        sig = [r for r in results if r.get("p_value") is not None
               and r["p_value"] < st.bonferroni(0.05, max(len(arms) - 1, 1))
               and r.get("lift_abs", 0) > 0]
        verdict = ("ship:" + max(sig, key=lambda r: r["lift_abs"])["variant"]
                   if sig else "no_winner")

    return {
        "key": key, "version": version, "status": exp["status"],
        "primary_metric": exp["primary_metric"],
        "arms": arms, "results": results, "srm": srm,
        "exposure_note": "assignment used as exposure proxy (experiment_exposed "
                         "dark until the client SDK ships) — dilution not yet separable",
        "guardrails": json.loads(exp["guardrails_json"] or "[]"),
        "verdict": verdict, "banner": banner,
        "decision": exp["decision"], "decision_rationale": exp["decision_rationale"],
    }


def preview(spec: dict) -> dict:
    """Design-time power/duration calculator (FR-42). Needs a baseline rate,
    MDE, arms, and eligible-traffic/week; returns n/arm, weeks, MDE-in-2/4/8w,
    and the beta-honesty banner."""
    from . import analytics_stats as st
    p = float(spec.get("baseline_rate", 0.3))
    mde = float(spec.get("mde", 0.05))
    arms = len(spec.get("variants") or [{}, {}])
    eligible = float(spec.get("eligible_per_week", 0) or 0)
    return st.design_calculator(p, mde, arms, eligible,
                                alpha=float(spec.get("alpha", 0.05)),
                                power=float(spec.get("power", 0.80)))
