"""Draft board payload builder (rookie-draft M3 — plan §M3, lld §4.4).

ONE versioned read-only payload (`schema: 1`) describing a league's rookie
draft: what the order is, which picks have been made, who owns each slot, and
which rookies are still on the board.

Three properties are structural rather than conventional, because each is a
named failure this design exists to prevent:

* **No Flask, no ``server`` import.** Everything upstream arrives through an
  injected :class:`Fetchers`. The route (next wave) is a ~15-line shim; the
  M1 replay corpora drive this module directly, with no app context.
* **The divergence rule (I-7).** This module NEVER imports
  ``database.load_draft_picks``. The draft object is truth for the board;
  ``draft_picks`` rows are truth for *pre-draft ownership* only, are read by
  the route, and are passed in. #228 deletes the season's ``draft_picks`` rows
  when a draft completes — a board sourced from them empties at the finish
  line. ``test_draft_board.py`` asserts the import graph.
* **No platform writes (I-8, D9).** No POST, no PUT, no ``sleeper_write``
  import. The terminal CTA is ``deep_link``.

**The order gate (D5).** ``order_confidence`` is ``"assigned"`` *iff*
``detail["draft_order"]`` is non-null. A pre-draft Sleeper draft returns
``slot_to_roster_id = {"1":1 … "12":12}`` — an identity map that looks exactly
like a real order and is not one. Reading it invents a draft order. Nothing in
this module reads ``slot_to_roster_id`` at all; slot → roster is resolved
through ``draft_order`` (user → slot) composed with the rosters list
(user → roster), which is only defined when the order actually exists.

**The poll rule (D6).** Complete drafts are CDN-cached ~24 h, so polling
``/draft/<id>/picks`` directly reads a stale list while believing it is live.
Instead: poll the 1.2 KB detail object (``s-maxage=30``) and fetch the 20 KB
pick list only when ``last_picked`` moves.

Deviations from the LLD, recorded here rather than silently:

1. **``Fetchers`` gains ``users``, ``rookie_ids`` and ``players``.** The
   payload's ``owner_username`` has no source in the LLD's fetcher list, and
   ``_undrafted`` was specced calling ``database`` directly — which would make
   this module untestable without a seeded DB. Both are injected;
   :func:`database_rookie_ids` / :func:`database_players` are the production
   bindings (``load_rookie_player_ids`` is still THE predicate).
2. **The single-flight lock is keyed ``(platform, league_id)``**, not the full
   cache key: ``draft_id`` is only known *after* the first upstream read. The
   cache entry is still stored under the LLD's ``(platform, league_id,
   draft_id)`` key once resolved.
3. **MFL renders ``undrafted`` only when the caller injects a player map.**
   MFL pick ids are MFL-space; subtracting them from our rookie ids without a
   crosswalk would silently under-count. Absent the map the list is suppressed
   honestly (``undrafted_suppressed: true``) rather than computed wrongly.
   M5 wires the crosswalk that lifts this.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from . import draft_status

log = logging.getLogger(__name__)

SCHEMA = 1

# ── Closed enums (lld §2.1) ───────────────────────────────────────────────
SLEEPER = "sleeper"
MFL = "mfl"

UPCOMING = "upcoming"
LIVE = "live"
COMPLETE = "complete"
UNAVAILABLE = "unavailable"

KIND_ROOKIE = "rookie"
KIND_STARTUP = "startup"
KIND_UNKNOWN = "unknown"

ORDER_ASSIGNED = "assigned"
ORDER_UNSET = "unset"
ORDER_UNKNOWN = "unknown"

BASIS_CONSENSUS = "consensus"
BASIS_MY_BOARD = "my_board"

REASON_UPSTREAM_ERROR = "upstream_error"
REASON_BREAKER_OPEN = "breaker_open"
REASON_BUDGET_EXCEEDED = "budget_exceeded"
REASON_AUTH_EXPIRED = "auth_expired"

NOTICE_ORDER_NOT_SET = "order_not_set"
NOTICE_STARTUP_DRAFT = "startup_draft"
NOTICE_PLATFORM_UNSUPPORTED = "platform_unsupported"
NOTICE_CLASS_NOT_LOADED = "class_not_loaded"
NOTICE_MFL_RECONNECT = "mfl_reconnect"

_NOTICE_MESSAGES = {
    NOTICE_ORDER_NOT_SET: "The draft order is not set yet — showing who owns each round.",
    NOTICE_STARTUP_DRAFT: "Startup draft — rookie list hidden.",
    NOTICE_PLATFORM_UNSUPPORTED: "Draft rooms are available for Sleeper and MyFantasyLeague.",
    NOTICE_CLASS_NOT_LOADED: "This rookie class has not loaded yet.",
    NOTICE_MFL_RECONNECT: "Reconnect MyFantasyLeague to refresh this draft.",
}

# Sleeper's `status` vocabulary → our `state`. Treated as an OPEN set: an
# unrecognised status reads as `upcoming`, which is the conservative end (it
# never claims picks were made). Mirrors
# backend/tests/support/draft_replay.SLEEPER_STATUS_TO_STATE.
SLEEPER_STATUS_TO_STATE = {
    "pre_draft": UPCOMING,
    "drafting": LIVE,
    "paused": LIVE,
    "complete": COMPLETE,
}

# ── Cache / budget / breaker constants (lld §3.1) ─────────────────────────
_TTL_BY_STATE = {UPCOMING: 300, LIVE: 20, COMPLETE: 86_400, UNAVAILABLE: 60}
_LEAGUE_META_TTL_SECONDS = 300      # drafts/rosters/users/traded_picks change slowly
_CACHE_MAX_ENTRIES = 200
_BREAKER_FAILS = 3
_BREAKER_OPEN_SECONDS = 120
_BUDGET_WINDOW_SECONDS = 60.0
_BUDGET_PER_MIN = 3                 # upstream refresh cycles per draft (D6)

# ── Unbounded-resource guards (lld §5.3) ──────────────────────────────────
_UNDRAFTED_CAP = 300                # the class is ~250 skill players; a hit is a bug
_ORDER_CAP = 500                    # rounds x teams; refuse beyond

_POSITIONS = ("QB", "RB", "WR", "TE")

_cache: dict[tuple[str, str, str], "_Entry"] = {}
_cache_lock = threading.Lock()
_inflight: dict[tuple[str, str], threading.Lock] = {}


def _now_monotonic() -> float:
    """Module-level indirection so M1's :class:`FakeClock` can replace it.

    Tests do ``monkeypatch.setattr(draft_board_service, "_now_monotonic",
    clock)`` rather than patching the stdlib, which is why every TTL/breaker/
    budget comparison in this file goes through here.
    """
    return time.monotonic()


def _now_iso() -> str:
    """ISO-8601 UTC, matching ``database._now()``."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Request / injection surface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardRequest:
    """Everything the caller knows; nothing this module can look up itself."""

    league_id: str
    platform: str
    season: int
    user_id: str | None = None
    basis: str = BASIS_CONSENSUS
    #: Caller-supplied per-player Elo for ``basis="my_board"``.
    board_elo: Mapping[str, float] | None = None
    #: Consensus seed Elo (the universal pool). The LLD left this source
    #: unstated; it lives in ``server``'s pool globals, so it is injected.
    consensus_elo: Mapping[str, float] | None = None
    #: MFL only — the export host and the year of the ``draftResults`` grid.
    mfl_host: str | None = None
    mfl_year: int | None = None
    #: MFL only — franchise id → our user id, and MFL player id → our player id.
    mfl_franchise_to_user: Mapping[str, str] | None = None
    mfl_player_ids: Mapping[str, str] | None = None
    #: Rostered player ids in OUR id space, for platforms whose rosters this
    #: module does not fetch (MFL). Sleeper derives them from ``rosters``.
    rostered_ids: Sequence[str] | None = None
    #: Platform draft-room URL. Never a write (D9).
    deep_link: str | None = None


