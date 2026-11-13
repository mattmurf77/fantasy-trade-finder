"""One bounded worker; fetching is outside simulation, completion is atomic."""
import json
import logging
import threading
import time

from ..feature_flags import is_enabled
from . import provider, store, batch, clinch
from .core import Unavailable, VERSION
from .simulation import simulate

log = logging.getLogger(__name__)
_lock = threading.Lock()
_worker = None
# Max PF moves stops this long after the job started at the latest: well
# inside the job's own 540 s cancel line and the lease's 600 s write window.
MOVES_DEADLINE_SECONDS = 480


def wake(fetch_json, *, foreground_busy=None):
    global _worker
    if not is_enabled("league.projections"):
        return
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run, args=(fetch_json, foreground_busy), name="league-projection-worker", daemon=True)
        _worker.start()


def _viewer_identity(user_id):
    from .. import accounts
    if accounts.is_account_user_id(user_id):
        account = accounts.get_account(user_id[len(accounts.ACCOUNT_USER_PREFIX):])
        if not account or not account.get("sleeper_user_id"):
            raise Unavailable("verified_sleeper_binding_required")
        return str(account["sleeper_user_id"])
    return str(user_id)


def _checkpoint(cancelled, foreground_busy):
    """Yield bounded CPU time, preserving the original cancellation contract."""
    if cancelled():
        return True
    if foreground_busy is None:
        return False
    waited = False
    for _ in range(10):
        try:
            busy = foreground_busy()
        except Exception:
            # Scheduling is advisory. An unavailable signal gets bounded
            # deference, never an unbounded wait or a changed simulation.
            busy = True
        if not busy:
            break
        time.sleep(.1)
        waited = True
    # The database control read is unchanged when idle. After a pause,
    # recheck lease/flags/deadline before doing any more simulation work.
    return cancelled() if waited else False


def _attach_moves(result, prior, snapshot, sidecar, started, job_cancelled, foreground_busy):
    """Max PF moves (flag `league.max_pf_moves`, baseline runs only): add the
    saved block to `result`. Never raises and never delays the forecast past
    its budget: any failure or a hit time budget returns `result` without the
    block, and the read then reports `unavailable` / `not_computed`."""
    from . import maxpf_moves
    timed_out = []
    try:
        options = maxpf_moves.settings()
        saved = result.get("max_pf_moves")
        if prior and saved and saved.get("computed") and saved.get("settings_hash") == maxpf_moves.settings_hash(options):
            return result
        clock = time.monotonic()
        stop = min(clock + options["time_budget_seconds"], started + MOVES_DEADLINE_SECONDS)

        def cancelled():
            if time.monotonic() >= stop:
                timed_out.append(True)
                return True
            return _checkpoint(job_cancelled, foreground_busy)
        block = maxpf_moves.compute(snapshot, result, sidecar.get("free_agents") or {}, options,
                                    names=sidecar.get("names"), trade_deadline=sidecar.get("trade_deadline"),
                                    cancelled=cancelled)
        block["elapsed_ms"] = int((time.monotonic() - clock) * 1000)
        if block.get("computed") and options.get("combined_sizes") and "combined" not in block:
            # compute saved the rows and dropped only the combined step (D-261).
            log.warning("max_pf_moves combined not computed: %s", "time_budget" if timed_out else "failed")
    except Exception:
        # No exception text: it can carry provider payloads (same rule as _run).
        log.warning("max_pf_moves not computed: %s", "time_budget" if timed_out else "failed")
        return {k: v for k, v in result.items() if k != "max_pf_moves"}
    return {**result, "max_pf_moves": block}


def _run(fetch_json, foreground_busy=None):
    while is_enabled("league.projections"):
        row = store.claim()
        if not row:
            return
        started = time.monotonic()
        try:
            inputs = json.loads(row["input_json"])
            def admit():
                if not is_enabled("league.projections_provider_approved"):
                    raise Unavailable("new_projection_provider_approval_pending")
                if not batch.settings()["policy_approved"]:
                    raise Unavailable("projection_policy_approval_pending")
                if inputs.get("expected_model_version") != VERSION:
                    raise Unavailable("queued_projection_model_changed", state="failed")
                if inputs.get("baseline_run_id"):
                    baseline = store.get(inputs["baseline_run_id"], row["user_id"], row["league_id"])
                    if (inputs.get("expected_baseline_model_version") != VERSION or not baseline
                            or baseline["status"] != "complete"
                            or json.loads(baseline.get("result_json") or "{}").get("model_version") != VERSION):
                        raise Unavailable("comparison_requires_current_model_baseline", state="failed")
            def cancelled():
                current = store.control(row["run_id"], row["user_id"], row["league_id"])
                return (not current or current["status"] != "running" or current.get("worker_token") != row.get("worker_token")
                        or current["expires_at"] <= store.utc_now() or time.monotonic() - started > 540
                        or not is_enabled("league.projections") or not is_enabled("league.projections_provider_approved") or not batch.settings()["policy_approved"])
            admit()
            # Max PF moves rides only a fresh baseline capture with its flag on;
            # off, capture and the result are exactly as before.
            moves = (is_enabled("league.max_pf_moves") and inputs.get("kind") == "baseline"
                     and not row.get("snapshot_json"))
            sidecar = {} if moves else None
            if row.get("snapshot_json"):
                snapshot = json.loads(row["snapshot_json"])
            else:
                for attempt in range(2):
                    # A changed capture is discarded in full. The second attempt
                    # shares this job's original lease/deadline and revalidates
                    # authority, policy and model before any further source reads.
                    if attempt:
                        admit()
                    if cancelled():
                        raise Unavailable("cancelled", state="cancelled")
                    try:
                        if moves:
                            sidecar.clear()
                        snapshot = provider.capture(row["league_id"], inputs["league_user_id"], inputs["config"], fetch_json,
                                                    viewer_user_id=_viewer_identity(row["user_id"]),
                                                    **({"sidecar": sidecar} if moves else {}))
                        break
                    except Unavailable as exc:
                        if attempt or exc.reason != "inputs_changed_during_capture":
                            raise
            if cancelled():
                raise Unavailable("cancelled", state="cancelled")
            prior = store.save_snapshot(row, snapshot, inputs["config"])
            if cancelled():
                raise Unavailable("cancelled", state="cancelled")
            result = prior or simulate(snapshot, inputs["config"],
                                       cancelled=lambda: _checkpoint(cancelled, foreground_busy))
            result = {**result, "reused_compatible_result": bool(prior), "verified_at": snapshot["captured_at"]}
            # Clinched / eliminated from the rules (D-262), on every run and on
            # a reused prior result too. Never raises; changes no probability.
            result = clinch.attach(result, snapshot)
            if moves:
                result = _attach_moves(result, prior, snapshot, sidecar, started, cancelled, foreground_busy)
            elif "max_pf_moves" in result:
                # A result reused from a run saved while the flag was on.
                result = {k: v for k, v in result.items() if k != "max_pf_moves"}
            store.finish(row, result)
        except Unavailable as exc:
            store.fail(row, exc)
        except PermissionError:
            store.fail(row, Unavailable("league_membership_changed", state="failed"))
        except Exception:
            # Exception text can contain provider URLs/payloads. Keep public
            # failure reasons bounded and do not log private inputs.
            store.fail(row, Unavailable("projection_run_failed", state="failed"))
