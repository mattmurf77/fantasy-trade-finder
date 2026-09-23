"""Paged prepared-inventory admission and evidence-before-publication wiring.

Preparation never calls this path. Only a real interactive job can adopt an
inventory; current source/model/account/disposition checks remain mandatory.
"""
from contextlib import ExitStack
import copy
import time

from . import prepared_trade_store as legacy_store
from . import prepared_trade_store_v2 as store
from . import prepared_trade_read_guard as read_guard
from . import user_data_lifecycle as lifecycle
from .prepared_trade_payload_v2 import open_attested_inventory, is_artifact_error


def _dispositions_match(server, cards, scope):
    """One bounded authenticated-index callback, not a second inventory scan."""
    survivors = server._project_trade_dispositions(
        cards, scope.user_id, scope.league_id, prepared=True)
    return len(survivors) == len(cards)


def try_adopt(server, *, job_id, context, fairness, prefs):
    """None: no v2 artifact; False: miss; True: job handled, including errors.

    The reader never supplies a whole inventory JSON object. Runtime retention
    after publication is the existing cumulative job/service behavior, not an
    additional prepared-bundle copy.
    """
    from . import prepared_trade_runtime as runtime

    scope = runtime.scope_for(context.user_id, context.league_id, context.league_user_id,
                              context.scoring_format, fairness)
    claim, guard, cached = None, None, None
    published = 0
    handled_evidence = False
    try:
        reader = store.peek_inventory(scope, now=runtime.utcnow())
        if reader is None:
            return None
        cached = reader.header
        metadata = reader.metadata()
        identity = runtime.model_identity(server)
        if legacy_store.dependency_hash(identity) != legacy_store.dependency_hash(cached["model_identity"]):
            return False
        target = runtime.refresh_target(server, scope)
        if (set(context.user_roster) != set(p for p in target["user_roster"]
                if p in context.trade_service._players) or
                {m.user_id: set(m.roster) for m in context.league.members
                 if m.user_id not in {scope.user_id, scope.league_user_id}} !=
                {m["user_id"]: {p for p in m["player_ids"] if p in context.trade_service._players}
                 for m in target["opponents"]}):
            return False
        session = runtime._session_for_context(context)
        # Pin observed roster/availability before admission too. In particular,
        # league_members may change independently of the provider target while
        # the compact index is being scanned; do not bless that new baseline.
        guard = read_guard.capture(server, scope, expires_at=min(
            legacy_store._time(cached["expires_at"]),
            legacy_store._time(metadata["codec"]["expires_at"] or cached["expires_at"])))
        # Capture the active invariant BEFORE the admission comparison. Taking
        # it afterward could bless an explicit board edit that raced admission.
        active_receipt = runtime.active_dependency_receipt(server, scope, session, target,
            exclude_job_id=metadata["generation_job_id"], own_mutations=metadata["mutations"],
            served_at=(cached.get("publication") or {}).get("served_at"))
        receipt = runtime.dependency_receipt(server, scope, session, target,
            exclude_job_id=metadata["generation_job_id"], own_mutations=metadata["mutations"],
            served_at=(cached.get("publication") or {}).get("served_at"))
        if legacy_store.dependency_hash(receipt) != legacy_store.dependency_hash(cached["dependency_receipt"]):
            return False
        # The store attests full semantic validation of the pinned sealed root.
        # Admission still checks all dispositions; each publishing batch is
        # independently revalidated and durably bound before exposure.
        inventory = open_attested_inventory(reader, user_id=scope.user_id,
            league_id=scope.league_id, now=runtime.utcnow(),
            disposition_check=lambda cards: _dispositions_match(server, cards, scope))
        claim = store.claim_adoption(cached["inventory_id"], dependency_receipt=receipt,
            model_identity=identity, publication={"served_at": runtime.utcnow().isoformat(),
                "first_deck": bool(metadata["job_fields"].get("first_deck")),
                "board_state": list(server.load_board_state(scope.user_id, scope.league_id, scope.scoring_format))},
            now=runtime.utcnow())
        if claim is None:
            return False
        publication = claim["publication"]

        def still_current():
            with server._trade_jobs_lock:
                live = server._job_live(server._trade_jobs.get(job_id))
            return (live and runtime.supported(server, scope.league_id)
                and read_guard.valid(server, guard, scope=scope)
                and legacy_store.dependency_hash(runtime.model_identity(server)) == legacy_store.dependency_hash(identity)
                and runtime.utcnow() < legacy_store._time(cached["expires_at"])
                and legacy_store.dependency_hash(runtime.active_dependency_receipt(server, scope, session, target,
                    exclude_job_id=metadata["generation_job_id"],
                    own_mutations=metadata["mutations"], served_at=publication["served_at"])) == legacy_store.dependency_hash(active_receipt))

        with ExitStack() as stack:
            for uid in cached["participants"]:
                if not stack.enter_context(lifecycle.capture(uid, started=claim["work_started"]).active()):
                    raise ValueError("account_deleted")
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if not server._job_live(job):
                    return True
                job.update(copy.deepcopy(metadata["job_fields"]))
                job.update(prepared_inventory_id=cached["inventory_id"],
                    prepared_expires_at=cached["expires_at"], prepared_guard=guard,
                    final_checks_pending=True)

            had_batch = False
            for batch in inventory.batches(**publication):
                had_batch = True
                if not still_current():
                    raise ValueError("inputs_changed")
                for card, row in zip(batch["cards"], batch["impression_rows"]):
                    row["features_json"].update(
                        prepared_runtime=batch["runtime_records"][card.trade_id],
                        prepared_inventory_id=cached["inventory_id"], deck_source="prepared_adoption")
                start, end = batch["cursor_before"], batch["cursor_after"]
                store.ensure_adoption_evidence(claim, candidate_set=batch["candidate_set"],
                    rows=batch["impression_rows"], ordinal_start=start["cards"], ordinal_end=end["cards"],
                    ghost_start=start["ghosts"], ghost_end=end["ghosts"], now=runtime.utcnow())
                handled_evidence = True
                complete = end["cards"] == inventory.card_count and end["ghosts"] == cached["ghost_count"]
                if (end["cards"] > claim["published_count"] or end["ghosts"] > claim["ghost_published_count"]
                        or (complete and end == {"cards": 0, "ghosts": 0})):
                    store.checkpoint_adoption(claim, published_count=end["cards"],
                        expected_prefix=claim["published_count"], ghost_published_count=end["ghosts"],
                        expected_ghost_prefix=claim["ghost_published_count"], complete=complete,
                        now=runtime.utcnow())
                    claim.update(published_count=end["cards"], ghost_published_count=end["ghosts"])
                if not still_current():
                    raise ValueError("inputs_changed")
                visible = server._project_trade_dispositions(
                    batch["cards"], scope.user_id, scope.league_id, prepared=True)
                visible_ids = {card.trade_id for card in visible}
                with server._trade_jobs_lock:
                    job = server._trade_jobs.get(job_id)
                    if not server._job_live(job):
                        raise ValueError("inputs_changed")
                    for card in visible:
                        card._prepared_guard = guard
                        if getattr(card, "owner_evaluation", None) is not None:
                            card.owner_published = True
                        context.trade_service._trade_cards[card.trade_id] = card
                        exemption = batch["significance_by_trade_id"].get(card.trade_id)
                        if exemption is not None:
                            server._significance_exemptions_for(context.trade_service)[
                                server._significance_card_key(card)] = exemption
                    # Readers retain the previous list after releasing the
                    # lock; replace its shallow container, never mutate it.
                    job["cards"] = [*job["cards"], *copy.deepcopy([
                        card for card in batch["public_cards"] if card["trade_id"] in visible_ids])]
                    job["final_checks_pending"] = False
                    job["prepared_progress_at"] = time.monotonic()
                published = end["cards"]

            if not had_batch:
                if not still_current():
                    raise ValueError("inputs_changed")
                store.ensure_adoption_evidence(claim, candidate_set=metadata["candidate_set"], rows=[],
                    ordinal_start=0, ordinal_end=0, ghost_start=0, ghost_end=0, now=runtime.utcnow())
                handled_evidence = True
                store.checkpoint_adoption(claim, published_count=0, expected_prefix=claim["published_count"],
                    ghost_published_count=0, expected_ghost_prefix=claim["ghost_published_count"],
                    complete=True, now=runtime.utcnow())
                if not still_current():
                    raise ValueError("inputs_changed")
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if server._job_live(job):
                    job["final_checks_pending"] = False
                    job["opponents_done"] = job["opponents_total"]
            server._finish_trade_job(job_id)
            server.log.info("prepared paged inventory adopted: cards=%d", published)
            return True
    except Exception as exc:
        server.log.warning("prepared paged adoption unavailable (%s)", type(exc).__name__)
        if cached is not None and (isinstance(exc, store.InvalidArtifact) or is_artifact_error(exc)):
            try:
                store.retire_invalid_inventory(cached["inventory_id"], cached["root_sha256"])
            except Exception:
                # A transient recovery write failure cannot authorize exposure
                # or delete another inventory; leave retry to later requests.
                server.log.warning("prepared invalid inventory retirement deferred")
        if str(exc) in {"inputs_changed", "account_deleted"} or isinstance(exc, legacy_store.StaleWork):
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if job is not None:
                    for public in job.get("cards", ()):
                        card = context.trade_service._trade_cards.get(public["trade_id"])
                        if card is not None and guard is not None and getattr(card, "_prepared_guard", None) is guard:
                            context.trade_service._trade_cards.pop(card.trade_id, None)
                    server._revoke_trade_job_locked(job, "inputs_changed")
            return True
        # Once evidence has committed, never mix in an unrelated fresh suffix.
        if published or handled_evidence:
            server._finish_trade_job(job_id, error="prepared_adoption_incomplete")
            return True
        with server._trade_jobs_lock:
            job = server._trade_jobs.get(job_id)
            if job is not None:
                for key in ("prepared_inventory_id", "prepared_expires_at", "prepared_guard", "first_deck",
                            "board_refresh", "suppression_note"):
                    job.pop(key, None)
        return False
    finally:
        if claim is not None:
            try:
                store.release_adoption(claim)
            except Exception:
                server.log.warning("prepared paged adoption lease release deferred to expiry")