class Fetchers(Protocol):
    """Upstream reads, injected so this module is import-free of Flask.

    Implementations may raise; :func:`build_board` owns the error policy and
    turns a raise into ``degraded``/``stale``, never a 5xx.
    """

    def drafts(self, league_id: str) -> list[dict]: ...
    def draft_detail(self, draft_id: str) -> dict | None: ...
    def draft_picks(self, draft_id: str) -> list[dict]: ...
    def traded_picks(self, league_id: str) -> list[dict]: ...
    def rosters(self, league_id: str) -> list[dict]: ...
    def users(self, league_id: str) -> list[dict]: ...
    def mfl_draft_results(self, league_id: str, year: int, host: str) -> dict | None: ...
    def rookie_ids(self, season: int) -> set[str]: ...
    def players(self, player_ids: Sequence[str]) -> dict[str, dict]: ...


def database_rookie_ids(season: int) -> set[str]:
    """THE rookie predicate (`docs/cross-client-invariants.md § Rookie predicate`).

    Lazily imported so this module stays importable without a database.
    """
    from .database import load_rookie_player_ids
    return load_rookie_player_ids(int(season))


def database_players(player_ids: Sequence[str]) -> dict[str, dict]:
    from .database import load_players_by_ids
    return load_players_by_ids([str(p) for p in player_ids])


