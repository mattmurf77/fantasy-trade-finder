"""Pure private input provenance. Collection only; never a model input.

Bindings live with one pool entry, not in a global object-ID registry. They
retain actual object references so recycled IDs or equal replacement Players
cannot inherit another incarnation's source evidence.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import copy
import json
import math


VERSION = "owner-age-evidence-1"


def _age(value):
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            result = int(value)
        elif isinstance(value, (int, float)) and math.isfinite(value) and int(value) == value:
            result = int(value)
        else:
            return None
        return result if result > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _observed_at(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def age_row(raw, enriched=None):
    """Mirror the existing source priority without changing its public age.

    The DB branch uses its truthy age verbatim. The raw branch first coerces
    to int, then uses 25 if false. Invalid selected data remains Unknown even
    when that legacy conversion could manufacture a positive integer.
    """
    db_age = (enriched or {}).get("age")
    raw_age = raw.get("age")
    source, selected, imputed = "players_db", db_age, False
    if not db_age:
        source, selected = "sleeper_cache", raw_age
        try:
            if not int(raw_age or 0):
                source, selected, imputed = "default", None, True
        except (ValueError, TypeError, OverflowError):
            imputed = None  # This would not have been a successful legacy build.
    age = _age(selected)
    observed = _observed_at((enriched or {}).get("last_synced")) if source == "players_db" else None
    return {"age": age, "source": source, "imputed": imputed,
            "state": "imputed" if imputed else "observed" if age is not None else "invalid",
            "observed_at": observed,
            "observation_basis": "players.last_synced" if observed else None}


def _is_pick(player):
    return getattr(player, "position", None) == "PICK" or getattr(player, "team", None) == "PICK"


def _attributes(player):
    # Type tags distinguish True from 1, and repr freezes malformed/nonfinite
    # values without putting them into JSON or retaining mutable attributes.
    return tuple((type(value).__name__, repr(value)) for value in
                 (getattr(player, key, None) for key in ("id", "position", "team", "age", "pick_value")))


def _unknown(player, reason):
    pick = _is_pick(player)
    return {"age": None, "source": "not_applicable" if pick else "unknown",
            "imputed": None, "state": "not_applicable" if pick else "unknown",
            "observed_at": None, "observation_basis": None,
            "reason": "pick_asset" if pick else reason}


@dataclass(frozen=True)
class _BoundAge:
    player: object
    attributes: tuple
    row_json: str

    def row(self, pid, player):
        if self.player is not player or getattr(player, "id", None) != pid:
            return _unknown(player, "pool_player_mismatch")
        if self.attributes != _attributes(player):
            return _unknown(player, "player_attributes_changed")
        return json.loads(self.row_json)

    def __deepcopy__(self, memo):
        # Copying a context must not rebind proof to freshly copied Players.
        return self


def _bind(player, row):
    return _BoundAge(player, _attributes(player), json.dumps(row, sort_keys=True, allow_nan=False))


class CapturedInputEvidence:
    def __init__(self, rows):
        self._rows = dict(rows)

    def as_dict(self, players):
        return {"schema_version": VERSION, "used_in_model": False,
                "age": {pid: (self._rows[pid].row(pid, player) if pid in self._rows
                              else _unknown(player, "capture_player_missing"))
                        for pid, player in players.items()}}


class PoolInputEvidence:
    """Optional build collector; committed atomically beside its pool objects."""
    def __init__(self):
        self._rows = {}

    def record(self, player, *, raw, enriched=None):
        row = _unknown(player, "pick_asset") if _is_pick(player) else age_row(raw, enriched)
        self._rows[player.id] = _bind(player, row)

    def capture(self, players):
        rows = {}
        for pid, player in players.items():
            bound = self._rows.get(pid)
            if bound:
                # Freeze pre-copy identity validation while retaining the
                # original signature, never a fresh mutable attribute read.
                row = bound.row(pid, player)
                rows[pid] = _BoundAge(bound.player, bound.attributes,
                                     json.dumps(row, sort_keys=True, allow_nan=False))
            else:
                rows[pid] = _bind(player, _unknown(player, "pool_evidence_missing"))
        return CapturedInputEvidence(rows)


class OwnerInputContext(dict):
    """Strict generator kwargs plus a separate collection-only attribute.

    Ordinary dict(context), context.copy(), or **context drops this channel.
    Generation never depends on it; later capture explicitly records Unknown.
    """
    def __init__(self, values, evidence):
        super().__init__(values)
        self._input_evidence = evidence


def request_evidence(context):
    captured = getattr(context, "_input_evidence", None)
    if isinstance(captured, CapturedInputEvidence):
        return captured.as_dict(context["players"])
    return {"schema_version": VERSION, "used_in_model": False,
            "age": {pid: _unknown(player, "context_evidence_missing")
                    for pid, player in context["players"].items()}}


def detached_context(values, pool_evidence):
    """Validate original pool identity, then explicitly bind owned input copies.

    This is the sole supported rebind: arbitrary subsequent copying cannot
    manufacture a new pool incarnation. Both the original and copied relevant
    attributes must still agree with the pre-copy binding.
    """
    # Own the selected map before validation/copy. A later live-map replacement
    # must neither authenticate foreign evidence nor invalidate this snapshot.
    selected_players = dict(values["players"])
    captured = pool_evidence.capture(selected_players)
    cloned = copy.deepcopy({**values, "players": selected_players})
    rows = {}
    for pid, player in cloned["players"].items():
        original = captured._rows[pid]
        row = json.loads(original.row_json)
        if original.attributes != _attributes(player):
            row = _unknown(player, "player_changed_during_capture")
        rows[pid] = _bind(player, row)
    return OwnerInputContext(cloned, CapturedInputEvidence(rows))


def project_evidence(evidence, assets):
    """Exact offered rows only; the request hash joins the complete capture."""
    return {**evidence, "age": {pid: row for pid, row in evidence.get("age", {}).items()
                               if pid in assets}}
