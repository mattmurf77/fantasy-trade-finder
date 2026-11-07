"""One bounded worker; fetching is outside simulation, completion is atomic."""
import json
import threading
import time

from ..feature_flags import is_enabled
from . import provider, store, batch
from .core import Unavailable
from .simulation import simulate

_lock = threading.Lock()
_worker = None


def wake(fetch_json):
    global _worker
    if not is_enabled("league.projections"):
        return
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run, args=(fetch_json,), name="league-projection-worker", daemon=True)
        _worker.start()


def _viewer_identity(user_id):
    from .. import accounts
    if accounts.is_account_user_id(user_id):
        account = accounts.get_account(user_id[len(accounts.ACCOUNT_USER_PREFIX):])
        if not account or not account.get("sleeper_user_id"):
            raise Unavailable("verified_sleeper_binding_required")
        return str(account["sleeper_user_id"])
    return str(user_id)


def _run(fetch_json):
    while is_enabled("league.projections"):
        row = store.claim()
        if not row:
            return
        started = time.monotonic()
        try:
            if not is_enabled("league.projections_provider_approved"):
                raise Unavailable("new_projection_provider_approval_pending")
            if not batch.settings()["policy_approved"]:
                raise Unavailable("projection_policy_approval_pending")
            inputs = json.loads(row["input_json"])
            snapshot = json.loads(row["snapshot_json"]) if row.get("snapshot_json") else provider.capture(row["league_id"], inputs["league_user_id"], inputs["config"], fetch_json, viewer_user_id=_viewer_identity(row["user_id"]))
            prior = store.save_snapshot(row, snapshot, inputs["config"])
            def cancelled():
                current = store.get(row["run_id"], row["user_id"], row["league_id"])
                return (not current or current["status"] != "running" or current.get("worker_token") != row.get("worker_token") or time.monotonic() - started > 540
                        or not is_enabled("league.projections") or not is_enabled("league.projections_provider_approved") or not batch.settings()["policy_approved"])
            if cancelled():
                raise Unavailable("cancelled", state="cancelled")
            result = prior or simulate(snapshot, inputs["config"], cancelled=cancelled)
            result = {**result, "reused_compatible_result": bool(prior), "verified_at": snapshot["captured_at"]}
            store.finish(row, result)
        except Unavailable as exc:
            store.fail(row, exc)
        except PermissionError:
            store.fail(row, Unavailable("league_membership_changed", state="failed"))
        except Exception:
            # Exception text can contain provider URLs/payloads. Keep public
            # failure reasons bounded and do not log private inputs.
            store.fail(row, Unavailable("projection_run_failed", state="failed"))
