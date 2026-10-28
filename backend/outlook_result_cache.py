"""In-process result cache for `GET /api/league/outlook` (c2-eng-backend-2).

`run_outlook` is 10,000 pure-Python season sims (0.3-3.5 s on an M1), and prod
runs one gunicorn worker with four threads, so every uncached run holds the GIL
and starves the other request threads. The sim is deterministic per input
(`simulator.py` seeds a local `random.Random(stable_hash(league_id) ^
outlook_seed)` and never touches global `random`), so a stored result is the
answer an uncached run would give.

Correctness comes from the key, not the TTL:
  - `league_id`, `basis`, `scoring_format`, plus the caller's user id only when
    `basis == "personal"` (the caller's own board feeds the values);
  - a SHA-256 of canonical JSON (sorted keys) of every input `run_outlook`
    reads: the whole `LeagueState` (teams, rosters, records, schedule, weekly
    scores, settings incl. median match and playoff shape, plus any attribute
    attached after construction), the `player_value` / `player_pos` maps, the
    whole `model_config` dict, `playoff_seed_type`, and the configured strength
    source (`FTF_OUTLOOK_STRENGTH_SOURCE`). Any change to rosters, records or
    schedule is a miss by construction.

The bounds (6 h TTL, 256 entries, LRU) only cap memory.

Caller-specific output: the only field in the payload that depends on the
caller is `teams[].is_you` (`backend/outlook/serialize.py`). The route computes
the payload with `you_user_id=""`, which makes the stored value
caller-independent, and `for_caller()` deep-copies it and stamps `is_you` for
the current caller with the serializer's own rule. A stored payload is never
handed out or mutated.

Single-flight: concurrent misses on one key run ONE computation; the rest wait
and share its result. If it raises, nothing is stored and every waiter gets the
same exception (a waiter that recomputed would hold the GIL for another full
run). Errors, including the `NotImplementedError` behind the route's 501, are
never cached.

Hit/miss/coalesced/error counters live in `OUTLOOK_RESULTS.stats` and go to the
debug log only; they are never part of an API response.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable

log = logging.getLogger(__name__)

TTL_SECONDS = 6 * 3600.0
MAX_ENTRIES = 256


def _canon(obj):
    """`json.dumps` fallback: dataclasses as their attribute dict (fields plus
    anything attached later, e.g. `state.playoff_seed_type`), sets sorted."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return vars(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=lambda v: json.dumps(v, sort_keys=True, default=_canon))
    raise TypeError(f"outlook result cache cannot hash {type(obj).__name__}")


def input_digest(**inputs) -> str:
    """Order-independent SHA-256 of `inputs` (canonical JSON, sorted keys)."""
    blob = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=_canon)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def make_key(*, league_id: str, basis: str, scoring_format: str | None,
             user_id: str, state, player_value: dict, player_pos: dict,
             model_cfg: dict, playoff_seed_type, strength_source: str) -> tuple:
    """The cache key for one `run_outlook` call (see the module docstring)."""
    return (
        league_id, basis, scoring_format,
        user_id if basis == "personal" else "",
        input_digest(state=state, player_value=player_value,
                     player_pos=player_pos, model_cfg=model_cfg,
                     playoff_seed_type=playoff_seed_type,
                     strength_source=strength_source),
    )


def for_caller(payload: dict, you_user_id: str) -> dict:
    """A private copy of a stored payload with `is_you` set for this caller,
    by the same rule as `StandardSerializer`."""
    out = copy.deepcopy(payload)
    for t in out["teams"]:
        t["is_you"] = bool(you_user_id) and t["user_id"] == you_user_id
    return out


class _Flight:
    """One in-progress computation that other threads can wait on."""
    __slots__ = ("done", "value", "error")

    def __init__(self):
        self.done = threading.Event()
        self.value = None
        self.error: BaseException | None = None


class OutlookResultCache:
    def __init__(self, ttl_seconds: float = TTL_SECONDS,
                 max_entries: int = MAX_ENTRIES,
                 clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self._inflight: dict[tuple, _Flight] = {}
        self.stats = {"hits": 0, "misses": 0, "coalesced": 0, "errors": 0}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            for k in self.stats:
                self.stats[k] = 0

    def get_or_compute(self, key: tuple, compute: Callable[[], dict]) -> dict:
        """The stored value for `key`, computing it once if absent or expired.
        Treat the result as read-only and pass it through `for_caller()`."""
        with self._lock:
            hit = self._entries.get(key)
            if hit is not None and self._clock() - hit[0] < self._ttl:
                self._entries.move_to_end(key)
                self.stats["hits"] += 1
                log.debug("outlook result cache hit %s", self.stats)
                return hit[1]
            if hit is not None:
                del self._entries[key]
            flight = self._inflight.get(key)
            leader = flight is None
            if leader:
                flight = self._inflight[key] = _Flight()
                self.stats["misses"] += 1
            else:
                self.stats["coalesced"] += 1
            log.debug("outlook result cache %s %s",
                      "miss" if leader else "coalesced", self.stats)

        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value

        try:
            flight.value = compute()
        except BaseException as e:
            flight.error = e
            with self._lock:
                self.stats["errors"] += 1
            raise
        else:
            with self._lock:
                self._entries[key] = (self._clock(), flight.value)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max:
                    self._entries.popitem(last=False)
            return flight.value
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            flight.done.set()


OUTLOOK_RESULTS = OutlookResultCache()