@dataclass
class PlatformFetchers:
    """Concrete :class:`Fetchers` over injectable callables.

    ``sleeper_get`` is ``server._sleeper_get`` in production — which also buys
    fixture replay for free (the ``FTF_SLEEPER_FIXTURES_DIR`` seam, A-7).
    ``mfl_opener`` is threaded all the way down to
    ``mfl_service.fetch_draft_results`` so the committed MFL grids can drive
    the MFL path (RB-3); without it M5 would be untestable.
    """

    sleeper_get: Callable[[str], Any] | None = None
    mfl_opener: Any = None
    mfl_cookie: str | None = None
    rookie_ids_fn: Callable[[int], set[str]] = database_rookie_ids
    players_fn: Callable[[Sequence[str]], dict[str, dict]] = database_players

    _BASE = "https://api.sleeper.app/v1"

    def _get(self, path: str):
        if self.sleeper_get is None:
            raise RuntimeError("PlatformFetchers has no sleeper_get injected")
        return self.sleeper_get(f"{self._BASE}/{path}")

    # ── Sleeper ──
    def drafts(self, league_id: str) -> list[dict]:
        return _as_list(self._get(f"league/{league_id}/drafts"))

    def draft_detail(self, draft_id: str) -> dict | None:
        doc = self._get(f"draft/{draft_id}")
        return doc if isinstance(doc, dict) else None

    def draft_picks(self, draft_id: str) -> list[dict]:
        return _as_list(self._get(f"draft/{draft_id}/picks"))

    def traded_picks(self, league_id: str) -> list[dict]:
        return _as_list(self._get(f"league/{league_id}/traded_picks"))

    def rosters(self, league_id: str) -> list[dict]:
        return _as_list(self._get(f"league/{league_id}/rosters"))

    def users(self, league_id: str) -> list[dict]:
        return _as_list(self._get(f"league/{league_id}/users"))

    # ── MFL ──
    def mfl_draft_results(self, league_id: str, year: int, host: str) -> dict | None:
        from . import mfl_service
        return mfl_service.fetch_draft_results(
            league_id, year, host, cookie=self.mfl_cookie, _opener=self.mfl_opener)

    # ── our own data ──
    def rookie_ids(self, season: int) -> set[str]:
        return self.rookie_ids_fn(int(season))

    def players(self, player_ids: Sequence[str]) -> dict[str, dict]:
        return self.players_fn(player_ids)


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    """Upstream material for one league's draft. The RENDERED payload is
    deliberately NOT cached: rendering is cheap and depends on ``basis`` and
    on the session user (``my_picks``), so caching it would multiply keys."""

    fetched_at: float = 0.0
    as_of: str = ""
    state: str = UNAVAILABLE
    draft_id: str = ""
    detail: dict | None = None
    picks: list | None = None
    last_picked: Any = None
    traded: list = field(default_factory=list)
    rosters: list = field(default_factory=list)
    league_users: list = field(default_factory=list)
    drafts: list = field(default_factory=list)
    league_fetched_at: float = 0.0
    mfl: dict | None = None
    fails: int = 0
    opened_until: float = 0.0
    budget: deque = field(default_factory=deque)
    degraded: dict | None = None
    notice_code: str | None = None

    @property
    def loaded(self) -> bool:
        return self.fetched_at > 0.0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_board(req: BoardRequest, fetchers: Fetchers) -> dict:
    """THE entry point. Returns the ``schema:1`` payload.

    Never raises and never writes. An upstream failure becomes
    ``state``/``degraded``/``stale``, never an exception and never a 5xx.
    """
    platform = str(req.platform or "").lower()
    _prune_cache()

    if platform not in (SLEEPER, MFL):
        return _render_unavailable(req, platform,
                                   notice=_notice(NOTICE_PLATFORM_UNSUPPORTED))
    try:
        entry = _refresh(req, fetchers, platform)
    except Exception:                                   # never propagate (lld §2.1)
        log.exception("draft-board build failed league=%s platform=%s",
                      req.league_id, platform)
        return _render_unavailable(
            req, platform, degraded=_degraded(REASON_UPSTREAM_ERROR, _now_iso()))

    try:
        return _render(req, platform, entry, fetchers)
    except Exception:
        log.exception("draft-board render failed league=%s platform=%s",
                      req.league_id, platform)
        return _render_unavailable(
            req, platform, degraded=_degraded(REASON_UPSTREAM_ERROR, entry.as_of or _now_iso()))


# ---------------------------------------------------------------------------
# Cache / single-flight / budget / breaker
# ---------------------------------------------------------------------------

def reset_cache() -> None:
    """Drop every cached draft. Tests only — there is no production caller."""
    with _cache_lock:
        _cache.clear()
        _inflight.clear()


def _prune_cache() -> None:
    """TTL purge + hard cap, run before every lookup (lld §3.1).

    TTL does the real work; the cap only bounds a pathological league count,
    which is why this is oldest-first rather than LRU.
    """
    now = _now_monotonic()
    with _cache_lock:
        for key, entry in list(_cache.items()):
            if now < entry.opened_until:
                continue    # an OPEN breaker outlives its TTL, or evicting the
                            # entry would silently re-arm the upstream calls it
                            # exists to stop
            if now - entry.fetched_at > 2 * _TTL_BY_STATE.get(entry.state, 60):
                _cache.pop(key, None)
        if len(_cache) > _CACHE_MAX_ENTRIES:
            for key, _ in sorted(_cache.items(), key=lambda kv: kv[1].fetched_at)[
                    : len(_cache) - _CACHE_MAX_ENTRIES]:
                _cache.pop(key, None)


def _find_entry(platform: str, league_id: str) -> tuple[tuple[str, str, str] | None, "_Entry | None"]:
    """The entry for a league, whatever ``draft_id`` it was filed under.

    The LLD's key is ``(platform, league_id, draft_id)``, but ``draft_id`` is
    only knowable after the first upstream read — so lookup is by league and
    the key is completed on write. With <=200 entries the scan is free.
    """
    with _cache_lock:
        for key, entry in _cache.items():
            if key[0] == platform and key[1] == league_id:
                return key, entry
    return None, None


def _fresh(entry: "_Entry | None") -> bool:
    if entry is None or not entry.loaded:
        return False
    return _now_monotonic() - entry.fetched_at < _TTL_BY_STATE.get(entry.state, 60)


def _breaker_open(entry: "_Entry") -> bool:
    return _now_monotonic() < entry.opened_until


