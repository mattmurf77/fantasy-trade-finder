"""Offline owner-input observations; never a serving or proof-reuse certificate.

No route imports this module. Captures are non-atomic observations of declared
dependencies. Materialization returns evaluator kwargs, not a provider-bound
OwnerInputContext. Existing evaluation/currentness/quality gates remain required.
"""
from dataclasses import dataclass, field, fields
import hashlib
import json
import marshal
import math
from pathlib import Path
import sys
from types import FunctionType


VERSION = "owner-input-observation-1"
CONTEXT_KEYS = frozenset((
    "players", "league", "user_id", "user_roster", "user_elo", "seed_elo",
    "scoring_format", "fairness_threshold", "outlook", "opponent_outlooks",
    "inferred_outlooks", "user_sources", "opponent_sources", "manager_preferences",
    "acquire_positions", "trade_away_positions", "avoid_positions",
    "pinned_give_players", "pinned_receive_players", "exact_give", "opponent_user_id",
    "trade_intent", "swap_positions", "lateral_scope", "past_decision_keys",
    "exclusion_keys", "max_cards", "config", "input_evidence"))
REQUIRED_CONTEXT = ("players", "league", "user_id", "user_roster", "user_elo", "seed_elo")
AMBIENT_KEYS = ("effective_trade_config", "raw_owner_limits", "ranking_config",
                "feature_flags", "stud_tax_mode", "static_data", "source_files", "runtime")
SOURCE_FILES = ("trade_gen_owner.py", "trade_gen_bilateral.py", "trade_gen_bilateral_candidate.py",
                "trade_gen_outlook_evidence.py", "trade_service.py", "ranking_service.py",
                "trade_roster.py", "pick_values.py", "trade_input_evidence.py", "feature_flags.py",
                "owner_evaluation_inputs.py")
STATIC_KEYS = ("model_constants", "ordered_tiers", "tier_config", "roster_eligibility",
               "unavailable", "generic_pick_seeds", "age_now", "age_future", "outlook_alpha_keys",
               "optional_proof_decoder_enabled")
UNBOUND_DEPENDENCIES = (
    "cross-source atomicity and ABA revisions",
    "proof that evaluation consumed these observations",
    "all transitive loaded-code/constant overrides, decoder internals and mutable memo contents",
    "set iteration layout and cross-runtime execution equivalence",
    "original mutable alias topology and object identity",
    "provider changes not yet ingested",
    "account lifetime, authorization, job supersession and final serving gates",
)


class UnsupportedOwnerInput(ValueError):
    def __init__(self, reason, path):
        self.reason, self.path = reason, path
        super().__init__(f"{reason} at {path}")


def _records():
    from .ranking_service import Player
    from .trade_service import League, LeagueMember
    return {cls.__name__: cls for cls in (Player, LeagueMember, League)}


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except ValueError:
        # A native int can exceed Python's configurable JSON digit limit.
        # This also covers encoding set members for canonical ordering.
        raise UnsupportedOwnerInput("input_encoding_limit", "input") from None


def _freeze(value, path, active, records):
    """Build an owned tagged tree without custom serializers or source aliases."""
    kind = type(value)
    if value is None:
        return ("none",)
    if kind in (str, bool, int):
        return (kind.__name__, value)
    if kind is float:
        if not math.isfinite(value):
            raise UnsupportedOwnerInput("nonfinite_number", path)
        return ("float", value.hex())  # Preserve negative zero and exact bits.
    if kind not in (dict, list, tuple, set, frozenset, *records.values()):
        raise UnsupportedOwnerInput("unsupported_type", path)
    if id(value) in active:
        raise UnsupportedOwnerInput("cyclic_input", path)
    active.add(id(value))
    try:
        if kind in records.values():
            data = vars(value)
            names = {item.name for item in fields(value)}
            if type(data) is not dict or data.keys() != names:
                raise UnsupportedOwnerInput("record_attribute_schema", path)
            return ("record", kind.__name__, _freeze(data, path, active, records))
        if kind is dict:
            # Preserve iteration order: sorting a board/config map is not an
            # established equivalent execution contract for the owner engines.
            return ("dict", tuple((_freeze(k, path + ".key", active, records),
                                   _freeze(v, path + ".value", active, records))
                                  for k, v in value.items()))
        items = tuple(_freeze(v, path + "[]", active, records) for v in value)
        if kind in (set, frozenset):
            items = tuple(sorted(items, key=_json))
        return (kind.__name__, items)
    finally:
        active.remove(id(value))


def _thaw(node, records):
    kind = node[0]
    if kind == "none":
        return None
    if kind in ("str", "bool", "int"):
        return node[1]
    if kind == "float":
        return float.fromhex(node[1])
    if kind == "record":
        return records[node[1]](**_thaw(node[2], records))
    if kind == "dict":
        return {_thaw(k, records): _thaw(v, records) for k, v in node[1]}
    constructors = {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}
    return constructors[kind](_thaw(v, records) for v in node[1])


