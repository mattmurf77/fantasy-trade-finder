"""B1 — the nightly pass registry, ledger claims, and tick driver.

docs/plans/trade-relevance-engine/hld.md §2.1, lld.md §3.3/§4.1, §5 E1/E2.

Today `/api/cron/daily-tick` runs six jobs inline in one gunicorn worker. When
the tick dies mid-way, everything after the corpse silently doesn't run and
nothing durable records which passes completed. This module turns that inline
sequence into a registry of named passes, each with:

  • a durable `cron_pass_runs` row per (pass_name, run_date) — the ledger,
  • an INSERT-claim on `uq_pass_run` so a double-POST can't double-run a pass,
  • a **mandatory** stale-`running` recovery so a mid-pass OOM can't wedge a
    pass for the rest of the day (E2 / T-3),
  • an operational kill valve `cron.pass_disabled.<name>` in `model_config`
    with inverted polarity (absent ⇒ the pass RUNS),
  • its own try/except, so one dead pass can't eat the ones behind it,
  • a class: `resumable` (deadline-skippable, picked up next tick/day) vs
    `must_complete_today` (date-gated work, exempt from the deadline skip,
    retried ≤ `max_same_day_retries` same-day before a final `error`).

Two things this module deliberately does NOT do:

  • **No preemption.** `budget_s` is post-hoc only: it marks an overrunning
    pass `timeout` after the fact and feeds the 2×-budget stale-claim rule.
    Passes run synchronously and are never killed mid-flight (LLD §2.1).
  • **No fail-closed ledger.** If the ledger itself is unreachable, passes
    still run. A ledger bug must not be able to silence the nightly pushes —
    that is the exact failure this table exists to prevent. Re-run safety in
    that degraded mode comes from the push-kind invariant below.

Push-kind invariant (HLD §2.1): every push kind a ledger pass may dispatch
must carry a frequency cap or a documented dedup key, because a re-run pass
re-sends. `register()` refuses a spec that declares a kind with neither.
The host app supplies the two known-kind sets via `configure_push_kinds()`;
this module never imports the server (D12: ZERO Flask imports in this
package).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Sequence

from .config import valve

__all__ = [
    "PassSpec", "PassContext", "REGISTRY", "register", "clear_registry",
    "configure_push_kinds", "run_ledger",
    "STATUS_RUNNING", "STATUS_OK", "STATUS_ERROR", "STATUS_SKIPPED",
    "STATUS_TIMEOUT", "KLASS_RESUMABLE", "KLASS_MUST_COMPLETE",
    "SKIP_VALVE", "SKIP_DEADLINE", "SKIP_CLAIMED", "SKIP_DONE",
]

log = logging.getLogger(__name__)

# Ledger statuses (mirror the `cron_pass_runs.status` comment in database.py).
STATUS_RUNNING = "running"
STATUS_OK      = "ok"
STATUS_ERROR   = "error"
STATUS_SKIPPED = "skipped"
STATUS_TIMEOUT = "timeout"

KLASS_RESUMABLE      = "resumable"
KLASS_MUST_COMPLETE  = "must_complete_today"

# `error_text` tokens written on a `skipped` row. M1's green-rate definition
# excludes `skipped` from the denominator but REQUIRES it split by cause:
# valve-off/dark is healthy, a chronically deadline-starved pass is not and
# must not read as 100% green. These tokens are that split.
SKIP_VALVE    = "valve"
SKIP_DEADLINE = "deadline"
SKIP_CLAIMED  = "claimed_elsewhere"   # another worker owns / already ran it
SKIP_DONE     = "already_terminal"    # errored/timed out earlier today


# ---------------------------------------------------------------------------
# PassSpec / PassContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PassSpec:
    """One nightly pass. `name` is the ledger key AND the valve suffix."""
    name: str
    fn: Callable[["PassContext"], dict]
    budget_s: float
    klass: str = KLASS_RESUMABLE
    max_same_day_retries: int = 2          # read only for must_complete_today
    push_kinds: tuple[str, ...] = ()       # every push kind this pass may send
    # Escape hatch for the registration assert: a kind that legitimately has
    # no `_NOTIF_FREQ_CAPS` entry because its re-run safety comes from a
    # per-call dedup key instead. Listing a kind here is a claim the reviewer
    # can check; it is NOT a way to declare an uncapped kind safe.
    dedup_key_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.klass not in (KLASS_RESUMABLE, KLASS_MUST_COMPLETE):
            raise ValueError(f"PassSpec {self.name!r}: unknown klass {self.klass!r}")
        if self.budget_s <= 0:
            raise ValueError(f"PassSpec {self.name!r}: budget_s must be > 0")


@dataclass
class PassContext:
    """What a pass body gets. `counters` and `state` are SHARED across passes
    — that is how the refactored daily-tick keeps its response payload
    byte-identical to the inline version it replaced (LLD §4.1 / R2)."""
    now: datetime
    run_date: str
    counters: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    deadline_at: float | None = None       # time.monotonic() deadline, or None


# ---------------------------------------------------------------------------
# Push-kind registration assert (HLD §2.1)
# ---------------------------------------------------------------------------

_freq_capped_kinds: frozenset[str] = frozenset()
_dedup_keyed_kinds: frozenset[str] = frozenset()
_push_kinds_configured = False


def configure_push_kinds(*, freq_capped: Iterable[str],
                         dedup_keyed: Iterable[str] = ()) -> None:
    """Tell the registry which push kinds are re-run safe.

    `freq_capped` is `server._NOTIF_FREQ_CAPS` (kind → window/limit);
    `dedup_keyed` is `server._NOTIF_DEDUP_CAPS` (kinds whose call sites pass a
    dedup_key). Called once by the host app before it registers any pass.
    """
    global _freq_capped_kinds, _dedup_keyed_kinds, _push_kinds_configured
    _freq_capped_kinds = frozenset(freq_capped)
    _dedup_keyed_kinds = frozenset(dedup_keyed)
    _push_kinds_configured = True


def _validate_push_kinds(spec: PassSpec) -> None:
    if not spec.push_kinds:
        return
    if not _push_kinds_configured:
        raise ValueError(
            f"pass {spec.name!r} declares push_kinds {list(spec.push_kinds)} but "
            "configure_push_kinds() has not been called — the registry cannot "
            "verify the frequency-cap invariant (HLD §2.1)."
        )
    for kind in spec.push_kinds:
        if kind in _freq_capped_kinds:
            continue
        if kind in _dedup_keyed_kinds:
            continue
        if kind in spec.dedup_key_kinds:
            continue
        raise ValueError(
            f"pass {spec.name!r} declares push kind {kind!r} with no frequency "
            "cap and no documented dedup key. A ledger pass can re-run "
            "(double-POST, stale-claim recovery, same-day retry), so an "
            "uncapped kind means duplicate pushes to real users (HLD §2.1). "
            "Add it to _NOTIF_FREQ_CAPS / _NOTIF_DEDUP_CAPS, or list it in the "
            "pass's dedup_key_kinds whitelist if its call site passes a "
            "dedup_key."
        )


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

REGISTRY: list[PassSpec] = []


def register(spec: PassSpec) -> PassSpec:
    """Append a pass to the global registry. Order of registration IS run
    order (LLD §4.1). Refuses duplicates and uncapped push kinds."""
    if any(s.name == spec.name for s in REGISTRY):
        raise ValueError(f"pass {spec.name!r} is already registered")
    _validate_push_kinds(spec)
    REGISTRY.append(spec)
    return spec


def clear_registry() -> None:
    """Test hook. Production registers once at import."""
    REGISTRY.clear()


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def _ledger():
    """Late import so this module stays import-cheap and Flask-free."""
    from .. import database as db
    return db, db.cron_pass_runs_table


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _claim(spec: PassSpec, run_date: str, now: datetime) -> tuple[bool, int, str]:
    """INSERT-claim the (pass_name, run_date) row (LLD §3.3, E1/E2).

    Returns (claimed, attempt, reason). `reason` is the `skipped` cause when
    claimed is False. Any unexpected ledger failure fails OPEN (claimed=True)
    — see the module docstring.
    """
    from sqlalchemy import insert, select, update
    from sqlalchemy.exc import IntegrityError

    db, t = _ledger()

    try:
        with db.engine.begin() as conn:
            conn.execute(insert(t).values(
                pass_name=spec.name, run_date=run_date, status=STATUS_RUNNING,
                started_at=now.isoformat(), attempt=1,
            ))
        return True, 1, ""
    except IntegrityError:
        pass                                   # someone got here first
    except Exception as e:                     # ledger unreachable ⇒ fail open
        log.warning("pass-ledger: claim of %s failed (%s); running anyway",
                    spec.name, e)
        return True, 1, ""

    try:
        with db.engine.connect() as conn:
            row = conn.execute(
                select(t).where(t.c.pass_name == spec.name,
                                t.c.run_date == run_date)
            ).first()
    except Exception as e:
        log.warning("pass-ledger: read-back of %s failed (%s); running anyway",
                    spec.name, e)
        return True, 1, ""

    if row is None:                            # vanished between insert & read
        return True, 1, ""

    status  = row.status
    attempt = int(row.attempt or 1)

    if status == STATUS_OK:
        return False, attempt, SKIP_CLAIMED

    def _reclaim(new_attempt: int, note: str | None) -> tuple[bool, int, str]:
        try:
            with db.engine.begin() as conn:
                conn.execute(update(t)
                             .where(t.c.pass_name == spec.name,
                                    t.c.run_date == run_date)
                             .values(status=STATUS_RUNNING, attempt=new_attempt,
                                     started_at=now.isoformat(),
                                     duration_ms=None, error_text=note))
        except Exception as e:
            log.warning("pass-ledger: re-claim of %s failed (%s); running anyway",
                        spec.name, e)
        return True, new_attempt, ""

    if status == STATUS_RUNNING:
        started = _parse_iso(row.started_at)
        age_s = (now - started).total_seconds() if started else float("inf")
        if age_s < 2 * spec.budget_s:
            return False, attempt, SKIP_CLAIMED     # a live worker owns it
        # Stale corpse from a killed worker. MANDATORY branch (T-3): without
        # it one mid-pass OOM wedges this pass for the rest of the day. The
        # spec's "UPDATE to error, then re-claim attempt+1" collapses into one
        # UPDATE because it is the same single row; the note records it.
        log.warning("pass-ledger: %s had a stale 'running' row (%.0fs old, "
                    "budget %.0fs) — reclaiming as attempt %d",
                    spec.name, age_s, spec.budget_s, attempt + 1)
        return _reclaim(attempt + 1,
                        f"reclaimed stale running (age {age_s:.0f}s)")

    if status == STATUS_SKIPPED:
        # A deadline- or valve-skipped pass never ran; it is picked up by the
        # next tick (HLD §2.1). Same attempt — nothing was attempted.
        return _reclaim(attempt, None)

    # error / timeout: work was attempted. `resumable` waits for tomorrow
    # (E2); `must_complete_today` gets bounded same-day retries.
    if spec.klass == KLASS_MUST_COMPLETE and attempt <= spec.max_same_day_retries:
        return _reclaim(attempt + 1, None)
    return False, attempt, SKIP_DONE


def _write(spec: PassSpec, run_date: str, now: datetime, *, status: str,
           attempt: int, duration_ms: int | None = None,
           items: int | None = None, error_text: str | None = None) -> None:
    """Upsert the ledger row's terminal state. Never raises."""
    from sqlalchemy import insert, update
    db, t = _ledger()
    vals = dict(status=status, attempt=attempt, duration_ms=duration_ms,
                items=items, error_text=error_text)
    try:
        with db.engine.begin() as conn:
            res = conn.execute(update(t)
                               .where(t.c.pass_name == spec.name,
                                      t.c.run_date == run_date)
                               .values(**vals))
            if not res.rowcount:
                conn.execute(insert(t).values(
                    pass_name=spec.name, run_date=run_date,
                    started_at=now.isoformat(), **vals))
    except Exception as e:
        log.warning("pass-ledger: could not record %s=%s (%s)",
                    spec.name, status, e)