def _budget_available(entry: "_Entry") -> bool:
    """Rolling-60 s fetch budget (D6). Entries strictly older than the window
    are dropped, so a cycle exactly on the boundary still counts."""
    now = _now_monotonic()
    while entry.budget and now - entry.budget[0] > _BUDGET_WINDOW_SECONDS:
        entry.budget.popleft()
    return len(entry.budget) < _BUDGET_PER_MIN


def _refresh(req: BoardRequest, fetchers: Fetchers, platform: str) -> "_Entry":
    """Return a usable entry, fetching at most once per (draft, TTL) window."""
    key, entry = _find_entry(platform, req.league_id)
    if _fresh(entry):
        return entry                                    # type: ignore[return-value]

    flight_key = (platform, req.league_id)
    with _cache_lock:
        lock = _inflight.get(flight_key)
        if lock is None:
            lock = _inflight[flight_key] = threading.Lock()

    with lock:
        # Double-checked: N concurrent viewers of a cold draft ⇒ ONE fetch.
        key, entry = _find_entry(platform, req.league_id)
        if _fresh(entry):
            return entry                                # type: ignore[return-value]
        if entry is None:
            entry = _Entry()

        if _breaker_open(entry):
            entry.degraded = _degraded(REASON_BREAKER_OPEN, entry.as_of or _now_iso())
            _store(platform, req.league_id, entry, key)
            return entry
        if entry.loaded and not _budget_available(entry):
            entry.degraded = _degraded(REASON_BUDGET_EXCEEDED, entry.as_of or _now_iso())
            _store(platform, req.league_id, entry, key)
            return entry

        try:
            if platform == SLEEPER:
                _fetch_sleeper(req, fetchers, entry)
            else:
                _fetch_mfl(req, fetchers, entry)
        except _AuthExpired:
            entry.fails += 1
            entry.degraded = _degraded(REASON_AUTH_EXPIRED, entry.as_of or _now_iso())
            entry.notice_code = NOTICE_MFL_RECONNECT
            _trip_breaker(entry)
        except Exception:
            log.exception("draft-board upstream failed league=%s", req.league_id)
            entry.fails += 1
            entry.degraded = _degraded(REASON_UPSTREAM_ERROR, entry.as_of or _now_iso())
            _trip_breaker(entry)
        else:
            entry.fails = 0
            entry.opened_until = 0.0
            entry.degraded = None
            entry.as_of = _now_iso()
        finally:
            entry.budget.append(_now_monotonic())
            entry.fetched_at = _now_monotonic()

        _store(platform, req.league_id, entry, key)
        return entry


def _trip_breaker(entry: "_Entry") -> None:
    if entry.fails >= _BREAKER_FAILS:
        entry.opened_until = _now_monotonic() + _BREAKER_OPEN_SECONDS


def _store(platform: str, league_id: str, entry: "_Entry",
           old_key: tuple[str, str, str] | None) -> None:
    key = (platform, league_id, entry.draft_id or "")
    with _cache_lock:
        if old_key is not None and old_key != key:
            _cache.pop(old_key, None)
        _cache[key] = entry


class _AuthExpired(Exception):
    """MFL refused the export — a stored snapshot is served instead."""


# ---------------------------------------------------------------------------
# Sleeper fetch — the poll rule (D6 / KD-8)
# ---------------------------------------------------------------------------

def _fetch_sleeper(req: BoardRequest, fetchers: Fetchers, entry: "_Entry") -> None:
    now = _now_monotonic()
    if not entry.loaded or now - entry.league_fetched_at >= _LEAGUE_META_TTL_SECONDS:
        entry.drafts = _as_list(fetchers.drafts(req.league_id))
        entry.traded = _as_list(fetchers.traded_picks(req.league_id))
        entry.rosters = _as_list(fetchers.rosters(req.league_id))
        entry.league_users = _as_list(fetchers.users(req.league_id))
        entry.league_fetched_at = now

    draft = _select_draft(entry.drafts, req.season)
    if draft is None:
        # `drafts == []` is ambiguous (a flake and a draft-less league are
        # indistinguishable) — say `unavailable`, never fabricate a board.
        entry.draft_id = ""
        entry.detail = None
        entry.picks = []
        entry.state = UNAVAILABLE
        return

    draft_id = str(draft.get("draft_id") or "")
    if draft_id != entry.draft_id:
        entry.picks = None                              # a different draft: pick list is void
        entry.last_picked = None
    entry.draft_id = draft_id

    detail = fetchers.draft_detail(draft_id)
    if not isinstance(detail, dict):
        raise RuntimeError(f"draft detail unavailable for {draft_id}")
    entry.detail = detail

    # THE poll rule: the 20 KB pick list is fetched only when the 1.2 KB
    # detail object says a pick has been made. Polling /picks directly reads
    # the ~24 h CDN cache of a complete draft while believing it is live.
    last_picked = detail.get("last_picked")
    if entry.picks is None or last_picked != entry.last_picked:
        entry.picks = _as_list(fetchers.draft_picks(draft_id))
    entry.last_picked = last_picked

    entry.state = SLEEPER_STATUS_TO_STATE.get(str(detail.get("status") or ""), UPCOMING)