@dataclass(frozen=True)
class OwnerInputEnvelope:
    schema_version: str
    model_version: str
    fingerprint: str
    payload_json: str = field(repr=False)

    @property
    def unbound_dependencies(self):
        return UNBOUND_DEPENDENCIES

    def _read(self, key):
        return _thaw(json.loads(self.payload_json)[key], _records())

    def evaluator_kwargs(self):
        """Detached kwargs only. Never restores object-bound source authority."""
        return self._read("context")

    def ambient_observation(self):
        return self._read("ambient")

    def provenance_observation(self):
        return self._read("provenance")


@dataclass(frozen=True)
class CaptureResult:
    envelope: OwnerInputEnvelope | None = None
    reason: str | None = None
    path: str | None = None


def _models():
    from . import trade_gen_owner, trade_gen_bilateral
    from . import trade_gen_bilateral_candidate, trade_gen_outlook_evidence
    return {module.VERSION: module for module in (
        trade_gen_owner, trade_gen_bilateral, trade_gen_bilateral_candidate, trade_gen_outlook_evidence)}


def _required_mapping(value, keys, path):
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise UnsupportedOwnerInput("unsupported_ambient_mapping", path)
    for key in keys:
        if key not in value:
            raise UnsupportedOwnerInput("missing_ambient_dependency", path + "." + key)


def _primitive_model_constants(module):
    # Declared primitive tables/thresholds, not an attestation of every loaded
    # object (compiled regexes/callables/extensions remain explicit limitations).
    return {name: value for name, value in vars(module).items()
            if name.isupper() and type(value) in (str, int, float, bool, dict, list, tuple, set, frozenset)}


def _ambient_inventory(ambient):
    from . import feature_flags as ff, ranking_service as ranking, trade_service as ts
    from . import trade_gen_owner as owner
    _required_mapping(ambient, AMBIENT_KEYS, "ambient")
    for key, required in (("effective_trade_config", ts._DEFAULT_CFG),
                          ("raw_owner_limits", owner._LIMITS),
                          ("ranking_config", ranking._DEFAULT_CFG),
                          ("feature_flags", ff.DEFAULT_FLAGS),
                          ("static_data", STATIC_KEYS), ("source_files", SOURCE_FILES),
                          ("runtime", ("python", "implementation", "byteorder", "string_hash_observation"))):
        _required_mapping(ambient[key], required, "ambient." + key)
    _required_mapping(ambient["static_data"]["model_constants"],
                      (module.__name__ for module in _models().values()),
                      "ambient.static_data.model_constants")
    for module in _models().values():
        _required_mapping(ambient["static_data"]["model_constants"][module.__name__],
                          _primitive_model_constants(module),
                          "ambient.static_data.model_constants." + module.__name__)


def _validate_provenance_binding(captured, records):
    from .trade_input_evidence import CapturedInputEvidence, _BoundAge
    if type(captured) is not CapturedInputEvidence or set(vars(captured)) != {"_rows"}:
        raise UnsupportedOwnerInput("unsupported_provenance_binding", "provenance")
    rows = captured._rows
    if type(rows) is not dict or any(type(pid) is not str for pid in rows):
        raise UnsupportedOwnerInput("unsupported_provenance_binding", "provenance.rows")
    for bound in rows.values():
        if (type(bound) is not _BoundAge or set(vars(bound)) != {"player", "attributes", "row_json"}
                or type(bound.player) is not records["Player"] or type(bound.row_json) is not str
                or type(bound.attributes) is not tuple
                or any(type(pair) is not tuple or len(pair) != 2
                       or any(type(value) is not str for value in pair) for pair in bound.attributes)):
            raise UnsupportedOwnerInput("unsupported_provenance_binding", "provenance.rows[]")
        # Reject unsafe nested attributes before the known row method reads
        # them. This validates representation only; it never rebinds a player.
        _freeze(bound.player, "provenance.player", set(), records)


def capture_owner_inputs(context, *, model_version, ambient):
    """Observe supported inputs without interpreting equality as permission.

    Caller controls isolation. This does not prove that capture was coherent or
    that a subsequent evaluation used these ambient values. Unsupported values
    return a reason, never a lossy projection or a partial success.
    """
    from .trade_input_evidence import OwnerInputContext, request_evidence
    try:
        if type(context) not in (dict, OwnerInputContext):
            raise UnsupportedOwnerInput("unsupported_context_type", "context")
        if type(model_version) is not str or model_version not in _models():
            raise UnsupportedOwnerInput("unknown_model", "model_version")
        if any(type(key) is not str or key not in CONTEXT_KEYS for key in context):
            raise UnsupportedOwnerInput("unknown_context_key", "context")
        for key in REQUIRED_CONTEXT:
            if key not in context:
                raise UnsupportedOwnerInput("missing_context_key", "context." + key)
        _ambient_inventory(ambient)
        if type(context) is OwnerInputContext and set(vars(context)) != {"_input_evidence"}:
            raise UnsupportedOwnerInput("unsupported_context_attributes", "context")
        records = _records()
        if type(context["players"]) is not dict:
            raise UnsupportedOwnerInput("unsupported_player_map", "context.players")
        if any(type(key) is not str or type(value) is not records["Player"]
               for key, value in context["players"].items()):
            raise UnsupportedOwnerInput("unsupported_player_record", "context.players")
        if type(context["league"]) is not records["League"]:
            raise UnsupportedOwnerInput("unsupported_league_record", "context.league")
        # Validate/copy the entire kwargs graph before any source-evidence
        # helper can deepcopy its explicit v3 values.
        frozen_context = _freeze(dict(context), "context", set(), records)
        if type(context) is OwnerInputContext:
            _validate_provenance_binding(context._input_evidence, records)
        try:
            provenance = {"kind": "observation_not_rebound", "rows": request_evidence(context)}
        except (AttributeError, TypeError, ValueError):
            raise UnsupportedOwnerInput("unsupported_source_evidence", "provenance") from None
        payload = {"schema_version": VERSION, "model_version": model_version,
                   "context": frozen_context,
                   "ambient": _freeze(ambient, "ambient", set(), records),
                   "provenance": _freeze(provenance, "provenance", set(), records)}
        raw = _json(payload)
        return CaptureResult(OwnerInputEnvelope(VERSION, model_version,
            hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw))
    except UnsupportedOwnerInput as exc:
        return CaptureResult(reason=exc.reason, path=exc.path)
    except RecursionError:
        return CaptureResult(reason="input_nesting_limit", path="input")
    except RuntimeError:
        return CaptureResult(reason="input_changed_during_copy", path="input")