def _bump_attempt(spec: PassSpec, run_date: str, now: datetime,
                  attempt: int) -> None:
    """Same-day retry of a must_complete_today pass: back to `running`."""
    _write(spec, run_date, now, status=STATUS_RUNNING, attempt=attempt)


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

def _disabled(name: str) -> bool:
    """`cron.pass_disabled.<name>` — inverted polarity, absent ⇒ pass runs.

    Read through `valve()` (raw model_config, uncached, resolver-exempt) so no
    experiment or per-user setting can resurrect a killed pass (HLD §2.1).
    """
    try:
        return valve(f"cron.pass_disabled.{name}") >= 0.5
    except Exception as e:          # never let a valve read stop a pass
        log.warning("pass-ledger: valve read for %s failed (%s); running", name, e)
        return False


def run_ledger(now: datetime, *, wall_budget_s: float = 600.0,
               registry: Sequence[PassSpec] | None = None,
               counters: dict[str, Any] | None = None,
               state: dict[str, Any] | None = None) -> dict:
    """Iterate the registry in order, one ledger row per pass per UTC day.

    Per pass: ledger claim (§3.3) → valve check → global-deadline check
    (between passes only; `must_complete_today` exempt) → run under its own
    try/except and time budget.

    `registry`/`counters`/`state` are additive keyword arguments on top of the
    LLD §2.1 signature: the moved daily-tick bodies share one `counters` dict
    and one `state` bag so the tick's response payload stays byte-identical
    (R2), and an explicit registry keeps the driver unit-testable.

    Returns {'statuses': {name: status}, 'counters': {name: pass_counters}}.
    """
    specs = list(REGISTRY if registry is None else registry)
    ctx = PassContext(
        now=now,
        run_date=now.strftime("%Y-%m-%d"),
        counters={} if counters is None else counters,
        state={} if state is None else state,
    )
    started_mono = time.monotonic()
    ctx.deadline_at = started_mono + wall_budget_s

    statuses: dict[str, str] = {}
    per_pass: dict[str, dict] = {}

    for spec in specs:
        must = spec.klass == KLASS_MUST_COMPLETE

        # ── kill valve (checked before the claim so a disabled pass costs one
        #    cheap read, and its `skipped` row records the cause for M1) ──
        if _disabled(spec.name):
            claimed, attempt, _reason = _claim(spec, ctx.run_date, now)
            if claimed:
                _write(spec, ctx.run_date, now, status=STATUS_SKIPPED,
                       attempt=attempt, error_text=SKIP_VALVE)
            statuses[spec.name] = STATUS_SKIPPED
            log.info("pass-ledger: %s skipped (valve)", spec.name)
            continue

        # ── global deadline, BETWEEN passes only; never preempts mid-flight ──
        if not must and time.monotonic() >= ctx.deadline_at:
            claimed, attempt, _reason = _claim(spec, ctx.run_date, now)
            if claimed:
                _write(spec, ctx.run_date, now, status=STATUS_SKIPPED,
                       attempt=attempt, error_text=SKIP_DEADLINE)
            statuses[spec.name] = STATUS_SKIPPED
            log.warning("pass-ledger: %s skipped (wall deadline %.0fs reached)",
                        spec.name, wall_budget_s)
            continue

        claimed, attempt, reason = _claim(spec, ctx.run_date, now)
        if not claimed:
            statuses[spec.name] = STATUS_SKIPPED
            log.info("pass-ledger: %s skipped (%s)", spec.name, reason)
            continue

        retries_left = spec.max_same_day_retries if must else 0
        while True:
            ctx.attempt = attempt
            t0 = time.monotonic()
            try:
                result = spec.fn(ctx) or {}
            except Exception as e:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                if retries_left > 0:
                    retries_left -= 1
                    attempt += 1
                    log.warning("pass-ledger: %s failed (%s); same-day retry "
                                "%d/%d", spec.name, e, attempt,
                                spec.max_same_day_retries + 1)
                    _bump_attempt(spec, ctx.run_date, now, attempt)
                    continue
                _write(spec, ctx.run_date, now, status=STATUS_ERROR,
                       attempt=attempt, duration_ms=elapsed_ms,
                       error_text=str(e)[:2000])
                statuses[spec.name] = STATUS_ERROR
                if must:
                    log.error("OPERATOR ALERT: date-gated pass %r failed all "
                              "%d same-day attempts (%s) — its date gate will "
                              "not come back tomorrow",
                              spec.name, spec.max_same_day_retries + 1, e)
                else:
                    log.exception("pass-ledger: %s errored", spec.name)
                break

            elapsed = time.monotonic() - t0
            # budget_s is post-hoc: the pass finished, it just overran. No
            # preemption exists (LLD §2.1) — `timeout` is a report, not a kill.
            status = STATUS_TIMEOUT if elapsed > spec.budget_s else STATUS_OK
            items = result.get("items") if isinstance(result, dict) else None
            _write(spec, ctx.run_date, now, status=status, attempt=attempt,
                   duration_ms=int(elapsed * 1000),
                   items=int(items) if isinstance(items, (int, float)) else None,
                   error_text=(f"overran budget {spec.budget_s:.0f}s"
                               if status == STATUS_TIMEOUT else None))
            if status == STATUS_TIMEOUT:
                log.warning("pass-ledger: %s took %.1fs (budget %.0fs)",
                            spec.name, elapsed, spec.budget_s)
            statuses[spec.name] = status
            per_pass[spec.name] = result if isinstance(result, dict) else {}
            break

    return {"statuses": statuses, "counters": per_pass}