def _select_draft(drafts: list, season: int) -> dict | None:
    """The season's draft: rookie-shaped first, most recently created wins."""
    candidates = []
    for d in drafts:
        if not isinstance(d, dict):
            continue
        try:
            if int(d.get("season") or 0) != int(season):
                continue
        except (TypeError, ValueError):
            continue
        candidates.append(d)
    if not candidates:
        return None
    rookie_shaped = [d for d in candidates
                     if draft_status._is_rookie_shaped(d) is not False]
    pool = rookie_shaped or candidates
    return max(pool, key=lambda d: int(d.get("created") or 0))


# ---------------------------------------------------------------------------
# MFL fetch
# ---------------------------------------------------------------------------

def _fetch_mfl(req: BoardRequest, fetchers: Fetchers, entry: "_Entry") -> None:
    year = int(req.mfl_year or req.season)
    host = req.mfl_host or ""
    raw = fetchers.mfl_draft_results(req.league_id, year, host)
    if not isinstance(raw, dict) or not raw:
        # fetch_draft_results swallows MflError into {} — an empty payload is
        # indistinguishable from an auth refusal, so serve the stored snapshot
        # and say "reconnect" rather than render stale-as-live.
        raise _AuthExpired()
    entry.mfl = raw
    entry.draft_id = str(req.league_id)
    entry.notice_code = None
    made, total, _ = _mfl_counts(raw)
    if total == 0:
        entry.state = UNAVAILABLE
    elif made == 0:
        entry.state = UPCOMING
    elif made < total:
        entry.state = LIVE
    else:
        entry.state = COMPLETE


def _mfl_units(raw: dict) -> list[dict]:
    units = _as_list((raw.get("draftResults") or {}).get("draftUnit"))
    return [u for u in units if isinstance(u, dict)]


def _mfl_picks(unit: dict) -> list[dict]:
    return [p for p in _as_list(unit.get("draftPick")) if isinstance(p, dict)]


def _mfl_unit_width(unit: dict) -> int:
    """Picks per round in one ``draftUnit``.

    ``round1DraftOrder`` is the honest source: counting DISTINCT franchises
    across the grid under-counts, because a franchise that traded away all of
    its picks never appears and one that acquired several appears once
    (``mfl-partial``: 10 distinct franchises on a 12-team grid).
    """
    raw = str(unit.get("round1DraftOrder") or "")
    width = len([f for f in raw.split(",") if f.strip()])
    if width:
        return width
    per_round: dict[int, int] = {}
    for p in _mfl_picks(unit):
        r = _int_or_none(p.get("round")) or 0
        per_round[r] = per_round.get(r, 0) + 1
    return max(per_round.values()) if per_round else 0


def _mfl_counts(raw: dict) -> tuple[int, int, int]:
    """``(made, total, teams)`` aggregated over every ``draftUnit``."""
    made = total = teams = 0
    for unit in _mfl_units(raw):
        teams += _mfl_unit_width(unit)
        for p in _mfl_picks(unit):
            total += 1
            if str(p.get("player") or "").strip():
                made += 1
    return made, total, teams


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify(detail: dict, rounds: int | None, teams: int | None) -> tuple[str, str]:
    """``(state, kind)`` from a Sleeper detail object.

    ``state`` treats Sleeper's ``status`` as an OPEN set. ``kind`` is the
    rounds shape only — ``settings.player_type`` is 0 even on a rookies-only
    draft (verified useless, #207 research §1.3).
    """
    state = SLEEPER_STATUS_TO_STATE.get(str(detail.get("status") or ""), UPCOMING)
    return state, _kind_from_rounds(rounds)


def _kind_from_rounds(rounds: int | None) -> str:
    if not rounds or rounds <= 0:
        return KIND_UNKNOWN
    if rounds <= draft_status.ROOKIE_MAX_ROUNDS:
        return KIND_ROOKIE
    if rounds >= draft_status.STARTUP_MIN_ROUNDS:
        return KIND_STARTUP
    return KIND_UNKNOWN


# ---------------------------------------------------------------------------
# Order (D5)
# ---------------------------------------------------------------------------