def _callable_observation(fn):
    if type(fn) is not FunctionType or fn.__closure__:
        raise UnsupportedOwnerInput("unsupported_ambient_callable", "ambient.age_curves")
    return {"module": fn.__module__, "name": fn.__qualname__,
            "code_sha256": hashlib.sha256(marshal.dumps(fn.__code__)).hexdigest(),
            "defaults": fn.__defaults__, "kwdefaults": fn.__kwdefaults__}


def observe_ambient_inputs():
    """Read declared ambient dependencies for OFFLINE callers only.

    This may initialize the existing flag cache; it never reloads config, calls
    a provider/database, changes a flag or installs captured globals. File hashes
    do not attest every loaded function; explicit unbound dependencies remain.
    """
    from . import feature_flags as ff, ranking_service as ranking, trade_service as ts
    from . import trade_gen_owner as owner, trade_roster, pick_values, trade_input_evidence
    if type(ts._cfg) is not dict or type(getattr(ts._cfg_local, "map", None)) not in (dict, type(None)):
        raise UnsupportedOwnerInput("unsupported_config_mapping", "ambient.effective_trade_config")
    if ts.FLAGS is not ff.FLAGS or type(ff.FLAGS) is not ff._FlagsProxy:
        raise UnsupportedOwnerInput("unsupported_flag_proxy", "ambient.feature_flags")
    if type(ff._flags_cache) not in (dict, type(None)):
        raise UnsupportedOwnerInput("unsupported_flag_mapping", "ambient.feature_flags")
    flags = ff.flags_dict()
    if any(type(key) is not str or type(value) is not bool for key, value in flags.items()):
        raise UnsupportedOwnerInput("unsupported_flag_value", "ambient.feature_flags")
    # is_enabled returns False for missing cache keys, even where the shipped
    # default is True. Bind that actual effective state, not a default fill.
    flags = {**dict.fromkeys(ff.DEFAULT_FLAGS, False), **flags}
    if type(ts._AGE_NOW_CURVE) is not dict or type(ts._AGE_FUTURE_CURVE) is not dict:
        raise UnsupportedOwnerInput("unsupported_age_curve_mapping", "ambient.age_curves")
    constants = {}
    for module in _models().values():
        constants[module.__name__] = _primitive_model_constants(module)
    observed = {
        "effective_trade_config": {key: ts._c(key) for key in ts._DEFAULT_CFG},
        "raw_owner_limits": {key: ts._cfg.get(key, default) for key, default in owner._LIMITS.items()},
        "ranking_config": {key: ranking._c(key) for key in ranking._DEFAULT_CFG},
        "feature_flags": flags, "stud_tax_mode": ts.current_stud_tax_mode(),
        "static_data": {"model_constants": constants, "ordered_tiers": ranking.ORDERED_TIERS,
            "tier_config": ranking.TIER_CONFIG, "roster_eligibility": trade_roster.ELIGIBILITY,
            "unavailable": trade_roster.UNAVAILABLE, "generic_pick_seeds": pick_values.GENERIC_PICK_SEEDS,
            "age_now": {key: _callable_observation(fn) for key, fn in ts._AGE_NOW_CURVE.items()},
            "age_future": {key: _callable_observation(fn) for key, fn in ts._AGE_FUTURE_CURVE.items()},
            "outlook_alpha_keys": ts._OUTLOOK_ALPHA_CFG_KEY,
            "optional_proof_decoder_enabled": owner._fast_json is not None},
        "source_files": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                         for name in SOURCE_FILES},
        "runtime": {"python": sys.version, "implementation": sys.implementation.cache_tag,
                    "byteorder": sys.byteorder, "string_hash_observation": hash("owner-input-observation-1")},
    }

    records = _records()
    return _thaw(_freeze(observed, "ambient", set(), records), records)