def _traded_overlay(traded: Iterable, season: int) -> dict[tuple[int, int], int]:
    """``(round, original_roster_id) -> current owner roster_id``.

    Filtered to the draft's own season — the same export carries future years.
    A row whose ``owner_id`` equals ``roster_id`` is a pick that came home; it
    is kept so ``is_traded`` can be computed as "owner != original".
    """
    out: dict[tuple[int, int], int] = {}
    for row in traded or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("season") or 0) != int(season):
                continue
            out[(int(row["round"]), int(row["roster_id"]))] = int(row["owner_id"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _pick_no(round_no: int, slot: int, teams: int, draft_type: str,
             reversal_round: int) -> int | None:
    """Overall pick number, or ``None`` when the shape is not one we can
    compute honestly.

    Only ``linear`` and plain ``snake`` are computed. Sleeper's
    ``reversal_round`` (3rd-round reversal) changes the parity in a way we
    have no live payload to verify against, so a snake draft that sets it
    reports ``pick_no: null`` rather than a guess. Note that Lakeview carries
    ``reversal_round: 3`` on a ``linear`` draft — it is a stale default there
    and the recorded picks confirm plain linear numbering.
    """
    base = (round_no - 1) * teams
    if draft_type == "linear":
        return base + slot
    if draft_type == "snake" and not reversal_round:
        return base + (slot if round_no % 2 == 1 else teams - slot + 1)
    return None


def _order_from(detail: dict, traded: list, rosters: list, users: list,
                season: int) -> tuple[list[dict], str]:
    """``(order[], order_confidence)``.

    ``draft_order`` (user → slot) composed with the rosters list (user →
    roster) is the ONLY slot resolution here. ``slot_to_roster_id`` is never
    read: pre-draft it is the identity map ``{"1":1 … "12":12}``, which reads
    as a plausible order and is not one (D5).
    """
    settings = detail.get("settings") or {}
    rounds = _int_or_none(settings.get("rounds"))
    teams = _int_or_none(settings.get("teams")) or len(rosters) or None
    roster_by_user = {str(r.get("owner_id")): _int_or_none(r.get("roster_id"))
                      for r in rosters if isinstance(r, dict) and r.get("owner_id")}
    user_by_roster = {v: k for k, v in roster_by_user.items() if v is not None}
    all_roster_ids = sorted(
        rid for rid in (_int_or_none(r.get("roster_id"))
                        for r in rosters if isinstance(r, dict))
        if rid is not None)
    username = {str(u.get("user_id")): u.get("display_name")
                for u in users if isinstance(u, dict)}
    overlay = _traded_overlay(traded, season)

    draft_order = detail.get("draft_order")

    def entry(round_no: int, slot: int | None, original_roster: int | None) -> dict:
        owner_roster = overlay.get((round_no, original_roster), original_roster)
        original_user = user_by_roster.get(original_roster)
        owner_user = user_by_roster.get(owner_roster)
        return {
            "slot": slot,
            "round": round_no,
            "pick_no": (_pick_no(round_no, slot, teams,
                                 str(detail.get("type") or ""),
                                 _int_or_none(settings.get("reversal_round")) or 0)
                        if slot is not None and teams else None),
            "owner_user_id": owner_user,
            "owner_username": username.get(owner_user) if owner_user else None,
            "original_user_id": original_user,
            "original_username": username.get(original_user) if original_user else None,
            "is_traded": owner_roster != original_roster,
        }

    if not rounds:
        return [], (ORDER_ASSIGNED if draft_order else ORDER_UNKNOWN)

    order: list[dict] = []
    if not draft_order:
        # THE honest degradation: round-level ownership, slot deliberately
        # null. Never an invented order.
        for round_no in range(1, rounds + 1):
            for roster_id in all_roster_ids:
                order.append(entry(round_no, None, roster_id))
        return _cap_order(order), ORDER_UNSET

    if not teams:
        return [], ORDER_ASSIGNED
    roster_by_slot: dict[int, int | None] = {}
    for user_id, slot in draft_order.items():
        slot_i = _int_or_none(slot)
        if slot_i:
            roster_by_slot[slot_i] = roster_by_user.get(str(user_id))
    for round_no in range(1, rounds + 1):
        for slot in range(1, teams + 1):
            order.append(entry(round_no, slot, roster_by_slot.get(slot)))
    return _cap_order(order), ORDER_ASSIGNED


def _cap_order(order: list[dict]) -> list[dict]:
    if len(order) > _ORDER_CAP:
        log.warning("draft-board order truncated at %d entries (had %d)",
                    _ORDER_CAP, len(order))
        return order[:_ORDER_CAP]
    return order


# ---------------------------------------------------------------------------
# Picks
# ---------------------------------------------------------------------------

def _picks_from(raw_picks: Iterable) -> list[dict]:
    """``picks[]``, ascending ``pick_no``.

    ``picked_at`` is always ``None`` for Sleeper: pick objects carry no
    timestamp (verified against the live Lakeview recording — ``last_picked``
    lives only on the detail object).
    """
    out = []
    for p in raw_picks or []:
        if not isinstance(p, dict):
            continue
        meta = p.get("metadata") or {}
        name = " ".join(x for x in (meta.get("first_name"), meta.get("last_name")) if x).strip()
        out.append({
            "round": _int_or_none(p.get("round")) or 0,
            "pick_no": _int_or_none(p.get("pick_no")) or 0,
            "slot": _int_or_none(p.get("draft_slot")),
            "player_id": str(p.get("player_id") or ""),
            "name": name,
            "position": str(meta.get("position") or ""),
            "team": (meta.get("team") or None),
            "picked_by_user_id": str(p.get("picked_by")) if p.get("picked_by") else None,
            "picked_at": None,
        })
    out.sort(key=lambda x: x["pick_no"])
    return out


# ---------------------------------------------------------------------------
# Undrafted (D7)
# ---------------------------------------------------------------------------

def _undrafted(season: int, drafted_ids: set[str], rostered_ids: set[str],
               basis: str, board_elo: Mapping[str, float] | None,
               consensus_elo: Mapping[str, float] | None,
               fetchers: Fetchers) -> tuple[list[dict], bool]:
    """``(undrafted[], class_loaded)`` — D7.

    Membership is ``load_rookie_player_ids(season)`` minus drafted minus
    rostered. **Rows with no value are rendered, never dropped** — they sort
    last and carry ``valued: false`` so the client can say "no consensus
    value". Sourcing from the value pool instead would silently vanish exactly
    the late-round prospects a draft board exists to show.
    """
    ids = set(fetchers.rookie_ids(season) or ())
    if not ids:
        return [], False

    remaining = sorted(ids - drafted_ids - rostered_ids)
    if not remaining:
        return [], True

    rows = fetchers.players(remaining) or {}
    values = board_elo if basis == BASIS_MY_BOARD else consensus_elo
    values = values or {}

    out = []
    for pid in remaining:
        row = rows.get(pid) or {}
        position = str(row.get("position") or "").upper()
        if position and position not in _POSITIONS:
            continue
        value = values.get(pid)
        out.append({
            "player_id": pid,
            "name": row.get("full_name") or row.get("name") or "",
            "position": position,
            "team": row.get("team") or None,
            "rookie_year": str(row.get("rookie_year")) if row.get("rookie_year") else None,
            "value": float(value) if value is not None else None,
            "valued": value is not None,
            "_search_rank": row.get("search_rank"),
        })

    out.sort(key=lambda r: (
        not r["valued"],                                    # valued first
        -(r["value"] or 0.0),
        r["_search_rank"] is None, r["_search_rank"] or 0,  # then the honest tail
        r["name"],
    ))
    if len(out) > _UNDRAFTED_CAP:
        log.warning("draft-board undrafted list capped at %d (had %d) — season=%s",
                    _UNDRAFTED_CAP, len(out), season)
        out = out[:_UNDRAFTED_CAP]
    for rank, row in enumerate(out, start=1):
        row.pop("_search_rank", None)
        row["rank"] = rank
    return out, True


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _render(req: BoardRequest, platform: str, entry: "_Entry",
            fetchers: Fetchers) -> dict:
    if platform == MFL:
        return _render_mfl(req, entry, fetchers)
    return _render_sleeper(req, entry, fetchers)


def _render_sleeper(req: BoardRequest, entry: "_Entry", fetchers: Fetchers) -> dict:
    detail = entry.detail
    if not isinstance(detail, dict):
        return _render_unavailable(req, SLEEPER, degraded=entry.degraded,
                                   as_of=entry.as_of, stale=_is_stale(entry))

    settings = detail.get("settings") or {}
    rounds = _int_or_none(settings.get("rounds"))
    teams = _int_or_none(settings.get("teams")) or (len(entry.rosters) or None)
    season = _int_or_none(detail.get("season")) or int(req.season)
    state, kind = _classify(detail, rounds, teams)

    order, confidence = _order_from(detail, entry.traded, entry.rosters,
                                    entry.league_users, season)
    picks = _picks_from(entry.picks or [])

    drafted = {p["player_id"] for p in picks if p["player_id"]}
    rostered = set()
    for r in entry.rosters:
        if isinstance(r, dict):
            rostered |= {str(p) for p in (r.get("players") or []) if p}

    suppressed = kind == KIND_STARTUP
    undrafted: list[dict] = []
    class_loaded = True
    if not suppressed:
        undrafted, class_loaded = _undrafted(
            season, drafted, rostered, req.basis, req.board_elo,
            req.consensus_elo, fetchers)
        if not class_loaded:
            suppressed = True

    notice_code = None
    if kind == KIND_STARTUP:
        notice_code = NOTICE_STARTUP_DRAFT
    elif confidence == ORDER_UNSET:
        notice_code = NOTICE_ORDER_NOT_SET
    elif not class_loaded:
        notice_code = NOTICE_CLASS_NOT_LOADED

    return _payload(
        req, SLEEPER, state=state, kind=kind, season=season, rounds=rounds,
        teams=teams, order=order, order_confidence=confidence, picks=picks,
        undrafted=undrafted, undrafted_suppressed=suppressed, entry=entry,
        notice=_notice(notice_code),
        deep_link=req.deep_link or (f"https://sleeper.com/draft/nfl/{entry.draft_id}"
                                    if entry.draft_id else None),
    )


def _render_mfl(req: BoardRequest, entry: "_Entry", fetchers: Fetchers) -> dict:
    raw = entry.mfl
    if not isinstance(raw, dict):
        return _render_unavailable(
            req, MFL, degraded=entry.degraded, as_of=entry.as_of,
            stale=_is_stale(entry),
            notice=_notice(entry.notice_code or NOTICE_MFL_RECONNECT))

    made, total, width_total = _mfl_counts(raw)
    teams = width_total or None
    rounds = int(total / teams) if teams and total % teams == 0 else None
    kind = _kind_from_rounds(rounds)
    season = int(req.mfl_year or req.season)

    fr_to_user = req.mfl_franchise_to_user or {}
    username = {}                                   # MFL has no display-name export here
    order: list[dict] = []
    picks: list[dict] = []
    pid_map = req.mfl_player_ids or {}
    assigned = True
    offset = 0
    for unit in _mfl_units(raw):
        unit_picks = _mfl_picks(unit)
        width = _mfl_unit_width(unit)
        for p in unit_picks:
            round_no = _int_or_none(p.get("round")) or 0
            slot = _int_or_none(p.get("pick"))
            fid = str(p.get("franchise") or "").strip()
            if not fid:
                assigned = False
            owner = fr_to_user.get(fid)
            comments = str(p.get("comments") or "")
            pick_no = (offset + (round_no - 1) * width + slot) if (slot and width) else None
            order.append({
                "slot": slot,
                "round": round_no,
                "pick_no": pick_no,
                "owner_user_id": owner,
                "owner_username": username.get(owner) if owner else None,
                # MFL's grid states the CURRENT owner; provenance survives only
                # as prose in `comments`, so the original owner is unknown.
                "original_user_id": None,
                "original_username": None,
                "is_traded": "traded from" in comments.lower(),
            })
            mfl_pid = str(p.get("player") or "").strip()
            if mfl_pid:
                ts = _int_or_none(p.get("timestamp"))
                picks.append({
                    "round": round_no,
                    "pick_no": pick_no or 0,
                    "slot": slot,
                    "player_id": str(pid_map.get(mfl_pid, mfl_pid)),
                    "name": "",
                    "position": "",
                    "team": None,
                    "picked_by_user_id": owner,
                    "picked_at": (datetime.fromtimestamp(ts, timezone.utc).isoformat()
                                  if ts else None),
                })
        offset += len(unit_picks)

    order = _cap_order(order)
    picks.sort(key=lambda x: x["pick_no"])

    # Undrafted needs OUR id space on both sides. Without the crosswalk the
    # subtraction would silently under-count, so it is suppressed honestly
    # rather than computed wrongly (M5 injects `mfl_player_ids`).
    suppressed = kind == KIND_STARTUP or not pid_map
    undrafted: list[dict] = []
    class_loaded = True
    if not suppressed:
        drafted = {p["player_id"] for p in picks if p["player_id"]}
        rostered = {str(p) for p in (req.rostered_ids or ()) if p}
        undrafted, class_loaded = _undrafted(
            season, drafted, rostered, req.basis, req.board_elo,
            req.consensus_elo, fetchers)
        if not class_loaded:
            suppressed = True

    notice_code = entry.notice_code
    if notice_code is None:
        if kind == KIND_STARTUP:
            notice_code = NOTICE_STARTUP_DRAFT
        elif not assigned:
            notice_code = NOTICE_ORDER_NOT_SET
        elif not class_loaded:
            notice_code = NOTICE_CLASS_NOT_LOADED

    static_url = None
    for unit in _mfl_units(raw):
        static_url = unit.get("static_url") or static_url

    return _payload(
        req, MFL, state=entry.state, kind=kind, season=season, rounds=rounds,
        teams=teams, order=order,
        order_confidence=ORDER_ASSIGNED if assigned else ORDER_UNKNOWN,
        picks=picks, undrafted=undrafted, undrafted_suppressed=suppressed,
        entry=entry, notice=_notice(notice_code),
        deep_link=req.deep_link or static_url,
    )


def _payload(req: BoardRequest, platform: str, *, state: str, kind: str,
             season: int, rounds: int | None, teams: int | None,
             order: list[dict], order_confidence: str, picks: list[dict],
             undrafted: list[dict], undrafted_suppressed: bool,
             entry: "_Entry", notice: dict | None,
             deep_link: str | None) -> dict:
    my_picks = ([o for o in order if o.get("owner_user_id") == req.user_id]
                if req.user_id else [])
    return {
        "schema": SCHEMA,
        "league_id": str(req.league_id),
        "platform": platform,
        "state": state,
        "kind": kind,
        "season": int(season),
        "rounds": rounds,
        "teams": teams,
        "order_confidence": order_confidence,
        "order": order,
        "picks": picks,
        "undrafted": undrafted,
        "undrafted_basis": req.basis if req.basis in (BASIS_CONSENSUS, BASIS_MY_BOARD)
                           else BASIS_CONSENSUS,
        "undrafted_suppressed": bool(undrafted_suppressed),
        "my_picks": my_picks,
        "as_of": entry.as_of or _now_iso(),
        "stale": _is_stale(entry),
        "degraded": entry.degraded,
        "notice": notice,
        "deep_link": deep_link,
    }


def _render_unavailable(req: BoardRequest, platform: str, *,
                        notice: dict | None = None,
                        degraded: dict | None = None,
                        as_of: str | None = None,
                        stale: bool = False) -> dict:
    return {
        "schema": SCHEMA,
        "league_id": str(req.league_id),
        "platform": platform,
        "state": UNAVAILABLE,
        "kind": KIND_UNKNOWN,
        "season": int(req.season),
        "rounds": None,
        "teams": None,
        "order_confidence": ORDER_UNKNOWN,
        "order": [],
        "picks": [],
        "undrafted": [],
        "undrafted_basis": req.basis if req.basis in (BASIS_CONSENSUS, BASIS_MY_BOARD)
                           else BASIS_CONSENSUS,
        "undrafted_suppressed": True,
        "my_picks": [],
        "as_of": as_of or _now_iso(),
        "stale": bool(stale or degraded is not None),
        "degraded": degraded,
        "notice": notice,
        "deep_link": None,
    }


def _is_stale(entry: "_Entry") -> bool:
    """True when the payload is older than 2x its state's TTL, or degraded."""
    if entry.degraded is not None or _breaker_open(entry):
        return True
    if not entry.loaded:
        return True
    return (_now_monotonic() - entry.fetched_at) > 2 * _TTL_BY_STATE.get(entry.state, 60)


def _notice(code: str | None) -> dict | None:
    if not code:
        return None
    return {"code": code, "message": _NOTICE_MESSAGES.get(code, "")}


def _degraded(reason: str, since: str) -> dict:
    return {"reason": reason, "since": since}


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _as_list(value) -> list:
    """MFL serves a bare dict for a single-member collection; Sleeper serves
    ``null`` for an absent list. Normalise both."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
